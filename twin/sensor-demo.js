/* Virtual-sensor DEMO layer (opt-in: scan-compare.html?...&sensors=demo). ILLUSTRATIVE ONLY: no sensor is installed in
   Grimes and every reading comes from twin/sensor-demo.json, a hand-written concept file. Each sensor is anchored to a
   real BIM element (layer sidecar id + source_guid) so it stays on that pipe/duct while the camera moves.

   Split of work (same-origin postMessage, like the Lens pick contract in twin/element-cards.js):
   - BIM pane (scan-bim.html?pane=bim&sensors=demo) — mountBim(): resolves anchors against the loaded element layers
     (identity check: sidecar name must match the config), recolours a DTS-anchored element with a temperature gradient
     (a render-only copy of its triangles; source GLBs, batches and the triangle-range map are never changed) and, after
     each render, posts the anchors projected to its canvas plus a Range / wall-occlusion visibility factor.
   - Compare page (scan-compare.html?...&sensors=demo) — mountParent(): draws pins, the fibre line, alert pulses, links
     and zone tints in a DOM layer over the BIM frame (not inside the Lens mask, so they stay readable), the persistent
     "Demo sensors — illustrative, not installed" badge and an info card in the Lens-card style.
   Without ?sensors=demo neither page loads this file or its JSON (no request, no DOM, no render change).
   Pure helpers are exported for tests/sensor-demo.test.cjs. */
