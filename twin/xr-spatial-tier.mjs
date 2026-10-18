/* twin/xr-spatial-tier.mjs — runtime-only spatial render tier for scan-xr.html (Quest WebXR overlay).

   Same contract as the scan-bim.html / grimes-bim-viewer.html render tier, re-bucketed for a head-mounted view:
   - Source GLBs, Draco bytes and node names are never changed. Identity = original node name (bindElementSourceIds),
     resolved per fragment against the layer sidecar; merged batches carry triangle/segment range -> element maps,
     instanced batches carry one id per instance (resolveHit below has the scan-bim semantics).
   - Only fragments whose sidecar levelKey is in `levels` are kept (e.g. Level 1); others are dropped after decode.
   - Buckets are (cell, primitive, side) instead of (material, level, type): material colour is baked into a vertex
     colour (merged) or instance colour (instanced), so one shared overlay shader serves a whole layer and the
     batches are small enough for per-station radius visibility (sphere test against the station).
   Nothing here touches the DOM or the network. THREE is passed in (pinned three@0.169.0 in the page). */

export function bindElementSourceIds(gltf) {
  let boundNodes = 0;
  const associations = gltf.parser?.associations, nodes = gltf.parser?.json?.nodes;
  if (!associations || !nodes) return {boundNodes};
  gltf.scene.traverse(object => {
    const nodeIndex = associations.get(object)?.nodes;
    if (!Number.isInteger(nodeIndex)) return;
    const sourceName = object.userData.name, name = typeof sourceName === 'string' && sourceName ? sourceName : nodes[nodeIndex]?.name;
    if (typeof name === 'string' && name) { object.userData.elementId = name; boundNodes++; }
  });
  return {boundNodes};
}

/* Release parser caches after building (scan-bim releaseElementSource). Instanced batches keep sharing source geometry. */
export function releaseSource(gltf) {
  if (!gltf) return;
  gltf.parser?.cache?.removeAll();
  gltf.parser?.associations?.clear();
  for (const s of gltf.scenes || []) s.clear();
  gltf.scene?.clear();
  gltf.scenes = []; gltf.scene = null; gltf.parser = null;
}

const tick = () => new Promise(resolve => setTimeout(resolve, 0));

