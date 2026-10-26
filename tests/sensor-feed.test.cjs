/* Sensor registry + feed contract (twin/sensors/): registry and snapshot schemas, the shared stale / missing / unit
   rules, simulator determinism and JS == Python agreement, adapter stubs, and that the Lens element card only gains a
   feed row with ?sensors=demo (the standard card is unchanged). */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const {execFileSync} = require('node:child_process');
const root = path.join(__dirname, '..'), read = f => fs.readFileSync(path.join(root, f), 'utf8'), json = f => JSON.parse(read(f));
const V = require('../twin/sensors/schema-lite.js'), F = require('../twin/sensors/feed.js'), SD = require('../twin/sensor-demo.js');
const REG = json('twin/sensors/registry.json'), RS = json('twin/sensors/registry.schema.json'), OS = json('twin/sensors/observation.schema.json'), FS = json('twin/sensors/feed.schema.json');
const refs = {'observation.schema.json': OS};
const T = Date.parse('2026-10-26T10:00:00-07:00');

test('registry: valid against its JSON Schema and the layer validator; one source of truth', () => {
  assert.deepEqual(V.validate(RS, REG), []);
  assert.equal(SD.validateConfig(REG).ok, true);
  assert.ok(!fs.existsSync(path.join(root, 'twin/sensor-demo.json')), 'the old demo config is gone');
  assert.equal(SD.CONFIG_URL, 'twin/sensors/registry.json');
  for (const s of REG.sensors) {
    assert.equal(s.brick.isPointOf, 'urn:grimes:bim-guid:' + s.anchor.guid, s.id + ' isPointOf = its BIM element GUID');
    assert.ok(['candidate', 'used-in-model', 'verified'].includes(s.brick.status));
    if (s.point_kind === 'derived') assert.ok(REG.sensors.some(x => x.id === s.derived_from), s.id + ' derived_from exists');
    assert.equal(s.source_point, null, 'no real point is claimed yet');
  }
  const bad = JSON.parse(JSON.stringify(REG)); bad.sensors[0].unit = 'furlongs'; bad.sensors[1].install_status = 'maybe'; bad.sensors[2].brick.isPointOf = 'x';
  assert.equal(V.validate(RS, bad).length, 3);
});

test('feed snapshot + observation schemas; a bad observation is caught', () => {
  const ok = {sensor_id: 'hvac-iaq', ts: '2026-10-26T17:00:00.000Z', value: 821, unit: 'ppm', quality: 'good', source: 'demo-sim', simulated: true};
  assert.deepEqual(V.validate(OS, ok), []);
  assert.deepEqual(V.validate(FS, {schema: 'grimes-sensor-feed/1', simulated: true, source: 'demo-sim', observations: [ok]}, refs), []);
  for (const [why, o] of [['no tz', {...ok, ts: '2026-10-26T17:00:00'}], ['bad quality', {...ok, quality: 'fine'}], ['bad source', {...ok, source: 'web'}], ['string value', {...ok, value: '821'}]])
    assert.ok(V.validate(OS, o).length > 0 && !F.validObservation(o), why);
  assert.ok(V.validate(OS, {...ok, foo: 1}).length > 0, 'schema refuses unknown fields');
  assert.ok(F.validObservation({sensor_id: 'x', ts: null, value: null, unit: 'ppm', quality: 'missing', source: 'bms'}), 'missing = null value');
  assert.ok(!F.validObservation({...ok, simulated: undefined}), 'demo-sim must say simulated: true');
});

