/* Multi-floor Oct 18 preview (2026-10-20): stair edges in scan-photo, local-only selection and floor following in
   scan-compare, floor message in scan-bim. Pure extraction tests; the local package itself is checked when present. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const read=f=>fs.readFileSync(path.join(__dirname,'..',f),'utf8');
const photo=read('scan-photo.html'),compare=read('scan-compare.html'),bim=read('scan-bim.html');
function photoFns(){const a=photo.match(/function chooseWalkNeighbor\([\s\S]*?\n}/)[0],b=photo.match(/function chooseStairNeighbor\([\s\S]*?\n}/)[0],c=photo.match(/function readNavLimits\([^\n]*/)[0];const ctx={};vm.createContext(ctx);vm.runInContext(a+b+c+';this.walk=chooseWalkNeighbor;this.stair=chooseStairNeighbor;this.limits=readNavLimits;',ctx);return ctx}
function floorBlock(){const m=compare.match(/\/\* MULTI-FLOOR PREVIEW[\s\S]*?\*\/([\s\S]*?)\/\* END MULTI-FLOOR PREVIEW \*\//);assert.ok(m,'multi-floor block exists');const ctx={URLSearchParams};vm.createContext(ctx);vm.runInContext(m[1]+';this.sel=multiFloorSelection;this.floor=floorForHeight;this.path=FLOORS_MANIFEST;',ctx);return ctx}
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
