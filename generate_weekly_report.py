"""
Weekly Energy Report Generator
================================
Reads daily JSON snapshots from data/daily/
Generates data/weekly_report.json with:
- Weekly totals, averages, peaks
- Per-building weekly stats
- Day-by-day breakdown
- Week-over-week comparison

Run: python generate_weekly_report.py
"""

import json, os
from datetime import datetime, timedelta
from pathlib import Path

DAILY_DIR = Path("./data/daily")
OUTPUT = Path("./data/weekly_report.json")
COST_PER_KWH = 0.15
CO2_PER_KWH = 0.21


def load_day(date_str):
    f = DAILY_DIR / f"{date_str}.json"
    if f.exists():
        with open(f) as fh:
            return json.load(fh)
    return None


def run():
    today = datetime.now().date()

    # Last 7 days
    days = []
    for i in range(7):
        d = today - timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        data = load_day(ds)
        if data:
            days.append((ds, data))

    days.reverse()  # oldest first

    if not days:
        print("No daily data found")
        return

    print(f"Weekly report: {len(days)} days of data")

    # ── Campus-wide stats ──
    all_readings = []
    daily_summaries = []

    for ds, data in days:
        readings = data.get("readings", [])
        if not readings:
            continue

        kws = [r["total_kw"] for r in readings if r.get("total_kw")]
        online_counts = [r["online"] for r in readings if r.get("online")]

        day_avg = round(sum(kws) / len(kws), 1) if kws else 0
        day_peak = round(max(kws), 1) if kws else 0
        day_min = round(min(kws), 1) if kws else 0
        peak_time = ""
        for r in readings:
            if r.get("total_kw") == max(kws):
                peak_time = r.get("time", "")
                break

        day_kwh = round(day_avg * 24, 0)
        day_cost = round(day_kwh * COST_PER_KWH, 2)
        day_co2 = round(day_kwh * CO2_PER_KWH, 1)

        daily_summaries.append({
            "date": ds,
            "day": datetime.strptime(ds, "%Y-%m-%d").strftime("%A"),
            "avg_kw": day_avg,
            "peak_kw": day_peak,
            "peak_time": peak_time,
            "min_kw": day_min,
            "readings_count": len(readings),
            "avg_online": round(sum(online_counts) / len(online_counts)) if online_counts else 0,
            "est_kwh": day_kwh,
            "est_cost": day_cost,
            "est_co2_kg": day_co2,
        })
        all_readings.extend(kws)

        print(f"  {ds} ({datetime.strptime(ds, '%Y-%m-%d').strftime('%a')}): avg={day_avg}kW peak={day_peak}kW ({peak_time}) readings={len(readings)}")

    # ── Per-building weekly stats ──
    building_stats = {}
    for ds, data in days:
        for r in data.get("readings", []):
            for bid, kw in r.get("buildings", {}).items():
                if bid not in building_stats:
                    building_stats[bid] = {"readings": [], "name": ""}
                building_stats[bid]["readings"].append(kw)

    # Get names from latest data
    latest_day = days[-1][1] if days else None
    if latest_day:
        for r in latest_day.get("readings", []):
            for bid in r.get("buildings", {}):
                if bid in building_stats and not building_stats[bid]["name"]:
                    # Try to get name from campus_energy.json
                    pass

    building_weekly = {}
    for bid, bs in building_stats.items():
        kws = [k for k in bs["readings"] if k is not None and k > 0]
        if not kws:
            continue
        building_weekly[bid] = {
            "avg_kw": round(sum(kws) / len(kws), 1),
            "peak_kw": round(max(kws), 1),
            "min_kw": round(min(kws), 1),
            "readings": len(kws),
            "est_weekly_kwh": round(sum(kws) / len(kws) * 24 * 7, 0),
            "est_weekly_cost": round(sum(kws) / len(kws) * 24 * 7 * COST_PER_KWH, 2),
            "est_weekly_co2_kg": round(sum(kws) / len(kws) * 24 * 7 * CO2_PER_KWH, 1),
        }

    # ── Week totals ──
    week_avg = round(sum(all_readings) / len(all_readings), 1) if all_readings else 0
    week_peak = round(max(all_readings), 1) if all_readings else 0
    week_min = round(min(all_readings), 1) if all_readings else 0
    week_kwh = round(week_avg * 24 * len(days), 0)

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "period": {
            "start": days[0][0] if days else "",
            "end": days[-1][0] if days else "",
            "days": len(days),
            "total_readings": len(all_readings),
        },
        "campus_summary": {
            "avg_kw": week_avg,
            "peak_kw": week_peak,
            "min_kw": week_min,
            "total_kwh": week_kwh,
            "total_cost": round(week_kwh * COST_PER_KWH, 2),
            "total_co2_kg": round(week_kwh * CO2_PER_KWH, 1),
            "total_co2_tons": round(week_kwh * CO2_PER_KWH / 1000, 2),
            "trees_equivalent": round(week_kwh * CO2_PER_KWH / 21.7),
        },
        "daily_breakdown": daily_summaries,
        "building_rankings": dict(sorted(building_weekly.items(), key=lambda x: -x[1]["avg_kw"])),
    }

    with open(OUTPUT, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n  ✓ Saved → {OUTPUT}")
    print(f"  ✓ Period: {report['period']['start']} to {report['period']['end']} ({len(days)} days)")
    print(f"  ✓ Avg: {week_avg} kW | Peak: {week_peak} kW")
    print(f"  ✓ Total: {week_kwh} kWh | ${report['campus_summary']['total_cost']} | {report['campus_summary']['total_co2_tons']} t CO₂")


if __name__ == "__main__":
    run()
