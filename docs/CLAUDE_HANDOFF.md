# Claude handoff — Campus and Interior Digital Twin

**Updated October 14, 2026. Public, sanitized continuation guide.**

Read [AGENTS.md](../AGENTS.md) first, then this document, [README.md](../README.md), and the instructions for the component you will change. This is project context, not authorization for a deployment or an unrelated rewrite.

This version intentionally excludes workstation paths, private document links, unpublished home imagery, internal server addresses, account information and credentials. All source paths below are repository-relative unless explicitly described as local-only work.

## 1. The research and the current boundary

The project connects **captured site appearance, identified BIM components and operational information** for existing buildings with incomplete drawings and sensor coverage. Grimes Engineering Center is the detailed pilot. The longer-term goal is transferable, evidence-aware inspection, including on-site use through display-equipped AR hardware.

The research has two streams:

```text
INDOOR CAPTURE                         BIM
Phone / 360 imagery                    Original building model
          |                                      |
Prepare photographs/video              Preserve component IDs and properties
Estimate cameras and spatial structure Connect verified operational records
Choose an exploration representation   Optimize loading, storage and rendering
          |                                      |
          +---------- spatial registration -------+
                                  |
                  Same-place appearance, objects and information
                                  |
                      Tracked on-site inspection
```

Reconstruction and rendering are parts of the system, not the research contribution by themselves. Proposed evaluation includes task completion, correct component identification, registration reliability, information provenance, update continuity and runtime cost. A completed user study or demonstrated improvement in decision accuracy is not claimed.

### Public implementation versus local experiments

| Area | Available in this repository | Separate local research status |
|---|---|---|
| Full BIM explorer | `grimes-bim-explorer.html` and maintained source in `viewer-src/bim-explorer/` | Source for the richer desktop workshop |
| Element/data viewer | `grimes-bim-viewer.html` | Related properties/data inspection in WebXR prototypes |
| Scan comparison | Public photo/mesh comparison with stored registrations | Additional recorded-viewpoint inspection experiments |
| Gaussian pipeline | Methods and processing scripts are documented | Trained raw-video scenes, evaluation renders and teaching notebooks remain separate |
| Quest optimization | The local Quest runtime is not shipped by this documentation update | Latest storage/visibility/material experiments are summarized below |
| New memory benchmark | Summary only in this handoff | Full raw reports, runtime packages and source snapshots are not included here |

**A fresh clone does not contain the latest local Quest runtime or its 54-package benchmark.** Do not invent files from the local implementation or attribute its measurements to the deployed explorer. Public explorer code baseline at this handoff: commit `35d1586d`.

## 2. Open the demonstrations

