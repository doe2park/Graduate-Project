"""Offline Scan/BIM overlay diagnostics (CPU only; no browser, no GPU).

Renders the captured scan mesh as an equirectangular image from a photo
station, using exactly the panorama orientation convention of
scan-photo.html, and compares it with the captured 360-degree photo.  The
best circular azimuth shift between the two is the heading error of the photo
relative to the mesh it was reconstructed with.  Optionally renders BIM
geometry (decoded, uncompressed triangle soup in BIM viewer world) from the
registered station to measure photo-to-BIM heading.

This is a diagnostic: correlation peaks are image-similarity estimates, not
surveyed orientation accuracy.

    python3 scripts/registration_diagnostics.py --capture 2026-09-17 --stations 0 40 80 --out DIR
"""
import argparse, json, math, struct
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = {
    '2026-05-06': {'manifest': 'scan-assets/panoramas/manifest.json',
                   'mesh': ['scan-assets/mobile/level1-scan-2026-05-06.glb', 'scan-assets/mobile/level1-scan-2026-05-06-part2.glb'],
                   'registration': 'alignment-analysis/accepted-registration.json'},
    '2026-09-17': {'manifest': 'scan-assets/captures/2026-09-17/panoramas/manifest.json',
                   'mesh': ['scan-assets/captures/2026-09-17/mobile/scan.glb'],
                   'registration': 'scan-assets/captures/2026-09-17/registration.json'},
}


# ---------- small quaternion / matrix helpers (Three.js conventions) ----------
def quat_to_matrix(q):
    x, y, z, w = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


AXIS = rot_x(-math.pi/2)        # E57/GLB Z-up -> viewer Y-up
CENTER = rot_y(math.pi)         # scan-photo.html centerCorrection


def sphere_rotation(e57_quaternion, heading_offset_deg=0.0):
    """Rotation of the textured sphere in scan-photo.html, optionally pre-multiplied by a heading offset about +Y."""
    r = AXIS @ quat_to_matrix(e57_quaternion) @ AXIS.T @ CENTER
    return rot_y(math.radians(heading_offset_deg)) @ r


def pixel_directions(width, height):
    """Sphere-local unit direction of every equirect pixel centre (after geometry.scale(-1,1,1))."""
    u = (np.arange(width)+.5)/width
    v = (np.arange(height)+.5)/height
    phi, theta = np.meshgrid(2*math.pi*u, math.pi*v)
    return np.stack([np.cos(phi)*np.sin(theta), np.cos(theta), np.sin(phi)*np.sin(theta)], -1)


def directions_to_pixels(d, rotation, width, height):
    local = d @ rotation            # rotation.T applied to row vectors
    norm = np.linalg.norm(local, axis=1)
    theta = np.arccos(np.clip(local[:, 1]/norm, -1, 1))
    u = (np.arctan2(local[:, 2], local[:, 0]) / (2*math.pi)) % 1
    col = np.minimum((u*width).astype(np.int64), width-1)
    row = np.minimum((theta/math.pi*height).astype(np.int64), height-1)
    return row, col


# ---------- GLB reading (uncompressed meshes only) ----------
COMPONENTS = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}
SIZES = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}


def read_glb(path):
    data = Path(path).read_bytes()
    size = struct.unpack_from('<I', data, 12)[0]
    gltf = json.loads(data[20:20+size])
    binary = data[20+size+8:]
    return gltf, binary


def accessor(gltf, binary, index):
    a = gltf['accessors'][index]
    view = gltf['bufferViews'][a['bufferView']]
    dtype = COMPONENTS[a['componentType']]
    n = SIZES[a['type']]
    start = view.get('byteOffset', 0) + a.get('byteOffset', 0)
    stride = view.get('byteStride')
    if stride and stride != n*np.dtype(dtype).itemsize:
        raw = np.frombuffer(binary, np.uint8, count=stride*a['count'], offset=start).reshape(a['count'], stride)
        return raw[:, :n*np.dtype(dtype).itemsize].copy().view(dtype).reshape(a['count'], n)
    return np.frombuffer(binary, dtype, count=a['count']*n, offset=start).reshape(a['count'], n)


def node_matrix(node):
    if 'matrix' in node:
        return np.array(node['matrix'], dtype=float).reshape(4, 4).T
    m = np.eye(4)
    if 'scale' in node:
        m = np.diag(list(node['scale'])+[1]) @ m
    if 'rotation' in node:
        r = np.eye(4); r[:3, :3] = quat_to_matrix(node['rotation']); m = r @ m
    if 'translation' in node:
        t = np.eye(4); t[:3, 3] = node['translation']; m = t @ m
    return m


