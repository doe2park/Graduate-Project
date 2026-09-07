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
