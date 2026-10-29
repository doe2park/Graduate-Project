# Concept scenarios for the interactive twin slides. Base images: public May 6, 2026 capture only (clean crops, no UI text).
import math
from twin_lib import *

# Live twin: the LOCAL viewer (same origin as this deck) with the opt-in demo-sensor layer (twin/sensors/registry.json).
# Relative to talks/sensor-deck/: works on the local server and on GitHub Pages (site root = repo root).
LENS = '../../scan-compare.html?view=overlay&capture=2026-05-06&mode=photo&style=lens&sensors=demo&scene={scene}&focus={focus}&at='
# the Lens opens on (and follows) the scene's main sensor: twin/sensors/registry.json "primary"
import json as _json, pathlib as _pl
_PRIMARY = _json.loads((_pl.Path(__file__).resolve().parent.parent.parent / 'twin' / 'sensors' / 'registry.json').read_text())['primary']
_REG = {x['id']: x for x in _json.loads((_pl.Path(__file__).resolve().parent.parent.parent / 'twin' / 'sensors' / 'registry.json').read_text())['sensors']}
def live(scene, at): return LENS.format(scene=scene, focus=_PRIMARY[scene]) + at
FOOT = 'Nothing installed; values simulated.'
def foot(capture, where=''): return (where + ' ' if where else '') + FOOT + ' Live twin: May 6, 2026 capture ' + str(capture) + '; demo sensors on real BIM elements.'

# ---------- 1. leak ceiling (DTS pipe) -- original view, capture 35
OFF = 11; _dx, _dy = 905 - 330, 619 - 176; _L = math.hypot(_dx, _dy)
P0 = (330 + OFF * _dy / _L - 200, 176 - OFF * _dx / _L - 175); P1 = (905 + OFF * _dy / _L - 200, 619 - OFF * _dx / _L - 175)
def ptl(t): return P0[0] + t * (P1[0] - P0[0]), P0[1] + t * (P1[1] - P0[1])
HOT = ptl(.40); VIB = (224, 47); LEAK = (385, 273)
_stops = ''.join(f'<stop offset="{i/30:.3f}" stop-color="#00BEE6"/>' for i in range(31))
_defs = (f'<linearGradient class="dts" id="g1" gradientUnits="userSpaceOnUse" x1="{P0[0]:.1f}" y1="{P0[1]:.1f}" x2="{P1[0]:.1f}" y2="{P1[1]:.1f}">{_stops}</linearGradient>'
         '<radialGradient id="glow1"><stop offset="0" stop-color="#E61E1E" stop-opacity=".55"/><stop offset="1" stop-color="#E61E1E" stop-opacity="0"/></radialGradient>')
