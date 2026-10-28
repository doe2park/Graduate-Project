"""Route sketches for docs/FIELD_CAPTURE_L2_L3.md: BIM plan section per floor (1.2 m above the slab), the Level 1
start/end spot at the atrium stair foot (registered Level 1 stations that photo-linked to the Oct 18 stair foot), and the
Oct 18 upper-floor coverage (Cupix-based per-floor packages, local, if present). North-up is inferred from the BIM frame
(Cupix placed video B "north of the building" at BIM z < 0), not from a survey. System python (NumPy, Matplotlib).

    python3 scripts/field_capture_figures.py --out docs/field-capture
"""
import argparse, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import multifloor_review as mr  # noqa: E402

START = [('scan-assets/captures/2026-10-18/panoramas', 'scan-assets/captures/2026-10-18/registration.json', ('pano_107294634', 'pano_107294636', 'pano_107294638')),
         ('scan-assets/panoramas', 'alignment-analysis/accepted-registration.json', ('83697689', '83697690'))]
COVER = {'L2': 'capture-local/grimes-L2-2026-10-18-v2', 'L3': 'capture-local/grimes-L3-2026-10-18-v2'}
TEXT = {'L1': 'START / END: stand still 5 s. Short loop (~10 m) around the atrium lounge, pass the start again, then up the atrium stair.',
        'L2': 'Full corridor ring incl. parts without grey dots, back to the stair top. Grey = Oct 18 coverage.',
        'L3': 'Full loop: every corridor WITHOUT grey dots too (Oct 18 gap), back to the stair top. Grey = Oct 18 coverage.'}


def main():
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    import registration_diagnostics as rd
    ap = argparse.ArgumentParser(); ap.add_argument('--out', default=str(ROOT / 'docs/field-capture'))
    ap.add_argument('--bim-soup', default=str(ROOT / 'work/floorplans/arch-struct.f32')); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); tris = rd.load_soup(a.bim_soup)
    start = []
    for pdir, regf, ids in START:
        m = json.loads((ROOT / pdir / 'manifest.json').read_text()); reg = json.loads((ROOT / regf).read_text())
        start += [mr.apply(reg, s['position'])[0] for s in m['stations'] if s['id'] in ids]
    start = np.array(start); sc = start.mean(0)
    segs = {f: mr.plan_segments(tris, mr.SLAB[f] + 1.2) for f in ('L1', 'L2', 'L3')}
    allp = np.concatenate([s.reshape(-1, 2) for s in segs.values() if len(s)]); lo, hi = np.percentile(allp, 1, 0) - 3, np.percentile(allp, 99, 0) + 3
    for f in ('L1', 'L2', 'L3'):
        fig, ax = plt.subplots(figsize=(8, 7.2))
        ax.add_collection(LineCollection(segs[f], colors='k', linewidths=.35))
        if f in COVER and (ROOT / COVER[f] / 'panoramas/manifest.json').exists():
            st = json.loads((ROOT / COVER[f] / 'panoramas/manifest.json').read_text())['stations']
            p = np.array([s['positionBIM'] for s in st]); ax.plot(p[:, 0], p[:, 2], '-', c='#bbbbbb', lw=1, zorder=1)
            ax.scatter(p[:, 0], p[:, 2], s=14, c='#999999', zorder=2, label='Oct 18 coverage (%d stations)' % len(p))
        if f == 'L1':
            ax.scatter(start[:, 0], start[:, 2], s=18, c='#1b6ca8', zorder=3, label='registered Level 1 photos that matched the stair foot')
            ax.scatter([sc[0]], [sc[2]], s=420, marker='*', c='#d62728', edgecolors='k', zorder=4, label='START / END spot')
        else:
            ax.scatter([sc[0]], [sc[2]], s=160, marker='s', facecolors='none', edgecolors='#d62728', linewidths=2, zorder=4, label='atrium stair (above the start spot)')
        ax.annotate('N (inferred)', xy=(0.95, 0.93), xytext=(0.95, 0.80), xycoords='axes fraction', ha='center', fontsize=10,
                    arrowprops={'arrowstyle': '->', 'lw': 1.5})
        ax.plot([lo[0] + 2, lo[0] + 12], [hi[1] - 2, hi[1] - 2], 'k-', lw=3); ax.text(lo[0] + 7, hi[1] - 3, '10 m', ha='center', fontsize=9)
        ax.set_xlim(lo[0], hi[0]); ax.set_ylim(hi[1], lo[1]); ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
        import textwrap
        ax.set_title(textwrap.fill('%s: %s' % (mr.LEVEL_NAMES[f], TEXT[f]), 95), fontsize=10, loc='left')
        ax.legend(loc='lower left', fontsize=8, framealpha=.9)
        fig.text(0.01, 0.005, 'BIM section 1.2 m above the slab (design geometry, not an official drawing). Provisional sketch.', fontsize=7, color='#555')
        fig.tight_layout(); fig.savefig(out / ('route-%s.png' % f), dpi=110); plt.close(fig); print('wrote', out / ('route-%s.png' % f))


if __name__ == '__main__':
    main()
