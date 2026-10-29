# Small inline-SVG charts for the test-install callouts (slides 8-12). PUBLIC.
# Every series comes from twin/sensors/registry.json or the deterministic demo feed (tools/sensor_sim.py, same math as
# twin/sensors/feed.js). Nothing here is measured: each chart carries a "SIMULATED" tag. The checks in chart_for() keep the
# drawn numbers consistent with the card text (0.42 / 0.55 kW, 1.2 -> 2.1 mm/s, night flow 01:00-04:00, +9 degC at 33 m).
import html, json, math, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / 'tools'))
import sensor_sim  # noqa: E402  deterministic demo feed

REG = json.loads((REPO / 'twin' / 'sensors' / 'registry.json').read_text())
BY = {s['id']: s for s in REG['sensors']}
SIM_DAY = datetime(2026, 10, 26, tzinfo=ZoneInfo('America/Los_Angeles'))   # the simulated day drawn for feed-only sensors
W, H = 400, 236                       # viewBox = slide pixels at 1920 x 1080
L, R, T, B = 58, 14, 34, 40           # plot margins
FS = 17                               # axis / label font size (slide px)
INK, MUTE, GRID = '#1F2A37', '#5B7089', '#D5DEE8'
e = lambda s: html.escape(str(s), quote=True)
_N = [0]   # gradient id counter (stable across runs)


def fmt(v):
    return f'{v:.2f}'.rstrip('0').rstrip('.') if abs(v) < 10 else f'{v:.0f}'


def sim_day(sid):
    """24 hourly values of the demo feed over SIM_DAY (00:00-23:00 local)."""
    return [sensor_sim.simulate(BY[sid], int(SIM_DAY.replace(hour=h).timestamp() * 1000))['value'] for h in range(24)]


def dts_profile(n=97):
    """(metres, degC, baseline degC) along the cable, from the registry dts block (same formula as twin/sensor-demo.js dtsTempC)."""
    d = BY['leak-dts']['dts']; m0, m1 = d['cableM']
    us = [i / (n - 1) for i in range(n)]
    base = [d['baselineC'] + d['slopeC'] * (u - .5) for u in us]
    temp = [b + (d['peakC'] - d['baselineC']) * math.exp(-((u - d['hotT']) / d['hotWidth']) ** 2) + .35 * math.sin(u * 23) for u, b in zip(us, base)]
    return [m0 + u * (m1 - m0) for u in us], temp, base


