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
`--port`, `--no-stt`, `--stt-model small.en`, `--no-tts` (no laptop voice for `/api/speak`), `--no-fallbacks`, `--lan` (private-LAN HTTPS, see Headset below), `--verbose`.
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
- Audio is decoded on the server with PyAV into 16 kHz mono before faster-whisper (`decode_16k`): faster-whisper 1.2.1's own
  decoder passes an argument PyAV 19 no longer accepts (`TypeError … metadata_errors`, found 2026-11-03), which made every
  `/api/transcribe` fail with 500.
- **Laptop voice:** `POST /api/speak {text}` returns a WAV from macOS `say` with an English voice (Samantha if installed;
  the default voice follows the system language). Used by the headset page when the browser has no voice.

## Headset (WebXR) on Quest 3

**Status: built and checked on the Mac only. Not tested on a headset.** The four question levels work inside the immersive
MR/VR page (`scan-xr.html`, the page behind `/mr`) in mock mode; nothing below is verified on Quest hardware.

`/mr` is a redirect to `scan-xr.html?mode=ar&place=demo&sensors=demo` and passes extra parameters through, so
`/mr/?ask=1` opens the MR page with the ask feature. `scan-xr.html` is a different page from the element viewer
(`grimes-bim-viewer.html`); both talk to the same local server. Without `?ask=1` the MR/VR page is unchanged.

### What you do in the headset

1. Trigger on a service element (duct, pipe, light…) or on a demo-sensor pin: the usual info card appears, plus an
   **ask bar** under it: `1 · What is this?` (look up), `2 · What's above?` (nearby in 3D), `3 · What feeds it?`
   (trace a system), `4 · Why is it warm?` (reason across sources), **Hold to speak**, **Close**.
2. Trigger on a level button, or hold the trigger on *Hold to speak*, say the question, release.
3. The answer comes back as a world-locked card just under the element: Claude badge, LIVE/MOCK, the short lead,
   two evidence lines, the first *check first* line, the cited ids (verified ones bordered; unverified struck through) and
   the provenance footer (*design BIM · inferred geometry and rooms · demo sensors SIMULATED · not headset-verified*).
4. Verified cited elements glow (most likely source magenta, others cyan): render-only copies of the element's own
   batch vertices, drawn on top; a box outline when the element is not drawn (layer not loaded, other level). When the
   answer used `connected_run` (levels 3 and 4), the run lights up piece by piece from the cited terminal unit to the
   picked element, then a pulse travels along it. The card says the run is inferred from touching geometry and that the
   model has no flow direction.
5. The answer is read aloud: the browser voice if `speechSynthesis` has a voice (2.5 s start watchdog), else the laptop's
   macOS voice (`POST /api/speak` → WAV played with Web Audio), else the card says *text only*.

The mock answers for the four levels are scripted from real tool runs (`MockAgent._lookup`, `_above`, `_feed`,
`_comfort` in `scripts/ask_twin/agent.py`). With a key the same page gets live Claude answers.

### Try it on the Quest (owner steps)

1. Mac and Quest on the **same Wi-Fi** (a home or lab network; guest/campus Wi-Fi with client isolation blocks it).
2. On the Mac:
   ```bash
   cd ~/Graduate-Project-asktwin            # the feat/ask-twin-ai worktree
   python3 scripts/ask_twin_server.py --mock --lan
   ```
   It prints `headset (WebXR MR + ask): https://<lan-ip>:8765/mr/?ask=1`. (Live answers: drop `--mock` once
   `~/.config/ask-twin/env` holds the key.)
3. In Quest Browser type that address. A certificate warning appears (self-signed development certificate, made by
   `scripts/serve_quest_https.py`, kept in the ignored `work/quest-https/`): **Advanced → Proceed**, for this address only.
   No certificate is installed anywhere and no system setting changes.
4. Wait for *Services ready*. In the **Ask the twin** box (top right): press **Allow mic** (allow the microphone
   prompt), then **Test voice** (you should hear "Ask the twin is ready"; this also unlocks sound).
5. Press **Enter MR**. *Demo anywhere* is the default: point at the floor, trigger, the Grimes services appear at
   real scale (DEMO, not aligned). Trigger on a duct or diffuser overhead → the ask bar → press `3` (or hold *Hold to speak*).
