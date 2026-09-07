import importlib.util,unittest,pathlib
p=pathlib.Path(__file__).resolve().parents[1]/'scripts/enrich_element_provenance.py'
class Provenance(unittest.TestCase):
 def test_source_floor_and_legacy_feed(self):
  self.assertTrue(p.exists(),'provenance enrichment missing')
  spec=importlib.util.spec_from_file_location('enrich',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  doc={'elements':{'1':{'level':'LEVEL 02','type':'Pipe','source_file':'02FP.DWG'},'2':{'level':'unknown'}}}
  m.enrich(doc,'fire');self.assertEqual(doc['elements']['1']['levelKey'],'L2');self.assertEqual(doc['elements']['1']['levelSource'],'source-file');self.assertNotIn('levelKey',doc['elements']['2'])
  old={'elements':{'1':{'kind':'panelboard','isFedBy':['bmo:meter:76:kw'],'feedSource':'panel-schedule'}}}
  m.enrich(old,'equipment');self.assertEqual(old['elements']['1']['feedSource'],'legacy-unverified');self.assertEqual(old['elements']['1']['isFedBy'],['bmo:meter:76:kw'])
 def test_fabrication_values_keep_source_units(self):
  spec=importlib.util.spec_from_file_location('enrich',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  d={'elements':{'7':{}}};raw={'7':{'properties':{'Attributes':{'Size':'6 inch','Length':'37 feet','Manufacturer':'Generic','Detail Sheet Location':'####'},'Item':{'GUID':'abc'}}}}
  m.enrich_properties(d,raw)
  self.assertEqual(d['elements']['7']['fabrication']['Length'],'37 feet')
  self.assertNotIn('Detail Sheet Location',d['elements']['7']['fabrication'])
  self.assertEqual(d['elements']['7']['source_guid'],'abc')
if __name__=='__main__':unittest.main()
