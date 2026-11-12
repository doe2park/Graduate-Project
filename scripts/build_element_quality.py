#!/usr/bin/env python3
"""Build buildings/grimes/element-quality.json: a derived overlay that names known content defects of the
element model, so the viewers can hide or correct them at load time.

Nothing in a GLB or in a *.elements.json sidecar is changed. The 66,620 source identities stay as exported; this
file only says which of them are not real building parts, and where a floor label disagrees with the geometry.
Geometry facts come from the GLB JSON chunk (primitive modes, vertex counts, POSITION min/max); nothing is decoded.

Rules (each id gets at most one "hidden" reason, checked in this order):
  annotation   line-only geometry on a CAD "-ANNO" layer whose source_guid also has a solid twin in the same layer
  reference    layout points, sleeve points, clearance zones and load symbols: construction aids, not parts
  duplicate    same type, same name and the same bounding box to 1 mm as another element in the layer;
               the copy with the most triangles (then the lowest id) is kept
Not hidden, only described:
  noGeometry   every primitive is a single vertex: the element has an identity but nothing to draw
  aggregate    one fabrication-drawing object that spans most of a floor plate (a whole floor's hangers
               exported as one object, for example); it cannot be picked as a single part
  storey       the element's box lies entirely outside the storey its level label names; the value is the storey
               that contains the box centre. Floors are the measured slab tops in the viewer frame.

Usage:  python3 scripts/build_element_quality.py            write the overlay
        python3 scripts/build_element_quality.py --check    exit 1 if the committed overlay is stale
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ask_twin.index import BUILDING_LAYERS, ROOT, _apply, _mat_mul, _trs, read_glb_json, to_viewer  # noqa: E402

SCHEMA = 'twin-element-quality/1'
OUT = 'buildings/grimes/element-quality.json'
# Slab tops in the viewer frame (metres). Measured: median top of interior/floors-l{1,2,3}.glb and the median of
# (element centre - Revit "elevation from level") per Revit level. They sit 0.83 m below the Revit elevations.
FLOORS = [('LOWER', 0.69), ('L1', 5.26), ('L2', 9.53), ('L3', 14.41), ('ROOF', 18.98)]
BELOW_TOLERANCE_M, ABOVE_TOLERANCE_M = 1.0, 0.5   # framing hangs below its floor; devices sit just above the next one
REFERENCE_NAME = re.compile(r'Clearance Zone|Layout Point|Sleeve Point|Control Point|Generic Pt|eV_Point|Point Load Symbol', re.I)
AGGREGATE_SPAN_M = 30.0   # fabrication (DWG) layers only: a Revit slab this long is one real part


def layer_facts(gltf: dict, ids: set) -> dict:
    """{id: {'box': [6], 'tris': int, 'solid': bool, 'maxVerts': int, 'fragments': int}} with boxes in the viewer frame."""
    nodes, meshes, accessors = gltf.get('nodes', []), gltf.get('meshes', []), gltf.get('accessors', [])
    out: dict = {}
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    stack = [(i, identity, None) for i in gltf['scenes'][gltf.get('scene', 0)]['nodes']]
    while stack:
        index, parent, owner = stack.pop()
        node = nodes[index]
        world = _mat_mul(parent, _trs(node))
        if node.get('name') in ids:
            owner = node['name']
        if owner is not None and 'mesh' in node:
            fact = out.setdefault(owner, {'box': None, 'tris': 0, 'solid': False, 'maxVerts': 0, 'fragments': 0})
            fact['fragments'] += 1
            for prim in meshes[node['mesh']]['primitives']:
                acc = accessors[prim['attributes']['POSITION']]
                fact['maxVerts'] = max(fact['maxVerts'], acc.get('count', 0))
                if prim.get('mode', 4) == 4:
                    fact['solid'] = True
                    count = accessors[prim['indices']]['count'] if 'indices' in prim else acc.get('count', 0)
                    fact['tris'] += count // 3
                lo, hi = acc.get('min'), acc.get('max')
                if not lo or not hi:
                    continue
                box = fact['box']
                for cx in (lo[0], hi[0]):
                    for cy in (lo[1], hi[1]):
                        for cz in (lo[2], hi[2]):
                            v = to_viewer(_apply(world, (cx, cy, cz)))
                            if box is None:
                                box = fact['box'] = [v[0], v[1], v[2], v[0], v[1], v[2]]
                            else:
                                for a in range(3):
                                    if v[a] < box[a]: box[a] = v[a]
                                    if v[a] > box[a + 3]: box[a + 3] = v[a]
        for child in node.get('children', []):
            stack.append((child, world, owner))
    return out


def storey_of(label: str, box) -> str | None:
    """The storey that holds the box centre, when the box is wholly outside the labelled storey. Else None."""
    keys = [k for k, _ in FLOORS]
    label = 'LOWER' if label == 'MEZZ' else label
    if label not in keys or box is None:
        return None
    at = keys.index(label)
    low = -1e9 if at == 0 else FLOORS[at][1] - BELOW_TOLERANCE_M
    high = 1e9 if at + 1 == len(FLOORS) else FLOORS[at + 1][1] + ABOVE_TOLERANCE_M
    if box[4] >= low and box[1] <= high:
        return None
    centre, found = (box[1] + box[4]) / 2, keys[0]
    for key, y in FLOORS:
        if centre >= y - 0.05:
            found = key
    return None if found == label else found


def numeric(ids):
    return sorted(ids, key=lambda i: (0, int(i)) if i.isdigit() else (1, i))


def build(root: Path = ROOT, log=print) -> dict:
    layers, sources, totals = {}, {}, Counter()
    for key, (glb, side) in BUILDING_LAYERS.items():
        raw = (root / side).read_bytes()
        meta = json.loads(raw)['elements']
        facts = layer_facts(read_glb_json(root / glb), set(meta))
        sources[key] = {'sidecar': side, 'sidecarSha256': hashlib.sha256(raw).hexdigest(), 'glb': glb, 'glbBytes': (root / glb).stat().st_size}
        hidden: dict = {}
        solid_guids = {e.get('source_guid') for i, e in meta.items() if facts.get(i, {}).get('solid')}
        for i, e in meta.items():
            fact = facts.get(i)
            if fact and not fact['solid'] and fact['maxVerts'] > 1 and str(e.get('system', '')).endswith('-ANNO') and e.get('source_guid') in solid_guids:
                hidden[i] = 'annotation'
            elif REFERENCE_NAME.search(str(e.get('name', ''))):
                hidden[i] = 'reference'
        groups = defaultdict(list)
        for i, e in meta.items():
            fact = facts.get(i)
            if i in hidden or not fact or not fact['box'] or not fact['solid']:
                continue
            groups[(e.get('type'), e.get('name'), tuple(round(v, 3) for v in fact['box']))].append(i)
        for members in groups.values():
            if len(members) > 1:
                keep = min(members, key=lambda i: (-facts[i]['tris'], int(i) if i.isdigit() else 0, i))
                for i in members:
                    if i != keep:
                        hidden[i] = 'duplicate'
        no_geometry = [i for i in meta if i not in hidden and (i not in facts or facts[i]['maxVerts'] <= 1)]
        aggregate = [i for i, f in facts.items() if i not in hidden and f['box'] and 'cad_handle' in meta[i]
                     and max(f['box'][3] - f['box'][0], f['box'][5] - f['box'][2]) > AGGREGATE_SPAN_M]
        storey = defaultdict(list)
        for i, e in meta.items():
            if i in hidden or i in no_geometry:
                continue
            found = storey_of(e.get('levelKey'), facts.get(i, {}).get('box'))
            if found:
                storey[found].append(i)
        by_reason = defaultdict(list)
        for i, reason in hidden.items():
            by_reason[reason].append(i)
        entry = {'elements': len(meta),
                 'hidden': {r: numeric(v) for r, v in sorted(by_reason.items())},
                 'noGeometry': numeric(no_geometry), 'aggregate': numeric(aggregate),
                 'storey': {k: numeric(storey[k]) for k, _ in FLOORS if storey.get(k)}}
        layers[key] = entry
        counts = {**{r: len(v) for r, v in entry['hidden'].items()}, 'noGeometry': len(no_geometry), 'aggregate': len(aggregate), 'storey': sum(len(v) for v in storey.values())}
        totals.update(counts)
        totals['elements'] += len(meta)
        log(f'[element-quality] {key}: {len(meta)} elements · ' + ' · '.join(f'{k} {v}' for k, v in counts.items() if v))
    hidden_total = sum(totals[r] for r in ('annotation', 'reference', 'duplicate'))
    return {'_schema': SCHEMA,
            '_doc': 'Derived by scripts/build_element_quality.py from the GLB JSON chunks and the element sidecars. '
                    'It changes no source file. "hidden" ids are not building parts (annotation copies, layout points and '
                    'clearance zones, exact double exports); viewers skip them unless the page is opened with ?flagged=1. '
                    '"storey" lists elements whose box lies wholly outside the storey their level label names.',
            'floorsViewerY': dict(FLOORS),
            'storeyTolerance': {'belowLabelledFloorM': BELOW_TOLERANCE_M, 'aboveNextFloorM': ABOVE_TOLERANCE_M},
            'summary': {'elements': totals['elements'], 'hidden': hidden_total, 'shownByDefault': totals['elements'] - hidden_total,
                        **{k: totals[k] for k in ('annotation', 'reference', 'duplicate', 'noGeometry', 'aggregate', 'storey')}},
            'sources': sources, 'layers': layers}


def render(data: dict) -> str:
    return json.dumps(data, separators=(',', ':'), sort_keys=False) + '\n'


def main(argv) -> int:
    quiet = '--check' in argv
    text = render(build(log=(lambda *_: None) if quiet else print))
    path = ROOT / OUT
    if quiet:
        if not path.exists() or path.read_text() != text:
            print(f'{OUT} is stale: run python3 scripts/build_element_quality.py', file=sys.stderr)
            return 1
        return 0
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(text)
    tmp.replace(path)
    print(f'wrote {OUT} ({len(text)} bytes)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
