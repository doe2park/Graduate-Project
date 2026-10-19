"""Zone definitions for splitting Gaussian training of one capture across people.

scripts/gaussian_zones.json (schema 1) lists, per capture date, the zones of that capture:

    {"schema": 1, "captures": {"2026-09-17": {"building": "grimes", "floor": "L1",
        "manifest": "scan-assets/captures/2026-09-17/panoramas/manifest.json",
        "zones": [{"id": "l1-a", "name": "...", "stations": [...], "core": [...],
                   "overlapMetres": 3.0, "owner": "", "status": "unassigned"}]}}}

`core` is the set of stations a zone is responsible for (cores partition the capture); `stations` is the
training set: the core plus every station within overlapMetres of it, so neighbouring zones overlap at seams.

New floors or buildings are just more capture entries: run scripts/plan_gaussian_zones.py on that capture's
panorama manifest. Floor labels: L1, L2, L3, B1 (basement), ... Pure helpers only; no training code here.
"""
import json
import math
import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ZONES_PATH = SCRIPTS / 'gaussian_zones.json'
SCHEMA = 1
STATUSES = ('unassigned', 'claimed', 'training', 'review', 'published')
ZONE_ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,30}$')
FLOOR = re.compile(r'^(L|B)[1-9][0-9]?$')


class ZoneError(ValueError):
    """Invalid zone file or unknown zone; message is shown to the user."""


def load_zones(path=ZONES_PATH):
    return validate_zones(json.loads(Path(path).read_text()))


def validate_zones(doc, station_ids_by_capture=None):
    """Structural validation. With station_ids_by_capture {capture: set(ids)}, also checks every id exists."""
    if not isinstance(doc, dict) or doc.get('schema') != SCHEMA:
        raise ZoneError('Unsupported zones schema (expected schema 1)')
    captures = doc.get('captures')
    if not isinstance(captures, dict):
        raise ZoneError('Zones file needs a "captures" object')
    for capture, entry in captures.items():
        where = f'capture {capture}'
        # A date, optionally with a floor suffix when one day's capture spans floors (e.g. 2026-10-18-L3).
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}(-[A-Za-z0-9]+)?', capture):
            raise ZoneError(f'{where}: key must be a YYYY-MM-DD capture date, optionally with a -FLOOR suffix')
        if not isinstance(entry.get('building'), str) or not entry['building']:
            raise ZoneError(f'{where}: missing "building"')
        if not isinstance(entry.get('floor'), str) or not FLOOR.match(entry['floor']):
            raise ZoneError(f'{where}: "floor" must be a label like L1, L2, L3 or B1')
        zones = entry.get('zones')
        if not isinstance(zones, list) or not zones:
            raise ZoneError(f'{where}: needs a non-empty "zones" list')
        seen_ids, claimed_core = set(), {}
        known = (station_ids_by_capture or {}).get(capture)
        for zone in zones:
            zid = zone.get('id') if isinstance(zone, dict) else None
            if not isinstance(zid, str) or not ZONE_ID.match(zid):
                raise ZoneError(f'{where}: zone id must be lowercase letters, digits or "-" (got {zid!r})')
            if zid in seen_ids:
                raise ZoneError(f'{where}: duplicate zone id {zid}')
            seen_ids.add(zid)
            if not isinstance(zone.get('name'), str) or not zone['name'].strip():
                raise ZoneError(f'{where}/{zid}: missing "name"')
            for key in ('stations', 'core'):
                ids = zone.get(key)
                if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
                    raise ZoneError(f'{where}/{zid}: "{key}" must be a non-empty list of station ids')
                if len(set(ids)) != len(ids):
                    raise ZoneError(f'{where}/{zid}: duplicate ids in "{key}"')
            if not set(zone['core']) <= set(zone['stations']):
                raise ZoneError(f'{where}/{zid}: every core station must be in "stations"')
            if len(zone['stations']) < 4:
                raise ZoneError(f'{where}/{zid}: a zone needs at least 4 stations to train')
            overlap = zone.get('overlapMetres')
            if isinstance(overlap, bool) or not isinstance(overlap, (int, float)) or not math.isfinite(overlap) or overlap < 0:
                raise ZoneError(f'{where}/{zid}: "overlapMetres" must be a non-negative number')
            if not isinstance(zone.get('owner'), str):
                raise ZoneError(f'{where}/{zid}: "owner" must be a string (empty when unclaimed)')
            if zone.get('status') not in STATUSES:
                raise ZoneError(f'{where}/{zid}: "status" must be one of {list(STATUSES)}')
            if zone['status'] != 'unassigned' and not zone['owner']:
                raise ZoneError(f'{where}/{zid}: status {zone["status"]!r} needs an owner')
            for sid in zone['core']:
                if sid in claimed_core:
                    raise ZoneError(f'{where}: station {sid} is core of both {claimed_core[sid]} and {zid}')
                claimed_core[sid] = zid
            if known is not None:
                missing = [s for s in zone['stations'] if s not in known]
                if missing:
                    raise ZoneError(f'{where}/{zid}: stations not in the manifest: {missing[:5]}')
    return doc


