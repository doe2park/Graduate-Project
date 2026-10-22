#!/usr/bin/env python3
"""Serve this repository read-only over private-LAN HTTPS so Quest Browser can open scan-xr.html (WebXR needs a
secure context). Modelled on the workshop kit's https/start_https.py.

- Binds only to the Mac's private RFC1918 IPv4 address (or 127.0.0.1 with --local). No public tunnel, no router,
  firewall or trust-store changes.
- Self-signed 30-day development certificate under work/quest-https/ (gitignored); reused while valid for the address.
- GET/HEAD only, no directory listings, no uploads. Only public site file types are served; dot-paths (.git, .env,
  .github-token ...), work/, capture-local/, node_modules/, tools/, target/, logs/ and private exports are refused,
  and every path must resolve inside the repository (symlink escapes refused).

- Opt-in (2026-10-19): --gaussian-package work/gaussian/<capture>/<zone>/<run>/package additionally serves exactly that one
  local, unpublished Gaussian package (viewer.json, *.ksplat, *.ply directly inside it) for scan-xr.html?gaussian=...
  Nothing else under work/ (certificate, key, other runs) becomes reachable.

Usage:  python3 scripts/serve_quest_https.py            # prints https://<private-ip>:8929/scan-xr.html
        python3 scripts/serve_quest_https.py --dry-run  # address + certificate only, no server
        python3 scripts/serve_quest_https.py --gaussian-package work/gaussian/2026-10-18/l1-a/<run>/package
Ctrl+C stops the server.
"""
import argparse
import hashlib
import ipaddress
import os
import ssl
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parent.parent
CERT_DIR = REPO / 'work' / 'quest-https'
PORT = 8929
PRIVATE_NETWORKS = [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
ALLOWED_SUFFIXES = {'.html', '.js', '.mjs', '.css', '.json', '.glb', '.bin', '.jpg', '.jpeg', '.png', '.webp', '.svg',
                    '.ico', '.ksplat', '.ply', '.wasm', '.pdf', '.txt'}
DENIED_TOP = {'work', 'capture-local', 'node_modules', 'tools', 'target', 'logs', 'raw_csv', 'Claude outputs', 'legacy',
              'worker', 'scripts', 'tests', 'scans'}
DENIED_NAMES = {'.env', '.github-token'}
GAUSSIAN_PACKAGE_ROOT = ('work', 'gaussian')
GAUSSIAN_PACKAGE_SUFFIXES = {'.json', '.ksplat', '.ply'}


def gaussian_package(root, value):
    """Resolve an opt-in local Gaussian package directory: must be a real directory under work/gaussian/ with a viewer.json."""
    root = Path(root).resolve()
    candidate = Path(value)
    target = (candidate if candidate.is_absolute() else root / candidate).resolve()
    base = root.joinpath(*GAUSSIAN_PACKAGE_ROOT)
    if not target.is_relative_to(base) or target == base or not target.is_dir() or not (target / 'viewer.json').is_file():
        raise ValueError('--gaussian-package must be a package directory with viewer.json under work/gaussian/')
    if any(p.startswith('.') for p in target.relative_to(root).parts):
        raise ValueError('--gaussian-package must not contain dot-directories')
    return target


def is_private(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.version == 4 and any(ip in n for n in PRIVATE_NETWORKS)


def servable(root, url_path, packages=()):
    """Return the resolved file for a URL path, or None when it must not be served.
    `packages`: resolved opt-in Gaussian package directories (see gaussian_package); only files directly inside them."""
    path = unquote(urlsplit(url_path).path)
    if not path.startswith('/') or '\x00' in path or '\\' in path:
        return None
    if path.endswith('/'):
        path += 'index.html'
    parts = [p for p in path.split('/') if p]
    if not parts or any(p in ('.', '..') or p.startswith('.') for p in parts):
        return None
    if parts[-1] in DENIED_NAMES:
        return None
    if parts[0] in DENIED_TOP:
        return _package_file(root, parts, packages)
    name = parts[-1].lower()
    if name.endswith(('.patch', '.lock', '.pem', '.key')) or name.startswith('claude-inbox'):
        return None
    if Path(name).suffix not in ALLOWED_SUFFIXES:
        return None
    root = Path(root).resolve()
    target = (root / Path(*parts)).resolve()
    if not target.is_file() or not target.is_relative_to(root):
        return None
    if any(p.startswith('.') for p in target.relative_to(root).parts):
        return None
    return target


def _package_file(root, parts, packages):
    if not packages or tuple(parts[:2]) != GAUSSIAN_PACKAGE_ROOT or Path(parts[-1]).suffix.lower() not in GAUSSIAN_PACKAGE_SUFFIXES:
        return None
    root = Path(root).resolve()
    target = (root / Path(*parts)).resolve()
    if not target.is_file() or target.parent not in {Path(p).resolve() for p in packages}:
        return None
    return target


def handler_for(root, packages=()):
    class Handler(SimpleHTTPRequestHandler):
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript', '.js': 'text/javascript',
                          '.glb': 'model/gltf-binary', '.wasm': 'application/wasm', '.ksplat': 'application/octet-stream',
                          '.ply': 'application/octet-stream'}

        def send_head(self):
            path = unquote(urlsplit(self.path).path)
            if path in ('/', '/index.html'):
                self.send_response(302); self.send_header('Location', '/scan-xr.html'); self.send_header('Content-Length', '0'); self.end_headers()
                return None
            target = servable(root, self.path, packages)
            if target is None:
                self.send_error(404, 'Not available')
                return None
            f = target.open('rb')
            self.send_response(200)
            self.send_header('Content-Type', self.guess_type(str(target)))
            self.send_header('Content-Length', str(target.stat().st_size))
            self.end_headers()
            return f

        def list_directory(self, path):
            self.send_error(404, 'Not available')

        def do_POST(self):  # read-only origin
            self.send_error(405, 'Read-only')
        do_PUT = do_DELETE = do_PATCH = do_POST

        def end_headers(self):
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Robots-Tag', 'noindex, nofollow, noarchive')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Permissions-Policy', 'xr-spatial-tracking=(self)')
            super().end_headers()

        def log_message(self, fmt, *args):  # quiet: only errors
            if args and str(args[1]).startswith(('4', '5')):
                super().log_message(fmt, *args)
    return Handler


