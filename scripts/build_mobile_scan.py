"""Make texture-only mobile derivatives. Geometry bufferViews are copied verbatim.
Usage: python scripts/build_mobile_scan.py scan-assets (requires Pillow).
"""
import io,json,struct,sys,hashlib
from pathlib import Path
from PIL import Image
root=Path(sys.argv[1]);out=root/'mobile';out.mkdir(exist_ok=True)
records=[]
for name in ['level1-scan-2026-05-06','level1-scan-2026-05-06-part2']:
 src=root/(name+'.glb');raw=src.read_bytes();n=struct.unpack_from('<I',raw,12)[0];j=json.loads(raw[20:20+n]);binary=raw[28+n:];images={i['bufferView']:i for i in j['images']};buf=bytearray();pixels=0
 for i,v in enumerate(j['bufferViews']):
  chunk=binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
  if i in images:
   with Image.open(io.BytesIO(chunk)) as im:
    im.thumbnail((512,512),Image.Resampling.LANCZOS);pixels+=im.width*im.height
    dest=io.BytesIO();im.save(dest,format='PNG',optimize=True);chunk=dest.getvalue();images[i]['mimeType']='image/png'
  while len(buf)%4:buf.append(0)
  v['byteOffset']=len(buf);v['byteLength']=len(chunk);buf.extend(chunk)
 while len(buf)%4:buf.append(0)
 j['buffers'][0]['byteLength']=len(buf);js=json.dumps(j,separators=(',',':')).encode();js+=b' '*(-len(js)%4)
 result=struct.pack('<III',0x46546c67,2,28+len(js)+len(buf))+struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(buf),0x004e4942)+buf
 target=out/(name+'.glb');target.write_bytes(result)
 records.append({'source':src.name,'source_sha256':hashlib.sha256(raw).hexdigest(),'output':target.name,'output_sha256':hashlib.sha256(result).hexdigest(),'bytes':len(result),'texturePixels':pixels,'rgbaWithMipmapsBytes':round(pixels*4*4/3)})
(out/'provenance.json').write_text(json.dumps({'method':'Texture-only mobile derivative, maximum edge 512px. Every non-image bufferView, node, mesh, accessor and coordinate preserved. Original GLBs unchanged.','assets':records},indent=2)+'\n')
print(json.dumps(records,indent=2))
