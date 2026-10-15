"""One-shot setup for Gaussian training: .venv-gaussian + pinned Python deps, pinned npm encoder, Brush v0.3.0.

    python scripts/setup_gaussian_env.py        # Python 3.11+ (3.12 recommended), Node 22+

Safe to re-run. Creates only gitignored folders (.venv-gaussian/, tools/node_modules/, tools/brush/).
"""
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / '.venv-gaussian'


def venv_python(venv_dir=VENV, windows=None):
    windows = (sys.platform == 'win32') if windows is None else windows
    return Path(venv_dir) / ('Scripts/python.exe' if windows else 'bin/python')


def check_prerequisites(version=None, node_major=None, have_npm=None):
    """Return a list of problems (empty when fine). Arguments let tests avoid a real toolchain."""
    problems = []
    version = version or sys.version_info[:2]
    if tuple(version) < (3, 11):
        problems.append(f'Python 3.11+ required (3.12 recommended); found {version[0]}.{version[1]}')
    if node_major is None:
        node = shutil.which('node')
        if not node:
            problems.append('Node.js 22+ not found (needed for the .ksplat encoder)')
        else:
            out = subprocess.run([node, '--version'], capture_output=True, text=True).stdout.strip().lstrip('v')
            node_major = int(out.split('.')[0]) if out[:1].isdigit() else 0
    if node_major is not None and node_major < 22:
        problems.append(f'Node.js 22+ required; found {node_major}')
    if have_npm is None:
        have_npm = bool(shutil.which('npm'))
    if not have_npm:
        problems.append('npm not found (installed with Node.js)')
    return problems


def main():
    problems = check_prerequisites()
    if problems:
        print('Cannot continue:\n  - ' + '\n  - '.join(problems), file=sys.stderr)
        return 1
    if not VENV.exists():
        print(f'Creating {VENV}')
        venv.EnvBuilder(with_pip=True).create(VENV)
    py = str(venv_python())
    print('Installing pinned Python packages', flush=True)
    subprocess.run([py, '-m', 'pip', 'install', '--quiet', '-r', str(ROOT / 'requirements-gaussian.txt')], check=True)
    print('Installing pinned encoder (gaussian-splats-3d 0.4.7) into tools/node_modules', flush=True)
    subprocess.run([shutil.which('npm'), 'ci', '--no-audit', '--no-fund', '--prefix', str(ROOT / 'tools')], check=True)
    print('Fetching Brush v0.3.0', flush=True)
    subprocess.run([py, str(ROOT / 'scripts' / 'get_brush.py')], check=True)
    print('\nSetup complete. Try the smoke test:\n'
          f'  {py} scripts/run_gaussian_pipeline.py --capture 2026-09-17 --quick')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
