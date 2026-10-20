import importlib.util, json, math, sys, tempfile, unittest, argparse
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import raw360_core as core  # noqa: E402
import raw360_privacy as pv  # noqa: E402

W, H = 1024, 512
SIZE = 256


def yaw_view(yaw, pitch=0.0, fov=100.0):
    return ('t', yaw, pitch, fov)


class BrightSquareDetector:
    """Test double: 'detects' pixels brighter than 250 in the crop and returns their bounding box."""
    def __init__(self, kind='person'):
        self.kind = kind

    def detect(self, bgr):
        ys, xs = np.where(bgr[:, :, 0] > 250)
        if len(xs) < 20:
            return []
        return [(float(xs.min()), float(ys.min()), float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1), 0.9)]


def pano_with_blob(az_deg, el_deg, radius_deg=6.0, noise_seed=0):
    rng = np.random.default_rng(noise_seed)
    img = rng.integers(0, 200, (H, W, 3), dtype=np.uint8)
    d = core.equirect_dirs(W, H)
    c = np.array([math.cos(math.radians(el_deg)) * math.cos(math.radians(az_deg)),
                  math.cos(math.radians(el_deg)) * math.sin(math.radians(az_deg)), math.sin(math.radians(el_deg))])
    ang = np.degrees(np.arccos(np.clip(d @ c, -1, 1)))
    blob = ang < radius_deg
    img[blob] = 255
    return img, blob


