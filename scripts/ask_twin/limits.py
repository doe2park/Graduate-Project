"""Demo limits for the Ask-the-twin laptop server: access code, rate limits, daily token budget, idle shutdown.

Sensible, not strict: the point is that the owner can let people try the twin during a demo without strangers on the same
Wi-Fi using it and without a runaway bill. Everything is in memory except the daily usage counter, which is a small JSON
file outside the repository (default ~/.config/ask-twin/usage-YYYY-MM-DD.json, local date) so a restart does not reset it.

  access code   random 6 characters (no 0/O, 1/I/L) unless --code is given; --no-code turns it off (localhost only).
                Compared case-insensitively in constant time. Wrong codes are rate limited per client IP.
  rate limits   per client IP: questions per minute; whole server: questions per day; speech endpoints per IP per minute.
  token budget  counted from each API response's usage: input + cache writes + output + cache reads / 10
                (cache reads are billed at about a tenth of the input price). When today's count reaches the budget,
                /api/ask answers 429 without calling the API, and a running answer stops before its next model round.
"""
from __future__ import annotations

import hmac
import json
import math
import os
import re
import secrets
import tempfile
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta
from pathlib import Path

ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'   # no 0/O, 1/I/L: easy to read aloud and type on a headset
CODE_LEN = 6
CODE_RX = re.compile(r'^[A-Za-z0-9]{4,32}$')
USAGE_KEYS = ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')

DEFAULTS = {'per_minute': 10, 'per_day': 300, 'daily_tokens': 2_000_000, 'speech_per_minute': 30, 'bad_codes_per_minute': 10}


def make_code(n: int = CODE_LEN) -> str:
    return ''.join(secrets.choice(ALPHABET) for _ in range(n))


def normalize_code(s) -> str:
    """What the user typed or the URL carried -> canonical form (upper case, spaces and dashes dropped)."""
    return re.sub(r'[\s-]+', '', str(s or '')).upper()[:64]


def code_matches(expected: str, given) -> bool:
    """Constant-time comparison of the normalized codes (hmac.compare_digest on equal-type bytes)."""
    return hmac.compare_digest(normalize_code(expected).encode(), normalize_code(given).encode())


def budget_tokens(usage: dict) -> int:
    """The budget count of one response's usage: input + cache writes + output, cache reads at one tenth (rounded up)."""
    u = {k: int(usage.get(k) or 0) for k in USAGE_KEYS}
    return u['input_tokens'] + u['cache_creation_input_tokens'] + u['output_tokens'] + math.ceil(u['cache_read_input_tokens'] / 10)


def seconds_to_midnight(now: datetime | None = None) -> int:
    now = now or datetime.now()
    nxt = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    return max(1, int((nxt - now).total_seconds()))


class Window:
    """Sliding-window counter per key: at most `limit` hits in `seconds`."""

    def __init__(self, limit: int, seconds: float = 60.0, clock=time.monotonic):
        self.limit, self.seconds, self.clock = limit, seconds, clock
        self.hits: dict[str, deque] = {}
        self.lock = threading.Lock()

    def hit(self, key: str) -> int:
        """Record a hit; returns 0 if allowed, else the seconds to wait (the hit is not recorded)."""
        if self.limit <= 0:
            return 0
        with self.lock:
            now, q = self.clock(), self.hits.setdefault(key, deque())
            while q and now - q[0] >= self.seconds:
                q.popleft()
            if len(q) >= self.limit:
                return max(1, math.ceil(self.seconds - (now - q[0])))
            q.append(now)
            if len(self.hits) > 4096:   # forget idle keys (a demo has a handful of clients)
                for k in [k for k, v in self.hits.items() if not v or now - v[-1] >= self.seconds][:2048]:
                    self.hits.pop(k, None)
            return 0


