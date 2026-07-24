#!/usr/bin/env python3
"""
build_baseline.py — hour-of-week median baselines + MAD z-score anomaly detection.

Reconstructs per-building hourly kW series, then computes:
  - baseline168: median kW for each (weekday, hour) slot, with sparse-slot
    fallbacks (weekday-class x hour -> hour -> overall median), like
    data/baselines.json tiers but median/MAD-robust instead of mean/std.
  - sigma: robust residual scale (1.4826 * MAD of kw - baseline).
  - current z-score + anomaly flag (|z| > 3).
  - recent24: last 24 h of (kw, baseline, z) for frontend band charts.
  - events: recent episodes of |z| > 3 sustained >= MIN_EVENT_HOURS.

Incremental by design: an accumulated hourly series lives in
data/energy_baseline_cache.json. Each 15-min workflow run appends the latest
snapshot + rolling history (cheap). `--backfill` additionally ingests every
daily archive in data/archive/*.json (used once to seed, or to rebuild).

Level correction: on 2026-07-14 multi-meter summation was fixed, shifting some
buildings (notably grimes) to a higher, correct level. Pre-cutoff samples are
rescaled by median(post)/median(pre) when the level shift is significant, so
old data still informs the weekly shape without dragging the level down.

Timestamps: BMO per-building `timestamp` strings are Pacific local time; all
binning uses those naive local stamps directly (occupancy patterns are local).

Usage:  python scripts/build_baseline.py [--backfill]
Writes: data/energy_baseline.json (published, compact)
        data/energy_baseline_cache.json (accumulated series)
"""
import json
import math
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
CACHE_PATH = os.path.join(DATA, 'energy_baseline_cache.json')
OUT_PATH = os.path.join(DATA, 'energy_baseline.json')

EPOCH = datetime(2026, 1, 1)               # naive-local hour index origin
LEVEL_CUTOFF = datetime(2026, 7, 14)       # multi-meter summation fix
RETAIN_DAYS = 150                          # cache horizon
Z_THRESH = 3.0
MIN_EVENT_HOURS = 2
EVENT_WINDOW_DAYS = 14
MIN_SLOT_N = 3                             # samples needed to trust a 168-slot
MIN_BUILDING_HOURS = 24                    # below this: no baseline published


