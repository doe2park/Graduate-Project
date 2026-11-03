#!/usr/bin/env python3
"""Ask-the-twin local demo server (laptop only; nothing is deployed).

    python3 scripts/ask_twin_server.py            # live: needs ANTHROPIC_API_KEY (env, or ~/.config/ask-twin/env)
    python3 scripts/ask_twin_server.py --mock     # no key: scripted answers built from the same read-only tools
    open http://127.0.0.1:8765/                   # -> grimes-bim-viewer.html?ask=1

Serves this checkout read-only (GET/HEAD; dot-files, work/, capture-local/ and node_modules refused) plus:
    GET  /api/health      mode, model, index and speech-to-text status
    POST /api/ask         {question, element_id?, point?, history?} -> text/event-stream of agent events
    POST /api/transcribe  raw audio body (webm/ogg/wav/mp4) -> {text} via local faster-whisper (optional)
    POST /api/speak       {text} -> audio/wav via macOS `say` (optional; for browsers with no speechSynthesis voice)
The API key is read only from ANTHROPIC_API_KEY (optionally loaded from an env file OUTSIDE the repo). It is never
printed, logged, written or sent anywhere except to the Anthropic API.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = Path.home() / '.venvs' / 'ask-twin'
VENV_PY = VENV_DIR / 'bin' / 'python'
DEFAULT_ENV_FILE = Path.home() / '.config' / 'ask-twin' / 'env'
DENY_TOP = {'work', 'capture-local', 'node_modules', 'target', 'logs', 'raw_csv'}
MAX_BODY = 25 * 1024 * 1024
ENTRY = '/grimes-bim-viewer.html?ask=1'
XR_ENTRY = '/mr/?ask=1'   # the headset page: /mr -> scan-xr.html?mode=ar&place=demo&sensors=demo&ask=1


def maybe_reexec_in_venv():
    """One command: if the SDK is missing here but the documented venv exists, re-run inside it."""
    try:
        import anthropic  # noqa: F401
        return
    except ImportError:
        pass
    # compare prefixes, not executables: a venv's python is a symlink to the base interpreter
    if VENV_PY.exists() and Path(sys.prefix).resolve() != VENV_DIR.resolve() and not os.environ.get('ASK_TWIN_NO_REEXEC'):
        os.environ['ASK_TWIN_NO_REEXEC'] = '1'
        os.execv(str(VENV_PY), [str(VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])


def load_env_file(path: Path) -> bool:
    """Load ANTHROPIC_API_KEY from KEY=VALUE lines. Refuses files inside the repository. Returns True if set."""
    path = path.expanduser()
    if not path.is_file():
        return False
    try:
        path.resolve().relative_to(ROOT.resolve())
        sys.exit(f'Refusing to read an env file inside the repository ({path}). Keep it outside, e.g. {DEFAULT_ENV_FILE}.')
    except ValueError:
        pass
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith('export '):
            line = line[7:].strip()
        if line.startswith('ANTHROPIC_API_KEY='):
            val = line.split('=', 1)[1].strip().strip('"').strip("'")
            if val:
                os.environ['ANTHROPIC_API_KEY'] = val
                return True
    return False


NO_KEY_MESSAGE = f"""
ANTHROPIC_API_KEY is not set, so live answers cannot run.

  Option A (this shell):   export ANTHROPIC_API_KEY=...   then re-run this command
  Option B (kept file):    mkdir -p ~/.config/ask-twin && printf 'ANTHROPIC_API_KEY=...\\n' > {DEFAULT_ENV_FILE} && chmod 600 {DEFAULT_ENV_FILE}
  Without a key:           python3 scripts/ask_twin_server.py --mock   (scripted, tool-grounded answers)
