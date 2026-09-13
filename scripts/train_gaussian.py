"""Run a version-pinned local Brush trainer against a prepared posed dataset.
No downloads or uploads. Use a new run directory; logs and exact arguments persist.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_dataset(dataset):
    dataset = Path(dataset).resolve()
    provenance = json.loads((dataset / 'dataset-provenance.json').read_text())
    if provenance.get('frame') != 'unchanged scan Y-up metres':
        raise ValueError('Dataset must explicitly preserve the scan Y-up metre frame')
    for name in ['transforms.json', 'transforms_val.json']:
        config = json.loads((dataset / name).read_text())
        if not config.get('frames'):
            raise ValueError(f'{name} requires views')
        for frame in config['frames']:
            image = (dataset / frame['file_path']).resolve()
            if not image.is_relative_to(dataset) or not image.is_file():
                raise ValueError('Training image missing or outside dataset')
    return dataset


def train(binary, dataset, output, steps=50000, max_splats=1000000,
          resolution=768, checkpoint_every=5000, refine_every=400,
          growth_stop=30000, sh_degree=2):
    binary = Path(binary).resolve()
    dataset = validate_dataset(dataset)
    output = Path(output).resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError('Supply an executable, verified Brush v0.3.0 binary')
    if min(steps, max_splats, resolution, checkpoint_every, refine_every) < 1:
        raise ValueError('Training counts must be positive')
    if max_splats > 3000000 or resolution > 2048 or not 0 <= sh_degree <= 3:
        raise ValueError('Configuration exceeds the local review budget')
    if not 0 <= growth_stop <= steps:
        raise ValueError('Growth stop must be between zero and total steps')
    output.mkdir(parents=True, exist_ok=False)
    args = [str(binary), str(dataset), '--total-steps', str(steps),
            '--max-splats', str(max_splats), '--refine-every', str(refine_every),
            '--growth-stop-iter', str(growth_stop), '--sh-degree', str(sh_degree),
            '--max-resolution', str(resolution), '--export-every', str(checkpoint_every),
            '--eval-every', str(checkpoint_every), '--eval-save-to-disk',
            '--export-path', str(output)]
    record = {'startedAt': datetime.now(timezone.utc).isoformat(),
              'args': args, 'executableSha256': digest(binary),
              'datasetProvenanceSha256': digest(dataset / 'dataset-provenance.json'),
              'software': 'Brush v0.3.0; verify downloaded binary against official release checksum',
              'status': 'running'}
    record_path = output / 'command.json'
    record_path.write_text(json.dumps(record, indent=2))
    started = time.monotonic()
    try:
        with (output / 'train.log').open('w') as log:
            result = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT,
                                    env={**os.environ, 'RUST_LOG': 'warn,brush_cli=info,brush_process=info'})
        record['exitCode'] = result.returncode
        checkpoint = output / f'export_{steps}.ply'
        record['status'] = 'trained' if result.returncode == 0 and checkpoint.is_file() else 'failed'
        if record['status'] == 'trained':
            record['checkpointSha256'] = digest(checkpoint)
            record['checkpointBytes'] = checkpoint.stat().st_size
    except BaseException as error:
        record['status'] = 'interrupted-or-failed'
        record['errorType'] = type(error).__name__
        raise
    finally:
        record['endedAt'] = datetime.now(timezone.utc).isoformat()
        record['elapsedSeconds'] = round(time.monotonic() - started, 3)
        record_path.write_text(json.dumps(record, indent=2))
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['brush', 'dataset', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    for name, default in [('steps', 50000), ('max-splats', 1000000), ('resolution', 768),
                          ('checkpoint-every', 5000), ('refine-every', 400),
                          ('growth-stop', 30000), ('sh-degree', 2)]:
        parser.add_argument('--' + name, type=int, default=default)
    a = parser.parse_args()
    result = train(a.brush, a.dataset, a.output, a.steps, a.max_splats, a.resolution,
                   a.checkpoint_every, a.refine_every, a.growth_stop, a.sh_degree)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'trained' else 1)
