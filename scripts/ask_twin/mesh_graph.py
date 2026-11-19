"""Mesh-contact connection graph for the Ask-the-twin connected_run tool (offline builder, read-only over the GLBs).

The element sidecars of the fabrication layers carry no connector or system-membership records, so connectivity is
inferred from the shapes. The Draco GLBs are decoded in memory by decode_layer_mesh.mjs (nothing is re-encoded or
written back; the decoded dump goes to an ignored work cache) and two elements of a layer are linked when their meshes
actually meet at an end face:

    ring distance(A, B) = max(d3(A->B), d3(B->A)) <= ring_m
    d3(A->B) = third-smallest distance from a distinct vertex of A to the triangle surface of B

i.e. at least three distinct vertices of each part lie within ring_m of the other part's surface. Fabrication parts
are modelled with vertices only at their ends (a straight duct or pipe is a tube between two end rings), so two runs
that cross or pass close by mid-span share no vertices and are not linked, while an end ring that sits on the next
part's end ring is. Thresholds per layer are chosen from the measured distribution of ring distances (see
LAYER_CRITERIA and docs in the output file).

Excluded from the graph (never links, as in tools.NOT_RUN): hangers, supports, sleeves, annotation, clearance zones,
architectural/structural/electrical reference objects that sit in the same DWG layer, and "Fabrication Skin"
insulation wraps. A skin is mapped to the part it wraps (skin_host) so a pick on the insulation follows its duct.

Output: work/ask-twin/mesh-graph.json (derived, inferred from geometry, not surveyed; no connector data exists).

    python3 scripts/ask_twin/mesh_graph.py --layers duct hydronic plumbing fire
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import time
from collections import defaultdict, deque
from datetime import date
from pathlib import Path

try:
    import numpy as np
except ImportError:   # the server only needs load_graph (plain JSON); the builder needs numpy
    np = None

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ask_twin import index as ix   # noqa: E402
else:
    from . import index as ix

ROOT = ix.ROOT
SCHEMA = 'ask-twin-mesh-graph/1'
GRAPH_PATH = ROOT / 'work' / 'ask-twin' / 'mesh-graph.json'
DUMP_DIR = ROOT / 'work' / 'ask-twin' / 'mesh-cache'
DECODER = Path(__file__).with_name('decode_layer_mesh.mjs')

# Same skip list as tools.NOT_RUN, plus reference objects drawn in the MEP DWGs (architectural/structural/electrical CAD
# layers) and insulation skins. Kept here so the builder does not import the tool module.
NOT_RUN = re.compile(r'hanger|support|clearance zone|anno|mounting|unistrut|brace|banger|nut$|sleeve|eV_Point|field weld', re.I)
REFERENCE_TYPE = re.compile(r'^(A|S|E)-')
SKIN = re.compile(r'fabrication skin', re.I)

# ring_m: end-face contact threshold. min_verts: distinct vertices required on each side.
LAYER_CRITERIA = {
    'duct': {'ring_m': 0.012, 'min_verts': 3, 'min_span_m': 0.02},
    'hydronic': {'ring_m': 0.012, 'min_verts': 3, 'min_span_m': 0.01},
    'plumbing': {'ring_m': 0.012, 'min_verts': 3, 'min_span_m': 0.01},
    'fire': {'ring_m': 0.012, 'min_verts': 3, 'min_span_m': 0.01},
}
PAIR_PAD = 0.03        # box pre-filter (the old box test's tolerance): only pairs within 3 cm are measured
SURFACE_PAD = 0.05     # vertices / triangles considered around the other part
SKIN_PAD = 0.06        # a skin's host lies inside the skin box grown by this much (insulation up to ~2")
NEAREST_RADIUS = 1.0   # nearest other-component part reported for isolated parts / outlets, metres


# ---------------- decoded mesh dump ----------------
def decode(glb: Path, sidecar: Path, out: Path, log=print) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(['node', str(DECODER), str(glb), str(sidecar), str(out)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'decode failed for {glb.name}: {r.stderr.strip()[-400:]}')
    log(r.stderr.strip())


def load_dump(path: Path):
    b = path.read_bytes()
    hl = struct.unpack('<I', b[:4])[0]
    h = json.loads(b[4:4 + hl])
    o = 4 + hl
    P = np.frombuffer(b, np.float32, h['nVerts'] * 3, o).reshape(-1, 3).astype(np.float64)
    T = np.frombuffer(b, np.uint32, h['nTris'] * 3, o + h['nVerts'] * 12).reshape(-1, 3).astype(np.int64)
    return h, P, T


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


# ---------------- geometry ----------------
def point_tri_dist(p, a, b, c):
    """Row-wise distance from points p to triangles (a, b, c); arrays (N, 3). Closest-point regions after Ericson,
    Real-Time Collision Detection 5.1.5. Degenerate triangles fall back to their vertices/edges."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    res = np.empty_like(p)
    done = np.zeros(len(p), bool)

    def put(mask, q):
        nonlocal done
        mask = mask & ~done
        res[mask] = q[mask]
        done |= mask

    with np.errstate(divide='ignore', invalid='ignore'):
        put((d1 <= 0) & (d2 <= 0), a)
        put((d3 >= 0) & (d4 <= d3), b)
        put((vc <= 0) & (d1 >= 0) & (d3 <= 0), a + (d1 / (d1 - d3))[:, None] * ab)
        put((d6 >= 0) & (d5 <= d6), c)
        put((vb <= 0) & (d2 >= 0) & (d6 <= 0), a + (d2 / (d2 - d6))[:, None] * ac)
        e = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        put((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), b + e[:, None] * (c - b))
        den = 1.0 / (va + vb + vc)
        put(np.ones(len(p), bool), a + ab * (vb * den)[:, None] + ac * (vc * den)[:, None])
        d = np.linalg.norm(p - res, axis=1)
    d[~np.isfinite(d)] = np.inf
    return d


