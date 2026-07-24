#!/usr/bin/env python3
"""
discover_channels.py — one-shot BMO channel inventory (runs on Actions).

For every AcquiSuite device the campus fetcher knows about (parsed live from
bmo_fetch_campus.py so the list can't drift), probes candidate meter IDs via
the same mbdev_export.php CSV endpoint and records each responding meter's
column headers. Flow/gas/steam channels are flagged with a regex so we can
see at a glance which buildings expose more than electricity.

Output: data/bmo_channels_report.json
Never raises: any failure is recorded per-device and the script exits 0.
"""
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    print('discover: requests missing')
    sys.exit(0)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'data', 'bmo_channels_report.json')

BMO_BASE = 'https://www.buildingmanageronline.com'
EXPORT = BMO_BASE + '/members/mbdev_export.php'
USER = os.environ.get('BMO_USERNAME', '')
PW = os.environ.get('BMO_PASSWORD', '')

# meter IDs seen anywhere in the repo + common Obvius slots (incl. 250 pulse/flow)
CANDIDATE_IDS = sorted(set(
    [str(i) for i in range(1, 11)] +
    ['29', '30', '48', '53', '58', '63', '76', '77', '91', '92', '93', '94', '97', '250', '251']
))
FLOW_RE = re.compile(r'gal|gpm|cf|cubic|steam|water|gas|therm|btu|flow|irrig', re.I)


def devices_from_campus_script():
    """Parse the BUILDINGS list out of bmo_fetch_campus.py (single source)."""
    src = open(os.path.join(ROOT, 'bmo_fetch_campus.py')).read()
    out, seen = [], set()
    for m in re.finditer(r'\{"id":"([^"]+)","name":"([^"]+)","mac":"([0-9A-F]+)","db":"([^"]+)","meters":\[([^\]]*)\]', src):
        bid, name, mac, db, meters = m.groups()
        if mac in seen:
            continue
        seen.add(mac)
        known = re.findall(r'"(\d+)"', meters)
        out.append({'id': bid, 'name': name, 'mac': mac, 'db': db, 'known_meters': known})
    return out


def probe(session, dev, mid, start, end):
    try:
        r = session.get(EXPORT + f'/{dev["mac"]}_{mid}.csv', params={
            'DB': dev['db'], 'AS': dev['mac'], 'MB': mid, 'DOWNLOAD': 'YES',
            'DATE_RANGE_STARTTIME': start, 'DATE_RANGE_ENDTIME': end,
            'DELIMITER': 'TAB', 'COLNAMES': 'ON', 'EXPORTTIMEZONE': 'US/Pacific',
        }, timeout=15)
        if r.status_code != 200 or '<html' in r.text.lower()[:200]:
            return None
        lines = [l for l in r.text.splitlines() if l.strip()]
        if not lines:
            return None
        cols = [c.strip().strip('"') for c in lines[0].split('\t') if c.strip()]
        if len(cols) < 2:
            return None
        return {'columns': cols, 'rows': max(0, len(lines) - 1),
                'flow_like': [c for c in cols if FLOW_RE.search(c)]}
    except Exception:
        return None


def main():
    if not USER or not PW:
        print('discover: no BMO credentials — skipping')
        return
    s = requests.Session()
    s.auth = (USER, PW)
    s.headers.update({'User-Agent': 'Mozilla/5.0 (channel discovery, one-shot)'})
    try:
        s.get(BMO_BASE + '/members/', timeout=30).raise_for_status()
    except Exception as e:
        print('discover: login failed', e)
        return

    end = datetime.now()
    start = end - timedelta(hours=2)
    ss, ee = start.strftime('%Y-%m-%d+%H:%M:%S'), end.strftime('%Y-%m-%d+%H:%M:%S')

    devices = devices_from_campus_script()
    report = {'_schema': 'bmo-channels/1',
              'generated_at': end.strftime('%Y-%m-%d %H:%M:%S'),
              'candidate_ids': CANDIDATE_IDS,
              'devices': {}}
    flow_summary = {}
    for dev in devices:
        ids = sorted(set(dev['known_meters']) | set(CANDIDATE_IDS), key=lambda x: int(x))
        meters = {}
        for mid in ids:
            info = probe(s, dev, mid, ss, ee)
            if info:
                meters[mid] = info
            time.sleep(0.05)
        report['devices'][dev['mac']] = {'building': dev['id'], 'name': dev['name'], 'meters': meters}
        fl = {mid: m['flow_like'] for mid, m in meters.items() if m['flow_like']}
        if fl:
            flow_summary[dev['id']] = fl
        print(f'{dev["id"]:12s} {dev["mac"]}: {len(meters)} meters respond, '
              f'{sum(len(v["flow_like"]) for v in meters.values())} flow-like cols')
    report['flow_summary'] = flow_summary
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w') as f:
        json.dump(report, f, indent=1)
    print('report written:', OUT)


if __name__ == '__main__':
    main()