/* materialFor({isLine, instanced, side}) must return a shared material; merged batches need vertexColors=true. */
export async function buildSpatialTier(THREE, sceneGroup, meta, layerKey, {levels = null, cellSize = 6, maxVertices = 120000, instanceReuse = 8, materialFor} = {}) {
  if (typeof materialFor !== 'function') throw new Error('materialFor is required');
  const stats = {sourceObjects: 0, unidentifiedObjects: 0, droppedOtherLevels: 0, keptFragments: 0, renderTriangles: 0, renderSegments: 0, mergedMeshes: 0, instancedMeshes: 0, instances: 0, drawCalls: 0, elements: 0};
  const identity = object => { for (let p = object; p; p = p.parent) { const id = p.userData.elementId ?? p.name; if (id && Object.prototype.hasOwnProperty.call(meta, id)) return id; } return null; };
  const fragments = [], repeated = new Map(), ids = new Set(), box = new THREE.Box3(), center = new THREE.Vector3(), color = new THREE.Color();
  sceneGroup.updateMatrixWorld(true);
  sceneGroup.traverse(object => {
    if (!(object.isMesh || object.isLine) || !object.geometry?.attributes.position) return;
    stats.sourceObjects++;
    const id = identity(object);
    if (id === null) { stats.unidentifiedObjects++; return; }   // never invent identity
    const info = meta[id];
    if (levels && !levels.has(info.levelKey)) { stats.droppedOtherLevels++; return; }
    const geometry = object.geometry, isLine = !!object.isLine, indexedCount = geometry.index?.count ?? geometry.attributes.position.count;
    const drawStart = Math.max(0, geometry.drawRange.start), drawEnd = Math.min(indexedCount, drawStart + geometry.drawRange.count);
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    const groups = Array.isArray(object.material) ? geometry.groups : [{start: 0, count: indexedCount, materialIndex: 0}];
    if (!geometry.boundingBox) geometry.computeBoundingBox();
    box.copy(geometry.boundingBox).applyMatrix4(object.matrixWorld).getCenter(center);
    const cell = [Math.floor(center.x / cellSize), Math.floor(center.z / cellSize)];
    if (!isLine && !geometry.attributes.normal) geometry.computeVertexNormals();   // runtime-only; source bytes untouched
    for (const group of groups) {
      const material = materials[group.materialIndex || 0];
      if (!material) continue;
      const start = Math.max(drawStart, group.start), end = Math.min(drawEnd, group.start + group.count);
      if (end <= start) continue;
      const side = !isLine && material.side === THREE.DoubleSide ? 'double' : 'front';
      const matrix = object.matrixWorld.clone();
      const part = {object, geometry, material, id, isLine, side, start, end, matrix, cell,
        baseColor: color.copy(material.color || color.setRGB(1, 1, 1)).getHex(THREE.LinearSRGBColorSpace)};
      part.canInstance = !isLine && matrix.determinant() > 0 && start === 0 && end === indexedCount && !Array.isArray(object.material) && !(material.vertexColors && geometry.attributes.color);
      // instancing is decided per cell: only geometry repeated >= instanceReuse times inside the same cell is instanced,
      // everything else in the cell merges into one batch (fewer draw calls than per-geometry instancing)
      part.reuseKey = geometry.uuid + '|' + side + '|' + cell.join(',');
      if (part.canInstance) repeated.set(part.reuseKey, (repeated.get(part.reuseKey) || 0) + 1);
      fragments.push(part); ids.add(id); stats.keptFragments++;
    }
  });
  stats.elements = ids.size;
  const meshes = [];
  const decorate = (mesh, cell, data) => {
    mesh.name = 'xr-elements:' + layerKey;
    mesh.userData = {layer: layerKey, cell, ...data};
    mesh.frustumCulled = true;
    meshes.push(mesh);
  };
  const instanceBuckets = new Map(), mergeBuckets = new Map();
  for (const part of fragments) {
    const instanced = part.canInstance && repeated.get(part.reuseKey) >= instanceReuse;
    const key = instanced ? part.reuseKey : (part.isLine ? 'L' : 'M') + '|' + part.side + '|' + part.cell.join(',');
    const target = instanced ? instanceBuckets : mergeBuckets;
    if (!target.has(key)) target.set(key, []);
    target.get(key).push(part);
  }
  let work = 0;
  const c = new THREE.Color();
  for (const parts of instanceBuckets.values()) {
    const p = parts[0], mesh = new THREE.InstancedMesh(p.geometry, materialFor({isLine: false, instanced: true, side: p.side}), parts.length);
    const baseColors = new Uint32Array(parts.length);
    parts.forEach((part, i) => { mesh.setMatrixAt(i, part.matrix); baseColors[i] = part.baseColor; mesh.setColorAt(i, c.setHex(part.baseColor, THREE.LinearSRGBColorSpace)); });
    mesh.instanceMatrix.needsUpdate = true; mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingBox(); mesh.computeBoundingSphere();
    decorate(mesh, p.cell, {ids: parts.map(x => x.id), baseColors, renderTier: 'instanced'});
    stats.instancedMeshes++; stats.instances += parts.length; stats.renderTriangles += Math.floor((p.end - p.start) / 3) * parts.length;
    if (++work % 100 === 0) await tick();
  }
  const normalMatrix = new THREE.Matrix3(), v = new THREE.Vector3();
  for (const parts of mergeBuckets.values()) {
    let chunk = [], vertices = 0;
    const flush = () => {
      if (!chunk.length) return;
      const isLine = chunk[0].part.isLine, positions = new Float32Array(vertices * 3), colors = new Float32Array(vertices * 3), normals = isLine ? null : new Float32Array(vertices * 3);
      const indexCount = chunk.reduce((n, x) => n + x.indices.length, 0), indices = new (vertices > 65535 ? Uint32Array : Uint16Array)(indexCount), ranges = [];
      let vo = 0, io = 0;
      for (const {part, indices: local, sourceVertices} of chunk) {
        normalMatrix.getNormalMatrix(part.matrix);
        const pos = part.geometry.attributes.position, nor = part.geometry.attributes.normal, col = part.material.vertexColors ? part.geometry.attributes.color : null;
        c.setHex(part.baseColor, THREE.LinearSRGBColorSpace);
        for (let i = 0; i < sourceVertices.length; i++) {
          const s = sourceVertices[i], d = (vo + i) * 3;
          v.fromBufferAttribute(pos, s).applyMatrix4(part.matrix); positions[d] = v.x; positions[d + 1] = v.y; positions[d + 2] = v.z;
          if (normals) { if (nor) v.fromBufferAttribute(nor, s).applyMatrix3(normalMatrix).normalize(); else v.set(0, 1, 0); normals[d] = v.x; normals[d + 1] = v.y; normals[d + 2] = v.z; }
          colors[d] = c.r * (col ? col.getX(s) : 1); colors[d + 1] = c.g * (col ? col.getY(s) : 1); colors[d + 2] = c.b * (col ? col.getZ(s) : 1);
        }
        for (let i = 0; i < local.length; i++) indices[io + i] = vo + local[i];
        if (!isLine && part.matrix.determinant() < 0) for (let i = 0; i < local.length; i += 3) { const a = io + i + 1, t = indices[a]; indices[a] = indices[a + 1]; indices[a + 1] = t; }
        ranges.push({id: part.id, start: io, count: local.length, vertexStart: vo, vertexCount: sourceVertices.length});
        io += local.length; vo += sourceVertices.length;
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      if (normals) g.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
      g.setAttribute('color', new THREE.BufferAttribute(colors, 3));
      g.setIndex(new THREE.BufferAttribute(indices, 1)); g.computeBoundingBox(); g.computeBoundingSphere();
      const first = chunk[0].part, material = materialFor({isLine, instanced: false, side: first.side});
      const mesh = isLine ? new THREE.LineSegments(g, material) : new THREE.Mesh(g, material);
      decorate(mesh, first.cell, {ids: [...new Set(ranges.map(r => r.id))], ranges, renderTier: 'merged', isLine, highlighted: new Map()});
      stats.mergedMeshes++;
      if (isLine) stats.renderSegments += indexCount / 2; else stats.renderTriangles += indexCount / 3;
      chunk = []; vertices = 0;
    };
    for (const part of parts) {
      const local = [], sourceVertices = [], remap = new Map();
      const append = offset => { const s = part.geometry.index ? part.geometry.index.getX(offset) : offset; let l = remap.get(s); if (l === undefined) { l = sourceVertices.length; remap.set(s, l); sourceVertices.push(s); } local.push(l); };
      if (part.isLine && !part.object.isLineSegments) { for (let i = part.start; i + 1 < part.end; i++) { append(i); append(i + 1); } if (part.object.isLineLoop && part.end - part.start > 1) { append(part.end - 1); append(part.start); } }
      else { const step = part.isLine ? 2 : 3, end = part.end - (part.end - part.start) % step; for (let i = part.start; i < end; i++) append(i); }
      if (vertices + sourceVertices.length > maxVertices) flush();
      chunk.push({part, indices: local, sourceVertices}); vertices += sourceVertices.length;   // one element larger than maxVertices stays whole
      if (++work % 250 === 0) await tick();
    }
    flush();
  }
  stats.drawCalls = meshes.length;
  return {meshes, stats};
}

export function resolveHit(object, instanceId, faceIndex, index) {
  if (!object?.userData?.ids) return null;
  if (object.isInstancedMesh) return Number.isInteger(instanceId) ? object.userData.ids[instanceId] ?? null : null;
  const ranges = object.userData.ranges;
  if (!ranges) return object.userData.ids.length === 1 ? object.userData.ids[0] : null;
  const offset = object.isLine ? index : (Number.isInteger(faceIndex) ? faceIndex * 3 : null);
  if (!Number.isInteger(offset) || offset < 0) return null;
  let low = 0, high = ranges.length - 1;
  // Three r169 Line.raycast returns the first vertex index, not the index-buffer offset.
  while (low <= high) { const mid = (low + high) >> 1, r = ranges[mid], start = object.isLine ? r.vertexStart : r.start, count = object.isLine ? r.vertexCount : r.count; if (offset < start) high = mid - 1; else if (offset >= start + count) low = mid + 1; else return r.id; }
  return null;
}

/* Highlight one element; restores the exact baked colours on release. */
export function highlight(THREE, mesh, id, on, hex = 0xfbbf24) {
  if (!id || !mesh.userData.ids?.includes(id)) return;
  const c = new THREE.Color();
  if (mesh.isInstancedMesh) {
    mesh.userData.ids.forEach((x, i) => { if (x === id) mesh.setColorAt(i, on ? c.setHex(hex) : c.setHex(mesh.userData.baseColors[i], THREE.LinearSRGBColorSpace)); });
    mesh.instanceColor.needsUpdate = true; return;
  }
  const attr = mesh.geometry.getAttribute('color'), saved = mesh.userData.highlighted;
  if (on) {
    if (saved.has(id)) return;
    c.setHex(hex); const snaps = [];
    for (const r of mesh.userData.ranges) { if (r.id !== id) continue; const s = r.vertexStart * 3, e = (r.vertexStart + r.vertexCount) * 3; snaps.push({s, values: attr.array.slice(s, e)}); for (let i = r.vertexStart; i < r.vertexStart + r.vertexCount; i++) attr.setXYZ(i, c.r, c.g, c.b); }
    saved.set(id, snaps);
  } else { for (const x of saved.get(id) || []) attr.array.set(x.values, x.s); saved.delete(id); }
  attr.needsUpdate = true;
}

/* Station radius visibility (BIM frame). Returns the number of visible batches. */
export function applyRadius(meshes, center, radius) {
  let n = 0;
  for (const m of meshes) {
    const s = m.isInstancedMesh ? m.boundingSphere : m.geometry.boundingSphere;
    m.visible = !!s && Math.hypot(s.center.x - center[0], s.center.y - center[1], s.center.z - center[2]) - s.radius <= radius;
    if (m.visible) n++;
  }
  return n;
}
