# Gaussian reconstruction: methods, evidence, and reuse

Recorded 2026-09-13 for future research presentations and capture reuse. No PowerPoint was edited for this update. **Three local optimization runs completed; an actual trained Gaussian scene is available in the local linked viewer.** The selected one-million-Gaussian model supports continuous novel-view movement but still has substantial blur and floaters. This is an experimental appearance layer, not a photograph-quality replacement or a public deployment.

## Three representations, different jobs

| Representation | What it does | Evidence boundary |
|---|---|---|
| Captured panorama Walk — implemented | Displays 100 recovered 4096 × 2048 E57 images at recorded poses; blends adjacent stations and synchronizes BIM | A crossfade is image-based navigation. Intermediate frames are not measured parallax or newly reconstructed surfaces. The source inventory has 217 positions, not 217 recovered images. |
| Gaussian reconstruction — local experiment implemented | Optimizes a spatial radiance representation against posed training images to synthesize novel views | A trained result must be inspected. Splat appearance alone does not establish survey accuracy, solid geometry, collision surfaces, or equipment identity. |
| Scan/BIM GLB — implemented | Renders explicit mesh geometry for free camera translation and registered comparison; BIM node IDs link to element sidecars | Design geometry is not proof of installed contents. Preserve GLB node identity and distinguish scan meshes from design BIM. |

The original 3DGS method optimizes Gaussian position, anisotropic covariance, opacity and appearance with density control and a visibility-aware rasterizer. It is the conceptual basis of this experiment, not evidence that this project's outputs match its benchmark quality or performance. See [Kerbl et al., 2023](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/).

