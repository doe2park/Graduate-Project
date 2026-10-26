# Sensor deck: generates index.html from content.json + scenarios.py (live twin concept slides) + the extra slides below.
# PUBLIC (served by GitHub Pages from talks/sensor-deck/). Run from anywhere: python3 talks/sensor-deck/gen.py
# Image provenance: img/SOURCES.md. Fonts: Carlito, SIL OFL 1.1 (fonts/OFL.txt).
# Units: inches on a 10 x 5.625 in slide rendered at 1920 x 1080 px.
import json, html, math
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
HEADER = 'UC Berkeley · Civil & Environmental Engineering'
CJ = json.loads((ROOT / 'content.json').read_text())
CS = {s['id']: s for s in CJ['slides']}
def blk(sid, typ, n=0): return [b for b in CS[sid]['blocks'] if b['type'] == typ][n]

NAVY, GOLD, TEAL, CARD, MUTED, DARK, RED = '#003262', '#FDB515', '#087F8C', '#EEF3F8', '#5B7089', '#1F2A37', '#C4402F'
U = 192.0; PT = U / 72
def px(v): return f'{v*U:.1f}px'
def pos(x, y, w, h): return f'left:{px(x)};top:{px(y)};width:{px(w)};height:{px(h)}'
def e(s): return html.escape(s, quote=True)
def isize(p): return Image.open(ROOT / 'img' / p).size

from scenarios import SCENARIOS
CS.update({sc['id']: dict(sc, kind='figure', notes=sc['notes'] or CS[sc['id']]['notes']) for sc in SCENARIOS})
COURSE = 'CE170/278 Infrastructure Sensing, UC Berkeley (Prof. K. Soga)'
def lect_credit(lec, page, extra=''): return f'Figure: {COURSE}, Lecture {lec}, p. {page}' + (f' ({extra})' if extra else '')
EXTRA = {
 'fiber': dict(id='fiber', kind='figure', title='Fiber sensing: one cable, many sensors',
   subtitle='A laser pulse is sent down the fiber; light scattered back is timed to give a reading every metre or so',
   footnote='Concepts: ' + COURSE + '. Typical values; actual performance depends on the analyzer and cable. Sketches drawn for this deck.',
   notes='Fiber optic sensing turns one cable into thousands of sensors. The analyzer sends a laser pulse and times the light scattered back, so each slice of the cable becomes a reading. The type of scattering decides what is measured. Raman scattering gives temperature: that is DTS, about one reading per metre over kilometres, which is why it suits leak detection on pipes. Brillouin scattering, BOTDR or BOTDA, gives strain and temperature; in a building that means pipe, hanger or slab strain. Rayleigh scattering, read as phase, gives vibration at kilohertz rates: that is DAS, distributed acoustic sensing. Fiber Bragg gratings are different: they are written at chosen points, so they measure strain or temperature only there. The concepts come from the CE170/278 infrastructure sensing course.'),
 'ce278': dict(id='ce278', kind='figure', title='From the CE278 project: the DAS method a riser would use',
   subtitle='Own CE278 project: one minute of DAS on a roadside fiber. The same method on a riser would show water hammer and pump noise',
   footnote='Figures: own CE278 final project (UC Berkeley, fall 2025), DAS run 15:59:38–16:00:38, focused channels 1450–1650; course-provided DAS dataset.',
   notes='This is from my own CE278 final project, which used distributed acoustic sensing on a fiber along a road. The left plot is a waterfall: across is position along the fiber, one channel is roughly a metre, down is time over one minute, and colour is dynamic strain. Each vehicle shows up as a short burst at the channels it passes. On the right, the strain energy in a hundred channels is reduced to one curve, and every peak above the dashed threshold is a detected event. The road is only where the project data came from. The point for Grimes is the method: on a pipe riser, across becomes height along the riser, and water hammer, pump noise or the hiss of a leak would appear as stripes at the floor where they happen.'),
 'mems': dict(id='mems', kind='figure', title='Point sensors: MEMS vibration nodes',
   subtitle='Micro-electro-mechanical systems: silicon-made, small, cheap and low-power, the core of wireless vibration nodes',
   footnote=lect_credit('2-4', 3) + '; ' + lect_credit('2-4', 19) + '.',
   notes='The point sensors in the concepts are mostly MEMS. In a MEMS accelerometer a small proof mass on springs carries comb fingers between fixed electrodes; when it moves, the capacitance changes, and that gives acceleration. They are made thousands at a time on a silicon wafer, so they are small, cheap and low-power, and a battery node like the one in the photo, from the course lab, can carry one. It samples at about a kilohertz, so it records short bursts when triggered. In Grimes we would clamp nodes on pumps, fans, air-handler casings or pipe hangers, where rising vibration warns of bearing wear or loose supports. Figures are from the CE170/278 lectures.'),
 'wsn': dict(id='wsn', kind='figure', title='Wireless sensor networks: what limits them',
   subtitle='Sensor nodes report by radio to a gateway; battery, sampling rate and radio paths decide the design',
   footnote='Diagram drawn for this deck. Design points summarised from ' + COURSE + ', Lecture 2-4.',
   notes='A wireless sensor network is a set of nodes that measure and send data by radio to a gateway, and from there to the cloud. The diagram shows how it would sit in Grimes: battery nodes in the ceiling plenums, a gateway on each floor, and the campus network carrying the data to the building management system and the twin. Four things limit the design. Topology: a star is simple, a mesh relays around obstacles. Battery: a tilt node reading hourly on one D cell can in theory last twenty to twenty-five years, but a vibration node sampling at a kilohertz cannot run continuously, so it records short bursts when triggered. Radio: walls, floors, people and metal ducts weaken the signal. For Grimes that means nodes in the ceiling plenums, a gateway per floor, triggered vibration recordings, and IT approval for the radio.'),
}
CS.update(EXTRA)
ORDER = ['cover', 'part-1', 'bms', 'part-2', 'sensing', 'fiber', 'ce278', 'mems', 'wsn', 'pilot'] + [sc['id'] for sc in SCENARIOS] + ['thanks']
SLIDES = [CS[i] for i in ORDER]

