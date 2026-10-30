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
  report.pointAndGo=await pointAndGoSmoke(page,m);
  report.hoverRayCostMs=await page.evaluate(()=>xrDebug.rayCostMs());   // desktop CPU; the Quest is slower (the page self-throttles at 20x the measured cost)
  // Sep 17: provisional label everywhere, its own registration
  await page.evaluate(()=>xrDebug.switchCapture('2026-09-17'));await page.waitForFunction(()=>xrInspection().capture.date==='2026-09-17'&&xrInspection().ready);
  const sep=await page.evaluate(()=>xrInspection());assert.equal(sep.capture.provisional,true);assert.match(await page.locator('#align').textContent(),/PROVISIONAL/);
  sep.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-sep.camera.world[k])<1e-6,'eye on the Sep station'));
  const sepReg=JSON.parse(fs.readFileSync(path.join(ROOT,'scan-assets/captures/2026-09-17/registration.json')));assert.ok(Math.abs(sep.bimRoot.rotationY+sepReg.rotationYDegrees*Math.PI/180)<1e-12);
  await page.evaluate(()=>xrDebug.setStyle('all'));await page.waitForTimeout(150);await page.screenshot({path:path.join(OUT,'scan-xr-sep-all.png')});await page.evaluate(()=>xrDebug.setStyle('lens'));
  report.sep={station:sep.station.id,visibleBatches:sep.totals.visibleDrawCalls};
  // Oct 18: the menu Capture button cycles May → Sep → Oct; provisional, its own registration and photos
  await page.evaluate(()=>xrDebug.menuAction('capture'));await page.waitForFunction(()=>xrInspection().capture.date==='2026-10-18'&&xrInspection().ready);
  const oct=await page.evaluate(()=>xrInspection());assert.equal(oct.capture.provisional,true);assert.match(await page.locator('#align').textContent(),/Oct 18, 2026 · PROVISIONAL/);
  oct.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-oct.camera.world[k])<1e-6,'eye on the Oct station'));
  const octReg=JSON.parse(fs.readFileSync(path.join(ROOT,'scan-assets/captures/2026-10-18/registration.json')));assert.equal(octReg.status,'project-frame-provisional');assert.ok(Math.abs(oct.bimRoot.rotationY+octReg.rotationYDegrees*Math.PI/180)<1e-12);
  assert.ok(oct.texture&&oct.texture.width>=2048,'Oct photo loaded');
  await page.evaluate(()=>xrDebug.setStyle('all'));await page.waitForTimeout(150);await page.screenshot({path:path.join(OUT,'scan-xr-oct-all.png')});await page.evaluate(()=>xrDebug.setStyle('lens'));
  report.oct={station:oct.station.id,visibleBatches:oct.totals.visibleDrawCalls};
  await page.evaluate(()=>xrDebug.menuAction('capture'));await page.waitForFunction(()=>xrInspection().capture.date==='2026-05-06'&&xrInspection().ready);
  // XR menu (2026-10-22): 5 large buttons ~0.8 m away; the ray highlights a button, a click acts on that button only; More page
  report.menu=await menuSmoke(page);
  // phone width: no horizontal overflow
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(200);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no horizontal overflow at 390 px');
  await page.screenshot({path:path.join(OUT,'scan-xr-390.png')});
  assert.ok(await page.evaluate(()=>{const a=document.getElementById('align');return a.scrollWidth<=a.clientWidth+1&&/not surveyed\)/.test(a.textContent);}),'alignment caveat is not clipped at 390 px');
  assert.deepEqual(errors.filter(e=>!/favicon/.test(e)),[]);
  if(process.env.XR_SMOKE_GAUSSIAN!=='0')report.gaussian=await gaussianSmoke(browser,base,now);
  if(process.env.XR_SMOKE_OCT==='1')report.gaussianOct=await gaussianSmoke(browser,base,now,'work/gaussian/2026-10-18/l1-a/20261019T074640Z/package/viewer.json');
  if(process.env.XR_SMOKE_MR!=='0')report.mr=await mrSmoke(browser,base,now);
  fs.writeFileSync(path.join(OUT,'scan-xr-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));console.log('PASS scan-xr desktop smoke (registration, photo, Level-1 services, radius culling, card tiers, navigation, provisional Sep/Oct, capture cycle, point-and-go, snap turn, menu hover/click/More, idle gating, 390 px'+(report.gaussian?', Gaussian mobile scene, teleport, scene toggle':'')+(report.gaussianOct?', local Oct 18 zone override':'')+(report.mr?', MR passthrough desktop simulation (alignment fit, persistence, fade/culling, checks, nudge)':'')+')');
 }finally{await browser.close();if(server)server.kill();}
})().catch(e=>{console.error(e);process.exit(1);});
/* Point-and-go in 360-photo mode (desktop emulation: the camera ray stands in for the LEFT controller ray).
   A level ray at a station 6-14 m away (not a route neighbour) jumps straight there; pointing at the floor next to a station picks it;
   pointing up explains; snap turn keeps the eye fixed. */
