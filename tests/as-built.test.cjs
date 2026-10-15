/* As-built position adjustments (twin/as-built.js): schema validation, render-time application on the
   instanced and merged runtime tiers, exact restore, identity preservation, statistics and page wiring. */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const A = require('../twin/as-built.js');
const root = path.join(__dirname, '..'), read = f => fs.readFileSync(path.join(root, f), 'utf8');
const bim = read('scan-bim.html'), compare = read('scan-compare.html');

const good = (over = {}) => ({element: {id: '171361', layer: 'lighting', name: '_TEE_Linear Fixture', type: 'Linear fixture', system: 'Lighting'},
  translation: [0.12, 0, -0.04], yawDegrees: 1, evidence: {captureDate: '2026-09-17', scanMode: 'photo', stationIndex: 56, stationLabel: '57/100'},
  author: 'YC', timestamp: '2026-10-14T18:00:00.000Z', note: 'centre of strip', status: 'manual-unsurveyed', ...over});
const doc = list => ({...A.emptyDocument(), adjustments: list});

test('shipped sidecar is a valid, empty document', () => {
  const j = JSON.parse(read('buildings/grimes/as-built-adjustments.json'));
  const v = A.validateDocument(j); assert.ok(v.ok, v.errors.join('; ')); assert.deepEqual(j.adjustments, []);
  assert.match(j._doc, /Not surveyed/); assert.equal(j.frame, 'bim-pane-world-y-up-m');
});

test('schema: required fields, bounds, honest status, duplicates and sidecar membership', () => {
  assert.ok(A.validateDocument(doc([good()])).ok);
  const bad = [
    [{status: 'surveyed'}, /status/], [{author: 'Yoonsung'}, /initials/], [{translation: [0.1, 0]}, /translation/],
    [{translation: [2, 0, 0]}, /exceeds/], [{yawDegrees: 90}, /yawDegrees/], [{timestamp: 'yesterday'}, /timestamp/],
    [{evidence: {captureDate: '17/09/2026', scanMode: 'photo'}}, /captureDate/], [{evidence: {captureDate: '2026-09-17', scanMode: 'lidar'}}, /scanMode/],
    [{element: {id: '1', layer: 'architecture'}}, /layer/], [{element: {id: '', layer: 'lighting'}}, /element\.id/], [{note: 'x'.repeat(501)}, /note/],
    [{pivot: [1, 2]}, /pivot/], [{evidence: {captureDate: '2026-09-17', scanMode: 'photo', stationIndex: -1}}, /stationIndex/],
  ];
  for (const [over, re] of bad) { const v = A.validateDocument(doc([good(over)])); assert.equal(v.ok, false, JSON.stringify(over)); assert.match(v.errors.join(' '), re); }
  assert.match(A.validateDocument(doc([good(), good()])).errors.join(' '), /duplicate element lighting:171361/);
  assert.ok(A.validateDocument(doc([good(), good({element: {id: '171361', layer: 'duct'}})])).ok, 'same id in another layer is a different element');
  assert.match(A.validateDocument(doc([good()]), {elementExists: () => false}).errors.join(' '), /not in the lighting sidecar/);
  for (const d of [null, [], {adjustments: []}, {...A.emptyDocument(), adjustments: 'x'}]) assert.equal(A.validateDocument(d).ok, false);
  const partial = A.validateDocument(doc([good(), good({element: {id: '2', layer: 'lighting'}, author: '?'})]));
  assert.equal(partial.adjustments.length, 1, 'valid entries survive alongside reported invalid ones');
});

test('edits are rounded and immutable; export drops zero adjustments and sorts', () => {
  let a = A.createAdjustment({id: '5', layer: 'duct', info: {name: 'Diffuser', system: 'HVAC'}, evidence: {captureDate: '2026-05-06', scanMode: 'photo', stationIndex: 89, stationLabel: '90/100'}, author: 'YC', now: Date.UTC(2026, 9, 14)});
  assert.equal(a.status, 'manual-unsurveyed'); assert.deepEqual(a.translation, [0, 0, 0]); assert.ok(A.isIdentity(a));
  for (let i = 0; i < 10; i++) a = A.nudge(a, {dx: 0.01});
  assert.deepEqual(a.translation, [0.1, 0, 0], 'ten 1 cm nudges are exactly 10 cm');
  const b = A.nudge(a, {dz: -0.05, dy: 0.01, dyaw: -1});
  assert.deepEqual(a.translation, [0.1, 0, 0], 'nudge does not mutate'); assert.deepEqual(b.translation, [0.1, 0.01, -0.05]); assert.equal(b.yawDegrees, -1);
  let d = A.upsert(A.emptyDocument(), b); d = A.upsert(d, A.createAdjustment({id: '1', layer: 'lighting', author: 'YC'}));
  d = A.upsert(d, A.nudge(b, {dx: 0.01}));
  assert.equal(d.adjustments.length, 2); assert.deepEqual(A.find(d, 'duct:5').translation, [0.11, 0.01, -0.05]);
  const out = JSON.parse(A.exportText(d));
  assert.equal(out.adjustments.length, 1, 'zero adjustment is not exported'); assert.ok(A.validateDocument(out).ok, A.validateDocument(out).errors.join());
  assert.equal(A.remove(d, 'duct:5').adjustments.length, 1);
});

