"""One qualified fresh P consumer using the accepted CLI execution objects."""

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
OLD_ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OLD = OLD_ROOT / 'verification/m4_region_localization_consumption_001'
ROUTED = OLD_ROOT / 'verification/m4_routed_task_benefit_001'
VIEW = HERE.with_name('m4_view_reuse_001')
EXTERNAL = Path('D:/he_complete_witness_001')
PRODUCT_SHA256 = 'd8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02'
OLD_FREEZE_SHA256 = '7d55ddadcb4683c9b262d4412ab2604670ebb340290c00e5f9b56e6fc87acd50'
ROUTED_FREEZE_SHA256 = '00b7fb3c9a399a60291758cabaa5726fec4c87c1998ab6d537901f19d27af87b'
VIEW_FREEZE_SHA256 = '6456f8511e1bedf71cd119b5da347f8f2431c8bd8db5314ee1fdf5d3ede51943'
PRIVATE_SOURCE_FILES = ('admin/TRUTH.json', 'admin/SCORING_CONTRACT.json',
                        'admin/NORMALIZATION_SCHEMA.json', 'SCORING_PLAN.md')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value, *, exclusive=False):
    with Path(path).open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def error_record(error, phase):
    return dict(phase=phase, type=type(error).__name__, message=str(error),
                traceback=''.join(traceback.format_exception(type(error), error, error.__traceback__)))


def input_checks(plan):
    if (plan['schema'] != 'complete-witness-consumption-001-plan-v1'
            or [(r['slot'], r['group']) for r in plan['sequence']] != [('P1', 'P')]
            or plan['formal_batch_attempts'] != 1):
        raise ValueError('single_fresh_P1_contract')
    if (plan['route_deadline_seconds'], plan['max_tool_calls'], plan['max_render_attempts'],
            plan['preparation_render_cap'], plan['formal_render_cap'], plan['total_new_render_cap']) != (450, 12, 6, 6, 6, 12):
        raise ValueError('qualification6_formal6_global12')
    if (plan['requested_model'], plan['requested_reasoning_effort'], plan['requested_service_tier']) != ('gpt-6.1-sol', 'medium', 'default'):
        raise ValueError('accepted_requested_CLI_profile')
    if (Path(plan['external_root']).resolve() != EXTERNAL
            or Path(plan['runtime_root']).resolve() != EXTERNAL / 'formal'):
        raise ValueError('new_complete_witness_runtime')
    prompt = Path(plan['inputs']['prompt']).resolve()
    manifest_path = Path(plan['inputs']['input_manifest']).resolve()
    if (not prompt.is_relative_to(HERE / 'inputs') or not manifest_path.is_relative_to(HERE / 'inputs')
            or sha(prompt) != plan['expected_prompt_sha256']):
        raise ValueError('frozen_public_prompt_and_manifest')
    manifest = read(manifest_path)
    if (manifest['schema'] != 'region-localization-consumption-001-inputs-v1'
            or manifest['replay_label'] != 'CAPTURE_REPLAY'
            or manifest['public_surface_color_rgb'] != [180, 190, 205]):
        raise ValueError('accepted_raw_replay_input_contract')
    sources = {str(path): sha(path) for path in (prompt, manifest_path)}
    for name in ('scene', 'cameras', 'capture', 'product_binding'):
        spec = manifest[name]
        path = Path(spec['path']).resolve()
        if sha(path) != spec['sha256']:
            raise ValueError('frozen_input_changed_' + name)
        if name != 'product_binding' and not path.is_relative_to(HERE / 'inputs'):
            raise ValueError('new_case_input_required_' + name)
        sources[str(path)] = spec['sha256']
    binding = read(manifest['product_binding']['path'])
    if (binding['source_sha256'] != PRODUCT_SHA256 or plan['product_source_sha256'] != PRODUCT_SHA256
            or Path(binding['install_root']).resolve() != Path('D:/he_view_reuse_001/product')
            or Path(binding['dependency_root']).resolve() != Path('D:/he_anchor_001/venv/Lib/site-packages')):
        raise ValueError('fixed_accepted_VIEW_installation')
    budget = manifest['budget_contract']
    if (Path(budget['external_root']).resolve() != EXTERNAL
            or Path(budget['formal_root']).resolve() != EXTERNAL / 'formal'
            or Path(budget['preparation_root']).resolve() != EXTERNAL / 'preparation'
            or Path(budget['ledger_root']).resolve() != EXTERNAL / 'raster_budget'
            or (budget['preparation_cap'], budget['formal_cap'], budget['total_cap'], budget['per_slot_cap']) != (6, 6, 12, 6)):
        raise ValueError('shared_qualification_formal_12_raster_ledger')
    return prompt.read_bytes(), manifest_path, sources


