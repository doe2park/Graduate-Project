/* Data-honesty regression tests for grimes-bim-viewer.html.
   Same vm-sandbox approach as viewer.test.cjs: code blocks are cut out of the
   page between marker strings and run against a fake DOM. */
const {test} = require('node:test'); const assert = require('node:assert/strict');
const fs = require('fs'), vm = require('vm'), path = require('path');
const source = fs.readFileSync(process.env.VIEWER || path.join(__dirname, '../grimes-bim-viewer.html'), 'utf8');
function block(start, end) {
  const a = source.indexOf(start); assert.ok(a >= 0, 'marker missing: ' + start);
  const b = source.indexOf(end, a + start.length); assert.ok(b >= 0, 'end marker missing: ' + end);
  return source.slice(a, b);
}
function makeEl() {
  return {style: {}, dataset: {}, children: [], className: '', innerHTML: '', textContent: '', value: '', hidden: false, disabled: false,
    classList: {_s: new Set(), add(...c) { c.forEach(x => this._s.add(x)); }, remove(...c) { c.forEach(x => this._s.delete(x)); }, toggle(c, f) { (f ?? !this._s.has(c)) ? this._s.add(c) : this._s.delete(c); }, contains(c) { return this._s.has(c); }},
    setAttribute(k, v) { this['attr:' + k] = v; }, removeAttribute(k) { delete this['attr:' + k]; },
    append(...a) { this.children.push(...a); }, appendChild(a) { this.children.push(a); }, replaceChildren() { this.children = []; },
    getContext() { return {clearRect() {}}; }, addEventListener() {}};
}
function sandbox(extra = {}) {
  const dom = new Map(); const get = id => { if (!dom.has(id)) dom.set(id, makeEl()); return dom.get(id); };
  const ctx = {document: {getElementById: get, createElement: makeEl, createTextNode: t => ({text: String(t)}), body: {classList: {add() {}, remove() {}}}},
    console: {log() {}, warn() {}, error() {}}, Date, Number, Intl, Map, Set, setTimeout, clearTimeout, ...extra};
  ctx.window = ctx;
  vm.createContext(ctx);
  return {ctx, get, run: code => vm.runInContext(code, ctx)};
}
const nowIso = (offsetMin = 0) => new Date(Date.now() + offsetMin * 60000).toISOString();
const HELPERS = () => block('/* ELEMENT DATA HELPERS */', '/* END ELEMENT DATA HELPERS */');
const CORE = ['SYSTEMS', 'NAME_TO_SYS', 'NORM'];

/* ─────────── pickSystem fixtures ─────────── */
function systemFixture({points, values, water} = {}) {
  const s = sandbox({
    cachedJson: async url => (/building_data/.test(url) ? {water} : {}),
    TwinResolver: {
      resolveNode: () => ({bound: true, uri: 'grimes:Sys.X', type: 'brick:Electrical_System', feeders: [], points}),
      fetchValues: async () => values,
    },
    twinPkg: {brick: {entities: {}}}, highlight() {}, unhighlightEquip() {}, loadMeterHistory() {}, renderFlowHeadline() {}, renderBaseline() {}, renderEquip() {},
    sparks: [],
  });
  s.ctx.drawSpark = (cv, series) => s.ctx.sparks.push(series);
  s.run(block('const SYSTEMS = [', 'const draco'));
  s.run(HELPERS());
  s.run('const esc = x => String(x).replace(/[&<>"\']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",\'"\':"&quot;","\'":"&#39;"}[c]));const dsec = t => t;const drow = (k, v) => k + ":" + v;');
  s.run(block('const CHANNELS = {', '// Building-level panel'));
  s.run(block('async function pickSystem(', '/* ── DESIGN EQUIPMENT'));
  return s;
}
const mesh = name => ({name, parent: null});

test('bug1: summed feeder kW never becomes a green live Power sensor of the system', async () => {
  const {ctx, get} = systemFixture({points: [{ref: 'a'}], values: {a: {value: 50, ts: nowIso(), name: 'M77', series: []}}});
  await ctx.pickSystem(mesh('HVAC Equipment'));
  const html = get('twinPoints').innerHTML;
  assert.doesNotMatch(html, /livedot/);
  assert.match(html, /Power \(kW\)<\/span><span>— not connected/);
  assert.match(html, /Building meter context/);
});

