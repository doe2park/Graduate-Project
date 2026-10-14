"""Pipeline tests for scripts/build_mv.py (Grimes counter-based M&V)."""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("build_mv_pipeline", ROOT / "scripts" / "build_mv.py")
mv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mv)

KW = {"3": 10.0, "76": 20.0, "77": 30.0}    # constant draw -> 60 kW -> 1440 kWh / day
C0 = {"3": 1000.0, "76": 5000.0, "77": 9000.0}
T0 = datetime(2026, 10, 10, 0, 0)
FMT = "%Y-%m-%d %H:%M:%S"


def counters(t):
    h = (t - T0).total_seconds() / 3600
    return {m: C0[m] + KW[m] * h for m in KW}


def archive_doc(t, series=None):
    c = counters(t)
    meters = {}
    for i, m in enumerate(("3", "76", "77")):
        meters[m] = {"latest": {"timestamp": (t + timedelta(seconds=i % 2)).strftime(FMT),
                                "kwh_delivered": c[m]},
                     "timeseries_kw": (series or {}).get(m, [])}
    return {"meters": meters}


class MVBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"
        (self.data / "archive").mkdir(parents=True)
        p = mock.patch.object(mv, "DATA_DIR", str(self.data))
        p.start()
        self.addCleanup(p.stop)
        self.set_now(datetime(2026, 10, 14, 4, 0))

    def set_now(self, dt):
        p = mock.patch.object(mv, "pacific_now", lambda: dt)
        p.start()
        self.addCleanup(p.stop)

    def snap(self, t, utc_name=None, series=None):
        name = utc_name or t.strftime("%Y-%m-%d")
        (self.data / "archive" / ("buildings_%s.json" % name)).write_text(json.dumps(archive_doc(t, series)))

    def build(self):
        mv.main()
        return json.loads((self.data / "mv_grimes.json").read_text())


