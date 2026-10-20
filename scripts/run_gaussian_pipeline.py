"""One cross-platform entry for Gaussian training on a capture.

    python scripts/run_gaussian_pipeline.py --capture 2026-09-17 [--steps N] [--quick] [--mask-nadir] [--publish --yes]
    python scripts/run_gaussian_pipeline.py --capture 2026-09-17 --list-zones
    python scripts/run_gaussian_pipeline.py --capture 2026-09-17 --zone l1-c      # train one zone (teammates)
    python scripts/run_gaussian_pipeline.py --capture 2026-09-17 --all-zones      # every zone in turn (owner; resumable)
    python scripts/run_gaussian_pipeline.py --capture 2026-10-18 --zone l1-c --seed 43   # reproducibility experiment

Stages: prepare dataset -> train (Brush v0.3.0) -> encode desktop .ksplat -> mobile .ply
+ viewer.json with provenance -> optional publish into scan-assets/gaussian/<capture>/.
Output: work/gaussian/<capture>/<timestamp>/ (zones: work/gaussian/<capture>/<zone>/<timestamp>/), gitignored. Nothing is published unless
--publish --yes is given, and existing published files are never replaced without --overwrite.

--seed N sets the random seed of both the dataset's random point sampling and Brush training (default 42 for
both, the long-standing behaviour). Without --seed the run settings carry no seed key, so existing run folders still
resume; with it, settings['seed'] differs per seed so different seeds never resume each other. Seeds fix the random
choices only; GPU floating-point non-determinism remains, so report mean +/- sd over several seeds.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import gaussian_zones as gz  # noqa: E402

PRESETS_PATH = SCRIPTS / 'gaussian_presets.json'
TOOLS_DIR = ROOT / 'tools'
WORK_ROOT = ROOT / 'work' / 'gaussian'
PUBLISH_ROOT = ROOT / 'scan-assets' / 'gaussian'
ENCODER_MODULE = TOOLS_DIR / 'node_modules' / '@mkkellogg' / 'gaussian-splats-3d' / 'build' / 'gaussian-splats-3d.module.js'

CAPTURE_KEYS = {'building': str, 'label': str, 'manifest': str, 'registration': str, 'seedGlbs': list,
                'centerId': str, 'radius': (int, float), 'size': int, 'pointCount': int,
                'seedUpAxis': str, 'train': dict, 'mobileBudget': int}
TRAIN_KEYS = ['steps', 'maxSplats', 'resolution', 'checkpointEvery', 'refineEvery', 'growthStop', 'shDegree']
QUICK_KEYS = ['maxStations', 'steps', 'size', 'pointCount', 'maxSplats', 'checkpointEvery', 'refineEvery',
              'growthStop', 'mobileBudget']


class CliError(ValueError):
    """A refused or invalid command line; message is shown to the user."""


# ---------------------------------------------------------------- presets

def validate_presets(presets):
    if presets.get('schema') != 1:
        raise ValueError('Unsupported presets schema')
    if not presets.get('captures'):
        raise ValueError('Presets define no captures')
    quick = presets.get('quick', {})
    missing = [k for k in QUICK_KEYS if not isinstance(quick.get(k), int) or quick[k] < 1]
    if missing:
        raise ValueError(f'quick preset needs positive integers: {missing}')
    if quick['growthStop'] > quick['steps']:
        raise ValueError('quick preset growthStop exceeds steps')
    for name, capture in presets['captures'].items():
        for key, kind in CAPTURE_KEYS.items():
            if key not in capture or not isinstance(capture[key], kind):
                raise ValueError(f'Capture {name}: missing or invalid "{key}"')
        if capture['seedUpAxis'] not in ('y', 'z'):
            raise ValueError(f'Capture {name}: seedUpAxis must be y or z')
        if capture['radius'] <= 0:
            raise ValueError(f'Capture {name}: radius must be positive')
        train = capture['train']
        for key in TRAIN_KEYS:
            if not isinstance(train.get(key), int) or train[key] < 0:
                raise ValueError(f'Capture {name}: train.{key} must be a non-negative integer')
        if train['growthStop'] > train['steps']:
            raise ValueError(f'Capture {name}: growthStop exceeds steps')
    return presets


def load_presets(path=PRESETS_PATH):
    return validate_presets(json.loads(Path(path).read_text()))


def build_settings(preset, quick_preset=None, quick=False, steps=None, max_splats=None, resolution=None, seed=None):
    """Resolve prepare/train parameters. Pure: no I/O."""
    train = dict(preset['train'])
    prepare = {'size': preset['size'], 'pointCount': preset['pointCount'], 'maxStations': None,
               'radius': preset['radius'], 'centerId': preset['centerId'], 'seedUpAxis': preset['seedUpAxis']}
    mobile_budget = preset['mobileBudget']
    if quick:
        q = quick_preset
        prepare.update(size=q['size'], pointCount=q['pointCount'], maxStations=q['maxStations'])
        train.update(steps=q['steps'], maxSplats=q['maxSplats'], checkpointEvery=q['checkpointEvery'],
                     refineEvery=q['refineEvery'], growthStop=q['growthStop'], resolution=min(train['resolution'], q['size']))
        mobile_budget = q['mobileBudget']
    if steps is not None:
        # Keep the preset's growth schedule proportion (30k of 50k) when the step count changes.
        ratio = preset['train']['growthStop'] / preset['train']['steps']
        train['steps'] = steps
        train['growthStop'] = min(train['growthStop'], round(steps * ratio))
        train['checkpointEvery'] = min(train['checkpointEvery'], max(1, steps))
    if max_splats is not None:
        train['maxSplats'] = max_splats
    if resolution is not None:
        train['resolution'] = resolution
    settings = {'prepare': prepare, 'train': train, 'mobileBudget': mobile_budget}
    if seed is not None:  # only when requested: default settings stay byte-identical so --resume/find_run still match
        settings['seed'] = prepare['seed'] = train['seed'] = seed
    return settings


# ---------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--capture', help='capture date key from gaussian_presets.json (required except with --list-zones)')
    p.add_argument('--zone', help='train only this zone of the capture (id from gaussian_zones.json; see --list-zones)')
    p.add_argument('--all-zones', action='store_true', help='train every zone of the capture one after another (resumable: finished zones are skipped)')
    p.add_argument('--list-zones', action='store_true', help='print the zones (stations, owner, status) and exit')
    p.add_argument('--zones-file', type=Path, default=gz.ZONES_PATH, help=argparse.SUPPRESS)
    p.add_argument('--steps', type=int, help='override training steps (growth stop scales with it)')
    p.add_argument('--max-splats', type=int, help='override the splat cap (lower it if memory runs out)')
    p.add_argument('--resolution', type=int, help='override Brush training resolution')
    p.add_argument('--seed', type=int, help='random seed for dataset point sampling and Brush training (default 42 in both); for reproducibility experiments, e.g. 42 43 44')
    p.add_argument('--quick', action='store_true', help='smoke test: 4 stations, 300 steps, tiny model; never publishable')
    p.add_argument('--mask-nadir', action='store_true', help='drop downward-looking faces where the camera operator appears')
    p.add_argument('--watch', action='store_true', help="open Brush's live training window to watch the scene form")
    p.add_argument('--publish', action='store_true', help='copy results into scan-assets/gaussian/<capture>/ (zones: .../<capture>/zones/<zone>/) (needs --yes)')
    p.add_argument('--yes', action='store_true', help='confirm the publish checklist')
    p.add_argument('--overwrite', action='store_true', help='allow replacing an already published capture folder')
    p.add_argument('--brush', type=Path, help='use this Brush binary instead of tools/brush/')
    p.add_argument('--output-root', type=Path, default=WORK_ROOT)
    p.add_argument('--resume', type=Path, help='re-use a previous run folder, skipping finished stages')
    p.add_argument('--dry-run', action='store_true', help='print resolved settings and exit')
    return p


def publish_target(publish_root, capture, zone_id=None):
    base = Path(publish_root) / capture
    return base / 'zones' / zone_id if zone_id else base


def validate_args(args, presets, publish_root=PUBLISH_ROOT, zones_doc=None):
    """Refuse unsafe or contradictory command lines before any expensive work."""
    zone, all_zones = getattr(args, 'zone', None), getattr(args, 'all_zones', False)
    if getattr(args, 'list_zones', False):
        return args
    if not args.capture:
        raise CliError('--capture is required')
    if zone and all_zones:
        raise CliError('--zone and --all-zones are mutually exclusive')
    if all_zones and args.resume:
        raise CliError('--resume applies to one run; --all-zones resumes unfinished zones by itself')
    zone_ids = []
    if zone or all_zones:
        try:
            zone_ids = gz.zone_ids(zones_doc, args.capture)
            if zone:
                gz.get_zone(zones_doc, args.capture, zone)
        except (gz.ZoneError, TypeError) as error:
            raise CliError(str(error))
    if args.capture not in presets['captures']:
        raise CliError(f'Unknown capture {args.capture!r}; choose from {sorted(presets["captures"])}')
    if getattr(args, 'seed', None) is not None and args.seed < 0:
        raise CliError('--seed must be non-negative')
    for name in ('steps', 'max_splats', 'resolution'):
        value = getattr(args, name)
        if value is not None and value < 1:
            raise CliError(f'--{name.replace("_", "-")} must be positive')
    if args.overwrite and not args.publish:
        raise CliError('--overwrite only applies with --publish')
    if args.publish:
        if args.quick:
            raise CliError('--quick results are smoke tests and cannot be published')
        if not args.yes:
            raise CliError('--publish requires --yes after you have read the checklist above')
        for target in [publish_target(publish_root, args.capture, z) for z in (zone_ids if all_zones else [zone])]:
            if target.exists() and not args.overwrite:
                raise CliError(f'{target} already exists; add --overwrite to replace published files')
    return args


def publish_checklist(capture, preset, mask_nadir, registration_status, zone=None):
    lines = [f'Publish checklist for {capture}:',
             '  [ ] Privacy: the panoramas include the camera operator at nadir (looking straight down).',
             ('      This run used --mask-nadir (downward faces dropped). Still inspect the result for people.'
              if mask_nadir else
              '      This run did NOT use --mask-nadir. Inspect floor views for a person, or re-run with --mask-nadir.'),
             '  [ ] Alignment: scan-to-BIM registration status is ' + (registration_status or 'UNKNOWN') + '.',
             ('      Provisional: label the layer as an appearance preview, not registered geometry.'
              if registration_status != 'geometry-registered' else
              '      Registered: still not independently surveyed geometry.'),
             '  [ ] Labels: result is an experimental appearance layer; metrics are held-out stations from the',
             '      same reconstruction, not controlled across captures and not geometry accuracy.',
             (f'  [ ] Size: files go to scan-assets/gaussian/{capture}/zones/{zone}/ and zones/index.json (tracked in the repo, public once pushed).'
              if zone else f'  [ ] Size: files go to scan-assets/gaussian/{capture}/ (tracked in the repo, public once pushed).')]
    if zone:
        lines.append('  [ ] Zone: only this zone is replaced; check its seams against neighbouring zones before publishing them.')
    return '\n'.join(lines)


def registration_status(preset, root=ROOT):
    try:
        return json.loads((Path(root) / preset['registration']).read_text()).get('status')
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- parsing and provenance

_NUM = r'([0-9]+(?:\.[0-9]+)?)'


def parse_eval_metrics(log_text):
    """Last evaluation PSNR/SSIM mentioned in a Brush log (ANSI colour codes ignored)."""
    text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', log_text)
    psnr = re.findall(r'psnr[^0-9\-\n]{0,12}' + _NUM, text, flags=re.I)
    ssim = re.findall(r'ssim[^0-9\-\n]{0,12}' + _NUM, text, flags=re.I)
    return {'psnr': float(psnr[-1]) if psnr else None, 'ssim': float(ssim[-1]) if ssim else None}


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def assemble_provenance(*, capture, preset, settings, quick, mask_nadir, argv, input_hashes, tools,
                        timings, started_at, ended_at, metrics, dataset_report, steps):
    """Everything needed to reproduce and judge a run. Pure: callers supply measured values."""
    stations = dataset_report.get('stations', [])
    eval_stations = sum(1 for s in stations if s.get('split') == 'evaluation')
    validation = {'stations': eval_stations, 'views': dataset_report.get('evaluationViews'),
                  'psnr': metrics.get('psnr'), 'ssim': metrics.get('ssim'),
                  'scope': 'Station-held-out validation parsed from the Brush log; no independent final test set; '
                           'not controlled across captures; camera poses and seed come from the same reconstruction.'}
    return {
        'capture': capture,
        'building': preset['building'],
        'trainingIterations': steps,
        'validation': validation,
        'pipeline': {
            'script': 'scripts/run_gaussian_pipeline.py',
            'argv': list(argv),
            'smokeTest': bool(quick),
            'nadirMasked': bool(mask_nadir),
            'settings': settings,
            'inputs': input_hashes,
            'tools': tools,
            'timingsSeconds': timings,
            'startedAt': started_at,
            'endedAt': ended_at,
            'trainViews': dataset_report.get('trainViews'),
            'evaluationViews': dataset_report.get('evaluationViews'),
        },
    }


# ---------------------------------------------------------------- run helpers

class Run:
    """A run folder plus a small resumable state file."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.state_path = self.folder / 'run.json'
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {'stages': {}}

    def done(self, stage):
        return self.state['stages'].get(stage, {}).get('status') == 'done'

    def mark(self, stage, status, seconds=None, **extra):
        self.state['stages'][stage] = {'status': status, 'seconds': seconds, **extra}
        self.save()

    def save(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=2))


