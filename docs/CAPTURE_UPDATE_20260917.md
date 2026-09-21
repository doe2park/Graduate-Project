# September 17 Grimes capture update

Imported September 21, 2026. Cupix SiteView visibly selected Level 1 / September 17, 2026 and displayed actual new panoramas. This is separate from the May 6 baseline.

## Assets and source

- E57 export: With Pano enabled, Use Coordinates from Source Data disabled (project coordinates). Three completed E57 files were checked against their container lengths. One contains 100 spherical images and poses; two contain point-cloud data only.
- Image names identify `VID_20260917_134908_00_013`. All recovered photos are 4096 × 2048; mobile derivatives are 2048 × 1024. The 100 exported images are not asserted to be the entire server inventory.
- One textured GLB exported, 98,549,364 bytes. The desktop copy is byte-identical. Mobile is 19,260,184 bytes with textures reduced to at most 512 pixels per edge. All non-image bufferViews, nodes, meshes and accessors were compared and remain identical.
- Public package: `scan-assets/captures/2026-09-17/`. Raw E57 files and extraction records remain in the owner's local `Grimes_360_Pilot/capture-20260917` archive. Hashes and selected export settings are in the package's `provenance.json`.

## Navigation and dates

The ordinary comparison defaults to September 17. The date picker retains May 6 without overwriting its assets. `?capture=2026-05-06` opens the baseline; `?capture=2026-09-17` opens the update. Photo and mesh modes follow the selected date. The local Gaussian option explicitly belongs to May; selecting it returns to that date. No September Gaussian training is claimed.

New photo stations are sorted by their original video frame number. Only consecutive exported frames with distance at most 5.5 m and elevation change at most 1.5 m are connected: 95 edges, four gaps. These are sparse temporally supported links, not verified collision-free paths. No arbitrary nearest spatial neighbors are connected through walls. The capture picker/previous-next controls can cross a route gap, but directional Walk cannot. Blended intermediate images are not measured parallax.

## Coordinate evidence and limits

Image poses convert E57 Z-up to viewer Y-up as `[x,z,-y]`, without adding the floor elevation again. New camera elevations span approximately 5.19–6.98 m in the source frame; this package remains labeled Level 1 as selected in Cupix, not Level 2.

New-to-May mesh consistency was checked from sampled vertices, voxelized at 0.12 m. There were 29,927 May samples and 32,081 September samples. With no additional transform, alternating held-out new samples had nearest-May median 0.298 m and p80 1.632 m. A 60%-trimmed yaw+XYZ ICP candidate changed yaw by -0.659 degrees and translation by [0.247, 0.054, -0.305] m; median improved to 0.276 m but p80 worsened to 1.742 m. That candidate was **not applied**. New coverage and changed furniture make nearest-old distances imperfect diagnostics.

The September package retains the Cupix project frame and uses the May scan-to-BIM transform only as a **provisional visualization alignment**, visibly labeled in the comparison. It has its own registration file/status. Neither these distances nor camera synchronization establish surveyed accuracy. Review distributed fixed landmarks and independent check points before treating device locations as verified.

## Verification

- Date-selection tests cover latest/old capture routing, unrecognized inputs and prevention of September labeling on the May Gaussian experiment.
- Walk loading tests and both element-viewer data-honesty test suites passed (38 tests total).
- All 100 source photo hashes/mobile dimensions and all 95 route edges checked.
- Every mobile GLB non-image bufferView and node/mesh/accessor record matches desktop.
- Chrome UI: September photo loaded; BIM Walk moved capture 1 to 2 with both views visible. At 390 px width, scroll width was 390 px and touch controls/date picker stayed visible. September mobile mesh loaded one part successfully. Date selection returned to the May mesh and May photo asset paths.
- Existing May source GLBs, BIM identity sidecars and data branch unchanged. No slide edits.

## September Mesh Walk correction (2026-09-21)

The new mesh was loaded, but the scan Walk spawn search had no September camera positions. The capture-aware loader now reads the 100 recorded stations from the September panorama manifest, already in Y-up project coordinates. May retains its legacy coordinate conversion and elevation offset. The comparison iframe revision was advanced so previously loaded viewer code is refreshed.

Verification: 12 capture-selection, Walk-camera, and Walk-loading tests passed. Chrome local preview entered September Mesh first-person at a geometry-supported floor of 4.55 m in desktop and 390 x 844 mobile viewport. Mobile arrow movement and linked BIM view were exercised. This checks entry and short movement, not every route or physical phone hardware; mesh holes can still limit traversable areas. Registration remains provisional. The owner subsequently approved public access to the September photos, mesh and poses, with a restrictive copyright notice. Publication includes LICENSE.md and a visible rights link; public viewing and GitHub forking rights remain unaffected.
