"""Ask-the-twin: element index, read-only tools, citation grounding, mock agent, live loop (fake client) and server.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_ask_twin
No network and no API key: the live loop runs against a scripted fake client.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from ask_twin import agent as A  # noqa: E402
from ask_twin import index as ix  # noqa: E402
from ask_twin import tools as T  # noqa: E402

TWIN = None


def twin():
    global TWIN
    if TWIN is None:
        TWIN = T.Twin(log=lambda *a: None)
    return TWIN


LIGHT, LEAK_PIPE, DUCT = '12442', '278123', '401233'   # recessed light under the demo leak pipe; demo airflow duct
LIGHT_POINT = [-33.05, 7.99, -17.4]


class IndexTests(unittest.TestCase):
    def test_boxes_follow_hierarchy_and_viewer_placement(self):
        gltf = {'scene': 0, 'scenes': [{'nodes': [0]}],
                'nodes': [{'scale': [2, 2, 2], 'children': [1]}, {'name': 'A', 'translation': [1, 0, 0], 'children': [2]}, {'mesh': 0}],
                'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
                'accessors': [{'min': [0, 0, 0], 'max': [1, 1, 1]}]}
        b = ix.element_boxes(gltf, {'A'})['A']
        # scene: x in [2,4], y,z in [0,2]; viewer: (-x, y, -z) + offset
        ox, oy, oz = ix.VIEWER_OFFSET
        self.assertEqual(b, [round(v, 3) for v in (-4 + ox, 0 + oy, -2 + oz, -2 + ox, 2 + oy, 0 + oz)])

    def test_unnamed_meshes_without_owner_are_skipped(self):
        gltf = {'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}], 'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
                'accessors': [{'min': [0, 0, 0], 'max': [1, 1, 1]}]}
        self.assertEqual(ix.element_boxes(gltf, {'x'}), {})

    def test_real_index_matches_sidecar_elevations(self):
        tw = twin()
        side = json.loads((ROOT / 'buildings/grimes/elements.json').read_text())['elements']
        diffs = sorted(tw.box[k][1] - v['elevation_m'] for k, v in side.items() if k in tw.box and v.get('elevation_m') is not None)
        self.assertLess(abs(diffs[len(diffs) // 2]), 0.15, 'equipment box bottoms should sit at the Revit elevation (frame check)')
        for key, L in tw.index['layers'].items():
            self.assertEqual(L['withBox'], L['sidecarElements'], key)

    def test_quality_overlay_hides_non_parts_and_files_elements_by_geometry(self):
        tw = twin()
        quality = json.loads((ROOT / 'buildings/grimes/element-quality.json').read_text())['layers']
        anno, moved = quality['duct']['hidden']['annotation'][0], quality['fixtures']['storey']['L1'][0]
        self.assertNotIn(anno, tw.box)
        self.assertEqual(tw.hidden[anno], 'annotation')
        self.assertIn('error', tw.get_element(anno))
        summary = tw.summary(moved)
        self.assertEqual(summary['level'], 'L1')
        self.assertNotEqual(summary['level_label_in_source'], 'L1')
        self.assertIn('level label disagrees', summary['model_note'])
        self.assertEqual(len(tw.box) + len(tw.hidden), sum(L['withBox'] for L in tw.index['layers'].values()))

    def test_level_of_y_uses_measured_slab_heights(self):
        from scripts.ask_twin.tools import level_of_y
        self.assertEqual([level_of_y(y) for y in (0.9, 5.2, 5.9, 9.4, 9.6, 14.6, 19.5)], ['LOWER', 'L1', 'L1', 'L2', 'L2', 'L3', 'ROOF'])

    def test_box_gap(self):
        self.assertEqual(ix.box_gap([0, 0, 0, 1, 1, 1], [0.5, 0.5, 0.5, 2, 2, 2]), 0)
        self.assertAlmostEqual(ix.box_gap([0, 0, 0, 1, 1, 1], [1, 3, 1, 2, 4, 2]), 2.0)


class ToolTests(unittest.TestCase):
    def test_elements_near_above_only_returns_only_elements_above(self):
        r = twin().elements_near(element_id=LIGHT, radius_m=2.0, above_only=True)
        self.assertGreater(r['total_found'], 0)
        top = twin().box[LIGHT][4]
        for e in r['elements']:
            self.assertEqual(e['vertical'], 'above', e)
            self.assertGreaterEqual(twin().box[e['id']][1], top - 0.02)
            self.assertLessEqual(e['horizontal_gap_m'], 2.0)

    def test_leak_pipe_is_above_the_light_with_service_hint(self):
        r = twin().elements_near(element_id=LIGHT, radius_m=2.0, above_only=True, layers=['fire'], limit=60)
        hit = next(e for e in r['elements'] if e['id'] == LEAK_PIPE)
        self.assertEqual(hit['service_hint']['service'], 'fire sprinkler piping')
        self.assertTrue(0.5 < hit['vertical_gap_m'] < 1.6)

    def test_layer_and_type_filters(self):
        r = twin().elements_near(point=LIGHT_POINT, radius_m=5, layers=['duct'], type_contains='duct')
        self.assertTrue(r['elements'] and all(e['layer'] == 'duct' for e in r['elements']))

    def test_room_is_inferred_and_labelled(self):
        r = twin().room_of(point=LIGHT_POINT)
        self.assertEqual(r['level'], 'L1')
        self.assertIn('inferred', r['basis'])
        self.assertTrue(r['ceilings_at_this_xz'], 'Level 1 ceiling slice covers this spot')

    def test_find_elements_valves_on_level(self):
        r = twin().find_elements(text='ball valve', level='L1')
        self.assertGreater(r['total_found'], 0)
        self.assertTrue(all('valve' in e['name'].lower() and e['level'] == 'L1' for e in r['elements']))

    def test_connected_run_reaches_terminal_units_and_is_labelled_inferred(self):
        r = twin().connected_run(DUCT)
        self.assertTrue(any(n['type'] == 'Terminal unit' for n in r['notable_on_run']))
        self.assertIn('Not a verified', r['evidence'])
        n = r['notable_on_run'][0]
        self.assertEqual(n['path_ids'][0], DUCT)
        self.assertEqual(n['path_ids'][-1], n['id'])

    def test_sensors_are_demo_and_simulated(self):
        s = twin().list_sensors(element_id=LIGHT, radius_m=6)
        self.assertIn('leak-alert', [x['sensor_id'] for x in s['sensors']])
        self.assertIn('DEMO', s['warning'])
        r = twin().sensor_readings('leak-alert', hours=24)
        self.assertTrue(r['simulated'])
        self.assertEqual(r['latest']['source'], 'demo-sim')
        self.assertTrue(r['alert_active'])
        self.assertIn('error', twin().sensor_readings('nope'))

    def test_run_tool_validates_and_never_raises(self):
        self.assertIn('error', T.run_tool(twin(), 'drop_table', {}))
        self.assertIn('error', T.run_tool(twin(), 'get_element', {}))
        self.assertIn('error', T.run_tool(twin(), 'get_element', {'element_id': '1', 'x': 2}))
        self.assertIn('error', T.run_tool(twin(), 'elements_near', {'point': [1, 2]}))
        self.assertIn('error', T.run_tool(twin(), 'elements_near', {'element_id': 'does-not-exist'}))
        self.assertIn('element', T.run_tool(twin(), 'get_element', {'element_id': LIGHT}))

    def test_ids_in_collects_element_and_path_ids(self):
        self.assertEqual(T.ids_in({'a': [{'id': '1'}, {'anchor_element_id': '2'}], 'path_ids': ['3', '4']}), {'1', '2', '3', '4'})

    def test_tool_schemas_are_strict_objects(self):
        for t in T.TOOL_SCHEMAS:
            self.assertEqual(t['input_schema']['type'], 'object')
            self.assertFalse(t['input_schema']['additionalProperties'])
            self.assertTrue(hasattr(twin(), t['name']))


class CitationTests(unittest.TestCase):
    def test_only_tool_returned_ids_are_verified(self):
        c = A.verify_citations(twin(), 'see [[278123]] and [[12442]] and [[999999999]] and [[278123]]', {'278123'})
        self.assertEqual([(x['id'], x['verified']) for x in c], [('278123', True), ('12442', False), ('999999999', False)])
        self.assertFalse(c[2]['known'])


class MockAgentTests(unittest.TestCase):
    def ask(self, q, eid=LIGHT, pt=None):
        evs = list(A.MockAgent(twin(), delay=0).ask(q, eid, pt))
        self.assertEqual(evs[-1]['type'], 'final')
        return evs, evs[-1]

    def test_leak_question_cites_demo_pipe_grounded(self):
        evs, f = self.ask("There's a water stain on the ceiling tile here, what is leaking?", LIGHT, LIGHT_POINT)
        self.assertTrue(f['answer'].startswith(f'**Most likely source:** [[{LEAK_PIPE}]]'))
        self.assertIn('simulated', f['answer'])
        self.assertTrue(f['citations'] and all(c['verified'] for c in f['citations']))
        self.assertIn('elements_near', [e['name'] for e in evs if e['type'] == 'tool'])
        self.assertEqual(''.join(e['text'] for e in evs if e['type'] == 'text'), f['answer'])
        self.assertEqual(f['mode'], 'mock')

    def test_valve_and_feed_and_describe(self):
        _, f = self.ask('Which valve shuts off water to this room?')
        self.assertIn('valve', f['answer'].lower())
        self.assertIn('confidence: low', f['answer'])
        _, f = self.ask('What feeds this duct?', DUCT)
        self.assertIn('Terminal unit', ' '.join(c['type'] or '' for c in f['citations']))
        _, f = self.ask('What is this?', LIGHT)
        self.assertTrue(all(c['verified'] for c in f['citations']))

    def test_four_headset_levels_are_tool_grounded(self):
        diffuser = '388279'   # Level 1 supply diffuser, anchor of the demo IAQ / comfort sensors
        evs, f = self.ask('What is this, and what room am I in?', diffuser)
        self.assertEqual([e['name'] for e in evs if e['type'] == 'tool'], ['get_element', 'room_of'])
        self.assertIn('inferred', f['answer'])
        evs, f = self.ask('What is above this ceiling tile within 2 m?', diffuser)
        self.assertEqual([e['name'] for e in evs if e['type'] == 'tool'], ['elements_near'])
        self.assertTrue(f['citations'] and all(c['verified'] for c in f['citations']))
        evs, f = self.ask('Which VAV box feeds this diffuser?', diffuser)
        run = [e for e in evs if e['type'] == 'tool' and e['name'] == 'connected_run'][0]
        self.assertEqual(run['start'], diffuser)
        lead = A.CITE_RX.search(f['answer']).group(1)
        path = next(p['ids'] for p in run['paths'] if p['to'] == lead)
        self.assertEqual((path[0], path[-1]), (diffuser, lead))   # the run the headset lights up, start -> cited box
        # the box itself (Price SDV5), not its two 'Coil Kit Supply/Return' pipe connection kits that touch it one step earlier
        self.assertEqual(lead, '400766')
        self.assertEqual(len(path), 12)   # 11 steps: diffuser, 10 duct pieces, box
        self.assertNotIn('383845', f['answer']); self.assertNotIn('383987', f['answer'])
        self.assertIn('reheat-coil pipe connection kit', T.Twin.service_hint(twin(), '383845')['service'])
        evs, f = self.ask('This room is warm from 9 to 5 every weekday. What is the likely cause, and where do I check first?', diffuser)
        names = [e['name'] for e in evs if e['type'] == 'tool']
        self.assertEqual(names[:2], ['room_of', 'connected_run'])
        self.assertIn('sensor_readings', names)
        self.assertIn('simulated', f['answer'])
        self.assertTrue(all(c['verified'] for c in f['citations']))

    def test_tool_event_visual_is_copied_from_the_tool_result(self):
        """Headset answer card graphics (twin/xr-ask.js answerVisual): structured data from the tool result, nothing added."""
        near = {'query': {'radius_m': 2.0, 'above_only': True}, 'total_found': 3, 'counts_by_layer': {'fire': 2, 'structural': 1},
                'elements': [{'id': 'p1', 'layer': 'fire', 'type': 'Pipe', 'name': 'Pipe', 'size': '3"', 'size_m': [4, .1, .1],
                              'vertical': 'above', 'vertical_gap_m': .16, 'horizontal_gap_m': 0.0, 'center_offset_m': [0, .2, 0]}]}
        v = A.tool_event('elements_near', {}, near)['visual']
        self.assertEqual((v['kind'], v['above_only'], v['total'], v['counts_by_layer']), ('near', True, 3, {'fire': 2, 'structural': 1}))
        self.assertEqual(v['items'][0], {'id': 'p1', 'label': 'sprinkler pipe', 'type': 'Pipe', 'layer': 'fire', 'size': '3"', 'size_m': [4, .1, .1],
                                         'vertical': 'above', 'vertical_gap_m': .16, 'horizontal_gap_m': 0.0})
        r = A.tool_event('room_of', {}, {'level': 'L1', 'room': 'B114A', 'confidence': 'low'})['visual']
        self.assertEqual(r, {'kind': 'room', 'room': 'B114A', 'level': 'L1', 'confidence': 'low', 'basis': 'nearby labels'})
        r2 = A.tool_event('room_of', {}, {'level': 'L1', 'room': '100', 'confidence': 'recorded on the element (design BIM)'})['visual']
        self.assertEqual((r2['confidence'], r2['basis']), ('recorded', 'element'))
        run = {'start': {'id': 'd', 'layer': 'duct', 'type': 'M-HVAC-CDFF'}, 'layer': 'duct', 'elements_reached': 150, 'types_in_run': {'Duct': 120},
               'notable_on_run': [{'id': 'v', 'layer': 'duct', 'type': 'Terminal unit', 'hops': 12, 'horizontal_gap_m': 3.4, 'vertical': 'above',
                                   'vertical_gap_m': .3, 'path_ids': ['d', 'x', 'v']}]}
        rv = A.tool_event('connected_run', {}, run)['visual']
        self.assertEqual((rv['kind'], rv['reached'], rv['start']['label']), ('run', 150, 'diffuser'))
        self.assertEqual({k: rv['notable'][0][k] for k in ('id', 'label', 'hops', 'horizontal_gap_m')}, {'id': 'v', 'label': 'VAV box', 'hops': 12, 'horizontal_gap_m': 3.4})
        self.assertEqual(A.tool_event('get_element', {}, {'element': {'id': 'e', 'layer': 'lighting', 'type': 'Light', 'level': 'L2'}})['visual']['element']['label'], 'light')
        for name, res in (('list_sensors', {'sensors': []}), ('elements_near', {'error': 'x'}), ('connected_run', {'error': 'x'})):
            self.assertNotIn('visual', A.tool_event(name, {}, res))

    def test_tool_event_paths_only_for_connected_run(self):
        self.assertNotIn('paths', A.tool_event('get_element', {}, {'element': {}}))
        ev = A.tool_event('connected_run', {}, {'start': {'id': 'a'}, 'notable_on_run': [{'id': 'c', 'path_ids': ['a', 'b', 'c']}]})
        self.assertEqual((ev['start'], ev['paths']), ('a', [{'to': 'c', 'ids': ['a', 'b', 'c']}]))
        self.assertNotIn('paths', A.tool_event('connected_run', {}, {'error': 'unknown element id x'}))

    def test_no_selection(self):
        _, f = self.ask('What is leaking?', None, None)
        self.assertIn('Select an element', f['answer'])


# ---------------- fake Anthropic client for the live loop ----------------
def _block(**kw):
    return types.SimpleNamespace(**kw)


class FakeStream:
    def __init__(self, text, blocks, stop):
        self.text, self.blocks, self.stop = text, blocks, stop

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        for ch in self.text:
            yield _block(type='content_block_delta', delta=_block(type='text_delta', text=ch))

    def get_final_message(self):
        content = ([_block(type='text', text=self.text)] if self.text else []) + self.blocks
        return _block(content=content, stop_reason=self.stop, usage=_block(input_tokens=10, output_tokens=5, cache_read_input_tokens=0))


class FakeClient:
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.beta = _block(messages=_block(stream=self._stream))

    def _stream(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=lambda o: getattr(o, '__dict__', str(o)))))
        return FakeStream(*self.script.pop(0))


class LiveAgentTests(unittest.TestCase):
    def test_tool_loop_grounding_and_request_shape(self):
        client = FakeClient([
            ('', [_block(type='tool_use', id='t1', name='elements_near', input={'element_id': LIGHT, 'radius_m': 2, 'above_only': True, 'layers': ['fire']})], 'tool_use'),
            (f'**Most likely source:** [[{LEAK_PIPE}]] sprinkler pipe. Also [[123456789]].', [], 'end_turn'),
        ])
        evs = list(A.LiveAgent(twin(), client, model='claude-sonnet-5-5').ask('leak?', LIGHT, LIGHT_POINT))
        f = evs[-1]
        self.assertEqual(f['type'], 'final')
        self.assertEqual([e['name'] for e in evs if e['type'] == 'tool'], ['elements_near'])
        cites = {c['id']: c['verified'] for c in f['citations']}
        self.assertEqual(cites, {LEAK_PIPE: True, '123456789': False})
        first, second = client.calls
        self.assertEqual(first['model'], 'claude-sonnet-5-5')
        self.assertEqual(first['fallbacks'], 'default')
        self.assertTrue(all(t['eager_input_streaming'] for t in first['tools']))
        self.assertEqual(first['system'][0]['cache_control'], {'type': 'ephemeral'})
        self.assertNotIn('thinking', first)
        self.assertNotIn('tool_choice', first)
        tool_turn = second['messages'][-1]
        self.assertEqual(tool_turn['role'], 'user')
        self.assertEqual(tool_turn['content'][0]['tool_use_id'], 't1')

    def test_refusal_and_truncation_stop_without_running_tools(self):
        client = FakeClient([('', [_block(type='tool_use', id='t1', name='get_element', input={'element_id': LIGHT})], 'max_tokens')])
        evs = list(A.LiveAgent(twin(), client).ask('x', LIGHT))
        self.assertEqual(evs[-1]['type'], 'error')
        self.assertFalse([e for e in evs if e['type'] == 'tool'])
        evs = list(A.LiveAgent(twin(), FakeClient([('', [], 'refusal')])).ask('x', LIGHT))
        self.assertEqual(evs[-1]['type'], 'error')

    def test_empty_cut_off_or_unsettled_answers_are_errors_not_finals(self):
        call = lambda i: _block(type='tool_use', id=f't{i}', name='get_element', input={'element_id': LIGHT})
        for script, word in (([('', [], 'max_tokens')], 'cut off'),
                             ([('This is a ceiling light. It is on', [], 'max_tokens')], 'cut off'),
                             ([('', [], 'end_turn')], 'no answer'),
                             ([('', [call(i)], 'tool_use') for i in range(A.MAX_ROUNDS)], 'did not settle')):
            evs = list(A.LiveAgent(twin(), FakeClient(script)).ask('x', LIGHT))
            self.assertEqual(evs[-1]['type'], 'error', word)
            self.assertIn(word, evs[-1]['message'])
            self.assertFalse([e for e in evs if e['type'] == 'final'])
        # max_tokens after a complete answer (the Evidence line is there) is still a normal final
        evs = list(A.LiveAgent(twin(), FakeClient([(f'This is a ceiling light.\nEvidence: [[{LIGHT}]]', [], 'max_tokens')])).ask('x', LIGHT))
        self.assertEqual(evs[-1]['type'], 'final')

    def test_evidence_on_the_answer_line_is_split_off(self):
        body, ids = A.split_answer(f'This is a ceiling light. Check on site. Evidence: [[{LIGHT}]]')
        self.assertEqual((body, ids), ('This is a ceiling light. Check on site.', [LIGHT]))
        tidy = A.tidy_answer(twin(), f'This is a ceiling light. Check on site. Evidence: [[{LIGHT}]]', LIGHT)
        self.assertEqual(tidy.count('Evidence:'), 1)
        self.assertTrue(tidy.splitlines()[-1].startswith('Evidence: [['))
        self.assertNotIn('Evidence', tidy.splitlines()[0])
        self.assertEqual(A.split_answer('There is evidence: none in the model.')[0], 'There is evidence: none in the model.')

    def test_wrong_typed_input_is_an_error_result_not_a_crash(self):
        from ask_twin.tools import run_tool
        for name, args in (('find_elements', {'text': 5}), ('elements_near', {'element_id': LIGHT, 'type_contains': 5})):
            self.assertIn('error', run_tool(twin(), name, args), name)
        client = FakeClient([(f'This is a ceiling light.\nEvidence: [[{LIGHT}]]', [], 'end_turn')])
        evs = list(A.LiveAgent(twin(), client).ask('x', LIGHT, history=['hello', {'q': 'a', 'a': 'b'}, 7]))
        self.assertEqual(evs[-1]['type'], 'final')
        self.assertEqual(len(client.calls[0]['messages']), 3)

    def test_a_400_on_the_retry_does_not_downgrade_the_shared_agent(self):
        class Always400:
            def __init__(self):
                self.beta = _block(messages=_block(stream=self._stream))

            def _stream(self, **kw):
                raise Rejecting400()
        import ask_twin.agent as mod
        real = mod._sdk_errors
        mod._sdk_errors = lambda: _block(AuthenticationError=KeyError, RateLimitError=IndexError, APIStatusError=Rejecting400, APIConnectionError=OSError)
        try:
            agent = A.LiveAgent(twin(), Always400())
            tools = agent.tools
            evs = list(agent.ask('x', LIGHT))
        finally:
            mod._sdk_errors = real
        self.assertEqual(evs[-1]['type'], 'error')
        self.assertTrue(agent.fallbacks)
        self.assertIs(agent.tools, tools)


class Rejecting400(Exception):
    status_code, message = 400, 'unknown field'


class LiveDowngradeTests(unittest.TestCase):
    def test_400_retries_once_without_optional_features(self):
        client = FakeClient([('**Answer:** [[%s]] light.' % LIGHT, [], 'end_turn')])
        real = client._stream
        state = {'n': 0}

        def flaky(**kw):
            state['n'] += 1
            if state['n'] == 1:
                raise Rejecting400()
            return real(**kw)
        client.beta = _block(messages=_block(stream=flaky))
        sdk = types.SimpleNamespace(AuthenticationError=A._Never, RateLimitError=A._Never, APIStatusError=Rejecting400, APIConnectionError=A._Never)
        orig = A._sdk_errors
        A._sdk_errors = lambda: sdk
        try:
            evs = list(A.LiveAgent(twin(), client).ask('what is this', LIGHT))
        finally:
            A._sdk_errors = orig
        self.assertEqual(evs[-1]['type'], 'final')
        self.assertNotIn('fallbacks', client.calls[0])
        self.assertNotIn('eager_input_streaming', client.calls[0]['tools'][0])


# ---------------- HTTP server in mock mode ----------------
class ServerTests(unittest.TestCase):
    CODE = 'TEST42'

    @classmethod
    def setUpClass(cls):
        import ask_twin_server as S
        cls.S = S
        cls.usage_tmp = tempfile.TemporaryDirectory()
        args = S.parse_args(['--mock', '--no-stt', '--port', '0', '--code', cls.CODE, '--per-minute', '100', '--usage-dir', cls.usage_tmp.name])
        app = S.build_app(args, log=lambda *a: None)
        S.Handler.app = app
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), S.Handler)
        app.port = cls.httpd.server_address[1]
        cls.base = f'http://127.0.0.1:{app.port}'
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.usage_tmp.cleanup()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def post(self, path, body, headers=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'X-Ask-Code': self.CODE, **(headers or {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_health(self):
        code, body = self.get('/api/health')
        h = json.loads(body)
        self.assertEqual((code, h['mode']), (200, 'mock'))
        self.assertGreater(h['index']['elements'], 60000)

    def test_ask_streams_events(self):
        code, body = self.post('/api/ask', {'question': 'water stain, what is leaking?', 'element_id': LIGHT, 'point': LIGHT_POINT})
        self.assertEqual(code, 200)
        evs = [json.loads(l[6:]) for l in body.split('\n\n') if l.startswith('data: ')]
        self.assertEqual(evs[-1]['type'], 'final')
        self.assertIn(LEAK_PIPE, [c['id'] for c in evs[-1]['citations'] if c['verified']])

    def test_bad_requests(self):
        self.assertEqual(self.post('/api/ask', {'question': ''})[0], 400)
        self.assertEqual(self.post('/api/ask', {'question': 'x'}, {'Origin': 'http://evil.example'})[0], 403)
        self.assertEqual(self.post('/api/transcribe', {})[0], 501)

    def test_speak_is_optional_and_validated(self):
        code, _ = self.post('/api/speak', {'text': ''})
        self.assertIn(code, (400, 501))
        self.assertEqual(self.post('/api/speak', {'text': 'x'}, {'Origin': 'http://evil.example'})[0], 403)
        h = json.loads(self.get('/api/health')[1])
        self.assertIn('tts', h)

    def test_xr_page_and_helper_are_served(self):
        self.assertEqual(self.get('/scan-xr.html')[0], 200)
        self.assertEqual(self.get('/twin/xr-ask.js')[0], 200)

    def test_static_is_read_only_and_restricted(self):
        self.assertEqual(self.get('/twin/ask-twin.js')[0], 200)
        for p in ('/.git/config', '/work/ask-twin/element-index.json', '/scripts/../.git/HEAD', '/.gitignore',
                  '/Work/ask-twin/element-index.json', '/WORK/', '/Capture-Local/x.json', '/TWIN/ask-twin.js',
                  '/docs/', '/scripts/ask_twin/', '/twin', '/thesis/draft.pdf', '/scripts/ask_twin/__pycache__/'):
            self.assertEqual(self.get(p)[0], 403, p)
        self.assertEqual(self.get('/mr/')[0], 200)   # a folder with a tracked index.html still opens

    def test_static_rule_serves_only_what_git_does_not_ignore(self):
        import ask_twin_server as S
        served = frozenset({'twin/ask-twin.js', 'mr/index.html', 'notes/new.md'})
        for p, blocked in (('/twin/ask-twin.js', False), ('/twin/ask-twin.js?v=4', False), ('/mr/', False), ('/mr', False),
                           ('/notes/new.md', False), ('/Twin/ask-twin.js', True), ('/twin/', True), ('/thesis/a.pdf', True),
                           ('/twin/%2e%2e/thesis/a.pdf', True), ('/twin/.hidden', True), ('/', True)):
            self.assertEqual(S.static_blocked(p, served), blocked, p)
        # git unavailable: the old deny-list, now case-insensitive
        for p, blocked in (('/Work/x.json', True), ('/capture-local/x', True), ('/twin/ask-twin.js', False), ('/.env', True)):
            self.assertEqual(S.static_blocked(p, None), blocked, p)
        tracked = S.served_files()
        self.assertIn('twin/ask-twin.js', tracked)
        self.assertFalse([f for f in tracked if f.startswith(('work/', 'capture-local/', 'thesis/'))])


class AudioDecodeTests(unittest.TestCase):
    def test_decode_16k_resamples_a_wav_to_mono_float(self):
        try:
            import av  # noqa: F401
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest('PyAV/numpy not installed (the ~/.venvs/ask-twin venv has them)')
        import math
        import struct
        import wave
        import ask_twin_server as S
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'tone.wav'
            with wave.open(str(f), 'wb') as w:
                w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
                w.writeframes(b''.join(struct.pack('<hh', int(8000 * math.sin(i / 20)), 0) for i in range(48000)))
            a = S.decode_16k(str(f))
        self.assertEqual(str(a.dtype), 'float32')
        self.assertAlmostEqual(len(a) / 16000, 1.0, delta=0.05)
        self.assertLess(float(abs(a).max()), 1.0)


class KeyHandlingTests(unittest.TestCase):
    def run_server(self, *args, env_extra=None):
        env = {k: v for k, v in os.environ.items() if k != 'ANTHROPIC_API_KEY'}
        env.update({'ASK_TWIN_NO_REEXEC': '1', **(env_extra or {})})
        return subprocess.run([sys.executable, str(ROOT / 'scripts' / 'ask_twin_server.py'), *args], env=env, capture_output=True, text=True, timeout=60)

    def test_no_key_fails_clearly_and_suggests_mock(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_server('--env-file', str(Path(d) / 'missing'), '--port', '0')
        self.assertEqual(r.returncode, 2)
        self.assertIn('ANTHROPIC_API_KEY is not set', r.stderr)
        self.assertIn('--mock', r.stderr)

    def test_env_file_inside_repo_is_refused(self):
        p = ROOT / 'work' / 'ask-twin' / 'test-env-inside-repo'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('ANTHROPIC_API_KEY=not-a-real-key\n')
        try:
            r = self.run_server('--env-file', str(p), '--port', '0')
        finally:
            p.unlink()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('Refusing to read an env file inside the repository', r.stderr)
        self.assertNotIn('not-a-real-key', r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()


# ---------------- Method A (public page + laptop API), voice, speech, routing ----------------
def _req(base, path, method='GET', headers=None, body=None):
    req = urllib.request.Request(base + path, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


class CorsTests(ServerTests):
    """CORS / Private Network Access: exactly https://doe2park.github.io (and the server's own origin / localhost)."""
    PUB = 'https://doe2park.github.io'

    def test_preflight_from_public_page_with_private_network(self):
        code, h, _ = _req(self.base, '/api/ask', 'OPTIONS', {'Origin': self.PUB, 'Access-Control-Request-Method': 'POST',
                                                              'Access-Control-Request-Headers': 'content-type',
                                                              'Access-Control-Request-Private-Network': 'true'})
        self.assertEqual(code, 204)
        self.assertEqual(h.get('Access-Control-Allow-Origin'), self.PUB)
        self.assertEqual(h.get('Access-Control-Allow-Private-Network'), 'true')
        self.assertIn('POST', h.get('Access-Control-Allow-Methods'))
        self.assertIn('Content-Type', h.get('Access-Control-Allow-Headers'))
        self.assertIn('X-Ask-Code', h.get('Access-Control-Allow-Headers'))
        # no PNA header unless the browser asks for it
        code, h, _ = _req(self.base, '/api/health', 'OPTIONS', {'Origin': self.PUB, 'Access-Control-Request-Method': 'GET'})
        self.assertEqual(code, 204)
        self.assertNotIn('Access-Control-Allow-Private-Network', h)

    def test_other_origins_are_refused(self):
        for o in ('https://evil.example', 'http://doe2park.github.io', 'https://doe2park.github.io.evil.example',
                  'https://evil.github.io', 'null', 'https://doe2park.github.io:8443'):
            code, h, _ = _req(self.base, '/api/ask', 'OPTIONS', {'Origin': o, 'Access-Control-Request-Method': 'POST',
                                                                  'Access-Control-Request-Private-Network': 'true'})
            self.assertEqual(code, 403, o)
            self.assertNotIn('Access-Control-Allow-Origin', h)
            self.assertNotIn('Access-Control-Allow-Private-Network', h)
            code, h, _ = _req(self.base, '/api/health', headers={'Origin': o})
            self.assertNotIn('Access-Control-Allow-Origin', h, o)
            code, _, _ = _req(self.base, '/api/ask', 'POST', {'Origin': o, 'Content-Type': 'application/json'}, b'{"question":"x"}')
            self.assertEqual(code, 403, o)
        self.assertEqual(_req(self.base, '/scan-xr.html', 'OPTIONS', {'Origin': self.PUB})[0], 404)

    def test_public_origin_can_read_api_responses(self):
        code, h, body = _req(self.base, '/api/health', headers={'Origin': self.PUB})
        self.assertEqual((code, h.get('Access-Control-Allow-Origin')), (200, self.PUB))
        self.assertIn('Origin', h.get('Vary', ''))
        code, h, body = _req(self.base, '/api/ask', 'POST', {'Origin': self.PUB, 'Content-Type': 'application/json', 'X-Ask-Code': self.CODE},
                             json.dumps({'question': 'What is above this ceiling tile?', 'element_id': '388279'}).encode())
        self.assertEqual((code, h.get('Access-Control-Allow-Origin')), (200, self.PUB))
        evs = [json.loads(l[6:]) for l in body.decode().split('\n\n') if l.startswith('data: ')]
        speak = [e for e in evs if e['type'] == 'speak']
        self.assertEqual([e['part'] for e in speak], ['lead', 'check'])
        self.assertLess(evs.index(speak[0]), len(evs) - 1)   # spoken lead arrives before the final event
        self.assertEqual(evs[-1]['spoken'], ' '.join(e['text'] for e in speak))
        # static files carry no CORS header (only the API is shared)
        self.assertNotIn('Access-Control-Allow-Origin', _req(self.base, '/twin/xr-ask.js', headers={'Origin': self.PUB})[1])

    def test_trust_page(self):
        code, h, body = _req(self.base, '/trust')
        self.assertEqual(code, 200)
        self.assertIn(b'Retry', body)



