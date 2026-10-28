"""Cupix-free BIM placement of raw360 SfM submodels (scripts/raw360_bim.py) and the one-command runner's planning
(scripts/capture_upper_floors.py). Synthetic data only; no BIM soup, pycolmap or images needed.

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_raw360_bim
"""
import math, sys, unittest
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import raw360_bim as rb  # noqa: E402
import raw360_core as core  # noqa: E402
import multifloor_review as mr  # noqa: E402
import capture_upper_floors as cuf  # noqa: E402


def rz(deg):
    return rb.rot_z(math.radians(deg))


class FrameTests(unittest.TestCase):
    def test_axes_round_trip_and_yaw_convention(self):
        p = np.array([[1.0, 2.0, 3.0], [-4.0, 0.5, 9.0]])
        np.testing.assert_allclose(rb.to_viewer(rb.to_e57(p)), p)
        # registration_fit viewer yaw a on viewer points == E57 rotation +a about +Z on E57 points
        reg = {'rotationYDegrees': 33.0, 'translation': [0, 0, 0]}
        np.testing.assert_allclose(mr.apply(reg, p), rb.to_viewer((rb.viewer_yaw_to_e57(33.0) @ rb.to_e57(p).T).T), atol=1e-12)

    def test_pose_maps_points_and_rotations(self):
        L = core.level_rotation([0.05, -0.02, 1.0]); P = rb.Pose(2.0, 30.0, [1, 2, 3], L)
        x = np.array([[0.5, 0.1, -0.2]])
        np.testing.assert_allclose(P.points(x)[0], 2.0 * (rz(30) @ L @ x[0]) + [1, 2, 3])
        np.testing.assert_allclose(P.rotation(np.eye(3)), rz(30) @ L)


class ScaleTests(unittest.TestCase):
    def test_floor_mode_ignores_floor_seen_through_an_atrium(self):
        rng = np.random.default_rng(0)
        C = np.stack([np.linspace(0, 20, 30), np.zeros(30), np.full(30, 1.0)], 1)       # units: camera 1.0 above floor
        floor = np.c_[rng.uniform(-2, 22, 3000), rng.uniform(-3, 3, 3000), rng.normal(0, 0.01, 3000)]
        atrium = np.c_[rng.uniform(-2, 22, 4000), rng.uniform(-3, 3, 4000), rng.normal(-2.45, 0.01, 4000)]  # lower floor (subsampled below)
        ceiling = np.c_[rng.uniform(-2, 22, 3000), rng.uniform(-3, 3, 3000), rng.normal(2.0, 0.01, 3000)]
        walls = np.c_[rng.uniform(-2, 22, 2000), rng.choice([-3, 3], 2000), rng.uniform(0, 2, 2000)]
        # the atrium floor is seen only far from the cameras' own floor patch, i.e. at larger height below; still lower layer
        mode, per, second = rb.floor_mode(C, np.vstack([floor, atrium[::4], ceiling, walls]), radius=2.0)
        self.assertAlmostEqual(mode, 1.0, delta=0.04)
        self.assertGreater(np.isfinite(per).mean(), 0.9)
        # the old lowest-layer rule picks the atrium floor
        d = core.floor_distances(C, np.vstack([floor, atrium[::4], ceiling, walls]), [0, 0, 1], 2.0)
        self.assertGreater(np.nanmedian(d), 2.0)

    def test_level_and_scale_metres(self):
        rng = np.random.default_rng(1)
        C = np.stack([np.linspace(0, 10, 20), np.zeros(20), np.full(20, 0.5)], 1)
        P = np.c_[rng.uniform(-1, 11, 4000), rng.uniform(-2, 2, 4000), rng.normal(0, 0.005, 4000)]
        m = {'R': [np.eye(3)] * 20, 'C': C, 'P': P}
        ls = rb.level_and_scale(m, 2.0)
        self.assertAlmostEqual(ls['scale'], 4.0, delta=0.15)

    def test_floor_cluster(self):
        cl = rb.floor_cluster([0.0, 0.05, -0.02, 4.9, 4.95, 0.01, 2.4])
        self.assertAlmostEqual(cl[0][0], 0.0, delta=0.03); self.assertEqual(cl[0][1], 4)


