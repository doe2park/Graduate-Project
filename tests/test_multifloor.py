"""Pure geometry / route tests for scripts/multifloor_link.py and scripts/multifloor_review.py (no OpenCV, no data)."""
import math, sys, unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import multifloor_link as ml
import multifloor_review as mr


def synthetic_pair(yaw_deg, centre_b, n=300, seed=1):
    """Bearings of random points seen from A (origin, world-aligned) and B (rotated frame R = Rz(yaw))."""
    rng = np.random.default_rng(seed)
    X = rng.uniform([-8, -8, -2], [8, 8, 4], (n, 3))
    R = ml.rot_z(yaw_deg)
    f1 = X / np.linalg.norm(X, axis=1, keepdims=True)
    Xb = (R @ (X - centre_b).T).T
    f2 = Xb / np.linalg.norm(Xb, axis=1, keepdims=True)
    return f1, f2, R


class RelativePoseTests(unittest.TestCase):
    def test_recovers_yaw_and_direction(self):
        c = np.array([2.0, 1.0, 0.6])
        f1, f2, R = synthetic_pair(81.6, c)
        r = ml.relative_pose(f1, f2, iters=200)
        self.assertAlmostEqual(ml.yaw_deg(r['R']), 81.6, places=3)
        self.assertLess(ml.tilt_deg(r['R']), 1e-3)
        self.assertLess(ml.angle_deg(r['direction'], c), 1e-3)

    def test_too_few_matches(self):
        self.assertIsNone(ml.relative_pose(np.eye(3), np.eye(3)))

    def test_ray_intersection_and_residuals(self):
        P = np.array([3.0, -2.0, 1.5]); rays = [(o, P - o, 1.0) for o in (np.zeros(3), np.array([5.0, 0, 0]), np.array([0, 4.0, 1]))]
        Q = ml.intersect_rays(rays)
        self.assertTrue(np.allclose(Q, P))
        self.assertTrue(all(r['missMetres'] < 1e-9 for r in ml.ray_residuals(Q, rays)))

    def test_viewer_registration_matches_e57_rotation(self):
        """E57 p' = Rz(-yaw) p + t equals the viewer-convention registration on [x, z, -y] positions."""
        yaw, t = 81.565, np.array([24.5, -7.9, 9.0])
        reg = ml.viewer_registration(yaw, t)
        p = np.array([13.87, 12.65, -1.69])  # E57
        e = ml.rot_z(-yaw) @ p + t
        v = mr.apply(reg, [p[0], p[2], -p[1]])[0]
        self.assertTrue(np.allclose(v, [e[0], e[2], -e[1]]))

    def test_pixel_dirs_convention(self):
        d, el = ml.pixel_dirs(np.array([[1023.5, 511.5], [511.5, 511.5], [1023.5, 0]], float))
        self.assertTrue(np.allclose(d[0], [1, 0, 0], atol=1e-3))   # centre = +X
        self.assertTrue(np.allclose(d[1], [0, 1, 0], atol=1e-2))   # left quarter = +Y
        self.assertGreater(d[2][2], 0.99)                          # top = +Z


class TransformTests(unittest.TestCase):
    def test_compose_and_invert(self):
        a = {'rotationYDegrees': -81.5, 'translation': [24.5, 9.0, 7.9]}; b = {'rotationYDegrees': 0.08, 'translation': [-35.2, 0.63, -25.1]}
        p = np.array([[13.0, 1.9, -5.0], [1, 2, 3]])
        self.assertTrue(np.allclose(mr.apply(mr.compose(a, b), p), mr.apply(b, mr.apply(a, p))))
        self.assertTrue(np.allclose(mr.apply(mr.invert(b), mr.apply(b, p)), p))

    def test_quaternion_yaw_rotates_panorama_forward(self):
        q = [0.0, 0.0, math.sqrt(.5), math.sqrt(.5)]
        q2 = mr.rotate_e57_quaternion(q, 30)
        f = ml.quat_matrix(q2) @ [1, 0, 0]; f0 = ml.quat_matrix(q) @ [1, 0, 0]
        self.assertTrue(np.allclose(f, ml.rot_z(30) @ f0))


