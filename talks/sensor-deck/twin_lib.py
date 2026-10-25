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

def spark(vals, col='#003262', warn_from=None):
    n = len(vals); lo, hi = min(vals), max(vals); rng = (hi - lo) or 1
    pts = [(4 + i * 112 / (n - 1), 26 - (v - lo) / rng * 22) for i, v in enumerate(vals)]
    d = ' '.join(f'{a:.1f},{b:.1f}' for a, b in pts)
    dot = f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.2" fill="{col}"/>'
    return f'<svg class="spk" viewBox="0 0 120 30"><polyline points="{d}" fill="none" stroke="{col}" stroke-width="2" stroke-linejoin="round"/>{dot}</svg>'

def marker_group(k, title, drawing, hit):
    hx, hy, hr = hit
    return (f'<g class="mk" data-m="{k}" tabindex="0" role="button" aria-label="{e(title)}"><circle cx="{hx}" cy="{hy}" r="{hr}" fill="rgba(0,0,0,.001)"/>{drawing}</g>')

def build_twin(sc, U, x, y, h):
    """Return (html, js-config) for one scenario. sc keys: slug, base, fallback, elements[], bg (svg under markers), defs, anim, live."""
    w = h * IMG_W / IMG_H; slug = sc['slug']
    px = lambda v: f'{v*U:.1f}px'
    pos = lambda a, b, c, d: f'left:{px(a)};top:{px(b)};width:{px(c)};height:{px(d)}'
    defs = ('<filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="9"/></filter>' + sc.get('defs', ''))
    groups = ''; cards = ''; cfg = {}
    for el in sc['elements']:
        k = el['k']
        groups += marker_group(k, el['title'], el['draw'], el['hit'])
        el.setdefault('sid', '')
        cfg[k] = el['badge']
        sp = f'<div class="twspk">{el["spark"]}<span>{e(el.get("spark_note",""))}</span></div>' if el.get('spark') else ''
        cards += (f'<div class="twcard" data-m="{k}" hidden><div class="twh" style="background:{el["col"]}"><span>{k}</span>{e(el["title"])}</div>'
                  f'<p><b>What it is</b> {e(el["what"])}</p><p><b>Illustrative reading</b> {e(el["val"])}</p>{sp}'
                  f'<p><b>Maps to</b> {e(el.get("maps","BIM element ID"))}</p></div>')
    svg = (f'<svg class="tw-svg" viewBox="0 0 {IMG_W} {IMG_H}" style="position:absolute;inset:0;width:100%;height:100%" xmlns="http://www.w3.org/2000/svg">'
           f'<defs>{defs}</defs><g class="tw-sensors">{sc.get("bg","")}{groups}</g></svg>')
    base = (f'<img class="tw-base" src="img/{sc["base"]}" alt="{e(sc.get("alt","Level 1 ceiling in the Lens overlay (May 6 capture)"))}" style="position:absolute;inset:0;width:100%;height:100%" data-fallback="{sc.get("fallback","")}">')
    out = f'<div class="tw" data-slug="{slug}" data-anim="{sc.get("anim","")}" data-w="{IMG_W}" data-h="{IMG_H}" data-pts=\'{__import__("json").dumps(cfg)}\' style="{pos(x,y,w,h)}">{base}{svg}{cards}</div>'
    # LIVE layer on top of the static figure: the local viewer with ?sensors=demo, loaded only while this slide is active
    # (deck.js: data-nopreload). The static image + SVG underneath stays as the fallback (Static view, or iframe failure).
    out += (f'<div class="live twlive" data-live="sensor" data-nopreload="1" data-clean="1" data-scale="0.72" data-src="{e(sc["live"])}" style="{pos(x,y,w,h)}">'
            '<div class="vp"></div><span class="loading">Loading live twin…</span><span class="badge-live">LIVE 3D · drag to look</span></div>')
    out += (f'<div style="{pos(x,y+h+.1,w+2,.32)};display:flex;gap:10px"><button class="btn tw-btn tw-toggle" aria-pressed="true">Sensors: on</button>'
            '<button class="btn tw-btn tw-mode" aria-pressed="false">Static view</button>'
            f'<a class="btn tw-btn" href="{e(sc["live"])}" target="_blank" rel="noopener">Open in viewer ↗</a></div>')
    return out, w

