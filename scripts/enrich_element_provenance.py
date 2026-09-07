#!/usr/bin/env python3
"""Normalize CAD floor provenance and conservatively label legacy feeder mappings.
Does not infer circuits, rewrite GLBs or touch the machine-written data branch.
"""
import argparse,json,pathlib,re
CAD_LAYERS=('duct','hydronic','plumbing','fire')
def enrich(doc,layer):
 doc['model']='grimes-'+layer+'.glb'
 for e in doc['elements'].values():
  if layer in CAD_LAYERS:
   lv=str(e.get('level') or '').upper()
   m=re.fullmatch(r'LEVEL 0?([1-4])',lv)
   key='LOWER' if lv=='LOWER LEVEL' else 'ROOF' if lv=='ROOF' else 'L'+m[1] if m else None
   if key:
    e['levelKey']=key;e['levelSource']='source-file'
   else:
    e.pop('levelKey',None);e.pop('levelSource',None)
  if e.get('feedSource')=='panel-schedule' and not e.get('feedEvidence'):
   e['feedSource']='legacy-unverified'
   e['feedNote']='Legacy association; panel schedule evidence is not attached. Not verified circuit topology.'
 return doc

def enrich_properties(doc, properties):
 for eid,e in doc['elements'].items():
  groups=properties.get(eid,{}).get('properties',{})
  item=groups.get('Item',{}); revit=groups.get('Element',{}); attrs=groups.get('Attributes',{})
  if item.get('GUID'): e['source_guid']=item['GUID']
  handle=groups.get('Entity Handle',{}).get('Value')
  if handle: e['cad_handle']=handle
  if revit.get('Name'): e['element_tag']=revit['Name']
  fields={k:v for k,v in attrs.items() if k in ('Category','Sub Category','Description','Size','Length','Elevation','Manufacturer','General Category','CSI Code') and v not in (None,'','####')}
  if fields: e['fabrication']=fields
 return doc

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=pathlib.Path);p.add_argument('--properties',type=pathlib.Path);a=p.parse_args()
 props=json.loads(a.properties.read_text())['elements'] if a.properties else {}
 for layer in ('equipment','fixtures','lighting','lifesafety','structural','conduit')+CAD_LAYERS:
  f=a.directory/('elements.json' if layer=='equipment' else layer+'.elements.json')
  d=json.loads(f.read_text());enrich(d,layer);enrich_properties(d,props);f.write_text(json.dumps(d,indent=1)+'\n')
if __name__=='__main__':main()