# ---------------------------------------------------------------- primitives (same as v1)
def box(x, y, w, h, cls='card', extra=''):
    return f'<div class="{cls}" style="{pos(x,y,w,h)};border-radius:{0.06*min(w,h)*U:.1f}px;{extra}"></div>'

def text(x, y, w, h, paras, size=12, color=DARK, bold=False, align='left', anchor='top', cls='', extra='', gap=0):
    out = []
    for i, para in enumerate(paras):
        spans = ''.join(f'<span style="font-size:{o.get("size",size)*PT:.1f}px;color:{o.get("color",color)};font-weight:{700 if o.get("bold",bold) else 400};font-style:{"italic" if o.get("italic") else "normal"}">{e(t)}</span>' for t, o in para)
        mb = f'margin-bottom:{gap*PT:.1f}px' if gap and i < len(paras) - 1 else ''
        out.append(f'<p style="{mb}">{spans}</p>')
    jc = {'top': 'flex-start', 'middle': 'center', 'bottom': 'flex-end'}[anchor]
    return f'<div class="tx {cls}" style="{pos(x,y,w,h)};text-align:{align};justify-content:{jc};{extra}">{"".join(out)}</div>'

def P(s, **o): return [[(s, o)]]

def picture(p, x, y, w, h, caption=None, frame=False, align='center'):
    iw, ih = isize(p); cap = .3 if caption else 0
    s = min(w / iw, (h - cap) / ih); pw, ph = iw * s, ih * s
    px_ = x + (w - pw) / 2 if align == 'center' else x
    st = 'outline:3px solid #FDB515;outline-offset:-1px' if frame else 'outline:2px solid #C8D1DC;outline-offset:-1px'
    out = f'<img src="img/{p}" alt="" style="{pos(px_,y,pw,ph)};{st}">'
    if caption: out += text(px_, y + ph + .03, pw, .3, P(caption, size=9, color=MUTED, italic=True))
    return out, (px_, y, pw, ph)

def pill(x, y, w, h, label, bg=NAVY, color='#fff', size=11, bold=True, cls='pill'):
    return f'<div class="{cls}" style="{pos(x,y,w,h)};background:{bg};color:{color};font-size:{size*PT:.1f}px;border-radius:{0.2*h*U:.1f}px;font-weight:{700 if bold else 400}">{e(label)}</div>'

def card(x, y, w, h, head, body, navy=False, head_size=12, size=10.5, num=None, numcol=NAVY, middle=False):
    out = box(x, y, w, h, 'card navy' if navy else 'card'); tx = x + .14
    if num is not None:
        d = .42; out += f'<div class="circ" style="{pos(x+.14,y+.14,d,d)};background:{numcol};font-size:{15*PT:.1f}px">{e(str(num))}</div>'; tx = x + .68
    paras = [[(head, dict(bold=True, color=GOLD if navy else NAVY, size=head_size))]]
    if body: paras.append([(body, dict(size=size, color='#fff' if navy else DARK))])
    return out + text(tx, y + .06, x + w - tx - .1, h - .1, paras, anchor='middle' if middle else 'top', gap=2)

def qr(path, url, x, y, s, caption, cap_size=9):
    return (f'<a class="qra" href="{e(url)}" target="_blank" rel="noopener" style="{pos(x,y,s,s)}"><img src="img/{path}" alt="QR code: {e(caption)}" style="width:100%;height:100%"></a>'
            + f'<a class="qrcap" href="{e(url)}" target="_blank" rel="noopener" style="{pos(x-.4,y+s+.02,s+.8,.25)};font-size:{cap_size*PT:.1f}px">{e(caption)}</a>')

