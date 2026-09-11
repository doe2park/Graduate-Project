const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const s=fs.readFileSync(require('node:path').join(__dirname,'../scan-bim.html'),'utf8');
const code=s.slice(s.indexOf('function exitWalk()')).match(/scanRoot.traverse\([^\n]+/)[0];
for(const pane of ['scan',null]){
 const object={isMesh:true,material:{opacity:1,depthWrite:true}};
 vm.runInNewContext(code,{scanRoot:{traverse:fn=>fn(object)},splitPane:pane,document:{getElementById:()=>({value:pane==='scan'?1:.65})}});
 assert.equal(object.material.depthWrite,pane==='scan','opaque scan must retain depth occlusion after walking');
}
console.log('Scan depth policy passed');
