const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync(require('node:path').join(__dirname,'../scan-compare.html'),'utf8');
function select(q){const block=src.match(/\/\* CAPTURE SELECTION \*\/([\s\S]*?)\/\* END CAPTURE SELECTION \*\//);assert.ok(block,'dated capture selection exists');const c={URLSearchParams};vm.createContext(c);vm.runInContext(block[1],c);return c.captureSelection(q)}
test('latest capture selects its own photos, mesh and provisional registration',()=>{const c=select('');assert.equal(c.date,'2026-09-17');assert.match(c.photo,/2026-09-17/);assert.match(c.registration,/2026-09-17/);assert.match(c.mesh,/capture=2026-09-17/);assert.equal(c.provisional,true)});
test('old capture remains available with original registration',()=>{const c=select('?capture=2026-05-06');assert.equal(c.photo,'scan-assets/panoramas/manifest.json');assert.equal(c.registration,'alignment-analysis/accepted-registration.json');assert.equal(c.provisional,false)});
test('Gaussian experiment cannot be presented as September reconstruction',()=>{const c=select('?mode=splat&capture=2026-09-17');assert.equal(c.date,'2026-05-06')});
test('unrecognized capture values cannot inject asset paths',()=>{assert.equal(select('?capture=https://evil.invalid/x').date,'2026-09-17')});
