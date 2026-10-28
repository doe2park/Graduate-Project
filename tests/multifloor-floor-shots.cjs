/* Headless one-floor check of the local Oct 18 per-floor previews (scan-compare.html?capture=2026-10-18&floors=L2 / L3,
   2026-10-27). For each floor: the page opens the floor's own package, every station is on that floor (or its stairs),
   the photo label and the BIM floor filter follow, the Floor menu is offered, and a few stations are photographed
   looking up (ceiling/space views, people are below the horizon and blurred anyway).
   Needs capture-local/grimes-L{2,3}-2026-10-18-v2 (scripts/multifloor_review.py floors) and python3 -m http.server.
   PLAYWRIGHT_MODULE=/path/to/playwright-core node tests/multifloor-floor-shots.cjs
   Env: VIEWER_BASE_URL (default http://127.0.0.1:8790), CHROME_EXECUTABLE, VALIDATION_OUTPUT (default work/web-matrix/floors),
   FLOORS (default L2,L3), SHOTS (stations per floor, default 4), PITCH (radians, default 0.45 = looking up),
   VIEW (both = Compare, default; overlay = Plain overlay 60%). 2026-10-27: the BIM pane must also load that floor's
   interior (Compare: interiorInspection().loadedLevel) or that floor's walls as the Overlay occluder; overlay shots are
   floor-<L>-overlay-*.png. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const ROOT=path.join(__dirname,'..'),OUT=process.env.VALIDATION_OUTPUT||path.join(ROOT,'work','web-matrix','floors'),BASE=process.env.VIEWER_BASE_URL||'http://127.0.0.1:8790';
const FLOORS=(process.env.FLOORS||'L2,L3').split(','),SHOTS=+(process.env.SHOTS||4),PITCH=+(process.env.PITCH||0.45),VIEW=process.env.VIEW||'both';
/* 2026-10-27: CAPTURE=<date> checks a Cupix-free local capture (scripts/capture_upper_floors.py -> capture-local/grimes-<L>-<date>) */
const CAPTURE=process.env.CAPTURE||'2026-10-18',PKG=CAPTURE==='2026-10-18'?'-v2':'',TAG=CAPTURE==='2026-10-18'?'':'-'+CAPTURE;
(async()=>{
 fs.mkdirSync(OUT,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--enable-webgl','--ignore-gpu-blocklist','--use-angle=metal']});
 const report={base:BASE,floors:{}},errors=[];let ran=0;
 try{
  for(const floor of FLOORS){
   const man=path.join(ROOT,`capture-local/grimes-${floor}-${CAPTURE}${PKG}/panoramas/manifest.json`);
   if(!fs.existsSync(man)){console.log('SKIP',floor,'package not built');continue;}
   const m=JSON.parse(fs.readFileSync(man,'utf8'));ran++;
   const page=await browser.newPage({viewport:{width:1280,height:800}});page.setDefaultTimeout(120000);page.on('pageerror',e=>errors.push(floor+': '+e.message));
   const now=new Date().toISOString().slice(0,19).replace('T',' ');
   await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({json:{meters:{76:{latest:{kw:120.5,t:now}},77:{latest:{kw:40.2,t:now}},3:{latest:{kw:12,t:now}}}}}));
   await page.route('**/raw.githubusercontent.com/**/campus_energy_history.json',r=>r.fulfill({json:{grimes:[]}}));
   await page.goto(BASE+'/scan-compare.html?capture='+CAPTURE+'&floors='+floor+(VIEW==='overlay'?'&view=overlay&style=plain&opacity=60':''));
   const scan=()=>page.frames().find(f=>/scan-photo\.html/.test(f.url())),bim=()=>page.frames().find(f=>f.url().includes('pane=bim'));
   await page.waitForFunction(()=>typeof registration!=='undefined'&&registration&&scanReady);
   await scan().waitForFunction(n=>window.photoInspection&&photoInspection().count===n&&!photoInspection().loading,m.stations.length);
   const settle=async()=>{await scan().waitForFunction(()=>!photoInspection().loading&&!photoInspection().transitioning);await page.waitForTimeout(1800);};
   const state=()=>page.evaluate(()=>{const f=[...document.querySelectorAll('iframe')],p=f[0].contentWindow.photoInspection();
    return{active:p.active,id:p.station.id,level:p.station.level||null,count:p.count,label:f[0].contentWindow.document.getElementById('loading').textContent,
     bimFloorFilter:f[1].contentWindow.document.getElementById('elementFloor').value,note:document.getElementById('floorsNote')?.textContent||null,
     jump:[...(document.getElementById('floorsJump')?.options||[])].map(o=>o.value)}});
   await settle();
   /* the BIM pane swaps to this floor's interior (Compare) or this floor's walls as occluder (Overlay) */
   const interior=VIEW==='overlay'
    ?(await bim().waitForFunction(f=>{const o=overlayVisibilityInspection().occluder;return o.level===f&&o.state==='ready'&&o;},floor,{timeout:240000})).jsonValue()
    :(await bim().waitForFunction(f=>{const i=interiorInspection();return i.ready&&i.loadedLevel===f&&i;},floor,{timeout:240000})).jsonValue();
   const interiorState=await interior;
   if(VIEW==='overlay'){assert.equal(interiorState.source,`interior/enclosure-${floor.toLowerCase()}.glb (Walls)`);assert.ok(interiorState.elements>0);}
   else{assert.equal(interiorState.level,floor);assert.equal(Object.keys(interiorState.groups).length,4);
    const status=await bim().evaluate(()=>document.getElementById('interiorStatus').textContent);assert.match(status,/not surveyed as-built/);interiorState.status=status;}
   const first=await state();assert.equal(first.id,m.defaultStation,'opens on the default station');assert.match(first.note||'',new RegExp(floor.replace('L','Level ')+' only'));
   /* spread SHOTS stations over the largest walk group (ordered by frame), never stairs */
   const group=m.walkGroups[0].map(id=>m.stations.findIndex(s=>s.id===id)).filter(i=>m.stations[i].level===floor);
   const picks=[...new Set(Array.from({length:SHOTS},(_,k)=>group[Math.round(k*(group.length-1)/Math.max(1,SHOTS-1))]))];
   const steps=[];
   for(const [k,i] of picks.entries()){
    await scan().selectOption('#station',String(i));await settle();
    /* look up at the ceiling, heading along the walk */
    const nb=m.stations[i].neighbors[0],dx=nb!=null?m.stations[nb].position[0]-m.stations[i].position[0]:0,dz=nb!=null?m.stations[nb].position[2]-m.stations[i].position[2]:-1;
    const yaw=Math.atan2(-dx,-dz),cy=Math.cos(yaw/2),sy=Math.sin(yaw/2),cp=Math.cos(PITCH/2),sp=Math.sin(PITCH/2);
    await page.evaluate(q=>send('scan',{type:'grimes-linked-pose',epoch,pose:{position:poses.scan?.position||[0,0,0],quaternion:q,fov:70,zoom:1}}),[sp*cy,sy*cp,-sp*sy,cy*cp]);
    await page.waitForTimeout(1500);
    const s=await state();steps.push(s);
    assert.equal(s.id,m.stations[i].id);assert.equal(s.count,m.stations.length);assert.equal(s.level,floor);assert.equal(s.bimFloorFilter,floor,'BIM floor filter follows');
    await page.screenshot({path:path.join(OUT,`floor-${floor}${TAG}-${VIEW==='overlay'?'overlay-':''}${String(k).padStart(2,'0')}-${s.id.slice(-7)}.png`)});
   }
   report.floors[floor]={stations:m.stations.length,default:m.defaultStation,view:VIEW,interior:interiorState,first,steps};
   await page.close();
  }
  report.errors=errors;
 }finally{fs.writeFileSync(path.join(OUT,VIEW==='overlay'?'floor-shots-overlay-report.json':'floor-shots-report.json'),JSON.stringify(report,null,1));await browser.close();}
 for(const [f,r] of Object.entries(report.floors))console.log(f,r.stations,'stations; shots',r.steps.map(s=>s.id+' '+s.level+' bim '+s.bimFloorFilter).join(' | '));
 assert.equal(errors.length,0,errors.join('\n'));console.log(ran?'PASS one-floor previews':'SKIP: no per-floor package');process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
