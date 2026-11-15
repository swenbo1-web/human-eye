"""New fixed scene inputs around the accepted routed complete-slot execution."""

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
EXTERNAL = Path('D:/he_occluded_transfer_001')
PRODUCT_SHA256 = 'd8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02'
OLD_FREEZE_SHA256 = '7d55ddadcb4683c9b262d4412ab2604670ebb340290c00e5f9b56e6fc87acd50'
ROUTED_FREEZE_SHA256 = '00b7fb3c9a399a60291758cabaa5726fec4c87c1998ab6d537901f19d27af87b'
VIEW_FREEZE_SHA256 = '6456f8511e1bedf71cd119b5da347f8f2431c8bd8db5314ee1fdf5d3ede51943'
COMPLETE_FREEZE_SHA256 = '907bc76d011f32e3695f546d685bc4c682d54459e829f02d09f3acab18f6bb4d'
SEQUENCE = [('N1', 'N'), ('P1', 'P'), ('P2', 'P'), ('N2', 'N'), ('N3', 'N'), ('P3', 'P')]
PREFIXES = {
    'N': b'For this comparison, begin with whichever available native entry is most efficient. Reuse current-session evidence and computed facts; obtain additional evidence only when it is missing or inconsistent. Complete the task below within this turn.',
    'P': b'For this comparison, begin with active_observation(include_images=true). Reuse current-session evidence and computed facts; obtain additional evidence only when it is missing or inconsistent. Complete the task below within this turn.'}
STATIC_DOCUMENTS = ('ADMINISTRATOR_PLAN.md', 'PLAN.md', 'PLAN.json', 'BASELINE.json',
    'DESIGN_CASE.md', 'SCORING_PLAN.md', 'SHARED_DEPENDENCY.json', 'RUNTIME_INTERFACE_CHECK.json')


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
    return dict(phase=phase, type=type(error).__name__, message=str(error),
        traceback=''.join(traceback.format_exception(type(error), error, error.__traceback__)))


def load_fixed(name, source, freeze_path, freeze_digest):
    if sha(freeze_path) != freeze_digest or read(freeze_path)['files_sha256'][str(source)] != sha(source):
        raise ValueError('accepted_execution_module_changed:' + str(source))
    module = types.ModuleType(name)
    module.__file__ = str(source)
    sys.modules[name] = module
    exec(compile(source.read_bytes(), str(source), 'exec', dont_inherit=True), module.__dict__)
    return module


def old_launcher():
    return load_fixed('_occluded_transfer_localization_launcher', OLD / 'launcher.py',
                      OLD / 'FROZEN.json', OLD_FREEZE_SHA256)


def routed_launcher():
    return load_fixed('_occluded_transfer_routed_launcher', ROUTED / 'launcher.py',
                      ROUTED / 'FROZEN.json', ROUTED_FREEZE_SHA256)


def runtime_bindings():
    return read(VIEW / 'RUNTIME_BINDINGS.json')


def shared_dependency():
    path = HERE / 'SHARED_DEPENDENCY.json'
    value = read(path)
    if (value['schema'] != 'occluded-transfer-common-dependency-v1'
            or value['shapely_version'] != '2.1.2'
            or Path(value['dependency_root']).resolve() != EXTERNAL / 'shared_dependencies'):
        raise ValueError('one_new_common_shapely_dependency')
    for source, digest in value['files_sha256'].items():
        if sha(source) != digest:
            raise ValueError('shared_library_changed:' + source)
    return dict(path=str(path), sha256=sha(path))


