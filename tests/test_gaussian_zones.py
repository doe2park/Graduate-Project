import argparse
import contextlib
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import gaussian_zones as gz
import plan_gaussian_zones as plan
import prepare_gaussian_dataset as prep
import preview_gaussian
import run_gaussian_pipeline as pipe

SEP = '2026-09-17'
MANIFEST = ROOT / 'scan-assets' / 'captures' / SEP / 'panoramas' / 'manifest.json'


def real_stations():
    return json.loads(MANIFEST.read_text())['stations']


def grid_stations(w=8, h=5, step=3.0):
    """A walkable w x h grid with route neighbours along rows (boustrophedon), ids s0..sN."""
    out = []
    for r in range(h):
        for c in range(w):
            out.append({'id': f's{len(out)}', 'position': [c * step, 6.0, r * step], 'neighbors': []})
    return out


def zone_doc(**changes):
    zone = {'id': 'l1-a', 'name': 'Zone A', 'stations': ['a', 'b', 'c', 'd', 'e'], 'core': ['a', 'b', 'c', 'd'],
            'overlapMetres': 3.0, 'owner': '', 'status': 'unassigned'}
    zone.update(changes)
    return {'schema': 1, 'captures': {SEP: {'building': 'grimes', 'floor': 'L1', 'zones': [zone]}}}


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.stations = real_stations()
        self.pos = np.array([s['position'] for s in self.stations])
        self.adj = plan.build_graph(self.stations)

    def test_walk_graph_is_connected(self):
        self.assertEqual(len(plan.components(self.adj)), 1)

    def test_real_capture_zones_are_connected_partition_with_all_stations_covered(self):
        zones = plan.plan_zones(self.stations, 4, 3.0, seed=1)
        self.assertEqual(len(zones), 4)
        cores = [i for z in zones for i in z['core']]
        self.assertEqual(sorted(cores), list(range(len(self.stations))))  # every station in exactly one core
        covered = {i for z in zones for i in z['train']}
        self.assertEqual(covered, set(range(len(self.stations))))
        for z in zones:
            self.assertTrue(plan.is_connected(self.adj, z['core']))
        sizes = [len(z['core']) for z in zones]
        self.assertLessEqual(max(sizes) - min(sizes), 8)  # similar station counts

    def test_overlap_rule_adds_exactly_the_stations_within_reach(self):
        for overlap in (0.0, 3.0, 6.0):
            for z in plan.plan_zones(self.stations, 4, overlap, seed=1):
                core, train = set(z['core']), set(z['train'])
                self.assertTrue(core <= train)
                for i in range(len(self.stations)):
                    near = np.min(np.linalg.norm(self.pos[list(core)] - self.pos[i], axis=1)) <= overlap
                    self.assertEqual(i in train, near or i in core, f'station {i} overlap {overlap}')
        zero = plan.plan_zones(self.stations, 4, 0.0, seed=1)
        self.assertEqual([z['core'] for z in zero], [z['train'] for z in zero])

    def test_deterministic_for_a_seed_and_valid_for_others(self):
        a = plan.plan_zones(self.stations, 4, 3.0, seed=7)
        b = plan.plan_zones(self.stations, 4, 3.0, seed=7)
        self.assertEqual(a, b)
        for seed in (1, 2, 3):
            for z in plan.plan_zones(self.stations, 4, 3.0, seed=seed):
                self.assertTrue(plan.is_connected(self.adj, z['core']))

    def test_other_zone_counts_and_synthetic_grid(self):
        stations = grid_stations()
        for k in (1, 2, 3, 5):
            zones = plan.plan_zones(stations, k, 3.0, seed=1)
            self.assertEqual(sorted(i for z in zones for i in z['core']), list(range(len(stations))))
            adj = plan.build_graph(stations)
            self.assertTrue(all(plan.is_connected(adj, z['core']) for z in zones))
        with self.assertRaises(ValueError):
            plan.plan_zones(stations, 11, 3.0)  # fewer than 4 stations per zone
        with self.assertRaises(ValueError):
            plan.plan_zones(stations, 2, -1)

    def test_disconnected_walk_graph_is_bridged(self):
        far = [{'id': f'x{i}', 'position': [100.0 + i * 3, 6.0, 0.0], 'neighbors': []} for i in range(6)]
        near = [{'id': f'y{i}', 'position': [i * 3.0, 6.0, 0.0], 'neighbors': []} for i in range(6)]
        adj = plan.build_graph(near + far)
        self.assertEqual(len(plan.components(adj)), 1)