class DailyTests(MVBase):
    def test_constant_load_gives_exact_daily_energy_regardless_of_snapshot_hour(self):
        # snapshots at varying times of day (as the real archive: last run of each UTC day)
        for d, hh, mm in [(10, 14, 30), (11, 9, 0), (12, 16, 15), (13, 10, 45)]:
            self.snap(datetime(2026, 10, d, hh, mm))
        out = self.build()
        self.assertEqual([r["d"] for r in out["daily"]], ["2026-10-11", "2026-10-12"])
        for r in out["daily"]:
            self.assertEqual((r["t"], r["m3"], r["m76"], r["m77"]), (1440.0, 240.0, 480.0, 720.0))
        self.assertEqual(out["avg_daily_kwh"], 1440)

    def test_current_partial_pacific_day_is_excluded(self):
        # the real failure: 2026-10-14 06:03 UTC snapshot is 10-13 23:00 PT; today (10-14) just began.
        for d, hh in [(11, 9), (12, 10), (13, 10)]:
            self.snap(datetime(2026, 10, d, hh, 0))
        self.snap(datetime(2026, 10, 13, 23, 0), utc_name="2026-10-14")
        self.set_now(datetime(2026, 10, 14, 4, 0))
        out = self.build()
        self.assertEqual([r["d"] for r in out["daily"]], ["2026-10-12"])
        self.assertEqual(out["period"]["end"], "2026-10-12")
        self.assertTrue(all(r["t"] == 1440.0 for r in out["daily"]))

    def test_day_not_closed_by_a_snapshot_is_not_emitted(self):
        for d, hh in [(11, 9), (12, 10), (13, 10)]:
            self.snap(datetime(2026, 10, d, hh, 0))
        self.set_now(datetime(2026, 10, 13, 22, 0))
        out = self.build()
        self.assertNotIn("2026-10-13", [r["d"] for r in out["daily"]])

    def test_weekend_flag_and_date_use_pacific_not_utc_archive_name(self):
        # Sat 2026-10-17 20:00 PT is stored in the *UTC* 2026-10-18 file.
        self.snap(datetime(2026, 10, 16, 9, 0))
        self.snap(datetime(2026, 10, 17, 9, 0))
        self.snap(datetime(2026, 10, 18, 9, 0))
        self.snap(datetime(2026, 10, 17, 20, 0), utc_name="2026-10-18-late")
        self.set_now(datetime(2026, 10, 19, 12, 0))
        by_day = {r["d"]: r for r in self.build()["daily"]}
        self.assertIs(by_day["2026-10-17"]["we"], True)      # Saturday
        self.assertIs(by_day["2026-10-17"]["we"], True)
        self.assertEqual(by_day["2026-10-17"]["t"], 1440.0)
        self.assertNotIn("2026-10-18", by_day)               # Sunday not closed yet

    def test_gap_longer_than_three_days_is_not_interpolated(self):
        self.snap(datetime(2026, 10, 10, 9, 0))
        self.snap(datetime(2026, 10, 12, 9, 0))
        self.snap(datetime(2026, 10, 17, 9, 0))
        self.snap(datetime(2026, 10, 18, 9, 0))
        self.set_now(datetime(2026, 10, 19, 12, 0))
        days = [r["d"] for r in self.build()["daily"]]
        self.assertEqual(days, ["2026-10-11"])

    def test_counter_reset_is_skipped(self):
        self.snap(datetime(2026, 10, 10, 9, 0))
        self.snap(datetime(2026, 10, 11, 9, 0))
        doc = archive_doc(datetime(2026, 10, 12, 9, 0))
        for m in doc["meters"].values():
            m["latest"]["kwh_delivered"] = 12.0
        (self.data / "archive" / "buildings_2026-10-12.json").write_text(json.dumps(doc))
        self.snap(datetime(2026, 10, 13, 9, 0))
        days = [r["d"] for r in self.build()["daily"]]
        self.assertEqual(days, [])

    def test_output_schema_and_method_note(self):
        for d in (10, 11, 12):
            self.snap(datetime(2026, 10, d, 9, 0))
        out = self.build()
        for k in ("peak_measured_kw", "peak_measured_date", "peak_design_kw", "peak_baseline_kw",
                  "weekday_avg_kwh", "weekend_avg_kwh", "temp_fit", "avoided_vs_baseline", "_schema",
                  "_doc", "generated_at", "period", "avg_daily_kwh", "annualized_mwh",
                  "design_daily_kwh", "baseline_daily_kwh", "eui_actual", "eui_design", "daily", "monthly"):
            self.assertIn(k, out)
        self.assertEqual(out["_schema"], "mv-grimes/1")
        self.assertIn("method", out)
        self.assertEqual(set(out["daily"][0]) - {"pk", "tc"}, {"d", "t", "m3", "m76", "m77", "we"})


class PeakAndWeatherTests(MVBase):
    def test_peak_is_sum_of_meters_in_the_same_minute(self):
        series = {m: [{"t": "2026-10-11 12:15:0%d" % i, "v": v}, {"t": "2026-10-11 12:30:0%d" % i, "v": 1.0}]
                  for i, (m, v) in enumerate([("3", 5.0), ("76", 6.0), ("77", 7.0)])}
        for d in (10, 11, 12, 13):
            self.snap(datetime(2026, 10, d, 9, 0), series=series if d == 12 else None)
        out = self.build()
        row = {r["d"]: r for r in out["daily"]}["2026-10-11"]
        self.assertEqual(row["pk"], 18.0)
        self.assertEqual(out["peak_measured_kw"], 18.0)

    def test_weather_epoch_is_read_from_cache(self):
        for d in (10, 11, 12):
            self.snap(datetime(2026, 10, d, 9, 0))
        day0 = datetime(2026, 10, 11)
        ep = datetime(2025, 6, 1)
        base = int((day0 - ep).total_seconds() // 3600)
        hours = {str(base + h): 12.0 for h in range(24)}
        (self.data / "weather_cache.json").write_text(json.dumps({"epoch": "2025-06-01", "hours": hours}))
        out = self.build()
        self.assertEqual({r["d"]: r for r in out["daily"]}["2026-10-11"]["tc"], 12.0)


if __name__ == "__main__":
    unittest.main()
