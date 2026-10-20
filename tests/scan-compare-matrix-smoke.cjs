/* scan-compare.html desktop matrix smoke: capture date x scan mode x Compare/Overlay (Lens / Plain; Ghost removed 2026-10-19).
   One headless Chrome, ONE chained walk through the real UI so the ?at= viewpoint carry is exercised too:
     May photo -> (mode) May Gaussian -> (date) Sep 17 [no Gaussian: photo + note] -> (date) Oct 18 Gaussian zones -> (mode) Oct 18 photo
   PLAYWRIGHT_MODULE=/path/to/playwright(-core) node tests/scan-compare-matrix-smoke.cjs
   Optional: VIEWER_BASE_URL (default http://127.0.0.1:8790, an already-running python3 -m http.server at the repo root),
   CHROME_EXECUTABLE, VALIDATION_OUTPUT (default work/web-matrix/). Meter feeds are route fixtures.
   Headless desktop only: no frame-rate, phone or Quest claim. Screenshots are visual evidence, not survey accuracy. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const ROOT=path.join(__dirname,'..'),OUT=process.env.VALIDATION_OUTPUT||path.join(ROOT,'work','web-matrix'),BASE=process.env.VIEWER_BASE_URL||'http://127.0.0.1:8790';
fs.mkdirSync(OUT,{recursive:true});
const SERVICE=['equipment','lighting','conduit','duct','hydronic','plumbing','lifesafety'];
/* start viewpoint: Oct 18 station pano_107294555 (inside trained zone l1-a), looking 15 degrees up, in the shared BIM frame */
function toBim(reg,pos,q){const a=reg.rotationYDegrees*Math.PI/180,c=Math.cos(a),s=Math.sin(a),t=reg.translation,[x,y,z]=pos;
 const h=Math.sin(a/2),w=Math.cos(a/2),[qx,qy,qz,qw]=q;return{position:[c*x+s*z+t[0],y+t[1],-s*x+c*z+t[2]],quaternion:[w*qx+h*qz,w*qy+h*qw,w*qz-h*qx,w*qw-h*qy]};}
