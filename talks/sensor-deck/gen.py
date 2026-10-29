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
# Main-talk parts, shown as a tag above each slide title (no divider slides): label, background, text colour.
PARTS = {'dashboard': ('DASHBOARD · campus energy', TEAL, '#fff', 'DASHBOARD'), 'grimes': ('GRIMES · digital twin', GOLD, NAVY, 'GRIMES')}
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
  'ready': dict(id='ready', kind='figure', title='Ready for real sensors',
   subtitle='One feed format, each source tied to a BIM element; real feeds need an adapter, verified mapping and commissioning',
   footnote='Today every value in the twin’s sensor layer is simulated (labelled “Simulated”); no sensor is installed. Brick class names are candidates, not yet verified. Headset and dashboard connections are proposed, not demonstrated.',
   notes='This slide is about what happens after the demo. Whatever the source is, a building automation point, a campus meter (BMO now; SkySpark suggested by Facilities, not decided), a wireless gateway or a fiber analyzer, a small adapter turns it into one common feed format: sensor, time, value, unit, quality and source. A registry ties each sensor to its BIM element by the element GUID, with a Brick class, its units and its alert rule. The Lens, the headset and the dashboard read only that feed and registry. Today the feed is a simulator that runs in the browser and is clearly labelled Simulated. A real feed is not a simple switch: it needs an adapter, a verified mapping to the right equipment and commissioning. Once those are done it would appear with a Live badge, under the same rules for missing and stale data. The headset and dashboard connections on the right are proposed, not yet demonstrated.'),
}
EXTRA.update({
 'week-energy': dict(id='week-energy', kind='figure', title='Campus energy data: possible move to SkySpark', sub_size=15, part='dashboard',
   subtitle='Suggested by Facilities; nothing decided yet',
   footnote='BMO values shown for reference; no SkySpark access yet.',
   notes='The first part is the campus energy dashboard. Facilities told us this week that BMO, which the dashboard reads today, is no longer their source of truth: the platform is outdated and new meters cannot be added. They suggested SkySpark, which they actively manage, as a possible source, and mentioned an intake form so students could pull hourly data themselves. Nothing is decided yet. On the class side, the request is hourly electricity data, a target of twelve months so winter and summer are both covered. One student group wants to do an energy balance of the main campus, so coverage matters. The dashboard today covers 37 buildings from BMO. Some main-campus buildings are not listed yet, for example the Valley Life Sciences Building, and some buildings may be fed or sub-metered from a neighbour. The requested interval and period come from the utility side of the email thread on October 26. What we need: a decision on SkySpark access, or the intake form, before the student presentations in the week of November 16; a confirmed interval, period and building list; and which buildings are fed from others. If access is approved, the dashboard would switch its meter source to SkySpark. Until then, the dashboard values from BMO are shown for reference only.'),
 'week-facilities': dict(id='week-facilities', kind='figure', title='Facilities follow-up: three requests', sub_size=15, part='grimes',
   subtitle='Asked at the Oct 22 meeting; no decision yet',
   notes='The second part is the Grimes twin. First, the follow-up from our meeting with building operations on October 22. We asked for three things. One, floor plans or building data for older campus buildings, which usually have no BIM: plans let us place the 360 captures and build a basic model. Two, whether sensors can be installed, so readings link to a room or a system instead of the whole-building meter; that means locations, approval, an installer and data access. Three, permission to film with a drone, for the exterior and roof, to complete the model; that means the approval process, forms and lead time. As of October 26 none has a decision yet. The follow-up email with the final list of requests goes out after today\'s meeting, once the final comments are collected. What we need is an owner and an approval process for each request, and a first candidate building.'),
 'week-quest': dict(id='week-quest', kind='figure', title='Quest 3: expected mixed-reality benefits', part='grimes',
   notes='Next, the headset, and this is what we expect, not a result: we have not received the lab Quest 3 yet, so nothing has run on it. The picture is a concept mockup: our own twin view of the Level 1 ceiling from the public May 6 capture, with the BIM overlay and the simulated demo sensors; it is not a Quest 3 capture. With mixed reality you see the real surroundings through the headset. That means you can actually walk around inside the building without tripping or falling, while the BIM services hidden above the ceiling, the pipes and ducts, appear in place, and sensor readings appear at the element they belong to. Today those readings are simulated. The Quest 3 matters because its passthrough is in colour and it builds a room mesh; we expect that to help, but it is to be evaluated. How we would check it: you align the model by touching four landmarks, column faces and wall corners, plus the floor; the page fits a rotation and a shift and reports the error. Two Level 1 areas are prepared, the auditorium foyer with its open ceiling and the east entrance. Then we check real sprinkler heads and a diffuser against their BIM positions, in centimetres. The proposed test targets are three centimetres RMS and five at worst; they are targets to test, not results. We compare real ceiling devices against their BIM positions separately from the landmark fit, and re-check after a ten metre walk to see drift. The protocol takes about ten minutes, and the log is saved on the headset. The landmarks are BIM-derived candidates, not surveyed points, and the RMS measures how consistently the landmarks were touched, not survey accuracy. Also ready: the VR controls were redesigned after the first headset try, with point and go, a visible laser and a five-button menu; and the black screen we saw on a Quest 2 has a fix that passes an emulated headset test only, not confirmed on hardware. So far everything is tested on the desktop and an emulated headset only. What we need: the headset this week, a quiet time in the Level 1 foyer, and after a pass, permission to put it on the public link.'),
 'week-asks': dict(id='week-asks', kind='figure', title='What we need',
   subtitle='Decisions requested, in order of urgency; tagged by part',
   footnote='Asks 1 and 2 go to Facilities in the follow-up email after this meeting; ask 3 is within the lab. Roles only; no dates agreed.',
   notes='To sum up, four asks in order of urgency, tagged by part. One, for the dashboard: a decision on SkySpark meter access for the main campus, hourly, with a twelve month target, before the November 16 presentations. Two, for Grimes: an owner and a process for floor plans, sensor installs and drone filming, plus one location, an owner and a short window for the first test install. Three, the lab Quest 3 and a quiet time in the Grimes foyer this week. Four, later, a read-only building automation trend export and point list, tagged so points link to BIM elements, once the first three are moving. Asks one and two go to Facilities in the follow-up email after this meeting; ask three is within the lab.'),
 'open-ceiling': dict(id='open-ceiling', kind='figure', title='Oct 18: a leak repair opened this ceiling',
   subtitle='Level 1 entrance by the auditorium doors: our 360° walk passed under the open tiles',
   footnote='Oct 18 capture, ceiling only, no people. Model overlay uses a provisional alignment (not surveyed); offsets are read from screenshots and are not survey measurements. Pipes deeper in the plenum were too dark to check.',
   notes='Before the concepts, a real case. On October 18 the ceiling at the Level 1 entrance was open for a leak repair, and our 360 walk passed right under it. On the right is the same view with the building model on top. The supply diffuser, the flex duct and the sprinkler head look visually close to the model in this view. The fire-alarm device in the tile appears about 0.7 metres from where the model puts it. That is an apparent mismatch in a screenshot with a provisional alignment, so it has to be verified on site before we say the device was installed away from the drawings. Two lessons for sensors. First, today a leak is found when water shows on a tile, and the ceiling has to be opened to find the source. Second, if we attach sensors to BIM elements, the model has to match what is installed, and an opening like this is the chance to check it on site. The next slides show how sensors in the twin would point to the pipe before anyone opens a tile.'),
 'test-installs': dict(id='test-installs', kind='figure', title='Five test installs: where, what, and what we would learn',
   subtitle='Each one is a small trial on a real BIM element above a Level 1 ceiling; the next five slides show how each would look in the twin',
   takeaway='Ask: one location, an owner and a short install window for a first test',
   footnote='Concept stage: no sensor is installed. Scale is indicative only; no costs have been estimated. Locations are BIM elements seen in the public May 6 capture.',
   notes='Here is the proposal in one table. Five small test installs, each on a real BIM element above a Level 1 ceiling, each with a narrow question. One: can a controlled temperature change along the sprinkler main be detected by a fiber cable and mapped to the right BIM pipe segment, with a wetness sensor below checking for water. Two: compare measured airflow in a supply branch with a verified design value, and its trend with one representative room reading. Three: a wetness sensor below a pipe coupling, to test detection of water at that fitting; a flow meter is only a later option on a verified supply branch. Four: after confirming the circuit, a power meter to measure the load profile of the VAV terminal units and compare operating and idle periods. Five: a vibration node on a fan-fed duct, to test whether vibration changes reproducibly with the fan operating state. Nothing is installed and we have not estimated costs. What we need is one location, an owner, and a short window to try the first one.'),
 'part-A': dict(id='part-A', kind='divider', number='A', label='APPENDIX', title='Appendix: data feeds and sensing',
   subtitle='Ready for real sensors, then sensing options, fiber, the CE278 DAS example, MEMS nodes and wireless networks',
   notes='Background slides, for questions. First, how real data feeds would plug into the twin; then the survey of sensing options for Grimes and how the sensors work.'),
})
CS.update(EXTRA)
for _sid in ['bms', 'open-ceiling', 'test-installs', 'pilot'] + [sc['id'] for sc in SCENARIOS]: CS[_sid] = dict(CS[_sid], part='grimes')
CS['thanks'] = dict(CS['thanks'], notes='Thank you. Three questions to leave with you: can we get a decision on SkySpark meter access before the November 16 presentations, can we run the mixed-reality test in the Grimes foyer with the Quest 3 this week, and where could we try a first test install?')
CS['pilot'] = dict(CS['pilot'], title='First test and its success criterion: fiber temperature on Pipe219763')
_EFFECT = {'twin-concept': 'Test: whether a controlled temperature change along Pipe219763 can be detected and mapped to the right BIM pipe segment; a separate wetness sensor below checks for water.',
           'twin-hvac': 'Test: compare measured airflow in branch 401233 with a verified design value, and compare its trend with one representative room temperature / CO2 reading.',
           'twin-water': 'Test: place a leak (wetness) sensor below coupling 423698 to test detection of water at this fitting. A flow meter is only a later option on a verified supply branch.',
           'twin-power': 'Test: after confirming the circuit, measure its load profile with a power meter (current + voltage) and compare operating and idle periods.',
           'twin-fan': 'Test: whether vibration on duct 399665 changes reproducibly with the upstream fan’s operating state.'}
