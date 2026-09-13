import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('training', Path(__file__).resolve().parents[1] / 'scripts/train_gaussian.py')
training = importlib.util.module_from_spec(spec)
spec.loader.exec_module(training)


class TrainingTest(unittest.TestCase):
    def test_record_failure_and_require_final_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = root / 'dataset'
            dataset.mkdir()
            (dataset / 'image.png').write_bytes(b'test fixture')
            (dataset / 'dataset-provenance.json').write_text(json.dumps({'frame': 'unchanged scan Y-up metres'}))
            config = {'frames': [{'file_path': 'image.png'}]}
            for name in ['transforms.json', 'transforms_val.json']:
                (dataset / name).write_text(json.dumps(config))
            binary = root / 'fake-brush'
            binary.write_text('#!/bin/sh\nexit 0\n')
            binary.chmod(0o755)
            record = training.train(binary, dataset, root / 'run', steps=10, growth_stop=5)
            self.assertEqual(record['exitCode'], 0)
            self.assertEqual(record['status'], 'failed')  # A silent exit is not a trained model.
            self.assertIn('endedAt', record)
            with self.assertRaises(FileExistsError):
                training.train(binary, dataset, root / 'run', steps=10, growth_stop=5)
            config['frames'][0]['file_path'] = '../outside.png'
            (root / 'outside.png').write_bytes(b'outside')
            (dataset / 'transforms.json').write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                training.validate_dataset(dataset)


if __name__ == '__main__':
    unittest.main()
