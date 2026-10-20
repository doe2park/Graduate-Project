import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import publish_local_zone as plz

CAP, ZONE = '2026-10-18', 'l1-c'
PRESETS = {'captures': {CAP: {'building': 'grimes', 'registration': 'none.json', 'notes': 'Local.'},
                        '2026-10-18-L3': {'building': 'grimes', 'registration': 'none.json', 'notes': 'SUPERSEDED 2026-10-20: x'}}}
ZONE_CTX = ({'id': ZONE, 'name': 'Zone C', 'stations': ['a', 'b'], 'core': ['a'], 'floor': 'L1'},
            {'bounds': [0, 1], 'coreBounds': [0, 1], 'corePositions': [[0, 0, 0]], 'floor': 'L1'})


def loader(args, presets, zone_id):
    return ZONE_CTX


def make_run(work, stamp, status='done', argv=('--mask-nadir',), zone=ZONE, mask=True):
    folder = work / CAP / ZONE / stamp
    (folder / 'package').mkdir(parents=True)
    stages = {s: {'status': status} for s in plz.STAGES}
    (folder / 'run.json').write_text(json.dumps({'stages': stages, 'capture': CAP, 'argv': list(argv),
                                                 'settings': {'maskNadir': mask, 'zone': {'id': zone}}}))
    (folder / 'package' / 'viewer.json').write_text(json.dumps({'file': 'a.ksplat', 'mobileFile': 'm.ksplat', 'splatCount': 5}))
    (folder / 'package' / 'a.ksplat').write_bytes(b'a')
    (folder / 'package' / 'm.ksplat').write_bytes(b'm')
    return folder


class PublishLocalZoneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.work, self.pub, self.caps = t / 'work', t / 'pub', t / 'caps'
        (self.caps / CAP).mkdir(parents=True)
        (self.caps / CAP / 'registration.json').write_text(json.dumps({'status': 'project-frame-provisional'}))

    def tearDown(self):
        self.tmp.cleanup()

    def go(self, **kw):
        return plz.publish_zone(CAP, ZONE, presets=PRESETS, output_root=self.work, publish_root=self.pub,
                                captures_root=self.caps, zone_loader=loader, **kw)

    def test_picks_newest_finished_non_quick_run(self):
        make_run(self.work, '20261019T000000Z')
        good = make_run(self.work, '20261020T000000Z')
        make_run(self.work, '20261021T000000Z', status='running')
        make_run(self.work, '20261022T000000Z', argv=('--quick',))
        self.assertEqual(plz.find_latest_run(self.work, CAP, ZONE), good)

    def test_no_eligible_run_errors(self):
        make_run(self.work, '20261022T000000Z', argv=('--quick',))
        with self.assertRaises(plz.PublishError):
            self.go()

    def test_publishes_with_site_registration_label_and_overwrites(self):
        make_run(self.work, '20261020T000000Z')
        r = self.go()
        self.go()  # overwrite must not raise
        self.assertEqual(r['alignment'], 'project-frame-provisional')
        index = json.loads((self.pub / CAP / 'zones' / 'index.json').read_text())
        self.assertEqual(index['alignment'], 'project-frame-provisional')
        self.assertEqual([z['id'] for z in index['zones']], [ZONE])
        manifest = json.loads((self.pub / CAP / 'zones' / ZONE / 'viewer.json').read_text())
        self.assertIn('nadir faces masked', manifest['publication'])
        self.assertTrue((self.pub / CAP / 'zones' / ZONE / 'a.ksplat').is_file())

    def test_existing_index_alignment_wins_over_site_registration(self):
        make_run(self.work, '20261020T000000Z')
        idx = self.pub / CAP / 'zones'
        idx.mkdir(parents=True)
        (idx / 'index.json').write_text(json.dumps({'alignment': 'custom-label', 'zones': []}))
        self.assertEqual(self.go()['alignment'], 'custom-label')
        self.assertEqual(json.loads((idx / 'index.json').read_text())['alignment'], 'custom-label')

    def test_explicit_alignment_overrides(self):
        make_run(self.work, '20261020T000000Z')
        self.assertEqual(self.go(alignment='geometry-registered')['alignment'], 'geometry-registered')

    def test_missing_alignment_source_errors(self):
        make_run(self.work, '20261020T000000Z')
        (self.caps / CAP / 'registration.json').unlink()
        with self.assertRaises(plz.PublishError):
            self.go()

    def test_refuses_superseded_preset(self):
        with self.assertRaises(plz.PublishError):
            plz.publish_zone('2026-10-18-L3', 'l3-a', presets=PRESETS, output_root=self.work, publish_root=self.pub,
                             captures_root=self.caps, zone_loader=loader)
        self.assertFalse(self.pub.exists())

    def test_run_of_other_zone_rejected(self):
        folder = make_run(self.work, '20261020T000000Z', zone='l1-a')
        with self.assertRaises(plz.PublishError):
            self.go(run=str(folder))


if __name__ == '__main__':
    unittest.main()