test('bug2: Electrical mesh label is not "Spiral Ductwork" and agrees with binding.json', () => {
  const {ctx, run} = sandbox(); run(block('const SYSTEMS = [', 'const draco'));
  const sys = vm.runInContext('SYSTEMS', ctx).find(s => s.name === 'Electrical');
  assert.ok(sys); assert.doesNotMatch(sys.label, /spiral|duct/i); assert.match(sys.label, /electrical/i);
  const binding = JSON.parse(fs.readFileSync(path.join(__dirname, '../buildings/grimes/binding.json'), 'utf8'));
  assert.equal(binding.nodes.Electrical, 'grimes:Sys.Electrical');
  assert.match(source, /'Electrical': 'elec'/);
});

/* ─────────── flow headline ─────────── */
function flowFixture(water) {
  const s = sandbox({cachedJson: async () => ({water}), charts: []});
  s.run(HELPERS());
  s.ctx.drawFlowChart = (cv, series) => s.ctx.charts.push(series);
  s.run('const CHARTKEY_FLOW="";');
  s.run(block('async function renderFlowHeadline(', 'function drawFlowChart('));
  return s;
}
test('bug3: missing flow channels are not LIVE and not zero', async () => {
  const {ctx, get} = flowFixture({latest: {timestamp: nowIso()}, timeseries_water: []});
  await ctx.renderFlowHeadline();
  assert.doesNotMatch(get('twinBadge').textContent, /LIVE/); assert.doesNotMatch(get('twinBigKw').innerHTML, /0\.0/);
  assert.match(get('twinBigKw').innerHTML, /—/); assert.match(get('twinSrc').textContent, /No reading in this window/);
});
test('bug3: one of two water channels is PARTIAL, not LIVE', async () => {
  const {ctx, get} = flowFixture({latest: {timestamp: nowIso(), water1_rate_cfm: 2}, timeseries_water: []});
  await ctx.renderFlowHeadline();
  assert.equal(get('twinBadge').textContent, 'PARTIAL'); assert.match(get('twinBigKw').innerHTML, /^15\.0/); assert.match(get('twinSrc').textContent, /1 of 2/);
});
test('bug3: old flow reading is a grey LATEST with age text', async () => {
  const {ctx, get} = flowFixture({latest: {timestamp: nowIso(-180), water1_rate_cfm: 2, water2_rate_cfm: 1}, timeseries_water: []});
  await ctx.renderFlowHeadline();
  assert.equal(get('twinBadge').textContent, 'LATEST'); assert.equal(get('twinBadge').className, 'badge na');
  assert.match(get('twinSrc').textContent, /Last reading \d\d:\d\d · 3h ago/);
});
test('bug3: fresh complete flow is LIVE; steam/irrigation missing show em dash; chart has gaps not zeros', async () => {
  const {ctx, get} = flowFixture({latest: {timestamp: nowIso(), water1_rate_cfm: 2, water2_rate_cfm: 1, steam_rate_gpm: null},
    timeseries_water: [{t: '2026-01-01 00:00', v: 1}, {t: '2026-01-01 00:15', v: null}, {t: '2026-01-01 00:30', v: 0}]});
  await ctx.renderFlowHeadline();
  assert.equal(get('twinBadge').textContent, 'LIVE');
  assert.match(get('twinBigKw').innerHTML, /^22\.4/);
  assert.match(get('twinEvent').innerHTML, /Steam condensate[\s\S]*—/); assert.doesNotMatch(get('twinEvent').innerHTML, /0\.0 GPM/);
  const series = ctx.charts[0]; assert.equal(series[1].v, null); assert.equal(series[2].v, 0);
});

