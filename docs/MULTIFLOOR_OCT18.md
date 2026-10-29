# October 18 upper floors: diagnosis, placement and multi-floor photo walk (2026-10-20, local, uncommitted)

Goal: walk naturally from Level 1 up the atrium stairs to Level 2 and Level 3 in the Oct 18 360° photo mode.
Everything below is **provisional, not surveyed**. Nothing is published; the preview package lives in ignored `capture-local/`.

## Diagnosis

The Cupix "Ground Level" export (`capture-local/grimes-GROUND-2026-10-18`, 100 stations) contains **two videos** (E57 image names):

| Video | Stations | Content |
|---|---|---|
| `VID_20261018_141325` (A) | 68 | the Level 1 walk (same video as the Level 1 export; 35 byte-identical, 33 other frames) |
| `VID_20261018_153400` (B) | 32 | starts on Level 3 (frame 5), Level 3, atrium stair down, Level 2, stair foot on Level 1, back to Level 2 |

- The height split that made `grimes-L3-2026-10-18` put all 68 Level 1 frames above 3.5 m into "L3": it removed only the 35 byte-identical ones, so
  the L3 package is **33 Level 1 frames + 19 video B frames**; Gaussian zones `l3-a` had 20/36 and `l3-b` 15/18 Level 1 images. Video B is not
  "connected through Level 1 connector photos": it has none (it starts on Level 3).
- Cupix placed video B in an arbitrary pose: its Level 3 floor at Cupix y 4.78 (Level 1 floor 4.58), north of the building
  (BIM z -20 to -53 with the borrowed May transform), overlapping Level 1 coordinates. Training Level 1 and Level 3 images at overlapping
  coordinates explains the smeared L3 Gaussians (PSNR 13.5/14.1). Video B's **internal** trajectory is consistent.
- Internal consistency (essential matrix on bearings, consecutive panoramas with >= 40 inliers): video B 13/31 pairs, rotation deviation
  median 0.53 deg (p90 1.2), translation-direction error median 0.65 deg (p90 2.9), including the stair descent; video A 47/67 pairs, 0.33 / 0.52 deg.
  Video B's Level 3 to Level 2 floor drop is 4.88 m (BIM slabs 4.9 m).

## Placement (method)

1. `scripts/multifloor_link.py link` (raw360 venv, OpenCV): SIFT on the equirects, cross-video matches of all 32 video B panoramas against
   all Level 1 panoramas. 5 pairs survive (Level 1 stations 634/635/636/638 see 812 at the atrium stair foot; 634 sees 809):
   relative yaw 81.56 deg (spread 0.17 deg, tilt < 1.3 deg). The four rays to 812 intersect within 1.5-4.2 cm; the 809 ray is an
   independent check: 0.25 m miss at 4.5 m (3.2 deg). Scale fixed at 1 (Cupix metric). Photo-only vertical check: Level 3 floor lands
   at 13.78 m in the Level 1 frame vs 13.68 m expected from BIM slab spacing (+0.10), Level 2 at 8.90 vs 8.78 (+0.12).
2. `scripts/multifloor_review.py register`: composed with the Oct 18 provisional (borrowed May) registration, the photo-only placement already
   fits BIM Level 2/3 surfaces at held-out median 0.126 m (95 % within 0.5 m). A yaw+XYZ trimmed ICP of video B's own E57 points (points near
   B stations and > 4 m from A stations) moves it 0.19 m / 0.22 deg (stations: median 0.23 m, max 0.29 m); held-out median 0.112 m
   (Level 2 0.104, Level 3 0.126). BIM floor ray-cast under each station: all 17 Level 3 stations above the 14.4 m BIM floor
   (camera 1.99-2.16 m above it), 11 Level 2 stations above 9.52 m (1.90-2.10 m), 4 stair stations on stair geometry. Camera height is
   about 2.0 m in both videos (stick held high), not 1.5 m.

Outputs: `capture-local/grimes-L3-2026-10-18/registration-candidate-upper-walk-2026-10-20.json` (status `candidate-not-surveyed`; applies to
video B only), figures in `capture-local/grimes-L3-2026-10-18/registration-review/multifloor-2026-10-20/` (use `figures-v2/`: plan before/after
on BIM sections, elevation before/after with slabs, video B points over BIM sections), link evidence `work/multifloor/2026-10-18/link.json`.

