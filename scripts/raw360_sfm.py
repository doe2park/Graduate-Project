"""Pluggable SfM backends for raw360_pipeline.py.

All backends read the same frames.json (keyframes + rig of derived views/lenses), share ONE feature/match
database (same pairs, same SIFT settings) so methods are benchmarked on identical input, and write the same
sfm/<method>/sfm-result.json + points.npy shape consumed by scale/export/validate.

Implemented: colmap-incremental (pycolmap incremental mapper, rig-constrained),
             colmap-global (pycolmap global_mapping = GLOMAP integrated in COLMAP 4, rig-constrained).
Planned (hooks raise with guidance): opensfm-spherical (OpenSfM native equirect camera),
             stella-vslam (equirect visual SLAM front-end for tracking/keyframes, then COLMAP BA).
"""
import hashlib, json, shutil, time
from pathlib import Path
import numpy as np
import raw360_core as core

PLANNED = {
    'opensfm-spherical': 'Planned: export panos/ + exif to an OpenSfM dataset with projection_type "spherical" and run '
                         'detect_features/match_features/create_tracks/reconstruct; convert reconstruction.json shots '
                         '(rotation = world->camera axis-angle, OpenSfM camera axes) to worldFromPano/centre.',
    'stella-vslam': 'Planned: run stella_vslam with an Equirectangular camera on a low-res stitched video for tracking and '
                    'keyframe selection, export keyframe poses + map, then refine with COLMAP bundle adjustment using these '
                    'images. Not installed or built in this repository.',
}


def _hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]


def _descriptors(work, keyframes):
    from PIL import Image
    out = []
    for k in keyframes:
        with Image.open(work / 'panos' / k['pano']) as im:
            g = np.asarray(im.convert('L').resize((256, 128), Image.Resampling.BOX))
        out.append(core.yaw_invariant_descriptor(g[16:112]))  # +-67.5 deg elevation band
    return np.array(out)


def build_database(work, meta, a):
    """Feature extraction + rig config + matching on sequential and appearance-loop pairs. Cached by settings."""
    import pycolmap
    rig, kfs = meta['rig'], meta['keyframes']
    settings = {'rig': [(v['name'], v['model'], v['params']) for v in rig], 'frames': [k['frame'] for k in kfs],
                'maxFeatures': a.max_features, 'overlap': a.overlap, 'loops': a.loops, 'loopMinSep': a.loop_min_separation,
                'gamma': meta.get('gamma'), 'nadir': meta.get('nadirMaskDeg'), 'peak': a.peak_threshold, 'firstOctave': a.first_octave,
                'dsp': a.dsp, 'workFrames': meta.get('range')}
    common = work / 'sfm' / f'common-{_hash(settings)}'; db_path = common / 'database.db'; info_path = common / 'database.json'
    if info_path.exists():
        return db_path, json.loads(info_path.read_text())
    shutil.rmtree(common, ignore_errors=True); common.mkdir(parents=True)
    t0 = time.time()
    names = [f"{v['name']}/{k['pano']}" for v in rig for k in kfs]
    reader = pycolmap.ImageReaderOptions(); reader.camera_model = rig[0]['model']
    reader.camera_params = ','.join(f'{p:.6f}' for p in rig[0]['params']); reader.mask_path = str(work / 'masks')
    ext = pycolmap.FeatureExtractionOptions(); ext.num_threads = a.threads; ext.use_gpu = False
    ext.sift.max_num_features = a.max_features; ext.sift.peak_threshold = a.peak_threshold
    ext.sift.first_octave = a.first_octave; ext.sift.domain_size_pooling = a.dsp
    pycolmap.extract_features(db_path, work / 'views', image_names=names, camera_mode=pycolmap.CameraMode.PER_FOLDER,
                              reader_options=reader, extraction_options=ext, device=pycolmap.Device.cpu)
    t1 = time.time()
    ref = np.array(rig[0]['camFromPano']); cams = []
    for i, v in enumerate(rig):
        c = pycolmap.RigConfigCamera(); c.image_prefix = v['name'] + '/'; c.ref_sensor = i == 0
        if i:
            R = np.array(v['camFromPano']) @ ref.T  # cam_i <- cam_0 (= rig)
            c.cam_from_rig = pycolmap.Rigid3d(rotation=pycolmap.Rotation3d(R), translation=np.zeros(3))
        cams.append(c)
    cfg = pycolmap.RigConfig(); cfg.cameras = cams
    db = pycolmap.Database.open(db_path)
    try:
        pycolmap.apply_rig_config([cfg], db)
    finally:
        db.close()
    desc = _descriptors(work, kfs)
    pano_pairs = core.panorama_pairs(len(kfs), a.overlap, desc, a.loops, a.loop_min_separation)
    loops = [(i, j) for i, j in pano_pairs if j - i > a.overlap]
    with open(common / 'pairs.txt', 'w') as f:
        for i, j in pano_pairs:
            for v in rig:
                for w in rig:
                    f.write(f"{v['name']}/{kfs[i]['pano']} {w['name']}/{kfs[j]['pano']}\n")
    mo = pycolmap.FeatureMatchingOptions(); mo.num_threads = a.threads; mo.use_gpu = False
    mo.rig_verification = True; mo.skip_image_pairs_in_same_frame = True
    po = pycolmap.ImportedPairingOptions(); po.match_list_path = common / 'pairs.txt'
    pycolmap.match_image_pairs(db_path, matching_options=mo, pairing_options=po, device=pycolmap.Device.cpu)
    t2 = time.time()
    db = pycolmap.Database.open(db_path)
    try:
        verified = db.num_verified_image_pairs()
        _, tvgs = db.read_two_view_geometries()
        inliers = np.array([g.inlier_matches.shape[0] for g in tvgs]) if len(tvgs) else np.zeros(0)
    finally:
        db.close()
    info = {'settings': settings, 'images': len(names), 'panoramaPairs': len(pano_pairs), 'loopCandidatePairs': len(loops),
            'imagePairs': len(pano_pairs) * len(rig) ** 2, 'verifiedImagePairsReported': int(verified),
            'pairsWithAtLeast15Inliers': int((inliers >= 15).sum()), 'pairsWithAtLeast50Inliers': int((inliers >= 50).sum()),
            'pairing': 'sequential overlap + yaw-invariant appearance loop candidates (no vocabulary tree download)',
            'seconds': {'extract': round(t1 - t0, 1), 'match': round(t2 - t1, 1)}}
    info_path.write_text(core.dumps(info))
    return db_path, info


