"""Freeze the one-slot entry and unchanged task-quality dependencies."""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if (HERE / 'FROZEN.json').exists() or Path('D:/he_explicit_001').exists():
        raise FileExistsError('fresh diagnostic freeze and runtime required')
    spec = importlib.util.spec_from_file_location('_explicit_source_listing', HERE / 'launcher.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    plan = launcher.read(HERE / 'PLAN.json')
    sources = launcher.source_file_list(plan)
    for path in HERE.rglob('*'):
        if not path.is_file():
            continue
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf8'), filename=str(path))
        sources[str(path.resolve())] = digest(path)
    contract = launcher.read(HERE / 'admin/SCORING_CONTRACT.json')
    for path, expected in contract['files_sha256'].items():
        assert digest(path) == expected, path
        sources[path] = expected
    binding = launcher.read(launcher.read(plan['inputs']['input_manifest'])['product_binding']['path'])
    for row in binding['source_manifest']:
        source = ROOT / row['path']
        assert digest(source) == row['sha256']
        sources[str(source.resolve())] = row['sha256']
    result = {'schema': 'explicit-observation-single-source-freeze-v1',
              'task': plan['task'], 'baseline_git': plan['baseline_commit'],
              'product_git': '7d42bb939c7881a98fe322c10c216398f6c7aecc',
              'product_source_sha256': binding['source_sha256'],
              'files_sha256': dict(sorted(sources.items())),
              'prefix_sha256': plan['prefix_sha256'],
              'original_suffix_sha256': plan['original_suffix_sha256'],
              'prompt_sha256': plan['expected_prompt_sha256'],
              'slots': [{'slot': 'P1', 'group': 'P'}],
              'limits': {'contexts': 1, 'user_turns': 1, 'seconds': 450,
                         'tool_attempts': 12, 'raster_attempts': 6,
                         'preparation_raster_attempts': 0, 'outer_retries': 0},
              'frozen_before_publication_ns': time.perf_counter_ns(),
              'preparation_scope': 'Static source, parameters and hashes only. No fake, 42 probe, product, renderer or model execution.'}
    with (HERE / 'FROZEN.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'files': len(sources), 'freeze_sha256': digest(HERE / 'FROZEN.json'),
                      'preparation_rasters': 0, 'model_contexts_started': 0}))


if __name__ == '__main__':
    main()
