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

import os, csv, io, json, re, sys, statistics, requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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
    # "stanley" removed 2026-07: its MAC (001EC6000C5A) duplicated Grimes — readings were
    # actually Grimes meter #3. Re-add only after confirming Stanley's real AcquiSuite MAC.
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

# History is time-windowed (not count-capped): GitHub's cron actually fires every
# few hours, so a fixed row count says nothing about elapsed time.
HISTORY_HOURS = 24         # rows kept, by BMO timestamp
FIRST_RUN_WINDOW_H = 2     # request window when a building has no stored rows
MAX_WINDOW_H = 24          # upper bound for catch-up requests after an outage
SLOT_MIN = 5               # meters' rows are aligned to this grid before summing

PT = ZoneInfo("America/Los_Angeles")
TS_FMT = "%Y-%m-%d %H:%M:%S"
TS_COL = "time (US/Pacific)"


class BMOOutage(Exception):
    """BMO unreachable / maintenance / 5xx: callers must NOT overwrite published data."""


_MAINTENANCE = re.compile(
    r"(under|scheduled|down for|offline for)\s+(scheduled\s+)?maintenance|"
    r"temporarily unavailable|service unavailable", re.I)


def now_utc():
    return datetime.now(timezone.utc)


def pacific_now():
    """Naive America/Los_Angeles wall time (BMO exports are naive Pacific)."""
    return now_utc().astimezone(PT).replace(tzinfo=None)


def parse_pt(s):
    try:
        return datetime.strptime(str(s).strip()[:19], TS_FMT)
    except (ValueError, TypeError):
        return None


def is_ambiguous_pt(naive):
    """True for fall-back repeated hour or spring-forward gap: wall time maps to no single instant."""
    return naive.replace(tzinfo=PT, fold=0).utcoffset() != naive.replace(tzinfo=PT, fold=1).utcoffset()


def bmo_param_time(dt):
    return dt.strftime("%Y-%m-%d+%H:%M:%S")


def create_session():
    s = requests.Session()
    s.auth = (BMO_USER, BMO_PASS)
    s.headers["User-Agent"] = "Mozilla/5.0 (Campus Energy v2)"
    try:
        r = s.get(f"{BMO_BASE}/members/", timeout=30)
    except requests.RequestException as e:
        raise BMOOutage("BMO unreachable: %s" % e)
    if r.status_code == 401:
        raise Exception("BMO login failed")
    if not 200 <= r.status_code < 300:
        raise BMOOutage("BMO login page HTTP %s" % r.status_code)
    if _MAINTENANCE.search(r.text[:5000]):
        raise BMOOutage("BMO maintenance page")
    return s


def _kw_from_row(row):
    for col in KW_COLUMNS:
        val = row.get(col)
        if val is not None:
            try:
                kw = float(val)
                if 0 <= kw < 50000:
                    return round(kw, 1)
            except (ValueError, TypeError):
                pass
    for col_name, val in row.items():
        if col_name and "kW" in col_name and "kWh" not in col_name:
            try:
                kw = float(val)
                if 0 <= kw < 50000:
                    return round(kw, 1)
            except (ValueError, TypeError):
                pass
    return None


def fetch_kw_rows(session, mac, db, meter_id, start, end):
    """All interval rows in [start, end] (naive Pacific) -> [(ts, kw)] ascending.

    Rows with an unparsable or DST-ambiguous timestamp are unknown and dropped.
    Any failure yields [] (the caller treats that as "no data", never zero).
    """
    url = f"{BMO_BASE}/members/mbdev_export.php/{mac}_{meter_id}.csv"
    params = {
        "DB": db, "AS": mac, "MB": meter_id, "DOWNLOAD": "YES",
        "DATE_RANGE_STARTTIME": bmo_param_time(start),
        "DATE_RANGE_ENDTIME": bmo_param_time(end),
        "DELIMITER": "TAB", "COLNAMES": "ON", "EXPORTTIMEZONE": TIMEZONE,
    }
    try:
        r = session.get(url, params=params, timeout=20)
        if r.status_code != 200 or "<html" in r.text[:200].lower():
            return []
        out = []
        for row in csv.DictReader(io.StringIO(r.text), delimiter="\t"):
            ts = row.get(TS_COL, "")
            dt = parse_pt(ts)
            if dt is None or is_ambiguous_pt(dt):
                continue
            kw = _kw_from_row(row)
            if kw is not None:
                out.append((dt, ts.strip(), kw))
        out.sort(key=lambda x: x[0])
        return [(ts, kw) for _, ts, kw in out]
    except Exception:
        return []


