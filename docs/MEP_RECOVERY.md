# MEP source recovery tools

`plan_mep_recovery.py` uses the canonical classification rules from `extract_mep_layer.py` to distinguish total CAD entities, excluded clearance/annotation entities, and eligible entities. It walks every eligible owner's subtree so repeated geometry leaves are requested even when a child name does not repeat its owner's class. Baseline sidecar IDs and names must match the source metadata. Generated planning files contain no APS credentials or source URN.

```sh
python3 scripts/plan_mep_recovery.py master.meta.json recovery-plan --bindings-dir buildings/grimes
```

Use the resulting `all.wanted.json` or per-layer `*.wanted.json` with the existing `nwd_extract_subset.js`. Preserve original APS translation and dbIds. The SVF reader can safely use `{filter: dbid => wanted.has(dbid), skipPropertyDb: true}` because properties were retrieved separately. The writer must use `deduplicate:false`, `center:false`, and the same filter.

For each raw export, pack fresh geometry with the documented safe flags. Existing compressed GLBs must never be re-encoded.

```sh
gltf-transform optimize recovery/duct/output.gltf recovery/duct.source.glb --compress draco --instance false --simplify false --palette false --join false --flatten false
python3 scripts/extract_mep_layer.py recovery/duct.source.glb master.meta.json duct recovery/grimes-duct.glb recovery/duct.elements.json
python3 scripts/verify_mep_recovery.py --raw-gltf recovery/duct/output.gltf --packed recovery/duct.source.glb --output recovery/grimes-duct.glb --elements recovery/duct.elements.json --baseline buildings/grimes/grimes-duct.glb --owners recovery-plan/duct.owners.json --report recovery/duct.verified.json
```

The verifier fails on any per-owner primitive-count change, missing/extra binding identity, root transform change, altered compressed buffer bytes during subsetting, or source-to-final transformed-bounds error of 1 mm or more. It reports old and new full bounds; added source geometry can legitimately expand the old bounds. Bounds use accessor min/max transformed through scene hierarchy, and do not independently decode every Draco vertex.

The old extractor's generated `_doc` and `survival.total` describe the historical master export. Before integration, update provenance to the original-ID no-dedup recovery and report total/excluded/eligible/with_geometry separately. Never equate excluded coordination volumes with geometry loss.

```sh
python3 -m unittest discover -s scripts -p test_mep_recovery.py -v
```

For large fresh exports where the standard optimizer spends excessive time comparing geometry, `dedup_raw_gltf.py` shares only byte-identical bufferViews/accessors/meshes while retaining every named node and transform:

```sh
python3 scripts/dedup_raw_gltf.py recovery/fire/output.gltf recovery/fire/input-dedup.gltf
gltf-transform draco recovery/fire/input-dedup.gltf recovery/fire.source.glb --method sequential
```

The sequential Draco method is necessary for the fire source: default edgebreaker discarded degenerate triangle indices in the original CAD mesh. The generic verifier catches this as a primitive-count mismatch. Always verify against the original `output.gltf`, not just an intermediate.

For bounded browser parsing, split the canonical fire GLB into floor chunks with at most 30,000 mesh nodes, keeping each owner's fragments together. The full canonical GLB remains untouched.

```sh
python3 scripts/split_element_glb.py recovery/grimes-fire.glb buildings/grimes/fire.elements.json recovery --prefix grimes-fire --max-nodes 30000
```

`grimes-fire.chunks.json` lists the resulting files, floor keys, owner counts, mesh-node counts, and byte sizes. The splitter checks exact identity union, per-owner primitive counts, byte-identical bufferViews, and unsplit owners. The viewer should parse and assemble each chunk in sequence, releasing the temporary parsed scene before proceeding to the next chunk.
