# Raw Insta360 → posed panoramas (local, Cupix-free)

`scripts/raw360_pipeline.py` turns a raw Insta360 ONE X2 dual-INSV recording into an `images.json` folder that
`scripts/capture_import.py prepare --source <folder>` imports unchanged. Local open-source tools only: FFmpeg
(`v360`), COLMAP through pycolmap, NumPy, Pillow. No cloud service, Cupix or Insta360 Studio. Cupix exports are used
only by `validate`, never as input. Status: **smoke-tested on 12 s of the Sep 17 Level 1 clip; no full-floor run yet.**

## Setup

```sh
python3 -m venv work/raw360-venv
work/raw360-venv/bin/pip install pycolmap numpy pillow   # tested: pycolmap 4.2.1 (COLMAP 4.2.1), numpy 2.5.4, Pillow 13.0.0
```

FFmpeg 8.1.1 (`/opt/homebrew/bin/ffmpeg`; override with `FFMPEG`/`FFPROBE`). `work/` and `capture-local/` are gitignored.

## Stages

| Stage | Does | Output (under `--work`) |
|---|---|---|
| `probe` | ffprobe both lens files, SHA-256, parse the INSV trailer: lens calibration, per-frame timestamps, IMU | `probe.json`, `imu.npz` |
| `frames` | low-res stitch of every frame in range → IMU walking cue + yaw-aligned image change + sharpness → keyframes; full-res stitch (ffmpeg `v360` dual fisheye → equirect); SfM inputs + masks | `frames.json`, `frame-scores.json`, `panos/`, `views/`, `masks/` |
| `sfm --method M` | shared SIFT features + matching (sequential overlap + appearance loop candidates), then backend `M` with rig constraint | `sfm/common-<hash>/`, `sfm/M/sfm-result.json`, `points.npy`, `model/` |
| `scale` | level by mean panorama up axis; metric scale from camera height above the local floor; optional landmarks | `sfm/M/scale.json` |
| `export` | `images.json` + equirect JPEGs + `provenance.json` | `--out` folder |
| `privacy` | blur faces and whole people in equirect panoramas, write per-image SfM person masks and a privacy report | `--out` folder (blurred copies, `privacy-report.json`), `--masks-out` |
| `validate` | compare to a reference manifest by video frame number | `sfm/M/validation.json` + one row in a runs table |

### Key choices

- **Stitch**: `_00_` rotated clockwise, `_10_` counter-clockwise, `hstack`, `v360=input=dfisheye`. FOV is the
  equidistant least-squares fit to the camera's own Mei-model calibration in the trailer (196.6°, max model error
  12 px at 2880 px for θ ≤ 90°). The `_10_` lens lands at the panorama centre (+X). Seams are not blended or
  parallax-corrected; close objects show seam offsets.
- **Pose convention**: E57 spherical (image centre +X, left +Y, top +Z), quaternion `[x,y,z,w]` world-from-panorama,
  world Z-up metres; `capture_import` converts to Y-up. Origin = floor below the first registered station.
- **Keyframes**: cumulative motion = max(normalized IMU walking cue, normalized yaw-aligned image change), equal
  steps, sharpest frame in each window, `--min/max-gap` guards. Motion is a proxy for distance, not a measured distance.
- **SfM input** (`--view-mode`):
  - `pinhole-rig` (default): 4 (or `--views N`) pinhole views, 100°, rendered from each equirect; one rig per
    panorama with shared centre and fixed rotations.
  - `fisheye-rig`: no stitching in SfM; each lens is an `OPENCV_FISHEYE` camera (initial f from the trailer fit,
    intrinsics and lens-to-lens pose refined in BA, rays ≤ 88° only). **Better on the smoke test** (table below).
- **Matching**: imported pairs = sequential overlap (`--overlap`, panoramas) + top-k yaw-invariant appearance
  candidates (`--loops`, `--loop-min-separation`). No vocabulary-tree download. Same database for all backends.
- **Masks**: nadir cone (`--nadir-deg`, default 40°) and a static-region detector (pixels that stay unchanged while
  walking, e.g. the stick). Hook: `--extra-mask-dir` with per-panorama equirect PNG masks (white = keep), e.g.
  from the `privacy` step (`--masks-out`). Exported panoramas contain the operator unless `privacy` is run on them.

### SfM backends

| Method | Status |
|---|---|
| `colmap-incremental` | Implemented: pycolmap incremental mapper, rig-constrained, fixed pinhole intrinsics |
| `colmap-global` | Implemented: `pycolmap.global_mapping` (GLOMAP integrated in COLMAP 4), rig-constrained. Unstable here |
| `opensfm-spherical` | Planned hook: OpenSfM with native `spherical` camera on the equirects |
| `stella-vslam` | Planned hook: stella_vslam (equirect camera) for tracking/keyframe selection, then COLMAP BA. Not installed |

