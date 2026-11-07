/* Live sensor test (?sensors=live&feed=<url>, twin/sensors/FEED.md "Live test with a phone"): the live-test registry is valid,
   honest and separate from the public demo registry; the feed URL is accepted only for this computer or the private LAN; the
   gateway adapter passes only valid, non-simulated gateway observations; both viewers turn the live layer on only behind the
   parameter and label it Live / Stale / No data (never Simulated). Gateway server behaviour: tests/test_sensor_gateway.py. */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const root = path.join(__dirname, '..'), read = f => fs.readFileSync(path.join(root, f), 'utf8'), json = f => JSON.parse(read(f));
const V = require('../twin/sensors/schema-lite.js'), F = require('../twin/sensors/feed.js'), SD = require('../twin/sensor-demo.js'), SX = require('../twin/sensor-xr.js');
const LIVE = json('twin/sensors/registry.live-test.json'), REG = json('twin/sensors/registry.json'), RS = json('twin/sensors/registry.schema.json');
const OS = json('twin/sensors/observation.schema.json'), FS = json('twin/sensors/feed.schema.json');
const T = Date.parse('2026-11-07T15:00:00-08:00'), iso = ms => new Date(ms).toISOString();

test('live-test registry: valid, temporary test device on a real BIM element, separate from the public demo registry', () => {
  assert.deepEqual(V.validate(RS, LIVE), []);
  const v = SD.validateConfig(LIVE); assert.deepEqual(v.errors, []); assert.equal(v.sensors.length, LIVE.sensors.length);
  assert.equal(SD.LIVE_CONFIG_URL, 'twin/sensors/registry.live-test.json');
  assert.match(LIVE.scope, /ONLY with \?sensors=live/);
  const duct = json('buildings/grimes/duct.elements.json').elements;
  for (const s of LIVE.sensors) {
    assert.equal(s.install_status, 'test', s.id); assert.equal(s.data_source, 'gateway', s.id); assert.equal(s.scenario, 'live-test', s.id);
    assert.equal(s.test_device.temporary, true); assert.match(s.label + s.kind, /[Tt]est device|[Tt]emporary/);
    assert.match(s.provenance, /[Tt]emporary/);
    assert.equal(s.brick.isPointOf, 'urn:grimes:bim-guid:' + s.anchor.guid);
    const el = duct[s.anchor.id]; assert.ok(el, s.id + ' anchor element exists');
    assert.equal(el.name, s.anchor.name); assert.equal(el.source_guid, s.anchor.guid); assert.equal(el.level, 'LEVEL 01');
  }
  const phone = LIVE.sensors.find(s => s.id === 'test-phone-vib');
  assert.equal(phone.anchor.id, '399665', 'the fan-fed duct run of "Test install 5"');
  assert.equal(phone.unit, 'm/s2'); assert.equal(phone.quantity, 'vibration_acceleration_rms', 'acceleration, not ISO velocity');
  assert.equal(F.formatValue(0.123, 'm/s2'), '0.123 m/s²');
  /* the public demo registry is untouched: no test devices, ids disjoint */
  assert.ok(REG.sensors.every(s => s.install_status === 'demo' && s.scenario !== 'live-test'));
  assert.ok(!LIVE.sensors.some(s => REG.sensors.some(r => r.id === s.id)));
});

test('validateConfig: a test device must report real data and say it is temporary', () => {
  const one = patch => { const c = JSON.parse(JSON.stringify(LIVE)); Object.assign(c.sensors[0], patch); return SD.validateConfig(c); };
  assert.equal(one({data_source: 'demo-sim'}).ok, false, 'test + simulator refused');
  assert.equal(one({test_device: undefined}).ok, false, 'test_device required');
  assert.equal(one({test_device: {device: 'phone', temporary: false, note: 'long enough note'}}).ok, false, 'must be temporary');
});

