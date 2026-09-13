"""Local intake for a new building/floor/capture. Never uploads or edits data branch."""
import argparse, datetime, hashlib, json, math, re, shutil, struct, tempfile
from pathlib import Path


def slug(value):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
        raise ValueError('Use letters, digits, dash or underscore for building and level IDs')
    return value


def vector(values, n):
    if len(values) != n or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values):
        raise ValueError('Invalid finite coordinate/quaternion')
    return list(values)


def yup(p):
    return vector([p['x'], p['z'], -p['y']], 3)


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2)+'\n')


def fit_registration(data):
    """Metric Y-up, yaw-only rigid fit; checks excluded from fitting."""
    pairs, checks = data.get('pairs', []), data.get('checks', [])
    if len(pairs) < 3 or not checks:
        raise ValueError('Need 3+ non-collinear fit pairs and 1+ independent check pair')
    for pair in pairs+checks:
        vector(pair['scan'], 3); vector(pair['bim'], 3)
    for check in checks:
        if any(check['scan'] == pair['scan'] or check['bim'] == pair['bim'] for pair in pairs):
            raise ValueError('Independent checks must not reuse fit landmarks')
    for key in ['scan', 'bim']:
        pts = [p[key] for p in pairs]
        center = [sum(p[k] for p in pts)/len(pts) for k in range(3)]
        xx = sum((p[0]-center[0])**2 for p in pts)
        zz = sum((p[2]-center[2])**2 for p in pts)
        xz = sum((p[0]-center[0])*(p[2]-center[2]) for p in pts)
        if xx*zz-xz*xz < 1e-6 * max(1, (xx+zz)**2):
            raise ValueError('Landmarks must span a 2D area, not a line')
    a = [sum(p['scan'][k] for p in pairs)/len(pairs) for k in range(3)]
    b = [sum(p['bim'][k] for p in pairs)/len(pairs) for k in range(3)]
    c = sum((p['scan'][0]-a[0])*(p['bim'][0]-b[0])+(p['scan'][2]-a[2])*(p['bim'][2]-b[2]) for p in pairs)
    s = sum((p['scan'][2]-a[2])*(p['bim'][0]-b[0])-(p['scan'][0]-a[0])*(p['bim'][2]-b[2]) for p in pairs)
    yaw = math.atan2(s, c); cs, sn = math.cos(yaw), math.sin(yaw)
    def rotate(p):return [cs*p[0]+sn*p[2], p[1], -sn*p[0]+cs*p[2]]
    t = [b[k]-rotate(a)[k] for k in range(3)]
    def residual(p):return math.dist([v+t[k] for k,v in enumerate(rotate(p['scan']))], p['bim'])
    errors = [residual(p) for p in pairs]; held = [residual(p) for p in checks]
    return {'status':'provisional-landmarks', 'rotationYDegrees':math.degrees(yaw), 'translation':t, 'scale':1,
            'fitRmsMetres':math.sqrt(sum(e*e for e in errors)/len(errors)), 'fitMaxMetres':max(errors),
            'checkMaxMetres':max(held), 'checkErrorsMetres':held, 'fitPairs':len(pairs), 'checkPairs':len(checks),
            'scope':'Y-up metres; visualization candidate, not surveyed accuracy. Review independent checks and image orientation before use.'}


