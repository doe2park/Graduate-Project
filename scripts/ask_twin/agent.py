"""Question -> answer loop for Ask-the-twin: live (Claude API + read-only tools) or mock (scripted, same tools).

Both modes emit the same event stream (dicts) so the browser and the tests do not care which one ran:
  {'type': 'status', 'text'}              progress line
  {'type': 'tool', 'name', 'input', 'summary'}
  {'type': 'text', 'text'}                answer text delta (live: plain paragraph + 'Evidence: [[id]] ...'; mock: card markdown)
  {'type': 'final', 'answer', 'citations', 'tools_used', 'mode', 'model', ...}
  {'type': 'error', 'message'}
  {'type': 'status', 'phase': 'thinking', 'text'}   live: before each model round ("Thinking…")
The server adds {'type': 'speak', 'part': 'lead'|'check', 'text'} and final['spoken'] (scripts/ask_twin/speech.py).
Citations are verified server-side: an id counts as grounded only if it is the selected element or appeared in a
tool result during this answer. Unverified ids are returned flagged and are not highlighted.
"""
from __future__ import annotations

import json
import re
import time

from . import index as ix
from .tools import TOOL_SCHEMAS, Twin, ids_in, run_tool

NOT_RUN_RX = re.compile(r'hanger|support|clearance zone|anno', re.I)
CITE_RX = re.compile(r'\[\[([A-Za-z0-9_.:-]{1,40})\]\]')
DEFAULT_MODEL = 'claude-sonnet-5-5'
MAX_ROUNDS = 8
DEFAULT_MAX_TOKENS = 4000   # per model round; answers are ~170 words, the rest is room for adaptive thinking + tool calls

