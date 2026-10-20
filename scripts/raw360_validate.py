"""Validation of a raw360 run against a reference station manifest (e.g. the Cupix Sep 17 export).

The reference is used ONLY here, never as pipeline input. Stations are matched by video frame number
(reference sourceFrame = 0-based frame index + frame_base). Reports, per run, a JSON plus one markdown table row so
methods/parameters can be compared: registration rate, position error after a best-fit similarity (and after a
rigid fit with our metric scale), fitted scale factor, heading error from image alignment, IMU rotation agreement,
runtimes and parameters. Errors are relative to another reconstruction, not surveyed ground truth.
"""
import json, math, time
from pathlib import Path
import numpy as np
import raw360_core as core


def _gray(path, size=(512, 256)):
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert('L').resize(size, Image.Resampling.BOX), dtype=np.float32)


def imu_agreement(work, track):
    """Compare SfM relative rotations of consecutive registered keyframes with gyro integration.

    Rotation angle magnitudes are frame-independent; a hand-eye rotation (pano <- IMU) is solved by Kabsch
    on rotation vectors and the remaining residual reported. Also: gravity (accel) mapped through it vs SfM up.
    """
    z_path = work / 'imu.npz'
    if not z_path.exists() or len(track) < 4:
        return None
    z = np.load(z_path)
    if 'frame_times_ms' not in z:
        return None
    ft, t, gyr, acc = z['frame_times_ms'], z['imu_t_ms'], z['gyro_rad_s'], z['accel_g']
    pairs = []
    for (fa, Ra), (fb, Rb) in zip(track[:-1], track[1:]):
        if fb >= len(ft):
            continue
        R_cam = Ra.T @ Rb; R_imu = core.integrate_gyro(t, gyr, ft[fa], ft[fb])
        pairs.append((fa, fb, R_cam, R_imu))
    if len(pairs) < 3:
        return None
    ang_diff = [abs(core.rotation_angle_deg(c) - core.rotation_angle_deg(i)) for _, _, c, i in pairs]
    big = [(core.rotvec(i), core.rotvec(c)) for _, _, c, i in pairs if core.rotation_angle_deg(c) > 2]
    out = {'pairs': len(pairs), 'angleMagnitudeDiffDeg': core.error_summary(ang_diff),
           'sfmRelativeAngleDeg': core.error_summary([core.rotation_angle_deg(c) for _, _, c, _ in pairs])}
    if len(big) >= 3:
        X = core.kabsch_rotation([b[0] for b in big], [b[1] for b in big])
        res = [core.rotation_angle_deg(c.T @ X @ i @ X.T) for _, _, c, i in pairs]
        out['handEyeResidualDeg'] = core.error_summary(res); out['panoFromImu'] = X.tolist()
        tilts = []
        for f, Rw in track:
            if f < len(ft):
                lo, hi = np.searchsorted(t, ft[f] - 250), np.searchsorted(t, ft[f] + 250)
                if hi - lo > 2:
                    g = acc[lo:hi].mean(0); up = Rw @ (X @ (g / np.linalg.norm(g)))
                    tilts.append(math.degrees(math.acos(np.clip(up[2], -1, 1))))
        out['gravityVsSfmUpDeg'] = core.error_summary(tilts)
        out['note'] = ('Gravity from mean accelerometer over +-250 ms mapped by the fitted hand-eye rotation; compares the IMU '
                       'up direction with the levelled reconstruction (+Z). Frame/IMU time sync is assumed from trailer timestamps.')
    return out