(function (root, factory) {
  const api = factory();
  if (root) root.SensorDemo = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';

const SCHEMA = 'grimes-sensor-demo/1', STATUS = 'illustrative-not-installed', CONFIG_URL = 'twin/sensor-demo.json';
const BADGE_TEXT = 'Demo sensors — illustrative, not installed';
const MSG = {state: 'grimes-sensor-demo-state', frame: 'grimes-sensor-demo-frame', focus: 'grimes-sensor-demo-focus'};
const TYPES = {
  dts: 'Fiber temperature (DTS)', alert: 'Alert rule', vibration: 'Vibration node', leak: 'Leak sensor', airflow: 'Airflow probe',
  iaq: 'CO2 / temperature / RH node', zone: 'Comfort tint', damper: 'BAS point', flow: 'Flow meter', ct: 'Current (CT) meter',
  rollup: 'Building meter link', bearing: 'Bearing temperature'};
const LAYERS = ['equipment', 'fixtures', 'lighting', 'lifesafety', 'structural', 'conduit', 'duct', 'hydronic', 'plumbing', 'fire'];
const finite = v => typeof v === 'number' && Number.isFinite(v);
const vec3 = v => Array.isArray(v) && v.length === 3 && v.every(finite);
const str = (v, n = 300) => typeof v === 'string' ? v.slice(0, n) : '';
const clamp01 = v => Math.min(1, Math.max(0, v));

/* ?scene=<scenario id> shows one scenario's sensors (its tint, fibre and links too); absent or unknown-format = all */
function parseSceneParam(search) {
  try { const v = new URLSearchParams(search || '').get('scene'); return v && /^[a-z0-9-]{1,30}$/.test(v) ? v : null; } catch (e) { return null; }
}
function parseFocusParam(search) {
  try { const v = new URLSearchParams(search || '').get('focus'); return v && /^[a-z0-9-]{1,40}$/.test(v) ? v : null; } catch (e) { return null; }
}
/* The sensor the Lens rests on: ?focus=<id> if it is in the scene, else the scene's configured primary, else none. */
function primaryFor(cfg, scene, focus, ids) {
  if (focus && ids.includes(focus)) return focus;
  const p = scene && cfg && cfg.primary ? cfg.primary[scene] : null;
  return p && ids.includes(p) ? p : null;
}
/* Where the locked Lens goes: the locked sensor's projected pin if it is in front of the camera (lensPoint then clamps it
   to the viewport, so an off-screen sensor keeps the Lens at the nearest edge); if it is behind the camera, the centroid
   of the sensors that are visible; otherwise null (the Lens stays where it is). proj: {id: [px, py, inFront]}. */
function lensAnchor(lockId, proj, visibleIds) {
  const p = lockId && proj[lockId];
  if (p && p[2]) return [p[0], p[1]];
  const v = (visibleIds || []).map(id => proj[id]).filter(q => q && q[2]);
  if (!v.length) return null;
  return [v.reduce((a, q) => a + q[0], 0) / v.length, v.reduce((a, q) => a + q[1], 0) / v.length];
}
function filterScene(sensors, scene) { return scene ? sensors.filter(s => s.scenario === scene) : sensors.slice(); }
function parseSensorsParam(search) {
  try { return new URLSearchParams(search || '').get('sensors') === 'demo' ? 'demo' : null; } catch (e) { return null; }
}

/* Only well-formed sensors survive; a bad entry is reported, never drawn. */
function validateConfig(cfg) {
  const errors = [], sensors = [], ids = new Set();
  if (!cfg || cfg.schema !== SCHEMA) return {ok: false, errors: ['schema must be ' + SCHEMA], sensors};
  if (cfg.status !== STATUS) return {ok: false, errors: ['status must be ' + STATUS], sensors};
  if (!Array.isArray(cfg.sensors)) return {ok: false, errors: ['sensors must be an array'], sensors};
  cfg.sensors.forEach((s, i) => {
    const where = 'sensor ' + i + (s && s.id ? ' (' + s.id + ')' : ''), a = s && s.anchor;
    const bad = m => errors.push(where + ': ' + m);
    if (!s || typeof s.id !== 'string' || !/^[a-z0-9-]{1,40}$/.test(s.id)) return bad('id must be a short lowercase slug');
    if (ids.has(s.id)) return bad('duplicate id');
    if (!TYPES[s.type]) return bad('unknown type ' + s.type);
    if (!str(s.label)) return bad('label missing');
    if (!s.reading || !str(s.reading.value)) return bad('reading.value missing');
    if (!a || !LAYERS.includes(a.layer) || typeof a.id !== 'string' || !/^\d+$/.test(a.id)) return bad('anchor needs a known layer and a numeric element id');
    if (a.t !== undefined && !(finite(a.t) && a.t >= 0 && a.t <= 1)) return bad('anchor.t must be 0..1');
    if (a.offset !== undefined && !(vec3(a.offset) && a.offset.every(v => Math.abs(v) <= 3))) return bad('anchor.offset must be 3 numbers within 3 m');
    if (s.color !== undefined && !/^#[0-9a-fA-F]{6}$/.test(s.color)) return bad('color must be #rrggbb');
    if (a.part !== undefined && !(typeof a.part === 'string' && /^grimes-[a-z0-9-]+\.glb$/.test(a.part))) return bad('anchor.part must be a grimes-*.glb chunk file name');
    if (s.type === 'dts') {
      const d = s.dts;
      if (!d || ![d.baselineC, d.peakC, d.hotT, d.hotWidth].every(finite) || !Array.isArray(d.scaleC) || d.scaleC.length !== 2 || !d.scaleC.every(finite) || d.scaleC[1] <= d.scaleC[0] || d.hotWidth <= 0) return bad('dts needs baselineC, peakC, hotT, hotWidth and scaleC [lo, hi]');
    }
    if (s.type === 'zone' && !(s.zone && finite(s.zone.radiusM) && s.zone.radiusM > 0 && s.zone.radiusM <= 5)) return bad('zone.radiusM must be 0..5 m');
    if (cfg.primary !== undefined && (typeof cfg.primary !== 'object' || !cfg.primary)) return bad('primary must map scenario -> sensor id');
    if (s.links !== undefined && !(Array.isArray(s.links) && s.links.every(x => typeof x === 'string'))) return bad('links must be sensor ids');
    if (s.reading.series !== undefined && !(Array.isArray(s.reading.series) && s.reading.series.length >= 2 && s.reading.series.every(finite))) return bad('reading.series must be numbers');
    ids.add(s.id); sensors.push(s);
  });
  for (const s of sensors) for (const l of s.links || []) if (!ids.has(l)) errors.push(s.id + ': link to unknown sensor ' + l);
  for (const [sc, id] of Object.entries(cfg.primary || {})) { const s = sensors.find(x => x.id === id); if (!s || s.scenario !== sc) errors.push('primary.' + sc + ': ' + id + ' is not a sensor of that scenario'); }
  if (cfg.types !== undefined) for (const [k, t] of Object.entries(cfg.types)) {
    if (!TYPES[k]) errors.push('types.' + k + ': unknown type');
    else if (!t || !str(t.short, 30) || !/^#[0-9a-fA-F]{6}$/.test(t.color || '') || !/^[MmLlHhVvCcSsQqTtAaZz0-9 .,\-]+$/.test(t.icon || '')) errors.push('types.' + k + ': needs short, #rrggbb color and an SVG path icon');
  }
  return {ok: errors.length === 0, errors, sensors};
}

/* ── temperature colour map (same stops as the concept deck): cool blue -> normal cyan -> warm yellow -> hot red ── */
const STOPS = [[0, [30, 80, 220]], [0.33, [0, 190, 230]], [0.6, [250, 215, 40]], [1, [230, 30, 30]]];
function colorAt(v) {
  v = clamp01(finite(v) ? v : 0);
  for (let i = 0; i < STOPS.length - 1; i++) {
    const [a, ca] = STOPS[i], [b, cb] = STOPS[i + 1];
    if (v <= b) { const f = (v - a) / (b - a); return ca.map((c, j) => Math.round(c + f * (cb[j] - c))); }
  }
  return STOPS[STOPS.length - 1][1].slice();
}
const cssColor = rgb => 'rgb(' + rgb.join(',') + ')';
/* illustrative temperature along the element: baseline (+ optional linear slopeC over the length) + a Gaussian warm spot
   at hotT, plus a small fixed ripple */
function dtsTempC(t, d) {
  const u = clamp01(t), w = d.hotWidth;
  return d.baselineC + (finite(d.slopeC) ? d.slopeC * (u - 0.5) : 0) + (d.peakC - d.baselineC) * Math.exp(-Math.pow((u - d.hotT) / w, 2)) + 0.35 * Math.sin(u * 23);
}
function dtsValue(t, d) { return clamp01((dtsTempC(t, d) - d.scaleC[0]) / (d.scaleC[1] - d.scaleC[0])); }

/* ── element geometry: principal axis of its vertices (pipes/ducts are long and thin) ── */
function principalAxis(pos, stride) {
  stride = stride || 3; const n = Math.floor(pos.length / stride);
  if (!n) return null;
  let cx = 0, cy = 0, cz = 0;
  for (let i = 0; i < n; i++) { cx += pos[i * stride]; cy += pos[i * stride + 1]; cz += pos[i * stride + 2]; }
  cx /= n; cy /= n; cz /= n;
  let xx = 0, xy = 0, xz = 0, yy = 0, yz = 0, zz = 0;
  for (let i = 0; i < n; i++) {
    const x = pos[i * stride] - cx, y = pos[i * stride + 1] - cy, z = pos[i * stride + 2] - cz;
    xx += x * x; xy += x * y; xz += x * z; yy += y * y; yz += y * z; zz += z * z;
  }
  /* power iteration from the longest bounding-box direction (deterministic, robust for a near-isotropic blob) */
  let v = [1, 0, 0];
  { let mn = [Infinity, Infinity, Infinity], mx = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < n; i++) for (let k = 0; k < 3; k++) { const p = pos[i * stride + k]; if (p < mn[k]) mn[k] = p; if (p > mx[k]) mx[k] = p; }
    const ext = [0, 1, 2].map(k => mx[k] - mn[k]), k = ext.indexOf(Math.max(...ext)); v = [0, 0, 0]; v[k] = 1; v[(k + 1) % 3] = 1e-3; }
  for (let it = 0; it < 64; it++) {
    const w = [xx * v[0] + xy * v[1] + xz * v[2], xy * v[0] + yy * v[1] + yz * v[2], xz * v[0] + yz * v[1] + zz * v[2]];
    const l = Math.hypot(...w); if (!(l > 1e-12)) break; v = w.map(c => c / l);
  }
  /* canonical sign: +x, else +z, else +y — so t=0..1 runs the same way on every load */
  if (v[0] < -1e-9 || (Math.abs(v[0]) <= 1e-9 && (v[2] < -1e-9 || (Math.abs(v[2]) <= 1e-9 && v[1] < 0)))) v = v.map(c => -c || 0);
  let tMin = Infinity, tMax = -Infinity;
  for (let i = 0; i < n; i++) {
    const d = (pos[i * stride] - cx) * v[0] + (pos[i * stride + 1] - cy) * v[1] + (pos[i * stride + 2] - cz) * v[2];
    if (d < tMin) tMin = d; if (d > tMax) tMax = d;
  }
  return {center: [cx, cy, cz], dir: v, tMin, tMax, length: tMax - tMin};
}
function axisParam(p, ax) {
  const d = (p[0] - ax.center[0]) * ax.dir[0] + (p[1] - ax.center[1]) * ax.dir[1] + (p[2] - ax.center[2]) * ax.dir[2];
  return ax.length > 1e-9 ? clamp01((d - ax.tMin) / ax.length) : 0.5;
}
function axisPoint(ax, t) {
  const d = ax.tMin + clamp01(t) * ax.length;
  return [0, 1, 2].map(k => ax.center[k] + ax.dir[k] * d);
}
function anchorPoint(ax, anchor) {
  const p = axisPoint(ax, anchor && finite(anchor.t) ? anchor.t : 0.5), o = anchor && vec3(anchor.offset) ? anchor.offset : [0, 0, 0];
  return [p[0] + o[0], p[1] + o[1], p[2] + o[2]];
}
/* a horizontal circle (zone tint) around a point */
function zoneRing(c, r, n) { n = n || 28; const out = []; for (let i = 0; i < n; i++) { const a = i / n * 2 * Math.PI; out.push([c[0] + r * Math.cos(a), c[1], c[2] + r * Math.sin(a)]); } return out; }

/* ── per-type look: icon (24x24 stroke path), colour and short chip label, from cfg.types ── */
const FALLBACK_TYPE = {short: 'Sensor', color: '#087F8C', icon: 'M12 4a8 8 0 1 0 .01 0'};
function typeStyle(cfg, type) { const t = cfg && cfg.types && cfg.types[type]; return t ? t : {...FALLBACK_TYPE, short: TYPES[type] || 'Sensor'}; }
function iconSvg(path, size, stroke) {
  return '<svg class="sd-ico" viewBox="0 0 24 24" width="' + (size || 16) + '" height="' + (size || 16) + '" aria-hidden="true"><path d="' + esc(path) + '" fill="none" stroke="' + esc(stroke || '#fff') + '" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
}
/* Project a BIM-world point with a linked camera pose {position, quaternion [x,y,z,w], fov (vertical deg), zoom} and the
   canvas aspect, exactly like THREE.PerspectiveCamera: -> [x 0..1, y 0..1 (down), inFront 0|1]. Lets the compare page place
   pins from the pose it has just forwarded, in the same frame, instead of waiting for the BIM pane to render and reply. */
function projectPoint(p, pose, aspect) {
  const [px, py, pz] = pose.position, [qx, qy, qz, qw] = pose.quaternion;
  const vx = p[0] - px, vy = p[1] - py, vz = p[2] - pz;
  /* rotate by the conjugate quaternion (world -> camera) */
  const cx = -qx, cy = -qy, cz = -qz, tx = 2 * (cy * vz - cz * vy), ty = 2 * (cz * vx - cx * vz), tz = 2 * (cx * vy - cy * vx);
  const rx = vx + qw * tx + (cy * tz - cz * ty), ry = vy + qw * ty + (cz * tx - cx * tz), rz = vz + qw * tz + (cx * ty - cy * tx);
  const f = Math.tan((pose.fov || 60) * Math.PI / 360) / (pose.zoom || 1), d = -rz;
  if (!(d > 1e-6)) return [0.5, 0.5, 0];
  return [+((rx / d / (f * aspect) + 1) / 2).toFixed(4), +((1 - ry / d / f) / 2).toFixed(4), d > 0.05 ? 1 : 0];
}
/* Lens centre for a sensor: its pin position (main-element px) as the normalised pointer the Lens uses, clamped so the
   ring centre stays inside the viewport with a margin. */
function lensPoint(p, w, h, margin) {
  if (!p || !(w > 0) || !(h > 0) || !finite(p[0]) || !finite(p[1])) return null;
  const m = Math.max(0, margin || 0), cx = Math.min(w - m, Math.max(m, p[0])), cy = Math.min(h - m, Math.max(m, p[1]));
  return {x: m * 2 >= w ? 0.5 : cx / w, y: m * 2 >= h ? 0.5 : cy / h};
}
/* Greedy label placement: each chip tries right, left, above, below its pin (then further out) and takes the first spot
   that overlaps no pin and no chip already placed and stays inside the box. Returns [{id, x, y}] (chip top-left). */
function placeChips(items, box, pinR) {
  const r = pinR || 14, placed = [], pins = items.map(it => ({x: it.x - r, y: it.y - r, w: 2 * r, h: 2 * r}));
  const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  const out = [];
  for (const it of items) {
    const w = it.w, h = it.h, gap = r + 4;
    const cands = [];
    for (const k of [0, 1, 2]) {
      const d = k * (h + 4);
      cands.push([it.x + gap, it.y - h / 2 + d], [it.x - gap - w, it.y - h / 2 + d], [it.x - w / 2, it.y - gap - h - d], [it.x - w / 2, it.y + gap + d], [it.x + gap, it.y - h / 2 - d], [it.x - gap - w, it.y - h / 2 - d]);
    }
    let best = null;
    for (const [x, y] of cands) {
      const c = {x, y, w, h};
      if (x < box.x || y < box.y || x + w > box.x + box.w || y + h > box.y + box.h) continue;
      if (pins.some(p => hit(c, p)) || placed.some(p => hit(c, p))) continue;
      best = c; break;
    }
    if (!best) best = {x: Math.min(box.x + box.w - w, Math.max(box.x, it.x + gap)), y: Math.min(box.y + box.h - h, Math.max(box.y, it.y - h / 2)), w, h};
    placed.push(best); out.push({id: it.id, x: best.x, y: best.y});
  }
  return out;
}

/* ── card (Lens-card look: gz-* classes) ── */
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]); }
function sparkSvg(series, color) {
  if (!Array.isArray(series) || series.length < 2) return '';
  const W = 220, H = 30, mx = Math.max(...series), mn = Math.min(...series), sp = (mx - mn) || 1;
  const pts = series.map((v, i) => [(i / (series.length - 1)) * W, H - 3 - ((v - mn) / sp) * (H - 6)]);
  const line = pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' '), last = pts[pts.length - 1];
  return '<div class="gz-spark"><svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" aria-hidden="true"><polyline points="' + line + '" fill="none" stroke="' + esc(color) + '" stroke-width="1.8"/>'
    + '<circle cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) + '" r="2.6" fill="' + esc(color) + '"/></svg></div>';
}
function elementLabel(el) {
  if (!el) return '';
  const name = String(el.name || el.type || 'Element');
  return name.length > 46 ? name.slice(0, 45) + '…' : name;
}
function cardHtml(s, el, style) {
  const color = /^#[0-9a-fA-F]{6}$/.test(s.color || '') ? s.color : '#22d3ee';
  const sub = [TYPES[s.type], s.kind].filter(Boolean).join(' · ');
  const elSub = el ? [el.type, el.system, el.level].filter(Boolean).join(' · ') : '';
  const where = s.anchor.layer + ':' + s.anchor.id;
  let html = '<div class="gz-top"><span class="gz-name"><i class="sd-dot" style="background:' + color + '">' + (style ? iconSvg(style.icon, 12) : '') + '</i>' + (s.k ? esc(s.k) + ' · ' : '') + esc(s.label) + '</span><span class="gz-badge sd-demo">DEMO</span></div>'
    + (sub ? '<div class="gz-sub">' + esc(sub) + '</div>' : '')
    + '<div class="gz-val">' + esc(s.reading.value) + '</div>'
    + (s.reading.detail ? '<div class="gz-det">' + esc(s.reading.detail) + '</div>' : '');
  if (s.type === 'dts' && s.dts) {
    const g = STOPS.map(([v, c]) => cssColor(c) + ' ' + (v * 100) + '%').join(',');
    html += '<div class="sd-grad" style="background:linear-gradient(90deg,' + g + ')"></div><div class="sd-grad-cap"><span>' + esc(s.dts.scaleC[0]) + ' °C</span><span>colour scale on the pipe</span><span>' + esc(s.dts.scaleC[1]) + ' °C</span></div>';
  }
  html += sparkSvg(s.reading.series, color);
  html += '<div class="sd-map">Maps to BIM element: <b>' + esc(el ? elementLabel(el) : (s.anchor.name || where)) + '</b><br><span>' + esc([where, elSub].filter(Boolean).join(' · ')) + '</span></div>'
    + '<div class="sd-note">Illustrative value · no sensor installed</div>';
  return html;
}

