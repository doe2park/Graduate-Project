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

test('Gaussian is enabled only from the public May manifest and never for Sep 17',()=>{
 const splat=fs.readFileSync(path.join(__dirname,'../scan-splat.html'),'utf8');
 assert.match(src,/GAUSSIAN_MANIFEST='scan-assets\/gaussian\/2026-05-06\/viewer\.json'/);
 assert.doesNotMatch(src+splat,/capture-local\/gaussian/);
 assert.match(splat,/get\('manifest'\)\|\|'scan-assets\/gaussian\/2026-05-06\/viewer\.json'/);
 assert.doesNotMatch(splat,/train the local pilot/);
 const m=src.match(/\/\* CAPTURE SELECTION \*\/([\s\S]*?)\/\* END CAPTURE SELECTION \*\//)[1],c={URLSearchParams};vm.createContext(c);vm.runInContext(m,c);
 assert.equal(c.captureSelection('?mode=splat&capture=2026-09-17').date,'2026-05-06');
 assert.equal(c.captureSelection('').date,'2026-09-17');
 assert.match(src,/value="splat" disabled/);
 assert.match(logic().splatSource('scan-assets/gaussian/2026-05-06/viewer.json'),/^scan-splat\.html\?manifest=scan-assets%2Fgaussian%2F2026-05-06%2Fviewer\.json/)});

/* ── Overlay styles: lens / ghost / plain (AR X-ray vision) ── */
test('?style= selects lens (default) / ghost / plain and rejects anything else',()=>{const c=logic();
 assert.equal(c.OVERLAY_DEFAULT_STYLE,'lens');assert.equal(c.parseStyle(''),'lens');
 for(const s of ['lens','ghost','plain'])assert.equal(c.parseStyle('?view=overlay&style='+s),s);
 for(const bad of ['?style=GHOST','?style=','?style=xray','?style=javascript:1'])assert.equal(c.parseStyle(bad),'lens')});
test('lens radius is 22% of the shorter side, centre follows a clamped pointer or stays centred',()=>{const c=logic();
 assert.equal(c.LENS_RADIUS_FRACTION,.22);assert.equal(c.lensRadius(1600,900),198);assert.ok(Math.abs(c.lensRadius(390,844)-85.8)<1e-9);assert.equal(c.lensRadius(0,0),0);
 assert.deepEqual({...c.lensCenter(null,1600,900)},{x:800,y:450});assert.deepEqual({...c.lensCenter({x:NaN,y:.5},1600,900)},{x:800,y:450});
 assert.deepEqual({...c.lensCenter({x:.25,y:.5},1600,900)},{x:400,y:450});assert.deepEqual({...c.lensCenter({x:-3,y:9},1600,900)},{x:0,y:900})});
test('lens opacities: ~85% inside, ~8% outside',()=>{const c=logic();assert.equal(c.LENS_INSIDE,.85);assert.equal(c.LENS_OUTSIDE,.08);
 const m=c.lensMask(100,50,80);assert.match(m,/radial-gradient\(circle 80px at 100px 50px/);assert.match(m,/rgba\(0,0,0,0\.85\)/);assert.match(m,/rgba\(0,0,0,0\.08\)/)});
test('GHOST edge layer is enabled only for 360° photos on wide, non-touch devices; otherwise falls back to plain',()=>{const c=logic();
 assert.equal(c.ghostAvailable({display:'photo',narrowOrTouch:false}),true);
 assert.equal(c.ghostAvailable({display:'photo',narrowOrTouch:true}),false);
 assert.equal(c.ghostAvailable({display:'mesh',narrowOrTouch:false}),false);assert.equal(c.ghostAvailable({display:'splat',narrowOrTouch:false}),false);
 assert.equal(c.effectiveStyle('ghost',{display:'photo',narrowOrTouch:true}),'plain');assert.equal(c.effectiveStyle('ghost',{display:'photo',narrowOrTouch:false}),'ghost');
 assert.equal(c.effectiveStyle('lens',{display:'mesh',narrowOrTouch:true}),'lens');assert.equal(c.effectiveStyle('plain',{display:'photo',narrowOrTouch:false}),'plain')});
test('compare page offers the Style picker (44px touch targets) and cites the X-ray techniques',()=>{
 for(const v of ['lens','ghost','plain'])assert.match(src,new RegExp('data-style="'+v+'"'));
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
