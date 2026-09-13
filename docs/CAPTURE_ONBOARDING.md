# Add a floor or building capture

The local intake path prepares a separate capture package without changing the working Grimes comparison. It handles E57 spherical images with poses or the extracted `images.json` format. A self-contained GLB is optional. It does not upload to Cupix, APS, GitHub or any other service.

## What to keep when scanning

- Keep the original camera memory-card files, including all companion INSV files; copy them before deleting/reformatting the card. Also retain any stitched video, camera settings and capture timestamps. Do not rely solely on a hosted viewer as the archive.
- Identify building, floor and capture date. Keep sessions from different floors distinct. Preserve start/end positions and a marked floor plan; note doors, stairs and transitions.
- Record stable, clearly identifiable landmarks shared by the scan and BIM, such as column corners or door-frame corners. Spread at least three fit landmarks across the floor area, and retain additional independent check landmarks away from the fit points. Record which image shows each landmark. Moving chairs and people are poor alignment references.
- Keep connected coverage around turns and doorways. The current photo Walk requires known adjacent stations with gaps at most 5.5 m and elevation difference at most 1.5 m; a video alone does not establish metric station poses.
- If using Cupix while available, retain E57 **with panoramas**, exported scan geometry/point cloud, camera poses, route inventory, floor-plan registration and export coordinate settings. A point-cloud-only E57 cannot supply this photo viewer.

These are archive/coverage requirements for this tool, not camera-specific instructions or a claim that new raw video has already been reconstructed.

## Input cases

| Material available | What can happen now | Additional processing |
|---|---|---|
| E57 spherical panoramas + poses | Extract, validate, create photo viewer package | Review route and scan-to-BIM alignment |
| Extracted `images.json` + image files | Same import without re-extracting E57 | Same review |
| Only original INSV / MP4 video | Preserve original files | Stitch/export imagery and reconstruct metric camera poses; this importer does not implement SfM/SLAM |
| Self-contained GLB in Y-up metres | Copy byte-for-byte and display in intake review | Check units, element identity and sidecars |
| NWD / RVT / IFC | Preserve source as conversion input | Convert using the appropriate existing/export pipeline; do not rename a file to GLB |
| A new building's sensor feed | No automatic reuse of Grimes feeds | Supply equipment IDs, point list, units, timestamps and documented binding evidence |

The existing Grimes NWD extraction scripts remain the conversion path for that source. Another building may have a different Navisworks hierarchy and property schema; inspect it before reusing category/dbId selection rules. This is not yet a universal NWD-to-live-twin upload service.

## Prepare locally

Python 3.11+ with Pillow is required. Run from the repository root. Use a new output folder for every capture. Building and floor IDs allow letters, digits, dash and underscore.

```sh
python3 scripts/capture_import.py prepare \
  --source '/absolute/path/new-floor-with-panos.e57' \
  --output capture-local/grimes-L2-2026-09-20 \
  --building grimes --level L2 --date 2026-09-20 \
  --model '/absolute/path/self-contained-model.glb'
```

The date/path above are examples, not an existing Level 2 capture. `--model` is optional; `--source` can instead be a folder with `images.json` produced by `extract_e57_images.py`. For other buildings change `--building` and use that building's model. New source poses are converted `[x,y,z] → [x,z,-y]` exactly once. **No Grimes 4.572 m offset is added.** New same-building captures do not inherit the accepted L1 transform: an export may have a different origin.

Output includes:

- `project.json`: building/floor/date, photo manifest, optional model, registration initially null, `NO FEED`.
- `panoramas/`: original images with hashes, pose manifest, mobile derivatives no larger than 2048 × 1024.
- `model.glb`: optional byte-for-byte model copy, source hash and node count in report.
- `intake-report.json`: imported/skipped images, source metadata hash (or E57 hash), model hash, missing route/alignment work. The folder hash is for `images.json`; individual image hashes are in the panorama manifest.
- `landmarks.template.json`, `route.template.json`: empty inputs for real evidence; no fabricated sample coordinates.

Invalid image hashes, non-unit quaternions, missing/non-full spherical angular coverage, duplicate GUIDs, invalid paths and invalid GLB container/chunk bounds fail rather than producing a partially ready package. Images without spherical representations or poses are listed as skipped. Existing output folders are never overwritten; input files are not modified.

Serve the repository and open:

```text
http://127.0.0.1:8893/capture-review.html?project=capture-local/grimes-L2-2026-09-20/project.json
```

This review shows imported photos and optional BIM, permits independent model orbit and source-node inspection, and starts without linked cameras. Without a route, use the capture picker; Walk is labelled Route pending. The node card is `NO FEED` and is not a substitute for verified element sidecars. The review is separate from the full Grimes operational viewer.

## Connect a route

Create a JSON file with `edges` containing pairs of exact image GUIDs from the new panorama manifest:

```json
{"edges": [["actual-first-guid", "actual-second-guid"]]}
```

Supply it using `--route /path/route.json` when preparing a **new** output folder. Only connect known walkable neighbors. The importer checks GUID membership and distance bounds; it cannot detect a wall between two cameras. Never assume export order is capture chronology. Raw video reconstruction or camera-track export should eventually supply this graph with stronger evidence.

## Fit and review alignment

Fill `pairs` and `checks` in a copy of `landmarks.template.json`. Every entry has `scan: [x,y,z]` and `bim: [x,y,z]`, both in **Y-up metres**. Use 3+ fit pairs spanning an area and at least one independent check pair; more spatially spread checks are preferable. Do not reuse a fit landmark as an independent check.

```sh
python3 scripts/capture_import.py fit /path/real-landmarks.json \
  --output capture-local/grimes-L2-2026-09-20/registration-candidate.json
```

The solver fits yaw + XYZ translation with scale fixed to 1. It rejects collinear fit points and reports fit RMS/max and independent check errors. It does not solve arbitrary tilt or unit mismatch and never silently scales a model. A small fit residual alone is not surveyed accuracy.

For visual inspection set the package's `project.json` field `registration` to `"registration-candidate.json"`. Reload the review and explicitly enable **Preview provisional landmark alignment**. This sends photo camera motion to the BIM under the candidate transform, with its independent check error displayed. It remains provisional; no automatic promotion into the production viewer occurs. Validate the floor, image heading, several distant landmarks and route, then integrate using that capture's paths and reviewed transform.

## What remains building-specific

The intake is ready for the next file; generalizing the full operational viewer is a separate integration stage. Confirm model axes/units, layer categories, GLB node IDs ↔ sidecars, floor metadata and source-backed sensor bindings. Copying the Grimes meter IDs or apportioned values to another building is prohibited. Maintain measured / modelled / inferred labels.

`capture-local/` is gitignored. Local preparation does not publish indoor images or source files. Keep raw video/E57/NWD in your archive; explicitly select reviewed assets when publishing later.

## Validation

- `python3 tests/test_capture_import.py`: no height inheritance, source preservation, duplicate output rejection, separate building metadata, known-transform solution and degenerate fit rejection.
- `node tests/capture-review.cjs`: configured photo path, route-pending state, independent model preview and provisional position/orientation alignment (Playwright and Three.js environment paths supported).
- Existing `tests/photo-integration.cjs` remains the Grimes Walk/alignment regression.