SYSTEM_PROMPT = """You are the diagnostic assistant inside the Grimes Engineering Center (UC Berkeley) digital twin.
A facilities user has clicked a BIM element (and a point on it) in the 3D viewer and asks a question about it.

Data you can reach only through the read-only tools:
- Design BIM: ten element layers (equipment, receptacles, lighting, life safety, structure, conduit, ductwork, hydronic/mechanical piping, plumbing, fire sprinkler piping) with identity, type, CAD layer/system code, level and design parameters, plus interior ceiling slices for Levels 1-3.
- Geometry: bounding boxes in the viewer frame (metres, +Y up). Gaps are box-to-box and approximate.
- Inferred: service hints from manufacturer/family names (e.g. cast-iron no-hub = drain/waste; Type L copper = pressurized water; Price SDV coil = reheat coil), rooms from nearby labelled equipment, adjacency runs from touching boxes. There is NO verified pipe/duct connectivity, flow direction, valve-to-zone mapping or room geometry.
- Demo sensors: 17 simulated sensors (none installed). Their values are SIMULATED, never measurements.
- Rooms: find_rooms lists named rooms and restrooms with an approximate centre point (from labels, no outlines). For "closest X to room Y": find_rooms, then find_elements or elements_near around that centre_point.
- Electricity: electrical_summary gives DESIGN load (nameplate volt-amperes) and nearby panels; building_meters gives MEASURED power per building service. Nothing is measured per device, circuit or room, and the model has no circuits: for "how much power does this use", give the device's design value if it has one, then the measured building-level figure, and say plainly that the two are different things.

Rules:
1. Every fact must come from a tool result in this conversation or from the selected-element context below. If the data cannot answer, say so plainly and name what record would answer it (e.g. plumbing isometrics, valve tags, BAS points). Never invent elements, distances, readings, rooms or connections.
2. Cite every element your answer relies on as [[id]] on the Evidence line, with an id that a tool returned (the viewer turns these into clickable, highlighted chips). Do not cite ids you have not seen in a tool result.
3. If the selected element is large (a ceiling, slab, beam or long run, > ~3 m), query around the clicked point instead of the whole element. Use the tools efficiently: usually elements_near (above_only for anything seen on a ceiling), then get_element / connected_run / list_sensors / sensor_readings as needed. For "where does the air/water come from", "what feeds this" or "which VAV box", call connected_run from the selected element (or the nearest duct/pipe) and name the first terminal unit / AHU on that run, giving its distance as the number of pieces along the run (hops); do not pick a source by straight-line proximity alone. Prefer parallel tool calls when independent. Stop after at most ~6 tool calls.
4. Use the numbers the tools give (vertical_gap_m, horizontal_gap_m). Describe direction as above / below / beside plus horizontal distance; do not use compass directions (north is not verified in this frame).
5. Any sensor value must be called simulated (e.g. "a simulated demo sensor reads 8.8 degC above normal").
6. Be honest about how sure you are, in plain words: sure only when geometry and a sensor signal agree; "probably" when one strong water/air source is directly above; "possibly ..., check on site" when it rests on proximity or name heuristics alone.

Who reads the answer: facilities staff, students and visitors, most of them not engineers. It is shown on a card and read
aloud, so write the way you would explain it to a colleague standing next to you.

Answer format (strict):
- Line 1: the answer itself, one paragraph of AT MOST 3 short sentences and at most 55 words in total:
  (1) the direct answer, (2) where it is or the one key detail, (3) how sure the twin is and what to check.
  Never a 4th sentence. Leave out anything that does not answer the question (sizes, extra elements, how a tool works).
  - The first sentence answers exactly the question asked, in plain English ("This is a supply air vent in the
    ceiling." / "The air comes from a VAV box above the ceiling, about 10 duct pieces upstream."). For a two-part
    question, answer both parts in the first two sentences.
  - Plain words first. Give a technical term in parentheses at most once, right after its plain words
    ("supply air vent (diffuser)", "VAV box (a box that controls how much air goes to this area)").
  - Then where it is (room, level, distance in metres) and why it matters or what to check, one short sentence each.
  - No markdown, no bullets, no headings, no "Answer:", no element ids or [[...]], no CAD layer or system codes
    (e.g. M-HVAC-CDFF), no family or catalog names, no "confidence: low/medium/high".
  - Be honest about uncertainty in plain words: "probably", "the model shows ..., so check on site", "the twin cannot
    tell ...". A room found from nearby labels is "probably room X"; a duct run found from touching pieces is "the model
    suggests"; any sensor value comes from "a simulated demo sensor".
- Line 2: Evidence: [[id]] [[id]] ...  (the element ids behind the answer, each returned by a tool or the selected element;
  first the element the answer is mainly about: the selected element for "what is this"; the source (e.g. the VAV box)
  BEFORE the selected element for "where does it come from" / "what feeds this"; the closest element for "what is
  above"; at most 6). The viewer turns this line into clickable chips; it is not read aloud.
Write nothing before or between tool calls; write only these two lines at the end."""


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
            from .speech import spoken_name
            row.update({'layer': s['layer'], 'type': s.get('type'), 'label': spoken_name(s), 'name': s.get('name'), 'level': s.get('level'), 'size': s.get('size'), 'size_m': s.get('size_m'),
                        'bbox_m': twin.box[cid], 'in_viewer': s['layer'] in ix.VIEWER_LAYERS})
        out.append(row)
    return out


LEGACY_LEAD_RX = re.compile(r'^\s*\*\*(?:Most likely source|Answer):\*\*', re.M)
EVIDENCE_RX = re.compile(r'^[ \t]*(?:\*\*)?Evidence:(?:\*\*)?[ \t]*(.*)$', re.M | re.I)
# "…on site. Evidence: [[id]]" on one line: the Evidence line starts after the sentence, so it is never shown or spoken
INLINE_EVIDENCE_RX = re.compile(r'([.!?)])[ \t]+((?:\*\*)?Evidence:(?:\*\*)?[ \t]*\[\[)')
CAD_CODE_RX = re.compile(r'\b[A-Z]-[A-Z]{2,}(?:-[A-Z0-9]+)+\b')
MAX_EVIDENCE = 6


