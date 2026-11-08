/* Ask the twin — local demo panel for grimes-bim-viewer.html?ask=1 (served by scripts/ask_twin_server.py).
   Click an element, ask a question (typed or push-to-talk); the local server answers with Claude + read-only tools
   (or scripted mock answers). Cited elements ([[id]]) become chips: verified ones are highlighted in the model and
   fly the camera on click. Nothing here writes model data; highlights are render-time colours only. */
(function () {
'use strict';
/* Access code (scripts/ask_twin_server.py prints the page link with &code=…): read from this page's URL and sent as the
   X-Ask-Code header on every call that spends credits or runs speech. Pure helpers, unit-tested in tests/ask-twin.test.cjs. */
const H = {
  accessCode(search) { return String(new URLSearchParams(search || '').get('code') || '').replace(/[\s-]+/g, '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 32); },
  headers(code, extra = {}) { return code ? {...extra, 'X-Ask-Code': code} : {...extra}; },
  /* 401 / 429 from the server -> the sentence the panel shows (null for any other status). */
  refusalText(status, body = {}) {
    const b = body || {};
    if (status === 401) return b.reason === 'code_wrong' ? 'Wrong access code. Use the link printed in the laptop terminal, or type the code below.'
      : 'Access code needed. Open the link printed in the laptop terminal (it ends with &code=…), or type the code below.';
    if (status === 429) return b.error || `Too many requests right now.${b.retry_after_s ? ` Try again in ${b.retry_after_s} s.` : ''}`;   // server text says when
    return null;
  },
};
if (typeof module === 'object' && module && module.exports) module.exports = H;
const api = typeof window !== 'undefined' && window.twinViewerApi;
if (!api) { if (typeof window !== 'undefined' && window.document) console.warn('[ask-twin] viewer API missing'); return; }
const PRIMARY = 0xff3df0, OTHER = 0x22d3ee;   // magenta / cyan: distinct from layer colours and the amber pick
const AUTOLOAD_MAX_MB = 25;   // larger layers (fire 86 MB) load only when their chip is clicked
const EXAMPLES = [
  ["Water stain", "There's a water stain on the ceiling tile here. What runs above it and what could be leaking?"],
  ["Shut-off valve", "Which valve shuts off water to this room?"],
  ["What feeds this?", "What feeds this duct?"],
];
const $ = (sel, root = document) => root.querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

const css = `
#askTwin{position:fixed;left:14px;bottom:14px;z-index:120;width:min(430px,calc(100vw - 28px));max-height:min(78vh,760px);display:flex;flex-direction:column;
 background:rgba(8,20,42,.97);border:1px solid rgba(212,167,44,.55);border-radius:12px;box-shadow:0 18px 50px rgba(0,0,0,.55);
 font:13px/1.5 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;color:#e5e9f2;overflow:hidden}
#askTwin.min .at-body{display:none}
#askTwin .at-head{display:flex;align-items:center;gap:8px;padding:10px 12px;background:linear-gradient(90deg,#0b2347,#102c57);border-bottom:1px solid rgba(212,167,44,.35);cursor:default}
#askTwin .at-logo{width:22px;height:22px;border-radius:6px;background:#d4a72c;color:#0b1f3a;display:grid;place-items:center;font-weight:800;font-size:13px}
#askTwin .at-title{font-weight:700;letter-spacing:.2px;color:#fff}
#askTwin .at-mode{margin-left:auto;font-size:10.5px;font-weight:700;letter-spacing:.5px;padding:2px 7px;border-radius:999px;border:1px solid}
#askTwin .at-mode.live{color:#86efac;border-color:#22c55e55;background:#22c55e14}
#askTwin .at-mode.mock{color:#fcd34d;border-color:#f59e0b66;background:#f59e0b14}
#askTwin .at-mode.off{color:#fca5a5;border-color:#ef444466}
#askTwin .at-x{background:none;border:0;color:#9fb0cc;font-size:16px;cursor:pointer;padding:0 2px}
#askTwin .at-body{display:flex;flex-direction:column;gap:9px;padding:11px 12px 12px;overflow:auto}
#askTwin .at-ctx{display:flex;align-items:center;gap:8px;padding:7px 9px;border-radius:8px;background:#0f2a50;border:1px dashed #36507a;color:#b9c6dc;font-size:12px}
#askTwin .at-ctx.on{border-style:solid;border-color:#d4a72c99;color:#f5e7b8}
#askTwin .at-ctx b{color:#fff}
#askTwin .at-dot{width:8px;height:8px;border-radius:50%;background:#64748b;flex:none}
#askTwin .at-ctx.on .at-dot{background:#fbbf24;box-shadow:0 0 0 3px #fbbf2433}
#askTwin .at-ex{display:flex;flex-wrap:wrap;gap:6px}
#askTwin .at-ex button{background:#11305c;border:1px solid #2b4a7c;color:#cfe0ff;border-radius:999px;padding:3px 10px;font:inherit;font-size:11.5px;cursor:pointer}
#askTwin .at-ex button:hover{border-color:#d4a72c;color:#fff}
#askTwin .at-in{display:flex;gap:6px;align-items:flex-end}
#askTwin textarea{flex:1;resize:none;min-height:40px;max-height:110px;background:#061630;color:#fff;border:1px solid #2b4a7c;border-radius:9px;padding:8px 10px;font:inherit;outline:none}
#askTwin textarea:focus{border-color:#d4a72c}
#askTwin .at-btn{height:40px;min-width:40px;border-radius:9px;border:0;cursor:pointer;font:inherit;font-weight:700}
#askTwin .at-ask{background:#d4a72c;color:#0b1f3a;padding:0 14px}
#askTwin .at-ask:disabled{opacity:.5;cursor:wait}
#askTwin .at-mic{background:#11305c;color:#e5e9f2;border:1px solid #2b4a7c;font-size:17px;touch-action:none}
#askTwin .at-mic.rec{background:#b91c1c;border-color:#ef4444;animation:atPulse 1s infinite}
@keyframes atPulse{50%{box-shadow:0 0 0 6px #ef444433}}
#askTwin .at-opts{display:flex;gap:12px;align-items:center;font-size:11.5px;color:#9fb0cc}
#askTwin .at-opts label{display:flex;gap:5px;align-items:center;cursor:pointer}
#askTwin .at-opts .at-link{margin-left:auto;background:none;border:0;color:#9fb0cc;text-decoration:underline;cursor:pointer;font:inherit}
#askTwin .at-steps{font-size:11.5px;color:#9fb0cc;border-left:2px solid #2b4a7c;padding-left:8px;display:none}
#askTwin .at-steps.on{display:block}
#askTwin .at-steps div{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#askTwin .at-steps code{color:#f2c14e;font:11px ui-monospace,Menlo,monospace}
#askTwin .at-card{display:none;background:#f8f6ef;color:#14213d;border-radius:10px;padding:12px 13px;border-top:4px solid #d4a72c;font-size:13.5px;line-height:1.5}
#askTwin .at-card.on{display:block}
#askTwin .at-card.err{border-top-color:#ef4444;background:#fff1f1}
#askTwin .at-card p{margin:0 0 6px}
#askTwin .at-card ul{margin:2px 0 7px;padding-left:18px}
#askTwin .at-card li{margin:1px 0}
#askTwin .at-card strong{color:#0b1f3a}
#askTwin .at-card .at-lead{background:#0b1f3a;color:#fff;margin:-12px -13px 9px;padding:9px 13px;border-radius:6px 6px 0 0;font-size:13.5px}
#askTwin .at-card .at-lead strong{color:#f2c14e}
#askTwin .at-card .at-lead .at-chip{background:#d4a72c;color:#0b1f3a;border-color:#d4a72c}
#askTwin .at-chip{display:inline-flex;align-items:center;gap:4px;border:1px solid #0b1f3a33;background:#e7eefb;color:#0b1f3a;border-radius:6px;padding:0 6px;margin:0 1px;font:600 12px/1.6 inherit;cursor:pointer;vertical-align:baseline}
#askTwin .at-chip:hover{background:#d4a72c;border-color:#d4a72c}
#askTwin .at-chip i{font-style:normal;font-weight:400;opacity:.65;font-size:11px}
#askTwin .at-chip.bad{background:#fde2e2;color:#991b1b;text-decoration:line-through;cursor:help}
#askTwin .at-foot{font-size:11px;color:#9fb0cc;display:flex;flex-wrap:wrap;gap:4px 10px}
#askTwin .at-foot b{color:#e5e9f2;font-weight:600}
#askTwin .at-code{display:flex;gap:6px;margin-top:6px}
#askTwin .at-code input{flex:1;min-width:0;border:1px solid #c9b88a;border-radius:7px;padding:5px 8px;font:600 14px/1.3 ui-monospace,Menlo,monospace;letter-spacing:2px;text-transform:uppercase}
#askTwin .at-code button{border:0;border-radius:7px;background:#0b1f3a;color:#fff;font:inherit;font-weight:700;padding:0 12px;cursor:pointer}
#askTwin .at-cursor::after{content:'▍';color:#d4a72c;animation:atBlink 1s steps(2) infinite}
@keyframes atBlink{50%{opacity:0}}
#askTwinMarker{position:fixed;z-index:110;pointer-events:none;transform:translate(-50%,-100%);display:none}
#askTwinMarker .tag{background:#d61fc0;color:#fff;font:700 11px/1 Inter,system-ui,sans-serif;padding:5px 8px;border-radius:6px;white-space:nowrap;box-shadow:0 4px 14px rgba(0,0,0,.4)}
#askTwinMarker .stem{width:2px;height:22px;background:#ff3df0;margin:0 auto}
#askTwinMarker .ring{width:16px;height:16px;border:2px solid #ff3df0;border-radius:50%;margin:-2px auto 0;animation:atPulse 1.2s infinite}
@media (max-width:640px){#askTwin{left:8px;right:8px;bottom:8px;width:auto;max-height:60vh}}
`;
document.head.appendChild(Object.assign(document.createElement('style'), {textContent: css}));

const panel = Object.assign(document.createElement('section'), {id: 'askTwin'});
panel.setAttribute('aria-label', 'Ask the twin');
panel.innerHTML = `
 <div class="at-head"><div class="at-logo">?</div><div class="at-title">Ask the twin</div>
  <span class="at-mode off" id="atMode">connecting…</span><button class="at-x" id="atMin" title="Minimise">–</button></div>
 <div class="at-body">
  <div class="at-ctx" id="atCtx"><span class="at-dot"></span><span>Click an element in the model, then ask about it.</span></div>
  <div class="at-ex" id="atEx">${EXAMPLES.map(([l, q], i) => `<button data-i="${i}" title="${esc(q)}">${esc(l)}</button>`).join('')}</div>
  <div class="at-in"><textarea id="atQ" rows="2" placeholder="Ask about the selected element…  (Enter to ask)"></textarea>
   <button class="at-btn at-mic" id="atMic" title="Hold to talk">🎙</button><button class="at-btn at-ask" id="atAsk">Ask</button></div>
  <div class="at-opts"><label><input type="checkbox" id="atSpeak"> Speak answers</label><span id="atStt"></span>
   <button class="at-link" id="atClear" title="Clear highlights and follow-up memory">Clear</button></div>
  <div class="at-steps" id="atSteps"></div>
  <div class="at-card" id="atCard" aria-live="polite"></div>
  <div class="at-foot" id="atFoot"></div>
 </div>`;
document.body.appendChild(panel);
const marker = Object.assign(document.createElement('div'), {id: 'askTwinMarker'});
marker.innerHTML = '<div class="tag">Most likely source</div><div class="stem"></div><div class="ring"></div>';
document.body.appendChild(marker);
// Typing in the panel must not drive the viewer's keyboard shortcuts (Walk, cards, ...).
for (const t of ['keydown', 'keyup', 'keypress']) panel.addEventListener(t, e => e.stopPropagation());

const state = {sel: null, point: null, busy: false, history: [], markerAt: null, stt: false, health: null, lastCites: [],
  code: H.accessCode(location.search), lastQuestion: ''};
class Refused extends Error { constructor(msg, status) { super(msg); this.status = status; } }
async function refusal(res) {   // 401 / 429 -> Refused with the friendly text; other errors -> null
  let body = {}; try { body = await res.clone().json(); } catch (e) { /* not JSON */ }
  const t = H.refusalText(res.status, body);
  return t ? new Refused(t, res.status) : null;
}
function showCodeBox(msg) {
  const card = $('#atCard');
  card.className = 'at-card on err';
  card.innerHTML = `<p><strong>Could not answer.</strong> ${esc(msg)}</p><div class="at-code"><input id="atCode" placeholder="Access code" maxlength="32" autocomplete="off" spellcheck="false"><button id="atCodeGo">Use code</button></div>`;
  const go = () => { const c = H.accessCode('?code=' + encodeURIComponent($('#atCode').value)); if (!c) return; state.code = c;
    card.className = 'at-card'; if (state.lastQuestion) ask(state.lastQuestion); };
  $('#atCodeGo').onclick = go;
  $('#atCode').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); go(); } });
}

