"""Download the official Brush v0.3.0 release for this OS, verify its SHA-256, extract it.

    python scripts/get_brush.py            # prints the binary path on the last line

Binaries go to tools/brush/<target>/ (gitignored). Nothing is committed or vendored.
Source: https://github.com/ArthurBrussee/brush/releases/tag/v0.3.0
"""
import argparse
import hashlib
import platform
import shutil
import stat
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = 'v0.3.0'
BASE_URL = f'https://github.com/ArthurBrussee/brush/releases/download/{VERSION}'
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / 'tools' / 'brush'

# (system, machine) -> (release target, archive extension, binary file name)
TARGETS = {
    ('darwin', 'arm64'): ('aarch64-apple-darwin', 'tar.xz', 'brush_app'),
    ('windows', 'x86_64'): ('x86_64-pc-windows-msvc', 'zip', 'brush_app.exe'),
    ('linux', 'x86_64'): ('x86_64-unknown-linux-gnu', 'tar.xz', 'brush_app'),
}
MACHINE_ALIASES = {'aarch64': 'arm64', 'amd64': 'x86_64', 'x64': 'x86_64'}


def target_for(system=None, machine=None):
    """Map an OS/CPU to (target, extension, binary name); unsupported platforms raise SystemExit."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    machine = MACHINE_ALIASES.get(machine, machine)
    try:
        return TARGETS[(system, machine)]
    except KeyError:
        supported = ', '.join(f'{s}/{m}' for s, m in TARGETS)
        raise SystemExit(f'No official Brush {VERSION} build for {system}/{machine}. Supported: {supported}.')


def asset_urls(target, ext):
    name = f'brush-app-{target}.{ext}'
    return f'{BASE_URL}/{name}', f'{BASE_URL}/{name}.sha256'


def parse_sha256(text):
    """Accept '<hex>  name', '<hex> *name' or a bare '<hex>'."""
    token = text.strip().split()[0].lower() if text.strip() else ''
    if len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
        raise ValueError('Unrecognised SHA-256 file')
    return token


def sha256_of(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(path, expected):
    actual = sha256_of(path)
    if actual != expected:
        raise ValueError(f'SHA-256 mismatch for {Path(path).name}: expected {expected}, got {actual}')
    return actual


def safe_extract(archive, destination):
    """Extract an archive, refusing members that would land outside the destination."""
    destination = Path(destination).resolve()
    archive = Path(archive)
    if archive.suffix == '.zip':
        with zipfile.ZipFile(archive) as zf:
            for name in zf.namelist():
                if not (destination / name).resolve().is_relative_to(destination):
                    raise ValueError(f'Unsafe path in archive: {name}')
            zf.extractall(destination)
    else:
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                if not (destination / member.name).resolve().is_relative_to(destination):
                    raise ValueError(f'Unsafe path in archive: {member.name}')
            tf.extractall(destination, filter='data')


def find_binary(directory, binary_name):
    matches = sorted(Path(directory).rglob(binary_name))
    return matches[0] if matches else None


def download(url, destination):
    request = urllib.request.Request(url, headers={'User-Agent': 'graduate-project-get-brush'})
    with urllib.request.urlopen(request, timeout=60) as response, Path(destination).open('wb') as out:
        shutil.copyfileobj(response, out)


def ensure_brush(dest=DEFAULT_DEST, system=None, machine=None, fetch=download):
    """Return the path of a verified Brush binary, downloading it only when missing."""
    system_name = (system or platform.system()).lower()
    target, ext, binary_name = target_for(system, machine)
    folder = Path(dest) / target
    marker = folder / 'VERIFIED_SHA256'
    if marker.exists():
        existing = find_binary(folder, binary_name)
        if existing:
            return existing
    folder.mkdir(parents=True, exist_ok=True)
    archive_url, sha_url = asset_urls(target, ext)
    archive = folder / archive_url.rsplit('/', 1)[1]
    sha_file = Path(str(archive) + '.sha256')
    print(f'Downloading {archive_url}', flush=True)
    fetch(sha_url, sha_file)
    expected = parse_sha256(sha_file.read_text())
    fetch(archive_url, archive)
    actual = verify(archive, expected)
    print(f'SHA-256 verified: {actual}', flush=True)
    safe_extract(archive, folder)
    binary = find_binary(folder, binary_name)
    if binary is None:
        raise FileNotFoundError(f'{binary_name} not found in {archive.name}')
    if system_name != 'windows':
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if system_name == 'darwin' and shutil.which('codesign'):
        # Apple Silicon refuses unsigned binaries; an ad-hoc local signature is enough.
        subprocess.run(['codesign', '--force', '--sign', '-', str(binary)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    marker.write_text(actual + '\n')
    archive.unlink()
    return binary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dest', type=Path, default=DEFAULT_DEST)
    print(ensure_brush(parser.parse_args().dest))
