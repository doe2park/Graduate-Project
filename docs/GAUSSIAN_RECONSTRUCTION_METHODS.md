# Gaussian reconstruction: methods, evidence, and reuse

Recorded 2026-09-13 for future research presentations and capture reuse. No PowerPoint was edited for this update. **The local Gaussian training outcome is pending in this record.** Fill the run-results section from actual logs and reviewed renders before making completion or quality claims.

## Three representations, different jobs

| Representation | What it does | Evidence boundary |
|---|---|---|
| Captured panorama Walk — implemented | Displays 100 recovered 4096 × 2048 E57 images at recorded poses; blends adjacent stations and synchronizes BIM | A crossfade is image-based navigation. Intermediate frames are not measured parallax or newly reconstructed surfaces. The source inventory has 217 positions, not 217 recovered images. |
| Gaussian reconstruction — experiment pending | Optimizes a spatial radiance representation against posed training images to synthesize novel views | A trained result must be inspected. Splat appearance alone does not establish survey accuracy, solid geometry, collision surfaces, or equipment identity. |
| Scan/BIM GLB — implemented | Renders explicit mesh geometry for free camera translation and registered comparison; BIM node IDs link to element sidecars | Design geometry is not proof of installed contents. Preserve GLB node identity and distinguish scan meshes from design BIM. |

The original 3DGS method optimizes Gaussian position, anisotropic covariance, opacity and appearance with density control and a visibility-aware rasterizer. It is the conceptual basis of this experiment, not evidence that this project's outputs match its benchmark quality or performance. See [Kerbl et al., 2023](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/).

