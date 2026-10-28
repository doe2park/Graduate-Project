"""Cupix-free placement of raw Insta360 SfM submodels in the Grimes BIM viewer frame, per-floor packages, validation.

Chain (each step writes JSON under the raw360 work folder; nothing is overwritten silently, raw inputs are read only):

    dump     (raw360 venv: pycolmap)  every SfM submodel -> sfm/<method>/submodels/model-<id>.npz (poses + points)
    anchor   (raw360 venv: OpenCV)    optional: SIFT links of submodel panoramas to already-registered Level 1
                                      panoramas (scan-assets) -> anchors.json (yaw + position seeds per submodel)
    place    (system python: SciPy)   per submodel: level by the panoramas' up axis, metric scale from the camera
                                      height above the local floor, coarse pose by a global yaw + translation search
                                      of the points against BIM floor sections (FFT, every candidate floor) and/or
                                      the Level 1 anchors, yaw+XYZ(+scale) trimmed ICP against BIM surfaces,
                                      independent checks (held-out residual, camera height above the BIM floor ray
                                      cast, stations inside walls, scale vs camera height, ambiguity of the search),
                                      accept/drop per submodel -> placed-bim.json
    package  (system python: Pillow)  per-floor local preview packages capture-local/grimes-L2-<date>/ and -L3-
                                      (stations stored directly in the BIM viewer frame; identity registration)
    compare  (system python)          validation only: per-frame differences to another placement (e.g. the
                                      Cupix-based Oct 18 packages); never used as input to place

    work/raw360-venv/bin/python scripts/raw360_bim.py dump --work W --method strict-incremental
    work/raw360-venv/bin/python scripts/raw360_bim.py anchor --work W --method strict-incremental   # optional
    python3 scripts/raw360_bim.py place --work W --method strict-incremental --camera-height 2.0
    python3 scripts/raw360_bim.py package --work W --method strict-incremental --date 2026-10-28 --blurred <privacy out>
    python3 scripts/raw360_bim.py compare --placed W/placed-bim.json --reference capture-local/grimes-L2-2026-10-18-v2 ...

Frames: SfM worlds are E57-style Z-up (panorama centre +X, left +Y, top +Z). "BIM-E57" = BIM viewer world (Y-up metres)
with E57 axes, i.e. viewer [x, y, z] = BIM-E57 [x, z, -y]. Every result is photogrammetric / ICP consistency against
BIM design surfaces: provisional, NOT surveyed accuracy.
"""
import argparse, datetime, hashlib, json, math, os, shutil, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import raw360_core as core  # noqa: E402

LABEL = 'provisional, not surveyed'
SLAB = {'L1': 5.2, 'L2': 9.4, 'L3': 14.3}          # BIM slab heights, viewer frame (m); as multifloor_review.SLAB
BIM_SOUP = ROOT / 'work/floorplans/arch-struct.f32'
YUP_FROM_E57 = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0.0]])   # viewer [x,y,z] = M @ E57 [x,y,z]
LEVEL1_ANCHOR_PACKAGES = (  # registered Level 1 photo packages: (manifest dir, registration file)
    ('scan-assets/captures/2026-10-18/panoramas', 'scan-assets/captures/2026-10-18/registration.json'),
    ('scan-assets/panoramas', 'alignment-analysis/accepted-registration.json'),
)

DEFAULTS = {  # acceptance thresholds for one submodel (documented in the result)
    'minFrames': 6, 'maxHeldOutMedian': 0.30, 'minHeldOutWithin025': 0.45, 'cameraHeightRange': [1.55, 2.45],
    'maxCameraHeightIQR': 0.30, 'maxStationsInWallsFraction': 0.15, 'maxScaleChange': 0.12, 'ambiguityRatio': 1.15,
    'ambiguityDistance': 2.0, 'ambiguityYaw': 10.0, 'maxSeedShift': 2.0, 'maxSeedYawChange': 6.0,
    'minModelFree': 0.45, 'minSegmentFree': 0.35, 'segmentFreeRatio': 0.5, 'maxFlaggedFraction': 0.4,
}


# ---------------------------------------------------------------- small helpers
def load(p):
    return json.loads(Path(p).read_text())


def save_new(path, obj, overwrite=False):
    path = Path(path)
    if path.exists() and not overwrite:
        raise SystemExit(f'{path} exists; pass --overwrite to replace it')
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(core.dumps(obj))


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def rot_z(rad):
    c, s = math.cos(rad), math.sin(rad)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def to_viewer(p_e57):
    """E57-axes points (N,3) -> viewer Y-up [x, z, -y]."""
    p = np.asarray(p_e57, float).reshape(-1, 3)
    return np.stack([p[:, 0], p[:, 2], -p[:, 1]], 1)


def to_e57(p_viewer):
    p = np.asarray(p_viewer, float).reshape(-1, 3)
    return np.stack([p[:, 0], -p[:, 2], p[:, 1]], 1)


def viewer_yaw_to_e57(rotation_y_degrees):
    """registration_fit viewer yaw a  ==  E57 rotation about +Z by +a (multifloor_review.rotate_e57_quaternion)."""
    return rot_z(math.radians(rotation_y_degrees))


class Pose:
    """BIM-E57 = s * Rz(yaw) * L * sfm + t  (L levels the submodel; yaw about +Z; t in BIM-E57 metres)."""

    def __init__(self, s, yaw_deg, t, L):
        self.s, self.yaw, self.t, self.L = float(s), float(yaw_deg), np.asarray(t, float), np.asarray(L, float)

    @property
    def R(self):
        return rot_z(math.radians(self.yaw)) @ self.L

    def points(self, p):
        return self.s * (np.asarray(p, float).reshape(-1, 3) @ self.R.T) + self.t

    def rotation(self, R_world_from_pano):
        return self.R @ np.asarray(R_world_from_pano, float)

    def asdict(self):
        return {'scale': self.s, 'yawDegrees': self.yaw, 'translationE57': self.t.tolist(), 'levelling': self.L.tolist(),
                'convert': 'BIM-E57 = scale * Rz(yaw) * levelling * sfm + translationE57; viewer [x,y,z] = BIM-E57 [x,z,-y]'}


# ---------------------------------------------------------------- dump (raw360 venv)
def cmd_dump(a):
    import pycolmap, raw360_sfm
    work = Path(a.work); meta = load(work / 'frames.json'); mdir = work / 'sfm' / a.method / 'models'
    if not mdir.is_dir():
        raise SystemExit(f'{mdir} missing: run raw360_pipeline.py sfm first')
    out = work / 'sfm' / a.method / 'submodels'; out.mkdir(exist_ok=True); rows = []
    for d in sorted((x for x in mdir.iterdir() if x.name.isdigit()), key=lambda x: int(x.name)):
        rec = pycolmap.Reconstruction(str(d)); fr = [f for f in raw360_sfm._frame_poses(rec, meta) if f['registered']]
        pts = np.array([[*p.xyz, p.error, p.track.length()] for p in rec.points3D.values()]) if rec.num_points3D() else np.zeros((0, 5))
        # observations: which registered panoramas see each point (CSR: obs_ptr[i]..obs_ptr[i+1] into obs_idx = row in frames)
        row = {f['pano']: k for k, f in enumerate(fr)}; ptr, obs = [0], []
        for p in rec.points3D.values():
            seen = sorted({row.get(rec.images[e.image_id].name.split('/', 1)[-1]) for e in p.track.elements} - {None})
            obs.extend(seen); ptr.append(len(obs))
        np.savez_compressed(out / f'model-{int(d.name)}.npz', frames=np.array([f['frame'] for f in fr], int),
                            panos=np.array([f['pano'] for f in fr]), centres=np.array([f['centre'] for f in fr]).reshape(-1, 3),
                            R=np.array([f['worldFromPano'] for f in fr]).reshape(-1, 3, 3), points=pts,
                            obs_ptr=np.array(ptr, np.int64), obs_idx=np.array(obs, np.int32))
        rows.append({'model': int(d.name), 'frames': len(fr), 'points': int(len(pts)),
                     'frameRange': [min(f['frame'] for f in fr), max(f['frame'] for f in fr)] if fr else None})
    (out / 'index.json').write_text(core.dumps({'schema': 'raw360-submodels/1', 'work': str(work), 'method': a.method, 'models': rows}))
    for r in rows:
        print('model', r['model'], 'frames', r['frames'], 'points', r['points'], 'range', r['frameRange'])


# ---------------------------------------------------------------- photo links (raw360 venv: OpenCV)
def level1_stations(packages=LEVEL1_ANCHOR_PACKAGES, root=ROOT):
    """Registered Level 1 panoramas -> [{key, image, positionE57 (BIM-E57), R (world_from_pano, BIM-E57)}]."""
    import multifloor_review as mr
    out = []
    for pdir, regf in packages:
        pdir = Path(root) / pdir; regf = Path(root) / regf
        if not (pdir / 'manifest.json').exists() or not regf.exists():
            continue
        m = load(pdir / 'manifest.json'); reg = load(regf)
        for s in m['stations']:
            img = pdir / s['file']
            if not img.exists():
                continue
            pos = mr.apply(reg, s['position'])[0]
            out.append({'key': '%s:%s' % (pdir.relative_to(root), s['id']), 'image': str(img), 'positionE57': to_e57(pos)[0].tolist(),
                        'R': (viewer_yaw_to_e57(reg['rotationYDegrees']) @ core.matrix_from_quat(s['e57Quaternion'])).tolist(),
                        'registration': str(regf.relative_to(root)), 'registrationStatus': reg.get('status')})
    return out


def place_descriptor(image_path, cache):
    cache = Path(cache)
    if cache.exists():
        return np.load(cache)
    from PIL import Image
    with Image.open(image_path) as im:
        g = np.asarray(im.convert('L').resize((256, 128), Image.Resampling.BOX))
    d = core.yaw_invariant_descriptor(g[16:112]); cache.parent.mkdir(parents=True, exist_ok=True); np.save(cache, d)
    return d


