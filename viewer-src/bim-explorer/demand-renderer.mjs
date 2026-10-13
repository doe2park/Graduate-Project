/** Preserve every object. Only raster resolution changes during navigation. */
export function createDemandRenderer({renderer, scene, camera, controls, blocked = () => false, onFrame = () => {}, pixelRatio = Math.min(globalThis.devicePixelRatio || 1, 1.5)}) {
  let pending = false, moving = false, dragging = false, settleTimer, disposed = false, frames = 0;
  const stats = {frames: 0, moving: false, pixelRatio, calls: 0, triangles: 0, cpuSubmitMs: 0};
  const setRatio = ratio => { if (renderer.getPixelRatio() !== ratio) renderer.setPixelRatio(ratio); stats.pixelRatio = ratio; };
  function settle() { clearTimeout(settleTimer); settleTimer = setTimeout(() => { if (dragging || disposed) return; moving = false; setRatio(pixelRatio); invalidate(); }, 180); }
  function invalidate() {
    if (pending || disposed || blocked() || document.hidden) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      if (disposed || blocked() || document.hidden) return;
      controls.update();
      const start = performance.now(); renderer.render(scene,camera);
      Object.assign(stats, {frames: ++frames, moving, calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, cpuSubmitMs: performance.now()-start});
      onFrame({...stats});
    });
  }
  const start = () => { dragging = moving = true; clearTimeout(settleTimer); setRatio(Math.min(pixelRatio, 0.85)); invalidate(); };
  const change = () => { if (moving) settle(); invalidate(); };
  const end = () => { dragging = false; settle(); };
  const visibility = () => { if (!document.hidden) { dragging = moving = false; setRatio(pixelRatio); invalidate(); } };
  controls.addEventListener('start',start); controls.addEventListener('change',change); controls.addEventListener('end',end); document.addEventListener('visibilitychange',visibility);
  setRatio(pixelRatio);
  return {invalidate, get stats(){return {...stats};}, dispose(){disposed=true;clearTimeout(settleTimer);controls.removeEventListener('start',start);controls.removeEventListener('change',change);controls.removeEventListener('end',end);document.removeEventListener('visibilitychange',visibility);}};
}
