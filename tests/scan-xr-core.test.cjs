/* scan-xr.html pure helpers (twin/xr-core.js): registration placement, photo orientation, flashlight cone,
   station navigation, XR input, menu hit-testing and info-card honesty. Real capture manifests and registrations;
   scan-photo.html / scan-compare.html functions are extracted from the pages so the XR page cannot drift from them. */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const {pathToFileURL} = require('node:url');
const X = require('../twin/xr-core.js'), RC = require('../registration-core.js'), EC = require('../twin/element-cards.js');
const root = path.join(__dirname, '..'), read = f => fs.readFileSync(path.join(root, f), 'utf8'), json = f => JSON.parse(read(f));
const near = (a, b, eps = 1e-9) => a.forEach((v, k) => assert.ok(Math.abs(v - b[k]) < eps, `${a} vs ${b}`));
const MAY = json('alignment-analysis/accepted-registration.json'), SEP = json('scan-assets/captures/2026-09-17/registration.json');
const MANIFESTS = {may: json('scan-assets/panoramas/manifest.json'), sep: json('scan-assets/captures/2026-09-17/panoramas/manifest.json')};

test('captures: May 6 default + accepted registration, Sep 17 provisional; paths match scan-compare captureSelection', () => {
  const html = read('scan-compare.html'), fn = html.match(/function captureSelection\(search\)\{[\s\S]*?\n\}/);
  assert.ok(fn, 'scan-compare captureSelection exists');
  const sel = vm.runInNewContext(fn[0] + ';captureSelection', {URLSearchParams});
  for (const date of ['2026-05-06', '2026-09-17']) {
    const a = X.captureConfig(date), b = sel('?capture=' + date);
    assert.equal(a.photo, b.photo); assert.equal(a.registration, b.registration); assert.equal(a.provisional, b.provisional);
  }
  assert.equal(X.captureConfig(undefined).date, '2026-05-06');
  assert.equal(X.captureConfig('2026-09-17').provisional, true);
  assert.match(X.captureConfig('2026-09-17').alignmentText, /PROVISIONAL/);
  assert.match(X.captureConfig('2026-05-06').alignmentText, /not surveyed/);
  assert.ok(X.validRegistration(MAY) && X.validRegistration(SEP));
  assert.equal(MAY.status, 'geometry-registered'); assert.equal(SEP.status, 'project-frame-provisional');
  assert.equal(X.validRegistration({rotationYDegrees: 1, translation: [0, 0], scale: 1}), false);
  assert.equal(X.validRegistration({rotationYDegrees: 1, translation: [0, 0, 0], scale: 1.01}), false);
});

test('BIM root group = exact inverse of registration-core apply (so BIM lands where the web overlay puts it)', () => {
  for (const reg of [MAY, SEP, {rotationYDegrees: -137.25, translation: [3, -1, 9], scale: 1}]) {
    const tf = X.bimRootTransform(reg);
    for (const p of [[0, 0, 0], [-35.2, 5.1, -25], [12.3, 6.1, -4.2], [55, 11, 41]]) {
      near(X.applyRootTransform(tf, p), RC.invert(reg, p), 1e-9);
      near(X.applyRootTransform(tf, RC.apply(reg, p)), p, 1e-9);
    }
    near(X.applyReg(reg, [1, 2, 3]), RC.apply(reg, [1, 2, 3])); near(X.invertReg(reg, [1, 2, 3]), RC.invert(reg, [1, 2, 3]));
  }
});

test('placement consistency with scan-compare convert(): same camera-relative direction to every BIM point', () => {
  const html = read('scan-compare.html'), fn = html.match(/function convert\(p,from\)\{[\s\S]*?\n\}/);
  assert.ok(fn, 'scan-compare convert exists');
  for (const reg of [MAY, SEP]) {
    const convert = vm.runInNewContext('const registration=' + JSON.stringify(reg) + ';' + fn[0] + ';convert');
    const s = MANIFESTS.may.stations[10], qScan = X.stationQuaternion(s.e57Quaternion), pose = {position: s.position, quaternion: qScan, fov: 65, zoom: 1};
    const bim = convert(pose, 'scan'), inv = q => [-q[0], -q[1], -q[2], q[3]];
    for (const P of [[-30, 7, -20], [-20.5, 9.2, -10], [-40, 6.4, 5]]) {
      // web overlay: BIM camera in BIM frame looking at P;  XR: scan-frame camera looking at the BIM placed by the inverse map
      const web = X.rotateByQuat(inv(bim.quaternion), P.map((v, k) => v - bim.position[k]));
      const xr = X.rotateByQuat(inv(qScan), X.applyRootTransform(X.bimRootTransform(reg), P).map((v, k) => v - s.position[k]));
      near(web, xr, 1e-9);
    }
  }
});