def input_checks(plan, group=None):
    if (plan['schema'] != 'occluded-scene-transfer-001-plan-v1'
            or [(r['slot'], r['group']) for r in plan['sequence']] != SEQUENCE
            or plan['formal_batch_attempts'] != 1):
        raise ValueError('fixed_six_fresh_slot_order')
    limits = tuple(plan[key] for key in ('route_deadline_seconds', 'max_tool_calls', 'max_render_attempts',
        'preparation_render_cap', 'formal_render_cap', 'total_new_render_cap'))
    if limits != (450, 12, 6, 12, 36, 48):
        raise ValueError('new_12_36_48_raster_contract')
    if (plan['requested_model'], plan['requested_reasoning_effort'], plan['requested_service_tier']) != ('gpt-6.1-sol', 'medium', 'default'):
        raise ValueError('unchanged_requested_CLI_profile')
    if (Path(plan['external_root']).resolve() != EXTERNAL
            or Path(plan['runtime_root']).resolve() != EXTERNAL / 'formal'):
        raise ValueError('new_external_runtime_required')
    manifest_path = Path(plan['inputs']['input_manifest']).resolve()
    suffix = HERE / 'inputs/PROMPT_SUFFIX.txt'
    if (manifest_path != HERE / 'inputs/SOURCES.json'
            or sha(suffix) != plan['expected_suffix_sha256']):
        raise ValueError('frozen_new_common_suffix')
    sources = {str(path): sha(path) for path in (manifest_path, suffix)}
    prompts = {}
    for arm in ('N', 'P'):
        prefix = HERE / ('inputs/PREFIX_' + arm + '.txt')
        prompt = Path(plan['inputs']['prompts'][arm]).resolve()
        if (prompt != HERE / ('inputs/PROMPT_' + arm + '.txt') or prefix.read_bytes() != PREFIXES[arm]
                or prompt.read_bytes() != PREFIXES[arm] + b'\n\n' + suffix.read_bytes()
                or sha(prompt) != plan['expected_prompt_sha256'][arm]):
            raise ValueError('registered_entry_and_byteexact_task_' + arm)
        prompts[arm] = prompt.read_bytes()
        sources.update({str(prefix): sha(prefix), str(prompt): sha(prompt)})
    manifest = read(manifest_path)
    if (manifest['schema'] != 'region-localization-consumption-001-inputs-v1'
            or manifest['replay_label'] != 'CAPTURE_REPLAY'
            or manifest['public_surface_color_rgb'] != [180, 190, 205]):
        raise ValueError('accepted_shared_source_schema')
    for name in ('scene', 'cameras', 'capture', 'product_binding'):
        spec = manifest[name]
        path = Path(spec['path']).resolve()
        if sha(path) != spec['sha256'] or (name != 'product_binding' and not path.is_relative_to(HERE / 'inputs')):
            raise ValueError('new_frozen_source_' + name)
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
            or (budget['preparation_cap'], budget['formal_cap'], budget['total_cap'], budget['per_slot_cap']) != (12, 36, 48, 6)):
        raise ValueError('new_raster_ledger_12_36_48')
    shared_dependency()
    if group is not None and group not in prompts:
        raise ValueError('registered_group_required')
    return None if group is None else prompts[group], manifest_path, sources


def source_file_list(plan):
    sources = {}
    for directory, digest in ((VIEW, VIEW_FREEZE_SHA256), (ROUTED, ROUTED_FREEZE_SHA256)):
        freeze = directory / 'FROZEN.json'
        if sha(freeze) != digest:
            raise ValueError('accepted_execution_freeze_changed:' + str(freeze))
        for source, expected in read(freeze)['files_sha256'].items():
            if source in sources and sources[source] != expected:
                raise ValueError('accepted_source_closures_disagree')
            sources[source] = expected
        sources[str(freeze)] = digest
    old_freeze = OLD / 'FROZEN.json'
    if sha(old_freeze) != OLD_FREEZE_SHA256:
        raise ValueError('accepted_localization_freeze_changed')
    sources[str(old_freeze)] = OLD_FREEZE_SHA256
    sources[str(OLD / 'launcher.py')] = read(old_freeze)['files_sha256'][str(OLD / 'launcher.py')]
    complete = HERE.with_name('m4_complete_witness_consumption_001')
    complete_freeze = complete / 'FROZEN.json'
    if sha(complete_freeze) != COMPLETE_FREEZE_SHA256:
        raise ValueError('accepted_complete_witness_freeze_changed')
    sources[str(complete_freeze)] = COMPLETE_FREEZE_SHA256
    complete_sources = read(complete_freeze)['files_sha256']
    for name in ('oracle.py', 'make_case.py', 'qual_driver.py', 'launcher.py'):
        path = str(complete / name)
        sources[path] = complete_sources[path]
    sources.update(input_checks(plan)[2])
    paths = list(HERE.glob('*.py')) + list((HERE / 'inputs').glob('*'))
    paths += [HERE / relative for relative in STATIC_DOCUMENTS]
    paths += list((HERE / 'admin').glob('*.py'))
    paths += [HERE / 'admin/TRUTH.json', HERE / 'admin/SCORING_CONTRACT.json', HERE / 'admin/NORMALIZATION_SCHEMA.json']
    for path in paths:
        if path.is_file():
            sources[str(path.resolve())] = sha(path)
    dependency = read(HERE / 'SHARED_DEPENDENCY.json')
    sources.update(dependency['files_sha256'])
    runtime = runtime_bindings()
    sources[str(VIEW / 'RUNTIME_BINDINGS.json')] = sha(VIEW / 'RUNTIME_BINDINGS.json')
    for name in ('base_python', 'verified_bootstrap'):
        spec = runtime[name]
        if sha(spec['path']) != spec['sha256']:
            raise ValueError('accepted_runtime_changed_' + name)
        sources[str(Path(spec['path']).resolve())] = spec['sha256']
    binding = read(read(plan['inputs']['input_manifest'])['product_binding']['path'])
    if len(binding['source_manifest']) != 141:
        raise ValueError('fixed_141_product_sources')
    install = Path(binding['install_root'])
    for row in binding['source_manifest']:
        source = (install / row['path']).resolve()
        if not source.is_relative_to(install):
            raise ValueError('installed_source_path')
        sources[str(source)] = row['sha256']
    for source, expected in sources.items():
        if sha(source) != expected:
            raise ValueError('execution_dependency_changed:' + source)
    return sources


