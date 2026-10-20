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
  Level 1 -> Level 2 -> Level 3. The BIM pane's architectural interior is Level 1 only.

Tests: `tests/test_multifloor.py`, `tests/multifloor-viewer.test.cjs`, headless `tests/multifloor-walk-smoke.cjs` (screenshots in
`work/web-matrix/floors/`; `VIEW=overlay` for the overlay).

## Gaussian retraining (prepared, not run)

`scripts/multifloor_review.py upper` built `capture-local/grimes-UPPER-2026-10-18/` (video B only, original unblurred panoramas, Level 1 scan
frame, Oct 18 provisional registration copy, no seed mesh because the Ground `scan.glb` mixes both videos). Preset entry to add (not added):
`work/multifloor/2026-10-18/gaussian-upper-preset.json`, then `python scripts/run_gaussian_pipeline.py --capture 2026-10-18-upper --mask-nadir`.
Expected: no more superimposed Level 1 / Level 3 images, so the streaking should go; quality stays limited by 32 sparse views and random
initialisation. Not measured.
