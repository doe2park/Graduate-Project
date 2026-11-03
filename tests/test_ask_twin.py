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
        diffs = sorted(tw.box[k][1] - v['elevation_m'] for k, v in side.items() if v.get('elevation_m') is not None)
        self.assertLess(abs(diffs[len(diffs) // 2]), 0.15, 'equipment box bottoms should sit at the Revit elevation (frame check)')
        for key, L in tw.index['layers'].items():
            self.assertEqual(L['withBox'], L['sidecarElements'], key)

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
    @classmethod
    def setUpClass(cls):
        import ask_twin_server as S
        cls.S = S
        args = S.parse_args(['--mock', '--no-stt', '--port', '0'])
        app = S.build_app(args, log=lambda *a: None)
        S.Handler.app = app
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), S.Handler)
        app.port = cls.httpd.server_address[1]
        cls.base = f'http://127.0.0.1:{app.port}'
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def post(self, path, body, headers=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', **(headers or {})})
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

    def test_static_is_read_only_and_restricted(self):
        self.assertEqual(self.get('/twin/ask-twin.js')[0], 200)
        for p in ('/.git/config', '/work/ask-twin/element-index.json', '/scripts/../.git/HEAD', '/.gitignore'):
            self.assertEqual(self.get(p)[0], 403, p)


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
