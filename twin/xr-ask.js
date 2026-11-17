/* Ask the twin inside the headset page (scan-xr.html?ask=1, served by scripts/ask_twin_server.py on the laptop).
   DOM overlays are invisible in an immersive session, so everything the user sees is drawn on 2D canvases that the page
   puts on planes in the scene. This file holds the logic and the drawing only (no three.js, no DOM queries):
     - the preset questions of the four levels (look up · nearby in 3D · trace a system · reason across sources),
     - the answer stream parser (Server-Sent Events from /api/ask),
     - the in-view answer card (headline + a picture built from the tool results + caption, check chip, cited ids, provenance),
     - the spoken text, the run lighting timing for connected_run, the voice/TTS plans,
     - the waiting state (2026-11-15): step lines from the stream events (stepsAdd), the Claude-style starburst, and the pure
       timing of what the page animates on small overlay meshes (markPose, dotWave, revealPose, waitPulse),
     - the decluttered in-view controls (2026-11-15): one compact element label with a hold-to-ask hint and a small "⋯", the
       presets panel behind that "⋯", and their hit tests.
   Unit-tested in tests/xr-ask.test.cjs. The page is unchanged unless it is opened with ?ask=1. NOT verified on a headset. */
(function (root, factory) {
  const api = factory();
  if (root) root.XRAsk = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this), function () {
'use strict';

const API = 5;   // 3: access code (code=, X-Ask-Code, refusalText) · 4: the Claude mark path, headerNote, upright settle · 5: pair once (X-Ask-Token, auto-connect)
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
/* The code when there is one (a printed link or a typed code), else a paired device's token (X-Ask-Token, header only). */
function askHeaders(code, extra = {}, token = null) {
  if (code) return Object.assign({}, extra, {'X-Ask-Code': code});
  return token && TOKEN_RX.test(token) ? Object.assign({}, extra, {'X-Ask-Token': token}) : Object.assign({}, extra);
}
/* 401 / 429 from the ask server -> the sentence the card shows (null for any other status). */
function refusalText(status, body = {}) {
  const b = body || {};
  if (status === 401 && b.reason === 'token_unknown') return 'This headset is no longer paired with the laptop. Type the code shown on the laptop in the Ask the twin box.';
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
const TUNNEL_HOST = /^[a-z0-9]+(?:-[a-z0-9]+){1,7}\.trycloudflare\.com$/;
function serverOrigin(raw) {
  const s = String(raw || '').trim();
  if (!/^https:\/\/[^/?#@\s]+(\/)?$/i.test(s)) return null;   // https only, no path, query, fragment or credentials
  let u; try { u = new URL(s); } catch (e) { return null; }
  if (u.protocol !== 'https:' || u.username || u.password) return null;
  const host = u.hostname.toLowerCase(), typed = /^https:\/\/([^:/]+)/i.exec(s)[1].toLowerCase();
  if (typed !== host) return null;   // refuse anything the URL parser had to rewrite (0x7f.1, 192.168.001.2, ...)
  // The temporary public address of scripts/ask_twin_public.sh (a Cloudflare quick tunnel in front of the laptop): exactly
  // <words>.trycloudflare.com on 443. The page then comes from GitHub Pages (fast) and only the AI calls go to the laptop.
  if (!u.port) return TUNNEL_HOST.test(host) ? 'https://' + host : null;   // every other host needs an explicit (non-443) port
  if (!(host === 'localhost' || privateIPv4(host))) return null;
  return 'https://' + host + ':' + u.port;
}
/* Connect with the code only (2026-11-13): the laptop's temporary address changes on every start and is far too long to type
   on a headset. scripts/ask_twin_public.sh writes the current address (never the access code) to one small file on the
   'ask-endpoint' branch of the public repository; the page reads it, checks that it has exactly the temporary-address form, and
   the visitor types only the six-character code from the laptop screen. The address alone opens nothing: questions need the code. */
const ENDPOINT = {api: 'https://api.github.com/repos/doe2park/Graduate-Project/contents/ask-endpoint.json?ref=ask-endpoint',
  raw: 'https://raw.githubusercontent.com/doe2park/Graduate-Project/ask-endpoint/ask-endpoint.json', staleHours: 18};
function endpointFrom(doc, nowMs) {
  if (!doc || typeof doc !== 'object' || typeof doc.server !== 'string') return {ok: false, why: 'No laptop has announced an address yet. Start the server on the laptop.'};
  const server = serverOrigin(doc.server);
  if (!server || !TUNNEL_HOST.test(server.slice(8))) return {ok: false, why: 'The announced address is not a valid temporary address. Start the server on the laptop again.'};
  const t = Date.parse(doc.updated), ageH = Number.isFinite(t) && Number.isFinite(nowMs) ? Math.max(0, (nowMs - t) / 3600000) : null;
  return {ok: true, server, ageH, stale: ageH != null && ageH > ENDPOINT.staleHours};
}
/* What the visitor typed -> the access code (letters and digits, upper case), or null. */
function connectCode(raw) { const c = String(raw == null ? '' : raw).toUpperCase().replace(/[^A-Z0-9]/g, ''); return c.length >= 4 && c.length <= 32 ? c : null; }

/* Pair once (2026-11-17). The first Connect with the code also asks the laptop for a device token (POST /api/pair); the page keeps
   it in this browser's localStorage (PAIR_KEY) and later sends it as X-Ask-Token instead of a code. The laptop stores only its hash
   (scripts/ask_twin/pairing.py). On later visits with no ask/server/code in the address, the page reads the announced address,
   checks that the laptop answers and still knows the token, and turns Ask on with no typing. The token never goes into a URL.
   "Forget this laptop" deletes it here and (if the laptop answers) there. */
const PAIR_KEY = 'askTwin.pairing.v1', TOKEN_RX = /^[A-Za-z0-9_-]{32,128}$/, NET_MS = 8000;
function loadPairing(storage) {
  try { const p = JSON.parse(storage?.getItem(PAIR_KEY) || 'null'); return p && typeof p === 'object' && TOKEN_RX.test(p.token || '') ? {token: p.token, at: typeof p.at === 'string' ? p.at : null} : null; }
  catch (e) { return null; }
}
function savePairing(storage, token, nowMs = Date.now()) {
  if (!TOKEN_RX.test(token || '')) return false;
  try { storage.setItem(PAIR_KEY, JSON.stringify({token, at: new Date(nowMs).toISOString()})); return loadPairing(storage)?.token === token; } catch (e) { return false; }
}
function forgetPairing(storage) { try { storage?.removeItem(PAIR_KEY); return true; } catch (e) { return false; } }
/* 'url': the address says what to do (ask=1, server= or code= present; the stored token stands in for a missing code);
   'auto': nothing in the address but this browser is paired -> find the laptop by itself; 'off': neither. */
function connectPlan(search, pairing) {
  const q = new URLSearchParams(search || '');
  if (q.get('ask') === '1' || q.has('server') || q.has('code')) return 'url';
  return pairing ? 'auto' : 'off';
}
/* The entry card's one state line. */
function connectLine(state, {mode = '', paired = false} = {}) {
  const m = String(mode || '').toUpperCase();
  switch (state) {
    case 'connecting': return {state, text: paired ? 'Connecting to the laptop…' : 'Looking for the laptop…'};
    case 'connected': return {state, text: 'Connected' + (m ? ' · ' + m : '')};
    case 'down': return {state, text: 'Laptop not running',
      note: 'The laptop is not answering, so Ask the twin is off. Everything else on this page works. Start Ask on the laptop, then press Try again.'};
    case 'unpaired': return {state, text: 'Not connected', note: 'The laptop no longer knows this headset. Type the code shown on the laptop and press Connect.'};
    default: return {state: 'off', text: 'Not connected'};
  }
}
/* fetch with a time limit (a dead tunnel address should not leave the card spinning). */
async function fetchT(fetchFn, url, opts = {}, ms = NET_MS) {
  const ac = typeof AbortController !== 'undefined' ? new AbortController() : null, t = ac ? setTimeout(() => ac.abort(), ms) : 0;
  try { return await fetchFn(url, Object.assign({cache: 'no-store'}, opts, ac ? {signal: ac.signal} : {})); } finally { clearTimeout(t); }
}
/* The announced address (ENDPOINT, GitHub API first, then raw) -> is that laptop answering? -> {ok, server, health, stale} or
   {ok:false, state:'down', why}. Never sends a code or token. */
async function findLaptop(fetchFn, nowMs = Date.now()) {
  let doc = null;
  for (const [u, h] of [[ENDPOINT.api, {Accept: 'application/vnd.github.raw+json'}], [ENDPOINT.raw + '?t=' + nowMs, {}]]) {
    try { const r = await fetchT(fetchFn, u, {headers: h}); if (r.ok) { doc = await r.json(); break; } } catch (e) { /* next source */ }
  }
  const e = endpointFrom(doc, nowMs);
  if (!e.ok) return {ok: false, state: 'down', why: e.why};
  try {
    const r = await fetchT(fetchFn, e.server + '/api/health');
    if (!r.ok) throw new Error('status ' + r.status);
    return {ok: true, server: e.server, health: await r.json(), stale: e.stale};
  } catch (err) {
    return {ok: false, state: 'down', server: e.server, why: 'The laptop' + (e.stale ? ' has not announced a new address for a while and' : '') + ' does not answer.'};
  }
}
/* Typed code -> device token from the laptop. {ok, token} · {ok:false, fallback:true} (older server or pairing off: use the code
   for this visit only) · {ok:false, status, why}. */
async function pairWithCode(fetchFn, server, code) {
  let r, b = {};
  try { r = await fetchT(fetchFn, apiUrl(server, 'pair'), {method: 'POST', headers: askHeaders(code, {'Content-Type': 'application/json'}), body: '{}'}); }
  catch (e) { return {ok: false, status: 0, why: 'The laptop stopped answering. Press Connect again.'}; }
  try { b = await r.json(); } catch (e) { b = {}; }
  if (r.ok && TOKEN_RX.test(b.token || '')) return {ok: true, token: b.token, device: b.device || null};
  if (r.status === 404 || r.status === 405 || (r.status === 400 && b.reason === 'pairing_off')) return {ok: false, fallback: true};
  return {ok: false, status: r.status, why: refusalText(r.status, b) || ('Pairing failed (' + r.status + ').')};
}
/* Paired visit: find the laptop, then ask it whether it still knows this token. {ok, server, health} or {ok:false, state, why}. */
async function autoConnect(fetchFn, token, nowMs = Date.now()) {
  const f = await findLaptop(fetchFn, nowMs);
  if (!f.ok) return f;
  let r;
  try { r = await fetchT(fetchFn, apiUrl(f.server, 'pair/check'), {method: 'POST', headers: askHeaders('', {'Content-Type': 'application/json'}, token), body: '{}'}); }
  catch (e) { return {ok: false, state: 'down', server: f.server, why: 'The laptop does not answer.'}; }
  if (r.ok) return {ok: true, server: f.server, health: f.health};
  let b = {}; try { b = await r.json(); } catch (e) { b = {}; }
  if (r.status === 401) return {ok: false, state: 'unpaired', server: f.server, reason: b.reason || null};
  return {ok: false, state: 'down', server: f.server, why: refusalText(r.status, b) || 'The laptop answered with an error (' + r.status + ').'};
}
/* Forget this laptop: tell the laptop (best effort, token in the header), then delete the token here. */
async function forgetLaptop(fetchFn, storage, server) {
  const p = loadPairing(storage);
  let told = false;
  if (p && server) {
    try { const r = await fetchT(fetchFn, apiUrl(server, 'pair/forget'), {method: 'POST', headers: askHeaders('', {'Content-Type': 'application/json'}, p.token), body: '{}'}, 4000); told = r.ok; } catch (e) { told = false; }
  }
  return {forgotten: forgetPairing(storage), told};
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
const HONESTY = 'Design BIM, inferred rooms · demo sensors SIMULATED · not headset-verified';
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
    // honesty footer: ONE small line on the card (mode + provenance); the lookup / verification counts sit on the evidence row
    verified: final ? {n: nv, of: cites.length} : null,
    stats: final ? `${toolCount != null ? toolCount : (final.tools_used || []).length} lookups · ${nv}/${cites.length} cited IDs verified` : '',
    footer: [mode === 'live' ? 'LIVE · ' + (final.model || 'Claude') : mode === 'mock' ? 'MOCK · scripted' : '', HONESTY],
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
/* ---------------------------------------------------------------- waiting state (2026-11-15)
   While the answer is on its way the card shows real progress, driven only by the server's stream events:
     before the first tool event -> "Listening done · thinking" (voice) / "Thinking" (preset), the animated mark only
     each 'tool' event            -> one step line: a line pictogram for the tool + a short phrase ("Following the duct…");
                                     the previous step gets a drawn tick, the newest one an animated three-dot wave
     the first 'text' event       -> "Writing the answer…"
     'final'                      -> every step done (the card then switches to the answer)
   Parallel calls of the same tool with the same phrase share one line (n counts them). No emoji anywhere. */
const STEP_ICON = {room_of: 'room', elements_near: 'height', connected_run: 'route', get_element: 'lookup', find_elements: 'lookup',
  list_sensors: 'sensor', sensor_readings: 'sensor'};
function stepIcon(name) { return STEP_ICON[name] || 'twin'; }
const RUN_WORD = {duct: 'duct', fire: 'sprinkler pipe', plumbing: 'pipe', hydronic: 'pipe', conduit: 'conduit'};
function stepPhrase(ev, el = null) {
  if (!ev) return null;
  if (ev.type === 'text') return 'Writing the answer…';
  if (ev.type !== 'tool') return null;
  const inp = ev.input || {}, layers = inp.layers || [];
  switch (ev.name) {
    case 'room_of': return 'Finding the room…';
    case 'elements_near': return inp.above_only ? 'Checking above…' : layers.length === 1 && LAYER_WORDS[layers[0]] ? 'Checking the ' + LAYER_WORDS[layers[0]] + ' nearby…' : 'Checking around it…';
    case 'connected_run': return 'Following the ' + (RUN_WORD[(el && el.layer) || ''] || 'run') + '…';
    case 'get_element': return 'Looking it up…';
    case 'find_elements': return 'Searching the model…';
    case 'list_sensors': return 'Finding the demo sensors…';
    case 'sensor_readings': return 'Reading the demo sensors (simulated)…';
    default: return 'Checking the twin…';
  }
}
/* steps + one stream event -> {steps, changed}. steps: [{key, icon, text, state: 'done'|'current', n}] (a new array when changed). */
function stepsAdd(steps, ev, el = null) {
  const list = Array.isArray(steps) ? steps : [];
  if (!ev) return {steps: list, changed: false};
  if (ev.type === 'final') {
    if (!list.some(s => s.state !== 'done')) return {steps: list, changed: false};
    return {steps: list.map(s => Object.assign({}, s, {state: 'done'})), changed: true};
  }
  const text = stepPhrase(ev, el);
  if (!text) return {steps: list, changed: false};
  const key = ev.type === 'text' ? 'write' : String(ev.name || 'tool');
  // text streamed before a tool call was a preamble ("Let me check…"), not the answer: that "Writing" line goes away again
  const base = key !== 'write' && list.length && list[list.length - 1].key === 'write' ? list.slice(0, -1) : list, last = base[base.length - 1];
  if (last && last.key === key && last.text === text) {
    if (key === 'write') return {steps: list, changed: false};   // one line for the whole streamed answer
    return {steps: base.slice(0, -1).concat(Object.assign({}, last, {n: (last.n || 1) + 1, state: 'current'})), changed: true};
  }
  const done = base.map(s => s.state === 'done' ? s : Object.assign({}, s, {state: 'done'}));
  return {steps: done.concat({key, icon: key === 'write' ? 'write' : stepIcon(ev.name), text, state: 'current', n: 1}), changed: true};
}
function stepsFrom(events, el = null) { let s = []; for (const ev of events || []) s = stepsAdd(s, ev, el).steps; return s; }
/* the line above the steps: before any tool event this is the whole status */
function waitLabel({heard = false} = {}) { return heard ? 'Listening done · thinking' : 'Thinking'; }
/* done steps read as finished: no trailing ellipsis */
const doneText = t => String(t || '').replace(/…$/, '');

/* Animation timing (pure, ms). Everything that moves per frame is a small separate mesh over the card (mark, three dots, the
   picture cover) or a uniform (element pulse), so the big card canvas is redrawn only on step changes and on the answer. */
const WAIT = {spinMs: 6400, breatheMs: 1800, settleMs: 600, dotMs: 1050, revealMs: 200, pictureDelayMs: 120, pictureMs: 240, pulseMs: 1500};
const clamp01 = x => Math.max(0, Math.min(1, x)), easeOut = x => 1 - Math.pow(1 - clamp01(x), 3);
const RAYS = 12;
/* the mark's rays: n round-capped strokes, evenly spaced, lengths varied in a fixed pattern (drawn in code, not a logo file) */
function starburstRays(n = RAYS) {
  const L = [1, .74, .9, .68, .97, .78, .86, .7, .95, .76, .88, .72];
  return Array.from({length: n}, (_, i) => ({a: -Math.PI / 2 + i * 2 * Math.PI / n + (i % 2 ? .05 : -.03), len: L[i % L.length], w: i % 3 === 0 ? .2 : .17}));
}
/* mark pose at time t (ms since waiting began). settleAt: t when the answer arrived (null = still waiting). While waiting: slow
   rotation + gentle breathing (scale, opacity). After the answer it eases back upright (the nearest whole turn, at most half a turn,
   within settleMs) and stops: the Claude mark is not symmetric, so it must come to rest the right way up. */
function markPose(t, {settleAt = null, reduced = false} = {}) {
  if (reduced) return {rot: 0, scale: 1, opacity: 1, moving: false};
  const spin = tt => 2 * Math.PI * tt / WAIT.spinMs, breathe = tt => Math.sin(2 * Math.PI * tt / WAIT.breatheMs);
  const wait = tt => ({rot: spin(tt), scale: 1 + .07 * breathe(tt), opacity: .82 + .18 * (.5 + .5 * breathe(tt))});
  if (settleAt == null || t < settleAt) return Object.assign(wait(Math.max(0, t)), {moving: true});
  const from = wait(settleAt), turn = 2 * Math.PI, to = Math.round(from.rot / turn) * turn, k = easeOut((t - settleAt) / WAIT.settleMs);
  const moving = t - settleAt < WAIT.settleMs;
  return {rot: from.rot + (to - from.rot) * k, scale: from.scale + (1 - from.scale) * k, opacity: from.opacity + (1 - from.opacity) * k, moving};
}
/* three-dot wave of the current step: [{a, dy}] (opacity 0.3-1, lift in layout px) */
function dotWave(t, {reduced = false} = {}) {
  return [0, 1, 2].map(i => {
    if (reduced) return {a: .8, dy: 0};
    const p = Math.max(0, Math.sin(2 * Math.PI * (t / WAIT.dotMs) - i * .9)), e = p * p;
    return {a: .3 + .7 * e, dy: -5 * e};
  });
}
/* card reveal at t ms: it eases in (scale 0.94 -> 1, opacity from -> 1, revealMs). from = 0 when the card first appears (the
   question is sent); from = 0.55 when the waiting card turns into the answer (a soft cross-fade, not a blink). picture: the picture
   block fills in last (cover 1 -> 0 after pictureDelayMs). */
function revealPose(t, {reduced = false, from = 0, picture = true} = {}) {
  if (reduced) return {scale: 1, opacity: 1, cover: 0, done: true};
  const f = clamp01(from), e = easeOut(t / WAIT.revealMs), c = picture ? 1 - easeOut((t - WAIT.pictureDelayMs) / WAIT.pictureMs) : 0;
  return {scale: 1 - .06 * (1 - f) * (1 - e), opacity: f + (1 - f) * e, cover: c, done: t >= (picture ? WAIT.pictureDelayMs + WAIT.pictureMs : WAIT.revealMs)};
}
/* the asked element while waiting: a soft brightness pulse (glow copy's opacity and boost uniform), no rings */
function waitPulse(t, {reduced = false} = {}) {
  if (reduced) return {opacity: .45, boost: .2};
  const p = .5 - .5 * Math.cos(2 * Math.PI * t / WAIT.pulseMs);
  return {opacity: .22 + .38 * p, boost: .55 * p};
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
function runGlow(i, n, t, {stepMs = 90, fadeMs = 220, pulseMs = 1600, base = .5, reduced = false} = {}) {   // base: a lit piece stays this solid; the pulse only adds to it
  if (reduced) return .5;
  const on = t - i * stepMs;
  if (on <= 0) return 0;
  let a = base * Math.min(1, on / fadeMs);
  const after = t - n * stepMs;
  if (after > 0 && n > 1) { const p = ((after % pulseMs) / pulseMs) * (n + 4) - 2, d = i - p; a += .3 * Math.exp(-(d * d) / 3); }
  return Math.min(.8, a);
}

/* ---------------------------------------------------------------- decluttered headset controls (2026-11-15)
   Demo feedback: picking an element showed an info card plus a six-button bar, too much at once. Now:
     picked     -> ONE compact label next to the element: "<type> · <level>", a hint line ("Hold trigger to ask"), a small honesty
                   line, and a small "⋯" at its right end. Holding the trigger on the element (or on the label) asks by voice.
     listening  -> the same label says "Listening… release to ask" (the ring pulses on the element)
     answer     -> only the answer card, with its own small "⋯" in the top-right corner
     "⋯"        -> the presets panel: the four preset questions (noisy rooms, no microphone), Details (the full element card), Close
   Dismiss without a button: point away and pull the trigger on empty space, or B/Y (Escape on the desktop).
   (u, v) below are plane UVs, v up (three.js PlaneGeometry). Sizes are layout units; the page draws them at a higher pixel scale. */
const CHIP = {W: 640, H: 176, moreX: .8};
const PICTO_WORD = {vent: 'Air vent', vav: 'VAV box', duct: 'Duct', damper: 'Damper', sprinkler: 'Sprinkler pipe', pipe: 'Pipe', valve: 'Valve',
  light: 'Light', beam: 'Beam', ceiling: 'Ceiling', conduit: 'Conduit', equipment: 'Equipment'};
/* label model. el: {label?, type?, name?, layer?, level?}; sensorLabel: the demo sensor's type name when a sensor pin was picked;
   honesty: the page's one-line provenance (alignment / simulated sensor). */
function chipModel({el = null, sensorLabel = '', voice = 'off', busy = false, honesty = ''} = {}) {
  const key = pictogram(el), level = LEVEL_WORD(el && el.level);
  const name = sensorLabel ? sensorLabel : (PICTO_WORD[key] || shortName(el));
  const hint = busy ? {text: 'Thinking…', tone: 'dim'} : voice === 'recording' ? {text: 'Listening… release to ask', tone: 'rec'}
    : voice === 'transcribing' ? {text: 'Transcribing…', tone: 'dim'} : voice === 'off' ? {text: 'Voice off · ⋯ for questions', tone: 'dim'}
    : {text: 'Hold trigger to ask', tone: 'hint'};
  return {title: name + (level ? ' · ' + level : ''), picto: sensorLabel ? 'sensor' : key, layer: (el && el.layer) || null, hint, honesty: String(honesty || '')};
}
function chipHit(u, v) { return u >= CHIP.moreX && u <= 1 && v >= 0 && v <= 1 ? 'more' : 'body'; }
/* the answer card's "⋯": top-right corner (layout 1024 x 800: x >= 914, y <= 92) */
const ANSWER_MORE = {x0: 914 / 1024, y1: 92 / 800};
function answerHit(u, v) { return u >= ANSWER_MORE.x0 && 1 - v <= ANSWER_MORE.y1 ? 'more' : 'body'; }
/* Presets panel (behind "⋯"): 2 rows x 3 buttons. */
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
/* Buttons: the four levels, Details (the full element card), Close. state: {busy, details}. Voice is not a button any more:
   the trigger held on the element is the microphone. */
function barButtons(state = {}) {
  return [...LEVELS.map(l => ({id: l.id, label: l.level + ' · ' + l.label, sub: l.hint, disabled: !!state.busy})),
    {id: 'details', label: state.details ? 'Hide details' : 'Details', sub: 'element record'},
    {id: 'close', label: 'Close', sub: 'B/Y also closes', tone: 'exit'}];
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
   Header (2026-11-15): a Claude-style starburst drawn in code (no logo file) + "Claude · LIVE/MOCK"; MOCK answers are scripted,
   which the mode pill and the footer say. */
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
const LEVEL_WORD = l => { const m = /^(?:L|LEVEL\s*)?0*(\d+)$/i.exec(String(l || '').trim()); return m ? 'Level ' + m[1] : (l ? String(l) : ''); };
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

/* The Claude mark (2026-11-16, "like before"): the Claude spark, irregular rounded rays in Claude terracotta, drawn in code as one
   filled path in a 24 x 24 box (no image file is loaded). It is drawn about the box centre (12, 12) and scaled so the farthest ray tip
   (13.2 units from the centre) stays inside radius r at any rotation (the waiting mark spins). Without Path2D (Node tests) the older
   stroked starburst stands in. rot in radians. */
const CLAUDE_COLOR = '#D97757';
const CLAUDE_MARK_PATH = 'M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.704.231-.243 1.908-1.312-.006.006z';
const CLAUDE_MARK_REACH = 13.2;
function drawStarburst(ctx, cx, cy, r, color = CLAUDE_COLOR, rot = 0) {
  if (typeof Path2D === 'function') {
    const k = r / CLAUDE_MARK_REACH;
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot); ctx.scale(k, k); ctx.translate(-12, -12); ctx.fillStyle = color; ctx.fill(new Path2D(CLAUDE_MARK_PATH)); ctx.restore();
    return;
  }
  ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot); ctx.strokeStyle = color; ctx.lineCap = 'round';
  for (const ray of starburstRays()) {
    ctx.lineWidth = r * ray.w; ctx.beginPath(); ctx.moveTo(Math.cos(ray.a) * r * .12, Math.sin(ray.a) * r * .12);
    ctx.lineTo(Math.cos(ray.a) * r * (ray.len - ray.w / 2), Math.sin(ray.a) * r * (ray.len - ray.w / 2)); ctx.stroke();
  }
  ctx.restore();
}
/* small neutral mark (four-point spark) drawn here, no logo file (kept for other panels) */
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
    // waiting steps (same stroke weight): a drawn tick, floor plan, vertical ruler, route, magnifier, generic twin, writing
    case 'tick': L(-.55, .02, -.15, .42); L(-.15, .42, .6, -.4); break;
    case 'room': R(-.8, -.7, 1.6, 1.4); L(-.1, -.7, -.1, -.05); L(-.1, .3, -.1, .7); L(-.1, -.05, .25, -.05); L(.5, -.05, .8, -.05); break;
    case 'height': L(-.3, -.8, -.3, .8); for (const [y, w] of [[-.8, .5], [-.4, .3], [0, .5], [.4, .3], [.8, .5]]) L(-.3, y, -.3 + w, y); L(.45, -.65, .45, .65); L(.3, -.45, .45, -.65); L(.6, -.45, .45, -.65); L(.3, .45, .45, .65); L(.6, .45, .45, .65); break;
    case 'route': ctx.beginPath(); ctx.moveTo(cx - .65 * h, cy + .55 * h); ctx.lineTo(cx - .1 * h, cy + .55 * h); ctx.lineTo(cx - .1 * h, cy - .5 * h); ctx.lineTo(cx + .6 * h, cy - .5 * h); ctx.stroke();
      C(-.65, .55, .16, true); C(-.1, .02, .12, true); C(.6, -.5, .16); break;
    case 'lookup': C(-.15, -.15, .5); L(.22, .22, .72, .72); L(-.38, -.15, .08, -.15); break;
    case 'twin': R(-.7, -.25, 1.05, .95); L(-.7, -.25, -.35, -.65); L(.35, -.25, .7, -.65); L(-.35, -.65, .7, -.65); L(.7, -.65, .7, .3); L(.35, .7, .7, .3); break;
    case 'write': for (const [y, w] of [[-.55, 1.5], [-.15, 1.5], [.25, 1.0]]) L(-.75, y, -.75 + w, y); L(.35, .65, .8, .2); L(.25, .75, .35, .65); break;
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
/* The answer card. view: {phase: 'thinking'|'answer'|'error', model (cardModel; model.visual from answerVisual),
   wait: {steps (stepsAdd), heard}, error, speech: 'speaking'|'done'|'text only'|..., modeLabel, footer,
   markLayer: true = the page draws the animated mark on its own small mesh (the spot stays empty here)}.
   Returns the layout the page needs for its overlay meshes (layout units): {mark: {x, y, r}, indicator: {x, y} | null,
   picture: {x, y, w, h} | null, h}. h: the height actually used. The waiting card is compact (h < H: the page shows only the top
   h of the canvas, so a two-step wait is not a mostly empty panel); the answer and error cards use the full H. */
function waitHeight(ctx, W, H, question, nSteps) {
  ctx.font = 'italic 27px Arial';
  const q = question ? 50 + wrap(ctx, '“' + question + '”', W - 80, 2).length * 35 + 58 : 0;
  return Math.min(H, Math.max(360, Math.round(92 + q + (nSteps ? 44 + nSteps * 70 : 70) + 70)));
}
const CARD_BG = 'rgba(10,16,24,.97)', MARK = {x: 64, y: 50, r: 30};
/* The header word (2026-11-16): the mark + "Claude" as on the earlier Claude-badge card, in LIVE and in MOCK. Honesty stays in the mode
   pill right next to it: LIVE (green) only when Claude answered; MOCK (amber) + "scripted" (headerNote) on scripted answers, and the
   footer still starts "MOCK · scripted". No mode (no server answer yet): "Answer". */
function headerWord(mode) { return mode === 'LIVE' || mode === 'MOCK' ? 'Claude' : 'Answer'; }
function headerNote(mode) { return mode === 'MOCK' ? 'scripted, not a Claude answer' : ''; }
function drawAnswer(ctx, W, H, view) {
  const m = view.model || {}, pad = 40, v = m.visual || null, wait = view.wait || {}, heard = !!wait.heard, wsteps = (wait.steps || []).slice(-5);
  const HH = view.phase === 'thinking' ? waitHeight(ctx, W, H, m.question, wsteps.length) : H;
  const layout = {mark: Object.assign({}, MARK), indicator: null, picture: null, h: HH};
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = CARD_BG; rr(ctx, 4, 4, W - 8, HH - 8, 28); ctx.fill();
  ctx.strokeStyle = view.phase === 'error' ? '#e2725b' : 'rgba(226,232,240,.35)'; ctx.lineWidth = 3; ctx.stroke();
  // header: Claude-style mark + "Claude", mode; right: a speaker icon while it is read aloud, "B/Y closes", and the small "⋯"
  if (!view.markLayer) drawStarburst(ctx, MARK.x, MARK.y, MARK.r);
  const mode = view.modeLabel || (m.mode === 'live' ? 'LIVE' : m.mode === 'mock' ? 'MOCK' : ''), brand = headerWord(mode);
  ctx.font = '600 30px Arial'; ctx.fillStyle = '#f1f5f9'; ctx.fillText(brand, pad + 66, 60);
  let hx = pad + 66 + ctx.measureText(brand).width + 10;
  if (mode) { ctx.fillStyle = '#7f94a8'; ctx.fillText('·', hx, 60); hx += ctx.measureText('·').width + 10; }
  if (mode) hx += pill(ctx, hx, 33, mode, {h: 34, size: 21, weight: '700', fill: mode === 'LIVE' ? '#14532d' : '#6a4a10', color: mode === 'LIVE' ? '#86efac' : '#fcd34d'}) + 12;
  const note = headerNote(mode);
  if (note) { ctx.font = '500 20px Arial'; ctx.fillStyle = '#fcd34d'; ctx.fillText(note, hx, 58, Math.max(60, W * ANSWER_MORE.x0 - 150 - hx)); }
  const mx = W * ANSWER_MORE.x0 + (W - W * ANSWER_MORE.x0) / 2 - 6;
  drawMore(ctx, mx, 48, 30, !!view.hoverMore);
  let rx = mx - 46;
  if (view.speech === 'speaking') { drawSpeaker(ctx, rx - 30, 48, 30, '#fde68a'); rx -= 46; }
  if (view.phase === 'answer' || view.phase === 'error') { ctx.textAlign = 'right'; ctx.font = '500 21px Arial'; ctx.fillStyle = '#7f94a8'; ctx.fillText('B/Y closes', rx, 56); ctx.textAlign = 'left'; }
  let y = 96;
  if (view.phase === 'thinking' && m.question) {   // what was heard (voice) or asked (preset), small, at the top
    ctx.font = '600 20px Arial'; ctx.fillStyle = '#8aa2b8'; ctx.fillText(heard ? 'HEARD' : 'ASKED', pad, y + 14);
    ctx.font = 'italic 27px Arial'; ctx.fillStyle = '#cfe3f5'; for (const t of wrap(ctx, '“' + m.question + '”', W - 2 * pad, 2)) { ctx.fillText(t, pad, y + 50); y += 35; }
    y += 40; ctx.strokeStyle = 'rgba(226,232,240,.14)'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(W - pad, y); ctx.stroke(); y += 18;
  } else if (view.phase === 'error' || !v) {
    if (m.question) { ctx.font = 'italic 28px Arial'; ctx.fillStyle = '#a9c1d6'; for (const t of wrap(ctx, '“' + m.question + '”', W - 2 * pad, 2)) { ctx.fillText(t, pad, y + 20); y += 36; } y += 14; }
  }
  if (view.phase === 'thinking') {
    const steps = wsteps;
    ctx.fillStyle = steps.length ? '#8aa2b8' : '#e8f1f8';
    if (steps.length) { ctx.font = '600 20px Arial'; ctx.fillText(waitLabel({heard}).toUpperCase(), pad, y + 24); y += 44; }
    else { fit(ctx, waitLabel({heard}), pad, y + 44, W - 2 * pad, 38, '700'); y += 70; }
    for (const st of steps) {
      const cur = st.state === 'current', my = y + 32;
      if (cur) layout.indicator = {x: pad + 20, y: my}; else drawPicto(ctx, 'tick', pad + 20, my, 30, '#34d399');
      drawPicto(ctx, st.icon || 'twin', pad + 82, my, 42, cur ? '#ffffff' : '#9fb6cb');
      const t = (cur ? st.text : doneText(st.text)) + (st.n > 1 ? ' ×' + st.n : '');
      ctx.fillStyle = cur ? '#ffffff' : '#9fb6cb'; fit(ctx, t, pad + 124, my + (cur ? 11 : 10), W - 2 * pad - 130, cur ? 32 : 28, cur ? '700' : '500');
      y += 70;
    }
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
    if (drawn) layout.picture = {x: pad - 6, y: by - 6, w: W - 2 * pad + 12, h: (v.kind === 'text' ? 250 : bh) + 12};
    y = drawn ? by + (v.kind === 'text' ? 250 : bh) + 14 : y;
    // caption (the sentence answer, 1-2 lines)
    ctx.font = '27px Arial'; ctx.fillStyle = '#c3d3e2';
    for (const t of wrap(ctx, v.caption || '', W - 2 * pad, drawn ? 2 : 6)) { ctx.fillText(t, pad, y + 24); y += 34; }
    // bottom rows: check on site, then the evidence ids (with the verification count)
    const ry = H - 172;
    pill(ctx, pad, ry, '      ' + v.check, {h: 48, size: 26, fill: 'rgba(251,191,36,.16)', stroke: '#fbbf24', color: '#fde68a', weight: '700', maxW: W - 2 * pad});
    drawPicto(ctx, 'check', pad + 28, ry + 24, 28, '#fbbf24');
    let cx = pad; const ey = H - 106;
    const evl = 'EVIDENCE' + (m.verified ? ' ' + m.verified.n + '/' + m.verified.of + ' VERIFIED' : '');   // the verification count rides on the evidence row
    ctx.font = '600 21px Arial'; ctx.fillStyle = '#8aa2b8'; ctx.fillText(evl, cx, ey + 25); cx += ctx.measureText(evl).width + 14;
    for (const c of m.chips || []) {
      const col = !c.verified ? '#ef4444' : c.primary ? hex(COLORS.primary) : hex(COLORS.other);
      ctx.font = '600 22px Arial'; const t = '#' + c.id + ' ' + shortName(c).toLowerCase(), wNeed = Math.min(ctx.measureText(t).width + 26, 270); if (cx + wNeed > W - pad) break;
      const w = pill(ctx, cx, ey, t, {h: 36, size: 22, fill: 'rgba(255,255,255,.06)', stroke: col, color: c.verified ? '#f1f5f9' : '#fca5a5', maxW: 270});
      if (!c.verified) { ctx.strokeStyle = '#fca5a5'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(cx + 8, ey + 18); ctx.lineTo(cx + w - 8, ey + 18); ctx.stroke(); }
      cx += w + 8;
    }
  } else {
    // no visual model (older page): the text card as before
    ctx.font = '700 36px Arial'; ctx.fillStyle = '#ffffff';
    for (const t of wrap(ctx, m.lead || '', W - 2 * pad, 6)) { ctx.fillText(t, pad, y + 10); y += 46; }
    let cx = pad;
    for (const c of m.chips || []) { const w = pill(ctx, cx, H - 170, '#' + c.id + ' ' + c.label, {h: 40, size: 22, stroke: c.primary ? hex(COLORS.primary) : hex(COLORS.other), maxW: W - pad - cx}); cx += w + 10; if (cx > W - 200) break; }
  }
  // ONE small honesty line (mode + provenance); the stats line only when there are no evidence chips to carry it
  const f = (m.footer && m.footer.length ? m.footer : view.footer) || [];
  if (view.runNote && !(v && v.kind === 'trace') && view.phase === 'answer') { ctx.fillStyle = '#9fe7f5'; fit(ctx, view.runNote, pad, H - 52, W - 2 * pad, 21); }
  ctx.fillStyle = '#7f94a8';
  const foot = [f[0], m.stats && view.phase === 'answer' && !(v && (m.chips || []).length) ? m.stats : '', f[1]].filter(Boolean).join(' · ');
  if (foot) fit(ctx, foot, pad, HH - 20, W - 2 * pad, 21, '500');
  return layout;
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
    fit(ctx, b.label, x + w / 2, y + h * .5, w - 20, 36, '700');
    ctx.fillStyle = hov ? '#0b1020' : '#9fb6cb'; fit(ctx, b.sub || '', x + w / 2, y + h * .82, w - 20, 24, '500');
    ctx.textAlign = 'left';
  });
}
/* the small round "⋯" button */
function drawMore(ctx, cx, cy, r, hover = false) {
  ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fillStyle = hover ? '#FDB515' : 'rgba(255,255,255,.10)'; ctx.fill();
  ctx.lineWidth = hover ? 4 : 2.5; ctx.strokeStyle = hover ? '#ffffff' : 'rgba(226,232,240,.45)'; ctx.stroke();
  ctx.fillStyle = hover ? '#0b1020' : '#e2e8f0'; for (const dx of [-.42, 0, .42]) { ctx.beginPath(); ctx.arc(cx + dx * r, cy, r * .13, 0, Math.PI * 2); ctx.fill(); }
  ctx.restore();
}
/* The compact element label (chipModel). hover: the "⋯" is under a ray. Layout CHIP.W x CHIP.H. */
function drawChip(ctx, W, H, model, hover = false) {
  const m = model || {}, rec = m.hint && m.hint.tone === 'rec', col = sysColor(m.layer), mx = W * CHIP.moreX;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(10,16,24,.96)'; rr(ctx, 3, 3, W - 6, H - 6, 30); ctx.fill();
  ctx.strokeStyle = rec ? '#fb7185' : 'rgba(226,232,240,.35)'; ctx.lineWidth = rec ? 4 : 2.5; ctx.stroke();
  ctx.fillStyle = col; rr(ctx, 16, 24, 8, H - 48, 4); ctx.fill();
  drawPicto(ctx, m.picto || 'box', 66, 52, 46, col);
  ctx.fillStyle = '#ffffff'; fit(ctx, m.title || '', 104, 66, mx - 120, 40, '700');
  const h = m.hint || {text: ''};
  let hx = 40;
  if (rec) { ctx.beginPath(); ctx.arc(hx + 9, 106, 9, 0, Math.PI * 2); ctx.fillStyle = '#fb7185'; ctx.fill(); hx += 28; }
  ctx.fillStyle = rec ? '#fecdd3' : h.tone === 'hint' ? '#fde68a' : '#a9c1d6'; fit(ctx, h.text, hx, 116, mx - hx - 16, 31, '600');
  ctx.fillStyle = '#7f94a8'; fit(ctx, m.honesty || '', 40, 156, mx - 56, 22, '500');
  ctx.strokeStyle = 'rgba(226,232,240,.18)'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(mx, 26); ctx.lineTo(mx, H - 26); ctx.stroke();
  drawMore(ctx, mx + (W - mx) / 2 - 2, H / 2, 40, hover);
}

return {API, LEVELS, COLORS, BAR, CHIP, ANSWER_MORE, HONESTY, SYS, parseParams, createStream, sections, leadId, plainLine, cardModel, speakable, runPath, runGlow,
  barRects, barHit, barButtons, chipModel, chipHit, answerHit, micPlan, ttsPlan, wrap, drawMark, drawStarburst, starburstRays, CLAUDE_COLOR, CARD_BG, MARK, drawPicto,
  headerWord, headerNote, CLAUDE_MARK_PATH, waitHeight, STEP_ICON, stepIcon, stepPhrase, stepsAdd, stepsFrom, waitLabel, WAIT, markPose, dotWave, revealPose, waitPulse, drawAnswer, drawBar, drawChip, drawMore,
  pictogram, niceName, sizeText, roomChip, captionText, checkText, answerVisual,
  serverOrigin, privateIPv4, ENDPOINT, endpointFrom, connectCode, PAIR_KEY, loadPairing, savePairing, forgetPairing, connectPlan, connectLine,
  findLaptop, pairWithCode, autoConnect, forgetLaptop, apiUrl, healthProblem, accessCode, askHeaders, refusalText, progressText, EARCONS, HOLD_MS, holdAskAllowed, FILLER_MS};
});
