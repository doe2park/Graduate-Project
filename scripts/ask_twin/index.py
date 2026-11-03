"""Element spatial index for the Ask-the-twin demo (read-only, derived, cached).

Bounding boxes come from the glTF POSITION accessor min/max that every Draco primitive carries in the GLB JSON
chunk, transformed by the node hierarchy and then by the viewer placement used in grimes-bim-viewer.html
(rotY(pi) + EQUIP_OFFSET). No geometry is decoded, nothing is re-encoded, no GLB is written.

Identity follows the viewer (buildElementRenderTier): a mesh node belongs to the nearest ancestor (or itself) whose
node name is a key of the layer sidecar. Boxes are axis-aligned boxes of transformed accessor boxes, so they are
slightly conservative for rotated parts. Coordinates are metres in the viewer frame, +Y up.
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_SCHEMA = 'ask-twin-index/1'
# grimes-bim-viewer.html: sourceGroup.rotation.y = Math.PI; sourceGroup.position = EQUIP_OFFSET
VIEWER_OFFSET = (-35.28, -97.16, 28.60)

# key -> (glb, sidecar, displayed in grimes-bim-viewer.html)
BUILDING_LAYERS = {
    'equipment': ('buildings/grimes/grimes-equipment.glb', 'buildings/grimes/elements.json'),
    'fixtures': ('buildings/grimes/grimes-fixtures.glb', 'buildings/grimes/fixtures.elements.json'),
    'lighting': ('buildings/grimes/grimes-lighting.glb', 'buildings/grimes/lighting.elements.json'),
    'lifesafety': ('buildings/grimes/grimes-lifesafety.glb', 'buildings/grimes/lifesafety.elements.json'),
    'structural': ('buildings/grimes/grimes-structural.glb', 'buildings/grimes/structural.elements.json'),
    'conduit': ('buildings/grimes/grimes-conduit.glb', 'buildings/grimes/conduit.elements.json'),
    'duct': ('buildings/grimes/grimes-duct.glb', 'buildings/grimes/duct.elements.json'),
    'hydronic': ('buildings/grimes/grimes-hydronic.glb', 'buildings/grimes/hydronic.elements.json'),
    'plumbing': ('buildings/grimes/grimes-plumbing.glb', 'buildings/grimes/plumbing.elements.json'),
    'fire': ('buildings/grimes/grimes-fire.glb', 'buildings/grimes/fire.elements.json'),
}
# Interior ceilings (Level 1-3 slices, same frame per interior/manifest.json). Indexed for "what is above this
# ceiling" lookups; the element viewer does not draw them.
INTERIOR_LAYERS = {f'ceilings-l{n}': (f'interior/ceilings-l{n}.glb', f'interior/ceilings-l{n}.elements.json') for n in (1, 2, 3)}
VIEWER_LAYERS = set(BUILDING_LAYERS)


def read_glb_json(path: Path) -> dict:
    with open(path, 'rb') as fh:
        magic, _version, _length = struct.unpack('<4sII', fh.read(12))
        if magic != b'glTF':
            raise ValueError(f'{path}: not a GLB')
        chunk_len, chunk_type = struct.unpack('<II', fh.read(8))
        if chunk_type != 0x4E4F534A:
            raise ValueError(f'{path}: first chunk is not JSON')
        return json.loads(fh.read(chunk_len))


def _mat_mul(a, b):
    # column-major 4x4 (glTF convention), returns a*b
    return [sum(a[r + 4 * k] * b[k + 4 * c] for k in range(4)) for c in range(4) for r in range(4)]


def _trs(node) -> list:
    if 'matrix' in node:
        return list(node['matrix'])
    tx, ty, tz = node.get('translation', (0, 0, 0))
    qx, qy, qz, qw = node.get('rotation', (0, 0, 0, 1))
    sx, sy, sz = node.get('scale', (1, 1, 1))
    xx, yy, zz, xy, xz, yz, wx, wy, wz = qx * qx, qy * qy, qz * qz, qx * qy, qx * qz, qy * qz, qw * qx, qw * qy, qw * qz
    return [(1 - 2 * (yy + zz)) * sx, 2 * (xy + wz) * sx, 2 * (xz - wy) * sx, 0,
            2 * (xy - wz) * sy, (1 - 2 * (xx + zz)) * sy, 2 * (yz + wx) * sy, 0,
            2 * (xz + wy) * sz, 2 * (yz - wx) * sz, (1 - 2 * (xx + yy)) * sz, 0,
            tx, ty, tz, 1]


def _apply(m, p):
    x, y, z = p
    return (m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13], m[2] * x + m[6] * y + m[10] * z + m[14])


def to_viewer(p):
    """GLB scene coordinates -> viewer frame (rotY(pi) then translate)."""
    return (-p[0] + VIEWER_OFFSET[0], p[1] + VIEWER_OFFSET[1], -p[2] + VIEWER_OFFSET[2])


def element_boxes(gltf: dict, ids: set) -> dict:
    """{element id: [minx,miny,minz,maxx,maxy,maxz]} in the viewer frame."""
    nodes, meshes, accessors = gltf.get('nodes', []), gltf.get('meshes', []), gltf.get('accessors', [])
    out: dict = {}
    identity = 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1
    stack = [(i, list(identity), None) for i in gltf['scenes'][gltf.get('scene', 0)]['nodes']]
    while stack:
        index, parent, owner = stack.pop()
        node = nodes[index]
        world = _mat_mul(parent, _trs(node))
        name = node.get('name')
        if name in ids:
            owner = name   # nearest named ancestor wins, as in the viewer's identity()
        if owner is not None and 'mesh' in node:
            for prim in meshes[node['mesh']]['primitives']:
                acc = accessors[prim['attributes']['POSITION']]
                lo, hi = acc.get('min'), acc.get('max')
                if not lo or not hi:
                    continue
                box = out.get(owner)
                for cx in (lo[0], hi[0]):
                    for cy in (lo[1], hi[1]):
                        for cz in (lo[2], hi[2]):
                            v = to_viewer(_apply(world, (cx, cy, cz)))
                            if box is None:
                                box = out[owner] = [v[0], v[1], v[2], v[0], v[1], v[2]]
                            else:
                                if v[0] < box[0]: box[0] = v[0]
                                if v[1] < box[1]: box[1] = v[1]
                                if v[2] < box[2]: box[2] = v[2]
                                if v[0] > box[3]: box[3] = v[0]
                                if v[1] > box[4]: box[4] = v[1]
                                if v[2] > box[5]: box[5] = v[2]
        for child in node.get('children', []):
            stack.append((child, world, owner))
    return {k: [round(x, 3) for x in v] for k, v in out.items()}


def _fingerprint(root: Path, layers: dict) -> list:
    fp = []
    for key, (glb, side) in sorted(layers.items()):
        for rel in (glb, side):
            st = (root / rel).stat()
            fp.append([rel, st.st_size, int(st.st_mtime)])
    return fp


def all_layers() -> dict:
    return {**BUILDING_LAYERS, **INTERIOR_LAYERS}


def build_index(root: Path = ROOT, layers: dict | None = None, log=print) -> dict:
    layers = layers or all_layers()
    out = {'schema': CACHE_SCHEMA, 'frame': 'viewer (grimes-bim-viewer.html): rotY(pi) + EQUIP_OFFSET, metres, +Y up',
           'fingerprint': _fingerprint(root, layers), 'layers': {}}
    for key, (glb, side) in layers.items():
        meta = json.loads((root / side).read_text())['elements']
        boxes = element_boxes(read_glb_json(root / glb), set(meta))
        out['layers'][key] = {'glb': glb, 'sidecar': side, 'boxes': boxes,
                              'sidecarElements': len(meta), 'withBox': len(boxes)}
        log(f'[ask-twin index] {key}: {len(boxes)}/{len(meta)} elements with a box')
    return out


def load_index(root: Path = ROOT, cache: Path | None = None, log=print) -> dict:
    """Read the cached index if its source fingerprint matches, else rebuild it (a few seconds)."""
    cache = cache or root / 'work' / 'ask-twin' / 'element-index.json'
    layers = all_layers()
    if cache.exists():
        try:
            data = json.loads(cache.read_text())
            if data.get('schema') == CACHE_SCHEMA and data.get('fingerprint') == _fingerprint(root, layers):
                return data
        except (OSError, ValueError):
            pass
    data = build_index(root, layers, log)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, separators=(',', ':')))
    return data


def box_center(b):
    return ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2)


def box_gap(a, b) -> float:
    """Euclidean gap between two boxes (0 when they touch or overlap)."""
    dx = max(0.0, a[0] - b[3], b[0] - a[3])
    dy = max(0.0, a[1] - b[4], b[1] - a[4])
    dz = max(0.0, a[2] - b[5], b[2] - a[5])
    return math.sqrt(dx * dx + dy * dy + dz * dz)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Build/refresh the Ask-the-twin element index (work/ask-twin/).')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    cache = ROOT / 'work' / 'ask-twin' / 'element-index.json'
    if a.force and cache.exists():
        cache.rename(cache.with_suffix('.json.old'))
    idx = load_index()
    print('layers:', {k: v['withBox'] for k, v in idx['layers'].items()})
