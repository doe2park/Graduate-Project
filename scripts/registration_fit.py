"""Reproduce a Scan->BIM registration from a workbench pairs file (Python mirror of registration-core.js).

Model: rigid yaw about +Y plus XYZ translation, scale fixed at 1 (same model as the accepted May ICP
and scripts/capture_import.py fit).  Both frames are Y-up metres:
    p_bim = R_y(theta) p_scan + t,   R_y = [[c,0,s],[0,1,0],[-s,0,c]]

Subcommands
  fit PAIRS.json --output NEW.json      closed-form landmark fit, optional exhaustive RANSAC, leave-one-out,
                                        independent check points, per-station photo heading offsets
  icp --capture DATE --bim-soup F.f32 --init REG.json --output NEW.json
                                        constrained yaw+XYZ trimmed ICP (archive method) seeded by a landmark fit

Outputs are NEW dated candidate files.  The accepted May registration and every capture's registration.json
are refused as outputs, and existing files are never overwritten.  Residuals are internal consistency,
not surveyed accuracy, unless every check point is marked as surveyed.
"""
import argparse, datetime, hashlib, itertools, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'grimes-registration-candidate/1'
MIN_FIT_PAIRS = 4
MIN_SPREAD_METRES = 0.5
PROTECTED = [ROOT/'alignment-analysis/accepted-registration.json']


# ---------------- core maths (keep identical to registration-core.js) ----------------
def _vec(v, n=3):
    if not isinstance(v, (list, tuple)) or len(v) != n or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in v):
        raise ValueError('Coordinates must be finite %d-vectors' % n)
    return [float(x) for x in v]


def apply(reg, p):
    a = math.radians(reg['rotationYDegrees']); c, s = math.cos(a), math.sin(a); t = reg['translation']
    return [c*p[0]+s*p[2]+t[0], p[1]+t[1], -s*p[0]+c*p[2]+t[2]]


def invert(reg, p):
    a = math.radians(reg['rotationYDegrees']); c, s = math.cos(a), math.sin(a); t = reg['translation']
    x, y, z = p[0]-t[0], p[1]-t[1], p[2]-t[2]
    return [c*x-s*z, y, s*x+c*z]


def fit_yaw_translation(pairs):
    """Closed-form least squares for yaw + XYZ (scale 1).  pairs: [{'scan':[x,y,z],'bim':[x,y,z]}, ...]."""
    if len(pairs) < 2:
        raise ValueError('Need at least 2 pairs for a yaw + XYZ fit')
    n = len(pairs)
    a = [sum(_vec(p['scan'])[k] for p in pairs)/n for k in range(3)]
    b = [sum(_vec(p['bim'])[k] for p in pairs)/n for k in range(3)]
    c = s = spread = 0.0
    for p in pairs:
        x, z = p['scan'][0]-a[0], p['scan'][2]-a[2]
        X, Z = p['bim'][0]-b[0], p['bim'][2]-b[2]
        c += x*X+z*Z; s += z*X-x*Z; spread += x*x+z*z
    if math.sqrt(spread/n) < MIN_SPREAD_METRES or math.hypot(c, s) < 1e-9:
        raise ValueError('Landmarks are too close together horizontally to determine yaw (spread < %.1f m)' % MIN_SPREAD_METRES)
    yaw = math.atan2(s, c)
    reg = {'rotationYDegrees': math.degrees(yaw), 'translation': [0.0, 0.0, 0.0]}
    ra = apply(reg, a)
    reg['translation'] = [b[k]-ra[k] for k in range(3)]
    reg['residualsMetres'] = [math.dist(apply(reg, p['scan']), p['bim']) for p in pairs]
    return reg


def residual_rows(reg, pairs, inliers=None):
    rows = []
    for i, p in enumerate(pairs):
        q = apply(reg, p['scan'])
        d = [q[k]-p['bim'][k] for k in range(3)]
        rows.append({'id': p.get('id', str(i)), 'errorMetres': math.sqrt(sum(v*v for v in d)),
                     'horizontalMetres': math.hypot(d[0], d[2]), 'verticalMetres': d[1],
                     **({'inlier': i in inliers} if inliers is not None else {})})
    return rows