_L1 = f'x1="{P0[0]:.1f}" y1="{P0[1]:.1f}" x2="{P1[0]:.1f}" y2="{P1[1]:.1f}"'
S1 = dict(
 id='twin-concept', slug='leak', base='t1-lens-base.jpg', fallback='img/t2-twin-sensor-mockup.jpg', anim='dts',
 live=live('leak', '-32.082,7.233,-14.823,0.3367,0.3199,-0.1228,0.8771,75.0'),
 defs=_defs,
 bg=(f'<line x1="{HOT[0]:.1f}" y1="{HOT[1]:.1f}" x2="{LEAK[0]}" y2="{LEAK[1]}" stroke="#fff" stroke-opacity=".8" stroke-width="2"/>'
     f'<circle cx="{HOT[0]:.1f}" cy="{HOT[1]:.1f}" r="62" fill="url(#glow1)"/>'),
 elements=[
  dict(k=1, sid='leak-dts', col='#1E50DC', title='Fiber temperature line (DTS)', row='Colour = temperature every ~1 m along the pipe',
       what='Fiber cable strapped along the pipe; an analyzer reads a temperature about every metre.', val='22 °C baseline, 31 °C at 33 m along the cable (simulated test change)',
       maps='BIM pipe Pipe219763 (fire main, element 278123); cable metres → pipe via the route survey', badge=(500, 238), hit=(500, 238, 16), under=True,
       draw=(f'<line {_L1} stroke="#fff" stroke-opacity=".95" stroke-width="11" stroke-linecap="round"/><line {_L1} stroke="url(#g1)" stroke-width="7" stroke-linecap="round"/>'
             f'{flowline([P0, P1], "#fff", 3, "3 52")}<line {_L1} stroke="rgba(0,0,0,.001)" stroke-width="30"/>' + badge(1, 500, 238, '#1E50DC')), ),
  dict(k=2, sid='leak-alert', col='#C81E1E', title='Temperature anomaly (test)', row='Controlled temperature change above the expected value',
       what='Flags where the line reads above the expected value during the controlled test.', val='+9 °C above baseline during the test',
       maps='Pipe219763 at the test location (element 278123)', badge=(HOT[0] - 34, HOT[1] - 34), hit=(HOT[0], HOT[1], 42),
       draw=ring(round(HOT[0], 1), round(HOT[1], 1), 40) + badge(2, round(HOT[0] - 34, 1), round(HOT[1] - 34, 1), '#C81E1E')),
  dict(k=3, sid='leak-vibration', col='#087F8C', title='Vibration node', row='Wireless MEMS node on the line: pump / flow condition',
       what='Wireless MEMS accelerometer on the line: pump and flow condition.', val='0.8 mm/s RMS, normal',
       maps='Pipe219763, the pipe it is clamped to', badge=VIB, hit=(*VIB, 24), draw=pin(3, *VIB, '#087F8C')),
  dict(k=4, sid='leak-puck', col='#003262', title='Leak (wetness) sensor', row='Point check on the tile below: is there water?',
       what='Separate wetness sensor on the tile below, to check for water.', val='Dry now; would flip to "water detected"',
       maps='Pipe219763 above it (no ceiling elements in the model)', badge=LEAK, hit=(*LEAK, 24), draw=pin(4, *LEAK, '#003262')),
 ],
 legend=[('#1E50DC', 'cool'), ('#00BEE6', 'normal'), ('#FAD728', 'warm'), ('#E61E1E', 'hot (alert)')],
 steps=[dict(head='Test', text='Controlled change; analyzer reads 31 °C at 33 m'), dict(head='Map to BIM', text='33 m → Pipe219763 segment (route survey)'),
        dict(head='Check', text='Right segment? Wetness sensor checks water')],
)
S1.update(title='Test install 1: Fiber temperature on a sprinkler main', subtitle='Can a controlled temperature change on Pipe219763 be detected and mapped to the right BIM pipe segment?',
          footnote=foot(35, 'Sprinkler main above a Level 1 ceiling.'),
          notes='This is a concept of how the test would look in the twin. The view on the left is the interactive viewer: the May 6 capture with the BIM in the Lens, and you can drag to look around; the demo sensors stay attached to their BIM elements. Nothing is installed and the values are simulated. The question is narrow: can a controlled temperature change along the sprinkler main, element Pipe219763, be detected and mapped to the right BIM pipe segment? We are not claiming that a real leak would make a measurable warm spot on this pipe; that is something the test would have to establish. Marker one is the fiber temperature line, with the pipe coloured from blue for cool to red for hot. Marker two flags a temperature anomaly during the test. Marker three is a wireless vibration node on the same pipe. Marker four is a separate wetness sensor on the tile below, which checks for water independently of the fiber. The steps: apply a contained, controlled temperature change; the analyzer reports a temperature at a distance along the cable; we map that distance to the pipe segment using a survey of the cable route and check that it is the right segment. If the interactive view does not load, the Static view button shows a screenshot.')


def mk_slide(**kw): return kw
SPK_NIGHT = _REG['water-flow']['reading']['series']   # 24 hourly values from 00:00; elevated 01:00-04:00