class FloorAndRouteTests(unittest.TestCase):
    def test_floor_below_and_level(self):
        slab = lambda y: np.array([[[-10, y, -10], [10, y, -10], [10, y, 10]], [[-10, y, -10], [10, y, 10], [-10, y, 10]]], float)
        tris = np.concatenate([slab(5.2), slab(9.4), slab(14.3)])
        h = mr.horizontal_triangles(tris)
        self.assertAlmostEqual(mr.floor_below(h, (0, 16.3, 0)), 14.3)
        self.assertAlmostEqual(mr.floor_below(h, (0, 11.4, 0)), 9.4)
        self.assertIsNone(mr.floor_below(h, (30, 16.3, 0)))
        self.assertEqual(mr.classify_level(14.25), 'L3'); self.assertEqual(mr.classify_level(9.5), 'L2')
        self.assertEqual(mr.classify_level(12.0), 'stairs'); self.assertIsNone(mr.classify_level(None))

    def test_route_kinds(self):
        st = [{'id': 'a', 'position': [0, 16.3, 0], 'level': 'L3'}, {'id': 'b', 'position': [4, 16.3, 0], 'level': 'L3'},
              {'id': 'c', 'position': [6, 14.6, 0], 'level': 'stairs'}, {'id': 'd', 'position': [9, 11.4, 0], 'level': 'L2'},
              {'id': 'e', 'position': [40, 11.4, 0], 'level': 'L2'}, {'id': 'f', 'position': [44, 11.4, 0], 'level': 'L2'},
              {'id': 'g', 'position': [9, 7.4, 3], 'level': 'L1'}]
        vis = [{'a': 'd', 'b': 'f', 'verified': True}, {'a': 'a', 'b': 'd', 'verified': True}, {'a': 'b', 'b': 'd', 'verified': False}]
        A = [{'index': 7, 'position': [10, 7.2, 4], 'level': 'L1'}, {'index': 8, 'position': [30, 7.2, 4], 'level': 'L1'}]
        e = mr.build_route(st, vis, A)
        self.assertEqual(e['a']['b'], 'route'); self.assertEqual(e['b']['c'], 'stairs'); self.assertEqual(e['c']['d'], 'stairs')
        self.assertNotIn('e', e['d'])            # 31 m frame gap stays a gap
        self.assertEqual(e['e']['f'], 'route')
        self.assertNotIn('f', e['d'])            # verified but 35 m: too long
        self.assertNotIn('d', e['a'])            # different floors: never a visual shortcut
        self.assertEqual(e['g'].get('A:7'), 'link-inferred'); self.assertNotIn('A:8', e['g'])
        self.assertNotIn('A:7', e['d'])          # 4 m height difference: no cross-video link

    def test_bim_clear_links_need_same_floor_and_no_wall(self):
        st = [{'id': 'a', 'position': [0, 16.3, 0], 'level': 'L3'}, {'id': 'x', 'position': [30, 16.3, 0], 'level': 'L3'},
              {'id': 'b', 'position': [3, 16.3, 0], 'level': 'L3'}, {'id': 'c', 'position': [0, 16.3, 3], 'level': 'L3'}]
        wall = np.array([[[1.5, -5], [1.5, 5]]])
        clear = lambda p, q: not mr.segment_blocked(np.asarray(p)[[0, 2]], np.asarray(q)[[0, 2]], wall)
        e = mr.build_route(st, (), (), clear=clear)
        self.assertNotIn('b', e['a'])                        # wall at x = 1.5 between a and b
        self.assertEqual(e['a'].get('c'), 'link-bim-clear')  # same side of the wall, 3 m
        self.assertNotIn('a', mr.build_route(st, (), ())['c'])  # no clear test -> no inferred link

    def test_segment_blocked(self):
        segs = np.array([[[0, -1], [0, 1]]], float)
        self.assertTrue(mr.segment_blocked([-1, 0], [1, 0], segs)); self.assertFalse(mr.segment_blocked([1, 0], [2, 0], segs))
        self.assertFalse(mr.segment_blocked([-1, 0], [1, 0], np.zeros((0, 2, 2))))


    def test_package_floor_assignment(self):
        self.assertEqual(mr.package_floor('L3', 14.4), 'L3'); self.assertEqual(mr.package_floor('L2', 9.5), 'L2')
        self.assertEqual(mr.package_floor('stairs', 12.65), 'L3')   # upper flight goes with Level 3 (its top)
        self.assertEqual(mr.package_floor(None, 12.57), 'L3')
        self.assertEqual(mr.package_floor('stairs', 7.92), 'L2')    # lower flight goes with Level 2
        self.assertEqual(mr.package_floor('stairs', 5.96), 'L2')    # stair foot on Level 1: Level 1 has its own package
        self.assertEqual(mr.package_floor('stairs', 9.3), 'L3')     # first step above Level 2 belongs to the flight up
        self.assertIsNone(mr.package_floor('stairs', None)); self.assertIsNone(mr.package_floor('stairs', 18.0))

    def test_subset_edges_components_default(self):
        st = [{'id': 'a', 'position': [0, 16.3, 0], 'level': 'L3'}, {'id': 'b', 'position': [4, 16.3, 0], 'level': 'L3'},
              {'id': 'c', 'position': [6, 14.6, 0], 'level': 'stairs'}, {'id': 'd', 'position': [9, 11.4, 0], 'level': 'L2'},
              {'id': 'e', 'position': [40, 16.3, 0], 'level': 'L3'}, {'id': 'f', 'position': [42, 16.3, 0], 'level': 'L3'}, {'id': 'x', 'position': [44, 16.3, 0], 'level': 'L3'}]
        e = mr.build_route(st, (), ())
        sub = mr.subset_edges(e, {'a', 'b', 'c', 'e', 'f', 'x'})
        self.assertNotIn('d', sub); self.assertNotIn('d', sub['c'])   # cross-floor link dropped
        self.assertEqual(sub['b']['c'], 'stairs')
        groups = mr.components(['a', 'b', 'c', 'e', 'f', 'x'], sub)
        self.assertEqual([sorted(g) for g in groups], [['a', 'b', 'c'], ['e', 'f', 'x']])
        rows = [s for s in st if s['id'] != 'd']
        self.assertIn(mr.default_station(rows, sub), ('a', 'b'))       # medoid of the (first) largest group, stair 'c' skipped
        stairy = [{**r, 'position': [1, 16.3, 0]} if r['id'] == 'c' else r for r in rows]
        self.assertNotEqual(mr.default_station(stairy, sub), 'c')      # never opens on a stair station when the floor has others
        for a_, nb in sub.items():
            for b_ in nb: self.assertIn(a_, sub[b_])                 # symmetric
    def test_source_frame_and_levelled_similarity(self):
        self.assertEqual(mr.source_frame('VID_20261018_153400_00_477(287).jpg'), 287)
        rng = np.random.default_rng(3); src = rng.uniform(-5, 5, (8, 3)); src[:, 2] *= 0.1
        a = math.radians(5.0); L = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])  # SfM frame tilted 5 deg
        y = math.radians(81.5); Rz = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]])
        up_sfm = L.T @ np.array([0, 0, 1.0]); src_t = src @ L                         # points as seen in the tilted SfM frame
        dst = 1.9 * (src @ Rz.T) + np.array([10, -3, 14])
        s, R, t = mr.fit_levelled_similarity(src_t, dst, up_sfm)
        self.assertAlmostEqual(s, 1.9, places=6)
        self.assertTrue(np.allclose((s * (R @ src_t.T)).T + t, dst, atol=1e-6))


if __name__ == '__main__':
    unittest.main()
