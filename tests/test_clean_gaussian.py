import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
try:
    import scipy  # noqa: F401
    HAVE_SCIPY = True
except ImportError:  # the Gaussian tools run in .venv-gaussian, which has SciPy
    HAVE_SCIPY = False
import clean_gaussian as cg  # noqa: E402
import package_gaussian  # noqa: E402

FIELDS = (['x', 'y', 'z', 'opacity'] + [f'rot_{i}' for i in range(4)] + [f'scale_{i}' for i in range(3)]
          + [f'f_dc_{i}' for i in range(3)] + [f'f_rest_{i}' for i in range(3)])
CAMERAS = [(0.0, 1.5, 0.0), (4.0, 1.5, 0.0), (8.0, 1.5, 0.0)]  # a corridor walk, Y up, floor at y = 0


def gaussian(x, y, z, alpha=0.9, scales=(0.02, 0.02, 0.005)):
    row = dict.fromkeys(FIELDS, 0.1)
    row.update(x=x, y=y, z=z, opacity=np.log(alpha / (1 - alpha)), rot_0=1.0, rot_1=0.0, rot_2=0.0, rot_3=0.0)
    row.update({f'scale_{i}': np.log(s) for i, s in enumerate(scales)})
    return row


def scene():
    """A dense floor and wall, plus one planted floater per rule (names say which)."""
    rows, names = [], []
    for x in np.arange(-1, 9.01, 0.1):
        for z in np.arange(-1, 1.01, 0.1):
            rows.append(gaussian(x, 0.0, z)); names.append('good')
        for y in np.arange(0, 3.01, 0.1):
            rows.append(gaussian(x, y, 1.0)); names.append('good')
    planted = {
        'opacity': gaussian(4.0, 0.0, 0.05, alpha=0.005),
        'isolated': gaussian(4.0, 2.2, -0.5),                        # mid-air, 0.5 m+ from everything
        'needle': gaussian(2.0, 0.0, 0.0, scales=(0.6, 0.01, 0.005)),  # long thin streak on the floor
        'oversized': gaussian(6.0, 0.0, 0.0, scales=(2.5, 2.4, 0.01)),
        'outside': gaussian(30.0, 0.0, 0.0),                          # 22 m beyond the last camera
    }
    for name, row in planted.items():
        rows.append(row); names.append(name)
    # 'outside' is also isolated; give it neighbours so it is flagged by the outside rule alone
    for dx in np.arange(-0.2, 0.21, 0.1):
        for dz in np.arange(-0.2, 0.21, 0.1):
            if dx or dz:
                rows.append(gaussian(30.0 + dx, 0.0, dz)); names.append('outside-cluster')
    rows.append(gaussian(4.0, -6.0, 0.0)); names.append('below')   # 7.5 m under the cameras
    data = np.zeros(len(rows), dtype=[(f, '<f4') for f in FIELDS])
    for i, row in enumerate(rows):
        for f in FIELDS:
            data[f][i] = row[f]
    return data, np.array(names)


def write_inputs(folder):
    data, names = scene()
    ply = Path(folder) / 'export.ply'
    cg.write_ply(ply, data, 'test scene')
    transforms = Path(folder) / 'transforms.json'
    frames = [{'file_path': f'images/{i}.png',
               'transform_matrix': [[1, 0, 0, c[0]], [0, 1, 0, c[1]], [0, 0, 1, c[2]], [0, 0, 0, 1]]}
              for i, c in enumerate(CAMERAS) for _ in range(2)]  # two views per station share a centre
    transforms.write_text(json.dumps({'frames': frames}))
    return data, names, ply, transforms


@unittest.skipUnless(HAVE_SCIPY, 'SciPy is installed in .venv-gaussian')
class FloaterRuleTests(unittest.TestCase):
    def setUp(self):
        self.data, self.names = scene()
        self.cameras = np.array(CAMERAS)
        self.flags = cg.floater_flags(self.data, self.cameras, cg.resolve_params('medium'))

    def test_each_planted_floater_is_flagged_by_its_rule(self):
        for rule in ('opacity', 'isolated', 'needle', 'oversized', 'outside'):
            self.assertTrue(self.flags[rule][self.names == rule].all(), rule)

    def test_points_far_below_the_cameras_are_outside(self):
        self.assertTrue(self.flags['outside'][self.names == 'below'].all())

    def test_good_surface_and_far_corridor_ends_are_kept(self):
        good = self.names == 'good'
        for rule, flagged in self.flags.items():
            self.assertFalse(flagged[good].any(), f'{rule} removed real surface')
        # the corridor ends (x = -1 and x = 9) are far from the cloud centre but next to a camera: kept
        self.assertTrue(good[(self.data['x'] < -0.9) | (self.data['x'] > 8.9)].any())

    def test_flat_surface_discs_are_not_needles(self):
        # Brush surfaces are flat discs (two long axes, one tiny): a large max/min ratio is normal
        flat = cg.floater_flags(np.array([tuple(gaussian(4, 0, 0, scales=(0.05, 0.05, 1e-5))[f] for f in FIELDS)],
                                         dtype=self.data.dtype), self.cameras, cg.resolve_params('strong'))
        self.assertFalse(flat['needle'][0])


