# AGENTS.md — orientation for AI agents working on this repo

> Written 2026-09-07 as a full handoff so any coding agent (Codex, Claude, etc.)
> can work here without prior conversation history. Deeper docs:
> `PROJECT_CONTEXT.md` (history), `TWIN_GENERALIZATION_DESIGN.md` (architecture
> rationale), `README.md` (public overview). The owner's research notes live in
> an Obsidian vault outside this repo.

## What this project is

M.S. thesis project (Yoonsung Chung, UC Berkeley CEE, advisor Prof. Kenichi
Soga): a **campus-scale operational digital twin** at zero hosting cost.
Grimes (Bechtel) Engineering Center is the deep pilot — LEED v4 BD+C:NC
**Platinum, awarded 2026-07-23, 82/110** (see `data/leed_scorecard.json`).
End goal: every building element carries its own live information, eventually
viewed on-site through AR glasses.

**Stack:** UC Berkeley BMO utility meters → GitHub Actions (every 15 min,
`.github/workflows/`) → JSON on the orphan **`data` branch** → GitHub Pages
(this repo, `main`) → static HTML interfaces. No servers, no build step —
every page is a self-contained HTML file.

## The four live interfaces (everything else redirects to them)

| Page | Role |
|---|---|
| `grimes-campus-map-arcgis.html` | Hub. ArcGIS map, 61 buildings, live kW/water/steam, built-in chatbot |
| `grimes-bim-viewer.html` | Grimes element-tier BIM viewer (Three.js + draco GLB, no external BIM service) |
| `campus-energy-dashboard.html` | Campus charts (Chart.js) |
| `grimes-performance.html` | LEED design-vs-actual M&V, live; Platinum scorecard section |

`campus-3d`, `grimes-xr`, `weekly-report`, `comfort-dashboard`, `vote`,
`leed-lca-preview`, `twin-viewer`, `grimes-bim-iot/protoys` are redirect
stubs (2026-09 consolidation) — do not resurrect them; old code is in git
history. A separate Cloudflare Worker chatbot lives in `worker/`.

## The viewer's data model (the heart of the project)

`grimes-bim-viewer.html` renders **ten element layers**, each a draco GLB +
identity sidecar under `buildings/grimes/`:

- Six **Revit-category layers** (equipment 1,143 · receptacles 4,927 ·
  lighting 1,735 · life safety 553 · structure 2,420 · conduit 11,063), cut by
  `scripts/extract_layer.py` from a targeted no-dedup APS SVF re-export —
  100% element identity. GLB **node name = Revit element dbId**; the sidecar
  (`*.elements.json`) maps dbId → name/category/level/type/design params.
- Four **MEP fabrication layers** (ductwork 16,704 · mech piping 11,102 ·
  plumbing 6,035 · fire piping 10,938), cut by `scripts/extract_mep_layer.py`
  from the original APS SVF with no-dedup recovery (2026-09-07). These are CAD entities (per-floor DWG models,
  no Revit category); identity = depth-3 entity node in the Navisworks tree
  (file → CAD layer → entity → geometry). All eligible entities now have geometry. Sidecar `survival` separates total,
  eligible, intentionally excluded and with_geometry counts; never count excluded
  clearance volumes as missing geometry. See `docs/MEP_RECOVERY.md`.

Viewer behaviour: the architectural Building Shell feature was removed at the owner's request on 2026-09-09, including its controls, loaders and Walk auto-load path. The lightweight MEP overview is initially visible on all devices. Ten element layers and their structural geometry remain available. Walk uses explicitly stepped heights without shell slab-following. The layer list has per-layer type-filter chips; clicking an element opens its dashboard. Rendering uses runtime-only bounded merges by level/material/type, keeping
strongly repeated geometry instanced. Triangle/line ranges resolve picks.
GLTFLoader uniquifies node names: `bindElementSourceIds` reads the exact original
`userData.name` before merging; parser associations alone are unsafe for clones.
Source parser caches are released after batching; scene rendering pauses while
a layer loads, to avoid rendering millions of triangles at every batching yield.

**Data honesty ladder (a thesis principle — preserve it):**
measured (3 building meters only) → **modelled** (meter 77 apportioned over
loads by Revit design VA; meter 3 over supply diffusers by design CFM;
meter 76 deliberately NOT split) → inferred (level via kNN). Every number in
the UI is labelled with its tier (LIVE / MODELLED / NO FEED). Never present
an apportionment as a measurement. The electrical model is **not circuited**
(no panel→circuit tree — verified against the full property dump); the
panel-schedule PDFs + BACnet read access are still needed. The owner confirmed
on 2026-09-07 that the email to the professor has not yet been sent; do not
claim that these materials/access have already been requested or received.
Current feeder associations are provisional: voltage/floor/system rules do not
prove circuit membership, and design VA/CFM allocations are uncalibrated scenarios.
A meter total shown in an element card is building/feeder context, not an
element measurement. No documentary feedEvidence is currently attached.

## Hard-won invariants — do not violate

1. **Never re-encode draco geometry** when subsetting GLBs. gltf-transform
   prune/optimize silently changes triangle counts. Copy bufferViews
   byte-verbatim (see `read_glb`/`subset_from_source` in
   `scripts/extract_layer.py`) and verify with md5/bounds checks.
