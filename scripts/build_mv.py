#!/usr/bin/env python3
"""
build_mv.py — measurement & verification series for Grimes.

Reads the daily `buildings_YYYY-MM-DD.json` archives (cumulative
kwh_delivered counters on meters 3/76/77) plus the LEED design figures,
and writes data/mv_grimes.json for the live Design-vs-Actual page.

Method (`counter_interpolated_pacific_midnight`): the archive holds one
snapshot per UTC day taken at whatever time the last run happened, so
consecutive snapshots are NOT calendar days apart. Each snapshot is placed at
its own meter timestamp (naive America/Los_Angeles wall time); the cumulative
counter is interpolated linearly (constant draw between two snapshots) to each
Pacific midnight, and a day's energy is the difference between its two
midnights. Only COMPLETE Pacific days are emitted -- the current, still-running
day never enters the averages. Brackets longer than 3 days, counter resets and
DST-ambiguous stamps yield no row. Counter deltas are revenue-grade, but the
within-interval profile is assumed flat, so individual days carry some
smearing between neighbours; averages over many days are unaffected.

Never raises on bad files; a partial archive just yields a shorter series.
"""
import json
import glob
import os
import datetime as dt
from collections import defaultdict
from zoneinfo import ZoneInfo

METERS = ("3", "76", "77")
DATA_DIR = "data"
TS_FMT = "%Y-%m-%d %H:%M:%S"
PT = ZoneInfo("America/Los_Angeles")
MAX_BRACKET = dt.timedelta(hours=72)
JITTER_KWH = 5            # tolerate tiny counter jitter
METHOD = "counter_interpolated_pacific_midnight"


def pacific_now():
    return dt.datetime.now(dt.timezone.utc).astimezone(PT).replace(tzinfo=None)


def parse_ts(s):
    try:
        return dt.datetime.strptime(str(s).strip()[:19], TS_FMT)
    except ValueError:
        return None


def ambiguous(t):
    return t.replace(tzinfo=PT, fold=0).utcoffset() != t.replace(tzinfo=PT, fold=1).utcoffset()


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def read_snapshots():
    """-> sorted [(naive PT datetime, {meter: kWh})], one per distinct meter timestamp."""
    seen = {}
    for f in sorted(glob.glob(os.path.join(DATA_DIR, "archive", "buildings_*.json"))):
        d = load(f)
        if not isinstance(d, dict):
            continue
        row, stamps = {}, []
        for mid, m in (d.get("meters") or {}).items():
            latest = (m or {}).get("latest") or {}
            k = latest.get("kwh_delivered")
            t = parse_ts(latest.get("timestamp"))
            if mid in METERS and k and t:
                row[mid] = k
                stamps.append(t)
        if all(m in row for m in METERS):
            t = max(stamps)
            if not ambiguous(t) and t not in seen:
                seen[t] = row
    return sorted(seen.items())


def counter_at(snaps, t):
    """Interpolated {meter: kWh} at t, or None if t is not inside a sane bracket."""
    for (ta, ca), (tb, cb) in zip(snaps, snaps[1:]):
        if ta <= t <= tb:
            span = tb - ta
            if span <= dt.timedelta(0) or span > MAX_BRACKET:
                return None
            if any(cb[m] - ca[m] < -JITTER_KWH for m in METERS):
                return None                      # counter reset / replaced meter
            f = (t - ta) / span
            return {m: ca[m] + (cb[m] - ca[m]) * f for m in METERS}
    return None


def daily_rows(snaps, today):
    rows = []
    if len(snaps) < 2:
        return rows
    day = snaps[0][0].date()
    while day < today:
        c0 = counter_at(snaps, dt.datetime.combine(day, dt.time()))
        c1 = counter_at(snaps, dt.datetime.combine(day + dt.timedelta(days=1), dt.time()))
        if c0 and c1:
            e = {m: c1[m] - c0[m] for m in METERS}
            if all(v >= -JITTER_KWH for v in e.values()):
                rows.append({
                    "d": day.isoformat(),
                    "t": round(sum(e.values()), 1),
                    "m3": round(e["3"], 1),
                    "m76": round(e["76"], 1),
                    "m77": round(e["77"], 1),
                    "we": day.weekday() >= 5,       # Pacific calendar date
                })
        day += dt.timedelta(days=1)
    return rows


def daily_peaks():
    """Pacific date -> max total kW (sum of the three meters in the same minute)."""
    buckets = defaultdict(dict)
    for f in sorted(glob.glob(os.path.join(DATA_DIR, "archive", "buildings_*.json"))):
        d = load(f)
        if not isinstance(d, dict):
            continue
        for mid in METERS:
            for p in ((d.get("meters") or {}).get(mid, {}) or {}).get("timeseries_kw") or []:
                t = parse_ts(p.get("t"))
                if t and not ambiguous(t) and isinstance(p.get("v"), (int, float)):
                    buckets[t.strftime("%Y-%m-%d %H:%M")][mid] = p["v"]
    peak = {}
    for minute, got in buckets.items():
        if len(got) == len(METERS):
            day = minute[:10]
            peak[day] = max(peak.get(day, 0), sum(got.values()))
    return {k: round(v, 1) for k, v in peak.items()}