test('photo sphere orientation matches scan-photo stationOrientation (Three.js)', async () => {
  let THREE;
  for (const c of [process.env.THREE_MODULE, path.join(root, 'tools/node_modules/three/build/three.module.js')].filter(Boolean)) {
    try { THREE = await import(pathToFileURL(c).href); break; } catch {}
  }
  if (!THREE) return test.skip?.('three not installed');
  const axis = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2), center = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI);
  const ref = (e57, d) => { const q = new THREE.Quaternion().copy(axis).multiply(new THREE.Quaternion().fromArray(e57)).multiply(axis.clone().invert()).multiply(center); return d ? new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), d * Math.PI / 180).multiply(q) : q; };
  for (const e57 of [MANIFESTS.may.stations[0].e57Quaternion, MANIFESTS.sep.stations[5].e57Quaternion, [0.1, 0.2, 0.3, 0.927].map((v, _, a) => v / Math.hypot(...a))]) for (const d of [0, 3.5, -170]) {
    const a = X.stationQuaternion(e57, d), b = ref(e57, d).toArray(), sign = Math.sign(a[3] * b[3] + a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) || 1;
    near(a, b.map(v => v * sign), 1e-6);
  }
});

test('neighbour navigation = scan-photo chooseWalkNeighbor on both real manifests', () => {
  const fn = read('scan-photo.html').match(/function chooseWalkNeighbor\([\s\S]*?\n}/), ref = vm.runInNewContext(fn[0] + ';chooseWalkNeighbor');
  let moves = 0;
  for (const m of Object.values(MANIFESTS)) for (let i = 0; i < m.stations.length; i++) for (let k = 0; k < 16; k++) {
    const a = k * Math.PI / 8, dir = [Math.cos(a), 0, Math.sin(a)], got = X.chooseNeighbor(m.stations, i, dir);
    assert.equal(got, ref(m.stations, i, dir));
    if (got >= 0) { moves++; assert.ok(m.stations[i].neighbors.includes(got), 'only recorded neighbours'); }
  }
  assert.ok(moves > 1000);
  assert.equal(X.chooseNeighbor([{position: [0, 0, 0], neighbors: [1]}, {position: [0, 0, -9]}], 0, [0, 0, -1]), -1, '5.5 m bound');
});

test('thumbstick hysteresis: one action per push, snap turn keeps the head fixed, rig puts the head on the station', () => {
  const s = {armed: true};
  assert.equal(X.stickStep(s, 0, -.9), 'forward'); assert.equal(X.stickStep(s, 0, -.95), null, 'held: no repeat');
  assert.equal(X.stickStep(s, 0, -.5), null); assert.equal(X.stickStep(s, 0, -.1), null, 're-armed only'); assert.equal(X.stickStep(s, .8, .1), 'turn-right');
  X.stickStep(s, 0, 0); assert.equal(X.stickStep(s, -.2, .9), 'back'); X.stickStep(s, 0, 0); assert.equal(X.stickStep(s, -.8, .3), 'turn-left'); X.stickStep(s, 0, 0); assert.equal(X.stickStep(s, .5, .5), null, 'dead zone');
  const rot = (yaw, v) => [Math.cos(yaw) * v[0] + Math.sin(yaw) * v[2], v[1], -Math.sin(yaw) * v[0] + Math.cos(yaw) * v[2]];
  const rig = [3, 0, -2], yaw = .4, headLocal = [.3, 1.6, -.2], head = rot(yaw, headLocal).map((v, k) => v + rig[k]);
  const t = X.snapTurn(rig, yaw, head, Math.PI / 6), after = rot(t.yaw, headLocal).map((v, k) => v + t.position[k]);
  near(after, head, 1e-12); assert.ok(Math.abs(t.yaw - (yaw + Math.PI / 6)) < 1e-12);
  const st = [20.3, 6.0, 38.8], r = X.rigForStation(st, yaw, headLocal);
  near(rot(yaw, headLocal).map((v, k) => v + r[k]), st, 1e-12);
});

test('flashlight cone: inside, soft edge, outside, behind; Lens vs All alpha', () => {
  const o = [0, 0, 0], d = [0, 0, -1], c = X.coneCos(12), soft = c - X.coneCos(14);
  assert.equal(X.coneWeight(o, d, c, soft, [0, 0, -5]), 1);
  assert.equal(X.coneWeight(o, d, c, soft, [0, 0, 5]), 0, 'behind the controller');
  const at = deg => X.coneWeight(o, d, c, soft, [Math.sin(deg * Math.PI / 180) * 4, 0, -Math.cos(deg * Math.PI / 180) * 4]);
  assert.equal(at(11), 1); assert.equal(at(20), 0); assert.ok(at(13) > 0 && at(13) < 1, 'soft edge');
  assert.equal(X.fragmentAlpha('lens', .85, 0), 0); assert.equal(X.fragmentAlpha('lens', .85, 1), .85); assert.equal(X.fragmentAlpha('all', .35, 0), .35);
  assert.equal(X.stepOpacity(.85, 1), 1); assert.equal(X.stepOpacity(1, 1), 1); assert.equal(X.stepOpacity(.15, -1), .15); assert.equal(X.stepOpacity(.33, -1), .15);
  assert.equal(X.stepCone(30, 1), 30); assert.equal(X.stepCone(4, -1), 4); assert.equal(X.stepCone(12, 1), 14);
  assert.ok(X.withinRadius([0, 0, 0], [15, 0, 0], 2, 14)); assert.ok(!X.withinRadius([0, 0, 0], [17, 0, 0], 2, 14));
  assert.equal(X.cellKey(-.1, 6.1, 6), '-1,1');
});

