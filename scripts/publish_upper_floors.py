#!/usr/bin/env python3
"""Publish the Oct 18, 2026 Level 2 / Level 3 360-degree photos (approved manual-blur set) as per-floor packages.

    python3 scripts/publish_upper_floors.py            # build scan-assets/captures/2026-10-18/floors/{L2,L3}
    python3 scripts/publish_upper_floors.py --check    # verify an existing build against the sources, write nothing

Inputs (local, ignored capture-local/, never modified):
  capture-local/grimes-L{2,3}-2026-10-18-v2/panoramas/manifest.json   station positions, route, floor assignment
  capture-local/grimes-L{2,3}-2026-10-18-v2/registration.json         must equal the published Oct 18 registration
  capture-local/grimes-UPPER-2026-10-18-raw477-manual/                 approved images (strict auto-blur + manual boxes)
  capture-local/grimes-UPPER-2026-10-18-raw477-blurred-v2/privacy-report.json   strict auto-blur parameters
The v2 packages display the older auto-blur output; only the station metadata is taken from them. Every published
full-resolution image is a byte copy of the manual set (sha256 checked); mobile copies are 2048x1024 LANCZOS, JPEG
quality 88, made from that copy (same recipe as scripts/build_capture_update.py).
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / 'capture-local'
MANUAL = LOCAL / 'grimes-UPPER-2026-10-18-raw477-manual'
AUTO_REPORT = LOCAL / 'grimes-UPPER-2026-10-18-raw477-blurred-v2' / 'privacy-report.json'
REVIEW_PDF = LOCAL / 'grimes-UPPER-2026-10-18-raw477-manual-review' / 'Oct18_L2-L3_manual-blur_review.pdf'
CAPTURE = ROOT / 'scan-assets' / 'captures' / '2026-10-18'
FLOORS = ('L2', 'L3')
APPROVED = '2026-10-28'
SOURCE_VIDEO = 'VID_20261018_153400_00_477'
PRIVACY = ('automatic blur (strict) + manual blur boxes after manual review of every image; publishing approved by the '
           'owner on ' + APPROVED + '; not a claim of full anonymisation. Strict automatic blur = person score 0.15, '
           'crop 1536, fixed nadir cone. sha256 = published file.')
PLACEMENT = ('Frames from the raw 360-degree video ' + SOURCE_VIDEO + ' (not a Cupix export). Positions: local '
             'structure-from-motion submodels fitted by frame number to the Cupix-placed stations of the same video '
             '(upper-walk candidate: photo matching to Level 1 + yaw/XYZ ICP to BIM), moved into the Level 1 scan frame; '
             'the provisional Oct 18 registration then maps them to BIM. A Cupix-free placement dry run '
             '(scripts/raw360_bim.py) differs by a median 0.09 m (max 0.31 m) over 79 frames. Provisional, not surveyed.')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def check_registration(floor):
    pub, loc = load(CAPTURE / 'registration.json'), load(LOCAL / f'grimes-{floor}-2026-10-18-v2' / 'registration.json')
    for k in ('rotationYDegrees', 'translation', 'scale'):
        if pub[k] != loc[k]:
            raise SystemExit(f'{floor}: v2 registration {k} differs from the published Oct 18 registration')


def floor_manifest(src, floor, files):
    keep = ('schema', 'level', 'captureDate', 'exportedStations', 'defaultStation', 'frame', 'projection', 'navigation',
            'navigationLimits', 'levels', 'walkGroups', 'floorAssignment', 'coverage')
    m = {'building': 'Grimes'} | {k: src[k] for k in keep}
    m['status'] = 'published-provisional'
    m['alignment'] = 'provisional, not surveyed'
    m['placement'] = PLACEMENT
    m['privacy'] = PRIVACY
    s = src['source']
    m['source'] = {'kind': s['kind'], 'video': SOURCE_VIDEO, 'panoramasInVideo': s['panoramas'],
                   'models': [{k: x[k] for k in ('model', 'frames', 'frameRange', 'status', 'scale', 'fitResidualMetres',
                                                 'leaveOneOutMetres')} for x in s['models']],
                   'heldOutAfterIcp': s['heldOutAfterIcp'], 'heldOutAfterIcpThisFloor': s['heldOutAfterIcpThisFloor'],
                   'metricsNote': 'Internal consistency only (fit to Cupix-placed stations; ICP residuals are distances to '
                                  'BIM design surfaces). Not surveyed accuracy.'}
    m['stations'] = []
    for st in src['stations']:
        st = dict(st)
        f = files[st['file']]
        st['sha256'], st['mobileSha256'], st['manualBlurBoxes'] = f['sha256'], f['mobileSha256'], f['manualBlurBoxes']
        st['originalSha256'] = None
        m['stations'].append(st)
    if m['exportedStations'] != len(m['stations']):
        raise SystemExit(f'{floor}: exportedStations mismatch')
    return m


def build(check_only):
    boxes = load(MANUAL / 'manual-boxes.json')
    auto = load(AUTO_REPORT)
    out_all = {}
    for floor in FLOORS:
        check_registration(floor)
        src = load(LOCAL / f'grimes-{floor}-2026-10-18-v2' / 'panoramas' / 'manifest.json')
        if src['level'] != floor or src['captureDate'] != '2026-10-18':
            raise SystemExit(f'{floor}: unexpected source manifest')
        out = CAPTURE / 'floors' / floor
        photos = out / 'panoramas'
        files = {}
        for st in src['stations']:
            name = st['file']
            if name != f"f{st['sourceFrame']:06d}.jpg" or st['sourceName'] != f"raw477 frame {st['sourceFrame']}":
                raise SystemExit(f'{floor}: station {st["id"]} does not map to a raw477 frame file')
            source = MANUAL / name
            digest = sha256(source)
            dest, mobile = photos / name, photos / 'mobile' / name
            if not check_only:
                from PIL import Image
                (photos / 'mobile').mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
                with Image.open(dest) as im:
                    if im.size != (4096, 2048):
                        raise SystemExit(f'{name}: {im.size}, expected 4096x2048')
                    im.convert('RGB').resize((2048, 1024), Image.Resampling.LANCZOS).save(mobile, quality=88)
            if sha256(dest) != digest:
                raise SystemExit(f'{floor}/{name}: published file is not byte-identical to the manual set')
            files[name] = {'file': name, 'stationId': st['id'], 'sha256': digest, 'mobileSha256': sha256(mobile),
                           'bytes': dest.stat().st_size, 'mobileBytes': mobile.stat().st_size,
                           'manualBlurBoxes': len(boxes.get(name, []))}
        manifest = floor_manifest(src, floor, files)
        n_boxes = sum(f['manualBlurBoxes'] for f in files.values())
        prov = {
            'schema': 'grimes-floor-package/1', 'captureDate': '2026-10-18', 'level': floor, 'status': 'published-provisional',
            'alignment': 'provisional, not surveyed', 'sourceVideo': SOURCE_VIDEO + '.insv',
            'images': 'equirectangular 4096x2048 frames extracted from the raw INSV video (scripts/raw360_pipeline.py), '
                      'not a Cupix export',
            'placement': PLACEMENT, 'placementCupixFree': False,
            'registration': {'file': '../../registration.json', 'note': 'stations are in the Level 1 scan frame; the '
                             'published Oct 18 provisional registration applies unchanged (checked equal to the v2 package '
                             'registration: rotationYDegrees, translation, scale)'},
            'stationSource': f'capture-local/grimes-{floor}-2026-10-18-v2/panoramas/manifest.json (local, not published; '
                             'built by scripts/multifloor_review.py floors)',
            'privacy': {
                'method': 'automatic blur (strict) + manual blur boxes after manual review of every image',
                'automaticBlur': {'tool': 'scripts/raw360_pipeline.py privacy (scripts/raw360_privacy.py)',
                                  'params': auto['params'] | {'input': None, 'out': None, 'masksOut': None},
                                  'models': auto['models'], 'totalsAll108': auto['totals'],
                                  'reportSha256': sha256(AUTO_REPORT), 'reportLocation': 'local only, not published'},
                'manualBoxes': {'thisFloor': n_boxes, 'allUpperFloors': sum(len(v) for v in boxes.values()),
                                'imagesWithBoxesThisFloor': sum(1 for f in files.values() if f['manualBlurBoxes']),
                                'file': 'manual-boxes.json (local only, not published)',
                                'sha256': sha256(MANUAL / 'manual-boxes.json')},
                'manualReview': {'status': 'done', 'scope': 'every image of the upper-floor set (108) reviewed by a person',
                                 'reviewDocumentSha256': sha256(REVIEW_PDF), 'reviewDocumentLocation': 'local only, not published',
                                 'publishApproved': APPROVED, 'approvedBy': 'owner',
                                 'supplementaryPass': '2026-10-28, after publishing: 39 more boxes on small distant people '
                                                      '(far balcony / atrium / through glass) in 36 images, found by a second '
                                                      'full-resolution look at the horizon band of all 108 images; counts above include them'},
                'publishedFilesVerified': 'full-resolution panoramas are byte-identical to the approved manual-blur set '
                                          '(sha256 per file below); mobile copies are resized from them',
                'statement': 'Detection and review can miss people; not a claim of full anonymisation.'},
            'derivatives': 'panoramas/mobile: 2048x1024 LANCZOS, JPEG quality 88, made from the published image',
            'notPublished': ['combined Level 1-3 graph (floors=all)', 'Gaussian splats', 'meshes',
                             'raw477 Gaussian', 'older automatic-blur images', 'unblurred frames'],
            'files': sorted(files.values(), key=lambda f: f['file']),
        }
        if not check_only:
            (photos / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
            (out / 'provenance.json').write_text(json.dumps(prov, indent=1) + '\n')
        else:
            pm, pp = load(photos / 'manifest.json'), load(out / 'provenance.json')
            if pm != manifest or pp['files'] != prov['files']:
                raise SystemExit(f'{floor}: published manifest/provenance differ from a fresh build')
        out_all[floor] = {'stations': len(files), 'manualBoxes': n_boxes,
                          'bytes': sum(f['bytes'] + f['mobileBytes'] for f in files.values())}
    print(json.dumps(out_all, indent=1))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true')
    build(ap.parse_args().check)
    sys.exit(0)