def run(work, a):
    import raw360_pipeline as pipe
    t0 = time.time(); work = Path(work)
    res = pipe.sfm_result(work, a.method); frames_meta = pipe.load(work / 'frames.json')
    scale_path = work / 'sfm' / a.method / 'scale.json'; metric = scale_path.exists()
    if metric:
        poses, _, sc = pipe.export_poses(work, a.method)
    else:
        sc = None
        poses = [{'frame': r['frame'], 'pano': r['pano'], 'position': np.array(r['centre']), 'worldFromPano': np.array(r['worldFromPano'])}
                 for r in res['frames'] if r['registered']]
    poses.sort(key=lambda p: p['frame'])
    ref_path = Path(a.reference); ref = json.loads(ref_path.read_text())
    frames = [p['frame'] for p in poses]; pos = [np.asarray(p['position'], float) for p in poses]; rots = [np.asarray(p['worldFromPano']) for p in poses]
    lo, hi = frames_meta['range']
    matches = []
    for st in ref['stations']:
        q = int(st['sourceFrame']) - a.frame_base
        if not lo <= q < hi:
            continue
        m = core.interpolate_track(frames, pos, rots, q, a.max_interp_gap) if poses else None
        matches.append({'id': st['id'], 'sourceFrame': st['sourceFrame'], 'frame': q, 'status': m[2] if m else 'unmatched',
                        'ours': m[0].tolist() if m else None, 'oursR': m[1] if m else None,
                        'ref': core.yup_to_e57(st['position']), 'refR': core.matrix_from_quat(st['e57Quaternion']), 'file': st['file']})
    used = [m for m in matches if m['ours'] is not None]
    out = {'schema': 'raw360-validation/1', 'method': a.method, 'reference': str(ref_path), 'referenceUse': 'validation only',
           'frameBase': a.frame_base, 'maxInterpGapFrames': a.max_interp_gap, 'frameRange': [lo, hi],
           'registration': {'panoramas': res.get('registeredPanoramas', 0), 'totalPanoramas': res.get('totalPanoramas'),
                            'images': res.get('registeredImages', 0), 'totalImages': res.get('totalImages'),
                            'rate': (res.get('registeredPanoramas', 0) / res['totalPanoramas']) if res.get('totalPanoramas') else 0},
           'reprojectionErrorPx': res.get('meanReprojectionErrorPx'), 'points3D': res.get('points3D'),
           'referenceStationsInRange': len(matches), 'matchedExact': sum(m['status'] == 'exact' for m in used),
           'matchedInterpolated': sum(m['status'] == 'interpolated' for m in used),
           'scale': {'metricExport': metric, 'method': sc.get('scaleMethod') if sc else None,
                     'estimate': (sc.get('cameraHeight') or {}).get('scale') if sc else None,
                     'cameraHeightMetres': sc.get('cameraHeightMetres') if sc else None}}
    if len(used) >= 3 and core.planar_rank_ok([m['ours'] for m in used]):
        A = np.array([m['ours'] for m in used]); B = np.array([m['ref'] for m in used])
        s, R, t = core.umeyama(A, B); err = np.linalg.norm((s * (R @ A.T)).T + t - B, axis=1)
        for m, e in zip(used, err):
            m['simErr'] = float(e)
        out['similarityFit'] = {'scale': s, 'all': core.error_summary(err),
                                'exactOnly': core.error_summary([m['simErr'] for m in used if m['status'] == 'exact']),
                                'interpolatedOnly': core.error_summary([m['simErr'] for m in used if m['status'] == 'interpolated'])}
        if metric:
            out['similarityFit']['scaleErrorPercent'] = (s - 1) * 100
            s1, R1, t1 = core.umeyama(A, B, with_scale=False); e1 = np.linalg.norm((R1 @ A.T).T + t1 - B, axis=1)
            out['rigidFitUsingOurScale'] = core.error_summary(e1)
        refspan = float(np.linalg.norm(B.max(0) - B.min(0))); out['referenceExtentMetres'] = refspan
        if not a.no_heading:
            out['heading'] = heading_errors(work, used, R, ref_path.parent, pipe, frames_meta)
    else:
        out['similarityFit'] = {'error': 'fewer than 3 non-collinear matched stations'}
    out['imuRotation'] = imu_agreement(work, [(p['frame'], np.asarray(p['worldFromPano'])) for p in poses])
    out['runtimeSeconds'] = {'frames': frames_meta.get('seconds'), 'sfm': res.get('seconds'), 'validate': round(time.time() - t0, 1)}
    out['parameters'] = {'selection': frames_meta.get('selection'), 'viewMode': frames_meta.get('viewMode'),
                         'rig': [(v['name'], v.get('yawDeg'), v.get('hfovDeg')) for v in frames_meta.get('rig') or []],
                         'sfm': res.get('options'), 'pairs': (res.get('database') or {}).get('panoramaPairs')}
    out['stations'] = [{k: v for k, v in m.items() if k not in ('oursR', 'refR')} for m in matches]
    (work / 'sfm' / a.method / 'validation.json').write_text(core.dumps(out))
    row = table_row(work, out)
    table = Path(a.runs_table); table.parent.mkdir(parents=True, exist_ok=True)
    if not table.exists():
        table.write_text(TABLE_HEADER)
    with table.open('a') as f:
        f.write(row + '\n')
    print(TABLE_HEADER + row)
    return out


