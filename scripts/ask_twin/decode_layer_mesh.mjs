#!/usr/bin/env node
/* Decode one element layer GLB into a flat per-element mesh dump for scripts/ask_twin/build_mesh_graph.py.

   READ-ONLY: the GLB is parsed and its Draco geometry is DECODED in memory. Nothing is re-encoded or written back,
   node names (element identity) are only read. The only output is the dump file given on the command line
   (a scratch/work cache, never a published asset).

   Identity follows the viewer (and scripts/ask_twin/index.py): a mesh node belongs to the nearest ancestor (or
   itself) whose node name is a key of the layer sidecar. Positions are transformed by the node hierarchy and the
   viewer placement rotY(pi) + EQUIP_OFFSET, metres, +Y up (same frame as the Ask index boxes).

   Usage: node scripts/ask_twin/decode_layer_mesh.mjs <layer.glb> <layer.elements.json> <out.bin>
   Dump layout (little endian):
     u32 headerLength, header JSON {ids, vOff, tOff, nVerts, nTris}, padding to 4 bytes,
     f32 positions[nVerts*3], u32 triangles[nTris*3] (indices local to the element's vertex range).
   Line primitives (mode 1) contribute vertices but no triangles. Needs the Draco JS decoder from
   tools/node_modules/three (THREE_DRACO_DIR overrides). */
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const require = createRequire(import.meta.url);
const CANDIDATE_DIRS = [
  process.env.THREE_DRACO_DIR,
  path.join(ROOT, 'tools/node_modules/three/examples/jsm/libs/draco/gltf'),
  path.join(process.env.HOME || '', 'Graduate-Project/tools/node_modules/three/examples/jsm/libs/draco/gltf'),
].filter(Boolean);
const DRACO_DIR = CANDIDATE_DIRS.find(d => fs.existsSync(path.join(d, 'draco_decoder.js')));
const EQUIP_OFFSET = [-35.28, -97.16, 28.60];

function compose(t = [0, 0, 0], q = [0, 0, 0, 1], s = [1, 1, 1]) {
  const [x, y, z, w] = q, x2 = x + x, y2 = y + y, z2 = z + z, xx = x * x2, xy = x * y2, xz = x * z2, yy = y * y2, yz = y * z2, zz = z * z2, wx = w * x2, wy = w * y2, wz = w * z2;
  return [(1 - (yy + zz)) * s[0], (xy + wz) * s[0], (xz - wy) * s[0], 0, (xy - wz) * s[1], (1 - (xx + zz)) * s[1], (yz + wx) * s[1], 0,
    (xz + wy) * s[2], (yz - wx) * s[2], (1 - (xx + yy)) * s[2], 0, t[0], t[1], t[2], 1];
}
function mul(a, b) {
  const o = new Array(16);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
  return o;
}
const nodeMatrix = n => n.matrix ? n.matrix.slice() : compose(n.translation, n.rotation, n.scale);
const VIEWER = mul(compose(EQUIP_OFFSET), compose([0, 0, 0], [0, 1, 0, 0]));

function readGlb(file) {
  const b = fs.readFileSync(file);
  if (b.readUInt32LE(0) !== 0x46546c67) throw new Error(file + ': not a GLB');
  const jl = b.readUInt32LE(12), json = JSON.parse(b.subarray(20, 20 + jl).toString('utf8'));
  const binStart = 20 + jl + 8, binLen = b.readUInt32LE(20 + jl);
  return {json, bin: b.subarray(binStart, binStart + binLen)};
}

async function dracoModule() {
  if (!DRACO_DIR) throw new Error('Draco decoder not found (set THREE_DRACO_DIR)');
  const file = path.join(DRACO_DIR, 'draco_decoder.js'), mod = {exports: {}};
  new Function('module', 'exports', 'require', '__dirname', '__filename', fs.readFileSync(file, 'utf8'))(mod, mod.exports, require, DRACO_DIR, file);
  return mod.exports({});
}

function readAccessor(glb, index) {
  const acc = glb.json.accessors[index], bv = glb.json.bufferViews[acc.bufferView];
  const comps = {SCALAR: 1, VEC3: 3}[acc.type];
  const Ctor = {5126: Float32Array, 5125: Uint32Array, 5123: Uint16Array, 5121: Uint8Array}[acc.componentType];
  if (!comps || !Ctor) throw new Error('unexpected accessor ' + acc.type + '/' + acc.componentType);
  const size = Ctor.BYTES_PER_ELEMENT, stride = (bv.byteStride || comps * size) / size, base = (bv.byteOffset || 0) + (acc.byteOffset || 0);
  const raw = new Ctor(glb.bin.buffer.slice(glb.bin.byteOffset + base, glb.bin.byteOffset + base + ((acc.count - 1) * stride + comps) * size));
  const out = new (Ctor === Float32Array ? Float32Array : Uint32Array)(acc.count * comps);
  for (let i = 0; i < acc.count; i++) for (let k = 0; k < comps; k++) out[i * comps + k] = raw[i * stride + k];
  return out;
}

