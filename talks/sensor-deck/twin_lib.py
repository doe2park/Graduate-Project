# Generic interactive "twin concept" slide machinery (live SVG on a clean Lens base image). Used by gen.py.
import html, math
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
            '<div class="vp"></div><span class="badge-live">INTERACTIVE TWIN · SIMULATED DATA · drag to look</span></div>')
    out += (f'<div style="{pos(x,y+h+.1,w,.32)};display:flex;gap:10px;align-items:center"><button class="btn tw-btn tw-toggle" aria-pressed="true">Sensors: on</button>'
            '<button class="btn tw-btn tw-mode" aria-pressed="false">Static view</button>'
            f'<a class="btn tw-btn" href="{e(sc["live"])}" target="_blank" rel="noopener">Open in viewer ↗</a><span class="tw-status" aria-live="polite"></span></div>')
    return out, w

def info_panel(sc, U, x, y, w, h, chart_for):
    """Sensor details OUTSIDE the image (right column, in place of the steps while a sensor is selected): never covers a
    marker, the pipe or the live view. One block per numbered sensor, with a small simulated chart when the registry or
    the demo feed has a series that matches the card (charts.py)."""
    px = lambda v: f'{v*U:.1f}px'
    out = f'<div class="twpanel" style="left:{px(x)};top:{px(y)};width:{px(w)};height:{px(h)}">'
    for el in sc['elements']:
        k = el['k']; ch = chart_for(el.get('sid', ''))
        out += (f'<div class="twinfo{" haschart" if ch else ""}" data-m="{k}" hidden><div class="twh" style="background:{el["col"]}"><span>{k}</span><em>{e(el["title"])}</em>'
                f'<i>SIMULATED · not installed</i></div><div class="twib"><div class="twit"><p><b>Simulated reading</b>{e(el["val"])}</p>'
                f'<p><b>What it is</b>{e(el["what"])}</p><p><b>Maps to</b>{e(el.get("maps","BIM element ID"))}</p></div>'
                + (f'<div class="twch">{ch}</div>' if ch else '') + '</div></div>')
    return out + '</div>'

