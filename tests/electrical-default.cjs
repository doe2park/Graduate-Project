const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../scan-bim.html'),'utf8');
const line=source.match(/const mobileMq = .*;/)[0];
assert.equal(vm.runInNewContext(line+';mobileMq.matches',{window:{matchMedia:()=>({matches:true})},qualityWindow:{matchMedia:()=>({matches:false})}}),false,'desktop split must load all element layers');
console.log('Desktop split loading policy passed');