# ---------- 2. HVAC: duct + room air node + comfort tint  (capture 43, station 83697643, yaw 270 / pitch 40)
S2 = dict(
 id='twin-hvac', slug='hvac', base='b-hvac.jpg', fallback='', anim='',
 live=live('air', '-20.475,6.642,0.696,0.2418,-0.6645,0.2418,0.6645,75.0'),
 title='Test install 2: Airflow in a supply branch vs design',
 subtitle='Compare measured airflow in branch 401233 with a verified design value and its trend with one room reading',
 bg=zone(235, 345, 190, 105, '#FF7A1A', .22, -10) + zone(190, 250, 90, 55, '#FFC14D', .16, -10),
 elements=[
  dict(k=1, sid='hvac-airflow', col='#087F8C', title='Airflow + supply-air temperature', row='Duct probe: airflow and air temperature in the branch',
       what='Pitot / thermal probe in the supply branch, reporting airflow and air temperature.', val='420 CFM at 13.2 °C; illustrative design reference 450 CFM (to verify)',
       maps='BIM spiral duct, element 401233 (M-HVAC-DUCT)', badge=(585, 255), hit=(585, 255, 26),
       draw=flowline([(585, 335), (585, 190)], '#fff', 6, '2 44') + pin(1, 585, 255, '#087F8C')),
  dict(k=2, sid='hvac-iaq', col='#1E50DC', title='Room reading: CO2 / temperature / humidity', row='One representative point reading next to the diffuser',
       what='Small wireless node on the ceiling tile: CO2, air temperature and humidity.', val='CO2 780 ppm, 25.9 °C, 48 % RH (one point reading)',
       maps='BIM supply diffuser, element 388279 (no room elements in the model)', badge=(250, 300), hit=(250, 300, 26), draw=pin(2, 250, 300, '#1E50DC')),
  dict(k=3, sid='hvac-comfort', col='#E8590C', title='Comfort tint (illustrative only)', row='Not a measurement: one node cannot map a whole room',
       what='Illustrative tint only. A single node does not give a spatial comfort map; room and served-zone mapping are missing.', val='Illustrative: +2.4 °C vs a 23.5 °C reference',
       maps='Drawn around diffuser 388279; a room element would be needed', badge=(130, 380), hit=(235, 345, 70),
       draw='<ellipse cx="235" cy="345" rx="190" ry="105" fill="rgba(0,0,0,.001)" transform="rotate(-10 235 345)"/>' + badge(3, 130, 380, '#E8590C')),
  dict(k=4, sid='hvac-damper', col='#003262', title='VAV damper status (from BAS)', row='Not a new sensor: a point we would ask Facilities for',
       what='Damper position and zone setpoint from the building automation system, if we get access. The branch–diffuser–VAV relation needs verifying.', val='Damper 72 % open; cooling mode',
       maps='Shown on branch duct 401200; the VAV box is outside this view', badge=(655, 385), hit=(655, 385, 26), draw=pin(4, 655, 385, '#003262')),
 ],
 legend=[('#FF7A1A', 'illustrative tint, not measured'), ('#7C3AED', 'room reading')],
 steps=[dict(head='Measure', text='Branch airflow; one room CO2 / temperature reading'), dict(head='Map to BIM', text='Probe → duct 401233; verify branch–diffuser–VAV'),
        dict(head='Compare', text='Measured vs verified design value; trend vs room')],
 footnote=foot(43, 'Spiral supply-duct branches, Level 1 ceiling. 450 CFM and 23.5 °C are illustrative; branch–diffuser–VAV relation to be verified.'),
 notes='Concept two is airflow. The view looks up at a Level 1 ceiling where the model shows branches off a supply duct. The test is a comparison: measured airflow in branch 401233 against a verified design value, and how its trend relates to one representative room temperature and CO2 reading. Marker one is an airflow and supply air temperature probe in the branch. Marker two is a single small node next to the diffuser giving one point reading, not a whole-room picture. Marker three is only an illustrative tint: one node cannot give a spatial comfort map, and the room and served zone are not modelled, so please read it as a placeholder. Marker four is not a new sensor: the damper position from the building automation system, if Facilities shares it. Before anything is installed we need to verify how this branch, the diffuser and the VAV box are related, and what the design airflow really is: 450 CFM and 23.5 degrees are illustrative references. Each reading would map to a BIM duct element ID. Every number is made up.')