def chrome(s, n):
    out = (f'<div class="rule" style="left:0;top:0;width:1920px;height:{px(.079)}"></div><div class="rule gold" style="left:{px(8.5)};top:0;width:{px(1.5)};height:{px(.079)}"></div>')
    out += text(5.12, .115, 3.37, .18, P(HEADER, size=8, color=NAVY), align='right')
    out += f'<div class="marker" style="{pos(.5,.30,.079,.45)}"></div>'
    out += text(.73, .27, 8.6, .5, P(s['title'], size=21, color=NAVY, bold=True), anchor='middle')
    if s.get('subtitle'): out += text(.85, .86, 8.5, .26, P(s['subtitle'], size=10.5 if len(s['subtitle'])>110 else 12))
    if s.get('takeaway'): out += text(.85, 4.82, 8.4, .3, P(s['takeaway'], size=13, color=NAVY, bold=True))
    if s.get('footnote'): out += text(.85, 5.12, 8.0, .4, P(s['footnote'], size=7.5, color=MUTED))
    out += text(9.0, 5.3, .5, .2, P(str(n), size=9, color=MUTED), align='right')
    return out

def affiliation():
    return (f'<div class="rule" style="left:0;top:0;width:1920px;height:{px(.08)}"></div><div class="rule gold" style="left:{px(8.5)};top:0;width:{px(1.5)};height:{px(.08)}"></div>'
            + text(6.3, .35, 3.2, .6, [[('UNIVERSITY OF CALIFORNIA, BERKELEY', dict(bold=True, size=10, color=NAVY))], [('Civil & Environmental Engineering', dict(size=8.5, color=NAVY))]], extra=f'padding:{px(.05)} {px(.1)} 0'))


# ---------------------------------------------------------------- blocks
def bullets_card(x, y, w, h, head, items, head_size=13, size=11, tag=None, tagbg=RED, navy=False):
    out = box(x, y, w, h, 'card navy' if navy else 'card')
    out += text(x + .14, y + .08, w - .28, .34, P(head, size=head_size, bold=True, color=GOLD if navy else NAVY))
    lis = ''.join(f'<p style="padding-left:{.2*U:.0f}px;text-indent:-{.2*U:.0f}px;margin-bottom:{4*PT:.1f}px;font-size:{size*PT:.1f}px;color:{"#fff" if navy else DARK}"><span style="color:{GOLD if not navy else GOLD};font-weight:700">•&nbsp;&nbsp;</span>{e(t)}</p>' for t in items)
    out += f'<div class="tx" style="{pos(x+.14, y+.47, w-.28, h-.52)}">{lis}</div>'
    return out

def numsteps(x, y, w, h, steps, head_size=11, size=10.5, arrow=.2, compact=False):
    n = len(steps); sw = (w - arrow * (n - 1)) / n; out = ''
    for i, s_ in enumerate(steps):
        sx = x + i * (sw + arrow)
        out += box(sx, y, sw, h, 'card')
        out += f'<div class="circ" style="{pos(sx+.08,y+.08,.26 if compact else .34,.26 if compact else .34)};background:{NAVY};font-size:{(10 if compact else 13)*PT:.1f}px">{i+1}</div>'
        out += text(sx + .08, y + (.38 if compact else .5), sw - .16, h - (.4 if compact else .52), [[(s_['head'], dict(bold=True, size=head_size, color=NAVY))], [(s_['text'], dict(size=size))]], gap=3)
        if i < n - 1: out += f'<div class="arrow" style="{pos(sx+sw+.02,y+h/2-.1,arrow-.04,.2)}"></div>'
    return out

ICON_DAS = 'M2 12h3l2-5 3 10 3-8 2 6 2-3h5'
ICON_FBG = 'M2 12h20M7 8v8M10 8v8M13 8v8M16 8v8'
def _sd_types(): return json.loads((ROOT.parent.parent / 'twin' / 'sensor-demo.json').read_text())['types']
_T = _sd_types()
ROW_ICONS = [(_T['dts']['icon'], _T['dts']['color']), (_T['vibration']['icon'], _T['vibration']['color']), (ICON_DAS, '#0F766E'), (ICON_FBG, '#5B21B6'), (_T['iaq']['icon'], _T['iaq']['color'])]