def verify_frozen(sources):
    frozen = read(HERE / 'FROZEN.json')
    if any(frozen['files_sha256'].get(path) != expected for path, expected in sources.items()):
        raise ValueError('required_source_missing_from_new_freeze')
    for path, expected in frozen['files_sha256'].items():
        if sha(path) != expected:
            raise ValueError('new_frozen_source_changed:' + path)
    return frozen


def connect_slot(plan, slot, group):
    old = old_launcher()
    driver = old.connect(plan, 'formal')
    accepted_route = driver.run_route
    accepted_launch = accepted_route.__globals__['launch']

    def python_command(entry, arguments):
        if Path(entry).resolve() != HERE / 'actor.py':
            raise ValueError('registered_new_actor_alias')
        command = accepted_launch.python_command(OLD / 'actor.py', arguments)
        config_path = Path(arguments[arguments.index('--config') + 1])
        config = read(config_path)
        if (config['group'] != group or config['phase'] != 'formal'
                or config['phase_render_cap'] != 36 or config['whole_render_cap'] != 44
                or config['max_render_attempts'] != 6 or config['max_tool_calls'] != 12
                or Path(config['output']).resolve() != EXTERNAL / 'formal' / slot / 'o'
                or Path(config['budget_root']).resolve() != EXTERNAL / 'raster_budget'
                or Path(command[5]).resolve() != OLD / 'bootstrap.py'
                or Path(command[6]).resolve() != OLD / 'bridge.py'):
            raise ValueError('accepted_command_before_new_batch_adjustment')
        config['whole_render_cap'] = 48
        config['runtime_binding']['shared_dependency'] = shared_dependency()
        save(config_path, config)
        command[5:7] = [str(HERE / 'bootstrap.py'), str(HERE / 'bridge.py')]
        return command

    def slot_input_checks(value):
        return input_checks(value, group)

    launch = types.SimpleNamespace(BASE=accepted_launch.BASE, BASE_SHA256=accepted_launch.BASE_SHA256,
        stop_process=accepted_launch.stop_process, python_command=python_command)
    route = old.clone(accepted_route, {'HERE': HERE, 'input_checks': slot_input_checks, 'launch': launch})
    consumer = driver.consumer
    retained = {'accepted_route': accepted_route, 'slot_route': route, 'consumer': consumer.consume_turn,
        'archive': consumer.archive_turn, 'matcher': consumer.result_contract.bind_tool_result,
        'cleanup': launch.stop_process, 'common': route.__globals__['common_image_faults']}
    codes = {name: function.__code__ for name, function in retained.items()}

    def pointer_proof():
        current = {'accepted_route': driver.run_route, 'slot_route': route, 'consumer': consumer.consume_turn,
            'archive': consumer.archive_turn, 'matcher': consumer.result_contract.bind_tool_result,
            'cleanup': launch.stop_process, 'common': route.__globals__['common_image_faults']}
        checks = {name: current[name] is value and current[name].__code__ is codes[name]
                  for name, value in retained.items()}
        checks.update(route_code_reused=route.__code__ is accepted_route.__code__,
            route_consumer_reused=route.__globals__['consumer'] is consumer,
            current_namespace=route.__globals__['HERE'] == HERE,
            route_input_check=route.__globals__['input_checks'] is slot_input_checks,
            route_command=route.__globals__['launch'] is launch,
            archive_matcher=consumer.archive_turn.__globals__['result_contract'].bind_tool_result is retained['matcher'],
            consume_archive=consumer.consume_turn.__globals__['archive_turn'] is retained['archive'],
            accepted_globals_unchanged=accepted_route.__globals__['launch'] is accepted_launch)
        if not all(checks.values()):
            raise ValueError('actual_accepted_pointer_chain_changed')
        return dict(schema='routed-task-entry-pointer-proof-v1', slot=slot, group=group, checks=checks,
            functions={name: dict(source_path=value.__code__.co_filename, qualname=value.__qualname__,
                source_sha256=sha(value.__code__.co_filename)) for name, value in current.items()},
            accepted_connect_time_snapshot=driver.pointers,
            command_adjustment='New shared dependency, bridge/bootstrap paths and actual whole cap48; phase36/per6.',
            old_main_called=False, old_run_batch_called=False)

    return route, pointer_proof


