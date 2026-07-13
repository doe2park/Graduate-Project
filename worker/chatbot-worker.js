/**
 * Campus Chatbot Worker — Phase 2
 *
 * Cloudflare Worker that proxies questions to Workers AI (Llama 3.1 8B Instruct)
 * and returns structured responses the client can use to drive the map.
 *
 * Deploy:
 *   wrangler deploy worker/chatbot-worker.js --name campus-chatbot
 *
 * Request (POST JSON):
 *   { question: string,                // user's latest message
 *     history?: [{role, content}, …],  // optional last N turns
 *     context?: string,                // client-provided live data blob
 *     lang?: "en" | "ko" }             // language hint (answer in same)
 *
 * Response (JSON):
 *   { answer: "<html string>",         // museum-label HTML for chat bubble
 *     actions: [{type, arg}, …],       // parsed from <<…>> markers
 *     model: "llama-3.1-8b-instruct",
 *     latency_ms: 123 }
 *
 * Action markers the LLM may emit (one per line, at the very end of the reply):
 *   <<ZOOM:building_id>>     — fly map to a building
 *   <<FILTER:Category>>      — filter markers by category
 *   <<RESET>>                — reset view
 *   <<TREND:building_id>>    — ask client to render 24h sparkline for a building
 *
 * The worker strips markers from the visible answer before returning.
 */

// Only the GitHub Pages site (and local dev) may call this worker.
const ALLOWED_ORIGINS = [
  'https://doe2park.github.io',
  'http://localhost:8000',
  'http://127.0.0.1:8000',
];

function corsHeaders(request) {
  const origin = request.headers.get('Origin') || '';
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Vary': 'Origin',
  };
}

function originAllowed(request) {
  const origin = request.headers.get('Origin');
  // Non-browser calls (no Origin header) are rejected — default: reject.
  return origin !== null && ALLOWED_ORIGINS.includes(origin);
}

const MODEL = '@cf/meta/llama-3.1-8b-instruct';

// Valid building ids the LLM may emit in action markers.
// SINGLE SOURCE: data/building_ids.json on GitHub Pages (derived from D[] in
// grimes-campus-map-arcgis.html). Fetched lazily + cached 1h; falls back to
// the embedded snapshot below if the fetch fails.
const BUILDING_IDS_URL = 'https://doe2park.github.io/Graduate-Project/data/building_ids.json';
const BUILDING_IDS_FALLBACK = [
  'grimes',
  'cory',
  'soda',
  'davis',
  'etch',
  'hmm',
  'hesse',
  'obrien',
  'jacobs',
  'sutardja',
  'mclaughlin',
  'blum',
  'stanley',
  'tan',
  'latimer',
  'lewis',
  'pimentel',
  'evans',
  'campbell',
  'birge',
  'leconte',
  'vlsb',
  'lksc',
  'hilde',
  'wheeler',
  'dwinelle',
  'moses',
  'durant',
  'south',
  'barrows',
  'stephens',
  'haas',
  'boalt',
  'wurster',
  'kroeber',
  'tolman',
  'morgan',
  'giannini',
  'california',
  'mlk',
  'rsf',
  'chavez',
  'anthony',
  'unit1',
  'unit2',
  'unit3',
  'stadium',
  'doe',
  'moffitt',
  'stacks',
  'bancroft',
  'music',
  'campanile',
  'sproul',
  'uhall',
  'sgate',
  'zeller',
  'donner',
  'mulford',
  'northgate',
  'bww'
];
let _bidCache = { ids: null, exp: 0 };
async function getBuildingIds() {
  const now = Date.now();
  if (_bidCache.ids && now < _bidCache.exp) return _bidCache.ids;
  try {
    const r = await fetch(BUILDING_IDS_URL, { cf: { cacheTtl: 3600 } });
    if (r.ok) {
      const j = await r.json();
      if (Array.isArray(j.building_ids) && j.building_ids.length) {
        _bidCache = { ids: j.building_ids, exp: now + 3600 * 1000 };
        return _bidCache.ids;
      }
    }
  } catch (e) { /* fall through */ }
  return BUILDING_IDS_FALLBACK;
}
const CATEGORIES = [
  'Engineering', 'Science', 'Humanities', 'Professional',
  'Libraries', 'Student Life', 'Other',
];

