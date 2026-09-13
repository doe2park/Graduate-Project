import sys,unittest,math
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_gaussian_dataset import face_rotation, camera_to_world, sphere_uv
class ProjectionTests(unittest.TestCase):
 def test_panorama_cardinal_directions(self):
  np.testing.assert_allclose(sphere_uv(np.array([[1.,0,0],[0,-1,0],[0,0,1]])),[[.5,.5],[.75,.5],[.5,0]],atol=1e-8)
 def test_pose_matches_existing_photo_forward(self):
  station={'position':[23.,6.,24.],'e57Quaternion':[0,0,math.sqrt(.5),math.sqrt(.5)]}
  c=camera_to_world(station,0,0);np.testing.assert_allclose(c[:3,3],station['position']);np.testing.assert_allclose(-c[:3,2],[0,0,-1],atol=1e-8);np.testing.assert_allclose(c[:3,0],[1,0,0],atol=1e-8)
 def test_all_faces_are_rigid(self):
  for yaw in [0,90,180,270]:
   for pitch in [-45,0,45]:
    r=face_rotation(yaw,pitch);np.testing.assert_allclose(r.T@r,np.eye(3),atol=1e-8);self.assertAlmostEqual(np.linalg.det(r),1)
if __name__=='__main__':unittest.main()
