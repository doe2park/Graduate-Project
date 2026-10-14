/* AR gaze card: feed-tier resolution, dwell logic and card HTML.
   Same vm-sandbox pattern as viewer-honesty.test.cjs (blocks cut out of the page). */
const {test} = require('node:test'); const assert = require('node:assert/strict');
const fs = require('fs'), vm = require('vm'), path = require('path');
const source = fs.readFileSync(process.env.VIEWER || path.join(__dirname, '../grimes-bim-viewer.html'), 'utf8');
function block(start, end) {
  const a = source.indexOf(start); assert.ok(a >= 0, 'marker missing: ' + start);
  const b = source.indexOf(end, a + start.length); assert.ok(b >= 0, 'end marker missing: ' + end);
  return source.slice(a, b);
}
function load() {
  const ctx = {console, Date, Number, Intl, Map, Set, Math, document: {getElementById: () => ({style: {}, classList: {add() {}, remove() {}, toggle() {}}})}};
  ctx.window = ctx; vm.createContext(ctx);
  vm.runInContext('const esc = s => String(s).replace(/[&<>"\']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",\'"\':"&quot;","\'":"&#39;"}[c]));', ctx);
  vm.runInContext(block('/* ELEMENT DATA HELPERS */', '/* END ELEMENT DATA HELPERS */'), ctx);
  return ctx;
}
const nowIso = (offMin = 0) => new Date(Date.now() + offMin * 60000).toISOString();
const meters = (kw = 12.5, off = 0) => ({'77': {latest: {kw, t: nowIso(off)}}});
const feeds = {_schema: 'element-feeds/1', elements: {'42': [{ref: 'bmo:meter:77:kw', kind: 'sensor', quantity: 'power', unit: 'kW', source: 'Panel CT 4', evidence: 'install log'}]}};
const apportion = {meter: '77', basis: 'design VA', weight: 360, share: 0.000174, pool: 1556};
const full = {name: 'Receptacle', type: 'Receptacle (quad)', system: 'Electrical', level: 'LEVEL 02', layer: 'fixtures', isFedBy: ['bmo:meter:77:kw'], apportion};
const all = t => [t.valueText, t.detailText, t.sourceText].join(' | ');

test('precedence: explicit feed > modelled > context > none', () => {
  const c = load();
  assert.equal(c.elementFeedTier('42', full, feeds, meters()).tier, 'LIVE');
  assert.equal(c.elementFeedTier('7', full, feeds, meters()).tier, 'MODELLED');
  assert.equal(c.elementFeedTier('7', {...full, apportion: undefined}, feeds, meters()).tier, 'CONTEXT');
  const none = c.elementFeedTier('7', {name: 'Column'}, feeds, meters());
  assert.equal(none.tier, 'NONE'); assert.match(none.valueText, /No feed yet/); assert.match(none.detailText, /Sensor link not yet connected/); assert.doesNotMatch(all(none), /\.json/);
});

test('explicit feed: fresh is LIVE, old is LATEST with age, missing says no reading', () => {
  const c = load();
  const fresh = c.elementFeedTier('42', full, feeds, meters(12.5, -5));
  assert.equal(fresh.tier, 'LIVE'); assert.match(fresh.valueText, /12\.50 kW/); assert.match(all(fresh), /Panel CT 4/);
  const old = c.elementFeedTier('42', full, feeds, meters(12.5, -190));
  assert.equal(old.tier, 'LATEST'); assert.doesNotMatch(all(old), /LIVE/); assert.match(all(old), /Last reading \d\d:\d\d · 3h ago/);
  const missing = c.elementFeedTier('42', full, feeds, {});
  assert.notEqual(missing.tier, 'LIVE'); assert.match(all(missing), /No reading in this window/);
  const nullKw = c.elementFeedTier('42', full, feeds, {'77': {latest: {kw: null, t: nowIso()}}});
  assert.notEqual(nullKw.tier, 'LIVE'); assert.doesNotMatch(all(nullKw), /null|NaN/);
});

test('explicit feed key may be layer-namespaced and wins over the bare id', () => {
  const c = load();
  const f = {elements: {'fixtures:9': [{ref: 'bmo:meter:77:kw', unit: 'kW', source: 'ns'}], '9': [{ref: 'bmo:meter:3:kw', unit: 'kW', source: 'bare'}]}};
  assert.match(all(c.elementFeedTier('9', {layer: 'fixtures'}, f, meters())), /ns/);
  assert.match(all(c.elementFeedTier('9', {layer: 'duct'}, f, meters())), /bare/);
});

