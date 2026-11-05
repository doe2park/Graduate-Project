/* Ask the twin inside the headset page (scan-xr.html?ask=1, served by scripts/ask_twin_server.py on the laptop).
   DOM overlays are invisible in an immersive session, so everything the user sees is drawn on 2D canvases that the page
   puts on planes in the scene. This file holds the logic and the drawing only (no three.js, no DOM queries):
     - the preset questions of the four levels (look up · nearby in 3D · trace a system · reason across sources),
     - the answer stream parser (Server-Sent Events from /api/ask),
     - the short in-view answer card (lead, 2-3 bullets, cited ids, provenance footer) and its canvas drawing with the Claude badge,
     - the spoken text, the run lighting timing for connected_run, the ask-bar layout and hit test, and the voice/TTS plans.
   Unit-tested in tests/xr-ask.test.cjs. The page is unchanged unless it is opened with ?ask=1. NOT verified on a headset. */
(function (root, factory) {
  const api = factory();
  if (root) root.XRAsk = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';

const API = 2;
const CITE_RX = /\[\[([A-Za-z0-9_.:-]{1,40})\]\]/g;
const LEVELS = [
  {level: 1, id: 'q1', label: 'What is this?', hint: 'look up', question: 'What is this, and what room am I in?'},
  {level: 2, id: 'q2', label: "What's above?", hint: 'nearby in 3D', question: 'What is above this ceiling tile within 2 m?'},
  {level: 3, id: 'q3', label: 'What feeds it?', hint: 'trace a system', question: 'Which VAV box feeds this?'},
  {level: 4, id: 'q4', label: 'Why is it warm?', hint: 'reason across sources', question: 'This room is warm from 9 to 5 every weekday. What is the likely cause, and where do I check first?'},
];
const COLORS = {primary: 0xff3df0, other: 0x22d3ee, run: 0x22d3ee};   // same magenta / cyan as the laptop panel (twin/ask-twin.js)
const CLAUDE = {orange: '#D97757', cream: '#F4EFE6'};

/* ?ask=1 turns the feature on. Anything else (absent, 0, off) leaves the page exactly as it was.
   &server=https://<laptop LAN IP>:<port> ("Method A"): the page itself comes from anywhere (e.g. GitHub Pages) and only the
   AI calls (health, ask, transcribe, speak) go to the laptop. Validated by serverOrigin; an invalid value is ignored.
   &voice=headset prefers the headset browser's own voice over the laptop voice. */
function parseParams(search) {
  const q = new URLSearchParams(search || ''), raw = q.get('server');
  const server = raw == null ? null : serverOrigin(raw);
  return {enabled: q.get('ask') === '1', server, serverIgnored: raw != null && !server, preferVoice: q.get('voice') === 'headset' ? 'browser' : 'laptop'};
}
/* server= must be https, a private-LAN IPv4 (10/8, 172.16/12, 192.168/16) or localhost, with an explicit port and nothing
   else (no path, query, user). Returns the origin "https://host:port" or null. Nothing is ever sent to any other host. */
function privateIPv4(host) {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host || '');
  if (!m) return false;
  const o = m.slice(1).map(Number);
  if (o.some(n => n > 255) || m.slice(1).some(t => t.length > 1 && t[0] === '0')) return false;
  return o[0] === 10 || (o[0] === 172 && o[1] >= 16 && o[1] <= 31) || (o[0] === 192 && o[1] === 168) || (o[0] === 127 && o[1] === 0 && o[2] === 0 && o[3] === 1);
}
function serverOrigin(raw) {
  const s = String(raw || '').trim();
  if (!/^https:\/\/[^/?#@\s]+(\/)?$/i.test(s)) return null;   // https only, no path, query, fragment or credentials
  let u; try { u = new URL(s); } catch (e) { return null; }
  if (u.protocol !== 'https:' || u.username || u.password || !u.port) return null;   // explicit (non-443) port required
  const host = u.hostname.toLowerCase(), typed = /^https:\/\/([^:/]+)/i.exec(s)[1].toLowerCase();
  if (typed !== host) return null;   // refuse anything the URL parser had to rewrite (0x7f.1, 192.168.001.2, ...)
  if (!(host === 'localhost' || privateIPv4(host))) return null;
  return 'https://' + host + ':' + u.port;
}
/* API URL: same origin (relative, as before) or the validated laptop origin. */
function apiUrl(base, name) { return (base ? base + '/' : '') + 'api/' + name; }
/* Health check failed: what the 2D box says, and (Method A) the one-tap link that makes the headset accept the laptop's
   self-signed certificate (a fetch cannot show the certificate warning; opening the address once in a tab can). */
function healthProblem({server = null, error = '', ignored = false, sameOrigin = true} = {}) {
  if (ignored) return {text: 'server= ignored: use https://<private LAN IP>:<port>, e.g. https://192.168.1.20:8765', trustUrl: null};
  if (server) return {text: 'Laptop not reached (' + (error || 'network') + '). Same Wi-Fi? Server running with --lan? First time: open the link below once and accept the certificate, then Retry.',
    trustUrl: server + '/trust', trustLabel: 'Open ' + server + '/ once to trust it'};
  return {text: sameOrigin ? 'Open this page from scripts/ask_twin_server.py (--lan for the Quest), or add &server=https://<laptop IP>:8765' : 'No ask server', trustUrl: null};
}

/* Server-Sent Events from /api/ask: "data: {json}\n\n" blocks, split across arbitrary network chunks. */
function createStream(onEvent) {
  let buf = '';
  const take = () => {
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, i); buf = buf.slice(i + 2);
      for (const line of block.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        let ev = null;
        try { ev = JSON.parse(line.slice(6)); } catch (e) { ev = {type: 'error', message: 'unreadable server event'}; }
        onEvent(ev);
      }
    }
  };
  return {push(text) { buf += text; take(); }, end() { if (buf.trim()) { buf += '\n\n'; take(); } buf = ''; }};
}

const MOCK_TAG = /\s*\*\((?:mock mode)[^)]*\)\*/g;
function plainLine(s, idText = id => '#' + id) {
  return String(s || '').replace(MOCK_TAG, '').replace(CITE_RX, (_, id) => idText(id)).replace(/\*\*(.+?)\*\*/g, '$1').replace(/\*(.+?)\*/g, '$1').replace(/\s+/g, ' ').trim();
}
/* The first cited id of the lead line (**Most likely source:** / **Answer:**): the element the answer is about. */
function leadId(answer) {
  const m = /^\s*\*\*(?:Most likely source|Answer):\*\*[^\n]*?\[\[([A-Za-z0-9_.:-]{1,40})\]\]/.exec(answer || '');
  return m ? m[1] : null;
}
/* Markdown-lite answer -> {lead, sections: {name: [lines]}, limits}. Sections are the bold "**Name:**" lines of the card format. */
function sections(answer) {
  const out = {lead: '', leadKind: null, sections: {}, order: [], limits: ''};
  let cur = null;
  for (const raw of String(answer || '').replace(MOCK_TAG, '').split('\n')) {
    const line = raw.trim(); if (!line) continue;
    const h = /^\*\*([A-Za-z ]{2,30}):\*\*\s*(.*)$/.exec(line);
    if (h) {
      const name = h[1].trim();
      if (!out.lead && /^(Most likely source|Answer)$/.test(name)) { out.lead = h[2]; out.leadKind = name; cur = null; continue; }
      if (name === 'Limits') { out.limits = h[2]; cur = null; continue; }
      cur = name; out.sections[cur] = out.sections[cur] || []; out.order.push(cur);
      if (h[2]) out.sections[cur].push(h[2]);
      continue;
    }
    const li = /^[-•]\s+(.*)$/.exec(line);
    if (cur) out.sections[cur].push(li ? li[1] : line);
    else if (!out.lead) out.lead = line;
  }
  return out;
}

