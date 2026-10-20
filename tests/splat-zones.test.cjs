/* Zone selection logic of scan-splat.html (pure functions between markers; no browser needed). */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../scan-splat.html'),'utf8');
function logic(){const m=src.match(/\/\* ZONE LOGIC \*\/([\s\S]*?)\/\* END ZONE LOGIC \*\//);assert.ok(m,'zone logic block exists');
 const c={Math,Number,Array,Set,URL};vm.createContext(c);vm.runInContext(m[1]+';this.selectZone=selectZone;this.normalizeZoneIndex=normalizeZoneIndex;this.ZONE_HYSTERESIS=ZONE_HYSTERESIS;',c);return c}
const box=(x0,z0,x1,z1)=>({min:[x0,5,z0],max:[x1,7,z1]});
const zones=[
 {id:'west',name:'West',coreBounds:box(0,0,10,10),corePositions:[[1,1],[9,9]]},
 {id:'east',name:'East',coreBounds:box(20,0,30,10),corePositions:[[21,1],[29,9]]},
 {id:'south',name:'South',coreBounds:box(0,20,30,30),corePositions:[[5,25],[25,25]]}];
test('camera inside exactly one core box selects that zone',()=>{const {selectZone}=logic();
 assert.equal(selectZone(zones,5,5),'west');assert.equal(selectZone(zones,25,5),'east');assert.equal(selectZone(zones,15,25),'south')});
test('overlapping boxes pick the zone with the nearest core station',()=>{const {selectZone}=logic();
 const z=[{id:'a',coreBounds:box(0,0,20,10),corePositions:[[2,2],[18,2]]},{id:'b',coreBounds:box(10,0,30,10),corePositions:[[12,8],[28,8]]}];
 assert.equal(selectZone(z,3,2),'a');assert.equal(selectZone(z,28,8),'b');assert.equal(selectZone(z,14,5),'b');assert.equal(selectZone(z,16,2),'a')});
test('outside every core box falls back to the nearest zone',()=>{const {selectZone}=logic();
 assert.equal(selectZone(zones,12,5),'west');assert.equal(selectZone(zones,18,5),'east');assert.equal(selectZone(zones,-50,-50),'west');assert.equal(selectZone(zones,100,100),'south')});
test('without corePositions the box distance is used',()=>{const {selectZone}=logic();
 const z=zones.map(({id,coreBounds})=>({id,coreBounds}));assert.equal(selectZone(z,5,5),'west');assert.equal(selectZone(z,17,5),'east');assert.equal(selectZone(z,15,15),'south')});
test('current zone is kept near a boundary (no flapping) but not once clearly outside',()=>{const {selectZone,ZONE_HYSTERESIS}=logic();
 assert.ok(ZONE_HYSTERESIS>0);
 assert.equal(selectZone(zones,10.5,5,'west'),'west');assert.equal(selectZone(zones,19.5,5,'west'),'east');
 assert.equal(selectZone(zones,14.9,5),'west');assert.equal(selectZone(zones,14.9,5,'east'),'east');assert.equal(selectZone(zones,14.9,5,'west'),'west');
 const near=selectZone(zones,10.6,1,'east');assert.equal(near,'west'); /* east is 10.4 m away, not kept */
 assert.equal(selectZone(zones,20.2,1,'west'),'east')});
test('invalid input keeps the current zone',()=>{const {selectZone}=logic();
 assert.equal(selectZone([],1,1,'x'),'x');assert.equal(selectZone(null,1,1),null);assert.equal(selectZone(zones,NaN,1,'east'),'east')});
const entry=(id,extra={})=>({id,name:id.toUpperCase(),manifest:id+'/viewer.json',bounds:box(0,0,5,5),coreBounds:box(1,1,4,4),corePositions:[[2,2]],...extra});
test('zones index is validated and manifests resolve against the index URL',()=>{const {normalizeZoneIndex}=logic();
 const ok=normalizeZoneIndex({schema:1,frame:'scan-y-up-metres',capture:'2026-09-17',defaultZone:'b',zones:[entry('a'),entry('b')]},'http://localhost:8000/scan-assets/gaussian/2026-09-17/zones/index.json');
 assert.equal(ok.defaultZone,'b');assert.equal(ok.zones[0].manifestURL,'http://localhost:8000/scan-assets/gaussian/2026-09-17/zones/a/viewer.json');
 assert.equal(normalizeZoneIndex({schema:1,frame:'scan-y-up-metres',zones:[entry('a')],defaultZone:'zz'},'http://h/i.json').defaultZone,'a');
 const base='http://h/zones/index.json',good={schema:1,frame:'scan-y-up-metres',zones:[entry('a')]};
 for(const bad of [null,{...good,schema:2},{...good,frame:'other'},{...good,zones:[]},{...good,zones:[entry('a'),entry('a')]},
   {...good,zones:[entry('a',{coreBounds:{min:[0,0],max:[1,1]}})]},{...good,zones:[entry('a',{manifest:'http://evil.example/v.json'})]},{...good,zones:[entry('a',{name:3})]}])
  assert.throws(()=>normalizeZoneIndex(bad,base));
 assert.equal(normalizeZoneIndex(good,base).zones[0].corePositions.length,1)});
test('single-scene behaviour stays the default and the viewer shows a zone label',()=>{
 assert.match(src,/get\('manifest'\)\|\|'scan-assets\/gaussian\/2026-05-06\/viewer\.json'/);assert.match(src,/captureParam\)rel=`scan-assets\/gaussian\/\$\{captureParam\}\/viewer\.json`/);
 assert.match(src,/id="zoneLabel"/);assert.match(src,/Zone: \$\{z\.name\}/);
 assert.match(src,/params\.get\('zones'\)/);assert.match(src,/old\.dispose\(\)/);
 assert.match(src,/if\(!explicit&&params\.get\('manifest'\)\)return null/)});
test('zone index scope is passed through (bounded) and shown; the published Oct 18 index validates if present',()=>{const {normalizeZoneIndex}=logic();
 const idx={schema:1,frame:'scan-y-up-metres',scope:'x'.repeat(500),zones:[entry('a')]};assert.equal(normalizeZoneIndex(idx,'http://h/z/index.json').scope.length,300);
 assert.equal(normalizeZoneIndex({...idx,scope:undefined},'http://h/z/index.json').scope,'');
 assert.match(src,/if\(zoneIndex\.scope\)/);
 const f=path.join(__dirname,'../scan-assets/gaussian/2026-10-18/zones/index.json');if(!fs.existsSync(f))return;
 const n=normalizeZoneIndex(JSON.parse(fs.readFileSync(f,'utf8')),'http://127.0.0.1:8790/scan-assets/gaussian/2026-10-18/zones/index.json');
 assert.equal(n.capture,'2026-10-18');assert.ok(n.zones.some(z=>z.id==='l1-a'));assert.equal(n.zones[0].manifestURL,'http://127.0.0.1:8790/scan-assets/gaussian/2026-10-18/zones/l1-a/viewer.json');assert.match(n.scope,/not surveyed/)});
