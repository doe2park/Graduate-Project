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
  await page.addInitScript(()=>{window.__status=[];addEventListener('DOMContentLoaded',()=>{const el=document.getElementById('status');new MutationObserver(()=>window.__status.push(el.textContent)).observe(el,{childList:true,characterData:true,subtree:true});});});
  const t0=Date.now();await page.goto(base+'/scan-xr.html?'+layers.slice(1));
  await page.waitForFunction(()=>window.xrInspection?.().ready,null,{timeout:60000});
  const first=await page.evaluate(()=>xrInspection());
  assert.equal(first.capture.date,'2026-05-06');assert.equal(first.capture.provisional,false);assert.equal(first.station.id,'83697765','manifest default station');
  assert.deepEqual(first.texture,{width:4096,height:2048},'desktop without XR uses the full photo');
  assert.equal(await page.locator('#enterVR').isHidden(),true,'no Enter VR without immersive-vr');assert.match(await page.locator('#xrNote').textContent(),/Desktop preview/);
  assert.match(await page.locator('#align').textContent(),/registered \(internal residual ≈0\.13 m, not surveyed\)/);
  const cam=first.camera.world;first.station.positionScan.forEach((v,k)=>assert.ok(Math.abs(v-cam[k])<1e-6,'eye on the station'));
  // progress text: never "loaded / total" with loaded > total (gzip Content-Length vs decompressed bytes), and the gzip case is handled by the pure helper
  {const texts=await page.evaluate(()=>window.__status),bad=texts.filter(t=>{const m=t.match(/([\d.]+) \/ ([\d.]+) MB/);return m&&Number(m[1])>Number(m[2])+1e-9;});
   assert.deepEqual(bad,[],'no improper-fraction progress text');report.progressTexts=texts.filter(t=>/ MB/.test(t)).length;
   assert.equal(await page.evaluate(()=>ScanXRCore.loadProgressText('Fire piping 2/2',21.8e6,2.0e6)),'Fire piping 2/2 · 21.8 MB loaded');}
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
  if(process.env.XR_SMOKE_MR!=='0')report.mrBackdrop=await mrBackdropSmoke(browser,base,now);
  if(process.env.XR_SMOKE_SENSORS!=='0'){report.sensorsVr=await sensorsVrSmoke(browser,base,now);report.mrSensors=await mrSensorsSmoke(browser,base,now);}
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
const bdWait=(page,state='photo')=>page.waitForFunction(st=>{const b=window.xrInspection?.()?.mr?.backdrop;return !!b&&!b.busy&&b.state===st;},state,{timeout:90000,polling:250});
async function mrSmoke(browser,base,now){
 const ctx=await browser.newContext({viewport:{width:1280,height:800}}),page=await ctx.newPage(),errors=[],out={};
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({meters:{76:{latest:{kw:120.5,t:now}},3:{latest:{kw:12,t:now}}}})}));
 const layers=(process.env.XR_SMOKE_MR_LAYERS||'duct,plumbing').split(','),t0=Date.now();
 await page.goto(base+'/scan-xr.html?mode=ar&layers='+layers.join(','));
 await page.waitForFunction(n=>{const i=window.xrInspection?.();if(!i?.mr?.area)return false;const l=Object.values(i.layers);return l.length>=n&&l.every(x=>x.loaded||x.error);},layers.length,{timeout:240000,polling:500});
 let i=await page.evaluate(()=>xrInspection());out.layersReadyWallMs=Date.now()-t0;
 await bdWait(page);i=await page.evaluate(()=>xrInspection());
 assert.equal(i.mode,'ar');assert.equal(i.capture,null,'no VR capture state in MR');assert.deepEqual(i.texture,{width:2048,height:1024},'desktop MR preview: 2K May 6 photo backdrop');assert.equal(i.photoSphereVisible,true);
 assert.equal(i.mr.backdrop.state,'photo');assert.equal(i.mr.backdrop.date,'2026-05-06');assert.equal(i.mr.backdrop.background,false);
 assert.equal(await page.locator('#mrBackdropNote').textContent(),'Desktop preview: May 6 photo as background · in Quest the real room shows instead');assert.equal(await page.locator('#mrBackdropNote').isVisible(),true);
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
 const stored=await page.evaluate(()=>JSON.parse(localStorage.getItem('grimes-mr-alignment/2')).areas['l1-auditorium-foyer']);assert.equal(stored.area,'l1-auditorium-foyer');assert.equal(await page.evaluate(()=>localStorage.getItem('grimes-mr-alignment/1')),null,'no legacy single record');assert.equal(stored.rmsCm,i.mr.record.rmsCm);
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
 {const savedBefore=await page.evaluate(()=>localStorage.getItem('grimes-mr-alignment/2')),checksBefore=await page.evaluate(()=>localStorage.getItem('grimes-mr-checks/1'));
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
  assert.equal(i.mr.bimVisible,true);assert.equal(await page.evaluate(()=>localStorage.getItem('grimes-mr-alignment/2')),savedBefore,'demo does not touch the saved alignment');
  // explicit point + heading (head looking along +x: yaw -90 deg)
  await page.evaluate(()=>xrDebug.mr.demo([1,0,-3],-Math.PI/2));i=await page.evaluate(()=>xrInspection());
  const R2=i.mr.demo.reference,fwd=await page.evaluate(()=>{const T=xrInspection().mr.T,R=xrInspection().mr.demo.reference,a=MRAlign.applyT(T,R),b=MRAlign.applyT(T,[R[0],R[1],R[2]-1]);return [b[0]-a[0],b[2]-a[2]];});
  assert.ok(Math.abs(fwd[0]-1)<1e-9&&Math.abs(fwd[1])<1e-9,'BIM forward follows the head heading: '+fwd);
  assert.deepEqual(await page.evaluate(r=>MRAlign.applyT(xrInspection().mr.T,r).map(v=>+v.toFixed(9)),R2),[1,0,-3]);
  // ceiling height: services stay relative to the floor point; nudge up/down still works and is NOT saved
  const yD=i.mr.T.t[1];await page.evaluate(()=>xrDebug.mr.nudge('height',-1));i=await page.evaluate(()=>xrInspection());assert.ok(Math.abs(i.mr.T.t[1]-yD+.01)<1e-9);assert.equal(await page.evaluate(()=>localStorage.getItem('grimes-mr-alignment/2')),savedBefore,'nudging a demo is not saved');
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
 i=await page.evaluate(()=>xrInspection());assert.match(i.mr.note,/saved alignment of this area exists .*no anchor/);
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(200);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'MR: no horizontal overflow at 390 px');await page.screenshot({path:path.join(OUT,'scan-xr-mr-390.png')});
 assert.deepEqual(errors.filter(e=>!/favicon/.test(e)),[]);
 out.heapMB=i.heapMB;await ctx.close();return out;
}