@unittest.skipUnless(HAVE_SCIPY, 'SciPy is installed in .venv-gaussian')
class CleanOutputTests(unittest.TestCase):
    def test_writes_derivative_with_identical_kept_rows_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, names, ply, transforms = write_inputs(tmp)
            source_sha = package_gaussian.sha(ply)
            report = cg.clean(ply, [transforms], Path(tmp) / 'out', 'medium')
            out = package_gaussian.read_ply(Path(tmp) / 'out' / 'cleaned.ply')
            keep = (names == 'good')
            self.assertEqual(out.tobytes(), data[keep].tobytes())  # every parameter, incl. f_rest, unchanged
            self.assertEqual(package_gaussian.sha(ply), source_sha)  # source untouched
            saved = json.loads((Path(tmp) / 'out' / 'clean-report.json').read_text())
            self.assertEqual(saved['source']['sha256'], source_sha)
            self.assertEqual(saved['output']['sha256'], package_gaussian.sha(Path(tmp) / 'out' / 'cleaned.ply'))
            self.assertEqual(saved['kept'], int(keep.sum()))
            self.assertEqual(saved['removed'], int((~keep).sum()))
            self.assertEqual(saved['cameras']['uniqueCentres'], 3)
            self.assertIn('not a geometry correction', saved['scope'].lower())
            self.assertEqual(report['flaggedByRule']['needle'], 1)

    def test_refuses_existing_output_and_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, ply, transforms = write_inputs(tmp)
            out = Path(tmp) / 'out'
            report = cg.clean(ply, [transforms], out, 'light', dry_run=True)
            self.assertEqual(report['status'], 'dry-run')
            self.assertFalse(out.exists())
            out.mkdir()
            with self.assertRaises(FileExistsError):
                cg.clean(ply, [transforms], out, 'light')

    def test_cli_requires_inputs(self):
        self.assertEqual(cg.main(['--input', 'a.ply']), 2)


def write_glb(path, triangles):
    """Minimal glTF 2.0 binary: one mesh of float32 positions and uint32 indices (source frame Z-up, as exported)."""
    import struct
    verts = np.asarray(triangles, dtype='<f4').reshape(-1, 3)
    idx = np.arange(len(verts), dtype='<u4')
    blob = verts.tobytes() + idx.tobytes()
    gltf = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1, 'mode': 4}]}],
            'buffers': [{'byteLength': len(blob)}],
            'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': verts.nbytes},
                            {'buffer': 0, 'byteOffset': verts.nbytes, 'byteLength': idx.nbytes}],
            'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': len(verts), 'type': 'VEC3'},
                          {'bufferView': 1, 'componentType': 5125, 'count': len(idx), 'type': 'SCALAR'}]}
    js = json.dumps(gltf).encode()
    js += b' ' * (-len(js) % 4)
    blob += b'\0' * (-len(blob) % 4)
    body = struct.pack('<II', len(js), 0x4E4F534A) + js + struct.pack('<II', len(blob), 0x004E4942) + blob
    Path(path).write_bytes(struct.pack('<4sII', b'glTF', 2, 12 + len(body)) + body)


def quad(a, b, c, d):
    return [a, b, c, a, c, d]


# The test scene's floor (training y = 0) and wall (training z = 1) in the exported Z-up frame,
# where training [x, y, z] = source [x, z, -y].
SCAN_TRIANGLES = (quad((-1, 1, 0), (9, 1, 0), (9, -1, 0), (-1, -1, 0))
                  + quad((-1, -1, 0), (9, -1, 0), (9, -1, 3), (-1, -1, 3)))


def hovering_cluster():
    """A dense patch 1 m above the floor: not isolated, not thin, inside the walk, but far from any scanned surface."""
    return [gaussian(4.0 + dx, 1.0, -0.3 + dz) for dx in np.arange(-0.2, 0.21, 0.1) for dz in np.arange(-0.2, 0.21, 0.1)]


