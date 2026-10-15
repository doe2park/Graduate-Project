/* twin/as-built.js — manual as-built position adjustments for BIM elements (pure; no DOM, no network, no Three.js).
   Used by scan-bim.html (render-time application) and scan-compare.html (editing, export/import).
   Mirrored by scripts/check_as_built.py (schema + statistics). Owner steps: docs/AS_BUILT_ADJUSTMENTS.md.

   What it is: an owner's visual correction "the installed light is ~12 cm east of the BIM light", recorded
   per element in buildings/grimes/as-built-adjustments.json. Status is always 'manual-unsurveyed'.
   What it never does: modify a GLB, a node name or a sidecar. Adjustments are applied at render time to the
   runtime draw-call tier only, and are exactly reversible:
     - instanced meshes: the element's instance matrices are replaced by  M * original  (originals snapshotted);
     - merged meshes:    the element's own vertex range (positions, normals, tangents) is rewritten as M * original
                         in place. The merged tier never shares vertices between elements, so no neighbour moves.
                         Index buffer and the triangle-range -> element map are untouched, so picking identity
                         (resolveElementHit) is unchanged. Restore copies the snapshotted Float32 slices back (bit-exact).
   M = T(pivot + translation) * Ry(yaw) * T(-pivot), in the BIM pane world frame (Three.js Y-up metres,
   the same frame the scan registration targets). pivot = centre of the element's design bounding box. */