def fetch_latest_kw(session, mac, db, meter_id):
    """Latest single reading of one meter -> (kw, ts); kept for ad-hoc callers/tests."""
    now = pacific_now()
    rows = fetch_kw_rows(session, mac, db, meter_id, now - timedelta(hours=FIRST_RUN_WINDOW_H), now)
    return (rows[-1][1], rows[-1][0]) if rows else (None, None)


def _slot(dt):
    base = dt.replace(minute=0, second=0, microsecond=0)
    return base + timedelta(minutes=int(round((dt.minute + dt.second / 60) / SLOT_MIN)) * SLOT_MIN)


def combine_meters(per_meter):
    """{meter: [(ts, kw)]} -> ([(ts, kw_sum)] ascending, meters_used).

    A building's load is the SUM of its meters. Only slots where every
    responding meter has a row are emitted, so a lagging meter never produces
    a stored partial sum. If no slot is complete (meters on unaligned grids),
    fall back to the sum of each meter's latest row -- the legacy single
    reading -- rather than reporting the building offline.
    """
    live = {mid: rows for mid, rows in per_meter.items() if rows}
    if not live:
        return [], []
    slots = {}
    for mid, rows in live.items():
        for ts, kw in rows:
            slots.setdefault(_slot(parse_pt(ts)), {})[mid] = (ts, kw)   # last row in slot wins
    out = []
    for key in sorted(slots):
        got = slots[key]
        if len(got) == len(live):
            ts = max((v[0] for v in got.values()), key=parse_pt)
            out.append((ts, round(sum(v[1] for v in got.values()), 1)))
    if not out:
        last = [rows[-1] for rows in live.values()]
        out = [(max((t for t, _ in last), key=parse_pt), round(sum(k for _, k in last), 1))]
    return out, sorted(live)


def window_start(history_rows, now_pt):
    """Request start: last stored BMO timestamp, bounded to MAX_WINDOW_H; 2 h when nothing stored."""
    stamps = [parse_pt(e.get("ts")) for e in history_rows or []]
    stamps = [t for t in stamps if t]
    if not stamps:
        return now_pt - timedelta(hours=FIRST_RUN_WINDOW_H)
    return max(max(stamps), now_pt - timedelta(hours=MAX_WINDOW_H))


def merge_history(existing, new_rows, now_pt, run_t):
    """De-duplicate by timestamp, keep a HISTORY_HOURS window by BMO timestamp."""
    by_ts = {e["ts"]: e for e in existing or [] if e.get("ts")}
    for ts, kw in new_rows:
        old = by_ts.get(ts)
        by_ts[ts] = {"kw": kw, "ts": ts, "t": old["t"] if old and old.get("t") else run_t}
    cutoff = now_pt - timedelta(hours=HISTORY_HOURS)
    keep = [(parse_pt(ts), e) for ts, e in by_ts.items()]
    return [e for t, e in sorted(((t, e) for t, e in keep if t and t >= cutoff), key=lambda x: x[0])]


def observed_interval_min(history):
    """Median spacing of stored rows (gaps over 3 h ignored); None if undeterminable."""
    diffs = []
    for rows in history.values():
        ts = sorted(t for t in (parse_pt(e.get("ts")) for e in rows) if t)
        diffs += [(b - a).total_seconds() / 60 for a, b in zip(ts, ts[1:])
                  if 0 < (b - a).total_seconds() <= 3 * 3600]
    return round(statistics.median(diffs)) if diffs else None