def synthetic_link(aPos, aR, b_world, bR_world, L, bR_sfm, bC_sfm):
    """Relative pose between a placed panorama a and a submodel panorama b, in each panorama's own frame."""
    R = bR_world.T @ aR          # v_b = R v_a  with  world_from_b = aR R^T
    d = aR.T @ (b_world - aPos); d /= np.linalg.norm(d)
    return {'aPos': aPos, 'aR': aR, 'bCentre': bC_sfm, 'bR': bR_sfm, 'R': R, 'direction': d, 'weight': 50}


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.L = core.level_rotation([0.03, 0.01, 1.0]); self.s = 1.7; self.yaw = 57.0; self.t = np.array([-12.0, 4.0, 14.4])
        self.pose = rb.Pose(self.s, self.yaw, self.t, self.L)

    def make(self, a_positions, b_index=(0, 1)):
        rng = np.random.default_rng(3)
        bC = rng.uniform(-3, 3, (3, 3)); bR = [core.exp_so3(rng.normal(0, 0.3, 3)) for _ in range(3)]
        links = []
        for k, aPos in enumerate(a_positions):
            aR = rz(rng.uniform(0, 360)); i = b_index[k % len(b_index)]
            links.append(synthetic_link(np.asarray(aPos, float), aR, self.pose.points(bC[i])[0], self.pose.rotation(bR[i]), self.L, bR[i], bC[i]))
        return links

    def test_recovers_yaw_and_translation_from_rays(self):
        links = self.make([[-5, 0, 15], [-15, 6, 15.2], [-9, -6, 14.8]])
        out = rb.seed_from_links(links, self.s, self.L)
        self.assertNotIn('error', out)
        self.assertAlmostEqual(core.wrap_deg(out['yawDegrees'] - self.yaw), 0, places=6)
        np.testing.assert_allclose(out['translationE57'], self.t, atol=1e-6)
        self.assertLess(out['missMedianMetres'], 1e-6)

    def test_parallel_rays_are_refused(self):
        links = self.make([[-30, 0, 15], [-40, 0, 15]], b_index=(0,))
        # both rays to the same b station from a line through it: same direction
        out = rb.seed_from_links(links, self.s, self.L)
        self.assertIn('error', out)

    def test_shared_frame_gives_position_directly(self):
        bC = np.array([0.3, -0.2, 0.1]); bR = core.exp_so3([0.1, 0.0, 0.4])
        link = {'aPos': self.pose.points(bC)[0], 'aR': self.pose.rotation(bR), 'bCentre': bC, 'bR': bR, 'R': np.eye(3),
                'direction': [1.0, 0, 0], 'weight': 1000, 'shared': True}
        out = rb.seed_from_links([link], self.s, self.L)
        self.assertAlmostEqual(core.wrap_deg(out['yawDegrees'] - self.yaw), 0, places=6)
        np.testing.assert_allclose(out['translationE57'], self.t, atol=1e-9)

    def test_outlier_link_is_out_of_the_yaw_cluster(self):
        links = self.make([[-5, 0, 15], [-15, 6, 15.2], [-9, -6, 14.8]])
        bad = dict(links[0]); bad['R'] = rz(40) @ np.asarray(bad['R']); bad['weight'] = 10
        out = rb.seed_from_links(links + [bad], self.s, self.L)
        self.assertEqual(out['linksUsed'], 3)
        self.assertAlmostEqual(core.wrap_deg(out['yawDegrees'] - self.yaw), 0, places=6)


class IcpTests(unittest.TestCase):
    def test_similarity_icp_recovers_offset_yaw_and_scale(self):
        from scipy.spatial import cKDTree
        rng = np.random.default_rng(5)
        # BIM-E57: corridor walls (two L-shapes) + floor
        walls = np.vstack([np.c_[rng.uniform(0, 30, 4000), np.full(4000, 0.0), rng.uniform(0, 3, 4000)],
                           np.c_[rng.uniform(0, 30, 4000), np.full(4000, 2.5), rng.uniform(0, 3, 4000)],
                           np.c_[np.full(2000, 30.0), rng.uniform(-10, 2.5, 2000), rng.uniform(0, 3, 2000)],
                           np.c_[np.full(2000, 27.5), rng.uniform(-10, 0, 2000), rng.uniform(0, 3, 2000)],
                           np.c_[rng.uniform(0, 30, 4000), rng.uniform(0, 2.5, 4000), np.zeros(4000)],
                           np.c_[rng.uniform(0, 30, 4000), rng.uniform(0, 2.5, 4000), np.full(4000, 3.0)],      # ceiling
                           *[np.c_[np.full(1500, x), rng.uniform(0, 2.5, 1500), rng.uniform(0, 3, 1500)] for x in (0.0, 7.0, 15.0)]])  # cross walls
        L = np.eye(3); true = rb.Pose(2.0, 20.0, [3.0, -1.0, 0.5], L)
        src = (np.linalg.inv(true.R) @ ((walls[::3] - true.t) / true.s).T).T + rng.normal(0, 0.005, (len(walls[::3]), 3))
        start = rb.Pose(2.0 * 1.04, 23.0, [3.4, -0.7, 0.6], L)
        tree = cKDTree(walls)
        coarse = rb.similarity_icp(src, walls, tree, start, iterations=30, max_distance=1.5)
        normals = np.zeros_like(walls); k = 0
        for n_, v in ((4000, [0, 1, 0]), (4000, [0, 1, 0]), (2000, [1, 0, 0]), (2000, [1, 0, 0]), (4000, [0, 0, 1]), (4000, [0, 0, 1]),
                      (1500, [1, 0, 0]), (1500, [1, 0, 0]), (1500, [1, 0, 0])):
            normals[k:k + n_] = v; k += n_
        out = rb.similarity_icp(src, walls, tree, coarse, iterations=60, max_distance=0.6, fit_scale=True, normals=normals)
        self.assertAlmostEqual(out.yaw, 20.0, delta=0.2); self.assertAlmostEqual(out.s, 2.0, delta=0.01)
        np.testing.assert_allclose(out.t, true.t, atol=0.05)


