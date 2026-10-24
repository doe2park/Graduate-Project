/* Virtual-sensor DEMO layer (twin/sensor-demo.js + twin/sensor-demo.json, opt-in ?sensors=demo).
   Checks: the config is valid and honest (status, every anchor = a real sidecar element with the same name and
   source_guid), the pure helpers (colour map, DTS profile, element axis, card), and that both pages load the layer ONLY
   behind the ?sensors=demo guard (no request, no DOM, no render change without it). */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const root = path.join(__dirname, '..');
const read = f => fs.readFileSync(path.join(root, f), 'utf8');
const SD = require('../twin/sensor-demo.js');
const CFG = JSON.parse(read('twin/sensor-demo.json'));
const compare = read('scan-compare.html'), bim = read('scan-bim.html');
const OVERLAY_LAYERS = ['equipment', 'lighting', 'conduit', 'duct', 'hydronic', 'plumbing', 'lifesafety', 'fire'];
const sidecarFile = l => 'buildings/grimes/' + (l === 'equipment' ? 'elements.json' : l + '.elements.json');

test('config is a valid, explicitly illustrative demo file', () => {
  const v = SD.validateConfig(CFG);
  assert.deepEqual(v.errors, []);
  assert.equal(v.ok, true);
  assert.equal(CFG.status, 'illustrative-not-installed');
  assert.match(CFG.scope, /No sensors are installed/);
  assert.equal(v.sensors.length, CFG.sensors.length);
  /* the five deck scenarios, each with numbered sensors 1..n */
  const by = {};
  for (const s of CFG.sensors) (by[s.scenario] = by[s.scenario] || []).push(s.k);
  assert.deepEqual(Object.keys(by).sort(), ['fan', 'hvac', 'leak', 'power', 'water']);
  for (const [sc, ks] of Object.entries(by)) assert.deepEqual(ks, ks.map((_, i) => i + 1), sc);
  assert.ok(CFG.sensors.some(s => s.type === 'dts'), 'at least one DTS fibre');
});

test('every anchor is a real BIM element in an Overlay layer: sidecar id, exact name and source_guid', () => {
  const cache = {};
  for (const s of CFG.sensors) {
    const a = s.anchor;
    assert.ok(OVERLAY_LAYERS.includes(a.layer), s.id + ' layer is shown in Overlay');
    const els = cache[a.layer] || (cache[a.layer] = JSON.parse(read(sidecarFile(a.layer))).elements);
    const el = els[a.id];
    assert.ok(el, s.id + ': element ' + a.id + ' exists in ' + a.layer);
    assert.equal(el.name, a.name, s.id + ' name');
    assert.equal(el.source_guid, a.guid, s.id + ' guid');
    assert.equal(el.level, 'LEVEL 01', s.id + ' is on the captured floor');
  }
  /* the elements the deck slides describe */
  const leak = CFG.sensors.find(s => s.id === 'leak-dts');
  assert.equal(leak.anchor.name, 'Pipe219763');
  assert.match(cache.fire[leak.anchor.id].system, /^F-SPRN-MAIN/);
  assert.equal(cache.duct[CFG.sensors.find(s => s.id === 'hvac-airflow').anchor.id].type, 'Spiral duct');
  assert.match(cache.plumbing[CFG.sensors.find(s => s.id === 'water-puck').anchor.id].name, /^Charlotte No-Hub Coupling/);
  for (const s of CFG.sensors.filter(x => x.scenario === 'fan')) assert.equal(cache.duct[s.anchor.id].type, 'Rectangular duct', s.id + ': slide 11 is a straight rectangular duct');
});

test('validateConfig refuses malformed or dishonest entries', () => {
  const base = JSON.parse(JSON.stringify(CFG));
  assert.equal(SD.validateConfig({...base, status: 'installed'}).ok, false);
  assert.equal(SD.validateConfig({...base, schema: 'x'}).ok, false);
  const one = patch => { const c = JSON.parse(JSON.stringify(base)); Object.assign(c.sensors[1], patch); return SD.validateConfig(c); };
  for (const [what, patch] of [
    ['unknown type', {type: 'laser'}], ['bad id', {id: 'Bad ID'}], ['duplicate id', {id: base.sensors[0].id}],
    ['non-numeric element', {anchor: {layer: 'fire', id: 'abc'}}], ['unknown layer', {anchor: {layer: 'roof', id: '1'}}],
    ['offset too far', {anchor: {...base.sensors[1].anchor, offset: [0, 9, 0]}}], ['t out of range', {anchor: {...base.sensors[1].anchor, t: 1.5}}],
    ['no reading', {reading: {}}], ['bad colour', {color: 'red'}], ['link to nothing', {links: ['ghost']}]]) {
    const v = one(patch);
    assert.equal(v.ok, false, what);
    assert.ok(v.errors.length >= 1, what);
  }
  const c = JSON.parse(JSON.stringify(base)); c.sensors[0].dts.scaleC = [30, 20];
  assert.equal(SD.validateConfig(c).ok, false, 'inverted DTS scale');
  assert.equal(one({type: 'laser'}).sensors.length, base.sensors.length - 1, 'a bad entry is dropped, the rest survive');
});

