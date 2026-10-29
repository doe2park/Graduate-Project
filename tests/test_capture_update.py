"""Dated capture-update packages (scan-assets/captures/<date>/): payload hashes, mobile derivatives, frame-ordered
route edges (consecutive frames, <=5.5 m, <=1.5 m rise), provisional May-transform registration and provenance.
Also unit-tests the builder's route and frame-number helpers (scripts/build_capture_update.py)."""
import hashlib, json, math, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_capture_update as B

MAY = json.loads((ROOT / 'alignment-analysis/accepted-registration.json').read_text())


def load(date):
    base = ROOT / 'scan-assets/captures' / date
    return base, json.loads((base / 'panoramas/manifest.json').read_text())


class RouteRule(unittest.TestCase):
    def test_frame_number(self):
        self.assertEqual(B.frame_number('VID_20261018_141325_00_474(306).jpg'), 306)
        with self.assertRaises(ValueError):
            B.frame_number('00000.jpg')

    def test_route_links_only_close_consecutive_frames(self):
        s = [{'position': p, 'neighbors': []} for p in ([0, 5, 0], [5, 5, 0], [12, 5, 0], [13, 7, 0], [14, 7, 0])]
        edges, gaps = B.route(s)
        self.assertEqual(edges, 2)
        self.assertEqual([(g['from'], g['to']) for g in gaps], [(1, 2), (2, 3)])
        self.assertEqual([x['neighbors'] for x in s], [[1], [0], [], [4], [3]])

    def test_rule_reproduces_sep17_edges(self):
        _, m = load('2026-09-17'); s = [{'position': x['position'], 'neighbors': []} for x in m['stations']]
        edges, gaps = B.route(s)
        self.assertEqual(edges, 95)
        self.assertEqual([x['neighbors'] for x in s], [x['neighbors'] for x in m['stations']])
        self.assertEqual(gaps, m['routeGaps'])