def hour_index(dt):
    return int((dt - EPOCH).total_seconds() // 3600)


def index_dt(idx):
    return EPOCH + timedelta(hours=idx)


def parse_ts(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    m = n // 2
    return xs[m] if n % 2 else (xs[m - 1] + xs[m]) / 2.0


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


# ── series ingestion ────────────────────────────────────────────────────────

def ingest_sparkline(series, bldg):
    """sparkline = 24 hourly values ending at the building's own PT timestamp."""
    ts = parse_ts(bldg.get('timestamp'))
    spark = bldg.get('sparkline') or []
    if not ts or not spark:
        return
    end = hour_index(ts)
    n = len(spark)
    for i, v in enumerate(spark):
        if isinstance(v, (int, float)) and v > 0:
            series[end - (n - 1 - i)] = round(float(v), 2)


def ingest_history(series, entries):
    """campus_energy_history.json: [{kw, ts}] hourly rolling window."""
    for e in entries or []:
        ts = parse_ts(e.get('ts'))
        v = e.get('kw')
        if ts and isinstance(v, (int, float)) and v > 0:
            series[hour_index(ts)] = round(float(v), 2)


def collect(backfill):
    """building id -> {hour_index: kw}"""
    cache = load_json(CACHE_PATH) or {}
    out = {}
    for bid, ser in (cache.get('series') or {}).items():
        out[bid] = {int(k): v for k, v in ser.items()}

    def series_for(bid):
        return out.setdefault(bid, {})

    if backfill:
        arch = os.path.join(DATA, 'archive')
        for fn in sorted(os.listdir(arch)) if os.path.isdir(arch) else []:
            if fn.startswith('buildings_') or not fn.endswith('.json'):
                continue
            snap = load_json(os.path.join(arch, fn)) or {}
            for bid, b in (snap.get('buildings') or {}).items():
                ingest_sparkline(series_for(bid), b)

    hist = load_json(os.path.join(DATA, 'campus_energy_history.json')) or {}
    for bid, entries in hist.items():
        ingest_history(series_for(bid), entries)

    cur = load_json(os.path.join(DATA, 'campus_energy.json')) or {}
    for bid, b in (cur.get('buildings') or {}).items():
        ingest_sparkline(series_for(bid), b)

    # prune horizon
    floor = hour_index(datetime.now() - timedelta(days=RETAIN_DAYS))
    for bid in out:
        out[bid] = {k: v for k, v in out[bid].items() if k >= floor}
    return out, cur


# ── baseline math ───────────────────────────────────────────────────────────

def level_correct(series):
    """Rescale pre-cutoff samples if the 2026-07-14 metering fix shifted levels."""
    cut = hour_index(LEVEL_CUTOFF)
    pre = [v for k, v in series.items() if k < cut]
    post = [v for k, v in series.items() if k >= cut]
    if len(pre) < 48 or len(post) < 48:
        return series, None
    mp, mq = median(pre), median(post)
    if not mp or mp <= 0:
        return series, None
    ratio = mq / mp
    if 0.8 <= ratio <= 1.25:               # no meaningful shift
        return series, None
    if 0.5 <= ratio <= 2.0:                # moderate shift: rescale old level
        fixed = {k: (round(v * ratio, 2) if k < cut else v) for k, v in series.items()}
        return fixed, {'mode': 'scaled', 'ratio': round(ratio, 3)}
    # Extreme shift (e.g. grimes 1 meter -> 3 meters, ~11x): scaling would just
    # amplify the old series' noise into the baseline — drop pre-cutoff instead.
    fixed = {k: v for k, v in series.items() if k >= cut}
    return fixed, {'mode': 'pre-cutoff-excluded', 'ratio': round(ratio, 3)}


def build_baseline(series):
    """-> (baseline168, sigma, zfn) or (None, None, None) if too sparse."""
    if len(series) < MIN_BUILDING_HOURS:
        return None, None, None
    slots = [[] for _ in range(168)]
    by_class = {}                          # (is_weekend, hour) -> []
    by_hour = [[] for _ in range(24)]
    allv = []
    for idx, v in series.items():
        dt = index_dt(idx)
        dow, hr = dt.weekday(), dt.hour
        slots[dow * 24 + hr].append(v)
        by_class.setdefault((dow >= 5, hr), []).append(v)
        by_hour[hr].append(v)
        allv.append(v)
    overall = median(allv)
    baseline = []
    for s in range(168):
        dow, hr = divmod(s, 24)
        if len(slots[s]) >= MIN_SLOT_N:
            baseline.append(round(median(slots[s]), 1))
        elif len(by_class.get((dow >= 5, hr), [])) >= MIN_SLOT_N:
            baseline.append(round(median(by_class[(dow >= 5, hr)]), 1))
        elif len(by_hour[hr]) >= MIN_SLOT_N:
            baseline.append(round(median(by_hour[hr]), 1))
        else:
            baseline.append(round(overall, 1))
    resid = []
    for idx, v in series.items():
        dt = index_dt(idx)
        resid.append(v - baseline[dt.weekday() * 24 + dt.hour])
    mr = median(resid) or 0.0
    mad = median([abs(r - mr) for r in resid]) or 0.0
    sigma = max(1.4826 * mad, 1.5, 0.05 * (overall or 0))
    sigma = round(sigma, 2)

    def zfn(dt, kw):
        base = baseline[dt.weekday() * 24 + dt.hour]
        return base, round((kw - base) / sigma, 2)

    return baseline, sigma, zfn


def find_events(series, zfn):
    floor = hour_index(datetime.now() - timedelta(days=EVENT_WINDOW_DAYS))
    pts = sorted((k, v) for k, v in series.items() if k >= floor)
    events, run = [], []
    for idx, kw in pts:
        base, z = zfn(index_dt(idx), kw)
        if abs(z) > Z_THRESH:
            if run and idx - run[-1][0] > 1:   # gap breaks the episode
                if len(run) >= MIN_EVENT_HOURS:
                    events.append(run)
                run = []
            run.append((idx, kw, z))
        else:
            if len(run) >= MIN_EVENT_HOURS:
                events.append(run)
            run = []
    if len(run) >= MIN_EVENT_HOURS:
        events.append(run)
    out = []
    for ep in events[-8:]:
        zs = [p[2] for p in ep]
        peak = max(zs, key=abs)
        out.append({
            'start': index_dt(ep[0][0]).strftime('%Y-%m-%d %H:%M'),
            'end': index_dt(ep[-1][0]).strftime('%Y-%m-%d %H:%M'),
            'hours': len(ep),
            'peak_z': peak,
            'dir': 'high' if peak > 0 else 'low',
        })
    return out


def main():
    backfill = '--backfill' in sys.argv
    all_series, current_snap = collect(backfill)
    now = datetime.now()
    buildings_out, corrections = {}, {}
    cache_out = {}

    for bid, raw in sorted(all_series.items()):
        if not raw:
            continue
        cache_out[bid] = {str(k): v for k, v in sorted(raw.items())}
        series, ratio = level_correct(raw)
        if ratio:
            corrections[bid] = ratio
        baseline, sigma, zfn = build_baseline(series)
        if baseline is None:
            continue

        cur_b = (current_snap.get('buildings') or {}).get(bid) or {}
        cur_kw = cur_b.get('kw')
        cur_ts = parse_ts(cur_b.get('timestamp'))
        current = {'kw': None, 'base': None, 'z': None, 'anomaly': False, 'ts': None}
        if isinstance(cur_kw, (int, float)) and cur_kw > 0 and cur_ts:
            base, z = zfn(cur_ts, cur_kw)
            current = {'kw': round(cur_kw, 1), 'base': base, 'z': z,
                       'anomaly': abs(z) > Z_THRESH,
                       'ts': cur_ts.strftime('%Y-%m-%d %H:%M')}

        recent = []
        for idx, kw in sorted(series.items())[-24:]:
            dt = index_dt(idx)
            base, z = zfn(dt, kw)
            recent.append({'ts': dt.strftime('%Y-%m-%d %H:%M'),
                           'kw': kw, 'base': base, 'z': z})

        buildings_out[bid] = {
            'name': cur_b.get('name') or bid,
            'n_hours': len(series),
            'sigma': sigma,
            'baseline168': baseline,
            'current': current,
            'recent24': recent,
            'events': find_events(series, zfn),
        }

    out = {
        '_schema': 'energy-baseline/1',
        '_doc': 'Hour-of-week median baseline + MAD z-scores. baseline168 is '
                'indexed weekday*24+hour (Mon=0, local building time). '
                'anomaly = |z| > %.1f. Built by scripts/build_baseline.py.' % Z_THRESH,
        'generated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'z_threshold': Z_THRESH,
        'level_corrections': corrections,
        'buildings': buildings_out,
    }
    with open(OUT_PATH, 'w') as f:
        json.dump(out, f, separators=(',', ':'))
    with open(CACHE_PATH, 'w') as f:
        json.dump({'_doc': 'accumulated hourly kW series (naive PT, hours since 2026-01-01)',
                   'series': cache_out}, f, separators=(',', ':'))

    anom = [b for b, v in buildings_out.items() if v['current']['anomaly']]
    print('baseline: %d buildings, %d anomalous now %s' %
          (len(buildings_out), len(anom), anom or ''))


if __name__ == '__main__':
    main()