(function (root, factory) {
  const api = factory();
  if (root) root.AsBuilt = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';

const SCHEMA = 'as-built-adjustments/1', FRAME = 'bim-pane-world-y-up-m', STATUS = 'manual-unsurveyed';
const LAYER_KEYS = ['equipment', 'fixtures', 'lighting', 'lifesafety', 'structural', 'conduit', 'duct', 'hydronic', 'plumbing', 'fire'];
const MAX_OFFSET_M = 1.0, MAX_YAW_DEG = 45, SCAN_MODES = ['photo', 'mesh', 'splat'];
const D2R = Math.PI / 180;
const finite = v => typeof v === 'number' && Number.isFinite(v);
const vec3 = v => Array.isArray(v) && v.length === 3 && v.every(finite);
const round = (v, d) => { const f = 10 ** d; const r = Math.round(v * f) / f; return Object.is(r, -0) ? 0 : r; };
const key = (layer, id) => String(layer) + ':' + String(id);

function emptyDocument() {
  return {_schema: SCHEMA, frame: FRAME,
    _doc: 'Manual as-built position adjustments (owner visual match against a captured photo/mesh). Not surveyed. Applied at render time only; GLBs and node names are never modified. See docs/AS_BUILT_ADJUSTMENTS.md.',
    adjustments: []};
}

function validateAdjustment(a) {
  const e = [];
  if (!a || typeof a !== 'object') return ['adjustment must be an object'];
  const el = a.element;
  if (!el || typeof el !== 'object') e.push('element missing');
  else {
    if (typeof el.id !== 'string' || !el.id.trim() || el.id.length > 80) e.push('element.id must be a non-empty string');
    if (!LAYER_KEYS.includes(el.layer)) e.push('element.layer must be one of ' + LAYER_KEYS.join(', '));
    for (const k of ['name', 'type', 'system']) if (el[k] != null && typeof el[k] !== 'string') e.push('element.' + k + ' must be a string');
  }
  if (!vec3(a.translation)) e.push('translation must be three finite numbers (m)');
  else if (Math.hypot(...a.translation) > MAX_OFFSET_M) e.push('translation exceeds ' + MAX_OFFSET_M + ' m (likely a mistake; a re-registration is the right tool for larger offsets)');
  if (!finite(a.yawDegrees)) e.push('yawDegrees must be a finite number');
  else if (Math.abs(a.yawDegrees) > MAX_YAW_DEG) e.push('yawDegrees exceeds ±' + MAX_YAW_DEG);
  if (a.pivot != null && !vec3(a.pivot)) e.push('pivot must be three finite numbers when present');
  const ev = a.evidence;
  if (!ev || typeof ev !== 'object') e.push('evidence missing');
  else {
    if (typeof ev.captureDate !== 'string' || !/^\d{4}-\d\d-\d\d$/.test(ev.captureDate) || !Number.isFinite(Date.parse(ev.captureDate))) e.push('evidence.captureDate must be YYYY-MM-DD');
    if (!SCAN_MODES.includes(ev.scanMode)) e.push('evidence.scanMode must be photo, mesh or splat');
    if (ev.stationIndex != null && !(Number.isInteger(ev.stationIndex) && ev.stationIndex >= 0)) e.push('evidence.stationIndex must be a non-negative integer or null');
    if (ev.stationLabel != null && typeof ev.stationLabel !== 'string') e.push('evidence.stationLabel must be a string or null');
    if (ev.registration != null && typeof ev.registration !== 'string') e.push('evidence.registration must be a string');
  }
  if (typeof a.author !== 'string' || !/^[A-Za-z]{2,4}$/.test(a.author)) e.push('author must be 2-4 letter initials');
  if (typeof a.timestamp !== 'string' || !/^\d{4}-\d\d-\d\dT/.test(a.timestamp) || !Number.isFinite(Date.parse(a.timestamp))) e.push('timestamp must be an ISO date-time');
  if (a.note != null && (typeof a.note !== 'string' || a.note.length > 500)) e.push('note must be a string of at most 500 characters');
  if (a.status !== STATUS) e.push("status must be '" + STATUS + "'");
  return e;
}

/* opts.elementExists(layer, id) -> boolean (optional sidecar check). Returns {ok, errors, adjustments}. */
function validateDocument(doc, opts) {
  const errors = [];
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) return {ok: false, errors: ['document must be a JSON object'], adjustments: []};
  if (doc._schema !== SCHEMA) errors.push("_schema must be '" + SCHEMA + "'");
  if (doc.frame !== FRAME) errors.push("frame must be '" + FRAME + "'");
  if (!Array.isArray(doc.adjustments)) return {ok: false, errors: errors.concat('adjustments must be an array'), adjustments: []};
  const seen = new Set(), good = [];
  doc.adjustments.forEach((a, i) => {
    const e = validateAdjustment(a);
    if (!e.length) {
      const k = key(a.element.layer, a.element.id);
      if (seen.has(k)) e.push('duplicate element ' + k);
      else if (opts && typeof opts.elementExists === 'function' && !opts.elementExists(a.element.layer, a.element.id)) e.push('element ' + k + ' is not in the ' + a.element.layer + ' sidecar');
      seen.add(k);
    }
    if (e.length) errors.push(...e.map(m => 'adjustments[' + i + ']: ' + m)); else good.push(a);
  });
  return {ok: errors.length === 0, errors, adjustments: good};
}

/* Immutable edit helpers. Values are rounded (0.1 mm, 0.01°) so repeated nudges never accumulate float noise. */
function createAdjustment({id, layer, info, evidence, author, note, pivot, now}) {
  return {element: Object.assign({id: String(id), layer}, info && info.name ? {name: String(info.name)} : {}, info && info.type ? {type: String(info.type)} : {}, info && info.system ? {system: String(info.system)} : {}),
    translation: [0, 0, 0], yawDegrees: 0, pivot: vec3(pivot) ? pivot.map(v => round(v, 4)) : undefined,
    evidence: Object.assign({captureDate: null, scanMode: 'photo', stationIndex: null, stationLabel: null}, evidence || {}),
    author: author || '', timestamp: (now ? new Date(now) : new Date()).toISOString(), note: note || '', status: STATUS};
}
function nudge(adj, {dx = 0, dy = 0, dz = 0, dyaw = 0} = {}, now) {
  const t = adj.translation;
  return Object.assign({}, adj, {translation: [round(t[0] + dx, 4), round(t[1] + dy, 4), round(t[2] + dz, 4)],
    yawDegrees: round((adj.yawDegrees || 0) + dyaw, 2), timestamp: (now ? new Date(now) : new Date()).toISOString()});
}
function isIdentity(adj) { return !adj || (vec3(adj.translation) && adj.translation.every(v => v === 0) && !adj.yawDegrees); }
function upsert(doc, adj) {
  const k = key(adj.element.layer, adj.element.id), list = (doc.adjustments || []).filter(a => key(a.element.layer, a.element.id) !== k);
  return Object.assign({}, doc, {adjustments: list.concat(adj)});
}
function remove(doc, k) { return Object.assign({}, doc, {adjustments: (doc.adjustments || []).filter(a => key(a.element.layer, a.element.id) !== k)}); }
function find(doc, k) { return (doc && Array.isArray(doc.adjustments) ? doc.adjustments : []).find(a => a && a.element && key(a.element.layer, a.element.id) === k) || null; }
/* Export: drop identity (zero) adjustments, stable order, JSON text with trailing newline. */
function exportText(doc) {
  const list = (doc.adjustments || []).filter(a => !isIdentity(a)).slice().sort((a, b) => key(a.element.layer, a.element.id).localeCompare(key(b.element.layer, b.element.id)))
    .map(a => { const c = JSON.parse(JSON.stringify(a)); if (c.pivot == null) delete c.pivot; return c; });
  return JSON.stringify(Object.assign(emptyDocument(), {updated: new Date().toISOString(), adjustments: list}), null, 2) + '\n';
}

/* ── 4x4 maths, column-major (Three.js Matrix4.elements order) ── */
function multiply(a, b) {
  const o = new Array(16);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
    let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k]; o[c * 4 + r] = s;
  }
  return o;
}
/* M = T(pivot + t) * Ry(yaw) * T(-pivot). Ry follows Three.js rotation.y: x' = c x + s z, z' = -s x + c z. */
function adjustmentMatrix(translation, yawDegrees, pivot) {
  const a = (yawDegrees || 0) * D2R, c = Math.cos(a), s = Math.sin(a), p = vec3(pivot) ? pivot : [0, 0, 0], t = translation;
  const rx = p[0] - (c * p[0] + s * p[2]), rz = p[2] - (-s * p[0] + c * p[2]);
  return [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, rx + t[0], t[1], rz + t[2], 1];
}
function applyPoint(m, x, y, z) { return [m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13], m[2] * x + m[6] * y + m[10] * z + m[14]]; }
function applyDir(m, x, y, z) { const v = [m[0] * x + m[4] * y + m[8] * z, m[1] * x + m[5] * y + m[9] * z, m[2] * x + m[6] * y + m[10] * z]; const l = Math.hypot(...v) || 1; return [v[0] / l, v[1] / l, v[2] / l]; }