def chart(xs, ys, *, title, unit, xticks, color, ylo=None, yhi=None, yticks=None, ref=None, band=None, marks=(), base=None, grad=None, step=False, ylabels=None):
    """Line chart. ref=(value, label) dashed reference; band=(x0, x1, label) shaded span; marks=[(x, y, label, anchor)];
    base=ys of a dashed baseline; grad=[(offset, colour)] colours the line along x; step=draw as steps; ylabels={value: text}."""
    x0, x1 = min(xs), max(xs)
    lo = min(ys + ([ref[0]] if ref else []) + (base or [])) if ylo is None else ylo
    hi = max(ys + ([ref[0]] if ref else []) + (base or [])) if yhi is None else yhi
    sp = (hi - lo) or 1
    X = lambda x: L + (x - x0) / ((x1 - x0) or 1) * (W - L - R)
    Y = lambda y: H - B - (y - lo) / sp * (H - T - B)
    o = [f'<svg class="twc" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{e(title)} (simulated)">']
    o.append(f'<text x="0" y="17" font-size="{FS}" font-weight="700" fill="{INK}">{e(title)}<tspan font-weight="400" fill="{MUTE}">{e(" · " + unit if unit else "")}</tspan></text>'
             f'<text x="{W}" y="17" font-size="13" font-weight="700" fill="#7C3AED" text-anchor="end" letter-spacing=".06em">SIMULATED</text>')
    if band:
        o.append(f'<rect x="{X(band[0]):.1f}" y="{T}" width="{X(band[1]) - X(band[0]):.1f}" height="{H - T - B}" fill="#FDB515" fill-opacity=".22"/>'
                 f'<text x="{(X(band[0]) + X(band[1])) / 2:.1f}" y="{H - B - 8}" font-size="14" fill="#8A5A00" text-anchor="middle" font-weight="700" paint-order="stroke" stroke="#FFF3D6" stroke-width="4">{e(band[2])}</text>')
    for v in (yticks or [lo, hi]):
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{GRID}" stroke-width="1"/>'
                 f'<text x="{L - 6}" y="{Y(v) + 5:.1f}" font-size="{FS - 2}" fill="{MUTE}" text-anchor="end">{e((ylabels or {}).get(v, fmt(v)))}</text>')
    for x, lab in xticks:
        o.append(f'<line x1="{X(x):.1f}" x2="{X(x):.1f}" y1="{H - B}" y2="{H - B + 5}" stroke="{MUTE}"/>'
                 f'<text x="{X(x):.1f}" y="{H - B + 22}" font-size="{FS - 2}" fill="{MUTE}" text-anchor="middle">{e(lab)}</text>')
    o.append(f'<line x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}" stroke="{MUTE}" stroke-width="1.5"/>')
    if ref:
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(ref[0]):.1f}" y2="{Y(ref[0]):.1f}" stroke="{INK}" stroke-width="2" stroke-dasharray="7 5"/>'
                 f'<text x="{L + 4}" y="{Y(ref[0]) - 6:.1f}" font-size="14" fill="{INK}" text-anchor="start" paint-order="stroke" stroke="#fff" stroke-width="3">{e(ref[1])}</text>')
    if base:
        d = ' '.join(f'{X(x):.1f},{Y(y):.1f}' for x, y in zip(xs, base))
        o.append(f'<polyline points="{d}" fill="none" stroke="{MUTE}" stroke-width="2" stroke-dasharray="6 5"/>'
                 f'<text x="{X(xs[len(xs) // 6]):.1f}" y="{Y(base[len(xs) // 6]) + 22:.1f}" font-size="14" fill="{MUTE}">baseline</text>')
    if step:
        pts = []
        for i, (x, y) in enumerate(zip(xs, ys)):
            if i: pts.append((x, ys[i - 1]))
            pts.append((x, y))
    else:
        pts = list(zip(xs, ys))
    d = ' '.join(f'{X(x):.1f},{Y(y):.1f}' for x, y in pts)
    stroke = color
    if grad:
        _N[0] += 1; gid = f'twg{_N[0]}'
        o.append(f'<defs><linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{L}" x2="{W - R}" y1="0" y2="0">'
                 + ''.join(f'<stop offset="{of:.3f}" stop-color="{c}"/>' for of, c in grad) + '</linearGradient></defs>')
        stroke = f'url(#{gid})'
    o.append(f'<polyline points="{d}" fill="none" stroke="#fff" stroke-width="7" stroke-linejoin="round"/>'
             f'<polyline points="{d}" fill="none" stroke="{stroke}" stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round"/>')
    for x, y, lab, anc in marks:
        below = anc.endswith('-below'); anc = anc.replace('-below', '')
        tx = X(x) + {'start': 8, 'end': -8, 'middle': 0}[anc]
        ty = Y(y) + 24 if below or Y(y) - 10 <= T + 4 else Y(y) - 10
        o.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="5.5" fill="{color}" stroke="#fff" stroke-width="2"/>'
                 f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="{FS}" font-weight="700" fill="{INK}" text-anchor="{anc}" paint-order="stroke" stroke="#fff" stroke-width="4">{e(lab)}</text>')
    o.append('</svg>')
    return ''.join(o)


HOURS = [(0, '00'), (6, '06'), (12, '12'), (18, '18'), (23, '23 h')]
DTS_STOPS = [[0, (30, 80, 220)], [.33, (0, 190, 230)], [.6, (250, 215, 40)], [1, (230, 30, 30)]]


def _cmap(v):
    v = max(0, min(1, v))
    for (a, ca), (b, cb) in zip(DTS_STOPS, DTS_STOPS[1:]):
        if v <= b:
            f = (v - a) / (b - a); return '#%02x%02x%02x' % tuple(round(c + f * (d - c)) for c, d in zip(ca, cb))
    return '#e61e1e'


def _dts(emph):
    xs, ys, base = dts_profile(); d = BY['leak-dts']['dts']
    i = max(range(len(ys)), key=ys.__getitem__); pm, pc, rise = xs[i], ys[i], ys[i] - base[i]
    # consistency with the card text: "31 degC at 33 m", "+9 degC above baseline", "22 degC baseline"
    assert round(pm) == 33 and round(pc) == 31 and round(rise) == 9 and d['baselineC'] == 22, (pm, pc, rise)
    lo, hi = d['scaleC']; m0, m1 = d['cableM']
    grad = [((x - m0) / (m1 - m0), _cmap((y - lo) / (hi - lo))) for x, y in zip(xs[::4], ys[::4])]
    lab = f'+{rise:.0f} °C at {pm:.0f} m' if emph else f'{pc:.0f} °C at {pm:.0f} m'
    return chart(xs, ys, title='Temperature along the cable', unit='°C', color='#C81E1E', ylo=18, yhi=33, yticks=[18, 22, 26, 30],
                 xticks=[(m, f'{m} m' if m == m1 else str(m)) for m in range(m0, m1 + 1, 4)], base=base, grad=grad,
                 marks=[(pm, pc, lab, 'start')], band=(pm - 1.5, pm + 1.5, 'test location') if emph else None)


