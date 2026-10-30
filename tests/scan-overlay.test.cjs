/* Logic for the scan/BIM "X-ray overlay" view and compact view switcher.
   Pure functions are extracted from scan-compare.html between markers (no browser needed). */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../scan-compare.html'),'utf8');
const bim=fs.readFileSync(path.join(__dirname,'../scan-bim.html'),'utf8');
const photo=fs.readFileSync(path.join(__dirname,'../scan-photo.html'),'utf8');
function logic(){const m=src.match(/\/\* OVERLAY LOGIC \*\/([\s\S]*?)\/\* END OVERLAY LOGIC \*\//);assert.ok(m,'overlay logic block exists');const c={URLSearchParams,Number,Math};vm.createContext(c);vm.runInContext(m[1]+';this.OVERLAY_DEFAULT_OPACITY=OVERLAY_DEFAULT_OPACITY;this.OVERLAY_LAYERS=OVERLAY_LAYERS;this.OVERLAY_DEFAULT_STYLE=OVERLAY_DEFAULT_STYLE;this.LENS_RADIUS_FRACTION=LENS_RADIUS_FRACTION;this.LENS_INSIDE=LENS_INSIDE;this.LENS_OUTSIDE=LENS_OUTSIDE;',c);return c}
test('view parameter selects compare / overlay / scan / bim and rejects anything else',()=>{const c=logic();
 assert.equal(c.parseView(''),'compare');assert.equal(c.parseView('?view=overlay'),'overlay');assert.equal(c.parseView('?view=scan'),'scan');assert.equal(c.parseView('?view=bim'),'bim');
 assert.equal(c.parseView('?view=compare'),'compare');assert.equal(c.parseView('?view=OVERLAY'),'compare');assert.equal(c.parseView('?view=javascript:1'),'compare');assert.equal(c.parseView('?view='),'compare')});
test('overlay opacity defaults to 30% and is clamped to 0..1',()=>{const c=logic();
 assert.equal(c.OVERLAY_DEFAULT_OPACITY,.30);assert.equal(c.clampOpacity(undefined),.30);assert.equal(c.clampOpacity('abc'),.30);assert.equal(c.clampOpacity(null),.30);
 assert.equal(c.clampOpacity(-3),0);assert.equal(c.clampOpacity(7),1);assert.equal(c.clampOpacity('0.8'),.8);assert.equal(c.clampOpacity(0),0);assert.equal(c.clampOpacity(Infinity),.30)});
test('?opacity= (percent) seeds the slider within bounds',()=>{const c=logic();
 assert.equal(c.parseOpacity(''),.30);assert.equal(c.parseOpacity('?opacity=70'),.7);assert.equal(c.parseOpacity('?opacity=250'),1);assert.equal(c.parseOpacity('?opacity=-5'),0);assert.equal(c.parseOpacity('?opacity=x'),.30)});
test('overlay label stays honest about alignment status',()=>{const c=logic();
 assert.equal(c.overlayLabel({provisional:true}),'Overlay · provisional alignment');
 assert.equal(c.overlayLabel({provisional:false}),'Overlay · registered (internal residual ≈0.13 m, not surveyed)');
 assert.doesNotMatch(c.overlayLabel({provisional:true}),/registered|surveyed|verified/i)});
test('overlay shows only MEP/service layers, never architecture or structure',()=>{const c=logic();
 const layers=[...c.OVERLAY_LAYERS];for(const k of ['duct','hydronic','plumbing','conduit','lighting','equipment','lifesafety','fire'])assert.ok(layers.includes(k),k);
 for(const k of ['structural','furniture','enclosure','floors','ceilings'])assert.ok(!layers.includes(k),k)});
test('header offers Compare / Overlay / Scan / BIM on every width',()=>{
 for(const v of ['both','overlay','scan','bim'])assert.match(src,new RegExp('data-focus="'+v+'"'));
 assert.doesNotMatch(src,/#paneViews\{display:none\}/)});
test('BIM pane implements transparent overlay without loading architecture',()=>{
 assert.match(bim,/grimes-overlay/);assert.match(bim,/alpha:\s*true/);assert.match(bim,/setClearColor\(0,\s*0\)/);
 assert.match(bim,/OVERLAY_LAYER_KEYS/)});
test('scan-bim overlay layer list matches the compare page list',()=>{
 const a=src.match(/OVERLAY_LAYERS\s*=\s*(\[[^\]]*\])/)[1],b=bim.match(/OVERLAY_LAYER_KEYS\s*=\s*(\[[^\]]*\])/)[1];
 assert.deepEqual(JSON.parse(a.replace(/'/g,'"')),JSON.parse(b.replace(/'/g,'"')))});
test('compact toolbars keep aria labels, keyboard ids and a single ⋯ menu per pane',()=>{
 for(const [name,s] of [['photo',photo],['bim',bim]]){assert.match(s,/aria-haspopup.{1,4}menu/,name);assert.match(s,/⋯|&#8943;|\\u22EF/,name)}
 for(const id of ['previous','next','station','photoWalk'])assert.match(photo,new RegExp('id="'+id+'"'));
 assert.match(photo,/aria-label="Previous captured position"/);assert.match(photo,/aria-label="Next captured position"/);assert.match(photo,/aria-label="Captured position"/);
 for(const id of ['scanObjects','bimNavigate','showAllLayersQuick','fitBimQuick','electricalFocus','interiorServices'])assert.match(bim,new RegExp('id="'+id+'"'));
 assert.doesNotMatch(photo,/Drag to look · WASD \/ arrows: walk along capture route · Transitions blend recorded photos<\/div>\s*<script/)});
test('shared toolbar sizing is the same in both panes (32px desktop, 44px touch)',()=>{
 for(const s of [photo,bim]){assert.match(s,/--tb-h:32px/);assert.match(s,/--tb-h:44px/);assert.match(s,/--tb-radius:8px/)}});
test('Building Shell is not reintroduced',()=>{assert.doesNotMatch(src+photo,/Building Shell/)});

test('Gaussian is enabled only from each capture\'s own public manifest/zone index and never for Sep 17',()=>{
 const splat=fs.readFileSync(path.join(__dirname,'../scan-splat.html'),'utf8');
 assert.match(src,/'2026-05-06':\{kind:'manifest',path:'scan-assets\/gaussian\/2026-05-06\/viewer\.json'\}/);
 assert.match(src,/'2026-10-18':\{kind:'zones',path:'scan-assets\/gaussian\/2026-10-18\/zones\/index\.json'\}/);
 assert.doesNotMatch(src+splat,/capture-local\/gaussian/);
 assert.match(splat,/get\('manifest'\)\|\|'scan-assets\/gaussian\/2026-05-06\/viewer\.json'/);
 assert.doesNotMatch(splat,/train the local pilot/);
 const m=src.match(/\/\* CAPTURE SELECTION \*\/([\s\S]*?)\/\* END CAPTURE SELECTION \*\//)[1],c={URLSearchParams};vm.createContext(c);vm.runInContext(m,c);
 const sep=c.captureSelection('?mode=splat&capture=2026-09-17');assert.equal(sep.date,'2026-09-17');assert.equal(sep.gaussian,null);assert.equal(sep.display,'photo');
 assert.equal(c.captureSelection('').date,'2026-09-17');
 assert.match(src,/value="splat" disabled/);
 assert.match(logic().splatSource('scan-assets/gaussian/2026-05-06/viewer.json'),/^scan-splat\.html\?manifest=scan-assets%2Fgaussian%2F2026-05-06%2Fviewer\.json/)});

/* ── Overlay styles: lens / plain; Ghost removed 2026-10-19 (AR X-ray vision) ── */
test('?style= selects lens (default) / plain, maps old ghost links to plain, and rejects anything else',()=>{const c=logic();
 assert.equal(c.OVERLAY_DEFAULT_STYLE,'lens');assert.equal(c.parseStyle(''),'lens');
 for(const s of ['lens','plain'])assert.equal(c.parseStyle('?view=overlay&style='+s),s);
 assert.equal(c.parseStyle('?view=overlay&style=ghost'),'plain');assert.match(src,/OVERLAY_STYLES=\['lens','plain'\]/);
 for(const bad of ['?style=GHOST','?style=','?style=xray','?style=javascript:1'])assert.equal(c.parseStyle(bad),'lens')});
test('lens radius is 22% of the shorter side, centre follows a clamped pointer or stays centred',()=>{const c=logic();
 assert.equal(c.LENS_RADIUS_FRACTION,.22);assert.equal(c.lensRadius(1600,900),198);assert.ok(Math.abs(c.lensRadius(390,844)-85.8)<1e-9);assert.equal(c.lensRadius(0,0),0);
 assert.deepEqual({...c.lensCenter(null,1600,900)},{x:800,y:450});assert.deepEqual({...c.lensCenter({x:NaN,y:.5},1600,900)},{x:800,y:450});
 assert.deepEqual({...c.lensCenter({x:.25,y:.5},1600,900)},{x:400,y:450});assert.deepEqual({...c.lensCenter({x:-3,y:9},1600,900)},{x:0,y:900})});
test('touch lens drag: centre is clamped to margins and the usable band; invalid drags return null',()=>{const c=logic();
 assert.equal(c.lensDragCenter(null,390,700,56,520),null);assert.equal(c.lensDragCenter({x:NaN,y:10},390,700,56,520),null);
 assert.deepEqual({...c.lensDragCenter({x:200,y:300},390,700,56,520)},{x:200,y:300});
 assert.deepEqual({...c.lensDragCenter({x:-50,y:300},390,700,56,520)},{x:24,y:300});
 assert.deepEqual({...c.lensDragCenter({x:5000,y:300},390,700,56,520)},{x:366,y:300});
 assert.deepEqual({...c.lensDragCenter({x:200,y:-100},390,700,56,520)},{x:200,y:66});
 assert.deepEqual({...c.lensDragCenter({x:200,y:5000},390,700,56,520)},{x:200,y:510});
 const tiny=c.lensDragCenter({x:0,y:0},30,700,56,520);assert.equal(tiny.x,15);
 const squeezed=c.lensDragCenter({x:200,y:0},390,700,600,520);assert.ok(squeezed.y>=0&&Number.isFinite(squeezed.y))});
test('touch lens drag: a ⠿ handle exists on the ring, 44px+ touch target, pointer events on the handle only',()=>{
 assert.match(src,/id="lensHandle"/);
 assert.match(src,/#lensHandle\{[^}]*min-width:44px/);
 assert.match(src,/#lensHandle\{[^}]*pointer-events:auto/);
 assert.match(src,/#lensHandle\{[^}]*touch-action:none/);
 assert.match(src,/@media\(pointer:coarse\)\{body\[data-focus="overlay"\]\[data-style="lens"\] #lensHandle\{display:block\}/);
 assert.match(src,/lensHandle\.setPointerCapture/);
 assert.match(src,/#lensRing\{[^}]*pointer-events:none/)});
test('lens opacities: ~85% inside, ~8% outside',()=>{const c=logic();assert.equal(c.LENS_INSIDE,.85);assert.equal(c.LENS_OUTSIDE,.08);
 const m=c.lensMask(100,50,80);assert.match(m,/radial-gradient\(circle 80px at 100px 50px/);assert.match(m,/rgba\(0,0,0,0\.85\)/);assert.match(m,/rgba\(0,0,0,0\.08\)/)});
test('Ghost style is removed: no ghost API, button, edge layer or iframe in scan-compare',()=>{const c=logic();
 assert.equal(c.ghostAvailable,undefined);assert.doesNotMatch(src,/data-style="ghost"|id="edgeLayer"|edges=1|edgeFrame/);
 assert.equal(c.effectiveStyle('lens',{display:'mesh',narrowOrTouch:true}),'lens');assert.equal(c.effectiveStyle('plain',{display:'photo',narrowOrTouch:false}),'plain')});
test('compare page offers the Style picker (44px touch targets) and cites the X-ray techniques',()=>{
 for(const v of ['lens','plain'])assert.match(src,new RegExp('data-style="'+v+'"'));
 assert.match(src,/Schall et al\. 2009/);assert.match(src,/Kalkofen et al\. 2007/);assert.match(src,/Zollmann et al\. 2014/);
 assert.match(src,/#styleBar button\{flex:1;min-height:44px/)});
test('scan panes post normalised pointer coordinates; photo pane has an edges-only mode',()=>{
 const splat=fs.readFileSync(path.join(__dirname,'../scan-splat.html'),'utf8');
 for(const s of [photo,splat,bim])assert.match(s,/grimes-pointer/);
 assert.match(photo,/edges'\)==='1'/);assert.match(photo,/Sobel/);assert.match(photo,/grimes-photo-station/)});
test('honest alignment labels are unchanged',()=>{assert.match(src,/internal residual \\u22480\.13 m, not surveyed/);assert.match(src,/provisional alignment/)});

test('opacity slider drives the lens too (no fixed opacity:1, no greyed label)',()=>{
 assert.match(src,/data-style="lens"\] section\[aria-label="BIM model"\] iframe\{opacity:var\(--lens-xray,1\)\}/);
 assert.doesNotMatch(src,/label\[for="xrayOpacity"\]\{opacity:\.45\}/);
 assert.match(src,/function syncXray\(\)/);assert.match(src,/layoutLens\(true\);syncXray\(\);/);
});

/* ── Overlay × Gaussian (2026-10-19): every style works or says why not ── */
test('splat source: May uses its manifest, Oct 18 uses its zone index with the capture date',()=>{const c=logic();
 assert.match(c.splatSource({kind:'manifest',path:'scan-assets/gaussian/2026-05-06/viewer.json'}),/^scan-splat\.html\?manifest=scan-assets%2Fgaussian%2F2026-05-06%2Fviewer\.json&revision=/);
 const z=c.splatSource({kind:'zones',path:'scan-assets/gaussian/2026-10-18/zones/index.json'},'2026-10-18');
 assert.match(z,/^scan-splat\.html\?zones=scan-assets%2Fgaussian%2F2026-10-18%2Fzones%2Findex\.json&capture=2026-10-18&revision=/);assert.doesNotMatch(z,/manifest=/)});
test('Lens and Plain stay available on the Gaussian; ghost maps to plain',()=>{const c=logic();
 const env={display:'splat',narrowOrTouch:false};assert.equal(c.effectiveStyle('lens',env),'lens');assert.equal(c.effectiveStyle('plain',env),'plain');assert.equal(c.parseStyle('?style=ghost'),'plain');
 assert.doesNotMatch(src,/not available on the Gaussian/)});
test('Gaussian overlay status keeps the experimental label and the capture alignment label',()=>{
 assert.match(src,/Gaussian \\u00b7 experimental appearance, not surveyed/);assert.match(src,/function scanNoteText\(\)/);
 assert.match(src,/No Gaussian for '\+CAPTURE_SHORT\[capture\.date\]/);assert.match(src,/const n=typeof scanNoteText==='function'\?scanNoteText\(\):''/)});
test('a requested Gaussian loads only after validation, so the carried viewpoint reaches the Gaussian pane',()=>{
 assert.match(src,/if\(capture\.display!=='splat'\)frames\[0\]\.src=photoSource/);
 assert.match(src,/function startSplat\(\)\{mode\.value='splat';photoMode=false;scanReady=false;/);
 assert.match(src,/send\('scan',\{type:photoMode\?'grimes-photo-goto':'grimes-start-pose'/)});

test('ui=min parses only the exact value and the default page is unchanged without it',()=>{const c=logic();
 assert.equal(c.parseUiMin(''),false);assert.equal(c.parseUiMin('?view=overlay'),false);assert.equal(c.parseUiMin('?ui=full'),false);assert.equal(c.parseUiMin('?ui=MIN'),false);
 assert.equal(c.parseUiMin('?ui=min'),true);assert.equal(c.parseUiMin('?view=overlay&capture=2026-05-06&style=lens&sensors=demo&ui=min&at=1,2,3'),true);
 assert.equal(c.parseView('?view=overlay&ui=min'),'overlay');
 /* wiring: class only added when the param is present; touch-only collapse path kept; demo-sensor notice never hidden by ui-min rules */
 assert.match(src,/if\(uiMin\)document\.body\.classList\.add\('ui-min'\)/);
 assert.match(src,/else if\(touchMq\.matches\)apply\(saved===null\?view==='overlay':saved==='1'\)/);
 assert.match(src,/btn\.hidden=!\(touchMq\.matches\|\|uiMin\)/);
 const rules=src.match(/body\.ui-min[^{]*\{[^}]*\}/g).join('\n');assert.doesNotMatch(rules,/sensor|badge/i);
 assert.match(src,/body\.ctl-min header p,body\.ctl-min \.rights-link/)});
