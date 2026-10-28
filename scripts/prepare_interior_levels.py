#!/usr/bin/env python3
"""Per-floor interior context groups (furniture / enclosure / floors / ceilings) for scan-bim.html.

    python3 scripts/prepare_interior_levels.py [--source DIR] [--out interior] [--levels L1,L2,L3] [--check-only]

Generalises the Level 1 slicer (Grimes_360_Pilot/scripts/prepare-interior.py, 2026-09-10) to Level 2 and Level 3.
The rules are the same per source node (fragment):
  * furniture / casework belong to a floor by the centre of their bounding box: sliceY[0] <= centre < sliceY[1];
  * enclosure, floors and ceilings belong to every floor whose slice they overlap (hi >= sliceY[0] and lo < sliceY[1])
    and are clipped to sliceY at runtime, so a stair flight or a wall that crosses a slab shows on both floors.
Source design geometry, not surveyed as-built. Walls and curtain-wall mullions carry no Revit level in the source
sidecar (`level` null; furniture, floors, ceilings, stairs mostly do), so the floor is a geometric slice for every
category, as for L1; the Revit level is only reported as a cross-check (`revitLevelCheck`).

Geometry is never re-encoded: meshes / accessors / Draco bufferViews are copied byte-for-byte with
extract_layer.subset_from_source and every output Draco payload hash is asserted to equal the source payload set.
L1 is regenerated with the original slice and must reproduce the published interior/*-l1.* files byte-for-byte; this
script never overwrites them (it fails instead). The existing manifest fields (schema, scope, frame, sliceY,
sourceSurvival, groups = Level 1) are kept unchanged; per-floor data is added under `levels`.
"""
import argparse
import collections
import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from extract_layer import read_glb, write_glb, subset_from_source  # noqa: E402

DEFAULT_SOURCE = Path.home() / "Documents/Playground/Grimes_360_Pilot/interior"
GROUPS = {"furniture": ["Furniture", "Casework"], "enclosure": ["Walls", "Doors", "Curtain Wall Mullions"],
          "floors": ["Floors", "Stairs", "Railings"], "ceilings": ["Ceilings"]}
FRAME = {"rotationYDegrees": 180, "translation": [-35.28, -97.16, 28.60]}
# Viewer-frame heights (m). Slab tops are the modal Floors top per storey in the source (9.5 / 14.4; L1 legacy).
# L2/L3 slice = [slab top - 0.27, next slab top - 0.1] (0.27 m below the slab top as in L1's 4.3 vs 4.57);
# L3's top stops at 19.3 m, under the roof penthouse walls/floors (bottoms 19.5-22 m).
LEVELS = {
    "L1": {"label": "Level 1", "sliceY": [4.3, 10.3], "slabTopY": 4.57, "legacy": True},
    "L2": {"label": "Level 2", "sliceY": [9.23, 14.3], "slabTopY": 9.5},
    "L3": {"label": "Level 3", "sliceY": [14.13, 19.3], "slabTopY": 14.4},
}
HONESTY = "source design geometry, not surveyed as-built"


def revit_floor(name):
    """Revit level name -> L1/L2/L3/other (cross-check only; assignment is geometric)."""
    if not name:
        return None
    for k, prefix in (("L1", "LEVEL 01"), ("L2", "LEVEL 02"), ("L3", "LEVEL 03")):
        if name.startswith(prefix):
            return k
    return "other"


def matrix(n):
    if "matrix" in n:
        return np.array(n["matrix"]).reshape(4, 4, order="F")
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    s = n.get("scale", [1, 1, 1])
    m = np.eye(4)
    m[:3, :3] = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                          [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                          [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]) @ np.diag(s)
    m[:3, 3] = n.get("translation", [0, 0, 0])
    return m


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def draco_payloads(doc, bin_, meshes=None):
    out = set()
    for m in (meshes if meshes is not None else doc["meshes"]):
        for p in m["primitives"]:
            d = p.get("extensions", {}).get("KHR_draco_mesh_compression")
            if d:
                v = doc["bufferViews"][d["bufferView"]]
                s = v.get("byteOffset", 0)
                out.add(sha256(bin_[s:s + v["byteLength"]]))
    return out


