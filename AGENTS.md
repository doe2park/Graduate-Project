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
- Four **MEP fabrication layers** (ductwork 13,921 · mech piping 4,863 ·
  plumbing 2,621 · fire piping 3,861), cut by `scripts/extract_mep_layer.py`
  from the dedup master export. These are CAD entities (per-floor DWG models,
  no Revit category); identity = depth-3 entity node in the Navisworks tree
  (file → CAD layer → entity → geometry). Geometry survival is partial
  (dedup ate repeated fittings) — honest counts in each sidecar's `survival`.

Viewer behaviour: desktop opens **exterior-first** (ghost shell auto-loads,
legacy 8-mesh MEP overview hidden behind a "🎨 MEP overview" toggle); layer
list is a fixed left panel with per-layer type-filter chips; clicking any
element opens a dashboard (identity, Revit design data, live/modelled power,
neighbours). Rendering is InstancedMesh per (geometry, material); line-only
2D-symbol elements render as THREE.Line and are pickable.

**Data honesty ladder (a thesis principle — preserve it):**
measured (3 building meters only) → **modelled** (meter 77 apportioned over
loads by Revit design VA; meter 3 over supply diffusers by design CFM;
meter 76 deliberately NOT split) → inferred (level via kNN). Every number in
the UI is labelled with its tier (LIVE / MODELLED / NO FEED). Never present
an apportionment as a measurement. The electrical model is **not circuited**
(no panel→circuit tree — verified against the full property dump); the
panel-schedule PDFs + BACnet read access have been requested from Facilities.

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
  --join false --flatten false` (the only safe gltf-transform invocation).
- **Enrichment:** `scripts/classify_elements.py` (type taxonomy, feed tiers,
  kNN level inference, meter apportionment pools).
- **Testing:** headless Playwright against `python3 -m http.server`; drive the
  viewer via `page.evaluate("toggleLayer('x')")` (clicks stall under software
  GL); serve `data/building_data.json` via route-fulfill.
- Local edits: work on `main`, verify, push. Two agents share this repo —
  **always `git pull` before starting work**, keep commits small and messaged.

## Current roadmap (agreed with the owner)

1. **Draw-call merge tier**: merge geometry per (level, material) with a
   triangle-range → element map so all ten layers render together without lag
   (~100k draw calls today; fire piping 49k is worst). Keep per-element
   picking via face index lookup. Interim cheap win: per-level display filter.
2. Targeted no-dedup re-export for the four MEP fabrication layers → 100%
   geometry survival (compute wanted dbIds from `extract_mep_layer.py`).
3. Embodied-carbon card from structural volume × material (LEED MR
   life-cycle credit 5/5 is the certification hook).
4. WebXR AR MVP (Quest 3) on the same GLB+JSON chain; QR-code anchors.
5. Campus M&V scale-out once more buildings' EAp2 submittals arrive.

## Owner preferences

English in code/docs, Korean in chat. Dense, terse, honest labelling;
programmatic over manual calibration; diagnose-then-fix with evidence; verify
against the live site before claiming something is deployed.
