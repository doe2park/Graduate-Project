/* Overlay realistic visibility (2026-10-20): distance fade, wall occlusion rule, Range presets / ?range= parsing,
   shader patch and the page wiring. Pure helpers come from twin/overlay-visibility.js (no browser needed). */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const OV=require('../twin/overlay-visibility.js');
const compare=fs.readFileSync(path.join(__dirname,'../scan-compare.html'),'utf8');
const bim=fs.readFileSync(path.join(__dirname,'../scan-bim.html'),'utf8');
const close=(a,b,e=1e-9)=>assert.ok(Math.abs(a-b)<=e,a+' != '+b);

test('Range presets: near 3->6 m, room 8->14 m (default), all = no fade and no occlusion',()=>{
 assert.deepEqual([...OV.RANGE_KEYS],['near','room','all']);assert.equal(OV.DEFAULT_RANGE,'room');
 assert.equal(OV.RANGE_PRESETS.near.fadeStart,3);assert.equal(OV.RANGE_PRESETS.near.fadeEnd,6);
 assert.equal(OV.RANGE_PRESETS.room.fadeStart,8);assert.equal(OV.RANGE_PRESETS.room.fadeEnd,14);
 assert.equal(OV.RANGE_PRESETS.all.occlude,false);assert.ok(OV.RANGE_PRESETS.near.occlude&&OV.RANGE_PRESETS.room.occlude);
 for(const k of OV.RANGE_KEYS){assert.ok(Object.isFrozen(OV.RANGE_PRESETS[k]));assert.equal(OV.preset(k).key,k);}
 assert.equal(OV.preset('bogus').key,'room');assert.equal(OV.preset(undefined).key,'room')});

test('?range= parsing accepts only the three presets',()=>{
 assert.equal(OV.parseRange(''),'room');assert.equal(OV.parseRange('?view=overlay'),'room');
 for(const k of ['near','room','all'])assert.equal(OV.parseRange('?view=overlay&range='+k+'&at=1,2,3'),k);
 for(const bad of ['?range=ALL','?range=','?range=far','?range=javascript:1','?range=near%20'])assert.equal(OV.parseRange(bad),'room',bad);
 assert.equal(OV.parseRange(null),'room')});

test('distance fade: full to fadeStart, smooth, gone at fadeEnd; All never fades',()=>{
 const room=OV.preset('room');
 assert.equal(OV.rangeFade(0,room),1);assert.equal(OV.rangeFade(8,room),1);close(OV.rangeFade(11,room),.5);
 assert.equal(OV.rangeFade(14,room),0);assert.equal(OV.rangeFade(30,room),0);
 let prev=1;for(let d=8;d<=14;d+=.25){const f=OV.rangeFade(d,room);assert.ok(f<=prev+1e-12,'monotonic at '+d);prev=f;}
 close(OV.rangeFade(4.5,'near'),.5);assert.equal(OV.rangeFade(6,'near'),0);
 for(const d of [0,10,100,1e6])assert.equal(OV.rangeFade(d,'all'),1);
 assert.equal(OV.rangeFade(NaN,'room'),0);close(OV.smoothstep(0,1,.25),.15625)});

test('wall occlusion: margin behind the wall face, near-camera walls ignored, Lens relaxes, All ignores walls',()=>{
 const {marginM,nearIgnoreM,hidden,lens}=OV.OCCLUSION;
 assert.equal(marginM,.35);assert.equal(nearIgnoreM,.6);assert.equal(hidden,0);assert.ok(lens>hidden&&lens<1);
 assert.equal(OV.isOccluded(5,Infinity),false);
 assert.equal(OV.isOccluded(3.2,3),false,'in-wall conduit within the margin stays visible');
 assert.equal(OV.isOccluded(4,3),true);
 assert.equal(OV.isOccluded(4,.3),false,'a wall at the camera (station inside a wall) is ignored');
 assert.equal(OV.occlusionFactor(true,0,'room'),hidden);assert.equal(OV.occlusionFactor(true,1,'room'),lens);
 close(OV.occlusionFactor(true,.5,'room'),(hidden+lens)/2);assert.equal(OV.occlusionFactor(false,0,'room'),1);
 assert.equal(OV.occlusionFactor(true,0,'all'),1);
 assert.equal(OV.visibility({distance:4,wallDistance:3},'room'),0);
 assert.equal(OV.visibility({distance:4,wallDistance:3,lensW:1},'room'),lens);
 assert.equal(OV.visibility({distance:40,wallDistance:3},'all'),1)});