// ---------- selection context (fed by the viewer's pickEquipment) ----------
window.__askTwin = {
  onPick(id, info, point) {
    state.sel = id; state.point = point || null;
    const ctx = $('#atCtx');
    ctx.classList.add('on');
    const label = info.type || info.category || info.name || 'Element';
    ctx.innerHTML = `<span class="at-dot"></span><span>Selected: <b>${esc(label)}</b> · ${esc(info.levelKey || info.level || '')} · ${esc(info.layer || '')} <span style="opacity:.7">#${esc(id)}</span>${point ? ' · point ✓' : ''}</span>`;
  },
};

// ---------- health / mode ----------
fetch('/api/health').then(r => r.json()).then(h => {
  state.health = h;
  const m = $('#atMode');
  m.className = 'at-mode ' + (h.mode === 'live' ? 'live' : 'mock');
  m.textContent = h.mode === 'live' ? `LIVE · ${h.model}` : 'MOCK · no API key';
  m.title = h.mode === 'live' ? 'Answers from the Claude API using read-only twin tools' : 'Scripted answers built from the same read-only tools (no API call)';
  state.stt = !!h.stt?.available;
  if (h.access?.code_required && !state.code) showCodeBox(H.refusalText(401, {reason: 'code_required'}));
  $('#atStt').textContent = state.stt ? '🎙 local whisper' : (webSpeech() ? '🎙 browser speech' : '');
}).catch(() => { $('#atMode').textContent = 'server offline'; });

