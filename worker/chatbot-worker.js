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

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const MODEL = '@cf/meta/llama-3.1-8b-instruct';

// Valid building ids the LLM may emit in action markers.
// Keep in sync with D[] in grimes-campus-map-arcgis.html.
const BUILDING_IDS = [
  'grimes', 'davis', 'cory', 'soda', 'etch', 'hmm', 'hesse', 'jacobs',
  'sutardja', 'mclaughlin', 'stanley', 'tan', 'latimer', 'evans', 'birge',
  'hilde', 'wheeler', 'dwinelle', 'moses', 'south', 'barrows', 'stephens',
  'wurster', 'giannini', 'california', 'mlk', 'rsf', 'chavez', 'sproul',
  'doe', 'moffitt', 'uhall', 'zeller', 'donner', 'mulford', 'northgate',
  'haas', 'morgan', 'bww', 'lksc', 'vlsb',
];
const CATEGORIES = [
  'Engineering', 'Science', 'Humanities', 'Professional',
  'Libraries', 'Student Life', 'Other',
];

function buildSystemPrompt(context, lang) {
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

MAP ACTION MARKERS:
When the user asks you to do something on the map, emit ONE of these markers on its OWN line at the very end of your reply:
  <<ZOOM:{building_id}>>     — fly map to a single building (also use when user says "show me X", "where is X", "take me to X")
  <<FILTER:{Category}>>      — filter markers by category ("show only Engineering", "hide other categories")
  <<RESET>>                  — restore full view ("reset map", "show everything", "clear filter")
  <<TREND:{building_id}>>    — render the 24h trend inline ("how has X been doing", "X trend")

You may emit MULTIPLE markers if the user asks for multiple things (e.g. "compare Davis and Wheeler on the map" → two <<ZOOM:…>>).

Valid building_id values: ${BUILDING_IDS.join(', ')}
Valid Category values: ${CATEGORIES.join(', ')}
(If the user names a building, use the id above, not the full name.)

LIVE CONTEXT (fresh at time of question):
${context || '(context not provided)'}

When a user question is open-ended ("how does campus compare to last year", "what's interesting about Grimes"), answer from the context plus your general knowledge, staying factual and citing the source line.

When a user question is about a building not in the id list, say so briefly.

Do NOT invent numbers. If the context doesn't have it, say you don't have that data yet.`;
}

// Parse <<ACTION:arg>> markers from an LLM reply. Returns { actions, clean }.
function parseActions(text) {
  const actions = [];
  const re = /<<\s*(ZOOM|FILTER|RESET|TREND)\s*(?::\s*([^>]+?))?\s*>>/gi;
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

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', ...CORS },
  });
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    if (request.method !== 'POST') return new Response('POST only', { status: 405, headers: CORS });

    let body;
    try { body = await request.json(); }
    catch (e) { return json({ error: 'Invalid JSON' }, 400); }

    const question = (body.question || '').toString().slice(0, 2000);
    if (!question) return json({ error: 'question required' }, 400);

    const history = Array.isArray(body.history) ? body.history.slice(-8) : [];
    const context = (body.context || '').toString().slice(0, 6000);
    const lang = /[\uAC00-\uD7AF]/.test(question) ? 'ko' : (body.lang || 'en');

    const t0 = Date.now();

    // Build messages: system + last history turns + user question
    const messages = [
      { role: 'system', content: buildSystemPrompt(context, lang) },
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
      }, 200);
    }

    const { actions, clean } = parseActions(reply);

    // Validate actions against whitelists
    const safeActions = actions.filter(a => {
      if (a.type === 'reset') return true;
      if (a.type === 'filter') return CATEGORIES.includes(a.arg);
      if (a.type === 'zoom' || a.type === 'trend') return BUILDING_IDS.includes(a.arg);
      return false;
    });

    return json({
      answer: clean || '<div class="tb-kicker">No reply</div><div class="tb-body">The model did not return text. Please rephrase.</div>',
      actions: safeActions,
      model: MODEL,
      latency_ms: Date.now() - t0,
    });
  },
};