test('matrix: yaw about the element pivot, then translate (Three.js rotation.y convention)', () => {
  const m = A.adjustmentMatrix([0.1, 0.2, 0.3], 90, [10, 5, 20]);
  const near = (p, q) => p.forEach((v, i) => assert.ok(Math.abs(v - q[i]) < 1e-9, p + ' vs ' + q));
  near(A.applyPoint(m, 10, 5, 20), [10.1, 5.2, 20.3]);            // pivot only translates
  near(A.applyPoint(m, 11, 5, 20), [10.1, 5.2, 19.3]);            // +x rotates to -z for +90° (x' = c x + s z, z' = -s x + c z)
  near(A.applyPoint(A.adjustmentMatrix([0, 0, 0], 0, [1, 2, 3]), 4, 5, 6), [4, 5, 6]);
  const I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  assert.deepEqual(A.multiply(I, m), m);
});

/* Fake runtime tier, shaped like buildElementRenderTier output in scan-bim.html */
function mergedMesh() {
  // two elements, no shared vertices: 'a' = vertices 0..2, 'b' = 3..5, 'a' again (second fragment) = 6..8
  const pos = new Float32Array([0, 0, 0, 1, 0, 0, 0, 0, 1, 5, 5, 5, 6, 5, 5, 5, 5, 6, 0, 1, 0, 1, 1, 0, 0, 1, 1]);
  const nor = new Float32Array(27); for (let i = 0; i < 9; i++) nor[i * 3] = 1;
  let spheres = 0;
  return {isMesh: true, userData: {ids: ['a', 'b'], ranges: [{id: 'a', start: 0, count: 3, vertexStart: 0, vertexCount: 3}, {id: 'b', start: 3, count: 3, vertexStart: 3, vertexCount: 3}, {id: 'a', start: 6, count: 3, vertexStart: 6, vertexCount: 3}]},
    geometry: {index: {array: Uint16Array.from([0, 1, 2, 3, 4, 5, 6, 7, 8])}, attributes: {position: {array: pos, itemSize: 3, count: 9}, normal: {array: nor, itemSize: 3, count: 9}},
      computeBoundingBox() {}, computeBoundingSphere() { spheres++; }}, get spheres() { return spheres; }};
}
function instancedMesh() {
  const arr = new Float32Array(48);
  [[1, 2, 3], [4, 5, 6], [7, 8, 9]].forEach((t, i) => arr.set([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, ...t, 1], i * 16));
  return {isInstancedMesh: true, userData: {ids: ['a', 'c', 'a']}, instanceMatrix: {array: arr, needsUpdate: false},
    geometry: {boundingBox: {min: {x: -0.5, y: -0.5, z: -0.5}, max: {x: 0.5, y: 0.5, z: 0.5}}}, computeBoundingSphere() {}, computeBoundingBox() {}};
}

test('merged tier: only the element’s own vertex ranges move; index/ranges (picking identity) untouched; exact restore', () => {
  const m = mergedMesh(), before = Float32Array.from(m.geometry.attributes.position.array), nBefore = Float32Array.from(m.geometry.attributes.normal.array);
  const ranges = JSON.stringify(m.userData.ranges), index = Array.from(m.geometry.index.array);
  const adj = A.createAdjuster();
  const r = adj.apply([m], 'duct', 'a', {translation: [0.1, 0, 0], yawDegrees: 0});
  assert.deepEqual(r.pivot, [0.5, 0.5, 0.5], 'pivot = design bounding-box centre of all fragments');
  const p = m.geometry.attributes.position.array;
  assert.ok(Math.abs(p[0] - 0.1) < 1e-6 && Math.abs(p[18] - 0.1) < 1e-6, 'both fragments of a moved');
  assert.deepEqual(Array.from(p.slice(9, 18)), Array.from(before.slice(9, 18)), 'neighbour b unchanged');
  assert.equal(JSON.stringify(m.userData.ranges), ranges); assert.deepEqual(Array.from(m.geometry.index.array), index);
  assert.ok(m.geometry.attributes.position.needsUpdate); assert.ok(m.spheres > 0, 'bounding sphere recomputed for raycasting');
  // re-apply with a different value is computed from the design snapshot, not cumulatively
  adj.apply([m], 'duct', 'a', {translation: [0.2, 0, 0], yawDegrees: 0});
  assert.ok(Math.abs(p[0] - 0.2) < 1e-6);
  adj.apply([m], 'duct', 'a', {translation: [0, 0, 0], yawDegrees: 90});
  assert.ok(Math.abs(m.geometry.attributes.normal.array[0]) < 1e-6 && Math.abs(m.geometry.attributes.normal.array[2] + 1) < 1e-6, 'normals rotate with yaw');
  const bounds = adj.bounds('duct:a'); assert.deepEqual(bounds.design.center, [0.5, 0.5, 0.5]);
  assert.ok(adj.restore('duct:a'));
  assert.deepEqual(Array.from(p), Array.from(before), 'positions bit-exact after restore');
  assert.deepEqual(Array.from(m.geometry.attributes.normal.array), Array.from(nBefore), 'normals bit-exact after restore');
  assert.equal(adj.restore('duct:a'), false);
});

