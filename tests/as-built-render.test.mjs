/* As-built adjustments on the real runtime tier of scan-bim.html with Three.js (three@0.169.0, or THREE_MODULE).
   Picks resolve to the same element id at the moved location, never at the old one; Design mode restores bytes exactly. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const THREE = await import(process.env.THREE_MODULE ? pathToFileURL(process.env.THREE_MODULE).href : 'three');
const AsBuilt = createRequire(import.meta.url)('../twin/as-built.js');
const html = fs.readFileSync(new URL('../scan-bim.html', import.meta.url), 'utf8');
const source = html.slice(html.indexOf('/* Runtime-only draw-call tier.'), html.indexOf('/* ELEMENT DATA HELPERS */'));
const ctx = vm.createContext({console, setTimeout}); vm.runInContext(source, ctx);
const meta = {a: {levelKey: 'L1', type: 'light'}, b: {levelKey: 'L1', type: 'light'}};
const mat = new THREE.MeshStandardMaterial({color: 0xffffff});
function quad() { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0], 3)); g.setAttribute('normal', new THREE.Float32BufferAttribute([0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1], 3)); g.setIndex([0, 1, 2, 0, 2, 3]); return g; }
function pick(meshes, x, y) {
  const out = new THREE.Group(); out.add(...meshes); out.updateMatrixWorld(true);
  const h = new THREE.Raycaster(new THREE.Vector3(x, y, 3), new THREE.Vector3(0, 0, -1)).intersectObjects(out.children, false)[0];
  for (const m of meshes) out.remove(m);
  return h ? ctx.resolveElementHit(h.object, h.instanceId, h.faceIndex, h.index) : null;
}
async function tier(instanced) {
  const s = new THREE.Group(), g = quad();
  const n = instanced ? 8 : 2;
  for (let i = 0; i < n; i++) { const o = new THREE.Mesh(instanced ? g : quad(), mat); o.name = i === 0 ? 'a' : 'b'; o.position.x = i * 3; s.add(o); }
  s.updateMatrixWorld(true);
  return (await ctx.buildElementRenderTier(THREE, s, meta, 'lighting')).meshes;
}
for (const instanced of [false, true]) test((instanced ? 'instanced' : 'merged') + ' tier: moved element stays pickable as itself; design restores exactly', async () => {
  const meshes = await tier(instanced);
  assert.equal(meshes.some(m => m.isInstancedMesh), instanced);
  const snap = () => meshes.map(m => Array.from(m.isInstancedMesh ? m.instanceMatrix.array : m.geometry.attributes.position.array));
  const before = snap();
  assert.equal(pick(meshes, .5, .5), 'a'); assert.equal(pick(meshes, 3.5, .5), 'b');
  const adjuster = AsBuilt.createAdjuster();
  const set = [{element: {id: 'a', layer: 'lighting'}, translation: [0, 0.6, 0], yawDegrees: 0}];
  const r = AsBuilt.syncAdjuster(adjuster, {lighting: meshes}, set, 'asbuilt');
  assert.deepEqual(r.applied, ['lighting:a']); assert.deepEqual(r.pivots['lighting:a'].map(v => +v.toFixed(4)), [0.5, 0.5, 0]);
  assert.equal(pick(meshes, .5, 1.4), 'a', 'hit at the adjusted position resolves the same element id');
  assert.equal(pick(meshes, .5, .2), null, 'nothing left at the old position');
  assert.equal(pick(meshes, 3.5, .5), 'b', 'neighbour unaffected');
  assert.ok(meshes.every(m => m.name === 'elements:lighting'), 'runtime mesh names unchanged');
  AsBuilt.syncAdjuster(adjuster, {lighting: meshes}, set, 'design');
  assert.deepEqual(snap(), before, 'bit-exact restore');
  assert.equal(pick(meshes, .5, .2), 'a');
});