@unittest.skipUnless(HAVE_SCIPY, 'SciPy is installed in .venv-gaussian')
class MeshRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.glb = Path(self.tmp.name) / 'scan.glb'
        write_glb(self.glb, SCAN_TRIANGLES)

    def tearDown(self):
        self.tmp.cleanup()

    def test_samples_lie_on_the_scan_surfaces_in_the_training_frame(self):
        pts = cg.mesh_surface_samples([self.glb], spacing=0.05)
        on_floor = np.abs(pts[:, 1]) < 1e-5
        on_wall = np.abs(pts[:, 2] - 1) < 1e-5
        self.assertTrue((on_floor | on_wall).all())
        self.assertGreater(len(pts), 0.8 * (20 + 30) / 0.05 ** 2)  # about one sample per 5 cm square

    def test_hovering_cluster_is_caught_only_by_the_mesh_rule(self):
        data, names = scene()
        extra = hovering_cluster()
        hover = np.zeros(len(extra), dtype=data.dtype)
        for i, row in enumerate(extra):
            for f in FIELDS:
                hover[f][i] = row[f]
        data = np.concatenate([data, hover])
        names = np.concatenate([names, ['hover'] * len(extra)])
        mesh = cg.mesh_surface_samples([self.glb])
        flags = cg.floater_flags(data, np.array(CAMERAS), cg.resolve_params('medium'), mesh_points=mesh)
        self.assertTrue(flags['offsurface'][names == 'hover'].all())
        self.assertFalse(flags['offsurface'][names == 'good'].any())
        for rule in cg.RULES:
            self.assertFalse(flags[rule][names == 'hover'].any(), rule)
        without = cg.floater_flags(data, np.array(CAMERAS), cg.resolve_params('medium'))
        self.assertNotIn('offsurface', without)

    def test_report_records_mesh_and_its_risk_only_when_used(self):
        _, _, ply, transforms = write_inputs(self.tmp.name)
        with_mesh = cg.clean(ply, [transforms], Path(self.tmp.name) / 'a', 'medium', mesh_glbs=[self.glb])
        self.assertIn('offsurface', with_mesh['flaggedByRule'])
        self.assertEqual(with_mesh['mesh']['files'], {'scan.glb': package_gaussian.sha(self.glb)})
        self.assertIn('holes', with_mesh['mesh']['risk'])
        self.assertEqual(with_mesh['parameters']['offSurfaceMetres'], 0.3)
        plain = cg.clean(ply, [transforms], Path(self.tmp.name) / 'b', 'medium')
        self.assertNotIn('offsurface', plain['flaggedByRule'])
        self.assertNotIn('mesh', plain)
        self.assertNotIn('offSurfaceMetres', plain['parameters'])

    def test_cli_mesh_needs_a_run(self):
        self.assertEqual(cg.main(['--input', 'a.ply', '--cameras', 'b.json', '--output', 'c', '--mesh']), 2)


class ParameterTests(unittest.TestCase):
    def test_presets_get_stricter(self):
        light, medium, strong = (cg.resolve_params(p) for p in ('light', 'medium', 'strong'))
        self.assertLess(light['minAlpha'], medium['minAlpha'])
        self.assertLess(medium['minAlpha'], strong['minAlpha'])
        self.assertGreater(light['isolatedMetres'], strong['isolatedMetres'])

    def test_overrides_are_typed_and_checked(self):
        self.assertEqual(cg.resolve_params('medium', {'isolatedMetres': '0.25'})['isolatedMetres'], 0.25)
        with self.assertRaises(ValueError):
            cg.resolve_params('medium', {'nope': 1})
        with self.assertRaises(ValueError):
            cg.resolve_params('extreme')
        self.assertEqual(cg.parse_overrides(['a=1', 'b = 2']), {'a': '1', 'b': '2'})
        with self.assertRaises(ValueError):
            cg.parse_overrides(['a'])


class PipelineFlagTests(unittest.TestCase):
    def test_clean_is_off_by_default_and_keeps_settings_unchanged(self):
        import run_gaussian_pipeline as pipe
        parser = pipe.build_parser()
        self.assertEqual(parser.parse_args(['--capture', '2026-09-17']).clean, 'off')
        self.assertEqual(parser.parse_args(['--capture', '2026-09-17', '--clean', 'light']).clean, 'light')
        out = []
        real_print = print
        try:
            import builtins
            builtins.print = lambda *a, **k: out.append(' '.join(map(str, a)))
            pipe.main(['--capture', '2026-09-17', '--dry-run'])
            default = json.loads(out[-1])['settings']
            out.clear()
            pipe.main(['--capture', '2026-09-17', '--dry-run', '--clean', 'medium'])
            cleaned = json.loads(out[-1])['settings']
        finally:
            builtins.print = real_print
        self.assertNotIn('clean', default)  # so earlier run folders still resume
        self.assertEqual(cleaned['clean'], 'medium')
        self.assertNotIn('cleanMesh', cleaned)

    def test_clean_mesh_flag(self):
        import io
        import contextlib
        import run_gaussian_pipeline as pipe
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(pipe.main(['--capture', '2026-09-17', '--dry-run', '--clean-mesh']), 2)
        self.assertIn('--clean-mesh needs --clean', err.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            pipe.main(['--capture', '2026-09-17', '--dry-run', '--clean', 'light', '--clean-mesh'])
        self.assertTrue(json.loads(out.getvalue())['settings']['cleanMesh'])


if __name__ == '__main__':
    unittest.main()