test('instanced tier: per-instance matrices of that element only; exact restore', () => {
  const m = instancedMesh(), before = Float32Array.from(m.instanceMatrix.array), adj = A.createAdjuster();
  const r = adj.apply([m], 'lighting', 'a', {translation: [0, 0.05, 0], yawDegrees: 0});
  assert.deepEqual(r.pivot, [4, 5, 6], 'pivot = centre of the two instance bounding boxes');
  const a = m.instanceMatrix.array;
  assert.ok(Math.abs(a[13] - 2.05) < 1e-6 && Math.abs(a[32 + 13] - 8.05) < 1e-6);
  assert.deepEqual(Array.from(a.slice(16, 32)), Array.from(before.slice(16, 32)), 'instance c unchanged');
  assert.ok(m.instanceMatrix.needsUpdate);
  adj.restoreAll();
  assert.deepEqual(Array.from(a), Array.from(before));
});

test('Design/As-built toggle: sync applies the set, design mode restores exact originals, unknown layers are pending', () => {
  const merged = mergedMesh(), inst = instancedMesh(), adj = A.createAdjuster();
  const p0 = Float32Array.from(merged.geometry.attributes.position.array), m0 = Float32Array.from(inst.instanceMatrix.array);
  const set = [good({element: {id: 'a', layer: 'duct'}, translation: [0.1, 0.02, 0.03], yawDegrees: 2}), good({element: {id: 'a', layer: 'lighting'}, translation: [0, 0, 0.15], yawDegrees: 0}), good({element: {id: 'zz', layer: 'fire'}})];
  const res = A.syncAdjuster(adj, {duct: [merged], lighting: [inst]}, set, 'asbuilt');
  assert.deepEqual(res.applied.sort(), ['duct:a', 'lighting:a']); assert.deepEqual(res.pending, ['fire:zz']);
  assert.notDeepEqual(Array.from(merged.geometry.attributes.position.array), Array.from(p0));
  for (let i = 0; i < 3; i++) { A.syncAdjuster(adj, {duct: [merged], lighting: [inst]}, set, 'design'); A.syncAdjuster(adj, {duct: [merged], lighting: [inst]}, set, 'asbuilt'); }
  A.syncAdjuster(adj, {duct: [merged], lighting: [inst]}, set, 'design');
  assert.deepEqual(Array.from(merged.geometry.attributes.position.array), Array.from(p0), 'merged restored exactly after repeated toggles');
  assert.deepEqual(Array.from(inst.instanceMatrix.array), Array.from(m0), 'instanced restored exactly after repeated toggles');
  assert.deepEqual(adj.keys(), []);
  // removing one element from the set restores only that one
  A.syncAdjuster(adj, {duct: [merged], lighting: [inst]}, set, 'asbuilt');
  A.syncAdjuster(adj, {duct: [merged], lighting: [inst]}, set.slice(1), 'asbuilt');
  assert.deepEqual(Array.from(merged.geometry.attributes.position.array), Array.from(p0)); assert.deepEqual(adj.keys(), ['lighting:a']);
});

test('statistics per system: mean / max offset, horizontal vs vertical, yaw', () => {
  const s = A.stats([good({translation: [0.3, 0, 0.4]}), good({translation: [0, 0.1, 0], yawDegrees: -2}), good({element: {id: '9', layer: 'duct', system: 'HVAC'}, translation: [0.1, 0, 0]})]);
  assert.deepEqual(s.Lighting, {n: 2, meanOffsetM: 0.3, maxOffsetM: 0.5, meanHorizontalM: 0.25, meanVerticalM: 0.05, meanAbsYawDeg: 1.5});
  assert.equal(s.HVAC.n, 1);
});

test('wiring: render-time only, GLBs untouched, honest labels, toggle and export/import UI', () => {
  assert.match(bim, /<script src="twin\/as-built\.js"><\/script>/); assert.match(compare, /<script src="twin\/as-built\.js"><\/script>/);
  assert.match(bim, /AsBuilt\.syncAdjuster\(/); assert.match(bim, /grimes-asbuilt/);
  assert.doesNotMatch(bim + compare, /GLTFExporter|as-built.*\.glb/i);
  assert.match(compare, /Design \(BIM\)/); assert.match(compare, /As-built adjusted/);
  assert.match(compare, /manual, not surveyed/); assert.match(compare, /id="asBuiltBadge"/);
  assert.match(compare, /buildings\/grimes\/as-built-adjustments\.json/);
  assert.match(compare, /type="file"/); assert.match(compare, /AsBuilt\.exportText\(/); assert.match(compare, /AsBuilt\.validateDocument\(/);
  for (const label of ['−5', '−1', '+1', '+5']) assert.ok(compare.includes(label), label);
});
