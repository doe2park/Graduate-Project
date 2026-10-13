/* View operations act on runtime batches only. Source vertex attributes and
 * object identity metadata remain available through the stable byKey index. */
export function createObjectView(THREE, meshes, keyFor) {
  const byKey = new Map();
  const states = [...new Set(meshes)].map(mesh => {
    const ids = mesh.userData.ids || [];
    for (const id of new Set(ids)) {
      const key = keyFor(mesh, id);
      if (key == null) continue;
      if (!byKey.has(key)) byKey.set(key, []);
      byKey.get(key).push({ mesh, id });
    }
    const state = {
      mesh, ids, geometry: mesh.geometry, ranges: mesh.userData.ranges,
      hadFilterFlag: Object.hasOwn(mesh.userData, 'objectFilterVisible'),
      filterFlag: mesh.userData.objectFilterVisible,
      box: mesh.boundingBox, sphere: mesh.boundingSphere,
      count: mesh.count, filteredGeometry: null, active: false,
    };
    if (mesh.isInstancedMesh) {
      // Runtime instance buffers may be compacted; these snapshots never are.
      state.matrices = mesh.instanceMatrix.array.slice();
      state.colors = mesh.instanceColor?.array.slice();
    }
    return state;
  });

  function restoreState(s) {
    const m = s.mesh;
    if (s.active) {
      if (m.isInstancedMesh) {
        m.instanceMatrix.array.set(s.matrices);
        m.instanceMatrix.needsUpdate = true;
        if (s.colors && m.instanceColor) {
          m.instanceColor.array.set(s.colors);
          m.instanceColor.needsUpdate = true;
        }
        m.count = s.count;
        m.boundingBox = s.box;
        m.boundingSphere = s.sphere;
      } else {
        m.geometry = s.geometry;
        m.userData.ranges = s.ranges;
      }
      m.userData.ids = s.ids;
      s.active = false;
    }
    if (s.hadFilterFlag) m.userData.objectFilterVisible = s.filterFlag;
    else delete m.userData.objectFilterVisible;
  }

  function setObjectFilter({ isolatedKey = null, hiddenKeys = new Set() } = {}) {
    const visibleKeys = new Set();
    for (const s of states) {
      const m = s.mesh;
      const keep = id => {
        const key = keyFor(m, id);
        const show = (isolatedKey == null || key === isolatedKey) && !hiddenKeys.has(key);
        if (show && key != null) visibleKeys.add(key);
        return show;
      };
      const kept = s.ids.map(keep);
      if (kept.every(Boolean)) { restoreState(s); continue; }
      // Entire excluded batches only need a visibility flag. Allocating an
      // index copy for each off-screen system would defeat whole-building
      // isolation's memory benefit. Restore previous partial state first.
      if (!kept.some(Boolean)) {
        restoreState(s);
        m.userData.objectFilterVisible = false;
        continue;
      }
      s.active = true;
      if (m.isInstancedMesh) {
        const ids = [], colorSize = m.instanceColor?.itemSize || 3;
        for (let i = 0; i < s.count; i++) {
          if (!kept[i]) continue;
          const at = ids.length;
          m.instanceMatrix.array.set(s.matrices.subarray(i * 16, (i + 1) * 16), at * 16);
          if (s.colors && m.instanceColor) {
            m.instanceColor.array.set(s.colors.subarray(i * colorSize, (i + 1) * colorSize), at * colorSize);
          }
          ids.push(s.ids[i]);
        }
        m.count = ids.length;
        m.userData.ids = ids;
        m.instanceMatrix.needsUpdate = true;
        if (m.instanceColor) m.instanceColor.needsUpdate = true;
        // Preserve the exact baseline bounds for restore; never mutate them.
        m.boundingBox = null; m.boundingSphere = null;
        m.computeBoundingBox(); m.computeBoundingSphere();
        m.userData.objectFilterVisible = m.count > 0;
      } else if (s.ranges && s.geometry.index) {
        // Each filtered view owns its index/groups/ranges. Even if another mesh
        // shares the geometry, its rendered primitives cannot be changed here.
        if (!s.filteredGeometry) {
          const g = s.filteredGeometry = new THREE.BufferGeometry();
          for (const [name, attr] of Object.entries(s.geometry.attributes)) g.setAttribute(name, attr);
          g.morphAttributes = s.geometry.morphAttributes;
          g.morphTargetsRelative = s.geometry.morphTargetsRelative;
          g.boundingBox = s.geometry.boundingBox?.clone() || null;
          g.boundingSphere = s.geometry.boundingSphere?.clone() || null;
          // Reuse one GPU index buffer across hide/isolate operations.
          g.setIndex(new THREE.BufferAttribute(new s.geometry.index.array.constructor(s.geometry.index.count), 1));
        }
        const start = s.geometry.drawRange.start;
        const end = Math.min(s.geometry.index.count, start + s.geometry.drawRange.count);
        const allowed = new Set(s.ids.filter((_, i) => kept[i]));
        const pieces = s.ranges.filter(r => allowed.has(r.id)).map(r => ({
          range: r, from: Math.max(start, r.start), to: Math.min(end, r.start + r.count),
        })).filter(r => r.to > r.from);
        const ranges = [], g = s.filteredGeometry;
        const indices = g.index.array;
        let offset = 0;
        g.clearGroups();
        for (const p of pieces) {
          const count = p.to - p.from;
          indices.set(s.geometry.index.array.subarray(p.from, p.to), offset);
          ranges.push({ ...p.range, start: offset, count });
          for (const group of s.geometry.groups) {
            const from = Math.max(p.from, group.start), to = Math.min(p.to, group.start + group.count);
            if (to > from) g.addGroup(offset + from - p.from, to - from, group.materialIndex);
          }
          offset += count;
        }
        g.index.needsUpdate = true;
        g.setDrawRange(0, offset);
        m.geometry = g;
        m.userData.ranges = ranges;
        // Vertex starts deliberately stay unchanged. Line.raycast reports
        // a vertex index; Mesh.raycast reports a face in the filtered index.
        m.userData.objectFilterVisible = offset > 0;
      } else {
        // A single-identity unbatched object only needs its draw range hidden.
        // Unknown multi-identity formats must not pretend to isolate an object.
        if (s.ids.length > 1) throw new Error('Object filtering requires merged ranges or instance identities.');
        if (!s.filteredGeometry) {
          const g = s.filteredGeometry = new THREE.BufferGeometry();
          for (const [name, attr] of Object.entries(s.geometry.attributes)) g.setAttribute(name, attr);
          g.setIndex(s.geometry.index);
        }
        s.filteredGeometry.setDrawRange(0, 0);
        m.geometry = s.filteredGeometry;
        m.userData.objectFilterVisible = false;
      }
    }
    return { visibleKeys };
  }

  return {
    byKey, setObjectFilter,
    restore() { for (const s of states) restoreState(s); },
    dispose() {
      for (const s of states) { restoreState(s); s.filteredGeometry?.dispose(); }
      byKey.clear();
    },
  };
}

