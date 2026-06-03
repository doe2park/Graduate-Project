#!/usr/bin/env python3
"""
Extract LEED v4.1 MR "Building Life-Cycle Impact Reduction" data
(Option 1, Path 1 — Maintain Existing Structural Elements) from the
Bechtel LEED-LCA submittal spreadsheet into a small JSON the front-end
can consume.

Source:
    `Submittal/UCB _LEED_LCA credit.xlsx`
    Path 1 table (Walls / Floors / Roofs / Envelope)

Output:
    data/bechtel_lca.json

Adds the "embodied-carbon / material reuse" layer to the digital twin:
- Per-element existing area, reused area, project area
- Reuse % of project area (LEED scoring metric)
- Reuse % of existing material kept (renovation completeness)
- Total project reuse % → LEED credit point band

Re-run whenever an updated LCA submittal arrives.

Usage:
    pip install openpyxl --break-system-packages
    python extract_lca.py path/to/UCB_LEED_LCA_credit.xlsx
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("Install openpyxl: pip install openpyxl --break-system-packages")

# LEED v4.1 BD+C NC — Building Life-Cycle Impact Reduction
# Option 1, Path 1 scoring bands (% reuse of project area)
SCORING_BANDS = [
    (90, 'exemplary', 6),
    (75, '5 points', 5),
    (60, '4 points', 4),
    (45, '3 points', 3),
    (30, '2 points', 2),
    (15, '1 point', 1),
    (0,  'below threshold', 0),
]


def band_for(pct):
    for thresh, label, pts in SCORING_BANDS:
        if pct >= thresh:
            return {'label': label, 'points': pts, 'threshold_pct': thresh}
    return {'label': 'below threshold', 'points': 0, 'threshold_pct': 0}


def num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def pct(numerator, denominator):
    if not denominator:
        return None
    return round(numerator / denominator * 100, 1)


def extract(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.active  # Sheet1 — single sheet

    # Walk rows looking for the Path 1 element table (Walls / Floors / Roofs / Envelope).
    # Spreadsheet structure:
    #   row 3: header (Element, Existing Area, Reused Area, Project area, note)
    #   row 4-7: elements
    elements = []
    in_table = False
    for r in ws.iter_rows(min_row=1, max_row=20, values_only=True):
        if not r or not any(r):
            continue
        first = str(r[0]).strip() if r[0] else ''

        if first == 'Element' and in_table is False:
            in_table = True
            continue

        if in_table:
            existing = num(r[1])
            reused = num(r[2])
            project = num(r[3])
            note = (r[4] or '').strip() if r[4] else None

            # Stop on blank row or section break (e.g. "AND/OR Path 2:")
            if not first or first.startswith('AND/OR') or 'Path 2' in first:
                break

            # Strip trailing comma/whitespace from element label
            name = first.rstrip(' ,')

            elements.append({
                'element': name,
                'existing_sqft': existing,
                'reused_sqft': reused,
                'project_sqft': project,
                'reuse_pct_of_project': pct(reused or 0, project) if project else None,
                'kept_pct_of_existing': pct(reused or 0, existing) if existing else None,
                'note': note,
            })

    # Totals (per LEED v4.1 calculation: sum reused / sum project area)
    total_existing = sum(e['existing_sqft'] or 0 for e in elements)
    total_reused = sum(e['reused_sqft'] or 0 for e in elements)
    total_project = sum(e['project_sqft'] or 0 for e in elements)
    overall_pct = pct(total_reused, total_project) if total_project else 0
    score = band_for(overall_pct or 0)

    return {
        '_doc': 'LEED v4.1 BD+C Materials & Resources credit — Building '
                'Life-Cycle Impact Reduction (Option 1, Path 1: Maintain '
                'Existing Structural Elements). Bechtel Engineering Center '
                'Addition & Renovation. Extracted from the LEED-LCA '
                'submittal calculator. Powers the embodied-carbon / material '
                'reuse layer of the digital twin.',
        '_source_file': Path(xlsx_path).name,
        '_leed_credit': 'MR — Building Life-Cycle Impact Reduction (v4.1)',
        '_leed_project_id': '1000171106',
        '_consultant': 'Sage Green Strategies',
        '_architect': 'Skidmore, Owings & Merrill (SOM)',
        '_submitted': '2023-11-30',
        'elements': elements,
        'totals': {
            'existing_sqft': round(total_existing, 1),
            'reused_sqft': round(total_reused, 1),
            'project_sqft': round(total_project, 1),
            'overall_reuse_pct_of_project': overall_pct,
            'score_band': score,
        },
        'narrative': {
            'headline': f'{overall_pct:.0f}% of the project area is reused existing structure',
            'detail': (f'The Bechtel renovation kept the bones of the original '
                       f'building — roughly {overall_pct:.0f}% of the finished '
                       f'project area is original existing structure. Floors '
                       f'and envelope were retained almost entirely.'),
            'leed_score': f'Qualifies for LEED {score["label"]} ({score["points"]} pt band) under MR Building Life-Cycle Impact Reduction.',
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('xlsx', help='Path to UCB _LEED_LCA credit.xlsx')
    ap.add_argument('--output', default='data/bechtel_lca.json')
    args = ap.parse_args()

    data = extract(args.xlsx)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(data, f, indent=2)

    t = data['totals']
    print(f"  {len(data['elements'])} elements extracted")
    print(f"  Existing reused: {t['reused_sqft']:,.0f} sqft of {t['project_sqft']:,.0f} project sqft")
    print(f"  Overall reuse %: {t['overall_reuse_pct_of_project']:.1f}%  →  "
          f"LEED {t['score_band']['label']} ({t['score_band']['points']} pt band)")
    for e in data['elements']:
        rp = e['reuse_pct_of_project']
        kp = e['kept_pct_of_existing']
        if rp is None:
            continue
        kept_str = f"{kp:.1f}% of existing kept" if kp is not None else "no existing (new construction)"
        print(f"    {e['element']:12} {rp:5.1f}% of project ({kept_str})")
    print(f"→ wrote {args.output}")


if __name__ == '__main__':
    main()
