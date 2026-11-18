/* Decode and ray-pick restored L2 ducts. QA level override only, not a photo/field alignment claim. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawn,execFileSync}=require('node:child_process'),net=require('node:net'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const ROOT=path.join(__dirname,'..'),OUT=process.env.VALIDATION_OUTPUT||'/tmp/grimes-mobile-quality';
(async()=>{fs.mkdirSync(OUT,{recursive:true});const port=await new Promise(r=>{const s=net.createServer();s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>r(p));});});
 const server=spawn('python3',['-m','http.server',String(port),'--bind','127.0.0.1'],{cwd:ROOT,stdio:'ignore'}),base='http://127.0.0.1:'+port;
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--mute-audio','--enable-webgl','--ignore-gpu-blocklist','--use-angle=metal']});
 try{for(let i=0;i<50;i++){try{await fetch(base);break;}catch{await new Promise(r=>setTimeout(r,100));}}
 const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:2}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{Object.defineProperty(window,'speechSynthesis',{value:{speak(){},cancel(){},getVoices:()=>[]}});});
 await page.route('**/raw.githubusercontent.com/**/building_data.json',r=>r.fulfill({contentType:'application/json',body:'{"meters":{}}'}));
 const baseline=process.env.BASELINE==='1';if(baseline){const body=execFileSync('git',['show','85172a58d:scan-xr.html'],{cwd:ROOT});await page.route('**/scan-xr.html?*',r=>r.fulfill({contentType:'text/html',body}));}
 await page.goto(base+'/scan-xr.html?layers=duct&levels=L2&radius=60&hires=0');
 await page.waitForFunction(()=>{const i=window.xrInspection?.();return i?.ready&&!i.transitioning&&Object.keys(i.layers).length===1&&Object.values(i.layers).every(x=>x.loaded&&!x.loading&&!x.error);},null,{timeout:240000});
 const state=await page.evaluate(()=>xrInspection());assert.deepEqual(state.levels,['L2']);assert.equal(state.layers.duct.elements,2810,'recovered L2 identities after documented quality exclusions');assert.ok(state.layers.duct.renderTriangles>0);assert.equal(state.layers.duct.unidentifiedObjects||0,0);
 const old=JSON.parse(fs.readFileSync(path.join(ROOT,'buildings/grimes/duct.elements.json'))).elements,newMeta=JSON.parse(fs.readFileSync(path.join(ROOT,'buildings/grimes/duct-restored.elements.json'))).elements;
 const ids=Object.keys(newMeta).filter(id=>!old[id]);const target=await page.evaluate(()=>{xrDebug.setStyle('all');const camera=xrDebug.surfaces().camera;let root=camera;while(root.parent)root=root.parent;const out=[],at=xrInspection().station.positionBim;
 root.traverse(m=>{if(m.userData.layer!=='duct'||!m.userData.ranges||m.userData.isLine)return;const g=m.geometry,p=g.attributes.position;for(const r of m.userData.ranges){if(r.count<3)continue;const ii=[0,1,2].map(j=>g.index.getX(r.start+j)),point=['getX','getY','getZ'].map(k=>ii.reduce((s,i)=>s+p[k](i),0)/3);out.push({id:r.id,point,d:Math.hypot(...point.map((v,i)=>v-at[i]))});}});return out.sort((a,b)=>a.d-b.d).slice(0,80);});assert.ok(target.length,'decoded recovered L2 triangle targets');
 let picked=null;for(const e of target){await page.evaluate(p=>xrDebug.lookAtBim(p),e.point);const hit=await page.evaluate(()=>xrDebug.pickNdc(0,0));if(hit?.id&&ids.includes(hit.id)){picked=hit;break;}}
 assert.ok(picked,'ray pick resolves an authentic recovered L2 ID');const report={level:state.levels,elements:state.layers.duct.elements,triangles:state.layers.duct.renderTriangles,pickedId:picked.id,pickedLayer:picked.layer,sourceLevel:newMeta[picked.id].levelKey};
 assert.equal(report.pickedLayer,'duct');assert.match(String(newMeta[picked.id].level||report.sourceLevel),/2/);
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(OUT,'duct-report.json'),JSON.stringify(report,null,2));console.log('PASS recovered L2 duct decode + identity ray pick',report);
 }finally{await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
