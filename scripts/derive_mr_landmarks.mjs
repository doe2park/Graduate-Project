#!/usr/bin/env node
/* Derive BIM-frame coordinates for the Quest MR alignment landmarks (buildings/grimes/mr-landmarks.json).

   READ-ONLY: GLBs are parsed and their Draco geometry is DECODED in memory to measure element bounding boxes.
   Nothing is re-encoded or written back; node names (element identity) are only read.

   Frame = the BIM viewer world used by scan-bim.html / scan-xr.html: the GLB scene (its own root node carries the
   Revit Z-up -> Y-up rotation and feet -> metres scale) placed with rotY(pi) + EQUIP_OFFSET (-35.28, -97.16, 28.60).

   Usage:
     node scripts/derive_mr_landmarks.mjs --list            # print candidate elements near the L1 entrance
     node scripts/derive_mr_landmarks.mjs --write           # (re)write buildings/grimes/mr-landmarks.json
   Needs the Draco JS decoder from tools/node_modules/three (THREE_DRACO_DIR overrides). */
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const DRACO_DIR = process.env.THREE_DRACO_DIR || path.join(ROOT, 'tools/node_modules/three/examples/jsm/libs/draco/gltf');
const EQUIP_OFFSET = [-35.28, -97.16, 28.60];

/* ── small mat4 helpers (column-major, glTF convention) ── */
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
/* viewer placement: T(EQUIP_OFFSET) * rotY(pi) */
const VIEWER = mul(compose(EQUIP_OFFSET), compose([0, 0, 0], [0, 1, 0, 0]));

function readGlb(file) {
  const b = fs.readFileSync(file);
  if (b.readUInt32LE(0) !== 0x46546c67) throw new Error(file + ': not a GLB');
  const jl = b.readUInt32LE(12), json = JSON.parse(b.subarray(20, 20 + jl).toString('utf8'));
  const binStart = 20 + jl + 8, binLen = b.readUInt32LE(20 + jl);
  return {json, bin: b.subarray(binStart, binStart + binLen)};
}

let draco = null;
async function dracoModule() {
  if (draco) return draco;
  // three's package.json is "type":"module", so require() would treat the UMD decoder as ESM: evaluate it as a script.
  const mod = {exports: {}};
  new Function('module', 'exports', 'require', '__dirname', '__filename', fs.readFileSync(path.join(DRACO_DIR, 'draco_decoder.js'), 'utf8'))(mod, mod.exports, require, DRACO_DIR, path.join(DRACO_DIR, 'draco_decoder.js'));
  draco = await mod.exports({});
  return draco;
}
function decodePositions(D, glb, prim) {
  const ext = prim.extensions?.KHR_draco_mesh_compression;
  if (!ext) {   // plain (uncompressed) primitive, e.g. lines: read the FLOAT VEC3 accessor as stored
    const acc = glb.json.accessors[prim.attributes.POSITION], bv = glb.json.bufferViews[acc.bufferView];
    if (acc.componentType !== 5126 || acc.type !== 'VEC3') throw new Error('unexpected POSITION accessor');
    const stride = (bv.byteStride || 12) / 4, base = (bv.byteOffset || 0) + (acc.byteOffset || 0), out = new Float32Array(acc.count * 3);
    const f = new Float32Array(glb.bin.buffer.slice(glb.bin.byteOffset + base, glb.bin.byteOffset + base + ((acc.count - 1) * stride + 3) * 4));
    for (let i = 0; i < acc.count; i++) for (let k = 0; k < 3; k++) out[i * 3 + k] = f[i * stride + k];
    return out;
  }
  const bv = glb.json.bufferViews[ext.bufferView], bytes = glb.bin.subarray(bv.byteOffset || 0, (bv.byteOffset || 0) + bv.byteLength);
  const dec = new D.Decoder(), buf = new D.DecoderBuffer();
  buf.Init(new Int8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength), bytes.byteLength);
  const mesh = new D.Mesh(), st = dec.DecodeBufferToMesh(buf, mesh);
  if (!st.ok()) throw new Error('Draco decode failed: ' + st.error_msg());
  const attr = dec.GetAttributeByUniqueId(mesh, ext.attributes.POSITION), n = mesh.num_points(), arr = new D.DracoFloat32Array();
  dec.GetAttributeFloatForAllPoints(mesh, attr, arr);
  const out = new Float32Array(n * 3); for (let i = 0; i < n * 3; i++) out[i] = arr.GetValue(i);
  D.destroy(arr); D.destroy(mesh); D.destroy(buf); D.destroy(dec);
  return out;
}