def _map_incremental(db, image_path, out, meta, a):
    import pycolmap
    o = pycolmap.IncrementalPipelineOptions(); o.num_threads = a.threads; o.max_runtime_seconds = int(a.max_runtime)
    fisheye = meta['viewMode'] == 'fisheye-rig'
    o.ba_refine_focal_length = fisheye; o.ba_refine_principal_point = False; o.ba_refine_extra_params = fisheye
    o.ba_refine_sensor_from_rig = fisheye
    if a.relaxed:  # weak, dark indoor imagery: accept smaller inlier sets (more registrations, more risk of wrong poses)
        o.mapper.abs_pose_min_num_inliers = 15; o.mapper.abs_pose_min_inlier_ratio = 0.15; o.mapper.init_min_num_inliers = 50
    return pycolmap.incremental_mapping(db, image_path, out, o), o.todict()


def _map_global(db, image_path, out, meta, a):
    import pycolmap
    o = pycolmap.GlobalPipelineOptions(); o.num_threads = a.threads
    fisheye = meta['viewMode'] == 'fisheye-rig'
    m = o.mapper; m.num_threads = a.threads
    m.bundle_adjustment.refine_focal_length = fisheye; m.bundle_adjustment.refine_extra_params = fisheye
    m.bundle_adjustment.refine_principal_point = False
    for part in (m, m.rotation_averaging, m.global_positioning, m.bundle_adjustment):
        if hasattr(part, 'refine_sensor_from_rig'):
            part.refine_sensor_from_rig = fisheye
    m.global_positioning.use_gpu = False; m.bundle_adjustment.ceres.use_gpu = False
    return pycolmap.global_mapping(db, image_path, out, o), {'mapper': 'GLOMAP via pycolmap.global_mapping', 'refineIntrinsics': fisheye}


BACKENDS = {'colmap-incremental': _map_incremental, 'colmap-global': _map_global}


