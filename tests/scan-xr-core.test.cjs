/* scan-xr.html pure helpers (twin/xr-core.js): registration placement, photo orientation, flashlight cone,
   station navigation, XR input, menu hit-testing and info-card honesty. Real capture manifests and registrations;
   scan-photo.html / scan-compare.html functions are extracted from the pages so the XR page cannot drift from them. */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const {pathToFileURL} = require('node:url');
const X = require('../twin/xr-core.js'), RC = require('../registration-core.js'), EC = require('../twin/element-cards.js');
const root = path.join(__dirname, '..'), read = f => fs.readFileSync(path.join(root, f), 'utf8'), json = f => JSON.parse(read(f));
const near = (a, b, eps = 1e-9) => a.forEach((v, k) => assert.ok(Math.abs(v - b[k]) < eps, `${a} vs ${b}`));
const MAY = json('alignment-analysis/accepted-registration.json'), SEP = json('scan-assets/captures/2026-09-17/registration.json'), OCT = json('scan-assets/captures/2026-10-18/registration.json');
const MANIFESTS = {may: json('scan-assets/panoramas/manifest.json'), sep: json('scan-assets/captures/2026-09-17/panoramas/manifest.json')};

test('captures: May 6 default + accepted registration, Sep 17 provisional; paths match scan-compare captureSelection', () => {
  const html = read('scan-compare.html'), fn = html.match(/function captureSelection\(search\)\{[\s\S]*?\n\}/);
  assert.ok(fn, 'scan-compare captureSelection exists');
  const sel = vm.runInNewContext(fn[0] + ';captureSelection', {URLSearchParams});
  for (const date of ['2026-05-06', '2026-09-17', '2026-10-18']) {
    const a = X.captureConfig(date), b = sel('?capture=' + date);
    assert.equal(a.photo, b.photo); assert.equal(a.registration, b.registration); assert.equal(a.provisional, b.provisional);
  }
  assert.equal(X.captureConfig(undefined).date, '2026-05-06');
  assert.equal(X.captureConfig('2026-09-17').provisional, true);
  assert.match(X.captureConfig('2026-09-17').alignmentText, /PROVISIONAL/);
  assert.match(X.captureConfig('2026-05-06').alignmentText, /not surveyed/);
  assert.ok(X.validRegistration(MAY) && X.validRegistration(SEP));
  assert.equal(MAY.status, 'geometry-registered'); assert.equal(SEP.status, 'project-frame-provisional');
  assert.equal(X.captureConfig('2026-10-18').provisional, true);
  assert.match(X.captureConfig('2026-10-18').alignmentText, /PROVISIONAL/);
  assert.ok(X.validRegistration(OCT)); assert.equal(OCT.status, 'project-frame-provisional');
  // Oct borrows the May transform (provisional), exactly like Sep
  assert.equal(OCT.rotationYDegrees, MAY.rotationYDegrees); assert.deepEqual(OCT.translation, MAY.translation);
  // menu cycle May → Sep → Oct → May; unknown values restart at May
  assert.deepEqual(X.CAPTURE_ORDER, ['2026-05-06', '2026-09-17', '2026-10-18']);
  assert.equal(X.nextCapture('2026-05-06'), '2026-09-17'); assert.equal(X.nextCapture('2026-09-17'), '2026-10-18');
  assert.equal(X.nextCapture('2026-10-18'), '2026-05-06'); assert.equal(X.nextCapture('bogus'), '2026-05-06');
  // public site: only captures whose manifest loaded are cycled (Oct 18 is unpublished there)
  const pub = ['2026-05-06', '2026-09-17'];
  assert.equal(X.nextCapture('2026-05-06', pub), '2026-09-17'); assert.equal(X.nextCapture('2026-09-17', pub), '2026-05-06');
  assert.equal(X.nextCapture('2026-05-06', ['2026-05-06']), '2026-05-06'); assert.equal(X.nextCapture('2026-05-06', []), '2026-05-06');
  assert.equal(X.nextCapture('2026-09-17', X.CAPTURE_ORDER), '2026-10-18');
  assert.deepEqual(Object.keys(X.CAPTURES).sort(), [...X.CAPTURE_ORDER].sort());
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

test('XR menu (2026-10-22): main page ≤ 5 large buttons, More holds settings + 8 layers; every centre hits its own index, gaps miss', () => {
  for (const [page, rows] of Object.entries(X.MENU_PAGES)) {
    const rects = X.menuLayout(rows), n = rows.reduce((a, b) => a + b, 0);
    assert.equal(rects.length, n);
    rects.forEach((r, i) => assert.equal(X.layoutHit(rects, r.x + r.w / 2, 1 - (r.y + r.h / 2)), i, page + ' ' + i));
    assert.equal(X.layoutHit(rects, .5, .9), -1, 'header'); assert.equal(X.layoutHit(rects, .01, .2), -1, 'margin');
    const a = rects[0], b = rects[1]; assert.equal(X.layoutHit(rects, (a.x + a.w + b.x) / 2, 1 - (a.y + a.h / 2)), -1, 'gap');
    for (const r of rects) assert.ok(r.x >= 0 && r.y >= X.MENU_AREA.top - 1e-12 && r.x + r.w <= 1 && r.y + r.h <= 1);
  }
  const main = X.menuButtons('main', {captureLabel: 'Sep 17', mode: 'lens', scene: 'photo', gaussianAvailable: false});
  assert.ok(main.length <= 5 && main.length === X.menuLayout(X.MENU_PAGES.main).length);
  assert.deepEqual(main.map(b => b.id), ['capture', 'style', 'scene', 'recenter', 'more']);
  assert.equal(main[0].value, 'Sep 17'); assert.equal(main[1].value, 'Lens'); assert.match(main[2].value, /no Gaussian/);
  assert.ok(!main.some(b => /opacity/i.test(b.label + b.value)), 'opacity is not on the main page');
  // main buttons are big: at the 0.64 m panel width each is wider than 0.18 m and taller than 0.09 m (0.40 m panel height)
  for (const r of X.menuLayout(X.MENU_PAGES.main)) { assert.ok(r.w * .64 > .18, 'width ' + r.w * .64); assert.ok(r.h * .4 > .09, 'height ' + r.h * .4); }
  const layers = ['equipment', 'lighting', 'conduit', 'duct', 'hydronic', 'plumbing', 'lifesafety', 'fire'].map((key, i) => ({key, label: key, on: i < 7, loading: false}));
  const more = X.menuButtons('more', {hands: 'both', opacity: .7, hiRes: false, scene: 'photo', layers});
  assert.equal(more.length, X.menuLayout(X.MENU_PAGES.more).length);
  assert.deepEqual(more.slice(0, 5).map(b => b.id), ['back', 'hands', 'opacity', 'hires', 'exit']);
  assert.equal(more[1].value, 'both hands'); assert.equal(more[2].value, '70%'); assert.equal(more[12].id, 'layer:fire'); assert.equal(more[12].value, 'off');
  assert.equal(X.menuButtons('more', {scene: 'gaussian', layers}).find(b => b.id === 'hires').value, 'n/a');
  // fixed opacity defaults, More ▸ Opacity cycles 50/70/90 %
  assert.equal(X.DEFAULT_LENS_OPACITY, .7); assert.equal(X.DEFAULT_ALL_OPACITY, .35);
  assert.equal(X.nextLensOpacity(.7), .9); assert.equal(X.nextLensOpacity(.9), .5); assert.equal(X.nextLensOpacity(.5), .7); assert.equal(X.nextLensOpacity(.33), .5);
});

test('controller roles: LEFT moves, RIGHT is the flashlight; both-hands adds the left cone; a lone controller does both', () => {
  const L = {handedness: 'left', pointer: true}, R = {handedness: 'right', pointer: true};
  assert.deepEqual(X.controllerRoles([L, R]), {move: 0, lens: [1]});
  assert.deepEqual(X.controllerRoles([R, L]), {move: 1, lens: [0]}, 'slot order does not matter');
  assert.deepEqual(X.controllerRoles([R, L], 'both'), {move: 1, lens: [0, 1]}, 'right cone first, then the left');
  assert.deepEqual(X.controllerRoles([null, R]), {move: 1, lens: [1]}, 'right alone: moves and lights');
  assert.deepEqual(X.controllerRoles([L, null]), {move: 0, lens: [0]});
  assert.deepEqual(X.controllerRoles([{handedness: 'none', pointer: true}, {handedness: 'none', pointer: true}]), {move: 0, lens: [1]});
  assert.deepEqual(X.controllerRoles([{handedness: 'left', pointer: false}, R]), {move: 1, lens: [1]}, 'gaze/screen sources are ignored');
  assert.deepEqual(X.controllerRoles([null, null]), {move: -1, lens: []});
  // stick intents: move hand aims / steps back; flashlight hand widens / narrows; both sticks snap-turn
  assert.equal(X.stickIntent('move', 'forward'), 'aim'); assert.equal(X.stickIntent('move', 'back'), 'step-back');
  assert.equal(X.stickIntent('both', 'forward'), 'aim'); assert.equal(X.stickIntent('lens', 'forward'), 'cone-wider'); assert.equal(X.stickIntent('lens', 'back'), 'cone-narrower');
  for (const r of ['move', 'lens', 'both']) { assert.equal(X.stickIntent(r, 'turn-left'), 'turn-left'); assert.equal(X.stickIntent(r, 'turn-right'), 'turn-right'); }
  assert.equal(X.stickIntent(null, 'forward'), null); assert.equal(X.stickIntent('move', null), null);
  // hold-to-aim: held keeps the preview, release goes, pulling back cancels
  assert.equal(X.aimUpdate(0, -.9), 'hold'); assert.equal(X.aimUpdate(.4, -.1), 'hold', 'sideways while held still aims');
  assert.equal(X.aimUpdate(0, -.1), 'go'); assert.equal(X.aimUpdate(0, 0), 'go'); assert.equal(X.aimUpdate(0, .8), 'cancel');
  assert.equal(X.stepConeHalf(12, 1), 15); assert.equal(X.stepConeHalf(29, 1), 30); assert.equal(X.stepConeHalf(5, -1), 4);
  // snap turn: 30° about the head, repeated 12 times returns to the start
  let rig = {position: [2, 0, -1], yaw: .3}; const head = [2.4, 1.6, -1.3];
  for (let k = 0; k < 12; k++) rig = X.snapTurn(rig.position, rig.yaw, head, Math.PI / 6);
  near(rig.position, [2, 0, -1], 1e-9); assert.ok(Math.abs(rig.yaw - .3 - 2 * Math.PI) < 1e-9);
});

test('point-and-go: floor spot -> nearest station, cone ≤ 30° / ≤ 15 m, detour penalty, other floors ignored, arc + labels', () => {
  // a corridor along -z with a side room behind a wall (only reachable by a long route)
  const st = [[0, 6, 0], [0, 6, -3], [0, 6, -6], [0, 6, -9], [0, 6, -12], [0, 6, -20], [4, 6, -6], [0, 9.5, -6], [3, 6, 0.5]].map((position, i) => ({id: 's' + i, position, neighbors: []}));
  const link = (a, b) => { st[a].neighbors.push(b); st[b].neighbors.push(a); };
  link(0, 1); link(1, 2); link(2, 3); link(3, 4); link(4, 5); link(2, 6); link(0, 8);
  const route = X.routeDistances(st, 0);
  assert.equal(route[0], 0); assert.equal(route[3], 9); assert.ok(Math.abs(route[6] - 10) < 1e-12); assert.equal(route[7], Infinity, 'unconnected');
  const o = [0, 5.6, 0], fwd = [0, 0, -1], opts = {current: 0, floorY: 4.5, refY: 6, route};
  const dirTo = p => { const d = p.map((v, k) => v - o[k]), n = Math.hypot(...d); return d.map(v => v / n); };
  // a level ray down the corridor ("I want to go over there") picks a far station, not the next one
  const a = X.stationTarget(st, o, fwd, opts);
  assert.equal(a.ok, true); assert.equal(a.method, 'cone'); assert.ok(a.index === 3 || a.index === 4, 'far station, got ' + a.index);
  assert.equal(a.point[1], 4.5, 'marker on the assumed floor'); assert.ok(a.distance >= 9);
  // aiming at a station's camera centre selects exactly it, near or far
  for (const k of [1, 2, 3, 4]) assert.equal(X.stationTarget(st, o, dirTo(st[k].position.map((v, j) => v + (j === 0 ? .25 : 0))), opts).index, k, 'aimed at ' + k);
  // pointing at the floor 9 m ahead picks the station above that spot
  const f = X.stationTarget(st, o, dirTo([0.3, 4.5, -9.2]), opts);
  assert.deepEqual([f.ok, f.index, f.method], [true, 3, 'floor']); assert.ok(f.floorPoint);
  // beyond 15 m: never; 20 m station is not a candidate even straight on
  assert.notEqual(X.stationTarget(st, o, dirTo([0, 5.6, -20]), opts).index, 5);
  // the side room (4,6,-6): 46° off the corridor axis is outside the 30° cone; pointed at directly it is chosen
  const side = X.stationTarget(st, o, dirTo([4, 5.6, -6]), opts); assert.equal(side.index, 6);
  assert.notEqual(X.stationTarget(st, o, fwd, {...opts, coneDeg: 10}).index, 6);
  // station on another floor (3.5 m higher) and unconnected stations are ignored
  assert.notEqual(X.stationTarget(st, o, dirTo([0, 9.5, -6]), opts).index, 7);
  // detour: two stations at the same angle; the one 20 m away by the recorded route (behind a wall) loses to the on-route one
  const st2 = [{position: [0, 6, 0], neighbors: [2]}, {position: [-.5, 6, -6], neighbors: []}, {position: [.5, 6, -6], neighbors: [0]}];
  assert.equal(X.stationTarget(st2, [0, 6, 0], [0, 0, -1], {current: 0}).index, 1, 'without a route: tie, first wins');
  assert.equal(X.stationTarget(st2, [0, 6, 0], [0, 0, -1], {current: 0, route: [0, 20, Math.hypot(.5, 6)]}).index, 2, 'route detour penalised');
  assert.equal(X.stationTarget(st2, [0, 6, 0], [0, 0, -1], {current: 0, route: X.routeDistances(st2, 0)}).index, 2, 'unconnected station skipped');
  // pointing at your own feet, straight up, or into empty space: explained refusals
  assert.match(X.stationTarget(st, o, dirTo([0.2, 4.5, -.4]), opts).reason, /You are here/);
  assert.match(X.stationTarget(st, o, [0, 1, 0], opts).reason, /Point toward/);
  assert.match(X.stationTarget(st, o, [-1, 0, 0], {...opts, coneDeg: 20}).reason, /No captured position within 20° and 15 m/);
  // Gaussian fallback: zone indices only, distance reported from the teleport landing
  const z = X.stationTarget(st, o, fwd, {...opts, current: -1, indices: [2, 3], from: [0, 6, -1]});
  assert.equal(z.index, 3); assert.ok(Math.abs(z.distance - 8) < 1e-12);
  // arc: starts at the controller, ends at the target, apex above both
  const arc = X.arcPoints([0, 1, 0], [0, 0, -6], 24);
  assert.equal(arc.length, 24); near(arc[0], [0, 1, 0]); near(arc[23], [0, 0, -6]); assert.ok(Math.max(...arc.map(p => p[1])) > 1);
  assert.equal(X.targetLabel({...a, kind: 'station', distance: 3}, 'Capture 2'), 'Capture 2 · 3.0 m');
  assert.equal(X.targetLabel({...f, kind: 'station'}, 'Capture 4'), 'Capture 4 · 9.0 m · floor');
  assert.equal(X.targetLabel({ok: true, kind: 'point', distance: 2.149}), 'Teleport · 2.1 m');
  assert.match(X.targetLabel({ok: false, reason: 'Point toward a captured position'}), /Point toward/);
});

test('point-and-go on the real May 6 manifest: from the default station every far station in view is reachable by pointing', () => {
  const m = MANIFESTS.may, s = m.stations, i0 = s.findIndex(x => x.id === m.defaultStation), here = s[i0].position, route = X.routeDistances(s, i0);
  assert.ok(route.filter(Number.isFinite).length > 50, 'station graph connected');
  const o = [here[0], here[1] - .4, here[2]];
  let tried = 0, hit = 0, far = 0;
  for (let j = 0; j < s.length; j++) {
    const p = s[j].position, dh = Math.hypot(p[0] - here[0], p[2] - here[2]);
    if (j === i0 || dh < 1 || dh > 15 || Math.abs(p[1] - here[1]) > 1.5 || !Number.isFinite(route[j]) || route[j] > 1.5 * dh + 3) continue;
    tried++;
    const d = [p[0] - o[0], 0, p[2] - o[2]].map((v, _, a) => v / Math.hypot(a[0], a[2]));
    const t = X.stationTarget(s, o, d, {current: i0, floorY: here[1] - 1.5, refY: here[1], route});
    if (t.ok && t.index === j) { hit++; if (dh > 6) far++; }
  }
  assert.ok(tried > 5, 'candidates ' + tried);
  assert.ok(hit / tried > .6, `pointing straight at a station selects it: ${hit}/${tried}`);
  assert.ok(far >= 1, 'at least one station > 6 m away is reachable in one jump (the old stick only stepped ≤ 5.5 m to a neighbour)');
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
  // 2026-10-22 controls: two flashlight cones in the shader, laser + reticle, haptics, point-and-go, hover-only clicks
  assert.ok(html.includes('if(cone2On>.5)w=max(w,smoothstep(coneCos-coneSoft,coneCos,dot(normalize(vWorld-cone2Origin),cone2Dir)));'));
  assert.ok(html.includes('gp.hapticActuators?.[0]') && html.includes('X.stationTarget(stations,') && html.includes('X.controllerRoles(') && html.includes('X.aimUpdate(x,y)'));
  assert.ok(html.includes("if(h&&h.panel){if(h.button>=0){"), 'trigger acts on the highlighted button only');
  assert.ok(!/state\.snap\b|menuLabels|X\.menuHit|X\.MENU\b/.test(html), 'old 6x2 menu removed');
  assert.ok(html.includes('opacity:{lens:X.DEFAULT_LENS_OPACITY,all:X.DEFAULT_ALL_OPACITY}'));
  assert.ok(/\(needs blending\)\n for\(const m of materials\.values\(\)\)m\.transparent=!opaque;/.test(html), 'material transparency loop is code, not part of a comment');
});

/* ── Gaussian scene mode (2026-10-19) ── */
const MAY_G = json('scan-assets/gaussian/2026-05-06/viewer.json');
const OCT_G_PATH = 'work/gaussian/2026-10-18/l1-a/20261019T074640Z/package/viewer.json';

test('Gaussian manifest: frame/status checks, mobile file in XR, full on desktop, SH0 in XR, budgets', () => {
  const xr = X.gaussianAsset(MAY_G, {xr: true}), desk = X.gaussianAsset(MAY_G, {xr: false});
  assert.deepEqual([xr.ok, xr.file, xr.count, xr.mobile, xr.shDegree], [true, 'mobile.ply', 350000, true, 0]);
  assert.deepEqual([desk.ok, desk.file, desk.count, desk.mobile, desk.shDegree], [true, 'trained.ksplat', 1000000, false, 2]);
  assert.equal(X.gaussianAsset(MAY_G, {xr: false, prefer: 'mobile'}).file, 'mobile.ply', '?splat=mobile on desktop (smoke test)');
  assert.equal(X.gaussianAsset(MAY_G, {xr: true, prefer: 'full'}).file, 'trained.ksplat', 'full file in XR only when forced, within the 1M headset budget');
  assert.equal(X.gaussianAsset({...MAY_G, splatCount: 2e6}, {xr: true, prefer: 'full'}).ok, false, 'headset budget 1M');
  assert.equal(X.gaussianAsset({...MAY_G, frame: 'bim'}).ok, false);
  assert.equal(X.gaussianAsset({...MAY_G, status: 'draft'}).ok, false);
  assert.equal(X.gaussianAsset({...MAY_G, capture: undefined}).ok, false);
  for (const file of ['../trained.ksplat', 'sub/x.ply', '.hidden.ply', 'x.glb', 'https://evil.example/x.ply']) assert.equal(X.gaussianAsset({...MAY_G, file}).ok, false, file);
  assert.equal(MAY_G.capture, '2026-05-06'); assert.equal(X.PUBLISHED_GAUSSIANS['2026-05-06'], 'scan-assets/gaussian/2026-05-06/viewer.json');
  if (fs.existsSync(path.join(root, OCT_G_PATH))) {   // local, unpublished Oct 18 zone l1-a package (ignored work/)
    const oct = json(OCT_G_PATH), a = X.gaussianAsset(oct, {xr: true});
    assert.deepEqual([a.ok, a.file, oct.capture, oct.zone.id], [true, 'mobile.ply', '2026-10-18', 'l1-a']);
  }
});

test('?gaussian= override: dev hosts only (loopback + RFC1918), never the public host; no traversal or absolute paths', () => {
  for (const h of ['localhost', '127.0.0.1', '[::1]', '::1', 'app.localhost', '192.168.68.53', '10.0.0.4', '172.16.0.1', '172.31.255.254']) assert.ok(X.isDevHost(h), h);
  for (const h of ['doe2park.github.io', 'github.io', '8.8.8.8', '172.32.0.1', '172.15.0.1', '192.169.1.1', '192.168.1.1.evil.example', '0.0.0.0', '256.1.1.1', '', null, undefined]) assert.equal(X.isDevHost(h), false, String(h));
  assert.equal(X.gaussianOverride('192.168.68.53', OCT_G_PATH), OCT_G_PATH);
  assert.equal(X.gaussianOverride('127.0.0.1', 'scan-assets/gaussian/2026-05-06/viewer.json'), 'scan-assets/gaussian/2026-05-06/viewer.json');
  assert.equal(X.gaussianOverride('doe2park.github.io', OCT_G_PATH), null, 'public GitHub Pages host');
  for (const v of ['../secret.json', 'work/../../etc/x.json', 'work/gaussian/..%2f/x.json', '/abs/viewer.json', '//evil.example/x.json', 'https://evil.example/x.json',
    'work/.hidden/viewer.json', '.git/config.json', 'work//viewer.json', 'viewer.js', 'a\\b.json', 'a b.json', '', null, 'x'.repeat(400) + '.json']) assert.equal(X.gaussianOverride('localhost', v), null, String(v));
  // the page wires exactly this helper and never trusts the raw parameter
  const html = read('scan-xr.html');
  assert.ok(html.includes("X.gaussianOverride(location.hostname,q.get('gaussian'))") && html.includes("if(url.origin!==location.origin)throw Error('Use a same-origin Gaussian manifest')"));
});

test('scene mode toggling: May published, Sep none (stays Photo with a reason), Oct only via a local override', () => {
  assert.equal(X.sceneRequest('gaussian'), 'gaussian'); assert.equal(X.sceneRequest('GAUSSIAN'), 'photo'); assert.equal(X.sceneRequest(null), 'photo');
  assert.equal(X.toggleScene('photo'), 'gaussian'); assert.equal(X.toggleScene('gaussian'), 'photo');
  const may = X.gaussianFor('2026-05-06', null), sep = X.gaussianFor('2026-09-17', null), oct = X.gaussianFor('2026-10-18', null);
  assert.deepEqual(may, {path: 'scan-assets/gaussian/2026-05-06/viewer.json', local: false}); assert.equal(sep, null); assert.equal(oct, null);
  const ov = {path: OCT_G_PATH, capture: '2026-10-18'};
  assert.deepEqual(X.gaussianFor('2026-10-18', ov), {path: OCT_G_PATH, local: true});
  assert.deepEqual(X.gaussianFor('2026-05-06', ov), may, 'an Oct override never replaces May');
  assert.deepEqual(X.gaussianFor('2026-05-06', {path: 'x/viewer.json', capture: '2026-05-06'}), {path: 'x/viewer.json', local: true});
  assert.deepEqual(X.resolveScene('gaussian', 'May 6, 2026', may), {scene: 'gaussian', note: null});
  const r = X.resolveScene('gaussian', 'Sep 17, 2026', sep);
  assert.equal(r.scene, 'photo'); assert.match(r.note, /No Gaussian scene for Sep 17, 2026 · staying in Photo/);
  assert.deepEqual(X.resolveScene('photo', 'May 6, 2026', may), {scene: 'photo', note: null});
});

test('Gaussian labels: date, zone, experimental appearance not surveyed, provisional for Oct, local preview', () => {
  const may = X.gaussianLabel(MAY_G, X.captureConfig('2026-05-06'));
  assert.equal(may, 'Gaussian · May 6, 2026 · whole capture · experimental appearance, not surveyed');
  const oct = X.gaussianLabel({capture: '2026-10-18', zone: {id: 'l1-a', name: 'Zone A'}}, X.captureConfig('2026-10-18'), {local: true});
  assert.equal(oct, 'Gaussian · Oct 18, 2026 · zone l1-a (Zone A) · experimental appearance, not surveyed · provisional alignment · local preview, unpublished');
  const st = [{id: 'a'}, {id: 'b'}, {id: 'c'}];
  assert.deepEqual(X.gaussianStations({zone: {stations: ['c', 'a']}}, st), [0, 2]); assert.deepEqual(X.gaussianStations(MAY_G, st), [0, 1, 2]);
});

test('teleport: floor-plane hit below the eye, distance / station / zone limits, landing keeps eye height', () => {
  const eye = [0, 6, 0], down = d => { const a = d * Math.PI / 180; return [0, -Math.sin(a), -Math.cos(a)]; };
  near(X.floorHit(eye, [0, -1, 0], 4.5), [0, 4.5, 0]);
  const h = X.floorHit(eye, down(30), 4.5); near(h, [0, 4.5, -1.5 / Math.tan(Math.PI / 6)], 1e-9);
  assert.equal(X.floorHit(eye, [0, 0, -1], 4.5), null, 'horizontal ray');
  assert.equal(X.floorHit(eye, [0, .2, -1], 4.5), null, 'upward ray');
  assert.equal(X.floorHit(eye, down(5), 4.5, 8), null, 'beyond 8 m');
  assert.equal(X.floorHit([0, 4, 0], [0, -1, 0], 4.5), null, 'floor above the controller');
  const stations = [{position: [0, 6, 0]}, {position: [0, 6, -4]}, {position: [20, 6, 0]}];
  const t = X.teleportTarget(eye, down(30), {viewY: 6, eyeHeight: 1.5, stations});
  assert.equal(t.ok, true); near(t.landing, [0, 6, -2.598076211353316], 1e-9); assert.equal(t.nearest, 1);
  assert.match(X.teleportTarget(eye, [0, 0, -1], {viewY: 6, stations}).reason, /Point at the floor/);
  const far = X.teleportTarget([12, 6, 0], down(25), {viewY: 6, stations, stationRadius: 2});
  assert.equal(far.ok, false); assert.ok(far.point); assert.match(far.reason, /from any captured position/);
  const zone = {min: [-1, 0, -1], max: [1, 9, 1]};
  assert.match(X.teleportTarget(eye, down(30), {viewY: 6, stations, bounds: zone}).reason, /Outside the trained Gaussian zone/);
  assert.equal(X.teleportTarget(eye, down(30), {viewY: 6, stations, bounds: zone, boundsPad: 1.7}).ok, true, 'zone padding');
  assert.equal(X.teleportTarget(eye, down(30), {viewY: 6, stations, indices: [2], stationRadius: 6}).ok, false, 'only zone stations count');
  // real May manifest: from the default station, 35° down in every heading lands on the floor near the route
  const m = MANIFESTS.may, i = m.stations.findIndex(s => s.id === m.defaultStation), s = m.stations[i];
  let ok = 0;
  for (let k = 0; k < 8; k++) { const a = k * Math.PI / 4, d = [Math.sin(a) * Math.cos(.61), -Math.sin(.61), Math.cos(a) * Math.cos(.61)], r = X.teleportTarget(s.position, d, {viewY: s.position[1], stations: m.stations}); if (r.ok) { ok++; assert.equal(r.landing[1], s.position[1]); } }
  assert.ok(ok >= 6, 'teleport targets near a recorded station: ' + ok);
});

test('scan-xr.html Gaussian wiring: pinned GaussianSplats3D 0.4.7 DropInViewer, worker sort without SharedArrayBuffer, SH0/mobile in XR, no photo sphere', () => {
  const html = read('scan-xr.html');
  assert.ok(html.includes('"@mkkellogg/gaussian-splats-3d":"https://cdn.jsdelivr.net/npm/@mkkellogg/gaussian-splats-3d@0.4.7/build/gaussian-splats-3d.module.js"'));
  assert.ok(html.includes('new GS.DropInViewer({sharedMemoryForWorkers:false,gpuAcceleratedSort:false'));
  assert.ok(html.includes('sphericalHarmonicsDegree:a.shDegree') && html.includes('X.gaussianAsset(m,{xr:xrSupported||renderer.xr.isPresenting,prefer:SPLAT_PREF})'));
  assert.ok(html.includes('setActiveSphericalHarmonicsDegrees(0)'), 'SH0 once in XR');
  assert.ok(html.includes('sphere.visible=false') && html.includes('setFramebufferScaleFactor(P.xrScale)') && html.includes('setFoveation(P.foveation)'));
  assert.ok(html.includes("const opaque=state.mode==='lens'&&o>=.99&&gauss.scene!=='gaussian'"), 'services stay after the transparent splat pass');
  assert.ok(!/new SharedArrayBuffer|crossOriginIsolated|sharedMemoryForWorkers:true/.test(html), "no SharedArrayBuffer / COOP-COEP requirement");
  // the pinned package really exports DropInViewer with the API used here (local copy in tools/node_modules)
  const mod = path.join(root, 'tools/node_modules/@mkkellogg/gaussian-splats-3d');
  if (fs.existsSync(mod)) {
    assert.equal(JSON.parse(fs.readFileSync(path.join(mod, 'package.json'), 'utf8')).version, '0.4.7');
    const src = fs.readFileSync(path.join(mod, 'build/gaussian-splats-3d.module.js'), 'utf8');
    for (const k of ['class DropInViewer extends THREE.Group', 'addSplatScene(path, options = {})', 'setActiveSphericalHarmonicsDegrees(', 'static onBeforeRender(viewer, renderer, threeScene, camera)', 'runSplatSort = function']) assert.ok(src.includes(k), k);
    assert.match(src, /export \{[^}]*\bDropInViewer\b/);
  }
});
