#!/usr/bin/env python3
"""Split canonical element GLBs by floor and bounded mesh-node count.

Copies bufferViews verbatim through extract_layer.subset_from_source, preserving
every dbId node and the source root frame. No Draco decoding or encoding.
"""
import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

FLOOR_ORDER = {'lower': 0, 'l1': 1, 'l2': 2, 'l3': 3, 'l4': 4, 'unknown': 99}


def floor_key(element):
    key = (element.get('levelKey') or '').lower()
    if key in FLOOR_ORDER:
        return key
    match = re.match(r'^(?:MD)?(\d\d)', element.get('source_file') or '', re.I)
    if match:
        return {'00': 'lower', '01': 'l1', '02': 'l2', '03': 'l3', '04': 'l4'}.get(match[1], 'unknown')
    return 'unknown'


def partitions(document, elements, max_nodes):
    floors = defaultdict(dict)
    for idx, node in enumerate(document['nodes']):
        if 'mesh' not in node:
            continue
        owner = node.get('name')
        if owner not in elements:
            raise ValueError(f'Unbound mesh node: {owner}')
        floors[floor_key(elements[owner])].setdefault(owner, []).append(idx)
    result = []
    for floor in sorted(floors, key=lambda key: (FLOOR_ORDER.get(key, 99), key)):
        parts, keep = [], {}
        for owner, indices in floors[floor].items():
            if len(indices) > max_nodes:
                raise ValueError(f'Element {owner} alone exceeds max-nodes ({len(indices)})')
            if keep and len(keep) + len(indices) > max_nodes:
                parts.append(keep)
                keep = {}
            keep.update({idx: owner for idx in indices})
        if keep:
            parts.append(keep)
        for number, mapping in enumerate(parts, 1):
            suffix = floor if len(parts) == 1 else f'{floor}-{number}'
            result.append((floor, suffix, mapping))
    return result


def primitive_counts(document):
    result = defaultdict(Counter)
    for node in document['nodes']:
        if 'mesh' not in node:
            continue
        counts = result[node['name']]
        counts['nodes'] += 1
        for primitive in document['meshes'][node['mesh']]['primitives']:
            accessor = document['accessors'][primitive.get('indices', primitive['attributes']['POSITION'])]
            counts[f'mode_{primitive.get("mode", 4)}_indices'] += accessor['count']
    return dict(result)


def buffer_hashes(document, binary):
    return Counter(hashlib.sha256(binary[v.get('byteOffset', 0):v.get('byteOffset', 0) + v['byteLength']]).hexdigest()
                   for v in document.get('bufferViews', []))


def split_document(document, binary, elements, max_nodes, subset_from_source):
    root_idx = document['scenes'][document.get('scene', 0)]['nodes']
    if len(root_idx) != 1:
        raise ValueError('Expected one canonical scene root')
    root_idx = root_idx[0]
    source_root = {k: copy.deepcopy(v) for k, v in document['nodes'][root_idx].items() if k != 'children'}
    for idx, node in enumerate(document['nodes']):
        if idx != root_idx and 'mesh' not in node and any(k in node for k in ('matrix', 'rotation', 'scale', 'translation')):
            raise ValueError('Intermediate group transforms are unsupported')
    source_hashes = buffer_hashes(document, binary)
    source_counts = primitive_counts(document)
    seen = set()
    result = []
    for floor, suffix, keep in partitions(document, elements, max_nodes):
        out, accessors, views, meshes, materials = bytearray(), [], [], [], []
        leaves = subset_from_source(document, binary, keep, out, accessors, views, meshes, materials)
        root = copy.deepcopy(source_root)
        root['children'] = [1]
        new = {k: copy.deepcopy(v) for k, v in document.items()
               if k in ('asset', 'extensionsUsed', 'extensionsRequired')}
        new.update({'scene': 0, 'scenes': [{'nodes': [0]}],
                    'nodes': [root, {'name': f'chunk:{suffix}', 'children': list(range(2, 2 + len(leaves)))}] + leaves,
                    'accessors': accessors, 'bufferViews': views, 'meshes': meshes,
                    'materials': materials, 'buffers': [{'byteLength': len(out)}]})
        counts = primitive_counts(new)
        if seen & set(counts):
            raise ValueError('An owner was split between chunks')
        if any(counts[owner] != source_counts[owner] for owner in counts):
            raise ValueError('Primitive counts changed')
        if buffer_hashes(new, out) - source_hashes:
            raise ValueError('Buffer bytes changed')
        seen.update(counts)
        result.append((floor, suffix, new, out, len(counts)))
    if seen != set(source_counts):
        raise ValueError('Chunk identity union differs from canonical GLB')
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('elements', type=Path)
    ap.add_argument('output_dir', type=Path)
    ap.add_argument('--prefix', default='grimes-fire')
    ap.add_argument('--max-nodes', type=int, default=30000)
    ap.add_argument('--extractor-dir', type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()
    if args.max_nodes <= 0:
        raise ValueError('max-nodes must be positive')
    sys.path.insert(0, str(args.extractor_dir))
    from extract_layer import read_glb, write_glb, subset_from_source
    document, binary = read_glb(args.source)
    elements = json.loads(args.elements.read_text())['elements']
    chunks = split_document(document, binary, elements, args.max_nodes, subset_from_source)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for floor, suffix, chunk, payload, owners in chunks:
        filename = f'{args.prefix}-{suffix}.glb'
        dest = args.output_dir / filename
        write_glb(chunk, payload, dest)
        entry = {'file': filename, 'levelKey': floor.upper(), 'meshNodes': len(chunk['nodes']) - 2,
                 'elements': owners, 'bytes': dest.stat().st_size}
        entries.append(entry)
        print(json.dumps(entry), flush=True)
    report = {'schema': 'element-glb-chunks/1', 'canonical': args.source.name,
              'maxMeshNodes': args.max_nodes, 'checks': {'identityUnionExact': True,
              'perOwnerPrimitiveCountsExact': True, 'bufferViewsByteIdentical': True,
              'rootFrameExact': True, 'ownersUnsplit': True}, 'chunks': entries}
    (args.output_dir / f'{args.prefix}.chunks.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