/* ═══════════════ BIM pane runtime ═══════════════ */
function mountBim(ctx) {
  const THREE = ctx.THREE, post = ctx.post || (() => {}), sensors = [], resolved = new Map(), states = {};
  const _v = new THREE.Vector3(), _c = new THREE.Vector3(), _m = new THREE.Matrix4(), _n = new THREE.Matrix4();
  const group = new THREE.Group(); group.name = 'sensor-demo (illustrative)'; ctx.scene.add(group);
  let lastSig = '', visAt = 0, visCache = new Map(), config = null, failed = null;
  function sendState() { post({type: MSG.state, failed, sensors: sensors.map(s => ({id: s.id, ...(states[s.id] || {status: 'pending'})}))}); }
  /* this element's triangles (world space) from the runtime batches, without touching them */
  function elementGeometry(layerState, id) {
    const pos = [], idx = [];
    for (const mesh of layerState.meshes || []) {
      const ids = mesh.userData && mesh.userData.ids; if (!Array.isArray(ids) || !ids.includes(id)) continue;
      const line = !!(mesh.isLine || mesh.isLineSegments);   // CAD polylines: positions anchor a point, no triangles to recolour
      mesh.updateWorldMatrix(true, false);
      const g = mesh.geometry, P = g.attributes.position; if (!P) continue;
      const pushTris = (indexAt, vStart, vCount, matrix) => {
        const base = pos.length / 3;
        for (let v = 0; v < vCount; v++) { _v.fromBufferAttribute(P, vStart + v).applyMatrix4(matrix); pos.push(_v.x, _v.y, _v.z); }
        if (!line) for (const i of indexAt) idx.push(base + i);
      };
      if (mesh.isInstancedMesh) {
        const n = P.count, local = g.index ? Array.from(g.index.array) : Array.from({length: n}, (_, i) => i);
        ids.forEach((x, i) => { if (x !== id) return; mesh.getMatrixAt(i, _m); _n.multiplyMatrices(mesh.matrixWorld, _m); pushTris(local, 0, n, _n); });
      } else if (Array.isArray(mesh.userData.ranges)) {
        for (const r of mesh.userData.ranges) {
          if (r.id !== id) continue;
          const local = line ? [] : g.index ? Array.from(g.index.array.subarray(r.start, r.start + r.count), i => i - r.vertexStart) : Array.from({length: r.vertexCount}, (_, i) => i);
          pushTris(local, r.vertexStart, r.vertexCount, mesh.matrixWorld);
        }
      } else if (ids.length === 1) {
        pushTris(g.index ? Array.from(g.index.array) : Array.from({length: P.count}, (_, i) => i), 0, P.count, mesh.matrixWorld);
      }
    }
    return pos.length ? {pos: new Float32Array(pos), idx} : null;
  }
  /* DTS: recolour a render-only copy of the element with the temperature gradient, slightly inflated about its axis.
     Colour is looked up per fragment from the position along the element axis (CAD pipes often have vertices only at
     their two ends, so per-vertex colours would lose the warm spot). */
  function dtsLut(d) {
    const n = 128, data = new Uint8Array(n * 4);
    for (let i = 0; i < n; i++) { const c = colorAt(dtsValue(i / (n - 1), d)); data.set([c[0], c[1], c[2], 255], i * 4); }
    const tex = new THREE.DataTexture(data, n, 1, THREE.RGBAFormat); tex.magFilter = tex.minFilter = THREE.LinearFilter; tex.needsUpdate = true;
    return tex;
  }
  function dtsMesh(s, geo, ax) {
    const n = geo.pos.length / 3, out = new Float32Array(geo.pos.length);
    for (let i = 0; i < n; i++) {
      const p = [geo.pos[i * 3], geo.pos[i * 3 + 1], geo.pos[i * 3 + 2]], q = axisPoint(ax, axisParam(p, ax));
      for (let k = 0; k < 3; k++) out[i * 3 + k] = q[k] + (p[k] - q[k]) * 1.08;
    }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(out, 3)); g.setIndex(geo.idx);
    const m = new THREE.ShaderMaterial({
      uniforms: {lut: {value: dtsLut(s.dts)}, axC: {value: new THREE.Vector3(...ax.center)}, axD: {value: new THREE.Vector3(...ax.dir)}, axT0: {value: ax.tMin}, axLen: {value: Math.max(1e-6, ax.length)}, opacity: {value: 0.96}},
      vertexShader: 'varying vec3 vW;void main(){vec4 w=modelMatrix*vec4(position,1.0);vW=w.xyz;gl_Position=projectionMatrix*viewMatrix*w;}',
      fragmentShader: 'uniform sampler2D lut;uniform vec3 axC;uniform vec3 axD;uniform float axT0;uniform float axLen;uniform float opacity;varying vec3 vW;'
        + 'void main(){float t=clamp((dot(vW-axC,axD)-axT0)/axLen,0.0,1.0);gl_FragColor=vec4(texture2D(lut,vec2(t,0.5)).rgb,opacity);}',
      side: THREE.DoubleSide, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4, toneMapped: false});
    const mesh = new THREE.Mesh(g, m); mesh.name = 'sensor-demo dts ' + s.id; mesh.renderOrder = 20; mesh.userData.sensorDemo = s.id;
    return mesh;
  }
  function tryResolve() {
    let changed = false;
    for (const s of sensors) {
      if (resolved.has(s.id) || (states[s.id] && states[s.id].status === 'refused')) continue;
      let st = ctx.getLayer(s.anchor.layer);
      if ((!st || !st.group || !st.meshes) && subsets[s.anchor.layer] && subsets[s.anchor.layer].st) st = subsets[s.anchor.layer].st;
      if (!st || !st.group || !st.meshes) { requestSubset(s.anchor.layer); if (!states[s.id] || states[s.id].reason !== layerReason(s.anchor.layer)) { states[s.id] = {status: 'pending', reason: layerReason(s.anchor.layer)}; changed = true; } continue; }
      const info = (st.meta && st.meta[s.anchor.id]) || ctx.elementInfo(s.anchor.layer, s.anchor.id);
      if (!info) { states[s.id] = {status: 'refused', reason: 'element ' + s.anchor.id + ' not in the ' + s.anchor.layer + ' sidecar'}; changed = true; continue; }
      if (s.anchor.name && info.name !== s.anchor.name) { states[s.id] = {status: 'refused', reason: 'sidecar name differs from the config anchor'}; changed = true; continue; }
      if (s.anchor.guid && info.source_guid && info.source_guid !== s.anchor.guid) { states[s.id] = {status: 'refused', reason: 'source_guid differs from the config anchor'}; changed = true; continue; }
      const geo = elementGeometry(st, s.anchor.id);
      if (!geo) { states[s.id] = {status: 'refused', reason: 'no geometry for element ' + s.anchor.id}; changed = true; continue; }
      const ax = principalAxis(geo.pos), rec = {s, st, ax, point: anchorPoint(ax, s.anchor), mesh: null};
      if (s.type === 'dts') { if (geo.idx.length) { rec.mesh = dtsMesh(s, geo, ax); group.add(rec.mesh); } rec.samples = Array.from({length: 33}, (_, i) => ({t: i / 32, p: axisPoint(ax, i / 32)})); }
      if (s.type === 'zone') { rec.ring = zoneRing(rec.point, s.zone.radiusM); rec.point = rec.ring[0]; }   // pin on the tint's edge, not on the node at its centre
      resolved.set(s.id, rec);
      const r3 = v => v.map(c => +c.toFixed(4));
      rec.world = {p: r3(rec.point), fibre: rec.samples ? rec.samples.map(q => [...r3(q.p), +q.t.toFixed(3)]) : null, ring: rec.ring ? rec.ring.map(r3) : null};
      states[s.id] = {world: rec.world, status: 'attached', element: {name: str(info.name, 200), type: str(info.type, 80), system: str(info.system, 80), level: str(info.level, 40), guid: str(info.source_guid, 60), layer: s.anchor.layer, id: s.anchor.id}, lengthM: +ax.length.toFixed(2)};
      changed = true;
    }
    if (changed) { lastSig = ''; sendState(); if (ctx.kick) ctx.kick(); }
  }
  /* A layer the Overlay skips on this device (fire on phones / coarse-pointer browsers such as Quest): load only the
     anchored elements, from the chunk(s) named by anchor.part, as a separate render-only group (never layerState). */
  const subsets = {};
  function layerReason(layer) { const sb = subsets[layer]; return sb ? (sb.error ? layer + ' anchors failed to load: ' + sb.error : sb.st ? layer + ' anchors loaded' : 'loading only the anchored ' + layer + ' elements') : layer + ' layer not loaded'; }
  function requestSubset(layer) {
    if (subsets[layer] || !ctx.skipped || !ctx.skipped(layer) || !ctx.loadSubset) return;
    const mine = sensors.filter(x => x.anchor.layer === layer), ids = [...new Set(mine.map(x => x.anchor.id))], parts = [...new Set(mine.map(x => x.anchor.part).filter(Boolean))];
    if (!parts.length) { subsets[layer] = {error: 'no anchor.part chunk named for this device'}; return; }
    const sb = subsets[layer] = {ids, parts, st: null, error: null};
    Promise.resolve(ctx.loadSubset(layer, ids, parts)).then(st => { sb.st = st; tryResolve(); }).catch(e => { sb.error = String(e && e.message || e); lastSig = ''; sendState(); });
  }
  function project(p) {
    _v.set(p[0], p[1], p[2]); _c.copy(_v).applyMatrix4(ctx.camera.matrixWorldInverse);
    const front = _c.z < -0.05; _v.project(ctx.camera);
    return [+((_v.x + 1) / 2).toFixed(4), +((1 - _v.y) / 2).toFixed(4), front ? 1 : 0];
  }
  function frame() {
    if (!config || !resolved.size) return;
    const now = (typeof performance !== 'undefined' ? performance.now() : Date.now()), refreshVis = now - visAt > 220;
    if (refreshVis) visAt = now;
    ctx.camera.updateMatrixWorld();
    const items = [], fibres = [], zones = [];
    for (const [id, r] of resolved) {
      const shown = !!(r.st.group && r.st.group.visible);
      if (r.mesh) r.mesh.visible = shown;
      if (!shown) continue;
      if (refreshVis || !visCache.has(id)) visCache.set(id, +(ctx.visibility ? ctx.visibility(r.point) : 1).toFixed(2));
      const [x, y, f] = project(r.point); items.push([id, x, y, f, visCache.get(id)]);
      if (r.samples) fibres.push([id, r.samples.map(q => { const [a, b, c] = project(q.p); return [a, b, c, +q.t.toFixed(3)]; })]);
      if (r.ring) zones.push([id, r.ring.map(q => project(q))]);
    }
    const sig = JSON.stringify([items, fibres, zones]);
    if (sig === lastSig) return; lastSig = sig;
    post({type: MSG.frame, items, fibres, zones});
  }
  fetch(ctx.configUrl || CONFIG_URL, {cache: 'no-store'}).then(r => { if (!r.ok) throw Error('config ' + r.status); return r.json(); }).then(cfg => {
    const v = validateConfig(cfg); config = cfg; sensors.push(...filterScene(v.sensors, ctx.sceneFilter || null));
    if (!v.ok) console.warn('[sensor-demo] config entries skipped:', v.errors);
    sendState(); tryResolve(); const iv = setInterval(() => { tryResolve(); if (resolved.size + Object.values(states).filter(x => x.status === 'refused').length >= sensors.length) clearInterval(iv); }, 600); if (iv && iv.unref) iv.unref();   // Node tests: never keep the process alive
  }).catch(e => { failed = String(e && e.message || e); sendState(); console.warn('[sensor-demo] not shown:', failed); });
  const api = {frame, inspection: () => ({scene: ctx.sceneFilter || null, sensors: sensors.map(x => x.id), subsets: Object.fromEntries(Object.entries(subsets).map(([k, v]) => [k, {ids: v.ids || [], parts: v.parts || [], loaded: !!v.st, meshes: v.st ? v.st.meshes.length : 0, error: v.error || null}])), config: !!config, failed, states: JSON.parse(JSON.stringify(states)), dtsMeshes: group.children.length}), resend: () => { lastSig = ''; sendState(); }};
  return api;
}

