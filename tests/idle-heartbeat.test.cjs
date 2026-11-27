/* scan-bim.html render loop: 250 ms heartbeat while active (input/messages within 5 s, or loading), 2 s when fully idle.
   Same harness as walk-loading.test.cjs: the loop source runs in a vm context with stub renderer/camera. */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
function setup({loading = false} = {}) {
  let cb, renders = 0; const listeners = {}, now = {t: 0};
  const ctx = {splitPane: null, walkMode: false, layerState: {equipment: {loading}}, interiorState: {loading: false}, mobileMq: {matches: false}, linkedPose: null, lastSyncAt: 0, Date,
    performance: {now: () => now.t}, window: {addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); }},
    controls: {update() {}}, updateWalk() {}, publishScanPose() {}, scene: {}, camera: {updateMatrixWorld() {}, matrixWorld: {elements: new Array(16).fill(0)}, projectionMatrix: {elements: new Array(16).fill(0)}},
    renderer: {setAnimationLoop(fn) { cb = fn; }, render() { renders++; }, domElement: {width: 1, height: 1, addEventListener: (type, fn) => { (listeners['canvas:' + type] ||= []).push(fn); }}}};
  vm.createContext(ctx);
  const html = fs.readFileSync('scan-bim.html', 'utf8'), at = html.lastIndexOf('let _lastT = 0');
  vm.runInContext(html.slice(at, html.indexOf('</script>', at)), ctx);
  return {frame: t => { now.t = t; cb(t); }, count: () => renders, fire: type => { for (const fn of listeners[type] || []) fn(); }, listeners, ctx};
}
test('pointer motion and wheel kick only from the canvas; clicks, input, keys and messages from the window', () => {
  const s = setup();
  for (const type of ['pointermove', 'wheel']) { assert.ok(s.listeners['canvas:' + type], 'canvas ' + type); assert.ok(!s.listeners[type], 'not window ' + type); }
  for (const type of ['pointerdown', 'pointerup', 'click', 'input', 'change', 'keydown', 'keyup', 'message', 'resize', 'focus']) assert.ok(s.listeners[type], 'window ' + type);
});
test('idle page draws every 2 s; any kick restores the 250 ms heartbeat for 5 s', () => {
  const s = setup();
  s.frame(10000); assert.equal(s.count(), 1, 'first frame');
  s.frame(10300); s.frame(11000); assert.equal(s.count(), 1, 'no 250 ms redraws when idle');
  s.frame(12000); assert.equal(s.count(), 2, '2 s idle heartbeat');
  s.fire('message'); s.frame(12100); assert.equal(s.count(), 3, 'kick draws at once');
  s.frame(12300); assert.equal(s.count(), 3, 'kick window over, 200 ms since the last draw'); s.frame(12400); assert.equal(s.count(), 4, 'active: 250 ms heartbeat');
  s.frame(16900); assert.equal(s.count(), 5, 'still active just before 5 s'); s.frame(17300); assert.equal(s.count(), 5, 'idle again after 5 s'); s.frame(18950); assert.equal(s.count(), 6, '2 s after the last draw');
});
test('a finished load keeps the fast heartbeat for 5 s', () => {
  const s = setup({loading: true});
  s.frame(10000); s.frame(11000); assert.equal(s.count(), 0, 'non-Walk loading does not render');
  s.ctx.layerState.equipment.loading = false; s.frame(11016); assert.equal(s.count(), 1);
  s.frame(11300); assert.equal(s.count(), 2, 'fast heartbeat right after loading'); s.frame(15000); assert.equal(s.count(), 3);
});
