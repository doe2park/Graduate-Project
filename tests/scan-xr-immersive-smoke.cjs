/* scan-xr.html IMMERSIVE smoke: the Enter VR render path under an emulated Quest 2 (Meta IWER, Immersive Web Emulation Runtime).
   The desktop smoke (tests/scan-xr-smoke.cjs) never presents an XR session, so it cannot see a black headset view. This test
   injects IWER before the page scripts, presses Enter VR (immersive-vr, two tracked Touch controllers), lets the XR animation
   loop run, reads pixels from the XR framebuffer inside an XR frame (after three.js drew it) and asserts:
     - no page errors / console errors, the XR loop keeps producing frames (an exception inside setAnimationLoop stops it),
     - the photo sphere is visible and the XR view is not black (lit fraction of a 24x16 grid of sampled pixels),
     - the same after a controller trigger, a stick push (aim preview), the B/Y menu and with hand tracking.
   Emulation is not a headset: IWER renders into the page canvas (no real XRWebGLLayer framebuffer, no compositor, no foveation),
   so this catches page-side failures (exceptions, invisible sphere, wrong clear, broken rig) but not Quest Browser driver issues.

   PLAYWRIGHT_MODULE=/path/to/playwright(-core) IWER_BUILD=/path/to/node_modules/iwer/build/iwer.min.js node tests/scan-xr-immersive-smoke.cjs
   IWER_BUILD: the UMD build of iwer (pinned; tested with iwer@2.5.0). Missing -> the test is SKIPPED (exit 0), or FAILS with
   XR_IMMERSIVE_REQUIRED=1. Optional: CHROME_EXECUTABLE, VIEWER_BASE_URL (default: python3 -m http.server on a free port),
   XR_SMOKE_LAYERS (default 'equipment', small and fast; 'default' = the page default layers), XR_SMOKE_GIT_REV (serve scan-xr.html
   and twin/*.js from that git revision instead of the working tree, for regression bisecting), XR_SMOKE_CORE_REV (serve only
   twin/xr-core.js from that revision = a stale cached core next to a newer page, the 2026-10-22 black-view case: the page must
   refuse Enter VR, and a forced session must keep rendering), VALIDATION_OUTPUT (screenshots + scan-xr-immersive.json). */
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),net=require('node:net'),assert=require('node:assert/strict'),{spawn,execFileSync}=require('node:child_process');
const ROOT=path.join(__dirname,'..'),OUT=process.env.VALIDATION_OUTPUT||path.join(os.tmpdir(),'grimes-validation','scan-xr-immersive');
const IWER=process.env.IWER_BUILD;
if(!IWER||!fs.existsSync(IWER)){const msg='SKIP scan-xr-immersive-smoke: set IWER_BUILD to iwer/build/iwer.min.js (npm install iwer@2.5.0 in a temp dir)';
 if(process.env.XR_IMMERSIVE_REQUIRED==='1'){console.error(msg.replace('SKIP','FAIL'));process.exit(1);}console.log(msg);process.exit(0);}
let chromium;try{({chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright'));}catch(e){console.log('SKIP scan-xr-immersive-smoke: playwright not found (PLAYWRIGHT_MODULE)');process.exit(process.env.XR_IMMERSIVE_REQUIRED==='1'?1:0);}
fs.mkdirSync(OUT,{recursive:true});
const REV=process.env.XR_SMOKE_GIT_REV||null,CORE_REV=process.env.XR_SMOKE_CORE_REV||null;
const fromRev=(f,rev)=>execFileSync('git',['show',rev+':'+f],{cwd:ROOT,maxBuffer:64<<20});
const freePort=()=>new Promise(r=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>r(p));});});
/* Runs in the page before any page script: install the emulated Quest 2, keep a handle on the session, and register a
   per-frame probe AFTER three.js's own XR frame callback so readPixels sees the finished XR frame (same frame, before compositing). */
const INIT=`(()=>{const dev=new IWER.XRDevice(IWER.metaQuest2,{stereoEnabled:true});dev.installRuntime({forceInstall:true});window.__iwer=dev;
 const probe=window.__xrProbe={frames:0,samples:null,want:false,session:null,errors:[]};
 const orig=navigator.xr.requestSession.bind(navigator.xr);
 navigator.xr.requestSession=async(mode,init)=>{const s=await orig(mode,init);probe.session=s;probe.mode=mode;probe.init=JSON.parse(JSON.stringify(init||{}));
  const tick=(t,frame)=>{probe.frames++;
   if(probe.want){probe.want=false;try{const gl=s.renderState.baseLayer.context,fb=s.renderState.baseLayer.framebuffer;gl.bindFramebuffer(gl.FRAMEBUFFER,fb);
     const w=gl.drawingBufferWidth,h=gl.drawingBufferHeight,px=new Uint8Array(4);let lit=0,n=0,sum=[0,0,0];
     for(let i=1;i<24;i++)for(let j=1;j<16;j++){gl.readPixels(Math.floor(w*i/24),Math.floor(h*j/16),1,1,gl.RGBA,gl.UNSIGNED_BYTE,px);n++;sum[0]+=px[0];sum[1]+=px[1];sum[2]+=px[2];if(px[0]+px[1]+px[2]>45)lit++;}
     probe.samples={w,h,n,lit,litFraction:lit/n,mean:sum.map(v=>Math.round(v/n)),frame:probe.frames};}catch(e){probe.errors.push(String(e&&e.message||e));}}
   s.requestAnimationFrame(tick);};
  // three.js registers its XR frame callback when renderer.xr.setSession() resolves (after this promise). Registering ours later keeps
  // it after three's in every frame (both re-register in callback order), so readPixels sees this frame's drawing, or nothing if the
  // page did not draw (the black headset case: IWER's canvas is not preserved between frames).
  setTimeout(()=>s.requestAnimationFrame(tick),500);return s;};
})();`;
async function sample(page){await page.evaluate(()=>{window.__xrProbe.samples=null;window.__xrProbe.want=true;});
 await page.waitForFunction(()=>window.__xrProbe.samples||window.__xrProbe.errors.length,null,{timeout:10000}).catch(()=>{});
 return page.evaluate(()=>window.__xrProbe.samples);}