def sensing_table():
    t = blk('sensing', 'table'); x, y = 1.5, 1.24; cw = [c['w'] for c in t['cols']]; rh, hh = t['row_h'], t['head_h']
    th = ''.join(f'<th style="width:{px(w)};font-size:{10*PT:.1f}px;text-align:left;padding:0 {.08*U:.0f}px">{e(c["head"])}</th>' for c, w in zip(t['cols'], cw))
    rows = ''
    for ri, r in enumerate(t['rows']):
        tds = ''
        for ci, cell in enumerate(r):
            st = f'font-size:{10*PT:.1f}px;padding:0 {.08*U:.0f}px'
            if ci == 0: st += f';font-weight:700;color:{NAVY}'
            if ci == 2: st += f';font-weight:700;color:{TEAL if ri < 2 else (DARK)}'
            tds += f'<td style="{st}">{e(cell)}</td>'
        bg = '#FFF3D6' if ri == 0 else ('#EEF3F8' if ri % 2 == 0 else '#fff')
        rows += f'<tr style="height:{px(rh)};background:{bg}">{tds}</tr>'
    out = (f'<table class="stbl" style="{pos(x,y,sum(cw),hh+rh*len(t["rows"]))};width:{px(sum(cw))};border-collapse:collapse;table-layout:fixed;box-shadow:0 4px 10px rgba(0,0,0,.18)">'
           f'<thead><tr style="height:{px(hh)};background:{NAVY};color:#fff">{th}</tr></thead><tbody>{rows}</tbody></table>')
    # a type icon beside each row (same icons as the live sensor layer; no stock photos)
    for i, (path, col) in enumerate(ROW_ICONS):
        d = .5; out += (f'<div class="circ" style="{pos(.8, y+hh+rh*i+(rh-d)/2, d, d)};background:{col}">'
                        f'<svg viewBox="0 0 24 24" width="{.3*U:.0f}" height="{.3*U:.0f}" aria-hidden="true"><path d="{e(path)}" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>')
    return out

# --- interactive twin concept slides (generic; scenarios in scenarios.py)
from twin_lib import build_twin, TWIN_JS, TWIN_CSS
SC = {sc['id']: sc for sc in SCENARIOS}

# Sensor type look (icon, colour, short label) shared with the viewer: ../../twin/sensor-demo.json
SDJ = json.loads((ROOT.parent.parent / 'twin' / 'sensor-demo.json').read_text())
SD_TYPE = {x['id']: x['type'] for x in SDJ['sensors']}
def sd_style(sid): return SDJ['types'][SD_TYPE[sid]]
def sd_icon(sid, px_):
    return (f'<svg viewBox="0 0 24 24" width="{px_:.0f}" height="{px_:.0f}" aria-hidden="true"><path d="{e(sd_style(sid)["icon"])}" fill="none" stroke="#fff" '
            'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')

def twin_slide(sc):
    for el in sc['elements']:
        if el.get('sid') in SD_TYPE: el['col'] = sd_style(el['sid'])['color']   # rows and cards use the viewer's type colour
    x, y, h = .55, 1.2, 3.3
    out, w = build_twin(sc, U, x, y, h)
    rx = x + w + .3; rw = 9.45 - rx; yy = 1.2; els = sc['elements']
    pitch = min(.66, 2.0 / len(els)); rowh = pitch - .04
    for el in els:
        k = el['k']
        out += (f'<div class="twrow card" data-m="{k}" data-sid="{e(el.get("sid",""))}" style="{pos(rx,yy,rw,rowh)};border-radius:{.06*rowh*U:.1f}px;cursor:pointer"></div>'
                f'<div class="circ" style="{pos(rx+.1,yy+(rowh-.32)/2,.32,.32)};background:{el["col"]};font-size:{13*PT:.1f}px;pointer-events:none">{sd_icon(el["sid"], .2*U) if el.get("sid") in SD_TYPE else k}</div>'
                + text(rx + .52, yy, rw - .6, rowh, [[(f'{k} · ' + el['title'], dict(bold=True, size=10.5, color=NAVY)), (('   ' + sd_style(el['sid'])['short']) if el.get('sid') in SD_TYPE else '', dict(size=8.5, color=el['col'], bold=True))], [(el['row'], dict(size=9))]], anchor='middle', extra='pointer-events:none'))
        yy += pitch
    if sc.get('legend'):
        lg = ''.join(f'<span style="display:inline-flex;align-items:center;margin-right:{.18*U:.0f}px"><i style="display:inline-block;width:{.13*U:.0f}px;height:{.13*U:.0f}px;background:{c};margin-right:{.06*U:.0f}px"></i>{n}</span>' for c, n in sc['legend'])
        out += f'<div class="tx" style="{pos(rx,yy+.02,rw,.22)};flex-direction:row;font-size:{9*PT:.1f}px;align-items:center">{lg}</div>'
    yy = 3.54
    out += numsteps(rx, yy, rw, 4.7 - yy, sc['steps'], head_size=10, size=9, arrow=.18, compact=True)
    return out

def fig(p, x, y, w, h, frame=False):
    return picture(p, x, y, w, h, frame=frame)[0]

def credit(x, y, w, t):
    return text(x, y, w, .2, P(t, size=7, color=MUTED, italic=True))

