"""
BMO Auto-Fetcher — Grimes Engineering Center
Logs into BMO, downloads latest CSV for all meters, processes to JSON.

Usage:
    python bmo_fetch.py                  # Fetch last 24h
    python bmo_fetch.py --hours 48       # Fetch last 48h
    python bmo_fetch.py --days 7         # Fetch last 7 days

Setup:
    1. pip install requests python-dotenv
    2. Create .env file:
       BMO_USERNAME=your_username
       BMO_PASSWORD=your_password
    3. Run: python bmo_fetch.py

Automate (cron every 15 min):
    */15 * * * * cd /path/to/project && python bmo_fetch.py >> logs/fetch.log 2>&1
"""

import os
import csv
import json
import io
import requests
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ────────────────────────────────────────────
BMO_BASE = "https://www.buildingmanageronline.com"
BMO_EXPORT_URL = f"{BMO_BASE}/members/mbdev_export.php"

BMO_USERNAME = os.environ.get("BMO_USERNAME", "")
BMO_PASSWORD = os.environ.get("BMO_PASSWORD", "")

DEVICE = "001EC6000C5A"
DB = "dbU216ucberkelF682"
TIMEZONE = "US/Pacific"

METERS = {
    "3":   {"name": "Roof Electric",       "voltage": "480V 3-phase"},
    "76":  {"name": "480/277V Electric",    "voltage": "480V"},
    "77":  {"name": "208/120V Electric",    "voltage": "208V"},
    "250": {"name": "Condensate & Water",   "voltage": "—"},
}

# ── Column mappings — comprehensive ───────────────────
# Meter 3 (Schneider ION6200) has different column names than 76/77
METER3_COLS = {
    "kw":           "Active Power Total (kW)",
    "kw_a":         "Active Power A (kW)",
    "kw_b":         "Active Power B (kW)",
    "kw_c":         "Active Power C (kW)",
    "kva":          "Apparent Power Total (kVA)",
    "kvar":         "Reactive Power Total (kVAR)",
    "power_factor": "Power Factor Total (PF)",
    "pf_a":         "Power Factor A (PF)",
    "pf_b":         "Power Factor B (PF)",
    "pf_c":         "Power Factor C (PF)",
    "current_a":    "Current A (Amps)",
    "current_b":    "Current B (Amps)",
    "current_c":    "Current C (Amps)",
    "current_avg":  "Current Avg (Amps)",
    "voltage_ll":   "Voltage L-L Avg (Volts)",
    "voltage_ln":   "Voltage L-N Avg (Volts)",
    "frequency":    "Frequency (Hz)",
    "kwh_delivered": "Active Energy Delivered (Into Load) (kWh)",
    "demand_kw":    "Active Power Present Demand (kW)",
    "peak_demand_kw": "Active Power Peak Demand (kW)",
}

SUBPANEL_COLS = {
    "kw":           "kW total (kW)",
    "kw_a":         "kW a (kW)",
    "kw_b":         "kW b (kW)",
    "kw_c":         "kW c (kW)",
    "kva":          "kVA total (kVA)",
    "kvar":         "kVAR total (kVAR)",
    "power_factor": "PF sign total",
    "current_a":    "I a (Amps)",
    "current_b":    "I b (Amps)",
    "current_c":    "I c (Amps)",
    "current_avg":  "I ave (Amps)",
    "voltage_ll":   "Vll ave (Volts)",
    "voltage_ln":   "Vln ave (Volts)",
    "frequency":    "Frequency (Hz)",
    "kwh_delivered": "kWh del (kWh)",
    "demand_kw":    "kW demand (kW)",
    "peak_demand_kw": "kW peak demand (kW)",
    "thd_v1":       "V1 THD (%)",
    "thd_v2":       "V2 THD (%)",
    "thd_v3":       "V3 THD (%)",
    "thd_i1":       "I1 THD (%)",
    "thd_i2":       "I2 THD (%)",
    "thd_i3":       "I3 THD (%)",
}

COL_MAP = {
    "3": METER3_COLS,
    "76": SUBPANEL_COLS,
    "77": SUBPANEL_COLS,
}

