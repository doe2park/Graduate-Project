#!/usr/bin/env python3
"""Validate buildings/grimes/as-built-adjustments.json and report design-vs-installed statistics.

Mirrors the schema in twin/as-built.js (tests/as-built.test.cjs, tests/test_check_as_built.py).
Each adjustment must name an element that exists in its layer's identity sidecar (*.elements.json;
key = GLB node name). Statistics are grouped by the sidecar's `system` (authoritative), falling back to
the layer. Every value is a MANUAL visual match by the owner against a captured photo/mesh: status
'manual-unsurveyed'. Report it as "manual, not surveyed", never as surveyed as-built accuracy.

Usage:
  python3 scripts/check_as_built.py                       # validate + summary table
  python3 scripts/check_as_built.py --json                # machine-readable report
  python3 scripts/check_as_built.py --file other.json --root buildings/grimes
Exit status 1 when the document is invalid.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

SCHEMA = "as-built-adjustments/1"
FRAME = "bim-pane-world-y-up-m"
STATUS = "manual-unsurveyed"
MAX_OFFSET_M = 1.0
MAX_YAW_DEG = 45.0
SCAN_MODES = ("photo", "mesh", "splat")
# layer key -> identity sidecar (same table as LAYERS in scan-bim.html / grimes-bim-viewer.html)
LAYER_SIDECARS = {
    "equipment": "elements.json",
    "fixtures": "fixtures.elements.json",
    "lighting": "lighting.elements.json",
    "lifesafety": "lifesafety.elements.json",
    "structural": "structural.elements.json",
    "conduit": "conduit.elements.json",
    "duct": "duct.elements.json",
    "hydronic": "hydronic.elements.json",
    "plumbing": "plumbing.elements.json",
    "fire": "fire.elements.json",
}
ROOT = Path(__file__).resolve().parents[1]


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _vec3(v) -> bool:
    return isinstance(v, list) and len(v) == 3 and all(_finite(x) for x in v)


def _iso_date(s) -> bool:
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d\d-\d\d", s):
        return False
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _iso_datetime(s) -> bool:
    if not isinstance(s, str) or not re.match(r"\d{4}-\d\d-\d\dT", s):
        return False
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_adjustment(a) -> list[str]:
    e: list[str] = []
    if not isinstance(a, dict):
        return ["adjustment must be an object"]
    el = a.get("element")
    if not isinstance(el, dict):
        e.append("element missing")
    else:
        if not isinstance(el.get("id"), str) or not el["id"].strip() or len(el["id"]) > 80:
            e.append("element.id must be a non-empty string")
        if el.get("layer") not in LAYER_SIDECARS:
            e.append("element.layer must be one of " + ", ".join(LAYER_SIDECARS))
        for k in ("name", "type", "system"):
            if el.get(k) is not None and not isinstance(el[k], str):
                e.append(f"element.{k} must be a string")
    t = a.get("translation")
    if not _vec3(t):
        e.append("translation must be three finite numbers (m)")
    elif math.hypot(*t) > MAX_OFFSET_M:
        e.append(f"translation exceeds {MAX_OFFSET_M} m")
    yaw = a.get("yawDegrees")
    if not _finite(yaw):
        e.append("yawDegrees must be a finite number")
    elif abs(yaw) > MAX_YAW_DEG:
        e.append(f"yawDegrees exceeds ±{MAX_YAW_DEG:g}")
    if a.get("pivot") is not None and not _vec3(a["pivot"]):
        e.append("pivot must be three finite numbers when present")
    ev = a.get("evidence")
    if not isinstance(ev, dict):
        e.append("evidence missing")
    else:
        if not _iso_date(ev.get("captureDate")):
            e.append("evidence.captureDate must be YYYY-MM-DD")
        if ev.get("scanMode") not in SCAN_MODES:
            e.append("evidence.scanMode must be photo, mesh or splat")
        si = ev.get("stationIndex")
        if si is not None and not (isinstance(si, int) and not isinstance(si, bool) and si >= 0):
            e.append("evidence.stationIndex must be a non-negative integer or null")
        if ev.get("stationLabel") is not None and not isinstance(ev["stationLabel"], str):
            e.append("evidence.stationLabel must be a string or null")
    if not isinstance(a.get("author"), str) or not re.fullmatch(r"[A-Za-z]{2,4}", a["author"]):
        e.append("author must be 2-4 letter initials")
    if not _iso_datetime(a.get("timestamp")):
        e.append("timestamp must be an ISO date-time")
    note = a.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > 500):
        e.append("note must be a string of at most 500 characters")
    if a.get("status") != STATUS:
        e.append(f"status must be '{STATUS}'")
    return e


def load_sidecars(root: Path, layers) -> dict[str, dict]:
    out = {}
    for layer in sorted(set(layers)):
        path = root / LAYER_SIDECARS[layer]
        out[layer] = json.loads(path.read_text(encoding="utf-8")).get("elements", {})
    return out


def check(doc, root: Path | None = None, sidecars: dict | None = None) -> dict:
    """Return {ok, errors, warnings, count, stats}. `sidecars` (layer -> elements) overrides reading from root."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(doc, dict):
        return {"ok": False, "errors": ["document must be a JSON object"], "warnings": [], "count": 0, "stats": {}}
    if doc.get("_schema") != SCHEMA:
        errors.append(f"_schema must be '{SCHEMA}'")
    if doc.get("frame") != FRAME:
        errors.append(f"frame must be '{FRAME}'")
    adjustments = doc.get("adjustments")
    if not isinstance(adjustments, list):
        return {"ok": False, "errors": errors + ["adjustments must be an array"], "warnings": [], "count": 0, "stats": {}}
    valid = []
    for i, a in enumerate(adjustments):
        e = validate_adjustment(a)
        if not e:
            valid.append((i, a))
        errors.extend(f"adjustments[{i}]: {m}" for m in e)
    if sidecars is None:
        sidecars = load_sidecars(root or ROOT / "buildings" / "grimes", [a["element"]["layer"] for _, a in valid])
    seen = set()
    groups: dict[str, list] = {}
    for i, a in valid:
        layer, eid = a["element"]["layer"], a["element"]["id"]
        key = f"{layer}:{eid}"
        if key in seen:
            errors.append(f"adjustments[{i}]: duplicate element {key}")
            continue
        seen.add(key)
        info = sidecars.get(layer, {}).get(eid)
        if info is None:
            errors.append(f"adjustments[{i}]: element {key} is not in the {layer} sidecar ({LAYER_SIDECARS[layer]})")
            continue
        for k in ("name", "type", "system"):
            if a["element"].get(k) is not None and info.get(k) is not None and a["element"][k] != info[k]:
                warnings.append(f"adjustments[{i}]: element.{k} '{a['element'][k]}' differs from sidecar '{info[k]}' (sidecar wins)")
        groups.setdefault(info.get("system") or layer, []).append(a)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "count": sum(len(v) for v in groups.values()),
            "stats": stats(groups), "status": STATUS}


