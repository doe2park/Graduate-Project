"""Global yaw + translation search of a scan against BIM floor sections (CPU, numpy/scipy only).

Used for captures that Cupix exported in an arbitrary horizontal frame (no floor plan uploaded), where no
landmark seed exists.  For one horizontal band of the scan (scan frame, Y-up metres) and one band of the BIM
(BIM viewer world), both are rasterised to 2D occupancy (top view), blurred, and every yaw (no reflection) is
scored by FFT cross-correlation over translation.  The best peaks become seeds for the constrained yaw+XYZ
trimmed ICP of scripts/registration_fit.py.

Scan input may be the exported mesh GLB (scripts/registration_diagnostics.load_scan_geometry) or the Cupix E57
point cloud (single-precision cartesian fields; read here without pye57).  Inputs are read-only.

    python3 scripts/global_registration_search.py search --e57 A.e57 [B.e57 ...] --bim-soup work/floorplans/arch-struct.f32 \
        --scan-band 5.5 6.5 --bim-band 6.0 7.0 --out DIR

Scores are image-similarity estimates; nothing here is surveyed accuracy.
"""
import argparse, json, math, re, struct, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))


# ---------------- E57 (Cupix export: uncompressed single-precision cartesian, 8-bit colour) ----------------
def _e57_logical(path):
    raw = np.fromfile(path, np.uint8)
    n = len(raw)//1024*1024
    return np.concatenate([raw[:n].reshape(-1, 1024)[:, :1020].reshape(-1), raw[n:]]).tobytes()


