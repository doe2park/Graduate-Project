"""Infer bounded navigation edges from archived capture-list adjacency.
Run after build_panorama_assets.py; inventory remains private.
"""
import argparse, json, math
from pathlib import Path
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('inventory', type=Path)
parser.add_argument('--manifest', type=Path, default=Path(__file__).resolve().parents[1]/'scan-assets/panoramas/manifest.json')
args = parser.parse_args()
m = json.loads(args.manifest.read_text())
raw = json.loads(args.inventory.read_text())['records']['GET_PANO_ALL_RESPONSE']['response']['panos']
positions = [[p['position'][0], p['position'][2]+4.572, -p['position'][1]] for p in raw]
stations = m['stations']
nearest = [min(range(len(stations)), key=lambda i: math.dist(p, stations[i]['position'])) for p in positions]
edges = [set() for _ in stations]
for k, (a, b) in enumerate(zip(nearest, nearest[1:])):
    pa, pb = stations[a]['position'], stations[b]['position']
    if a != b and math.dist(positions[k], positions[k+1]) <= 4 and math.dist(pa, pb) <= 5.5 and abs(pa[1]-pb[1]) < 1.5:
        edges[a].add(b)
        edges[b].add(a)
for s, neighbors in zip(stations, edges):
    s['neighbors'] = sorted(neighbors)
m['navigation'] = 'Inferred from consecutive archived capture positions mapped to exported stations; edges limited to 5.5 m. Not collision-certified or surveyed.'
args.manifest.write_text(json.dumps(m, indent=2)+'\n')
print('Built capture-derived route for', len(stations), 'stations')
