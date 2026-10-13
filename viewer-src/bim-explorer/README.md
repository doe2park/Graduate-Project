# Public BIM explorer source

This directory contains the maintained source for the static `grimes-bim-explorer.html` page. It preserves the October 13 local workshop's object selection, isolation, sectioning, materials, source-identity checks and render batching. Public hosting paths are isolated in `deployment.mjs`.

The root HTML contains the bundled application and inline CSS. Its import map pins Three.js and addons to **0.169.0**. Draco decoder files are served from `bim-explorer-assets/draco/`; source buffers and object IDs are unchanged. Existing full-building GLBs/JSON remain under `buildings/grimes/` and are loaded directly from this project's origin.

## Build and verify

Use Node.js 22+ and npm. From the repository root:

```sh
node scripts/build_bim_explorer.mjs
node scripts/build_bim_explorer.mjs --check
node --test tests/bim-explorer-deployment.test.mjs
```

The build invokes `npx --yes --prefer-offline --package=esbuild@0.25.0 esbuild` with pinned arguments. The first invocation needs npm registry access to download the build tool; subsequent invocations can reuse npm's cache. The browser does not run npm or esbuild. No unpinned build tool is used. `--check` exits unsuccessfully if the generated HTML or input/output hash manifest is stale.

Edit the source modules, `style.css` or `index.template.html`, then rebuild. Do not hand-edit the generated root HTML. `bim-explorer-assets/build-manifest.json` records SHA-256 hashes and byte sizes for shipped source/assets and the generated page; it contains no timestamp so identical inputs yield identical files.

## Hosting and data boundaries

Open `grimes-bim-explorer.html?model=full` for the complete Grimes model, or use `?model=regional` / `?model=conduit` for the bundled teaching examples. Desktop defaults to full; narrow screens default to regional unless a mode is explicit. Full loading requires the existing 24 source files and can be demanding on a phone. All modes keep original property/identity validation.

The regional package is a partial Level 1 area: 492 objects and eight disciplines. Its transform is specific to Grimes. The public explorer supports prepared embedded GLB + matching JSON input, not direct NWD/IFC conversion or automatic spatial registration.

The UI shows source BIM properties and no verified element-level live feed. This page does not deploy the private/local Quest environment, physical AR calibration or BAS credentials. Scan comparison and the energy dashboard are separate linked public interfaces.

Original source files, copyright and third-party notices remain applicable. See the repository `LICENSE.md`, `bim-explorer-assets/THREE-LICENSE.txt`, and the Draco license/readme. Draco files are copied byte-for-byte from the existing workshop vendor distribution; the supplemental upstream license copy was obtained from the Draco 1.5.7 license URL, without claiming an independently verified decoder binary version.

For public provenance, `regional/provenance.json` replaces the original machine-specific repository and renderer paths with the public repository URL and repository-relative `grimes-bim-viewer.html`. These two metadata-only adaptations do not change geometry, IDs, source hashes or the recorded transform.