async function pointAndGoSmoke(page,m){
 const out={},I=await page.evaluate(()=>xrInspection()),cur=I.station.index,here=m.stations[cur].position;
 const route=require('../twin/xr-core.js').routeDistances(m.stations,cur);
 const cand=m.stations.map((s,j)=>({j,s,dh:Math.hypot(s.position[0]-here[0],s.position[2]-here[2])})).filter(c=>c.j!==cur&&!m.stations[cur].neighbors.includes(c.j)&&c.dh>6&&c.dh<14&&Math.abs(c.s.position[1]-here[1])<1&&Number.isFinite(route[c.j])&&route[c.j]<1.4*c.dh).sort((a,b)=>b.dh-a.dh);
 assert.ok(cand.length,'a far station to point at');
 let done=null;
 for(const c of cand.slice(0,6)){await page.evaluate(p=>xrDebug.lookAtScan(p),c.s.position);const a=await page.evaluate(()=>xrDebug.aimNdc(0,0));if(a?.ok&&a.index===c.j){done={c,a};break;}}
 assert.ok(done,'pointing straight at a far station selects it');
 assert.equal(done.a.method,'cone');assert.match(done.a.label,/^Capture \d+ · \d+\.\d m$/);assert.equal((await page.evaluate(()=>xrInspection())).aim.index,done.c.j);
 await page.screenshot({path:path.join(OUT,'scan-xr-aim.png')});
 const g=await page.evaluate(()=>xrDebug.goNdc(0,0));assert.equal(g.moved,true);
 await page.waitForFunction(j=>xrInspection().station.index===j&&xrInspection().ready,done.c.j,{timeout:30000});
 const at=await page.evaluate(()=>xrInspection());at.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-at.camera.world[k])<1e-6,'eye on the far station'));
 out.jump={from:cur,to:done.c.j,metres:+done.c.dh.toFixed(2),routeMetres:+route[done.c.j].toFixed(2),neighbourHop:false};
 // floor spot next to a station within 15 m -> that station ('floor' method)
 const h2=at.station.positionScan,fc=m.stations.map((s,j)=>({j,s,dh:Math.hypot(s.position[0]-h2[0],s.position[2]-h2[2])})).filter(c=>c.j!==at.station.index&&c.dh>2.5&&c.dh<9&&Math.abs(c.s.position[1]-h2[1])<.5).sort((a,b)=>a.dh-b.dh);
 let floor=null;for(const c of fc.slice(0,8)){await page.evaluate(p=>xrDebug.lookAtScan(p),[c.s.position[0]+.3,h2[1]-1.5,c.s.position[2]]);const a=await page.evaluate(()=>xrDebug.aimNdc(0,0));if(a?.ok&&a.method==='floor'&&a.index===c.j){floor=a;break;}}
 assert.ok(floor,'floor spot -> the nearest station');out.floor={index:floor.index,label:floor.label};
 const up=await page.evaluate(()=>{xrDebug.look(0,1.4);return xrDebug.aimNdc(0,0);});assert.equal(up.ok,false);assert.match(up.reason,/Point toward a captured position/);
 await page.evaluate(()=>xrDebug.aimNdc(5,5));
 // snap turn: 30° about the eye, eye position unchanged; back again
 const t1=await page.evaluate(()=>xrDebug.snapTurn(1)),t2=await page.evaluate(()=>xrDebug.snapTurn(-1));
 t1.before.forEach((v,k)=>assert.ok(Math.abs(v-t1.after[k])<1e-9,'snap turn keeps the eye'));assert.ok(Math.abs(t1.yaw+Math.PI/6)<1e-9&&Math.abs(t2.yaw)<1e-9);
 await page.evaluate(()=>xrDebug.look(0,0));return out;
}
/* XR menu panel (desktop emulation of the controller ray via the camera ray through a button centre). */
async function menuSmoke(page){
 const out={};await page.evaluate(()=>{xrDebug.look(0,0);xrDebug.setMenu(true);});
 let mi=(await page.evaluate(()=>xrInspection())).menu;assert.equal(mi.open,true);assert.deepEqual(mi.buttons,['capture','style','scene','recenter','more'],'≤ 5 main buttons');
 assert.ok(Math.abs(mi.distance-Math.hypot(.8,.15))<.02,'panel ≈0.8 m from the eye: '+mi.distance);out.distanceM=+mi.distance.toFixed(3);
 await page.screenshot({path:path.join(OUT,'scan-xr-menu.png')});
 const nd=await page.evaluate(()=>xrDebug.menuButtonNdc('style'));assert.ok(nd&&Math.abs(nd[0])<1&&Math.abs(nd[1])<1,'Lens/All button on screen');
 const hv=await page.evaluate(([x,y])=>xrDebug.hoverNdc(x,y),nd);assert.equal(hv.id,'style');assert.deepEqual((await page.evaluate(()=>xrInspection())).menu.hover,[1],'hover highlight');
 await page.waitForTimeout(100);await page.screenshot({path:path.join(OUT,'scan-xr-menu-hover.png')});
 const s0=(await page.evaluate(()=>xrInspection())).style;const r=await page.evaluate(([x,y])=>xrDebug.pickNdc(x,y),nd);assert.equal(r.menu,'style');
 assert.notEqual((await page.evaluate(()=>xrInspection())).style,s0,'click acted on the highlighted button');
 // a click on the panel header (above the buttons) does nothing
 const hd=await page.evaluate(()=>{const [x,y]=xrDebug.menuButtonNdc('capture');return [x,y+.25];});const hr=await page.evaluate(([x,y])=>xrDebug.hoverNdc(x,y),hd);
 assert.ok(hr&&hr.button===-1,'header hit, no button');const before=(await page.evaluate(()=>xrInspection())).capture.date;assert.equal((await page.evaluate(([x,y])=>xrDebug.pickNdc(x,y),hd)).menu,null);assert.equal((await page.evaluate(()=>xrInspection())).capture.date,before);
 await page.evaluate(()=>xrDebug.hoverNdc(5,5));assert.deepEqual((await page.evaluate(()=>xrInspection())).menu.hover,[],'hover cleared off the panel');
 // More page: flashlight hands, fixed opacity cycle, layer toggles, back, exit
 const mp=await page.evaluate(()=>xrDebug.menuButtonNdc('more'));assert.equal((await page.evaluate(([x,y])=>xrDebug.pickNdc(x,y),mp)).menu,'more');
 mi=(await page.evaluate(()=>xrInspection())).menu;assert.equal(mi.page,'more');assert.deepEqual(mi.buttons.slice(0,5),['back','hands','opacity','hires','exit']);assert.equal(mi.buttons.filter(b=>b.startsWith('layer:')).length,8);
 await page.waitForTimeout(100);await page.screenshot({path:path.join(OUT,'scan-xr-menu-more.png')});
 const c=(await page.evaluate(()=>xrInspection())).controls;assert.equal(c.hands,'right');assert.equal(c.lensOpacity,.7);assert.equal(c.allOpacity,.35);
 await page.evaluate(()=>xrDebug.menuAction('hands'));assert.equal((await page.evaluate(()=>xrInspection())).controls.hands,'both');await page.evaluate(()=>xrDebug.menuAction('hands'));
 for(const want of [.9,.5,.7]){await page.evaluate(()=>xrDebug.menuAction('opacity'));assert.equal((await page.evaluate(()=>xrInspection())).controls.lensOpacity,want);}
 const key=Object.keys((await page.evaluate(()=>xrInspection())).layers)[0];
 await page.evaluate(k=>xrDebug.menuAction('layer:'+k),key);assert.equal((await page.evaluate(()=>xrInspection())).layers[key].visible,false);
 await page.evaluate(k=>xrDebug.menuAction('layer:'+k),key);assert.equal((await page.evaluate(()=>xrInspection())).layers[key].visible,true);
 await page.evaluate(()=>xrDebug.menuAction('back'));assert.equal((await page.evaluate(()=>xrInspection())).menu.page,'main');
 await page.evaluate(()=>xrDebug.menuAction('exit'));assert.equal((await page.evaluate(()=>xrInspection())).menu.open,false,'Exit outside VR closes the menu');
 await page.evaluate(()=>xrDebug.setStyle('all'));   // the next check expects All (as the old menu test left it)
 out.buttons=mi.buttons;return out;
}
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
 // point-and-go in Gaussian mode: floor = free teleport target; level ray = fallback to the station cone
 const fl=await page.evaluate(()=>{xrDebug.look(xrInspection().rig.yaw,-.61);return xrDebug.aimNdc(0,0);});assert.equal(fl.kind,'point');assert.equal(fl.ok,true);assert.match(fl.label,/^Teleport · \d+\.\d m$/);
 const hz=await page.evaluate(()=>{xrDebug.look(xrInspection().rig.yaw,0);return xrDebug.aimNdc(0,0);});assert.equal(hz.kind,'station');assert.ok(hz.ok||hz.reason,'station fallback answers');out.horizonFallback=hz.ok?hz.label:hz.reason;
 await page.evaluate(()=>xrDebug.aimNdc(5,5));
 // station jumps still work in Gaussian mode (no photo download)
 await page.evaluate(()=>xrDebug.recenter());await page.waitForFunction(()=>xrInspection().ready,null,{timeout:10000});
 const r0=await page.evaluate(()=>xrInspection());r0.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-r0.camera.world[k])<1e-6,'recentred on the nearest station'));
 await page.evaluate(()=>xrDebug.openStation(xrInspection().station.index+1));await page.waitForFunction(i=>xrInspection().station.index!==i&&xrInspection().ready,r0.station.index,{timeout:10000});
 const j=await page.evaluate(()=>xrInspection());assert.equal(j.photoSphereVisible,false);assert.equal(j.texture,null);j.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-j.camera.world[k])<1e-6));
 // menu toggle back to Photo: nearest station's photo returns; and to Gaussian again (scene stays resident)
 await page.evaluate(()=>xrDebug.menuAction('scene'));await page.waitForFunction(()=>xrInspection().scene.mode==='photo'&&xrInspection().texture,null,{timeout:20000});
 const ph=await page.evaluate(()=>xrInspection());assert.equal(ph.photoSphereVisible,true);assert.equal(ph.scene.splatVisible,false);ph.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-ph.camera.world[k])<1e-6));
 const tg=Date.now();await page.evaluate(()=>xrDebug.menuAction('scene'));await page.waitForFunction(()=>xrInspection().scene.splatVisible&&xrInspection().ready,null,{timeout:20000});out.retoggleMs=Date.now()-tg;
 // Sep 17 has no Gaussian: the toggle explains and stays in Photo
 await page.evaluate(()=>xrDebug.switchCapture('2026-09-17'));await page.waitForFunction(()=>xrInspection().capture.date==='2026-09-17'&&xrInspection().ready&&xrInspection().texture,null,{timeout:30000});
 const sep=await page.evaluate(()=>xrInspection());assert.equal(sep.scene.mode,'photo');assert.equal(sep.scene.available,false);assert.match(await page.locator('#status').textContent(),/No Gaussian scene for Sep 17, 2026 · staying in Photo/);
 assert.equal(sep.scene.splats,0,'previous capture splats disposed');
 assert.deepEqual(errors.filter(e=>!/favicon/.test(e)),[]);
 await page.close();return out;
}
/* MR passthrough mode (?mode=ar) on a desktop without immersive-ar: the page must explain, load only services (no photo),
   and run the full alignment flow with synthetic touches (Simulate alignment). XR_SMOKE_MR=0 skips; XR_SMOKE_MR_LAYERS
   overrides the light default (duct,plumbing; the page default adds fire piping, ~42 MB). Not a headset test. */
