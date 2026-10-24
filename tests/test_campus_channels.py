import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('campus',Path(__file__).parents[1]/'bmo_fetch_campus.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Response:
    status_code=200
    def __init__(self,text): self.text=text
class Session:
    def __init__(self,text): self.text=text
    def get(self,*a,**k): return Response(self.text)
class Channels(unittest.TestCase):
    def test_separate_demand_columns_no_instantaneous_or_sum(self):
        text='time (US/Pacific)\tElectric Main#1 (#...213) Demand (kW)\tElectric Main#2 (#...378) Demand (kW)\tElectric Main#1 (#...213) Instantaneous (kW)\n2026-10-12 18:45:00\t0\t42.5\t999\n'
        r=m.fetch_soda_electric_channels(Session(text))
        self.assertEqual([c['kw'] for c in r],[0,42.5])
        self.assertTrue(all(c['device_id']=='250' and c['unit']=='kW' for c in r))
        self.assertTrue(all(c['timestamp']=='2026-10-12 18:45:00' for c in r))
        self.assertNotIn('total_kw',r[0])
    def test_invalid_or_missing_demand_is_not_zero(self):
        r=m.fetch_soda_electric_channels(Session('time (US/Pacific)\tElectric Main#1 (#...213) Demand (kW)\n2026-10-12 18:45:00\tNaN\n'))
        self.assertTrue(all(c['kw'] is None for c in r))
        self.assertEqual(r[1]['status'],'column_missing')
    def test_legacy_3_76_77_preserve_zero_and_timestamp(self):
        for mid in ['3','76','77']:
            self.assertEqual(m.fetch_latest_kw(Session('time (US/Pacific)\tkW total (kW)\n2026-10-12 18:45:01\t0\n'),'mac','db',mid),(0,'2026-10-12 18:45:01'))
    def test_html_is_not_a_reading(self):
        self.assertTrue(all(c['kw'] is None for c in m.fetch_soda_electric_channels(Session('<html>login</html>'))))
    def test_last_valid_time_survives_missing_response(self):
        previous=[{'column':'Electric Main#1 (#...213) Demand (kW)','kw':0,'timestamp':'2026-10-12 18:45:00'}]
        r=m.fetch_soda_electric_channels(Session('<html>unavailable</html>'),previous)
        self.assertIsNone(r[0]['kw'])
        self.assertEqual(r[0]['last_observed_at'],'2026-10-12 18:45:00')
