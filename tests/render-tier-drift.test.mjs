/* scan-bim.html keeps an inline copy of the element render tier (pages stay self-contained, AGENTS.md invariant 4).
   viewer-src/bim-explorer/render-tier.mjs is the maintained module. This test fails when the batching rules of the two drift:
   the instancing/merge constants, the instance eligibility and reuse keys, and the actual merge-vs-instance decision on
   synthetic geometry. Needs Three.js: THREE_MODULE, else tools/node_modules/three, else 'three'. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {pathToFileURL, fileURLToPath} from 'node:url';
const local = fileURLToPath(new URL('../tools/node_modules/three/build/three.module.js', import.meta.url));
const THREE = await import(process.env.THREE_MODULE ? pathToFileURL(process.env.THREE_MODULE).href : fs.existsSync(local) ? pathToFileURL(local).href : 'three');
const moduleText = fs.readFileSync(new URL('../viewer-src/bim-explorer/render-tier.mjs', import.meta.url), 'utf8');
const html = fs.readFileSync(new URL('../scan-bim.html', import.meta.url), 'utf8');
const copyText = html.slice(html.indexOf('/* Runtime-only draw-call tier.'), html.indexOf('/* ELEMENT DATA HELPERS */'));
const mod = await import('../viewer-src/bim-explorer/render-tier.mjs');
const ctx = vm.createContext({console, setTimeout}); vm.runInContext(copyText, ctx);

const constant = (text, name) => {
  const m = text.match(new RegExp(`\\b${name}\\s*=\\s*(?:Number\\.isFinite\\([^)]*\\)\\s*\\?\\s*[^:]+:\\s*)?(\\d+)`));
  assert.ok(m, `${name} not found`); return Number(m[1]);
};
const line = (text, start) => { const at = text.indexOf(start); assert.ok(at >= 0, `missing: ${start}`); return text.slice(at, text.indexOf('\n', at)).replace(/\s+/g, ''); };

test('scan-bim copy has the same batching constants as render-tier.mjs', () => {
  assert.ok(copyText.length > 1000, 'scan-bim render tier copy located');
  for (const name of ['MAX_VERTICES', 'INSTANCE_REUSE', 'INSTANCE_MIN_TRIANGLES']) assert.equal(constant(copyText, name), constant(moduleText, name), name);
});

test('scan-bim copy uses the same instance eligibility, reuse key and merge-vs-instance rule', () => {
  for (const start of ['part.canInstance =', 'part.reuseKey =', 'const copies =', 'const target =']) assert.equal(line(copyText, start), line(moduleText, start), start);
});

function grid(n) {
  const p = [], idx = [];
  for (let j = 0; j <= n; j++) for (let i = 0; i <= n; i++) p.push(i / n, j / n, 0);
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { const a = j * (n + 1) + i; idx.push(a, a + 1, a + n + 2, a, a + n + 2, a + n + 1); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3)); g.setIndex(idx); return g;
}
async function batches(build, cells, copies) {
  const s = new THREE.Group(), g = grid(cells), mat = new THREE.MeshStandardMaterial(), meta = {};
  for (let i = 0; i < copies; i++) { const id = 'e' + i; meta[id] = {levelKey: 'L1', type: 'fitting'}; const o = new THREE.Mesh(g, mat); o.name = id; o.position.x = i * 2; s.add(o); }
  s.updateMatrixWorld(true);
  const r = await build(THREE, s, meta, 'equipment');
  return {instanced: r.meshes.filter(m => m.isInstancedMesh).length, merged: r.meshes.filter(m => !m.isInstancedMesh).length, triangles: r.stats.renderTriangles};
}
for (const [label, cells, copies, instanced] of [['small reused shape merges', 1, 8, false], ['too few copies merges', 12, 7, false], ['large reused shape instances', 12, 8, true], ['exactly at the triangle threshold instances', 10, 10, true], ['just below the triangle threshold merges', 10, 9, false]]) {
  test(`same decision in both tiers: ${label}`, async () => {
    const a = await batches(mod.buildElementRenderTier, cells, copies), b = await batches(ctx.buildElementRenderTier, cells, copies);
    assert.deepEqual(b, a, 'scan-bim copy and module agree');
    assert.equal(a.instanced > 0, instanced); assert.equal(a.triangles, cells * cells * 2 * copies, 'no triangle lost');
  });
}