class EntryAndMergeTests(unittest.TestCase):
    def setUp(self):
        self.stations = real_stations()
        self.plan = plan.plan_zones(self.stations, 4, 3.0, seed=1)

    def entry(self, **kw):
        return plan.build_entry(self.stations, self.plan, 'grimes', 'L1', 'm.json', 3.0, **kw)

    def test_entry_validates_against_manifest_and_uses_floor_prefixed_ids(self):
        doc = {'schema': 1, 'captures': {SEP: self.entry()}}
        gz.validate_zones(doc, {SEP: {s['id'] for s in self.stations}})
        self.assertEqual([z['id'] for z in doc['captures'][SEP]['zones']], ['l1-a', 'l1-b', 'l1-c', 'l1-d'])
        self.assertEqual({z['status'] for z in doc['captures'][SEP]['zones']}, {'unassigned'})

    def test_second_floor_is_just_another_capture_entry(self):
        l2 = plan.build_entry(self.stations, self.plan, 'grimes', 'L2', 'm2.json', 3.0)
        doc = {'schema': 1, 'captures': {SEP: self.entry(), '2026-12-01': l2}}
        gz.validate_zones(doc)
        self.assertEqual(l2['zones'][0]['id'], 'l2-a')

    def test_merge_refuses_silent_overwrite_and_preserves_owner_status_name(self):
        doc = {'schema': 1, 'captures': {SEP: self.entry()}}
        with self.assertRaises(gz.ZoneError):
            plan.merge_into(doc, SEP, self.entry())
        doc['captures'][SEP]['zones'][1].update(owner='alice', status='claimed', name='Auditorium (likely)')
        merged = plan.merge_into(doc, SEP, self.entry(existing=doc['captures'][SEP]), replace=True)
        z = merged['captures'][SEP]['zones'][1]
        self.assertEqual((z['owner'], z['status'], z['name']), ('alice', 'claimed', 'Auditorium (likely)'))

    def test_merge_refuses_to_drop_a_claimed_zone(self):
        doc = {'schema': 1, 'captures': {SEP: self.entry()}}
        doc['captures'][SEP]['zones'][3].update(owner='bob', status='training')
        three = plan.build_entry(self.stations, plan.plan_zones(self.stations, 3, 3.0), 'grimes', 'L1', 'm.json', 3.0,
                                 existing=doc['captures'][SEP])
        with self.assertRaises(gz.ZoneError):
            plan.merge_into(doc, SEP, three, replace=True)

    def test_replace_warns_when_a_claimed_zone_changes(self):
        old = self.entry()
        old['zones'][0].update(owner='carol', status='claimed')
        new = self.entry(existing=old)
        new['zones'][0]['core'] = new['zones'][0]['core'][:-1]
        self.assertTrue(plan.warnings_for_replace(old, new))
        self.assertEqual(plan.warnings_for_replace(old, self.entry(existing=old)), [])


