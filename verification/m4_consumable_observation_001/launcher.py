"""One consumable-observation route using pinned accepted execution objects.

Importing this module starts no product, actor, CLI, renderer or model.
The root explicitly freezes and starts the sole real route.
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
OLD = HERE.with_name('m4_region_localization_consumption_001')
EXPLICIT = HERE.with_name('m4_explicit_observation_consumption_001')
EXTERNAL = Path('D:/he_consume_001')
OLD_FREEZE_SHA256 = '7d55ddadcb4683c9b262d4412ab2604670ebb340290c00e5f9b56e6fc87acd50'
PROMPT_SHA256 = 'ecbcb28c961847f14ae9564425f1b8152f07b952d2d5f38ebfcd9fd143ff79d4'


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


def old_launcher():
    frozen_path = OLD / 'FROZEN.json'
    if sha(frozen_path) != OLD_FREEZE_SHA256:
        raise ValueError('accepted_old_freeze_changed')
    path = (OLD / 'launcher.py').resolve()
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != read(frozen_path)['files_sha256'][str(path)]:
        raise ValueError('accepted_old_launcher_changed')
    module = types.ModuleType('_consumable_accepted_localization_launcher')
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def input_checks(plan):
    if (plan['schema'] != 'consumable-observation-001-plan-v1'
            or [(row['slot'], row['group']) for row in plan['sequence']] != [('P1', 'P')]
            or plan['formal_batch_attempts'] != 1):
        raise ValueError('single_fresh_P1_contract')
    if (plan['route_deadline_seconds'], plan['max_tool_calls'], plan['max_render_attempts'],
            plan['preparation_render_cap'], plan['formal_render_cap'], plan['total_new_render_cap']) != (450, 12, 6, 0, 6, 6):
        raise ValueError('single_slot_limits')
    previous_plan = read(OLD / 'PLAN.json')
    for name in ('requested_model', 'requested_reasoning_effort', 'requested_service_tier'):
        if plan[name] != previous_plan[name]:
            raise ValueError('unchanged_requested_CLI_profile_' + name)
    if (Path(plan['external_root']).resolve() != EXTERNAL
            or Path(plan['runtime_root']).resolve() != EXTERNAL / 'formal'):
        raise ValueError('new_external_runtime_required')
    prompt = Path(plan['inputs']['prompt']).resolve()
    manifest_path = Path(plan['inputs']['input_manifest']).resolve()
    if not prompt.is_relative_to(HERE) or not manifest_path.is_relative_to(HERE):
        raise ValueError('new_batch_prompt_and_manifest_required')
    old_prompt = EXPLICIT / 'inputs/PROMPT.txt'
    if (plan['expected_prompt_sha256'] != PROMPT_SHA256 or sha(prompt) != PROMPT_SHA256
            or sha(old_prompt) != PROMPT_SHA256 or prompt.read_bytes() != old_prompt.read_bytes()):
        raise ValueError('byteexact_previous_explicit_prompt_required')
    manifest = read(manifest_path)
    previous_manifest_path = Path(previous_plan['inputs']['input_manifest']).resolve()
    previous = read(previous_manifest_path)
    if (manifest['schema'] != previous['schema'] or manifest['replay_label'] != 'CAPTURE_REPLAY'
            or manifest['public_surface_color_rgb'] != previous['public_surface_color_rgb']):
        raise ValueError('unchanged_public_source_schema_color')
    sources = {str(path): sha(path) for path in (prompt, old_prompt, manifest_path)}
    for name in ('capture', 'scene', 'cameras'):
        specification = manifest[name]
        path = Path(specification['path']).resolve()
        old_specification = previous[name]
        old_path = (Path(old_specification['path']) if 'path' in old_specification
                    else previous_manifest_path.parent / old_specification['file']).resolve()
        if (path != old_path or sha(path) != specification['sha256']
                or specification['sha256'] != old_specification['sha256']):
            raise ValueError('same_readonly_source_' + name)
        sources[str(path)] = specification['sha256']
    binding_specification = manifest['product_binding']
    binding_path = Path(binding_specification['path']).resolve()
    if binding_path != (HERE / 'inputs/PRODUCT_BINDING.json').resolve() or sha(binding_path) != binding_specification['sha256']:
        raise ValueError('new_candidate_binding_required')
    binding = read(binding_path)
    candidate = plan['product_source_sha256']
    if (len(candidate) != 64 or any(character not in '0123456789abcdef' for character in candidate)
            or binding['source_sha256'] != candidate
            or Path(binding['install_root']).resolve() != EXTERNAL / 'product'
            or Path(binding['dependency_root']).resolve() != Path('D:/he_anchor_001/venv/Lib/site-packages')):
        raise ValueError('current_candidate_installation_required')
    sources[str(binding_path)] = binding_specification['sha256']
    budget = manifest['budget_contract']
    if (Path(budget['external_root']).resolve() != EXTERNAL
            or Path(budget['formal_root']).resolve() != EXTERNAL / 'formal'
            or Path(budget['preparation_root']).resolve() != EXTERNAL / 'preparation'
            or Path(budget['ledger_root']).resolve() != EXTERNAL / 'raster_budget'
            or (budget['formal_cap'], budget['preparation_cap'], budget['per_slot_cap'], budget['total_cap']) != (6, 0, 6, 44)):
        raise ValueError('new_six_raster_phase_with_unchanged_legacy_container')
    return prompt.read_bytes(), manifest_path, sources


def source_file_list(plan):
    """Pin inherited old execution bytes and separately add candidate bytes."""
    old = old_launcher()
    accepted_pins = read(OLD / 'FROZEN.json')['files_sha256']
    sources = old.source_file_list(read(OLD / 'PLAN.json'))
    for path, wanted in sources.items():
        if accepted_pins.get(path) != wanted:
            raise ValueError('old_execution_source_not_in_accepted_freeze:' + path)
    sources.update(input_checks(plan)[2])
    paths = [OLD / 'FROZEN.json', HERE / 'PLAN.json', HERE / 'PLAN.md',
             HERE / 'DESIGN_LAUNCHER.md', HERE / 'DESIGN_PRODUCT.md']
    paths.extend(HERE.glob('*.py'))
    paths.extend((HERE / 'admin').glob('*.py'))
    paths.extend((HERE / 'admin').glob('*.json'))
    for path in paths:
        sources[str(path.resolve())] = sha(path)
    binding = read(HERE / 'inputs/PRODUCT_BINDING.json')
    installed = Path(binding['install_root']).resolve()
    for row in binding['source_manifest']:
        path = installed / row['path']
        if not path.resolve().is_relative_to(installed) or sha(path) != row['sha256']:
            raise ValueError('candidate_installed_source_changed:' + row['path'])
        sources[str(path.resolve())] = row['sha256']
    for path in installed.glob('*.dist-info/*'):
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


def connect_once(plan):
    old = old_launcher()
    driver = old.connect(plan, 'formal')
    accepted_route = driver.run_route
    accepted_launch = accepted_route.__globals__['launch']

    def python_command(entry, arguments):
        if Path(entry).resolve() != (HERE / 'actor.py').resolve():
            raise ValueError('registered_new_route_actor_alias')
        command = accepted_launch.python_command(OLD / 'actor.py', arguments)
        config_path = Path(arguments[arguments.index('--config') + 1])
        config = read(config_path)
        if (config['group'] != 'P' or config['phase'] != 'formal' or config['phase_render_cap'] != 36
                or config['whole_render_cap'] != 44 or config['max_render_attempts'] != 6
                or Path(config['output']).resolve() != EXTERNAL / 'formal/P1/o'
                or Path(config['budget_root']).resolve() != EXTERNAL / 'raster_budget'
                or Path(command[5]).resolve() != (OLD / 'bootstrap.py').resolve()
                or Path(command[6]).resolve() != (OLD / 'bridge.py').resolve()):
            raise ValueError('accepted_command_before_candidate_path_adjustment')
        config['phase_render_cap'] = 6
        save(config_path, config)
        command[5:7] = [str(HERE / 'bootstrap.py'), str(HERE / 'bridge.py')]
        return command

    launch = types.SimpleNamespace(BASE=accepted_launch.BASE, BASE_SHA256=accepted_launch.BASE_SHA256,
                                   stop_process=accepted_launch.stop_process, python_command=python_command)
    route = old.clone(accepted_route, {'HERE': HERE, 'input_checks': input_checks, 'launch': launch})
    consumer = driver.consumer
    common = route.__globals__['common_image_faults']
    retained = {'old_connect': old.connect, 'accepted_route': accepted_route, 'single_route': route,
                'consumer': consumer.consume_turn, 'archive': consumer.archive_turn,
                'matcher': consumer.result_contract.bind_tool_result,
                'cleanup': accepted_launch.stop_process, 'common': common}
    retained_codes = {name: function.__code__ for name, function in retained.items()}

    def pointer_proof():
        current = {'old_connect': old.connect, 'accepted_route': driver.run_route, 'single_route': route,
                   'consumer': consumer.consume_turn, 'archive': consumer.archive_turn,
                   'matcher': consumer.result_contract.bind_tool_result,
                   'cleanup': launch.stop_process, 'common': route.__globals__['common_image_faults']}
        checks = {name + '_same_function_and_code_reference': current[name] is function
                  and current[name].__code__ is retained_codes[name] for name, function in retained.items()}
        checks.update({
            'single_route_code_is_accepted_route_code': route.__code__ is accepted_route.__code__,
            'single_route_consumer_is_accepted_consumer': route.__globals__['consumer'] is consumer,
            'single_route_uses_new_input_check': route.__globals__['input_checks'] is input_checks,
            'single_route_uses_new_path_namespace': route.__globals__['HERE'] == HERE,
            'single_route_uses_new_command': route.__globals__['launch'] is launch,
            'consumer_archive_is_unified_accepted_archive': consumer.consume_turn.__globals__['archive_turn'] is retained['archive'],
            'same_matcher_module': common.__globals__['consumer'].result_contract is consumer.result_contract,
            'archive_uses_retained_matcher': consumer.archive_turn.__globals__['result_contract'].bind_tool_result is retained['matcher'],
            'consumer_base_unchanged': consumer.launch.BASE == launch.BASE,
            'old_route_globals_not_mutated': accepted_route.__globals__['launch'] is accepted_launch})
        if not all(checks.values()):
            raise ValueError('actual_accepted_single_route_pointer_chain')
        return {'schema': 'consumable-observation-entry-pointer-proof-v1', 'checks': checks,
                'accepted_connect_time_snapshot': driver.pointers,
                'snapshot_scope': 'Inherited eight booleans were evaluated inside accepted connect; current checks above are evaluated at this receipt.',
                'functions': {name: function_description(function) for name, function in current.items()},
                'accepted_launcher_path': str(OLD / 'launcher.py'), 'accepted_freeze_sha256': OLD_FREEZE_SHA256,
                'matcher_path': str(Path(consumer.result_contract.__file__).resolve()),
                'matcher_sha256': sha(consumer.result_contract.__file__),
                'command_adjustment': 'Candidate bootstrap and bridge paths; formal phase cap 36 to 6 before actor start. Accepted CLI/consumer/archive/cleanup code objects retained.',
                'legacy_ledger_container_cap': 44, 'effective_new_phase_cap': 6, 'per_actor_cap': 6,
                'old_run_batch_called': False, 'old_main_called': False}

    return route, pointer_proof


def exception_record(error, phase):
    return {'phase': phase, 'type': type(error).__name__, 'message': str(error),
            'traceback': ''.join(traceback.format_exception(type(error), error, error.__traceback__))}


def execute_and_finalize(route_call, postcheck, directory, context, started_ns=None):
    """Call once and publish the actual outcome even when the route raises."""
    directory = Path(directory)
    started = time.perf_counter_ns() if started_ns is None else started_ns
    record = None
    route_error = None
    post_error = None
    publication_errors = []
    result = None
    post = None
    route_started = time.perf_counter_ns()
    try:
        record = route_call()
    except BaseException as error:
        route_error = error
    finally:
        route_closed = time.perf_counter_ns()
        try:
            post = postcheck()
        except BaseException as error:
            post_error = error
        terminal = [exception_record(error, phase) for error, phase in
                    ((route_error, 'route'), (post_error, 'post_route_checks')) if error is not None]
        completed = isinstance(record, dict) and record.get('outer_valid_completion') is True
        if isinstance(record, dict):
            record['execution_state'] = 'completed' if completed else 'failed'
        cli_count = int(record.get('consumer_pid') is not None) if isinstance(record, dict) else None
        thread = record.get('observed_thread_id') if isinstance(record, dict) else None
        result = {'schema': 'consumable-observation-single-route-v1', 'records': [] if record is None else [record],
                  'planned_routes': 1, 'planned_user_turns': 1, 'actual_routes': 1,
                  'actual_CLI_processes': cli_count, 'observed_fresh_threads': [thread] if thread else [],
                  'execution_state': 'completed' if completed else 'failed',
                  'launcher_succeeded': completed and not terminal,
                  'terminal_errors': terminal, 'post_route_checks': post,
                  'maximum_tools_per_route': 12, 'maximum_render_attempts_per_route': 6,
                  'maximum_formal_raster_attempts': 6, 'preparation_raster_attempts': 0,
                  'outer_retries': 0, 'provider_internal_raw_requests': None, 'fees': None,
                  'content_quality': 'unscored', 'Blender_processes': 0, 'paid_API_calls': 0}
        launch = {'schema': 'consumable-observation-single-launch-v1', **context,
                  'actual_routes': 1, 'actual_CLI_processes': cli_count,
                  'route_execution_state': result['execution_state'],
                  'launcher_succeeded': result['launcher_succeeded'], 'terminal_errors': terminal,
                  'post_route_checks': post, 'outer_retries': 0}
        for name, value in (('RUN_RESULT.json', result), ('LAUNCH_RESULT.json', launch)):
            try:
                save(directory / name, value, exclusive=True)
            except BaseException as error:
                publication_errors.append(exception_record(error, 'publish_' + name))
        closed = time.perf_counter_ns()
        timing = {'started_ns': started, 'route_started_ns': route_started,
                  'route_closed_ns': route_closed, 'launch_results_closed_ns': closed,
                  'elapsed_ns': closed - started, 'route_elapsed_ns': route_closed - route_started,
                  'terminal_errors': terminal, 'publication_errors': list(publication_errors),
                  'scope': 'Launch call through source checks, one route, cleanup/archive and postchecks plus result publications. Interpreter startup and this final timing receipt publication are outside this clock.'}
        try:
            save(directory / 'LAUNCH_TIMING.json', timing, exclusive=True)
        except BaseException as error:
            publication_errors.append(exception_record(error, 'publish_LAUNCH_TIMING.json'))
    if route_error is not None:
        raise route_error.with_traceback(route_error.__traceback__)
    if post_error is not None:
        raise post_error.with_traceback(post_error.__traceback__)
    if publication_errors:
        raise RuntimeError('launch_receipt_publication_failed:' + json.dumps(publication_errors, ensure_ascii=False))
    return result


def run_once(plan, preparation_git):
    started = time.perf_counter_ns()
    sources = source_file_list(plan)
    verify_frozen(sources)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    if head.returncode or head.stdout.strip() != preparation_git:
        raise ValueError('fixed_preparation_commit_required')
    if plan.get('model_consumer_enabled') is not True:
        raise ValueError('explicit_single_provider_entry_flag_required')
    ledger = EXTERNAL / 'raster_budget'
    if ledger.exists() and any(ledger.iterdir()):
        raise ValueError('new_empty_single_slot_ledger_required')
    route, pointer_proof = connect_once(plan)
    before = pointer_proof()
    runtime = EXTERNAL / 'formal'
    runtime.mkdir(parents=True, exist_ok=False)
    save(runtime / 'ENTRY_PROOF_BEFORE.json', before, exclusive=True)
    context = {'preparation_git': preparation_git, 'freeze_sha256': sha(HERE / 'FROZEN.json')}
    save(HERE / 'FORMAL_STARTED.json', {'started_ns': time.perf_counter_ns(), **context,
         'slot': 'P1', 'group': 'P', 'maximum_provider_sessions': 1, 'outer_retries': 0}, exclusive=True)

    def postcheck():
        errors = []
        after = None
        try:
            after = pointer_proof()
            save(runtime / 'ENTRY_PROOF_AFTER.json', after, exclusive=True)
        except BaseException as error:
            errors.append(exception_record(error, 'entry_reference_check'))
        try:
            verify_frozen(sources)
            if source_file_list(plan) != sources:
                raise ValueError('source_changed_during_single_slot')
        except BaseException as error:
            errors.append(exception_record(error, 'source_byte_check'))
        if errors:
            raise RuntimeError(json.dumps(errors, ensure_ascii=False))
        return {'source_unchanged': True, 'pointer_chain': after}

    return execute_and_finalize(lambda: route('P1', 'P', plan, runtime), postcheck, runtime, context, started)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-models', action='store_true', required=True)
    parser.add_argument('--preparation-git', required=True)
    arguments = parser.parse_args()
    result = run_once(read(HERE / 'PLAN.json'), arguments.preparation_git)
    print(json.dumps({'actual_routes': result['actual_routes'],
                      'actual_CLI_processes': result['actual_CLI_processes'],
                      'execution_state': result['execution_state'],
                      'launcher_succeeded': result['launcher_succeeded']}))
    return 0 if result['launcher_succeeded'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
