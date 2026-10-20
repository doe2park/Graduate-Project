"""Tie a second Cupix video (another floor) to an already placed capture by panorama feature matching (CPU).

Problem (Oct 18, 2026): Cupix exported two videos in one "Ground Level" E57. The Level 1 video is in the shared
project frame (May/Sep registration applies); the second video (Level 3 -> atrium stair -> Level 2 -> stair foot on
Level 1) has an internally consistent trajectory but an arbitrary yaw/position relative to Level 1 (Cupix placed it
north of the building at Level 1 height). This script measures, from the photographs only:

1. internal consistency of each video: relative rotation and translation direction of consecutive panoramas
   (essential matrix on bearing vectors, 8-point + RANSAC) versus the Cupix poses;
2. the rigid yaw + translation (scale fixed at 1, Cupix metric) from the second video's frame into the first one's,
   from cross-video matches: yaw = weighted mean relative rotation, translation = least-squares intersection of the
   bearing rays from first-video stations to each matched second-video station (needs >= 2 rays per anchor);
3. which non-consecutive stations of the second video see each other (visually verified links for the route).

Input panoramas are Cupix E57 equirects (world-aligned: every station has the same quaternion). Output: link.json.
Run with the raw360 venv (OpenCV):

    work/raw360-venv/bin/python scripts/multifloor_link.py link --ground capture-local/grimes-GROUND-2026-10-18 \
        --e57 "<Ground Level E57>" --placed capture-local/grimes-L1-2026-10-18 --video-a 141325 --video-b 153400 \
        --out work/multifloor/2026-10-18

Results are photogrammetric consistency between Cupix exports, not surveyed accuracy.
"""
import argparse, json, math, re, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
W, H = 2048, 1024


# ---------------- geometry (pure numpy, unit-tested) ----------------
def pixel_dirs(px, width=W, height=H):
    """E57 spherical equirect convention: image centre +X, left +Y, top +Z."""
    u = (px[:, 0] + 0.5) / width; v = (px[:, 1] + 0.5) / height
    az = np.pi * (1 - 2 * u); el = np.pi * (0.5 - v)
    return np.stack([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)], 1), el


def quat_matrix(q):
    x, y, z, w = np.asarray(q, float) / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def rot_z(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def e57_from_viewer(p):
    """Manifest positions are viewer Y-up [x, z, -y]; back to E57 Z-up."""
    x, y, z = p
    return np.array([x, -z, y], float)


def eight_point(f1, f2):
    A = np.einsum('ni,nj->nij', f2, f1).reshape(len(f1), 9)
    E = np.linalg.svd(A)[2][-1].reshape(3, 3)
    U, _, Vt = np.linalg.svd(E)
    return U @ np.diag([1, 1, 0]) @ Vt


def epipolar_error(E, f1, f2):
    n = (E @ f1.T).T; n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    return np.abs((f2 * n).sum(1))


def decompose(E, f1, f2):
    """(R, t, n_in_front) with f2 ~ R f1 + t (directions in each panorama's world-aligned frame)."""
    U, _, Vt = np.linalg.svd(E)
    if np.linalg.det(U) < 0: U = -U
    if np.linalg.det(Vt) < 0: Vt = -Vt
    Wm = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1.0]]); best = None
    for R in (U @ Wm @ Vt, U @ Wm.T @ Vt):
        for t in (U[:, 2], -U[:, 2]):
            A = np.stack([(R @ f1.T).T, -f2], 2)
            lam = np.array([np.linalg.lstsq(A[k], -t, rcond=None)[0] for k in range(len(f1))])
            good = int(((lam[:, 0] > 0) & (lam[:, 1] > 0)).sum())
            if best is None or good > best[2]:
                best = (R, t, good)
    return best


