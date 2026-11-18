const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../scan-xr.html'),'utf8'),MR=require('../twin/mr-align.js');
test('MR layers have nine readable targets rather than a sparse twenty-slot expert grid',()=>{
 const source=html.slice(html.indexOf('const MR_SIMPLE='),html.indexOf('async function mrButton('));
 const keys=['equipment','duct','mech','plumbing','conduit','receptacles','lighting','fire'];
 const ctx={MR,mr:{page:'layers'},OVERLAY_LAYER_KEYS:keys,LAYERS:Object.fromEntries(keys.map(k=>[k,{label:k}])),layerState:{},mrLayerOn:()=>false};
 vm.createContext(ctx);vm.runInContext(source+';globalThis.layout=mrLayout();globalThis.buttons=mrButtons();',ctx);
 assert.equal(ctx.layout.cols,3);assert.equal(ctx.layout.rows,3);assert.equal(ctx.buttons.length,9);assert.match(ctx.buttons[8],/Back/);
 assert.ok(ctx.buttons.every(Boolean),'no blank cells between systems and Back');
 for(let i=0;i<9;i++){const r=MR.gridRect(ctx.layout,i);assert.ok(r.h>.2,'large enough vertical target');assert.equal(MR.gridHit(ctx.layout,r.x+r.w/2,1-r.y-r.h/2),i);}
});
test('status notifications dock above an open menu rather than covering action buttons',()=>{
 const source=html.slice(html.indexOf('const TOAST_FONT='),html.indexOf('let picked=null'));
 const node=()=>({parent:null,position:{set(x,y,z){Object.assign(this,{x,y,z});}},rotation:{set(){}},scale:{setScalar(){}},add(n){n.parent=this;}});
 const camera=node(),menu={mesh:node()},mrPanel={mesh:node()},mesh=node();
 const ctx2={clearRect(){},measureText:t=>({width:t.length*20}),beginPath(){},roundRect(){},fill(){},stroke(){},fillText(){}};
 const surf={mesh,texture:{},ctx:ctx2,W:1024,H:170};
 const ctx={makeSurface:()=>surf,camera,menu,mrPanel,state:{menu:true},mr:{panel:false},MODE_AR:false,MENU_H:.4,
 renderer:{xr:{isPresenting:true}},X:{toastLines:t=>[t]},setTimeout:()=>0,clearTimeout(){},invalidate(){}};
 vm.createContext(ctx);vm.runInContext(source+';xrToast("Move cancelled");',ctx);
 assert.equal(mesh.parent,menu.mesh);assert.ok(mesh.position.y>.2,'toast above menu top');
 ctx.state.menu=false;ctx.MODE_AR=true;ctx.mr.panel=true;vm.runInContext('xrToast("Saved");',ctx);
 assert.equal(mesh.parent,mrPanel.mesh);assert.ok(mesh.position.y>.5625/2,'toast above MR panel');
 ctx.mr.panel=false;vm.runInContext('xrToast("Services ready");',ctx);assert.equal(mesh.parent,camera);
});