# ---------- 3. Plumbing branch: ultrasonic flow + leak puck + night-flow alert  (capture 1, station 83697575, yaw 0 / pitch 40)
S3 = dict(
 id='twin-water', slug='water', base='b-plumb.jpg', fallback='', anim='',
 live=live('water', '-14.906,6.632,13.671,0.3420,0.0000,0.0000,0.9397,75.0'),
 title='Test install 3: Wetness sensor at a pipe coupling',
 subtitle='Place a leak (wetness) sensor below coupling 423698 to test detection of water at this fitting; a flow meter is a later option',
 bg=link(615, 300, 715, 148, '#fff', 2, '5 5'),
 elements=[
  dict(k=1, sid='water-flow', col='#087F8C', title='Flow meter (later option)', row='Not in this trial: only on a verified domestic supply branch',
       what='Later option: clamp-on ultrasonic meter on a verified domestic supply branch. This cast-iron no-hub pipe is likely drainage, so it is shown only for orientation.', val='Illustrative: 0.0 L/s normally; 0.6 L/s between 1 and 4 am',
       maps='BIM cast-iron no-hub pipe, element 418392 (P-PIPE); location illustrative', badge=(615, 300), hit=(615, 300, 26),
       draw='<rect x="596" y="288" width="38" height="24" rx="4" fill="#fff" stroke="#003262" stroke-width="3"/>' + pin(1, 615, 300, '#087F8C', 16)),
  dict(k=2, sid='water-puck', col='#003262', title='Leak (wetness) sensor', row='This trial: puck below coupling 423698',
       what='Wetness puck below the coupling: reports water on the surface below, to test detection of water at this fitting.', val='Dry; would flip to "water detected"',
       maps='BIM no-hub coupling above it, element 423698', badge=(560, 470), hit=(560, 470, 26), draw=pin(2, 560, 470, '#003262')),
  dict(k=3, sid='water-alert', col='#C81E1E', title='Night-flow rule (later option)', row='Persistent unexplained night flow triggers investigation',
       what='If a flow meter is added later: persistent unexplained flow when the building is empty would trigger an investigation.', val='Illustrative: +0.6 L/s between 1 and 4 am',
       maps='Pipe 418392 (location illustrative)', badge=(715, 148), hit=(715, 148, 40),
       draw=ring(615, 300, 46) + '<circle cx="715" cy="148" r="16" fill="#C81E1E" stroke="#fff" stroke-width="3"/><text x="715" y="154" text-anchor="middle" font-size="18" font-weight="700" fill="#fff">3</text>'),
 ],
 legend=None,
 steps=[dict(head='Place', text='Wetness sensor below coupling 423698'), dict(head='Detect', text='Does it report water at this fitting?'),
        dict(head='Show', text='Alert on that coupling in the Lens')],
 footnote=foot(1, 'Cast-iron no-hub pipe and coupling (BIM plumbing) above the Level 1 lobby; sensor location illustrative.'),
 notes='Concept three is a water fitting. The view looks up at the Level 1 lobby ceiling, where the BIM shows a cast iron no hub pipe and coupling in the plumbing model. Cast iron no hub is usually drain piping, so we do not propose a flow meter here. This location is a wetness only trial: place a leak sensor below coupling 423698 to test whether it detects water at this fitting. Marker two is that sensor. Markers one and three are a later option, shown for orientation: a clamp on ultrasonic flow meter would go on a verified domestic supply branch, and persistent unexplained flow at night, when the building is empty, would trigger an investigation. The night flow curve is simulated, with the raised flow between one and four in the morning. All values are illustrative.')

