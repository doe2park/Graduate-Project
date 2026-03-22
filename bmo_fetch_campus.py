"""
BMO Campus-Wide Energy Fetcher
================================
Fetches latest kW reading from ALL metered campus buildings.
Outputs campus_energy.json for the campus map to consume.

Usage:
    python bmo_fetch_campus.py

Output: data/campus_energy.json (committed by GitHub Actions)
"""

import os, csv, io, json, requests
from datetime import datetime, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BMO_BASE = "https://www.buildingmanageronline.com"
BMO_USER = os.environ.get("BMO_USERNAME", "")
BMO_PASS = os.environ.get("BMO_PASSWORD", "")
TIMEZONE = "US/Pacific"

# ── All campus buildings with their BMO device info ──
# mac, db, preferred electric meter, campus_map_id
BUILDINGS = [
    # Engineering
    {"id":"grimes","name":"Grimes Engineering Center","mac":"001EC6000C5A","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"cory","name":"Cory Hall","mac":"001EC6001885","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"soda","name":"Soda Hall","mac":"001EC600187F","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"davis","name":"Davis Hall","mac":"001EC6000C58","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"etch","name":"Etcheverry Hall","mac":"001EC600077E","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"hmm","name":"Hearst Memorial Mining","mac":"001EC6000450","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"hesse","name":"Hesse & O'Brien Hall","mac":"001EC600077D","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"sutardja","name":"Sutardja Dai Hall","mac":"444D50E019ED","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"mclaughlin","name":"McLaughlin Hall","mac":"001EC6000495","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"jacobs","name":"Jacobs Hall","mac":"001EC6000495","db":"dbU216ucberkelF682","meters":["3"]},
    # Science
    {"id":"stanley","name":"Stanley Hall","mac":"001EC6000C5A","db":"dbU216ucberkelF682","meters":["3"]},
    {"id":"tan","name":"Tan Hall","mac":"001EC6001473","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"latimer","name":"Latimer & Pimentel Hall","mac":"0050C230ECE6","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"evans","name":"Evans Hall","mac":"001EC6000C58","db":"dbU216ucberkelF682","meters":["3"]},
    {"id":"birge","name":"Birge Hall","mac":"001EC6001C55","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"hilde","name":"Hildebrand Hall","mac":"001EC6000764","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"lksc","name":"Li Ka Shing","mac":"001EC6000C83","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"koshland","name":"Koshland Hall","mac":"444D50E01A41","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    # Humanities
    {"id":"wheeler","name":"Wheeler Hall","mac":"001EC6000C8C","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"dwinelle","name":"Dwinelle Hall","mac":"001EC600045C","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"barrows","name":"Barrows Hall","mac":"001EC600063F","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"moses","name":"Moses Hall","mac":"001EC6001C7A","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"stephens","name":"Stephens Hall","mac":"001EC6000CB6","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    # Professional
    {"id":"wurster","name":"Wurster Hall","mac":"001EC6000B5F","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"giannini","name":"Giannini Hall","mac":"001EC6000CCA","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"tolman","name":"Tolman Hall","mac":"001EC6000CA3","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"morgan","name":"Morgan Hall","mac":"001EC6001BC1","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"california","name":"California Hall","mac":"001EC6000C58","db":"dbU216ucberkelF682","meters":["3"]},
    {"id":"boalt","name":"Boalt Hall","mac":"001EC6000793","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    # Student Life
    {"id":"mlk","name":"MLK Student Union","mac":"001EC6000481","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"rsf","name":"Rec Sports Facility","mac":"001EC6000CA0","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"chavez","name":"Chavez Center","mac":"001EC6000BB9","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"anthony","name":"Anthony Hall","mac":"001EC6000C9A","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"sproul","name":"Sproul Hall","mac":"001EC6000CAE","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    # Libraries
    {"id":"doe","name":"Doe Library","mac":"001EC6000C54","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"moffitt","name":"Moffitt Library","mac":"001EC6000C90","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    # Other
    {"id":"uhall","name":"University Hall","mac":"001EC6002D3C","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"northgate","name":"North Gate Hall","mac":"001EC6070132","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"donner","name":"Donner Laboratory","mac":"001EC6000C24","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"bww","name":"Berkeley Way West","mac":"001EC6000777","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"mulford","name":"Mulford Hall","mac":"001EC6000CB2","db":"dbU216ucberkelF682","meters":["3","76","77"]},
]

# kW column names to search for (different meter models use different names)
KW_COLUMNS = [
    "kW total (kW)",
    "Active Power Total (kW)",
    "kW total",
    "kW",
    "kW del-rec (kW)",
    "Power Total (kW)",
]

OUTPUT_DIR = Path("./data")
OUTPUT_FILE = OUTPUT_DIR / "campus_energy.json"


def create_session():
    s = requests.Session()
    s.auth = (BMO_USER, BMO_PASS)
    s.headers["User-Agent"] = "Mozilla/5.0 (Campus Energy Fetcher)"
    r = s.get(f"{BMO_BASE}/members/", timeout=30)
    if r.status_code == 401:
        raise Exception("BMO login failed (401)")
    return s


def fetch_latest_kw(session, mac, db, meter_id):
    """Fetch last 1 hour of data and return latest kW reading."""
    now = datetime.now()
    start = now - timedelta(hours=2)

    url = f"{BMO_BASE}/members/mbdev_export.php/{mac}_{meter_id}.csv"
    params = {
        "DB": db, "AS": mac, "MB": meter_id, "DOWNLOAD": "YES",
        "DATE_RANGE_STARTTIME": start.strftime("%Y-%m-%d+%H:%M:%S"),
        "DATE_RANGE_ENDTIME": now.strftime("%Y-%m-%d+%H:%M:%S"),
        "DELIMITER": "TAB", "COLNAMES": "ON", "EXPORTTIMEZONE": TIMEZONE,
    }

    try:
        r = session.get(url, params=params, timeout=20)
        if r.status_code != 200 or "<html" in r.text[:200].lower():
            return None, None

        reader = csv.DictReader(io.StringIO(r.text), delimiter="\t")
        rows = list(reader)
        if not rows:
            return None, None

        last_row = rows[-1]
        timestamp = last_row.get("time (US/Pacific)", "")

        # Try each known kW column name
        for col in KW_COLUMNS:
            val = last_row.get(col)
            if val is not None:
                try:
                    kw = float(val)
                    if 0 < kw < 50000:  # reasonable range for a building
                        return round(kw, 1), timestamp
                except (ValueError, TypeError):
                    pass

        # Fallback: search any column with "kW" in the name
        for col_name, val in last_row.items():
            if "kW" in col_name and "kWh" not in col_name:
                try:
                    kw = float(val)
                    if 0 < kw < 50000:
                        return round(kw, 1), timestamp
                except (ValueError, TypeError):
                    pass

        return None, timestamp
    except Exception:
        return None, None


def run():
    print(f"BMO Campus Energy Fetch — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  Buildings: {len(BUILDINGS)}")

    session = create_session()
    print(f"  ✓ Logged in\n")

    results = {}
    online = 0

    for b in BUILDINGS:
        kw = None
        ts = None

        # Try each meter until we get a kW reading
        for meter_id in b["meters"]:
            kw, ts = fetch_latest_kw(session, b["mac"], b["db"], meter_id)
            if kw is not None:
                break

        status = "online" if kw is not None else "offline"
        if kw is not None:
            online += 1

        results[b["id"]] = {
            "name": b["name"],
            "kw": kw,
            "status": status,
            "timestamp": ts,
            "mac": b["mac"],
        }

        icon = "✅" if kw else "·"
        kw_str = f"{kw} kW" if kw else "no data"
        print(f"  {icon} {b['name']:30s} {kw_str}")

    # Build output
    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "update_interval_min": 15,
        "buildings_total": len(BUILDINGS),
        "buildings_online": online,
        "total_kw": round(sum(r["kw"] for r in results.values() if r["kw"]), 1),
        "buildings": results,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n  ✓ Saved → {OUTPUT_FILE}")
    print(f"  ✓ {online}/{len(BUILDINGS)} buildings online")
    print(f"  ✓ Total campus load: {output['total_kw']} kW")


if __name__ == "__main__":
    run()
