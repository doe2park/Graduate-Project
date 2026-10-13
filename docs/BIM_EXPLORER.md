# Grimes BIM Explorer

[Open the viewer](https://doe2park.github.io/Graduate-Project/grimes-bim-explorer.html) · [Open the complete building](https://doe2park.github.io/Graduate-Project/grimes-bim-explorer.html?model=full)

This is the public version of the October 13 BIM inspection workspace. A colleague can open it directly in a WebGL-capable browser. No Python server, VS Code, Autodesk account or local project folder is needed. The owner's Mac does not have to be running.

## Inspect the building

1. Open the complete-building link on a desktop. The first load fetches and verifies the original geometry and property files; allow it to finish.
2. Drag to orbit, scroll to zoom, or use Fit and Top. Choose floors and systems to inspect an area.
3. Click an object or search by its name/ID. The inspector shows the source-scoped identity and available design properties.
4. Focus, isolate or hide the selected object. Reset visibility to return to the complete view.
5. Use the section plane to look inside the model. Original materials are the default; system colors are an optional inspection aid.
6. The header links to the separate Scan ↔ BIM comparison and energy dashboard.

The base URL chooses a regional example on narrow screens. The model selector can switch to the full building. A full load can exceed a phone's practical memory/rendering budget; mobile availability is not a guarantee of whole-building performance.

| Mode | URL parameter | Contents |
|---|---|---|
| Whole building | `?model=full` | Ten layers and 66,620 source identities |
| Regional example | `?model=regional` | Partial Level 1 area: 492 objects across eight systems |
| Conduit example | `?model=conduit` | 24-object GLB/JSON teaching package |

## What GitHub serves

The generated `grimes-bim-explorer.html` contains the application code and CSS. Three.js and its addons are pinned to 0.169.0 and loaded from a CDN. Draco decoders and small examples live in `bim-explorer-assets/`; the whole building uses the existing GLB and JSON files in `buildings/grimes/`.

The hosting adaptation does not simplify, re-encode or rename the source geometry. Original source IDs continue to bind objects to their sidecars. Source-file hashes, byte lengths and object counts are checked during loading. The full catalog describes 48,728,223 triangle instances and 385,803 line segments; these are inventory counts, not a measured frame rate.

This page displays BIM design properties. It does not establish an element's actual installed state or attach a verified live sensor feed. The existing [element viewer](https://doe2park.github.io/Graduate-Project/grimes-bim-viewer.html) contains separately labelled operating-data context. Publishing this explorer does not validate Quest performance, physical AR alignment or scan registration.

## Modify the application

The editable source is in [`viewer-src/bim-explorer/`](../viewer-src/bim-explorer/). Keep responsibilities separated:

| Files | Responsibility |
|---|---|
| `index.template.html`, `style.css` | Layout, navigation and appearance |
| `deployment.mjs` | Project-relative hosting URLs |
| `viewer.mjs` | Viewer assembly, controls and selection |
| `source-model.mjs`, `render-tier.mjs` | Source identity and rendering/batching |
| `contract.mjs`, `catalog.mjs`, `load-gate.mjs` | Input validation and safe model replacement |
| `record-index.mjs`, `object-view.mjs` | Search and object inspection |
| `asset-cache.mjs`, `demand-renderer.mjs` | Verified asset caching and render scheduling |

With Node.js 22+ and npm installed, run from the repository root:

```sh
node scripts/build_bim_explorer.mjs
node scripts/build_bim_explorer.mjs --check
node --test tests/bim-explorer-deployment.test.mjs
```

The builder uses pinned esbuild 0.25.0 and records deterministic file hashes in `bim-explorer-assets/build-manifest.json`. Commit the generated HTML and manifest along with source edits. GitHub Pages serves the already-built files; visitors do not run the build tool.

For local preview, `python3 -m http.server 8000` is sufficient. If that port is occupied, select another port; do not stop an unrelated server. Open `/grimes-bim-explorer.html` on the chosen local port.

Before publishing an update, test full/regional/sample modes, selection, filtering and a narrow viewport. Verify the live GitHub Pages URL after deployment. Read the root `AGENTS.md` before changing BIM assets; preserve original Draco buffers, element identity and the machine-written data branch.

## Try another prepared model

Use the page's GLB/JSON upload controls for a prepared, embedded GLB and matching identity sidecar. The supplied conduit downloads demonstrate the required contract. Selecting local files does not upload them to a server; the browser validates and renders them locally. This is not an NWD/IFC conversion service or an automatic registration workflow.

Public viewing does not grant general reuse permission. See [the project rights notice](../LICENSE.md) and the dependency notices in `bim-explorer-assets/`.
