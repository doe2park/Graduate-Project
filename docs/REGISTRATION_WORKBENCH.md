# Registration workbench: correcting Scan to BIM alignment

Recorded 2026-10-14. This covers why the Overlay view looked misaligned, what was measured, and how the owner or a collaborator corrects alignment with `registration-workbench.html`, `registration-core.js` and `scripts/registration_fit.py`. All numbers below measure internal consistency between the scan mesh, the photos and the BIM geometry. None of them is surveyed accuracy.

## 1. What was wrong: diagnosis evidence

Evidence and screenshots are in the owner's local `Graduate-Project-media/review/registration/`, summarised in `diagnosis-summary-2026-10-14.json`. Rerun everything with `scripts/registration_diagnostics.py`, a CPU-only tool that needs no browser.

| Possible source | How it was tested | May 6 (accepted ICP) | Sep 17 (provisional) |
|---|---|---|---|
| (c) Overlay projection: FOV, aspect, canvas offset | Headless Chrome overlay: rects, FOV, camera pose | Identical rects (1280×671), FOV 65°/zoom 1 in both, BIM camera = transformed station | Same |
| (b) Per-photo heading or pose | Mesh rendered as a panorama from the station, cross-correlated with the photo | ≤0.26° over 7 stations, mirror rejected | ≤0.37° over 8 stations, mirror rejected |
| (a) Mesh↔BIM floors | Vertical ray at every station | median +0.002 m (ceilings +0.014 m) | median −0.068 m |
| (a) Mesh↔BIM walls | 72 horizontal rays per station → local 2D offset | median 0.062 m, p80 0.091 m | **median 0.282 m, p80 0.343 m** |
| (d) Provisional transform | Rigid model fitted to Sep offset field | n/a | **0.78° yaw** + ~0.1 m |

Findings:

- **Photos are not the problem.** All 100 E57 quaternions are identical because Cupix exports world-aligned panoramas. Heading is not missing. Every tested photo agrees with the textured mesh within 0.4°, and 50/50 photo+mesh blends show no ghosting.
- **The projection is exact.** Both panes share the same rectangle, vertical FOV, aspect and camera pose.
- **September's dominant error is the borrowed May transform.** The Sep GLB root node already carries a 0.70° rotation (and 0.988 scale) relative to May part 1, so applying May's transform leaves about 0.6–0.8° of yaw. That is roughly 0.3 m at 25 m from the centre, or 4–5° in the view at typical ceiling distances. A Sep-specific constrained ICP candidate (yaw −0.593°, t [−34.965, 0.694, −25.443]) cuts the wall offset to a median of 0.131 m (p80 0.232 m) and the floor offset to −0.001 m. It is a **candidate**, not the default; see section 4.
- **May's registration is already good for architecture**: about 6 cm on walls and about 0 on floors and ceilings. The remaining visible differences are at device level. Some ceiling lights and diffusers in BIM sit 0.1–0.2 m from the installed ones in varying directions, while others coincide. Ducts and pipes above the ceiling are drawn behind it (X-ray), so they are not expected to touch visible ceiling features. No global ICP can fix either case.

## 2. Why not just "more ICP"

ICP minimises the distance between *all* scan and BIM surfaces. It can only remove an error that is the same everywhere, namely one rotation and one shift.

- For **September** that is exactly the problem, and one constrained ICP run against BIM halves the error. Running more iterations or reusing May's result does not help. What helps is a fit made **for this capture**.
- For **May** ICP has already converged. Our reimplementation reproduces the accepted transform within 0.006° and 1 cm. The remaining offsets are local and point in different directions (as-built vs design, furniture, scan holes), so more ICP would trade one area against another.
- ICP residuals are nearest-surface distances, not errors at the devices people care about. Accuracy has to be checked at **independent landmarks**, ideally surveyed, that were not used in the fit. The workbench is built around that.

## 3. Owner workflow (about 20 minutes per capture)

Serve the repository (`python3 -m http.server 8765 --bind 127.0.0.1`) and open `registration-workbench.html?capture=2026-09-17` (or `2026-05-06`). On a slower Mac, close other 3D tabs first. The page renders only when something changes.

### Step A: landmark pairs (mode 1)

1. The **Section** slider (default 9.3 m) cuts away upper floors, so you look into Level 1 from above.
2. Click a sharp, fixed feature in the **scan mesh** (left), then the same feature in **BIM** (right). A click is a press without dragging; dragging orbits. Repeat.
   - Good features: column corners, door jambs, wall corners, stair nosings, ceiling diffuser or downlight centres.
   - Avoid furniture, glass, people and scan holes.