def split_answer(text: str) -> tuple[str, list]:
    """Plain answer format -> (visible body, evidence ids in order). Ids written in the body are moved to the evidence list."""
    text = INLINE_EVIDENCE_RX.sub(r'\1\n\2', str(text or ''))
    ev = []
    for m in EVIDENCE_RX.finditer(text):
        ev += CITE_RX.findall(m.group(1))
    body = EVIDENCE_RX.sub('', text)
    ev += CITE_RX.findall(body)
    seen, ids = set(), []
    for i in ev:
        if i not in seen:
            seen.add(i)
            ids.append(i)
    return body.strip(), ids


def tidy_answer(twin: Twin, text: str, selected=None) -> str:
    """Live answers in the plain format: one clean paragraph + 'Evidence: [[id]] ...'. The model is asked for exactly this;
    this only repairs slips (markdown, an 'Answer:' label, ids or CAD codes in the sentence). Answers in the older card
    format (**Answer:** / **Most likely source:** lead and no Evidence line) are returned unchanged."""
    text = str(text or '').strip()
    text = INLINE_EVIDENCE_RX.sub(r'\1\n\2', text)
    if not text or (LEGACY_LEAD_RX.search(text) and not EVIDENCE_RX.search(text)):
        return text
    from .speech import spoken_name   # local import: speech imports nothing from here, but keep agent importable alone
    body, ids = split_answer(text)

    def name(m):
        cid = m.group(1)
        if selected is not None and cid == str(selected):
            return 'this element'
        return 'the ' + spoken_name(twin.summary(cid) if cid in twin.box else None)
    body = CITE_RX.sub(name, body)
    body = re.sub(r'\*\*(.+?)\*\*', r'\1', body).replace('**', '')
    body = re.sub(r'^\s*(?:Answer|Most likely source)\s*:\s*', '', body, flags=re.I)
    body = re.sub(r'\s*\([^()]*' + CAD_CODE_RX.pattern + r'[^()]*\)', '', body)
    body = CAD_CODE_RX.sub('', body)
    body = re.sub(r'\s*[·,;]?\s*confidence:\s*(low|medium|high)\b', '', body, flags=re.I)
    body = re.sub(r'^\s*[-•]\s+', '', body, flags=re.M)
    body = re.sub(r'\s+', ' ', body).strip()
    body = re.sub(r'\s+([,.;:!?])', r'\1', body)
    body = body[:1].upper() + body[1:]
    if not ids:
        return body
    return body + '\nEvidence: ' + ' '.join(f'[[{i}]]' for i in ids[:MAX_EVIDENCE])


def tool_event(name, args, result) -> dict:
    """The 'tool' event the browser sees. connected_run also carries its paths (element ids from the start element to each
    notable element on the run, all from this tool result) so the headset can light the run up; nothing else is added."""
    ev = {'type': 'tool', 'name': name, 'input': args, 'summary': tool_summary(name, args, result)}
    if name == 'connected_run' and 'error' not in result:
        ev['paths'] = [{'to': n['id'], 'ids': list(n.get('path_ids') or [])} for n in result.get('notable_on_run', [])[:6]]
        ev['start'] = (result.get('start') or {}).get('id')
    vis = tool_visual(name, result)
    if vis:
        ev['visual'] = vis
    return ev


def _vis_el(s: dict) -> dict:
    """One element for the headset answer card's pictograms: id, plain name, type, layer (+ size string when recorded)."""
    from .speech import spoken_name
    out = {'id': s.get('id'), 'label': spoken_name(s), 'type': s.get('type'), 'layer': s.get('layer')}
    if s.get('size'):
        out['size'] = str(s['size'])[:24]
    if s.get('size_m'):
        out['size_m'] = s['size_m']
    return out


