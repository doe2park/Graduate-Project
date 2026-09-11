# Captured panorama / BIM comparison — 2026-09-11

## What changed

The comparison now opens **360° photos** by default. These are actual captured images recovered from Cupix's **Aerial → 3D Display Settings → Export → Point Cloud → E57 → With Pano** export, not textures stretched over the imperfect reconstructed mesh. The previous **3D mesh** remains available in the scan selector for free movement. Neither mode requires Cupix at runtime.

The finished export produced three E57 files. One contains 100 spherical images with full image poses; the other two contain point-cloud data without images. All 100 JPEGs are 4096 × 2048. Raw E57 files, XML and extraction metadata are archived locally under the Grimes_360_Pilot/source-recovery directory. Original camera videos have **not** been recovered. Archived source filenames include `VID_20260506_145040_00_472.insv(12).jpg`, consistent with images extracted from an Insta360 video; this filename alone does not recover the video or establish its processing pipeline.

The inventory contains 217 positions, but this export contains 100 panoramas. Do not describe this as a complete 217-image backup. Every inventory position is within 1.884 m of an exported photo station (median 0.732 m); this checks proximity along the recorded route, not complete room/surface coverage or surveyed accuracy.

## Coordinate and image binding

1. E57 image GUID `pano_<id>` identifies the captured image. Match that ID to the archived Cupix inventory.
2. E57 image poses already include the Level 1 elevation. Relative to the API position, E57 translation is `[x, y, z + 4.572]`; maximum observed position discrepancy across the 100 matches is 0.0000078 m. This is coordinate consistency, not positioning accuracy.
3. Convert E57 Z-up to the scan viewer's Y-up with `W = rotationX(-90°)`, so `[x,y,z] → [x,z,-y]`.
4. E57 spherical image center faces camera-local +X, and local +Z is up. The negative-X-scaled Three.js sphere is oriented with `W * Q_e57 * inverse(W) * rotationY(180°)`. Image orientation comes from the E57 pose, not an assumed viewing-camera heading or the old -135° Cupix calibration.
5. The existing accepted scan-to-BIM transform then maps camera position and orientation into BIM. It is unchanged: yaw 0.08168900948820965°, translation [-35.23265480091985, 0.6271199075628591, -25.106843949799668], scale 1.

References: [libE57Format Image2D pose](https://asmaloney.github.io/libE57Format-docs/d1/d28/structe57_1_1_image2_d.html), [spherical representation](https://asmaloney.github.io/libE57Format-docs/d9/d2d/structe57_1_1_spherical_representation.html), and [BlobNode reading implementation](https://github.com/asmaloney/libE57Format/blob/master/src/BlobNodeImpl.cpp).

## Honest navigation

A photograph has one optical center. Photo mode moves between recorded stations, rather than pretending that a single image supplies arbitrary walking parallax. Drag either pane to look around; hold WASD / arrow keys in either pane, or use the on-screen movement pad. Movement chooses a nearby route neighbor in the viewing direction. Capture arrows/select remain available for explicit jumps. BIM's center crosshair and element inspection remain available. Free translation and Fit BIM are available in **3D mesh** mode. Floor selection does not move the scan to another floor.

The parent validates message origin, source, epoch and pose values. Photo mode keeps the BIM camera at the transformed active station; either pane may supply orientation. After the next image loads, a 420–850 ms eased crossfade moves both cameras together. The intermediate image is a blend of recorded photos, not measured parallax or a newly reconstructed video frame. Long explicit jumps crossfade without flying across the building. Reduced-motion preference removes the animation. Stale texture loads are disposed. No live sensor value, GLB identity or geometry is synthesized or changed.

## Loading and verification

Only the current photo and one replacement texture are held, including during crossfade. Two neighboring JPEGs are prefetched into the browser cache without GPU texture allocation. Original 4K images are served on desktop; 2048 × 1024 JPEG derivatives are served on mobile. Approximate active texture allocations with mipmaps are 45 MB and 11 MB respectively; these exclude BIM, browser overhead and the transient replacement texture. The large scan GLBs are not loaded in photo mode.

- Original JPEG SHA-256 values match all 100 extracted payloads; poses are finite unit quaternions.
- Source-image dimensions and mobile derivatives verified.
- Same corridor, stair and ramp layout visually checked in the photo/BIM split.
- Mobile Chrome test: 100 stations available; mobile image selected; next station, photo drag, BIM drag and Electrical focus preserve the accepted position/orientation mapping; mesh switch loads both GLB parts and restores free navigation; no JavaScript errors.
- Electrical default and opaque scan depth regression tests pass. Physical-phone testing is still distinct from browser emulation.

Run `python3 tests/panorama-assets.py`. For the browser integration, serve the repository on 127.0.0.1:8893 and run `node tests/photo-integration.cjs` with Playwright and Three.js installed (or set PLAYWRIGHT_MODULE and THREE_MODULE).

Slow-network regression: repeated Next moves to the cumulative target; a failed in-flight image does not drop a newer queued selection (`tests/photo-queue.cjs`). Rebuild runtime assets using `scripts/build_panorama_assets.py <extracted-directory>` with Pillow; originals are copied byte-for-byte.


## Directional walk route

The 217 archived capture-list positions map to their nearest exported photo stations. Adjacent entries contribute an edge only if the raw step is at most 4 m, the exported-station step is at most 5.5 m, and the elevation difference is under 1.5 m. All 100 exported stations are connected. This is an inferred route from list adjacency, not a verified chronological video track or a collision-certified floor plan. Walking chooses only graph neighbors within the requested forward/back/side direction; turn at route ends. It does not fabricate missing captures.

After rebuilding images, run `python3 scripts/build_photo_route.py <private-scan-inventory.json>` to regenerate neighbor indices. Do not publish the raw inventory. Validate with `node tests/photo-walk.cjs`, the asset tests, and `tests/photo-integration.cjs` (mobile tap, held forward motion, interpolated camera and registered endpoints).
