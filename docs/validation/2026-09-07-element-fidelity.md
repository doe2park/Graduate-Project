# Grimes element fidelity validation — 2026-09-07

## Scope

Fixed missing-meter zero/LIVE presentation, selection-response races, line selection and cross-floor neighbours. Added explicit source provenance, floor filtering, runtime geometry batching and a material-factor carbon scenario card. Restored missing geometry using the original translated combined NWD, preserving dbIds.

## Geometry recovery

| Layer | Before | After / eligible | Intentionally excluded | File MB (decimal) |
|---|---:|---:|---:|---:|
| Duct | 13,921 | 16,704 | 406 | 21.1 |
| Hydronic | 4,863 | 11,102 | 1,127 | 20.4 |
| Plumbing | 2,621 | 6,035 | 756 | 20.9 |
| Fire | 3,861 | 10,938 | 0 | 83.8 |

19,513 recovered entities; 66,620 total across ten layers. All six Revit GLBs remain byte-identical. Structure's 10,582 intentional exclusions explain its old misleading survival denominator: 2,420 / 2,420 eligible structures were already present.

`2026-09-07-recovery.json` records per-owner primitive count equality, ID-set equality, root transform equality, byte-verbatim bufferView subsetting, and accessor-derived transformed bounds. Maximum source/final bounds difference is 1.46e-9 m. Bounds validation does not independently decode all Draco vertices. Existing compressed GLBs were never recompressed; recovered layers originate from freshly extracted raw geometry. Fire required sequential Draco because edgebreaker discarded degenerate face indices; the rejected intermediate was not installed.

## Runtime

Same original fire GLB, same desktop headless Chrome viewport: fire batches 49,104 -> 63, scene draw calls 49,285 -> 244; CPU render-call median 130.3 ms -> 0.6 ms over eight submissions. This measures CPU submission, not GPU time or end-user FPS. The larger recovered fire alone has 1,198 batches, 10,938 IDs and 8,349,677 triangles.

Runtime merges retain every source triangle/segment, materials and vertex attributes; repeated geometry stays instanced. Source GLB names are resolved before runtime name uniquification can erase identity. Full-loading validation initially terminated during fire after nine layers; parser cleanup and suppression of redundant render calls during loading alone did not remove the peak. Fire is now loaded sequentially in five byte-identical chunks, maximum 29,991 mesh nodes per chunk. The complete ten-layer browser test then passed twice. Final runtime: 6,789 element batches (6,970 scene draw calls including the shell), 66,620 identities, zero missing IDs, exact triangle/segment totals, real ray selection, floor filter, carbon scenario and mobile overflow checks.

## Data limits

Element electricity remains an allocation of measured feeder totals, never element telemetry. Meter 76 remains unallocated. Existing panel maps with no attached documentary evidence remain available but labelled legacy-unverified. Fabrication attributes preserve source units; source GUIDs and CAD handles supplement, never replace, dbId.

Carbon is an explicit user-input scenario: Revit volume converted to m³, exact material, factor in kgCO₂e/m³, evidence text and lifecycle scope. No project EPD factor has been supplied; the UI does not invent one or claim whole-building/avoided emissions. Unsupported volume units or absent material produce no estimate.

## Reproduce

See `tests/README.md` for unit and browser validation. Browser telemetry and source-recovery reports accompany this document. Large-model GPU/memory limits still depend on the device; floor/type filters reduce the visible workload without changing the geometry.

## Final test evidence

41 unit regressions pass: 14 viewer/data, 13 real Three.js, 2 provenance, 7 recovery and 5 chunking. Final browser report: `2026-09-07-browser.json`. All tests use deterministic fixture meter data, not evidence of live BMO freshness.