/* ── Render-time application on the runtime draw-call tier (duck-typed Three.js objects) ── */
function targetsFor(meshes, id) {
  const out = [];
  for (const mesh of meshes || []) {
    const ids = mesh && mesh.userData && mesh.userData.ids;
    if (!Array.isArray(ids) || !ids.includes(id)) continue;
    if (mesh.isInstancedMesh) { const idx = []; ids.forEach((x, i) => { if (x === id) idx.push(i); }); out.push({mesh, kind: 'instanced', instances: idx}); }
    else {
      const pos = mesh.geometry && mesh.geometry.attributes && mesh.geometry.attributes.position;
      if (!pos) continue;
      const ranges = Array.isArray(mesh.userData.ranges) ? mesh.userData.ranges.filter(r => r.id === id).map(r => ({vertexStart: r.vertexStart, vertexCount: r.vertexCount}))
        : ids.length === 1 ? [{vertexStart: 0, vertexCount: pos.count != null ? pos.count : pos.array.length / pos.itemSize}] : [];
      if (ranges.length) out.push({mesh, kind: 'merged', ranges});
    }
  }
  return out;
}
const VEC_ATTRS = ['position', 'normal', 'tangent'];
function snapshot(target) {
  if (target.kind === 'instanced') { const a = target.mesh.instanceMatrix.array; target.saved = target.instances.map(i => Float32Array.prototype.slice.call(a, i * 16, i * 16 + 16)); return; }
  const attrs = target.mesh.geometry.attributes; target.saved = {};
  for (const name of VEC_ATTRS) {
    const at = attrs[name]; if (!at) continue;
    target.saved[name] = target.ranges.map(r => at.array.slice(r.vertexStart * at.itemSize, (r.vertexStart + r.vertexCount) * at.itemSize));
  }
}
function refresh(mesh, kind) {
  if (kind === 'instanced') { mesh.instanceMatrix.needsUpdate = true; if (typeof mesh.computeBoundingBox === 'function') mesh.computeBoundingBox(); if (typeof mesh.computeBoundingSphere === 'function') mesh.computeBoundingSphere(); return; }
  for (const name of VEC_ATTRS) { const at = mesh.geometry.attributes[name]; if (at) at.needsUpdate = true; }
  if (typeof mesh.geometry.computeBoundingBox === 'function') mesh.geometry.computeBoundingBox();
  if (typeof mesh.geometry.computeBoundingSphere === 'function') mesh.geometry.computeBoundingSphere();
}
function writeTarget(target, m) {
  if (target.kind === 'instanced') {
    const a = target.mesh.instanceMatrix.array;
    target.instances.forEach((i, n) => { a.set(m ? multiply(m, Array.from(target.saved[n])) : target.saved[n], i * 16); });
  } else {
    const attrs = target.mesh.geometry.attributes;
    for (const name of Object.keys(target.saved)) {
      const at = attrs[name], size = at.itemSize;
      target.ranges.forEach((r, n) => {
        const src = target.saved[name][n], base = r.vertexStart * size;
        if (!m) { at.array.set(src, base); return; }
        for (let v = 0; v < r.vertexCount; v++) {
          const o = v * size, out = name === 'position' ? applyPoint(m, src[o], src[o + 1], src[o + 2]) : applyDir(m, src[o], src[o + 1], src[o + 2]);
          at.array[base + o] = out[0]; at.array[base + o + 1] = out[1]; at.array[base + o + 2] = out[2];   // tangent w (handedness) is unchanged by a rotation
        }
      });
    }
  }
  refresh(target.mesh, target.kind);
}
/* Design-state bounds of one target set (from snapshots if present, else live data). */
function boundsOf(targets, useCurrent) {
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  const add = p => { for (let k = 0; k < 3; k++) { if (p[k] < min[k]) min[k] = p[k]; if (p[k] > max[k]) max[k] = p[k]; } };
  for (const t of targets) {
    if (t.kind === 'instanced') {
      const g = t.mesh.geometry; if (g && !g.boundingBox && typeof g.computeBoundingBox === 'function') g.computeBoundingBox();   // cache only, data untouched
      const bb = g && g.boundingBox; if (!bb) continue;
      const a = t.mesh.instanceMatrix.array;
      t.instances.forEach((i, n) => {
        const m = useCurrent || !t.saved ? Array.from(a.slice(i * 16, i * 16 + 16)) : Array.from(t.saved[n]);
        for (const x of [bb.min.x, bb.max.x]) for (const y of [bb.min.y, bb.max.y]) for (const z of [bb.min.z, bb.max.z]) add(applyPoint(m, x, y, z));
      });
    } else {
      const at = t.mesh.geometry.attributes.position, size = at.itemSize;
      t.ranges.forEach((r, n) => {
        const src = !useCurrent && t.saved && t.saved.position ? t.saved.position[n] : at.array.subarray(r.vertexStart * size, (r.vertexStart + r.vertexCount) * size);
        for (let o = 0; o < src.length; o += size) add([src[o], src[o + 1], src[o + 2]]);
      });
    }
  }
  return Number.isFinite(min[0]) ? {min, max, center: [0, 1, 2].map(k => (min[k] + max[k]) / 2)} : null;
}

