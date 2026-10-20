"""Build a public capture-update package (scan-assets/captures/<date>/) from a capture_import intake folder and its
privacy-blurred copy, the way the Sep 17 package was built.

Inputs (all local and read-only):
  --intake   capture_import.py package (project.json, intake-report.json, panoramas/manifest.json)
  --blurred  raw360_pipeline.py privacy output for intake/panoramas (blurred JPEGs + privacy-report.json)
  --e57      the source E57 (only its XML is read, for the original image names / video frame numbers)
  --raw      optional extra raw export files to list in provenance (name, bytes, sha256; never copied)

Output (new folder, never overwritten): panoramas/<00000..>.jpg (blurred originals), panoramas/mobile/ (2048x1024
derivatives of the blurred image), panoramas/manifest.json, registration.json, provenance.json. No mesh.

Stations are sorted by original video frame number. Route edges join only consecutive frames with distance
<= 5.5 m and height difference <= 1.5 m (the rule that reproduces the Sep 17 manifest's 95 edges); gaps are listed,
never bridged. registration.json copies the accepted May scan-to-BIM transform under status
'project-frame-provisional': a visualization candidate, not a new registration and not surveyed.
"""
import argparse, hashlib, json, math, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_STEP, MAX_RISE = 5.5, 1.5


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def e57_names(path):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from extract_e57_images import E57, node_value
    _, root = E57(path).xml()
    return {node_value(n.find('guid')): node_value(n.find('name')) for n in root.find('images2D')}


def frame_number(name):
    m = re.search(r'\((\d+)\)\.[A-Za-z]+$', name or '')
    if not m:
        raise ValueError(f'No video frame number in image name {name!r}')
    return int(m.group(1))


def route(stations):
    edges, gaps = 0, []
    for i in range(len(stations) - 1):
        a, b = stations[i]['position'], stations[i + 1]['position']
        d, rise = math.dist(a, b), abs(a[1] - b[1])
        if d <= MAX_STEP and rise <= MAX_RISE:
            stations[i]['neighbors'].append(i + 1); stations[i + 1]['neighbors'].append(i); edges += 1
        else:
            gaps.append({'from': i, 'to': i + 1, 'metres': d, 'heightDifference': rise})
    return edges, gaps


