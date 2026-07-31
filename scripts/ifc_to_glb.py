#!/usr/bin/env python3
"""
ifc_to_glb.py — element-identity-preserving IFC → GLB converter.

Replaces the retired APS pipeline for the Grimes twin. Every IFC product
becomes ONE glTF node whose name is its IFC GlobalId, so the viewer can pick
an individual element and resolve it through binding.json → Brick entity →
live data. A sidecar JSON maps GlobalId → {type, name, storey} for building
the element-tier binding without bloating the GLB.

Usage:
    python scripts/ifc_to_glb.py model.ifc out.glb
    python scripts/ifc_to_glb.py model.ifc out.glb --types IfcFlowSegment,IfcFlowTerminal
    python scripts/ifc_to_glb.py model.ifc out.glb --storey "Level 1" --exclude IfcSpace,IfcOpeningElement

Then compress (optional but recommended, keeps node names):
    npx @gltf-transform/cli optimize out.glb out-opt.glb \
        --compress draco --simplify false --palette false --join false --flatten false

Requires: pip install ifcopenshell trimesh numpy
"""
import argparse
import json
import sys
from collections import defaultdict

import numpy as np


def storey_of(element):
    """Walk containment/aggregation upward to the IfcBuildingStorey name."""
    import ifcopenshell.util.element as uel
    try:
        container = uel.get_container(element)
        while container is not None:
            if container.is_a("IfcBuildingStorey"):
                return container.Name or container.GlobalId
            container = uel.get_aggregate(container) or uel.get_container(container)
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ifc")
    ap.add_argument("glb")
    ap.add_argument("--types", help="comma list: only these IFC classes (e.g. IfcFlowSegment,IfcPump)")
    ap.add_argument("--exclude", default="IfcSpace,IfcOpeningElement,IfcSite",
                    help="comma list of IFC classes to skip (default: spaces/openings/site)")
    ap.add_argument("--storey", help="only elements contained in this storey name")
    ap.add_argument("--sidecar", help="metadata JSON path (default: <glb>.meta.json)")
    args = ap.parse_args()

    import ifcopenshell
    import ifcopenshell.geom
    import trimesh

    f = ifcopenshell.open(args.ifc)
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)  # bake placements; one node per element

    only = set(t.strip() for t in args.types.split(",")) if args.types else None
    skip = set(t.strip() for t in args.exclude.split(",") if t.strip())

    scene = trimesh.Scene()
    meta = {}
    counts = defaultdict(int)
    it = ifcopenshell.geom.iterator(settings, f, num_threads=4)
    if not it.initialize():
        sys.exit("No geometry found in IFC (is it a geometry-less export?)")

    while True:
        shape = it.get()
        el = f.by_id(shape.id)
        cls = el.is_a()
        keep = (only is None or any(el.is_a(t) for t in only)) and not any(el.is_a(t) for t in skip)
        if keep and args.storey:
            keep = storey_of(el) == args.storey
        if keep:
            g = shape.geometry
            verts = np.array(g.verts, dtype=np.float64).reshape(-1, 3)
            faces = np.array(g.faces, dtype=np.int64).reshape(-1, 3)
            if len(faces):
                mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
                # Per-element flat color from the first IFC style, if any
                try:
                    mats = g.materials
                    if mats:
                        c = mats[0]
                        rgba = [int(255 * x) for x in (c.diffuse.r(), c.diffuse.g(), c.diffuse.b())] + [
                            int(255 * (1.0 - c.transparency)) if c.has_transparency else 255]
                        mesh.visual.face_colors = rgba
                except Exception:
                    pass
                gid = el.GlobalId
                scene.add_geometry(mesh, node_name=gid, geom_name=gid)
                meta[gid] = {
                    "type": cls,
                    "name": el.Name or "",
                    "storey": storey_of(el),
                }
                counts[cls] += 1
        if not it.next():
            break

    if not meta:
        sys.exit("Nothing matched the filters — check --types/--storey values.")

    scene.export(args.glb)
    sidecar = args.sidecar or (args.glb + ".meta.json")
    with open(sidecar, "w") as out:
        json.dump({"_schema": "twin-elements/1", "_source": args.ifc.split("/")[-1],
                   "elements": meta}, out, indent=1)

    print(f"✓ {args.glb}: {len(meta)} elements")
    for cls, n in sorted(counts.items(), key=lambda kv: -kv[1])[:15]:
        print(f"   {cls:32s} {n}")
    print(f"✓ sidecar: {sidecar}")


if __name__ == "__main__":
    main()