# ---------- 4. Electrical: CT sub-meter + panel monitor, rolled up to the building meter  (capture 43, station 83697643, yaw 180 / pitch 40)
SPK_KW = _REG['power-ct']['reading']['series']   # one illustrative day, hourly from 00:00, shared with the viewer's registry
S4 = dict(
 id='twin-power', slug='power', base='b-elec.jpg', fallback='', anim='',
 live=live('elec', '-20.475,6.642,0.696,0.0000,0.9397,-0.3420,0.0000,75.0'),
 title='Test install 4: Power on a VAV circuit',
 subtitle='After confirming the circuit, measure its load profile with a power meter (current + voltage); compare operating and idle periods',
 bg=link(535, 330, 700, 205, '#FDB515', 2.5, '6 5', .95) + link(705, 378, 700, 205, '#FDB515', 2.5, '6 5', .95),
 elements=[
  dict(k=1, sid='power-ct', col='#E8590C', title='Power meter (current + voltage)', row='On the circuit feeding these units, once confirmed',
       what='Power meter with current and voltage inputs (a current clamp alone does not give true kW), on the circuit that feeds the terminal units once membership is confirmed.', val='0.42 kW now (peak 0.55 kW at 11:00)',
       maps='BIM terminal unit (coil kit), element 381444; circuit unconfirmed, no conduit modelled', badge=(535, 335), hit=(535, 335, 26), draw=pin(1, 535, 335, '#E8590C')),
  dict(k=2, sid='power-unit', col='#087F8C', title='Unit power monitor', row='Controller and actuator current at the VAV terminal unit',
       what='Small monitor at the VAV box: controller supply and damper-actuator current.', val='24 VAC controller; actuator 0.6 A',
       maps='BIM VAV terminal unit (Price SDV5), element 396073', badge=(705, 380), hit=(705, 380, 26), draw=pin(2, 705, 380, '#087F8C')),
  dict(k=3, sid='power-bmo', col='#003262', title='Building-level context', row='Whole-building meter, shown for context only',
       what='The whole-building meter reports every 15 minutes (BMO now; SkySpark suggested, not decided). It is context only: this small trial is not expected to add up to it.', val='Building 212 kW (context only)',
       maps='Building meter channel (building-level)', badge=(700, 205), hit=(700, 205, 26), draw=pin(3, 700, 205, '#003262')),
 ],
 legend=None,
 steps=[dict(head='Confirm', text='Which circuit feeds these units'), dict(head='Measure', text='Load profile: operating vs idle periods'),
        dict(head='Show', text='Circuit load on the BIM element, in the viewer')],
 footnote=foot(43, 'Price SDV5 VAV box and coil kit (BIM) above a Level 1 ceiling; no conduit is modelled in this view.'),
 notes='Concept four is electrical. The view shows two VAV terminal units in a Level 1 ceiling: in the BIM they are a Price SDV5 box and a coil kit. No conduit is modelled in this view, so which circuit feeds them is not confirmed, and the first step of the trial is to confirm it. Marker one is a power meter with current and voltage inputs on that circuit, because a current clamp alone does not give true kilowatts; the card shows one illustrative day, and the test compares operating and idle periods. Marker two is a small monitor on the VAV box with controller and actuator current. Marker three is building level context from the whole building meter, which reports every fifteen minutes; this small trial is not expected to add up to it. Each reading maps to a BIM element ID. Values are made up.')

