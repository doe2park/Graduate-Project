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

**Stack:** UC Berkeley BMO utility meters → GitHub Actions (cron `*/15`, but GitHub fires it only every ~4-5 h; see below,
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

`campus-3d`, `grimes-xr`, `comfort-dashboard`, `vote`,
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

Registration methodology and archived computation: `docs/SCAN_BIM_REGISTRATION.md`. The old Cupix -135-degree calibration is not the exported scan GLB registration. Internal nearest-point residuals (median ~0.13 m) are not surveyed accuracy.

## Captured panorama comparison (2026-09-11)

The scan comparison now defaults to `scan-photo.html`: 100 actual 4096×2048 E57 panoramas, with original image poses and 2K mobile derivatives under `scan-assets/panoramas`. Source inventory has 217 positions; do not claim all 217 images were recovered. The E57 includes Level 1 elevation, so do not add 4.572 twice. Photo mode walks between recorded stations over an inferred capture-adjacency graph, crossfading photos and synchronizing BIM; endpoints retain recorded positions and intermediate blends are not measured parallax; select 3D mesh for free translation. The accepted GLB-to-BIM registration is unchanged. Details and tests: `docs/CAPTURED_PANORAMA_VIEWER.md`. `Show electrical` reveals conduit, receptacles, lighting and equipment without interior occlusion, retaining the floor. Device policy uses the top-level window, not an iframe width.

## New capture intake (2026-09-12)

Use `scripts/capture_import.py prepare` for a new building/floor/capture; `capture-review.html?project=...` reviews its isolated package. `capture-local/` is ignored. Original E57 poses are converted once without a Grimes elevation offset; no registration or sensor feeds are inherited. The optional landmark fit remains provisional with independent checks. INSV requires reconstruction and NWD/IFC requires conversion before intake; do not claim direct upload-to-twin support. See `docs/CAPTURE_ONBOARDING.md`.

## Local Gaussian reconstruction (2026-09-13)

`scan-splat.html` renders actual optimized 3D Gaussians with pinned GaussianSplats3D 0.4.7 / three 0.169.0, continuous camera movement and the existing bidirectional scan/BIM transform. `scan-compare.html?mode=splat` selects the locally available experimental manifest under ignored `capture-local/gaussian/pilot/`; the ordinary entry keeps photo mode. A 1M-splat Brush 0.3.0 result is the local default after a 2M capacity experiment showed little final quality improvement. Desktop KSplat is 48.1 MB; mobile uses a reduced 350k SH0 model. Substantial blur remains; do not claim photograph-quality or surveyed geometry. No source GLB or data-branch changes, and no public Gaussian asset deployment.

Reusable scripts: `prepare_gaussian_dataset.py`, `train_gaussian.py`, `encode_gaussian.mjs`, `package_gaussian.py`. Preserve original posed image/scan coordinates; never apply Grimes registration to another building by changing the manifest path. Raw INSV still needs pose/scale reconstruction. Actual methods, references, metrics and evidence: `docs/GAUSSIAN_RECONSTRUCTION_METHODS.md`. Future PPT additions are recorded in the owner's local `Grimes_360_Pilot/Presentation_Update_Backlog.md`; no PPT or deleted presenter notes were changed. Browser tests: `tests/splat-viewer.cjs`, `tests/splat-integration.cjs` (local optimized asset required), `tests/gaussian-codec.cjs`; Python camera/package tests use the isolated NumPy/SciPy/Pillow environment.

## Weekly history restored (2026-09-17)
At the owner’s explicit request, weekly-report.html is again maintained as a companion to Campus Energy Dashboard. It reads the automated data branch daily/index.json and up to seven daily snapshots per window, with cached back/forward navigation, zero-preserving sample statistics, missing-day gaps and CSV export. These are collector observations, not verified continuous meter histories. Archive date labels are UTC collector dates; extrapolated energy is sum(daily sample mean × 24 hours), not measured counter deltas. No manually written data branch reports.

UI updates must include mobile-width overflow, touch interaction and chart/legend checks, per owner request (2026-09-17). Dashboard building charts share category colors. Demand per floor is a rough comparison, not an energy-efficiency rating.

Walk loading exception (2026-09-17): while a layer loads, active Walk may render bounded preview frames (250 ms desktop / 400 ms narrow or touch) so camera motion remains visible. Ordinary orbit loading still pauses renders. This avoids the previous total visual freeze; large synchronous geometry work can still cause stalls.

## September capture update (2026-09-21)
The comparison now defaults to the September 17 Level 1 capture; a date picker preserves the May 6 baseline. `scan-assets/captures/2026-09-17/` contains 100 E57 posed photos, a byte-identical exported mesh and mobile derivatives. September uses a separately labeled **provisional project-frame alignment**, not the verified status of the May registration. Its 95 temporal route edges leave four sparse gaps. Gaussian remains the May-only local experiment. See `docs/CAPTURE_UPDATE_20260917.md` for provenance, coordinate checks and limits.

## Data cadence, honesty states and Walk info cards (2026-10-14)
GitHub's `schedule` trigger fires these workflows only every ~4-5 h (verified via the Actions API). `worker/dispatch-cron/` is a separate Cloudflare Worker that dispatches both workflows every 15 min once the owner sets its `GITHUB_TOKEN` secret and deploys it (see its README). Independently, `bmo_fetch_campus.py` backfills every BMO interval row since the last stored timestamp, so history no longer depends on run cadence. A BMO outage or zero online buildings aborts the run without overwriting published files. The hour-of-week baseline cache was rebuilt (version 2) because sparkline ingestion had phase-shifted it; TOWT fits resume after ~14 days of 15-min history.

Pacific-date history (2026-10-16): `bmo_fetch_campus.py` also merges every retained observation of configured buildings into append-only `data/history/<Pacific date>.json` (`[[ts, kW], …]` per building, naive America/Los_Angeles wall time; `history/index.json` lists dates). `campus_energy_history.json` stays 24 h because the campus map loads it. The dashboard's 7/30/90-day periods start at Pacific midnight (24 h stays rolling), read these files, and say where 15-minute history begins; UTC-named `daily/` and `archive/` files are unchanged and labelled as UTC collector dates. Tests: `tests/test_pipeline_campus.py` (PacificDayFileTests), `tests/energy-dashboard.test.cjs`.

Shared UI vocabulary: LIVE only for finite readings ≤45 min old; older readings show a grey LATEST badge with "Last reading HH:MM · Nh ago" (Pacific); missing values show "—", never 0. Building meter totals are labelled as context, never as an element's or system's own sensor.

Walk mode has AR-style info cards (`I` toggles): dwell 400 ms on an element shows its tier — explicit element feed (`buildings/grimes/element-feeds.json`, ships empty) → MODELLED share → building-meter CONTEXT → NO FEED. See `docs/ELEMENT_FEEDS.md`. `?capture=1` exposes `window.walkCapture` for deterministic presentation recording only.

## Scan↔BIM overlay and public Gaussian layer (2026-10-14)
`scan-compare.html` has Compare / Overlay / Scan / BIM views (`?view=overlay&opacity=30`). Overlay stacks the synced BIM pane over the scan pane at the same rect, renders only service layers (equipment, lighting, conduit, duct, hydronic, plumbing, life safety, fire; fire skipped on phones) on a transparent background at 30% default opacity, and labels alignment honestly (Sep 17 provisional; May registered, internal residual ≈0.13 m, not surveyed). At the owner's request the May 6 Gaussian scene is now public in `scan-assets/gaussian/2026-05-06/` (`trained.ksplat` 48.1 MB desktop, `mobile.ply` 19.6 MB SH0 350k; SHA-256 match the manifest provenance; the mobile file was regenerated byte-identically from `export_50000.ply` with `scripts/package_gaussian.py` logic). It remains May-only, experimental appearance, not surveyed geometry.

**Overlay styles (`?view=overlay&style=lens|ghost|plain`, default lens).** Based on AR X-ray-vision work: LENS = cut-away / virtual excavation (Schall et al. 2009, handheld AR for underground utilities) with focus+context (Kalkofen et al. 2007): a soft circular hole, radius 22% of the shorter side, services ~85% inside and ~8% outside (CSS `mask-image` radial gradient on the BIM layer) with a thin ring; the lens follows the mouse via `grimes-pointer` postMessages from the photo/mesh/splat panes and stays centred on touch (no easing under `prefers-reduced-motion`). GHOST = edge-based ghosting (Kalkofen 2007; Avery/Sandor): a second `scan-photo.html?edges=1` instance (transparent canvas, Sobel edge post-process, gold edges, camera and station mirrored via `grimes-linked-pose` / `grimes-photo-station`, hidden during station transitions) is stacked above the BIM layer; it is enabled only for 360-degree photos on wide non-touch devices, otherwise the UI falls back to Plain with a note. PLAIN = uniform opacity slider. Ordinal depth cues (real room in front, services behind) are preferred over absolute depth (Zollmann et al. 2014). All styles apply a screen-space outline pass (`saturate(.72)` plus dark `drop-shadow`) to the BIM layer; MEP-only. Alignment labels are unchanged. Logic and tests: `tests/scan-overlay.test.cjs`. Limitations: Ghost not implemented for mesh/Gaussian; lens on touch is not draggable.

## Registration workbench and overlay diagnosis (2026-10-14)
Overlay misalignment was diagnosed before changing anything (`docs/REGISTRATION_WORKBENCH.md`, evidence in the owner's `Graduate-Project-media/review/registration/`). Photo headings match the textured mesh within 0.4° (the 100 identical E57 quaternions are world-aligned panoramas, not missing headings). Overlay projection is exact. May's accepted ICP is ~6 cm at walls and ~0 at floors. September's provisional (borrowed May) transform is off by ~0.7° yaw (median wall offset 0.28 m). A dated Sep ICP candidate `scan-assets/captures/2026-09-17/registration-candidates/2026-10-14-icp-arch.json` (0.13 m) is preview-only via `scan-compare.html?registration=<path>`. `registration-workbench.html` + `registration-core.js` (landmark pairs, RANSAC, leave-one-out, independent checks, per-photo heading) export new dated candidates. `scripts/registration_fit.py` reproduces fits and runs the archive ICP. Never write `accepted-registration.json` or a capture `registration.json` from these tools. Promotion is a separate reviewed commit. Residuals are not surveyed accuracy unless every check is surveyed. Overlay **Align…** (`scan-compare.html`) is a temporary whole-BIM nudge / element-pair match on an in-memory copy of the registration, labelled "Manual alignment preview · not saved · not surveyed"; it exports a dated `manual-nudge-unsurveyed` candidate only (`docs/REGISTRATION_WORKBENCH.md` §7). Tests: `tests/registration-core.test.cjs`, `tests/registration-preview.test.cjs`, `tests/align-nudge.test.cjs`, `tests/test_registration_fit.py`.

## Gaussian training zones (2026-10-14)
Large captures can be trained in zones so teammates each take an area: `scripts/gaussian_zones.json` (per capture date: building, floor L1/L2/L3/B1, zones with `stations`, `core`, `overlapMetres`, `owner`, `status`), proposed by `scripts/plan_gaussian_zones.py` (graph-connected, similar station counts, overlap ring; never overwrites owner/status). `run_gaussian_pipeline.py --list-zones | --zone <id> | --all-zones`; `prepare_gaussian_dataset.py --stations`. Published zones live under `scan-assets/gaussian/<capture>/zones/<zone>/` with `zones/index.json`; `scan-splat.html` swaps zones by camera position. Zone names are inferred from thumbnails and marked "(likely)". Workflow: `docs/GAUSSIAN_TRAINING_GUIDE.md` ("Splitting work by zone"). Tests: `tests/test_gaussian_zones.py`, `tests/splat-zones.test.cjs`.

## Overlay Lens info cards and as-built adjustments (2026-10-14)
Shared pure helpers now live in `twin/element-cards.js`: reading freshness, feed tier, gaze dwell, card HTML and the lens pick message contract. **Exception to the single-file rule:** `grimes-bim-viewer.html`, `scan-bim.html` and `scan-compare.html` load this one same-origin classic script (like `twin/twin-resolver.js`) instead of keeping copies. The viewer binds the helpers with `var {…} = globalThis.ElementCards` inside its ELEMENT DATA HELPERS block. The vm-sandbox tests evaluate the shared file first. The Overlay Lens shows the viewer's gaze card for the element under the lens: the BIM pane picks, and the compare page positions the card (`docs/ELEMENT_FEEDS.md`). `twin/as-built.js` + `buildings/grimes/as-built-adjustments.json` (ships empty) record per-element manual as-built offsets. They are applied at render time only: instanced → per-instance matrix, merged → the element's own vertex range, snapshotted and restored bit-exactly. GLBs, node names and range maps are never changed. Labels say "manual, not surveyed" and there is a Design (BIM) / As-built adjusted toggle. `scripts/check_as_built.py` validates the file and reports design-vs-installed statistics. Owner steps: `docs/AS_BUILT_ADJUSTMENTS.md`. Tests: `tests/element-cards.test.cjs`, `tests/as-built.test.cjs`, `tests/as-built-ui.test.cjs`, `tests/test_check_as_built.py`.
