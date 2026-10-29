const slides=[...document.querySelectorAll('.slide')],stage=document.getElementById('stage'),vp=document.getElementById('viewport');
let cur=-1;
function fit(){const w=vp.clientWidth,h=vp.clientHeight,s=Math.min(w/1920,h/1080);stage.style.transform=`translate(${(w-1920*s)/2}px,${(h-1080*s)/2}px) scale(${s})`}
addEventListener('resize',fit);

/* ---------- live frames: load on the active slide, pre-warm the next slide's frame (hidden), unload the rest ---------- */
const CLEAN_CSS='header,#overlayBar{display:none!important}';
/* live twin slides: the deck draws the selected sensor's callout (with its simulated chart) beside the clicked pin, placed
   clear of the other pins (TWIN_JS + place.js), so the viewer's own floating cards (#lensCard, #sdCard) are hidden */
const CLEAN_CSS_SENSOR=CLEAN_CSS+'#lensCard,#sdCard{display:none!important}'
  +'#sdLayer .sd-pin.on{outline:6px solid #FDB515!important;outline-offset:3px!important;box-shadow:0 0 0 12px rgba(253,181,21,.35),0 2px 8px rgba(0,0,0,.55)!important}#sdLayer .sd-chip.on{outline:3px solid #FDB515!important;background:#FDB515!important;color:#1F2A37!important}';   /* the selected sensor stands out at slide scale */
/* live twin slides: also hide the capture / Walk controls of the nested scan (photo) frame, same origin; re-applied when it reloads */
const NESTED_CLEAN_CSS='#tools{display:none!important}';
function cleanNested(el,f){if(el.dataset.live!=='sensor')return;const apply=n=>{try{const d=n.contentDocument;if(!d||!d.head)return;let s=d.getElementById('deck-clean-nested');const on=el.dataset.clean==='1';
    if(on&&!s){s=d.createElement('style');s.id='deck-clean-nested';s.textContent=NESTED_CLEAN_CSS;d.head.appendChild(s)}if(!on&&s)s.remove()}catch(_){}};
  const scan=()=>{try{f.contentDocument.querySelectorAll('iframe').forEach(n=>{apply(n);if(!n._deckClean){n._deckClean=1;n.addEventListener('load',()=>apply(n))}})}catch(_){}};
  scan();let k=0;const iv=setInterval(()=>{if(!f.isConnected||++k>40){clearInterval(iv);return}scan()},500)}
function applyClean(el,f){cleanNested(el,f);try{const d=f.contentDocument;let s=d.getElementById('deck-clean');const on=el.dataset.clean==='1';
  if(on&&!s){s=d.createElement('style');s.id='deck-clean';s.textContent=el.dataset.live==='sensor'?CLEAN_CSS_SENSOR:CLEAN_CSS;d.head.appendChild(s)}
  if(!on&&s)s.remove();f.contentWindow.dispatchEvent(new Event('resize'));
  const b=el.querySelector('[data-toggle-chrome]');if(b)b.textContent=on?'Show page controls':'Hide page controls'}catch(e){}}
function loadLive(el){
  if(el.querySelector('iframe')||el.dataset.off==='1')return;
  const f=document.createElement('iframe'),sc=+el.dataset.scale||1,k=el.dataset.live;
  const W=parseFloat(el.style.width),H=parseFloat(el.style.height);
  f.setAttribute('allow','fullscreen; xr-spatial-tracking; accelerometer; gyroscope');
  f.style.width=(W/sc)+'px';f.style.height=(H/sc)+'px';f.style.transform=`scale(${sc})`;f.style.visibility='hidden';
  el.classList.add('busy');
  const fail=()=>{el.classList.add('failed');el.classList.remove('busy');f.remove()};
  f.addEventListener('load',()=>{
    try{const d=f.contentDocument;if(!d||!d.body||/^\s*(404|Error)/i.test(d.title)||/404 Not Found|Error response/i.test(d.body.innerText.slice(0,200)))return fail();
      if(el.dataset.clean==='1'||el.querySelector('[data-toggle-chrome]'))applyClean(el,f);
      f.style.visibility='visible';el.classList.remove('failed');hookKeys(f.contentWindow);
      if(k==='sensor'){let n=0;const iv=setInterval(()=>{let ok=false;try{const w=f.contentWindow;ok=!!(w&&w.sensorDemoInspection&&w.sensorDemoInspection().pins.length)}catch(_){}
        if(!f.isConnected){clearInterval(iv);return}   /* unloaded (Static view / slide change): not ready */
        if(ok||++n>180){clearInterval(iv);el.classList.remove('busy');el.classList.add('ready')}},250)}   /* live twin: hidden (static view shown) until its demo sensors are drawn (max 45 s) */
      else setTimeout(()=>el.classList.remove('busy'),k==='lens'?2500:800);
      if(k==='energy')focusEnergy(f);
    }catch(e){fail()}
  });
  f.addEventListener('error',fail);
  f.src=el.dataset.src;el.querySelector('.vp').appendChild(f);
}
function focusEnergy(f){let n=0;const t=setInterval(()=>{try{const d=f.contentDocument,w=d.getElementById('water-panel');
  const sel=d.getElementById('building');
  if(sel&&sel.options.length&&!f._sel){const o=[...sel.options].find(o=>/grimes/i.test(o.textContent));if(o){f._sel=1;sel.value=o.value;sel.dispatchEvent(new Event('change',{bubbles:true}))}}
  if(w&&!w.hidden){d.documentElement.scrollTop=w.getBoundingClientRect().top+d.documentElement.scrollTop-8;clearInterval(t)}}catch(e){clearInterval(t)}
  if(++n>40)clearInterval(t)},500)}
