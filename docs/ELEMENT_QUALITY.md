# Element model quality overlay

`buildings/grimes/element-quality.json` lists known content defects of the ten element layers. The viewers apply it when a
layer loads. No GLB and no `*.elements.json` sidecar is changed, and all original 66,620 source identities are still there; 2,944 recovered MD02 identities are now added (69,564 total).

Build or check it with:

```bash
python3 scripts/build_element_quality.py
python3 scripts/build_element_quality.py --check
```

The script reads only the GLB JSON chunks (primitive modes, vertex counts, POSITION bounds) and the sidecars. Nothing is
decoded or re-encoded. Rebuild it whenever a GLB or a sidecar changes; `tests/test_element_quality.py` fails if it is stale.

## What it records (November 18, 2026)

| Key | Count | Meaning | What viewers do |
|---|---:|---|---|
| `hidden.annotation` | 2,740 | Line-only copy of a part on a CAD `-ANNO` layer; the solid twin shares its `source_guid` | Not drawn |
| `hidden.reference` | 205 | Layout points, sleeve points, clearance zones, load symbols | Not drawn |
| `hidden.duplicate` | 939 | Same type, name and bounding box (1 mm) as another element in the layer | The copy with the most triangles is drawn |
| `noGeometry` | 243 | Every primitive is one vertex (229 lights, 14 equipment items) | Kept; shown with a model note |
| `aggregate` | 6 | One fabrication object spanning most of a floor plate | Kept; shown with a model note |
| `storey` | 1,665 | The element's box lies wholly outside the storey its level label names | Filed under the storey that holds it; the source label stays visible |

65,680 identities are retained by the default visibility rules (including 243 source records without drawable geometry). Open any element page with `?flagged=1` to draw the hidden ones as well.

Storeys use slab tops measured in the element frame: Lower 0.69 m, Level 1 5.26 m, Level 2 9.53 m, Level 3 14.41 m,
Roof 18.98 m. A label is corrected only when the box misses the labelled storey by more than 1.0 m below its floor or
0.5 m above the next floor, so framing that hangs under its own floor and columns that span storeys keep their label.
`manifest.json` lists the Revit elevations, which are 0.83 m higher than this frame; it is not used for storey tests.

## Where it is applied

- `twin/element-quality.mjs` is the one implementation for the browser.
- `scan-xr.html`: hidden objects are cut from the scene graph before Draco decodes them; the Level filter uses the corrected storey.
- `grimes-bim-viewer.html`, `scan-bim.html`: hidden objects are removed before batching and leave lists, search and picking.
- `grimes-bim-explorer.html`: every identity is still loaded and verified against the source catalogue; the non-part objects start hidden and Focus shows one.
- `scripts/ask_twin/tools.py`: hidden objects are never offered to the model; `level` is the corrected storey.

## Not fixed here

- Level 2 ductwork was omitted by the earlier filename classifier, which accepted only short `MDxx.dwg` names. The archived source uses `UCBBE-FMB-MD_adammTJDRY-3D View - MD02 EXPORT.dwg`. A byte-preserving additive recovery now restores 2,944 eligible source identities; 495 eligible identities remain absent from that older deduplicated GLB. This is partial source recovery, not full as-built validation. See `buildings/grimes/duct-recovery-provenance.json` and `scripts/recover_duct_alias.py`. The original duct GLB and sidecar remain unchanged.
- 833 fabrication elements carry a CAD layer code as their type (`M-EQPM`, `A-GENM`), and most duct names are CAD primitive names.
- Revit elements that share a `source_guid` but sit in different places are left alone: they are separate instances.
