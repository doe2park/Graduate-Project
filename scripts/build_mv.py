#!/usr/bin/env python3
"""
build_mv.py — measurement & verification series for Grimes.

Reads the daily `buildings_YYYY-MM-DD.json` archives (cumulative
kwh_delivered counters on meters 3/76/77) plus the LEED design figures,
and writes data/mv_grimes.json for the live Design-vs-Actual page.

Counter deltas between consecutive snapshots are the measured energy —
revenue-grade, immune to sampling gaps. Runs inside the 15-min campus
workflow (cheap: one pass over the archive files). Never raises on bad
files; a partial archive just yields a shorter series.
"""
import json
import glob
import datetime as dt
from collections import defaultdict

METERS = ("3", "76", "77")


def main():
    pts = {}
    for f in sorted(glob.glob("data/archive/buildings_*.json")):
        date = f.split("buildings_")[1][:10]
        try:
            d = json.load(open(f))
        except Exception:
            continue
        row = {}
        for mid, m in (d.get("meters") or {}).items():
            k = (m.get("latest") or {}).get("kwh_delivered")
            if k:
                row[mid] = k
        if all(m in row for m in METERS):
            pts[date] = row

    daily = []
    prev = None
    for date in sorted(pts):
        if prev:
            dd = (dt.date.fromisoformat(date) - dt.date.fromisoformat(prev)).days
            if 0 < dd <= 3:
                e = {m: (pts[date][m] - pts[prev][m]) / dd for m in METERS}
                if all(v >= -5 for v in e.values()):  # tolerate tiny counter jitter
                    daily.append({
                        "d": date,
                        "t": round(sum(e.values()), 1),
                        "m3": round(e["3"], 1),
                        "m76": round(e["76"], 1),
                        "m77": round(e["77"], 1),
                    })
        prev = date

    monthly = defaultdict(lambda: [0.0, 0])
    for r in daily:
        monthly[r["d"][:7]][0] += r["t"]
        monthly[r["d"][:7]][1] += 1
    mrows = [{"m": k, "avg": round(v[0] / v[1])} for k, v in sorted(monthly.items()) if v[1]]

    # LEED design figures (static, on main)
    design_daily = baseline_daily = None
    area = eui_design = None
    try:
        leed = json.load(open("data/bechtel_leed.json"))
        design_daily = round(leed["totals"]["proposed_annual_kwh"] / 365)
        baseline_daily = round(leed["totals"]["baseline_annual_kwh"] / 365)
        area = leed["building"]["conditioned_area_sqft"]
        eui_design = leed["totals"]["eui_proposed_kwh_per_sqft_yr"]
    except Exception:
        pass

    avg_daily = round(sum(r["t"] for r in daily) / len(daily)) if daily else 0
    out = {
        "_schema": "mv-grimes/1",
        "_doc": "Counter-based M&V for Grimes: daily kWh from cumulative kwh_delivered deltas vs LEED design figures.",
        "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
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
    with open("data/mv_grimes.json", "w") as f:
        json.dump(out, f)
    print(f"mv_grimes.json: {len(daily)} daily pts, avg {avg_daily} kWh/day, "
          f"annualized {out['annualized_mwh']} MWh vs design "
          f"{round((design_daily or 0) * 365 / 1000)} MWh")


if __name__ == "__main__":
    main()
