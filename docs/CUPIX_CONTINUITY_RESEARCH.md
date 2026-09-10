# Cupix reconstruction and continuity assessment

Research date: 2026-09-10. Evidence combines public vendor documentation, a read-only inspection of the authenticated project, and existing local export records. No reconstruction job or new bulk export was run during this investigation.

## Findings

Cupix is more than a hosted viewer. Its documented workflow accepts 360 imagery and produces positioned panoramas, point clouds and textured meshes. Cupix publicly describes SLAM powered by its Neural 3D Engine. This establishes the technology family but does not disclose the exact proprietary algorithm, parameter set or engine build used for the Grimes capture. Calling the project a known COLMAP/SfM pipeline is unsupported.

Cupix also published a Gaussian Splatting virtual-navigation development preview. Therefore, saying Cupix does not use or develop Gaussian Splatting would be incorrect. That preview does not establish that Grimes used it or that a particular account can export splats. The assets used in our current viewer are ordinary textured triangle meshes, not Gaussian splat files.

## Public-source evidence

1. [Cupix Neural 3D Engine / SLAM announcement, 2022-09-20](https://careers-kr.cupix.com/38d20990-7c01-4b18-9668-a3aa9f8fbb34): vendor explicitly describes SLAM technology. Historical technology announcement, not a project processing log.
2. [CupixWorks TwinCapture documentation](https://support.cupix.works/support/solutions/articles/70000105541-twincapture): distinguishes 3D Map (tour plus dollhouse mesh), 360 Video (tour), and 360 Photo (manually positioned tour). Camera brand alone does not establish which mode was used.
3. [CupixVista cloud processing](https://support.cupixvista.com/hc/en-us/articles/37919077903515-What-Happens-in-the-Cloud): video frames are positioned in 3D; point cloud and textured mesh are generated. Vista documentation explains a related vendor workflow; it is not evidence of this Works project's exact engine version.
4. [Cupix Insta360 X4 integration announcement, 2024-08-20](https://www.cupix.com/press-releases/cupix-announces-seamless-integration-with-insta360-x4-camera-elevating-3d-as-built-capture-quality): describes stitch-line correction and proprietary 3D mapping improvements.
5. [Cupix's Gaussian Splatting development preview](https://www.linkedin.com/posts/cupix_gaussiansplatting-nerf-cupix-activity-7174464755468828672-o3wE): vendor-authored preview of 360-video-based Gaussian Splatting navigation. No assumption of deployment in this capture.
6. [CupixVista export documentation](https://support.cupixvista.com/hc/en-us/articles/37920987204763-Export-3D-Data): E57/PLY/XYZ point clouds, GLB/OBJ meshes, proprietary CPC archive. E57 can optionally include panoramas in Vista; that option was not verified in the Works project dialog.
7. [Cupix Connect options](https://support.cupix.works/support/solutions/articles/70000271136-cupix-connect-options): Download SiteView Content requires Team Admin. Viewing/exporting one model does not establish this broader privilege.

## Authenticated project findings

The existing signed-in Chrome session accessed the Herrero CupixWorks project and the Level 1 / May 6, 2026 capture. No new login was needed. SiteView displayed version 2026.3.8; this is the viewer version, not a verified reconstruction-engine version.

Directly inspected path: Main / aerial view → 3D Display Settings → Export.

- Point Cloud tab: PLY (binary or text), E57, XYZ.
- Textured Mesh tab: OBJ (mesh only), GLB (mesh and texture).
- Both tabs expose Use Coordinates from Source Data.
- These are observed available controls, not proof that every selected format has been downloaded successfully.
- Account/project menus inspected exposed SiteView access. Capture processing history, original video download and Team Admin backup privileges were not verified. No API key was generated or permissions changed.

Historical local records identify an Insta360 X4 panorama (4096×2048 sample) and video-derived panorama names including VID_20260506_145040_00_472(12).jpg. The inventory has two capture records and 217 panorama metadata entries. These metadata support video-derived imagery but do not establish the complete internal reconstruction pipeline. A list of panorama positions is not a complete calibrated camera-pose dataset.

## What is already preserved

| Asset | Confirmed status | Continuity value |
|---|---|---|
| Two Level 1 textured scan GLBs | Local and public repository; source hashes recorded | Existing scan remains renderable without Cupix at runtime |
| Accepted scan/BIM transform | Public JSON, method record, archived fitter/results | Existing geometry and camera alignment remain usable |
| Panorama metadata inventory | Local private file, 217 entries | Captured names, dates and positions; not all full-resolution images or full poses |
| Example panorama | One locally documented 4096×2048 sample | Example only, not full panorama backup |
| Original Insta360 videos | Not verified in inspected project files or current UI | Highest priority for independent reconstruction |
| E57/PLY point-cloud exports | Export controls available; downloaded files not verified | Needed for independent geometric analysis and interoperability |
| Source plans, scale references, control points | Full export package not verified | Needed to establish scale and validate alignment |

Original source GLBs total approximately 97 MB. The current mobile derivatives only reduce texture resolution, preserve all geometry and coordinates, and total approximately 20 MB. Their current mesh appearance does not reveal whether any proprietary neural model participated upstream.

## Continuity plan

### Existing capture

The current scan-compare page loads locally hosted GLBs and the saved registration. It does not need the Cupix viewer to render that captured geometry. Keep the original GLBs, texture-bearing files, registration JSON, provenance hashes and source BIM outside any expiring workspace. Coverage remains the exported Level 1 representation, with holes; it is not established that every room or surface is represented.

Before losing access, obtain:

1. Original camera files and all companion segments/metadata for the May 6 capture (native .insv if that is the recorded format, otherwise the actual original format), plus an unedited stitched equirectangular export if available. Preserve resolution, frame rate, timestamps, camera model and stitching/stabilization settings. Do not assume an exported mesh can recover these images.
2. All full-resolution panoramas with IDs, timestamps and corresponding camera position/orientation, projection convention, calibration, units and coordinate system if exportable.
3. Full-resolution E57 or PLY and both GLB parts, with coordinate-export choice recorded. Export in a consistent source frame and preserve any project-to-source transform. Do not silently reuse the existing transform on a differently transformed export.
4. Reference plans, known dimensions, control-point measurements, capture mode, processing date/status and any available engine/version report.
5. A complete SiteView backup through an authorized Team Admin if needed. Treat proprietary CPC/backup packages as supplementary, not the sole independent archive.

### Future captures without Cupix

Start with a short representative corridor/room pilot using original 360 footage, then test pose recovery and geometric consistency before scaling to Level 1.

- Geometric route: spherical-aware SfM/SLAM, dense reconstruction and a mesh/point cloud, followed by verified scale and BIM registration. [OpenSfM documentation](https://opensfm.org/docs/using.html) includes a spherical 360 dataset and camera-model configuration. The software provides a candidate implementation, not guaranteed equivalent output to Cupix.
- Appearance route: camera estimation plus Gaussian Splatting for visual context, with the BIM retaining semantic element IDs, picking and operational data. [Nerfstudio custom-data documentation](https://github.com/nerfstudio-project/nerfstudio/blob/main/docs/quickstart/custom_dataset.md) describes processing Insta360-like equirectangular images/video. Its reconstruction/training stage needs a suitable compute environment; GitHub Pages only serves the resulting viewer/assets.
- Check geometric residuals on independent fixed references, camera drift, thin pipes/occlusions, and physical-phone memory before claiming a replacement. Photorealism alone is not geometric validation. Gaussian Splatting does not automatically identify devices or attach BAS points.

## Suggested request to the project administrator

Please preserve and provide the original Insta360 capture files for the May 6 Level 1 survey, together with full-resolution panoramic images and their camera poses/calibration if available. Please also export the point cloud as E57 or PLY and the textured mesh as GLB, retaining source coordinates and documenting any project transform. We also need the capture mode, processing information, reference floor plans and known dimensions/control points, so that we can archive the existing survey and evaluate a reconstruction workflow independent of Cupix. If our account cannot download the full SiteView content, please arrange a Team Admin export.

No request was sent as part of this investigation.

## Professor explanation

“Insta360 provided the capture imagery. Cupix processed the imagery into spatially positioned panoramas and 3D geometry, using its proprietary mapping technology, publicly described as SLAM-based. We then performed a separate constrained ICP registration to align the exported mesh with BIM. The exact proprietary reconstruction configuration for this capture is not yet verified. For future independence, we are preserving the source imagery and evaluating an alternative reconstruction workflow.”
