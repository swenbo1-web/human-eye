"""Small read-only FIX2 contract review, with leaf checks on frozen records."""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
RUNNER = BATCH / 'engineering/run_candidate.py'
FIX1 = ROOT / 'verification/m4_surface_scan_continuity_001_fix1'


def read(path):
    return json.loads(path.read_bytes())


def main():
    labels = []

    def check(condition, label):
        assert condition, label
        labels.append(label)

    def rejected(action, reason, label):
        try:
            action()
        except AssertionError as error:
            check(str(error) == reason, label)
        else:
            raise AssertionError(label + '_accepted')

    shared = read(HERE / 'SHARED_BYTES.json')
    for row in shared['shared_files']:
        raw = (ROOT / row['path']).read_bytes()
        check(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'shared_current_' + row['path'])
        expected = subprocess.check_output(['git', 'show', shared['baseline_commit'] + ':' + row['path']], cwd=ROOT)
        check(raw == expected, 'shared_Git_' + row['path'])
    for row in shared['installed_fixed_profile_records']:
        raw = Path(row['path']).read_bytes()
        check(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'fixed_install_' + row['path'])

    source = RUNNER.read_bytes()
    tree = ast.parse(source.decode('utf8'))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    check('qualify_after_finish' in functions and 'publish_result' in functions, 'separate_postclose_and_publication')
    run = functions['run_episode']
    finishes = [node for node in ast.walk(run) if isinstance(node, ast.Call) and ast.unparse(node.func) == 'driver.finish']
    postclose = [node for node in ast.walk(run) if isinstance(node, ast.Call) and ast.unparse(node.func) == 'qualify_after_finish']
    check(len(finishes) == len(postclose) == 1 and finishes[0].lineno < postclose[0].lineno, 'single_finish_before_qualification')
    outer = next(node for node in run.body if isinstance(node, ast.Try))
    final_lines = {node.lineno for statement in outer.finalbody for node in ast.walk(statement) if hasattr(node, 'lineno')}
    check(finishes[0].lineno in final_lines and postclose[0].lineno in final_lines, 'finish_and_qualification_in_finally')
    qualify = ast.unparse(functions['qualify_after_finish'])
    check("result.get('cleanup', {}).get('confirmed') is True" in qualify, 'postclose_requires_confirmed_finish')
    check(qualify.index('verify_terminal_wire(') < qualify.index('verify_business('), 'terminal_wire_before_rows')
    check("sources[row['state']]" in qualify, 'state_specific_qualification_source')
    ended_writes = [node for node in ast.walk(functions['qualify_after_finish'])
                    if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store)
                    and isinstance(node.slice, ast.Constant) and node.slice.value == 'ended_ns']
    check(not ended_writes, 'qualification_preserves_original_business_end')
    run_source = ast.unparse(run)
    check("sources['BASE'] = read(folder / 'owner/INITIAL.json')" in run_source, 'initial_source_retained')
    check("sources['EDIT'] = result['registered_pose']['snapshot']" in run_source, 'registered_edit_source_retained')
    check("deadline = started + 590 * 10 ** 9" in run_source, 'one_original_590s_deadline')
    business = ast.unparse(functions['verify_business'])
    check("event['started_ns'] + event['elapsed_ns'] <= row['ended_ns']" in business, 'host_complete_window_uses_elapsed')
    check("event['ended_ns']" not in business, 'no_new_host_end_field')
    main_source = ast.unparse(functions['main'])
    check("FIX1 / 'runtime/consumer_transport.py'" in main_source and "FIX1 / 'qualification/verify_continuity.py'" in main_source, 'fixed_consumer_and_qualification_references')
    check("FIX1 / 'runtime/actor.py'" in run_source, 'fixed_actor_reference')
    validate = ast.unparse(functions['validate_preparation'])
    check("preparation.relative_to(ROOT).as_posix()" in validate and "m4_surface_scan_continuity_001_fix2" in validate,
          'current_batch_dynamic_preparation_path')

    spec = importlib.util.spec_from_file_location('_FIX2_contract_runner', RUNNER)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    actual = read(FIX1 / 'episodes/C/TURN_BASE.json')['body']
    runner.validate_online_body(actual)
    check(True, 'real_complete_online_receipt')
    cases = [
        ('status', 'unknown', 'online_observe_not_complete'),
        ('status', 'partial', 'online_observe_not_complete'),
        ('scope_issues', ['unresolved'], 'online_scope_unresolved'),
        ('unsupported_objects', ['mesh'], 'online_scope_unresolved'),
        ('unresolved', ['pair'], 'online_scope_unresolved'),
    ]
    for key, value, reason in cases:
        changed = copy.deepcopy(actual)
        changed[key] = value
        rejected(lambda: runner.validate_online_body(changed), reason, 'reject_online_' + key + '_' + str(value))
    for key, value, reason in (('unknown', 1, 'online_coverage_unresolved'),
                               ('deferred', 1, 'online_coverage_unresolved'),
                               ('unknown', False, 'online_coverage_unresolved'),
                               ('catalog_scope_confirmed', False, 'online_catalog_scope_unconfirmed')):
        changed = copy.deepcopy(actual)
        changed['coverage'][key] = value
        rejected(lambda: runner.validate_online_body(changed), reason, 'reject_coverage_' + key + '_' + str(value))
    changed = copy.deepcopy(actual)
    changed['delivery']['complete'] = False
    rejected(lambda: runner.validate_online_body(changed), 'online_delivery_incomplete', 'reject_partial_delivery')
    folder = FIX1 / 'episodes/C'
    wire_check = runner.verify_terminal_wire(folder)
    check(wire_check['passed'] and wire_check['closed_frame_verified'], 'real_closed_wire_complete')
    index = read(folder / 'owner/native/WIRE/INDEX.json')
    for field, value, reason in (('response_sendall_completed', False, 'terminal_WIRE_send_unconfirmed'),
                                  ('request_bytes', -1, 'terminal_WIRE_request_size'),
                                  ('sequence', 2, 'terminal_WIRE_sequence')):
        changed = copy.deepcopy(index)
        changed[0][field] = value
        with patch.object(runner, 'read', return_value=changed):
            rejected(lambda: runner.verify_terminal_wire(folder), reason, 'reject_wire_' + field)

    result = {'schema': 'FIX2_source_contract_review_v1', 'passed': True, 'checks': len(labels), 'labels': labels,
              'runner_sha256': hashlib.sha256(source).hexdigest(), 'shared_source_files': len(shared['shared_files']),
              'fixed_install_records': len(shared['installed_fixed_profile_records']),
              'scope': 'Source control-flow review and small pure checks using fixed closed records. Full integration and real runtime are separate evidence.',
              'new_Blender_product_model_API_runs': 0, 'Git_mutations': 0}
    (HERE / 'CONTRACT_RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({key: result[key] for key in ('passed', 'checks', 'shared_source_files', 'fixed_install_records', 'new_Blender_product_model_API_runs')}))


if __name__ == '__main__':
    main()