@unittest.skipUnless((ROOT / 'scan-assets/captures/2026-10-18/panoramas/manifest.json').is_file(), 'Oct 18 package not built')
class Oct18Package(unittest.TestCase):
    def setUp(self):
        self.base, self.m = load('2026-10-18')

    def test_payloads(self):
        from PIL import Image
        s = self.m['stations']
        self.assertEqual(self.m['captureDate'], '2026-10-18'); self.assertEqual(self.m['level'], 'L1')
        self.assertEqual(len(s), self.m['exportedStations']); self.assertEqual(len(s), 100)
        self.assertEqual(len({x['id'] for x in s}), len(s)); self.assertEqual(self.m['defaultStation'], s[0]['id'])
        self.assertEqual([x['sourceFrame'] for x in s], sorted(x['sourceFrame'] for x in s))
        for i, x in enumerate(s):
            with self.subTest(x['id']):
                self.assertEqual(x['file'], f'{i:05d}.jpg')
                self.assertAlmostEqual(sum(v * v for v in x['e57Quaternion']), 1, places=10)
                self.assertTrue(all(math.isfinite(v) for v in x['position']))
                f = self.base / 'panoramas' / x['file']
                self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(), x['sha256'])
                self.assertNotEqual(x['sha256'], x['originalSha256'], 'published image is the blurred copy')
                with Image.open(f) as im: self.assertEqual(list(im.size), [4096, 2048])
                with Image.open(self.base / 'panoramas/mobile' / x['file']) as im: self.assertEqual(im.size, (2048, 1024))

    def test_route(self):
        s = self.m['stations']; n = 0
        for i, x in enumerate(s):
            for j in x['neighbors']:
                self.assertEqual(abs(i - j), 1, 'only consecutive frames')
                self.assertIn(i, s[j]['neighbors'])
                self.assertLessEqual(math.dist(x['position'], s[j]['position']), 5.5)
                self.assertLessEqual(abs(x['position'][1] - s[j]['position'][1]), 1.5)
                n += 1
        prov = json.loads((self.base / 'provenance.json').read_text())
        self.assertEqual(n // 2, prov['routeEdges']); self.assertEqual(prov['routeGaps'], self.m['routeGaps'])
        self.assertEqual(n // 2 + len(self.m['routeGaps']), len(s) - 1)

    def test_registration_is_provisional_may_transform(self):
        r = json.loads((self.base / 'registration.json').read_text())
        self.assertEqual(r['status'], 'project-frame-provisional'); self.assertEqual(r['captureDate'], '2026-10-18')
        self.assertEqual(r['rotationYDegrees'], MAY['rotationYDegrees']); self.assertEqual(r['translation'], MAY['translation'])
        self.assertEqual(r['scale'], 1); self.assertIn('not surveyed', r['consistencyCheck']['scope'].lower())

    def test_provenance_and_no_mesh(self):
        p = json.loads((self.base / 'provenance.json').read_text())
        self.assertEqual(p['exportOptions'], {'e57': 'With Pano', 'useCoordinatesFromSourceData': False})
        self.assertEqual(p['rawFiles'][0]['name'], 'Point cloud test_Level 1_pointcloud_Oct 18, 2026.e57')
        self.assertEqual(len(p['rawFiles'][0]['sha256']), 64)
        pr = p['privacy']
        self.assertTrue(pr['manualReviewRequired']); self.assertEqual(len(pr['reportSha256']), 64)
        self.assertEqual(pr['manualReview']['status'], 'done'); self.assertEqual(pr['manualReview']['publishApproved'], '2026-10-28')
        self.assertEqual(pr['params']['alwaysBlurNadirDeg'], 35.0); self.assertEqual(pr['params']['faceScore'], 0.85)
        self.assertIsNone(p['mesh'])
        self.assertFalse(list(self.base.rglob('*.glb')), 'mesh view is retired; no GLB in the package')


def jpeg_size(path):
    """(width, height) from the first SOF marker of a JPEG (no Pillow needed)."""
    b = path.read_bytes(); i = 2
    while i < len(b):
        if b[i] != 0xFF: i += 1; continue
        m = b[i + 1]
        if m in (0xC0, 0xC1, 0xC2): return int.from_bytes(b[i + 7:i + 9], 'big'), int.from_bytes(b[i + 5:i + 7], 'big')
        i += 2 + int.from_bytes(b[i + 2:i + 4], 'big')
    raise ValueError(path)


@unittest.skipUnless((ROOT / 'scan-assets/captures/2026-10-18/floors/L2/panoramas/manifest.json').is_file(), 'upper floors not published')
class Oct18UpperFloors(unittest.TestCase):
    """Published Level 2 / Level 3 packages (scripts/publish_upper_floors.py, 2026-10-28): approved manual-blur photos only."""
    def test_packages(self):
        reg = json.loads((ROOT / 'scan-assets/captures/2026-10-18/registration.json').read_text())
        self.assertEqual(reg['status'], 'project-frame-provisional')
        total_boxes = 0
        for floor in ('L2', 'L3'):
            base = ROOT / 'scan-assets/captures/2026-10-18/floors' / floor
            m = json.loads((base / 'panoramas/manifest.json').read_text()); p = json.loads((base / 'provenance.json').read_text())
            s = m['stations']
            self.assertEqual((m['level'], m['captureDate'], m['status']), (floor, '2026-10-18', 'published-provisional'))
            self.assertEqual(len(s), 54); self.assertEqual(m['exportedStations'], 54)
            self.assertIn(m['defaultStation'], {x['id'] for x in s})
            files = {f['file']: f for f in p['files']}
            self.assertEqual(set(files), {x['file'] for x in s})
            for i, x in enumerate(s):
                self.assertEqual(x['file'], f"f{x['sourceFrame']:06d}.jpg"); self.assertIn(x['level'], (floor, 'stairs'))
                full, mob = base / 'panoramas' / x['file'], base / 'panoramas/mobile' / x['file']
                self.assertEqual(hashlib.sha256(full.read_bytes()).hexdigest(), x['sha256'])
                self.assertEqual(hashlib.sha256(mob.read_bytes()).hexdigest(), x['mobileSha256'])
                self.assertEqual(files[x['file']]['sha256'], x['sha256'])
                self.assertEqual(jpeg_size(full), (4096, 2048)); self.assertEqual(jpeg_size(mob), (2048, 1024))
                for n in x['neighbors']: self.assertIn(i, s[n]['neighbors'])
            # nothing but the photos, their mobile copies, the manifest and the provenance record
            published = sorted(str(f.relative_to(base)) for f in base.rglob('*') if f.is_file())
            expected = sorted(['provenance.json', 'panoramas/manifest.json'] + [f'panoramas/{x["file"]}' for x in s] + [f'panoramas/mobile/{x["file"]}' for x in s])
            self.assertEqual(published, expected)
            pr = p['privacy']; total_boxes += pr['manualBoxes']['thisFloor']
            self.assertEqual(pr['manualReview']['publishApproved'], '2026-10-28'); self.assertEqual(pr['automaticBlur']['params']['personScore'], 0.15)
            self.assertEqual(pr['automaticBlur']['params']['crop'], 1536); self.assertFalse(p['placementCupixFree'])
            self.assertEqual(p['registration']['file'], '../../registration.json')
        self.assertEqual(total_boxes, 1241)
        self.assertFalse([f for f in (ROOT / 'scan-assets/captures/2026-10-18/floors').rglob('*') if f.suffix in ('.glb', '.ply', '.ksplat', '.splat', '.e57')])


if __name__ == '__main__':
    unittest.main()
