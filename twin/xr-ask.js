/* Ask the twin inside the headset page (scan-xr.html?ask=1, served by scripts/ask_twin_server.py on the laptop).
   DOM overlays are invisible in an immersive session, so everything the user sees is drawn on 2D canvases that the page
   puts on planes in the scene. This file holds the logic and the drawing only (no three.js, no DOM queries):
     - the preset questions of the four levels (look up · nearby in 3D · trace a system · reason across sources),
     - the answer stream parser (Server-Sent Events from /api/ask),
     - the in-view answer card (headline + a picture built from the tool results + caption, check chip, cited ids, provenance),
     - the spoken text, the run lighting timing for connected_run, the ask-bar layout and hit test, and the voice/TTS plans.
   Unit-tested in tests/xr-ask.test.cjs. The page is unchanged unless it is opened with ?ask=1. NOT verified on a headset. */
(function (root, factory) {
  const api = factory();
  if (root) root.XRAsk = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';

const API = 3;   // 3: access code (code=, X-Ask-Code, refusalText)
const CITE_RX = /\[\[([A-Za-z0-9_.:-]{1,40})\]\]/g;
const LEVELS = [
  {level: 1, id: 'q1', label: 'What is this?', hint: 'look up', question: 'What is this, and what room am I in?'},
  {level: 2, id: 'q2', label: "What's above?", hint: 'nearby in 3D', question: 'What is above this ceiling tile within 2 m?'},
  {level: 3, id: 'q3', label: 'What feeds it?', hint: 'trace a system', question: 'Which VAV box feeds this?'},
  {level: 4, id: 'q4', label: 'Why is it warm?', hint: 'reason across sources', question: 'This room is warm from 9 to 5 every weekday. What is the likely cause, and where do I check first?'},
];
const COLORS = {primary: 0xff3df0, other: 0x22d3ee, run: 0x22d3ee};   // same magenta / cyan as the laptop panel (twin/ask-twin.js)

/* ?ask=1 turns the feature on. Anything else (absent, 0, off) leaves the page exactly as it was.
   &server=https://<laptop LAN IP>:<port> ("Method A"): the page itself comes from anywhere (e.g. GitHub Pages) and only the
   AI calls (health, ask, transcribe, speak) go to the laptop. Validated by serverOrigin; an invalid value is ignored.
   &voice=headset prefers the headset browser's own voice over the laptop voice. */
function parseParams(search) {
  const q = new URLSearchParams(search || ''), raw = q.get('server');
  const server = raw == null ? null : serverOrigin(raw);
  return {enabled: q.get('ask') === '1', server, serverIgnored: raw != null && !server, preferVoice: q.get('voice') === 'headset' ? 'browser' : 'laptop',
    code: accessCode(search)};
}
/* &code=… : the access code the laptop server prints at start (letters/digits, case-insensitive). Sent only to the ask server,
   as the X-Ask-Code header on ask / transcribe / speak. */
function accessCode(search) { return String(new URLSearchParams(search || '').get('code') || '').replace(/[\s-]+/g, '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 32); }
function askHeaders(code, extra = {}) { return code ? Object.assign({}, extra, {'X-Ask-Code': code}) : Object.assign({}, extra); }
/* 401 / 429 from the ask server -> the sentence the card shows (null for any other status). */
function refusalText(status, body = {}) {
  const b = body || {};
  if (status === 401) return b.reason === 'code_wrong' ? 'Wrong access code: reopen this page with the link printed in the laptop terminal.'
    : 'Access code needed: open the link printed in the laptop terminal (it ends with &code=…).';
  if (status === 429) return b.error || ('Too many requests right now.' + (b.retry_after_s ? ' Try again in ' + b.retry_after_s + ' s.' : ''));
  return null;
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
  if (m) return m[1];
  // plain format (live answers since Nov 2026): one paragraph, then "Evidence: [[id]] ..." with the main element first
  const ev = /^\s*(?:\*\*)?Evidence:(?:\*\*)?\s*\[\[([A-Za-z0-9_.:-]{1,40})\]\]/im.exec(answer || '');
  return ev && !/^\s*\*\*(?:Most likely source|Answer):\*\*/m.test(answer || '') ? ev[1] : null;
}
/* Markdown-lite answer -> {lead, sections: {name: [lines]}, limits}. Sections are the bold "**Name:**" lines of the card format. */
function sections(answer) {
  const out = {lead: '', leadKind: null, sections: {}, order: [], limits: ''};
  let cur = null;
  for (const raw of String(answer || '').replace(MOCK_TAG, '').split('\n')) {
    const line = raw.trim(); if (!line) continue;
    if (/^(?:\*\*)?Evidence:/i.test(line)) continue;   // plain format: ids for the chips, not text
    const h = /^\*\*([A-Za-z ]{2,30}):\*\*\s*(.*)$/.exec(line);
    if (h) {
      const name = h[1].trim();
      if (!out.leadKind && /^(Most likely source|Answer)$/.test(name)) { out.lead = h[2]; out.leadKind = name; cur = null; continue; }
      if (name === 'Limits') { out.limits = h[2]; cur = null; continue; }
      cur = name; out.sections[cur] = out.sections[cur] || []; out.order.push(cur);
      if (h[2]) out.sections[cur].push(h[2]);
      continue;
    }
    const li = /^[-•]\s+(.*)$/.exec(line);
    if (cur) out.sections[cur].push(li ? li[1] : line);
    else if (!out.leadKind && !out.order.length) out.lead = out.lead ? out.lead + ' ' + line : line;   // plain paragraph (or preamble)
  }
  return out;
}

/* The short in-view card: lead + at most 2 evidence bullets + the first "check first" line, cited ids, provenance.
   final = the server's 'final' event (citations verified server-side; only verified ids are highlighted). */
function cardModel({question = '', answer = '', final = null, level = null, toolCount = null, visuals = null, selected = null} = {}) {
  const S = sections(answer), cites = (final && final.citations) || [], byId = new Map(cites.map(c => [c.id, c]));
  const label = id => { const c = byId.get(id); return c && c.type ? c.type : null; };
  const primary = leadId(answer);
  const conf = (/confidence:\s*(low|medium|high)/i.exec(S.lead) || [])[1] || null;
  const lead = plainLine(S.lead.replace(/\s*·\s*confidence:\s*(low|medium|high)/i, ''));
  const evidence = S.sections.Why || S.sections.Closest || S.sections.Where || S.sections['Nearby (1 m)'] || [];
  const check = (S.sections['Check first'] || [])[0];
  const bullets = [...evidence.slice(0, 2).map(t => ({kind: 'why', text: plainLine(t)})), ...(check ? [{kind: 'check', text: plainLine(check)}] : [])];
  const chips = cites.filter(c => c.known !== false).map(c => ({id: c.id, label: c.label || c.type || c.layer || 'element', verified: !!c.verified, primary: c.id === primary}))
    .sort((a, b) => (b.primary - a.primary) || (b.verified - a.verified)).slice(0, 5);
  const nv = cites.filter(c => c.verified).length, mode = final ? final.mode : null;
  const prim = primary && byId.get(primary)?.verified ? primary : null;
  const visual = visuals ? answerVisual({visuals, citations: cites, primary: prim, selected, answer}) : null;
  if (visual && S.leadKind && visual.kind !== 'text') visual.caption = plainLine(S.lead.replace(/\s*·\s*confidence:\s*(low|medium|high)/i, ''), id => 'the ' + (byId.get(id)?.label || 'element'));   // older card format: the lead line
  return {question: plainLine(question), level, lead, leadKind: S.leadKind, confidence: conf, bullets, chips, primary: prim, visual,
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
function drawSpeaker(ctx, x, y, s, color) {
  ctx.save(); ctx.fillStyle = color; ctx.strokeStyle = color; ctx.lineWidth = s * .12; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(x, y - s * .2); ctx.lineTo(x + s * .22, y - s * .2); ctx.lineTo(x + s * .5, y - s * .45); ctx.lineTo(x + s * .5, y + s * .45); ctx.lineTo(x + s * .22, y + s * .2); ctx.lineTo(x, y + s * .2); ctx.closePath(); ctx.fill();
  ctx.beginPath(); ctx.arc(x + s * .55, y, s * .3, -.8, .8); ctx.stroke(); ctx.beginPath(); ctx.arc(x + s * .55, y, s * .55, -.8, .8); ctx.stroke();
  ctx.restore();
}
const hex = c => '#' + c.toString(16).padStart(6, '0');
/* ---------------------------------------------------------------- visual answer card (Nov 9 redesign)
   Feedback after the first recordings: a text-only card is hard to read in a headset. The card now leads with one short
   headline and a picture chosen by the tool that answered, built from the structured tool results the server sends with
   each 'tool' event (ev.visual, scripts/ask_twin/agent.py tool_visual) and the verified citations, never by parsing prose:
     look up  (room_of / get_element) -> element pictogram, size, level, room chip with how sure the room is
     nearby   (elements_near)          -> "what's above" height graph with pictogram markers + counts by system
     trace    (connected_run)          -> mini path diagram: this element -> n pieces along the run -> source
   The full sentence answer stays as a 1-2 line caption; a "check on site" chip and the evidence ids sit at the bottom.
   A small neutral spark mark + "AI answer" replaces the chat-style header (no logo, no bubble). */
const SYS = {duct: '#7dd3fc', fire: '#f87171', hydronic: '#fb923c', plumbing: '#60a5fa', structural: '#cbd5e1', lighting: '#fde68a',
  equipment: '#86efac', conduit: '#c4b5fd', lifesafety: '#fca5a5', fixtures: '#e2e8f0', ceiling: '#94a3b8'};
const SYS_WORD = {duct: 'ducts', fire: 'sprinkler pipes', hydronic: 'heating/cooling pipes', plumbing: 'plumbing', structural: 'structure',
  lighting: 'lights', equipment: 'equipment', conduit: 'conduit', lifesafety: 'life safety', fixtures: 'fixtures'};
const PICTO_FOR_LAYER = {duct: 'duct', fire: 'sprinkler', hydronic: 'pipe', plumbing: 'pipe', structural: 'beam', lighting: 'light',
  equipment: 'equipment', conduit: 'conduit', lifesafety: 'sensor', fixtures: 'equipment'};
/* element -> pictogram key: vent, vav, duct, damper, sprinkler, pipe, valve, light, beam, ceiling, conduit, sensor, equipment, box */
function pictogram(el) {
  if (!el) return 'box';
  const label = String(el.label || '').toLowerCase(), t = `${el.type || ''} ${el.name || ''}`.toLowerCase(), layer = String(el.layer || '');
  if (el.sensor || /sensor/.test(label)) return 'sensor';
  if (label === 'vav box' || /terminal unit|\bvav\b|\bsdv\b/.test(t)) return 'vav';
  if (label === 'diffuser' || /cdff|diffuser|grille|register|air outlet/.test(t)) return 'vent';
  if (label === 'damper' || /damper/.test(t)) return 'damper';
  if (label === 'valve' || /valve/.test(t)) return 'valve';
  if (/sprinkler/.test(label) || layer === 'fire') return 'sprinkler';
  if (label === 'light' || layer === 'lighting') return 'light';
  if (label === 'ceiling' || layer.startsWith('ceilings')) return 'ceiling';
  if (layer === 'structural' || /beam|framing|joist|girder|column|slab/.test(t)) return 'beam';
  return PICTO_FOR_LAYER[layer] || (/pipe/.test(label) ? 'pipe' : /duct/.test(label) ? 'duct' : 'box');
}
const NICE = {diffuser: 'Air vent (diffuser)', 'VAV box': 'VAV box', light: 'Ceiling light', duct: 'Duct', 'sprinkler pipe': 'Sprinkler pipe',
  'sprinkler drop': 'Sprinkler drop', 'sprinkler head': 'Sprinkler head', 'sprinkler fitting': 'Sprinkler fitting', pipe: 'Pipe', 'pipe fitting': 'Pipe fitting',
  valve: 'Valve', damper: 'Damper', ceiling: 'Ceiling', 'coil connection kit': 'Coil connection kit'};
/* plain display name: the server's spoken label, else the BIM type unless it is a CAD code */
function niceName(el) {
  if (!el) return 'Element';
  const l = el.label && el.label !== 'element' ? el.label : (el.type && !/[A-Z]-[A-Z]{2,}/.test(el.type) ? el.type : '');
  if (!l) return pictogram(el) === 'beam' ? 'Beam' : 'Element';
  if (NICE[l]) return NICE[l];
  if (/structural framing|beam/i.test(l)) return 'Beam';
  return l.charAt(0).toUpperCase() + l.slice(1);
}
const shortName = el => niceName(el).replace(/\s*\(.*\)$/, '');
const mFmt = v => (Math.round(v * 100) / 100).toFixed(v < 1 ? 2 : 1).replace(/\.?0+$/, '') + ' m';
/* recorded size string, else the plan size of the model box ("0.6 × 0.6 m"), else null */
function sizeText(el) {
  if (!el) return null;
  if (el.size) return String(el.size).replace(/\s+/g, ' ').trim().slice(0, 20);
  const s = Array.isArray(el.size_m) && el.size_m.length === 3 ? el.size_m.map(Number) : null;
  if (!s || !s.every(Number.isFinite)) return null;
  const plan = [s[0], s[2]].sort((a, b) => b - a), r = v => (Math.round(v * 10) / 10).toFixed(1).replace(/\.0$/, '');
  if (plan[1] < .05) return null;
  return plan[0] > 3 ? r(plan[0]) + ' m long' : r(plan[0]) + ' × ' + r(plan[1]) + ' m';
}
const LEVEL_WORD = l => { const m = /^L?(\d+)$/i.exec(String(l || '')); return m ? 'Level ' + m[1] : (l ? String(l) : ''); };
/* room_of confidence -> chip: dots (1-3), word, basis */
function roomChip(room) {
  if (!room || !room.room) return null;
  const c = room.confidence, recorded = c === 'recorded';
  const name = String(room.room).replace(/\s*\/\s*/g, ' / ').replace(/\s+/g, ' ').trim().toLowerCase().replace(/(^|[\s/(-])([a-z])/g, (_, a, b) => a + b.toUpperCase()).slice(0, 40);
  return {name, dots: recorded ? 3 : c === 'medium' ? 2 : 1, word: recorded ? 'Recorded' : c === 'medium' ? 'Probably' : 'Best guess',
    basis: recorded ? 'on the element record' : 'guessed from nearby labels'};
}
/* answer prose -> caption (first sentences) and the "check …" phrase for the on-site chip. Display only; the graphics never
   depend on these. */
function answerBody(answer) {
  return String(answer || '').replace(MOCK_TAG, '').split('\n').filter(l => !/^\s*(?:\*\*)?Evidence:/i.test(l)).join(' ')
    .replace(CITE_RX, 'it').replace(/\*\*(.+?)\*\*:?/g, '$1').replace(/\*(.+?)\*/g, '$1').replace(/^\s*(?:Answer|Most likely source):\s*/i, '').replace(/\s+/g, ' ').trim();
}
function captionText(answer, n = 2) {
  const body = answerBody(answer), parts = body ? body.split(/(?<=[.!?])\s+(?=[A-Z"“(])/) : [];
  return parts.slice(0, n).map(t => t.trim()).join(' ').trim();
}
const CHECK_DEFAULT = {lookup: 'Check the room sign on site', near: 'Look above the ceiling tile on site', trace: 'Check the duct drawings or BAS points',
  text: 'Check on site'};
function checkText(answer, kind = 'text') {
  const body = answerBody(answer).replace(/\s*\([^()]*\)/g, '');
  const m = /\bcheck(?:ing)?\s+((?:the|a|an|on|with|its|for)\b[^.;:!?]{0,60})/i.exec(body);
  let t = m ? 'Check ' + m[1].trim().replace(/[,\s]+$/, '') : '';
  if (t.length > 52) t = t.slice(0, 52).replace(/\s+\S*$/, '') + '…';
  return t || CHECK_DEFAULT[kind] || CHECK_DEFAULT.text;
}
/* visuals (ev.visual of every tool event) + verified citations + primary/selected -> what the card draws */
function answerVisual({visuals = [], citations = [], primary = null, selected = null, answer = ''} = {}) {
  const vis = (visuals || []).filter(v => v && typeof v === 'object'), of = k => vis.filter(v => v.kind === k);
  const cites = (citations || []).filter(c => c && c.known !== false), ok = new Set(cites.filter(c => c.verified).map(c => c.id));
  const byId = new Map(cites.map(c => [c.id, c])), citedOrder = cites.map(c => c.id);
  const selId = selected && selected.id != null ? String(selected.id) : null;
  const selEl = Object.assign({}, selected || {}, byId.get(selId) || {});
  const run = of('run').find(v => (v.notable || []).some(n => ok.has(n.id))), near   /* a trace card only for a run the answer verifiably cites */ = of('near').find(v => v.above_only && (v.items || []).length) || of('near').find(v => (v.items || []).length);
  const room = of('room').filter(v => v.room).pop() || null, elv = of('element').map(v => v.element).find(e => e && String(e.id) === selId) || of('element')[0]?.element || null;
  const out = {kind: 'text', headline: '', check: '', caption: captionText(answer)};
  if (run) {
    const src = run.notable.find(n => n.id === primary && ok.has(n.id)) || run.notable.find(n => ok.has(n.id));
    const from = selId && run.start && String(run.start.id) !== selId ? selEl : (run.start && run.start.id ? Object.assign({}, run.start, byId.get(run.start.id) || {}) : selEl);
    Object.assign(out, {kind: 'trace', from: {label: shortName(from), picto: pictogram(from)}, to: {id: src.id, label: shortName(src), picto: pictogram(src)},
      hops: Number.isFinite(src.hops) ? src.hops : null, away: Number.isFinite(src.horizontal_gap_m) ? src.horizontal_gap_m : null,
      where: src.vertical === 'above' ? 'above the ceiling' : src.vertical === 'below' ? 'below' : '', pieceWord: run.layer === 'duct' ? 'duct pieces' : 'pieces',
      runPicto: PICTO_FOR_LAYER[run.layer] || 'duct', reached: run.reached || null, verified: ok.has(src.id)});
    out.headline = (run.layer === 'duct' ? 'Probably fed by ' : 'Connected to ') + (/^[aeiou]/i.test(out.to.label) && !/^VAV/.test(out.to.label) ? 'an ' : 'a ') + out.to.label.replace(/^(?!VAV)\w/, c => c.toLowerCase());
  } else if (near) {
    const items = (near.items || []).filter(it => !String(it.layer || '').startsWith('ceilings')), rank = it => { const i = citedOrder.indexOf(it.id); return i < 0 ? 99 : i; };
    const pickFrom = items.filter(it => ok.has(it.id)).sort((a, b) => rank(a) - rank(b));
    const seen = new Set(pickFrom.map(it => it.label)), fill = items.filter(it => !ok.has(it.id) && it.vertical === 'above' && !seen.has(it.label) && seen.add(it.label));
    const marks = [...pickFrom, ...fill].slice(0, 5).map(it => ({id: it.id, label: shortName(it), picto: pictogram(it), layer: it.layer, cited: ok.has(it.id),
      above: it.vertical === 'above', dy: Number(it.vertical_gap_m) || 0, dh: Number(it.horizontal_gap_m) || 0}));
    const counts = Object.entries(near.counts_by_layer || {}).filter(([layer]) => !layer.startsWith('ceilings')).slice(0, 5).map(([layer, n]) => ({layer, n, word: SYS_WORD[layer] || layer, picto: PICTO_FOR_LAYER[layer] || 'box'}));
    const upAll = marks.filter(m => m.above && m.dy >= .03).sort((a, b) => a.dy - b.dy), up = upAll.some(m => m.cited) ? upAll.filter(m => m.cited) : upAll, top = up.find(m => m.dh < .3) || up[0];   // the headline names what the answer cited; an uncited neighbour only when nothing cited is above;   // touching neighbours (0 m) do not make a headline
    Object.assign(out, {kind: 'near', self: {label: shortName(selEl), picto: pictogram(selEl)}, marks, counts, total: near.total || 0, radius: near.radius_m || null, aboveOnly: !!near.above_only});
    out.headline = top ? `${top.label} ${mFmt(top.dy)} above` : `${out.total} things within ${near.radius_m || 2} m`;
  } else if (room || elv || selId || primary) {
    const el = Object.assign({}, selEl, elv || {}, (!selId && byId.get(primary)) || {});
    Object.assign(out, {kind: 'lookup', element: {label: niceName(el), picto: pictogram(el), layer: el.layer || null}, size: sizeText(el),
      level: LEVEL_WORD((room && room.level) || el.level), room: roomChip(room)});
    out.headline = niceName(el);
  }
  if (out.kind === 'text') {
    out.items = cites.filter(c => ok.has(c.id)).slice(0, 4).map(c => ({id: c.id, label: shortName(c), picto: pictogram(c), layer: c.layer}));
    const first = captionText(answer, 1);
    out.headline = first.length > 46 ? first.slice(0, 46).replace(/\s+\S*$/, '') + '…' : first;
    out.caption = captionText(answer, 3).slice(first.length).trim() || '';
  }
  out.check = checkText(answer, out.kind);
  return out;
}

/* small neutral mark (four-point spark) drawn here, no logo file */
function drawMark(ctx, cx, cy, r, color = '#e2e8f0') {
  ctx.save(); ctx.fillStyle = color; ctx.translate(cx, cy); ctx.beginPath();
  for (let k = 0; k < 4; k++) { const a = k * Math.PI / 2; ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r); ctx.quadraticCurveTo(0, 0, Math.cos(a + Math.PI / 4) * r * .22, Math.sin(a + Math.PI / 4) * r * .22); }
  ctx.closePath(); ctx.fill(); ctx.restore();
}
/* pictograms: line drawings in a square of side s centred on (cx, cy) */
function drawPicto(ctx, key, cx, cy, s, color = '#e2e8f0') {
  const h = s / 2, L = (x1, y1, x2, y2) => { ctx.beginPath(); ctx.moveTo(cx + x1 * h, cy + y1 * h); ctx.lineTo(cx + x2 * h, cy + y2 * h); ctx.stroke(); };
  const R = (x, y, w, hh, fill) => { ctx.beginPath(); ctx.rect(cx + x * h, cy + y * h, w * h, hh * h); fill ? ctx.fill() : ctx.stroke(); };
  const C = (x, y, r, fill) => { ctx.beginPath(); ctx.arc(cx + x * h, cy + y * h, r * h, 0, Math.PI * 2); fill ? ctx.fill() : ctx.stroke(); };
  ctx.save(); ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = Math.max(2, s * .07); ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  switch (key) {
    case 'vent': R(-.8, -.8, 1.6, 1.6); R(-.45, -.45, .9, .9); L(-.8, -.8, -.45, -.45); L(.8, -.8, .45, -.45); L(-.8, .8, -.45, .45); L(.8, .8, .45, .45); break;
    case 'light': R(-.85, -.55, 1.7, .4, true); for (const x of [-.6, 0, .6]) L(x, -.02, x * 1.35, .75); break;
    case 'duct': R(-.85, -.35, 1.25, .8); L(-.85, -.35, -.45, -.7); L(.4, -.35, .8, -.7); L(-.45, -.7, .8, -.7); L(.8, -.7, .8, .1); L(.4, .45, .8, .1); break;
    case 'damper': R(-.8, -.6, 1.6, 1.2); for (const y of [-.3, 0, .3]) L(-.55, y + .12, .55, y - .12); break;
    case 'pipe': L(-.85, -.28, .6, -.28); L(-.85, .28, .6, .28); ctx.beginPath(); ctx.ellipse(cx + .6 * h, cy, .14 * h, .28 * h, 0, 0, Math.PI * 2); ctx.stroke(); break;
    case 'conduit': L(-.85, -.12, .85, -.12); L(-.85, .12, .85, .12); break;
    case 'sprinkler': L(-.9, -.55, .9, -.55); L(-.9, -.3, .9, -.3); L(0, -.3, 0, .1); L(-.3, .12, .3, .12); for (const [x, y] of [[-.45, .5], [0, .65], [.45, .5]]) C(x, y, .09, true); break;
    case 'valve': ctx.beginPath(); ctx.moveTo(cx - .8 * h, cy - .45 * h); ctx.lineTo(cx + .8 * h, cy + .45 * h); ctx.lineTo(cx + .8 * h, cy - .45 * h); ctx.lineTo(cx - .8 * h, cy + .45 * h); ctx.closePath(); ctx.stroke(); L(0, 0, 0, -.7); L(-.3, -.7, .3, -.7); break;
    case 'beam': R(-.8, -.7, 1.6, .25, true); R(-.8, .45, 1.6, .25, true); R(-.12, -.45, .24, .9, true); break;
    case 'vav': R(-.85, -.5, 1.7, 1); C(-.2, 0, .3); L(-.2, -.3, -.2, .3); L(.25, 0, .65, 0); L(.5, -.13, .65, 0); L(.5, .13, .65, 0); break;
    case 'ceiling': L(-.9, -.2, .9, -.2); for (const x of [-.6, -.2, .2, .6]) L(x, -.2, x, .2); L(-.9, .2, .9, .2); break;
    case 'sensor': C(0, .1, .22, true); ctx.beginPath(); ctx.arc(cx, cy + .1 * h, .5 * h, -2.4, -.75); ctx.stroke(); ctx.beginPath(); ctx.arc(cx, cy + .1 * h, .8 * h, -2.4, -.75); ctx.stroke(); break;
    case 'equipment': R(-.75, -.6, 1.5, 1.2); C(0, 0, .3); L(-.75, -.3, -.95, -.3); L(.75, .3, .95, .3); break;
    case 'check': C(0, 0, .8); L(-.35, 0, -.08, .3); L(-.08, .3, .4, -.3); break;
    default: R(-.6, -.45, 1, .9); L(-.6, -.45, -.25, -.75); L(.4, -.45, .75, -.75); L(-.25, -.75, .75, -.75); L(.75, -.75, .75, .15); L(.4, .45, .75, .15);
  }
  ctx.restore();
}
const sysColor = layer => SYS[layer] || (String(layer || '').startsWith('ceilings') ? SYS.ceiling : '#e2e8f0');
function pill(ctx, x, y, text, {h = 40, size = 24, fill = 'rgba(255,255,255,.08)', stroke = null, color = '#f1f5f9', weight = '600', maxW = 600} = {}) {
  ctx.font = `${weight} ${size}px Arial`; let t = text;
  while (ctx.measureText(t).width + h * .7 > maxW && t.length > 4) t = t.slice(0, -2) + '…';
  const w = ctx.measureText(t).width + h * .7;
  ctx.fillStyle = fill; rr(ctx, x, y, w, h, h / 2); ctx.fill(); if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 2.5; ctx.stroke(); }
  ctx.fillStyle = color; ctx.fillText(t, x + h * .35, y + h / 2 + size * .36); return w;
}
function tile(ctx, x, y, w, h, color) { ctx.fillStyle = 'rgba(255,255,255,.05)'; rr(ctx, x, y, w, h, 22); ctx.fill(); ctx.strokeStyle = color; ctx.globalAlpha = .55; ctx.lineWidth = 2; ctx.stroke(); ctx.globalAlpha = 1; }
function drawLookup(ctx, v, x, y, w, h) {
  const col = sysColor(v.element.layer);
  tile(ctx, x, y, 290, h, col); drawPicto(ctx, v.element.picto, x + 145, y + h * .44, 150, col);
  ctx.textAlign = 'center'; ctx.fillStyle = '#e2e8f0'; fit(ctx, shortName(v.element), x + 145, y + h - 26, 260, 28, '600'); ctx.textAlign = 'left';
  let ry = y + 10; const rx = x + 330, rw = w - 330;
  const row = (k, val) => { ctx.font = '600 22px Arial'; ctx.fillStyle = '#8aa2b8'; ctx.fillText(k.toUpperCase(), rx, ry + 22); ctx.fillStyle = '#fff'; fit(ctx, val, rx, ry + 70, rw, 44, '700'); ry += 96; };
  if (v.size) row('Size', v.size);
  if (v.level) row('Level', v.level);
  if (v.room) {
    ctx.font = '600 22px Arial'; ctx.fillStyle = '#8aa2b8'; ctx.fillText('ROOM', rx, ry + 22);
    ctx.fillStyle = '#fff'; fit(ctx, v.room.name, rx, ry + 64, rw, 38, '700');
    let dx = rx; for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.arc(dx + 10, ry + 94, 9, 0, Math.PI * 2); ctx.fillStyle = i < v.room.dots ? '#fbbf24' : 'rgba(255,255,255,.18)'; ctx.fill(); dx += 26; }
    ctx.font = '600 24px Arial'; ctx.fillStyle = '#fde68a'; ctx.fillText(v.room.word, dx + 8, ry + 102); const ww = ctx.measureText(v.room.word).width;
    ctx.font = '22px Arial'; ctx.fillStyle = '#a9c1d6'; fit(ctx, '· ' + v.room.basis, dx + 18 + ww, ry + 102, rw - (dx + 18 + ww - rx), 22);
  } else if (!v.size && !v.level) { ctx.font = '26px Arial'; ctx.fillStyle = '#a9c1d6'; ctx.fillText('No size or room in the model record', rx, ry + 40); }
}
function drawNear(ctx, v, x, y, w, h) {
  const gw = Math.round(w * .6), axX = x + 92, base = y + h - 54, top = y + 26;
  tile(ctx, x, y, gw, h, '#64748b');
  const above = v.marks.filter(m => m.above), maxDy = Math.max(.5, ...above.map(m => m.dy)), span = Math.min(4, Math.ceil(maxDy * 1.25 / .5) * .5);
  const Y = d => base - (Math.min(d, span) / span) * (base - top);
  ctx.strokeStyle = 'rgba(255,255,255,.35)'; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(axX, base); ctx.lineTo(axX, top - 6); ctx.stroke();
  ctx.font = '600 20px Arial'; ctx.fillStyle = '#8aa2b8'; ctx.textAlign = 'right';
  for (const d of [0, span / 2, span]) { const yy = Y(d); ctx.fillText(d ? '+' + mFmt(d) : '0', axX - 12, yy + 7); ctx.beginPath(); ctx.moveTo(axX - 6, yy); ctx.lineTo(axX + 6, yy); ctx.stroke(); }
  ctx.textAlign = 'left';
  // the selected element at height 0
  drawPicto(ctx, v.self.picto, axX + 46, base + 22, 40, '#ffffff'); ctx.font = '600 22px Arial'; ctx.fillStyle = '#fff'; fit(ctx, 'this ' + v.self.label.toLowerCase(), axX + 78, base + 30, gw - 190, 22, '600');
  // markers, labels pushed apart (min 48 px) with a leader to the true height
  const ms = above.slice().sort((a, b) => a.dy - b.dy); let last = base - 10; const lab = [];
  for (const m of ms) { let ly = Math.min(Y(m.dy), last - 48); ly = Math.max(ly, top + 8); lab.push([m, ly]); last = ly; }
  for (const [m, ly] of lab) {
    const col = sysColor(m.layer), yy = Y(m.dy);
    ctx.strokeStyle = col; ctx.lineWidth = m.cited ? 4 : 2; ctx.beginPath(); ctx.moveTo(axX - 8, yy); ctx.lineTo(axX + 24, yy); ctx.lineTo(axX + 40, ly); ctx.stroke();
    drawPicto(ctx, m.picto, axX + 70, ly, 40, col);
    ctx.font = '700 26px Arial'; ctx.fillStyle = '#fff'; const t = '+' + mFmt(m.dy); ctx.fillText(t, axX + 100, ly + 9); const tw = ctx.measureText(t).width;
    ctx.fillStyle = m.cited ? '#e2e8f0' : '#a9c1d6'; fit(ctx, m.label.toLowerCase() + (m.dh >= .3 ? ' · ' + mFmt(m.dh) + ' aside' : ''), axX + 110 + tw, ly + 9, gw - (axX - x) - 130 - tw, 24, m.cited ? '600' : '');
  }
  const beside = v.marks.filter(m => !m.above).slice(0, 2);
  if (beside.length) { ctx.font = '22px Arial'; ctx.fillStyle = '#a9c1d6'; fit(ctx, 'beside: ' + beside.map(m => m.label.toLowerCase() + ' ' + mFmt(m.dh)).join(', '), x + 20, y + h - 12, gw - 40, 22); }
  // counts by system
  const cx = x + gw + 24, cw = w - gw - 24; tile(ctx, cx, y, cw, h, '#64748b');
  ctx.font = '600 22px Arial'; ctx.fillStyle = '#8aa2b8'; fit(ctx, `${v.total} ITEMS WITHIN ${v.radius || 2} M` + (v.aboveOnly ? ' ABOVE' : ''), cx + 18, y + 38, cw - 36, 22, '600');
  const maxN = Math.max(1, ...v.counts.map(c => c.n)); let yy = y + 66;
  for (const c of v.counts) {
    const col = sysColor(c.layer); drawPicto(ctx, c.picto, cx + 38, yy + 22, 34, col);
    ctx.font = '600 22px Arial'; ctx.fillStyle = '#e2e8f0'; fit(ctx, c.word, cx + 66, yy + 16, cw - 140, 22, '600');
    ctx.textAlign = 'right'; ctx.font = '700 24px Arial'; ctx.fillStyle = '#fff'; ctx.fillText(String(c.n), cx + cw - 16, yy + 18); ctx.textAlign = 'left';
    ctx.fillStyle = col; ctx.globalAlpha = .75; rr(ctx, cx + 66, yy + 26, Math.max(6, (cw - 90) * c.n / maxN), 10, 5); ctx.fill(); ctx.globalAlpha = 1;
    yy += 58; if (yy > y + h - 40) break;
  }
}
function drawTrace(ctx, v, x, y, w, h) {
  const midY = y + h * .42, ax = x + 130, bx = x + w - 130, col = SYS.duct;
  for (const [cx, el, sub] of [[ax, v.from, 'this ' + v.from.label.toLowerCase()], [bx, v.to, (v.away != null ? mFmt(v.away) + ' away' : '') + (v.where ? (v.away != null ? ' · ' : '') + v.where : '')]]) {
    tile(ctx, cx - 115, midY - 105, 230, 210, el === v.to ? hex(COLORS.primary) : '#94a3b8'); drawPicto(ctx, el.picto, cx, midY - 18, 110, el === v.to ? '#ffd1fb' : '#e2e8f0');
    ctx.textAlign = 'center'; ctx.fillStyle = '#fff'; fit(ctx, el.label, cx, midY + 78, 210, 28, '700');
    ctx.fillStyle = '#a9c1d6'; fit(ctx, sub, cx, midY + 140, 260, 24, ''); ctx.textAlign = 'left';
  }
  // the run between them: a chain of short duct pieces
  const x0 = ax + 125, x1 = bx - 125, n = 7, seg = (x1 - x0) / n;
  ctx.fillStyle = col;
  for (let i = 0; i < n; i++) { ctx.globalAlpha = .35 + .55 * (i / (n - 1)); rr(ctx, x0 + i * seg + 4, midY - 12, seg - 8, 24, 6); ctx.fill(); }
  ctx.globalAlpha = 1; ctx.textAlign = 'center';
  ctx.font = '700 40px Arial'; ctx.fillStyle = '#fff'; ctx.fillText(v.hops != null ? String(v.hops) : '?', (x0 + x1) / 2, midY - 34);
  ctx.font = '600 24px Arial'; ctx.fillStyle = '#bae6fd'; ctx.fillText(v.pieceWord + ' along the run', (x0 + x1) / 2, midY + 50);
  ctx.textAlign = 'left';
  ctx.font = '22px Arial'; ctx.fillStyle = '#a9c1d6';
  const note = 'Lit up in the room · found from touching pieces, no flow direction in the model';
  ctx.strokeStyle = col; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(x + 20, y + h - 18); ctx.lineTo(x + 60, y + h - 18); ctx.stroke();
  fit(ctx, note, x + 74, y + h - 10, w - 90, 22);
}
function drawItems(ctx, v, x, y, w, h) {
  const items = v.items || []; if (!items.length) return false;
  const tw = Math.min(220, (w - 20 * (items.length - 1)) / items.length);
  items.forEach((it, i) => { const tx = x + i * (tw + 20), col = sysColor(it.layer); tile(ctx, tx, y, tw, h, col); drawPicto(ctx, it.picto, tx + tw / 2, y + h * .42, Math.min(110, tw * .55), col);
    ctx.textAlign = 'center'; ctx.fillStyle = '#fff'; fit(ctx, it.label, tx + tw / 2, y + h - 52, tw - 20, 26, '600'); ctx.fillStyle = '#8aa2b8'; fit(ctx, '#' + it.id, tx + tw / 2, y + h - 18, tw - 20, 20, ''); ctx.textAlign = 'left'; });
  return true;
}
/* The answer card. view: {phase: 'thinking'|'answer'|'error', model (cardModel; model.visual from answerVisual), steps: [text],
   error, speech: 'speaking'|'done'|'text only'|..., progress, modeLabel, footer} */
function drawAnswer(ctx, W, H, view) {
  const m = view.model || {}, pad = 40, v = m.visual || null;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(10,16,24,.94)'; rr(ctx, 4, 4, W - 8, H - 8, 28); ctx.fill();
  ctx.strokeStyle = view.phase === 'error' ? '#e2725b' : 'rgba(226,232,240,.35)'; ctx.lineWidth = 3; ctx.stroke();
  // header: small mark + "AI answer", mode, read-aloud state
  drawMark(ctx, pad + 14, 46, 15, '#e2e8f0');
  ctx.font = '600 24px Arial'; ctx.fillStyle = '#a9c1d6'; ctx.fillText('AI answer', pad + 38, 55);
  let hx = pad + 38 + ctx.measureText('AI answer').width + 16;
  const mode = view.modeLabel || (m.mode === 'live' ? 'LIVE' : m.mode === 'mock' ? 'MOCK' : '');
  if (mode) hx += pill(ctx, hx, 32, mode, {h: 32, size: 19, weight: '700', fill: mode === 'LIVE' ? '#14532d' : '#6a4a10', color: mode === 'LIVE' ? '#86efac' : '#fcd34d'}) + 12;
  if (view.speech) { const sp = view.speech, t = sp === 'speaking' ? 'READ ALOUD' : sp.toUpperCase(), col = sp === 'speaking' ? '#fde68a' : '#8aa2b8'; ctx.textAlign = 'right'; ctx.font = '700 20px Arial'; ctx.fillStyle = col; ctx.fillText(t, W - pad, 55); const tw = ctx.measureText(t).width; ctx.textAlign = 'left'; drawSpeaker(ctx, W - pad - tw - 38, 48, 28, col); }
  let y = 92;
  if (view.phase === 'thinking' || view.phase === 'error' || !v) {
    if (m.question) { ctx.font = 'italic 28px Arial'; ctx.fillStyle = '#a9c1d6'; for (const t of wrap(ctx, '“' + m.question + '”', W - 2 * pad, 2)) { ctx.fillText(t, pad, y + 20); y += 36; } y += 14; }
  }
  if (view.phase === 'thinking') {
    ctx.fillStyle = '#e8f1f8'; fit(ctx, view.progress || 'Thinking…', pad, y + 30, W - 2 * pad, 40, '700'); y += 80;
    ctx.font = '26px Arial';
    for (const s of (view.steps || []).slice(-6)) { drawPicto(ctx, 'check', pad + 14, y - 9, 26, '#34d399'); ctx.fillStyle = '#cfe3f5'; fit(ctx, s, pad + 40, y, W - 2 * pad - 40, 26); y += 40; }
  } else if (view.phase === 'error') {
    ctx.font = '700 38px Arial'; ctx.fillStyle = '#ffb4a8'; ctx.fillText('Could not answer', pad, y + 20); y += 66;
    ctx.font = '30px Arial'; ctx.fillStyle = '#e8f1f8'; for (const t of wrap(ctx, view.error || '', W - 2 * pad, 4)) { ctx.fillText(t, pad, y); y += 40; }
  } else if (v) {
    // headline
    ctx.fillStyle = '#ffffff'; fit(ctx, v.headline || m.lead || '', pad, y + 50, W - 2 * pad, 56, '700'); y += 78;
    // the picture
    const bh = 330, by = y;
    const drawn = v.kind === 'lookup' ? (drawLookup(ctx, v, pad, by, W - 2 * pad, bh), true) : v.kind === 'near' ? (drawNear(ctx, v, pad, by, W - 2 * pad, bh), true)
      : v.kind === 'trace' ? (drawTrace(ctx, v, pad, by, W - 2 * pad, bh), true) : drawItems(ctx, v, pad, by, W - 2 * pad, 250);
    y = drawn ? by + (v.kind === 'text' ? 250 : bh) + 14 : y;
    // caption (the sentence answer, 1-2 lines)
    ctx.font = '25px Arial'; ctx.fillStyle = '#b8c9d9';
    for (const t of wrap(ctx, v.caption || '', W - 2 * pad, drawn ? 2 : 6)) { ctx.fillText(t, pad, y + 22); y += 32; }
    // bottom rows: check on site, then the evidence ids
    const ry = H - 200;
    const cw = pill(ctx, pad, ry, '      ' + v.check, {h: 46, size: 24, fill: 'rgba(251,191,36,.16)', stroke: '#fbbf24', color: '#fde68a', weight: '700', maxW: W - 2 * pad});
    drawPicto(ctx, 'check', pad + 27, ry + 23, 26, '#fbbf24');
    let cx = pad; const ey = H - 140;
    ctx.font = '600 19px Arial'; ctx.fillStyle = '#8aa2b8'; ctx.fillText('EVIDENCE', cx, ey + 23); cx += ctx.measureText('EVIDENCE').width + 14;
    for (const c of m.chips || []) {
      const col = !c.verified ? '#ef4444' : c.primary ? hex(COLORS.primary) : hex(COLORS.other);
      ctx.font = '600 20px Arial'; const t = '#' + c.id + ' ' + shortName(c).toLowerCase(), wNeed = Math.min(ctx.measureText(t).width + 24, 260); if (cx + wNeed > W - pad) break;
      const w = pill(ctx, cx, ey, t, {h: 34, size: 20, fill: 'rgba(255,255,255,.06)', stroke: col, color: c.verified ? '#f1f5f9' : '#fca5a5', maxW: 260});
      if (!c.verified) { ctx.strokeStyle = '#fca5a5'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(cx + 8, ey + 17); ctx.lineTo(cx + w - 8, ey + 17); ctx.stroke(); }
      cx += w + 8;
    }
  } else {
    // no visual model (older page): the text card as before
    ctx.font = '700 36px Arial'; ctx.fillStyle = '#ffffff';
    for (const t of wrap(ctx, m.lead || '', W - 2 * pad, 6)) { ctx.fillText(t, pad, y + 10); y += 46; }
    let cx = pad;
    for (const c of m.chips || []) { const w = pill(ctx, cx, H - 170, '#' + c.id + ' ' + c.label, {h: 40, size: 22, stroke: c.primary ? hex(COLORS.primary) : hex(COLORS.other), maxW: W - pad - cx}); cx += w + 10; if (cx > W - 200) break; }
  }
  const f = (m.footer && m.footer.length ? m.footer : view.footer) || [];
  if (view.runNote && !(v && v.kind === 'trace') && view.phase === 'answer') { ctx.fillStyle = '#9fe7f5'; fit(ctx, view.runNote, pad, H - 70, W - 2 * pad, 20); }
  ctx.fillStyle = '#7f94a8';
  if (f[0]) fit(ctx, f[0], pad, H - 44, W - 2 * pad, 20);
  ctx.fillStyle = '#7f94a8';
  if (f[1]) fit(ctx, f[1], pad, H - 18, W - 2 * pad, 20);
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
    rr(ctx, x, y, w, h, 16); ctx.fill(); ctx.strokeStyle = hov ? '#fff' : b.id === 'mic' && b.tone !== 'off' ? '#fbbf24' : '#5d82a3'; ctx.lineWidth = hov ? 6 : 3; ctx.stroke();
    ctx.textAlign = 'center'; ctx.fillStyle = hov ? '#0b1020' : b.disabled ? '#7b8da0' : '#fff';
    fit(ctx, b.label, x + w / 2, y + h * .48, w - 20, 34, '700');
    ctx.fillStyle = hov ? '#0b1020' : '#9fb6cb'; fit(ctx, b.sub || '', x + w / 2, y + h * .8, w - 20, 22, '500');
    ctx.textAlign = 'left';
  });
}

return {API, LEVELS, COLORS, BAR, SYS, parseParams, createStream, sections, leadId, plainLine, cardModel, speakable, runPath, runGlow,
  barRects, barHit, barButtons, micPlan, ttsPlan, wrap, drawMark, drawPicto, drawAnswer, drawBar,
  pictogram, niceName, sizeText, roomChip, captionText, checkText, answerVisual,
  serverOrigin, privateIPv4, apiUrl, healthProblem, accessCode, askHeaders, refusalText, progressText, EARCONS, HOLD_MS, holdAskAllowed, FILLER_MS};
});
