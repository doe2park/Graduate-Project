"""Question -> answer loop for Ask-the-twin: live (Claude API + read-only tools) or mock (scripted, same tools).

Both modes emit the same event stream (dicts) so the browser and the tests do not care which one ran:
  {'type': 'status', 'text'}              progress line
  {'type': 'tool', 'name', 'input', 'summary'}
  {'type': 'text', 'text'}                answer text delta (markdown-ish, citations as [[element id]])
  {'type': 'final', 'answer', 'citations', 'tools_used', 'mode', 'model', ...}
  {'type': 'error', 'message'}
Citations are verified server-side: an id counts as grounded only if it is the selected element or appeared in a
tool result during this answer. Unverified ids are returned flagged and are not highlighted.
"""
from __future__ import annotations

import json
import re
import time

from . import index as ix
from .tools import TOOL_SCHEMAS, Twin, ids_in, run_tool

CITE_RX = re.compile(r'\[\[([A-Za-z0-9_.:-]{1,40})\]\]')
DEFAULT_MODEL = 'claude-sonnet-5-5'
MAX_ROUNDS = 8

SYSTEM_PROMPT = """You are the diagnostic assistant inside the Grimes Engineering Center (UC Berkeley) digital twin.
A facilities user has clicked a BIM element (and a point on it) in the 3D viewer and asks a question about it.

Data you can reach only through the read-only tools:
- Design BIM: ten element layers (equipment, receptacles, lighting, life safety, structure, conduit, ductwork, hydronic/mechanical piping, plumbing, fire sprinkler piping) with identity, type, CAD layer/system code, level and design parameters, plus interior ceiling slices for Levels 1-3.
- Geometry: bounding boxes in the viewer frame (metres, +Y up). Gaps are box-to-box and approximate.
- Inferred: service hints from manufacturer/family names (e.g. cast-iron no-hub = drain/waste; Type L copper = pressurized water; Price SDV coil = reheat coil), rooms from nearby labelled equipment, adjacency runs from touching boxes. There is NO verified pipe/duct connectivity, flow direction, valve-to-zone mapping or room geometry.
- Demo sensors: 17 simulated sensors (none installed). Their values are SIMULATED, never measurements.

Rules:
1. Every fact must come from a tool result in this conversation or from the selected-element context below. If the data cannot answer, say so plainly and name what record would answer it (e.g. plumbing isometrics, valve tags, BAS points). Never invent elements, distances, readings, rooms or connections.
2. Cite every element you mention as [[id]] with an id that a tool returned (the viewer turns these into clickable, highlighted chips). Do not cite ids you have not seen in a tool result.
3. If the selected element is large (a ceiling, slab, beam or long run, > ~3 m), query around the clicked point instead of the whole element. Use the tools efficiently: usually elements_near (above_only for anything seen on a ceiling), then get_element / connected_run / list_sensors / sensor_readings as needed. Prefer parallel tool calls when independent. Stop after at most ~6 tool calls.
4. Use the numbers the tools give (vertical_gap_m, horizontal_gap_m). Describe direction as above / below / beside plus horizontal distance; do not use compass directions (north is not verified in this frame).
5. Any sensor value must be written as "simulated demo" (e.g. "demo sensor (simulated): +8.8 degC above baseline").
6. Be honest about confidence: high only when geometry and a sensor signal agree; medium when one strong water/air source is directly above; low when it rests on proximity or name heuristics alone.

Answer format (plain text with light markdown, at most ~170 words):
**Most likely source:** [[id]] <short description> - ~N m above (M m horizontally) · confidence: low|medium|high
**Why:** 2-4 short bullets with the evidence (type/service, distance, demo sensor trend).
**Check first:** 1-3 short bullets (what to inspect, in order).
**Other candidates:** up to 3 bullets with [[id]] and distance.
**Limits:** one line on what the twin cannot tell.
For a non-diagnostic question (e.g. "what is this?", "which valve...?"), replace the first line with **Answer:** and keep the same sections that apply."""