/* The short in-view card: lead + at most 2 evidence bullets + the first "check first" line, cited ids, provenance.
   final = the server's 'final' event (citations verified server-side; only verified ids are highlighted). */
function cardModel({question = '', answer = '', final = null, level = null, toolCount = null} = {}) {
  const S = sections(answer), cites = (final && final.citations) || [], byId = new Map(cites.map(c => [c.id, c]));
  const label = id => { const c = byId.get(id); return c && c.type ? c.type : null; };
  const primary = leadId(answer);
  const conf = (/confidence:\s*(low|medium|high)/i.exec(S.lead) || [])[1] || null;
  const lead = plainLine(S.lead.replace(/\s*·\s*confidence:\s*(low|medium|high)/i, ''));
  const evidence = S.sections.Why || S.sections.Closest || S.sections.Where || S.sections['Nearby (1 m)'] || [];
  const check = (S.sections['Check first'] || [])[0];
  const bullets = [...evidence.slice(0, 2).map(t => ({kind: 'why', text: plainLine(t)})), ...(check ? [{kind: 'check', text: plainLine(check)}] : [])];
  const chips = cites.filter(c => c.known !== false).map(c => ({id: c.id, label: c.type || c.layer || 'element', verified: !!c.verified, primary: c.id === primary}))
    .sort((a, b) => (b.primary - a.primary) || (b.verified - a.verified)).slice(0, 4);
  const nv = cites.filter(c => c.verified).length, mode = final ? final.mode : null;
  return {question: plainLine(question), level, lead, leadKind: S.leadKind, confidence: conf, bullets, chips, primary: primary && byId.get(primary)?.verified ? primary : null,
    limits: plainLine(S.limits), mode, model: final ? final.model : null, label,
    footer: [
      (mode === 'live' ? 'LIVE · ' + (final.model || 'Claude') : mode === 'mock' ? 'MOCK · scripted from real tool results' : '') +
        (final ? ` · ${toolCount != null ? toolCount : (final.tools_used || []).length} lookups · ${nv}/${cites.length} cited IDs verified` : ''),
      'Design BIM · inferred geometry and rooms · demo sensors SIMULATED · not headset-verified'],
  };
}