/* One adjuster per BIM pane. apply() always rewrites from the design snapshot, so nudging never drifts. */
function createAdjuster() {
  const state = new Map();   // key -> {layer, id, targets, pivot, adj}
  function restore(k) {
    const s = state.get(k); if (!s) return false;
    for (const t of s.targets) writeTarget(t, null);
    state.delete(k); return true;
  }
  function apply(meshes, layer, id, adj) {
    const k = key(layer, id);
    let s = state.get(k);
    if (!s) {
      const targets = targetsFor(meshes, id);
      if (!targets.length) return null;
      targets.forEach(snapshot);
      s = {layer, id, targets, pivot: null, adj: null}; state.set(k, s);
    }
    const design = boundsOf(s.targets, false);
    s.pivot = vec3(adj.pivot) ? adj.pivot.slice() : design ? design.center.map(v => round(v, 4)) : [0, 0, 0];
    s.adj = adj;
    const m = adjustmentMatrix(adj.translation, adj.yawDegrees, s.pivot);
    for (const t of s.targets) writeTarget(t, m);
    return {key: k, pivot: s.pivot};
  }
  return {
    apply, restore,
    restoreAll() { for (const k of [...state.keys()]) restore(k); },
    restoreLayer(layer) { for (const [k, s] of [...state]) if (s.layer === layer) restore(k); },
    has: k => state.has(k), keys: () => [...state.keys()], get: k => state.get(k) || null,
    bounds(k) { const s = state.get(k); return s ? {design: boundsOf(s.targets, false), adjusted: boundsOf(s.targets, true)} : null; },
    designPivot(meshes, id) { const b = boundsOf(targetsFor(meshes, id), true); return b ? b.center.map(v => round(v, 4)) : null; },
  };
}
/* Apply a whole set (mode 'asbuilt') or none (mode 'design') to the loaded meshes of each layer.
   meshesByLayer: {layer: mesh[]}. Elements whose layer is not loaded yet are reported in `pending`. */
