# LEED + LCA Integration — Presentation Notes

> Bechtel Engineering Center (Grimes Hall) digital twin. LEED submittal data wired into the live popup, in two presentation modes.

---

## Where to view

| | URL |
|---|---|
| **Live map** | https://doe2park.github.io/Graduate-Project/grimes-campus-map-arcgis.html |
| **Preview** (panels in popup context) | https://doe2park.github.io/Graduate-Project/leed-lca-preview.html |
| GitHub repo | https://github.com/doe2park/Graduate-Project |

In the live map: click the **Grimes / Bechtel** marker → toggle **Engineer ↔ Public** at the top-right.

---

## What materials were received

Two LEED submittal packages, both for **LEED Project #1000171106** (Bechtel Engineering Center Addition & Renovation). Prepared by **SOM** (architect) and **Sage Green Strategies** (LEED consultant), submitted to USGBC in November 2023.

### Package 1 — Energy Performance

**Core file**: `20240529_Bechtel_LEEDv4MinEnergyPerfCalc.xlsm`

Compliance workbook for LEED v4 BD+C's **EAp2 (Energy Performance prerequisite)** + **EAc1 (Optimize Energy Performance credit)**. Contains the building's full operational-energy model:

- 11 end-uses (heating, cooling, pumps, fans, lighting, receptacles, IT, elevators, water heating, etc.)
- Two scenarios compared per end-use:
  - **ASHRAE 90.1-2010 baseline** — code minimum
  - **Proposed** — as-designed, simulated in eQuest
- Annual kWh + peak kW for each
- **Bechtel result**: baseline 1,501 MWh/yr → designed 824 MWh/yr → **45% modeled savings**

### Package 2 — Life-Cycle Submittal (Structural Reuse)

**Core file**: `UCB _LEED_LCA credit.xlsx`
**Supporting files**: `LCA Credit - Structural Reuse.pdf` (SOM drawings), `v4.1-Building Life-Cycle Impact Reduction.pdf` (LEED rulebook), `creditForm.pdf` (submittal form), plus archive PDFs

Compliance package for the LEED v4.1 BD+C **MR Credit "Building Life-Cycle Impact Reduction" — Option 1, Path 1** (Maintain Existing Structural Elements). Quantifies how much of the existing structure was preserved during the renovation, by element:

- 4 elements: walls / floors / roofs / envelope
- For each: (a) existing area, (b) reused area, (c) project area
- **Bechtel result**: **70% of project area is reused existing structure** → **LEED 4 points** (60%+ band)
- Note: Bechtel is multi-terraced — floor / roof distinction is blurry, so all reuse counted as "floors" per the submittal

### One-line you can say in the presentation

> "The materials I received are two LEED submittal packages: one is operational energy — the eQuest model's predicted annual usage vs the code baseline — and the other is structural reuse, quantifying how much of the existing walls, floors, and envelope was kept during the renovation. Both are official USGBC submittals for the same project, LEED #1000171106."

---

## One-line summary

I wired both LEED submittal packages into the digital twin so that operational energy and embodied carbon are visible on a single popup, layered for different stakeholders (Engineer SCADA panel + Public plain-English card).

---

# Panel 1 — Material Reuse (Engineer)

**Location:** Grimes popup → Engineer mode → right-docked SCADA panel.

**What it shows:** how much of the existing Bechtel structure was preserved during renovation.

- Section header right side: `70% kept · LEED 4 points` (color-coded terracotta)
- Per-element rows with SVG icons + bars + percentage:
  - Walls 88%, Floors 94%, Envelope 98% kept
- Hover any row → exact sqft tooltip (e.g. "Walls · 20,346 of 23,142 sqft kept")
- Roofs row dropped — Bechtel is multi-terraced, always N/A

**Meaning:** embodied carbon ≈ the amount of new concrete and steel poured. Higher reuse → smaller upfront carbon footprint. Complements operational-energy metrics by capturing the full building lifecycle.

