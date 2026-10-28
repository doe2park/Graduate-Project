"""Place a second Cupix video (upper floors) in the BIM frame, review it, and build a local multi-floor photo package.

Consumes `scripts/multifloor_link.py` output (photo-matched yaw + translation of video B into the placed video A frame).
System python (NumPy, SciPy, Matplotlib, Pillow); CPU only.

    python3 scripts/multifloor_review.py register --link work/multifloor/2026-10-18/link.json \
        --ground capture-local/grimes-GROUND-2026-10-18 --e57 <Ground E57 files...> \
        --placed-registration scan-assets/captures/2026-10-18/registration.json \
        --candidate capture-local/grimes-L3-2026-10-18/registration-candidate-upper-walk-2026-10-20.json \
        --review capture-local/grimes-L3-2026-10-18/registration-review/multifloor-2026-10-20
    python3 scripts/multifloor_review.py package --candidate <that json> --ground ... --blurred <privacy output of video B> \
        --base scan-assets/captures/2026-10-18 --out capture-local/grimes-oct18-floors
    python3 scripts/multifloor_review.py floors --candidate <that json> --ground ... --blurred <privacy output of video B> \
        --base scan-assets/captures/2026-10-18 --link work/multifloor/2026-10-18/link.json   # -> capture-local/grimes-L{2,3}-2026-10-18-v2

`register` = image-only placement (video B -> video A frame -> placed registration -> BIM), then a yaw+XYZ trimmed ICP of
video B's own E57 points against the BIM L2/L3 band as an independent check/refinement, per-station BIM floor ray cast,
figures. `package` = one Oct 18 station graph (Level 1 + atrium stairs + Level 3 + partial Level 2) in the Level 1 scan
frame so the existing provisional Oct 18 registration applies unchanged. Never overwrites an existing file or folder.
Placement is photogrammetric/ICP consistency, NOT surveyed accuracy; every output says "provisional, not surveyed".
"""
import argparse, datetime, hashlib, json, math, os, shutil, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SLAB = {'LOWER': 0.6, 'L1': 5.2, 'L2': 9.4, 'L3': 14.3}  # BIM slab heights, viewer frame (m)
LEVEL_NAMES = {'L1': 'Level 1', 'L2': 'Level 2', 'L3': 'Level 3', 'stairs': 'Stairs'}
LABEL = 'provisional, not surveyed'


# ---------------- transforms (registration_fit convention) ----------------
def apply(reg, p):
    a = math.radians(reg['rotationYDegrees']); c, s = math.cos(a), math.sin(a); t = reg['translation']
    p = np.asarray(p, float).reshape(-1, 3)
    return np.stack([c * p[:, 0] + s * p[:, 2] + t[0], p[:, 1] + t[1], -s * p[:, 0] + c * p[:, 2] + t[2]], 1)


def compose(first, then):
    """Registration equal to applying `first` and then `then`."""
    t = apply({'rotationYDegrees': then['rotationYDegrees'], 'translation': [0, 0, 0]}, first['translation'])[0] + np.asarray(then['translation'], float)
    return {'rotationYDegrees': first['rotationYDegrees'] + then['rotationYDegrees'], 'translation': [float(v) for v in t]}


def invert(reg):
    inv_rot = {'rotationYDegrees': -reg['rotationYDegrees'], 'translation': [0, 0, 0]}
    t = -apply(inv_rot, reg['translation'])[0]
    return {'rotationYDegrees': -reg['rotationYDegrees'], 'translation': [float(v) for v in t]}


def quat_mul(a, b):
    ax, ay, az, aw = a; bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz]


def rotate_e57_quaternion(q, rotation_y_degrees):
    """A viewer yaw a (registration convention) is the E57 rotation about +Z by a: q' = Rz(a) q."""
    h = math.radians(rotation_y_degrees) / 2
    out = quat_mul([0.0, 0.0, math.sin(h), math.cos(h)], list(q)); n = math.sqrt(sum(v * v for v in out))
    return [v / n for v in out]


# ---------------- BIM checks ----------------
def horizontal_triangles(tris, min_normal_y=0.9):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]); ln = np.linalg.norm(n, axis=1)
    ok = ln > 1e-9
    ny = np.zeros(len(tris)); ny[ok] = np.abs(n[ok, 1]) / ln[ok]
    return tris[ny >= min_normal_y]


def floor_below(htris, point, max_drop=4.0):
    """Highest near-horizontal BIM surface under `point` (x, y, z) within `max_drop` m, or None."""
    x, y, z = point
    a, b, c = htris[:, 0], htris[:, 1], htris[:, 2]
    sel = (np.minimum(np.minimum(a[:, 0], b[:, 0]), c[:, 0]) <= x) & (np.maximum(np.maximum(a[:, 0], b[:, 0]), c[:, 0]) >= x) & \
          (np.minimum(np.minimum(a[:, 2], b[:, 2]), c[:, 2]) <= z) & (np.maximum(np.maximum(a[:, 2], b[:, 2]), c[:, 2]) >= z)
    if not sel.any():
        return None
    a, b, c = a[sel], b[sel], c[sel]
    v0 = c[:, [0, 2]] - a[:, [0, 2]]; v1 = b[:, [0, 2]] - a[:, [0, 2]]; v2 = np.array([x, z]) - a[:, [0, 2]]
    d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1); d20 = (v2 * v0).sum(1); d21 = (v2 * v1).sum(1)
    den = d00 * d11 - d01 * d01; good = np.abs(den) > 1e-12
    u = np.where(good, (d11 * d20 - d01 * d21) / np.where(good, den, 1), -1); v = np.where(good, (d00 * d21 - d01 * d20) / np.where(good, den, 1), -1)
    inside = (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)
    ys = a[:, 1] + u * (c[:, 1] - a[:, 1]) + v * (b[:, 1] - a[:, 1])
    ok = inside & (ys < y - 0.3) & (ys > y - max_drop)
    return float(ys[ok].max()) if ok.any() else None


def classify_level(floor_y, tolerance=0.45):
    """BIM floor height under a station -> L1/L2/L3, 'stairs' between slabs, None when no floor was found."""
    if floor_y is None:
        return None
    for k in ('L3', 'L2', 'L1'):
        if abs(floor_y - SLAB[k]) <= tolerance:
            return k
    return 'stairs'


def plan_segments(tris, height):
    """BIM section at `height`: (N, 2, 2) xz segments."""
    ys = tris[:, :, 1]; sel = tris[(ys.min(1) < height) & (ys.max(1) > height)]
    pts = {}
    for i, j in ((0, 1), (1, 2), (2, 0)):
        pa, pb = sel[:, i], sel[:, j]; da, db = pa[:, 1] - height, pb[:, 1] - height; m = da * db < 0
        f = (da[m] / (da[m] - db[m]))[:, None]
        for k, q in zip(np.nonzero(m)[0], (pa[m] + (pb[m] - pa[m]) * f)[:, [0, 2]]): pts.setdefault(k, []).append(q)
    return np.array([v[:2] for v in pts.values() if len(v) >= 2]).reshape(-1, 2, 2)


def segment_blocked(p, q, segs):
    """True when the xz segment p-q properly crosses any section segment."""
    if len(segs) == 0:
        return False
    a, b = segs[:, 0], segs[:, 1]
    def orient(u, v, w): return (v[..., 0] - u[..., 0]) * (w[..., 1] - u[..., 1]) - (v[..., 1] - u[..., 1]) * (w[..., 0] - u[..., 0])
    p = np.asarray(p, float); q = np.asarray(q, float)
    o1 = orient(p, q, a); o2 = orient(p, q, b); o3 = orient(a, b, p); o4 = orient(a, b, q)
    return bool(((o1 * o2 < 0) & (o3 * o4 < 0)).any())