// ---------- markdown-lite with citation chips ----------
function chip(id) {
  const c = state.lastCites.find(x => x.id === id);
  const meta = api.meta(id);
  const label = (c?.type || meta?.type || c?.layer || 'element');
  if (c && !c.verified) return `<span class="at-chip bad" title="Not returned by any tool in this answer: not highlighted">${esc(id)}</span>`;
  return `<button class="at-chip" data-id="${esc(id)}" title="Fly to and select #${esc(id)}">${esc(label)} <i>#${esc(id)}</i></button>`;
}
function render(text) {
  const lines = esc(text).split('\n');
  let html = '', inList = false, first = true;
  for (let line of lines) {
    line = line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/\[\[([A-Za-z0-9_.:-]{1,40})\]\]/g, (_, id) => chip(id));
    const li = /^\s*[-•]\s+(.*)$/.exec(line);
    if (li) { if (!inList) { html += '<ul>'; inList = true; } html += `<li>${li[1]}</li>`; continue; }
    if (inList) { html += '</ul>'; inList = false; }
    if (!line.trim()) continue;
    const lead = first && /^<strong>(Most likely source|Answer):<\/strong>/.test(line);
    html += lead ? `<p class="at-lead">${line}</p>` : `<p>${line}</p>`;
    first = false;
  }
  if (inList) html += '</ul>';
  return html;
}

