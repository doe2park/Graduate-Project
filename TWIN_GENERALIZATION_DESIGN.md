# Campus Digital Twin — Generalization Architecture

**Goal:** turn the Grimes-specific viewer into a reusable framework where *any building with a BIM model* becomes a live digital twin by dropping in a self-contained package — no per-building code. The technical heart is **sensor/meter → BIM-element binding**, expressed in a portable standard (**Brick Schema**) so the work is research-credible and cross-building by construction.

---

## 1. Where you are now (grounded)

You already have the *seed* of the binding, but it is hard-coded and building-specific in three places:

- **In code:** `grimes-bim-iot/protoys.html` holds an `EQUIPMENT[]` array — each entry ties a BIM element (`bimId`, Revit `family`/`category`) to a list of sensor channels. This is, in effect, an ad-hoc Brick model written in JavaScript.
- **In a bespoke manifest:** `data/grimes-interior.json` `hotspots[]` place clickable markers at hand-picked 3D coordinates and reference `data_refs.meter_id / sensor_id / equipment_id`.
- **In the viewer:** `grimes-xr.html` and the ArcGIS map carry explicit "for Grimes only" branches.

Two hard facts constrain the design — and actually simplify it:

1. **The glb has no element identity.** `grimes-mep-only.glb` contains exactly **8 meshes**, one per discipline (HVAC Duct, HVAC Equipment, Piping, Sprinkler, Conduit, Diffusers, Pumps/Valves, Electrical). No per-element IDs, no Revit GUIDs, no `extras`. You can pick a *discipline*, not an individual VAV. (The per-element `bimId`s in `protoys.html` came from the Autodesk APS/Forge viewer, which you stepped away from because NWD→glTF was blocked at the Hub-permission level.)
2. **The live data is whole-building.** `data/building_data.json` exposes **3 electrical meters** — Roof Electric, 480/277V, 208/120V. There is no per-VAV or per-pump telemetry today.

**The key insight:** your geometry granularity (system/discipline) and your data granularity (building/panel) already meet at the **system level**. Per-element binding is aspirational and needs both a richer export *and* a richer BMS feed. System-level binding is achievable now, matches the data you actually have, and — because every Revit model can export discipline-grouped geometry and most buildings expose panel/system metering — is exactly the granularity that *generalizes most easily across buildings*. Design for all tiers; populate the tier you have.

---

## 2. The three couplings to break

Generalization = removing what currently ties the viewer to Grimes:

1. **Code coupling** — building knowledge lives in HTML/JS. → Make the viewer fully **data-driven**; all building knowledge moves into package files.
2. **Schema coupling** — `EQUIPMENT[]` / `hotspots[]` are bespoke. → Adopt **Brick Schema** as the canonical semantic model (portable, queryable, standard).
3. **Data coupling** — fetching is BMO-specific. → Insert a thin **data-source adapter** interface so BMO / BACnet / CSV / API all look identical to the viewer.

---

## 3. The "Twin Package" — the core deliverable

Each building becomes a self-contained folder. Adding a building = adding a folder. The campus map reads each `manifest.json`; the viewer loads the rest.

```
buildings/<building-id>/
  model.glb         # BIM geometry. Nodes named by a stable key (see §5).
  model.brick.json  # Brick model: equipment, points, locations, relations.
  binding.json      # join table:  glb node id  ↔  Brick entity URI
  sources.json      # adapter config: Brick point  ↔  live data stream
  manifest.json     # name, lat/lon, levels, units, true-north angle, default views, flags
```

`manifest.json` is the only file the **map** needs (to place and label the building). The **viewer** loads `model.glb` + the three companions. Nothing building-specific stays in code.

---

## 4. Brick Schema as the binding layer

Brick is an open ontology for building points/equipment. It replaces `EQUIPMENT[]` with a standard graph.

- **Equipment classes:** `brick:Fan`, `brick:Pump`, `brick:VAV`, `brick:Chiller`, `brick:Chilled_Water_System`, `brick:Hot_Water_System`, `brick:Electrical_Meter`, `brick:Air_Handling_Unit`, …
- **Point classes:** `brick:Supply_Air_Temperature_Sensor`, `brick:Flow_Sensor`, `brick:Power_Sensor`, `brick:Pressure_Sensor`, `brick:Run_Status`, `brick:Fault_Status`, …
- **Relations:** `brick:hasPoint`, `brick:hasLocation`, `brick:feeds`, `brick:isPartOf`, `brick:hasUnit`.
- **Stream link:** each point carries an `externalReference` (a stream key) resolved by `sources.json`.

Why it's worth it: (1) it is exactly what `EQUIPMENT[]` is groping toward, but standardized; (2) it makes the model *queryable* ("show every Power_Sensor that feeds Level 2") via a small in-browser graph or SPARQL; (3) it is the credibility anchor for the research claim — "we bind live data to BIM through a standard semantic layer," not a bespoke JSON blob.

Concretely, the Grimes system tier in Brick is tiny and you can author it by hand from `protoys.html` + the 3 meters. Example sketch (compact JSON form):

