from pathlib import Path
import json,shutil,hashlib,math
from PIL import Image
import argparse
parser=argparse.ArgumentParser(description='Build Grimes panorama assets from extracted E57 images.json');parser.add_argument('extracted_directory');args=parser.parse_args()
repo=Path(__file__).resolve().parents[1];source=Path(args.extracted_directory)
out=repo/'scan-assets/panoramas';(out/'mobile').mkdir(parents=True,exist_ok=True)
images=json.load(open(source/'images.json'))['images'];stations=[]
for item in images:
 rep=next(r for r in item['representations'] if r['projection']=='sphericalRepresentation');id=item['guid'].removeprefix('pano_');name=id+'.jpg';src=source/rep['file'];shutil.copyfile(src,out/name)
 im=Image.open(src);im.resize((2048,1024),Image.Resampling.LANCZOS).save(out/'mobile'/name,quality=88)
 p=item['pose']['translation'];q=item['pose']['rotation'];stations.append({'id':id,'file':name,'position':[p['x'],p['z'],-p['y']],'e57Quaternion':[q['x'],q['y'],q['z'],q['w']],'sha256':rep['sha256'],'dimensions':rep['dimensions']})
manifest={'schema':'grimes-captured-panoramas/1','source':'Cupix E57 export with panoramas, 2026-09-11','captureDate':'2026-05-06','level':'L1','exportedStations':len(stations),'inventoryStations':217,'defaultStation':'83697765','frame':'E57 file coordinates, Z-up converted to Y-up by rotX(-90deg); same frame as exported scan GLB','projection':'E57 sphericalRepresentation; image center +X, camera +Z up','stations':stations}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
print('Prepared',len(stations),'original and mobile panoramas')
