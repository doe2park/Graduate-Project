"""Pure functions for the raw Insta360 -> posed-panorama pipeline (scripts/raw360_pipeline.py).

Only numpy + stdlib, so tests run without pycolmap/ffmpeg. Conventions:
- Panorama local frame = E57 sphericalRepresentation: image centre +X, left of centre +Y, top +Z.
  Column u (0..1 from left) -> azimuth pi*(1-2u); row v (0..1 from top) -> elevation pi*(0.5-v).
- Rotations are 3x3 matrices; quaternions are [x, y, z, w] (E57 / three.js order).
- World frame of an export is E57-style Z-up metres; capture_import converts to Y-up [x, z, -y].
"""
import json, math, re, struct
import numpy as np

TRAILER_MAGIC = b'8db42d694ccc418790edff439fe026bf'
RECORD_NAMES = {0x101: 'metadata', 0x200: 'preview', 0x300: 'imu', 0x400: 'exposure', 0x500: 'thumbnail_h264',
                0x600: 'frame_timestamps', 0x700: 'gps', 0x900: 'unknown_0x900', 0xa00: 'unknown_0xa00'}

# ---------------------------------------------------------------- INSV trailer

def parse_trailer_index(f, size):
    """Index Insta360 INSV trailer records: {record_id: (offset, length)}. Empty if no trailer."""
    if size < 78:
        return {}
    f.seek(size - 78); tail = f.read(78)
    if tail[-32:] != TRAILER_MAGIC:
        return {}
    total, version = struct.unpack('<II', tail[-40:-32])
    start, pos, out = size - total, size - 78, {}
    while pos > start:
        f.seek(pos); rid, length = struct.unpack('<HI', f.read(6))
        if length == 0 or pos - length < start:
            break
        out[rid] = (pos - length, length); pos -= length + 6
    out['_version'] = version
    return out


def parse_imu(raw):
    """IMU record 0x300 (ONE X2 layout): u64 ms timestamp + 6 float64 (accel g xyz, gyro rad/s xyz)."""
    if len(raw) % 56:
        raise ValueError('Unexpected IMU record length; this camera/firmware layout is not supported')
    a = np.frombuffer(raw, dtype=np.dtype([('t', '<u8'), ('v', '<f8', (6,))]))
    return a['t'].astype(np.float64), a['v'][:, :3].copy(), a['v'][:, 3:].copy()


def parse_frame_times(raw):
    """Record 0x600: one u64 millisecond timestamp per video frame (time-lapse capture instants)."""
    if len(raw) % 8:
        raise ValueError('Unexpected frame timestamp record length')
    return np.frombuffer(raw, '<u8').astype(np.float64)


def parse_lens_calibration(meta):
    """Extract the per-lens calibration strings from the metadata record.

    Observed ONE X2 layout (interpreted, not vendor-documented): '2_' then per lens
    xi fx fy cx cy yaw pitch roll tx ty tz k1 k2 k3 p1 p2 W H ver (unified/Mei fisheye model).
    """
    text = meta.decode('latin-1')
    lenses = []
    for match in re.finditer(r'2_((?:-?\d+\.\d+_){16}\d+_\d+_\d+_(?:-?\d+\.\d+_){16}\d+_\d+_\d+)', text):
        vals = match.group(1).split('_')
        for chunk in (vals[:19], vals[19:38]):
            keys = ['xi', 'fx', 'fy', 'cx', 'cy', 'yaw', 'pitch', 'roll', 'tx', 'ty', 'tz', 'k1', 'k2', 'k3', 'p1', 'p2', 'width', 'height', 'version']
            lenses.append(dict(zip(keys, [float(v) for v in chunk])))
        break
    return lenses


def equidistant_fov_from_mei(lens, image_size, calib_lens_size=3040, max_theta_deg=90.0):
    """Least-squares equidistant (r = f*theta) fit to a Mei-model lens; returns (fov_deg, max_px_error).

    ffmpeg v360 fisheye input is equidistant; this picks the FOV that best matches the camera's own
    calibration and reports the residual model mismatch instead of hiding it.
    """
    s = image_size / calib_lens_size
    th = np.radians(np.linspace(0.5, max_theta_deg, 400))
    x = np.sin(th) / (np.cos(th) + lens['xi']); r2 = x * x
    r = lens['fx'] * s * x * (1 + lens['k1'] * r2 + lens['k2'] * r2 ** 2 + lens['k3'] * r2 ** 3)
    f = float(th @ r / (th @ th))
    return math.degrees(image_size / f), float(np.max(np.abs(r - f * th)))

