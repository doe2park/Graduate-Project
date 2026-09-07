#!/usr/bin/env python3
"""Plan original-ID MEP recovery from an APS metadata sidecar, without network access.

Place beside extract_mep_layer.py, or provide --extractor-dir. Outputs wanted
geometry-tree dbIds and leaf-to-owner mappings, plus honest total/excluded/
eligible/current geometry coverage. Never copies the metadata _source URN.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re


def plan_layer(meta, source_rule, classify_type):
    """Identify eligible depth-3 entities and all descendants, preserving IDs."""
    src_rx, rvt_rx = source_rule
    byext = {e['externalId']: did for did, e in meta.items()}
    total, eligible = set(), set()
    for did, e in meta.items():
        parts = e['externalId'].split('/')
        if e.get('category') or len(parts) != 3:
            continue
        src, name = e.get('source_file') or '', e.get('name') or ''
        if not (re.search(src_rx, src, re.I) or
                (rvt_rx and 'ENG_R22.rvt' in src and re.search(rvt_rx, name, re.I))):
            continue
        total.add(did)
        cad = meta.get(byext.get('/'.join(parts[:2]), ''), {}).get('name')
        if classify_type(name, cad) is not None:
            eligible.add(did)
    owners = {}
    for did, e in meta.items():
        parts = e['externalId'].split('/')
        if len(parts) < 3:
            continue
        owner = byext.get('/'.join(parts[:3]))
        if owner in eligible:
            owners[did] = owner
    return total, eligible, owners


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('metadata', type=Path)
    ap.add_argument('output_dir', type=Path)
    ap.add_argument('--extractor-dir', type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument('--bindings-dir', type=Path)
    args = ap.parse_args()
    spec = importlib.util.spec_from_file_location('mep_extractor', args.extractor_dir / 'extract_mep_layer.py')
    extractor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extractor)
    meta = json.loads(args.metadata.read_text())['elements']
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report, union = {}, set()
    for layer, rule in extractor.SRC.items():
        total, eligible, owners = plan_layer(meta, rule, extractor.type_of)
        entry = {'total': len(total), 'excluded': len(total - eligible), 'eligible': len(eligible),
                 'wanted_dbids': len(owners)}
        if args.bindings_dir:
            current = json.loads((args.bindings_dir / f'{layer}.elements.json').read_text())['elements']
            missing = set(current) - eligible
            mismatches = [did for did, e in current.items()
                          if did in meta and e['name'] != meta[did]['name']]
            if missing or mismatches:
                raise ValueError(f'{layer}: baseline IDs/names incompatible with source metadata')
            entry['with_geometry_current'] = len(current)
        wanted = sorted(map(int, owners))
        (args.output_dir / f'{layer}.wanted.json').write_text(json.dumps(wanted))
        (args.output_dir / f'{layer}.owners.json').write_text(json.dumps(owners))
        union.update(wanted)
        report[layer] = entry
    (args.output_dir / 'all.wanted.json').write_text(json.dumps(sorted(union)))
    (args.output_dir / 'coverage.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
