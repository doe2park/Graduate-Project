#!/usr/bin/env python3
"""Ask-the-twin local demo server (laptop only; nothing is deployed).

    python3 scripts/ask_twin_server.py            # live: needs ANTHROPIC_API_KEY (env, or ~/.config/ask-twin/env)
    python3 scripts/ask_twin_server.py --mock     # no key: scripted answers built from the same read-only tools
    open http://127.0.0.1:8765/                   # -> grimes-bim-viewer.html?ask=1

Serves this checkout read-only (GET/HEAD; dot-files, work/, capture-local/ and node_modules refused) plus:
    GET  /api/health      mode, model, index, speech-to-text status, limits and today's usage (numbers only; open)
    GET  /trust           a tiny page to open once in the headset so it accepts the self-signed certificate (Method A)
    POST /api/ask         {question, element_id?, point?, history?} -> text/event-stream of agent events
    POST /api/transcribe  raw audio body (webm/ogg/wav/mp4) -> {text} via local faster-whisper (optional)
    POST /api/speak       {text} -> audio/wav via macOS `say` (best installed English voice; --voice overrides)
CORS: the API also answers the public GitHub Pages site (PUBLIC_ORIGINS, exact match) so the published /mr page can use
this laptop for the AI calls only ("Method A", docs/ASK_TWIN.md); preflights, including Chrome's Private Network Access
preflight, are answered for those origins only. Every other cross-origin request is refused as before.
Limits (scripts/ask_twin/limits.py, docs/ASK_TWIN.md "Limits and access code"): POST /api/ask, /api/transcribe and /api/speak
need the access code printed at start (header X-Ask-Code, or ?code=); questions are rate limited per client and per day, and
answers stop at a daily token budget counted from the API's own usage numbers. --idle-minutes stops an unused server.
The API key is read only from ANTHROPIC_API_KEY (optionally loaded from an env file OUTSIDE the repo). It is never
printed, logged, written or sent anywhere except to the Anthropic API.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = Path.home() / '.venvs' / 'ask-twin'
VENV_PY = VENV_DIR / 'bin' / 'python'
DEFAULT_ENV_FILE = Path.home() / '.config' / 'ask-twin' / 'env'
DENY_TOP = {'work', 'capture-local', 'node_modules', 'target', 'logs', 'raw_csv'}
MAX_BODY = 25 * 1024 * 1024
ENTRY = '/grimes-bim-viewer.html?ask=1'
# Pages allowed to call the API from another origin (exact scheme://host[:port]; no wildcards, no http).
PUBLIC_ORIGINS = frozenset({'https://doe2park.github.io'})
API_PATHS = frozenset({'/api/health', '/api/ask', '/api/transcribe', '/api/speak'})
# Speech-to-text hints: the words people use about this building (faster-whisper initial_prompt and hotwords).
STT_PROMPT = ('Questions about the Grimes building services: the duct, the diffuser, the VAV box, the damper, airflow, '
              'the sprinkler pipe, a valve, the ceiling tile, a light, what is above it, where the air comes from.')
STT_HOTWORDS = 'Grimes duct diffuser VAV box damper airflow sprinkler pipe valve ceiling tile'
XR_ENTRY = '/mr/?ask=1'   # the headset page: /mr -> scan-xr.html?mode=ar&place=demo&sensors=demo&ask=1
CODE_HEADER = 'X-Ask-Code'
PUBLIC_MR = 'https://doe2park.github.io/Graduate-Project/mr/?ask=1'


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


NO_KEY_NOTE = 'Live AI needs a key on the laptop; running scripted answers'
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


def _norm_words(t: str) -> str:
    return ' '.join(re.findall(r"[a-z0-9']+", (t or '').lower()))


def clean_transcript(segments) -> str:
    """Join faster-whisper segments, dropping ones that are probably not speech (high no-speech probability with low
    confidence) and text that only echoes the prompt (Whisper can repeat its initial_prompt on silence or noise)."""
    keep = []
    for s in segments:
        if getattr(s, 'no_speech_prob', 0.0) > 0.6 and getattr(s, 'avg_logprob', 0.0) < -1.0:
            continue
        t = (getattr(s, 'text', '') or '').strip()
        if t:
            keep.append(t)
    text = ' '.join(keep).strip()
    n = _norm_words(text)
    if not n or (len(n) > 3 and n in _norm_words(STT_PROMPT)):
        return ''
    return text


class STT:
    """Lazy local speech-to-text (faster-whisper). Optional: the browser falls back to Web Speech."""

    def __init__(self, model_name='base.en', enabled=True, beam_size=5):
        self.model_name, self.enabled, self.model, self.error, self.beam_size = model_name, enabled, None, None, beam_size
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
            # VAD trims leading/trailing silence and drops pauses; the prompt and hotwords bias toward the building's words
            segments, info = model.transcribe(decode_16k(f.name), language='en', beam_size=self.beam_size, vad_filter=True,
                                              vad_parameters={'min_silence_duration_ms': 400, 'speech_pad_ms': 200},
                                              initial_prompt=STT_PROMPT, hotwords=STT_HOTWORDS, condition_on_previous_text=False,
                                              without_timestamps=True)
            text = clean_transcript(list(segments))
            speech_s = float(getattr(info, 'duration_after_vad', 1.0) or 0.0)
        out = {'text': text, 'seconds': round(time.time() - t0, 2), 'engine': f'faster-whisper {self.model_name} (local)'}
        if not text or speech_s < 0.25:
            out.update(text='', no_speech=True)
        return out


PREMIUM_MARKS = ('(premium)', '(프리미엄)')          # macOS shows the quality in the system language
ENHANCED_MARKS = ('(enhanced)', '(고품질)', '(향상됨)')
STANDARD_FALLBACK = ('Samantha', 'Daniel', 'Karen', 'Moira', 'Fred')
PREFERRED_PREMIUM = ('Zoe', 'Ava', 'Evan', 'Nathan', 'Noelle', 'Joelle', 'Susan', 'Tom', 'Allison', 'Jamie', 'Serena', 'Samantha')
VOICE_LINE = re.compile(r'^(?P<name>.+?)\s{2,}(?P<locale>[a-z]{2,3}[_-][A-Za-z0-9]{2,4})\s+#')


def parse_voices(listing: str) -> list:
    """`say -v '?'` -> [{'name', 'locale', 'quality': 'premium'|'enhanced'|'standard'}]"""
    out = []
    for line in (listing or '').splitlines():
        m = VOICE_LINE.match(line)
        if not m:
            continue
        name, low = m.group('name').strip(), m.group('name').lower()
        q = 'premium' if any(k in low for k in PREMIUM_MARKS) else 'enhanced' if any(k in low for k in ENHANCED_MARKS) else 'standard'
        out.append({'name': name, 'locale': m.group('locale').replace('-', '_'), 'quality': q})
    return out


def pick_voice(voices: list, override: str | None = None):
    """Best English voice: --voice if installed (exact name, or the name before ' ('), else (Premium) then (Enhanced)
    en_US / en_GB voices (preferred names first, US before GB), else Samantha and the other standard voices.
    Returns (voice dict or None, note)."""
    if override:
        o = override.strip().lower()
        hit = next((v for v in voices if v['name'].lower() == o), None) or \
            next((v for v in sorted(voices, key=lambda v: {'premium': 0, 'enhanced': 1}.get(v['quality'], 2))
                  if v['name'].lower().split(' (')[0] == o), None)
        if hit:
            return hit, f'--voice {override}'
        note = f'--voice {override!r} is not installed; '
    else:
        note = ''
    english = [v for v in voices if v['locale'] in ('en_US', 'en_GB')]

    def rank(v):
        base = v['name'].split(' (')[0]
        return (PREFERRED_PREMIUM.index(base) if base in PREFERRED_PREMIUM else len(PREFERRED_PREMIUM), v['locale'] != 'en_US', v['name'])
    for quality in ('premium', 'enhanced'):
        best = sorted((v for v in english if v['quality'] == quality), key=rank)
        if best:
            return best[0], note + f'best installed {quality} English voice'
    names = {v['name']: v for v in voices if v['locale'].startswith('en_')}
    for n in STANDARD_FALLBACK:
        if n in names:
            return names[n], note + 'standard voice (no Premium/Enhanced English voice installed)'
    return None, note + 'system default voice'


class TTS:
    """Spoken replies made on the laptop (macOS `say` -> WAV), preferred over the headset browser's own voice.
    Local only: the text never leaves the machine. The voice is the best installed English one (see pick_voice)."""
    MAX_CHARS = 1200

    def __init__(self, enabled=True, voice=None):
        self.cmd = shutil.which('say') if enabled and sys.platform == 'darwin' else None
        self.available = bool(self.cmd)
        self.error = None if self.available else ('disabled' if not enabled else 'macOS `say` not available')
        self.voice, self.quality, self.note = None, None, ''
        if self.available:
            v, self.note = pick_voice(self._voices(), voice)
            if v:
                self.voice, self.quality = v['name'], v['quality']

    def _voices(self):
        try:
            return parse_voices(subprocess.run([self.cmd, '-v', '?'], capture_output=True, text=True, timeout=10).stdout)
        except Exception:
            return []

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


TRUST_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ask the twin: laptop trusted</title><style>body{font:18px/1.5 Arial,sans-serif;background:#08101c;color:#e8f1f8;margin:0;padding:24px}
b{color:#D97757}code{color:#fcd34d}</style></head><body><h1>Laptop server reached</h1>
<p>This browser now accepts the laptop's development certificate for <code>%s</code>. Nothing was installed.</p>
<p><b>Close this tab</b>, go back to the twin page and press <b>Retry</b> in the <i>Ask the twin</i> box.</p>
<p style="color:#8aa2b8">Ask the twin, local demo server on the owner's laptop (private Wi-Fi only).</p></body></html>"""


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

    def _cors_origin(self):
        """The request's Origin if it may read API responses (own origin, localhost on this port, PUBLIC_ORIGINS), else None."""
        origin = self.headers.get('Origin')
        return origin if origin and self.app.cors_ok(origin, self.headers.get('Host')) else None

    def end_headers(self):
        api = self.path.startswith('/api/')
        self.send_header('Cache-Control', 'no-store' if api else 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if api:
            origin = self._cors_origin()
            if origin:
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Access-Control-Expose-Headers', 'Retry-After')
            self.send_header('Vary', 'Origin')
        super().end_headers()

    def do_OPTIONS(self):
        """CORS preflight for the API, only for allowed origins. Chrome-based browsers (Quest Browser) also send a
        Private Network Access preflight when a public HTTPS page calls a private-LAN address: answered with
        Access-Control-Allow-Private-Network for the same allowed origins only."""
        path = urlparse(self.path).path
        if path not in API_PATHS:
            return self._json(404, {'error': 'unknown endpoint'})
        if not self._cors_origin():
            return self._json(403, {'error': 'cross-origin request refused'})
        method = (self.headers.get('Access-Control-Request-Method') or '').upper()
        if method and method not in ('GET', 'POST'):
            return self._json(405, {'error': 'method not allowed'})
        self.send_response(204)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST')
        self.send_header('Access-Control-Allow-Headers', f'Content-Type, {CODE_HEADER}')
        self.send_header('Access-Control-Max-Age', '600')
        if (self.headers.get('Access-Control-Request-Private-Network') or '').lower() == 'true':
            self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Content-Length', '0')
        self.end_headers()

    # ----- static, read-only
    def _blocked(self) -> bool:
        parts = [p for p in unquote(urlparse(self.path).path).split('/') if p]
        return any(p.startswith('.') for p in parts) or (parts and parts[0] in DENY_TOP) or '..' in parts

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            code = (parse_qs(urlparse(self.path).query).get('code') or [''])[0]
            self.send_response(HTTPStatus.FOUND)
            self.send_header('Location', ENTRY + ('&' + urlencode({'code': code[:32]}) if code else ''))
            self.end_headers()
            return
        if path == '/api/health':
            return self._json(200, self.app.health())
        if path == '/trust':
            data = (TRUST_PAGE % self.headers.get('Host', '')[:80].replace('<', '').replace('&', '')).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
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

    def _json(self, code, obj, retry_after=None):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        if retry_after:
            self.send_header('Retry-After', str(int(retry_after)))
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = urlparse(self.path).path
        if not self.app.origin_ok(self.headers.get('Origin'), self.headers.get('Host')):
            return self._json(403, {'error': 'cross-origin request refused'})
        if path in ('/api/ask', '/api/transcribe', '/api/speak') and self.app.limits:
            given = self.headers.get(CODE_HEADER) or (parse_qs(urlparse(self.path).query).get('code') or [None])[0]
            refused = self.app.limits.admit('ask' if path == '/api/ask' else 'speech', self.client_address[0], given)
            if refused:
                status, body, wait = refused
                if body.get('reason') in ('budget', 'rate_day'):
                    sys.stderr.write(f'[ask-twin] refused: {body["reason"]}\n')
                self.rfile.read(min(int(self.headers.get('Content-Length') or 0), MAX_BODY))   # drain so the client sees the reply
                return self._json(status, body, wait)
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
        from ask_twin.speech import with_speech
        twin = self.app.twin
        type_of = lambda cid: twin.summary(cid) if cid in twin.box else None   # noqa: E731
        try:
            for ev in with_speech(self.app.agent.ask(q, eid, pt, hist), type_of, eid):
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
    def __init__(self, agent, mode, model, twin, stt, port, verbose=False, lan=False, tts=None, limits=None):
        self.agent, self.mode, self.model, self.twin, self.stt, self.port, self.verbose, self.lan = agent, mode, model, twin, stt, port, verbose, lan
        self.tts, self.note, self.limits = tts, None, limits

    def cors_ok(self, origin, host):
        """Exact allow-list: this server's own origin, localhost/127.0.0.1 on this port, or a PUBLIC_ORIGINS entry."""
        if not origin or origin == 'null':
            return False
        if origin in PUBLIC_ORIGINS:
            return True
        o = urlparse(origin)
        if o.path or o.query or o.username:
            return False
        own_scheme = 'https' if self.lan else 'http'
        if host and o.netloc == host and o.scheme == own_scheme:
            return True
        return o.scheme in ('http', 'https') and o.hostname in ('127.0.0.1', 'localhost') and str(o.port) == str(self.port)

    def origin_ok(self, origin, host):
        if not origin:
            return True   # same-origin fetch from older browsers / curl
        return self.cors_ok(origin, host)

    def health(self):
        return {'ok': True, 'mode': self.mode, 'model': self.model, 'note': self.note,
                'index': {'elements': len(self.twin.box), 'layers': len(self.twin.index['layers'])},
                'sensors': {'count': len(self.twin.sensors), 'note': 'demo, simulated'},
                'stt': {'available': bool(self.stt and self.stt.available), 'loaded': bool(self.stt and self.stt.model),
                        'engine': f'faster-whisper {self.stt.model_name}' if self.stt else None, 'error': self.stt.error if self.stt else None},
                'tts': {'available': bool(self.tts and self.tts.available), 'engine': f'macOS say {self.tts.voice or "default voice"} (local)' if self.tts and self.tts.available else None,
                        'voice': self.tts.voice if self.tts else None, 'quality': self.tts.quality if self.tts else None, 'prefer': 'laptop'},
                **(self.limits.public() if self.limits else {})}


def build_app(args, log=print):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from ask_twin.agent import DEFAULT_MODEL, LiveAgent, MockAgent
    from ask_twin.limits import Budget, Limits, make_code
    from ask_twin.tools import Twin
    note = None
    if not args.mock and not os.environ.get('ANTHROPIC_API_KEY'):
        load_env_file(Path(args.env_file))
    if not args.mock and not os.environ.get('ANTHROPIC_API_KEY'):
        if not args.auto:
            sys.stderr.write(NO_KEY_MESSAGE)
            sys.exit(2)
        args.mock, note = True, NO_KEY_NOTE   # --auto: live when a key exists, else scripted answers, said on the page
        log(f'[ask-twin] {NO_KEY_NOTE} (put ANTHROPIC_API_KEY in {DEFAULT_ENV_FILE}, then restart)')
    elif args.mock and not (os.environ.get('ANTHROPIC_API_KEY') or Path(args.env_file).expanduser().is_file()):
        note = NO_KEY_NOTE
    if args.mock:
        mode, model = 'mock', 'mock (scripted, tool-grounded)'
    else:
        try:
            import anthropic
        except ImportError:
            sys.exit(f'The anthropic package is not installed. Run: python3 -m venv ~/.venvs/ask-twin && '
                     f'~/.venvs/ask-twin/bin/pip install anthropic faster-whisper   (or use --mock)')
        mode, model = 'live', args.model or DEFAULT_MODEL
    usage_dir = Path(args.usage_dir).expanduser()
    try:
        usage_dir.resolve().relative_to(ROOT.resolve())
        sys.exit(f'Refusing to keep the usage counter inside the repository ({usage_dir}). Use e.g. {DEFAULT_ENV_FILE.parent}.')
    except ValueError:
        pass
    # mock answers cost nothing: same code and rate-limit paths, counter kept in memory only (budget stays 0)
    budget = Budget(usage_dir, args.daily_tokens, args.per_day, persist=(mode == 'live'))
    limits = Limits(None if args.no_code else (args.code or make_code()), budget, per_minute=args.per_minute)
    twin = Twin(log=log)
    if mode == 'live':
        client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'], max_retries=2, timeout=120)
        agent = LiveAgent(twin, client, model=model, effort=args.effort, max_tokens=args.max_tokens, fallbacks=not args.no_fallbacks,
                          on_usage=budget.add_usage, budget_left=budget.tokens_left)
    else:
        agent = MockAgent(twin)
    stt = None if args.no_stt else STT(args.stt_model, beam_size=args.stt_beam)
    app = App(agent, mode, model, twin, stt, args.port, args.verbose, args.lan, tts=TTS(not args.no_tts, voice=args.voice), limits=limits)
    app.note = note
    return app


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description='Ask-the-twin local demo server')
    ap.add_argument('--mock', action='store_true', help='no API key: scripted answers from the same read-only tools')
    ap.add_argument('--auto', action='store_true', help='live Claude if a key is found, else scripted answers (the page says so)')
    ap.add_argument('--model', default=None, help='Claude model id (default claude-sonnet-5-5; e.g. claude-opus-5-5)')
    ap.add_argument('--effort', default='medium', choices=['low', 'medium', 'high', 'xhigh', 'max'])
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--env-file', default=str(DEFAULT_ENV_FILE), help='file outside the repo with ANTHROPIC_API_KEY=...')
    ap.add_argument('--no-stt', action='store_true', help='disable local speech-to-text (browser Web Speech only)')
    ap.add_argument('--no-tts', action='store_true', help='disable laptop text-to-speech (/api/speak, macOS say)')
    ap.add_argument('--stt-model', default='base.en', help='faster-whisper model (tiny.en, base.en, small.en)')
    ap.add_argument('--stt-beam', type=int, default=5, help='faster-whisper beam size (1 = fastest)')
    ap.add_argument('--voice', default=None, help='macOS voice for /api/speak, e.g. "Zoe (Premium)" or Ava (default: best installed English voice)')
    ap.add_argument('--no-fallbacks', action='store_true', help='do not send the server-side refusal fallback beta')
    ap.add_argument('--lan', action='store_true', help='HTTPS on the private LAN address (Quest on the same Wi-Fi), self-signed dev certificate from scripts/serve_quest_https.py')
    lim = ap.add_argument_group('limits and access (docs/ASK_TWIN.md "Limits and access code")')
    lim.add_argument('--code', default=None, help='access code to require (4-32 letters/digits; default: a random 6-character code each start)')
    lim.add_argument('--no-code', action='store_true', help='no access code (localhost only; refused with --lan)')
    lim.add_argument('--per-minute', type=int, default=10, help='questions per minute per client IP (default 10; 0 = no limit)')
    lim.add_argument('--per-day', type=int, default=300, help='questions per day, whole server (default 300; 0 = no limit)')
    lim.add_argument('--daily-tokens', type=int, default=2_000_000, help='daily token budget, counted from API usage (default 2000000; 0 = no budget)')
    lim.add_argument('--max-tokens', type=int, default=4000, help='max_tokens per model round (default 4000)')
    lim.add_argument('--idle-minutes', type=float, default=120, help='stop after this many minutes without a question (default 120; 0 = never)')
    lim.add_argument('--usage-dir', default=str(DEFAULT_ENV_FILE.parent), help='folder for usage-YYYY-MM-DD.json (outside the repo)')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args(argv)
    if args.code is not None and not re.fullmatch(r'[A-Za-z0-9]{4,32}', args.code):
        ap.error('--code must be 4-32 letters or digits')
    if args.no_code and args.code:
        ap.error('use either --code or --no-code')
    if args.no_code and args.lan:
        ap.error('--no-code is for localhost only; with --lan an access code is required (omit --no-code, or pass --code)')
    if args.max_tokens < 256:
        ap.error('--max-tokens must be at least 256')
    return args


