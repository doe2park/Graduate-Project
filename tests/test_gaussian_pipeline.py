import argparse
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import get_brush
import prepare_gaussian_dataset as prep
import preview_gaussian
import run_gaussian_pipeline as pipe
import setup_gaussian_env as setup_env


def args(**overrides):
    base = dict(capture='2026-09-17', steps=None, max_splats=None, resolution=None, quick=False, mask_nadir=False,
                publish=False, yes=False, overwrite=False)
    base.update(overrides)
    return argparse.Namespace(**base)


class PresetTests(unittest.TestCase):
    def test_shipped_presets_load_and_match_published_settings(self):
        presets = pipe.load_presets()
        for name in ('2026-05-06', '2026-09-17'):
            train = presets['captures'][name]['train']
            self.assertEqual((train['steps'], train['maxSplats'], train['resolution'], train['checkpointEvery'],
                              train['refineEvery'], train['growthStop'], train['shDegree']),
                             (50000, 1000000, 768, 5000, 400, 30000, 2))
            self.assertEqual(presets['captures'][name]['mobileBudget'], 350000)
        sep = presets['captures']['2026-09-17']
        self.assertEqual((sep['centerId'], sep['radius'], sep['size'], sep['pointCount'], sep['seedUpAxis']),
                         ('pano_103114745', 60, 768, 150000, 'z'))

    def test_shipped_presets_point_at_existing_inputs(self):
        for preset in pipe.load_presets()['captures'].values():
            for rel in [preset['manifest'], preset['registration'], *preset['seedGlbs']]:
                self.assertTrue((ROOT / rel).is_file(), rel)

    def test_validation_rejects_bad_presets(self):
        good = pipe.load_presets()
        for mutate in (lambda p: p.update(schema=2),
                       lambda p: p['captures']['2026-09-17'].pop('centerId'),
                       lambda p: p['captures']['2026-09-17'].update(seedUpAxis='x'),
                       lambda p: p['captures']['2026-09-17']['train'].update(growthStop=60000),
                       lambda p: p['captures']['2026-09-17'].update(radius=-1),
                       lambda p: p['quick'].update(steps=0)):
            bad = copy.deepcopy(good)
            mutate(bad)
            with self.assertRaises(ValueError):
                pipe.validate_presets(bad)

    def test_settings_resolution(self):
        presets = pipe.load_presets()
        preset = presets['captures']['2026-09-17']
        full = pipe.build_settings(preset)
        self.assertEqual(full['train']['steps'], 50000)
        self.assertIsNone(full['prepare']['maxStations'])
        quick = pipe.build_settings(preset, presets['quick'], quick=True)
        self.assertEqual((quick['train']['steps'], quick['prepare']['maxStations']), (300, 4))
        self.assertLessEqual(quick['train']['growthStop'], quick['train']['steps'])
        short = pipe.build_settings(preset, steps=10000)
        self.assertEqual(short['train']['growthStop'], 6000)
        self.assertEqual(pipe.build_settings(preset, max_splats=500000, resolution=512)['train']['maxSplats'], 500000)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.presets = pipe.load_presets()

    def test_publish_requires_yes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(pipe.CliError, '--yes'):
                pipe.validate_args(args(publish=True), self.presets, tmp)
            pipe.validate_args(args(publish=True, yes=True), self.presets, tmp)

    def test_refuses_overwrite_without_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / '2026-09-17').mkdir()
            with self.assertRaisesRegex(pipe.CliError, '--overwrite'):
                pipe.validate_args(args(publish=True, yes=True), self.presets, tmp)
            pipe.validate_args(args(publish=True, yes=True, overwrite=True), self.presets, tmp)

    def test_published_may_folder_is_protected_by_default(self):
        with self.assertRaises(pipe.CliError):
            pipe.validate_args(args(capture='2026-05-06', publish=True, yes=True), self.presets)

    def test_other_refusals(self):
        with self.assertRaises(pipe.CliError):
            pipe.validate_args(args(capture='1999-01-01'), self.presets)
        with self.assertRaises(pipe.CliError):
            pipe.validate_args(args(publish=True, yes=True, quick=True), self.presets)
        with self.assertRaises(pipe.CliError):
            pipe.validate_args(args(overwrite=True), self.presets)
        with self.assertRaises(pipe.CliError):
            pipe.validate_args(args(steps=0), self.presets)

    def test_main_refuses_publish_without_yes_before_any_work(self):
        self.assertEqual(pipe.main(['--capture', '2026-09-17', '--publish']), 2)

    def test_dry_run_does_not_create_anything(self):
        self.assertEqual(pipe.main(['--capture', '2026-09-17', '--quick', '--dry-run']), 0)

    def test_checklist_mentions_privacy_and_alignment(self):
        preset = self.presets['captures']['2026-09-17']
        text = pipe.publish_checklist('2026-09-17', preset, False, 'project-frame-provisional')
        self.assertIn('nadir', text)
        self.assertIn('did NOT use --mask-nadir', text)
        self.assertIn('Provisional', text)
        self.assertIn('This run used --mask-nadir', pipe.publish_checklist('x', preset, True, 'geometry-registered'))