const octReg=JSON.parse(fs.readFileSync(path.join(ROOT,'scan-assets/captures/2026-10-18/registration.json'),'utf8'));
const octSt=JSON.parse(fs.readFileSync(path.join(ROOT,'scan-assets/captures/2026-10-18/panoramas/manifest.json'),'utf8')).stations.find(s=>s.id==='pano_107294555');
const pitch=15*Math.PI/180,start=toBim(octReg,octSt.position,[Math.sin(pitch/2),0,0,Math.cos(pitch/2)]);
const AT=[...start.position.map(v=>v.toFixed(3)),...start.quaternion.map(v=>v.toFixed(4)),'65.0'].join(',');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--enable-webgl','--ignore-gpu-blocklist','--use-angle=metal']});
 const report={base:BASE,at:AT,steps:[]},errors=[];
 try{
  const page=await browser.newPage({viewport:{width:1280,height:800}});page.setDefaultTimeout(120000);
  page.on('pageerror',e=>errors.push(e.message));
  const now=new Date().toISOString().slice(0,19).replace('T',' ');
  await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({json:{meters:{76:{latest:{kw:120.5,t:now}},77:{latest:{kw:40.2,t:now}},3:{latest:{kw:12,t:now}}}}}));
  await page.route('**/raw.githubusercontent.com/**/campus_energy_history.json',r=>r.fulfill({json:{grimes:[]}}));
  const scanFrame=()=>page.frames().find(f=>/scan-(photo|splat)\.html/.test(f.url())&&!f.url().includes('edges=1'));
  const bimFrame=()=>page.frames().find(f=>f.url().includes('pane=bim'));
  async function ready(display){
   await page.waitForFunction(d=>document.getElementById('scanMode').value===d&&typeof registration!=='undefined'&&registration&&scanReady,display);
   if(display==='splat')await scanFrame().waitForFunction(()=>window.splatInspection?.().state==='ready',null,{timeout:180000});
   else await scanFrame().waitForFunction(()=>window.photoInspection&&!photoInspection().loading&&!photoInspection().transitioning);
   await page.waitForTimeout(1200);
  }
  async function overlayLoaded(){await bimFrame().waitForFunction(k=>{const l=scanInspection().layerStats;return k.every(x=>l[x]?.loaded);},SERVICE,{timeout:240000,polling:500});await page.waitForTimeout(800);}
  async function poseCheck(){
   /* the BIM camera must sit on the registered transform of the scan camera (same mechanism for photo and Gaussian) */
   return page.evaluate(async()=>{const f=[...document.querySelectorAll('iframe')];const scanWin=f[0].contentWindow,bimWin=f[1].contentWindow;
    const sc=scanWin.splatInspection?scanWin.splatInspection().camera:poses.scan,bc=bimWin.scanInspection().camera;if(!sc||!bc)return null;
    const exp=convert({...sc,zoom:1},'scan');const dp=Math.hypot(...exp.position.map((v,k)=>v-bc.position[k]));
    const dq=Math.abs(exp.quaternion.reduce((s,v,k)=>s+v*bc.quaternion[k],0));
    return{scanPosition:sc.position.map(v=>+v.toFixed(3)),bimPosition:bc.position.map(v=>+v.toFixed(3)),positionErrorM:+dp.toFixed(5),rotationErrorDeg:+(2*Math.acos(Math.min(1,dq))*180/Math.PI).toFixed(4),fovScan:sc.fov,fovBim:bc.fov};});
  }
  const ui=()=>page.evaluate(()=>{const o=document.querySelector('#scanMode [value=splat]');return{date:capture.date,display:document.getElementById('scanMode').value,splatOption:{disabled:o.disabled,text:o.textContent,title:o.title},status:document.getElementById('linkStatus').textContent,style:document.body.dataset.style,styleNote:document.getElementById('styleNote').textContent,ghostButton:!!document.querySelector('#styleBar [data-style=ghost]'),view:document.body.dataset.focus,xray:getComputedStyle(document.documentElement).getPropertyValue('--xray').trim(),lensXray:getComputedStyle(document.documentElement).getPropertyValue('--lens-xray').trim(),lensMask:!!document.documentElement.style.getPropertyValue('--lens-mask'),edgeFrame:!!document.querySelector('#edgeLayer iframe')};});
  const shot=name=>page.screenshot({path:path.join(OUT,name+'.png')});
  async function matrix(tag,display){
   const step={tag,display};await ready(display);
   await page.click('#paneViews [data-focus=both]');await page.waitForTimeout(600);step.compare=await ui();step.comparePose=await poseCheck();await shot(tag+'-compare');
   await page.click('#paneViews [data-focus=overlay]');await overlayLoaded();
   await page.click('#styleBar [data-style=lens]');
   /* Lens info card: move the lens over a few points until the BIM pane reports an element under its centre */
   for(const [x,y] of [[640,560],[640,420],[400,330],[880,330],[900,520],[640,300]]){await page.mouse.move(x,y,{steps:4});
    if(await page.waitForFunction(()=>document.getElementById('lensCard').classList.contains('show'),null,{timeout:1600}).then(()=>true,()=>false)){step.lensAt=[x,y];break;}}
   step.lens=await ui();
   step.lensCard=await page.evaluate(()=>({shown:document.getElementById('lensCard').classList.contains('show'),text:document.getElementById('lensCard').textContent.slice(0,160)}));
   step.overlayPose=await poseCheck();await shot(tag+'-overlay-lens');
   await page.click('#styleBar [data-style=plain]');await page.locator('#xrayOpacity').fill('60');await page.waitForTimeout(500);step.plain=await ui();await shot(tag+'-overlay-plain');
   /* old ?style=ghost links load Plain */
   await page.evaluate(()=>setStyle('ghost'));await page.waitForTimeout(300);step.ghost=await ui();
   await page.click('#styleBar [data-style=lens]');
   report.steps.push(step);console.log(JSON.stringify({tag,display:step.lens.display,date:step.lens.date,status:step.lens.status,pose:step.overlayPose,ghost:step.ghost.style,note:step.ghost.styleNote}));
   return step;
  }
  const nav=async fn=>{await Promise.all([page.waitForNavigation({waitUntil:'domcontentloaded'}),fn()]);};
  /* 1. May photo, entered with the Oct station viewpoint */
  await page.goto(BASE+'/scan-compare.html?capture=2026-05-06&at='+AT,{waitUntil:'domcontentloaded'});
  const may=await matrix('may-photo','photo');
  assert.equal(may.compare.date,'2026-05-06');assert.equal(may.compare.splatOption.disabled,false);assert.match(may.lens.status,/registered \(internal residual ≈0\.13 m, not surveyed\)/);
  assert.equal(may.ghost.style,'plain');assert.equal(may.ghost.ghostButton,false);assert.equal(may.plain.xray,'0.6');assert.equal(may.lens.lensMask,true);
  /* 2. mode -> Gaussian keeps May and the viewpoint */
  await nav(()=>page.selectOption('#scanMode','splat'));
  const maySplat=await matrix('may-splat','splat');
  assert.equal(maySplat.compare.date,'2026-05-06');assert.match(maySplat.lens.status,/Gaussian · experimental appearance, not surveyed/);assert.match(maySplat.lens.status,/registered/);
  assert.equal(maySplat.ghost.style,'plain');assert.equal(maySplat.ghost.styleNote,'');
  report.carryMayPhotoToSplatM=Math.hypot(...maySplat.comparePose.scanPosition.map((v,k)=>v-may.comparePose.scanPosition[k]));
  /* 3. date -> Sep 17 (no Gaussian): photos with an honest note, option disabled */
  await nav(()=>page.selectOption('#captureDate','2026-09-17'));
  const sep=await matrix('sep-photo-from-splat','photo');
  assert.equal(sep.compare.date,'2026-09-17');assert.equal(sep.compare.splatOption.disabled,true);assert.match(sep.compare.splatOption.text,/no Gaussian for this capture/);
  assert.match(sep.lens.status,/No Gaussian for Sep 17 · showing 360° photos/);assert.match(sep.lens.status,/provisional alignment/);assert.equal(sep.ghost.style,'plain');
  /* 4. date -> Oct 18: the Gaussian request comes back, as the Oct 18 zone scene */
  await nav(()=>page.selectOption('#captureDate','2026-10-18'));
  const octSplat=await matrix('oct-splat','splat');
  const zone=await scanFrame().evaluate(()=>splatInspection().zone);report.octZone=zone;assert.equal(zone.id,'l1-a');
  assert.match(scanFrame().url(),/zones=scan-assets%2Fgaussian%2F2026-10-18%2Fzones%2Findex\.json/);
  assert.match(octSplat.lens.status,/Oct 18 (only Zone A trained|\d+ zones trained: Zone A[^·]*) · other areas have no Gaussian/);assert.match(octSplat.lens.status,/provisional alignment/);
  assert.equal(octSplat.ghost.style,'plain');
  /* 5. mode -> photo keeps Oct 18 and the viewpoint (nearest recorded station) */
  await nav(()=>page.selectOption('#scanMode','photo'));
  const octPhoto=await matrix('oct-photo','photo');
  assert.equal(octPhoto.compare.date,'2026-10-18');assert.equal(octPhoto.compare.splatOption.disabled,false);assert.equal(octPhoto.ghost.style,'plain');
  const station=await scanFrame().evaluate(()=>photoInspection().station.id);report.octPhotoStation=station;
  report.carryOctSplatToPhotoM=Math.hypot(...octPhoto.comparePose.scanPosition.map((v,k)=>v-octSplat.comparePose.scanPosition[k]));
  /* 7. mode -> Gaussian again: the Oct 18 Gaussian at exactly the Oct 18 photo station (same-viewpoint alignment evidence) */
  await nav(()=>page.selectOption('#scanMode','splat'));
  const octSplat2=await matrix('oct-splat-at-photo-station','splat');
  report.carryOctPhotoToSplatM=Math.hypot(...octSplat2.comparePose.scanPosition.map((v,k)=>v-octPhoto.comparePose.scanPosition[k]));
  assert.ok(report.carryOctPhotoToSplatM<.05,'Oct photo -> Gaussian keeps the station position');
  /* 6. old link: ?mode=splat with no capture -> May Gaussian */
  await page.goto(BASE+'/scan-compare.html?mode=splat',{waitUntil:'domcontentloaded'});await ready('splat');
  report.oldLink=await ui();assert.equal(report.oldLink.date,'2026-05-06');assert.equal(report.oldLink.display,'splat');
  for(const s of report.steps){assert.ok(s.lensCard.shown,s.tag+': Lens info card appears over a BIM element');assert.ok(s.lens.lensMask,s.tag+': lens mask applied');assert.equal(s.plain.xray,'0.6',s.tag+': opacity slider drives Plain');}
  for(const s of report.steps)for(const p of [s.comparePose,s.overlayPose]){assert.ok(p,'pose available '+s.tag);assert.ok(p.positionErrorM<.01,s.tag+' BIM position follows scan '+p.positionErrorM);assert.ok(p.rotationErrorDeg<.2,s.tag+' BIM rotation follows scan '+p.rotationErrorDeg);}
  assert.ok(report.carryMayPhotoToSplatM<.05,'photo -> Gaussian keeps the station position');
  report.errors=errors.filter(e=>!/ResizeObserver/.test(e));assert.deepEqual(report.errors,[]);
  console.log('PASS scan-compare matrix');
 }finally{report.errors=report.errors||errors;fs.writeFileSync(path.join(OUT,'matrix-report.json'),JSON.stringify(report,null,1));await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
