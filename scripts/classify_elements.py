#!/usr/bin/env python3
"""
classify_elements.py — enrich buildings/grimes/elements.json (element tier).

Adds, per element:
  type        human taxonomy derived from the Revit family name
  system      one of the 8 viewer systems (SYSTEMS[] in grimes-bim-viewer.html)
  levelKey    normalized level (LOWER/MEZZ/L1/L2/L3/ROOF) from the Revit level
              name, or — when Revit carried none — from the element's elevation
              (5-NN vote among Revit-labelled elements; levelSource = "revit" | "geometry")
  elevation_m element centroid Y in the viewer frame (equipment GLB world Y + EQUIP_OFFSET.y)
  isFedBy     for electrical elements without an explicit feed, the feeder
              meters serving the element's level (feedSource = "level-inferred")

Idempotent: reads the current file, recomputes the derived fields, keeps the
original name/category/level/kind and any hand-set isFedBy.
"""
import json
import re
import struct
import sys

import numpy as np

GLB = "buildings/grimes/grimes-equipment.glb"
ELEMENTS = "buildings/grimes/elements.json"
EQUIP_OFFSET_Y = -97.16          # grimes-bim-viewer.html EQUIP_OFFSET
LEVEL_NAMES = {
    "LEVEL B1": "LOWER", "LOWER LEVEL": "LOWER", "LOWER LEVEL - LOWER": "LOWER",
    "B1 LEVEL - MEZZ": "MEZZ", "LEVEL 01": "L1", "LEVEL 02": "L2", "LEVEL 03": "L3", "ROOF": "ROOF",
}
# feeder meters by level (same table as the panelboard mapping / viewer LVL2METERS)
LEVEL_METERS = {
    "LOWER": ["bmo:meter:76:kw", "bmo:meter:77:kw"], "MEZZ": ["bmo:meter:76:kw", "bmo:meter:77:kw"],
    "L1": ["bmo:meter:76:kw", "bmo:meter:77:kw"], "L2": ["bmo:meter:77:kw"], "L3": ["bmo:meter:77:kw"],
    "ROOF": ["bmo:meter:3:kw"],
}

# (regex on family name, type, system)  — first match wins
RULES = [
    (r"^RT_BX_Pull_Can", "Junction box", "Electrical"),
    (r"Panelboard", "Panelboard", "Electrical"),
    (r"Disconnect", "Disconnect switch", "Electrical"),
    (r"Transformer", "Transformer", "Electrical"),
    (r"Panel_TopHat", "Panel (top hat)", "Electrical"),
    (r"Ground_Bar", "Ground bar", "Electrical"),
    (r"^RT_EQ_Pad", "Equipment pad", "Electrical"),
    (r"^RT_EQ_Access_Panel", "Access panel", "Electrical"),
    (r"FIRE ALARM", "Fire alarm device", "Electrical"),
    (r"Air Grille & Access Panel", "Air grille / access panel", "HVAC Equipment"),
    (r"^Diffuser", "Diffuser", "Diffusers"),
    (r"^Grill", "Grille", "Diffusers"),
    (r"Fountain|Elkay_Drinking", "Drinking fountain", "Piping"),
    (r"^Sink|Lavatory|Counter", "Sink / lavatory", "Piping"),
    (r"^Toilet|EZOOTL|^ez|Combined EZ", "Water closet / carrier", "Piping"),
    (r"Shower|Handshower|Wall_Supply|Vacuum_Breaker|T342", "Shower fitting", "Piping"),
    (r"^Drain", "Floor drain", "Piping"),
]


def classify(name, category):
    for rx, typ, sys_ in RULES:
        if re.search(rx, name, re.I):
            return typ, sys_
    fallback = {"Electrical Equipment": ("Electrical equipment", "Electrical"),
                "Plumbing Fixtures": ("Plumbing fixture", "Piping"),
                "Air Terminals": ("Air terminal", "Diffusers"),
                "Mechanical Equipment": ("Mechanical equipment", "HVAC Equipment"),
                "Fire Alarm Devices": ("Fire alarm device", "Electrical")}
    return fallback.get(category, ("Element", "Electrical"))