# ---------------------------------------------------------------- equirect / pinhole geometry

def equirect_dirs(width, height):
    u = (np.arange(width) + 0.5) / width; v = (np.arange(height) + 0.5) / height
    az = np.pi * (1 - 2 * u)[None, :]; el = np.pi * (0.5 - v)[:, None]
    return np.stack(np.broadcast_arrays(np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el) + 0 * az), -1)


def dir_to_equirect_px(d, width, height):
    d = d / np.linalg.norm(d, axis=-1, keepdims=True)
    az = np.arctan2(d[..., 1], d[..., 0]); el = np.arcsin(np.clip(d[..., 2], -1, 1))
    return (1 - az / np.pi) / 2 * width - 0.5, (0.5 - el / np.pi) * height - 0.5


def cam_from_pano(yaw_deg, pitch_deg=0.0):
    """Rotation mapping panorama-frame vectors into a COLMAP pinhole frame (x right, y down, z forward)."""
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    f = np.array([math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)])
    r = np.array([math.sin(y), -math.cos(y), 0.0])
    d = np.cross(f, r)
    return np.stack([r, d, f])


def pinhole_maps(R_cam_from_pano, size, hfov_deg, eq_w, eq_h):
    f = size / 2 / math.tan(math.radians(hfov_deg) / 2); c = (size - 1) / 2
    xs, ys = np.meshgrid((np.arange(size) - c) / f, (np.arange(size) - c) / f)
    rays = np.stack([xs, ys, np.ones_like(xs)], -1) @ R_cam_from_pano  # = R^T * ray per pixel
    mx, my = dir_to_equirect_px(rays, eq_w, eq_h)
    return mx.astype(np.float32), my.astype(np.float32), f


def remap_bilinear(img, mx, my):
    """Bilinear sampling with horizontal wrap (equirect) and clamped rows. img HxW or HxWxC."""
    h, w = img.shape[:2]
    x0 = np.floor(mx).astype(np.int64); y0 = np.floor(my).astype(np.int64)
    fx = (mx - x0)[..., None] if img.ndim == 3 else mx - x0
    fy = (my - y0)[..., None] if img.ndim == 3 else my - y0
    xa, xb = x0 % w, (x0 + 1) % w; ya, yb = np.clip(y0, 0, h - 1), np.clip(y0 + 1, 0, h - 1)
    im = img.astype(np.float32)
    out = (im[ya, xa] * (1 - fx) * (1 - fy) + im[ya, xb] * fx * (1 - fy) + im[yb, xa] * (1 - fx) * fy + im[yb, xb] * fx * fy)
    return out


def rotate_equirect(img, R_out_from_in, out_w=None, out_h=None):
    """Resample an equirect so that a direction d_in appears at R_out_from_in @ d_in."""
    h, w = img.shape[:2]; out_w, out_h = out_w or w, out_h or h
    d_out = equirect_dirs(out_w, out_h)
    mx, my = dir_to_equirect_px(d_out @ R_out_from_in, w, h)  # d_in = R^T d_out
    return remap_bilinear(img, mx, my)


def nadir_mask(width, height, cone_deg):
    """Equirect mask (True = keep) excluding the cone of half-angle cone_deg around straight down."""
    el = np.degrees(np.pi * (0.5 - (np.arange(height) + 0.5) / height))
    return np.repeat((el > -90 + cone_deg)[:, None], width, 1)

# ---------------------------------------------------------------- frame scoring and selection

def sharpness(gray):
    g = gray.astype(np.float32)
    lap = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    return float(lap.var())


def yaw_aligned_difference(a, b, valid=None):
    """Mean |a-b| after the best circular horizontal (yaw) shift; removes pure camera yaw from the motion cue."""
    a = a.astype(np.float32); b = b.astype(np.float32)
    if valid is None:
        valid = np.ones(a.shape, bool)
    za = np.where(valid, a - a[valid].mean(), 0); zb = np.where(valid, b - b[valid].mean(), 0)
    corr = np.fft.irfft(np.sum(np.fft.rfft(za, axis=1) * np.conj(np.fft.rfft(zb, axis=1)), 0), n=a.shape[1])
    shift = int(np.argmax(corr))
    bs = np.roll(b, shift, axis=1); vs = valid & np.roll(valid, shift, axis=1)
    scale = max(1e-6, 0.5 * (a[vs].mean() + bs[vs].mean()))
    return float(np.abs(a[vs] - bs[vs]).mean() / scale), shift