# Soda logger 250 exposes two distinct electric demand channels alongside flow.
# Never add these to the legacy building aggregate: feeder boundaries unverified.
def fetch_soda_electric_channels(session, previous=()):
    b = next(b for b in BUILDINGS if b["id"] == "soda")
    url = f"{BMO_BASE}/members/mbdev_export.php/{b['mac']}_250.csv"
    columns = ["Electric Main#1 (#...213) Demand (kW)",
               "Electric Main#2 (#...378) Demand (kW)"]
    channels = [{"device_id": "250", "column": col, "unit": "kW",
                 "kw": None, "timestamp": None, "timezone": "America/Los_Angeles",
                 "source": url, "status": "unavailable"} for col in columns]
    for c in channels:
        old = next((v for v in previous if v.get("column") == c["column"]), {})
        c["last_observed_at"] = old.get("timestamp") if old.get("kw") is not None else old.get("last_observed_at")
    now = pacific_now()
    params = {"DB": b["db"], "AS": b["mac"], "MB": "250", "DOWNLOAD": "YES",
              "DATE_RANGE_STARTTIME": bmo_param_time(now-timedelta(hours=2)),
              "DATE_RANGE_ENDTIME": bmo_param_time(now),
              "DELIMITER": "TAB", "COLNAMES": "ON", "EXPORTTIMEZONE": TIMEZONE}
    try:
        r = session.get(url, params=params, timeout=20)
        if r.status_code != 200 or "<html" in r.text[:200].lower():
            return channels
        rows = list(csv.DictReader(io.StringIO(r.text), delimiter="\t"))
        if not rows:
            return channels
        row = rows[-1]
        for c in channels:
            c["timestamp"] = row.get("time (US/Pacific)") or None
            c["status"] = "column_missing" if c["column"] not in row else "invalid_or_missing"
            try:
                value = float(row.get(c["column"]))
                if 0 <= value < 50000:
                    c["kw"] = value
                    c["status"] = "observed"
                    c["last_observed_at"] = c["timestamp"]
            except (TypeError, ValueError):
                pass
    except requests.RequestException:
        pass
    return channels


# ── Flow channels (water / steam / condensate / irrigation) ───────────────
# Discovered by scripts/discover_channels.py → data/bmo_channels_report.json:
# 29 buildings expose non-electric channels, almost all on meter #250 (plus a
# few odd slots). Column names vary per site, so channels are classified by
# regex; only the Ave-Rate style columns are summed (Min/Max/Inst skipped).
import re as _re

FLOW_METERS = {
    "grimes": ["250"], "cory": ["250"], "soda": ["250"], "davis": ["250"],
    "etch": ["250"], "hmm": ["250"], "hesse": ["250"], "mclaughlin": ["250"],
    "latimer": ["250"], "birge": ["250"], "hilde": ["250"], "lksc": ["1"],
    "wheeler": ["250"], "dwinelle": ["250", "53"], "barrows": ["250"],
    "moses": ["250"], "stephens": ["250"], "wurster": ["250"],
    "giannini": ["250"], "morgan": ["250"], "rsf": ["250"],
    "chavez": ["250", "3"], "sproul": ["250"], "doe": ["250"],
    "moffitt": ["250"], "northgate": ["2"], "donner": ["250"],
    "bww": ["250"], "mulford": ["250"],
}

_FLOW_UNIT = _re.compile(r"\((cfm|gpm|lb/hr)\)", _re.I)


def _classify_flow_col(col):
    """column name -> (kind, unit) or None. Rate columns only."""
    c = col.lower()
    m = _FLOW_UNIT.search(c)
    if not m:
        return None
    if "min (" in c or "max (" in c or "instantaneous" in c:
        return None
    unit = m.group(1)
    if "irrig" in c:
        kind = "irrigation"
    elif "condensate" in c:
        kind = "condensate"
    elif "steam" in c:
        kind = "steam"
    elif "water" in c:
        kind = "water"
    else:
        return None
    return kind, unit