/* Bounding boxes (viewer world) of the elements selected by want(id, info). Identity = nearest ancestor node name in the sidecar. */
async function elementBoxes(glbFile, meta, want) {
  const D = await dracoModule(), glb = readGlb(path.join(ROOT, glbFile)), nodes = glb.json.nodes, boxes = new Map();
  const visit = (ni, parentM, parentId) => {
    const n = nodes[ni], m = mul(parentM, nodeMatrix(n));
    const id = n.name && Object.prototype.hasOwnProperty.call(meta, n.name) ? n.name : parentId;
    if (n.mesh != null && id && want(id, meta[id])) {
      for (const prim of glb.json.meshes[n.mesh].primitives) {
        const p = decodePositions(D, glb, prim);
        let b = boxes.get(id); if (!b) boxes.set(id, b = {min: [Infinity, Infinity, Infinity], max: [-Infinity, -Infinity, -Infinity]});
        for (let i = 0; i < p.length; i += 3) {
          const x = p[i], y = p[i + 1], z = p[i + 2];
          const w = [m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13], m[2] * x + m[6] * y + m[10] * z + m[14]];
          for (let k = 0; k < 3; k++) { if (w[k] < b.min[k]) b.min[k] = w[k]; if (w[k] > b.max[k]) b.max[k] = w[k]; }
        }
      }
    }
    for (const c of n.children || []) visit(c, m, id);
  };
  for (const r of glb.json.scenes[glb.json.scene || 0].nodes) visit(r, VIEWER, null);
  return boxes;
}
const r3 = v => v.map(x => Math.round(x * 1000) / 1000);
const centre = b => b.min.map((v, k) => (v + b.max[k]) / 2);
const size = b => b.max.map((v, k) => v - b.min[k]);
const loadMeta = f => JSON.parse(fs.readFileSync(path.join(ROOT, f), 'utf8')).elements;

/* ── Curated landmarks ──
   Each point is read from one element's bounding box (axis-aligned in the BIM world: these walls, mullions and
   columns are thin along x or z). kind: 'xz' = vertical edge / face point (any touch height; fixes plan position),
   'y' = floor touch (fixes height only), 'check' = not used in the fit; after alignment the user compares the BIM
   element with the installed one. pick: [x, z] selectors 'min' | 'max' | 'mid' on the element box; y comes from the
   area floor datum (+ touchHeight for xz). Selection evidence is in the descriptions; NONE of these was checked on site. */
