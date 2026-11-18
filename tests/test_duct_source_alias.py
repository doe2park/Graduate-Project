import unittest
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from extract_mep_layer import SRC, level_of

class DuctAliases(unittest.TestCase):
    def test_actual_long_export_alias_is_a_duct_source(self):
        for name in ('MD02.dwg', 'UCBBE-FMB-MD_adammTJDRY-3D View - MD02 EXPORT.dwg'):
            self.assertIsNotNone(re.search(SRC['duct'][0], name, re.I))
            self.assertEqual(level_of(name), 'LEVEL 02')
    def test_unrelated_cad_does_not_match(self):
        for name in ('NOT-MD02.dwg', 'MD02.pdf', '02-UCBBE-FMB-PL.dwg'):
            self.assertIsNone(re.search(SRC['duct'][0], name, re.I))
