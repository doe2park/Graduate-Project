# Data and JSON sharing guide

Updated September 25, 2026. [Project overview](../README.md)

JSON is a structured data format. The project uses several distinct JSON datasets; they are not interchangeable.

| Dataset | Purpose | Geometry / live readings included? |
|---|---|---|
| `buildings/grimes/*.elements.json` | Published, layer-specific element identities and properties | Geometry is in the corresponding GLB; design properties are not telemetry |
| Automated outputs on the `data` branch | Collected utility observations and history | No BIM geometry; freshness and sample coverage must be checked |
| Capture manifests under `scan-assets/` | Published photo locations, file references and capture metadata | Reference separate images/meshes; alignment status is capture-specific |
| `props_revit.json` (shared separately) | Full property groups for Revit-categorized elements | No 3D geometry or live sensor readings |

## Full Revit property export

The inspected local `props_revit.json` is approximately **49.89 MB** and contains **55,631 records**. Its top-level keys are `_doc` and `elements`; `elements` is an object keyed by exported identifiers. Records contain a name, an external identifier and available source property groups such as `Element`.

The source description is: “Revit-categorized elements with full property groups (from grimes-elements.glb.props.json)”. Property groups and fields vary between records. Values may include units as strings. Do not assume every element has every field, or that every source identifier is a stable Revit GUID across exports.

This export is not the same population as the 66,620 rendered identities across the ten public layers: fabrication/CAD entities and Revit-categorized property records have different scopes. Before joining a full export to viewer layers, verify source model/revision and identifier correspondence. An identical-looking ID from another source is not sufficient.

## Delivering data to a collaborator

For property analysis, share the JSON through a recipient-restricted Drive link, alongside a short description of the source, schema, units and limitations. A compressed ZIP is also suitable. For visual inspection or an object-to-geometry join, provide the corresponding geometry and a verified identity mapping as well.

For reproducibility, record the delivered filename, export revision/date when known, byte count and SHA-256 hash. Do not describe a filesystem modification date as the model's capture date. Send the agreed snapshot, not an ambiguous mixture of similarly named copies.

The full property export and original capture files are **not added to GitHub by this documentation update**. Public viewer sidecars remain available in the repository. Access permissions and third-party rights must be respected when sharing source exports.
