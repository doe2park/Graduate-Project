/* twin/mr-align.js: Quest MR passthrough alignment maths (yaw + translation from touched landmarks), residuals,
   leave-one-out, noise behaviour, nudge, anchors, persistence, check offsets, the session state machine, the
   landmark file and the scan-xr.html wiring.   node --test tests/mr-align.test.cjs */
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const ROOT = path.join(__dirname, '..'), read = f => fs.readFileSync(path.join(ROOT, f), 'utf8');
const MR = require('../twin/mr-align.js'), RC = require('../registration-core.js'), OV = require('../twin/overlay-visibility.js');
const close = (a, b, eps, msg) => assert.ok(Math.abs(a - b) <= eps, `${msg || ''} ${a} vs ${b} (eps ${eps})`);
const close3 = (a, b, eps, msg) => a.forEach((v, k) => close(v, b[k], eps, msg));
const LANDMARKS = JSON.parse(read('buildings/grimes/mr-landmarks.json'));

test('yaw convention matches registration-core apply() and Three.js rotation.y; invert/compose round trip', () => {
  const T = {yawDeg: 37.5, t: [1.2, -5.25, -3.4]}, p = [-18.77, 6.25, -7.15];
  close3(MR.applyT(T, p), RC.apply({rotationYDegrees: T.yawDeg, translation: T.t}, p), 1e-12, 'same as registration-core');
  // Three.js Object3D: position + R_y(rotation.y) p, with R_y = [[c,0,s],[0,1,0],[-s,0,c]]
  const a = T.yawDeg * Math.PI / 180, three = [Math.cos(a) * p[0] + Math.sin(a) * p[2] + T.t[0], p[1] + T.t[1], -Math.sin(a) * p[0] + Math.cos(a) * p[2] + T.t[2]];
  close3(MR.applyT(T, p), three, 1e-12, 'Three.js composition');
  close3(MR.applyT(MR.invertT(T), MR.applyT(T, p)), p, 1e-12, 'inverse');
  const B = {yawDeg: -120, t: [4, 0.5, 9]};
  close3(MR.applyT(MR.composeT(T, B), p), MR.applyT(T, MR.applyT(B, p)), 1e-12, 'compose');
  assert.equal(MR.wrapDeg(190), -170); assert.equal(MR.wrapDeg(-180), 180);
});

test('exact touches recover the transform (xz points at random heights + floor touch)', () => {
  const area = MR.areaById(LANDMARKS, 'l1-auditorium-foyer');
  for (const yawDeg of [0, 37, -150, 179.5]) {
    const Tt = {yawDeg, t: [2.1, -area.floorY, -7.3]}, r = MR.rng(1);
    const pairs = area.points.map(p => ({id: p.id, kind: p.kind, bim: MR.landmarkBim(area, p), xr: MR.simulateTouch(area, p, Tt, {noiseM: 0, random: r})}));
    const f = MR.fitAlignment(pairs, {floorY: area.floorY});
    assert.ok(f.ok, f.error);
    close(MR.wrapDeg(f.T.yawDeg - yawDeg), 0, 1e-9, 'yaw');
    close3(f.T.t, Tt.t, 1e-9, 'translation');
    assert.ok(f.rmsM < 1e-9 && f.heightSource === 'floor-touch' && f.label === 'manual alignment, not surveyed');
  }
});

test('same least-squares solution as registration-core fitYawTranslation on 3D pairs', () => {
  const r = MR.rng(42), Tt = {yawDeg: -63.2, t: [10, 1.5, -4]}, pairs = [];
  for (let i = 0; i < 6; i++) {
    const b = [r() * 20 - 10, 5 + r() * 3, r() * 20 - 10], x = MR.applyT(Tt, b);
    pairs.push({id: 'p' + i, kind: 'xyz', bim: b, xr: x.map(v => v + (r() - .5) * .04)});
  }
  const f = MR.fitAlignment(pairs), ref = RC.fitYawTranslation(pairs.map(p => ({scan: p.bim, bim: p.xr})));
  close(f.T.yawDeg, ref.rotationYDegrees, 1e-9, 'yaw'); close(f.T.t[0], ref.translation[0], 1e-9); close(f.T.t[2], ref.translation[2], 1e-9);
  close(f.T.t[1], ref.translation[1], 1e-9, 'height = mean offset');
});

