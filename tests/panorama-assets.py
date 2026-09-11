"""Validate published panorama identity, pose and image payloads."""
import hashlib,json,math,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'scan-assets/panoramas'
class PanoramaAssets(unittest.TestCase):
 def test_payloads_and_poses(self):
  m=json.loads((ROOT/'manifest.json').read_text());s=m['stations'];self.assertEqual(len(s),m['exportedStations']);self.assertEqual(len({p['id'] for p in s}),len(s));self.assertIn(m['defaultStation'],{p['id']for p in s})
  for p in s:
   with self.subTest(p['id']):
    self.assertTrue(all(math.isfinite(v)for v in p['position']+p['e57Quaternion']));self.assertAlmostEqual(sum(v*v for v in p['e57Quaternion']),1,places=10)
    original=ROOT/p['file'];self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),p['sha256']);self.assertTrue((ROOT/'mobile'/p['file']).is_file());self.assertEqual(p['dimensions'],[4096,2048])
 def test_route(self):
  s=json.loads((ROOT/'manifest.json').read_text())['stations'];seen={0};pending=[0]
  while pending:
   i=pending.pop()
   for j in s[i]['neighbors']:
    self.assertIn(i,s[j]['neighbors']);self.assertLessEqual(math.dist(s[i]['position'],s[j]['position']),5.5)
    if j not in seen:seen.add(j);pending.append(j)
  self.assertEqual(len(seen),len(s))
if __name__=='__main__':unittest.main()
