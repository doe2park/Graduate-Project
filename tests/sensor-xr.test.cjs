const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const SX = require('../twin/sensor-xr.js'), MR = require('../twin/mr-align.js'), SD = require('../twin/sensor-demo.js'), SF = require('../twin/sensors/feed.js'), X = require('../twin/xr-core.js');
const ROOT = path.join(__dirname, '..'), read = f => fs.readFileSync(path.join(ROOT, f), 'utf8');
const registry = JSON.parse(read('twin/sensors/registry.json'));

test('params: sensors=demo opt-in, scene default leak, ?scene=gaussian is not a sensor scene', () => {
  assert.deepEqual(SX.parseParams(''), {enabled: false, scene: 'leak'});
  assert.deepEqual(SX.parseParams('?mode=ar&sensors=demo&scene=air'), {enabled: true, scene: 'air'});
  assert.deepEqual(SX.parseParams('?sensors=demo&scene=gaussian'), {enabled: true, scene: 'leak'});
  assert.equal(SX.parseParams('?sensors=off').enabled, false);
  assert.deepEqual(SX.SCENES, ['leak', 'air', 'water', 'elec', 'rotating']);
  assert.equal(SX.nextScene('leak'), 'air'); assert.equal(SX.nextScene('rotating'), 'leak'); assert.equal(SX.nextScene('leak', -1), 'rotating'); assert.equal(SX.nextScene('zzz'), 'air');
  // every scene exists in the registry and has a primary sensor
  for (const sc of SX.SCENES) { assert.ok(SD.filterScene(registry.sensors, sc).length >= 3, sc); assert.ok(registry.primary[sc]); }
});
test('state in the URL: other params kept, choices replaced', () => {
  assert.equal(SX.withState('?mode=ar&place=demo&sensors=demo', {mode: 'align', area: 'l1-auditorium-foyer'}), '?mode=ar&place=grimes&sensors=demo&area=l1-auditorium-foyer');
  assert.equal(SX.withState('?mode=ar&place=grimes', {mode: 'demo', sensors: false}), '?mode=ar&place=demo&sensors=off');
  assert.equal(SX.withState('?mode=ar&scene=leak', {scene: 'water', sensors: true}), '?mode=ar&scene=water&sensors=demo');
  assert.equal(SX.withState('?mode=ar', {scene: 'nope'}), '?mode=ar');
});
test('/mr defaults: demo + sensors unless the query says otherwise; extra params pass through', () => {
  assert.equal(SX.mrDefaults(''), '?mode=ar&place=demo&sensors=demo');
  assert.equal(SX.mrDefaults('?scene=air&radius=20'), '?mode=ar&place=demo&sensors=demo&scene=air&radius=20');
  assert.equal(SX.mrDefaults('?place='), '?mode=ar&sensors=demo&place=');
  assert.equal(SX.mrDefaults('?sensors=off'), '?mode=ar&place=demo&sensors=off');
  assert.equal(SX.mrDefaults('?place=demo&sensors=demo'), '?mode=ar&place=demo&sensors=demo');
  const html = read('mr/index.html');
  assert.ok(html.includes('place=demo') && html.includes('sensors=demo') && html.includes('Tap here if it does not open'), 'fallback link kept, defaults named');
});
test('cluster centre and the demo reference: the floor point lands under the scene centroid', () => {
  assert.equal(SX.clusterCenter([]), null);
  const c = SX.clusterCenter([[0, 4, 0], [2, 6, 4], [NaN, 1, 1]]); assert.deepEqual(c, [1, 5, 2]);
  const doc = JSON.parse(read('buildings/grimes/mr-landmarks.json')), area = doc.areas[0], da = SX.demoArea(area, [-20, 9, -3]);
  assert.deepEqual(MR.demoReference(da), [-20, area.floorY, -3]);
  const F = [1, 0, -2], T = MR.demoTransform(da, {floorPoint: F, headYawRad: 0.7});
  const w = MR.applyT(T, MR.demoReference(da)); w.forEach((v, k) => assert.ok(Math.abs(v - F[k]) < 1e-9));
  assert.equal(SX.demoArea(area, null), area, 'no cluster: foyer reference');
  assert.notDeepEqual(MR.demoReference(da), MR.demoReference(area));
});
test('pin picking and sizing', () => {
  const pins = [{id: 'a', p: [0, 0, -5], r: .3}, {id: 'b', p: [0, 0, -3], r: .3}, {id: 'c', p: [2, 0, -3], r: .3}];
  assert.equal(SX.pickPin([0, 0, 0], [0, 0, -1], pins, 20).id, 'b', 'nearest along the ray');
  assert.equal(SX.pickPin([0, 0, 0], [0, 0, -1], pins, 4).id, 'b'); assert.equal(SX.pickPin([0, 0, 0], [0, 0, 1], pins, 20), null, 'behind');
  assert.equal(SX.pickPin([0, 0, 0], [0.5, 0, -1], pins, 20), null); assert.equal(SX.pickPin([0, 0, 0], [2, 0, -3], pins, 20).id, 'c');
  const two = [{id: 'p', p: [0.05, 0, -10], r: .5}, {id: 'q', p: [-0.3, 0, -10], r: .5}];
  assert.equal(SX.pickPin([0, 0, 0], [0, 0, -1], two, 20).id, 'p', 'overlapping pins: closest to the ray axis');
  assert.ok(SX.pinSize(0.1) === 0.12 && SX.pinSize(100) === 0.6 && SX.pinSize(5) === 0.3);
});
test('card and chip never present a simulated value as real', () => {
  const s = registry.sensors.find(x => x.id === 'leak-dts'), obs = SF.simulate(s, Date.parse('2026-10-30T20:00:00Z'));
  assert.equal(obs.simulated, true);
  const v = SF.formatValue(obs.value, s.unit), lines = SX.cardLines({sensor: s, element: {name: 'Pipe219763'}, typeName: SD.TYPES[s.type], sceneName: 'Leak', valueText: v, series: SX.simSeries(SF.simulate, s, Date.parse('2026-10-30T20:00:00Z'), 24), alignText: 'DEMO placement · not aligned to this building'});
  assert.equal(lines.badge, 'SIMULATED'); assert.equal(lines.footer[0], 'Demo sensor — illustrative, not installed · values simulated'); assert.match(lines.footer[1], /DEMO placement/);
  assert.match(lines.rows[0], /^Simulated value: .*°C$/); assert.match(lines.rows[2], /Pipe219763 · fire:278123/); assert.equal(lines.spark.length, 24);
  assert.ok(lines.title.length <= 44);
  assert.match(SX.chipText('Leak', 'Dry'), /SIM$/);
  assert.equal(SX.cardLines({sensor: s, valueText: '', alignText: ''}).rows[0], 'Simulated value: no data');
});
test('page wiring: loadProgressText, versions, no real-reading claims', () => {
  const html = read('scan-xr.html');
  assert.equal(X.API, 4); assert.ok(html.includes('twin/xr-core.js?v=4') && html.includes('XR_CORE_API=4,'));
  assert.equal(X.loadProgressText('Fire piping', 21.8e6, 2.0e6), 'Fire piping · 21.8 MB loaded', 'loaded > total is never a fraction');
  assert.equal(X.loadProgressText('Fire', 5e6, 24.2e6), 'Fire · 5.0 / 24.2 MB'); assert.equal(X.loadProgressText('Duct', 21.11e6, 21.1e6), 'Duct · 21.1 / 21.1 MB');
  assert.equal(X.loadProgressText('Duct', 30e6, 21.1e6), 'Duct · 30.0 MB loaded'); assert.equal(X.loadProgressText('X', 3e6), 'X · 3.0 MB loaded'); assert.equal(X.loadProgressText('X', NaN, 5), 'X · loading…');
  assert.ok(!/p\.total/.test(html), 'compressed Content-Length is never used as a denominator');
  for (const f of ['twin/sensor-xr.js', 'twin/sensor-demo.js', 'twin/sensors/feed.js']) assert.ok(html.includes(f + '?v='), f + ' loaded with ?v=');
  assert.match(html, /globalThis\.SensorXR,SXOK=SX\?\.API===1/, 'stale-cache guard for the sensor helper');
  const menu = X.menuButtons('more', {layers: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'].map(k => ({key: k, label: k})), sensorsLabel: 'Leak'});
  assert.equal(menu.length, X.menuLayout(X.MENU_PAGES.more).length); assert.equal(menu[13].id, 'sensors'); assert.equal(menu[13].value, 'Leak'); assert.equal(menu[13].tone, 'on');
});
