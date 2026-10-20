# October 18 Grimes Level 1 capture (prepared 2026-10-19, not yet published)

Third capture date in `scan-compare.html` and `scan-xr.html`, after May 6 (registered baseline) and Sep 17. Package:
`scan-assets/captures/2026-10-18/` (109 MB, 203 files: 100 blurred 4096 x 2048 panoramas, 100 mobile 2048 x 1024
derivatives, manifest, registration, provenance). No mesh/GLB: the mesh view is retired. Gaussian remains May-only.

## Source and export

- Cupix SiteView, Level 1, Oct 18, 2026. E57 export With Pano, Use Coordinates from Source Data disabled (project
  coordinates, the same frame as May 6 and Sep 17). Source E57 name, bytes and sha256 are in `provenance.json`;
  companion E57s and the mesh GLB are listed there but not published. Raw files stay in the owner's local
  `Grimes_360_Pilot/capture-20261018` archive; the intake package is `capture-local/grimes-L1-2026-10-18/`.
- One source video (`VID_20261018_141325_00_474`); 100 exported images. Not a claim of complete capture inventory.

## Privacy

Cupix exports blur bystander faces, but the camera operator appears at the nadir. Before packaging, every panorama
went through `scripts/raw360_pipeline.py privacy` (YuNet face score 0.85, faces wider than 25 degrees dropped, YOLOX
person score 0.4, 11 perspective crops, nadir cone 35 degrees always blurred, review flag when nothing is detected
below -50 degrees). Report totals: 1 face, 444 raw person detections (about 130 distinct), all 100 images with a
detection, 0 images flagged, blurred pixel fraction 19.4-23.9 %. Published files are the blurred copies; their
sha256 is `sha256`, the original E57 image hash is `originalSha256`. Automatic detection can miss people; the
contact sheets and report must be reviewed by a person before publishing (manualReviewRequired).

## Route and coordinates

Stations are sorted by video frame number. The Sep 17 rule (consecutive frames, distance <= 5.5 m, height difference
<= 1.5 m; it reproduces Sep's 95 edges exactly, see `tests/test_capture_update.py`) gives 97 edges and two gaps
(87-88: 11.5 m; 98-99: 5.51 m). Gaps are not bridged. Poses convert E57 Z-up to Y-up `[x,z,-y]` without an
elevation offset. Built by `scripts/build_capture_update.py`.

## Registration: provisional

`registration.json` copies the accepted May transform with status `project-frame-provisional`, exactly like Sep 17.
An independent ICP check of the companion Oct 18 export, reported from a separate session, found the frame within
0.15 degrees and 4 cm of the accepted May registration. Its evidence file is not in this package. This is internal
consistency between exports, not surveyed accuracy. Every UI label says provisional.

## UI

- `scan-compare.html?capture=2026-10-18`: picker lists Oct 18 / Sep 17 (both "Provisional") / May 6. The no-parameter
  default is unchanged (Sep 17).
- `scan-xr.html?capture=2026-10-18`: the menu Capture button cycles May 6 -> Sep 17 -> Oct 18 -> May 6 (default May 6);
  Oct 18 shows `PROVISIONAL alignment (not surveyed)`.
- `registration-workbench.html` is not wired for Oct 18 (it needs a published mesh).