test('noise: 1 cm and 3 cm touch noise on the real foyer landmarks (200 seeded trials each)', () => {
  const area = MR.areaById(LANDMARKS, 'l1-auditorium-foyer'), Tt = {yawDeg: 81, t: [-3, -area.floorY, 12]};
  const plan = area.points.filter(p => p.kind === 'xz');
  for (const [sigma, maxP95Cm, yawP95] of [[0.01, 3, 0.4], [0.03, 8, 1.2]]) {
    const errs = [], yaws = [], rms = [], r = MR.rng(Math.round(sigma * 1e4));
    for (let k = 0; k < 200; k++) {
      const pairs = area.points.map(p => ({id: p.id, kind: p.kind, bim: MR.landmarkBim(area, p), xr: MR.simulateTouch(area, p, Tt, {noiseM: sigma, random: r})}));
      const f = MR.fitAlignment(pairs, {floorY: area.floorY}); assert.ok(f.ok);
      // true error at the landmarks and at a sprinkler head 2.9 m up (what the user actually compares)
      const probes = [...plan.map(p => p.bim), ...area.checks.map(c => c.bim)];
      errs.push(Math.max(...probes.map(b => { const a = MR.applyT(f.T, b), t = MR.applyT(Tt, b); return Math.hypot(a[0] - t[0], a[1] - t[1], a[2] - t[2]); })));
      yaws.push(Math.abs(MR.wrapDeg(f.T.yawDeg - Tt.yawDeg))); rms.push(f.rmsM);
    }
    const p95 = a => [...a].sort((x, y) => x - y)[Math.floor(a.length * .95)];
    assert.ok(p95(errs) * 100 < maxP95Cm, `σ=${sigma}: p95 true error ${(p95(errs) * 100).toFixed(1)} cm`);
    assert.ok(p95(yaws) < yawP95, `σ=${sigma}: p95 yaw error ${p95(yaws).toFixed(2)}°`);
    const meanRms = rms.reduce((a, b) => a + b, 0) / rms.length;
    assert.ok(meanRms > sigma * 0.4 && meanRms < sigma * 1.6, `σ=${sigma}: mean residual RMS ${meanRms} tracks the noise`);
  }
});

test('a mis-touched point stands out (worst residual and leave-one-out)', () => {
  const area = MR.areaById(LANDMARKS, 'l1-auditorium-foyer'), Tt = {yawDeg: 12, t: [0, -area.floorY, 0]}, r = MR.rng(5);
  const pairs = area.points.map(p => ({id: p.id, kind: p.kind, bim: MR.landmarkBim(area, p), xr: MR.simulateTouch(area, p, Tt, {noiseM: 0.005, random: r})}));
  pairs.find(p => p.id === 'C').xr[0] += 0.30;   // touched the wrong corner, 30 cm off
  const f = MR.fitAlignment(pairs, {floorY: area.floorY});
  assert.equal(f.worst, 'C');
  const loo = f.leaveOneOut;
  assert.ok(loo.C > 0.25, 'C predicted from the others is ~30 cm off: ' + loo.C);
  for (const id of ['A', 'B', 'D']) assert.ok(loo[id] < loo.C, id + ' less suspicious than C');
});

