# Grimes twin sensors

- **`registry.json`** is the one source of truth for sensors.
  - It lists every sensor: what it measures (quantity, unit, interval), the BIM element it belongs to (layer, element id, `source_guid`, sidecar name, position), its location, install status, data source, alert rule, Brick class and provenance.
  - The demo layer (`twin/sensor-demo.js`, `?sensors=demo`) and the deck read it.
  - Today all 17 entries are `install_status: "demo"` with `data_source: "demo-sim"`: **no sensor is installed and every value is simulated**.
- **Feed contract:** `FEED.md`. JSON Schemas: `registry.schema.json`, `observation.schema.json`, `feed.schema.json`.
- **Viewer adapter:** `feed.js` (`SensorFeed.create({registry}).getLatest(ids)`).
- **Snapshot generator:** `../../tools/sensor_sim.py`.

## Add a real sensor
1. **Registry row.** Add the sensor or edit a demo row:
   - set the `anchor` to the real BIM element (copy `id`, `name` and `source_guid` from the layer sidecar);
   - set `quantity`, `unit` and `sampling_interval_s`;
   - set `install_status: "installed"`;
   - set `data_source` to `bms`, `bmo`, `gateway` or `fiber`;
   - set `source_point` to the real point id.
   - `node --test tests/sensor-demo.test.cjs tests/sensor-feed.test.cjs` checks the anchor against the sidecar and the row against the schema. An installed sensor cannot use `demo-sim`.
2. **Adapter.** In `feed.js`, replace the stub for that `data_source`. An adapter receives the registry rows and returns observations in the `FEED.md` format:
   - convert units to the registry unit;
   - set `ts` to the measurement time;
   - set `quality`;
   - set `value: null` (not `0`) when there is no reading.
   - No credentials in the browser or in this public repo: a protected source must be published as a JSON file by the existing collector workflow first, and the adapter only fetches that file.
3. **That's all.** The demo layer and the Lens card show the new value with a **Live** badge, its age and quality, under the same stale and missing rules.

### Example: a BMO meter (already collected)
The BMO collector already publishes `data/building_data.json` on the machine-written `data` branch. A registry row with `"data_source": "bmo", "source_point": "bmo:meter:76:kw", "unit": "kW", "sampling_interval_s": 900` and this adapter is enough:
```js
bmo: async sensors => {
  const d = await fetch('https://raw.githubusercontent.com/doe2park/Graduate-Project/data/data/building_data.json').then(r => r.json());
  return sensors.map(s => { const m = /^bmo:meter:(\d+):kw$/.exec(s.source_point || ''), l = m && d.meters?.[m[1]]?.latest;
    return l && Number.isFinite(l.kw) ? {sensor_id: s.id, ts: new Date(l.t).toISOString(), value: l.kw, unit: 'kW', quality: 'good', source: 'bmo'}
                                      : {sensor_id: s.id, ts: null, value: null, unit: s.unit, quality: 'missing', source: 'bmo', reason: 'meter not in building_data.json'}; });
}
```
- Check the timestamp format and time zone of `latest.t` before trusting it.
- A building meter is building context. Anchor it as a building-level point (like `power-bmo`), never as an element measurement (AGENTS.md data-honesty ladder).

### Example: a BACnet point (once Facilities grants read access)
- Registry: `"data_source": "bms", "source_point": "bacnet:2400/analog-input:12"` (device instance / object type : instance), plus a unit that matches the point's engineering unit.
- A small read-only exporter on the campus side reads the point. It is not part of this repo and never holds credentials here.
- The exporter writes observations in the `FEED.md` format to a published JSON file. The `bms` adapter fetches that file and maps `source_point` to the observation.
- No BACnet traffic or credentials ever go through the browser.

## Brick
- Each row carries `brick.class` and `brick.isPointOf` (`urn:grimes:bim-guid:<source_guid>`).
- Class names are **candidates** from the Brick 1.3 vocabulary, not machine-verified here.
- `used-in-model` means the class is already used in `buildings/grimes/model.brick.json`.
- Verify with `brickschema` before exporting TTL.