Each backend writes the same `sfm-result.json`, so `scale`/`export`/`validate` are shared.

### IMU (INSV trailer, `_00_` file)

Observed ONE X2 layout (interpreted, not vendor-documented): record `0x300` = u64 ms + accel xyz (g) + gyro xyz
(rad/s), ~125 Hz; `0x600` = one u64 ms timestamp per video frame (500 ms apart: the clip is a 2 fps time-lapse,
386 s of walking in 25.9 s of video); `0x101` = metadata incl. per-lens Mei calibration. Currently used for the
walking cue and as an **independent check** (gyro vs SfM relative rotations after a fitted hand-eye rotation;
accelerometer gravity vs reconstructed up). Not yet used as a constraint in BA. A gravity prior (GLOMAP
`rotation_averaging.use_gravity`) or rotation priors are the next step.

## Privacy step (blur faces and people) - `privacy`

Replaces what Cupix did (people blurred in its exports). **Status: code and synthetic tests done; not yet run with real
models (see "Models").** Place in the chain:

```
frames  ->  privacy --masks-out M   ->  frames --extra-mask-dir M  ->  sfm ...   (people excluded from SfM features)
export  ->  privacy --in <export> --out <blurred copy>  ->  manual review  ->  publish only the blurred copy
```

Masks before SfM (re-run `frames` or reuse its panoramas with `--extra-mask-dir`); blur after `export` and always
before anything is published or shared. Originals are never overwritten (`--out` must be a new folder).

```sh
work/raw360-venv/bin/python scripts/raw360_pipeline.py privacy --in capture-local/raw360-sep17-smoke-v2 \
  --out capture-local/raw360-sep17-smoke-v2-blurred --masks-out work/raw360/privacy-masks \
  --face-model work/raw360-models/face_detection_yunet_2023mar.onnx \
  --person-model work/raw360-models/object_detection_yolox_2022nov.onnx --max-images 20
```

How it works: each panorama is rendered into 11 perspective crops (6 horizon at 100 deg, up, down, and 3 at -50 deg
pitch to see the operator under the camera), YuNet (faces) and YOLOX class "person" run on every crop, and each box is
expanded (faces +50 %, people +15 % per side) and mapped back to the panorama by **inverse projection**, which is exact
across the +-180 deg seam and at the poles. Each region gets a Gaussian blur plus pixelation sized to the region; pixels
outside the regions are byte-identical to the input. Per-image masks (`<stem>.png`, white = keep, black = person/face)
have the `--extra-mask-dir` format. `--always-blur-nadir-deg N` additionally blurs the cone around straight down.

`privacy-report.json` (schema `raw360-privacy/1`, written beside the blurred images): images processed, raw detections
per kind, approximate distinct faces/persons (merged by angular distance), per-detection view/azimuth/elevation/size,
blurred pixel fraction, model file info and parameters. **An image is flagged for manual review when nothing was
detected below `--nadir-flag-deg` (default -50 deg elevation)**, i.e. the operator under the camera was probably missed.

**Limits - manual review is required before publishing.** Detection is automatic and will miss people (tiny, occluded,
partial, odd poses, stitch seams, reflections, photos/screens showing faces). Never describe the output as 100 %
anonymised; the report states `manualReviewRequired: true`. Check every blurred image (including unflagged ones) at
full resolution, and add a manual blur where needed.

### Models

