/* twin/mr-align.js — pure helpers for the Quest mixed-reality (passthrough) mode of scan-xr.html (?mode=ar).
   No DOM, no Three.js, no network. Browser global (window.MRAlign) and CommonJS (tests/mr-align.test.cjs).

   Frames
   - BIM: the BIM viewer world of scan-bim.html / scan-xr.html (metres, Y up). Landmarks in
     buildings/grimes/mr-landmarks.json are in this frame.
   - XR: the WebXR 'local-floor' reference space of the current session (gravity-aligned, y = 0 at the floor the
     headset estimated). Its origin and heading are set where the session started, so they change every session.
   Alignment T maps BIM -> XR with a yaw about the vertical axis and a translation (no tilt, no scale; both frames
   are gravity-aligned and metric):   p_xr = R_y(yaw) p_bim + t
   R_y follows registration-core.js apply() and Three.js Object3D.rotation.y: [c x + s z, y, -s x + c z].
   So in the page the BIM group gets rotation.y = yaw (radians) and position = t.

   Honesty: every alignment made here is MANUAL and NOT SURVEYED. The residual measures how consistently the user
   touched the landmarks against the design (BIM) positions; it is not a survey accuracy. */
(function (root, factory) {
  const api = factory();
  if (root) root.MRAlign = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';
const D2R = Math.PI / 180, R2D = 180 / Math.PI;
const LABEL = 'manual alignment, not surveyed';
const MIN_SPREAD_M = 0.5;          // horizontal RMS spread of the plan points below which the heading is undetermined
const SHORT_SPAN_M = 3;            // warn when the plan points span less than this
const finite3 = v => Array.isArray(v) && v.length === 3 && v.every(Number.isFinite);
const wrapDeg = d => { let a = ((d + 180) % 360 + 360) % 360 - 180; return a === -180 ? 180 : a; };

/* ── Rigid yaw + translation ── */
function rotY(yawRad, p) { const c = Math.cos(yawRad), s = Math.sin(yawRad); return [c * p[0] + s * p[2], p[1], -s * p[0] + c * p[2]]; }
function applyT(T, p) { const r = rotY(T.yawDeg * D2R, p); return [r[0] + T.t[0], r[1] + T.t[1], r[2] + T.t[2]]; }
function invertT(T) { const yawDeg = -T.yawDeg, t = rotY(yawDeg * D2R, T.t); return {yawDeg, t: [-t[0], -t[1], -t[2]]}; }
/* compose(A, B): apply B first, then A */
function composeT(A, B) { const t = applyT(A, B.t); return {yawDeg: wrapDeg(A.yawDeg + B.yawDeg), t}; }
function validT(T) { return !!T && Number.isFinite(T.yawDeg) && finite3(T.t); }
const IDENTITY = Object.freeze({yawDeg: 0, t: Object.freeze([0, 0, 0])});

/* ── Fit ──
   pairs: [{id, kind, bim:[x,y,z], xr:[x,y,z]}]
   kind 'xz'  : vertical edge / plumb point; constrains plan position only (heights are ignored)
   kind 'y'   : floor touch; constrains height only (bim[1] = BIM floor height)
   kind 'xyz' : full 3D point
   Yaw + plan translation: least squares over the plan points (closed form, as registration-core fitYawTranslation).
   Height: mean of (xr.y - bim.y) over height points; without one, the Quest floor (xr y = xrFloorY) is assumed to be
   the BIM floor datum floorY. Returns {ok:false, error} when the heading is undetermined. */
const usesPlan = k => k === 'xz' || k === 'xyz', usesHeight = k => k === 'y' || k === 'xyz';
function fitAlignment(pairs, {floorY = null, xrFloorY = 0, _noLoo = false} = {}) {
  const P = (pairs || []).filter(p => p && finite3(p.xr) && Array.isArray(p.bim));
  const plan = P.filter(p => usesPlan(p.kind) && Number.isFinite(p.bim[0]) && Number.isFinite(p.bim[2]));
  const height = P.filter(p => usesHeight(p.kind) && Number.isFinite(p.bim[1]));
  if (plan.length < 2) return {ok: false, error: 'Need at least 2 wall/column points (have ' + plan.length + ')'};
  const n = plan.length, a = [0, 0], b = [0, 0];
  for (const p of plan) { a[0] += p.bim[0]; a[1] += p.bim[2]; b[0] += p.xr[0]; b[1] += p.xr[2]; }
  a[0] /= n; a[1] /= n; b[0] /= n; b[1] /= n;
  let c = 0, s = 0, spread = 0;
  for (const p of plan) {
    const x = p.bim[0] - a[0], z = p.bim[2] - a[1], X = p.xr[0] - b[0], Z = p.xr[2] - b[1];
    c += x * X + z * Z; s += z * X - x * Z; spread += x * x + z * z;
  }
  const spreadM = Math.sqrt(spread / n);
  if (spreadM < MIN_SPREAD_M || Math.hypot(c, s) < 1e-9) return {ok: false, error: 'Points are too close together to fix the heading (spread ' + spreadM.toFixed(2) + ' m < ' + MIN_SPREAD_M + ' m)'};
  const yawDeg = Math.atan2(s, c) * R2D, ra = rotY(yawDeg * D2R, [a[0], 0, a[1]]);
  let ty, heightSource;
  if (height.length) { ty = height.reduce((m, p) => m + (p.xr[1] - p.bim[1]), 0) / height.length; heightSource = height.some(p => p.kind === 'y') ? 'floor-touch' : 'xyz-points'; }
  else if (Number.isFinite(floorY)) { ty = xrFloorY - floorY; heightSource = 'quest-floor-assumed'; }
  else return {ok: false, error: 'No height reference: touch the floor or give the BIM floor datum'};
  const T = {yawDeg: wrapDeg(yawDeg), t: [b[0] - ra[0], ty, b[1] - ra[2]]};
  const res = residuals(T, P);
  const warnings = [];
  const span = maxPlanSpan(plan);
  if (n === 2) warnings.push('Only 2 plan points: the residual only checks their spacing. Add a third point.');
  if (span < SHORT_SPAN_M) warnings.push('Points span only ' + span.toFixed(1) + ' m: heading errors grow with distance from them.');
  if (heightSource === 'quest-floor-assumed') warnings.push('Height assumed from the Quest floor estimate (no floor touch).');
  const loo = n >= 3 && !_noLoo ? leaveOneOut(P, {floorY, xrFloorY}) : null;
  return {ok: true, T, n: P.length, planPoints: n, heightPoints: height.length, heightSource, spreadM, spanM: span, ...res, leaveOneOut: loo, warnings, label: LABEL};
}
function maxPlanSpan(plan) {
  let m = 0;
  for (let i = 0; i < plan.length; i++) for (let j = i + 1; j < plan.length; j++) m = Math.max(m, Math.hypot(plan[i].bim[0] - plan[j].bim[0], plan[i].bim[2] - plan[j].bim[2]));
  return m;
}
/* Per point: horizontal (plan) and vertical residual of the XR touch against the aligned BIM point, metres. */
function residuals(T, pairs) {
  const rows = [];
  let sq = 0, hsq = 0, hn = 0, vsq = 0, vn = 0;
  for (const p of pairs) {
    const q = applyT(T, [Number.isFinite(p.bim[0]) ? p.bim[0] : 0, Number.isFinite(p.bim[1]) ? p.bim[1] : 0, Number.isFinite(p.bim[2]) ? p.bim[2] : 0]);
    const row = {id: p.id, kind: p.kind, horizontalM: null, verticalM: null, errorM: 0};
    if (usesPlan(p.kind)) { row.horizontalM = Math.hypot(p.xr[0] - q[0], p.xr[2] - q[2]); row.dx = p.xr[0] - q[0]; row.dz = p.xr[2] - q[2]; hsq += row.horizontalM ** 2; hn++; }
    if (usesHeight(p.kind)) { row.verticalM = p.xr[1] - q[1]; vsq += row.verticalM ** 2; vn++; }
    row.errorM = Math.hypot(row.horizontalM || 0, row.verticalM || 0);
    sq += row.errorM ** 2; rows.push(row);
  }
  const worst = rows.reduce((w, r) => (!w || r.errorM > w.errorM ? r : w), null);
  return {residuals: rows, rmsM: rows.length ? Math.sqrt(sq / rows.length) : null, horizontalRmsM: hn ? Math.sqrt(hsq / hn) : null, verticalRmsM: vn ? Math.sqrt(vsq / vn) : null,
    maxM: worst ? worst.errorM : null, worst: worst ? worst.id : null};
}
/* For every plan point: refit without it and measure how far its touch is from the prediction. A point much worse than
   the others was probably touched at the wrong place (or the real element differs from the design). */
function leaveOneOut(pairs, opts) {
  const out = {};
  for (const p of pairs) {
    if (!usesPlan(p.kind)) continue;
    const rest = pairs.filter(o => o !== p), f = fitAlignment(rest, {...opts, _noLoo: true});
    if (!f.ok) { out[p.id] = null; continue; }
    const q = applyT(f.T, p.bim);
    out[p.id] = Math.hypot(p.xr[0] - q[0], p.xr[2] - q[2]);
  }
  return out;
}
const cm = m => m == null ? null : Math.round(m * 1000) / 10;   // metres -> cm, 1 decimal
/* Short text for the panel: "RMS 2.3 cm · worst C 3.9 cm (4 points, floor touch)" */
function summary(fit) {
  if (!fit || !fit.ok) return fit?.error || 'Not aligned';
  const w = fit.residuals.find(r => r.id === fit.worst);
  return 'RMS ' + cm(fit.rmsM).toFixed(1) + ' cm · worst ' + fit.worst + ' ' + cm(w.errorM).toFixed(1) + ' cm · ' + fit.n + ' points · height ' +
    {'floor-touch': 'floor touch', 'xyz-points': '3D points', 'quest-floor-assumed': 'Quest floor (assumed)'}[fit.heightSource];
}

/* ── Manual nudge (fine-tuning after the fit) ──
   move: XR-frame translation added to t. yawDeg: turn the BIM about the vertical axis through pivot (XR frame,
   normally the head): p' = R(phi)(p - c) + c  =>  yaw' = yaw + phi, t' = R(phi)(t - c) + c. */
function nudge(T, {move = [0, 0, 0], yawDeg = 0, pivot = [0, 0, 0]} = {}) {
  let out = {yawDeg: T.yawDeg, t: T.t.slice()};
  if (yawDeg) {
    const r = rotY(yawDeg * D2R, [out.t[0] - pivot[0], 0, out.t[2] - pivot[2]]);
    out = {yawDeg: wrapDeg(out.yawDeg + yawDeg), t: [r[0] + pivot[0], out.t[1], r[2] + pivot[2]]};
  }
  out.t = [out.t[0] + move[0], out.t[1] + move[1], out.t[2] + move[2]];
  return out;
}
/* Thumbstick step in the user's heading: forward = where the head looks (projected on the floor). headYaw = the
   head's yaw in XR (radians, 0 = looking along -z). Returns an XR-frame [dx, 0, dz] of length step. */
function headingStep(direction, headYaw, step) {
  const f = [-Math.sin(headYaw), 0, -Math.cos(headYaw)], r = [Math.cos(headYaw), 0, -Math.sin(headYaw)];
  const v = direction === 'forward' ? f : direction === 'back' ? f.map(x => -x) : direction === 'right' ? r : direction === 'left' ? r.map(x => -x) : [0, 0, 0];
  return v.map(x => x * step + 0);
}
/* Yaw (radians) of a quaternion [x, y, z, w]: heading of its rotated -z axis on the floor (0 = -z). */
function yawFromQuaternion(q) {
  const [x, y, z, w] = q;
  const fx = -(2 * (x * z + w * y)), fz = -(1 - 2 * (x * x + y * y));   // R * (0,0,-1)
  return Math.atan2(-fx, -fz);
}
const NUDGE_STEPS = Object.freeze({fine: {moveM: 0.01, yawDeg: 0.25}, coarse: {moveM: 0.05, yawDeg: 1}});

/* ── Persistence ──
   An XR anchor is the only thing that survives a new session: the alignment is stored RELATIVE to the anchor
   (T_anchor = A^-1 . T) and rebuilt from the anchor's pose next time (T = A' . T_anchor). Without an anchor the stored
   alignment is in the old session's local-floor frame and is valid only if the new session starts at the same spot
   and heading; the page says so and asks for a landmark check. Anchor poses are reduced to yaw + position
   (gravity-aligned), so a slightly tilted anchor never tilts the BIM. */
const STORE_KEY = 'grimes-mr-alignment/1', SCHEMA = 'grimes-mr-alignment/1';
function anchorT(position, quaternion) { return {yawDeg: wrapDeg(yawFromQuaternion(quaternion) * R2D), t: position.slice()}; }
function toAnchorFrame(T, A) { return composeT(invertT(A), T); }
function fromAnchorFrame(local, A) { return composeT(A, local); }
function makeRecord({area, level, T, fit = null, anchorHandle = null, anchorLocal = null, nudged = false, created = new Date().toISOString()}) {
  if (!validT(T)) throw new Error('alignment must be a finite yaw + translation');
  return {schema: SCHEMA, area: String(area || ''), level: String(level || ''), created, yawDeg: T.yawDeg, t: T.t.slice(),
    rmsCm: fit?.ok ? cm(fit.rmsM) : null, points: fit?.ok ? fit.n : null, heightSource: fit?.ok ? fit.heightSource : null, nudged: !!nudged,
    frame: anchorHandle && validT(anchorLocal) ? 'anchor' : 'session', anchor: anchorHandle && validT(anchorLocal) ? {handle: String(anchorHandle), local: {yawDeg: anchorLocal.yawDeg, t: anchorLocal.t.slice()}} : null,
    label: LABEL};
}
function parseRecord(text) {
  let r; try { r = typeof text === 'string' ? JSON.parse(text) : text; } catch (e) { return null; }
  if (!r || r.schema !== SCHEMA || !Number.isFinite(r.yawDeg) || !finite3(r.t) || typeof r.area !== 'string') return null;
  if (r.frame === 'anchor' && !(r.anchor && typeof r.anchor.handle === 'string' && validT(r.anchor.local))) return null;
  if (r.frame !== 'anchor' && r.frame !== 'session') return null;
  return r;
}
/* storage: a Web Storage object (localStorage). Every access is guarded: private mode / blocked storage must not break MR. */
function saveRecord(storage, record) { try { storage.setItem(STORE_KEY, JSON.stringify(record)); return true; } catch (e) { return false; } }
function loadRecord(storage) { try { return parseRecord(storage.getItem(STORE_KEY)); } catch (e) { return null; } }
function clearRecord(storage) { try { storage.removeItem(STORE_KEY); return true; } catch (e) { return false; } }
/* check log (sprinkler / diffuser offsets), newest last, capped */
const CHECK_KEY = 'grimes-mr-checks/1';
function appendCheck(storage, row, cap = 200) {
  try { const list = JSON.parse(storage.getItem(CHECK_KEY) || '[]'); const out = Array.isArray(list) ? list : []; out.push(row); storage.setItem(CHECK_KEY, JSON.stringify(out.slice(-cap))); return out.length; } catch (e) { return 0; }
}
function loadChecks(storage) { try { const l = JSON.parse(storage.getItem(CHECK_KEY) || '[]'); return Array.isArray(l) ? l : []; } catch (e) { return []; } }

/* ── Check points: BIM element vs the installed one ──
   The user holds the tip directly below the real device (plumb). Offset = touch - aligned BIM centre, in the plan.
   Reported in BIM axes too (rotate back by -yaw) so offsets from different sessions are comparable. */
function checkOffset(T, bim, xr) {
  const q = applyT(T, bim), d = [xr[0] - q[0], 0, xr[2] - q[2]], inBim = rotY(-T.yawDeg * D2R, d);
  return {horizontalCm: cm(Math.hypot(d[0], d[2])), dxBimCm: cm(inBim[0]), dzBimCm: cm(inBim[2]), heightBelowCm: cm(q[1] - xr[1])};
}

/* ── Landmark file ── */
function validateLandmarks(doc) {
  if (!doc || doc.schema !== 'grimes-mr-landmarks/1' || !Array.isArray(doc.areas) || !doc.areas.length) throw new Error('mr-landmarks.json: unexpected schema');
  for (const a of doc.areas) {
    if (typeof a.id !== 'string' || !Number.isFinite(a.floorY) || !Array.isArray(a.points)) throw new Error('mr-landmarks.json: bad area');
    const plan = a.points.filter(p => usesPlan(p.kind));
    if (plan.length < 2) throw new Error('mr-landmarks.json: area ' + a.id + ' needs at least 2 plan points');
    for (const p of a.points) {
      if (!['xz', 'y', 'xyz'].includes(p.kind) || !Array.isArray(p.bim) || p.bim.length !== 3) throw new Error('mr-landmarks.json: bad point ' + a.id + '/' + p.id);
      if (usesPlan(p.kind) && !(Number.isFinite(p.bim[0]) && Number.isFinite(p.bim[2]))) throw new Error('mr-landmarks.json: plan point without x/z ' + p.id);
      if (usesHeight(p.kind) && !Number.isFinite(p.bim[1])) throw new Error('mr-landmarks.json: height point without y ' + p.id);
    }
    for (const c of a.checks || []) if (!finite3(c.bim)) throw new Error('mr-landmarks.json: bad check ' + c.id);
  }
  return doc;
}
function areaById(doc, id) { return doc.areas.find(a => a.id === id) || doc.areas[0]; }
/* the BIM point used for a capture: height points carry only y (x/z are free), so return the floor datum there */
function landmarkBim(area, p) { return p.kind === 'y' ? [null, Number.isFinite(p.bim[1]) ? p.bim[1] : area.floorY, null] : p.bim.slice(); }

/* ── Alignment session state machine (pure; the page renders it) ──
   steps: one per landmark (capture or skip), then 'review' (residual, redo / accept), then 'aligned'. */
function createSession(area) {
  return {area: area.id, index: 0, captures: {}, skipped: {}, fit: null, phase: 'capture'};
}
function currentPoint(area, s) { return s.phase === 'capture' ? area.points[s.index] || null : null; }
function capture(area, s, xr) {
  const p = currentPoint(area, s); if (!p || !finite3(xr)) return s;
  s.captures[p.id] = xr.slice(); delete s.skipped[p.id];
  return advance(area, s);
}
function skip(area, s) { const p = currentPoint(area, s); if (!p) return s; s.skipped[p.id] = true; delete s.captures[p.id]; return advance(area, s); }
function advance(area, s) {
  s.index++;
  if (s.index >= area.points.length) { s.phase = 'review'; s.fit = solveSession(area, s); }
  return s;
}
/* redo one point (or the last captured one) */
function redo(area, s, id = null) {
  const target = id || [...area.points].reverse().find(p => s.captures[p.id] || s.skipped[p.id])?.id;
  const i = area.points.findIndex(p => p.id === target);
  if (i < 0) return s;
  delete s.captures[target]; delete s.skipped[target]; s.index = i; s.phase = 'capture'; s.fit = null;
  return s;
}
/* jump to review early (>= 2 plan points captured) */
function finishEarly(area, s) { s.phase = 'review'; s.fit = solveSession(area, s); return s; }
function sessionPairs(area, s) { return area.points.filter(p => s.captures[p.id]).map(p => ({id: p.id, kind: p.kind, bim: landmarkBim(area, p), xr: s.captures[p.id]})); }
function solveSession(area, s) { return fitAlignment(sessionPairs(area, s), {floorY: area.floorY}); }
function capturedPlanCount(area, s) { return area.points.filter(p => usesPlan(p.kind) && s.captures[p.id]).length; }

/* ── Shader mirror (scan-xr.html FRAG with the MR uniforms) ──
   lens: alpha = opacity * mix(outside, 1, coneWeight); all: alpha = opacity. Then the distance fade of
   twin/overlay-visibility.js: alpha *= 1 - smoothstep(fadeStart, fadeEnd, distance). */
function smoothstep(e0, e1, x) { const t = Math.max(0, Math.min(1, (x - e0) / (e1 - e0))); return t * t * (3 - 2 * t); }
function mrAlpha({mode = 'lens', opacity = 0.85, cone = 1, outside = 0, distance = 0, fade = null} = {}) {
  let a = mode === 'all' ? opacity : opacity * (outside + (1 - outside) * cone);
  if (fade && Number.isFinite(fade[1])) a *= 1 - smoothstep(fade[0], fade[1], distance);
  return a;
}

/* ── MR panel (world-locked canvas) ── buttons in a cols x rows grid in the lower part; (u, v) plane UVs, v up. */
const PANEL = {cols: 5, rows: 3, left: .025, right: .975, top: .52, bottom: .97, gap: .012};
function gridRect(L, i) {
  const w = (L.right - L.left - L.gap * (L.cols - 1)) / L.cols, h = (L.bottom - L.top - L.gap * (L.rows - 1)) / L.rows;
  const c = i % L.cols, r = Math.floor(i / L.cols);
  return {x: L.left + c * (w + L.gap), y: L.top + r * (h + L.gap), w, h};
}
function gridHit(L, u, v) {
  const x = u, y = 1 - v;
  for (let i = 0; i < L.cols * L.rows; i++) { const r = gridRect(L, i); if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) return i; }
  return -1;
}

/* ── Desktop simulation / tests: synthetic XR touches from a known transform with Gaussian noise ── */
function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function gauss(r) { let u = 0, v = 0; while (u === 0) u = r(); while (v === 0) v = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
/* xz points: touched at a random height (the height is free); y points: on the floor at a random spot */
function simulateTouch(area, p, Ttrue, {noiseM = 0.01, random = Math.random, xrFloorY = 0} = {}) {
  if (p.kind === 'y') {
    const q = applyT(Ttrue, [0, area.floorY, 0]);
    return [random() * 4 - 2, q[1] + gauss(random) * noiseM, random() * 4 - 2];
  }
  const b = p.bim.slice(); if (p.kind === 'xz') b[1] = area.floorY + 0.6 + random() * 0.8;
  const q = applyT(Ttrue, b);
  return [q[0] + gauss(random) * noiseM, q[1] + (p.kind === 'xyz' ? gauss(random) * noiseM : 0), q[2] + gauss(random) * noiseM];
}

return {LABEL, MIN_SPREAD_M, SHORT_SPAN_M, IDENTITY, rotY, applyT, invertT, composeT, validT, wrapDeg,
  fitAlignment, residuals, leaveOneOut, cm, summary, nudge, headingStep, yawFromQuaternion, NUDGE_STEPS,
  STORE_KEY, CHECK_KEY, SCHEMA, anchorT, toAnchorFrame, fromAnchorFrame, makeRecord, parseRecord, saveRecord, loadRecord, clearRecord, appendCheck, loadChecks,
  checkOffset, validateLandmarks, areaById, landmarkBim, createSession, currentPoint, capture, skip, redo, finishEarly, sessionPairs, solveSession, capturedPlanCount,
  smoothstep, mrAlpha, PANEL, gridRect, gridHit, rng, gauss, simulateTouch};
});
