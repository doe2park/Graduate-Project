"""Draw Gaussian training progress per zone, for review and slides.

    python3 scripts/gaussian_progress_map.py --out "<folder>" [--captures 2026-10-18 2026-10-18-L3 2026-10-18-L2]

For each capture in scripts/gaussian_zones.json (or a whole-capture preset without zones) it finds finished runs
under work/gaussian/<capture>/<zone>/<run>/ (run.json with every stage done) and reads the last
"Eval iter N: PSNR x, ssim y" line of train/train.log. A zone is DONE only when such a run exists.

Placement: a capture is drawn on the BIM floor-plan section only when its registration file is
status 'geometry-registered' or when --bim-registration names a registration explicitly (the Oct 18 Level 1
export shares the Cupix project frame of May/Sep, so the accepted May registration is used provisionally and the
figure says so). Otherwise the zone map is drawn in the capture's own frame and labelled 'not yet registered to BIM'.
The BIM section comes from work/floorplans/arch-struct.f32 (scripts/decode_bim_soup.mjs output for the architecture
and structure layers); if it is missing, captures are drawn in their own frame.
"""
import argparse
import json
import math
import re
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection

ROOT = Path(__file__).resolve().parents[1]
ZONES = ROOT / 'scripts/gaussian_zones.json'
PRESETS = ROOT / 'scripts/gaussian_presets.json'
SOUP = ROOT / 'work/floorplans/arch-struct.f32'
SLAB = {'LOWER': 0.6, 'L1': 5.2, 'L2': 9.4, 'L3': 14.3}  # BIM slab heights (viewer frame, m)
DONE, OPEN = '#1f8a4c', '#9aa5b1'
ZONE_COLORS = ['#1b6ca8', '#d9822b', '#2e9e6b', '#a24bb0', '#c0392b', '#16a085']
EVAL = re.compile(r'Eval iter (\d+): PSNR ([0-9.]+), ssim ([0-9.]+)')


def finished_run(capture, zone):
    """Latest run folder whose stages are all done, with its last eval line; None if none."""
    base = ROOT / 'work/gaussian' / capture / (zone or 'full')
    if zone is None:
        base = ROOT / 'work/gaussian' / capture
    best = None
    for run in sorted(base.glob('*/run.json') if zone else base.glob('*/run.json')):
        try:
            stages = json.loads(run.read_text()).get('stages', {})
        except (OSError, ValueError):
            continue
        if not stages or any(s.get('status') != 'done' for s in stages.values()):
            continue
        log = run.parent / 'train/train.log'
        hits = EVAL.findall(log.read_text(errors='ignore')) if log.exists() else []
        if hits:
            it, psnr, ssim = hits[-1]
            best = {'run': str(run.parent.relative_to(ROOT)), 'steps': int(it), 'psnr': float(psnr), 'ssim': float(ssim),
                    'trainMinutes': round(stages.get('train', {}).get('seconds', 0) / 60, 1)}
    return best


def registration(path):
    reg = json.loads(Path(path).read_text())
    a = math.radians(reg['rotationYDegrees']); c, s = math.cos(a), math.sin(a); t = reg['translation']
    return lambda p: (c * p[0] + s * p[2] + t[0], -s * p[0] + c * p[2] + t[2])


def plan_segments(floor):
    if not SOUP.exists() or floor not in SLAB:
        return None
    tri = np.fromfile(SOUP, np.float32).reshape(-1, 3, 3).astype(np.float64)
    cut = SLAB[floor] + 1.2
    ys = tri[:, :, 1]; sel = tri[(ys.min(1) < cut) & (ys.max(1) > cut)]
    out = []
    for row in sel:
        pts = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            a, b = row[i], row[j]; da, db = a[1] - cut, b[1] - cut
            if da * db < 0:
                f = da / (da - db); p = a + (b - a) * f; pts.append((p[0], p[2]))
        if len(pts) >= 2:
            out.append(pts[:2])
    return np.array(out)


