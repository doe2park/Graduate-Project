"""One command: raw Insta360 ONE X2 INSV recordings of Grimes Level 2 / Level 3 -> per-floor local preview packages
registered to the BIM, with no Cupix input.

    python3 scripts/capture_upper_floors.py --date 2026-10-28 "/Users/yschung/Desktop/Research stuff/Raw Data/Insta 360 X2 Scan/VID_20261028_..._00_NNN.insv"
    # then: python3 -m http.server 8893  and open  http://localhost:8893/scan-compare.html?capture=2026-10-28&floors=L2  (or L3, L1)

Per INSV (work/raw360/<date>/<tag>/, tag = the INSV number):
    probe -> frames -> sfm (strict incremental, fisheye rig) -> dump -> anchor (photo links to registered Level 1
    panoramas + between SfM submodels) -> place (scale from camera height, trimmed ICP to BIM, checks) -> privacy (blur)
then for the whole day: package (capture-local/grimes-L1|L2|L3-<date>/, grimes-UPPER-<date>/) and optionally the
Gaussian (--gaussian: adds the preset '<date>-upper' to scripts/gaussian_presets.json and trains it).

Stages whose output already exists are skipped (re-run after fixing something; --redo STAGE forces one stage and the
ones after it). The run report (work/raw360/<date>/run-report.json) records every stage, its time and key metrics;
on failure the runner stops with the failed stage, the last log lines and what to do next. Raw INSV files are read
only. Interpreters: work/raw360-venv (pycolmap, OpenCV) for SfM/photo stages, system python3 (SciPy) for BIM stages,
.venv-gaussian for the Gaussian.  Results are provisional, not surveyed.
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / 'work/raw360-venv/bin/python'
SYS = sys.executable
GAUSS = ROOT / '.venv-gaussian/bin/python'
MODELS = ROOT / 'work/raw360-models'
FFPROBE = shutil.which('ffprobe') or '/opt/homebrew/bin/ffprobe'
STAGES = ['probe', 'frames', 'sfm', 'dump', 'anchor', 'place', 'privacy', 'package', 'validate', 'gaussian']
DUAL_STREAM_FOV = 196.6
DUAL_STREAM_FOV_SOURCE = ('Sep 17 X2 trailer Mei-model fit (196.6 deg); the Oct 2026 single-file recordings carry a photo-mode '
                          'calibration in the trailer, so it is not used')


def now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def insv_tag(path):
    m = re.search(r'_(\d+)\.insv$', Path(path).name, re.I)
    return m.group(1) if m else Path(path).stem[-8:]


def recording_info(path):
    """Streams, frames and the real recording duration (file name start time -> file modification time)."""
    info = json.loads(subprocess.run([FFPROBE, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)],
                                     capture_output=True, text=True, check=True).stdout)
    v = [s for s in info['streams'] if s['codec_type'] == 'video']; au = [s for s in info['streams'] if s['codec_type'] == 'audio']
    frames = int(v[0].get('nb_frames') or 0) if v else 0
    real = None; m = re.search(r'VID_(\d{8})_(\d{6})', Path(path).name)
    if m:
        start = datetime.datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S').timestamp(); real = os.path.getmtime(path) - start
    return {'videoStreams': len(v), 'audio': bool(au), 'frames': frames, 'playbackSeconds': float(info['format'].get('duration', 0)),
            'realSecondsFromNameAndMtime': real}


def frame_plan(rec, frame_interval=None, seconds_per_keyframe=1.5):
    """Keyframe count and gap guards in frames, from the real frame rate. Time-lapse files (no audio) hold one frame per
    interval (Oct 18: 0.5 s); normal video ~30 fps. The file-name start + modification time cross-checks it when plausible."""
    frames = rec['frames']; real = rec['realSecondsFromNameAndMtime']
    if frame_interval:
        rate, how = 1.0 / frame_interval, 'given --frame-interval %.3f s' % frame_interval
    elif rec['audio']:
        rate, how = frames / rec['playbackSeconds'] if rec['playbackSeconds'] else 29.97, 'normal video (audio track): playback frame rate'
    else:
        rate, how = 2.0, 'time-lapse (no audio track): 0.5 s interval assumed (Oct 18 setting)'
        if real and 30 < real < 4 * 3600 and 0.2 < frames / real < 10:
            rate, how = frames / real, 'time-lapse: frames / (modification time - start time in the file name)'
    seconds = frames / rate
    count = int(min(700, max(40, round(seconds / seconds_per_keyframe))))
    return {'framesPerRealSecond': rate, 'basis': how, 'walkSeconds': seconds, 'count': count,
            'maxGap': max(2, int(round(3.0 * rate))), 'minGap': max(1, int(round(1.0 * rate)))}


class Runner:
    def __init__(self, a):
        self.a = a; self.root = ROOT / 'work/raw360' / a.date; self.root.mkdir(parents=True, exist_ok=True)
        self.report_path = self.root / 'run-report.json'
        self.report = {'schema': 'capture-upper-floors-run/1', 'date': a.date, 'started': now(), 'label': 'provisional, not surveyed',
                       'inputs': [str(Path(p).resolve()) for p in a.insv], 'cameraHeightMetres': a.camera_height, 'stages': [], 'videos': {}}
        self.redo = STAGES.index(a.redo) if a.redo else len(STAGES)

    def save(self):
        self.report['updated'] = now(); self.report_path.write_text(json.dumps(self.report, indent=1))

    def fail(self, stage, msg, log=None, hint=None):
        tail = Path(log).read_text(errors='replace').splitlines()[-25:] if log and Path(log).exists() else []
        self.report.update(status='failed', failedStage=stage, error=msg, logTail=tail, nextStep=hint); self.save()
        print('\n' + '=' * 78 + f'\nFAILED at stage "{stage}": {msg}')
        if tail: print('--- last log lines (%s) ---\n%s' % (log, '\n'.join(tail)))
        if hint: print('--- what to do ---\n' + hint)
        print('Report: %s\n' % self.report_path + '=' * 78); sys.exit(1)

    def run(self, stage, cmd, log, done_marker=None, hint=None, video=None):
        idx = STAGES.index(stage)
        if done_marker is not None and Path(done_marker).exists() and idx < self.redo:
            print(f'[{now()}] {stage}{" " + video if video else ""}: done earlier ({done_marker}), skipped'); return 0.0
        if self.a.dry_run:
            print('DRY', ' '.join(map(str, cmd))); return 0.0
        print(f'[{now()}] {stage}{" " + video if video else ""}: running (log {log})', flush=True)
        t0 = time.time()
        with open(log, 'w') as fh:
            fh.write('$ ' + ' '.join(map(str, cmd)) + '\n'); fh.flush()
            r = subprocess.run([str(c) for c in cmd], cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, env={**os.environ, 'PYTHONWARNINGS': 'ignore'})
        dt = time.time() - t0
        self.report['stages'].append({'stage': stage, 'video': video, 'seconds': round(dt, 1), 'exit': r.returncode, 'log': str(log)}); self.save()
        if r.returncode:
            self.fail(stage + (' ' + video if video else ''), f'exit code {r.returncode}', log, hint)
        print(f'[{now()}] {stage}{" " + video if video else ""}: ok in {dt:.0f} s', flush=True)
        return dt

    def video(self, insv):
        a = self.a; tag = insv_tag(insv); W = self.root / tag; W.mkdir(parents=True, exist_ok=True); logs = W / 'logs'; logs.mkdir(exist_ok=True)
        V = self.report['videos'].setdefault(tag, {'insv': str(Path(insv).resolve()), 'work': str(W)})
        rec = recording_info(insv); plan = frame_plan(rec, a.frame_interval); V.update(recording=rec, framePlan=plan)
        if a.count: plan['count'] = a.count
        companion = Path(str(insv).replace('_00_', '_10_'))
        if rec['videoStreams'] >= 2:
            probe = ['--dual-stream', insv, '--lens-ops', 'none,none', '--fov', DUAL_STREAM_FOV, '--fov-source', DUAL_STREAM_FOV_SOURCE]
        elif '_00_' in Path(insv).name and companion.exists():
            probe = ['--front', insv, '--back', companion]
        else:
            self.fail('probe ' + tag, f'{insv}: one video stream and no _10_ companion file; copy both lens files (or the single _00_ file of a newer recording)')
        P = [VENV, 'scripts/raw360_pipeline.py']; B = [SYS, 'scripts/raw360_bim.py']; M = 'colmap-incremental'
        self.run('probe', P + ['probe', '--work', W] + probe, logs / 'probe.log', W / 'probe.json', video=tag,
                 hint='Check the file is a complete INSV copy (sha256 in the copy log) and ffprobe can read it.')
        self.run('frames', P + ['frames', '--work', W, '--count', plan['count'], '--max-gap', plan['maxGap'], '--min-gap', plan['minGap'],
                                '--motion-cue', 'image', '--view-mode', 'fisheye-rig'], logs / 'frames.log', W / 'frames.json', video=tag,
                 hint='Disk space (df -h), or a corrupt/partial INSV. Re-run the same command after fixing; finished stages are skipped.')
        self.run('sfm', P + ['sfm', '--work', W, '--method', M, '--overlap', 6, '--loops', 3, '--dsp', '--max-runtime', 1800],
                 logs / 'sfm.log', W / 'sfm' / M / 'sfm-result.json', video=tag,
                 hint='SfM failed to start a model: too dark / too fast / too few keyframes. Try --count larger (e.g. 1.5x) with --redo frames.')
        res = json.loads((W / 'sfm' / M / 'sfm-result.json').read_text()) if (W / 'sfm' / M / 'sfm-result.json').exists() else {}
        V['sfm'] = {k: res.get(k) for k in ('models', 'registeredPanoramas', 'totalPanoramas', 'meanReprojectionErrorPx', 'seconds')}
        self.run('dump', [VENV, 'scripts/raw360_bim.py', 'dump', '--work', W, '--method', M], logs / 'dump.log', W / 'sfm' / M / 'submodels/index.json', video=tag)
        self.run('anchor', [VENV, 'scripts/raw360_bim.py', 'anchor', '--work', W, '--method', M], logs / 'anchor.log', W / f'anchors-{M}.json', video=tag,
                 hint='Photo matching failed (OpenCV in work/raw360-venv?).')
        placed = W / 'placed-bim.json'
        extra = ['--accept-unlinked'] if a.accept_unlinked else []
        self.run('place', B + ['place', '--work', W, '--method', M, '--camera-height', a.camera_height, '--height-source', a.height_source,
                               '--overwrite'] + extra, logs / 'place.log', placed, video=tag,
                 hint='No SfM part could be tied to the BIM without Cupix. Usual cause: the walk has no photo link to a registered Level 1 '
                      'panorama (did it start at the atrium stair foot / a Level 1 station?) and the SfM broke on the stairs. Options: '
                      '(1) inspect work/.../placed-bim.json "models" (reasons per part); (2) --accept-unlinked to keep global-search '
                      'candidates for a visual check only; (3) upload the INSV to Cupix as before (fallback) and use the Cupix route.')
        P_ = json.loads(placed.read_text()) if placed.exists() else {}
        V['placement'] = {'summary': P_.get('summary'), 'bridgeCheckSummary': P_.get('bridgeCheckSummary'),
                          'models': [{k: m.get(k) for k in ('model', 'frames', 'frameRange', 'status', 'reasons')} |
                                     {kk: (m.get('checks') or {}).get(kk) for kk in ('heldOut', 'cameraAboveBimFloor', 'freeSightLines', 'scaleChange',
                                                                                     'impliedCameraHeightMetres', 'stationsInWalls', 'framesFlaggedByVisibility')} |
                                     {'seed': (m.get('chosenHypothesis') or {}).get('source'), 'cameraHeightScale': m.get('cameraHeightScale')}
                                     for m in P_.get('models', [])]}
        self.save()
        # privacy on the placed panoramas only (symlinks; the work panoramas stay untouched)
        pp = W / 'placed-panos'; blurred = W / 'blurred'
        if STAGES.index('privacy') >= self.redo or not (blurred / 'privacy-report.json').exists():
            shutil.rmtree(blurred, ignore_errors=True)
            if not a.dry_run:   # rebuilt from the current placement every time privacy runs
                shutil.rmtree(pp, ignore_errors=True); pp.mkdir()
                for st in P_.get('stations', []):
                    os.symlink(os.path.join('..', 'panos', st['pano']), pp / st['pano'])
        self.run('privacy', P + ['privacy', '--in', pp, '--out', blurred, '--face-model', MODELS / 'face_detection_yunet_2023mar.onnx',
                                 '--person-model', MODELS / 'object_detection_yolox_2022nov.onnx'], logs / 'privacy.log', blurred / 'privacy-report.json', video=tag,
                 hint='Privacy models missing? They live in work/raw360-models (see docs/RAW360_PIPELINE.md, "Models").')
        if (blurred / 'privacy-report.json').exists():
            pr = json.loads((blurred / 'privacy-report.json').read_text())
            V['privacy'] = {k: pr.get(k) for k in ('imagesProcessed', 'totals', 'flaggedImages', 'manualReviewRequired', 'runtimeSeconds')}
        self.save()
        return tag, placed, blurred

    def go(self):
        a = self.a
        for p in a.insv:
            if not Path(p).is_file():
                self.fail('inputs', f'{p} not found')
        for exe in (VENV,):
            if not exe.exists():
                self.fail('inputs', f'{exe} missing (python3 -m venv work/raw360-venv; pip install pycolmap numpy pillow opencv-python-headless)')
        free = shutil.disk_usage(ROOT).free / 1e9; self.report['diskFreeGBAtStart'] = round(free, 1)
        if free < 5:
            self.fail('inputs', f'only {free:.1f} GB free; need ~2-5 GB per recording')
        vids = [self.video(p) for p in a.insv]
        floors = {f: ROOT / 'capture-local' / f'grimes-{f}-{a.date}' for f in ('L1', 'L2', 'L3')}
        upper = ROOT / 'capture-local' / f'grimes-UPPER-{a.date}'
        if STAGES.index('package') >= self.redo:
            for d in list(floors.values()) + [upper]:
                if d.exists():
                    shutil.rmtree(d)
        summary = self.root / 'package-summary.json'
        marker = summary if any(d.exists() for d in floors.values()) else None
        self.run('package', [SYS, 'scripts/raw360_bim.py', 'package', '--date', a.date, '--placed'] + [v[1] for v in vids] +
                 ['--blurred'] + [v[2] for v in vids] + ['--tag'] + [v[0] for v in vids] + ['--upper-out', upper, '--summary', summary],
                 self.root / 'package.log', marker, hint='See the log; packages are never overwritten (use --redo package).')
        self.report['packages'] = json.loads(summary.read_text()) if summary.exists() else None
        self.report['open'] = ['http://localhost:8893/scan-compare.html?capture=%s&floors=%s' % (a.date, f) for f, d in floors.items() if d.exists()]
        if a.validate_against:
            out = self.root / 'validation.json'
            self.run('validate', [SYS, 'scripts/raw360_bim.py', 'compare', '--placed', vids[0][1], '--reference'] + a.validate_against +
                     ['--out', out, '--reference-note', 'validation only'], self.root / 'validate.log', None)
            v = json.loads(out.read_text()); self.report['validation'] = {k: v.get(k) for k in ('common', 'distance', 'horizontal', 'vertical', 'headingAbs', 'perModel', 'placedOnly', 'referenceOnly')}
        if a.gaussian and upper.exists():
            self.gaussian(upper)
        self.report.update(status='ok', finished=now()); self.save()
        print('\n' + '=' * 78 + '\nDone. Report: %s' % self.report_path)
        for v in self.report['videos'].values():
            s = (v.get('placement') or {}).get('summary') or {}
            print('  %s: placed %s / %s keyframes %s; parts not placed: %s' % (Path(v['insv']).name, s.get('placed'), s.get('keyframes'), s.get('levels'),
                  [(x['model'], x['frames']) for x in s.get('submodelsNotPlaced', [])]))
        print('Serve the repo (python3 -m http.server 8893) and open:\n  ' + '\n  '.join(self.report['open']))
        print('Privacy: blurred automatically; review every panorama before sharing anything. Provisional, not surveyed.\n' + '=' * 78)

    def gaussian(self, upper):
        a = self.a; key = f'{a.date}-upper'; presets_path = ROOT / 'scripts/gaussian_presets.json'
        presets = json.loads(presets_path.read_text()); m = json.loads((upper / 'panoramas/manifest.json').read_text())
        if key not in presets['captures']:
            presets['captures'][key] = {
                'building': 'grimes', 'label': f'Levels 2-3 + stairs, {a.date} raw INSV (Cupix-free placement; local, unpublished)',
                'manifest': str((upper / 'panoramas/manifest.json').relative_to(ROOT)), 'registration': str((upper / 'registration.json').relative_to(ROOT)),
                'seedGlbs': [], 'centerId': m['defaultStation'], 'radius': 60, 'size': 768, 'pointCount': 150000, 'seedUpAxis': 'z',
                'train': {'steps': 30000, 'maxSplats': 1000000, 'resolution': 768, 'checkpointEvery': 5000, 'refineEvery': 400, 'growthStop': 15000, 'shDegree': 2},
                'mobileBudget': 350000,
                'notes': f'Added by scripts/capture_upper_floors.py on {now()}. Blurred panoramas (automatic, manual review pending), BIM-frame poses '
                         '(identity registration), no seed mesh. Provisional, not surveyed; never publish. Use --mask-nadir.'}
            presets_path.write_text(json.dumps(presets, indent=2) + '\n')
        if not GAUSS.exists():
            self.fail('gaussian', f'{GAUSS} missing (python3 scripts/setup_gaussian_env.py)')
        self.run('gaussian', [GAUSS, 'scripts/run_gaussian_pipeline.py', '--capture', key, '--mask-nadir'], self.root / 'gaussian.log', None,
                 hint='Gaussian training is optional; the photo packages are already usable.')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('insv', nargs='+', help='_00_ INSV file(s) of the capture day (one per recording)')
    ap.add_argument('--date', required=True, help='capture label, e.g. 2026-10-28 (letters/digits/dash after the date allowed)')
    ap.add_argument('--camera-height', type=float, default=2.0, help='camera (lens) height above the floor, m (stick held at about 2.0 m)')
    ap.add_argument('--height-source', default='owner: stick held at about 2.0 m (Oct 18 data: 1.97-2.07 m implied); not taped')
    ap.add_argument('--frame-interval', type=float, help='time-lapse interval in seconds when known (default 0.5 s, or from the file times)')
    ap.add_argument('--count', type=int, help='override the keyframe count per recording')
    ap.add_argument('--accept-unlinked', action='store_true', help='also accept SfM parts placed without a photo link (risky; visual check required)')
    ap.add_argument('--validate-against', nargs='+', help='reference package folder(s) for a validation-only comparison (e.g. Cupix-based)')
    ap.add_argument('--gaussian', action='store_true', help='also add a Gaussian preset and train the upper floors (long; heavy)')
    ap.add_argument('--redo', choices=STAGES, help='force this stage and every later one')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}(-[a-z0-9]{1,24})?', a.date):
        raise SystemExit('--date must look like 2026-10-28 or 2026-10-28-test')
    Runner(a).go()


if __name__ == '__main__':
    main()