def heading_errors(work, used, R_sim, ref_dir, pipe, frames_meta):
    """Yaw offset between world-aligned reference and our panoramas of the same frame (image alignment)."""
    from PIL import Image
    probe = pipe.load(work / 'probe.json'); need = sorted({m['frame'] for m in used if m['status'] != 'exact'})
    vdir = work / 'validate-panos'
    missing = [f for f in need if not (vdir / f'f{f:06d}.jpg').exists()]
    if missing:
        pipe.stitch_full(probe, missing, vdir, 1024)
    band = np.abs(90 - (np.arange(256) + 0.5) / 256 * 180) < 45
    errs = []
    for m in used:
        ours_file = (work / 'panos' if m['status'] == 'exact' else vdir) / f"f{m['frame']:06d}.jpg"
        ref_file = ref_dir / 'mobile' / m['file']
        ref_file = ref_file if ref_file.exists() else ref_dir / m['file']
        a = core.rotate_equirect(_gray(ours_file), R_sim @ m['oursR'])
        b = core.rotate_equirect(_gray(ref_file), m['refR'])
        shift, score = core.yaw_shift_deg(b, a, band)
        m['headingErrDeg'] = float(core.wrap_deg(shift)); m['headingScore'] = score; errs.append(abs(m['headingErrDeg']))
    signed = [m['headingErrDeg'] for m in used]
    return {'absDeg': core.error_summary(errs), 'medianSignedDeg': float(np.median(signed)),
            'absAfterRemovingMedianDeg': core.error_summary([abs(core.wrap_deg(x - np.median(signed))) for x in signed]),
            'exactOnlyAbsDeg': core.error_summary([abs(m['headingErrDeg']) for m in used if m['status'] == 'exact']),
            'method': 'grey 512x256 equirects rotated into the reference world frame; circular cross-correlation of gradient '
                      'magnitude over +-45 deg elevation. Large values can also mean a failed image correlation.'}


TABLE_HEADER = ('| run | method | reg pano | reg img | reproj px | scale est | sim scale | pos med m | pos p90 m | rigid med m | '
                'heading med deg | heading p90 deg | matched ex/int | sfm s (features+match+map) | params |\n'
                '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n')


def table_row(work, o):
    def f(x, d=2):
        return '-' if x is None else (f'{x:.{d}f}' if isinstance(x, float) else str(x))
    sim = o.get('similarityFit', {}); h = (o.get('heading') or {}).get('absDeg', {}); sec = o['runtimeSeconds'].get('sfm') or {}; sfm_s = float(sum((sec.get('database') or {}).values()) + (sec.get('mapping') or 0)) if sec else None
    p = o['parameters']; sel = p.get('selection') or {}
    params = f"count={sel.get('count')} gap={sel.get('maxGap')} views={len(p.get('rig') or [])} pairs={p.get('pairs')} ov={(p.get('sfm') or {}).get('overlap')} loops={(p.get('sfm') or {}).get('loops')}"
    r = o['registration']
    return (f"| {Path(work).name} | {o['method']} | {r['panoramas']}/{r['totalPanoramas']} | {r['images']}/{r['totalImages']} | {f(o.get('reprojectionErrorPx'))} | "
            f"{f(o['scale'].get('estimate'), 4)} | {f(sim.get('scale'), 3)} | {f((sim.get('all') or {}).get('median'))} | {f((sim.get('all') or {}).get('p90'))} | "
            f"{f((o.get('rigidFitUsingOurScale') or {}).get('median'))} | {f(h.get('median'), 1)} | {f(h.get('p90'), 1)} | {o['matchedExact']}/{o['matchedInterpolated']} | {f(sfm_s, 0)} | {params} |")
