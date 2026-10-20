import importlib.util, io, json, math, struct, sys, tempfile, unittest
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
core = load('raw360_core')

def rotz(deg):
    a = math.radians(deg); return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1.0]])

class ScaleTests(unittest.TestCase):
    def grid(self, floor):
        xs, ys = np.meshgrid(np.linspace(-5, 15, 60), np.linspace(-4, 4, 30)); x, y = xs.ravel(), ys.ravel()
        return np.c_[x, y, floor(x)]
    def test_flat_floor_scale(self):
        cams = np.array([[i, 0, 0.8] for i in range(10)], float)
        d = core.floor_distances(cams, self.grid(lambda x: 0 * x), [0, 0, 1], radius=1.0)
        self.assertTrue(np.allclose(d, 0.8)); self.assertAlmostEqual(core.camera_height_scale(d, 1.6)['scale'], 2.0)
    def test_raked_floor_uses_local_floor(self):
        cams = np.array([[i, 0, 0.1 * i + 0.8] for i in range(10)], float)
        d = core.floor_distances(cams, self.grid(lambda x: 0.1 * x), [0, 0, 1], radius=0.5)
        self.assertAlmostEqual(core.camera_height_scale(d, 1.6)['scale'], 2.0, delta=0.05)
    def test_furniture_above_floor_ignored(self):
        pts = self.grid(lambda x: 0 * x); seats = pts.copy(); seats[:, 2] = 0.45
        d = core.floor_distances([[5, 0, 0.8]], np.r_[pts, seats[::3]], [0, 0, 1], radius=1.5)
        self.assertAlmostEqual(d[0], 0.8, delta=0.02)
    def test_too_few_cameras_rejected(self):
        with self.assertRaises(ValueError): core.camera_height_scale([np.nan, 0.8], 1.6)

class SimilarityTests(unittest.TestCase):
    def test_umeyama_recovers_similarity(self):
        rng = np.random.default_rng(1); A = rng.normal(size=(12, 3)) * 4; R = rotz(37) @ core.exp_so3([0.1, -0.05, 0]); t = np.array([3, -2, 7.0])
        s, R2, t2 = core.umeyama(A, (2.5 * (R @ A.T)).T + t)
        self.assertAlmostEqual(s, 2.5); self.assertTrue(np.allclose(R2, R)); self.assertTrue(np.allclose(t2, t))
    def test_landmark_similarity_reports_checks_and_rejects_collinear(self):
        move = lambda p: (0.5 * (rotz(90) @ np.array(p, float))) + [1, 2, 3]
        pts = [[0, 0, 0], [4, 0, 0], [0, 5, 0], [2, 2, 1]]
        r = core.landmark_similarity([{'scan': p, 'bim': move(p).tolist()} for p in pts[:3]], [{'scan': pts[3], 'bim': move(pts[3]).tolist()}],
                                     [{'a': [0, 0, 0], 'b': [2, 0, 0], 'metres': 1.0}])
        self.assertAlmostEqual(r['scale'], 0.5); self.assertLess(r['checkMaxMetres'], 1e-9); self.assertAlmostEqual(r['distanceScale'], 0.5)
        with self.assertRaises(ValueError):
            core.landmark_similarity([{'scan': [i, 0, 0], 'bim': [i, 0, 0]} for i in range(3)])