def payload_set_digest(hashes):
    return sha256("\n".join(sorted(hashes)).encode())


def node_boxes(g):
    world = np.diag([-1, 1, -1, 1.0])
    world[:3, 3] = FRAME["translation"]
    world = world @ matrix(g["nodes"][0])
    boxes = {}
    for i, n in enumerate(g["nodes"]):
        if "mesh" not in n:
            continue
        pts = []
        for p in g["meshes"][n["mesh"]]["primitives"]:
            a = g["accessors"][p["attributes"]["POSITION"]]
            if "min" not in a:
                raise ValueError("Missing source bounds")
            pts.extend([(*q, 1) for q in itertools.product(*zip(a["min"], a["max"]))])
        v = np.array(pts) @ (world @ matrix(n)).T
        boxes[i] = (v[:, :3].min(axis=0), v[:, :3].max(axis=0))
    return boxes


def select(g, meta, boxes, key, cats, lo_y, hi_y):
    keep = {}
    for i, (lo, hi) in boxes.items():
        n = g["nodes"][i]
        if meta[n["name"]]["category"] not in cats:
            continue
        if key == "furniture":
            inside = lo_y <= (lo[1] + hi[1]) / 2 < hi_y
        else:
            inside = hi[1] >= lo_y and lo[1] < hi_y
        if inside:
            keep[i] = n["name"]
    return keep


def build_group(g, b, meta, keep, key, level):
    out = bytearray()
    acc, bv, meshes, mats = [], [], [], []
    leaves = subset_from_source(g, b, keep, out, acc, bv, meshes, mats)
    root = {k: v for k, v in g["nodes"][0].items() if k != "children"}
    root["children"] = list(range(1, len(leaves) + 1))
    gen = "prepare-interior.py byte-preserving subset"  # same generator string as the L1 files (byte reproduction)
    doc = {"asset": {"version": "2.0", "generator": gen}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [root] + leaves, "meshes": meshes, "accessors": acc, "bufferViews": bv, "materials": mats,
           "buffers": [{"byteLength": len(out)}], "extensionsUsed": g.get("extensionsUsed", []),
           "extensionsRequired": g.get("extensionsRequired", [])}
    ids = set(keep.values())
    # sorted for reproducible sidecars (the 2026-09-10 L1 sidecar used set order; compared by content below)
    els = {i: {**meta[i], "levelKey": level, "levelFrom": "geometry-slice", "type": key, "feedTier": "no-feed"}
           for i in sorted(ids, key=lambda x: (len(x), x))}
    src = set()
    for i in keep:
        for p in g["meshes"][g["nodes"][i]["mesh"]]["primitives"]:
            d = p.get("extensions", {}).get("KHR_draco_mesh_compression")
            if d:
                v = g["bufferViews"][d["bufferView"]]
                s = v.get("byteOffset", 0)
                src.add(sha256(b[s:s + v["byteLength"]]))
    outp = draco_payloads(doc, out, meshes)
    assert src == outp, f"{level} {key}: Draco payloads changed"
    assert set(n["name"] for n in leaves) == set(els)
    return doc, out, els, leaves, outp