def tool_visual(name, result) -> dict | None:
    """Compact structured data from a tool result for the headset answer card's graphics (pictograms, height graph, run
    diagram). Copied from the tool result only (no prose parsing, nothing added); None for tools the card does not draw."""
    if not isinstance(result, dict) or 'error' in result:
        return None
    if name == 'get_element' and result.get('element'):
        e = result['element']
        return {'kind': 'element', 'element': _vis_el(e), 'level': e.get('level')}
    if name == 'room_of':
        conf = result.get('confidence')
        return {'kind': 'room', 'room': result.get('room'), 'level': result.get('level'),
                'confidence': 'recorded' if conf and conf.startswith('recorded') else conf,
                'basis': 'element' if conf and conf.startswith('recorded') else 'nearby labels'}
    if name == 'elements_near':
        items = []
        for s in result.get('elements', [])[:16]:
            it = _vis_el(s)
            it.update({'vertical': s.get('vertical'), 'vertical_gap_m': s.get('vertical_gap_m'), 'horizontal_gap_m': s.get('horizontal_gap_m')})
            items.append(it)
        q = result.get('query') or {}
        return {'kind': 'near', 'above_only': bool(q.get('above_only')), 'radius_m': q.get('radius_m'), 'total': result.get('total_found', 0),
                'counts_by_layer': dict(list((result.get('counts_by_layer') or {}).items())[:6]), 'items': items}
    if name == 'connected_run':
        notable = []
        for s in result.get('notable_on_run', [])[:4]:
            it = _vis_el(s)
            it.update({'hops': s.get('hops'), 'horizontal_gap_m': s.get('horizontal_gap_m'), 'vertical': s.get('vertical'), 'vertical_gap_m': s.get('vertical_gap_m')})
            notable.append(it)
        return {'kind': 'run', 'start': _vis_el(result.get('start') or {}), 'layer': result.get('layer'), 'reached': result.get('elements_reached'),
                'types_in_run': dict(list((result.get('types_in_run') or {}).items())[:4]), 'notable': notable}
    return None


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

def _cache_last_tool(tools):
    """Prompt caching: a breakpoint on the last tool definition caches the whole tool list (render order tools -> system ->
    messages); the system prompt carries the second breakpoint. Both are byte-stable across questions."""
    tools = [dict(t) for t in tools]
    if tools:
        tools[-1]['cache_control'] = {'type': 'ephemeral'}
    return tools


def _mark_cache_tail(messages, prev):
    """Move the rolling cache breakpoint to the last block of the newest user turn, so the next model round of this answer
    reads the earlier rounds from the cache. At most one such breakpoint at a time (the API allows four in total)."""
    if prev is not None:
        prev.pop('cache_control', None)
    last = messages[-1]
    if isinstance(last['content'], str):
        last['content'] = [{'type': 'text', 'text': last['content']}]
    block = last['content'][-1]
    block['cache_control'] = {'type': 'ephemeral'}
    return block


