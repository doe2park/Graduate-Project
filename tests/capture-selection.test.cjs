const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync(require('node:path').join(__dirname,'../scan-compare.html'),'utf8');
function select(q){const block=src.match(/\/\* CAPTURE SELECTION \*\/([\s\S]*?)\/\* END CAPTURE SELECTION \*\//);assert.ok(block,'dated capture selection exists');const c={URLSearchParams};vm.createContext(c);vm.runInContext(block[1],c);return c.captureSelection(q)}
test('latest capture selects its own photos, mesh and provisional registration',()=>{const c=select('');assert.equal(c.date,'2026-09-17');assert.match(c.photo,/2026-09-17/);assert.match(c.registration,/2026-09-17/);assert.match(c.mesh,/capture=2026-09-17/);assert.equal(c.provisional,true)});
test('old capture remains available with original registration',()=>{const c=select('?capture=2026-05-06');assert.equal(c.photo,'scan-assets/panoramas/manifest.json');assert.equal(c.registration,'alignment-analysis/accepted-registration.json');assert.equal(c.provisional,false)});
test('Gaussian experiment cannot be presented as September reconstruction',()=>{const c=select('?mode=splat&capture=2026-09-17');assert.equal(c.date,'2026-09-17');assert.equal(c.gaussian,null);assert.equal(c.display,'photo');assert.equal(c.splatRefused,true)});
test('unrecognized capture values cannot inject asset paths',()=>{assert.equal(select('?capture=https://evil.invalid/x').date,'2026-09-17')});
test('Oct 18 capture selects its own photos and provisional registration; May and Sep unchanged',()=>{const c=select('?capture=2026-10-18');assert.equal(c.date,'2026-10-18');assert.equal(c.photo,'scan-assets/captures/2026-10-18/panoramas/manifest.json');assert.equal(c.registration,'scan-assets/captures/2026-10-18/registration.json');assert.equal(c.provisional,true);assert.equal(select('?capture=2026-09-17').photo,'scan-assets/captures/2026-09-17/panoramas/manifest.json');assert.equal(select('?capture=2026-05-06').provisional,false)});
test('Oct 18 Gaussian is its own zone index, never the May scene',()=>{const c=select('?mode=splat&capture=2026-10-18');assert.equal(c.date,'2026-10-18');assert.equal(c.display,'splat');assert.equal(c.gaussian.kind,'zones');assert.equal(c.gaussian.path,'scan-assets/gaussian/2026-10-18/zones/index.json');assert.doesNotMatch(c.gaussian.path,/2026-05-06/)});
test('capture picker lists every selectable date, Oct and Sep labelled provisional',()=>{const opts=[...src.match(/<select id="captureDate"[^>]*>([\s\S]*?)<\/select>/)[1].matchAll(/<option value="([^"]+)">([^<]+)<\/option>/g)].map(m=>[m[1],m[2]]);assert.deepEqual(opts.map(o=>o[0]),['2026-10-18','2026-09-17','2026-05-06']);for(const [d,l] of opts){assert.equal(select('?capture='+d).date,d);if(d!=='2026-05-06')assert.match(l,/Provisional/)}});
test('every provisional capture package exists with project-frame-provisional status',()=>{const fsp=require('node:path');for(const d of ['2026-09-17','2026-10-18']){const c=select('?capture='+d),r=JSON.parse(fs.readFileSync(fsp.join(__dirname,'..',c.registration),'utf8')),m=JSON.parse(fs.readFileSync(fsp.join(__dirname,'..',c.photo),'utf8'));assert.equal(r.status,'project-frame-provisional');assert.equal(m.captureDate,d);assert.equal(m.exportedStations,m.stations.length)}});

/* capture-aware Gaussian (2026-10-19) */
function block(){const m=src.match(/\/\* CAPTURE SELECTION \*\/([\s\S]*?)\/\* END CAPTURE SELECTION \*\//);const c={URLSearchParams};vm.createContext(c);vm.runInContext(m[1]+';this.gaussianOptionLabel=gaussianOptionLabel;this.gaussianZoneSummary=gaussianZoneSummary;',c);return c}
test('old ?mode=splat links without a capture still open the May Gaussian; May keeps its single public manifest',()=>{
 for(const q of ['?mode=splat','?mode=splat&capture=bogus']){const c=select(q);assert.equal(c.date,'2026-05-06');assert.equal(c.display,'splat');assert.equal(c.gaussian.kind,'manifest');assert.equal(c.gaussian.path,'scan-assets/gaussian/2026-05-06/viewer.json');assert.equal(c.provisional,false)}
 const may=select('?mode=splat&capture=2026-05-06');assert.equal(may.display,'splat');assert.equal(may.registration,'alignment-analysis/accepted-registration.json')});
test('photo stays the default display for every date; no Gaussian is chosen unless asked',()=>{
 assert.equal(select('').date,'2026-09-17');for(const d of ['2026-05-06','2026-09-17','2026-10-18']){const c=select('?capture='+d);assert.equal(c.display,'photo');assert.equal(c.splatRefused,false)}
 assert.equal(select('?capture=2026-09-17&mode=photo').gaussian,null)});
test('Gaussian option label names the capture and stays experimental; Sep says it has none',()=>{const c=block();
 assert.equal(c.gaussianOptionLabel(select('?capture=2026-09-17')),'Gaussian · no Gaussian for this capture');
 assert.match(c.gaussianOptionLabel(select('?capture=2026-10-18')),/^Gaussian · Oct 18 zones \(experimental\)$/);
 assert.match(c.gaussianOptionLabel(select('?capture=2026-05-06')),/^Gaussian · May 6 \(experimental\)$/)});
test('zone index summary lists only trained zones and refuses non-experimental or malformed indexes',()=>{const c=block();
 const ok={schema:1,frame:'scan-y-up-metres',status:'experimental-trained',zones:[{id:'l1-a',name:'Zone A',manifest:'l1-a/viewer.json'}]};
 const s=c.gaussianZoneSummary(ok);assert.equal(s.zones.length,1);assert.match(s.note,/only Zone A trained/);assert.match(s.note,/other areas have no Gaussian/);
 assert.match(c.gaussianZoneSummary({...ok,zones:[...ok.zones,{id:'l1-b',name:'Zone B',manifest:'l1-b/viewer.json'}]}).note,/2 zones trained: Zone A, Zone B/);
 for(const bad of [null,{...ok,schema:2},{...ok,frame:'bim'},{...ok,zones:[]},{...ok,status:'surveyed'},{...ok,zones:[{id:'x'}]}])assert.throws(()=>c.gaussianZoneSummary(bad))});
test('the local Oct 18 zone package (if present) matches the publish format and the viewer rules',()=>{
 const p=require('node:path'),dir=p.join(__dirname,'../scan-assets/gaussian/2026-10-18/zones');if(!fs.existsSync(p.join(dir,'index.json')))return;
 const idx=JSON.parse(fs.readFileSync(p.join(dir,'index.json'),'utf8')),c=block();
 assert.equal(idx.schema,1);assert.equal(idx.capture,'2026-10-18');assert.equal(idx.status,'experimental-trained');assert.equal(idx.alignment,'project-frame-provisional');assert.match(idx.scope,/not surveyed/);
 c.gaussianZoneSummary(idx);
 for(const z of idx.zones){const m=JSON.parse(fs.readFileSync(p.join(dir,z.manifest),'utf8'));assert.equal(m.status,'experimental-trained');assert.equal(m.frame,'scan-y-up-metres');assert.equal(m.capture,'2026-10-18');
  for(const f of [m.file,m.mobileFile])assert.ok(fs.statSync(p.join(dir,p.dirname(z.manifest),f)).size>0,f)}});
test('date switches carry a Gaussian request and the viewpoint; mode switches keep the date',()=>{
 assert.match(src,/capturePicker\.onchange=\(\)=>navigateCapture\(capturePicker\.value,mode\.value==='splat'\|\|capture\.splatRefused\?'splat':'photo'\)/);
 assert.match(src,/mode\.onchange=\(\)=>navigateCapture\(capture\.date,mode\.value\)/);
 assert.doesNotMatch(src,/mode\.value==='splat'\?'2026-05-06'/);
 assert.match(src,/u\.searchParams\.set\('at',encodeAt\(p\)\)/)});