The selected local implementation is **Brush v0.3.0 on an Apple M4 Pro with 24 GB unified memory**. Brush is an independent implementation; this experiment is not an exact replication of the original paper or its CUDA reference code. Record actual options and initialization below. [Brush repository](https://github.com/ArthurBrussee/brush), [v0.3.0 release](https://github.com/ArthurBrussee/brush/releases/tag/v0.3.0), [original 3DGS reference implementation](https://github.com/graphdeco-inria/gaussian-splatting).

## Algorithm lineage: original 3DGS, MCMC, and Brush

[Kheradmand et al., 2024, 3D Gaussian Splatting as Markov Chain Monte Carlo](https://ubc-vision.github.io/3dgs-mcmc/) (NeurIPS 2024; [paper](https://proceedings.neurips.cc/paper_files/paper/2024/file/93be245fce00a9bb2333c17ceae4b732-Paper-Conference.pdf), [authors’ implementation](https://github.com/ubc-vision/3dgs-mcmc)) revisits Gaussian optimization as MCMC sampling. This is a later algorithmic lineage than Kerbl et al. (2023), not another name for the original method.

Brush's [version-pinned v0.3.0 changelog](https://github.com/ArthurBrussee/brush/blob/v0.3.0/CHANGELOG.md) explicitly describes MCMC-like training with its own automatic Gaussian growth variation and a maximum splat cap. The implementation rationale in [Brush PR #121](https://github.com/ArthurBrussee/brush/pull/121) combines gradient-guided growth with MCMC-like replacement of inactive Gaussians. Therefore describe this experiment as **Brush v0.3.0, an MCMC-inspired Gaussian splatting variant with automatic growth**. Cite original 3DGS for the representation/rendering foundation, Kheradmand et al. for the MCMC lineage, and Brush for the actual software. Neither paper is reproduced exactly, and upstream benchmark improvements do not establish improvement on Grimes.

### Completed local pilot — broader quality experiment in progress

The working pilot selects **20 physical stations** from the 100-image archive and configures **136 training perspective views and 24 evaluation views**, at **640-pixel resolution and 100° field of view**, with fixed exported E57 poses. Initialization uses **50,000 mesh-sampled points**. The completed run used **6,000 steps, spherical harmonics degree 2, and a 450,000-splat cap**, and exported **404,038 optimized Gaussians**. Brush reported 159 seconds of training, held-out PSNR 18.713148 dB and SSIM 0.8523402 across 24 views from three held-out physical stations. The 17 training stations and three evaluation stations are disjoint. The full archive is not this pilot subset.

A separate 10-step smoke run succeeded first. The completed pilot renders continuous walls and corridor structure more coherently than the jagged scan mesh at reviewed viewpoints, but blur, elongated floaters and railing/floor bleed remain substantial. It is not photograph-quality reconstruction. A subsequent whole-archive experiment uses 86 training stations and 14 held-out stations (688/112 perspective views), 768-pixel crops, 150,000 mesh-sampled initial points, a one-million-Gaussian cap and 50,000 steps; its final evaluation remains pending here.

## Technology map for a later presentation

| Project part | Actual technique/software | Reference and what may be claimed |
|---|---|---|
| Source capture | Recovered Cupix E57 spherical images and exported poses | Preserve source provenance. This project did not reproduce or inspect Cupix's proprietary capture reconstruction algorithm. |
| Image preparation | Equirectangular-to-pinhole projection; SciPy bilinear sampling; fixed E57 camera transforms | Explicit camera convention and analytic tests in `prepare_gaussian_dataset.py`. Derived crops are not extra physical observations. |
| Appearance reconstruction | Brush v0.3.0 Gaussian optimization, MCMC-inspired growth, SH degree 2 | Kerbl et al. 2023 for 3DGS; Kheradmand et al. 2024 for MCMC lineage; Brush for the actual variant and implementation. |
| Browser novel-view rendering | GaussianSplats3D 0.4.7 with Three.js 0.169.0; demand rendering; continuous camera movement | [Renderer implementation](https://github.com/mkkellogg/GaussianSplats3D). Rendering optimized PLY is distinct from training it, and splats are not BIM objects. |
| Scan/BIM coordinates | Previously computed trimmed point-to-point ICP; yaw + XYZ translation, fixed metric scale | Besl & McKay 1992; Chetverikov et al. 2002. Gaussian cameras use the same verified scan frame and forward/inverse registration; no new ICP run is implied. |
| BIM identity and selection | Original GLB node IDs, identity sidecar JSON, runtime batches with triangle/line ranges | Project engineering implementation; no separate research algorithm claimed. Preserve identifiers when adding future buildings. |
| Operational data | BMO utility-meter data → scheduled GitHub Actions → machine-written data branch → browser JSON | Actual upstream meter observations, not invented Gaussian data. This is not a newly implemented direct BACnet/BAS connection. |
| Element information | Measured building/feeder context; modelled design-VA/CFM allocation; inferred level; NO FEED where absent | Data-honesty ladder. Meter 76 is not apportioned. Appearance similarity does not prove an equipment-to-sensor association. |
| Future camera-only reconstruction | Proposed frame extraction and SfM/SLAM pose recovery with metric-scale verification | Schönberger & Frahm 2016 for SfM background. Not implemented by the current Gaussian training step. |

## Input and camera preparation

The current experiment starts from the **100 recovered Cupix E57 panoramas and their exported poses**, not a newly solved raw-video trajectory. Original files, image GUIDs, poses and hashes remain the provenance source; derived perspective images are training inputs, not additional physical capture stations.

A pinhole training view can be generated by mapping each perspective pixel through its camera intrinsics to a direction on the sphere, rotating that direction into the panorama frame, then sampling the corresponding longitude/latitude. Every crop from one panorama shares its camera center; only its orientation and intrinsics change. Cropping adds neither baseline nor image detail. The exact crop size, field of view, axes, rotation order and interpolation must be saved with each run. FFmpeg's official [v360 documentation](https://ffmpeg.org/ffmpeg-filters.html#v360) documents equirectangular/flat projection, field of view and orientation controls; it is a reference for projection concepts, not a claim that this run uses FFmpeg.

For the existing intake, E57 positions convert once from `[x,y,z]` to viewer `[x,z,-y]`, a -90° X-axis basis rotation. Original quaternion components are retained as `e57Quaternion` in `[x,y,z,w]` order; the rendering/training adapter must apply its documented camera-axis convention. Do not blindly copy quaternion components into a renderer or invert the pose twice. In column-vector notation, with E57 camera-to-world rotation `R`, translation `t`, world basis change `A`, and output camera-ray basis mapping `C`, use `R_out = A R C` and `t_out = A t`; a world-to-camera format instead requires inversion. Verify known headings and a reprojection before training. E57's rotation/translation representation is documented in the maintained [libE57Format data structures](https://github.com/asmaloney/libE57Format/blob/master/include/E57SimpleData.h); the specific axis adapter is this project's convention.

The source already includes Level 1 elevation. **Do not add 4.572 m twice, and do not add a Grimes elevation offset to new captures.** Implementation evidence: [capture importer](../scripts/capture_import.py), [panorama viewer method](CAPTURED_PANORAMA_VIEWER.md).

## Registration actually used in Grimes

The accepted scan/BIM alignment is historical **trimmed point-to-point ICP constrained to four degrees of freedom: yaw plus XYZ translation, scale fixed at 1**. It estimates alignment from nearest sampled geometry after coordinate conversion; it does not optimize image appearance. It is not six-DOF or point-to-plane ICP.

Correspondences are trimmed below `min(2 m, 65th percentile)` before fitting yaw and translation. The internal median nearest-reference-point residual is **0.12927 m** and p80 is **0.48278 m**. These are not surveyed accuracy, equipment-location accuracy, or a Gaussian reconstruction score. The evaluation subset also selected initializations, and spatial sensitivity checks start from the accepted fit; independent survey controls remain needed. Exact transform, thresholds, sampling and limitations: [registration evidence](SCAN_BIM_REGISTRATION.md), [accepted result](../alignment-analysis/accepted-registration.json).

Method lineage: [Besl and McKay, 1992, A Method for Registration of 3-D Shapes](https://graphics.stanford.edu/courses/cs348a-21-winter/Handouts/Besl92.pdf) provides ICP foundations; [Chetverikov, Svirko, Stepanov and Krsek, 2002, The Trimmed Iterative Closest Point Algorithm](https://doi.org/10.1109/ICPR.2002.1047997) provides trimmed correspondence fitting. This project's yaw-only rotation constraint and thresholds are application choices, not a claim of exact paper replication.

A future splat may use the existing scan/BIM transform only after confirming its coordinates match the registered scan frame. Any training normalization must be inverted or composed explicitly. Do not use the legacy Cupix -135° calibration as the exported scan GLB registration.

## Repeatable intake for L2 or another building

1. Archive continuous footage and all INSV companion files, stitched exports, capture date, building/floor, route and stable landmarks. Preserve original E57/point cloud, exported poses and NWD/IFC/RVT when available.
2. For raw footage, select sharp overlapping frames, recover camera poses using a suitable SfM/SLAM pipeline, and establish metric scale and frame conventions from evidence. [Schönberger and Frahm, 2016, Structure-from-Motion Revisited](https://www.cv-foundation.org/openaccess/content_cvpr_2016/html/Schonberger_Structure-From-Motion_Revisited_CVPR_2016_paper.html) is the SfM reference. This raw-video stage remains proposed here; the intake does not implement it.
3. Prepare posed training views, run Gaussian optimization, archive configuration/logs/output hashes, and inspect held-out viewpoints and route transitions. Hold out whole physical stations rather than sibling crops to avoid misleading evaluation. Gaussian training does not automatically produce a trustworthy GLB mesh.
4. Convert source BIM/scan geometry separately when necessary. Use `scripts/capture_import.py prepare` to create an isolated building/floor/date package, then review with `capture-review.html?project=...`. These intake tools are implemented; [CAPTURE_ONBOARDING.md](CAPTURE_ONBOARDING.md) contains commands and input requirements.
5. Establish that capture's GLB/BIM registration from real fit landmarks or geometry and evaluate independent check landmarks. The optional landmark alignment is provisional. A new L2 export may have a new origin; do not inherit L1 transforms.
6. Review mobile loading, navigation, image headings, distant alignment checks and actual element picking before integration. Keep original imagery available as a baseline. Record device/browser and measured performance; use a verified audience URL for later presentation QR codes.

There is **no automatic NWD/INSV upload-to-reconstruction service** in this intake. New buildings inherit neither Grimes transforms nor Grimes sensor feeds. Preserve source photo IDs, GLB node IDs and sidecars. Gaussian appearance does not identify a sensor: measured / modelled / inferred / NO FEED labels still apply, and equipment-to-feed links require documentary evidence.

## Run results — PENDING, fill from the actual experiment

| Field | Recorded value |
|---|---|
| Run ID, start/end time, status | Pending |
| Brush version/build, device/backend | Target: v0.3.0, Apple M4 Pro, 24 GB; actual backend/build pending |
| Source manifest and hashes | 100 recovered 4096 × 2048 E57 panoramas; exact manifest/hash pending |
| Used stations/crops; crop resolution/FOV | Pending; do not equate crop count with station count |
| Pose convention, normalization, scan-frame mapping | Pending |
| Initialization, training options, iterations | Pending |
| Elapsed training time, peak memory | Pending measurement |
| Output path, format, bytes, checksum | Pending |
| Train/held-out station split and image metrics | Pending; label unmeasured metrics unavailable |
| Fixed-camera comparison and observed artifacts | Pending visual review |
| Mobile loading/frame rate/browser/device | Pending device QA |
| BIM registration/check landmarks | Pending splat-frame verification |
| Accepted for presentation/public viewer | Pending; no quality or deployment claim |

Future slides should show: (1) capture and provenance, (2) panorama versus splat versus BIM, (3) training method and measured run outcome, (4) constrained registration and validation limits, and (5) repeatable L2/building intake. Keep full references in a reference appendix or separate research notes (do not restore presenter notes removed at the owner’s request) and use reviewed project screenshots rather than paper benchmark images to imply local results.

## Reusable local commands

Use an isolated Python environment with `numpy`, `scipy`, and `Pillow`. The tested environment used NumPy 2.3.5 and SciPy 1.18.1. Obtain **Brush v0.3.0** from its official release, verify the published archive checksum, and retain the binary hash. The training runner neither downloads software nor uploads images. The Apple Silicon release used here required a local ad-hoc signature after macOS rejected its packaged signature; this is recorded as a local runtime adjustment, not a change to reconstruction algorithms.

For a new capture, first use the [capture intake workflow](CAPTURE_ONBOARDING.md) to produce `capture-local/<capture>/panoramas/manifest.json`. That manifest contains image hashes, station positions and E57 quaternions consumed by the exporter below. Choose a real station ID as the center and a radius that includes the intended capture area; the exporter reports the exact selected count. These examples use placeholders that must be replaced with actual paths and IDs:

```bash
python scripts/prepare_gaussian_dataset.py \
  --manifest capture-local/<capture>/panoramas/manifest.json \
  --output /private/path/<capture>-dataset \
  --center-id <recorded-station-id> --radius 60 --size 768 \
  --seed-glb /private/path/scan.glb --seed-up-axis z --point-count 150000

python scripts/train_gaussian.py \
  --brush /private/path/brush_app \
  --dataset /private/path/<capture>-dataset \
  --output /private/path/<capture>-run \
  --steps 50000 --max-splats 1000000 --resolution 768 \
  --checkpoint-every 5000 --refine-every 400 --growth-stop 30000 --sh-degree 2

python scripts/package_gaussian.py \
  --input /private/path/<capture>-run/export_50000.ply \
  --output capture-local/gaussian/<capture> \
  --panoramas capture-local/<capture>/panoramas/manifest.json \
  --station-id <recorded-station-id> --mobile-budget 350000 --iterations 50000
```

The seed is **scan geometry, not the design BIM**. `--seed-up-axis z` matches the tested Cupix export; use `y` only for a verified Y-up scan already in the same metric frame as the cameras. The exporter does not register a misaligned mesh to the photos, decode Draco seeds, recover missing camera poses, or infer units. Omitting `--seed-glb` uses the trainer's random initialization, an unvalidated option for new datasets. Checkpoints must be reviewed rather than selecting the largest iteration number automatically.

Open `scan-splat.html?manifest=capture-local/gaussian/<capture>/viewer.json` for isolated review. It preserves the capture coordinates. The Grimes comparison page's `Gaussian · experiment` option reads `capture-local/gaussian/pilot/viewer.json` and applies **Grimes's accepted registration only**. Do not put another building's package at that path to get a supposedly registered comparison. Establish and integrate a separate registration for the new project first.

The desktop `trained.ply` is a byte-identical copy of the selected checkpoint. `mobile.ply` is a lossy derivative: at most 350,000 retained optimized Gaussians, opacity filtering, 15 cm spatial coverage followed by opacity prioritization, and degree-zero spherical harmonics. It does not retrain or move retained Gaussians. Inspect both variants, because the smaller file can lose opacity and detail. The manifest records file hashes, byte counts, retained counts and initial camera. `capture-local/` remains ignored; producing a package is not publishing it.

Reusing this workflow removes repetitive camera conversion, training-command setup and viewer packaging. Reconstruction time, registration review and missing coverage still depend on each capture. A camera-only workflow without Cupix requires an additional implemented and validated pose/scale reconstruction stage; this experiment reuses Cupix E57 poses and scan initialization.

## Additional diagnostic: exported camera consistency

A read-only local diagnostic tested 15 usable nearby image pairs from 16 sampled stations, using OpenCV 4.13.0 SIFT descriptors (ratio 0.65) and `USAC_MAGSAC` fundamental-matrix inlier selection (1.5-pixel threshold). Sampson distances were then computed from the **fixed exported E57 poses**, not the fitted fundamental matrix. The median of pair medians was 0.451 pixels at 768-pixel crop resolution (pair medians 0.174–2.768 pixels). Several pairs had very large upper-tail errors, consistent with mismatches/planar ambiguity; these must not be hidden by the aggregate.

This limited check supports broadly consistent image poses in sampled overlaps but does not prove all poses correct, diagnose every blurred surface, or establish metric registration accuracy. No camera pose, BIM transform or training input was changed from this diagnostic. Local evidence: `Grimes_360_Pilot/gaussian-splatting/pose-consistency-diagnostic.json` and its adjacent script. Method references: [Lowe, 2004, Distinctive Image Features from Scale-Invariant Keypoints](https://www.cs.ubc.ca/~lowe/papers/ijcv04.pdf); [Barath et al., 2020, MAGSAC++](https://openaccess.thecvf.com/content_CVPR_2020/html/Barath_MAGSAC_a_Fast_Reliable_and_Accurate_Robust_Estimator_CVPR_2020_paper.html). These are diagnostic algorithm lineages, not replacements for the recorded scan-to-BIM ICP.