def build(a):
    from PIL import Image
    intake, blurred, out = Path(a.intake), Path(a.blurred), Path(a.out)
    if out.exists():
        raise SystemExit(f'{out} exists; packages are never overwritten')
    project = json.loads((intake / 'project.json').read_text())
    report_in = json.loads((intake / 'intake-report.json').read_text())
    manifest = json.loads((intake / 'panoramas/manifest.json').read_text())
    privacy_path = blurred / 'privacy-report.json'
    privacy = json.loads(privacy_path.read_text())
    date = project['captureDate']
    e57 = Path(a.e57)
    if e57.name != report_in['sourceName']:
        raise SystemExit('E57 name differs from intake-report sourceName')
    e57_hash = sha256(e57)
    if e57_hash != report_in['sourceHash']:
        raise SystemExit('E57 sha256 differs from intake-report sourceHash')
    if privacy['imagesProcessed'] != len(manifest['stations']):
        raise SystemExit('privacy report does not cover every station')
    names = e57_names(e57)

    stations = []
    for s in manifest['stations']:
        src = intake / 'panoramas' / s['file']
        if sha256(src) != s['sha256']:
            raise SystemExit(f'intake image hash mismatch: {s["file"]}')
        if not (blurred / s['file']).is_file():
            raise SystemExit(f'missing blurred image: {s["file"]}')
        name = names[s['id']]
        stations.append({'id': s['id'], 'intakeFile': s['file'], 'sourceName': name, 'sourceFrame': frame_number(name),
                         'position': s['position'], 'e57Quaternion': s['e57Quaternion'], 'originalSha256': s['sha256'],
                         'dimensions': s['dimensions'], 'neighbors': []})
    stations.sort(key=lambda s: s['sourceFrame'])
    if len({s['sourceFrame'] for s in stations}) != len(stations):
        raise SystemExit('duplicate video frame numbers')
    edges, gaps = route(stations)

    stage = out.with_name('.' + out.name + '.partial')
    if stage.exists():
        shutil.rmtree(stage)
    photos = stage / 'panoramas'; (photos / 'mobile').mkdir(parents=True)
    for i, s in enumerate(stations):
        name = f'{i:05d}.jpg'; src = blurred / s.pop('intakeFile')
        shutil.copyfile(src, photos / name)  # blurred bytes copied verbatim
        with Image.open(src) as im:
            if list(im.size) != s['dimensions']:
                raise SystemExit(f'blurred image size changed: {src.name}')
            im.convert('RGB').resize((2048, 1024), Image.Resampling.LANCZOS).save(photos / 'mobile' / name, quality=88)
        s['file'] = name; s['sha256'] = sha256(photos / name)
        stations[i] = {k: s[k] for k in ['id', 'file', 'sourceName', 'sourceFrame', 'position', 'e57Quaternion',
                                         'sha256', 'originalSha256', 'dimensions', 'neighbors']}
    video = sorted({re.sub(r'\(\d+\)\.[A-Za-z]+$', '', s['sourceName']) for s in stations})
    (photos / 'manifest.json').write_text(json.dumps({
        'schema': 'grimes-captured-panoramas/1', 'building': 'Grimes', 'captureDate': date, 'level': project['level'],
        'exportedStations': len(stations), 'defaultStation': stations[0]['id'],
        'frame': 'Cupix project coordinates, E57 Z-up converted to Y-up [x,z,-y]. No added floor elevation.',
        'projection': 'E57 sphericalRepresentation; image center +X, camera +Z up',
        'privacy': 'Automatic face/person blur and a fixed nadir cone applied before packaging; manual review required before publishing. sha256 = published blurred file; originalSha256 = E57 image.',
        'navigation': f'Consecutive exported frames from one source video; distance <={MAX_STEP:g}m and height difference <={MAX_RISE:g}m. Sparse gaps are not linked. Interpolation is a visual blend, not measured parallax.',
        'routeGaps': gaps, 'stations': stations}, indent=1) + '\n')

    may = json.loads((ROOT / 'alignment-analysis/accepted-registration.json').read_text())
    (stage / 'registration.json').write_text(json.dumps({
        'rotationYDegrees': may['rotationYDegrees'], 'translation': may['translation'], 'scale': 1,
        'status': 'project-frame-provisional', 'captureDate': date,
        'basis': 'Cupix project-coordinate export; May scan-to-BIM transform (alignment-analysis/accepted-registration.json) used as a visualization candidate, exactly as for Sep 17. No survey validation; no correction applied.',
        'consistencyCheck': {'method': a.check_method, 'result': a.check_result,
                             'scope': 'Internal consistency between Cupix exports only; no survey anchors. Not surveyed accuracy.'}}, indent=2) + '\n')

    raw = [{'name': e57.name, 'bytes': e57.stat().st_size, 'sha256': e57_hash, 'role': 'E57 with 100 spherical images and poses (source of this package)'}]
    for p in map(Path, a.raw or []):
        raw.append({'name': p.name, 'bytes': p.stat().st_size, 'sha256': sha256(p), 'role': 'companion export; not published'})
    pp = privacy['params']
    (stage / 'provenance.json').write_text(json.dumps({
        'captureDate': date, 'exportOptions': {'e57': 'With Pano', 'useCoordinatesFromSourceData': False},
        'observations': f'{len(stations)} exported images from {", ".join(video)}. Not a claim of complete capture inventory. Selected as Level 1 in Cupix.',
        'rawFiles': raw,
        'privacy': {'tool': 'scripts/raw360_pipeline.py privacy (scripts/raw360_privacy.py)', 'reportSchema': privacy['schema'],
                    'reportSha256': sha256(privacy_path), 'reportLocation': 'local only (capture-local/), not published',
                    'params': {k: pp[k] for k in ['faceScore', 'personScore', 'crop', 'views', 'faceMargin', 'personMargin', 'nadirFlagDeg', 'alwaysBlurNadirDeg']},
                    'maxFaceAngularSizeDeg': a.max_face_deg, 'models': privacy['models'], 'totals': privacy['totals'],
                    'flaggedImages': privacy['flaggedImages'], 'manualReviewRequired': True,
                    'note': 'Cupix exports already blur bystander faces; this step adds automatic person/face blur and a fixed nadir cone for the camera operator. Detection can miss people; not a claim of complete anonymisation.'},
        'derivatives': 'panoramas/mobile: 2048x1024 LANCZOS, JPEG quality 88, made from the blurred image',
        'mesh': None, 'routeEdges': edges, 'routeGaps': gaps}, indent=2) + '\n')
    stage.rename(out)
    print(f'{out}: {len(stations)} stations, {edges} route edges, {len(gaps)} gaps')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--intake', required=True); p.add_argument('--blurred', required=True); p.add_argument('--e57', required=True)
    p.add_argument('--out', required=True); p.add_argument('--raw', nargs='*')
    p.add_argument('--check-method', required=True); p.add_argument('--check-result', required=True)
    p.add_argument('--max-face-deg', type=float, default=25.0)
    build(p.parse_args())


if __name__ == '__main__':
    main()