test('two points: allowed, residual only checks the spacing, warning given; degenerate inputs refused', () => {
  const area = MR.areaById(LANDMARKS, 'l1-east-entrance'), Tt = {yawDeg: -30, t: [1, -area.floorY, 2]};
  const A = area.points.find(p => p.id === 'A'), E = area.points.find(p => p.id === 'E');
  const xa = MR.applyT(Tt, A.bim), xe = MR.applyT(Tt, E.bim); xe[0] += 0.04;   // 4 cm spacing error along ~x
  const f = MR.fitAlignment([{id: 'A', kind: 'xz', bim: A.bim, xr: xa}, {id: 'E', kind: 'xz', bim: E.bim, xr: xe}], {floorY: area.floorY});
  assert.ok(f.ok && f.planPoints === 2 && f.warnings.some(w => /Only 2 plan points/.test(w)) && f.warnings.some(w => /Quest floor/.test(w)));
  assert.equal(f.heightSource, 'quest-floor-assumed'); close(f.T.t[1], -area.floorY, 1e-12, 'height from the Quest floor = BIM floor datum');
  assert.ok(f.horizontalRmsM < 0.04);
  assert.equal(MR.fitAlignment([{id: 'A', kind: 'xz', bim: A.bim, xr: xa}], {floorY: 5.25}).ok, false);
  const near = MR.fitAlignment([{id: 'a', kind: 'xz', bim: [0, 0, 0], xr: [0, 0, 0]}, {id: 'b', kind: 'xz', bim: [0.3, 0, 0], xr: [0.3, 0, 0]}], {floorY: 0});
  assert.equal(near.ok, false); assert.match(near.error, /too close/);
  assert.equal(MR.fitAlignment([{id: 'a', kind: 'xz', bim: [0, 0, 0], xr: [0, 0, 0]}, {id: 'b', kind: 'xz', bim: [3, 0, 0], xr: [3, 0, 0]}]).ok, false, 'no height reference at all');
  const short = MR.fitAlignment([A, area.points.find(p => p.id === 'B')].map(p => ({id: p.id, kind: 'xz', bim: p.bim, xr: MR.applyT(Tt, p.bim)})), {floorY: 5.25});
  assert.ok(short.warnings.some(w => /span only 1\.8 m/.test(w)), 'door jambs alone: short span warning');
});

test('nudge: move in the head heading, turn about the head (the BIM point under the head stays put), height', () => {
  const T = {yawDeg: 20, t: [1, -5.25, 2]}, head = [0.5, 1.6, -0.5];
  const underHead = MR.applyT(MR.invertT(T), head), turned = MR.nudge(T, {yawDeg: 1, pivot: head});
  close3(MR.applyT(turned, underHead), head, 1e-12, 'pivot fixed');
  close(turned.yawDeg, 21, 1e-12);
  const f = MR.headingStep('forward', 0, 0.01); close3(f, [0, 0, -0.01], 1e-15, 'yaw 0 looks along -z');
  close3(MR.headingStep('right', Math.PI / 2, 0.05), [0, 0, -0.05], 1e-15, 'facing -x, right is -z');
  close3(MR.nudge(T, {move: [0, 0.01, 0]}).t, [1, -5.24, 2], 1e-12);
  // yawFromQuaternion: rotation about +Y by a
  for (const a of [0, 0.4, -2.5, Math.PI - 0.01]) close(MR.yawFromQuaternion([0, Math.sin(a / 2), 0, Math.cos(a / 2)]), a, 1e-12, 'yaw ' + a);
  assert.deepEqual(MR.NUDGE_STEPS.fine, {moveM: 0.01, yawDeg: 0.25});
});

test('anchor frame: stored relative to the anchor, rebuilt when the anchor reappears in a new session frame', () => {
  const T = {yawDeg: 33, t: [3, -5.25, -8]}, A = {yawDeg: 0, t: [1, 0, -2]}, local = MR.toAnchorFrame(T, A);
  // next session: a different local-floor origin/heading G; the anchor is reported at G(A)
  const G = {yawDeg: -75, t: [4, 0.02, 1]}, A2 = MR.composeT(G, A), T2 = MR.fromAnchorFrame(local, A2), p = [-20, 6, -6];
  close3(MR.applyT(T2, p), MR.applyT(G, MR.applyT(T, p)), 1e-9, 'alignment follows the anchor');
  const q = [0, Math.sin(0.3), 0, Math.cos(0.3)], At = MR.anchorT([1, 2, 3], q);
  close(At.yawDeg, 0.6 * 180 / Math.PI, 1e-9); assert.deepEqual(At.t, [1, 2, 3]);
});

