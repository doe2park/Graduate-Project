#!/usr/bin/env python3
"""Put a finished Gaussian zone run onto the LOCAL web viewer (scan-assets/gaussian/<capture>/zones/).

    python3 scripts/publish_local_zone.py --capture 2026-10-18 --zone l1-c [--run <folder>] [--alignment LABEL]

Without --run it uses the newest run folder under work/gaussian/<capture>/<zone>/ whose run.json has every stage
done and which is not a --quick smoke test. It calls run_gaussian_pipeline.publish() with overwrite=True, the
nadir-mask flag recorded in the run, and the zone context from scripts/gaussian_zones.json.

Alignment label (never silently changed): --alignment, else the alignment already in the capture's
zones/index.json, else status in scan-assets/captures/<capture>/registration.json. If none exists the script stops.
Superseded presets are refused. scan-assets/gaussian/2026-10-18/ is local-only (.git/info/exclude): nothing here
publishes to the site; this script never runs git.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import run_gaussian_pipeline as rgp  # noqa: E402

STAGES = ('prepare', 'train', 'encode', 'package')
URL = 'http://127.0.0.1:8790/scan-compare.html?capture={capture}&mode=splat'


class PublishError(Exception):
    pass


def refuse_superseded(preset, capture):
    if str(preset.get('notes', '')).lstrip().upper().startswith('SUPERSEDED'):
        raise PublishError(f'preset {capture} is SUPERSEDED ({preset["notes"][:80]}...); refusing to publish it')


def _load_state(folder):
    try:
        return json.loads((folder / 'run.json').read_text())
    except (OSError, ValueError):
        return None


def run_is_publishable(state):
    """All four stages done and not a --quick smoke test."""
    if not state:
        return False
    stages = state.get('stages', {})
    if not all(stages.get(s, {}).get('status') == 'done' for s in STAGES):
        return False
    return '--quick' not in (state.get('argv') or [])


def find_latest_run(output_root, capture, zone_id):
    root = Path(output_root) / capture / zone_id
    if not root.is_dir():
        raise PublishError(f'no runs under {root}')
    for folder in sorted((d for d in root.iterdir() if d.is_dir()), reverse=True):
        if run_is_publishable(_load_state(folder)) and (folder / 'package' / 'viewer.json').is_file():
            return folder
    raise PublishError(f'no finished, non-quick run with a package under {root}')


def resolve_alignment(explicit, publish_root, capture, captures_root):
    """explicit > existing zones/index.json > site registration.json status. Returns (label, source)."""
    if explicit:
        return explicit, '--alignment'
    index = Path(publish_root) / capture / 'zones' / 'index.json'
    try:
        label = json.loads(index.read_text()).get('alignment')
        if label:
            return label, 'existing zones/index.json'
    except (OSError, ValueError):
        pass
    reg = Path(captures_root) / capture / 'registration.json'
    try:
        label = json.loads(reg.read_text()).get('status')
        if label:
            return label, str(reg.relative_to(rgp.ROOT) if reg.is_relative_to(rgp.ROOT) else reg)
    except (OSError, ValueError):
        pass
    raise PublishError(f'no alignment label for {capture}: pass --alignment (checked {index} and {reg})')


def publish_zone(capture, zone_id, run=None, alignment=None, presets=None, output_root=None, publish_root=None,
                 captures_root=None, zone_loader=None, zones_file=None):
    presets = presets or rgp.load_presets()
    output_root = Path(output_root or rgp.WORK_ROOT)
    publish_root = Path(publish_root or rgp.PUBLISH_ROOT)
    captures_root = Path(captures_root or rgp.ROOT / 'scan-assets' / 'captures')
    preset = presets['captures'].get(capture)
    if not preset:
        raise PublishError(f'unknown capture {capture}')
    refuse_superseded(preset, capture)
    folder = Path(run).resolve() if run else find_latest_run(output_root, capture, zone_id)
    state = _load_state(folder)
    if not run_is_publishable(state):
        raise PublishError(f'{folder} is not a finished non-quick run')
    if state.get('capture') != capture or (state.get('settings', {}).get('zone') or {}).get('id') != zone_id:
        raise PublishError(f'{folder} is not a run of {capture} zone {zone_id}')
    package_dir = folder / 'package'
    if not (package_dir / 'viewer.json').is_file():
        raise PublishError(f'{package_dir}/viewer.json is missing')
    mask_nadir = bool(state['settings'].get('maskNadir', '--mask-nadir' in state.get('argv', [])))
    label, source = resolve_alignment(alignment, publish_root, capture, captures_root)
    loader = zone_loader or rgp.load_zone_context
    zone, geometry = loader(SimpleNamespace(capture=capture, zones_file=zones_file or rgp.gz.ZONES_PATH), presets, zone_id)
    destination = rgp.publish(package_dir, capture, preset, publish_root, True, mask_nadir, False,
                              zone=zone, geometry=geometry, alignment=label)
    return {'destination': destination, 'run': folder, 'alignment': label, 'alignmentSource': source,
            'maskNadir': mask_nadir}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--capture', required=True)
    p.add_argument('--zone', required=True)
    p.add_argument('--run', help='run folder (default: newest finished non-quick run of the zone)')
    p.add_argument('--alignment', help='alignment label; default keeps the existing index label, else the site registration status')
    p.add_argument('--no-hub', action='store_true', help='skip regenerating work/local-test.html')
    args = p.parse_args(argv)
    try:
        result = publish_zone(args.capture, args.zone, args.run, args.alignment)
    except (PublishError, rgp.CliError, OSError, ValueError, KeyError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    print(f'Run: {result["run"]}')
    print(f'Alignment label: {result["alignment"]} (from {result["alignmentSource"]}); nadir masked: {result["maskNadir"]}')
    print(f'Published to {result["destination"]} (overwrite).')
    print('LOCAL ONLY: scan-assets/gaussian/2026-10-18/ is excluded via .git/info/exclude; this is not published to the site.'
          if args.capture == '2026-10-18' else
          'Note: this folder is tracked by git; it becomes public only if you commit and push it. Nothing was committed.')
    if not args.no_hub:
        subprocess.run([sys.executable, str(SCRIPTS / 'local_test_hub.py')], check=False)
    print('Open (needs `python3 -m http.server 8790` in the repo root, or the Local test hub task): '
          + URL.format(capture=args.capture))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