/* Desktop MR preview backdrop + per-area records + automatic anchor restore (mocked XR anchor API). Not a headset test. */
async function canvasStats(page,clip){
 const b64=(await page.screenshot({clip})).toString('base64');
 return page.evaluate(async b=>{const img=new Image();img.src='data:image/png;base64,'+b;await img.decode();const c=document.createElement('canvas');c.width=img.width;c.height=img.height;const g=c.getContext('2d');g.drawImage(img,0,0);
  const d=g.getImageData(0,0,c.width,c.height).data;let sum=0,sq=0,dark=0,n=0;for(let k=0;k<d.length;k+=16){const y=.2126*d[k]+.7152*d[k+1]+.0722*d[k+2];sum+=y;sq+=y*y;if(y<12)dark++;n++;}
  const m=sum/n;return {mean:m,std:Math.sqrt(Math.max(0,sq/n-m*m)),darkFraction:dark/n};},b64);}
async function mrBackdropSmoke(browser,base,now){
 const out={},mk=async(route)=>{const ctx=await browser.newContext({viewport:{width:1280,height:800}}),page=await ctx.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({meters:{76:{latest:{kw:120.5,t:now}}}})}));if(route)await route(page);return {ctx,page,errors};};
 const clip={x:470,y:90,width:790,height:620};
 // 1) demo + sensors (the /mr default): photo of the station nearest the leak cluster, BIM + sensors registered on it
 {const {ctx,page,errors}=await mk();
  await page.goto(base+'/scan-xr.html?mode=ar&place=demo&sensors=demo&layers=duct,plumbing');
  await page.waitForFunction(()=>{const i=window.xrInspection?.();return i?.mr?.phase==='demo'&&i.sensors?.ready&&Object.values(i.layers).every(l=>l.loaded||l.error);},null,{timeout:240000,polling:500});
  await bdWait(page);await page.evaluate(()=>xrDebug.setStyle('all'));await page.waitForTimeout(500);
  const i=await page.evaluate(()=>xrInspection());
  assert.equal(i.mr.backdrop.state,'photo');assert.equal(i.photoSphereVisible,true);assert.deepEqual(i.texture,{width:2048,height:1024},'2K mobile panorama');assert.equal(i.mr.phase,'demo');
  // the chosen station is the nearest to the sensor cluster (independent computation in the page)
  const near=await page.evaluate(async()=>{const cfg=ScanXRCore.captureConfig('2026-05-06'),[m,r]=await Promise.all([fetch(cfg.photo).then(x=>x.json()),fetch(cfg.registration).then(x=>x.json())]);
   const tf=ScanXRCore.bimRootTransform(r),c=ScanXRCore.applyRootTransform(tf,xrInspection().sensors.center);let best=-1,bd=1e9;m.stations.forEach((s,k)=>{const d=Math.hypot(s.position[0]-c[0],s.position[2]-c[2]);if(d<bd){bd=d;best=k;}});return {best,id:m.stations[best].id,dist:bd};});
  assert.equal(i.mr.backdrop.station,near.best,'nearest May 6 station to the sensor cluster');out.station={index:near.best,number:near.best+1,id:near.id,distM:+near.dist.toFixed(2),scene:i.sensors.scene};
  // the camera sits at the sphere (the station) and BIM pins are registered on the photo: the photo-VR relation scan->BIM->world equals sphere->pin
  const reg=await page.evaluate(async()=>{const I=xrInspection(),cfg=ScanXRCore.captureConfig('2026-05-06'),r=await fetch(cfg.registration).then(x=>x.json());
   const s=I.sensors.sensors[0],w=MRAlign.applyT(I.mr.T,s.point),cam=I.camera.world,sp=I.mr.backdrop.sphereWorld;
   const tf=ScanXRCore.bimRootTransform(r),pinScan=ScanXRCore.applyRootTransform(tf,s.point),G=MRAlign.composeT(I.mr.T,{yawDeg:r.rotationYDegrees,t:r.translation}),m=await fetch(cfg.photo).then(x=>x.json()),st=m.stations[I.mr.backdrop.station];
   return {camToSphere:Math.hypot(cam[0]-sp[0],cam[1]-sp[1],cam[2]-sp[2]),pinDirWorld:[w[0]-sp[0],w[1]-sp[1],w[2]-sp[2]],pinDirScan:[pinScan[0]-st.position[0],pinScan[1]-st.position[1],pinScan[2]-st.position[2]],yaw:G.yawDeg,T:I.mr.T};});
  assert.ok(reg.camToSphere<1e-6,'camera at the photo centre');const dw=Math.hypot(...reg.pinDirWorld),ds=Math.hypot(...reg.pinDirScan);assert.ok(Math.abs(dw-ds)<1e-6,'pin distance from the photo centre is identical in photo VR and in the MR preview: '+dw+' vs '+ds);
  const st=await canvasStats(page,clip);out.pixels=st;assert.ok(st.mean>25&&st.std>12&&st.darkFraction<.5,'photo backdrop is not black: '+JSON.stringify(st));
  assert.equal(await page.locator('#mrBackdropNote').textContent(),'Desktop preview: May 6 photo as background · in Quest the real room shows instead');
  await page.screenshot({path:path.join(OUT,'mr-desktop-backdrop.png')});
  assert.deepEqual(errors.filter(e=>!/favicon/.test(e)),[]);await ctx.close();}
 // 2) photo unavailable -> dark gradient + floor grid, not pure black
 {const {ctx,page,errors}=await mk(p=>p.route('**/scan-assets/panoramas/mobile/**',r=>r.abort()));
  await page.goto(base+'/scan-xr.html?mode=ar&place=demo&sensors=demo&layers=duct,plumbing');
  await page.waitForFunction(()=>{const i=window.xrInspection?.();return i?.mr?.phase==='demo'&&i.sensors?.ready;},null,{timeout:240000,polling:500});
  await bdWait(page,'fallback');await page.waitForTimeout(400);const i=await page.evaluate(()=>xrInspection());
  assert.equal(i.mr.backdrop.fallbackGrid,true);assert.equal(i.mr.backdrop.background,true);assert.equal(i.photoSphereVisible,false);assert.match(await page.locator('#mrBackdropNote').textContent(),/photo not available, plain background/);
  const st=await canvasStats(page,clip);out.fallbackPixels=st;assert.ok(st.mean>8&&st.std>4,'fallback is a visible gradient, not black: '+JSON.stringify(st));
  await page.screenshot({path:path.join(OUT,'mr-desktop-backdrop-fallback.png')});await ctx.close();}
 // 3) per-area records, migration, export, restore decisions with a mocked anchor API
 {const {ctx,page,errors}=await mk();
  await page.goto(base+'/scan-xr.html?mode=ar&layers=duct');
  await page.waitForFunction(()=>window.xrInspection?.()?.mr?.area&&Object.values(xrInspection().layers).every(l=>l.loaded||l.error),null,{timeout:240000,polling:500});await bdWait(page);
  await page.evaluate(()=>{xrDebug.mr.simulate();xrDebug.mr.startAlign('l1-east-entrance');xrDebug.mr.simulate();});
  let areas=await page.evaluate(()=>Object.keys(JSON.parse(localStorage.getItem('grimes-mr-alignment/2')).areas).sort());assert.deepEqual(areas,['l1-auditorium-foyer','l1-east-entrance'],'one record per area');
  await page.evaluate(()=>xrDebug.mr.forget());areas=await page.evaluate(()=>Object.keys(JSON.parse(localStorage.getItem('grimes-mr-alignment/2')).areas));assert.deepEqual(areas,['l1-auditorium-foyer'],'forgetting east keeps the foyer');
  // migration: a legacy single record is moved under its area on the next load
  await page.evaluate(()=>{const rec=MRAlign.loadRecord(localStorage,'l1-auditorium-foyer');localStorage.removeItem('grimes-mr-alignment/2');localStorage.setItem('grimes-mr-alignment/1',JSON.stringify(rec));});
  await page.reload();await page.waitForFunction(()=>window.xrInspection?.()?.mr?.area,null,{timeout:120000});
  assert.deepEqual(await page.evaluate(()=>[localStorage.getItem('grimes-mr-alignment/1'),Object.keys(JSON.parse(localStorage.getItem('grimes-mr-alignment/2')).areas)]),[null,['l1-auditorium-foyer']]);
  // export download: no network, no pose, no handle
  const [dl]=await Promise.all([page.waitForEvent('download'),page.locator('#mrExport').click()]);const ex=JSON.parse(fs.readFileSync(await dl.path(),'utf8'));
  assert.match(dl.suggestedFilename(),/^grimes-mr-alignments-\d{4}-\d\d-\d\d\.json$/);assert.equal(ex.rows.length,1);assert.deepEqual(Object.keys(ex.rows[0]).sort(),['anchorPresent','area','created','frame','heightSource','level','nudged','points','rmsCm']);assert.equal(ex.rows[0].anchorPresent,false);out.export=ex.rows[0];
  // restore with a mocked persistent-anchor API (foyer record with an anchor)
  await page.evaluate(()=>xrDebug.mr.startAlign('l1-auditorium-foyer'));   // the URL kept the last area (east)
  await page.evaluate(()=>{const T={yawDeg:12,t:[1,0.1,2]},A={yawDeg:30,t:[4,0,5]};const rec=MRAlign.makeRecord({area:'l1-auditorium-foyer',level:'L1',T,fit:{ok:true,rmsM:0.021,n:5,heightSource:'floor-touch'},anchorHandle:'uuid-mock',anchorLocal:MRAlign.toAnchorFrame(T,A),created:'2026-10-30T10:00:00Z'});MRAlign.saveRecord(localStorage,rec);window.__A=A;window.__T=T;});
  await page.evaluate(()=>{window.__calls=[];xrDebug.mr.restoreWith({restorePersistentAnchor:h=>{window.__calls.push(h);return Promise.resolve({anchorSpace:{},delete(){}});}});});
  await page.waitForFunction(()=>xrInspection().mr.restore?.phase==='tracking',null,{timeout:5000}).catch(async e=>{const d=await page.evaluate(()=>{const m=xrInspection().mr;return {restore:m.restore,note:m.note,phase:m.phase,area:m.area,events:m.events};});throw new Error('restore did not reach tracking: '+JSON.stringify(d));});let i=await page.evaluate(()=>xrInspection());
  assert.deepEqual(await page.evaluate(()=>window.__calls),['uuid-mock']);assert.equal(i.mr.session,undefined);assert.notEqual(i.mr.phase,'capture','landmark touching is skipped');
  assert.equal(i.mr.bimVisible,false,'nothing is shown before the anchor is tracked');
  await page.evaluate(()=>{const q=Math.sin(window.__A.yawDeg*Math.PI/360);xrDebug.mr.anchorPose(window.__A.t,[0,q,0,Math.cos(window.__A.yawDeg*Math.PI/360)]);});i=await page.evaluate(()=>xrInspection());
  assert.equal(i.mr.restore,null);assert.equal(i.mr.phase,'aligned');assert.equal(i.mr.bimVisible,true);assert.match(i.mr.source,/^anchor \(restored 2026-10-30\)/);
  assert.match(i.mr.note,/^Restored from Quest anchor · 2026-10-30 · RMS 2\.1 cm at save · manual alignment restored via Quest anchor, not surveyed · check one point or Re-align$/);
  assert.ok(Math.abs(i.mr.T.yawDeg-12)<1e-6&&i.mr.T.t.every((v,k)=>Math.abs(v-[1,0.1,2][k])<1e-6),'T = anchor pose . stored anchor-relative alignment');
  // not found: the promise rejects -> plain message + landmark flow
  await page.evaluate(()=>xrDebug.mr.restoreWith({restorePersistentAnchor:()=>Promise.reject(new Error('not found'))}));await page.waitForFunction(()=>xrInspection().mr.phase==='capture',null,{timeout:5000});
  i=await page.evaluate(()=>xrInspection());assert.match(i.mr.note,/saved Grimes anchor was not found \(not found\)\. Starting the landmark alignment/);
  // timeout (8 s): never answers
  await page.evaluate(()=>xrDebug.mr.restoreWith({restorePersistentAnchor:()=>new Promise(()=>{})}));i=await page.evaluate(()=>xrInspection());assert.equal(i.mr.restore.phase,'looking');assert.match(await page.locator('#mrFit').textContent(),/Looking for the saved Grimes anchor…/);
  await page.waitForFunction(()=>xrInspection().mr.phase==='capture',null,{timeout:12000});i=await page.evaluate(()=>xrInspection());assert.match(i.mr.note,/not found \(no answer in 8 s\)/);
  // no anchor API in the session: landmark flow with a plain message; a record without anchor keeps the stale warning
  await page.evaluate(()=>xrDebug.mr.restoreWith({}));i=await page.evaluate(()=>xrInspection());assert.equal(i.mr.phase,'capture');assert.match(i.mr.note,/no anchors in this session/);
  await page.evaluate(()=>{const r=MRAlign.loadRecord(localStorage,'l1-auditorium-foyer');MRAlign.saveRecord(localStorage,MRAlign.makeRecord({area:r.area,level:'L1',T:{yawDeg:r.yawDeg,t:r.t},created:r.created}));xrDebug.mr.restoreWith({restorePersistentAnchor:()=>Promise.reject()});});
  i=await page.evaluate(()=>xrInspection());assert.equal(i.mr.stale,true);assert.match(i.mr.note,/WITHOUT an anchor/);
  // demo never touches or reads the records
  const before=await page.evaluate(()=>localStorage.getItem('grimes-mr-alignment/2'));await page.evaluate(()=>xrDebug.mr.beginDemo());assert.equal(await page.evaluate(()=>localStorage.getItem('grimes-mr-alignment/2')),before);
  assert.deepEqual((await page.evaluate(()=>xrInspection())).mr.sessionInit.requiredFeatures,['local-floor']);assert.ok((await page.evaluate(()=>xrInspection())).mr.sessionInit.optionalFeatures.includes('anchors'));
  assert.deepEqual(errors.filter(e=>!/favicon/.test(e)),[]);await ctx.close();}
 return out;
}

