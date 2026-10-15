/* Shared element-card module (twin/element-cards.js): parity between the Walk gaze card in grimes-bim-viewer.html
   and the Overlay-Lens card (scan-bim.html picks, scan-compare.html renders), plus the lens pick message contract. */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const root = path.join(__dirname, '..');
const read = f => fs.readFileSync(path.join(root, f), 'utf8');
const SHARED = read('twin/element-cards.js'), viewer = read('grimes-bim-viewer.html'), bim = read('scan-bim.html'), compare = read('scan-compare.html');
const EC = require('../twin/element-cards.js');
function block(src, start, end) { const a = src.indexOf(start); assert.ok(a >= 0, start); const b = src.indexOf(end, a + start.length); assert.ok(b >= 0, end); return src.slice(a, b); }
function pageContext(src) {
  const ctx = {console, Date, Number, Intl, Map, Set, Math, document: {getElementById: () => ({style: {}, classList: {add() {}, remove() {}}})}};
  ctx.window = ctx; vm.createContext(ctx);
  vm.runInContext(SHARED, ctx);
  vm.runInContext(block(src, '/* ELEMENT DATA HELPERS */', '/* END ELEMENT DATA HELPERS */'), ctx);
  return ctx;
}
const nowIso = (off = 0) => new Date(Date.now() + off * 60000).toISOString();
const meters = {'77': {latest: {kw: 12.5, t: nowIso(-3)}}, '3': {latest: {kw: 40, t: nowIso(-200)}}, '76': {latest: {kw: null, t: nowIso()}}};
const feeds = {elements: {'42': [{ref: 'bmo:meter:77:kw', unit: 'kW', source: 'Panel CT 4'}], 'lighting:43': [{ref: 'bmo:meter:3:kw', source: 'old'}]}};
const cases = [
  ['42', {name: 'Panel', layer: 'equipment'}],
  ['43', {name: 'Light', layer: 'lighting'}],
  ['7', {name: 'Diffuser', type: 'Supply diffuser', system: 'HVAC', level: 'LEVEL 01', apportion: {meter: '3', basis: 'design CFM ratio', share: 0.002}}],
  ['8', {name: 'Linear', type: 'Linear fixture', system: 'Lighting', isFedBy: ['bmo:meter:76:kw']}],
  ['9', {name: 'Box', isFedBy: ['bmo:meter:77:kw', 'bmo:meter:3:kw']}],
  ['10', {name: 'Column'}],
];

test('both pages and the compare page load the one shared script; no page keeps its own copy', () => {
  for (const [name, src] of [['viewer', viewer], ['scan-bim', bim], ['scan-compare', compare]]) assert.match(src, /<script src="twin\/element-cards\.js"><\/script>/, name);
  for (const [name, src] of [['viewer', viewer], ['scan-bim', bim], ['scan-compare', compare]])
    for (const fn of ['elementFeedTier', 'gazeCardHtml', 'meterReading', 'bmoTimestamp', 'readingAgeText', 'gazeDwell', 'elementFeedEntry'])
      assert.doesNotMatch(src, new RegExp('function ' + fn + '\\('), name + ' defines ' + fn);
  // the viewer's shared script is a classic script loaded before its module
  assert.ok(viewer.indexOf('twin/element-cards.js') < viewer.indexOf('<script type="module">'));
  assert.ok(bim.indexOf('twin/element-cards.js') < bim.indexOf('<script type="module">'));
});

test('tier and card HTML are identical in the viewer, the BIM pane and the module itself', () => {
  const v = pageContext(viewer), b = pageContext(bim);
  for (const [id, meta] of cases) {
    const ref = EC.elementFeedTier(id, meta, feeds, meters);
    assert.deepEqual(JSON.parse(JSON.stringify(v.elementFeedTier(id, meta, feeds, meters))), ref, 'viewer ' + id);
    assert.deepEqual(JSON.parse(JSON.stringify(b.elementFeedTier(id, meta, feeds, meters))), ref, 'scan-bim ' + id);
    assert.equal(v.gazeCardHtml(id, meta, ref), EC.gazeCardHtml(id, meta, ref));
  }
  assert.deepEqual(cases.map(([id, m]) => EC.elementFeedTier(id, m, feeds, meters).tier), ['LIVE', 'LATEST', 'MODELLED', 'CONTEXT', 'CONTEXT', 'NONE']);
});

test('tier labels stay honest: CONTEXT/MODELLED never LIVE, missing never zero', () => {
  for (const [id, meta] of cases) {
    const t = EC.elementFeedTier(id, meta, feeds, {});
    assert.notEqual(t.tier, 'LIVE'); assert.doesNotMatch(t.valueText, /\b0\.0|NaN|undefined/);
  }
  const ctx = EC.elementFeedTier('8', cases[3][1], feeds, meters);
  assert.match(ctx.detailText, /not this element’s own reading/);
});

