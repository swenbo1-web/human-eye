"""Freeze the candidate installation and one-slot consumer before execution."""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if (HERE / 'FROZEN.json').exists() or Path('D:/he_consume_001/formal').exists():
        raise FileExistsError('unused_source_freeze_and_formal_namespace_required')
    specification = importlib.util.spec_from_file_location('_consumable_source_listing', HERE / 'launcher.py')
    launcher = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(launcher)
    plan = launcher.read(HERE / 'PLAN.json')
    sources = launcher.source_file_list(plan)
    binding = launcher.read(HERE / 'inputs/PRODUCT_BINDING.json')
    for row in binding['source_manifest']:
        source = ROOT / row['path']
        if digest(source) != row['sha256']:
            raise ValueError(f'candidate_repository_source_changed: {source}')
        sources[str(source.resolve())] = row['sha256']
    contract = launcher.read(HERE / 'admin/SCORING_CONTRACT.json')
    for path, expected in contract['files_sha256'].items():
        if digest(path) != expected:
            raise ValueError(f'fixed_scoring_source_changed: {path}')
        sources[path] = expected
    for path in HERE.rglob('*'):
        if not path.is_file():
            continue
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf8'), filename=str(path))
        sources[str(path.resolve())] = digest(path)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    frozen = {
        'schema': 'consumable-observation-source-freeze-v1',
        'task': plan['task'],
        'baseline_git': plan['baseline_commit'],
        'candidate_source_git': binding['preparation_git'],
        'before_freeze_git': head,
        'product_source_sha256': binding['source_sha256'],
        'files_sha256': dict(sorted(sources.items())),
        'prompt_sha256': plan['expected_prompt_sha256'],
        'slots': [{'slot': 'P1', 'group': 'P'}],
        'limits': {'contexts': 1, 'user_turns': 1, 'seconds': 450,
                   'tool_business_admissions': 12, 'actual_rasters': 6,
                   'preparation_rasters': 0, 'outer_retries': 0},
        'preparation_scope': 'Saved-state projections, synthetic protocol/string tests, literal-only finalization checks and isolated build. New model, observation and raster calls are zero.',
        'before_publication_ns': time.perf_counter_ns(),
    }
    with (HERE / 'FROZEN.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(frozen, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'files': len(sources), 'freeze_sha256': digest(HERE / 'FROZEN.json'),
                      'model_contexts_started': 0, 'new_preparation_rasters': 0}))


if __name__ == '__main__':
    main()