def daily_temps():
    """Pacific date -> mean outdoor degC from the TOWT weather cache (>= 12 h of data)."""
    out = {}
    wc = load(os.path.join(DATA_DIR, "weather_cache.json")) or {}
    try:
        epoch = dt.datetime.strptime(str(wc.get("epoch", "2026-01-01"))[:10], "%Y-%m-%d")  # legacy: 2026
        byday = defaultdict(list)
        for k, v in (wc.get("hours") or {}).items():
            byday[(epoch + dt.timedelta(hours=int(k))).date()].append(v)
        for day, vals in byday.items():
            if len(vals) >= 12:
                out[day.isoformat()] = round(sum(vals) / len(vals), 1)
    except Exception:
        pass
    return out


def main():
    snaps = read_snapshots()
    peak, tmean = daily_peaks(), daily_temps()
    daily = daily_rows(snaps, pacific_now().date())
    for r in daily:
        if r["d"] in peak:
            r["pk"] = peak[r["d"]]
        if r["d"] in tmean:
            r["tc"] = tmean[r["d"]]

    monthly = defaultdict(lambda: [0.0, 0])
    for r in daily:
        monthly[r["d"][:7]][0] += r["t"]
        monthly[r["d"][:7]][1] += 1
    mrows = [{"m": k, "avg": round(v[0] / v[1])} for k, v in sorted(monthly.items()) if v[1]]

    # LEED design figures (static, on main)
    leed = None
    design_daily = baseline_daily = None
    area = eui_design = None
    try:
        leed = json.load(open(os.path.join(DATA_DIR, "bechtel_leed.json")))
        design_daily = round(leed["totals"]["proposed_annual_kwh"] / 365)
        baseline_daily = round(leed["totals"]["baseline_annual_kwh"] / 365)
        area = leed["building"]["conditioned_area_sqft"]
        eui_design = leed["totals"]["eui_proposed_kwh_per_sqft_yr"]
    except Exception:
        pass

    avg_daily = round(sum(r["t"] for r in daily) / len(daily)) if daily else 0
    wd = [r["t"] for r in daily if not r["we"]]
    we = [r["t"] for r in daily if r["we"]]
    peak_row = max((r for r in daily if "pk" in r), key=lambda r: r["pk"], default=None)
    # temperature sensitivity: OLS of kWh/day on mean outdoor temp
    xy = [(r["tc"], r["t"]) for r in daily if "tc" in r]
    fit = None
    if len(xy) >= 10:
        n = len(xy)
        mx = sum(x for x, _ in xy) / n
        my = sum(y for _, y in xy) / n
        sxx = sum((x - mx) ** 2 for x, _ in xy)
        sxy = sum((x - mx) * (y - my) for x, y in xy)
        syy = sum((y - my) ** 2 for _, y in xy)
        if sxx > 0 and syy > 0:
            slope = sxy / sxx
            fit = {"slope_kwh_per_degc": round(slope, 1), "intercept": round(my - slope * mx, 1),
                   "r2": round((sxy * sxy) / (sxx * syy), 3), "n": n}
    baseline_annual = (baseline_daily or 0) * 365
    actual_annual = avg_daily * 365
    avoided_kwh = max(0, baseline_annual - actual_annual)
    out = {
        "peak_measured_kw": peak_row["pk"] if peak_row else None,
        "peak_measured_date": peak_row["d"] if peak_row else None,
        "peak_design_kw": leed["totals"].get("proposed_peak_kw") if design_daily else None,
        "peak_baseline_kw": leed["totals"].get("baseline_peak_kw") if design_daily else None,
        "weekday_avg_kwh": round(sum(wd) / len(wd)) if wd else None,
        "weekend_avg_kwh": round(sum(we) / len(we)) if we else None,
        "temp_fit": fit,
        "avoided_vs_baseline": {
            "mwh_yr": round(avoided_kwh / 1000),
            "usd_yr": round(avoided_kwh * 0.15),          # PG&E commercial, as elsewhere in the pipeline
            "tco2_yr": round(avoided_kwh * 0.21 / 1000, 1)  # CARB CA grid factor kg/kWh
        } if baseline_daily and daily else None,
        "_schema": "mv-grimes/1",
        "_doc": "Counter-based M&V for Grimes: daily kWh from cumulative kwh_delivered deltas vs LEED design figures. Complete Pacific days only.",
        "method": METHOD,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "period": {"start": daily[0]["d"], "end": daily[-1]["d"], "days": len(daily)} if daily else None,
        "avg_daily_kwh": avg_daily,
        "annualized_mwh": round(avg_daily * 365 / 1000),
        "design_daily_kwh": design_daily,
        "baseline_daily_kwh": baseline_daily,
        "eui_actual": round(avg_daily * 365 / area, 1) if area else None,
        "eui_design": eui_design,
        "daily": daily,
        "monthly": mrows,
    }
    with open(os.path.join(DATA_DIR, "mv_grimes.json"), "w") as f:
        json.dump(out, f)
    print(f"mv_grimes.json: {len(daily)} daily pts, avg {avg_daily} kWh/day, "
          f"annualized {out['annualized_mwh']} MWh vs design "
          f"{round((design_daily or 0) * 365 / 1000)} MWh")


if __name__ == "__main__":
    main()
