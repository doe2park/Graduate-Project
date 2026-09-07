#!/usr/bin/env python3
"""Share byte-identical raw geometry without removing or renaming any nodes.

For fresh, uncompressed glTF only. Buffer files stay in their original folder;
the output glTF must be written beside its source. Existing Draco GLBs must
never pass through this utility. SHA-256 keys include accessor and bufferView
metadata, so data layout, indices, normals, UVs, and topology stay intact.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def dedup_raw(document, buffers):
    g = copy.deepcopy(document)
    if 'KHR_draco_mesh_compression' in g.get('extensionsUsed', []):
        raise ValueError('Use only on fresh uncompressed glTF')
    def key(d):return json.dumps(d,sort_keys=True,separators=(',',':'))
    bvs=[];bvm={};seen={}
    for i,v in enumerate(g['bufferViews']):
     start=v.get('byteOffset',0);data=buffers[v.get('buffer',0)][start:start+v['byteLength']];meta={k:x for k,x in v.items() if k not in ['buffer','byteOffset']};k=(key(meta),hashlib.sha256(data).digest())
     if k not in seen:seen[k]=len(bvs);bvs.append(v)
     bvm[i]=seen[k]
    accessors=[];am={};seen={}
    for i,a in enumerate(g['accessors']):
     a=dict(a)
     if 'bufferView'in a:a['bufferView']=bvm[a['bufferView']]
     if 'sparse'in a:raise ValueError('Sparse raw accessors not supported')
     k=key(a)
     if k not in seen:seen[k]=len(accessors);accessors.append(a)
     am[i]=seen[k]
    meshes=[];mm={};seen={}
    for i,m in enumerate(g['meshes']):
     for prim in m['primitives']:
      prim['attributes']={k:am[v]for k,v in prim['attributes'].items()}
      if 'indices'in prim:prim['indices']=am[prim['indices']]
      if 'targets'in prim:raise ValueError('Morph targets not supported')
     k=key(m)
     if k not in seen:seen[k]=len(meshes);meshes.append(m)
     mm[i]=seen[k]
    for n in g['nodes']:
     if 'mesh'in n:n['mesh']=mm[n['mesh']]
    g['bufferViews']=bvs;g['accessors']=accessors;g['meshes']=meshes
    return g


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    if args.source.resolve().parent != args.output.resolve().parent:
        raise ValueError('Output must be beside source to preserve external buffer paths')
    doc = json.loads(args.source.read_text())
    buffers = [(args.source.parent / b['uri']).read_bytes() for b in doc['buffers']]
    out = dedup_raw(doc, buffers)
    args.output.write_text(json.dumps(out, separators=(',', ':')))
    print(json.dumps({'nodes': len(out['nodes']), 'original_meshes': len(doc['meshes']),
                      'meshes': len(out['meshes']), 'original_accessors': len(doc['accessors']),
                      'accessors': len(out['accessors'])}))


if __name__ == '__main__':
    main()