def prepare(source, output, building, level, date, model=None, route=None):
    from PIL import Image
    source, output = Path(source).resolve(), Path(output).absolute()
    slug(building); slug(level); datetime.date.fromisoformat(date)
    if output.exists():raise FileExistsError('Choose a new capture folder; existing captures are never overwritten')
    if output == source or source in output.parents:raise ValueError('Output must be outside source folder')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.capture-', dir=output.parent) as work:
        stage = Path(work)/'package'; stage.mkdir()
        raw = source
        if source.suffix.lower() == '.e57':
            from extract_e57_images import extract
            raw = Path(work)/'extracted'; extract(source, raw)
        images_file = raw/'images.json'
        if not images_file.is_file():
            raise ValueError('Provide an E57 with spherical images and poses, or an extracted images.json folder. INSV/NWD/IFC alone need preprocessing; no coordinates are invented.')
        images = json.loads(images_file.read_text())['images']; stations = []; skipped = []; ids = set()
        photos = stage/'panoramas'; (photos/'mobile').mkdir(parents=True)
        for item in images:
            reps = [r for r in item.get('representations', []) if r.get('projection') == 'sphericalRepresentation']
            if not reps or not item.get('pose'):
                skipped.append({'id':item.get('guid'), 'reason':'Missing spherical image or pose'});continue
            ident = str(item.get('guid') or '')
            if not ident or ident in ids:raise ValueError('Missing or duplicate image GUID')
            ids.add(ident); rep = reps[0]; src = (raw/rep['file']).resolve()
            if raw.resolve() not in src.parents:raise ValueError('Image path escapes source directory')
            sha = digest(src)
            if rep.get('sha256') and rep['sha256'] != sha:raise ValueError('Image hash mismatch')
            pose = item['pose']; position = yup(pose['translation']); q = vector([pose['rotation'][k] for k in ['x','y','z','w']],4)
            if abs(sum(v*v for v in q)-1) > 1e-4:raise ValueError('Image rotation must be a unit quaternion')
            with Image.open(src) as im:
                if im.format not in ['JPEG','PNG'] or im.width != 2*im.height:raise ValueError('Only full 2:1 spherical JPEG/PNG images supported')
                if not math.isclose(float(rep.get('pixelWidth', 0))*im.width, 2*math.pi, abs_tol=1e-3) or not math.isclose(float(rep.get('pixelHeight', 0))*im.height, math.pi, abs_tol=1e-3):raise ValueError('Spherical angular metadata must cover full 360 by 180 degrees')
                if rep.get('imageWidth',im.width)!=im.width or rep.get('imageHeight',im.height)!=im.height:raise ValueError('E57 image dimensions disagree with payload')
                name = f'{len(stations):05d}'+('.jpg' if im.format == 'JPEG' else '.png')
                dimensions = list(im.size); shutil.copyfile(src, photos/name)
                size = (min(2048, im.width), min(1024, im.height))
                small = im.convert('RGB').resize(size, Image.Resampling.LANCZOS)
                small.save(photos/'mobile'/name, **({'quality':88} if name.endswith('.jpg') else {}))
            stations.append({'id':ident, 'file':name, 'position':position, 'e57Quaternion':q, 'dimensions':dimensions, 'sha256':sha, 'neighbors':[]})
        if not stations:raise ValueError('No usable spherical images with poses; a point-cloud-only E57 cannot provide the photo Walk mode')
        if route:
            edges = json.loads(Path(route).read_text())['edges']; lookup = {s['id']:i for i,s in enumerate(stations)}
            for left, right in edges:
                if left not in lookup or right not in lookup:raise ValueError('Route references unknown image GUID')
                a,b = lookup[left],lookup[right];pa,pb = stations[a]['position'],stations[b]['position']
                if a == b or math.dist(pa,pb)>5.5 or abs(pa[1]-pb[1])>1.5:raise ValueError('Route exceeds Walk distance/height bounds; use denser captures')
                for x,y in [(a,b),(b,a)]:
                    if y not in stations[x]['neighbors']:stations[x]['neighbors'].append(y)
        write_json(photos/'manifest.json', {'schema':'grimes-captured-panoramas/1','building':building,'level':level,'captureDate':date,
            'exportedStations':len(stations),'defaultStation':stations[0]['id'],'frame':'E57 Z-up metres to Y-up: [x,z,-y]. No building elevation offset added.',
            'navigation':'Explicit route edges only; no nearest-neighbor links guessed through walls. Capture picker works without route.', 'stations':stations})
        model_entry = None
        if model:
            model = Path(model).resolve()
            with model.open('rb') as f:
                header = f.read(12)
                if len(header)!=12 or struct.unpack('<4sII',header) != (b'glTF',2,model.stat().st_size):raise ValueError('Model must be a valid GLB v2 container; convert NWD/IFC first')
                size,kind = struct.unpack('<II',f.read(8))
                if kind!=0x4e4f534a or size>64*1024*1024 or size%4 or size>model.stat().st_size-20:raise ValueError('Invalid GLB JSON chunk')
                gltf=json.loads(f.read(size))
                while f.tell()<model.stat().st_size:
                    chunk=f.read(8)
                    if len(chunk)!=8:raise ValueError('Truncated GLB chunk header')
                    chunk_size,_=struct.unpack('<II',chunk)
                    if chunk_size%4 or chunk_size>model.stat().st_size-f.tell():raise ValueError('Truncated GLB chunk payload')
                    f.seek(chunk_size,1)
                if any(v.get('uri') and not v['uri'].startswith('data:') for k in ['buffers','images'] for v in gltf.get(k,[])):
                    raise ValueError('Use self-contained GLB; external assets would be missing')
            shutil.copyfile(model,stage/'model.glb')
            model_entry={'file':'model.glb','sha256':digest(model),'nodeCount':len(gltf.get('nodes',[])),'frame':'Y-up metres required; verify before registration','identity':'Copied byte-for-byte; no node renaming/recompression; data binding not yet configured'}
        project={'schema':'capture-project/1','building':building,'level':level,'captureDate':date,'panoramas':'panoramas/manifest.json',
                 'model':model_entry,'registration':None,'dataStatus':'NO FEED','status':'intake-review','routeReady':bool(route),
                 'notes':['Review units, floor, image orientation and route before integration.', 'No sensor feeds or registration inherited from Grimes.']}
        write_json(stage/'project.json',project)
        write_json(stage/'landmarks.template.json',{'frame':'Both scan and BIM: Y-up metres; 3+ non-collinear pairs and separate check landmarks. Fill real coordinates only.','pairs':[],'checks':[]})
        write_json(stage/'route.template.json',{'instructions':'Connect known walkable capture GUID pairs; max 5.5 m, vertical step <=1.5 m. Never infer adjacency from filenames.','edges':[]})
        write_json(stage/'intake-report.json',{'imagesImported':len(stations),'imagesSkipped':skipped,'sourceName':source.name,'sourceHash':digest(source if source.is_file() else images_file),'rawVideoRecovered':False,'model':model_entry,'registrationStatus':'pending','routeStatus':'provided; field check needed' if route else 'pending; use capture picker'})
        (stage/'README.txt').write_text('Local review package. Serve the repository and open capture-review.html?project=<relative package path>/project.json. No upload performed. Keep original video and exports separately. See docs/CAPTURE_ONBOARDING.md.\n')
        stage.rename(output)
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('prepare');a.add_argument('--source',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    for key in ['building','level','date']:a.add_argument('--'+key,required=True)
    a.add_argument('--model',type=Path);a.add_argument('--route',type=Path)
    b=sub.add_parser('fit');b.add_argument('landmarks',type=Path);b.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.command=='prepare':
            out=prepare(args.source,args.output,args.building,args.level,args.date,args.model,args.route);print('Prepared local review:',out/'project.json')
        else:
            if args.output.exists():raise FileExistsError('Choose a new candidate file')
            result=fit_registration(json.loads(args.landmarks.read_text()));write_json(args.output,result);print(json.dumps(result,indent=2))
    except (ValueError,KeyError,OSError) as e:p.exit(2,str(e)+'\n')

if __name__=='__main__':main()
