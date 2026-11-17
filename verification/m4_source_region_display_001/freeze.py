"""Freeze the candidate and owned execution inputs before Blender admission."""

import ast
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    baseline = json.loads((HERE / 'BASELINE.json').read_bytes())
    binding = json.loads((HERE / 'R0_RUN_BINDING.json').read_bytes())
    assert len(binding['source_manifest']) == 143
    for row in binding['source_manifest']:
        assert sha(Path(binding['install_root']) / row['path']) == row['sha256']
    direct = [HERE / 'BASELINE.json', HERE / 'R0_RUN_BINDING.json', HERE / 'SHARED_DEPENDENCY.json',
              HERE / 'public_schema/R0_scene_observe.json', HERE / 'oracle/source_oracle.py']
    direct += sorted((HERE / 'harness').rglob('*.py')) + sorted((HERE / 'inputs').iterdir())
    direct += [Path(baseline['asset']['path'])]
    for path in sorted((HERE / 'harness').rglob('*.py')):
        ast.parse(path.read_bytes(), filename=str(path))
    value = {'schema': 'source-region-display-freeze-v1', 'frozen_ns': time.perf_counter_ns(),
             'product_git': binding['preparation_git'], 'source_sha256': binding['source_sha256'],
             'direct_inputs': [{'path': str(path.resolve()), 'bytes': path.stat().st_size,
                                'sha256': sha(path)} for path in direct],
             'runtime_manifest': binding['source_manifest'], 'limits': baseline['limits']}
    with (HERE / 'SOURCE_FREEZE.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'files': len(direct), 'source_sha256': binding['source_sha256'], 'live_starts': 0}))


if __name__ == '__main__':
    main()
