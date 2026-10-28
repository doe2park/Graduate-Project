/* Per-floor interior in scan-bim.html (2026-10-27): Level 1 keeps the legacy manifest fields, Level 2/3 load lazily
   from manifest.levels when the element floor changes, one floor in memory, cancel-safe; the Overlay wall occluder
   follows the element floor. Pure extraction tests plus the real interior/manifest.json. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const read=f=>fs.readFileSync(path.join(__dirname,'..',f),'utf8');
const bim=read('scan-bim.html'),compare=read('scan-compare.html'),manifest=JSON.parse(read('interior/manifest.json'));
function fns(){
 const spec=bim.match(/function interiorSpec\([\s\S]*?\n}/)[0],lv=bim.match(/const INTERIOR_LEVELS=[^\n]*/)[0];
 const occ=bim.match(/function ovOccluderLevel\(\)[^\n]*/)[0];
 const ctx={equipLevelFilter:null};vm.createContext(ctx);
 vm.runInContext(lv+'\n'+spec+'\n'+occ+';this.spec=interiorSpec;this.occ=()=>ovOccluderLevel();',ctx);return ctx;
}
test('Level 1 resolves to the legacy top-level groups and slice (public views unchanged)',()=>{const c=fns();
 const s=c.spec(manifest,'L1');assert.equal(s.level,'L1');assert.equal(s.groups,manifest.groups);assert.deepEqual(s.sliceY,[4.3,10.3]);
 assert.equal(s.groups.enclosure.glb,'interior/enclosure-l1.glb')});
test('Level 2 / Level 3 resolve to their own files and slices; an unlisted floor falls back to Level 1',()=>{const c=fns();
 for(const L of ['L2','L3']){const s=c.spec(manifest,L);assert.equal(s.level,L);assert.deepEqual(s.sliceY,manifest.levels[L].sliceY);
  for(const k of ['furniture','enclosure','floors','ceilings'])assert.equal(s.groups[k].glb,`interior/${k}-${L.toLowerCase()}.glb`);}
 const legacy={...manifest};delete legacy.levels;assert.equal(c.spec(legacy,'L2').level,'L1');
 assert.equal(c.spec(manifest,'L4').level,'L1')});
test('every manifest file exists and the level labels are honest',()=>{
 assert.match(manifest.provenance.label,/source design geometry, not surveyed as-built/);
 for(const [L,lv] of Object.entries(manifest.levels)){assert.match(lv.scope,/not surveyed as-built/);
  for(const e of Object.values(lv.groups)){assert.ok(fs.existsSync(path.join(__dirname,'..',e.glb)),e.glb);assert.ok(fs.existsSync(path.join(__dirname,'..',e.json)),e.json);
   assert.equal(fs.statSync(path.join(__dirname,'..',e.glb)).size,e.bytes);}}});
test('occluder floor: All floors and Level 1 keep Level 1 walls; Level 2/3 use their own; other floors none',()=>{const c=fns();
 for(const [f,want] of [[null,'L1'],['L1','L1'],['L2','L2'],['L3','L3'],['L4',null],['ROOF',null],['UNKNOWN',null]]){c.equipLevelFilter=f;assert.equal(c.occ(),want,String(f));}});
test('wiring: element floor drives the interior, lazy + cancel-safe, one floor at a time, overlay defers',()=>{
 assert.match(bim,/window\.setElementFloor = value => \{[^\n]*syncInteriorFloor\(equipLevelFilter\);/);
 assert.match(bim,/d\?\.type==='grimes-floor'&&splitPane==='bim'&&\['L1','L2','L3'\]\.includes\(d\.level\)\)\{setElementFloor\(d\.level\)/);
 const load=bim.match(/async function loadInterior\(\)\{[\s\S]*?\n}\n/)[0];
 assert.match(load,/const run=\+\+interiorState\.run/);assert.ok((load.match(/if\(!live\(\)\)/g)||[]).length>=3,'checks after each await');
 assert.match(load,/if\(!live\(\)\)\{disposeInteriorObject\(group\);return;\}/);assert.match(load,/finally\{if\(live\(\)\)interiorState\.loading=false\}/);
 assert.match(load,/interiorSpec\(manifest,level\)/);
 const set=bim.match(/window\.setInteriorLevel=level=>\{[\s\S]*?\n};/)[0];
 assert.match(set,/interiorState\.run\+\+/);assert.match(set,/disposeInteriorGroups\(\)/);assert.match(set,/if\(interiorState\.wanted&&!overlayOn\)loadInterior\(\)/);
 assert.match(bim,/const interiorState=\{[^\n]*level:'L1'/,'default floor is Level 1');
 /* the occluder keeps the Level 1 file name for Level 1 and is dropped / reloaded per floor */
 assert.match(bim,/const OV_OCC_L1_SOURCE='interior\/enclosure-l1\.glb \(Walls\)'/);
 assert.match(bim,/function ovOccluderFloorOk\(\)\{const l=ovOccluderLevel\(\);return !!l&&ovOcc\.level===l;\}/);
 assert.match(bim,/if\(run!==ovOcc\.run\)return;   \/\/ element floor changed during the download/);
 assert.match(bim,/Source design geometry, not surveyed as-built/);
 assert.match(compare,/elements \+ interior follow the photo floor/)});