def stats(groups: dict[str, list]) -> dict:
    out = {}
    for name, items in sorted(groups.items()):
        d = [math.hypot(*a["translation"]) for a in items]
        h = [math.hypot(a["translation"][0], a["translation"][2]) for a in items]
        v = [a["translation"][1] for a in items]
        yaw = [abs(a.get("yawDegrees") or 0) for a in items]
        n = len(items)
        out[name] = {"n": n, "meanOffsetM": round(sum(d) / n, 4), "maxOffsetM": round(max(d), 4),
                     "meanHorizontalM": round(sum(h) / n, 4), "meanVerticalM": round(sum(v) / n, 4),
                     "meanAbsYawDeg": round(sum(yaw) / n, 3)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", type=Path, default=ROOT / "buildings" / "grimes" / "as-built-adjustments.json")
    ap.add_argument("--root", type=Path, default=ROOT / "buildings" / "grimes", help="folder holding the *.elements.json sidecars")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        doc = json.loads(args.file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {args.file}: {exc}", file=sys.stderr)
        return 1
    report = check(doc, args.root)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{args.file}: {'OK' if report['ok'] else 'INVALID'} · {report['count']} adjustment(s) · status {STATUS} (manual, not surveyed)")
        for m in report["errors"]:
            print("  error:", m)
        for m in report["warnings"]:
            print("  warning:", m)
        if report["stats"]:
            print(f"  {'system':<24}{'n':>4}{'mean |d| m':>12}{'max |d| m':>11}{'mean horiz':>12}{'mean vert':>11}{'mean |yaw|':>12}")
            for name, s in report["stats"].items():
                print(f"  {name[:24]:<24}{s['n']:>4}{s['meanOffsetM']:>12.3f}{s['maxOffsetM']:>11.3f}{s['meanHorizontalM']:>12.3f}{s['meanVerticalM']:>11.3f}{s['meanAbsYawDeg']:>11.2f}°")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
