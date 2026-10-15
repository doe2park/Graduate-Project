# Where collaborators can help

Each task is self-contained, produces evidence the project does not yet have, and has a concrete entry point in this repository. Nothing here requires access to private data. Ask the owner before publishing new captures of people or rooms.

| # | Task | You need | Entry point | Typical effort | Result |
|---|---|---|---|---|---|
| 1 | **Independent check points for scan↔BIM registration.** Measure ≥8 well-spread Level 1 landmarks (column corners, door jambs, floor drains) and record them in both the scan and BIM frames. | Tape or laser distance meter, a floor plan | `docs/SCAN_BIM_REGISTRATION.md`, `scripts/capture_import.py fit` | 2–3 h on site | Surveyed per-axis error instead of the internal ≈0.13 m residual |
| 2 | **Capture another floor or room.** 360° stations every 2–3 m with overlap, following the onboarding guide. | 360 camera or phone, building access | `docs/CAPTURE_ONBOARDING.md`, `scripts/capture_import.py prepare` | 1–2 h capture + 1 h import | A new isolated capture package and review page |
| 3 | **Link real sensors to BIM elements.** Turn a MODELLED or NO FEED card into a LIVE one by binding a documented feed (panel schedule circuit, BAS/BACnet point) to an element ID. | Facilities contact or panel schedules | `buildings/grimes/element-feeds.json`, `docs/ELEMENT_FEEDS.md` | 1 h per system once data is available | Element-level LIVE readings in the Walk info cards |
| 4 | **Meter data quality check.** Verify each building's configured BMO meters; investigate implausible zeros (e.g. buildings reporting 0.0 kW while online). | BMO dashboard access | `bmo_fetch_campus.py` building table, `data` branch JSON | 2–4 h | Corrected meter inventory; fewer partial campus totals |
| 5 | **Gaussian reconstruction on new captures.** Train with the same settings, compare views held out by area, and try a geometry-aware variant (e.g. 2D Gaussian Splatting on Colab) against BIM surfaces. | Apple Silicon Mac or Windows PC with a recent GPU | `docs/GAUSSIAN_TRAINING_GUIDE.md` (one-command pipeline), `docs/GAUSSIAN_RECONSTRUCTION_METHODS.md`, `scripts/run_gaussian_pipeline.py` | ~40 min training per scene on an M4 Pro | Comparable appearance metrics and a first geometry comparison |
| 6 | **Headset inspection study.** Run the same inspection route on a Quest with a few participants; record task completion, correct component IDs and frame intervals. | Quest 2/3, 3–5 participants | Quest validation protocol (presentation slide "Quest validation task") | Half a day | First physical-headset measurements |

Ground rules: keep source GLBs, node names and material values unchanged; label measured / modelled / inferred values honestly; never write the machine-owned `data` branch by hand; never commit credentials.
