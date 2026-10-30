/* Simulated-sensor helpers for the headset page (scan-xr.html, opt-in ?sensors=demo). ILLUSTRATIVE ONLY: no sensor is installed in
   Grimes; every value comes from twin/sensors/feed.js (demo-sim) and every caption says so. Pure logic only (no DOM, no three.js),
   unit-tested in tests/sensor-xr.test.cjs. The 3D drawing, picking and cards are in scan-xr.html and reuse the registry and the
   geometry helpers of twin/sensor-demo.js (principalAxis, anchorPoint, colorAt, dtsValue) instead of copying them. */
(function (root, factory) {
  const api = factory();
  if (root) root.SensorXR = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';

const API = 1;
const SCENES = ['leak', 'air', 'water', 'elec', 'rotating'];
const SCENE_NAMES = {leak: 'Leak', air: 'Air', water: 'Water', elec: 'Power', rotating: 'Rotating'};
const DEFAULT_SCENE = 'leak';
const CAPTION = 'Demo sensor — illustrative, not installed · values simulated';
const BADGE = 'SIMULATED';
const finite = v => typeof v === 'number' && Number.isFinite(v);

/* ?sensors=demo turns the layer on (anything else, e.g. sensors=off, is off); ?scene= picks a scenario id, default leak.
   Note ?scene=gaussian belongs to the photo/Gaussian switch and is not a sensor scene. */
function parseParams(search) {
  let p; try { p = new URLSearchParams(search || ''); } catch (e) { p = new URLSearchParams(''); }
  const sc = p.get('scene');
  return {enabled: p.get('sensors') === 'demo', scene: SCENES.includes(sc) ? sc : DEFAULT_SCENE};
}
function nextScene(cur, step) {
  const i = SCENES.indexOf(cur), n = SCENES.length;
  return SCENES[(((i < 0 ? 0 : i) + (step || 1)) % n + n) % n];
}
/* Query string for the current choices (history.replaceState keeps them on reload). Other params are kept untouched.
   mode 'demo' = Demo here placement; 'align' = real Grimes landmark alignment (area optional). */
function withState(search, {mode, sensors, scene, area} = {}) {
  const p = new URLSearchParams(search || '');
  if (mode === 'demo') p.set('place', 'demo'); else if (mode === 'align') p.set('place', 'grimes');
  if (sensors === true) p.set('sensors', 'demo'); else if (sensors === false) { p.set('sensors', 'off'); }
  if (scene && SCENES.includes(scene)) p.set('scene', scene);
  if (area) p.set('area', area);
  return '?' + p.toString();
}
/* /mr defaults: demo placement with sensors, unless the incoming query already names place or sensors (even empty / "off"). */
function mrDefaults(search) {
  const p = new URLSearchParams(search || '');
  const out = new URLSearchParams(); out.set('mode', 'ar');
  if (!p.has('place')) out.set('place', 'demo');
  if (!p.has('sensors')) out.set('sensors', 'demo');
  for (const [k, v] of p) if (k !== 'mode') out.set(k, v);
  return '?' + out.toString();
}

const mean = a => a.reduce((s, v) => s + v, 0) / a.length;
/* Centre of a sensor cluster (BIM points). Returns null without points. */
function clusterCenter(points) {
  const pts = (points || []).filter(p => Array.isArray(p) && p.length === 3 && p.every(finite));
  return pts.length ? [mean(pts.map(p => p[0])), mean(pts.map(p => p[1])), mean(pts.map(p => p[2]))] : null;
}
/* A one-point "area" for MRAlign.demoTransform / demoReference: the cluster centre (x, z) at the area's floor datum, so the user's
   floor point lands under the scene's sensors and the pipe / duct appears overhead at its real height above the floor. */
function demoArea(area, center) {
  if (!area || !center || !finite(center[0]) || !finite(center[2])) return area;
  return {id: area.id, level: area.level, name: area.name, floorY: area.floorY, sensorCluster: true,
    points: [{id: 'S', kind: 'xz', label: 'sensor cluster centre', bim: [center[0], area.floorY, center[2]]}]};
}

/* Pin size in world metres for a viewing distance (keeps a roughly constant angular size, bounded for very near / far pins). */
function pinSize(dist) { return Math.min(0.6, Math.max(0.12, (finite(dist) ? dist : 3) * 0.06)); }
/* Pin hit by a ray (closest to the ray axis, ties: nearer): pins [{id, p:[x,y,z], r}] (world). Returns {id, distance, point} or null. */
function pickPin(origin, dir, pins, far) {
  let best = null;
  const dl = Math.hypot(dir[0], dir[1], dir[2]) || 1, d = dir.map(v => v / dl);
  for (const pin of pins || []) {
    const ox = pin.p[0] - origin[0], oy = pin.p[1] - origin[1], oz = pin.p[2] - origin[2];
    const t = ox * d[0] + oy * d[1] + oz * d[2];
    if (t < 0.05 || (finite(far) && t > far)) continue;
    const dx = ox - d[0] * t, dy = oy - d[1] * t, dz = oz - d[2] * t;
    const miss = Math.hypot(dx, dy, dz);
    if (miss > pin.r) continue;
    /* overlapping pins (two sensors at one spot seen from afar): the one the ray passes closest to wins, then the nearer one */
    const score = miss / pin.r;
    if (!best || score < best.score - 1e-9 || (Math.abs(score - best.score) <= 1e-9 && t < best.distance)) best = {id: pin.id, distance: t, score, point: [origin[0] + d[0] * t, origin[1] + d[1] * t, origin[2] + d[2] * t]};
  }
  return best;
}

/* Short world-locked chip text: type + SIMULATED value. */
function chipText(typeShort, valueText) { return (typeShort || 'Sensor') + ' · ' + (valueText || '—') + ' · SIM'; }

/* Lines for the headset card (same shape as xr-core cardLines: title, sub, badge, cls, rows, footer) + an optional sparkline.
   Never presents a value as a real reading: badge SIMULATED, caption on the first footer line, alignment caption on the second. */
function cardLines({sensor, element, typeName, sceneName, valueText, series, alignText}) {
  const clip = (t, n) => { t = String(t == null ? '' : t); return t.length > n ? t.slice(0, n - 1) + '…' : t; };
  const where = sensor.anchor.layer + ':' + sensor.anchor.id, el = element ? clip(element.name || element.type || 'Element', 40) : clip(sensor.anchor.name || where, 40);
  const rows = [valueText ? 'Simulated value: ' + valueText : 'Simulated value: no data',
    clip('Scenario (illustrative): ' + (sensor.reading && sensor.reading.value || ''), 80),
    'Anchored to BIM element ' + el + ' · ' + where];
  return {title: clip((sensor.k ? sensor.k + ' · ' : '') + sensor.label, 44), sub: clip([typeName, sceneName && 'scene ' + sceneName].filter(Boolean).join(' · '), 70),
    badge: BADGE, tier: 'SIMULATED', cls: 'mod', rows, footer: [CAPTION, clip(alignText || '', 140)],
    spark: Array.isArray(series) && series.length > 1 && series.every(finite) ? series.slice() : null, sparkColor: sensor.color || '#22d3ee'};
}

/* Deterministic sparkline from the demo simulator: n samples ending at nowMs, one per sampling interval.
   simulate = SensorFeed.simulate. Points the simulator cannot model are skipped. */
function simSeries(simulate, sensor, nowMs, n) {
  const out = [], iv = sensor.sampling_interval_s * 1000;
  for (let k = (n || 24) - 1; k >= 0; k--) {
    const o = simulate(sensor, nowMs - k * iv);
    if (o && o.quality !== 'missing' && finite(o.value)) out.push(o.value);
  }
  return out;
}

return {API, SCENES, SCENE_NAMES, DEFAULT_SCENE, CAPTION, BADGE, parseParams, nextScene, withState, mrDefaults, clusterCenter, demoArea, pinSize, pickPin, chipText, cardLines, simSeries};
});
