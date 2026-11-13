"""Read-only preparation checks for the bounded continuous-consumption cycle.

This checker never launches a provider, Blender, Git, or another process. Its
output describes preparation evidence and does not score model performance.
"""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
CLI = Path('C:/Users/Administrator/.codex/packages/standalone/releases/'
           '0.152.1-x86_64-pc-windows-msvc/bin/codex.exe')
CLI_SHA = '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
PLAN_SHA = '95a334c39672a72ac771beba0f02e6c17735771a5e0f8411203d46e2769feba5'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def main():
    checks = []

    def check(name, condition, details=None):
        checks.append({'name': name, 'passed': bool(condition), 'details': details})

    plan = read(BATCH / 'PLAN.json')
    work = read(BATCH / 'WORK_ORDER.json')
    check('fixed_cycle', plan['cycle'] == 'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-001')
    check('root_plan_identity', digest(BATCH / 'inputs/ROOT_PLAN.md') == PLAN_SHA
          and plan['root_plan_sha256'] == PLAN_SHA)
    expected = ['N1', 'C1', 'C2', 'N2', 'N3', 'C3']
    check('six_fixed_serial_slots', [row['cell'] for row in plan['sequence']] == expected
          and len({row['anonymous_episode_id'] for row in plan['sequence']}) == 6
          and len({turn for row in plan['sequence'] for turn in row['anonymous_turn_ids']}) == 18)
    check('provider_gate_explicit_true', plan.get('model_consumer_enabled') is True)
    expected_limits = {
        'episode_seconds': 590, 'turn_seconds': 450, 'actor_startup_seconds': 40,
        'tool_timeout_seconds': 30, 'episode_tool_attempts': 32,
        'episode_host_nonclose_requests': 128, 'episode_tool_response_bytes': 1048576,
        'code_bytes': 262144, 'image_count': 0, 'new_images': 0,
    }
    check('fixed_budget_contract', all(type(plan.get(key)) is int and plan[key] == value
          for key, value in expected_limits.items()), expected_limits)
    check('unknown_usage_and_quality_seal', plan.get('quality_before_cost') is True
          and plan.get('usage_aggregation') is None
          and plan.get('usage_semantics') == 'unconfirmed_until_actual_resume_evidence')
    check('no_replacements_unavailable_stop', plan.get('replace_failed_episodes') is False
          and plan.get('stop_unavailable_or_unknown') is True)
    check('common_requested_service', plan['requested_model'] == 'gpt-6.1-sol'
          and plan['requested_effort'] == 'medium' and plan['service_tier'] == 'default')
    checksums = []
    for item in work['inputs']:
        path = BATCH / item['path']
        checksums.append({'path': item['path'], 'passed': path.stat().st_size == item['bytes']
                          and digest(path) == item['sha256']})
    check('seven_fixed_input_copies', len(checksums) == 7 and all(row['passed'] for row in checksums), checksums)
    base = (BATCH / 'inputs/PROMPT_T1.txt').read_bytes()
    recheck = (BATCH / 'inputs/PROMPT_T2_T3.txt').read_bytes()
    check('literal_recheck_prefix_only', recheck == '请重新检查当前场景。'.encode('utf8') + base)
    native = read(BATCH / 'inputs/COMMON_NATIVE.json')
    check('same_original_native_tool', native['name'] == 'execute_blender_code'
          and native == read(ROOT / 'verification/m4_surface_scan_continuity_001_fix1/inputs/COMMON_NATIVE.json'))
    product = read(BATCH / 'inputs/C_PUBLIC_TOOLS.json')
    check('only_ordinary_observe_addition', [row['name'] for row in product] == ['human_eye_scene_observe']
          and product == plan['read_schemas'])
    reused = read(BATCH / 'REUSE.json')['external_sha256']
    mismatches = [str(path) for path, expected_sha in reused.items()
                  if not Path(path).is_file() or digest(Path(path)) != expected_sha]
    check('frozen_reused_sources_unchanged', not mismatches,
          {'checked_files': len(reused), 'mismatches': mismatches})
    package = read(CLI.parent.parent / 'codex-package.json')
    cli_sha = digest(CLI)
    check('fixed_cli_binary_identity', package['version'] == '0.152.1' and cli_sha == CLI_SHA,
          {'bytes': CLI.stat().st_size, 'sha256': cli_sha})
    package_paths = [path.relative_to(CLI.parent.parent).as_posix()
                     for path in (CLI.parent.parent).rglob('*') if path.is_file()]
    source_files = [name for name in package_paths if Path(name).suffix in ('.rs', '.ts', '.js', '.py')]
    check('usage_scope_remains_unknown', not source_files,
          {'package_files': sorted(package_paths), 'implementation_source_found': source_files,
           'scope': 'Help and binary field strings do not establish turn.completed total/last selection.'})
    learning = work['learning_context']
    check('no_borrowed_learning_context', learning.get('context_bound') is False
          and learning.get('host_epoch') == 5 and learning.get('borrowed_handle') is False)
    driver = BATCH / 'runtime/driver.py'
    check('driver_available_for_separate_source_review', driver.is_file())
    if driver.is_file():
        ast.parse(driver.read_text(encoding='utf8'))
        spec = importlib.util.spec_from_file_location('_continuous_readonly_review_driver', driver)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        check('driver_pure_contract_accepts_fixed_plan', module.contract(plan)['planned_turns'] == 18)
        check('driver_original_clock_constants', module.EPISODE_NS == 590 * 10**9
              and module.TURN_NS == 450 * 10**9)
        entered = {'turns': [{'turn_index': 1, 'turn_label': 'BASE', 'folder': 'unused'}]}
        rows = module.execution_rows(entered)
        check('entered_exception_retains_three_slots', [row['execution_state'] for row in rows]
              == ['failed', 'not_run', 'not_run'])
        check('unknown_consumer_execution_stops_remaining', bool(module.stop_reasons({'coordinator': entered})))
        ordinary_failure = {'turns': [{'turn_label': 'BASE', 'consumer': {
            'valid_completion': False, 'errors': [{'type': 'Error', 'message': 'unparseable final'}],
            'summary': {'errors': []}, 'process_reaped': True, 'readers_stopped': True,
        }}]}
        check('ordinary_answer_failure_does_not_stop_batch',
              not module.stop_reasons({'coordinator': ordinary_failure}))
        rejected_cleanup = copy.deepcopy(ordinary_failure)
        rejected_cleanup['turns'][0]['consumer']['bridge_cleanup'] = {'confirmed': False}
        check('rejected_thin_cleanup_stops_remaining',
              bool(module.stop_reasons({'coordinator': rejected_cleanup})))
        unknown_exit_receipt = copy.deepcopy(ordinary_failure)
        unknown_exit_receipt['turns'][0]['consumer']['bridge_cleanup'] = {'confirmed': None}
        check('missing_thin_exit_keeps_existing_scope',
              not module.stop_reasons({'coordinator': unknown_exit_receipt}))
        structured_unavailable = copy.deepcopy(ordinary_failure)
        structured_unavailable['turns'][0]['consumer']['errors'] = [{'event': {'error': {'status': 429}}}]
        check('terminal_structured_unavailable_stops_remaining',
              bool(module.stop_reasons({'coordinator': structured_unavailable})))
        recovered = copy.deepcopy(structured_unavailable)
        recovered['turns'][0]['consumer'].update(turn_completed_ns=20, final_received_ns=21, exit_code=0)
        check('recovered_provider_retains_failure_without_unavailable_stop',
              not module.stop_reasons({'coordinator': recovered}))
        for name in ('pack_quality.py', 'check_package.py'):
            path = BATCH / 'quality_tools' / name
            check('quality_source_available_' + name, path.is_file())
            if path.is_file():
                ast.parse(path.read_text(encoding='utf8'))
    result = {
        'scope': 'Offline preparation only. Guard source review is documented separately. No execution or benefit claim.',
        'passed': all(row['passed'] for row in checks), 'checks': checks,
        'usage_aggregation': None, 'usage_scope': 'unknown',
        'driver_sha256': digest(driver) if driver.is_file() else None,
        'quality_sources_sha256': {name: digest(BATCH / 'quality_tools' / name)
                                  for name in ('pack_quality.py', 'check_package.py', 'SCORING_CONTRACT.json')
                                  if (BATCH / 'quality_tools' / name).is_file()},
        'checker_sha256': digest(Path(__file__)),
    }
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))


if __name__ == '__main__':
    main()
