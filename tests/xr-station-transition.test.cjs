/* Exercise the real page transition with controlled async texture/fade boundaries. */
const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../scan-xr.html'),'utf8');
const source=html.slice(html.indexOf('async function openStation('),html.indexOf('/* Put the tracked head exactly on the capture station'));
function fixture(){
 let resolveFade,disposed=0;
 const old={dispose(){}},tex={dispose(){disposed++;}},el={};
 const ctx={stations:[{position:[0,0,0]},{position:[1,0,0]}],active:0,busyStation:false,pendingStation:null,captureEpoch:1,
  clamp:(v,a,b)=>Math.min(b,Math.max(a,v)),gauss:{scene:'photo'},status(){},photoURL:()=>'/photo.jpg',
  texLoader:{loadAsync:async()=>tex},THREE:{SRGBColorSpace:'srgb'},fade:to=>to===0?new Promise(r=>{resolveFade=r;}):Promise.resolve(),
  hideCard(){},sphereMat:{map:old,color:{setScalar(){}}},sphere:{position:{fromArray(){}},quaternion:{fromArray(){}},visible:true},
  X:{stationQuaternion:()=>[0,0,0,1],applyReg:()=>[0,0,0]},placeRig(){},reg:{},updateRadius(){},$:()=>el,
  timing:{firstPhotoMs:1},xrSession:null,capture:{label:'new',provisional:false},U:{fade:{value:0}},fader:{visible:false},
  prefetchNeighbors(){},state:{menu:false},invalidate(){},console:{error(e){throw e;}}};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 return {ctx,old,tex,disposed:()=>disposed,finishFade:()=>resolveFade()};
}
test('a capture changed during the fade cannot install the previous capture photo or station',async()=>{
 const f=fixture(),p=f.ctx.openStation(1);await new Promise(setImmediate);
 f.ctx.captureEpoch++; // a different capture was selected while the old photo faded out
 f.finishFade();await p;
 assert.equal(f.ctx.sphereMat.map,f.old,'discard the stale texture instead of pairing it with the new registration');
 assert.equal(f.ctx.active,0,'the stale station must not become active');
 assert.equal(f.disposed(),1,'discarded GPU texture is released');
 assert.equal(f.ctx.busyStation,false,'later station navigation remains available');
});
test('an unchanged capture completes the station transition normally',async()=>{
 const f=fixture(),p=f.ctx.openStation(1);await new Promise(setImmediate);f.finishFade();await p;
 assert.equal(f.ctx.sphereMat.map,f.tex);assert.equal(f.ctx.active,1);assert.equal(f.disposed(),0);assert.equal(f.ctx.busyStation,false);
});
test('switching to Gaussian during a photo fade also discards the stale photo',async()=>{
 const f=fixture(),p=f.ctx.openStation(1);await new Promise(setImmediate);f.ctx.gauss.scene='gaussian';f.finishFade();await p;
 assert.equal(f.ctx.sphereMat.map,f.old);assert.equal(f.ctx.active,0);assert.equal(f.disposed(),1);assert.equal(f.ctx.U.fade.value,1);
});