class CorsUnitTests(unittest.TestCase):
    def test_cors_ok_rules(self):
        import ask_twin_server as S
        app = S.App(None, 'mock', 'm', types.SimpleNamespace(box={}, index={'layers': []}, sensors=[]), None, 8765, lan=True)
        ok = lambda o, host='192.168.68.52:8765': app.cors_ok(o, host)   # noqa: E731
        self.assertTrue(ok('https://doe2park.github.io'))
        self.assertTrue(ok('https://192.168.68.52:8765'))          # its own origin
        self.assertFalse(ok('http://192.168.68.52:8765'))          # own host, wrong scheme
        self.assertTrue(ok('https://localhost:8765'))
        self.assertFalse(ok('https://localhost:9999'))
        self.assertFalse(ok(''))
        self.assertFalse(ok('null'))
        self.assertFalse(ok('https://doe2park.github.io/'))       # Origin never has a path; exact match only


class NoKeyNoteTests(unittest.TestCase):
    def test_auto_without_key_runs_scripted_and_says_so(self):
        import ask_twin_server as S
        saved = os.environ.pop('ANTHROPIC_API_KEY', None)
        try:
            with tempfile.TemporaryDirectory() as d:
                app = S.build_app(S.parse_args(['--auto', '--no-stt', '--no-tts', '--env-file', str(Path(d) / 'missing'), '--port', '0']), log=lambda *a: None)
                self.assertEqual(app.mode, 'mock')
                self.assertEqual(app.health()['note'], 'Live AI needs a key on the laptop; running scripted answers')
                app = S.build_app(S.parse_args(['--mock', '--no-stt', '--no-tts', '--env-file', str(Path(d) / 'missing'), '--port', '0']), log=lambda *a: None)
                self.assertEqual(app.health()['note'], S.NO_KEY_NOTE)
        finally:
            if saved is not None:
                os.environ['ANTHROPIC_API_KEY'] = saved

    def test_live_loop_says_thinking_first(self):
        script = [('**Answer:** [[12442]] is a recessed light.\n', [], 'end_turn')]
        evs = list(A.LiveAgent(twin(), FakeClient(script)).ask('What is this?', LIGHT))
        self.assertEqual((evs[0]['type'], evs[0].get('phase')), ('status', 'thinking'))
        self.assertEqual(evs[-1]['type'], 'final')