function unloadLive(el){const f=el.querySelector('iframe');if(f){f.src='about:blank';f.remove()}el.classList.remove('failed','busy','ready')}

/* ---------- keys inside same-origin frames (and their nested frames) still drive the deck ---------- */
const FWD=['ArrowLeft','ArrowRight','PageUp','PageDown','n','N','f','F'];
function hookKeys(w){try{if(!w||w._deckHooked)return;w._deckHooked=1;
  const nested=()=>{try{w.document.querySelectorAll('iframe').forEach(n=>{if(n._deckHk)return;n._deckHk=1;n.addEventListener('load',()=>hookKeys(n.contentWindow));hookKeys(n.contentWindow)})}catch(_){}};
  nested();const iv=setInterval(()=>{try{if(w.closed){clearInterval(iv);return}nested()}catch(_){clearInterval(iv)}},1500);
  w.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();window.focus();document.activeElement&&document.activeElement.blur();document.dispatchEvent(new Event('deck-esc'));return}
    if(e.target&&/INPUT|SELECT|TEXTAREA/.test(e.target.tagName))return;if(e.ctrlKey||e.metaKey||e.altKey)return;
    if(FWD.includes(e.key)){e.preventDefault();e.stopImmediatePropagation();handle(e)}},true)}catch(_){}}

/* ---------- cross-fade time slider ---------- */
const XF={};
document.querySelectorAll('.xf').forEach(box=>{const k=box.dataset.xf,n=+box.dataset.n,sl=box.closest('.slide');
  const x={k,n,box,t:0,anim:0,imgs:[...box.querySelectorAll('img')],tags:[...box.querySelectorAll('.xtag')],
    range:sl.querySelector(`[data-xf-range="${k}"]`),btns:[...sl.querySelectorAll(`[data-xf-go="${k}"]`)],caps:[...sl.querySelectorAll(`[data-xf-cap="${k}"]`)]};
  x.t=+x.range.value;XF[k]=x;setT(x,x.t);
  x.range.addEventListener('input',()=>{cancelAnimationFrame(x.anim);setT(x,+x.range.value)});
  x.range.addEventListener('change',()=>{go(x,Math.round(x.t));x.range.blur()});
  x.range.addEventListener('keydown',e=>{if(/^Arrow|^Page|Home|End/.test(e.key))e.preventDefault()});   /* deck keys, not native range steps */
  x.btns.forEach(b=>b.addEventListener('click',()=>{go(x,+b.dataset.i);b.blur()}));
  let drag=null;
  box.addEventListener('pointerdown',e=>{drag={id:e.pointerId};box.setPointerCapture(e.pointerId);cancelAnimationFrame(x.anim);fromPointer(e)});
  box.addEventListener('pointermove',e=>{if(drag&&drag.id===e.pointerId)fromPointer(e)});
  const end=e=>{if(!drag||drag.id!==e.pointerId)return;drag=null;go(x,Math.round(x.t))};
  box.addEventListener('pointerup',end);box.addEventListener('pointercancel',end);
  function fromPointer(e){const r=box.getBoundingClientRect();setT(x,Math.max(0,Math.min(1,(e.clientX-r.left)/r.width))*(n-1))}
});
function setT(x,t){x.t=t=Math.max(0,Math.min(x.n-1,t));const base=Math.min(x.n-2,Math.floor(t)),fr=t-base,near=Math.round(t);
  x.imgs.forEach((im,i)=>{im.style.opacity=i===base?1:i===base+1?fr:0});
  x.tags.forEach((g,i)=>g.hidden=i!==near);x.btns.forEach((b,i)=>b.classList.toggle('on',i===near));x.caps.forEach((c,i)=>c.classList.toggle('on',i===near));
  x.range.value=t}
