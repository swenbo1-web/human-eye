"""One explicit P diagnostic using the accepted single-route implementation.

No actor, consumer, renderer or model starts on import. Source listing uses
only pinned metadata and hashes. The sole provider entry calls the actual
accepted run_route once, with private globals for this batch's paths/input
contract and a pre-launch phase-cap adjustment. Old sources stay read-only.
"""

import argparse
import hashlib
import json
import marshal
from pathlib import Path
import subprocess
import sys
import time
import types


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.with_name('m4_region_localization_consumption_001')
EXTERNAL = Path('D:/he_explicit_001')
OLD_FREEZE_SHA256 = '7d55ddadcb4683c9b262d4412ab2604670ebb340290c00e5f9b56e6fc87acd50'
PRODUCT_SHA256 = '96d7da8c50680a73f251496406c9f0bbbf6b38bd4dfe848c931e45f094343b76'
SUFFIX_SHA256 = '3f848a42070580ad479e3de6507b9ffe09c59b9651c784c17608f0d752c1205a'
PREFIX_SHA256 = 'a5fa763545131ac0181bd5bcfaa69b09f6f9fa565da99f21d40fab2aad85caa8'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value, exclusive=False):
    with Path(path).open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def old_launcher():
    """Execute the exact pinned old module bytes, preserving their real path."""
    frozen_path = OLD / 'FROZEN.json'
    if sha(frozen_path) != OLD_FREEZE_SHA256:
        raise ValueError('accepted_old_freeze_changed')
    pins = read(frozen_path)['files_sha256']
    path = (OLD / 'launcher.py').resolve()
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pins[str(path)]:
        raise ValueError('accepted_old_launcher_changed')
    module = types.ModuleType('_explicit_accepted_localization_launcher')
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def input_checks(plan):
    if (plan['schema'] != 'explicit-observation-consumption-001-plan-v1'
            or [(row['slot'], row['group']) for row in plan['sequence']] != [('P1', 'P')]
            or plan['formal_batch_attempts'] != 1):
        raise ValueError('single_fresh_P1_contract')
    if (plan['route_deadline_seconds'], plan['max_tool_calls'], plan['max_render_attempts'],
            plan['preparation_render_cap'], plan['formal_render_cap'], plan['total_new_render_cap']) != (450, 12, 6, 0, 6, 6):
        raise ValueError('single_slot_limits')
    old_plan = read(OLD / 'PLAN.json')
    for name in ('requested_model', 'requested_reasoning_effort', 'requested_service_tier'):
        if plan[name] != old_plan[name]:
            raise ValueError('unchanged_requested_CLI_profile_' + name)
    if Path(plan['external_root']).resolve() != EXTERNAL or Path(plan['runtime_root']).resolve() != EXTERNAL / 'formal':
        raise ValueError('new_external_runtime_required')
    prompt_path = Path(plan['inputs']['prompt']).resolve()
    manifest_path = Path(plan['inputs']['input_manifest']).resolve()
    if not prompt_path.is_relative_to(HERE) or not manifest_path.is_relative_to(HERE):
        raise ValueError('new_batch_prompt_and_manifest_required')
    prefix = HERE / 'inputs/PREFIX.txt'
    suffix = HERE / 'inputs/PROMPT_SUFFIX.txt'
    original = Path(old_plan['inputs']['prompt']).resolve()
    if (sha(prefix) != PREFIX_SHA256 or sha(suffix) != SUFFIX_SHA256 or sha(original) != SUFFIX_SHA256
            or suffix.read_bytes() != original.read_bytes()
            or prompt_path.read_bytes() != prefix.read_bytes() + b'\n\n' + original.read_bytes()
            or sha(prompt_path) != plan['expected_prompt_sha256']
            or plan['original_suffix_sha256'] != SUFFIX_SHA256 or plan['prefix_sha256'] != PREFIX_SHA256):
        raise ValueError('fixed_explicit_prefix_and_byteexact_original_suffix')
    manifest = read(manifest_path)
    previous_manifest_path = Path(old_plan['inputs']['input_manifest']).resolve()
    previous = read(previous_manifest_path)
    if (manifest['schema'] != previous['schema'] or manifest['replay_label'] != 'CAPTURE_REPLAY'
            or manifest['public_surface_color_rgb'] != previous['public_surface_color_rgb']):
        raise ValueError('unchanged_public_source_schema_color')
    sources = {str(path): sha(path) for path in (prompt_path, manifest_path, prefix, suffix, original)}
    for name in ('capture', 'scene', 'cameras', 'product_binding'):
        specification = manifest[name]
        path = Path(specification['path']).resolve()
        old_specification = previous[name]
        expected_path = (Path(old_specification['path']) if 'path' in old_specification
                         else previous_manifest_path.parent / old_specification['file']).resolve()
        if path != expected_path or sha(path) != specification['sha256'] or specification['sha256'] != old_specification['sha256']:
            raise ValueError('same_readonly_source_' + name)
        sources[str(path)] = specification['sha256']
    budget = manifest['budget_contract']
    if (Path(budget['external_root']).resolve() != EXTERNAL
            or Path(budget['formal_root']).resolve() != EXTERNAL / 'formal'
            or Path(budget['preparation_root']).resolve() != EXTERNAL / 'preparation'
            or Path(budget['ledger_root']).resolve() != EXTERNAL / 'raster_budget'
            or (budget['formal_cap'], budget['preparation_cap'], budget['per_slot_cap'], budget['total_cap']) != (6, 0, 6, 44)):
        raise ValueError('new_six_raster_phase_with_unchanged_legacy_container')
    if read(manifest['product_binding']['path'])['source_sha256'] != PRODUCT_SHA256:
        raise ValueError('unchanged_installed_product')
    return prompt_path.read_bytes(), manifest_path, sources


