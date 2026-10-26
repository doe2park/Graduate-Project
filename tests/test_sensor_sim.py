"""tools/sensor_sim.py: deterministic, schema-shaped, clearly simulated demo feed (twin/sensors/FEED.md)."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import sensor_sim as S  # noqa: E402


class SensorSimTest(unittest.TestCase):
    def setUp(self):
        self.reg = json.loads((ROOT / 'twin/sensors/registry.json').read_text())
        self.t = 1793034000000  # 2026-10-26T10:00:00-07:00

    def test_deterministic_and_labelled(self):
        a, b = S.snapshot(self.reg, self.t), S.snapshot(self.reg, self.t)
        self.assertEqual(a, b)
        self.assertTrue(a['simulated'])
        self.assertEqual(len(a['observations']), len(self.reg['sensors']))
        for o in a['observations']:
            self.assertTrue(S.valid_observation(o), o)
            self.assertEqual(o['source'], 'demo-sim')
            self.assertIs(o['simulated'], True)
            unit = next(s['unit'] for s in self.reg['sensors'] if s['id'] == o['sensor_id'])
            self.assertEqual(o['unit'], unit)

    def test_patterns(self):
        by = lambda t: {o['sensor_id']: o['value'] for o in S.snapshot(self.reg, t)['observations']}
        day, night = by(self.t), by(self.t - 7.5 * 3600 * 1000)  # 02:30 local
        self.assertGreater(night['water-flow'], 0.5)
        self.assertLess(day['water-flow'], 0.2)
        self.assertGreater(day['hvac-iaq'], night['hvac-iaq'] + 200)
        self.assertEqual(day['leak-puck'], 0)

    def test_missing_is_not_zero(self):
        self.assertTrue(S.valid_observation({'sensor_id': 'x', 'ts': None, 'value': None, 'unit': 'ppm', 'quality': 'missing', 'source': 'bms'}))
        self.assertFalse(S.valid_observation({'sensor_id': 'x', 'ts': '2026-10-26T17:00:00Z', 'value': 1, 'unit': 'ppm', 'quality': 'good', 'source': 'demo-sim'}))

    def test_cli_writes_latest_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([sys.executable, str(ROOT / 'tools/sensor_sim.py'), '--at', '2026-10-26T10:00:00-07:00', '--out', d, '--history'], check=True, capture_output=True)
            snap = json.loads((Path(d) / 'latest.json').read_text())
            hist = json.loads((Path(d) / 'history' / '2026-10-26.json').read_text())
            self.assertEqual(snap['schema'], 'grimes-sensor-feed/1')
            self.assertEqual(len(hist['observations']), 24 * len(self.reg['sensors']))

    def test_needs_timezone(self):
        r = subprocess.run([sys.executable, str(ROOT / 'tools/sensor_sim.py'), '--at', '2026-10-26T10:00:00', '--out', tempfile.gettempdir()], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
