/* scan-compare.html as-built panel logic (pure block between markers) and the BIM-pane message contract. */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const src = fs.readFileSync(path.join(__dirname, '../scan-compare.html'), 'utf8'), bim = fs.readFileSync(path.join(__dirname, '../scan-bim.html'), 'utf8');
const A = require('../twin/as-built.js');
function logic() { const m = src.match(/\/\* AS-BUILT UI LOGIC[^*]*\*\/([\s\S]*?)\/\* END AS-BUILT UI LOGIC \*\//); assert.ok(m); const c = {URLSearchParams, Math, String, Number}; vm.createContext(c); vm.runInContext(m[1], c); return c; }

test('keyboard nudges: 1 cm / 1°, Shift 5 cm / 5°, unrelated keys ignored', () => {
  const c = logic(), k = (key, shiftKey = false) => JSON.parse(JSON.stringify(c.nudgeForKey({key, shiftKey})));
  assert.deepEqual(k('ArrowRight'), {dx: .01}); assert.deepEqual(k('ArrowLeft', true), {dx: -.05});
  assert.deepEqual(k('ArrowUp'), {dz: -.01}); assert.deepEqual(k('PageUp'), {dy: .01}); assert.deepEqual(k('PageDown', true), {dy: -.05});
  assert.deepEqual(k(']'), {dyaw: 1}); assert.deepEqual(k('{', true), {dyaw: -5});
  assert.equal(c.nudgeForKey({key: 'w'}), null); assert.equal(c.nudgeForKey({key: 'Enter'}), null);
});

test('mode defaults to Design (BIM); ?asbuilt=1 opts in', () => {
  const c = logic(); assert.equal(c.parseAsBuiltMode(''), 'design'); assert.equal(c.parseAsBuiltMode('?asbuilt=1'), 'asbuilt'); assert.equal(c.parseAsBuiltMode('?asbuilt=yes'), 'design');
});

test('evidence records capture date, scan mode and the 1-based station label; produces a valid record', () => {
  const c = logic();
  const ev = JSON.parse(JSON.stringify(c.evidenceFor({date: '2026-09-17', display: 'photo', station: 56, registration: 'scan-assets/captures/2026-09-17/registration.json'})));
  assert.deepEqual(ev, {captureDate: '2026-09-17', scanMode: 'photo', stationIndex: 56, stationLabel: '57', registration: 'scan-assets/captures/2026-09-17/registration.json'});
  assert.equal(c.evidenceFor({date: '2026-05-06', display: 'mesh', station: 89}).stationIndex, null, 'a mesh view has no station');
  const rec = {...A.nudge(A.createAdjustment({id: '171361', layer: 'lighting', author: 'YC'}), {dx: .1}), evidence: ev};
  assert.deepEqual(A.validateAdjustment(rec), []);
  assert.ok(c.validInitials('yc')); assert.ok(!c.validInitials('Y')); assert.ok(!c.validInitials('Y.C'));
  assert.match(c.readoutText(rec), /x 10\.0 · y 0\.0 · z 0\.0 cm · \|Δ\| 10\.0 cm · yaw 0\.0°/);
});

test('message contract: the BIM pane validates before applying and answers with applied/pending/pivots', () => {
  assert.match(bim, /AsBuilt\.validateDocument\(\{\.\.\.AsBuilt\.emptyDocument\(\),adjustments:list\}\)/);
  assert.match(bim, /type:'grimes-asbuilt-applied',mode:asBuilt\.mode,applied:res\.applied,pending:res\.pending,pivots:res\.pivots/);
  assert.match(bim, /e\.source!==window\.parent/);
  assert.match(src, /e\.source!==frames\[1\]\.contentWindow/);
  assert.match(bim, /queueMicrotask\(asBuiltLayerLoaded\)/, 'late layers receive their adjustments');
  assert.match(bim, /keepInWalk/, 'outlines are not hidden in walk/photo mode');
  const tail = bim.slice(bim.indexOf('OVERLAY LENS PICK + AS-BUILT'));
  assert.doesNotMatch(tail.slice(0, tail.indexOf("document.getElementById('pauseScanLayers')")), /equipMeshes\.push/, 'outlines are never added to the pickable element meshes');
});
