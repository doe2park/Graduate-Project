"""Pipeline tests for bmo_fetch_campus.py: backfill, Pacific window, outage safety."""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("campus_pipeline", ROOT / "bmo_fetch_campus.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

FMT = "%Y-%m-%d %H:%M:%S"
BLDG = {"id": "grimes", "name": "Grimes", "mac": "AAA", "db": "DB", "meters": ["3", "76"]}


class Resp:
    def __init__(self, status=200, text=""):
        self.status_code, self.text = status, text


def csv_text(rows, col="kW total (kW)"):
    out = ["time (US/Pacific)\terror\t" + col]
    out += ["%s\t0\t%s" % (ts, kw) for ts, kw in rows]
    return "\n".join(out) + "\n"


class FakeSession:
    """Serves per-meter rows filtered by the requested [start, end] window."""

    def __init__(self, meters, login=None):
        self.meters = meters          # "AAA_3" -> [(ts, kw)]
        self.login = login or Resp(200, "<html>members</html>")
        self.calls = []
        self.auth = None
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        if params is None:
            return self.login
        self.calls.append((url, dict(params), timeout))
        key = url.rsplit("/", 1)[1][:-4]
        if key not in self.meters:
            return Resp(404, "<html>nope</html>")
        s = datetime.strptime(params["DATE_RANGE_STARTTIME"].replace("+", " "), FMT)
        e = datetime.strptime(params["DATE_RANGE_ENDTIME"].replace("+", " "), FMT)
        rows = [(t, v) for t, v in self.meters[key]
                if s <= datetime.strptime(t, FMT) <= e]
        return Resp(200, csv_text(rows))


NOW_UTC = datetime(2026, 10, 14, 10, 7, tzinfo=timezone.utc)  # = 03:07 Pacific (PDT)


class CampusBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name) / "data"
        patches = [
            mock.patch.object(m, "OUTPUT_DIR", d),
            mock.patch.object(m, "OUTPUT_FILE", d / "campus_energy.json"),
            mock.patch.object(m, "HISTORY_FILE", d / "campus_energy_history.json"),
            mock.patch.object(m, "BUILDINGS", [BLDG]),
            mock.patch.object(m, "FLOW_METERS", {}),
            mock.patch.object(m, "now_utc", lambda: NOW_UTC),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.d = d
        d.mkdir()

    def run_with(self, session):
        with mock.patch.object(m, "create_session", return_value=session):
            return m.run()

    def hist(self):
        return json.loads((self.d / "campus_energy_history.json").read_text())


def two_meter_rows(times, a=10.0, b=5.0):
    return {"AAA_3": [(t, a) for t in times], "AAA_76": [(t, b) for t in times]}


class BackfillTests(CampusBase):
    def test_first_run_requests_two_hours_in_pacific_wall_time(self):
        s = FakeSession(two_meter_rows(["2026-10-14 03:00:00"]))
        self.assertEqual(self.run_with(s), 0)
        p = s.calls[0][1]
        self.assertEqual(p["DATE_RANGE_ENDTIME"], "2026-10-14+03:07:00")
        self.assertEqual(p["DATE_RANGE_STARTTIME"], "2026-10-14+01:07:00")
        self.assertEqual(p["EXPORTTIMEZONE"], "US/Pacific")

    def test_window_starts_at_last_stored_timestamp(self):
        (self.d / "campus_energy_history.json").write_text(json.dumps(
            {"grimes": [{"kw": 15.0, "ts": "2026-10-14 00:30:01", "t": "07:31"}]}))
        s = FakeSession(two_meter_rows(["2026-10-14 03:00:00"]))
        self.run_with(s)
        self.assertEqual(s.calls[0][1]["DATE_RANGE_STARTTIME"], "2026-10-14+00:30:01")

    def test_window_bounded_to_24h(self):
        (self.d / "campus_energy_history.json").write_text(json.dumps(
            {"grimes": [{"kw": 15.0, "ts": "2026-10-10 00:30:01", "t": "07:31"}]}))
        s = FakeSession(two_meter_rows(["2026-10-14 03:00:00"]))
        self.run_with(s)
        self.assertEqual(s.calls[0][1]["DATE_RANGE_STARTTIME"], "2026-10-13+03:07:00")

    def test_all_interval_rows_merged_without_duplicates(self):
        times = ["2026-10-14 02:00:00", "2026-10-14 02:15:00", "2026-10-14 02:30:00",
                 "2026-10-14 02:45:00", "2026-10-14 03:00:00"]
        (self.d / "campus_energy_history.json").write_text(json.dumps(
            {"grimes": [{"kw": 15.0, "ts": "2026-10-14 02:00:00", "t": "09:01"}]}))
        s = FakeSession(two_meter_rows(times))
        self.run_with(s)
        h = self.hist()["grimes"]
        self.assertEqual([e["ts"] for e in h], times)
        self.assertEqual(h[-1]["kw"], 15.0)
        self.assertEqual(set(h[0]), {"kw", "ts", "t"})        # schema preserved
        # rerun is idempotent
        self.run_with(FakeSession(two_meter_rows(times)))
        self.assertEqual([e["ts"] for e in self.hist()["grimes"]], times)

    def test_history_is_time_windowed_not_count_capped(self):
        old = {"kw": 1.0, "ts": "2026-10-13 02:00:00", "t": "x"}     # 25 h old
        keep = {"kw": 2.0, "ts": "2026-10-13 04:00:00", "t": "x"}    # 23 h old
        (self.d / "campus_energy_history.json").write_text(json.dumps({"grimes": [old, keep]}))
        s = FakeSession(two_meter_rows(["2026-10-14 03:00:00"]))
        self.run_with(s)
        ts = [e["ts"] for e in self.hist()["grimes"]]
        self.assertNotIn(old["ts"], ts)
        self.assertIn(keep["ts"], ts)
        times = ["2026-10-13 %02d:%02d:00" % (h, mi) for h in range(4, 24) for mi in (0, 10, 20, 30, 40, 50)]
        (self.d / "campus_energy_history.json").write_text(json.dumps(
            {"grimes": [{"kw": 1.0, "ts": "2026-10-13 03:10:00", "t": "x"}]}))
        self.run_with(FakeSession(two_meter_rows(times + ["2026-10-14 03:00:00"])))
        self.assertGreater(len(self.hist()["grimes"]), 96)  # no MAX_HISTORY cap
        self.assertFalse(hasattr(m, "MAX_HISTORY"))

    def test_incomplete_slot_is_not_stored_as_partial_sum(self):
        rows = two_meter_rows(["2026-10-14 02:45:00"])
        rows["AAA_3"].append(("2026-10-14 03:00:00", 10.0))   # meter 76 lags this slot
        self.run_with(FakeSession(rows))
        h = self.hist()["grimes"]
        self.assertEqual([e["ts"] for e in h], ["2026-10-14 02:45:00"])
        self.assertEqual(h[0]["kw"], 15.0)

    def test_dst_ambiguous_rows_are_unknown_not_stored(self):
        now = datetime(2026, 11, 1, 10, 30, tzinfo=timezone.utc)  # 02:30 PST
        rows = two_meter_rows(["2026-11-01 00:45:00", "2026-11-01 01:15:00", "2026-11-01 02:00:00"])
        with mock.patch.object(m, "now_utc", lambda: now):
            self.run_with(FakeSession(rows))
        ts = [e["ts"] for e in self.hist()["grimes"]]
        self.assertEqual(ts, ["2026-11-01 00:45:00", "2026-11-01 02:00:00"])

    def test_update_interval_reflects_observed_spacing(self):
        times = ["2026-10-14 02:00:00", "2026-10-14 02:15:00", "2026-10-14 02:30:00", "2026-10-14 02:45:00"]
        self.run_with(FakeSession(two_meter_rows(times)))
        out = json.loads((self.d / "campus_energy.json").read_text())
        self.assertEqual(out["update_interval_min"], 15)
        times = ["2026-10-14 02:00:00", "2026-10-14 02:30:00", "2026-10-14 03:00:00"]
        (self.d / "campus_energy_history.json").write_text("{}")
        self.run_with(FakeSession(two_meter_rows(times)))
        out = json.loads((self.d / "campus_energy.json").read_text())
        self.assertEqual(out["update_interval_min"], 30)

    def test_live_reading_is_latest_complete_row(self):
        times = ["2026-10-14 02:00:00", "2026-10-14 02:15:00"]
        self.run_with(FakeSession(two_meter_rows(times)))
        out = json.loads((self.d / "campus_energy.json").read_text())
        b = out["buildings"]["grimes"]
        self.assertEqual((b["kw"], b["timestamp"], b["status"]), (15.0, "2026-10-14 02:15:00", "online"))


class PacificDayFileTests(CampusBase):
    """data/history/<Pacific date>.json keeps every observation past the 24 h history."""

    def day(self, date):
        return json.loads((self.d / "history" / f"{date}.json").read_text())

    def test_rows_are_filed_by_pacific_wall_date_not_utc_run_date(self):
        # 22:00 PDT on Oct 13 is already Oct 14 in UTC; it belongs to the Oct 13 file.
        (self.d / "campus_energy_history.json").write_text(json.dumps(
            {"grimes": [{"kw": 12.0, "ts": "2026-10-13 22:00:00", "t": "05:00"}]}))
        self.run_with(FakeSession(two_meter_rows(["2026-10-14 03:00:00"])))
        self.assertEqual(self.day("2026-10-13")["buildings"]["grimes"], [["2026-10-13 22:00:00", 12.0]])
        self.assertEqual(self.day("2026-10-14")["buildings"]["grimes"], [["2026-10-14 03:00:00", 15.0]])
        self.assertEqual(self.day("2026-10-14")["timezone"], "America/Los_Angeles")
        index = json.loads((self.d / "history" / "index.json").read_text())
        self.assertEqual(index["dates"], ["2026-10-13", "2026-10-14"])
        self.assertEqual(index["timezone"], "America/Los_Angeles")

    def test_rows_older_than_24h_history_are_kept_and_reruns_do_not_duplicate(self):
        (self.d / "history").mkdir()
        (self.d / "history" / "2026-10-10.json").write_text(json.dumps(
            {"date": "2026-10-10", "timezone": "America/Los_Angeles",
             "buildings": {"grimes": [["2026-10-10 12:00:00", 9.0]]}}))
        times = ["2026-10-14 02:45:00", "2026-10-14 03:00:00"]
        self.run_with(FakeSession(two_meter_rows(times)))
        self.run_with(FakeSession(two_meter_rows(times)))
        self.assertEqual(self.day("2026-10-10")["buildings"]["grimes"], [["2026-10-10 12:00:00", 9.0]])
        self.assertEqual([r[0] for r in self.day("2026-10-14")["buildings"]["grimes"]], times)
        index = json.loads((self.d / "history" / "index.json").read_text())
        self.assertEqual(index["dates"], ["2026-10-10", "2026-10-14"])

    def test_stale_rows_of_removed_buildings_are_not_filed(self):
        # A building dropped from BUILDINGS keeps old rows in the history file; they must
        # not create old date files that would misstate where retained history starts.
        (self.d / "campus_energy_history.json").write_text(json.dumps(
            {"stanley": [{"kw": 5.0, "ts": "2026-07-05 14:45:00", "t": "x"}]}))
        self.run_with(FakeSession(two_meter_rows(["2026-10-14 03:00:00"])))
        index = json.loads((self.d / "history" / "index.json").read_text())
        self.assertEqual(index["dates"], ["2026-10-14"])
        self.assertNotIn("stanley", self.day("2026-10-14")["buildings"])

    def test_ambiguous_fall_back_hour_is_not_filed(self):
        now = datetime(2026, 11, 1, 10, 30, tzinfo=timezone.utc)  # 02:30 PST
        rows = two_meter_rows(["2026-11-01 00:45:00", "2026-11-01 01:15:00", "2026-11-01 02:00:00"])
        with mock.patch.object(m, "now_utc", lambda: now):
            self.run_with(FakeSession(rows))
        self.assertEqual([r[0] for r in self.day("2026-11-01")["buildings"]["grimes"]],
                         ["2026-11-01 00:45:00", "2026-11-01 02:00:00"])


class OutageTests(CampusBase):
    def seed(self):
        for name in ("campus_energy.json",):
            (self.d / name).write_text('{"sentinel": 1}')
        (self.d / "daily").mkdir()
        (self.d / "daily" / "2026-10-14.json").write_text('{"sentinel": 2}')

    def assert_untouched(self):
        self.assertEqual((self.d / "campus_energy.json").read_text(), '{"sentinel": 1}')
        self.assertEqual((self.d / "daily" / "2026-10-14.json").read_text(), '{"sentinel": 2}')
        self.assertFalse((self.d / "campus_energy_history.json").exists())
        self.assertFalse((self.d / "history").exists())

    def test_login_503_aborts_without_writing(self):
        self.seed()
        s = FakeSession({}, login=Resp(503, "Service Unavailable"))
        with mock.patch("requests.Session", return_value=s):
            rc = m.run()
        self.assertNotEqual(rc, 0)
        self.assert_untouched()

    def test_maintenance_page_aborts(self):
        self.seed()
        s = FakeSession({}, login=Resp(200, "<html><h1>Site is down for scheduled maintenance</h1></html>"))
        with mock.patch("requests.Session", return_value=s):
            self.assertNotEqual(m.run(), 0)
        self.assert_untouched()

    def test_login_timeout_aborts(self):
        import requests
        self.seed()
        s = FakeSession({})
        s.get = mock.Mock(side_effect=requests.Timeout("slow"))
        with mock.patch("requests.Session", return_value=s):
            self.assertNotEqual(m.run(), 0)
        self.assert_untouched()

    def test_401_still_rejected(self):
        self.seed()
        s = FakeSession({}, login=Resp(401, ""))
        with mock.patch("requests.Session", return_value=s):
            self.assertNotEqual(m.run(), 0)
        self.assert_untouched()

    def test_zero_online_after_fetch_aborts_without_writing(self):
        self.seed()
        rc = self.run_with(FakeSession({}))      # every meter 404 / no rows
        self.assertNotEqual(rc, 0)
        self.assert_untouched()

    def test_all_meters_5xx_aborts(self):
        self.seed()
        s = FakeSession({})
        s.get = mock.Mock(side_effect=lambda url, params=None, timeout=None:
                          Resp(200, "<html>ok</html>") if params is None else Resp(502, "bad gateway"))
        self.assertNotEqual(self.run_with(s), 0)
        self.assert_untouched()

    def test_requests_have_timeout(self):
        s = FakeSession(two_meter_rows(["2026-10-14 03:00:00"]))
        self.run_with(s)
        self.assertTrue(all(c[2] for c in s.calls))


if __name__ == "__main__":
    unittest.main()