def stage_banner(n, total, name):
    print(f'\n=== [{n}/{total}] {name} ===', flush=True)


def tool_versions(brush_path, brush_sha):
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip().splitlines()[0]
        except Exception:
            return None
    node = shutil.which('node')
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:
        commit = None
    return {'brush': run([str(brush_path), '--version']), 'brushExecutableSha256': brush_sha,
            'node': run([node, '--version']) if node else None, 'python': platform.python_version(),
            'gaussianSplats3d': '0.4.7', 'os': f'{platform.system()} {platform.release()} {platform.machine()}',
            'repoCommit': commit}


def encode_ksplat(ply, ksplat):
    node = shutil.which('node')
    if not node:
        raise SystemExit('Node.js is required for the encode stage (install Node 22+).')
    if not ENCODER_MODULE.is_file():
        raise SystemExit('Encoder dependency missing. Run: python scripts/setup_gaussian_env.py')
    env = {**os.environ, 'GAUSSIAN_MODULE': ENCODER_MODULE.as_uri()}
    subprocess.run([node, str(SCRIPTS / 'encode_gaussian.mjs'), str(ply), str(ksplat)], check=True, env=env,
                   stdout=subprocess.DEVNULL)


def resolve_brush(arg):
    if arg:
        return Path(arg).resolve()
    import get_brush
    return get_brush.ensure_brush()


