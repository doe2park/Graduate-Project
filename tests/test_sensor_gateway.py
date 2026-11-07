"""tools/sensor_gateway.py: observation validation (FEED.md rules), latest/history store, snapshot schema shape, and the
handler over plain HTTP on 127.0.0.1 with an ephemeral port (no TLS, no LAN bind, no certificate)."""
import importlib.util
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('sensor_gateway', ROOT / 'tools' / 'sensor_gateway.py')
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)

NOW = datetime(2026, 11, 7, 23, 0, 0, tzinfo=timezone.utc)
Z = lambda dt: dt.isoformat().replace('+00:00', 'Z')


def obs(**kw):
    o = {'sensor_id': 'test-phone-vib', 'ts': Z(NOW - timedelta(seconds=1)), 'value': 0.2, 'unit': 'm/s2', 'quality': 'good', 'source': 'gateway'}
    o.update(kw)
    return {k: v for k, v in o.items() if v is not ...}


class Validation(unittest.TestCase):
    def setUp(self):
        self.sensors = G.load_sensors(G.DEFAULT_REGISTRY)

    def test_registry_is_the_live_test_file(self):
        self.assertEqual(list(self.sensors), ['test-phone-vib'])
        self.assertEqual(self.sensors['test-phone-vib']['unit'], 'm/s2')
        with self.assertRaises(ValueError):   # the public demo registry has no gateway sensors
            G.load_sensors(ROOT / 'twin' / 'sensors' / 'registry.json')

    def test_accepts_valid(self):
        for o in (obs(), obs(value=0), obs(ts='2026-11-07T14:59:59-08:00'), obs(simulated=False), obs(quality='suspect', reason='low rate'),
                  obs(value=None, quality='missing', reason='no samples'), obs(value=None, quality='missing', ts=None)):
            clean, why = G.validate_observation(o, self.sensors, NOW)
            self.assertIsNone(why, o)
            self.assertEqual(clean['source'], 'gateway')

    def test_rejects(self):
        cases = {
            'unknown sensor': obs(sensor_id='fan-vibration'), 'unit': obs(unit='mm/s'), 'no tz': obs(ts='2026-11-07T23:00:00'),
            'string value': obs(value='0.2'), 'bool value': obs(value=True), 'nan': obs(value=float('nan')),
            'null not missing': obs(value=None), 'missing with value': obs(quality='missing'), 'bad quality': obs(quality='fine'),
            'simulated': obs(simulated=True), 'source': obs(source='demo-sim'), 'extra field': obs(foo=1),
            'future': obs(ts=Z(NOW + timedelta(minutes=5))), 'too old': obs(ts=Z(NOW - timedelta(days=2))), 'value without ts': obs(ts=None),
            'not an object': [1, 2]}
        for name, o in cases.items():
            clean, why = G.validate_observation(o, self.sensors, NOW)
            self.assertIsNone(clean, name)
            self.assertTrue(why, name)

    def test_store_latest_history_snapshot(self):
        st = G.Store(self.sensors, history=3)
        snap = st.snapshot(NOW)
        self.assertEqual(snap['schema'], 'grimes-sensor-feed/1')
        self.assertFalse(snap['simulated'])
        self.assertEqual(snap['observations'][0]['quality'], 'missing')   # nothing received yet: explicit missing, never 0
        self.assertIsNone(snap['observations'][0]['value'])
        acc, rej = st.add([obs(ts=Z(NOW - timedelta(seconds=4)), value=0.1), obs(ts=Z(NOW - timedelta(seconds=2)), value=0.3), obs(unit='g')], NOW)
        self.assertEqual(acc, ['test-phone-vib', 'test-phone-vib'])
        self.assertEqual(rej[0]['index'], 2)
        st.add([obs(ts=Z(NOW - timedelta(seconds=9)), value=9.9)], NOW)   # an older, late observation does not replace the latest
        self.assertEqual(st.snapshot(NOW)['observations'][0]['value'], 0.3)
        st.add([obs(ts=Z(NOW), value=0.5)], NOW)
        h = st.history('test-phone-vib')['observations']
        self.assertEqual([o['value'] for o in h], [0.3, 9.9, 0.5])   # bounded rolling history
        self.assertEqual(set(st.snapshot(NOW)), {'schema', 'generated_at', 'simulated', 'source', 'note', 'observations'})

    def test_client_and_origin_rules(self):
        for a in ('127.0.0.1', '::1', '192.168.1.5', '10.2.3.4', '172.16.0.9', '::ffff:192.168.0.2'):
            self.assertTrue(G.client_allowed(a), a)
        for a in ('8.8.8.8', '172.32.0.1', '100.64.0.1', 'fe80::1', 'nonsense'):
            self.assertFalse(G.client_allowed(a), a)
        self.assertTrue(G.private_origin('http://127.0.0.1:8000'))
        self.assertTrue(G.private_origin('https://192.168.1.20:8929'))
        self.assertFalse(G.private_origin('https://evil.example'))
        self.assertFalse(G.private_origin('https://192.168.1.20:8929/path'))


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = G.Store(G.load_sensors(G.DEFAULT_REGISTRY))
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), G.make_handler(cls.store, G._serve_quest(), lan=False, static=True, quiet=True))
        cls.base = f'http://127.0.0.1:{cls.srv.server_address[1]}'
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def req(self, path, data=None, headers=None, method=None):
        r = urllib.request.Request(self.base + path, data=data, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def post(self, body, **headers):
        h = {'Content-Type': 'application/json', **headers}
        return self.req('/api/sensors/observations', json.dumps(body).encode(), h)

    def test_post_then_read(self):
        now = datetime.now(timezone.utc)
        code, _, body = self.post({'observations': [obs(ts=Z(now), value=0.42)]})
        self.assertEqual(code, 200, body)
        self.assertEqual(json.loads(body)['accepted'], 1)
        code, h, body = self.req('/api/sensors/latest.json')
        snap = json.loads(body)
        self.assertEqual(snap['observations'][0]['value'], 0.42)
        self.assertEqual(h.get('Cache-Control'), 'no-store')
        code, _, body = self.req('/api/sensors/history.json?sensor=test-phone-vib')
        self.assertGreaterEqual(len(json.loads(body)['observations']), 1)
        self.assertEqual(self.req('/api/sensors/history.json?sensor=nope')[0], 404)

    def test_post_guards(self):
        now = Z(datetime.now(timezone.utc))
        self.assertEqual(self.post(obs(ts=now), Origin='https://evil.example')[0], 403)
        self.assertEqual(self.post(obs(ts=now), **{'Content-Type': 'text/plain'})[0], 415)
        code, _, body = self.post(obs(ts=now, unit='mm/s'))
        self.assertEqual(code, 422)
        self.assertIn('registry unit', json.loads(body)['rejected'][0]['reason'])
        self.assertEqual(self.req('/api/sensors/observations', b'{bad', {'Content-Type': 'application/json'})[0], 400)
        self.assertEqual(self.post(obs(ts=now), Origin=self.base)[0], 200, 'same origin (the /phone page) is accepted')

    def test_cors_for_reads(self):
        _, h, _ = self.req('/api/sensors/latest.json', headers={'Origin': 'https://doe2park.github.io'})
        self.assertEqual(h.get('Access-Control-Allow-Origin'), 'https://doe2park.github.io')
        _, h, _ = self.req('/api/sensors/latest.json', headers={'Origin': 'https://evil.example'})
        self.assertNotIn('Access-Control-Allow-Origin', h)
        code, h, _ = self.req('/api/sensors/latest.json', method='OPTIONS', headers={'Origin': 'http://127.0.0.1:8000', 'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Private-Network': 'true'})
        self.assertEqual(code, 204)
        self.assertEqual(h.get('Access-Control-Allow-Private-Network'), 'true')
        self.assertEqual(self.req('/api/sensors/observations', method='OPTIONS', headers={'Origin': 'https://doe2park.github.io', 'Access-Control-Request-Method': 'POST'})[0], 405)

    def test_static_and_phone(self):
        code, h, body = self.req('/phone')
        self.assertEqual(code, 200)
        self.assertIn(b'TEMPORARY TEST DEVICE', body)
        self.assertEqual(self.req('/twin/sensors/registry.live-test.json')[0], 200)
        for p in ('/tools/sensor_gateway.py', '/.git/config', '/scripts/serve_quest_https.py', '/work/quest-https/private-key.pem', '/api/x'):
            self.assertEqual(self.req(p)[0], 404, p)
        self.assertEqual(self.req('/', headers={})[0], 200)   # redirect to /phone is followed


if __name__ == '__main__':
    unittest.main()
