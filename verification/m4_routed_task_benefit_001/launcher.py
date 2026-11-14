"""Six serial routed/native slots with one common complete slot clock.

Import performs no connection, product work, CLI invocation or rendering.
Only the root starts the frozen formal batch.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import types


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREVIOUS = HERE.with_name('m4_consumable_observation_001')
OLD = HERE.with_name('m4_region_localization_consumption_001')
EXTERNAL = Path('D:/he_routed_001')
PREVIOUS_FREEZE_SHA256 = '7b239d6a6416d4250750d7b7443a6df09ca166ff59040d4ab74f5b883caf1cd1'
PRODUCT_SHA256 = '6d4f7d363aaa48081eff7db467fff20665419172560f19b3a4ccb0fbb46c900f'
SUFFIX_SHA256 = '3f848a42070580ad479e3de6507b9ffe09c59b9651c784c17608f0d752c1205a'
SEQUENCE = [('N1', 'N'), ('P1', 'P'), ('P2', 'P'), ('N2', 'N'), ('N3', 'N'), ('P3', 'P')]
PREFIXES = {
    'N': b'For this comparison, begin with whichever available native entry is most efficient. Reuse current-session evidence and computed facts; obtain additional evidence only when it is missing or inconsistent. Complete the task below within this turn.',
    'P': b'For this comparison, begin with active_observation(include_images=true). Reuse current-session evidence and computed facts; obtain additional evidence only when it is missing or inconsistent. Complete the task below within this turn.'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value, exclusive=False):
    with Path(path).open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def error_record(error, phase):
    return {'phase': phase, 'type': type(error).__name__, 'message': str(error),
            'traceback': ''.join(traceback.format_exception(type(error), error, error.__traceback__))}


def previous_launcher():
    path = PREVIOUS / 'FROZEN.json'
    if sha(path) != PREVIOUS_FREEZE_SHA256:
        raise ValueError('accepted_previous_freeze_changed')
    source = (PREVIOUS / 'launcher.py').resolve()
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != read(path)['files_sha256'][str(source)]:
        raise ValueError('accepted_previous_launcher_changed')
    module = types.ModuleType('_routed_accepted_consumable_launcher')
    module.__file__ = str(source)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(source), 'exec', dont_inherit=True), module.__dict__)
    return module


def input_checks(plan, group=None):
    if (plan['schema'] != 'routed-task-benefit-001-plan-v1'
            or [(row['slot'], row['group']) for row in plan['sequence']] != SEQUENCE
            or plan['formal_batch_attempts'] != 1):
        raise ValueError('fixed_six_fresh_slot_order')
    if (plan['route_deadline_seconds'], plan['max_tool_calls'], plan['max_render_attempts'],
            plan['preparation_render_cap'], plan['formal_render_cap'], plan['total_new_render_cap']) != (450, 12, 6, 0, 36, 36):
        raise ValueError('fixed_route_and_batch_limits')
    if (plan['requested_model'], plan['requested_reasoning_effort'], plan['requested_service_tier']) != ('gpt-6.1-sol', 'medium', 'default'):
        raise ValueError('unchanged_requested_CLI_profile')
    if (Path(plan['external_root']).resolve() != EXTERNAL
            or Path(plan['runtime_root']).resolve() != EXTERNAL / 'formal'):
        raise ValueError('new_external_runtime_required')
    manifest_path = Path(plan['inputs']['input_manifest']).resolve()
    if not manifest_path.is_relative_to(HERE):
        raise ValueError('new_batch_manifest_required')
    suffix = HERE / 'inputs/PROMPT_SUFFIX.txt'
    original = OLD / 'inputs/PROMPT.txt'
    if sha(suffix) != SUFFIX_SHA256 or sha(original) != SUFFIX_SHA256 or suffix.read_bytes() != original.read_bytes():
        raise ValueError('byteexact_common_suffix_required')
    sources = {str(path.resolve()): sha(path) for path in (manifest_path, suffix, original)}
    prompts = {}
    for arm in ('N', 'P'):
        prefix = HERE / ('inputs/PREFIX_' + arm + '.txt')
        prompt = Path(plan['inputs']['prompts'][arm]).resolve()
        if (not prompt.is_relative_to(HERE) or prefix.read_bytes() != PREFIXES[arm]
                or prompt.read_bytes() != PREFIXES[arm] + b'\n\n' + suffix.read_bytes()
                or sha(prompt) != plan['expected_prompt_sha256'][arm]):
            raise ValueError('registered_entry_prefix_and_common_task_' + arm)
        prompts[arm] = prompt.read_bytes()
        sources.update({str(prefix.resolve()): sha(prefix), str(prompt): sha(prompt)})
    manifest = read(manifest_path)
    previous_path = PREVIOUS / 'inputs/SOURCES.json'
    previous = read(previous_path)
    if (manifest['schema'] != previous['schema'] or manifest['replay_label'] != 'CAPTURE_REPLAY'
            or manifest['public_surface_color_rgb'] != previous['public_surface_color_rgb']):
        raise ValueError('unchanged_public_source_schema_color')
    for name in ('capture', 'scene', 'cameras', 'product_binding'):
        specification = manifest[name]
        path = Path(specification['path']).resolve()
        old_specification = previous[name]
        if (path != Path(old_specification['path']).resolve()
                or sha(path) != specification['sha256']
                or specification['sha256'] != old_specification['sha256']):
            raise ValueError('same_readonly_source_' + name)
        sources[str(path)] = specification['sha256']
    binding = read(manifest['product_binding']['path'])
    if (binding['source_sha256'] != PRODUCT_SHA256
            or plan['product_source_sha256'] != PRODUCT_SHA256
            or Path(binding['install_root']).resolve() != Path('D:/he_consume_001/product')):
        raise ValueError('unchanged_accepted_candidate_installation')
    budget = manifest['budget_contract']
    if (Path(budget['external_root']).resolve() != EXTERNAL
            or Path(budget['formal_root']).resolve() != EXTERNAL / 'formal'
            or Path(budget['preparation_root']).resolve() != EXTERNAL / 'preparation'
            or Path(budget['ledger_root']).resolve() != EXTERNAL / 'raster_budget'
            or (budget['formal_cap'], budget['preparation_cap'], budget['per_slot_cap'], budget['total_cap']) != (36, 0, 6, 44)):
        raise ValueError('new_36_raster_formal_phase_with_legacy_container')
    if group is not None and group not in prompts:
        raise ValueError('registered_group_required')
    return None if group is None else prompts[group], manifest_path, sources


def source_file_list(plan):
    previous_launcher()
    sources = dict(read(PREVIOUS / 'FROZEN.json')['files_sha256'])
    sources[str((PREVIOUS / 'FROZEN.json').resolve())] = PREVIOUS_FREEZE_SHA256
    sources.update(input_checks(plan)[2])
    paths = [HERE / 'PLAN.json', HERE / 'DESIGN_LAUNCHER.md', HERE / 'PLAN.md']
    paths.extend(HERE.glob('*.py'))
    paths.extend((HERE / 'inputs').glob('*'))
    paths.extend((HERE / 'admin').glob('*.py'))
    paths.extend((HERE / 'admin').glob('*.json'))
    paths.extend((HERE / 'admin').glob('*.md'))
    for path in paths:
        if path.is_file():
            sources[str(path.resolve())] = sha(path)
    for path, wanted in sources.items():
        if sha(path) != wanted:
            raise ValueError('execution_dependency_changed:' + path)
    return sources


def verify_frozen(sources):
    frozen = read(HERE / 'FROZEN.json')
    if any(frozen['files_sha256'].get(path) != wanted for path, wanted in sources.items()):
        raise ValueError('required_source_missing_from_new_freeze')
    for path, wanted in frozen['files_sha256'].items():
        if sha(path) != wanted:
            raise ValueError('new_frozen_source_changed:' + path)
    return frozen


def function_description(function):
    return {'source_path': function.__code__.co_filename, 'qualname': function.__qualname__,
            'module': function.__module__, 'source_sha256': sha(function.__code__.co_filename)}


def connect_slot(plan, slot, group):
    previous = previous_launcher()
    old = previous.old_launcher()
    driver = old.connect(plan, 'formal')
    accepted_route = driver.run_route
    accepted_launch = accepted_route.__globals__['launch']

    def python_command(entry, arguments):
        if Path(entry).resolve() != (HERE / 'actor.py').resolve():
            raise ValueError('registered_new_route_actor_alias')
        command = accepted_launch.python_command(OLD / 'actor.py', arguments)
        config_path = Path(arguments[arguments.index('--config') + 1])
        config = read(config_path)
        if (config['group'] != group or config['phase'] != 'formal' or config['phase_render_cap'] != 36
                or config['whole_render_cap'] != 44 or config['max_render_attempts'] != 6
                or Path(config['output']).resolve() != EXTERNAL / 'formal' / slot / 'o'
                or Path(config['budget_root']).resolve() != EXTERNAL / 'raster_budget'
                or Path(command[5]).resolve() != (OLD / 'bootstrap.py').resolve()
                or Path(command[6]).resolve() != (OLD / 'bridge.py').resolve()):
            raise ValueError('accepted_command_before_new_batch_paths')
        command[5:7] = [str(HERE / 'bootstrap.py'), str(HERE / 'bridge.py')]
        return command

    def slot_input_checks(value):
        return input_checks(value, group)

    launch = types.SimpleNamespace(BASE=accepted_launch.BASE, BASE_SHA256=accepted_launch.BASE_SHA256,
                                   stop_process=accepted_launch.stop_process, python_command=python_command)
    route = old.clone(accepted_route, {'HERE': HERE, 'input_checks': slot_input_checks, 'launch': launch})
    consumer = driver.consumer
    common = route.__globals__['common_image_faults']
    retained = {'old_connect': old.connect, 'accepted_route': accepted_route, 'slot_route': route,
                'consumer': consumer.consume_turn, 'archive': consumer.archive_turn,
                'matcher': consumer.result_contract.bind_tool_result,
                'cleanup': accepted_launch.stop_process, 'common': common}
    codes = {name: function.__code__ for name, function in retained.items()}

    def pointer_proof():
        current = {'old_connect': old.connect, 'accepted_route': driver.run_route, 'slot_route': route,
                   'consumer': consumer.consume_turn, 'archive': consumer.archive_turn,
                   'matcher': consumer.result_contract.bind_tool_result,
                   'cleanup': launch.stop_process, 'common': route.__globals__['common_image_faults']}
        checks = {name + '_same_function_and_code_reference': current[name] is function
                  and current[name].__code__ is codes[name] for name, function in retained.items()}
        checks.update({
            'slot_route_code_is_accepted_route_code': route.__code__ is accepted_route.__code__,
            'slot_route_consumer_is_accepted_consumer': route.__globals__['consumer'] is consumer,
            'slot_route_uses_registered_input_check': route.__globals__['input_checks'] is slot_input_checks,
            'slot_route_uses_new_path_namespace': route.__globals__['HERE'] == HERE,
            'slot_route_uses_new_command': route.__globals__['launch'] is launch,
            'consumer_archive_is_unified_accepted_archive': consumer.consume_turn.__globals__['archive_turn'] is retained['archive'],
            'archive_uses_retained_matcher': consumer.archive_turn.__globals__['result_contract'].bind_tool_result is retained['matcher'],
            'old_route_globals_not_mutated': accepted_route.__globals__['launch'] is accepted_launch})
        if not all(checks.values()):
            raise ValueError('actual_accepted_route_pointer_chain')
        return {'schema': 'routed-task-entry-pointer-proof-v1', 'slot': slot, 'group': group,
                'checks': checks, 'functions': {name: function_description(function) for name, function in current.items()},
                'accepted_connect_time_snapshot': driver.pointers,
                'snapshot_scope': 'Inherited eight booleans were evaluated inside accepted connect; current checks above are evaluated at this receipt.',
                'accepted_previous_freeze_sha256': PREVIOUS_FREEZE_SHA256,
                'selected_prompt_sha256': plan['expected_prompt_sha256'][group],
                'command_adjustment': 'New batch bootstrap and bridge paths; original CLI/consumer/archive/cleanup code objects and formal36/container44/per6 retained.',
                'old_run_batch_called': False, 'old_main_called': False}

    return route, pointer_proof


def run_slot(plan, slot, group, runtime):
    started = time.perf_counter_ns()
    metadata = runtime / 'slot_records' / slot
    record = None
    route_invoked = False
    sources = None
    pointer_proof = None
    terminal = []
    publication_errors = []
    source_unchanged = None
    after = None
    try:
        metadata.mkdir(parents=True, exist_ok=False)
        sources = source_file_list(plan)
        verify_frozen(sources)
        route, pointer_proof = connect_slot(plan, slot, group)
        save(metadata / 'ENTRY_PROOF_BEFORE.json', pointer_proof(), exclusive=True)
        route_invoked = True
        record = route(slot, group, plan, runtime)
    except BaseException as error:
        terminal.append(error_record(error, 'slot_entry_or_route'))
    finally:
        if pointer_proof is not None:
            try:
                after = pointer_proof()
                save(metadata / 'ENTRY_PROOF_AFTER.json', after, exclusive=True)
            except BaseException as error:
                terminal.append(error_record(error, 'entry_reference_check'))
        if sources is not None:
            try:
                verify_frozen(sources)
                source_unchanged = source_file_list(plan) == sources
                if not source_unchanged:
                    raise ValueError('source_changed_during_slot')
            except BaseException as error:
                source_unchanged = False
                terminal.append(error_record(error, 'source_byte_check'))
        if record is None:
            record = {'slot': slot, 'group': group, 'outer_valid_completion': False,
                      'errors': [], 'stop_remaining_reasons': []}
        record['execution_state'] = 'completed' if record.get('outer_valid_completion') is True else 'failed'
        record['route_invoked'] = route_invoked
        record['slot_wrapper_errors'] = terminal
        record['stop_remaining_reasons'] = list(record.get('stop_remaining_reasons', []))
        result = {'schema': 'routed-task-slot-result-v1', 'slot': slot, 'group': group,
                  'started_ns': started, 'route_invoked': route_invoked, 'route': record,
                  'source_unchanged': source_unchanged, 'pointer_after': after,
                  'terminal_errors': terminal}
        try:
            save(metadata / 'SLOT_RESULT.json', result, exclusive=True)
        except BaseException as error:
            publication_errors.append(error_record(error, 'publish_SLOT_RESULT'))
        closed = time.perf_counter_ns()
        timing = {'schema': 'routed-task-complete-slot-clock-v1', 'slot': slot, 'group': group,
                  'started_ns': started, 'SLOT_RESULT_closed_ns': closed, 'elapsed_ns': closed - started,
                  'route_invoked': route_invoked, 'publication_errors': list(publication_errors),
                  'scope': 'Same wrapper for N/P, starting before per-slot directory/source/input checks and connection construction, through one accepted route, consumer/process cleanup/archive, post-source/reference checks and independent SLOT_RESULT write/fsync/close. This SLOT_TIMING receipt publication and later aggregate writes excluded.'}
        try:
            save(metadata / 'SLOT_TIMING.json', timing, exclusive=True)
        except BaseException as error:
            publication_errors.append(error_record(error, 'publish_SLOT_TIMING'))
        record['slot_wrapper_publication_errors'] = publication_errors
        record['slot_timing'] = {'path': str(metadata / 'SLOT_TIMING.json'), **timing}
        if publication_errors:
            record['slot_wrapper_errors'].extend(publication_errors)
    return record


def batch_blockers(record):
    """Keep original slot validity separate from safe fresh-slot scheduling."""
    blockers = list(record.get('common_image_faults', []))
    if record.get('errors'):
        blockers.append({'reason': 'accepted_route_infrastructure_exception', 'errors': record['errors']})
    if record.get('slot_wrapper_errors'):
        blockers.append({'reason': 'slot_entry_route_or_postcheck_exception', 'errors': record['slot_wrapper_errors']})
    if record.get('input_readback_unchanged') is not True:
        blockers.append({'reason': 'shared_input_source_unknown_or_changed'})
    for key in ('owner_process_cleanup', 'consumer_process_cleanup'):
        cleanup = record.get(key) or {}
        if cleanup.get('confirmed') is not True or cleanup.get('reaped') is not True or cleanup.get('process_handle_closed') is not True:
            blockers.append({'reason': key + '_actual_terminal_state_unknown'})
    if record.get('owner_close_confirmed') is not True:
        blockers.append({'reason': 'owner_service_close_unconfirmed'})
    if (record.get('runtime_binding') or {}).get('confirmed') is not True:
        blockers.append({'reason': 'thin_actual_process_binding_unknown'})
    runtime_exit = record.get('runtime_exit') or {}
    if runtime_exit.get('confirmed') is not True or runtime_exit.get('handle_closed') is not True:
        blockers.append({'reason': 'thin_actual_terminal_state_unknown'})
    if (record.get('bridge_cleanup') or {}).get('confirmed') is False:
        blockers.append({'reason': 'thin_protocol_receipt_rejected'})
    for original in record.get('stop_remaining_reasons', []):
        if original.get('reason') == 'terminal_service_or_account_unavailable':
            blockers.append(original)
    # A missing thin EXIT receipt with a confirmed retained-handle exit is
    # already supported by the accepted route. Quality or safe_to_continue
    # flags alone do not establish that a fresh process is unsafe to start.
    return blockers


def aggregate(records, started):
    return {'schema': 'routed-task-benefit-six-route-v1', 'records': records,
            'planned_routes': 6, 'planned_user_turns': 6,
            'actual_routes': sum(row.get('route_invoked') is True for row in records),
            'route_invocations_unknown': sum(row.get('route_invoked') is None for row in records),
            'actual_CLI_processes': sum(row.get('consumer_pid') is not None for row in records),
            'observed_fresh_threads': [row['observed_thread_id'] for row in records if row.get('observed_thread_id')],
            'maximum_tools_per_route': 12, 'maximum_render_attempts_per_route': 6,
            'maximum_formal_raster_attempts': 36, 'preparation_raster_attempts': 0,
            'outer_retries': 0, 'provider_internal_raw_requests': None, 'fees': None,
            'content_quality': 'unscored', 'Blender_processes': 0, 'paid_API_calls': 0,
            'started_ns': started, 'before_publication_ns': time.perf_counter_ns()}


def run_formal(plan, preparation_git):
    started = time.perf_counter_ns()
    runtime = EXTERNAL / 'formal'
    runtime.mkdir(parents=True, exist_ok=False)
    context = {'preparation_git': preparation_git, 'freeze_sha256': None}
    records = []
    stopped = None
    terminal = []
    publication_errors = []
    result = None
    try:
        sources = source_file_list(plan)
        verify_frozen(sources)
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
        if head.returncode or head.stdout.strip() != preparation_git:
            raise ValueError('fixed_preparation_commit_required')
        if plan.get('model_consumer_enabled') is not True:
            raise ValueError('explicit_formal_provider_entry_flag_required')
        ledger = EXTERNAL / 'raster_budget'
        if ledger.exists() and any(ledger.iterdir()):
            raise ValueError('new_empty_batch_ledger_required')
        context['freeze_sha256'] = sha(HERE / 'FROZEN.json')
        save(HERE / 'FORMAL_STARTED.json', {'started_ns': time.perf_counter_ns(), **context,
             'maximum_provider_sessions': 6, 'outer_retries': 0, 'sequence': plan['sequence']}, exclusive=True)
        for slot, group in SEQUENCE:
            if stopped:
                records.append({'slot': slot, 'group': group, 'execution_state': 'not_run',
                                'route_invoked': False, 'stop_reasons': stopped})
                continue
            try:
                row = run_slot(plan, slot, group, runtime)
            except BaseException as error:
                failure = error_record(error, 'slot_wrapper_unexpected_exception')
                row = {'slot': slot, 'group': group, 'execution_state': 'failed',
                       'outer_valid_completion': False, 'route_invoked': None,
                       'slot_wrapper_errors': [failure], 'errors': [failure],
                       'stop_remaining_reasons': [{'reason': 'slot_wrapper_execution_state_unknown'}]}
            row['batch_stop_reasons'] = batch_blockers(row)
            records.append(row)
            if row['batch_stop_reasons']:
                stopped = row['batch_stop_reasons']
    except BaseException as error:
        terminal.append(error_record(error, 'batch_checks_or_execution'))
        stopped = [{'reason': 'batch_entry_check_or_execution_failed', 'errors': terminal}]
    finally:
        for slot, group in SEQUENCE[len(records):]:
            records.append({'slot': slot, 'group': group, 'execution_state': 'not_run',
                            'route_invoked': False, 'stop_reasons': stopped or terminal})
        result = aggregate(records, started)
        result['terminal_errors'] = terminal
        result['stop_remaining_reasons'] = stopped
        launch = {'schema': 'routed-task-benefit-launch-v1', **context,
                  'actual_routes': result['actual_routes'], 'actual_CLI_processes': result['actual_CLI_processes'],
                  'execution_states': {row['slot']: row['execution_state'] for row in records},
                  'terminal_errors': terminal, 'stop_remaining_reasons': stopped,
                  'outer_retries': 0}
        for name, value in (('RUN_RESULT.json', result), ('LAUNCH_RESULT.json', launch)):
            try:
                save(runtime / name, value, exclusive=True)
            except BaseException as error:
                publication_errors.append(error_record(error, 'publish_' + name))
        closed = time.perf_counter_ns()
        timing = {'started_ns': started, 'aggregate_results_closed_ns': closed, 'elapsed_ns': closed - started,
                  'terminal_errors': terminal, 'publication_errors': list(publication_errors),
                  'scope': 'Entire formal call through common preparation/checks, fixed serial slots and aggregate/launch write/fsync/close. Interpreter startup, parent shutdown, and this timing receipt publication excluded. Per-slot clocks are independently recorded and are never derived by division.'}
        try:
            save(runtime / 'BATCH_TIMING.json', timing, exclusive=True)
        except BaseException as error:
            publication_errors.append(error_record(error, 'publish_BATCH_TIMING'))
    result['launcher_publication_errors'] = publication_errors
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-models', action='store_true', required=True)
    parser.add_argument('--preparation-git', required=True)
    arguments = parser.parse_args()
    result = run_formal(read(HERE / 'PLAN.json'), arguments.preparation_git)
    states = {row['slot']: row['execution_state'] for row in result['records']}
    print(json.dumps({'actual_routes': result['actual_routes'], 'actual_CLI_processes': result['actual_CLI_processes'],
                      'execution_states': states, 'terminal_errors': result['terminal_errors'],
                      'batch_stopped': bool(result['stop_remaining_reasons']),
                      'publication_errors': result['launcher_publication_errors']}))
    return 0 if (all(state == 'completed' for state in states.values())
                 and not result['stop_remaining_reasons']
                 and not result['launcher_publication_errors'] and not result['terminal_errors']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