## Multi-floor photo walk (local web viewer)

- Privacy: video B panoramas blurred with `scripts/raw360_pipeline.py privacy` (same defaults as Level 1) into
  `capture-local/grimes-UPPER-2026-10-18-blurred/` (0 faces, 261 raw person detections, ~94 distinct, 0 flagged). Manual review still required.
- `scripts/multifloor_review.py package` builds `capture-local/grimes-oct18-floors/` (132 stations): the 100 published Level 1 stations
  unchanged (symlinks, same positions and route), plus video B moved into the Level 1 scan frame (headings rotated), so the existing Oct 18
  provisional registration applies to every station. Edges: Level 1 route as before; video B consecutive frames = `route` (<= 7.7 m, rise <= 1.5 m)
  or `stairs`; non-consecutive same-floor links only when the panoramas verify each other (`route-visual`) or no BIM wall lies between them
  (`link-bim-clear`, none survived here); 812 to Level 1 stations 634/636 = `link-inferred`. Per-edge kinds are in `edgeKinds`.
- `scan-compare.html?capture=2026-10-18&floors=all` (localhost only; a "Levels 1-3 (local)" button appears next to the Oct 18 date when the
  package exists): arrows/WASD follow the route, stair edges accept larger rises, **PgUp / PgDn** (and pad ⇧ ⇩ on touch) take the stairs,
  the photo label shows Level 1 / Stairs / Level 2 / Level 3, and the BIM pane's element floor follows the camera height
  (`grimes-floor` message -> `setElementFloor`). The capture picker itself is unchanged; May/Sep/Oct 18 Level 1 behave as before.
- Not walk-connected: Level 3 stations 740-772 (11, west/north) - a 75-frame gap (772 -> 775) and a BIM wall between 744/747 and 775; reach them
  with the station picker. The Level 1 -> Level 3 stairs were not filmed (video B starts on Level 3), so the walk goes up the atrium stair
  Level 1 -> Level 2 -> Level 3. The BIM pane's architectural interior follows the element floor since 2026-10-27 (below).

Tests: `tests/test_multifloor.py`, `tests/multifloor-viewer.test.cjs`, headless `tests/multifloor-walk-smoke.cjs` (screenshots in
`work/web-matrix/floors/`; `VIEW=overlay` for the overlay).

## Gaussian retraining (prepared, not run)

`scripts/multifloor_review.py upper` built `capture-local/grimes-UPPER-2026-10-18/` (video B only, original unblurred panoramas, Level 1 scan
frame, Oct 18 provisional registration copy, no seed mesh because the Ground `scan.glb` mixes both videos). Preset entry to add (not added):
`work/multifloor/2026-10-18/gaussian-upper-preset.json`, then `python scripts/run_gaussian_pipeline.py --capture 2026-10-18-upper --mask-nadir`.
Expected: no more superimposed Level 1 / Level 3 images, so the streaking should go; quality stays limited by 32 sparse views and random
initialisation. Not measured.

## Per-floor previews and raw INSV upper floors (2026-10-27, local, uncommitted)

- Raw `VID_20261018_153400_00_477.insv` (video B, 463 frames) is a single `_00_` file holding both lenses as video streams 0/1,
  already upright, no IMU/frame-time records, and a trailer calibration for a 16000x6000 photo mode. `scripts/raw360_pipeline.py probe
  --dual-stream <file> --lens-ops none,none --fov 196.6` (Sep 17 fit) handles it; frame selection is chunked (ffmpeg's `select`
  expression fails with > ~100 terms). Cupix name `(N)` = 0-based frame N (image correlation, 6 frames).
- 143 keyframes, fisheye-rig incremental SfM: submodels of 78 / 39 / 17 panoramas. `scripts/multifloor_review.py place-raw` fits each
  submodel (levelled 4-DoF similarity) to the Cupix video-B stations of `grimes-oct18-floors` by frame number: fit median 0.086 / 0.040 /
  0.041 m, leave-one-out 0.093 / 0.057 / 0.090 m (16 / 5 / 3 matches); headings within ~1 deg of the Cupix panoramas (20 frames). Frames
  further than 15 frames from a submodel's matches are dropped (an unsupported tail came out 180 deg off). 108 placed; frames 6-31 and
  136-213 (Level 3 west/north) unplaced; `--relaxed` and a targeted 110-230 run gave broken fits (6.6-9 m) and were not used.
  Camera height above the BIM floor comes out 1.8-2.2 m on both floors, independently of the Cupix ICP.
