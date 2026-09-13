// Actual local optimized PLY required. Set SPLAT_PACKAGE to a repository-relative viewer.json.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),base=process.env.SPLAT_TEST_ORIGIN||'http://127.0.0.1:8893';
const manifestPath=process.env.SPLAT_PACKAGE||'capture-local/gaussian/pilot/viewer.json';
const manifest=JSON.parse(fs.readFileSync(path.join(root,manifestPath)));
const registration=JSON.parse(fs.readFileSync(path.join(root,'alignment-analysis/accepted-registration.json')));
function registered(pose){
 const a=registration.rotationYDegrees*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
 const [x,y,z]=pose.position,t=registration.translation,[qx,qy,qz,qw]=pose.quaternion,h=Math.sin(a/2),w=Math.cos(a/2);
 return {position:[c*x+s*z+t[0],y+t[1],-s*x+c*z+t[2]],quaternion:[w*qx+h*qz,w*qy+h*qw,w*qz-h*qx,w*qw-h*qy]};
}
const distance=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try{
  const mobile=process.env.SPLAT_MOBILE==='1';
  const page=await browser.newPage(mobile?{viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:2}:{viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const manifestURL=new URL(manifestPath,base+'/');
  await page.route(url=>url.pathname==='/capture-local/gaussian/pilot/viewer.json',route=>route.fulfill({json:{...manifest,file:new URL(manifest.file,manifestURL).pathname,...(manifest.mobileFile?{mobileFile:new URL(manifest.mobileFile,manifestURL).pathname}:{})}}));
  await page.goto(base+'/scan-compare.html?mode=splat');
  await page.waitForFunction(()=>document.querySelector('#scanMode').value==='splat');
  const splat=page.frames().find(f=>f.url().includes('scan-splat')),bim=page.frames().find(f=>f.url().includes('pane=bim'));
  await splat.waitForFunction(()=>window.splatInspection?.().state==='ready',null,{timeout:180000});
  await bim.waitForFunction(()=>window.interiorInspection?.().ready&&scanInspection().camera.linked,null,{timeout:180000});
  async function aligned(label){
   await page.waitForTimeout(400);
   const scan=await splat.evaluate(()=>splatInspection()),model=await bim.evaluate(()=>scanInspection().camera),expected=registered(scan.camera);
   assert.ok(distance(expected.position,model.position)<1e-5,label+' position');
   assert.ok(Math.min(distance(expected.quaternion,model.quaternion),distance(expected.quaternion,model.quaternion.map(v=>-v)))<1e-5,label+' orientation');
   assert.ok(Math.abs(scan.camera.fov-model.fov)<1e-5,label+' field of view');
   return scan;
  }
  const initial=await aligned('initial');assert.equal(initial.mobile,mobile);
  if(mobile){
   assert.equal(initial.count,manifest.mobileSplatCount,'mobile derivative count');
   const pad=await splat.locator('[data-move=forward]').boundingBox();await page.mouse.move(pad.x+10,pad.y+10);await page.mouse.down();await page.waitForTimeout(500);await page.mouse.up();
  }else{
   await splat.locator('canvas').click({position:{x:200,y:250}});await page.keyboard.down('w');await page.waitForTimeout(500);await page.keyboard.up('w');
  }
  const moved=await aligned('Gaussian movement');assert.ok(distance(initial.camera.position,moved.camera.position)>.1,'Gaussian actually moves');
  await bim.locator('#bimNavigate').click();await bim.waitForFunction(()=>scanInspection().walk.active);
  await page.keyboard.down('w');await page.waitForTimeout(500);await page.keyboard.up('w');
  const bimMoved=await aligned('BIM movement');assert.ok(distance(moved.camera.position,bimMoved.camera.position)>.1,'BIM actually moves');
  const rect=await bim.locator('canvas').first().boundingBox();await page.mouse.move(rect.x+rect.width*.5,rect.y+rect.height*.5);await page.mouse.down();await page.mouse.move(rect.x+rect.width*.6,rect.y+rect.height*.55,{steps:8});await page.mouse.up();await aligned('BIM look');
  await page.screenshot({path:process.env.SPLAT_SCREENSHOT||'/tmp/grimes-splat-bim-integration.png'});
  assert.deepEqual(errors,[]);console.log('PASS: actual optimized Gaussian asset, '+(mobile?'mobile':'desktop')+' load, movement from both panes and registered position/orientation/FOV, no page errors');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
