import hashlib,json,unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from verify_mep_recovery import read_glb
from verify_mep_recovery import hashes,counts
from scripts.ask_twin.index import element_boxes

class RecoveredDuct(unittest.TestCase):
    def test_existing_source_bytes_and_records_are_unchanged(self):
        p=json.loads((ROOT/'buildings/grimes/duct-recovery-provenance.json').read_text())
        for name,key in [('grimes-duct.glb','baselineGeometrySHA256'),('duct.elements.json','baselineMetadataSHA256')]:
            self.assertEqual(hashlib.sha256((ROOT/'buildings/grimes'/name).read_bytes()).hexdigest(),p[key])
        old=json.loads((ROOT/'buildings/grimes/duct.elements.json').read_text())['elements']
        new=json.loads((ROOT/'buildings/grimes/duct-restored.elements.json').read_text())['elements']
        self.assertTrue(all(new[k]==v for k,v in old.items()))
        self.assertEqual(len(set(new)-set(old)),2944)
        g,b=read_glb(ROOT/'buildings/grimes/grimes-duct.glb')
        r,rb=read_glb(ROOT/'buildings/grimes/grimes-duct-restored.glb')
        self.assertFalse(hashes(g,b)-hashes(r,rb))
        oldcounts,newcounts=counts(g),counts(r)
        self.assertTrue(all(newcounts[k]==v for k,v in oldcounts.items()))
        self.assertEqual(element_boxes(g,set(old)),element_boxes(r,set(old)))
    def test_partial_recovery_has_real_l2_bounds_and_no_full_coverage_claim(self):
        p=json.loads((ROOT/'buildings/grimes/duct-recovery-provenance.json').read_text())
        self.assertEqual((p['eligibleOwners'],p['recoveredOwners'],p['missingEligibleOwners']),(3439,2944,495))
        self.assertEqual(p['status'],'partial-original-source-recovery')
        self.assertEqual(p['checks']['sourceBoundsMaxAbsErrorM'],0)
        self.assertGreater(p['recoveredBoundsViewerM'][0][1],9)
        self.assertLess(p['recoveredBoundsViewerM'][1][1],14.5)
    def test_all_viewers_and_catalog_use_restored_source(self):
        for page in ['scan-xr.html','scan-bim.html','grimes-bim-viewer.html']:
            text=(ROOT/page).read_text()
            self.assertTrue("glb:'buildings/grimes/grimes-duct-restored.glb'" in text.replace(' ',''),page)
            self.assertIn('duct-restored.elements.json',text)
        c=json.loads((ROOT/'bim-explorer-assets/source-catalog.json').read_text())
        d=next(x for x in c['layers'] if x['key']=='duct')
        self.assertEqual(d['objects'],16704+2944)
        self.assertEqual(d['metadata'],'buildings/grimes/duct-restored.elements.json')
        self.assertEqual(d['parts'][0]['path'],'buildings/grimes/grimes-duct-restored.glb')
