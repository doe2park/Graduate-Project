# Grimes element fidelity implementation plan

Approved scope: user requested all findings in the preceding diagnosis, including NWD analysis and geometry recovery where available.

Global constraints: preserve source GLBs byte-for-byte except verified staged recovery; keep dbId binding; never write data branch; self-contained viewer, three@0.169.0; never label inferred/modelled values as measured. Existing untracked files untouched.

1. Viewer correctness: regressions for missing meters, stale responses, line picking, cross-floor neighbours. Fix using an explicit selection token, meter availability states, line ID resolution and normalized floor provenance. Validate node tests.
2. Data fidelity: normalize four CAD-layer sidecars without electrical classification, remove unsupported panel-schedule assertion unless documentary evidence exists, expose coverage and actual sidecar path. Validate id sets and sample floors.
3. Rendering: retain compact instancing for reused geometry; merge unique geometry by level/material/type with indexed triangle ranges, cap vertex count, keep source files immutable. Adapt picking, highlights, filters and crosshair; measure old/new draw calls and frame times in browser. Geometry and identity tests use real Three.js fixtures and full GLBs.
4. Carbon card: parse explicit volume units; material-specific factor input with source and lifecycle scope, no default fabricated factors. Label calculation MODELLED, unsupported/missing inputs show no estimate. Validate units, zero and invalid values.
5. Recovery: discover original combined NWD/compatible APS exports; stage targeted recovery and verify names, draco buffer hashes, bounds before replacing. If missing sources/access, document exact blocker and provide tested extraction planning tooling.
6. Integration: rerun regressions, browser test all layers and filters; run read-only GLB identity/hash audits, inspect diff, independently review. Update handoff and validation report. No deployment claim without live verification.

Ruling: prior explicit approval covers the diagnosed design; no repeated design approval. Work on main per AGENTS.md. Repo changes applied via sandbox escalation. Implementation staged in /private/tmp to make each patch concrete and reviewable.

Completion: all six steps implemented and independently reviewed. All 41 unit regressions and the complete ten-layer browser validation passed. Recovery restored 19,513 entities from the original translated NWD; see docs/validation/2026-09-07-element-fidelity.md for evidence and remaining input/device limits.
