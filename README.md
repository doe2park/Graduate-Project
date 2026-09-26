# Campus Digital Twin · Grimes Engineering Center

**Yoonsung Chung · UC Berkeley Civil & Environmental Engineering**

Advisor: Prof. Kenichi Soga · Research status updated September 25, 2026

A research prototype linking **captured site appearance, BIM objects and operational data**, with explicit labels for measured, modelled and inferred information.

> In existing buildings with incomplete drawings and sensor coverage, does connecting these sources and showing their evidence help people understand building conditions faster and more accurately?

**For research collaborators:** [Start here](docs/RESEARCH_COLLABORATION.md) · [Data and JSON guide](docs/DATA_SHARING.md) · [Reconstruction experiments](docs/RAW_VIDEO_RECONSTRUCTION.md)

## Explore the public demonstrations

No installation is required. Open a live page, rather than its HTML source on GitHub. Desktop is recommended for the full BIM demonstration; mobile layouts and reduced scan assets are provided, but large-model loading depends on device memory and WebGL support.

| Interface | Live demonstration | Source | Purpose |
|---|---|---|---|
| Campus map | [Open map](https://doe2park.github.io/Graduate-Project/grimes-campus-map-arcgis.html) | [HTML](grimes-campus-map-arcgis.html) | Geographic context and available utility observations for 61 buildings |
| Energy dashboard | [Open dashboard](https://doe2park.github.io/Graduate-Project/campus-energy-dashboard.html) | [HTML](campus-energy-dashboard.html) | Compare demand, building categories and reporting availability |
| Weekly history | [Open weekly report](https://doe2park.github.io/Graduate-Project/weekly-report.html) | [HTML](weekly-report.html) | Review archived observations, sample counts and seven-day windows |
| Element BIM viewer | [Open BIM](https://doe2park.github.io/Graduate-Project/grimes-bim-viewer.html) | [HTML](grimes-bim-viewer.html) | Select floors, layers and individual elements; inspect properties and data provenance |
| Scan ↔ BIM | [Open comparison](https://doe2park.github.io/Graduate-Project/scan-compare.html) | [HTML](scan-compare.html) | Compare captured panoramas or scan mesh with linked BIM views |
| Design vs actual | [Open performance](https://doe2park.github.io/Graduate-Project/grimes-performance.html) | [HTML](grimes-performance.html) | Examine LEED design context against available operating evidence |

**Suggested tour:** campus map → energy dashboard / weekly history → BIM object selection → Scan ↔ BIM → performance. The scan comparison does not require a Cupix login.

## What is implemented—and what remains experimental

| Area | Current status | Evidence boundary |
|---|---|---|
| Element BIM | Ten layers, 66,620 identities with geometry; filtering, picking and runtime batching | Design properties do not prove installed condition or sensor coverage |
| Operating data | Scheduled BMO collection and archived observations | Not a direct BAS/BACnet connection or continuous verified meter history |
| Public scan comparison | September 17 capture is the default; May 6 baseline remains selectable | September alignment is provisional; photo transitions are not measured parallax |
| Gaussian reconstruction | Two distinct local research tracks: exported poses and independent raw-video SfM | Trained scenes remain local; public links open photo/mesh modes |
| Research evaluation | Task-based comparison proposed | No completed user study or demonstrated improvement in decision accuracy yet |

## Architecture and data honesty

```text
BMO utility observations → scheduled GitHub Actions → JSON on data branch
                                                        ↓
BIM GLBs + element-property JSON → static web interfaces ← scan photos / mesh
```

The collection workflow is scheduled every 15 minutes. This does not guarantee that a meter is online or its reading is fresh. GitHub Pages serves the HTML and public assets; geometry and JSON are separate files, not embedded entirely in the HTML.

- **Measured:** three Grimes building electricity meters. A total shown beside a BIM element is meter context, not a measurement of that element.
- **Modelled:** uncalibrated design-weighted allocations—meter 77 by design VA; meter 3 by design CFM. These do not establish circuit membership or device consumption.
- **Meter 76 is not apportioned:** defensible allocation evidence is missing.
- **Inferred:** relationships such as some floor assignments; preserve the source and uncertainty.
- Missing/stale values must not become live zero readings. Panel schedules, reviewed equipment relationships and BAS point mappings are needed for verified asset-to-feed connections.

## Scan registration and reconstruction

The public comparison contains separate May 6 and September 17 packages, each with 100 recovered panoramas. The May source inventory lists 217 positions; that is not 217 recovered images. The September package is not claimed to cover the entire building or all server imagery.

The May registration uses axis conversion, pose search and trimmed point-to-point ICP constrained to yaw and translation, with metric scale fixed. Its approximately 0.13 m internal median nearest-point residual is **not surveyed accuracy**. September uses a separately labelled provisional project-frame alignment; May's validation status must not be transferred to it.

Photo mode moves between recorded stations with blends. Mesh mode supports free translation within usable geometry. Linked cameras do not themselves prove registration accuracy.

The separate **Cupix-independent September raw-video pilot** uses Insta360 Studio → FFmpeg perspective images → COLMAP SfM → Brush Gaussian optimization. It registered 142 of 144 views and produced 7,565 sparse points and an 8,000-step Gaussian result. Metric scale and BIM alignment remain unvalidated; no dense mesh was generated in that pilot.

[Scan/BIM registration](docs/SCAN_BIM_REGISTRATION.md) · [September public capture](docs/CAPTURE_UPDATE_20260917.md) · [Raw-video pilot](docs/RAW_VIDEO_RECONSTRUCTION.md) · [Earlier posed-image Gaussian experiment](docs/GAUSSIAN_RECONSTRUCTION_METHODS.md)

## Repository guide

| Location | Contents |
|---|---|
| Root HTML files | Public interfaces; legacy pages may redirect |
| `buildings/grimes/` | BIM geometry and element-property sidecars |
| `scan-assets/` | Published scan meshes, photos and capture manifests |
| `alignment-analysis/accepted-registration.json` | May registration record |
| `scripts/` and `tests/` | Processing, provenance and validation tools |
| `docs/` | Methods, evidence, limitations and collaboration guidance |
| `.github/workflows/` | Automated collection |
| `worker/` | Optional Cloudflare chatbot |

`main` contains the website and static assets. The orphan **`data` branch is machine-written** and must not be edited manually. Raw INSV/E57 files, full private property exports, local training outputs and credentials are not included by this documentation update.

### Run locally

```bash
git clone https://github.com/doe2park/Graduate-Project.git
cd Graduate-Project
python3 -m http.server 8000
```

Open `http://localhost:8000/grimes-campus-map-arcgis.html`. Internet access is needed for CDN libraries and online data. Cloning the repository also downloads its tracked public assets; local Gaussian training outputs are not included.

For implementation changes, read [AGENTS.md](AGENTS.md). Preserve GLB identity nodes and existing Draco bytes; sidecars bind to source-scoped element identifiers. See [MEP recovery](docs/MEP_RECOVERY.md) and [new capture onboarding](docs/CAPTURE_ONBOARDING.md).

## Copyright and reuse

© 2026 Yoonsung Chung. All rights reserved for author-owned contributions. Public viewing and sharing links are welcome; reuse requires permission unless an applicable exception or existing license permits it. Third-party models, captures, data and dependencies retain their respective rights. See [LICENSE.md](LICENSE.md). Public GitHub viewing/forking rights remain unaffected.
