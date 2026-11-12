/* twin/element-quality.mjs and buildings/grimes/element-quality.json: non-part source objects leave the drawn model,
   storey labels follow the geometry, source records are otherwise untouched, and every viewer applies the overlay.
   Needs Three.js like the other tier tests (THREE_MODULE, tools/node_modules/three, or 'three'). */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {pathToFileURL, fileURLToPath} from 'node:url';
const local = fileURLToPath(new URL('../tools/node_modules/three/build/three.module.js', import.meta.url));
const THREE = await import(process.env.THREE_MODULE ? pathToFileURL(process.env.THREE_MODULE).href : fs.existsSync(local) ? pathToFileURL(local).href : 'three');
const Q = await import('../twin/element-quality.mjs');
const {pruneGlbToLevels, buildSpatialTier} = await import('../twin/xr-spatial-tier.mjs');
const root = new URL('../', import.meta.url), read = path => fs.readFileSync(new URL(path, root), 'utf8'), json = path => JSON.parse(read(path));
const overlay = json(Q.ELEMENT_QUALITY_PATH);
const sample = () => ({a: {levelKey: 'L1'}, anno: {levelKey: 'L1'}, pt: {levelKey: 'L1'}, dup: {levelKey: 'L1'}, up: {levelKey: 'L2'}, dot: {levelKey: 'L1'}, big: {levelKey: 'L1'}});
const small = {_schema: 'twin-element-quality/1', layers: {duct: {hidden: {annotation: ['anno', 'gone'], reference: ['pt'], duplicate: ['dup', 'anno']}, noGeometry: ['dot'], aggregate: ['big'], storey: {L1: ['up', 'a'], L3: [7]}}}};

test('hidden ids leave the sidecar view, storey follows the geometry, the rest is untouched', () => {
  const meta = sample(), r = Q.applyElementQuality(meta, small, 'duct');
  assert.equal(r.applied, true); assert.deepEqual(Object.keys(meta).sort(), ['a', 'big', 'dot', 'up']);
  assert.deepEqual([...r.hidden.keys()].sort(), ['anno', 'dup', 'pt']); assert.equal(r.hidden.get('anno').hidden, 'annotation', 'first reason wins');
  assert.deepEqual(r.counts, {annotation: 1, reference: 1, duplicate: 1, noGeometry: 1, aggregate: 1, storey: 1});
  assert.deepEqual(meta.up, {levelKey: 'L1', sourceLevelKey: 'L2', quality: ['storey']}); assert.deepEqual(meta.a, {levelKey: 'L1'}, 'already on that storey: no flag');
  assert.match(Q.qualityText(meta.up), /Level label disagrees/); assert.equal(Q.qualityText(meta.a), ''); assert.match(Q.hiddenSummary(r.counts), /^3 non-part/);
  assert.equal(Q.applyElementQuality(meta, small, 'duct'), r, 'a cached sidecar object is applied once');
});

test('?flagged=1 keeps every record and only labels it; a missing or unknown overlay changes nothing', () => {
  const meta = sample(), r = Q.applyElementQuality(meta, small, 'duct', {keepHidden: Q.showFlagged('?flagged=1')});
  assert.equal(Object.keys(meta).length, 7); assert.equal(r.hidden.size, 0); assert.equal(Q.isNonPart(meta.anno), true); assert.equal(Q.isNonPart(meta.up), false); assert.equal(meta.anno.hidden, undefined);
  assert.equal(Q.showFlagged('?flagged=0'), false); assert.equal(Q.showFlagged(''), false);
  for (const bad of [null, {}, {_schema: 'other/9', layers: small.layers}, {_schema: small._schema, layers: {}}, {_schema: small._schema, layers: {duct: 'x'}}]) {
    const m = sample(), x = Q.applyElementQuality(m, bad, 'duct');
    assert.equal(x.applied, false); assert.deepEqual(m, sample());
  }
});

test('drawables of hidden ids are removed before a tier is built; nearest known owner decides', async () => {
  const meta = sample(), r = Q.applyElementQuality(meta, small, 'duct'), scene = new THREE.Group();
  const tri = () => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3)); return g; };
  const node = (name, parent = scene) => { const o = new THREE.Group(); o.name = name; parent.add(o); return o; };
  const mesh = (parent, name = '') => { const o = new THREE.Mesh(tri(), new THREE.MeshBasicMaterial()); o.name = name; parent.add(o); return o; };
  const kept = mesh(node('a')), line = new THREE.Line(tri(), new THREE.LineBasicMaterial()); node('anno').add(line);
  const nested = mesh(node('a', node('pt'))), byId = mesh(scene); byId.userData.elementId = 'dup'; const stray = mesh(scene, 'nobody');
  assert.equal(Q.dropHiddenObjects(scene, r.hidden, meta), 2);
  assert.ok(kept.parent && nested.parent && stray.parent, 'kept: owned by a shown id, or unknown'); assert.equal(line.parent, null); assert.equal(byId.parent, null);
  assert.equal(Q.dropHiddenObjects(scene, new Map(), meta), 0);
  const mats = new Map(), materialFor = o => { const k = JSON.stringify(o); if (!mats.has(k)) mats.set(k, new THREE.MeshBasicMaterial({vertexColors: !o.instanced})); return mats.get(k); };
  const tier = await buildSpatialTier(THREE, scene, meta, 'duct', {levels: new Set(['L1']), materialFor});
  assert.equal(tier.stats.elements, 1); assert.equal(tier.stats.unidentifiedObjects, 1, 'the stray mesh is still reported, never drawn as an element');
});