The selected local implementation is **Brush v0.3.0 on an Apple M4 Pro with 24 GB unified memory**. Brush is an independent implementation; this experiment is not an exact replication of the original paper or its CUDA reference code. Actual options, initialization and results are recorded below. [Brush repository](https://github.com/ArthurBrussee/brush), [v0.3.0 release](https://github.com/ArthurBrussee/brush/releases/tag/v0.3.0), [original 3DGS reference implementation](https://github.com/graphdeco-inria/gaussian-splatting).

## Algorithm lineage: original 3DGS, MCMC, and Brush

[Kheradmand et al., 2024, 3D Gaussian Splatting as Markov Chain Monte Carlo](https://ubc-vision.github.io/3dgs-mcmc/) (NeurIPS 2024; [paper](https://proceedings.neurips.cc/paper_files/paper/2024/file/93be245fce00a9bb2333c17ceae4b732-Paper-Conference.pdf), [authors’ implementation](https://github.com/ubc-vision/3dgs-mcmc)) revisits Gaussian optimization as MCMC sampling. This is a later algorithmic lineage than Kerbl et al. (2023), not another name for the original method.

Brush's [version-pinned v0.3.0 changelog](https://github.com/ArthurBrussee/brush/blob/v0.3.0/CHANGELOG.md) explicitly describes MCMC-like training with its own automatic Gaussian growth variation and a maximum splat cap. The implementation rationale in [Brush PR #121](https://github.com/ArthurBrussee/brush/pull/121) combines gradient-guided growth with MCMC-like replacement of inactive Gaussians. Therefore describe this experiment as **Brush v0.3.0, an MCMC-inspired Gaussian splatting variant with automatic growth**. Cite original 3DGS for the representation/rendering foundation, Kheradmand et al. for the MCMC lineage, and Brush for the actual software. Neither paper is reproduced exactly, and upstream benchmark improvements do not establish improvement on Grimes.

### Completed local experiments

The working pilot selects **20 physical stations** from the 100-image archive and configures **136 training perspective views and 24 evaluation views**, at **640-pixel resolution and 100° field of view**, with fixed exported E57 poses. Initialization uses **50,000 mesh-sampled points**. The completed run used **6,000 steps, spherical harmonics degree 2, and a 450,000-splat cap**, and exported **404,038 optimized Gaussians**. Brush reported 159 seconds of training, held-out PSNR 18.713148 dB and SSIM 0.8523402 across 24 views from three held-out physical stations. The 17 training stations and three evaluation stations are disjoint. The full archive is not this pilot subset.

A separate 10-step smoke run succeeded first. The completed pilot renders continuous walls and corridor structure more coherently than the jagged scan mesh at reviewed viewpoints, but blur, elongated floaters and railing/floor bleed remain substantial. It is not photograph-quality reconstruction. A subsequent whole-archive experiment uses 86 training stations and 14 held-out stations (688/112 perspective views), 768-pixel crops, 150,000 mesh-sampled initial points, a one-million-Gaussian cap and 50,000 steps; it completed successfully. A second whole-archive run warm-started that final checkpoint, using a new optimizer/schedule, 30,000 additional steps and a two-million-Gaussian cap. Both final outputs were reviewed; the larger model did not materially resolve the blur, so the smaller final baseline is the local experimental default. This is a practical selection, not a claim that the final checkpoint is the globally best checkpoint.

## Technology map for a later presentation

| Project part | Actual technique/software | Reference and what may be claimed |
|---|---|---|
| Source capture | Recovered Cupix E57 spherical images and exported poses | Preserve source provenance. This project did not reproduce or inspect Cupix's proprietary capture reconstruction algorithm. |
| Image preparation | Equirectangular-to-pinhole projection; SciPy bilinear sampling; fixed E57 camera transforms | Explicit camera convention and analytic tests in `prepare_gaussian_dataset.py`. Derived crops are not extra physical observations. |
| Appearance reconstruction | Brush v0.3.0 Gaussian optimization, MCMC-inspired growth, SH degree 2 | Kerbl et al. 2023 for 3DGS; Kheradmand et al. 2024 for MCMC lineage; Brush for the actual variant and implementation. |
| Browser novel-view rendering | GaussianSplats3D 0.4.7 with Three.js 0.169.0; demand rendering; continuous camera movement | [Renderer implementation](https://github.com/mkkellogg/GaussianSplats3D). Rendering optimized PLY/KSplat is distinct from training it, and splats are not BIM objects. |
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

## Recorded run results — completed 2026-09-13

| Run | Physical stations (train / validation) | Views / resolution | Optimized Gaussians / steps | Brush-reported training time | Final validation PSNR / SSIM |
|---|---|---|---|---|---|
| `pilot-v1b` | 17 / 3 | 136 / 24, 640 px | 404,038 / 6,000 | 159 s | 18.713148 dB / 0.8523402 |
| `level1-v1` — selected | 86 / 14 | 688 / 112, 768 px | 1,000,000 / 50,000 | 2,274 s (37.9 min) | 19.197687 dB / 0.7978114 |
| `level1-detail-v2` | Same 86 / 14 | Same 688 / 112, 768 px | 2,000,000 / 30,000 additional | 2,061 s (34.4 min) | 19.237213 dB / 0.7976699 |

All runs use 100° perspective crops, fixed exported poses and SH degree 2. The pilot and whole-archive validation sets differ: their aggregate scores must not be treated as a controlled before/after comparison. The two whole-archive runs share a split. Their final PSNR difference is only 0.039526 dB, with slightly lower SSIM at 2M. Intermediate checkpoints sometimes score better: 1M at 35k scored 19.331604 dB; 2M at 10k scored 19.393484 dB. Validation guided experimentation, so there is **no independent final test set**, and these metrics are not geometry accuracy. The best-scoring 2M intermediate is retained for later analysis, not claimed to be the reviewed default.

The selected baseline started at 2026-09-13 22:32:21 UTC and ended at 23:11:04 UTC (exit 0, wall time about 2,324 s). The 2M warm start ran from 23:11:33 to 23:46:34 UTC (exit 0, wall time 2,100.532 s); it initializes optimized parameters from the baseline, **not the previous optimizer state**. Exact GPU adapter telemetry and peak unified-memory use were not measured. Brush's Apple Silicon executable reported `brush-cli 0.3.0`; the locally signed executable SHA-256 is `ec87ea0c950e74b88767fb978d83e5a4814dd41641a87f1b3c0a4b91bed95b2f`.

Source panorama manifest SHA-256: `57b14b84251fdfd4d9e55f179655a7e2af81e9e9756938643556e716886c55d1`. Whole-archive dataset provenance SHA-256: `95323f4db7a07253784f07abcf2949935075e0154488b63b2ba5fcad0a0523b8`. Individual image hashes and train/validation station IDs are archived in the private dataset provenance, along with both source scan-GLB hashes. The original scan GLBs remain byte-identical.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Selected 1M raw optimized PLY | 152,001,027 | `91eac1915c1938940d3d936eb21f7a7c32dff3c510857d3b10d7ee110791d9f7` |
| Selected 1M desktop KSplat | 48,058,596 | `0f0792ca2da1558a5fe3599929655f9d9c8c0fdc829521f63d46800069b0e33a` |
| Selected mobile 350k SH0 PLY | 19,600,427 | `178f456cbf00afe367f0613ea16a9054b8ac510d9b54f5bfc3c58bcd43c0f627` |
| Larger 2M raw optimized PLY | 304,001,027 | `7018e515c3624bade9e8e23d294b45af6d9c8f02530a9d326d04f4f80ce26524` |
| Larger 2M desktop KSplat | 96,108,464 | `9efdd53d569ebae202e8a63cd0fad3fd0c90b62d9f6ee3125b63a019edbc5056` |

The 1M compressed model loaded in **1,318 ms** in one local post-training headless-Chrome run on the M4 Pro. During a four-second forward walk, requestAnimationFrame interval median/p95 were 16.7/16.7 ms; the settled half-second idle sample rendered zero new frames. The 2M version loaded in 2,319 ms with median/p95 16.7/16.8 ms. These are single-machine local-server observations, not WAN timings, isolated GPU frame-time measurements, sustained-stress benchmarks, or physical-phone performance. Browser mobile emulation passed reduced-asset loading, on-screen movement controls and bidirectional BIM position/orientation/FOV checks; a real iOS/Android device still needs testing.

Matched browser views at the initial corridor station and a held-out lobby camera show recognizable walls, ceiling seams and furniture regions, but **blur, elongated floaters, cloudy railings, floor bleed and damaged furniture remain**. Doubling capacity did not materially fix those artifacts in the reviewed final outputs. Browser-versus-native-trainer checks at one held-out view support that the principal blur originates in the learned reconstruction, rather than a gross viewer coordinate error. A separate pilot raw-PLY/KSplat comparison at two fixed views yielded 56.8–57.0 dB image PSNR, supporting small codec differences at those views; this is compression parity, not photo-reconstruction quality.

The source provides only 100 recovered panoramas, not the original full continuous video. More crops do not add capture baselines. Plausible contributors include coverage gaps, reflective/transparent surfaces, panorama stitching, residual pose mismatch and model/training limits; their individual causal contributions have not been isolated. More splats or iterations alone are not an evidenced cure. Next quality work should prioritize denser sharp source frames with recoverable poses, explicit pose/scale checks, and bounded local-area reconstruction comparisons before another whole-floor capacity increase.

Private evidence root: `/Users/yschung/Documents/Playground/Grimes_360_Pilot/gaussian-splatting/`. `run-results.json` indexes actual logs, scores, hashes and browser timing reports. `review/selected50k-station89.png`, `review/selected50k-eval003.png`, and `review/detail30k-*.png` retain matched project screenshots. Generated intermediate checkpoint/evaluation files were selectively retired during disk pressure, with retention logs and final sources preserved. The 2M 5k export failed for lack of disk space; later exports and the final exit/checkpoint were verified. Reserve disk space for checkpoints and validation images before repeating training.

Local experimental comparison: `http://127.0.0.1:8893/scan-compare.html?mode=splat`. Default Gaussian manifest: `capture-local/gaussian/pilot/viewer.json`, referencing `baseline-50000-compact`. The larger retained experiment is available independently through `scan-splat.html?manifest=capture-local/gaussian/detail-30000/viewer.json`. Normal comparison entry still offers captured-photo and mesh modes. Local loopback URLs are not audience/mobile QR destinations. These private reconstructed assets have **not been published**.

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

The seed is **scan geometry, not the design BIM**. `--seed-up-axis z` matches the tested Cupix export; use `y` only for a verified Y-up scan already in the same metric frame as the cameras. The exporter does not register a misaligned mesh to the photos, decode Draco seeds, recover missing camera poses, or infer units. Selection is geometric, not an automatic floor classifier: the current mesh seed clips around the selected camera center from -3 to +7 metres vertically. Use an isolated floor capture/seed and inspect the bounds; merely changing a floor label does not exclude an adjacent floor. Omitting `--seed-glb` uses the trainer's random initialization, an unvalidated option for new datasets. Checkpoints must be reviewed rather than selecting the largest iteration number automatically.

For a smaller desktop asset, install `@mkkellogg/gaussian-splats-3d@0.4.7` and `three@0.169.0` in an isolated tool directory. Set `GAUSSIAN_MODULE` to that package's absolute `build/gaussian-splats-3d.module.js` path (or use normal Node resolution), then run:

```bash
node scripts/encode_gaussian.mjs \
  /private/path/<capture>-run/export_50000.ply \
  /private/path/<capture>.ksplat
```

It writes the KSplat and adjacent `.ksplat.json` provenance without changing the PLY. Add `--desktop-ksplat /private/path/<capture>.ksplat` to the packaging command and choose a **new** output directory. Compression is for transport/rendering; it does not improve training quality.

Open `scan-splat.html?manifest=capture-local/gaussian/<capture>/viewer.json` for isolated review. It preserves the capture coordinates. The Grimes comparison page's `Gaussian · experiment` option reads `capture-local/gaussian/pilot/viewer.json` and applies **Grimes's accepted registration only**. Do not put another building's package at that path to get a supposedly registered comparison. Establish and integrate a separate registration for the new project first.

Without compression, desktop `trained.ply` is a byte-identical copy of the selected checkpoint. The selected local default instead uses a **lossy KSplat level-2 derivative** produced by pinned GaussianSplats3D 0.4.7; it quantizes parameters and preserves the recorded scene frame. The codec records input/output hashes and counts, and packaging rejects a derivative whose hashes do not bind to the supplied checkpoint. `mobile.ply` is a lossy derivative: at most 350,000 retained optimized Gaussians, opacity filtering, 15 cm spatial coverage followed by opacity prioritization, and degree-zero spherical harmonics. It does not retrain or move retained Gaussians. Inspect both variants, because the smaller file can lose opacity and detail. The manifest records file hashes, byte counts, retained counts and initial camera. `capture-local/` remains ignored; producing a package is not publishing it.

Reusing this workflow removes repetitive camera conversion, training-command setup and viewer packaging. Reconstruction time, registration review and missing coverage still depend on each capture. A camera-only workflow without Cupix requires an additional implemented and validated pose/scale reconstruction stage; this experiment reuses Cupix E57 poses and scan initialization.

## Additional diagnostic: exported camera consistency

A read-only local diagnostic tested 15 usable nearby image pairs from 16 sampled stations, using OpenCV 4.13.0 SIFT descriptors (ratio 0.65) and `USAC_MAGSAC` fundamental-matrix inlier selection (1.5-pixel threshold). Sampson distances were then computed from the **fixed exported E57 poses**, not the fitted fundamental matrix. The median of pair medians was 0.451 pixels at 768-pixel crop resolution (pair medians 0.174–2.768 pixels). Several pairs had very large upper-tail errors, consistent with mismatches/planar ambiguity; these must not be hidden by the aggregate.

This limited check supports broadly consistent image poses in sampled overlaps but does not prove all poses correct, diagnose every blurred surface, or establish metric registration accuracy. No camera pose, BIM transform or training input was changed from this diagnostic. Local evidence: `Grimes_360_Pilot/gaussian-splatting/pose-consistency-diagnostic.json` and its adjacent script. Method references: [Lowe, 2004, Distinctive Image Features from Scale-Invariant Keypoints](https://www.cs.ubc.ca/~lowe/papers/ijcv04.pdf); [Barath et al., 2020, MAGSAC++](https://openaccess.thecvf.com/content_CVPR_2020/html/Barath_MAGSAC_a_Fast_Reliable_and_Accurate_Robust_Estimator_CVPR_2020_paper.html). These are diagnostic algorithm lineages, not replacements for the recorded scan-to-BIM ICP.

## Verification record

Passed: five Python camera/projection/packaging tests; real Gaussian codec round-trip, source-hash and no-overwrite checks; synthetic browser Gaussian rendering, idle/wheel/resize behavior, invalid/stale pose rejection and mobile asset policy; actual selected 1M KSplat and 350k mobile PLY load/navigation with scan ↔ BIM position, orientation and FOV matching within numerical tolerance. Existing photo/mesh integration checks also passed during this work. These software checks verify the implementation and coordinate transport, not physical registration accuracy. Independent code review found no remaining actionable issue in the final codec/package/viewer changes.
