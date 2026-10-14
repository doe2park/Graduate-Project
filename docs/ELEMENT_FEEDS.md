# Element feeds and the Walk-mode info card

Walk mode shows a small "AR gaze card" after the crosshair rests on one element for 400 ms.
The card names the data tier honestly; `elementFeedTier()` in `grimes-bim-viewer.html` picks it.

## Tier ladder (first match wins)
1. **LIVE / LATEST** - an explicit entry in `buildings/grimes/element-feeds.json`. LIVE only if the reading is
   <= 45 min old (same `meterReading` rule as the twin panel); older shows LATEST with "Last reading HH:MM · Nh ago";
   no value shows "No reading in this window".
2. **MODELLED** (amber) - `apportion` in the sidecar: "≈ X W modelled share", from building meter N by design VA/CFM ratio.
3. **CONTEXT** (grey) - `isFedBy` only: building meter value and age, explicitly not the element's own reading.
4. **NO FEED** - nothing is bound; hint that a sensor link can be added.

## File format
```json
{"_schema": "element-feeds/1", "_doc": "...",
 "elements": {"12345": [{"ref": "bmo:meter:77:kw", "kind": "sensor", "quantity": "power", "unit": "kW",
                          "source": "Panel CT 4", "evidence": "install log 2026-xx"}]}}
```
Key = exact source element id (sidecar key = GLB node name). If ids could collide across layers use
`"<layer>:<id>"` (e.g. `"duct:12345"`); it wins over the bare id. The first entry with a `ref` is used.
`ref` is currently a building-meter series (`bmo:meter:<n>:kw`) resolved against `building_data.json`.

## Adding a real sensor
Add one entry under `elements` (above) once the sensor is verified and its `evidence` is recorded. No code change.
The file ships with an empty `elements` object; a missing or unparsable file is treated as empty, silently.

## What it does not claim
No sensor exists today, so no card is LIVE for an element. MODELLED shares are uncalibrated allocations of a
building meter; CONTEXT is a building/feeder total. Neither is an element measurement.

## Controls and capture
Toolbar "Info cards" button or `I` toggles the cards (default on). With `?capture=1`, `window.walkCapture`
(`enter`, `setPose`, `aimNow`, `render`, `ready`, `state`) enables deterministic frame-stepped recording
with no hint and no fades; it is undefined otherwise.