# native principle sketches for the fiber techniques (SVG, drawn here; no raster text)
def _sk(inner): return f'<svg viewBox="0 0 160 60" style="width:100%;height:100%" xmlns="http://www.w3.org/2000/svg">{inner}</svg>'
FIB = '<line x1="6" y1="48" x2="154" y2="48" stroke="#5B7089" stroke-width="3" stroke-linecap="round"/>'
PULSE = '<path d="M8 40h10l-4-4M18 40l-4 4" fill="none" stroke="#C4402F" stroke-width="2"/>'
SKETCH = {
 'DTS': _sk(FIB + PULSE + '<path d="M6 30 C40 30 50 30 62 28 C72 6 84 6 94 28 C108 31 130 31 154 31" fill="none" stroke="#E61E1E" stroke-width="2.6"/>'
            '<path d="M120 40h-10l4-4M110 40l4 4" fill="none" stroke="#1E50DC" stroke-width="2"/>'),
 'BOTDR / BOTDA': _sk(FIB.replace('stroke-width="3"', 'stroke-width="3" stroke-dasharray="0"') + PULSE +
            '<path d="M6 32H70V16H106V32H154" fill="none" stroke="#087F8C" stroke-width="2.6"/><path d="M70 48l-4 -4M106 48l4 -4" stroke="#087F8C" stroke-width="2"/>'),
 'DAS': _sk(''.join(f'<line x1="{12+i*12}" y1="6" x2="{12+i*12}" y2="54" stroke="#EEF3F8" stroke-width="1"/>' for i in range(12)) +
            '<path d="M20 8 L60 54M60 8 L100 54M104 8 L150 50" stroke="#C4402F" stroke-width="5" stroke-linecap="round" opacity=".8"/>'
            '<rect x="2" y="2" width="156" height="56" fill="none" stroke="#C8D1DC"/>'),
 'FBG': _sk(FIB + ''.join(f'<line x1="{70+i*4}" y1="42" x2="{70+i*4}" y2="54" stroke="#5B21B6" stroke-width="2"/>' for i in range(6)) +
            '<path d="M8 22h40" stroke="url(#rb)" stroke-width="6"/><defs><linearGradient id="rb"><stop offset="0" stop-color="#1E50DC"/><stop offset=".5" stop-color="#22C55E"/><stop offset="1" stop-color="#E61E1E"/></linearGradient></defs>'
            '<path d="M48 22h12l-4-4M60 22l-4 4" fill="none" stroke="#5B7089" stroke-width="2"/><path d="M118 28 L124 28 L127 8 L130 28 L154 28" fill="none" stroke="#22C55E" stroke-width="2.6"/>'
            '<path d="M110 22h-10l4-4M100 22l4 4" fill="none" stroke="#22C55E" stroke-width="2"/>'),
}
def fiber_slide():
    rows = [('DTS', 'Raman', 'Temperature', '~1 m over km; 0.1 °C', 'Leaks as warm or cold spots on pipes; radiant-loop faults'),
            ('BOTDR / BOTDA', 'Brillouin', 'Strain + temperature', '~1 m; slow (static)', 'Pipe and hanger strain; slab or riser movement'),
            ('DAS', 'Rayleigh (phase)', 'Vibration / sound', '1–10 m; up to kHz', 'Flow noise, water hammer, pumps along a riser'),
            ('FBG', 'Bragg gratings', 'Strain / temperature', 'Chosen points only', 'A few known hot spots: pump or AHU mounts')]
    cw = [1.35, 1.25, 1.25, 1.45, 2.3]; x, y, rh, hh = 1.85, 1.2, .56, .3
    heads = ['Technique', 'Scattering', 'Measures', 'Spacing / speed (typical)', 'Use in Grimes']
    th = ''.join(f'<th style="width:{px(w)};font-size:{10*PT:.1f}px;text-align:left;padding:0 {.08*U:.0f}px">{e(h)}</th>' for h, w in zip(heads, cw))
    trs = ''
    for i, r in enumerate(rows):
        tds = ''.join(f'<td style="font-size:{10.5*PT:.1f}px;padding:0 {.08*U:.0f}px;{"font-weight:700;color:"+NAVY if j==0 else ""}">{e(c)}</td>' for j, c in enumerate(r))
        trs += f'<tr style="height:{px(rh)};background:{"#FFF3D6" if i in (0, 2) else ("#EEF3F8" if i % 2 else "#fff")}">{tds}</tr>'
    out = (f'<table class="stbl" style="{pos(x,y,sum(cw),hh+rh*len(rows))};width:{px(sum(cw))};border-collapse:collapse;table-layout:fixed;box-shadow:0 4px 10px rgba(0,0,0,.18)">'
           f'<thead><tr style="height:{px(hh)};background:{NAVY};color:#fff">{th}</tr></thead><tbody>{trs}</tbody></table>')
    out += text(.55, y, 1.2, hh, P('How it works', size=9, bold=True, color=NAVY), anchor='middle')
    for i, (k, *_r) in enumerate(rows):
        out += f'<div style="{pos(.55, y+hh+rh*i+.04, 1.2, rh-.08)};background:#fff;outline:1px solid #C8D1DC;outline-offset:-1px" title="{e(k)} principle sketch">{SKETCH[k]}</div>'
    out += text(.55, y + hh + rh * 4 + .03, 8.9, .22, P('Sketches: DTS temperature bump at a leak · BOTDR shift where strained · DAS stripes in distance × time · FBG reflects one wavelength', size=8, color=MUTED, italic=True))
    out += box(.55, 4.08, 4.3, .64, 'card') + text(.7, 4.09, 4.0, .62, [[('Distributed', dict(bold=True, color=NAVY, size=11))], [('DTS, BOTDR, DAS: every metre of the cable is a sensor, so a leak can be anywhere along a pipe', dict(size=10))]], anchor='middle', gap=1)
    out += box(5.05, 4.08, 4.4, .64, 'card') + text(5.2, 4.09, 4.1, .62, [[('Point', dict(bold=True, color=NAVY, size=11))], [('FBG and MEMS nodes: precise, but only where they are placed', dict(size=10))]], anchor='middle', gap=1)
    return out