test('lens weight matches the parent CSS mask (full inside 72% of the radius, 0 at the rim)',()=>{
 assert.equal(OV.LENS_CORE,.72);
 const m=compare.match(/rgba\(0,0,0,'\+LENS_INSIDE\+'\) (\d+)%/);assert.ok(m);assert.equal(Number(m[1])/100,OV.LENS_CORE);
 assert.equal(OV.lensWeight(0,0,100),1);close(OV.lensWeight(72,0,100),1);close(OV.lensWeight(86,0,100),.5);
 assert.equal(OV.lensWeight(100,0,100),0);assert.equal(OV.lensWeight(0,300,100),0);assert.equal(OV.lensWeight(0,0,0),0);assert.equal(OV.lensWeight(NaN,0,10),0);
 assert.deepEqual(OV.lensToFragCoord({on:true,x:100,y:50,r:40},800,2),[200,1500,80,1]);
 assert.deepEqual(OV.lensToFragCoord({on:false,x:1,y:1,r:1},800,2),[0,0,0,0]);
 assert.deepEqual(OV.lensToFragCoord({on:true,x:NaN,y:1,r:1},800,1),[0,0,0,0])});

test('picking ignores faded and hidden services',()=>{
 assert.equal(OV.PICK_MIN,.25);
 assert.ok(OV.isPickable({distance:2},'room'));assert.ok(!OV.isPickable({distance:30},'room'));
 assert.ok(OV.isPickable({distance:30},'all'),'All keeps today\'s behaviour');
 assert.ok(!OV.isPickable({distance:5,wallDistance:2},'room'),'30 m behind a wall: not pickable outside the lens');
 assert.ok(OV.isPickable({distance:5,wallDistance:2,lensW:1},'room'),'inside the lens a dimmed occluded service can be picked');
 assert.ok(!OV.isPickable({distance:13.5,wallDistance:2,lensW:1},'room'))});

test('uniform values: finite fade band, All maps to a far sentinel',()=>{
 assert.deepEqual(OV.uniformValues('room'),{fade:[8,14],occlude:1});
 const all=OV.uniformValues('all');assert.equal(all.occlude,0);assert.ok(all.fade[0]>=1e6&&all.fade[1]>all.fade[0])});

