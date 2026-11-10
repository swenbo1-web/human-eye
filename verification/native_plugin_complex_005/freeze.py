"""Freeze verified preparation once. Only the administrator can subsequently GO."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.parent/'native_plugin_complex_003'
PREVIOUS = HERE.parent/'native_plugin_complex_004'
DIAG = HERE.parent/'scale_diag_001'
ADMIN = Path('D:/hefe/verification/fixes/20261110_native_plugin_compare_005')
RUBRIC_SHA256 = '4dc89dcfe8e82a2e28c56391b091ef88167da66305d41cfd124246180c7246a4'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if condition is not True:
        raise ValueError(message)


def main():
    target = HERE/'FREEZE.json'
    require(not target.exists() and not (HERE/'GO.json').exists() and not (HERE/'STARTED.json').exists(), 'freeze_must_precede_GO_and_consumers_and_be_exclusive')
    plan = read(HERE/'PLAN.json'); review = read(HERE/'PREFLIGHT_REVIEW.json')
    tests = read(HERE/'ADAPTER_TESTS.json'); source = read(HERE/'SOURCE_PREFLIGHT.json')
    require(plan['cycle_id'] == 'NATIVE-PLUGIN-COMPLEX-005' and plan['denominator'] == 18
        and review['passed'] is True and review['model_calls'] == 0 and source['passed'] is True
        and tests['passed'] is True and tests['actor_sha256'] == sha(HERE/'actor.py'), 'preparation_or_adapter_tests_not_qualified')
    require(tests['test_sha256'] == sha(HERE/'test_adapter.py'), 'new_adapter_test_script_changed_after_receipt')
    require(source['versions']['H']['source_sha256'] == 'a045a800256f4767271308d239c735177f992ce3408d927d42bde5f1d4b60d8f'
        and len(source['versions']['H']['runtime_sources']) == 125
        and source['versions']['C']['source_sha256'] == '3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd'
        and len(source['versions']['C']['runtime_sources']) == 137, 'actual_historical_or_current_source_contract_changed')
    sequence = plan['sequence']
    require(len(sequence) == 18 and [slot['cell'] for slot in sequence] == [str(i).zfill(2) for i in range(1, 19)]
        and Counter((row['task'], row['group']) for row in sequence) == Counter({(task, group): 3 for task in ('assembly', 'discovery') for group in ('N', 'H', 'C')}), 'fixed_eighteen_slot_denominator_changed')
    require(sha(ADMIN/'PRIVATE_RUBRIC_REUSED.json') == RUBRIC_SHA256, 'original_rubric_changed')
    files = {}
    def add(path, expected=None):
        path = Path(path).resolve()
        actual = sha(path)
        require(expected is None or actual == expected, 'referenced_bytes_changed:'+str(path))
        if str(path) in files:
            require(files[str(path)] == actual, 'inconsistent_reference:'+str(path))
        files[str(path)] = actual
    # Each no-model read, actual product frame and closure receipt is protected
    # by the independently recomputed review index, without a new test harness.
    for path, expected in review['verified_artifact_hashes'].items():
        add(path, expected)
    for path in sorted(HERE.glob('*.py')):
        add(path)
    for name in ('PLAN.json', 'PLAN_DRAFT.md', 'SOURCE_PREFLIGHT.json', 'H_CAPABILITY_REVIEW.json',
            'CLI_PREFLIGHT.json', 'PREFLIGHT.json', 'PREFLIGHT_REVIEW.json', 'ADAPTER_TESTS.json',
            'H_identity.stdout.json', 'H_schemas.stdout.json', 'H_TOOLS_CATALOGUE.json',
            'C_identity.stdout.json', 'C_schemas.stdout.json', 'C_TOOLS_CATALOGUE.json'):
        add(HERE/name)
    for pattern in ('*_identity.COMMAND.json', '*_schemas.COMMAND.json', '*_identity.stderr.txt', '*_schemas.stderr.txt'):
        for path in HERE.glob(pattern):
            add(path)
    for name in ('PREFLIGHT_CLEANUP.json', 'PREFLIGHT_PID_INDEX.json'):
        add(HERE/name)
    for name in ('ROOT_PLAN.md', 'INSTALLED_BASELINE_REVIEW.json', 'CATALOGUE_FAIRNESS_REVIEW.md', 'PRIVATE_RUBRIC_REUSED.json'):
        add(ADMIN/name)
    # Unchanged model-visible text is reused by raw bytes, never reconstructed.
    for name in ('SESSION_RULES.txt', 'PROMPT_DISCOVERY.txt'):
        add(PREVIOUS/name)
    assembly = read(OLD/'FREEZE.json')
    for name in ('scene.blend', 'PROMPT.txt', 'private/TRUTH.json', 'private/author_mesh_snapshots.json'):
        add(OLD/name, assembly[name])
    add(OLD/'FREEZE.json')
    diag = read(DIAG/'FREEZE.json')
    for name in ('fixtures/D48.blend', 'fixtures/D48.json', 'ORACLE.json', 'ORACLE_REPLAY.json'):
        expected = ('0fff81623ae584d6cda4a03052e7ea1b0dbf974da2f9e4b23f4fc761616feee4'
            if name == 'ORACLE_REPLAY.json' else diag['files'][name])
        add(DIAG/name, expected)
    add(DIAG/'FREEZE.json')
    for name in ('actor.py', 'reused/accepted_native.py', 'reused/stdio_attach.py'):
        add(OLD/name)
    # The previous lifecycle proof is reused only through exact AST equality.
    for name in ('actor.py', 'test_actor_lifecycle.py', 'WRAPPER_TESTS.json'):
        add(PREVIOUS/name)
    for group in ('H', 'C'):
        version = source['versions'][group]
        entry = Path(version['entry'])
        add(entry, version['entry_sha256'])
        add(entry.with_name('RUNTIME_BINDING.json'), version['binding_sha256'])
        add(entry.with_name('installed_release.py'), version['admin_sha256'])
        for row in version['runtime_sources']:
            add(Path(version['installed_root'])/row['path'], row['sha256'])
        for row in version['source_origin']['records']:
            add(row['path'], row['sha256'])
    expected_inputs = {'assembly': '1ffb175653bdc11423e62e177915639f4fc10ee5a22871dc41259c8032097358',
        'discovery': 'ddcf37206d68bb5abfebccaabe4699b1681a4470d4d22799d8b405df26f09571'}
    for task, row in plan['tasks'].items():
        raw = Path(plan['session_rules']).read_bytes()+b'\n'+Path(row['prompt']).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == row['model_input_sha256'] == expected_inputs[task]
            and len(raw) == row['model_input_bytes'], 'actual_model_input_changed:'+task)
        add(row['prompt'], row['prompt_sha256'])
    require(all(sha(path) == expected for path, expected in files.items()), 'reference_changed_during_freeze')
    result = {'task': 'NATIVE-PLUGIN-COMPLEX-005', 'phase': 'PREFLIGHT_READY; administrator GO pending',
        'parent_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
        'model_execution_authorized': False, 'logical_denominator': 18, 'files_sha256': files,
        'private_truth_visibility': 'not sent, copied into consumer workspaces or exposed by public broker; audited Python protocol, not an adversarial OS sandbox',
        'model_inputs': {task: {key: row[key] for key in ('prompt_sha256', 'model_input_sha256', 'model_input_bytes')} for task, row in plan['tasks'].items()},
        'source_versions': {group: source['versions'][group]['source_sha256'] for group in ('H', 'C')},
        'actual_public_read_schema_policy': 'common native; each H/C original observe and status definitions; no cross-release normalization',
        'preflight_model_calls': 0, 'preflight_public_stdio_measured': False,
        'preflight_transport_scope': 'direct broker TCP and actual product stdio; formal consumers alone measure actual public thin stdio',
        'no_product_or_default_config_changes': True}
    with target.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'freeze_sha256': sha(target), 'files': len(files), 'model_calls': 0, 'phase': result['phase']}))


if __name__ == '__main__':
    main()