class SchemaTests(unittest.TestCase):
    def test_shipped_file_is_valid_for_the_real_manifest(self):
        doc = gz.load_zones()
        ids = {s['id'] for s in real_stations()}
        gz.validate_zones(doc, {SEP: ids})
        entry = doc['captures'][SEP]
        self.assertEqual((entry['building'], entry['floor'], len(entry['zones'])), ('grimes', 'L1', 4))
        self.assertEqual({i for z in entry['zones'] for i in z['core']}, ids)
        for z in entry['zones']:
            self.assertEqual((z['owner'], z['status']), ('', 'unassigned'))

    def test_accepts_minimal_valid_document(self):
        gz.validate_zones(zone_doc())

    def test_rejections(self):
        bad = [
            ({'schema': 2, 'captures': {}}, 'schema'),
            (zone_doc(id='L1 A'), 'zone id'),
            (zone_doc(status='done'), 'status'),
            (zone_doc(owner='', status='claimed'), 'owner'),
            (zone_doc(overlapMetres=-1), 'overlap'),
            (zone_doc(overlapMetres='3'), 'overlap'),
            (zone_doc(core=['a', 'zz']), 'core'),
            (zone_doc(stations=['a', 'b', 'c']), '4 stations'),
            (zone_doc(stations=['a', 'a', 'b', 'c', 'd']), 'duplicate'),
            (zone_doc(name=' '), 'name'),
        ]
        for doc, hint in bad:
            with self.subTest(hint=hint), self.assertRaises(gz.ZoneError):
                gz.validate_zones(doc)

    def test_bad_floor_capture_key_core_overlap_and_unknown_station(self):
        doc = zone_doc()
        doc['captures'][SEP]['floor'] = 'Level 2'
        with self.assertRaises(gz.ZoneError):
            gz.validate_zones(doc)
        for floor in ('L1', 'L2', 'L3', 'B1'):
            doc['captures'][SEP]['floor'] = floor
            gz.validate_zones(doc)
        doc = zone_doc()
        doc['captures']['sep-17'] = doc['captures'].pop(SEP)
        with self.assertRaises(gz.ZoneError):
            gz.validate_zones(doc)
        two = zone_doc()
        two['captures'][SEP]['zones'].append(dict(two['captures'][SEP]['zones'][0], id='l1-b'))
        with self.assertRaises(gz.ZoneError):  # same core stations in two zones
            gz.validate_zones(two)
        with self.assertRaises(gz.ZoneError):
            gz.validate_zones(zone_doc(), {SEP: {'a', 'b'}})

    def test_station_list_parsing(self):
        self.assertEqual(gz.parse_station_list('a, b,c'), ['a', 'b', 'c'])
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'ids.txt'
            f.write_text('a\nb # note\n\nc,d\n')
            self.assertEqual(gz.parse_station_list(f'@{f}'), ['a', 'b', 'c', 'd'])
        for bad in ('', ' , ', 'a,a'):
            with self.assertRaises(gz.ZoneError):
                gz.parse_station_list(bad)

    def test_zone_geometry(self):
        stations = real_stations()
        zone = gz.get_zone(gz.load_zones(), SEP, 'l1-c')
        g = gz.zone_geometry(zone, stations)
        self.assertIn(g['centerId'], zone['core'])
        self.assertEqual(len(g['corePositions']), len(zone['core']))
        for axis in range(3):
            self.assertLessEqual(g['coreBounds']['min'][axis], g['coreBounds']['max'][axis])
            self.assertLessEqual(g['bounds']['min'][axis], g['coreBounds']['min'][axis])
            self.assertGreaterEqual(g['bounds']['max'][axis], g['coreBounds']['max'][axis])
        with self.assertRaises(gz.ZoneError):
            gz.zone_geometry(dict(zone, stations=['nope'] + zone['stations']), stations)


