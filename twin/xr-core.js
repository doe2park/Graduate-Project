/* twin/xr-core.js — pure helpers for scan-xr.html (Quest WebXR Scan<->BIM overlay). No DOM, no network, no Three.js.
   Works as a browser global (window.ScanXRCore) and as CommonJS (tests/scan-xr-core.test.cjs).

   Frames (same as scan-photo.html / scan-compare.html):
   - Stations, the photo sphere and the viewer live in the capture's SCAN frame (E57, Y-up metres).
   - BIM element layers live in the BIM viewer world. The accepted rigid registration maps scan -> BIM:
       p_bim = R_y(theta) p_scan + t        (registration-core.js apply())
     scan-compare converts the photo camera into the BIM frame with exactly this map. scan-xr instead keeps the
     viewer in the scan frame and places the BIM under one group carrying the INVERSE map; the relative geometry
     between eye, photo pixels and BIM services is identical (tests check this against registration-core.js).
   Honesty: May 6 = accepted registration (internal residual, not surveyed); Sep 17 / Oct 18 = provisional alignment. */
(function (root, factory) {
  const api = factory();
  if (root) root.ScanXRCore = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';
const D2R = Math.PI / 180;

/* ── Captures ── default May 6 (accepted registration); Sep 17 and Oct 18 are selectable and always labelled provisional. */
const CAPTURES = {
  '2026-05-06': {date: '2026-05-06', label: 'May 6, 2026', provisional: false,
    photo: 'scan-assets/panoramas/manifest.json', registration: 'alignment-analysis/accepted-registration.json',
    alignmentText: 'registered (internal residual ≈0.13 m, not surveyed)'},
  '2026-09-17': {date: '2026-09-17', label: 'Sep 17, 2026', provisional: true,
    photo: 'scan-assets/captures/2026-09-17/panoramas/manifest.json', registration: 'scan-assets/captures/2026-09-17/registration.json',
    alignmentText: 'PROVISIONAL alignment (not surveyed)'},
  '2026-10-18': {date: '2026-10-18', label: 'Oct 18, 2026', provisional: true,
    photo: 'scan-assets/captures/2026-10-18/panoramas/manifest.json', registration: 'scan-assets/captures/2026-10-18/registration.json',
    alignmentText: 'PROVISIONAL alignment (not surveyed)'},
};
const DEFAULT_CAPTURE = '2026-05-06';
/* Menu order: May 6 → Sep 17 → Oct 18 → May 6. */
const CAPTURE_ORDER = ['2026-05-06', '2026-09-17', '2026-10-18'];
function captureConfig(date) {
  const c = CAPTURES[Object.prototype.hasOwnProperty.call(CAPTURES, date) ? date : DEFAULT_CAPTURE];
  return {...c};
}
function nextCapture(date) {
  const i = CAPTURE_ORDER.indexOf(date);
  return CAPTURE_ORDER[(i + 1) % CAPTURE_ORDER.length];
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

/* ── XR menu panel ── canvas fractions (y down). Buttons are a 6x2 grid in the lower part of the panel (12 buttons since the Gaussian scene toggle). */
const MENU = {cols: 6, rows: 2, left: .025, right: .975, top: .6, bottom: .965, gap: .012};
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

/* ── Gaussian scene mode (2026-10-19) ──
   The splat scene lives in the capture's SCAN frame (manifest frame 'scan-y-up-metres'), exactly like the photo stations,
   so it is added to the scene root untransformed and the BIM keeps the same inverse-registration group.
   Gaussian = trained appearance, not surveyed geometry. Only the May 6 scene is published. */
const PUBLISHED_GAUSSIANS = {'2026-05-06': 'scan-assets/gaussian/2026-05-06/viewer.json'};
const SCENES = ['photo', 'gaussian'];
function sceneRequest(value) { return value === 'gaussian' ? 'gaussian' : 'photo'; }
/* Dev hosts that may preview unpublished local packages: loopback and private RFC1918 IPv4 (the Quest dev server binds one). */
function isDevHost(hostname) {
  const h = String(hostname || '').toLowerCase().replace(/^\[|\]$/g, '');
  if (h === 'localhost' || h === '127.0.0.1' || h === '::1' || h.endsWith('.localhost')) return true;
  const m = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!m) return false;
  const o = m.slice(1).map(Number);
  if (o.some(v => v > 255)) return false;
  return o[0] === 10 || (o[0] === 172 && o[1] >= 16 && o[1] <= 31) || (o[0] === 192 && o[1] === 168);
}
/* ?gaussian=<manifest path>: honoured only on dev hosts; a relative same-origin .json path, no traversal, no dot-segments. */
function gaussianOverride(hostname, value) {
  if (!isDevHost(hostname) || typeof value !== 'string' || value.length > 300) return null;
  if (!/^[\w.\/-]+\.json$/.test(value) || value.startsWith('/') || value.includes('//') || value.includes('..')) return null;
  if (value.split('/').some(s => !s || s.startsWith('.'))) return null;
  return value;
}
const SPLAT_BUDGET = {mobile: 1000000, full: 3000000};
/* Manifest check (same rules as scan-splat.html readManifest) + file choice: XR uses mobileFile unless forced 'full'. */
function gaussianAsset(m, {xr = false, prefer = null} = {}) {
  if (!m || typeof m !== 'object') return {ok: false, error: 'Gaussian manifest unreadable'};
  if (m.frame !== 'scan-y-up-metres') return {ok: false, error: 'Unsupported Gaussian frame · expected scan-y-up-metres'};
  if (m.status !== 'experimental-trained') return {ok: false, error: 'Gaussian manifest is not an experimental-trained scene'};
  if (typeof m.capture !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(m.capture)) return {ok: false, error: 'Gaussian manifest has no capture date'};
  const useMobile = prefer === 'mobile' ? !!m.mobileFile : prefer === 'full' ? false : xr && !!m.mobileFile;
  const file = useMobile ? m.mobileFile : m.file, count = useMobile ? m.mobileSplatCount : m.splatCount;
  if (typeof file !== 'string' || !/^[\w.-]+\.(ply|ksplat)$/i.test(file) || file.startsWith('.')) return {ok: false, error: 'Gaussian asset must be a sibling .ply or .ksplat file'};
  if (!Number.isSafeInteger(count) || count < 1) return {ok: false, error: 'Gaussian manifest needs a positive splat count'};
  const budget = xr || useMobile ? SPLAT_BUDGET.mobile : SPLAT_BUDGET.full;
  if (count > budget) return {ok: false, error: 'Gaussian scene exceeds the ' + (xr ? 'headset' : 'device') + ' splat budget'};
  return {ok: true, file, count, mobile: useMobile, shDegree: xr || useMobile ? 0 : 2};
}
/* Which Gaussian (if any) belongs to this capture: the published one, or a validated local override for the same capture date. */
function gaussianFor(captureDate, override) {
  if (override && override.capture === captureDate) return {path: override.path, local: true};
  if (Object.prototype.hasOwnProperty.call(PUBLISHED_GAUSSIANS, captureDate)) return {path: PUBLISHED_GAUSSIANS[captureDate], local: false};
  return null;
}
/* Toggle logic: a request for 'gaussian' without a scene for this capture stays in Photo and explains why. */
function resolveScene(requested, captureLabel, source) {
  if (sceneRequest(requested) !== 'gaussian') return {scene: 'photo', note: null};
  if (!source) return {scene: 'photo', note: 'No Gaussian scene for ' + (captureLabel || 'this capture') + ' · staying in Photo (published Gaussian: May 6 only)'};
  return {scene: 'gaussian', note: null};
}
function toggleScene(current) { return current === 'gaussian' ? 'photo' : 'gaussian'; }
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function dateLabel(iso) { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || '')); return m ? MONTHS[Number(m[2]) - 1] + ' ' + Number(m[3]) + ', ' + m[1] : String(iso || ''); }
/* Honest caption: capture date, zone, 'experimental appearance, not surveyed', provisional alignment where it applies, local preview. */
function gaussianLabel(m, capture, {local = false} = {}) {
  const zone = m?.zone && typeof m.zone.id === 'string' ? 'zone ' + m.zone.id + (m.zone.name ? ' (' + m.zone.name + ')' : '') : 'whole capture';
  const parts = ['Gaussian · ' + dateLabel(m?.capture), zone, 'experimental appearance, not surveyed'];
  if (capture?.provisional) parts.push('provisional alignment');
  if (local) parts.push('local preview, unpublished');
  return parts.join(' · ');
}
/* Stations in a zoned Gaussian: the trained stations, else every station. */
function gaussianStations(m, stations) {
  const ids = Array.isArray(m?.zone?.stations) ? new Set(m.zone.stations) : null;
  return stations.map((s, i) => i).filter(i => !ids || ids.has(stations[i].id));
}