test('shared rules: missing is not zero, stale after N x interval, unit mismatch, quality', () => {
  const s = REG.sensors.find(x => x.id === 'hvac-iaq'), iv = s.sampling_interval_s * 1000, base = {sensor_id: s.id, value: 800, unit: 'ppm', quality: 'good', source: 'demo-sim', simulated: true};
  const at = ms => new Date(ms).toISOString();
  assert.equal(F.assess({...base, ts: at(T - iv)}, s, T).state, 'ok');
  assert.equal(F.assess({...base, ts: at(T - 3 * iv)}, s, T).state, 'ok', 'exactly 3 intervals: still fresh');
  assert.equal(F.assess({...base, ts: at(T - 3 * iv - 1000)}, s, T).state, 'stale');
  assert.equal(F.assess({...base, value: 0, ts: at(T)}, s, T).state, 'ok', 'a real zero is a value');
  assert.equal(F.assess({...base, value: null, ts: at(T)}, s, T).state, 'missing', 'null is missing, not 0');
  assert.equal(F.assess({...base, quality: 'missing', ts: at(T)}, s, T).state, 'missing');
  assert.equal(F.assess({...base, unit: 'ppb', ts: at(T)}, s, T).state, 'suspect');
  assert.equal(F.assess({...base, quality: 'suspect', ts: at(T)}, s, T).state, 'suspect');
  assert.equal(F.assess({...base, ts: at(T)}, s, T).badge, 'Simulated');
  assert.equal(F.assess({...base, source: 'bms', simulated: undefined, ts: at(T)}, s, T).badge, 'Live');
  const html = F.feedHtml(s, {...base, ts: at(T - 60000)}, F.assess({...base, ts: at(T - 60000)}, s, T));
  assert.match(html, /SIMULATED/); assert.match(html, /800 ppm/); assert.match(html, /1 min ago/); assert.match(html, /quality good/); assert.match(html, /source demo-sim/);
  assert.match(F.feedHtml(s, null, F.assess(null, s, T)), /No data/);
  assert.equal(F.formatValue(0, 'bool'), 'Dry'); assert.equal(F.formatValue(1, 'bool'), 'Water detected'); assert.equal(F.formatValue(null, 'ppm'), '—');
});

test('simulator: deterministic, labelled, valid, follows the scenario patterns', async () => {
  const feed = F.create({registry: REG}), a = await feed.getLatest(null, T), b = await feed.getLatest(null, T);
  assert.deepEqual(a, b, 'same time -> same values');
  assert.equal(Object.keys(a).length, REG.sensors.length);
  for (const o of Object.values(a)) {
    assert.ok(F.validObservation(o), o.sensor_id); assert.deepEqual(V.validate(OS, o), [], o.sensor_id);
    assert.equal(o.source, 'demo-sim'); assert.equal(o.simulated, true);
    assert.equal(o.unit, feed.sensor(o.sensor_id).unit);
    assert.equal(F.assess(o, feed.sensor(o.sensor_id), T).state, 'ok', 'fresh at its own interval');
  }
  const night = await feed.getLatest(['water-flow', 'hvac-iaq', 'leak-dts'], Date.parse('2026-10-26T02:30:00-07:00'));
  assert.ok(night['water-flow'].value > 0.5, 'night flow between 1 and 4 am');
  assert.ok(a['water-flow'].value < 0.2, 'normal daytime flow');
  assert.ok(night['hvac-iaq'].value < 480 && a['hvac-iaq'].value > 700, 'CO2 follows occupancy');
  assert.ok(a['leak-dts'].value > 29, 'warm spot on the leak pipe');
  const early = await feed.getLatest(['fan-vibration'], Date.parse('2026-09-05T10:00:00-07:00'));
  assert.ok(a['fan-vibration'].value > early['fan-vibration'].value + 0.5, 'vibration trend rises over weeks');
  assert.equal(a['leak-puck'].value, 0, 'leak puck dry');
});