- `VID_20261018_153237_00_476.insv` (542 frames, audio): camera held near the face and tilted at two spots by the atrium; no walk. Not used.
- `scripts/multifloor_review.py floors` builds `capture-local/grimes-L2-2026-10-18-v2` and `grimes-L3-2026-10-18-v2` (54 + 54 blurred
  panoramas, `--raw-placed`; the 32-panorama Cupix version is `grimes-L{2,3}-2026-10-18-cupix32`) and the training package
  `grimes-UPPER-2026-10-18-raw477`. Stair stations go with the floor at the top of their flight. Privacy:
  `capture-local/grimes-UPPER-2026-10-18-raw477-blurred` (automatic, manual review required).
- Viewer: `scan-compare.html?capture=2026-10-18&floors=L2` / `floors=L3` (localhost only; Floor menu next to the Levels 1-3 button).
  Tests: `tests/multifloor-viewer.test.cjs`, headless `tests/multifloor-floor-shots.cjs` (screenshots `work/web-matrix/floors/floor-*.png`).

## Per-floor BIM interior (2026-10-27, uncommitted)

- `scripts/prepare_interior_levels.py` (rules of the 2026-09-10 Level 1 slicer `Grimes_360_Pilot/scripts/prepare-interior.py`, read-only
  source `Grimes_360_Pilot/interior/source.glb` + `source.elements.json`) writes `interior/{furniture,enclosure,floors,ceilings}-l2.*` and
  `-l3.*`. Draco bufferViews copied byte-verbatim; output payload set == source payload set, asserted per group. It regenerates Level 1
  in memory and refuses to continue unless it equals the published `-l1.*` (GLB bytes identical, sidecar content identical).
- Floor = viewer-frame height slice (walls / mullions have no Revit level in the source). Furniture/casework by bounding-box centre in
  `[sliceY0, sliceY1)`; walls/doors/mullions, floors/stairs/railings and ceilings when their box overlaps the slice, clipped to the slice at
  runtime, so a stair flight or wall crossing a slab is listed on both floors. Slices: L1 `[4.3, 10.3]` (legacy, unchanged), L2
  `[9.23, 14.3]`, L3 `[14.13, 19.3]` (slab top - 0.27 m to next slab top - 0.1 m; L3 stops under the roof penthouse).
  Cross-check with the Revit level where one exists (`revitLevelCheck`): L2 furniture 971/971, L3 830/830 on the same floor.

| Floor | furniture | enclosure | floors | ceilings | GLB total |
|---|---|---|---|---|---|
| L1 (legacy) | 2,163 (11.0 MB) | 2,289 (3.8 MB) | 424 (3.3 MB) | 75 (0.13 MB) | 18.3 MB |
| L2 | 982 (6.6 MB) | 5,213 (2.2 MB; 4,585 mullions, 626 walls) | 243 (1.7 MB) | 27 (0.05 MB) | 10.6 MB |
| L3 | 834 (3.3 MB) | 9,019 (2.7 MB; 8,570 mullions, 448 walls) | 42 (0.28 MB) | 47 (0.08 MB) | 6.3 MB |

- `interior/manifest.json`: legacy fields (schema `grimes-interior/1`, scope, frame, sliceY, sourceSurvival, groups = Level 1) unchanged;
  added `levels.{L1,L2,L3}` (sliceY, slabTopY, scope "... source design geometry, not surveyed as-built", groups with sha256 of GLB /
  sidecar, Draco payload-set digest, revitLevelCheck) and `provenance` (source hashes, assignment rules).
- `scan-bim.html`: one floor's interior in memory. Level 1 uses the legacy fields, so May / Sep / Oct 18 Level 1 views load the same four
  files. `setElementFloor` (Element floor menu, scan-compare `grimes-floor`) to L1/L2/L3 swaps the interior: the old floor is disposed, the
  new one loads lazily; a `run` token makes in-flight loads drop their result. All floors / other floors keep the current interior. In
  Overlay the interior stays unloaded until the Overlay is turned off. The Overlay wall occluder uses the element floor's walls
  (All floors / L1 = `enclosure-l1` as before; L2 / L3 their own; other floors none). Status line and scan-compare header say
  "source design geometry, not surveyed as-built".