class Budget:
    """Today's questions and tokens, persisted as usage-YYYY-MM-DD.json in `folder` (persist=False: memory only, mock mode).
    Rolls over by local date: a new day starts from that day's file (or zero)."""

    def __init__(self, folder: Path, daily_tokens: int, per_day: int, persist: bool = True, today=date.today):
        self.folder, self.daily_tokens, self.per_day, self.persist, self.today = Path(folder).expanduser(), daily_tokens, per_day, persist, today
        self.lock = threading.Lock()
        self.day, self.data = None, None
        self._roll()

    def path(self, day: str) -> Path:
        return self.folder / f'usage-{day}.json'

    @staticmethod
    def _empty(day):
        return {'date': day, 'questions': 0, 'budget_tokens': 0, **{k: 0 for k in USAGE_KEYS}}

    def _roll(self):
        day = self.today().isoformat()
        if day == self.day:
            return
        data = self._empty(day)
        if self.persist:
            try:
                saved = json.loads(self.path(day).read_text())
                for k in data:
                    if k != 'date' and isinstance(saved.get(k), int):
                        data[k] = saved[k]
            except (OSError, ValueError):
                pass
        self.day, self.data = day, data

    def _save(self):
        if not self.persist:
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.usage-', suffix='.json', dir=self.folder)
        with os.fdopen(fd, 'w') as f:
            json.dump(self.data, f, indent=1)
        os.replace(tmp, self.path(self.day))   # atomic rename over the old counter

    def snapshot(self) -> dict:
        with self.lock:
            self._roll()
            return dict(self.data, daily_tokens=self.daily_tokens, per_day=self.per_day)

    def tokens_left(self) -> int:
        with self.lock:
            self._roll()
            return self.daily_tokens - self.data['budget_tokens'] if self.daily_tokens > 0 else 1 << 60

    def check(self):
        """None if a new question may start, else (reason, message). Does not count anything."""
        with self.lock:
            self._roll()
            if self.per_day > 0 and self.data['questions'] >= self.per_day:
                return 'rate_day', f'Daily limit reached ({self.per_day} questions today). It resets at midnight.'
            if self.daily_tokens > 0 and self.data['budget_tokens'] >= self.daily_tokens:
                return 'budget', 'Daily budget reached for the AI answers. It resets at midnight.'
        return None

    def add_question(self):
        with self.lock:
            self._roll()
            self.data['questions'] += 1
            self._save()

    def add_usage(self, usage: dict):
        """usage: one API response's usage fields (response.usage.input_tokens, ...). Adds to today's counter."""
        with self.lock:
            self._roll()
            for k in USAGE_KEYS:
                self.data[k] += int(usage.get(k) or 0)
            self.data['budget_tokens'] += budget_tokens(usage)
            self._save()


class Limits:
    """Access code + rate limits + budget for the API endpoints. admit() returns None or (http status, json body, retry s)."""

    def __init__(self, code: str | None, budget: Budget, per_minute=DEFAULTS['per_minute'],
                 speech_per_minute=DEFAULTS['speech_per_minute'], bad_codes_per_minute=DEFAULTS['bad_codes_per_minute'],
                 clock=time.monotonic):
        self.code, self.budget = (normalize_code(code) or None) if code else None, budget
        self.per_minute = per_minute
        self.asks = Window(per_minute, 60, clock)
        self.speech = Window(speech_per_minute, 60, clock)
        self.bad = Window(bad_codes_per_minute, 60, clock)
        self.last_question = time.monotonic()

    @property
    def code_required(self) -> bool:
        return bool(self.code)

    def admit(self, kind: str, ip: str, given_code=None):
        """kind: 'ask' (spends API credits) or 'speech' (local speech-to-text / text-to-speech)."""
        if self.code:
            if not given_code or not code_matches(self.code, given_code):
                wait = self.bad.hit(ip)
                if wait:
                    return 429, {'error': f'Too many wrong access codes. Wait {wait} s, then use the link printed in the laptop terminal.',
                                 'reason': 'rate_bad_code', 'retry_after_s': wait}, wait
                if not given_code:
                    return 401, {'error': 'Access code needed: open the link printed in the laptop terminal (it ends with &code=...).',
                                 'reason': 'code_required'}, None
                return 401, {'error': 'Wrong access code: check the code printed in the laptop terminal.', 'reason': 'code_wrong'}, None
        if kind == 'ask':
            refused = self.budget.check()
            if refused:
                wait = seconds_to_midnight()
                return 429, {'error': refused[1], 'reason': refused[0], 'retry_after_s': wait}, wait
            wait = self.asks.hit(ip)
            if wait:
                return 429, {'error': f'Easy there: at most {self.per_minute} questions per minute. Try again in {wait} s.',
                             'reason': 'rate_ip', 'retry_after_s': wait}, wait
            self.budget.add_question()
            self.last_question = time.monotonic()
            return None
        wait = self.speech.hit(ip)
        if wait:
            return 429, {'error': f'Too many voice requests. Try again in {wait} s.', 'reason': 'rate_speech', 'retry_after_s': wait}, wait
        return None

    def public(self) -> dict:
        """Numbers and flags only, for /api/health and the banner (never the code)."""
        u = self.budget.snapshot()
        return {'access': {'code_required': self.code_required},
                'limits': {'questions_per_minute_per_client': self.per_minute, 'questions_per_day': self.budget.per_day,
                           'daily_tokens': self.budget.daily_tokens},
                'usage_today': {'date': u['date'], 'questions': u['questions'], 'budget_tokens': u['budget_tokens'],
                                **{k: u[k] for k in USAGE_KEYS}}}