WATER_COLS = {
    "steam_total_gal":     "Steam Condensate Meter (Gal)",
    "steam_rate_gpm":      "Steam Condensate Meter Ave Rate (Gpm)",
    "steam_instant_gpm":   "Steam Condensate Meter Instantaneous (Gpm)",
    "irrigation_total_gal":"Irrigation Water ABADBECH (Gallons)",
    "irrigation_rate_gpm": "Irrigation Water ABADBECH Ave Rate (Gpm)",
    "water1_total_cf":     "Water 70313687 (Cubic Feet)",
    "water1_rate_cfm":     "Water 70313687 Ave Rate (CFm)",
    "water1_instant_cfm":  "Water 70313687 Instantaneous (CFm)",
    "water2_total_cf":     "Water 70313686 (Cubic Feet)",
    "water2_rate_cfm":     "Water 70313686 Ave Rate (CFm)",
}

OUTPUT_DIR = Path("./data")
OUTPUT_FILE = OUTPUT_DIR / "building_data.json"


# ── BMO Session ───────────────────────────────────────
def create_session():
    """Login to BMO using HTTP Basic Auth."""
    session = requests.Session()
    session.auth = (BMO_USERNAME, BMO_PASSWORD)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Grimes Energy Dashboard)"
    })

    print("  Logging into BMO...")
    resp = session.get(BMO_BASE + "/members/", timeout=30)

    if resp.status_code == 401:
        raise Exception(f"Login failed (status 401). Check credentials in .env")

    print(f"  ✓ Login successful (status {resp.status_code})")
    return session


def fetch_meter_csv(session, meter_id, start_time, end_time):
    """Download CSV for a single meter."""
    filename = f"{DEVICE}_{meter_id}.csv"
    url = f"{BMO_EXPORT_URL}/{filename}"

    params = {
        "DB": DB,
        "AS": DEVICE,
        "MB": meter_id,
        "DOWNLOAD": "YES",
        "DATE_RANGE_STARTTIME": start_time.strftime("%Y-%m-%d+%H:%M:%S"),
        "DATE_RANGE_ENDTIME": end_time.strftime("%Y-%m-%d+%H:%M:%S"),
        "DELIMITER": "TAB",
        "COLNAMES": "ON",
        "EXPORTTIMEZONE": TIMEZONE,
    }

    resp = session.get(url, params=params)

    if resp.status_code != 200:
        print(f"  ✗ Meter #{meter_id}: HTTP {resp.status_code}")
        return None

    content = resp.text
    if "<html" in content.lower()[:200]:
        print(f"  ✗ Meter #{meter_id}: Got HTML instead of CSV (session expired?)")
        return None

    return content


# ── Data Processing ───────────────────────────────────
def safe_float(val, default=None):
    try:
        v = float(val)
        # Filter out obviously bad values (e.g. THD of 3276.8 = sensor error)
        if abs(v) > 1e8:
            return default
        return round(v, 3)
    except (ValueError, TypeError):
        return default


def parse_power_csv(csv_text, meter_id):
    """Parse power meter CSV into full readings."""
    cols = COL_MAP.get(meter_id, SUBPANEL_COLS)
    readings = []

    reader = csv.DictReader(io.StringIO(csv_text), delimiter="\t")
    for row in reader:
        try:
            if int(row.get("error", "0")) != 0:
                continue
        except ValueError:
            continue

        kw = safe_float(row.get(cols["kw"]))
        if kw is None:
            continue

        entry = {"timestamp": row.get("time (US/Pacific)", "")}
        for key, col_name in cols.items():
            entry[key] = safe_float(row.get(col_name))

        readings.append(entry)

    return readings


def parse_water_csv(csv_text):
    """Parse water/steam meter CSV."""
    readings = []
    reader = csv.DictReader(io.StringIO(csv_text), delimiter="\t")
    for row in reader:
        try:
            if int(row.get("error", "0")) != 0:
                continue
        except ValueError:
            continue

        entry = {"timestamp": row.get("time (US/Pacific)", "")}
        for key, col in WATER_COLS.items():
            entry[key] = safe_float(row.get(col))
        if any(v is not None for k, v in entry.items() if k != "timestamp"):
            readings.append(entry)

    return readings


def compute_stats(readings, key="kw"):
    values = [r[key] for r in readings if r.get(key) is not None]
    if not values:
        return {}
    peak_val = max(values)
    peak_idx = values.index(peak_val)
    return {
        "current": values[-1],
        "min": round(min(values), 2),
        "max": round(peak_val, 2),
        "avg": round(sum(values) / len(values), 2),
        "count": len(values),
        "peak_time": readings[peak_idx]["timestamp"],
    }


