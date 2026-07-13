# Project Context — UC Berkeley Campus Digital Twin

> Paste this whole file into a fresh Cowork session. Gives a new Claude full context to continue without redoing work.
> User: Yoonsung (yschung1105@gmail.com) · Graduate student, UC Berkeley.

---

## TL;DR

Web-based digital twin of UC Berkeley campus energy, centered on **Grimes Hall / Bechtel Engineering Center**. Live BMO meter data on ArcGIS map + 3D BIM viewer for Grimes + LEED submittal data integration + Cupix 360° panorama compare with auto-sync.

**Three main pages:**
- `grimes-campus-map-arcgis.html` — campus map, Engineer/Public modes, per-building popups (LEED panels for Grimes)
- `grimes-xr.html` — 3D BIM viewer with custom Three.js + MEP-only glb model
- `grimes-aps-viewer.html` — NEW — full Bechtel BIM via Autodesk APS Viewer (no glb conversion needed)

**Live URLs:**
- Main map: https://doe2park.github.io/Graduate-Project/grimes-campus-map-arcgis.html
- XR viewer (MEP-only): https://doe2park.github.io/Graduate-Project/grimes-xr.html
- APS viewer (full BIM): https://doe2park.github.io/Graduate-Project/grimes-aps-viewer.html
- LEED panels preview: https://doe2park.github.io/Graduate-Project/leed-lca-preview.html

**Repo:** https://github.com/doe2park/Graduate-Project (GitHub Pages auto-deploys main)

---

## File map (most important first)

| Path | What it is |
|---|---|
| `grimes-campus-map-arcgis.html` | Main campus map. ArcGIS JS, sonar markers, Engineer SCADA + Public storytelling popups. LEED panels for Grimes only. |
| `grimes-xr.html` | Three.js BIM viewer (MEP only — `grimes-mep-only.glb`). Floor nav, heatmaps, Cupix Compare split-screen with auto-sync. |
| `grimes-aps-viewer.html` | **NEW** — Autodesk APS Viewer embedding the full Bechtel NWD by URN. Cupix Compare with calibration toggles. **CURRENTLY DEBUGGING COORD ALIGNMENT.** |
| `worker/chatbot-worker.js` | Cloudflare Worker — `/aps-token` endpoint (NEW) + chatbot proxy |
| `data/campus_energy.json` | Live BMO snapshot (auto-updated ~15min via GitHub Actions) |
| `data/baselines.json` | Per-building hour-of-week baseline |
| `data/bechtel_leed.json` | LEED v4 Energy Performance — 11 end-uses, baseline vs designed |
| `data/bechtel_lca.json` | LEED v4.1 MR Material Reuse — element reuse % |
| `data/grimes-interior.json` | Manifest for interior scan + Cupix integration |
| `data/bechtel_nwd_metadata.json` | APS metadata dump — **LOCAL ONLY, not in repo** (regenerate via `convert_nwd_local.py`) |
| `data/bechtel_nwd_properties.json` | 504MB property dump — **LOCAL ONLY, not in repo** |
| `convert_nwd_local.py` | NWD→APS pipeline (auth, upload, translate, properties) |
| `extract_leed.py` / `extract_lca.py` | LEED data extraction scripts |
| `APS_VIEWER_SETUP.md` | Cloudflare worker setup guide (env vars, deployment) |
| `LEED_LCA_PRESENTATION.md` | English presentation notes for LEED integration |

---

## CURRENT STATE — what works / what's stuck

### ✅ Working

- Main campus map with Engineer/Public modes
- Per-building LEED panels for Grimes (Engineer + Public both)
- `grimes-xr.html` with Three.js MEP viewer + Cupix Compare + sync (calibrated)
- `grimes-aps-viewer.html` APS Viewer renders the full Bechtel BIM (loads via URN, no glb)
- Cupix postMessage flow confirmed (~262 msgs/sec when navigating)
- Worker `/aps-token` endpoint serving APS V2 tokens

### 🟡 IN PROGRESS — Cupix→APS Viewer coordinate alignment (yaw fix implemented, needs live test)