def _day(sid, title, unit, color, **kw):
    return chart(list(range(24)), kw.pop('ys'), title=title, unit=unit, color=color, xticks=HOURS, **kw)


def _wet(sid):
    ys = sim_day(sid)
    assert all(v == 0 for v in ys), 'the demo puck is dry all day'
    return chart(list(range(24)), ys, title='Wetness over one day', unit='', color='#003262', ylo=0, yhi=1.2, yticks=[0, 1], step=True,
                 ylabels={0: 'dry', 1: 'wet'}, xticks=HOURS, marks=[(12, 0, 'dry all day', 'middle')], ref=(1, 'would flip to "water detected"'))


def chart_for(sid):
    """Inline SVG for one sensor, or '' when the registry / feed has no series that matches its card."""
    if sid in ('leak-dts', 'leak-alert'):
        return _dts(sid == 'leak-alert')
    if sid in ('leak-puck', 'water-puck'):
        return _wet(sid)
    if sid == 'leak-vibration':
        ys = sim_day(sid)
        return _day(sid, 'Vibration over one day', 'mm/s', '#087F8C', ys=ys, ylo=0, yhi=1.2, yticks=[0, .4, .8, 1.2])
    if sid == 'hvac-airflow':
        ys = sim_day(sid); assert 420 in ys
        return _day(sid, 'Branch airflow vs design', 'CFM', '#087F8C', ys=ys, ylo=0, yhi=500, yticks=[0, 200, 400],
                    ref=(450, 'design ref. 450 (to verify)'), marks=[(ys.index(420), 420, '420', 'end')])
    if sid in ('water-flow', 'water-alert'):
        ys = BY['water-flow']['reading']['series']; night = ys[1:5]
        assert len(ys) == 24 and min(night) >= .55 and max(night) == .6 and max(ys[5:] + ys[:1]) < .2
        return _day(sid, 'Flow over one day', 'L/s', '#087F8C', ys=ys, ylo=0, yhi=.7, yticks=[0, .3, .6],
                    band=(1, 4, ''), marks=[(2, .6, '0.6 L/s, 01:00–04:00', 'start')])
    if sid == 'power-ct':
        ys = BY['power-ct']['reading']['series']
        assert ys[16] == .42 and max(ys) == .55 and ys.index(.55) == 11
        return _day(sid, 'Circuit power: operating vs idle', 'kW', '#E8590C', ys=ys, ylo=0, yhi=.7, yticks=[0, .2, .4, .6],
                    band=(7, 19, 'operating hours'), marks=[(11, .55, 'peak 0.55', 'end'), (16, .42, 'now 0.42', 'start')])
    if sid == 'power-bmo':
        ys = BY['power-bmo']['reading']['series']; assert ys[-1] == 212
        return chart([i * .25 for i in range(len(ys))], ys, title='Building meter, last 2.5 h', unit='kW', color='#003262', ylo=150, yhi=250,
                     yticks=[150, 200, 250], xticks=[(0, '−2.25 h'), (1, '−1.25'), (2.25, 'now')], marks=[(2.25, 212, '212 kW', 'end-below')])
    if sid in ('fan-vibration', 'fan-alert'):
        ys = BY['fan-vibration']['reading']['series']; n = len(ys)
        assert n == 13 and ys[n - 5] == 1.2 and ys[-1] == 2.1
        return chart(list(range(n)), ys, title='Duct vibration, 13 weeks', unit='mm/s', color='#C81E1E', ylo=0, yhi=2.5, yticks=[0, 1, 2],
                     xticks=[(0, '−12 wk'), (4, '−8'), (8, '−4'), (12, 'now')], band=(8, 12, '+75 % in 4 weeks') if sid == 'fan-alert' else None,
                     marks=[(8, 1.2, '1.2', 'middle'), (12, 2.1, '2.1', 'end')])
    return ''
