# Element feeds and the Walk-mode info card

Walk mode shows a small "AR gaze card" after the crosshair rests on one element for 400 ms.
The card names the data tier honestly; `elementFeedTier()` in the shared `twin/element-cards.js` picks it
(used by `grimes-bim-viewer.html`, `scan-bim.html` and `scan-compare.html`, so every card uses the same rules).

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

## Overlay Lens cards (scan-compare)
In `scan-compare.html?view=overlay` with the Lens style, the element under the lens centre gets the same card next to the
lens ring. On desktop the lens follows the pointer. On mobile the card sits above the bottom controls. The same 400 ms dwell
and 250 ms grace apply. It works over 360° photos, the mesh and the Gaussian scene. The parent posts
`{type:'grimes-lens-probe', seq, x, y}` (normalised in the BIM iframe) about every 150 ms. The BIM pane raycasts its visible
element layers with the click-pick identity (`resolveElementHit`), resolves the tier and answers
`{type:'grimes-lens-pick', seq, x, y, hit:null|{id, layer, meta, tier, adjustment}}`. The parent drops stale or
malformed replies (`ElementCards.parseLensPick`) and derives the badge class itself. The "Info cards" button or `I` toggles
the cards. In As-built mode an adjusted element adds the line "As-built · manual, not surveyed · moved N cm"
(see `docs/AS_BUILT_ADJUSTMENTS.md`).