const LAYERS = {
  enclosure: {glb: 'interior/enclosure-l1.glb', json: 'interior/enclosure-l1.elements.json'},
  structural: {glb: 'buildings/grimes/grimes-structural.glb', json: 'buildings/grimes/structural.elements.json'},
  equipment: {glb: 'buildings/grimes/grimes-equipment.glb', json: 'buildings/grimes/elements.json'},
  fire: {glb: ['buildings/grimes/grimes-fire-l1-1.glb', 'buildings/grimes/grimes-fire-l1-2.glb'], json: 'buildings/grimes/fire.elements.json'},
};
const AREAS = [
  {id: 'l1-auditorium-foyer', level: 'L1', floorY: 5.25,
    name: 'Level 1 · foyer outside the auditorium doors (open ceiling)',
    why: 'Likely the Oct 18 open-ceiling check area: a row of exposed upright sprinkler heads (VK300) over the foyer between two round concrete columns, directly north of the raked auditorium floor (Floor 128625, z -22.1 to -7.15). Inferred from BIM, confirm on site.',
    floorNote: 'Level 1 datum y = 5.25 m (base of the L1 column and wall segments here). The foyer floor finish was not verified.',
    points: [
      {id: 'A', kind: 'xz', layer: 'structural', element: '130415', pick: ['min', 'mid'], label: 'East round column · face toward the other column',
        text: 'Round concrete column (20" dia., BIM 130415) on the east side of the foyer. Touch its surface at the point that faces the west column across the foyer, at any height.'},
      {id: 'B', kind: 'xz', layer: 'structural', element: '130413', pick: ['max', 'mid'], label: 'West round column · face toward the other column',
        text: 'Round concrete column (20" dia., BIM 130413) on the west side, ~8.3 m from A. Touch the point that faces column A, at any height.'},
      {id: 'C', kind: 'xz', layer: 'enclosure', element: '14933', pick: ['max', 'min'], label: 'West wall · outside corner nearest the auditorium',
        text: 'Outside (convex) corner of the thick wall north-east of column B (BIM wall 14933), the corner nearer the auditorium. Vertical edge, any height.'},
      {id: 'D', kind: 'xz', layer: 'enclosure', element: '14925', pick: ['min', 'min'], label: 'East wall · outside corner nearest the auditorium',
        text: 'Outside corner of the wall north-east of column A (BIM wall 14925), the corner nearer the auditorium. Vertical edge, any height.'},
      {id: 'F', kind: 'y', label: 'Floor', text: 'Touch the floor anywhere in the foyer (not on a mat or ramp).'},
    ],
    checks: [
      {id: 'S1', layer: 'fire', element: '278545', label: 'Upright sprinkler head (centre of the exposed row)', text: 'Exposed upright head VK300 (BIM 278545). Stand under the real head, hold the tip directly below its deflector, trigger.'},
      {id: 'S2', layer: 'fire', element: '278541', label: 'Upright sprinkler head (west)', text: 'Exposed upright head VK300 (BIM 278541), west end of the row.'},
      {id: 'S3', layer: 'fire', element: '278537', label: 'Upright sprinkler head (east)', text: 'Exposed upright head VK300 (BIM 278537), east end of the row.'},
      {id: 'G1', layer: 'equipment', element: '15365', label: '24×24 supply diffuser, mark 672', text: '24×24 supply diffuser (BIM 15365, mark 672), ~2.2 m north of the foyer\'s north wall in BIM. Hold the tip directly below its centre. If it is not in the same room, skip it and use the east-entrance check.'},
    ]},
  {id: 'l1-east-entrance', level: 'L1', floorY: 5.25,
    name: 'Level 1 · east entrance (double glass door 140)',
    why: 'Exterior double door (BIM door mark 140, "EXTERIOR, CR, PANIC") in the east curtain wall: clean frame edges and a concealed pendent head 0.75 m inside the door.',
    floorNote: 'Level 1 datum y = 5.25 m (door threshold / vestibule floor 7920 top at 5.248).',
    points: [
      {id: 'A', kind: 'xz', layer: 'enclosure', element: '18089', pick: ['min', 'max'], label: 'Door 140 · frame edge A (inside face)',
        text: 'Inside face of the door-frame mullion (BIM 18089) at the edge of the opening, on the side away from the small closet. Vertical edge, any height.'},
      {id: 'B', kind: 'xz', layer: 'enclosure', element: '18097', pick: ['min', 'min'], label: 'Door 140 · frame edge B (inside face)',
        text: 'Inside face of the other frame mullion (BIM 18097), 1.83 m from A, on the closet side.'},
      {id: 'C', kind: 'xz', layer: 'enclosure', element: '26157', pick: ['min', 'min'], label: 'Closet · outside corner',
        text: 'Outside corner of the small closet next to the door (walls 26157/26161), the corner farthest from the door and nearest the corridor. Vertical edge, any height.'},
      {id: 'D', kind: 'xz', layer: 'enclosure', element: '25593', pick: ['max', 'min'], label: 'Corridor doorway · jamb corner west of the closet',
        text: 'Corridor-side corner of the short wall (BIM 25593) that forms the far jamb of the opening just west of the closet, ~3 m from the door. Vertical edge, any height.'},
      {id: 'E', kind: 'xz', layer: 'enclosure', element: '25723', pick: ['min', 'min'], label: 'Corridor north wall · west end (~9.7 m in)',
        text: 'Where the corridor\'s north wall ends ~9.7 m in from the door (BIM wall 25723 corner). Far point: improves the heading. Skip it if the corner is not exposed.'},
      {id: 'F', kind: 'y', label: 'Floor', text: 'Touch the floor just inside the door (not on the threshold or a mat).'},
    ],
    checks: [
      {id: 'S1', layer: 'fire', element: '279994', label: 'Concealed pendent head 0.75 m inside the door', text: 'Concealed pendent head VK462 (BIM 279994). Hold the tip directly below the cover plate centre, trigger.'},
      {id: 'G1', layer: 'equipment', element: '15169', label: '24×24 supply diffuser, mark 55', text: '24×24 supply diffuser (BIM 15169, mark 55). Directly below its centre.'},
      {id: 'G2', layer: 'equipment', element: '15165', label: '24×24 supply diffuser, mark 33', text: '24×24 supply diffuser (BIM 15165, mark 33). Directly below its centre.'},
    ]},
];
const TOUCH_HEIGHT = 1.0;   // suggested touch height above the floor for 'xz' points (display only; height is free)

