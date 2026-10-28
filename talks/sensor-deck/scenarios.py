# Concept scenarios for the interactive twin slides. Base images: public May 6, 2026 capture only (clean crops, no UI text).
import math
from twin_lib import *

# Live twin: the LOCAL viewer (same origin as this deck) with the opt-in demo-sensor layer (twin/sensors/registry.json).
# Relative to talks/sensor-deck/: works on the local server and on GitHub Pages (site root = repo root).
LENS = '../../scan-compare.html?view=overlay&capture=2026-05-06&mode=photo&style=lens&sensors=demo&scene={scene}&focus={focus}&at='
# the Lens opens on (and follows) the scene's main sensor: twin/sensors/registry.json "primary"
import json as _json, pathlib as _pl
_PRIMARY = _json.loads((_pl.Path(__file__).resolve().parent.parent.parent / 'twin' / 'sensors' / 'registry.json').read_text())['primary']
def live(scene, at): return LENS.format(scene=scene, focus=_PRIMARY[scene]) + at
FOOT = 'Concept mockup — no sensors are installed; values are illustrative.'
def foot(capture, where=''): return (where + ' ' if where else '') + FOOT + ' Live twin: public May 6, 2026 capture ' + str(capture) + '; demo sensors anchored to real BIM elements.'

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
       what='Fiber cable strapped along the pipe; an analyzer reads a temperature about every metre.', val='22 °C baseline, 31 °C at 33 m along the cable',
       maps='BIM pipe Pipe219763 (fire main, element 278123); cable metres → pipe via the route survey', badge=(500, 238), hit=(500, 238, 16),
       draw=(f'<line {_L1} stroke="#fff" stroke-opacity=".95" stroke-width="11" stroke-linecap="round"/><line {_L1} stroke="url(#g1)" stroke-width="7" stroke-linecap="round"/>'
             f'{flowline([P0, P1], "#fff", 3, "3 52")}<line {_L1} stroke="rgba(0,0,0,.001)" stroke-width="30"/>' + badge(1, 500, 238, '#1E50DC')), ),
  dict(k=2, sid='leak-alert', col='#C81E1E', title='Alert ring', row='Warm spot above the expected value: possible leak',
       what='Warm spot above the expected value along the line: possible leak.', val='+9 °C above baseline, alert raised',
       maps='Pipe219763 at the warm spot (element 278123)', badge=(HOT[0] - 34, HOT[1] - 34), hit=(HOT[0], HOT[1], 42),
       draw=ring(round(HOT[0], 1), round(HOT[1], 1), 40) + badge(2, round(HOT[0] - 34, 1), round(HOT[1] - 34, 1), '#C81E1E')),
  dict(k=3, sid='leak-vibration', col='#087F8C', title='Vibration node', row='Wireless MEMS node on the line: pump / flow condition',
       what='Wireless MEMS accelerometer on the line: pump and flow condition.', val='0.8 mm/s RMS, normal',
       maps='Pipe219763, the pipe it is clamped to', badge=VIB, hit=(*VIB, 24), draw=pin(3, *VIB, '#087F8C')),
  dict(k=4, sid='leak-puck', col='#003262', title='Leak sensor', row='Point check on the tile below the warm spot',
       what='Point check on the tile below the warm spot, to confirm water.', val='Dry now; would flip to "water detected"',
       maps='Pipe219763 above it (no ceiling elements in the model)', badge=LEAK, hit=(*LEAK, 24), draw=pin(4, *LEAK, '#003262')),
 ],
 legend=[('#1E50DC', 'cool'), ('#00BEE6', 'normal'), ('#FAD728', 'warm'), ('#E61E1E', 'hot (alert)')],
 steps=[dict(head='Reading', text='Analyzer: 31 °C at 33 m along the cable'), dict(head='Map to BIM', text='33 m → Pipe219763 (cable route survey)'),
        dict(head='Show', text='Colour and alert on that pipe, in the Lens and the headset')],
)
S1.update(title='Test install 1 · Fiber temperature on a sprinkler main', subtitle='If installed here: a warm spot on the pipe points to a leak before anyone opens a tile · BIM element Pipe219763',
          footnote=foot(35, 'Sprinkler main above a Level 1 ceiling.'),
          notes='This is a concept of how the sensors would look in the twin. The view on the left is the live viewer: the May 6 capture with the BIM in the Lens, and you can drag to look around; the demo sensors stay attached to their BIM elements. Nothing is installed and the values are made up. Marker one is the fiber temperature line on the sprinkler main, element Pipe219763: the pipe itself is coloured from blue for cool to red for hot. Marker two is an alert ring where the line is warmer than expected, which could mean a leak. Marker three is a wireless vibration node, and marker four is a leak sensor on the tile below the warm spot, to confirm water. It would work in three steps. The analyzer reports a temperature at a distance along the cable. We map that distance to the BIM pipe element using a survey of the cable route. Then the viewer colours that pipe and shows the alert, both in the Lens on the computer and in the headset. If the live view does not load, the Static view button shows a screenshot.')


