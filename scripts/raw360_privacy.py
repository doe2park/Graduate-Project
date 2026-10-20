"""Privacy step for the local raw 360 pipeline: blur faces and whole people in equirect panoramas.

Equirect images distort people, so detection runs on several perspective crops (horizon ring, up, down, and a
lower ring that sees the camera operator at the nadir). Detections are mapped back to the panorama as exact
inverse-projected regions (no seam problem), blurred, and also written as per-image SfM feature masks.

NOT a guarantee: detectors miss people (small, occluded, partly visible, seam artefacts, odd poses). A human must
review every output before anything is published. See docs/RAW360_PIPELINE.md.

Pure NumPy/Pillow helpers here are tested without a model. OpenCV (cv2) is imported lazily and only needed by the
YuNet / YOLOX detector classes.
"""
import hashlib, json, math, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

import raw360_core as core

SCHEMA = 'raw360-privacy/1'
DISCLAIMER = ('Automatic detection is not 100% complete. Manual review of every image is required before publishing; '
              'flagged images need extra attention. Do not describe the output as fully anonymised.')

# (name, yaw_deg, pitch_deg, hfov_deg). Horizon ring of 6, straight up, straight down, lower ring of 3 (operator/stick).
DEFAULT_VIEWS = (
    [(f'h{y:03d}', y, 0.0, 100.0) for y in range(0, 360, 60)]
    + [('up', 0.0, 90.0, 110.0), ('down', 0.0, -90.0, 120.0)]
    + [(f'low{y:03d}', y, -50.0, 100.0) for y in (0, 120, 240)]
)
FACE_MARGIN = 0.5      # fraction of box size added on each side
PERSON_MARGIN = 0.15
KINDS = ('face', 'person')


# ---------------------------------------------------------------- geometry (no model needed)

def view_rotation(yaw_deg, pitch_deg):
    return core.cam_from_pano(yaw_deg, pitch_deg)


def view_focal(size, hfov_deg):
    return size / 2 / math.tan(math.radians(hfov_deg) / 2)


def render_crop(img, view, size):
    """Perspective crop (HxWx3 uint8) of an equirect image for view=(name, yaw, pitch, hfov)."""
    _, yaw, pitch, fov = view
    h, w = img.shape[:2]
    mx, my, _ = core.pinhole_maps(view_rotation(yaw, pitch), size, fov, w, h)
    return np.clip(core.remap_bilinear(img, mx, my), 0, 255).astype(np.uint8)


def crop_px_to_dir(view, size, px, py):
    """Pixels of a view's crop -> unit directions in the panorama frame (Nx3)."""
    _, yaw, pitch, fov = view
    f = view_focal(size, fov); c = (size - 1) / 2
    rays = np.stack([(np.asarray(px, float) - c) / f, (np.asarray(py, float) - c) / f, np.ones(np.shape(px))], -1)
    d = rays @ view_rotation(yaw, pitch)
    return d / np.linalg.norm(d, axis=-1, keepdims=True)


def dir_to_crop_px(view, size, d):
    """Panorama directions (Nx3) -> (px, py, in_front) in a view's crop."""
    _, yaw, pitch, fov = view
    f = view_focal(size, fov); c = (size - 1) / 2
    cam = np.asarray(d, float) @ view_rotation(yaw, pitch).T
    z = cam[..., 2]
    safe = np.where(z > 1e-9, z, 1.0)
    return f * cam[..., 0] / safe + c, f * cam[..., 1] / safe + c, z > 1e-9


def expand_box(box, margin, size, min_px=4.0):
    """Expand (x, y, w, h) by margin*size each side (at least min_px); clip to the crop."""
    x, y, w, h = box
    mx, my = max(margin * w, min_px), max(margin * h, min_px)
    x0, y0, x1, y1 = max(0.0, x - mx), max(0.0, y - my), min(size - 1.0, x + w + mx), min(size - 1.0, y + h + my)
    return (x0, y0, x1 - x0, y1 - y0)