/* ─────────── system total power ─────────── */
test('bug4: partial system meters show "n of m meters" and no full total', async () => {
  const {ctx, get} = systemFixture({points: [{ref: 'a'}, {ref: 'b'}], values: {a: {value: 10, ts: nowIso(), series: []}, b: {error: 'meter missing'}}});
  await ctx.pickSystem(mesh('Conduit'));
  const html = get('twinPoints').innerHTML;
  assert.match(html, /1 of 2 meters/); assert.doesNotMatch(html, /#34d399/);
  assert.doesNotMatch(html, /Total[^<]*<\/span><span class="v"[^>]*>10\.0/);
});
test('bug4: complete live meters are LIVE green; old ones are neutral LATEST with age', async () => {
  let f = systemFixture({points: [{ref: 'a'}], values: {a: {value: 10, ts: nowIso(), series: []}}});
  await f.ctx.pickSystem(mesh('Conduit'));
  assert.match(f.get('twinPoints').innerHTML, /LIVE/);
  f = systemFixture({points: [{ref: 'a'}], values: {a: {value: 10, ts: nowIso(-240), series: []}}});
  await f.ctx.pickSystem(mesh('Conduit'));
  const html = f.get('twinPoints').innerHTML;
  assert.match(html, /LATEST/); assert.match(html, /Last reading \d\d:\d\d · 4h ago/); assert.doesNotMatch(html, /#34d399/); assert.doesNotMatch(html, /STALE|ERROR|FAILED/);
});

/* ─────────── element card headline ─────────── */
function elementFixture(meters, info, extra = {}) {
  const s = sandbox({
    equipMeta: {'123': {name: 'x', type: 'Receptacle', layer: 'fixtures', ...info}}, equipMeshes: [], LAYERS: {fixtures: {json: 'f.json'}},
    cachedJson: async () => ({meters}), highlight() {}, unhighlightEquip() {}, drawSpark() {}, highlightElementRender() {},
    EQUIP_LABELS: {}, revitRows: () => '', carbonRows: () => '', loadMeterHistory() {}, ...extra,
  });
  s.run('const esc = x => String(x).replace(/[&<>"\']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",\'"\':"&quot;","\'":"&#39;"}[c]));const dsec = t => t;const drow = (k, v) => k + ":" + v;');
  s.run(HELPERS());
  s.run(block('function resolveElementHit(', '// An element is selected only when'));
  s.run(block('function neighbourRows(', '\nfunction apportionRow('));
  s.run(block('function apportionRow(', '\nasync function pickEquipment('));
  s.run(block('async function pickEquipment(', '\nfunction drawSpark('));
  s.ctx.loadMeterHistory = () => {};
  return s;
}
const FEED77 = ['bmo:meter:77:kw'];
test('bug5: level-inferred feeder total is "Feeder context" with a non-green badge', async () => {
  const {ctx, get} = elementFixture({'77': {latest: {kw: 5, t: nowIso()}}}, {isFedBy: FEED77, feedSource: 'level-inferred'});
  await ctx.pickEquipment({userData: {ids: ['123']}}, 0);
  assert.match(get('twinBigKw').innerHTML, /[Ff]eeder context/); assert.notEqual(get('twinBadge').className, 'badge'); assert.notEqual(get('twinBadge').textContent, 'LIVE');
});
test('bug5: when apportion exists the MODELLED share is the headline', async () => {
  const ap = {meter: '77', share: 0.1, basis: 'VA', weight: 1, pool: 10};
  const {ctx, get} = elementFixture({'77': {latest: {kw: 5, t: nowIso()}}}, {isFedBy: FEED77, feedSource: 'revit-voltage', apportion: ap});
  await ctx.pickEquipment({userData: {ids: ['123']}}, 0);
  assert.match(get('twinBigKw').innerHTML, /≈ 500 W/); assert.match(get('twinBigKw').innerHTML, /[Mm]odelled share/);
  assert.equal(get('twinBadge').textContent, 'MODELLED'); assert.match(get('twinPoints').innerHTML, /Building meter context/);
});
test('bug5: old meter reading is grey LATEST and no green badge', async () => {
  const {ctx, get} = elementFixture({'77': {latest: {kw: 5, t: nowIso(-300)}}}, {isFedBy: FEED77, feedSource: 'level-inferred'});
  await ctx.pickEquipment({userData: {ids: ['123']}}, 0);
  assert.doesNotMatch(get('twinPoints').innerHTML, /STALE|ERROR|FAILED/); assert.match(get('twinPoints').innerHTML, /Last reading \d\d:\d\d · 5h ago/);
});

test('bug6: apportionRow reuses meterReading; NaN/strings never render', () => {
  const {ctx} = elementFixture({}, {});
  const info = share => ({apportion: {meter: '77', share, basis: 'VA', weight: 1, pool: 2}});
  for (const kw of [NaN, 'abc', null, undefined, Infinity]) {
    const out = ctx.apportionRow(info(0.5), {'77': {latest: {kw, t: nowIso()}}});
    assert.doesNotMatch(out, /NaN|Infinity|undefined/); assert.match(out, /—/); assert.match(out, /No reading in this window/);
  }
  assert.doesNotMatch(ctx.apportionRow(info(NaN), {'77': {latest: {kw: 4, t: nowIso()}}}), /NaN/);
  assert.match(ctx.apportionRow(info(0.5), {'77': {latest: {kw: 4, t: nowIso()}}}), /≈ 2\.00 kW/);
  const old = ctx.apportionRow(info(0.5), {'77': {latest: {kw: 4, t: nowIso(-600)}}});
  assert.match(old, /Last reading \d\d:\d\d · 10h ago/); assert.doesNotMatch(old, /offline/i);
  assert.match(ctx.apportionRow(info(0.5), {'77': {latest: {kw: 0, t: nowIso()}}}), /≈ 0 W/);
});

test('bug7: system sparkline sums meters aligned on timestamp, not position', async () => {
  const mk = ts => ts.map(([t, v]) => ({t, v}));
  const A = mk([['2026-01-01T00:00:00Z', 1], ['2026-01-01T00:15:00Z', 2], ['2026-01-01T00:30:00Z', 3]]);
  const B = mk([['2026-01-01T00:15:00Z', 20], ['2026-01-01T00:30:00Z', 30], ['2026-01-01T00:45:00Z', 40]]);
  const f = systemFixture({points: [{ref: 'a'}, {ref: 'b'}], values: {a: {value: 3, ts: nowIso(), series: A}, b: {value: 30, ts: nowIso(), series: B}}});
  await f.ctx.pickSystem(mesh('Conduit'));
  const last = f.ctx.sparks.at(-1);
  assert.deepEqual([...last.map(p => p.v)], [22, 33]);
});

/* ─────────── identity: no fallback to element 0 ─────────── */
test('bug8: unresolved multi-element line hit selects nothing', async () => {
  const {ctx, get} = elementFixture({}, {}); ctx.equipMeta['456'] = {name: 'y', type: 'Pipe', layer: 'fixtures'};
  await ctx.pickEquipment({userData: {ids: ['123', '456'], isLine: true}}, undefined);
  assert.equal(ctx.equipPicked ?? null, null); assert.equal(get('twinTitle').textContent, '');
});
test('bug8: single-element line mesh still resolves; resolved hit picks, unresolved hit falls through', async () => {
  const {ctx} = elementFixture({}, {}); await ctx.pickEquipment({userData: {ids: ['123'], isLine: true}}, undefined); assert.equal(ctx.equipPicked?.id, '123');
  const picked = []; const s = sandbox({picked, pickEquipment: (...a) => picked.push(a)});
  s.run(block('function resolveElementHit(', 'function highlightElementRender('));
  s.run(block('function pickResolvedEquipmentHit(', '\n}\n') + '\n}\n');
  const multi = {userData: {ids: ['a', 'b'], isLine: true, ranges: [{id: 'a', vertexStart: 0, vertexCount: 2}, {id: 'b', vertexStart: 2, vertexCount: 2}]}, isLine: true};
  assert.equal(s.ctx.pickResolvedEquipmentHit({object: multi, index: 9}), false); assert.equal(s.ctx.picked.length, 0);
  assert.equal(s.ctx.pickResolvedEquipmentHit({object: multi, index: 2}), true); assert.equal(s.ctx.picked[0][2], 'b');
});

/* ─────────── no inline onclick with interpolated ids ─────────── */
test('bug9: neighbour rows use data-element-id and a delegated listener', () => {
  const {ctx} = elementFixture({}, {});
  ctx.equipMeta = {a: {type: 'Pipe', level: 'LEVEL 01'}, 'c\'),alert(1),(\'': {type: 'Pipe', level: 'LEVEL 01'}};
  const html = ctx.neighbourRows('a', ctx.equipMeta.a);
  assert.doesNotMatch(html, /onclick/); assert.match(html, /data-element-id="c&#39;\),alert\(1\),\(&#39;"/);
  const row = {dataset: {elementId: 'zz'}}; assert.equal(ctx.delegatedElementId({closest: sel => (sel === '[data-element-id]' ? row : null)}), 'zz');
  assert.equal(ctx.delegatedElementId({closest: () => null}), null);
  assert.match(source, /twinDetEquip'\)\.addEventListener\('click'/);
});

/* ─────────── layers: bulk confirm / failures / legend / floors ─────────── */
function bulkFixture({mobile = true, confirmResult = true, layers} = {}) {
  const els = new Map(); const get = id => { if (!els.has(id)) els.set(id, makeEl()); return els.get(id); };
  const s = sandbox({
    LAYERS: layers || {a: {mb: 3}, b: {mb: 4}, c: {mb: 85.9}}, layerState: {}, mepModel: {visible: true}, equipTypeFilter: null, equipLevelFilter: null,
    mobileMq: {matches: mobile}, confirms: [], started: [], clearPick() {}, applyEquipFilter() {}, buildEquipFilter() {},
  });
  s.ctx.document.getElementById = get; s.ctx.window = s.ctx;
  s.ctx.confirm = msg => { s.ctx.confirms.push(msg); return confirmResult; };
  s.ctx.toggleLayer = key => { s.ctx.started.push(key); const st = s.ctx.layerState[key]; st.group = {visible: true}; return Promise.resolve(true); };
  s.run(block('// Bulk visibility is independent', 'window.toggleEquipment'));
  return {...s, get};
}
test('bug10: mobile "Show all elements" asks once, with total MB, and declining loads nothing', async () => {
  const f = bulkFixture({confirmResult: false});
  await f.ctx.setAllElements(true);
  assert.equal(f.ctx.confirms.length, 1); assert.match(f.ctx.confirms[0], /92\.9 MB/); assert.deepEqual(f.ctx.started, []);
  const g = bulkFixture({confirmResult: true}); await g.ctx.setAllElements(true);
  assert.equal(g.ctx.confirms.length, 1); assert.deepEqual(g.ctx.started, ['a', 'b', 'c']);
  const d = bulkFixture({mobile: false}); await d.ctx.setAllElements(true); assert.equal(d.ctx.confirms.length, 0);
});
test('bug13: show-all hides the MEP overview legend too', async () => {
  const f = bulkFixture({mobile: false}); await f.ctx.setAllElements(true);
  assert.equal(f.get('legend').style.display, 'none');
});

function toggleFixture(failFirst) {
  const els = new Map(); const get = id => { if (!els.has(id)) { const e = makeEl(); e.innerHTML = '🏗 Structure <small>12.9 MB · 2,420</small>'; els.set(id, e); } return els.get(id); };
  let calls = 0;
  const s = sandbox({LAYERS: {structural: {glb: 'g', json: 'j', label: '🏗 Structure', mb: 12.9}}, layerState: {}, mobileMq: {matches: false},
    cachedJson: async () => { calls++; if (failFirst && calls === 1) throw new Error('network'); throw new Error('stop after meta'); }, updateAllElementsButton() {}});
  s.ctx.document.getElementById = get;
  s.run(block('window.toggleLayer = (key', '// Bulk visibility') .replace(/^window\.toggleLayer = /, 'var toggleLayer = ') );
  return {...s, get, calls: () => calls};
}
test('bug11: failed layer load records st.error and shows a quiet retry on the layer control', async () => {
  const f = toggleFixture(true);
  await f.run('toggleLayer("structural")');
  const st = f.ctx.layerState.structural; assert.ok(st.error); assert.equal(st.loading, false);
  const btn = f.get('layerBtn-structural');
  assert.match(btn.innerHTML, /Tap to retry/); assert.match(btn.innerHTML, /12\.9 MB/); assert.doesNotMatch(btn.innerHTML, /error|failed/i);
  await f.run('toggleLayer("structural")'); assert.equal(f.calls(), 2);   // retry re-attempts the load
});
test('bug11: status line reports "n not loaded · tap to retry" neutrally', () => {
  const f = bulkFixture({mobile: false, layers: {a: {mb: 1}, b: {mb: 1}}});
  f.ctx.layerState.a = {error: new Error('x')}; f.ctx.layerState.b = {group: {visible: true}};
  f.run('updateAllElementsButton()');
  const t = f.get('allElementsStatus').textContent; assert.match(t, /1 not loaded · tap to retry/); assert.doesNotMatch(t, /error|fail/i);
});

test('bug12: Unknown floor filter keeps working in element selection and the mobile list', async () => {
  const picked = [];
  const unknown = {name: 'u', type: 'Pipe', layer: 'a', levelKey: 'UNKNOWN'};
  const s = sandbox({equipMeta: {u: unknown}, equipMeshes: [{isInstancedMesh: true, userData: {ids: ['u'], layer: 'a'}}], layerState: {a: {group: {visible: true}}},
    toggleLayer() {}, applyEquipFilter() {}, buildEquipFilter() {}, picked, pickEquipment: (...a) => picked.push(a)});
  s.run(HELPERS()); s.run(block('function findElementSelection(', '/* Call in finally'));
  s.run("let equipLevelFilter='UNKNOWN',equipTypeFilter=null;");
  s.run(block('window.selectElementById = ', '\nfunction neighbourRows('));
  s.ctx.selectElementById('u');
  assert.equal(s.ctx.picked.length, 1); assert.equal(s.run('equipLevelFilter'), 'UNKNOWN');
  s.run("var equipMeta=" + JSON.stringify({u: unknown, k: {name: 'k', layer: 'a', level: 'LEVEL 01'}}) + ";var layerState={a:{group:{visible:true}}};");
  s.get('mobileElementSearch').value = ''; s.run(block('function renderMobileElements(', 'document.getElementById(\'mobileBrowse\')'));
  s.run('renderMobileElements()');
  assert.equal(s.get('mobileElementResults').children.length, 1); assert.equal(s.get('mobileElementResults').children[0].dataset.elementId, 'u');
});

/* ─────────── static markup ─────────── */
test('bug14: layer button labels agree with LAYERS sizes and sidecar element counts', () => {
  const layers = source.match(/const LAYERS = \{[\s\S]*?\n\};/)[0];
  for (const m of layers.matchAll(/^\s+(\w+):\s+\{[^\n]*json: '([^']+)'[^\n]*mb: ([0-9.]+)/gm)) {
    const [, key, json, mb] = m;
    const btn = source.match(new RegExp('id="layerBtn-' + key + '"[^>]*>[^<]*<small>([^<]+)</small>'));
    assert.ok(btn, 'button for ' + key);
    const count = Object.keys(JSON.parse(fs.readFileSync(path.join(__dirname, '..', json), 'utf8')).elements).length;
    assert.equal(btn[1], `${mb} MB · ${count.toLocaleString('en-US')}`, key);
  }
});
test('bug15: baseline chart does not block vertical page scrolling on phones', () => {
  assert.match(source, /_baseCv\.style\.touchAction = 'pan-y'/); assert.doesNotMatch(source, /_baseCv\.style\.touchAction = 'none'/);
});

/* ─────────── baseline age gate ─────────── */
function ptStamp(offsetMin) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-US', {timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'})
    .formatToParts(new Date(Date.now() + offsetMin * 60000)).map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;
}
function baselineFixture(ts) {
  const recent = [{ts: '2026-01-01 00:00', kw: 100, base: 100, z: 0}, {ts: '2026-01-01 01:00', kw: 101, base: 100, z: 0.1}];
  const eb = {z_threshold: 3, buildings: {grimes: {sigma: 5, recent24: recent, current: {kw: 100, base: 100, z: 0, anomaly: false, ts}, events: []}}};
  const s = sandbox({cachedJson: async url => { if (/energy_baseline/.test(url)) return eb; throw new Error('absent'); },
    drawBaseChart(cv) { cv._chart = {}; }});
  s.run(HELPERS()); s.run('const CHARTKEY_POWER="";const esc=x=>String(x);function fmtEvTime(s){return s;}');
  s.run(block('async function renderBaseline(', 'function drawBaseChart('));
  return s;
}
test('bug16: stale baseline "current" is a neutral LATEST, never "Normal for this hour"', async () => {
  const old = baselineFixture(ptStamp(-300)); await old.ctx.renderBaseline();
  assert.equal(old.get('twinBadge').textContent, 'LATEST'); assert.equal(old.get('twinBadge').className, 'badge na');
  assert.match(old.get('twinSrc').textContent, /Last reading \d\d:\d\d · 5h ago/); assert.doesNotMatch(old.get('twinRange').innerHTML, /Typical for this hour/);
  const fresh = baselineFixture(ptStamp(-5)); await fresh.ctx.renderBaseline();
  assert.equal(fresh.get('twinBadge').textContent, 'Normal for this hour');
});