def glb_bytes(doc, out, tmp):
    write_glb(doc, out, tmp)
    data = tmp.read_bytes()
    tmp.unlink()
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out", type=Path, default=REPO / "interior")
    ap.add_argument("--levels", default="L1,L2,L3")
    ap.add_argument("--check-only", action="store_true", help="build in memory, compare, write nothing")
    args = ap.parse_args()
    out_dir = args.out.resolve()
    src_glb, src_json = args.source / "source.glb", args.source / "source.elements.json"
    g, b = read_glb(src_glb)
    side = json.loads(src_json.read_text())
    meta = side["elements"]
    boxes = node_boxes(g)
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema"] == "grimes-interior/1" and manifest["sliceY"] == LEVELS["L1"]["sliceY"]
    manifest["levels"] = manifest.get("levels", {})
    manifest["provenance"] = {
        "label": HONESTY,
        "source": {"glb": "Grimes_360_Pilot/interior/source.glb", "glbSha256": sha256(src_glb.read_bytes()),
                   "elementsSha256": sha256(src_json.read_bytes()), "elements": len(meta)},
        "builder": "scripts/prepare_interior_levels.py (rules of Grimes_360_Pilot/scripts/prepare-interior.py)",
        "levelFrom": "geometry-slice: viewer-frame height slice (walls/mullions have no Revit level in the source; "
                     "revitLevelCheck compares the slice with the Revit level where one exists)",
        "assignment": {"furniture": "bounding-box centre in [sliceY0, sliceY1)",
                       "enclosure,floors,ceilings": "bounding box overlaps the slice; clipped to sliceY at runtime; "
                                                    "an element crossing a slab is listed on both floors"},
    }
    tmp = out_dir / ".prepare-interior-levels.tmp.glb"
    for level in [s.strip() for s in args.levels.split(",") if s.strip()]:
        spec = LEVELS[level]
        lo_y, hi_y = spec["sliceY"]
        suffix = level.lower()
        entry_level = {"label": spec["label"], "sliceY": spec["sliceY"], "slabTopY": spec["slabTopY"],
                       "scope": f"{spec['label']} geometric slice; {HONESTY}", "groups": {}}
        for key, cats in GROUPS.items():
            keep = select(g, meta, boxes, key, cats, lo_y, hi_y)
            doc, out, els, leaves, payloads = build_group(g, b, meta, keep, key, level)
            data = glb_bytes(doc, out, tmp)
            side_bytes = json.dumps({"elements": els}, indent=1).encode()
            glb_p, json_p = out_dir / f"{key}-{suffix}.glb", out_dir / f"{key}-{suffix}.elements.json"
            if spec.get("legacy"):
                # Level 1 is published: reproduce it, never rewrite it.
                if glb_p.read_bytes() != data or json.loads(json_p.read_bytes())["elements"] != els:
                    raise SystemExit(f"{level} {key}: regenerated content differs from published {glb_p.name}; not overwriting")
                side_bytes = json_p.read_bytes()
            elif not args.check_only:
                glb_p.write_bytes(data)
                json_p.write_bytes(side_bytes)
            entry = {"glb": f"interior/{glb_p.name}", "json": f"interior/{json_p.name}", "elements": len(els),
                     "fragments": len(leaves), "bytes": len(data),
                     "categories": dict(collections.Counter(e["category"] for e in els.values())),
                     "verifiedDracoPayloads": len(payloads), "glbSha256": sha256(data),
                     "jsonSha256": sha256(side_bytes), "dracoPayloadSetSha256": payload_set_digest(payloads)}
            revit = collections.Counter(revit_floor(e.get("level")) for e in els.values())
            entry["revitLevelCheck"] = {"sameFloor": revit.get(level, 0),
                                        "otherFloor": sum(v for k, v in revit.items() if k not in (level, None)),
                                        "noRevitLevel": revit.get(None, 0)}
            if spec.get("legacy"):
                legacy = manifest["groups"][key]
                for k in ("glb", "json", "elements", "fragments", "bytes", "categories", "verifiedDracoPayloads"):
                    assert legacy[k] == entry[k], (level, key, k, legacy[k], entry[k])
            entry_level["groups"][key] = entry
            print(level, key, {k: entry[k] for k in ("elements", "fragments", "bytes", "verifiedDracoPayloads")},
                  entry["categories"])
        if spec.get("legacy"):
            entry_level["note"] = ("Published 2026-09-10 slice, unchanged. Its 10.3 m top lies 0.8 m above the Level 2 "
                                   "slab, so it also holds Level 2 furniture whose centres are below 10.3 m (clipped at "
                                   "runtime) and the lower parts of Level 2 walls/railings.")
        manifest["levels"][level] = entry_level
    if not args.check_only:
        manifest_path.write_text(json.dumps(manifest, indent=2))
    print("manifest", "checked" if args.check_only else "written", manifest_path)


if __name__ == "__main__":
    main()