function buildSystemPrompt(context, lang, buildingIds) {
  const langLine = lang === 'ko'
    ? 'Reply in natural Korean (한국어로 답변).'
    : 'Reply in natural English.';

  return `You are the UC Berkeley Campus Digital Twin assistant.
You answer questions about campus buildings, live energy use, cost, CO₂, and the Grimes Engineering Center BIM-based digital twin.

${langLine}

STYLE RULES (important):
- Museum-label tone: a 1-line kicker (UPPERCASE SMALL), then the answer. Short, grounded, no hype.
- Use compact HTML: <b> for key numbers, <ul><li> or simple rows for lists, <i> for examples.
- NEVER use emojis. NEVER use phrases like "Great question!", "I'd love to help!", "As an AI".
- Always end with a tiny source line: "Source: BMO · live" or a similar single short line.
- Keep replies under 6 short lines whenever possible.

MAP ACTION MARKERS (VERY IMPORTANT — exact format):
When the user asks you to do something on the map, emit ONE marker on its OWN line at the very end of your reply. The format is EXACTLY two angle brackets on each side:

  <<ZOOM:grimes>>
  <<FILTER:Engineering>>
  <<RESET>>
  <<TREND:davis>>

Common mistakes to avoid:
  × <FILTER:Engineering>>   (only one bracket on left — WRONG)
  × <<FILTER:Engineering>   (only one bracket on right — WRONG)
  × <<FILTER: Engineering>> (leading space inside the arg — WRONG)
  × <<filter:engineering>>  (lowercase — WRONG)

You may emit MULTIPLE markers if the user asks for multiple things — one per line (e.g. "compare Davis and Wheeler on the map" → "<<ZOOM:davis>>" newline "<<ZOOM:wheeler>>").

Valid building_id values (use EXACTLY these, never the pretty name): ${buildingIds.join(', ')}
Valid Category values (use EXACTLY these, case-sensitive): ${CATEGORIES.join(', ')}

GROUNDING RULES:
- NEVER invent buildings that are not in the BUILDING REGISTRY below.
- When asked "which buildings are in category X", filter the registry by category column, do not guess from the name.
- When asked for numbers (kW, $, CO₂), only use numbers present in the LIVE CONTEXT. If missing, say "I don't have that reading yet".

LIVE CONTEXT (fresh at time of question):
${context || '(context not provided)'}

When a user question is open-ended ("how does campus compare to last year", "what's interesting about Grimes"), answer from the context plus your general knowledge, staying factual and citing the source line.

When a user question is about a building not in the id list, say so briefly.

Do NOT invent numbers. If the context doesn't have it, say you don't have that data yet.`;
}

// Parse <<ACTION:arg>> markers from an LLM reply. Returns { actions, clean }.
// Tolerant of Llama 8B dropping one bracket on either side (e.g. "<FILTER:X>>").
function parseActions(text) {
  const actions = [];
  const re = /<{1,2}\s*(ZOOM|FILTER|RESET|TREND)\s*(?::\s*([^<>\n]+?))?\s*>{1,2}/gi;
  const clean = (text || '').replace(re, (_m, kind, arg) => {
    const type = kind.toUpperCase();
    const value = (arg || '').trim();
    if (type === 'RESET') actions.push({ type: 'reset' });
    else if (type === 'ZOOM' && value) actions.push({ type: 'zoom', arg: value });
    else if (type === 'FILTER' && value) actions.push({ type: 'filter', arg: value });
    else if (type === 'TREND' && value) actions.push({ type: 'trend', arg: value });
    return '';
  }).trim();
  return { actions, clean };
}

function json(data, status = 200, cors = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', ...cors },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const cors = corsHeaders(request);

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });

    // (The /aps-token endpoint was removed 2026-07 — the BIM viewer is now
    //  self-hosted Three.js + GLB with no Autodesk dependency.)

    if (request.method !== 'POST') return new Response('POST only', { status: 405, headers: cors });
    if (!originAllowed(request)) return json({ error: 'origin not allowed' }, 403, cors);

    let body;
    try { body = await request.json(); }
    catch (e) { return json({ error: 'Invalid JSON' }, 400, cors); }

    const question = (body.question || '').toString().slice(0, 2000);
    if (!question) return json({ error: 'question required' }, 400, cors);

    const history = Array.isArray(body.history) ? body.history.slice(-8) : [];
    const context = (body.context || '').toString().slice(0, 6000);
    const lang = /[\uAC00-\uD7AF]/.test(question) ? 'ko' : (body.lang || 'en');

    const t0 = Date.now();
    const buildingIds = await getBuildingIds();

    // Build messages: system + last history turns + user question
    const messages = [
      { role: 'system', content: buildSystemPrompt(context, lang, buildingIds) },
    ];
    for (const h of history) {
      if (!h || !h.role || !h.content) continue;
      if (h.role !== 'user' && h.role !== 'assistant') continue;
      messages.push({ role: h.role, content: String(h.content).slice(0, 1200) });
    }
    messages.push({ role: 'user', content: question });

    let reply = '';
    try {
      const out = await env.AI.run(MODEL, { messages, max_tokens: 512 });
      reply = (out && (out.response || out.result || '')) + '';
    } catch (e) {
      return json({
        answer: '<div class="tb-kicker">Error</div><div class="tb-title">Brain unreachable</div><div class="tb-body">The AI service timed out. I fell back to a simple answer — try a specific building name.</div>',
        actions: [],
        error: String(e).slice(0, 200),
      }, 200, cors);
    }

    const { actions, clean } = parseActions(reply);

    // Validate actions against whitelists
    const safeActions = actions.filter(a => {
      if (a.type === 'reset') return true;
      if (a.type === 'filter') return CATEGORIES.includes(a.arg);
      if (a.type === 'zoom' || a.type === 'trend') return buildingIds.includes(a.arg);
      return false;
    });

    return json({
      answer: clean || '<div class="tb-kicker">No reply</div><div class="tb-body">The model did not return text. Please rephrase.</div>',
      actions: safeActions,
      model: MODEL,
      latency_ms: Date.now() - t0,
    }, 200, cors);
  },
};
