#!/usr/bin/env python3
"""
extract_mep_layer.py — cut the CAD-fabrication MEP tiers out of the APS master.

    python3 scripts/extract_mep_layer.py master.glb master.meta.json LAYER out.glb out.elements.json

The combined NWD carries ~30k MEP fabrication entities that have NO Revit
category (they come from per-floor DWG/NWC fabrication models — mechanical
piping, plumbing, fire protection, ductwork — plus the ENG_R22.rvt MEP
model), so scripts/extract_layer.py's category-driven owner walk skips them.
Their tree is instead:

    <file>.nwc  →  CAD layer (F-SPRN-DRAIN-N, M-DFT-…)  →  entity ("Pipe26877")
                →  instance node (same name)            →  geometry leaves

Element identity here = the depth-3 ENTITY node: every geometry leaf is
renamed to its entity dbId, so clicking any segment of Pipe26877 selects the
pipe, and the sidecar describes the pipe once. The CAD layer (depth 2) is
kept as `system`, the floor comes from the source-file prefix, and `type`
is derived from the entity name shape (the fabrication family).

Geometry is copied byte-for-byte from the master (draco untouched), same
survival caveat as the other master-sourced layers: the master was exported
with dedup, so repeated fittings lost their nodes — the sidecar `survival`
block reports honest per-layer counts.
"""
import json
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from extract_layer import read_glb, write_glb, subset_from_source

# layer -> source-file rule (regex on source_file; ENG_R22.rvt splits by name)
SRC = {
    "duct":     (r"^MD\d+\.dwg$", r"duct|flex drop|damper|tap|transition"),
    "hydronic": (r"FMB-MP\.dwg$", r"pipe|coupling|valve|hanger|sprink"),
    "plumbing": (r"FMB-PL\.dwg$", None),
    "fire":     (r"FP\.DWG$",     None),
}
CATEGORY = {"duct": "Ductwork (fabrication)", "hydronic": "Hydronic Piping (fabrication)",
            "plumbing": "Plumbing Piping (fabrication)", "fire": "Fire Protection Piping (fabrication)"}
# entity-name shape -> type (first match wins)
TYPES = [
    (r"ACCESS SPACE", None), (r"^Pipe\d+$", "Pipe segment"), (r"^Fitting\d", "Fitting"),
    (r"Copper Pipe", "Copper pipe"), (r"No-Hub Pipe", "Cast-iron pipe"), (r"BLK ERW PIPE|STD ERW", "Steel pipe"),
    (r"No-Hub Heavy Duty Coupling|No-Hub Coupling|Nested_CN_Coupling|Coupling", "Coupling"),
    (r"No-Hub (Short Sweep|Eighth Bend|Quarter Bend|Combination|Sanitary|Wye|Tee)", "Cast-iron fitting"),
    (r"Spiral Duct", "Spiral duct"), (r"Straight Rect", "Rectangular duct"), (r"^Straight\b|Fabrication Skin_ Straight", "Round duct"),
    (r"Square Elb|Rectangular Elbow|ProPress Copper.*Ell|\bElbow\b|\bElb\b", "Elbow"),
    (r"Transition", "Transition"), (r"Conical Tap|\bTap\b", "Duct tap"),
    (r"Damper", "Damper"), (r"Flex Drop", "Flex drop"), (r"Flex", "Flex duct"),
    (r"Sprinkler", "Sprinkler"), (r"Valve", "Valve"), (r"Nipple", "Nipple"), (r"Weld Neck|Flange", "Flange"),
    (r"Hanger|Gripple|Single Strap|Unistrut|Seismic Brace", "Hanger / support"), (r"Reducer", "Reducer"),
    (r"Tee\b|Wye\b|Cross\b", "Branch fitting"), (r"\bCap\b", "Cap"),
    (r"Price SDV|Coil", "Terminal unit"), (r"Duct", "Duct"), (r"Pipe", "Pipe"),
]
# CAD-layer decode for entities whose own name is bare geometry ("PolyFace Mesh", "Arc", ...)
GENERIC_NAMES = re.compile(r"^(PolyFace Mesh|Arc|Circle|SPLINE|Solid|Line Set|3D Face Set|Line|Mesh|Point|Ellipse|Block)$", re.I)
CADMAP = [
    (r"-CNTR$", None),                     # centerline annotation layers: excluded
    (r"NOFLY|ACCESS", None),               # coordination volumes: excluded
    (r"M-HVAC-DUCT", "Duct"), (r"M-DFT", "Duct fitting"),
    (r"P-PIPE|P-DOM|P-SAN|P-STM", "Pipe"), (r"E-POWR-CNDT", "Conduit"),
    (r"F-SPRN-HANG", "Hanger / support"), (r"F-SPRN-FITG", "Fitting"),
    (r"F-SPRN-EOLR", "End-of-line restraint"), (r"F-SPRN-BRAC", "Seismic brace"),
    (r"F-SPRN-FH", "Fire hose cabinet"), (r"F-SPRN-DRAIN", "Drain pipe"), (r"F-SPRN", "Sprinkler piping"),
    (r"Z-MNTG", "Mounting"),
]
LEVEL = {"00": "LOWER LEVEL", "01": "LEVEL 01", "02": "LEVEL 02", "03": "LEVEL 03", "04": "LEVEL 04"}