**2026-07 root-cause analysis:** the old toggle set (scale / swapY↔Z / flipZ / subtract-offset) could never align, because the working grimes-xr calibration (`data/cupix_calib.json`) proves the Cupix↔BIM registration includes **yaw ≈ −135° about the up-axis** — unreachable by 90° swaps and sign flips. `grimes-aps-viewer.html` now applies **scale → yaw(Z) → offset**, with defaults derived from cupix_calib.json conjugated into Z-up/feet: scale 3.2808 · yaw −135° · offset (55.4, −35.4, 20.0) ft = 3.2808·(o.x, −o.z, o.y). Yaw/offset are editable in the sync panel and persisted to localStorage. Also: do NOT enable "subtract globalOffset" — it pushes z to ≈ −338 ft, outside the bbox (±47.6).

<details><summary>Original stuck-state notes (pre-yaw)</summary>


Despite both viewers loading same NWD (`ALL - UCBBE - COMBINED.nwd`, which IS Bechtel-only per user), camera positions don't align.

**Confirmed data from console:**
```
globalOffset:  x=115.23  y=79.21   z=345.06
bbox.min:      x=-220.55 y=-183.09 z=-47.57
bbox.max:      x=220.55  y=183.09  z=47.57
bbox.size:     x=441.10  y=366.18  z=95.14   → tallest axis = Y (but world up = Z)
world up:      x=0.00    y=0.00    z=1.00     (Z-up world)
```

**Cupix tm sample (row-major 4×4):**
```
position: (26.26, -27.29, 2.08)
```

**Latest hypothesis (untested as of handoff):** Unit mismatch. APS Viewer uses **feet** (441 ft = 134 m, plausible for Bechtel), Cupix sends **meters**. Fix: multiply Cupix coords by **3.2808** (m→ft). Default scale in latest push is 3.2808.

