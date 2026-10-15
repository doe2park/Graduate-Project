"""scripts/check_as_built.py: schema parity with twin/as-built.js, sidecar membership and statistics."""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_as_built as cab  # noqa: E402


def adj(**over):
    a = {"element": {"id": "171361", "layer": "lighting"}, "translation": [0.12, 0, -0.04], "yawDegrees": 1,
         "evidence": {"captureDate": "2026-09-17", "scanMode": "photo", "stationIndex": 56, "stationLabel": "57/100"},
         "author": "YC", "timestamp": "2026-10-14T18:00:00.000Z", "note": "", "status": "manual-unsurveyed"}
    a.update(over)
    return a


def doc(items):
    return {"_schema": cab.SCHEMA, "frame": cab.FRAME, "adjustments": items}


SIDECARS = {"lighting": {"171361": {"name": "_TEE_Linear Fixture", "system": "Lighting"}, "2": {"system": "Lighting"}},
            "duct": {"9": {"system": "M-HVAC-DUCT"}}}


class CheckAsBuilt(unittest.TestCase):
    def test_shipped_file_is_valid_and_empty(self):
        report = cab.check(json.loads((ROOT / "buildings/grimes/as-built-adjustments.json").read_text()))
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["count"], 0)

    def test_real_sidecar_membership(self):
        self.assertTrue(cab.check(doc([adj()]))["ok"])  # 171361 exists in lighting.elements.json
        bad = cab.check(doc([adj(element={"id": "no-such-id", "layer": "lighting"})]))
        self.assertFalse(bad["ok"])
        self.assertIn("not in the lighting sidecar", " ".join(bad["errors"]))

    def test_schema_errors_match_js_rules(self):
        cases = [({"status": "surveyed"}, "status"), ({"author": "Yoonsung"}, "initials"), ({"translation": [2, 0, 0]}, "exceeds"),
                 ({"yawDegrees": 90}, "yawDegrees"), ({"timestamp": "yesterday"}, "timestamp"), ({"pivot": [1, 2]}, "pivot"),
                 ({"evidence": {"captureDate": "2026-13-01", "scanMode": "photo"}}, "captureDate"),
                 ({"evidence": {"captureDate": "2026-09-17", "scanMode": "lidar"}}, "scanMode"),
                 ({"element": {"id": "1", "layer": "architecture"}}, "layer"), ({"translation": [True, 0, 0]}, "translation")]
        for over, word in cases:
            r = cab.check(doc([adj(**over)]), sidecars=SIDECARS)
            self.assertFalse(r["ok"], over)
            self.assertIn(word, " ".join(r["errors"]), over)
        dup = cab.check(doc([adj(), adj()]), sidecars=SIDECARS)
        self.assertIn("duplicate element lighting:171361", " ".join(dup["errors"]))
        self.assertFalse(cab.check({"_schema": "x", "frame": cab.FRAME, "adjustments": []})["ok"])

    def test_statistics_grouped_by_sidecar_system(self):
        r = cab.check(doc([adj(translation=[0.3, 0, 0.4]), adj(element={"id": "2", "layer": "lighting", "system": "Wrong"}, translation=[0, 0.1, 0], yawDegrees=-2),
                           adj(element={"id": "9", "layer": "duct"}, translation=[0.1, 0, 0], yawDegrees=0)]), sidecars=SIDECARS)
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(r["stats"]["Lighting"], {"n": 2, "meanOffsetM": 0.3, "maxOffsetM": 0.5, "meanHorizontalM": 0.25, "meanVerticalM": 0.05, "meanAbsYawDeg": 1.5})
        self.assertEqual(r["stats"]["M-HVAC-DUCT"]["n"], 1)
        self.assertIn("differs from sidecar", " ".join(r["warnings"]))

    def test_cli_exit_status_and_output(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.json"
            p.write_text(json.dumps(doc([adj()])))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cab.main(["--file", str(p)]), 0)
            self.assertIn("manual, not surveyed", out.getvalue())
            self.assertIn("Lighting", out.getvalue())
            p.write_text(json.dumps(doc([adj(status="surveyed")])))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cab.main(["--file", str(p), "--json"]), 1)


if __name__ == "__main__":
    unittest.main()
