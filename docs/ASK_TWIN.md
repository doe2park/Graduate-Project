# Ask the twin — local AI demo

Click a BIM element in `grimes-bim-viewer.html`, ask a question (typed or push-to-talk), and get a diagnostic answer
card. The answer comes from Claude using **read-only tools** over the twin's own data, or from a scripted mock that uses
the same tools. Elements the answer cites are verified, highlighted and clickable (fly-to + select).

**Local only.** The server runs on the laptop (`127.0.0.1`); nothing is deployed, no data branch is touched, no GLB is
re-encoded. The viewer loads the panel only with `?ask=1`; without it the page behaves exactly as before.

## Run it

```bash
python3 scripts/ask_twin_server.py --mock   # no key needed: scripted, tool-grounded answers (badge: MOCK)
python3 scripts/ask_twin_server.py          # live Claude (badge: LIVE · claude-sonnet-5-5)
open http://127.0.0.1:8765/                 # redirects to grimes-bim-viewer.html?ask=1
```

Then: open **Layers** and load the layers you want to see (lighting, ductwork, fire piping…), click an element, and
ask, or press an example chip. Hold 🎙 to talk; tick *Speak answers* for a spoken reply.

### One-time setup (live mode and local speech-to-text)

```bash
python3 -m venv ~/.venvs/ask-twin
~/.venvs/ask-twin/bin/pip install anthropic faster-whisper
```

`scripts/ask_twin_server.py` re-runs itself inside `~/.venvs/ask-twin` when that venv exists, so the start command stays
the same. Mock mode needs only the system Python. The first voice request downloads the faster-whisper `base.en`
model (~145 MB) into the Hugging Face cache.

### API key (owner)

The key is read **only** from `ANTHROPIC_API_KEY`. Either export it in the shell that starts the server, or keep it in
a file **outside the repo** that the server loads at start:

```bash
mkdir -p ~/.config/ask-twin
printf 'ANTHROPIC_API_KEY=sk-ant-...\n' > ~/.config/ask-twin/env
chmod 600 ~/.config/ask-twin/env
```

The server refuses an env file inside the repository, never prints the key, and exits with a clear message (and the
`--mock` hint) when no key is set. `.gitignore` also lists `ask-twin.env` / `.env.ask-twin` in case a copy is made.

Options: `--model claude-opus-5-5` (default `claude-sonnet-5-5`), `--effort low|medium|high` (default `medium`),
`--port`, `--no-stt`, `--stt-model small.en`, `--no-fallbacks`, `--lan` (private-LAN HTTPS, see Quest below), `--verbose`.
If the API rejects an optional request feature (the refusal-fallback beta or eager tool streaming) with a 400, the
server retries that question once without them.

## How an answer is made

1. The browser sends the question, the selected element id and the clicked 3D point (viewer frame).
2. The server gives Claude the element summary plus seven read-only tools (`scripts/ask_twin/tools.py`):

| Tool | What it returns | Evidence kind |
|---|---|---|
| `get_element(id)` | sidecar record: identity, type, CAD layer/system, level, design parameters, box | design BIM |
| `elements_near(id or point, radius, above_only, layers, type_contains)` | nearest elements with above/below, vertical and horizontal gaps, service hint | geometry (+ inferred hint) |
| `room_of(id or point)` | level, room estimated from nearby labelled equipment, ceiling slice at that spot | inferred |
| `find_elements(text, layer, level, near, radius)` | word search over type/name/system/family/room | design BIM |
| `connected_run(id)` | touching-box run on the same layer; valves, terminal units, AHUs, heaters, drain pans on it | inferred |
| `list_sensors(near)` / `sensor_readings(id, hours)` | demo sensors, simulated series, alert rule | **demo-sim** |

3. Claude answers in a fixed card format (*Most likely source · confidence*, *Why*, *Check first*, *Other candidates*,
   *Limits*), citing elements as `[[id]]`.
4. **Citation check:** the server marks a cited id as verified only if it is the selected element or appeared in a tool
   result during that answer. Unverified ids are shown struck through and are never highlighted.
5. The viewer colours verified citations (most likely source magenta, others cyan), draws box outlines on top, loads
   small layers automatically (fire piping, 86 MB, loads when its chip is clicked) and flies to the most likely source.

The live loop uses the Anthropic Python SDK (`client.beta.messages.stream`) with streaming text, prompt caching on
the system prompt, adaptive thinking (model default), `output_config.effort`, the server-side refusal fallback
(`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`; disable with `--no-fallbacks`), and stops on
`refusal` / truncated tool calls. At most 8 model rounds per question.

## What the data supports — and what it does not

Verified from the repository data:

- **66,769 indexed elements**: all 66,620 element-layer identities (ten layers) plus 149 interior ceiling elements
  (Levels 1-3). Every sidecar element has a bounding box.
- **Boxes** come from the glTF `POSITION` accessor min/max in each GLB JSON chunk, transformed by the node hierarchy
  and the viewer placement `rotY(π) + EQUIP_OFFSET` (`scripts/ask_twin/index.py`). No Draco data is decoded or
  re-encoded. Check: equipment box bottoms sit at the Revit `elevation_m` (median difference −0.05 m). The index is
  cached in ignored `work/ask-twin/element-index.json` and rebuilt automatically (~5 s) when a GLB/sidecar changes.
