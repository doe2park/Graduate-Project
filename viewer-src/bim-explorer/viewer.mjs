import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {DRACOLoader} from 'three/addons/loaders/DRACOLoader.js';
import {bindElementSourceIds,buildElementRenderTier,resolveElementHit,highlightElementRender,releaseElementSource} from './render-tier.mjs';
import {readGLB,validatePackage} from './contract.mjs';
import {createLoadGate} from './load-gate.mjs';
import {systems,layerMetadata,identityKey} from './catalog.mjs';
import {sourceMetadata,combineParts,verifyBytes,levelName} from './source-model.mjs';
import {createObjectView,pickVisible} from './object-view.mjs';
import {createRecordIndex} from './record-index.mjs';
import {createDemandRenderer} from './demand-renderer.mjs';
import {verifiedAsset} from './asset-cache.mjs';
import {deploymentPaths} from './deployment.mjs';
const deployment=deploymentPaths(document.baseURI);
const $=id=>document.getElementById(id),vp=$('viewport'),scene=new THREE.Scene();scene.background=new THREE.Color('#eef3f6');
const camera=new THREE.PerspectiveCamera(42,1,.001,100000),renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));vp.append(renderer.domElement);
scene.add(new THREE.HemisphereLight(0xffffff,0x607080,1.8));const light=new THREE.DirectionalLight(0xffffff,1.5);light.position.set(8,15,12);scene.add(light);
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;const ray=new THREE.Raycaster();ray.params.Line.threshold=.025;
const draco=new DRACOLoader().setDecoderPath(deployment.asset('draco/'));draco.setWorkerLimit(2);const loader=new GLTFLoader().setDRACOLoader(draco);
let root=null,records={},report=null,selected=null,mode=null,layers=[],events=[],objectView=null,recordIndex=createRecordIndex({}),hiddenKeys=new Set(),isolatedKey=null,cacheReads=[];
const gate=createLoadGate();let floor='',buildingSource=false;const query=new URLSearchParams(location.search);if(!query.has('model')&&matchMedia('(max-width: 600px)').matches)$('dataset').value='regional';if(['regional','conduit','full'].includes(query.get('model')))$('dataset').value=query.get('model');
const draw=createDemandRenderer({renderer,scene,camera,controls,blocked:()=>buildingSource,onFrame:stats=>{
 $('render-stats').textContent=`${stats.calls.toLocaleString()} draw calls${stats.moving?' · navigating':''}`;
}});
const invalidate=()=>draw.invalidate();
const sectionPlane=new THREE.Plane(new THREE.Vector3(0,-1,0),0);
function enabledLayers(){return new Set(layers.filter(l=>l.visible).map(l=>l.key));}
new ResizeObserver(()=>{camera.aspect=vp.clientWidth/vp.clientHeight;camera.updateProjectionMatrix();renderer.setSize(vp.clientWidth,vp.clientHeight);invalidate();}).observe(vp);
function visibleBox(){
 const box=new THREE.Box3(),visible=enabledLayers();
 for(const [key,e] of recordIndex.entries)if(e.viewBounds&&visible.has(e.layer)&&(!floor||(e.levelKey||'UNKNOWN')===floor)&&!hiddenKeys.has(key)&&(!isolatedKey||key===isolatedKey))
  box.union(new THREE.Box3(new THREE.Vector3(...e.viewBounds.min),new THREE.Vector3(...e.viewBounds.max)));
 return box;
}
function fit(top=false){if(!root)return;const box=visibleBox();if(box.isEmpty())return;const c=box.getCenter(new THREE.Vector3()),s=box.getSize(new THREE.Vector3()),radius=s.length()/2;controls.target.copy(c);const direction=(top?new THREE.Vector3(0,1,.0001):new THREE.Vector3(.9,.65,1)).normalize(),right=new THREE.Vector3().crossVectors(new THREE.Vector3(0,1,0),direction).normalize(),up=new THREE.Vector3().crossVectors(direction,right),tan=Math.tan(THREE.MathUtils.degToRad(camera.fov/2));let distance=0;for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]){const v=new THREE.Vector3(x,y,z).sub(c);distance=Math.max(distance,v.dot(direction)+Math.abs(v.dot(right))/(tan*camera.aspect),v.dot(direction)+Math.abs(v.dot(up))/tan);}camera.position.copy(c).addScaledVector(direction,distance*1.09);camera.near=Math.max(radius/10000,.001);camera.far=Math.max(radius*50,100);camera.updateProjectionMatrix();controls.update();$('view-label').textContent=(top?'Top view':'Model overview')+(floor?' · '+levelName(floor):'');invalidate();}
$('fit').onclick=()=>fit();$('top').onclick=()=>fit(true);
function event(message){events.push({at:new Date().toISOString(),message});events=events.slice(-40);$('activity').replaceChildren(...events.slice(-6).reverse().map(e=>{const li=document.createElement('li'),time=document.createElement('time');li.textContent=e.message;time.dateTime=e.at;time.textContent=new Date(e.at).toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit'});li.append(time);return li;}));}
function status(message,error=false){$('status').textContent=message;$('status').className=error?'error':'';}
function dispose(object){const geometries=new Set(),materials=new Set(),textures=new Set();object?.traverse(o=>{if(o.geometry)geometries.add(o.geometry);for(const m of Array.isArray(o.material)?o.material:[o.material])if(m){materials.add(m);for(const v of Object.values(m))if(v?.isTexture)textures.add(v);}});for(const t of textures)t.dispose();for(const m of materials)m.dispose();for(const g of geometries)g.dispose();object?.clear();}
function applyVisibility(){
 if(!root)return;
 const visible=enabledLayers();
 for(const m of root.children)m.visible=visible.has(m.userData.layer)&&(!floor||(m.userData.levelKey||'UNKNOWN')===floor)&&m.userData.objectFilterVisible!==false;
 $('metric-visible').textContent=recordIndex.count({layers:visible,floor,hiddenKeys,isolatedKey}).toLocaleString();
 $('object-filter-state').textContent=isolatedKey?'One object isolated':hiddenKeys.size?`${hiddenKeys.size} objects hidden`:'';
 invalidate();
}
function highlight(key,enabled){
 for(const {mesh,id} of objectView?.byKey.get(key)||[])highlightElementRender(mesh,id,enabled,new THREE.Color('#FDB515'));
}
function applyObjectFilter(){
 highlight(selected,false);
 objectView?.setObjectFilter({isolatedKey,hiddenKeys});
 highlight(selected,true);applyVisibility();
}
function setAllLayers(visible){
 for(const l of layers)l.visible=visible;
 for(const input of $('layers').querySelectorAll('input'))input.checked=visible;
 applyVisibility();
}
function resetSection(){
 const box=visibleBox();
 $('section-enabled').checked=false;renderer.clippingPlanes=[];
 if(!box.isEmpty()){
  $('section-height').min=box.min.y.toFixed(2);$('section-height').max=box.max.y.toFixed(2);
  $('section-height').value=((box.min.y+box.max.y)/2).toFixed(2);
 }
 updateSection();
}
function updateSection(){
 const height=Number($('section-height').value);sectionPlane.constant=height;
 renderer.clippingPlanes=$('section-enabled').checked?[sectionPlane]:[];
 $('section-height').disabled=!$('section-enabled').checked;
 $('section-value').textContent=`${height.toFixed(2)} m`;invalidate();
}
$('section-enabled').onchange=updateSection;$('section-height').oninput=updateSection;
$('isolate').onclick=()=>{
 if(!selected)return;$('section-enabled').checked=false;updateSection();isolatedKey=selected;hiddenKeys.delete(selected);
 const e=records[selected];floor=e.levelKey||'';$('floor').value=floor;setLayer(e.layer,true);
 applyObjectFilter();fit();
};
$('hide-object').onclick=()=>{if(selected){hiddenKeys.add(selected);isolatedKey=null;applyObjectFilter();}};
function restoreView(){
 hiddenKeys.clear();isolatedKey=null;floor='';$('floor').value='';
 highlight(selected,false);objectView?.restore();highlight(selected,true);
 setAllLayers(true);resetSection();fit();
}
$('restore-view').onclick=restoreView;
function visibleCount(){applyVisibility();}
function setLayer(key,visible){const l=layers.find(l=>l.key===key);if(!l)return;l.visible=visible;const cb=$('layers').querySelector(`input[data-layer="${CSS.escape(key)}"]`);if(cb)cb.checked=visible;applyVisibility();}
function setupFloors(){floor='';$('floor').replaceChildren();for(const key of ['',...new Set(Object.values(records).map(e=>e.levelKey||'UNKNOWN'))].sort((a,b)=>['','LOWER','MEZZ','L1','L2','L3','L4','ROOF','UNKNOWN'].indexOf(a)-['','LOWER','MEZZ','L1','L2','L3','L4','ROOF','UNKNOWN'].indexOf(b))){const o=document.createElement('option');o.value=key;o.textContent=key?levelName(key):'All floors';$('floor').append(o);}}
$('floor').onchange=()=>{floor=$('floor').value;applyVisibility();fit();};
function applyColours(){root?.traverse(m=>{for(const mat of Array.isArray(m.material)?m.material:[m.material])if(mat?.userData.sourceColour!==undefined){mat.color.setHex(mat.userData.sourceColour);if($('colours').value==='systems')mat.color.set(systems[m.userData.layer]?.color||'#829bad');}});invalidate();}
$('colours').onchange=applyColours;
$('all').onclick=()=>{hiddenKeys.clear();isolatedKey=null;applyObjectFilter();setAllLayers(true);event('All systems shown');};$('none').onclick=()=>{setAllLayers(false);event('All systems hidden');};
function renderLayers(){ $('layers').replaceChildren(...layers.map(l=>{const row=document.createElement('label'),input=document.createElement('input'),name=document.createElement('span'),count=document.createElement('em');row.className='layer-row';row.style.setProperty('--system-color',systems[l.key]?.color||'#607080');input.type='checkbox';input.checked=true;input.dataset.layer=l.key;input.setAttribute('aria-label',systems[l.key]?.label||l.key);input.onchange=()=>setLayer(l.key,input.checked);name.className='layer-name';name.textContent=systems[l.key]?.label||l.key;count.textContent=l.count;row.append(input,name,count);return row;}));$('layer-count').textContent=layers.length;visibleCount();}
function options(){
 const {count,shown}=recordIndex.search($('search').value,100,selected);
 $('objects').replaceChildren(...shown.map(([key,e])=>{const o=document.createElement('option');o.value=key;o.textContent=`${e.type||e.layer} · ${e.sourceId}`;return o;}));
 $('search-count').textContent=count>100?`${count.toLocaleString()} matches · refine your search`:`${count.toLocaleString()} matching objects`;
 $('objects').disabled=!count;
 if(!count){const o=document.createElement('option');o.textContent='No matching objects';$('objects').append(o);}
 else if(shown.some(([k])=>k===selected))$('objects').value=selected;
}
let searchTimer;
$('search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(options,100);};
function select(key){
 const e=records[key];if(!e)return;
 highlight(selected,false);selected=key;highlight(selected,true);
 if(!$('objects').querySelector(`option[value="${CSS.escape(key)}"]`))options();
 $('objects').value=key;$('type').textContent=e.type||e.category||'BIM component';
 $('system-name').textContent=systems[e.layer]?.label||e.layer;
 $('key').textContent=`${e.buildingId} / ${e.layer} / ${e.sourceId}`;$('props').replaceChildren();
 for(const [label,value]of [['Tag',e.element_tag||e.mark||'Not supplied'],['System',e.system||e.layer],['Level',e.level||'Not supplied'],['Source ID',e.sourceId],['Location',e.location||'Not supplied']]){
  const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=String(value);$('props').append(dt,dd);
 }
 $('raw').textContent=JSON.stringify(e,null,2);invalidate();
}
$('objects').onchange=e=>select(e.target.value);
$('focus').onclick=()=>{const e=records[selected];if(!e)return;$('section-enabled').checked=false;updateSection();hiddenKeys.delete(selected);isolatedKey=null;applyObjectFilter();if(floor&&e.levelKey!==floor){floor=e.levelKey||'';$('floor').value=floor;}setLayer(e.layer,true);const bounds=e.viewBounds;if(!bounds){fit();return;}const b=new THREE.Box3(new THREE.Vector3(...bounds.min),new THREE.Vector3(...bounds.max)),c=b.getCenter(new THREE.Vector3()),distance=Math.max(b.getSize(new THREE.Vector3()).length()*1.8,1.8);controls.target.copy(c);camera.position.copy(c).add(new THREE.Vector3(.8,.5,1).normalize().multiplyScalar(distance));controls.update();$('view-label').textContent=e.type||'Selected object';invalidate();};
async function checked(url,kind='json'){const r=await fetch(url);if(!r.ok)throw Error(`File unavailable (${r.status}): ${url}`);return kind==='buffer'?r.arrayBuffer():r.json();}
async function decode(buffer,metadata,transform=null){const validated=validatePackage(readGLB(buffer),metadata);const gltf=await loader.parseAsync(buffer,'');let built;try{bindElementSourceIds(gltf);const group=new THREE.Group();if(transform){group.rotation.y=transform.yaw;group.position.fromArray(transform.translation);}group.add(gltf.scene);group.updateMatrixWorld(true);const mapped={};for(const id of validated.ids)mapped[identityKey(metadata.buildingId,metadata.layer,id)]={...metadata.elements[id],buildingId:metadata.buildingId,layer:metadata.layer,sourceId:id};
// Bounds come from the actual transformed geometry; uploaded property bounds are not trusted.
 group.traverse(o=>{if(!o.geometry?.attributes.position)return;let id;for(let p=o;p;p=p.parent)if(Object.hasOwn(metadata.elements,p.userData.elementId)){id=String(p.userData.elementId);break;}if(!id)return;if(!o.geometry.boundingBox)o.geometry.computeBoundingBox();const b=o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld),key=identityKey(metadata.buildingId,metadata.layer,id),old=mapped[key].viewBounds;if(old)b.union(new THREE.Box3(new THREE.Vector3(...old.min),new THREE.Vector3(...old.max)));mapped[key].viewBounds={min:b.min.toArray(),max:b.max.toArray()};});
 built=await buildElementRenderTier(THREE,group,metadata.elements,metadata.layer,{groupByType:query.get('batching')==='legacy',preserveMaterial:true});if(built.stats.unidentifiedObjects)throw Error('Geometry without a source identity');for(const m of built.meshes){m.userData.buildingId=metadata.buildingId;for(const mat of Array.isArray(m.material)?m.material:[m.material])if(mat.color){mat.userData.sourceColour=mat.color.getHex();}}
 return {meshes:built.meshes,records:mapped,validation:validated,stats:built.stats,bytes:buffer.byteLength,layer:metadata.layer};
 }catch(e){if(built){const g=new THREE.Group();g.add(...built.meshes);dispose(g);}else dispose(gltf.scene);throw e;}finally{releaseElementSource(gltf);}}
async function loadExample(){const choice=$('dataset').value;return requestLoad(async next=>{if(choice==='full'){buildingSource=true;try{return await loadFull(next);}finally{buildingSource=false;}}if(choice==='conduit'){const [buffer,metadata]=await Promise.all([checked(deployment.asset('sample.glb'),'buffer'),checked(deployment.asset('sample.json'))]);const l=await decode(buffer,metadata);next.add(...l.meshes);return {parts:[l],choice,scope:'Conduit identity exercise · 24 source objects'};}
 const manifest=await checked(deployment.asset('regional/manifest.json')),all=await checked(deployment.asset('regional/'+manifest.elements)),parts=[];for(const l of manifest.layers){$('loading').textContent=`Loading ${systems[l.layer]?.label||l.layer}…`;const part=await decode(await checked(deployment.asset('regional/'+l.file),'buffer'),layerMetadata(all,l.layer),manifest.sourceTransform);next.add(...part.meshes);parts.push(part);if(part.validation.matched!==l.objects)throw Error(`Object count mismatch in ${l.layer}`);event(`${systems[l.layer]?.label||l.layer}: ${part.validation.matched} identities verified`);}if(parts.reduce((s,p)=>s+p.stats.renderTriangles,0)!==manifest.triangleInstances)throw Error('Triangle count mismatch');if(parts.reduce((s,p)=>s+p.validation.matched,0)!==manifest.objectCount)throw Error('Package identity count mismatch');return {parts,choice,center:manifest.zone.centerBim,scope:'Level 1 regional package · Eight disciplines · Partial coverage'};});}
async function fetchSourceFile(path){return checked(deployment.source(path),'buffer');}
async function sourceFile(path,hash){
 return verifiedAsset(path,hash,{fetchBuffer:fetchSourceFile,verify:verifyBytes,onRead:r=>cacheReads.push(r)});
}
async function loadFull(next){const catalog=await checked(deployment.asset('source-catalog.json')),parts=[];let completed=0;const total=catalog.layers.reduce((s,l)=>s+l.parts.length,0);for(const layer of catalog.layers){$('loading').textContent=`Restoring ${systems[layer.key]?.label||layer.key} · ${completed}/${total} files`;const raw=await sourceFile(layer.metadata,layer.metadataSHA256);const metadata=sourceMetadata(JSON.parse(new TextDecoder().decode(raw)),layer.key),chunks=[];for(const file of layer.parts){$('loading').textContent=`Loading ${systems[layer.key]?.label||layer.key} · ${completed+1}/${total} files`;await new Promise(r=>setTimeout(r,0));const buffer=await sourceFile(file.path,file.sha256);const part=await decode(buffer,metadata,catalog.transform);if(part.validation.matched!==file.objects||part.stats.renderTriangles!==file.triangles||part.stats.renderSegments!==file.segments){const g=new THREE.Group();g.add(...part.meshes);dispose(g);throw Error(`Source fidelity mismatch: ${file.path}`);}next.add(...part.meshes);chunks.push(part);completed++;}parts.push(combineParts(chunks,layer.key));event(`${systems[layer.key]?.label||layer.key}: ${layer.objects.toLocaleString()} original identities restored`);}if(parts.reduce((n,p)=>n+p.validation.matched,0)!==catalog.objects)throw Error('Incomplete building identities');return {parts,choice:'full',scope:'Complete BIM · 10 disciplines · Existing source geometry'};}
async function requestLoad(build){return gate.run(async()=>{const next=new THREE.Group(),started=performance.now();cacheReads=[];for(const id of ['demo','load','dataset'])$(id).disabled=true;$('loading').hidden=false;status('Checking the package…');event('Package load started');try{const result=await build(next),newRecords=Object.assign({},...result.parts.map(p=>p.records));if(Object.keys(newRecords).length!==result.parts.reduce((s,p)=>s+p.validation.matched,0))throw Error('Duplicate identity across packages');const old=root;objectView?.dispose();root=next;records=newRecords;recordIndex=createRecordIndex(records);selected=null;hiddenKeys=new Set();isolatedKey=null;objectView=createObjectView(THREE,root.children,(m,id)=>identityKey(m.userData.buildingId,m.userData.layer,id));mode=result.choice;layers=result.parts.map(p=>({key:p.layer,count:p.validation.matched,visible:true}));setupFloors();scene.add(root);if(old){scene.remove(old);dispose(old);}report={matched:Object.keys(records).length,ids:Object.keys(records),layers:result.parts.map(p=>({layer:p.layer,...p.stats,matched:p.validation.matched,bytes:p.bytes})),fileBytes:result.parts.reduce((s,p)=>s+p.bytes,0),triangles:result.parts.reduce((s,p)=>s+p.stats.renderTriangles,0),segments:result.parts.reduce((s,p)=>s+p.stats.renderSegments,0),sourceGeometryPreserved:true,batching:query.get('batching')==='legacy'?'by-type':'compatible-material-floor-system',cache:{hits:cacheReads.filter(r=>r.source==='verified-cache').length,reads:cacheReads.length,assets:cacheReads},mode:result.choice,scope:result.scope,units:'m',upAxis:'Y',spatiallyRegistered:false,hardwareValidated:false,validatedAt:new Date().toISOString(),loadMs:Math.round(performance.now()-started)};
 applyColours();$('scope').textContent=result.scope;$('search').value='';options();renderLayers();resetSection();select(Object.keys(records).find(k=>records[k].sourceId==='160988'&&records[k].layer==='equipment')||report.ids[0]);fit();if(result.choice==='full'){camera.position.sub(controls.target).multiplyScalar(.84).add(controls.target);controls.update();}if(result.center){const c=new THREE.Vector3(...result.center);controls.target.copy(c);camera.position.copy(c).add(new THREE.Vector3(10,7,12).multiplyScalar(1.2*Math.max(1,1/camera.aspect)));controls.update();$('view-label').textContent='Regional overview';invalidate();}$('metric-objects').textContent=report.matched.toLocaleString();$('metric-bytes').textContent=report.fileBytes>1e6?`${(report.fileBytes/1e6).toFixed(2)} MB`:`${(report.fileBytes/1000).toFixed(1)} kB`;$('summary').textContent=`${report.matched} objects · ${report.triangles} triangles · identity preserved`;$('report').disabled=false;status('Ready. Select a component to inspect its source properties.');event(`Ready: ${report.matched} objects in ${layers.length} systems`);
 }catch(e){dispose(next);status(e.message,true);event('Load failed; previous model retained');if(mode&&mode!=='upload')$('dataset').value=mode;}finally{$('loading').hidden=true;for(const id of ['demo','load','dataset'])$(id).disabled=false;invalidate();}});}
$('demo').onclick=loadExample;$('dataset').onchange=loadExample;
$('load').onclick=()=>requestLoad(async next=>{const g=$('glb').files[0],m=$('json').files[0];if(!g||!m)throw Error('Choose both a GLB and its identity JSON.');if(!g.name.toLowerCase().endsWith('.glb')||!m.name.toLowerCase().endsWith('.json'))throw Error('Choose .glb and .json files.');if(g.size>100*1024*1024||m.size>20*1024*1024)throw Error('File limit: GLB 100 MB, JSON 20 MB.');const part=await decode(await g.arrayBuffer(),JSON.parse(await m.text()));next.add(...part.meshes);return {parts:[part],choice:'upload',scope:'Local package · Source coordinates · No physical alignment'};});
function hitKey(h){const id=resolveElementHit(h.object,h.instanceId,h.faceIndex,h.index);return id===null?null:identityKey(h.object.userData.buildingId,h.object.userData.layer,id);}
let down;renderer.domElement.onpointerdown=e=>down=[e.clientX,e.clientY];renderer.domElement.onpointerup=e=>{if(!root||!down)return;const moved=Math.hypot(e.clientX-down[0],e.clientY-down[1]);down=null;if(moved>5)return;const r=renderer.domElement.getBoundingClientRect();ray.setFromCamera(new THREE.Vector2(2*(e.clientX-r.left)/r.width-1,1-2*(e.clientY-r.top)/r.height),camera);const h=pickVisible(ray,root.children,renderer.clippingPlanes).find(h=>records[hitKey(h)]);if(h){$('search').value='';options();select(hitKey(h));}};
$('report').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({...report,render:draw.stats,events},null,2)],{type:'application/json'}));a.download='validation-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
window.bimLab={get report(){return report;},get selected(){return selected;},get root(){return root;},get records(){return records;},get frames(){return draw.stats.frames;},get renderStats(){return draw.stats;},select,restoreView,fit,get layers(){return layers;},get floor(){return floor;},scene,camera,renderer,hitKey};
loadExample();