def ce278_slide():
    out = fig('ce278-das-waterfall.jpg', .45, 1.2, 3.75, 2.9, frame=True)
    out += fig('ce278-das-detection.jpg', 4.4, 1.2, 5.1, 2.0, frame=True)
    out += box(4.4, 3.5, 2.45, 1.25, 'card') + text(4.52, 3.53, 2.25, 1.2, [[('Reading a waterfall', dict(bold=True, color=NAVY, size=11))], [('Across: position along the fiber (channel ≈ 1 m). Down: time. Colour: dynamic strain. A vehicle = a short burst where it passes.', dict(size=9.5))]], gap=2)
    out += box(7.0, 3.5, 2.5, 1.25, 'card navy') + text(7.12, 3.53, 2.3, 1.2, [[('Same method on a Grimes riser', dict(bold=True, color=GOLD, size=11))], [('Across = height up the riser. Water hammer, pump noise or a leak’s hiss would show as stripes at the floor where they happen.', dict(size=9.5, color='#fff'))]], gap=2)
    out += text(.45, 4.15, 3.75, .5, P('Waterfall: 60 s of dynamic strain, channels 1450–1650', size=9, color=MUTED, italic=True))
    out += text(4.4, 3.21, 5.1, .22, P('Detection: RMS strain in channels 1500–1600; each × above the dashed threshold is an event', size=9, color=MUTED, italic=True))
    return out

def mems_slide():
    out = fig('l24-p3-mems-accelerometer.jpg', .55, 1.22, 2.75, 2.56, frame=True)
    out += credit(.55, 3.8, 2.8, 'MEMS accelerometer (comb design)')
    out += fig('l24-p19-wireless-node.jpg', 3.5, 1.22, 2.3, 2.56, frame=True)
    out += credit(3.5, 3.8, 2.4, 'Battery wireless sensor node (course lab hardware)')
    items = ['A proof mass on springs moves its comb fingers between fixed electrodes; the capacitance change gives acceleration',
             'Made thousands at a time on silicon: small, cheap, milliwatt power, so a node can run on a battery',
             'Records vibration level and spectrum; samples ~1 kHz, so it stores short bursts when triggered']
    out += bullets_card(6.0, 1.22, 3.45, 2.56, 'How it works', items, head_size=12, size=9.5)
    out += box(.55, 4.05, 8.9, .68, 'card navy') + text(.7, 4.07, 8.6, .64, [[('In Grimes', dict(bold=True, color=GOLD, size=11))], [('Clamp a node on a pump, fan, air-handler casing or pipe hanger: rising vibration warns of bearing wear or loose supports before failure (concepts 1 and 5).', dict(size=10, color='#fff'))]], anchor='middle', gap=1)
    return out