def source_file_list(plan):
    """Reuse the old source closure with its old six-slot plan, then add this batch."""
    old = old_launcher()
    accepted_pins = read(OLD / 'FROZEN.json')['files_sha256']
    sources = old.source_file_list(read(OLD / 'PLAN.json'))
    for name, wanted in sources.items():
        if accepted_pins.get(name) != wanted:
            raise ValueError('old_execution_source_not_in_accepted_freeze:' + name)
    sources.update(input_checks(plan)[2])
    for path in (OLD / 'FROZEN.json', HERE / 'launcher.py', HERE / 'PLAN.json',
                 HERE / 'PLAN.md', HERE / 'INPUT_BINDING.json'):
        sources[str(path.resolve())] = sha(path)
    return sources


def verify_frozen(sources):
    frozen = read(HERE / 'FROZEN.json')
    if any(frozen['files_sha256'].get(path) != wanted for path, wanted in sources.items()):
        raise ValueError('required_source_missing_from_new_freeze')
    for path, wanted in frozen['files_sha256'].items():
        if sha(path) != wanted:
            raise ValueError('new_frozen_source_changed:' + path)
    return frozen


def function_identity(function):
    return {'source_path': function.__code__.co_filename, 'qualname': function.__qualname__,
            'module': function.__module__, 'code_sha256': hashlib.sha256(marshal.dumps(function.__code__)).hexdigest()}


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
                or Path(config['budget_root']).resolve() != EXTERNAL / 'raster_budget'):
            raise ValueError('accepted_command_before_single_phase_adjustment')
        config['phase_render_cap'] = 6
        save(config_path, config)
        return command

    launch = types.SimpleNamespace(BASE=accepted_launch.BASE, BASE_SHA256=accepted_launch.BASE_SHA256,
                                   stop_process=accepted_launch.stop_process, python_command=python_command)
    route = old.clone(accepted_route, {'HERE': HERE, 'input_checks': input_checks, 'launch': launch})
    consumer = driver.consumer
    common = route.__globals__['common_image_faults']
    def pointer_proof():
        checks = {**driver.pointers,
                  'single_route_code_is_accepted_route_code': route.__code__ is accepted_route.__code__,
                  'single_route_consumer_is_accepted_consumer': route.__globals__['consumer'] is consumer,
                  'single_route_uses_new_input_check': route.__globals__['input_checks'] is input_checks,
                  'single_route_uses_new_path_namespace': route.__globals__['HERE'] == HERE,
                  'consumer_archive_is_unified_accepted_archive': consumer.consume_turn.__globals__['archive_turn'] is consumer.archive_turn,
                  'same_matcher_instance': common.__globals__['consumer'].result_contract is consumer.result_contract,
                  'held_cleanup_unchanged': launch.stop_process is accepted_launch.stop_process,
                  'consumer_base_unchanged': consumer.launch.BASE == launch.BASE,
                  'old_route_globals_not_mutated': accepted_route.__globals__['launch'] is accepted_launch}
        if not all(checks.values()):
            raise ValueError('actual_accepted_single_route_pointer_chain')
        return {'schema': 'explicit-observation-entry-pointer-proof-v1', 'checks': checks,
             'accepted_launcher_path': str(OLD / 'launcher.py'), 'accepted_launcher_sha256': sha(OLD / 'launcher.py'),
             'accepted_freeze_sha256': OLD_FREEZE_SHA256, 'old_connect': function_identity(old.connect),
             'accepted_route': function_identity(accepted_route), 'single_route': function_identity(route),
             'consumer': function_identity(consumer.consume_turn), 'archive': function_identity(consumer.archive_turn),
             'matcher_path': str(Path(consumer.result_contract.__file__).resolve()),
             'matcher_sha256': sha(consumer.result_contract.__file__),
             'python_command_adjustment': 'Original command targets original bootstrap and bridge; only new ACTOR_CONFIG phase_render_cap changes 36 to 6 before launch.',
             'legacy_ledger_container_cap': 44, 'effective_new_phase_cap': 6, 'per_actor_cap': 6,
             'old_run_batch_called': False, 'old_main_called': False,
             'audit_scope': 'Original research-root and explicit private-path guards retained. New runtime is one fresh slot; no broader OS sandbox claim.'}
    return route, pointer_proof


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
    proof = pointer_proof()
    runtime = EXTERNAL / 'formal'
    runtime.mkdir(parents=True, exist_ok=False)
    save(runtime / 'ENTRY_PROOF_BEFORE.json', proof, exclusive=True)
    save(HERE / 'FORMAL_STARTED.json', {'started_ns': time.perf_counter_ns(), 'preparation_git': preparation_git,
         'freeze_sha256': sha(HERE / 'FROZEN.json'), 'slot': 'P1', 'group': 'P',
         'maximum_provider_sessions': 1, 'outer_retries': 0}, exclusive=True)
    record = route('P1', 'P', plan, runtime)
    record['execution_state'] = 'completed' if record['outer_valid_completion'] else 'failed'
    result = {'schema': 'explicit-observation-single-route-v1', 'records': [record],
              'planned_routes': 1, 'planned_user_turns': 1, 'actual_routes': 1,
              'actual_CLI_processes': int(record.get('consumer_pid') is not None),
              'observed_fresh_threads': [record['observed_thread_id']] if record.get('observed_thread_id') else [],
              'maximum_tools_per_route': 12, 'maximum_render_attempts_per_route': 6,
              'maximum_formal_raster_attempts': 6, 'preparation_raster_attempts': 0,
              'outer_retries': 0, 'provider_internal_raw_requests': None, 'fees': None,
              'content_quality': 'unscored', 'Blender_processes': 0, 'paid_API_calls': 0}
    save(runtime / 'RUN_RESULT.json', result, exclusive=True)
    verify_frozen(sources)
    if source_file_list(plan) != sources:
        raise ValueError('source_changed_during_single_slot')
    after = pointer_proof()
    save(runtime / 'ENTRY_PROOF_AFTER.json', after, exclusive=True)
    if after != proof:
        raise ValueError('entry_pointer_chain_changed_during_single_slot')
    save(runtime / 'LAUNCH_RESULT.json', {'schema': 'explicit-observation-single-launch-v1',
         'preparation_git': preparation_git, 'source_unchanged': True, 'pointer_chain': proof,
         'freeze_sha256': sha(HERE / 'FROZEN.json'), 'actual_routes': 1,
         'actual_CLI_processes': result['actual_CLI_processes'], 'outer_retries': 0}, exclusive=True)
    closed = time.perf_counter_ns()
    save(runtime / 'LAUNCH_TIMING.json', {'started_ns': started, 'launch_result_closed_ns': closed,
         'elapsed_ns': closed - started, 'scope': 'Single launcher call through source/input checks, accepted route, held cleanup/archive, result publication and post-source check. Interpreter startup and this timing receipt publication excluded.'}, exclusive=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-models', action='store_true', required=True)
    parser.add_argument('--preparation-git', required=True)
    arguments = parser.parse_args()
    result = run_once(read(HERE / 'PLAN.json'), arguments.preparation_git)
    print(json.dumps({'actual_routes': result['actual_routes'],
                      'actual_CLI_processes': result['actual_CLI_processes'],
                      'execution_state': result['records'][0]['execution_state']}))


if __name__ == '__main__':
    main()
