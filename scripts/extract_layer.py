#!/usr/bin/env python3
"""
extract_layer.py — cut an element-tier web layer out of the APS master GLB.

    python3 scripts/extract_layer.py master.glb master.meta.json LAYER out.glb out.elements.json

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
    "equipment":  ["Electrical Equipment", "Mechanical Equipment", "Air Terminals", "Plumbing Fixtures", "Fire Alarm Devices"],
}
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


def main(master, metap, layer, out_glb, out_json):
    cats = LAYERS[layer]
    g, bin_ = read_glb(master)
    meta = json.load(open(metap))["elements"]
    owner = owners(meta)
    nodes = g["nodes"]

    # select leaves whose owner is in the layer's categories
    keep_leaf = {}            # node index -> owner id
    per_owner = defaultdict(list)
    for i, n in enumerate(nodes):
        nm = n.get("name")
        if not nm or "mesh" not in n or nm not in meta:
            continue
        o = owner(nm)
        if o and meta[o].get("category") in cats and not (
                layer in EXCLUDE and re.match(EXCLUDE[layer], meta[o].get("name") or "")):
            keep_leaf[i] = o
            per_owner[o].append(nm)

    # rebuild node list: root(transform) -> group -> leaves (renamed to owner)
    root = dict(nodes[g["scenes"][0]["nodes"][0]])
    group_idx = root["children"][0]
    new_nodes = [None, {"name": f"layer:{layer}", "children": []}]
    root["children"] = [1]
    new_nodes[0] = root
    for i, o in keep_leaf.items():
        n = {k: v for k, v in nodes[i].items() if k in ("translation", "rotation", "scale", "matrix", "mesh")}
        n["name"] = o
        new_nodes[1]["children"].append(len(new_nodes))
        new_nodes.append(n)
    g["nodes"] = new_nodes
    g["scenes"] = [{"nodes": [0]}]
    g["scene"] = 0

    # prune meshes -> accessors -> bufferViews -> materials, rebuild buffer
    used_mesh = sorted({n["mesh"] for n in new_nodes[2:]})
    mesh_remap = {o: i for i, o in enumerate(used_mesh)}
    g["meshes"] = [g["meshes"][i] for i in used_mesh]
    for n in new_nodes[2:]:
        n["mesh"] = mesh_remap[n["mesh"]]
    used_acc, used_mat = set(), set()
    for m in g["meshes"]:
        for p in m["primitives"]:
            used_acc.update(p["attributes"].values())
            if "indices" in p:
                used_acc.add(p["indices"])
            if "material" in p:
                used_mat.add(p["material"])
    acc_keep = sorted(used_acc)
    acc_remap = {o: i for i, o in enumerate(acc_keep)}
    g["accessors"] = [g["accessors"][i] for i in acc_keep]
    mat_keep = sorted(used_mat)
    mat_remap = {o: i for i, o in enumerate(mat_keep)}
    g["materials"] = [g["materials"][i] for i in mat_keep]
    for m in g["meshes"]:
        for p in m["primitives"]:
            p["attributes"] = {k: acc_remap[v] for k, v in p["attributes"].items()}
            if "indices" in p:
                p["indices"] = acc_remap[p["indices"]]
            if "material" in p:
                p["material"] = mat_remap[p["material"]]
    used_bv = set()
    for a in g["accessors"]:
        if "bufferView" in a:
            used_bv.add(a["bufferView"])
    for m in g["meshes"]:
        for p in m["primitives"]:
            d = p.get("extensions", {}).get("KHR_draco_mesh_compression")
            if d:
                used_bv.add(d["bufferView"])
    bv_keep = sorted(used_bv)
    bv_remap = {o: i for i, o in enumerate(bv_keep)}
    out = bytearray()
    new_bvs = []
    for i in bv_keep:
        bv = dict(g["bufferViews"][i])
        off = bv.get("byteOffset", 0)
        out += b"\0" * (-len(out) % 4)
        bv["byteOffset"] = len(out)
        out += bin_[off:off + bv["byteLength"]]
        new_bvs.append(bv)
    g["bufferViews"] = new_bvs
    for a in g["accessors"]:
        if "bufferView" in a:
            a["bufferView"] = bv_remap[a["bufferView"]]
    for m in g["meshes"]:
        for p in m["primitives"]:
            d = p.get("extensions", {}).get("KHR_draco_mesh_compression")
            if d:
                d["bufferView"] = bv_remap[d["bufferView"]]
    g["buffers"] = [{"byteLength": len(out)}]
    for k in ("extensionsUsed", "extensionsRequired"):
        if k in g:
            g[k] = [e for e in g[k] if e != "EXT_mesh_gpu_instancing"]
    for k in ("images", "textures", "samplers", "skins", "animations", "cameras"):
        g.pop(k, None)
    write_glb(g, out, out_glb)

    # identity sidecar
    total = Counter(e["category"] for e in meta.values() if e.get("category") in cats)
    got = Counter(meta[o]["category"] for o in per_owner)
    els = {}
    for o, leaves in per_owner.items():
        e = meta[o]
        lv = e.get("level")
        if isinstance(lv, str) and lv.startswith('Level "'):
            lv = lv.split('"')[1]
        els[o] = {"name": e.get("name"), "category": e.get("category"), "level": lv,
                  "source_file": e.get("source_file"), "leaves": len(leaves)}
    doc = {"_schema": "twin-elements-binding/2", "layer": layer, "model": out_glb.split("/")[-1],
           "_doc": f"Element tier '{layer}': glb node name (= owner dbId) -> identity. Cut from the APS master by scripts/extract_layer.py.",
           "survival": {c: {"total": total[c], "with_geometry": got.get(c, 0)} for c in cats},
           "elements": els}
    json.dump(doc, open(out_json, "w"), indent=1)
    print(f"{layer}: {len(els)} elements / {len(keep_leaf)} leaves / {len(g['meshes'])} meshes / "
          f"{len(g['materials'])} materials / {len(out) / 1e6:.1f} MB bin; survival "
          + ", ".join(f"{c} {got.get(c, 0)}/{total[c]}" for c in cats))


if __name__ == "__main__":
    main(*sys.argv[1:6])