def quat_m(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def centroids():
    """GLB-frame centroid (x,y,z) per element id, from node transforms + accessor bounds."""
    b = open(GLB, "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    g = json.loads(b[20:20 + jl])
    nodes, acc = g["nodes"], g["accessors"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}

    def local(n):
        M = np.eye(4)
        M[:3, :3] = quat_m(n.get("rotation", [0, 0, 0, 1])) @ np.diag(n.get("scale", [1, 1, 1]))
        M[:3, 3] = n.get("translation", [0, 0, 0])
        return M

    def world(i):
        M = local(nodes[i])
        p = parent.get(i)
        while p is not None:
            M = local(nodes[p]) @ M
            p = parent.get(p)
        return M

    ys = {}
    for i, n in enumerate(nodes):
        if not (n.get("name") and "mesh" in n):
            continue
        W = world(i)
        pts = []
        for p in g["meshes"][n["mesh"]]["primitives"]:
            a = acc[p["attributes"]["POSITION"]]
            for c in (a["min"], a["max"]):
                pts.append((W @ np.array(list(c) + [1.0]))[:3])
        ys.setdefault(n["name"], []).append(np.mean(pts, axis=0))
    return {k: np.mean(v, axis=0) for k, v in ys.items()}


def knn_level(c, labelled, k=5, y_weight=3.0):
    """Nearest-neighbour level vote among Revit-labelled elements. Elevation is
    weighted 3x so a ceiling-mounted L1 box is not captured by the L2 floor above
    it; XZ handles the partial mezzanine (a pure elevation band cannot)."""
    d = [((np.hypot(c[0] - p[0], c[2] - p[2]) ** 2 + (y_weight * (c[1] - p[1])) ** 2), lv) for p, lv in labelled]
    d.sort(key=lambda t: t[0])
    votes = {}
    for _, lv in d[:k]:
        votes[lv] = votes.get(lv, 0) + 1
    return max(votes.items(), key=lambda t: t[1])[0]


def main():
    doc = json.load(open(ELEMENTS))
    els = doc["elements"]
    cent = centroids()
    elev = {k: round(float(v[1]) + EQUIP_OFFSET_Y, 2) for k, v in cent.items()}
    labelled = [(cent[i], LEVEL_NAMES[e["level"]]) for i, e in els.items()
                if e.get("level") in LEVEL_NAMES and i in cent]
    # leave-one-out check of the inference against the Revit labels
    loo = sum(knn_level(c, [t for t in labelled if t[0] is not c]) == lv for c, lv in labelled)
    print(f"kNN level inference, leave-one-out vs Revit: {loo}/{len(labelled)} = {loo / len(labelled):.0%}")
    counts = {"type": {}, "system": {}, "levelKey": {}, "levelSource": {}, "feedSource": {}}
    for eid, e in els.items():
        typ, sys_ = classify(e.get("name", ""), e.get("category", ""))
        e["type"], e["system"] = typ, sys_
        if eid in elev:
            e["elevation_m"] = elev[eid]
        if e.get("level") in LEVEL_NAMES:
            e["levelKey"], e["levelSource"] = LEVEL_NAMES[e["level"]], "revit"
        elif eid in cent:
            e["levelKey"], e["levelSource"] = knn_level(cent[eid], labelled), "geometry"
        else:
            e.pop("levelKey", None); e.pop("levelSource", None)
        # feeds: keep explicit (panelboard) mapping; infer for other electrical elements by level
        if e.get("kind") == "panelboard" and e.get("isFedBy"):
            e["feedSource"] = "panel-schedule"
        elif sys_ == "Electrical" and e.get("levelKey") in LEVEL_METERS:
            e["isFedBy"], e["feedSource"] = LEVEL_METERS[e["levelKey"]], "level-inferred"
        else:
            if e.get("feedSource") == "level-inferred":
                e.pop("isFedBy", None)
            e.pop("feedSource", None)
        for k in counts:
            v = e.get(k)
            if v is not None:
                counts[k][v] = counts[k].get(v, 0) + 1
    doc["_schema"] = "twin-elements-binding/2"
    doc["_doc"] = (doc["_doc"].split(" Enriched")[0]
                   + " Enriched by scripts/classify_elements.py: type/system taxonomy from family names, "
                     "levelKey (revit name or geometry-inferred from elevation), level-inferred feeder meters for electrical elements.")
    doc["_taxonomy"] = {"types": counts["type"], "systems": counts["system"], "levels": counts["levelKey"],
                        "levelSource": counts["levelSource"], "feedSource": counts["feedSource"]}
    json.dump(doc, open(ELEMENTS, "w"), indent=1)
    for k, v in counts.items():
        print(k, dict(sorted(v.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    sys.exit(main())