def get_zone(doc, capture, zone_id):
    entry = doc['captures'].get(capture)
    if entry is None:
        raise ZoneError(f'No zones defined for capture {capture!r}; defined: {sorted(doc["captures"])}')
    for zone in entry['zones']:
        if zone['id'] == zone_id:
            return zone
    raise ZoneError(f'Unknown zone {zone_id!r} for {capture}; choose from {[z["id"] for z in entry["zones"]]}')


def zone_ids(doc, capture):
    entry = doc['captures'].get(capture)
    if entry is None:
        raise ZoneError(f'No zones defined for capture {capture!r}; defined: {sorted(doc["captures"])}')
    return [z['id'] for z in entry['zones']]


def describe_zones(doc, capture=None):
    """Human readable listing for --list-zones."""
    lines = []
    for cap in ([capture] if capture else sorted(doc['captures'])):
        if cap not in doc['captures']:
            raise ZoneError(f'No zones defined for capture {cap!r}; defined: {sorted(doc["captures"])}')
        entry = doc['captures'][cap]
        lines.append(f'{cap}  {entry["building"]} {entry["floor"]}  ({len(entry["zones"])} zones)')
        for z in entry['zones']:
            lines.append(f'  {z["id"]:<8} {z["name"]:<34} core {len(z["core"]):>3}  train {len(z["stations"]):>3}  '
                         f'overlap {z["overlapMetres"]:g} m  {z["status"]:<10} owner: {z["owner"] or "-"}')
    return '\n'.join(lines)


def parse_station_list(text):
    """Station ids from 'a,b,c' or '@file' (ids separated by commas, spaces or newlines; '#' starts a comment)."""
    if text.startswith('@'):
        raw = Path(text[1:]).read_text()
        raw = '\n'.join(line.split('#', 1)[0] for line in raw.splitlines())
    else:
        raw = text
    ids = [t for t in re.split(r'[,\s]+', raw) if t]
    if not ids:
        raise ZoneError('--stations needs at least one station id')
    if len(set(ids)) != len(ids):
        raise ZoneError('--stations contains duplicate ids')
    return ids


def bounds_of(points):
    """{'min': [x,y,z], 'max': [x,y,z]} of 3D points (original scan Y-up metre frame)."""
    xs = list(zip(*points))
    return {'min': [round(min(c), 3) for c in xs], 'max': [round(max(c), 3) for c in xs]}


def zone_geometry(zone, manifest_stations):
    """Everything the pipeline and viewer need from a zone and the manifest stations.

    centerId  : core station nearest the core's XZ centroid (initial camera, seed-mesh centre)
    radius    : metres from centerId to the farthest training station + 1 m (seed-mesh reach)
    bounds / coreBounds : 3D boxes of training / core station positions
    corePositions : [[x, z], ...] core station positions in XZ, for nearest-zone selection in the viewer
    """
    by_id = {s['id']: s['position'] for s in manifest_stations}
    missing = [i for i in zone['stations'] if i not in by_id]
    if missing:
        raise ZoneError(f'Zone {zone["id"]}: stations not in the manifest: {missing[:5]}')
    core = [by_id[i] for i in zone['core']]
    cx = sum(p[0] for p in core) / len(core)
    cz = sum(p[2] for p in core) / len(core)
    center_id = min(zone['core'], key=lambda i: (by_id[i][0] - cx) ** 2 + (by_id[i][2] - cz) ** 2)
    c = by_id[center_id]
    radius = max(math.dist(c, by_id[i]) for i in zone['stations']) + 1.0
    return {'centerId': center_id, 'radius': round(radius, 2),
            'bounds': bounds_of([by_id[i] for i in zone['stations']]),
            'coreBounds': bounds_of(core),
            'corePositions': [[round(p[0], 2), round(p[2], 2)] for p in core]}