def mesh_instances(gltf):
    out = []
    def walk(i, parent):
        node = gltf['nodes'][i]
        m = parent @ node_matrix(node)
        if 'mesh' in node:
            out.append((node['mesh'], m))
        for c in node.get('children', []):
            walk(c, m)
    for root in gltf['scenes'][gltf.get('scene', 0)]['nodes']:
        walk(root, np.eye(4))
    return out


def load_textured_scan(paths, texture_max=512):
    """Triangles (N,3,3) in viewer Y-up scan frame, UVs (N,3,2), texture index per triangle, list of textures."""
    from PIL import Image
    import io
    tris, uvs, tex_ids, textures = [], [], [], []
    for path in paths:
        gltf, binary = read_glb(ROOT/path)
        base = len(textures)
        for img in gltf['images']:
            view = gltf['bufferViews'][img['bufferView']]
            raw = binary[view.get('byteOffset', 0):view.get('byteOffset', 0)+view['byteLength']]
            im = Image.open(io.BytesIO(raw)).convert('RGB')
            im.thumbnail((texture_max, texture_max))
            textures.append(np.asarray(im))
        for mesh_index, m in mesh_instances(gltf):
            for prim in gltf['meshes'][mesh_index]['primitives']:
                pos = accessor(gltf, binary, prim['attributes']['POSITION']).astype(float)
                uv = accessor(gltf, binary, prim['attributes']['TEXCOORD_0']).astype(float)
                idx = accessor(gltf, binary, prim['indices']).reshape(-1).astype(np.int64)
                world = pos @ m[:3, :3].T + m[:3, 3]
                world = world @ AXIS.T
                tris.append(world[idx].reshape(-1, 3, 3)); uvs.append(uv[idx].reshape(-1, 3, 2))
                material = gltf['materials'][prim['material']]
                texture = gltf['textures'][material['pbrMetallicRoughness']['baseColorTexture']['index']]['source']
                tex_ids.append(np.full(len(idx)//3, base+texture))
    return np.concatenate(tris), np.concatenate(uvs), np.concatenate(tex_ids), textures


def load_scan_geometry(paths):
    """Triangles (N,3,3) only, viewer Y-up scan frame (same transform chain as the scan pane)."""
    out = []
    for path in paths:
        gltf, binary = read_glb(ROOT/path)
        for mesh_index, m in mesh_instances(gltf):
            for prim in gltf['meshes'][mesh_index]['primitives']:
                pos = accessor(gltf, binary, prim['attributes']['POSITION']).astype(float)
                idx = accessor(gltf, binary, prim['indices']).reshape(-1).astype(np.int64)
                world = (pos @ m[:3, :3].T + m[:3, 3]) @ AXIS.T
                out.append(world[idx].reshape(-1, 3, 3))
    return np.concatenate(out)


def load_soup(path):
    """Plain float32 triangle soup written by tools/decode_bim_soup.mjs: N*9 floats, BIM viewer world."""
    return np.fromfile(path, np.float32).reshape(-1, 3, 3).astype(float)


# ---------- point-splat equirect renderer ----------
def render(station, rotation, tris, width, height, uvs=None, tex_ids=None, textures=None, max_samples=40_000_000, seed=0):
    """Nearest-surface equirect render.  Returns (rgb or None, depth, normal-dot) arrays."""
    rng = np.random.default_rng(seed)
    a, b, c = tris[:, 0]-station, tris[:, 1]-station, tris[:, 2]-station
    centroid = (a+b+c)/3
    dist = np.linalg.norm(centroid, axis=1)
    keep = dist > .05
    area = .5*np.linalg.norm(np.cross(b-a, c-a), axis=1)
    pixel = (2*math.pi/width)**2
    # samples ~ 3 per covered pixel, bounded per triangle
    counts = np.clip(np.ceil(6*area/np.maximum(dist, .2)**2/pixel), 1, 60000).astype(np.int64)
    counts[~keep] = 0
    total = counts.sum()
    if total > max_samples:
        counts = np.maximum((counts*max_samples/total).astype(np.int64), keep.astype(np.int64))
    tri_index = np.repeat(np.arange(len(tris)), counts)
    r1, r2 = rng.random(len(tri_index)), rng.random(len(tri_index))
    flip = r1+r2 > 1
    r1[flip], r2[flip] = 1-r1[flip], 1-r2[flip]
    p = a[tri_index]+(b-a)[tri_index]*r1[:, None]+(c-a)[tri_index]*r2[:, None]
    depth = np.linalg.norm(p, axis=1)
    row, col = directions_to_pixels(p, rotation, width, height)
    flat = row*width+col
    zbuf = np.full(width*height, np.inf)
    np.minimum.at(zbuf, flat, depth)
    win = depth <= zbuf[flat]+1e-9
    n = np.cross(b-a, c-a); n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    facing = np.abs(np.einsum('ij,ij->i', n[tri_index], p/np.maximum(depth[:, None], 1e-9)))
    shade = np.zeros(width*height); shade[flat[win]] = facing[win]
    rgb = None
    if textures is not None:
        uv = uvs[tri_index, 0]+(uvs[tri_index, 1]-uvs[tri_index, 0])*r1[:, None]+(uvs[tri_index, 2]-uvs[tri_index, 0])*r2[:, None]
        rgb = np.zeros((width*height, 3), np.uint8)
        sel = np.nonzero(win)[0]
        tids = tex_ids[tri_index[sel]]
        for t in np.unique(tids):
            s = sel[tids == t]; tex = textures[t]; h, w = tex.shape[:2]
            x = np.clip((uv[s, 0] % 1)*w, 0, w-1).astype(int); y = np.clip((uv[s, 1] % 1)*h, 0, h-1).astype(int)
            rgb[flat[s]] = tex[y, x]
        rgb = rgb.reshape(height, width, 3)
    zbuf[~np.isfinite(zbuf)] = 0
    return rgb, zbuf.reshape(height, width), shade.reshape(height, width)


# ---------- image comparison ----------
def gray(rgb):
    rgb = np.asarray(rgb[..., :3], dtype=np.float64)
    return np.log1p(rgb[..., 0]*.299+rgb[..., 1]*.587+rgb[..., 2]*.114)


def blur(img, k=1):
    out = img.copy()
    for _ in range(k):
        out = (np.roll(out, 1, 1)+out+np.roll(out, -1, 1))/3
        out[1:-1] = (out[:-2]+out[1:-1]+out[2:])/3
    return out


def gradient(img):
    g = blur(img, 1)
    gx = np.roll(g, -1, 1)-np.roll(g, 1, 1)
    gy = np.zeros_like(g); gy[1:-1] = g[2:]-g[:-2]
    return np.hypot(gx, gy)


def heading_scan(reference, moving, mask, max_shift_deg=180.0, rows=(0.12, 0.88)):
    """NCC of gradient images over circular column shifts; positive shift = rotate moving to +column."""
    h, w = reference.shape
    r0, r1 = int(rows[0]*h), int(rows[1]*h)
    ref = reference[r0:r1]; mov = moving[r0:r1]; m = mask[r0:r1]
    shifts = np.arange(-int(round(max_shift_deg/360*w)), int(round(max_shift_deg/360*w))+1)
    scores = []
    for s in shifts:
        mm = np.roll(m, s, 1)
        a = ref[mm]; b = np.roll(mov, s, 1)[mm]
        if a.size < 100:
            scores.append(-1); continue
        a = a-a.mean(); b = b-b.mean()
        scores.append(float((a*b).sum()/math.sqrt((a*a).sum()*(b*b).sum()+1e-12)))
    scores = np.array(scores)
    best = int(np.argmax(scores))
    # sub-pixel parabolic refinement
    sub = 0.0
    if 0 < best < len(scores)-1:
        y0, y1, y2 = scores[best-1:best+2]
        den = y0-2*y1+y2
        sub = .5*(y0-y2)/den if abs(den) > 1e-12 else 0.0
    zero = scores[len(shifts)//2]
    return {'bestShiftDeg': float((shifts[best]+sub)*360/w), 'bestScore': float(scores[best]), 'scoreAtZero': float(zero),
            'secondPeakScore': float(np.max(np.where(np.abs(shifts-shifts[best]) > w/36, scores, -1))),
            'shiftsDeg': (shifts*360/w).tolist(), 'scores': scores.tolist()}


def load_photo(path, width, height):
    from PIL import Image
    with Image.open(path) as im:
        return np.asarray(im.convert('RGB').resize((width, height), Image.Resampling.LANCZOS))


def registration_to_bim(registration, p):
    a = math.radians(registration['rotationYDegrees']); t = registration['translation']
    c, s = math.cos(a), math.sin(a)
    return np.array([c*p[0]+s*p[2]+t[0], p[1]+t[1], -s*p[0]+c*p[2]+t[2]])


# ---------- wall / floor ray check (independent of ICP sampling) ----------
def raycast(tris, origin, dirs, maxd=20.0):
    a = tris[:, 0]-origin; e1 = tris[:, 1]-tris[:, 0]; e2 = tris[:, 2]-tris[:, 0]
    out = np.full(len(dirs), np.inf)
    for k, d in enumerate(dirs):
        p = np.cross(d, e2); det = np.einsum('ij,ij->i', e1, p)
        ok = np.abs(det) > 1e-9; inv = np.where(ok, 1/np.where(ok, det, 1), 0)
        tvec = -a; u = np.einsum('ij,ij->i', tvec, p)*inv
        q = np.cross(tvec, e1); v = (q @ d)*inv; t = np.einsum('ij,ij->i', e2, q)*inv
        hit = ok & (u >= 0) & (v >= 0) & (u+v <= 1) & (t > .05) & (t < maxd)
        if hit.any():
            out[k] = t[hit].min()
    return out


def _near(tris, p, r=20.0, dy=4.0):
    c = tris.mean(1)
    return tris[(np.abs(c[:, 0]-p[0]) < r) & (np.abs(c[:, 2]-p[2]) < r) & (np.abs(c[:, 1]-p[1]) < dy)]


def wall_check(registration, tris_scan, bim, stations, wall_height=2.3, step_deg=5):
    """Per station: first floor below (scan vs BIM) and horizontal rays at floor+wall_height.
    d_scan - d_bim = n . delta  ->  robust 2D local offset delta of the scan relative to BIM (metres)."""
    a = math.radians(registration['rotationYDegrees']); c, s = math.cos(a), math.sin(a)
    R = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]); t = np.array(registration['translation'])
    btris = (tris_scan.reshape(-1, 3) @ R.T + t).reshape(-1, 3, 3)
    az = np.radians(np.arange(0, 360, step_deg)); dirs = np.stack([np.cos(az), np.zeros_like(az), np.sin(az)], 1)
    down = np.array([[0.0, -1.0, 0.0]])
    rows = []
    for i, pos in stations:
        p = registration_to_bim(registration, pos)
        ns, nb = _near(btris, p), _near(bim, p)
        fs, fb = raycast(ns, p, down)[0], raycast(nb, p, down)[0]
        if not (np.isfinite(fs) and np.isfinite(fb)):
            continue
        q = p.copy(); q[1] = p[1]-fb+wall_height
        ds, db = raycast(ns, q, dirs), raycast(nb, q, dirs)
        diff = ds-db; ok = np.isfinite(diff) & (np.abs(diff) < 1.0) & (db < 15)
        # floorOffset = scan floor height - BIM floor height (positive: scan floor above BIM floor)
        row = {'station': i, 'floorOffsetMetres': float(fb-fs), 'rays': int(ok.sum())}
        if ok.sum() >= 12:
            A = dirs[ok][:, [0, 2]]; y = diff[ok]; w = np.ones(len(y))
            for _ in range(8):
                delta = np.linalg.lstsq(A*w[:, None], y*w, rcond=None)[0]
                r = y-A@delta; sc = 1.4826*np.median(np.abs(r))+1e-3; w = 1/np.maximum(1, np.abs(r)/(2*sc))
            row.update({'localOffsetMetres': delta.tolist(), 'localOffsetNorm': float(np.hypot(*delta)),
                        'medianAbsRayDiffMetres': float(np.median(np.abs(y)))})
        rows.append(row)
    norms = [r['localOffsetNorm'] for r in rows if 'localOffsetNorm' in r]
    floors = [r['floorOffsetMetres'] for r in rows]
    summary = {'stations': len(rows), 'wallStations': len(norms),
               'localOffsetMedianMetres': float(np.median(norms)) if norms else None,
               'localOffsetP80Metres': float(np.percentile(norms, 80)) if norms else None,
               'floorOffsetMedianMetres': float(np.median(floors)) if floors else None,
               'medianAbsRayDiffMetres': float(np.median([r['medianAbsRayDiffMetres'] for r in rows if 'medianAbsRayDiffMetres' in r])) if norms else None}
    return summary, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--capture', choices=CAPTURES, required=True)
    ap.add_argument('--stations', type=int, nargs='+', required=True)
    ap.add_argument('--width', type=int, default=1024)
    ap.add_argument('--bim-soup', type=Path, help='float32 triangle soup in BIM viewer world (optional)')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--save-images', action='store_true')
    ap.add_argument('--mode', choices=['heading', 'walls'], default='heading',
                    help='heading: photo vs mesh (and BIM) equirect comparison; walls: floor + wall ray offsets scan vs BIM (needs --bim-soup)')
    ap.add_argument('--registration', type=Path, help='registration/candidate JSON to evaluate instead of the capture default')
    args = ap.parse_args()
    cfg = CAPTURES[args.capture]; W = args.width; H = W//2
    manifest_path = ROOT/cfg['manifest']; manifest = json.loads(manifest_path.read_text())
    registration = json.loads((args.registration or ROOT/cfg['registration']).read_text())
    if args.mode == 'walls':
        if not args.bim_soup:
            ap.error('--mode walls needs --bim-soup')
        summary, rows = wall_check(registration, load_scan_geometry(cfg['mesh']), load_soup(args.bim_soup),
                                   [(i, np.array(manifest['stations'][i]['position'], float)) for i in args.stations])
        args.out.mkdir(parents=True, exist_ok=True)
        name = (args.registration.stem if args.registration else 'default')
        (args.out/f'walls-{args.capture}-{name}.json').write_text(json.dumps({'registration': str(args.registration or cfg['registration']), 'summary': summary, 'rows': rows}, indent=1)+'\n')
        print(json.dumps(summary))
        return
    tris, uvs, tex_ids, textures = load_textured_scan(cfg['mesh'])
    bim = load_soup(args.bim_soup) if args.bim_soup else None
    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    for index in args.stations:
        st = manifest['stations'][index]
        pos = np.array(st['position'], float)
        rot = sphere_rotation(st['e57Quaternion'])
        photo = load_photo(manifest_path.parent/'mobile'/st['file'], W, H)
        rgb, depth, _ = render(pos, rot, tris, W, H, uvs, tex_ids, textures)
        cover = depth > 0
        gp, gm = gradient(gray(photo)), gradient(gray(rgb))
        mesh = heading_scan(gp, gm, cover & (depth < 25))
        mirrored = heading_scan(gp, gradient(gray(rgb[:, ::-1])), (cover & (depth < 25))[:, ::-1])
        entry = {'capture': args.capture, 'station': index, 'id': st['id'], 'position': st['position'],
                 'meshCoverage': float(cover.mean()),
                 'photoVsMesh': {k: v for k, v in mesh.items() if k not in ('shiftsDeg', 'scores')},
                 'photoVsMirroredMesh': {k: v for k, v in mirrored.items() if k not in ('shiftsDeg', 'scores')}}
        if bim is not None:
            bpos = registration_to_bim(registration, pos)
            brot = rot_y(math.radians(registration['rotationYDegrees'])) @ rot
            _, bdepth, bshade = render(bpos, brot, bim, W, H)
            bcover = bdepth > 0
            gb = gradient(bshade*8)+gradient(np.log1p(bdepth))*4
            entry['photoVsBim'] = {k: v for k, v in heading_scan(gp, gb, bcover & (bdepth < 25)).items() if k not in ('shiftsDeg', 'scores')}
            entry['meshDepthVsBimDepth'] = {k: v for k, v in heading_scan(gradient(np.log1p(depth))*4, gradient(np.log1p(bdepth))*4, bcover & cover).items() if k not in ('shiftsDeg', 'scores')}
            both = cover & bcover
            entry['meshMinusBimDepthMedianMetres'] = float(np.median((depth-bdepth)[both])) if both.any() else None
            if args.save_images:
                from PIL import Image
                Image.fromarray(np.clip(bshade*255, 0, 255).astype(np.uint8)).save(args.out/f'{args.capture}-s{index:03d}-bim.png')
        results.append(entry)
        if args.save_images:
            from PIL import Image
            Image.fromarray(photo).save(args.out/f'{args.capture}-s{index:03d}-photo.png')
            Image.fromarray(rgb).save(args.out/f'{args.capture}-s{index:03d}-mesh.png')
            blend = (photo.astype(float)*.5+rgb.astype(float)*.5).astype(np.uint8)
            Image.fromarray(blend).save(args.out/f'{args.capture}-s{index:03d}-blend.png')
        print(json.dumps({k: v for k, v in entry.items()}, indent=None))
    (args.out/f'diagnostics-{args.capture}.json').write_text(json.dumps(results, indent=2)+'\n')


if __name__ == '__main__':
    main()