def context_block(twin: Twin, element_id=None, point=None) -> tuple[str, set]:
    lines, grounded = [], set()
    if element_id and str(element_id) in twin.box:
        eid = str(element_id)
        grounded.add(eid)
        lines.append('Selected element: ' + json.dumps(twin.summary(eid)))
    elif element_id:
        lines.append(f'Selected element id {element_id} is not in the twin index.')
    if point is not None:
        lines.append(f'Clicked point (viewer frame, m): {[round(v, 2) for v in point]}')
    if not lines:
        lines.append('No element selected.')
    return '\n'.join(lines), grounded


def verify_citations(twin: Twin, text: str, grounded: set) -> list:
    out, seen = [], set()
    for cid in CITE_RX.findall(text):
        if cid in seen:
            continue
        seen.add(cid)
        known = cid in twin.box
        row = {'id': cid, 'known': known, 'verified': known and cid in grounded}
        if known:
            s = twin.summary(cid)
            row.update({'layer': s['layer'], 'type': s.get('type'), 'name': s.get('name'), 'level': s.get('level'),
                        'bbox_m': twin.box[cid], 'in_viewer': s['layer'] in ix.VIEWER_LAYERS})
        out.append(row)
    return out


def tool_summary(name, args, result) -> str:
    if 'error' in result:
        return f'error: {result["error"]}'
    if name in ('elements_near', 'find_elements'):
        return f'{result.get("total_found", 0)} elements' + (f' · {", ".join(f"{k} {v}" for k, v in list(result.get("counts_by_layer", {}).items())[:4])}' if result.get('counts_by_layer') else '')
    if name == 'connected_run':
        return f'{result.get("elements_reached")} touching elements · {len(result.get("notable_on_run", []))} notable'
    if name == 'list_sensors':
        return f'{len(result.get("sensors", []))} demo sensors'
    if name == 'sensor_readings':
        lt = result.get('latest') or {}
        return f'simulated latest {lt.get("value")} {result.get("unit")}'
    if name == 'room_of':
        return f'{result.get("level")} · {result.get("room") or "room unknown"} ({result.get("confidence") or "no label"})'
    if name == 'get_element':
        e = result.get('element', {})
        return f'{e.get("type")} · {e.get("layer")} · {e.get("level")}'
    return 'ok'


# ---------------------------------------------------------------- live mode
class _Never(Exception):
    pass


def _sdk_errors():
    """The SDK's typed errors, or never-raised stand-ins when the SDK is absent (tests with a fake client)."""
    try:
        import anthropic
        return anthropic
    except ImportError:
        import types
        return types.SimpleNamespace(AuthenticationError=_Never, RateLimitError=_Never, APIStatusError=_Never, APIConnectionError=_Never)

