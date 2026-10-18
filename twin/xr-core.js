/* twin/xr-core.js — pure helpers for scan-xr.html (Quest WebXR Scan<->BIM overlay). No DOM, no network, no Three.js.
   Works as a browser global (window.ScanXRCore) and as CommonJS (tests/scan-xr-core.test.cjs).

   Frames (same as scan-photo.html / scan-compare.html):
   - Stations, the photo sphere and the viewer live in the capture's SCAN frame (E57, Y-up metres).
   - BIM element layers live in the BIM viewer world. The accepted rigid registration maps scan -> BIM:
       p_bim = R_y(theta) p_scan + t        (registration-core.js apply())
     scan-compare converts the photo camera into the BIM frame with exactly this map. scan-xr instead keeps the
     viewer in the scan frame and places the BIM under one group carrying the INVERSE map; the relative geometry
     between eye, photo pixels and BIM services is identical (tests check this against registration-core.js).
   Honesty: May 6 = accepted registration (internal residual, not surveyed); Sep 17 = provisional alignment. */
(function (root, factory) {
  const api = factory();
  if (root) root.ScanXRCore = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';
const D2R = Math.PI / 180;

/* ── Captures ── default May 6 (accepted registration); Sep 17 is selectable and always labelled provisional. */
const CAPTURES = {
  '2026-05-06': {date: '2026-05-06', label: 'May 6, 2026', provisional: false,
    photo: 'scan-assets/panoramas/manifest.json', registration: 'alignment-analysis/accepted-registration.json',
    alignmentText: 'registered (internal residual ≈0.13 m, not surveyed)'},
  '2026-09-17': {date: '2026-09-17', label: 'Sep 17, 2026', provisional: true,
    photo: 'scan-assets/captures/2026-09-17/panoramas/manifest.json', registration: 'scan-assets/captures/2026-09-17/registration.json',
    alignmentText: 'PROVISIONAL alignment (not surveyed)'},
};
const DEFAULT_CAPTURE = '2026-05-06';
function captureConfig(date) {
  const c = CAPTURES[Object.prototype.hasOwnProperty.call(CAPTURES, date) ? date : DEFAULT_CAPTURE];
  return {...c};
}
/* A registration file must be a finite yaw + 3-vector, scale 1 (the only model registration-core supports). */
function validRegistration(reg) {
  return !!reg && Number.isFinite(reg.rotationYDegrees) && Array.isArray(reg.translation) && reg.translation.length === 3
    && reg.translation.every(Number.isFinite) && (reg.scale == null || reg.scale === 1);
}

/* ── Registration placement ── same convention as registration-core.js apply()/invert() and scan-compare convert(). */
function applyReg(reg, p) { const a = reg.rotationYDegrees * D2R, c = Math.cos(a), s = Math.sin(a), t = reg.translation; return [c * p[0] + s * p[2] + t[0], p[1] + t[1], -s * p[0] + c * p[2] + t[2]]; }
function invertReg(reg, p) { const a = reg.rotationYDegrees * D2R, c = Math.cos(a), s = Math.sin(a), t = reg.translation, x = p[0] - t[0], y = p[1] - t[1], z = p[2] - t[2]; return [c * x - s * z, y, s * x + c * z]; }
/* Object3D parameters for the BIM root group inside the scan-frame scene: rotation.y (radians) then position.
   Three.js composes M = T * R, so p_scan = R_y(-theta) p_bim + invert(reg, 0) = R_y(-theta)(p_bim - t) = invert(reg, p_bim). */
function bimRootTransform(reg) {
  if (!validRegistration(reg)) throw new Error('Registration must be a finite yaw + XYZ translation with scale 1');
  return {rotationY: -reg.rotationYDegrees * D2R, position: invertReg(reg, [0, 0, 0])};
}
function applyRootTransform(tf, p) { const c = Math.cos(tf.rotationY), s = Math.sin(tf.rotationY); return [c * p[0] + s * p[2] + tf.position[0], p[1] + tf.position[1], -s * p[0] + c * p[2] + tf.position[2]]; }

/* ── Photo sphere orientation (scan-photo.html stationOrientation, verbatim maths) ──
   q = axis * e57 * axis^-1 * centerCorrection, axis = rotX(-90deg), centerCorrection = rotY(180deg);
   an optional per-station heading offset is pre-multiplied as rotY(deg). Quaternions are [x, y, z, w]. */
function quatMul(a, b) {
  const [ax, ay, az, aw] = a, [bx, by, bz, bw] = b;
  return [aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz];
}
const quatAxisAngle = (axis, rad) => { const s = Math.sin(rad / 2); return [axis[0] * s, axis[1] * s, axis[2] * s, Math.cos(rad / 2)]; };
const AXIS = quatAxisAngle([1, 0, 0], -Math.PI / 2), AXIS_INV = [-AXIS[0], -AXIS[1], -AXIS[2], AXIS[3]], CENTER = quatAxisAngle([0, 1, 0], Math.PI);
function normalizeQuat(q) { const n = Math.hypot(...q) || 1; return q.map(v => v / n); }
function stationQuaternion(e57Quaternion, headingOffsetDegrees = 0) {
  const q = quatMul(quatMul(quatMul(AXIS, normalizeQuat(e57Quaternion)), AXIS_INV), CENTER);
  const d = Number(headingOffsetDegrees);
  return Number.isFinite(d) && d ? quatMul(quatAxisAngle([0, 1, 0], d * D2R), q) : q;
}
function rotateByQuat(q, v) { const p = quatMul(quatMul(q, [v[0], v[1], v[2], 0]), [-q[0], -q[1], -q[2], q[3]]); return [p[0], p[1], p[2]]; }

/* ── X-ray flashlight cone ── mirrors the GLSL in scan-xr.html:
   w = smoothstep(cos(half) - soft, cos(half), dot(normalize(p - origin), dir)). dir must be unit length. */
function coneCos(halfAngleDegrees) { return Math.cos(Math.max(0.5, Math.min(60, halfAngleDegrees)) * D2R); }
function smoothstep(e0, e1, x) { const t = Math.max(0, Math.min(1, (x - e0) / (e1 - e0))); return t * t * (3 - 2 * t); }
function coneWeight(origin, dir, cosHalf, soft, p) {
  const d = [p[0] - origin[0], p[1] - origin[1], p[2] - origin[2]], n = Math.hypot(...d);
  if (!(n > 1e-9)) return 1;
  return smoothstep(cosHalf - soft, cosHalf, (d[0] * dir[0] + d[1] * dir[1] + d[2] * dir[2]) / n);
}
/* fragment alpha for the two styles: lens = only inside the cone; all = uniform semi-transparent services */
function fragmentAlpha(mode, opacity, weight) { return mode === 'all' ? opacity : opacity * weight; }
const OPACITY_STEPS = [0.15, 0.3, 0.45, 0.6, 0.75, 0.85, 1];
function stepOpacity(value, delta) {
  let i = 0;
  OPACITY_STEPS.forEach((v, k) => { if (Math.abs(v - value) < Math.abs(OPACITY_STEPS[i] - value)) i = k; });
  return OPACITY_STEPS[Math.max(0, Math.min(OPACITY_STEPS.length - 1, i + Math.sign(delta)))];
}
function stepCone(deg, delta) { return Math.max(4, Math.min(30, Math.round(deg + 2 * Math.sign(delta)))); }

/* ── Station navigation ── chooseNeighbor is scan-photo.html chooseWalkNeighbor (tests compare both on the real manifests):
   neighbours only (no off-route shortcuts), <= 5.5 m, <= 1.5 m height change, alignment >= 0.25 with the XZ direction. */
function chooseNeighbor(nodes, index, direction) {
  let best = -1, score = -Infinity;
  for (const i of nodes[index]?.neighbors || []) {
    const a = nodes[index].position, b = nodes[i].position, dx = b[0] - a[0], dz = b[2] - a[2], d = Math.hypot(dx, dz), length = Math.hypot(dx, b[1] - a[1], dz);
    if (d < .1 || length > 5.5 || Math.abs(b[1] - a[1]) > 1.5) continue;
    const alignment = (dx * direction[0] + dz * direction[2]) / d;
    if (alignment < .25) continue;
    const rank = alignment - .04 * d;
    if (rank > score) { score = rank; best = i; }
  }
  return best;
}
/* Thumbstick with hysteresis: one action per push. Press beyond 0.7, re-arm below 0.3. Quest xr-standard: axes[2]=x, axes[3]=y (forward = -y). */
function stickStep(state, x, y, {press = .7, release = .3} = {}) {
  const ax = Math.abs(x || 0), ay = Math.abs(y || 0);
  if (state.armed === false) { if (Math.max(ax, ay) < release) state.armed = true; return null; }
  if (Math.max(ax, ay) < press) return null;
  state.armed = false;
  if (ay >= ax) return y < 0 ? 'forward' : 'back';
  return x < 0 ? 'turn-left' : 'turn-right';
}
/* Snap turn about the head: rotate the rig by angle about +Y through the head's world XZ position. */
function snapTurn(rigPosition, rigYaw, headWorld, angle) {
  const c = Math.cos(angle), s = Math.sin(angle), dx = rigPosition[0] - headWorld[0], dz = rigPosition[2] - headWorld[2];
  return {position: [headWorld[0] + c * dx + s * dz, rigPosition[1], headWorld[2] - s * dx + c * dz], yaw: rigYaw + angle};
}
/* Rig placement that puts the tracked head (rig-local headLocal) exactly at the station: rig = station - R_y(yaw) headLocal. */
function rigForStation(station, rigYaw, headLocal) {
  const c = Math.cos(rigYaw), s = Math.sin(rigYaw), h = headLocal;
  return [station[0] - (c * h[0] + s * h[2]), station[1] - h[1], station[2] - (-s * h[0] + c * h[2])];
}

/* ── Spatial visibility ── a batch is shown when its bounding sphere comes within radius of the station (BIM frame). */
function withinRadius(center, sphereCenter, sphereRadius, radius) {
  return Math.hypot(sphereCenter[0] - center[0], sphereCenter[1] - center[1], sphereCenter[2] - center[2]) - Math.max(0, sphereRadius) <= radius;
}
function cellKey(x, z, size) { return Math.floor(x / size) + ',' + Math.floor(z / size); }

/* ── XR menu panel ── canvas fractions (y down). Buttons are a 5x2 grid in the lower part of the panel. */
const MENU = {cols: 5, rows: 2, left: .025, right: .975, top: .56, bottom: .965, gap: .012};
function menuRect(i) {
  const w = (MENU.right - MENU.left - MENU.gap * (MENU.cols - 1)) / MENU.cols, h = (MENU.bottom - MENU.top - MENU.gap * (MENU.rows - 1)) / MENU.rows;
  const c = i % MENU.cols, r = Math.floor(i / MENU.cols);
  return {x: MENU.left + c * (w + MENU.gap), y: MENU.top + r * (h + MENU.gap), w, h};
}
/* (u, v) are plane UVs (v up, Three.js PlaneGeometry convention). Returns button index or -1. */
function menuHit(u, v) {
  const x = u, y = 1 - v;
  for (let i = 0; i < MENU.cols * MENU.rows; i++) { const r = menuRect(i); if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) return i; }
  return -1;
}

/* ── Info card text ── tier comes from ElementCards.elementFeedTier (same honesty ladder as the web overlay).
   CONTEXT is a building/feeder meter total, never the element's own reading; NO FEED stays "No feed yet". */
function clip(s, n) { s = String(s ?? ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
function cardLines(id, meta, tier, capture) {
  const title = clip(meta?.name || meta?.type || 'Element', 44);
  const sub = [meta?.type, meta?.system, meta?.level].filter(Boolean).join(' · ');
  const rows = [tier.valueText, tier.detailText, tier.sourceText].filter(Boolean).map(s => clip(s, 70));
  if (tier.tier === 'CONTEXT' && !rows.some(r => /not this element/i.test(r))) rows.push('Building meter total · not this element’s own reading');
  // The alignment caveat is never truncated (the page shrinks the font to fit instead).
  const footer = [
    (capture?.label ? capture.label + ' · ' : '') + (capture?.alignmentText || ''),
    clip('Design (BIM) position · ' + (meta?.layer ? meta.layer + ' · ' : '') + 'id ' + id, 80),
  ];
  return {title, sub: clip(sub, 70), badge: tier.label, tier: tier.tier, cls: tier.cls, rows, footer};
}

return {CAPTURES, DEFAULT_CAPTURE, captureConfig, validRegistration, applyReg, invertReg, bimRootTransform, applyRootTransform,
  quatMul, stationQuaternion, rotateByQuat, coneCos, smoothstep, coneWeight, fragmentAlpha, OPACITY_STEPS, stepOpacity, stepCone,
  chooseNeighbor, stickStep, snapTurn, rigForStation, withinRadius, cellKey, MENU, menuRect, menuHit, cardLines};
});