test('card adds an as-built line only for an applied adjustment, labelled manual and not surveyed', () => {
  const meta = cases[2][1], tier = EC.elementFeedTier('7', meta, feeds, meters);
  const plain = EC.gazeCardHtml('7', meta, tier);
  assert.doesNotMatch(plain, /gz-adj|As-built/);
  assert.equal(EC.gazeCardHtml('7', meta, tier, {}), plain);
  const adj = EC.gazeCardHtml('7', meta, tier, {adjustment: {translation: [0.12, 0, -0.05], yawDegrees: 1}});
  assert.match(adj, /As-built · manual, not surveyed · moved 13 cm · yaw 1\.0°/);
  assert.equal(EC.adjustmentLine({translation: [NaN, 0, 0]}), '');
});

test('lens probe: normalised coordinates only', () => {
  assert.deepEqual(EC.lensProbeMessage(3, .5, .25), {type: 'grimes-lens-probe', seq: 3, x: .5, y: .25});
  for (const bad of [[1.5, 0.5], [-0.1, 0.5], [NaN, 0.5], ['0.5', 0.5]]) assert.equal(EC.lensProbeMessage(1, ...bad), null);
  assert.equal(EC.lensProbeMessage(1.5, .5, .5), null);
  assert.equal(EC.parseLensProbe({type: 'grimes-lens-probe', seq: 2, x: .1, y: .9}).seq, 2);
  assert.equal(EC.parseLensProbe({type: 'grimes-pointer', x: .1, y: .1}), null);
});

test('lens pick: round trip, whitelisted meta, derived class, stale replies dropped', () => {
  const info = {name: 'Diffuser <b>', type: 'Supply diffuser', system: 'HVAC', level: 'LEVEL 01', isFedBy: ['x'], apportion: {meter: '3'}, source_guid: 'secret-ish'};
  const tier = EC.elementFeedTier('7', {...info, apportion: {meter: '3', share: .002}}, {}, meters);
  const msg = EC.lensPickMessage({seq: 9, x: .5, y: .5, id: '7', layer: 'duct', info, tier: {...tier, cls: 'live" onclick="x'}, adjustment: {translation: [.1, 0, 0], yawDegrees: 0}});
  assert.equal(msg.type, 'grimes-lens-pick');
  assert.deepEqual(Object.keys(msg.hit.meta).sort(), ['layer', 'level', 'name', 'system', 'type']);
  assert.equal(msg.hit.tier.cls, 'mod');
  const back = EC.parseLensPick(JSON.parse(JSON.stringify(msg)), 8);
  assert.equal(back.hit.id, '7'); assert.equal(back.hit.layer, 'duct'); assert.equal(back.hit.tier.tier, 'MODELLED'); assert.equal(back.hit.adjustment.status, 'manual-unsurveyed');
  assert.equal(EC.parseLensPick(msg, 9), null, 'same seq is stale'); assert.equal(EC.parseLensPick(msg, 12), null, 'older seq is stale');
  assert.deepEqual(EC.parseLensPick(EC.lensPickMessage({seq: 10, x: .2, y: .3}), 9), {seq: 10, x: .2, y: .3, hit: null});
  for (const bad of [{...msg, hit: {...msg.hit, tier: {tier: 'MEASURED'}}}, {...msg, hit: {...msg.hit, layer: '../x'}}, {...msg, x: 2}, {...msg, type: 'grimes-pointer'}, null])
    assert.equal(EC.parseLensPick(bad, 0), null);
  const noTier = EC.lensPickMessage({seq: 11, x: .5, y: .5, id: '7', layer: 'duct', info, tier: null});
  assert.equal(noTier.hit, null, 'a hit without an honest tier is not shown');
});

test('lens card placement: right of the ring, flips at the edge, mobile sits above the bottom controls', () => {
  const base = {r: 100, w: 200, h: 90, vw: 1600, vh: 900};
  assert.deepEqual(EC.lensCardPosition({...base, cx: 800, cy: 450}), {x: 914, y: 405});
  const flipped = EC.lensCardPosition({...base, cx: 1450, cy: 450});
  assert.ok(flipped.x + base.w <= 1450 - 100);
  const m = EC.lensCardPosition({...base, vw: 390, vh: 844, cx: 195, cy: 400, mobile: true, bottomInset: 120});
  assert.equal(m.y + base.h, 844 - 120 - 8); assert.equal(m.x, 95);
});

test('wiring: BIM pane answers lens probes; compare page renders the card with the shared module', () => {
  assert.match(bim, /ElementCards\.parseLensProbe\(/);
  assert.match(bim, /ElementCards\.lensPickMessage\(/);
  assert.match(compare, /ElementCards\.parseLensPick\(/);
  assert.match(compare, /ElementCards\.gazeDwell\(/);
  assert.match(compare, /ElementCards\.gazeCardHtml\(/);
  assert.match(compare, /id="lensCard"/);
});
