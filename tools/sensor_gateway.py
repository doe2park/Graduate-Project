#!/usr/bin/env python3
"""Live-test sensor gateway on the laptop (twin/sensors/FEED.md, "Live test with a phone"). Standard library only.

A temporary stand-in for a real wireless gateway / BMS exporter: devices POST observations in the grimes-sensor-feed/1
format, the gateway validates them against the sensor registry and serves a snapshot (latest.json) that the twin pages read
through the 'gateway' adapter of twin/sensors/feed.js. A real gateway later only has to publish the same snapshot shape.

    python3 tools/sensor_gateway.py          # http://127.0.0.1:8931  (desktop check; POST synthetic observations with curl)
    python3 tools/sensor_gateway.py --lan    # https://<private-ip>:8931 (phone + Quest on the same Wi-Fi)

Endpoints
    GET  /phone                        the phone page (tools/sensor-phone.html): accelerometer -> vibration RMS -> POST
    GET  /trust                        open once on a device so its browser accepts the self-signed dev certificate
    POST /api/sensors/observations     one observation or {"observations": [...]}; JSON; same origin or no Origin (curl)
    GET  /api/sensors/latest.json      grimes-sensor-feed/1 snapshot: the latest observation per sensor (missing = null)
    GET  /api/sensors/history.json?sensor=<id>   the rolling history of one sensor (newest last)
    GET  /api/sensors/registry.json    the sensors this gateway accepts (id, label, unit, interval) for the phone page
    GET  /api/health
    GET  /<repo file>                  the twin pages themselves, read-only, same rules as scripts/serve_quest_https.py
                                       (so scan-compare.html / scan-xr.html can read the feed from the same origin)

Rules (FEED.md): sensor_id must be a gateway sensor in the registry; unit must equal the registry unit; ts must be ISO 8601
with a time zone (not more than 2 min in the future, not older than 24 h); value is a number or null (null <=> quality
"missing"); source must be "gateway"; simulated must not be true. Rejected observations are answered with a reason.
Only loopback and private-LAN (RFC 1918) clients are served. No credentials anywhere; nothing is written to disk except the
self-signed certificate that scripts/serve_quest_https.py keeps under work/quest-https/ (gitignored).
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import ipaddress
import json
import math
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = ROOT / 'twin' / 'sensors' / 'registry.live-test.json'
PHONE_PAGE = ROOT / 'tools' / 'sensor-phone.html'
PORT = 8931
FEED_SCHEMA = 'grimes-sensor-feed/1'
QUALITY = ('good', 'suspect', 'missing')
OBS_KEYS = {'sensor_id', 'ts', 'value', 'unit', 'quality', 'source', 'simulated', 'reason'}
TS_RE = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d(\.\d+)?)?(Z|[+-]\d\d:\d\d)$')
MAX_BODY = 64 * 1024
MAX_FUTURE = timedelta(minutes=2)
MAX_AGE = timedelta(hours=24)
PUBLIC_ORIGINS = frozenset({'https://doe2park.github.io'})   # the published twin pages may READ the feed (GET only)
PRIVATE_NETS = [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]


def _serve_quest():
    """scripts/serve_quest_https.py: private_ip, is_private, ensure_certificate and the read-only file allow-list."""
    sys.dont_write_bytecode = True   # no __pycache__ next to the scripts
    spec = importlib.util.spec_from_file_location('serve_quest_https', ROOT / 'scripts' / 'serve_quest_https.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def client_allowed(address: str) -> bool:
    """Loopback or private-LAN IPv4 (also IPv4-mapped IPv6) only."""
    try:
        ip = ipaddress.ip_address(address.split('%')[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or (ip.version == 4 and any(ip in n for n in PRIVATE_NETS))


def private_origin(origin: str) -> bool:
    """http(s)://localhost|127.x|[::1]|RFC1918[:port] with no path: a twin page served on this machine or the LAN."""
    try:
        o = urlsplit(origin)
    except ValueError:
        return False
    if o.scheme not in ('http', 'https') or o.path or o.query or o.username or not o.hostname:
        return False
    if o.hostname == 'localhost':
        return True
    return client_allowed(o.hostname)


def load_sensors(registry_path: Path) -> dict:
    """Gateway sensors of a grimes-sensor-registry/1 file: {id: row}. Retired rows and other data sources are ignored."""
    reg = json.loads(Path(registry_path).read_text())
    if reg.get('schema') != 'grimes-sensor-registry/1':
        raise ValueError(f'{registry_path}: not a grimes-sensor-registry/1 file')
    out = {s['id']: s for s in reg.get('sensors', []) if s.get('data_source') == 'gateway' and s.get('install_status') != 'retired'}
    if not out:
        raise ValueError(f'{registry_path}: no gateway sensors')
    return out