class NadirMaskTests(unittest.TestCase):
    def test_default_keeps_all_eight_faces_in_original_order(self):
        faces = prep.select_faces(False)
        self.assertEqual(len(faces), 8)
        self.assertEqual([(y, p) for _, y, p in faces], prep.FACES)

    def test_mask_drops_only_downward_faces_and_keeps_indices(self):
        faces = prep.select_faces(True)
        self.assertEqual(len(faces), 6)
        self.assertTrue(all(p > -30 for _, _, p in faces))
        self.assertEqual([k for k, _, _ in faces], [0, 1, 2, 3, 5, 7])  # file names stay stable

    def test_station_selection_cap_keeps_nearest_in_original_order(self):
        stations = [{'id': str(i), 'position': [i, 0, 0]} for i in (5, 1, 3, 2, 40)]
        picked = prep.select_stations(stations, [0, 0, 0], 10, 3)
        self.assertEqual([s['id'] for s in picked], ['1', '3', '2'])
        self.assertEqual(len(prep.select_stations(stations, [0, 0, 0], 10)), 4)
        with self.assertRaises(ValueError):
            prep.select_stations(stations, [0, 0, 0], 10, 0)


class ProvenanceTests(unittest.TestCase):
    def test_assembly_records_settings_hashes_tools_timings_and_metrics(self):
        presets = pipe.load_presets()
        preset = presets['captures']['2026-09-17']
        settings = pipe.build_settings(preset)
        report = {'trainViews': 688, 'evaluationViews': 112,
                  'stations': [{'split': 'train'}] * 86 + [{'split': 'evaluation'}] * 14}
        prov = pipe.assemble_provenance(
            capture='2026-09-17', preset=preset, settings=settings, quick=False, mask_nadir=True,
            argv=['--capture', '2026-09-17', '--mask-nadir'], input_hashes={'manifestSha256': 'ab'},
            tools={'brush': 'brush-cli 0.3.0'}, timings={'train': 2274.0}, started_at='s', ended_at='e',
            metrics={'psnr': 19.2, 'ssim': 0.8}, dataset_report=report, steps=50000)
        self.assertEqual(prov['validation']['stations'], 14)
        self.assertEqual(prov['validation']['psnr'], 19.2)
        self.assertTrue(prov['pipeline']['nadirMasked'])
        self.assertFalse(prov['pipeline']['smokeTest'])
        self.assertEqual(prov['pipeline']['settings']['train']['maxSplats'], 1000000)
        self.assertEqual(prov['pipeline']['timingsSeconds'], {'train': 2274.0})
        self.assertEqual(prov['pipeline']['tools']['brush'], 'brush-cli 0.3.0')
        self.assertIn('not controlled across captures', prov['validation']['scope'])
        json.dumps(prov)  # must serialise

    def test_eval_metric_parsing_uses_last_values_and_tolerates_absence(self):
        log = 'eval psnr: 17.5 ssim: 0.70\n\x1b[32mINFO\x1b[0m Eval | PSNR 19.25 | SSIM 0.801\n'
        self.assertEqual(pipe.parse_eval_metrics(log), {'psnr': 19.25, 'ssim': 0.801})
        self.assertEqual(pipe.parse_eval_metrics('nothing here'), {'psnr': None, 'ssim': None})


