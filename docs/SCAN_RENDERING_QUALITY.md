# Scan rendering quality investigation — 2026-09-11

## Confirmed observations

The authenticated Cupix SiteView for Level 1 / May 6 shows holes and distorted surfaces in its aerial textured mesh. Switching the same active station to first-person shows a continuous photographic corridor. Capture Data identifies panorama 83697766, captured with Insta360 X4. The archived 4096 × 2048 panorama of that ID depicts the same corridor. Thus the clear first-person appearance must not be treated as evidence that the exported mesh contains equally complete geometry.

The public comparison had an additional rendering defect: its quality policy evaluated the iframe viewport. A 1386-pixel desktop window produces panes under 768 pixels, selecting 512-pixel mobile texture derivatives on desktop. The fix evaluates the same-origin top-level window; cross-origin embedding falls back to its own window. Coarse-pointer devices retain the memory-constrained policy. This fixes unintended texture downsampling; it does not reconstruct missing geometry.

## Validation

- Regression reproduction failed on a 680-pixel pane in a 1386-pixel desktop window before the fix.
- Desktop split, phone, tablet and narrow desktop policy cases pass after the fix.
- Chrome local comparison: scan frame reports `data-quality=full` and `data-scan-parts=2`.
- Existing viewer tests: 14 passing.
- Registration transform, camera synchronization and all GLB files remain unchanged.

## Photographic viewing requirements

A faithful Cupix-independent indoor view needs captured panoramas at their actual stations, with verified image orientation and conversion into the exported-mesh frame, followed by the accepted mesh-to-BIM registration. One archived panorama and 217 position records do not establish a complete calibrated panorama tour. A recorded viewer camera matrix is the viewing direction at one instant, not automatically the equirectangular image orientation. Do not use it as an unverified image calibration, or project one image from arbitrary walking positions. Retain the geometric comparison until those bindings are verified.
