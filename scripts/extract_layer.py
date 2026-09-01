#!/usr/bin/env python3
"""
extract_layer.py — cut an element-tier web layer out of the APS master GLB.

    python3 scripts/extract_layer.py SRC1.glb[,SRC2.glb...] master.meta.json LAYER out.glb out.elements.json [props_revit.json]

Sources are searched in order: a leaf dbId takes ALL its nodes from the first
source that names it (the 2026-09-01 targeted subset — no dedup, every leaf
named — goes first; the 2026-08-03 master second for categories the subset
did not request, e.g. conduit runs). props_revit.json (optional) is the
Revit property dump; selected design parameters are copied into the sidecar.

Master = svf-utils export of the whole NWD (every geometry node named by its
leaf dbId, ~182k named nodes) + the properties sidecar (dbId -> name /
category / level / externalId / source_file). Element identity lives on an
ANCESTOR of the geometry leaf: the externalId is the containment path, so the
owning Revit element is the nearest prefix that carries a Revit category.

Output GLB keeps the master's root transform (Z-up feet -> Y-up metres), one
node per leaf renamed to its OWNER dbId (the viewer walks parents by name), and
only the meshes / draco bufferViews those leaves reference, copied byte-for-byte
(no re-encode: geometry is bit-identical to the master). No instancing nodes are
carried over, so no ghost nodes (see Design Decisions Log 2026-09-01).

Survival note: the master was exported with GPU-instancing dedup, so many
elements (e.g. 99% of receptacles) have no named leaf. The sidecar records
per-category survival so the UI can say "309 of 1,570" honestly.
"""
import json
import re
import struct
import sys
from collections import Counter, defaultdict

LAYERS = {
    "structural": ["Structural Framing", "Structural Columns", "Structural Foundations", "Structural Connections"],
    "lighting":   ["Lighting Fixtures", "Lighting Devices"],
    "conduit":    ["Conduits", "Conduit Fittings", "Cable Trays", "Cable Tray Fittings"],
    "lifesafety": ["Fire Alarm Devices", "Sprinklers", "Security Devices", "Specialty Equipment"],
    "fixtures":   ["Electrical Fixtures", "Data Devices", "Audio Visual Devices"],
    "furniture":  ["Furniture", "Casework"],
    "equipment":  ["Electrical Equipment", "Mechanical Equipment", "Air Terminals", "Plumbing Fixtures"],
}
# Revit parameters worth carrying into the sidecar (group, key) -> sidecar field
PROPS = [
    ("Element", "Mark", "mark"), ("Element", "Location", "location"), ("Element", "Comments", "comments"),
    ("Element", "Electrical Data", "electrical_data"), ("Element", "Watts", "watts"),
    ("Element", "Flow", "flow"), ("Element", "System Classification", "system_classification"),
    ("Element", "Pressure Drop", "pressure_drop"), ("Element", "Size", "size"),
    ("Element", "Mains", "mains"), ("Element", "MCB Rating", "mcb_rating"), ("Element", "Total Connected", "total_connected"),
    ("Element", "Volume", "volume"), ("Element", "Length", "length"), ("Element", "Area", "area"),
    ("Element", "Structural Material", "structural_material"), ("Element", "Structural Usage", "structural_usage"),
    ("Element", "Elevation from Level", "elevation_from_level"), ("Element", "Host", "host"),
    ("Element", "Family", "family"), ("Element", "Type", "revit_type"), ("Element", "Workset", "workset"),
    ("Element", "Phase Created", "phase"),
]
LEVEL_KEYS = [("Element", "Schedule Level"), ("Element", "Level"), ("Element", "Reference Level"),
              ("Element", "Base Level"), ("Reference Level", "Name"), ("Schedule Level", "Name"), ("Level", "Name")]
