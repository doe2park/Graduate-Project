import json,sys,math,hashlib
from pathlib import Path
from collections import Counter,defaultdict
import struct
def read_glb(path):
 b=Path(path).read_bytes()
 if b[:4]!=b'glTF':raise ValueError('Invalid GLB header')
 jl=struct.unpack('<I',b[12:16])[0];g=json.loads(b[20:20+jl]);bl=struct.unpack('<I',b[20+jl:24+jl])[0]
 return g,b[28+jl:28+jl+bl]
def identity():return [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
def mat(n):
 if 'matrix'in n:return n['matrix']
 x,y,z,w=n.get('rotation',[0,0,0,1]);sx,sy,sz=n.get('scale',[1,1,1]);tx,ty,tz=n.get('translation',[0,0,0])
 return [(1-2*(y*y+z*z))*sx,2*(x*y+z*w)*sx,2*(x*z-y*w)*sx,0,2*(x*y-z*w)*sy,(1-2*(x*x+z*z))*sy,2*(y*z+x*w)*sy,0,2*(x*z+y*w)*sz,2*(y*z-x*w)*sz,(1-2*(x*x+y*y))*sz,0,tx,ty,tz,1]
def mul(a,b):return [sum(a[k*4+r]*b[c*4+k]for k in range(4))for c in range(4)for r in range(4)]
def bounds(g):
 lo=[math.inf]*3;hi=[-math.inf]*3
 def visit(idx,parent):
  n=g['nodes'][idx];m=mul(parent,mat(n))
  if 'mesh'in n:
   for p in g['meshes'][n['mesh']]['primitives']:
    a=g['accessors'][p['attributes']['POSITION']]
    if 'min'not in a:continue
    for x in [a['min'][0],a['max'][0]]:
     for y in [a['min'][1],a['max'][1]]:
      for z in [a['min'][2],a['max'][2]]:
       for j in range(3):
        v=m[j]*x+m[4+j]*y+m[8+j]*z+m[12+j];lo[j]=min(lo[j],v);hi[j]=max(hi[j],v)
  for c in n.get('children',[]):visit(c,m)
 for n in g['scenes'][g.get('scene',0)]['nodes']:visit(n,identity())
 return [lo,hi]
def counts(g,owners=None):
 out=defaultdict(Counter)
 for n in g['nodes']:
  if 'mesh'not in n:continue
  did=n['name'];did=owners[did]if owners else did
  out[did]['nodes']+=1
  for p in g['meshes'][n['mesh']]['primitives']:
   mode=p.get('mode',4);a=g['accessors'][p.get('indices',p['attributes']['POSITION'])];out[did][f'mode_{mode}_indices']+=a['count']
 return dict(out)
def hashes(g,b):return Counter(hashlib.sha256(b[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]).hexdigest()for v in g['bufferViews'])
def main():
 import argparse, importlib.util
 ap=argparse.ArgumentParser(description="Verify no-dedup MEP geometry packing and byte-verbatim subsetting.")
 for key in ['raw-gltf','packed','output','elements','baseline','owners','report']:
  ap.add_argument('--'+key,required=True,type=Path)
 args=ap.parse_args()
 raw=json.loads(args.raw_gltf.read_text());source,sb=read_glb(args.packed);new,nb=read_glb(args.output);old,_=read_glb(args.baseline);owner_map=json.loads(args.owners.read_text());els=json.loads(args.elements.read_text())['elements']
 rc=counts(raw,owner_map);sc=counts(source,owner_map);nc=counts(new)
 root=lambda g:{k:v for k,v in g['nodes'][g['scenes'][0]['nodes'][0]].items()if k!='children'}
 diff=[k for k in rc.keys()|sc.keys()|nc.keys()if rc.get(k)!=sc.get(k)or sc.get(k)!=nc.get(k)]
 rb=bounds(raw);nbounds=bounds(new);ob=bounds(old);err=max(abs(a-b)for va,vb in zip(rb,nbounds)for a,b in zip(va,vb));sh=hashes(source,sb);nh=hashes(new,nb)
 entry={'owners':len(nc),'mesh_nodes':sum(c['nodes']for c in nc.values()),'raw_to_final_primitive_count_mismatches':len(diff),'final_identity_matches_sidecar':set(nc)==set(els),'packed_root_exactly_matches_old':root(new)==root(old),'final_bufferViews_copied_byte_verbatim':not(nh-sh),'bufferViews':len(new['bufferViews']),'raw_bounds_m':rb,'final_bounds_m':nbounds,'old_bounds_m':ob,'raw_final_bounds_max_abs_error_m':err,'file_bytes':args.output.stat().st_size}
 args.report.write_text(json.dumps(entry,indent=2));print(json.dumps(entry,indent=2))
 success=not diff and entry['final_identity_matches_sidecar'] and entry['packed_root_exactly_matches_old'] and entry['final_bufferViews_copied_byte_verbatim'] and err<0.001
 if not success:raise SystemExit(1)
if __name__=='__main__':main()
