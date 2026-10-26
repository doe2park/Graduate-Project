# Sensor feed contract (`grimes-sensor-feed/1`)

Every data source (BMS/BACnet, BMO meters, a wireless gateway, a fiber analyzer, or today the demo simulator) is turned into the same observation format. The twin only reads this format. It never reads a vendor protocol directly.

## Observation
```json
{"sensor_id": "hvac-iaq", "ts": "2026-10-26T17:00:00.000Z", "value": 821, "unit": "ppm",
 "quality": "good", "source": "demo-sim", "simulated": true}
```
| Field | Rule |
|---|---|
| `sensor_id` | An `id` in `twin/sensors/registry.json` |
| `ts` | ISO 8601 with a time zone (`Z` or `±hh:mm`): the time the value was measured, not the time it was fetched. `null` only when the value is missing. |
| `value` | A number, with booleans as `0`/`1`. **Missing is `null`, never `0`.** |
| `unit` | Must equal the registry `unit` for that sensor. A mismatch is shown as **Unit mismatch** and the value is not used. |
| `quality` | `good` · `suspect` (out of range, sensor fault flag) · `missing` |
| `source` | `demo-sim` · `bms` · `bmo` · `gateway` · `fiber` |
| `simulated` | `true` for every `demo-sim` observation. The UI shows those as **Simulated**; real sources are shown as **Live**. |
| `reason` | Optional text, for example why a value is missing |

JSON Schemas:
- `observation.schema.json` describes one observation.
- `feed.schema.json` describes a snapshot file.
- `registry.schema.json` describes the registry.

## Shared rules (`SensorFeed.assess`, the same everywhere)
1. **Missing ≠ 0.** A `null` value or `quality: missing` is shown as *No data*, together with the reason.
2. **Stale** once the observation is older than `stale_after_intervals` (registry: 3) × the sensor's `sampling_interval_s`. It is shown as *Stale*, greyed out.
3. **Units must match** the registry, otherwise the state is *Unit mismatch*.
4. **Provenance is always visible:** a source badge (Simulated / Live), the age, the quality and the source on every card.

## Files
One file per snapshot:
- `latest.json`: `{schema, generated_at, simulated, source, note, observations[]}`.
- Optionally `history/<YYYY-MM-DD>.json` with the same shape plus `date`.

`tools/sensor_sim.py --out <dir> [--history]` writes demo snapshots. Never write feed files to the machine-owned `data` branch by hand: a future live feed would be published by the existing collector workflow, not by a new schedule.

## Viewer
`twin/sensors/feed.js` → `SensorFeed.create({registry}).getLatest(ids)` returns `{id: observation}`.
- Today every sensor uses `demo-sim`, a deterministic time-of-day simulator that runs in the browser with no backend.
- The `bms`, `bmo`, `gateway` and `fiber` adapters are stubs that return `missing` with a reason.
- The simulator and `tools/sensor_sim.py` use the same math (checked by `tests/sensor-feed.test.cjs`).