def box_to_equirect_boxes(view, size, box, eq_w, eq_h, samples=24):
    """Back-project a crop box to axis-aligned equirect pixel boxes [(x0, y0, x1, y1), ...].

    A box that straddles the +-180 degree seam is split in two. A box containing a pole direction spans the whole
    width down/up to the pole. Boxes are bounding rectangles of the projected box outline (conservative)."""
    x, y, w, h = box
    t = np.linspace(0, 1, samples)
    px = np.concatenate([x + w * t, np.full(samples, x + w), x + w * t, np.full(samples, x)])
    py = np.concatenate([np.full(samples, y), y + h * t, np.full(samples, y + h), y + h * t])
    d = crop_px_to_dir(view, size, px, py)
    az = np.arctan2(d[:, 1], d[:, 0]); el = np.arcsin(np.clip(d[:, 2], -1, 1))
    for sign in (1, -1):  # pole inside the box?
        ppx, ppy, front = dir_to_crop_px(view, size, np.array([[0.0, 0.0, float(sign)]]))
        if front[0] and x <= ppx[0] <= x + w and y <= ppy[0] <= y + h:
            e = el.max() if sign > 0 else el.min()
            y_pole = 0.0 if sign > 0 else eq_h - 1.0
            y_edge = (0.5 - e / math.pi) * eq_h - 0.5
            return [(0.0, min(y_pole, y_edge), eq_w - 1.0, max(y_pole, y_edge))]
    centre = math.atan2(np.sin(az).mean(), np.cos(az).mean())
    rel = (az - centre + math.pi) % (2 * math.pi) - math.pi   # unwrapped around the box centre
    lo, hi = centre + rel.min(), centre + rel.max()           # azimuth extent, may leave [-pi, pi]
    y0 = (0.5 - el.max() / math.pi) * eq_h - 0.5; y1 = (0.5 - el.min() / math.pi) * eq_h - 0.5
    def xp(a):
        return (1 - a / math.pi) / 2 * eq_w - 0.5
    out = []
    for a0, a1 in ((lo, hi),):
        if a1 > math.pi:        # crosses +180: part at the left edge of the image
            out += [(xp(math.pi), y0, xp(a0), y1), (xp(-math.pi), y0, xp(a1 - 2 * math.pi), y1)]
        elif a0 < -math.pi:     # crosses -180: part at the right edge
            out += [(xp(a1), y0, xp(-math.pi), y1), (xp(a0 + 2 * math.pi), y0, xp(math.pi), y1)]
        else:
            out.append((xp(a1), y0, xp(a0), y1))
    res = []
    for x0, ya, x1, yb in out:
        res.append((max(0.0, min(x0, x1)), max(0.0, ya), min(eq_w - 1.0, max(x0, x1)), min(eq_h - 1.0, yb)))
    return res


_DIR_CACHE = {}


def _mask_dirs(mw, mh):
    k = (mw, mh)
    if k not in _DIR_CACHE:
        _DIR_CACHE.clear(); _DIR_CACHE[k] = core.equirect_dirs(mw, mh).astype(np.float32)
    return _DIR_CACHE[k]


def region_mask(view, size, box, mask_w, mask_h):
    """Bool equirect mask (mask_h x mask_w): exactly the panorama pixels that project into `box` of the view crop.
    Computed by inverse mapping, so it is seam- and pole-safe."""
    d = _mask_dirs(mask_w, mask_h)
    px, py, front = dir_to_crop_px(view, size, d)
    x, y, w, h = box
    return front & (px >= x) & (px <= x + w) & (py >= y) & (py <= y + h)


def box_direction(view, size, box):
    """Unit direction (panorama frame) of the box centre, and its angular size in degrees (max of w/h)."""
    x, y, w, h = box
    d = crop_px_to_dir(view, size, np.array([x + w / 2]), np.array([y + h / 2]))[0]
    f = view_focal(size, view[3])
    return d, math.degrees(2 * math.atan(max(w, h) / 2 / f))


def elevation_deg(d):
    return math.degrees(math.asin(max(-1.0, min(1.0, float(d[2])))))


# ---------------------------------------------------------------- blur