/* ═══════════════ compare-page runtime ═══════════════ */
const PARENT_CSS = `
#sdLayer{position:absolute;inset:0;z-index:7;pointer-events:none;overflow:hidden}
#sdLayer svg{position:absolute;left:0;top:0;width:100%;height:100%;overflow:visible}
#sdLayer .sd-pin{position:absolute;left:0;top:0;width:28px;height:28px;margin:-14px 0 0 -14px;border-radius:50%;border:3px solid #fff;color:#fff;font:700 13px/22px Arial,sans-serif;text-align:center;padding:0;cursor:pointer;pointer-events:auto;box-shadow:0 2px 8px rgba(0,0,0,.55);transition:opacity .15s}
#sdLayer .sd-pin:hover,#sdLayer .sd-pin.on{outline:3px solid #FDB515;outline-offset:1px}
#sdLayer .sd-pin[hidden],#sdLayer .sd-chip[hidden]{display:none}
#sdLayer .sd-pin svg{display:block;margin:3px auto 0}
#sdLayer .sd-pin.alert svg{margin-top:2px}
#sdLayer .sd-chip{position:absolute;left:0;top:0;display:inline-flex;align-items:center;gap:4px;padding:1px 6px 1px 2px;border-radius:9px;border:1.5px solid #FDB515;background:rgba(8,14,28,.82);color:#f1f5f9;font:700 11px/15px Arial,sans-serif;white-space:nowrap;pointer-events:auto;cursor:pointer;box-shadow:0 1px 4px rgba(0,0,0,.45);transition:opacity .15s}
#sdLayer .sd-chip b{display:inline-block;min-width:15px;height:15px;border-radius:8px;color:#fff;font-size:10px;line-height:15px;text-align:center}
#sdLayer .sd-chip.on{outline:2px solid #FDB515}
#sdCard .sd-dot svg{display:block;margin:1px}
#sdLayer .sd-pin.alert{width:24px;height:24px;margin:-12px 0 0 -12px;line-height:18px;font-size:12px}
@keyframes sdPulse{0%{r:14;stroke-opacity:.95}100%{r:46;stroke-opacity:0}}
#sdLayer circle.sd-pulse{animation:sdPulse 1.8s ease-out infinite}
@media(prefers-reduced-motion:reduce){#sdLayer circle.sd-pulse{animation:none}}
#sdBadge{position:absolute;z-index:8;left:50%;bottom:12px;transform:translateX(-50%);display:flex;align-items:center;gap:8px;max-width:calc(100% - 20px);padding:5px 6px 5px 11px;border-radius:8px;background:rgba(8,14,28,.82);border:1px solid #FDB515;color:#ffe29b;font:700 12px Arial,sans-serif;white-space:nowrap;box-shadow:0 2px 10px rgba(0,0,0,.35)}
#sdBadge small{font-weight:400;color:#cbd5e1}
#sdBadge button{font:700 11px Arial;background:#244562;color:#fff;border:1px solid #8aa5bb;border-radius:5px;padding:2px 7px;cursor:pointer}
#sdCard{position:absolute;left:0;top:0;z-index:9;width:270px;padding:9px 12px;border-radius:12px;background:rgba(8,14,28,.78);backdrop-filter:blur(14px) saturate(1.2);-webkit-backdrop-filter:blur(14px) saturate(1.2);border:1px solid rgba(253,181,21,.55);box-shadow:0 6px 24px rgba(0,0,0,.35);color:#e2e8f0;font:13px/1.4 Arial,sans-serif;pointer-events:none;opacity:0;visibility:hidden;transition:opacity .15s ease,visibility 0s linear .15s}
#sdCard.show{opacity:1;visibility:visible;transition:opacity .15s ease}
#sdCard .gz-top{display:flex;align-items:center;justify-content:space-between;gap:8px}
#sdCard .gz-name{font-weight:600;font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#sdCard .gz-badge{flex:none;font:700 9.5px/1 monospace;letter-spacing:.3px;padding:3px 6px;border-radius:4px}
#sdCard .gz-badge.sd-demo{background:rgba(253,181,21,.18);color:#fbbf24}
#sdCard .gz-sub{margin-top:2px;font-size:12px;color:#94a3b8}
#sdCard .gz-val{margin-top:6px;font-size:14px;font-weight:600;color:#f1f5f9}
#sdCard .gz-det{margin-top:2px;font-size:12px;line-height:1.35;color:#94a3b8}
#sdCard .gz-spark{margin-top:6px}#sdCard .gz-spark svg{display:block;width:100%;height:30px}
#sdCard .sd-dot{display:inline-block;width:16px;height:16px;border-radius:50%;margin-right:6px;vertical-align:-3px;border:1px solid #fff}
#sdCard .sd-grad{margin-top:7px;height:9px;border-radius:5px}
#sdCard .sd-grad-cap{display:flex;justify-content:space-between;font-size:10.5px;color:#94a3b8;margin-top:2px}
#sdCard .sd-map{margin-top:7px;padding-top:6px;border-top:1px solid rgba(148,163,184,.3);font-size:12px;color:#cbd5e1;line-height:1.35;word-break:break-word}
#sdCard .sd-map b{color:#f1f5f9;font-weight:600}#sdCard .sd-map span{color:#94a3b8;font-size:11px}
#sdCard .sd-note{margin-top:5px;font-size:11px;color:#fbbf24}
body.sd-card-on #lensCard{opacity:0!important;visibility:hidden!important}
body.sd-off #sdLayer{display:none}
@media(max-width:768px),(pointer:coarse){#sdCard{width:230px;font-size:11.5px}#sdBadge{font-size:10.5px;bottom:58px;max-width:calc(100% - 24px)}#sdBadge small{display:none}#sdLayer .sd-chip{font-size:9.5px;line-height:13px;padding:0 5px 0 2px}#sdLayer .sd-chip b{min-width:13px;height:13px;line-height:13px;font-size:9px}}
`;
const MIN_VIS = 0.5;   // Range fade x occlusion below this: the sensor is not drawn (Room: about 11 m; Near: about 4.5 m)
function mountParent(ctx) {
  const lens = ctx.lens || null;   // {set(px, py, mainW, mainH), release()} from scan-compare: Lens follows the focused sensor
  const doc = ctx.document || document, main = ctx.main, frame = ctx.frame, SVGNS = 'http://www.w3.org/2000/svg';
  const style = doc.createElement('style'); style.id = 'sdStyle'; style.textContent = PARENT_CSS; doc.head.appendChild(style);
  const layer = doc.createElement('div'); layer.id = 'sdLayer'; layer.setAttribute('aria-label', 'Demo sensors (illustrative)');
  const svg = doc.createElementNS(SVGNS, 'svg'); layer.appendChild(svg);
  const gZones = doc.createElementNS(SVGNS, 'g'), gLinks = doc.createElementNS(SVGNS, 'g'), gFibre = doc.createElementNS(SVGNS, 'g'), gPulse = doc.createElementNS(SVGNS, 'g');
  svg.append(gZones, gLinks, gFibre, gPulse);
  const badge = doc.createElement('div'); badge.id = 'sdBadge'; badge.setAttribute('role', 'note');
  badge.innerHTML = '<span>' + esc(BADGE_TEXT) + ' <small id="sdCount"></small></span><button type="button" id="sdLensMode" hidden title="Lens follows the scene\u2019s main sensor, or the mouse">Lens: on sensor</button><button type="button" id="sdToggle" aria-pressed="true">Hide</button>';
  const card = doc.createElement('div'); card.id = 'sdCard'; card.setAttribute('role', 'status');
  main.append(layer, badge, card);
  const byId = new Map(), pins = new Map(), chips = new Map(), elements = {};
  let last = null, raf = 0, hover = null, pinned = null, on = true, failed = null, cfgAll = null, lensLocked = false;
  const worlds = {}, chipSize = new Map(); let lastRect = null, cardSize = null, lastProj = {}, lastSeen = [], restDiff = null;
  /* Lens rest sensor (?focus= or the scene's primary). auto = the Lens sits on it when no sensor is pinned (a pin click or a
     deck card switches the lock; releasing returns to the primary). In a deck embed it always stays on; standalone, the badge
     button toggles between "on sensor" and mouse-follow. */
  let primaryId = null, auto = false;
  const embedded = (ctx.window || window).parent !== (ctx.window || window);   // BIM-world anchors per sensor (from the state message); measured chip sizes
  /* Pins follow the camera pose the compare page has just forwarded (ctx.getPose), projected here in the same frame; the
     BIM pane's own 2D projection (one render + one message later) is only the fallback, and still supplies visibility. */
  function projected(R) {
    const pose = ctx.getPose ? ctx.getPose() : null, aspect = R.w / R.h;
    if (!last || !pose || !(aspect > 0)) return last;
    const P = q => projectPoint(q, pose, aspect);
    return {
      items: (last.items || []).map(it => { const w = worlds[it[0]]; if (!w) return it; const [x, y, f] = P(w.p); return [it[0], x, y, f, it[4]]; }),
      fibres: (last.fibres || []).map(([id, pts]) => { const w = worlds[id]; return [id, w && w.fibre ? w.fibre.map(q => { const [x, y, f] = P(q); return [x, y, f, q[3]]; }) : pts]; }),
      zones: (last.zones || []).map(([id, pts]) => { const w = worlds[id]; return [id, w && w.ring ? w.ring.map(P) : pts]; })};
  }
  const styleOf = s => typeStyle(cfgAll, s.type);
  const count = doc.getElementById('sdCount'), lensBtn = doc.getElementById('sdLensMode');
  lensBtn.onclick = e => { auto = !auto; renderCard(); e.currentTarget.blur(); };
  doc.getElementById('sdToggle').onclick = e => { on = !on; doc.body.classList.toggle('sd-off', !on); e.currentTarget.textContent = on ? 'Hide' : 'Show'; e.currentTarget.setAttribute('aria-pressed', String(on)); if (!on) { pinned = hover = null; } renderCard(); e.currentTarget.blur(); };
  function pinFor(s) {
    let b = pins.get(s.id); if (b) return b;
    const st = styleOf(s);
    b = doc.createElement('button'); b.type = 'button'; b.className = 'sd-pin' + (s.type === 'alert' ? ' alert' : ''); b.innerHTML = iconSvg(st.icon, s.type === 'alert' ? 13 : 15);
    b.style.background = st.color; b.dataset.sensor = s.id; b.dataset.type = s.type; b.setAttribute('aria-label', (s.k ? s.k + ' ' : '') + s.label + ' (demo, illustrative)'); b.hidden = true;
    const c = doc.createElement('span'); c.className = 'sd-chip'; c.dataset.sensor = s.id; c.style.borderColor = st.color; c.hidden = true;
    c.innerHTML = (s.k ? '<b style="background:' + esc(st.color) + '">' + esc(s.k) + '</b>' : '') + esc(st.short);
    c.addEventListener('click', e => { e.stopPropagation(); pinned = pinned === s.id ? null : s.id; renderCard(); });
    layer.appendChild(c); chips.set(s.id, c);
    b.addEventListener('mouseenter', () => { hover = s.id; renderCard(); }); b.addEventListener('mouseleave', () => { hover = null; renderCard(); });
    b.addEventListener('focus', () => { hover = s.id; renderCard(); }); b.addEventListener('blur', () => { hover = null; renderCard(); });
    b.addEventListener('click', e => { e.stopPropagation(); pinned = pinned === s.id ? null : s.id; renderCard(); });
    layer.appendChild(b); pins.set(s.id, b); return b;
  }
  function rect() {
    const r = frame.getBoundingClientRect(), m = main.getBoundingClientRect();
    return lastRect = {x: r.left - m.left, y: r.top - m.top, w: r.width, h: r.height, mw: m.width, mh: m.height};
  }
  const at = (R, x, y) => [R.x + x * R.w, R.y + y * R.h];
  const inView = (R, p) => p[0] > R.x - 40 && p[0] < R.x + R.w + 40 && p[1] > R.y - 40 && p[1] < R.y + R.h + 40;
  function el(tag, attrs) { const n = doc.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); return n; }
  function render() {
    raf = 0; if (!last) return;
    const R = rect(), shown = R.w > 20 && R.h > 20, seen = new Set(), pos = {}, L = projected(R);
    gZones.replaceChildren(); gLinks.replaceChildren(); gFibre.replaceChildren(); gPulse.replaceChildren();
    const visOf = {}; for (const it of L.items || []) visOf[it[0]] = it[4];
    const faint = id => !(visOf[id] >= MIN_VIS);   /* beyond the Range or not reported: draw nothing for that sensor */
    if (shown) {
      for (const [id, pts] of L.zones || []) {
        const s = byId.get(id); if (!s || faint(id) || pts.some(p => !p[2])) continue;
        const xy = pts.map(p => at(R, p[0], p[1]));
        gZones.appendChild(el('polygon', {points: xy.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' '), fill: s.color || '#E8590C', 'fill-opacity': '.2', stroke: s.color || '#E8590C', 'stroke-opacity': '.8', 'stroke-width': '2', 'stroke-dasharray': '6 5'}));
      }
      for (const [id, pts] of L.fibres || []) {
        const s = byId.get(id); if (!s || !s.dts || faint(id)) continue;
        for (let i = 0; i + 1 < pts.length; i++) {
          const a = pts[i], b = pts[i + 1]; if (!a[2] || !b[2]) continue;
          const pa = at(R, a[0], a[1]), pb = at(R, b[0], b[1]), c = (a[3] + b[3]) / 2;
          const xy = {x1: pa[0].toFixed(1), y1: pa[1].toFixed(1), x2: pb[0].toFixed(1), y2: pb[1].toFixed(1)};
          gFibre.appendChild(el('line', {...xy, stroke: '#fff', 'stroke-width': '7', 'stroke-linecap': 'round', 'stroke-opacity': '.9'}));
          gFibre.appendChild(el('line', {...xy, stroke: cssColor(colorAt(dtsValue(c, s.dts))), 'stroke-width': '4', 'stroke-linecap': 'round'}));
        }
      }
      for (const [id, x, y, front, vis] of L.items || []) {
        const s = byId.get(id); if (!s) continue; const p = at(R, x, y);
        if (!front || !inView(R, p) || !(vis >= MIN_VIS)) continue;
        pos[id] = p; seen.add(id);
        const b = pinFor(s); if (b.hidden) b.hidden = false; b.style.transform = 'translate(' + p[0].toFixed(1) + 'px,' + p[1].toFixed(1) + 'px)'; b.style.opacity = String(Math.min(1, vis)); b.dataset.x = p[0].toFixed(1); b.dataset.y = p[1].toFixed(1);
        b.title = s.label + ' · ' + s.reading.value + ' (illustrative)';
        if (s.type === 'alert') {
          gPulse.appendChild(el('circle', {cx: p[0].toFixed(1), cy: p[1].toFixed(1), r: '20', fill: 'none', stroke: '#fff', 'stroke-width': '6', 'stroke-opacity': String(0.9 * vis)}));
          gPulse.appendChild(el('circle', {cx: p[0].toFixed(1), cy: p[1].toFixed(1), r: '20', fill: 'none', stroke: s.color || '#C81E1E', 'stroke-width': '3.5'}));
          gPulse.appendChild(el('circle', {class: 'sd-pulse', cx: p[0].toFixed(1), cy: p[1].toFixed(1), r: '14', fill: 'none', stroke: s.color || '#C81E1E', 'stroke-width': '3'}));
        }
      }
      for (const [id, p] of Object.entries(pos)) for (const l of byId.get(id).links || []) if (pos[l])
        gLinks.appendChild(el('line', {x1: p[0].toFixed(1), y1: p[1].toFixed(1), x2: pos[l][0].toFixed(1), y2: pos[l][1].toFixed(1), stroke: '#FDB515', 'stroke-width': '2.5', 'stroke-dasharray': '6 5', 'stroke-opacity': '.95'}));
    }
    for (const [id, b] of pins) if (!seen.has(id)) b.hidden = true;
    lastProj = {}; for (const [id, x, y, front] of L.items || []) { const q = at(R, x, y); lastProj[id] = [q[0], q[1], front]; }
    lastSeen = [...seen];
    /* at rest the page projection must coincide with the BIM pane's own (one render later): worst pin offset, px */
    if (L !== last) { let m = 0; for (const it of last.items || []) { const q = lastProj[it[0]]; if (q && it[3]) { const b2 = at(R, it[1], it[2]); m = Math.max(m, Math.hypot(b2[0] - q[0], b2[1] - q[1])); } } restDiff = +m.toFixed(2); }
    /* always-visible type chips beside the pins, nudged apart (placeChips) */
    const items = [];
    for (const [id, c] of chips) { if (!seen.has(id)) { c.hidden = true; continue; } if (c.hidden) c.hidden = false; }
    for (const [id, c] of chips) if (seen.has(id) && !chipSize.has(id) && c.offsetWidth) chipSize.set(id, [c.offsetWidth, c.offsetHeight]);   // one layout read, first time only
    for (const id of seen) { const z = chipSize.get(id) || [70, 18]; items.push({id, x: pos[id][0], y: pos[id][1], w: z[0], h: z[1]}); }
    for (const q of placeChips(items, {x: 4, y: 4, w: R.mw - 8, h: R.mh - 8}, 14)) { const c = chips.get(q.id); c.style.transform = 'translate(' + q.x.toFixed(1) + 'px,' + q.y.toFixed(1) + 'px)'; c.style.opacity = pins.get(q.id).style.opacity; }
    const attached = Object.values(elements).length;
    count.textContent = failed ? '· not loaded' : '· ' + (ctx.sceneFilter ? 'scene ' + ctx.sceneFilter + ' · ' : '') + seen.size + ' in view · ' + attached + ' attached to BIM elements';
    renderCard();
  }
  function renderCard() {
    const id = on ? (pinned || hover) : null, s = id && byId.get(id), b = s && pins.get(id);
    pins.forEach((p, k) => p.classList.toggle('on', k === id)); chips.forEach((c, k) => c.classList.toggle('on', k === id));
    /* the Lens follows a clicked / deck-focused sensor: centred on its pin, recomputed from each new projection */
    const lockId = on ? (pinned || (auto ? primaryId : null)) : null;
    const RR = lastRect || rect();   // the rect read at the start of this render: no forced layout after the pin writes
    const pt = lockId ? lensAnchor(lockId, lastProj, lastSeen) : null;
    if (lens && lockId) { if (pt) lens.set(pt[0], pt[1], RR.mw, RR.mh); lensLocked = true; }
    else if (lens && lensLocked) { lens.release(); lensLocked = false; }
    if (lensBtn) { lensBtn.hidden = !primaryId || embedded; lensBtn.textContent = auto ? 'Lens: on sensor' : 'Lens: mouse'; lensBtn.setAttribute('aria-pressed', String(auto)); }
    if (!s || !b || b.hidden) { card.classList.remove('show'); doc.body.classList.remove('sd-card-on'); return; }
    if (card.dataset.sensor !== id) { card.innerHTML = cardHtml(s, elements[id], styleOf(s)); card.dataset.sensor = id; cardSize = null; }
    const R = RR, x = +b.dataset.x || 0, y = +b.dataset.y || 0;
    if (!cardSize) cardSize = [card.offsetWidth || 270, card.offsetHeight || 160];   // measured once per card content
    const [cw, ch] = cardSize;
    let L = x + 22; if (L + cw > R.mw - 8) L = x - 22 - cw; L = Math.max(8, Math.min(R.mw - cw - 8, L));
    const T = Math.max(8, Math.min(R.mh - ch - 52, y - ch / 2));
    card.style.transform = 'translate(' + L.toFixed(0) + 'px,' + T.toFixed(0) + 'px)';
    card.classList.add('show'); doc.body.classList.add('sd-card-on');
  }
  function schedule() { if (!raf) raf = requestAnimationFrame(render); }
  const win = ctx.window || window;
  win.addEventListener('message', e => {
    if (e.origin !== win.location.origin) return; const d = e.data;
    if (e.source === frame.contentWindow) {
      if (d && d.type === MSG.state) { failed = d.failed || null; for (const x of Array.isArray(d.sensors) ? d.sensors : []) { if (x && x.status === 'attached' && x.element && byId.has(x.id)) { elements[x.id] = x.element; if (x.world && Array.isArray(x.world.p) && x.world.p.length === 3 && x.world.p.every(finite)) worlds[x.id] = x.world; } else if (x) { delete elements[x.id]; delete worlds[x.id]; } } card.dataset.sensor = ''; schedule(); }
      else if (d && d.type === MSG.frame) { last = d; schedule(); }
      return;
    }
    /* the presenting deck (parent page, same origin) can point at one sensor: {type:'grimes-sensor-demo-focus', id|null} */
    if (e.source === win.parent && win.parent !== win && d && d.type === MSG.focus) { pinned = typeof d.id === 'string' && byId.has(d.id) ? d.id : null; renderCard(); }
  });
  new ResizeObserver(schedule).observe(main);
  doc.documentElement.addEventListener('mouseleave', () => { if (hover) { hover = null; renderCard(); } });   // pointer left the page (e.g. into the deck)
  main.addEventListener('pointerdown', e => { if (!e.target.closest || !e.target.closest('.sd-pin')) { if (pinned) { pinned = null; renderCard(); } } }, true);
  fetch(ctx.configUrl || CONFIG_URL, {cache: 'no-store'}).then(r => { if (!r.ok) throw Error('config ' + r.status); return r.json(); }).then(cfg => {
    const v = validateConfig(cfg); cfgAll = cfg; for (const s of filterScene(v.sensors, ctx.sceneFilter || null)) byId.set(s.id, s);
    primaryId = primaryFor(cfg, ctx.sceneFilter || null, ctx.focus || null, [...byId.keys()]); auto = !!primaryId; schedule();
  }).catch(e => { failed = String(e && e.message || e); count.textContent = '· not loaded'; });
  return {poseChanged: schedule,
    /* a locked Lens ignores mouse moves over the photo (dragging the view included), so it stays on its sensor; standalone,
       the badge button "Lens: on sensor / mouse" hands it back to the mouse. true = let the mouse move the Lens */
    pointerMoved: () => !lensLocked,
    inspection: () => ({primary: primaryId, auto, lockId: on ? (pinned || (auto ? primaryId : null)) : null, restDiff, projectedFromPose: !!(ctx.getPose && ctx.getPose() && Object.keys(worlds).length), lensLocked, chips: [...chips].filter(([, c]) => !c.hidden).map(([id, c]) => { const r = c.getBoundingClientRect(); return [id, c.textContent, Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; }),
    pinXY: Object.fromEntries([...pins].filter(([, b]) => !b.hidden).map(([id, b]) => [id, [+b.dataset.x, +b.dataset.y]])), scene: ctx.sceneFilter || null, sensors: byId.size, attached: Object.keys(elements), pins: [...pins].filter(([, b]) => !b.hidden).map(([id]) => id), fibreSegments: gFibre.childNodes.length / 2, pulses: gPulse.childNodes.length / 3, links: gLinks.childNodes.length, zones: gZones.childNodes.length, card: card.classList.contains('show') ? card.dataset.sensor : null, failed}),
    focus: id => { pinned = byId.has(id) ? id : null; renderCard(); }};
}

return {parseFocusParam, primaryFor, lensAnchor, projectPoint, typeStyle, iconSvg, lensPoint, placeChips, SCHEMA, STATUS, CONFIG_URL, BADGE_TEXT, MSG, TYPES, parseSensorsParam, parseSceneParam, filterScene, validateConfig, colorAt, cssColor, dtsTempC, dtsValue,
  principalAxis, axisParam, axisPoint, anchorPoint, zoneRing, esc, sparkSvg, cardHtml, mountBim, mountParent, PARENT_CSS};
});