class GetBrushTests(unittest.TestCase):
    def test_os_to_asset_mapping(self):
        self.assertEqual(get_brush.target_for('Darwin', 'arm64'), ('aarch64-apple-darwin', 'tar.xz', 'brush_app'))
        self.assertEqual(get_brush.target_for('Windows', 'AMD64'), ('x86_64-pc-windows-msvc', 'zip', 'brush_app.exe'))
        self.assertEqual(get_brush.target_for('Linux', 'x86_64')[0], 'x86_64-unknown-linux-gnu')
        for system, machine in (('Darwin', 'x86_64'), ('Windows', 'ARM64'), ('Linux', 'arm64')):
            with self.assertRaises(SystemExit):
                get_brush.target_for(system, machine)

    def test_urls_are_official_release_assets(self):
        url, sha = get_brush.asset_urls('x86_64-pc-windows-msvc', 'zip')
        self.assertEqual(url, 'https://github.com/ArthurBrussee/brush/releases/download/v0.3.0/brush-app-x86_64-pc-windows-msvc.zip')
        self.assertEqual(sha, url + '.sha256')

    def test_sha_parsing_and_verification(self):
        digest = hashlib.sha256(b'abc').hexdigest()
        self.assertEqual(get_brush.parse_sha256(f'{digest}  brush.zip\n'), digest)
        self.assertEqual(get_brush.parse_sha256(f'{digest.upper()} *brush.zip'), digest)
        with self.assertRaises(ValueError):
            get_brush.parse_sha256('not a hash')
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'a'
            f.write_bytes(b'abc')
            self.assertEqual(get_brush.verify(f, digest), digest)
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                get_brush.verify(f, '0' * 64)

    def test_extraction_rejects_path_traversal(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'evil.zip'
            with zipfile.ZipFile(archive, 'w') as zf:
                zf.writestr('../escape.txt', 'x')
            with self.assertRaises(ValueError):
                get_brush.safe_extract(archive, Path(tmp) / 'out')

    def test_ensure_brush_refuses_bad_checksum_and_installs_good_one(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / 'payload.zip'
            with zipfile.ZipFile(payload, 'w') as zf:
                zf.writestr('brush-app/brush_app.exe', 'binary')
            good = hashlib.sha256(payload.read_bytes()).hexdigest()

            def make_fetch(sha):
                def fetch(url, dest):
                    Path(dest).write_text(sha) if url.endswith('.sha256') else Path(dest).write_bytes(payload.read_bytes())
                return fetch
            with self.assertRaises(ValueError):
                get_brush.ensure_brush(Path(tmp) / 'bad', 'Windows', 'AMD64', make_fetch('0' * 64))
            path = get_brush.ensure_brush(Path(tmp) / 'good', 'Windows', 'AMD64', make_fetch(good))
            self.assertEqual(path.name, 'brush_app.exe')
            self.assertEqual(get_brush.ensure_brush(Path(tmp) / 'good', 'Windows', 'AMD64', None), path)  # cached


class SetupAndPreviewTests(unittest.TestCase):
    def test_prerequisite_checks(self):
        self.assertEqual(setup_env.check_prerequisites((3, 12), 22, True), [])
        self.assertEqual(len(setup_env.check_prerequisites((3, 9), 20, False)), 3)

    def test_venv_python_paths(self):
        self.assertEqual(setup_env.venv_python('v', windows=True), Path('v/Scripts/python.exe'))
        self.assertEqual(setup_env.venv_python('v', windows=False), Path('v/bin/python'))

    def test_preview_urls_override_manifest(self):
        urls = preview_gaussian.preview_urls(Path('work/gaussian/2026-09-17/x/package/viewer.json'), 8000)
        self.assertIn('scan-compare.html?mode=splat&manifest=work%2Fgaussian%2F2026-09-17%2Fx%2Fpackage%2Fviewer.json', urls['compare'])
        self.assertTrue(urls['splat'].startswith('http://localhost:8000/scan-splat.html?manifest='))

    def test_latest_run_picks_newest_packaged(self):
        with tempfile.TemporaryDirectory() as tmp:
            for stamp, packaged in (('20260101T000000Z', True), ('20260301T000000Z', True), ('20260401T000000Z', False)):
                d = Path(tmp) / 'cap' / stamp
                (d / 'package').mkdir(parents=True)
                if packaged:
                    (d / 'package' / 'viewer.json').write_text('{}')
            self.assertEqual(preview_gaussian.latest_run('cap', tmp).name, '20260301T000000Z')
            self.assertIsNone(preview_gaussian.latest_run('none', tmp))


if __name__ == '__main__':
    unittest.main()


class WatchTests(unittest.TestCase):
    """--watch opens Brush's own live training window (brush_app --with-viewer)."""

    def test_brush_args_add_viewer_only_when_requested(self):
        import train_gaussian
        base = dict(steps=300, max_splats=1000, refine_every=400, growth_stop=0, sh_degree=1,
                    resolution=256, checkpoint_every=100)
        quiet = train_gaussian.brush_args('/b', '/d', '/o', **base)
        live = train_gaussian.brush_args('/b', '/d', '/o', viewer=True, **base)
        self.assertNotIn('--with-viewer', quiet)
        self.assertIn('--with-viewer', live)
        self.assertEqual([a for a in live if a != '--with-viewer'], quiet)

    def test_pipeline_parser_accepts_watch(self):
        ns = pipe.build_parser().parse_args(['--capture', '2026-09-17', '--watch'])
        self.assertTrue(ns.watch)
        self.assertFalse(pipe.build_parser().parse_args(['--capture', '2026-09-17']).watch)