def blur_masked(img, mask, sigma=None, pixelate=True):
    """Blur img (HxWx3 uint8) only where mask (bool, any equirect resolution) is True; pixels outside are untouched.

    Strong Gaussian (sigma ~ 30% of the region's short side, min 6 px) plus optional pixelation. A region touching
    both left and right image edges is processed on a half-width-rolled copy so it is one piece."""
    h, w = img.shape[:2]
    out = img.copy()
    if mask is None or not mask.any():
        return out
    m = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize((w, h), Image.NEAREST)) > 127 if mask.shape != (h, w) else mask
    roll = bool(m[:, 0].any() and m[:, -1].any())
    if roll:
        out = np.roll(out, w // 2, axis=1); m = np.roll(m, w // 2, axis=1)
    ys, xs = np.where(m)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    s = float(sigma if sigma is not None else max(6.0, 0.3 * min(int(y1 - y0), int(x1 - x0))))
    pad = int(3 * s) + 2
    ya, yb, xa, xb = max(0, y0 - pad), min(h, y1 + pad), max(0, x0 - pad), min(w, x1 + pad)
    tile = Image.fromarray(out[ya:yb, xa:xb])
    if pixelate:
        cell = max(4, int(s * 0.8))
        small = tile.resize((max(1, tile.width // cell), max(1, tile.height // cell)), Image.BILINEAR)
        tile = small.resize(tile.size, Image.NEAREST)
    tile = np.asarray(tile.filter(ImageFilter.GaussianBlur(s)))
    sub = m[ya:yb, xa:xb]
    out[ya:yb, xa:xb][sub] = tile[sub]
    return np.roll(out, -(w // 2), axis=1) if roll else out


# ---------------------------------------------------------------- detectors (need cv2 + model files)

def _cv2():
    try:
        import cv2
    except ImportError as e:
        raise SystemExit('privacy needs OpenCV: work/raw360-venv/bin/pip install opencv-python-headless') from e
    return cv2


def file_info(path):
    p = Path(path); h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''):
            h.update(c)
    return {'file': p.name, 'bytes': p.stat().st_size, 'sha256': h.hexdigest()}


class YuNetFaces:
    """OpenCV Zoo YuNet face detector (MIT). detect(bgr) -> [(x, y, w, h, score)]."""
    kind = 'face'

    def __init__(self, model, score=0.6, nms=0.3):
        self.cv2 = _cv2(); self.model, self.score, self.nms = str(model), score, nms
        self.det = self.cv2.FaceDetectorYN.create(self.model, '', (320, 320), score, nms, 5000)

    def detect(self, bgr):
        h, w = bgr.shape[:2]; self.det.setInputSize((w, h))
        _, faces = self.det.detect(bgr)
        return [] if faces is None else [(float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])) for f in faces]


class YoloxPersons:
    """OpenCV Zoo YOLOX (Apache-2.0), COCO class 0 'person'. detect(bgr) -> [(x, y, w, h, score)]."""
    kind = 'person'

    def __init__(self, model, score=0.4, nms=0.5, size=640):
        self.cv2 = _cv2(); self.net = self.cv2.dnn.readNet(str(model)); self.score, self.nms, self.size = score, nms, size
        strides = (8, 16, 32); grids, exps = [], []
        for s in strides:
            n = size // s; gx, gy = np.meshgrid(np.arange(n), np.arange(n))
            grids.append(np.stack([gx, gy], -1).reshape(-1, 2)); exps.append(np.full((n * n, 1), s))
        self.grid = np.concatenate(grids).astype(np.float32); self.stride = np.concatenate(exps).astype(np.float32)

    def detect(self, bgr):
        cv2 = self.cv2; h, w = bgr.shape[:2]; r = min(self.size / h, self.size / w)
        canvas = np.full((self.size, self.size, 3), 114, np.uint8)
        canvas[:int(h * r), :int(w * r)] = cv2.resize(bgr, (int(w * r), int(h * r)), interpolation=cv2.INTER_LINEAR)
        self.net.setInput(canvas.transpose(2, 0, 1)[None].astype(np.float32))
        o = self.net.forward()[0]
        xy = (o[:, :2] + self.grid) * self.stride; wh = np.exp(o[:, 2:4]) * self.stride
        sc = o[:, 4] * o[:, 5]            # objectness * class 0 (person)
        keep = sc >= self.score
        if not keep.any():
            return []
        boxes = np.c_[xy[keep] - wh[keep] / 2, wh[keep]] / r
        idx = cv2.dnn.NMSBoxes(boxes.tolist(), sc[keep].tolist(), self.score, self.nms)
        return [(float(boxes[i][0]), float(boxes[i][1]), float(boxes[i][2]), float(boxes[i][3]), float(sc[keep][i])) for i in np.array(idx).reshape(-1)]


# ---------------------------------------------------------------- per-image processing

# A real face, even the operator's just under the camera, spans well under this angle in the panorama.
MAX_FACE_DEG = 25.0


def detect_panorama(img_rgb, detectors, views=DEFAULT_VIEWS, crop=1024):
    """Run each detector on every perspective crop. Returns detections:
    {kind, view, boxCrop (x,y,w,h), score, dir (pano unit vector), elevationDeg, angularSizeDeg}."""
    dets = []
    for view in views:
        bgr = np.ascontiguousarray(render_crop(img_rgb, view, crop)[:, :, ::-1])
        for det in detectors:
            for (x, y, w, h, s) in det.detect(bgr):
                d, ang = box_direction(view, crop, (x, y, w, h))
                if det.kind == 'face' and ang > MAX_FACE_DEG:
                    continue  # a 'face' spanning tens of degrees is a false positive (ceiling arcs, seat rows)
                dets.append({'kind': det.kind, 'view': view, 'boxCrop': (x, y, w, h), 'score': float(s), 'dir': d,
                             'elevationDeg': elevation_deg(d), 'angularSizeDeg': ang})
    return dets


def unique_count(dets, kind, merge_deg=None):
    """Approximate distinct objects: greedy merge of detections whose centres are close on the sphere."""
    thr = merge_deg or (8.0 if kind == 'face' else 15.0)
    kept = []
    for d in sorted((d for d in dets if d['kind'] == kind), key=lambda d: -d['score']):
        if all(math.degrees(math.acos(max(-1, min(1, float(d['dir'] @ k['dir']))))) > thr for k in kept):
            kept.append(d)
    return kept


def build_masks(dets, eq_w, eq_h, crop=1024, mask_scale=2, always_nadir_deg=0.0):
    """Returns (blur_masks list of bool arrays (one per detection), union bool mask) at width eq_w // mask_scale."""
    mw, mh = eq_w // mask_scale, eq_h // mask_scale
    masks = []
    for d in dets:
        box = expand_box(d['boxCrop'], FACE_MARGIN if d['kind'] == 'face' else PERSON_MARGIN, crop)
        masks.append(region_mask(d['view'], crop, box, mw, mh))
    union = np.zeros((mh, mw), bool)
    for m in masks:
        union |= m
    if always_nadir_deg > 0:
        union |= ~core.nadir_mask(mw, mh, always_nadir_deg)
    return masks, union


def apply_privacy(img_rgb, masks, union):
    """Blur each detection region with a sigma sized to that region, then the always-blur remainder."""
    out = img_rgb
    for m in masks:
        out = blur_masked(out, m)
    extra = union.copy()
    for m in masks:
        extra &= ~m
    if extra.any():
        out = blur_masked(out, extra)
    return out


def is_nadir_covered(dets, nadir_flag_deg):
    """True when some detection (face or person) lies below -nadir_flag_deg elevation, i.e. where the operator stands."""
    return any(d['elevationDeg'] < -nadir_flag_deg for d in dets)


def process_image(path, out_path, mask_path, detectors, views=DEFAULT_VIEWS, crop=1024, nadir_flag_deg=50.0,
                  always_nadir_deg=0.0, min_score=None):
    img = np.asarray(Image.open(path).convert('RGB'))
    h, w = img.shape[:2]
    dets = detect_panorama(img, detectors, views, crop)
    masks, union = build_masks(dets, w, h, crop, always_nadir_deg=always_nadir_deg)
    out = apply_privacy(img, masks, union)
    Image.fromarray(out).save(out_path, quality=92) if str(out_path).lower().endswith(('.jpg', '.jpeg')) else Image.fromarray(out).save(out_path)
    if mask_path:  # SfM feature mask: white = keep, black = person/face (+ always-blur zone)
        Image.fromarray((~union * 255).astype(np.uint8)).save(mask_path)
    faces, persons = unique_count(dets, 'face'), unique_count(dets, 'person')
    covered = is_nadir_covered(dets, nadir_flag_deg)
    flags = [] if covered or always_nadir_deg >= nadir_flag_deg else [f'no face/person detected below -{nadir_flag_deg:g} deg elevation (operator at the nadir may be missed)']
    return {'file': Path(path).name, 'width': w, 'height': h,
            'rawDetections': {k: sum(1 for d in dets if d['kind'] == k) for k in KINDS},
            'uniqueApprox': {'face': len(faces), 'person': len(persons)},
            'nadirDetected': covered,
            'detections': [{'kind': d['kind'], 'view': d['view'][0], 'score': round(d['score'], 3),
                            'elevationDeg': round(d['elevationDeg'], 1), 'azimuthDeg': round(math.degrees(math.atan2(d['dir'][1], d['dir'][0])), 1),
                            'angularSizeDeg': round(d['angularSizeDeg'], 1)} for d in dets],
            'blurredPixelFraction': round(float(union.mean()), 5),
            'flaggedForManualReview': bool(flags), 'flags': flags}


def make_report(per_image, models, params, seconds):
    n = len(per_image)
    return {'schema': SCHEMA, 'disclaimer': DISCLAIMER, 'manualReviewRequired': True,
            'imagesProcessed': n,
            'totals': {'rawFaceDetections': sum(i['rawDetections']['face'] for i in per_image),
                       'rawPersonDetections': sum(i['rawDetections']['person'] for i in per_image),
                       'uniqueFacesApprox': sum(i['uniqueApprox']['face'] for i in per_image),
                       'uniquePersonsApprox': sum(i['uniqueApprox']['person'] for i in per_image),
                       'imagesWithAnyDetection': sum(1 for i in per_image if i['rawDetections']['face'] + i['rawDetections']['person']),
                       'imagesFlaggedForManualReview': sum(1 for i in per_image if i['flaggedForManualReview'])},
            'flaggedImages': [i['file'] for i in per_image if i['flaggedForManualReview']],
            'params': params, 'models': models, 'runtimeSeconds': round(seconds, 1), 'images': per_image}


def run(a, detectors=None, models=None):
    """CLI entry (args from raw360_pipeline.py `privacy`)."""
    src, dst = Path(a.input), Path(a.out)
    if src.resolve() == dst.resolve():
        raise SystemExit('--out must differ from --in (originals are never overwritten)')
    files = sorted(p for p in src.iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png'))
    if a.max_images:
        files = files[:a.max_images]
    if not files:
        raise SystemExit(f'no images in {src}')
    if detectors is None:
        models, detectors = {}, []
        if a.face_model:
            detectors.append(YuNetFaces(a.face_model, a.face_score)); models['face'] = file_info(a.face_model)
        if a.person_model:
            detectors.append(YoloxPersons(a.person_model, a.person_score)); models['person'] = file_info(a.person_model)
        if not detectors:
            raise SystemExit('give --face-model and/or --person-model (see docs/RAW360_PIPELINE.md, Privacy step)')
    dst.mkdir(parents=True, exist_ok=True)
    mdir = Path(a.masks_out) if a.masks_out else None
    if mdir:
        mdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); per = []
    for p in files:
        per.append(process_image(p, dst / p.name, (mdir / (p.stem + '.png')) if mdir else None, detectors, crop=a.crop,
                                 nadir_flag_deg=a.nadir_flag_deg, always_nadir_deg=a.always_blur_nadir_deg))
        print(f'{p.name}: faces~{per[-1]["uniqueApprox"]["face"]} persons~{per[-1]["uniqueApprox"]["person"]}' + ('  FLAG' if per[-1]['flaggedForManualReview'] else ''), flush=True)
    params = {'input': str(src), 'out': str(dst), 'masksOut': str(mdir) if mdir else None, 'crop': a.crop, 'views': [list(v) for v in DEFAULT_VIEWS],
              'faceMargin': FACE_MARGIN, 'personMargin': PERSON_MARGIN, 'nadirFlagDeg': a.nadir_flag_deg,
              'alwaysBlurNadirDeg': a.always_blur_nadir_deg, 'faceScore': a.face_score, 'personScore': a.person_score}
    rep = make_report(per, models, params, time.time() - t0)
    (dst / 'privacy-report.json').write_text(core.dumps(rep))
    # blurred copy stays importable: carry images.json (new sha256) and provenance if present
    ij = src / 'images.json'
    if ij.exists():
        doc = json.loads(ij.read_text()); names = {p.name for p in files}
        doc['images'] = [r for r in doc['images'] if all(rep_['file'] in names for rep_ in r['representations'])]
        for r in doc['images']:
            for rep_ in r['representations']:
                rep_['sha256'] = file_info(dst / rep_['file'])['sha256']
        doc['privacy'] = {'schema': SCHEMA, 'status': 'automatic blur applied; manual review required before publishing', 'report': 'privacy-report.json'}
        (dst / 'images.json').write_text(core.dumps(doc))
    print(json.dumps(rep['totals']), f'flagged: {rep["flaggedImages"]}', f'{rep["runtimeSeconds"]} s')
    return rep
