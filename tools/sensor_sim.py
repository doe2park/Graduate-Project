#!/usr/bin/env python3
"""Deterministic DEMO sensor feed (twin/sensors/FEED.md). Writes snapshot files in the common feed format:

    python3 tools/sensor_sim.py --at 2026-10-26T10:00:00-07:00 --out work/sensor-feed          # latest.json
    python3 tools/sensor_sim.py --at 2026-10-26T00:00:00-07:00 --out work/sensor-feed --history  # + history/2026-10-26.json (hourly)

Every observation is simulated: source "demo-sim", simulated: true. Same math as twin/sensors/feed.js (the viewer's
client-side simulator); tests/sensor-feed.test.cjs checks that both agree. No network, no credentials, no schedule:
run it by hand. Never point --out at the machine-written `data` branch.
"""
import argparse, json, math, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / 'twin' / 'sensors' / 'registry.json'
TZ = ZoneInfo('America/Los_Angeles')
FEED_SCHEMA = 'grimes-sensor-feed/1'
DAY = 86400000
TREND_START = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
QUALITY, SOURCES = ('good', 'suspect', 'missing'), ('demo-sim', 'bms', 'bmo', 'gateway', 'fiber')


def fnv1a(s):
    h = 0x811c9dc5
    for b in s.encode('utf-8'):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def noise(sid, bucket): return fnv1a(f'{sid}|{bucket}') / 4294967296 * 2 - 1


def local_hour(ms):
    d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(TZ)
    return d.hour + d.minute / 60 + d.second / 3600


def occ(h): return 0 if h < 7 or h >= 19 else (h - 7) / 2 if h < 9 else 1 if h < 17 else (19 - h) / 2
def diurnal(h): return math.sin(2 * math.pi * (h - 9) / 24)
def trend(ms): return min(1, max(0, (ms - TREND_START) / DAY / 56))
def vib_base(ms): return 1.2 + 0.9 * trend(ms)
def rnd(v, d): f = 10 ** d; return math.floor(v * f + 0.5) / f


SIM = {
    'leak-dts': lambda h, n, t: (30.6 + 0.6 * diurnal(h) + 0.2 * n, 2),
    'leak-alert': lambda h, n, t: (8.8 + 0.2 * n, 2),
    'leak-vibration': lambda h, n, t: (0.7 + 0.2 * occ(h) + 0.05 * n, 2),
    'leak-puck': lambda h, n, t: (0, 0),
    'hvac-airflow': lambda h, n, t: (330 + 90 * occ(h) + 12 * n if occ(h) > 0 else 140 + 5 * n, 0),
    'hvac-iaq': lambda h, n, t: (450 + 380 * occ(h) + 15 * n, 0),
    'hvac-comfort': lambda h, n, t: (0.3 + 2.1 * occ(h) + 0.15 * n, 2),
    'hvac-damper': lambda h, n, t: (30 + 42 * occ(h) + 2 * n, 0),
    'water-flow': lambda h, n, t: (0.6 + 0.02 * n if 1 <= h < 4 else 0.08 + 0.06 * abs(n) if occ(h) > 0 else 0.01 * abs(n), 3),
    'water-puck': lambda h, n, t: (0, 0),
    'water-alert': lambda h, n, t: (0.6 + 0.01 * n, 3),
    'power-ct': lambda h, n, t: (0.2 + 0.33 * occ(h) + 0.02 * n, 3),
    'power-unit': lambda h, n, t: (0.35 + 0.3 * occ(h) + 0.03 * n, 2),
    'power-bmo': lambda h, n, t: (175 + 48 * occ(h) + 3 * n, 0),
    'fan-vibration': lambda h, n, t: (vib_base(t) + 0.08 * n, 2),
    'fan-bearing': lambda h, n, t: (46 + 10 * trend(t) + 1.5 * diurnal(h) + 0.3 * n, 2),
    'fan-alert': lambda h, n, t: ((vib_base(t) - vib_base(t - 28 * DAY)) / vib_base(t - 28 * DAY) * 100, 0),
}


def iso(ms):
    ms = int(ms)
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + f'{ms % 1000:03d}Z'


def simulate(sensor, now_ms):
    iv = int(sensor['sampling_interval_s'] * 1000)
    t = int(now_ms) // iv * iv
    f = SIM.get(sensor['id'])
    if f is None:
        return {'sensor_id': sensor['id'], 'ts': None, 'value': None, 'unit': sensor['unit'], 'quality': 'missing', 'source': 'demo-sim', 'reason': 'no simulation model'}
    v, d = f(local_hour(t), noise(sensor['id'], t // iv), t)
    return {'sensor_id': sensor['id'], 'ts': iso(t), 'value': rnd(v, d), 'unit': sensor['unit'], 'quality': 'good', 'source': 'demo-sim', 'simulated': True}


def demo_sensors(registry):
    return [s for s in registry['sensors'] if s['install_status'] != 'retired' and s['data_source'] == 'demo-sim']


def snapshot(registry, now_ms):
    return {'schema': FEED_SCHEMA, 'generated_at': iso(now_ms), 'simulated': True, 'source': 'demo-sim',
            'note': 'DEMO: simulated observations (tools/sensor_sim.py). No sensor is installed; not measurements.',
            'observations': [simulate(s, now_ms) for s in demo_sensors(registry)]}


def valid_observation(o):
    if not isinstance(o, dict) or not isinstance(o.get('sensor_id'), str) or o.get('quality') not in QUALITY or o.get('source') not in SOURCES or not isinstance(o.get('unit'), str):
        return False
    if o['quality'] == 'missing':
        return o.get('value') is None
    import re
    return isinstance(o.get('value'), (int, float)) and isinstance(o.get('ts'), str) and \
        re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d(\.\d+)?)?(Z|[+-]\d\d:\d\d)', o['ts']) is not None and \
        (o['source'] != 'demo-sim' or o.get('simulated') is True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--at', help='ISO time with timezone (default: now)')
    ap.add_argument('--out', required=True, help='output folder (never the data branch)')
    ap.add_argument('--history', action='store_true', help='also write history/<local date>.json, hourly over that local day')
    a = ap.parse_args(argv)
    now = datetime.fromisoformat(a.at) if a.at else datetime.now(timezone.utc)
    if now.tzinfo is None:
        sys.exit('--at needs a timezone, e.g. 2026-10-26T10:00:00-07:00')
    now_ms = int(now.timestamp() * 1000)
    reg = json.loads(REGISTRY.read_text())
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    snap = snapshot(reg, now_ms)
    assert all(valid_observation(o) for o in snap['observations'])
    (out / 'latest.json').write_text(json.dumps(snap, indent=1) + '\n')
    if a.history:
        day = now.astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        hours = [int((day + timedelta(hours=k)).timestamp() * 1000) for k in range(24)]
        hist = {'schema': FEED_SCHEMA, 'date': day.date().isoformat(), 'simulated': True, 'source': 'demo-sim',
                'observations': [simulate(s, t) for t in hours for s in demo_sensors(reg)]}
        (out / 'history').mkdir(exist_ok=True)
        (out / 'history' / f'{day.date().isoformat()}.json').write_text(json.dumps(hist, indent=1) + '\n')
    print(f'wrote {out / "latest.json"} ({len(snap["observations"])} simulated observations)')


if __name__ == '__main__':
    main()
