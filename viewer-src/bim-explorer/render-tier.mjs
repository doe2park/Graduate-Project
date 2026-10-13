/* GLTFLoader uniquifies runtime names. r169 keeps the exact source name in
   userData.name. Prefer that value: cloned mesh references may share one
   associations record whose node index is overwritten by the last clone. */
function bindElementSourceIds(gltf) {
  let boundNodes = 0, associationNameConflicts = 0;
  const associations = gltf.parser?.associations, nodes = gltf.parser?.json?.nodes;
  if (!associations || !nodes) return { boundNodes, associationNameConflicts };
  gltf.scene.traverse(object => {
    const nodeIndex = associations.get(object)?.nodes;
    if (!Number.isInteger(nodeIndex)) return;
    const associatedName = nodes[nodeIndex]?.name;
    const sourceName = object.userData.name;
    const name = typeof sourceName === 'string' && sourceName ? sourceName : associatedName;
    if (sourceName && associatedName && sourceName !== associatedName) associationNameConflicts++;
    if (typeof name === 'string' && name) { object.userData.elementId = name; boundNodes++; }
  });
  return { boundNodes, associationNameConflicts };
}
/* Runtime-only draw-call tier. Source GLBs/geometries remain untouched.
   Buckets retain level/type identity; merged index ranges resolve element picks.
   Repeated geometry remains instanced to avoid expanding thousands of fittings. */