def cmd_anchor(a):
    """SIFT links (multifloor_link machinery: RootSIFT on 2048x1024 equirects, essential matrix on bearings) of every
    submodel keyframe to (1) registered Level 1 panoramas (appearance-prefiltered top-k) and (2) keyframes of OTHER
    submodels within --bridge-gap frames (bridges across SfM breaks, e.g. stairs). Bearings stay in each panorama's own
    frame; place combines them with the poses. Writes <work>/anchors-<method>.json."""
    import multifloor_link as ml
    work = Path(a.work); models = read_submodels(work, a.method); feat_dir = work / 'anchor-features'
    l1 = level1_stations() if not a.no_level1 else []
    ident = [0.0, 0.0, 0.0, 1.0]
    feats = {}

    def feat(key, image):
        if key not in feats:
            feats[key] = ml.features(image, feat_dir / (key.replace('/', '_').replace(':', '_') + '.npz'), ident)
        return feats[key]

    def pose(ka, ia, kb, ib, iters):
        da, Da = feat(ka, ia); db, Db = feat(kb, ib)
        pr = ml.mutual_ratio_matches(Da, Db)
        if len(pr) < 15:
            return None
        pr = np.array(pr); return ml.relative_pose(da[pr[:, 0]], db[pr[:, 1]], iters=iters)

    kf = [(m['model'], f, m['panos'][i]) for m in models if len(m['frames']) >= 2 for i, f in enumerate(m['frames'])]
    pairs = []
    if l1:
        D1 = np.array([place_descriptor(s['image'], feat_dir / ('desc_' + s['key'].replace('/', '_').replace(':', '_') + '.npy')) for s in l1])
        for k, (mid, f, pano) in enumerate(kf):
            d = place_descriptor(work / 'panos' / pano, feat_dir / ('desc_%s.npy' % pano))
            for j in np.argsort(-(D1 @ d))[:a.level1_topk]:
                s = l1[int(j)]; r = pose(s['key'], s['image'], 'kf_%s' % pano, work / 'panos' / pano, 800)
                if r and r['inliers'] >= a.min_inliers:
                    r = pose(s['key'], s['image'], 'kf_%s' % pano, work / 'panos' / pano, 4000)
                    if r and r['inliers'] >= a.min_inliers:
                        pairs.append({'kind': 'level1', 'a': {'level1': s['key']}, 'b': {'model': mid, 'frame': f}, 'inliers': r['inliers'],
                                      'matches': r['matches'], 'R': r['R'].tolist(), 'direction': r['direction'].tolist(), 'tiltDegrees': ml.tilt_deg(r['R'])})
                        print('level1 link', s['key'], '-> model', mid, 'frame', f, 'inliers', r['inliers'], flush=True)
            if (k + 1) % 25 == 0:
                print('level1 prefilter/verify %d/%d keyframes' % (k + 1, len(kf)), flush=True)
    for i, (ma, fa, pa) in enumerate(kf):
        for mb, fb, pb in kf[i + 1:]:
            if ma == mb or fa == fb or abs(fa - fb) > a.bridge_gap:   # the same frame in two models: shared station (place uses it directly)
                continue
            r = pose('kf_%s' % pa, work / 'panos' / pa, 'kf_%s' % pb, work / 'panos' / pb, 3000)
            if r and r['inliers'] >= a.min_inliers:
                pairs.append({'kind': 'bridge', 'a': {'model': ma, 'frame': fa}, 'b': {'model': mb, 'frame': fb}, 'inliers': r['inliers'],
                              'matches': r['matches'], 'R': r['R'].tolist(), 'direction': r['direction'].tolist(), 'tiltDegrees': ml.tilt_deg(r['R'])})
    print('bridges:', sum(p['kind'] == 'bridge' for p in pairs), 'level1 links:', sum(p['kind'] == 'level1' for p in pairs), flush=True)
    out = {'schema': 'raw360-bim-anchors/1', 'work': str(work), 'method': a.method, 'level1Stations': l1,
           'settings': {'minInliers': a.min_inliers, 'level1TopK': a.level1_topk, 'bridgeGapFrames': a.bridge_gap,
                        'method': 'RootSIFT (multifloor_link.features, elevation > -45 deg) + mutual ratio 0.8 + essential matrix on bearings '
                                  '(8-point RANSAC 0.006 rad); Level 1 candidates prefiltered by a yaw-invariant place descriptor'},
           'pairs': pairs}
    save_new(work / ('anchors-%s.json' % a.method), out, overwrite=True)
    if not a.keep_features:
        shutil.rmtree(feat_dir, ignore_errors=True)   # ~5 MB per panorama; re-made on the next run


# ---------------------------------------------------------------- seed from photo links (pure)
def yaw_of(M):
    return math.degrees(math.atan2(M[1, 0] - M[0, 1], M[0, 0] + M[1, 1]))


def seed_from_links(links, scale, L, cluster_deg=3.0, min_rays=2, min_ray_angle=8.0):
    """links: [{'aPos' (BIM-E57), 'aR' (world_from_pano, BIM-E57), 'bCentre' (SfM units), 'bR' (SfM world_from_pano),
    'R' (pano_b <- pano_a), 'direction' (b seen from a, pano-a frame), 'weight'}].
    world_from_pano_b = aR R^T = Rz(yaw) L bR  ->  yaw per link; consensus = largest cluster within cluster_deg.
    Translation: least squares over rays, Rz L (scale * bCentre) + t on the ray from aPos along aR @ direction.
    Returns {'yaw', 't', 'links used', 'yawSpread', 'rayResiduals', ...} or {'error': ...}."""
    if not links:
        return {'error': 'no links'}
    yaws, tilts = [], []
    for l in links:
        M = np.asarray(l['aR']) @ np.asarray(l['R']).T @ (np.asarray(L) @ np.asarray(l['bR'])).T
        y = yaw_of(M); yaws.append(y); tilts.append(core.rotation_angle_deg(rot_z(math.radians(y)).T @ M))
    yaws = np.array(yaws); w = np.array([l.get('weight', 1.0) for l in links], float)
    support = [w[np.abs(core.wrap_deg(yaws - y)) < cluster_deg].sum() for y in yaws]
    y0 = yaws[int(np.argmax(support))]; use = np.abs(core.wrap_deg(yaws - y0)) < cluster_deg
    yaw = float(y0 + np.average(core.wrap_deg(yaws[use] - y0), weights=w[use]))
    Rz = rot_z(math.radians(yaw)) @ np.asarray(L)
    shared = [l for l, u in zip(links, use) if u and l.get('shared')]
    if shared:   # the same panorama registered in both models: position equality, no ray needed
        ts = np.array([np.asarray(l['aPos']) - scale * Rz @ np.asarray(l['bCentre']) for l in shared]); t = np.median(ts, axis=0)
        res = [{'rangeMetres': 0.0, 'missMetres': float(np.linalg.norm(x - t))} for x in ts]
        return {'yawDegrees': yaw, 'yawSpreadDegrees': float(np.ptp(yaws[use])), 'linksUsed': int(use.sum()), 'linksTotal': len(links),
                'tiltResidualMedianDegrees': float(np.median(np.array(tilts)[use])), 'sharedFrames': len(shared),
                'translationE57': t.tolist(), 'rayResiduals': res, 'missMedianMetres': float(np.median([r['missMetres'] for r in res]))}
    A = np.zeros((3, 3)); bvec = np.zeros(3); dirs = []
    for l, u, wt in zip(links, use, w):
        if not u:
            continue
        d = np.asarray(l['aR']) @ np.asarray(l['direction']); d /= np.linalg.norm(d); dirs.append(d)
        P = np.eye(3) - np.outer(d, d); A += wt * P; bvec += wt * P @ (np.asarray(l['aPos']) - scale * Rz @ np.asarray(l['bCentre']))
    hd = [x[:2] / (np.linalg.norm(x[:2]) + 1e-12) for x in dirs]
    spread = max((math.degrees(math.acos(np.clip(abs(p @ q), -1, 1))) for i, p in enumerate(hd) for q in hd[i + 1:]), default=0.0)
    out = {'yawDegrees': yaw, 'yawSpreadDegrees': float(np.ptp(yaws[use])), 'linksUsed': int(use.sum()), 'linksTotal': len(links),
           'tiltResidualMedianDegrees': float(np.median(np.array(tilts)[use])), 'rayAngleSpreadDegrees': spread}
    if use.sum() < min_rays or spread < min_ray_angle:
        out['error'] = 'need >= %d links with horizontal ray directions >= %.0f deg apart (have %d, %.1f deg)' % (min_rays, min_ray_angle, use.sum(), spread)
        return out
    t = np.linalg.solve(A + 1e-9 * np.eye(3), bvec)
    res = []
    for l, u in zip(links, use):
        if not u:
            continue
        d = np.asarray(l['aR']) @ np.asarray(l['direction']); d /= np.linalg.norm(d); p = scale * Rz @ np.asarray(l['bCentre']) + t
        v = p - np.asarray(l['aPos']); s_ = v @ d; res.append({'rangeMetres': float(s_), 'missMetres': float(np.linalg.norm(v - s_ * d))})
    out.update(translationE57=t.tolist(), rayResiduals=res, missMedianMetres=float(np.median([r['missMetres'] for r in res])))
    return out


def read_submodels(work, method):
    d = Path(work) / 'sfm' / method / 'submodels'
    if not (d / 'index.json').exists():
        raise SystemExit(f'{d}/index.json missing: run "raw360_bim.py dump" with the raw360 venv first')
    out = []
    for r in load(d / 'index.json')['models']:
        z = np.load(d / f"model-{r['model']}.npz")
        out.append({'model': r['model'], 'frames': z['frames'].tolist(), 'panos': [str(x) for x in z['panos']], 'C': z['centres'],
                    'R': z['R'], 'P': z['points'][:, :3], 'err': z['points'][:, 3] if len(z['points']) else np.zeros(0),
                    'obs_ptr': z['obs_ptr'] if 'obs_ptr' in z else None, 'obs_idx': z['obs_idx'] if 'obs_idx' in z else None})
    return out


# ---------------------------------------------------------------- levelling and scale (pure)
def floor_mode(C, Q, radius, log_bin=0.04, smooth=1.5, band=0.15, min_points=8):
    """Camera height above the floor (reconstruction units) as the dominant mode of log(height below camera) of all
    points within `radius` horizontally of any camera, pooled over the submodel. Log bins make it scale-free; the
    lowest-layer rule of raw360_core.floor_distances picks floors seen through atria / stairwells (Oct 18 video 477:
    a 3.4x wrong scale on Level 3), the mode does not. Returns (mode_units, per-station floor distance (NaN when the
    station has fewer than min_points points within +-band in log of the mode), second-mode ratio)."""
    from scipy.ndimage import gaussian_filter1d
    C = np.asarray(C, float); Q = np.asarray(Q, float); per = []
    for c in C:
        rel = Q - c; h = -rel[:, 2]; sel = (np.hypot(rel[:, 0], rel[:, 1]) < radius) & (h > 0)
        per.append(np.log(h[sel]))
    allh = np.concatenate(per) if per else np.zeros(0)
    if len(allh) < 30:
        return None, np.full(len(C), np.nan), None
    med = float(np.median(allh)); edges = np.arange(med - 4, med + 4 + log_bin, log_bin)
    hist = gaussian_filter1d(np.histogram(allh, bins=edges)[0].astype(float), smooth)
    k = int(hist.argmax()); mode = float(edges[k] + log_bin / 2)
    far = np.abs((edges[:-1] + log_bin / 2) - mode) > 0.35
    second = float(hist[far].max() / hist[k]) if far.any() else 0.0
    d = np.array([float(np.exp(np.median(p[np.abs(p - mode) < band]))) if (np.abs(p - mode) < band).sum() >= min_points else np.nan for p in per])
    return float(np.exp(mode)), d, second