ZONE_INDEX_SCOPE = ('Experimental appearance layer; not surveyed geometry. Only the zones listed here are trained and '
                    'published; areas of other planned zones have no Gaussian yet.')


def merge_zone_index(existing, capture, building, floor, entry, alignment=None):
    """zones/index.json content after publishing one zone. Pure: `entry` replaces the same id.
    Honesty labels (status, alignment, scope) are top-level keys that viewers may show; they never change the schema."""
    zones = [z for z in (existing or {}).get('zones', []) if z.get('id') != entry['id']] + [entry]
    zones.sort(key=lambda z: z['id'])
    out = {'schema': 1, 'capture': capture, 'building': building, 'floor': floor,
           'frame': 'scan-y-up-metres', 'defaultZone': (existing or {}).get('defaultZone') or zones[0]['id'], 'zones': zones,
           'status': 'experimental-trained', 'scope': ZONE_INDEX_SCOPE}
    alignment = alignment or (existing or {}).get('alignment')
    if alignment:
        out['alignment'] = alignment
    return out


def publish(package_dir, capture, preset, destination_root, overwrite, mask_nadir, quick, zone=None, geometry=None,
            alignment=None):
    """Copy a packaged run to scan-assets/gaussian/<capture>/ or, for a zone, <capture>/zones/<zone>/ and
    refresh <capture>/zones/index.json. `alignment` = scan-to-BIM registration status shown with the layer
    (default: the preset's registration file)."""
    alignment = alignment or registration_status(preset)
    destination = publish_target(destination_root, capture, zone['id'] if zone else None)
    if destination.exists() and not overwrite:
        raise CliError(f'{destination} already exists; add --overwrite')
    manifest = json.loads((package_dir / 'viewer.json').read_text())
    manifest['capture'] = capture
    manifest['building'] = preset['building']
    if alignment:
        manifest['alignment'] = alignment
    today = datetime.now(timezone.utc).date().isoformat()
    manifest['publication'] = (f'Published {today} from scripts/run_gaussian_pipeline.py'
                               f'{" with nadir faces masked" if mask_nadir else ""}'
                               f'{" for zone " + zone["id"] + " (" + zone["name"] + ")" if zone else ""}. Experimental appearance layer; '
                               'not surveyed geometry; see provenance.pipeline for settings and held-out metrics.')
    destination.mkdir(parents=True, exist_ok=True)
    for name in (manifest['file'], manifest['mobileFile']):
        shutil.copyfile(package_dir / name, destination / name)
    (destination / 'viewer.json').write_text(json.dumps(manifest, indent=2))
    if zone:
        index_path = destination.parent / 'index.json'
        existing = json.loads(index_path.read_text()) if index_path.exists() else None
        entry = {'id': zone['id'], 'name': zone['name'], 'manifest': f'{zone["id"]}/viewer.json',
                 'stationCount': len(zone['stations']), 'coreCount': len(zone['core']),
                 'bounds': geometry['bounds'], 'coreBounds': geometry['coreBounds'],
                 'corePositions': geometry['corePositions'], 'splatCount': manifest['splatCount'], 'publishedAt': today}
        index = merge_zone_index(existing, capture, preset['building'], zone_floor(zone, geometry), entry, alignment)
        index_path.write_text(json.dumps(index, indent=2))
    return destination