def get_today_readings(readings):
    today = datetime.now().strftime("%Y-%m-%d")
    return [r for r in readings if r["timestamp"].startswith(today)]


def get_timeseries(readings, key="kw", limit=96):
    """Extract last N (timestamp, value) pairs for charting."""
    pairs = []
    for r in readings[-limit:]:
        val = r.get(key)
        if val is not None:
            pairs.append({"t": r["timestamp"], "v": val})
    return pairs


# ── Main Pipeline ─────────────────────────────────────
def run(hours=24):
    now = datetime.now()
    start = now - timedelta(hours=hours)

    print(f"BMO Auto-Fetch — Grimes Engineering Center")
    print(f"  Range: {start.strftime('%Y-%m-%d %H:%M')} → {now.strftime('%Y-%m-%d %H:%M')}")
    print()

    session = create_session()

    output = {
        "building": {
            "name": "Grimes Engineering Center",
            "bmo_alias": "Bechtel Center",
            "campus": "UC Berkeley",
            "device_mac": DEVICE,
        },
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "update_interval_min": 15,
        "meters": {},
        "water": None,
        "summary": {},
    }

    total_kw = 0
    meter_count = 0

    # ── Fetch power meters ──
    for meter_id in ["3", "76", "77"]:
        name = METERS[meter_id]["name"]
        print(f"  Fetching meter #{meter_id} ({name})...")

        csv_text = fetch_meter_csv(session, meter_id, start, now)
        if not csv_text:
            output["meters"][meter_id] = {
                "name": name,
                "voltage": METERS[meter_id]["voltage"],
                "status": "offline",
            }
            continue

        readings = parse_power_csv(csv_text, meter_id)
        if not readings:
            output["meters"][meter_id] = {
                "name": name,
                "voltage": METERS[meter_id]["voltage"],
                "status": "offline",
            }
            continue

        today = get_today_readings(readings)

        output["meters"][meter_id] = {
            "name": name,
            "voltage": METERS[meter_id]["voltage"],
            "status": "online",
            "latest": readings[-1],
            "stats_today": {
                "kw": compute_stats(today, "kw"),
                "power_factor": compute_stats(today, "power_factor"),
                "current": compute_stats(today, "current_avg"),
            },
            "timeseries_kw": get_timeseries(readings, "kw"),
        }

        latest_kw = readings[-1].get("kw", 0) or 0
        print(f"    ✓ {len(readings)} readings, latest: {latest_kw} kW")

        if latest_kw:
            total_kw += latest_kw
            meter_count += 1

    # ── Fetch water meter ──
    print(f"  Fetching meter #250 (Water/Steam)...")
    csv_text = fetch_meter_csv(session, "250", start, now)
    if csv_text:
        water_readings = parse_water_csv(csv_text)
        today_water = get_today_readings(water_readings)
        output["water"] = {
            "status": "online",
            "latest": water_readings[-1] if water_readings else None,
            "stats_today": {
                "water_rate": compute_stats(today_water, "water1_rate_cfm") if today_water else {},
                "steam_rate": compute_stats(today_water, "steam_rate_gpm") if today_water else {},
            },
            "timeseries_water": get_timeseries(water_readings, "water1_rate_cfm"),
        }
        print(f"    ✓ {len(water_readings)} readings")
    else:
        output["water"] = {"status": "offline"}

    # ── Summary ──
    output["summary"] = {
        "total_kw_now": round(total_kw, 2),
        "meters_online": meter_count,
        "kw_main": output["meters"].get("3", {}).get("latest", {}).get("kw"),
        "kw_sub_a": output["meters"].get("76", {}).get("latest", {}).get("kw"),
        "kw_sub_b": output["meters"].get("77", {}).get("latest", {}).get("kw"),
    }

    # ── Save ──
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n  ✓ Saved → {OUTPUT_FILE}")
    print(f"  ✓ Total: {total_kw:.1f} kW ({meter_count} meters online)")
    print(f"  ✓ Next auto-fetch in 15 min\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--days", type=int, default=None)
    args = parser.parse_args()

    hrs = args.days * 24 if args.days else args.hours
    run(hours=hrs)
