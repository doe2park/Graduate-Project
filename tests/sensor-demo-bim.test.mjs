/* BIM-pane half of the sensor DEMO layer (twin/sensor-demo.js mountBim) on real three@0.169.0 objects shaped like the
   runtime draw-call tier (merged batch with userData.ids + triangle ranges). Checks: identity gate (sidecar name / guid),
   a DTS gradient copy built from exactly that element's triangles with the source batch left byte-identical, and the
   projected anchors posted after a frame.
   THREE_MODULE=/path/to/three/build/three.module.js node --test tests/sensor-demo-bim.test.mjs */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const THREE = await import(process.env.THREE_MODULE ? pathToFileURL(process.env.THREE_MODULE).href : 'three');
const SD = createRequire(import.meta.url)('../twin/sensor-demo.js');

/* two box "elements" merged in one batch: a 4 m pipe along x (id 11) and a small box (id 22) */
function batch() {
  const a = new THREE.BoxGeometry(4, 0.1, 0.1).translate(2, 3, -1), b = new THREE.BoxGeometry(0.3, 0.3, 0.3).translate(-2, 3, 0);
  const pa = a.attributes.position.array, pb = b.attributes.position.array, ia = a.index.array, ib = b.index.array, na = a.attributes.position.count;
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(Float32Array.from([...pa, ...pb]), 3));
  g.setIndex([...ia, ...Array.from(ib, i => i + na)]);
  const mesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial());
  mesh.userData = {ids: ['11', '22'], layer: 'fire', ranges: [{id: '11', start: 0, count: ia.length, vertexStart: 0, vertexCount: na}, {id: '22', start: ia.length, count: ib.length, vertexStart: na, vertexCount: b.attributes.position.count}]};
  const group = new THREE.Group(); group.add(mesh);
  return {mesh, group, triA: ia.length / 3};
}
const cfg = sensors => ({schema: SD.SCHEMA, status: SD.STATUS, sensors});
const dts = {id: 'p-dts', k: 1, type: 'dts', label: 'DTS', reading: {value: 'x'}, anchor: {layer: 'fire', id: '11', name: 'Pipe11', guid: 'g-11', t: 0.8},
  dts: {baselineC: 22, peakC: 31, hotT: 0.4, hotWidth: 0.1, scaleC: [18, 32]}};
const pin = {id: 'p-pin', k: 2, type: 'leak', label: 'Leak', reading: {value: 'dry'}, anchor: {layer: 'fire', id: '11', name: 'Pipe11', t: 0.5, offset: [0, -0.5, 0]}};
const wrong = {id: 'p-wrong', k: 3, type: 'vibration', label: 'V', reading: {value: 'v'}, anchor: {layer: 'fire', id: '22', name: 'Not the sidecar name'}};

async function mount(sensors) {
  const {mesh, group, triA} = batch(), scene = new THREE.Scene(), before = mesh.geometry.attributes.position.array.slice(), beforeIdx = mesh.geometry.index.array.slice();
  scene.add(group);
  const camera = new THREE.PerspectiveCamera(60, 1, 0.05, 100); camera.position.set(2, 0, 4); camera.lookAt(2, 3, -1); camera.updateMatrixWorld(); camera.updateProjectionMatrix();
  const posts = [], meta = {'11': {name: 'Pipe11', source_guid: 'g-11', type: 'Pipe segment'}, '22': {name: 'Box22'}};
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ok: true, json: async () => cfg(sensors)});
  try {
    const api = SD.mountBim({THREE, scene, camera, getLayer: k => k === 'fire' ? {group, meshes: [mesh]} : null, elementInfo: (l, id) => meta[id] || null, post: m => posts.push(m), visibility: () => 0.8, configUrl: 'x.json'});
    for (let i = 0; i < 50 && !(api.inspection().config && Object.keys(api.inspection().states).length === sensors.length && Object.values(api.inspection().states).every(s => s.status !== 'pending')); i++) await new Promise(r => setTimeout(r, 10));
    return {api, posts, scene, mesh, before, beforeIdx, triA, camera};
  } finally { globalThis.fetch = realFetch; }
}

test('attaches to the right element, refuses an identity mismatch, never edits the source batch', async () => {
  const {api, posts, scene, mesh, before, beforeIdx, triA} = await mount([dts, pin, wrong]);
  const st = api.inspection().states;
  assert.equal(st['p-dts'].status, 'attached');
  assert.equal(st['p-pin'].status, 'attached');
  assert.equal(st['p-dts'].element.name, 'Pipe11');
  assert.ok(Math.abs(st['p-dts'].lengthM - 4) < 0.01, 'axis length = the pipe, not the merged batch');
  assert.equal(st['p-wrong'].status, 'refused');
  assert.match(st['p-wrong'].reason, /name differs/);
  assert.deepEqual([...mesh.geometry.attributes.position.array], [...before], 'source positions untouched');
  assert.deepEqual([...mesh.geometry.index.array], [...beforeIdx], 'source index untouched');
  const copy = scene.getObjectByName('sensor-demo (illustrative)').children;
  assert.equal(copy.length, 1, 'one DTS gradient copy');
  assert.equal(copy[0].geometry.index.count / 3, triA, 'exactly the element triangles');
  /* colour comes from a per-fragment lookup along the element axis: hottest at t = hotT, cool at the ends */
  const u = copy[0].material.uniforms, lut = u.lut.value.image.data, n = lut.length / 4, at = t => Array.from(lut.slice(Math.round(t * (n - 1)) * 4, Math.round(t * (n - 1)) * 4 + 3));
  assert.ok(Math.abs(u.axLen.value - 4) < 0.01 && Math.abs(Math.abs(u.axD.value.x) - 1) < 1e-6, 'axis uniforms = the pipe');
  { const i = Math.round(0.4 * (n - 1)); assert.deepEqual(at(0.4), SD.colorAt(SD.dtsValue(i / (n - 1), dts.dts))); }
  assert.ok(at(0.4)[0] > at(0.4)[2] && at(1)[2] > at(1)[0], 'red warm spot, blue end');
  assert.equal(copy[0].material.depthWrite, false);
  const state = posts.filter(m => m.type === SD.MSG.state).pop();
  assert.deepEqual(state.sensors.map(s => s.status), ['attached', 'attached', 'refused']);
});

test('frame(): posts projected anchors, fibre samples and visibility; silent when nothing changed', async () => {
  const {api, posts, camera} = await mount([dts, pin]);
  posts.length = 0; api.frame();
  const f = posts.find(m => m.type === SD.MSG.frame);
  assert.ok(f, 'frame message');
  assert.equal(f.items.length, 2);
  for (const [id, x, y, front, vis] of f.items) { assert.ok(['p-dts', 'p-pin'].includes(id)); assert.equal(front, 1); assert.ok(x > 0 && x < 1 && y > 0 && y < 1, id + ' on screen'); assert.equal(vis, 0.8); }
  const pinY = f.items.find(i => i[0] === 'p-pin')[2], dtsY = f.items.find(i => i[0] === 'p-dts')[2];
  assert.ok(pinY > dtsY - 0.5, 'offset below the pipe projects lower or level');
  assert.equal(f.fibres.length, 1); assert.equal(f.fibres[0][1].length, 33);
  posts.length = 0; api.frame(); assert.equal(posts.length, 0, 'unchanged view: no message');
  camera.position.x += 0.5; camera.updateMatrixWorld(); api.frame();
  assert.equal(posts.filter(m => m.type === SD.MSG.frame).length, 1, 'moved camera: anchors re-projected');
});