TWIN_JS = r"""
document.querySelectorAll('.tw').forEach(tw=>{
const sl=tw.closest('.slide'),base=tw.querySelector('.tw-base'),svg=tw.querySelector('.tw-svg'),MP=JSON.parse(tw.dataset.pts),IW=+tw.dataset.w,IH=+tw.dataset.h;
const cards=[...tw.querySelectorAll('.twcard')],rows=[...sl.querySelectorAll('.twrow')],mks=[...tw.querySelectorAll('.mk')],tg=sl.querySelector('.tw-toggle'),grp=tw.querySelector('.tw-sensors');
base.addEventListener('error',()=>{if(base.dataset.fallback){base.src=base.dataset.fallback}svg.remove();cards.forEach(c=>c.remove());if(tg)tg.remove();tw.classList.add('fallback')},{once:true});
let pinned=null,hover=null,on=true;
const live=sl.querySelector('.twlive'),mode=sl.querySelector('.tw-mode'),SID={};rows.forEach(r=>{if(r.dataset.sid)SID[+r.dataset.m]=r.dataset.sid});
const liveOn=()=>live&&!live.hidden&&!live.classList.contains('failed');
const liveFrame=()=>{const f=live&&live.querySelector('iframe');return liveOn()&&f&&f.contentWindow?f:null};
function focusLive(){const f=liveFrame();if(!f)return;const k=pinned||hover;try{f.contentWindow.postMessage({type:'grimes-sensor-demo-focus',id:(on&&k&&SID[k])||null},location.origin)}catch(_){}}
function setMode(stat){if(!live)return;live.hidden=stat;live.dataset.off=stat?'1':'';mode.setAttribute('aria-pressed',String(stat));mode.textContent=stat?'Live 3D view':'Static view';
  if(stat)unloadLive(live);else if(sl.classList.contains('active'))loadLive(live);mode.blur()}
if(mode)mode.addEventListener('click',()=>setMode(!live.hidden));
if(live)new MutationObserver(()=>{if(live.classList.contains('failed')&&mode){mode.textContent='Live view unavailable';mode.disabled=true}}).observe(live,{attributes:true,attributeFilter:['class']});
function render(){const k=pinned||hover;
  cards.forEach(c=>{const m=+c.dataset.m,show=on&&k===m&&!liveOn();c.hidden=!show;   /* live: the viewer shows its own card */
    if(show){const W=tw.clientWidth,H=tw.clientHeight,[mx,my]=MP[m],X=mx/IW*W,Y=my/IH*H,cw=c.offsetWidth,ch=c.offsetHeight;
      let L=X>W*.5?X-cw-30:X+30;L=Math.max(8,Math.min(W-cw-8,L));let T=Math.max(8,Math.min(H-ch-8,Y-ch/2));c.style.left=L+'px';c.style.top=T+'px'}});
  rows.forEach(r=>r.classList.toggle('on',on&&+r.dataset.m===k));
  mks.forEach(g=>g.classList.toggle('on',+g.dataset.m===k));focusLive()}
function wire(el,m){el.addEventListener('mouseenter',()=>{hover=m;render()});el.addEventListener('mouseleave',()=>{hover=null;render()});
  el.addEventListener('click',ev=>{ev.stopPropagation();pinned=pinned===m?null:m;render()});
  el.addEventListener('keydown',ev=>{if(ev.key==='Enter'){ev.stopPropagation();pinned=pinned===m?null:m;render()}})}
mks.forEach(g=>wire(g,+g.dataset.m));rows.forEach(r=>wire(r,+r.dataset.m));
tw.addEventListener('click',()=>{pinned=null;render()});
if(tg)tg.addEventListener('click',()=>{on=!on;grp.style.display=on?'':'none';
  try{const f=liveFrame(),b=f&&f.contentDocument.getElementById('sdToggle');if(b&&(b.getAttribute('aria-pressed')==='true')!==on)b.click()}catch(_){}tg.textContent='Sensors: '+(on?'on':'off');tg.setAttribute('aria-pressed',on);tg.blur();if(!on)pinned=null;render()});
addEventListener('hashchange',()=>{pinned=null;hover=null;render()});
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
.tw .mk{cursor:pointer;outline:none}.tw .mk:focus-visible{filter:drop-shadow(0 0 6px #FDB515)}.tw .mk.on{filter:drop-shadow(0 0 5px #FDB515)}
.twcard{position:absolute;z-index:5;width:451px;background:#fff;border-radius:10px;box-shadow:0 6px 18px rgba(0,0,0,.4);font-size:18.2px;line-height:1.25;overflow:hidden;pointer-events:none;color:#1F2A37}
.twcard[hidden]{display:none}
.twcard p{margin:0;padding:6px 14px 0}.twcard p:last-child{padding-bottom:12px}.twcard b{color:#003262;display:block;font-size:.82em;text-transform:uppercase;letter-spacing:.04em}
.twh{color:#fff;font-weight:700;font-size:20px;padding:8px 14px;display:flex;align-items:center;gap:10px}
.twh span{background:#fff;color:#1F2A37;border-radius:50%;width:28px;height:28px;flex:none;display:inline-flex;align-items:center;justify-content:center;font-size:17px}
.twspk{display:flex;align-items:center;gap:10px;padding:2px 14px 0}.spk{width:150px;height:38px;flex:none}.twspk span{font-size:.8em;color:#5B7089}
.twrow{transition:background .15s,outline-color .15s;outline:3px solid transparent;outline-offset:-1px}.twrow.on{background:#FFF3D6;outline-color:#FDB515}
.tw-btn{font-size:19px;padding:5px 16px;display:inline-flex;align-items:center}
.tw-btn[disabled]{opacity:.55;cursor:default}
.live.twlive{background:transparent;outline:3px solid #FDB515}
.live.twlive[hidden],.live.twlive.failed{display:none}
.live[data-live="sensor"] .badge-live{left:auto;bottom:auto;right:12px;top:12px}
.stbl th,.stbl td{border:0;vertical-align:middle;text-align:left}
"""