async function buildElementRenderTier(THREE, sceneGroup, meta, layerKey, options = {}) {
  const MAX_VERTICES = 180000, INSTANCE_REUSE = 8;
  const fragments = [], repeated = new Map(), mergeBuckets = new Map(), meshes = [];
  const stats = { sourceObjects: 0, unidentifiedObjects: 0, unidentifiedNames: [], sourceTriangles: 0, renderTriangles: 0, sourceSegments: 0, renderSegments: 0, mergedMeshes: 0, instancedMeshes: 0, instances: 0, drawCalls: 0 };
  const tick = () => new Promise(resolve => setTimeout(resolve, 0));
  const identity = object => {
    for (let p = object; p; p = p.parent) {
      const id = p.userData.elementId ?? p.name;
      if (id && Object.prototype.hasOwnProperty.call(meta, id)) return id;
    }
    return null;
  };
  sceneGroup.traverse(object => {
    if (!(object.isMesh || object.isLine) || !object.geometry?.attributes.position) return;
    stats.sourceObjects++;
    const id = identity(object), info = meta[id] || {}, geometry = object.geometry;
    if (id === null) {
      stats.unidentifiedObjects++;
      if (stats.unidentifiedNames.length < 8) stats.unidentifiedNames.push(object.userData.elementId || object.name || '(unnamed)');
    }
    const isLine = !!object.isLine, indexedCount = geometry.index?.count ?? geometry.attributes.position.count;
    const drawStart = Math.max(0, geometry.drawRange.start), drawEnd = Math.min(indexedCount, drawStart + geometry.drawRange.count);
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    const groups = Array.isArray(object.material) ? geometry.groups : [{start: 0, count: indexedCount, materialIndex: 0}];
    for (const group of groups) {
      const material = materials[group.materialIndex || 0];
      if (!material) continue;
      const start = Math.max(drawStart, group.start), end = Math.min(drawEnd, group.start + group.count);
      if (end <= start) continue;
      const part = { object, geometry, material, id, levelKey: info.levelKey || '', type: info.type || '', isLine, start, end, matrix: object.matrixWorld.clone() };
      let cell = '';
      if (options.cellSize > 0) { geometry.computeBoundingBox(); const c = geometry.boundingBox.getCenter(new THREE.Vector3()).applyMatrix4(part.matrix); cell = [c.x,c.z].map(v=>Math.floor(v/options.cellSize)).join(':'); }
      part.key = JSON.stringify([material.uuid, part.levelKey, options.groupByType === false ? '' : part.type, cell, isLine, Object.entries(geometry.attributes).sort(([a],[b])=>a.localeCompare(b)).map(([name,a])=>[name,a.itemSize])]);
      part.reuseKey = part.key + '|' + geometry.uuid;
      // Three.js InstancedMesh does not support negatively scaled matrices.
      part.canInstance = !isLine && part.matrix.determinant() > 0 && start === 0 && end === indexedCount && !Array.isArray(object.material);
      if (part.canInstance) repeated.set(part.reuseKey, (repeated.get(part.reuseKey) || 0) + 1);
      if (!isLine) stats.sourceTriangles += Math.floor((end-start)/3);
      else stats.sourceSegments += object.isLineSegments ? Math.floor((end-start)/2) : Math.max(0,end-start-1) + (object.isLineLoop && end-start > 1 ? 1 : 0);
      fragments.push(part);
    }
  });
  const prepareMaterial = original => {
    const material = original.clone();
    if (!options.preserveMaterial && layerKey === 'structural' && material.emissive) { material.emissive.setHex(0x1e293b); material.emissiveIntensity = 0.25; }
    return material;
  };
  const decorate = (mesh, part, data) => {
    mesh.name = 'elements:' + layerKey;
    mesh.userData = { layer: layerKey, levelKey: part.levelKey, type: part.type, isLine: part.isLine, ...data };
    meshes.push(mesh);
    return mesh;
  };
  const instanceBuckets = new Map();
  for (const part of fragments) {
    const target = part.canInstance && repeated.get(part.reuseKey) >= INSTANCE_REUSE ? instanceBuckets : mergeBuckets;
    const key = target === instanceBuckets ? part.reuseKey : part.key;
    if (!target.has(key)) target.set(key, []);
    target.get(key).push(part);
  }
  let work = 0;
  for (const parts of instanceBuckets.values()) {
    const p = parts[0], mesh = new THREE.InstancedMesh(p.geometry, prepareMaterial(p.material), parts.length);
    const white = new THREE.Color(0xffffff);
    parts.forEach((part,i)=>{mesh.setMatrixAt(i,part.matrix);mesh.setColorAt(i,white);});
    mesh.instanceMatrix.needsUpdate = true;
    mesh.computeBoundingBox(); mesh.computeBoundingSphere();
    decorate(mesh,p,{ ids:parts.map(p=>p.id), renderTier:'instanced' });
    stats.instancedMeshes++; stats.instances += parts.length;
    stats.renderTriangles += Math.floor((p.end-p.start)/3)*parts.length;
    if (++work % 100 === 0) await tick();
  }
  const normalMatrix = new THREE.Matrix3(), vector = new THREE.Vector3();
  for (const parts of mergeBuckets.values()) {
    let chunk = [], vertices = 0;
    const flush = () => {
      if (!chunk.length) return;
      const p = chunk[0].part, sourceAttrs = p.geometry.attributes;
      const geometry = new THREE.BufferGeometry(), arrays = {}, sizes = {};
      for (const [name,attribute] of Object.entries(sourceAttrs)) { sizes[name]=attribute.itemSize; arrays[name]=new Float32Array(vertices*attribute.itemSize); }
      if (!arrays.color) { sizes.color=3;arrays.color=new Float32Array(vertices*3);arrays.color.fill(1); }
      const indexCount = chunk.reduce((n,c)=>n+c.indices.length,0), indices = new (vertices>65535?Uint32Array:Uint16Array)(indexCount);
      const ranges = [];let vertexOffset=0,indexOffset=0;
      for (const {part,indices:localIndices,sourceVertices} of chunk) {
        normalMatrix.getNormalMatrix(part.matrix);
        for (let i=0;i<sourceVertices.length;i++) {
          const sourceIndex=sourceVertices[i], dest=vertexOffset+i;
          for (const [name,attribute] of Object.entries(part.geometry.attributes)) {
            const size=attribute.itemSize, array=arrays[name], at=dest*size;
            for (let k=0;k<size;k++) array[at+k]=(name==='color'&&!part.material.vertexColors)?1:attribute.getComponent(sourceIndex,k);
            if (name==='position') { vector.fromArray(array,at).applyMatrix4(part.matrix);vector.toArray(array,at); }
            else if(name==='normal') { vector.fromArray(array,at).applyMatrix3(normalMatrix).normalize();vector.toArray(array,at); }
            else if(name==='tangent') { vector.fromArray(array,at).transformDirection(part.matrix);vector.toArray(array,at);if(size===4 && part.matrix.determinant()<0)array[at+3]*=-1; }
          }
        }
        for(let i=0;i<localIndices.length;i++) indices[indexOffset+i]=vertexOffset+localIndices[i];
        if(!part.isLine && part.matrix.determinant()<0)for(let i=0;i<localIndices.length;i+=3){const at=indexOffset+i+1,tmp=indices[at];indices[at]=indices[at+1];indices[at+1]=tmp;}
        ranges.push({id:part.id,start:indexOffset,count:localIndices.length,vertexStart:vertexOffset,vertexCount:sourceVertices.length});
        indexOffset+=localIndices.length;vertexOffset+=sourceVertices.length;
      }
      for(const [name,array]of Object.entries(arrays))geometry.setAttribute(name,new THREE.BufferAttribute(array,sizes[name]));
      geometry.setIndex(new THREE.BufferAttribute(indices,1));geometry.computeBoundingBox();geometry.computeBoundingSphere();
      const material=prepareMaterial(p.material);material.vertexColors=true;
      const mesh=p.isLine?new THREE.LineSegments(geometry,material):new THREE.Mesh(geometry,material);
      decorate(mesh,p,{ids:[...new Set(ranges.map(r=>r.id))],ranges,renderTier:'merged',highlighted:new Map()});
      stats.mergedMeshes++;
      if(p.isLine)stats.renderSegments+=indexCount/2;else stats.renderTriangles+=indexCount/3;
      chunk=[];vertices=0;
    };
    for(const part of parts) {
      // Compact each fragment independently: no cross-element vertex sharing,
      // so highlighting one identity cannot change its neighbours.
      const localIndices=[],sourceVertices=[],remap=new Map();
      const append = offset => {const source=part.geometry.index?part.geometry.index.getX(offset):offset;let local=remap.get(source);if(local===undefined){local=sourceVertices.length;remap.set(source,local);sourceVertices.push(source);}localIndices.push(local);};
      if(part.isLine&&!part.object.isLineSegments){for(let i=part.start;i+1<part.end;i++){append(i);append(i+1);}if(part.object.isLineLoop&&part.end-part.start>1){append(part.end-1);append(part.start);}}
      else {const step=part.isLine?2:3,end=part.end-(part.end-part.start)%step;for(let i=part.start;i<end;i++)append(i);}
      const appendChunk = (indices, sourceVertices) => {
        if(vertices+sourceVertices.length>MAX_VERTICES)flush();
        chunk.push({part,indices,sourceVertices});vertices+=sourceVertices.length;
      };
      if(sourceVertices.length<=MAX_VERTICES)appendChunk(localIndices,sourceVertices);
      else {
        // Bound even one unusually large element; 180000 is divisible by both
        // triangle and line primitive sizes, so no primitive is cut in half.
        for(let start=0;start<localIndices.length;start+=MAX_VERTICES){
          const subIndices=[],subVertices=[],subMap=new Map();
          for(let i=start;i<Math.min(start+MAX_VERTICES,localIndices.length);i++){
            const source=sourceVertices[localIndices[i]];let local=subMap.get(source);
            if(local===undefined){local=subVertices.length;subMap.set(source,local);subVertices.push(source);}
            subIndices.push(local);
          }
          appendChunk(subIndices,subVertices);
          await tick();
        }
      }
      if(++work%250===0)await tick();
    }
    flush();
  }
  stats.drawCalls=meshes.length;
  return {meshes,stats};
}
function resolveElementHit(object,instanceId,faceIndex,index) {
  if(!object?.userData?.ids)return null;
  if(object.isInstancedMesh)return Number.isInteger(instanceId)?object.userData.ids[instanceId]??null:null;
  const ranges=object.userData.ranges;
  if(!ranges)return object.userData.ids.length===1?object.userData.ids[0]:null;
  const offset=object.isLine?index:(Number.isInteger(faceIndex)?faceIndex*3:null);
  if(!Number.isInteger(offset)||offset<0)return null;
  let low=0,high=ranges.length-1;
  // Three r169 Line.raycast returns the first vertex index, not index-buffer offset.
  while(low<=high){const mid=(low+high)>>1,r=ranges[mid],start=object.isLine?r.vertexStart:r.start,count=object.isLine?r.vertexCount:r.count;if(offset<start)high=mid-1;else if(offset>=start+count)low=mid+1;else return r.id;}
  return null;
}
function highlightElementRender(mesh,id,on,color) {
  if(!id||!mesh.userData.ids?.includes(id))return;
  if(mesh.isInstancedMesh){const value=mesh.material.color.clone().set(on?(color??0xfbbf24):0xffffff);mesh.userData.ids.forEach((x,i)=>{if(x===id)mesh.setColorAt(i,value);});mesh.instanceColor.needsUpdate=true;return;}
  const attribute=mesh.geometry.getAttribute('color'),saved=mesh.userData.highlighted;
  if(!attribute||!saved)return;
  if(on){
    if(saved.has(id))return;
    const value=mesh.material.color.clone().set(color??0xfbbf24),snapshots=[];
    for(const r of mesh.userData.ranges){if(r.id!==id)continue;const start=r.vertexStart*attribute.itemSize,end=(r.vertexStart+r.vertexCount)*attribute.itemSize;snapshots.push({start,values:attribute.array.slice(start,end)});for(let i=r.vertexStart;i<r.vertexStart+r.vertexCount;i++)attribute.setXYZ(i,value.r,value.g,value.b);}
    saved.set(id,snapshots);
  }else{for(const s of saved.get(id)||[])attribute.array.set(s.values,s.start);saved.delete(id);}
  attribute.needsUpdate=true;
}
function setElementRenderVisible(mesh,levelFilter,typeFilter,meta) {
  mesh.visible=(!levelFilter||mesh.userData.levelKey===levelFilter)&&(!typeFilter||mesh.userData.type===typeFilter);
  return mesh.visible;
}
function findElementSelection(mesh,id) {
  if(mesh.isInstancedMesh){const i=mesh.userData.ids.indexOf(id);return i<0?null:{id,instanceId:i};}
  const r=mesh.userData.ranges?.find(r=>r.id===id);return r?{id,faceIndex:mesh.isLine?undefined:r.start/3,index:mesh.isLine?r.vertexStart:undefined}:null;
}
/* Call in finally after building this static runtime tier. Do not dispose
   source geometry/textures: live instances/material clones still share them. */
function releaseElementSource(gltf) {
  if (!gltf) return;
  gltf.parser?.cache?.removeAll();
  gltf.parser?.associations?.clear();
  for (const source of gltf.scenes || []) source.clear();
  gltf.scene?.clear();
  gltf.scenes = [];
  gltf.scene = null;
  gltf.parser = null;
}


export {bindElementSourceIds, buildElementRenderTier, resolveElementHit, highlightElementRender, findElementSelection, releaseElementSource, setElementRenderVisible};
