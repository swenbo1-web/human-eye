"""Freeze the unchanged product and six-slot sources before formal execution."""

import ast
import importlib.util
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    if (HERE / 'FROZEN.json').exists() or Path('D:/he_routed_001/formal').exists():
        raise FileExistsError('unused_freeze_and_formal_namespace_required')
    specification = importlib.util.spec_from_file_location('_routed_source_listing', HERE / 'launcher.py')
    launcher = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(launcher)
    plan = launcher.read(HERE / 'PLAN.json')
    sources = launcher.source_file_list(plan)
    manifest = launcher.read(plan['inputs']['input_manifest'])
    binding = launcher.read(manifest['product_binding']['path'])
    for row in binding['source_manifest']:
        source = ROOT / row['path']
        installed = Path(binding['install_root']) / row['path']
        if launcher.sha(source) != row['sha256'] or launcher.sha(installed) != row['sha256']:
            raise ValueError('unchanged_product_source_required:' + row['path'])
        sources[str(source.resolve())] = row['sha256']
        sources[str(installed.resolve())] = row['sha256']
    contract = launcher.read(HERE / 'admin/SCORING_CONTRACT.json')
    for path, expected in contract['files_sha256'].items():
        if launcher.sha(path) != expected:
            raise ValueError('fixed_scoring_source_changed:' + path)
        sources[path] = expected
    for path in HERE.rglob('*'):
        if not path.is_file():
            continue
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        sources[str(path.resolve())] = launcher.sha(path)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    frozen = {'schema': 'routed-task-benefit-source-freeze-v1', 'task': plan['task'],
              'baseline_git': plan['baseline_commit'], 'product_git': plan['product_commit'],
              'before_freeze_git': head, 'product_source_sha256': binding['source_sha256'],
              'files_sha256': dict(sorted(sources.items())),
              'prompt_sha256': plan['expected_prompt_sha256'], 'slots': plan['sequence'],
              'limits': {'contexts': 6, 'user_turns': 6, 'seconds_per_slot': 450,
                         'tool_business_admissions_per_slot': 12, 'actual_rasters_per_slot': 6,
                         'actual_formal_rasters': 36, 'preparation_rasters': 0, 'outer_retries': 0},
              'preparation_scope': 'Static source/parameter/reference checks; any separately authorized ordinary Python source-read receipt is retained. New models and rasters are zero.',
              'before_publication_ns': time.perf_counter_ns()}
    launcher.save(HERE / 'FROZEN.json', frozen, exclusive=True)
    print(json.dumps({'files': len(sources), 'freeze_sha256': launcher.sha(HERE / 'FROZEN.json'),
                      'new_model_contexts': 0, 'new_preparation_rasters': 0}))


if __name__ == '__main__':
    main()
