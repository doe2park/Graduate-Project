"""One cross-platform entry for Gaussian training on a capture.

    python scripts/run_gaussian_pipeline.py --capture 2026-09-17 [--steps N] [--quick] [--mask-nadir] [--publish --yes]

Stages: prepare dataset -> train (Brush v0.3.0) -> encode desktop .ksplat -> mobile .ply
+ viewer.json with provenance -> optional publish into scan-assets/gaussian/<capture>/.
Output: work/gaussian/<capture>/<timestamp>/ (gitignored). Nothing is published unless
--publish --yes is given, and existing published files are never replaced without --overwrite.
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


def build_settings(preset, quick_preset=None, quick=False, steps=None, max_splats=None, resolution=None):
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
    return {'prepare': prepare, 'train': train, 'mobileBudget': mobile_budget}


# ---------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--capture', required=True, help='capture date key from gaussian_presets.json')
    p.add_argument('--steps', type=int, help='override training steps (growth stop scales with it)')
    p.add_argument('--max-splats', type=int, help='override the splat cap (lower it if memory runs out)')
    p.add_argument('--resolution', type=int, help='override Brush training resolution')
    p.add_argument('--quick', action='store_true', help='smoke test: 4 stations, 300 steps, tiny model; never publishable')
    p.add_argument('--mask-nadir', action='store_true', help='drop downward-looking faces where the camera operator appears')
    p.add_argument('--publish', action='store_true', help='copy results into scan-assets/gaussian/<capture>/ (needs --yes)')
    p.add_argument('--yes', action='store_true', help='confirm the publish checklist')
    p.add_argument('--overwrite', action='store_true', help='allow replacing an already published capture folder')
    p.add_argument('--brush', type=Path, help='use this Brush binary instead of tools/brush/')
    p.add_argument('--output-root', type=Path, default=WORK_ROOT)
    p.add_argument('--resume', type=Path, help='re-use a previous run folder, skipping finished stages')
    p.add_argument('--dry-run', action='store_true', help='print resolved settings and exit')
    return p


def validate_args(args, presets, publish_root=PUBLISH_ROOT):
    """Refuse unsafe or contradictory command lines before any expensive work."""
    if args.capture not in presets['captures']:
        raise CliError(f'Unknown capture {args.capture!r}; choose from {sorted(presets["captures"])}')
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
        target = Path(publish_root) / args.capture
        if target.exists() and not args.overwrite:
            raise CliError(f'{target} already exists; add --overwrite to replace published files')
    return args


def publish_checklist(capture, preset, mask_nadir, registration_status):
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
             f'  [ ] Size: files go to scan-assets/gaussian/{capture}/ (git-tracked, public once pushed).']
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


def publish(package_dir, capture, preset, destination_root, overwrite, mask_nadir, quick):
    destination = Path(destination_root) / capture
    if destination.exists() and not overwrite:
        raise CliError(f'{destination} already exists; add --overwrite')
    manifest = json.loads((package_dir / 'viewer.json').read_text())
    manifest['capture'] = capture
    manifest['building'] = preset['building']
    manifest['publication'] = (f'Published {datetime.now(timezone.utc).date().isoformat()} from scripts/run_gaussian_pipeline.py'
                               f'{" with nadir faces masked" if mask_nadir else ""}. Experimental appearance layer; '
                               'not surveyed geometry; see provenance.pipeline for settings and held-out metrics.')
    destination.mkdir(parents=True, exist_ok=True)
    for name in (manifest['file'], manifest['mobileFile']):
        shutil.copyfile(package_dir / name, destination / name)
    (destination / 'viewer.json').write_text(json.dumps(manifest, indent=2))
    return destination


# ---------------------------------------------------------------- main

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    presets = load_presets()
    preset_ok = presets['captures'].get(args.capture)
    if args.publish and preset_ok:
        print(publish_checklist(args.capture, preset_ok, args.mask_nadir, registration_status(preset_ok)))
    try:
        validate_args(args, presets)
    except CliError as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    preset = presets['captures'][args.capture]
    settings = build_settings(preset, presets['quick'], args.quick, args.steps, args.max_splats, args.resolution)
    settings['maskNadir'] = args.mask_nadir
    if args.dry_run:
        print(json.dumps({'capture': args.capture, 'settings': settings}, indent=2))
        return 0

    started = datetime.now(timezone.utc)
    stamp = started.strftime('%Y%m%dT%H%M%SZ')
    folder = args.resume.resolve() if args.resume else (args.output_root / args.capture / stamp).resolve()
    run = Run(folder)
    run.state.update(capture=args.capture, argv=argv, settings=settings)
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
                                           p['pointCount'], p['seedUpAxis'], args.mask_nadir, p['maxStations'])
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
                                          tr['checkpointEvery'], tr['refineEvery'], tr['growthStop'], tr['shDegree'], stream=True)
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
            capture=args.capture, preset=preset, settings=settings, quick=args.quick, mask_nadir=args.mask_nadir,
            argv=argv, input_hashes=input_hashes, tools=tool_versions(brush, record.get('executableSha256')),
            timings=timings, started_at=run.state['startedAt'], ended_at=datetime.now(timezone.utc).isoformat(),
            metrics=metrics, dataset_report=dataset_report, steps=settings['train']['steps'])
        viewer = json.loads((package_dir / 'viewer.json').read_text())
        viewer['capture'], viewer['building'] = extra['capture'], extra['building']
        viewer['provenance']['validation'] = extra['validation']
        viewer['provenance']['pipeline'] = extra['pipeline']
        viewer['provenance']['selectionStatus'] = ('Smoke test only; not a usable reconstruction.' if args.quick else
                                                   'Local run from the one-command pipeline; not yet reviewed or selected.')
        (package_dir / 'viewer.json').write_text(json.dumps(viewer, indent=2))
        run.mark('package', 'done', timings['package'])
    except KeyboardInterrupt:
        print(f'\nInterrupted. Finished stages are kept in {folder}.\n'
              f'Resume (skips finished stages; training restarts from step 0): '
              f'python scripts/run_gaussian_pipeline.py {" ".join(a for a in argv if a != "--resume")} --resume "{folder}"', file=sys.stderr)
        return 130
    except Exception as error:
        print(f'\nFailed: {error}\nFinished stages are kept in {folder}. After fixing the cause, re-run with --resume "{folder}".', file=sys.stderr)
        return 1

    run.state['endedAt'] = datetime.now(timezone.utc).isoformat()
    run.save()
    print(f'\nDone. Eval PSNR {metrics["psnr"]} SSIM {metrics["ssim"]}. Results: {package_dir}')
    print(f'Preview: python scripts/preview_gaussian.py --capture {args.capture}')
    if args.publish:
        destination = publish(package_dir, args.capture, preset, PUBLISH_ROOT, args.overwrite, args.mask_nadir, args.quick)
        print(f'Published to {destination}. Review `git status`, then commit deliberately.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
