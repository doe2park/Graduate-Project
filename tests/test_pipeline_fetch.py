"""Pipeline tests for bmo_fetch.py (Grimes building_data.json)."""
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("fetch_pipeline", ROOT / "bmo_fetch.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

FMT = "%Y-%m-%d %H:%M:%S"
# 2026-10-15 03:30 UTC == 2026-10-14 20:30 Pacific: UTC date != Pacific date
NOW_UTC = datetime(2026, 10, 15, 3, 30, tzinfo=timezone.utc)


class Resp:
    def __init__(self, status=200, text=""):
        self.status_code, self.text = status, text


def power_csv(rows):
    head = "time (US/Pacific)\terror\tkW total (kW)\tActive Power Total (kW)\tkWh del (kWh)"
    return "\n".join([head] + ["%s\t0\t%s\t%s\t%s" % (t, kw, kw, 1000 + i) for i, (t, kw) in enumerate(rows)]) + "\n"


class FakeSession:
    def __init__(self, meters=None, login=None, error=None):
        self.meters, self.login, self.error = meters or {}, login or Resp(200, "<html>ok</html>"), error
        self.calls, self.headers, self.auth = [], {}, None

    def get(self, url, params=None, timeout=None):
        if params is None:
            return self.login
        self.calls.append((url, dict(params), timeout))
        if self.error:
            raise self.error
        mid = params["MB"]
        if mid not in self.meters:
            return Resp(503, "unavailable")
        return Resp(200, self.meters[mid])


class FetchBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        for p in (mock.patch.object(m, "OUTPUT_DIR", d),
                  mock.patch.object(m, "OUTPUT_FILE", d / "building_data.json"),
                  mock.patch.object(m, "now_utc", lambda: NOW_UTC)):
            p.start()
            self.addCleanup(p.stop)
        self.d = d
        self.out = d / "building_data.json"

    def run_with(self, session, hours=24):
        with mock.patch("requests.Session", return_value=session):
            return m.run(hours=hours)


class FetchTests(FetchBase):
    def good_meters(self):
        rows = [("2026-10-14 19:45:00", 10), ("2026-10-14 20:00:00", 11), ("2026-10-14 20:15:00", 12)]
        return {"3": power_csv(rows), "76": power_csv(rows), "77": power_csv(rows)}

    def test_request_window_is_pacific_wall_time_with_timeout(self):
        s = FakeSession(self.good_meters())
        self.run_with(s, hours=24)
        _, params, timeout = s.calls[0]
        self.assertEqual(params["DATE_RANGE_ENDTIME"], "2026-10-14+20:30:00")
        self.assertEqual(params["DATE_RANGE_STARTTIME"], "2026-10-13+20:30:00")
        self.assertTrue(timeout)
        self.assertTrue(all(c[2] for c in s.calls))

    def test_stats_today_uses_pacific_date_not_utc(self):
        mixed = power_csv([("2026-10-14 08:00:00", 5), ("2026-10-14 20:00:00", 11), ("2026-10-15 00:00:00", 99)])
        s = FakeSession({"3": mixed, "76": mixed, "77": mixed})
        self.assertEqual(self.run_with(s), 0)
        d = json.loads(self.out.read_text())
        st = d["meters"]["3"]["stats_today"]["kw"]
        self.assertEqual(st["count"], 2)       # 10-14 rows only; not UTC '10-15'
        self.assertEqual(st["max"], 11)

    def test_get_today_readings_helper(self):
        rows = [{"timestamp": "2026-10-14 08:00:00"}, {"timestamp": "2026-10-15 00:00:00"}]
        self.assertEqual(m.get_today_readings(rows, today="2026-10-14"), rows[:1])

    def test_503_everywhere_does_not_overwrite(self):
        self.out.write_text('{"sentinel": 1}')
        self.assertNotEqual(self.run_with(FakeSession({})), 0)
        self.assertEqual(self.out.read_text(), '{"sentinel": 1}')

    def test_login_outage_does_not_overwrite(self):
        self.out.write_text('{"sentinel": 1}')
        self.assertNotEqual(self.run_with(FakeSession(login=Resp(503, "x"))), 0)
        self.assertEqual(self.out.read_text(), '{"sentinel": 1}')

    def test_timeout_does_not_overwrite_or_raise(self):
        import requests
        self.out.write_text('{"sentinel": 1}')
        self.assertNotEqual(self.run_with(FakeSession(error=requests.Timeout("t"))), 0)
        self.assertEqual(self.out.read_text(), '{"sentinel": 1}')

    def test_empty_csv_is_not_a_zero_reading(self):
        empty = power_csv([])
        self.out.write_text('{"sentinel": 1}')
        self.assertNotEqual(self.run_with(FakeSession({"3": empty, "76": empty, "77": empty})), 0)
        self.assertEqual(self.out.read_text(), '{"sentinel": 1}')

    def test_update_interval_is_observed_spacing(self):
        self.run_with(FakeSession(self.good_meters()))
        self.assertEqual(json.loads(self.out.read_text())["update_interval_min"], 15)

    def test_ambiguous_dst_rows_dropped(self):
        rows = power_csv([("2026-11-01 00:45:00", 1), ("2026-11-01 01:15:00", 2), ("2026-11-01 02:00:00", 3)])
        parsed = m.parse_power_csv(rows, "3")
        self.assertEqual([r["timestamp"] for r in parsed], ["2026-11-01 00:45:00", "2026-11-01 02:00:00"])


if __name__ == "__main__":
    unittest.main()