2. **GLB node names are element identity.** The viewer resolves picks by node
   name → sidecar. Renaming nodes or flattening the node list breaks the twin.
3. **The `data` branch is machine-written** by Actions — never commit to it
   by hand; pages fetch it via `raw.githubusercontent.com/.../data/data/*.json`.
4. Keep pages self-contained single HTML files; CDN deps pinned
   (three@0.169.0, ArcGIS 4.29, Chart.js 4.4).
5. Labels stay honest (survival counts, MODELLED badges, caveats like
   "Apr–Aug only, heating source unverified").

## Secrets

**No credentials in this repo — it is public.** The GitHub PAT is embedded in
the local clone's remote URL (`~/Graduate-Project`); APS client id/secret and
the model URN live in the owner's Obsidian vault (`meta/secrets.md`). Never
paste them into committed files, and never commit `claude-inbox-*.patch` /
`*.lock` leftovers.

## Toolchain & workflows

- **Re-export pipeline (owner's Mac):** `node scripts/nwd_extract_subset.js
  <URN> <outdir> <wanted_dbids.json>` (per-fragment no-dedup subset from APS
  SVF); `python3 convert_nwd_to_glb.py x --skip-upload --skip-translate
  --props-only --urn <URN> --output out.glb` (full Revit property dump via
  Model Derivative); pack with `npx @gltf-transform/cli optimize in.gltf
  out.glb --compress draco --instance false --simplify false --palette false
  --join false --flatten false` (safe standard invocation for fresh raw exports; fire requires sequential
  Draco on byte-deduplicated raw glTF to retain degenerate faces, documented in
  `docs/MEP_RECOVERY.md`; never recompress an existing Draco GLB).
- **Enrichment:** `scripts/classify_elements.py` (type taxonomy, feed tiers,
  kNN level inference, meter apportionment pools).
- **Testing:** headless Playwright against `python3 -m http.server`; drive the
  viewer via `page.evaluate("toggleLayer('x')")` (clicks stall under software
  GL); serve `data/building_data.json` via route-fulfill.
- Local edits: work on `main`, verify, push. Two agents share this repo —
  **always `git pull` before starting work**, keep commits small and messaged.

## Current roadmap (agreed with the owner)

1. **Draw-call merge tier (implemented 2026-09-07; continue profiling)**: merge geometry per (level, material) with a
   triangle-range → element map so all ten layers render together without lag
   (historical ~100k draw calls; old fire-only geometry now 63 batches vs 49,104).
   Per-element picking, floor/type filters, material and primitive counts remain intact.
2. Targeted no-dedup recovery completed for all four MEP fabrication layers:
   44,779 eligible entities (19,513 recovered). Use `scripts/plan_mep_recovery.py`
   and `scripts/verify_mep_recovery.py` for future recovery.
3. Embodied-carbon scenario card implemented for structural volume × material.
   A material-matched EPD factor/source/lifecycle scope is still required; no
   project factor or avoided-carbon claim is fabricated. LEED MR 5/5 is context,
   not a substitute for an element EPD.
4. WebXR AR MVP (Quest 3) on the same GLB+JSON chain; QR-code anchors.
5. Campus M&V scale-out once more buildings' EAp2 submittals arrive.

## Owner preferences

English in code/docs, Korean in chat. Dense, terse, honest labelling;
programmatic over manual calibration; diagnose-then-fix with evidence; verify
against the live site before claiming something is deployed.

## Validation and provenance additions (2026-09-07)

- `node --test tests/viewer.test.cjs`; `node --test tests/render-tier.test.mjs`
  (three@0.169.0 installed, or THREE_MODULE points to its build/three.module.js).
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests`; recovery
  tests: `python3 -m unittest discover -s scripts -p test_mep_recovery.py`.
- `scripts/enrich_element_provenance.py buildings/grimes --properties <full-properties>`
  binds GUIDs, element tags, CAD handles and explicit fabrication Attributes.
  CAD floors derive from filenames. Legacy panel associations without attached
  `feedEvidence` are `legacy-unverified`, not panel-schedule evidence.
- BMO naive timestamps are America/Los_Angeles wall time; ambiguous DST readings
  show TIME UNKNOWN. Missing/partial/stale values never become LIVE zero.
- Selection epochs cover element, system and building async UI writes.

Fire streaming uses `grimes-fire.chunks.json` (five parts) to cap transient parser memory. The canonical `grimes-fire.glb` is preserved. Rebuild chunks with `scripts/split_element_glb.py`; never recompress the canonical geometry. Final validated runtime across all ten layers: 6,789 element batches, 66,620 identities.

## Public registered comparison (2026-09-10)

`scan-compare.html` is the registered 3D scan/BIM companion to the main viewer; `scan-bim.html` supplies the two panes. Both panes drive the same accepted rigid registration. Runtime scan and interior GLBs are copied byte-for-byte, with hashes in `scan-assets/provenance.json`; raw capture/account inventory is not published. The main viewer now links to this comparison instead of opening the legacy Cupix split. `Show all elements` / `Hide all elements` controls all ten layers independently of floor selection and loads missing layers sequentially; hiding during a load cancels the queue and keeps its late result hidden. The comparison also toggles its interior groups. See `docs/PUBLIC_SCAN_COMPARISON.md`.
