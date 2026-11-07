/* Sensor feed adapter + deterministic demo simulator (twin/sensors/FEED.md). One entry point for the viewer:
     SensorFeed.create({registry}).getLatest(ids [, nowMs]) -> Promise<{id: observation}>
   Sources: 'demo-sim' = the simulator below (time-of-day patterns, no backend, no cron); 'bms' | 'bmo' | 'gateway' |
   'fiber' = stubs that return quality "missing" with a reason until a real adapter is written (twin/sensors/README.md).
   The same math lives in tools/sensor_sim.py (snapshot files); tests/sensor-feed.test.cjs checks both agree.
   Every simulated observation carries source "demo-sim" and simulated: true, and the UI labels it "Simulated".
   Live test (opt-in ?sensors=live&feed=<url>, FEED.md "Live test with a phone"): create({registry, gateway: {url}}) turns the
   'gateway' adapter into a reader of a grimes-sensor-feed/1 snapshot (tools/sensor_gateway.py today, a real wireless gateway
   later). liveFeedUrl() only accepts a feed on this machine or the private LAN. */
(function (root, factory) {
  const api = factory();
  if (root) root.SensorFeed = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';

const FEED_SCHEMA = 'grimes-sensor-feed/1', QUALITY = ['good', 'suspect', 'missing'], SOURCES = ['demo-sim', 'bms', 'bmo', 'gateway', 'fiber'];
const TZ = 'America/Los_Angeles', TREND_START = Date.UTC(2026, 8, 1), DAY = 86400000;
const finite = v => typeof v === 'number' && Number.isFinite(v);

/* ── deterministic helpers (mirrored in tools/sensor_sim.py) ── */
function fnv1a(str) {
  let h = 0x811c9dc5;
  for (const b of Buffer_from(str)) { h ^= b; h = Math.imul(h, 0x01000193) >>> 0; }
  return h >>> 0;
}
function Buffer_from(str) { return typeof TextEncoder !== 'undefined' ? new TextEncoder().encode(str) : Array.from(unescape(encodeURIComponent(str)), c => c.charCodeAt(0)); }
function noise(id, bucket) { return fnv1a(id + '|' + bucket) / 4294967296 * 2 - 1; }   // [-1, 1)
function localHour(ms) {
  const parts = new Intl.DateTimeFormat('en-US', {timeZone: TZ, hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'}).formatToParts(new Date(ms));
  const g = t => +parts.find(p => p.type === t).value;
  return (g('hour') % 24) + g('minute') / 60 + g('second') / 3600;
}
function occ(h) { return h < 7 || h >= 19 ? 0 : h < 9 ? (h - 7) / 2 : h < 17 ? 1 : (19 - h) / 2; }
function diurnal(h) { return Math.sin(2 * Math.PI * (h - 9) / 24); }
function trend(ms) { return Math.min(1, Math.max(0, (ms - TREND_START) / DAY / 56)); }
function vibBase(ms) { return 1.2 + 0.9 * trend(ms); }
function round(v, d) { const f = Math.pow(10, d); return Math.floor(v * f + 0.5) / f; }

/* value of one demo sensor at a quantised time tMs (its own sampling bucket) */
const SIM = {
  'leak-dts':       (h, n) => [30.6 + 0.6 * diurnal(h) + 0.2 * n, 2],
  'leak-alert':     (h, n) => [8.8 + 0.2 * n, 2],
  'leak-vibration': (h, n) => [0.7 + 0.2 * occ(h) + 0.05 * n, 2],
  'leak-puck':      () => [0, 0],
  'hvac-airflow':   (h, n) => [occ(h) > 0 ? 330 + 90 * occ(h) + 12 * n : 140 + 5 * n, 0],
  'hvac-iaq':       (h, n) => [450 + 380 * occ(h) + 15 * n, 0],
  'hvac-comfort':   (h, n) => [0.3 + 2.1 * occ(h) + 0.15 * n, 2],
  'hvac-damper':    (h, n) => [30 + 42 * occ(h) + 2 * n, 0],
  'water-flow':     (h, n) => [h >= 1 && h < 4 ? 0.6 + 0.02 * n : occ(h) > 0 ? 0.08 + 0.06 * Math.abs(n) : 0.01 * Math.abs(n), 3],
  'water-puck':     () => [0, 0],
  'water-alert':    (h, n) => [0.6 + 0.01 * n, 3],
  'power-ct':       (h, n) => [0.2 + 0.33 * occ(h) + 0.02 * n, 3],
  'power-unit':     (h, n) => [0.35 + 0.3 * occ(h) + 0.03 * n, 2],
  'power-bmo':      (h, n) => [175 + 48 * occ(h) + 3 * n, 0],
  'fan-vibration':  (h, n, t) => [vibBase(t) + 0.08 * n, 2],
  'fan-bearing':    (h, n, t) => [46 + 10 * trend(t) + 1.5 * diurnal(h) + 0.3 * n, 2],
  'fan-alert':      (h, n, t) => [(vibBase(t) - vibBase(t - 28 * DAY)) / vibBase(t - 28 * DAY) * 100, 0],
};
function simulate(sensor, nowMs) {
  const iv = sensor.sampling_interval_s * 1000, t = Math.floor(nowMs / iv) * iv, f = SIM[sensor.id];
  if (!f) return missing(sensor, 'demo-sim', 'no simulation model for ' + sensor.id);
  const [v, d] = f(localHour(t), noise(sensor.id, Math.floor(t / iv)), t);
  return {sensor_id: sensor.id, ts: new Date(t).toISOString(), value: round(v, d), unit: sensor.unit, quality: 'good', source: 'demo-sim', simulated: true};
}
function missing(sensor, source, reason) {
  return {sensor_id: sensor.id, ts: null, value: null, unit: sensor.unit, quality: 'missing', source, reason};
}

/* ── live test: the feed URL from ?sensors=live&feed=<url> (absolute, or relative to the page). Accepted only for this machine
   (localhost, 127/8, [::1]) or a private-LAN IPv4 address (10/8, 172.16/12, 192.168/16), http(s), no credentials, a .json path.
   An https page cannot read an http feed (mixed content), except from this machine. -> {live, url, error} ── */
function privateHost(h) {
  h = String(h || '').toLowerCase();
  if (h === 'localhost' || h === '[::1]') return 'loopback';
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(h);
  if (!m) return null;
  const b = m.slice(1).map(Number);
  if (b.some(x => x > 255) || m.slice(1).some(x => x.length > 1 && x[0] === '0')) return null;
  if (b[0] === 127) return 'loopback';
  return b[0] === 10 || (b[0] === 172 && b[1] >= 16 && b[1] <= 31) || (b[0] === 192 && b[1] === 168) ? 'lan' : null;
}
function liveFeedUrl(search, base) {
  let p; try { p = new URLSearchParams(search || ''); } catch (e) { return {live: false, url: null, error: null}; }
  if (p.get('sensors') !== 'live') return {live: false, url: null, error: null};
  const raw = p.get('feed');
  if (!raw) return {live: true, url: null, error: 'no feed URL: add &feed=https://<laptop-ip>:<port>/api/sensors/latest.json'};
  let u, b = null;
  try { b = base ? new URL(base) : null; u = new URL(raw, b || undefined); } catch (e) { return {live: true, url: null, error: 'feed is not a valid URL'}; }
  const refuse = why => ({live: true, url: null, error: 'feed URL refused: ' + why});
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return refuse('only http(s)');
  if (u.username || u.password) return refuse('no credentials in the URL');
  const kind = privateHost(u.hostname);
  if (!kind) return refuse('only this computer or a private-LAN address (10.x, 172.16-31.x, 192.168.x)');
  if (!/\.json$/.test(u.pathname)) return refuse('the path must end in .json');
  if (b && b.protocol === 'https:' && u.protocol === 'http:' && kind !== 'loopback') return refuse('an https page cannot read an http feed; use the gateway https address');
  u.hash = '';
  return {live: true, url: u.href, error: null};
}
/* 'gateway' adapter reading a grimes-sensor-feed/1 snapshot. Every observation is re-checked: it must be valid, carry source
   gateway and must not be simulated; anything else becomes "missing" with a reason (never a fake value). */
const OBS_KEYS = ['sensor_id', 'ts', 'value', 'unit', 'quality', 'source', 'simulated', 'reason'];
function gatewayAdapter(gw, fetchImpl) {
  const url = gw && gw.url, why = gw && gw.error;
  return async sensors => {
    if (!url) return sensors.map(s => missing(s, 'gateway', why || 'wireless gateway adapter not connected yet'));
    let snap;
    const ctl = typeof AbortController !== 'undefined' ? new AbortController() : null, timer = ctl ? setTimeout(() => ctl.abort(), 4000) : null;
    try {
      const r = await fetchImpl(url, {cache: 'no-store', credentials: 'omit', signal: ctl ? ctl.signal : undefined});
      if (!r.ok) throw new Error('HTTP ' + r.status);
      snap = await r.json();
    } catch (e) {
      return sensors.map(s => missing(s, 'gateway', 'gateway not reachable (' + String(e && e.name === 'AbortError' ? 'timeout' : (e && e.message) || e).slice(0, 80) + ')'));
    } finally { if (timer) clearTimeout(timer); }
    if (!snap || snap.schema !== FEED_SCHEMA || !Array.isArray(snap.observations)) return sensors.map(s => missing(s, 'gateway', 'gateway file is not ' + FEED_SCHEMA));
    const by = {};
    for (const o of snap.observations) if (o && typeof o.sensor_id === 'string') by[o.sensor_id] = o;
    return sensors.map(s => {
      const o = by[s.id];
      if (!o) return missing(s, 'gateway', 'no observation from the gateway yet');
      if (!validObservation(o) || o.source !== 'gateway' || o.simulated === true) return missing(s, 'gateway', 'invalid gateway observation refused');
      const out = {}; for (const k of OBS_KEYS) if (o[k] !== undefined) out[k] = o[k];
      if (typeof out.reason !== 'string') delete out.reason;
      return out;
    });
  };
}

/* ── adapters: one per data_source. Real ones replace the stubs (README: BMO meter, BACnet point). ── */
const ADAPTERS = {
  'demo-sim': (sensors, nowMs) => sensors.map(s => simulate(s, nowMs)),
  bms: sensors => sensors.map(s => missing(s, 'bms', 'BMS/BACnet adapter not connected yet' + (s.source_point ? '' : ' (no source_point)'))),
  bmo: sensors => sensors.map(s => missing(s, 'bmo', 'BMO meter adapter not connected yet' + (s.source_point ? '' : ' (no source_point)'))),
  gateway: sensors => sensors.map(s => missing(s, 'gateway', 'wireless gateway adapter not connected yet')),
  fiber: sensors => sensors.map(s => missing(s, 'fiber', 'fiber analyzer adapter not connected yet')),
};
function create({registry, adapters, gateway, fetch: fetchImpl} = {}) {
  const all = (registry && registry.sensors || []).filter(s => s.install_status !== 'retired');
  const by = new Map(all.map(s => [s.id, s])), use = Object.assign({}, ADAPTERS, adapters || {});
  if (gateway && !(adapters && adapters.gateway)) use.gateway = gatewayAdapter(gateway, fetchImpl || (typeof fetch === 'function' ? (u, o) => fetch(u, o) : null));
  async function getLatest(ids, nowMs) {
    const now = finite(nowMs) ? nowMs : Date.now(), want = (ids || [...by.keys()]).map(id => by.get(id)).filter(Boolean), groups = {};
    for (const s of want) (groups[s.data_source] = groups[s.data_source] || []).push(s);
    const out = {};
    for (const [src, list] of Object.entries(groups)) {
      const a = use[src];
      const res = a ? await a(list, now) : list.map(s => missing(s, src, 'unknown data_source ' + src));
      for (const o of res) out[o.sensor_id] = o;
    }
    return out;
  }
  return {getLatest, sensor: id => by.get(id) || null, staleAfter: (registry && registry.feed && registry.feed.stale_after_intervals) || 3};
}

/* ── shared rules: missing is not zero, stale after N x interval, units must match the registry ── */
function assess(obs, sensor, nowMs, staleAfter) {
  const n = staleAfter || 3, now = finite(nowMs) ? nowMs : Date.now();
  const badge = obs && obs.source === 'demo-sim' ? 'Simulated' : 'Live';
  if (!obs || obs.quality === 'missing' || obs.value === null || obs.value === undefined || !obs.ts) return {state: 'missing', badge, label: 'No data', reason: obs && obs.reason || 'no observation'};
  if (obs.unit !== sensor.unit) return {state: 'suspect', badge, label: 'Unit mismatch', reason: obs.unit + ' ≠ ' + sensor.unit};
  const ageS = Math.max(0, (now - Date.parse(obs.ts)) / 1000);
  if (!(ageS <= n * sensor.sampling_interval_s)) return {state: 'stale', badge, label: 'Stale', ageS, reason: 'older than ' + n + ' × ' + sensor.sampling_interval_s + ' s'};
  if (obs.quality === 'suspect') return {state: 'suspect', badge, label: 'Suspect', ageS};
  return {state: 'ok', badge, label: 'Good', ageS};
}
const UNIT_TEXT = {degC: '°C', 'mm/s': 'mm/s', 'm/s2': 'm/s²', CFM: 'CFM', ppm: 'ppm', '%': '%', 'L/s': 'L/s', kW: 'kW', A: 'A'};
function formatValue(value, unit) {
  if (value === null || value === undefined) return '—';
  if (unit === 'bool') return value ? 'Water detected' : 'Dry';
  return (Math.abs(value) >= 100 ? Math.round(value).toLocaleString('en-US') : String(value)) + ' ' + (UNIT_TEXT[unit] || unit);
}
function ageText(s) { return !finite(s) ? '' : s < 60 ? Math.round(s) + ' s ago' : s < 3600 ? Math.floor(s / 60) + ' min ago' : Math.floor(s / 3600) + ' h ago'; }
function escH(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]); }
/* card block: value + unit, age, quality and a Simulated / Live badge (same rules everywhere) */
function feedHtml(sensor, obs, a) {
  const cls = a.badge === 'Simulated' ? 'sim' : 'live', st = a.state;
  return '<div class="sd-feed sd-' + st + '"><span class="sd-src ' + cls + '">' + escH(a.badge.toUpperCase()) + '</span>'
    + '<b>' + escH(st === 'missing' ? 'No data' : formatValue(obs.value, sensor.unit)) + '</b>'
    + '<small>' + escH([st === 'ok' ? ageText(a.ageS) : a.label, st === 'stale' ? 'last value ' + ageText(a.ageS) : '', st === 'ok' ? 'quality ' + obs.quality : a.reason, 'source ' + (obs ? obs.source : sensor.data_source)].filter(Boolean).join(' · ')) + '</small></div>';
}

/* minimal observation check (tests and adapters): the JSON Schema in observation.schema.json is the reference */
function validObservation(o) {
  if (!o || typeof o.sensor_id !== 'string' || !QUALITY.includes(o.quality) || !SOURCES.includes(o.source) || typeof o.unit !== 'string') return false;
  if (o.quality === 'missing') return o.value === null && (o.ts === null || typeof o.ts === 'string');
  return finite(o.value) && typeof o.ts === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d(\.\d+)?)?(Z|[+-]\d\d:\d\d)$/.test(o.ts) && (o.source !== 'demo-sim' || o.simulated === true);
}

return {FEED_SCHEMA, QUALITY, SOURCES, TZ, privateHost, liveFeedUrl, gatewayAdapter, fnv1a, noise, localHour, occ, simulate, create, assess, formatValue, ageText, feedHtml, validObservation, ADAPTERS};
});