def type_of(name, cad_layer):
    if not GENERIC_NAMES.match(name or ""):
        for rx, t in TYPES:
            if re.search(rx, name, re.I):
                return t                    # None = excluded (e.g. ACCESS SPACE boxes)
    for rx, t in CADMAP:
        if re.search(rx, cad_layer or "", re.I):
            return t
    return cad_layer or "Element"


def level_of(src):
    m = re.match(r"^(?:MD)?(\d\d)", src or "")
    return LEVEL.get(m.group(1)) if m else None


def main(master_glb, metap, layer, out_glb, out_json):
    src_rx, rvt_rx = SRC[layer]
    meta = json.load(open(metap))["elements"]
    byext = {e["externalId"]: did for did, e in meta.items()}

    def wanted(e):
        src, n = e.get("source_file") or "", e.get("name") or ""
        if e.get("category"):
            return False
        if re.search(src_rx, src, re.I):
            return True
        return bool(rvt_rx) and "ENG_R22.rvt" in src and re.search(rvt_rx, n, re.I)

    g, bin_ = read_glb(master_glb)
    root = {k: v for k, v in g["nodes"][g["scenes"][0]["nodes"][0]].items() if k != "children"}
    keep, per_owner = {}, defaultdict(int)
    total_entities = set()
    for did, e in meta.items():
        if wanted(e) and len(e["externalId"].split("/")) == 3:
            total_entities.add(did)
    def owner_type(e, nm):
        parts = e["externalId"].split("/")
        if len(parts) < 3:
            return None, None
        owner = byext.get("/".join(parts[:3]), nm)
        oe = meta[owner]
        cad_layer = meta.get(byext.get("/".join(parts[:2]), ""), {}).get("name")
        return owner, type_of(oe.get("name") or "", cad_layer)

    for i, n in enumerate(g["nodes"]):
        nm = n.get("name")
        if not nm or "mesh" not in n:
            continue
        e = meta.get(nm)
        if not e or not wanted(e):
            continue
        owner, t = owner_type(e, nm)
        if not owner or t is None:
            continue                        # excluded (centerlines, coordination volumes)
        keep[i] = owner
        per_owner[owner] += 1

    out, acc, bv, mesh, mat = bytearray(), [], [], [], []
    leaves = subset_from_source(g, bin_, keep, out, acc, bv, mesh, mat)
    new_nodes = [root, {"name": f"layer:{layer}", "children": list(range(2, 2 + len(leaves)))}] + leaves
    root["children"] = [1]
    doc_glb = {"asset": {"version": "2.0", "generator": "extract_mep_layer.py"}, "scene": 0,
               "scenes": [{"nodes": [0]}], "nodes": new_nodes, "meshes": mesh, "accessors": acc,
               "bufferViews": bv, "materials": mat, "buffers": [{"byteLength": len(out)}],
               "extensionsUsed": ["KHR_draco_mesh_compression", "KHR_texture_transform"],
               "extensionsRequired": ["KHR_draco_mesh_compression"]}
    write_glb(doc_glb, out, out_glb)

    els = {}
    for o, cnt in per_owner.items():
        e = meta[o]
        parts = e["externalId"].split("/")
        cad_layer = meta.get(byext.get("/".join(parts[:2]), ""), {}).get("name")
        nm = e.get("name") or ""
        els[o] = {"name": nm, "category": CATEGORY[layer], "level": level_of(e.get("source_file")),
                  "source_file": e.get("source_file"), "leaves": cnt,
                  "type": type_of(nm, cad_layer), "system": cad_layer}
    tc = Counter(v["type"] for v in els.values())
    doc = {"_schema": "twin-elements-binding/2", "layer": layer, "model": out_glb.split("/")[-1],
           "_doc": f"MEP fabrication tier '{layer}': glb node name (= entity dbId) -> identity. "
                   "Cut from the APS master by scripts/extract_mep_layer.py (CAD entities, no Revit category).",
           "survival": {CATEGORY[layer]: {"total": len(total_entities), "with_geometry": len(els)}},
           "elements": els}
    json.dump(doc, open(out_json, "w"), indent=1)
    print(f"{layer}: {len(els)}/{len(total_entities)} entities / {len(leaves)} leaves / {len(mesh)} meshes / "
          f"{len(mat)} materials / {len(out)/1e6:.1f} MB bin; types " +
          ", ".join(f"{t} {c}" for t, c in tc.most_common(8)))


if __name__ == "__main__":
    main(*sys.argv[1:6])