def bim_clear_test(tris):
    """clear(a, b) for build_route: no BIM wall crossing at 1.0 m and 1.7 m above the slab under the stations."""
    cache = {}
    def clear(pa, pb):
        lvl = min(SLAB, key=lambda k: abs(pa[1] - 2.0 - SLAB[k]))
        if lvl not in cache:
            cache[lvl] = [plan_segments(tris, SLAB[lvl] + h) for h in (1.0, 1.7)]
        return not any(segment_blocked(pa[[0, 2]], pb[[0, 2]], s) for s in cache[lvl])
    return clear


# ---------------- route (pure; tests/test_multifloor.py) ----------------
def build_route(stations, visual_links=(), a_stations=(), max_step=7.7, max_rise=1.5, stair_step=9.0, stair_rise=4.6, link_radius=4.5, link_rise=1.0,
                clear=None, clear_radius=4.0):
    """stations: video B in frame order [{'id','position'(BIM),'level'}]. a_stations: placed stations [{'index','position','level'}].
    Returns {id: {neighbour id/index key: kind}} with kinds route / stairs / route-visual / link-inferred.
    Consecutive frames were physically walked; a non-consecutive link needs a visual check; cross-video links need the
    photo-matched placement and stay labelled inferred. Optional clear(a_pos, b_pos) -> bool (no BIM wall between two
    same-floor stations <= clear_radius apart) adds 'link-bim-clear' edges (inferred from design walls, not from photos)."""
    edges = {s['id']: {} for s in stations}
    pos = {s['id']: np.asarray(s['position'], float) for s in stations}; lvl = {s['id']: s.get('level') for s in stations}
    for a, b in zip(stations, stations[1:]):
        d = pos[b['id']] - pos[a['id']]; dist = float(np.linalg.norm(d)); rise = abs(float(d[1]))
        stairish = rise > 0.5 or 'stairs' in (lvl[a['id']], lvl[b['id']]) or lvl[a['id']] != lvl[b['id']]
        kind = None
        if not stairish and dist <= max_step and rise <= max_rise:
            kind = 'route'
        elif stairish and dist <= stair_step and rise <= stair_rise:
            kind = 'stairs'
        if kind:
            edges[a['id']][b['id']] = kind; edges[b['id']][a['id']] = kind
    for v in visual_links:
        if not v.get('verified') or v['a'] not in pos or v['b'] not in pos:
            continue
        d = pos[v['b']] - pos[v['a']]
        if abs(d[1]) <= 0.5 and np.linalg.norm(d) <= max_step and v['b'] not in edges[v['a']]:
            edges[v['a']][v['b']] = 'route-visual'; edges[v['b']][v['a']] = 'route-visual'
    if clear is not None:
        for i, s in enumerate(stations):
            for t in stations[i + 2:]:
                if t['id'] in edges[s['id']] or lvl[s['id']] != lvl[t['id']] or lvl[s['id']] in (None, 'stairs'):
                    continue
                d = pos[t['id']] - pos[s['id']]
                if abs(d[1]) <= 0.5 and np.linalg.norm(d) <= clear_radius and clear(pos[s['id']], pos[t['id']]):
                    edges[s['id']][t['id']] = 'link-bim-clear'; edges[t['id']][s['id']] = 'link-bim-clear'
    for s in stations:
        near = []
        for a in a_stations:
            d = np.asarray(a['position'], float) - pos[s['id']]
            if abs(d[1]) <= link_rise and np.linalg.norm(d) <= link_radius:
                near.append((float(np.linalg.norm(d)), a['index']))
        for _, idx in sorted(near)[:2]:
            edges[s['id']]['A:%d' % idx] = 'link-inferred'
    return edges


# ---------------- register ----------------
def split_cloud(points, a_positions, b_positions, b_radius=8.0, a_clear=4.0):
    """Points of video B only: within b_radius of a B station and farther than a_clear from every A station.
    (The Cupix export does not label points by video; where the two misplaced videos overlap, points are dropped.)"""
    from scipy.spatial import cKDTree
    db, _ = cKDTree(b_positions).query(points); da, _ = cKDTree(a_positions).query(points)
    return points[(db < b_radius) & (da > a_clear)]


def register(a):
    import registration_fit as rf, registration_diagnostics as rd
    from global_registration_search import read_e57_points, e57_to_viewer, voxel, bounded_icp, nn_bounded
    from scipy.spatial import cKDTree
    link = json.loads(Path(a.link).read_text()); placed = json.loads(Path(a.placed_registration).read_text())
    manifest = json.loads((Path(a.ground) / 'panoramas/manifest.json').read_text()); by_id = {s['id']: s for s in manifest['stations']}
    A, B = link['stationsA'], link['stationsB']
    qa = np.array([by_id[i]['position'] for i in A]); qb = np.array([by_id[i]['position'] for i in B])
    image_only = compose(link['bToPlacedViewer'], placed)
    cloud = voxel(np.concatenate([e57_to_viewer(read_e57_points(p)) for p in a.e57]), 0.05)
    cloud_b = split_cloud(cloud, qa, qb)
    tris = rd.load_soup(a.bim_soup)
    lo, hi = SLAB['L2'] - 0.9, SLAB['L3'] + 5.2
    y = tris[:, :, 1]; band = tris[(y.max(1) >= lo) & (y.min(1) <= hi)]
    bim = rf._voxel(rf._sample_surface(band, 15), .12); bim = bim[(bim[:, 1] >= lo) & (bim[:, 1] <= hi)]
    scan = rf._voxel(cloud_b, .14); sb = apply(image_only, scan); scan = scan[(sb[:, 1] >= lo) & (sb[:, 1] <= hi)]
    train, held = scan[0::3], scan[1::3]; tree = cKDTree(bim)
    before = nn_bounded(image_only, held, bim, tree=tree)
    icp = bounded_icp(train, bim, image_only, iterations=60)
    after = nn_bounded(icp, held, bim, tree=tree)
    shift = np.linalg.norm(apply(icp, qb) - apply(image_only, qb), axis=1)
    per_floor = {}
    for k, (l, h) in {'L2': (SLAB['L2'], SLAB['L3']), 'L3': (SLAB['L3'], hi)}.items():
        hb = held[(apply(icp, held)[:, 1] >= l) & (apply(icp, held)[:, 1] < h)]
        per_floor[k] = nn_bounded(icp, hb, bim, tree=tree)
    # Cupix-as-exported placement (what the viewer would show with the borrowed May transform), for "before" figures
    as_exported = placed
    htris = horizontal_triangles(tris)
    cloud_floor = {}
    tb = cKDTree(cloud_b[:, [0, 2]])
    stations = []
    for i in B:
        p = np.asarray(by_id[i]['position'], float); P = apply(icp, p)[0]
        f = floor_below(htris, P); lvl = classify_level(f)
        idx = tb.query_ball_point([p[0], p[2]], 0.8); ys = cloud_b[idx, 1]; ys = ys[ys < p[1] - 0.3]
        cf = None
        if len(ys) > 20:
            hgt, edges = np.histogram(ys, bins=np.arange(p[1] - 4, p[1], 0.05)); cf = float(edges[hgt.argmax()] + 0.025 + icp['translation'][1])
        stations.append({'id': i, 'name': link['names'][i], 'positionBIM': P.tolist(), 'bimFloorBelow': f, 'level': lvl,
                         'cameraAboveBimFloor': None if f is None else float(P[1] - f), 'cloudFloorBIM': cf,
                         'positionAsExportedBIM': apply(as_exported, p)[0].tolist()})
    a_rows = [{'id': i, 'positionBIM': apply(placed, by_id[i]['position'])[0].tolist()} for i in A]
    created = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    cand = {'schema': 'grimes-registration-candidate/1', 'createdAt': created, 'status': 'candidate-not-surveyed', 'label': LABEL,
            'appliesTo': {'package': str(Path(a.ground)), 'video': link['videoB'], 'stations': B,
                          'note': 'Only the second video of the Oct 18 "Ground Level" export (Level 3, atrium stairs, partial Level 2). '
                                  'The Level 1 video of that export keeps the provisional project-frame (borrowed May) registration.'},
            'rotationYDegrees': icp['rotationYDegrees'], 'translation': icp['translation'], 'scale': 1,
            'convert': 'position=[c*x+s*z+t0, y+t1, -s*x+c*z+t2], a=rotationYDegrees (registration_fit convention)',
            'frames': {'source': 'Cupix frame of the Oct 18 Ground Level export, Y-up metres (E57 [x,z,-y]; manifest positions)', 'target': 'BIM viewer world, Y-up metres'},
            'chain': {'imageOnly': image_only, 'videoBToPlacedFrame': link['bToPlacedViewer'], 'placedRegistration': {k: placed[k] for k in ('rotationYDegrees', 'translation', 'status')},
                      'placedRegistrationFile': str(Path(a.placed_registration))},
            'method': {'link': link['method'], 'linkPairs': [[p['placed'], p['b'], p['inliers']] for p in link['pairs']],
                       'linkYawSpreadDegrees': link['yawSpreadDegrees'], 'anchors': link['anchors'], 'independentRayChecks': link['checks'],
                       'icp': 'yaw+XYZ trimmed ICP (scripts/global_registration_search.bounded_icp, 60 iterations) of video-B E57 points '
                              '(within 8 m of a B station and > 4 m from every A station) against BIM arch+struct surfaces y %.1f..%.1f; every 3rd point trains, held-out every 3rd+1' % (lo, hi),
                       'icpChangeFromImageOnly': {'translationMetres': float(math.dist(icp['translation'], image_only['translation'])), 'yawDegrees': icp['rotationYDegrees'] - image_only['rotationYDegrees'],
                                                  'stationShiftMedianMetres': float(np.median(shift)), 'stationShiftMaxMetres': float(shift.max())}},
            'metrics': {'heldOutImageOnly': before, 'heldOutAfterIcp': after, 'heldOutAfterIcpPerFloor': per_floor,
                        'internalConsistency': {k: v['summary'] for k, v in link['consistency'].items()}},
            'stations': stations,
            'honesty': 'Internal consistency only: photo matching ties video B to the Level 1 photos, whose own placement is the provisional '
                       'borrowed May transform; ICP residuals are distances to BIM design surfaces. Not surveyed accuracy.'}
    out = Path(a.candidate)
    if out.exists():
        raise SystemExit(f'{out} exists; candidates are never overwritten')
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(cand, indent=1))
    print('candidate', out, '\nimage-only', image_only, '\nicp', icp, '\nheld-out before', before, '\nafter', after)
    figures(Path(a.review), cand, a_rows, tris, cloud_b, icp)