class VoiceTests(unittest.TestCase):
    LISTING = '\n'.join([
        'Albert              en_US    # Hello! My name is Albert.',
        'Daniel              en_GB    # Hello! My name is Daniel.',
        'Eddy (영어(미국))       en_US    # Hello! My name is Eddy.',
        'Samantha            en_US    # Hello! My name is Samantha.',
        'Yuna                ko_KR    # 안녕하세요.',
    ])

    def test_parse_and_fallback_to_samantha(self):
        import ask_twin_server as S
        v = S.parse_voices(self.LISTING)
        self.assertIn({'name': 'Eddy (영어(미국))', 'locale': 'en_US', 'quality': 'standard'}, v)
        best, note = S.pick_voice(v)
        self.assertEqual(best['name'], 'Samantha')
        self.assertIn('no Premium', note)

    def test_premium_then_enhanced_and_override(self):
        import ask_twin_server as S
        listing = self.LISTING + '\n' + '\n'.join([
            'Serena (Premium)    en_GB    # Hello! My name is Serena.',
            'Ava (Enhanced)      en_US    # Hello! My name is Ava.',
            'Zoe (Premium)       en_US    # Hello! My name is Zoe.',
            'Lee (Premium)       en_AU    # Hello! My name is Lee.',
            'Nathan (고품질)      en_US    # Hello! My name is Nathan.'])
        v = S.parse_voices(listing)
        self.assertEqual(S.pick_voice(v)[0]['name'], 'Zoe (Premium)')            # Premium en_US first, en_AU ignored
        no_prem = [x for x in v if x['quality'] != 'premium']
        self.assertIn(S.pick_voice(no_prem)[0]['name'], ('Ava (Enhanced)', 'Nathan (고품질)'))
        self.assertEqual(S.pick_voice(no_prem)[0]['quality'], 'enhanced')
        self.assertEqual(S.pick_voice(v, 'Daniel')[0]['name'], 'Daniel')
        self.assertEqual(S.pick_voice(v, 'serena')[0]['name'], 'Serena (Premium)')   # name before ' (' works
        best, note = S.pick_voice(v, 'Nobody')
        self.assertEqual(best['name'], 'Zoe (Premium)')
        self.assertIn('not installed', note)