**If unit fix doesn't work:** combinations of toggles available in the sync panel:
- `subtract globalOffset` (subtract APS's auto-shift)
- `swap Y↔Z` (if APS turned out to be Y-up — but logged up shows Z)
- `flip Z sign` (handedness mismatch)
- `Lock anchor` manual fallback (NOT preferred — only if nothing else works)

The right combination is whichever puts the APS camera inside the building. Console logs every 30th sync with raw/transformed values.

</details>

### ❌ Known broken / blocked

- `convert_nwd_local.py` `to_glb()` step (was using `forge-convert-utils` which calls dead V1 auth endpoint — confirmed broken). Bypassed by using APS Viewer SDK directly.
- NWD → OBJ Model Derivative output stays at 0% (APS doesn't support OBJ for NWD source).

---

## How to continue debugging APS Viewer sync

1. Open https://doe2park.github.io/Graduate-Project/grimes-aps-viewer.html
2. Cmd+Shift+R (cache bust)
3. Open DevTools console
4. Wait for `[aps-viewer] model loaded.` log with bbox/offset values
5. Click `⌂ Fit view` to see whole model (confirms it's Bechtel only or campus combined)
6. Click `🪞 Cupix Compare` → split-screen
7. Click into Cupix photo + drag → check sync panel
8. Try toggling: default scale 3.2808 first (already on), then add `subtract globalOffset` if still off, then others
9. Console logs `[sync] cupix raw: ... → transformed pos: ... · toggles: {...}` every 30th sync — paste to diagnose

### What the right combination probably is

Most likely: just `scale=3.2808` (the default in latest push). If not, also `subtract globalOffset`. Y/Z swap probably NOT needed (both are Z-up). Z flip probably NOT needed.

---

## LEED data context

User received 2 LEED submittal packages from professor:

**Package 1 — Energy Performance** (`20240529_Bechtel_LEEDv4MinEnergyPerfCalc.xlsm`)
- LEED v4 BD+C EAp2 + EAc1 compliance
- 11 end-uses, ASHRAE baseline vs eQuest proposed
- Result: 1,501 → 825 MWh/yr = **45% modeled savings**
- Extracted by `extract_leed.py` → `data/bechtel_leed.json`

**Package 2 — Life-Cycle Submittal** (`UCB _LEED_LCA credit.xlsx` + PDFs)
- LEED v4.1 MR Building Life-Cycle Impact Reduction (Option 1, Path 1)
- 4 elements (walls/floors/roofs/envelope)
- Result: **70% of project area reused** → **LEED 4 points**
- Extracted by `extract_lca.py` → `data/bechtel_lca.json`

LEED Project **#1000171106** · SOM architect · Sage Green Strategies LEED consultant · Nov 2023 submittal.

---

## Cupix integration

- Cupix URL: `https://herrero.cupix.works/v2/sv/q7qk7m?svpl=basic&svv=4&qp=2QtKby0x5DjQCH1Yrdk5rr&ql=83000`
- Cupix has Bechtel scanned, BIM overlay via their own internal Forge Viewer
- Cupix postMessage protocol confirmed:
  - `responseType: 'VIEW_ACTIVE_CAMERA_ROTATED_RESPONSE'`
  - `response.cameraParameters.tm: [16 floats]` (row-major 4×4)
  - Position at `tm[3], tm[7], tm[11]`
  - Camera back = `tm[8..10]` → forward = `-tm[8..10]`
  - Camera up = `tm[4..6]`
  - Camera right = `tm[0..2]`
- The Three.js viewer in `grimes-xr.html` has working Cupix sync after manual Lock Here calibration (Y↔Z swap + offset)
- The APS Viewer in `grimes-aps-viewer.html` should NOT need manual calibration if unit scale is right

---

## NWD conversion (done, won't redo)

User uploaded `ALL - UCBBE - COMBINED.nwd` (185 MB, Bechtel only despite the name). APS conversion succeeded. URN:

```
dXJuOmFkc2sub2JqZWN0czpvcy5vYmplY3Q6Z3JpbWVzLXR3aW4tYXRhNnc3Z2hzdGFxeHd5ajV0YTIvQUxMJTIwLSUyMFVDQkJFJTIwLSUyMENPTUJJTkVELm53ZA
```

(Hardcoded in `grimes-aps-viewer.html`)

APS credentials live ONLY in env vars (`APS_CLIENT_ID` / `APS_CLIENT_SECRET`) and Cloudflare worker secrets. They were previously committed to this public repo (`convert_nwd_local.py`, `APS_VIEWER_SETUP.md`) — **those keys are burned and must be rotated** at https://aps.autodesk.com/myapps. `convert_nwd_local.py` now reads env vars and exits if unset. Worker `/aps-token` is origin-restricted to doe2park.github.io, scope `viewables:read` only, with token caching.

To rotate: generate new keys at https://aps.autodesk.com/myapps, then `export APS_CLIENT_ID=... APS_CLIENT_SECRET=...` locally and update worker secrets via `wrangler secret put APS_CLIENT_ID` / `APS_CLIENT_SECRET`, then `wrangler deploy worker/chatbot-worker.js --name campus-chatbot`.

---

## User preferences (learned from many iterations)

- **English only** in deliverable files / preview / notes
- **Korean only in chat**
- **Less empty space** — tight padding, dense layouts
- **No big hero blocks** — key numbers in section headers
- **Restrained typography** — fewer weights (400/500/700)
- **Hover for details** — primary surface skimmable, exact numbers in `title=""` tooltips
- **Don't repeat data** between two visualizations in same panel
- **Visual elements should encode meaning** (length, color, shape) not just text
- **Terse explanations**, not bloated
- **No manual calibration / matching when avoidable** — programmatic solutions preferred
- **No apologies / promise then break** — diagnose root cause first
- **User is technical** — can paste console output, knows what curl is, but doesn't want to debug for me

---

## Workflow notes

### Pushing changes — DO NOT USE LOCAL CLONE

Local `~/Graduate-Project` is 1000+ commits behind origin. ALWAYS push via fresh sandbox clone:

```bash
cd /tmp && rm -rf graduate_fresh
git clone https://doe2park:<TOKEN>@github.com/doe2park/Graduate-Project.git graduate_fresh
cp "/sessions/<sandbox-id>/mnt/Graduate-Project/<file>" /tmp/graduate_fresh/
cd /tmp/graduate_fresh
git config user.name "Yoonsung" && git config user.email "yschung1105@gmail.com"
git add <files>
git commit -m "..."
git push origin main
```

GitHub PAT for pushes — store in env var or password manager, never commit to repo.
- User should rotate any tokens that appeared in chat history.
- Use `GITHUB_TOKEN` env var: `export GITHUB_TOKEN=ghp_...` then `git clone https://doe2park:$GITHUB_TOKEN@github.com/...`

### Syntax checking

For `grimes-xr.html` (uses `<script type="module">`):
```bash
node -e "
const fs = require('fs');
const html = fs.readFileSync('grimes-xr.html', 'utf8');
const m = html.match(/<script type=\"module\">([\s\S]*?)<\/script>/);
fs.writeFileSync('/tmp/_xr_module.mjs', m[1]);
" && node --check /tmp/_xr_module.mjs
```

For other HTMLs (plain script blocks), use `new Function(src)` to parse.

### onclick handlers in modules

`grimes-xr.html`'s main JS is in `<script type="module">`. Top-level functions are NOT global. To make `onclick="fn()"` work, explicitly assign at module bottom:
```js
window.fn = fn;
```
Recent additions all needed this (toggleCupixCompare, lockHere, etc).

---

## Recent commit log (last ~25, most recent first)

- `4f4bd23` APS sync: experimental toggles (offset / Y-Z swap / Z flip) + explicit logging
- `571d74f` APS Viewer sync: subtract model.getGlobalOffset() from Cupix positions
- `d899f18` APS Viewer sync: flip target sign — tm row 2 is camera BACK
- `cade6ad` APS Viewer: relax postMessage listener + add Test sync button
- `ef0b89a` APS Viewer sync: use viewer.getCamera().position.constructor for THREE.Vector3
- `65b05c7` Plan C — embed APS Viewer + Cupix sync (no NWD conversion needed)
- `5380851` Fix showPopPub ReferenceError (liveTs undefined → Public popup crashed)
- `a8b4c82` Preview: aggressive compaction, Engineer + Public side by side
- `a8944ea` Cupix sync: row-major matrix + Z-up→Y-up swap (Three.js version)
- `2e18085` Cupix sync: relax listener filter + message type histogram
- `90c478b` Test sync: bypass dispatchEvent, call apply directly
- `2f11e37` Add Test sync button for isolated debugging
- `754f973` Fix viewMode crash from new topbar buttons + expose debug vars
- `d913737` Cupix sync: skip OrbitControls.update() during sync
- `5730ee0` Cupix → BIM auto-sync end-to-end
- `b60916b` Cupix Compare: floor-sync UX + postMessage listener experiment
- `c3cac31` Cupix: drop sandbox + update URL
- `d711257` Cupix Compare: hide overlapping left-side UI
- `15d416f` Cupix Compare split-screen
- `1e57b69` Cupix 360° integration (Option C — hotspot links)
- `c4c6e52` Fix text overflow in new LEED/LCA panels
- `a2d2398` Add LEED + LCA layer for Grimes (initial)

---

## Open priorities (user's choice)

1. **Finish APS Viewer Cupix sync** (try scale=3.28, then offset, then swap) — almost there, just coord transform tweaks
2. **Prepare presentation slides** — `LEED_LCA_PRESENTATION.md` notes exist, could become pptx
3. **Add Bechtel-only NWD if available** (skip this if combined NWD turns out to be Bechtel after all — user confirmed it is)
4. **Auto-search Bechtel within combined NWD** (skip — file is already Bechtel-only)
5. **Cupix Web SDK official access** — long-term

---

## First message to fresh Claude

If you're a fresh Claude reading this:

1. **Don't redo work** — read this file first, the user has been iterating for weeks
2. **The user is technical** — give them concrete commands and console output to inspect, not vague hand-waving
3. **For any file edit, push via /tmp/graduate_fresh clone** (see workflow above)
4. **Stop apologizing — diagnose** — when something breaks, ask for console logs / specific numbers BEFORE proposing fixes
5. **The Cupix→APS sync is the active blocker** — coordinate alignment issue (likely units). If they say "still doesn't work", get exact console output before guessing again
6. **The combined NWD file IS Bechtel only** despite the name — confirmed by user, do not assume scope mismatch again
7. **APS Viewer is Z-up** with units possibly in feet (bbox 441×366×95 suggests this)
8. **No manual calibration matching** — user has explicitly rejected this as a primary path

---

## Quick test the project is alive

After pulling latest, in a browser:
1. Open https://doe2park.github.io/Graduate-Project/grimes-aps-viewer.html
2. APS Viewer should render the Bechtel BIM (full architectural model with MEP/structure)
3. Click `🪞 Cupix Compare` → split screen
4. Navigate in Cupix → check sync panel for msg count + position match
5. The unit scale (3.2808 default) should make positions land inside the building

If broken at any step, that's the regression to fix first.