class LiveAgent:
    def __init__(self, twin: Twin, client, model=DEFAULT_MODEL, effort='medium', max_tokens=DEFAULT_MAX_TOKENS, fallbacks=True,
                 on_usage=None, budget_left=None):
        self.twin, self.client, self.model, self.effort, self.max_tokens, self.fallbacks = twin, client, model, effort, max_tokens, fallbacks
        self.tools = _cache_last_tool(dict(t, eager_input_streaming=True) for t in TOOL_SCHEMAS)
        # on_usage(dict): called after every model round with that response's usage (the server's daily token budget);
        # budget_left() -> int: checked before every round after the first, so a long answer stops once the budget is spent.
        self.on_usage, self.budget_left = on_usage, budget_left

    def ask(self, question: str, element_id=None, point=None, history=None):
        anthropic = _sdk_errors()
        ctx, grounded = context_block(self.twin, element_id, point)
        messages = []
        for h in (history or [])[-3:]:
            if isinstance(h, dict) and h.get('q') and h.get('a'):
                messages += [{'role': 'user', 'content': str(h['q'])[:2000]}, {'role': 'assistant', 'content': str(h['a'])[:4000]}]
        messages.append({'role': 'user', 'content': f'{ctx}\n\nQuestion: {question}'})
        system = [{'type': 'text', 'text': SYSTEM_PROMPT, 'cache_control': {'type': 'ephemeral'}}]
        answer, used, usage = '', [], {'input_tokens': 0, 'output_tokens': 0, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}
        t0 = time.time()
        downgraded, tail, stop = False, None, None
        # Optional request features are dropped per question; the shared agent only changes once a retry without them worked.
        fallbacks, tools = self.fallbacks, self.tools
        for _round in range(MAX_ROUNDS):
            if _round and self.budget_left is not None and self.budget_left() <= 0:
                yield {'type': 'error', 'message': 'Daily budget reached for the AI answers; this answer was stopped. It resets at midnight.'}
                return
            tail = _mark_cache_tail(messages, tail)
            kwargs = dict(model=self.model, max_tokens=self.max_tokens, system=system, tools=tools, messages=messages,
                          output_config={'effort': self.effort})
            if fallbacks:
                kwargs.update(betas=['server-side-fallback-2026-07-01'], fallbacks='default')
            round_text = ''
            # visible "Thinking…" while the model reasons before its first tool call or text (adaptive thinking)
            yield {'type': 'status', 'phase': 'thinking', 'text': 'Thinking…' if not used else 'Thinking about what the twin returned…'}
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
                if e.status_code == 400 and (fallbacks or tools[0].get('eager_input_streaming')) and not downgraded:
                    # Optional request features (refusal fallback beta, eager tool streaming) rejected: retry once without them.
                    downgraded, fallbacks = True, False
                    tools = _cache_last_tool(TOOL_SCHEMAS)
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
            if downgraded and (self.fallbacks or self.tools is not tools):   # the retry worked: later questions skip the features
                self.fallbacks, self.tools = False, tools
            round_usage = {k: getattr(msg.usage, k, 0) or 0 for k in usage}
            for k in usage:
                usage[k] += round_usage[k]
            if self.on_usage:
                self.on_usage(round_usage)
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
                stop = msg.stop_reason or 'end_turn'
                break
            if round_text:
                answer += '\n\n'
                yield {'type': 'text', 'text': '\n\n'}
            results = []
            for b in calls:
                res = run_tool(self.twin, b.name, b.input)
                grounded |= ids_in(res)
                used.append({'name': b.name, 'input': b.input})
                yield tool_event(b.name, b.input, res)
                results.append({'type': 'tool_result', 'tool_use_id': b.id, 'content': json.dumps(res, separators=(',', ':')),
                                **({'is_error': True} if 'error' in res else {})})
            messages.append({'role': 'user', 'content': results})   # all results in one user turn
        if stop is None:   # every round asked for more lookups: there is no answer to show
            yield {'type': 'error', 'message': 'The lookups did not settle on an answer. Ask again, or ask a narrower question.'}
            return
        # The card shows the last round's text only: anything written before a tool call was a preamble, not the answer.
        raw = round_text if round_text.strip() else answer
        if stop == 'max_tokens' and not EVIDENCE_RX.search(INLINE_EVIDENCE_RX.sub(r'\1\n\2', raw)):
            # the Evidence line closes every answer, so without it the text stopped mid-way: never show half a sentence as the answer
            yield {'type': 'error', 'message': 'The answer was cut off before it finished. Ask again.'}
            return
        answer = tidy_answer(self.twin, raw, element_id)
        if not split_answer(answer)[0]:
            yield {'type': 'error', 'message': 'The model returned no answer. Ask again.'}
            return
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


# Mock mode routes a question (typed, a preset, or a speech-to-text transcript) by keywords to a scripted, tool-grounded
# answer. Order matters: the first match wins. Anything else gets the generic description of the element and its neighbours.
MOCK_ROUTES = (
    ('leak', re.compile(r'leak|stain|drip|wet|water damage|moist|mold|mould|puddle')),
    ('valve', re.compile(r'valve|shut ?off|isolat')),
    ('comfort', re.compile(r'\bwarm|\bhot\b|\bcold\b|stuffy|comfort|too (warm|hot|cold)|\bwhy\b|temperature|\bheat')),
    ('feed', re.compile(r'feed|\bfed\b|\bserv(e|es|ed|ing)\b|supplie|upstream|comes? from|where does (the |this |that )?air|'
                        r'\bahu\b|air handler|which vav|what vav')),
    ('above', re.compile(r'\babove\b|\bover (this|the|my|me|here)\b|overhead|plenum|on top of|behind (this|the) ceiling')),
    ('lookup', re.compile(r"what(?: i|')s (this|that|it)\b|what is this|what room|which room|where am i|what am i looking at|identify|what kind")),
)