class SpokenTextTests(unittest.TestCase):
    def spoken(self, q, eid):
        from ask_twin.speech import spoken_text
        f = list(A.MockAgent(twin(), delay=0).ask(q, eid))[-1]
        t = twin()
        return spoken_text(f['answer'], lambda i: t.summary(i) if i in t.box else None, eid)

    def test_feed_answer_is_short_and_plain(self):
        s = self.spoken('Which VAV box feeds this?', '388279')
        self.assertTrue(s.startswith('Most likely the VAV box'), s)
        self.assertIn('First, trace the duct from here to the VAV box', s)
        for bad in ('[[', '400766', '388279', '**', 'confidence', 'mock', '(', '·', 'Limits'):
            self.assertNotIn(bad, s)
        self.assertLessEqual(s.count('.'), 3)

    def test_leak_and_lookup(self):
        s = self.spoken("There's a water stain, what is leaking?", LIGHT)
        self.assertIn('about 1.1 metres above', s)
        self.assertNotIn('Other candidates', s)
        self.assertNotIn('simulated', s)   # evidence bullets stay on the card
        self.assertEqual(self.spoken('What is this, and what room am I in?', '388279'), 'This is an air outlet on level 1.')

    def test_streaming_parts_and_live_preamble(self):
        from ask_twin.speech import SpokenStream, with_speech
        st = SpokenStream(lambda i: {'type': 'Terminal unit', 'layer': 'duct'}, '1')
        self.assertEqual(st.feed('**Answer:** [[2]] VAV box, 3 steps from [[1]] · confidence: low'), [])   # line not complete yet
        self.assertEqual(st.feed('\n**Why:**\n- x\n'), [('lead', 'Most likely the VAV box, 3 steps from here.')])
        self.assertEqual(st.feed('**Check first:**\n- The damper of [[2]] and its airflow.\n'), [('check', 'First, check the damper of the VAV box and its airflow.')])
        evs = [{'type': 'text', 'text': 'Let me look around it.\n'}, {'type': 'tool', 'name': 'elements_near'},
               {'type': 'text', 'text': '**Answer:** [[2]] is above.\n'}, {'type': 'final', 'answer': '...'}]
        out = list(with_speech(evs, lambda i: {'type': 'Duct', 'layer': 'duct'}, '1'))
        self.assertEqual([e['text'] for e in out if e['type'] == 'speak'], ['The duct is above.'])
        self.assertEqual(out[-1]['spoken'], 'The duct is above.')