- Known gaps: the Level 1 slice's 10.3 m top is 0.8 m above the Level 2 slab, so `furniture-l1` also holds 915 Level 2 furniture elements
  (clipped at runtime) and `floors-l1` some Level 2 slabs - published, left unchanged. Thin in the source model itself: L2 ceilings (27),
  L3 floors (18 Floors elements; 42 in the group), L3 stairs (2). Cancelled loads are not aborted (the download finishes, the result is
  discarded).
- Tests: `tests/test_interior_levels.py`, `tests/interior-levels.test.cjs`; headless `tests/multifloor-floor-shots.cjs` now asserts the
  floor's interior (Compare) / walls occluder (`VIEW=overlay`), screenshots `work/web-matrix/floors/floor-L{2,3}-*.png` and
  `floor-L{2,3}-overlay-*.png`.

## Cupix-free route for the Oct 28 re-scan (2026-10-27, local, uncommitted)

`scripts/raw360_bim.py` + `scripts/capture_upper_floors.py` place raw INSV SfM in the BIM frame without Cupix. It uses photo links to registered Level 1 panoramas and between submodels, then point-to-plane ICP to BIM and visibility / camera-height / wall checks.
A dry run on video 477 with Cupix withheld gave `capture-local/grimes-L2-2026-10-18-nocupix` (54 stations) and `-L3-` (25 stations); view them with `scan-compare.html?capture=2026-10-18-nocupix&floors=L2`.
Against the Cupix-based v2 packages, 79 frames differ by a median of 0.09 m (max 0.31 m). The Level 3 east loop (frames 39–178) could not be placed without Cupix: there is no Level 1 link, and SfM breaks at frames 179–215.
Method and numbers: `docs/RAW360_PIPELINE.md`. Field protocol: `docs/FIELD_CAPTURE_L2_L3.md`.

## Level 2 and Level 3 published (2026-10-28)

- `scripts/publish_upper_floors.py` writes `scan-assets/captures/2026-10-18/floors/L2/` and `L3/` (54 + 54 stations; `--check` rebuilds
  in memory and compares). Each package: `panoramas/f000NNN.jpg` (4096 x 2048, byte copies of the approved
  `capture-local/grimes-UPPER-2026-10-18-raw477-manual` set), `panoramas/mobile/` (2048 x 1024 LANCZOS, JPEG quality 88, made from the
  published file), `panoramas/manifest.json` (stations, route and floor assignment from the v2 package; `sha256` / `mobileSha256` of the
  published files; `status: published-provisional`) and `provenance.json` (per-file hashes, privacy record, placement, what is not published).
- Privacy: automatic blur (strict: person score 0.15, crop 1536; `grimes-UPPER-2026-10-18-raw477-blurred-v2/privacy-report.json`) +
  1,280 manual blur boxes (L2 684, L3 596: 1,241 from the review plus 39 added the same day for small distant people on the far
  balcony / atrium in 36 images) after manual review of every image; publishing approved by the owner on 2026-10-28. Not a claim
  of full anonymisation. The v2 packages still display the older automatic blur (`-raw477-blurred`), which missed seated people: never publish it.
- Placement, stated honestly: the images are raw-video frames of `VID_20261018_153400_00_477` (not a Cupix export), but the v2 positions are
  local SfM fitted by frame number to the Cupix-placed stations of the same video (`placementCupixFree: false`). The Cupix-free dry run
  differs by a median 0.09 m (max 0.31 m) over 79 frames. Stations are in the Level 1 scan frame; `positionBIM` equals the published Oct 18
  provisional registration applied to `position` (checked: 0.0 m difference on all 108), so `registration.json` is shared. Provisional, not surveyed.
- Viewer: `scan-compare.html?capture=2026-10-18&floors=L2` / `floors=L3` on every host (also localhost, which now opens the published
  packages instead of v2). A Floor picker (Level 1 / Level 2 · provisional / Level 3 · provisional) sits next to the Oct 18 date; the scan
  header reads "Level N · provisional, not surveyed" with the method in its tooltip; the BIM element floor and interior follow the photo
  floor. `floors=all`, the Oct 18 Gaussian, meshes and the raw477 Gaussian stay local.