def level_and_scale(m, camera_height, radius_factor=2.0):
    """Gravity from the panoramas (camera carried upright), metric scale from the camera height above the floor
    (floor_mode). Returns dict with L, scale, per-station floor distances (units), and diagnostics."""
    R = list(m['R']); C = np.asarray(m['C'], float); P = np.asarray(m['P'], float)
    P = P[np.isfinite(P).all(1)]
    up = core.up_from_panoramas(R); L = core.level_rotation(up)
    tilts = [math.degrees(math.acos(np.clip((L @ r)[:, 2] @ [0, 0, 1], -1, 1))) for r in R]
    step = float(np.median(np.linalg.norm(np.diff(C, axis=0), axis=1))) if len(C) > 1 else 1.0
    mode, d, second = floor_mode(C @ L.T, P @ L.T, radius_factor * step)
    if mode is None:
        est = {'error': 'too few points below the cameras'}
    else:
        ok = np.isfinite(d)
        est = {'scale': float(camera_height / mode), 'floorModeUnits': mode, 'camerasWithFloor': int(ok.sum()),
               'secondModeRatio': second, 'method': 'mode of log(point height below camera) within %.1f median steps, pooled' % radius_factor,
               'perStationRelativeSpreadIQR': float(np.subtract(*np.percentile(d[ok], [75, 25])) / np.median(d[ok])) if ok.sum() >= 4 else None}
    return {'L': L, 'up': up, 'floorDistancesUnits': d, 'cameraHeight': est, 'scale': est.get('scale'),
            'stationTiltDegrees': core.error_summary(tilts), 'medianStepUnits': step}


# ---------------------------------------------------------------- BIM geometry (system python)
def load_bim(path=BIM_SOUP):
    import registration_diagnostics as rd
    return rd.load_soup(path)


def bim_sample(tris, lo, hi, voxel=0.12, density=15, with_normals=False):
    """Surface samples of BIM triangles in the height band [lo, hi] (viewer frame), voxel-thinned; optional unit normals."""
    import registration_fit as rf
    y = tris[:, :, 1]; band = tris[(y.max(1) >= lo) & (y.min(1) <= hi)]
    pts = rf._sample_surface(band, density)
    a_, b_, c_ = band[:, 0], band[:, 1], band[:, 2]; area = .5 * np.linalg.norm(np.cross(b_ - a_, c_ - a_), axis=1)
    counts = np.minimum(3000, np.ceil(area * density)).astype(np.int64)          # same counts as registration_fit._sample_surface
    nrm = np.cross(b_ - a_, c_ - a_); nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12; nrm = np.repeat(nrm, counts, axis=0)
    keys = np.floor(pts / voxel).astype(np.int64); _, first = np.unique(keys, axis=0, return_index=True); first = np.sort(first)
    pts, nrm = pts[first], nrm[first]; ok = (pts[:, 1] >= lo) & (pts[:, 1] <= hi)
    return (pts[ok], nrm[ok]) if with_normals else pts[ok]


def floor_cluster(heights, gap=1.5):
    """Heights (m) -> list of (median, members) clusters separated by > gap (stair flights in between are small)."""
    h = np.sort(np.asarray(heights, float)); h = h[np.isfinite(h)]
    if not len(h):
        return []
    groups, cur = [], [h[0]]
    for v in h[1:]:
        if v - cur[-1] > gap:
            groups.append(cur); cur = [v]
        else:
            cur.append(v)
    groups.append(cur)
    return sorted([(float(np.median(g)), len(g)) for g in groups], key=lambda x: -x[1])


def floors_under(htris, viewer_positions, max_drop=4.0):
    import multifloor_review as mr
    return [mr.floor_below(htris, p, max_drop) for p in viewer_positions]


def wall_raster(segs, cell=0.1, pad=5.0):
    """Distance transform (m) to the nearest wall-section segment on a plan grid: (origin xz, cell, array)."""
    from scipy.ndimage import distance_transform_edt
    if len(segs) == 0:
        return None
    pts = segs.reshape(-1, 2); lo = pts.min(0) - pad; hi = pts.max(0) + pad; shape = tuple(np.ceil((hi - lo) / cell).astype(int) + 1)
    occ = np.zeros(shape, bool)
    for a_, b_ in segs:
        n = max(2, int(np.linalg.norm(b_ - a_) / (cell / 2)) + 1); q = a_ + (b_ - a_) * np.linspace(0, 1, n)[:, None]
        ij = np.floor((q - lo) / cell).astype(int); occ[ij[:, 0], ij[:, 1]] = True
    return lo, cell, distance_transform_edt(~occ) * cell


def wall_lookup(raster, xz):
    if raster is None:
        return np.full(len(xz), np.inf)
    lo, cell, dt = raster; ij = np.floor((np.asarray(xz, float) - lo) / cell).astype(int)
    ok = (ij[:, 0] >= 0) & (ij[:, 0] < dt.shape[0]) & (ij[:, 1] >= 0) & (ij[:, 1] < dt.shape[1])
    out = np.full(len(ij), np.inf); out[ok] = dt[ij[ok, 0], ij[ok, 1]]
    return out


def free_ray_fraction(pose, m, ctx, camera_height, frame_rows=None, max_range=10.0, step=0.1, wall_tol=0.05, end_trim=0.35, start_trim=0.25,
                      max_rays=4000, seed=0):
    """Visibility check against BIM walls: for (point, observing panorama) pairs with the point 0.3-2.3 m above the camera's
    floor (wall band) and 0.8-max_range m away, does the plan segment camera -> point (trimmed at both ends) cross a BIM wall
    section of that floor? Returns (free fraction, rays tested). A wrong placement sends sight lines through walls. Glass
    walls / doors modelled closed also block, so the value is relative (compare hypotheses), not an absolute pass mark."""
    if m.get('obs_ptr') is None:
        return None, 0
    C = to_viewer(pose.points(m['C'])); X = to_viewer(pose.points(m['P'])); ptr, obs = m['obs_ptr'], m['obs_idx']
    rows = set(range(len(C))) if frame_rows is None else set(frame_rows)
    pi = np.repeat(np.arange(len(ptr) - 1), np.diff(ptr)); ci = obs.astype(int)
    keep = np.array([c in rows for c in ci]) if frame_rows is not None else np.ones(len(ci), bool)
    pi, ci = pi[keep], ci[keep]
    dz = X[pi, 1] - C[ci, 1]; lo, hi = 0.3 - camera_height, 2.3 - camera_height
    d2 = np.hypot(X[pi, 0] - C[ci, 0], X[pi, 2] - C[ci, 2])
    ok = (dz >= lo) & (dz <= hi) & (d2 > 0.8) & (d2 < max_range) & np.isfinite(d2)
    pi, ci, d2 = pi[ok], ci[ok], d2[ok]
    if len(pi) > max_rays:
        sel = np.random.default_rng(seed).choice(len(pi), max_rays, replace=False); pi, ci, d2 = pi[sel], ci[sel], d2[sel]
    if not len(pi):
        return None, 0
    free = np.ones(len(pi), bool)
    for f, (y0, y1) in {'L1': (-9, 9.9), 'L2': (9.9, 14.8), 'L3': (14.8, 99)}.items():
        on = (C[ci, 1] >= y0) & (C[ci, 1] < y1)
        if not on.any() or ctx['wallDT'].get(f) is None:
            continue
        a_ = C[ci[on]][:, [0, 2]]; b_ = X[pi[on]][:, [0, 2]]; L_ = d2[on]
        n = int(np.ceil(max_range / step)) + 1; t = np.linspace(0, 1, n)[None, :]
        t0 = (start_trim / L_)[:, None]; t1 = (1 - end_trim / L_)[:, None]; tt = t0 + (t1 - t0) * t
        q = a_[:, None, :] + (b_ - a_)[:, None, :] * tt[..., None]
        dist = wall_lookup(ctx['wallDT'][f], q.reshape(-1, 2)).reshape(q.shape[:2])
        free[np.nonzero(on)[0]] = dist.min(1) >= wall_tol
    return float(free.mean()), int(len(free))


def wall_distance_2d(segs, xz):
    """Distance in plan from each point to the nearest section segment (inf when there are none)."""
    if len(segs) == 0:
        return np.full(len(xz), np.inf)
    a, b = segs[:, 0], segs[:, 1]; ab = b - a; L2 = (ab * ab).sum(1) + 1e-12; out = np.empty(len(xz))
    for i, p in enumerate(np.asarray(xz, float)):
        t = np.clip(((p - a) * ab).sum(1) / L2, 0, 1); q = a + ab * t[:, None]; out[i] = np.sqrt(((q - p) ** 2).sum(1)).min()
    return out


# ---------------------------------------------------------------- coarse search + ICP (system python)
def similarity_icp(src, bim, tree, pose, iterations=40, keep_percentile=65, max_distance=1.0, bound=3.0, fit_scale=False, max_scale_change=0.12,
                   normals=None):
    """Trimmed ICP in BIM-E57: yaw about +Z + XYZ (+ optional scale, bounded to +-max_scale_change of the start).
    src = unlevelled SfM points (the pose's levelling is applied). With BIM `normals` the update is point-to-plane
    (Gauss-Newton on n . (s Rz q + t - p)), which slides along walls and converges where point-to-point stalls;
    otherwise closed-form point-to-point. Returns a new Pose."""
    s0 = pose.s; s, yaw, t = pose.s, pose.yaw, pose.t.copy(); L = pose.L
    Q = src @ L.T                                  # levelled SfM units
    for it in range(iterations):
        Rz = rot_z(math.radians(yaw)); Xr = s * (Q @ Rz.T); X = Xr + t
        d, j = tree.query(X, distance_upper_bound=bound); fin = np.isfinite(d)
        if fin.sum() < 50:
            break
        thr = min(max_distance, np.percentile(np.where(fin, d, np.inf), keep_percentile)); keep = fin & (d < thr)
        if normals is not None:
            n = normals[j[keep]]; Xk = Xr[keep]; r = ((X[keep] - bim[j[keep]]) * n).sum(1)
            cols = [n[:, 0] * -Xk[:, 1] + n[:, 1] * Xk[:, 0]]
            if fit_scale:
                cols.append((n * Xk).sum(1) / s)
            J = np.column_stack(cols + [n[:, 0], n[:, 1], n[:, 2]])
            delta = np.linalg.lstsq(J, -r, rcond=None)[0]
            dth = float(delta[0]); ds = float(delta[1]) if fit_scale else 0.0; dt = delta[-3:]
            sn = min(max(s + ds, s0 * (1 - max_scale_change)), s0 * (1 + max_scale_change))
            # rotate/scale about the origin of the BIM frame: t follows so that the linearised point motion is kept
            ang = math.radians(yaw) + dth; tn = t + dt
            change = abs(dth) + np.linalg.norm(dt) + abs(sn - s) / max(s, 1e-9)
        else:
            A = Q[keep]; B = bim[j[keep]]
            a0, b0 = A.mean(0), B.mean(0); x, y = A - a0, B - b0
            H = x[:, :2].T @ y[:, :2]; ang = math.atan2(H[0, 1] - H[1, 0], H[0, 0] + H[1, 1])
            Rn = rot_z(ang)
            if fit_scale:
                xr = x @ Rn.T; sn = float((xr * y).sum() / (xr * xr).sum())
                sn = min(max(sn, s0 * (1 - max_scale_change)), s0 * (1 + max_scale_change))
            else:
                sn = s
            tn = b0 - sn * (Rn @ a0); change = abs(ang - math.radians(yaw)) + np.linalg.norm(tn - t) + abs(sn - s) / max(s, 1e-9)
        s, yaw, t = sn, math.degrees(ang), tn
        if change < 1e-6:
            break
    return Pose(s, yaw, t, L)