function syncAdjuster(adjuster, meshesByLayer, adjustments, mode) {
  const want = new Map();
  if (mode === 'asbuilt') for (const a of adjustments || []) if (a && a.element && !isIdentity(a)) want.set(key(a.element.layer, a.element.id), a);
  for (const k of adjuster.keys()) if (!want.has(k)) adjuster.restore(k);
  const applied = [], pending = [], pivots = {};
  for (const [k, a] of want) {
    const meshes = meshesByLayer[a.element.layer];
    if (!meshes) { pending.push(k); continue; }
    const r = adjuster.apply(meshes, a.element.layer, a.element.id, a);
    if (r) { applied.push(k); pivots[k] = r.pivot; } else pending.push(k);
  }
  return {applied, pending, pivots};
}

/* Current bounds of one element across the runtime tier ({min,max,center} or null). */
function elementBounds(meshes, id) { return boundsOf(targetsFor(meshes, id), true); }

/* Statistics: offset magnitude per group (system, else layer). */
function stats(adjustments, groupOf) {
  const g = groupOf || (a => (a.element && (a.element.system || a.element.layer)) || 'unknown');
  const groups = {};
  for (const a of adjustments || []) {
    const t = a.translation, k = g(a), d = Math.hypot(...t), h = Math.hypot(t[0], t[2]);
    const s = groups[k] || (groups[k] = {n: 0, sum: 0, max: 0, sumH: 0, sumV: 0, sumYaw: 0});
    s.n++; s.sum += d; s.max = Math.max(s.max, d); s.sumH += h; s.sumV += t[1]; s.sumYaw += Math.abs(a.yawDegrees || 0);
  }
  const out = {};
  for (const [k, s] of Object.entries(groups)) out[k] = {n: s.n, meanOffsetM: round(s.sum / s.n, 4), maxOffsetM: round(s.max, 4), meanHorizontalM: round(s.sumH / s.n, 4), meanVerticalM: round(s.sumV / s.n, 4), meanAbsYawDeg: round(s.sumYaw / s.n, 3)};
  return out;
}

return {SCHEMA, FRAME, STATUS, LAYER_KEYS, MAX_OFFSET_M, MAX_YAW_DEG, key, emptyDocument, validateAdjustment, validateDocument,
  createAdjustment, nudge, isIdentity, upsert, remove, find, exportText, multiply, adjustmentMatrix, applyPoint,
  targetsFor, elementBounds, createAdjuster, syncAdjuster, stats};
});