def page_urls(scheme, host, port, code=None, lan=False):
    """The addresses printed at start (with the access code). Keys: laptop, headset, and with --lan: public, trust."""
    c = ('&' + urlencode({'code': code})) if code else ''
    base = f'{scheme}://{host}:{port}'
    out = {'laptop': f'{base}{ENTRY}{c}', 'headset': f'{base}{XR_ENTRY}{c}'}
    if lan:
        out.update(public=f'{PUBLIC_MR}&server={base}{c}', trust=f'{base}/trust')
    return out


def idle_watch(httpd, limits, minutes, log=print, poll=30.0):
    """Stop the server after `minutes` without a question (limits.last_question). Runs in a daemon thread."""
    def run():
        while True:
            time.sleep(min(poll, minutes * 60))
            idle = time.monotonic() - limits.last_question
            if idle >= minutes * 60:
                log(f'[ask-twin] no questions for {minutes:g} min: stopping at {time.strftime("%H:%M")} (--idle-minutes)', flush=True)
                httpd.shutdown()
                return
    t = threading.Thread(target=run, daemon=True, name='ask-twin-idle')
    t.start()
    return t


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
    if app.tts and app.tts.available:
        tip = '' if app.tts.quality in ('premium', 'enhanced') else '  (more natural: download "Zoe (Premium)" or "Ava (Premium)" in System Settings > Accessibility > Spoken Content > System voice > Manage Voices)'
        print(f'[ask-twin] laptop voice: {app.tts.voice or "system default"} · {app.tts.note}{tip}', flush=True)
    lim = app.limits
    urls = page_urls(scheme, host, args.port, lim.code, args.lan)
    pub = lim.public()
    u, L = pub['usage_today'], pub['limits']
    print(f'[ask-twin] access code: {lim.code}   (the links below include it; people without it get "Access code needed")' if lim.code
          else '[ask-twin] access code: off (--no-code, localhost only)', flush=True)
    print(f'[ask-twin] laptop page:  {urls["laptop"]}   (Ctrl+C to stop)', flush=True)
    print(f'[ask-twin] headset page: {urls["headset"]}'
          + ('\n[ask-twin] self-signed dev certificate: accept the warning only for this address; same Wi-Fi required' if args.lan else ''), flush=True)
    if args.lan:
        print(f'[ask-twin] public page + this laptop (Method A): {urls["public"]}'
              f'\n[ask-twin]   first time in the headset: open {urls["trust"]} once and accept the certificate', flush=True)
    print(f'[ask-twin] limits: {L["questions_per_minute_per_client"] or "no"} questions/min per client · {L["questions_per_day"] or "no"} questions/day · '
          f'budget {L["daily_tokens"] or "none"} tokens/day · max_tokens {args.max_tokens}/round'
          + (' · mock: counted in memory, 0 tokens' if app.mode == 'mock' else ''), flush=True)
    print(f'[ask-twin] today ({u["date"]}): {u["questions"]} questions · {u["budget_tokens"]} budget tokens '
          f'(input {u["input_tokens"]}, output {u["output_tokens"]}, cache read {u["cache_read_input_tokens"]}, cache write {u["cache_creation_input_tokens"]})', flush=True)
    if args.idle_minutes > 0:
        stop_at = time.strftime('%H:%M', time.localtime(time.time() + args.idle_minutes * 60))
        print(f'[ask-twin] stops after {args.idle_minutes:g} min without a question (first check: {stop_at}; --idle-minutes 0 keeps it running)', flush=True)
        idle_watch(httpd, lim, args.idle_minutes)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n[ask-twin] stopped')


if __name__ == '__main__':
    main()