class PlannerCliTests(unittest.TestCase):
    def run_cli(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = plan.main(['--capture', SEP, '--no-map', *extra])
        return code, out.getvalue(), err.getvalue()

    def test_writes_then_refuses_then_replace_keeps_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            zf = Path(tmp) / 'zones.json'
            code, out, _ = self.run_cli('--zones-file', str(zf))
            self.assertEqual(code, 0)
            doc = json.loads(zf.read_text())
            self.assertEqual(len(doc['captures'][SEP]['zones']), 4)
            code, _, err = self.run_cli('--zones-file', str(zf))
            self.assertEqual(code, 2)
            self.assertIn('--replace', err)
            doc['captures'][SEP]['zones'][3].update(owner='dana', status='claimed')
            zf.write_text(json.dumps(doc))
            self.assertEqual(self.run_cli('--zones-file', str(zf), '--replace')[0], 0)
            self.assertEqual(json.loads(zf.read_text())['captures'][SEP]['zones'][3]['owner'], 'dana')
            self.assertEqual(self.run_cli('--zones-file', str(zf), '--replace', '--zones', '3')[0], 2)  # would drop claimed zone

    def test_dry_run_writes_nothing_and_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            zf = Path(tmp) / 'zones.json'
            code, out1, _ = self.run_cli('--zones-file', str(zf), '--dry-run', '--seed', '5')
            self.assertEqual(code, 0)
            self.assertFalse(zf.exists())
            self.assertEqual(out1, self.run_cli('--zones-file', str(zf), '--dry-run', '--seed', '5')[1])

    def test_new_floor_capture_uses_its_own_manifest_and_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            stations = [dict(s, neighbors=[]) for s in grid_stations(8, 4)]
            manifest = Path(tmp) / 'manifest.json'
            manifest.write_text(json.dumps({'building': 'Grimes', 'level': 'B1', 'stations': stations}))
            zf = Path(tmp) / 'zones.json'
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = plan.main(['--capture', '2026-12-01', '--manifest', str(manifest), '--zones', '2', '--no-map',
                                  '--zones-file', str(zf)])
            self.assertEqual(code, 0, err.getvalue())
            entry = json.loads(zf.read_text())['captures']['2026-12-01']
            self.assertEqual((entry['floor'], entry['building']), ('B1', 'grimes'))
            self.assertEqual([z['id'] for z in entry['zones']], ['b1-a', 'b1-b'])

    def test_map_png_is_small(self):
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest('matplotlib not installed')
        stations = real_stations()
        entry = plan.build_entry(stations, plan.plan_zones(stations, 4, 3.0), 'grimes', 'L1', 'm.json', 3.0)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'sub' / 'zones.png'
            size = plan.render_map(SEP, entry, stations, target)
            self.assertTrue(target.is_file())
            self.assertEqual(size, target.stat().st_size)
            self.assertLess(size, 300_000)
            self.assertEqual(target.read_bytes()[:4], b'\x89PNG')


class PrepareStationsTests(unittest.TestCase):
    def stations(self):
        return [{'id': f's{i}', 'position': [i, 0, 0]} for i in range(6)]

    def test_select_by_ids_keeps_manifest_order_and_rejects_unknown(self):
        picked = prep.select_by_ids(self.stations(), ['s4', 's1', 's2'])
        self.assertEqual([s['id'] for s in picked], ['s1', 's2', 's4'])
        with self.assertRaises(ValueError):
            prep.select_by_ids(self.stations(), ['s1', 'nope'])
        with self.assertRaises(ValueError):
            prep.select_by_ids(self.stations(), ['s1', 's1'])
        self.assertEqual([s['id'] for s in prep.select_by_ids(self.stations(), ['s1', 's2', 's4'], 2, [4, 0, 0])], ['s2', 's4'])

    def test_build_with_explicit_stations_records_provenance(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            stations = []
            for i in range(6):
                f = tmp / f'{i}.jpg'
                Image.new('RGB', (128, 64), (i * 30, 10, 10)).save(f)
                stations.append({'id': f's{i}', 'file': f.name, 'sha256': hashlib.sha256(f.read_bytes()).hexdigest(),
                                 'position': [float(i), 6.0, 0.0], 'e57Quaternion': [0, 0, 0.7071067811865476, 0.7071067811865476],
                                 'neighbors': []})
            (tmp / 'manifest.json').write_text(json.dumps({'stations': stations}))
            with contextlib.redirect_stdout(io.StringIO()):
                report = prep.build(tmp / 'manifest.json', tmp / 'ds', 's2', 1.0, size=64, station_ids=['s5', 's1', 's2', 's3', 's4'])
            self.assertEqual([s['id'] for s in report['stations']], ['s1', 's2', 's3', 's4', 's5'])  # radius 1 would give 3
            self.assertEqual(report['stationSelection'], 'explicit-station-list')
            self.assertEqual(report['requestedStationIds'], ['s5', 's1', 's2', 's3', 's4'])
            with contextlib.redirect_stdout(io.StringIO()):
                default = prep.build(tmp / 'manifest.json', tmp / 'ds2', 's2', 10.0, size=64)
            self.assertEqual((default['stationSelection'], default['requestedStationIds']), ('radius-around-center', None))

    def test_cli_requires_center_or_stations(self):
        import subprocess
        r = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'prepare_gaussian_dataset.py'), '--manifest', 'm', '--output', 'o'],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('--center-id', r.stderr)