/* Simulated sensors in the photo VR view (&sensors=demo, May 6 default station): pins at the anchored elements, a pin pick opens a SIMULATED card.
   The fire layer (leak scene) is loaded on demand. Desktop only; nothing here is a headset measurement. */
async function sensorsVrSmoke(browser,base,now){
 const ctx=await browser.newContext({viewport:{width:1280,height:800}}),page=await ctx.newPage(),errors=[],out={};
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({meters:{76:{latest:{kw:120.5,t:now}}}})}));
 const reg=JSON.parse(fs.readFileSync(path.join(ROOT,'twin/sensors/registry.json')));
 await page.goto(base+'/scan-xr.html?layers=equipment&sensors=demo');
 await page.waitForFunction(()=>{const i=window.xrInspection?.();return i?.ready&&i.sensors&&(i.sensors.ready||i.sensors.error);},null,{timeout:240000,polling:500});
 let i=await page.evaluate(()=>xrInspection());assert.equal(i.sensors.error,null);assert.equal(i.sensors.scene,'leak','default scene');assert.equal(i.sensors.ready,true);
 assert.equal(i.layers.fire?.loaded,true,'fire layer loaded on demand for the leak scene');
 const want=reg.sensors.filter(s=>s.scenario==='leak');assert.deepEqual(i.sensors.sensors.map(s=>s.id).sort(),want.map(s=>s.id).sort());
 for(const s of i.sensors.sensors){const w=want.find(x=>x.id===s.id);assert.equal(s.layer,w.anchor.layer);assert.equal(s.element,w.anchor.id);s.point.forEach(v=>assert.ok(Number.isFinite(v)));
  assert.equal(s.simulated,true,s.id+' value is simulated');assert.match(s.chip,/ · SIM$/);}
 assert.equal(i.sensors.dtsMeshes,1,'DTS colouring along the pipe');assert.equal(i.sensors.rings,1,'alert ring');
 // all leak sensors sit on the one anchored pipe (same element): their points lie within its length of each other
 const pts=i.sensors.sensors.map(s=>s.point),span=Math.max(...pts.map(a=>Math.max(...pts.map(b=>Math.hypot(a[0]-b[0],a[1]-b[1],a[2]-b[2])))));assert.ok(span>0.3&&span<60,'cluster span '+span);
 out.span=span;
 const card=await page.evaluate(async()=>{xrDebug.sensors.lookAt('leak-alert');return xrDebug.pickNdc(0,0);});
 assert.equal(card?.sensor,'leak-alert','centre-ray pick on the pin');assert.equal(card.simulated,true);assert.equal(card.lines.badge,'SIMULATED');
 assert.equal(card.lines.footer[0],'Demo sensor — illustrative, not installed · values simulated');assert.match(card.lines.footer[1],/registered/);assert.match(card.lines.rows[2],/Pipe219763 · fire:278123/);assert.match(card.lines.rows[0],/^Simulated value: /);
 assert.equal((await page.evaluate(()=>xrInspection())).sensors.card,'leak-alert');
 await page.waitForTimeout(200);await page.screenshot({path:path.join(OUT,'scan-xr-sensors-vr-card.png')});
 // scene cycling from the menu: leak -> air (duct layer on demand); off after the last scene
 await page.evaluate(()=>{xrDebug.setMenu(true);});
 assert.ok((await page.evaluate(()=>xrInspection().menu.buttons)) ,'menu exists');
 await page.evaluate(()=>xrDebug.setMenu(false));
 await page.evaluate(()=>xrDebug.menuAction('sensors')).catch(()=>{});
 await page.waitForFunction(()=>xrInspection().sensors.scene==='air'&&xrInspection().sensors.ready,null,{timeout:240000});
 i=await page.evaluate(()=>xrInspection());assert.ok(i.sensors.sensors.length>=3);assert.equal(i.layers.duct?.loaded,true);assert.equal(i.sensors.card,null,'card closed when the scene changes');
 for(const sc of ['water','elec','rotating']){await page.evaluate(()=>xrDebug.sensors.next());await page.waitForFunction(s=>xrInspection().sensors.scene===s&&xrInspection().sensors.ready,sc,{timeout:240000});}
 await page.evaluate(()=>xrDebug.menuAction('sensors'));await page.waitForFunction(()=>xrInspection().sensors.enabled===false,null,{timeout:20000});
 i=await page.evaluate(()=>xrInspection());assert.equal(i.sensors.drawables,0);assert.equal(i.sensors.ready,false);
 // no sensors without the opt-in: no request for the sensor files at all
 const p2=await ctx.newPage(),reqs=[];p2.on('request',r=>reqs.push(r.url()));await p2.goto(base+'/scan-xr.html?layers=equipment');await p2.waitForFunction(()=>xrInspection?.().ready,null,{timeout:120000});
 assert.deepEqual(reqs.filter(u=>/sensors\/|sensor-demo|feed\.js/.test(u)),[],'no sensor files without sensors=demo');assert.equal((await p2.evaluate(()=>xrInspection())).sensors.enabled,false);
 assert.deepEqual(errors.filter(e=>!/favicon/.test(e)),[]);await ctx.close();return out;
}
/* /mr default (demo placement + simulated sensors), the 2D choice buttons and the saved-alignment rule, on a desktop without immersive-ar. */
async function mrSensorsSmoke(browser,base,now){
 const ctx=await browser.newContext({viewport:{width:1280,height:800}}),page=await ctx.newPage(),errors=[],out={};
 page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({meters:{76:{latest:{kw:120.5,t:now}}}})}));
 // plain /mr: the short address opens the demo with sensors; an explicit param wins; extra params pass through
 const q=async s=>{await page.goto(base+'/mr/'+s);await page.waitForURL(/scan-xr\.html/);return new URL(page.url()).searchParams;};
 let u=await q('?layers=fire,duct,plumbing');assert.equal(u.get('mode'),'ar');assert.equal(u.get('place'),'demo');assert.equal(u.get('sensors'),'demo');assert.equal(u.get('layers'),'fire,duct,plumbing');
 await page.waitForFunction(()=>{const i=window.xrInspection?.();return i?.mr?.phase&&i.sensors?.ready&&i.mr.phase==='demo';},null,{timeout:240000,polling:500});
 let i=await page.evaluate(()=>xrInspection());
 assert.equal(i.mr.phase,'demo');assert.equal(i.sensors.scene,'leak');assert.equal(i.mr.demo.sensorScene,'leak');assert.equal(i.mr.persisted,false);
 // the demo reference is the scene centroid at the level floor, not the foyer landmark centroid
 const c=i.sensors.center,area=await page.evaluate(()=>MRAlign.demoReference({floorY:xrInspection().mr.demo.reference[1],points:[]})).catch(()=>null);
 assert.ok(Math.abs(i.mr.demo.reference[0]-c[0])<1e-9&&Math.abs(i.mr.demo.reference[2]-c[2])<1e-9,'reference x,z = sensor cluster centre');
 const lm=JSON.parse(fs.readFileSync(path.join(ROOT,'buildings/grimes/mr-landmarks.json'))).areas[0];assert.equal(i.mr.demo.reference[1],lm.floorY);
 const foyer=await page.evaluate(()=>0);const fc=lm.points.filter(p=>p.kind!=='y').reduce((a,p)=>[a[0]+p.bim[0]/4,a[1]+p.bim[2]/4],[0,0]);
 assert.ok(Math.hypot(i.mr.demo.reference[0]-fc[0],i.mr.demo.reference[2]-fc[1])>1,'not the foyer centroid');
 const W=await page.evaluate(()=>{const I=xrInspection();return {ref:MRAlign.applyT(I.mr.T,I.mr.demo.reference),floor:I.mr.demo.floorPoint,pins:I.sensors.sensors.map(s=>MRAlign.applyT(I.mr.T,s.point))};});
 W.ref.forEach((v,k)=>assert.ok(Math.abs(v-W.floor[k])<1e-9,'floor point sits under the cluster centre'));
 for(const p of W.pins){assert.ok(Math.hypot(p[0]-W.floor[0],p[2]-W.floor[2])<40,'pin within 40 m horizontally of the user');assert.ok(p[1]>W.floor[1]+0.5,'pin above the floor: '+p[1]);}
 out.pinHeightsAboveFloor=W.pins.map(p=>+(p[1]-W.floor[1]).toFixed(2));
 assert.match(i.mr.caption,/^DEMO placement · not aligned to this building · Grimes L1 foyer services shown at real scale · placed around the demo-sensor scene "Leak" \(simulated sensors\)$/);assert.ok(!/RMS|manual alignment/.test(i.mr.caption));
 assert.match(await page.locator('#align').textContent(),/DEMO placement/);assert.match(await page.locator('#mrNow').textContent(),/DEMO placement.*sensors Leak \(simulated\)/);
 const card=await page.evaluate(async()=>{xrDebug.sensors.lookAt('leak-alert');return xrDebug.pickNdc(0,0);});
 assert.equal(card?.sensor,'leak-alert');assert.match(card.lines.footer[1],/DEMO placement · not aligned to this building/);assert.equal(card.lines.footer[0],'Demo sensor — illustrative, not installed · values simulated');
 await page.evaluate(()=>{xrDebug.sensors.lookAt('leak-dts');xrDebug.setStyle('all');});await page.waitForTimeout(400);await page.screenshot({path:path.join(OUT,'scan-xr-mr-demo-sensors.png')});
 // 2D buttons reflect the state; the scene picker re-places the demo around the new scene and updates the URL
 assert.equal(await page.locator('#chDemo').getAttribute('aria-pressed'),'true');assert.equal(await page.locator('#chScene-leak').getAttribute('aria-pressed'),'true');
 const refLeak=i.mr.demo.reference.slice();
 await page.locator('#chScene-water').click();await page.waitForFunction(()=>xrInspection().sensors.scene==='water'&&xrInspection().sensors.ready,null,{timeout:240000});
 i=await page.evaluate(()=>xrInspection());assert.equal(i.mr.demo.sensorScene,'water');assert.notDeepEqual(i.mr.demo.reference,refLeak,'demo re-placed around the new scene');
 assert.deepEqual(i.mr.demo.floorPoint,W.floor,'same floor point and heading');assert.equal(new URL(page.url()).searchParams.get('scene'),'water');assert.equal(new URL(page.url()).searchParams.get('sensors'),'demo');
 // in-headset panel: scene button (index 18) cycles, mode button (16) switches
 await page.evaluate(()=>{xrDebug.mr.panel(true);xrDebug.mr.button(18);});await page.waitForFunction(()=>xrInspection().sensors.scene==='elec'&&xrInspection().sensors.ready,null,{timeout:240000});
 await page.evaluate(()=>{xrDebug.look(0,0);});await page.waitForTimeout(250);await page.screenshot({path:path.join(OUT,'scan-xr-mr-demo-sensors-panel.png')});
 // a saved Grimes alignment survives the demo default and is used when Grimes mode is chosen
 await page.evaluate(()=>xrDebug.mr.simulate());const saved=await page.evaluate(()=>localStorage.getItem('grimes-mr-alignment/2'));assert.ok(saved,'alignment saved');
 await page.locator('#chDemo').click();await page.waitForFunction(()=>xrInspection().mr.phase==='demo'&&xrInspection().sensors.ready,null,{timeout:240000});
 assert.equal(await page.evaluate(()=>localStorage.getItem('grimes-mr-alignment/2')),saved,'demo does not touch the saved alignment');assert.equal(new URL(page.url()).searchParams.get('place'),'demo');
 await page.locator('#chFoyer').click();await page.waitForFunction(()=>xrInspection().mr.phase==='aligned',null,{timeout:20000});
 i=await page.evaluate(()=>xrInspection());assert.match(i.mr.source,/saved/);assert.equal(i.mr.demo,null);assert.equal(new URL(page.url()).searchParams.get('place'),'grimes');assert.equal(new URL(page.url()).searchParams.get('area'),'l1-auditorium-foyer');
 assert.match(await page.locator('#mrNow').textContent(),/Grimes alignment/);assert.equal(await page.locator('#chFoyer').getAttribute('aria-pressed'),'true');
 assert.equal(await page.evaluate(()=>localStorage.getItem('grimes-mr-alignment/2')),saved);
 // east entrance has no saved alignment: a fresh landmark flow; sensors stay on
 await page.locator('#chEast').click();await page.waitForFunction(()=>xrInspection().mr.area==='l1-east-entrance',null,{timeout:20000});i=await page.evaluate(()=>xrInspection());assert.equal(i.mr.phase,'capture');assert.equal(i.sensors.enabled,true);assert.equal(new URL(page.url()).searchParams.get('area'),'l1-east-entrance');
 // sensors toggle off/on
 await page.locator('#chSens').click();await page.waitForFunction(()=>xrInspection().sensors.enabled===false,null,{timeout:20000});assert.equal(new URL(page.url()).searchParams.get('sensors'),'off');assert.match(await page.locator('#chSens').textContent(),/OFF/);
 // reload keeps the choice
 await page.reload();await page.waitForFunction(()=>window.xrInspection?.()?.mr?.area==='l1-east-entrance',null,{timeout:120000});assert.equal((await page.evaluate(()=>xrInspection())).sensors.enabled,false);
 // explicit params beat the /mr defaults
 u=await q('?place=');assert.equal(u.get('place'),'');assert.equal(u.get('sensors'),'demo');await page.waitForFunction(()=>window.xrInspection?.()?.mr?.area,null,{timeout:120000});assert.notEqual((await page.evaluate(()=>xrInspection())).mr.phase,'demo');
 assert.deepEqual(errors.filter(e=>!/favicon|Failed to fetch/.test(e)),[]);   // reload/navigation aborts layer fetches in flight; any other error fails (it aborts the layer fetches in flight)
 u=await q('?sensors=off');assert.equal(u.get('place'),'demo');assert.equal(u.get('sensors'),'off');
 await ctx.close();return out;
}
