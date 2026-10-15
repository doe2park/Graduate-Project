"""Registration workbench maths (Python mirror). Synthetic data only; no real landmarks are claimed."""
import importlib.util, json, math, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('registration_fit', ROOT/'scripts/registration_fit.py')
rf = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(rf)
FIXTURE = ROOT/'tests/fixtures/registration-pairs.fixture.json'


def transform(yaw_deg, t, p):
    a = math.radians(yaw_deg); c, s = math.cos(a), math.sin(a)
    return [c*p[0]+s*p[2]+t[0], p[1]+t[1], -s*p[0]+c*p[2]+t[2]]


class RigidFit(unittest.TestCase):
    def test_exact_recovery_of_known_yaw_and_translation(self):
        pts = [[0, 4.5, 0], [10, 4.5, 2], [3, 8, 15], [20, 5, 9], [7, 6, 30]]
        pairs = [{'scan': p, 'bim': transform(37.5, [-35, .6, -25], p)} for p in pts]
        fit = rf.fit_yaw_translation(pairs)
        self.assertAlmostEqual(fit['rotationYDegrees'], 37.5, places=9)
        for a, b in zip(fit['translation'], [-35, .6, -25]): self.assertAlmostEqual(a, b, places=9)
        self.assertLess(max(fit['residualsMetres']), 1e-9)

    def test_noisy_fixture_recovers_truth_after_ransac(self):
        d = json.loads(FIXTURE.read_text())
        result = rf.solve(d)
        self.assertEqual(result['ransac']['outlierIds'], ['f7'])
        self.assertAlmostEqual(result['rotationYDegrees'], d['truth']['rotationYDegrees'], delta=0.05)
        for a, b in zip(result['translation'], d['truth']['translation']): self.assertAlmostEqual(a, b, delta=0.03)
        self.assertLess(result['fit']['rmsMetres'], 0.03)
        self.assertLess(result['checks']['maxMetres'], 0.05)

    def test_without_ransac_outlier_corrupts_fit_and_is_visible_in_leave_one_out(self):
        d = json.loads(FIXTURE.read_text()); d['ransac'] = {'enabled': False}
        result = rf.solve(d)
        self.assertGreater(result['fit']['maxMetres'], 0.3)
        loo = {e['id']: e['errorMetres'] for e in result['leaveOneOut']['errors']}
        self.assertEqual(max(loo, key=loo.get), 'f7')

    def test_leave_one_out_is_independent_of_left_out_pair(self):
        pts = [[0, 4.5, 0], [10, 4.5, 2], [3, 8, 15], [20, 5, 9]]
        pairs = [{'id': str(i), 'scan': p, 'bim': transform(5, [1, 2, 3], p)} for i, p in enumerate(pts)]
        pairs[2]['bim'] = [pairs[2]['bim'][0]+1.0, pairs[2]['bim'][1], pairs[2]['bim'][2]]
        loo = rf.leave_one_out(pairs)
        errs = {e['id']: e['errorMetres'] for e in loo['errors']}
        # the left-out bad pair is predicted by a fit that never saw it: error ~= its 1 m perturbation
        self.assertAlmostEqual(errs['2'], 1.0, delta=0.15)

    def test_degenerate_inputs_rejected(self):
        with self.assertRaises(ValueError): rf.fit_yaw_translation([{'scan': [0, 0, 0], 'bim': [0, 0, 0]}])
        same = [{'scan': [1, 0, 1], 'bim': [2, 0, 2]}]*3
        with self.assertRaises(ValueError): rf.fit_yaw_translation(same)


class Heading(unittest.TestCase):
    def test_heading_solve_recovers_offset(self):
        d = json.loads(FIXTURE.read_text()); obs = d['headingObservations'][0]
        reg = {'rotationYDegrees': d['truth']['rotationYDegrees'], 'translation': d['truth']['translation']}
        h = rf.solve_heading(obs, reg)
        self.assertAlmostEqual(h['headingOffsetDegrees'], obs['trueHeadingOffsetDegrees'], places=4)
        self.assertLess(max(h['residualsDegrees']), 1e-4)  # fixture targets rounded to 1 micrometre

    def test_heading_needs_two_observations(self):
        d = json.loads(FIXTURE.read_text()); obs = dict(d['headingObservations'][0])
        obs['photoDirections'] = obs['photoDirections'][:1]; obs['bimTargets'] = obs['bimTargets'][:1]
        with self.assertRaises(ValueError): rf.solve_heading(obs, {'rotationYDegrees': 0, 'translation': [0, 0, 0]})