test('persistence: record schema, anchor vs session frame, guarded storage, check log', () => {
  const mem = () => { const m = new Map(); return {getItem: k => m.has(k) ? m.get(k) : null, setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k), m}; };
  const st = mem(), fit = {ok: true, rmsM: 0.0234, n: 5, heightSource: 'floor-touch'};
  const rec = MR.makeRecord({area: 'l1-auditorium-foyer', level: 'L1', T: {yawDeg: 10, t: [1, 2, 3]}, fit, created: '2026-10-21T10:00:00Z'});
  assert.equal(rec.frame, 'session'); assert.equal(rec.anchor, null); assert.equal(rec.rmsCm, 2.3); assert.equal(rec.label, 'manual alignment, not surveyed');
  assert.ok(MR.saveRecord(st, rec)); assert.deepEqual(MR.loadRecord(st), rec); assert.ok([...st.m.keys()].every(k => k === MR.STORE_KEY));
  const ra = MR.makeRecord({area: 'x', level: 'L1', T: {yawDeg: 1, t: [0, 0, 0]}, anchorHandle: 'uuid-1', anchorLocal: {yawDeg: 2, t: [1, 1, 1]}});
  assert.equal(ra.frame, 'anchor'); assert.equal(MR.parseRecord(JSON.stringify(ra)).anchor.handle, 'uuid-1');
  assert.equal(MR.makeRecord({area: 'x', T: {yawDeg: 1, t: [0, 0, 0]}, anchorHandle: null, anchorLocal: {yawDeg: 2, t: [1, 1, 1]}}).frame, 'session', 'no persistent handle = session frame');
  for (const bad of ['{', '{}', JSON.stringify({...rec, schema: 'x'}), JSON.stringify({...rec, t: [1, 2]}), JSON.stringify({...rec, frame: 'anchor'})]) assert.equal(MR.parseRecord(bad), null);
  const broken = {getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); }, removeItem() { throw new Error('denied'); }};
  assert.equal(MR.saveRecord(broken, rec), false); assert.equal(MR.loadRecord(broken), null); assert.equal(MR.clearRecord(broken), false);
  assert.ok(MR.clearRecord(st)); assert.equal(MR.loadRecord(st), null);
  assert.equal(MR.appendCheck(st, {check: 'S1', horizontalCm: 4.2}), 1); assert.equal(MR.appendCheck(st, {check: 'G1'}), 2);
  assert.deepEqual(MR.loadChecks(st).map(r => r.check), ['S1', 'G1']); assert.deepEqual(MR.loadChecks(broken), []);
  assert.throws(() => MR.makeRecord({area: 'x', T: {yawDeg: NaN, t: [0, 0, 0]}}));
});

test('check offset: installed device vs aligned BIM, reported in BIM axes', () => {
  const T = {yawDeg: 90, t: [5, -5.25, 1]}, head = [-21.564, 8.22, -5.957];
  const realBim = [head[0] + 0.06, 0, head[2] - 0.08], tip = MR.applyT(T, [realBim[0], 6.3, realBim[2]]);
  const o = MR.checkOffset(T, head, tip);
  close(o.horizontalCm, 10, 0.05); close(o.dxBimCm, 6, 0.05); close(o.dzBimCm, -8, 0.05); close(o.heightBelowCm, 192, 0.05);
});