def mock_route(question: str) -> str:
    q = ' '.join(str(question or '').lower().split())
    return next((name for name, rx in MOCK_ROUTES if rx.search(q)), 'describe')


class MockAgent:
    """Scripted answers built only from real tool results (no API key). Labelled MOCK in every answer."""

    def __init__(self, twin: Twin, delay=0.012):
        self.twin, self.delay = twin, delay

    def _tool(self, name, args, used, grounded):
        res = run_tool(self.twin, name, args)
        grounded |= ids_in(res)
        used.append({'name': name, 'input': args})
        return res, tool_event(name, args, res)

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
        route = mock_route(question)
        if ref is None:
            text = '**Answer:** Select an element in the viewer first (click it), then ask again. *(mock mode)*'
        else:
            text = yield from getattr(self, '_' + route)(ref, used, grounded)
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
        fam = str(top.get('name') or '').split(' - ')[0].split(' w-')[0]
        what = 'VAV box with hot-water reheat coil' if 'terminal with hot-water reheat' in self._svc(top) else self._svc(top)
        lines = [f'**Answer:** [[{top["id"]}]] {what}' + (f' ({fam})' if fam else '')
                 + f', {top["hops"]} steps along touching ducts from [[{start}]] · confidence: low',
                 '**Why:**', f'- Nearest terminal unit on the touching-duct run: {top["hops"] - 1} duct pieces between them; the run reaches {run["elements_reached"]} elements.',
                 f'- Design record: {top.get("type")}, family {str(top.get("name") or "").split(" - ")[0] or "unknown"}; service {top["service_hint"]["basis"] if top.get("service_hint") else "unknown"}.',
                 '**Check first:**', f'- Trace the duct from [[{start}]] to [[{top["id"]}]] on the mechanical drawings.']
        if len(notable) > 1:
            lines.append('**Other candidates:**')
            lines += [f'- [[{n["id"]}]] {self._label(n)}, {n["hops"]} segments' for n in notable[1:4]]
        lines.append('**Limits:** touching boxes are not verified connections; no airflow direction in the model. *(mock mode: scripted, tool-grounded)*')
        return '\n'.join(lines)

    # The four question levels of the headset demo (look up · nearby in 3D · trace a system · reason across sources).
    # _feed is level 3; these three are levels 1, 2 and 4. Every id and number below comes from a tool result.
    def _lookup(self, ref, used, grounded):
        lines = []
        if ref.get('element_id'):
            el, ev = self._tool('get_element', {'element_id': ref['element_id']}, used, grounded)
            yield ev
            e = el['element']
            lines.append(f'**Answer:** [[{e["id"]}]] is a {self._label(e)} on {e.get("level")} ({e["layer"]} layer).')
        room, ev = self._tool('room_of', dict(ref), used, grounded)
        yield ev
        n = len(room.get('nearby_labelled_equipment') or [])
        lines += ['**Why:**', '- Identity, type and level come from its own design BIM record.',
                  f'- Room: {room.get("room") or "unknown"} on {room.get("level")} (inferred, {room.get("confidence") or "no label"}): '
                  f'the most common label among the {n} nearest room-labelled elements.' if room.get('room') else
                  f'- Room: no room-labelled element nearby on {room.get("level")}.',
                  '**Limits:** the model has no room outlines; the room is a vote, not a boundary. *(mock mode: scripted, tool-grounded)*']
        return '\n'.join(lines)

    def _above(self, ref, used, grounded):
        near, ev = self._tool('elements_near', dict(ref, radius_m=2.0, above_only=True, limit=40), used, grounded)
        yield ev
        els = [e for e in near.get('elements', []) if not NOT_RUN_RX.search(f'{e.get("type", "")} {e.get("name", "")}')]
        if not els:
            return ('**Answer:** Nothing within 2 m above this spot in the design model. '
                    '**Limits:** design BIM positions, not as-built. *(mock mode: scripted, tool-grounded)*')
        counts = ', '.join(f'{k} {v}' for k, v in list(near.get('counts_by_layer', {}).items())[:4])
        top = els[0]
        lines = [f'**Answer:** Above this spot within 2 m: {near.get("total_found")} elements ({counts}). '
                 f'Closest: [[{top["id"]}]] {self._label(top)}, {self._d(top)}.',
                 '**Closest:**', *[f'- [[{e["id"]}]] {self._label(e)}, {self._d(e)}' for e in els[:3]],
                 '**Check first:**', f'- Lift the ceiling tile next to [[{top["id"]}]] before cutting or drilling.',
                 '**Limits:** box-to-box distances from the design model, not an as-built survey. *(mock mode: scripted, tool-grounded)*']
        return '\n'.join(lines)

    def _comfort(self, ref, used, grounded):
        room, ev = self._tool('room_of', dict(ref), used, grounded)
        yield ev
        start = ref.get('element_id')
        if not start or self.twin.layer.get(start) != 'duct':
            near, ev = self._tool('elements_near', dict(ref, radius_m=3, layers=['duct'], limit=5), used, grounded)
            yield ev
            start = (near.get('elements') or [{}])[0].get('id')
        box = None
        if start:
            run, ev = self._tool('connected_run', {'element_id': start, 'max_elements': 250}, used, grounded)
            yield ev
            box = next((n for n in run.get('notable_on_run', []) if n.get('type') == 'Terminal unit'), None)
        sens, ev = self._tool('list_sensors', dict(ref, radius_m=6), used, grounded)
        yield ev
        reads = {}
        for s in sens.get('sensors', []):
            if s['type'] in ('zone', 'iaq', 'damper', 'airflow') and s['type'] not in reads:
                r, ev = self._tool('sensor_readings', {'sensor_id': s['sensor_id'], 'hours': 24}, used, grounded)
                yield ev
                reads[s['type']] = r
        room_txt = f'{room.get("room")} on {room.get("level")} (inferred, {room.get("confidence")})' if room.get('room') else f'{room.get("level")} (room unknown)'
        if not reads:
            return (f'**Answer:** {room_txt}. No demo sensor is near this spot, so the twin has no trend to reason from. '
                    '**Limits:** the model alone cannot explain a comfort complaint. *(mock mode: scripted, tool-grounded)*')
        st = lambda r: r.get('stats') or {}
        why = []
        zone, damper, iaq, air = reads.get('zone'), reads.get('damper'), reads.get('iaq'), reads.get('airflow')
        if zone:
            why.append(f'- Demo zone sensor (simulated): {zone["latest"]["value"]:+.1f} °C vs reference now, 24 h range {st(zone).get("min")} to {st(zone).get("max")}'
                       + (' - above the 2 °C rule.' if zone.get('alert_active') else '.'))
        if iaq:
            why.append(f'- Demo CO2 (simulated): {st(iaq).get("min"):.0f} to {st(iaq).get("max"):.0f} ppm over 24 h: consistent with heat from people.')
        if damper:
            why.append(f'- Demo damper at [[{damper["anchor_element_id"]}]] (simulated): {st(damper).get("min"):.0f} to {st(damper).get("max"):.0f} % open; it never opens fully.')
        capped = bool(damper and st(damper).get('max', 100) < 90 and zone and zone.get('alert_active'))
        conf = 'medium' if capped and box else 'low'
        lead = (f'**Most likely source:** [[{box["id"]}]] terminal unit (VAV box), {box["hops"]} steps along touching ducts from here (inferred) · confidence: {conf}' if box
                else f'**Answer:** {room_txt}: warm with the demo sensors, but no terminal unit was found on the touching duct run · confidence: low')
        lines = [lead, f'**Where:** {room_txt}.', '**Why:**', *why, '**Check first:**']
        if box:
            lines.append(f'- The maximum airflow setting of [[{box["id"]}]] and its damper command against the position.')
        if air:
            lines.append(f'- Then the supply air at [[{air["anchor_element_id"]}]] (demo airflow sensor, simulated).')
        lines.append('**Limits:** no sun or window data, no verified duct connections or design airflow; all sensor values are simulated. *(mock mode: scripted, tool-grounded)*')
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
