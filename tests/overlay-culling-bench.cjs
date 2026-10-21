/* Overlay distance-culling bench (2026-10-20): per viewpoint x Range (near / room / all) it records what the BIM pane
   submits (meshes, instances, element ranges), renderer.info draw calls and triangles (wall pre-pass + scene), a
   synchronous frame time over a scripted walk-around (camera circles 1.5 m around the station while turning 360 deg;
   every frame = wall pre-pass + scene + 1-pixel readPixels, so the GPU has finished: continuous rendering, no vsync),
   and a PNG of the BIM canvas at the station pose (for pixel diffs against another TAG).
     PLAYWRIGHT_MODULE=/path/to/playwright-core TAG=after node tests/overlay-culling-bench.cjs
   Env: TAG (default 'after'), CULL (on|off; 'off' calls overlayCulling(false) if the page has it), AB=1 (same session:
   culling off/on/off/on per view x range, frame times pooled per mode; PNGs <TAG>-off-* and <TAG>-on-*), MOBILE=1 (390x844,
   DPR 3, touch; Room only unless RANGES is set), RANGES (comma list), ONLY (comma list of view names), FRAMES (default 120),
   VIEWER_BASE_URL (default http://127.0.0.1:8790), CHROME_EXECUTABLE, VALIDATION_OUTPUT (default work/web-matrix/culling).
   Headless Chrome on this Mac (ANGLE Metal): numbers are relative evidence for this machine only, not a phone/Quest claim. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path');
const ROOT=path.join(__dirname,'..'),OUT=process.env.VALIDATION_OUTPUT||path.join(ROOT,'work','web-matrix','culling'),BASE=process.env.VIEWER_BASE_URL||'http://127.0.0.1:8790';
const TAG=process.env.TAG||'after',CULL=process.env.CULL||'on',AB=process.env.AB==='1',MOBILE=process.env.MOBILE==='1',FRAMES=+(process.env.FRAMES||120);
const RANGES=(process.env.RANGES||(MOBILE?'room':'near,room,all')).split(',').filter(Boolean),ONLY=(process.env.ONLY||'').split(',').filter(Boolean);
fs.mkdirSync(OUT,{recursive:true});
const reg=JSON.parse(fs.readFileSync(path.join(ROOT,'scan-assets/captures/2026-10-18/registration.json'),'utf8'));
const l1=JSON.parse(fs.readFileSync(path.join(ROOT,'scan-assets/captures/2026-10-18/panoramas/manifest.json'),'utf8')).stations;
const FLOORS=path.join(ROOT,'capture-local/grimes-oct18-floors/panoramas/manifest.json');
const up=fs.existsSync(FLOORS)?JSON.parse(fs.readFileSync(FLOORS,'utf8')).stations:[];
const station=id=>l1.find(s=>s.id===id)||up.find(s=>s.id===id);
/* same ?at= convention as tests/overlay-visibility-smoke.cjs */
function at(id,yawDeg,pitchDeg){const s=station(id);if(!s)return null;
 const y=yawDeg*Math.PI/180,p=pitchDeg*Math.PI/180,qy=[0,Math.sin(y/2),0,Math.cos(y/2)],qp=[Math.sin(p/2),0,0,Math.cos(p/2)];
 const q=[qy[3]*qp[0]+qy[0]*qp[3]+qy[1]*qp[2]-qy[2]*qp[1],qy[3]*qp[1]-qy[0]*qp[2]+qy[1]*qp[3]+qy[2]*qp[0],qy[3]*qp[2]+qy[0]*qp[1]-qy[1]*qp[0]+qy[2]*qp[3],qy[3]*qp[3]-qy[0]*qp[0]-qy[1]*qp[1]-qy[2]*qp[2]];
 const a=reg.rotationYDegrees*Math.PI/180,c=Math.cos(a),sn=Math.sin(a),t=reg.translation,[x,yy,z]=s.position,h=Math.sin(a/2),w=Math.cos(a/2),[qx,qyy,qz,qw]=q;
 const pos=[c*x+sn*z+t[0],yy+t[1],-sn*x+c*z+t[2]],qq=[w*qx+h*qz,w*qyy+h*qw,w*qz-h*qx,w*qw-h*qyy];
 return[...pos.map(v=>v.toFixed(3)),...qq.map(v=>v.toFixed(4)),'75.0'].join(',');}