PLAIN = ('The air comes from a VAV box (a box that controls how much air goes to this area) about 3 m away, above the ceiling. '
         'The model suggests this from touching duct pieces, so check the drawings before relying on it.\nEvidence: [[400766]] [[388279]]')


class PlainAnswerTests(unittest.TestCase):
    """Live answers for non-experts: one plain 2-3 sentence paragraph, then an Evidence line with the cited ids."""

    def test_prompt_asks_for_plain_words_and_an_evidence_line(self):
        p = A.SYSTEM_PROMPT
        for must in ('AT MOST 3 short sentences', 'at most 55 words', 'first sentence answers exactly the question asked', 'in parentheses at most once',
                     'No markdown', 'no element ids', 'CAD layer or system codes', 'no "confidence: low/medium/high"',
                     'Evidence: [[id]]', 'probably', 'not read aloud', 'Write nothing before or between tool calls',
                     'call connected_run from the selected element', 'not pick a source by straight-line proximity',
                     'BEFORE the selected element', 'Never a 4th sentence'):
            self.assertIn(must, p)
        for gone in ('**Most likely source:**', '**Why:**', '**Check first:**', '**Limits:**'):
            self.assertNotIn(gone, p)

    def test_split_and_tidy_keep_ids_off_the_text(self):
        body, ids = A.split_answer(PLAIN)
        self.assertEqual(ids, ['400766', '388279'])
        self.assertNotIn('[[', body)
        self.assertEqual(A.tidy_answer(twin(), PLAIN, '388279'), PLAIN)   # already clean: unchanged
        messy = ('**Answer:** [[388279]] is a supply air vent (M-HVAC-CDFF) in the ceiling on Level 1 · confidence: low.\n'
                 'It is probably in room 120.\nEvidence: [[388279]]')
        t = A.tidy_answer(twin(), messy, '388279')
        body, ids = A.split_answer(t)
        for bad in ('**', 'Answer:', '[[', 'M-HVAC', 'confidence'):
            self.assertNotIn(bad, body)
        self.assertTrue(body.startswith('This element is a supply air vent in the ceiling on Level 1.'), body)
        self.assertEqual(ids, ['388279'])
        no_ev = A.tidy_answer(twin(), 'The air comes from [[400766]], probably.', '388279')
        self.assertEqual(no_ev, 'The air comes from the VAV box, probably.\nEvidence: [[400766]]')
        card = '**Answer:** [[388279]] x · confidence: low\n**Why:**\n- y'
        self.assertEqual(A.tidy_answer(twin(), card, '388279'), card)   # older card format (mock) left alone

    def test_live_answer_is_the_last_round_only_and_citations_are_verified(self):
        client = FakeClient([
            ('Let me look this up.', [_block(type='tool_use', id='t1', name='connected_run', input={'element_id': '388279', 'max_elements': 250})], 'tool_use'),
            (PLAIN, [], 'end_turn'),
        ])
        f = list(A.LiveAgent(twin(), client).ask('Where does the air from this vent come from?', '388279'))[-1]
        self.assertEqual(f['answer'], PLAIN)
        self.assertEqual({c['id']: c['verified'] for c in f['citations']}, {'400766': True, '388279': True})
        self.assertEqual({c['id']: c['label'] for c in f['citations']}, {'400766': 'VAV box', '388279': 'diffuser'})

    def test_spoken_text_matches_the_card_paragraph(self):
        from ask_twin.speech import plain_speech, with_speech, spoken_text
        want = ('The air comes from a VAV box (a box that controls how much air goes to this area) about 3 metres away, above the '
                'ceiling. The model suggests this from touching duct pieces, so check the drawings before relying on it.')
        self.assertEqual(plain_speech(PLAIN), want)
        self.assertEqual(spoken_text(PLAIN), want)
        evs = [{'type': 'text', 'text': 'Let me check.\n'}, {'type': 'tool', 'name': 'connected_run'},
               *[{'type': 'text', 'text': c} for c in (PLAIN[:40], PLAIN[40:150], PLAIN[150:])],
               {'type': 'final', 'answer': PLAIN}]
        out = list(with_speech(evs))
        self.assertEqual([e['text'] for e in out if e['type'] == 'speak'], [want])
        self.assertEqual(out[-1]['spoken'], want)
        for bad in ('Evidence', '[[', '400766'):
            self.assertNotIn(bad, out[-1]['spoken'])