def zone_floor(zone, geometry):
    return (geometry or {}).get('floor') or zone.get('floor') or ''


# ---------------------------------------------------------------- zones

def zone_settings(settings, zone, geometry, quick_preset, quick):
    """Pure: settings for a zone run. Trains exactly the zone's stations, seeded around its core centre."""
    out = json.loads(json.dumps(settings))
    out['prepare'].update(centerId=geometry['centerId'], radius=geometry['radius'], stations=list(zone['stations']))
    out['zone'] = {'id': zone['id'], 'name': zone['name'], 'stations': list(zone['stations']), 'core': list(zone['core']),
                   'overlapMetres': zone['overlapMetres'], 'bounds': geometry['bounds'], 'coreBounds': geometry['coreBounds']}
    return out


def zone_run_dir(output_root, capture, zone_id=None):
    root = Path(output_root) / capture
    return root / zone_id if zone_id else root


def find_run(output_root, capture, zone_id, settings):
    """Newest earlier run folder of this zone with identical settings (never a smoke test).
    Returns (folder, finished) or (None, False)."""
    root = zone_run_dir(output_root, capture, zone_id)
    if not root.is_dir():
        return None, False
    for folder in sorted((d for d in root.iterdir() if (d / 'run.json').is_file()), reverse=True):
        try:
            state = json.loads((folder / 'run.json').read_text())
        except (OSError, ValueError):
            continue
        if state.get('settings') != settings:
            continue
        return folder, state.get('stages', {}).get('package', {}).get('status') == 'done'
    return None, False