def parse_ts(ts: str):
    if not isinstance(ts, str) or not TS_RE.match(ts):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except ValueError:
        return None
    return dt if dt.tzinfo else None


def validate_observation(o, sensors: dict, now: datetime | None = None):
    """-> (clean observation, None) or (None, reason). Same rules as FEED.md / observation.schema.json, plus a clock check."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(o, dict):
        return None, 'observation must be an object'
    extra = set(o) - OBS_KEYS
    if extra:
        return None, 'unknown field(s): ' + ', '.join(sorted(extra))
    sid = o.get('sensor_id')
    if not isinstance(sid, str) or sid not in sensors:
        return None, f'sensor_id {sid!r} is not a gateway sensor in the registry'
    s = sensors[sid]
    if o.get('source') != 'gateway':
        return None, 'source must be "gateway"'
    if o.get('simulated') not in (None, False):
        return None, 'simulated observations are not accepted by the live gateway'
    if o.get('unit') != s['unit']:
        return None, f'unit {o.get("unit")!r} does not match the registry unit {s["unit"]!r}'
    q = o.get('quality')
    if q not in QUALITY:
        return None, 'quality must be good, suspect or missing'
    v = o.get('value')
    if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)):
        return None, 'value must be a finite number or null'
    if (v is None) != (q == 'missing'):
        return None, 'value null <=> quality "missing" (missing is never 0)'
    ts = o.get('ts')
    if ts is None:
        if v is not None:
            return None, 'ts is required with a value'
    else:
        dt = parse_ts(ts)
        if dt is None:
            return None, 'ts must be ISO 8601 with a time zone (Z or +hh:mm)'
        if dt - now > MAX_FUTURE:
            return None, 'ts is more than 2 min in the future (check the device clock)'
        if now - dt > MAX_AGE:
            return None, 'ts is older than 24 h'
    r = o.get('reason')
    if r is not None and not isinstance(r, str):
        return None, 'reason must be text'
    clean = {'sensor_id': sid, 'ts': ts, 'value': v, 'unit': s['unit'], 'quality': q, 'source': 'gateway'}
    if o.get('simulated') is False:
        clean['simulated'] = False
    if r:
        clean['reason'] = r[:200]
    return clean, None


class Store:
    """Latest observation per sensor (newest ts wins) plus a bounded rolling history. Thread-safe."""

    def __init__(self, sensors: dict, history: int = 300):
        self.sensors, self.lock = sensors, threading.Lock()
        self.latest: dict = {}
        self.hist = {sid: collections.deque(maxlen=history) for sid in sensors}
        self.accepted = self.rejected = 0

    def add(self, items, now=None):
        accepted, rejected = [], []
        with self.lock:
            for i, o in enumerate(items):
                clean, why = validate_observation(o, self.sensors, now)
                if why:
                    rejected.append({'index': i, 'reason': why})
                    self.rejected += 1
                    continue
                sid = clean['sensor_id']
                self.hist[sid].append(clean)
                cur = self.latest.get(sid)
                if cur is None or cur['ts'] is None or (clean['ts'] is not None and parse_ts(clean['ts']) >= parse_ts(cur['ts'])):
                    self.latest[sid] = clean
                accepted.append(sid)
                self.accepted += 1
        return accepted, rejected

    def snapshot(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self.lock:
            obs = [dict(self.latest[sid]) if sid in self.latest else
                   {'sensor_id': sid, 'ts': None, 'value': None, 'unit': s['unit'], 'quality': 'missing', 'source': 'gateway',
                    'reason': 'no observation received by the gateway yet'} for sid, s in self.sensors.items()]
        return {'schema': FEED_SCHEMA, 'generated_at': now.isoformat(timespec='milliseconds').replace('+00:00', 'Z'), 'simulated': False,
                'source': 'gateway', 'note': 'LIVE TEST: temporary test device(s) via tools/sensor_gateway.py on the laptop; '
                'real but uncalibrated measurements, not a permanent Grimes sensor.', 'observations': obs}

    def history(self, sid):
        with self.lock:
            return {'schema': FEED_SCHEMA, 'sensor_id': sid, 'simulated': False, 'source': 'gateway', 'observations': list(self.hist[sid])}


TRUST_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sensor gateway</title></head><body style="font:16px/1.5 system-ui;background:#0b1220;color:#e2e8f0;padding:24px">
<h1 style="font-size:20px">Live-test sensor gateway</h1><p>This browser now accepts the laptop's development certificate. Nothing was installed.</p>
<p><a style="color:#7dd3fc" href="/phone">Phone sensor page</a> · <a style="color:#7dd3fc" href="/api/sensors/latest.json">latest.json</a></p>
<p style="color:#8aa2b8">Temporary test gateway on the owner's laptop (private Wi-Fi only).</p></body></html>"""


