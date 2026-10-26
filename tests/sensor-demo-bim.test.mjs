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

test('a layer the Overlay skips on this device: only the anchored elements load (subset), then attach', async () => {
  const {mesh, group} = batch(), scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(60, 1, 0.05, 100);
  camera.position.set(2, 0, 4); camera.lookAt(2, 3, -1); camera.updateMatrixWorld(); camera.updateProjectionMatrix();
  const calls = [], posts = [], realFetch = globalThis.fetch;
  const fire = {...dts, anchor: {...dts.anchor, part: 'grimes-fire-l1-1.glb'}}, fire2 = {...pin, anchor: {...pin.anchor, part: 'grimes-fire-l1-1.glb'}};
  globalThis.fetch = async () => ({ok: true, json: async () => cfg([fire, fire2])});
  try {
    const api = SD.mountBim({THREE, scene, camera, getLayer: () => null, elementInfo: () => null, post: m => posts.push(m), visibility: () => 1, configUrl: 'x.json',
      skipped: k => k === 'fire',
      loadSubset: async (k, ids, parts) => { calls.push([k, ids, parts]); return {group, meshes: [mesh], meta: {'11': {name: 'Pipe11', source_guid: 'g-11'}}, subset: true}; }});
    for (let i = 0; i < 80 && api.inspection().states['p-dts']?.status !== 'attached'; i++) await new Promise(r => setTimeout(r, 10));
    assert.equal(api.inspection().states['p-dts'].status, 'attached');
    assert.equal(api.inspection().states['p-pin'].status, 'attached');
    assert.deepEqual(calls, [['fire', ['11'], ['grimes-fire-l1-1.glb']]], 'one subset request: unique ids, named chunk only');
    assert.deepEqual(api.inspection().subsets.fire, {ids: ['11'], parts: ['grimes-fire-l1-1.glb'], loaded: true, meshes: 1, error: null});
  } finally { globalThis.fetch = realFetch; }
});

test('not skipped on this device (desktop): no subset request, waits for the real layer', async () => {
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(), calls = [], realFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ok: true, json: async () => cfg([{...dts, anchor: {...dts.anchor, part: 'grimes-fire-l1-1.glb'}}])});
  try {
    const api = SD.mountBim({THREE, scene, camera, getLayer: () => null, elementInfo: () => null, post: () => {}, configUrl: 'x.json', skipped: () => false, loadSubset: async (...a) => { calls.push(a); }});
    await new Promise(r => setTimeout(r, 80));
    assert.equal(calls.length, 0);
    assert.equal(api.inspection().states['p-dts'].status, 'pending');
    assert.match(api.inspection().states['p-dts'].reason, /fire layer not loaded/);
  } finally { globalThis.fetch = realFetch; }
});

test('projectPoint (compare page, same frame) matches THREE.PerspectiveCamera projection', () => {
  const cam = new THREE.PerspectiveCamera(75, 16 / 9, 0.05, 2000);
  for (const [pos, q, zoom] of [[[-32.082, 7.233, -14.823], [0.3367, 0.3199, -0.1228, 0.8771], 1], [[1, 2, 3], [0, 0.9397, -0.342, 0], 1.5], [[0, 0, 0], [0, 0, 0, 1], 1]]) {
    cam.position.fromArray(pos); cam.quaternion.fromArray(q).normalize(); cam.zoom = zoom; cam.updateProjectionMatrix(); cam.updateMatrixWorld();
    const pose = {position: pos, quaternion: cam.quaternion.toArray(), fov: 75, zoom};
    for (const p of [[-31, 8, -13], [pos[0] + 1, pos[1] + 0.5, pos[2] - 3], [pos[0] - 2, pos[1] - 1, pos[2] - 6]]) {
      const v = new THREE.Vector3(...p), c = v.clone().applyMatrix4(cam.matrixWorldInverse); v.project(cam);
      const [x, y, f] = SD.projectPoint(p, pose, 16 / 9);
      if (c.z < -0.05) { assert.ok(Math.abs(x - (v.x + 1) / 2) < 2e-4 && Math.abs(y - (1 - v.y) / 2) < 2e-4, JSON.stringify([p, x, y, (v.x + 1) / 2, (1 - v.y) / 2])); assert.equal(f, 1); }
      else assert.equal(f, 0);
    }
  }
});