test('feed URL: only with sensors=live, only this computer or a private-LAN address', () => {
  const page = 'https://192.168.1.20:8931/scan-compare.html?x', pub = 'https://doe2park.github.io/Graduate-Project/scan-compare.html';
  assert.deepEqual(F.liveFeedUrl('', page), {live: false, url: null, error: null});
  assert.equal(F.liveFeedUrl('?sensors=demo&feed=https://192.168.1.20:8931/api/sensors/latest.json', page).live, false, 'demo never reads a feed URL');
  assert.match(F.liveFeedUrl('?sensors=live', page).error, /no feed URL/);
  const ok = (q, base, want) => { const r = F.liveFeedUrl(q, base); assert.equal(r.error, null, q + ' -> ' + r.error); assert.equal(r.url, want); };
  ok('?sensors=live&feed=/api/sensors/latest.json', page, 'https://192.168.1.20:8931/api/sensors/latest.json');
  ok('?sensors=live&feed=' + encodeURIComponent('https://192.168.1.20:8931/api/sensors/latest.json'), pub, 'https://192.168.1.20:8931/api/sensors/latest.json');
  ok('?sensors=live&feed=https://10.0.0.5:8931/a.json', pub, 'https://10.0.0.5:8931/a.json');
  ok('?sensors=live&feed=https://172.20.1.2/a.json#x', pub, 'https://172.20.1.2/a.json');
  ok('?sensors=live&feed=http://127.0.0.1:8931/api/sensors/latest.json', 'http://127.0.0.1:8000/scan-compare.html', 'http://127.0.0.1:8931/api/sensors/latest.json');
  ok('?sensors=live&feed=http://localhost:8931/x.json', pub, 'http://localhost:8931/x.json');
  for (const [q, base, why] of [
    ['?sensors=live&feed=https://example.com/latest.json', page, /private-LAN/], ['?sensors=live&feed=https://8.8.8.8/x.json', page, /private-LAN/],
    ['?sensors=live&feed=https://172.32.0.1/x.json', page, /private-LAN/], ['?sensors=live&feed=https://192.169.1.1/x.json', page, /private-LAN/],
    ['?sensors=live&feed=https://localhost.evil.com/x.json', page, /private-LAN/], ['?sensors=live&feed=https://192.168.1.1.nip.io/x.json', page, /private-LAN/],
    ['?sensors=live&feed=https://u:p@192.168.1.2/x.json', page, /credentials/], ['?sensors=live&feed=file:///etc/passwd.json', page, /http/],
    ['?sensors=live&feed=javascript:alert(1)//.json', page, /http/], ['?sensors=live&feed=https://192.168.1.2/api/sensors', page, /\.json/],
    ['?sensors=live&feed=/api/sensors/latest.json', pub, /private-LAN/], ['?sensors=live&feed=http://192.168.1.2:8931/x.json', pub, /https page cannot read an http feed/]]) {
    const r = F.liveFeedUrl(q, base); assert.equal(r.url, null, q); assert.equal(r.live, true); assert.match(r.error, why, q);
  }
  assert.equal(F.privateHost('10.1.2.3'), 'lan'); assert.equal(F.privateHost('127.0.0.1'), 'loopback'); assert.equal(F.privateHost('[::1]'), 'loopback');
  assert.equal(F.privateHost('192.168.001.1'), null, 'no leading zeros'); assert.equal(F.privateHost('300.1.1.1'), null);
});

