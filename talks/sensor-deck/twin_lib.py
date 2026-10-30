# Generic interactive "twin concept" slide machinery (live SVG on a clean Lens base image). Used by gen.py.
import html, json, math
def e(s): return html.escape(s, quote=True)
IMG_W, IMG_H = 775, 630

# ---- SVG drawing helpers (base-image pixel coordinates)
def pin(k, x, y, col, r=19):
    return (f'<circle cx="{x+3}" cy="{y+4}" r="{r}" fill="rgba(0,0,0,.28)"/><circle cx="{x}" cy="{y}" r="{r}" fill="#fff"/>'
            f'<circle cx="{x}" cy="{y}" r="{r-5}" fill="{col}"/><text x="{x}" y="{y+6}" text-anchor="middle" font-size="18" font-weight="700" fill="#fff">{k}</text>')
def badge(k, x, y, col):
    return (f'<circle cx="{x}" cy="{y}" r="15" fill="#fff"/><circle cx="{x}" cy="{y}" r="12" fill="{col}"/>'
            f'<text x="{x}" y="{y+5.5}" text-anchor="middle" font-size="16" font-weight="700" fill="#fff">{k}</text>')
def ring(x, y, r, col='#DC1414', pulse=True):
    s = (f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="#fff" stroke-width="7"/><circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="{col}" stroke-width="4"/>')
    if pulse: s += (f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="{col}" stroke-width="3"><animate attributeName="r" values="{r};{r*1.9:.0f}" dur="1.8s" repeatCount="indefinite"/>'
                    f'<animate attributeName="stroke-opacity" values=".85;0" dur="1.8s" repeatCount="indefinite"/></circle>')
    return s
def zone(x, y, rx, ry, col, op=.45, rot=0, pulse=False):
    """soft elliptical tint (heat map / coverage). Radial fade done with a blurred ellipse."""
    a = f'<animate attributeName="opacity" values="1;.55;1" dur="3.2s" repeatCount="indefinite"/>' if pulse else ''
    return (f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{col}" fill-opacity="{op}" transform="rotate({rot} {x} {y})" filter="url(#soft)">{a}</ellipse>')
def poly(pts, col, op=.35, stroke=None, dash=None, sw=3):
    d = ' '.join(f'{px_},{py_}' for px_, py_ in pts)
    st = f' stroke="{stroke}" stroke-width="{sw}"' + (f' stroke-dasharray="{dash}"' if dash else '') if stroke else ''
    return f'<polygon points="{d}" fill="{col}" fill-opacity="{op}"{st} stroke-linejoin="round"/>'
def link(x1, y1, x2, y2, col='#fff', w=2, dash=None, op=.85):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-opacity="{op}" stroke-width="{w}"' + (f' stroke-dasharray="{dash}"' if dash else '') + '/>'
def flowline(pts, col='#fff', w=5, dash='2 40'):
    d = ' '.join(f'{x},{y}' for x, y in pts)
    return (f'<polyline class="flow" points="{d}" fill="none" stroke="{col}" stroke-opacity=".9" stroke-width="{w}" stroke-linecap="round" stroke-dasharray="{dash}"/>')

def marker_group(k, title, drawing, hit):
    hx, hy, hr = hit
    return (f'<g class="mk" data-m="{k}" tabindex="0" role="button" aria-label="{e(title)}"><circle cx="{hx}" cy="{hy}" r="{hr}" fill="rgba(0,0,0,.001)"/>{drawing}</g>')

def build_twin(sc, U, x, y, h):
    """Return (html, js-config) for one scenario. sc keys: slug, base, fallback, elements[], bg (svg under markers), defs, anim, live."""
    w = h * IMG_W / IMG_H; slug = sc['slug']
    px = lambda v: f'{v*U:.1f}px'
    pos = lambda a, b, c, d: f'left:{px(a)};top:{px(b)};width:{px(c)};height:{px(d)}'
    defs = ('<filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="9"/></filter>' + sc.get('defs', ''))
    groups = ''; halos = ''; cfg = {}
    # large hit areas (the DTS line, alert rings, zones) go underneath, so every numbered badge stays clickable on top of them
    for el in sorted(sc['elements'], key=lambda el: (not el.get('under'), -el['hit'][2])):
        k = el['k']; bx, by = el['badge']
        groups += marker_group(k, el['title'], el['draw'], el['hit'])
        # selection halo around the numbered badge (drawn under the markers; shown only for the active one)
        halos += (f'<g class="halo" data-m="{k}"><circle cx="{bx}" cy="{by}" r="27" fill="rgba(253,181,21,.25)" stroke="#fff" stroke-width="10"/>'
                  f'<circle cx="{bx}" cy="{by}" r="27" fill="none" stroke="#FDB515" stroke-width="6"/></g>')
        el.setdefault('sid', '')
        cfg[k] = el['badge']
    svg = (f'<svg class="tw-svg" viewBox="0 0 {IMG_W} {IMG_H}" style="position:absolute;inset:0;width:100%;height:100%" xmlns="http://www.w3.org/2000/svg">'
           f'<defs>{defs}</defs><g class="tw-sensors">{sc.get("bg","")}{halos}{groups}</g></svg>')
    base = (f'<img class="tw-base" src="img/{sc["base"]}" alt="{e(sc.get("alt","Level 1 ceiling in the Lens overlay (May 6 capture)"))}" style="position:absolute;inset:0;width:100%;height:100%" data-fallback="{sc.get("fallback","")}">')
    out = f'<div class="tw" data-slug="{slug}" data-anim="{sc.get("anim","")}" data-w="{IMG_W}" data-h="{IMG_H}" data-pts=\'{__import__("json").dumps(cfg)}\' style="{pos(x,y,w,h)}">{base}{svg}</div>'
    # LIVE layer on top of the static figure: the local viewer with ?sensors=demo, loaded on its slide and warmed (hidden) one
    # slide ahead (deck.js). It stays invisible until its demo sensors are drawn, so the static image + SVG underneath shows
    # at once and remains the fallback (Static view, or iframe failure).
    out += (f'<div class="live twlive" data-live="sensor" data-clean="1" data-scale="0.72" data-src="{e(sc["live"])}" style="{pos(x,y,w,h)}">'
            '<div class="vp"></div><span class="badge-live">Interactive twin, simulated data. Drag to look</span></div>')
    out += (f'<div class="tw-wait" hidden style="{pos(x,y,w,h)}"><span>Loading the interactive 3D view: about 10–20 seconds.<br>This still image is shown until it is ready.</span></div>')
    out += (f'<div style="{pos(x,y+h+.1,w,.32)};display:flex;gap:10px;align-items:center"><button class="btn tw-btn tw-toggle" aria-pressed="true">Sensors: on</button>'
            '<button class="btn tw-btn tw-mode" aria-pressed="false">Static view</button>'
            f'<a class="btn tw-btn" href="{e(sc["live"])}" target="_blank" rel="noopener">Open in viewer ↗</a><span class="tw-status" aria-live="polite"></span></div>')
    return out, w

def callouts(sc, U, x, y, h, chart_for):
    """Callout layer over the image / live view (slides 8-12): one compact card per numbered sensor (title, SIMULATED tag,
    the simulated reading, a small chart when the registry or the demo feed has a matching series, charts.py). deck JS
    places the selected card BESIDE its marker or live pin with a leader line, clear of the other markers, the selected
    sensor's pipe / cable and the slide text (place.js). data-ob: badge [x, y, r] and drawn shapes per marker, base-image px."""
    w = h * IMG_W / IMG_H
    px = lambda v: f'{v*U:.1f}px'
    ob = {el['k']: dict(b=[*el['badge'], el.get('br', 20)], geo=el.get('geo', []), area=el.get('area', [])) for el in sc['elements']}
    out = (f'<div class="twco" data-ob=\'{json.dumps(ob, separators=(",", ":"))}\' style="left:{px(x)};top:{px(y)};width:{px(w)};height:{px(h)}">'
           '<svg class="twlead" style="position:absolute;inset:0;width:100%;height:100%;overflow:visible" aria-hidden="true"><line class="twl0"/><line class="twl1"/><circle r="5"/></svg>')
    for el in sc['elements']:
        k = el['k']; ch = chart_for(el.get('sid', ''))
        out += (f'<div class="twcall{" haschart" if ch else ""}" data-m="{k}" role="note" hidden><div class="twh" style="background:{el["col"]}"><span>{k}</span>'
                f'<div><em>{e(el["title"])}</em><i>SIMULATED · not installed</i></div></div><p class="twcv">{e(el["val"])}</p>'
                + (f'<div class="twch">{ch}</div>' if ch else '') + '</div>')
    return out + '</div>'

TWIN_JS = r"""
document.querySelectorAll('.tw').forEach(tw=>{
const sl=tw.closest('.slide'),base=tw.querySelector('.tw-base'),svg=tw.querySelector('.tw-svg'),
  rows=[...sl.querySelectorAll('.twrow')],mks=[...tw.querySelectorAll('.mk')],halos=[...tw.querySelectorAll('.halo')],
  tg=sl.querySelector('.tw-toggle'),grp=tw.querySelector('.tw-sensors'),status=sl.querySelector('.tw-status'),
  co=sl.querySelector('.twco'),calls=[...co.querySelectorAll('.twcall')],lead=co.querySelector('.twlead'),
  OB=JSON.parse(co.dataset.ob),FS=parseFloat(tw.style.width)/(+tw.dataset.w);
base.addEventListener('error',()=>{if(base.dataset.fallback){base.src=base.dataset.fallback}svg.remove();tw.classList.add('fallback')},{once:true});
/* selection: pinned (click) > hover (deck) > liveSel (a pin hovered / clicked inside the live view) */
let pinned=null,hover=null,liveSel=null,on=true,cardObs=null,pinObs=null,shown=null,prefer=null,raf=0;
const live=sl.querySelector('.twlive'),mode=sl.querySelector('.tw-mode'),SID={},KOF={};rows.forEach(r=>{if(r.dataset.sid){SID[+r.dataset.m]=r.dataset.sid;KOF[r.dataset.sid]=+r.dataset.m}});
const liveOn=()=>!!live&&!live.hidden&&live.classList.contains('ready')&&!live.classList.contains('failed');
const liveFrame=()=>{const f=live&&live.querySelector('iframe');return liveOn()&&f&&f.contentWindow?f:null};
function focusLive(){const f=liveFrame();if(!f)return;const k=pinned||hover;try{f.contentWindow.postMessage({type:'grimes-sensor-demo-focus',id:(on&&k&&SID[k])||null},location.origin)}catch(_){}}
/* the viewer's own card (#sdCard) is hidden in the deck; its state tells us which pin the audience is looking at */
function watchCard(){if(cardObs){cardObs.disconnect();cardObs=null}const f=liveFrame();let c=null;try{c=f&&f.contentDocument.getElementById('sdCard')}catch(_){}
  if(!c)return;const sync=()=>{const id=c.classList.contains('show')?c.dataset.sensor:'';const k=KOF[id]||null;
    if(!k&&pinned&&liveSel)pinned=null;   /* clicked elsewhere in the view: the deck selection closes too */
    if(k!==liveSel){liveSel=k;render(true)}};
  cardObs=new MutationObserver(sync);cardObs.observe(c,{attributes:true,attributeFilter:['class','data-sensor']});sync()}
/* the callout follows its pin while the view moves (pins are re-positioned by the viewer on every frame) */
function watchPins(){if(pinObs){pinObs.disconnect();pinObs=null}const f=liveFrame();let L=null;try{L=f&&f.contentDocument.getElementById('sdLayer')}catch(_){}
  if(!L)return;pinObs=new MutationObserver(()=>{if(shown&&!raf)raf=requestAnimationFrame(()=>{raf=0;placeCall(true)})});
  pinObs.observe(L,{attributes:true,subtree:true,attributeFilter:['style','hidden']})}
function setStatus(){if(!status||!live)return;const busy=!live.hidden&&!live.classList.contains('ready')&&!live.classList.contains('failed')&&sl.classList.contains('active');
  status.textContent=busy?'Interactive view loading (about 10–20 s)…':'';status.hidden=!busy;
  const wt=sl.querySelector('.tw-wait');if(wt)wt.hidden=!busy}
function setMode(stat){if(!live)return;live.hidden=stat;live.dataset.off=stat?'1':'';mode.setAttribute('aria-pressed',String(stat));mode.textContent=stat?'Interactive view':'Static view';
  if(stat)unloadLive(live);else if(sl.classList.contains('active'))loadLive(live);liveSel=null;setStatus();render();mode.blur()}
if(mode)mode.addEventListener('click',ev=>{ev.stopPropagation();setMode(!live.hidden)});
if(live)new MutationObserver(()=>{if(live.classList.contains('failed')&&mode){mode.textContent='Live view unavailable';mode.disabled=true}
  if(liveOn()){watchCard();watchPins();focusLive()}else{if(cardObs){cardObs.disconnect();cardObs=null}if(pinObs){pinObs.disconnect();pinObs=null}liveSel=null}setStatus();render(true)}).observe(live,{attributes:true,attributeFilter:['class','hidden']});
if(sl)new MutationObserver(setStatus).observe(sl,{attributes:true,attributeFilter:['class']});
/* ---- callout beside the selected marker / pin (place.js: clear of the other markers, the selected pipe / cable, the text) */
const W=parseFloat(co.style.width),H=parseFloat(co.style.height),BOUNDS=[6,6,W-6,H-6],TIERS=['t0','t1','t2'];
const rel=(r,o)=>[r.left-o.left,r.top-o.top,r.right-o.left,r.bottom-o.top];
function sizes(c){const out=[];TIERS.forEach(t=>{c.classList.remove(...TIERS);c.classList.add(t);out.push({w:c.offsetWidth,h:c.offsetHeight})});return out}
function staticScene(k){const hard=[],soft=[];
  for(const [m,o] of Object.entries(OB)){const [bx,by,br]=o.b;
    if(+m===k){hard.push(...TwPlace.shapeRects([['dot',bx,by,34]],FS),...TwPlace.shapeRects(o.geo,FS))}
    else{hard.push(...TwPlace.shapeRects([['dot',bx,by,br+6]],FS));soft.push(...TwPlace.shapeRects(o.geo,FS))}
    soft.push(...TwPlace.shapeRects(o.area,FS))}
  const [ax,ay]=OB[k].b;return {anchor:{x:ax*FS,y:ay*FS},r0:30*FS,hard,soft}}
function liveScene(k){const f=liveFrame();if(!f)return null;let d;try{d=f.contentDocument}catch(_){return null}if(!d)return null;
  const sc=+live.dataset.scale||1,fo={left:0,top:0},S=r=>[r[0]*sc,r[1]*sc,r[2]*sc,r[3]*sc],pad=(r,p)=>[r[0]-p,r[1]-p,r[2]+p,r[3]+p];
  const hard=[],soft=[],sid=SID[k];let anchor=null,r0=18;
  d.querySelectorAll('#sdLayer .sd-pin').forEach(p=>{if(p.hidden)return;const r=S(rel(p.getBoundingClientRect(),fo));
    if(p.dataset.sensor===sid){const a=p.dataset.type==='alert'?18:12;hard.push(pad(r,a));anchor={x:(r[0]+r[2])/2,y:(r[1]+r[3])/2};r0=(r[2]-r[0])/2+a-4}
    else hard.push(pad(r,5))});
  d.querySelectorAll('#sdLayer .sd-chip').forEach(c=>{if(!c.hidden)soft.push(S(rel(c.getBoundingClientRect(),fo)))});
  const sv=d.querySelector('#sdLayer svg');if(sv){const o=sv.getBoundingClientRect(),own=sid==='leak-dts';
    sv.querySelectorAll('line').forEach(l=>{const q=TwPlace.shapeRects([['seg',+l.getAttribute('x1')+o.left,+l.getAttribute('y1')+o.top,+l.getAttribute('x2')+o.left,+l.getAttribute('y2')+o.top,5]],sc);(own?hard:soft).push(...q)})}
  const bd=d.getElementById('sdBadge');if(bd&&bd.offsetWidth)hard.push(S(rel(bd.getBoundingClientRect(),fo)));
  const bl=live.querySelector('.badge-live');if(bl&&bl.offsetWidth)hard.push([bl.offsetLeft,bl.offsetTop,bl.offsetLeft+bl.offsetWidth,bl.offsetTop+bl.offsetHeight]);
  if(!anchor){const [ax,ay]=OB[k].b;anchor={x:ax*FS,y:ay*FS,off:true}}   /* pin out of view: the card sits near the sensor's usual spot, no leader */
  return {anchor,r0,hard,soft}}
function placeCall(keep){const k=shown;if(!k)return;const c=calls.find(x=>+x.dataset.m===k);if(!c)return;
  const S=liveOn()?liveScene(k):staticScene(k);if(!S)return;
  const sz=sizes(c),p=TwPlace.place({anchor:S.anchor,sizes:sz,bounds:BOUNDS,hard:S.hard,soft:S.soft,gap:S.r0+16,prefer:keep?prefer:null});
  prefer={tier:p.tier,dx:p.dx,dy:p.dy};c.classList.remove(...TIERS);c.classList.add(TIERS[p.tier]);
  c.style.left=p.x.toFixed(1)+'px';c.style.top=p.y.toFixed(1)+'px';c.dataset.stage=p.stage;c.dataset.hard=Math.round(p.hard);c.dataset.soft=Math.round(p.soft);
  const ln=S.anchor.off?null:TwPlace.leader(p,S.anchor.x,S.anchor.y,S.r0);lead.style.display=ln?'':'none';
  if(ln){lead.querySelectorAll('line').forEach(l=>{l.setAttribute('x1',ln[0]);l.setAttribute('y1',ln[1]);l.setAttribute('x2',ln[2]);l.setAttribute('y2',ln[3])});
    const cc=lead.querySelector('circle');cc.setAttribute('cx',ln[0]);cc.setAttribute('cy',ln[1])}}
function showCall(k){if(k!==shown)prefer=null;shown=k;calls.forEach(c=>{c.hidden=+c.dataset.m!==k});co.classList.toggle('on',!!k);if(k)placeCall(false);else lead.style.display='none'}
function render(noFocus){const k=on?(pinned||hover||(liveOn()?liveSel:null)):null;
  showCall(k);sl.classList.toggle('tw-sel',!!k);tw.classList.toggle('sel',!!k);
  rows.forEach(r=>r.classList.toggle('on',+r.dataset.m===k));
  mks.forEach(g=>g.classList.toggle('on',+g.dataset.m===k));halos.forEach(g=>g.classList.toggle('on',+g.dataset.m===k));if(!noFocus)focusLive()}
function wire(el,m){el.addEventListener('mouseenter',()=>{hover=m;render()});el.addEventListener('mouseleave',()=>{hover=null;render()});
  el.addEventListener('click',ev=>{ev.stopPropagation();pinned=pinned===m?null:m;render()});
  el.addEventListener('keydown',ev=>{if(ev.key==='Enter'){ev.stopPropagation();pinned=pinned===m?null:m;render()}})}
mks.forEach(g=>wire(g,+g.dataset.m));rows.forEach(r=>wire(r,+r.dataset.m));
calls.forEach(c=>c.addEventListener('click',ev=>ev.stopPropagation()));   /* clicking the card itself keeps it open */
sl.addEventListener('click',ev=>{if(ev.target.closest('.tw-btn,a'))return;if(pinned){pinned=null;render()}});   /* click elsewhere closes */
const esc=()=>{if(!sl.classList.contains('active'))return;pinned=null;hover=null;render();try{const f=liveFrame();f&&f.contentWindow.postMessage({type:'grimes-sensor-demo-focus',id:null},location.origin)}catch(_){}};
document.addEventListener('keydown',ev=>{if(ev.key==='Escape')esc()});document.addEventListener('deck-esc',esc);
if(tg)tg.addEventListener('click',ev=>{ev.stopPropagation();on=!on;grp.style.display=on?'':'none';
  try{const f=liveFrame(),b=f&&f.contentDocument.getElementById('sdToggle');if(b&&(b.getAttribute('aria-pressed')==='true')!==on)b.click()}catch(_){}tg.textContent='Sensors: '+(on?'on':'off');tg.setAttribute('aria-pressed',on);tg.blur();if(!on)pinned=null;render()});
addEventListener('hashchange',()=>{pinned=null;hover=null;render()});
setStatus();
const RM=matchMedia('(prefers-reduced-motion: reduce)').matches;
const flows=[...tw.querySelectorAll('.flow')];
let ga=null;if(tw.dataset.anim==='dts'){const g=tw.querySelector('linearGradient.dts'),st=[...g.querySelectorAll('stop')];ga={st}}
const STOPS=[[0,[30,80,220]],[.33,[0,190,230]],[.6,[250,215,40]],[1,[230,30,30]]];
function cm(v){for(let i=0;i<STOPS.length-1;i++){const[a,ca]=STOPS[i],[b,cb]=STOPS[i+1];if(v<=b){const f=(v-a)/(b-a);return'rgb('+ca.map((c,j)=>Math.round(c+f*(cb[j]-c))).join(',')+')'}}return'rgb(230,30,30)'}
const HT=+(tw.dataset.ht||.4),CT=+(tw.dataset.ct||.8);
function frame(ts){const t=ts/1000;
  if(ga){const amp=.86+.14*Math.sin(t*2.2);ga.st.forEach((s,i)=>{const u=i/(ga.st.length-1);const v=.36+.64*amp*Math.exp(-Math.pow((u-HT)/.085,2))-.34*Math.exp(-Math.pow((u-CT)/.06,2))+.02*Math.sin(u*40+t*3);s.setAttribute('stop-color',cm(Math.max(0,Math.min(1,v))))})}
  flows.forEach((f,i)=>{f.style.strokeDashoffset=(-(t*(36+8*i))%42)});
  if(!RM)requestAnimationFrame(frame)}
if(ga||flows.length)requestAnimationFrame(frame);
});
"""

TWIN_CSS = """
.tw{overflow:hidden;outline:2px solid #C8D1DC;outline-offset:-1px;box-shadow:0 4px 10px rgba(0,0,0,.22);background:#ddd}
.tw .mk{cursor:pointer;outline:none;transition:opacity .15s}.tw .mk:focus-visible{filter:drop-shadow(0 0 6px #FDB515)}.tw .mk.on{filter:drop-shadow(0 0 6px #FDB515)}
.tw.sel .mk:not(.on){opacity:.45}
.tw .halo{display:none;pointer-events:none}.tw .halo.on{display:inline}
.twrow{transition:background .15s,outline-color .15s;outline:3px solid transparent;outline-offset:-1px}.twrow.on{background:#FFF3D6;outline-color:#FDB515}
.twsteps>*{position:absolute}
/* callout layer: same box as the image, above the live view; only the card itself takes clicks */
.twco{z-index:4;pointer-events:none;overflow:hidden}
.twlead{display:none}.twco.on .twlead{display:block}
.twlead line.twl0{stroke:#fff;stroke-width:8;stroke-linecap:round}.twlead line.twl1{stroke:#FDB515;stroke-width:4;stroke-linecap:round}.twlead circle{fill:#FDB515;stroke:#fff;stroke-width:2.5}
.twcall{position:absolute;left:0;top:0;pointer-events:auto;background:#fff;border-radius:12px;box-shadow:0 6px 18px rgba(0,0,0,.35);outline:3px solid #FDB515;outline-offset:-1px;overflow:hidden;color:#1F2A37;cursor:default}
.twcall[hidden]{display:none}
.twcall.t0{width:420px}.twcall.t1{width:350px}.twcall.t2{width:290px}
.twcall:not(.haschart).t0{width:340px}.twcall:not(.haschart).t1{width:300px}.twcall:not(.haschart).t2{width:260px}
.twh{color:#fff;font-weight:700;padding:6px 12px;display:flex;align-items:center;gap:10px}
.twh span{background:#fff;color:#1F2A37;border-radius:50%;width:32px;height:32px;flex:none;display:inline-flex;align-items:center;justify-content:center;font-size:20px}
.twh div{min-width:0;display:flex;flex-direction:column}
.twh em{font-style:normal;font-size:20px;line-height:1.12}
.twh i{font-style:normal;font-size:13px;letter-spacing:.05em;opacity:.95;margin-top:1px}
.twcv{margin:0;padding:6px 12px 2px;font-size:19px;line-height:1.2}
.t2 .twcv{font-size:17px}.t2 .twh em{font-size:18px}
.twch{padding:0 10px 6px}.twc{display:block;width:100%;height:auto;font-family:Calibri,Carlito,Arial,sans-serif}
.tw-btn{font-size:19px;padding:5px 16px;display:inline-flex;align-items:center}
.tw-btn[disabled]{opacity:.55;cursor:default}
.tw-status{font:700 17px Calibri,Carlito,Arial,sans-serif;color:#003262;background:#FFF3D6;border-radius:999px;padding:4px 12px;white-space:nowrap}
.tw-status[hidden]{display:none}
.tw-wait{position:absolute;display:flex;align-items:flex-end;justify-content:center;padding-bottom:28px;pointer-events:none;z-index:5}
.tw-wait[hidden]{display:none}
.tw-wait span{font:700 19px Calibri,Carlito,Arial,sans-serif;color:#fff;background:rgba(0,50,98,.88);border-radius:10px;padding:10px 18px;text-align:center;line-height:1.35}
.live.twlive{background:transparent;outline:3px solid #FDB515;transition:opacity .35s}
.live.twlive:not(.ready){opacity:0;pointer-events:none}
.live.twlive[hidden],.live.twlive.failed{display:none}
.live[data-live="sensor"] .badge-live{left:auto;bottom:auto;right:12px;top:12px}
.stbl th,.stbl td{border:0;vertical-align:middle;text-align:left}
"""