def _stats(errors):
    if not errors:
        return {'rmsMetres': None, 'maxMetres': None, 'medianMetres': None}
    e = sorted(errors); m = len(e)
    median = e[m//2] if m % 2 else .5*(e[m//2-1]+e[m//2])
    return {'rmsMetres': math.sqrt(sum(v*v for v in e)/m), 'maxMetres': e[-1], 'medianMetres': median}


def leave_one_out(pairs):
    """Each pair predicted by a fit that excludes it (independent of that pair)."""
    if len(pairs) < 3:
        raise ValueError('Leave-one-out needs at least 3 fit pairs')
    errors = []
    for i, p in enumerate(pairs):
        reg = fit_yaw_translation(pairs[:i]+pairs[i+1:])
        errors.append({'id': p.get('id', str(i)), 'errorMetres': math.dist(apply(reg, p['scan']), p['bim'])})
    return {'errors': errors, **_stats([e['errorMetres'] for e in errors])}


def ransac(pairs, threshold=0.25):
    """Deterministic exhaustive RANSAC over all 2-pair minimal samples (identical in JS)."""
    best = None
    for i, j in itertools.combinations(range(len(pairs)), 2):
        pi, pj = pairs[i]['scan'], pairs[j]['scan']
        if math.hypot(pi[0]-pj[0], pi[2]-pj[2]) < 2*MIN_SPREAD_METRES:
            continue
        try:
            reg = fit_yaw_translation([pairs[i], pairs[j]])
        except ValueError:
            continue
        errs = [math.dist(apply(reg, p['scan']), p['bim']) for p in pairs]
        inl = [k for k, e in enumerate(errs) if e <= threshold]
        score = (len(inl), -sum(errs[k]**2 for k in inl))
        if best is None or score > best[0]:
            best = (score, inl)
    if best is None or len(best[1]) < 3:
        raise ValueError('RANSAC found no consensus of 3+ pairs within %.2f m' % threshold)
    inliers = best[1]
    for _ in range(3):
        reg = fit_yaw_translation([pairs[k] for k in inliers])
        new = [k for k, p in enumerate(pairs) if math.dist(apply(reg, p['scan']), p['bim']) <= threshold]
        if new == inliers or len(new) < 3:
            break
        inliers = new
    return {'inliers': inliers, 'outliers': [k for k in range(len(pairs)) if k not in inliers], 'thresholdMetres': threshold}


def _azimuth(v):
    return math.atan2(v[2], v[0])


def _wrap(a):
    return (a+math.pi) % (2*math.pi)-math.pi


def solve_heading(obs, reg):
    """Heading offset (deg) about +Y to pre-multiply onto the photo sphere so photo features hit BIM targets.

    obs: {'station', 'stationPosition':[scan frame], 'photoDirections':[[x,y,z] scan-frame directions of the clicked photo
          pixels with NO heading offset applied], 'bimTargets':[[x,y,z] BIM frame]}"""
    dirs, targets = obs.get('photoDirections', []), obs.get('bimTargets', [])
    if len(dirs) != len(targets) or len(dirs) < 2:
        raise ValueError('Heading needs 2+ photo directions with matching BIM targets')
    st = _vec(obs['stationPosition'])
    deltas, elev = [], []
    for d, t in zip(dirs, targets):
        d = _vec(d); ts = invert(reg, _vec(t)); v = [ts[k]-st[k] for k in range(3)]
        if math.hypot(v[0], v[2]) < .3 or math.hypot(d[0], d[2]) < 1e-6:
            raise ValueError('Heading targets must not be straight above/below the station')
        deltas.append(_wrap(_azimuth(d)-_azimuth(v)))
        elev.append(math.degrees(math.atan2(d[1], math.hypot(d[0], d[2]))-math.atan2(v[1], math.hypot(v[0], v[2]))))
    delta = math.atan2(sum(math.sin(x) for x in deltas), sum(math.cos(x) for x in deltas))
    return {'station': obs.get('station'), 'headingOffsetDegrees': math.degrees(delta),
            'residualsDegrees': [abs(math.degrees(_wrap(x-delta))) for x in deltas],
            'elevationResidualsDegrees': elev, 'observations': len(deltas)}


def split_pairs(data):
    pairs = data.get('pairs', [])
    ids = set()
    for p in pairs:
        _vec(p.get('scan')); _vec(p.get('bim'))
        if p.get('role') not in ('fit', 'check'):
            raise ValueError('Each pair needs role "fit" or "check"')
        pid = str(p.get('id', ''))
        if not pid or pid in ids:
            raise ValueError('Pair ids must be unique and non-empty')
        ids.add(pid)
    fit = [p for p in pairs if p['role'] == 'fit']; checks = [p for p in pairs if p['role'] == 'check']
    if len(fit) < MIN_FIT_PAIRS:
        raise ValueError('Need %d+ fit pairs (got %d)' % (MIN_FIT_PAIRS, len(fit)))
    if not checks:
        raise ValueError('Need 1+ independent check pair, never used in the fit')
    for c in checks:
        for p in fit:
            if math.dist(c['scan'], p['scan']) < 1e-6 or math.dist(c['bim'], p['bim']) < 1e-6:
                raise ValueError('Check %s reuses a fit landmark; checks must be independent' % c['id'])
    return fit, checks


def solve(data):
    fit_pairs, checks = split_pairs(data)
    rs = data.get('ransac') or {}
    if rs.get('enabled'):
        r = ransac(fit_pairs, float(rs.get('thresholdMetres', .25)))
        inliers = r['inliers']
        ransac_out = {'enabled': True, 'thresholdMetres': r['thresholdMetres'], 'outlierIds': [fit_pairs[k]['id'] for k in r['outliers']]}
    else:
        inliers = list(range(len(fit_pairs))); ransac_out = {'enabled': False, 'outlierIds': []}
    used = [fit_pairs[k] for k in inliers]
    if len(used) < 3:
        raise ValueError('Fewer than 3 inlier fit pairs remain')
    reg = fit_yaw_translation(used)
    reg = {'rotationYDegrees': reg['rotationYDegrees'], 'translation': reg['translation']}
    fit_rows = residual_rows(reg, fit_pairs, set(inliers))
    check_rows = residual_rows(reg, checks)
    headings = [solve_heading(o, reg) for o in data.get('headingObservations', [])]
    return {**reg, 'scale': 1,
            'fit': {'pairs': len(used), 'residuals': fit_rows, **_stats([r['errorMetres'] for r in fit_rows if r['inlier']])},
            'leaveOneOut': leave_one_out(used),
            'checks': {'pairs': len(checks), 'surveyed': all(bool(c.get('surveyed')) for c in checks), 'residuals': check_rows,
                       **_stats([r['errorMetres'] for r in check_rows])},
            'ransac': ransac_out, 'headings': headings}


def canonical_pairs_text(data):
    f = lambda v: ','.join(format(x, '.6f') for x in v)
    lines = ['%s|%s|%s|%s|%s' % (p['role'], p['id'], f(p['scan']), f(p['bim']), 'surveyed' if p.get('surveyed') else 'unsurveyed') for p in data['pairs']]
    for o in data.get('headingObservations', []):
        lines.append('heading|%s|%s|%s|%s' % (o.get('station'), f(o['stationPosition']), ';'.join(f(d) for d in o['photoDirections']), ';'.join(f(t) for t in o['bimTargets'])))
    return '\n'.join(lines)+'\n'


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _manual_offsets(data):
    """Slider-only heading offsets (visual alignment, no picks). Recorded separately; pick-based solves win."""
    out = {}
    for k, v in (data.get('manualHeadingOffsetsDegrees') or {}).items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or abs(v) > 180:
            raise ValueError('Manual heading offsets must be finite degrees within +/-180')
        out[str(k)] = float(v)
    return out


def status_for(result):
    return 'landmark-fit-surveyed-checks' if result['checks']['surveyed'] else 'landmark-fit-unsurveyed'


def build_export(data, result, created=None, extra_inputs=None):
    created = created or datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    status = status_for(result)
    return {
        'schema': SCHEMA, 'capture': data.get('capture'), 'createdAt': created,
        'rotationYDegrees': result['rotationYDegrees'], 'translation': result['translation'], 'scale': 1, 'status': status,
        'method': {'model': 'rigid yaw about +Y + XYZ translation, scale fixed at 1',
                   'solver': 'closed-form centroid / atan2 (same as scripts/capture_import.py fit and the accepted ICP update step)',
                   'ransac': result['ransac'], 'icp': None},
        'frames': {'source': 'scan viewer frame, Y-up metres (photo stations and scan mesh)', 'target': 'BIM viewer world, Y-up metres'},
        'inputs': {'pairsSha256': sha256_text(canonical_pairs_text(data)), 'baseline': data.get('baseline'), **(extra_inputs or {})},
        'fit': result['fit'], 'leaveOneOut': result['leaveOneOut'], 'checks': result['checks'],
        'stationHeadingOffsetsDegrees': {**_manual_offsets(data), **{h['station']: h['headingOffsetDegrees'] for h in result['headings'] if h.get('station')}},
        'manualHeadingOffsetsDegrees': _manual_offsets(data),
        'headingSolves': result['headings'],
        'pairs': data['pairs'], 'headingObservations': data.get('headingObservations', []),
        'scope': ('Visualization candidate from clicked landmarks. Fit and leave-one-out residuals are internal consistency; '
                  + ('check points are marked surveyed by the author.' if status.endswith('surveyed-checks') else 'check points are not surveyed, so this is not surveyed accuracy.')
                  + ' Review in scan-compare.html?registration=<this file> before publishing.'),
    }


def check_output_path(path):
    path = Path(path).resolve()
    captures = (ROOT/'scan-assets/captures').resolve()
    if path in [p.resolve() for p in PROTECTED] or (path.name == 'registration.json' and captures in path.parents):
        raise ValueError('Refusing to overwrite an accepted/provisional registration: write a new dated candidate file')
    if path.exists():
        raise FileExistsError('%s exists; candidates are never overwritten' % path)
    return path


# ---------------- ICP refinement (archive method, constrained yaw + XYZ) ----------------
def _sample_surface(tris, density, seed_offset=0):
    import numpy as np
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    area = .5*np.linalg.norm(np.cross(b-a, c-a), axis=1)
    counts = np.minimum(3000, np.ceil(area*density)).astype(np.int64)
    idx = np.repeat(np.arange(len(tris)), counts)
    k = np.concatenate([np.arange(1, n+1) for n in counts]) if len(counts) else np.zeros(0)
    u = (k*.61803398875) % 1; w = (k*.41421356237) % 1
    flip = u+w > 1; u[flip], w[flip] = 1-u[flip], 1-w[flip]
    return a[idx]*(1-u-w)[:, None]+b[idx]*u[:, None]+c[idx]*w[:, None]


def _voxel(points, size):
    import numpy as np
    keys = np.floor(points/size).astype(np.int64)
    _, first = np.unique(keys, axis=0, return_index=True)
    return points[np.sort(first)]


def _fit_arrays(src, dst):
    import numpy as np
    a = src.mean(0); b = dst.mean(0); x = src-a; y = dst-b
    c = float((x[:, 0]*y[:, 0]+x[:, 2]*y[:, 2]).sum()); s = float((x[:, 2]*y[:, 0]-x[:, 0]*y[:, 2]).sum())
    reg = {'rotationYDegrees': math.degrees(math.atan2(s, c)), 'translation': [0.0, 0.0, 0.0]}
    ra = apply(reg, a.tolist()); reg['translation'] = [float(b[k]-ra[k]) for k in range(3)]
    return reg


def _apply_array(reg, pts):
    import numpy as np
    a = math.radians(reg['rotationYDegrees']); c, s = math.cos(a), math.sin(a); t = np.array(reg['translation'])
    return np.stack([c*pts[:, 0]+s*pts[:, 2], pts[:, 1], -s*pts[:, 0]+c*pts[:, 2]], 1)+t


def icp(scan_pts, bim_pts, init, iterations=40, keep_percentile=65, max_distance=2.0):
    import numpy as np
    from scipy.spatial import cKDTree
    tree = cKDTree(bim_pts); reg = {'rotationYDegrees': init['rotationYDegrees'], 'translation': list(init['translation'])}
    for it in range(iterations):
        moved = _apply_array(reg, scan_pts); d, j = tree.query(moved)
        keep = d < min(max_distance, np.percentile(d, keep_percentile))
        new = _fit_arrays(scan_pts[keep], bim_pts[j[keep]])
        change = math.dist(new['translation'], reg['translation'])+abs(math.radians(new['rotationYDegrees']-reg['rotationYDegrees']))
        reg = new
        if change < 1e-5:
            break
    reg['iterations'] = it+1
    return reg


def nn_stats(reg, scan_pts, bim_pts):
    import numpy as np
    from scipy.spatial import cKDTree
    d, _ = cKDTree(bim_pts).query(_apply_array(reg, scan_pts))
    return {'medianMetres': float(np.median(d)), 'p80Metres': float(np.percentile(d, 80)),
            'within025': float((d <= .25).mean()), 'within05': float((d <= .5).mean()), 'points': int(len(d))}


def run_icp(args):
    import numpy as np
    import registration_diagnostics as rd
    cfg = rd.CAPTURES[args.capture]
    init = json.loads(Path(args.init).read_text())
    tris = rd.load_scan_geometry(cfg['mesh'])
    scan = _voxel(_sample_surface(tris, 15), .14)
    bim = np.concatenate([rd.load_soup(p) for p in args.bim_soup])
    bim_pts = _voxel(_sample_surface(bim, 15), .12)
    lo, hi = args.bim_height
    bim_pts = bim_pts[(bim_pts[:, 1] >= lo) & (bim_pts[:, 1] <= hi)]
    sb = _apply_array(init, scan)
    scan = scan[(sb[:, 1] >= lo-.3) & (sb[:, 1] <= hi+.3)]
    train, evaluate = scan[0::3], scan[1::3]
    before = nn_stats(init, evaluate, bim_pts)
    reg = icp(train, bim_pts, init)
    after = nn_stats(reg, evaluate, bim_pts)
    out = {'schema': SCHEMA, 'capture': args.capture,
           'createdAt': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
           'rotationYDegrees': reg['rotationYDegrees'], 'translation': reg['translation'], 'scale': 1, 'status': 'icp-refined-unsurveyed',
           'method': {'model': 'rigid yaw about +Y + XYZ translation, scale fixed at 1',
                      'solver': 'trimmed point-to-point ICP (alignment-analysis/method-archive): cKDTree nearest BIM point, keep d < min(2 m, p65), closed-form yaw+XYZ update, <=40 iterations, stop at 1e-5',
                      'icp': {'iterations': reg['iterations'], 'scanVoxelMetres': .14, 'bimVoxelMetres': .12, 'bimHeightBandMetres': [lo, hi],
                              'trainPoints': int(len(train)), 'evaluationPoints': int(len(evaluate)), 'evaluation': 'every third scan sample trains, the next is held out'},
                      'ransac': None},
           'frames': {'source': 'scan viewer frame, Y-up metres', 'target': 'BIM viewer world, Y-up metres'},
           'inputs': {'init': str(Path(args.init).resolve().relative_to(ROOT)) if ROOT in Path(args.init).resolve().parents else Path(args.init).name, 'initSha256': hashlib.sha256(Path(args.init).read_bytes()).hexdigest(),
                      'scanMeshes': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in cfg['mesh']},
                      'bimSoups': {Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in args.bim_soup},
                      'bimSources': {str(p): hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (args.bim_source or [])},
                      'bimSoupNote': 'float32 triangles decoded by scripts/decode_bim_soup.mjs from buildings/grimes/*.glb (read-only)'},
           'nearestPointBefore': before, 'nearestPointAfter': after,
           'stationHeadingOffsetsDegrees': {},
           'scope': 'ICP candidate seeded by %s. Nearest-point distances are internal consistency against sampled BIM geometry, not surveyed accuracy. Review with independent check points and in scan-compare.html?registration=<this file>.' % Path(args.init).name}
    if args.pairs:
        data = json.loads(Path(args.pairs).read_text())
        _, checks = split_pairs(data)
        out['checks'] = {'pairs': len(checks), 'surveyed': all(bool(c.get('surveyed')) for c in checks), 'residuals': residual_rows(reg, checks),
                         **_stats([r['errorMetres'] for r in residual_rows(reg, checks)])}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    f = sub.add_parser('fit'); f.add_argument('pairs', type=Path); f.add_argument('--output', type=Path, required=True)
    f.add_argument('--no-ransac', action='store_true', help='ignore the pairs file RANSAC setting')
    i = sub.add_parser('icp'); i.add_argument('--capture', required=True); i.add_argument('--init', type=Path, required=True)
    i.add_argument('--bim-soup', type=Path, nargs='+', required=True); i.add_argument('--output', type=Path, required=True)
    i.add_argument('--bim-height', type=float, nargs=2, default=[4.7, 10.0]); i.add_argument('--pairs', type=Path)
    i.add_argument('--bim-source', nargs='+', help='repository GLB paths the soup was decoded from (hashes recorded)')
    args = p.parse_args()
    try:
        out_path = check_output_path(args.output)
        if args.command == 'fit':
            data = json.loads(args.pairs.read_text())
            if args.no_ransac:
                data['ransac'] = {'enabled': False}
            result = build_export(data, solve(data), extra_inputs={'pairsFile': args.pairs.name})
        else:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            result = run_icp(args)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open('x') as fh:
            fh.write(json.dumps(result, indent=2)+'\n')
        print(json.dumps({k: result[k] for k in ['status', 'rotationYDegrees', 'translation']}, indent=2))
    except (ValueError, KeyError, OSError) as e:
        p.exit(2, 'error: %s\n' % e)


if __name__ == '__main__':
    main()