def wsn_svg():
    """native diagram: three floors, nodes in the ceiling plenums -> a gateway per floor -> campus network -> BMS / twin"""
    W, H = 1000, 560; out = []
    for i, (lvl, y) in enumerate([('Level 3', 40), ('Level 2', 210), ('Level 1', 380)]):
        out.append(f'<rect x="20" y="{y}" width="700" height="150" fill="#F6F8FB" stroke="#C8D1DC"/><rect x="20" y="{y}" width="700" height="40" fill="#EEF3F8"/>'
                   f'<text x="30" y="{y+140}" font-size="22" fill="#5B7089">{lvl}</text><text x="30" y="{y+27}" font-size="17" fill="#5B7089">ceiling plenum</text>')
        for j, nx in enumerate([200, 330, 460, 590]):
            out.append(f'<line x1="{nx}" y1="{y+20}" x2="660" y2="{y+20}" stroke="#087F8C" stroke-width="2" stroke-dasharray="5 6" opacity=".7"/>' if j == 0 else '')
            out.append(f'<circle cx="{nx}" cy="{y+20}" r="13" fill="#087F8C" stroke="#fff" stroke-width="3"/>')
        out.append(f'<rect x="645" y="{y+5}" width="56" height="30" rx="6" fill="#003262"/><text x="673" y="{y+26}" font-size="15" fill="#fff" text-anchor="middle" font-weight="700">GW</text>'
                   f'<path d="M701 {y+20} H790" stroke="#003262" stroke-width="3"/>')
    out.append('<path d="M790 60 V400" stroke="#003262" stroke-width="3"/><path d="M790 230 H830" stroke="#003262" stroke-width="3"/>'
               '<rect x="830" y="180" width="150" height="100" rx="10" fill="#003262"/><text x="905" y="222" font-size="19" fill="#FDB515" text-anchor="middle" font-weight="700">Campus</text>'
               '<text x="905" y="248" font-size="19" fill="#fff" text-anchor="middle">network</text>'
               '<path d="M905 280 V330" stroke="#003262" stroke-width="3"/><rect x="830" y="330" width="150" height="90" rx="10" fill="#FDB515"/>'
               '<text x="905" y="368" font-size="19" fill="#003262" text-anchor="middle" font-weight="700">BMS +</text><text x="905" y="394" font-size="19" fill="#003262" text-anchor="middle" font-weight="700">twin viewer</text>'
               '<circle cx="40" cy="545" r="9" fill="#087F8C"/><text x="56" y="551" font-size="17" fill="#1F2A37">battery sensor node</text>'
               '<rect x="250" y="533" width="34" height="22" rx="4" fill="#003262"/><text x="294" y="551" font-size="17" fill="#1F2A37">gateway (one per floor)</text>'
               '<line x1="520" y1="544" x2="560" y2="544" stroke="#087F8C" stroke-width="2" stroke-dasharray="5 6"/><text x="570" y="551" font-size="17" fill="#1F2A37">radio link</text>')
    return f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:100%" xmlns="http://www.w3.org/2000/svg" font-family="Calibri,Carlito,Arial,sans-serif">{"".join(out)}</svg>'

def wsn_slide():
    out = f'<div style="{pos(.45,1.2,5.3,2.97)};background:#fff;outline:2px solid #C8D1DC;outline-offset:-1px">{wsn_svg()}</div>'
    out += credit(.45, 4.2, 5.3, 'How a wireless network would sit in Grimes (illustrative layout, not a design)')
    items = ['Topology: star is simple; mesh relays around obstacles',
             'Battery: an hourly tilt node on one D-cell ≈ 20–25 years (theory); a 1 kHz vibration node records 5–25 s bursts when triggered',
             'Sampling: slow for temperature, humidity, CO2; fast for acceleration and sound',
             'Radio: walls, floors, people and metal ducts block the signal']
    out += bullets_card(5.95, 1.2, 3.5, 2.55, 'Design limits (CE170/278)', items, head_size=12, size=9.5)
    out += box(5.95, 3.88, 3.5, .82, 'card navy') + text(6.08, 3.9, 3.3, .78, [[('For Grimes', dict(bold=True, color=GOLD, size=11))], [('Nodes in ceiling plenums, a gateway per floor, triggered vibration recordings, IT approval for the radio', dict(size=9.5, color='#fff'))]], anchor='middle', gap=1)
    return out

def block(b):
    return b

def divider(s):
    out = f'<div style="{pos(0,0,10,5.625)};background:#F6F8FB"></div>'
    out += chrome_bars()
    out += text(.9, 1.0, 8.2, 1.7, P(s['number'], size=96, bold=True, color=GOLD), anchor='bottom')
    out += f'<div class="marker flat" style="{pos(.98,2.85,1.2,.06)}"></div>'
    out += text(.9, 3.0, 8.2, .8, P(s['title'], size=37.5, bold=True, color=NAVY))
    out += text(.9, 3.8, 7.6, .8, P(s['subtitle'], size=16.5, color=MUTED))
    out += text(.9, 4.9, 4, .3, P('SECTION ' + s['number'], size=9, bold=True, color=NAVY))
    return out

DIV_CSS = ''

def chrome_bars():
    return (f'<div class="rule" style="left:0;top:0;width:1920px;height:{px(.079)}"></div><div class="rule gold" style="left:{px(8.5)};top:0;width:{px(1.5)};height:{px(.079)}"></div>'
            f'<div class="marker" style="{pos(.5,1.7,.079,1.9)}"></div>')

