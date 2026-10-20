"""scripts/serve_quest_https.py: read-only allowlist, private-address guard and handler behaviour.
The handler is exercised over plain HTTP on 127.0.0.1 with an ephemeral port (no TLS, no LAN bind, no certificate)."""
import importlib.util
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('serve_quest_https', ROOT / 'scripts' / 'serve_quest_https.py')
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)


class AllowList(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.root = Path(self.tmp.name)
        for rel in ('scan-xr.html', 'twin/xr-core.js', 'twin/xr-spatial-tier.mjs', 'buildings/grimes/grimes-duct.glb',
                    'scan-assets/panoramas/mobile/1.jpg', '.git/config', '.env', '.github-token', 'work/quest-https/private-key.pem',
                    'capture-local/x.jpg', 'node_modules/a/index.js', 'scripts/serve_quest_https.py', 'notes.patch', 'a.lock',
                    'twin/.hidden.js', 'README.md'):
            p = r / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'x')
        outside = Path(self.tmp.name + '-outside.json')
        outside.write_text('{}')
        self.addCleanup(outside.unlink)
        os.symlink(outside, r / 'escape.json')

    def tearDown(self):
        self.tmp.cleanup()

    def test_public_site_files_are_served(self):
        for path in ('/scan-xr.html', '/twin/xr-core.js', '/twin/xr-spatial-tier.mjs', '/buildings/grimes/grimes-duct.glb',
                     '/scan-assets/panoramas/mobile/1.jpg', '/scan-xr.html?capture=2026-09-17'):
            self.assertIsNotNone(srv.servable(self.root, path), path)

    def test_private_and_unsafe_paths_are_refused(self):
        for path in ('/.git/config', '/.env', '/.github-token', '/work/quest-https/private-key.pem', '/capture-local/x.jpg',
                     '/node_modules/a/index.js', '/scripts/serve_quest_https.py', '/notes.patch', '/a.lock', '/twin/.hidden.js',
                     '/README.md', '/../etc/passwd', '/twin/../.git/config', '/%2e%2e/x.json', '/%2egit/config', '/escape.json',
                     '/missing.html', 'scan-xr.html', '/twin/'):
            self.assertIsNone(srv.servable(self.root, path), path)

    def test_only_private_ipv4_addresses(self):
        for a in ('192.168.68.53', '10.0.0.4', '172.20.1.1'):
            self.assertTrue(srv.is_private(a))
        for a in ('8.8.8.8', '127.0.0.1', '0.0.0.0', '172.32.0.1', '::1', '', 'en0'):
            self.assertFalse(srv.is_private(a))

    def test_handler_read_only_no_listing(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), srv.handler_for(self.root))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_address[1]}'
        with urllib.request.urlopen(base + '/scan-xr.html') as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.headers['Permissions-Policy'], 'xr-spatial-tracking=(self)')
            self.assertEqual(r.headers['X-Content-Type-Options'], 'nosniff')
        with urllib.request.urlopen(base + '/twin/xr-spatial-tier.mjs') as r:
            self.assertEqual(r.headers['Content-Type'], 'text/javascript')
        for path in ('/.git/config', '/twin/', '/work/quest-https/private-key.pem'):
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + path)
            self.assertEqual(e.exception.code, 404, path)
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(base + '/scan-xr.html', data=b'x', method='POST'))
        self.assertEqual(e.exception.code, 405)

    def test_opt_in_gaussian_package_serves_only_that_package(self):
        r = self.root
        pkg = r / 'work/gaussian/2026-10-18/l1-a/run1/package'
        other = r / 'work/gaussian/2026-10-18/l1-a/run0/package'
        for d in (pkg, other):
            d.mkdir(parents=True)
            for n in ('viewer.json', 'mobile.ply', 'trained.ksplat'):
                (d / n).write_bytes(b'x')
        (pkg / 'notes.txt').write_bytes(b'x')
        (pkg / 'sub').mkdir()
        (pkg / 'sub/x.json').write_bytes(b'x')
        base = '/work/gaussian/2026-10-18/l1-a/run1/package/'
        self.assertIsNone(srv.servable(r, base + 'viewer.json'), 'off by default')
        packages = (srv.gaussian_package(r, 'work/gaussian/2026-10-18/l1-a/run1/package'),)
        for n in ('viewer.json', 'mobile.ply', 'trained.ksplat'):
            self.assertIsNotNone(srv.servable(r, base + n, packages), n)
        for path in (base + 'notes.txt', base + 'sub/x.json', '/work/gaussian/2026-10-18/l1-a/run0/package/viewer.json',
                     '/work/quest-https/private-key.pem', base + '../../run0/package/viewer.json', base + '%2e%2e/x.json',
                     '/capture-local/x.jpg', '/scripts/serve_quest_https.py'):
            self.assertIsNone(srv.servable(r, path, packages), path)
        for bad in ('work/quest-https', 'work', 'work/gaussian', 'scan-assets', '/etc', 'work/gaussian/../quest-https', 'work/gaussian/missing'):
            with self.assertRaises(ValueError, msg=bad):
                srv.gaussian_package(r, bad)
        server = ThreadingHTTPServer(('127.0.0.1', 0), srv.handler_for(r, packages))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_address[1]}'
        with urllib.request.urlopen(url + base + 'viewer.json') as resp:
            self.assertEqual(resp.status, 200)
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(url + '/work/quest-https/private-key.pem')
        self.assertEqual(e.exception.code, 404)

    def test_certificate_lives_in_ignored_work_dir(self):
        self.assertEqual(srv.CERT_DIR.relative_to(ROOT).parts[0], 'work')
        self.assertIn('work/', (ROOT / '.gitignore').read_text().splitlines())


if __name__ == '__main__':
    unittest.main()
