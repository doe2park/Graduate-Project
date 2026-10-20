/* Headless walk Level 1 -> atrium stairs -> Level 2 -> Level 3 in the local Oct 18 multi-floor preview
   (scan-compare.html?capture=2026-10-18&floors=all). Uses the real keyboard navigation of the photo pane: the camera is
   turned toward the next station of a fixed route, then ArrowUp (walk forward) or PageUp (stairs) is pressed.
   Needs the local package capture-local/grimes-oct18-floors (scripts/multifloor_review.py package) and a running
   python3 -m http.server at the repo root.
   PLAYWRIGHT_MODULE=/path/to/playwright-core node tests/multifloor-walk-smoke.cjs
   Env: VIEWER_BASE_URL (default http://127.0.0.1:8790), CHROME_EXECUTABLE, VALIDATION_OUTPUT (default work/web-matrix/floors).
   Screenshots are visual evidence of navigation and floor following, not survey accuracy. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const ROOT=path.join(__dirname,'..'),OUT=process.env.VALIDATION_OUTPUT||path.join(ROOT,'work','web-matrix','floors'),BASE=process.env.VIEWER_BASE_URL||'http://127.0.0.1:8790';
const MAN=path.join(ROOT,'capture-local/grimes-oct18-floors/panoramas/manifest.json');
if(!fs.existsSync(MAN)){console.log('SKIP: local multi-floor package not built');process.exit(0);}
fs.mkdirSync(OUT,{recursive:true});
const m=JSON.parse(fs.readFileSync(MAN,'utf8')),ix=id=>m.stations.findIndex(s=>s.id===id);
/* route: Level 1 atrium -> stair foot (812) -> stair (809) -> Level 2 (805, 802) -> stair (799, 795) -> Level 3 (792, 788) */
const ROUTE=(process.env.ROUTE||'pano_107294634,pano_107294812,pano_107294809,pano_107294805,pano_107294802,pano_107294799,pano_107294795,pano_107294792,pano_107294788').split(',');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--enable-webgl','--ignore-gpu-blocklist','--use-angle=metal']});
 const report={base:BASE,route:ROUTE,steps:[]},errors=[];
 try{
  const page=await browser.newPage({viewport:{width:1280,height:800}});page.setDefaultTimeout(120000);page.on('pageerror',e=>errors.push(e.message));
  const now=new Date().toISOString().slice(0,19).replace('T',' ');
  await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({json:{meters:{76:{latest:{kw:120.5,t:now}},77:{latest:{kw:40.2,t:now}},3:{latest:{kw:12,t:now}}}}}));
  await page.route('**/raw.githubusercontent.com/**/campus_energy_history.json',r=>r.fulfill({json:{grimes:[]}}));
  const view=process.env.VIEW||'both';
  await page.goto(BASE+'/scan-compare.html?capture=2026-10-18&floors=all'+(view==='overlay'?'&view=overlay&style=plain&opacity=60':''));
  const scan=()=>page.frames().find(f=>/scan-photo\.html/.test(f.url())),bim=()=>page.frames().find(f=>f.url().includes('pane=bim'));
  await page.waitForFunction(()=>typeof registration!=='undefined'&&registration&&scanReady);
  await scan().waitForFunction(()=>window.photoInspection&&photoInspection().count>100&&!photoInspection().loading);
  const settle=async()=>{await scan().waitForFunction(()=>!photoInspection().loading&&!photoInspection().transitioning);await page.waitForTimeout(view==='overlay'?2500:1500);};
  const state=()=>page.evaluate(()=>{const f=[...document.querySelectorAll('iframe')],p=f[0].contentWindow.photoInspection(),b=f[1].contentWindow.scanInspection().camera;
   return{active:p.active,id:p.station.id,level:p.station.level||null,label:f[0].contentWindow.document.getElementById('loading').textContent,
    bimCamera:b.position.map(v=>+v.toFixed(2)),bimFloorFilter:f[1].contentWindow.document.getElementById('elementFloor').value,bimHeader:document.querySelector('section[aria-label="BIM model"] h2 span').textContent,
    note:document.getElementById('floorsNote')?.textContent||null,toggle:document.getElementById('floorsToggle')?.textContent||null}});
  /* start at the first route station via the photo pane's own station picker */
  await scan().selectOption('#station',String(ix(ROUTE[0])));await settle();
  if(view==='overlay'){await bim().waitForFunction(()=>{const l=scanInspection().layerStats;return ['equipment','lighting','duct'].every(x=>l[x]?.loaded);},null,{timeout:240000,polling:500});await page.waitForTimeout(1000);}
  const shot=async(k,s)=>{await page.screenshot({path:path.join(OUT,`${view}-${String(k).padStart(2,'0')}-${s.level||'na'}-${s.id.slice(-3)}.png`)});};
  let s=await state();report.steps.push({how:'start',...s});await shot(0,s);
  for(let k=1;k<ROUTE.length;k++){
   const target=ix(ROUTE[k]),cur=m.stations[s.active],dst=m.stations[target];assert.ok(target>=0,ROUTE[k]);
   const dx=dst.position[0]-cur.position[0],dz=dst.position[2]-cur.position[2],rise=dst.position[1]-cur.position[1],yaw=Math.atan2(-dx,-dz);
   const stair=(cur.stairs||[]).includes(target);
   /* look toward the next station (as a user would), slightly up or down on stairs */
   const pitch=stair?Math.sign(rise)*0.25:0,cy=Math.cos(yaw/2),sy=Math.sin(yaw/2),cp=Math.cos(pitch/2),sp=Math.sin(pitch/2);
   await page.evaluate(q=>send('scan',{type:'grimes-linked-pose',epoch,pose:{position:poses.scan?.position||[0,0,0],quaternion:q,fov:65,zoom:1}}),[sp*cy,sy*cp,-sp*sy,cy*cp]);
   await page.waitForTimeout(300);
   const key=stair?(rise>0?'PageUp':'PageDown'):'ArrowUp';
   await page.locator('iframe').first().focus();await scan().locator('canvas').focus().catch(()=>{});
   await scan().evaluate(k=>{window.dispatchEvent(new KeyboardEvent('keydown',{code:k,key:k}));setTimeout(()=>window.dispatchEvent(new KeyboardEvent('keyup',{code:k,key:k})),300);},key);
   await scan().waitForFunction(t=>photoInspection().active===t||photoInspection().transitioning,target,{timeout:8000}).catch(()=>{});
   await settle();s=await state();report.steps.push({how:key,expected:ROUTE[k],ok:s.id===ROUTE[k],...s});await shot(k,s);
   if(s.id!==ROUTE[k])break;
  }
  report.errors=errors;
 }finally{fs.writeFileSync(path.join(OUT,(process.env.VIEW||'both')+'-walk-report.json'),JSON.stringify(report,null,1));await browser.close();}
 for(const st of report.steps)console.log(st.how.padEnd(8),st.id,st.level,'bim',st.bimCamera,'floor',st.bimFloorFilter,st.ok===false?'MISSED':'');
 const missed=report.steps.filter(x=>x.ok===false);assert.equal(missed.length,0,'route step missed');assert.equal(errors.length,0,errors.join('\n'));
 console.log('PASS multi-floor walk',report.steps.length,'stations');process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