def _lo(p):
    return (p//1024)*1020 + p % 1024


def read_e57_points(path):
    """All data3D clouds as (N,3) float64 in the E57 frame (Z-up).  Cloud poses must be absent (checked)."""
    data = _e57_logical(path)
    _, _, _, _, xoff, xlen, _ = struct.unpack('<8sIIQQQQ', data[:48])
    xml = data[_lo(xoff):_lo(xoff)+xlen].decode('utf-8', 'replace')
    d3 = xml[xml.find('<data3D'):xml.find('</data3D>')]
    if '<pose' in d3:
        raise ValueError('%s: data3D pose present; not supported by this reader' % path)
    out = []
    for m in re.finditer(r'<points type="CompressedVector" fileOffset="(\d+)" recordCount="(\d+)">\s*<prototype.*?</prototype>', d3, re.S):
        off, count = int(m.group(1)), int(m.group(2))
        fields = re.findall(r'<([\w:]+) type="(Float|Integer)"([^/]*)/>', m.group(0))
        sec = _lo(off)
        if data[sec] != 1:
            raise ValueError('not a CompressedVector section')
        length, dphys, _ = struct.unpack('<QQQ', data[sec+8:sec+32])
        p, end = _lo(dphys), sec+length
        streams = [bytearray() for _ in fields]
        while p < end:
            kind = data[p]; plen = struct.unpack('<H', data[p+2:p+4])[0]+1
            if kind == 1:
                bc = struct.unpack('<H', data[p+4:p+6])[0]
                lens = struct.unpack('<%dH' % bc, data[p+6:p+6+2*bc]); q = p+6+2*bc
                for k, ln in enumerate(lens):
                    streams[k] += data[q:q+ln]; q += ln
            p += plen
        cols = {}
        for (name, typ, attrs), s in zip(fields, streams):
            if typ == 'Float':
                if 'single' not in attrs:
                    raise ValueError('only single-precision floats supported')
                cols[name] = np.frombuffer(bytes(s), np.float32)[:count]
        if any(len(cols[k]) != count for k in ('cartesianX', 'cartesianY', 'cartesianZ')):
            raise ValueError('truncated cartesian stream in %s' % path)
        out.append(np.stack([cols['cartesianX'], cols['cartesianY'], cols['cartesianZ']], 1).astype(float))
    return np.concatenate(out)


def e57_to_viewer(p):
    """E57 Z-up -> viewer Y-up [x, z, -y]: the same chain as the panorama manifest positions."""
    return np.stack([p[:, 0], p[:, 2], -p[:, 1]], 1)


# ---------------- rasterisation and search ----------------
def voxel(points, size):
    keys = np.floor(points/size).astype(np.int64)
    _, first = np.unique(keys, axis=0, return_index=True)
    return points[np.sort(first)]


def raster(xz, origin, shape, cell):
    ij = np.floor((xz-origin)/cell).astype(int)
    ok = (ij[:, 0] >= 0) & (ij[:, 0] < shape[0]) & (ij[:, 1] >= 0) & (ij[:, 1] < shape[1])
    img = np.zeros(shape); np.add.at(img, (ij[ok, 0], ij[ok, 1]), 1.0)
    return img


def prep(img, blur_cells):
    from scipy.ndimage import gaussian_filter
    img = np.minimum(img, np.percentile(img[img > 0], 90)) if (img > 0).any() else img
    img = (img > 0).astype(float)
    img = gaussian_filter(img, blur_cells)
    return img/(np.linalg.norm(img)+1e-12)


def rotate_xz(xz, deg):
    """Same yaw convention as registration_fit.apply: X' = c x + s z, Z' = -s x + c z."""
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return np.stack([c*xz[:, 0]+s*xz[:, 1], -s*xz[:, 0]+c*xz[:, 1]], 1)


def search(scan_xz, bim_xz, yaws, cell=0.25, blur=1.5, pad=30.0, top=5):
    """For each yaw, FFT cross-correlation over translation.  Returns rows sorted by score."""
    lo = bim_xz.min(0)-pad; hi = bim_xz.max(0)+pad
    shape = tuple(np.ceil((hi-lo)/cell).astype(int))
    B = prep(raster(bim_xz, lo, shape, cell), blur)
    FB = np.fft.rfft2(B)
    rows = []
    for yaw in yaws:
        r = rotate_xz(scan_xz, yaw); c0 = r.mean(0)
        S = prep(raster(r-c0+(hi-lo)/2, np.zeros(2), shape, cell), blur)   # scan centred in the canvas
        corr = np.fft.irfft2(FB*np.conj(np.fft.rfft2(S)), s=shape)
        k = np.unravel_index(np.argmax(corr), shape)
        shift = np.array([k[0] if k[0] < shape[0]/2 else k[0]-shape[0], k[1] if k[1] < shape[1]/2 else k[1]-shape[1]])*cell
        # scan point q (rotated, centred at canvas middle) maps to canvas q - c0 + mid + shift; canvas origin = lo
        t = lo + (hi-lo)/2 - c0 + shift
        rows.append({'yaw': float(yaw), 'score': float(corr[k]), 'tx': float(t[0]), 'tz': float(t[1])})
    return rows


def peaks(rows, min_sep_deg=8.0, top=6):
    rows = sorted(rows, key=lambda r: -r['score']); out = []
    for r in rows:
        if all(abs(((r['yaw']-o['yaw']+180) % 360)-180) >= min_sep_deg for o in out):
            out.append(r)
        if len(out) >= top:
            break
    return out


def bounded_icp(scan_pts, bim_pts, init, iterations=40, keep_percentile=65, max_distance=2.0, bound=4.0):
    """registration_fit.icp with a kd-tree distance bound (points farther than `bound` cannot be inliers anyway,
    since max_distance < bound); identical update step.  Keeps runtime short when a seed is far off."""
    from scipy.spatial import cKDTree
    import registration_fit as rf
    tree = cKDTree(bim_pts); reg = {'rotationYDegrees': init['rotationYDegrees'], 'translation': list(init['translation'])}
    for it in range(iterations):
        d, j = tree.query(rf._apply_array(reg, scan_pts), distance_upper_bound=bound)
        fin = np.isfinite(d)
        if fin.sum() < 100:
            break
        thr = min(max_distance, np.percentile(np.where(fin, d, np.inf), keep_percentile))
        keep = fin & (d < thr)
        new = rf._fit_arrays(scan_pts[keep], bim_pts[j[keep]])
        change = math.dist(new['translation'], reg['translation'])+abs(math.radians(new['rotationYDegrees']-reg['rotationYDegrees']))
        reg = new
        if change < 1e-5:
            break
    reg['iterations'] = it+1
    return reg


def nn_bounded(reg, pts, bim_pts, bound=4.0, tree=None):
    from scipy.spatial import cKDTree
    import registration_fit as rf
    if len(pts) == 0:
        return {'points': 0}
    d, _ = (tree or cKDTree(bim_pts)).query(rf._apply_array(reg, pts), distance_upper_bound=bound)
    d = np.minimum(d, bound)
    return {'medianMetres': float(np.median(d)), 'p80Metres': float(np.percentile(d, 80)), 'within010': float((d <= .10).mean()),
            'within025': float((d <= .25).mean()), 'within05': float((d <= .5).mean()), 'points': int(len(d)), 'distancesCappedAt': bound}


def refine(scan, tris, hyps, bim_height, out_dir):
    """Constrained yaw+XYZ trimmed ICP (registration_fit.icp) from each seed; held-out nearest-point stats."""
    import registration_fit as rf
    lo, hi = bim_height
    y = tris[:, :, 1]; sel = tris[(y.max(1) >= lo) & (y.min(1) <= hi)]
    bim = rf._voxel(rf._sample_surface(sel, 15), .12); bim = bim[(bim[:, 1] >= lo) & (bim[:, 1] <= hi)]
    scan = rf._voxel(scan, .14)
    rows = []
    for h in hyps:
        init = {'rotationYDegrees': h['yaw'], 'translation': [h['tx'], h['ty'], h['tz']]}
        sb = rf._apply_array(init, scan); s = scan[(sb[:, 1] >= lo-.3) & (sb[:, 1] <= hi+.3)]
        train, evaluate = s[0::3], s[1::3]
        before = nn_bounded(init, evaluate, bim)
        reg = bounded_icp(train, bim, init)
        after = nn_bounded(reg, evaluate, bim)
        rows.append({'name': h['name'], 'init': init, 'icp': reg, 'heldOutBefore': before, 'heldOutAfter': after,
                     'trainPoints': int(len(train)), 'bimPoints': int(len(bim))})
        print(h['name'], round(reg['rotationYDegrees'], 3), [round(v, 3) for v in reg['translation']], 'iters', reg['iterations'],
              'before med %.3f after med %.3f p80 %.3f w25 %.3f w50 %.3f' % (before['medianMetres'], after['medianMetres'], after['p80Metres'], after['within025'], after['within05']))
    return rows, bim


def load_scan(e57, mesh):
    import registration_fit as rf, registration_diagnostics as rd
    scan = [e57_to_viewer(read_e57_points(p)) for p in e57]
    if mesh:
        scan.append(rf._sample_surface(rd.load_scan_geometry(mesh), 15))
    return voxel(np.concatenate(scan), 0.1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('search', 'refine'):
        p = sub.add_parser(name)
        p.add_argument('--e57', nargs='*', default=[]); p.add_argument('--mesh', nargs='*', default=[])
        p.add_argument('--bim-soup', required=True); p.add_argument('--out', type=Path, required=True)
    s_ = sub.choices['search']
    s_.add_argument('--scan-band', type=float, nargs=2, required=True); s_.add_argument('--bim-band', type=float, nargs=2, action='append', required=True)
    s_.add_argument('--cell', type=float, default=0.25); s_.add_argument('--blur', type=float, default=1.5)
    r_ = sub.choices['refine']
    r_.add_argument('--hyp', action='append', required=True, help='name:yaw:tx:ty:tz seed (scan -> BIM, registration_fit convention)')
    r_.add_argument('--bim-height', type=float, nargs=2, required=True)
    a = ap.parse_args()
    import registration_fit as rf, registration_diagnostics as rd
    scan = load_scan(a.e57, a.mesh)
    tris = rd.load_soup(a.bim_soup)
    a.out.mkdir(parents=True, exist_ok=True)
    if a.cmd == 'refine':
        hyps = []
        for h in a.hyp:
            n, *v = h.split(':'); v = [float(x) for x in v]
            hyps.append({'name': n, 'yaw': v[0], 'tx': v[1], 'ty': v[2], 'tz': v[3]})
        rows, _ = refine(scan, tris, hyps, a.bim_height, a.out)
        (a.out/'refine.json').write_text(json.dumps({'bimHeightBand': a.bim_height, 'hypotheses': rows}, indent=1))
        return
    s = scan[(scan[:, 1] >= a.scan_band[0]) & (scan[:, 1] <= a.scan_band[1])][:, [0, 2]]
    result = {'scanBand': a.scan_band, 'scanPoints': int(len(s)), 'cell': a.cell, 'blurCells': a.blur, 'levels': []}
    for band in a.bim_band:
        y = tris[:, :, 1]; sel = tris[(y.max(1) >= band[0]) & (y.min(1) <= band[1])]
        pts = voxel(rf._sample_surface(sel, 15), 0.1); pts = pts[(pts[:, 1] >= band[0]) & (pts[:, 1] <= band[1])][:, [0, 2]]
        coarse = search(s, pts, np.arange(0, 360, 2.0), a.cell, a.blur)
        best = peaks(coarse)
        fine = []
        for b in best:
            f = search(s, pts, b['yaw']+np.arange(-2, 2.01, 0.25), a.cell, a.blur)
            fine.append(max(f, key=lambda r: r['score']))
        fine.sort(key=lambda r: -r['score'])
        result['levels'].append({'bimBand': band, 'bimPoints': int(len(pts)), 'coarseMedianScore': float(np.median([r['score'] for r in coarse])),
                                 'hypotheses': fine, 'coarse': coarse})
        print(band, [(round(r['yaw'], 2), round(r['score'], 4), round(r['tx'], 2), round(r['tz'], 2)) for r in fine], 'median', round(result['levels'][-1]['coarseMedianScore'], 4))
    (a.out/'global-search.json').write_text(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