def runtime_bindings():
    return read(VIEW / 'RUNTIME_BINDINGS.json')


def source_file_list(plan):
    """Read source manifests without re-importing retained execution modules."""
    routed_freeze = ROUTED / 'FROZEN.json'
    view_freeze = VIEW / 'FROZEN.json'
    if (sha(routed_freeze) != ROUTED_FREEZE_SHA256 or sha(OLD / 'FROZEN.json') != OLD_FREEZE_SHA256
            or sha(view_freeze) != VIEW_FREEZE_SHA256):
        raise ValueError('accepted_execution_freeze_changed')
    sources = dict(read(view_freeze)['files_sha256'])
    for path, expected in read(routed_freeze)['files_sha256'].items():
        if sources.get(path, expected) != expected:
            raise ValueError('accepted_source_closures_disagree')
        sources[path] = expected
    sources.update(input_checks(plan)[2])
    paths = [routed_freeze, view_freeze, OLD / 'FROZEN.json', VIEW / 'RUNTIME_BINDINGS.json',
             HERE / 'PLAN.json', HERE / 'PLAN.md', HERE / 'DESIGN_FIXTURE.md',
             HERE / 'ADMINISTRATOR_PLAN.md', HERE / 'DESIGN_CASE.md', HERE / 'BASELINE.json',
             ROOT / 'verification/m4_active_coverage_consumption_001/image_content.py']
    paths.extend(HERE.glob('*.py'))
    paths.extend((HERE / 'inputs').glob('*'))
    paths.extend((HERE / 'admin').glob('*.py'))
    for relative in PRIVATE_SOURCE_FILES:
        path = HERE / relative
        if not path.is_file():
            raise ValueError('required_private_judgment_input_missing:' + relative)
        paths.append(path)
    for path in paths:
        if path.is_file():
            sources[str(path.resolve())] = sha(path)
    runtime = runtime_bindings()
    for name in ('base_python', 'verified_bootstrap'):
        spec = runtime[name]
        if sha(spec['path']) != spec['sha256']:
            raise ValueError('accepted_runtime_changed_' + name)
        sources[str(Path(spec['path']).resolve())] = spec['sha256']
    manifest = read(plan['inputs']['input_manifest'])
    binding = read(manifest['product_binding']['path'])
    installed = Path(binding['install_root']).resolve()
    if len(binding['source_manifest']) != 141:
        raise ValueError('fixed_product_141_source_manifest')
    for row in binding['source_manifest']:
        path = installed / row['path']
        if not path.resolve().is_relative_to(installed) or sha(path) != row['sha256']:
            raise ValueError('installed_product_source_changed')
        sources[str(path.resolve())] = row['sha256']
    for path in installed.glob('*.dist-info/*'):
        if path.is_file():
            sources[str(path.resolve())] = sha(path)
    for path, expected in sources.items():
        if sha(path) != expected:
            raise ValueError('execution_source_changed:' + path)
    return sources


def verify_frozen(sources):
    frozen = read(HERE / 'FROZEN.json')
    if any(frozen['files_sha256'].get(path) != expected for path, expected in sources.items()):
        raise ValueError('required_source_missing_from_new_freeze')
    for path, expected in frozen['files_sha256'].items():
        if sha(path) != expected:
            raise ValueError('new_frozen_source_changed:' + path)
    return frozen