/* Spoken reply (fallback when the server sends no 'speak' events): lead + the first check only; ids read as their
   element type; evidence, other candidates and Limits stay on the card. The server's version (speech.py) is preferred. */
function speakable(answer, citations = []) {
  const byId = new Map((citations || []).map(c => [c.id, c]));
  const S = sections(answer);
  const say = s => plainLine(s, id => byId.get(id)?.type || 'element')   // ids stay on the card; read aloud they would be noise
    .replace(/\s*·\s*confidence:\s*(low|medium|high)/i, '. Confidence $1')
    .replace(/~/g, 'about ').replace(/·/g, ',').replace(/(\d)\s?m\b/g, '$1 metres').replace(/\bdegC\b|°C/g, ' degrees').replace(/\s+/g, ' ').trim();
  const lead = String(S.lead || '').replace(/\s*·\s*confidence:\s*(low|medium|high)/i, '').replace(/\s*\([^()]*\)/g, '');
  const parts = [lead, ...(S.sections['Check first'] || []).slice(0, 1).map(t => 'First, ' + t.replace(/^\w/, c => c.toLowerCase()))];
  return parts.filter(Boolean).map(say).map(t => /[.!?]$/.test(t) ? t : t + '.').join(' ');
}

/* Waiting feedback: a friendly progress line from each server event ("Checking the ducts…"). */
const LAYER_WORDS = {duct: 'ducts', fire: 'sprinkler pipes', plumbing: 'plumbing pipes', hydronic: 'heating and cooling pipes', lighting: 'lights', equipment: 'equipment'};
function progressText(ev, el = null) {
  if (!ev) return 'Thinking…';
  if (ev.type === 'status') return ev.phase === 'thinking' ? ev.text || 'Thinking…' : null;
  if (ev.type === 'text') return 'Writing the answer…';
  if (ev.type !== 'tool') return null;
  const layers = (ev.input && ev.input.layers) || [], lw = LAYER_WORDS[(el && el.layer) || ''] || 'services';
  switch (ev.name) {
    case 'elements_near': return ev.input && ev.input.above_only ? 'Checking what is above it…' : layers.length === 1 && LAYER_WORDS[layers[0]] ? 'Checking the ' + LAYER_WORDS[layers[0]] + ' nearby…' : 'Checking what is around it…';
    case 'connected_run': return 'Following the ' + lw + '…';
    case 'room_of': return 'Finding the room…';
    case 'get_element': return 'Looking it up…';
    case 'find_elements': return 'Searching the model…';
    case 'list_sensors': return 'Finding the demo sensors…';
    case 'sensor_readings': return 'Reading the demo sensors (simulated)…';
    default: return 'Checking the twin…';
  }
}
/* Earcons (Web Audio tones): [frequency Hz, start s, duration s, gain]. listen = recording started, send = question sent,
   done = answer ready, miss = nothing heard / error. Short and quiet so they do not cover speech. */