test('the committed overlay matches the sidecars it describes', () => {
  assert.equal(overlay._schema, 'twin-element-quality/1');
  const total = {elements: 0, annotation: 0, reference: 0, duplicate: 0, noGeometry: 0, aggregate: 0, storey: 0};
  for (const [layer, entry] of Object.entries(overlay.layers)) {
    const side = json(overlay.sources[layer].sidecar).elements, seen = new Set();
    assert.equal(Object.keys(side).length, entry.elements, layer); total.elements += entry.elements;
    for (const [reason, ids] of Object.entries(entry.hidden)) for (const id of ids) {
      assert.ok(Object.hasOwn(side, id), `${layer} ${id}`); assert.ok(!seen.has(id), `${layer} ${id} hidden twice`); seen.add(id); total[reason]++;
      if (reason === 'annotation') assert.match(side[id].system, /-ANNO$/);
    }
    for (const key of ['noGeometry', 'aggregate']) for (const id of entry[key]) { assert.ok(Object.hasOwn(side, id) && !seen.has(id), `${layer} ${id}`); total[key]++; }
    for (const [storey, ids] of Object.entries(entry.storey)) for (const id of ids) {
      assert.ok(Object.hasOwn(overlay.floorsViewerY, storey)); assert.ok(!seen.has(id)); assert.notEqual(side[id].levelKey, storey, `${layer} ${id}`); total.storey++;
    }
  }
  const s = overlay.summary;
  assert.deepEqual({elements: s.elements, annotation: s.annotation, reference: s.reference, duplicate: s.duplicate, noGeometry: s.noGeometry, aggregate: s.aggregate, storey: s.storey}, total);
  assert.equal(s.elements, 66620, 'source identities are not removed'); assert.equal(s.hidden, s.annotation + s.reference + s.duplicate); assert.equal(s.shownByDefault, s.elements - s.hidden);
});

test('real duct layer: annotation copies and layout points are cut before decode', () => {
  const meta = json('buildings/grimes/duct.elements.json').elements, bytes = fs.readFileSync(new URL('buildings/grimes/grimes-duct.glb', root));
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), levels = new Set(['L1']);
  const before = pruneGlbToLevels(buffer, meta, levels);
  const r = Q.applyElementQuality(meta, overlay, 'duct'), after = pruneGlbToLevels(buffer, Q.metaForPruning(meta, r.hidden), levels);
  assert.equal(r.hidden.size, overlay.layers.duct.hidden.annotation.length + overlay.layers.duct.hidden.reference.length + overlay.layers.duct.hidden.duplicate.length);
  assert.ok(after.pruned && after.keptMeshNodes < before.keptMeshNodes, `${after.keptMeshNodes} < ${before.keptMeshNodes}`);
  assert.equal(after.keptMeshNodes + after.droppedMeshNodes, before.keptMeshNodes + before.droppedMeshNodes);
  assert.ok(!Object.hasOwn(meta, overlay.layers.duct.hidden.annotation[0]));
});

test('every element viewer applies the overlay, and the explorer keeps all identities', () => {
  for (const page of ['grimes-bim-viewer.html', 'scan-bim.html']) {
    const html = read(page);
    assert.match(html, /from '\.\/twin\/element-quality\.mjs\?v=1'/, page);
    assert.match(html, /applyElementQuality\(meta, await elementQualityOverlay\(\), key, \{keepHidden: SHOW_FLAGGED\}\)/, page);
    assert.match(html, /dropHiddenObjects\(sourceGroup, st\.hidden, meta\);\s*const built = await buildElementRenderTier/, page);
  }
  const xr = read('scan-xr.html');
  assert.match(xr, /element-quality\.mjs\?v=1/); assert.match(xr, /pruneGlbToLevels\(bytes,pruneMeta,P\.levels\)/); assert.match(xr, /metaForPruning\(meta,quality\.hidden\)/);
  const explorer = read('viewer-src/bim-explorer/viewer.mjs');
  assert.equal(explorer.split(',{keepHidden:true})').length - 1, 2, 'full and regional packages keep every record');
  assert.match(explorer, /hiddenKeys=new Set\(flaggedKeys\)/);
  assert.match(read('grimes-bim-explorer.html'), /non-part source objects not drawn/, 'rebuilt page');
});