const VIEWS=[
 {name:'l1-corridor',id:'pano_107294621',yaw:90,pitch:12,q:'capture=2026-10-18'},
 {name:'l1-lobby',id:'pano_107294634',yaw:0,pitch:15,q:'capture=2026-10-18'},
 {name:'l1-auditorium',id:'pano_107294555',yaw:0,pitch:15,q:'capture=2026-10-18'},
 {name:'l3-oct18-floors',id:'pano_107294788',yaw:0,pitch:12,q:'capture=2026-10-18&floors=all'},
];
const pct=(a,p)=>{const s=[...a].sort((x,y)=>x-y);return s[Math.min(s.length-1,Math.floor(p*(s.length-1)+.5))];};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--enable-webgl','--ignore-gpu-blocklist','--use-angle=metal']});
 const report={tag:TAG,cull:AB?'ab':CULL,mobile:MOBILE,frames:FRAMES,orbit:'1.5 m circle around the station, 360 deg turn',runs:[]},errors=[];
 try{
  const ctx=await browser.newContext(MOBILE?{viewport:{width:390,height:844},deviceScaleFactor:3,isMobile:true,hasTouch:true}:{viewport:{width:1280,height:800}});
  const page=await ctx.newPage();page.setDefaultTimeout(300000);page.on('pageerror',e=>errors.push(e.message));
  const now=new Date().toISOString().slice(0,19).replace('T',' ');
  await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({json:{meters:{76:{latest:{kw:120.5,t:now}}}}}));
  await page.route('**/raw.githubusercontent.com/**/campus_energy_history.json',r=>r.fulfill({json:{grimes:[]}}));
  const scanFrame=()=>page.frames().find(f=>/scan-(photo|splat)\.html/.test(f.url()));
  const bimFrame=()=>page.frames().find(f=>f.url().includes('pane=bim'));
  const layers=MOBILE?['equipment','lighting','conduit','duct','hydronic','plumbing','lifesafety']:['equipment','lighting','conduit','duct','hydronic','plumbing','lifesafety','fire'];
  for(const v of VIEWS){
   if(ONLY.length&&!ONLY.includes(v.name))continue;const a=at(v.id,v.yaw,v.pitch);
   if(!a){report.runs.push({view:v.name,skipped:'local station package missing'});continue;}
   const url=BASE+'/scan-compare.html?'+v.q+'&view=overlay&style=plain&opacity=60&range='+RANGES[0]+'&at='+a;
   await page.goto(url,{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>typeof registration!=='undefined'&&registration&&scanReady);
   await scanFrame().waitForFunction(()=>window.photoInspection&&!photoInspection().loading&&!photoInspection().transitioning);
   await bimFrame().waitForFunction(ls=>{if(!window.scanInspection||!window.overlayBench)return false;const l=scanInspection().layerStats;return ls.every(x=>l[x]?.loaded);},layers,{timeout:400000,polling:500});
   await page.waitForTimeout(1500);
   if(CULL==='off')await bimFrame().evaluate(()=>window.overlayCulling?.(false));
   for(const range of RANGES){
    await page.evaluate(r=>setRange(r),range);   // the Range bar's own handler (its buttons are folded away on phones)
    await bimFrame().waitForFunction(r=>{const o=window.overlayVisibilityInspection?.();return o&&o.range===r&&o.occluder.state!=='loading';},range,{timeout:120000,polling:250});
    await page.waitForTimeout(1200);
    const one=mode=>bimFrame().evaluate(({frames,mode})=>{
     if(mode)window.overlayCulling(mode==='on');
     const B=window.overlayBench,base=B.pose();B.frame(base);const still=B.frame(base,{png:true});
     const q0=base.quaternion,yaw=t=>[0,Math.sin(t/2),0,Math.cos(t/2)];
     const mul=(a,b)=>[a[3]*b[0]+a[0]*b[3]+a[1]*b[2]-a[2]*b[1],a[3]*b[1]-a[0]*b[2]+a[1]*b[3]+a[2]*b[0],a[3]*b[2]+a[0]*b[1]-a[1]*b[0]+a[2]*b[3],a[3]*b[3]-a[0]*b[0]-a[1]*b[1]-a[2]*b[2]];
     const pose=i=>{const t=2*Math.PI*i/frames;return{position:[base.position[0]+1.5*Math.cos(t)-1.5,base.position[1],base.position[2]+1.5*Math.sin(t)],quaternion:mul(yaw(t),q0),fov:base.fov};};
     for(let i=0;i<10;i++)B.frame(pose(i));
     const ms=[],calls=[],tris=[],meshes=[],inst=[];
     for(let i=0;i<frames;i++){const f=B.frame(pose(i));ms.push(f.ms);calls.push(f.calls);tris.push(f.triangles);meshes.push(f.meshes);inst.push(f.instances);}
     const cull=window.overlayCullInspection?.()||null;B.frame(base);
     return{base,still,ms,calls,tris,meshes,inst,vis:window.overlayVisibilityInspection(),cull};
    },{frames:FRAMES,mode});
    const mean=a=>a.reduce((x,y)=>x+y,0)/a.length;
    const summary=(r,file)=>({file,station:{meshes:r.still.meshes,instances:r.still.instances,elements:r.still.elements,calls:r.still.calls,triangles:r.still.triangles,lines:r.still.lines},
     orbit:{msMedian:+pct(r.ms,.5).toFixed(2),msP95:+pct(r.ms,.95).toFixed(2),callsMean:Math.round(mean(r.calls)),trianglesMean:Math.round(mean(r.tris)),meshesMean:Math.round(mean(r.meshes)),instancesMean:Math.round(mean(r.inst))},
     occluder:r.vis.occluder,cull:r.cull,ms:r.ms});
    if(AB){
     /* same session, same loaded data: culling off / on alternated twice; frame times pooled per mode */
     const modes={off:[],on:[]};
     for(const mode of ['off','on','off','on']){const r=await one(mode);modes[mode].push(r);}
     const out={view:v.name,range,ab:{}};
     for(const mode of ['off','on']){const rs=modes[mode],file=TAG+'-'+mode+'-'+v.name+'-'+range+'.png';fs.writeFileSync(path.join(OUT,file),Buffer.from(rs[0].still.png.split(',')[1],'base64'));
      const sm=summary(rs[0],file),all=rs.flatMap(r=>r.ms);sm.orbit.msMedian=+pct(all,.5).toFixed(2);sm.orbit.msP95=+pct(all,.95).toFixed(2);sm.orbit.frames=all.length;delete sm.ms;out.ab[mode]=sm;}
     await one('on');report.runs.push(out);console.log(JSON.stringify({view:v.name,range,off:out.ab.off.orbit,on:out.ab.on.orbit}));continue;
    }
    const r=await one(null),file=TAG+'-'+v.name+'-'+range+'.png';fs.writeFileSync(path.join(OUT,file),Buffer.from(r.still.png.split(',')[1],'base64'));
    const run={view:v.name,range,...summary(r,file)};delete run.ms;
    report.runs.push(run);console.log(JSON.stringify({view:v.name,range,station:run.station,orbit:run.orbit}));
   }
  }
  report.errors=errors.filter(e=>!/ResizeObserver/.test(e));
 }finally{fs.writeFileSync(path.join(OUT,'bench-'+TAG+'.json'),JSON.stringify(report,null,1));await browser.close();}
 process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
