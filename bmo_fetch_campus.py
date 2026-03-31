"""
BMO Campus-Wide Energy Fetcher v2
===================================
- Correct meter/MAC per building (fixes offline buildings)
- Stores 24hr history for trend analysis
- Anomaly detection (flags >150% of rolling average)
- CO2 + cost estimation
- Prediction (weighted rolling average)

Output: data/campus_energy.json + data/campus_energy_history.json
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
CO2_PER_KWH = 0.21
COST_PER_KWH = 0.15

BUILDINGS = [
    {"id":"grimes","name":"Grimes Engineering Center","mac":"001EC6000C5A","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"cory","name":"Cory Hall","mac":"001EC6001885","db":"dbU216ucberkelF682","meters":["1","2","3","4","5","6","48","53","58"]},
    {"id":"cory","name":"Cory Hall (Legacy)","mac":"444D50E07076","db":"dbU216ucberkelF682","meters":["48","53","58","63"]},
    {"id":"soda","name":"Soda Hall","mac":"001EC600187F","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"davis","name":"Davis Hall","mac":"001EC6000C58","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"etch","name":"Etcheverry Hall","mac":"001EC600077E","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"hmm","name":"Hearst Memorial Mining","mac":"001EC6000450","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"hesse","name":"Hesse & O'Brien Hall","mac":"001EC600077D","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"sutardja","name":"Sutardja Dai Hall","mac":"444D50E019ED","db":"dbU216ucberkelF682","meters":["76","29","30","97"]},
    {"id":"mclaughlin","name":"McLaughlin Hall","mac":"001EC6000495","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"stanley","name":"Stanley Hall","mac":"001EC6000C5A","db":"dbU216ucberkelF682","meters":["3"]},
    {"id":"tan","name":"Tan Hall","mac":"0050C230ED00","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"latimer","name":"Latimer & Pimentel Hall","mac":"0050C230ECE6","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"birge","name":"Birge Hall","mac":"001EC6001C55","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"hilde","name":"Hildebrand Hall","mac":"001EC6000764","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"lksc","name":"Li Ka Shing","mac":"001EC6000C83","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"koshland","name":"Koshland Hall","mac":"001EC6000C2F","db":"dbU216ucberkelF682","meters":["1","2","3","91","92","93","94"]},
    {"id":"wheeler","name":"Wheeler Hall","mac":"001EC6000C8C","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"dwinelle","name":"Dwinelle Hall","mac":"001EC600045C","db":"dbU216ucberkelF682","meters":["1","2","3","76","77","53","59"]},
    {"id":"barrows","name":"Barrows Hall","mac":"001EC600063F","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"moses","name":"Moses Hall","mac":"001EC6001C7A","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"stephens","name":"Stephens Hall","mac":"001EC6000CB6","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"wurster","name":"Wurster Hall","mac":"001EC6000B5F","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"giannini","name":"Giannini Hall","mac":"001EC6000CCA","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"tolman","name":"Tolman Hall","mac":"001EC6000CA3","db":"dbU216ucberkelF682","meters":["76"]},
    {"id":"morgan","name":"Morgan Hall","mac":"001EC6001BC1","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"boalt","name":"Boalt Hall","mac":"001EC6000793","db":"dbU216ucberkelF682","meters":["76","77"]},
    {"id":"mlk","name":"MLK Student Union","mac":"001EC6000481","db":"dbU216ucberkelF682","meters":["1"]},
    {"id":"rsf","name":"Rec Sports Facility","mac":"001EC6000CA0","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"chavez","name":"Chavez Center","mac":"001EC6000BB9","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"anthony","name":"Anthony Hall","mac":"001EC6000C9A","db":"dbU216ucberkelF682","meters":["76"]},
    {"id":"sproul","name":"Sproul Hall","mac":"001EC6000CAE","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"doe","name":"Doe Library","mac":"001EC6000C54","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"moffitt","name":"Moffitt Library","mac":"001EC6000C90","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"uhall","name":"University Hall","mac":"001EC6002D3C","db":"dbU216ucberkelF682","meters":["76"]},
    {"id":"northgate","name":"North Gate Hall","mac":"001EC6070132","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"donner","name":"Donner Laboratory","mac":"001EC6000C24","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"bww","name":"Berkeley Way West","mac":"001EC6000777","db":"dbU216ucberkelF682","meters":["3","76","77"]},
    {"id":"mulford","name":"Mulford Hall","mac":"001EC6000CB2","db":"dbU216ucberkelF682","meters":["3","76","77"]},
]

KW_COLUMNS = [
    "kW total (kW)", "Active Power Total (kW)", "kW total", "kW",
    "kW del-rec (kW)", "Power Total (kW)", "kW del (kW)",
    "Watts Total (kW)", "Watts, Total (kW)", "kW Total (kW)",
]

OUTPUT_DIR = Path("./data")
OUTPUT_FILE = OUTPUT_DIR / "campus_energy.json"
HISTORY_FILE = OUTPUT_DIR / "campus_energy_history.json"
MAX_HISTORY = 96  # 24hrs at 15min


def create_session():
    s = requests.Session()
    s.auth = (BMO_USER, BMO_PASS)
    s.headers["User-Agent"] = "Mozilla/5.0 (Campus Energy v2)"
    r = s.get(f"{BMO_BASE}/members/", timeout=30)
    if r.status_code == 401:
        raise Exception("BMO login failed")
    return s


def fetch_latest_kw(session, mac, db, meter_id):
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
        for col in KW_COLUMNS:
            val = last_row.get(col)
            if val is not None:
                try:
                    kw = float(val)
                    if 0 < kw < 50000:
                        return round(kw, 1), timestamp
                except (ValueError, TypeError):
                    pass
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


def load_history():
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def detect_anomaly(history, bid, kw):
    if kw is None:
        return None
    pts = history.get(bid, [])
    recent = [p["kw"] for p in pts[-8:] if p.get("kw")]
    if len(recent) < 4:
        return None
    avg = sum(recent) / len(recent)
    if avg > 0 and kw > avg * 1.5:
        return {"type": "high", "current": kw, "avg": round(avg, 1), "ratio": round(kw / avg, 2)}
    if avg > 10 and kw < avg * 0.3:
        return {"type": "low", "current": kw, "avg": round(avg, 1), "ratio": round(kw / avg, 2)}
    return None


def predict_next(history, bid):
    pts = history.get(bid, [])
    recent = [p["kw"] for p in pts[-4:] if p.get("kw")]
    if len(recent) < 2:
        return None
    weights = list(range(1, len(recent) + 1))
    return round(sum(v * w for v, w in zip(recent, weights)) / sum(weights), 1)


def run():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"BMO Campus Energy v2 — {now_str}")

    session = create_session()
    print("  ✓ Logged in\n")

    history = load_history()
    results = {}
    online = 0

    for b in BUILDINGS:
        bid = b["id"]
        # Skip if already got data for this building (alias/fallback)
        if bid in results and results[bid]["kw"] is not None:
            continue

        kw, ts, meter_used = None, None, None
        for mid in b["meters"]:
            kw, ts = fetch_latest_kw(session, b["mac"], b["db"], mid)
            if kw is not None:
                meter_used = mid
                break

        if bid not in results or (kw is not None and (results.get(bid, {}).get("kw") is None)):
            if kw is not None:
                online += 1
                # Update history
                if bid not in history:
                    history[bid] = []
                history[bid].append({"kw": kw, "ts": ts, "t": datetime.now().strftime("%H:%M")})
                history[bid] = history[bid][-MAX_HISTORY:]

            anomaly = detect_anomaly(history, bid, kw)
            prediction = predict_next(history, bid)
            sparkline = [p["kw"] for p in history.get(bid, [])[-24:]]

            results[bid] = {
                "name": b["name"].replace(" (Legacy)", ""),
                "kw": kw,
                "status": "online" if kw else "offline",
                "timestamp": ts,
                "mac": b["mac"],
                "meter": meter_used,
                "predicted_kw": prediction,
                "anomaly": anomaly,
                "sparkline": sparkline,
                "est_daily_kwh": round(kw * 24) if kw else None,
                "est_daily_cost": round(kw * 24 * COST_PER_KWH, 2) if kw else None,
                "est_daily_co2_kg": round(kw * 24 * CO2_PER_KWH, 1) if kw else None,
            }

        icon = "✅" if kw else "·"
        kw_str = f"{kw} kW (m#{meter_used})" if kw else "no data"
        anom = f" ⚠️ {results[bid].get('anomaly',{}).get('type','')}" if results.get(bid,{}).get("anomaly") else ""
        print(f"  {icon} {b['name']:30s} {kw_str}{anom}")

    total_kw = round(sum(r["kw"] for r in results.values() if r["kw"]), 1)
    anomalies = {k: v["anomaly"] for k, v in results.items() if v.get("anomaly")}

    output = {
        "generated_at": now_str,
        "update_interval_min": 15,
        "buildings_total": len(results),
        "buildings_online": online,
        "total_kw": total_kw,
        "total_daily_kwh": round(total_kw * 24),
        "total_daily_cost": round(total_kw * 24 * COST_PER_KWH, 2),
        "total_daily_co2_kg": round(total_kw * 24 * CO2_PER_KWH, 1),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "buildings": results,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)

    print(f"\n  ✓ {online}/{len(results)} online | {total_kw} kW")
    print(f"  ✓ ~${output['total_daily_cost']}/day | ~{output['total_daily_co2_kg']} kg CO2/day")
    if anomalies:
        print(f"  ⚠️ Anomalies: {list(anomalies.keys())}")


if __name__ == "__main__":
    run()