def mk_slide(**kw): return kw
SPK_NIGHT = [0, 0, 0, 0, 0, 0, 0, 0.05, 0.02, 0, 0, 0, 0.1, 0.05, 0, 0, 0, 0.06, 0, 0.55, 0.6, 0.58, 0.6, 0.59]

# ---------- 2. HVAC: duct + room air node + comfort tint  (capture 43, station 83697643, yaw 270 / pitch 40)
S2 = dict(
 id='twin-hvac', slug='hvac', base='b-hvac.jpg', fallback='', anim='',
 live=live('air', '-20.475,6.642,0.696,0.2418,-0.6645,0.2418,0.6645,75.0'),
 title='Test install 2 · Airflow and comfort at a supply duct',
 subtitle='If installed here: shows whether this room gets its design airflow, and which duct to check when it does not',
 bg=zone(235, 345, 190, 105, '#FF7A1A', .5, -10, True) + zone(190, 250, 90, 55, '#FFC14D', .35, -10),
 elements=[
  dict(k=1, sid='hvac-airflow', col='#087F8C', title='Airflow + supply-air temperature', row='Duct probe: airflow and air temperature in the branch',
       what='Pitot / thermal probe in the supply branch, reporting airflow and air temperature.', val='420 CFM at 13.2 °C; design 450 CFM',
       maps='BIM spiral duct, element 401233 (M-HVAC-DUCT)', badge=(585, 255), hit=(585, 255, 26),
       draw=flowline([(585, 335), (585, 190)], '#fff', 6, '2 44') + pin(1, 585, 255, '#087F8C')),
  dict(k=2, sid='hvac-iaq', col='#1E50DC', title='CO2 / temperature / humidity node', row='Room-side node next to the supply diffuser',
       what='Small wireless node on the ceiling tile: CO2, air temperature and humidity.', val='CO2 780 ppm, 25.9 °C, 48 % RH',
       maps='BIM supply diffuser, element 388279 (no room elements in the model)', badge=(250, 300), hit=(250, 300, 26), draw=pin(2, 250, 300, '#1E50DC')),
  dict(k=3, sid='hvac-comfort', col='#E8590C', title='Comfort heat-map tint', row='Warm area above the setpoint, drawn on the room',
       what='Tint on the floor area served by this duct: warm where the room runs above its setpoint.', val='Zone +2.4 °C above the 23.5 °C setpoint',
       maps='Drawn around diffuser 388279; a room element would be needed', badge=(130, 380), hit=(235, 345, 70),
       draw='<ellipse cx="235" cy="345" rx="190" ry="105" fill="rgba(0,0,0,.001)" transform="rotate(-10 235 345)"/>' + badge(3, 130, 380, '#E8590C')),
  dict(k=4, sid='hvac-damper', col='#003262', title='VAV damper status (from BAS)', row='Not a new sensor: a point we would ask Facilities for',
       what='Damper position and zone setpoint, read from the building automation system if we get access.', val='Damper 72 % open; cooling mode',
       maps='Shown on branch duct 401200; the VAV box is outside this view', badge=(655, 385), hit=(655, 385, 26), draw=pin(4, 655, 385, '#003262')),
 ],
 legend=[('#FFC14D', 'slightly warm'), ('#FF7A1A', 'above setpoint'), ('#7C3AED', 'room node')],
 steps=[dict(head='Measure', text='Duct airflow, room CO2 and temperature'), dict(head='Map to BIM', text='Probe → duct ID; node → room / space ID'),
        dict(head='Show', text='Tint the room, flag a duct that under-delivers')],
 footnote=foot(43, 'Spiral supply-duct branches above a Level 1 ceiling: the ducts are real BIM elements, the sensors are not.'),
 notes='Concept two is air and comfort. The view looks up at a Level 1 ceiling where the model shows branches off a supply duct. Marker one is an airflow and supply air temperature probe in a branch, so we can see whether it delivers its design airflow. Marker two is a small CO2, temperature and humidity node on the ceiling below. Marker three tints the room on the model when it runs warmer than its setpoint. Marker four is not a new sensor: the damper position from the building automation system, if Facilities shares it. Each reading would map to a BIM duct or space element ID. This is an illustrative location and every number is made up.')