- **Types, CAD layer codes, levels, design parameters** (marks, room `location` on 334 equipment elements, flow, size,
  fire fabrication attributes) from the sidecars.
- **Valves** exist as fabrication entities (e.g. 42 valves on Level 1, all on the hydronic layer; plumbing-layer valves
  are on the Lower level and Level 2).
- **17 demo sensors** (`twin/sensors/registry.json`), all `install_status: demo`, simulated by `tools/sensor_sim.py`.

Not in the data (the tools say so instead of guessing):

- **No pipe/duct connectivity, flow direction or valve-to-zone mapping.** `connected_run` follows touching boxes; it can
  join crossing runs and cannot tell upstream from downstream. "Which valve shuts off this room" can only return the
  nearest isolation valves (low confidence).
- **No room or space geometry.** Rooms are inferred from the nearest equipment that carries a room label.
- **Service (water vs drain vs air)** is inferred from manufacturer/family names (cast-iron no-hub → drain/waste, Type L
  copper/ProPress → pressurized water, Price SDV coil → reheat coil, fire layer → sprinkler). Whether the sprinkler
  system is wet or dry is not recorded.
- **Distances are box-to-box** (design model, not as-built, not surveyed). Directions are above/below/beside only:
  north is not verified in the viewer frame.
- **Sensor values are simulated.** No sensor is installed in Grimes.
- Interior ceilings are indexed (so "what is above this ceiling spot" works) but the element viewer does not draw them.

## Example questions that answer well

Use the recessed light `#12442` on Level 1 (under the demo leak pipe; reach it with Layers → Lighting, then click), or
the spiral duct `#401233` (demo airflow sensor anchor).

- *"There's a water stain on the ceiling tile here. What runs above it and what could be leaking?"* → fire sprinkler
  pipe `#278123` about 1.1 m above, with the simulated DTS temperature alert; other candidates are nearby sprinkler
  fittings; room inferred as MECHANICAL 101.
- *"Which valve shuts off water to this room?"* → nearest Level 1 isolation (ball) valve, flagged as hydronic, not
  domestic water; low confidence; check the drawings.
- *"What feeds this duct?"* → reheat-coil terminal units a few touching segments away; low confidence.
- *"What is this and what is around it?"* → identity and nearby elements.

## Voice (Milestone B)

- **Push-to-talk:** hold 🎙 → browser `MediaRecorder` (webm/opus) → `POST /api/transcribe` → local
  **faster-whisper** `base.en` (CPU, int8; ~0.6 s for a short question on this Mac) → the question is asked.
  If the server has no speech-to-text, the browser falls back to Web Speech recognition (Chrome/Safari desktop).
- **Spoken reply:** *Speak answers* reads the card with `speechSynthesis` (ids replaced by element types, the
  *Limits* line skipped).

## Quest 3 (stretch, not verified on a headset)

`python3 scripts/ask_twin_server.py --lan` serves HTTPS on the Mac's **private** LAN address only (never `0.0.0.0`),
reusing the self-signed development certificate logic of `scripts/serve_quest_https.py` (key under ignored
`work/quest-https/`). On the Quest Browser open the printed `https://<lan-ip>:8765/` and accept the certificate warning
for that address only. HTTPS gives the page a secure context, so push-to-talk records with `MediaRecorder` and is
transcribed on the laptop (Quest Browser has no Web Speech recognition); answers can be spoken with `speechSynthesis`.
Verified on the Mac only (HTTPS health check on the LAN address, localhost refused in that mode). This is the 2D
desktop viewer page with the panel inside the Quest browser, **not** the immersive MR page: wiring the panel into
`scan-xr.html` (controller ray pick → ask → world-space card) is not done.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_ask_twin      # index, tools, citations, mock, live loop (fake client), server
python3 scripts/ask_twin_server.py --mock &                             # then the headless browser check:
PLAYWRIGHT_MODULE=/path/to/playwright-core CHROME_EXECUTABLE=/path/to/chrome-headless-shell \
  [FAKE_AUDIO=/abs/question.wav] node tests/ask-twin-smoke.cjs          # screenshots -> work/ask-twin/shots/
```

The headless check loads three element layers under software WebGL and takes about 2-4 minutes of full CPU.

## Files

- `scripts/ask_twin_server.py` — server (static read-only + `/api/health`, `/api/ask` SSE, `/api/transcribe`)
- `scripts/ask_twin/index.py` — element box index; `tools.py` — read-only tools + schemas; `agent.py` — live and mock loops
- `twin/ask-twin.js` — panel, citation chips, highlights, fly-to, push-to-talk, spoken reply
- `grimes-bim-viewer.html` — small `?ask=1` hook (`window.twinViewerApi`, pick context); inert without `?ask=1`
- `tests/test_ask_twin.py`, `tests/ask-twin-smoke.cjs`