class GeometryTests(unittest.TestCase):
    def test_crop_equirect_round_trip(self):
        for view in [yaw_view(0), yaw_view(135, 20), yaw_view(-170), ('up', 0, 90, 110), ('down', 0, -90, 120), yaw_view(60, -50)]:
            px, py = np.meshgrid(np.linspace(20, SIZE - 20, 7), np.linspace(20, SIZE - 20, 7))
            d = pv.crop_px_to_dir(view, SIZE, px.ravel(), py.ravel())
            bx, by, front = pv.dir_to_crop_px(view, SIZE, d)
            self.assertTrue(front.all())
            self.assertTrue(np.allclose(bx, px.ravel(), atol=1e-6) and np.allclose(by, py.ravel(), atol=1e-6), view)
            # and through the equirect pixel grid used by core
            ex, ey = core.dir_to_equirect_px(d, W, H)
            d2 = core.equirect_dirs(W, H)[np.clip(np.round(ey).astype(int), 0, H - 1), np.round(ex).astype(int) % W]
            self.assertLess(np.degrees(np.arccos(np.clip((d * d2).sum(1), -1, 1))).max(), 1.0)

    def test_box_back_projection_across_seam(self):
        # view centred on the seam (az = 180): box covering the middle must split into two equirect boxes at both edges
        view = yaw_view(180)
        boxes = pv.box_to_equirect_boxes(view, SIZE, (96, 96, 64, 64), W, H)
        self.assertEqual(len(boxes), 2)
        left = min(boxes, key=lambda b: b[0]); right = max(boxes, key=lambda b: b[0])
        self.assertAlmostEqual(left[0], 0.0, delta=1.0); self.assertAlmostEqual(right[2], W - 1.0, delta=1.0)
        self.assertLess(left[2], W / 4); self.assertGreater(right[0], 3 * W / 4)
        # a box away from the seam stays whole and centred where expected (yaw 0 -> image centre)
        one = pv.box_to_equirect_boxes(yaw_view(0), SIZE, (96, 96, 64, 64), W, H)
        self.assertEqual(len(one), 1)
        self.assertAlmostEqual((one[0][0] + one[0][2]) / 2, W / 2, delta=3.0)

    def test_box_containing_pole_spans_full_width(self):
        boxes = pv.box_to_equirect_boxes(('down', 0, -90, 120), SIZE, (80, 80, 96, 96), W, H)
        self.assertEqual(len(boxes), 1)
        self.assertEqual((boxes[0][0], boxes[0][2]), (0.0, W - 1.0)); self.assertAlmostEqual(boxes[0][3], H - 1.0, delta=1)

    def test_region_mask_matches_projection_and_wraps(self):
        view = yaw_view(180)
        m = pv.region_mask(view, SIZE, (96, 96, 64, 64), W // 2, H // 2)
        cols = np.where(m.any(0))[0]
        self.assertTrue(cols.min() == 0 and cols.max() == W // 2 - 1)      # touches both edges
        self.assertFalse(m[:, W // 8: 3 * W // 8].any() or m[:, 5 * W // 8: 7 * W // 8].any())
        self.assertTrue(m[H // 4, 1] and m[H // 4, W // 2 - 2])           # the centre of the box is at the seam


class BlurTests(unittest.TestCase):
    def test_blur_only_inside_mask(self):
        rng = np.random.default_rng(1)
        img = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)
        mask = np.zeros((H, W), bool); mask[100:200, 300:420] = True
        out = pv.blur_masked(img, mask)
        self.assertTrue(np.array_equal(out[~mask], img[~mask]))
        self.assertGreater(np.abs(out[mask].astype(int) - img[mask].astype(int)).mean(), 20)
        self.assertLess(out[mask].std(), img[mask].std() * 0.6)             # detail is gone

    def test_blur_mask_wrapping_seam_and_halfres_mask(self):
        rng = np.random.default_rng(2)
        img = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)
        mask = np.zeros((H // 2, W // 2), bool); mask[60:120, :20] = True; mask[60:120, -20:] = True
        out = pv.blur_masked(img, mask)
        full = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize((W, H), Image.NEAREST)) > 127
        self.assertTrue(np.array_equal(out[~full], img[~full]))
        self.assertGreater(np.abs(out[full].astype(int) - img[full].astype(int)).mean(), 20)

    def test_empty_mask_is_identity(self):
        img = np.random.default_rng(3).integers(0, 256, (64, 64, 3), dtype=np.uint8)
        self.assertTrue(np.array_equal(pv.blur_masked(img, np.zeros((64, 64), bool)), img))


class EndToEndTests(unittest.TestCase):
    def run_one(self, az, el):
        img, blob = pano_with_blob(az, el)
        with tempfile.TemporaryDirectory() as t:
            t = Path(t); src = t / 'in'; src.mkdir(); Image.fromarray(img).save(src / 'a.png')
            rec = pv.process_image(src / 'a.png', t / 'out.png', t / 'mask.png', [BrightSquareDetector()], crop=SIZE, nadir_flag_deg=50)
            out = np.asarray(Image.open(t / 'out.png')); mask = np.asarray(Image.open(t / 'mask.png'))
        return img, blob, out, mask, rec

    def test_blob_is_blurred_and_far_pixels_untouched(self):
        for az, el in [(0, 0), (180, 5), (-90, 20), (45, -60)]:
            img, blob, out, mask, rec = self.run_one(az, el)
            self.assertEqual(rec['uniqueApprox']['person'], 1, (az, el))
            self.assertGreater(rec['rawDetections']['person'], 0)
            self.assertLess(out[blob].mean(), 250, (az, el))                  # white blob smeared into the noise
            # mask: black over the blob (at half res), white far away; far pixels identical to the input
            mblob = np.asarray(Image.fromarray(blob.astype(np.uint8) * 255).resize(mask.shape[::-1], Image.NEAREST)) > 127
            self.assertLess(mask[mblob].mean() / 255, 0.02, (az, el))
            self.assertEqual(rec['flaggedForManualReview'], not rec['nadirDetected'])
            changed = np.any(out != img, axis=2)
            self.assertLess(changed.mean(), 0.2)

    def test_nadir_flag(self):
        _, _, _, _, high = self.run_one(0, 10)
        _, _, _, _, low = self.run_one(45, -75)
        self.assertTrue(high['flaggedForManualReview']); self.assertFalse(high['nadirDetected'])
        self.assertTrue(low['nadirDetected']); self.assertFalse(low['flaggedForManualReview'])

    def test_report_shape(self):
        per = [self.run_one(0, 10)[4], self.run_one(10, -70)[4]]
        rep = pv.make_report(per, {'face': {'file': 'x.onnx', 'bytes': 1, 'sha256': '0'}}, {}, 1.23)
        for k in ['schema', 'disclaimer', 'manualReviewRequired', 'imagesProcessed', 'totals', 'flaggedImages', 'params', 'models', 'runtimeSeconds', 'images']:
            self.assertIn(k, rep)
        self.assertTrue(rep['manualReviewRequired']); self.assertIn('Manual review', rep['disclaimer'])
        self.assertNotIn('100%', rep['disclaimer'].replace('not 100%', ''))
        self.assertEqual(rep['imagesProcessed'], 2); self.assertEqual(len(rep['flaggedImages']), 1)
        self.assertEqual(rep['totals']['imagesFlaggedForManualReview'], 1)
        for rec in rep['images']:
            for k in ['file', 'rawDetections', 'uniqueApprox', 'nadirDetected', 'detections', 'flaggedForManualReview', 'flags', 'blurredPixelFraction']:
                self.assertIn(k, rec)
        json.dumps(rep)

    def test_run_refuses_to_overwrite_inputs(self):
        with tempfile.TemporaryDirectory() as t:
            a = argparse.Namespace(input=t, out=t, max_images=None, masks_out=None, face_model=None, person_model=None)
            with self.assertRaises(SystemExit):
                pv.run(a, detectors=[BrightSquareDetector()], models={})


if __name__ == '__main__':
    unittest.main()