class MockRouteTests(unittest.TestCase):
    def test_keywords_reach_the_four_scripted_answers(self):
        cases = {
                 'What is this, and what room am I in?': 'lookup', "what's this": 'lookup',
                 'What is above this ceiling tile within 2 m?': 'above', "what's over the ceiling here": 'above',
                 'Which VAV box feeds this?': 'feed', 'Where does the air come from?': 'feed', 'where does the air in this go': 'feed',
                 'Why is it so warm in here?': 'comfort', 'it is hot': 'comfort', 'why': 'comfort',
                 'What is leaking?': 'leak', 'which valve shuts this off': 'valve', 'So pipe, no, is it?': 'describe'}
        for q, want in cases.items():
            self.assertEqual(A.mock_route(q), want, q)


class TranscriptTests(unittest.TestCase):
    def test_no_speech_and_prompt_echo_are_dropped(self):
        import ask_twin_server as S
        seg = lambda t, ns=0.0, lp=-0.2: types.SimpleNamespace(text=t, no_speech_prob=ns, avg_logprob=lp)   # noqa: E731
        self.assertEqual(S.clean_transcript([seg(' Which pipe is above this tile?')]), 'Which pipe is above this tile?')
        self.assertEqual(S.clean_transcript([seg(' you', ns=0.9, lp=-1.4)]), '')
        self.assertEqual(S.clean_transcript([seg(' the duct, the diffuser, the VAV box.')]), '')   # echo of the prompt
        self.assertEqual(S.clean_transcript([seg(' What is above this ceiling tile?')]), 'What is above this ceiling tile?')
        self.assertEqual(S.clean_transcript([]), '')


