const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
for(const file of ['grimes-bim-viewer.html','scan-bim.html'])test(file+': measured history rejects missing readings, preserves zero and gaps',()=>{
 const s=fs.readFileSync(require('node:path').join(__dirname,'../'+file),'utf8');
 const code=s.match(/function normaliseMeterHistory\(series\) \{[\s\S]*?\n\}/);assert.ok(code,'history normaliser exists');
 const fn=vm.runInNewContext(code[0]+';normaliseMeterHistory',{bmoTimestamp:Date.parse});
 const out=fn([{t:'2026-09-17T01:00:00Z',v:3},{t:'bad',v:8},{t:'2026-09-17T00:00:00Z',v:0},{t:'2026-09-17T00:15:00Z',v:null},{t:'2026-09-17T00:30:00Z',v:'5'}]);
 assert.equal(out.length,2);assert.equal(out[0].v,0);assert.equal(out[1].at-out[0].at,3600000);
});