test('alignment session: capture, skip, redo, early solve; summary text', () => {
  const area = MR.areaById(LANDMARKS, 'l1-east-entrance'), Tt = {yawDeg: 140, t: [0.3, -area.floorY, 4]}, r = MR.rng(9);
  const s = MR.createSession(area);
  assert.equal(MR.currentPoint(area, s).id, 'A');
  MR.capture(area, s, MR.simulateTouch(area, area.points[0], Tt, {noiseM: 0.005, random: r}));
  MR.skip(area, s); assert.equal(MR.currentPoint(area, s).id, 'C'); assert.ok(s.skipped.B);
  MR.capture(area, s, [9, 9, 9]); MR.redo(area, s); assert.equal(MR.currentPoint(area, s).id, 'C', 'redo goes back to the last touched point');
  for (const p of area.points.slice(2)) MR.capture(area, s, MR.simulateTouch(area, p, Tt, {noiseM: 0.005, random: r}));
  assert.equal(s.phase, 'review'); assert.ok(s.fit.ok && s.fit.n === 5);
  assert.ok(Math.abs(MR.wrapDeg(s.fit.T.yawDeg - 140)) < 0.3);
  assert.match(MR.summary(s.fit), /^RMS \d+\.\d cm · worst [A-F] \d+\.\d cm · 5 points · height floor touch$/);
  const e = MR.createSession(area); MR.capture(area, e, MR.applyT(Tt, area.points[0].bim)); MR.capture(area, e, MR.applyT(Tt, area.points[4].bim));
  assert.equal(MR.capturedPlanCount(area, e), 2); MR.finishEarly(area, e); assert.ok(e.fit.ok, 'A + the far point E already fix the heading');
  assert.equal(MR.summary({ok: false, error: 'x'}), 'x');
});

test('landmark file: schema, BIM-derived labels, plan points per area, includes the auditorium-foyer area', () => {
  MR.validateLandmarks(LANDMARKS);
  assert.match(LANDMARKS.status, /not verified on site/); assert.match(LANDMARKS.frame, /EQUIP_OFFSET/);
  const foyer = MR.areaById(LANDMARKS, 'l1-auditorium-foyer');
  assert.equal(foyer.id, 'l1-auditorium-foyer'); assert.equal(foyer.level, 'L1');
  assert.ok(foyer.points.filter(p => p.kind === 'xz').length >= 3 && foyer.points.some(p => p.kind === 'y'));
  assert.ok(foyer.checks.some(c => /sprinkler/i.test(c.label)) && foyer.checks.some(c => /24×24/.test(c.label)));
  for (const a of LANDMARKS.areas) for (const p of [...a.points, ...a.checks]) if (p.source) {
    const b = p.source.box; assert.ok(b.min.every((v, k) => v <= b.max[k]), 'element box');
    if (p.kind === 'xz') assert.ok(p.bim[0] >= b.min[0] - 1e-9 && p.bim[0] <= b.max[0] + 1e-9 && p.bim[2] >= b.min[2] - 1e-9 && p.bim[2] <= b.max[2] + 1e-9, p.id + ' on its element box');
  }
  for (const f of Object.keys(LANDMARKS.inputs)) assert.ok(fs.existsSync(path.join(ROOT, f)), f);
  assert.throws(() => MR.validateLandmarks({schema: 'grimes-mr-landmarks/1', areas: [{id: 'a', floorY: 0, points: [{id: 'A', kind: 'xz', bim: [0, 0, 0]}]}]}), /2 plan points/);
});

test('landmark file is reproducible from the GLBs (read-only Draco decode)', {skip: !fs.existsSync(path.join(ROOT, 'tools/node_modules/three/examples/jsm/libs/draco/gltf/draco_decoder.js')) && 'needs tools/node_modules/three'}, async () => {
  const {build} = await import(path.join(ROOT, 'scripts/derive_mr_landmarks.mjs'));
  const fresh = await build();
  assert.deepEqual(fresh, LANDMARKS, 'buildings/grimes/mr-landmarks.json matches scripts/derive_mr_landmarks.mjs --write');
});