def relative_pose(f1, f2, thr=0.006, iters=3000, seed=0):
    """RANSAC essential matrix on bearings; None if fewer than 15 matches."""
    n = len(f1)
    if n < 15:
        return None
    rng = np.random.default_rng(seed); best = None
    for _ in range(iters):
        s = rng.choice(n, 8, replace=False); inl = epipolar_error(eight_point(f1[s], f2[s]), f1, f2) < thr
        if best is None or inl.sum() > best.sum(): best = inl
    for _ in range(3):
        E = eight_point(f1[best], f2[best]); inl = epipolar_error(E, f1, f2) < thr
        if inl.sum() < best.sum(): break
        best = inl
    R, t, front = decompose(E, f1[best], f2[best])
    direction = -R.T @ t  # centre of panorama 2 seen from panorama 1, in frame 1
    return {'R': R, 'direction': direction / np.linalg.norm(direction), 'inliers': int(best.sum()), 'matches': n, 'inFront': front}


def yaw_deg(R):
    return math.degrees(math.atan2(R[1, 0], R[0, 0]))


def tilt_deg(R):
    return math.degrees(math.acos(np.clip(R[2, 2], -1, 1)))


def angle_deg(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    return math.degrees(math.acos(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1, 1)))


def intersect_rays(rays):
    """Least-squares point closest to rays [(origin, direction, weight)]; needs >= 2 non-parallel rays."""
    A = np.zeros((3, 3)); b = np.zeros(3)
    for o, d, w in rays:
        d = np.asarray(d, float) / np.linalg.norm(d); M = np.eye(3) - np.outer(d, d); A += w * M; b += w * M @ np.asarray(o, float)
    return np.linalg.solve(A, b)


def ray_residuals(point, rays):
    out = []
    for o, d, w in rays:
        d = np.asarray(d, float) / np.linalg.norm(d); v = point - np.asarray(o, float); s = v @ d
        out.append({'rangeMetres': float(s), 'missMetres': float(np.linalg.norm(v - s * d)), 'angleDegrees': angle_deg(v, d)})
    return out


def viewer_registration(yaw_e57_deg, t_e57):
    """E57 Z-up rotation about +Z by -yaw then +t  ==  viewer convention [c x + s z + t0, y + t1, -s x + c z + t2]."""
    return {'rotationYDegrees': -yaw_e57_deg, 'translation': [float(t_e57[0]), float(t_e57[2]), float(-t_e57[1])]}


# ---------------- features and matching (OpenCV) ----------------
def features(image_path, cache, quaternion):
    import cv2
    cache = Path(cache)
    if cache.exists():
        z = np.load(cache); d, des = z['d'], z['des']
    else:
        im = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        im = cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA)
        kp, des = cv2.SIFT_create(nfeatures=12000, contrastThreshold=0.02).detectAndCompute(im, None)
        d, el = pixel_dirs(np.array([p.pt for p in kp], np.float32))
        keep = el > math.radians(-45)  # operator / stick below
        des = des[keep]; des = np.sqrt(des / (np.abs(des).sum(1, keepdims=True) + 1e-9)).astype(np.float32)  # RootSIFT
        d = d[keep].astype(np.float32); cache.parent.mkdir(parents=True, exist_ok=True); np.savez(cache, d=d, des=des)
    return (quat_matrix(quaternion) @ d.T).T.astype(float), des


def mutual_ratio_matches(Da, Db, ratio=0.8):
    import cv2
    bf = cv2.BFMatcher(cv2.NORM_L2)
    back = {m[0].queryIdx: m[0].trainIdx for m in bf.knnMatch(Db, Da, k=1)}
    return [(m[0].queryIdx, m[0].trainIdx) for m in bf.knnMatch(Da, Db, k=2)
            if len(m) == 2 and m[0].distance < ratio * m[1].distance and back.get(m[0].trainIdx) == m[0].queryIdx]


class Stations:
    def __init__(self, packages, cache):
        self.info, self.cache = {}, Path(cache)
        for pkg in packages:
            m = json.loads((Path(pkg) / 'panoramas/manifest.json').read_text())
            for s in m['stations']:
                self.info.setdefault(s['id'], {'image': Path(pkg) / 'panoramas' / s['file'], 'position': s['position'], 'q': s['e57Quaternion']})
        self._f = {}

    def feat(self, i):
        if i not in self._f:
            s = self.info[i]; self._f[i] = features(s['image'], self.cache / (i + '.npz'), s['q'])
        return self._f[i]

    def pose(self, a, b, **kw):
        da, Da = self.feat(a); db, Db = self.feat(b)
        pr = mutual_ratio_matches(Da, Db)
        if len(pr) < 15:
            return None
        pr = np.array(pr)
        return relative_pose(da[pr[:, 0]], db[pr[:, 1]], **kw)

    def e57(self, i):
        return e57_from_viewer(self.info[i]['position'])