def figures_only(a):
    """Redraw the review figures from an existing candidate into a NEW folder (no refit)."""
    import registration_diagnostics as rd
    from global_registration_search import read_e57_points, e57_to_viewer, voxel
    cand = json.loads(Path(a.candidate).read_text()); link = json.loads(Path(a.link).read_text()); placed = json.loads(Path(a.placed_registration).read_text())
    by_id = {s['id']: s for s in json.loads((Path(a.ground) / 'panoramas/manifest.json').read_text())['stations']}
    qa = np.array([by_id[i]['position'] for i in link['stationsA']]); qb = np.array([by_id[i]['position'] for i in link['stationsB']])
    cloud_b = split_cloud(voxel(np.concatenate([e57_to_viewer(read_e57_points(p)) for p in a.e57]), 0.05), qa, qb)
    a_rows = [{'id': i, 'positionBIM': apply(placed, by_id[i]['position'])[0].tolist()} for i in link['stationsA']]
    figures(Path(a.review), cand, a_rows, rd.load_soup(a.bim_soup), cloud_b, {k: cand[k] for k in ('rotationYDegrees', 'translation')})


def figures(review, cand, a_rows, tris, cloud_b, icp):
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    if review.exists():
        raise SystemExit(f'{review} exists; review folders are never overwritten')
    review.mkdir(parents=True)

    def cut(h):
        ys = tris[:, :, 1]; sel = tris[(ys.min(1) < h) & (ys.max(1) > h)]
        segs = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            pa, pb = sel[:, i], sel[:, j]; da, db = pa[:, 1] - h, pb[:, 1] - h; m = da * db < 0
            f = (da[m] / (da[m] - db[m]))[:, None]; segs.append((np.nonzero(m)[0], (pa[m] + (pb[m] - pa[m]) * f)[:, [0, 2]]))
        d = {}
        for idx, pts in segs:
            for k, p in zip(idx, pts): d.setdefault(k, []).append(p)
        return [v[:2] for v in d.values() if len(v) >= 2]
    st = cand['stations']; A = np.array([r['positionBIM'] for r in a_rows])
    new = np.array([s['positionBIM'] for s in st]); old = np.array([s['positionAsExportedBIM'] for s in st])
    lv = [s['level'] for s in st]
    colors = {'L3': '#c0392b', 'L2': '#1b6ca8', 'L1': '#2e9e6b', 'stairs': '#d9822b', None: '#7f8c8d'}
    floors = [('L1', SLAB['L1'] + 1.2), ('L2', SLAB['L2'] + 1.2), ('L3', SLAB['L3'] + 1.2)]
    cuts = {k: cut(h) for k, h in floors}
    for tag, P in (('before', old), ('after', new)):
        fig, ax = plt.subplots(1, 3, figsize=(27, 10))
        for k, (name, h) in enumerate(floors):
            g = ax[k]; g.add_collection(LineCollection(cuts[name], colors='k', linewidths=.35))
            g.scatter(A[:, 0], A[:, 2], s=8, c='#95a5a6', label='Level 1 video (provisional May transform)')
            for l in colors:
                m = np.array([x == l and (tag == 'before' or l in (name, 'stairs')) for x in lv])
                if m.any(): g.scatter(P[m, 0], P[m, 2], s=34, marker='^', c=colors[l], edgecolors='k', linewidths=.4, label='upper video: %s' % (LEVEL_NAMES.get(l, 'no BIM floor') if tag == 'after' else l or 'no BIM floor'))
            for k2 in range(len(P) - 1):
                if np.linalg.norm(P[k2 + 1] - P[k2]) < 9 and (tag == 'before' or {lv[k2], lv[k2 + 1]} & {name}):
                    g.plot(P[k2:k2 + 2, 0], P[k2:k2 + 2, 2], '-', lw=.6, c='#555')
            g.set_title('%s · BIM section y=%.1f' % (LEVEL_NAMES[name], h)); g.set_aspect('equal'); g.invert_yaxis(); g.autoscale(); g.grid(alpha=.2)
        ax[0].legend(loc='lower left', fontsize=8)
        fig.suptitle(('BEFORE: upper-floor video as exported by Cupix (placed with the borrowed May transform)' if tag == 'before' else
                      'AFTER: upper-floor video placed by photo matching to Level 1 + ICP to BIM') + ' · provisional, not surveyed', fontsize=13)
        fig.tight_layout(); fig.savefig(review / ('plan-%s.png' % tag), dpi=70); plt.close(fig)
    fig, ax = plt.subplots(1, 2, figsize=(20, 7))
    for g, P, tag in ((ax[0], old, 'before (as exported)'), (ax[1], new, 'after (photo-matched + ICP)')):
        for k, v in SLAB.items():
            g.axhline(v, c='k', lw=.8, ls='--'); g.text(0.01, v + .1, '%s slab %.1f' % (k, v), fontsize=8, transform=g.get_yaxis_transform())
        g.scatter(A[:, 2], A[:, 1], s=8, c='#95a5a6', label='Level 1 video cameras')
        for l in colors:
            m = np.array([x == l for x in lv])
            if m.any(): g.scatter(P[m, 2], P[m, 1], s=34, marker='^', c=colors[l], edgecolors='k', linewidths=.4, label=LEVEL_NAMES.get(l, str(l)))
        for k2 in range(len(P) - 1):
            if np.linalg.norm(P[k2 + 1] - P[k2]) < 9: g.plot(P[k2:k2 + 2, 2], P[k2:k2 + 2, 1], '-', lw=.6, c='#555')
        g.set_xlabel('BIM z (m)'); g.set_title('Elevation · ' + tag); g.grid(alpha=.2)
    ax[0].set_ylabel('BIM height y (m), camera centres'); ax[1].legend(fontsize=8)
    fig.suptitle('Camera heights vs BIM slabs · provisional, not surveyed'); fig.tight_layout(); fig.savefig(review / 'elevation-before-after.png', dpi=70); plt.close(fig)
    # held-out residual map of the upper-video cloud after ICP
    from scipy.spatial import cKDTree
    import registration_fit as rf
    pts = apply(icp, cloud_b[::4]); keep = (pts[:, 1] > SLAB['L2'] - .9)
    pts = pts[keep]
    fig, ax = plt.subplots(1, 2, figsize=(20, 10))
    for g, (name, l, h) in zip(ax, (('L2', SLAB['L2'], SLAB['L3']), ('L3', SLAB['L3'], 30))):
        m = (pts[:, 1] >= l + .8) & (pts[:, 1] < min(h, l + 2.4)); g.add_collection(LineCollection(cuts[name], colors='k', linewidths=.35))
        g.scatter(pts[m, 0], pts[m, 2], s=.3, c='#c0392b'); g.set_title('%s · upper-video points %.1f-%.1f m above slab over BIM section' % (LEVEL_NAMES[name], .8, 2.4))
        g.set_aspect('equal'); g.invert_yaxis(); g.autoscale()
    fig.tight_layout(); fig.savefig(review / 'cloud-over-bim-after.png', dpi=70); plt.close(fig)
    (review / 'README.txt').write_text('Upper-floor (second video) placement review, %s. Figures: plan-before.png, plan-after.png, elevation-before-after.png, '
                                       'cloud-over-bim-after.png. Candidate: ../../registration-candidate-upper-walk-2026-10-20.json. Provisional, not surveyed.\n' % cand['createdAt'])