def _aggregate_flow_row(row):
    """last CSV row -> partial sums per kind, CFm converted to GPM."""
    by_kind = {}
    cols = {}
    for col in row.keys():
        k = _classify_flow_col(col)
        if k:
            cols.setdefault(k[0], []).append((col, k[1]))
    for kind, cands in cols.items():
        low = [(c, u, c.lower()) for c, u in cands]
        use = ([(c, u) for c, u, l in low if "ave" in l]
               or [(c, u) for c, u, l in low if "rate" in l]
               or cands)
        total = 0.0
        got = False
        for col, unit in use:
            try:
                v = float(row.get(col))
            except (TypeError, ValueError):
                continue
            if not (0 <= v < 1e6):
                continue
            total += v * 7.481 if unit == "cfm" else v
            got = True
        if got:
            by_kind[kind] = round(total, 2)
    return by_kind


def fetch_flow(session, mac, db, meter_ids):
    """-> {'water_gpm','steam_lb_hr','condensate_gpm','irrigation_gpm','ts'} (None-filled)."""
    out = {"water_gpm": None, "steam_lb_hr": None, "condensate_gpm": None,
           "irrigation_gpm": None, "ts": None}
    keymap = {"water": "water_gpm", "steam": "steam_lb_hr",
              "condensate": "condensate_gpm", "irrigation": "irrigation_gpm"}
    now = pacific_now()
    start = now - timedelta(hours=2)
    for mid in meter_ids:
        url = f"{BMO_BASE}/members/mbdev_export.php/{mac}_{mid}.csv"
        params = {
            "DB": db, "AS": mac, "MB": mid, "DOWNLOAD": "YES",
            "DATE_RANGE_STARTTIME": bmo_param_time(start),
            "DATE_RANGE_ENDTIME": bmo_param_time(now),
            "DELIMITER": "TAB", "COLNAMES": "ON", "EXPORTTIMEZONE": TIMEZONE,
        }
        try:
            r = session.get(url, params=params, timeout=20)
            if r.status_code != 200 or "<html" in r.text[:200].lower():
                continue
            rows = list(csv.DictReader(io.StringIO(r.text), delimiter="\t"))
            if not rows:
                continue
            last = rows[-1]
            out["ts"] = last.get("time (US/Pacific)", out["ts"])
            for kind, v in _aggregate_flow_row(last).items():
                key = keymap[kind]
                out[key] = round((out[key] or 0.0) + v, 2)
        except Exception:
            continue
    return out


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
    """Fetch, merge, publish. Returns a process exit code.

    Non-zero (nothing written) when BMO is down or no building answered: the
    previously published files then remain and pages show them as older
    readings instead of a fabricated all-zero campus.
    """
    now_str = now_utc().strftime(TS_FMT)
    run_t = now_utc().strftime("%H:%M")
    now_pt = pacific_now()
    print(f"BMO Campus Energy v2 — {now_str} UTC / {now_pt.strftime(TS_FMT)} Pacific")

    try:
        session = create_session()
    except BMOOutage as e:
        print(f"::error::BMO outage, keeping previous data: {e}")
        return 2
    except Exception as e:
        print(f"::error::BMO login failed: {e}")
        return 1
    print("  ✓ Logged in\n")

    history = load_history()
    try:
        prev_out = json.loads(OUTPUT_FILE.read_text())
    except (OSError, ValueError):
        prev_out = {}
    prior_channels = (prev_out.get("buildings", {}).get("soda", {}) or {}).get("electricity_channels", [])
    results = {}
    online = 0

    for b in BUILDINGS:
        bid = b["id"]
        # Skip if already got data for this building (alias/fallback)
        if bid in results and results[bid]["kw"] is not None:
            continue

        # Sum every meter that responds — a building's load is the SUM of its
        # meters (e.g. Grimes = #3 roof + #76 HVAC/lighting + #77 outlets).
        # Request everything since the last stored row, parse ALL rows.
        start = window_start(history.get(bid), now_pt)
        per_meter = {mid: fetch_kw_rows(session, b["mac"], b["db"], mid, start, now_pt)
                     for mid in b["meters"]}
        rows, meters_used_ids = combine_meters(per_meter)
        kw, ts = (rows[-1][1], rows[-1][0]) if rows else (None, None)
        meter_used = "+".join(meters_used_ids) if meters_used_ids else None

        if bid not in results or (kw is not None and (results.get(bid, {}).get("kw") is None)):
            if kw is not None:
                online += 1
                history[bid] = merge_history(history.get(bid), rows, now_pt, run_t)
            elif bid in history:
                history[bid] = merge_history(history[bid], [], now_pt, run_t)

            anomaly = detect_anomaly(history, bid, kw)
            prediction = predict_next(history, bid)
            sparkline = [p["kw"] for p in history.get(bid, [])[-24:]]

            results[bid] = {
                "name": b["name"].replace(" (Legacy)", ""),
                "kw": kw,
                "status": "online" if kw is not None else "offline",
                "timestamp": ts,
                "mac": b["mac"],
                "meter": meter_used,
                "meters_configured": b["meters"],
                "predicted_kw": prediction,
                "anomaly": anomaly,
                "sparkline": sparkline,
                "est_daily_kwh": round(kw * 24) if kw is not None else None,
                "est_daily_cost": round(kw * 24 * COST_PER_KWH, 2) if kw is not None else None,
                "est_daily_co2_kg": round(kw * 24 * CO2_PER_KWH, 1) if kw is not None else None,
            }

        if bid == "soda":
            results[bid]["electricity_channels"] = fetch_soda_electric_channels(session, prior_channels)
            results[bid]["electricity_scope"] = "Separate demand channels; feeder overlap unverified; not summed"

        # flow channels (water/steam) where the logger exposes them
        if bid in results and bid in FLOW_METERS and "flow" not in results[bid]:
            results[bid]["flow"] = fetch_flow(session, b["mac"], b["db"], FLOW_METERS[bid])

        icon = "✅" if kw is not None else "·"
        kw_str = f"{kw} kW (m#{meter_used})" if kw is not None else "no data"
        anom = f" ⚠️ {results[bid].get('anomaly',{}).get('type','')}" if results.get(bid,{}).get("anomaly") else ""
        print(f"  {icon} {b['name']:30s} {kw_str}{anom}")

    if online == 0:
        print("::error::0 buildings returned data (BMO outage?) — nothing written, previous files kept")
        return 3

    total_kw = round(sum(r["kw"] for r in results.values() if r["kw"] is not None), 1)
    anomalies = {k: v["anomaly"] for k, v in results.items() if v.get("anomaly")}

    output = {
        "generated_at": now_str,
        # observed spacing of BMO rows (cron firing cadence is NOT the data cadence)
        "update_interval_min": observed_interval_min(history) or prev_out.get("update_interval_min"),
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

    # ── Save daily snapshot (append to today's file) ──
    daily_dir = OUTPUT_DIR / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    today_str = now_utc().strftime("%Y-%m-%d")
    daily_file = daily_dir / f"{today_str}.json"
    try:
        with open(daily_file) as f:
            daily = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        daily = {"date": today_str, "readings": []}

    daily["readings"].append({
        "time": run_t,
        "total_kw": total_kw,
        "online": online,
        "buildings": {bid: r["kw"] for bid, r in results.items() if r["kw"] is not None}
    })
    with open(daily_file, "w") as f:
        json.dump(daily, f)

    # ── Update daily index ──
    daily_files = sorted(daily_dir.glob("*.json"))
    index = [f.stem for f in daily_files if f.stem != "index"]
    with open(daily_dir / "index.json", "w") as f:
        json.dump({"days": index, "updated": now_str}, f)

    print(f"\n  ✓ {online}/{len(results)} online | {total_kw} kW")
    print(f"  ✓ ~${output['total_daily_cost']}/day | ~{output['total_daily_co2_kg']} kg CO2/day")
    if anomalies:
        print(f"  ⚠️ Anomalies: {list(anomalies.keys())}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
