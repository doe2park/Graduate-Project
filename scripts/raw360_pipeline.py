"""Local raw Insta360 ONE X2 (dual INSV) -> posed equirect panoramas for capture_import.py.

No cloud services, no Cupix, no Insta360 Studio. Tools: ffmpeg/ffprobe, pycolmap (project venv), numpy, Pillow.
Subcommands: probe, frames, sfm, scale, export, validate, privacy. See docs/RAW360_PIPELINE.md.
All outputs go under a work directory (default work/raw360/<run>) and capture-local/; raw inputs are read only.
"""
import argparse, hashlib, json, math, os, platform, shutil, subprocess, sys, time
from fractions import Fraction
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import raw360_core as core  # noqa: E402

FFMPEG = os.environ.get('FFMPEG', shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg')
FFPROBE = os.environ.get('FFPROBE', shutil.which('ffprobe') or '/opt/homebrew/bin/ffprobe')
LOWRES = (1024, 512)      # scoring equirect
TINY = (256, 128)         # motion / static mask / place descriptor


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(core.dumps(obj))


def tool_versions():
    out = {'python': platform.python_version(), 'numpy': np.__version__, 'platform': platform.platform()}
    try:
        out['ffmpeg'] = subprocess.run([FFMPEG, '-version'], capture_output=True, text=True).stdout.splitlines()[0]
    except OSError:
        out['ffmpeg'] = None
    try:
        import PIL; out['pillow'] = PIL.__version__
    except ImportError:
        pass
    try:
        import pycolmap; out['pycolmap'] = pycolmap.__version__
        out['colmap'] = getattr(pycolmap, 'COLMAP_version', None)
    except ImportError:
        out['pycolmap'] = None
    return out


def stitch_filter(fov_deg, out_w, out_h, frames=None, gray=False, ops=('transpose=1', 'transpose=2')):
    """ffmpeg filtergraph: X2 lens files (_00_, _10_) -> upright dual fisheye -> equirect (E57 pixel convention).

    The X2 sensor images are rotated 90 deg; _00_ is turned clockwise (transpose=1), _10_ counter-clockwise
    (transpose=2), then hstacked as v360 'dfisheye'; the _10_ lens lands at the equirect centre (+X). Verified on
    Sep 17 (floor down, no mirroring; fisheye-rig heading check); repeat the check for another body or firmware.
    """
    sel = ''
    if frames is not None:
        sel = 'select=' + "'" + '+'.join(f'eq(n\\,{int(n)})' for n in frames) + "'" + ','
    fmt = ',format=gray' if gray else ''
    o0, o1 = (o if o and o != 'none' else 'null' for o in ops)
    return (f'[0:v]{sel}{o0}[a];[1:v]{sel}{o1}[b];[a][b]hstack=inputs=2,'
            f'v360=input=dfisheye:output=equirect:ih_fov={fov_deg:.3f}:iv_fov={fov_deg:.3f}:w={out_w}:h={out_h}:interp=cubic{fmt}')


def lens_paths(probe):
    return probe['inputs']['front']['path'], probe['inputs']['back']['path']


def lens_streams(probe):
    """Video stream index of each lens inside its file: (0, 0) for the dual-file _00_/_10_ layout; (0, 1) for a single
    _00_ file carrying both lenses as two streams (Oct 2026 X2 recordings)."""
    return probe['inputs']['front'].get('stream', 0), probe['inputs']['back'].get('stream', 0)


def lens_ops(probe):
    """Per-lens upright filter: Sep 17 dual-file X2 sensor images are rotated 90 deg (transpose=1 / =2); the Oct 18
    single-file recordings are already upright ('none'). Stored in probe.json as lensOps."""
    return tuple(probe.get('lensOps') or ('transpose=1', 'transpose=2'))


def with_streams(fg, probe):
    """Point the filtergraph's [0:v] / [1:v] at the lens streams (no-op for the dual-file layout)."""
    s0, s1 = lens_streams(probe)
    return fg.replace('[0:v]', f'[0:v:{s0}]').replace('[1:v]', f'[1:v:{s1}]')

# ------------------------------------------------------------------ probe

def cmd_probe(a):
    t0 = time.time(); work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    inputs = {}
    if a.dual_stream:
        if a.front or a.back:
            raise SystemExit('--dual-stream replaces --front/--back')
        # stream 0 plays the _00_ role, stream 1 the _10_ role (check the stitch heading against a reference)
        roles = [('front', a.dual_stream, 0), ('back', a.dual_stream, 1)]
    elif a.front and a.back:
        roles = [('front', a.front, None), ('back', a.back, None)]
    else:
        raise SystemExit('give --front and --back, or --dual-stream')
    for role, path, stream in roles:
        path = str(Path(path).resolve())
        info = json.loads(subprocess.run([FFPROBE, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', path],
                                         capture_output=True, text=True, check=True).stdout)
        vs = [s for s in info['streams'] if s['codec_type'] == 'video']
        if stream is not None and len(vs) < 2:
            raise SystemExit(f'{path}: --dual-stream needs two video streams, found {len(vs)}')
        v = vs[stream or 0]
        inputs[role] = ({'stream': stream} if stream is not None else {})
        inputs[role].update({'path': path, 'bytes': os.path.getsize(path), 'sha256': None if a.no_hash else sha256(path),
                        'codec': v['codec_name'], 'width': v['width'], 'height': v['height'], 'fps': v['avg_frame_rate'],
                        'frames': int(v.get('nb_frames', 0)), 'duration': float(info['format']['duration'])})
        if stream is not None and role == 'back':
            inputs[role]['sha256'] = inputs['front']['sha256']
    trailer = {}; imu_summary = None; calib = []; fov = None; fov_err = None
    with open(inputs['front']['path'], 'rb') as f:
        idx = core.parse_trailer_index(f, inputs['front']['bytes'])
        if idx:
            trailer = {core.RECORD_NAMES.get(k, hex(k)): {'id': hex(k), 'offset': o, 'bytes': n} for k, (o, n) in ((k, v) for k, v in idx.items() if k != '_version')}
            trailer['_version'] = idx['_version']
            def rec(rid):
                o, n = idx[rid]; f.seek(o); return f.read(n)
            if 0x101 in idx:
                calib = core.parse_lens_calibration(rec(0x101))
            arrays = {}
            if 0x600 in idx:
                arrays['frame_times_ms'] = core.parse_frame_times(rec(0x600))
            if 0x300 in idx:
                t, acc, gyr = core.parse_imu(rec(0x300)); arrays.update(imu_t_ms=t, accel_g=acc, gyro_rad_s=gyr)
                dt = np.diff(t)
                imu_summary = {'samples': int(len(t)), 'medianIntervalMs': float(np.median(dt)), 'spanSeconds': float((t[-1] - t[0]) / 1000),
                               'accelNormMedian_g': float(np.median(np.linalg.norm(acc, axis=1))),
                               'gyroUnitsAssumed': 'rad/s', 'accelUnitsAssumed': 'g', 'layout': 'u64 ms + 6 x f64 (accel xyz, gyro xyz)'}
            if arrays:
                np.savez(work / 'imu.npz', **arrays)
            if 'frame_times_ms' in arrays and imu_summary:
                ft = arrays['frame_times_ms']; imu_summary['frameTimestamps'] = int(len(ft))
                imu_summary['frameIntervalMedianMs'] = float(np.median(np.diff(ft)))
                imu_summary['captureSpanSeconds'] = float((ft[-1] - ft[0]) / 1000)
    if calib and not a.fov:
        fov, fov_err = core.equidistant_fov_from_mei(calib[0], inputs['front']['width'])
    probe = {'schema': 'raw360-probe/1', 'inputs': inputs, 'trailer': trailer, 'lensCalibration': calib,
             'stitchFovDeg': a.fov if a.fov else round(fov, 3) if fov else a.default_fov,
             'stitchFovSource': ('explicit --fov: ' + (a.fov_source or 'no source given')) if a.fov else
                                'equidistant least-squares fit to INSV trailer Mei calibration (theta<=90 deg)' if fov else 'default; no calibration found',
             'equidistantModelMaxErrorPx': fov_err, 'imu': imu_summary,
             'lensOps': [o.strip() for o in a.lens_ops.split(',')] if a.lens_ops else ['transpose=1', 'transpose=2'],
             'notes': [('Single INSV with both lenses as video streams 0 (_00_ role) and 1 (_10_ role); frame index n assumed simultaneous.'
                        if a.dual_stream else 'Lens files are separate streams; frame index n is assumed simultaneous in both files.'),
                       f"Frame counts front/back: {inputs['front']['frames']}/{inputs['back']['frames']}.",
                       'Trailer layout is interpreted from observed bytes, not a vendor specification.'],
             'tools': tool_versions(), 'seconds': round(time.time() - t0, 2)}
    save(work / 'probe.json', probe)
    print(json.dumps({k: probe[k] for k in ['stitchFovDeg', 'equidistantModelMaxErrorPx', 'imu']}, indent=2))

# ------------------------------------------------------------------ frames

def ffmpeg_frames(probe, start, end, size, gray=True):
    """Stream low-res stitched equirect frames [start, end) as numpy arrays."""
    front, back = lens_paths(probe); w, h = size
    fg = stitch_filter(probe['stitchFovDeg'], w, h, gray=gray, ops=lens_ops(probe)).replace('[0:v]', f"[0:v]trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS,scale=1440:1440,", 1)
    fg = with_streams(fg.replace('[1:v]', f"[1:v]trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS,scale=1440:1440,", 1), probe)
    cmd = [FFMPEG, '-v', 'error', '-i', front, '-i', back, '-filter_complex', fg, '-f', 'rawvideo', '-pix_fmt', 'gray', '-fps_mode', 'passthrough', '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE); n = w * h
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w)
    if p.wait() != 0:
        raise RuntimeError('ffmpeg scoring pass failed')


def frame_chunks(frames, size=60):
    frames = sorted(int(f) for f in frames)
    return [frames[i:i + size] for i in range(0, len(frames), size)]


def stitch_full(probe, frames, out_dir, width):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / '_tmp'; shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
    front, back = lens_paths(probe); made = []
    for k, chunk in enumerate(frame_chunks(frames)):  # ffmpeg's expression parser fails (ENOMEM) on ~>100 eq() terms
        fg = with_streams(stitch_filter(probe['stitchFovDeg'], width, width // 2, frames=chunk, ops=lens_ops(probe)), probe)
        subprocess.run([FFMPEG, '-v', 'error', '-i', front, '-i', back, '-filter_complex', fg, '-fps_mode', 'passthrough',
                        '-q:v', '2', str(tmp / f'c{k:03d}_%05d.jpg')], check=True)
        made += sorted(tmp.glob(f'c{k:03d}_*.jpg'))
    if len(made) != len(frames):
        raise RuntimeError(f'Stitched {len(made)} images for {len(frames)} requested frames')
    names = []
    for f, src in zip(sorted(frames), made):
        name = f'f{f:06d}.jpg'; src.rename(out_dir / name); names.append(name)
    tmp.rmdir()
    return names


def view_rig(n_views, fov):
    return [{'name': f'v{k}', 'yawDeg': 360.0 * k / n_views, 'pitchDeg': 0.0, 'hfovDeg': fov} for k in range(n_views)]


def cmd_frames(a):
    from PIL import Image
    t0 = time.time(); work = Path(a.work); probe = load(work / 'probe.json')
    fps = float(Fraction(probe['inputs']['front']['fps']))
    nmax = min(probe['inputs']['front']['frames'], probe['inputs']['back']['frames'])
    start = a.start_frame; end = min(nmax, a.end_frame or nmax)
    if a.max_seconds:
        end = min(end, start + int(a.max_seconds * fps))
    lows, tiny, sharp = [], [], []
    for g in ffmpeg_frames(probe, start, end, LOWRES):
        sharp.append(core.sharpness(g))
        tiny.append(np.asarray(Image.fromarray(g).resize(TINY, Image.Resampling.BOX)))
    tiny = np.array(tiny); n = len(tiny)
    if n < 3:
        raise SystemExit('Too few frames decoded')
    el = np.degrees(np.pi * (0.5 - (np.arange(TINY[1]) + 0.5) / TINY[1]))
    keep = core.static_region_mask(tiny, valid_rows=el < -15) & core.nadir_mask(*TINY, a.nadir_deg)
    band = (np.abs(el) < 60)[:, None] & keep
    motion = [0.0] + [core.yaw_aligned_difference(tiny[i - 1], tiny[i], band)[0] for i in range(1, n)]
    floor = float(np.percentile(motion[1:], 5)); image_cue = [0.0] + [max(0.0, m - floor) for m in motion[1:]]
    imu_cue = None; cue_used = 'image'
    if a.motion_cue in ('imu', 'both') and (work / 'imu.npz').exists():
        z = np.load(work / 'imu.npz')
        if 'frame_times_ms' in z and len(z['frame_times_ms']) >= start + n:
            cue_all, _, rest = core.walking_cue(z['imu_t_ms'], z['accel_g'], z['frame_times_ms'])
            imu_cue = cue_all[start:start + n].tolist(); cue_used = f'imu (accel-std walking cue, rest level {rest:.4f} g)'
    motion_c = image_cue
    if imu_cue is not None:
        def norm(x):
            x = np.asarray(x, float); return x / max(1e-9, np.median(x[x > 0]) if (x > 0).any() else 1)
        motion_c = np.maximum(norm(imu_cue), norm(image_cue)).tolist() if a.motion_cue == 'both' else imu_cue
        if a.motion_cue == 'both':
            cue_used = 'max(normalized IMU walking cue, normalized yaw-aligned image change)'
    scores = {'frames': list(range(start, start + n)), 'imageMotionRaw': motion, 'imageMotionNoiseFloor': floor, 'imageCue': image_cue, 'imuCue': imu_cue,
              'cueUsed': cue_used, 'sharpness': sharp}
    save(work / 'frame-scores.json', scores)
    picks = core.select_keyframes(motion_c, sharp, count=a.count, step=a.step, window=a.window, max_gap=a.max_gap, min_gap=a.min_gap)
    if a.select_only:
        print(f'{len(picks)} keyframes: {[start + i for i in picks]}'); return
    if a.max_panoramas and len(picks) > a.max_panoramas:
        raise SystemExit(f'{len(picks)} keyframes exceed --max-panoramas {a.max_panoramas}; raise --step or lower --count')
    frames = [start + i for i in picks]
    t1 = time.time()
    names = stitch_full(probe, frames, work / 'panos', a.pano_width)
    t2 = time.time()
    # masks: nadir cone + operator/stick (static) region, at panorama resolution; optional external per-pano masks
    W, H = a.pano_width, a.pano_width // 2
    keep_full = np.asarray(Image.fromarray((keep * 255).astype(np.uint8)).resize((W, H), Image.Resampling.NEAREST)) > 127
    keep_full &= core.nadir_mask(W, H, a.nadir_deg)
    Image.fromarray((keep_full * 255).astype(np.uint8)).save(work / 'pano-mask.png')
    rig = view_rig(a.views, a.view_fov) if a.view_mode == 'pinhole-rig' else None
    records = []
    if a.view_mode == 'pinhole-rig':
        maps = []
        for v in rig:
            R = core.cam_from_pano(v['yawDeg'], v['pitchDeg']); mx, my, f = core.pinhole_maps(R, a.view_size, v['hfovDeg'], W, H)
            v.update(camFromPano=R.tolist(), model='PINHOLE', params=[f, f, (a.view_size - 1) / 2 + 0.5, (a.view_size - 1) / 2 + 0.5], size=[a.view_size, a.view_size])
            maps.append((mx, my))
        lut = (255 * (np.arange(256) / 255) ** (1 / a.gamma)).astype(np.uint8)
        for frame, name in zip(frames, names):
            pano = np.asarray(Image.open(work / 'panos' / name).convert('RGB'))
            mask = keep_full.copy()
            if a.extra_mask_dir:  # hook: e.g. person segmentation, equirect PNG named like the panorama, white = keep
                extra = Path(a.extra_mask_dir) / (Path(name).stem + '.png')
                if extra.exists():
                    mask &= np.asarray(Image.open(extra).convert('L').resize((W, H))) > 127
            for v, (mx, my) in zip(rig, maps):
                img = np.clip(core.remap_bilinear(pano, mx, my), 0, 255).astype(np.uint8)
                m = core.remap_bilinear(mask.astype(np.float32), mx, my) > 0.5
                (work / 'views' / v['name']).mkdir(parents=True, exist_ok=True); (work / 'masks' / v['name']).mkdir(parents=True, exist_ok=True)
                Image.fromarray(lut[img]).save(work / 'views' / v['name'] / name, quality=92)
                Image.fromarray((m * 255).astype(np.uint8)).save(work / 'masks' / v['name'] / (name + '.png'))
            records.append({'frame': frame, 'pano': name})
    else:  # fisheye-rig: raw lens images, no stitching in the SfM input
        rig = fisheye_rig_views(probe, frames, work, a)
        records = [{'frame': f, 'pano': nm} for f, nm in zip(frames, names)]
    meta = {'schema': 'raw360-frames/1', 'range': [start, end], 'fps': fps, 'decodedFrames': n, 'keyframes': records,
            'selection': {'count': a.count, 'step': a.step, 'window': a.window, 'maxGap': a.max_gap, 'minGap': a.min_gap, 'motionCue': cue_used},
            'viewMode': a.view_mode, 'rig': rig, 'panoWidth': W, 'gamma': a.gamma, 'nadirMaskDeg': a.nadir_deg,
            'staticMaskFraction': float(1 - keep.mean()), 'extraMaskDir': a.extra_mask_dir,
            'seconds': {'scoring': round(t1 - t0, 1), 'stitch': round(t2 - t1, 1), 'views': round(time.time() - t2, 1)}}
    save(work / 'frames.json', meta)
    print(f'{len(frames)} keyframes from frames {start}-{end - 1}; seconds {meta["seconds"]}')


def fisheye_rig_views(probe, frames, work, a):
    """Alternative SfM input: each lens as its own OPENCV_FISHEYE camera in a 2-sensor rig (no stitching).

    Initial intrinsics come from the equidistant fit to the INSV calibration; the inter-lens rotation is
    initialised as 180 deg about the camera's up axis and refined in bundle adjustment (sensor_from_rig).
    COLMAP cannot use rays beyond 90 deg off-axis, so each lens contributes <= a hemisphere.
    """
    from PIL import Image
    size = a.fisheye_size; front, back = lens_paths(probe); fov = probe['stitchFovDeg']
    f = size / math.radians(fov); c = size / 2
    rig = []
    ops = [o if o and o != 'none' else 'null' for o in lens_ops(probe)]
    for k, (path, tr, st) in enumerate([(front, ops[0], lens_streams(probe)[0]), (back, ops[1], lens_streams(probe)[1])]):
        d = work / 'views' / f'lens{k}'; d.mkdir(parents=True, exist_ok=True)
        made = []
        for ci, chunk in enumerate(frame_chunks(frames)):
            sel = "'" + '+'.join(f'eq(n\\,{n})' for n in chunk) + "'"
            subprocess.run([FFMPEG, '-v', 'error', '-i', path, '-map', f'0:v:{st}', '-vf', f'select={sel},{tr},scale={size}:{size}', '-fps_mode', 'passthrough',
                            '-q:v', '2', str(d / f'_c{ci:03d}_%05d.jpg')], check=True)
            made += sorted(d.glob(f'_c{ci:03d}_*.jpg'))
        for fr, src in zip(sorted(frames), made):
            src.rename(d / f'f{fr:06d}.jpg')
        yy, xx = np.mgrid[:size, :size]; r = np.hypot(xx - c + 0.5, yy - c + 0.5)
        m = r < f * math.radians(88)
        md = work / 'masks' / f'lens{k}'; md.mkdir(parents=True, exist_ok=True)
        for fr in frames:
            Image.fromarray((m * 255).astype(np.uint8)).save(md / f'f{fr:06d}.jpg.png')
        # ffmpeg dfisheye puts the right-hand input (_10_) at the equirect centre (+X): verified on the Sep 17 smoke
        # run, where the opposite assignment gave a constant ~180 deg heading error. So _00_ looks along -X.
        R = core.cam_from_pano(180.0 if k == 0 else 0.0)
        rig.append({'name': f'lens{k}', 'model': 'OPENCV_FISHEYE', 'params': [f, f, c, c, 0, 0, 0, 0], 'size': [size, size],
                    'camFromPano': R.tolist(), 'refineIntrinsics': True})
    return rig

# ------------------------------------------------------------------ sfm / scale / export / validate

def cmd_sfm(a):
    import raw360_sfm
    raw360_sfm.run(Path(a.work), a)


def sfm_result(work, method):
    return load(Path(work) / 'sfm' / method / 'sfm-result.json')


def cmd_scale(a):
    work = Path(a.work); res = sfm_result(work, a.method)
    regs = [r for r in res['frames'] if r['registered']]
    if len(regs) < 3:
        raise SystemExit('Fewer than 3 registered panoramas; no scale estimate')
    Rw = [np.array(r['worldFromPano']) for r in regs]; C = np.array([r['centre'] for r in regs])
    P = np.load(work / 'sfm' / a.method / 'points.npy')[:, :3]
    up = core.up_from_panoramas(Rw); L = core.level_rotation(up)
    step = float(np.median(np.linalg.norm(np.diff(C, axis=0), axis=1)))
    radius = a.radius_factor * step
    d = core.floor_distances(C, P, up, radius, min_points=a.min_floor_points)
    out = {'schema': 'raw360-scale/1', 'method': a.method, 'up': up.tolist(), 'medianStationStepUnits': step, 'floorRadiusUnits': radius,
           'cameraHeightMetres': a.camera_height, 'cameraHeightSource': a.height_source}
    try:
        est = core.camera_height_scale(d, a.camera_height); out['cameraHeight'] = est; s = est['scale']; out['scaleMethod'] = 'camera-height (local floor below each station)'
    except ValueError as e:
        out['cameraHeight'] = {'error': str(e)}; s = None
    plane = core.fit_plane_ransac(P[(C.mean(0) - P) @ up > 0], up, threshold=0.01 * step * 10)
    if plane[0] is not None:
        dist_plane = C @ plane[0] + plane[1]
        out['globalPlaneDiagnostic'] = {'inliers': plane[2], 'scale': float(a.camera_height / np.median(dist_plane)) if np.median(dist_plane) > 0 else None,
                                        'tiltFromUpDeg': math.degrees(math.acos(min(1, abs(plane[0] @ up)))), 'note': 'single plane; unreliable on raked floors'}
    if s is None:
        if not a.landmarks:
            save(work / 'sfm' / a.method / 'scale.json', out); raise SystemExit('No scale: camera-height failed and no landmarks given')
        s = 1.0; out['scaleMethod'] = 'landmarks only'
    # export frame: levelled, metric, origin at floor below the first registered station
    origin = s * (L @ C[0]) - np.array([0, 0, a.camera_height])
    T = {'scale': s, 'rotation': L.tolist(), 'translation': (-origin).tolist()}
    if a.landmarks:
        lm = load(a.landmarks); Ry = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0.0]])  # E57 z-up -> Y-up [x,z,-y]
        if lm.get('distances') and not lm.get('pairs'):
            r = core.landmark_similarity([], distances=lm['distances']); k = r['distanceScale']
            T = {'scale': s * k, 'rotation': L.tolist(), 'translation': (-origin * k).tolist()}; out['landmarks'] = r
            out['scaleMethod'] += ' + laser/tape distance rescale'
        elif lm.get('pairs'):
            r = core.landmark_similarity(lm['pairs'], lm.get('checks', []), lm.get('distances', [])); out['landmarks'] = r
            Rl, tl, sl = np.array(r['rotation']), np.array(r['translation']), r['scale']
            # landmark coords are Y-up metres in the export frame -> compose in E57 frame
            Re = Ry.T @ Rl @ Ry; te = Ry.T @ tl
            T = {'scale': s * sl, 'rotation': (Re @ L).tolist(), 'translation': (sl * Re @ (-origin) + te).tolist()}
            out['scaleMethod'] += ' + landmark similarity (scale, rotation, translation)'
            out['frameNote'] = 'Export is in the landmark (BIM) frame; provisional, not surveyed.'
    out['exportTransform'] = T
    out['note'] = 'Camera-height scale assumes the stated constant height above the local floor; it is an estimate, not surveyed accuracy.'
    save(work / 'sfm' / a.method / 'scale.json', out)
    print(json.dumps({k: out.get(k) for k in ['scaleMethod', 'cameraHeight', 'globalPlaneDiagnostic', 'landmarks']}, indent=2))


def export_poses(work, method):
    res = sfm_result(work, method); sc = load(Path(work) / 'sfm' / method / 'scale.json'); T = sc['exportTransform']
    s, R, t = T['scale'], np.array(T['rotation']), np.array(T['translation'])
    out = []
    for r in res['frames']:
        if r['registered']:
            out.append({'frame': r['frame'], 'pano': r['pano'], 'position': s * R @ np.array(r['centre']) + t,
                        'worldFromPano': R @ np.array(r['worldFromPano'])})
    return out, res, sc


def cmd_privacy(a):
    import raw360_privacy
    raw360_privacy.run(a)


def cmd_export(a):
    from PIL import Image
    work = Path(a.work); out = Path(a.out)
    if out.exists():
        raise SystemExit('Output exists; choose a new folder')
    poses, res, sc = export_poses(work, a.method); frames_meta = load(work / 'frames.json'); probe = load(work / 'probe.json')
    out.mkdir(parents=True); records = []
    for p in poses:
        src = work / 'panos' / p['pano']; dst = out / p['pano']; shutil.copyfile(src, dst)
        with Image.open(dst) as im:
            w, h = im.size
        q = core.quat_from_matrix(p['worldFromPano'])
        records.append(core.images_json_record(f"raw360_f{p['frame']:06d}", p['pano'], sha256(dst), w, h, p['position'], q,
                                               {'sourceFrame': p['frame'] + a.frame_base, 'videoFrameIndex0': p['frame']}))
    save(out / 'images.json', {'source': 'raw360_pipeline export (local SfM)', 'status': 'posed by local SfM; scale/alignment provisional', 'images': records})
    prov = {'schema': 'raw360-provenance/1', 'created': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'inputs': probe['inputs'], 'tools': tool_versions(), 'stitch': {'fovDeg': probe['stitchFovDeg'], 'source': probe['stitchFovSource'],
                                                                        'maxModelErrorPx': probe['equidistantModelMaxErrorPx'], 'engine': 'ffmpeg v360 dfisheye->equirect'},
            'frames': {k: frames_meta[k] for k in ['range', 'selection', 'viewMode', 'rig', 'panoWidth', 'gamma', 'nadirMaskDeg', 'staticMaskFraction', 'extraMaskDir', 'seconds']},
            'sfm': {k: res[k] for k in res if k != 'frames'}, 'scale': sc,
            'registeredPanoramas': len(poses), 'totalPanoramas': len(res['frames']),
            'frameNumbering': f'sourceFrame = 0-based ffmpeg frame index + {a.frame_base}',
            'limits': ['Metric scale from assumed camera height or landmarks; not surveyed.', 'Cupix outputs were not used as input.',
                       'Pose frame: E57-style Z-up metres; capture_import converts to Y-up.']}
    save(out / 'provenance.json', prov)
    print(f'Exported {len(poses)}/{len(res["frames"])} posed panoramas to {out}')


def cmd_validate(a):
    import raw360_validate
    raw360_validate.run(Path(a.work), a)


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='cmd', required=True)
    def w(sp):
        sp.add_argument('--work', required=True, help='work directory, e.g. work/raw360/sep17-smoke')
    s = sub.add_parser('probe'); w(s); s.add_argument('--front', help='..._00_NNN.insv'); s.add_argument('--back', help='..._10_NNN.insv')
    s.add_argument('--dual-stream', help='single ..._00_NNN.insv holding both lenses as video streams 0 and 1 (no _10_ file)')
    s.add_argument('--no-hash', action='store_true'); s.add_argument('--default-fov', type=float, default=197.0)
    s.add_argument('--fov', type=float, help='override the stitch FOV (e.g. when the trailer calibration is for another sensor mode)'); s.add_argument('--fov-source')
    s.add_argument('--lens-ops', help="per-lens upright filter for stream/file 0,1 (default 'transpose=1,transpose=2'; 'none,none' for upright Oct 18 streams)")
    s = sub.add_parser('frames'); w(s)
    s.add_argument('--start-frame', type=int, default=0); s.add_argument('--end-frame', type=int); s.add_argument('--max-seconds', type=float)
    s.add_argument('--count', type=int); s.add_argument('--step', type=float); s.add_argument('--window', type=float, default=0.35)
    s.add_argument('--max-gap', type=int, default=10); s.add_argument('--min-gap', type=int, default=3); s.add_argument('--max-panoramas', type=int); s.add_argument('--select-only', action='store_true'); s.add_argument('--motion-cue', choices=['both', 'imu', 'image'], default='both')
    s.add_argument('--pano-width', type=int, default=4096); s.add_argument('--view-mode', choices=['pinhole-rig', 'fisheye-rig'], default='pinhole-rig')
    s.add_argument('--views', type=int, default=4); s.add_argument('--view-fov', type=float, default=100.0); s.add_argument('--view-size', type=int, default=1024)
    s.add_argument('--fisheye-size', type=int, default=1440); s.add_argument('--gamma', type=float, default=1.8)
    s.add_argument('--nadir-deg', type=float, default=40.0); s.add_argument('--extra-mask-dir')
    s = sub.add_parser('sfm'); w(s)
    s.add_argument('--method', default='colmap-incremental', help='colmap-incremental | colmap-global | opensfm-spherical (planned) | stella-vslam (planned)')
    s.add_argument('--overlap', type=int, default=5); s.add_argument('--loops', type=int, default=3); s.add_argument('--loop-min-separation', type=int, default=15)
    s.add_argument('--max-features', type=int, default=8192); s.add_argument('--peak-threshold', type=float, default=0.0067); s.add_argument('--first-octave', type=int, default=0); s.add_argument('--dsp', action='store_true'); s.add_argument('--relaxed', action='store_true'); s.add_argument('--max-runtime', type=float, default=480); s.add_argument('--threads', type=int, default=8)
    s = sub.add_parser('scale'); w(s); s.add_argument('--method', default='colmap-incremental')
    s.add_argument('--camera-height', type=float, default=1.6); s.add_argument('--height-source', default='default 1.6 m (not measured)')
    s.add_argument('--radius-factor', type=float, default=0.75); s.add_argument('--min-floor-points', type=int, default=8); s.add_argument('--landmarks')
    s = sub.add_parser('export'); w(s); s.add_argument('--method', default='colmap-incremental'); s.add_argument('--out', required=True); s.add_argument('--frame-base', type=int, default=1)
    s = sub.add_parser('privacy', help='blur faces/people in equirect panoramas + write SfM person masks (manual review still required)')
    s.add_argument('--in', dest='input', required=True, help='folder of equirect images (e.g. an export folder or work/.../panos)'); s.add_argument('--out', required=True, help='NEW folder for blurred copies (originals never touched)')
    s.add_argument('--masks-out', help='folder for per-image SfM masks (PNG, white = keep) usable as --extra-mask-dir'); s.add_argument('--max-images', type=int)
    s.add_argument('--face-model', help='YuNet ONNX (opencv_zoo face_detection_yunet)'); s.add_argument('--person-model', help='YOLOX ONNX (opencv_zoo object_detection_yolox)')
    s.add_argument('--face-score', type=float, default=0.85); s.add_argument('--person-score', type=float, default=0.4); s.add_argument('--crop', type=int, default=1024)
    s.add_argument('--nadir-flag-deg', type=float, default=50.0, help='flag images with no detection below this depression angle'); s.add_argument('--always-blur-nadir-deg', type=float, default=35.0, help='also blur the cone around straight down (0 = off)')
    s = sub.add_parser('validate'); w(s); s.add_argument('--method', default='colmap-incremental')
    s.add_argument('--reference', default='scan-assets/captures/2026-09-17/panoramas/manifest.json'); s.add_argument('--frame-base', type=int, default=1)
    s.add_argument('--max-interp-gap', type=int, default=10); s.add_argument('--no-heading', action='store_true'); s.add_argument('--runs-table', default='work/raw360/runs.md')
    a = p.parse_args()
    {'probe': cmd_probe, 'frames': cmd_frames, 'sfm': cmd_sfm, 'scale': cmd_scale, 'export': cmd_export, 'validate': cmd_validate, 'privacy': cmd_privacy}[a.cmd](a)


if __name__ == '__main__':
    main()