test('opt-in parameter: only sensors=demo', () => {
  assert.equal(SD.parseSensorsParam('?sensors=demo&view=overlay'), 'demo');
  for (const q of ['', '?view=overlay', '?sensors=1', '?sensors=DEMO', '?sensors=demo2']) assert.equal(SD.parseSensorsParam(q), null, q);
});

test('temperature colour map and DTS profile: cool ends, hottest at the alert position', () => {
  assert.deepEqual(SD.colorAt(0), [30, 80, 220]);
  assert.deepEqual(SD.colorAt(1), [230, 30, 30]);
  assert.deepEqual(SD.colorAt(-3), SD.colorAt(0));
  assert.deepEqual(SD.colorAt(NaN), SD.colorAt(0));
  const d = CFG.sensors.find(s => s.type === 'dts').dts;
  const ts = Array.from({length: 101}, (_, i) => i / 100), vals = ts.map(t => SD.dtsTempC(t, d));
  const hot = ts[vals.indexOf(Math.max(...vals))];
  assert.ok(Math.abs(hot - d.hotT) <= 0.03, 'peak at hotT, got ' + hot);
  assert.ok(Math.abs(Math.max(...vals) - d.peakC) < 1.2, 'peak near peakC');
  assert.ok(SD.dtsValue(d.hotT, d) > 0.85 && SD.dtsValue(1, d) < 0.35 && SD.dtsValue(0, d) < 0.5);
  for (const t of ts) { const v = SD.dtsValue(t, d); assert.ok(v >= 0 && v <= 1); }
});

test('principal axis of a long element, parametric positions and offsets', () => {
  /* a 4 m "pipe" along (1,0,1)/sqrt2 with a 5 cm ring of vertices every 0.25 m */
  const dir = [Math.SQRT1_2, 0, Math.SQRT1_2], pos = [];
  for (let i = 0; i <= 16; i++) for (let k = 0; k < 8; k++) {
    const s = i * 0.25 - 2, a = k / 8 * 2 * Math.PI, r = 0.05;
    pos.push(10 + dir[0] * s + r * Math.cos(a) * Math.SQRT1_2, 3 + r * Math.sin(a), -5 + dir[2] * s - r * Math.cos(a) * Math.SQRT1_2);
  }
  const ax = SD.principalAxis(Float32Array.from(pos));
  assert.ok(Math.abs(Math.abs(ax.dir[0] * dir[0] + ax.dir[2] * dir[2]) - 1) < 1e-4, 'axis follows the pipe');
  assert.ok(ax.dir[0] > 0, 'canonical sign');
  assert.ok(Math.abs(ax.length - 4) < 0.02);
  const mid = SD.axisPoint(ax, 0.5);
  assert.ok(Math.hypot(mid[0] - 10, mid[1] - 3, mid[2] + 5) < 1e-3);
  for (const t of [0, 0.3, 0.82, 1]) assert.ok(Math.abs(SD.axisParam(SD.axisPoint(ax, t), ax) - t) < 1e-6, 't round trip ' + t);
  const p = SD.anchorPoint(ax, {t: 0.5, offset: [0, -0.45, 0]});
  assert.ok(Math.abs(p[1] - (3 - 0.45)) < 1e-3);
  assert.equal(SD.principalAxis([]), null);
  const ring = SD.zoneRing([1, 2, 3], 0.5, 12);
  assert.equal(ring.length, 12);
  for (const q of ring) { assert.ok(Math.abs(Math.hypot(q[0] - 1, q[2] - 3) - 0.5) < 1e-9); assert.equal(q[1], 2); }
});