# ---------------- limits: access code, rate limits, daily budget, idle shutdown ----------------
from ask_twin import limits as LIM  # noqa: E402


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class AccessCodeTests(unittest.TestCase):
    def limits(self, **kw):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return LIM.Limits('K7PX3M', LIM.Budget(Path(d.name), 1000, 50, persist=False), **kw)

    def test_generated_code_is_short_and_unambiguous(self):
        for _ in range(50):
            c = LIM.make_code()
            self.assertEqual(len(c), 6)
            self.assertFalse(set(c) & set('01OIL'))
            self.assertTrue(set(c) <= set(LIM.ALPHABET))

    def test_missing_wrong_right(self):
        lim = self.limits()
        status, body, _ = lim.admit('ask', '10.0.0.2', None)
        self.assertEqual((status, body['reason']), (401, 'code_required'))
        status, body, _ = lim.admit('ask', '10.0.0.2', 'K7PX3N')
        self.assertEqual((status, body['reason']), (401, 'code_wrong'))
        self.assertIsNone(lim.admit('ask', '10.0.0.2', 'k7px-3m'))   # case, dashes and spaces do not matter
        self.assertIsNone(lim.admit('speech', '10.0.0.2', 'K7PX3M'))
        self.assertNotIn('K7PX3M', json.dumps(lim.public()))       # health never carries the code

    def test_wrong_codes_are_rate_limited_per_ip(self):
        lim = self.limits(bad_codes_per_minute=3)
        for _ in range(3):
            self.assertEqual(lim.admit('ask', '10.0.0.3', 'NOPE00')[0], 401)
        status, body, wait = lim.admit('ask', '10.0.0.3', 'NOPE00')
        self.assertEqual((status, body['reason']), (429, 'rate_bad_code'))
        self.assertGreater(wait, 0)
        self.assertEqual(lim.admit('ask', '10.0.0.4', 'NOPE00')[0], 401)   # another client is not affected

    def test_no_code_mode(self):
        lim = LIM.Limits(None, LIM.Budget(Path('.'), 0, 0, persist=False))
        self.assertFalse(lim.code_required)
        self.assertIsNone(lim.admit('ask', '127.0.0.1', None))


class RateLimitTests(unittest.TestCase):
    def test_per_ip_window_and_recovery(self):
        clock = FakeClock()
        lim = LIM.Limits(None, LIM.Budget(Path('.'), 0, 0, persist=False), per_minute=3, clock=clock)
        for _ in range(3):
            self.assertIsNone(lim.admit('ask', '10.0.0.5'))
        status, body, wait = lim.admit('ask', '10.0.0.5')
        self.assertEqual((status, body['reason']), (429, 'rate_ip'))
        self.assertTrue(1 <= wait <= 60)
        self.assertEqual(body['retry_after_s'], wait)
        self.assertIsNone(lim.admit('ask', '10.0.0.6'))          # per client
        clock.t += 61
        self.assertIsNone(lim.admit('ask', '10.0.0.5'))          # window slid

    def test_daily_question_cap(self):
        lim = LIM.Limits(None, LIM.Budget(Path('.'), 0, 2, persist=False))
        self.assertIsNone(lim.admit('ask', 'a'))
        self.assertIsNone(lim.admit('ask', 'b'))
        status, body, wait = lim.admit('ask', 'c')
        self.assertEqual((status, body['reason']), (429, 'rate_day'))
        self.assertGreater(wait, 0)
        self.assertIsNone(lim.admit('speech', 'c'))              # speech is not a question


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.day = [__import__('datetime').date(2026, 11, 7)]

    def budget(self, tokens=1000, per_day=0):
        return LIM.Budget(self.dir, tokens, per_day, persist=True, today=lambda: self.day[0])

    def test_counts_persist_and_roll_over_by_date(self):
        b = self.budget()
        b.add_usage({'input_tokens': 100, 'output_tokens': 50, 'cache_read_input_tokens': 1001, 'cache_creation_input_tokens': 20})
        b.add_question()
        saved = json.loads((self.dir / 'usage-2026-11-07.json').read_text())
        self.assertEqual(saved['budget_tokens'], 100 + 50 + 20 + 101)   # cache reads count one tenth, rounded up
        self.assertEqual((saved['questions'], saved['cache_read_input_tokens']), (1, 1001))
        again = self.budget()                                           # restart: same day reads the file back
        self.assertEqual(again.snapshot()['budget_tokens'], 271)
        self.day[0] = __import__('datetime').date(2026, 11, 8)          # midnight: a fresh counter, old file kept
        self.assertEqual(again.snapshot()['budget_tokens'], 0)
        self.assertEqual(again.snapshot()['date'], '2026-11-08')
        again.add_question()
        self.assertTrue((self.dir / 'usage-2026-11-07.json').is_file())
        self.assertEqual(json.loads((self.dir / 'usage-2026-11-08.json').read_text())['questions'], 1)

    def test_budget_reached_refuses_without_counting(self):
        b = self.budget(tokens=300)
        lim = LIM.Limits(None, b)
        b.add_usage({'input_tokens': 250, 'output_tokens': 60})
        status, body, wait = lim.admit('ask', '10.0.0.7')
        self.assertEqual((status, body['reason']), (429, 'budget'))
        self.assertGreater(wait, 0)
        self.assertEqual(b.snapshot()['questions'], 0)
        self.assertLessEqual(b.tokens_left(), 0)

    def test_memory_only_in_mock(self):
        b = LIM.Budget(self.dir, 1000, 0, persist=False)
        b.add_question()
        b.add_usage({'input_tokens': 5})
        self.assertEqual(list(self.dir.iterdir()), [])