async function mrSmoke(browser,base,now){
 const ctx=await browser.newContext({viewport:{width:1280,height:800}}),page=await ctx.newPage(),errors=[],out={};
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({meters:{76:{latest:{kw:120.5,t:now}},3:{latest:{kw:12,t:now}}}})}));
 const layers=(process.env.XR_SMOKE_MR_LAYERS||'duct,plumbing').split(','),t0=Date.now();
 await page.goto(base+'/scan-xr.html?mode=ar&layers='+layers.join(','));
 await page.waitForFunction(n=>{const i=window.xrInspection?.();if(!i?.mr?.area)return false;const l=Object.values(i.layers);return l.length>=n&&l.every(x=>x.loaded||x.error);},layers.length,{timeout:240000,polling:500});
 let i=await page.evaluate(()=>xrInspection());out.layersReadyWallMs=Date.now()-t0;
 assert.equal(i.mode,'ar');assert.equal(i.capture,null,'no capture / registration in MR');assert.equal(i.texture,null,'no photo downloaded');assert.equal(i.photoSphereVisible,false);
 assert.equal(i.mr.area,'l1-auditorium-foyer','default area');assert.deepEqual(i.mr.areas,['l1-auditorium-foyer','l1-east-entrance']);
 assert.equal(i.mr.phase,'capture');assert.equal(i.mr.current,'A');assert.equal(i.mr.bimVisible,false,'services hidden until aligned');
 for(const [k,l] of Object.entries(i.layers)){assert.equal(l.error,null,k);assert.ok(l.elements>0,k);assert.equal(l.unidentifiedObjects||0,0,k);}
 assert.deepEqual(Object.keys(i.layers).sort(),[...layers].sort());
 assert.equal(await page.locator('#enterMR').isHidden(),true,'no Enter MR without immersive-ar');assert.equal(await page.locator('#enterVR').isHidden(),true);
 assert.match(await page.locator('#xrNote').textContent(),/Desktop MR simulation/);assert.equal(await page.locator('#mr').isVisible(),true);
 assert.match(await page.locator('#align').textContent(),/MR passthrough · .* · manual alignment, not surveyed · not aligned yet/);
 assert.equal(i.mr.rangeKey,'room');assert.deepEqual(i.mr.fade,{on:1,range:[8,14]});assert.equal(i.mr.outside,.12,'Lens: faint outside the cone');
 // simulated alignment: 5 synthetic touches (1 cm noise) through the same state machine and solver
 const sim=await page.evaluate(()=>xrDebug.mr.simulate());i=await page.evaluate(()=>xrInspection());
 assert.ok(i.mr.fit&&i.mr.fit.n===5&&i.mr.fit.rmsCm<3,'fit RMS '+i.mr.fit?.rmsCm);assert.ok(sim.maxTruthErrorCm<3&&sim.yawErrorDeg<.5,'recovers the hidden transform: '+JSON.stringify(sim));
 assert.equal(i.mr.phase,'aligned');assert.equal(i.mr.bimVisible,true);assert.ok(Math.abs(i.mr.bimRoot.rotationY-i.mr.fit.yawDeg*Math.PI/180)<1e-12);i.mr.bimRoot.position.forEach((v,k)=>assert.ok(Math.abs(v-i.mr.fit.t[k])<1e-12));
 assert.equal(i.mr.record.frame,'session');assert.equal(i.mr.record.label,'manual alignment, not surveyed');
 const stored=await page.evaluate(()=>JSON.parse(localStorage.getItem('grimes-mr-alignment/1')));assert.equal(stored.area,'l1-auditorium-foyer');assert.equal(stored.rmsCm,i.mr.record.rmsCm);
 assert.match(await page.locator('#align').textContent(),/manual alignment, not surveyed · RMS \d+\.\d cm \(5 points\)/);
 out.fit=i.mr.fit;out.sim=sim;
 // services render over the (cleared) background; distance culling keeps far batches out
 const fr=await page.evaluate(()=>{xrDebug.setStyle('all');return xrDebug.frameStats();});assert.ok(fr.litFraction>0,'services on screen: '+fr.litFraction);
 i=await page.evaluate(()=>xrInspection());assert.ok(i.totals.visibleDrawCalls>0&&i.totals.visibleDrawCalls<i.totals.drawCalls,'Room range culls distant batches');out.room={visible:i.totals.visibleDrawCalls,total:i.totals.drawCalls,frame:fr};
 await page.screenshot({path:path.join(OUT,'scan-xr-mr-all.png')});
 await page.evaluate(()=>xrDebug.mr.range('near'));i=await page.evaluate(()=>xrInspection());assert.deepEqual(i.mr.fade,{on:1,range:[3,6]});assert.ok(i.totals.visibleDrawCalls<=out.room.visible);out.near={visible:i.totals.visibleDrawCalls};
 await page.evaluate(()=>xrDebug.mr.range('all'));i=await page.evaluate(()=>xrInspection());assert.equal(i.mr.fade.on,0);assert.equal(i.totals.visibleDrawCalls,i.totals.drawCalls,'All = no culling');
 await page.evaluate(()=>{xrDebug.mr.range('room');xrDebug.setStyle('lens');});
 // info card on an aligned element: honest MR caption
 const card=await page.evaluate(async()=>{const I=xrInspection(),near=xrDebug.elementsNearStation(30);for(const e of near){const w=MRAlign.applyT(I.mr.T,e.point),c=I.camera.world,d=[w[0]-c[0],w[1]-c[1],w[2]-c[2]],n=Math.hypot(...d);
  xrDebug.look(Math.atan2(-d[0],-d[2]),Math.asin(d[1]/n));const r=await xrDebug.pickNdc(0,0);if(r?.id)return r;}return null;});
 assert.ok(card?.id,'centre-ray pick on an aligned service');assert.match(card.lines.footer[0],/^MR · .* · manual alignment, not surveyed · RMS/);assert.match(card.lines.footer[1],/Design \(BIM\) position/);out.pick={id:card.id,layer:card.layer,tier:card.tier};
 // check point: a device 5 cm (BIM x) from its design position is reported as 5 cm and logged
 const chk=await page.evaluate(()=>{xrDebug.mr.nextCheck();const I=xrInspection(),doc=I.mr,a=doc.check;return {id:a};});assert.equal(chk.id,'S1');
 const row=await page.evaluate(async()=>{const d=await (await fetch('buildings/grimes/mr-landmarks.json')).json(),c=d.areas[0].checks[0],T=xrInspection().mr.T;xrDebug.mr.check(MRAlign.applyT(T,[c.bim[0]+.05,6.3,c.bim[2]]));return xrInspection().mr.lastCheck;});
 assert.equal(row.check,'S1');assert.equal(row.horizontalCm,5);assert.equal(row.dxBimCm,5);assert.equal(row.dzBimCm,0);assert.match(row.note,/not surveyed/);
 assert.equal((await page.evaluate(()=>JSON.parse(localStorage.getItem('grimes-mr-checks/1')))).length,1);
 // nudge (1 cm up) is applied and saved
 const y0=i.mr.T.t[1];await page.evaluate(()=>xrDebug.mr.nudge('height',1));i=await page.evaluate(()=>xrInspection());assert.ok(Math.abs(i.mr.T.t[1]-y0-.01)<1e-9);assert.equal(i.mr.record.nudged,true);
 // the check loaded its element's layer (fire piping for S1) on demand
 await page.waitForFunction(()=>Object.values(xrInspection().layers).every(x=>x.loaded||x.error),null,{timeout:240000,polling:500});
 assert.equal((await page.evaluate(()=>xrInspection())).layers.fire?.loaded,true,'check S1 brings in its fire piping layer');
 // world panel (what the headset shows) and its buttons
 await page.evaluate(()=>{xrDebug.look(0,0);xrDebug.mr.panel(true);});await page.waitForTimeout(250);await page.screenshot({path:path.join(OUT,'scan-xr-mr-panel.png')});
 await page.evaluate(()=>xrDebug.mr.button(9));assert.equal((await page.evaluate(()=>xrInspection())).mr.rangeKey,'all');await page.evaluate(()=>xrDebug.mr.button(9));
 await page.evaluate(()=>xrDebug.mr.button(11));assert.equal((await page.evaluate(()=>xrInspection())).mr.page,'layers');await page.waitForTimeout(250);await page.screenshot({path:path.join(OUT,'scan-xr-mr-layers.png')});await page.evaluate(()=>xrDebug.mr.button(14));
 // Demo here: Grimes services at real scale in any room. Not an alignment: labelled DEMO, no RMS, no checks, never saved; a landmark alignment replaces it.
 {const savedBefore=await page.evaluate(()=>localStorage.getItem('grimes-mr-alignment/1')),checksBefore=await page.evaluate(()=>localStorage.getItem('grimes-mr-checks/1'));
  await page.evaluate(()=>xrDebug.mr.panel(true));
  const label=await page.evaluate(()=>MRAlign.demoLabel({id:xrInspection().mr.area}));
  await page.evaluate(()=>xrDebug.mr.button(15));i=await page.evaluate(()=>xrInspection());   // desktop: places 2 m ahead of the camera
  assert.equal(i.mr.phase,'demo');assert.equal(i.mr.fit,null,'no RMS / fit for a demo placement');assert.equal(i.mr.source,'demo');assert.equal(i.mr.persisted,false);assert.equal(i.mr.checksEnabled,false);
  assert.equal(i.mr.demo.label,label);assert.match(i.mr.demo.label,/^DEMO placement · not aligned to this building · Grimes L1 foyer services shown at real scale$/);
  assert.equal(i.mr.caption,label);assert.ok(!/RMS|manual alignment/.test(i.mr.caption));
  const al=await page.locator('#align').textContent();assert.match(al,/DEMO placement · not aligned to this building/);assert.ok(!/RMS|manual alignment/.test(al));
  assert.match(await page.locator('#mrLab').textContent(),/DEMO placement/);assert.match(await page.locator('#mrFit').textContent(),/DEMO placement · not an alignment · no RMS/);
  const Fp=i.mr.demo.floorPoint,Rf=i.mr.demo.reference,Wp=await page.evaluate(r=>MRAlign.applyT(xrInspection().mr.T,r),Rf);
  Wp.forEach((v,k)=>assert.ok(Math.abs(v-Fp[k])<1e-9,'reference point sits on the chosen floor point'));assert.ok(Math.abs(Fp[1])<1e-9,'floor point on the XR floor');
  assert.equal(i.mr.bimVisible,true);assert.equal(await page.evaluate(()=>localStorage.getItem('grimes-mr-alignment/1')),savedBefore,'demo does not touch the saved alignment');
  // explicit point + heading (head looking along +x: yaw -90 deg)
  await page.evaluate(()=>xrDebug.mr.demo([1,0,-3],-Math.PI/2));i=await page.evaluate(()=>xrInspection());
  const R2=i.mr.demo.reference,fwd=await page.evaluate(()=>{const T=xrInspection().mr.T,R=xrInspection().mr.demo.reference,a=MRAlign.applyT(T,R),b=MRAlign.applyT(T,[R[0],R[1],R[2]-1]);return [b[0]-a[0],b[2]-a[2]];});
  assert.ok(Math.abs(fwd[0]-1)<1e-9&&Math.abs(fwd[1])<1e-9,'BIM forward follows the head heading: '+fwd);
  assert.deepEqual(await page.evaluate(r=>MRAlign.applyT(xrInspection().mr.T,r).map(v=>+v.toFixed(9)),R2),[1,0,-3]);
  // ceiling height: services stay relative to the floor point; nudge up/down still works and is NOT saved
  const yD=i.mr.T.t[1];await page.evaluate(()=>xrDebug.mr.nudge('height',-1));i=await page.evaluate(()=>xrInspection());assert.ok(Math.abs(i.mr.T.t[1]-yD+.01)<1e-9);assert.equal(await page.evaluate(()=>localStorage.getItem('grimes-mr-alignment/1')),savedBefore,'nudging a demo is not saved');
  // checks are disabled
  await page.evaluate(()=>xrDebug.mr.nextCheck());i=await page.evaluate(()=>xrInspection());assert.equal(i.mr.check,null);assert.match(i.mr.note,/Check points are off in DEMO/);
  await page.evaluate(()=>xrDebug.mr.check([0,0,0]));assert.equal(await page.evaluate(()=>localStorage.getItem('grimes-mr-checks/1')),checksBefore,'no check logged in demo');
  await page.evaluate(()=>{xrDebug.look(0,0);xrDebug.mr.panel(true);});await page.waitForTimeout(250);await page.screenshot({path:path.join(OUT,'scan-xr-mr-demo-panel.png')});
  // a landmark alignment replaces the demo (and a demo replaces the alignment view) cleanly
  await page.evaluate(()=>xrDebug.mr.simulate());i=await page.evaluate(()=>xrInspection());
  assert.equal(i.mr.phase,'aligned');assert.equal(i.mr.demo,null);assert.equal(i.mr.checksEnabled,true);assert.ok(i.mr.fit&&i.mr.fit.rmsCm<3);assert.match(i.mr.caption,/^manual alignment, not surveyed · RMS/);
  assert.match(await page.locator('#align').textContent(),/manual alignment, not surveyed · RMS/);assert.ok(!/DEMO/.test(await page.locator('#align').textContent()));
  await page.evaluate(()=>xrDebug.mr.beginDemo());i=await page.evaluate(()=>xrInspection());assert.equal(i.mr.phase,'demo');assert.equal(i.mr.fit,null);
  await page.evaluate(()=>xrDebug.mr.simulate());i=await page.evaluate(()=>xrInspection());assert.equal(i.mr.phase,'aligned');assert.equal(i.mr.demo,null);
  out.demo={label,floorPoint:Fp};}
 // reload: the saved alignment is announced (applied on Enter MR; no anchor on desktop)
 await page.reload();await page.waitForFunction(()=>window.xrInspection?.()?.mr?.area,null,{timeout:60000});
 i=await page.evaluate(()=>xrInspection());assert.match(i.mr.note,/saved alignment exists .*no anchor/);
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(200);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'MR: no horizontal overflow at 390 px');await page.screenshot({path:path.join(OUT,'scan-xr-mr-390.png')});
 assert.deepEqual(errors.filter(e=>!/favicon/.test(e)),[]);
 out.heapMB=i.heapMB;await ctx.close();return out;
}