class ExportAndSafety(unittest.TestCase):
    def test_export_schema_and_honest_status(self):
        d = json.loads(FIXTURE.read_text()); out = rf.build_export(d, rf.solve(d), created='2026-10-14T00:00:00Z')
        for key in ['schema', 'capture', 'rotationYDegrees', 'translation', 'scale', 'status', 'method', 'inputs', 'fit', 'leaveOneOut', 'checks', 'stationHeadingOffsetsDegrees', 'scope']:
            self.assertIn(key, out)
        self.assertEqual(out['schema'], 'grimes-registration-candidate/1')
        self.assertEqual(out['scale'], 1)
        self.assertEqual(out['status'], 'landmark-fit-unsurveyed')
        self.assertRegex(out['scope'], 'not surveyed')
        self.assertEqual(len(out['inputs']['pairsSha256']), 64)
        self.assertIn('pano_A', out['stationHeadingOffsetsDegrees'])

    def test_manual_offsets_recorded_separately_and_picks_win(self):
        d = json.loads(FIXTURE.read_text()); d['manualHeadingOffsetsDegrees'] = {'pano_B': -3.0, 'pano_A': 99.0}
        out = rf.build_export(d, rf.solve(d))
        self.assertEqual(out['manualHeadingOffsetsDegrees'], {'pano_B': -3.0, 'pano_A': 99.0})
        self.assertEqual(out['stationHeadingOffsetsDegrees']['pano_B'], -3.0)
        self.assertAlmostEqual(out['stationHeadingOffsetsDegrees']['pano_A'], 2.5, delta=0.05)  # solved with the fitted (not true) transform
        d['manualHeadingOffsetsDegrees'] = {'x': 400}
        with self.assertRaises(ValueError): rf.build_export(d, rf.solve(d))

    def test_surveyed_status_only_when_every_check_is_surveyed(self):
        d = json.loads(FIXTURE.read_text())
        for p in d['pairs']:
            if p['role'] == 'check': p['surveyed'] = True
        self.assertEqual(rf.build_export(d, rf.solve(d))['status'], 'landmark-fit-surveyed-checks')
        d['pairs'][-1]['surveyed'] = False
        self.assertEqual(rf.build_export(d, rf.solve(d))['status'], 'landmark-fit-unsurveyed')

    def test_checks_never_reuse_fit_points_and_need_four_fit_pairs(self):
        d = json.loads(FIXTURE.read_text())
        d['pairs'][-1]['scan'] = d['pairs'][0]['scan']
        with self.assertRaises(ValueError): rf.solve(d)
        d = json.loads(FIXTURE.read_text()); d['pairs'] = [p for p in d['pairs'] if p['id'] in ('f1', 'f2', 'f3', 'c1')]
        with self.assertRaises(ValueError): rf.solve(d)
        d = json.loads(FIXTURE.read_text()); d['pairs'] = [p for p in d['pairs'] if p['role'] == 'fit']
        with self.assertRaises(ValueError): rf.solve(d)

    def test_refuses_to_overwrite_accepted_or_existing_files(self):
        for protected in [ROOT/'alignment-analysis/accepted-registration.json', ROOT/'scan-assets/captures/2026-09-17/registration.json']:
            with self.assertRaises(ValueError): rf.check_output_path(protected)
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp)/'x.json'; existing.write_text('{}')
            with self.assertRaises(FileExistsError): rf.check_output_path(existing)
            rf.check_output_path(Path(tmp)/'new.json')

    def test_cli_writes_new_file_and_refuses_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'candidate.json'
            ok = subprocess.run([sys.executable, str(ROOT/'scripts/registration_fit.py'), 'fit', str(FIXTURE), '--output', str(out)], capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(json.loads(out.read_text())['method']['ransac']['outlierIds'], ['f7'])
            bad = subprocess.run([sys.executable, str(ROOT/'scripts/registration_fit.py'), 'fit', str(FIXTURE), '--output', str(ROOT/'alignment-analysis/accepted-registration.json')], capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)


if __name__ == '__main__':
    unittest.main()