test('shader mirror: lens floor outside the cone and the overlay-visibility distance fade', () => {
  const near = OV.uniformValues('near').fade, room = OV.uniformValues('room').fade;
  for (const d of [0, 2.9, 4, 5.5, 6, 9]) close(MR.mrAlpha({mode: 'all', opacity: 1, distance: d, fade: near}), OV.rangeFade(d, 'near'), 1e-12, 'near ' + d);
  for (const d of [7, 10, 13.9]) close(MR.mrAlpha({mode: 'all', opacity: 1, distance: d, fade: room}), OV.rangeFade(d, 'room'), 1e-12, 'room ' + d);
  close(MR.mrAlpha({mode: 'lens', opacity: 0.85, cone: 0, outside: 0.12}), 0.85 * 0.12, 1e-12, 'outside the cone: faint');
  close(MR.mrAlpha({mode: 'lens', opacity: 0.85, cone: 1, outside: 0.12}), 0.85, 1e-12, 'inside: full');
  close(MR.mrAlpha({mode: 'lens', opacity: 0.85, cone: 0.3, outside: 0}), 0.85 * 0.3, 1e-12, 'outside 0 = the VR lens');
  for (let i = 0; i < 15; i++) { const r = MR.gridRect(MR.PANEL, i); assert.equal(MR.gridHit(MR.PANEL, r.x + r.w / 2, 1 - (r.y + r.h / 2)), i); }
  assert.equal(MR.gridHit(MR.PANEL, 0.5, 0.9), -1, 'header is not a button');
});

test('scan-xr.html MR wiring: immersive-ar with local-floor + optional features, transparent services-only scene, honest labels, storage via MRAlign only', () => {
  const html = read('scan-xr.html');
  for (const s of ['twin/overlay-visibility.js', 'twin/mr-align.js']) assert.match(html, new RegExp(`<script src="${s.replace(/\./g, '\\.')}(\\?v=\\d+)?"></script>`));
  assert.ok(html.includes("navigator.xr.requestSession('immersive-ar',{requiredFeatures:['local-floor'],optionalFeatures:['hit-test','anchors','plane-detection','mesh-detection','dom-overlay']"));
  assert.ok(html.includes("isSessionSupported('immersive-ar')") && html.includes("const MODE_AR=q.get('mode')==='ar'"));
  assert.ok(html.includes("const MR_DEFAULT_LAYERS=['fire','duct','plumbing']"));
  assert.ok(html.includes("renderer.xr.setReferenceSpaceType('local-floor')") && html.includes('setFoveation(P.foveation)') && html.includes('updateTargetFrameRate(72)'));
  assert.ok(/if\(fadeOn>\.5\)a\*=1\.-smoothstep\(fadeRange\.x,fadeRange\.y,length\(vWorld-cameraPosition\)\)/.test(html), 'per-fragment distance fade in the XR shader');
  assert.ok(html.includes('opacity*mix(outside,1.,w)'), 'lens floor');
  assert.ok(html.includes("fetchJson('buildings/grimes/mr-landmarks.json')"));
  assert.ok(html.includes('MR.saveRecord(localStorage') && !/localStorage\.setItem/.test(html), 'only MRAlign writes storage (its own keys)');
  assert.ok(/'MR passthrough · '\+mrShort\(\)\+' · '\+MR\.LABEL/.test(html) && MR.LABEL === 'manual alignment, not surveyed');
  assert.ok(html.includes("sphere.visible=false") && /function bootMR\(\)[\s\S]*?sphere\.visible=false/.test(html), 'no photo sphere in MR');
});