def draw(capture, entry, preset, out_dir, bim_reg, highlight=None):
    stations = {s['id']: s for s in json.loads((ROOT / entry['manifest']).read_text())['stations']}
    floor = entry.get('floor', '')
    reg_file = ROOT / preset['registration'] if preset else None
    placed = None
    if bim_reg.get(capture):
        placed = registration(ROOT / bim_reg[capture]); note = f'BIM plan · provisional placement with {bim_reg[capture]} (not surveyed)'
    elif reg_file and reg_file.exists() and json.loads(reg_file.read_text()).get('status') == 'geometry-registered':
        placed = registration(reg_file); note = 'BIM plan · registered (internal residual, not surveyed)'
    else:
        note = 'capture frame · not yet registered to BIM'
    xy = (lambda p: placed(p)) if placed else (lambda p: (p[0], p[2]))
    fig, ax = plt.subplots(figsize=(11, 8.5), dpi=170)
    segs = plan_segments(floor) if placed else None
    if segs is not None and len(segs):
        ax.add_collection(LineCollection(segs, colors='#3a3f47', linewidths=0.6, zorder=1))
    status = []; centres = []; labels = []
    for k, z in enumerate(entry['zones']):
        run = finished_run(capture, z['id'])
        col = ZONE_COLORS[k % len(ZONE_COLORS)]
        P = np.array([xy(stations[i]['position']) for i in z['stations'] if i in stations])
        core = np.array([xy(stations[i]['position']) for i in z.get('core', z['stations']) if i in stations])
        ax.scatter(P[:, 0], P[:, 1], s=150, color=col, alpha=0.30 if run else 0.12, edgecolors='none', zorder=2)
        if highlight == z['id']:  # same figure, one zone emphasised (e.g. for a volunteer)
            ax.scatter(P[:, 0], P[:, 1], s=330, facecolors='none', edgecolors=col, linewidths=2.2, zorder=3)
        ax.scatter(core[:, 0], core[:, 1], s=30, color=col, edgecolors='white', linewidths=0.6, zorder=3)
        centres.append(core.mean(0)); labels.append((z, run, col))
        status.append({'zone': z['id'], 'name': z['name'], 'stations': len(z['stations']), 'done': bool(run), **(run or {})})
    allp = np.array([xy(s['position']) for s in stations.values()]); mid = allp.mean(0)
    for (z, run, col), c in zip(labels, centres):  # push each label outward from the floor's centre so labels do not collide
        d = c - mid; n = np.linalg.norm(d) or 1.0; lx, ly = c + d / n * 7.0
        text = ('YOUR PART · ' if highlight == z['id'] else '') + f"{z['name']} ({z['id']})\n" + (f"DONE  {run['psnr']:.1f} dB · SSIM {run['ssim']:.2f}" if run else 'OPEN · volunteer needed')
        ax.annotate(text, xy=c, xytext=(lx, ly), ha='center', va='center', fontsize=12 if highlight == z['id'] else 10, fontweight='bold',
                    color='white' if run else col, zorder=5,
                    bbox=dict(boxstyle='round,pad=0.4', fc=col if run else 'white', ec=col, lw=1.6, ls='-' if run else '--'),
                    arrowprops=dict(arrowstyle='-', color=col, lw=1.2))
    pad = 10; ax.set_xlim(allp[:, 0].min() - pad, allp[:, 0].max() + pad); ax.set_ylim(allp[:, 1].min() - pad, allp[:, 1].max() + pad)
    ax.set_aspect('equal'); ax.invert_yaxis(); ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    ax.plot([x0 + 1, x0 + 11], [y0 - 1.5, y0 - 1.5], color='#003262', lw=4, solid_capstyle='butt')
    ax.text(x0 + 6, y0 - 2.3, '10 m', ha='center', fontsize=9, color='#003262')
    done = sum(s['done'] for s in status)
    ax.set_title(f"Grimes {floor} · {capture} · Gaussian zones {done}/{len(status)} done", fontsize=14, color='#003262', loc='left')
    fig.text(0.01, 0.01, note + ' · scores are on held-out views of each zone; zones are not directly comparable', fontsize=8, color='#555')
    fig.tight_layout()
    out = Path(out_dir) / (f'gaussian-progress-{capture}' + (f'-highlight-{highlight}' if highlight else '') + '.png')
    fig.savefig(out); plt.close(fig)
    return out, status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--captures', nargs='*')
    ap.add_argument('--highlight', help='zone id to emphasise (writes an extra -highlight-<zone> figure; the standard figure is unchanged)')
    ap.add_argument('--bim-registration', action='append', default=['2026-10-18=alignment-analysis/accepted-registration.json'],
                    help='CAPTURE=registration.json to place a capture on the BIM plan provisionally (repeatable)')
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    zones = json.loads(ZONES.read_text())['captures']; presets = json.loads(PRESETS.read_text())['captures']
    bim_reg = dict(x.split('=', 1) for x in a.bim_registration)
    report = {}
    for cap in a.captures or [c for c in zones if c.startswith('2026-10-18')]:
        if cap in zones:
            path, status = draw(cap, zones[cap], presets.get(cap), a.out, bim_reg)
            if a.highlight and any(z['id'] == a.highlight for z in zones[cap]['zones']):
                print('  highlight', draw(cap, zones[cap], presets.get(cap), a.out, bim_reg, a.highlight)[0])
        else:  # whole-capture preset without zones (e.g. the 12-station Level 2 piece)
            run = finished_run(cap, None)
            status = [{'zone': 'whole', 'done': bool(run), **(run or {})}]; path = None
        report[cap] = {'figure': str(path) if path else None, 'zones': status}
        print(cap, f"{sum(s['done'] for s in status)}/{len(status)} done", path or '')
    (Path(a.out) / 'gaussian-progress.json').write_text(json.dumps(report, indent=1) + '\n')


if __name__ == '__main__':
    main()