def old_launcher():
    path = (OLD / 'launcher.py').resolve()
    frozen = read(OLD / 'FROZEN.json')
    if sha(OLD / 'FROZEN.json') != OLD_FREEZE_SHA256 or frozen['files_sha256'][str(path)] != sha(path):
        raise ValueError('accepted_localization_launcher_changed')
    module = types.ModuleType('_complete_witness_accepted_launcher')
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(path.read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def function_description(function):
    return dict(source_path=function.__code__.co_filename, qualname=function.__qualname__,
                source_sha256=sha(function.__code__.co_filename))


def connect_once(plan):
    old = old_launcher()
    driver = old.connect(plan, 'formal')
    accepted_route = driver.run_route
    accepted_launch = accepted_route.__globals__['launch']

    def python_command(entry, arguments):
        if Path(entry).resolve() != (HERE / 'actor.py').resolve():
            raise ValueError('new_actor_alias_required')
        command = accepted_launch.python_command(OLD / 'actor.py', arguments)
        config_path = Path(arguments[arguments.index('--config') + 1])
        config = read(config_path)
        if (config['group'] != 'P' or config['phase'] != 'formal'
                or config['phase_render_cap'] != 36 or config['whole_render_cap'] != 44
                or config['max_render_attempts'] != 6 or config['max_tool_calls'] != 12
                or Path(config['output']).resolve() != EXTERNAL / 'formal/P1/o'
                or Path(config['budget_root']).resolve() != EXTERNAL / 'raster_budget'
                or Path(command[5]).resolve() != (OLD / 'bootstrap.py').resolve()
                or Path(command[6]).resolve() != (OLD / 'bridge.py').resolve()):
            raise ValueError('retained_command_before_new_adapter_adjustment')
        config.update(phase_render_cap=6, whole_render_cap=12)
        save(config_path, config)
        command[5:7] = [str(HERE / 'bootstrap.py'), str(HERE / 'bridge.py')]
        return command

    launch = types.SimpleNamespace(BASE=accepted_launch.BASE, BASE_SHA256=accepted_launch.BASE_SHA256,
        stop_process=accepted_launch.stop_process, python_command=python_command)
    route = old.clone(accepted_route, {'HERE': HERE, 'input_checks': input_checks, 'launch': launch})
    consumer = driver.consumer
    common = route.__globals__['common_image_faults']
    retained = {'connect': old.connect, 'accepted_route': accepted_route, 'single_route': route,
                'consumer': consumer.consume_turn, 'archive': consumer.archive_turn,
                'matcher': consumer.result_contract.bind_tool_result, 'cleanup': launch.stop_process,
                'common': common}
    codes = {name: function.__code__ for name, function in retained.items()}

    def pointer_proof():
        current = {'connect': old.connect, 'accepted_route': driver.run_route, 'single_route': route,
                   'consumer': consumer.consume_turn, 'archive': consumer.archive_turn,
                   'matcher': consumer.result_contract.bind_tool_result, 'cleanup': launch.stop_process,
                   'common': route.__globals__['common_image_faults']}
        checks = {name: current[name] is value and current[name].__code__ is codes[name]
                  for name, value in retained.items()}
        checks.update(route_code_reused=route.__code__ is accepted_route.__code__,
            route_consumer_reused=route.__globals__['consumer'] is consumer,
            current_namespace=route.__globals__['HERE'] == HERE,
            new_input_check=route.__globals__['input_checks'] is input_checks,
            new_command=route.__globals__['launch'] is launch,
            archive_matcher=consumer.archive_turn.__globals__['result_contract'].bind_tool_result is retained['matcher'],
            consume_archive=consumer.consume_turn.__globals__['archive_turn'] is retained['archive'],
            accepted_globals_unchanged=accepted_route.__globals__['launch'] is accepted_launch)
        if not all(checks.values()):
            raise ValueError('accepted_single_route_pointer_chain_changed')
        return dict(schema='complete-witness-entry-pointer-proof-v1', checks=checks,
                    functions={name: function_description(value) for name, value in current.items()},
                    accepted_connect_snapshot=driver.pointers,
                    snapshot_scope='The snapshot was evaluated in connect. Current references above are checked at publication.',
                    adjustment='New VIEW-reuse bridge/bootstrap paths and formal6/global12/perowner6 limits.',
                    old_main_called=False, old_run_batch_called=False)

    return route, pointer_proof


def require_qualification(plan):
    path = Path(plan['inputs']['qualification']).resolve()
    if path != (HERE / 'admin/QUALIFICATION.json').resolve():
        raise ValueError('private_fixed_qualification_path')
    value = read(path)
    manifest = read(plan['inputs']['input_manifest'])
    expected_inputs = {name: manifest[name]['sha256'] for name in ('scene', 'cameras', 'capture', 'product_binding')}
    if (value['schema'] != 'complete-witness-qualification-v1' or value['passed'] is not True
            or value['status'] != 'qualified' or value['source_freeze_sha256'] != sha(HERE / 'FROZEN.json')
            or value['prompt_sha256'] != plan['expected_prompt_sha256'] or value['input_sha256'] != expected_inputs
            or value['actual_model_calls'] != 0 or value['actual_product_calls'] != 1
            or type(value['actual_rasters']) is not int or not 1 <= value['actual_rasters'] <= 6):
        raise ValueError('same_source_complete_witness_qualification_required')
    run_spec = value['qualification_run']
    run_path = Path(run_spec['path']).resolve()
    if (run_path != EXTERNAL / 'preparation/Q1/QUALIFICATION_RUN.json'
            or sha(run_path) != run_spec['sha256']):
        raise ValueError('actual_qualification_run_binding')
    run = read(run_path)
    if (not run['transport_passed'] or run['actual_model_calls'] != 0
            or run['actual_product_calls'] != 1 or run['actual_rasters'] != value['actual_rasters']):
        raise ValueError('actual_qualification_transport_required')
    intents = [read(p) for p in sorted((EXTERNAL / 'raster_budget').glob('attempt_*/INTENT.json'))]
    if (len(intents) != value['actual_rasters']
            or [row['global_attempt'] for row in intents] != list(range(1, len(intents) + 1))
            or any(row['phase'] != 'preparation' for row in intents)):
        raise ValueError('qualification_only_prefix_before_fresh_formal')
    return dict(path=str(path), sha256=sha(path), qualification_run=run_spec,
                qualified_rasters=value['actual_rasters'])


def run_once(plan, preparation_git):
    started = time.perf_counter_ns()
    sources = source_file_list(plan)
    verify_frozen(sources)
    qualification = require_qualification(plan)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    if head.returncode or head.stdout.strip() != preparation_git or not plan.get('model_consumer_enabled'):
        raise ValueError('fixed_preparation_git_and_model_flag_required')
    route, pointer_proof = connect_once(plan)
    runtime = EXTERNAL / 'formal'
    runtime.mkdir(parents=True, exist_ok=False)
    save(HERE / 'FORMAL_STARTED.json', dict(started_ns=time.perf_counter_ns(), preparation_git=preparation_git,
        freeze_sha256=sha(HERE / 'FROZEN.json'), qualification=qualification,
        maximum_model_consumers=1, outer_retries=0), exclusive=True)
    record = None
    errors = []
    pointer_after = None
    route_started = None
    route_closed = None
    try:
        save(runtime / 'ENTRY_PROOF_BEFORE.json', pointer_proof(), exclusive=True)
        route_started = time.perf_counter_ns()
        record = route('P1', 'P', plan, runtime)
    except BaseException as error:
        errors.append(error_record(error, 'single_route'))
    finally:
        route_closed = time.perf_counter_ns()
        try:
            pointer_after = pointer_proof()
            save(runtime / 'ENTRY_PROOF_AFTER.json', pointer_after, exclusive=True)
            verify_frozen(sources)
            if sources != source_file_list(plan) or sha(qualification['path']) != qualification['sha256']:
                raise ValueError('source_or_qualification_changed_during_formal')
        except BaseException as error:
            errors.append(error_record(error, 'post_route_checks'))
        complete = isinstance(record, dict) and record.get('outer_valid_completion') is True
        result = dict(schema='complete-witness-single-formal-v1', records=[] if record is None else [record],
            planned_routes=1, actual_routes=int(route_started is not None),
            actual_CLI_processes=(int(record.get('consumer_pid') is not None) if isinstance(record, dict) else None),
            execution_state='completed' if complete else 'failed', launcher_succeeded=complete and not errors,
            terminal_errors=errors, outer_retries=0, content_quality='unscored', qualification=qualification,
            maximum_formal_rasters=6, maximum_qualification_and_formal_rasters=12,
            model_token_cash_benefit='not_a_comparison', provider_requests=None,
            preparation_git=preparation_git, freeze_sha256=sha(HERE / 'FROZEN.json'))
        for name in ('RUN_RESULT.json', 'LAUNCH_RESULT.json'):
            save(runtime / name, result, exclusive=True)
        closed = time.perf_counter_ns()
        save(runtime / 'LAUNCH_TIMING.json', dict(started_ns=started, launch_results_closed_ns=closed,
            elapsed_ns=closed-started, route_started_ns=route_started, route_closed_ns=route_closed,
            route_elapsed_ns=None if route_started is None else route_closed-route_started,
            terminal_errors=errors,
            scope='Before formal source/qualification checks through one route, cleanup, postchecks and result fsync/close. Interpreter import and this timing publication are excluded.'), exclusive=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-models', action='store_true', required=True)
    parser.add_argument('--preparation-git', required=True)
    args = parser.parse_args()
    result = run_once(read(HERE / 'PLAN.json'), args.preparation_git)
    print(json.dumps({key: result[key] for key in ('actual_routes', 'actual_CLI_processes', 'execution_state', 'launcher_succeeded')}))
    return 0 if result['launcher_succeeded'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
