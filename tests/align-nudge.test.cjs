/* Overlay "Align" tool: registration-core nudge/pair maths, the lens-pick point contract and the
   scan-compare.html ALIGN NUDGE block (pure, between markers). Synthetic numbers only. */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const RC = require('../registration-core.js'), EC = require('../twin/element-cards.js');
const src = fs.readFileSync(path.join(__dirname, '../scan-compare.html'), 'utf8');
const bim = fs.readFileSync(path.join(__dirname, '../scan-bim.html'), 'utf8'), photo = fs.readFileSync(path.join(__dirname, '../scan-photo.html'), 'utf8');
const plain = v => JSON.parse(JSON.stringify(v));
const near = (a, b, eps = 1e-9, msg) => { assert.equal(a.length, b.length); a.forEach((v, k) => assert.ok(Math.abs(v - b[k]) < eps, (msg || '') + ' ' + a + ' vs ' + b)); };
function block() {
  const m = src.match(/\/\* ALIGN NUDGE[^*]*\*\/([\s\S]*?)\/\* END ALIGN NUDGE \*\//); assert.ok(m, 'ALIGN NUDGE block exists');
  const c = {Math, JSON, Number, String, Array, Object, RegistrationCore: RC}; vm.createContext(c); vm.runInContext(m[1], c);
  c.get = name => vm.runInContext(name, c); return c;
}
/* scan-compare convert(): camera pose scan -> BIM (position via apply, quaternion premultiplied by rotY(theta)) */
const qmul = (a, b) => [a[3]*b[0]+a[0]*b[3]+a[1]*b[2]-a[2]*b[1], a[3]*b[1]-a[0]*b[2]+a[1]*b[3]+a[2]*b[0], a[3]*b[2]+a[0]*b[1]-a[1]*b[0]+a[2]*b[3], a[3]*b[3]-a[0]*b[0]-a[1]*b[1]-a[2]*b[2]];
const rotYq = deg => { const h = deg * Math.PI / 360; return [0, Math.sin(h), 0, Math.cos(h)]; };
const qrot = (q, v) => { const p = qmul(qmul(q, [...v, 0]), [-q[0], -q[1], -q[2], q[3]]); return p.slice(0, 3); };
const bimCamera = (reg, scanPos, scanQ) => ({position: RC.apply(reg, scanPos), quaternion: qmul(rotYq(reg.rotationYDegrees), scanQ)});
const toCamera = (cam, P) => qrot([-cam.quaternion[0], -cam.quaternion[1], -cam.quaternion[2], cam.quaternion[3]], [P[0]-cam.position[0], P[1]-cam.position[1], P[2]-cam.position[2]]);
const base = {rotationYDegrees: 20, translation: [-3, .5, 4], stationHeadingOffsetsDegrees: {a: 1.25}};
const scanPos = [2, 1.5, 3], scanQ = qmul(rotYq(-35), [Math.sin(-.1), 0, 0, Math.cos(-.1)]);   // yawed and slightly pitched

test('nudgeRegistration: identity nudge returns an equal copy with scale 1', () => {
  const r = RC.nudgeRegistration(base, {moveBim: [0, 0, 0], yawBimDeg: 0, pivot: [7, 1, -2]});
  assert.notEqual(r, base); assert.equal(r.scale, 1); assert.equal(r.rotationYDegrees, 20); near(r.translation, base.translation, 1e-12);
  assert.deepEqual(r.stationHeadingOffsetsDegrees, {a: 1.25}, 'other fields are carried'); assert.deepEqual(base.translation, [-3, .5, 4], 'input untouched');
  assert.throws(() => RC.nudgeRegistration(base, {moveBim: [0, NaN, 0]}));
});

test('sign convention: moving the BIM along camera-right shifts a point straight ahead to the right on screen', () => {
  const c = block(), cam = bimCamera(base, scanPos, scanQ), fwd = qrot(cam.quaternion, [0, 0, -1]);
  const P = cam.position.map((v, k) => v + 5 * fwd[k]);
  near(toCamera(cam, P), [0, 0, -5], 1e-9, 'P starts dead ahead');
  const v = plain(c.alignMove('right', .2, c.alignBasis(cam.quaternion)));
  const moved = bimCamera(RC.nudgeRegistration(base, {moveBim: v, pivot: cam.position}), scanPos, scanQ), q = toCamera(moved, P);
  assert.ok(q[0] > .19, 'screen-right (camera +x): ' + q); near(moved.position, cam.position.map((x, k) => x - v[k]), 1e-9, 'BIM camera moved by -v');
  near(moved.quaternion, cam.quaternion, 1e-12, 'pure move keeps the view direction');
  const up = bimCamera(RC.nudgeRegistration(base, {moveBim: plain(c.alignMove('up', .05, c.alignBasis(cam.quaternion))), pivot: cam.position}), scanPos, scanQ);
  assert.ok(toCamera(up, P)[1] > .04, 'Up raises the BIM on screen');
  const away = bimCamera(RC.nudgeRegistration(base, {moveBim: plain(c.alignMove('forward', .2, c.alignBasis(cam.quaternion))), pivot: cam.position}), scanPos, scanQ);
  assert.ok(toCamera(away, P)[2] < -5.1, 'Away pushes the BIM further from the camera');
});

test('sign convention: +yaw turns the BIM counter-clockwise from above about the camera (ahead point moves left)', () => {
  const level = rotYq(-35), cam = bimCamera(base, scanPos, level), fwd = qrot(cam.quaternion, [0, 0, -1]), P = cam.position.map((v, k) => v + 5 * fwd[k]);
  const r = RC.nudgeRegistration(base, {yawBimDeg: 2, pivot: cam.position}), moved = bimCamera(r, scanPos, level), q = toCamera(moved, P);
  assert.ok(Math.abs(r.rotationYDegrees - 18) < 1e-9, 'theta\' = theta - phi');
  near(q, [-5 * Math.sin(2 * Math.PI / 180), 0, -5 * Math.cos(2 * Math.PI / 180)], 1e-9);
});

test('pivot invariance: the pivot (camera position) maps to itself under a pure yaw', () => {
  const c = RC.apply(base, scanPos), r = RC.nudgeRegistration(base, {yawBimDeg: 7.3, pivot: c});
  near(RC.apply(r, scanPos), c, 1e-9);
  const other = [10, 2, -6]; assert.ok(Math.hypot(...RC.apply(r, other).map((v, k) => v - RC.apply(base, other)[k])) > .1, 'other points do move');
});

test('composition: sequential nudges equal composing the visual motions', () => {
  const n1 = {moveBim: [.2, 0, -.05], yawBimDeg: .5, pivot: [1, 1.5, 2]}, n2 = {moveBim: [-.01, .03, .1], yawBimDeg: -1.25, pivot: [4, 1.5, -3]};
  const f = (n, q) => { const d = RC.rotateY([q[0]-n.pivot[0], q[1]-n.pivot[1], q[2]-n.pivot[2]], -n.yawBimDeg); return d.map((v, k) => v + n.pivot[k] - n.moveBim[k]); };
  const r = RC.nudgeRegistration(RC.nudgeRegistration(base, n1), n2);
  for (const p of [[0, 0, 0], scanPos, [12, 4, -7]]) near(RC.apply(r, p), f(n2, f(n1, RC.apply(base, p))), 1e-8);
  const back = RC.nudgeRegistration(RC.nudgeRegistration(base, {moveBim: [.2, 0, 0]}), {moveBim: [-.2, 0, 0]});
  assert.deepEqual(back.translation, base.translation, 'float noise cancelled on an undo');
});

test('fitFromElementPairs: 1 pair is an exact translation that keeps yaw', () => {
  const pair = {scan: [3, 2, 1], bim: [-1, 2.7, 8]}, r = RC.fitFromElementPairs(base, [pair]);
  assert.equal(r.mode, 'translation'); assert.equal(r.reg.rotationYDegrees, 20); near(RC.apply(r.reg, pair.scan), pair.bim, 1e-9); assert.ok(r.residualsMetres[0] < 1e-9);
  assert.throws(() => RC.fitFromElementPairs(base, []));
});

test('fitFromElementPairs: 2 spread pairs recover a known yaw + translation; 4+ use RANSAC', () => {
  const truth = {rotationYDegrees: -12.5, translation: [4, -.3, 2]}, mk = p => ({scan: p, bim: RC.apply(truth, p)});
  const r = RC.fitFromElementPairs(base, [mk([0, 3, 0]), mk([4, 3.5, 1])]);
  assert.equal(r.mode, 'yaw+translation'); assert.ok(Math.abs(r.reg.rotationYDegrees + 12.5) < 1e-9); near(r.reg.translation, truth.translation, 1e-9);
  const pairs = [mk([0, 3, 0]), mk([4, 3, 1]), mk([1, 3, 6]), mk([7, 3, 5]), {scan: [3, 3, 3], bim: [40, 0, 40]}];
  const rr = RC.fitFromElementPairs(base, pairs); assert.equal(rr.mode, 'yaw+translation'); assert.deepEqual([...rr.inliers], [0, 1, 2, 3]); assert.ok(Math.abs(rr.reg.rotationYDegrees + 12.5) < 1e-9);
});

test('fitFromElementPairs: spread guard falls back to translation only (no yaw from pairs < 1 m apart)', () => {
  const truth = {rotationYDegrees: 5, translation: [1, 0, 1]}, mk = p => ({scan: p, bim: RC.apply(truth, p)});
  const r = RC.fitFromElementPairs(base, [mk([0, 3, 0]), mk([.4, 3, .3])]);
  assert.equal(r.mode, 'translation'); assert.equal(r.reg.rotationYDegrees, 20); assert.match(r.note, /too close/);
  const c = block(); assert.equal(c.alignSolveMode(plain([mk([0, 3, 0]), mk([.4, 3, .3])])), 'translation'); assert.equal(c.alignSolveMode(plain([mk([0, 3, 0]), mk([4, 3, 1])])), 'yaw+translation');
  assert.equal(c.alignSolveMode([]), 'none'); assert.match(c.alignPairsText(plain([mk([0, 3, 0])])), /1 pair · Solve = translation only/);
});

test('manual status is a known candidate status and the filename can never be an accepted one', () => {
  assert.ok(RC.CANDIDATE_STATUSES.includes('manual-nudge-unsurveyed'));
  for (const s of ['landmark-fit-unsurveyed', 'landmark-fit-surveyed-checks', 'icp-refined-unsurveyed']) assert.ok(RC.CANDIDATE_STATUSES.includes(s), 'existing status kept: ' + s);
  assert.equal(RC.suggestFilename('2026-09-17', '2026-10-15', 'manual-nudge'), 'registration-candidates/2026-10-15-manual-nudge.json');
  assert.equal(RC.suggestFilename('2026-09-17', '2026-10-15'), 'registration-candidates/2026-10-15-landmark-fit.json');
  assert.equal(RC.suggestFilename('x', '2026-10-15', '../evil'), 'registration-candidates/2026-10-15-landmark-fit.json');
});

test('lens pick carries an optional BIM-world hit point; old messages without it still parse', () => {
  const tier = {tier: 'NONE', label: 'NO FEED', valueText: '—'}, info = {name: 'Light', type: 'Linear'};
  const withPt = EC.lensPickMessage({seq: 3, x: .5, y: .5, id: '42', layer: 'lighting', info, tier, point: [1.5, 3.25, -7]});
  assert.deepEqual(EC.parseLensPick(withPt, 2).hit.point, [1.5, 3.25, -7]);
  const old = EC.lensPickMessage({seq: 4, x: .5, y: .5, id: '42', layer: 'lighting', info, tier});
  const parsed = EC.parseLensPick(old, 3); assert.ok(parsed.hit); assert.equal('point' in parsed.hit, false);
  for (const bad of [[1, 2], [1, 2, NaN], [1, 2, '3'], 'x', {0: 1, 1: 2, 2: 3}]) {
    const p = EC.parseLensPick({...old, seq: 9, hit: {...old.hit, point: bad}}, 3); assert.ok(p && p.hit, 'still a hit'); assert.equal('point' in p.hit, false, 'bad point dropped: ' + JSON.stringify(bad));
  }
  assert.match(bim, /point:hit\.point\.toArray\(\)/, 'BIM pane sends the world-space raycast point');
});

test('photo pane: pick mode posts a scan-frame ray on a click, not a drag, with a crosshair', () => {
  assert.match(photo, /grimes-photo-pickmode/); assert.match(photo, /cursor=pickMode\?'crosshair'/);
  assert.match(photo, /Math\.hypot\(e\.clientX-drag\.x0,e\.clientY-drag\.y0\)<5/);
  assert.match(photo, /type:'grimes-photo-pick',x,y,direction:d\.toArray\(\),origin:camera\.position\.toArray\(\),station:active/);
});

test('ALIGN block: modification state, honest banner and working registration', () => {
  const c = block(), banner = c.get('ALIGN_BANNER');
  assert.equal(banner, 'Manual alignment preview · not saved · not surveyed');
  assert.doesNotMatch(banner.replace('not surveyed', ''), /accepted|surveyed|verified/i);
  assert.equal(c.alignModified(base, base), false);
  const same = c.alignWorking(base, {rotationYDegrees: 20, translation: [-3, .5, 4]}); assert.equal(same, base, 'unmodified -> the loaded object itself');
  const w = c.alignWorking(base, RC.nudgeRegistration(base, {moveBim: [.2, 0, 0]}));
  assert.equal(c.alignModified(base, w), true); assert.equal(w.status, 'manual-nudge-unsurveyed'); assert.deepEqual(plain(w.stationHeadingOffsetsDegrees), {a: 1.25});
  assert.equal(c.alignStatusLine(true, 'scan-assets/captures/2026-09-17/registration.json'), banner + ' · base 2026-09-17/registration.json'); assert.equal(c.alignStatusLine(false, 'x'), '');
  assert.match(c.alignReadout(base, w), /Δ yaw \+0\.00° · Δt -20\.0 \/ \+0\.0 \/ \+0\.0 cm \(\|20\.0\| cm\)\nθ 20\.000°/);
  assert.match(src, /if\(typeof alignStatusText==='function'\)\{const a=alignStatusText\(\);if\(a\)status\.textContent=a;\}/, 'page status shows the banner while modified');
});

test('ALIGN block: keyboard shortcuts avoid plain WASD/arrows (walking)', () => {
  const c = block(), k = (key, shiftKey = false, extra = {}) => plain(c.alignKeyAction({key, shiftKey, ...extra}));
  assert.equal(c.alignKeyAction({key: 'ArrowRight'}), null); assert.equal(c.alignKeyAction({key: 'w'}), null); assert.equal(c.alignKeyAction({key: 'D', shiftKey: true}), null);
  assert.deepEqual(k('ArrowRight', true), {move: 'right'}); assert.deepEqual(k('ArrowUp', true), {move: 'forward'}); assert.deepEqual(k('PageDown', true), {move: 'down'});
  assert.deepEqual(k(']'), {yaw: .1}); assert.deepEqual(k('{', true), {yaw: -.5}); assert.equal(c.alignKeyAction({key: ']', metaKey: true}), null);
});

test('ALIGN block: photo-click depth keeps the picked BIM point\'s distance from the station', () => {
  const c = block(), bimPt = RC.apply(base, [5, 2, 3]), origin = [2, 1.5, 3];
  const s = plain(c.alignPhotoPoint(bimPt, {origin, direction: [0, 0, -2]}, base, RC.invert));
  near(s, [2, 1.5, 3 - Math.hypot(3, .5, 0)], 1e-9);
  assert.equal(c.alignValidPick({type: 'grimes-photo-pick', x: .5, y: .5, direction: [0, 0, -1], origin}), true);
  for (const bad of [{x: 2}, {direction: [0, 0, 0]}, {origin: [1, 2]}, {type: 'grimes-pointer'}]) assert.equal(c.alignValidPick({type: 'grimes-photo-pick', x: .5, y: .5, direction: [0, 0, -1], origin, ...bad}), false);
});

test('ALIGN block: exported candidate follows the schema, validates and stays honest', () => {
  const c = block(), reg = c.alignWorking(base, RC.nudgeRegistration(base, {moveBim: [0, 0, .05], yawBimDeg: .1, pivot: [1, 1, 1]}));
  const pairs = [{id: 'pair-1', element: {id: '42', layer: 'lighting'}, station: 56, scan: [1, 2, 3], bim: [4, 5, 6]}];
  const out = plain(c.alignCandidate({capture: '2026-09-17', base, basePath: 'scan-assets/captures/2026-09-17/registration.json', reg, solver: 'element pairs', pairs, fit: {mode: 'translation', residualsMetres: [0], note: 'n'}, created: '2026-10-15T00:00:00Z'}));
  assert.equal(out.schema, RC.SCHEMA); assert.equal(out.capture, '2026-09-17'); assert.equal(out.createdAt, '2026-10-15T00:00:00Z'); assert.equal(out.scale, 1);
  assert.equal(out.status, 'manual-nudge-unsurveyed'); assert.equal(out.method.model, 'yaw+translation'); assert.equal(out.method.solver, 'element pairs');
  assert.equal(out.method.base, 'scan-assets/captures/2026-09-17/registration.json'); assert.deepEqual(out.method.baseTranslation, [-3, .5, 4]);
  assert.equal(out.rotationYDegrees, reg.rotationYDegrees); assert.deepEqual(out.translation, plain(reg.translation));
  assert.deepEqual(out.stationHeadingOffsetsDegrees, {a: 1.25}); assert.equal(out.pairs[0].surveyed, false); assert.match(out.scope, /Not surveyed and not the accepted registration/);
  assert.deepEqual(RC.validateRegistration(out, '2026-09-17'), {ok: true}); assert.equal(RC.validateRegistration(out, '2026-05-06').ok, false);
  const noPairs = plain(c.alignCandidate({capture: '2026-05-06', base, basePath: 'b.json', reg, solver: 'manual nudge', pairs: [], created: 'x'}));
  assert.equal('pairs' in noPairs, false); assert.equal(c.alignCandidateFolder('2026-05-06'), 'alignment-analysis/candidates/'); assert.equal(c.alignCandidateFolder('2026-09-17'), 'scan-assets/captures/2026-09-17/registration-candidates/');
});

test('ALIGN block: draft round-trips per capture and base, and storage failures are tolerated', () => {
  const c = block(), reg = RC.nudgeRegistration(base, {moveBim: [.1, 0, 0]}), key = c.alignDraftKey('2026-09-17');
  assert.equal(key, 'grimes-align-nudge-v1:2026-09-17');
  const text = c.alignDraftText({capture: '2026-09-17', basePath: 'b.json', reg, solver: 'manual nudge', pairs: [{scan: [1, 2, 3], bim: [4, 5, 6]}]});
  const d = plain(c.alignRestore(text, '2026-09-17', 'b.json')); assert.deepEqual(d.translation, reg.translation); assert.equal(d.pairs.length, 1);
  assert.equal(c.alignRestore(text, '2026-05-06', 'b.json'), null, 'other capture ignored'); assert.equal(c.alignRestore(text, '2026-09-17', 'other.json'), null, 'changed base ignored');
  for (const bad of [null, '', '{', '{"v":1}', JSON.stringify({v: 1, capture: '2026-09-17', basePath: 'b.json', rotationYDegrees: 'x', translation: [0, 0, 0]})]) assert.equal(c.alignRestore(bad, '2026-09-17', 'b.json'), null);
  const throwing = {getItem() { throw Error('denied'); }, setItem() { throw Error('quota'); }, removeItem() { throw Error('denied'); }};
  for (const ls of [throwing, null, undefined]) { const st = c.alignStore(ls); assert.equal(st.get(key), null); assert.equal(st.set(key, 'x'), false); assert.doesNotThrow(() => st.del(key)); }
  const mem = new Map(), ok = c.alignStore({getItem: k => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v), removeItem: k => mem.delete(k)});
  assert.equal(ok.set(key, text), true); assert.equal(ok.get(key), text); ok.del(key); assert.equal(ok.get(key), null);
});

test('Align UI: overlay-only toggle, honest copy, preview help, and accepted files are never written', () => {
  assert.match(src, /<button id="alignToggle"[^>]*>Align…<\/button>/); assert.match(src, /body:not\(\[data-focus="overlay"\]\) #alignToggle/);
  assert.match(src, /id="alignBadge" hidden>MANUAL ALIGNMENT PREVIEW · not saved · not surveyed/);
  assert.match(src, /preview with scan-compare\.html\?view=overlay&amp;registration=/);
  assert.match(src, /registration=alignWorking\(alBase,next\);[\s\S]*?epoch\+\+;roles\(\);/);
  assert.match(src, /suggestFilename\(capture\.date,created\.slice\(0,10\),'manual-nudge'\)/); assert.match(src, /RegistrationCore\.assertCandidateName\(name\)/);
  assert.doesNotMatch(src, /a\.download='(accepted-)?registration\.json'/);
});