const EARCONS = {
  listen: [[660, 0, .07, .16], [990, .08, .09, .16]],
  send: [[880, 0, .06, .12]],
  done: [[784, 0, .07, .12], [1175, .08, .11, .12]],
  miss: [[330, 0, .12, .14], [262, .13, .14, .12]],
};
/* Point-and-ask: hold the trigger on an element for HOLD_MS (not on a panel, not while placing/aligning) -> pick + record;
   release -> ask about that element. A shorter press is the usual trigger click (info card). */
const HOLD_MS = 400;
function holdAskAllowed({on = false, hoverPanel = null, aiming = false, grip = false, placing = false, placed = true, busy = false} = {}) {
  return !!on && !hoverPanel && !aiming && !grip && !placing && !!placed && !busy;
}
/* Spoken filler while waiting: only if nothing has been said FILLER_MS after the question was sent. */
const FILLER_MS = 1500;

/* connected_run paths from the tool events -> the element ids to light up, from the cited source to the picked element.
   The model has no flow direction: the order only follows the answer ("source" = the cited terminal unit / AHU). */
function runPath(paths, primary, citations = []) {
  const ok = new Set((citations || []).filter(c => c.verified).map(c => c.id));
  const list = (paths || []).filter(p => p && Array.isArray(p.ids) && p.ids.length > 1);
  const hit = list.find(p => p.to === primary && ok.has(p.to)) || list.find(p => ok.has(p.to));
  return hit ? hit.ids.slice(0, 80).reverse() : null;
}
/* Opacity of element i of n on the lit run at time t (ms since the answer): pieces light one after another, then a soft
   pulse travels along the run. reduced = prefers-reduced-motion: everything lit, no motion. */
function runGlow(i, n, t, {stepMs = 90, fadeMs = 220, pulseMs = 1600, base = .3, reduced = false} = {}) {
  if (reduced) return .5;
  const on = t - i * stepMs;
  if (on <= 0) return 0;
  let a = base * Math.min(1, on / fadeMs);
  const after = t - n * stepMs;
  if (after > 0 && n > 1) { const p = ((after % pulseMs) / pulseMs) * (n + 4) - 2, d = i - p; a += .45 * Math.exp(-(d * d) / 3); }
  return Math.min(.8, a);
}

/* Ask bar under the card: 2 rows x 3 buttons. (u, v) are plane UVs, v up (three.js PlaneGeometry). */
const BAR = {cols: 3, rows: 2, left: .02, right: .98, top: .05, bottom: .95, gap: .03};
function barRects(area = BAR) {
  const out = [], w = (area.right - area.left - area.gap * (area.cols - 1)) / area.cols, h = (area.bottom - area.top - area.gap * (area.rows - 1)) / area.rows;
  for (let r = 0; r < area.rows; r++) for (let c = 0; c < area.cols; c++) out.push({x: area.left + c * (w + area.gap), y: area.top + r * (h + area.gap), w, h});
  return out;
}
function barHit(u, v, area = BAR) {
  const x = u, y = 1 - v, rects = barRects(area);
  for (let i = 0; i < rects.length; i++) { const r = rects[i]; if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) return i; }
  return -1;
}
/* Buttons: the four levels, voice, close. state: {busy, voice: 'ready'|'recording'|'transcribing'|'off', voiceNote} */
function barButtons(state = {}) {
  const v = state.voice || 'off';
  return [...LEVELS.map(l => ({id: l.id, label: l.level + ' · ' + l.label, sub: l.hint, disabled: !!state.busy})),
    {id: 'mic', label: v === 'recording' ? 'Listening… release' : v === 'transcribing' ? 'Transcribing…' : 'Hold to speak', sub: v === 'off' ? (state.voiceNote || 'voice off: use 1-4') : 'trigger held on this button',
      tone: v === 'recording' ? 'rec' : v === 'off' ? 'off' : '', disabled: v === 'off' || v === 'transcribing' || (!!state.busy && v !== 'recording')},
    {id: 'close', label: 'Close', sub: 'clear the answer', tone: 'exit'}];
}

/* Voice in: the permission prompt is a 2D dialog that cannot show inside an immersive session, so the microphone is
   opened on the 2D page (a button press) BEFORE Enter MR/VR and kept open. In-session getUserMedia is tried as a last resort. */
