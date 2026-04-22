# Campus Chatbot Worker (Phase 2)

Cloudflare Worker that powers the Berkeley Campus Digital Twin chatbot. It proxies questions to Workers AI (Llama 3.1 8B Instruct) with a structured system prompt that produces museum-label tone answers and optional map-action markers the client can dispatch.

## What changed vs Phase 1

**Phase 1** (deployed worker, simple proxy): took `{question, context}`, returned a text reply. No memory, no action dispatch, no tone constraints.

**Phase 2** (this file): takes `{question, history, context, lang}`, returns `{answer, actions[], model, latency_ms}`. The LLM can emit action markers (`<<ZOOM:id>>`, `<<FILTER:Category>>`, `<<RESET>>`, `<<TREND:id>>`) that the worker parses, validates against whitelists, and returns to the client as a structured `actions` array. The client executes them against `window.campusMap`. The system prompt enforces a grounded, emoji-free museum-label tone.

## Deploy

From the repo root:

```
cd worker
wrangler deploy
```

This deploys as the existing name `campus-chatbot` so the live map picks up the new brain with no client config change. Verify with:

```
curl -X POST https://campus-chatbot.ucb-dt.workers.dev \
  -H 'content-type: application/json' \
  -d '{"question":"show only Engineering"}'
```

Expected shape:

```json
{
  "answer": "<div class=\"tb-kicker\">Filter</div>...",
  "actions": [{ "type": "filter", "arg": "Engineering" }],
  "model": "@cf/meta/llama-3.1-8b-instruct",
  "latency_ms": 480
}
```

## Tool vocabulary

- `ZOOM:{id}` — fly map to a single building. `id` must be one of `grimes, davis, cory, soda, etch, hmm, hesse, jacobs, sutardja, mclaughlin, stanley, tan, latimer, evans, birge, hilde, wheeler, dwinelle, moses, south, barrows, stephens, wurster, giannini, california, mlk, rsf, chavez, sproul, doe, moffitt, uhall, zeller, donner, mulford, northgate, haas, morgan, bww, lksc, vlsb`.
- `FILTER:{Category}` — filter markers. `Category` must be one of `Engineering, Science, Humanities, Professional, Libraries, Student Life, Other`.
- `RESET` — clear filters, recenter map.
- `TREND:{id}` — render 24h sparkline inline in the answer.

Invalid markers are silently dropped by the worker before reply returns.

## Multi-turn memory

The client sends the last 6–8 message pairs in `history`. The worker clips each to 1200 chars and caps total history at 8 entries to keep Llama prompts small.

## Language detection

If the incoming question contains Korean (Hangul) characters, the system prompt switches to Korean mode. Otherwise it uses `body.lang` or defaults to English.