test('shader patch: view-space varying, fade + occlusion at the end of main, premultiplied only for opaque',()=>{
 const make=()=>({uniforms:{},vertexShader:'void main(){\n#include <project_vertex>\n}',fragmentShader:'void main(){\ngl_FragColor=vec4(1.);\n}'});
 const u={ovOn:{value:1}},s=OV.patchShader(make(),u);
 assert.equal(s.uniforms.ovOn,u.ovOn,'uniform objects are shared, not copied');
 assert.match(s.vertexShader,/^varying vec3 ovView;/);assert.match(s.vertexShader,/#include <project_vertex>\s*ovView = mvPosition\.xyz;/);
 assert.match(s.fragmentShader,/^#define OV_PREMULTIPLY/);assert.match(s.fragmentShader,/smoothstep\(ovFade\.x, ovFade\.y, ovD\)/);
 assert.ok(s.fragmentShader.indexOf('gl_FragColor=vec4(1.)')<s.fragmentShader.indexOf('ovD = length'),'applied after the material output');
 assert.match(s.fragmentShader,/\}\s*$/);
 const t=OV.patchShader(make(),u,{premultiply:false});assert.doesNotMatch(t.fragmentShader,/#define OV_PREMULTIPLY/);
 const again=OV.patchShader(s,u);assert.equal((again.vertexShader.match(/varying vec3 ovView/g)||[]).length,1,'idempotent');
 const o=OV.patchOccluderShader(make());assert.match(o.fragmentShader,/length\(ovView\) < 0\.60\) discard/);
 assert.ok(OV.isWallOccluder({category:'Walls'}));for(const c of ['Doors','Curtain Wall Mullions','Ceilings','Floors'])assert.ok(!OV.isWallOccluder({category:c}),c);
 assert.ok(!OV.isWallOccluder(null))});

test('page wiring: Range control, ?range= persistence, BIM pane messages, render hook and filtered picks',()=>{
 assert.match(compare,/<script src="twin\/overlay-visibility\.js"><\/script>/);assert.match(bim,/<script src="twin\/overlay-visibility\.js"><\/script>/);
 for(const k of ['near','room','all'])assert.match(compare,new RegExp('data-range="'+k+'"'));
 assert.match(compare,/OverlayVisibility\.parseRange\(location\.search\)/);assert.match(compare,/searchParams\.set\('range',overlayRange\)/);
 assert.match(compare,/type:'grimes-overlay-range'/);assert.match(compare,/type:'grimes-overlay-lens'/);
 assert.match(bim,/grimes-overlay-range/);assert.match(bim,/grimes-overlay-lens/);
 assert.match(bim,/ovBeforeRender\(\);[^\n]*\n\s*renderer\.render\(scene, camera\);/,'wall depth pre-pass runs inside the gated draw');
 assert.match(bim,/ovPatchMaterial\(im\.material\)/);assert.match(bim,/OV\.isPickable\(/);
 assert.match(bim,/interior\/enclosure-l1\.glb \(Walls\)/);
 /* capture/mode switches copy location.href, so ?range= travels with ?at= */
 assert.match(compare,/function navigateCapture\(date,display\)\{const u=new URL\(location\.href\)/)});

/* ── distance culling (2026-10-20) ── */
test('cull limit: fadeEnd padded by the recompute distance; All never culls',()=>{
 const {moveM,padM}=OV.CULL;assert.equal(moveM,.5);assert.ok(padM>0&&padM<.2);
 close(OV.cullLimit('near'),6+moveM+padM);close(OV.cullLimit('room'),14+moveM+padM);
 assert.equal(OV.cullLimit('all'),Infinity);assert.equal(OV.cullLimit(OV.preset('bogus')),OV.cullLimit('room'));
 /* anything culled at the last recompute is still beyond fadeEnd (fade exactly 0) anywhere within moveM of that point */
 for(const k of ['near','room'])assert.equal(OV.rangeFade(OV.cullLimit(k)-moveM,k),0)});

test('cull decision: the nearest point of the bounding sphere must be beyond the limit',()=>{
 const L=OV.cullLimit('room');
 assert.equal(OV.sphereBeyond(20,0,0,1,0,0,0,L),true);            // nearest point 19 m
 assert.equal(OV.sphereBeyond(15,0,0,1,0,0,0,L),false,'nearest point 14 m: still drawn (fade boundary)');
 assert.equal(OV.sphereBeyond(40,0,0,30,0,0,0,L),false,'a long pipe reaching back toward the camera is kept');
 assert.equal(OV.sphereBeyond(1e4,0,0,1,0,0,0,Infinity),false,'All');
 assert.equal(OV.sphereBeyond(NaN,0,0,1,0,0,0,L),false,'unknown bounds are never culled');
 const s=new Float32Array([20,0,0,1, 15,0,0,1, 0,3,0,.5, NaN,0,0,0, 0,0,-30,10]),keep=new Uint8Array(5).fill(1);
 let r=OV.cullSpheres(s,[0,0,0],L,keep);assert.deepEqual([...keep],[0,1,1,1,0]);assert.deepEqual(r,{kept:3,changed:2});
 r=OV.cullSpheres(s,[0,0,0],L,keep);assert.deepEqual(r,{kept:3,changed:0},'unchanged set: nothing to re-upload');
 r=OV.cullSpheres(s,[0,0,0],Infinity,keep);assert.deepEqual([...keep],[1,1,1,1,1]);assert.equal(r.kept,5);
 /* squared fast path agrees with sphereBeyond */
 const n=2000,sp=new Float32Array(n*4),k=new Uint8Array(n);let seed=7;const rnd=()=>((seed=(seed*16807)%2147483647)/2147483647);
 for(let i=0;i<n;i++){sp[i*4]=rnd()*60-30;sp[i*4+1]=rnd()*10;sp[i*4+2]=rnd()*60-30;sp[i*4+3]=rnd()*4;}
 OV.cullSpheres(sp,[1,2,3],L,k);for(let i=0;i<n;i++)assert.equal(k[i]===0,OV.sphereBeyond(sp[i*4],sp[i*4+1],sp[i*4+2],sp[i*4+3],1,2,3,L))});

test('element bounds from a vertex range (AABB centre, half diagonal)',()=>{
 const p=new Float32Array([9,9,9, 0,0,0, 2,0,0, 0,4,4, 9,9,9]),o=new Float32Array(8);
 OV.rangeSphere(p,1,3,o,4);assert.deepEqual([...o.slice(4,7)],[1,2,2]);close(o[7],Math.hypot(2,4,4)/2,1e-6);
 OV.rangeSphere(p,0,0,o,0);assert.ok(Number.isNaN(o[3]),'empty range has no bounds (never culled)')});

test('merged batch compaction keeps draw order, merges adjacent runs and maps picks back',()=>{
 const src=Uint16Array.from({length:18},(_,i)=>100+i);                 // 6 triangles, element ranges of 3/6/3/6 indices
 const starts=Uint32Array.from([0,3,9,12]),counts=Uint32Array.from([3,6,3,6]),dst=new Uint16Array(18),map=new Uint32Array(8);
 let r=OV.compactRanges(starts,counts,Uint8Array.from([1,0,1,1]),src,dst,map);
 assert.deepEqual(r,{count:12,runs:2});assert.deepEqual([...dst.slice(0,12)],[100,101,102,109,110,111,112,113,114,115,116,117]);
 assert.equal(OV.compactedToSource(0,map,r.runs),0);assert.equal(OV.compactedToSource(3,map,r.runs),9);assert.equal(OV.compactedToSource(11,map,r.runs),17);
 r=OV.compactRanges(starts,counts,new Uint8Array(4),src,dst,map);assert.deepEqual(r,{count:0,runs:0});
 r=OV.compactRanges(starts,counts,new Uint8Array(4).fill(1),src,dst,map);assert.deepEqual(r,{count:18,runs:1})});

test('instanced batch compaction keeps order and records the source instance',()=>{
 const m=Float32Array.from({length:4*16},(_,i)=>i),c=Float32Array.from({length:12},(_,i)=>i),dm=new Float32Array(64),dc=new Float32Array(12),order=new Uint32Array(4);
 const k=OV.compactInstances(Uint8Array.from([0,1,0,1]),[[m,dm,16],[c,dc,3]],order);
 assert.equal(k,2);assert.deepEqual([...order.slice(0,2)],[1,3]);assert.deepEqual([...dm.slice(0,16)],[...m.slice(16,32)]);assert.deepEqual([...dm.slice(16,32)],[...m.slice(48,64)]);
 assert.deepEqual([...dc.slice(0,6)],[3,4,5,9,10,11])});

test('recompute only after moving more than moveM, or when range / revision change',()=>{
 const t=OV.createCullTracker();
 assert.equal(t.needs([0,0,0],'room',1),true,'first frame');
 assert.equal(t.needs([0.3,0,0],'room',1),false);assert.equal(t.needs([0.5,0,0],'room',1),false,'exactly moveM: still exact');
 assert.equal(t.needs([0.51,0,0],'room',1),true);assert.equal(t.last.x,.51);
 assert.equal(t.needs([0.6,0.1,0],'room',1),false,'measured from the last recompute, not the last frame');
 assert.equal(t.needs([0.6,0.1,0],'near',1),true,'range change');assert.equal(t.needs([0.6,0.1,0],'near',2),true,'visibility / geometry revision');
 t.reset();assert.equal(t.needs([0.6,0.1,0],'near',2),true)});

test('page wiring: culling runs inside the gated draw, is swapped back after it, and picks skip culled elements',()=>{
 assert.match(bim,/function ovBeforeRender\(\)\{\n ovCullUpdate\(\);ovCullApply\(\);/);
 assert.match(bim,/finally \{ if \(typeof ovAfterRender === 'function'\) ovAfterRender\(\); \}/);
 assert.match(bim,/ovCullApply\(\);hits=raycaster\.intersectObjects\(visibleEquip\(\),false\)\.map\(ovCullMapHit\);\}finally\{ovCullRestore\(\);\}/);
 assert.match(bim,/m\.layers\.disable\(0\)/,'separate cull flag: layers, not .visible');
 assert.doesNotMatch(bim.slice(bim.indexOf('function ovCullUpdate'),bim.indexOf('function ovCullCompactInstances')),/\.visible\s*=/,'cull never writes .visible');
 assert.match(bim,/OV\.cullLimit\(ovPreset\)/);assert.match(bim,/get\('cull'\)!=='0'/);
 /* the shared helper stays Three.js-free for scan-xr.html */
 const src=fs.readFileSync(path.join(__dirname,'../twin/overlay-visibility.js'),'utf8');assert.doesNotMatch(src,/\bTHREE\b|require\(|import /)});
