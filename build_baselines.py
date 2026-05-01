#!/usr/bin/env python3
"""
Build per-building energy baselines for the campus map's forecast layer.

Walks `data/archive/2026-*.json` snapshots, expands each building's sparkline
(last 16 × 15min ≈ 4hr) into discrete (timestamp, kw) samples, then aggregates
into a 4-tier baseline lookup that the front-end can consult to forecast
"what's typical for this building at this future moment":

    Tier 1: (weekday, hour)        — most specific
    Tier 2: (weekday_class, hour)  — weekday vs weekend
    Tier 3: hour                   — pooled across all days
    Tier 4: building mean          — last resort

Output: data/baselines.json (loaded once by grimes-campus-map-arcgis.html).

Re-run after new archive snapshots arrive (or wire into bmo_fetch_campus.py).
"""

import json
import glob
import os
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, pstdev

ARCHIVE_GLOB = "data/archive/2026-*.json"
OUT_PATH     = "data/baselines.json"
SPARK_STEP_MIN = 15
MIN_SAMPLES_TIER1 = 3   # (weekday, hour) needs ≥3 samples to be trusted
MIN_SAMPLES_TIER2 = 3
MIN_SAMPLES_TIER3 = 3


def collect_samples():
    """Returns {building: [(ts, kw), ...]} from all archive sparklines."""
    samples = defaultdict(list)
    for fp in sorted(glob.glob(ARCHIVE_GLOB)):
        # Skip the 'buildings_*.json' variants — different schema
        if os.path.basename(fp).startswith("buildings_"):
            continue
        try:
            with open(fp) as f:
                d = json.load(f)
        except Exception as e:
            print(f"  skip {fp}: {e}")
            continue
        if "buildings" not in d:
            continue
        snap_ts_str = d.get("generated_at") or d.get("timestamp")
        if not snap_ts_str:
            continue
        try:
            snap_ts = datetime.fromisoformat(snap_ts_str.replace("Z", ""))
        except Exception:
            continue
        for bname, bdata in d["buildings"].items():
            spark = bdata.get("sparkline")
            if not spark:
                continue
            n = len(spark)
            for i, kw in enumerate(spark):
                if kw is None:
                    continue
                offset_min = (n - 1 - i) * SPARK_STEP_MIN
                ts = snap_ts - timedelta(minutes=offset_min)
                samples[bname].append((ts, float(kw)))
    return samples


def aggregate(samples):
    """Build the 4-tier baseline structure for a single building."""
    by_wday_hr   = defaultdict(list)  # (wday, hr) -> [kw]
    by_class_hr  = defaultdict(list)  # ('weekday'|'weekend', hr) -> [kw]
    by_hr        = defaultdict(list)  # hr -> [kw]
    overall      = []

    for ts, kw in samples:
        wday = ts.weekday()                  # 0=Mon ... 6=Sun
        wclass = "weekend" if wday >= 5 else "weekday"
        hr = ts.hour
        by_wday_hr[(wday, hr)].append(kw)
        by_class_hr[(wclass, hr)].append(kw)
        by_hr[hr].append(kw)
        overall.append(kw)

    def stat(vs):
        if not vs:
            return None
        return {
            "mean": round(mean(vs), 2),
            "std":  round(pstdev(vs), 2) if len(vs) > 1 else 0.0,
            "n":    len(vs),
        }

    return {
        "tier1": {f"{w},{h}": stat(v) for (w, h), v in by_wday_hr.items() if len(v) >= MIN_SAMPLES_TIER1},
        "tier2": {f"{c},{h}": stat(v) for (c, h), v in by_class_hr.items() if len(v) >= MIN_SAMPLES_TIER2},
        "tier3": {str(h): stat(v) for h, v in by_hr.items() if len(v) >= MIN_SAMPLES_TIER3},
        "tier4": stat(overall),
    }


def main():
    samples = collect_samples()
    print(f"buildings collected: {len(samples)}")

    out = {
        "_doc": "Forecast baselines per building. Lookup order: tier1 ('wday,hr') → tier2 ('weekday|weekend,hr') → tier3 ('hr') → tier4 (overall mean). 'wday' is 0=Mon..6=Sun.",
        "_generated_at": datetime.utcnow().isoformat() + "Z",
        "_source_files": sorted([os.path.basename(p) for p in glob.glob(ARCHIVE_GLOB)
                                 if not os.path.basename(p).startswith("buildings_")]),
        "_min_samples": {"tier1": MIN_SAMPLES_TIER1, "tier2": MIN_SAMPLES_TIER2, "tier3": MIN_SAMPLES_TIER3},
        "buildings": {},
    }

    for bname, ss in samples.items():
        agg = aggregate(ss)
        out["buildings"][bname] = agg

    # Coverage report
    print("\nCoverage (top 5 by sample count):")
    for bname in sorted(samples.keys(), key=lambda b: -len(samples[b]))[:5]:
        agg = out["buildings"][bname]
        print(f"  {bname:14s} samples={len(samples[bname]):4d}  "
              f"tier1={len(agg['tier1']):3d}/168  "
              f"tier2={len(agg['tier2']):3d}/48  "
              f"tier3={len(agg['tier3']):2d}/24")

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    sz = os.path.getsize(OUT_PATH) / 1024
    print(f"\nwrote {OUT_PATH} ({sz:.1f} KB)")


if __name__ == "__main__":
    main()