# ---------- 5. Rotating equipment: vibration + bearing temperature + trend alert  (capture 22, station 83697587, yaw 180 / pitch 40)
SPK_VIB = _REG['fan-vibration']['reading']['series']   # 13 weekly values: 1.2 four weeks ago -> 2.1 now (+75 %), shared with the registry
S5 = dict(
 id='twin-fan', slug='fan', base='b-fan.jpg', fallback='', anim='',
 live=live('rotating', '-23.391,6.497,12.169,0.0000,0.9397,-0.3420,0.0000,75.0'),
 title='Test install 5: Vibration on a fan-fed duct run',
 subtitle='Test whether vibration on duct 399665 changes reproducibly with the upstream fan’s operating state',
 bg='',
 elements=[
  dict(k=1, sid='fan-vibration', col='#087F8C', title='Vibration node', row='Wireless MEMS accelerometer on the duct run',
       what='Wireless MEMS node on the duct: vibration spectrum and overall level, carried from the fan that feeds it.', val='2.1 mm/s RMS, up from 1.2 four weeks ago (illustrative)',
       maps='BIM straight rectangular duct, element 399665 (M-HVAC-DUCT)', badge=(540, 338), hit=(540, 338, 26), draw=pin(1, 540, 338, '#087F8C')),
  dict(k=2, sid='fan-bearing', col='#E8590C', title='Bearing temp. (separate future test)', row='Not in this proposal: a later fan-mounted probe',
       what='Separate future test: a surface probe mounted on the fan bearing itself. Shown on the duct only because the fan is not in this scan.', val='Illustrative: 58 °C; reference 45 to 50 °C',
       maps='Shown on duct 399665; the fan has no element in this view', badge=(603, 312), hit=(603, 312, 26), draw=pin(2, 603, 312, '#E8590C')),
  dict(k=3, sid='fan-alert', col='#C81E1E', title='"Vibration change" flag', row='A sustained change, flagged for inspection',
       what='Flags a sustained change in vibration, to be checked against the fan’s operating state before anyone concludes anything.', val='+75 % in 4 weeks (1.2 to 2.1): flag for inspection',
       maps='Duct 399665; inspection request to Facilities', badge=(455, 250), hit=(540, 330, 100),
       draw=ring(540, 330, 98) + '<circle cx="455" cy="250" r="16" fill="#C81E1E" stroke="#fff" stroke-width="3"/><text x="455" y="256" text-anchor="middle" font-size="18" font-weight="700" fill="#fff">3</text>'),
 ],
 legend=None,
 steps=[dict(head='Measure', text='Duct vibration; note the fan’s on / off state'), dict(head='Compare', text='Does vibration change with the fan state, every time?'),
        dict(head='Show', text='Flag a change for inspection in the Lens')],
 footnote=foot(22, 'Straight rectangular duct by the Level 1 windows; the fan itself is not in the scan.'),
 notes='Concept five is rotating equipment. The fans, pumps and air handlers are in plant rooms that are not in this scan, so this is an illustrative location: a duct run fed by a fan. In the BIM the element is a straight rectangular duct near the Level 1 windows, not a fan box. The question is simple: does vibration on duct 399665 change reproducibly with the upstream fan operating state? Marker one is a wireless vibration node on the duct, with an illustrative thirteen week trend on the card that rises from 1.2 to 2.1, which is plus 75 percent over the last four weeks. Marker three flags a sustained change for inspection; it is not a prediction of failure, and duct vibration alone does not establish fan wear. Marker two, bearing temperature, is not part of this proposal; it is a separate future test with a probe mounted on the fan itself, shown here only for orientation. All values are illustrative.')

for _s, _n in ((S2, 'twin-hvac'), (S3, 'twin-water'), (S4, 'twin-power'), (S5, 'twin-fan')):
    _s['kind'] = 'figure'
SCENARIOS = [S1, S2, S3, S4, S5]

# ---------- drawn geometry per marker, for the callout placement (place.js; base-image px). 'geo' is avoided when that
# marker is selected (hard) and when another one is (soft); 'area' (tints) is only ever soft. Shapes: seg / ring / box / dot.
GEO = {
 ('leak', 1): dict(geo=[('seg', *P0, *P1, 9)]),
 ('leak', 2): dict(geo=[('ring', round(HOT[0], 1), round(HOT[1], 1), 40, 6), ('seg', round(HOT[0], 1), round(HOT[1], 1), *LEAK, 3)]),
 ('hvac', 1): dict(geo=[('seg', 585, 335, 585, 190, 5)]),
 ('hvac', 3): dict(area=[('box', 45, 250, 425, 440)]),
 ('water', 1): dict(geo=[('box', 594, 286, 636, 314)]),
 ('water', 3): dict(geo=[('ring', 615, 300, 46, 6), ('seg', 615, 300, 715, 148, 3)]),
 ('power', 1): dict(geo=[('seg', 535, 330, 700, 205, 3)]),
 ('power', 2): dict(geo=[('seg', 705, 378, 700, 205, 3)]),
 ('power', 3): dict(geo=[('seg', 535, 330, 700, 205, 3), ('seg', 705, 378, 700, 205, 3)]),
 ('fan', 3): dict(geo=[('ring', 540, 330, 98, 6)]),
}
for _s in SCENARIOS:
    for _el in _s['elements']:
        _el.update(GEO.get((_s['slug'], _el['k']), {}))