| Interface | Live page | Source |
|---|---|---|
| Full BIM Explorer | [Open complete Grimes model](https://doe2park.github.io/Graduate-Project/grimes-bim-explorer.html?model=full) | [Generated page](../grimes-bim-explorer.html), [editable modules](../viewer-src/bim-explorer/) |
| Element BIM viewer | [Open viewer](https://doe2park.github.io/Graduate-Project/grimes-bim-viewer.html) | [HTML](../grimes-bim-viewer.html) |
| Campus map | [Open map](https://doe2park.github.io/Graduate-Project/grimes-campus-map-arcgis.html) | [HTML](../grimes-campus-map-arcgis.html) |
| Energy dashboard | [Open dashboard](https://doe2park.github.io/Graduate-Project/campus-energy-dashboard.html) | [HTML](../campus-energy-dashboard.html) |
| Weekly history | [Open report](https://doe2park.github.io/Graduate-Project/weekly-report.html) | [HTML](../weekly-report.html) |
| Scan/BIM | [Open comparison](https://doe2park.github.io/Graduate-Project/scan-compare.html) | [HTML](../scan-compare.html) |
| Design versus actual | [Open performance page](https://doe2park.github.io/Graduate-Project/grimes-performance.html) | [HTML](../grimes-performance.html) |

The richer public BIM Explorer supports source-property inspection, search, isolation/hiding, floors/systems and sectioning. The element viewer supplies the established operating-data context. They serve different inspection tasks; do not replace either with an old small teaching sample.

Desktop Explorer defaults to all ten BIM layers. Narrow screens use a smaller regional default unless `model=full` is requested. The regional package contains 492 objects in a partial Level 1 area; it is not the whole building.

## 3. Files Claude can actually edit in a fresh clone

| Repository path | Responsibility |
|---|---|
| `viewer-src/bim-explorer/viewer.mjs` | Public explorer orchestration, interaction and controls |
| `viewer-src/bim-explorer/source-model.mjs` | Source-model loading and identities |
| `viewer-src/bim-explorer/render-tier.mjs` | Source-preserving rendering/batching |
| `viewer-src/bim-explorer/object-view.mjs` | Object inspection behavior |
| `viewer-src/bim-explorer/record-index.mjs` | Source record lookup |
| `viewer-src/bim-explorer/asset-cache.mjs` | Asset caching |
| `viewer-src/bim-explorer/demand-renderer.mjs` | Render scheduling |
| `viewer-src/bim-explorer/deployment.mjs` | Public hosting paths |
| `viewer-src/bim-explorer/style.css` | Public explorer styles |
| `viewer-src/bim-explorer/index.template.html` | Explorer HTML template |
| `scripts/build_bim_explorer.mjs` | Pinned build and consistency check |
| `tests/bim-explorer-deployment.test.mjs` | Deployment/source contract tests |
| `bim-explorer-assets/` | Catalog, small examples, vendor decoders and build manifest |
| `buildings/grimes/` | Canonical GLBs and identity sidecars |
| `scan-assets/` | Published capture packages, meshes and panoramas |
| `docs/` | Methods and provenance |

Read the [Explorer guide](BIM_EXPLORER.md) and [source README](../viewer-src/bim-explorer/README.md). Edit maintained modules, then rebuild the root HTML; do not hand-edit the generated explorer. The established element viewer and other canonical pages have their own single-HTML architecture.

The local Quest experiment has additional concepts named spatial visibility, material interning, adaptive detail, exact array storage, sensor adapters and runtime benchmarking. Those local modules are **not public import paths in this clone**. Porting any of them requires a separate reviewed implementation and verification.

## 4. Source identity, model scope and hard invariants

The ten BIM layers contain **66,620 source identities**:

| Layer | Identities |
|---|---:|
| Equipment | 1,143 |
| Receptacles/data | 4,927 |
| Lighting | 1,735 |
| Life safety | 553 |
| Structure | 2,420 |
| Electrical conduit | 11,063 |
| Ductwork | 16,704 |
| Hydronic/mechanical piping | 11,102 |
| Plumbing | 6,035 |
| Fire protection | 10,938 |

Public full-BIM scope is 48,728,223 triangle instances. The separate local experiment also loads 4,951 Level 1 design-context objects, producing **71,571 identities / 57,215,133 source triangle instances**. Do not mix those inventories or report local context as public whole-building content.

For Revit-category layers, the original GLB node name represents the source element dbId; `*.elements.json` binds that identifier to properties. Fabrication/CAD MEP layers use entity identity in the Navisworks hierarchy. Preserve a layer/building namespace when joining records.

GLTFLoader can uniquify names. The original identity must survive parsing, clones, instancing, batching and selection. Triangle/line ranges resolve picks back to source elements; a render batch is not the source object's identity.

### Never violate these rules

1. **Do not recompress existing Draco GLBs.** Subset with the documented byte-preserving extraction/splitting pipeline. Verify source bytes, primitive counts and bounds.
2. **Do not rename or flatten away identity nodes.** Preserve GLB-to-sidecar joins and exact source picking.
3. **Do not manually write the `data` branch.** GitHub Actions owns it.

Also retain honest provenance, pinned dependencies, copyright/third-party notices and mobile usability. Do not restore the removed Building Shell UI. Historical offline architectural reference geometry used for registration does not authorize restoring that feature.

## 5. October 14 storage experiment — local results

The following is a **maintainer-recorded local experiment summary**. The underlying adaptive packages, raw reports and runtime source snapshots are not distributed by this documentation commit. A fresh public clone cannot independently reproduce these measurements.

Scope: 54 packages; 71,571 identities; 57,215,133 source triangle instances; 385,840 line segments; 6,867 scene batches. Canonical GLBs and encoded runtime packages were unchanged.

| Quantity | Original | Compact storage |
|---|---:|---:|
| Allocated CPU geometry backing arrays | 1,050,983,978 B | 951,623,267 B |
| Decimal MB | 1,050.984 | 951.623 |
| Distinct BufferAttribute potential upload payload | 1,073,943,883 B | 1,016,589,058 B |
| Source IDs, source/LOD values, material records and ranges | Preserved | Preserved |

CPU reduction: **99.361 MB / 9.454%**. Attribute upload-payload reduction: **57.355 MB / 5.341%**.

Methods:

- Share byte-identical arrays only after type/shape, hash and byte comparison; bound the pool to a load and clear its references on success/failure.
- Narrow indices to Uint16 only where safe, preserving the reserved primitive-restart index, primitive order and winding.
- Store exact binary source colours as normalized bytes; preserve original source values and copy-on-write selection isolation. Arbitrary highlight colours then use byte precision on converted arrays.

Positions/normals retain Float32 precision. The local audit checked all 54 packages and 93 selection/reset operations. Available source geometry remains intact; adaptive LOD can still draw reduced detail for distant batches.

These are **retained decoded CPU arrays** and **potential attribute-upload payload**, not total browser RAM, measured GPU residency, loading peak or HTTP cache size. The live UI's approximately 952.1 MB is a separate observation and has not been reconciled with the controlled 951.623 MB inventory.

### Timing: memory improved; frame cadence stayed approximately unchanged

Desktop Apple M4 Pro browser, sequential 960×960 renders for two eyes, unrecorded ABBA, 60 warm-up frames and 240 measured poses per pass. Both conditions already enable the same spatial visibility, material sharing and detail settings; only storage differs.

| Workload | Original p50 / p95 | Compact p50 / p95 |
|---|---|---|
| Whole-model overview | 55.50 / 56.105 ms | 55.50 / 55.80 ms |
| Interior walk/selection | 11.20 / 17.20 ms | 11.20 / 17.005 ms |

Camera poses, eye views, submitted counters, selected source IDs and ray-hit positions matched. The reduction establishes lower retained array storage, not faster rendering or adequate Quest performance. Correlated samples and pass-order drift limit inference.

An earlier, separate visibility/material/selection experiment reported indoor p50 16.55→9.90 ms and p95 18.20→17.90 ms. Do not attribute that earlier change to compact storage. Do not compare an older overview's 41.7 ms with the new 55.5 ms as a controlled before/after result.

The local snapshot recorded 206 passing checks: 181 JavaScript, 21 HTTP/receiver and 4 HTTPS. Those checks belong to the separate local implementation; they are not this public repository's current test count. Physical Quest timings for that latest revision remain pending.

## 6. Capture and Gaussian reconstruction

Keep separate:

- **Published panoramas:** actual photographs at recorded stations. Crossfades do not establish measured intermediate parallax.
- **Published scan mesh:** exported geometry used by the registered comparison. The vendor's reconstruction internals cannot be established from an export alone.
- **Earlier posed-image Gaussian pilot:** uses existing capture poses and its documented transform chain.
- **Independent raw-video SfM/Gaussian experiment:** estimates cameras from imagery; metric scale and BIM alignment remain unvalidated.

The raw-video workflow is imagery preparation/FFmpeg → COLMAP/PyCOLMAP SfM → inspect cameras and sparse components → Brush Gaussian optimization → evaluate/export. INSV requires export/stitching before that workflow. Gaussian PLY is not a triangle mesh.

Sparse points are triangulated feature tracks. Camera markers show estimated viewpoints, not BIM objects. Overlapping imagery is required; not every pixel becomes a 3D point, and registration can split into multiple components with arbitrary scale.

### Saved training evidence used in the latest presentation

No new training was launched for the October 14 presentation update. Existing saved outputs were evaluated:

- 144 prepared perspective views; 142 registered views; 7,565 sparse points; 124 training and 18 evaluation views.
- Same-run 1,000→2,000 steps: mean PSNR 21.9453→23.5846 dB.
- Configuration A: 2,000 steps, 512-pixel input, SH degree 1, 150k capacity; 20,728 final Gaussians.
- Configuration B: 8,000 steps, 768-pixel input, SH degree 2, 300k capacity; 291,825 final Gaussians; mean PSNR 26.5644 dB.
- B improved 17/18 saved evaluation views. One view declined; preserve that result.

A/B also differ in population growth settings. The comparison shows combined configuration effects, not steps alone. Nearby/same-panorama training views limit evaluation independence. Empty optimizer logs do not support a training-loss curve. Image agreement does not validate metric scale, physical geometry or generalization to independent rooms.

Brush repeatedly renders a known view, compares it with the source photograph, propagates the image objective and updates Gaussian parameters. A controlled learning study should keep settings/split fixed, save genuine checkpoints and logs, and evaluate separate spatial areas.

Read [raw-video reconstruction](RAW_VIDEO_RECONSTRUCTION.md), [earlier Gaussian methodology](GAUSSIAN_RECONSTRUCTION_METHODS.md), and [new capture onboarding](CAPTURE_ONBOARDING.md). The private/local training package and notebooks are not shipped with this handoff.

## 7. Registration and new floors/buildings

Read [the actual registration method](SCAN_BIM_REGISTRATION.md), [accepted registration](../alignment-analysis/accepted-registration.json), [captured panoramas](CAPTURED_PANORAMA_VIEWER.md), and [September capture update](CAPTURE_UPDATE_20260917.md).

May's documented fit converts coordinate axes, searches coarse poses and refines trimmed point-to-point ICP constrained to **yaw + XYZ translation, with scale fixed at one**. Its approximately 0.13 m internal median nearest-reference residual is not surveyed accuracy. Candidate selection/internal checks are not independent physical control.

The September 17 capture has a separately labelled provisional alignment. The raw-video Gaussian experiment has a different, unvalidated scale/alignment status. Do not reuse an old Cupix-frame angle, add floor elevation twice, or assign Grimes registration to a new building by changing a manifest URL.

Apply accepted transforms consistently to camera position and orientation, with the inverse for reverse navigation. Shared viewpoint means position, direction and field of view agree. A projected BIM point in a photo is a candidate geometric correspondence, not proof of physical device identity.

New data needs a building/capture namespace, units/up-axis confirmation, overlap, camera/geometry checks, a separately fitted transform and independent check points. Sparse monocular SfM needs scale established before fixed-scale ICP. A complete connected Level 1/Level 2 result is not claimed by this update.

## 8. Operating data and evidence honesty

The public pipeline is Berkeley BMO utility observations → scheduled GitHub Actions → JSON on the machine-written `data` branch → static interfaces. It does not imply direct BAS/BACnet access to every BIM component.

- **Measured:** real meter observations at the meter's actual scope.
- **Modelled:** explicitly labelled design-weighted allocations or provisional system relationships.
- **Inferred:** derived properties such as some floor assignments.

Meter 77 design-VA allocation and meter 3 design-CFM allocation are uncalibrated scenarios. **Meter 76 is not apportioned:** defensible component/circuit distribution evidence is missing. Voltage, floor, category, name or proximity do not prove circuit membership.

A meter total on a component card is meter/system context, not that component's consumption. Missing/stale data must never become live zero. Do not fabricate direct readings for a more impressive selection demo. Verified device/asset identifiers, panel schedules, point lists, units, timestamps and documentary relationships are needed for direct bindings.

The public Explorer currently focuses on source BIM properties; use the established element viewer for operating-data context. The newer local adapter design validates exact stable IDs and provenance and avoids fetching/decoding operational data every XR frame. It is not a deployed public BAS integration.

Weekly history records collector observations, not guaranteed continuous histories. Sample-mean × 24-hour extrapolation is not a measured meter-counter delta. See [data sharing](DATA_SHARING.md) and preserve uncertainty and freshness labels.

## 9. Quest and AR status

The owner has used a Quest 2 to inspect earlier versions and reported qualitative issues with exit controls, pointers, readability, materials and model completeness. The latest source-fidelity/storage work still needs physical hardware measurement.

- Tabletop passthrough places a scaled model in a tracked room; it does not establish building registration.
- VR uses a virtual reference frame.
- On-site overlay needs live headset-to-building calibration; a stored scan-to-BIM transform alone does not provide it.

The calibration design uses separated matching landmarks, a constrained transform and an independent check, with rechecks after tracking resets. Desktop two-eye rendering is not a Quest GPU/compositor simulation, tracked field test or proof of persistent anchors. Verify device APIs before promising a future glasses model is supported.

## 10. Presentation and documentation status

An editable 22-slide presentation was updated separately for October 15. Private cloud document identifiers, media links and unpublished captures are deliberately omitted from this public handoff.

The narrative now covers capture/BIM streams, actual reconstruction, a render/compare/update training diagram, identical source/A/B detail crops, varied real BIM selections, storage diagrams, the implemented workflow, headset methodology and a future evaluation flowchart. Full-model context is shown before and after component inspection. Captured-location comparison uses “Same viewpoint” and explicitly labels revealed concealed services; physical device identity remains unverified.

Presentation conventions: Calibri, navy/gold, consistent title/subtitle/content/footer positions, at most three main content regions, editable text/diagrams, equal image frames and preserved aspect ratios. Use real evidence and readable captions. The existing public element viewer remains a presentation entry point; the deployed richer Explorer is also available.

The manuscript and full private evidence ledger are maintained separately. Their current private links/locations are intentionally not included. A public code change must not be described as a synchronized manuscript or presentation update unless that was actually completed.

## 11. Reproduce public development

For viewing, Python 3 is sufficient to serve the tracked public files:

```sh
git clone https://github.com/doe2park/Graduate-Project.git
cd Graduate-Project
python3 -m http.server 8000
```

Open `http://localhost:8000/grimes-bim-explorer.html?model=full`. Tracked geometry/JSON are separate assets; opening only an HTML file is insufficient. Online libraries/data may require Internet access. On another computer, its own `localhost` does not reach this server.

For public Explorer edits, use Node.js 22+ and the pinned build workflow:

```sh
node scripts/build_bim_explorer.mjs
node scripts/build_bim_explorer.mjs --check
node --test tests/bim-explorer-deployment.test.mjs
```

The first build may fetch the pinned esbuild package from npm. Read the source README before running it. Generated HTML and the build manifest must match the maintained modules. Read component-specific instructions for other tests.

Do not run local-only workshop commands against guessed paths in this clone. Do not overwrite historical evidence during a new experiment. Save a new dated output, input/source hashes, scope, settings, environment, raw results and limitations. Isolate one policy at a time; keep camera route, eye resolution, model scope and LOD fixed. Measure without video capture and record presentation footage separately.

## 12. Useful next tasks for Claude

1. Inspect the public source and confirm current behavior before changing it. Keep the rich full-model Explorer and element/data viewer roles clear.
2. Add bounded, measurable optimizations to the public code only after preserving exact source identity, properties, geometry and materials. Separate transfer, decode peak, retained arrays, GPU buffers, draw/state changes and frame intervals.
3. Consider on-demand LOD/index residency with explicit retention, upload, eviction and reload accounting. Retaining a second encoded copy or dropping one JavaScript view is not proof of a reduction. The local candidate is not yet a public implementation.
4. Improve versioned capture/model registration and independent checks without assigning sensor identities from geometry alone.
5. Keep mobile/touch layout, memory, contrast, labels and object selection usable. Avoid replacing complete content with a tiny sample without a clear user choice.
6. Maintain evidence-aware data adapters and missing/stale states. Request documentary bindings through the owner rather than inventing direct telemetry.
7. Preserve neutral/worse results and distinguish software tests, image agreement, internal residuals, real accuracy and headset performance.

### Suggested continuation instruction

> Read AGENTS.md and this handoff, inspect the current tracked public code, and identify one bounded next change. Preserve source GLBs, node identities, material values and measured/modelled/inferred labels. Distinguish this repository from the summarized local experiments. Verify the change before claiming success, and report exactly what is implemented, tested and deployed.

Public documentation does not grant reuse rights beyond [LICENSE.md](../LICENSE.md) and applicable third-party licenses. Do not expose credentials or publish additional private datasets as part of continuation work.
