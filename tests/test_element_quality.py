"""scripts/build_element_quality.py: rules on synthetic input, and the committed overlay is current."""
import json
import unittest
from pathlib import Path

from scripts import build_element_quality as eq

ROOT = Path(__file__).resolve().parents[1]


class RuleTests(unittest.TestCase):
    def test_storey_only_when_the_box_is_wholly_outside_the_labelled_storey(self):
        box = lambda lo, hi: [0, lo, 0, 1, hi, 1]
        self.assertIsNone(eq.storey_of('L1', box(5.5, 6.0)))
        self.assertIsNone(eq.storey_of('L2', box(8.7, 9.4)), 'framing that hangs under its own floor stays')
        self.assertIsNone(eq.storey_of('L1', box(5.3, 14.0)), 'a column that spans storeys keeps its base label')
        self.assertIsNone(eq.storey_of('L1', box(9.6, 9.9)), 'a device just above the next floor stays')
        self.assertEqual(eq.storey_of('L2', box(6.6, 6.9)), 'L1')
        self.assertEqual(eq.storey_of('L2', box(15.0, 15.4)), 'L3')
        self.assertEqual(eq.storey_of('L3', box(19.6, 20.5)), 'ROOF')
        self.assertEqual(eq.storey_of('L1', box(1.0, 2.0)), 'LOWER')
        self.assertIsNone(eq.storey_of('MEZZ', box(1.0, 2.0)), 'the mezzanine is inside the lower storey')
        self.assertIsNone(eq.storey_of('UNKNOWN', box(1.0, 2.0)))
        self.assertIsNone(eq.storey_of('L1', None))

    def test_layer_facts_read_modes_vertices_and_fragments_without_decoding(self):
        gltf = {'scenes': [{'nodes': [0, 3]}],
                'nodes': [{'name': 'A', 'children': [1, 2]}, {'mesh': 0}, {'mesh': 1}, {'name': 'B', 'mesh': 2}],
                'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1}]},
                           {'primitives': [{'attributes': {'POSITION': 0}, 'mode': 1}]},
                           {'primitives': [{'attributes': {'POSITION': 2}, 'mode': 1}]}],
                'accessors': [{'count': 8, 'min': [0, 0, 0], 'max': [1, 2, 3]}, {'count': 36}, {'count': 1, 'min': [0, 0, 0], 'max': [0, 0, 0]}]}
        facts = eq.layer_facts(gltf, {'A', 'B'})
        self.assertEqual((facts['A']['tris'], facts['A']['solid'], facts['A']['fragments'], facts['A']['maxVerts']), (12, True, 2, 8))
        self.assertEqual((facts['B']['solid'], facts['B']['maxVerts']), (False, 1))
        self.assertAlmostEqual(facts['A']['box'][4] - facts['A']['box'][1], 2.0)

    def test_numeric_order(self):
        self.assertEqual(eq.numeric(['10', '9', 'x', '100']), ['9', '10', '100', 'x'])


class CommittedOverlayTests(unittest.TestCase):
    def test_committed_overlay_is_current_and_keeps_every_identity(self):
        text = (ROOT / eq.OUT).read_text()
        self.assertEqual(text, eq.render(eq.build(log=lambda *_: None)), 'run python3 scripts/build_element_quality.py')
        data = json.loads(text)
        self.assertEqual(data['summary']['elements'], 66620)
        self.assertEqual(data['summary']['annotation'], 2690)
        self.assertEqual(data['summary']['noGeometry'], 243)
        self.assertEqual(set(data['layers']), set(eq.BUILDING_LAYERS))


if __name__ == '__main__':
    unittest.main()