def require_qualification(plan):
    path = Path(plan['inputs']['qualification']).resolve()
    if path != HERE / 'admin/QUALIFICATION.json':
        raise ValueError('private_fixed_qualification_path')
    value = read(path)
    if (value.get('passed') is not True or value.get('status') != 'qualified'
            or value.get('source_freeze_sha256') != sha(HERE / 'FROZEN.json')):
        raise ValueError('same_source_paired_qualification_required')
    run_path = EXTERNAL / 'preparation/QUALIFICATION_RUN.json'
    run = read(run_path)
    if (run.get('transport_passed') is not True or run.get('actual_model_calls') != 0
            or run.get('actual_product_calls') != 1 or not 6 <= run.get('actual_rasters', -1) <= 12):
        raise ValueError('actual_paired_qualification_transport')
    if value.get('qualification_run', {}).get('sha256') != sha(run_path):
        raise ValueError('actual_qualification_binding')
    intents = [read(p) for p in sorted((EXTERNAL / 'raster_budget').glob('attempt_*/INTENT.json'))]
    if (len(intents) != run['actual_rasters']
            or [row['global_attempt'] for row in intents] != list(range(1, len(intents) + 1))
            or any(row['phase'] != 'preparation' for row in intents)):
        raise ValueError('qualification_only_prefix_before_formal')
    return dict(path=str(path), sha256=sha(path), qualification_run=dict(path=str(run_path), sha256=sha(run_path)),
                qualified_rasters=run['actual_rasters'])


def check_slot_facts(slot, group, runtime):
    """Validate saved facts between slots, outside the accepted slot clock."""
    started = time.perf_counter_ns()
    owner = runtime / slot / 'o'
    path = runtime / 'slot_records' / slot / 'FACT_CHECK.json'
    errors = []
    evidence = None
    evidence_summary = None
    blockers = []
    try:
        evidence = load_fixed('_occluded_transfer_saved_facts', HERE / 'saved_evidence.py',
                              HERE / 'FROZEN.json', sha(HERE / 'FROZEN.json'))
        value = evidence.evaluate_owner(owner, read(HERE / 'admin/TRUTH.json'))
        evidence_summary = evidence.summary(value)
        if value['product_errors']:
            blockers.append(dict(reason='current_product_facts_wrong',
                product_errors=value['product_errors']))
    except BaseException as error:
        errors.append(error_record(error, 'offline_saved_owner_fact_check'))
        reason = ('current_product_facts_wrong' if evidence is not None and isinstance(error, evidence.ProductFactError)
                  else 'saved_owner_input_or_frame_proof_failed')
        blockers.append(dict(reason=reason, errors=errors))
    closed = time.perf_counter_ns()
    result = dict(schema='occluded-transfer-between-slot-fact-check-v1', slot=slot, group=group,
        passed=not blockers, owner_output=str(owner), evidence_summary=evidence_summary,
        errors=errors, stop_reasons=blockers, actual_model_calls=0,
        actual_product_calls=0, actual_rasters=0, started_ns=started,
        before_publication_ns=closed, elapsed_ns=closed-started,
        scope='Offline administrator source/frame/product-fact validation after the unchanged complete run_slot clock and before scheduling the next slot. Elapsed excludes this receipt publication, included in full batch coordination. No answer quality or cost ranking is evaluated.')
    save(path, result, exclusive=True)
    return dict(path=str(path), sha256=sha(path), passed=result['passed'],
                elapsed_ns=result['elapsed_ns']), blockers


