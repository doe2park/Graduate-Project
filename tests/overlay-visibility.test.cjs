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
