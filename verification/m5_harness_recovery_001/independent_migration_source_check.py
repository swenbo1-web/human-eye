"""Bounded source differences for the new recovery context."""

import ast
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
OLD = HERE.with_name('m5_task_consumption_001')


def pin(path):
    data = path.read_bytes()
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def functions(path):
    result = {}
    for node in ast.parse(path.read_bytes()).body:
        if isinstance(node, ast.FunctionDef):
            result[node.name] = ast.dump(node, include_attributes=False)
        if isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, ast.FunctionDef):
                    result[node.name + '.' + member.name] = ast.dump(member, include_attributes=False)
    return result


def main():
    checks = []

    def check(name, condition, detail=None):
        checks.append({'name': name, 'passed': bool(condition), 'detail': detail})

    candidate = OLD / 'recovery_candidate/owned_runtime.py'
    current = HERE / 'harness/owned_runtime.py'
    old_functions, new_functions = functions(candidate), functions(current)
    changed = {name for name in old_functions if old_functions[name] != new_functions.get(name)}
    check('candidate_runtime_changes_only_startup_context_and_deadline', changed == {'RootRuntime.start', 'RootRuntime.check'}, sorted(changed))
    check('public_request_and_correlator_preserve_accepted_candidate_AST', all(old_functions[name] == new_functions[name]
        for name in ('correlate_archive', 'RootRuntime.public_request')))
    check('runtime_has_no_added_or_removed_functions', set(old_functions) == set(new_functions))
    before, after = functions(OLD / 'native_tools.py'), functions(HERE / 'native_tools.py')
    changed = {name for name in before if before[name] != after.get(name)}
    check('ordinary_Python_only_changes_observe_session_context', changed == {'OrdinarySession.observe'}, sorted(changed))
    before, after = functions(OLD / 'bridge.py'), functions(HERE / 'bridge.py')
    changed = {name for name in before if before[name] != after.get(name)}
    check('bridge_changes_only_outer_cap_public_identity_and_runtime_loader', changed == {'Owner.call', 'Owner.handle', 'main'}, sorted(changed))
    for name in ('bootstrap.py', 'native_consumer_audit.py', 'SHARED_DEPENDENCY.json',
                 'public_schema/A_scene_observe.json', 'public_schema/B_scene_observe.json',
                 'fixtures/DEVICE_CAMERAS.json', 'fixtures/DEVICE_PREPARATION.json'):
        check('unchanged_reference_' + name, (HERE / name).read_bytes() == (OLD / name).read_bytes())
    source = (HERE / 'native_tools.py').read_text(encoding='utf-8')
    check('new_public_session_identifier_only', 'm5-harness-recovery-001' in source and 'm5-task-consumption-001' not in source)
    pure = json.loads((HERE / 'MIGRATION_PURE.json').read_bytes())
    for row in pure['input_pins']:
        actual = pin(Path(row['path']))
        check('current_directed_control_source_' + Path(row['path']).name, actual['sha256'] == row['sha256'] and actual['bytes'] == row['bytes'])
    report = {'schema': 'm5-recovery-independent-source-check-v1',
        'passed_checked_scope': all(row['passed'] for row in checks), 'checks': checks,
        'check_count': len(checks), 'passed_count': sum(row['passed'] for row in checks),
        'input_pins': [pin(path) for path in (candidate, current, HERE / 'harness/budget.py', HERE / 'bridge.py',
            HERE / 'native_tools.py', HERE / 'MIGRATION_PURE.json', Path(__file__))],
        'author_association': 'Reviewer authored shared bridge migration. Another agent authored candidate runtime, budget and runtime migration. This check independently compares that runtime and discloses the bridge-author association.',
        'scope': 'AST/byte comparison only for changed context and required direct references. Existing historical matrices and old manifest members are referenced without rerunning or scanning.',
        'new_actual_operations': 0}
    with (HERE / 'INDEPENDENT_MIGRATION_SOURCE_CHECK.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': report['passed_checked_scope'], 'checks': len(checks),
        'failed': [row['name'] for row in checks if not row['passed']]}))
    if not report['passed_checked_scope']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