function go(x,i){i=Math.max(0,Math.min(x.n-1,i));cancelAnimationFrame(x.anim);const t0=x.t,t1=i,T=matchMedia('(prefers-reduced-motion: reduce)').matches?0:450,s=performance.now();
  const stp=now=>{const p=T?Math.min(1,(now-s)/T):1,ez=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;setT(x,t0+(t1-t0)*ez);if(p<1)x.anim=requestAnimationFrame(stp)};x.anim=requestAnimationFrame(stp)}
function curXF(){const b=slides[cur]&&slides[cur].querySelector('.xf');return b?XF[b.dataset.xf]:null}

/* ---------- navigation ---------- */
function show(i,noHash){i=Math.max(0,Math.min(slides.length-1,i));if(i===cur)return;
  if(cur>=0)slides[cur].classList.remove('active');
  cur=i;slides[i].classList.add('active');
  /* live frames load on the active slide and warm up, hidden, on the next one, so they are ready on arrival; every other
     frame is unloaded (at most two live 3D twins at a time). */
  const keep=new Set([slides[i],slides[i+1]].filter(Boolean));
  const warm=s=>!!s&&!!s.querySelector('.live');
  slides.forEach(s=>{s.classList.toggle('preload',s===slides[i+1]&&warm(s));if(!keep.has(s))s.querySelectorAll('.live').forEach(unloadLive)});
  slides[i].querySelectorAll('.live').forEach(loadLive);
  /* warm the next slide's live view so it is ready on arrival, but only once this slide's own live twin is ready: the two
     would otherwise share the bandwidth and the GPU and both arrive late */
  const warmNext=()=>{if(cur!==i||!slides[i+1])return;
    if([...slides[i].querySelectorAll('.live[data-live="sensor"]')].some(l=>!l.hidden&&l.dataset.off!=='1'&&l.querySelector('iframe')&&!l.classList.contains('ready')&&!l.classList.contains('failed')))return setTimeout(warmNext,300);
    slides[i+1].querySelectorAll('.live').forEach(loadLive)};
  warmNext();
  document.getElementById('count').textContent=(i+1)+' / '+slides.length;
  document.getElementById('notes-text').textContent=NOTES[i];
  if(!noHash)history.replaceState(null,'','#'+(i+1));
  window.focus()}
function handle(e){const k=e.key,x=curXF();
  if(x&&/^[1-9]$/.test(k)&&+k<=x.n){e.preventDefault();go(x,+k-1);return}
  if(x&&(k==='ArrowDown'||k==='ArrowUp')){e.preventDefault();go(x,Math.round(x.t)+(k==='ArrowDown'?1:-1));return}
  if(k==='ArrowRight'||k===' '||k==='PageDown'){e.preventDefault();show(cur+1)}
  else if(k==='ArrowLeft'||k==='PageUp'){e.preventDefault();show(cur-1)}
  else if(k==='Home')show(0);else if(k==='End')show(slides.length-1);
  else if(k==='f'||k==='F'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen()}
  else if(k==='n'||k==='N'){const n=document.getElementById('notes');n.hidden=!n.hidden;fit2()}
  else if(k==='Escape'){window.focus()}}
function fit2(){const n=document.getElementById('notes');vp.style.bottom=(44+(n.hidden?0:n.offsetHeight))+'px';fit()}
document.addEventListener('keydown',e=>{if(e.target&&e.target.tagName==='BUTTON'&&(e.key===' '||e.key==='Enter'))e.target.blur();handle(e)});
document.getElementById('prev').onclick=e=>{show(cur-1);e.currentTarget.blur()};document.getElementById('next').onclick=e=>{show(cur+1);e.currentTarget.blur()};
document.addEventListener('click',e=>{const b=e.target.closest('[data-toggle-chrome]');if(!b)return;const el=b.closest('.live'),f=el.querySelector('iframe');
  el.dataset.clean=el.dataset.clean==='1'?'0':'1';if(f)applyClean(el,f);b.blur()});
function fromHash(){const m=/^#(\d+)/.exec(location.hash);return m?+m[1]-1:0}
addEventListener('hashchange',()=>show(fromHash(),true));
fit();show(fromHash(),true);
