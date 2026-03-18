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
    pass  # .env optional if vars are set in environment

# ── Config ────────────────────────────────────────────
BMO_BASE = "https://www.buildingmanageronline.com"
BMO_LOGIN_URL = f"{BMO_BASE}/members/index.php"
BMO_EXPORT_URL = f"{BMO_BASE}/members/mbdev_export.php"

BMO_USERNAME = os.environ.get("BMO_USERNAME", "")
BMO_PASSWORD = os.environ.get("BMO_PASSWORD", "")

DEVICE = "001EC6000C5A"
DB = "dbU216ucberkelF682"
TIMEZONE = "US/Pacific"

METERS = {
    "3":   {"name": "Main Panel",  "voltage": "480V 3-phase"},
    "76":  {"name": "Sub-Panel A", "voltage": "480V"},
    "77":  {"name": "Sub-Panel B", "voltage": "208V"},
    "250": {"name": "Water/Steam", "voltage": "—"},
}

# Column mappings per meter type
POWER_COLS = {
    "3": {
        "kw": "Active Power Total (kW)",
        "kwh": "Active Energy Delivered (Into Load) (kWh)",
        "pf": "Power Factor Total (PF)",
        "amps": "Current Avg (Amps)",
        "volts": "Voltage L-L Avg (Volts)",
    },
    "76": {
        "kw": "kW total (kW)",
        "kwh": "kWh del (kWh)",
        "pf": "PF sign total",
        "amps": "I ave (Amps)",
        "volts": "Vll ave (Volts)",
    },
    "77": {
        "kw": "kW total (kW)",
        "kwh": "kWh del (kWh)",
        "pf": "PF sign total",
        "amps": "I ave (Amps)",
        "volts": "Vll ave (Volts)",
    },
}

WATER_COLS = {
    "steam_gal": "Steam Condensate Meter (Gal)",
    "steam_rate": "Steam Condensate Meter Instantaneous (Gpm)",
    "water_cf": "Water 70313687 (Cubic Feet)",
    "water_rate": "Water 70313687 Instantaneous (CFm)",
    "irrigation_gal": "Irrigation Water ABADBECH (Gallons)",
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

    # Check if we got actual CSV (not a login page)
    content = resp.text
    if "<html" in content.lower()[:200]:
        print(f"  ✗ Meter #{meter_id}: Got HTML instead of CSV (session expired?)")
        return None

    return content


# ── Data Processing ───────────────────────────────────
def safe_float(val, default=None):
    try:
        return round(float(val), 2)
    except (ValueError, TypeError):
        return default


def parse_power_csv(csv_text, meter_id):
    """Parse power meter CSV text into readings."""
    cols = POWER_COLS.get(meter_id, POWER_COLS["76"])
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

        readings.append({
            "timestamp": row.get("time (US/Pacific)", ""),
            "kw": kw,
            "kwh": safe_float(row.get(cols["kwh"])),
            "power_factor": safe_float(row.get(cols["pf"])),
            "current_amps": safe_float(row.get(cols["amps"])),
            "voltage": safe_float(row.get(cols["volts"])),
        })

    return readings


def parse_water_csv(csv_text):
    """Parse water/steam meter CSV text."""
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
        "min": round(min(values), 1),
        "max": round(peak_val, 1),
        "avg": round(sum(values) / len(values), 1),
        "peak_time": readings[peak_idx]["timestamp"],
    }


def get_today_readings(readings):
    today = datetime.now().strftime("%Y-%m-%d")
    return [r for r in readings if r["timestamp"].startswith(today)]


# ── Main Pipeline ─────────────────────────────────────
def run(hours=24):
    now = datetime.now()
    start = now - timedelta(hours=hours)

    print(f"BMO Auto-Fetch — Grimes Engineering Center")
    print(f"  Range: {start.strftime('%Y-%m-%d %H:%M')} → {now.strftime('%Y-%m-%d %H:%M')}")
    print()

    # Login
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

    # Fetch power meters
    for meter_id in ["3", "76", "77"]:
        name = METERS[meter_id]["name"]
        print(f"  Fetching meter #{meter_id} ({name})...")

        csv_text = fetch_meter_csv(session, meter_id, start, now)
        if not csv_text:
            continue

        readings = parse_power_csv(csv_text, meter_id)
        today = get_today_readings(readings)
        stats = compute_stats(today)

        output["meters"][meter_id] = {
            "name": name,
            "voltage": METERS[meter_id]["voltage"],
            "stats_today": stats,
            "readings_today": today,
            "latest": readings[-1] if readings else None,
        }

        print(f"    ✓ {len(readings)} readings, latest: {stats.get('current', '—')} kW")

        if stats.get("current"):
            total_kw += stats["current"]
            meter_count += 1

    # Fetch water meter
    print(f"  Fetching meter #250 (Water/Steam)...")
    csv_text = fetch_meter_csv(session, "250", start, now)
    if csv_text:
        water_readings = parse_water_csv(csv_text)
        today_water = get_today_readings(water_readings)
        output["water"] = {
            "readings_today": today_water,
            "latest": water_readings[-1] if water_readings else None,
        }
        print(f"    ✓ {len(water_readings)} readings")

    # Summary
    output["summary"] = {
        "total_kw_now": round(total_kw, 1),
        "meters_online": meter_count,
    }

    # Save
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