```json
{
  "grimes:RoofElectric":   { "type": "Electrical_Meter", "hasPoint": ["grimes:RoofElectric.kw"],
                             "feeds": ["grimes:Sys.HVAC_Equipment"] },
  "grimes:Sys.HVAC_Duct":  { "type": "HVAC_System", "hasLocation": "grimes:Whole" },
  "grimes:RoofElectric.kw":{ "type": "Power_Sensor", "hasUnit": "KiloW",
                             "externalReference": "bmo:meter:3:kw" }
}
```

---

## 5. The element↔point join, and click resolution

The whole interaction reduces to one resolver, identical for every building:

```
click mesh → glb node id → binding.json → Brick entity URI
           → Brick: entity hasPoint [points]
           → each point.externalReference → sources.json → live value
           → render panel
```

For this to work the glb nodes need **stable keys**. Two tiers:

- **System tier (today):** the 8 discipline mesh names *are* the keys. `binding.json` maps `"HVAC Duct" → grimes:Sys.HVAC_Duct`. This works with your current glb immediately.
- **Element tier (later):** re-export from Revit/IFC so each family instance is its own node, named by its **IFC GUID / Revit UniqueId**, optionally carrying `extras: { category, family, level }`. Then a click resolves to a single VAV. This needs an export convention, not the APS cloud — see §6.

---

## 6. Geometry identity: the one real decision

To ever reach element-level binding you must preserve element identity in geometry. Three options:

- **A — APS/Forge viewer.** Keeps every Revit element + dbId/GUID natively; true element binding. But heavy, cloud-dependent, and you already hit the blocked NWD→glTF Hub permission. *Not recommended as the spine.*
- **B — glb with an identity-preserving export (recommended).** Define a Revit/IFC → glb export that emits one node per element, `node.name = UniqueId`, plus `extras`. Lightweight, offline, Three.js-native. The cost is a repeatable export step, which becomes part of the onboarding pipeline (and is itself a modest research/tooling contribution).
- **C — Stay at system tier (recommended for now).** Ship the framework at system granularity, which matches your data. Move to element tier per-building only when that building has element-level BMS points worth showing.

Recommendation: **C now, B as the documented path to element tier.** Skip A.

---

## 7. Onboarding a new building — the generalization payoff

This workflow *is* the thesis demo. For a new building with a BIM model:

1. **Geometry:** export Revit → `model.glb`, discipline-grouped (system tier) or element-named (element tier).
2. **Semantics:** generate a **Brick stub** automatically from the Revit/IFC equipment schedule — a category/family → Brick-class lookup table does most of the work. Hand-correct the rest.
3. **Data:** fill `sources.json` mapping Brick points to live streams (panel meters at minimum).
4. **Place it:** set lat/lon + true-north in `manifest.json`.
5. Drop the folder in. The map lists it; the viewer renders it. **Zero code change.**

The measurable generalization claim: *time-to-twin per building* and *% of points auto-mapped by the Revit→Brick table*. That is a real, defensible systems contribution.

---

## 8. Phased roadmap

**Phase 0 — Refactor to data-driven (no new features).** Extract all Grimes-specific knowledge from `grimes-xr.html` and the map into a `buildings/grimes/` package. Prove the viewer renders purely from package files. *This is the unlock; everything else depends on it.*

**Phase 1 — Brick the binding.** Convert `protoys.html` `EQUIPMENT[]` + the 3 meters into `model.brick.json` + `binding.json` at system tier. Replace the `EQUIPMENT[]` array with the generic Brick resolver.

**Phase 2 — System-level click-to-data in the glb.** Raycast → discipline node → Brick → live panel, using the existing 8-mesh glb. First fully generic interaction.

**Phase 3 — Onboarding pipeline.** Build the Revit/IFC schedule → Brick-stub generator (category→class table). Onboard **building #2** end-to-end to validate that "BIM in → twin out" holds. This is the moment the project stops being "a Grimes app."

**Phase 4 — Adapters + element tier + scale.** Normalize `sources.json` behind adapters (BMO, BACnet, CSV); document the identity-preserving export (§6-B) for buildings that warrant element granularity; map auto-lists every packaged building.

Existing work that folds in cleanly: the performance-gap and FDD analytics become **building-agnostic modules** that run over any package's Brick points — so they generalize for free once Phase 1 lands.

---

## 9. Research framing

- **Contribution 1 — Twin-package spec** (glb + Brick + binding + sources) that cleanly decouples *geometry*, *semantics*, and *data*.
- **Contribution 2 — (Semi-)automated Revit/IFC → Brick binding pipeline** that lowers per-building onboarding cost (the generalization claim; measured in time-to-twin and auto-map coverage).
- **Contribution 3 — A zero-code generic viewer** demonstrating cross-building reuse on ≥2 real buildings (Grimes + 1), with an analytics use case (performance gap or FDD) running unchanged across both.
- **Evaluation:** onboarding effort per building, Brick auto-mapping coverage/accuracy, and a working cross-building analytic.

---

## 10. Recommended immediate next step

Do **Phase 0 + Phase 1 at system tier** first. It is achievable with the assets you already have (the 8-mesh glb, 3 meters, `protoys.html`'s registry), it produces the first genuinely generic, Brick-bound, click-to-live-data interaction, and it is the foundation every later phase stands on. Concretely: stand up `buildings/grimes/` with `manifest.json`, `model.brick.json`, `binding.json`, `sources.json`, and a small generic resolver — then prove the viewer needs *nothing Grimes-specific in code* to render it.