def run_formal(plan, preparation_git):
    started = time.perf_counter_ns()
    runtime = EXTERNAL / 'formal'
    runtime.mkdir(parents=True, exist_ok=False)
    records, terminal, publication_errors = [], [], []
    stopped = None
    context = dict(preparation_git=preparation_git, freeze_sha256=None)
    routed = routed_launcher()
    try:
        sources = source_file_list(plan)
        verify_frozen(sources)
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        if head != preparation_git or plan.get('model_consumer_enabled') is not True:
            raise ValueError('fixed_preparation_git_and_provider_flag')
        qualification = require_qualification(plan)
        context.update(freeze_sha256=sha(HERE / 'FROZEN.json'), qualification=qualification)
        save(HERE / 'FORMAL_STARTED.json', dict(started_ns=time.perf_counter_ns(), **context,
            maximum_provider_sessions=6, outer_retries=0, sequence=plan['sequence']), exclusive=True)
        for slot, group in SEQUENCE:
            if stopped:
                records.append(dict(slot=slot, group=group, execution_state='not_run', route_invoked=False, stop_reasons=stopped))
                continue
            row = run_slot(plan, slot, group, runtime)
            row['batch_stop_reasons'] = routed.batch_blockers(row)
            records.append(row)
            if row['execution_state'] == 'completed':
                fact_check, fact_blockers = check_slot_facts(slot, group, runtime)
                row['between_slot_fact_check'] = fact_check
                row['batch_stop_reasons'].extend(fact_blockers)
            if row['batch_stop_reasons']:
                stopped = row['batch_stop_reasons']
    except BaseException as error:
        terminal.append(error_record(error, 'batch_checks_or_execution'))
        stopped = [dict(reason='batch_entry_check_or_execution_failed', errors=terminal)]
    finally:
        for slot, group in SEQUENCE[len(records):]:
            records.append(dict(slot=slot, group=group, execution_state='not_run', route_invoked=False,
                                stop_reasons=stopped or terminal))
        result = routed.aggregate(records, started)
        qual_path = EXTERNAL / 'preparation/QUALIFICATION_RUN.json'
        result['preparation_raster_attempts'] = read(qual_path)['actual_rasters'] if qual_path.exists() else None
        result['maximum_qualification_and_formal_raster_attempts'] = 48
        result['terminal_errors'] = terminal
        result['stop_remaining_reasons'] = stopped
        launch = dict(schema='routed-task-benefit-launch-v1', **context,
            actual_routes=result['actual_routes'], actual_CLI_processes=result['actual_CLI_processes'],
            execution_states={row['slot']: row['execution_state'] for row in records},
            terminal_errors=terminal, stop_remaining_reasons=stopped, outer_retries=0)
        for name, value in (('RUN_RESULT.json', result), ('LAUNCH_RESULT.json', launch)):
            try:
                save(runtime / name, value, exclusive=True)
            except BaseException as error:
                publication_errors.append(error_record(error, 'publish_' + name))
        closed = time.perf_counter_ns()
        save(runtime / 'BATCH_TIMING.json', dict(started_ns=started, aggregate_results_closed_ns=closed,
            elapsed_ns=closed-started, terminal_errors=terminal, publication_errors=publication_errors,
            scope='Formal call through common checks, serial accepted run_slot bodies, cleanup and result publication. Per-slot clocks remain independently measured.'), exclusive=True)
    result['launcher_publication_errors'] = publication_errors
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-models', action='store_true', required=True)
    parser.add_argument('--preparation-git', required=True)
    args = parser.parse_args()
    result = run_formal(read(HERE / 'PLAN.json'), args.preparation_git)
    print(json.dumps({key: result[key] for key in ('actual_routes', 'actual_CLI_processes', 'terminal_errors', 'stop_remaining_reasons')}))
    return 0 if (all(row['execution_state'] == 'completed' for row in result['records'])
        and not result['terminal_errors'] and not result['stop_remaining_reasons']
        and not result['launcher_publication_errors']) else 1


# Construct this alias before any slot clock starts. Import executes only saved
# Python definitions and retains the original complete run_slot code object.
ACCEPTED_ROUTED = routed_launcher()
ACCEPTED_OLD = old_launcher()
run_slot = ACCEPTED_OLD.clone(ACCEPTED_ROUTED.run_slot, dict(HERE=HERE,
    source_file_list=source_file_list, verify_frozen=verify_frozen, connect_slot=connect_slot))
if run_slot.__code__ is not ACCEPTED_ROUTED.run_slot.__code__:
    raise ValueError('accepted_common_slot_clock_code')


if __name__ == '__main__':
    raise SystemExit(main())
