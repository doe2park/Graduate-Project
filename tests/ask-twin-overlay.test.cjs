/* Ask the twin over the real photo (scan-compare.html?view=overlay&ask=1): pure helpers extracted between the
   ASK OVERLAY LOGIC markers, plus wiring checks on the page, the BIM pane and the panel.   node --test tests/ask-twin-overlay.test.cjs */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const read = f => fs.readFileSync(path.join(__dirname, '..', f), 'utf8');
const src = read('scan-compare.html'), bim = read('scan-bim.html'), panel = read('twin/ask-twin.js');
function logic() {
  const m = src.match(/\/\* ASK OVERLAY LOGIC[^*]*\*\/([\s\S]*?)\/\* END ASK OVERLAY LOGIC \*\//);
  assert.ok(m, 'ask overlay logic block exists');
  const c = {URLSearchParams, Number, Math}; vm.createContext(c); vm.runInContext(m[1], c); return c;
}
test('off unless ?ask=1 exactly', () => {
  const c = logic();
  assert.equal(c.askEnabled('?ask=1'), true);
  for (const s of ['', '?ask=0', '?ask=true', '?ask', '?view=overlay']) assert.equal(c.askEnabled(s), false, s);
});
test('projected answer point -> normalised lens target, null behind the camera or at the edge', () => {
  const c = logic();
  assert.deepEqual(JSON.parse(JSON.stringify(c.askLensPoint({x: 0, y: 0, z: .9}))), {x: .5, y: .5});
  assert.deepEqual(JSON.parse(JSON.stringify(c.askLensPoint({x: .5, y: -.5, z: .5}))), {x: .75, y: .75});
  assert.equal(c.askLensPoint({x: 0, y: 0, z: 1.2}), null);          // behind the camera
  assert.equal(c.askLensPoint({x: .99, y: 0, z: .5}), null);         // at the edge
  assert.equal(c.askLensPoint({x: NaN, y: 0, z: .5}), null);
  assert.equal(c.askLensPoint(null), null);
});
test('box samples: centre first, then along the longest axis inside the box', () => {
  const c = logic(), s = c.askBoxSamples([0, 0, 0, 10, 1, 2], 5);
  assert.equal(s.length, 6); assert.deepEqual([...s[0]], [5, .5, 1]);
  for (const p of s.slice(1)) { assert.ok(p[0] > 0 && p[0] < 10); assert.equal(p[1], .5); assert.equal(p[2], 1); }
});
test('pick point: nearest to the current lens, never under the ask panel', () => {
  const c = logic(), block = {x0: 0, x1: .35, y0: .2, y1: 1};
  const pts = [null, {x: .2, y: .6}, {x: .6, y: .5}, {x: .9, y: .1}];
  assert.deepEqual({...c.askPickPoint(pts, {x: .25, y: .6}, block)}, {x: .6, y: .5});
  assert.deepEqual({...c.askPickPoint(pts, {x: .25, y: .6}, null)}, {x: .2, y: .6});
  assert.equal(c.askPickPoint([{x: .1, y: .5}], {x: .5, y: .5}, block), null);
  assert.equal(c.askPickPoint([], null, null), null);
});
test('turning toward a ceiling element looks higher (room below out of frame); level or lower targets unchanged', () => {
  const c = logic(), d = Math.PI / 180;
  assert.ok(Math.abs(c.askTurnPitch(20 * d, 60) - 44 * d) < 1e-9);
  assert.ok(Math.abs(c.askTurnPitch(70 * d, 60) - 85 * d) < 1e-9);
  assert.equal(c.askTurnPitch(-10 * d, 60), -10 * d);
  assert.equal(c.askTurnPitch(0, 60), 0);
});
test('the Lens holds the answer until the mouse really moves; leaving the photo keeps it', () => {
  const c = logic();
  assert.equal(c.askHoldKeeps({x: .5, y: .5}, {x: .51, y: .5}), true);
  assert.equal(c.askHoldKeeps({x: .5, y: .5}, {x: .7, y: .5}), false);
  assert.equal(c.askHoldKeeps({x: .5, y: .5}, {x: null, y: null}), true);
  assert.equal(c.askHoldKeeps(null, {x: .5, y: .5}), false);
});
test('wiring: BIM pane gets &ask=1 only with ?ask=1, exposes the panel API only then; panel uses focus instead of flying', () => {
  const m = /frames\[1\]\.src=(.+?);\n/.exec(src), frame = q => vm.runInNewContext(m[1], {URLSearchParams, location: {search: q}, view: 'overlay'});
  assert.equal(frame('?view=overlay&ask=1'), 'scan-bim.html?pane=bim&revision=overlay2&overlay=1&ask=1');
  assert.equal(frame('?view=overlay&ask=yes'), 'scan-bim.html?pane=bim&revision=overlay2&overlay=1');
  assert.match(src, /if\(askEnabled\(location\.search\)\)\{/);
  assert.match(bim, /if\(splitPane==='bim'&&new URLSearchParams\(location\.search\)\.get\('ask'\)==='1'\)\{[\s\S]{0,200}window\.twinViewerApi=/);
  assert.match(panel, /\(api\.focus \|\| flyTo\)\(pc\.bbox_m\)/);
  assert.match(panel, /state\.markerAt = pc && !api\.focus/);   // no ring marker over the photo: the Lens is the only circle
  assert.match(panel, /api\.pickHint \|\|/);
});