for _k, _t in _EFFECT.items(): CS[_k] = dict(CS[_k], notes=_t + ' ' + CS[_k]['notes'])
# Main talk: 15 slides in two parts shown by a header tag (Dashboard, then Grimes), no section dividers; 'What we need' closes.
# bms sits after the Facilities / Quest updates and directly before the open ceiling: it starts the sensing story
# (what Grimes measures today -> where sensors would add to it). Appendix: one divider, then backup slides.
ORDER = ['cover', 'week-energy', 'week-facilities', 'week-quest', 'bms', 'open-ceiling', 'test-installs'] + [sc['id'] for sc in SCENARIOS] + ['pilot', 'week-asks', 'thanks', 'part-A', 'ready', 'sensing', 'fiber', 'ce278', 'mems', 'wsn']
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
    if s.get('part'): out += part_pill(.73, .1, s['part'], w=1.75, h=.2, size=8.5)
    out += text(.73, .27, 8.6, .5, P(s['title'], size=21, color=NAVY, bold=True), anchor='middle')
    if s.get('subtitle'): out += text(.85, .86, 8.5, .26, P(s['subtitle'], size=s.get('sub_size') or (10.5 if len(s['subtitle'])>110 else 12)))
    if s.get('takeaway'): out += text(.85, 4.82, 8.4, .3, P(s['takeaway'], size=13, color=NAVY, bold=True))
    if s.get('footnote'): out += text(.85, 5.12, 8.0, .4, P(s['footnote'], size=8.5, color=MUTED))
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
def _sd_types(): return json.loads((ROOT.parent.parent / 'twin' / 'sensors' / 'registry.json').read_text())['types']
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
from twin_lib import build_twin, callouts, TWIN_JS, TWIN_CSS
from charts import chart_for
SC = {sc['id']: sc for sc in SCENARIOS}

