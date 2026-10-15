"""Serve the repo locally and print viewer URLs for a locally trained Gaussian run.

    python scripts/preview_gaussian.py --capture 2026-09-17 [--run work/gaussian/2026-09-17/<stamp>] [--port 8000]

Serves 127.0.0.1 only. Stop with Ctrl+C.
"""
import argparse
import functools
import http.server
import socketserver
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
WORK_ROOT = ROOT / 'work' / 'gaussian'


def latest_run(capture, work_root=WORK_ROOT):
    """Newest run folder (timestamps sort lexically) that has a packaged viewer.json."""
    runs = sorted(p for p in (Path(work_root) / capture).glob('*') if (p / 'package' / 'viewer.json').is_file())
    return runs[-1] if runs else None


def preview_urls(manifest_relative, port):
    """Viewer URLs for a manifest path relative to the repo root."""
    encoded = quote(Path(manifest_relative).as_posix(), safe='')
    base = f'http://localhost:{port}'
    return {'splat': f'{base}/scan-splat.html?manifest={encoded}',
            'compare': f'{base}/scan-compare.html?mode=splat&manifest={encoded}'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--capture', required=True)
    p.add_argument('--run', type=Path, help='run folder (default: newest for the capture)')
    p.add_argument('--port', type=int, default=8000)
    a = p.parse_args(argv)
    run = a.run.resolve() if a.run else latest_run(a.capture)
    if run is None or not (run / 'package' / 'viewer.json').is_file():
        print(f'No packaged run found for {a.capture}. Train first (see docs/GAUSSIAN_TRAINING_GUIDE.md).', file=sys.stderr)
        return 1
    urls = preview_urls((run / 'package' / 'viewer.json').relative_to(ROOT), a.port)
    print(f'Run: {run}\nGaussian layer alone  : {urls["splat"]}\n'
          f'Scan-compare splat mode: {urls["compare"]}\n'
          '  (compare mode uses the May 6 registration; for other captures prefer the standalone layer)\n'
          'Ctrl+C to stop.', flush=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(('127.0.0.1', a.port), handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\nStopped.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