/* XR frames delivered to our probe vs page renders (xrInspection().renderCount; null when the page's inspection throws). */
const counts=page=>page.evaluate(()=>{let r=null;try{r=xrInspection().renderCount;}catch(e){}return {p:window.__xrProbe.frames,r};});
async function framesAdvance(page,ms=600){const a=await counts(page);await page.waitForTimeout(ms);const b=await counts(page);
 return {probeFrames:b.p-a.p,pageRenders:a.r==null||b.r==null?null:b.r-a.r};}
(async()=>{
 let server=null,base=process.env.VIEWER_BASE_URL;
 if(!base){const port=await freePort();server=spawn('python3',['-m','http.server',String(port),'--bind','127.0.0.1'],{cwd:ROOT,stdio:'ignore'});base='http://127.0.0.1:'+port;
  for(let i=0;i<50;i++){try{await fetch(base+'/scan-xr.html');break;}catch{await new Promise(r=>setTimeout(r,100));}}}
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--enable-webgl','--ignore-gpu-blocklist','--use-angle=metal']});
 const report={rev:(REV||'working tree')+(CORE_REV?' + twin/xr-core.js@'+CORE_REV:''),iwer:path.basename(IWER)};let failed=null;
 try{
  const page=await browser.newPage({viewport:{width:1280,height:800}}),errors=[];
  page.on('pageerror',e=>errors.push('pageerror: '+e.message));page.on('console',m=>{if(m.type()==='error'&&!/Failed to load resource/.test(m.text()))errors.push('console: '+m.text());});
  page.on('response',r=>{if(r.status()>=400&&!/favicon/.test(r.url()))(report.httpErrors||=[]).push(r.status()+' '+new URL(r.url()).pathname);});   // unpublished captures 404 by design; recorded, not fatal
  await page.addInitScript({content:fs.readFileSync(IWER,'utf8')+'\n'+INIT});
  const now=new Date().toISOString().slice(0,19);
  await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({meters:{76:{latest:{kw:120.5,t:now}},77:{latest:{kw:40.2,t:now}},3:{latest:{kw:12,t:now}}}})}));
  // XR_SMOKE_CORE_REV: serve ONLY twin/xr-core.js from that revision = a browser holding a stale cached core script next to a new page
  // (GitHub Pages sends max-age=600 for every file). The page must still render the photo in XR and report the problem.
  const routes=REV?['scan-xr.html','twin/xr-core.js','twin/mr-align.js','twin/overlay-visibility.js'].map(f=>[f,REV]):[];if(CORE_REV)routes.push(['twin/xr-core.js',CORE_REV]);
  for(const [f,rev] of routes){let body;try{body=fromRev(f,rev);}catch{continue;}
   await page.route(u=>new URL(u).pathname.endsWith('/'+f),r=>r.fulfill({contentType:f.endsWith('.html')?'text/html':'text/javascript',body}));}
  const layersQ=process.env.XR_SMOKE_LAYERS==='default'?'':'layers='+(process.env.XR_SMOKE_LAYERS||'equipment');
  // inspection that survives a broken page (a stale core makes some inspection fields throw on the unfixed page)
  const insp=()=>page.evaluate(()=>{try{return xrInspection();}catch(e){return {inspectionError:String(e&&e.message||e)};}});
  const presenting=()=>page.evaluate(()=>!!window.__xrProbe.session&&!window.__xrProbe.ended);
  await page.goto(base+'/scan-xr.html?'+layersQ);
  await page.waitForFunction(()=>{try{return xrInspection().ready;}catch(e){return performance.now()>20000;}},null,{timeout:60000,polling:250});
  await page.waitForFunction(()=>{try{const l=Object.values(xrInspection().layers);return l.length>0&&l.every(x=>x.loaded||x.error);}catch(e){return true;}},null,{timeout:240000,polling:500});
  const pre=await insp();report.preXR={supported:pre.xr?.supported,coreInSync:pre.xr?.coreInSync,texture:pre.texture,photoSphereVisible:pre.photoSphereVisible,inspectionError:pre.inspectionError,
   enterVRVisible:await page.locator('#enterVR').isVisible(),xrNote:await page.locator('#xrNote').textContent()};
  if(!CORE_REV){assert.equal(pre.xr.supported,true,'IWER exposes immersive-vr');assert.equal(report.preXR.enterVRVisible,true,'Enter VR offered');}
  // a stale core must not offer Enter VR; the test still forces the session to prove the loop keeps drawing the photo
  if(CORE_REV)await page.evaluate(()=>document.getElementById('enterVR').click());else await page.click('#enterVR');
  await page.waitForFunction(()=>!!window.__xrProbe.session,null,{timeout:15000});await page.evaluate(()=>window.__xrProbe.session.addEventListener('end',()=>{window.__xrProbe.ended=true;}));
  report.session={mode:await page.evaluate(()=>window.__xrProbe.mode),init:await page.evaluate(()=>window.__xrProbe.init)};
  await page.waitForTimeout(800);   // pendingPlace (3 frames), controller 'connected' events, first input frames
  const check=async(label,{allowErrors=false}={})=>{const adv=await framesAdvance(page),s=await sample(page),i=await insp();
   const r={label,...adv,samples:s,photoSphereVisible:i.photoSphereVisible,presenting:await presenting(),frameErrors:i.xr?.frameErrors,lastFrameError:i.xr?.lastFrameError,rig:i.rig,camera:i.camera?.world,inspectionError:i.inspectionError,errors:errors.slice()};report[label]=r;
   await page.screenshot({path:path.join(OUT,'immersive-'+label+'.png')});
   assert.ok(s&&s.litFraction>.5,label+': XR view not black (lit fraction '+(s?s.litFraction.toFixed(2):'n/a')+', mean rgb '+(s?s.mean.join(','):'n/a')+')');
   assert.ok(adv.pageRenders==null||adv.pageRenders>3,label+': the page XR loop keeps rendering ('+adv.pageRenders+' renders in 600 ms) - an exception in setAnimationLoop stops it');
   assert.ok(adv.probeFrames>3,label+': XR frames are delivered ('+adv.probeFrames+')');
   assert.equal(r.presenting,true,label+': still presenting');
   assert.equal(r.photoSphereVisible,true,label+': photo sphere visible');
   if(!allowErrors){assert.deepEqual(errors,[],label+': no page errors in XR');if(r.frameErrors!==undefined)assert.equal(r.frameErrors,0,label+': no caught XR frame errors ('+r.lastFrameError+')');}
   return r;};
  if(CORE_REV){
   await check('stale-core',{allowErrors:true});
   assert.ok(!errors.some(e=>e.startsWith('pageerror')),'stale core: no uncaught exceptions');
   assert.equal(report.preXR.enterVRVisible,false,'stale core: Enter VR is not offered');assert.match(report.preXR.xrNote,/reload/i,'stale core: the page asks for a reload');
   console.log('PASS scan-xr immersive smoke, stale twin/xr-core.js ('+report.rev+')');
  }else{
  await check('enter');
  // Right trigger (info card path), left stick forward hold (point-and-go aim preview), pull back (cancel), B/Y menu (Y on the left controller).
  await page.evaluate(()=>{const r=__iwer.controllers.right;r.updateButtonValue('trigger',1);});await page.waitForTimeout(150);await page.evaluate(()=>__iwer.controllers.right.updateButtonValue('trigger',0));
  await page.evaluate(()=>__iwer.controllers.left.updateAxes('thumbstick',0,-1));await page.waitForTimeout(300);
  await check('aiming');
  await page.evaluate(()=>__iwer.controllers.left.updateAxes('thumbstick',0,.8));await page.waitForTimeout(150);await page.evaluate(()=>__iwer.controllers.left.updateAxes('thumbstick',0,0));
  await page.evaluate(()=>__iwer.controllers.left.updateButtonValue('y-button',1));await page.waitForTimeout(120);await page.evaluate(()=>__iwer.controllers.left.updateButtonValue('y-button',0));
  await page.waitForTimeout(200);
  await check('menu');report.menuOpen=(await insp()).menu?.open??null;
  // Quest hand tracking (controllers put down): hand input sources replace the controllers
  await page.evaluate(()=>{__iwer.primaryInputMode='hand';});await page.waitForTimeout(500);
  await check('hands');
  await page.evaluate(()=>{__iwer.primaryInputMode='controller';});await page.waitForTimeout(300);
  await page.evaluate(()=>window.__xrProbe.session.end());await page.waitForFunction(()=>{try{return !xrInspection().xr.presenting;}catch(e){return true;}},null,{timeout:10000});
  assert.deepEqual(errors,[],'no page errors after exit');
  console.log('PASS scan-xr immersive smoke ('+report.rev+')');}
 }catch(e){failed=e;}
 finally{fs.writeFileSync(path.join(OUT,'scan-xr-immersive.json'),JSON.stringify(report,null,1));console.log(JSON.stringify(report,null,1));await browser.close();if(server)server.kill();}
 if(failed){console.error('FAIL',failed.message);process.exitCode=1;}
})().catch(e=>{console.error(e);process.exitCode=1;});