"""


def decode_16k(path: str):
    """Audio file -> 16 kHz mono float32 for faster-whisper. Decoded here with PyAV because faster-whisper 1.2.1's own
    decode_audio passes metadata_errors=, which PyAV >= 15 no longer accepts (TypeError seen with av 19.0.2). Falls back to
    the path (faster-whisper decodes) if PyAV/numpy are unavailable."""
    try:
        import av
        import numpy as np
    except ImportError:
        return path
    out = []
    with av.open(path, mode='r') as container:
        rs = av.audio.resampler.AudioResampler(format='s16', layout='mono', rate=16000)
        for frame in container.decode(audio=0):
            out += [f.to_ndarray().reshape(-1) for f in rs.resample(frame)]
        out += [f.to_ndarray().reshape(-1) for f in rs.resample(None)]
    return (np.concatenate(out) if out else np.zeros(0, np.int16)).astype(np.float32) / 32768.0


class STT:
    """Lazy local speech-to-text (faster-whisper). Optional: the browser falls back to Web Speech."""

    def __init__(self, model_name='base.en', enabled=True):
        self.model_name, self.enabled, self.model, self.error = model_name, enabled, None, None
        self.lock = threading.Lock()
        try:
            import faster_whisper  # noqa: F401
            self.available = enabled
        except ImportError:
            self.available, self.error = False, 'faster-whisper not installed'

    def warm(self):
        if self.available:
            threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        with self.lock:
            if self.model is None and self.available:
                try:
                    from faster_whisper import WhisperModel
                    self.model = WhisperModel(self.model_name, device='cpu', compute_type='int8')
                except Exception as e:   # model download/load failure: report, fall back in the browser
                    self.available, self.error = False, f'{type(e).__name__}: {e}'[:200]
        return self.model

    def transcribe(self, data: bytes, suffix='.webm') -> dict:
        model = self._load()
        if model is None:
            raise RuntimeError(self.error or 'speech-to-text unavailable')
        with tempfile.NamedTemporaryFile(suffix=suffix) as f:
            f.write(data)
            f.flush()
            t0 = time.time()
            segments, info = model.transcribe(decode_16k(f.name), language='en', beam_size=1, vad_filter=True,
                                              initial_prompt='Grimes building digital twin: ceiling tile, duct, diffuser, VAV box, AHU, valve, pipe, sprinkler, leak, plenum.')
            text = ' '.join(s.text.strip() for s in segments).strip()
        return {'text': text, 'seconds': round(time.time() - t0, 2), 'engine': f'faster-whisper {self.model_name} (local)'}


class TTS:
    """Optional spoken replies made on the laptop (macOS `say` -> WAV) for browsers without a speechSynthesis voice
    (the Quest Browser may have none; not verified). Local only: the text never leaves the machine."""
    MAX_CHARS = 1200

    def __init__(self, enabled=True):
        self.cmd = shutil.which('say') if enabled and sys.platform == 'darwin' else None
        self.available = bool(self.cmd)
        self.error = None if self.available else ('disabled' if not enabled else 'macOS `say` not available')
        self.voice = self._english_voice() if self.available else None

    def _english_voice(self):
        """An English system voice: the default voice follows the Mac's language (e.g. Korean Yuna would read English oddly)."""
        try:
            listing = subprocess.run([self.cmd, '-v', '?'], capture_output=True, text=True, timeout=10).stdout
        except Exception:
            return None
        names = {line.split('  ')[0].strip() for line in listing.splitlines() if ' en_' in line}
        return next((v for v in ('Samantha', 'Daniel', 'Karen', 'Moira', 'Fred') if v in names), None)

    def speak(self, text: str) -> bytes:
        text = ' '.join(str(text or '').split())[:self.MAX_CHARS]
        if not text:
            raise ValueError('nothing to say')
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / 'in.txt', Path(d) / 'out.wav'
            src.write_text(text)
            subprocess.run([self.cmd, *(['-v', self.voice] if self.voice else []), '-o', str(out), '--data-format=LEI16@22050', '-f', str(src)],
                           check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return out.read_bytes()


class Handler(SimpleHTTPRequestHandler):
    server_version = 'AskTwin/1'
    app = None   # set in main()

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *args):
        if self.app.verbose or not (200 <= getattr(self, '_status', 200) < 400):
            sys.stderr.write('[ask-twin] %s - %s\n' % (self.address_string(), fmt % args))

    def send_response(self, code, message=None):
        self._status = code
        super().send_response(code, message)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store' if self.path.startswith('/api/') else 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

    # ----- static, read-only
    def _blocked(self) -> bool:
        parts = [p for p in unquote(urlparse(self.path).path).split('/') if p]
        return any(p.startswith('.') for p in parts) or (parts and parts[0] in DENY_TOP) or '..' in parts

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            self.send_response(HTTPStatus.FOUND)
            self.send_header('Location', ENTRY)
            self.end_headers()
            return
        if path == '/api/health':
            return self._json(200, self.app.health())
        if path.startswith('/api/'):
            return self._json(404, {'error': 'unknown endpoint'})
        if self._blocked():
            return self._json(403, {'error': 'not served'})
        return super().do_GET()

    def do_HEAD(self):
        if self._blocked():
            self.send_response(403)
            self.end_headers()
            return
        return super().do_HEAD()

    # ----- API
    def _body(self) -> bytes:
        n = int(self.headers.get('Content-Length') or 0)
        if n > MAX_BODY:
            raise ValueError('request body too large')
        return self.rfile.read(n) if n else b''

    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = urlparse(self.path).path
        if not self.app.origin_ok(self.headers.get('Origin'), self.headers.get('Host')):
            return self._json(403, {'error': 'cross-origin request refused'})
        try:
            if path == '/api/ask':
                return self._ask(json.loads(self._body() or b'{}'))
            if path == '/api/transcribe':
                return self._transcribe(self._body())
            if path == '/api/speak':
                return self._speak(json.loads(self._body() or b'{}'))
        except (ValueError, json.JSONDecodeError) as e:
            return self._json(400, {'error': str(e)[:200]})
        return self._json(404, {'error': 'unknown endpoint'})

    def _ask(self, req):
        q = str(req.get('question') or '').strip()[:1000]
        if not q:
            return self._json(400, {'error': 'question is empty'})
        eid = req.get('element_id')
        eid = str(eid)[:40] if eid not in (None, '') else None
        pt = req.get('point')
        if pt is not None and not (isinstance(pt, list) and len(pt) == 3 and all(isinstance(v, (int, float)) for v in pt)):
            pt = None
        hist = req.get('history') if isinstance(req.get('history'), list) else []
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()
        sys.stderr.write(f'[ask-twin] ask ({self.app.mode}) element={eid} q={q[:80]!r}\n')
        try:
            for ev in self.app.agent.ask(q, eid, pt, hist):
                self.wfile.write(f'data: {json.dumps(ev)}\n\n'.encode())
                self.wfile.flush()
                if ev['type'] == 'final':
                    sys.stderr.write(f'[ask-twin]   done in {ev.get("seconds")} s · {len(ev.get("tools_used", []))} tool calls · '
                                     f'{sum(c["verified"] for c in ev.get("citations", []))}/{len(ev.get("citations", []))} citations verified\n')
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as e:   # never leak a traceback with environment details to the page
            sys.stderr.write(f'[ask-twin] agent error: {type(e).__name__}: {e}\n')
            try:
                self.wfile.write(f'data: {json.dumps({"type": "error", "message": f"server error: {type(e).__name__}"})}\n\n'.encode())
            except OSError:
                pass

    def _speak(self, req):
        tts = self.app.tts
        if not tts or not tts.available:
            return self._json(501, {'error': (tts.error if tts else None) or 'text-to-speech disabled'})
        try:
            data = tts.speak(req.get('text'))
        except ValueError as e:
            return self._json(400, {'error': str(e)})
        except Exception as e:
            return self._json(500, {'error': f'speech failed: {type(e).__name__}'})
        self.send_response(200)
        self.send_header('Content-Type', 'audio/wav')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _transcribe(self, data: bytes):
        stt = self.app.stt
        if not stt or not stt.available:
            return self._json(501, {'error': (stt.error if stt else None) or 'speech-to-text disabled', 'fallback': 'web-speech'})
        if len(data) < 200:
            return self._json(400, {'error': 'no audio received'})
        ctype = (self.headers.get('Content-Type') or '').lower()
        suffix = '.ogg' if 'ogg' in ctype else '.mp4' if ('mp4' in ctype or 'aac' in ctype) else '.wav' if 'wav' in ctype else '.webm'
        try:
            return self._json(200, stt.transcribe(data, suffix))
        except Exception as e:
            return self._json(500, {'error': f'transcription failed: {type(e).__name__}', 'fallback': 'web-speech'})