async function boxesFor(layerKey, ids) {
  const L = LAYERS[layerKey], meta = loadMeta(L.json), want = new Set(ids), out = new Map();
  for (const g of [].concat(L.glb)) for (const [k, v] of await elementBoxes(g, meta, id => want.has(id))) {
    const b = out.get(k); if (!b) out.set(k, v); else for (let i = 0; i < 3; i++) { b.min[i] = Math.min(b.min[i], v.min[i]); b.max[i] = Math.max(b.max[i], v.max[i]); }
  }
  for (const id of ids) if (!out.has(id)) throw new Error(`${layerKey} element ${id} has no geometry`);
  return {boxes: out, meta};
}
const sel = (b, axis, how) => how === 'min' ? b.min[axis] : how === 'max' ? b.max[axis] : (b.min[axis] + b.max[axis]) / 2;
const sha = async f => (await import('node:crypto')).createHash('sha256').update(fs.readFileSync(path.join(ROOT, f))).digest('hex');

async function build() {
  const byLayer = {};
  for (const a of AREAS) for (const p of [...a.points, ...a.checks]) if (p.layer) (byLayer[p.layer] ||= new Set()).add(p.element);
  const B = {};
  for (const [k, ids] of Object.entries(byLayer)) B[k] = await boxesFor(k, [...ids]);
  const r = v => Math.round(v * 1000) / 1000;
  const areas = AREAS.map(a => ({
    id: a.id, level: a.level, name: a.name, why: a.why, floorY: a.floorY, floorNote: a.floorNote,
    points: a.points.map(p => {
      const out = {id: p.id, kind: p.kind, label: p.label, text: p.text};
      if (p.kind === 'y') out.bim = [null, a.floorY, null];
      else {
        const b = B[p.layer].boxes.get(p.element), info = B[p.layer].meta[p.element];
        out.bim = [r(sel(b, 0, p.pick[0])), r(a.floorY + TOUCH_HEIGHT), r(sel(b, 2, p.pick[1]))];
        out.source = {layer: p.layer, element: p.element, name: info.name, category: info.category, pick: p.pick, box: {min: b.min.map(r), max: b.max.map(r)}};
      }
      return out;
    }),
    checks: a.checks.map(c => {
      const b = B[c.layer].boxes.get(c.element), info = B[c.layer].meta[c.element];
      return {id: c.id, label: c.label, text: c.text, bim: [r((b.min[0] + b.max[0]) / 2), r(b.min[1]), r((b.min[2] + b.max[2]) / 2)],
        source: {layer: c.layer, element: c.element, name: info.name, description: info.fabrication?.Description || info.revit_type || null, mark: info.mark || null, box: {min: b.min.map(r), max: b.max.map(r)}}};
    }),
  }));
  const inputs = {};
  for (const L of Object.values(LAYERS)) for (const f of [...[].concat(L.glb), L.json]) inputs[f] = await sha(f);
  return {
    schema: 'grimes-mr-landmarks/1', building: 'grimes',
    frame: 'BIM viewer world (scan-bim / scan-xr): GLB scene placed with rotY(pi) + EQUIP_OFFSET (-35.28, -97.16, 28.60), metres, Y up',
    status: 'BIM-derived candidates, not verified on site; positions are design (BIM) positions, not surveyed',
    derivedWith: 'node scripts/derive_mr_landmarks.mjs --write (reads GLB node names and decodes Draco in memory; nothing re-encoded)',
    kinds: {xz: 'vertical edge or face point: plan position only, touch at any height (bim[1] = suggested touch height)', y: 'floor touch: height only', check: 'not fitted; compared after alignment'},
    inputs, areas};
}