**Data source:** `data/bechtel_lca.json` ← extracted from the LEED-LCA credit calculator (xlsx).

---

# Panel 2 — Design Intent vs Actual (Engineer)

**Location:** Grimes popup → Engineer mode → same SCADA panel, above Material Reuse.

**What it shows:** design model prediction vs code baseline vs live meter readings.

- Section header right side: `-54% vs design` (color-coded: green if under, orange if over, gray if tracking)
- Three horizontal bars, all scaled to the baseline length:
  - **Baseline** = ASHRAE 90.1-2010 code minimum (gray)
  - **Designed** = eQuest design model prediction (gold)
  - **Live** = current 6hr meter average × 8760 hr (cyan)
- Hover any bar → scope + source + exact kWh/yr tooltip

**Key detail — meter-aware comparison:** when viewing the M76 meter (mechanical), the panel sums only HVAC/pumps/fans LEED end-uses. When viewing M77 (plug+lighting), it sums lighting/receptacles only. This solves the apples-to-oranges problem of comparing a single sub-meter to a whole-building model.

**Meaning:** visualizes the academic **performance gap** (modeled vs actual energy use) in real time, every 15 minutes — typically only checked annually via utility bill reconciliation.

**Data source:** `data/bechtel_leed.json` ← extracted from the LEED Energy Performance calculator (xlsm), 11 end-uses, eQuest model output.

---

# Card 3 — LEED v4 Certified (Public)

**Location:** Grimes popup → Public mode → bottom-center rounded card, below the live kW hero.

**What it shows:** the same LEED energy data simplified for non-technical viewers.

- Green badge: `🏆 LEED v4 CERTIFIED`
- Big 30 px hero `45%` with `less energy than code minimum`
- Two-row comparison bar (code = gray full length, designed = green 55%) — the length difference visually conveys the savings
- Status line: "Tracking **12% below** design intent right now."

**Meaning:** same data as Panel 2, different abstraction. For the public, the complex SCADA comparison compresses to one sentence: "the building was designed to use about half what code requires, and it's running on plan."

---

# Card 4 — Built on Reuse (Public)

**Location:** Grimes popup → Public mode → bottom-center card, just below the LEED card.

**What it shows:** the structural-reuse data compressed into an embodied-carbon message.

- Terracotta badge: `♻ BUILT ON REUSE`
- Building cross-section SVG: upper hatched-gray block = new construction (30%), lower solid-terracotta block with floor lines and window squares = existing kept (70%)
- Big 24 px hero `70%` with `reused structure`
- Supporting line: `94% of original floors, 98% of envelope kept`

**Meaning:** one image conveys "this building was preserved, not built fresh." The two Public cards (LEED + Reuse) use different colors (green vs terracotta) to visually separate operational energy and embodied carbon as two distinct sustainability stories.

---

## Data sources

| File | Source | Extraction script |
|---|---|---|
| `data/bechtel_leed.json` | LEED v4 EAp2 Energy Performance Calculator (.xlsm) | `extract_leed.py` |
| `data/bechtel_lca.json` | LEED v4.1 MR Building Life-Cycle Impact Reduction (.xlsx) | `extract_lca.py` |

LEED Project **#1000171106** · UCB Bechtel Engineering Center · SOM architect · Sage Green Strategies LEED consultant.

---

## Why it matters (research framing)

1. **Performance gap visualization** — surfaces the modeled-vs-actual energy gap discussed in academic literature, in real time. Typically only checked via annual utility bill reconciliation.
2. **Meter-aware scoping** — single-meter totals ≠ whole-building model. By defining a meter → LEED end-use mapping explicitly, comparisons stay apples-to-apples.
3. **Operational + embodied carbon together** — typical BMS dashboards show only operational energy. Pairing it with LCA data captures the full building lifecycle footprint on one screen.
4. **Audience-tiered communication** — the same data source generates both an Engineer panel and a Public card, giving each stakeholder the abstraction level appropriate to them.
