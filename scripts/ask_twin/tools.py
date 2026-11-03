"""Read-only tools over the Grimes twin data for the Ask-the-twin demo.

Every function is pure over loaded data (sidecars, the derived box index, the sensor registry, the demo simulator).
Nothing here writes files or calls the network. Each result says what kind of evidence it is:
  - "design BIM"  : sidecar fields of the original model (identity, type, CAD layer, level, design parameters)
  - "geometry"    : distances/directions computed from element bounding boxes in the viewer frame
  - "inferred"    : heuristics (room from nearby labelled equipment, service from family names, box adjacency)
  - "demo-sim"    : simulated demo sensors (twin/sensors/registry.json); no sensor is installed in Grimes
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

from . import index as ix

ROOT = ix.ROOT
LEVELS = [('LOWER', 1.524), ('MEZZ', 2.286), ('L1', 6.096), ('L2', 10.363), ('L3', 15.24), ('ROOF', 19.812)]  # manifest.json viewerY
CELL = 2.0
MAX_LIST = 25

# US National CAD Standard layer-name convention (interpretation of the CAD layer code, not a model field).
SYSTEM_CODES = {
    'M-HVAC-DUCT': 'HVAC ductwork', 'M-HVAC-CDFF': 'HVAC ceiling diffusers', 'M-EQPM': 'mechanical equipment',
    'P-PIPE': 'piping (plumbing/mechanical CAD layer)', 'P-SANR-FIXT': 'sanitary fixtures', 'Z-MNTG': 'mounting/support',
    'E-POWR-CNDT': 'power conduit', 'A-GENM': 'architectural general', 'S-FNDN': 'foundation', 'Q-SPCQ': 'special equipment',
    'F-SPRN-MAIN': 'fire sprinkler main', 'F-SPRN-LINE': 'fire sprinkler branch line', 'F-SPRN-FITG': 'fire sprinkler fitting',
    'F-SPRN-HANG': 'fire sprinkler hanger', 'F-SPRN-FLXD': 'fire sprinkler flex drop', 'F-SPRN-EOLR': 'fire sprinkler end-of-line restraint',
    'F-SRPN-PEND': 'fire sprinkler pendant head', 'F-SPRN-PEND': 'fire sprinkler pendant head'}

# (regex on family/name, service, medium, basis) - inferred from manufacturer/family names, never a model field.
SERVICE_RULES = [
    (r'no-hub|cast[- ]iron|charlotte', 'drain / waste / vent (gravity)', 'water when draining', 'cast-iron no-hub family name'),
    (r'drain pan', 'condensate drain pan', 'condensate water', 'family name'),
    (r'water heater|\bdve-52\b|iewh', 'domestic water heater', 'pressurized hot water', 'family name'),
    (r'ball valve', 'isolation (shut-off) valve', 'pressurized water', 'ball valve family name'),
    (r'butterfly valve', 'isolation (shut-off) valve', 'pressurized water', 'butterfly valve family name'),
    (r'balanc(e|ing) valve|circuit setter', 'balancing valve (not a shut-off)', 'pressurized water', 'family name'),
    (r'check valve', 'check (backflow) valve, not a shut-off', 'pressurized water', 'family name'),
    (r'valve', 'valve (type unclear)', 'pressurized water', 'family name'),
    # 'Coil Kit Supply/Return_2019' (45 + 45 in the duct layer) are the hot-water pipe connection kits bolted to a Price SDV
    # box, not the box: their boxes touch the box and the duct, so without this rule they pose as the nearest terminal unit.
    (r'coil kit', 'reheat-coil pipe connection kit (accessory of a VAV box, not the box)', 'hot water', 'Coil Kit family name'),
    (r'coil|sdv5|vav', 'air terminal with hot-water reheat coil', 'hot water (coil) + air', 'Price SDV/coil family name'),
    (r'\bahu\b|air handl', 'air handling unit', 'air + chilled/hot water coils', 'family name'),
    (r'type l copper|propress|viega|copper', 'pressurized copper water piping (domestic or hydronic)', 'pressurized water', 'copper/press-fit family name'),
    (r'std blk erw|black steel|weld', 'steel piping (hydronic)', 'pressurized water', 'steel pipe family name'),
    (r'sprinkler|schedule 10|f-sprn|f-srpn', 'fire sprinkler piping', 'water (if wet system; not recorded)', 'fire layer / CAD layer'),
    (r'diffuser|grille|\bgrd\b', 'air outlet', 'air', 'family name'),
    (r'duct|spiral|rect', 'ductwork', 'air (condensation possible on cold ducts)', 'family name'),
]

WATER_LAYERS = ('plumbing', 'hydronic', 'fire', 'duct', 'equipment')
NOT_RUN = re.compile(r'hanger|support|clearance zone|anno|mounting|unistrut|brace|banger|nut$|sleeve|eV_Point|field weld', re.I)


def _r(v, d=2):
    return None if v is None else round(v, d)


def level_of_y(y: float) -> str:
    key = LEVELS[0][0]
    for k, ly in LEVELS:
        if y + 0.3 >= ly:
            key = k
    return key


class Twin:
    """Loaded twin data + spatial grid. Construct once per server."""

    def __init__(self, root: Path = ROOT, index: dict | None = None, registry: dict | None = None, log=print):
        self.root = root
        self.index = index or ix.load_index(root, log=log)
        self.meta: dict = {}
        self.box: dict = {}
        self.layer: dict = {}
        for key, L in self.index['layers'].items():
            side = json.loads((root / L['sidecar']).read_text())['elements']
            for eid, b in L['boxes'].items():
                self.box[eid], self.layer[eid], self.meta[eid] = b, key, side.get(eid, {})
        self.registry = registry or json.loads((root / 'twin' / 'sensors' / 'registry.json').read_text())
        self.sensors = {s['id']: s for s in self.registry['sensors'] if s.get('install_status') != 'retired'}
        self._grid: dict = {}
        self._big: list = []
        for eid, b in self.box.items():
            cells = self._cells(b)
            if len(cells) > 300:
                self._big.append(eid)
                continue
            for c in cells:
                self._grid.setdefault(c, []).append(eid)
        self._located = [(eid, m['location']) for eid, m in self.meta.items() if m.get('location')]

    # ---------- geometry helpers ----------
    @staticmethod
    def _cells(b, pad=0.0):
        x0, y0, z0 = (int(math.floor((b[i] - pad) / CELL)) for i in range(3))
        x1, y1, z1 = (int(math.floor((b[i + 3] + pad) / CELL)) for i in range(3))
        return [(x, y, z) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) for z in range(z0, z1 + 1)]

    def _candidates(self, b, pad):
        seen = set(self._big)
        for c in self._cells(b, pad):
            seen.update(self._grid.get(c, ()))
        return seen

    def ref_box(self, element_id=None, point=None):
        if element_id is not None:
            eid = str(element_id)
            if eid not in self.box:
                raise KeyError(f'unknown element id {eid!r}')
            return self.box[eid], eid
        if point is not None:
            if not (isinstance(point, (list, tuple)) and len(point) == 3 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in point)):
                raise ValueError('point must be [x, y, z] in metres (viewer frame)')
            x, y, z = point
            return [x, y, z, x, y, z], None
        raise ValueError('give element_id or point')

    @staticmethod
    def relation(ref, b):
        cr, cb = ix.box_center(ref), ix.box_center(b)
        hx = max(0.0, ref[0] - b[3], b[0] - ref[3])
        hz = max(0.0, ref[2] - b[5], b[2] - ref[5])
        hgap = math.hypot(hx, hz)
        if b[1] >= ref[4] - 0.02:
            vert, dy = 'above', b[1] - ref[4]
        elif b[4] <= ref[1] + 0.02:
            vert, dy = 'below', ref[1] - b[4]
        else:
            vert, dy = 'same height', 0.0
        return {'gap_m': _r(ix.box_gap(ref, b)), 'vertical': vert, 'vertical_gap_m': _r(max(0.0, dy)),
                'horizontal_gap_m': _r(hgap), 'center_offset_m': [_r(cb[0] - cr[0]), _r(cb[1] - cr[1]), _r(cb[2] - cr[2])]}

    # ---------- element descriptions ----------
    def service_hint(self, eid):
        m, layer = self.meta.get(eid, {}), self.layer.get(eid)
        text = ' '.join(str(m.get(k, '')) for k in ('name', 'family', 'revit_type', 'type', 'system'))
        if layer == 'fire':
            text += ' sprinkler'
        for rx, service, medium, basis in SERVICE_RULES:
            if re.search(rx, text, re.I):
                return {'service': service, 'medium': medium, 'basis': f'inferred from {basis}'}
        return None

    def summary(self, eid, ref=None):
        m, b = self.meta.get(eid, {}), self.box[eid]
        c = ix.box_center(b)
        out = {'id': eid, 'layer': self.layer[eid], 'type': m.get('type'), 'name': (m.get('name') or '')[:90],
               'system': m.get('system'), 'level': m.get('levelKey'), 'center_m': [_r(v) for v in c],
               'size_m': [_r(b[3] - b[0]), _r(b[4] - b[1]), _r(b[5] - b[2])]}
        if m.get('system') in SYSTEM_CODES or (m.get('system') or '')[:11] in SYSTEM_CODES:
            out['system_meaning'] = SYSTEM_CODES.get(m.get('system')) or SYSTEM_CODES.get(m['system'][:11])
        for k in ('mark', 'location', 'size', 'flow', 'element_tag'):
            if m.get(k):
                out[k] = m[k]
        if m.get('fabrication', {}).get('Size'):
            out['size'] = m['fabrication']['Size']
        hint = self.service_hint(eid)
        if hint:
            out['service_hint'] = hint
        if ref is not None:
            out.update(self.relation(ref, b))
        if self.layer[eid] not in ix.VIEWER_LAYERS:
            out['note'] = 'interior ceiling slice: indexed for lookups, not drawn in the element viewer'
        return out

    # ---------- tools ----------
    def get_element(self, element_id):
        eid = str(element_id)
        if eid not in self.box:
            return {'error': f'unknown element id {eid}', 'evidence': 'design BIM'}
        m = self.meta[eid]
        keep = {k: v for k, v in m.items() if k not in ('_doc',) and not isinstance(v, (list, dict)) or k in ('fabrication', 'isFedBy')}
        s = self.summary(eid)
        return {'element': s, 'sidecar_fields': keep, 'bbox_m': self.box[eid],
                'sensors_on_element': [sid for sid, sn in self.sensors.items() if str(sn['anchor'].get('id')) == eid],
                'evidence': 'design BIM sidecar + geometry box; feeds/isFedBy are provisional associations (not circuited)'}

    def elements_near(self, element_id=None, point=None, radius_m=3.0, above_only=False, layers=None, type_contains=None, limit=MAX_LIST):
        ref, self_id = self.ref_box(element_id, point)
        radius_m = max(0.1, min(float(radius_m), 15.0))
        limit = max(1, min(int(limit), 60))
        layers = set(layers) if layers else None
        tc = type_contains.lower() if type_contains else None
        hits = []
        for eid in self._candidates(ref, radius_m):
            if eid == self_id:
                continue
            if layers and self.layer[eid] not in layers:
                continue
            m, b = self.meta[eid], self.box[eid]
            if tc and tc not in ' '.join(str(m.get(k, '')) for k in ('type', 'name', 'system', 'family')).lower():
                continue
            if above_only:
                if b[1] < ref[4] - 0.02:   # starts below the top of the reference
                    continue
                hx = max(0.0, ref[0] - b[3], b[0] - ref[3])
                hz = max(0.0, ref[2] - b[5], b[2] - ref[5])
                if math.hypot(hx, hz) > radius_m or b[1] - ref[4] > 4.0:
                    continue
                d = math.hypot(math.hypot(hx, hz), b[1] - ref[4])
            else:
                d = ix.box_gap(ref, b)
                if d > radius_m:
                    continue
            hits.append((d, eid))
        hits.sort()
        by_layer = Counter(self.layer[e] for _, e in hits)
        by_type = Counter(self.meta[e].get('type') for _, e in hits)
        return {'reference': {'element_id': self_id, 'point': point, 'bbox_m': ref},
                'query': {'radius_m': radius_m, 'above_only': bool(above_only), 'layers': sorted(layers) if layers else 'all'},
                'total_found': len(hits), 'counts_by_layer': dict(by_layer.most_common()),
                'counts_by_type': dict(by_type.most_common(12)),
                'elements': [self.summary(e, ref) for _, e in hits[:limit]],
                'evidence': 'geometry (bounding boxes, viewer frame, +Y up; gaps are box-to-box, not surface-exact)'}

    def room_of(self, element_id=None, point=None):
        ref, self_id = self.ref_box(element_id, point)
        c = ix.box_center(ref)
        lvl = (self.meta.get(self_id, {}).get('levelKey') if self_id else None) or level_of_y(ref[1])
        own = self.meta.get(self_id, {}).get('location') if self_id else None
        near = []
        for eid, loc in self._located:
            if self.meta[eid].get('levelKey') != lvl:
                continue
            ec = ix.box_center(self.box[eid])
            d = math.hypot(ec[0] - c[0], ec[2] - c[2])
            if d <= 12:
                near.append((d, eid, loc))
        near.sort()
        votes = Counter(loc for _, _, loc in near[:7])
        best = votes.most_common(1)[0] if votes else None
        ceilings = []
        for eid in self._candidates([c[0], c[1] - 6, c[2], c[0], c[1] + 6, c[2]], 0.0):
            if not self.layer[eid].startswith('ceilings'):
                continue
            b = self.box[eid]
            if b[0] <= c[0] <= b[3] and b[2] <= c[2] <= b[5]:
                ceilings.append(self.summary(eid, ref))
        conf = None
        if own:
            conf = 'recorded on the element (design BIM)'
        elif best:
            conf = 'medium' if best[1] >= 3 and near[0][0] < 5 else 'low'
        return {'level': lvl, 'room': own or (best[0] if best else None), 'confidence': conf,
                'basis': 'element location field' if own else 'inferred: most common room label among the nearest labelled equipment on the same level (Grimes has no room/space geometry in this repo)',
                'nearby_labelled_equipment': [{'id': e, 'location': loc, 'horizontal_m': _r(d)} for d, e, loc in near[:7]],
                'ceilings_at_this_xz': ceilings[:3],
                'evidence': 'inferred'}

    def find_elements(self, text=None, layer=None, level=None, element_id=None, point=None, radius_m=None, limit=MAX_LIST):
        words = [w for w in re.split(r'\s+', (text or '').lower()) if w]
        ref = None
        if element_id is not None or point is not None:
            ref, _ = self.ref_box(element_id, point)
        limit = max(1, min(int(limit), 60))
        pool = self._candidates(ref, float(radius_m)) if ref and radius_m else self.box.keys()
        hits = []
        for eid in pool:
            if layer and self.layer[eid] != layer:
                continue
            m = self.meta[eid]
            if level and m.get('levelKey') != level:
                continue
            hay = ' '.join(str(m.get(k, '')) for k in ('type', 'name', 'system', 'family', 'revit_type', 'location', 'mark', 'element_tag')).lower()
            hint = self.service_hint(eid)
            if hint:
                hay += ' ' + hint['service'].lower()
            if not all(w in hay for w in words):
                continue
            d = ix.box_gap(ref, self.box[eid]) if ref else 0.0
            if ref and radius_m and d > float(radius_m):
                continue
            hits.append((d, eid))
        hits.sort()
        return {'query': {'text': text, 'layer': layer, 'level': level, 'radius_m': radius_m}, 'total_found': len(hits),
                'elements': [self.summary(e, ref) for _, e in hits[:limit]],
                'evidence': 'design BIM names/types (+ inferred service hint)'}

    def connected_run(self, element_id, max_elements=150, tolerance_m=0.03):
        eid0 = str(element_id)
        if eid0 not in self.box:
            return {'error': f'unknown element id {eid0}'}
        layer = self.layer[eid0]
        max_elements = max(10, min(int(max_elements), 400))
        hops = {eid0: 0}
        parent = {eid0: None}
        q = deque([eid0])
        while q and len(hops) < max_elements:
            cur = q.popleft()
            b = self.box[cur]
            for nb in self._candidates(b, tolerance_m):
                if nb in hops or self.layer[nb] != layer:
                    continue
                if NOT_RUN.search(self.meta[nb].get('name', '') + ' ' + str(self.meta[nb].get('type', ''))):
                    continue
                if ix.box_gap(b, self.box[nb]) <= tolerance_m:
                    hops[nb] = hops[cur] + 1
                    parent[nb] = cur
                    q.append(nb)
                    if len(hops) >= max_elements:
                        break
        notable = []
        for e, h in hops.items():
            hint = self.service_hint(e)
            t = f"{self.meta[e].get('type', '')} {self.meta[e].get('name', '')}".lower()
            if 'coil kit' in t:   # accessory of the terminal unit it touches; the unit itself is listed
                continue
            if hint and any(k in hint['service'] for k in ('valve', 'terminal', 'air handling', 'heater', 'drain pan')) or 'ahu' in t or self.meta[e].get('type') in ('Terminal unit', 'Valve'):
                s = self.summary(e, self.box[eid0])
                s['hops'] = h
                path, p = [], e
                while p is not None and len(path) < 60:
                    path.append(p)
                    p = parent[p]
                s['path_ids'] = list(reversed(path))
                notable.append(s)
        notable.sort(key=lambda s: (s['hops'], s['id']))   # id breaks ties: the same answer on every run
        types = Counter(self.meta[e].get('type') for e in hops)
        return {'start': self.summary(eid0), 'layer': layer, 'elements_reached': len(hops), 'stopped_at_limit': len(hops) >= max_elements,
                'max_hops': max(hops.values()), 'types_in_run': dict(types.most_common(10)),
                'notable_on_run': notable[:12],
                'evidence': 'inferred: bounding boxes touching within tolerance on the same layer (hangers/annotation skipped). '
                            'Not a verified pipe/duct connection and no flow direction: crossing runs can be joined falsely.'}

    def _sensor_position(self, s):
        b = self.box.get(str(s['anchor'].get('id')))
        if not b:
            return None
        t = float(s['anchor'].get('t', 0.5))
        ext = [b[3] - b[0], b[4] - b[1], b[5] - b[2]]
        ax = ext.index(max(ext))
        c = list(ix.box_center(b))
        c[ax] = b[ax] + t * ext[ax]
        return [_r(v) for v in c]

    def list_sensors(self, element_id=None, point=None, radius_m=10.0):
        ref = None
        if element_id is not None or point is not None:
            ref, _ = self.ref_box(element_id, point)
        out = []
        for sid, s in self.sensors.items():
            pos = self._sensor_position(s)
            row = {'sensor_id': sid, 'label': s.get('label'), 'type': s.get('type'), 'quantity': s.get('quantity'), 'unit': s.get('unit'),
                   'anchor_element_id': str(s['anchor'].get('id')), 'anchor_layer': s['anchor'].get('layer'), 'position_m': pos,
                   'install_status': s.get('install_status'), 'data_source': s.get('data_source')}
            if ref is not None:
                if pos is None:
                    continue
                d = ix.box_gap(ref, pos + pos)
                if d > float(radius_m):
                    continue
                row['distance_m'] = _r(d)
            out.append(row)
        out.sort(key=lambda r: r.get('distance_m', 0))
        return {'sensors': out, 'evidence': 'demo-sim',
                'warning': 'DEMO sensors: none is installed in Grimes; positions on the anchor element are illustrative and every value is simulated.'}

    def sensor_readings(self, sensor_id, hours=24, now=None):
        s = self.sensors.get(str(sensor_id))
        if not s:
            return {'error': f'unknown sensor id {sensor_id}', 'known': sorted(self.sensors)}
        sim = _sensor_sim()
        hours = max(1, min(int(hours), 24 * 14))
        now_ms = int((now or datetime.now(timezone.utc)).timestamp() * 1000)
        step = max(int(s['sampling_interval_s']) * 1000, hours * 3600 * 1000 // 48)
        series = [sim.simulate(s, now_ms - k * step) for k in range(int(hours * 3600 * 1000 // step), -1, -1)]
        vals = [o['value'] for o in series if o.get('value') is not None]
        latest = series[-1]
        out = {'sensor_id': s['id'], 'label': s.get('label'), 'unit': s.get('unit'), 'anchor_element_id': str(s['anchor'].get('id')),
               'latest': latest, 'window_hours': hours, 'points': len(series),
               'stats': {'min': min(vals), 'max': max(vals), 'mean': _r(sum(vals) / len(vals), 3), 'first': vals[0], 'last': vals[-1],
                         'change': _r(vals[-1] - vals[0], 3)} if vals else None,
               'series': [[o['ts'], o['value']] for o in series[:: max(1, len(series) // 12)]],
               'registry_reading_text': (s.get('reading') or {}).get('value'),
               'alert_rule': s.get('alert_rule'),
               'simulated': True, 'install_status': s.get('install_status'), 'evidence': 'demo-sim',
               'warning': 'SIMULATED demo values (tools/sensor_sim.py math). Not a measurement; no sensor is installed.'}
        rule = s.get('alert_rule') or {}
        if latest.get('value') is not None and rule.get('kind') == 'threshold' and 'above' in rule:
            out['alert_active'] = latest['value'] > rule['above']
        return out


_SIM = None


def _sensor_sim():
    global _SIM
    if _SIM is None:
        sys.path.insert(0, str(ROOT / 'tools'))
        import sensor_sim  # noqa: E402
        _SIM = sensor_sim
    return _SIM


# ---------------- Claude tool schemas ----------------
_ID = {'type': 'string', 'description': 'Element id (GLB node name / sidecar key), e.g. "278123".'}
_PT = {'type': 'array', 'items': {'type': 'number'}, 'minItems': 3, 'maxItems': 3, 'description': '[x, y, z] metres in the viewer frame, +Y up.'}
LAYER_ENUM = sorted(ix.all_layers())

TOOL_SCHEMAS = [
    {'name': 'get_element', 'description': 'Full design-BIM record of one element: identity, type, CAD layer/system, level, design parameters, bounding box, demo sensors attached.',
     'input_schema': {'type': 'object', 'properties': {'element_id': _ID}, 'required': ['element_id'], 'additionalProperties': False}},
    {'name': 'elements_near', 'description': 'Elements within radius_m of an element or point, nearest first, with vertical relation (above/below), gaps and an inferred service hint (e.g. pressurized copper water, cast-iron drain, sprinkler, reheat coil). above_only=true returns only elements above the reference within radius_m horizontally (the plenum above a ceiling). Use layers to focus (water sources: plumbing, hydronic, fire, duct, equipment).',
     'input_schema': {'type': 'object', 'properties': {
         'element_id': _ID, 'point': _PT, 'radius_m': {'type': 'number', 'description': 'Default 3, max 15.'},
         'above_only': {'type': 'boolean'}, 'layers': {'type': 'array', 'items': {'type': 'string', 'enum': LAYER_ENUM}},
         'type_contains': {'type': 'string', 'description': 'Case-insensitive filter on type/name/system, e.g. "valve".'},
         'limit': {'type': 'integer'}}, 'additionalProperties': False}},
    {'name': 'room_of', 'description': 'Level and (inferred) room of an element or point, from the nearest equipment that carries a room label, plus any interior ceiling element covering that spot. Grimes has no room geometry here, so treat the room as an estimate.',
     'input_schema': {'type': 'object', 'properties': {'element_id': _ID, 'point': _PT}, 'additionalProperties': False}},
    {'name': 'find_elements', 'description': 'Search elements by words over type/name/system/family/room (all words must match), optionally filtered by layer and level (LOWER, MEZZ, L1, L2, L3, ROOF) and limited to radius_m around an element or point (sorted by distance). E.g. text="ball valve", layer="plumbing", level="L1".',
     'input_schema': {'type': 'object', 'properties': {
         'text': {'type': 'string'}, 'layer': {'type': 'string', 'enum': LAYER_ENUM}, 'level': {'type': 'string'},
         'element_id': _ID, 'point': _PT, 'radius_m': {'type': 'number'}, 'limit': {'type': 'integer'}}, 'additionalProperties': False}},
    {'name': 'connected_run', 'description': 'Follow geometrically touching elements of the same layer from a start element (breadth-first, hangers skipped) and report valves, terminal units, AHUs, heaters or drain pans found along the run with hop counts. Heuristic adjacency, NOT verified connectivity and no flow direction.',
     'input_schema': {'type': 'object', 'properties': {'element_id': _ID, 'max_elements': {'type': 'integer', 'description': 'Default 150, max 400.'}},
                      'required': ['element_id'], 'additionalProperties': False}},
    {'name': 'list_sensors', 'description': 'DEMO sensors (all simulated, none installed) with their anchor element and position; optionally only those within radius_m of an element or point.',
     'input_schema': {'type': 'object', 'properties': {'element_id': _ID, 'point': _PT, 'radius_m': {'type': 'number'}}, 'additionalProperties': False}},
    {'name': 'sensor_readings', 'description': 'Simulated readings of one DEMO sensor over the last N hours: latest value, min/max/mean/change, a short series and its alert rule. Always label these values as simulated demo data.',
     'input_schema': {'type': 'object', 'properties': {'sensor_id': {'type': 'string'}, 'hours': {'type': 'integer', 'description': 'Default 24, max 336.'}},
                      'required': ['sensor_id'], 'additionalProperties': False}},
]

_ALLOWED = {t['name']: set(t['input_schema']['properties']) for t in TOOL_SCHEMAS}
_REQUIRED = {t['name']: set(t['input_schema'].get('required', [])) for t in TOOL_SCHEMAS}


def run_tool(twin: Twin, name: str, args) -> dict:
    """Validate and run one tool. Never raises: errors come back as {'error': ...} for the model."""
    if name not in _ALLOWED:
        return {'error': f'unknown tool {name}'}
    if not isinstance(args, dict):
        return {'error': 'tool input must be an object'}
    extra = set(args) - _ALLOWED[name]
    missing = _REQUIRED[name] - set(args)
    if extra or missing:
        return {'error': f'bad arguments: unexpected {sorted(extra)} missing {sorted(missing)}'}
    try:
        return getattr(twin, name)(**args)
    except (KeyError, ValueError, TypeError) as e:
        return {'error': str(e).strip("'\"")}


ID_RX = re.compile(r'"(?:id|element_id|anchor_element_id)": "([^"]+)"|"path_ids": \[([^\]]*)\]')


def ids_in(result) -> set:
    """Element ids that appear in a tool result (used to verify answer citations)."""
    text = json.dumps(result)
    out = set()
    for a, b in ID_RX.findall(text):
        if a:
            out.add(a)
        if b:
            out.update(x.strip().strip('"') for x in b.split(',') if x.strip())
    return out
