const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
for(const file of ['grimes-bim-viewer.html','scan-bim.html']){
 function setup(walk,loading,mobile=false){let cb,renders=0;const ctx={walkMode:walk,layerState:{equipment:{loading}},interiorState:{loading:false},mobileMq:{matches:mobile},linkedPose:null,lastSyncAt:0,Date,controls:{update(){}},updateWalk(){},publishScanPose(){},scene:{},camera:{},renderer:{setAnimationLoop(fn){cb=fn},render(){renders++}}};vm.createContext(ctx);const html=fs.readFileSync(file,'utf8');vm.runInContext(html.slice(html.lastIndexOf('let _lastT = 0'),html.lastIndexOf('</script>')),ctx);return {frame:t=>cb(t),count:()=>renders,ctx}}
 test(file+': Walk renders during loading, at a bounded rate',()=>{const s=setup(true,true);s.frame(1000);assert.equal(s.count(),1);s.frame(1050);assert.equal(s.count(),1);s.frame(1500);assert.equal(s.count(),2)});
 test(file+': non-Walk loading still avoids render churn',()=>{const s=setup(false,true);s.frame(1000);s.frame(1500);assert.equal(s.count(),0);s.ctx.layerState.equipment.loading=false;s.frame(1516);assert.equal(s.count(),1)});
 test(file+': mobile Walk loading is throttled',()=>{const s=setup(true,true,true);s.frame(1000);s.frame(1250);assert.equal(s.count(),1);s.frame(1450);assert.equal(s.count(),2)});
}
