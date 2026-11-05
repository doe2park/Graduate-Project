/* Lab-meeting deck (self-contained, works offline). Keys: left/right/space, Home/End, F fullscreen, N speaker notes. #N opens slide N.
   A slide holding a scripted demo (.demo[data-steps]) consumes Right/Space (and clicks on it) until its last step, Left steps back.
   ?print=1 shows every demo in its final state (used for the PNG/PDF renders); ?notes=1 opens with the notes panel visible. */
const slides=[...document.querySelectorAll('.slide')],stage=document.getElementById('stage'),vp=document.getElementById('viewport');
const PRINT=/[?&]print=1/.test(location.search);if(PRINT)document.body.classList.add('print');
let cur=-1;
function fit(){const w=vp.clientWidth,h=vp.clientHeight,s=Math.min(w/1920,h/1080);stage.style.transform=`translate(${(w-1920*s)/2}px,${(h-1080*s)/2}px) scale(${s})`}
addEventListener('resize',fit);
const demoOf=i=>slides[i]&&slides[i].querySelector('.demo[data-steps]');
function setStep(d,n){const max=+d.dataset.steps;n=Math.max(0,Math.min(max,n));d.dataset.step=n;const sl=d.closest('.slide');if(sl)sl.dataset.step=n;const c=d.querySelector('#demoStep');if(c)c.textContent=n;return n}
function show(i,noHash,fromBack){i=Math.max(0,Math.min(slides.length-1,i));if(i===cur)return;
  if(cur>=0)slides[cur].classList.remove('active');
  cur=i;slides[i].classList.add('active');
  const d=demoOf(i);if(d)setStep(d,PRINT||fromBack?+d.dataset.steps:0);
  document.getElementById('count').textContent=(i+1)+' / '+slides.length;
  document.getElementById('notes-text').textContent=NOTES[i];
  if(!noHash)history.replaceState(null,'','#'+(i+1)+(PRINT?'':''));window.focus()}
function next(){const d=demoOf(cur);if(d&&+d.dataset.step<+d.dataset.steps){setStep(d,+d.dataset.step+1);return}show(cur+1)}
function prev(){const d=demoOf(cur);if(d&&+d.dataset.step>0){setStep(d,+d.dataset.step-1);return}show(cur-1,false,true)}
function fit2(){const n=document.getElementById('notes');vp.style.bottom=(44+(n.hidden?0:n.offsetHeight))+'px';fit()}
function handle(e){const k=e.key;
  if(k==='ArrowRight'||k===' '||k==='PageDown'){e.preventDefault();next()}
  else if(k==='ArrowLeft'||k==='PageUp'){e.preventDefault();prev()}
  else if(k==='Home')show(0);else if(k==='End')show(slides.length-1);
  else if(k==='f'||k==='F'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen()}
  else if(k==='n'||k==='N'){const n=document.getElementById('notes');n.hidden=!n.hidden;fit2()}}
document.addEventListener('keydown',e=>{if(e.ctrlKey||e.metaKey||e.altKey)return;if(e.target&&e.target.tagName==='BUTTON'&&(e.key===' '||e.key==='Enter'))e.target.blur();handle(e)});
document.getElementById('prev').onclick=e=>{prev();e.currentTarget.blur()};document.getElementById('next').onclick=e=>{next();e.currentTarget.blur()};
document.querySelectorAll('.demo[data-steps]').forEach(d=>d.addEventListener('click',()=>{const s=+d.dataset.step;setStep(d,s>=+d.dataset.steps?0:s+1)}));
function fromHash(){const m=/^#(\d+)/.exec(location.hash);return m?+m[1]-1:0}
addEventListener('hashchange',()=>show(fromHash(),true));
if(/[?&]notes=1/.test(location.search))document.getElementById('notes').hidden=false;
fit2();show(fromHash(),true);