# Sensor type look (icon, colour, short label) shared with the viewer: ../../twin/sensors/registry.json
SDJ = json.loads((ROOT.parent.parent / 'twin' / 'sensors' / 'registry.json').read_text())
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
    pitch = min(.6, 1.9 / len(els)); rowh = pitch - .04
    for el in els:
        k = el['k']
        out += (f'<div class="twrow card" data-m="{k}" data-sid="{e(el.get("sid",""))}" style="{pos(rx,yy,rw,rowh)};border-radius:{.06*rowh*U:.1f}px;cursor:pointer"></div>'
                f'<div class="circ" style="{pos(rx+.1,yy+(rowh-.32)/2,.32,.32)};background:{el["col"]};font-size:{13*PT:.1f}px;pointer-events:none">{sd_icon(el["sid"], .2*U) if el.get("sid") in SD_TYPE else k}</div>'
                + text(rx + .52, yy, rw - .6, rowh, [[(f'{k} · ' + el['title'], dict(bold=True, size=10.5, color=NAVY)), (('   ' + sd_style(el['sid'])['short']) if el.get('sid') in SD_TYPE else '', dict(size=8.5, color=el['col'], bold=True))], [(el['row'], dict(size=9))]], anchor='middle', extra='pointer-events:none'))
        yy += pitch
    if sc.get('legend'):
        lg = ''.join(f'<span style="display:inline-flex;align-items:center;margin-right:{.18*U:.0f}px"><i style="display:inline-block;width:{.13*U:.0f}px;height:{.13*U:.0f}px;background:{c};margin-right:{.06*U:.0f}px"></i>{n}</span>' for c, n in sc['legend'])
        out += f'<div class="tx" style="{pos(rx,yy+.0,rw,.22)};flex-direction:row;font-size:{9*PT:.1f}px;align-items:center">{lg}</div>'
        yy += .26
    sy = 3.54
    out += '<div class="twsteps">' + numsteps(rx, sy, rw, 4.7 - sy, sc['steps'], head_size=10, size=9, arrow=.18, compact=True) + '</div>'
    # selected sensor: a callout card beside its marker / live pin, placed clear of the other markers and the text (place.js)
    out += callouts(sc, U, x, y, h, chart_for)
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

