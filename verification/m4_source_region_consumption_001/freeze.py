"""Freeze all inputs, execution sources, common wording and private scoring."""

import ast
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    began = time.perf_counter_ns()
    preflight = json.loads((HERE / 'PREFLIGHT.json').read_bytes())
    assert preflight['status'] == 'passed'
    rubric = json.loads((HERE / 'scoring/RUBRIC.json').read_bytes())
    assert rubric['common_prompt_verbatim'].encode('utf8') == (HERE / 'inputs/PROMPT.txt').read_bytes()
    paths = [path.resolve() for directory in ('inputs', 'scoring', 'harness')
             for path in (HERE / directory).rglob('*') if path.is_file() and path.suffix != '.pyc']
    paths += [HERE / name for name in ('BASELINE.json', 'INPUTS.json', 'PREFLIGHT.json',
                                       'checks/INPUT_REVIEW.json', 'checks/INFRA_PREFLIGHT_REVIEW.json')]
    paths += [Path(row['path']) for row in preflight['loaded_execution_sources']]
    paths += [Path(preflight['adapter_proof']['CLI_path']), Path(preflight['adapter_proof']['Python_path'])]
    binding = json.loads((HERE / 'inputs/PRODUCT_BINDING.json').read_bytes())
    assert len(binding['source_manifest']) == 143
    for row in binding['source_manifest']:
        path = Path(binding['install_root']) / row['path']
        assert sha(path) == row['sha256']
        paths.append(path)
    rows = [{'path': str(path.resolve()), 'bytes': path.stat().st_size, 'sha256': sha(path)}
            for path in sorted(set(paths))]
    for path in (HERE / 'harness').rglob('*.py'):
        ast.parse(path.read_bytes())
    value = {'schema': 'source-region-consumption-freeze-v1', 'frozen_ns': time.perf_counter_ns(),
        'preflight_completed_before_first_model': True, 'direct_inputs': rows,
        'product_source_sha256': binding['source_sha256'],
        'model_profile': {'model': 'gpt-6.1-sol', 'reasoning_effort': 'medium', 'service_tier': 'default'},
        'case_order': ['S1', 'S2', 'S3'], 'new_consumer_cap': 3, 'replacement_consumers': 0,
        'business_limit': 4, 'task_seconds': 450, 'process_seconds': 600,
        'preparation_freeze_started_ns': began,
        'private_scoring_is_not_a_consumer_input': True}
    with (HERE / 'FROZEN.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'inputs': len(rows), 'model_started': 0}))


if __name__ == '__main__':
    main()
