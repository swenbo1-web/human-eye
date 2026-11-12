"""Freeze the reviewed first candidate before primary timing and installation."""

import ast
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = '2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390'


def main():
    initial = json.loads((HERE / 'testing/initial_candidate_01/MANIFEST.json').read_bytes())
    assert initial['source_sha256'] == SOURCE and initial['source_count'] == 137
    for row in initial['manifest']:
        assert hashlib.sha256((ROOT / row['path']).read_bytes()).hexdigest() == row['sha256'], row['path']
    constants = {}
    for node in ast.parse((ROOT / 'human_eye_plugin/runtime_identity.py').read_bytes()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION'):
                constants[node.targets[0].id] = ast.literal_eval(node.value)
    canonical = hashlib.sha256(json.dumps({
        'base_version': constants['BASE_VERSION'],
        'implementation_revision': constants['IMPLEMENTATION_REVISION'],
        'files': initial['manifest'],
    }, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    assert canonical == SOURCE
    verified = {}
    for folder, methods in (('initial_regressions_01', 213), ('initial_directed_01', 8), ('initial_wiring_01', 9)):
        path = HERE / 'testing' / folder / 'RESULTS.json'
        result = json.loads(path.read_bytes())
        assert result['passed'] and result['methods'] == methods
        assert result['source_sha256'] == SOURCE and result['sources_unchanged'] and result['guard_verified']
        verified[folder] = {'methods': methods, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    record = {
        'cycle_id': 'M3-SUFFICIENT-SEPARATION-001', 'source_sha256': SOURCE, 'source_count': 137,
        'manifest': initial['manifest'], 'verified_checks': verified,
        'simplification_decision': 'retain initial candidate; no demonstrated redundant work',
        'substantive_simplifications_used': 0,
        'simplification_review_sha256': hashlib.sha256((HERE / 'SIMPLIFICATION_REVIEW.md').read_bytes()).hexdigest(),
        'remaining_execution': 'one fixed sixty-call sequence, isolated installation, four-business actual MCP sequence',
        'new_fact': 'spatial_relation', 'new_task_set_version': 'task-query-set-v2',
        'legacy_contract_version': 'task-query-set-v1', 'default_activation': False,
    }
    with (HERE / 'CANDIDATE_FREEZE.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'source_count': 137, 'source_sha256': SOURCE, 'regression_and_directed_methods': 230}))


if __name__ == '__main__':
    main()