test('modelled text never shows NaN/undefined and is not LIVE', () => {
  const c = load();
  const t = c.elementFeedTier('7', {...full, isFedBy: undefined}, null, meters(12.5, 0));
  assert.equal(t.tier, 'MODELLED'); assert.match(t.valueText, /^≈ .* modelled share$/);
  assert.match(t.detailText, /from building meter 77 · design VA ratio/);
  for (const bad of [{...apportion, share: undefined}, {...apportion, share: NaN}, {...apportion, weight: undefined}]) {
    for (const m of [meters(), {}, {'77': {latest: {kw: NaN}}}, undefined]) {
      const x = c.elementFeedTier('7', {name: 'x', apportion: bad}, {}, m);
      assert.equal(x.tier, 'MODELLED'); assert.doesNotMatch(all(x), /NaN|undefined|null|LIVE/);
    }
  }
});

test('context tier says context, is not the element reading, never LIVE', () => {
  const c = load();
  for (const m of [meters(12.5, 0), meters(12.5, -300), {}]) {
    const t = c.elementFeedTier('7', {name: 'x', isFedBy: ['bmo:meter:77:kw']}, {}, m);
    assert.equal(t.tier, 'CONTEXT'); assert.match(all(t), /context/i); assert.doesNotMatch(all(t), /LIVE|NaN|undefined/);
    assert.doesNotMatch(t.label, /LIVE/);
  }
});

test('empty, failed or malformed feeds file does not change other tiers', () => {
  const c = load();
  for (const f of [null, undefined, {}, {elements: {}}, {elements: null}, {elements: {'42': []}}, {elements: {'42': 'junk'}}, 'x']) {
    assert.equal(c.elementFeedTier('42', {name: 'x'}, f, meters()).tier, 'NONE');
    assert.equal(c.elementFeedTier('42', {name: 'x', apportion}, f, meters()).tier, 'MODELLED');
    assert.equal(c.elementFeedTier('42', {name: 'x', isFedBy: ['bmo:meter:77:kw']}, f, meters()).tier, 'CONTEXT');
  }
});

test('gazeDwell: 400 ms on one target, switching resets, leaving resets, force satisfies', () => {
  const c = load(); const s = {id: null, since: 0};
  assert.equal(c.gazeDwell(s, 'a', 1000).show, false);
  assert.equal(c.gazeDwell(s, 'a', 1399).show, false);
  assert.equal(c.gazeDwell(s, 'a', 1400).show, true);
  assert.equal(c.gazeDwell(s, 'b', 1500).show, false);       // switch resets
  assert.equal(c.gazeDwell(s, 'b', 1899).show, false);
  assert.equal(c.gazeDwell(s, 'b', 1900).show, true);
  assert.equal(c.gazeDwell(s, null, 2000).show, false);       // leave resets
  assert.equal(c.gazeDwell(s, 'b', 2100).show, false);
  assert.equal(c.gazeDwell(s, 'c', 3000, {force: true}).show, true);
  assert.equal(c.gazeDwell(s, 'c', 3010).show, true);         // force persists while aimed
});

test('card HTML escapes names and shows tier badge, line, source', () => {
  const c = load();
  const meta = {name: '<img src=x onerror=alert(1)>"&', type: '<b>T</b>', system: 'Elec', level: 'LEVEL 02'};
  const html = c.gazeCardHtml('1', meta, c.elementFeedTier('1', meta, {}, {}));
  assert.doesNotMatch(html, /<img|<b>/); assert.match(html, /&lt;img/); assert.match(html, /NO FEED/);
  const live = c.gazeCardHtml('42', full, c.elementFeedTier('42', full, feeds, meters()));
  assert.match(live, /LIVE/); assert.match(live, /Panel CT 4/);
});

test('wiring: card element, toggle, key I, capture hook gated on ?capture=1; feeds file ships empty', () => {
  assert.match(source, /id="gazeCard"/); assert.match(source, /Info cards/);
  assert.match(source, /e\.code\s*===\s*'KeyI'/);
  assert.match(source, /get\('capture'\)\s*===\s*'1'/);
  assert.match(source, /window\.walkCapture\s*=/);
  const j = JSON.parse(fs.readFileSync(path.join(__dirname, '../buildings/grimes/element-feeds.json'), 'utf8'));
  assert.equal(j._schema, 'element-feeds/1'); assert.deepEqual(j.elements, {}); assert.ok(j._doc.length > 40);
});