def select_keyframes(motion, sharp, count=None, step=None, window=0.35, max_gap=None, gap_min_motion=0.25, min_gap=3):
    """Pick frame indices spaced evenly in cumulative motion; within each window take the sharpest frame.

    motion[i] = cue between frames i-1 and i (motion[0] ignored). Either count or step (motion units).
    min_gap (frames) avoids near-duplicate keyframes; max_gap forces an extra keyframe when more than max_gap frames pass AND at least gap_min_motion*step of
    motion accumulated (guards against under-estimated motion without sampling a standing operator repeatedly).
    """
    n = len(motion)
    if n == 0 or len(sharp) != n:
        raise ValueError('motion and sharpness must have equal non-zero length')
    m = np.clip(np.asarray(motion, float), 0, None); m[0] = 0
    sharp = np.asarray(sharp, float); cum = np.cumsum(m); total = cum[-1]
    if step is None:
        if not count or count < 2:
            raise ValueError('Give count >= 2 or a positive step')
        step = total / (count - 1) if total > 0 else 0
    if step <= 0:
        return sorted({int(round(t)) for t in np.linspace(0, n - 1, count or 2)})
    picks = []
    def pick(cand, target=None):
        cand = np.asarray(cand); top = sharp[cand].max()
        good = cand[sharp[cand] >= 0.95 * top]  # near-sharpest; tie-break toward the motion target
        return int(good[np.argmin(np.abs(cum[good] - target))] if target is not None else good[np.argmax(sharp[good])])
    def fill_gaps(until):
        while max_gap and picks and until - picks[-1] > max_gap:
            lo = picks[-1] + max(min_gap, max_gap // 2); hi = picks[-1] + max_gap + 1
            if cum[hi - 1] - cum[picks[-1]] < gap_min_motion * step:
                break
            picks.append(pick(np.arange(lo, hi)))
    for target in np.arange(0, total + 1e-9, step):
        last = picks[-1] if picks else -1
        cand = np.where((np.abs(cum - target) <= window * step) & (np.arange(n) > last))[0]
        if len(cand) == 0:
            later = np.where((cum >= target) & (np.arange(n) > last))[0]
            if len(later) == 0:
                continue
            cand = later[:1]
        best = pick(cand, target)
        fill_gaps(best)
        if not picks or best - picks[-1] >= min_gap:
            picks.append(best)
    fill_gaps(n - 1)
    return picks


def walking_cue(t_ms, accel, frame_times_ms, half_window_ms=250.0, rest_percentile=5.0):
    """Per-frame travel cue from the IMU: std of |accel| around each frame instant minus the resting level.

    Walking produces step oscillation; standing still does not. With a roughly constant walking speed the
    cumulative cue is proportional to distance walked, independent of scene depth or camera rotation.
    """
    t = np.asarray(t_ms, float); a = np.linalg.norm(np.asarray(accel, float), axis=1); out = []
    for x in np.asarray(frame_times_ms, float):
        lo, hi = np.searchsorted(t, x - half_window_ms), np.searchsorted(t, x + half_window_ms)
        out.append(float(a[lo:hi].std()) if hi - lo > 2 else 0.0)
    out = np.array(out); rest = np.percentile(out, rest_percentile)
    return np.clip(out - rest, 0, None), out, float(rest)


def static_region_mask(stack, valid_rows=None, rel_threshold=0.25):
    """Pixels whose content hardly changes while the camera moves are rigid with the camera (operator, stick).

    stack: (T, H, W) low-res equirects of moving frames. Returns True = keep (scene), False = static.
    valid_rows: optional boolean (H,) restricting detection (e.g. lower hemisphere only).
    """
    s = stack.astype(np.float32)
    change = np.median(np.abs(np.diff(s, axis=0)), axis=0)
    level = np.median(change)
    static = change < rel_threshold * level
    if valid_rows is not None:
        static &= np.asarray(valid_rows)[:, None]
    return ~static


def yaw_invariant_descriptor(gray, rows=16, cols=64, harmonics=12):
    """Place descriptor for loop candidates: |FFT| over azimuth per row band is invariant to camera yaw."""
    h, w = gray.shape
    g = gray[: h - h % rows, : w - w % cols].astype(np.float32)
    g = g.reshape(rows, g.shape[0] // rows, cols, g.shape[1] // cols).mean((1, 3))
    g = (g - g.mean()) / (g.std() + 1e-6)
    d = np.abs(np.fft.rfft(g, axis=1))[:, 1:harmonics + 1].ravel()
    return d / (np.linalg.norm(d) + 1e-12)


def panorama_pairs(n, overlap, descriptors=None, loops_per_frame=0, min_separation=10):
    """Sequential pairs (i, i+1..i+overlap) plus top-k appearance loop candidates beyond min_separation."""
    pairs = {(i, j) for i in range(n) for j in range(i + 1, min(n, i + overlap + 1))}
    if descriptors is not None and loops_per_frame > 0:
        D = np.asarray(descriptors); S = D @ D.T
        for i in range(n):
            far = [j for j in np.argsort(-S[i]) if abs(int(j) - i) >= min_separation]
            for j in far[:loops_per_frame]:
                pairs.add((min(i, int(j)), max(i, int(j))))
    return sorted(pairs)

# ---------------------------------------------------------------- rotations and similarity

def quat_from_matrix(R):
    R = np.asarray(R, float); t = np.trace(R)
    if t > 0:
        s = math.sqrt(t + 1) * 2; q = [(R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s, s / 4]
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1 + R[0, 0] - R[1, 1] - R[2, 2]) * 2; q = [s / 4, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s, (R[2, 1] - R[1, 2]) / s]
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1 + R[1, 1] - R[0, 0] - R[2, 2]) * 2; q = [(R[0, 1] + R[1, 0]) / s, s / 4, (R[1, 2] + R[2, 1]) / s, (R[0, 2] - R[2, 0]) / s]
    else:
        s = math.sqrt(1 + R[2, 2] - R[0, 0] - R[1, 1]) * 2; q = [(R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, s / 4, (R[1, 0] - R[0, 1]) / s]
    q = np.array(q); q /= np.linalg.norm(q)
    return q if q[3] >= 0 else -q


def matrix_from_quat(q):
    x, y, z, w = np.asarray(q, float) / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def rotation_angle_deg(R):
    return math.degrees(math.acos(np.clip((np.trace(R) - 1) / 2, -1, 1)))


def rotvec(R):
    ang = math.acos(np.clip((np.trace(R) - 1) / 2, -1, 1))
    if ang < 1e-9:
        return np.zeros(3)
    v = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    n = np.linalg.norm(v)
    if n < 1e-9:  # ~180 deg
        w, V = np.linalg.eigh(R); v = V[:, np.argmax(w)]; return v * ang
    return v / n * ang


def exp_so3(w):
    a = np.linalg.norm(w)
    if a < 1e-12:
        return np.eye(3)
    k = w / a; K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K


def slerp(Ra, Rb, t):
    return Ra @ exp_so3(t * rotvec(Ra.T @ Rb))


def umeyama(src, dst, with_scale=True):
    """Least-squares similarity dst ~ s R src + t (Umeyama 1991). Returns s, R, t."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    if src.shape != dst.shape or src.shape[0] < 3:
        raise ValueError('Need >= 3 corresponding points')
    mu_s, mu_d = src.mean(0), dst.mean(0); a, b = src - mu_s, dst - mu_d
    U, S, Vt = np.linalg.svd(b.T @ a / len(src))
    D = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[2, 2] = -1
    R = U @ D @ Vt
    var = (a ** 2).sum() / len(src)
    s = float(np.trace(np.diag(S) @ D) / var) if with_scale else 1.0
    return s, R, mu_d - s * R @ mu_s


def planar_rank_ok(points, tol=1e-3):
    """True when points span at least a 2D area (not collinear)."""
    p = np.asarray(points, float); p = p - p.mean(0)
    sv = np.linalg.svd(p, compute_uv=False)
    return len(sv) >= 2 and sv[1] > tol * max(sv[0], 1e-12)


def level_rotation(up):
    """Smallest rotation taking unit vector `up` onto +Z."""
    u = np.asarray(up, float) / np.linalg.norm(up); z = np.array([0, 0, 1.0])
    axis = np.cross(u, z); s = np.linalg.norm(axis); c = float(u @ z)
    if s < 1e-12:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    return exp_so3(axis / s * math.atan2(s, c))


def up_from_panoramas(R_world_from_pano):
    """Camera is carried upright: the mean panorama +Z axis in the world is the up estimate."""
    z = np.array([R[:, 2] for R in R_world_from_pano]).mean(0)
    return z / np.linalg.norm(z)

# ---------------------------------------------------------------- metric scale

def floor_distances(centres, points, up, radius, min_points=8, low_fraction=0.3):
    """Per camera: robust distance to the local floor below it, in reconstruction units (NaN if too few points).

    Points within `radius` horizontally and below the camera are taken; the floor is the lowest `low_fraction`
    of them, fitted with a local plane evaluated directly below the camera. Local (not one global plane) so
    raked floors and steps are tolerated; furniture above the floor is excluded by the lowest-layer rule.
    """
    C, P = np.asarray(centres, float), np.asarray(points, float); u = np.asarray(up, float) / np.linalg.norm(up)
    out = np.full(len(C), np.nan)
    for i, c in enumerate(C):
        rel = P - c; h = -(rel * u).sum(1); hvec = rel + np.outer(h, u); horiz = np.linalg.norm(hvec, axis=1)
        sel = (horiz < radius) & (h > 0)
        if sel.sum() < min_points:
            continue
        hs = h[sel]; low = hs >= np.percentile(hs, 100 * (1 - low_fraction))
        if low.sum() < 3:
            out[i] = float(np.median(hs[low])); continue
        # local plane through the lowest layer, evaluated directly below the camera (removes slope bias)
        e1 = np.cross(u, [1, 0, 0] if abs(u[0]) < 0.9 else [0, 1, 0]); e1 /= np.linalg.norm(e1); e2 = np.cross(u, e1)
        X = np.c_[hvec[sel][low] @ e1, hvec[sel][low] @ e2, np.ones(low.sum())]
        coef, *_ = np.linalg.lstsq(X, hs[low], rcond=None)
        out[i] = float(coef[2]) if np.isfinite(coef[2]) else float(np.median(hs[low]))
    return out


def camera_height_scale(distances, camera_height_m):
    d = np.asarray(distances, float); d = d[np.isfinite(d) & (d > 0)]
    if len(d) < 3:
        raise ValueError('Fewer than 3 cameras have enough floor points below them; camera-height scale unavailable')
    per = camera_height_m / d
    return {'scale': float(camera_height_m / np.median(d)), 'camerasUsed': int(len(d)),
            'perCameraScaleP10': float(np.percentile(per, 10)), 'perCameraScaleP90': float(np.percentile(per, 90)),
            'relativeSpreadIQR': float((np.percentile(per, 75) - np.percentile(per, 25)) / np.median(per))}


def fit_plane_ransac(points, up, max_tilt_deg=15, threshold=0.02, iters=500, seed=0):
    """Dominant plane roughly perpendicular to `up`; returns (normal, d, inlier_count) with n.x + d = 0."""
    P = np.asarray(points, float); rng = np.random.default_rng(seed); best = (None, None, 0)
    u = np.asarray(up, float) / np.linalg.norm(up)
    if len(P) < 3:
        return best
    for _ in range(iters):
        a, b, c = P[rng.choice(len(P), 3, replace=False)]
        n = np.cross(b - a, c - a); nn = np.linalg.norm(n)
        if nn < 1e-12:
            continue
        n /= nn; n = n if n @ u > 0 else -n
        if math.degrees(math.acos(min(1, n @ u))) > max_tilt_deg:
            continue
        d = -n @ a; cnt = int((np.abs(P @ n + d) < threshold).sum())
        if cnt > best[2]:
            best = (n, float(d), cnt)
    return best


def landmark_similarity(pairs, checks=(), distances=()):
    """Scan(reconstruction) -> BIM similarity from landmark pairs; optional taped/laser distances for scale only.

    pairs/checks: [{'scan':[x,y,z], 'bim':[x,y,z]}]; distances: [{'a':[..], 'b':[..], 'metres': d}] in scan frame.
    """
    out = {}
    if distances:
        ratios = [d['metres'] / np.linalg.norm(np.subtract(d['a'], d['b'])) for d in distances]
        out['distanceScale'] = float(np.median(ratios)); out['distanceScaleSpread'] = float(np.ptp(ratios)) if len(ratios) > 1 else None
    if pairs:
        src = np.array([p['scan'] for p in pairs], float); dst = np.array([p['bim'] for p in pairs], float)
        if len(src) < 3 or not planar_rank_ok(src) or not planar_rank_ok(dst):
            raise ValueError('Need 3+ non-collinear landmark pairs')
        s, R, t = umeyama(src, dst)
        res = np.linalg.norm((s * (R @ src.T)).T + t - dst, axis=1)
        out.update({'scale': s, 'rotation': R.tolist(), 'translation': t.tolist(), 'fitRmsMetres': float(np.sqrt((res ** 2).mean())),
                    'fitMaxMetres': float(res.max())})
        if checks:
            cs = np.array([c['scan'] for c in checks], float); cb = np.array([c['bim'] for c in checks], float)
            ce = np.linalg.norm((s * (R @ cs.T)).T + t - cb, axis=1); out['checkErrorsMetres'] = ce.tolist(); out['checkMaxMetres'] = float(ce.max())
    return out

# ---------------------------------------------------------------- IMU

def integrate_gyro(t_ms, gyro, t0, t1):
    """Relative rotation of the IMU body between times t0 and t1 (R_body0_from_body1), first-order integration."""
    t = np.asarray(t_ms); i0, i1 = np.searchsorted(t, t0), np.searchsorted(t, t1)
    R = np.eye(3)
    for k in range(max(i0, 1), min(i1, len(t))):
        R = R @ exp_so3(gyro[k] * (t[k] - t[k - 1]) / 1000.0)
    return R


def kabsch_rotation(a, b):
    """R minimizing sum |R a_i - b_i|^2 (rotation only)."""
    H = np.asarray(a, float).T @ np.asarray(b, float); U, _, Vt = np.linalg.svd(H)
    D = np.diag([1, 1, np.sign(np.linalg.det(Vt.T @ U.T))])
    return Vt.T @ D @ U.T

# ---------------------------------------------------------------- export / validation

def images_json_record(guid, file, sha256, width, height, position, quaternion, extra=None):
    """One record in the extract_e57_images.py `images.json` shape accepted by capture_import.prepare."""
    q = [float(v) for v in quaternion]
    rec = {'guid': guid, 'name': guid,
           'pose': {'translation': dict(zip('xyz', [float(v) for v in position])), 'rotation': dict(zip('xyzw', q))},
           'representations': [{'projection': 'sphericalRepresentation', 'file': file, 'dimensions': [width, height], 'sha256': sha256,
                                'imageWidth': width, 'imageHeight': height, 'pixelWidth': 2 * math.pi / width, 'pixelHeight': math.pi / height}]}
    if extra:
        rec.update(extra)
    return rec


def yup_to_e57(p):
    return [p[0], -p[2], p[1]]


def interpolate_track(frames, positions, rotations, query, max_gap):
    """Pose at frame `query` from a sorted keyframe track; exact if present, else lerp/slerp within max_gap frames."""
    frames = list(frames)
    if query in frames:
        i = frames.index(query); return positions[i], rotations[i], 'exact'
    k = int(np.searchsorted(frames, query))
    if k == 0 or k == len(frames) or frames[k] - frames[k - 1] > max_gap:
        return None
    t = (query - frames[k - 1]) / (frames[k] - frames[k - 1])
    return (1 - t) * np.asarray(positions[k - 1]) + t * np.asarray(positions[k]), slerp(rotations[k - 1], rotations[k], t), 'interpolated'


def yaw_shift_deg(a, b, valid_rows=None):
    """Signed yaw (deg) such that rolling equirect b by it best matches a (circular correlation of gradients)."""
    def grad(x):
        x = x.astype(np.float32); gx = np.roll(x, -1, 1) - np.roll(x, 1, 1); gy = np.zeros_like(x); gy[1:-1] = x[2:] - x[:-2]
        g = np.hypot(gx, gy)
        if valid_rows is not None:
            g = g[valid_rows]
        return (g - g.mean()) / (g.std() + 1e-6)
    A, B = grad(a), grad(b)
    corr = np.fft.irfft(np.sum(np.fft.rfft(A, axis=1) * np.conj(np.fft.rfft(B, axis=1)), 0), n=a.shape[1])
    s = int(np.argmax(corr)); w = a.shape[1]
    s = s - w if s > w / 2 else s
    # rolling right by s columns = decreasing azimuth: content moved by -360*s/w degrees
    return -360.0 * s / w, float(corr.max() / (A.size))


def error_summary(values):
    v = np.asarray([x for x in values if x is not None and np.isfinite(x)], float)
    if not len(v):
        return {'n': 0}
    return {'n': int(len(v)), 'median': float(np.median(v)), 'p90': float(np.percentile(v, 90)), 'max': float(v.max()), 'mean': float(v.mean())}


def wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0


def dumps(obj):
    return json.dumps(obj, indent=2, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o)) + '\n'
