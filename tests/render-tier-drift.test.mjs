/* One element render tier for the explorer and the BIM pane. viewer-src/bim-explorer/render-tier.mjs is bundled into
   grimes-bim-explorer.html and imported directly by scan-bim.html (until 2026-11-27 scan-bim carried an inline copy that had
   drifted: it lacked INSTANCE_MIN_TRIANGLES). This test fails if scan-bim stops importing the module, re-introduces a local
   copy of any tier function, or the module loses the batching rule (merge-vs-instance decision on synthetic geometry).
   Needs Three.js: THREE_MODULE, else tools/node_modules/three, else 'three'. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {pathToFileURL, fileURLToPath} from 'node:url';
const local = fileURLToPath(new URL('../tools/node_modules/three/build/three.module.js', import.meta.url));
const THREE = await import(process.env.THREE_MODULE ? pathToFileURL(process.env.THREE_MODULE).href : fs.existsSync(local) ? pathToFileURL(local).href : 'three');
const mod = await import('../viewer-src/bim-explorer/render-tier.mjs');
const html = fs.readFileSync(new URL('../scan-bim.html', import.meta.url), 'utf8');
const NAMES = ['bindElementSourceIds', 'buildElementRenderTier', 'resolveElementHit', 'highlightElementRender', 'findElementSelection', 'releaseElementSource', 'setElementRenderVisible'];

test('scan-bim imports the render tier module and defines no copy of it', () => {
  const m = html.match(/import\s*\{([^}]*)\}\s*from\s*'\.\/viewer-src\/bim-explorer\/render-tier\.mjs(?:\?v=\d+)?';/);
  assert.ok(m, 'static import of ./viewer-src/bim-explorer/render-tier.mjs');
  assert.deepEqual(m[1].split(',').map(x => x.trim()).sort(), [...NAMES].sort());
  for (const name of NAMES) {
    assert.doesNotMatch(html, new RegExp(`function\\s+${name}\\s*\\(`), `scan-bim defines ${name} itself`);
    assert.equal(typeof mod[name], 'function', `module exports ${name}`);
  }
  assert.ok(html.indexOf("from './viewer-src/bim-explorer/render-tier.mjs") < html.indexOf('buildElementRenderTier(THREE'), 'import precedes use');
});

test('the module keeps the instancing constants scan-bim relied on', () => {
  const text = fs.readFileSync(new URL('../viewer-src/bim-explorer/render-tier.mjs', import.meta.url), 'utf8');
  assert.match(text, /MAX_VERTICES = 180000, INSTANCE_REUSE = 8;/);
  assert.match(text, /options\.instanceMinTriangles\) \? options\.instanceMinTriangles : 2000;/);
});

function grid(n) {
  const p = [], idx = [];
  for (let j = 0; j <= n; j++) for (let i = 0; i <= n; i++) p.push(i / n, j / n, 0);
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { const a = j * (n + 1) + i; idx.push(a, a + 1, a + n + 2, a, a + n + 2, a + n + 1); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3)); g.setIndex(idx); return g;
}
async function batches(cells, copies) {
  const s = new THREE.Group(), g = grid(cells), mat = new THREE.MeshStandardMaterial(), meta = {};
  for (let i = 0; i < copies; i++) { const id = 'e' + i; meta[id] = {levelKey: 'L1', type: 'fitting'}; const o = new THREE.Mesh(g, mat); o.name = id; o.position.x = i * 2; s.add(o); }
  s.updateMatrixWorld(true);
  const r = await mod.buildElementRenderTier(THREE, s, meta, 'equipment');   // scan-bim calls it with these four arguments
  return {instanced: r.meshes.filter(m => m.isInstancedMesh).length, triangles: r.stats.renderTriangles};
}
for (const [label, cells, copies, instanced] of [['small reused shape merges', 1, 8, false], ['too few copies merges', 12, 7, false], ['large reused shape instances', 12, 8, true], ['exactly at the triangle threshold instances', 10, 10, true], ['just below the triangle threshold merges', 10, 9, false]]) {
  test(`default batching (as scan-bim calls it): ${label}`, async () => {
    const a = await batches(cells, copies);
    assert.equal(a.instanced > 0, instanced); assert.equal(a.triangles, cells * cells * 2 * copies, 'no triangle lost');
  });
}