def ready_svg():
    """native diagram: sources -> adapters -> common feed -> registry (sensor <-> BIM GUID, Brick) -> Lens / headset / dashboard"""
    W, H = 1700, 560; o = []
    def bx(x, y, w, h, fill, title, sub=None, tc='#fff', sc='#DCE6F0'):
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}"/>'
                 f'<text x="{x+w/2}" y="{y+(h/2 if not sub else h/2-8)}" font-size="26" font-weight="700" fill="{tc}" text-anchor="middle" dominant-baseline="middle">{title}</text>')
        if sub: o.append(f'<text x="{x+w/2}" y="{y+h/2+22}" font-size="19" fill="{sc}" text-anchor="middle" dominant-baseline="middle">{sub}</text>')
    def ar(x1, y1, x2, y2): o.append(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="#FDB515" stroke-width="5" marker-end="url(#ah)"/>')
    o.append('<defs><marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L10 5L0 10z" fill="#FDB515"/></marker></defs>')
    srcs = [('BAS / BACnet', 'Facilities points'), ('Meters', 'BMO now; SkySpark not decided'), ('Wireless gateway', 'MEMS nodes'), ('Fiber analyzer', 'DTS / DAS')]
    for i, (t, sb) in enumerate(srcs):
        y = 20 + i * 132; bx(20, y, 300, 108, '#EEF3F8', t, sb, tc='#003262', sc='#5B7089'); ar(325, y + 54, 395, y + 54)
    o.append('<rect x="400" y="20" width="230" height="504" rx="14" fill="#087F8C"/>'
             '<text x="515" y="250" font-size="27" font-weight="700" fill="#fff" text-anchor="middle">Adapters</text>'
             '<text x="515" y="290" font-size="19" fill="#DFF5F3" text-anchor="middle">one per source</text>')
    ar(635, 272, 705, 272)
    bx(710, 172, 290, 200, '#003262', 'Common feed', 'id · time · value · unit', sc='#C9D7E6')
    o.append('<text x="855" y="330" font-size="19" fill="#C9D7E6" text-anchor="middle">quality · source</text>')
    ar(1005, 272, 1075, 272)
    bx(1080, 172, 290, 200, '#003262', 'Registry', 'sensor ↔ BIM GUID', sc='#C9D7E6')
    o.append('<text x="1225" y="330" font-size="19" fill="#C9D7E6" text-anchor="middle">Brick class · units · rules</text>')
    for i, (t, sb) in enumerate([('Lens', 'on the scan'), ('Headset', 'Quest MR'), ('Dashboard', 'campus energy')]):
        y = 60 + i * 150; ar(1375, 272, 1440, y + 54); bx(1445, y, 235, 108, '#FDB515', t, sb, tc='#003262', sc='#003262')
    return f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:100%" xmlns="http://www.w3.org/2000/svg" font-family="Calibri,Carlito,Arial,sans-serif">{"".join(o)}</svg>'

def ready_slide():
    out = f'<div style="{pos(.55,1.12,8.9,2.62)}">{ready_svg()}</div>'
    out += box(.55, 3.82, 8.9, .38, 'card') + text(.7, 3.82, 8.6, .38, [[('Today: ', dict(bold=True, color=TEAL, size=11)), ('simulated feed in the browser, labelled “Simulated”', dict(size=11)), ('   →   Next: ', dict(bold=True, color=NAVY, size=11)), ('adapter + verified mapping + commissioning → “Live”', dict(size=11))]], anchor='middle')
    items = ['Registry: 17 demo entries (13 sensor/source entries + 4 derived indicators), tied to real BIM element GUIDs, with units, rules and Brick classes',
             'One feed format and shared rules: missing is never zero, stale after 3 intervals, units must match',
             'Adapters: simulator live today; BMS, meter, gateway and fiber stubs ready to be filled in (a SkySpark adapter only if access is approved)']
    out += text(.6, 4.28, 8.8, .7, [[('✓ ', dict(bold=True, color=TEAL, size=10)), (t, dict(size=10))] for t in items], gap=0)
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
    out += text(.9, 4.9, 4, .3, P(s.get('label') or 'SECTION ' + s['number'], size=9, bold=True, color=NAVY))
    return out

DIV_CSS = ''

def chrome_bars():
    return (f'<div class="rule" style="left:0;top:0;width:1920px;height:{px(.079)}"></div><div class="rule gold" style="left:{px(8.5)};top:0;width:{px(1.5)};height:{px(.079)}"></div>'
            f'<div class="marker" style="{pos(.5,1.7,.079,1.9)}"></div>')

def big_card(x, y, w, h, head, body, num=None, head_size=24, size=18, navy=False):
    """Large-type card for the short 'this week' slides: optional number, one bold head, one short line."""
    out = box(x, y, w, h, 'card navy' if navy else 'card')
    paras = [[(head, dict(bold=True, size=head_size, color=GOLD if navy else NAVY))]]
    if body: paras.append([(body, dict(size=size, color='#fff' if navy else DARK))])
    if num is None: return out + text(x + .22, y + .45, w - .4, h - .55, paras, gap=8)
    d = .5; out += f'<div class="circ" style="{pos(x+.22,y+.25,d,d)};background:{NAVY};font-size:{18*PT:.1f}px">{e(str(num))}</div>'
    return out + text(x + .22, y + .85, w - .4, h - .95, paras, gap=8)

def bms(s):
    bl = [b for b in s['blocks'] if b['type'] == 'bullets']; ask = blk('bms', 'text'); out = ''
    for x, b in ((.55, bl[0]), (5.1, bl[1])):
        out += box(x, 1.25, 4.35, 2.7, 'card')
        out += text(x + .2, 1.38, 4.0, .45, P(b['head'], size=b['head_size'], bold=True, color=NAVY))
        out += text(x + .2, 1.8, 4.0, .3, P(b['tag'], size=13, color=MUTED))
        lis = ''.join(f'<p style="padding-left:{.25*U:.0f}px;text-indent:-{.25*U:.0f}px;margin-bottom:{6*PT:.1f}px;font-size:{b["size"]*PT:.1f}px;color:{DARK}"><span style="color:{GOLD};font-weight:700">•&nbsp;&nbsp;</span>{e(t)}</p>' for t in b['items'])
        out += f'<div class="tx" style="{pos(x + .2, 2.2, 4.0, 1.2)}">{lis}</div>'
    out += pill(5.3, 3.47, 2.6, .34, 'NOT confirmed for Grimes', bg=RED, size=12)
    return out + ask_bar(ask['text'], size=15)

def pilot(s):
    st = blk('pilot', 'numsteps')['steps']; bl = [b for b in s['blocks'] if b['type'] == 'bullets']
    out = numsteps(.55, 1.2, 8.9, 1.55, st, head_size=12, size=10.5, arrow=.2)
    out += bullets_card(.55, 2.95, 4.35, 1.65, bl[0]['head'], bl[0]['items'], size=11)
    out += bullets_card(5.1, 2.95, 4.35, 1.65, bl[1]['head'], bl[1]['items'], size=11)
    return out

def open_ceiling():
    out = fig('oct18-ceiling-open-photo.jpg', .55, 1.17, 3.3, 2.58)
    out += fig('oct18-ceiling-open-model.jpg', 4.0, 1.17, 3.3, 2.58, frame=True)
    out += pill(.65, 1.27, 1.6, .26, 'Photo · ceiling open', size=9)
    out += pill(5.6, 1.27, 1.6, .26, 'Same view + model', size=9)
    out += text(.55, 3.78, 6.75, .3, P('1 supply diffuser · 2 flex duct · 3 sprinkler head · 4 fire-alarm device (model position)', size=10, color=MUTED), anchor='middle')
    out += card(7.45, 1.17, 2.0, 1.12, '1–3  Visually close', 'Diffuser, flex duct and sprinkler head look close in this view', head_size=11.5, size=9.5)
    out += card(7.45, 2.39, 2.0, 1.12, '4  Apparent mismatch', '~0.7 m in this view: verify on site', head_size=11.5, size=9.5)
    out += card(7.45, 3.61, 2.0, .44, 'As-built check before sensors', '', head_size=9.5, middle=True)
    out += box(.55, 4.15, 8.9, .72, 'card navy')
    out += text(.7, 4.15, 1.9, .72, P('With sensors', size=17, bold=True, color=GOLD), anchor='middle')
    return out + text(2.55, 4.15, 6.8, .72, P('A sensor could point to the BIM pipe before anyone opens a tile; the model must match what is installed. Next: five small test installs and what each would show', size=12, color='#fff'), anchor='middle')

def ask_bar(t, y=4.15, h=.72, size=12):
    out = box(.55, y, 8.9, h, 'card navy')
    out += text(.7, y, 1.9, h, P('What we need', size=17, bold=True, color=GOLD), anchor='middle')
    return out + text(2.55, y, 6.8, h, P(t, size=size, color='#fff'), anchor='middle')

def week_energy():
    cards = [('BMO is outdated', 'Cannot add meters; SkySpark suggested'),
             ('Hourly, 12 months', 'Class need: winter and summer'),
             ('37 buildings today', 'Some main-campus buildings missing')]
    out = ''.join(big_card(.55 + i * 3.0, 1.3, 2.9, 2.6, h, b, head_size=22) for i, (h, b) in enumerate(cards))
    return out + ask_bar('A decision on SkySpark access before the Nov 16 student presentations', size=16)

def week_facilities():
    reqs = [('Floor plans', 'Older buildings without BIM'), ('Sensor installs', 'Readings per room or system'), ('Drone filming', 'Exterior and roof')]
    out = ''.join(big_card(.55 + i * 3.0, 1.25, 2.9, 2.2, h, b, num=i + 1, size=17) for i, (h, b) in enumerate(reqs))
    out += box(.55, 3.55, 8.9, .5, 'card')
    out += text(.75, 3.55, 8.5, .5, P('Follow-up email with the final request list goes out after today’s meeting', size=15, bold=True, color=TEAL), anchor='middle')
    return out + ask_bar('Owner + approval process per request; a first candidate building', size=15)

def week_quest():
    # Left ~55 %: concept mockup of the mixed-reality view (own screenshot of the public twin viewer, see img/SOURCES.md).
    out = f'<img src="img/quest-mr-mockup.jpg" alt="Concept mockup: twin view of a Level 1 ceiling with BIM pipes and simulated sensor readings" style="{pos(.55,1.28,4.45,2.5)};border-radius:{.16*U:.0f}px;outline:6px solid {DARK};outline-offset:-3px;object-fit:cover">'
    out += text(.55, 3.8, 4.45, .25, P('Concept mockup: 360° photo + BIM overlay from the twin; not a Quest 3 capture', size=8.5, color=MUTED, italic=True))
    cards = [('Walk the real building', 'Real surroundings, safe to walk'),
             ('See hidden BIM', 'Pipes, ducts above the ceiling'),
             ('Sensor readings on site', 'At each element (simulated)')]
    for i, (h, b) in enumerate(cards):
        out += card(5.2, 1.28 + i * .93, 4.25, .85, h, b, head_size=17, size=13.5, middle=True)
    out += pill(.85, .86, 3.6, .32, 'Not tested yet · waiting for the device', bg=RED, size=12)
    return out + ask_bar('Lab Quest 3 · Level 1 foyer time', size=16)

def part_pill(x, y, part, w=1.12, h=.26, size=9, short=False):
    lab, bg, fg, sh = PARTS[part]
    return pill(x, y, w, h, sh if short else lab, bg=bg, color=fg, size=size)

def week_asks():
    rows = [('1', 'dashboard', 'Decision on SkySpark meter access', 'main campus, hourly, 12-month target', 'Facilities energy data', 'Before Nov 16'),
            ('2', 'grimes', 'Owner + process: plans, sensors, drone', 'plus one site for a first test install', 'Facilities operations', 'Follow-up email after today'),
            ('3', 'grimes', 'Quest 3 + quiet time in the Grimes foyer', 'mixed-reality test', 'Lab (headset custodian)', 'This week'),
            ('4', 'grimes', 'Read-only BAS trend export + point list', 'tagged to BIM elements', 'Facilities controls', 'After asks 1–3')]
    out = ''; y0 = 1.2; rh = .78
    for x, w, t in [(1.15, 1.2, 'Part'), (2.45, 3.3, 'Ask'), (5.85, 1.8, 'From'), (7.75, 1.7, 'When')]:
        out += text(x, y0, w, .28, P(t.upper(), size=8.5, bold=True, color=TEAL))
    for i, (n, part, a, sub, frm, when) in enumerate(rows):
        y = y0 + .32 + i * (rh + .08)
        out += box(.55, y, 8.9, rh, 'card navy' if i == 0 else 'card')
        col = '#fff' if i == 0 else DARK; hc = GOLD if i == 0 else NAVY
        out += f'<div class="circ" style="{pos(.68,y+rh/2-.19,.38,.38)};background:{GOLD if i == 0 else NAVY};color:{NAVY if i == 0 else "#fff"};font-size:{14*PT:.1f}px">{n}</div>'
        out += part_pill(1.15, y + rh / 2 - .14, part, h=.28, size=10, short=True)
        out += text(2.45, y, 3.35, rh, [[(a, dict(bold=True, size=13, color=hc))], [(sub, dict(size=11, color=col))]], anchor='middle', gap=1)
        out += text(5.85, y, 1.85, rh, P(frm, size=11.5, color=col), anchor='middle')
        out += text(7.75, y, 1.65, rh, P(when, size=11.5, bold=True, color=hc), anchor='middle')
    return out

def test_installs():
    rows = [('1', 'Fiber temperature (DTS) + wetness sensor', 'Sprinkler main (Pipe219763)', 'Can a controlled temperature change be detected and mapped to the right BIM pipe segment?', 'One cable run, analyzer loan, contained thermal test'),
            ('2', 'Duct airflow probe + one room reading', 'Supply branch 401233 and nearby diffuser', 'Measured branch airflow vs a verified design value; its trend vs one room temperature / CO2 reading', '1 probe, 1 node; design value to verify'),
            ('3', 'Leak (wetness) sensor', 'No-hub coupling 423698, lobby', 'Is water at this fitting detected? (Flow meter: a later option on a verified supply branch)', '1 sensor; no cutting or shutdown'),
            ('4', 'Power meter (current + voltage)', 'Circuit feeding VAV units (to confirm)', 'Load profile of the confirmed circuit: operating vs idle periods', 'Panel access, electrician'),
            ('5', 'Wireless vibration node', 'Duct 399665, fed by a fan', 'Does duct vibration change reproducibly with the fan’s operating state?', '1 battery node, IT approval')]
    out = ''; y0 = 1.17; rh = .56
    for x, w, t in [(1.15, 3.35, 'Sensor · where'), (4.6, 3.1, 'What we would learn'), (7.8, 1.6, 'Scale (indicative)')]:
        out += text(x, y0, w, .26, P(t.upper(), size=8.5, bold=True, color=TEAL))
    for i, (n, sen, where, learn, scale) in enumerate(rows):
        y = y0 + .3 + i * (rh + .06)
        out += box(.55, y, 8.9, rh, 'card')
        out += f'<div class="circ" style="{pos(.68,y+rh/2-.16,.32,.32)};background:{NAVY};font-size:{12*PT:.1f}px">{n}</div>'
        out += text(1.15, y, 3.35, rh, [[(sen, dict(bold=True, size=11, color=NAVY))], [(where, dict(size=9.5))]], anchor='middle', gap=1)
        out += text(4.6, y, 3.1, rh, P(learn, size=10), anchor='middle')
        out += text(7.8, y, 1.6, rh, P(scale, size=9.5, color=MUTED), anchor='middle')
    return out

def thanks_extra():
    out = ''
    qs = ['Can we decide on SkySpark meter access before Nov 16?', 'Can we test mixed reality in the Grimes foyer with the Quest 3 this week?', 'Where could we try a first test install?']
    for i, q in enumerate(qs):
        out += box(.7 + 2.95 * i, 3.35, 2.75, 1.0, 'card')
        out += text(.82 + 2.95 * i, 3.35, 2.5, 1.0, [[('QUESTION ' + str(i + 1), dict(bold=True, size=8, color=TEAL))], [(q, dict(size=11.5, color=NAVY, bold=True))]], anchor='middle', gap=2)
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
        elif sid == 'open-ceiling': body += open_ceiling()
        elif sid == 'test-installs': body += test_installs()
        elif sid == 'fiber': body += fiber_slide()
        elif sid == 'ce278': body += ce278_slide()
        elif sid == 'mems': body += mems_slide()
        elif sid == 'wsn': body += wsn_slide()
        elif sid == 'ready': body += ready_slide()
        elif sid == 'week-energy': body += week_energy()
        elif sid == 'week-facilities': body += week_facilities()
        elif sid == 'week-quest': body += week_quest()
        elif sid == 'week-asks': body += week_asks()
        elif sid in SC: body += twin_slide(SC[sid])
    return f'<section class="slide" id="{s["id"]}">{body}</section>'

slides_html = '\n'.join(slide(s, i + 1) for i, s in enumerate(SLIDES))
notes = json.dumps([s.get('notes', '') for s in SLIDES], ensure_ascii=False)
css = (ROOT / 'deck.css').read_text() + TWIN_CSS + DIV_CSS
js = (ROOT / 'deck.js').read_text() + '\n' + (ROOT / 'place.js').read_text()
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