def video_of(names, i):
    return re.sub(r'\(\d+\)\.\w+$', '', names[i])


def frame_of(names, i):
    return int(re.search(r'\((\d+)\)\.\w+$', names[i]).group(1))


def consistency(st, ids, names):
    rows = []
    for a, b in zip(ids, ids[1:]):
        r = st.pose(a, b)
        if r is None:
            rows.append({'a': a, 'b': b, 'inliers': 0}); continue
        d = st.e57(b) - st.e57(a)
        rows.append({'a': a, 'b': b, 'inliers': r['inliers'], 'matches': r['matches'],
                     'rotationDeviationDegrees': math.degrees(math.acos(np.clip((np.trace(r['R']) - 1) / 2, -1, 1))),
                     'directionErrorDegrees': angle_deg(r['direction'], d) if np.linalg.norm(d) > .05 else None,
                     'cupixDistanceMetres': float(np.linalg.norm(d)), 'cupixRiseMetres': float(d[2])})
    return rows


def summarize_consistency(rows, min_inliers=40):
    good = [r for r in rows if r['inliers'] >= min_inliers and r.get('directionErrorDegrees') is not None]
    if not good:
        return {'pairs': len(rows), 'reliablePairs': 0}
    rot = np.array([r['rotationDeviationDegrees'] for r in good]); de = np.array([r['directionErrorDegrees'] for r in good])
    return {'pairs': len(rows), 'reliablePairs': len(good), 'minInliers': min_inliers,
            'rotationDeviationMedianDegrees': float(np.median(rot)), 'rotationDeviationP90Degrees': float(np.percentile(rot, 90)),
            'directionErrorMedianDegrees': float(np.median(de)), 'directionErrorP90Degrees': float(np.percentile(de, 90))}


