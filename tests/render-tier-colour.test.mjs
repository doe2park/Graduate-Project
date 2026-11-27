/* Merged-batch colour storage in viewer-src/bim-explorer/render-tier.mjs and the inline copy in scan-bim.html.
   The colour attribute exists for the selection highlight. It is stored as normalized Uint8 (white or Uint8 source colours)
   or Uint16 (Uint16 sources), and stays Float32 for float sources, so no source colour value changes. Highlight must
   restore the stored integers exactly. Needs Three.js: THREE_MODULE, else tools/node_modules/three, else 'three'. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {pathToFileURL, fileURLToPath} from 'node:url';
const local = fileURLToPath(new URL('../tools/node_modules/three/build/three.module.js', import.meta.url));
const THREE = await import(process.env.THREE_MODULE ? pathToFileURL(process.env.THREE_MODULE).href : fs.existsSync(local) ? pathToFileURL(local).href : 'three');
const mod = await import('../viewer-src/bim-explorer/render-tier.mjs');
const html = fs.readFileSync(new URL('../scan-bim.html', import.meta.url), 'utf8');
// typed-array constructors from this realm, so the copy's instanceof checks see the arrays built here (one realm in a browser)
const ctx = vm.createContext({console, setTimeout, Uint8Array, Uint16Array, Uint32Array, Float32Array});
vm.runInContext(html.slice(html.indexOf('/* Runtime-only draw-call tier.'), html.indexOf('/* ELEMENT DATA HELPERS */')), ctx);
const tiers = [['render-tier.mjs', mod], ['scan-bim.html copy', ctx]];
const kind = a => Object.prototype.toString.call(a).slice(8, -1);
const meta = {a: {levelKey: 'L1', type: 't'}, b: {levelKey: 'L1', type: 't'}};

function tri(x, colour) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute([x, 0, 0, x + 1, 0, 0, x, 1, 0], 3)); g.setIndex([0, 1, 2]);
  if (colour) g.setAttribute('color', colour);
  return g;
}
async function merged(t, parts, material) {
  const s = new THREE.Group();
  for (const [id, g] of parts) { const o = new THREE.Mesh(g, material); o.name = id; s.add(o); }
  s.updateMatrixWorld(true);
  const r = await t.buildElementRenderTier(THREE, s, meta, 'x');
  assert.equal(r.meshes.length, 1); return r.meshes[0];
}
function pick(t, mesh, x) {
  const g = new THREE.Group(); g.add(mesh); g.updateMatrixWorld(true);
  const h = new THREE.Raycaster(new THREE.Vector3(x, .2, 2), new THREE.Vector3(0, 0, -1)).intersectObject(mesh, false)[0]; g.remove(mesh);
  return h ? t.resolveElementHit(h.object, h.instanceId, h.faceIndex, h.index) : null;
}

for (const [name, t] of tiers) {
  test(`${name}: white colour is normalized Uint8; highlight changes one element and restores exactly`, async () => {
    const m = await merged(t, [['a', tri(0)], ['b', tri(2)]], new THREE.MeshStandardMaterial({color: 0x80a0c0}));
    const c = m.geometry.attributes.color;
    assert.ok(kind(c.array) === 'Uint8Array'); assert.equal(c.normalized, true); assert.equal(c.itemSize, 3);
    assert.ok([...c.array].every(v => v === 255)); assert.equal(c.getX(0), 1); assert.ok(m.material.vertexColors);
    assert.equal(pick(t, m, .2), 'a'); assert.equal(pick(t, m, 2.2), 'b');
    const before = c.array.slice();
    t.highlightElementRender(m, 'a', true, new THREE.Color(0xfdb515));
    const gold = new THREE.Color(0xfdb515);
    assert.equal(c.getX(0), Math.round(gold.r * 255) / 255); assert.equal(c.getY(2), Math.round(gold.g * 255) / 255);
    assert.deepEqual([...c.array.slice(9)], [...before.slice(9)], 'neighbour untouched');
    t.highlightElementRender(m, 'a', false); assert.deepEqual([...c.array], [...before], 'exact restore');
  });

  test(`${name}: Uint8 RGBA source colours are copied byte for byte`, async () => {
    const src = new THREE.Uint8BufferAttribute([255, 128, 0, 128, 1, 2, 3, 4, 9, 8, 7, 6], 4, true);
    const m = await merged(t, [['a', tri(0, src)]], new THREE.MeshBasicMaterial({vertexColors: true}));
    const c = m.geometry.attributes.color;
    assert.ok(kind(c.array) === 'Uint8Array'); assert.equal(c.normalized, true); assert.equal(c.itemSize, 4);
    assert.deepEqual([...c.array], [...src.array]);
    t.highlightElementRender(m, 'a', true, new THREE.Color('red')); assert.equal(c.getW(0), 128 / 255, 'alpha kept');
    t.highlightElementRender(m, 'a', false); assert.deepEqual([...c.array], [...src.array]);
  });

  test(`${name}: Uint16 and Uint8 sources in one batch are stored as exact Uint16`, async () => {
    const material = new THREE.MeshBasicMaterial({vertexColors: true});
    const u16 = new THREE.Uint16BufferAttribute([65535, 1, 300, 0, 40000, 7, 12345, 2, 65534], 3, true);
    const u8 = new THREE.Uint8BufferAttribute([255, 0, 1, 128, 64, 32, 7, 8, 9], 3, true);
    const m = await merged(t, [['a', tri(0, u16)], ['b', tri(2, u8)]], material);
    const c = m.geometry.attributes.color;
    assert.ok(kind(c.array) === 'Uint16Array'); assert.equal(c.normalized, true);
    assert.deepEqual([...c.array.slice(0, 9)], [...u16.array]);
    assert.deepEqual([...c.array.slice(9)], [...u8.array].map(v => v * 257), 'Uint8 -> Uint16 is exact (x257)');
  });

  test(`${name}: float source colours stay Float32 and unchanged`, async () => {
    const values = [0.1234567, 0.5, 1, 0.000001, 0.25, 0.75, 0.3, 0.6, 0.9];
    const m = await merged(t, [['a', tri(0, new THREE.Float32BufferAttribute(values, 3))]], new THREE.MeshBasicMaterial({vertexColors: true}));
    const c = m.geometry.attributes.color;
    assert.ok(kind(c.array) === 'Float32Array'); assert.equal(c.normalized, false);
    assert.deepEqual([...c.array], [...new Float32Array(values)]);
  });

  test(`${name}: a source colour on a material without vertexColors does not tint and stays Uint8 white`, async () => {
    const m = await merged(t, [['a', tri(0, new THREE.Float32BufferAttribute([1, 0, 0, 1, 0, 0, 1, 0, 0], 3))]], new THREE.MeshBasicMaterial({vertexColors: false}));
    const c = m.geometry.attributes.color;
    assert.ok(kind(c.array) === 'Uint8Array'); assert.equal(c.getY(0), 1);
  });
}
