/* scan-xr.html desktop smoke (non-XR) + measurements. One headless Chrome run against the real served assets.
   PLAYWRIGHT_MODULE=/path/to/playwright(-core) CHROME_EXECUTABLE=... node tests/scan-xr-smoke.cjs
   Optional: VIEWER_BASE_URL (default: starts python3 -m http.server on 127.0.0.1:<free port>), XR_SMOKE_LAYERS
   (comma list; default = page default: seven Level-1 service layers, fire off), VALIDATION_OUTPUT (screenshots + JSON).
   Meter data is a deterministic route fixture. Headless desktop numbers are NOT Quest frame rates. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),net=require('node:net'),{spawn}=require('node:child_process');
const ROOT=path.join(__dirname,'..'),OUT=process.env.VALIDATION_OUTPUT||path.join(os.tmpdir(),'grimes-validation','scan-xr');fs.mkdirSync(OUT,{recursive:true});
const freePort=()=>new Promise(r=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>r(p));});});
(async()=>{
 let server=null,base=process.env.VIEWER_BASE_URL;
 if(!base){const port=await freePort();server=spawn('python3',['-m','http.server',String(port),'--bind','127.0.0.1'],{cwd:ROOT,stdio:'ignore'});base='http://127.0.0.1:'+port;
  for(let i=0;i<50;i++){try{await fetch(base+'/scan-xr.html');break;}catch{await new Promise(r=>setTimeout(r,100));}}}
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--enable-webgl','--ignore-gpu-blocklist','--use-angle=metal','--enable-precise-memory-info']});
 const report={};
 try{
  const page=await browser.newPage({viewport:{width:1280,height:800}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  const now=new Date().toISOString().slice(0,19);
  await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({meters:{76:{latest:{kw:120.5,t:now}},77:{latest:{kw:40.2,t:now}},3:{latest:{kw:12,t:now}}}})}));
  const layers=process.env.XR_SMOKE_LAYERS?'&layers='+process.env.XR_SMOKE_LAYERS:'';
  const t0=Date.now();await page.goto(base+'/scan-xr.html?'+layers.slice(1));
  await page.waitForFunction(()=>window.xrInspection?.().ready,null,{timeout:60000});
  const first=await page.evaluate(()=>xrInspection());
  assert.equal(first.capture.date,'2026-05-06');assert.equal(first.capture.provisional,false);assert.equal(first.station.id,'83697765','manifest default station');
  assert.deepEqual(first.texture,{width:4096,height:2048},'desktop without XR uses the full photo');
  assert.equal(await page.locator('#enterVR').isHidden(),true,'no Enter VR without immersive-vr');assert.match(await page.locator('#xrNote').textContent(),/Desktop preview/);
  assert.match(await page.locator('#align').textContent(),/registered \(internal residual ≈0\.13 m, not surveyed\)/);
  const cam=first.camera.world;first.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-cam[k])<1e-6,'eye on the station'));
  const expected=process.env.XR_SMOKE_LAYERS?process.env.XR_SMOKE_LAYERS.split(',').length:7;
  await page.waitForFunction(n=>{const l=Object.values(xrInspection().layers);return l.length>=n&&l.every(x=>x.loaded||x.error);},expected,{timeout:240000,polling:500});
  const loaded=await page.evaluate(()=>{xrDebug.renderNow();return xrInspection();});
  report.loadWallMs=Date.now()-t0;report.timing=loaded.timing;report.heapMB=loaded.heapMB;report.totals=loaded.totals;report.render=loaded.lastRender;
  report.layers=Object.fromEntries(Object.entries(loaded.layers).map(([k,l])=>[k,{batches:l.drawCalls,visible:l.visibleBatches,elements:l.elements,triangles:l.renderTriangles,segments:l.renderSegments,dropped:l.droppedOtherLevels,loadMs:l.loadMs,error:l.error}]));
  for(const [k,l] of Object.entries(loaded.layers)){assert.equal(l.error,null,k);assert.ok(l.elements>0,k+' has Level 1 elements');assert.equal(l.unidentifiedObjects||0,0,k+': every fragment has sidecar identity');}
  assert.equal(loaded.layers.fire,undefined,'fire piping is opt-in');
  assert.ok(loaded.totals.visibleDrawCalls>0&&loaded.totals.visibleDrawCalls<loaded.totals.drawCalls,'radius visibility hides distant batches');
  const reg=JSON.parse(fs.readFileSync(path.join(ROOT,'alignment-analysis/accepted-registration.json')));
  assert.ok(Math.abs(loaded.bimRoot.rotationY+reg.rotationYDegrees*Math.PI/180)<1e-12);
  // render gating: idle desktop page does not redraw
  const c0=(await page.evaluate(()=>xrInspection().renderCount));await page.waitForTimeout(1200);const c1=await page.evaluate(()=>xrInspection().renderCount);
  assert.ok(c1-c0<=1,'idle outside XR: no continuous rendering ('+(c1-c0)+')');report.idleRendersPerSecond=(c1-c0)/1.2;
  // pick an element near the station through the centre ray -> world-space card with honest tier
  const near=await page.evaluate(()=>xrDebug.elementsNearStation(12));assert.ok(near.length,'service elements near the default station');
  let card=null;for(const e of near){await page.evaluate(p=>xrDebug.lookAtBim(p),e.point);card=await page.evaluate(()=>xrDebug.pickNdc(0,0));if(card?.id)break;}
  assert.ok(card?.id,'centre-ray pick resolved an element id');
  assert.ok(['LIVE','LATEST','NO READING','MODELLED','CONTEXT','NONE'].includes(card.tier));
  assert.match(card.lines.footer[0],/not surveyed/);assert.match(card.lines.footer[1],/Design \(BIM\) position/);
  if(card.tier==='CONTEXT')assert.ok(card.lines.rows.some(r=>/not this element/.test(r)));
  report.pick={id:card.id,layer:card.layer,tier:card.tier,badge:card.lines.badge};
  await page.screenshot({path:path.join(OUT,'scan-xr-lens-card.png')});
  // lens vs all differ on screen; opacity control reaches the shader
  const lens=await page.screenshot();await page.evaluate(()=>xrDebug.setStyle('all'));await page.waitForTimeout(150);const all=await page.screenshot({path:path.join(OUT,'scan-xr-all.png')});
  assert.notDeepEqual(lens,all,'All style shows services outside the cone');assert.equal((await page.evaluate(()=>xrInspection())).opacity,.35);
  await page.evaluate(()=>xrDebug.setStyle('lens'));
  // neighbour navigation along the recorded route
  const m=JSON.parse(fs.readFileSync(path.join(ROOT,'scan-assets/panoramas/manifest.json')));const i0=loaded.station.index,s0=m.stations[i0],n=m.stations[s0.neighbors[0]];
  await page.evaluate(([x,z])=>xrDebug.walk(x,z),[n.position[0]-s0.position[0],n.position[2]-s0.position[2]]);
  await page.waitForFunction(i=>xrInspection().station.index!==i&&!document.getElementById('status').textContent.startsWith('Loading'),i0,{timeout:30000});
  const moved=await page.evaluate(()=>xrInspection());assert.ok(s0.neighbors.includes(moved.station.index),'moved to a recorded neighbour');
  moved.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-moved.camera.world[k])<1e-6));assert.equal(moved.card,null,'card cleared on jump');
  // Sep 17: provisional label everywhere, its own registration
  await page.evaluate(()=>xrDebug.switchCapture('2026-09-17'));await page.waitForFunction(()=>xrInspection().capture.date==='2026-09-17'&&xrInspection().ready);
  const sep=await page.evaluate(()=>xrInspection());assert.equal(sep.capture.provisional,true);assert.match(await page.locator('#align').textContent(),/PROVISIONAL/);
  sep.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-sep.camera.world[k])<1e-6,'eye on the Sep station'));
  const sepReg=JSON.parse(fs.readFileSync(path.join(ROOT,'scan-assets/captures/2026-09-17/registration.json')));assert.ok(Math.abs(sep.bimRoot.rotationY+sepReg.rotationYDegrees*Math.PI/180)<1e-12);
  await page.evaluate(()=>xrDebug.setStyle('all'));await page.waitForTimeout(150);await page.screenshot({path:path.join(OUT,'scan-xr-sep-all.png')});await page.evaluate(()=>xrDebug.setStyle('lens'));
  report.sep={station:sep.station.id,visibleBatches:sep.totals.visibleDrawCalls};
  // Oct 18: the menu Capture button cycles May → Sep → Oct; provisional, its own registration and photos
  await page.evaluate(()=>xrDebug.menuAction(5));await page.waitForFunction(()=>xrInspection().capture.date==='2026-10-18'&&xrInspection().ready);
  const oct=await page.evaluate(()=>xrInspection());assert.equal(oct.capture.provisional,true);assert.match(await page.locator('#align').textContent(),/Oct 18, 2026 · PROVISIONAL/);
  oct.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-oct.camera.world[k])<1e-6,'eye on the Oct station'));
  const octReg=JSON.parse(fs.readFileSync(path.join(ROOT,'scan-assets/captures/2026-10-18/registration.json')));assert.equal(octReg.status,'project-frame-provisional');assert.ok(Math.abs(oct.bimRoot.rotationY+octReg.rotationYDegrees*Math.PI/180)<1e-12);
  assert.ok(oct.texture&&oct.texture.width>=2048,'Oct photo loaded');
  await page.evaluate(()=>xrDebug.setStyle('all'));await page.waitForTimeout(150);await page.screenshot({path:path.join(OUT,'scan-xr-oct-all.png')});await page.evaluate(()=>xrDebug.setStyle('lens'));
  report.oct={station:oct.station.id,visibleBatches:oct.totals.visibleDrawCalls};
  await page.evaluate(()=>xrDebug.menuAction(5));await page.waitForFunction(()=>xrInspection().capture.date==='2026-05-06'&&xrInspection().ready);
  // XR menu panel renders and its buttons work with a desktop click ray
  await page.evaluate(()=>xrDebug.setMenu(true));await page.screenshot({path:path.join(OUT,'scan-xr-menu.png')});
  await page.evaluate(()=>xrDebug.menuAction(0));assert.equal((await page.evaluate(()=>xrInspection())).style,'all');
  // phone width: no horizontal overflow
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(200);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no horizontal overflow at 390 px');
  await page.screenshot({path:path.join(OUT,'scan-xr-390.png')});
  assert.ok(await page.evaluate(()=>{const a=document.getElementById('align');return a.scrollWidth<=a.clientWidth+1&&/not surveyed\)/.test(a.textContent);}),'alignment caveat is not clipped at 390 px');
  assert.deepEqual(errors.filter(e=>!/favicon/.test(e)),[]);
  if(process.env.XR_SMOKE_GAUSSIAN!=='0')report.gaussian=await gaussianSmoke(browser,base,now);
  if(process.env.XR_SMOKE_OCT==='1')report.gaussianOct=await gaussianSmoke(browser,base,now,'work/gaussian/2026-10-18/l1-a/20261019T074640Z/package/viewer.json');
  fs.writeFileSync(path.join(OUT,'scan-xr-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));console.log('PASS scan-xr desktop smoke (registration, photo, Level-1 services, radius culling, card tiers, navigation, provisional Sep/Oct, capture cycle, menu, idle gating, 390 px'+(report.gaussian?', Gaussian mobile scene, teleport, scene toggle':'')+(report.gaussianOct?', local Oct 18 zone override':'')+')');
 }finally{await browser.close();if(server)server.kill();}
})().catch(e=>{console.error(e);process.exit(1);});
/* Gaussian scene mode: short run, two light layers, the reduced mobile file (350k SH0) that XR uses by default.
   Default: published May 6 scene, with a deliberately invalid ?gaussian= that must be ignored.
   XR_SMOKE_OCT=1 additionally loads the local, unpublished Oct 18 zone l1-a package through the dev-host override. */
