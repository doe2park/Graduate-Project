# Operational Campus Digital Twin from BIM

**UC Berkeley · Civil & Environmental Engineering · M.S. Construction Systems**

A web-based operational digital twin for UC Berkeley's campus buildings, centered on the Grimes Engineering Center. The system integrates BIM model analysis, real-time energy metering (BMO), and interactive web visualization — demonstrating a complete "BIM-to-Operations" pipeline at zero infrastructure cost.

**Live Demo:** [doe2park.github.io/Graduate-Project](https://doe2park.github.io/Graduate-Project/grimes-campus-map-arcgis.html)

---

## System Overview

```
BMO Obvius Meters (154 devices, 26 online)
  → GitHub Actions (Python, every 15 min)
    → JSON Data Store (live + 24hr history + daily archive + weekly report)
      → GitHub Pages (free HTTPS hosting)
        → 5 Web Interfaces
           ├── Campus Map (ArcGIS 2D)
           ├── 3D Viewer (CesiumJS + Google Photorealistic 3D Tiles)
           ├── Energy Dashboard (Chart.js)
           ├── Weekly Report
           └── Grimes MEP Viewer (Three.js + WebXR)
  → Cloudflare Workers AI (Llama 3.1 chatbot)
```

---

## Live Interfaces

| Interface | URL | Technology |
|---|---|---|
| **Campus Map** | [grimes-campus-map-arcgis.html](https://doe2park.github.io/Graduate-Project/grimes-campus-map-arcgis.html) | ArcGIS JS SDK 4.29 |
| **3D Campus View** | [campus-3d.html](https://doe2park.github.io/Graduate-Project/campus-3d.html) | CesiumJS + Google 3D Tiles |
| **Energy Dashboard** | [campus-energy-dashboard.html](https://doe2park.github.io/Graduate-Project/campus-energy-dashboard.html) | Chart.js 4.4 |
| **Weekly Report** | [weekly-report.html](https://doe2park.github.io/Graduate-Project/weekly-report.html) | Vanilla JS |
| **Grimes MEP Viewer** | [grimes-xr.html](https://doe2park.github.io/Graduate-Project/grimes-xr.html) | Three.js + WebXR |
| **AI Chatbot** | [campus-chatbot.ucb-dt.workers.dev](https://campus-chatbot.ucb-dt.workers.dev) | Cloudflare Workers AI |

---

## Campus Map

Interactive 2D satellite map displaying live energy data for 64 UC Berkeley buildings.

- **64 buildings** with coordinates verified from [berkeley.edu/map](https://www.berkeley.edu/map/)
- **26 buildings** with live kW readings from BMO metering, auto-refreshed every 60 seconds
- Category-colored markers with energy-intensity outline (green → gold → red)
- Click any building for popup with department, year built, floors, energy data
- **24-hour time slider** with play button — replay campus energy patterns
- **AI chatbot** powered by Cloudflare Workers AI (Llama 3.1 8B) with local NLP fallback
  - 20+ intents, fuzzy string matching, handles typos and varied phrasing
  - Korean keyword support
  - Time-slider aware — answers reflect currently selected time
- Links to berkeley.edu building pages, energy dashboard, and 3D viewer
- Grimes beacon marker guides users to the full BIM-to-WebXR digital twin

## 3D Campus Viewer

Photorealistic 3D visualization of UC Berkeley campus with live energy overlay.

- **Google Photorealistic 3D Tiles** via CesiumJS — real building textures, trees, terrain
- OSM Buildings fallback when Google Tiles unavailable
- Energy-coded ground circles: size proportional to kW, color by intensity
- Floating labels on building rooftops (visible on zoom-in, fade on zoom-out)
- **24-hour time slider** with stats panel synchronization
  - Total kW, buildings online, daily cost, CO₂ all update with slider position
- Click any building for info popup (name, department, kW, year, floors, cost, CO₂)
- Enhanced rendering: `maximumScreenSpaceError: 4`, FXAA, device pixel ratio scaling

## Energy Dashboard

Real-time analytics with 6 interactive charts.

- **Stats cards:** Campus load (kW), daily cost ($), avg kW/floor, daily energy (MWh)
- **Energy by Category:** Donut chart — Engineering, Science, Humanities, Professional, Student Life, Libraries
- **Top 10 Buildings:** Horizontal bar chart ranked by current kW
- **Campus Load History:** 24-hour line chart with hover crosshair and tooltip
- **Cost per Building:** Top consumers by estimated $/day
- **Energy Efficiency (kW/floor):** Normalized by floor count — identifies truly inefficient buildings
- **Building Age vs Energy:** Scatter plot — year built vs current kW with building metadata on hover
- Auto-refresh every 60 seconds
- `shortName()` mapping with 30+ entries and fuzzy matching

## Weekly Report

Auto-generated 7-day energy summary.

- Weekly stats: average kW, total MWh, cost, CO₂
- Daily breakdown cards with peak times
- Peak vs average comparison charts
- Building weekly rankings table
- Generated from daily JSON snapshot archive

## Grimes MEP Viewer

3D MEP (Mechanical, Electrical, Plumbing) walkthrough of Grimes Engineering Center with live energy data.

- **Three.js** renderer with **WebXR** support (desktop, mobile, VR headset)
- 8 MEP system layers: HVAC Ductwork, HVAC Equipment, Plumbing/Piping, Fire Protection, Electrical, Diffusers/Grilles, Pumps/Valves, Spiral Ductwork
- Toggle individual systems on/off via legend
- View modes: System (color by type), Temperature, Flow, Energy (heatmap)
- **Live BMO data** for electrical components (3 meters: Roof Electric, 480/277V, 208/120V)
- WASD + QE movement, mouse orbit, click any component for sensor panel
- First-person walkthrough mode

### Live Data (BMO Metering — ~70% of UI)

| Meter | Voltage | Data Points |
|---|---|---|
| Meter #3 (Roof Electric) | 480V | kW, current, voltage, power factor, frequency, kWh delivered, peak demand |
| Meter #76 (HVAC/Lighting) | 480/277V | kW, current, voltage |
| Meter #77 (Outlets/IT) | 208/120V | kW, current, voltage |
| Water meter | — | flow rate (cf/m), total consumption (cf) |
| Steam meter | — | total consumption (gal) |

### BIM-Validated Floor Energy Breakdown (~15% of UI)

Derived from analysis of **741,796 BIM elements** in the Revit/Navisworks model. **93 electrical panelboards** were identified and mapped to BMO meters by floor:

| Floor | Meter Sources | Panelboards | Description |
|---|---|---|---|
| **SRV (Roof)** | Meter #3 × 100% | 0 (direct AHU feed) | Rooftop air handling units, exhaust fans |
| **L3** | Meter #77 × 18% | 11 × 208V | Upper floor outlets, IT equipment |
| **L2** | Meter #77 × 35% | 22 × 208V | Mid floor outlets, lab equipment |
| **L1** | Meter #76 × 45% + Meter #77 × 31% | 14 × 480V + 19 × 208V | HVAC, lighting, outlets |
| **B1** | Meter #76 × 55% + Meter #77 × 16% | 17 × 480V + 10 × 208V | MSB, mechanical room, workshop |

**Key finding:** 480/277V panelboards (Meter #76) exist only on B1 and L1. L2 and L3 have exclusively 208/120V distribution. Main switchboards (MSB-1, MSB-2) are located on B1.

### Simulated Data (~5% of UI)

HVAC, plumbing, and fire protection sensor readings shown on component click are simulated placeholders. These are ready for future BAS (Building Automation System) integration. All simulated values are labeled "SIM" in the UI.

---

## Data Architecture

### Automated Pipeline

| File | Description | Update Frequency |
|---|---|---|
| `data/campus_energy.json` | Live snapshot — 26 buildings × kW, cost, CO₂, anomaly flags, prediction | Every 15 min |
| `data/campus_energy_history.json` | 24-hour rolling history — up to 96 data points per building | Every 15 min |
| `data/daily/YYYY-MM-DD.json` | Permanent daily archive — all readings preserved for trend analysis | Append each cycle |
| `data/weekly_report.json` | 7-day summary — avg/peak/min kW, cost, CO₂ per building | Every 15 min |

### BMO Connection

- **System:** BMO Obvius (BuildingManager Online)
- **Auth:** HTTP Basic Authentication
- **Database:** `dbU216ucberkelF682`
- **Devices discovered:** 154 AcquiSuite devices
- **Currently reporting:** 26 buildings
- **Offline:** 12 buildings (hardware disconnected — requires Facilities Services)
- **kW columns parsed:** "kW total (kW)", "Active Power Total (kW)", "kW total", "kW", "kW del-rec (kW)", "Power Total (kW)", "kW del (kW)"

### Features

- **Anomaly detection:** Flags buildings consuming >150% of their 2-hour rolling average
- **Prediction:** Weighted moving average for short-term kW prediction
- **CO₂ estimation:** kW × 24h × 0.21 kg/kWh (California grid average, CARB)
- **Cost estimation:** kW × 24h × $0.15/kWh (PG&E commercial rate)
- **Daily snapshots:** Permanent JSON files for long-term historical analysis

---

## AI Chatbot

Deployed as a Cloudflare Worker using **Workers AI** (free tier, no API key required).

- **Model:** Meta Llama 3.1 8B Instruct (`@cf/meta/llama-3.1-8b-instruct`)
- **Endpoint:** `https://campus-chatbot.ucb-dt.workers.dev`
- **Context:** Sends current energy data + building metadata with each query
- **Time-aware:** Reflects current time slider position
- **Fallback:** Local fuzzy NLP engine with 20+ intents when AI proxy is unavailable
- **Languages:** English and Korean

---

## BIM Model Analysis

The Grimes Engineering Center BIM model (Revit → Navisworks NWD) contains **741,796 elements** across **48 NWC files** from multiple design and construction teams:

| File Code | Firm / Role | Discipline |
|---|---|---|
| `RT` | Rutherford & Chekene | Electrical design |
| `FMB` | Mechanical designer | HVAC / plumbing design |
| `CDC` | Mechanical contractor | HVAC / plumbing construction BIM |
| `PRIBUSS PRAGMATIC` | Pribuss Engineering + Pragmatic PE | Fire protection design + construction |
| `SOM` | Skidmore, Owings & Merrill | Architecture |
| `XL` | — | 3D Grids / coordination |

### MEP Files (35 NWC)

```
Electrical:     00/01/02/03-UCBBE-RT-ELEC.nwc (power distribution)
                00/01/02/03-UCBBE-RT-ELEC-IW.nwc (internal wiring)
                00/01/02/03-UCBBE-RT-ELEC-LTG.nwc (lighting)
                RF-UCBBE-RT-ELEC.nwc (roof electrical)
Fire Protection: 00/01/02/03-UCBBE-PRIBUSS PRAGMATIC-FP.nwc
Mechanical:     00/01/02/03/04-UCBBE-FMB-MECH DUCT.nwc
                00/01/02/03-UCBBE-FMB-MP.nwc (mechanical piping)
                00/01/02/03-UCBBE-FMB-PL.nwc (plumbing)
                B1/L1/L2/L3-UCBB-CDC-MF.nwc (mechanical fabrication)
```

---

## Technology Stack

| Component | Technology | Cost |
|---|---|---|
| 2D Campus Map | ArcGIS JS SDK 4.29 | Free (developer tier) |
| 3D Campus View | CesiumJS 1.119 + Google Photorealistic 3D Tiles | Free (Cesium ion) |
| MEP 3D Viewer | Three.js r160 + WebXR | Free (open source) |
| Energy Dashboard | Chart.js 4.4.1 | Free (open source) |
| AI Chatbot | Cloudflare Workers AI (Llama 3.1 8B) | Free (Workers free tier) |
| Data Pipeline | Python 3.12 + GitHub Actions | Free (GitHub free tier) |
| Hosting | GitHub Pages | Free |
| Metering | BMO Obvius | UC Berkeley infrastructure |
| **Total monthly cost** | | **$0** |

---

## Repository Structure

```
Graduate-Project/
├── grimes-campus-map-arcgis.html    # Campus 2D map with chatbot
├── campus-3d.html                   # CesiumJS 3D viewer
├── campus-energy-dashboard.html     # Chart.js dashboard
├── weekly-report.html               # Weekly report viewer
├── grimes-xr.html                   # Grimes MEP 3D viewer
├── grimes-mep-only.glb              # MEP 3D model (1.7MB)
├── grimes-mep-compressed.glb        # Full building model (57MB)
├── bmo_fetch_campus.py              # BMO data fetcher (26 buildings)
├── generate_weekly_report.py        # Weekly report generator
├── data/
│   ├── campus_energy.json           # Live energy snapshot
│   ├── campus_energy_history.json   # 24hr rolling history
│   ├── weekly_report.json           # 7-day summary
│   └── daily/                       # Permanent daily archives
│       └── YYYY-MM-DD.json
└── .github/
    └── workflows/
        └── bmo-campus-energy.yml    # 15-min cron job
```

---

## Security Notes

The following files contain sensitive data and must NOT be committed to the public repository:

- `.env` — BMO credentials
- `data/building_data.json` — internal building configuration
- `raw_csv/` — raw BMO meter exports

Only code files and auto-generated output files (e.g., `campus_energy.json`) are safe to push.

---

## Future Work

- Restore 12 offline BMO meters (Facilities Services coordination)
- Energy efficiency index: kW/sqft normalization with actual floor area data
- Weather correlation: temperature vs. energy consumption using NOAA data
- Grimes MEP time-linked visualization: pipe colors change by real-time load
- Sub-metering integration: individual panelboard monitoring (93 panels identified)
- BAS integration: real HVAC/plumbing sensor data to replace simulated values
- Monthly automated PDF reports for Facilities Services
- User testing with campus facility managers

---

## Author

**Yoonsung Chung**
M.S. Construction Systems · UC Berkeley CEE
yoonsung_chung@berkeley.edu

---

## Acknowledgments

- UC Berkeley Facilities Services — BMO metering system access
- Prof. Katz — Thesis advisor
- Tianyu — BMO data coordination
- BIM model contributors: SOM (Architecture), Rutherford & Chekene (Electrical), Pribuss Engineering + Pragmatic PE (Fire Protection)