/* -> {pos: Float32Array, tri: Uint32Array|null} in the mesh's local frame */
function decodePrimitive(D, glb, prim) {
  const mode = prim.mode ?? 4;
  const ext = prim.extensions?.KHR_draco_mesh_compression;
  if (!ext) {
    const pos = readAccessor(glb, prim.attributes.POSITION);
    let tri = null;
    if (mode === 4) tri = prim.indices != null ? readAccessor(glb, prim.indices) : Uint32Array.from({length: pos.length / 3}, (_, i) => i);
    return {pos, tri};
  }
  const bv = glb.json.bufferViews[ext.bufferView], bytes = glb.bin.subarray(bv.byteOffset || 0, (bv.byteOffset || 0) + bv.byteLength);
  const dec = new D.Decoder(), buf = new D.DecoderBuffer();
  buf.Init(new Int8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength), bytes.byteLength);
  const isMesh = dec.GetEncodedGeometryType(buf) === D.TRIANGULAR_MESH;
  const geom = isMesh ? new D.Mesh() : new D.PointCloud();
  const st = isMesh ? dec.DecodeBufferToMesh(buf, geom) : dec.DecodeBufferToPointCloud(buf, geom);
  if (!st.ok()) throw new Error('Draco decode failed: ' + st.error_msg());
  const attr = dec.GetAttributeByUniqueId(geom, ext.attributes.POSITION), n = geom.num_points(), arr = new D.DracoFloat32Array();
  dec.GetAttributeFloatForAllPoints(geom, attr, arr);
  const pos = new Float32Array(n * 3);
  for (let i = 0; i < n * 3; i++) pos[i] = arr.GetValue(i);
  let tri = null;
  if (isMesh && mode === 4) {
    const nf = geom.num_faces(), ia = new D.DracoInt32Array();
    tri = new Uint32Array(nf * 3);
    for (let f = 0; f < nf; f++) {
      dec.GetFaceFromMesh(geom, f, ia);
      tri[f * 3] = ia.GetValue(0); tri[f * 3 + 1] = ia.GetValue(1); tri[f * 3 + 2] = ia.GetValue(2);
    }
    D.destroy(ia);
  }
  D.destroy(arr); D.destroy(geom); D.destroy(buf); D.destroy(dec);
  return {pos, tri};
}

async function main() {
  const [glbFile, sideFile, outFile] = process.argv.slice(2);
  if (!outFile) { console.error('usage: decode_layer_mesh.mjs <layer.glb> <layer.elements.json> <out.bin>'); process.exit(2); }
  const t0 = Date.now();
  const D = await dracoModule(), glb = readGlb(glbFile), meta = JSON.parse(fs.readFileSync(sideFile, 'utf8')).elements;
  const nodes = glb.json.nodes, cache = new Map(), parts = new Map();   // id -> [{pos, tri}]
  const decodeMesh = mi => {
    if (!cache.has(mi)) cache.set(mi, glb.json.meshes[mi].primitives.map(p => decodePrimitive(D, glb, p)));
    return cache.get(mi);
  };
  const stack = glb.json.scenes[glb.json.scene || 0].nodes.map(i => [i, VIEWER, null]);
  while (stack.length) {
    const [ni, parentM, parentId] = stack.pop();
    const n = nodes[ni], m = mul(parentM, nodeMatrix(n));
    const id = n.name && Object.prototype.hasOwnProperty.call(meta, n.name) ? n.name : parentId;
    if (n.mesh != null && id) {
      for (const {pos, tri} of decodeMesh(n.mesh)) {
        const w = new Float32Array(pos.length);
        for (let i = 0; i < pos.length; i += 3) {
          const x = pos[i], y = pos[i + 1], z = pos[i + 2];
          w[i] = m[0] * x + m[4] * y + m[8] * z + m[12];
          w[i + 1] = m[1] * x + m[5] * y + m[9] * z + m[13];
          w[i + 2] = m[2] * x + m[6] * y + m[10] * z + m[14];
        }
        if (!parts.has(id)) parts.set(id, []);
        parts.get(id).push({pos: w, tri});
      }
    }
    for (const c of n.children || []) stack.push([c, m, id]);
  }
  const ids = [...parts.keys()].sort(), vOff = [0], tOff = [0];
  let nv = 0, nt = 0;
  for (const id of ids) {
    for (const p of parts.get(id)) { nv += p.pos.length / 3; nt += p.tri ? p.tri.length / 3 : 0; }
    vOff.push(nv); tOff.push(nt);
  }
  const P = new Float32Array(nv * 3), T = new Uint32Array(nt * 3);
  let vi = 0, ti = 0;
  for (const id of ids) {
    let local = 0;
    for (const p of parts.get(id)) {
      P.set(p.pos, vi * 3);
      if (p.tri) { for (let k = 0; k < p.tri.length; k++) T[ti * 3 + k] = p.tri[k] + local; ti += p.tri.length / 3; }
      local += p.pos.length / 3; vi += p.pos.length / 3;
    }
  }
  let header = Buffer.from(JSON.stringify({ids, vOff, tOff, nVerts: nv, nTris: nt, glb: path.basename(glbFile)}));
  const pad = (4 - ((4 + header.length) % 4)) % 4;
  header = Buffer.concat([header, Buffer.alloc(pad, 0x20)]);
  const len = Buffer.alloc(4); len.writeUInt32LE(header.length);
  fs.writeFileSync(outFile, Buffer.concat([len, header, Buffer.from(P.buffer), Buffer.from(T.buffer)]));
  console.error(`[decode] ${path.basename(glbFile)}: ${ids.length} elements, ${nv} vertices, ${nt} triangles, ${((Date.now() - t0) / 1000).toFixed(1)} s`);
}
main().catch(e => { console.error(e.stack || String(e)); process.exit(1); });
