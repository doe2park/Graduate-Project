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
  assert.deepEqual(Object.keys(by).sort(), ['air', 'elec', 'leak', 'rotating', 'water']);
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
  for (const s of CFG.sensors.filter(x => x.scenario === 'rotating')) assert.equal(cache.duct[s.anchor.id].type, 'Rectangular duct', s.id + ': slide 11 is a straight rectangular duct');
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

test('per-type look: every used type has a short label, colour and icon; sensor colours follow their type', () => {
  for (const s of CFG.sensors) {
    const t = SD.typeStyle(CFG, s.type);
    assert.ok(t.short && t.short.length <= 12, s.type + ' short label');
    assert.equal(s.color, t.color, s.id + ' colour = type colour');
    assert.match(SD.iconSvg(t.icon, 16), /^<svg class="sd-ico" viewBox="0 0 24 24"[^>]*><path d="[^"]+"/);
  }
  const shorts = new Set(Object.values(CFG.types).map(t => t.short)), colors = new Set(Object.values(CFG.types).map(t => t.color));
  assert.equal(shorts.size, Object.keys(CFG.types).length, 'labels distinct');
  assert.equal(colors.size, Object.keys(CFG.types).length, 'colours distinct');
  const bad = JSON.parse(JSON.stringify(CFG)); bad.types.dts.icon = '<script>';
  assert.equal(SD.validateConfig(bad).ok, false, 'icon must be SVG path data');
});

test('phones / Quest: fire anchors name the fire chunk that really holds their element', () => {
  const fire = CFG.sensors.filter(s => s.anchor.layer === 'fire');
  assert.ok(fire.length >= 4 && fire.every(s => s.anchor.part), 'every fire anchor has a chunk hint');
  const chunks = JSON.parse(read('buildings/grimes/grimes-fire.chunks.json')).chunks.map(c => c.file);
  const names = {};
  for (const f of new Set(fire.map(s => s.anchor.part))) {
    assert.ok(chunks.includes(f), f + ' is a published fire chunk');
    const b = fs.readFileSync(path.join(root, 'buildings/grimes', f)), n = b.readUInt32LE(12);
    names[f] = new Set(JSON.parse(b.subarray(20, 20 + n).toString('utf8')).nodes.map(x => String(x.name)));
  }
  for (const s of fire) assert.ok(names[s.anchor.part].has(s.anchor.id), s.id + ': node ' + s.anchor.id + ' is in ' + s.anchor.part);
  /* the BIM pane's demo rule mirrors the Overlay skip rule exactly, and only exists inside the demo block */
  assert.match(bim, /if\(key==='fire'&&mobileQuality\)continue;/);
  const block = bim.slice(bim.indexOf('/* SENSOR DEMO'), bim.indexOf('let _lastT = 0'));
  assert.match(block, /const sdSkipped=key=>key==='fire'&&mobileQuality;/);
  assert.match(block, /skipped:k=>overlayOn&&sdSkipped\(k\),loadSubset:sdLoadSubset,/);
  assert.ok(!/layerState\[key\]\s*=/.test(block), 'the anchor subset never becomes the fire layer');
  const c = JSON.parse(JSON.stringify(CFG)); c.sensors[0].anchor.part = '../x.glb';
  assert.equal(SD.validateConfig(c).ok, false, 'part must be a plain chunk file name');
});