class LiveAgent:
    def __init__(self, twin: Twin, client, model=DEFAULT_MODEL, effort='medium', max_tokens=8000, fallbacks=True):
        self.twin, self.client, self.model, self.effort, self.max_tokens, self.fallbacks = twin, client, model, effort, max_tokens, fallbacks
        self.tools = [dict(t, eager_input_streaming=True) for t in TOOL_SCHEMAS]

    def ask(self, question: str, element_id=None, point=None, history=None):
        anthropic = _sdk_errors()
        ctx, grounded = context_block(self.twin, element_id, point)
        messages = []
        for h in (history or [])[-3:]:
            if h.get('q') and h.get('a'):
                messages += [{'role': 'user', 'content': str(h['q'])[:2000]}, {'role': 'assistant', 'content': str(h['a'])[:4000]}]
        messages.append({'role': 'user', 'content': f'{ctx}\n\nQuestion: {question}'})
        system = [{'type': 'text', 'text': SYSTEM_PROMPT, 'cache_control': {'type': 'ephemeral'}}]
        answer, used, usage = '', [], {'input_tokens': 0, 'output_tokens': 0, 'cache_read_input_tokens': 0}
        t0 = time.time()
        downgraded = False
        for _round in range(MAX_ROUNDS):
            kwargs = dict(model=self.model, max_tokens=self.max_tokens, system=system, tools=self.tools, messages=messages,
                          output_config={'effort': self.effort})
            if self.fallbacks:
                kwargs.update(betas=['server-side-fallback-2026-07-01'], fallbacks='default')
            round_text = ''
            try:
                with self.client.beta.messages.stream(**kwargs) as stream:
                    for event in stream:
                        if event.type == 'content_block_delta' and getattr(event.delta, 'type', '') == 'text_delta':
                            round_text += event.delta.text
                            yield {'type': 'text', 'text': event.delta.text}
                    msg = stream.get_final_message()
            except anthropic.AuthenticationError:
                yield {'type': 'error', 'message': 'The Anthropic API rejected ANTHROPIC_API_KEY (401). Check the key, or restart with --mock.'}
                return
            except anthropic.RateLimitError:
                yield {'type': 'error', 'message': 'Rate limited by the Anthropic API (429). Wait a moment and ask again.'}
                return
            except anthropic.APIStatusError as e:
                if e.status_code == 400 and (self.fallbacks or self.tools[0].get('eager_input_streaming')) and not downgraded:
                    # Optional request features (refusal fallback beta, eager tool streaming) rejected: retry once without them.
                    downgraded, self.fallbacks = True, False
                    self.tools = [dict(t) for t in TOOL_SCHEMAS]
                    yield {'type': 'status', 'text': 'retrying without optional API features'}
                    continue
                yield {'type': 'error', 'message': f'Anthropic API error {e.status_code}: {getattr(e, "message", "")}'[:300]}
                return
            except anthropic.APIConnectionError:
                yield {'type': 'error', 'message': 'Cannot reach the Anthropic API (network). Check the connection, or restart with --mock.'}
                return
            except ValueError as e:   # unparseable eager tool input: re-issue once per round
                yield {'type': 'status', 'text': f'retrying after malformed tool input ({e})'[:120]}
                continue
            for k in usage:
                usage[k] += getattr(msg.usage, k, 0) or 0
            answer += round_text
            if msg.stop_reason == 'refusal':
                yield {'type': 'error', 'message': 'The model declined this request.'}
                return
            messages.append({'role': 'assistant', 'content': msg.content})
            calls = [b for b in msg.content if b.type == 'tool_use']
            if msg.stop_reason == 'max_tokens' and calls:
                yield {'type': 'error', 'message': 'Answer was cut off (max_tokens) mid tool call.'}
                return
            if msg.stop_reason != 'tool_use' or not calls:
                break
            if round_text:
                answer += '\n\n'
                yield {'type': 'text', 'text': '\n\n'}
            results = []
            for b in calls:
                res = run_tool(self.twin, b.name, b.input)
                grounded |= ids_in(res)
                used.append({'name': b.name, 'input': b.input})
                yield {'type': 'tool', 'name': b.name, 'input': b.input, 'summary': tool_summary(b.name, b.input, res)}
                results.append({'type': 'tool_result', 'tool_use_id': b.id, 'content': json.dumps(res, separators=(',', ':')),
                                **({'is_error': True} if 'error' in res else {})})
            messages.append({'role': 'user', 'content': results})   # all results in one user turn
        yield {'type': 'final', 'answer': answer.strip(), 'citations': verify_citations(self.twin, answer, grounded),
               'tools_used': used, 'mode': 'live', 'model': self.model, 'effort': self.effort, 'usage': usage,
               'seconds': round(time.time() - t0, 1)}


# ---------------------------------------------------------------- mock mode
WATER_WEIGHT = [('reheat coil', 3.0), ('drain pan', 3.0), ('pressurized copper', 3.0), ('heater', 3.0), ('steel piping', 2.5),
                ('drain / waste', 2.5), ('sprinkler', 2.0), ('valve', 2.0), ('air handling', 2.0), ('ductwork', 0.6), ('air outlet', 0.4)]


def _water_score(el):
    svc = (el.get('service_hint') or {}).get('service', '')
    w = next((wt for k, wt in WATER_WEIGHT if k in svc), 0.0)
    return w