6. Ctrl+C on the Mac stops the server.

Why HTTPS: WebXR and the microphone need a secure context; a LAN IP over plain http is not one. Alternative without a
certificate warning (not tried here): USB + Quest developer mode + `adb reverse tcp:8765 tcp:8765`, then
`http://localhost:8765/mr/?ask=1` in Quest Browser (localhost counts as secure). The owner would install `adb` and enable
developer mode; this was not done for the prototype.

### Risky parts on the Quest (unverified)

| Part | Expectation | Fallback built in |
|---|---|---|
| Microphone inside an immersive session | The permission prompt is a 2D dialog that cannot show in VR/MR, so the mic is opened on the 2D page **before** Enter MR and kept open; recording itself (`MediaRecorder`) during the session is expected to work but is not verified. | If no stream: one in-session `getUserMedia` try, then *voice off: use 1-4*; the preset buttons never need the mic. |
| Text-to-speech | Quest Browser may have no `speechSynthesis` voice. | Laptop voice over the LAN (`/api/speak`, macOS `say`, local), then *text only* on the card. |
| Audio autoplay in XR | Web Audio is unlocked by the 2D click (Test voice / Enter MR). | The card still shows the answer. |
| HTTPS | Works with the self-signed certificate after *Proceed* (the same path `scripts/serve_quest_https.py` documents for the MR page). | `adb reverse` + localhost (owner). |
| Latency | Mac, mock: 1.4–2.2 s from press to the full card (smoke run). Live Claude: several seconds to tens of seconds (tool rounds); whisper `base.en` ≈ 0.6 s on this Mac; `say` ≈ 0.5–3 s. The card shows the tool steps while waiting. | — |
| Frame rate | Card redraws are throttled (≤ 8/s); the glow is ≤ ~80 small meshes. Not measured on the headset. | — |

### Desktop check (Mac only)

```bash
python3 scripts/ask_twin_server.py --mock --port 8766 &
PLAYWRIGHT_MODULE=/path/to/playwright-core node tests/xr-ask-smoke.cjs http://127.0.0.1:8766   # shots -> work/ask-twin/xr-shots/
```

The smoke opens the MR page in its **desktop simulation** (no immersive session; Chrome with the GPU, ductwork only,
photo backdrop refused so the shots carry no capture photos), picks diffuser `#388279` through the page's real ray path,
presses button 3 through the same panel hit test a controller ray uses, asks levels 4 and 2, and checks the glow, the lit
run, verified citations, speech plan and *Close*. The immersive emulator smoke (`tests/scan-xr-immersive-smoke.cjs`,
IWER) was not run for this feature.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_ask_twin      # index, tools, citations, mock (4 levels), live loop (fake client), server
node --test tests/xr-ask.test.cjs                                       # headset helpers: stream, card model, speech text, run path, bar hit, drawing
python3 scripts/ask_twin_server.py --mock &                             # then the headless browser check:
PLAYWRIGHT_MODULE=/path/to/playwright-core CHROME_EXECUTABLE=/path/to/chrome-headless-shell \
  [FAKE_AUDIO=/abs/question.wav] node tests/ask-twin-smoke.cjs          # screenshots -> work/ask-twin/shots/
```

The headless check loads three element layers under software WebGL and takes about 2-4 minutes of full CPU.

## Files

- `scripts/ask_twin_server.py` — server (static read-only + `/api/health`, `/api/ask` SSE, `/api/transcribe`, `/api/speak`)
- `scripts/ask_twin/index.py` — element box index; `tools.py` — read-only tools + schemas; `agent.py` — live and mock loops
- `twin/ask-twin.js` — panel, citation chips, highlights, fly-to, push-to-talk, spoken reply
- `twin/xr-ask.js` — headset helpers and canvas drawing (ask bar, answer card, Claude badge); `scan-xr.html` `?ask=1` block wires it into the XR page
- `tests/xr-ask.test.cjs`, `tests/xr-ask-smoke.cjs` — headset helper tests and the desktop-simulation smoke
- `grimes-bim-viewer.html` — small `?ask=1` hook (`window.twinViewerApi`, pick context); inert without `?ask=1`
- `tests/test_ask_twin.py`, `tests/ask-twin-smoke.cjs`