# ---------- 3. Plumbing branch: ultrasonic flow + leak puck + night-flow alert  (capture 1, station 83697575, yaw 0 / pitch 40)
S3 = dict(
 id='twin-water', slug='water', base='b-plumb.jpg', fallback='', anim='',
 live=live('water', '-14.906,6.632,13.671,0.3420,0.0000,0.0000,0.9397,75.0'),
 title='Test install 3 · Flow on a plumbing branch',
 subtitle='If installed here: flow at night, when the building is empty, reveals hidden leaks on this branch',
 bg=link(615, 300, 715, 148, '#fff', 2, '5 5'),
 elements=[
  dict(k=1, sid='water-flow', col='#087F8C', title='Clamp-on ultrasonic flow meter', row='Strapped on the branch pipe: no cutting, no shutdown',
       what='Clamp-on ultrasonic meter on the branch: measures flow without opening the pipe.', val='0.0 L/s normally; 0.6 L/s at 2 am',
       spark=spark(SPK_NIGHT, '#087F8C'), spark_note='24 h flow, one night leak',
       maps='BIM cast-iron no-hub pipe, element 418392 (P-PIPE)', badge=(615, 300), hit=(615, 300, 26),
       draw='<rect x="596" y="288" width="38" height="24" rx="4" fill="#fff" stroke="#003262" stroke-width="3"/>' + pin(1, 615, 300, '#087F8C', 16)),
  dict(k=2, sid='water-puck', col='#003262', title='Leak sensor puck', row='Point sensor on the slats below the coupling',
       what='Puck sensor near the fittings: reports water on the surface below.', val='Dry; would flip to "water detected"',
       maps='BIM no-hub coupling above it, element 423698', badge=(560, 470), hit=(560, 470, 26), draw=pin(2, 560, 470, '#003262')),
  dict(k=3, sid='water-alert', col='#C81E1E', title='Night-flow alert', row='Flow when the building is empty, shown on the pipe',
       what='Alert when this branch flows at night: a likely leak. It is compared with the Grimes water meter on the campus energy dashboard.', val='+0.6 L/s between 1 and 4 am; building meter shows the same rise',
       maps='Pipe 418392; Grimes building water meter', badge=(715, 148), hit=(715, 148, 40),
       draw=ring(615, 300, 46) + '<circle cx="715" cy="148" r="16" fill="#C81E1E" stroke="#fff" stroke-width="3"/><text x="715" y="154" text-anchor="middle" font-size="18" font-weight="700" fill="#fff">3</text>'),
 ],
 legend=None,
 steps=[dict(head='Measure', text='Flow on the branch; water on the slats'), dict(head='Compare', text='Night flow vs the Grimes building water meter'),
        dict(head='Show', text='Alert on that pipe in the Lens and the dashboard')],
 footnote=foot(1, 'Cast-iron no-hub pipe and coupling (BIM plumbing) above the Level 1 lobby; sensor location illustrative.'),
 notes='Concept three is a water branch. The view looks up at the Level 1 lobby ceiling, where the BIM shows a cast iron no hub pipe and coupling in the plumbing model. Cast iron no hub is usually drain piping, so a real flow meter would go on a copper supply branch; treat the location as illustrative. Marker one is a clamp on ultrasonic flow meter, which measures flow without cutting the pipe. Marker two is a leak puck on the slats below the fittings. Marker three is the night flow alert: if the branch flows between one and four in the morning when the building is empty, we compare it with the Grimes water meter on the campus energy dashboard. The alert shows on that pipe in the Lens. All values are illustrative.')