class SelectionTests(unittest.TestCase):
    def test_uniform_motion_even_spacing(self):
        picks = core.select_keyframes([0] + [1.0] * 99, [1.0] * 100, count=11)
        self.assertEqual(len(picks), 11); self.assertTrue(all(8 <= b - a <= 12 for a, b in zip(picks, picks[1:])))
    def test_standing_still_adds_no_keyframes_and_prefers_sharp(self):
        motion = [0] + [1.0] * 20 + [0.0] * 40 + [1.0] * 20; sharp = [1.0] * 81; sharp[10] = 50
        picks = core.select_keyframes(motion, sharp, step=10, window=0.5, max_gap=8)
        self.assertIn(10, picks); self.assertFalse(any(25 < p < 60 for p in picks))
    def test_max_gap_when_motion_underestimated(self):
        picks = core.select_keyframes([0] + [1.0] * 59, [1.0] * 60, step=30, max_gap=10)
        self.assertTrue(max(b - a for a, b in zip(picks, picks[1:])) <= 10)
    def test_walking_cue_separates_rest_and_walk(self):
        t = np.arange(0, 4000, 8.0); acc = np.tile([0, 0, 1.0], (len(t), 1)); walk = t > 2000
        acc[walk, 2] += 0.15 * np.sin(2 * np.pi * 2 * t[walk] / 1000)
        cue, raw, rest = core.walking_cue(t, acc, [500, 1500, 2500, 3500])
        self.assertLess(cue[0], 1e-6); self.assertGreater(cue[3], 0.05)
    def test_yaw_invariant_descriptor_and_pairs(self):
        rng = np.random.default_rng(0); img = rng.random((96, 256)) * 255
        a, b = core.yaw_invariant_descriptor(img), core.yaw_invariant_descriptor(np.roll(img, 64, axis=1))
        self.assertGreater(a @ b, 0.999)
        D = np.eye(30)[:, :8].copy(); D[25] = D[2]; D /= np.linalg.norm(D, axis=1, keepdims=True) + 1e-12
        pairs = core.panorama_pairs(30, 2, D, loops_per_frame=1, min_separation=10)
        self.assertIn((0, 1), pairs); self.assertIn((0, 2), pairs); self.assertNotIn((0, 3), pairs); self.assertIn((2, 25), pairs)

class GeometryTests(unittest.TestCase):
    def test_quaternion_round_trip_and_level(self):
        R = core.exp_so3([0.3, -0.2, 1.1]); q = core.quat_from_matrix(R)
        self.assertAlmostEqual(float(np.linalg.norm(q)), 1.0); self.assertTrue(np.allclose(core.matrix_from_quat(q), R))
        up = np.array([0.1, -0.2, 0.97]); self.assertTrue(np.allclose(core.level_rotation(up) @ (up / np.linalg.norm(up)), [0, 0, 1]))
    def test_view_rotation_and_e57_pixel_convention(self):
        for yaw in [0, 90, 180, 270]:
            R = core.cam_from_pano(yaw); self.assertAlmostEqual(np.linalg.det(R), 1.0)
            self.assertTrue(np.allclose(R.T @ [0, 0, 1], [math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0], atol=1e-12))
        mx, my, f = core.pinhole_maps(core.cam_from_pano(0), 101, 90, 400, 200)
        self.assertAlmostEqual(float(mx[50, 50]), 199.5, places=3); self.assertAlmostEqual(float(my[50, 50]), 99.5, places=3)
        u, v = core.dir_to_equirect_px(np.array([0, 1.0, 0]), 400, 200); self.assertAlmostEqual(float(u), 99.5)  # +Y left of centre
        self.assertLess(float(core.dir_to_equirect_px(np.array([0, 0, 1.0]), 400, 200)[1]), 0)  # +Z at top
    def test_rotate_equirect_and_yaw_shift(self):
        rng = np.random.default_rng(3); img = np.kron(rng.random((32, 64)), np.ones((8, 8))) * 255
        rot = core.rotate_equirect(img, rotz(45))
        self.assertTrue(np.allclose(rot[:, 64:], np.roll(img, -64, axis=1)[:, 64:], atol=1e-3))
        shift, _ = core.yaw_shift_deg(img, rot); self.assertAlmostEqual(core.wrap_deg(shift + 45), 0, delta=1)
    def test_interpolate_track(self):
        R = [np.eye(3), rotz(90)]; p = [np.zeros(3), np.array([10.0, 0, 0])]
        self.assertEqual(core.interpolate_track([0, 10], p, R, 0, 5)[2], 'exact')
        pos, Rm, kind = core.interpolate_track([0, 10], p, R, 5, 10); self.assertTrue(np.allclose(pos, [5, 0, 0])); self.assertAlmostEqual(core.rotation_angle_deg(Rm), 45)
        self.assertIsNone(core.interpolate_track([0, 10], p, R, 5, 9))
    def test_gyro_integration_and_hand_eye(self):
        t = np.arange(0, 1001, 2.0); gyro = np.tile([0, 0, math.pi / 2], (len(t), 1))
        self.assertAlmostEqual(core.rotation_angle_deg(core.integrate_gyro(t, gyro, 0, 1000)), 90, delta=0.5)
        X = core.exp_so3([0.4, 0.1, -0.7]); a = np.random.default_rng(2).normal(size=(6, 3))
        self.assertTrue(np.allclose(core.kabsch_rotation(a, (X @ a.T).T), X))

