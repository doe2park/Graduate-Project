const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../scan-bim.html'),'utf8');
const code=source.slice(source.indexOf('// Scan quality policy'),source.indexOf("document.body.dataset.quality="));
const legacy=source.match(/const mobileQuality=.*;/)[0];
for(const [name,frame,top,coarse,expected] of [['desktop split',680,1386,false,false],['phone',390,390,true,true],['tablet',820,820,true,true],['narrow desktop',600,600,false,true]]){
 const media=width=>query=>({matches:query.includes('pointer:coarse')&&coarse||query.includes('max-width:768px')&&width<=768});
 const actual=vm.runInNewContext((code||legacy)+';mobileQuality',{window:{matchMedia:media(frame),top:{location:{origin:'local'},matchMedia:media(top)}},location:{origin:'local'},matchMedia:media(frame)});
 assert.equal(actual,expected,name);
}
console.log('Quality policy: 4 cases passed');
