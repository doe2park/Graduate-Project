#!/usr/bin/env python3
"""
towt_baseline.py — LBNL TOWT-style weather-normalized baseline.

Model (Mathieu et al., LBNL-3939E, simplified single-regime):
    kW(t) ~ sum_i a_i * TOW_i(t)  +  sum_j b_j * Tc_j(T_out(t))
where TOW_i are 168 hour-of-week indicators and Tc_j are continuous
piecewise-linear outdoor-temperature components with knots at
TEMP_KNOTS (deg C). Fit by ridge-regularized least squares (numpy).

Data:
  - hourly kW series: data/energy_baseline_cache.json (built by
    build_baseline.py; hours since 2026-01-01, naive Pacific time)
  - level corrections: reused from data/energy_baseline.json so both
    baselines see the same corrected series
  - hourly outdoor temp for Berkeley (37.873, -122.259): open-meteo
    archive + forecast APIs, cached in data/weather_cache.json so each
    15-min run only fetches what's missing. DESIGNED TO RUN ON THE
    GITHUB ACTIONS RUNNER (free egress). Offline/sandbox runs keep
    working from the cache; if coverage is insufficient the script
    exits 0 without writing output (frontends fall back to the median
    baseline in energy_baseline.json).

Output: data/towt_baseline.json — per building: use_towt quality flag
(ASHRAE G14-style: CV-RMSE <= 30 %, >= 14 days, >= 80 % temp coverage),
CV-RMSE / NMBE, robust sigma, temp coefficients, current z, recent24
(same shape as energy_baseline.json's so frontends can swap sources).

Env overrides (testing): TOWT_WEATHER_CACHE, TOWT_OUT, TOWT_SKIP_FETCH=1.
Usage: python scripts/towt_baseline.py
"""
import json
import math
import os
import sys
from datetime import datetime, timedelta

try:
    import numpy as np
except ImportError:
    print('towt: numpy unavailable — skipping (median baseline still active)')
    sys.exit(0)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
CACHE_PATH = os.path.join(DATA, 'energy_baseline_cache.json')
EB_PATH = os.path.join(DATA, 'energy_baseline.json')
WEATHER_CACHE = os.environ.get('TOWT_WEATHER_CACHE', os.path.join(DATA, 'weather_cache.json'))
OUT_PATH = os.environ.get('TOWT_OUT', os.path.join(DATA, 'towt_baseline.json'))
SKIP_FETCH = os.environ.get('TOWT_SKIP_FETCH') == '1'

EPOCH = datetime(2026, 1, 1)           # same hour-index convention as build_baseline
LAT, LON = 37.873, -122.259            # UC Berkeley campus
TZ = 'America/Los_Angeles'
TEMP_KNOTS = [10.0, 14.0, 18.0, 22.0, 26.0]
RIDGE = 1e-3
Z_THRESH = 3.0
MIN_HOURS = 336                        # >= 14 days
MAX_CVRMSE = 0.30                      # ASHRAE Guideline 14, hourly
MIN_TEMP_COVER = 0.80


