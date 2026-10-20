"""Independent checks and review figures for a yaw+XYZ scan->BIM registration candidate (CPU only).

Checks, all against read-only inputs:
  * held-out nearest-point distances (every third scan sample, offset 1), split by whether the transformed point
    lies inside the BIM's modelled footprint (all levels, filled) -- scan geometry outside the model is reported
    separately instead of being counted as misfit;
  * per-station: inside/outside the footprint, BIM floor height below the transformed camera (sampled horizontal
    BIM triangles within 0.5 m), camera height above that floor vs the camera height above the scan's own floor;
  * dominant floor heights of scan vs BIM inside the footprint;
  * convergence re-run of the ICP from the candidate (more iterations);
  * plan overlays at the requested section heights, and BIM renders over captured panoramas
    (registration_diagnostics.render / sphere_rotation, the scan-photo.html orientation).

Distances are internal consistency against sampled BIM geometry, not surveyed accuracy.
"""
import argparse, json, math, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import registration_fit as rf
import registration_diagnostics as rd
import global_registration_search as gs


def section(tris, cut):
    y = tris[:, :, 1]; sel = tris[(y.min(1) < cut) & (y.max(1) > cut)]
    idxs, pts = [], []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        A = sel[:, i]; B = sel[:, j]; da = A[:, 1]-cut; db = B[:, 1]-cut; m = da*db < 0
        f = da[m]/(da[m]-db[m]); idxs.append(np.nonzero(m)[0]); pts.append((A[m]+(B[m]-A[m])*f[:, None])[:, [0, 2]])
    idx = np.concatenate(idxs); P = np.concatenate(pts); o = np.argsort(idx, kind='stable'); idx = idx[o]; P = P[o]
    _, s, cn = np.unique(idx, return_index=True, return_counts=True); k = s[cn >= 2]
    return np.stack([P[k], P[k+1]], 1)


def footprint(tris, cell=0.5):
    from scipy.ndimage import binary_closing, binary_fill_holes
    xz = tris.reshape(-1, 3)[:, [0, 2]]
    lo = xz.min(0)-2; shape = tuple(np.ceil((xz.max(0)+2-lo)/cell).astype(int))
    c = tris.mean(1)[:, [0, 2]]
    img = gs.raster(c, lo, shape, cell) > 0
    img = binary_fill_holes(binary_closing(img, iterations=3))
    def inside(p):
        ij = np.floor((np.asarray(p)-lo)/cell).astype(int)
        ok = (ij[:, 0] >= 0) & (ij[:, 0] < shape[0]) & (ij[:, 1] >= 0) & (ij[:, 1] < shape[1])
        out = np.zeros(len(ij), bool); out[ok] = img[ij[ok, 0], ij[ok, 1]]
        return out
    return inside


def horizontal_points(tris, density=8):
    n = np.cross(tris[:, 1]-tris[:, 0], tris[:, 2]-tris[:, 0]); a = np.linalg.norm(n, axis=1)
    hor = np.abs(n[:, 1]) > .95*np.maximum(a, 1e-12)
    return rf._voxel(rf._sample_surface(tris[hor], density), .1)


def floor_below(points_tree, pts_h, p, radius=0.5, min_drop=0.5):
    idx = points_tree.query_ball_point([p[0], p[2]], radius)
    y = pts_h[idx, 1]; y = y[y < p[1]-min_drop]
    return float(y.max()) if len(y) else None