async function candidates() {
  const enc = loadMeta('interior/enclosure-l1.elements.json'), eq = loadMeta('buildings/grimes/elements.json'),
    st = loadMeta('buildings/grimes/structural.elements.json'), fire = loadMeta('buildings/grimes/fire.elements.json'),
    floors = loadMeta('interior/floors-l1.elements.json');
  const doors = await elementBoxes('interior/enclosure-l1.glb', enc, (id, i) => i.category === 'Doors');
  const diff = await elementBoxes('buildings/grimes/grimes-equipment.glb', eq, (id, i) => i.levelKey === 'L1' && /^Diffuser - (Supply|Return) \(I\)$/.test(i.name || ''));
  const cols = await elementBoxes('buildings/grimes/grimes-structural.glb', st, (id, i) => i.levelKey === 'L1' && /column/i.test(i.type || ''));
  const heads = new Map();
  for (const f of ['buildings/grimes/grimes-fire-l1-1.glb', 'buildings/grimes/grimes-fire-l1-2.glb'])
    for (const [k, v] of await elementBoxes(f, fire, (id, i) => i.levelKey === 'L1' && /Pendent|Upright/.test(i.fabrication?.Description || ''))) heads.set(k, v);
  const floorBoxes = await elementBoxes('interior/floors-l1.glb', floors, () => true);
  return {doors, diff, cols, heads, floorBoxes, meta: {enc, eq, st, fire, floors}};
}

function nearest(map, p, n = 6) {
  return [...map.entries()].map(([id, b]) => ({id, b, d: Math.hypot(centre(b)[0] - p[0], centre(b)[2] - p[2])})).sort((a, b) => a.d - b.d).slice(0, n);
}

const args = new Set(process.argv.slice(2));
const MAIN = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (MAIN && args.has('--write')) {
  const out = await build(), file = path.join(ROOT, 'buildings/grimes/mr-landmarks.json');
  fs.writeFileSync(file, JSON.stringify(out, null, 1) + '\n');
  console.log('wrote', path.relative(ROOT, file), out.areas.map(a => a.id + ': ' + a.points.length + ' points, ' + a.checks.length + ' checks').join(' · '));
}
if (MAIN && !args.has('--write')) {
const C = await candidates();
const entrance = [...C.doors.entries()].filter(([id]) => C.meta.enc[id].mark === '140');
if (!entrance.length) throw new Error('door mark 140 (EXTERIOR, CR, PANIC) not found');
const eb = entrance.map(([, b]) => b), doorBox = {min: [0, 1, 2].map(k => Math.min(...eb.map(b => b.min[k]))), max: [0, 1, 2].map(k => Math.max(...eb.map(b => b.max[k])))};
const dc = centre(doorBox);

{
  const show = (label, list, metaOf) => { console.log('\n' + label); for (const x of list) console.log(' ', x.id, metaOf(x.id), 'centre', r3(centre(x.b)), 'size', r3(size(x.b)), 'dXZ', x.d.toFixed(2)); };
  console.log('door 140 union box', r3(doorBox.min), r3(doorBox.max), 'centre', r3(dc));
  show('doors', nearest(C.doors, dc, 8), id => [C.meta.enc[id].name, C.meta.enc[id].mark, C.meta.enc[id].comments].join(' | '));
  show('columns', nearest(C.cols, dc, 8), id => [C.meta.st[id].name, C.meta.st[id].revit_type].join(' | '));
  show('24x24 diffusers', nearest(C.diff, dc, 8), id => [C.meta.eq[id].name, C.meta.eq[id].revit_type, C.meta.eq[id].mark].join(' | '));
  show('sprinkler heads', nearest(C.heads, dc, 8), id => [C.meta.fire[id].fabrication.Description].join(' | '));
  show('floors', nearest(C.floorBoxes, dc, 4), id => [C.meta.floors[id].name, C.meta.floors[id].category].join(' | '));
}
}
export {elementBoxes, candidates, centre, size, r3, build, AREAS};