test('card: Lens-card look, DEMO badge, illustrative note, BIM element mapping, escaped text', () => {
  const s = {...CFG.sensors[0], label: '<b>x</b>', reading: {value: 'v & "q"', detail: 'd'}};
  const html = SD.cardHtml(s, {name: 'Pipe219763', type: 'Pipe segment', system: 'F-SPRN-MAIN-N', level: 'LEVEL 01'});
  assert.match(html, /class="gz-top"/);
  assert.match(html, /gz-badge sd-demo">DEMO</);
  assert.match(html, /Maps to BIM element: <b>Pipe219763<\/b>/);
  assert.match(html, /fire:278123 · Pipe segment · F-SPRN-MAIN-N · LEVEL 01/);
  assert.match(html, /Illustrative value · no sensor installed/);
  assert.ok(!html.includes('<b>x</b>') && html.includes('&lt;b&gt;x&lt;/b&gt;'));
  assert.ok(html.includes('v &amp; &quot;q&quot;'));
  assert.match(html, /class="sd-grad"/, 'DTS card carries the colour scale');
  /* not yet attached: falls back to the configured anchor name, still says it is a BIM element */
  assert.match(SD.cardHtml(CFG.sensors[4], null), /Maps to BIM element: <b>Spiral Duct/);
  assert.match(SD.cardHtml(CFG.sensors.find(x => x.reading.series), null), /class="gz-spark"/);
  assert.equal(SD.BADGE_TEXT, 'Demo sensors — illustrative, not installed');
});

/* everything about the demo in a page must sit inside its ?sensors=demo guard */
function guarded(src, name) {
  const hits = [...src.matchAll(/sensor-demo|sensorDemo|SensorDemo/g)].map(m => m.index);
  assert.ok(hits.length > 0, name + ' has the hook');
  const guards = [...src.matchAll(/(if\s*\(|\?)[^;{]{0,120}get\('sensors'\)==='demo'/g)];
  assert.ok(guards.length >= 1, name + ' guard');
  return {hits, guards};
}
test('scan-compare.html: no static script tag, the BIM frame URL is unchanged without the parameter', () => {
  assert.ok(!/<script src="twin\/sensor-demo\.js/.test(compare), 'never a static <script src>');
  guarded(compare, 'scan-compare');
  const m = /frames\[1\]\.src=(.+?);\n/.exec(compare);
  assert.ok(m, 'BIM frame src');
  const src = q => vm.runInNewContext(m[1], {URLSearchParams, location: {search: q}, view: 'overlay'});
  assert.equal(src('?view=overlay'), 'scan-bim.html?pane=bim&revision=overlay2&overlay=1');
  assert.equal(src('?view=overlay&sensors=demo'), 'scan-bim.html?pane=bim&revision=overlay2&overlay=1&sensors=demo');
  assert.equal(src('?view=overlay&sensors=yes'), 'scan-bim.html?pane=bim&revision=overlay2&overlay=1');
  /* the loader block is the last script, behind the guard */
  const block = compare.slice(compare.lastIndexOf('/* SENSOR DEMO'));
  assert.match(block, /^\/\* SENSOR DEMO[\s\S]*?\nif\(new URLSearchParams\(location\.search\)\.get\('sensors'\)==='demo'\)\{[\s\S]*twin\/sensor-demo\.js/);
});

test('scan-bim.html: loader only for the BIM pane with sensors=demo; render loop calls a null hook otherwise', () => {
  assert.ok(!/<script src="twin\/sensor-demo\.js/.test(bim));
  const a = bim.indexOf('/* SENSOR DEMO'), b = bim.indexOf('let _lastT = 0');
  assert.ok(a > 0 && b > a, 'block sits right before the render loop');
  const block = bim.slice(a, b);
  assert.match(block, /let sensorDemo=null;\nif\(splitPane==='bim'&&new URLSearchParams\(location\.search\)\.get\('sensors'\)==='demo'\)\{/);
  for (const i of [...bim.matchAll(/sensor-demo\.js/g)].map(m => m.index)) assert.ok(i > a && i < b, 'script injected only inside the guarded block');
  assert.match(bim, /if \(typeof sensorDemo !== 'undefined' && sensorDemo\) sensorDemo\.frame\(\);/);
  assert.equal([...bim.matchAll(/sensorDemo\.frame\(\)/g)].length, 1);
});

test('the module is UMD and self-contained (loads in a bare context, registers SensorDemo)', () => {
  const ctx = {}; vm.createContext(ctx); vm.runInContext(read('twin/sensor-demo.js'), ctx);
  assert.equal(typeof ctx.SensorDemo.mountBim, 'function');
  assert.equal(typeof ctx.SensorDemo.mountParent, 'function');
});