test('python generator == browser simulator (same values and timestamps); snapshot files valid', async () => {
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'sensor-sim-'));
  execFileSync('python3', [path.join(root, 'tools/sensor_sim.py'), '--at', '2026-10-26T10:00:00-07:00', '--out', out, '--history'], {env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}});
  const snap = JSON.parse(fs.readFileSync(path.join(out, 'latest.json'), 'utf8')), hist = JSON.parse(fs.readFileSync(path.join(out, 'history', '2026-10-26.json'), 'utf8'));
  assert.deepEqual(V.validate(FS, snap, refs), []); assert.deepEqual(V.validate(FS, hist, refs), []);
  assert.equal(snap.simulated, true); assert.equal(hist.observations.length, 24 * REG.sensors.length);
  const js = await F.create({registry: REG}).getLatest(null, T);
  for (const o of snap.observations) { assert.equal(o.ts, js[o.sensor_id].ts, o.sensor_id); assert.equal(o.value, js[o.sensor_id].value, o.sensor_id); }
  fs.rmSync(out, {recursive: true, force: true});
});

test('adapter stubs: real sources return missing with a reason, never a fake value', async () => {
  const reg = JSON.parse(JSON.stringify(REG));
  const src = {'hvac-iaq': 'gateway', 'power-bmo': 'bmo', 'hvac-damper': 'bms', 'leak-dts': 'fiber'};
  for (const s of reg.sensors) if (src[s.id]) { s.data_source = src[s.id]; s.install_status = 'installed'; }
  const o = await F.create({registry: reg}).getLatest(Object.keys(src), T);
  for (const [id, source] of Object.entries(src)) {
    assert.equal(o[id].source, source); assert.equal(o[id].quality, 'missing'); assert.equal(o[id].value, null);
    assert.match(o[id].reason, /not connected/); assert.ok(F.validObservation(o[id]));
    assert.equal(F.assess(o[id], reg.sensors.find(x => x.id === id), T).state, 'missing');
  }
  /* a custom adapter plugs in without touching the viewer */
  const live = await F.create({registry: reg, adapters: {bmo: list => list.map(s => ({sensor_id: s.id, ts: new Date(T).toISOString(), value: 212, unit: 'kW', quality: 'good', source: 'bmo'}))}}).getLatest(['power-bmo'], T);
  assert.equal(live['power-bmo'].value, 212);
  assert.equal(F.assess(live['power-bmo'], reg.sensors.find(x => x.id === 'power-bmo'), T).badge, 'Live');
});

test('viewer wiring: feed only behind ?sensors=demo; the standard Lens card is unchanged without it', () => {
  const compare = read('scan-compare.html');
  assert.ok(!/<script src="twin\/sensors\/feed\.js/.test(compare), 'never a static script tag');
  const block = compare.slice(compare.lastIndexOf('/* SENSOR DEMO'));
  assert.match(block, /^\/\* SENSOR DEMO[\s\S]*?\nif\(new URLSearchParams\(location\.search\)\.get\('sensors'\)==='demo'\)\{[\s\S]*twin\/sensors\/feed\.js/);
  assert.match(compare, /try\{if\(window\.sdElementFeedApply\)window\.sdElementFeedApply\(lensCard,pick\.hit\.layer,pick\.hit\.id,tier\);\}catch\(e\)\{\}/);
  assert.equal([...compare.matchAll(/window\.sdElementFeedApply=/g)].length, 1);
  assert.ok(compare.lastIndexOf('window.sdElementFeedApply=') > compare.lastIndexOf('/* SENSOR DEMO'), 'defined only inside the demo block');
  /* the card gets the feed block with a Simulated badge; without a feed it falls back to the illustrative text */
  const s = REG.sensors.find(x => x.id === 'hvac-iaq');
  assert.match(SD.cardHtml(s, null, null, '<div class="sd-feed">X</div>'), /sd-feed[\s\S]*Scenario: CO2 780 ppm[\s\S]*Simulated feed · no sensor installed/);
  assert.match(SD.cardHtml(s, null, null), /Illustrative value · no sensor installed/);
  assert.ok(!fs.readFileSync(path.join(root, 'tools/sensor_sim.py'), 'utf8').includes("'data'"), 'generator never targets the data branch');
});
