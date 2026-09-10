import json,struct,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def read(p):
 b=p.read_bytes();n=struct.unpack_from('<I',b,12)[0];return json.loads(b[20:20+n]),b[28+n:]
for name in ['level1-scan-2026-05-06','level1-scan-2026-05-06-part2']:
 s,b=read(root/f'scan-assets/{name}.glb');m,mb=read(root/f'scan-assets/mobile/{name}.glb')
 assert s['nodes']==m['nodes'] and s['meshes']==m['meshes'] and s['accessors']==m['accessors']
 images={x['bufferView'] for x in s['images']}
 for i,v in enumerate(s['bufferViews']):
  if i in images:continue
  w=m['bufferViews'][i]
  assert b[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]==mb[w.get('byteOffset',0):w.get('byteOffset',0)+w['byteLength']]
print('PASS mobile geometry bytes, nodes, accessors, transforms and mesh bindings preserved')