async function gaussianSmoke(browser,base,now,override){
 const page=await browser.newPage({viewport:{width:1280,height:800}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({meters:{76:{latest:{kw:120.5,t:now}}}})}));
 const out={},t0=Date.now();
 await page.goto(base+'/scan-xr.html?scene=gaussian&splat=mobile&layers=equipment,lighting&gaussian='+encodeURIComponent(override||'../secret.json'));
 await page.waitForFunction(()=>{const i=window.xrInspection?.();return i&&i.ready&&(i.scene.splatVisible||i.scene.error);},null,{timeout:120000,polling:250});
 let g=await page.evaluate(()=>xrInspection());out.sceneReadyWallMs=Date.now()-t0;
 assert.equal(g.scene.error,null);assert.equal(g.scene.mode,'gaussian');assert.equal(g.scene.file,'mobile.ply');assert.equal(g.scene.mobile,true);assert.equal(g.scene.shDegree,0);
 assert.ok(g.scene.splats>300000&&g.scene.splats<=350000,'mobile splat count '+g.scene.splats);assert.equal(g.photoSphereVisible,false,'photo sphere hidden');assert.equal(g.texture,null,'no photo downloaded in Gaussian mode');
 assert.equal(await page.evaluate(()=>crossOriginIsolated),false,'works without COOP/COEP');
 const align=await page.locator('#align').textContent();assert.match(align,/experimental appearance, not surveyed/);
 if(override){assert.equal(g.capture.date,'2026-10-18');assert.equal(g.scene.local,true);assert.equal(g.scene.zone,'l1-a');assert.match(align,/zone l1-a.*provisional alignment.*local preview, unpublished/);assert.match(align,/PROVISIONAL/);
  const m=JSON.parse(fs.readFileSync(path.join(ROOT,override)));assert.ok(m.zone.stations.includes(g.station.id),'starts inside the trained zone');}
 else{assert.equal(g.capture.date,'2026-05-06');assert.equal(g.scene.override,null);assert.match(g.scene.overrideNote,/ignored/);assert.equal(g.scene.manifest,'scan-assets/gaussian/2026-05-06/viewer.json');assert.doesNotMatch(align,/provisional/i);}
 g.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-g.camera.world[k])<1e-6,'eye on the station'));
 const regFile=override?'scan-assets/captures/2026-10-18/registration.json':'alignment-analysis/accepted-registration.json',reg=JSON.parse(fs.readFileSync(path.join(ROOT,regFile)));
 assert.ok(Math.abs(g.bimRoot.rotationY+reg.rotationYDegrees*Math.PI/180)<1e-12,'same BIM placement as Photo mode');
 await page.waitForFunction(()=>{const l=Object.values(xrInspection().layers);return l.length>=2&&l.every(x=>x.loaded||x.error);},null,{timeout:120000,polling:500});
 await page.waitForFunction(()=>!xrInspection().scene.sortRunning,null,{timeout:20000});
 const fr=await page.evaluate(()=>xrDebug.frameStats());assert.ok(fr.litFraction>.25,'splats cover the view: '+fr.litFraction);
 g=await page.evaluate(()=>xrInspection());Object.assign(out,{file:g.scene.file,splats:g.scene.splats,gaussianLoadMs:g.scene.loadMs,gaussianReadyMs:g.timing.gaussianMs,layersDoneMs:g.timing.layersDoneMs,heapMB:g.heapMB,frame:fr});
 await page.screenshot({path:path.join(OUT,'scan-xr-gaussian'+(override?'-oct':'')+'.png')});
 await page.evaluate(()=>xrDebug.setStyle('all'));await page.waitForTimeout(300);await page.screenshot({path:path.join(OUT,'scan-xr-gaussian-all'+(override?'-oct':'')+'.png')});await page.evaluate(()=>xrDebug.setStyle('lens'));
 // idle: once the worker sort has landed, the desktop page stops redrawing
 await page.waitForTimeout(400);const c0=await page.evaluate(()=>xrInspection().renderCount);await page.waitForTimeout(1200);const c1=await page.evaluate(()=>xrInspection().renderCount);
 out.idleRendersPerSecond=(c1-c0)/1.2;assert.ok(c1-c0<=3,'Gaussian idle redraws '+(c1-c0));
 // teleport: look 35° down, centre ray onto the assumed floor plane; eye height kept; BIM radius follows
 const before=g.viewPos;await page.evaluate(()=>xrDebug.look(xrInspection().rig.yaw,-.61));
 const pre=await page.evaluate(()=>xrDebug.teleportNdc(0,0,true));assert.ok(pre.ok,'floor target: '+pre.reason);
 await page.evaluate(()=>xrDebug.teleportNdc(0,0));await page.waitForFunction(()=>xrInspection().scene.teleports===1&&xrInspection().ready,null,{timeout:10000});
 const tp=await page.evaluate(()=>xrInspection());const moved=Math.hypot(tp.viewPos[0]-before[0],tp.viewPos[2]-before[2]);
 assert.ok(moved>.5&&moved<8,'teleported '+moved.toFixed(2)+' m');assert.ok(Math.abs(tp.viewPos[1]-before[1])<1e-9,'eye height kept');
 tp.viewPos.forEach((v,k)=>assert.ok(Math.abs(v-tp.camera.world[k])<1e-6,'eye at the landing'));
 const t=reg.rotationYDegrees*Math.PI/180,c=Math.cos(t),sn=Math.sin(t),p=tp.viewPos,bim=[c*p[0]+sn*p[2]+reg.translation[0],p[1]+reg.translation[1],-sn*p[0]+c*p[2]+reg.translation[2]];
 bim.forEach((v,k)=>assert.ok(Math.abs(v-tp.station.positionBim[k])<1e-9,'radius centre follows the teleport'));out.teleportMetres=+moved.toFixed(2);
 await page.evaluate(()=>xrDebug.look(xrInspection().rig.yaw,.3));const up=await page.evaluate(()=>xrDebug.teleportNdc(0,0,true));assert.equal(up.ok,false);assert.match(up.reason,/Point at the floor/);
 // station jumps still work in Gaussian mode (no photo download)
 await page.evaluate(()=>xrDebug.recenter());await page.waitForFunction(()=>xrInspection().ready,null,{timeout:10000});
 const r0=await page.evaluate(()=>xrInspection());r0.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-r0.camera.world[k])<1e-6,'recentred on the nearest station'));
 await page.evaluate(()=>xrDebug.openStation(xrInspection().station.index+1));await page.waitForFunction(i=>xrInspection().station.index!==i&&xrInspection().ready,r0.station.index,{timeout:10000});
 const j=await page.evaluate(()=>xrInspection());assert.equal(j.photoSphereVisible,false);assert.equal(j.texture,null);j.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-j.camera.world[k])<1e-6));
 // menu toggle back to Photo: nearest station's photo returns; and to Gaussian again (scene stays resident)
 await page.evaluate(()=>xrDebug.menuAction(9));await page.waitForFunction(()=>xrInspection().scene.mode==='photo'&&xrInspection().texture,null,{timeout:20000});
 const ph=await page.evaluate(()=>xrInspection());assert.equal(ph.photoSphereVisible,true);assert.equal(ph.scene.splatVisible,false);ph.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-ph.camera.world[k])<1e-6));
 const tg=Date.now();await page.evaluate(()=>xrDebug.menuAction(9));await page.waitForFunction(()=>xrInspection().scene.splatVisible&&xrInspection().ready,null,{timeout:20000});out.retoggleMs=Date.now()-tg;
 // Sep 17 has no Gaussian: the toggle explains and stays in Photo
 await page.evaluate(()=>xrDebug.switchCapture('2026-09-17'));await page.waitForFunction(()=>xrInspection().capture.date==='2026-09-17'&&xrInspection().ready&&xrInspection().texture,null,{timeout:30000});
 const sep=await page.evaluate(()=>xrInspection());assert.equal(sep.scene.mode,'photo');assert.equal(sep.scene.available,false);assert.match(await page.locator('#status').textContent(),/No Gaussian scene for Sep 17, 2026 · staying in Photo/);
 assert.equal(sep.scene.splats,0,'previous capture splats disposed');
 assert.deepEqual(errors.filter(e=>!/favicon/.test(e)),[]);
 await page.close();return out;
}