class PipelineZoneCliTests(unittest.TestCase):
    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = pipe.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_parser_accepts_zone_flags(self):
        p = pipe.build_parser()
        ns = p.parse_args(['--capture', SEP, '--zone', 'l1-a'])
        self.assertEqual((ns.zone, ns.all_zones, ns.list_zones), ('l1-a', False, False))
        self.assertTrue(p.parse_args(['--capture', SEP, '--all-zones']).all_zones)
        self.assertTrue(p.parse_args(['--list-zones']).list_zones)
        self.assertIsNone(p.parse_args(['--capture', SEP]).zone)

    def test_list_zones_prints_every_zone_and_needs_no_capture(self):
        code, out, _ = self.call('--capture', SEP, '--list-zones')
        self.assertEqual(code, 0)
        for zid in ('l1-a', 'l1-b', 'l1-c', 'l1-d'):
            self.assertIn(zid, out)
        self.assertIn('unassigned', out)
        self.assertEqual(self.call('--list-zones')[0], 0)
        self.assertEqual(self.call('--capture', '2020-01-01', '--list-zones')[0], 2)

    def test_conflicting_or_unknown_zone_arguments_are_refused(self):
        self.assertEqual(self.call('--capture', SEP, '--zone', 'l1-a', '--all-zones')[0], 2)
        code, _, err = self.call('--capture', SEP, '--zone', 'nope', '--dry-run')
        self.assertEqual(code, 2)
        self.assertIn('l1-a', err)
        self.assertEqual(self.call('--capture', SEP, '--all-zones', '--resume', 'x')[0], 2)
        self.assertEqual(self.call('--capture', '2026-05-06', '--zone', 'l1-a', '--dry-run')[0], 2)  # May has no zones
        self.assertEqual(self.call('--dry-run')[0], 2)  # capture required
        self.assertEqual(self.call('--capture', SEP, '--zone', 'l1-a', '--publish')[0], 2)  # needs --yes

    def test_zone_dry_run_resolves_stations_and_output_paths(self):
        code, out, _ = self.call('--capture', SEP, '--zone', 'l1-c', '--dry-run')
        self.assertEqual(code, 0)
        info = json.loads(out)['zones']
        self.assertEqual(len(info), 1)
        zone = gz.get_zone(gz.load_zones(), SEP, 'l1-c')
        self.assertEqual(info[0]['settings']['prepare']['stations'], zone['stations'])
        self.assertTrue(info[0]['outputRoot'].endswith('work/gaussian/2026-09-17/l1-c'))
        self.assertTrue(info[0]['publishTo'].endswith('scan-assets/gaussian/2026-09-17/zones/l1-c'))
        self.assertIn(info[0]['centerId'], zone['core'])

    def test_all_zones_dry_run_lists_each_zone(self):
        code, out, _ = self.call('--capture', SEP, '--all-zones', '--dry-run', '--mask-nadir')
        self.assertEqual(code, 0)
        zones = json.loads(out)['zones']
        self.assertEqual([z['zone'] for z in zones], ['l1-a', 'l1-b', 'l1-c', 'l1-d'])
        self.assertTrue(all(z['settings']['maskNadir'] for z in zones))

    def test_plain_capture_dry_run_is_unchanged(self):
        code, out, _ = self.call('--capture', SEP, '--quick', '--dry-run')
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIn('settings', data)
        self.assertNotIn('stations', data['settings']['prepare'])

    def test_publish_target_paths(self):
        self.assertEqual(pipe.publish_target('/p', SEP), Path('/p') / SEP)
        self.assertEqual(pipe.publish_target('/p', SEP, 'l1-a'), Path('/p') / SEP / 'zones' / 'l1-a')

    def test_publish_refusal_checks_each_zone_target(self):
        presets = pipe.load_presets()
        doc = gz.load_zones()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / SEP / 'zones' / 'l1-b').mkdir(parents=True)
            ns = argparse.Namespace(capture=SEP, zone=None, all_zones=True, list_zones=False, steps=None, max_splats=None,
                                    resolution=None, quick=False, mask_nadir=False, publish=True, yes=True, overwrite=False, resume=None)
            with self.assertRaises(pipe.CliError):
                pipe.validate_args(ns, presets, tmp, doc)
            ns.overwrite = True
            pipe.validate_args(ns, presets, tmp, doc)
            ns.overwrite, ns.zone, ns.all_zones = False, 'l1-a', False
            pipe.validate_args(ns, presets, tmp, doc)  # l1-a not yet published

    def test_checklist_names_zone_destination(self):
        preset = pipe.load_presets()['captures'][SEP]
        text = pipe.publish_checklist(SEP, preset, True, 'x', zone='l1-a')
        self.assertIn(f'scan-assets/gaussian/{SEP}/zones/l1-a/', text)
        self.assertIn('zones/index.json', text)