# ---------- 4. Electrical: CT sub-meter + panel monitor, rolled up to the building meter  (capture 43, station 83697643, yaw 180 / pitch 40)
SPK_KW = [8, 7.5, 7.2, 7, 7.4, 9, 12, 15, 17, 18, 17.5, 18, 17, 17.5, 16.5, 15, 13, 11, 10, 9.4, 9, 8.6, 8.2, 8]
S4 = dict(
 id='twin-power', slug='power', base='b-elec.jpg', fallback='', anim='',
 live=live('elec', '-20.475,6.642,0.696,0.0000,0.9397,-0.3420,0.0000,75.0'),
 title='Test install 4 · Power at VAV terminal units',
 subtitle='If installed here: shows which equipment uses the power, and whether sub-meters add up to the building meter',
 bg=link(535, 330, 700, 205, '#FDB515', 2.5, '6 5', .95) + link(705, 378, 700, 205, '#FDB515', 2.5, '6 5', .95),
 elements=[
  dict(k=1, sid='power-ct', col='#E8590C', title='CT power sub-meter', row='Clip-on current sensor on the circuit feeding these units',
       what='Split-core current transformer on the circuit that feeds the terminal units: real-time kW for that circuit.', val='0.42 kW now (peak 0.55 kW at noon)',
       spark=spark(SPK_KW, '#E8590C'), spark_note='today, kW',
       maps='BIM terminal unit (coil kit), element 381444; no conduit is modelled here', badge=(535, 335), hit=(535, 335, 26), draw=pin(1, 535, 335, '#E8590C')),
  dict(k=2, sid='power-unit', col='#087F8C', title='Unit power monitor', row='Controller and actuator current at the VAV terminal unit',
       what='Small monitor at the VAV box: controller supply and damper-actuator current.', val='24 VAC controller; actuator 0.6 A',
       maps='BIM VAV terminal unit (Price SDV5), element 396073', badge=(705, 380), hit=(705, 380, 26), draw=pin(2, 705, 380, '#087F8C')),
  dict(k=3, sid='power-bmo', col='#003262', title='Link to the building meter', row='Sub-meters should add up to the whole-building meter',
       what='The whole-building meter reports electricity every 15 minutes (BMO today; SkySpark is the Facilities source going forward). Sub-meters split that total by circuit.', val='Building 212 kW; sub-meters cover 61 %',
       spark=spark([180, 176, 172, 175, 190, 205, 220, 230, 224, 212], '#003262'), spark_note='building meter, last 2.5 h',
       maps='Building meter channel; sub-meters roll up to it', badge=(700, 205), hit=(700, 205, 26), draw=pin(3, 700, 205, '#003262')),
 ],
 legend=None,
 steps=[dict(head='Measure', text='kW per circuit; unit current'), dict(head='Roll up', text='Sub-meters vs the building meter'),
        dict(head='Show', text='Load on each circuit, in the viewer')],
 footnote=foot(43, 'Price SDV5 VAV box and coil kit (BIM) above a Level 1 ceiling; no conduit is modelled in this view.'),
 notes='Concept four is electrical. The view shows two VAV terminal units in a Level 1 ceiling: in the BIM they are a Price SDV5 box and a coil kit. No conduit is modelled in this view, so the circuit is illustrative. Marker one is a clip on current transformer on the circuit feeding these units, giving kilowatts, and the card shows a small day profile. Marker two is a small monitor on the VAV box with controller and actuator current. Marker three is the link to the building meter, which already reports whole building electricity every fifteen minutes. The idea is that circuit sub meters add up toward that total, so we can see where the load is. Each reading maps to a BIM element ID. Values are made up.')