# ---------------- package ----------------
def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''): h.update(block)
    return h.hexdigest()


def package(a):
    from PIL import Image
    cand = json.loads(Path(a.candidate).read_text()); base = Path(a.base); out = Path(a.out)
    if out.exists():
        raise SystemExit(f'{out} exists; packages are never overwritten')
    placed = json.loads((base / 'registration.json').read_text()); l1 = json.loads((base / 'panoramas/manifest.json').read_text())
    ground = json.loads((Path(a.ground) / 'panoramas/manifest.json').read_text()); by_id = {s['id']: s for s in ground['stations']}
    blurred = Path(a.blurred); privacy = json.loads((blurred / 'privacy-report.json').read_text())
    to_l1 = compose({k: cand[k] for k in ('rotationYDegrees', 'translation')}, invert(placed))  # video B -> Level 1 scan frame
    stage = out.with_name('.' + out.name + '.partial')
    if stage.exists(): shutil.rmtree(stage)
    photos = stage / 'panoramas'; (photos / 'mobile').mkdir(parents=True)
    stations = []
    rel_base = os.path.relpath(base / 'panoramas', photos); rel_mobile = os.path.relpath(base / 'panoramas/mobile', photos / 'mobile')
    for s in l1['stations']:
        os.symlink(os.path.join(rel_base, s['file']), photos / s['file']); os.symlink(os.path.join(rel_mobile, s['file']), photos / 'mobile' / s['file'])
        stations.append({**s, 'level': 'L1', 'video': 'A'})
    a_rows = [{'index': i, 'position': apply(placed, s['position'])[0], 'level': 'L1'} for i, s in enumerate(l1['stations'])]
    b_rows = [{'id': r['id'], 'position': r['positionBIM'], 'level': r['level'] or 'stairs'} for r in cand['stations']]
    link = json.loads(Path(a.link).read_text()) if a.link else {}
    import registration_diagnostics as rd
    edges = build_route(b_rows, link.get('visualLinks', ()), a_rows, clear=bim_clear_test(rd.load_soup(a.bim_soup)))
    first = len(stations); index = {r['id']: first + k for k, r in enumerate(b_rows)}
    for k, r in enumerate(cand['stations']):
        g = by_id[r['id']]; src = blurred / g['file']
        if not src.is_file():
            raise SystemExit(f'missing blurred image {src}')
        name = 'u%03d.jpg' % k; shutil.copyfile(src, photos / name)
        with Image.open(src) as im:
            im.convert('RGB').resize((2048, 1024), Image.Resampling.LANCZOS).save(photos / 'mobile' / name, quality=88)
        pos = apply(to_l1, g['position'])[0]
        stations.append({'id': r['id'], 'file': name, 'sourceName': r['name'], 'position': [float(v) for v in pos],
                         'e57Quaternion': rotate_e57_quaternion(g['e57Quaternion'], to_l1['rotationYDegrees']),
                         'sha256': sha256(photos / name), 'originalSha256': g['sha256'], 'dimensions': g['dimensions'],
                         'level': r['level'] or 'stairs', 'video': 'B', 'neighbors': []})
    kinds = {}
    def add(i, j, kind):
        for x, y in ((i, j), (j, i)):
            if y not in stations[x]['neighbors']: stations[x]['neighbors'].append(y)
            kinds.setdefault(x, {})[y] = kind
    for sid, nb in edges.items():
        for key, kind in nb.items():
            j = int(key[2:]) if isinstance(key, str) and key.startswith('A:') else index[key]
            add(index[sid], j, kind)
    for i, s in enumerate(stations):
        if i in kinds:
            s['edgeKinds'] = {str(j): k for j, k in sorted(kinds[i].items())}
            stairs = sorted(j for j, k in kinds[i].items() if k == 'stairs')
            if stairs: s['stairs'] = stairs
        s['neighbors'] = sorted(s['neighbors'])
    counts = {}
    for s in stations: counts[s['level']] = counts.get(s['level'], 0) + 1
    manifest = {'schema': 'grimes-captured-panoramas/1', 'building': 'Grimes', 'captureDate': '2026-10-18', 'level': 'L1-L3',
                'exportedStations': len(stations), 'defaultStation': l1['defaultStation'], 'status': 'local-preview', 'alignment': LABEL,
                'frame': l1['frame'] + ' Upper-floor stations transformed into this Level 1 scan frame (see upperWalk); the Oct 18 '
                         'provisional registration then maps every station to BIM.',
                'projection': l1.get('projection'), 'privacy': 'Level 1: as the Oct 18 package. Upper floors: same automatic blur '
                         '(scripts/raw360_pipeline.py privacy, report in the blurred folder); manual review required before any publishing.',
                'navigation': 'Level 1 edges as the Oct 18 package. Upper video: consecutive frames (walked) <= 7.7 m and rise <= 1.5 m = route; '
                              'consecutive frames across floors = stairs; non-consecutive same-floor links only when the two panoramas verify each other '
                              '(route-visual); same-floor stations <= 4 m apart with no BIM wall between them are link-bim-clear (inferred from design walls); upper-to-Level 1 links are link-inferred (placement by photo matching). Interpolation is a visual blend.',
                'navigationLimits': {'maxStep': 7.7, 'maxRise': 1.5, 'stairStep': 9.0, 'stairRise': 4.6},
                'levels': counts, 'routeGaps': l1.get('routeGaps', []),
                'upperWalk': {'status': cand['status'], 'label': LABEL, 'candidate': str(Path(a.candidate)), 'videoBToLevel1ScanFrame': to_l1,
                              'heldOutMedianMetres': cand['metrics']['heldOutAfterIcp']['medianMetres'],
                              'privacyReport': str(blurred / 'privacy-report.json'), 'privacyFlaggedImages': privacy.get('flaggedImages', []),
                              'coverage': 'Level 3 partly, Level 2 partial (occupied study areas not captured), atrium stairs; Level 1 -> Level 3 stairs were not '
                                          'captured (video 2 starts on Level 3), so the walk up goes through the atrium stair Level 1 <-> Level 2 <-> Level 3.'},
                'stations': stations}
    (photos / 'manifest.json').write_text(json.dumps(manifest, indent=1))
    (stage / 'README.txt').write_text('Local multi-floor preview of the Oct 18 capture (not for publishing). Serve the repository and open '
                                      'scan-compare.html?capture=2026-10-18&floors=all. Provisional, not surveyed.\n')
    stage.rename(out)
    print('wrote', out, counts, 'edges', sum(len(s['neighbors']) for s in stations) // 2)


# ---------------- upper-floor training package (Gaussian; prepared, not trained here) ----------------
def upper(a):
    """Video-B-only package for Gaussian training: original (unblurred, local) panoramas symlinked from the Ground intake,
    positions/headings in the Level 1 scan frame (same as the multi-floor photo package), the Oct 18 provisional
    registration copied unchanged. No seed mesh: the Ground scan.glb mixes both videos at overlapping coordinates."""
    cand = json.loads(Path(a.candidate).read_text()); base = Path(a.base); out = Path(a.out)
    if out.exists():
        raise SystemExit(f'{out} exists; packages are never overwritten')
    placed = json.loads((base / 'registration.json').read_text())
    ground = json.loads((Path(a.ground) / 'panoramas/manifest.json').read_text()); by_id = {s['id']: s for s in ground['stations']}
    to_l1 = compose({k: cand[k] for k in ('rotationYDegrees', 'translation')}, invert(placed))
    stage = out.with_name('.' + out.name + '.partial')
    if stage.exists(): shutil.rmtree(stage)
    (stage / 'panoramas').mkdir(parents=True)
    rel = os.path.relpath(Path(a.ground) / 'panoramas', stage / 'panoramas'); stations = []
    for r in cand['stations']:
        g = by_id[r['id']]; os.symlink(os.path.join(rel, g['file']), stage / 'panoramas' / g['file'])
        stations.append({'id': r['id'], 'file': g['file'], 'sourceName': r['name'], 'position': [float(v) for v in apply(to_l1, g['position'])[0]],
                         'e57Quaternion': rotate_e57_quaternion(g['e57Quaternion'], to_l1['rotationYDegrees']), 'dimensions': g['dimensions'],
                         'sha256': g['sha256'], 'level': r['level'] or 'stairs', 'neighbors': []})
    m = {'schema': 'grimes-captured-panoramas/1', 'building': 'grimes', 'level': 'L2-L3', 'captureDate': '2026-10-18', 'exportedStations': len(stations),
         'defaultStation': stations[0]['id'], 'status': 'local-training-input', 'alignment': LABEL,
         'frame': 'Level 1 scan frame of the Oct 18 capture (upper video moved by ' + str(Path(a.candidate)) + '); Y-up metres',
         'privacy': 'Original Cupix panoramas (local only, NOT blurred): never publish this package or a model trained from it without review.',
         'stations': stations}
    (stage / 'panoramas/manifest.json').write_text(json.dumps(m, indent=1))
    reg = dict(placed); reg['basis'] = placed.get('basis', '') + ' Upper-floor stations were moved into this Level 1 frame by the photo-matched candidate ' + str(Path(a.candidate)) + ' (provisional, not surveyed).'
    (stage / 'registration.json').write_text(json.dumps(reg, indent=2))
    (stage / 'README.txt').write_text('Upper-floor (Level 3 + atrium stairs + partial Level 2) Oct 18 video only, for Gaussian training. Local, unblurred, '
                                      'provisional, not surveyed. Built by scripts/multifloor_review.py upper.\n')
    stage.rename(out); print('wrote', out, len(stations), 'stations')


# ---------------- per-floor packages (local viewing; 2026-10-27) ----------------
FLOOR_TOLERANCE = 0.45


def package_floor(level, floor_y, tolerance=FLOOR_TOLERANCE):
    """Package floor of a video-B station. L2/L3 stations keep their level. A stair station (or one with no level) goes with
    the floor at the TOP of its flight: the lowest slab above its BIM floor height (+ tolerance), i.e. the floor one walks
    down from. Level 1 has its own package, so a stair foot on Level 1 (floor between L1 and L2) goes with Level 2.
    Returns None when nothing fits (no floor height, or above Level 3)."""
    if level in ('L2', 'L3'):
        return level
    if floor_y is None:
        return None
    for k in ('L2', 'L3'):
        if SLAB[k] > floor_y + tolerance:
            return k
    return 'L3' if abs(floor_y - SLAB['L3']) <= tolerance else None


def subset_edges(edges, keep):
    """Restrict build_route output to stations in `keep` (cross-floor and Level 1 links dropped)."""
    return {a: {b: k for b, k in nb.items() if b in keep} for a, nb in edges.items() if a in keep}


def components(ids, edges):
    seen, out = set(), []
    for i in ids:
        if i in seen:
            continue
        comp, q = [], [i]; seen.add(i)
        while q:
            x = q.pop(); comp.append(x)
            for y in edges.get(x, {}):
                if y not in seen: seen.add(y); q.append(y)
        out.append(comp)
    return sorted(out, key=len, reverse=True)


def default_station(rows, edges):
    """Medoid (horizontal) of the largest walk-connected group, so the floor opens on its best-connected part; stair
    stations only when the group has nothing else."""
    comp = components([r['id'] for r in rows], edges)[0]; lvl = {r['id']: r.get('level') for r in rows}
    comp = [i for i in comp if lvl[i] != 'stairs'] or comp; pos = {r['id']: np.asarray(r['position'], float)[[0, 2]] for r in rows}
    return min(comp, key=lambda i: (sum(float(np.linalg.norm(pos[i] - pos[j])) for j in comp), i))


def _cupix_rows(a, placed, to_l1):
    """Video-B rows from the Cupix Ground export + upper-walk candidate (32 panoramas)."""
    cand = json.loads(Path(a.candidate).read_text())
    ground = json.loads((Path(a.ground) / 'panoramas/manifest.json').read_text()); by_id = {s['id']: s for s in ground['stations']}
    blurred = Path(a.blurred).resolve(); rows = []
    for k, r in enumerate(cand['stations']):
        g = by_id[r['id']]
        rows.append({'id': r['id'], 'name': r['name'], 'file': g['file'], 'src': blurred / g['file'], 'frame': source_frame(r['name']), 'order': k,
                     'position': [float(v) for v in apply(to_l1, g['position'])[0]], 'positionBIM': [float(v) for v in r['positionBIM']],
                     'e57Quaternion': rotate_e57_quaternion(g['e57Quaternion'], to_l1['rotationYDegrees']), 'dimensions': g['dimensions'],
                     'originalSha256': g['sha256'], 'level': r['level'] or 'stairs', 'bimFloorBelow': r.get('bimFloorBelow'),
                     'cameraAboveBimFloor': r.get('cameraAboveBimFloor')})
    return rows, {'kind': 'cupix-ground-export', 'panoramas': len(rows), 'ground': str(Path(a.ground))}


def _raw_rows(a, placed, htris):
    """Rows from a raw INSV SfM placement (place-raw output): Level 1 scan frame poses, BIM floor ray cast per station."""
    import raw360_core as core
    P = json.loads(Path(a.raw_placed).read_text()); blurred = Path(a.blurred).resolve(); rows = []
    for k, st in enumerate(P['stations']):
        e = st['positionE57']; pos = [float(e[0]), float(e[2]), float(-e[1])]          # E57 [x,y,z] -> Y-up [x,z,-y]
        bim = apply(placed, pos)[0]; fy = floor_below(htris, bim)
        src = blurred / st['pano']
        if not src.is_file():
            raise SystemExit(f'missing blurred image {src}')
        with open(src, 'rb') as fh:
            from PIL import Image
            w, h = Image.open(fh).size
        rows.append({'id': '%s_f%06d' % (a.raw_tag, st['frame']), 'name': '%s frame %d' % (a.raw_tag, st['frame']), 'file': st['pano'], 'src': src,
                     'frame': st['frame'], 'order': k, 'position': pos, 'positionBIM': [float(v) for v in bim],
                     'e57Quaternion': [float(v) for v in core.quat_from_matrix(st['worldFromPanoE57'])], 'dimensions': [w, h],
                     'originalSha256': None, 'level': classify_level(fy) or 'stairs', 'bimFloorBelow': fy,
                     'cameraAboveBimFloor': None if fy is None else float(bim[1] - fy), 'sfmModel': st['model']})
    return rows, {'kind': 'raw-insv-local-sfm', 'placement': str(Path(a.raw_placed)), 'panoramas': len(rows), 'models': P['models'],
                  'unplacedKeyframes': P['unplacedKeyframes'], 'work': P['work']}


def floors(a):
    """Clean per-floor packages (Level 2, Level 3) from the upper-floor video only, for viewing each floor separately in
    the local viewer. Sources: the 32 Cupix panoramas (--candidate/--ground), or a denser raw INSV SfM placement
    (--raw-placed, from place-raw). Displayed panoramas are privacy-blurred copies (symlinked; 2048 px mobile copies
    written). Positions/headings are in the Level 1 scan frame, so the Oct 18 provisional registration maps them to BIM;
    registration.json says so and carries the upper-walk candidate status."""
    from PIL import Image
    import registration_diagnostics as rd
    cand_path = Path(a.candidate); cand = json.loads(cand_path.read_text()); base = Path(a.base); root = Path(a.out_root)
    outs = {k: root / (a.prefix % k) for k in ('L2', 'L3')}
    for o in outs.values():
        if o.exists():
            raise SystemExit(f'{o} exists; packages are never overwritten')
    placed = json.loads((base / 'registration.json').read_text())
    blurred = Path(a.blurred).resolve(); privacy = json.loads((blurred / 'privacy-report.json').read_text())
    to_l1 = compose({k: cand[k] for k in ('rotationYDegrees', 'translation')}, invert(placed))
    tris = rd.load_soup(a.bim_soup) if a.bim_soup else None
    if a.raw_placed:
        rows, source = _raw_rows(a, placed, horizontal_triangles(tris)); visual = ()
    else:
        rows, source = _cupix_rows(a, placed, to_l1); visual = json.loads(Path(a.link).read_text()).get('visualLinks', ()) if a.link else ()
    b_rows = [{'id': r['id'], 'position': r['positionBIM'], 'level': r['level']} for r in rows]
    edges = build_route(b_rows, visual, (), clear=bim_clear_test(tris) if tris is not None else None)
    assign = {r['id']: package_floor(r['level'], r['bimFloorBelow']) for r in rows}
    summary = {}
    if a.upper_out:  # all upper-floor stations in one training package (Gaussian), blurred panoramas, no route
        up = Path(a.upper_out)
        if up.exists():
            raise SystemExit(f'{up} exists; packages are never overwritten')
        stage = up.with_name('.' + up.name + '.partial')
        if stage.exists(): shutil.rmtree(stage)
        (stage / 'panoramas').mkdir(parents=True); rel = os.path.relpath(blurred, (stage / 'panoramas').resolve())
        tst = []
        for r in rows:
            os.symlink(os.path.join(rel, r['file']), stage / 'panoramas' / r['file'])
            tst.append({'id': r['id'], 'file': r['file'], 'sourceName': r['name'], 'sourceFrame': r['frame'], 'position': r['position'],
                        'e57Quaternion': r['e57Quaternion'], 'dimensions': r['dimensions'], 'sha256': sha256(r['src']),
                        'level': r['level'], 'packageFloor': assign[r['id']], 'neighbors': []})
        mid = default_station([{'id': r['id'], 'position': r['positionBIM'], 'level': r['level']} for r in rows], {r['id']: {} for r in rows})
        (stage / 'panoramas/manifest.json').write_text(json.dumps({'schema': 'grimes-captured-panoramas/1', 'building': 'grimes', 'level': 'L2-L3',
            'captureDate': '2026-10-18', 'exportedStations': len(tst), 'defaultStation': mid, 'status': 'local-training-input', 'alignment': LABEL,
            'frame': 'Level 1 scan frame of the Oct 18 capture, Y-up metres (as the per-floor packages)', 'source': source,
            'privacy': 'Privacy-blurred panoramas (' + str(blurred) + '); manual review still required; never publish this package or a model trained from it without review.',
            'stations': tst}, indent=1))
        reg = dict(placed); reg['basis'] = placed.get('basis', '') + ' Upper-floor stations were moved into this Level 1 frame (' + source['kind'] + '; provisional, not surveyed).'
        (stage / 'registration.json').write_text(json.dumps(reg, indent=2))
        (stage / 'README.txt').write_text('Upper-floor Oct 18 stations (Level 2 + Level 3 + stairs) for Gaussian training; blurred panoramas; local; provisional, not surveyed. '
                                          'Built by scripts/multifloor_review.py floors --upper-out.\n')
        stage.rename(up); print('wrote', up, len(tst), 'stations, centre', mid)
    for floor, out in outs.items():
        sel = [r for r in rows if assign[r['id']] == floor]
        keep = {r['id'] for r in sel}; fe = subset_edges(edges, keep)
        excluded = [{'id': r['id'], 'frame': r['frame'], 'packageFloor': assign[r['id']], 'level': r['level']} for r in rows if r['id'] not in keep]
        stage = out.with_name('.' + out.name + '.partial')
        if stage.exists(): shutil.rmtree(stage)
        photos = stage / 'panoramas'; (photos / 'mobile').mkdir(parents=True)
        rel = os.path.relpath(blurred, photos.resolve())
        idx = {r['id']: k for k, r in enumerate(sel)}; stations = []
        for r in sel:
            os.symlink(os.path.join(rel, r['file']), photos / r['file'])
            with Image.open(r['src']) as im:
                im.convert('RGB').resize((2048, 1024), Image.Resampling.LANCZOS).save(photos / 'mobile' / r['file'], quality=88)
            st = {'id': r['id'], 'file': r['file'], 'sourceName': r['name'], 'video': 'B', 'sourceFrame': r['frame'], 'frameOrder': r['order'],
                  'position': r['position'], 'positionBIM': r['positionBIM'], 'e57Quaternion': r['e57Quaternion'],
                  'sha256': sha256(r['src']), 'originalSha256': r['originalSha256'], 'dimensions': r['dimensions'],
                  'level': r['level'], 'packageFloor': floor, 'bimFloorBelow': r['bimFloorBelow'],
                  'cameraAboveBimFloor': r['cameraAboveBimFloor'], 'neighbors': sorted(idx[j] for j in fe[r['id']])}
            if 'sfmModel' in r: st['sfmModel'] = r['sfmModel']
            if fe[r['id']]:
                st['edgeKinds'] = {str(idx[j]): k for j, k in sorted(fe[r['id']].items(), key=lambda kv: idx[kv[0]])}
                stairs = sorted(idx[j] for j, k in fe[r['id']].items() if k == 'stairs')
                if stairs: st['stairs'] = stairs
            stations.append(st)
        order = {r['id']: r['order'] for r in sel}; comps = components([r['id'] for r in sel], fe)
        counts = {}
        for st in stations: counts[st['level']] = counts.get(st['level'], 0) + 1
        name = LEVEL_NAMES[floor]; this_floor = cand['metrics'].get('heldOutAfterIcpPerFloor', {}).get(floor)
        manifest = {'schema': 'grimes-captured-panoramas/1', 'building': 'grimes', 'level': floor, 'captureDate': '2026-10-18',
                    'exportedStations': len(stations), 'defaultStation': default_station([{'id': r['id'], 'position': r['positionBIM'], 'level': r['level']} for r in sel], fe),
                    'status': 'local-preview', 'alignment': LABEL,
                    'frame': 'Level 1 scan frame of the Oct 18 capture, Y-up metres (upper-floor video placed via the upper-walk candidate'
                             + (' and, for raw INSV frames, a per-submodel fit to the Cupix video-B stations by frame number' if a.raw_placed else '') +
                             '); the Oct 18 provisional registration then maps every station to BIM (positionBIM).',
                    'projection': 'equirectangular',
                    'privacy': 'Displayed panoramas are the automatic blur output (scripts/raw360_pipeline.py privacy, ' + str(blurred / 'privacy-report.json') +
                               '); detection is not complete, manual review required. Local only, never publish.',
                    'navigation': 'Upper-video edges restricted to this floor: consecutive placed frames <= 7.7 m and rise <= 1.5 m = route; across a slab = stairs; '
                                  + ('non-consecutive same-floor links only when the panoramas verify each other (route-visual) or ' if not a.raw_placed else 'non-consecutive same-floor links only when ')
                                  + 'no BIM wall lies between stations <= 4 m apart (link-bim-clear, inferred from design walls). No links to other floors or to Level 1.',
                    'navigationLimits': {'maxStep': 7.7, 'maxRise': 1.5, 'stairStep': 9.0, 'stairRise': 4.6},
                    'levels': counts, 'walkGroups': [sorted(c, key=lambda i: order[i]) for c in comps],
                    'floorAssignment': {'rule': 'Level from the highest near-horizontal BIM surface under the station (L2/L3 within ' + str(FLOOR_TOLERANCE) + ' m of the slab, '
                                        'else stairs). Stair stations go with the floor at the top of their flight: lowest slab above that BIM floor. '
                                        'Slabs (viewer frame, m): ' + json.dumps({k: SLAB[k] for k in ('L1', 'L2', 'L3')}) + '.',
                                        'excludedStations': excluded},
                    'source': {**source, 'video': 'VID_20261018_153400', 'candidate': str(cand_path), 'candidateStatus': cand['status'],
                               'videoBToLevel1ScanFrame': to_l1, 'heldOutAfterIcp': cand['metrics']['heldOutAfterIcp'], 'heldOutAfterIcpThisFloor': this_floor,
                               'privacyFlaggedImages': privacy.get('flaggedImages', [])},
                    'coverage': 'partial: one upper-floor video (VID_20261018_153400). ' +
                                ('Level 2: occupied study areas not captured.' if floor == 'L2' else 'Level 3: only the walked corridors; see walkGroups for disconnected parts.'),
                    'stations': stations}
        (photos / 'manifest.json').write_text(json.dumps(manifest, indent=1))
        reg = {k: placed[k] for k in ('rotationYDegrees', 'translation', 'scale')}
        reg.update({'status': cand['status'], 'label': LABEL, 'captureDate': '2026-10-18', 'level': floor,
                    'frames': {'source': 'Level 1 scan frame of the Oct 18 capture (panoramas/manifest.json positions)', 'target': 'BIM viewer world, Y-up metres'},
                    'basis': 'Chain: upper video -> (upper-walk candidate ' + str(cand_path) + ', photo matching to Level 1 + yaw/XYZ ICP to BIM'
                             + ('; raw INSV SfM submodels fitted to its stations by frame number, ' + str(Path(a.raw_placed)) if a.raw_placed else '') + ') -> BIM; '
                             'stored here as the Oct 18 provisional Level 1 registration (status ' + str(placed.get('status')) + ', borrowed May transform) '
                             'applied to stations pre-moved into the Level 1 scan frame. Not surveyed.',
                    'metrics': {'heldOutAfterIcp': cand['metrics']['heldOutAfterIcp'], 'heldOutAfterIcpThisFloor': this_floor,
                                **({'rawPlacementPerSubmodel': [{k: m.get(k) for k in ('model', 'frames', 'status', 'scale', 'fitResidualMetres', 'leaveOneOutMetres')} for m in source['models']]} if a.raw_placed else {})},
                    'honesty': cand.get('honesty')})
        (stage / 'registration.json').write_text(json.dumps(reg, indent=2))
        project = {'schema': 'capture-project/1', 'building': 'grimes', 'level': floor, 'captureDate': '2026-10-18', 'panoramas': 'panoramas/manifest.json',
                   'model': None, 'registration': 'registration.json', 'dataStatus': 'NO FEED', 'status': 'local-preview', 'routeReady': True,
                   'alignment': LABEL, 'coverage': 'partial',
                   'notes': [f'{name} from the upper-floor video only ({len(stations)} panoramas, source {source["kind"]}); provisional, not surveyed.',
                             'Supersedes grimes-%s-2026-10-18 for viewing (that package mixed Level 1 frames / used the wrong video split); the old one is left unchanged.' % floor,
                             'Blurred panoramas only; manual privacy review still required. Not for publishing.',
                             'Built by scripts/multifloor_review.py floors.']}
        (stage / 'project.json').write_text(json.dumps(project, indent=1))
        (stage / 'README.txt').write_text(f'Local {name} preview of the Oct 18 capture, upper-floor video only (provisional, not surveyed; not for publishing). '
                                          f'Serve the repository and open scan-compare.html?capture=2026-10-18&floors={floor}. Built by scripts/multifloor_review.py floors.\n')
        stage.rename(out)
        summary[floor] = {'out': str(out), 'stations': len(stations), 'levels': counts, 'walkGroups': [len(c) for c in comps], 'default': manifest['defaultStation']}
        print('wrote', out, counts, 'groups', [len(c) for c in comps], 'edges', sum(len(st['neighbors']) for st in stations) // 2, 'default', manifest['defaultStation'])
    return summary


# ---------------- raw INSV SfM submodels -> Level 1 scan frame (2026-10-27) ----------------
def source_frame(name):
    """Cupix image name 'VID_..._477(287).jpg' -> 287 (= 0-based video frame index of the raw INSV, checked by image
    correlation on 6 frames, 2026-10-27)."""
    return int(str(name).rsplit('(', 1)[1].split(')')[0])


def fit_levelled_similarity(src, dst, up):
    """dst ~ s * Rz(yaw) * L * src + t with L levelling `up` onto +Z (gravity from the panoramas themselves), so a
    near-collinear corridor cannot roll the model. src: SfM centres, dst: E57-axis (Z-up) reference. Returns
    (s, R (3x3, = Rz L), t)."""
    import raw360_core as core
    src = np.asarray(src, float); dst = np.asarray(dst, float); L = core.level_rotation(up); q = src @ L.T
    if len(src) < 2:
        raise ValueError('need >= 2 matches')
    a = q[:, :2] - q[:, :2].mean(0); b = dst[:, :2] - dst[:, :2].mean(0)
    za, zb = a[:, 0] + 1j * a[:, 1], b[:, 0] + 1j * b[:, 1]
    k = (np.conj(za) @ zb) / (np.conj(za) @ za)          # complex least squares: s * e^{i yaw}
    sc, yaw = float(abs(k)), float(np.angle(k)); c, sn = math.cos(yaw), math.sin(yaw)
    Rz = np.array([[c, -sn, 0], [sn, c, 0], [0, 0, 1.0]]); R = Rz @ L
    t = dst.mean(0) - sc * (R @ src.mean(0))
    return sc, R, t


def place_raw(a):
    """Place every SfM submodel of a raw360 run into the Level 1 scan frame by frame number: Cupix video-B stations
    (positions/headings of the multi-floor package, i.e. the upper-walk candidate) are the reference; exact keyframes
    plus poses interpolated <= max-gap frames. Levelled 4-DoF similarity per submodel, leave-one-out check; frames farther
    than --margin from the submodel's reference matches are dropped (2026-10-27: an unsupported tail came out 180 deg off). Writes
    placed.json; the panoramas themselves are not touched. Run with the raw360 venv (pycolmap)."""
    import pycolmap, raw360_core as core, raw360_sfm
    work = Path(a.work); meta = json.loads((work / 'frames.json').read_text())
    ref_m = json.loads(Path(a.reference).read_text())
    ref = {}
    for st in ref_m['stations']:
        if st.get('video') == 'B':
            ref[source_frame(st['sourceName'])] = {'id': st['id'], 'e57': np.array(core.yup_to_e57(st['position'])), 'R': core.matrix_from_quat(st['e57Quaternion'])}
    mdir = work / 'sfm' / a.method / 'models'; models = []
    for d in sorted(mdir.iterdir(), key=lambda x: int(x.name)):
        rec = pycolmap.Reconstruction(str(d)); fr = [f for f in raw360_sfm._frame_poses(rec, meta) if f['registered']]
        if len(fr) < a.min_model:
            continue
        frames = [f['frame'] for f in fr]; C = [np.array(f['centre']) for f in fr]; Rw = [np.array(f['worldFromPano']) for f in fr]
        m = []
        for q, r in sorted(ref.items()):
            hit = core.interpolate_track(frames, C, Rw, q, a.max_gap)
            if hit: m.append((q, hit[0], hit[2]))
        info = {'model': int(d.name), 'frames': len(fr), 'frameRange': [min(frames), max(frames)], 'matches': [[q, kind] for q, _, kind in m]}
        if len(m) < 3:
            info['status'] = 'unplaced: fewer than 3 reference frames'; models.append(info); continue
        up = core.up_from_panoramas(Rw); src = np.array([x[1] for x in m]); dst = np.array([ref[x[0]]['e57'] for x in m])
        s, R, t = fit_levelled_similarity(src, dst, up); res = np.linalg.norm((s * (R @ src.T)).T + t - dst, axis=1)
        loo = []
        for i in range(len(m)):
            keep = [j for j in range(len(m)) if j != i]
            if len(keep) >= 2:
                s1, R1, t1 = fit_levelled_similarity(src[keep], dst[keep], up); loo.append(float(np.linalg.norm(s1 * R1 @ src[i] + t1 - dst[i])))
        info.update(status='placed', scale=s, fitResidualMetres=core.error_summary(res), leaveOneOutMetres=core.error_summary(loo),
                    perMatch=[{'frame': q, 'id': ref[q]['id'], 'kind': kind, 'residual': float(e)} for (q, _, kind), e in zip(m, res)],
                    stations=[{'frame': f['frame'], 'pano': f['pano'], 'positionE57': (s * R @ np.array(f['centre']) + t).tolist(),
                               'worldFromPanoE57': (R @ np.array(f['worldFromPano'])).tolist()} for f in fr
                              if m[0][0] - a.margin <= f['frame'] <= m[-1][0] + a.margin])
        info['supportedFrameRange'] = [m[0][0] - a.margin, m[-1][0] + a.margin]
        info['droppedOutsideSupport'] = [f['frame'] for f in fr if not m[0][0] - a.margin <= f['frame'] <= m[-1][0] + a.margin]
        models.append(info)
    # one pose per frame: the larger model wins where submodels overlap
    chosen = {}
    for info in sorted([x for x in models if x['status'] == 'placed'], key=lambda x: -x['frames']):
        for st in info['stations']:
            chosen.setdefault(st['frame'], {**st, 'model': info['model']})
    out = {'schema': 'multifloor-raw-placement/1', 'label': LABEL, 'work': str(work), 'method': a.method, 'reference': str(Path(a.reference)),
           'referenceUse': 'placement (video-B Cupix stations, upper-walk candidate) by frame number; frame index = Cupix (N)',
           'fit': 'per submodel: levelled 4-DoF similarity (scale, yaw, translation; up from the panoramas), exact + interpolated (<= %d frames) matches' % a.max_gap,
           'models': [{k: v for k, v in x.items() if k != 'stations'} for x in models],
           'stations': [chosen[f] for f in sorted(chosen)], 'unplacedKeyframes': [k['frame'] for k in meta['keyframes'] if k['frame'] not in chosen]}
    Path(a.out).write_text(json.dumps(out, indent=1))
    for x in out['models']:
        print(x['model'], x['frames'], x['frameRange'], x['status'], 'n=%d' % len(x['matches']), 'scale %.3f' % x.get('scale', float('nan')),
              'fit med %.3f' % x.get('fitResidualMetres', {}).get('median', float('nan')), 'loo med %.3f' % x.get('leaveOneOutMetres', {}).get('median', float('nan')))
    print('placed', len(out['stations']), 'unplaced', len(out['unplacedKeyframes']))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('register')
    r.add_argument('--link', required=True); r.add_argument('--ground', required=True); r.add_argument('--e57', nargs='+', required=True)
    r.add_argument('--placed-registration', required=True); r.add_argument('--bim-soup', default=str(ROOT / 'work/floorplans/arch-struct.f32'))
    r.add_argument('--candidate', required=True); r.add_argument('--review', required=True)
    f = sub.add_parser('figures')
    for k in ('--link', '--ground', '--placed-registration', '--candidate', '--review'): f.add_argument(k, required=True)
    f.add_argument('--e57', nargs='+', required=True); f.add_argument('--bim-soup', default=str(ROOT / 'work/floorplans/arch-struct.f32'))
    p = sub.add_parser('package')
    p.add_argument('--candidate', required=True); p.add_argument('--ground', required=True); p.add_argument('--blurred', required=True)
    p.add_argument('--base', required=True); p.add_argument('--link'); p.add_argument('--out', required=True)
    p.add_argument('--bim-soup', default=str(ROOT / 'work/floorplans/arch-struct.f32'))
    u = sub.add_parser('upper')
    u.add_argument('--candidate', required=True); u.add_argument('--ground', required=True); u.add_argument('--base', required=True); u.add_argument('--out', required=True)
    fl = sub.add_parser('floors', help='per-floor Level 2 / Level 3 packages (video B only, blurred panoramas)')
    fl.add_argument('--candidate', required=True); fl.add_argument('--ground'); fl.add_argument('--blurred', required=True)
    fl.add_argument('--raw-placed', help='place-raw output: build from raw INSV SfM panoramas instead of the Cupix export'); fl.add_argument('--raw-tag', default='raw477')
    fl.add_argument('--upper-out', help='also write one all-upper-floor training package here (Gaussian input)')
    fl.add_argument('--base', required=True); fl.add_argument('--link'); fl.add_argument('--out-root', default=str(ROOT / 'capture-local'))
    fl.add_argument('--prefix', default='grimes-%s-2026-10-18-v2'); fl.add_argument('--bim-soup', default=str(ROOT / 'work/floorplans/arch-struct.f32'))
    pr = sub.add_parser('place-raw', help='place raw360 SfM submodels in the Level 1 scan frame by frame number (raw360 venv)')
    pr.add_argument('--work', required=True); pr.add_argument('--method', default='colmap-incremental'); pr.add_argument('--out', required=True)
    pr.add_argument('--reference', default=str(ROOT / 'capture-local/grimes-oct18-floors/panoramas/manifest.json'))
    pr.add_argument('--max-gap', type=int, default=10); pr.add_argument('--min-model', type=int, default=5)
    pr.add_argument('--margin', type=int, default=15, help='keep submodel frames only within this many frames of its first/last reference match (no unsupported extrapolation)')
    a = ap.parse_args()
    {'register': register, 'figures': figures_only, 'package': package, 'upper': upper, 'floors': floors, 'place-raw': place_raw}[a.cmd](a)


if __name__ == '__main__':
    main()