function micPlan({secure = false, getUserMedia = false, mediaRecorder = false, stt = false, haveStream = false, presenting = false} = {}) {
  if (!stt) return {mode: 'off', note: 'voice off: no speech-to-text on the laptop'};
  if (!secure) return {mode: 'off', note: 'voice off: needs HTTPS (--lan)'};
  if (!getUserMedia || !mediaRecorder) return {mode: 'off', note: 'voice off: no microphone API'};
  if (haveStream) return {mode: 'ready', note: ''};
  return presenting ? {mode: 'try', note: 'mic not opened before entering: trying'} : {mode: 'ask', note: 'press "Allow mic" before entering'};
}
/* Voice out: the laptop voice (macOS say, best installed English voice -> WAV over the LAN) when available, because the
   headset browser's voice is robotic; prefer = 'browser' (&voice=headset or the 2D toggle) uses the headset voice first.
   Otherwise a browser voice if one exists, else text only. */
function ttsPlan({synth = false, voices = 0, server = false, prefer = 'laptop'} = {}) {
  if (server && prefer !== 'browser') return 'server';
  if (synth && voices > 0) return 'browser';
  if (server) return 'server';
  return synth ? 'browser-unknown' : 'none';
}

// ---------------------------------------------------------------- canvas drawing (any CanvasRenderingContext2D)
function wrap(ctx, text, width, max = 2) {
  const words = String(text || '').split(/\s+/).filter(Boolean), lines = [];
  let line = '';
  for (const w of words) {
    const t = line ? line + ' ' + w : w;
    if (ctx.measureText(t).width > width && line) { lines.push(line); line = w; if (lines.length === max) break; } else line = t;
  }
  if (lines.length < max && line) lines.push(line);
  else if (lines.length === max && words.length) {   // ellipsis when cut
    const used = lines.join(' ').split(/\s+/).length;
    if (used < words.length) { let l = lines[max - 1]; while (l && ctx.measureText(l + '…').width > width) l = l.slice(0, -1); lines[max - 1] = l + '…'; }
  }
  return lines;
}
function fit(ctx, text, x, y, width, size, weight = '', family = 'Arial') {
  let s = size; do { ctx.font = `${weight} ${s}px ${family}`.trim(); } while (ctx.measureText(text).width > width && --s > 12);
  ctx.fillText(text, x, y);
}
function rr(ctx, x, y, w, h, r) { ctx.beginPath(); if (ctx.roundRect) ctx.roundRect(x, y, w, h, r); else ctx.rect(x, y, w, h); }
/* Claude badge: orange disc with a cream sparkle (tapered rays), drawn so no image asset is needed in the headset. */
function drawBadge(ctx, cx, cy, r) {
  ctx.save();
  ctx.fillStyle = CLAUDE.orange; ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
  ctx.translate(cx, cy); ctx.fillStyle = CLAUDE.cream;
  const n = 12;
  for (let k = 0; k < n; k++) {
    ctx.save(); ctx.rotate(k * Math.PI * 2 / n + (k % 3) * .05);
    const L = r * (k % 2 ? .52 : .7), w = r * (k % 2 ? .1 : .13);
    ctx.beginPath(); ctx.moveTo(-w / 2, 0); ctx.quadraticCurveTo(-w * .35, -L * .6, 0, -L); ctx.quadraticCurveTo(w * .35, -L * .6, w / 2, 0); ctx.closePath(); ctx.fill();
    ctx.restore();
  }
  ctx.beginPath(); ctx.arc(0, 0, r * .17, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}
function drawSpeaker(ctx, x, y, s, color) {
  ctx.save(); ctx.fillStyle = color; ctx.strokeStyle = color; ctx.lineWidth = s * .12; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(x, y - s * .2); ctx.lineTo(x + s * .22, y - s * .2); ctx.lineTo(x + s * .5, y - s * .45); ctx.lineTo(x + s * .5, y + s * .45); ctx.lineTo(x + s * .22, y + s * .2); ctx.lineTo(x, y + s * .2); ctx.closePath(); ctx.fill();
  ctx.beginPath(); ctx.arc(x + s * .55, y, s * .3, -.8, .8); ctx.stroke(); ctx.beginPath(); ctx.arc(x + s * .55, y, s * .55, -.8, .8); ctx.stroke();
  ctx.restore();
}
const hex = c => '#' + c.toString(16).padStart(6, '0');
/* The answer card. view: {phase: 'thinking'|'answer'|'error', model (cardModel), steps: [text], error, speech: 'speaking'|'done'|'text only'|...} */
function drawAnswer(ctx, W, H, view) {
  const m = view.model || {}, pad = 40;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgb(8,16,28)'; rr(ctx, 4, 4, W - 8, H - 8, 30); ctx.fill();
  ctx.strokeStyle = view.phase === 'error' ? '#e2725b' : CLAUDE.orange; ctx.lineWidth = 4; ctx.stroke();
  // header: badge, name, mode pill, read-aloud state
  drawBadge(ctx, pad + 30, 62, 30);
  ctx.fillStyle = '#fff'; ctx.font = '700 44px Arial'; ctx.fillText('Claude', pad + 74, 78);
  const mode = view.modeLabel || (m.mode === 'live' ? 'LIVE' : m.mode === 'mock' ? 'MOCK' : '');
  let hx = pad + 74 + ctx.measureText('Claude').width + 18;
  if (mode) { ctx.font = '700 26px Arial'; const w = ctx.measureText(mode).width + 28; ctx.fillStyle = mode === 'LIVE' ? '#14532d' : '#6a4a10'; rr(ctx, hx, 42, w, 42, 21); ctx.fill(); ctx.fillStyle = mode === 'LIVE' ? '#86efac' : '#fcd34d'; ctx.fillText(mode, hx + 14, 72); hx += w + 12; }
  if (m.level) { ctx.font = '600 26px Arial'; ctx.fillStyle = '#9fb6cb'; ctx.fillText('Level ' + m.level, hx + 4, 72); }
  if (view.speech) { const sp = view.speech, col = sp === 'speaking' ? '#ffd9a0' : '#8aa2b8'; ctx.textAlign = 'right'; ctx.font = '700 24px Arial'; ctx.fillStyle = col; ctx.fillText(sp === 'speaking' ? 'READ ALOUD' : sp.toUpperCase(), W - pad, 72); const tw = ctx.measureText(sp === 'speaking' ? 'READ ALOUD' : sp.toUpperCase()).width; ctx.textAlign = 'left'; drawSpeaker(ctx, W - pad - tw - 46, 63, 36, col); }
  let y = 128;
  if (m.question) { ctx.font = 'italic 28px Arial'; ctx.fillStyle = '#a9c1d6'; for (const t of wrap(ctx, '“' + m.question + '”', W - 2 * pad, 2)) { ctx.fillText(t, pad, y); y += 36; } y += 8; }
  if (view.phase === 'thinking') {
    ctx.font = '600 34px Arial'; ctx.fillStyle = '#e8f1f8'; fit(ctx, view.progress || 'Thinking…', pad, y + 12, W - 2 * pad, 34, '600'); y += 60;
    ctx.font = '28px Arial';
    for (const s of (view.steps || []).slice(-6)) { ctx.fillStyle = '#34d399'; ctx.fillText('✓', pad, y); ctx.fillStyle = '#cfe3f5'; fit(ctx, s, pad + 34, y, W - 2 * pad - 34, 28); y += 40; }
  } else if (view.phase === 'error') {
    ctx.font = '700 36px Arial'; ctx.fillStyle = '#ffb4a8'; ctx.fillText('Could not answer', pad, y + 12); y += 58;
    ctx.font = '30px Arial'; ctx.fillStyle = '#e8f1f8'; for (const t of wrap(ctx, view.error || '', W - 2 * pad, 4)) { ctx.fillText(t, pad, y); y += 40; }
  } else {
    ctx.font = '700 36px Arial'; ctx.fillStyle = '#ffffff';
    for (const t of wrap(ctx, m.lead || '', W - 2 * pad, 3)) { ctx.fillText(t, pad, y + 10); y += 46; }
    if (m.confidence) { ctx.font = '700 24px Arial'; const t = 'confidence: ' + m.confidence, w = ctx.measureText(t).width + 26; ctx.fillStyle = m.confidence === 'high' ? '#14532d' : m.confidence === 'medium' ? '#6a4a10' : '#3b2a4a'; rr(ctx, pad, y - 10, w, 36, 18); ctx.fill(); ctx.fillStyle = '#f1f5f9'; ctx.fillText(t, pad + 13, y + 16); y += 40; }
    y += 10;
    for (const b of m.bullets || []) {
      ctx.font = b.kind === 'check' ? '600 28px Arial' : '28px Arial'; ctx.fillStyle = b.kind === 'check' ? '#ffd479' : '#cfe3f5';
      const lines = wrap(ctx, (b.kind === 'check' ? 'Check first: ' : '') + b.text, W - 2 * pad - 30, 2);
      ctx.fillText(b.kind === 'check' ? '▸' : '•', pad, y + 6);
      for (const t of lines) { ctx.fillText(t, pad + 30, y + 6); y += 36; }
      y += 6;
      if (y > H - 190) break;
    }
    // cited ids (verified ones are highlighted in the model)
    let cx = pad; const cy = H - 150;
    ctx.font = '600 24px Arial';
    for (const c of m.chips || []) {
      const t = '#' + c.id + ' ' + c.label, w = Math.min(ctx.measureText(t).width + 30, W - pad - cx);
      if (w < 120) break;
      const col = !c.verified ? '#ef4444' : c.primary ? hex(COLORS.primary) : hex(COLORS.other);
      ctx.fillStyle = 'rgba(255,255,255,.06)'; rr(ctx, cx, cy - 30, w, 42, 12); ctx.fill(); ctx.strokeStyle = col; ctx.lineWidth = c.primary ? 4 : 2.5; ctx.stroke();
      ctx.fillStyle = c.verified ? '#f1f5f9' : '#fca5a5'; ctx.save(); ctx.beginPath(); ctx.rect(cx, cy - 34, w - 12, 50); ctx.clip(); ctx.fillText(t, cx + 15, cy); ctx.restore();
      if (!c.verified) { ctx.strokeStyle = '#fca5a5'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(cx + 12, cy - 9); ctx.lineTo(cx + w - 12, cy - 9); ctx.stroke(); }
      cx += w + 12;
    }
  }
  ctx.fillStyle = '#8aa2b8';
  const f = (m.footer && m.footer.length ? m.footer : view.footer) || [];
  if (view.runNote) { ctx.fillStyle = '#9fe7f5'; fit(ctx, view.runNote, pad, H - 92, W - 2 * pad, 24); }
  ctx.fillStyle = '#8aa2b8';
  if (f[0]) fit(ctx, f[0], pad, H - 58, W - 2 * pad, 24);
  if (f[1]) fit(ctx, f[1], pad, H - 26, W - 2 * pad, 22);
}
/* The ask bar (buttons). hover: Set of button indices under a ray. */
function drawBar(ctx, W, H, buttons, hover = new Set()) {
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(8,16,28,.92)'; rr(ctx, 2, 2, W - 4, H - 4, 24); ctx.fill();
  const rects = barRects();
  buttons.forEach((b, i) => {
    const r = rects[i]; if (!r) return;
    const hov = hover.has(i) && !b.disabled, x = r.x * W, y = r.y * H, w = r.w * W, h = r.h * H;
    ctx.fillStyle = hov ? '#FDB515' : b.tone === 'rec' ? '#7a2633' : b.tone === 'exit' ? '#3a2633' : b.disabled ? '#1b2a3a' : '#123a5c';
    rr(ctx, x, y, w, h, 16); ctx.fill(); ctx.strokeStyle = hov ? '#fff' : b.id === 'mic' && b.tone !== 'off' ? CLAUDE.orange : '#5d82a3'; ctx.lineWidth = hov ? 6 : 3; ctx.stroke();
    ctx.textAlign = 'center'; ctx.fillStyle = hov ? '#0b1020' : b.disabled ? '#7b8da0' : '#fff';
    fit(ctx, b.label, x + w / 2, y + h * .48, w - 20, 34, '700');
    ctx.fillStyle = hov ? '#0b1020' : '#9fb6cb'; fit(ctx, b.sub || '', x + w / 2, y + h * .8, w - 20, 22, '500');
    ctx.textAlign = 'left';
  });
}

return {API, LEVELS, COLORS, CLAUDE, BAR, parseParams, createStream, sections, leadId, plainLine, cardModel, speakable, runPath, runGlow,
  barRects, barHit, barButtons, micPlan, ttsPlan, wrap, drawBadge, drawAnswer, drawBar,
  serverOrigin, privateIPv4, apiUrl, healthProblem, progressText, EARCONS, HOLD_MS, holdAskAllowed, FILLER_MS};
});