def points_to_tris(pts, abc, chunk=1_500_000):
    a, b, c = abc
    n, m = len(pts), len(a)
    out = np.full(n, np.inf)
    if not n or not m:
        return out
    step = max(1, chunk // m)
    for s in range(0, n, step):
        p = pts[s:s + step]
        k = len(p)
        pi, ti = np.repeat(np.arange(k), m), np.tile(np.arange(m), k)
        out[s:s + k] = point_tri_dist(p[pi], a[ti], b[ti], c[ti]).reshape(k, m).min(1)
    return out


class LayerMesh:
    def __init__(self, dump: Path):
        self.h, self.P, self.T = load_dump(dump)
        self.ids = self.h['ids']
        self.vo, self.to = np.asarray(self.h['vOff']), np.asarray(self.h['tOff'])
        self.pos = {e: i for i, e in enumerate(self.ids)}
        n = len(self.ids)
        self.box = np.full((n, 6), np.nan)
        for i in range(n):
            if self.vo[i + 1] > self.vo[i]:
                v = self.P[self.vo[i]:self.vo[i + 1]]
                self.box[i] = np.r_[v.min(0), v.max(0)]

    def verts(self, i):
        return self.P[self.vo[i]:self.vo[i + 1]]

    def tris_near(self, j, lo, hi):
        t = self.T[self.to[j]:self.to[j + 1]] + self.vo[j]
        A, B, C = self.P[t[:, 0]], self.P[t[:, 1]], self.P[t[:, 2]]
        m = np.all(np.minimum(np.minimum(A, B), C) <= hi, 1) & np.all(np.maximum(np.maximum(A, B), C) >= lo, 1)
        return A[m], B[m], C[m]

    def side(self, i, j, pad=SURFACE_PAD, with_points=False):
        """Sorted distances from the distinct vertices of i (near j) to j's surface (and those vertices, same order)."""
        lo, hi = self.box[j, :3] - pad, self.box[j, 3:] + pad
        v = self.verts(i)
        v = v[np.all((v >= lo) & (v <= hi), 1)]
        none = (np.array([np.inf]), np.full((1, 3), np.nan)) if with_points else np.array([np.inf])
        if not len(v):
            return none
        v = np.unique(np.round(v, 4), axis=0)   # 0.1 mm: duplicated seam vertices count once
        tr = self.tris_near(j, v.min(0) - pad, v.max(0) + pad)
        if not len(tr[0]):
            return none
        d = points_to_tris(v, tr)
        o = np.argsort(d)
        return (d[o], v[o]) if with_points else d[o]

    def gap(self, i, j):
        a, b = self.box[i], self.box[j]
        return float(np.linalg.norm(np.maximum(0, np.maximum(a[:3] - b[3:], b[:3] - a[3:]))))


def patch_span(pts) -> float:
    """Extent of a contact patch along its second principal axis, metres (0 for collinear or fewer than 3 points)."""
    if len(pts) < 3:
        return 0.0
    c = pts - pts.mean(0)
    _, _, vt = np.linalg.svd(c, full_matrices=False)
    t = c @ vt[1]
    return float(t.max() - t.min())


def contact(M, i, j, ring_m, min_verts, min_span):
    """End-face contact of i on j: at least min_verts distinct vertices of i lie within ring_m of j's triangle surface
    and span a patch (not a line along an edge) at least min_span wide. Returns (ok, kth distance, count, span)."""
    d, v = M.side(i, j, with_points=True)
    near = d <= ring_m
    n = int(near.sum())
    kth = float(d[min_verts - 1]) if len(d) >= min_verts else float('inf')
    span = patch_span(v[near]) if n >= min_verts else 0.0
    return n >= min_verts and span >= min_span, kth, n, span


def box_pairs(box, members, pad, cell=1.0):
    """Index pairs (i < j) among members whose boxes are within pad."""
    grid, big = defaultdict(list), []
    for i in members:
        lo = np.floor((box[i, :3] - pad) / cell).astype(int)
        hi = np.floor((box[i, 3:] + pad) / cell).astype(int)
        if np.prod(hi - lo + 1) > 4000:
            big.append(i)
            continue
        for x in range(lo[0], hi[0] + 1):
            for y in range(lo[1], hi[1] + 1):
                for z in range(lo[2], hi[2] + 1):
                    grid[(x, y, z)].append(i)
    pairs = set()
    for lst in grid.values():
        for a in range(len(lst)):
            for b in range(a + 1, len(lst)):
                i, j = lst[a], lst[b]
                pairs.add((i, j) if i < j else (j, i))
    for i in big:
        for j in members:
            if j != i:
                pairs.add((i, j) if i < j else (j, i))
    if not pairs:
        return np.zeros((0, 2), int)
    pairs = np.array(sorted(pairs))
    a, b = box[pairs[:, 0]], box[pairs[:, 1]]
    g = np.linalg.norm(np.maximum(0, np.maximum(a[:, :3] - b[:, 3:], b[:, :3] - a[:, 3:])), axis=1)
    return pairs[g <= pad]


def classify(meta: dict) -> str:
    """'run' | 'skin' | 'excluded' for one sidecar record."""
    text = f"{meta.get('name', '')} {meta.get('type', '')}"
    if SKIN.search(text):
        return 'skin'
    if NOT_RUN.search(text) or REFERENCE_TYPE.match(str(meta.get('type') or '')):
        return 'excluded'
    return 'run'


def components(nodes, adj):
    comp, sizes = {}, []
    for s in nodes:
        if s in comp:
            continue
        k = len(sizes)
        comp[s] = k
        q, n = deque([s]), 0
        while q:
            a = q.popleft()
            n += 1
            for b in adj.get(a, ()):
                if b not in comp:
                    comp[b] = k
                    q.append(b)
        sizes.append(n)
    return comp, sizes


# ---------------- builder ----------------
def build_layer(key: str, root: Path = ROOT, dump_dir: Path = DUMP_DIR, log=print, keep_stats: bool = False) -> dict:
    glb_rel, side_rel = ix.BUILDING_LAYERS[key]
    crit = LAYER_CRITERIA[key]
    glb, side = root / glb_rel, root / side_rel
    t0 = time.time()
    digest = sha256(glb)
    dump = dump_dir / f'{key}.bin'
    decode(glb, side, dump, log)
    if sha256(glb) != digest:
        raise RuntimeError(f'{glb_rel} changed while decoding')   # read-only check: the canonical bytes are untouched
    meta = json.loads(side.read_text())['elements']
    M = LayerMesh(dump)
    hidden = set()
    try:
        q = json.loads((root / 'buildings/grimes/element-quality.json').read_text())['layers'].get(key, {})
        hidden = {e for ids in q.get('hidden', {}).values() for e in ids}
    except (OSError, ValueError, KeyError):
        pass
    kind = {e: ('excluded' if e in hidden else classify(meta.get(e, {}))) for e in M.ids}
    with_tris = {e for i, e in enumerate(M.ids) if M.to[i + 1] > M.to[i]}
    run_idx = [i for i, e in enumerate(M.ids) if kind[e] == 'run' and not np.isnan(M.box[i, 0])]
    pairs = box_pairs(M.box, run_idx, PAIR_PAD)
    log(f'[mesh-graph] {key}: {len(run_idx)} run parts, {len(pairs)} box-candidate pairs (gap <= {PAIR_PAD} m)')
    edges, stats = [], []
    t1 = time.time()
    args = crit['ring_m'], crit['min_verts'], crit['min_span_m']
    for n, (i, j) in enumerate(pairs):
        oki, ki, ni, si = contact(M, i, j, *args)
        okj, kj, nj, sj = contact(M, j, i, *args)
        if keep_stats:
            stats.append((M.ids[i], M.ids[j], ki, kj, ni, nj, si, sj))
        if oki or okj:
            # mode: 'ring' = both parts meet end to end; 'tap' = one part's end sits on the other's surface (a tap or
            # branch on a main, or a part ending against another)
            edges.append((M.ids[i], M.ids[j], 'ring' if oki and okj else 'tap'))
        if n and n % 20000 == 0:
            log(f'[mesh-graph] {key}: {n}/{len(pairs)} pairs, {time.time() - t1:.0f} s')
    # insulation skins -> the run part they wrap (largest run box inside the skin box grown by SKIN_PAD)
    skin_host = {}
    run_set = set(run_idx)
    for e, kd in kind.items():
        if kd != 'skin':
            continue
        i = M.pos[e]
        if np.isnan(M.box[i, 0]):
            continue
        lo, hi = M.box[i, :3] - SKIN_PAD, M.box[i, 3:] + SKIN_PAD
        inside = np.where(np.all(M.box[:, :3] >= lo, 1) & np.all(M.box[:, 3:] <= hi, 1))[0]
        best, bestv = None, 0.0
        sv = np.prod(np.maximum(M.box[i, 3:] - M.box[i, :3], 1e-3))
        for j in inside:
            if j not in run_set:
                continue
            v = np.prod(np.maximum(M.box[j, 3:] - M.box[j, :3], 1e-3))
            if v > bestv:
                best, bestv = j, v
        if best is not None and bestv >= 0.03 * sv:   # pipe insulation can be ~6x the pipe volume; a stray bolt is not a host
            skin_host[e] = M.ids[best]
    adj = defaultdict(set)
    for a, b, _ in edges:
        adj[a].add(b)
        adj[b].add(a)
    run_ids = [M.ids[i] for i in run_idx]
    comp, sizes = components(run_ids, adj)
    isolated = [e for e in run_ids if not adj.get(e)]
    # nearest part of another component, for isolated parts and air outlets ("does it meet a duct?")
    nearest = {}
    outlet = re.compile(r'diffuser|grille|register|\bgrd\b|cdff', re.I)
    probe = [e for e in run_ids if not adj.get(e) or outlet.search(f"{meta.get(e, {}).get('name', '')} {meta.get(e, {}).get('type', '')}")]
    cand = box_pairs(M.box, run_idx, NEAREST_RADIUS)
    by = defaultdict(list)
    for i, j in cand:
        by[i].append(j)
        by[j].append(i)
    for e in probe:
        i = M.pos[e]
        best = None
        for j in by.get(i, ()):
            if comp[M.ids[j]] == comp[e]:
                continue
            g = M.gap(i, j)
            if best is not None and g >= best[0]:
                continue
            di = M.side(i, j, pad=NEAREST_RADIUS)
            dj = M.side(j, i, pad=NEAREST_RADIUS)
            d = float(min(di[0], dj[0]))
            if np.isfinite(d) and (best is None or d < best[0]):
                best = (d, M.ids[j])
        if best is not None:
            nearest[e] = [best[1], round(best[0], 3)]
    secs = time.time() - t0
    out = {
        'glb': glb_rel, 'sidecar': side_rel, 'glb_sha256': digest, 'glb_bytes': glb.stat().st_size,
        'criterion': {**crit, 'pair_prefilter_box_gap_m': PAIR_PAD, 'skin_host_pad_m': SKIN_PAD, 'nearest_radius_m': NEAREST_RADIUS},
        'counts': {'decoded_elements': len(M.ids), 'with_triangles': len(with_tris), 'run_parts': len(run_ids),
                   'skins': sum(1 for v in kind.values() if v == 'skin'), 'skins_mapped_to_host': len(skin_host),
                   'excluded': sum(1 for v in kind.values() if v == 'excluded'), 'box_candidate_pairs': int(len(pairs)),
                   'edges': len(edges), 'components': len(sizes), 'isolated_parts': len(isolated),
                   'largest_component': max(sizes) if sizes else 0, 'build_seconds': round(secs, 1)},
        'edges': [[a, b] for a, b, _ in edges],
        'edge_mode': ''.join('r' if m == 'ring' else 't' for _, _, m in edges),
        'skin_host': skin_host,
        'nearest_other_component': nearest,
        'excluded_ids': sorted(e for e, v in kind.items() if v == 'excluded'),
    }
    if keep_stats:
        out['_pair_stats'] = stats
    log(f"[mesh-graph] {key}: {len(edges)} edges, {len(sizes)} components, {len(isolated)} isolated, {secs:.0f} s")
    return out


def provenance(layers: dict) -> dict:
    return {
        'schema': SCHEMA,
        'date': date.today().isoformat(),
        'evidence': 'INFERRED from mesh geometry (decoded Draco GLB triangles), not surveyed and not a design connector record: '
                    'the fabrication sidecars carry no connector or system-membership data.',
        'criterion': 'Two parts of the same layer are linked when at least min_verts distinct vertices of one part lie within '
                     'ring_m of the other part\'s triangle surface and those vertices span a patch at least min_span_m wide '
                     '(an end ring or a tap base, not a line along an edge). edge_mode r = both parts meet end to end, '
                     't = one part\'s end sits on the other\'s surface (tap or branch on a main). Fabrication parts have '
                     'vertices only at their ends, so runs that cross or pass close by mid-span are not linked. Pairs are '
                     'pre-filtered by the old 3 cm bounding-box test. Hangers/supports/annotation/reference objects and '
                     'insulation skins never link; a skin maps to the part it wraps (skin_host). Flow direction is not inferred.',
        'threshold_basis': 'duct layer, 2026-11-19: ring distance of named fabrication part pairs peaks at 0 mm (1,178 pairs) and '
                           'at 9-10 mm (852 pairs, a 3/8 in joint gap the fabrication model leaves at rectangular connectors and '
                           'diffuser necks), with only 47 pairs between 11 and 23 mm; ring_m = 12 mm keeps both joint modes.',
        'builder': 'scripts/ask_twin/mesh_graph.py (+ decode_layer_mesh.mjs, read-only Draco decode; GLBs never re-encoded)',
        'layers': layers,
    }


def load_graph(path: Path = GRAPH_PATH, root: Path = ROOT, log=print) -> dict:
    """{layer: {'adj': {id: set}, 'skin_host', 'nearest', 'excluded', 'counts', 'component', 'component_size'}} for the
    layers whose GLB still has the recorded size; {} when the file is missing or unreadable."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    if data.get('schema') != SCHEMA:
        return {}
    out = {}
    for key, L in (data.get('layers') or {}).items():
        try:
            if (root / L['glb']).stat().st_size != L['glb_bytes']:
                log(f'[ask-twin] mesh graph for {key} is stale (GLB size changed); using the box test')
                continue
        except (OSError, KeyError):
            continue
        adj = defaultdict(set)
        for a, b in L['edges']:
            adj[a].add(b)
            adj[b].add(a)
        comp, sizes = components(list(adj), adj)
        out[key] = {'adj': adj, 'skin_host': L.get('skin_host', {}), 'nearest': L.get('nearest_other_component', {}),
                    'excluded': set(L.get('excluded_ids', ())), 'counts': L.get('counts', {}), 'criterion': L.get('criterion', {}),
                    'component': comp, 'component_size': sizes, 'date': data.get('date')}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the mesh-contact connection graph (work/ask-twin/mesh-graph.json).')
    ap.add_argument('--layers', nargs='+', default=['duct'], choices=sorted(LAYER_CRITERIA))
    ap.add_argument('--out', type=Path, default=GRAPH_PATH)
    ap.add_argument('--stats', type=Path, help='also write per-pair contact stats (JSON lines) here, for threshold review')
    a = ap.parse_args(argv)
    layers = {}
    if a.out.exists():
        try:
            prev = json.loads(a.out.read_text())
            if prev.get('schema') == SCHEMA:
                layers = prev.get('layers', {})
        except ValueError:
            pass
    for key in a.layers:
        L = build_layer(key, keep_stats=bool(a.stats))
        st = L.pop('_pair_stats', None)
        if a.stats and st:
            a.stats.parent.mkdir(parents=True, exist_ok=True)
            with open(a.stats.with_name(f'{a.stats.stem}-{key}{a.stats.suffix}'), 'w') as fh:
                for row in st:
                    fh.write(json.dumps(row) + '\n')
        layers[key] = L
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.out.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(provenance(layers), separators=(',', ':')))
    tmp.replace(a.out)
    print('wrote', a.out, {k: v['counts'] for k, v in layers.items()})


if __name__ == '__main__':
    main()