def scan_floor_below(tree, pts, p, radius=0.6):
    idx = tree.query_ball_point([p[0], p[2]], radius)
    y = pts[idx, 1]; y = y[y < p[1]-0.5]
    if len(y) < 20:
        return None
    h, e = np.histogram(y, bins=np.arange(p[1]-4, p[1]-0.5, 0.05))
    return float(e[np.argmax(h)]+0.025)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--e57', nargs='+', required=True); ap.add_argument('--bim-soup', required=True)
    ap.add_argument('--reg', nargs=4, type=float, required=True, metavar=('YAW', 'TX', 'TY', 'TZ'))
    ap.add_argument('--alt', action='append', default=[], help='name:yaw:tx:ty:tz alternative shown in figures/stats')
    ap.add_argument('--manifest', action='append', required=True, help='label=path/to/manifest.json')
    ap.add_argument('--bim-height', type=float, nargs=2, required=True)
    ap.add_argument('--cuts', type=float, nargs='+', required=True, help='BIM section heights for plan figures')
    ap.add_argument('--scan-bands', type=float, nargs='+', required=True, help='scan-frame band pairs matching --cuts')
    ap.add_argument('--photo-stations', nargs='*', default=[], help='label:station_id for BIM-over-photo renders')
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    reg = {'rotationYDegrees': a.reg[0], 'translation': a.reg[1:]}
    alts = []
    for h in a.alt:
        n, *v = h.split(':'); v = [float(x) for x in v]; alts.append((n, {'rotationYDegrees': v[0], 'translation': v[1:]}))
    from scipy.spatial import cKDTree
    scan = gs.load_scan(a.e57, [])
    tris = rd.load_soup(a.bim_soup)
    inside = footprint(tris)
    lo, hi = a.bim_height
    y = tris[:, :, 1]; band = tris[(y.max(1) >= lo) & (y.min(1) <= hi)]
    bim = rf._voxel(rf._sample_surface(band, 15), .12); bim = bim[(bim[:, 1] >= lo) & (bim[:, 1] <= hi)]
    tree = cKDTree(bim)
    s14 = rf._voxel(scan, .14)
    report = {'registration': reg, 'bimHeightBand': [lo, hi]}

    # 1. held-out distances split by footprint
    def split_stats(r):
        sb = rf._apply_array(r, s14); keep = (sb[:, 1] >= lo-.3) & (sb[:, 1] <= hi+.3)
        ev = s14[keep][1::3]; evb = rf._apply_array(r, ev); ins = inside(evb[:, [0, 2]])
        return {'all': gs.nn_bounded(r, ev, bim, tree=tree), 'insideFootprint': gs.nn_bounded(r, ev[ins], bim, tree=tree),
                'outsideFootprint': gs.nn_bounded(r, ev[~ins], bim, tree=tree), 'fractionInsideFootprint': float(ins.mean())}
    report['heldOut'] = split_stats(reg)
    report['alternatives'] = {n: {'registration': r, 'heldOut': split_stats(r)} for n, r in alts}
    print('heldOut', json.dumps({k: (v if not isinstance(v, dict) else {kk: round(vv, 3) if isinstance(vv, float) else vv for kk, vv in v.items()}) for k, v in report['heldOut'].items()}))
    for n, v in report['alternatives'].items():
        print('alt', n, 'inside med %.3f w25 %.3f frac-inside %.2f' % (v['heldOut']['insideFootprint']['medianMetres'], v['heldOut']['insideFootprint']['within025'], v['heldOut']['fractionInsideFootprint']))

    # 2. convergence re-run
    sb = rf._apply_array(reg, s14); s = s14[(sb[:, 1] >= lo-.3) & (sb[:, 1] <= hi+.3)]
    rerun = gs.bounded_icp(s[0::3], bim, reg, iterations=150)
    report['convergenceRerun'] = {'rotationYDegrees': rerun['rotationYDegrees'], 'translation': rerun['translation'], 'iterations': rerun['iterations'],
                                  'yawChangeDegrees': rerun['rotationYDegrees']-reg['rotationYDegrees'],
                                  'translationChangeMetres': math.dist(rerun['translation'], reg['translation'])}
    print('rerun', report['convergenceRerun'])

    # 3. stations
    hpts = horizontal_points(tris); htree = cKDTree(hpts[:, [0, 2]])
    stree = cKDTree(scan[:, [0, 2]])
    stations = []
    for spec in a.manifest:
        label, path = spec.split('=', 1)
        for st in json.loads(Path(path).read_text())['stations']:
            p = np.array(st['position'], float); q = rf._apply_array(reg, p[None])[0]
            sf = scan_floor_below(stree, scan, p); bf = floor_below(htree, hpts, q)
            stations.append({'label': label, 'id': st['id'], 'scan': p.tolist(), 'bim': q.tolist(), 'insideFootprint': bool(inside(q[None, [0, 2]])[0]),
                             'scanFloorY': sf, 'cameraAboveScanFloor': None if sf is None else float(p[1]-sf),
                             'bimFloorY': bf, 'cameraAboveBimFloor': None if bf is None else float(q[1]-bf),
                             'floorMismatchMetres': None if (sf is None or bf is None) else float((sf+reg['translation'][1])-bf)})
    report['stations'] = stations
    summ = {}
    for label in sorted({s['label'] for s in stations}):
        S = [s for s in stations if s['label'] == label]; ins = [s for s in S if s['insideFootprint']]
        mm = [s['floorMismatchMetres'] for s in ins if s['floorMismatchMetres'] is not None]
        ab = [s['cameraAboveBimFloor'] for s in ins if s['cameraAboveBimFloor'] is not None]
        summ[label] = {'stations': len(S), 'insideFootprint': len(ins),
                       'cameraAboveBimFloorMedian': float(np.median(ab)) if ab else None,
                       'cameraAboveScanFloorMedian': float(np.nanmedian([s['cameraAboveScanFloor'] for s in S if s['cameraAboveScanFloor'] is not None])),
                       'floorMismatchMedian': float(np.median(mm)) if mm else None, 'floorMismatchAbsP80': float(np.percentile(np.abs(mm), 80)) if mm else None,
                       'withBimFloor': len(mm)}
    report['stationSummary'] = summ
    print('stations', json.dumps(summ))

    # 4. floor peaks inside footprint
    sv = rf._apply_array(reg, s14); ins = inside(sv[:, [0, 2]])
    def peaks_of(yv, w=None):
        h, e = np.histogram(yv, bins=np.arange(-3, 21, 0.1), weights=w)
        order = np.argsort(-h); out = []
        for k in order:
            if all(abs(e[k]-o) > 1.0 for o in out):
                out.append(float(e[k]+.05))
            if len(out) >= 5:
                break
        return sorted(out)
    hb = hpts[inside(hpts[:, [0, 2]])]
    report['floorPeaks'] = {'scanTransformedInside': peaks_of(sv[ins, 1]), 'bimHorizontalInside': peaks_of(hb[:, 1])}
    print('floor peaks', report['floorPeaks'])

    # 5. plan figures
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    colours = {'L3': '#c0392b', 'L2': '#1f5fbf'}
    variants = [('candidate', reg)] + alts
    for cut, b0, b1 in zip(a.cuts, a.scan_bands[0::2], a.scan_bands[1::2]):
        fig, axes = plt.subplots(1, len(variants), figsize=(10*len(variants), 10))
        axes = np.atleast_1d(axes)
        for ax, (name, r) in zip(axes, variants):
            ax.add_collection(LineCollection(section(tris, cut), colors='#222', linewidths=.5))
            m = (scan[:, 1] > b0) & (scan[:, 1] < b1); q = rf._apply_array(r, scan[m][::2])
            ax.scatter(q[:, 0], q[:, 2], s=.04, c='#e67e22', alpha=.35)
            for s_ in stations:
                p = rf._apply_array(r, np.array([s_['scan']]))[0]
                ax.scatter(p[0], p[2], s=16, c=colours.get(s_['label'], 'k'), marker='o' if s_['insideFootprint'] or name != 'candidate' else 'x')
            ax.set_aspect('equal'); ax.autoscale(); ax.grid(alpha=.25); ax.invert_yaxis()
            ax.set_title(f'{name}: yaw {r["rotationYDegrees"]:.2f}, t {np.round(r["translation"], 2).tolist()}\nBIM section y={cut} (black) · scan band {b0}..{b1} (orange) · stations L3 red / L2 blue', fontsize=10)
        fig.suptitle('Candidate registration · not surveyed', fontsize=12)
        plt.tight_layout(); plt.savefig(a.out/f'plan-cut-{cut:g}.png', dpi=90); plt.close(fig)

    # residual map inside band
    ev = s14[1::3]; evb = rf._apply_array(reg, ev); d, _ = tree.query(evb, distance_upper_bound=4); d = np.minimum(d, 4)
    fig, ax = plt.subplots(figsize=(11, 11))
    sc = ax.scatter(evb[::3, 0], evb[::3, 2], c=d[::3], s=.2, cmap='viridis', vmin=0, vmax=1)
    ax.add_collection(LineCollection(section(tris, a.cuts[0]), colors='k', linewidths=.3, alpha=.6))
    plt.colorbar(sc, label='held-out nearest BIM distance (m, capped)'); ax.set_aspect('equal'); ax.invert_yaxis()
    ax.set_title('Candidate: held-out scan-to-BIM nearest distance (internal, not surveyed)'); plt.tight_layout(); plt.savefig(a.out/'residual-map.png', dpi=90); plt.close(fig)

    # 6. BIM over photos
    from PIL import Image
    W, H = 2048, 1024
    photo_rows = []
    for spec in a.photo_stations:
        label, sid = spec.split(':', 1)
        path = dict(x.split('=', 1) for x in a.manifest)[label]
        man = json.loads(Path(path).read_text()); st = next(s for s in man['stations'] if s['id'] == sid)
        p = np.array(st['position'], float); rot = rd.sphere_rotation(st['e57Quaternion'])
        photo = rd.load_photo(Path(path).parent/st['file'], W, H)
        q = rf._apply_array(reg, p[None])[0]; brot = rd.rot_y(math.radians(reg['rotationYDegrees'])) @ rot
        near = rd._near(tris, q, r=25.0, dy=6.0)
        _, depth, shade = rd.render(q, brot, near, W, H, max_samples=12_000_000)
        cover = depth > 0
        gb = rd.gradient(shade*8)+rd.gradient(np.log1p(depth))*4
        gp = rd.gradient(rd.gray(photo))
        hs = rd.heading_scan(gp, gb, cover & (depth < 25), max_shift_deg=30)
        edges = gb > np.percentile(gb[cover], 90) if cover.any() else np.zeros_like(cover)
        img = photo.copy(); img[edges] = [0, 255, 255]
        Image.fromarray(img).save(a.out/f'photo-bim-{label}-{sid}.jpg', quality=85)
        photo_rows.append({'label': label, 'id': sid, 'bimCoverage': float(cover.mean()),
                           'photoVsBimHeading': {k: v for k, v in hs.items() if k not in ('shiftsDeg', 'scores')}})
        print('photo', label, sid, photo_rows[-1])
    report['photoChecks'] = photo_rows
    (a.out/'validation.json').write_text(json.dumps(report, indent=1))


if __name__ == '__main__':
    main()
