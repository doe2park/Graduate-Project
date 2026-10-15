/* scan-compare ?registration= preview of a candidate registration (workbench / ICP output). */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../scan-compare.html'),'utf8'),photo=fs.readFileSync(path.join(__dirname,'../scan-photo.html'),'utf8');
const RegistrationCore=require('../registration-core.js');
function block(){const m=src.match(/\/\* REGISTRATION OVERRIDE[^*]*\*\/([\s\S]*?)\/\* END REGISTRATION OVERRIDE \*\//);assert.ok(m,'override block exists');const c={URLSearchParams,RegistrationCore};vm.createContext(c);vm.runInContext(m[1],c);return c;}
test('no parameter keeps the accepted / provisional default',()=>{assert.equal(block().registrationOverride(''),null);assert.equal(block().registrationOverride('?capture=2026-05-06'),null)});
test('candidate path must be a same-origin relative JSON file',()=>{const c=block();
 assert.equal(c.registrationOverride('?registration=scan-assets/captures/2026-09-17/registration-candidates/2026-10-14-icp-arch.json'),'scan-assets/captures/2026-09-17/registration-candidates/2026-10-14-icp-arch.json');
 for(const bad of ['https://evil.invalid/a.json','//evil/a.json','../a.json','/a.json','a.js'])assert.equal(c.registrationOverride('?registration='+encodeURIComponent(bad)),'invalid',bad)});
test('preview label never claims accepted or surveyed status',()=>{const l=block().previewLabel({status:'icp-refined-unsurveyed'});assert.match(l,/PREVIEW/);assert.match(l,/not the accepted/);assert.doesNotMatch(l.replace('unsurveyed',''),/surveyed|verified/i)});
test('heading offsets come only from the candidate object',()=>{const c=block();assert.deepEqual({...c.headingOffsets({stationHeadingOffsetsDegrees:{a:1.5}})},{a:1.5});assert.deepEqual({...c.headingOffsets(null)},{});assert.deepEqual({...c.headingOffsets({})},{})});
test('compare page loads the shared core, validates against the selected capture and falls back visibly',()=>{
 assert.match(src,/<script src="registration-core\.js[^"]*"><\/script>/);
 assert.match(src,/validateRegistration\(c,capture\.date\)/);assert.match(src,/Candidate rejected/);
 assert.match(src,/if\(date!==capture\.date\)u\.searchParams\.delete\('registration'\)/);
 assert.match(src,/'project-frame-provisional':'geometry-registered'/,'default status gate unchanged')});
test('photo pane applies bounded per-station heading offsets about +Y and exposes them for inspection',()=>{
 assert.match(photo,/grimes-heading-offsets/);assert.match(photo,/Math\.abs\(v\)<=180/);assert.match(photo,/setFromAxisAngle\(new THREE\.Vector3\(0,1,0\),d\*Math\.PI\/180\)\.multiply\(q\)/);assert.match(photo,/headingOffset:/)});
test('the shipped September ICP candidate validates for September only',()=>{
 const c=JSON.parse(fs.readFileSync(path.join(__dirname,'../scan-assets/captures/2026-09-17/registration-candidates/2026-10-14-icp-arch.json'),'utf8'));
 assert.equal(RegistrationCore.validateRegistration(c,'2026-09-17').ok,true);assert.equal(RegistrationCore.validateRegistration(c,'2026-05-06').ok,false);
 assert.equal(c.status,'icp-refined-unsurveyed');assert.match(c.scope,/not surveyed/)});
