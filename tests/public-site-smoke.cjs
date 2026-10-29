/* Public-site smoke: what a visitor to GitHub Pages gets. Oct 18 Level 1 photos are published (2026-10-28, after manual
   contact-sheet review), and Oct 18 Level 2 / Level 3 photos (2026-10-28, strict automatic blur + manual blur boxes after
   manual review of every image); the Oct 18 Gaussian zones and the combined floors=all preview stay local-only.
   Run against the live site or a clean export of HEAD (git archive HEAD | tar -x) served under /Graduate-Project/:
     PLAYWRIGHT_MODULE=/path/to/playwright-core VIEWER_BASE_URL=https://doe2park.github.io/Graduate-Project node tests/public-site-smoke.cjs
   A local export needs a non-localhost host name (localhost-only previews would otherwise switch on), e.g.
     HOST_RULES='MAP pages.emu 127.0.0.1' VIEWER_BASE_URL=http://pages.emu:8811/Graduate-Project
   Checks: the three published captures are listed/cycled, Oct 18 Gaussian / floors=all links stay on Oct 18 photos with no
   local preview (Gaussian option reads "no Gaussian for this capture"), Overlay + Lens card + Range (Near/Room/All,
   distance culling) on May 6, Sep 17 and Oct 18 photos and the May 6 Gaussian, Oct 18 Level 2 / Level 3 via the floor picker
   (floor package, provisional label, BIM floor follows over three stations),
   BIM pose follows the scan, /vr/ opens scan-xr.html in desktop mode, campus dashboard loads (water panel hidden until
   the collector publishes water.usage). Real published meter data (no fixtures). Screenshots: VALIDATION_OUTPUT
   (default work/web-matrix/public). Headless desktop only: no frame-rate, phone or Quest claim. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const ROOT=path.join(__dirname,'..'),OUT=process.env.VALIDATION_OUTPUT||path.join(ROOT,'work','web-matrix','public');
const BASE=(process.env.VIEWER_BASE_URL||'https://doe2park.github.io/Graduate-Project').replace(/\/$/,'');
const PUBLIC=['2026-10-18','2026-09-17','2026-05-06'],SERVICE=['equipment','lighting','conduit','duct','hydronic','plumbing','lifesafety'];
fs.mkdirSync(OUT,{recursive:true});
const report={base:BASE,started:new Date().toISOString(),checks:{}};
(async()=>{
 const args=['--enable-webgl','--ignore-gpu-blocklist','--use-angle=metal'];if(process.env.HOST_RULES)args.push('--host-resolver-rules='+process.env.HOST_RULES);
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args});
 let failed=null;
 try{
  async function open(url,{w=1280,h=800}={}){
   const page=await browser.newPage({viewport:{width:w,height:h}});page.setDefaultTimeout(180000);page.errors=[];
   page.on('pageerror',e=>page.errors.push(e.message));
   await page.goto(BASE+'/'+url,{waitUntil:'domcontentloaded'});return page;}
  const pageErrors=p=>p.errors.filter(e=>!/ResizeObserver/.test(e));
  const scanFrame=p=>p.frames().find(f=>/scan-(photo|splat)\.html/.test(f.url())&&!f.url().includes('edges=1'));
  const bimFrame=p=>p.frames().find(f=>f.url().includes('pane=bim'));
  async function ready(p,display,layers=true){
   await p.waitForFunction(d=>document.getElementById('scanMode').value===d&&typeof registration!=='undefined'&&registration&&scanReady,display);
   if(display==='splat')await scanFrame(p).waitForFunction(()=>window.splatInspection?.().state==='ready',null,{timeout:240000});
   else await scanFrame(p).waitForFunction(()=>window.photoInspection&&!photoInspection().loading&&!photoInspection().transitioning);
   if(layers)await bimFrame(p).waitForFunction(k=>{if(!window.scanInspection)return false;const l=scanInspection().layerStats;return k.every(x=>l[x]?.loaded);},SERVICE,{timeout:300000,polling:500});
   await p.waitForTimeout(1500);}
  const options=p=>p.evaluate(()=>[...document.querySelectorAll('#captureDate option')].map(o=>o.value));
  async function poseCheck(p){return p.evaluate(()=>{const f=[...document.querySelectorAll('iframe')],sw=f[0].contentWindow,bw=f[1].contentWindow;
   const sc=sw.splatInspection?sw.splatInspection().camera:poses.scan,bc=bw.scanInspection().camera;if(!sc||!bc)return null;
   const e=convert({...sc,zoom:1},'scan'),dq=Math.abs(e.quaternion.reduce((s,v,k)=>s+v*bc.quaternion[k],0));
   return{positionErrorM:+Math.hypot(...e.position.map((v,k)=>v-bc.position[k])).toFixed(5),rotationErrorDeg:+(2*Math.acos(Math.min(1,dq))*180/Math.PI).toFixed(4)};});}
  async function lensCard(p){for(const [x,y] of [[640,560],[640,420],[400,330],[880,330],[900,520],[640,300],[500,480],[780,480]]){await p.mouse.move(x,y,{steps:4});
    if(await p.waitForFunction(()=>document.getElementById('lensCard').classList.contains('show'),null,{timeout:1800}).then(()=>true,()=>false))
     return{at:[x,y],text:await p.evaluate(()=>document.getElementById('lensCard').textContent.slice(0,140))};}return null;}
  async function overlay(tag,url,display){
   const p=await open(url),r={url};await ready(p,display);
   r.options=await options(p);assert.deepEqual(r.options,PUBLIC,tag+': only published captures listed');
   r.view=await p.evaluate(()=>document.body.dataset.focus);assert.equal(r.view,'overlay');
   r.status=await p.evaluate(()=>document.getElementById('linkStatus').textContent);
   r.pose=await poseCheck(p);assert.ok(r.pose&&r.pose.positionErrorM<.01&&r.pose.rotationErrorDeg<.2,tag+' BIM pose follows scan '+JSON.stringify(r.pose));
   await p.click('#styleBar [data-style=lens]');r.lens=await lensCard(p);assert.ok(r.lens,tag+': Lens info card appears');
   await p.screenshot({path:path.join(OUT,tag+'-lens.png')});r.ranges={};
   for(const k of ['near','room','all']){await p.click('#rangeBar [data-range='+k+']');await p.waitForTimeout(900);
    const pressed=await p.evaluate(k=>document.querySelector('#rangeBar [data-range='+k+']').getAttribute('aria-pressed'),k);assert.equal(pressed,'true');
    const c=await bimFrame(p).evaluate(()=>{const o=overlayCullInspection();return{enabled:o.enabled,active:o.active,kept:o.elements.kept,total:o.elements.total};});
    r.ranges[k]=c;if(k==='all')assert.equal(c.active,false,tag+': All = no culling');else assert.ok(c.enabled,tag+': culling on at '+k);
    await p.screenshot({path:path.join(OUT,tag+'-range-'+k+'.png')});}
   await p.click('#rangeBar [data-range=room]');await p.waitForTimeout(600);
   r.errors=pageErrors(p);assert.deepEqual(r.errors,[],tag+' page errors');report.checks[tag]=r;console.log(tag,JSON.stringify({status:r.status,pose:r.pose,lens:r.lens.text.slice(0,60),ranges:r.ranges}));await p.close();}
  /* 1. default entry: published captures only */
  {const p=await open('scan-compare.html');await ready(p,'photo',false);const r={options:await options(p),date:await p.evaluate(()=>capture.date),floors:await p.evaluate(()=>!!document.getElementById('floorsToggle'))};
   assert.deepEqual(r.options,PUBLIC);assert.equal(r.floors,false,'no multi-floor toggle off localhost');r.errors=pageErrors(p);assert.deepEqual(r.errors,[]);
   await p.screenshot({path:path.join(OUT,'default.png')});report.checks.default=r;console.log('default',JSON.stringify(r));await p.close();}
  /* 2-4. Overlay on the public captures and the May Gaussian */
  await overlay('may-photo-overlay','scan-compare.html?capture=2026-05-06&view=overlay','photo');
  await overlay('sep-photo-overlay','scan-compare.html?capture=2026-09-17&view=overlay','photo');
  await overlay('oct-photo-overlay','scan-compare.html?capture=2026-10-18&view=overlay','photo');
  await overlay('may-gaussian-overlay','scan-compare.html?capture=2026-05-06&mode=splat&view=overlay','splat');
  /* 5. Oct 18 is published as photos only: Gaussian and multi-floor links stay on its photos, nothing local switches on */
  for(const [tag,url] of [['oct18-gaussian-link','scan-compare.html?capture=2026-10-18&mode=splat'],['oct18-floors-link','scan-compare.html?capture=2026-10-18&floors=all']]){
   const p=await open(url);await ready(p,'photo',false);
   const r=await p.evaluate(()=>({date:capture.date,photo:capture.photo,gaussian:capture.gaussian,label:document.querySelector('#scanMode [value=splat]').textContent,disabled:document.querySelector('#scanMode [value=splat]').disabled,note:document.getElementById('captureMissingNote')?.textContent||null,floors:!!document.getElementById('floorsToggle')}));
   assert.equal(r.date,'2026-10-18');assert.equal(r.photo,'scan-assets/captures/2026-10-18/panoramas/manifest.json');assert.equal(r.gaussian,null);assert.equal(r.label,'Gaussian · no Gaussian for this capture');assert.equal(r.disabled,true);assert.equal(r.note,null);assert.equal(r.floors,false);
   r.errors=pageErrors(p);assert.deepEqual(r.errors,[]);report.checks[tag]=r;console.log(tag,JSON.stringify(r));await p.close();}
  /* 5b. Oct 18 Level 2 / Level 3 (published 2026-10-28): floor picker, the floor's own package, BIM floor follows the photo floor */
  for(const floor of ['L2','L3']){const tag='oct18-'+floor.toLowerCase()+'-overlay',p=await open('scan-compare.html?capture=2026-10-18&view=overlay&floors='+floor);await ready(p,'photo');
   const man='scan-assets/captures/2026-10-18/floors/'+floor+'/panoramas/manifest.json',m=await p.evaluate(u=>fetch(u).then(r=>r.json()),man);
   await scanFrame(p).waitForFunction(n=>photoInspection().count===n,m.stations.length);
   const r=await p.evaluate(()=>({date:capture.date,photo:capture.photo,registration:capture.registration,picker:[...document.querySelectorAll('#floorPicker option')].map(o=>[o.value,o.textContent]),value:document.getElementById('floorPicker')?.value,note:document.getElementById('floorsNote')?.textContent||null,toggle:!!document.getElementById('floorsToggle')}));
   assert.equal(r.date,'2026-10-18');assert.equal(r.photo,man);assert.equal(r.registration,'scan-assets/captures/2026-10-18/registration.json');assert.equal(r.value,floor);assert.equal(r.toggle,false,'no Levels 1-3 button off localhost');
   assert.deepEqual(r.picker.map(o=>o[0]),['L1','L2','L3']);assert.match(r.picker[1][1],/provisional/);assert.match(r.note,new RegExp(floor.replace('L','Level ')+' · provisional, not surveyed'));
   assert.equal(m.status,'published-provisional');assert.match(m.privacy,/manual review of every image/);
   const group=m.walkGroups[0].map(id=>m.stations.findIndex(s=>s.id===id)).filter(i=>m.stations[i].level===floor),picks=[group[0],group[Math.floor(group.length/2)],group[group.length-1]];r.steps=[];
   for(const i of picks){await scanFrame(p).selectOption('#station',String(i));await scanFrame(p).waitForFunction(()=>!photoInspection().loading&&!photoInspection().transitioning);
    await bimFrame(p).waitForFunction(f=>document.getElementById('elementFloor').value===f,floor,{timeout:60000});await p.waitForTimeout(1200);
    const s=await p.evaluate(()=>{const f=[...document.querySelectorAll('iframe')];return{id:f[0].contentWindow.photoInspection().station.id,bimFloor:f[1].contentWindow.document.getElementById('elementFloor').value};});
    assert.equal(s.id,m.stations[i].id);assert.equal(s.bimFloor,floor);r.steps.push(s);await p.screenshot({path:path.join(OUT,tag+'-'+s.id.slice(-7)+'.png')});}
   r.pose=await poseCheck(p);assert.ok(r.pose&&r.pose.positionErrorM<.01&&r.pose.rotationErrorDeg<.2,tag+' BIM pose follows scan '+JSON.stringify(r.pose));
   r.errors=pageErrors(p);assert.deepEqual(r.errors,[]);report.checks[tag]=r;console.log(tag,JSON.stringify(r));await p.close();}
  /* 6. VR page through the short /vr/ URL, desktop mode */
  {const p=await open('vr/');await p.waitForFunction(()=>window.xrInspection?.().ready,null,{timeout:120000});
   await p.waitForFunction(()=>{const l=Object.values(xrInspection().layers);return l.length>=7&&l.every(x=>x.loaded||x.error);},null,{timeout:300000,polling:500});
   const i=await p.evaluate(()=>xrInspection()),r={href:p.url(),capture:i.capture.date,available:i.availableCaptures,options:await p.evaluate(()=>[...document.querySelectorAll('#capture option')].map(o=>o.value)),note:await p.locator('#xrNote').textContent(),layerErrors:Object.entries(i.layers).filter(([,l])=>l.error).map(([k])=>k)};
   assert.match(r.href,/scan-xr\.html/);assert.equal(r.capture,'2026-05-06');assert.deepEqual(r.available,['2026-05-06','2026-09-17','2026-10-18']);assert.deepEqual(r.options,['2026-05-06','2026-09-17','2026-10-18']);assert.deepEqual(r.layerErrors,[]);
   await p.screenshot({path:path.join(OUT,'vr-desktop-may.png')});
   await p.evaluate(()=>xrDebug.menuAction(5));await p.waitForFunction(()=>xrInspection().capture.date==='2026-09-17'&&xrInspection().ready,null,{timeout:60000});
   await p.waitForTimeout(800);await p.screenshot({path:path.join(OUT,'vr-desktop-sep.png')});
   await p.evaluate(()=>xrDebug.menuAction(5));await p.waitForFunction(()=>xrInspection().capture.date==='2026-10-18'&&xrInspection().ready,null,{timeout:60000});
   await p.evaluate(()=>xrDebug.menuAction(5));await p.waitForFunction(()=>xrInspection().capture.date==='2026-05-06'&&xrInspection().ready,null,{timeout:60000});
   r.cycle='May -> Sep -> Oct -> May';r.errors=pageErrors(p);assert.deepEqual(r.errors,[]);report.checks.vr=r;console.log('vr',JSON.stringify(r));await p.close();}
  {const p=await open('scan-xr.html?capture=2026-10-18');await p.waitForFunction(()=>window.xrInspection?.().ready,null,{timeout:120000});
   const r={capture:await p.evaluate(()=>xrInspection().capture.date),note:await p.locator('#xrNote').textContent()};assert.equal(r.capture,'2026-10-18');assert.doesNotMatch(r.note,/not published/);
   r.errors=pageErrors(p);assert.deepEqual(r.errors,[]);report.checks['vr-oct18-link']=r;console.log('vr-oct18-link',JSON.stringify(r));await p.close();}
  {const p=await open('scan-xr.html?scene=gaussian');await p.waitForFunction(()=>{const i=window.xrInspection?.();return i&&i.ready&&(i.scene.splatVisible||i.scene.error);},null,{timeout:240000,polling:250});
   const i=await p.evaluate(()=>xrInspection()),r={mode:i.scene.mode,file:i.scene.file,splats:i.scene.splats,error:i.scene.error};assert.equal(r.error,null);assert.equal(r.mode,'gaussian');
   await p.waitForTimeout(1500);await p.screenshot({path:path.join(OUT,'vr-desktop-gaussian.png')});r.errors=pageErrors(p);assert.deepEqual(r.errors,[]);report.checks['vr-gaussian']=r;console.log('vr-gaussian',JSON.stringify(r));await p.close();}
  /* 7. campus dashboard */
  {const p=await open('campus-energy-dashboard.html');await p.waitForFunction(()=>!/Fetching/.test(document.getElementById('updated').textContent),null,{timeout:60000});await p.waitForTimeout(2500);
   const r=await p.evaluate(()=>({updated:document.getElementById('updated').textContent,waterHidden:document.getElementById('water-panel').hidden,waterTiles:document.getElementById('water-tiles').children.length}));
   if(r.waterHidden)assert.equal(r.waterTiles,0);r.errors=pageErrors(p);assert.deepEqual(r.errors,[]);
   await p.screenshot({path:path.join(OUT,'campus-dashboard.png'),fullPage:false});report.checks.dashboard=r;console.log('dashboard',JSON.stringify(r));await p.close();}
  console.log('PASS public-site smoke ('+BASE+')');
 }catch(e){failed=e;console.error(e);}
 finally{report.finished=new Date().toISOString();report.failed=failed?String(failed.message||failed):null;fs.writeFileSync(path.join(OUT,'public-report.json'),JSON.stringify(report,null,1));await browser.close();process.exit(failed?1:0);}
})();
