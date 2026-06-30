# Twin Packages — add a building without writing code

Every building is a self-contained folder under `buildings/<id>/`. The generic viewer
(`/twin-viewer.html?building=<id>`) and the campus map read these files. **Adding a
building = adding a folder. No code changes.**

```
buildings/<id>/
  manifest.json      name, location (lat/lon), levels, units, glb path, cupix url
  model.brick.json   Brick-Schema model: equipment, points, relations
  binding.json       glb node name  ->  Brick entity URI
  sources.json       Brick point externalReference  ->  live data stream
```

The geometry asset (`.glb`) can live at repo root and be referenced by `manifest.model.path`
— no need to copy large files into the folder.

## How a click becomes live data

```
click mesh -> glb node name --binding.json--> Brick entity
           --hasPoint / isFedBy--> points --externalReference--> sources.json
           --adapter--> live value   (see twin/twin-resolver.js)
```

This resolver is building-agnostic and never changes. All building knowledge lives in the
four JSON files.

## Onboarding steps

1. **Geometry.** Export the Revit/IFC model to `.glb`.
   - *System tier (works today):* group by discipline → one mesh per system. The mesh
     names become your binding keys (e.g. `HVAC Duct`, `Electrical`).
   - *Element tier (later):* one node per family instance, `node.name = Revit UniqueId`,
     with `extras: { category, family, level }`. Then a click resolves to a single VAV.
2. **Semantics.** Write `model.brick.json`. Map each Revit category/family to a Brick class
   using the table below. Most of this can be auto-generated from the equipment schedule.
3. **Binding.** In `binding.json`, map each glb node name to its Brick entity URI.
4. **Data.** In `sources.json`, point each Brick point at a live stream (panel meters at
   minimum). Add an adapter type if the source isn't BMO-JSON.
5. **Place it.** Set `lat/lon`, `trueNorthDeg`, `levels`, and `units` in `manifest.json`.
6. Open `/twin-viewer.html?building=<id>`. Done.

## Revit category/family → Brick class (starter table)

| Revit category / family            | Brick class                  |
| ---------------------------------- | ---------------------------- |
| Mechanical Equipment (AHU)         | `brick:Air_Handling_Unit`    |
| Mechanical Equipment (fan)         | `brick:Fan`                  |
| Mechanical Equipment (pump)        | `brick:Pump`                 |
| Ducts / MEP Fabrication Ductwork   | `brick:HVAC_System`          |
| Air Terminals / Diffusers          | `brick:Terminal_Unit`        |
| Pipes / Piping                     | `brick:Water_System`         |
| Electrical Equipment (panel/meter) | `brick:Electrical_Meter`     |
| Conduit / Cable Tray               | `brick:Electrical_System`    |
| Lighting Fixtures                  | `brick:Lighting_System`      |
| Sprinklers / Fire Protection       | `brick:Fire_Safety_System`   |

Point classes follow the same idea: a power reading is `brick:Electrical_Power_Sensor`, an
air temperature is `brick:Supply_Air_Temperature_Sensor`, a flow is `brick:Flow_Sensor`,
run state is `brick:Run_Status`, etc. Each point gets an `externalReference` resolved by
`sources.json`.

## Data-source adapters

`sources.json` declares adapters so the viewer never hard-codes a data backend.
Currently implemented in `twin/twin-resolver.js`:

- **`bmo-json`** — reads `meters[<id>].latest.kw` + `timeseries_kw` from a BMO snapshot JSON.

To add BACnet, a CSV export, or a REST API, add an adapter `type` and a matching branch in
`runAdapter()` — every building that references it then works unchanged.

## Worked example

`buildings/grimes/` is a complete, working system-tier package: 8 discipline meshes bound to
3 BMO electrical meters (M3 roof, M76 mechanical/HVAC, M77 plug+lighting). Use it as the
template for the next building.
