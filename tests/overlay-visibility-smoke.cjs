/* Overlay realistic-visibility headless check: the same viewpoints rendered as Plain overlay (60%) in Photo and Gaussian,
   so screenshots before/after the distance fade + wall occlusion change can be compared side by side.
     PLAYWRIGHT_MODULE=/path/to/playwright-core TAG=after node tests/overlay-visibility-smoke.cjs
   Env: TAG (file prefix, default 'after'), RANGE (adds ?range=, e.g. all/near/room; omitted = page default),
        STYLE (plain|lens, default plain), ONLY (comma list of shot names), VIEWER_BASE_URL (default http://127.0.0.1:8790,
        a python3 -m http.server at the repo root), CHROME_EXECUTABLE, VALIDATION_OUTPUT (default work/web-matrix/visibility).
   Viewpoints are Oct 18 photo stations in the shared BIM frame (?at=); Gaussian uses May 6 (whole L1) for corridor/lobby and the
   Oct 18 zone for the auditorium. The L3 view needs the local multi-floor package (floors=all, localhost only) and has no Gaussian.
   Headless desktop only: no frame-rate, phone or Quest claim. Screenshots are visual evidence, not survey accuracy. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path');
const ROOT=path.join(__dirname,'..'),OUT=process.env.VALIDATION_OUTPUT||path.join(ROOT,'work','web-matrix','visibility'),BASE=process.env.VIEWER_BASE_URL||'http://127.0.0.1:8790';
const TAG=process.env.TAG||'after',RANGE=process.env.RANGE||'',STYLE=process.env.STYLE||'plain';
fs.mkdirSync(OUT,{recursive:true});
const reg=JSON.parse(fs.readFileSync(path.join(ROOT,'scan-assets/captures/2026-10-18/registration.json'),'utf8'));
const l1=JSON.parse(fs.readFileSync(path.join(ROOT,'scan-assets/captures/2026-10-18/panoramas/manifest.json'),'utf8')).stations;
const FLOORS=path.join(ROOT,'capture-local/grimes-oct18-floors/panoramas/manifest.json');
const up=fs.existsSync(FLOORS)?JSON.parse(fs.readFileSync(FLOORS,'utf8')).stations:[];
const station=id=>l1.find(s=>s.id===id)||up.find(s=>s.id===id);
/* scan-frame position + (yaw, pitch) in degrees -> BIM-frame ?at= (same convention as scan-compare-matrix-smoke) */
function at(id,yawDeg,pitchDeg){const s=station(id);if(!s)return null;
 const y=yawDeg*Math.PI/180,p=pitchDeg*Math.PI/180,qy=[0,Math.sin(y/2),0,Math.cos(y/2)],qp=[Math.sin(p/2),0,0,Math.cos(p/2)];
 const q=[qy[3]*qp[0]+qy[0]*qp[3]+qy[1]*qp[2]-qy[2]*qp[1],qy[3]*qp[1]-qy[0]*qp[2]+qy[1]*qp[3]+qy[2]*qp[0],qy[3]*qp[2]+qy[0]*qp[1]-qy[1]*qp[0]+qy[2]*qp[3],qy[3]*qp[3]-qy[0]*qp[0]-qy[1]*qp[1]-qy[2]*qp[2]];
 const a=reg.rotationYDegrees*Math.PI/180,c=Math.cos(a),sn=Math.sin(a),t=reg.translation,[x,yy,z]=s.position,h=Math.sin(a/2),w=Math.cos(a/2),[qx,qyy,qz,qw]=q;
 const pos=[c*x+sn*z+t[0],yy+t[1],-sn*x+c*z+t[2]],qq=[w*qx+h*qz,w*qyy+h*qw,w*qz-h*qx,w*qw-h*qyy];
 return[...pos.map(v=>v.toFixed(3)),...qq.map(v=>v.toFixed(4)),'75.0'].join(',');}
