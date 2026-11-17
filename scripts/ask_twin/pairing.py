"""Paired devices for the Ask-the-twin laptop server: pair once with the access code, then connect without typing.

The access code is new on every server start, so a headset would have to retype it every session. Instead, the first time a
device connects with the code, the server gives it a random token (256 bits, secrets.token_urlsafe(32)). The page keeps the
token in its own localStorage and sends it as the X-Ask-Token header; it is accepted wherever the code is accepted (same origin
rules, same rate limits, same daily question and token limits) except for pairing another device.

On the laptop only a SHA-256 hash of each token is stored, in one file outside the repository
(default ~/.config/ask-twin/paired-devices.json, mode 0600). A random token needs no slow hash: there is nothing to guess
from its hash. The file is re-read when it changes, so `ask_twin_server.py --forget-devices` also locks out a running server.
Tokens unused for MAX_IDLE_DAYS expire; at most MAX_DEVICES are kept (the least recently used one is dropped).
Never logged, never written to the repository, never put in a URL.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

FILE_NAME = 'paired-devices.json'
SCHEMA = 'ask-twin-pairings/1'
MAX_DEVICES = 20
MAX_IDLE_DAYS = 30
TOUCH_EVERY_S = 6 * 3600          # last_used is written at most this often per device (no file write per question)
TOKEN_RX = re.compile(r'^[A-Za-z0-9_-]{32,128}$')


def token_hash(token: str) -> str:
    return hashlib.sha256(str(token).encode()).hexdigest()


def device_label(user_agent: str | None) -> str:
    """A short, harmless label from the User-Agent (for --list-devices); never the raw header."""
    ua = str(user_agent or '')
    if 'OculusBrowser' in ua or 'Quest' in ua:
        return 'Quest Browser'
    for key, name in (('Edg/', 'Edge'), ('Chrome/', 'Chrome'), ('Firefox/', 'Firefox'), ('Safari/', 'Safari')):
        if key in ua:
            return name + (' (phone)' if 'Mobile' in ua else '')
    return 'browser'


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _ts(s) -> float | None:
    try:
        return datetime.strptime(str(s), '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


class Pairings:
    """The paired-device file. issue() -> (token, device id); check(token) -> device id or None; forget(token); clear()."""

    def __init__(self, folder, clock=time.time, max_devices=MAX_DEVICES, max_idle_days=MAX_IDLE_DAYS):
        self.folder, self.clock = Path(folder).expanduser(), clock
        self.path = self.folder / FILE_NAME
        self.max_devices, self.max_idle_s = max_devices, max_idle_days * 86400
        self.lock = threading.Lock()
        self.devices, self._stamp = [], None

    # ---- file
    def _stat(self):
        try:
            st = self.path.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _load(self):
        """Re-read the file when it changed (or vanished) since the last read."""
        stamp = self._stat()
        if stamp == self._stamp:
            return
        devices = []
        if stamp is not None:
            try:
                data = json.loads(self.path.read_text())
                for d in data.get('devices', []) if isinstance(data, dict) else []:
                    if isinstance(d, dict) and re.fullmatch(r'[0-9a-f]{64}', str(d.get('sha256', ''))):
                        devices.append({'id': str(d.get('id', ''))[:16], 'sha256': d['sha256'], 'label': str(d.get('label', ''))[:40],
                                        'created': d.get('created'), 'last_used': d.get('last_used')})
            except (OSError, ValueError):
                devices = []   # unreadable file: no device is paired (fails closed)
        self.devices, self._stamp = devices, stamp

    def _save(self):
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(prefix='.paired-', suffix='.json', dir=self.folder)   # created 0600
        with os.fdopen(fd, 'w') as f:
            json.dump({'schema': SCHEMA, 'note': 'SHA-256 hashes of Ask-the-twin device tokens; the tokens themselves are only on the devices',
                       'devices': self.devices}, f, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        self._stamp = self._stat()

    def _expired(self, d, now) -> bool:
        t = _ts(d.get('last_used')) or _ts(d.get('created'))
        return t is None or now - t > self.max_idle_s

    def _prune(self, now) -> bool:
        keep = [d for d in self.devices if not self._expired(d, now)]
        changed = len(keep) != len(self.devices)
        self.devices = keep
        return changed

    def _find(self, token):
        if not token or not TOKEN_RX.match(str(token)):
            return None
        h = token_hash(token)
        hit = None
        for d in self.devices:   # compare every entry in constant time (a demo has a handful)
            if hmac.compare_digest(d['sha256'], h):
                hit = d
        return hit

    # ---- API
    def issue(self, label='browser'):
        with self.lock:
            self._load()
            now = self.clock()
            self._prune(now)
            token = secrets.token_urlsafe(32)
            dev = {'id': secrets.token_hex(4), 'sha256': token_hash(token), 'label': str(label)[:40], 'created': _iso(now), 'last_used': _iso(now)}
            self.devices.append(dev)
            if len(self.devices) > self.max_devices:
                self.devices.sort(key=lambda d: _ts(d.get('last_used')) or 0)
                self.devices = self.devices[-self.max_devices:]
            self._save()
            return token, dev['id']

    def check(self, token):
        """Device id if the token is paired and not expired, else None. Refreshes last_used now and then."""
        with self.lock:
            self._load()
            d = self._find(token)
            if not d:
                return None
            now = self.clock()
            if self._expired(d, now):
                self._prune(now)
                self._save()
                return None
            if now - (_ts(d.get('last_used')) or 0) >= TOUCH_EVERY_S:
                d['last_used'] = _iso(now)
                self._save()
            return d['id']

    def forget(self, token) -> bool:
        with self.lock:
            self._load()
            d = self._find(token)
            if not d:
                return False
            self.devices = [x for x in self.devices if x is not d]
            self._save()
            return True

    def clear(self) -> int:
        with self.lock:
            self._load()
            n = len(self.devices)
            self.devices = []
            self._save()
            return n

    def listing(self) -> list:
        """id, label, created, last_used for each paired device (never the hash)."""
        with self.lock:
            self._load()
            return [{k: d.get(k) for k in ('id', 'label', 'created', 'last_used')} for d in self.devices]

    def count(self) -> int:
        with self.lock:
            self._load()
            return len(self.devices)