3. Make **at least 4 fit pairs** spread over the whole floor: the four corners of the plan, not one room. Mix floor-level and ceiling-level points so height is constrained.
4. Make **at least 2 check pairs** (role "check") in areas *between* the fit points. Checks are never used in the fit. The tool refuses a check that reuses a fit landmark.
5. Leave **RANSAC** on (threshold 0.25 m) so a mis-click is reported as an outlier instead of bending the fit. Press **Fit**.
6. Read the result:
   - **fit RMS** shows how well the chosen points agree. It is optimistic.
   - **LOO** (leave-one-out) predicts each fit point from the others, so it is independent of that point. A single large LOO value means that point is wrong.
   - **checks** are the honest number. Red lines in the BIM view show where the fit puts each scan pick.
   - Rough guide: checks under about 0.10 m are good for visualization. If checks are much worse than LOO, the area is non-rigid, so add pairs there or accept the limit.
7. **Align BIM view to scan** moves the BIM camera through the current fit, which makes the next feature easy to find.

### Step B: per-photo heading (mode 2, optional)

Normally you do not need this step: photo headings already match the mesh. Use it only if a single photo looks rotated after Step A. The right view shows the photo at its station with BIM seen through it, through the current fit.

- Move the **Offset** slider until a column, door or light lines up. Positive values turn the photo content left.
- Or press **Pick photo → BIM pairs**, click a feature in the photo and then the same feature in BIM (two or more times), and press **Solve heading**.
- Large *elevation* residuals point to a station position or height problem, not heading. Fix that with Step A instead.

### Step C: export and preview

1. Press **Save pairs JSON** (your raw clicks) and **Save candidate registration**. The candidate is dated, for example `2026-10-14-landmark-fit.json`. Its status is `landmark-fit-unsurveyed` unless every check pair is ticked "srv". Tick that box only for checks whose BIM coordinates come from an independent survey.
2. Move the candidate into the path shown: `scan-assets/captures/<date>/registration-candidates/` for September, `alignment-analysis/candidates/` for May.
3. Preview it in Overlay:
   `scan-compare.html?view=overlay&capture=2026-09-17&registration=scan-assets/captures/2026-09-17/registration-candidates/<file>.json`
   - The status line reads **PREVIEW candidate · … · not the accepted registration**.
   - Toggle the parameter off and on to compare before and after. A candidate for another capture, an unknown status or a scale other than 1 is rejected visibly, and the default is shown instead.
4. Reproduce it from the command line for papers and reviews:
   `python3 scripts/registration_fit.py fit <pairs.json> --output <new dated file>`
   The JS and Python implementations give the same numbers on the shared test fixture, and the pairs hash in the candidate matches.
5. Optional ICP refinement, seeded by your landmark fit (the archive method, yaw+XYZ only):
   ```
   node scripts/decode_bim_soup.mjs /tmp/arch.f32 buildings/grimes/grimes-arch.glb --ymin 3 --ymax 12
   python3 scripts/registration_fit.py icp --capture 2026-09-17 --init <landmark candidate> \
     --bim-soup /tmp/arch.f32 --bim-source buildings/grimes/grimes-arch.glb --pairs <pairs.json> --output <new dated file>
   ```
   Passing `--pairs` re-evaluates your check pairs under the ICP result. Keep the ICP result only if the checks do not get worse.
6. Independent wall/floor check for any candidate:
   `python3 scripts/registration_diagnostics.py --mode walls --capture 2026-09-17 --bim-soup <arch+structural soup> --stations $(seq 0 4 99) --registration <file> --out <dir>`

### Publishing after review

The CLI and the page refuse to write `alignment-analysis/accepted-registration.json` or any capture `registration.json`, and they never overwrite an existing candidate. To promote a reviewed candidate, make a separate, reviewed commit:

1. Copy the transform into the capture's registration file.
2. Keep the original `status` vocabulary that `scan-compare.html` expects, or add the new status there in the same commit with a test.
3. Record the candidate path, its check residuals and the date in `docs/CAPTURE_UPDATE_*.md` or `docs/SCAN_BIM_REGISTRATION.md`.

Promotion is an owner decision. Do not do it automatically.

## 4. September candidate shipped with this change

`scan-assets/captures/2026-09-17/registration-candidates/2026-10-14-icp-arch.json` (status `icp-refined-unsurveyed`):

- Seeded from the provisional transform, against BIM architecture at 4.7–10 m.
- Held-out nearest-point median 0.161 → 0.143 m, p80 0.420 → 0.379 m.
- The wall-ray check is in the `walls-*.json` sidecars next to it: median local offset 0.282 → 0.131 m, floor −0.068 → −0.001 m.

