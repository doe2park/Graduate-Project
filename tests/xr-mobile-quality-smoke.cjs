/* Ready-state touch preview, not a claim of iPhone WebXR support. */
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
 await page.goto(base+'/scan-xr.html?layers=equipment,duct,plumbing&hires=0');
 await page.waitForFunction(()=>{const i=window.xrInspection?.();return i?.ready&&!i.transitioning&&Object.keys(i.layers).length===3&&Object.values(i.layers).every(x=>x.loaded&&!x.loading&&!x.error);},null,{timeout:240000});
 const target=await page.evaluate(()=>{const a=xrDebug.elementsNearStation(400);return a.find(e=>e.layer==='duct')||a[0];});assert.ok(target,'visible loaded BIM target');
 await page.evaluate(p=>{xrDebug.lookAtBim(p);xrDebug.setStyle('all');xrDebug.renderNow();},target.point);await page.waitForTimeout(200);
 await page.screenshot({path:path.join(OUT,baseline?'mobile-before.png':'mobile-controls.png')});
 const report={baseline,target,loaded:await page.evaluate(()=>xrInspection().layers),viewport:{width:390,height:844}};
 if(!baseline){assert.equal(await page.locator('#entryToggle').count(),1,'a phone user can reveal the model by collapsing controls');
 await page.locator('#moreOpts > summary').tap();for(const id of ['prev','next','styleAll','styleLens']){const b=await page.locator('#'+id).boundingBox();assert.ok(b.height>=44,id+' touch target '+b.height);}
 await page.locator('#entryToggle').tap();assert.equal(await page.locator('#entryToggle').getAttribute('aria-expanded'),'false');assert.equal(await page.locator('#moreOpts').isVisible(),false);
 await page.screenshot({path:path.join(OUT,'mobile-after.png')});
 await page.locator('#entryToggle').tap();assert.equal(await page.locator('#entryToggle').getAttribute('aria-expanded'),'true');assert.equal(await page.locator('#moreOpts').isVisible(),true);
 await page.locator('#styleLens').tap();assert.equal((await page.evaluate(()=>xrInspection())).style,'lens');await page.locator('#styleAll').tap();assert.equal((await page.evaluate(()=>xrInspection())).style,'all');
 await page.locator('#entryToggle').tap();await page.setViewportSize({width:844,height:390});await page.waitForTimeout(200);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal overflow after orientation change');
 await page.screenshot({path:path.join(OUT,'mobile-landscape.png')});
 await page.locator('#entryToggle').tap();assert.equal(await page.locator('#entryToggle').getAttribute('aria-expanded'),'true');}
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(OUT,'mobile-report.json'),JSON.stringify(report,null,2));console.log('PASS ready-state mobile preview '+(baseline?'baseline':'touch controls, collapse/restore, orientation'));
 }finally{await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