class App:
    def __init__(self, agent, mode, model, twin, stt, port, verbose=False, lan=False, tts=None):
        self.agent, self.mode, self.model, self.twin, self.stt, self.port, self.verbose, self.lan = agent, mode, model, twin, stt, port, verbose, lan
        self.tts = tts

    def origin_ok(self, origin, host):
        if not origin:
            return True   # same-origin fetch from older browsers / curl
        o = urlparse(origin)
        return o.netloc == host or (o.hostname in ('127.0.0.1', 'localhost') and str(o.port) == str(self.port))

    def health(self):
        return {'ok': True, 'mode': self.mode, 'model': self.model,
                'index': {'elements': len(self.twin.box), 'layers': len(self.twin.index['layers'])},
                'sensors': {'count': len(self.twin.sensors), 'note': 'demo, simulated'},
                'stt': {'available': bool(self.stt and self.stt.available), 'loaded': bool(self.stt and self.stt.model),
                        'engine': f'faster-whisper {self.stt.model_name}' if self.stt else None, 'error': self.stt.error if self.stt else None},
                'tts': {'available': bool(self.tts and self.tts.available), 'engine': f'macOS say {self.tts.voice or "default voice"} (local)' if self.tts and self.tts.available else None}}


def build_app(args, log=print):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from ask_twin.agent import DEFAULT_MODEL, LiveAgent, MockAgent
    from ask_twin.tools import Twin
    if args.mock:
        mode, model = 'mock', 'mock (scripted, tool-grounded)'
    else:
        if not os.environ.get('ANTHROPIC_API_KEY'):
            load_env_file(Path(args.env_file))
        if not os.environ.get('ANTHROPIC_API_KEY'):
            sys.stderr.write(NO_KEY_MESSAGE)
            sys.exit(2)
        try:
            import anthropic
        except ImportError:
            sys.exit(f'The anthropic package is not installed. Run: python3 -m venv ~/.venvs/ask-twin && '
                     f'~/.venvs/ask-twin/bin/pip install anthropic faster-whisper   (or use --mock)')
        mode, model = 'live', args.model or DEFAULT_MODEL
    twin = Twin(log=log)
    if mode == 'live':
        client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'], max_retries=2, timeout=120)
        agent = LiveAgent(twin, client, model=model, effort=args.effort, fallbacks=not args.no_fallbacks)
    else:
        agent = MockAgent(twin)
    stt = None if args.no_stt else STT(args.stt_model)
    return App(agent, mode, model, twin, stt, args.port, args.verbose, args.lan, tts=TTS(not args.no_tts))


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description='Ask-the-twin local demo server')
    ap.add_argument('--mock', action='store_true', help='no API key: scripted answers from the same read-only tools')
    ap.add_argument('--model', default=None, help='Claude model id (default claude-sonnet-5-5; e.g. claude-opus-5-5)')
    ap.add_argument('--effort', default='medium', choices=['low', 'medium', 'high', 'xhigh', 'max'])
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--env-file', default=str(DEFAULT_ENV_FILE), help='file outside the repo with ANTHROPIC_API_KEY=...')
    ap.add_argument('--no-stt', action='store_true', help='disable local speech-to-text (browser Web Speech only)')
    ap.add_argument('--no-tts', action='store_true', help='disable laptop text-to-speech (/api/speak, macOS say)')
    ap.add_argument('--stt-model', default='base.en', help='faster-whisper model (tiny.en, base.en, small.en)')
    ap.add_argument('--no-fallbacks', action='store_true', help='do not send the server-side refusal fallback beta')
    ap.add_argument('--lan', action='store_true', help='HTTPS on the private LAN address (Quest on the same Wi-Fi), self-signed dev certificate from scripts/serve_quest_https.py')
    ap.add_argument('--verbose', action='store_true')
    return ap.parse_args(argv)


