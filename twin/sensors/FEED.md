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
- The `bms`, `bmo` and `fiber` adapters are stubs that return `missing` with a reason. The `gateway` adapter is a stub too, unless the page is in live-test mode (below): then it reads a `latest.json` snapshot from the gateway URL.
- `?sensors=live&feed=<url>` turns on live-test mode, in `scan-compare.html` (web overlay) and `scan-xr.html` / `/mr/`. The URL is accepted only for this computer (`localhost`, `127.x`, `[::1]`) or a private-LAN IPv4 address (`10.x`, `172.16–31.x`, `192.168.x`). An https page cannot read an http feed, except one on this computer.
- The simulator and `tools/sensor_sim.py` use the same math (checked by `tests/sensor-feed.test.cjs`).

## Live test with a phone
An end-to-end test of the live path before any wireless sensor is bought. The owner's phone is a **temporary test device**. Its browser reads the accelerometer and posts real observations to a small gateway on the laptop. The twin then shows that sensor as **Live** on duct 399665, the fan-fed duct run of "Test install 5".
- **Registry:** `registry.live-test.json`, a separate file with the same schema. It has one row, `test-phone-vib`, with `install_status: "test"`, `data_source: "gateway"`, a `test_device` note, unit `m/s2` and a 2 s interval, so it goes stale after 6 s. Only live-test mode loads this file: the public `?sensors=demo` views never show it.
- **Quantity:** each 2 s window takes the phone's linear acceleration (x, y, z), removes the window mean of each axis and sends the RMS of the remaining magnitude, in m/s².
  - This is acceleration, not the ISO 10816 velocity in mm/s. A phone cannot integrate acceleration to velocity honestly.
  - Browsers sample at roughly 60–100 Hz, so vibration above about 30 Hz is not captured.
  - The phone is uncalibrated and not mounted on the duct.
  - When only gravity-including acceleration is available, or the sample rate is low, the observation is sent with `quality: suspect` and a reason.

### Run it
The phone, the Quest and the laptop must be on the same Wi-Fi.
1. On the laptop, from the repository root (a full checkout, so the twin pages have their assets): `python3 tools/sensor_gateway.py --lan`. It prints the URLs below with the laptop's private address.
2. **Phone:** open `https://<laptop-ip>:8931/phone`. Accept the self-signed certificate warning for this exact address, tap **Start sensor** and allow motion access (iOS asks on the tap). Keep the page open with the screen on.
3. **Web overlay**, from the gateway itself, so it is the same origin:
   `https://<laptop-ip>:8931/scan-compare.html?view=overlay&capture=2026-05-06&sensors=live&feed=/api/sensors/latest.json`.
   The duct pin shows a **TEST** card with a **LIVE** value, its age, `quality` and `source gateway`. Stop the phone, and after 3 missed intervals the card turns **Stale**.
4. **Quest:** open `https://<laptop-ip>:8931/mr/?sensors=live&feed=/api/sensors/latest.json` for passthrough MR. For photo VR, open `…/scan-xr.html?sensors=live&feed=/api/sensors/latest.json`. The chip and the card say LIVE, STALE or NO DATA, never SIMULATED.
- **Desktop check without a phone:** run `python3 tools/sensor_gateway.py` (http on 127.0.0.1:8931) and POST synthetic observations with the `curl` line it prints. Then open `http://127.0.0.1:8931/scan-compare.html?…&sensors=live&feed=/api/sensors/latest.json`.
- **The published pages** (GitHub Pages) can read the feed too, with `&feed=https://<laptop-ip>:8931/api/sensors/latest.json`, once the device has accepted the certificate (open `/trust`). The gateway answers CORS and Chrome's Private Network Access preflight for the published origin only. Browsers that ask for local-network permission show a prompt.

### Gateway (`tools/sensor_gateway.py`, standard library only)
- `POST /api/sensors/observations` takes one observation or `{"observations": [...]}`. Each one is checked against this contract and the registry:
  - the sensor must be a gateway sensor in the registry;
  - the unit must equal the registry unit;
  - `ts` must have a time zone and be at most 2 min ahead and at most 24 h old;
  - `value` must be a number or `null`, and `null` goes with `quality: missing`;
  - `source` must be `gateway`, and `simulated: true` is refused.
  The response lists each rejected observation with its reason.
- `GET /api/sensors/latest.json` returns the snapshot. A sensor with no data yet appears as `missing`. `GET /api/sensors/history.json?sensor=<id>` returns its rolling history.
- Only loopback and private-LAN clients are served. Observations are accepted from the gateway's own origin (the phone page) or from requests with no Origin header (curl, or a device on the LAN). Other origins can only read.
- No credentials. The self-signed certificate comes from `scripts/serve_quest_https.py`, under the gitignored `work/quest-https/`. Nothing else is written to disk, and nothing goes to the `data` branch.

### The same path for a real sensor
A real wireless gateway, or a BMS exporter, only has to publish the same `grimes-sensor-feed/1` snapshot, either directly or by posting to this gateway. The viewer side does not change: the same `gateway` adapter, the same `assess` rules and the same Live / Stale / No data labels.

To add the real sensor:
1. Add a row to `registry.json` with `install_status: "installed"`, `data_source: "gateway"`, the real `source_point` and its unit and interval.
2. Point the adapter at the published snapshot URL.
3. Retire `test-phone-vib`.

