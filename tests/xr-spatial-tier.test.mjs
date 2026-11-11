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

/* ── pruneGlbToLevels: load-time pruning of other floors before Draco decode ── */
const {pruneGlbToLevels} = await import('../twin/xr-spatial-tier.mjs');
function glb(json, bin = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8])) {
  const j = new TextEncoder().encode(JSON.stringify(json)), jp = (j.length + 3) & ~3, out = new Uint8Array(12 + 8 + jp + 8 + bin.length), v = new DataView(out.buffer);
  v.setUint32(0, 0x46546C67, true); v.setUint32(4, 2, true); v.setUint32(8, out.length, true); v.setUint32(12, jp, true); v.setUint32(16, 0x4E4F534A, true);
  out.set(j, 20); out.fill(0x20, 20 + j.length, 20 + jp); v.setUint32(20 + jp, bin.length, true); v.setUint32(24 + jp, 0x004E4942, true); out.set(bin, 28 + jp); return out.buffer;
}
function readGlb(buffer) { const v = new DataView(buffer), n = v.getUint32(12, true); return {json: JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 20, n))), rest: new Uint8Array(buffer, 20 + n), total: v.getUint32(8, true)}; }
function reachableMeshNodes(json) { const out = [], walk = i => { const n = json.nodes[i]; if (Number.isInteger(n.mesh)) out.push(i); (n.children || []).forEach(walk); }; json.scenes.forEach(s => s.nodes.forEach(walk)); return out.sort((a, b) => a - b); }
test('pruneGlbToLevels keeps only the requested floors, leaves indices and the BIN chunk alone', () => {
  const json = {asset: {version: '2.0'}, scene: 0, scenes: [{nodes: [0, 5, 6, 8]}], meshes: [{name: 'm0'}, {name: 'm1'}, {name: 'm2'}, {name: 'm3'}, {name: 'm4'}, {name: 'm5'}], nodes: [
    {name: 'root', children: [1, 2, 3]},
    {name: 'A', mesh: 0},                       // L1 -> kept
    {name: 'B', mesh: 1},                       // L2 -> dropped
    {name: 'C', children: [4]},                 // L2 group: its unnamed child inherits C -> dropped with the group
    {mesh: 2},
    {name: 'D', mesh: 3, children: [7]},        // L2 parent with an L1 child: parent stays as a transform, loses its mesh
    {name: 'nobody', mesh: 4},                  // not in the sidecar -> kept (the tier reports it as unidentified)
    {name: 'A2', mesh: 5},                      // L1 child of D
    {name: 'E'},                                // empty leaf -> dropped
  ]};
  const meta = {A: {levelKey: 'L1'}, B: {levelKey: 'L2'}, C: {levelKey: 'L2'}, D: {levelKey: 'L2'}, A2: {levelKey: 'L1'}, E: {levelKey: 'L1'}};
  const source = glb(json), before = new Uint8Array(source).slice();
  const r = pruneGlbToLevels(source, meta, new Set(['L1']));
  assert.equal(r.pruned, true); assert.deepEqual([r.keptMeshNodes, r.droppedMeshNodes], [3, 3]);
  assert.deepEqual([...new Uint8Array(source)], [...before], 'the input buffer is never modified');
  const out = readGlb(r.buffer), src = readGlb(source);
  assert.equal(out.total, r.buffer.byteLength); assert.equal(r.buffer.byteLength % 4, 0);
  assert.deepEqual([...out.rest], [...src.rest], 'BIN chunk (header + bytes) identical');
  assert.equal(out.json.nodes.length, json.nodes.length, 'no node is re-indexed'); assert.deepEqual(out.json.meshes, json.meshes);
  assert.deepEqual(out.json.scenes[0].nodes, [0, 5, 6]); assert.deepEqual(out.json.nodes[0].children, [1]);
  assert.deepEqual(reachableMeshNodes(out.json), [1, 6, 7]); assert.equal(out.json.nodes[5].mesh, undefined); assert.deepEqual(out.json.nodes[5].children, [7]);
  // nothing to drop, no level filter, or not a GLB: the same buffer comes back
  assert.equal(pruneGlbToLevels(source, meta, new Set(['L1', 'L2'])).buffer, source);
  assert.equal(pruneGlbToLevels(source, meta, null).buffer, source);
  const junk = new Uint8Array(64).buffer; assert.equal(pruneGlbToLevels(junk, meta, new Set(['L1'])).buffer, junk);
  const cyc = glb({scenes: [{nodes: [0]}], nodes: [{name: 'B', mesh: 0, children: [0]}], meshes: [{}]}); assert.equal(pruneGlbToLevels(cyc, meta, new Set(['L1'])).buffer, cyc);
});
test('pruneGlbToLevels on the published duct layer keeps exactly the Level 1 mesh nodes the tier would keep', {skip: !fs.existsSync(new URL('../buildings/grimes/grimes-duct.glb', import.meta.url))}, () => {
  const file = fs.readFileSync(new URL('../buildings/grimes/grimes-duct.glb', import.meta.url)), source = file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength);
  const meta = JSON.parse(fs.readFileSync(new URL('../buildings/grimes/duct.elements.json', import.meta.url), 'utf8')).elements;
  const levelOf = info => { if (info.levelKey && info.levelKey !== 'UNKNOWN') return info.levelKey; const n = String(info.level || '').toUpperCase(); if (/MEZZ/.test(n)) return 'MEZZ'; if (/LOWER|B1/.test(n)) return 'LOWER'; if (/ROOF/.test(n)) return 'ROOF'; const m = n.match(/^LEVEL 0?([1-4])$/); return m ? 'L' + m[1] : 'UNKNOWN'; };
  for (const info of Object.values(meta)) info.levelKey = levelOf(info);   // as scan-xr.html does before loading the GLB
  const levels = new Set(['L1']), src = readGlb(source), r = pruneGlbToLevels(source, meta, levels), out = readGlb(r.buffer);
  const expected = [], walk = (i, inherited) => { const n = src.json.nodes[i], id = Object.hasOwn(meta, n.name || '') ? n.name : inherited; if (Number.isInteger(n.mesh) && (id === null || levels.has(meta[id].levelKey))) expected.push(i); (n.children || []).forEach(c => walk(c, id)); };
  src.json.scenes.forEach(s => s.nodes.forEach(root => walk(root, null)));
  expected.sort((a, b) => a - b);
  assert.equal(r.pruned, true); assert.deepEqual(reachableMeshNodes(out.json), expected);
  assert.equal(r.keptMeshNodes, expected.length); assert.ok(r.droppedMeshNodes > 0 && expected.length > 0);
  assert.equal(Buffer.compare(Buffer.from(out.rest), Buffer.from(src.rest)), 0, 'Draco bytes untouched');
  assert.equal(out.json.nodes.length, src.json.nodes.length); assert.equal(out.json.meshes.length, src.json.meshes.length);
  console.log(`      duct: ${r.keptMeshNodes} mesh nodes kept, ${r.droppedMeshNodes} skipped before decode (${Math.round(100 * r.droppedMeshNodes / (r.keptMeshNodes + r.droppedMeshNodes))}%)`);
});
