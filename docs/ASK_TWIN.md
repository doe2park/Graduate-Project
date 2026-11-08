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
# open the "laptop page" link it prints: http://127.0.0.1:8765/grimes-bim-viewer.html?ask=1&code=<CODE>
```

The server prints a short **access code** at start, and its links already include it (see *Limits and access code* below).

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
`--port`, `--no-stt`, `--stt-model small.en`, `--stt-beam 1` (default 5), `--no-tts` (no laptop voice for `/api/speak`),
`--voice "Zoe (Premium)"` (default: best installed English voice), `--no-fallbacks`, `--lan` (private-LAN HTTPS, see Headset
below), `--auto` (live Claude when a key is found, else scripted answers with the note *Live AI needs a key on the laptop;
running scripted answers* on the 2D page and the answer card), `--verbose`. Limits and access: `--code`, `--no-code`, `--per-minute`,
`--per-day`, `--daily-tokens`, `--max-tokens`, `--idle-minutes`, `--usage-dir` (next section).

### Switching the running headset server to live answers (owner)

1. Put the key in `~/.config/ask-twin/env` (see above; `chmod 600`).
2. Stop the running server (Ctrl+C, or `pkill -f "ask_twin_server.py --mock --lan"`), then start it without `--mock`:
   `python3 scripts/ask_twin_server.py --lan` (or `--auto --lan`, which falls back to scripted answers if the key is missing).
3. Reload the page in the headset. The 2D box shows `LIVE · claude-sonnet-5-5` and the key note disappears.

Expected latency (live, not measured here: no key on this Mac): the card says *Thinking…* within ~0.1 s, the first tool
step after ~1-3 s, the spoken lead ~4-10 s after the question (2-4 tool rounds), the full card ~6-15 s. *One moment.* is
spoken when nothing has been said 1.5 s after the question. Speech-to-text adds ~0.4 s (base.en, beam 5, measured on
this Mac with synthetic speech).
If the API rejects an optional request feature (the refusal-fallback beta or eager tool streaming) with a 400, the
server retries that question once without them.

## Limits and access code

Sensible defaults for demos: people can try it, strangers on the same Wi-Fi cannot, and a day's spending has a ceiling.

| What | Default | Flag |
|---|---|---|
| Access code (random 6 characters, no 0/O/1/I/L, case-insensitive) on `/api/ask`, `/api/transcribe`, `/api/speak` | a new code every start | `--code K7PX3M` (fixed), `--no-code` (localhost only; refused with `--lan`) |
| Questions per minute, per client IP | 10 | `--per-minute N` (0 = off) |
| Questions per day, whole server | 300 | `--per-day N` (0 = off) |
| Daily token budget (live only) | 2,000,000 | `--daily-tokens N` (0 = off) |
| `max_tokens` per model round (rounds per answer stay at 8) | 4000 | `--max-tokens N` |
| Stop after no questions for | 120 min | `--idle-minutes N` (0 = never) |
| Usage counter folder (outside the repo) | `~/.config/ask-twin/` | `--usage-dir DIR` |

- **Code.** The page links printed at start carry `&code=…`; the laptop page and the headset page read it from their URL and send it
  as the `X-Ask-Code` header (`?code=` on the API also works, for curl). Without it the page says *Access code needed*, with a wrong one
  *Wrong access code*. On the laptop page you can also type it into the box that appears. Wrong codes are limited to 10 a minute per IP.
  `/api/health` stays open but shows only flags and numbers (never the code).
- **Rate limits** answer `429` with a short sentence and `Retry-After`; the voice endpoints have their own limit (30/min per IP).
- **Budget.** Every API response's usage is added to `~/.config/ask-twin/usage-YYYY-MM-DD.json` (local date; a restart keeps it, a new
  day starts at zero): budget tokens = `input_tokens` + `cache_creation_input_tokens` + `output_tokens` + `cache_read_input_tokens` / 10
  (cache reads are billed at about a tenth of the input price). Once today's count reaches the budget, `/api/ask` answers *Daily budget
  reached* without calling the API, and a running answer stops before its next model round. The banner and `/api/health` show today's numbers.
- **Prompt caching.** The tool definitions and the system prompt are cached (`cache_control: ephemeral` on the last tool and on the
  system prompt), and a rolling breakpoint on the newest turn lets each model round reuse the earlier rounds of the same answer.
- **Mock mode** goes through the same code and rate-limit checks; its counter stays in memory and its budget stays at 0.

Start commands (the owner copies the printed links; nothing else to configure):

```bash
python3 scripts/ask_twin_server.py --lan                      # live, Quest on the same Wi-Fi: random code, default limits
python3 scripts/ask_twin_server.py --lan --code K7PX3M        # same code every time (e.g. printed on a demo card)
python3 scripts/ask_twin_server.py --mock --lan               # try the whole flow without a key
python3 scripts/ask_twin_server.py --no-code                  # laptop only, no code
python3 scripts/ask_twin_server.py --lan --per-minute 20 --daily-tokens 5000000 --idle-minutes 240   # a long, busy demo
```

The start banner looks like this (example addresses):

```
[ask-twin] access code: K7PX3M   (the links below include it; people without it get "Access code needed")
[ask-twin] laptop page:  https://192.168.68.52:8765/grimes-bim-viewer.html?ask=1&code=K7PX3M   (Ctrl+C to stop)
[ask-twin] headset page: https://192.168.68.52:8765/mr/?ask=1&code=K7PX3M
[ask-twin] public page + this laptop (Method A): https://doe2park.github.io/Graduate-Project/mr/?ask=1&server=https://192.168.68.52:8765&code=K7PX3M
[ask-twin] limits: 10 questions/min per client · 300 questions/day · budget 2000000 tokens/day · max_tokens 4000/round
[ask-twin] today (2026-11-07): 0 questions · 0 budget tokens (input 0, output 0, cache read 0, cache write 0)
[ask-twin] stops after 120 min without a question (first check: 19:18; --idle-minutes 0 keeps it running)
```

There is no terminal QR code (that would need a new dependency).

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

3. Claude answers for non-experts (live format since Nov 7, 2026): **one plain-English paragraph of 2-3 short sentences**
   (the first sentence answers directly, e.g. *"This is a supply air vent (diffuser) in the ceiling."*; plain words first,
   a technical term in parentheses at most once; no markdown, ids, CAD codes or *confidence:* labels; uncertainty in plain
   words such as *probably* or *check on site*), then one line `Evidence: [[id]] [[id]] …` with the main element first.
   The server tidies slips (`agent.tidy_answer`: markdown, an *Answer:* label, ids or CAD codes in the sentence are moved
   or removed) and keeps only the last model round's text, so a *Let me check…* preamble never reaches the card. The
   laptop card shows the paragraph and an **Evidence** row of chips with plain labels (*diffuser*, *VAV box*); the spoken
   reply is the same paragraph with units spelled out. Mock answers keep the older card format (*Answer / Most likely
   source*, *Why*, *Check first*, *Limits*); both clients read both formats.
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
- **VAV boxes vs their coil kits:** the duct layer has 66 Price SDV5 terminal units and 90 `Coil Kit Supply/Return_2019`
  entities (the hot-water pipe connection kits on a box). Both carry type *Terminal unit*; the kits are now labelled as
  accessories and left out of `connected_run`'s notable list, so the box is named. From diffuser `#388279` the run reaches
  box `#400766` (Price SDV5, 1-2 row coil) in 11 steps (10 duct pieces between); its two kits `#383845`/`#383987` touch it
  and the last duct piece, one step earlier.
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

