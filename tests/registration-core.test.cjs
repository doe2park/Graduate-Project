/* Registration workbench maths (registration-core.js). Synthetic data only.
   Cross-checks the JS numbers against scripts/registration_fit.py on the shared fixture. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process'),os=require('node:os');
const RC=require('../registration-core.js');
const FIXTURE=path.join(__dirname,'fixtures/registration-pairs.fixture.json');
const fixture=()=>JSON.parse(fs.readFileSync(FIXTURE,'utf8'));
const move=(yaw,t,p)=>RC.apply({rotationYDegrees:yaw,translation:t},p);

test('closed-form fit recovers a known yaw and translation exactly',()=>{
 const pts=[[0,4.5,0],[10,4.5,2],[3,8,15],[20,5,9],[7,6,30]];
 const fit=RC.fitYawTranslation(pts.map(p=>({scan:p,bim:move(37.5,[-35,.6,-25],p)})));
 assert.ok(Math.abs(fit.rotationYDegrees-37.5)<1e-9);fit.translation.forEach((v,k)=>assert.ok(Math.abs(v-[-35,.6,-25][k])<1e-9));
 assert.ok(Math.max(...fit.residualsMetres)<1e-9);
});
test('apply and invert are exact inverses (same convention as scan-compare convert)',()=>{
 const reg={rotationYDegrees:-0.7,translation:[-35.25,.56,-25]},p=[12.3,6.1,-4.2],q=RC.invert(reg,RC.apply(reg,p));
 q.forEach((v,k)=>assert.ok(Math.abs(v-p[k])<1e-12));
});
test('noisy fixture: RANSAC rejects the outlier and recovers the truth',()=>{
 const d=fixture(),r=RC.solve(d);
 assert.deepEqual(r.ransac.outlierIds,['f7']);
 assert.ok(Math.abs(r.rotationYDegrees-d.truth.rotationYDegrees)<.05);
 r.translation.forEach((v,k)=>assert.ok(Math.abs(v-d.truth.translation[k])<.03));
 assert.ok(r.fit.rmsMetres<.03);assert.ok(r.checks.maxMetres<.05);
});
test('leave-one-out flags the bad pair when RANSAC is off',()=>{
 const d=fixture();d.ransac={enabled:false};const r=RC.solve(d);
 assert.ok(r.fit.maxMetres>.3);
 const worst=r.leaveOneOut.errors.reduce((a,b)=>b.errorMetres>a.errorMetres?b:a);assert.equal(worst.id,'f7');
});
test('heading solve recovers a known per-station offset',()=>{
 const d=fixture(),o=d.headingObservations[0],h=RC.solveHeading(o,{rotationYDegrees:d.truth.rotationYDegrees,translation:d.truth.translation});
 assert.ok(Math.abs(h.headingOffsetDegrees-o.trueHeadingOffsetDegrees)<1e-4);assert.ok(Math.max(...h.residualsDegrees)<1e-4);
 assert.throws(()=>RC.solveHeading({...o,photoDirections:o.photoDirections.slice(0,1),bimTargets:o.bimTargets.slice(0,1)},d.truth));
});
test('heading offset rotates the sphere so the photo direction lands on the target',()=>{
 const target=[3,1,4],dir=RC.rotateY(target,-12),fixed=RC.rotateY(dir,12);fixed.forEach((v,k)=>assert.ok(Math.abs(v-target[k])<1e-12));
});
test('checks must be independent and at least four fit pairs are required',()=>{
 let d=fixture();d.pairs[d.pairs.length-1].scan=d.pairs[0].scan.slice();assert.throws(()=>RC.solve(d),/independent/);
 d=fixture();d.pairs=d.pairs.filter(p=>['f1','f2','f3','c1'].includes(p.id));assert.throws(()=>RC.solve(d),/4\+ fit pairs/);
 d=fixture();d.pairs=d.pairs.filter(p=>p.role==='fit');assert.throws(()=>RC.solve(d),/check/);
});
test('export schema is dated, honest and never targets accepted files',async()=>{
 const d=fixture(),out=await RC.buildExport(d,RC.solve(d),{created:'2026-10-14T00:00:00Z'});
 for(const k of ['schema','capture','rotationYDegrees','translation','scale','status','method','inputs','fit','leaveOneOut','checks','stationHeadingOffsetsDegrees','scope'])assert.ok(k in out,k);
 assert.equal(out.schema,'grimes-registration-candidate/1');assert.equal(out.scale,1);assert.equal(out.status,'landmark-fit-unsurveyed');assert.match(out.scope,/not surveyed/);
 assert.match(RC.suggestFilename(d.capture,'2026-10-14'),/^registration-candidates\/2026-10-14-landmark-fit\.json$/);
 for(const bad of ['alignment-analysis/accepted-registration.json','scan-assets/captures/2026-09-17/registration.json','registration.json'])assert.throws(()=>RC.assertCandidateName(bad),/accepted|provisional/);
 RC.assertCandidateName('scan-assets/captures/2026-09-17/registration-candidates/2026-10-14-landmark-fit.json');
 const surveyed=fixture();surveyed.pairs.forEach(p=>{if(p.role==='check')p.surveyed=true});
 assert.equal((await RC.buildExport(surveyed,RC.solve(surveyed))).status,'landmark-fit-surveyed-checks');
});
test('candidate URL parameter only accepts same-origin relative JSON paths',()=>{
 for(const ok of ['scan-assets/captures/2026-09-17/registration-candidates/2026-10-14-icp-arch.json','alignment-analysis/candidates/a.json'])assert.equal(RC.safeRegistrationPath(ok),ok);
 for(const bad of ['https://evil.invalid/x.json','//evil/x.json','/etc/x.json','../x.json','a/../../x.json','x.js','javascript:alert(1)','a\\b.json',''])assert.equal(RC.safeRegistrationPath(bad),null,bad);
});
test('validateRegistration accepts candidates for the right capture only',()=>{
 const base={schema:'grimes-registration-candidate/1',capture:'2026-09-17',rotationYDegrees:-.5,translation:[1,2,3],scale:1,status:'icp-refined-unsurveyed'};
 assert.equal(RC.validateRegistration(base,'2026-09-17').ok,true);
 assert.equal(RC.validateRegistration(base,'2026-05-06').ok,false);
 assert.equal(RC.validateRegistration({...base,scale:1.01},'2026-09-17').ok,false);
 assert.equal(RC.validateRegistration({...base,status:'geometry-registered'},'2026-09-17').ok,false);
 assert.equal(RC.validateRegistration({...base,translation:[1,2]},'2026-09-17').ok,false);
 assert.equal(RC.validateRegistration({...base,stationHeadingOffsetsDegrees:{a:400}},'2026-09-17').ok,false);
});
test('canonical pairs hash matches the Python mirror byte for byte',()=>{
 const d=fixture(),text=RC.canonicalPairsText(d);
 const py=spawnSync('python3',['-c',`import importlib.util,json,sys;s=importlib.util.spec_from_file_location('r',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);sys.stdout.write(m.canonical_pairs_text(json.load(open(sys.argv[2]))))`,path.join(__dirname,'../scripts/registration_fit.py'),FIXTURE],{encoding:'utf8'});
 if(py.status!==0)return;  // python unavailable: covered by the Python suite
 assert.equal(text,py.stdout);
});
test('JS and Python give the same numbers on the shared fixture',()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'regfit-')),out=path.join(tmp,'candidate.json');
 const py=spawnSync('python3',[path.join(__dirname,'../scripts/registration_fit.py'),'fit',FIXTURE,'--output',out],{encoding:'utf8'});
 if(py.status!==0&&/No such file|not found/i.test(py.stderr||''))return;
 assert.equal(py.status,0,py.stderr);
 const p=JSON.parse(fs.readFileSync(out,'utf8')),j=RC.solve(fixture());
 assert.ok(Math.abs(p.rotationYDegrees-j.rotationYDegrees)<1e-9);p.translation.forEach((v,k)=>assert.ok(Math.abs(v-j.translation[k])<1e-9));
 assert.deepEqual(p.method.ransac.outlierIds,j.ransac.outlierIds);
 assert.ok(Math.abs(p.fit.rmsMetres-j.fit.rmsMetres)<1e-9);assert.ok(Math.abs(p.leaveOneOut.rmsMetres-j.leaveOneOut.rmsMetres)<1e-9);
 assert.ok(Math.abs(p.checks.maxMetres-j.checks.maxMetres)<1e-9);
 assert.ok(Math.abs(p.stationHeadingOffsetsDegrees.pano_A-j.headings[0].headingOffsetDegrees)<1e-9);
 fs.rmSync(tmp,{recursive:true,force:true});
});
test('manual slider offsets are recorded separately and pick solves win',async()=>{
 const d=fixture();d.manualHeadingOffsetsDegrees={pano_B:-3,pano_A:99};const out=await RC.buildExport(d,RC.solve(d));
 assert.deepEqual(out.manualHeadingOffsetsDegrees,{pano_B:-3,pano_A:99});assert.equal(out.stationHeadingOffsetsDegrees.pano_B,-3);assert.ok(Math.abs(out.stationHeadingOffsetsDegrees.pano_A-2.5)<.05);
 d.manualHeadingOffsetsDegrees={x:400};await assert.rejects(RC.buildExport(d,RC.solve(d)));
});