Visually, the BIM linear light at station 57 moves onto the real light strip. It has **not** replaced `registration.json`. Preview it with the URL above, and ideally confirm it with workbench check pairs before promoting it.

## 5. Files and tests

- `registration-workbench.html`: the UI described above. It loads mobile scan GLBs, BIM architecture and lighting, and photo derivatives only.
- `registration-core.js`: pure maths. Closed-form yaw+XYZ fit, exhaustive deterministic RANSAC, leave-one-out, heading solve, export schema, path and candidate validation. Shared by the workbench and `scan-compare.html`.
- `scripts/registration_fit.py`: Python mirror (`fit`, `icp`).
- `scripts/registration_diagnostics.py`: heading and wall diagnostics.
- `scripts/decode_bim_soup.mjs`: read-only Draco decoder for diagnostics. It never rewrites BIM GLBs.
- `scan-compare.html` `?registration=` loads the candidate preview. `scan-photo.html` applies a candidate's `stationHeadingOffsetsDegrees` (bounded to ±180°, about +Y).
- Tests:
  ```
  node --test tests/registration-core.test.cjs tests/registration-preview.test.cjs
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_registration_fit.py
  ```
  They cover synthetic recovery, RANSAC outlier rejection, leave-one-out, heading solve, export schema, refusal to overwrite accepted files, safe preview paths, and JS/Python agreement.

## 6. Slide summary: "How we correct alignment"

1. Measure before fixing. Photos, overlay projection and mesh were checked separately: photo headings match the mesh within 0.4°, and the projection is exact.
2. September used May's alignment. Its scan is rotated about 0.7°, so services drifted by about 0.3 m. A capture-specific ICP halves that (median wall error 0.28 → 0.13 m).
3. May's alignment is already within about 6 cm at walls and floors. The remaining differences are design-vs-installed devices and above-ceiling services, which ICP cannot fix.
4. The workbench: click 4+ matching points in scan and BIM, fit rotation + shift (scale fixed), reject mis-clicks with RANSAC, and judge the result only on independent check points.
5. Every result is a new dated candidate that can be previewed side by side in Overlay. Nothing replaces the accepted alignment without review.
6. Accuracy claims need surveyed check points. Until then, residuals describe internal consistency, not survey accuracy.

## 7. Align in Overlay (temporary whole-BIM nudge)

`scan-compare.html` Overlay view has an **Align…** button next to As-built. It changes only an in-memory copy of the loaded registration. BIM geometry, GLBs and every registration file stay untouched. Because one rigid transform moves the whole model, every designed relative distance is kept. Matching one element moves everything else with it.

- **Move / rotate** moves the BIM in camera-relative directions (left/right, away/near, up/down) in 1, 5 or 20 cm steps, and turns it ±0.1° or ±0.5° about the vertical axis through the current BIM camera. The maths is `RegistrationCore.nudgeRegistration`. The registration maps the camera, so moving the BIM by +v maps the camera by −v: θ' = θ − φ and t' = R(−φ)(t − c) + c − v. Keys work only while the panel is open and focused: Shift+arrows, Shift+PgUp/PgDn, `[ ]` and `{ }`. Plain WASD/arrows still walk.
- **Match elements** (360° photos only): Add pair → click a BIM element in the overlay, or press *Use lens centre* → click where it really is in the photo. The BIM pane returns the world-space raycast point (`hit.point`, optional `point` in `grimes-lens-pick`). The photo pane returns the clicked ray in the scan frame (`grimes-photo-pick`). The scan point is placed on that ray at the same distance from the station as the picked BIM point. This is a depth *assumption*. `RegistrationCore.fitFromElementPairs` solves translation only for 1 pair or for pairs < 1 m apart horizontally, yaw + translation for well-spread pairs, and uses RANSAC for 4+ pairs.
- While the alignment is modified, the page status and a badge say **"Manual alignment preview · not saved · not surveyed"**. The working copy is kept per capture in this browser's localStorage until *Reset to loaded registration*. The page still works without localStorage.
- **Export candidate JSON** downloads `YYYY-MM-DD-manual-nudge.json` (`grimes-registration-candidate/1`, status `manual-nudge-unsurveyed`, `method.base` = the loaded file, heading offsets carried over, plus pairs if any). Save it under `scan-assets/captures/<date>/registration-candidates/` (May: `alignment-analysis/candidates/`) and preview it with `scan-compare.html?view=overlay&capture=<date>&registration=<path>`. It is never a substitute for workbench check points or a surveyed registration, and promotion remains a separate reviewed commit.
- Tests: `node --test tests/align-nudge.test.cjs`.