class MockAgent:
    """Scripted answers built only from real tool results (no API key). Labelled MOCK in every answer."""

    def __init__(self, twin: Twin, delay=0.012):
        self.twin, self.delay = twin, delay

    def _tool(self, name, args, used, grounded):
        res = run_tool(self.twin, name, args)
        grounded |= ids_in(res)
        used.append({'name': name, 'input': args})
        return res, {'type': 'tool', 'name': name, 'input': args, 'summary': tool_summary(name, args, res)}

    def _stream(self, text):
        for chunk in re.findall(r'\S+\s*|\s+', text):
            if self.delay:
                time.sleep(self.delay)
            yield {'type': 'text', 'text': chunk}

    def ask(self, question: str, element_id=None, point=None, history=None):
        t0 = time.time()
        _, grounded = context_block(self.twin, element_id, point)
        used = []
        q = question.lower()
        ref = None
        if element_id and str(element_id) in self.twin.box:
            b = self.twin.box[str(element_id)]
            large = max(b[3] - b[0], b[5] - b[2]) > 3.0
            ref = {'point': list(point)} if (large and point) else {'element_id': str(element_id)}
        elif point:
            ref = {'point': list(point)}
        if ref is None:
            text = '**Answer:** Select an element in the viewer first (click it), then ask again. *(mock mode)*'
        elif re.search(r'leak|stain|drip|wet|water damage|moist|mold|mould|puddle', q):
            text = yield from self._leak(ref, used, grounded)
        elif re.search(r'valve|shut ?off|isolat', q):
            text = yield from self._valve(ref, used, grounded)
        elif re.search(r'feed|serv|supplied|upstream|where does .* come from|ahu|air handler', q):
            text = yield from self._feed(ref, used, grounded)
        else:
            text = yield from self._describe(ref, used, grounded)
        yield from self._stream(text)
        yield {'type': 'final', 'answer': text, 'citations': verify_citations(self.twin, text, grounded), 'tools_used': used,
               'mode': 'mock', 'model': 'mock (scripted, tool-grounded)', 'seconds': round(time.time() - t0, 1)}

    @staticmethod
    def _d(el):
        v = 'just ' + el['vertical'] if el['vertical_gap_m'] < 0.05 else f'~{el["vertical_gap_m"]:.1f} m {el["vertical"]}'
        return v + (f' ({el["horizontal_gap_m"]:.1f} m horizontally)' if el['horizontal_gap_m'] >= 0.05 else ', directly over it')

    @staticmethod
    def _label(el):
        svc = (el.get('service_hint') or {}).get('service')
        return f'{el.get("type") or el["layer"]}' + (f' - {svc}' if svc else '')

    @staticmethod
    def _svc(el):
        return (el.get('service_hint') or {}).get('service') or el.get('type') or el['layer']

    def _leak(self, ref, used, grounded):
        near, ev = self._tool('elements_near', dict(ref, radius_m=2.0, above_only=True, layers=['plumbing', 'hydronic', 'fire', 'duct', 'equipment'], limit=60), used, grounded)
        yield ev
        room, ev = self._tool('room_of', dict(ref), used, grounded)
        yield ev
        sens, ev = self._tool('list_sensors', dict(ref, radius_m=6), used, grounded)
        yield ev
        signals = {}
        for s in sens.get('sensors', []):
            if s['type'] in ('alert', 'leak', 'dts'):
                r, ev = self._tool('sensor_readings', {'sensor_id': s['sensor_id'], 'hours': 24}, used, grounded)
                yield ev
                signals.setdefault(s['anchor_element_id'], []).append(r)
        cands = []
        for el in near.get('elements', []):
            w = _water_score(el)
            if w <= 0:
                continue
            bonus = 3.0 if any(r.get('alert_active') for r in signals.get(el['id'], [])) else 0.0
            dist = (el['vertical_gap_m'] ** 2 + el['horizontal_gap_m'] ** 2) ** 0.5
            cands.append((w + bonus - dist, el, bool(bonus)))
        cands.sort(key=lambda c: -c[0])
        room_txt = f'{room.get("level")} · {room.get("room")} (inferred, {room.get("confidence")})' if room.get('room') else f'{room.get("level")} (room unknown)'
        if not cands:
            return (f'**Answer:** No water-carrying element was found within 2 m above this spot ({room_txt}). '
                    f'{near.get("total_found", 0)} other elements are above it.\n**Check first:**\n- Look further along the ceiling, or ask again with a larger radius.\n'
                    '**Limits:** design model only; no as-built survey or verified connectivity. *(mock mode: scripted, tool-grounded)*')
        score, top, alerted = cands[0]
        wet = any(r.get('unit') == 'bool' and (r.get('latest') or {}).get('value') == 1 for r in signals.get(top['id'], []))
        conf = 'high' if alerted and wet else 'medium' if alerted or (_water_score(top) >= 2.5 and top['horizontal_gap_m'] < 0.8) else 'low'
        why = [f'- {self._label(top)}, {top["service_hint"]["basis"]}.', f'- Directly in the plenum: {self._d(top)}.']
        for r in signals.get(top['id'], []):
            lt = r['latest']
            if r['unit'] == 'bool':
                why.append(f'- Demo sensor {r["label"]} (simulated): {"WET" if lt["value"] == 1 else "dry"} now and over 24 h.' if r['stats'] and r['stats']['max'] == lt['value'] else f'- Demo sensor {r["label"]} (simulated): {lt["value"]}.')
            else:
                why.append(f'- Demo sensor {r["label"]} (simulated): latest {lt["value"]} {r["unit"]}, 24 h range {r["stats"]["min"]}-{r["stats"]["max"]}'
                           + (' - alert rule active' if r.get('alert_active') else '') + '.')
        others = [c for c in cands[1:] if c[1]['id'] != top['id']][:3]
        lines = [f'**Most likely source:** [[{top["id"]}]] {self._svc(top)} - {self._d(top)} · confidence: {conf}',
                 f'**Where:** {room_txt}.', '**Why:**', *why, '**Check first:**',
                 f'- Open the ceiling at this spot and inspect [[{top["id"]}]] (joints, fittings, insulation).']
        if others:
            lines.append(f'- Then [[{others[0][1]["id"]}]] ({self._label(others[0][1])}).')
            lines.append('**Other candidates:**')
            lines += [f'- [[{c[1]["id"]}]] {self._label(c[1])}, {self._d(c[1])}' for c in others]
        lines.append('**Limits:** design BIM positions, box distances, sensors are simulated demos; no verified connectivity. *(mock mode: scripted, tool-grounded)*')
        return '\n'.join(lines)

    def _valve(self, ref, used, grounded):
        room, ev = self._tool('room_of', dict(ref), used, grounded)
        yield ev
        found, ev = self._tool('find_elements', dict(ref, text='valve', level=room.get('level'), limit=60), used, grounded)
        yield ev
        iso = [e for e in found.get('elements', []) if 'isolation' in (e.get('service_hint') or {}).get('service', '')]
        lvl = room.get('level')
        order = {'plumbing': 0, 'hydronic': 1}
        same = sorted([e for e in iso if e.get('level') == lvl] or iso, key=lambda e: (order.get(e['layer'], 2), e['gap_m']))
        if not same:
            return (f'**Answer:** No shut-off (ball/butterfly) valve was found on {lvl}. '
                    '**Limits:** the model has no valve-to-zone mapping; check the plumbing isometrics and valve tags. *(mock mode)*')
        top = same[0]
        domestic = None
        if top['layer'] == 'hydronic':
            domestic, ev = self._tool('find_elements', {'text': 'valve', 'layer': 'plumbing', 'level': lvl, 'limit': 5}, used, grounded)
            yield ev
        lines = [f'**Answer:** Nearest shut-off valve candidate: [[{top["id"]}]] {self._svc(top)} on {top.get("level")}, {top["gap_m"]:.1f} m away ({top["layer"]} layer) · confidence: low',
                 '**Why:**', f'- {top["service_hint"]["basis"]}; it is the closest isolation valve on the same level.',
                 f'- {len(iso)} of the {len(found.get("elements", []))} nearest valves on {lvl} are ball/butterfly (isolation) valves; none is linked to a room or zone in the model.',
                 *([f'- It is on the hydronic (mechanical piping) layer: it isolates heating/cooling water, not domestic water.'
                    + (f' The plumbing layer has no valve on {lvl}.' if domestic and domestic.get('total_found') == 0 else '')] if top['layer'] == 'hydronic' else []),
                 '**Check first:**',
                 f'- Confirm on site/drawings that [[{top["id"]}]] serves this area before closing it.']
        if len(same) > 1:
            lines.append('**Other candidates:**')
            lines += [f'- [[{e["id"]}]] {self._label(e)}, {e["gap_m"]:.1f} m, {e["layer"]}' for e in same[1:4]]
        lines.append('**Limits:** no verified pipe connectivity, flow direction or valve tags in the twin. *(mock mode: scripted, tool-grounded)*')
        return '\n'.join(lines)

    def _feed(self, ref, used, grounded):
        start = ref.get('element_id')
        if not start or self.twin.layer.get(start) != 'duct':
            near, ev = self._tool('elements_near', dict(ref, radius_m=3, layers=['duct'], limit=5), used, grounded)
            yield ev
            els = [e for e in near.get('elements', []) if 'duct' in (e.get('type') or '').lower()] or near.get('elements', [])
            if not els:
                return '**Answer:** No ductwork within 3 m of the selection. *(mock mode)*'
            start = els[0]['id']
        run, ev = self._tool('connected_run', {'element_id': start, 'max_elements': 250}, used, grounded)
        yield ev
        notable = run.get('notable_on_run', [])
        if not notable:
            return (f'**Answer:** Following touching duct segments from [[{start}]] ({run.get("elements_reached")} elements) found no AHU or terminal unit. '
                    '**Limits:** adjacency is geometric only. *(mock mode)*')
        top = notable[0]
        lines = [f'**Answer:** Nearest air source on this run: [[{top["id"]}]] {self._svc(top)}, {top["hops"]} segments from [[{start}]] · confidence: low',
                 '**Why:**', f'- Touching-box run of {run["elements_reached"]} duct elements ({", ".join(f"{k} {v}" for k, v in list(run["types_in_run"].items())[:3])}).',
                 f'- {top["service_hint"]["basis"] if top.get("service_hint") else "type " + str(top.get("type"))}.',
                 '**Check first:**', f'- Trace the duct from [[{start}]] to [[{top["id"]}]] on the mechanical drawings.']
        if len(notable) > 1:
            lines.append('**Other candidates:**')
            lines += [f'- [[{n["id"]}]] {self._label(n)}, {n["hops"]} segments' for n in notable[1:4]]
        lines.append('**Limits:** touching boxes are not verified connections; no airflow direction in the model. *(mock mode: scripted, tool-grounded)*')
        return '\n'.join(lines)

    def _describe(self, ref, used, grounded):
        lines = []
        if ref.get('element_id'):
            el, ev = self._tool('get_element', {'element_id': ref['element_id']}, used, grounded)
            yield ev
            e = el['element']
            lines.append(f'**Answer:** [[{e["id"]}]] is a {self._label(e)} on {e.get("level")} ({e["layer"]} layer, system {e.get("system")}).')
        near, ev = self._tool('elements_near', dict(ref, radius_m=1.0, limit=6), used, grounded)
        yield ev
        lines.append(f'**Nearby (1 m):** {near.get("total_found", 0)} elements - ' + ', '.join(f'{k} {v}' for k, v in list(near.get('counts_by_layer', {}).items())[:4]) + '.')
        lines += [f'- [[{x["id"]}]] {self._label(x)}, {x["gap_m"]:.1f} m' for x in near.get('elements', [])[:3]]
        lines.append('**Limits:** design BIM only. *(mock mode: scripted, tool-grounded; ask about a leak, a valve or what feeds a duct for a diagnosis)*')
        return '\n'.join(lines)