def make_handler(store: Store, qh, lan: bool, static: bool, quiet: bool = False):
    own_scheme = 'https' if lan else 'http'

    class Handler(SimpleHTTPRequestHandler):
        server_version = 'grimes-sensor-gateway/1'
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript',
                          '.glb': 'model/gltf-binary', '.wasm': 'application/wasm', '.ksplat': 'application/octet-stream',
                          '.ply': 'application/octet-stream'}

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(ROOT), **kw)

        # ----- guards
        def _own_origin(self):
            return f'{own_scheme}://{self.headers.get("Host", "")}'

        def _read_origin_ok(self, origin):
            return bool(origin) and origin != 'null' and (origin == self._own_origin() or origin in PUBLIC_ORIGINS or private_origin(origin))

        def _client_ok(self):
            if client_allowed(self.client_address[0]):
                return True
            self._json(403, {'error': 'only loopback and private-LAN clients'})
            return False

        def _json(self, code, obj, cors=False):
            data = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            origin = self.headers.get('Origin')
            if cors and self._read_origin_ok(origin):
                self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(data)

        def _html(self, data: bytes):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(data)

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store' if self.path.startswith('/api/') else 'no-cache')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Robots-Tag', 'noindex, nofollow')
            self.send_header('Permissions-Policy', 'xr-spatial-tracking=(self), accelerometer=(self), gyroscope=(self)')
            super().end_headers()

        def log_message(self, fmt, *args):
            if not quiet and args and str(args[1]).startswith(('4', '5')):
                super().log_message(fmt, *args)

        # ----- CORS preflight (GET of the feed from another private / published page; Chrome Private Network Access)
        def do_OPTIONS(self):
            if not self._client_ok():
                return
            path = urlsplit(self.path).path
            origin = self.headers.get('Origin')
            if not path.startswith('/api/sensors/') or not self._read_origin_ok(origin):
                return self._json(403, {'error': 'cross-origin request refused'})
            if (self.headers.get('Access-Control-Request-Method') or 'GET').upper() != 'GET':
                return self._json(405, {'error': 'only GET from other origins; observations are posted from /phone'})
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'GET')
            self.send_header('Access-Control-Max-Age', '600')
            if (self.headers.get('Access-Control-Request-Private-Network') or '').lower() == 'true':
                self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.send_header('Vary', 'Origin')
            self.send_header('Content-Length', '0')
            self.end_headers()

        # ----- reads
        def do_GET(self):
            if not self._client_ok():
                return
            u = urlsplit(self.path)
            path = u.path
            if path == '/':
                self.send_response(HTTPStatus.FOUND)
                self.send_header('Location', '/phone')
                self.send_header('Content-Length', '0')
                return self.end_headers()
            if path in ('/phone', '/phone/'):
                return self._html(PHONE_PAGE.read_bytes())
            if path == '/trust':
                return self._html(TRUST_PAGE.encode())
            if path == '/api/health':
                return self._json(200, {'ok': True, 'sensors': list(store.sensors), 'accepted': store.accepted, 'rejected': store.rejected}, cors=True)
            if path == '/api/sensors/latest.json':
                return self._json(200, store.snapshot(), cors=True)
            if path == '/api/sensors/history.json':
                sid = (parse_qs(u.query).get('sensor') or [''])[0]
                if sid not in store.sensors:
                    return self._json(404, {'error': 'unknown sensor'}, cors=True)
                return self._json(200, store.history(sid), cors=True)
            if path == '/api/sensors/registry.json':
                return self._json(200, {'sensors': [{k: s.get(k) for k in ('id', 'label', 'kind', 'quantity', 'unit', 'sampling_interval_s', 'test_device')}
                                                    for s in store.sensors.values()]}, cors=True)
            if path.startswith('/api/'):
                return self._json(404, {'error': 'unknown endpoint'})
            if not static or qh.servable(ROOT, self.path) is None:
                return self._json(404, {'error': 'not served'})
            return super().do_GET()

        def do_HEAD(self):
            if not self._client_ok():
                return
            if urlsplit(self.path).path.startswith('/api/') or not static or qh.servable(ROOT, self.path) is None:
                self.send_response(404)
                self.send_header('Content-Length', '0')
                return self.end_headers()
            return super().do_HEAD()

        def list_directory(self, path):
            self.send_error(404, 'Not available')

        # ----- writes: observations only, same origin (the /phone page) or no Origin (curl, a gateway on this LAN)
        def do_POST(self):
            if not self._client_ok():
                return
            if urlsplit(self.path).path != '/api/sensors/observations':
                return self._json(404, {'error': 'unknown endpoint'})
            origin = self.headers.get('Origin')
            if origin and origin != self._own_origin():
                return self._json(403, {'error': 'observations are accepted from the gateway origin only'})
            if (self.headers.get('Content-Type') or '').split(';')[0].strip().lower() != 'application/json':
                return self._json(415, {'error': 'Content-Type must be application/json'})
            try:
                n = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                n = -1
            if n <= 0 or n > MAX_BODY:
                return self._json(413, {'error': f'body must be 1..{MAX_BODY} bytes'})
            try:
                body = json.loads(self.rfile.read(n))
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {'error': 'body is not JSON'})
            items = body.get('observations') if isinstance(body, dict) and 'observations' in body else [body]
            if not isinstance(items, list) or not 1 <= len(items) <= 100:
                return self._json(400, {'error': 'observations must be a list of 1..100'})
            accepted, rejected = store.add(items)
            if not quiet:
                for o in items:
                    if isinstance(o, dict) and o.get('sensor_id') in accepted:
                        print(f'[gateway] {o["sensor_id"]} {o.get("value")} {o.get("unit")} {o.get("quality")} ts {o.get("ts")}', flush=True)
                for r in rejected:
                    print(f'[gateway] rejected #{r["index"]}: {r["reason"]}', flush=True)
            return self._json(200 if accepted else 422, {'accepted': len(accepted), 'rejected': rejected})
        do_PUT = do_DELETE = do_PATCH = lambda self: self._json(405, {'error': 'method not allowed'})

    return Handler


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--port', type=int, default=PORT)
    p.add_argument('--lan', action='store_true', help='HTTPS on the private LAN address (phone/Quest on the same Wi-Fi), self-signed dev certificate')
    p.add_argument('--registry', default=str(DEFAULT_REGISTRY), help='sensor registry (default: twin/sensors/registry.live-test.json)')
    p.add_argument('--history', type=int, default=300, help='observations kept per sensor (default 300)')
    p.add_argument('--no-static', action='store_true', help='serve only the gateway API and /phone, not the twin pages')
    p.add_argument('--quiet', action='store_true')
    a = p.parse_args(argv)
    sensors = load_sensors(Path(a.registry))
    store = Store(sensors, a.history)
    qh = _serve_quest()
    host = qh.private_ip() if a.lan else '127.0.0.1'
    if a.lan and not qh.is_private(host):
        raise SystemExit('Refusing to bind a non-private address: ' + host)
    server = ThreadingHTTPServer((host, a.port), make_handler(store, qh, a.lan, not a.no_static, a.quiet))
    scheme = 'http'
    if a.lan:
        import ssl
        cert, key = qh.ensure_certificate(host)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert, key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        scheme = 'https'
    base = f'{scheme}://{host}:{a.port}'
    feed = f'{base}/api/sensors/latest.json'
    sid = next(iter(sensors))
    print(f'[gateway] sensors: {", ".join(sensors)} (registry {Path(a.registry).resolve().relative_to(ROOT) if Path(a.registry).resolve().is_relative_to(ROOT) else a.registry})', flush=True)
    print(f'[gateway] phone page:   {base}/phone', flush=True)
    print(f'[gateway] feed:         {feed}', flush=True)
    if not a.no_static:
        print(f'[gateway] web overlay:  {base}/scan-compare.html?view=overlay&capture=2026-05-06&sensors=live&feed=/api/sensors/latest.json', flush=True)
        print(f'[gateway] Quest (MR):   {base}/mr/?sensors=live&feed=/api/sensors/latest.json', flush=True)
        print(f'[gateway] Quest (VR):   {base}/scan-xr.html?sensors=live&feed=/api/sensors/latest.json', flush=True)
    print(f'[gateway] curl test:    curl -s -H "Content-Type: application/json" -d \'{{"sensor_id":"{sid}","ts":"\'$(date -u +%Y-%m-%dT%H:%M:%SZ)\'","value":0.12,'
          f'"unit":"{sensors[sid]["unit"]}","quality":"good","source":"gateway"}}\' {base}/api/sensors/observations', flush=True)
    if a.lan:
        print('[gateway] self-signed dev certificate: on each device open the phone page (or /trust) once and accept the warning '
              'for this exact address. Same Wi-Fi required (no client isolation).', flush=True)
    print('[gateway] Ctrl+C stops.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[gateway] stopped.')
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
