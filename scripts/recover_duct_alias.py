#!/usr/bin/env python3
"""Recover MD02 aliases from an existing archived GLB without re-encoding source geometry.
Outputs a new additive combined duct asset; never overwrites original source GLB/sidecar.
Input paths and metadata _source (which may contain a private URN) are not published.
"""
import argparse, copy, hashlib, json, sys
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_layer import read_glb, write_glb, subset_from_source
from extract_mep_layer import type_of, CATEGORY
from plan_mep_recovery import plan_layer
from verify_mep_recovery import hashes, counts
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ask_twin.index import element_boxes

ROOT=Path(__file__).resolve().parents[1]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def root_data(g): return {k:v for k,v in g['nodes'][g['scenes'][g.get('scene',0)]['nodes'][0]].items() if k!='children'}
def inventory(g):
    out=Counter()
    for n in g['nodes']:
        if 'mesh' not in n: continue
        out['nodes']+=1
        for p in g['meshes'][n['mesh']]['primitives']:
            num=g['accessors'][p.get('indices',p['attributes']['POSITION'])]['count']; mode=p.get('mode',4)
            if mode==4: out['triangles']+=num//3
            elif mode==1: out['segments']+=num//2
            elif mode in (2,3): out['segments']+=max(0,num-1)+(mode==2 and num>1)
    return dict(out)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--metadata',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,default=ROOT/'buildings/grimes')
    a=ap.parse_args()
    base_path=ROOT/'buildings/grimes/grimes-duct.glb'
    side_path=ROOT/'buildings/grimes/duct.elements.json'
    base,bb=read_glb(base_path); source,sb=read_glb(a.source)
    assert root_data(base)==root_data(source),'Source frame differs'
    meta=json.loads(a.metadata.read_text())['elements']
    byext={e['externalId']:did for did,e in meta.items()}
    total,eligible,owners=plan_layer(meta,(r'^UCBBE-FMB-MD_.*-3D View - MD02 EXPORT\.dwg$',None),type_of)
    assert total and eligible,'No MD02 aliases in source metadata'
    old=json.loads(side_path.read_text())
    keep={i:owners[str(n['name'])] for i,n in enumerate(source['nodes']) if 'mesh' in n and str(n.get('name')) in owners}
    recovered=set(keep.values())
    assert not recovered.intersection(old['elements']),'Recovery would duplicate an existing identity'
    assert recovered,'No usable MD02 geometry'
    # Copy both existing and recovered bufferViews byte-verbatim into NEW output.
    out,acc,bv,mesh,mat=bytearray(),[],[],[],[]
    old_keep={i:str(n['name']) for i,n in enumerate(base['nodes']) if 'mesh' in n}
    leaves=subset_from_source(base,bb,old_keep,out,acc,bv,mesh,mat)
    leaves+=subset_from_source(source,sb,keep,out,acc,bv,mesh,mat)
    root=root_data(base);root['children']=list(range(1,1+len(leaves)))
    g={'asset':{'version':'2.0','generator':'recover_duct_alias.py (byte-preserving additive recovery)'},
       'scene':0,'scenes':[{'nodes':[0]}],'nodes':[root]+leaves,'meshes':mesh,'accessors':acc,
       'bufferViews':bv,'materials':mat,'buffers':[{'byteLength':len(out)}],
       'extensionsUsed':sorted(set(base.get('extensionsUsed',[]))|set(source.get('extensionsUsed',[]))),
       'extensionsRequired':sorted(set(base.get('extensionsRequired',[]))|set(source.get('extensionsRequired',[])))}
    # No retained geometry uses GPU instancing extensions: every selected node has its own source matrix.
    g['extensionsUsed']=[x for x in g['extensionsUsed'] if x!='EXT_mesh_gpu_instancing']
    g['extensionsRequired']=[x for x in g['extensionsRequired'] if x!='EXT_mesh_gpu_instancing']
    for i in keep: assert not source['nodes'][i].get('extensions'), 'Selected source leaf needs extension-aware copying'
    # Compare every recovered owner's ORIGINAL hierarchy-space bounds and primitive counts.
    chosen=copy.deepcopy(source)
    for i,n in enumerate(chosen['nodes']):
        if i in keep:n['name']=keep[i]
        elif 'mesh' in n:del n['mesh']
    all_ids=set(old['elements'])|recovered
    combined_counts=counts(g)
    source_counts=counts(chosen)
    assert all(combined_counts[k]==source_counts[k] for k in recovered),'Recovery changed primitives'
    before_counts=counts(base)
    assert all(combined_counts[k]==before_counts[k] for k in before_counts),'Existing primitives changed'
    boxes=element_boxes(g,all_ids)
    baseline_boxes=element_boxes(base,set(old['elements']))
    recovery_boxes=element_boxes(chosen,recovered)
    max_error=max(abs(x-y) for k,v in {**baseline_boxes,**recovery_boxes}.items() for x,y in zip(v,boxes[k]))
    assert max_error<1e-9, f'Source transforms changed: {max_error}'
    assert not (hashes(g,out)-(hashes(base,bb)+hashes(source,sb))), 'Geometry bytes changed'
    new=copy.deepcopy(old); new['model']='grimes-duct-restored.glb'
    per_owner=Counter(keep.values())
    for k in sorted(recovered,key=int):
        e=meta[k]; parts=e['externalId'].split('/')
        cad=meta.get(byext.get('/'.join(parts[:2]),''),{}).get('name')
        new['elements'][k]={'name':e.get('name') or '', 'category':CATEGORY['duct'],
          'level':'LEVEL 02','levelKey':'L2','levelSource':'source-file-alias',
          'source_file':e['source_file'],'leaves':per_owner[k],'type':type_of(e.get('name') or '',cad),'system':cad,
          'recovery':'MD02 original-source geometry; archived export is partial, not field-verified'}
    s=new['survival'][CATEGORY['duct']]
    for key,value in [('total',len(total)),('eligible',len(eligible)),('excluded',len(total-eligible)),('with_geometry',len(recovered))]:s[key]+=value
    new['_doc']=old['_doc']+' Additive 2026-11-18 MD02 alias recovery from the archived master; existing identities preserved. See duct-recovery-provenance.json. Not a complete as-built survey.'
    assert set(combined_counts)==set(new['elements'])
    result={'schema':'duct-source-recovery/1','date':'2026-11-18',
       'sourceFileName':a.source.name,'sourceSHA256':sha(a.source),'metadataSHA256':sha(a.metadata),
       'baselineGeometrySHA256':sha(base_path),'baselineMetadataSHA256':sha(side_path),
       'alias':'UCBBE-FMB-MD_adammTJDRY-3D View - MD02 EXPORT.dwg',
       'cause':'Earlier classifier accepted only short MDxx.dwg names and excluded the long MD02 export alias.',
       'sourceOwners':len(total),'eligibleOwners':len(eligible),'excludedOwners':len(total-eligible),
       'recoveredOwners':len(recovered),'missingEligibleOwners':len(eligible-recovered),
       'missingEligibleIds':sorted(eligible-recovered,key=int),
       'status':'partial-original-source-recovery','physicalValidation':'not surveyed or field-verified',
       'checks':{'originalFilesUnmodified':True,'existingIdentitiesAndPrimitivesPreserved':True,
          'bufferViewsByteIdentical':True,'sourceBoundsMaxAbsErrorM':max_error,'newIdsDisjoint':True},
       'recoveredBoundsViewerM':[
           [min(b[i] for b in recovery_boxes.values()) for i in range(3)],
           [max(b[i] for b in recovery_boxes.values()) for i in range(3,6)]],
       'combinedInventory':inventory(g)}
    a.output_dir.mkdir(parents=True,exist_ok=True)
    op=a.output_dir/'grimes-duct-restored.glb';write_glb(g,out,op)
    sp=a.output_dir/'duct-restored.elements.json';sp.write_text(json.dumps(new,indent=1)+'\n')
    result['outputGeometrySHA256']=sha(op); result['outputMetadataSHA256']=sha(sp)
    result['outputBytes']=op.stat().st_size
    (a.output_dir/'duct-recovery-provenance.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='missingEligibleIds'},indent=2))
if __name__=='__main__':main()