// ---------- camera fly + marker ----------
function boxOf(id) { return state.lastCites.find(c => c.id === id)?.bbox_m || null; }
function flyTo(b) {
  if (!b) return;
  const {THREE, camera, controls} = api;
  const c = new THREE.Vector3((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2);
  const diag = Math.hypot(b[3] - b[0], b[4] - b[1], b[5] - b[2]);
  const dist = Math.min(22, Math.max(4.5, diag * 2.2));
  const dir = camera.position.clone().sub(controls.target).normalize();
  if (dir.y < 0.25) { dir.y = 0.25; dir.normalize(); }   // keep a slight top-down view into the plenum
  const p1 = c.clone().add(dir.multiplyScalar(dist)), p0 = camera.position.clone(), t0 = controls.target.clone();
  const start = performance.now(), dur = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 750;
  (function step(now) {
    const k = dur ? Math.min(1, (now - start) / dur) : 1, e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    camera.position.lerpVectors(p0, p1, e); controls.target.lerpVectors(t0, c, e); controls.update();
    if (k < 1) requestAnimationFrame(step);
  })(start);
}
function trackMarker() {
  const {THREE, camera} = api, canvas = document.querySelector('canvas');
  if (state.markerAt && canvas) {
    const v = new THREE.Vector3(...state.markerAt).project(camera), r = canvas.getBoundingClientRect();
    const vis = v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1;
    marker.style.display = vis ? 'block' : 'none';
    marker.style.left = (r.left + (v.x + 1) / 2 * r.width) + 'px';
    marker.style.top = (r.top + (1 - v.y) / 2 * r.height) + 'px';
  } else marker.style.display = 'none';
  requestAnimationFrame(trackMarker);
}
requestAnimationFrame(trackMarker);

// Box outlines drawn on top (no depth test): cited elements stay findable even inside dense MEP or when their
// layer is not loaded. Overlay only; removed on the next answer or Clear.
const boxGroup = new api.THREE.Group(); boxGroup.name = 'ask-twin:citations'; boxGroup.renderOrder = 999; api.scene.add(boxGroup);
function clearBoxes() { for (const o of [...boxGroup.children]) { boxGroup.remove(o); o.geometry?.dispose(); o.material?.dispose(); } }
function addBox(b, color, pad) {
  const {THREE} = api, box = new THREE.Box3(new THREE.Vector3(b[0] - pad, b[1] - pad, b[2] - pad), new THREE.Vector3(b[3] + pad, b[4] + pad, b[5] + pad));
  const h = new THREE.Box3Helper(box, color); h.material.depthTest = false; h.material.transparent = true; h.material.opacity = .95; h.renderOrder = 999;
  boxGroup.add(h);
}
async function showCitations(cites, answer) {
  api.clearHighlights(); clearBoxes();
  const lead = /^\s*\*\*(Most likely source|Answer):\*\*[^\n]*?\[\[([A-Za-z0-9_.:-]+)\]\]/.exec(answer || '');
  const primary = lead ? lead[2] : null;
  const ok = cites.filter(c => c.verified && c.in_viewer);
  const layers = [...new Set(ok.map(c => c.layer))];
  for (const key of layers) {
    if (api.isLoaded(key)) continue;
    const mb = api.LAYERS[key]?.mb || 0;
    if (mb <= AUTOLOAD_MAX_MB) await api.loadLayer(key);
  }
  for (const c of ok) api.highlight([c.id], c.id === primary ? PRIMARY : OTHER);
  for (const c of cites) if (c.verified && c.bbox_m) addBox(c.bbox_m, c.id === primary ? PRIMARY : OTHER, c.id === primary ? 0.08 : 0.04);
  const pc = primary && cites.find(c => c.id === primary && c.verified);
  state.markerAt = pc ? [(pc.bbox_m[0] + pc.bbox_m[3]) / 2, pc.bbox_m[4], (pc.bbox_m[2] + pc.bbox_m[5]) / 2] : null;
  if (pc) flyTo(pc.bbox_m);
}

$('#atCard').addEventListener('click', async e => {
  const b = e.target.closest('.at-chip[data-id]'); if (!b) return;
  const id = b.dataset.id, c = state.lastCites.find(x => x.id === id);
  if (c && c.in_viewer && !api.isLoaded(c.layer)) { b.textContent = `loading ${c.layer}…`; await api.loadLayer(c.layer); }
  if (c && c.in_viewer) { api.highlight([id], OTHER); api.select(id); }
  flyTo(boxOf(id));
  if (c) state.markerAt = [(c.bbox_m[0] + c.bbox_m[3]) / 2, c.bbox_m[4], (c.bbox_m[2] + c.bbox_m[5]) / 2];
  setTimeout(() => { if (b.isConnected && !b.querySelector('i')) b.innerHTML = `${esc(c?.type || 'element')} <i>#${esc(id)}</i>`; }, 50);
});

// ---------- ask ----------
async function ask(question) {
  question = (question || '').trim();
  if (!question || state.busy) return;
  state.lastQuestion = question;
  state.busy = true; $('#atAsk').disabled = true; $('#atAsk').textContent = '…';
  speechSynthesis?.cancel?.();
  const steps = $('#atSteps'), card = $('#atCard'), foot = $('#atFoot');
  steps.innerHTML = ''; steps.classList.add('on'); card.className = 'at-card on'; foot.textContent = '';
  card.innerHTML = '<p class="at-cursor" style="color:#5b6b85">Looking it up in the twin…</p>';
  state.lastCites = []; state.markerAt = null; api.clearHighlights(); clearBoxes();
  let text = '', final = null, pending = false;
  const paint = () => { pending = false; card.innerHTML = render(text) + (final ? '' : '<span class="at-cursor"></span>'); };
  try {
    const res = await fetch('/api/ask', {method: 'POST', headers: H.headers(state.code, {'Content-Type': 'application/json'}),
      body: JSON.stringify({question, element_id: state.sel, point: state.point, history: state.history})});
    if (!res.ok) throw (await refusal(res)) || new Error(`server ${res.status}`);
    if (!res.body) throw new Error(`server ${res.status}`);
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const {value, done} = await reader.read(); if (done) break;
      buf += dec.decode(value, {stream: true});
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
        if (!chunk.startsWith('data: ')) continue;
        const ev = JSON.parse(chunk.slice(6));
        if (ev.type === 'tool') steps.insertAdjacentHTML('beforeend', `<div>✓ <code>${esc(ev.name)}</code> ${esc(ev.summary || '')}</div>`);
        else if (ev.type === 'status') steps.insertAdjacentHTML('beforeend', `<div>${esc(ev.text)}</div>`);
        else if (ev.type === 'text') { text += ev.text; if (!pending) { pending = true; requestAnimationFrame(paint); } }
        else if (ev.type === 'error') throw new Error(ev.message);
        else if (ev.type === 'final') final = ev;
      }
    }
    if (!final) throw new Error('the answer stream ended early');
    text = final.answer || text; state.lastCites = final.citations || [];
    paint();
    const nv = state.lastCites.filter(c => c.verified).length, nb = state.lastCites.length - nv;
    foot.innerHTML = `<span><b>${final.mode === 'live' ? 'Claude' : 'Mock'}</b> · ${esc(final.model)}</span><span>${final.tools_used.length} read-only lookups</span>`
      + `<span>${nv} cited element${nv === 1 ? '' : 's'} verified${nb ? ` · <b style="color:#fca5a5">${nb} unverified</b>` : ''}</span><span>${final.seconds}s</span>`
      + `<span>Sources: design BIM · geometry · <b>simulated</b> demo sensors</span>`;
    state.history.push({q: question, a: text}); state.history = state.history.slice(-3);
    await showCitations(state.lastCites, text);
    if ($('#atSpeak').checked) speak(final.spoken || text, !!final.spoken);   // server's short spoken version (lead + one check)
  } catch (e) {
    if (e instanceof Refused && e.status === 401) { steps.classList.remove('on'); showCodeBox(e.message); return; }
    card.className = 'at-card on err';
    card.innerHTML = `<p><strong>Could not answer.</strong> ${esc(e.message)}</p>`;
  } finally {
    state.busy = false; $('#atAsk').disabled = false; $('#atAsk').textContent = 'Ask';
  }
}
$('#atAsk').onclick = () => ask($('#atQ').value);
$('#atQ').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask($('#atQ').value); } });
$('#atEx').addEventListener('click', e => { const b = e.target.closest('button[data-i]'); if (!b) return; $('#atQ').value = EXAMPLES[b.dataset.i][1]; ask(EXAMPLES[b.dataset.i][1]); });
$('#atMin').onclick = () => { panel.classList.toggle('min'); $('#atMin').textContent = panel.classList.contains('min') ? '+' : '–'; };
$('#atClear').onclick = () => { api.clearHighlights(); clearBoxes(); state.history = []; state.lastCites = []; state.markerAt = null;
  $('#atCard').className = 'at-card'; $('#atSteps').className = 'at-steps'; $('#atFoot').textContent = ''; };

