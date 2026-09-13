import sys,tempfile,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from package_gaussian import read_ply,write_ply,mobile_subset
class PackageTests(unittest.TestCase):
 def test_parameters_preserved(self):
  fields=['x','y','z','opacity']+[f'{k}_{i}'for k,n in [('rot',4),('scale',3),('f_dc',3),('f_rest',24)]for i in range(n)]
  a=np.zeros(100,dtype=[(k,'<f4')for k in fields]);a['x']=np.arange(100)*.2;a['rot_0']=1;a['opacity']=2;a['scale_0']=-3
  b=mobile_subset(a,20);self.assertEqual(len(b),20);self.assertNotIn('f_rest_0',b.dtype.names);self.assertTrue(np.isin(b['x'],a['x']).all());np.testing.assert_array_equal(b['scale_0'],np.full(20,-3))
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'test.ply';write_ply(p,b);c=read_ply(p);np.testing.assert_array_equal(b,c);p.write_bytes(p.read_bytes()[:-4])
   with self.assertRaises(ValueError):read_ply(p)
if __name__=='__main__':unittest.main()
