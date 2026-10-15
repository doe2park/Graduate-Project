/* twin/element-cards.js — shared, pure element-card helpers (no DOM, no network, no Three.js).
   Single source for the Walk-mode gaze card in grimes-bim-viewer.html and the Overlay-Lens info card in
   scan-compare.html / scan-bim.html. See docs/ELEMENT_FEEDS.md for the tier ladder.

   Honesty rules (thesis principle, do not weaken):
   - LIVE only for a finite reading <= 45 min old from an explicit element feed (element-feeds.json).
   - Older readings are LATEST with "Last reading HH:MM · Nh ago" (Pacific); a missing value is never 0.
   - MODELLED = uncalibrated design-ratio share of a building meter; CONTEXT = building/feeder total.
     Neither is the element's own measurement. NONE = nothing is bound.
   - An as-built position adjustment is labelled "manual, not surveyed".

   Works as a browser global (window.ElementCards) and as CommonJS (tests). Also usable inside a vm context:
   the global is attached to the evaluating global object. */
(function (root, factory) {
  const api = factory();
  if (root) root.ElementCards = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';

const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* BMO naive timestamps are America/Los_Angeles wall time; DST-fold readings are ambiguous -> NaN (TIME UNKNOWN). */
function bmoTimestamp(raw) {
  const text = String(raw || '').trim();
  if (/Z$|[+-]\d{2}:?\d{2}$/.test(text)) return Date.parse(text);
  const m = text.match(/^(\d{4})-(\d\d)-(\d\d)[ T](\d\d):(\d\d)(?::(\d\d))?$/);
  if (!m) return NaN;
  const target = Date.UTC(+m[1],+m[2]-1,+m[3],+m[4],+m[5],+(m[6]||0));
  const fmt = new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
  const wall = at => { const p=Object.fromEntries(fmt.formatToParts(at).map(x=>[x.type,x.value]));return Date.UTC(+p.year,+p.month-1,+p.day,+p.hour,+p.minute,+p.second); };
  let at=target;
  for(let i=0;i<3;i++) at+=target-wall(at);
  // Naive readings during a DST fold cannot identify which occurrence was measured.
  if(wall(at)!==target || wall(at-3600000)===target || wall(at+3600000)===target) return NaN;
  return at;
}
function meterReading(m) {
  const kw = m?.latest?.kw;
  const value = Number.isFinite(kw) ? kw : null;
  const raw = m?.latest?.t || m?.latest?.timestamp;
  const at = bmoTimestamp(raw);
  const age = Date.now() - at;
  return {value, at, state: value == null ? 'OFFLINE' : !Number.isFinite(at) ? 'TIME UNKNOWN'
    : age > 45 * 60 * 1000 || age < -5 * 60 * 1000 ? 'STALE' : 'LIVE'};
}
/* Shared reading vocabulary (weekly-report safe): LIVE = finite value no older than 45 min;
   LATEST = older finite value, neutral grey, with its Pacific-time age; no value = em dash. */
const PT_CLOCK = new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
function readingAgeText(at, now = Date.now()) {
  if (!Number.isFinite(at)) return 'Last reading time unavailable';
  const mins = Math.max(0, Math.round((now - at) / 60000));
  const ago = mins < 60 ? mins + 'm ago' : mins < 2880 ? Math.floor(mins / 60) + 'h ago' : Math.floor(mins / 1440) + 'd ago';
  return `Last reading ${PT_CLOCK.format(at)} · ${ago}`;
}
const NO_READING_TEXT = 'No reading in this window';
function readingDisplay(r) {
  if (r.value == null) return {label: 'NO READING', cls: 'badge na', note: NO_READING_TEXT, live: false};
  if (r.state === 'LIVE') return {label: 'LIVE', cls: 'badge', note: '', live: true};
  return {label: 'LATEST', cls: 'badge na', note: readingAgeText(r.at), live: false};
}
function aggregateReadings(readings) {
  const have = readings.filter(r => r.value != null), n = readings.length;
  const complete = n > 0 && have.length === n, sum = have.reduce((a, r) => a + r.value, 0);
  const partialNote = `${have.length} of ${n} meters`;
  if (!have.length) return {have: 0, n, complete: false, sum: null, label: 'NO READING', cls: 'badge na', note: NO_READING_TEXT, live: false};
  if (!complete) return {have: have.length, n, complete, sum, label: 'PARTIAL', cls: 'badge na', note: partialNote, live: false};
  if (have.every(r => r.state === 'LIVE')) return {have: n, n, complete, sum, label: 'LIVE', cls: 'badge', note: '', live: true};
  const oldest = Math.min(...have.filter(r => r.state !== 'LIVE').map(r => Number.isFinite(r.at) ? r.at : -Infinity));
  return {have: n, n, complete, sum, label: 'LATEST', cls: 'badge na', note: readingAgeText(Number.isFinite(oldest) ? oldest : NaN), live: false};
}
const fmtKw = w => w < 1 ? (w * 1000).toFixed(0) + ' W' : w.toFixed(2) + ' kW';
// MODELLED share of one building meter. Never a measurement of the element itself.
function modelledShare(info, meters) {
  const ap = info.apportion;
  if (!ap) return null;
  const reading = meterReading(meters?.[ap.meter]);
  const share = Number.isFinite(ap.share) ? ap.share : null;
  return {ap, reading, share, est: reading.value != null && share != null ? reading.value * share : null};
}

/* Gaze / lens card — feed tier resolution, dwell and card markup.
   Precedence: explicit element feed > MODELLED apportionment > building-meter CONTEXT > NONE.
   Only an explicit entry in element-feeds.json can ever produce a LIVE element reading. */
const GAZE_DWELL_MS = 400, GAZE_GRACE_MS = 250;
const GAZE_TIER_CLASS = {LIVE: 'live', LATEST: 'latest', 'NO READING': 'latest', MODELLED: 'mod', CONTEXT: 'ctx', NONE: 'none'};
function elementFeedEntry(id, meta, feeds) {
  const els = feeds && typeof feeds === 'object' ? feeds.elements : null;
  if (!els || typeof els !== 'object') return null;
  // "<layer>:<id>" (collision-safe) wins over the bare source element id.
  for (const key of [meta?.layer ? meta.layer + ':' + id : null, String(id)]) {
    const list = key && Object.prototype.hasOwnProperty.call(els, key) ? els[key] : null;
    const entry = Array.isArray(list) ? list.find(e => e && typeof e.ref === 'string' && e.ref) : null;
    if (entry) return entry;
  }
  return null;
}
function elementFeedTier(id, meta, feeds, meters) {
  const out = (tier, label, valueText, detailText = '', sourceText = '') => ({tier, label, cls: GAZE_TIER_CLASS[tier], valueText, detailText, sourceText});
  const entry = elementFeedEntry(id, meta, feeds);
  if (entry) {
    const reading = meterReading(meters?.[String(entry.ref).split(':')[2]]);
    const src = String(entry.source || entry.ref);
    if (reading.value == null) return out('NO READING', 'NO READING', NO_READING_TEXT, '', src);
    const unit = entry.unit && entry.unit !== 'kW' ? entry.unit : null;
    const valueText = unit ? +reading.value.toFixed(2) + ' ' + unit : fmtKw(reading.value);
    return reading.state === 'LIVE' ? out('LIVE', 'LIVE', valueText, '', src)
      : out('LATEST', 'LATEST', valueText, readingAgeText(reading.at), src);
  }
  const share = meta?.apportion ? modelledShare(meta, meters) : null;
  if (share) {
    const basis = String(share.ap.basis || 'design').replace(/\s*ratio$/i, '');
    const age = share.reading.value != null && share.reading.state !== 'LIVE' ? readingAgeText(share.reading.at) : '';
    return out('MODELLED', 'MODELLED', share.est != null ? '≈ ' + fmtKw(share.est) + ' modelled share' : NO_READING_TEXT,
      `from building meter ${share.ap.meter} · ${basis} ratio`, age);
  }
  const refs = Array.isArray(meta?.isFedBy) ? meta.isFedBy : [];
  if (refs.length) {
    const ids = [...new Set(refs.map(r => String(r).split(':')[2]).filter(Boolean))];
    const agg = aggregateReadings(ids.map(n => meterReading(meters?.[n])));
    const label = (ids.length > 1 ? 'Building meters ' : 'Building meter ') + ids.join(', ') + ' context';
    const valueText = agg.have && agg.sum != null ? (agg.complete ? '' : 'Partial · ') + agg.sum.toFixed(1) + ' kW' : NO_READING_TEXT;
    return out('CONTEXT', 'CONTEXT', valueText, label + ' · not this element’s own reading', agg.live ? '' : agg.have ? agg.note : '');
  }
  return out('NONE', 'NO FEED', 'No feed yet', 'Sensor link not yet connected');
}
// Dwell: the same resolved element must stay under the crosshair / lens for GAZE_DWELL_MS. opts.force satisfies it (capture hook).
function gazeDwell(state, id, now, opts) {
  if (!id) { state.id = null; state.since = 0; return {show: false}; }
  if (state.id !== id) { state.id = id; state.since = now; }
  if (opts && opts.force) state.since = Math.min(state.since, now - GAZE_DWELL_MS);
  return {show: now - state.since >= GAZE_DWELL_MS};
}
/* "As-built · manual, not surveyed · moved 12 cm · yaw 1.0°" — only when an adjustment is actually applied. */
function adjustmentLine(adj) {
  if (!adj || !Array.isArray(adj.translation) || adj.translation.length !== 3 || !adj.translation.every(Number.isFinite)) return '';
  const cm = Math.round(Math.hypot(...adj.translation) * 100), yaw = Number.isFinite(adj.yawDegrees) ? adj.yawDegrees : 0;
  return 'As-built · manual, not surveyed · moved ' + cm + ' cm' + (yaw ? ' · yaw ' + yaw.toFixed(1) + '°' : '');
}
function gazeCardHtml(id, meta, tier, opts) {
  const short = String(meta?.name || meta?.type || 'Element');
  const name = short.length > 34 ? short.slice(0, 33) + '…' : short;
  const sub = [meta?.type, meta?.system, meta?.level].filter(Boolean).join(' · ');
  const adj = opts && opts.adjustment ? adjustmentLine(opts.adjustment) : '';
  return `<div class="gz-top"><span class="gz-name">${esc(name)}</span><span class="gz-badge ${esc(tier.cls)}">${esc(tier.label)}</span></div>`
    + (sub ? `<div class="gz-sub">${esc(sub)}</div>` : '')
    + `<div class="gz-val">${esc(tier.valueText)}</div>`
    + (tier.detailText ? `<div class="gz-det">${esc(tier.detailText)}</div>` : '')
    + (tier.sourceText ? `<div class="gz-det">${esc(tier.sourceText)}</div>` : '')
    + (adj ? `<div class="gz-adj">${esc(adj)}</div>` : '');
}

/* ── Overlay-Lens pick contract (scan-compare.html <-> scan-bim.html, same-origin postMessage) ──
   parent -> BIM pane : {type:'grimes-lens-probe', seq, x, y}            x,y normalised 0..1 in the BIM iframe rect
   BIM pane -> parent : {type:'grimes-lens-pick', seq, x, y, hit}        hit = null | {id, layer, meta, tier, adjustment, point?}
   point (optional) = raycast hit in BIM world metres (the frame the linked camera pose uses); used by the Overlay Align tool.
   The BIM pane raycasts its own visible element layers; the parent only positions and renders the card. */
const LENS_PROBE = 'grimes-lens-probe', LENS_PICK = 'grimes-lens-pick';
const CARD_META_FIELDS = ['name', 'type', 'system', 'level', 'layer'];
const TIER_FIELDS = ['tier', 'label', 'cls', 'valueText', 'detailText', 'sourceText'];
const KNOWN_TIERS = Object.keys(GAZE_TIER_CLASS);
const unit = v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;
const point3 = p => Array.isArray(p) && p.length === 3 && p.every(v => typeof v === 'number' && Number.isFinite(v)) ? p.slice() : null;
const shortStr = (v, n = 200) => typeof v === 'string' ? v.slice(0, n) : '';
function cardMeta(info, layer) {
  const out = {};
  for (const k of CARD_META_FIELDS) if (typeof info?.[k] === 'string' && info[k]) out[k] = info[k].slice(0, 200);
  if (layer) out.layer = String(layer).slice(0, 40);
  return out;
}
function cleanTier(t) {
  if (!t || !KNOWN_TIERS.includes(t.tier)) return null;
  const out = {};
  for (const k of TIER_FIELDS) out[k] = shortStr(t[k]);
  out.cls = GAZE_TIER_CLASS[t.tier];   // class is derived, never trusted from the message
  return out;
}
function cleanAdjustment(a) {
  if (!a || !Array.isArray(a.translation) || a.translation.length !== 3 || !a.translation.every(Number.isFinite)) return null;
  return {translation: a.translation.slice(), yawDegrees: Number.isFinite(a.yawDegrees) ? a.yawDegrees : 0, status: 'manual-unsurveyed'};
}
function lensProbeMessage(seq, x, y) {
  if (!Number.isInteger(seq) || !unit(x) || !unit(y)) return null;
  return {type: LENS_PROBE, seq, x, y};
}
function parseLensProbe(d) {
  return d && d.type === LENS_PROBE ? lensProbeMessage(d.seq, d.x, d.y) : null;
}
function lensPickMessage({seq, x, y, id, layer, info, tier, adjustment, point}) {
  const hit = id != null && id !== '' && layer ? {id: String(id), layer: String(layer), meta: cardMeta(info, layer), tier: cleanTier(tier), adjustment: cleanAdjustment(adjustment)} : null;
  if (hit && point3(point)) hit.point = point3(point);
  if (hit && !hit.tier) return {type: LENS_PICK, seq, x, y, hit: null};
  return {type: LENS_PICK, seq, x, y, hit};
}
/* Parent-side acceptance: drops malformed or out-of-order (stale) replies. Returns null or a clean copy. */
function parseLensPick(d, lastSeq) {
  if (!d || d.type !== LENS_PICK || !Number.isInteger(d.seq) || (Number.isInteger(lastSeq) && d.seq <= lastSeq)) return null;
  if (!unit(d.x) || !unit(d.y)) return null;
  if (d.hit == null) return {seq: d.seq, x: d.x, y: d.y, hit: null};
  const h = d.hit;
  if (typeof h.id !== 'string' || !h.id || typeof h.layer !== 'string' || !/^[a-z]+$/.test(h.layer)) return null;
  const tier = cleanTier(h.tier);
  if (!tier) return null;
  const hit = {id: h.id.slice(0, 80), layer: h.layer, meta: cardMeta(h.meta, h.layer), tier, adjustment: cleanAdjustment(h.adjustment)};
  if (point3(h.point)) hit.point = point3(h.point);   // optional; older panes omit it, malformed points are dropped
  return {seq: d.seq, x: d.x, y: d.y, hit};
}
/* Card placement next to a lens ring (compare-page pixels). Desktop: right of the ring, flipped left at the edge.
   Mobile: centred above the bottom controls (bottomInset px reserved). */
function lensCardPosition({cx, cy, r, w, h, vw, vh, mobile, bottomInset = 0, margin = 8}) {
  let x, y;
  if (mobile) { x = vw / 2 - w / 2; y = vh - bottomInset - h - margin; }
  else { x = cx + r + 14; y = cy - h / 2; if (x + w > vw - margin) x = cx - r - 14 - w; }
  x = Math.max(margin, Math.min(vw - w - margin, x)); y = Math.max(margin, Math.min(vh - h - margin, y));
  return {x: Math.round(x), y: Math.round(y)};
}

return {esc, bmoTimestamp, meterReading, PT_CLOCK, readingAgeText, NO_READING_TEXT, readingDisplay, aggregateReadings, fmtKw, modelledShare,
  GAZE_DWELL_MS, GAZE_GRACE_MS, GAZE_TIER_CLASS, elementFeedEntry, elementFeedTier, gazeDwell, adjustmentLine, gazeCardHtml,
  LENS_PROBE, LENS_PICK, cardMeta, lensProbeMessage, parseLensProbe, lensPickMessage, parseLensPick, lensCardPosition};
});