## Voice (Milestone B, revised Nov 5 2026)

- **Spoken answer = the card paragraph** for live (plain-format) answers: one `speak` event when the `Evidence:` line
  arrives, and `final.spoken` is the tidied paragraph with units spelled out (`speech.plain_speech`); the Evidence line is
  never read. For card-format (mock) answers:
- **Spoken answer is short:** the server turns the streamed answer into `speak` events (`scripts/ask_twin/speech.py`): the lead
  sentence and at most one *check first* sentence, in plain words ("Most likely the VAV box, 11 steps along touching ducts
  from here. First, trace the duct from here to the VAV box on the mechanical drawings."). Ids become names (*the VAV box*),
  the selected element becomes *this/here*; markdown, `[[ids]]`, parentheses, CAD codes and *confidence* are dropped. Each
  part is sent as soon as its line is complete, so speech starts before the card has finished. Text a live model writes
  before its tool calls ("Let me check…") is never spoken. The card keeps all details.
- **Laptop voice first:** `/api/speak` uses the best installed macOS English voice: a *(Premium)* en_US/en_GB voice (Zoe, Ava,
  Evan, Nathan, … preferred in that order, US before GB), else *(Enhanced)*, else Samantha; `--voice` overrides. Localized
  names are recognised (e.g. `(프리미엄)`, `(고품질)` on a Korean-language Mac). The headset page uses the laptop voice when
  the server has one (the Quest browser voice sounds robotic); the 2D box button *Voice: laptop / headset* or `&voice=headset`
  switches. Download a natural voice once (free): **System Settings → Accessibility → Spoken Content → System voice →
  Manage Voices… → English (US) → Zoe (Premium)** and/or **Ava (Premium)**; restart the server; it prints the voice it chose.
  A local neural TTS (e.g. Kokoro-82M, ~330 MB model + `kokoro`/`onnxruntime` packages) would sound better still; not installed.
- **Speech-to-text:** faster-whisper `base.en`, beam 5, VAD (trims leading/trailing silence; `min_silence_duration_ms` 400),
  a domain `initial_prompt` and `hotwords` (Grimes, duct, diffuser, VAV box, damper, airflow, sprinkler pipe, valve, ceiling
  tile). Segments that look like no speech (no_speech_prob > 0.6 with avg_logprob < −1) and transcripts that only echo the
  prompt are dropped; an empty result returns `no_speech: true` and the headset says *Didn't catch that* instead of asking.
  Measured on this Mac (synthetic `say` speech, not a Quest recording): 0.3-0.4 s per question. `small.en` (~480 MB
  download) was not measured; try `--stt-model small.en` if Quest transcripts stay poor.

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

### Method A: the public page, AI calls to the laptop (owner steps)

The page comes from GitHub Pages; only `/api/health`, `/api/ask`, `/api/transcribe` and `/api/speak` go to the laptop. Nothing
costs money publicly: the laptop server answers only on the owner's Wi-Fi, and only for `https://doe2park.github.io` (exact
CORS allow-list; preflights including Chrome's Private Network Access are answered for that origin only).

1. Mac and Quest on the same Wi-Fi. On the Mac (`feat/ask-twin-ai` worktree, or `main` once published):
   `python3 scripts/ask_twin_server.py --mock --lan` (live: drop `--mock` once the key is in place). It prints the exact address.
2. **Once per headset (certificate):** in Quest Browser open `https://192.168.68.52:8765/trust` (the laptop's address as printed),
   tap **Advanced → Proceed**, see *Laptop server reached*, close the tab.
3. Open the *public page + this laptop* link the server printed, e.g.
   `https://doe2park.github.io/Graduate-Project/mr/?ask=1&server=https://192.168.68.52:8765&code=K7PX3M` (the code is required;
   the published page sends it only once this branch is on `main`).
   If Quest Browser asks to let the page **access devices on your local network**, tap **Allow** (Chrome's Local Network Access;
   desktop Chrome 156 requires it; whether Quest Browser asks is not verified). If the box says *server not reachable*, tap the
   link *Open https://…/ once to trust it*, accept, come back and press **Retry**.
4. Press **Allow mic**, then **Test voice**, then **Enter MR**.

`server=` is used only if it is `https://` + a private-LAN IPv4 (10/8, 172.16/12, 192.168/16) or `localhost` + an explicit port,
with nothing else (no path, query, user, hex or zero-padded IP); otherwise it is ignored and the box says so. Without `?ask=1`
the public page is unchanged.

### Asking in the headset (Nov 5 2026 flow)

- **Point and ask:** point at a duct, pipe, light or diffuser and **hold the trigger** (≥ 0.4 s): a short chime, a red
  *Listening…* ring pulses on the element and the info card + ask bar appear; speak; **release** → the question is sent with
  that element. A short trigger press works as before (info card + ask bar with the four level buttons). The hold is not
  armed while pointing at a panel, aiming a move, holding the grip, placing the demo, aligning or while an answer is busy.
- **While waiting:** a send tone; the card shows *Thinking…* and then a line per server step (*Checking what is above it…*,
  *Following the ducts…*, *Reading the demo sensors (simulated)…*); if nothing has been said after 1.5 s the voice says
  *One moment.*
- **Answer:** the spoken lead starts as soon as it arrives, then one *First, …* sentence; the card, citations, glow and
  lit run are as before; the provenance footer stays. In scripted mode with no key the card footer and the 2D box say
  *Live AI needs a key on the laptop; running scripted answers*.

**Status: built and checked on the Mac only. Not tested on a headset.** The four question levels work inside the immersive
MR/VR page (`scan-xr.html`, the page behind `/mr`) in mock mode; nothing below is verified on Quest hardware.

`/mr` is a redirect to `scan-xr.html?mode=ar&place=demo&sensors=demo` and passes extra parameters through, so
`/mr/?ask=1` opens the MR page with the ask feature. `scan-xr.html` is a different page from the element viewer
(`grimes-bim-viewer.html`); both talk to the same local server. Without `?ask=1` the MR/VR page is unchanged.

### What you do in the headset

0. (New) Hold the trigger on an element to ask by voice: see *Asking in the headset* above.
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
5. The short answer is read aloud: the laptop's macOS voice (`POST /api/speak` → WAV played with Web Audio) when the server
   has one, else the browser voice if `speechSynthesis` has one (2.5 s start watchdog), else the card says *text only*.

Mock mode routes any question (typed, preset or spoken) by keywords (`mock_route` in `agent.py`): leak/stain → leak,
valve/shut off → valve, warm/hot/cold/why → comfort (level 4), feed/come from/where does the air/which VAV → feed (level 3),
above/over the ceiling/plenum → above (level 2), what is this/what room → look up (level 1), anything else → a description.
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
| Method A from the public page | Desktop Chrome 156 (headless smoke, `tests/xr-ask-methoda-smoke.cjs`): works after the *local network* permission and the certificate are accepted. Quest Browser's handling of Local Network Access / Private Network Access is not verified. | Same-origin page from the laptop (`https://<ip>:8765/mr/?ask=1`) as before. |
| Point-and-ask hold | Desktop check through the real hold path with a stand-in controller (`xrDebug.ask.holdSim`) and Chrome's fake mic playing a recorded question. Real controller timing on Quest not verified. | The 1-4 buttons and *Hold to speak* on the bar. |
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
node --test tests/xr-ask.test.cjs                                       # headset helpers: stream, card model, speech text, run path, bar hit, drawing, server= validation, progress, hold gate
# Method A, desktop Chrome against the running --lan server (public origin served from this checkout by Playwright):
PLAYWRIGHT_MODULE=/path/to/playwright-core FAKE_AUDIO=/abs/question.wav node tests/xr-ask-methoda-smoke.cjs https://<lan-ip>:8765
node --test tests/ask-twin.test.cjs                                     # laptop panel: code= from the URL, X-Ask-Code header, 401/429 text
python3 scripts/ask_twin_server.py --mock --no-code &                   # then the headless browser check (or keep the code and pass ASK_CODE=<code>):
PLAYWRIGHT_MODULE=/path/to/playwright-core CHROME_EXECUTABLE=/path/to/chrome-headless-shell \
  [FAKE_AUDIO=/abs/question.wav] node tests/ask-twin-smoke.cjs          # screenshots -> work/ask-twin/shots/
```

The smoke scripts (`ask-twin-smoke`, `xr-ask-smoke`, `xr-ask-methoda-smoke`) append `code=$ASK_CODE` to their page URL when it is set.

The headless check loads three element layers under software WebGL and takes about 2-4 minutes of full CPU.

## Files

- `scripts/ask_twin_server.py` — server (static read-only + `/api/health`, `/api/ask` SSE, `/api/transcribe`, `/api/speak`)
- `scripts/ask_twin/limits.py` — access code, rate limits, daily token budget (usage JSON outside the repo)
- `scripts/ask_twin/index.py` — element box index; `tools.py` — read-only tools + schemas; `agent.py` — live and mock loops (+ `mock_route`); `speech.py` — short spoken version and `speak` events
- `twin/ask-twin.js` — panel, citation chips, highlights, fly-to, push-to-talk, spoken reply
- `twin/xr-ask.js` — headset helpers and canvas drawing (ask bar, answer card, Claude badge); `scan-xr.html` `?ask=1` block wires it into the XR page
- `tests/xr-ask.test.cjs`, `tests/xr-ask-smoke.cjs` — headset helper tests and the desktop-simulation smoke
- `grimes-bim-viewer.html` — small `?ask=1` hook (`window.twinViewerApi`, pick context); inert without `?ask=1`
- `tests/test_ask_twin.py`, `tests/ask-twin-smoke.cjs`