// ---------- voice: push-to-talk in, speechSynthesis out ----------
function speak(text, ready = false) {
  if (!window.speechSynthesis) return;
  const plain = ready ? text : text.replace(/\[\[([^\]]+)\]\]/g, (_, id) => (state.lastCites.find(c => c.id === id)?.type || 'element'))
    .replace(/\*\(mock mode[^)]*\)\*/g, '').replace(/[*#]/g, '').replace(/~/g, 'about ').replace(/·/g, ',').replace(/\bdegC\b/g, 'degrees')
    .split('\n').filter(l => !/^Limits:/.test(l.trim())).slice(0, 8).join('. ');
  const u = new SpeechSynthesisUtterance(plain); u.rate = 1.05; u.lang = 'en-US';
  speechSynthesis.cancel(); speechSynthesis.speak(u);
}
function webSpeech() { return window.SpeechRecognition || window.webkitSpeechRecognition || null; }
const mic = $('#atMic');
let rec = null, chunks = [], stream = null, recog = null, recogText = '', holding = false, recStarted = 0;
async function startTalk() {
  if (state.busy || rec || recog) return;
  holding = true;
  speechSynthesis?.cancel?.();
  mic.classList.add('rec'); $('#atQ').placeholder = 'Starting microphone…';
  if (state.stt && navigator.mediaDevices?.getUserMedia && window.MediaRecorder) {
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}});
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'].find(t => MediaRecorder.isTypeSupported?.(t)) || '';
      rec = new MediaRecorder(stream, type ? {mimeType: type} : undefined); chunks = [];
      rec.ondataavailable = e => e.data.size && chunks.push(e.data);
      rec.start(250); recStarted = performance.now();
      $('#atQ').placeholder = 'Listening… release to ask';
      if (!holding) stopTalk();   // released while the microphone permission/startup was pending
      return;
    } catch (e) { console.warn('[ask-twin] mic:', e); stopTracks(); }
  }
  const SR = webSpeech();
  if (!SR) { mic.classList.remove('rec'); $('#atQ').placeholder = 'No microphone speech available here: type your question'; return; }
  recog = new SR(); recog.lang = 'en-US'; recog.interimResults = true; recog.continuous = true; recogText = '';
  recog.onresult = e => { recogText = [...e.results].map(r => r[0].transcript).join(' '); $('#atQ').value = recogText; };
  recog.start(); $('#atQ').placeholder = 'Listening (browser speech)… release to ask';
}
function stopTracks() { stream?.getTracks().forEach(t => t.stop()); stream = null; }
async function stopTalk() {
  holding = false;
  mic.classList.remove('rec'); $('#atQ').placeholder = 'Ask about the selected element…  (Enter to ask)';
  if (rec) {
    const r = rec; rec = null;
    await new Promise(res => { r.onstop = res; r.stop(); });
    stopTracks();
    const blob = new Blob(chunks, {type: r.mimeType || 'audio/webm'});
    if (blob.size < 1500 || performance.now() - recStarted < 500) { $('#atQ').placeholder = 'Too short: hold 🎙 while you speak, then release'; return; }
    $('#atQ').value = 'Transcribing…';
    try {
      const res = await fetch('/api/transcribe', {method: 'POST', headers: H.headers(state.code, {'Content-Type': blob.type}), body: blob});
      if (!res.ok) { const r = await refusal(res); if (r) { $('#atQ').value = ''; if (r.status === 401) showCodeBox(r.message); throw r; } }
      const j = await res.json();
      if (!res.ok) throw new Error(j.error || res.status);
      $('#atQ').value = j.text || '';
      if (j.text) ask(j.text);
    } catch (e) { $('#atQ').value = ''; $('#atQ').placeholder = `Speech-to-text failed (${e.message}); type instead`; }
  } else if (recog) {
    const r = recog; recog = null;
    await new Promise(res => { r.onend = res; r.stop(); setTimeout(res, 1200); });
    if (recogText.trim()) ask(recogText);
  }
}
mic.addEventListener('pointerdown', e => { e.preventDefault(); mic.setPointerCapture?.(e.pointerId); startTalk(); });
for (const t of ['pointerup', 'pointercancel']) mic.addEventListener(t, () => stopTalk());
})();