/* ── Point-and-teleport (Gaussian mode only; a photo has one optical centre) ──
   The floor is an invisible horizontal plane `eyeHeight` below the current view height (assumed capture-camera height,
   not measured). Landing keeps the current eye height. The target must be within maxDistance of the eye, within
   stationRadius of a recorded station (trained coverage proxy) and, for a zoned scene, inside the zone bounds (XZ). */
function floorHit(origin, dir, floorY, maxDistance = 8) {
  const dy = dir[1];
  if (!(dy < -1e-4) || !Number.isFinite(floorY)) return null;
  const t = (floorY - origin[1]) / dy;
  if (!(t > 0)) return null;
  const p = [origin[0] + dir[0] * t, floorY, origin[2] + dir[2] * t];
  return Math.hypot(p[0] - origin[0], p[2] - origin[2]) <= maxDistance ? p : null;
}
function nearestStation(stations, p, indices = null) {
  let best = -1, bd = Infinity;
  for (const i of indices || stations.map((_, k) => k)) { const s = stations[i].position, d = Math.hypot(s[0] - p[0], s[2] - p[2]); if (d < bd) { bd = d; best = i; } }
  return {index: best, distance: bd};
}
function teleportTarget(origin, dir, {viewY, eyeHeight = 1.5, maxDistance = 8, stations = [], indices = null, stationRadius = 6, bounds = null, boundsPad = 0} = {}) {
  const floorY = viewY - eyeHeight, hit = floorHit(origin, dir, floorY, maxDistance);
  if (!hit) return {ok: false, reason: 'Point at the floor within ' + maxDistance + ' m'};
  if (bounds && Array.isArray(bounds.min) && Array.isArray(bounds.max)
      && (hit[0] < bounds.min[0] - boundsPad || hit[0] > bounds.max[0] + boundsPad || hit[2] < bounds.min[2] - boundsPad || hit[2] > bounds.max[2] + boundsPad)) return {ok: false, point: hit, reason: 'Outside the trained Gaussian zone'};
  const near = nearestStation(stations, hit, indices);
  if (near.index < 0 || near.distance > stationRadius) return {ok: false, point: hit, reason: 'More than ' + stationRadius + ' m from any captured position'};
  return {ok: true, point: hit, landing: [hit[0], viewY, hit[2]], nearest: near.index};
}

return {CAPTURES, DEFAULT_CAPTURE, CAPTURE_ORDER, captureConfig, nextCapture, validRegistration, applyReg, invertReg, bimRootTransform, applyRootTransform,
  quatMul, stationQuaternion, rotateByQuat, coneCos, smoothstep, coneWeight, fragmentAlpha, OPACITY_STEPS, stepOpacity, stepCone,
  chooseNeighbor, stickStep, snapTurn, rigForStation, withinRadius, cellKey, MENU, menuRect, menuHit, cardLines,
  PUBLISHED_GAUSSIANS, SCENES, sceneRequest, isDevHost, gaussianOverride, SPLAT_BUDGET, gaussianAsset, gaussianFor, resolveScene, toggleScene,
  dateLabel, gaussianLabel, gaussianStations, floorHit, nearestStation, teleportTarget};
});