Local, CPU (OpenCV DNN), permissive licences, small. Not committed; download only from the official OpenCV Zoo
(https://github.com/opencv/opencv_zoo) into `work/raw360-models/` (gitignored), and `pip install opencv-python-headless`
(Apache-2.0) into `work/raw360-venv` only.

| Use | File | Source path in opencv_zoo | Licence | Size | sha256 |
|---|---|---|---|---|---|
| Faces | `face_detection_yunet_2023mar.onnx` | `models/face_detection_yunet/` | MIT | about 0.2 MB (expected) | recorded by the run in `privacy-report.json` -> `models` |
| People | `object_detection_yolox_2022nov.onnx` | `models/object_detection_yolox/` | Apache-2.0 | about 35 MB; an `_int8` variant is about 9 MB (expected) | same |

Sizes and paths above are from memory of the Zoo layout and **have not been verified**; the exact URL, byte size and
sha256 must be filled in here from the first real download (the report records file name, bytes and sha256 on every run).

Tests (no model needed): `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_raw360_privacy`.

## Metric scale

1. **Camera height** (default): per station, sparse points within `0.75 × median station step` horizontally and
   below the camera; the lowest 30 % are fitted with a local plane evaluated under the camera; `scale = height /
   median distance`. Local floors tolerate the raked auditorium. Record the measured height with
   `--camera-height 1.62 --height-source "tape, 2026-..."`. Default 1.6 m is an assumption.
2. **Landmarks** (`--landmarks file.json`): `pairs`/`checks` (`scan` in the export Y-up frame ↔ `bim`, Y-up
   metres) → Umeyama similarity with fit and independent-check residuals; or `distances` (`a`, `b`, `metres`) from
   laser/tape for scale only. Picking scan points is manual today.

Never report these as surveyed accuracy.

## Smoke test (Sep 17 L1, frames 0–358 = 12 s of video, 2026-10-18)

Full chain `probe → export → validate` took 107 s wall time (M4 Pro, CPU only). Reference: Cupix manifest, matched by
`sourceFrame = 0-based frame + 1`; exact frames plus poses interpolated between keyframes ≤ 10 frames apart.

| Run | Registered panos (images) | Reproj px | Scale vs Cupix fit | Pos. median / p90 m (n) | Heading median deg | Gyro vs SfM (hand-eye residual median) |
|---|---|---|---|---|---|---|
| pinhole-rig, incremental | 19/54 (76/216) | 1.06 | 1.12 | 0.53 / 0.90 (15) | 3.5 | 1.4° |
| pinhole-rig, global | 19/54 (76/216) | 1.12 | 1.07 | 0.48 / 1.00 (15) | 3.5 | – |
| **fisheye-rig, incremental** | 19/54 (38/108) | 0.90 | 1.10 | **0.17 / 0.31 (15)** | 4.2 | **1.0°** |

All registered panoramas come from the dark auditorium section (frames 167–293). A second, unmerged model covers the
bright lobby; the doorway (auto-exposure jump), dark/blurred frames and white corridor walls break continuity.
Global mapping produced broken geometry on two other keyframe sets. "Scale vs Cupix" ≠ 1 means camera-height scale
differs by 7–12 % from Cupix's scale with the unmeasured 1.6 m default. All runs: `work/raw360/runs-benchmark-v3.md`.

## Capture requirements for this pipeline

- Stop-and-go: stand still ~1 s every 2–3 m; walk slowly through doors and turns. Time-lapse mode is fine (the
  trailer gives frame times), but normal video gives more frames near doorways.
- Constant stick height; **measure** camera-lens height above the floor; keep the stick vertical.
- Lights on where possible; avoid moving between very dark and bright spaces without pausing on both sides.
- Loop back to the start (and cross earlier paths) for loop closure.
- Landmarks: photograph ≥ 3 spread fit landmarks + independent checks (column/door corners), with laser distances
  between some of them; note which station shows each.
- Keep both `_00_` and `_10_` INSV files (the `_00_` file carries IMU and calibration).

## Full-floor run (not yet executed)

```sh
R="/Users/yschung/Desktop/Research stuff/Raw Data/Insta 360 X2 Scan"; W=work/raw360/sep17-full
P() { work/raw360-venv/bin/python scripts/raw360_pipeline.py "$@"; }
P probe --work $W --front "$R/VID_20260917_134908_00_013.insv" --back "$R/VID_20260917_134908_10_013.insv"
P frames --work $W --count 100 --max-gap 10 --view-mode fisheye-rig
P sfm --work $W --method colmap-incremental --dsp --max-runtime 1800
P scale --work $W --method colmap-incremental --camera-height <measured> --height-source "<how measured>"
P export --work $W --method colmap-incremental --out capture-local/raw360-sep17-full
P validate --work $W --method colmap-incremental
python3 scripts/capture_import.py prepare --source capture-local/raw360-sep17-full \
  --output capture-local/raw360-sep17-full-review --building grimes --level L1 --date 2026-09-17
```

Expected runtime ≈ 3–6 min for ~120 keyframes (stages scale roughly linearly; extrapolated, not measured). Expect
the same lighting breaks: several disconnected models, only the largest exported.

## Limits

Not surveyed; reference errors are relative to Cupix's own reconstruction. Stitch seams are uncorrected; lens frame
sync between `_00_` (775 frames) and `_10_` (774) is assumed index-aligned. Only the largest model is exported.
Heading validation uses image correlation against Cupix panoramas and can fail on low texture. No route graph is
written; use `capture_import --route` after review.

Tests: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_raw360_pipeline`.

Privacy defaults (updated 2026-10-18 after the first real run): face score 0.85 and faces wider than 25 deg are dropped
(at score 0.6 YuNet returned 45-68 deg 'faces' on ceiling arcs and seat rows in the auditorium); the cone within 35 deg
of straight down is always blurred because the operator stands there and was missed by detection in 7 of 20 test images.
Smoke result on 20 Sep 17 panoramas: 0 face boxes, 21 person boxes, operator covered in the images viewed; 82 s on CPU.
