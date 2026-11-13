"""Explicit new-batch entry for the frozen unified-result candidate."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import traceback


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'verification/m4_active_coverage_consumption_001'
CANDIDATE = ROOT / 'verification/m4_consumer_error_contract_001'
PROMPT_SHA256 = 'a063914f32409ef33015c50751ea96a5d7646a672d5570d5eb5c725154c62583'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                          encoding='utf8', newline='\n')


def load_candidate():
    spec = importlib.util.spec_from_file_location('_coverage_consumption_002_candidate', CANDIDATE / 'driver.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execution_sources(plan):
    old_frozen = read(OLD / 'FROZEN.json')
    sources = dict(old_frozen['runtime_sources'])
    if len(sources) != 176:
        raise ValueError('original_176_dependency_closure_required')
    candidate_frozen = read(CANDIDATE / 'FROZEN.json')['files_sha256']
    for name in ('consumer.py', 'driver.py', 'result_contract.py'):
        path = (CANDIDATE / name).resolve()
        sources[str(path)] = candidate_frozen[str(path)]
    for path, wanted in sources.items():
        if sha(path) != wanted:
            raise ValueError('readonly_execution_dependency_changed:' + path)
    for path in (OLD / 'FROZEN.json', CANDIDATE / 'FROZEN.json',
                 HERE / 'launcher.py', HERE / 'PLAN.json', HERE / 'fake_cli.py'):
        sources[str(path.resolve())] = sha(path)
    prompt = Path(plan['inputs']['prompt'])
    manifest = Path(plan['inputs']['input_manifest'])
    runtime = Path(plan['runtime_root'])
    if not prompt.is_absolute() or not manifest.is_absolute() or not runtime.is_absolute():
        raise ValueError('absolute_new_runtime_and_readonly_inputs_required')
    if prompt.resolve() != (OLD / 'inputs/PROMPT.txt').resolve() or sha(prompt) != PROMPT_SHA256:
        raise ValueError('unchanged_shared_prompt_binding')
    if manifest.resolve() != (OLD / 'inputs/SOURCES.json').resolve():
        raise ValueError('unchanged_shared_source_manifest_binding')
    if runtime.resolve() != (HERE / 'r').resolve():
        raise ValueError('fresh_new_batch_runtime_binding')
    if Path(plan['candidate_driver']).resolve() != (CANDIDATE / 'driver.py').resolve():
        raise ValueError('fixed_candidate_driver_binding')
    return sources


def frozen_sources(plan):
    sources = execution_sources(plan)
    for name in ('TRUTH.json', 'SCORING_SCHEMA.json'):
        path = HERE / 'admin' / name
        if path.read_bytes() != (OLD / 'admin' / name).read_bytes():
            raise ValueError('unchanged_quality_contract_required:' + name)
    for path in (HERE / 'admin/TRUTH.json', HERE / 'admin/SCORING_SCHEMA.json',
                 HERE / 'admin/score_answers.py', HERE / 'admin/DISPATCH_PLAN.md'):
        sources[str(path.resolve())] = sha(path)
    interface_path = OLD.parent / 'm4_surface_scan_continuity_001/cli/CLI_INTERFACE.json'
    interface = read(interface_path)
    executable = Path(interface['executable']).resolve()
    if sha(executable) != interface['executable_sha256']:
        raise ValueError('fixed_actual_CLI_changed')
    sources[str(executable)] = interface['executable_sha256']
    base = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
    wanted = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
    if sha(base) != wanted:
        raise ValueError('fixed_actual_base_changed')
    sources[str(base.resolve())] = wanted
    sources[str((OLD / 'admin/score_answers.py').resolve())] = sha(OLD / 'admin/score_answers.py')
    return sources


def pointers(driver):
    consumer = driver.consumer
    checks = {
        'batch_to_route': driver.run_batch.__globals__['run_route'] is driver.run_route,
        'route_to_consumer': driver.run_route.__globals__['consumer'] is consumer,
        'route_to_common_check': driver.run_route.__globals__['common_image_faults'] is driver.common_image_faults,
        'consume_to_archive': consumer.consume_turn.__globals__['archive_turn'] is consumer.archive_turn,
        'batch_code_unchanged': driver.run_batch.__code__ is driver.legacy.run_batch.__code__,
        'route_code_unchanged': driver.run_route.__code__ is driver.legacy.run_route.__code__,
        'consume_code_unchanged': consumer.consume_turn.__code__ is consumer.legacy.consume_turn.__code__,
        'original_archive_pointer_unchanged': consumer.legacy.consume_turn.__globals__['archive_turn'] is consumer.legacy.archive_turn,
        'original_route_consumer_unchanged': driver.legacy.run_route.__globals__['consumer'] is driver.legacy.consumer,
        'original_route_check_unchanged': driver.legacy.run_route.__globals__['common_image_faults'] is driver.legacy.common_image_faults,
        'original_batch_route_unchanged': driver.legacy.run_batch.__globals__['run_route'] is driver.legacy.run_route,
        'same_safe_environment': consumer.safe_environment is consumer.legacy.safe_environment,
        'same_outer_gate': driver.outer_accepted is driver.legacy.outer_accepted,
    }
    if not all(checks.values()):
        raise ValueError('candidate_runtime_pointer_chain_changed')
    return {'checks': checks, 'candidate_driver': str(CANDIDATE / 'driver.py'),
            'candidate_consumer': str(CANDIDATE / 'consumer.py'),
            'candidate_matcher': str(CANDIDATE / 'result_contract.py'),
            'inherited_batch_code': driver.run_batch.__code__.co_filename,
            'inherited_route_code': driver.run_route.__code__.co_filename,
            'inherited_consume_code': consumer.consume_turn.__code__.co_filename}


def check_local_result(row):
    record = read(Path(row['consumer_output']) / 'CONSUMER.json')
    calls = record['tool_calls']
    contracts = record['archive']['result_contracts']
    checks = {'outer_accepted': row['outer_valid_completion'] is True,
              'safe_to_continue': record['safe_to_continue'] is True,
              'exact_two_tools': len(calls) == 2,
              'matched_error_then_success': [value['classification'] for value in contracts] == ['tool_error', 'success']
                  and all(value['matched'] for value in contracts),
              'ordinary_EOF_confirmed': record['bridge_cleanup']['confirmed'] is True,
              'runtime_exit_zero': record['runtime_exit']['confirmed'] is True and record['runtime_exit']['exit_code'] == 0,
              'zero_image_constructions': row['owner_metrics']['constructed_image_blocks'] == 0,
              'zero_delivered_images': record['public_image_count'] == 0,
              'zero_render_attempts': row['new_renders'] == 0}
    if len(calls) == 2:
        items = [call['item'] for call in calls]
        first = json.loads(items[0]['result']['content'][0]['text'])
        second = json.loads(items[1]['result']['content'][0]['text'])
        checks.update({
            'actual_ValueError': (first.get('error') or {}).get('type') == 'ValueError',
            'actual_recovery_42': second.get('stdout') == '42\n' and second.get('error') is None,
            'actual_CLI_failed_completed': [item['status'] for item in items] == ['failed', 'completed'],
            'actual_CLI_error_null': all('error' in item and item['error'] is None for item in items),
            'actual_known_projection': all(set(item['result']) == {'content', 'structured_content'}
                and item['result']['structured_content'] is None for item in items),
        })
    return {'passed': all(checks.values()), 'checks': checks}


def run_local(driver, plan, group):
    local = HERE / 'local'
    local.mkdir(exist_ok=True)
    previous = local / (group + '1')
    attempt = 1
    if previous.exists():
        result = read(previous / 'LOCAL_RESULT.json')
        if result['passed'] is not False:
            raise ValueError('passed_local_group_cannot_be_repeated')
        attempt = 2
    folder = local / (group + str(attempt))
    folder.mkdir(exist_ok=False)
    began = time.perf_counter_ns()
    before_sources = execution_sources(plan)
    before = pointers(driver)
    save(folder / 'POINTERS_BEFORE.json', before)
    base = driver.legacy.launch.BASE
    fixture = HERE / 'fake_cli.py'
    row = driver.run_route('LOCAL_' + group + str(attempt), group, plan, folder,
        local_cli={'command': [str(base), '-I', '-B', str(fixture)], 'script_sha256': sha(fixture)})
    try:
        checks = check_local_result(row)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        checks = {'passed': False, 'checks': {'local_readback_completed': False},
                  'readback_error': {'type': type(error).__name__, 'message': str(error),
                                     'traceback': traceback.format_exc()}}
    after = pointers(driver)
    after_sources = execution_sources(plan)
    save(folder / 'POINTERS_AFTER.json', after)
    result = {'schema': 'active-coverage-consumption-002-local-v1', 'group': group, 'attempt': attempt,
              'passed': checks['passed'] and before == after and before_sources == after_sources,
              'checks': checks['checks'], 'readback_error': checks.get('readback_error'),
              'route': row, 'execution_sources_sha256': before_sources,
              'source_unchanged': before_sources == after_sources, 'pointer_chain_unchanged': before == after,
              'started_ns': began, 'before_result_publication_ns': time.perf_counter_ns(),
              'new_Pro_sessions': 0,
              'new_image_constructions': (row.get('owner_metrics') or {}).get('constructed_image_blocks'),
              'new_renders': row.get('new_renders'), 'scope': 'Actual fake CLI/actor/stdio error-to-recovery pipeline, with ordinary EOF.'}
    save(folder / 'LOCAL_RESULT.json', result)
    return result


def require_local_qualification(plan):
    current = execution_sources(plan)
    selected = []
    for group in ('N', 'P'):
        folders = [HERE / 'local' / (group + str(attempt)) for attempt in (1, 2)]
        existing = [folder for folder in folders if folder.exists()]
        if not existing:
            raise ValueError('both_groups_require_local_error_recovery_check')
        result = read(existing[-1] / 'LOCAL_RESULT.json')
        if result['passed'] is not True or result['execution_sources_sha256'] != current:
            raise ValueError('local_qualification_missing_or_execution_sources_changed:' + group)
        selected.append({'group': group, 'path': str(existing[-1] / 'LOCAL_RESULT.json'),
                         'sha256': sha(existing[-1] / 'LOCAL_RESULT.json'), 'attempts': len(existing)})
    return selected


def check_frozen(plan):
    path = HERE / 'FROZEN.json'
    frozen = read(path)
    if frozen['files_sha256'] != frozen_sources(plan):
        raise ValueError('new_batch_frozen_execution_or_scoring_sources_changed')
    return frozen


def main():
    began = time.perf_counter_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--freeze', action='store_true')
    modes.add_argument('--check-local', action='store_true')
    modes.add_argument('--run-models', action='store_true')
    parser.add_argument('--group', choices=('N', 'P'))
    options = parser.parse_args()
    plan = read(HERE / 'PLAN.json')
    if options.freeze:
        value = {'schema': 'active-coverage-consumption-002-source-freeze-v1',
                 'baseline_git': plan['baseline_commit'], 'files_sha256': frozen_sources(plan),
                 'old_dependency_count': 176, 'candidate_source_count': 3,
                 'prompt_sha256': PROMPT_SHA256, 'frozen_ns': time.perf_counter_ns()}
        with (HERE / 'FROZEN.json').open('x', encoding='utf8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        print(json.dumps({'frozen': True, 'files': len(value['files_sha256'])}))
        return
    execution_sources(plan)
    driver = load_candidate()
    pointers(driver)
    if options.check_local:
        if options.group is None:
            raise ValueError('one_explicit_group_per_local_invocation')
        result = run_local(driver, plan, options.group)
        print(json.dumps({'group': options.group, 'attempt': result['attempt'], 'passed': result['passed'],
                          'new_Pro_sessions': 0, 'new_renders': result['new_renders']}))
        if not result['passed']:
            raise SystemExit(1)
        return
    frozen = check_frozen(plan)
    if not options.run_models:
        print(json.dumps({'source_unchanged': True, 'files': len(frozen['files_sha256']), 'model_sessions_started': 0}))
        return
    qualification = require_local_qualification(plan)
    if plan.get('model_consumer_enabled') is not True:
        raise ValueError('model_execution_not_enabled')
    with (HERE / 'FORMAL_STARTED.json').open('x', encoding='utf8') as stream:
        json.dump({'started_ns': time.perf_counter_ns(), 'freeze_sha256': sha(HERE / 'FROZEN.json'),
                   'local_qualification': qualification}, stream, ensure_ascii=False, indent=2)
    runtime = Path(plan['runtime_root']).resolve()
    runtime.mkdir(exist_ok=False)
    before = pointers(driver)
    save(runtime / 'POINTERS_BEFORE.json', before)
    try:
        result = driver.run_batch(plan, runtime)
    finally:
        after = pointers(driver)
        save(runtime / 'POINTERS_AFTER.json', after)
        check_frozen(plan)
        if before != after:
            raise ValueError('candidate_pointer_chain_changed_during_batch')
    save(runtime / 'LAUNCH_RESULT.json', {'schema': 'active-coverage-consumption-002-launch-v1',
         'freeze_sha256': sha(HERE / 'FROZEN.json'), 'source_unchanged': True,
         'local_qualification': qualification, 'pointer_chain_unchanged': before == after,
         'actual_routes': result['actual_routes'],
         'started_ns': began, 'before_launch_result_publication_ns': time.perf_counter_ns()})
    closed = time.perf_counter_ns()
    save(runtime / 'LAUNCH_TIMING.json', {'started_ns': began, 'LAUNCH_RESULT_closed_ns': closed,
         'elapsed_ns': closed - began,
         'scope': 'Launcher main entry through source/local qualification, fixed six-slot batch, final pointer/source readback and launch-result publication. Interpreter startup is outside this interval.'})
    print(json.dumps({'actual_routes': result['actual_routes'],
        'execution_counts': {state: sum(row['execution_state'] == state for row in result['records'])
                             for state in ('completed', 'failed', 'not_run')}}))


if __name__ == '__main__':
    main()