test('Lens centring on a sensor: pin position -> normalised Lens target, clamped to the viewport', () => {
  assert.deepEqual(SD.lensPoint([400, 300], 800, 600, 8), {x: 0.5, y: 0.5});
  assert.deepEqual(SD.lensPoint([200, 450], 800, 600, 0), {x: 0.25, y: 0.75});
  const q = SD.lensPoint([-50, 9999], 800, 600, 8);
  assert.deepEqual(q, {x: 8 / 800, y: (600 - 8) / 600}, 'off-screen pin clamps to the edge margin');
  assert.equal(SD.lensPoint([NaN, 1], 800, 600), null);
  assert.equal(SD.lensPoint([1, 1], 0, 600), null);
  /* the page wires it: a focused sensor locks the Lens, the mouse no longer moves it until released */
  assert.match(compare, /lens:\{set:\(x,y,w,h\)=>\{const q=SensorDemo\.lensPoint\(\[x,y\],w,h,8\);/);

  /* lag fix: pins are projected from the pose the page has just forwarded, re-drawn on each camera-pose message, Lens snaps */
  assert.match(compare, /getPose:\(\)=>poses\.bim&&valid\(poses\.bim\)\?poses\.bim:null,/);
  assert.match(compare, /e\.data\?\.type==='grimes-camera-pose'&&\(e\.source===frames\[0\]\.contentWindow\|\|e\.source===frames\[1\]\.contentWindow\)\)sd\.poseChanged\(\)/);
  assert.match(compare, /else lensTarget=q;layoutLens\(true\);/);
});

test('type chips: placed beside their pins without overlapping pins or each other', () => {
  const box = {x: 0, y: 0, w: 800, h: 500};
  const items = [[300, 200], [312, 206], [326, 214], [300, 230], [780, 490], [5, 5]].map(([x, y], i) => ({id: 's' + i, x, y, w: 74, h: 17}));
  const out = SD.placeChips(items, box, 14), rects = out.map(o => ({...o, w: 74, h: 17}));
  const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  for (let i = 0; i < rects.length; i++) {
    const r = rects[i];
    assert.ok(r.x >= 0 && r.y >= 0 && r.x + r.w <= 800 && r.y + r.h <= 500, 'inside the box ' + r.id);
    for (let j = i + 1; j < rects.length; j++) assert.ok(!hit(r, rects[j]), r.id + ' vs ' + rects[j].id);
    for (const p of items) assert.ok(!hit(r, {x: p.x - 14, y: p.y - 14, w: 28, h: 28}), r.id + ' clear of pin ' + p.id);
  }
});

test('Lens rests on the scene primary (or ?focus=), follows it, falls back sensibly', () => {
  const ids = s => CFG.sensors.filter(x => x.scenario === s).map(x => x.id);
  for (const sc of ['leak', 'air', 'water', 'elec', 'rotating']) {
    const p = SD.primaryFor(CFG, sc, null, ids(sc));
    assert.ok(p && ids(sc).includes(p), sc + ' has a primary in its scene');
  }
  assert.equal(SD.primaryFor(CFG, 'leak', null, ids('leak')), 'leak-alert');
  assert.equal(SD.primaryFor(CFG, 'leak', 'leak-puck', ids('leak')), 'leak-puck', '?focus= wins');
  assert.equal(SD.primaryFor(CFG, 'leak', 'hvac-airflow', ids('leak')), 'leak-alert', 'focus outside the scene is ignored');
  assert.equal(SD.primaryFor(CFG, null, null, CFG.sensors.map(x => x.id)), null, 'no scene, no focus: no auto-lock');
  assert.equal(SD.parseFocusParam('?focus=leak-dts'), 'leak-dts'); assert.equal(SD.parseFocusParam('?focus=<x>'), null);
  const bad = JSON.parse(JSON.stringify(CFG)); bad.primary.leak = 'hvac-airflow';
  assert.equal(SD.validateConfig(bad).ok, false, 'primary must belong to its scenario');
  const proj = {a: [100, 200, 1], b: [300, 400, 1], c: [999, -50, 1], d: [10, 10, 0]};
  assert.deepEqual(SD.lensAnchor('a', proj, ['a', 'b']), [100, 200]);
  assert.deepEqual(SD.lensAnchor('c', proj, ['a', 'b']), [999, -50], 'in front but off-screen: its point (lensPoint clamps to the edge)');
  assert.deepEqual(SD.lensAnchor('d', proj, ['a', 'b']), [200, 300], 'behind the camera: centroid of visible sensors');
  assert.equal(SD.lensAnchor('d', proj, []), null, 'nothing visible: stay');
  assert.deepEqual(SD.lensPoint([999, -50], 800, 600, 8), {x: 792 / 800, y: 8 / 600});
  assert.match(compare, /if\(window\.sdLensLock&&!\(window\.sdPointerMoved&&window\.sdPointerMoved\(\)\)\)return;/);
  assert.match(compare, /focus:SensorDemo\.parseFocusParam\(location\.search\),/);
});

test('opt-in parameter: only sensors=demo', () => {
  assert.equal(SD.parseSensorsParam('?sensors=demo&view=overlay'), 'demo');
  for (const q of ['', '?view=overlay', '?sensors=1', '?sensors=DEMO', '?sensors=demo2']) assert.equal(SD.parseSensorsParam(q), null, q);
});

test('scene filter: ?scene=<scenario> keeps only that scenario; absent = all; links stay inside the scene', () => {
  assert.equal(SD.parseSceneParam('?sensors=demo&scene=leak'), 'leak');
  for (const q of ['', '?scene=', '?scene=Leak!', '?scene=' + 'x'.repeat(40)]) assert.equal(SD.parseSceneParam(q), null, q);
  const all = SD.validateConfig(CFG).sensors;
  assert.equal(SD.filterScene(all, null).length, all.length);
  for (const sc of ['leak', 'air', 'water', 'elec', 'rotating']) {
    const f = SD.filterScene(all, sc), ids = new Set(f.map(s => s.id));
    assert.ok(f.length >= 3 && f.every(s => s.scenario === sc), sc);
    for (const s of f) for (const l of s.links || []) assert.ok(ids.has(l), sc + ' link ' + l);
  }
  assert.deepEqual(SD.filterScene(all, 'nope'), []);
  /* both pages pass the scene on: compare -> BIM frame URL, and to its own mount */
  assert.match(compare, /mountParent\(\{main:mainEl,frame:frames\[1\],sceneFilter:SensorDemo\.parseSceneParam\(location\.search\),/);
  assert.match(bim, /mountBim\(\{THREE,scene,camera,sceneFilter:window\.SensorDemo\.parseSceneParam\(location\.search\),/);
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
  assert.equal(src('?view=overlay&sensors=demo&scene=leak'), 'scan-bim.html?pane=bim&revision=overlay2&overlay=1&sensors=demo&scene=leak');
  assert.equal(src('?view=overlay&sensors=demo&scene=%3Cx%3E'), 'scan-bim.html?pane=bim&revision=overlay2&overlay=1&sensors=demo');
  assert.equal(src('?view=overlay&scene=leak'), 'scan-bim.html?pane=bim&revision=overlay2&overlay=1', 'scene alone does nothing');
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