def link(a):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from extract_e57_images import E57, node_value
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    _, root = E57(a.e57).xml()
    names = {node_value(n.find('guid')): node_value(n.find('name')) for n in root.find('images2D')}
    st = Stations([a.ground] + a.placed, out / 'features')
    ground = [s['id'] for s in json.loads((Path(a.ground) / 'panoramas/manifest.json').read_text())['stations']]
    vids = {i: video_of(names, i) for i in ground}
    A = sorted([i for i in ground if a.video_a in vids[i]], key=lambda i: frame_of(names, i))
    B = sorted([i for i in ground if a.video_b in vids[i]], key=lambda i: frame_of(names, i))
    placed = sorted(set(st.info) - set(B))
    print('video A %d, video B %d, placed candidates %d' % (len(A), len(B), len(placed)), flush=True)

    cons = {'A': consistency(st, A, names), 'B': consistency(st, B, names)}
    print('consistency A', summarize_consistency(cons['A']), '\nconsistency B', summarize_consistency(cons['B']), flush=True)

    cross = []
    for k, b in enumerate(B):
        for p in placed:
            r = st.pose(p, b, iters=800)
            if r and r['inliers'] >= a.min_inliers:
                cross.append({'placed': p, 'b': b, 'inliers': r['inliers'], 'yaw': yaw_deg(r['R']), 'tilt': tilt_deg(r['R'])})
        print('cross %d/%d' % (k + 1, len(B)), flush=True)
    if not cross:
        raise SystemExit('no cross-video matches with >= %d inliers' % a.min_inliers)
    # consensus yaw: largest cluster within 3 degrees, then refit each pair with more RANSAC iterations
    ys = np.array([c['yaw'] for c in cross]); support = [(np.abs(((ys - y + 180) % 360) - 180) < 3).sum() for y in ys]
    y0 = ys[int(np.argmax(support))]
    pairs = []
    for c in cross:
        if abs(((c['yaw'] - y0 + 180) % 360) - 180) >= 3:
            continue
        r = st.pose(c['placed'], c['b'], iters=5000)
        pairs.append({'placed': c['placed'], 'b': c['b'], 'inliers': r['inliers'], 'yaw': yaw_deg(r['R']), 'tilt': tilt_deg(r['R']),
                      'origin': st.e57(c['placed']).tolist(), 'direction': r['direction'].tolist()})
    w = np.array([p['inliers'] for p in pairs], float); yaw = float(np.average([p['yaw'] for p in pairs], weights=w))
    Rm = rot_z(-yaw); anchors, ts = [], []
    for b in sorted({p['b'] for p in pairs}):
        rays = [(p['origin'], p['direction'], p['inliers']) for p in pairs if p['b'] == b]
        if len(rays) < 2:
            continue
        P = intersect_rays(rays); t = P - Rm @ st.e57(b)
        anchors.append({'station': b, 'pointE57': P.tolist(), 'rays': ray_residuals(P, rays), 'tE57': t.tolist(), 'weight': float(sum(r[2] for r in rays))})
        ts.append((t, anchors[-1]['weight']))
    if not anchors:
        raise SystemExit('no second-video station is seen from >= 2 placed stations')
    t = np.average([x[0] for x in ts], axis=0, weights=[x[1] for x in ts])
    checks = []
    for p in pairs:
        if any(x['station'] == p['b'] for x in anchors) and len([q for q in pairs if q['b'] == p['b']]) >= 2:
            continue
        P = Rm @ st.e57(p['b']) + t
        checks.append({'placed': p['placed'], 'b': p['b'], 'inliers': p['inliers'], **ray_residuals(P, [(p['origin'], p['direction'], 1)])[0]})

    # visually verified non-consecutive links inside video B (same floor or not; route builder decides)
    vis = []
    for i, x in enumerate(B):
        for y in B[i + 2:]:
            d = st.e57(y) - st.e57(x)
            if np.linalg.norm(d) > a.link_radius:
                continue
            r = st.pose(x, y)
            ok = bool(r and r['inliers'] >= 40 and angle_deg(r['direction'], d) < 5 and
                      math.degrees(math.acos(np.clip((np.trace(r['R']) - 1) / 2, -1, 1))) < 2)
            vis.append({'a': x, 'b': y, 'distanceMetres': float(np.linalg.norm(d)), 'inliers': r['inliers'] if r else 0,
                        'directionErrorDegrees': angle_deg(r['direction'], d) if r else None, 'verified': ok})
    result = {'schema': 'grimes-multifloor-link/1', 'status': 'candidate-not-surveyed',
              'method': 'SIFT (RootSIFT, mutual ratio 0.8) on 2048x1024 equirects, elevation > -45 deg; essential matrix on bearing '
                        'vectors (8-point, RANSAC, 0.006 rad); yaw = inlier-weighted mean; translation = ray intersection, scale fixed 1',
              'videoA': a.video_a, 'videoB': a.video_b, 'stationsA': A, 'stationsB': B, 'names': {i: names[i] for i in A + B},
              'consistency': {k: {'summary': summarize_consistency(v), 'pairs': v} for k, v in cons.items()},
              'crossCandidates': cross, 'pairs': pairs, 'yawE57Degrees': yaw,
              'yawSpreadDegrees': float(np.ptp([p['yaw'] for p in pairs])), 'tE57': t.tolist(), 'anchors': anchors, 'checks': checks,
              'bToPlacedViewer': viewer_registration(yaw, t), 'visualLinks': vis}
    (out / 'link.json').write_text(json.dumps(result, indent=1))
    print('yaw %.3f (spread %.2f, %d pairs), t %s, anchors %s' % (yaw, result['yawSpreadDegrees'], len(pairs), np.round(t, 3),
          [x['station'] for x in anchors]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('link')
    p.add_argument('--ground', required=True, help='intake package holding both videos (panoramas/manifest.json)')
    p.add_argument('--e57', required=True, help='E57 of that package (for video/frame names)')
    p.add_argument('--placed', nargs='*', default=[], help='extra packages already in the placed frame (e.g. the Level 1 export)')
    p.add_argument('--video-a', required=True, help='substring of the placed video name'); p.add_argument('--video-b', required=True)
    p.add_argument('--min-inliers', type=int, default=40); p.add_argument('--link-radius', type=float, default=6.0)
    p.add_argument('--out', required=True)
    a = ap.parse_args()
    link(a)


if __name__ == '__main__':
    main()