const boundsCache = new WeakMap();
function effectiveVisible(mesh) {
  for (let p = mesh; p; p = p.parent) if (!p.visible) return false;
  if (mesh.userData.objectFilterVisible === false) return false;
  if (mesh.isInstancedMesh && mesh.count === 0) return false;
  return mesh.geometry?.drawRange.count !== 0;
}

/** Discard hidden/out-of-ray batches before their potentially costly raycast.
 * Bounds are conservative for filtered merged geometry: vertex buffers never
 * change, so this cannot drop a visible hit. Clipped-away hit points are rejected.
 */
export function pickVisible(raycaster, meshes, clippingPlanes = []) {
  const candidates = [], hits = [];
  for (const mesh of new Set(meshes)) {
    if (!effectiveVisible(mesh) || !mesh.geometry || !raycaster.layers.test(mesh.layers)) continue;
    mesh.updateWorldMatrix(true, false);
    const old = boundsCache.get(mesh), version = mesh.instanceMatrix?.version;
    let bounds = mesh.isInstancedMesh ? mesh.boundingBox : mesh.geometry.boundingBox;
    if (!bounds || (mesh.isInstancedMesh && old && (old.version !== version || old.count !== mesh.count))) {
      if (mesh.isInstancedMesh) mesh.computeBoundingBox();
      else mesh.geometry.computeBoundingBox();
      bounds = mesh.isInstancedMesh ? mesh.boundingBox : mesh.geometry.boundingBox;
    }
    let cached = old;
    if (!cached || cached.geometry !== mesh.geometry || cached.local !== bounds ||
        cached.version !== version || cached.count !== mesh.count || !cached.matrix.equals(mesh.matrixWorld)) {
      cached = { geometry: mesh.geometry, local: bounds, version, count: mesh.count,
        matrix: mesh.matrixWorld.clone(), box: bounds.clone().applyMatrix4(mesh.matrixWorld) };
      boundsCache.set(mesh, cached);
    }
    const box = mesh.isLine ? cached.box.clone().expandByScalar(raycaster.params.Line.threshold) : cached.box;
    if (raycaster.ray.intersectsBox(box)) candidates.push(mesh);
  }
  raycaster.intersectObjects(candidates, false, hits);
  return hits.filter(hit => {
    const material = Array.isArray(hit.object.material) ? hit.object.material[hit.face?.materialIndex || 0] : hit.object.material;
    return material?.visible !== false && !clippingPlanes.some(plane => plane.distanceToPoint(hit.point) < 0);
  }).sort((a, b) => a.distance - b.distance);
}