def format_timing_table(rows):
    """rows: [(zone, status, {stage: seconds})] -> text with minutes per zone."""
    lines = [f'{"zone":<10}{"status":<10}{"train min":>10}{"total min":>11}']
    total = 0.0
    for zone, status, timings in rows:
        t = timings or {}
        whole = sum(v for v in t.values() if isinstance(v, (int, float)))
        total += whole
        train = t.get('train')
        lines.append(f'{zone:<10}{status:<10}{(f"{train / 60:.1f}" if train is not None else "-"):>10}{whole / 60:>11.1f}')
    lines.append(f'{"all":<10}{"":<10}{"":>10}{total / 60:>11.1f}')
    return '\n'.join(lines)


def load_zone_context(args, presets, zone_id):
    doc = gz.load_zones(args.zones_file)
    entry = doc['captures'][args.capture]
    zone = dict(gz.get_zone(doc, args.capture, zone_id), floor=entry['floor'])
    manifest = json.loads((ROOT / presets['captures'][args.capture]['manifest']).read_text())
    gz.validate_zones(doc, {args.capture: {s['id'] for s in manifest['stations']}})
    geometry = gz.zone_geometry(zone, manifest['stations'])
    geometry['floor'] = entry['floor']
    return zone, geometry


# ---------------------------------------------------------------- one run

