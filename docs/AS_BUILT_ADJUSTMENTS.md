# As-built position adjustments (manual, not surveyed)

The BIM shows the design position of each element. At Grimes some installed lights, diffusers and junction
boxes sit 10–20 cm from their BIM position. You can record where an element was actually installed: open the
scan comparison, select the element and nudge it until it matches the captured photo or mesh. Each adjustment
is a visual match by one person. It is labelled **manual, not surveyed** everywhere it appears.

## What changes and what does not

- Adjustments live in one new sidecar file, `buildings/grimes/as-built-adjustments.json`. It ships empty.
- GLBs, Draco bytes, GLB node names and `*.elements.json` sidecars are **never** modified. The adjustment is
  applied only at render time, in the BIM pane of `scan-compare.html` (`scan-bim.html`).
- The "Design (BIM)" button restores the exact original geometry (bit-exact; tested).
- The registration is not changed. If every element on a floor is off in the same way, the scan registration
  is the problem. Use `registration-workbench.html` for that (`docs/REGISTRATION_WORKBENCH.md`), not this tool.

## Owner steps

1. Open `scan-compare.html?view=overlay` (Lens style, the default). Pick the capture date. For photos, go to
   the station you want to use as evidence, for example May station 90 or September station 57.
2. Click **As-built…** in the header. Enter your initials (2–4 letters). They are remembered in this browser.
3. Select the element:
   - **Overlay:** hold the lens on the element until its info card appears, then click **Select element under lens**.
   - **Compare view:** with the panel open, click the element in the BIM pane.
   The selected element gets a gold box.
4. Nudge it with **−5 / −1 / +1 / +5 cm** for X, Z and Y (height), and **±1° / ±5°** for yaw (about the
   element's own vertical axis). Keyboard, with the panel focused: ←/→ X, ↑/↓ Z, PgUp/PgDn height, `[` `]` yaw,
   Shift = 5 cm / 5°. The first nudge switches the view to **As-built adjusted**. A magenta box shows the adjusted
   position, a grey box shows the design position and a line joins them. The badge reads
   "AS-BUILT ADJUSTED · manual, not surveyed".
5. Optionally add a note (what you matched, e.g. "centre of light strip"). Evidence (capture date, scan mode,
   station, registration file) is recorded automatically from the current view.
6. Switch between **Design (BIM)** and **As-built adjusted** to check before/after.
7. Click **Export JSON**. Replace `buildings/grimes/as-built-adjustments.json` with the downloaded file, run
   `python3 scripts/check_as_built.py` and commit the file. Until then edits exist only as a draft in this
   browser (the status line says "local draft"). **Load JSON** re-imports an exported file.

`?asbuilt=1` opens the comparison in As-built mode. The default is Design (BIM).

## File format (`as-built-adjustments/1`)

```json
{"_schema": "as-built-adjustments/1", "frame": "bim-pane-world-y-up-m", "_doc": "...", "updated": "2026-10-14T…Z",
 "adjustments": [{
   "element": {"id": "171361", "layer": "lighting", "name": "_TEE_Linear Fixture", "type": "Linear fixture", "system": "Lighting"},
   "translation": [0.12, 0.0, -0.04], "yawDegrees": 1.0, "pivot": [12.3456, 8.09, -4.321],
   "evidence": {"captureDate": "2026-09-17", "scanMode": "photo", "stationIndex": 56, "stationLabel": "57",
                "registration": "scan-assets/captures/2026-09-17/registration.json"},
   "author": "YC", "timestamp": "2026-10-14T18:00:00.000Z", "note": "centre of strip", "status": "manual-unsurveyed"}]}
```

- `element.id` + `element.layer` identify the element. `id` is the exact sidecar key, which is the GLB node name. The
  layer is needed because ids can repeat across layers. `name/type/system` are an informative copy. The check
  script warns if they differ from the sidecar, and the sidecar wins.
- `translation` is in metres in the BIM pane world frame (Three.js, Y up, the same frame the scan registration
  targets). X and Z are horizontal and Y is height. Each record must stay within 1 m, and yaw within ±45°.
- `pivot` is the centre of the element's design bounding box, recorded on first apply. The transform is
  `T(pivot + translation) · Ry(yaw) · T(−pivot)`.
- `stationIndex` is 0-based (manifest order). `stationLabel` is the 1-based number shown in the photo pane.
- `status` is always `manual-unsurveyed`.

## Research summary

`python3 scripts/check_as_built.py` validates the file against the layer sidecars. It also reports the mean and
max offset, mean horizontal and vertical offset, and mean |yaw|, grouped by system ("design vs installed").
Use `--json` for a machine-readable report. Report these numbers as manual visual corrections relative to the
current registration. They are not surveyed as-built accuracy. They include registration error: September uses
a provisional alignment, and May's internal residual is about 0.13 m.

## How the geometry is moved (design notes)

The runtime draw-call tier has two kinds of meshes (`buildElementRenderTier`).

- **Instanced** (repeated identical geometry): each element owns one or more instances. Only those
  instance matrices are replaced by `M · original`.
- **Merged** (bounded batches per level/material/type): each element owns compacted vertex ranges, and **no
  vertex is shared between elements**. Only those ranges (positions, normals, tangents) are rewritten as
  `M · original`. The index buffer and the triangle-range → element map stay unchanged, so click and lens
  picking still resolve the same element id. Bounding volumes are recomputed for raycasting.

Each target's original Float32 data is snapshotted on first use. Every nudge is recomputed from that snapshot,
so nudges never accumulate float error. Design mode copies the snapshot back, bit-exact. A separate proxy mesh
(the alternative) would duplicate geometry, need the original range hidden, and break the one-mesh-per-pick
identity. Rewriting a copy of the vertex range in place keeps one geometry and one identity.

Code: `twin/as-built.js` (pure, shared), `scan-bim.html` (applies it, draws the outlines), `scan-compare.html`
(panel, export/import). Tests: `tests/as-built.test.cjs`, `tests/as-built-ui.test.cjs`, `tests/test_check_as_built.py`.

## Limitations

- Only the comparison BIM pane applies adjustments. The main viewer (`grimes-bim-viewer.html`) still shows the design position.
- No drag-on-plane yet. Use buttons or keys.
- In Overlay the keyboard works only while the panel has focus. The scan pane uses the arrow keys to walk.
- On phones the fire layer is not loaded in Overlay, so fire adjustments wait as "pending".