def held_out(pose, pts, tree, bound=3.0):
    if len(pts) == 0:
        return {'points': 0}
    d, _ = tree.query(pose.points(pts), distance_upper_bound=bound); d = np.minimum(d, bound)
    return {'medianMetres': float(np.median(d)), 'p80Metres': float(np.percentile(d, 80)), 'within010': float((d <= .10).mean()),
            'within025': float((d <= .25).mean()), 'within05': float((d <= .5).mean()), 'points': int(len(d)), 'distancesCappedAt': bound}


def coarse_hypotheses(Q, cam_floor_units, s, floor_y_viewer, tris_band_xz, band=(0.8, 2.4), yaw_step=2.0, top=4):
    """Global 2D search (scripts/global_registration_search.search) of one submodel against one floor.
    Q: levelled SfM points; cam_floor_units: levelled floor height (units) of the submodel's dominant floor.
    Returns hypotheses [(Pose-like dict yaw, tx, ty, tz, score)] in BIM-E57."""
    import global_registration_search as gs
    z = (Q[:, 2] - cam_floor_units) * s
    sel = (z >= band[0]) & (z <= band[1])
    if sel.sum() < 30:
        return []
    xy = Q[sel, :2] * s
    # global_registration_search works in viewer xz with yaw convention X' = c x + s z, Z' = -s x + c z.
    # E57 (x, y) -> viewer (x, z) = (x, -y); viewer yaw a == E57 rotation by +a about +Z.
    scan_xz = np.stack([xy[:, 0], -xy[:, 1]], 1)
    coarse = gs.search(scan_xz, tris_band_xz, np.arange(0, 360, yaw_step))
    best = gs.peaks(coarse, top=top); out = []
    for b in best:
        f = max(gs.search(scan_xz, tris_band_xz, b['yaw'] + np.arange(-yaw_step, yaw_step + 1e-9, 0.5)), key=lambda r: r['score'])
        out.append({'yaw': f['yaw'], 'score': f['score'], 'txE57': f['tx'], 'tyE57': -f['tz'],
                    'tzE57': floor_y_viewer - s * cam_floor_units, 'medianScore': float(np.median([r['score'] for r in coarse]))})
    return out


