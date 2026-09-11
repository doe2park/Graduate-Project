"""Extract embedded E57 images and poses without decoding/reconstructing points.
Reads the E57 paged container and Blob headers described by libE57Format.
Raw export and metadata stay local until coordinate/projection validation.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from xml.etree import ElementTree as ET

class E57:
    def __init__(self,path):
        self.path=Path(path);self.file=self.path.open('rb')
        magic,major,minor,size,self.xml_offset,self.xml_length,self.page=struct.unpack('<8sIIQQQQ',self.file.read(48))
        if magic!=b'ASTM-E57' or major!=1 or self.page!=1024:raise ValueError('Unsupported E57 header')
        if size!=self.path.stat().st_size:raise ValueError('Incomplete E57 file')
        if self.xml_length>64*1024*1024 or self.xml_offset>=size:raise ValueError('Invalid XML bounds')
    def __del__(self):
        if hasattr(self,"file"):self.file.close()
    def read(self,offset,length):
        if offset<0 or length<0:raise ValueError('Negative byte range')
        out=bytearray()
        while length:
            within=offset%self.page
            if within>=self.page-4:offset+=self.page-within;continue
            count=min(length,self.page-4-within)
            self.file.seek(offset);chunk=self.file.read(count)
            if len(chunk)!=count:raise ValueError('Truncated E57 section')
            out.extend(chunk);offset+=count;length-=count
        return bytes(out)
    def xml(self):
        raw=self.read(self.xml_offset,self.xml_length)
        root=ET.fromstring(raw)
        for el in root.iter():el.tag=el.tag.split('}')[-1]
        return raw,root
    def blob(self,node):
        length=int(node.attrib['length']);offset=int(node.attrib['fileOffset'])
        if not 0<length<128*1024*1024:raise ValueError('Unexpected image size')
        raw=self.read(offset,length+16)
        if raw[0]!=0:raise ValueError('Not an E57 blob section')
        section_length=struct.unpack_from('<Q',raw,8)[0]
        if section_length<length+16:raise ValueError('Invalid E57 blob size')
        return raw[16:]

def node_value(node):
    if node is None:return None
    if len(node):return {c.tag:node_value(c) for c in node}
    value=(node.text or '').strip()
    if node.get('type')=='Float':return float(value or 0)
    if node.get('type')=='Integer':return int(value or 0)
    return value

def extract(source,out):
    from PIL import Image
    import io
    e=E57(source);raw,root=e.xml();out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'source.xml').write_bytes(raw)
    images=root.find('images2D');records=[]
    for index,node in enumerate([] if images is None else images):
        record={'index':index,'guid':node_value(node.find('guid')),'name':node_value(node.find('name')),'pose':node_value(node.find('pose')),'representations':[]}
        for kind in ['sphericalRepresentation','pinholeRepresentation','cylindricalRepresentation','visualReferenceRepresentation']:
            rep=node.find(kind)
            if rep is None:continue
            metadata={c.tag:node_value(c) for c in rep if c.get('type')!='Blob'}
            for image_type,extension in [('jpegImage','jpg'),('pngImage','png')]:
                blob=rep.find(image_type)
                if blob is None:continue
                data=e.blob(blob);im=Image.open(io.BytesIO(data));dimensions=list(im.size);im.verify()
                name=f'pano-{index:04d}-{kind}.{extension}';(out/name).write_bytes(data)
                record['representations'].append({'projection':kind,'file':name,'dimensions':dimensions,'sha256':hashlib.sha256(data).hexdigest(),**metadata})
        records.append(record)
    manifest={'source':str(Path(source).resolve()),'status':'extracted; registration and projection verification pending','images':records}
    (out/'images.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'source':str(source),'images':len(records),'poses':sum(r['pose'] is not None for r in records),'output':str(out)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('output');a=parser.parse_args();extract(a.source,a.output)
