"""Propose Gaussian training zones for a capture from its panorama manifest.

    python3 scripts/plan_gaussian_zones.py --capture 2026-09-17 [--zones 4] [--overlap 3] [--seed 1]

Stations form a walk graph (manifest route neighbours plus stations within a short walking distance, so
loops where the route crosses itself connect). Zones are grown over that graph from k-means seeds, always
extending the smallest zone, so every zone is connected and zone sizes stay similar. Each zone's training
set is its core plus every station within --overlap metres of the core, so seams overlap.

Writes scripts/gaussian_zones.json (owner/status/name of an existing zone are never overwritten; an existing
capture is only re-planned with --replace) and a top-down map PNG for review and slides. Planning is
deterministic for a given manifest, zone count and seed. Requires numpy and matplotlib (map only).
"""
import argparse
import json
import math
import string
import textwrap
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import gaussian_zones as gz  # noqa: E402

LINK_DISTANCE = 5.5   # metres: same walk-link rule as the panorama manifest
LINK_HEIGHT = 1.5
MEDIA_DIR = Path('/Users/yschung/Graduate-Project-media/review/zones')
DOCS_IMAGE_DIR = ROOT / 'docs' / 'images'
PALETTE = ['#1b6ca8', '#d9822b', '#2e9e6b', '#a24bb0', '#c9453d', '#7d7d2a']


# ---------------------------------------------------------------- planning (pure)

def build_graph(stations, link_distance=LINK_DISTANCE, link_height=LINK_HEIGHT):
    """Adjacency list (list of sorted index lists) over station indices, always connected.

    Edges: manifest `neighbors` (route), any pair within link_distance horizontally and link_height vertically,
    and, only if components remain, the shortest bridge between components (so zoning never fails on route gaps).
    """
    n = len(stations)
    pos = np.array([s['position'] for s in stations], dtype=float)
    index = {s['id']: i for i, s in enumerate(stations)}
    adj = [set() for _ in range(n)]
    for i, s in enumerate(stations):
        for j in s.get('neighbors', []):
            j = index[j] if isinstance(j, str) else j
            if 0 <= j < n and j != i:
                adj[i].add(j)
                adj[j].add(i)
    for i in range(n):
        d = np.hypot(pos[:, 0] - pos[i, 0], pos[:, 2] - pos[i, 2])
        close = np.flatnonzero((d <= link_distance) & (np.abs(pos[:, 1] - pos[i, 1]) <= link_height))
        for j in close:
            if j != i:
                adj[i].add(int(j))
                adj[int(j)].add(i)
    while True:
        comps = components(adj)
        if len(comps) == 1:
            break
        best = None
        base = comps[0]
        rest = [i for c in comps[1:] for i in c]
        for i in base:
            d = np.linalg.norm(pos[rest] - pos[i], axis=1)
            k = int(np.argmin(d))
            if best is None or d[k] < best[0]:
                best = (float(d[k]), i, rest[k])
        adj[best[1]].add(best[2])
        adj[best[2]].add(best[1])
    return [sorted(a) for a in adj]


def components(adj):
    seen, out = set(), []
    for start in range(len(adj)):
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            v = stack.pop()
            comp.append(v)
            for w in adj[v]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        out.append(sorted(comp))
    return out


def is_connected(adj, members):
    members = set(members)
    if not members:
        return False
    start = next(iter(sorted(members)))
    seen, stack = {start}, [start]
    while stack:
        v = stack.pop()
        for w in adj[v]:
            if w in members and w not in seen:
                seen.add(w)
                stack.append(w)
    return seen == members


