// Decode Draco BIM layer GLBs into a plain float32 triangle soup in the BIM viewer world
// (scene rotation.y = PI, position EQUIP_OFFSET, exactly as scan-bim.html places layers).
// Diagnostic input for scripts/registration_diagnostics.py; source GLBs are only read.
//
//   GLTF_TRANSFORM_MODULES=/opt/homebrew/lib/node_modules/@gltf-transform/cli/node_modules \
//   node scripts/decode_bim_soup.mjs OUT.f32 buildings/grimes/grimes-arch.glb [more.glb ...] [--ymin 3 --ymax 11]
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import path from 'node:path';

const base = process.env.GLTF_TRANSFORM_MODULES || '/opt/homebrew/lib/node_modules/@gltf-transform/cli/node_modules';
const require = createRequire(path.join(base, 'noop.js'));
const { NodeIO } = await import(require.resolve('@gltf-transform/core'));
const { ALL_EXTENSIONS } = await import(require.resolve('@gltf-transform/extensions'));
const draco3d = require('draco3dgltf');

const args = process.argv.slice(2);
const opt = (name, fallback) => { const i = args.indexOf(name); if (i < 0) return fallback; const v = Number(args[i + 1]); args.splice(i, 2); return v; };
const ymin = opt('--ymin', -Infinity), ymax = opt('--ymax', Infinity);
const [out, ...inputs] = args;
if (!out || !inputs.length) { console.error('usage: decode_bim_soup.mjs OUT.f32 in.glb ...'); process.exit(2); }
const EQUIP_OFFSET = [-35.28, -97.16, 28.60];

const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'draco3d.decoder': await draco3d.createDecoderModule() });
const chunks = [];
let triangles = 0;
for (const file of inputs) {
  const doc = await io.read(file);
  for (const node of doc.getRoot().listNodes()) {
    const mesh = node.getMesh(); if (!mesh) continue;
    const m = node.getWorldMatrix(); // column-major 4x4
    for (const prim of mesh.listPrimitives()) {
      if (prim.getMode() !== 4) continue;
      const pos = prim.getAttribute('POSITION'), idx = prim.getIndices();
      const n = idx ? idx.getCount() : pos.getCount();
      const buf = new Float32Array(n * 3); let k = 0; const v = [0, 0, 0];
      const tri = new Float32Array(9);
      for (let i = 0; i < n; i += 3) {
        let keep = true;
        for (let j = 0; j < 3; j++) {
          pos.getElement(idx ? idx.getScalar(i + j) : i + j, v);
          const x = m[0] * v[0] + m[4] * v[1] + m[8] * v[2] + m[12];
          const y = m[1] * v[0] + m[5] * v[1] + m[9] * v[2] + m[13];
          const z = m[2] * v[0] + m[6] * v[1] + m[10] * v[2] + m[14];
          // rotation.y = PI: (x, y, z) -> (-x, y, -z), then EQUIP_OFFSET
          const wx = -x + EQUIP_OFFSET[0], wy = y + EQUIP_OFFSET[1], wz = -z + EQUIP_OFFSET[2];
          if (wy < ymin || wy > ymax) keep = false;
          tri[3 * j] = wx; tri[3 * j + 1] = wy; tri[3 * j + 2] = wz;
        }
        if (keep) { buf.set(tri, k); k += 9; triangles++; }
      }
      chunks.push(buf.subarray(0, k));
    }
  }
  console.error(file, 'triangles so far', triangles);
}
const total = chunks.reduce((a, c) => a + c.length, 0), all = new Float32Array(total);
let o = 0; for (const c of chunks) { all.set(c, o); o += c.length; }
writeFileSync(out, Buffer.from(all.buffer));
console.log(JSON.stringify({ out, triangles, ymin, ymax }));
