"""Pipeline tests for scripts/build_baseline.py (and the epoch handling in towt_baseline.py)."""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


b = load("build_baseline_pipeline", "scripts/build_baseline.py")


def snap(kw, ts, spark=None, name="Grimes"):
    return {"buildings": {"grimes": {"name": name, "kw": kw, "timestamp": ts,
                                     "sparkline": spark or []}}}


class BaselineBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"
        (self.data / "archive").mkdir(parents=True)
        for k, v in dict(DATA=str(self.data),
                         CACHE_PATH=str(self.data / "energy_baseline_cache.json"),
                         OUT_PATH=str(self.data / "energy_baseline.json"),
                         EPOCH=datetime(2026, 1, 1)).items():
            p = mock.patch.object(b, k, v)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(b, "pacific_now", lambda: datetime(2026, 10, 14, 4, 0))
        p.start()
        self.addCleanup(p.stop)

    def write(self, rel, obj):
        (self.data / rel).write_text(json.dumps(obj))

    def cache(self):
        return json.loads((self.data / "energy_baseline_cache.json").read_text())

    def series(self):
        return {datetime(2026, 1, 1) + timedelta(hours=int(k)): v
                for k, v in self.cache()["series"]["grimes"].items()}


class SparklineTests(BaselineBase):
    def test_sparkline_is_not_ingested_as_hourly_history(self):
        # 24 spark values would have been smeared over 24 earlier hours (phase shift).
        self.write("campus_energy.json", snap(40.0, "2026-10-14 03:00:00", spark=list(range(1, 25))))
        b.main([])
        s = self.series()
        self.assertEqual(s, {datetime(2026, 10, 14, 3): 40.0})

    def test_history_overrides_nothing_and_is_hour_averaged(self):
        hist = {"grimes": [
            {"kw": 10.0, "ts": "2026-10-14 01:00:01", "t": "x"},
            {"kw": 20.0, "ts": "2026-10-14 01:15:01", "t": "x"},
            {"kw": 30.0, "ts": "2026-10-14 01:30:01", "t": "x"},
            {"kw": 40.0, "ts": "2026-10-14 01:45:01", "t": "x"},
            {"kw": 8.0, "ts": "2026-10-14 02:00:01", "t": "x"}]}
        self.write("campus_energy_history.json", hist)
        self.write("campus_energy.json", snap(8.0, "2026-10-14 02:00:01", spark=[999] * 24))
        b.main([])
        s = self.series()
        self.assertEqual(s[datetime(2026, 10, 14, 1)], 25.0)
        self.assertEqual(s[datetime(2026, 10, 14, 2)], 8.0)
        self.assertEqual(len(s), 2)

    def test_dst_ambiguous_hour_is_unknown(self):
        hist = {"grimes": [{"kw": 10.0, "ts": "2026-11-01 01:15:00", "t": "x"},
                           {"kw": 12.0, "ts": "2026-11-01 02:15:00", "t": "x"}]}
        self.write("campus_energy_history.json", hist)
        b.main([])
        self.assertEqual(list(self.series()), [datetime(2026, 11, 1, 2)])


class RebuildTests(BaselineBase):
    def seed_archive(self):
        self.write("archive/2026-10-12.json", snap(50.0, "2026-10-12 09:00:00", spark=[777] * 24))
        self.write("archive/2026-10-13.json", snap(60.0, "2026-10-13 10:45:00", spark=[777] * 24))
        self.write("archive/buildings_2026-10-13.json", {"meters": {}})

    def test_cache_without_version_is_rebuilt_from_archive_timestamps(self):
        self.seed_archive()
        # contaminated legacy cache (no version key): phase-shifted sparkline values
        self.write("energy_baseline_cache.json", {"series": {"grimes": {"6000": 777.0, "6001": 777.0}}})
        b.main([])
        c = self.cache()
        self.assertEqual(c["version"], b.CACHE_VERSION)
        self.assertEqual(self.series(), {datetime(2026, 10, 12, 9): 50.0,
                                         datetime(2026, 10, 13, 10): 60.0})

    def test_current_version_cache_is_kept_not_rebuilt(self):
        self.seed_archive()
        keep = {"6000": 31.0}
        self.write("energy_baseline_cache.json", {"version": b.CACHE_VERSION, "epoch": "2026-01-01",
                                                  "series": {"grimes": keep}})
        b.main([])
        self.assertEqual(self.cache()["series"]["grimes"], keep)

    def test_rebuild_flag_forces_rebuild(self):
        self.seed_archive()
        self.write("energy_baseline_cache.json", {"version": b.CACHE_VERSION, "epoch": "2026-01-01",
                                                  "series": {"grimes": {"6000": 31.0}}})
        b.main(["--rebuild"])
        self.assertNotIn("6000", self.cache()["series"]["grimes"])
        self.assertEqual(len(self.cache()["series"]["grimes"]), 2)


class EpochTests(BaselineBase):
    def test_epoch_derived_from_data_for_fresh_cache(self):
        with mock.patch.object(b, "pacific_now", lambda: datetime(2027, 3, 1)):
            self.write("campus_energy.json", snap(40.0, "2027-02-10 03:00:00"))
            b.main([])
        c = self.cache()
        self.assertEqual(c["epoch"], "2027-01-01")
        self.assertEqual(list(c["series"]["grimes"]), [str(40 * 24 + 3)])

    def test_existing_cache_epoch_is_preserved(self):
        self.write("energy_baseline_cache.json", {"version": b.CACHE_VERSION, "epoch": "2026-01-01",
                                                  "series": {"grimes": {"6000": 31.0}}})
        self.write("campus_energy.json", snap(40.0, "2026-10-14 03:00:00"))
        b.main([])
        self.assertEqual(self.cache()["epoch"], "2026-01-01")


class OutputTests(BaselineBase):
    def seed_daily(self, kw):
        for n in range(30):
            d = (datetime(2026, 9, 10) + timedelta(days=n)).strftime("%Y-%m-%d")
            self.write("archive/%s.json" % d, snap(kw + n % 3, d + " 09:00:00"))

    def test_recent24_is_last_24_hours_not_last_24_points(self):
        self.seed_daily(50.0)   # sparse: one point per day (archive-only history)
        hist = {"grimes": [{"kw": 40.0, "ts": "2026-10-14 03:00:01", "t": "x"}]}
        self.write("campus_energy_history.json", hist)
        self.write("campus_energy.json", snap(40.0, "2026-10-14 03:00:01"))
        b.main(["--backfill"])
        out = json.loads((self.data / "energy_baseline.json").read_text())
        rec = out["buildings"]["grimes"]["recent24"]
        self.assertEqual([r["ts"] for r in rec], ["2026-10-14 03:00"])

    def test_stale_current_reading_is_not_flagged_anomalous(self):
        self.seed_daily(50.0)
        self.write("campus_energy.json", snap(5000.0, "2026-10-13 09:00:00"))   # 19 h old vs pacific_now
        b.main(["--backfill"])
        cur = json.loads((self.data / "energy_baseline.json").read_text())["buildings"]["grimes"]["current"]
        self.assertFalse(cur["anomaly"])
        self.assertTrue(cur.get("stale"))


class TowtEpochTests(unittest.TestCase):
    def test_towt_reads_epoch_from_cache_not_hardcoded(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy unavailable")
        t = load("towt_pipeline", "scripts/towt_baseline.py")
        self.assertEqual(t.epoch_from({"epoch": "2027-01-01"}), datetime(2027, 1, 1))
        self.assertEqual(t.epoch_from({}), datetime(2026, 1, 1))      # legacy caches


if __name__ == "__main__":
    unittest.main()