class VisibilityTests(unittest.TestCase):
    def test_wall_between_camera_and_point_blocks_the_sight_line(self):
        segs = np.array([[[5.0, -10.0], [5.0, 10.0]]])          # plan wall x = 5 (viewer x, z)
        ctx = {'wallDT': {'L1': rb.wall_raster(segs), 'L2': None, 'L3': None}}
        self.assertLess(rb.wall_lookup(ctx['wallDT']['L1'], np.array([[5.0, 0.0]]))[0], 0.11)
        # one camera at viewer (0, 7, 0) (Level 1 height), points in E57 axes: viewer [x, y, z] = E57 [x, z, -y]
        m = {'C': np.array([[0.0, 0.0, 7.0]]), 'P': np.array([[3.0, 0.0, 6.0], [8.0, 0.0, 6.0]]),
             'obs_ptr': np.array([0, 1, 2]), 'obs_idx': np.array([0, 0])}
        pose = rb.Pose(1.0, 0.0, [0, 0, 0], np.eye(3))
        f, n = rb.free_ray_fraction(pose, m, ctx, 2.0)
        self.assertEqual(n, 2); self.assertAlmostEqual(f, 0.5)
        m2 = dict(m, P=np.array([[3.0, 0.0, 6.0], [4.0, 1.0, 6.0]]))
        self.assertEqual(rb.free_ray_fraction(pose, m2, ctx, 2.0)[0], 1.0)


class PackageAndCompareTests(unittest.TestCase):
    def test_floor_of_station(self):
        self.assertEqual(rb.floor_of_station('L1', 5.25), 'L1')
        self.assertEqual(rb.floor_of_station('L3', 14.39), 'L3')
        self.assertEqual(rb.floor_of_station('stairs', 7.3), 'L2')       # flight between L1 and L2 goes with L2
        self.assertEqual(rb.floor_of_station('stairs', 12.0), 'L3')

    def test_compare_placements(self):
        R = rz(10.0)
        stations = [{'frame': 5, 'model': 1, 'level': 'L2', 'positionBIM': [1.0, 11.0, 2.0], 'worldFromPanoE57': R.tolist()},
                    {'frame': 9, 'model': 1, 'level': 'L2', 'positionBIM': [0.0, 0.0, 0.0], 'worldFromPanoE57': R.tolist()}]
        ref = {5: (np.array([1.0, 11.0, 2.3]), rz(7.0), 'L2')}
        rows = rb.compare_placements(stations, ref)
        self.assertEqual(len(rows), 1); self.assertAlmostEqual(rows[0]['distanceMetres'], 0.3); self.assertAlmostEqual(rows[0]['headingDegrees'], 3.0)


class RunnerPlanTests(unittest.TestCase):
    def test_time_lapse_plan_matches_the_oct18_settings(self):
        rec = {'frames': 463, 'audio': False, 'playbackSeconds': 15.45, 'realSecondsFromNameAndMtime': 233.0}
        p = cuf.frame_plan(rec)
        self.assertAlmostEqual(p['framesPerRealSecond'], 463 / 233, places=6)
        self.assertEqual((p['maxGap'], p['minGap']), (6, 2)); self.assertTrue(140 <= p['count'] <= 160)

    def test_time_lapse_with_copied_mtime_falls_back_to_half_second(self):
        rec = {'frames': 900, 'audio': False, 'playbackSeconds': 30.0, 'realSecondsFromNameAndMtime': 86400.0 * 3}
        p = cuf.frame_plan(rec)
        self.assertEqual(p['framesPerRealSecond'], 2.0); self.assertEqual(p['count'], 300)

    def test_normal_video_plan(self):
        rec = {'frames': 18000, 'audio': True, 'playbackSeconds': 600.6, 'realSecondsFromNameAndMtime': 601.0}
        p = cuf.frame_plan(rec)
        self.assertAlmostEqual(p['framesPerRealSecond'], 29.97, delta=0.01)
        self.assertEqual(p['maxGap'], 90); self.assertEqual(p['minGap'], 30); self.assertEqual(p['count'], 400)

    def test_insv_tag(self):
        self.assertEqual(cuf.insv_tag('/x/VID_20261018_153400_00_477.insv'), '477')


if __name__ == '__main__':
    unittest.main()