const VIEWS=[
 {name:'l1-corridor',id:'pano_107294621',yaw:+(process.env.YAW_CORRIDOR||90),pitch:12,photo:'capture=2026-10-18',splat:'capture=2026-05-06&mode=splat'},
 {name:'l1-lobby',id:'pano_107294634',yaw:+(process.env.YAW_LOBBY||0),pitch:15,photo:'capture=2026-10-18',splat:'capture=2026-05-06&mode=splat'},
 {name:'l1-auditorium',id:'pano_107294555',yaw:+(process.env.YAW_AUDITORIUM||0),pitch:15,photo:'capture=2026-10-18',splat:'capture=2026-10-18&mode=splat'},
 {name:'l3-oct18-floors',id:'pano_107294788',yaw:+(process.env.YAW_L3||0),pitch:12,photo:'capture=2026-10-18&floors=all',splat:null},
];
const ONLY=(process.env.ONLY||'').split(',').filter(Boolean);
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--enable-webgl','--ignore-gpu-blocklist','--use-angle=metal']});
 const report={tag:TAG,range:RANGE||'(default)',style:STYLE,shots:[]},errors=[];
 try{
  const page=await browser.newPage({viewport:{width:1280,height:800}});page.setDefaultTimeout(180000);page.on('pageerror',e=>errors.push(e.message));
  const now=new Date().toISOString().slice(0,19).replace('T',' ');
  await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({json:{meters:{76:{latest:{kw:120.5,t:now}},77:{latest:{kw:40.2,t:now}},3:{latest:{kw:12,t:now}}}}}));
  await page.route('**/raw.githubusercontent.com/**/campus_energy_history.json',r=>r.fulfill({json:{grimes:[]}}));
  const scanFrame=()=>page.frames().find(f=>/scan-(photo|splat)\.html/.test(f.url()));
  const bimFrame=()=>page.frames().find(f=>f.url().includes('pane=bim'));
  for(const v of VIEWS)for(const display of ['photo','splat']){
   const name=v.name+'-'+display;if(ONLY.length&&!ONLY.includes(name))continue;
   const q=display==='photo'?v.photo:v.splat,a=at(v.id,v.yaw,v.pitch);
   if(!q||!a){report.shots.push({name,skipped:!q?'no Gaussian for this view':'local station package missing'});continue;}
   const url=BASE+'/scan-compare.html?'+q+'&view=overlay&style='+STYLE+'&opacity=60'+(RANGE?'&range='+RANGE:'')+'&at='+a;
   await page.goto(url,{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>typeof registration!=='undefined'&&registration&&scanReady);
   if(display==='splat')await scanFrame().waitForFunction(()=>window.splatInspection?.().state==='ready',null,{timeout:240000});
   else await scanFrame().waitForFunction(()=>window.photoInspection&&!photoInspection().loading&&!photoInspection().transitioning);
   await bimFrame().waitForFunction(()=>{if(!window.scanInspection)return false;const l=scanInspection().layerStats;return ['equipment','lighting','conduit','duct','hydronic','plumbing','lifesafety'].every(x=>l[x]?.loaded);},null,{timeout:300000,polling:500});
   await bimFrame().waitForFunction(()=>!window.overlayVisibilityInspection||overlayVisibilityInspection().occluder.state!=='loading',null,{timeout:120000,polling:500});
   await page.waitForTimeout(2500);
   const file=TAG+'-'+name+'.png';await page.screenshot({path:path.join(OUT,file)});
   const info=await bimFrame().evaluate(()=>({camera:scanInspection().camera.position.map(x=>+x.toFixed(2)),visibility:window.overlayVisibilityInspection?overlayVisibilityInspection():null}));
   report.shots.push({name,file,url:url.replace(BASE,''),...info});console.log(JSON.stringify({name,file,visibility:info.visibility&&{range:info.visibility.range,occluder:info.visibility.occluder}}));
  }
  report.errors=errors.filter(e=>!/ResizeObserver/.test(e));
 }finally{fs.writeFileSync(path.join(OUT,TAG+'-report.json'),JSON.stringify(report,null,1));await browser.close();}
 process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