# family-name exclusions per layer (regex): structural keeps the PRIMARY structure —
# CDC-* is cold-formed partition framing (studs/tracks, 4,532 elements, 8.7k leaves),
# noflyzone-* are coordination clearance boxes. Both are legitimate Revit elements
# but not what a structural-monitoring twin instruments.
EXCLUDE = {"structural": r"^(CDC|noflyzone)"}


def read_glb(p):
    b = open(p, "rb").read()
    assert b[:4] == b"glTF"
    jl = struct.unpack("<I", b[12:16])[0]
    g = json.loads(b[20:20 + jl])
    bl = struct.unpack("<I", b[20 + jl:24 + jl])[0]
    return g, b[28 + jl:28 + jl + bl]


def write_glb(g, bin_, p):
    js = json.dumps(g, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    bin_ = bytes(bin_) + b"\0" * (-len(bin_) % 4)
    with open(p, "wb") as f:
        f.write(b"glTF" + struct.pack("<II", 2, 28 + len(js) + len(bin_)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(bin_), 0x004E4942) + bin_)


def owners(meta):
    """leaf/any dbId -> nearest categorized ancestor dbId (incl. self)."""
    ext2id = {e["externalId"]: i for i, e in meta.items()}
    cache = {}

    def owner(i):
        if i in cache:
            return cache[i]
        parts = meta[i]["externalId"].split("/")
        r = None
        for k in range(len(parts), 0, -1):
            j = ext2id.get("/".join(parts[:k]))
            if j and meta[j].get("category"):
                r = j
                break
        cache[i] = r
        return r
    return owner


def subset_from_source(g, bin_, keep, out, acc_list, bv_list, mesh_list, mat_list):
    """Copy the meshes/accessors/bufferViews/materials that `keep` (node idx -> owner)
    references from one source into the shared output lists; return new leaf nodes."""
    nodes = g["nodes"]
    mesh_map, acc_map, bv_map, mat_map = {}, {}, {}, {}

    def take_bv(i):
        if i not in bv_map:
            bv = dict(g["bufferViews"][i])
            off = bv.get("byteOffset", 0)
            out.extend(b"\0" * (-len(out) % 4))
            bv["byteOffset"] = len(out)
            out.extend(bin_[off:off + bv["byteLength"]])
            bv_map[i] = len(bv_list)
            bv_list.append(bv)
        return bv_map[i]

    def take_acc(i):
        if i not in acc_map:
            a = dict(g["accessors"][i])
            if "bufferView" in a:
                a["bufferView"] = take_bv(a["bufferView"])
            acc_map[i] = len(acc_list)
            acc_list.append(a)
        return acc_map[i]

    def take_mat(i):
        if i not in mat_map:
            mat_map[i] = len(mat_list)
            mat_list.append(g["materials"][i])
        return mat_map[i]

    def take_mesh(i):
        if i not in mesh_map:
            m = json.loads(json.dumps(g["meshes"][i]))
            for p in m["primitives"]:
                p["attributes"] = {k: take_acc(v) for k, v in p["attributes"].items()}
                if "indices" in p:
                    p["indices"] = take_acc(p["indices"])
                if "material" in p:
                    p["material"] = take_mat(p["material"])
                d = p.get("extensions", {}).get("KHR_draco_mesh_compression")
                if d:
                    d["bufferView"] = take_bv(d["bufferView"])
            mesh_map[i] = len(mesh_list)
            mesh_list.append(m)
        return mesh_map[i]

    leaves = []
    for i, o in keep.items():
        n = {k: v for k, v in nodes[i].items() if k in ("translation", "rotation", "scale", "matrix")}
        n["mesh"] = take_mesh(nodes[i]["mesh"])
        n["name"] = o
        leaves.append(n)
    return leaves


def main(sources, metap, layer, out_glb, out_json, propsp=None):
    cats = LAYERS[layer]
    meta = json.load(open(metap))["elements"]
    owner = owners(meta)
    props = json.load(open(propsp))["elements"] if propsp else {}

    per_owner = defaultdict(list)
    claimed = set()                 # leaf dbIds already taken from an earlier source
    root = None
    out, acc_list, bv_list, mesh_list, mat_list, leaves = bytearray(), [], [], [], [], []
    src_count = {}
    for src in sources.split(","):
        g, bin_ = read_glb(src)
        if root is None:
            root = {k: v for k, v in g["nodes"][g["scenes"][0]["nodes"][0]].items() if k != "children"}
        else:
            r2 = g["nodes"][g["scenes"][0]["nodes"][0]]
            assert r2.get("rotation") == root.get("rotation") and r2.get("scale") == root.get("scale"), "source frames differ"
        keep = {}
        names_here = set()
        for i, n in enumerate(g["nodes"]):
            nm = n.get("name")
            if not nm or "mesh" not in n or nm not in meta or nm in claimed:
                continue
            o = owner(nm)
            if o and meta[o].get("category") in cats and not (
                    layer in EXCLUDE and re.match(EXCLUDE[layer], meta[o].get("name") or "")):
                keep[i] = o
                names_here.add(nm)
                per_owner[o].append(nm)
        claimed |= names_here
        leaves += subset_from_source(g, bin_, keep, out, acc_list, bv_list, mesh_list, mat_list)
        src_count[src.split("/")[-1]] = len(keep)
        del g, bin_

    new_nodes = [root, {"name": f"layer:{layer}", "children": list(range(2, 2 + len(leaves)))}] + leaves
    root["children"] = [1]
    g = {"asset": {"version": "2.0", "generator": "extract_layer.py"}, "scene": 0, "scenes": [{"nodes": [0]}],
         "nodes": new_nodes, "meshes": mesh_list, "accessors": acc_list, "bufferViews": bv_list,
         "materials": mat_list, "buffers": [{"byteLength": len(out)}],
         "extensionsUsed": ["KHR_draco_mesh_compression", "KHR_texture_transform"],
         "extensionsRequired": ["KHR_draco_mesh_compression"]}
    write_glb(g, out, out_glb)

    # identity sidecar
    total = Counter(e["category"] for e in meta.values() if e.get("category") in cats)
    got = Counter(meta[o]["category"] for o in per_owner)
    els = {}
    for o, lv_leaves in per_owner.items():
        e = meta[o]
        lv = e.get("level")
        if isinstance(lv, str) and lv.startswith('Level "'):
            lv = lv.split('"')[1]
        els[o] = {"name": e.get("name"), "category": e.get("category"), "level": lv,
                  "source_file": e.get("source_file"), "leaves": len(lv_leaves)}
        pr = props.get(o)
        if pr:
            for grp, key, field in PROPS:
                v = (pr.get(grp) or {}).get(key)
                if v not in (None, "", "0 VA", "0 W"):
                    els[o][field] = v
            if not lv:
                for grp, key in LEVEL_KEYS:
                    v = (pr.get(grp) or {}).get(key)
                    if isinstance(v, str) and v:
                        els[o]["level"] = v.split('"')[1] if v.startswith('Level "') else v
                        els[o]["levelFrom"] = f"{grp}/{key}"
                        break
    doc = {"_schema": "twin-elements-binding/2", "layer": layer, "model": out_glb.split("/")[-1],
           "_doc": f"Element tier '{layer}': glb node name (= owner dbId) -> identity. Cut from the APS master by scripts/extract_layer.py.",
           "survival": {c: {"total": total[c], "with_geometry": got.get(c, 0)} for c in cats},
           "elements": els}
    json.dump(doc, open(out_json, "w"), indent=1)
    print(f"{layer}: {len(els)} elements / {len(leaves)} leaves / {len(mesh_list)} meshes / "
          f"{len(mat_list)} materials / {len(out) / 1e6:.1f} MB bin; per source {src_count}; survival "
          + ", ".join(f"{c} {got.get(c, 0)}/{total[c]}" for c in cats)
          + (f"; props on {sum(1 for v in els.values() if 'family' in v)}" if props else ""))


if __name__ == "__main__":
    main(*sys.argv[1:7])
