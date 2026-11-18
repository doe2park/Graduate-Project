# MD02 duct source recovery · November 18, 2026

## Finding

The previous extraction rule matched only short filenames such as `MD02.dwg`.
The archived combined-model metadata instead names
`UCBBE-FMB-MD_adammTJDRY-3D View - MD02 EXPORT.dwg`.
Consequently this source was omitted by classification, not absent from the original model.
The classifier now accepts the actual long export alias and resolves its source floor.

## Additive local result

- 3,541 MD02 owner records in metadata.
- 102 coordination/clearance exclusions; 3,439 eligible source owners.
- 2,944 owners with named geometry recovered from the archived deduplicated master.
- 495 eligible owners still have no named geometry there. They were not invented or reconstructed.
- Added 87,266 triangles and 489 line segments. 2,810 recovered identities pass the normal non-part quality filters.
- Combined duct: 19,648 identities, 976,728 triangles, 9,325 line segments, 24,453,252 bytes.
- Full available model: 69,564 identities, 48,815,489 triangle instances, 386,292 line segments.
- Default quality filtering retains 65,680 identities, including 243 records without drawable geometry.

The output is a **new** `buildings/grimes/grimes-duct-restored.glb` and
`duct-restored.elements.json`. The original `grimes-duct.glb` and
`duct.elements.json` remain byte-identical. Source IDs are unchanged, new IDs do not
overlap existing ones, and no Draco data was recompressed.

BIM Explorer, element BIM viewer, photo overlay, XR and Ask's spatial index select the
same recovered asset. Existing floor filters and quality rules still apply.
This recovery does not establish installed condition, surveyed alignment, field validation,
or public deployment. All edits remain local until separately published.

## Verification and provenance

`buildings/grimes/duct-recovery-provenance.json` records source/output SHA-256,
counts, missing IDs and checks. It intentionally omits machine paths and private source URNs.
Checks compare original and output per-owner primitive counts and bounds, and verify
compressed bufferViews byte-for-byte. Maximum source-to-output bound error: **0.0 m**.
Recovered bounds in the existing viewer frame:
`[-35.275, 9.515, -17.636]` to `[21.179, 14.395, 29.667]` metres.
These support the source Level 2 assignment; they are not survey measurements.

Reproduce from the owner's archived source files (not shipped in this repository):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/recover_duct_alias.py \
  --source /path/to/grimes-elements.glb \
  --metadata /path/to/grimes-elements.glb.meta.json
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_duct*.py'
PYTHONDONTWRITEBYTECODE=1 python3 scripts/build_element_quality.py --check
```

The recovery script verifies invariants before writing new outputs. The catalogue and
quality overlay also carry updated hashes/counts. To reproduce a full integration, rebuild
the source catalogue from the emitted provenance, regenerate the quality overlay and
BIM Explorer build, and rerun the complete test suite. The source files must not be
recompressed or replaced by synthetic geometry to make the missing count disappear.