test('XR menu: every button centre hits its own index, gaps and header miss', () => {
  for (let i = 0; i < 10; i++) { const r = X.menuRect(i); assert.equal(X.menuHit(r.x + r.w / 2, 1 - (r.y + r.h / 2)), i); }
  assert.equal(X.menuHit(.5, .9), -1, 'header'); assert.equal(X.menuHit(.01, .2), -1, 'margin');
  const a = X.menuRect(0), b = X.menuRect(1); assert.equal(X.menuHit((a.x + a.w + b.x) / 2, 1 - (a.y + a.h / 2)), -1, 'gap');
});

test('info card keeps the ElementCards honesty ladder (CONTEXT is a building meter, NO FEED stays no feed)', () => {
  const sep = X.captureConfig('2026-09-17'), may = X.captureConfig('2026-05-06');
  const meters = {76: {latest: {kw: 120.5, t: new Date().toISOString()}}, 77: {latest: {kw: 40, t: new Date().toISOString()}}};
  const ctxMeta = {name: 'RT_EQ_Transformer', type: 'Transformer', system: 'Electrical', level: 'LEVEL 01', layer: 'equipment', isFedBy: ['bmo:meter:76:kw', 'bmo:meter:77:kw']};
  const ctx = X.cardLines('138752', ctxMeta, EC.elementFeedTier('138752', ctxMeta, null, meters), may);
  assert.equal(ctx.badge, 'CONTEXT'); assert.ok(ctx.rows.some(r => /not this element/.test(r))); assert.ok(!ctx.rows.some(r => /LIVE/.test(r)));
  assert.match(ctx.footer[1], /Design \(BIM\) position/); assert.match(ctx.footer[0], /registered.*not surveyed/); assert.match(ctx.footer[1], /equipment · id 138752/);
  assert.equal(ctx.sub, 'Transformer · Electrical · LEVEL 01');
  const none = X.cardLines('9', {name: 'Duct', layer: 'duct'}, EC.elementFeedTier('9', {name: 'Duct', layer: 'duct'}, null, {}), sep);
  assert.equal(none.badge, 'NO FEED'); assert.ok(none.rows.includes('No feed yet')); assert.match(none.footer[0], /^Sep 17, 2026 · PROVISIONAL alignment \(not surveyed\)$/);
  const offline = X.cardLines('1', ctxMeta, EC.elementFeedTier('1', ctxMeta, null, {}), may);
  assert.ok(offline.rows.includes(EC.NO_READING_TEXT), 'missing meter is never 0');
  const forced = X.cardLines('1', {}, {tier: 'CONTEXT', label: 'CONTEXT', cls: 'ctx', valueText: '12 kW'}, may);
  assert.ok(forced.rows.some(r => /not this element/.test(r)), 'CONTEXT note added even if a tier omits it');
  assert.ok(X.cardLines('1', {name: 'x'.repeat(90)}, {tier: 'NONE', label: 'NO FEED', valueText: ''}, may).title.length <= 44);
});

test('scan-xr.html wiring: shared scripts, pinned three, overlay layer set, no edits to the source pages', () => {
  const html = read('scan-xr.html');
  for (const s of ['registration-core.js', 'twin/element-cards.js', 'twin/xr-core.js']) assert.ok(html.includes(`<script src="${s}"></script>`));
  assert.ok(html.includes('three@0.169.0/build/three.module.js') && !/three@0\.1[^6]/.test(html));
  const bim = read('scan-bim.html'), keys = bim.match(/const OVERLAY_LAYER_KEYS=(\[[^\]]*\])/)[1];
  assert.ok(html.includes('const OVERLAY_LAYER_KEYS=' + keys), 'same service layers as the web overlay');
  assert.ok(html.includes("const EQUIP_OFFSET={x:-35.28,y:-97.16,z:28.60}") && /EQUIP_OFFSET = \{ x: -35\.28, y: -97\.16, z: 28\.60 \}/.test(bim), 'same layer placement as scan-bim');
  assert.ok(html.includes("renderer.shadowMap.enabled=false") && html.includes('setFramebufferScaleFactor') && html.includes('setFoveation'));
  assert.ok(!/accepted-registration\.json['"]?\s*,\s*\{\s*method:\s*['"]PUT/.test(html) && !/localStorage\.setItem/.test(html));
});
