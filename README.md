# Operational Campus Digital Twin from BIM

UC Berkeley · Civil & Environmental Engineering · Yoonsung Chung · Advisor: Prof. Kenichi Soga

A campus-scale research prototype connecting site appearance, BIM objects and available operating data. Grimes / Bechtel Engineering Center is the detailed pilot. The research asks whether these connections, with explicit evidence labels, help users understand existing buildings with incomplete drawings and sensor coverage.

## Open the live sites

Updated for the September 17, 2026 presentation. These are the canonical public links used by the presentation QR codes.

| Website | Open | Source | What it does |
|---|---|---|---|
| Campus map | [Live map](https://doe2park.github.io/Graduate-Project/grimes-campus-map-arcgis.html) | [HTML](grimes-campus-map-arcgis.html) | Geographic context for 61 campus buildings and available utility readings |
| Campus energy dashboard | [Live dashboard](https://doe2park.github.io/Graduate-Project/campus-energy-dashboard.html) | [HTML](campus-energy-dashboard.html) | Demand trends, building comparisons and reporting availability |
| Element BIM viewer | [Live BIM viewer](https://doe2park.github.io/Graduate-Project/grimes-bim-viewer.html) | [HTML](grimes-bim-viewer.html) | Select floors/layers and inspect individual model objects and their data evidence |
| Scan ↔ BIM comparison | [Live comparison](https://doe2park.github.io/Graduate-Project/scan-compare.html) | [HTML](scan-compare.html) | Captured 360° photos and registered BIM with linked views; optional mesh mode |
| Design vs actual | [Live performance page](https://doe2park.github.io/Graduate-Project/grimes-performance.html) | [HTML](grimes-performance.html) | LEED design context and observed energy, with coverage and modelling limits |

The comparison supplements the four main interfaces. It does not require a Cupix login. The old Cupix iframe comparison is not the current demonstration. Former interfaces such as `campus-3d`, `grimes-xr`, `weekly-report` and `twin-viewer` redirect to the maintained pages; they are not separate active products.

### Suggested demonstration

1. Start with the campus map to locate Grimes.
2. Open the energy dashboard to explain the available building-level measurements.
3. Use the BIM viewer to select an object and distinguish its identity/design properties from its operating-data context.
4. Open Scan ↔ BIM to compare the same registered location. Photo walking moves along recorded capture stations with transitions; mesh mode allows free movement.
5. Use Design vs Actual to discuss energy performance and the limits of available evidence.

On narrow screens the comparison stacks its panes vertically and uses smaller panorama derivatives. Device memory and WebGL support affect large-model loading. Browser viewport tests do not establish compatibility with every physical phone.

## Data and evidence

```text
UC Berkeley BMO utility meters
  -> scheduled GitHub Actions (every 15 minutes)
  -> JSON on the machine-written data branch
  -> public static HTML interfaces on GitHub Pages
```

The current pipeline retrieves actual BMO utility observations. Direct BAS/BACnet device-point integration is not implemented. Scheduled collection does not guarantee every meter is online or every observation is fresh.

- **Measured:** three Grimes building electricity meters. Showing a meter total in an object card provides building/feeder context, not a direct measurement of that object.
- **Modelled:** provisional design-weighted allocations. Meter 77 uses design VA and meter 3 uses design CFM. These are uncalibrated scenarios, not verified device consumption or circuit membership.
- **Meter 76 is not apportioned:** no defensible allocation evidence is available.
- **Inferred:** derived relationships such as some floor assignments. Preserve their provenance and uncertainty.
- Panel schedules, reviewed equipment relationships and BAS point mappings are still needed for verified asset-to-feed connections. Missing/stale values must not become live zero readings.

## BIM identity and rendering

Ten element layers contain 66,620 identities with geometry. Original GLB node identifiers bind to JSON sidecars. Revit-derived dbIds and fabrication CAD entity identities have different source hierarchies. Identity is scoped to the source model and revision.

The viewer batches geometry at runtime while preserving picking through primitive ranges. It offers floor/type/layer filters and Show all / Hide all element controls. The architectural Building Shell feature was removed. Interior geometry in the scan comparison provides separate spatial context.

Never rename identity nodes, flatten away identity, or re-encode existing Draco geometry when subsetting. See [AGENTS.md](AGENTS.md) for the full invariants and development workflow.

## Scan, photos and alignment

- Public photo mode contains 100 recovered 4096×2048 panoramas and 2K mobile derivatives. The source inventory has 217 positions; it is not 217 recovered images.
- Photo transitions follow an inferred adjacency graph. Intermediate blends are not measured parallax or a new continuous reconstruction.
- The accepted registration uses axis conversion, pose search and trimmed point-to-point ICP constrained to yaw and XYZ translation, with metric scale fixed.
- The internal nearest-point median residual is about 0.13 m. This is not independently surveyed accuracy and does not validate every object association.
- Linked camera poses use the forward/inverse registration so either view can drive the comparison.

[Registration methodology](docs/SCAN_BIM_REGISTRATION.md) · [Captured panorama viewer](docs/CAPTURED_PANORAMA_VIEWER.md) · [Public comparison](docs/PUBLIC_SCAN_COMPARISON.md)

## Local Gaussian experiment

The repository includes a Gaussian viewer and reconstruction tools, but the trained assets remain local under ignored `capture-local/`. Public QR codes intentionally open the photo/mesh comparison. A local `?mode=splat` URL is not a public Gaussian deployment.

The experiment uses Brush 0.3.0 and exported image poses. Blur and floaters remain; it is not a claim of photograph-quality rendering, surveyed geometry or a complete camera-only reconstruction pipeline.

[Methods, papers and metrics](docs/GAUSSIAN_RECONSTRUCTION_METHODS.md)

## New floors and buildings

Each capture gets an isolated package with its own poses, scale, registration and reviewed data links. The tooling does not inherit the Grimes transform or meter associations. Raw INSV needs reconstruction; NWD/IFC needs conversion before browser intake.

[Capture onboarding](docs/CAPTURE_ONBOARDING.md) · [MEP recovery](docs/MEP_RECOVERY.md)

## Repository map

| Path | Purpose |
|---|---|
| Root HTML pages | Self-contained public interfaces |
| `buildings/grimes/` | Element GLBs and identity/design sidecars |
| `scan-assets/` | Public scan/interior assets and captured panorama derivatives |
| `alignment-analysis/accepted-registration.json` | Accepted scan-to-BIM transform |
| `scripts/` | Collection, extraction, provenance, capture and reconstruction tools |
| `tests/` | Rendering/identity, data, registration and capture checks |
| `docs/` | Methods, decisions, limitations and onboarding documentation |
| `.github/workflows/` | Automated data collection |
| `worker/` | Optional Cloudflare chatbot |

`main` holds code and static configuration. The orphan `data` branch holds automated outputs and must not be edited by hand. Raw captures, local Gaussian assets and credentials are not deployment inputs.

This is a research prototype for monitoring and investigation. Automated building control and a completed user study are not implemented.