def kmeans_seeds(xz, k, rng, restarts=12, iterations=30):
    """Indices of k stations nearest the best k-means (k-means++ start) centroids on XZ."""
    best = None
    for _ in range(restarts):
        centers = [xz[int(rng.integers(len(xz)))]]
        while len(centers) < k:
            d2 = np.min([np.sum((xz - c) ** 2, axis=1) for c in centers], axis=0)
            if d2.sum() == 0:
                centers.append(xz[int(rng.integers(len(xz)))])
            else:
                centers.append(xz[int(rng.choice(len(xz), p=d2 / d2.sum()))])
        centers = np.array(centers)
        for _ in range(iterations):
            label = np.argmin(((xz[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
            moved = np.array([xz[label == c].mean(axis=0) if np.any(label == c) else centers[c] for c in range(k)])
            if np.allclose(moved, centers):
                break
            centers = moved
        label = np.argmin(((xz[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
        sse = float(((xz - centers[label]) ** 2).sum())
        if best is None or sse < best[0]:
            best = (sse, centers)
    seeds = []
    for c in best[1]:
        order = np.argsort(((xz - c) ** 2).sum(axis=1), kind='stable')
        seeds.append(int(next(i for i in order if int(i) not in seeds)))
    return seeds


def grow_zones(adj, xz, seeds):
    """Balanced multi-source region growing: the smallest zone with a free neighbour takes the free
    neighbour nearest its centroid. Zones are connected by construction."""
    n, k = len(adj), len(seeds)
    owner = [-1] * n
    members = [[s] for s in seeds]
    for z, s in enumerate(seeds):
        owner[s] = z
    left = n - k
    while left:
        for z in sorted(range(k), key=lambda z: (len(members[z]), z)):
            frontier = sorted({w for v in members[z] for w in adj[v] if owner[w] == -1})
            if frontier:
                centroid = xz[members[z]].mean(axis=0)
                pick = min(frontier, key=lambda w: (float(np.sum((xz[w] - centroid) ** 2)), w))
                owner[pick] = z
                members[z].append(pick)
                left -= 1
                break
        else:
            raise RuntimeError('Unassigned stations are unreachable from every zone')  # graph is connected: unreachable
    return [sorted(m) for m in members]


def best_growth(adj, xz, k, seed, trials=12):
    """Try several seeded k-means starts; keep the growth with the most even zone sizes, then the most compact."""
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(trials):
        cores = grow_zones(adj, xz, kmeans_seeds(xz, k, rng, restarts=2))
        sizes = [len(c) for c in cores]
        spread = float(sum(((xz[c] - xz[c].mean(axis=0)) ** 2).sum() for c in cores))
        key = (max(sizes) - min(sizes), spread)
        if best is None or key < best[0]:
            best = (key, cores)
    return best[1]


def add_overlap(pos, core, overlap):
    """Core plus every station within `overlap` metres (3D) of any core station; sorted indices."""
    n = len(pos)
    core_pos = pos[core]
    d = np.min(np.linalg.norm(pos[:, None, :] - core_pos[None], axis=2), axis=1)
    return sorted(set(core) | {int(i) for i in range(n) if d[i] <= overlap})


def plan_zones(stations, n_zones=4, overlap=3.0, seed=1):
    """[{'core': [idx], 'train': [idx]}] ordered west to east. Pure and deterministic for a seed."""
    if n_zones < 1 or n_zones * 4 > len(stations):
        raise ValueError(f'{n_zones} zones need at least {n_zones * 4} stations; the manifest has {len(stations)}')
    if overlap < 0:
        raise ValueError('overlap must be non-negative')
    pos = np.array([s['position'] for s in stations], dtype=float)
    xz = pos[:, [0, 2]]
    adj = build_graph(stations)
    if n_zones == 1:
        cores = [list(range(len(stations)))]
    else:
        cores = best_growth(adj, xz, n_zones, seed)
    cores.sort(key=lambda c: (round(float(xz[c, 0].mean()), 6), round(float(xz[c, 1].mean()), 6)))
    return [{'core': c, 'train': add_overlap(pos, c, overlap)} for c in cores]


# ---------------------------------------------------------------- zones file

def zone_letters(n):
    return list(string.ascii_uppercase[:n]) if n <= 26 else [str(i + 1) for i in range(n)]


def build_entry(stations, plan, building, floor, manifest_rel, overlap, existing=None, seed=1, names=None, name_basis=None):
    """capture entry for gaussian_zones.json; zone ids are <floor>-<letter>. Keeps name/owner/status of
    an existing zone with the same id."""
    old = {z['id']: z for z in (existing or {}).get('zones', [])}
    letters = zone_letters(len(plan))
    zones = []
    for letter, p in zip(letters, plan):
        zid = f'{floor.lower()}-{letter.lower()}'
        previous = old.get(zid, {})
        zones.append({
            'id': zid,
            'name': (names[len(zones)] if names and len(zones) < len(names) else None) or previous.get('name') or f'Zone {letter}',
            'stations': [stations[i]['id'] for i in p['train']],
            'core': [stations[i]['id'] for i in p['core']],
            'overlapMetres': overlap,
            'owner': previous.get('owner', ''),
            'status': previous.get('status', 'unassigned'),
        })
        basis = (name_basis if names and len(zones) <= len(names) else None) or previous.get('nameBasis')
        if basis:
            zones[-1]['nameBasis'] = basis
    entry = {'building': building, 'floor': floor, 'manifest': manifest_rel, 'plannedWith': {
        'method': 'k-means seeds + balanced region growing over the station walk graph', 'seed': seed},
        'zones': zones}
    return entry


def merge_into(doc, capture, entry, replace=False):
    """New document with `capture` set to `entry`; refuses to drop or silently replace claimed zones."""
    doc = json.loads(json.dumps(doc))
    current = doc['captures'].get(capture)
    if current is not None and not replace:
        raise gz.ZoneError(f'{capture} already has zones; use --replace to re-plan (name, owner and status are kept for same ids)')
    if current is not None:
        kept = {z['id'] for z in entry['zones']}
        dropped = [z['id'] for z in current['zones'] if z['id'] not in kept and (z['owner'] or z['status'] != 'unassigned')]
        if dropped:
            raise gz.ZoneError(f'Refusing to drop claimed zones {dropped}; keep the same zone count or clear their owner by PR first')
    doc['captures'][capture] = entry
    return doc


def warnings_for_replace(old_entry, new_entry):
    out = []
    old = {z['id']: z for z in old_entry['zones']}
    for z in new_entry['zones']:
        o = old.get(z['id'])
        if o and (o['owner'] or o['status'] != 'unassigned') and (set(o['core']) != set(z['core']) or set(o['stations']) != set(z['stations'])):
            out.append(f'zone {z["id"]} ({o["owner"] or "no owner"}, {o["status"]}) changed its stations; tell its owner')
    return out


# ---------------------------------------------------------------- map

def render_map(capture, entry, stations, path, max_bytes=300_000):
    """Top-down XZ map: stations by zone, route links, overlap bands/rings, labels, scale bar. Returns bytes written."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    by_id = {s['id']: s for s in stations}
    overlap = entry['zones'][0]['overlapMetres']
    fig, ax = plt.subplots(figsize=(8.0, 7.2), dpi=110)
    for s in stations:  # route and walk links, faint
        for j in s.get('neighbors', []):
            t = stations[j] if isinstance(j, int) else by_id[j]
            ax.plot([s['position'][0], t['position'][0]], [s['position'][2], t['position'][2]], color='#c9ced4', lw=.7, zorder=1)
    handles = []
    for z, color in zip(entry['zones'], PALETTE * 4):
        core = np.array([by_id[i]['position'] for i in z['core']])
        extra = np.array([by_id[i]['position'] for i in z['stations'] if i not in set(z['core'])]).reshape(-1, 3)
        for p in core:  # overlap reach of the core
            ax.add_patch(plt.Circle((p[0], p[2]), z['overlapMetres'], color=color, alpha=.07, lw=0, zorder=0))
        ax.scatter(core[:, 0], core[:, 2], s=26, color=color, zorder=3, edgecolors='white', linewidths=.4)
        if len(extra):  # stations added from neighbouring zones: hollow ring in this zone's colour
            ax.scatter(extra[:, 0], extra[:, 2], s=78, facecolors='none', edgecolors=color, linewidths=1.3, zorder=4)
        cx, cz = core[:, 0].mean(), core[:, 2].mean()
        ax.text(cx, cz, textwrap.fill(z['name'], 18), ha='center', va='center', fontsize=8.5, weight='bold', color='#111', zorder=6,
                bbox=dict(boxstyle='round,pad=.25', fc='white', ec=color, lw=1.2, alpha=.92))
        handles.append(Line2D([], [], marker='o', ls='', color=color,
                              label=f'{z["id"]}  {z["name"]}  ({len(z["core"])} core + {len(z["stations"]) - len(z["core"])} overlap)'))
    handles.append(Line2D([], [], marker='o', ls='', mfc='none', mec='#444', ms=9, label=f'ring = added by {overlap:g} m overlap'))
    pts = np.array([s['position'] for s in stations])
    ax.set_xlim(pts[:, 0].min() - 5, pts[:, 0].max() + 5)
    ax.set_ylim(pts[:, 2].max() + 7, pts[:, 2].min() - 5)  # z grows downward, top-down plan view
    ax.set_aspect('equal')
    x0, z0 = pts[:, 0].min() - 3, pts[:, 2].max() + 4.5
    ax.plot([x0, x0 + 10], [z0, z0], color='black', lw=3, zorder=7)
    ax.text(x0 + 5, z0 - .8, '10 m', ha='center', va='bottom', fontsize=8)
    ax.set_xlabel('x (m, scan frame)', fontsize=8)
    ax.set_ylabel('z (m, scan frame)', fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(color='#eef0f2', lw=.5)
    ax.set_title(f'{entry["building"].title()} {entry["floor"]} · {capture} · Gaussian training zones (top-down)', fontsize=10)
    ax.legend(handles=handles, fontsize=7, loc='upper center', bbox_to_anchor=(.5, -.12), ncol=2, frameon=False)
    fig.text(.01, .004, 'Proposed split of station positions; cores partition the capture, rings overlap seams. '
             'Names are provisional.', fontsize=6.5, color='#555')
    fig.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    plt.close(fig)
    if path.stat().st_size > max_bytes:  # quantise to a small palette PNG for slides/docs
        from PIL import Image
        img = Image.open(path).convert('RGB').quantize(colors=64)
        img.save(path, optimize=True)
    return path.stat().st_size


# ---------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--capture', required=True, help='capture date, e.g. 2026-09-17')
    p.add_argument('--manifest', type=Path, help='panorama manifest (default scan-assets/captures/<capture>/panoramas/manifest.json)')
    p.add_argument('--building', help='default: manifest "building" lowercased')
    p.add_argument('--floor', help='floor label L1, L2, L3, B1... (default: manifest "level")')
    p.add_argument('--zones', type=int, default=4, help='number of zones (default 4)')
    p.add_argument('--overlap', type=float, default=3.0, help='metres of overlap added around each core (default 3)')
    p.add_argument('--seed', type=int, default=1, help='planning seed (default 1; same seed = same zones)')
    p.add_argument('--names', help='semicolon-separated zone names in west-to-east order (default "Zone A", "Zone B"...)')
    p.add_argument('--name-basis', help='how the names were inferred, stored as nameBasis (keep names honest, e.g. "likely ...")')
    p.add_argument('--zones-file', type=Path, default=gz.ZONES_PATH)
    p.add_argument('--replace', action='store_true', help='re-plan a capture that already has zones (keeps name/owner/status per zone id)')
    p.add_argument('--dry-run', action='store_true', help='print the plan; write nothing')
    p.add_argument('--no-map', action='store_true', help='skip the PNG maps')
    p.add_argument('--media-dir', type=Path, default=MEDIA_DIR)
    p.add_argument('--docs-image-dir', type=Path, default=DOCS_IMAGE_DIR)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    manifest_path = (args.manifest or ROOT / 'scan-assets' / 'captures' / args.capture / 'panoramas' / 'manifest.json').resolve()
    try:
        manifest = json.loads(manifest_path.read_text())
        stations = manifest['stations']
        floor = args.floor or manifest.get('level')
        building = (args.building or manifest.get('building') or '').lower()
        if not building or not floor:
            raise gz.ZoneError('Need --building and --floor (the manifest has no "building"/"level")')
        if not gz.FLOOR.match(floor):
            raise gz.ZoneError(f'floor {floor!r} must look like L1, L2, L3 or B1')
        plan = plan_zones(stations, args.zones, args.overlap, args.seed)
        try:
            rel = str(manifest_path.relative_to(ROOT))
        except ValueError:
            rel = str(manifest_path)
        doc = json.loads(args.zones_file.read_text()) if args.zones_file.exists() else {'schema': gz.SCHEMA, 'captures': {}}
        existing = doc['captures'].get(args.capture)
        entry = build_entry(stations, plan, building, floor, rel, args.overlap, existing if args.replace else None, args.seed,
                            [n.strip() for n in args.names.split(';')] if args.names else None, args.name_basis)
        merged = merge_into(doc, args.capture, entry, args.replace)
        gz.validate_zones(merged, {args.capture: {s['id'] for s in stations}})
    except (gz.ZoneError, ValueError, OSError, KeyError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    for z in entry['zones']:
        print(f'{z["id"]}  {z["name"]:<30} core {len(z["core"]):>3}  train {len(z["stations"]):>3}')
    if existing and args.replace:
        for w in warnings_for_replace(existing, entry):
            print('warning:', w)
    if args.dry_run:
        print('dry run: nothing written')
        return 0
    args.zones_file.write_text(json.dumps(merged, indent=2) + '\n')
    print(f'Wrote {args.zones_file}')
    if not args.no_map:
        for target in (args.media_dir / f'{args.capture}-zones.png', args.docs_image_dir / f'zones-{args.capture}.png'):
            size = render_map(args.capture, entry, stations, target)
            print(f'Map {target} ({size / 1024:.0f} KB)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
