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
  // XR menu panel renders and its buttons work with a desktop click ray
  await page.evaluate(()=>xrDebug.setMenu(true));await page.screenshot({path:path.join(OUT,'scan-xr-menu.png')});
  await page.evaluate(()=>xrDebug.menuAction(0));assert.equal((await page.evaluate(()=>xrInspection())).style,'all');
  // phone width: no horizontal overflow
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(200);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no horizontal overflow at 390 px');
  await page.screenshot({path:path.join(OUT,'scan-xr-390.png')});
  assert.ok(await page.evaluate(()=>{const a=document.getElementById('align');return a.scrollWidth<=a.clientWidth+1&&/not surveyed\)/.test(a.textContent);}),'alignment caveat is not clipped at 390 px');
  assert.deepEqual(errors.filter(e=>!/favicon/.test(e)),[]);
  fs.writeFileSync(path.join(OUT,'scan-xr-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));console.log('PASS scan-xr desktop smoke (registration, photo, Level-1 services, radius culling, card tiers, navigation, provisional Sep, menu, idle gating, 390 px)');
 }finally{await browser.close();if(server)server.kill();}
})().catch(e=>{console.error(e);process.exit(1);});
