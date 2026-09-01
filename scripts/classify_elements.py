#!/usr/bin/env python3
"""
classify_elements.py — enrich the element-tier identity files (buildings/grimes/*.elements.json).

    python3 scripts/classify_elements.py            # all layers
    python3 scripts/classify_elements.py lighting   # one layer

Layers share the APS master frame, so Revit-labelled elements from EVERY layer
form one pooled training set for the level inference.

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

LAYER_FILES = {   # layer -> (glb, identity json)
    "equipment":  ("buildings/grimes/grimes-equipment.glb",  "buildings/grimes/elements.json"),
    "lighting":   ("buildings/grimes/grimes-lighting.glb",   "buildings/grimes/lighting.elements.json"),
    "structural": ("buildings/grimes/grimes-structural.glb", "buildings/grimes/structural.elements.json"),
    "conduit":    ("buildings/grimes/grimes-conduit.glb",    "buildings/grimes/conduit.elements.json"),
    "fixtures":   ("buildings/grimes/grimes-fixtures.glb",   "buildings/grimes/fixtures.elements.json"),
    "lifesafety": ("buildings/grimes/grimes-lifesafety.glb", "buildings/grimes/lifesafety.elements.json"),
}
EQUIP_OFFSET_Y = -97.16          # grimes-bim-viewer.html EQUIP_OFFSET
LEVEL_NAMES = {
    "LEVEL B1": "LOWER", "LOWER LEVEL": "LOWER", "LOWER LEVEL - LOWER": "LOWER", "LEVEL B1 - LOWER": "LOWER",
    "LOWER LEVEL - KRESGE LANDING": "LOWER", "LEVEL 01 - LOWER": "LOWER",
    "B1 LEVEL - MEZZ": "MEZZ", "LEVEL B1 - MEZZ": "MEZZ",
    "LEVEL 01": "L1", "LEVEL 02": "L2", "LEVEL 02 - UPPER": "L2", "LEVEL 03": "L3", "CLERESTORY LEVEL": "L3",
    "ROOF": "ROOF", "ROOF LEVEL": "ROOF", "T/STEEL 09": "ROOF",
    # structural top-of-steel datums (framing Reference Level)
    "T/STEEL RF (N)": "ROOF", "T/STEEL 03 (N)": "L3", "T/STEEL 02 (N)": "L2", "T/STEEL 01 (N)": "L1", "T/STEEL LANDING": "MEZZ",
}
LEVEL_NAMES.update({k.title(): v for k, v in list(LEVEL_NAMES.items())})   # "Level 01" spellings from Revit Level elements
# feeder meters by level (same table as the panelboard mapping / viewer LVL2METERS)
LEVEL_METERS = {
    "LOWER": ["bmo:meter:76:kw", "bmo:meter:77:kw"], "MEZZ": ["bmo:meter:76:kw", "bmo:meter:77:kw"],
    "L1": ["bmo:meter:76:kw", "bmo:meter:77:kw"], "L2": ["bmo:meter:77:kw"], "L3": ["bmo:meter:77:kw"],
    "ROOF": ["bmo:meter:3:kw"],
}

# (regex on family name, type, system)  — first match wins
RULES = [
    # life safety
    (r"FIRE ALARM|Fire Alarm|Strobe|Horn|Pull Station|Smoke|Heat Detector", "Fire alarm device", "Life safety"),
    (r"Sprinkler", "Sprinkler", "Life safety"),
    (r"Exit Sign|EXIT", "Exit sign", "Life safety"),
    (r"Fire Extinguisher", "Fire extinguisher cabinet", "Life safety"),
    (r"Security|EMERGENCY CALL|Emergency Call", "Security / emergency call", "Life safety"),
    (r"Toilet Partition|Grab Bar|Dispenser|Mirror|Clothes_Hook|Baby Changing|Locker|Hook", "Restroom accessory", "Specialty"),
    (r"^RT_BX_Pull_Can", "Junction box", "Electrical"),
    (r"Panelboard", "Panelboard", "Electrical"),
    (r"Disconnect", "Disconnect switch", "Electrical"),
    (r"Transformer", "Transformer", "Electrical"),
    (r"Panel_TopHat", "Panel (top hat)", "Electrical"),
    (r"Ground_Bar", "Ground bar", "Electrical"),
    (r"^RT_EQ_Pad", "Equipment pad", "Electrical"),
    (r"^RT_EQ_Access_Panel", "Access panel", "Electrical"),
    (r"Air Grille & Access Panel", "Air grille / access panel", "HVAC Equipment"),
    (r"^Diffuser", "Diffuser", "Diffusers"),
    (r"^Grill", "Grille", "Diffusers"),
    (r"Fountain|Elkay_Drinking", "Drinking fountain", "Piping"),
    (r"^Sink|Lavatory|Counter", "Sink / lavatory", "Piping"),
    (r"^Toilet|EZOOTL|^ez|Combined EZ", "Water closet / carrier", "Piping"),
    (r"Shower|Handshower|Wall_Supply|Vacuum_Breaker|T342", "Shower fitting", "Piping"),
    (r"^Drain", "Floor drain", "Piping"),
    # lighting (277V lighting rides meter 76 by voltage class)
    (r"Exit Sign", "Exit sign", "Lighting"),
    (r"Pole Mounted|Post Fixture|Area Light|Groundwell|Terrace Floor|Column Light|Wall Mounted Light", "Exterior / site light", "Lighting"),
    (r"Downlight", "Downlight", "Lighting"),
    (r"Linear|Strip|LED Strip", "Linear fixture", "Lighting"),
    (r"Pendant|Globe", "Pendant", "Lighting"),
    (r"Track", "Track light", "Lighting"),
    (r"Wall Washer|Recessed Light", "Recessed fixture", "Lighting"),
    # structural
    (r"^SMA", "SMA brace device", "Structural"),
    (r"^Concrete.*Column|^REINF COLUMN", "Concrete column", "Structural"),
    (r"^HSS.*Column|^MC.*Column", "Steel column", "Structural"),
    (r"^Concrete.*Beam|^Beam|^BEAM|Tapaered|Thickened", "Concrete beam", "Structural"),
    (r"^W-Wide|^HSS|^MC-|^Round|^L-|^Plate|^Angle", "Steel framing", "Structural"),
    (r"^Pile", "Pile", "Structural"),
    (r"^Footing|^Foundation|^Wall Foundation|^Wall", "Foundation", "Structural"),
    (r"GUSSET|A325|^Structural Connection|Structural Connections", "Connection", "Structural"),
    # receptacles / devices (Electrical Fixtures) — prefab box families from the electrical contractor
    (r"Receptacle.*Quad|Quadruplex", "Receptacle (quad)", "Electrical"),
    (r"Receptacle|Duplex|GFCI|GFI", "Receptacle (duplex)", "Electrical"),
    (r"Orbit_|RT_PF_|RT_EF_|RT_ASM|eE_ASM|MC_Dot|Appleton|T5B|ZRT|Prefab|Pre-Fab|In-Wall|In_Wall", "Device box (prefab)", "Electrical"),
    (r"Wireless Access|WAP", "Wireless access point", "Electrical"),
    (r"Data|Telecom|Jack", "Data outlet", "Electrical"),
    (r"Speaker|Projector|Display|Screen|AV_|Audio|Camera", "AV / security device", "Electrical"),
    # conduit / cable tray
    (r"Cable Tray", "Cable tray", "Conduit"),
    (r"^Conduit", "Conduit run", "Conduit"),
    (r"Elbow|Coupling|Bend|Tee", "Conduit fitting", "Conduit"),
    (r"Floor_Box|_BX_", "Box", "Conduit"),
    (r"Rod|Hanger|Strut|Banger|SEISMIC|Clamp|_SU_|_HW_|_ST_", "Support / hanger", "Conduit"),
]
FEED_BY_SYSTEM = {"Lighting": (["bmo:meter:76:kw"], "voltage-class")}   # 277V lighting → meter 76 (fallback when no Revit voltage)
# Revit "Electrical Data" ("120 V/1-180 VA", "277 V/1-0 VA", "Primary 277 V/1-0 VA-Secondary ...") → feeder by voltage class:
#   120/208/220 V loads sit on the 208/120 V service (meter 77); 277/480 V on the 480/277 V service (meter 76).
ED_RX = re.compile(r"(\d{2,3})\s*V/(\d)-(\d+(?:\.\d+)?)\s*VA")


def parse_electrical_data(s):
    m = ED_RX.search(s or "")
    if not m:
        return None, None
    return int(m.group(1)), float(m.group(3))


def feed_by_voltage(volts):
    if volts is None:
        return None
    return ["bmo:meter:76:kw"] if volts >= 277 else ["bmo:meter:77:kw"]


def classify(name, category):
    for rx, typ, sys_ in RULES:
        if re.search(rx, name, re.I):
            return typ, sys_
    fallback = {"Electrical Equipment": ("Electrical equipment", "Electrical"),
                "Plumbing Fixtures": ("Plumbing fixture", "Piping"),
                "Air Terminals": ("Air terminal", "Diffusers"),
                "Mechanical Equipment": ("Mechanical equipment", "HVAC Equipment"),
                "Fire Alarm Devices": ("Fire alarm device", "Electrical"),
                "Lighting Fixtures": ("Light fixture", "Lighting"), "Lighting Devices": ("Lighting control", "Lighting"),
                "Structural Framing": ("Framing", "Structural"), "Structural Columns": ("Column", "Structural"),
                "Structural Foundations": ("Foundation", "Structural"), "Structural Connections": ("Connection", "Structural"),
                "Conduits": ("Conduit", "Conduit"), "Conduit Fittings": ("Conduit fitting", "Conduit"),
                "Cable Trays": ("Cable tray", "Conduit"), "Cable Tray Fittings": ("Cable tray fitting", "Conduit"),
                "Electrical Fixtures": ("Electrical device", "Electrical"), "Data Devices": ("Data outlet", "Electrical"),
                "Audio Visual Devices": ("AV / security device", "Electrical"), "Security Devices": ("Security / emergency call", "Life safety"),
                "Fire Alarm Devices": ("Fire alarm device", "Life safety"), "Sprinklers": ("Sprinkler", "Life safety"),
                "Specialty Equipment": ("Specialty equipment", "Life safety")}
    return fallback.get(category, ("Element", "Electrical"))


def quat_m(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def centroids(glb):
    """GLB-frame centroid (x,y,z) per element id, from node transforms + accessor bounds."""
    b = open(glb, "rb").read()
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


class LevelKNN:
    """5-NN level vote among Revit-labelled elements (numpy, all layers pooled).
    Elevation is weighted 3x so a ceiling-mounted L1 box is not captured by the
    L2 floor above it; XZ handles the partial mezzanine (a pure elevation band
    cannot)."""
    def __init__(self, labelled, k=5, y_weight=3.0):
        self.P = np.array([c for c, _ in labelled], dtype=float)
        self.P[:, 1] *= y_weight
        self.L = np.array([lv for _, lv in labelled])
        self.k, self.yw = k, y_weight

    def predict(self, c, exclude=None):
        q = np.array(c, dtype=float); q[1] *= self.yw
        d = ((self.P - q) ** 2).sum(axis=1)
        if exclude is not None:
            d[exclude] = np.inf
        idx = np.argpartition(d, self.k)[:self.k]
        vals, cnt = np.unique(self.L[idx], return_counts=True)
        return vals[cnt.argmax()]

    def loo(self):
        return sum(self.predict(self.P[i] / [1, self.yw, 1], exclude=i) == self.L[i] for i in range(len(self.L)))


def enrich(layer, glb, path, knn, cent):
    doc = json.load(open(path))
    els = doc["elements"]
    elev = {k: round(float(v[1]) + EQUIP_OFFSET_Y, 2) for k, v in cent.items()}
    counts = {"type": {}, "system": {}, "levelKey": {}, "levelSource": {}, "feedSource": {}}
    for eid, e in els.items():
        typ, sys_ = classify(e.get("name", ""), e.get("category", ""))
        e["type"], e["system"] = typ, sys_
        if eid in elev:
            e["elevation_m"] = elev[eid]
        if e.get("level") in LEVEL_NAMES:
            e["levelKey"], e["levelSource"] = LEVEL_NAMES[e["level"]], "revit"
        elif eid in cent:
            e["levelKey"], e["levelSource"] = str(knn.predict(cent[eid])), "geometry"
        else:
            e.pop("levelKey", None); e.pop("levelSource", None)
        # design electrical data from Revit (receptacles, lighting): voltage + VA
        volts, va = parse_electrical_data(e.get("electrical_data"))
        if volts is not None:
            e["design_volts"] = volts
            if va:
                e["design_va"] = va
        # feeds: explicit (panel schedule) > Revit voltage class > system rule > level inference for electrical
        if e.get("kind") == "panelboard" and e.get("isFedBy"):
            e["feedSource"] = "panel-schedule"
        elif sys_ in ("Electrical", "Lighting") and feed_by_voltage(volts):
            e["isFedBy"], e["feedSource"] = feed_by_voltage(volts), "revit-voltage"
        elif sys_ in FEED_BY_SYSTEM:
            e["isFedBy"], e["feedSource"] = FEED_BY_SYSTEM[sys_]
        elif sys_ == "Electrical" and e.get("levelKey") in LEVEL_METERS:
            e["isFedBy"], e["feedSource"] = LEVEL_METERS[e["levelKey"]], "level-inferred"
        else:
            if e.get("feedSource") in ("level-inferred", "voltage-class", "revit-voltage"):
                e.pop("isFedBy", None)
            e.pop("feedSource", None)
        for k in counts:
            v = e.get(k)
            if v is not None:
                counts[k][v] = counts[k].get(v, 0) + 1
    doc["_schema"] = "twin-elements-binding/2"
    doc["layer"] = layer
    doc["_doc"] = (doc["_doc"].split(" Enriched")[0]
                   + " Enriched by scripts/classify_elements.py: type/system taxonomy from family names, "
                     "levelKey (revit name or 5-NN by position, pooled across layers), feeder meters by panel schedule / "
                     "voltage class / level (feedSource).")
    doc["_taxonomy"] = {"types": counts["type"], "systems": counts["system"], "levels": counts["levelKey"],
                        "levelSource": counts["levelSource"], "feedSource": counts["feedSource"]}
    json.dump(doc, open(path, "w"), indent=1)
    print(f"[{layer}] " + " | ".join(f"{k}: " + ", ".join(f"{a} {b}" for a, b in sorted(v.items(), key=lambda x: -x[1])[:8])
                                    for k, v in counts.items() if k != "type"))
    print(f"[{layer}] types: " + ", ".join(f"{a} {b}" for a, b in sorted(counts["type"].items(), key=lambda x: -x[1])))


def apportion(layers_done):
    """Modelled apportionment of a feeder meter across the elements it serves —
    NEVER a measurement; the viewer labels it 'modelled'. Two pools with a
    defensible design-side weight:
      meter 77 (208/120 V service) → every load with a Revit design VA on that
        service (receptacles, 120 V lighting), weight = design VA
      meter 3 (roof AHU electric)  → supply diffusers, weight = design CFM
    Meter 76 mixes 277 V lighting with the mechanical plant and carries no
    element-level design weight in the NWD → no apportionment (stated in UI)."""
    docs = {L: json.load(open(LAYER_FILES[L][1])) for L in layers_done}
    pools = {"77": [], "3": []}
    for L, d in docs.items():
        for eid, e in d["elements"].items():
            if e.get("feedSource") == "revit-voltage" and e.get("design_volts", 999) < 277 and e.get("design_va"):
                pools["77"].append((L, eid, e["design_va"]))
            if e.get("type") == "Diffuser" and e.get("system_classification") == "Supply Air" and e.get("flow"):
                m = re.match(r"([\d.]+)", e["flow"])
                if m:
                    pools["3"].append((L, eid, float(m.group(1))))
    basis = {"77": "design VA", "3": "design CFM"}
    for meter, rows in pools.items():
        tot = sum(w for _, _, w in rows)
        for L, eid, w in rows:
            docs[L]["elements"][eid]["apportion"] = {"meter": meter, "basis": basis[meter], "weight": w,
                                                    "share": round(w / tot, 6), "pool": len(rows)}
    for L, d in docs.items():
        n = sum(1 for e in d["elements"].values() if "apportion" in e)
        d["_apportion"] = {"elements": n, "pools": {m: {"basis": basis[m], "n": len(r), "total": round(sum(w for _, _, w in r))} for m, r in pools.items()}}
        json.dump(d, open(LAYER_FILES[L][1], "w"), indent=1)
    print("apportionment pools: " + ", ".join(f"meter {m}: {len(r)} elements, total {round(sum(w for _, _, w in r))} {basis[m]}" for m, r in pools.items()))


def main(argv):
    layers = [a for a in argv if a in LAYER_FILES] or list(LAYER_FILES)
    cents, labelled = {}, []
    for layer, (glb, path) in LAYER_FILES.items():
        try:
            els = json.load(open(path))["elements"]
            cents[layer] = centroids(glb)
        except FileNotFoundError:
            continue
        labelled += [(cents[layer][i], LEVEL_NAMES[e["level"]]) for i, e in els.items()
                     if e.get("level") in LEVEL_NAMES and i in cents[layer]]
    knn = LevelKNN(labelled)
    loo = knn.loo()
    print(f"pooled kNN level inference, leave-one-out vs Revit: {loo}/{len(labelled)} = {loo / len(labelled):.0%}")
    for layer in layers:
        if layer in cents:
            enrich(layer, *LAYER_FILES[layer], knn, cents[layer])
    apportion([L for L in LAYER_FILES if L in cents])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