test('gateway adapter: valid live observations pass; simulated, wrong source, malformed or unreachable become missing', async () => {
  const reg = LIVE, s = reg.sensors[0], url = 'http://127.0.0.1:8931/api/sensors/latest.json';
  const good = {sensor_id: s.id, ts: iso(T - 1000), value: 0.21, unit: 'm/s2', quality: 'good', source: 'gateway', simulated: false};
  const snap = obs => ({schema: 'grimes-sensor-feed/1', generated_at: iso(T), simulated: false, source: 'gateway', observations: obs});
  assert.deepEqual(V.validate(FS, snap([good]), {'observation.schema.json': OS}), []);
  const feedWith = (body, opt = {}) => F.create({registry: reg, gateway: {url}, fetch: async (u, o) => { assert.equal(u, url); assert.equal(o.cache, 'no-store'); assert.equal(o.credentials, 'omit');
    if (opt.fail) throw new Error('connect ECONNREFUSED'); return {ok: !opt.status, status: opt.status || 200, json: async () => body}; }});
  let o = (await feedWith(snap([good])).getLatest(null, T))[s.id];
  assert.deepEqual(o, good);
  let a = F.assess(o, s, T, 3); assert.equal(a.badge, 'Live'); assert.equal(a.state, 'ok');
  const html = F.feedHtml(s, o, a); assert.match(html, /sd-src live">LIVE</); assert.match(html, /0\.21 m\/s²/); assert.match(html, /1 s ago/); assert.match(html, /source gateway/);
  assert.ok(!/SIMULATED/.test(html));
  /* stale after 3 x 2 s; the card keeps the last value greyed with its age */
  a = F.assess(o, s, T + 5000, 3); assert.equal(a.state, 'ok', 'exactly 3 intervals old'); a = F.assess(o, s, T + 8000, 3); assert.equal(a.state, 'stale');
  assert.match(F.feedHtml(s, o, a), /Stale · last value 9 s ago/);
  const missingWith = async (body, opt, why) => { const m = (await feedWith(body, opt).getLatest(null, T))[s.id]; assert.equal(m.value, null); assert.equal(m.quality, 'missing'); assert.match(m.reason, why); assert.ok(F.validObservation(m)); assert.equal(F.assess(m, s, T).state, 'missing'); };
  await missingWith(snap([{...good, simulated: true}]), {}, /refused/);
  await missingWith(snap([{...good, source: 'demo-sim', simulated: true}]), {}, /refused/);
  await missingWith(snap([{...good, value: '0.2'}]), {}, /refused/);
  await missingWith(snap([{...good, ts: '2026-11-07T15:00:00'}]), {}, /refused/);
  await missingWith(snap([]), {}, /no observation from the gateway yet/);
  await missingWith({observations: [good]}, {}, /not grimes-sensor-feed/);
  await missingWith(null, {fail: true}, /gateway not reachable \(connect ECONNREFUSED\)/);
  await missingWith(null, {status: 503}, /HTTP 503/);
  /* a missing observation from the device keeps its reason; a unit mismatch is shown as such */
  await missingWith(snap([{sensor_id: s.id, ts: iso(T), value: null, unit: 'm/s2', quality: 'missing', source: 'gateway', reason: 'no accelerometer samples'}]), {}, /no accelerometer samples/);
  o = (await feedWith(snap([{...good, unit: 'mm/s'}])).getLatest(null, T))[s.id]; assert.equal(F.assess(o, s, T).label, 'Unit mismatch');
  /* refused feed URL: the reason reaches the card instead of a value */
  const r = await F.create({registry: reg, gateway: {url: null, error: 'feed URL refused: only this computer'}}).getLatest(null, T);
  assert.match(r[s.id].reason, /feed URL refused/);
  /* without a gateway option the stub is unchanged (public demo and existing tests) */
  assert.match((await F.create({registry: reg}).getLatest(null, T))[s.id].reason, /not connected/);
});

test('web overlay: live layer only behind ?sensors=live, live registry + gateway URL only there; card says TEST, not DEMO or Simulated', () => {
  assert.equal(SD.parseSensorsParam('?sensors=live&feed=x'), 'live'); assert.equal(SD.parseSensorsParam('?sensors=demo'), 'demo'); assert.equal(SD.parseSensorsParam('?sensors=yes'), null);
  const compare = read('scan-compare.html'), block = compare.slice(compare.lastIndexOf('/* SENSOR DEMO'));
  assert.match(block, /const sdLive=new URLSearchParams\(location\.search\)\.get\('sensors'\)==='live';/);
  assert.match(block, /configUrl:sdLive\?SensorDemo\.LIVE_CONFIG_URL:undefined,/);
  assert.match(block, /gateway:sdLive\?\(window\.SensorFeed\?SensorFeed\.liveFeedUrl\(location\.search,location\.href\):/);
  assert.ok(!compare.slice(0, compare.lastIndexOf('/* SENSOR DEMO')).includes('registry.live-test'), 'nothing outside the guarded block');
  assert.ok(!/['"]twin\/sensors\/registry\.live-test\.json['"]/.test(read('scan-bim.html') + compare), 'the BIM pane uses SensorDemo.LIVE_CONFIG_URL, never a hard-coded path');
  const s = LIVE.sensors[0], card = SD.cardHtml(s, null, null, '<div class="sd-feed">X</div>');
  assert.match(card, /gz-badge sd-test">TEST</); assert.ok(!/DEMO|Simulated|Illustrative|Scenario:/.test(card));
  assert.match(card, /sd-note">Temporary test device for the end-to-end live path/); assert.match(card, /Maps to BIM element: <b>Straight Rect_/);
  assert.match(SD.PARENT_CSS, /#sdBadge\.sd-live/); assert.match(SD.LIVE_BADGE_TEXT, /^Live test — temporary phone sensor/);
});

test('XR page: ?sensors=live = the live-test scene with LIVE / STALE / NO DATA labels; state in the URL stays live', () => {
  assert.deepEqual(SX.parseParams('?mode=ar&sensors=live&feed=/api/sensors/latest.json'), {enabled: true, scene: 'live-test', live: true});
  assert.ok(!SX.SCENES.includes(SX.LIVE_SCENE), 'never in the demo scene cycle');
  assert.equal(SX.withState('?mode=ar&sensors=live&feed=%2Fapi%2Fsensors%2Flatest.json', {mode: 'demo', sensors: true, scene: 'live-test'}), '?mode=ar&sensors=live&feed=%2Fapi%2Fsensors%2Flatest.json&place=demo');
  assert.equal(SX.mrDefaults('?sensors=live&feed=x.json'), '?mode=ar&place=demo&sensors=live&feed=x.json');
  const s = LIVE.sensors[0], obs = {sensor_id: s.id, ts: iso(T - 3000), value: 0.42, unit: 'm/s2', quality: 'good', source: 'gateway'};
  const a = F.assess(obs, s, T), L = SX.liveCardLines({sensor: s, element: {name: 'Straight Rect_ duct'}, typeName: SD.TYPES[s.type], obs, a, valueText: F.formatValue(0.42, s.unit), age: F.ageText(a.ageS), series: [0.1, 0.4], alignText: 'DEMO placement'});
  assert.equal(L.badge, 'LIVE'); assert.equal(L.cls, 'live'); assert.equal(L.rows[0], 'Live value: 0.42 m/s² · 3 s ago'); assert.match(L.rows[1], /quality good · source gateway · temporary test device/);
  assert.match(L.footer[0], /Temporary test device/); assert.ok(!JSON.stringify(L).includes('Simulated'));
  const st = F.assess(obs, s, T + 60000), Ls = SX.liveCardLines({sensor: s, obs, a: st, valueText: '0.42 m/s²', age: F.ageText(st.ageS)});
  assert.equal(Ls.badge, 'STALE'); assert.equal(Ls.rows[0], 'Stale: last 0.42 m/s² · 1 min ago');
  const ms = F.assess(null, s, T); assert.equal(SX.liveCardLines({sensor: s, obs: null, a: ms, valueText: '—'}).rows[0], 'No data: no observation');
  assert.equal(SX.liveTag(F.assess({...obs, source: 'demo-sim', simulated: true}, s, T)), 'SIM', 'a simulated value is never tagged LIVE');
  assert.equal(SX.chipText('Vibration', '0.42 m/s²', 'LIVE'), 'Vibration · 0.42 m/s² · LIVE'); assert.equal(SX.chipText('Leak', 'Dry'), 'Leak · Dry · SIM');
  const html = read('scan-xr.html');
  assert.match(html, /fetchJson\(SENS\.live\?globalThis\.SensorDemo\.LIVE_CONFIG_URL:'twin\/sensors\/registry\.json'\)/);
  assert.match(html, /if\(SENS\.live\)SENS\.gw=globalThis\.SensorFeed\.liveFeedUrl\(location\.search,location\.href\);/);
  assert.match(html, /now-SENS\.lastFeed>\(SENS\.live\?2500:20000\)/);
});