# ---------- 5. Rotating equipment: vibration + bearing temperature + trend alert  (capture 22, station 83697587, yaw 180 / pitch 40)
SPK_VIB = [1.1, 1.2, 1.1, 1.2, 1.3, 1.2, 1.4, 1.5, 1.5, 1.7, 1.8, 2.0, 2.1]
S5 = dict(
 id='twin-fan', slug='fan', base='b-fan.jpg', fallback='', anim='',
 live=live('rotating', '-23.391,6.497,12.169,0.0000,0.9397,-0.3420,0.0000,75.0'),
 title='Test install 5 · Vibration on a duct run fed by a fan',
 subtitle='If installed here: vibration rising over weeks warns of fan wear before it fails',
 bg='',
 elements=[
  dict(k=1, sid='fan-vibration', col='#087F8C', title='Vibration node', row='Wireless MEMS accelerometer on the duct run',
       what='Wireless MEMS node on the duct: vibration spectrum and overall level, carried from the fan that feeds it.', val='2.1 mm/s RMS, up from 1.2 a month ago',
       spark=spark(SPK_VIB, '#C81E1E'), spark_note='13 weeks, mm/s RMS',
       maps='BIM straight rectangular duct, element 399665 (M-HVAC-DUCT)', badge=(540, 338), hit=(540, 338, 26), draw=pin(1, 540, 338, '#087F8C')),
  dict(k=2, sid='fan-bearing', col='#E8590C', title='Bearing temperature (at the fan)', row='Probe on the fan bearing upstream, shown on this duct',
       what='Surface temperature probe on the fan bearing: rises when a bearing wears. The fan is not in this scan.', val='58 °C; normal 45 to 50 °C',
       maps='Shown on duct 399665; the fan has no element in this view', badge=(603, 312), hit=(603, 312, 26), draw=pin(2, 603, 312, '#E8590C')),
  dict(k=3, sid='fan-alert', col='#C81E1E', title='"Vibration rising" trend alert', row='A slow trend, caught before the fan fails',
       what='Alert when vibration climbs steadily week after week, so maintenance is planned, not forced.', val='+75 % in 4 weeks: inspect bearing',
       maps='Duct 399665; work order to Facilities', badge=(455, 250), hit=(540, 330, 100),
       draw=ring(540, 330, 98) + '<circle cx="455" cy="250" r="16" fill="#C81E1E" stroke="#fff" stroke-width="3"/><text x="455" y="256" text-anchor="middle" font-size="18" font-weight="700" fill="#fff">3</text>'),
 ],
 legend=None,
 steps=[dict(head='Measure', text='Vibration and bearing temperature'), dict(head='Trend', text='Rising over weeks, not one spike'),
        dict(head='Show', text='Alert on that duct run in the Lens')],
 footnote=foot(22, 'Straight rectangular duct by the Level 1 windows; the fan itself is not in the scan.'),
 notes='Concept five is rotating equipment. The fans, pumps and air handlers are in plant rooms that are not in this scan, so this is an illustrative location: a duct run fed by a fan. In the BIM the element is a straight rectangular duct near the Level 1 windows, not a fan box. Marker one is a wireless vibration node on the duct, which picks up the vibration of the fan that feeds it, with its trend on the card. Marker two is a bearing temperature probe; on a real system it sits on the fan bearing, and here it is shown on the duct because the fan is not in view. Marker three is a trend alert: vibration climbing steadily over weeks, so maintenance can be planned before the fan fails. Each reading maps to a BIM element ID. All values are illustrative.')

for _s, _n in ((S2, 'twin-hvac'), (S3, 'twin-water'), (S4, 'twin-power'), (S5, 'twin-fan')):
    _s['kind'] = 'figure'
SCENARIOS = [S1, S2, S3, S4, S5]