class PipelineZoneHelperTests(unittest.TestCase):
    def setUp(self):
        self.presets = pipe.load_presets()
        self.preset = self.presets['captures'][SEP]
        self.doc = gz.load_zones()
        self.zone = dict(gz.get_zone(self.doc, SEP, 'l1-c'), floor='L1')
        self.geometry = gz.zone_geometry(self.zone, real_stations())
        self.geometry['floor'] = 'L1'
        self.base = pipe.build_settings(self.preset, self.presets['quick'])

    def test_zone_settings_train_exactly_the_zone_and_record_bounds(self):
        s = pipe.zone_settings(self.base, self.zone, self.geometry, self.presets['quick'], False)
        self.assertEqual(s['prepare']['stations'], self.zone['stations'])
        self.assertEqual(s['prepare']['centerId'], self.geometry['centerId'])
        self.assertEqual(s['zone']['core'], self.zone['core'])
        self.assertEqual(s['zone']['bounds'], self.geometry['bounds'])
        self.assertNotIn('stations', self.base['prepare'])  # base settings untouched

    def test_publish_writes_zone_folder_and_merges_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pkg = tmp / 'pkg'
            pkg.mkdir()
            (pkg / 'trained.ksplat').write_bytes(b'k')
            (pkg / 'mobile.ply').write_bytes(b'p')
            (pkg / 'viewer.json').write_text(json.dumps({'file': 'trained.ksplat', 'mobileFile': 'mobile.ply', 'splatCount': 9}))
            root = tmp / 'gaussian'
            dest = pipe.publish(pkg, SEP, self.preset, root, False, True, False, zone=self.zone, geometry=self.geometry)
            self.assertEqual(dest, root / SEP / 'zones' / 'l1-c')
            self.assertTrue((dest / 'viewer.json').is_file() and (dest / 'trained.ksplat').is_file())
            index = json.loads((root / SEP / 'zones' / 'index.json').read_text())
            self.assertEqual([z['id'] for z in index['zones']], ['l1-c'])
            entry = index['zones'][0]
            self.assertEqual(entry['manifest'], 'l1-c/viewer.json')
            self.assertEqual(entry['coreBounds'], self.geometry['coreBounds'])
            self.assertEqual(index['floor'], 'L1')
            with self.assertRaises(pipe.CliError):
                pipe.publish(pkg, SEP, self.preset, root, False, True, False, zone=self.zone, geometry=self.geometry)
            other = dict(gz.get_zone(self.doc, SEP, 'l1-a'), floor='L1')
            pipe.publish(pkg, SEP, self.preset, root, False, True, False, zone=other,
                         geometry=dict(gz.zone_geometry(other, real_stations()), floor='L1'))
            index = json.loads((root / SEP / 'zones' / 'index.json').read_text())
            self.assertEqual([z['id'] for z in index['zones']], ['l1-a', 'l1-c'])
            pipe.publish(pkg, SEP, self.preset, root, True, True, False, zone=self.zone, geometry=self.geometry)
            self.assertEqual(len(json.loads((root / SEP / 'zones' / 'index.json').read_text())['zones']), 2)

    def test_find_run_resumes_unfinished_and_skips_finished_runs_with_same_settings(self):
        settings = pipe.zone_settings(self.base, self.zone, self.geometry, self.presets['quick'], False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(pipe.find_run(root, SEP, 'l1-c', settings), (None, False))
            old = root / SEP / 'l1-c' / '20260101T000000Z'
            old.mkdir(parents=True)
            (old / 'run.json').write_text(json.dumps({'settings': settings, 'stages': {'prepare': {'status': 'done'}}}))
            self.assertEqual(pipe.find_run(root, SEP, 'l1-c', settings), (old, False))
            new = root / SEP / 'l1-c' / '20260201T000000Z'
            new.mkdir()
            (new / 'run.json').write_text(json.dumps({'settings': settings, 'stages': {'package': {'status': 'done'}}}))
            self.assertEqual(pipe.find_run(root, SEP, 'l1-c', settings), (new, True))
            changed = copy.deepcopy(settings)
            changed['train']['steps'] = 10
            self.assertEqual(pipe.find_run(root, SEP, 'l1-c', changed), (None, False))

    def test_timing_table_reports_minutes_per_zone(self):
        text = pipe.format_timing_table([('l1-a', 'done', {'prepare': 60.0, 'train': 1800.0}), ('l1-b', 'skipped', {})])
        self.assertIn('l1-a', text)
        self.assertIn('30.0', text)
        self.assertIn('31.0', text)
        self.assertIn('skipped', text)

    def test_zone_run_dir_and_preview_latest_run(self):
        self.assertEqual(pipe.zone_run_dir('/w', SEP, 'l1-a'), Path('/w') / SEP / 'l1-a')
        self.assertEqual(pipe.zone_run_dir('/w', SEP), Path('/w') / SEP)
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / SEP / 'l1-a' / '20260101T000000Z' / 'package'
            d.mkdir(parents=True)
            (d / 'viewer.json').write_text('{}')
            self.assertEqual(preview_gaussian.latest_run(SEP, tmp, zone='l1-a').name, '20260101T000000Z')
            self.assertIsNone(preview_gaussian.latest_run(SEP, tmp))  # zone runs are not capture runs


if __name__ == '__main__':
    unittest.main()