def private_ip():
    route = subprocess.run(['/sbin/route', '-n', 'get', 'default'], capture_output=True, text=True).stdout
    iface = next((l.split(':', 1)[1].strip() for l in route.splitlines() if l.strip().startswith('interface:')), 'en0')
    for name in dict.fromkeys([iface, 'en0', 'en1']):
        out = subprocess.run(['/usr/sbin/ipconfig', 'getifaddr', name], capture_output=True, text=True).stdout.strip()
        if is_private(out):
            return out
    raise RuntimeError('No private LAN IPv4 address found. Connect the Mac to the same Wi-Fi as the Quest.')


def ensure_certificate(address):
    os.umask(0o077)
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    cert, key, cnf = CERT_DIR / 'certificate.pem', CERT_DIR / 'private-key.pem', CERT_DIR / 'openssl.cnf'
    if cert.is_file() and key.is_file():
        fresh = subprocess.run(['/usr/bin/openssl', 'x509', '-in', str(cert), '-checkend', '86400', '-noout'], capture_output=True).returncode == 0
        text = subprocess.run(['/usr/bin/openssl', 'x509', '-in', str(cert), '-text', '-noout'], capture_output=True, text=True).stdout
        if fresh and f'IP Address:{address}' in text:
            return cert, key
    cnf.write_text('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=Grimes Quest XR local development\n'
                   f'[ext]\nsubjectAltName=IP:{address},DNS:localhost,IP:127.0.0.1\nbasicConstraints=critical,CA:FALSE\n'
                   'keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
    r = subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-sha256', '-nodes', '-days', '30',
                        '-keyout', str(key), '-out', str(cert), '-config', str(cnf)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return cert, key


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=PORT)
    p.add_argument('--local', action='store_true', help='bind 127.0.0.1 instead of the private LAN address (desktop check)')
    p.add_argument('--dry-run', action='store_true', help='resolve the address and certificate, then exit')
    p.add_argument('--gaussian-package', action='append', default=[], metavar='DIR',
                   help='also serve this one local Gaussian package (work/gaussian/.../package) for scan-xr.html?gaussian=')
    a = p.parse_args(argv)
    try:
        packages = tuple(gaussian_package(REPO, v) for v in a.gaussian_package)
    except ValueError as e:
        raise SystemExit(str(e))
    address = '127.0.0.1' if a.local else private_ip()
    if not a.local and not is_private(address):
        raise SystemExit('Refusing to bind a non-private address: ' + address)
    cert, key = ensure_certificate(address)
    fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
    url = f'https://{address}:{a.port}/scan-xr.html'
    print(f'Quest XR overlay: {url}\nCertificate (self-signed, dev only): {cert.relative_to(REPO)} sha256 {fingerprint[:16]}…', flush=True)
    for pkg in packages:
        rel = pkg.relative_to(REPO).as_posix()
        print(f'Local Gaussian (unpublished, experimental appearance): {url}?scene=gaussian&gaussian={rel}/viewer.json', flush=True)
    if a.dry_run:
        return 0
    server = ThreadingHTTPServer((address, a.port), handler_for(REPO, packages))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert, key)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    print('Same Wi-Fi required (no client isolation). Accept the certificate warning only for this exact address. Ctrl+C stops.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