def prepare_submodel(m, a):
    """Levelling, metric scale, floor clusters, filtered points and a fixed train / held-out split (every 3rd point)."""
    res = {'model': m['model'], 'frames': len(m['frames']), 'frameRange': [min(m['frames']), max(m['frames'])] if m['frames'] else None,
           'points': int(len(m['P']))}
    ls = level_and_scale(m, a.camera_height)
    res['levelling'] = {'up': ls['up'].tolist(), 'stationTiltDegrees': ls['stationTiltDegrees']}
    res['cameraHeightScale'] = ls['cameraHeight']
    prep = {'res': res, 'ls': ls, 'm': m}
    if ls['scale'] is None:
        return prep
    s = ls['scale']; L = ls['L']; P = np.asarray(m['P'], float); ok = np.isfinite(P).all(1)
    if len(m['err']):
        ok &= m['err'] < np.percentile(m['err'][np.isfinite(m['err'])], 95)
    P = P[ok]; Q = P @ L.T; Cq = np.asarray(m['C']) @ L.T
    near = np.full(len(Q), np.inf)
    for c in Cq[::max(1, len(Cq) // 80)]:
        near = np.minimum(near, np.hypot(Q[:, 0] - c[0], Q[:, 1] - c[1]))
    keep = near * s < a.max_point_range; P, Q = P[keep], Q[keep]
    fz = Cq[:, 2] - ls['floorDistancesUnits']; clusters = floor_cluster(fz * s, gap=1.5)
    res['floorsInSubmodel'] = [{'heightMetresRelative': c[0] - clusters[0][0], 'stations': c[1]} for c in clusters] if clusters else []
    rng = np.random.default_rng(0); idx = rng.permutation(len(P))
    prep.update(P=P, Q=Q, Cq=Cq, dom=(clusters[0][0] / s) if clusters else float(np.median(Cq[:, 2]) - ls['cameraHeight']['floorModeUnits']),
                train=P[idx[0::3]], test=P[idx[1::3]], clusters=clusters)
    return prep


def global_hypotheses(prep, ctx, floors):
    s = prep['ls']['scale']; hyps = []
    for fl in floors:
        for h in coarse_hypotheses(prep['Q'], prep['dom'], s, ctx['floorTop'][fl], ctx['sectionXZ'][fl]):
            h.update(floor=fl, source='global-search'); hyps.append(h)
    return hyps


def fit_submodel(prep, hyps, ctx, a, log=print):
    """ICP from every hypothesis, keep the best held-out residual, run the independent checks, accept or drop."""
    import multifloor_review as mr
    th = ctx['thresholds']; m = prep['m']; res = dict(prep['res']); ls = prep['ls']
    if len(m['frames']) < th['minFrames']:
        res.update(status='dropped', reasons=['fewer than %d registered panoramas' % th['minFrames']]); return res
    if ls['scale'] is None:
        res.update(status='dropped', reasons=['no camera-height scale: ' + ls['cameraHeight'].get('error', '?')]); return res
    if not hyps:
        res.update(status='unplaced', reasons=['no coarse pose (no Level 1 link, no bridge to a placed submodel, global search not run)']); return res
    s, L = ls['scale'], ls['L']; tried = []
    for h in hyps:
        p0 = Pose(s, h['yaw'], [h['txE57'], h['tyE57'], h['tzE57']], L)
        p1 = similarity_icp(prep['train'], ctx['bim'], ctx['tree'], p0, iterations=30, max_distance=1.5, bound=4.0)
        p2 = similarity_icp(prep['train'], ctx['bim'], ctx['tree'], p1, iterations=60, max_distance=0.6, bound=3.0, fit_scale=a.fit_scale,
                            max_scale_change=th['maxScaleChange'], normals=ctx.get('normals'))
        tried.append({'hyp': h, 'seed': p0, 'pose': p2, 'heldOut': held_out(p2, prep['test'], ctx['tree'])})
    tried.sort(key=lambda r: r['heldOut'].get('medianMetres', 9))
    best = tried[0]; pose = best['pose']; src = best['hyp']['source']; seeded = src in ('level1-link', 'bridge')

    def centre(p): return p.points(m['C']).mean(0)
    rivals = [r for r in tried[1:] if (np.linalg.norm(centre(r['pose']) - centre(pose)) > th['ambiguityDistance'] or
                                       abs(core.wrap_deg(r['pose'].yaw - pose.yaw)) > th['ambiguityYaw'])]
    ratio = (rivals[0]['heldOut']['medianMetres'] / max(best['heldOut']['medianMetres'], 1e-6)) if rivals else None
    C_bim = pose.points(m['C']); Cv = to_viewer(C_bim)
    shift = np.linalg.norm(C_bim - best['seed'].points(m['C']), axis=1)
    fl_under = floors_under(ctx['htris'], Cv)
    cam_above = np.array([np.nan if f is None else Cv[i, 1] - f for i, f in enumerate(fl_under)])
    levels = [mr.classify_level(f) for f in fl_under]; in_wall = []
    for i, p in enumerate(Cv):
        lv = levels[i] if levels[i] in SLAB else None
        in_wall.append(None if lv is None else bool(wall_lookup(ctx['wallDT'][lv], p[[0, 2]][None])[0] < a.wall_clearance))
    iw = [x for x in in_wall if x is not None]; ca = cam_above[np.isfinite(cam_above)]
    checks = {'heldOut': best['heldOut'], 'scaleFromCameraHeight': s, 'scaleAfterIcp': pose.s, 'scaleChange': pose.s / s - 1,
              'impliedCameraHeightMetres': a.camera_height * pose.s / s,
              'cameraAboveBimFloor': core.error_summary(ca) if len(ca) else None,
              'cameraAboveBimFloorIQR': float(np.subtract(*np.percentile(ca, [75, 25]))) if len(ca) >= 4 else None,
              'stationsWithBimFloor': int(len(ca)), 'stationsInWalls': int(sum(iw)), 'stationsWallChecked': len(iw),
              'levels': {k: levels.count(k) for k in set(levels) if k}, 'ambiguityRatio': ratio, 'hypothesesTried': len(tried),
              'icpShiftFromSeed': core.error_summary(shift), 'icpYawChangeFromSeedDegrees': core.wrap_deg(pose.yaw - best['seed'].yaw)}
    # visibility per temporal segment: sight lines of a wrongly merged part run through BIM walls (Oct 18 relaxed model:
    # frames 60-150 had 5-19 % free sight lines, the correct parts 55-95 %)
    seg_rows, segs = [], []
    order = np.argsort(m['frames'])
    for k in range(0, len(order), a.segment):
        rows = order[k:k + a.segment].tolist()
        if len(order) - (k + a.segment) < a.segment // 2 and k + a.segment < len(order):
            rows = order[k:].tolist()
        fv, n = free_ray_fraction(pose, m, ctx, a.camera_height, frame_rows=rows)
        segs.append({'frames': [int(m['frames'][i]) for i in rows], 'freeSightLines': fv, 'rays': n}); seg_rows.append(rows)
        if rows[-1] == order[-1]:
            break
    fv_all, n_all = free_ray_fraction(pose, m, ctx, a.camera_height)
    vals = [x['freeSightLines'] for x in segs if x['freeSightLines'] is not None and x['rays'] >= 40]
    ref = float(np.median(vals)) if vals else None; bad_rows = []
    for x, rows in zip(segs, seg_rows):
        x['flagged'] = bool(ref is not None and x['freeSightLines'] is not None and x['rays'] >= 40 and
                            x['freeSightLines'] < max(th['minSegmentFree'], th['segmentFreeRatio'] * ref))
        if x['flagged']: bad_rows += rows
    seed_frames = {l['frame'] for l in best['hyp'].get('links', [])}
    if seeded and seed_frames and any(x['flagged'] for x in segs):
        # keep only the unflagged run of segments that holds the photo-link frames; parts beyond a flagged block are
        # not supported by the link (Oct 18 relaxed model: frames 19-67 passed alone but were 15-23 m off)
        hold = [k for k, x in enumerate(segs) if seed_frames & set(x['frames'])]
        if hold:
            lo = min(hold); hi = max(hold)
            while lo > 0 and not segs[lo - 1]['flagged']: lo -= 1
            while hi < len(segs) - 1 and not segs[hi + 1]['flagged']: hi += 1
            for k, (x, rows) in enumerate(zip(segs, seg_rows)):
                if not lo <= k <= hi and not x['flagged']:
                    x['droppedBeyondFlagged'] = True; bad_rows += rows
    checks.update(freeSightLines=fv_all, sightLinesTested=n_all, segments=segs, framesFlaggedByVisibility=sorted(int(m['frames'][i]) for i in bad_rows))
    reasons = []; ho = best['heldOut']
    if fv_all is not None and n_all >= 100 and fv_all < th['minModelFree']:
        reasons.append('only %.0f %% of sight lines clear of BIM walls' % (100 * fv_all))
    if len(bad_rows) > th['maxFlaggedFraction'] * len(m['frames']):
        reasons.append('%d/%d frames in segments whose sight lines cross BIM walls' % (len(bad_rows), len(m['frames'])))
    if ho.get('medianMetres', 9) > th['maxHeldOutMedian']: reasons.append('held-out median %.3f m > %.2f' % (ho['medianMetres'], th['maxHeldOutMedian']))
    if ho.get('within025', 0) < th['minHeldOutWithin025']: reasons.append('held-out within 0.25 m %.2f < %.2f' % (ho['within025'], th['minHeldOutWithin025']))
    if checks['cameraAboveBimFloor'] is None or not (th['cameraHeightRange'][0] <= checks['cameraAboveBimFloor']['median'] <= th['cameraHeightRange'][1]):
        reasons.append('camera height above BIM floor outside %s' % th['cameraHeightRange'])
    if checks['cameraAboveBimFloorIQR'] is not None and checks['cameraAboveBimFloorIQR'] > th['maxCameraHeightIQR'] and len(prep.get('clusters') or []) <= 1:
        reasons.append('camera height above BIM floor varies (IQR %.2f m)' % checks['cameraAboveBimFloorIQR'])
    if iw and sum(iw) / len(iw) > th['maxStationsInWallsFraction']: reasons.append('%d/%d stations inside BIM walls' % (sum(iw), len(iw)))
    if abs(checks['scaleChange']) > th['maxScaleChange'] - 1e-6: reasons.append('ICP scale hit the +-%.0f %% bound' % (100 * th['maxScaleChange']))
    if seeded and (np.median(shift) > th['maxSeedShift'] or abs(checks['icpYawChangeFromSeedDegrees']) > th['maxSeedYawChange']):
        reasons.append('ICP moved %.2f m / %.1f deg from the photo-link seed' % (np.median(shift), checks['icpYawChangeFromSeedDegrees']))
    if not seeded and ratio is not None and ratio < th['ambiguityRatio']:
        reasons.append('ambiguous: a different pose fits within %.0f %%' % (100 * (ratio - 1)))
    if src in ('global-search', 'continuity') and not a.accept_unlinked:
        reasons.append('%s seed only (no photo link to a registered panorama): kept as an unverified candidate; '
                       'accept with --accept-unlinked only after checking it visually' % src)
    if src == 'continuity':
        c = best['hyp']['continuity']; st = ctx.get('placedPoses', {}).get((c['placedModel'], c['placedFrame']))
        if st is not None:
            gapd = float(np.linalg.norm(C_bim[m['frames'].index(c['frame'])] - np.asarray(st['positionE57'])))
            checks['continuityGapMetres'] = gapd
            if gapd > c['maxDistanceMetres'] + 0.5:
                reasons.append('continuity broken: %.1f m from the placed frame %d (allowed %.1f)' % (gapd, c['placedFrame'], c['maxDistanceMetres']))
    res.update(status='placed' if not reasons else 'dropped', reasons=reasons, pose=pose.asdict(), checks=checks,
               chosenHypothesis={k: v for k, v in best['hyp'].items() if k not in ('links',)},
               hypotheses=[{'source': r['hyp']['source'], 'floor': r['hyp'].get('floor'), 'searchScore': r['hyp'].get('score'),
                            'yawDegrees': r['pose'].yaw, 'scale': r['pose'].s, 'centreE57': centre(r['pose']).tolist(),
                            'heldOutMedian': r['heldOut'].get('medianMetres'), 'heldOutWithin025': r['heldOut'].get('within025'),
                            'pose': r['pose'].asdict()} for r in tried],
               stations=[{'frame': int(f), 'pano': m['panos'][i], 'positionE57': C_bim[i].tolist(), 'positionBIM': Cv[i].tolist(),
                          'worldFromPanoE57': pose.rotation(m['R'][i]).tolist(), 'bimFloorBelow': fl_under[i],
                          'cameraAboveBimFloor': None if not np.isfinite(cam_above[i]) else float(cam_above[i]),
                          'level': levels[i] or 'stairs', 'insideWall': in_wall[i]} for i, f in enumerate(m['frames']) if i not in set(bad_rows)])
    log('model %d (%d frames %s): %s via %s, held-out med %.3f w25 %.2f, scale %.3f->%.3f, cam above floor %s, walls %d/%d, free sight lines %s, '
        'visibility-flagged frames %d, seed shift %.2f m%s' % (
        m['model'], len(m['frames']), res['frameRange'], res['status'].upper(), best['hyp']['source'], ho.get('medianMetres', -1), ho.get('within025', -1),
        s, pose.s, 'med %.2f' % checks['cameraAboveBimFloor']['median'] if checks['cameraAboveBimFloor'] else None, sum(iw), len(iw),
        None if fv_all is None else round(fv_all, 2), len(bad_rows), float(np.median(shift)), (' | ' + '; '.join(reasons)) if reasons else ''), flush=True)
    return res


def link_hypothesis(prep, pairs, placed_poses, l1):
    """Seed for one submodel from photo links to already-placed panoramas (Level 1 stations or stations of placed
    submodels). Returns a hypothesis dict or None (with the reason in hyp['error'])."""
    m = prep['m']; idx = {f: i for i, f in enumerate(m['frames'])}; links = []; kinds = set()
    if prep['ls']['scale'] is None:
        return None
    for p in pairs:
        R = np.asarray(p['R']); d = np.asarray(p['direction'])
        if p['b'].get('model') == m['model'] and p['b']['frame'] in idx:
            other, mine = p['a'], p['b']; Rl, dl = R, d
        elif p['a'].get('model') == m['model'] and p['a']['frame'] in idx:
            other, mine = p['b'], p['a']; Rl = R.T; dl = -(R @ d)       # reversed link: a seen from b in b's frame
        else:
            continue
        if 'level1' in other:
            st = l1.get(other['level1'])
            if st is None: continue
            aPos, aR, kind = st['positionE57'], st['R'], 'level1-link'
        else:
            st = placed_poses.get((other['model'], other['frame']))
            if st is None: continue
            aPos, aR, kind = st['positionE57'], st['worldFromPanoE57'], 'bridge'
        i = idx[mine['frame']]; kinds.add(kind)
        links.append({'aPos': aPos, 'aR': aR, 'bCentre': m['C'][i], 'bR': m['R'][i], 'R': Rl, 'direction': dl, 'weight': p['inliers'],
                      'kind': kind, 'other': other, 'frame': mine['frame']})
    for (om, of), st in placed_poses.items():   # frames registered in this model AND in a placed one
        if om != m['model'] and of in idx:
            i = idx[of]; kinds.add('bridge')
            links.append({'aPos': st['positionE57'], 'aR': st['worldFromPanoE57'], 'bCentre': m['C'][i], 'bR': m['R'][i], 'R': np.eye(3),
                          'direction': [1.0, 0, 0], 'weight': 1000.0, 'shared': True, 'kind': 'shared-frame', 'other': {'model': om, 'frame': of}, 'frame': of})
    if not links:
        return None
    seed = seed_from_links(links, prep['ls']['scale'], prep['ls']['L'])
    src = 'level1-link' if 'level1-link' in kinds else 'bridge'
    if 'error' in seed:
        return {'source': src, 'error': seed['error'], 'seed': seed}
    t = seed['translationE57']
    return {'source': src, 'yaw': seed['yawDegrees'], 'txE57': t[0], 'tyE57': t[1], 'tzE57': t[2], 'seed': {k: v for k, v in seed.items() if k != 'rayResiduals'},
            'links': [{'kind': l['kind'], 'other': l['other'], 'frame': l['frame'], 'inliers': l['weight']} for l in links]}


def continuity_hypotheses(prep, placed_poses, ctx, floors, max_gap=12, yaw_step=3.0, grid=0.75, keep=12):
    """Seeds for a submodel with no photo link, from walking continuity: its first (last) keyframe was taken a few frames
    after (before) a keyframe of an already-placed submodel, so it lies within d_max of that station (d_max from the placed
    submodel's own metres-per-frame). Every yaw x offsets within d_max x candidate floor is pre-scored by a trimmed
    nearest-surface distance of a point subsample plus stations inside BIM walls; the best `keep` go to ICP."""
    m = prep['m']; s, L = prep['ls']['scale'], prep['ls']['L']; fr = m['frames']
    by_model = {}
    for (om, of), st in placed_poses.items():
        if om != m['model']:
            by_model.setdefault(om, {})[of] = st
    cons = []
    for om, sts in by_model.items():
        fs = sorted(sts)
        before = [f for f in fs if f < fr[0] and fr[0] - f <= max_gap]; after = [f for f in fs if f > fr[-1] and f - fr[-1] <= max_gap]
        P = np.array([sts[f]['positionE57'] for f in fs]); df = np.diff(fs)
        speed = float(np.median(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1) / np.maximum(df, 1))) if len(fs) > 2 else 0.5
        if before: cons.append((fr[0], before[-1], fr[0] - before[-1], sts[before[-1]], speed, om))
        if after: cons.append((fr[-1], after[0], after[0] - fr[-1], sts[after[0]], speed, om))
    if not cons:
        return []
    rng = np.random.default_rng(1); sub = prep['train'][rng.permutation(len(prep['train']))[:600]]; Qs = sub @ L.T
    Cq = prep['Cq']; fi = {f: i for i, f in enumerate(fr)}
    out = []
    for fu, fp, gap, st, speed, om in cons:
        dmax = float(np.clip(1.0 + 1.5 * gap * speed, 2.0, 8.0)); anchor = np.asarray(st['positionE57']); cu = Cq[fi[fu]]
        offs = [np.array([x, y]) for x in np.arange(-dmax, dmax + 1e-9, grid) for y in np.arange(-dmax, dmax + 1e-9, grid) if math.hypot(x, y) <= dmax]
        for fl in floors:
            tz = ctx['floorTop'][fl] - s * prep['dom']; zu = s * cu[2] + tz
            if abs(zu - anchor[2]) > max(0.6, 0.6 * dmax):
                continue
            for yaw in np.arange(0, 360, yaw_step):
                Rz = rot_z(math.radians(yaw)); base = s * (Rz @ cu)
                Xs = s * (Qs @ Rz.T); Cs = s * (Cq @ Rz.T)
                for o in offs:
                    t = np.array([anchor[0] + o[0] - base[0], anchor[1] + o[1] - base[1], tz])
                    d, _ = ctx['tree'].query(Xs + t, distance_upper_bound=1.0); q = float(np.median(np.minimum(d, 1.0)))
                    Cv = to_viewer(Cs + t); iw = float((wall_lookup(ctx['wallDT'][fl], Cv[:, [0, 2]]) < 0.15).mean())
                    out.append({'source': 'continuity', 'floor': fl, 'yaw': float(yaw), 'txE57': float(t[0]), 'tyE57': float(t[1]), 'tzE57': float(t[2]),
                                'prescore': q + 0.5 * iw, 'continuity': {'frame': int(fu), 'placedModel': int(om), 'placedFrame': int(fp), 'gapFrames': int(gap),
                                                                         'maxDistanceMetres': dmax}})
    out.sort(key=lambda h: h['prescore']); picked = []
    for h in out:   # spread: skip near-duplicates of an already picked seed
        if all(abs(core.wrap_deg(h['yaw'] - p['yaw'])) > 8 or math.hypot(h['txE57'] - p['txE57'], h['tyE57'] - p['tyE57']) > 1.5 or h['floor'] != p['floor'] for p in picked):
            picked.append(h)
        if len(picked) >= keep:
            break
    return picked


def build_context(a, tris):
    from scipy.spatial import cKDTree
    import multifloor_review as mr
    floors = a.floors.split(',')
    lo = min(SLAB[f] for f in floors) - 1.0; hi = max(SLAB[f] for f in floors) + 4.6
    bim, nrm = bim_sample(tris, lo, hi, with_normals=True)
    htris = mr.horizontal_triangles(tris)
    ctx = {'bim': to_e57(bim), 'normals': to_e57(nrm), 'tree': cKDTree(to_e57(bim)), 'htris': htris, 'sectionXZ': {}, 'wallSegs': {}, 'floorTop': {},
           'thresholds': dict(DEFAULTS)}
    ctx['wallDT'] = {}
    for f in ('L1', 'L2', 'L3'):
        ctx['wallSegs'][f] = mr.plan_segments(tris, SLAB[f] + 1.5); ctx['wallDT'][f] = wall_raster(ctx['wallSegs'][f])
    yy = htris[:, :, 1].mean(1); area = 0.5 * np.linalg.norm(np.cross(htris[:, 1] - htris[:, 0], htris[:, 2] - htris[:, 0]), axis=1)
    for f in floors:  # floor top: most common near-horizontal BIM surface height within 0.6 m of the nominal slab
        sel = np.abs(yy - SLAB[f]) < 0.6
        hist, edges = np.histogram(yy[sel], bins=np.arange(SLAB[f] - 0.6, SLAB[f] + 0.61, 0.02), weights=area[sel])
        ctx['floorTop'][f] = float(edges[hist.argmax()] + 0.01)
        ctx['sectionXZ'][f] = bim_sample(tris, ctx['floorTop'][f] + 0.8, ctx['floorTop'][f] + 2.4, voxel=0.1)[:, [0, 2]]
    return ctx


def merge_stations(results):
    """One pose per frame: the larger accepted submodel wins where submodels overlap."""
    chosen = {}
    for r in sorted([x for x in results if x['status'] == 'placed'], key=lambda x: -x['frames']):
        for st in r['stations']:
            chosen.setdefault(st['frame'], {**st, 'model': r['model']})
    return [chosen[f] for f in sorted(chosen)]


def cmd_place(a):
    work = Path(a.work); out = Path(a.out or work / 'placed-bim.json')
    if out.exists() and not a.overwrite:
        raise SystemExit(f'{out} exists; pass --overwrite')
    models = read_submodels(work, a.method); meta = load(work / 'frames.json')
    anchors_path = Path(a.anchors) if a.anchors else work / ('anchors-%s.json' % a.method)
    anchors = load(anchors_path) if anchors_path.exists() else {'pairs': [], 'level1Stations': []}
    pairs = [p for p in anchors['pairs'] if p['kind'] == 'bridge' or not a.no_level1]
    l1 = {s['key']: s for s in anchors.get('level1Stations', [])}
    tris = load_bim(a.bim_soup); ctx = build_context(a, tris)
    for k in ('max_held_out', 'min_within025'):
        v = getattr(a, k)
        if v is not None:
            ctx['thresholds'][{'max_held_out': 'maxHeldOutMedian', 'min_within025': 'minHeldOutWithin025'}[k]] = v
    print('floor tops (viewer y):', {k: round(v, 3) for k, v in ctx['floorTop'].items()}, '| BIM points', len(ctx['bim']),
          '| links: level1 %d, bridges %d' % (sum(p['kind'] == 'level1' for p in pairs), sum(p['kind'] == 'bridge' for p in pairs)), flush=True)
    preps = {m['model']: prepare_submodel(m, a) for m in models if len(m['frames']) >= 2}
    results, placed_poses, seed_log = {}, {}, []
    # rounds: Level 1 links first, then bridges to whatever is placed, until nothing changes
    for rnd in range(len(preps) + 1):
        progress = False
        for mid, prep in sorted(preps.items(), key=lambda kv: -kv[1]['res']['frames']):
            if mid in results and results[mid]['status'] == 'placed':
                continue
            h = link_hypothesis(prep, pairs, placed_poses, l1)
            key = (mid, h and h['source'], h and h.get('yaw') and round(h['yaw'], 1))
            if h is None or key in seed_log:
                continue
            seed_log.append(key)
            if 'error' in h:
                results[mid] = {**prep['res'], 'status': 'unplaced', 'reasons': ['photo link seed rejected: ' + h['error']], 'linkSeed': h}
                continue
            r = fit_submodel(prep, [h], ctx, a); r['linkSeed'] = {k: v for k, v in h.items() if k not in ('yaw', 'txE57', 'tyE57', 'tzE57')}
            results[mid] = r
            if r['status'] == 'placed':
                progress = True
                for st in r['stations']:
                    placed_poses[(mid, st['frame'])] = st
        if not progress and not a.no_continuity:   # walking continuity to a placed submodel (no photo link)
            ctx['placedPoses'] = placed_poses
            for mid, prep in sorted(preps.items(), key=lambda kv: -kv[1]['res']['frames']):
                if (mid in results and results[mid]['status'] == 'placed') or prep['ls']['scale'] is None or len(prep['m']['frames']) < ctx['thresholds']['minFrames']:
                    continue
                key = (mid, 'continuity', len(placed_poses))
                if key in seed_log:
                    continue
                seed_log.append(key)
                hyps = continuity_hypotheses(prep, placed_poses, ctx, a.floors.split(','))
                if not hyps:
                    continue
                prev = results.get(mid); r = fit_submodel(prep, hyps, ctx, a)
                if prev and prev.get('linkSeed'): r['linkSeed'] = prev['linkSeed']
                results[mid] = r
                if r['status'] == 'placed':
                    progress = True
                    for st in r['stations']:
                        placed_poses[(mid, st['frame'])] = st
                    break   # placing one may give others a photo link (shared frames / bridges): back to the link round
        if not progress:
            break
    for mid, prep in preps.items():  # no usable photo link: global search against every floor
        if mid in results and results[mid]['status'] == 'placed':
            continue
        if a.no_global or prep['ls']['scale'] is None or len(prep['m']['frames']) < ctx['thresholds']['minFrames']:
            results.setdefault(mid, fit_submodel(prep, [], ctx, a)); continue
        prev = results.get(mid)
        r = fit_submodel(prep, global_hypotheses(prep, ctx, a.floors.split(',')), ctx, a)
        if prev: r['linkSeed'] = prev.get('linkSeed'); r['reasons'] = prev.get('reasons', []) + r.get('reasons', [])
        results[mid] = r
    res_list = [results[k] for k in sorted(results)]
    stations = merge_stations(res_list); placed = {s['frame'] for s in stations}
    # bridge consistency: links between two placed submodels, ray miss after placement (independent of each fit)
    bridge_checks = []
    for p in anchors['pairs']:
        if p['kind'] != 'bridge':
            continue
        A, B = placed_poses.get((p['a']['model'], p['a']['frame'])), placed_poses.get((p['b']['model'], p['b']['frame']))
        if A is None or B is None:
            continue
        d = np.asarray(A['worldFromPanoE57']) @ np.asarray(p['direction']); d /= np.linalg.norm(d)
        v = np.asarray(B['positionE57']) - np.asarray(A['positionE57']); s_ = v @ d
        M = np.asarray(A['worldFromPanoE57']) @ np.asarray(p['R']).T @ np.asarray(B['worldFromPanoE57']).T
        bridge_checks.append({'a': p['a'], 'b': p['b'], 'inliers': p['inliers'], 'missMetres': float(np.linalg.norm(v - s_ * d)),
                              'rangeMetres': float(s_), 'rotationDisagreementDegrees': core.rotation_angle_deg(M)})
    result = {'schema': 'multifloor-raw-placement/1', 'variant': 'cupix-free-bim', 'label': LABEL, 'frame': 'bim-e57',
              'frameNote': 'positionE57 / worldFromPanoE57 are in the BIM viewer world with E57 axes (viewer [x,y,z] = [x, z, -y]); '
                           'positionBIM is the viewer Y-up position. No Cupix input.',
              'work': str(work), 'method': a.method, 'createdAt': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
              'inputs': {'bimSoup': str(a.bim_soup), 'cameraHeightMetres': a.camera_height, 'cameraHeightSource': a.height_source,
                         'floorsSearched': a.floors.split(','), 'fitScale': a.fit_scale, 'anchors': str(anchors_path) if anchors_path.exists() else None,
                         'level1Links': not a.no_level1, 'continuity': not a.no_continuity, 'globalSearch': not a.no_global, 'acceptUnlinked': a.accept_unlinked},
              'floorTopsViewerY': ctx['floorTop'], 'thresholds': ctx['thresholds'],
              'models': [{k: v for k, v in r.items() if k != 'stations'} for r in res_list],
              'bridgeChecks': bridge_checks, 'bridgeCheckSummary': {'missMetres': core.error_summary([b['missMetres'] for b in bridge_checks]),
                                                                    'rotationDegrees': core.error_summary([b['rotationDisagreementDegrees'] for b in bridge_checks])},
              'stations': stations, 'unplacedKeyframes': [k['frame'] for k in meta['keyframes'] if k['frame'] not in placed],
              'summary': {'keyframes': len(meta['keyframes']), 'placed': len(stations),
                          'levels': {lv: sum(s['level'] == lv for s in stations) for lv in ('L1', 'L2', 'L3', 'stairs')},
                          'submodelsPlaced': sum(r['status'] == 'placed' for r in res_list),
                          'submodelsNotPlaced': [{'model': r['model'], 'frames': r['frames'], 'status': r['status'], 'reasons': r.get('reasons')}
                                                 for r in res_list if r['status'] != 'placed']},
              'honesty': 'Coarse pose from photo links to registered Level 1 panoramas and between submodels (or a global search against '
                         'BIM floor sections), refined by trimmed ICP to BIM design surfaces. Residuals are distances to design geometry; '
                         'Level 1 anchors inherit the provisional Level 1 registration. Not surveyed accuracy.'}
    save_new(out, result, overwrite=a.overwrite)
    print('placed %d / %d keyframes (%s); submodels placed %d, not placed %d -> %s' % (
        len(stations), len(meta['keyframes']), result['summary']['levels'], result['summary']['submodelsPlaced'],
        len(result['summary']['submodelsNotPlaced']), out))
    if not stations:
        raise SystemExit('No submodel passed the checks; see %s (fallback: Cupix upload, or manual landmarks)' % out)


# ---------------------------------------------------------------- per-floor packages (system python)
IDENTITY_NOTE = ('Stations are stored directly in the BIM viewer world (Y-up metres), so this registration is the identity. '
                 'Placement: scripts/raw360_bim.py place (photo links to registered Level 1 panoramas / between SfM submodels, '
                 'trimmed ICP to BIM design surfaces); no Cupix input. Provisional, not surveyed.')


def floor_of_station(level, floor_y, tolerance=0.45):
    """Package floor: L1/L2/L3 keep their level; a stair station goes with the floor at the TOP of its flight
    (multifloor_review.package_floor rule), a stair station above Level 3 is dropped."""
    import multifloor_review as mr
    if level in ('L1', 'L2', 'L3'):
        return level
    return mr.package_floor(level, floor_y, tolerance)


def cmd_package(a):
    """Per-floor local packages from one or more placements (one per INSV of the capture day). Panorama files are named
    <tag>_<pano> so several videos can share a folder; ids are <tag>_f<frame>."""
    from PIL import Image
    import multifloor_review as mr
    placed_list, blurred_list = a.placed, a.blurred
    tags = a.tag or ['raw%d' % k if len(placed_list) > 1 else 'raw' for k in range(len(placed_list))]
    if not (len(placed_list) == len(blurred_list) == len(tags)):
        raise SystemExit('--placed, --blurred and --tag need the same number of entries')
    floors = a.floors.split(','); root = Path(a.out_root); outs = {f: root / (a.prefix % f) for f in floors}
    for o in list(outs.values()) + ([Path(a.upper_out)] if a.upper_out else []):
        if o.exists():
            raise SystemExit(f'{o} exists; packages are never overwritten')
    tris = load_bim(a.bim_soup) if a.bim_soup else None
    rows, privacy_reports, sources = [], [], []
    for placed_path, blurred, tag in zip(placed_list, blurred_list, tags):
        P = load(placed_path)
        if P.get('frame') != 'bim-e57':
            raise SystemExit('%s is not a raw360_bim placement (frame %r)' % (placed_path, P.get('frame')))
        blurred = Path(blurred).resolve(); rep = blurred / 'privacy-report.json'
        if not rep.exists() and not a.allow_unblurred:
            raise SystemExit(f'{rep} missing: run raw360_pipeline.py privacy first (or --allow-unblurred for a private test)')
        privacy = load(rep) if rep.exists() else {}
        privacy_reports.append({'tag': tag, 'report': str(rep) if rep.exists() else None, 'flaggedImages': privacy.get('flaggedImages', [])})
        sources.append({'tag': tag, 'placement': str(Path(placed_path)), 'work': P.get('work'), 'unplacedKeyframes': P.get('unplacedKeyframes'),
                        'summary': P.get('summary'), 'models': [{k: m.get(k) for k in ('model', 'frames', 'frameRange', 'status', 'reasons')} |
                                                                 {'heldOut': (m.get('checks') or {}).get('heldOut'), 'cameraAboveBimFloor': (m.get('checks') or {}).get('cameraAboveBimFloor'),
                                                                  'freeSightLines': (m.get('checks') or {}).get('freeSightLines'), 'seed': (m.get('chosenHypothesis') or {}).get('source')}
                                                                 for m in P['models']], 'bridgeCheckSummary': P.get('bridgeCheckSummary')})
        for st in P['stations']:
            src = blurred / st['pano']
            if not src.is_file():
                raise SystemExit(f'missing blurred image {src}')
            with Image.open(src) as im:
                w, h = im.size
            rows.append({'id': '%s_f%06d' % (tag, st['frame']), 'name': '%s frame %d' % (tag, st['frame']), 'file': '%s_%s' % (tag, st['pano']), 'src': src,
                         'frame': st['frame'], 'video': tag, 'order': len(rows), 'position': [float(v) for v in st['positionBIM']],
                         'positionBIM': [float(v) for v in st['positionBIM']], 'e57Quaternion': [float(v) for v in core.quat_from_matrix(np.asarray(st['worldFromPanoE57']))],
                         'dimensions': [w, h], 'level': st['level'], 'bimFloorBelow': st['bimFloorBelow'], 'cameraAboveBimFloor': st['cameraAboveBimFloor'],
                         'sfmModel': st['model']})
    if not rows:
        raise SystemExit('no placed stations to package')
    privacy = {'flaggedImages': [f'{p["tag"]}:{x}' for p in privacy_reports for x in p['flaggedImages']]}
    blurred = None
    P = {'models': [m for src in sources for m in src['models']], 'bridgeCheckSummary': [src['bridgeCheckSummary'] for src in sources],
         'honesty': 'Coarse pose from photo links to registered Level 1 panoramas and between SfM submodels, refined by trimmed ICP to BIM design '
                    'surfaces; residuals are distances to design geometry. Not surveyed accuracy.'}
    clear = mr.bim_clear_test(tris) if tris is not None else None; edges = {}
    for tag in tags:   # walked order = frame order within one video; videos are never chained to each other
        edges.update(mr.build_route([{'id': r['id'], 'position': r['positionBIM'], 'level': r['level']} for r in rows if r['video'] == tag], (), (), clear=clear))
    assign = {r['id']: floor_of_station(r['level'], r['bimFloorBelow']) for r in rows}
    reg = {'rotationYDegrees': 0.0, 'translation': [0.0, 0.0, 0.0], 'scale': 1, 'status': 'project-frame-provisional',
           'registrationKind': 'identity: stations already in the BIM viewer frame', 'label': LABEL, 'captureDate': a.date,
           'frames': {'source': 'BIM viewer world, Y-up metres (stations placed by raw360_bim place)', 'target': 'BIM viewer world, Y-up metres'},
           'basis': IDENTITY_NOTE, 'placements': sources,
           'honesty': P.get('honesty')}
    summary = {}
    for floor, out in outs.items():
        sel = [r for r in rows if assign[r['id']] == floor]
        if not sel:
            print('no stations for', floor, '- package not written'); summary[floor] = {'stations': 0}; continue
        keep = {r['id'] for r in sel}; fe = mr.subset_edges(edges, keep)
        stage = out.with_name('.' + out.name + '.partial')
        if stage.exists(): shutil.rmtree(stage)
        photos = stage / 'panoramas'; (photos / 'mobile').mkdir(parents=True)
        idx = {r['id']: k for k, r in enumerate(sel)}; stations = []
        for r in sel:
            os.symlink(os.path.relpath(r['src'], photos.resolve()), photos / r['file'])
            with Image.open(r['src']) as im:
                im.convert('RGB').resize((2048, 1024), Image.Resampling.LANCZOS).save(photos / 'mobile' / r['file'], quality=88)
            st = {'id': r['id'], 'file': r['file'], 'sourceName': r['name'], 'video': r['video'], 'sourceFrame': r['frame'], 'frameOrder': r['order'],
                  'position': r['position'], 'positionBIM': r['positionBIM'], 'e57Quaternion': r['e57Quaternion'], 'sha256': sha256(r['src']),
                  'dimensions': r['dimensions'], 'level': r['level'], 'packageFloor': floor, 'bimFloorBelow': r['bimFloorBelow'],
                  'cameraAboveBimFloor': r['cameraAboveBimFloor'], 'sfmModel': r['sfmModel'], 'neighbors': sorted(idx[j] for j in fe[r['id']])}
            if fe[r['id']]:
                st['edgeKinds'] = {str(idx[j]): k for j, k in sorted(fe[r['id']].items(), key=lambda kv: idx[kv[0]])}
                stairs = sorted(idx[j] for j, k in fe[r['id']].items() if k == 'stairs')
                if stairs: st['stairs'] = stairs
            stations.append(st)
        order = {r['id']: r['order'] for r in sel}; comps = mr.components([r['id'] for r in sel], fe)
        counts = {}
        for st in stations: counts[st['level']] = counts.get(st['level'], 0) + 1
        name = mr.LEVEL_NAMES[floor]
        manifest = {'schema': 'grimes-captured-panoramas/1', 'building': 'grimes', 'level': floor, 'captureDate': a.date,
                    'exportedStations': len(stations), 'defaultStation': mr.default_station([{'id': r['id'], 'position': r['positionBIM'], 'level': r['level']} for r in sel], fe),
                    'status': 'local-preview', 'alignment': LABEL,
                    'frame': 'BIM viewer world, Y-up metres (Cupix-free placement, scripts/raw360_bim.py place); registration.json is the identity.',
                    'projection': 'equirectangular',
                    'privacy': 'Displayed panoramas are the automatic blur output (' + ', '.join(str(p['report']) for p in privacy_reports) +
                               '); detection is not complete, manual review required. Local only, never publish.',
                    'navigation': 'Consecutive placed frames <= 7.7 m and rise <= 1.5 m = route; across a slab = stairs; non-consecutive same-floor links only '
                                  'when no BIM wall lies between stations <= 4 m apart (link-bim-clear, inferred from design walls). No links to other floors.',
                    'navigationLimits': {'maxStep': 7.7, 'maxRise': 1.5, 'stairStep': 9.0, 'stairRise': 4.6},
                    'levels': counts, 'walkGroups': [sorted(c, key=lambda i: order[i]) for c in comps],
                    'floorAssignment': {'rule': 'Level from the highest near-horizontal BIM surface under the station; stair stations go with the floor at the top of their flight.',
                                        'excludedStations': [{'id': r['id'], 'frame': r['frame'], 'packageFloor': assign[r['id']], 'level': r['level']} for r in rows if r['id'] not in keep]},
                    'source': {'kind': 'raw-insv-local-sfm-cupix-free', 'placements': [{k: v for k, v in x.items() if k != 'models'} for x in sources],
                               'privacyFlaggedImages': privacy.get('flaggedImages', [])},
                    'coverage': 'as walked; see walkGroups for disconnected parts and source.unplacedKeyframes for frames that were not placed.',
                    'stations': stations}
        (photos / 'manifest.json').write_text(json.dumps(manifest, indent=1))
        (stage / 'registration.json').write_text(json.dumps({**reg, 'level': floor}, indent=2))
        (stage / 'project.json').write_text(json.dumps({'schema': 'capture-project/1', 'building': 'grimes', 'level': floor, 'captureDate': a.date,
            'panoramas': 'panoramas/manifest.json', 'model': None, 'registration': 'registration.json', 'dataStatus': 'NO FEED', 'status': 'local-preview',
            'routeReady': True, 'alignment': LABEL, 'coverage': 'partial',
            'notes': [f'{name}, {len(stations)} panoramas from raw INSV (local SfM, Cupix-free placement); provisional, not surveyed.',
                      'Blurred panoramas only; manual privacy review still required. Not for publishing.', 'Built by scripts/raw360_bim.py package.']}, indent=1))
        (stage / 'README.txt').write_text(f'Local {name} preview of the {a.date} capture (Cupix-free; provisional, not surveyed; not for publishing). '
                                          f'Serve the repository and open scan-compare.html?capture={a.date}&floors={floor} on localhost. Built by scripts/raw360_bim.py package.\n')
        stage.rename(out)
        summary[floor] = {'out': str(out), 'stations': len(stations), 'levels': counts, 'walkGroups': [len(c) for c in comps], 'default': manifest['defaultStation']}
        print('wrote', out, counts, 'groups', [len(c) for c in comps], 'edges', sum(len(s['neighbors']) for s in stations) // 2)
    if a.upper_out:   # all Level 2 / Level 3 / stair stations in one Gaussian training package (blurred, no route)
        up = Path(a.upper_out); stage = up.with_name('.' + up.name + '.partial')
        if stage.exists(): shutil.rmtree(stage)
        (stage / 'panoramas').mkdir(parents=True); tst = []
        for r in rows:
            if assign[r['id']] not in ('L2', 'L3'):
                continue
            os.symlink(os.path.relpath(r['src'], (stage / 'panoramas').resolve()), stage / 'panoramas' / r['file'])
            tst.append({'id': r['id'], 'file': r['file'], 'sourceName': r['name'], 'sourceFrame': r['frame'], 'position': r['position'],
                        'e57Quaternion': r['e57Quaternion'], 'dimensions': r['dimensions'], 'sha256': sha256(r['src']), 'level': r['level'],
                        'packageFloor': assign[r['id']], 'neighbors': []})
        if tst:
            mid = mr.default_station([{'id': t['id'], 'position': t['position'], 'level': t['level']} for t in tst], {t['id']: {} for t in tst})
            (stage / 'panoramas/manifest.json').write_text(json.dumps({'schema': 'grimes-captured-panoramas/1', 'building': 'grimes', 'level': 'L2-L3',
                'captureDate': a.date, 'exportedStations': len(tst), 'defaultStation': mid, 'status': 'local-training-input', 'alignment': LABEL,
                'frame': 'BIM viewer world, Y-up metres (identity registration)', 'privacy': 'Privacy-blurred panoramas; manual review still required; '
                'never publish this package or a model trained from it without review.', 'stations': tst}, indent=1))
            (stage / 'registration.json').write_text(json.dumps({**reg, 'level': 'L2-L3'}, indent=2))
            (stage / 'README.txt').write_text(f'Upper-floor stations of the {a.date} capture for Gaussian training (blurred, local, provisional, not surveyed). Built by scripts/raw360_bim.py package --upper-out.\n')
            stage.rename(up); summary['upper'] = {'out': str(up), 'stations': len(tst), 'centerId': mid}; print('wrote', up, len(tst), 'stations, centre', mid)
        else:
            shutil.rmtree(stage)
    if a.summary:
        save_new(a.summary, summary, overwrite=True)
    return summary


# ---------------------------------------------------------------- validation against another placement (never an input)
def reference_frames(dirs):
    """{sourceFrame: (positionBIM viewer, world_from_pano BIM-E57)} from per-floor packages (manifest + registration)."""
    import multifloor_review as mr
    out = {}
    for d in dirs:
        d = Path(d); m = load(d / 'panoramas/manifest.json'); reg = load(d / 'registration.json')
        for s in m['stations']:
            pos = s.get('positionBIM') or mr.apply(reg, s['position'])[0].tolist()
            out[int(s['sourceFrame'])] = (np.asarray(pos, float), viewer_yaw_to_e57(reg.get('rotationYDegrees', 0)) @ core.matrix_from_quat(s['e57Quaternion']),
                                          s.get('level'))
    return out


def compare_placements(stations, ref, max_gap=6):
    """Per placed frame: the reference pose at the same video frame; exact, or interpolated between reference frames at
    most max_gap frames apart (both placements come from the same video, but keyframe sets of two SfM runs differ)."""
    rows = []; fs = sorted(ref)
    for st in stations:
        r = ref.get(int(st['frame'])); kind = 'exact'
        if r is None:
            hit = core.interpolate_track(fs, [ref[f][0] for f in fs], [ref[f][1] for f in fs], int(st['frame']), max_gap)
            if hit is None:
                continue
            k = int(np.searchsorted(fs, int(st['frame']))); r = (np.asarray(hit[0]), hit[1], ref[fs[k - 1]][2]); kind = 'interpolated'
        d = np.asarray(st['positionBIM']) - r[0]; Ra = np.asarray(st['worldFromPanoE57'])
        fwd_a, fwd_b = Ra[:, 0], r[1][:, 0]
        head = core.wrap_deg(math.degrees(math.atan2(fwd_a[1], fwd_a[0]) - math.atan2(fwd_b[1], fwd_b[0])))
        rows.append({'frame': int(st['frame']), 'match': kind, 'model': st.get('model'), 'level': st.get('level'), 'refLevel': r[2],
                     'distanceMetres': float(np.linalg.norm(d)), 'horizontalMetres': float(np.hypot(d[0], d[2])), 'verticalMetres': float(d[1]),
                     'headingDegrees': float(head)})
    return rows


def cmd_compare(a):
    P = load(a.placed); ref = reference_frames(a.reference); rows = compare_placements(P['stations'], ref)
    by_model = {}
    for r in rows: by_model.setdefault(r['model'], []).append(r)
    out = {'schema': 'raw360-bim-compare/1', 'label': 'validation only (reference never used as input); ' + LABEL, 'placed': a.placed,
           'reference': a.reference, 'referenceNote': a.reference_note,
           'common': len(rows), 'exact': sum(r['match'] == 'exact' for r in rows),
           'placedOnly': sorted(int(s['frame']) for s in P['stations'] if int(s['frame']) not in {r['frame'] for r in rows}),
           'referenceOnly': sorted(f for f in ref if not any(abs(f - int(s['frame'])) <= 3 for s in P['stations'])),
           'distance': core.error_summary([r['distanceMetres'] for r in rows]), 'horizontal': core.error_summary([r['horizontalMetres'] for r in rows]),
           'vertical': core.error_summary([abs(r['verticalMetres']) for r in rows]), 'headingAbs': core.error_summary([abs(r['headingDegrees']) for r in rows]),
           'perModel': {str(k): {'n': len(v), 'distance': core.error_summary([r['distanceMetres'] for r in v]),
                                 'headingAbs': core.error_summary([abs(r['headingDegrees']) for r in v])} for k, v in sorted(by_model.items(), key=lambda kv: str(kv[0]))},
           'rows': rows}
    save_new(a.out, out, overwrite=True)
    print('common %d frames: distance median %.3f m, p90 %.3f, max %.3f; heading |d| median %.2f deg, max %.2f; placed-only %d, reference-only %d' % (
        len(rows), out['distance'].get('median', float('nan')), out['distance'].get('p90', float('nan')), out['distance'].get('max', float('nan')),
        out['headingAbs'].get('median', float('nan')), out['headingAbs'].get('max', float('nan')), len(out['placedOnly']), len(out['referenceOnly'])))
    for k, v in out['perModel'].items():
        print('  model', k, v['n'], 'median %.3f max %.3f' % (v['distance']['median'], v['distance']['max']))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('dump'); d.add_argument('--work', required=True); d.add_argument('--method', default='colmap-incremental')
    an = sub.add_parser('anchor'); an.add_argument('--work', required=True); an.add_argument('--method', default='colmap-incremental')
    an.add_argument('--min-inliers', type=int, default=40); an.add_argument('--level1-topk', type=int, default=6)
    an.add_argument('--bridge-gap', type=int, default=15, help='frames: link keyframes of different submodels at most this far apart in time')
    an.add_argument('--no-level1', action='store_true'); an.add_argument('--keep-features', action='store_true', help='keep the SIFT cache (anchor-features/)')
    p = sub.add_parser('place'); p.add_argument('--work', required=True); p.add_argument('--method', default='colmap-incremental')
    p.add_argument('--out'); p.add_argument('--overwrite', action='store_true'); p.add_argument('--bim-soup', default=str(BIM_SOUP))
    p.add_argument('--camera-height', type=float, default=2.0); p.add_argument('--height-source', default='owner: stick held at about 2.0 m (not measured)')
    p.add_argument('--floors', default='L1,L2,L3'); p.add_argument('--anchors', help='default <work>/anchors-<method>.json when present')
    p.add_argument('--no-level1', action='store_true', help='ignore Level 1 links (bridges only)')
    p.add_argument('--no-global', action='store_true', help='never run the global search for unlinked submodels')
    p.add_argument('--no-continuity', action='store_true', help='do not seed unlinked submodels from walking continuity to a placed one')
    p.add_argument('--accept-unlinked', action='store_true', help='accept a global-search / continuity placement that passes every check '
                   '(risky: on Oct 18 video 477 wrong poses fitted BIM as well as the right one)')
    p.add_argument('--segment', type=int, default=10, help='keyframes per segment for the visibility check')
    p.add_argument('--no-fit-scale', dest='fit_scale', action='store_false')
    p.add_argument('--max-point-range', type=float, default=12.0); p.add_argument('--wall-clearance', type=float, default=0.12)
    p.add_argument('--max-held-out', type=float); p.add_argument('--min-within025', type=float)
    k = sub.add_parser('package', help='per-floor local preview packages (capture-local/grimes-<floor>-<date>)')
    k.add_argument('--placed', nargs='+', required=True); k.add_argument('--blurred', nargs='+', required=True); k.add_argument('--date', required=True)
    k.add_argument('--upper-out', help='also write one Level 2 + Level 3 Gaussian training package here')
    k.add_argument('--floors', default='L1,L2,L3'); k.add_argument('--out-root', default=str(ROOT / 'capture-local'))
    k.add_argument('--prefix', help="default 'grimes-%%s-<date>'"); k.add_argument('--tag', nargs='+', help='one short tag per placement (e.g. the INSV number)')
    k.add_argument('--bim-soup', default=str(BIM_SOUP)); k.add_argument('--allow-unblurred', action='store_true'); k.add_argument('--summary')
    c = sub.add_parser('compare', help='validation only: per-frame differences to another placement')
    c.add_argument('--placed', required=True); c.add_argument('--reference', nargs='+', required=True); c.add_argument('--out', required=True)
    c.add_argument('--reference-note', default='')
    a = ap.parse_args()
    if a.cmd == 'package' and not a.prefix:
        a.prefix = 'grimes-%s-' + a.date
    {'dump': cmd_dump, 'anchor': cmd_anchor, 'place': cmd_place, 'package': cmd_package, 'compare': cmd_compare}[a.cmd](a)


if __name__ == '__main__':
    main()