def hour_index(dt):
    return int((dt - EPOCH).total_seconds() // 3600)


def index_dt(idx):
    return EPOCH + timedelta(hours=idx)


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


# ── weather ─────────────────────────────────────────────────────────────────

def fetch_weather(need_lo, need_hi, temps):
    """Fill temps{idx: degC} from open-meteo for the missing span. Runner-only."""
    if SKIP_FETCH:
        return
    try:
        import requests
    except ImportError:
        return
    missing = [i for i in range(need_lo, need_hi + 1) if str(i) not in temps]
    if not missing:
        return
    lo_d = index_dt(min(missing)).date()
    hi_d = index_dt(max(missing)).date()
    today = datetime.now().date()

    def grab(url, params):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            j = r.json()
            times = j.get('hourly', {}).get('time', [])
            vals = j.get('hourly', {}).get('temperature_2m', [])
            for t, v in zip(times, vals):
                if v is None:
                    continue
                idx = hour_index(datetime.strptime(t, '%Y-%m-%dT%H:%M'))
                temps[str(idx)] = round(float(v), 1)
        except Exception as e:
            print('towt: weather fetch failed (%s) — continuing on cache' % e)

    base = dict(latitude=LAT, longitude=LON, hourly='temperature_2m', timezone=TZ)
    archive_end = today - timedelta(days=3)
    if lo_d <= archive_end:
        grab('https://archive-api.open-meteo.com/v1/archive',
             dict(base, start_date=str(lo_d), end_date=str(min(hi_d, archive_end))))
    if hi_d > archive_end:
        grab('https://api.open-meteo.com/v1/forecast',
             dict(base, past_days=7, forecast_days=1))


# ── model ───────────────────────────────────────────────────────────────────

def temp_components(t):
    """Continuous piecewise-linear basis: len(TEMP_KNOTS)+1 columns."""
    k = TEMP_KNOTS
    out = [min(t, k[0])]
    for j in range(len(k) - 1):
        out.append(max(0.0, min(t, k[j + 1]) - k[j]))
    out.append(max(0.0, t - k[-1]))
    return out


def corrected_series(raw, corr):
    cut = hour_index(datetime(2026, 7, 14))
    if not corr:
        return raw
    mode, ratio = corr.get('mode'), corr.get('ratio', 1.0)
    if mode == 'scaled':
        return {k: (round(v * ratio, 2) if k < cut else v) for k, v in raw.items()}
    if mode == 'pre-cutoff-excluded':
        return {k: v for k, v in raw.items() if k >= cut}
    return raw


def fit_building(series, temps):
    """-> result dict or None."""
    pts = [(i, kw, float(temps[str(i)])) for i, kw in sorted(series.items()) if str(i) in temps]
    if len(pts) < MIN_HOURS or len(pts) < MIN_TEMP_COVER * len(series):
        return None
    tow_slots = sorted({index_dt(i).weekday() * 24 + index_dt(i).hour for i, _, _ in pts})
    slot_col = {s: c for c, s in enumerate(tow_slots)}
    ntc = len(TEMP_KNOTS) + 1
    ncol = len(tow_slots) + ntc
    X = np.zeros((len(pts), ncol))
    y = np.zeros(len(pts))
    for r, (i, kw, t) in enumerate(pts):
        dt = index_dt(i)
        X[r, slot_col[dt.weekday() * 24 + dt.hour]] = 1.0
        X[r, len(tow_slots):] = temp_components(t)
        y[r] = kw
    A = X.T @ X + RIDGE * np.eye(ncol)
    beta = np.linalg.solve(A, X.T @ y)
    pred = X @ beta
    res = y - pred
    mean_y = float(y.mean())
    if mean_y <= 0:
        return None
    rmse = float(np.sqrt((res ** 2).mean()))
    cvrmse = rmse / mean_y
    nmbe = float(res.sum() / (len(res) * mean_y))
    mad = float(np.median(np.abs(res - np.median(res))))
    sigma = max(1.4826 * mad, 1.5, 0.05 * mean_y)

    def predict(dt, t):
        slot = dt.weekday() * 24 + dt.hour
        v = beta[slot_col[slot]] if slot in slot_col else float(np.median(beta[:len(tow_slots)]))
        return float(v + np.dot(beta[len(tow_slots):], temp_components(t)))

    return {
        'beta_tow': {str(s): round(float(beta[c]), 2) for s, c in slot_col.items()},
        'temp_coeffs': [round(float(b), 3) for b in beta[len(tow_slots):]],
        'predict': predict,
        'n_hours': len(pts),
        'cvrmse': round(cvrmse, 3),
        'nmbe': round(nmbe, 4),
        'sigma': round(sigma, 2),
    }


def nearest_temp(temps, idx, radius=2):
    for d in range(radius + 1):
        for i in (idx - d, idx + d):
            if str(i) in temps:
                return float(temps[str(i)])
    return None


def main():
    cache = load_json(CACHE_PATH)
    eb = load_json(EB_PATH) or {}
    if not cache or not cache.get('series'):
        print('towt: no series cache — run build_baseline.py first')
        return
    corrections = eb.get('level_corrections', {})

    wc = load_json(WEATHER_CACHE) or {}
    temps = wc.get('hours', {})
    all_idx = [int(i) for ser in cache['series'].values() for i in ser.keys()]
    if not all_idx:
        print('towt: empty series')
        return
    fetch_weather(min(all_idx), hour_index(datetime.now()) + 1, temps)
    try:
        with open(WEATHER_CACHE, 'w') as f:
            json.dump({'_doc': 'hourly temp degC, Berkeley, hours since 2026-01-01 (naive PT), open-meteo',
                       'hours': temps}, f, separators=(',', ':'))
    except Exception:
        pass
    if not temps:
        print('towt: no temperature data available — skipping output (median fallback stays active)')
        return

    cur_snap = load_json(os.path.join(DATA, 'campus_energy.json')) or {}
    out_b = {}
    for bid, raw in sorted(cache['series'].items()):
        series = corrected_series({int(k): v for k, v in raw.items()}, corrections.get(bid))
        fit = fit_building(series, temps)
        if not fit:
            continue
        use = fit['cvrmse'] <= MAX_CVRMSE and fit['n_hours'] >= MIN_HOURS

        cur_b = (cur_snap.get('buildings') or {}).get(bid) or {}
        current = {'kw': None, 'base': None, 'z': None, 'anomaly': False, 'ts': None}
        kw, ts_s = cur_b.get('kw'), cur_b.get('timestamp')
        if isinstance(kw, (int, float)) and kw > 0 and ts_s:
            try:
                ts = datetime.strptime(str(ts_s)[:19], '%Y-%m-%d %H:%M:%S')
                t = nearest_temp(temps, hour_index(ts))
                if t is not None:
                    base = fit['predict'](ts, t)
                    z = (kw - base) / fit['sigma']
                    current = {'kw': round(kw, 1), 'base': round(base, 1), 'z': round(z, 2),
                               'anomaly': abs(z) > Z_THRESH, 'ts': ts.strftime('%Y-%m-%d %H:%M')}
            except ValueError:
                pass

        recent = []
        for idx, kw_v in sorted(series.items())[-24:]:
            t = nearest_temp(temps, idx)
            if t is None:
                continue
            dt = index_dt(idx)
            base = fit['predict'](dt, t)
            recent.append({'ts': dt.strftime('%Y-%m-%d %H:%M'), 'kw': kw_v,
                           'base': round(base, 1), 'z': round((kw_v - base) / fit['sigma'], 2),
                           'temp': t})

        out_b[bid] = {
            'use_towt': bool(use),
            'n_hours': fit['n_hours'],
            'cvrmse': fit['cvrmse'],
            'nmbe': fit['nmbe'],
            'sigma': fit['sigma'],
            'temp_knots': TEMP_KNOTS,
            'temp_coeffs': fit['temp_coeffs'],
            'current': current,
            'recent24': recent,
        }

    out = {
        '_schema': 'towt-baseline/1',
        '_doc': 'TOWT-style weather-normalized baseline: 168 time-of-week indicators + '
                'piecewise-linear outdoor-temp terms (knots degC), ridge least squares. '
                'use_towt = CV-RMSE<=%.2f & n>=%d h. Frontends fall back to '
                'energy_baseline.json (median) when absent or use_towt=false.' % (MAX_CVRMSE, MIN_HOURS),
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'z_threshold': Z_THRESH,
        'buildings': out_b,
    }
    with open(OUT_PATH, 'w') as f:
        json.dump(out, f, separators=(',', ':'))
    good = [b for b, v in out_b.items() if v['use_towt']]
    print('towt: %d buildings fit, %d pass quality (%s)' % (len(out_b), len(good), ','.join(good) or '-'))


if __name__ == '__main__':
    main()