def main(argv=None):
    maybe_reexec_in_venv()
    args = parse_args(argv)
    app = build_app(args)
    Handler.app = app
    host, scheme = '127.0.0.1', 'http'
    if args.lan:   # private-LAN HTTPS (the Quest needs a secure context for the microphone); never a public address
        import ssl
        import serve_quest_https as qh
        host, scheme = qh.private_ip(), 'https'
        if not qh.is_private(host):
            sys.exit('Refusing to bind a non-private address: ' + host)
        cert, key = qh.ensure_certificate(host)
    httpd = ThreadingHTTPServer((host, args.port), Handler)
    httpd.daemon_threads = True
    if args.lan:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert, key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    if app.stt:
        app.stt.warm()
    print(f'[ask-twin] {app.mode.upper()} mode · model {app.model} · {len(app.twin.box)} indexed elements · '
          f'speech-to-text: {"faster-whisper " + app.stt.model_name + " (loading)" if app.stt and app.stt.available else "browser only"}', flush=True)
    print(f'[ask-twin] open {scheme}://{host}:{args.port}/   (Ctrl+C to stop)', flush=True)
    print(f'[ask-twin] headset (WebXR MR + ask): {scheme}://{host}:{args.port}{XR_ENTRY}'
          + ('\n[ask-twin] self-signed dev certificate: accept the warning only for this address; same Wi-Fi required' if args.lan else ''), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n[ask-twin] stopped')


if __name__ == '__main__':
    main()
