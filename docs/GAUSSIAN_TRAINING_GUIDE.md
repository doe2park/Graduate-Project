# Gaussian training guide

Train a Gaussian scene for a capture yourself, with a few commands. The pipeline wraps the existing scripts
(`prepare_gaussian_dataset.py`, `train_gaussian.py`, `encode_gaussian.mjs`, `package_gaussian.py`) and the
settings in [GAUSSIAN_RECONSTRUCTION_METHODS.md](GAUSSIAN_RECONSTRUCTION_METHODS.md). The result is an
**experimental appearance layer**, not surveyed geometry.

## Prerequisites

| | macOS (Apple Silicon) | Windows 10/11 x64 | Linux x64 |
|---|---|---|---|
| Python | 3.12 (3.11+ works) | 3.12 | 3.12 |
| Node.js | 22+ | 22+ | 22+ |
| Git | yes | yes (Git for Windows) | yes |
| GPU | M-series (Metal) | Recent NVIDIA or AMD driver (Vulkan/DX12) | Vulkan driver |
| Expected full run (50k steps, 1M splats) | measured 38-118 min on an M4 Pro | not measured yet | not measured yet |

Brush v0.3.0 is downloaded from the official GitHub release and its SHA-256 is verified. Intel Macs and
Windows/Linux ARM have no official build and are not supported. Disk: about 1 GB per run.

## Step by step: VS Code

1. Clone the repo and open the folder in VS Code.
2. `Terminal > Run Task...` and choose **Gaussian: setup** (once). It creates `.venv-gaussian`, installs the pinned
   Python packages and the pinned `gaussian-splats-3d 0.4.7` encoder, and downloads Brush.
3. Run **Gaussian: quick smoke test** (4 stations, 300 steps, about 15 s on an M4 Pro once setup is done). It proves the whole chain on your machine.
   Its output is not publishable.
4. Run **Gaussian: train Sep 17** (or **May 6**, or **Sep 17 (mask nadir)**). Close other GPU-heavy apps first: a full run keeps the GPU busy for
   about 40-120 minutes and the machine will feel slow.
5. Run **Gaussian: preview locally**, pick the capture, open the printed URL.

## Step by step: terminal

```bash
python3 scripts/setup_gaussian_env.py                 # Windows: python scripts\setup_gaussian_env.py
# macOS/Linux
.venv-gaussian/bin/python scripts/run_gaussian_pipeline.py --capture 2026-09-17 --quick
.venv-gaussian/bin/python scripts/run_gaussian_pipeline.py --capture 2026-09-17 [--mask-nadir] [--steps 50000]
.venv-gaussian/bin/python scripts/preview_gaussian.py --capture 2026-09-17
# Windows
.venv-gaussian\Scripts\python.exe scripts\run_gaussian_pipeline.py --capture 2026-09-17 --quick
```

Useful options: `--steps N` (growth schedule scales with it), `--max-splats N`, `--resolution N`, `--brush PATH`,
`--dry-run` (print resolved settings only), `--resume <run folder>`. Per-capture settings live in
`scripts/gaussian_presets.json`; to add a capture, copy a preset and change the manifest, seed GLB, centre station and radius.

Outputs go to `work/gaussian/<capture>/<timestamp>/` (gitignored): `dataset/`, `train/` (Brush log, checkpoints, eval
images), `encoded/`, `package/` (`trained.ksplat`, `mobile.ply`, `viewer.json`) and `run.json`. `viewer.json` records
settings, input hashes, tool versions, per-stage timings and held-out PSNR/SSIM parsed from the Brush log.

If a run is interrupted, finished stages are kept; re-run with `--resume <folder>`. Training itself restarts from
step 0 (the interrupted attempt is kept as `train.interrupted-*`).

## Preview

`Gaussian: preview locally` (or `scripts/preview_gaussian.py`) serves the repo on `127.0.0.1:8000` and prints two URLs:
the standalone layer `scan-splat.html?manifest=...` and `scan-compare.html?mode=splat&manifest=...`. The compare page
honours the `manifest` override on localhost only, and its splat mode uses the **May 6 registration**; for September
results prefer the standalone layer.

## Publishing responsibly

Nothing is published by default. `--publish` prints a checklist and refuses to continue without `--yes`:

- **Privacy:** the panoramas show the camera operator at nadir. Use `--mask-nadir` (drops the two downward-looking faces
  per station) and still inspect floor views for people before publishing. The default is off so the May run stays reproducible; the choice is
  recorded in `viewer.json`.
- **Alignment:** check the capture's registration status (September is `project-frame-provisional`). Describe the layer as an appearance preview.
- **Labels:** keep "experimental" wording; metrics are held-out stations from the same reconstruction, not geometry accuracy.
- **Overwrite:** an existing `scan-assets/gaussian/<capture>/` is never replaced without `--overwrite` (May 6 is already published).
- `--quick` runs can never be published. The scan files are large; commit them deliberately and never write the `data` branch by hand.

## Troubleshooting

- **Out of memory / crash during training:** lower `--max-splats` (e.g. 500000) or `--resolution` (e.g. 512), close other apps, re-run.
- **Very slow:** close other GPU apps (browsers with WebGL tabs, games, video calls); on laptops use the power adapter.
- **Brush autotune cache:** Brush writes a `target/` folder in the working directory for GPU kernel tuning. It is gitignored and safe to delete.
- **macOS refuses to run Brush:** `get_brush.py` ad-hoc signs it; if needed, run `codesign --force --sign - tools/brush/*/*/brush_app`.
- **Encoder error:** re-run setup; `tools/package-lock.json` pins `@mkkellogg/gaussian-splats-3d 0.4.7`.
- **Hash mismatch on download:** delete `tools/brush/` and retry; never use an unverified binary.

## How results are compared

Every 7th station (offset 3) is held out: the evaluation views come from stations never used in
training, so PSNR/SSIM measure novel-view appearance at new positions. They are not controlled across captures (different
scenes, station counts, radii), they share camera poses and seed geometry with the training data, and they are not an
independent test set or a geometry accuracy figure. Compare runs only on the same capture and split.

## Measurements (please add yours)

| Machine | GPU | Capture | Steps / splats | Wall time | PSNR / SSIM |
|---|---|---|---|---|---|
| M4 Pro (owner) | Metal | 2026-05-06 | 50,000 / 1M | 38 min (Brush-reported 2,274 s) | 19.20 dB / 0.798 |
| Windows x64 | | | | | |
