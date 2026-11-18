const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../scan-bim.html'),'utf8');
const source=html.slice(html.indexOf("let lensPickCache="),html.indexOf('function lensPickRay('));
function fixture(){let calls=0;const ctx={anyLayerVisible:()=>true,
 camera:{position:{toArray:()=>[0,0,0]},quaternion:{toArray:()=>[0,0,0,1]},fov:65,aspect:1,zoom:1,projectionMatrix:{elements:[1,0,0,0,0,1,0,0,0,0,-1,-1,0,0,-.1,0]}},
 equipMeshes:[],asBuilt:{adjuster:{keys:()=>[]}},asBuiltRevision:0,equipLevelFilter:'all',equipTypeFilter:'all',layerState:{a:{group:{visible:true}}},
 overlayOn:true,ovPreset:{key:'room'},ovOcc:{state:'ready'},ovLensCss:{on:true},lensPickRay:()=>({id:String(++calls)})};
 vm.createContext(ctx);vm.runInContext(source,ctx);return {ctx,calls:()=>calls};}
test('lens picking reuses unchanged rays but invalidates after a resize projection change',()=>{
 const f=fixture(),first=f.ctx.lensPick(.75,.5);assert.equal(f.ctx.lensPick(.75,.5),first);assert.equal(f.calls(),1);
 f.ctx.camera.aspect=2;f.ctx.camera.projectionMatrix.elements[0]/=2;
 assert.notEqual(f.ctx.lensPick(.75,.5),first,'resizing changes the off-centre ray and must raycast again');
});
test('lens picking invalidates after zoom or view-offset projection changes',()=>{
 const f=fixture(),first=f.ctx.lensPick(.75,.5);f.ctx.camera.zoom=2;f.ctx.camera.projectionMatrix.elements[0]*=2;
 const zoomed=f.ctx.lensPick(.75,.5);assert.notEqual(zoomed,first);
 f.ctx.camera.projectionMatrix.elements[8]=.2;assert.notEqual(f.ctx.lensPick(.75,.5),zoomed);
});
