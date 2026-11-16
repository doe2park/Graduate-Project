"""Remove floater Gaussians from an optimized Brush PLY, as a separate derivative.

    python scripts/clean_gaussian.py --run work/gaussian/2026-10-18/l1-a/<stamp> [--preset medium] [--package]
    python scripts/clean_gaussian.py --input export.ply --cameras transforms.json --output out/ [--preset light]
    python scripts/clean_gaussian.py --run <folder> --set isolatedMetres=0.25 --dry-run

The source checkpoint is only read. Whole Gaussians are dropped; every kept Gaussian keeps all of its optimized
parameters (including higher spherical harmonics) byte-for-byte. A clean-report.json records the source/output
hashes, the parameters and how many Gaussians each rule flagged.

Rules are camera-aware because these are indoor walks, where "far from the cloud centre" (the usual percentile
rule) would delete the ends of long corridors. Distances assume the run's metric, Y-up scan frame.

  opacity    activated opacity below minAlpha (near-invisible noise)
  isolated   mean distance to the kNeighbours nearest Gaussians above isolatedMetres (floating specks)
  needle     longest axis > needleRatio x middle axis AND longer than needleMinMetres (the elongated floaters)
  oversized  longest axis above maxScaleMetres
  outside    horizontally further than maxHorizontalMetres from every training/evaluation camera, or more than
             belowMetres under the lowest / aboveMetres over the highest camera
  offsurface (opt-in, --mesh) farther than offSurfaceMetres from the exported scan mesh that seeded training. The
             mesh has holes (glass, unscanned rooms), where real content is removed too: inspect the removed set.

This is a visual clean-up heuristic. It does not correct geometry, does not make the scene surveyed, and can remove
real but poorly observed content (glass, reflections, distant rooms seen through doors). Review the result.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import package_gaussian  # noqa: E402

PRESETS = {
    'light':  {'minAlpha': 0.02, 'isolatedMetres': 0.5, 'kNeighbours': 8, 'needleRatio': 50, 'needleMinMetres': 0.5,
               'maxScaleMetres': 2.0, 'maxHorizontalMetres': 15.0, 'belowMetres': 3.0, 'aboveMetres': 12.0,
               'offSurfaceMetres': 0.5},
    'medium': {'minAlpha': 0.03, 'isolatedMetres': 0.3, 'kNeighbours': 8, 'needleRatio': 20, 'needleMinMetres': 0.3,
               'maxScaleMetres': 1.5, 'maxHorizontalMetres': 12.0, 'belowMetres': 3.0, 'aboveMetres': 10.0,
               'offSurfaceMetres': 0.3},
    'strong': {'minAlpha': 0.05, 'isolatedMetres': 0.2, 'kNeighbours': 8, 'needleRatio': 10, 'needleMinMetres': 0.2,
               'maxScaleMetres': 1.0, 'maxHorizontalMetres': 10.0, 'belowMetres': 2.5, 'aboveMetres': 8.0,
               'offSurfaceMetres': 0.2},
}
RULES = ['opacity', 'isolated', 'needle', 'oversized', 'outside']
MESH_RULE = 'offsurface'  # only with a scan mesh: farther than offSurfaceMetres from the mesh surface
MESH_SPACING = 0.05
MESH_RISK = ('Mesh rule: the exported scan mesh has holes (glass, unscanned rooms, thin objects). Real content '
             'there is also far from the mesh and is removed. Inspect the removed set before publishing.')
SCOPE = ('Visual floater clean-up of trained appearance. Whole Gaussians removed, kept parameters unchanged. '
         'Not a geometry correction, accuracy improvement or surveyed result; may remove real but poorly observed content.')


def resolve_params(preset='medium', overrides=None):
    if preset not in PRESETS:
        raise ValueError(f'Unknown preset {preset!r}; choose {", ".join(PRESETS)}')
    params = dict(PRESETS[preset])
    for key, value in (overrides or {}).items():
        if key not in params:
            raise ValueError(f'Unknown parameter {key!r}; known: {", ".join(params)}')
        params[key] = type(params[key])(value)
    if params['kNeighbours'] < 1:
        raise ValueError('kNeighbours must be at least 1')
    return params


def camera_centres(paths):
    """Unique camera centres (metres) from nerfstudio-style transforms files (camera-to-world matrices)."""
    centres = []
    for path in paths:
        for frame in json.loads(Path(path).read_text())['frames']:
            centres.append(np.asarray(frame['transform_matrix'], dtype=np.float64)[:3, 3])
    if not centres:
        raise ValueError('No camera frames found')
    centres = np.unique(np.round(np.array(centres), 4), axis=0)
    if not np.isfinite(centres).all():
        raise ValueError('Non-finite camera centre')
    return centres


def mesh_surface_samples(glb_paths, spacing=0.05, up_axis_source='z', seed=0):
    """Points on the exported scan mesh, about `spacing` metres apart, in the training frame.

    Uses the same GLB reading and Z-up -> Y-up basis as prepare_gaussian_dataset.mesh_seed (which made the training
    seed), but samples every triangle densely and ignores textures. GLBs are only read.
    """
    import prepare_gaussian_dataset as prep
    from scipy.spatial.transform import Rotation

    basis = prep.W if up_axis_source == 'z' else np.eye(3)
    rng = np.random.default_rng(seed)
    out = []
    for path in glb_paths:
        j, data = prep.read_glb(path)

        def accessor(index):
            a = j['accessors'][index]
            v = j['bufferViews'][a['bufferView']]
            n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]
            dtype = {5126: '<f4', 5125: '<u4', 5123: '<u2'}[a['componentType']]
            item = np.dtype(dtype).itemsize
            return np.ndarray((a['count'], n), dtype=dtype, buffer=data,
                              offset=v.get('byteOffset', 0) + a.get('byteOffset', 0),
                              strides=(v.get('byteStride', item * n), item)).copy()

        def walk(index, parent):
            node = j['nodes'][index]
            if 'matrix' in node:
                m = np.array(node['matrix']).reshape((4, 4), order='F')
            else:
                m = np.eye(4)
                m[:3, :3] = Rotation.from_quat(node.get('rotation', [0, 0, 0, 1])).as_matrix() @ np.diag(node.get('scale', [1, 1, 1]))
                m[:3, 3] = node.get('translation', [0, 0, 0])
            world = parent @ m
            for primitive in (j['meshes'][node['mesh']]['primitives'] if 'mesh' in node else []):
                if primitive.get('mode', 4) != 4:
                    continue
                with np.errstate(all='ignore'):  # NumPy on Apple Accelerate can warn spuriously on matmul
                    verts = (accessor(primitive['attributes']['POSITION']) @ world[:3, :3].T + world[:3, 3]) @ basis.T
                if not np.isfinite(verts).all():
                    raise ValueError(f'Non-finite scan mesh vertex in {path}')
                tri = verts[accessor(primitive['indices']).reshape(-1, 3).astype(int)]
                area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) / 2
                per = np.maximum(1, np.ceil(area / spacing ** 2)).astype(int)  # at least the centroid of each triangle
                idx = np.repeat(np.arange(len(tri)), per)
                a, b = np.sqrt(rng.random(len(idx))), rng.random(len(idx))
                bary = np.stack([1 - a, a * (1 - b), a * b], axis=1)
                out.append((tri[idx] * bary[..., None]).sum(axis=1))
            for child in node.get('children', []):
                walk(child, world)

        for node in j['scenes'][j.get('scene', 0)]['nodes']:
            walk(node, np.eye(4))
    if not out:
        raise ValueError('No triangle geometry in the scan mesh')
    return np.concatenate(out)


def floater_flags(data, cameras, params, up_axis=1, mesh_points=None):
    """One boolean array per rule (True = flagged for removal). Pure: no I/O.
    With mesh_points (scan-mesh surface samples, same frame) the 'offsurface' rule is added."""
    from scipy.spatial import cKDTree

    xyz = np.column_stack([data[k] for k in 'xyz']).astype(np.float64)
    alpha = 1 / (1 + np.exp(-np.clip(data['opacity'].astype(np.float64), -80, 80)))
    scales = np.sort(np.exp(np.column_stack([data[f'scale_{i}'] for i in range(3)]).astype(np.float64)), axis=1)
    longest, middle = scales[:, 2], scales[:, 1]

    k = min(params['kNeighbours'], len(xyz) - 1)
    if k >= 1:
        dist, _ = cKDTree(xyz).query(xyz, k=k + 1, workers=-1)
        isolated = dist[:, 1:].mean(axis=1) > params['isolatedMetres']
    else:
        isolated = np.zeros(len(xyz), dtype=bool)

    ground = [i for i in range(3) if i != up_axis]
    horizontal, _ = cKDTree(cameras[:, ground]).query(xyz[:, ground], workers=-1)
    height = xyz[:, up_axis]
    outside = ((horizontal > params['maxHorizontalMetres'])
               | (height < cameras[:, up_axis].min() - params['belowMetres'])
               | (height > cameras[:, up_axis].max() + params['aboveMetres']))

    flags = {
        'opacity': alpha < params['minAlpha'],
        'isolated': isolated,
        'needle': (longest > params['needleRatio'] * np.maximum(middle, 1e-12)) & (longest > params['needleMinMetres']),
        'oversized': longest > params['maxScaleMetres'],
        'outside': outside,
    }
    if mesh_points is not None:
        surface, _ = cKDTree(mesh_points).query(xyz, workers=-1)
        flags[MESH_RULE] = surface > params['offSurfaceMetres']
    return flags


def write_ply(path, data, comment):
    header = ('ply\nformat binary_little_endian 1.0\ncomment ' + comment + '\nelement vertex ' + str(len(data)) + '\n'
              + ''.join('property float ' + n + '\n' for n in data.dtype.names) + 'end_header\n')
    with Path(path).open('wb') as f:
        f.write(header.encode('ascii'))
        f.write(data.tobytes())


def clean(source, camera_files, output_dir, preset='medium', overrides=None, up_axis=1, dry_run=False,
          mesh_glbs=None, mesh_up_axis='z'):
    """Write output_dir/cleaned.ply and clean-report.json. Refuses to replace an existing output folder.
    mesh_glbs: optional exported scan GLBs (the run's seed meshes) to enable the 'offsurface' rule."""
    source, output_dir = Path(source), Path(output_dir)
    params = resolve_params(preset, overrides)
    if not dry_run and output_dir.exists():
        raise FileExistsError(f'{output_dir} exists; choose a new folder (results are never overwritten)')
    started = time.monotonic()
    data = package_gaussian.read_ply(source)
    cameras = camera_centres(camera_files)
    mesh_points = mesh_surface_samples(mesh_glbs, MESH_SPACING, mesh_up_axis) if mesh_glbs else None
    flags = floater_flags(data, cameras, params, up_axis, mesh_points)
    rules = RULES + ([MESH_RULE] if mesh_points is not None else [])
    removed = np.zeros(len(data), dtype=bool)
    for rule in rules:
        removed |= flags[rule]
    kept = data[~removed]
    if not len(kept):
        raise ValueError('Every Gaussian was flagged; parameters are too strict for this scene')

    report = {
        'status': 'dry-run' if dry_run else 'cleaned',
        'preset': preset,
        'parameters': params,
        'upAxis': 'xyz'[up_axis],
        'frameAssumption': 'metric metres, same frame as the training cameras',
        'source': {'path': str(source), 'sha256': package_gaussian.sha(source), 'bytes': source.stat().st_size,
                   'gaussians': int(len(data))},
        'cameras': {'files': {Path(p).name: package_gaussian.sha(p) for p in camera_files},
                    'uniqueCentres': int(len(cameras))},
        'flaggedByRule': {rule: int(flags[rule].sum()) for rule in rules},
        'removed': int(removed.sum()),
        'removedFraction': round(float(removed.mean()), 6),
        'kept': int(len(kept)),
        'scope': SCOPE,
    }
    if mesh_points is not None:
        report['mesh'] = {'files': {Path(p).name: package_gaussian.sha(p) for p in mesh_glbs},
                          'sourceUpAxis': mesh_up_axis, 'sampleSpacingMetres': MESH_SPACING,
                          'samples': int(len(mesh_points)), 'risk': MESH_RISK}
    else:
        report['parameters'].pop('offSurfaceMetres', None)  # rule not applied: do not imply it was
    if not dry_run:
        output_dir.mkdir(parents=True)
        cleaned = output_dir / 'cleaned.ply'
        write_ply(cleaned, kept, f'Gaussian floater-cleaned derivative; preset {preset}; source sha256 '
                                 f'{report["source"]["sha256"]}')
        report['output'] = {'path': str(cleaned), 'sha256': package_gaussian.sha(cleaned),
                            'bytes': cleaned.stat().st_size}
    report['seconds'] = round(time.monotonic() - started, 1)
    if not dry_run:
        (output_dir / 'clean-report.json').write_text(json.dumps(report, indent=2))
    return report


# ---------------------------------------------------------------- run folders

def run_inputs(run_folder):
    """Checkpoint and camera files of a run_gaussian_pipeline.py run folder."""
    run_folder = Path(run_folder)
    state = json.loads((run_folder / 'run.json').read_text())
    steps = state['settings']['train']['steps']
    ply = run_folder / 'train' / f'export_{steps}.ply'
    cameras = [p for p in (run_folder / 'dataset' / 'transforms.json', run_folder / 'dataset' / 'transforms_val.json')
               if p.is_file()]
    if not ply.is_file():
        raise FileNotFoundError(f'{ply} not found; the run has not finished training')
    if not cameras:
        raise FileNotFoundError(f'No transforms.json in {run_folder / "dataset"}')
    return state, ply, cameras


def run_mesh(state):
    """The exported scan GLBs that seeded this run's training (same frame), with their up axis."""
    import run_gaussian_pipeline as pipe

    preset = pipe.load_presets()['captures'][state['capture']]
    glbs = [ROOT / g for g in preset['seedGlbs']]
    missing = [str(g) for g in glbs if not g.is_file()]
    if not glbs or missing:
        raise FileNotFoundError(f'Scan mesh for {state["capture"]} not available locally: {missing or "none configured"}')
    return glbs, preset['seedUpAxis']


def package_cleaned(run_folder, state, clean_dir, report):
    """Encode and package the cleaned PLY next to it, reusing the run's manifest and viewer metadata."""
    import run_gaussian_pipeline as pipe

    settings = state['settings']
    preset = pipe.load_presets()['captures'][state['capture']]
    cleaned = clean_dir / 'cleaned.ply'
    ksplat = clean_dir / 'encoded' / 'trained.ksplat'
    pipe.encode_ksplat(cleaned, ksplat)
    package_dir = clean_dir / 'package'
    package_gaussian.package(cleaned, package_dir, ROOT / preset['manifest'], settings['prepare']['centerId'],
                             settings['mobileBudget'], settings['train']['steps'], ksplat)
    viewer = json.loads((package_dir / 'viewer.json').read_text())
    original = Path(run_folder) / 'package' / 'viewer.json'
    if original.is_file():  # keep the run's capture/zone/validation context, which the cleaned scene inherits
        before = json.loads(original.read_text())
        for key in ('capture', 'building', 'zone'):
            if key in before:
                viewer[key] = before[key]
        for key in ('validation', 'pipeline'):
            if key in before.get('provenance', {}):
                viewer['provenance'][key] = before['provenance'][key]
    viewer['provenance']['cleaning'] = report
    viewer['provenance']['selectionStatus'] = ('Floater-cleaned derivative of a local run; validation metrics were '
                                               'measured before cleaning. Not yet reviewed or selected.')
    (package_dir / 'viewer.json').write_text(json.dumps(viewer, indent=2))
    return package_dir


def parse_overrides(pairs):
    out = {}
    for pair in pairs or []:
        key, sep, value = pair.partition('=')
        if not sep:
            raise ValueError(f'--set expects key=value, got {pair!r}')
        out[key.strip()] = value.strip()
    return out


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--run', type=Path, help='a run folder from run_gaussian_pipeline.py')
    p.add_argument('--input', type=Path, help='optimized Gaussian PLY (instead of --run)')
    p.add_argument('--cameras', type=Path, nargs='+', help='transforms.json file(s) with the training cameras')
    p.add_argument('--output', type=Path, help='new output folder (default <run>/cleaned-<preset>)')
    p.add_argument('--preset', choices=list(PRESETS), default='medium')
    p.add_argument('--set', action='append', metavar='KEY=VALUE', help='override one preset parameter (repeatable)')
    p.add_argument('--up-axis', choices=['x', 'y', 'z'], default='y', help='vertical axis of the frame (default y)')
    p.add_argument('--mesh', action='store_true',
                   help="also drop Gaussians far from the run's exported scan mesh (needs --run; mesh holes remove real content too)")
    p.add_argument('--mesh-glb', type=Path, nargs='+', help='scan GLB(s) in the training frame, with --input')
    p.add_argument('--mesh-up-axis', choices=['y', 'z'], default='z', help='up axis of --mesh-glb files (default z, as exported)')
    p.add_argument('--package', action='store_true', help='also encode .ksplat and build a viewer package (needs --run)')
    p.add_argument('--dry-run', action='store_true', help='report what would be removed; write nothing')
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        overrides = parse_overrides(args.set)
        mesh, mesh_up = args.mesh_glb, args.mesh_up_axis
        if args.run:
            state, ply, cameras = run_inputs(args.run)
            if args.mesh:
                mesh, mesh_up = run_mesh(state)
            output = args.output or Path(args.run) / f'cleaned-{args.preset}{"-mesh" if mesh else ""}'
        elif args.input and args.cameras and args.output:
            if args.mesh:
                raise ValueError('--mesh needs --run; with --input give --mesh-glb')
            state, ply, cameras, output = None, args.input, args.cameras, args.output
        else:
            raise ValueError('Give --run, or all of --input, --cameras and --output')
        if args.package and state is None:
            raise ValueError('--package needs --run (it reuses the run manifest and settings)')
        report = clean(ply, cameras, output, args.preset, overrides, 'xyz'.index(args.up_axis), args.dry_run,
                       mesh, mesh_up)
        print(json.dumps({k: report[k] for k in ('status', 'preset', 'flaggedByRule', 'removed', 'removedFraction', 'kept')},
                         indent=2))
        if args.package and not args.dry_run:
            print(f'Packaged: {package_cleaned(args.run, state, Path(output), report)}')
    except (ValueError, FileNotFoundError, FileExistsError, KeyError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