/* ── Demo here placement ── */
const FOYER = LANDMARKS.areas[0];
test('demo: the area reference point (plan centroid at floorY) lands exactly on the chosen floor point', () => {
  const R = MR.demoReference(FOYER);
  assert.equal(R[1], FOYER.floorY);
  const plan = FOYER.points.filter(p => p.kind !== 'y');
  close(R[0], plan.reduce((m, p) => m + p.bim[0], 0) / plan.length, 1e-12); close(R[2], plan.reduce((m, p) => m + p.bim[2], 0) / plan.length, 1e-12);
  for (const [F, hy] of [[[0, 0, 0], 0], [[2.5, 0.03, -4], 1.1], [[-7, 0, 9], -2.9], [[1, 0, 1], Math.PI]]) {
    const T = MR.demoTransform(FOYER, {floorPoint: F, headYawRad: hy});
    close3(MR.applyT(T, R), F, 1e-9, 'reference -> floor point');
  }
});
test('demo: heading convention, BIM -z (toward the auditorium doors) faces where the head looks; heights stay relative to the floor', () => {
  const R = MR.demoReference(FOYER), F = [3, 0, -2];
  for (const hy of [0, 0.7, -1.9, 3]) {
    const T = MR.demoTransform(FOYER, {floorPoint: F, headYawRad: hy});
    const a = MR.applyT(T, R), b = MR.applyT(T, [R[0], R[1], R[2] - 1]);          // one metre along BIM -z
    close3([b[0] - a[0], b[2] - a[2]], [-Math.sin(hy), -Math.cos(hy)], 1e-9, 'BIM forward = head forward (headingStep convention)');
    close3(MR.headingStep('forward', hy, 1).filter((_, k) => k !== 1), [b[0] - a[0], b[2] - a[2]], 1e-9);
    close(b[1], a[1], 1e-9, 'level');
    close(MR.applyT(T, [R[0], R[1] + 3.2, R[2]])[1] - F[1], 3.2, 1e-9, 'a 3.2 m ceiling stays 3.2 m above the floor point');
  }
  // heading 0 means no rotation; a quaternion yaw maps through yawFromQuaternion
  assert.equal(MR.demoTransform(FOYER, {floorPoint: F, headYawRad: 0}).yawDeg, 0);
  const hy = 0.9, q = [0, Math.sin(hy / 2), 0, Math.cos(hy / 2)];
  close(MR.demoTransform(FOYER, {floorPoint: F, headYawRad: MR.yawFromQuaternion(q)}).yawDeg, hy * 180 / Math.PI, 1e-9);
  // custom forward vector
  const T2 = MR.demoTransform(FOYER, {floorPoint: F, headYawRad: 0, forwardBim: [1, 0, 0]}), a = MR.applyT(T2, R), b = MR.applyT(T2, [R[0] + 1, R[1], R[2]]);
  close3([b[0] - a[0], b[2] - a[2]], [0, -1], 1e-9);
  assert.throws(() => MR.demoTransform(FOYER, {floorPoint: [NaN, 0, 0]}));
});
test('demo: honest label, API version, and the page never saves or checks a demo placement', () => {
  const l = MR.demoLabel(FOYER);
  assert.equal(l, 'DEMO placement · not aligned to this building · Grimes L1 foyer services shown at real scale');
  assert.ok(!/RMS|manual alignment/i.test(l));
  assert.equal(MR.API, 3);
  const html = read('scan-xr.html');
  assert.ok(html.includes(`<script src="twin/mr-align.js?v=${MR.API}"></script>`) && html.includes(`MR_ALIGN_API=${MR.API},`), 'mr-align.js versioned with its API; the page checks it');
  assert.match(html, /function mrSave\([^)]*\)\{if\(!mr\.T\|\|mr\.demo\)return;/, 'demo is never persisted');
  assert.match(html, /function mrCheck\(point,method\)\{if\(mrDemoOn\(\)\)return;/);
  assert.match(html, /function mrNextCheck\(\)\{if\(mrDemoOn\(\)\)/);
  assert.ok(html.includes("q.get('place')==='demo'") && html.includes('id="mrDemo"'));
});
