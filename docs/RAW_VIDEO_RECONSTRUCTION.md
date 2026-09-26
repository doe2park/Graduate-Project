# Grimes raw-video SfM and Gaussian pilot

Status summary updated September 25, 2026. Results are from local run records; raw video, trained scenes and private experiment directories are not published here.

## Distinguish the two experiments

| Track | Camera/geometry source | Relationship to BIM |
|---|---|---|
| Earlier posed-image Gaussian experiment | Cupix E57 image poses and scan-based initialization | Uses the existing scan frame; see [methods](GAUSSIAN_RECONSTRUCTION_METHODS.md) |
| September raw-video pilot described here | Original Insta360 ONE X2 INSV; COLMAP estimates poses | Metric scale unknown; no validated BIM alignment or ICP applied to this pilot |

The public September photo/mesh comparison is a separate exported-capture package. Its provisional alignment does not establish alignment of the independent Gaussian scene.

## Actual processing

1. Insta360 Studio stitches the dual-lens INSV capture into equirectangular 360° video. This uses proprietary stitching, but no Cupix photos, mesh or poses.
2. FFmpeg projects sampled panoramas into front/right/back/left perspective views with 100° field of view. Multiple directions at one station do not create new translational baseline.
3. COLMAP via pycolmap 4.2.0 performs SIFT extraction, exhaustive matching, geometric verification, incremental SfM and bundle adjustment.
4. Brush 0.3.0 optimizes a Gaussian scene using the images and estimated camera poses. Render–photo differences guide updates of position, shape, orientation, opacity and appearance. This is scene-specific optimization, not automatic BIM generation.

## Recorded results and limits

| Quantity | Local result |
|---|---|
| Input segment | First 2.4 playback seconds of accelerated footage; not field elapsed time |
| Derived images | 36 stations × 4 directions = 144 images, 1024 px |
| Registered images | 142 |
| Sparse points | 7,565 |
| Mean reprojection error | 0.756 px; internal image residual, not metric accuracy |
| Gaussian run | 8,000 steps, maximum training resolution 768 px, SH degree 2, 300k splat cap |
| Completion | Export completed successfully; blur and artefacts remain |
| Geometry / alignment | No dense mesh generated; metric scale and BIM alignment unvalidated |

The coarse whole-clip trial registered only 2 of 132 images. The successful short-segment result must not be presented as a completed whole-floor reconstruction. The SfM run does not enforce the shared-center constraint of views derived from the same panorama.

Evaluation holds out individual views, not independent physical regions; other directions or nearby frames may remain in training. Changing resolution and model capacity between runs means quality differences are not a controlled step-count comparison.

## Presentation evidence

The current explanatory slides use Grimes source images, actual registered COLMAP feature tracks, a projection of the recovered sparse points and a matching `front_0005` Brush evaluation render. The RGB-difference heatmap is computed from the source/render pair after resizing the source to 768 × 768; it is a diagnostic image comparison, not a saved training-loss map. Sparse-point plotting uses display filtering and a PCA projection; it is not a survey plan.

## Research role

Reconstruction aims to support movement between viewpoints and spatial interpretation. Original photos remain the detail reference. The research question is whether this appearance layer improves equipment-location and building-information tasks when connected to BIM and evidence-labelled data. That benefit remains to be tested.

## Method references

- [COLMAP documentation](https://colmap.github.io/tutorial): SfM/MVS workflow; this pilot uses the SfM stage.
- [Kerbl et al., 2023 — 3D Gaussian Splatting](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/): representation and rendering foundation.
- [Brush v0.3.0](https://github.com/ArthurBrussee/brush/releases/tag/v0.3.0): actual training software; an independent implementation, not an exact reproduction of the original paper.

Local evidence inspected: `dense/sfm-result.json`, `gaussian-provenance.json`, the pilot README and paired evaluation images. These records establish the reported settings and outputs, not surveyed geometry or complete public reproducibility.