def _frame_poses(rec, meta):
    """worldFromPano + centre per keyframe from a reconstruction (reference sensor = rig[0])."""
    rig, kfs = meta['rig'], meta['keyframes']; ref = np.array(rig[0]['camFromPano'])
    by_pano = {}
    for fid, fr in rec.frames.items():
        if not fr.has_pose:
            continue
        names = [rec.images[d.id].name for d in fr.image_ids] if hasattr(fr, 'image_ids') else []
        pano = names[0].split('/', 1)[1] if names else None
        T = fr.rig_from_world; R = np.array(T.rotation.matrix()); t = np.array(T.translation)
        by_pano[pano] = {'worldFromPano': (R.T @ ref).tolist(), 'centre': (-R.T @ t).tolist(),
                         'registeredViews': sum(1 for d in fr.image_ids if rec.images[d.id].has_pose)}
    out = []
    for k in kfs:
        p = by_pano.get(k['pano'])
        out.append({'frame': k['frame'], 'pano': k['pano'], 'registered': p is not None, **(p or {})})
    return out


def run(work, a):
    import pycolmap
    if a.method in PLANNED:
        raise SystemExit(f'{a.method}: {PLANNED[a.method]}')
    if a.method not in BACKENDS:
        raise SystemExit(f'Unknown method {a.method}; implemented: {sorted(BACKENDS)}; planned: {sorted(PLANNED)}')
    meta = json.loads((work / 'frames.json').read_text()); t0 = time.time()
    db_common, dbinfo = build_database(work, meta, a)
    mdir = work / 'sfm' / a.method; shutil.rmtree(mdir, ignore_errors=True); mdir.mkdir(parents=True)
    db = mdir / 'database.db'; shutil.copyfile(db_common, db)
    t1 = time.time()
    recs, opts = BACKENDS[a.method](db, work / 'views', mdir / 'models', meta, a)
    t2 = time.time()
    total_images = len(meta['rig']) * len(meta['keyframes'])
    models = [{'id': int(i), 'frames': r.num_reg_frames(), 'images': r.num_reg_images(), 'points': r.num_points3D()} for i, r in recs.items()]
    result = {'schema': 'raw360-sfm/1', 'method': a.method, 'pycolmap': pycolmap.__version__, 'viewMode': meta['viewMode'],
              'database': dbinfo, 'options': {'overlap': a.overlap, 'loops': a.loops, 'loopMinSeparation': a.loop_min_separation,
                                              'maxFeatures': a.max_features, 'maxRuntime': a.max_runtime, 'threads': a.threads,
                                              'relaxed': a.relaxed, 'dsp': a.dsp, 'firstOctave': a.first_octave, 'peakThreshold': a.peak_threshold},
              'mapperOptionsSummary': {k: v for k, v in opts.items() if isinstance(v, (int, float, str, bool))} if isinstance(opts, dict) else str(opts),
              'models': models, 'totalPanoramas': len(meta['keyframes']), 'totalImages': total_images}
    if not recs:
        result.update(registeredPanoramas=0, registeredImages=0, frames=[{'frame': k['frame'], 'pano': k['pano'], 'registered': False} for k in meta['keyframes']])
        np.save(mdir / 'points.npy', np.zeros((0, 5)))
    else:
        best_id = max(recs, key=lambda i: recs[i].num_reg_frames()); rec = recs[best_id]
        (mdir / 'model').mkdir(); rec.write(mdir / 'model')
        pts = np.array([[*p.xyz, p.error, p.track.length()] for p in rec.points3D.values()]) if rec.num_points3D() else np.zeros((0, 5))
        np.save(mdir / 'points.npy', pts)
        frames = _frame_poses(rec, meta)
        result.update(selectedModel=int(best_id), registeredPanoramas=sum(f['registered'] for f in frames), registeredImages=rec.num_reg_images(),
                      points3D=rec.num_points3D(), meanReprojectionErrorPx=float(rec.compute_mean_reprojection_error()),
                      meanTrackLength=float(rec.compute_mean_track_length()), frames=frames,
                      cameras={int(i): {'model': str(c.model), 'params': [float(x) for x in c.params]} for i, c in rec.cameras.items()},
                      rigs=[str(r) for r in rec.rigs.values()])
    result['seconds'] = {'database': dbinfo['seconds'], 'databaseThisRun': round(t1 - t0, 1), 'mapping': round(t2 - t1, 1), 'total': round(time.time() - t0, 1)}
    (mdir / 'sfm-result.json').write_text(core.dumps(result))
    print(json.dumps({k: result.get(k) for k in ['method', 'registeredPanoramas', 'totalPanoramas', 'registeredImages', 'totalImages',
                                                 'points3D', 'meanReprojectionErrorPx', 'models', 'seconds']}, indent=2))
