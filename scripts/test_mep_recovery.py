import unittest
from plan_mep_recovery import plan_layer
from verify_mep_recovery import counts, hashes, mat, mul, identity
from dedup_raw_gltf import dedup_raw

class PlanningTests(unittest.TestCase):
    def test_owner_scope_excludes_clearance_but_keeps_all_descendants(self):
        meta = {
            '1': {'externalId': 'a', 'name': 'Model'},
            '2': {'externalId': 'a/b', 'name': 'CAD'},
            '3': {'externalId': 'a/b/c', 'name': 'Pipe', 'source_file': '01-MP.dwg'},
            '4': {'externalId': 'a/b/c/d', 'name': 'Geometry'},
            '5': {'externalId': 'a/b/e', 'name': 'ACCESS SPACE', 'source_file': '01-MP.dwg'},
            '6': {'externalId': 'a/b/e/f', 'name': 'Geometry'},
            '7': {'externalId': 'a/b/g', 'name': 'Pipe', 'source_file': 'unrelated.dwg'},
        }
        total, eligible, owners = plan_layer(meta, (r'MP\.dwg$', None),
                                             lambda name, cad: None if name == 'ACCESS SPACE' else 'Pipe')
        self.assertEqual(total, {'3', '5'})
        self.assertEqual(eligible, {'3'})
        self.assertEqual(owners, {'3': '3', '4': '3'})
    def test_revit_categories_are_not_cad_entities(self):
        total, eligible, owners = plan_layer({'1': {'externalId': 'a/b/c', 'category': 'Conduits',
            'source_file': 'MP.dwg', 'name': 'Pipe'}}, (r'MP\.dwg$', None), lambda *_: 'Pipe')
        self.assertEqual(total, set())
        self.assertEqual(owners, {})

class GeometryTests(unittest.TestCase):
    def test_raw_dedup_preserves_every_node_and_distinct_bytes(self):
        g = {'nodes': [{'name': '1', 'mesh': 0}, {'name': '2', 'mesh': 1}, {'name': '3', 'mesh': 2}],
             'meshes': [{'primitives': [{'attributes': {'POSITION': i}}]} for i in range(3)],
             'accessors': [{'bufferView': i, 'count': 1, 'type': 'SCALAR', 'componentType': 5121} for i in range(3)],
             'bufferViews': [{'buffer': 0, 'byteOffset': i, 'byteLength': 1} for i in range(3)]}
        result = dedup_raw(g, [b'AAB'])
        self.assertEqual([n['name'] for n in result['nodes']], ['1', '2', '3'])
        self.assertEqual([n['mesh'] for n in result['nodes']], [0, 0, 1])
        self.assertEqual(len(result['accessors']), 2)
        self.assertEqual(g['nodes'][1]['mesh'], 1)
    def test_raw_dedup_rejects_compressed_source(self):
        with self.assertRaises(ValueError):
            dedup_raw({'extensionsUsed': ['KHR_draco_mesh_compression']}, [])
    def test_hashes_detect_modified_compressed_bytes(self):
        g = {'bufferViews': [{'byteOffset': 1, 'byteLength': 3}]}
        self.assertEqual(hashes(g, b'xABC'), hashes(g, b'yABC'))
        self.assertNotEqual(hashes(g, b'xABC'), hashes(g, b'xABD'))
    def test_identity_and_translation_transform(self):
        m = mat({'translation': [1, 2, 3]})
        self.assertEqual(mul(identity(), m), m)
        self.assertEqual(m[12:15], [1, 2, 3])
    def test_multiple_fragments_aggregate_to_owner(self):
        g = {'nodes': [{'name': '4', 'mesh': 0}, {'name': '5', 'mesh': 0}],
             'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1}]}],
             'accessors': [{'count': 4}, {'count': 6}]}
        self.assertEqual(counts(g, {'4': '3', '5': '3'})['3'], {'nodes': 2, 'mode_4_indices': 12})

if __name__ == '__main__':
    unittest.main()
