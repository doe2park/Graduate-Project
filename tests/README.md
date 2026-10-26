# Viewer validation

The static site has no build step. Tests use Node's test runner and Python unittest. Three.js is pinned to the same 0.169.0 as the viewer.

```sh
node --test tests/viewer.test.cjs
# Either install three@0.169.0 locally, or point to an external installation:
THREE_MODULE=/path/to/three/build/three.module.js node --test tests/render-tier.test.mjs
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts -p test_mep_recovery.py
```

Optional tools in a temporary directory (does not alter the project dependency tree):

```sh
npm install --prefix /tmp/grimes-validation-tools three@0.169.0 playwright@1.55.1
/tmp/grimes-validation-tools/node_modules/.bin/playwright install chromium
python3 -m http.server 8765 --bind 127.0.0.1
# In a second terminal:
PLAYWRIGHT_MODULE=/tmp/grimes-validation-tools/node_modules/playwright node tests/browser.cjs
```

`CHROME_EXECUTABLE` can select an existing Chrome executable. `VIEWER_BASE_URL` defaults to http://127.0.0.1:8765; `VALIDATION_OUTPUT` selects the screenshots/report directory (default system temp/grimes-validation).

The browser test injects inspection hooks into its HTML response only, uses deterministic test meter readings, loads all ten layers together, checks every rendered ID plus exact primitive counts, floor filters, a real raycast, the carbon scenario calculation, mobile overflow and page errors. It uses the actual served GLBs. It does not claim availability of the live BMO feed. Full-model testing is intentionally substantial; a phone with less GPU/memory can require floor/type filtering.

## Mobile QR interaction smoke test

`PLAYWRIGHT_MODULE=/path/to/playwright CHROME_EXECUTABLE=/path/to/chrome node tests/mobile-browser.cjs` checks the public QR destinations with actual published data (no meter fixtures). Optional `VIEWER_BASE_URL` changes the site; `STAGED_DIR` replaces only the two HTML responses while retaining real assets. `VALIDATION_OUTPUT` selects screenshots. It verifies menu closing, touch Walk movement/release and drag look, rotation to landscape, retained viewpoint, source-ID object search and the performance table. Chrome mobile emulation is not physical iOS/Safari certification.

## Registered comparison

Run `node --test tests/layer-visibility.test.cjs` for sequential bulk visibility, cancellation and latest-intent checks. `tests/registered-comparison.cjs` loads the actual scan, interior and ten BIM layers, verifies the accepted camera transform in both directions, and checks all-element visibility including interior while retaining the floor. It accepts `PLAYWRIGHT_MODULE`, `CHROME_EXECUTABLE`, `THREE_MODULE`, `VIEWER_BASE_URL` and `VALIDATION_OUTPUT`; see the browser test setup above. It uses real public data, not meter fixtures.

## Registration workbench

`node --test tests/registration-core.test.cjs tests/registration-preview.test.cjs` and `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_registration_fit.py` cover the shared yaw+XYZ fit, RANSAC, leave-one-out, heading solve, export schema, refusal to overwrite accepted registrations, `?registration=` preview safety and JS/Python numerical agreement on `tests/fixtures/registration-pairs.fixture.json` (synthetic data). See `docs/REGISTRATION_WORKBENCH.md`.

## Element cards and as-built adjustments

`node --test tests/element-cards.test.cjs tests/as-built.test.cjs tests/as-built-ui.test.cjs` and `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_check_as_built.py` cover:
- tier and card parity across the viewer, the BIM pane and `twin/element-cards.js`;
- the lens probe/pick message contract;
- as-built schema validation;
- instanced and merged-range application, including exact restore on Design/As-built toggles;
- the panel logic and `scripts/check_as_built.py` statistics.

## Quest WebXR overlay (`scan-xr.html`)

```sh
node --test tests/scan-xr-core.test.cjs        # registration placement vs registration-core/convert(), orientation, navigation, cone, menu, card honesty
node --test tests/xr-spatial-tier.test.mjs     # needs three (THREE_MODULE, tools/node_modules/three or 'three')
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_serve_quest_https.py
PLAYWRIGHT_MODULE=/path/to/playwright-core node tests/scan-xr-smoke.cjs   # one headless desktop run + measurements; XR_SMOKE_LAYERS=equipment,lighting for a lighter run
```
The smoke starts its own `python3 -m http.server` unless `VIEWER_BASE_URL` is set, uses a meter fixture, and launches Chrome with `--use-angle=metal --ignore-gpu-blocklist` (headless WebGL is otherwise disabled on macOS). Its numbers are desktop numbers, not Quest frame rates. See `docs/QUEST_XR_OVERLAY.md`.

## Demo sensor layer (illustrative, opt-in)

`node --test tests/sensor-demo.test.cjs` checks `twin/sensors/registry.json` (status `illustrative-not-installed`; every anchor is a real sidecar element with the same name and `source_guid`), the pure helpers in `twin/sensor-demo.js` and that `scan-compare.html` / `scan-bim.html` load the layer only behind `?sensors=demo` (and that `&scene=<leak|air|water|elec|rotating>` keeps one scenario). `THREE_MODULE=/path/to/three/build/three.module.js node --test tests/sensor-demo-bim.test.mjs` runs the BIM-pane half on real three@0.169.0 objects (identity gate, DTS gradient copy from exactly the element's triangles, source batch byte-identical, projected anchors). No sensor is installed; every reading in the JSON is made up for a concept presentation.

`node --test tests/talks-deck.test.cjs` checks the public deck in `talks/sensor-deck/`: every referenced asset resolves inside the folder, live-view URLs are relative (`../../scan-compare.html?...&sensors=demo&scene=…`), nothing local or private (Oct 18 paths, localhost, credentials, e-mail addresses) is included, and every image is listed in `img/SOURCES.md` with lecture figures credited on the slide.

`node --test tests/sensor-feed.test.cjs` and `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_sensor_sim` check the sensor registry and feed contract (`twin/sensors/`): registry/observation/snapshot JSON Schemas (via the dependency-free `twin/sensors/schema-lite.js`), the shared rules (missing is not zero, stale after N x interval, unit mismatch), simulator determinism and agreement between `twin/sensors/feed.js` and `tools/sensor_sim.py`, adapter stubs, and that the Lens card only gains a feed row with `?sensors=demo`.
