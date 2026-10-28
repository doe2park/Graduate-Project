"""Per-floor interior groups (interior/manifest.json `levels`, scripts/prepare_interior_levels.py).

Always: every listed file exists, sizes and SHA-256 match, sidecar keys = GLB node names, Draco payload sets match the
recorded digest, the legacy Level 1 fields are unchanged and still describe the Level 1 files.
When the read-only source (Grimes_360_Pilot/interior/source.*) is present: its hashes match the provenance, every node
name is a source element id, and every output Draco payload is byte-identical to a source payload (no re-encode).
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from extract_layer import read_glb  # noqa: E402
import prepare_interior_levels as pil  # noqa: E402

MANIFEST = json.loads((ROOT / "interior/manifest.json").read_text())
SOURCE = pil.DEFAULT_SOURCE
KEYS = ("furniture", "enclosure", "floors", "ceilings")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def entries():
    for level, spec in MANIFEST["levels"].items():
        for key, e in spec["groups"].items():
            yield level, key, e


class ManifestShapeTests(unittest.TestCase):
    def test_legacy_fields_unchanged(self):
        self.assertEqual(MANIFEST["schema"], "grimes-interior/1")
        self.assertEqual(MANIFEST["sliceY"], [4.3, 10.3])
        self.assertEqual(MANIFEST["frame"], {"rotationYDegrees": 180, "translation": [-35.28, -97.16, 28.6]})
        self.assertIn("not surveyed as-built", MANIFEST["scope"])
        for key in KEYS:
            self.assertEqual(MANIFEST["groups"][key]["glb"], f"interior/{key}-l1.glb")
        # legacy group entries still carry exactly their original fields
        self.assertEqual(set(MANIFEST["groups"]["furniture"]),
                         {"glb", "json", "elements", "fragments", "bytes", "categories", "verifiedDracoPayloads"})

    def test_levels_listed_with_honest_labels(self):
        self.assertEqual(sorted(MANIFEST["levels"]), ["L1", "L2", "L3"])
        self.assertEqual(MANIFEST["provenance"]["label"], "source design geometry, not surveyed as-built")
        for level, spec in MANIFEST["levels"].items():
            self.assertEqual(sorted(spec["groups"]), sorted(KEYS))
            self.assertIn("not surveyed as-built", spec["scope"])
            lo, hi = spec["sliceY"]
            self.assertLess(lo, spec["slabTopY"])
            self.assertLess(spec["slabTopY"], hi)
        self.assertEqual(MANIFEST["levels"]["L1"]["sliceY"], MANIFEST["sliceY"])
        # slices ascend floor by floor
        y = [MANIFEST["levels"][k]["sliceY"] for k in ("L1", "L2", "L3")]
        self.assertTrue(y[0][0] < y[1][0] < y[2][0] and y[0][1] < y[1][1] < y[2][1])

    def test_level1_block_points_at_the_legacy_files(self):
        for key in KEYS:
            legacy, lv = MANIFEST["groups"][key], MANIFEST["levels"]["L1"]["groups"][key]
            for k in legacy:
                self.assertEqual(legacy[k], lv[k], (key, k))


class FileIntegrityTests(unittest.TestCase):
    def test_files_exist_and_hashes_match(self):
        for level, key, e in entries():
            glb, js = ROOT / e["glb"], ROOT / e["json"]
            self.assertTrue(glb.is_file() and js.is_file(), (level, key))
            self.assertEqual(glb.stat().st_size, e["bytes"])
            self.assertEqual(sha(glb), e["glbSha256"], (level, key))
            self.assertEqual(sha(js), e["jsonSha256"], (level, key))
            self.assertEqual(e["glb"], f"interior/{key}-{level.lower()}.glb")

    def test_node_names_are_sidecar_keys_and_draco_payloads_match(self):
        for level, key, e in entries():
            g, b = read_glb(ROOT / e["glb"])
            side = json.loads((ROOT / e["json"]).read_text())["elements"]
            leaves = g["nodes"][1:]
            self.assertEqual(len(leaves), e["fragments"])
            self.assertEqual({n["name"] for n in leaves}, set(side), (level, key))
            self.assertEqual(len(side), e["elements"])
            self.assertTrue(all(v["levelKey"] == level and v["levelFrom"] == "geometry-slice" and v["type"] == key
                                for v in side.values()))
            cats = {}
            for v in side.values():
                cats[v["category"]] = cats.get(v["category"], 0) + 1
            self.assertEqual(cats, e["categories"])
            self.assertTrue(set(cats) <= set(pil.GROUPS[key]))
            payloads = pil.draco_payloads(g, b)
            self.assertEqual(len(payloads), e["verifiedDracoPayloads"])
            self.assertEqual(pil.payload_set_digest(payloads), e["dracoPayloadSetSha256"], (level, key))
            self.assertGreater(len(payloads), 0)


@unittest.skipUnless((SOURCE / "source.glb").is_file(), "read-only Grimes_360_Pilot source not present")
class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g, cls.b = read_glb(SOURCE / "source.glb")
        cls.meta = json.loads((SOURCE / "source.elements.json").read_text())["elements"]
        cls.payloads = pil.draco_payloads(cls.g, cls.b)
        cls.views = {hashlib.sha256(cls.b[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]]).digest()
                     for v in cls.g["bufferViews"]}

    def test_provenance_hashes(self):
        src = MANIFEST["provenance"]["source"]
        self.assertEqual(sha(SOURCE / "source.glb"), src["glbSha256"])
        self.assertEqual(sha(SOURCE / "source.elements.json"), src["elementsSha256"])
        self.assertEqual(len(self.meta), src["elements"])

    def test_names_subset_of_source_and_no_draco_reencode(self):
        for level, key, e in entries():
            g, b = read_glb(ROOT / e["glb"])
            names = {n["name"] for n in g["nodes"][1:]}
            self.assertTrue(names <= set(self.meta), (level, key))
            self.assertTrue(pil.draco_payloads(g, b) <= self.payloads, (level, key))
            # every bufferView (Draco or raw) is a byte-verbatim copy of a source bufferView
            src_views = self.views
            for v in g["bufferViews"]:
                s = v.get("byteOffset", 0)
                self.assertIn(hashlib.sha256(b[s:s + v["byteLength"]]).digest(), src_views, (level, key))
            side = json.loads((ROOT / e["json"]).read_text())["elements"]
            derived = {"levelKey", "levelFrom", "type", "feedTier"}
            for i, v in side.items():  # sidecar = source record with the four derived fields set (as for L1)
                self.assertEqual({k: v[k] for k in self.meta[i] if k not in derived},
                                 {k: x for k, x in self.meta[i].items() if k not in derived})


if __name__ == "__main__":
    unittest.main()