def execute(args, argv, preset, settings, folder, zone=None, geometry=None):
    """Run (or resume) the four stages in `folder`. Returns (exit code, run state timings, package dir)."""
    capture = args.capture
    started = datetime.now(timezone.utc)
    run = Run(folder)
    run.state.update(capture=capture, argv=argv, settings=settings, quick=bool(args.quick), zone=zone['id'] if zone else None)
    run.state.setdefault('startedAt', started.isoformat())
    run.save()
    print(f'Run folder: {folder}', flush=True)

    import get_brush  # noqa: F401  (resolve_brush imports lazily too)
    import prepare_gaussian_dataset
    import train_gaussian
    import package_gaussian

    timings = {name: s.get('seconds') for name, s in run.state['stages'].items() if s.get('seconds') is not None}
    dataset, train_dir = folder / 'dataset', folder / 'train'
    ply = train_dir / f'export_{settings["train"]["steps"]}.ply'
    ksplat = folder / 'encoded' / 'trained.ksplat'
    package_dir = folder / 'package'
    p = settings['prepare']
    manifest = ROOT / preset['manifest']
    seed_glbs = [ROOT / g for g in preset['seedGlbs']]
    total = 4
    try:
        stage_banner(1, total, 'Prepare dataset')
        if run.done('prepare'):
            print('already done, skipping')
        else:
            t = time.monotonic()
            if dataset.exists():
                shutil.rmtree(dataset)
            prepare_gaussian_dataset.build(manifest, dataset, p['centerId'], p['radius'], p['size'], seed_glbs,
                                           p['pointCount'], p['seedUpAxis'], args.mask_nadir, p['maxStations'],
                                           p.get('stations'), seed=p.get('seed', 42))
            timings['prepare'] = round(time.monotonic() - t, 1)
            run.mark('prepare', 'done', timings['prepare'])

        stage_banner(2, total, 'Train with Brush (long step: leave the machine to itself)')
        brush = resolve_brush(args.brush)
        if run.done('train') and ply.is_file():
            print('already done, skipping')
        else:
            if train_dir.exists():  # an interrupted attempt: keep it, start clean
                train_dir.rename(folder / f'train.interrupted-{int(time.time())}')
            t = time.monotonic()
            tr = settings['train']
            record = train_gaussian.train(brush, dataset, train_dir, tr['steps'], tr['maxSplats'], tr['resolution'],
                                          tr['checkpointEvery'], tr['refineEvery'], tr['growthStop'], tr['shDegree'], stream=True,
                                          viewer=args.watch, seed=tr.get('seed'))
            timings['train'] = round(time.monotonic() - t, 1)
            if record['status'] != 'trained':
                run.mark('train', 'failed', timings['train'])
                raise RuntimeError(f'Brush did not finish (exit {record.get("exitCode")}); see {train_dir / "train.log"}')
            run.mark('train', 'done', timings['train'])

        stage_banner(3, total, 'Encode desktop .ksplat')
        if run.done('encode') and ksplat.is_file():
            print('already done, skipping')
        else:
            t = time.monotonic()
            if ksplat.parent.exists():
                shutil.rmtree(ksplat.parent)
            encode_ksplat(ply, ksplat)
            timings['encode'] = round(time.monotonic() - t, 1)
            run.mark('encode', 'done', timings['encode'])

        stage_banner(4, total, 'Mobile preview and viewer.json')
        t = time.monotonic()
        if package_dir.exists():
            shutil.rmtree(package_dir)
        package_gaussian.package(ply, package_dir, manifest, p['centerId'], settings['mobileBudget'],
                                 settings['train']['steps'], ksplat)
        timings['package'] = round(time.monotonic() - t, 1)
        record = json.loads((train_dir / 'command.json').read_text())
        metrics = parse_eval_metrics((train_dir / 'train.log').read_text(errors='replace'))
        dataset_report = json.loads((dataset / 'dataset-provenance.json').read_text())
        input_hashes = {'manifestSha256': sha256_file(manifest), 'seedGlbSha256': {g.name: sha256_file(g) for g in seed_glbs},
                        'datasetProvenanceSha256': sha256_file(dataset / 'dataset-provenance.json')}
        extra = assemble_provenance(
            capture=capture, preset=preset, settings=settings, quick=args.quick, mask_nadir=args.mask_nadir,
            argv=argv, input_hashes=input_hashes, tools=tool_versions(brush, record.get('executableSha256')),
            timings=timings, started_at=run.state['startedAt'], ended_at=datetime.now(timezone.utc).isoformat(),
            metrics=metrics, dataset_report=dataset_report, steps=settings['train']['steps'])
        viewer = json.loads((package_dir / 'viewer.json').read_text())
        viewer['capture'], viewer['building'] = extra['capture'], extra['building']
        viewer['provenance']['validation'] = extra['validation']
        viewer['provenance']['pipeline'] = extra['pipeline']
        viewer['provenance']['selectionStatus'] = ('Smoke test only; not a usable reconstruction.' if args.quick else
                                                   'Local run from the one-command pipeline; not yet reviewed or selected.')
        if zone:
            viewer['zone'] = settings['zone']
            viewer['zone']['stationSelection'] = dataset_report.get('stationSelection')
        (package_dir / 'viewer.json').write_text(json.dumps(viewer, indent=2))
        run.mark('package', 'done', timings['package'])
    except KeyboardInterrupt:
        print(f'\nInterrupted. Finished stages are kept in {folder}.\n'
              f'Resume (skips finished stages; training restarts from step 0): '
              f'python scripts/run_gaussian_pipeline.py {" ".join(a for a in argv if a != "--resume")} --resume "{folder}"', file=sys.stderr)
        return 130, timings, package_dir
    except Exception as error:
        print(f'\nFailed: {error}\nFinished stages are kept in {folder}. After fixing the cause, re-run with --resume "{folder}"'
              f'{" (or re-run --all-zones, which resumes it)" if getattr(args, "all_zones", False) else ""}.', file=sys.stderr)
        return 1, timings, package_dir

    run.state['endedAt'] = datetime.now(timezone.utc).isoformat()
    run.save()
    print(f'\nDone. Eval PSNR {metrics["psnr"]} SSIM {metrics["ssim"]}. Results: {package_dir}')
    zone_arg = f' --zone {zone["id"]}' if zone else ''
    print(f'Preview: python scripts/preview_gaussian.py --capture {capture}{zone_arg}')
    if args.publish:
        destination = publish(package_dir, capture, preset, PUBLISH_ROOT, args.overwrite, args.mask_nadir, args.quick,
                              zone=zone, geometry=geometry)
        print(f'Published to {destination}. Review `git status`, then commit deliberately.')
    return 0, timings, package_dir