class TrailerAndExportTests(unittest.TestCase):
    CAL = ('2_1.728590_2330.060_2330.690_1518.610_1518.140_0.129_-0.510_-179.528_0.000000_0.000000_0.000000_0.24010099_-0.19895484'
           '_-0.93587917_-0.00000748_0.00045540_6080_3040_41_1.728590_2325.120_2325.840_4553.850_1521.950_-0.013_-0.819_-0.368_0.000162'
           '_-0.000625_-0.020551_0.26154283_-0.34033516_-0.69431013_0.00070931_-0.00014739_6080_3040_41_199680')
    def test_trailer_index_imu_and_calibration(self):
        meta = b'\x12\x0fInsta360 ONE X2*' + self.CAL.encode()
        imu = struct.pack('<Q6d', 1000, 0, 0, 1, 0.1, 0, 0) + struct.pack('<Q6d', 1008, 0, 0, 1, 0.2, 0, 0)
        recs = b''
        for rid, payload in [(0x300, imu), (0x101, meta)]:
            recs += payload + struct.pack('<HI', rid, len(payload))
        body = b'video' + recs + b'\0' * 32; total = len(recs) + 32 + 8 + 32
        blob = body + struct.pack('<II', total, 3) + core.TRAILER_MAGIC
        idx = core.parse_trailer_index(io.BytesIO(blob), len(blob))
        self.assertEqual(set(k for k in idx if k != '_version'), {0x101, 0x300})
        o, n = idx[0x300]; t, acc, gyr = core.parse_imu(blob[o:o + n]); self.assertEqual(list(t), [1000, 1008]); self.assertAlmostEqual(gyr[1, 0], 0.2)
        o, n = idx[0x101]; lenses = core.parse_lens_calibration(blob[o:o + n])
        self.assertEqual(len(lenses), 2); self.assertAlmostEqual(lenses[1]['tz'], -0.020551)
        fov, err = core.equidistant_fov_from_mei(lenses[0], 2880); self.assertAlmostEqual(fov, 196.6, delta=0.5); self.assertLess(err, 20)
        self.assertEqual(core.parse_trailer_index(io.BytesIO(b'x' * 100), 100), {})
    def test_stitch_filter_lens_orientation(self):
        pipe = load('raw360_pipeline'); fg = pipe.stitch_filter(196.568, 4096, 2048, frames=[3, 9])
        self.assertIn('[0:v]select=', fg); self.assertIn('transpose=1[a]', fg); self.assertIn('transpose=2[b]', fg)
        self.assertIn('input=dfisheye', fg); self.assertIn('ih_fov=196.568', fg); self.assertIn('eq(n\\,9)', fg)
    def test_export_record_is_accepted_by_capture_import(self):
        from PIL import Image
        import hashlib
        ci = load('capture_import')
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'src'; src.mkdir(); Image.new('RGB', (64, 32), 'gray').save(src / 'f000012.jpg')
            sha = hashlib.sha256((src / 'f000012.jpg').read_bytes()).hexdigest()
            q = core.quat_from_matrix(rotz(30) @ core.exp_so3([0.05, 0, 0]))
            rec = core.images_json_record('raw360_f000012', 'f000012.jpg', sha, 64, 32, [1.0, 2.0, 1.6], q, {'sourceFrame': 13})
            self.assertEqual(set(rec['pose']['rotation']), {'x', 'y', 'z', 'w'})
            (src / 'images.json').write_text(json.dumps({'images': [rec]}))
            out = Path(tmp) / 'pkg'; ci.prepare(src, out, 'grimes', 'L1', '2026-09-17')
            st = json.loads((out / 'panoramas/manifest.json').read_text())['stations'][0]
            self.assertEqual(st['position'], [1.0, 1.6, -2.0]); self.assertEqual(st['id'], 'raw360_f000012')

if __name__ == '__main__':
    unittest.main()
