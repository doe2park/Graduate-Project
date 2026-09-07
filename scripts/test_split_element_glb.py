import copy
import struct
import unittest
from extract_layer import subset_from_source
from split_element_glb import split_document, primitive_counts, buffer_hashes, partitions, floor_key


class SplitTests(unittest.TestCase):
    def fixture(self):
        binary = struct.pack('<9f3H', 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 2)
        document = {
            'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
            'nodes': [{'rotation': [0, 0, 0, 1], 'scale': [0.3048] * 3, 'children': [1]},
                      {'children': [2, 3, 4, 5]},
                      {'name': '10', 'mesh': 0, 'translation': [1, 2, 3]},
                      {'name': '10', 'mesh': 0, 'translation': [4, 5, 6]},
                      {'name': '20', 'mesh': 0}, {'name': '30', 'mesh': 0}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1}]}],
            'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3',
                           'min': [0, 0, 0], 'max': [1, 1, 0]},
                          {'bufferView': 1, 'componentType': 5123, 'count': 3, 'type': 'SCALAR'}],
            'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': 36},
                            {'buffer': 0, 'byteOffset': 36, 'byteLength': 6}],
            'buffers': [{'byteLength': len(binary)}], 'materials': []}
        elements = {'10': {'levelKey': 'L1'}, '20': {'levelKey': 'L1'},
                    '30': {'source_file': '00-building-FP.DWG'}}
        return document, binary, elements

    def test_split_preserves_identity_counts_root_and_bytes(self):
        doc, binary, elements = self.fixture()
        chunks = split_document(doc, binary, elements, 2, subset_from_source)
        self.assertEqual([suffix for _, suffix, *_ in chunks], ['lower', 'l1-1', 'l1-2'])
        source_counts = primitive_counts(doc)
        seen = set()
        for _, _, result, data, _ in chunks:
            counts = primitive_counts(result)
            self.assertFalse(seen & counts.keys())
            seen.update(counts)
            for owner, count in counts.items():
                self.assertEqual(count, source_counts[owner])
            self.assertFalse(buffer_hashes(result, data) - buffer_hashes(doc, binary))
            self.assertEqual({k: v for k, v in result['nodes'][0].items() if k != 'children'},
                             {k: v for k, v in doc['nodes'][0].items() if k != 'children'})
            self.assertLessEqual(sum(count['nodes'] for count in counts.values()), 2)
        self.assertEqual(seen, set(source_counts))
        self.assertEqual(doc['nodes'][2]['translation'], [1, 2, 3])

    def test_owner_is_never_split_across_chunks(self):
        doc, _, elements = self.fixture()
        with self.assertRaisesRegex(ValueError, 'alone exceeds'):
            partitions(doc, elements, 1)

    def test_rejects_intermediate_transform_that_would_be_lost(self):
        doc, binary, elements = self.fixture()
        doc['nodes'][1]['translation'] = [0, 2, 0]
        with self.assertRaisesRegex(ValueError, 'Intermediate'):
            split_document(doc, binary, elements, 2, subset_from_source)

    def test_rejects_unbound_mesh_identity(self):
        doc, _, elements = self.fixture()
        del elements['30']
        with self.assertRaisesRegex(ValueError, 'Unbound'):
            partitions(doc, elements, 2)

    def test_source_floor_fallback(self):
        self.assertEqual(floor_key({'source_file': '03-building-FP.DWG'}), 'l3')
        self.assertEqual(floor_key({}), 'unknown')


if __name__ == '__main__':
    unittest.main()
