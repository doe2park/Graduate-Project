# Scan/BIM registration method and evidence

Recorded 2026-09-10. Scope: Grimes Level 1, two May 6, 2026 scan GLBs and existing BIM viewer coordinates. This documents the actual local computation, not a new registration run.

## Current result and distinction from legacy Cupix calibration

The live [registered comparison](https://doe2park.github.io/Graduate-Project/scan-compare.html) uses [accepted-registration.json](../alignment-analysis/accepted-registration.json). The older Cupix panorama/camera calibration near -135 degrees belongs to a different input frame and is not the accepted transform for these exported scan GLBs. Do not reuse that value as the current scan registration.

## Method

1. Convert exported scan geometry from Z-up to Y-up with an X rotation of -90 degrees. The BIM reference is sampled in the existing viewer world. The historical reference extraction used architectural geometry with rotation Y = pi and offset (-35.28, -97.16, 28.60). This offline reference use does not restore the removed Building Shell feature.
2. Sample surface geometry and reduce point density by voxel bins. First search the horizontal plan using wall samples, eight initial yaw angles and a grid of translation seeds. Nearest-neighbor fitting provides candidate horizontal poses. The later refinement starts near yaw 0.2 degrees and X/Z (-35.23, -25.086), trying five height offsets (0, 0.5, 1, 1.5, 2 metres).
3. Refine with trimmed point-to-point ICP: a SciPy cKDTree finds nearest BIM reference points, retain distances below min(2 metres, the 65th percentile), then solve horizontal yaw and XYZ translation from centered corresponding points. Iterate up to 40 times, stopping when translation change plus angular change is below 1e-5. Scale remains 1. This is a constrained four-parameter rigid registration, not unrestricted six-degree-of-freedom ICP.
4. Refinement restricts BIM sample heights to 4.7–10 m and scan sample heights to 3.5–7.6 m in their respective converted frames. Voxel sizes are 0.12 m (BIM) and 0.14 m (scan). Every third scan sample trains the fit, with the next sample used for evaluation (31,319 each). Candidates are ranked by evaluation-set p80 nearest-point distance.
5. Check sensitivity by partitioning the scan into four X/Z zones, fitting three zones and evaluating the fourth. That check uses 0.14 m BIM and 0.18 m scan voxel spacing, then every second scan point. Its initial pose comes from the accepted full-data result, so this is an internal spatial sensitivity check, not independent validation.

## Accepted transform

After the Z-up conversion, column-vector convention:

```text
p_bim = R_y(theta) p_scan + t
R_y = [[cos(theta), 0, sin(theta)],
       [0,          1, 0],
       [-sin(theta),0, cos(theta)]]
theta = 0.08168900948820965 degrees
t = [-35.23265480091985, 0.6271199075628591, -25.106843949799668] metres
scale = 1
```

The comparison maps camera positions with this transform and camera orientations with the corresponding yaw quaternion. Reverse navigation uses the inverse transform. Field of view and zoom are synchronized. This preserves alignment while either pane drives navigation; it does not infer device identity from the scan.

## Internal geometric results

| Quantity | Result |
|---|---:|
| Median nearest-reference-point distance | 0.12927 m |
| 80th-percentile distance | 0.48278 m |
| Points within 0.25 m | 70.24% |
| Points within 0.50 m | 80.57% |
| Four spatial-zone medians | 0.11085–0.23035 m |
| Four spatial-zone p80 distances | 0.17347–0.95024 m |
| Translation shift on spatial refits | 0.00206–0.05703 m |

These are nearest-point residuals against sampled model geometry, not surveyed positioning accuracy, point-to-plane errors, or verified equipment-location errors. The candidate-selection set also ranks initializations, so it is not an untouched test set. Uneven overlap, scan gaps, furniture differences, and repeated geometry can affect the result. No independent survey anchors were used. Source GLB coordinates are not stretched, and element identities are unchanged. Mobile texture derivatives preserve geometry and use the same registration.

## Reproducibility and durable evidence

- [Accepted transform and zone results](../alignment-analysis/accepted-registration.json)
- [Historical scripts, outputs, hashes and rerun limitations](../alignment-analysis/method-archive/README.md)
- [Source GLB hashes](../scan-assets/provenance.json)
- [Camera synchronization implementation](../scan-compare.html)
- [Runtime interaction test](../tests/registered-comparison.cjs)

The algorithm and numerical outputs are archived. The temporary point-sample inputs are not in this public repository, and the historical scripts use local paths. A fresh clone is therefore not yet sufficient for end-to-end recomputation. Preserve or regenerate the exact samples and package a standalone pipeline before claiming full reproducibility. Camera synchronization tests verify the application of the transform, not physical correctness of the registration.

## Next validation

Obtain independently measured, well-distributed fixed control points across Level 1, verify units and coordinate origins, and evaluate points excluded from fitting and candidate selection. Report spatial error distributions separately from camera-sync correctness and device-to-sensor linkage.

## Suggested spoken answer

“I used geometry-based registration. After converting the scan to the viewer coordinate convention, I used constrained ICP to estimate horizontal rotation and three-dimensional translation, with scale fixed. I then applied that transform to both camera position and orientation to keep the views aligned. The median internal nearest-point distance was about 13 centimetres, but independent survey control points are still needed to establish real-world accuracy.”
