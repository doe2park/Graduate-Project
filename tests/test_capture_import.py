import importlib.util,json,tempfile,unittest,math
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('capture_import',Path(__file__).resolve().parents[1]/'scripts/capture_import.py')
mod=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(mod)
class ImportTests(unittest.TestCase):
 def test_axes_and_no_inherited_height(self):
  self.assertEqual(mod.yup({'x':1,'y':2,'z':8}),[1,8,-2])
 def test_slug_rejects_escape(self):
  for value in ['../grimes','a/b','', 'a b']:
   with self.assertRaises(ValueError):mod.slug(value)
 def test_landmark_transform(self):
  def move(p):return [p[2]+10,p[1]+2,-p[0]-4]
  points=[[0,0,0],[4,0,0],[0,0,5],[2,1,2]]
  result=mod.fit_registration({'pairs':[{'scan':p,'bim':move(p)}for p in points[:3]],'checks':[{'scan':points[3],'bim':move(points[3])}]})
  self.assertAlmostEqual(result['rotationYDegrees'],90);self.assertLess(result['checkMaxMetres'],1e-8);self.assertEqual(result['status'],'provisional-landmarks')
 def test_collinear_and_missing_checks_rejected(self):
  for d in [{'pairs':[],'checks':[]},{'pairs':[{'scan':[i,0,0],'bim':[i,0,0]}for i in range(3)],'checks':[{'scan':[0,0,1],'bim':[0,0,1]}]}]:
   with self.assertRaises(ValueError):mod.fit_registration(d)
 def test_check_cannot_reuse_fit_point(self):
  pairs=[{'scan':p,'bim':p} for p in [[0,0,0],[4,0,0],[0,0,5]]]
  with self.assertRaises(ValueError):mod.fit_registration({'pairs':pairs,'checks':[pairs[0]]})
 def test_prepare_preserves_source_and_separates_building(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);src=root/'source';src.mkdir();Image.new('RGB',(64,32),'red').save(src/'image.jpg')
   import hashlib
   data=(src/'image.jpg').read_bytes();record={'guid':'pano_one','pose':{'translation':{'x':1,'y':2,'z':8},'rotation':{'x':0,'y':0,'z':0,'w':1}},'representations':[{'projection':'sphericalRepresentation','file':'image.jpg','pixelWidth':2*math.pi/64,'pixelHeight':math.pi/32,'sha256':hashlib.sha256(data).hexdigest()}]}
   (src/'images.json').write_text(json.dumps({'images':[record]}));out=root/'new'
   mod.prepare(src,out,'other-building','L2','2026-09-12')
   m=json.loads((out/'panoramas/manifest.json').read_text());p=json.loads((out/'project.json').read_text())
   self.assertEqual(m['stations'][0]['position'],[1,8,-2]);self.assertEqual((out/'panoramas/00000.jpg').read_bytes(),data)
   self.assertEqual(p['building'],'other-building');self.assertIsNone(p['registration']);self.assertEqual(p['dataStatus'],'NO FEED');self.assertEqual(m['stations'][0]['neighbors'],[])
   import struct
   malformed=root/'broken.glb';payload=b'{"asset":{"version":"2.0"}}';malformed.write_bytes(struct.pack('<4sIIII',b'glTF',2,20+len(payload),999996,0x4e4f534a)+payload)
   with self.assertRaises(ValueError):mod.prepare(src,root/'broken-out','other','L2','2026-09-12',malformed)
   self.assertFalse((root/'broken-out').exists())
   record['representations'][0]['pixelWidth']=math.pi/64;(src/'images.json').write_text(json.dumps({'images':[record]}))
   with self.assertRaises(ValueError):mod.prepare(src,root/'cropped-out','other','L2','2026-09-12')
   self.assertFalse((root/'cropped-out').exists())
   with self.assertRaises(FileExistsError):mod.prepare(src,out,'other-building','L2','2026-09-12')
if __name__=='__main__':unittest.main()
