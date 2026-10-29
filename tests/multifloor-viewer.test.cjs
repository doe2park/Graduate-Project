/* Multi-floor Oct 18 (2026-10-20; Level 2 / 3 published 2026-10-28): stair edges in scan-photo, floor selection (L2 / L3 public,
   floors=all local-only) and floor following in scan-compare, floor message in scan-bim. Pure extraction tests; the local package itself is checked when present. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const read=f=>fs.readFileSync(path.join(__dirname,'..',f),'utf8');
const photo=read('scan-photo.html'),compare=read('scan-compare.html'),bim=read('scan-bim.html');
function photoFns(){const a=photo.match(/function chooseWalkNeighbor\([\s\S]*?\n}/)[0],b=photo.match(/function chooseStairNeighbor\([\s\S]*?\n}/)[0],c=photo.match(/function readNavLimits\([^\n]*/)[0];const ctx={};vm.createContext(ctx);vm.runInContext(a+b+c+';this.walk=chooseWalkNeighbor;this.stair=chooseStairNeighbor;this.limits=readNavLimits;',ctx);return ctx}
function floorBlock(){const m=compare.match(/\/\* MULTI-FLOOR PREVIEW[\s\S]*?\*\/([\s\S]*?)\/\* END MULTI-FLOOR PREVIEW \*\//);assert.ok(m,'multi-floor block exists');const ctx={URLSearchParams};vm.createContext(ctx);vm.runInContext(m[1]+';this.sel=multiFloorSelection;this.floor=floorForHeight;this.path=FLOORS_MANIFEST;this.per=FLOOR_MANIFESTS;this.local=localFloorSelection;',ctx);return ctx}
const nodes=()=>[{position:[0,16.3,0],neighbors:[1,2],stairs:[2]},{position:[0,16.3,-4]},{position:[0,14.6,3.5],neighbors:[0,3],stairs:[0,3]},{position:[0,12.6,7]},{position:[0,7,-1],neighbors:[5]},{position:[0,7,-7]}];

test('without stair flags or limits the original 5.5 m / 1.5 m rule is unchanged',()=>{const f=photoFns(),n=nodes();delete n[0].stairs;
 assert.equal(f.walk(n,0,[0,0,1]),-1);assert.equal(f.walk(n,0,[0,0,-1]),1);assert.equal(f.walk(n,4,[0,0,-1]),-1)});
test('stair neighbours accept a larger rise only when flagged',()=>{const f=photoFns(),n=nodes(),L={maxStep:7.7,maxRise:1.5,stairStep:9,stairRise:4.6};
 assert.equal(f.walk(n,0,[0,0,1],L),2);assert.equal(f.walk(n,2,[0,0,1],L),3);assert.equal(f.walk(n,4,[0,0,-1],L),5);
 const m=nodes();m[2].stairs=[];assert.equal(f.walk(m,2,[0,0,1],L),-1)});
test('PgUp / PgDn choose a rising or falling stair neighbour',()=>{const f=photoFns(),n=nodes();
 assert.equal(f.stair(n,2,1),0);assert.equal(f.stair(n,2,-1),3);assert.equal(f.stair(n,0,1),-1);assert.equal(f.stair(n,1,-1),-1)});
test('navigation limits from a manifest are validated',()=>{const f=photoFns();
 assert.equal(f.limits(null),null);assert.equal(f.limits({maxStep:'9'}),null);assert.equal(f.limits({maxStep:40}),null);
 assert.equal(JSON.stringify(f.limits({maxStep:7.7,stairRise:4.6,x:1})),JSON.stringify({maxStep:7.7,stairRise:4.6}))});
test('multi-floor preview is Oct 18 + localhost + floors=all only, and points into ignored capture-local',()=>{const c=floorBlock();
 assert.equal(c.sel('?capture=2026-10-18&floors=all','localhost',{date:'2026-10-18'}).photo,c.path);
 assert.equal(c.sel('?capture=2026-10-18&floors=all','127.0.0.1',{date:'2026-10-18'}).photo,c.path);
 assert.equal(c.sel('?capture=2026-10-18&floors=all','doe2park.github.io',{date:'2026-10-18'}),null);
 assert.equal(c.sel('?capture=2026-09-17&floors=all','localhost',{date:'2026-09-17'}),null);
 assert.equal(c.sel('?capture=2026-10-18','localhost',{date:'2026-10-18'}),null);
 assert.match(c.path,/^capture-local\//);assert.match(read('.gitignore'),/capture-local/)});
test('BIM floor follows camera height with slab thresholds',()=>{const c=floorBlock();
 assert.equal(c.floor(7.2),'L1');assert.equal(c.floor(11.4),'L2');assert.equal(c.floor(16.3),'L3');assert.equal(c.floor(9.6),'L1');assert.equal(c.floor(NaN),null)});
test('scan-compare forwards the floor and scan-bim applies it to the element floor filter',()=>{
 assert.match(compare,/if\(floorsPreview\)followFloor\(/);assert.match(compare,/type:'grimes-floor',level:f/);
 assert.match(bim,/d\?\.type==='grimes-floor'&&splitPane==='bim'&&\['L1','L2','L3'\]\.includes\(d\.level\)\)\{setElementFloor\(d\.level\)/)});
test('the capture picker itself is unchanged (preview is a separate local button)',()=>{
 const opts=[...compare.match(/<select id="captureDate"[^>]*>([\s\S]*?)<\/select>/)[1].matchAll(/<option value="([^"]+)">/g)].map(m=>m[1]);
 assert.deepEqual(opts,['2026-10-18','2026-09-17','2026-05-06'])});
test('local multi-floor package (if built) is labelled provisional, keeps Level 1 intact and links floors by stairs',()=>{
 const f=path.join(__dirname,'..','capture-local/grimes-oct18-floors/panoramas/manifest.json');if(!fs.existsSync(f))return;
 const m=JSON.parse(fs.readFileSync(f,'utf8')),l1=JSON.parse(read('scan-assets/captures/2026-10-18/panoramas/manifest.json'));
 assert.equal(m.status,'local-preview');assert.match(m.alignment,/provisional, not surveyed/);assert.equal(m.exportedStations,m.stations.length);
 for(const [i,s] of l1.stations.entries()){assert.equal(m.stations[i].id,s.id);assert.deepEqual(m.stations[i].position,s.position);for(const n of s.neighbors)assert.ok(m.stations[i].neighbors.includes(n))}
 const lv=new Set(m.stations.map(s=>s.level));for(const l of ['L1','L2','L3'])assert.ok(lv.has(l),l);
 for(const [i,s] of m.stations.entries())for(const n of s.neighbors){assert.ok(m.stations[n].neighbors.includes(i),'symmetric '+i+'-'+n);if(s.stairs?.includes(n))assert.equal(s.edgeKinds[String(n)],'stairs')}
 // reachability: from the default Level 1 station, every level is reachable through the graph
 const seen=new Set([m.stations.findIndex(s=>s.id===m.defaultStation)]),q=[...seen];while(q.length){const i=q.shift();for(const n of m.stations[i].neighbors)if(!seen.has(n)){seen.add(n);q.push(n)}}
 for(const l of ['L2','L3'])assert.ok([...seen].some(i=>m.stations[i].level===l),'reachable '+l)});
/* 2026-10-28: Level 2 / Level 3 published (approved manual-blur photos), so ?floors=L2 / L3 works on every host */
test('one-floor view (?floors=L2 / L3) is Oct 18 only, on every host, and points into the published per-floor packages',()=>{const c=floorBlock();
 for(const host of ['127.0.0.1','localhost','doe2park.github.io','pages.emu'])for(const f of ['L2','L3']){const s=c.sel('?capture=2026-10-18&floors='+f,host,{date:'2026-10-18'});
  assert.equal(s.photo,c.per[f]);assert.equal(s.photo,'scan-assets/captures/2026-10-18/floors/'+f+'/panoramas/manifest.json');assert.equal(s.floors,f);assert.equal(s.published,true);
  assert.ok(fs.existsSync(path.join(__dirname,'..',s.photo)),s.photo);assert.equal(c.sel('?capture=2026-09-17&floors='+f,host,{date:'2026-09-17'}),null)}
 assert.equal(c.sel('?capture=2026-10-18&floors=L1','localhost',{date:'2026-10-18'}),null);assert.equal(c.sel('?capture=2026-10-18&floors=toString','doe2park.github.io',{date:'2026-10-18'}),null);
 assert.equal(c.sel('?capture=2026-10-18&floors=all','localhost',{date:'2026-10-18'}).floors,'all');assert.equal(c.sel('?capture=2026-10-18&floors=all','doe2park.github.io',{date:'2026-10-18'}),null);
 for(const p of Object.values(c.per))assert.doesNotMatch(p,/capture-local/);
 assert.match(compare,/id='floorsJump'/);assert.match(compare,/j\.id='floorPicker'/)});
test('the Oct 18 floor picker is offered on every host (Level 1 / 2 / 3, upper floors labelled provisional); the Levels 1-3 button stays localhost-only',()=>{
 const ui=compare.slice(compare.indexOf('/* Floor picker for the Oct 18 capture'),compare.indexOf('if(localCapture){const L='));
 assert.match(ui,/^\/\* Floor picker/);assert.match(ui,/if\(capture\.date==='2026-10-18'&&!localCapture\)\{/);
 assert.match(ui,/for\(const k of \['L1','L2','L3'\]\)j\.add\(new Option\(FLOOR_NAMES\[k\]\+\(k==='L1'\?'':' \\u00b7 provisional'\),k\)\)/);
 assert.match(ui,/' \\u00b7 provisional, not surveyed'/);assert.match(ui,/not a Cupix export/);assert.match(ui,/not a claim of full anonymisation/);
 assert.doesNotMatch(ui,/placed without Cupix|Cupix-free placement/,'v2 positions are fitted to Cupix-placed stations');
 assert.match(ui,/if\(\['localhost','127\.0\.0\.1'\]\.includes\(location\.hostname\)\)\{\s*const b=document\.createElement\('button'\);b\.type='button';b\.id='floorsToggle'/);
 assert.match(compare,/for\(const el of \[mode,capturePicker,\.\.\.\['floorPicker','floorsJump','floorsToggle','floorsNote'\]\.map\(id=>document\.getElementById\(id\)\)\]\)if\(el\)\(next==='overlay'\?overlayBar:scanTitle\)\.appendChild\(el\)/,'floor picker moves into the overlay bar with the capture picker')});
test('local per-floor packages (if built) hold one floor, symmetric edges, provisional labels',()=>{
 for(const f of ['L2','L3']){const p=path.join(__dirname,'..','capture-local/grimes-'+f+'-2026-10-18-v2/panoramas/manifest.json');if(!fs.existsSync(p))continue;
  const m=JSON.parse(fs.readFileSync(p,'utf8'));assert.equal(m.level,f);assert.equal(m.status,'local-preview');assert.match(m.alignment,/provisional, not surveyed/);assert.equal(m.exportedStations,m.stations.length);
  assert.ok(m.stations.some(s=>s.id===m.defaultStation));assert.notEqual(m.stations.find(s=>s.id===m.defaultStation).level,'stairs');
  for(const [i,s] of m.stations.entries()){assert.equal(s.packageFloor,f);assert.ok([f,'stairs'].includes(s.level));for(const n of s.neighbors)assert.ok(m.stations[n].neighbors.includes(i),'symmetric '+i+'-'+n)}
  const reg=JSON.parse(fs.readFileSync(path.join(path.dirname(p),'..','registration.json'),'utf8'));assert.equal(reg.status,'candidate-not-surveyed')}});
test('Cupix-free local captures (?capture=<unpublished date>&floors=L1|L2|L3) are localhost-only and point into capture-local',()=>{const c=floorBlock(),pub=['2026-10-18','2026-09-17','2026-05-06'];
 const s=c.local('?capture=2026-10-28&floors=L2','localhost',pub);assert.equal(s.photo,'capture-local/grimes-L2-2026-10-28/panoramas/manifest.json');assert.equal(s.registration,'capture-local/grimes-L2-2026-10-28/registration.json');assert.equal(s.date,'2026-10-28');
 assert.equal(c.local('?capture=2026-10-18-nocupix&floors=L3','127.0.0.1',pub).photo,'capture-local/grimes-L3-2026-10-18-nocupix/panoramas/manifest.json');
 assert.equal(c.local('?capture=2026-10-28&floors=L2','doe2park.github.io',pub),null);
 assert.equal(c.local('?capture=2026-10-18&floors=L2','localhost',pub),null,'published dates keep their own preview');
 assert.equal(c.local('?capture=2026-10-28&floors=all','localhost',pub),null);
 for(const bad of ['../x','2026-10-28/../../etc','2026-10-28-UPPER','2026-1-28'])assert.equal(c.local('?capture='+encodeURIComponent(bad)+'&floors=L2','localhost',pub),null,bad);
 assert.match(compare,/localFloorSelection\(location\.search,location\.hostname,Object\.keys\(CAPTURE_SHORT\)\)/)});
test('local Cupix-free packages (if built) carry an identity registration the viewer accepts and stay labelled provisional',()=>{
 const dir=path.join(__dirname,'..','capture-local');if(!fs.existsSync(dir))return;
 for(const d of fs.readdirSync(dir).filter(n=>/^grimes-L[123]-\d{4}-\d{2}-\d{2}-nocupix$/.test(n)||/^grimes-L[123]-2026-10-28/.test(n))){
  const reg=JSON.parse(fs.readFileSync(path.join(dir,d,'registration.json'),'utf8')),m=JSON.parse(fs.readFileSync(path.join(dir,d,'panoramas/manifest.json'),'utf8'));
  assert.equal(reg.status,'project-frame-provisional');assert.equal(reg.rotationYDegrees,0);assert.deepEqual(reg.translation,[0,0,0]);assert.match(reg.label,/provisional, not surveyed/);
  assert.equal(m.status,'local-preview');assert.equal(m.exportedStations,m.stations.length);assert.ok(m.stations.some(s=>s.id===m.defaultStation));
  for(const [i,s] of m.stations.entries()){assert.deepEqual(s.position,s.positionBIM);for(const n of s.neighbors)assert.ok(m.stations[n].neighbors.includes(i),d+' symmetric '+i+'-'+n)}}});