# ---------------------------------------------------------------- main

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    presets = load_presets()
    zones_doc = None
    if args.list_zones or args.zone or args.all_zones:
        try:
            zones_doc = gz.load_zones(args.zones_file)
            if args.list_zones:
                print(gz.describe_zones(zones_doc, args.capture))
                return 0
        except (gz.ZoneError, OSError, ValueError) as error:
            print(f'error: {error}', file=sys.stderr)
            return 2
    preset_ok = presets['captures'].get(args.capture)
    if args.publish and preset_ok:
        print(publish_checklist(args.capture, preset_ok, args.mask_nadir, registration_status(preset_ok), args.zone))
    try:
        validate_args(args, presets, zones_doc=zones_doc)
    except CliError as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    preset = presets['captures'][args.capture]
    base = build_settings(preset, presets['quick'], args.quick, args.steps, args.max_splats, args.resolution,
                          getattr(args, 'seed', None))
    base['maskNadir'] = args.mask_nadir

    zone_ids = gz.zone_ids(zones_doc, args.capture) if args.all_zones else [args.zone] if args.zone else [None]
    plans = []
    for zid in zone_ids:
        if zid is None:
            plans.append((None, None, base))
            continue
        try:
            zone, geometry = load_zone_context(args, presets, zid)
        except (gz.ZoneError, OSError, ValueError, KeyError) as error:
            print(f'error: {error}', file=sys.stderr)
            return 2
        plans.append((zone, geometry, zone_settings(base, zone, geometry, presets['quick'], args.quick)))

    if args.dry_run:
        out = {'capture': args.capture, 'settings': plans[0][2]} if not (args.zone or args.all_zones) else {
            'capture': args.capture, 'zones': [{'zone': z['id'], 'stations': len(z['stations']), 'core': len(z['core']),
                                                'centerId': g['centerId'], 'radius': g['radius'],
                                                'outputRoot': str(zone_run_dir(args.output_root, args.capture, z['id'])),
                                                'publishTo': str(publish_target(PUBLISH_ROOT, args.capture, z['id'])),
                                                'settings': s} for z, g, s in plans]}
        print(json.dumps(out, indent=2))
        return 0

    rows, code = [], 0
    for zone, geometry, settings in plans:
        zid = zone['id'] if zone else None
        if zone:
            print(f'\n##### Zone {zid}: {zone["name"]} ({len(zone["stations"])} stations, owner: {zone["owner"] or "-"}) #####', flush=True)
        if args.resume:
            folder = args.resume.resolve()
        elif args.all_zones:
            found, finished = find_run(args.output_root, args.capture, zid, settings)
            if found and finished and not args.publish:
                print(f'Already trained in {found}; skipping (delete that folder to retrain).')
                state = json.loads((found / 'run.json').read_text())
                rows.append((zid, 'skipped', {k: v.get('seconds') for k, v in state['stages'].items()}))
                continue
            folder = found if found and not finished else None
            if found and finished:
                folder = found  # publish requested: reuse its finished stages, then publish
        else:
            folder = None
        if folder is None:
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            folder = (zone_run_dir(args.output_root, args.capture, zid) / stamp).resolve()
        result, timings, _ = execute(args, argv, preset, settings, folder, zone, geometry)
        rows.append((zid or args.capture, 'done' if result == 0 else 'failed', timings))
        if result:
            code = result
            break
    if args.all_zones:
        print('\n' + format_timing_table(rows))
        if code:
            print('Stopped at the first failure; re-run the same --all-zones command to continue (finished zones are skipped).', file=sys.stderr)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