TWIN_JS = r"""
document.querySelectorAll('.tw').forEach(tw=>{
const sl=tw.closest('.slide'),base=tw.querySelector('.tw-base'),svg=tw.querySelector('.tw-svg'),
  infos=[...sl.querySelectorAll('.twinfo')],rows=[...sl.querySelectorAll('.twrow')],mks=[...tw.querySelectorAll('.mk')],halos=[...tw.querySelectorAll('.halo')],
  tg=sl.querySelector('.tw-toggle'),grp=tw.querySelector('.tw-sensors'),status=sl.querySelector('.tw-status');
base.addEventListener('error',()=>{if(base.dataset.fallback){base.src=base.dataset.fallback}svg.remove();tw.classList.add('fallback')},{once:true});
/* selection: pinned (click) > hover (deck) > liveSel (a pin hovered / clicked inside the live view) */
let pinned=null,hover=null,liveSel=null,on=true,cardObs=null;
const live=sl.querySelector('.twlive'),mode=sl.querySelector('.tw-mode'),SID={},KOF={};rows.forEach(r=>{if(r.dataset.sid){SID[+r.dataset.m]=r.dataset.sid;KOF[r.dataset.sid]=+r.dataset.m}});
const liveOn=()=>!!live&&!live.hidden&&live.classList.contains('ready')&&!live.classList.contains('failed');
const liveFrame=()=>{const f=live&&live.querySelector('iframe');return liveOn()&&f&&f.contentWindow?f:null};
function focusLive(){const f=liveFrame();if(!f)return;const k=pinned||hover;try{f.contentWindow.postMessage({type:'grimes-sensor-demo-focus',id:(on&&k&&SID[k])||null},location.origin)}catch(_){}}
/* the viewer's own card (#sdCard) is hidden in the deck; its state tells us which pin the audience is looking at */
function watchCard(){if(cardObs){cardObs.disconnect();cardObs=null}const f=liveFrame();let c=null;try{c=f&&f.contentDocument.getElementById('sdCard')}catch(_){}
  if(!c)return;const sync=()=>{const id=c.classList.contains('show')?c.dataset.sensor:'';const k=KOF[id]||null;if(k!==liveSel){liveSel=k;render(true)}};
  cardObs=new MutationObserver(sync);cardObs.observe(c,{attributes:true,attributeFilter:['class','data-sensor']});sync()}
function setStatus(){if(!status||!live)return;const busy=!live.hidden&&!live.classList.contains('ready')&&!live.classList.contains('failed')&&sl.classList.contains('active');
  status.textContent=busy?'Live 3D view loading… static view shown':'';status.hidden=!busy}
function setMode(stat){if(!live)return;live.hidden=stat;live.dataset.off=stat?'1':'';mode.setAttribute('aria-pressed',String(stat));mode.textContent=stat?'Interactive view':'Static view';
  if(stat)unloadLive(live);else if(sl.classList.contains('active'))loadLive(live);liveSel=null;setStatus();render();mode.blur()}
if(mode)mode.addEventListener('click',()=>setMode(!live.hidden));
if(live)new MutationObserver(()=>{if(live.classList.contains('failed')&&mode){mode.textContent='Live view unavailable';mode.disabled=true}
  if(liveOn()){watchCard();focusLive()}else{if(cardObs){cardObs.disconnect();cardObs=null}liveSel=null}setStatus();render(true)}).observe(live,{attributes:true,attributeFilter:['class','hidden']});
if(sl)new MutationObserver(setStatus).observe(sl,{attributes:true,attributeFilter:['class']});
function render(noFocus){const k=on?(pinned||hover||(liveOn()?liveSel:null)):null;
  infos.forEach(c=>{c.hidden=+c.dataset.m!==k});sl.classList.toggle('tw-sel',!!k);tw.classList.toggle('sel',!!k);
  rows.forEach(r=>r.classList.toggle('on',+r.dataset.m===k));
  mks.forEach(g=>g.classList.toggle('on',+g.dataset.m===k));halos.forEach(g=>g.classList.toggle('on',+g.dataset.m===k));if(!noFocus)focusLive()}
function wire(el,m){el.addEventListener('mouseenter',()=>{hover=m;render()});el.addEventListener('mouseleave',()=>{hover=null;render()});
  el.addEventListener('click',ev=>{ev.stopPropagation();pinned=pinned===m?null:m;render()});
  el.addEventListener('keydown',ev=>{if(ev.key==='Enter'){ev.stopPropagation();pinned=pinned===m?null:m;render()}})}
mks.forEach(g=>wire(g,+g.dataset.m));rows.forEach(r=>wire(r,+r.dataset.m));
tw.addEventListener('click',()=>{pinned=null;render()});
if(tg)tg.addEventListener('click',()=>{on=!on;grp.style.display=on?'':'none';
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
.slide.tw-sel .twsteps{display:none}
.twsteps>*{position:absolute}
.twpanel{pointer-events:none}
.twinfo{position:absolute;inset:0;background:#fff;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,.25);outline:3px solid #FDB515;outline-offset:-1px;overflow:hidden;color:#1F2A37;display:flex;flex-direction:column}
.twinfo[hidden]{display:none}
.twh{color:#fff;font-weight:700;font-size:23px;padding:6px 14px;display:flex;align-items:center;gap:12px;flex:none}
.twh span{background:#fff;color:#1F2A37;border-radius:50%;width:34px;height:34px;flex:none;display:inline-flex;align-items:center;justify-content:center;font-size:21px}
.twh em{font-style:normal;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.twh i{font-style:normal;font-size:14px;letter-spacing:.05em;background:rgba(255,255,255,.2);border-radius:5px;padding:2px 7px;flex:none}
.twib{display:flex;gap:14px;padding:6px 14px 10px;flex:1;min-height:0}
.twit{flex:1;min-width:0;font-size:21px;line-height:1.2}
.twit p{margin:0 0 3px}.twit b{color:#003262;display:block;font-size:15px;text-transform:uppercase;letter-spacing:.05em}
.twch{flex:none;width:400px;align-self:center}.twc{display:block;width:400px;height:236px;font-family:Calibri,Carlito,Arial,sans-serif}
.tw-btn{font-size:19px;padding:5px 16px;display:inline-flex;align-items:center}
.tw-btn[disabled]{opacity:.55;cursor:default}
.tw-status{font:700 17px Calibri,Carlito,Arial,sans-serif;color:#003262;background:#FFF3D6;border-radius:999px;padding:4px 12px;white-space:nowrap}
.tw-status[hidden]{display:none}
.live.twlive{background:transparent;outline:3px solid #FDB515;transition:opacity .35s}
.live.twlive:not(.ready){opacity:0;pointer-events:none}
.live.twlive[hidden],.live.twlive.failed{display:none}
.live[data-live="sensor"] .badge-live{left:auto;bottom:auto;right:12px;top:12px}
.stbl th,.stbl td{border:0;vertical-align:middle;text-align:left}
"""