class LiveLimitsTests(unittest.TestCase):
    def test_usage_hook_caching_and_max_tokens(self):
        seen = []
        client = FakeClient([
            ('', [_block(type='tool_use', id='t1', name='get_element', input={'element_id': LIGHT})], 'tool_use'),
            ('**Answer:** [[%s]] light.' % LIGHT, [], 'end_turn')])
        evs = list(A.LiveAgent(twin(), client, on_usage=seen.append).ask('what is this', LIGHT))
        self.assertEqual(evs[-1]['type'], 'final')
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0]['input_tokens'], 10)
        self.assertIn('cache_creation_input_tokens', evs[-1]['usage'])
        first, second = client.calls
        self.assertEqual(first['max_tokens'], 4000)
        self.assertEqual(first['tools'][-1]['cache_control'], {'type': 'ephemeral'})
        self.assertNotIn('cache_control', first['tools'][0])
        self.assertEqual(first['system'][0]['cache_control'], {'type': 'ephemeral'})
        self.assertEqual(first['messages'][-1]['content'][-1]['cache_control'], {'type': 'ephemeral'})
        # second round: the breakpoint moved to the tool results; at most 4 breakpoints in the request
        marks = json.dumps(second).count('"cache_control"')
        self.assertLessEqual(marks, 4)
        self.assertEqual(second['messages'][-1]['content'][-1]['cache_control'], {'type': 'ephemeral'})
        self.assertNotIn('cache_control', second['messages'][0]['content'][-1])

    def test_budget_spent_stops_before_next_round(self):
        client = FakeClient([('', [_block(type='tool_use', id='t1', name='get_element', input={'element_id': LIGHT})], 'tool_use')])
        evs = list(A.LiveAgent(twin(), client, budget_left=lambda: 0).ask('what is this', LIGHT))
        self.assertEqual(evs[-1]['type'], 'error')
        self.assertIn('budget', evs[-1]['message'])
        self.assertEqual(len(client.calls), 1)


class LimitedServerTests(unittest.TestCase):
    """The HTTP paths in mock mode: 401 without / with a wrong code, 200 with it (header or ?code=), 429 past the limit."""
    @classmethod
    def setUpClass(cls):
        import ask_twin_server as S
        cls.S, cls.tmp = S, tempfile.TemporaryDirectory()
        app = S.build_app(S.parse_args(['--mock', '--no-stt', '--no-tts', '--port', '0', '--code', 'AB23CD', '--per-minute', '2',
                                        '--usage-dir', cls.tmp.name]), log=lambda *a: None)
        cls.app = app
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), type('H', (S.Handler,), {'app': app}))
        app.port = cls.httpd.server_address[1]
        cls.base = f'http://127.0.0.1:{app.port}'
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.tmp.cleanup()

    def ask(self, headers=None, query=''):
        return _req(self.base, '/api/ask' + query, 'POST', {'Content-Type': 'application/json', **(headers or {})},
                    json.dumps({'question': 'What is this?', 'element_id': LIGHT}).encode())

    def test_code_rate_limit_and_health(self):
        code, _, body = self.ask()
        self.assertEqual((code, json.loads(body)['reason']), (401, 'code_required'))
        code, _, body = self.ask({'X-Ask-Code': 'WRONG1'})
        self.assertEqual((code, json.loads(body)['reason']), (401, 'code_wrong'))
        self.assertEqual(_req(self.base, '/api/transcribe', 'POST', {'Content-Type': 'audio/webm'}, b'x' * 300)[0], 401)
        code, _, body = self.ask({'X-Ask-Code': 'ab23cd'})
        self.assertEqual(code, 200)
        self.assertIn('"type": "final"', body.decode())
        self.assertEqual(self.ask(query='?code=AB23CD')[0], 200)
        code, h, body = self.ask({'X-Ask-Code': 'AB23CD'})
        self.assertEqual((code, json.loads(body)['reason']), (429, 'rate_ip'))
        self.assertTrue(int(h['Retry-After']) > 0)
        hl = json.loads(_req(self.base, '/api/health')[2])
        self.assertTrue(hl['access']['code_required'])
        self.assertEqual(hl['usage_today']['questions'], 2)
        self.assertEqual(hl['usage_today']['budget_tokens'], 0)    # mock answers cost nothing
        self.assertEqual(hl['limits']['daily_tokens'], 2_000_000)
        self.assertNotIn('AB23CD', json.dumps(hl))
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])   # mock keeps the counter in memory

    def test_root_redirect_keeps_the_code(self):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **kw):
                return None
        try:
            urllib.request.build_opener(NoRedirect).open(self.base + '/?code=AB23CD')
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 302)
            self.assertEqual(e.headers['Location'], '/grimes-bim-viewer.html?ask=1&code=AB23CD')


class LimitArgsTests(unittest.TestCase):
    def test_flags_defaults_and_refusals(self):
        import contextlib
        import io
        import ask_twin_server as S
        a = S.parse_args([])
        self.assertEqual((a.per_minute, a.per_day, a.daily_tokens, a.max_tokens, a.idle_minutes, a.code, a.no_code),
                         (10, 300, 2_000_000, 4000, 120, None, False))
        for bad in (['--no-code', '--lan'], ['--code', 'x!'], ['--code', 'ABCD', '--no-code']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                S.parse_args(bad)

    def test_banner_urls_carry_the_code(self):
        import ask_twin_server as S
        u = S.page_urls('https', '192.168.1.20', 8765, 'AB23CD', lan=True)
        self.assertEqual(u['laptop'], 'https://192.168.1.20:8765/grimes-bim-viewer.html?ask=1&code=AB23CD')
        self.assertEqual(u['headset'], 'https://192.168.1.20:8765/mr/?ask=1&code=AB23CD')
        self.assertEqual(u['public'], 'https://doe2park.github.io/Graduate-Project/mr/?ask=1&server=https://192.168.1.20:8765&code=AB23CD')
        self.assertNotIn('code', S.page_urls('http', '127.0.0.1', 8765, None)['laptop'])

    def test_usage_dir_inside_repo_is_refused(self):
        import ask_twin_server as S
        with self.assertRaises(SystemExit):
            S.build_app(S.parse_args(['--mock', '--no-stt', '--no-tts', '--usage-dir', str(ROOT / 'work')]), log=lambda *a: None)

    def test_idle_watch_stops_the_server(self):
        import ask_twin_server as S
        stopped = threading.Event()
        lim = types.SimpleNamespace(last_question=0.0)
        t = S.idle_watch(types.SimpleNamespace(shutdown=stopped.set), lim, 0.001, log=lambda *a, **k: None, poll=0.01)
        self.assertTrue(stopped.wait(5))
        t.join(1)
