/* twin/xr-spatial-tier.mjs: Level filter, spatial cells, baked colours, identity via ray picks, instancing,
   highlight restore and station radius visibility. Synthetic geometry. Needs Three.js:
   THREE_MODULE=/path/to/three/build/three.module.js, else tools/node_modules/three (if present), else 'three'. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {pathToFileURL, fileURLToPath} from 'node:url';
const local = fileURLToPath(new URL('../tools/node_modules/three/build/three.module.js', import.meta.url));
const THREE = await import(process.env.THREE_MODULE ? pathToFileURL(process.env.THREE_MODULE).href : fs.existsSync(local) ? pathToFileURL(local).href : 'three');
const {buildSpatialTier, resolveHit, highlight, applyRadius, bindElementSourceIds} = await import('../twin/xr-spatial-tier.mjs');
const meta = {a: {levelKey: 'L1'}, b: {levelKey: 'L1'}, c: {levelKey: 'L2'}, far: {levelKey: 'L1'}};
const mats = new Map(), materialFor = o => { const k = JSON.stringify(o); if (!mats.has(k)) mats.set(k, new THREE.MeshBasicMaterial({vertexColors: !o.instanced, side: THREE.DoubleSide})); return mats.get(k); };
function tri() { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3)); g.setIndex([0, 1, 2]); return g; }
function add(s, id, g, x, color = 0x3366cc) { const o = new THREE.Mesh(g, new THREE.MeshStandardMaterial({color})); o.name = id; o.position.x = x; s.add(o); return o; }
const pick = (meshes, x, y = .2) => { const g = new THREE.Group(); g.add(...meshes); g.updateMatrixWorld(true); const h = new THREE.Raycaster(new THREE.Vector3(x, y, 2), new THREE.Vector3(0, 0, -1)).intersectObjects(meshes, false)[0]; g.remove(...meshes); return h ? resolveHit(h.object, h.instanceId, h.faceIndex, h.index) : null; };

test('keeps only requested levels, buckets by cell, preserves identity, bakes material colour', async () => {
  const s = new THREE.Group(); add(s, 'a', tri(), 0, 0xff0000); add(s, 'b', tri(), 2, 0x00ff00); add(s, 'c', tri(), 4); add(s, 'far', tri(), 40); add(s, 'unknown', tri(), 6);
  const r = await buildSpatialTier(THREE, s, meta, 'duct', {levels: new Set(['L1']), cellSize: 6, materialFor});
  assert.equal(r.stats.droppedOtherLevels, 1); assert.equal(r.stats.unidentifiedObjects, 1); assert.equal(r.stats.elements, 3);
  assert.equal(r.meshes.length, 2, 'cell 0 and the far cell'); assert.ok(r.meshes.every(m => m.userData.layer === 'duct' && m.material.vertexColors));
  assert.equal(pick(r.meshes, .2), 'a'); assert.equal(pick(r.meshes, 2.2), 'b'); assert.equal(pick(r.meshes, 4.2), null, 'L2 dropped'); assert.equal(pick(r.meshes, 40.2), 'far');
  const m = r.meshes.find(x => x.userData.ids.includes('a')), col = m.geometry.attributes.color, red = new THREE.Color(0xff0000);
  assert.ok(Math.abs(col.getX(0) - red.r) < 1e-6 && col.getY(0) === 0, 'linear material colour baked per vertex');
  assert.ok(m.geometry.attributes.normal, 'normals computed for shading');
  const before = col.array.slice(); highlight(THREE, m, 'b', true); assert.notDeepEqual([...col.array], [...before]); assert.deepEqual([...col.array.slice(0, 9)], [...before.slice(0, 9)], 'neighbour untouched');
  highlight(THREE, m, 'b', false); assert.deepEqual([...col.array], [...before], 'exact restore');
  assert.equal(applyRadius(r.meshes, [0, 0, 0], 14), 1); assert.equal(r.meshes.find(x => x.userData.ids.includes('far')).visible, false);
  assert.equal(applyRadius(r.meshes, [38, 0, 0], 14), 1); assert.equal(applyRadius(r.meshes, [20, 0, 0], 30), 2);
});

test('repeated geometry stays instanced per cell; instance colours highlight and restore', async () => {
  const s = new THREE.Group(), g = tri(); for (let i = 0; i < 8; i++) add(s, i % 2 ? 'b' : 'a', g, i * 2);
  const r = await buildSpatialTier(THREE, s, meta, 'fire', {levels: new Set(['L1']), cellSize: 50, materialFor});
  assert.equal(r.meshes.length, 1); const m = r.meshes[0]; assert.ok(m.isInstancedMesh); assert.equal(m.count, 8); assert.equal(m.material.vertexColors, false);
  assert.equal(pick([m], 2.2), 'b'); assert.equal(pick([m], 4.2), 'a');
  const split = await buildSpatialTier(THREE, s, meta, 'fire', {levels: new Set(['L1']), cellSize: 6, materialFor}); assert.equal(split.meshes.length, 3, 'one batch per cell'); assert.ok(split.meshes.every(x => !x.isInstancedMesh), 'too few repeats inside a cell: merged instead of instanced');
  const c = new THREE.Color(); m.getColorAt(0, c); const base = c.getHex();
  highlight(THREE, m, 'b', true); m.getColorAt(1, c); assert.equal(c.getHexString(), new THREE.Color(0xfbbf24).getHexString()); m.getColorAt(0, c); assert.equal(c.getHex(), base);
  highlight(THREE, m, 'b', false); m.getColorAt(1, c); assert.equal(c.getHex(), base);
});

test('line strips become segments with vertex-range identity; mirrored meshes keep winding', async () => {
  const s = new THREE.Group();
  for (const [i, id] of ['a', 'b'].entries()) { const o = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(1, 0, 0), new THREE.Vector3(1, 1, 0)]), new THREE.LineBasicMaterial()); o.name = id; o.position.x = i * 3; s.add(o); }
  const mir = add(s, 'a', tri(), 10); mir.scale.x = -1;
  const r = await buildSpatialTier(THREE, s, meta, 'conduit', {levels: new Set(['L1']), cellSize: 50, materialFor});
  const line = r.meshes.find(m => m.isLineSegments); assert.equal(line.geometry.index.count, 8);
  const ray = new THREE.Raycaster(new THREE.Vector3(3.5, 0, 2), new THREE.Vector3(0, 0, -1)); ray.params.Line.threshold = .02;
  const h = ray.intersectObject(line, false)[0]; assert.equal(resolveHit(h.object, h.instanceId, h.faceIndex, h.index), 'b');
  const mesh = r.meshes.find(m => m.isMesh && !m.isInstancedMesh); assert.equal(pick([mesh], 9.8), 'a');
  const n = mesh.geometry.attributes.normal; assert.ok(Math.abs(Math.abs(n.getZ(0)) - 1) < 1e-6);
});

test('bindElementSourceIds prefers the exact source name over uniquified runtime names', () => {
  const scene = new THREE.Group(), o = new THREE.Mesh(tri()); o.name = '370418_1'; o.userData.name = '370418'; scene.add(o);
  const gltf = {scene, parser: {associations: new Map([[o, {nodes: 0}]]), json: {nodes: [{name: '370418'}]}}};
  assert.equal(bindElementSourceIds(gltf).boundNodes, 1); assert.equal(o.userData.elementId, '370418');
});