def bms(s):
    bl = [b for b in s['blocks'] if b['type'] == 'bullets']; ask = blk('bms', 'text')
    out = bullets_card(.55, 1.2, 4.35, 2.85, 'Today: utility meters (BMO)', bl[0]['items'], size=11.5)
    out += pill(.69, 3.62, 1.5, .26, 'In place today', bg=TEAL, size=9)
    out += bullets_card(5.1, 1.2, 4.35, 2.85, 'Likely: building automation (WebCTRL / BACnet)', bl[1]['items'], head_size=12, size=10.5)
    out += pill(5.24, 3.62, 1.95, .26, 'NOT confirmed for Grimes', bg=RED, size=9)
    out += box(.55, 4.15, 8.9, .72, 'card navy')
    out += text(.7, 4.15, 1.9, .72, P('What we need', size=17, bold=True, color=GOLD), anchor='middle')
    out += text(2.55, 4.15, 6.8, .72, P(ask['text'], size=12.5, color='#fff'), anchor='middle')
    return out

def pilot(s):
    st = blk('pilot', 'numsteps')['steps']; bl = [b for b in s['blocks'] if b['type'] == 'bullets']
    out = numsteps(.55, 1.2, 8.9, 1.55, st, head_size=12, size=10.5, arrow=.2)
    out += bullets_card(.55, 2.95, 4.35, 1.65, bl[0]['head'], bl[0]['items'], size=11)
    out += bullets_card(5.1, 2.95, 4.35, 1.65, bl[1]['head'], bl[1]['items'], size=11)
    return out

def thanks_extra():
    out = ''
    qs = ['Can Facilities share building automation (BAS) data?', 'Is the riser pilot worth proposing to Prof. Soga’s lab?']
    for i, q in enumerate(qs):
        out += box(1.2 + 3.9 * i, 3.35, 3.7, .9, 'card')
        out += text(1.35 + 3.9 * i, 3.35, 3.4, .9, [[('QUESTION ' + str(i + 1), dict(bold=True, size=8, color=TEAL))], [(q, dict(size=12.5, color=NAVY, bold=True))]], anchor='middle', gap=2)
    return out

def slide(s, n):
    body = ''; k = s['kind']
    if k == 'cover':
        body += affiliation()
        body += f'<div class="marker flat" style="{pos(.5,1.1,.6,.06)}"></div>'
        body += text(.5, 1.306, 8.611, 1.458, [[(l, dict(bold=True, size=37.5, color=NAVY))] for l in s['title'].split('\n')], extra=f'padding:{px(.1)} {px(.1)} 0')
        body += text(.5, 2.917, 8.611, .805, [[(s['subtitle'], dict(size=16.5, color=NAVY))], [('October 29, 2026', dict(size=16.5, color=NAVY))]], extra=f'padding:{px(.1)} {px(.1)} 0')
        body += text(.5, 3.85, 3.0, .9, [[('PRESENTER', dict(bold=True, size=8, color=NAVY))], [('Yoonsung', dict(bold=True, size=14, color='#333333'))]], extra=f'padding:{px(.05)} {px(.1)} 0')
    elif k == 'divider':
        body += divider(s)
    elif k == 'thanks':
        body += affiliation()
        body += text(1.389, .95, 7.222, .945, P(s['title'], bold=True, size=37.5, color=NAVY), align='center', extra=f'padding:{px(.1)} {px(.1)} 0')
        body += text(1.167, 2.05, 7.667, .6, [[('Yoonsung', dict(size=16.5, color=NAVY))]], align='center', extra=f'padding:{px(.1)} {px(.1)} 0')
        body += thanks_extra()
    else:
        sid = s['id']; body += chrome(s, n)
        if sid == 'bms': body += bms(s)
        elif sid == 'sensing': body += sensing_table()
        elif sid == 'pilot': body += pilot(s)
        elif sid == 'fiber': body += fiber_slide()
        elif sid == 'ce278': body += ce278_slide()
        elif sid == 'mems': body += mems_slide()
        elif sid == 'wsn': body += wsn_slide()
        elif sid in SC: body += twin_slide(SC[sid])
    return f'<section class="slide" id="{s["id"]}">{body}</section>'

slides_html = '\n'.join(slide(s, i + 1) for i, s in enumerate(SLIDES))
notes = json.dumps([s.get('notes', '') for s in SLIDES], ensure_ascii=False)
css = (ROOT / 'deck.css').read_text() + TWIN_CSS + DIV_CSS
js = (ROOT / 'deck.js').read_text()
doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Building Data and Sensing for the Grimes Twin</title>
<style>{css}</style></head><body>
<div id="viewport"><div id="stage">
{slides_html}
</div></div>
<div id="notes" hidden><div id="notes-text"></div></div>
<div id="bar"><button id="prev" aria-label="Previous slide">‹</button><span id="count"></span><button id="next" aria-label="Next slide">›</button><span class="hint">←/→ slides · F fullscreen · N notes · concept slides: drag the live view · hover a numbered card to point at its sensor</span></div>
<script>const NOTES={notes};
{js}
{TWIN_JS}</script></body></html>"""
(ROOT / 'index.html').write_text(doc)
print('ok', len(doc), 'slides', len(SLIDES))
