"""Old/new product inputs around the accepted complete-slot implementation."""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import types


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LEGACY_ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe')
PREVIOUS = LEGACY_ROOT / 'verification/m4_occluded_scene_transfer_001'
PREVIOUS_FREEZE_SHA256 = '013f2d5e87b86c9493883a09dc72e1f52170a0a9283a2d47788e262a5dab532d'
EXTERNAL = Path('D:/he_source_face_001')
OLD_PRODUCT_SHA256 = 'd8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02'
SEQUENCE = [('A1', 'P'), ('B1', 'P'), ('B2', 'P'), ('A2', 'P'), ('A3', 'P'), ('B3', 'P')]


def load_previous():
    import hashlib
    frozen = PREVIOUS / 'FROZEN.json'
    if hashlib.sha256(frozen.read_bytes()).hexdigest() != PREVIOUS_FREEZE_SHA256:
        raise ValueError('accepted_previous_freeze_changed')
    source = PREVIOUS / 'launcher.py'
    saved = json.loads(frozen.read_bytes())['files_sha256']
    if saved[str(source)] != hashlib.sha256(source.read_bytes()).hexdigest():
        raise ValueError('accepted_previous_launcher_changed')
    spec = importlib.util.spec_from_file_location('_m1_fixed_previous_launcher', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


previous = load_previous()
sha, read, save = previous.sha, previous.read, previous.save
error_record = previous.error_record
runtime_bindings = previous.runtime_bindings
ACCEPTED_ROUTED = previous.routed_launcher()
ACCEPTED_OLD = previous.old_launcher()


def shared_dependency():
    path = PREVIOUS / 'SHARED_DEPENDENCY.json'
    value = read(path)
    if (value['shapely_version'] != '2.1.2'
            or Path(value['dependency_root']).resolve() != Path('D:/he_occluded_transfer_001/shared_dependencies')):
        raise ValueError('same_fixed_common_dependency')
    for name, expected in value['files_sha256'].items():
        if sha(name) != expected:
            raise ValueError('shared_dependency_changed:' + name)
    return dict(path=str(path), sha256=sha(path))


def input_checks(plan, arm=None):
    if (plan['schema'] != 'source-face-binding-001-plan-v1'
            or [(r['slot'], r['group']) for r in plan['sequence']] != SEQUENCE
            or [r['comparison_arm'] for r in plan['sequence']] != [s[0] for s, _ in SEQUENCE]
            or plan['formal_batch_attempts'] != 1):
        raise ValueError('fixed_six_product_comparison_slots')
    limits = tuple(plan[k] for k in ('route_deadline_seconds', 'max_tool_calls', 'max_render_attempts',
        'preparation_render_cap', 'formal_render_cap', 'total_new_render_cap'))
    if limits != (450, 12, 6, 12, 36, 48):
        raise ValueError('fixed_cumulative_12_36_48_limits')
    if (plan['requested_model'], plan['requested_reasoning_effort'], plan['requested_service_tier']) != ('gpt-6.1-sol', 'medium', 'default'):
        raise ValueError('fixed_CLI_profile')
    if Path(plan['external_root']).resolve() != EXTERNAL or Path(plan['runtime_root']).resolve() != EXTERNAL / 'formal':
        raise ValueError('new_task_runtime_required')
    prompt = Path(plan['inputs']['prompt']).resolve()
    old_prompt = PREVIOUS / 'inputs/PROMPT_P.txt'
    if prompt != HERE / 'inputs/PROMPT.txt' or prompt.read_bytes() != old_prompt.read_bytes():
        raise ValueError('same_old_P_prompt_required_for_both_arms')
    if sha(prompt) != plan['expected_prompt_sha256']:
        raise ValueError('fixed_prompt_sha256')
    sources = {str(prompt): sha(prompt), str(old_prompt): sha(old_prompt)}
    manifests = {}
    for candidate in ('A', 'B'):
        path = Path(plan['inputs']['manifests'][candidate]).resolve()
        if path != HERE / ('inputs/SOURCES_' + candidate + '.json'):
            raise ValueError('registered_arm_manifest')
        manifest = read(path)
        if (manifest['schema'] != 'region-localization-consumption-001-inputs-v1'
                or manifest['replay_label'] != 'CAPTURE_REPLAY'
                or manifest['public_surface_color_rgb'] != [180, 190, 205]
                or manifest['comparison_arm'] != candidate):
            raise ValueError('accepted_replay_schema')
        for name in ('capture', 'scene', 'cameras', 'tasks', 'product_binding'):
            spec = manifest[name]
            source = Path(spec['path']).resolve()
            if sha(source) != spec['sha256']:
                raise ValueError('frozen_input_changed:' + candidate + ':' + name)
            if name != 'product_binding':
                old_spec = read(PREVIOUS / 'inputs/SOURCES.json')[name]
                if spec != old_spec:
                    raise ValueError('same_previous_scene_input:' + name)
            sources[str(source)] = spec['sha256']
        binding_spec = manifest['product_binding']
        binding = read(binding_spec['path'])
        install = Path(binding['install_root']).resolve()
        valid_install = (install == Path('D:/he_view_reuse_001/product') if candidate == 'A'
                         else install.is_relative_to(EXTERNAL) and install != EXTERNAL)
        if (binding_spec != plan['products'][candidate]
                or not valid_install
                or binding['source_sha256'] != manifest['expected_product_source_sha256']
                or candidate == 'A' and binding['source_sha256'] != OLD_PRODUCT_SHA256
                or candidate == 'B' and binding['source_sha256'] == OLD_PRODUCT_SHA256
                or Path(binding['dependency_root']).resolve() != Path('D:/he_anchor_001/venv/Lib/site-packages')):
            raise ValueError('actual_arm_product_binding:' + candidate)
        budget = manifest['budget_contract']
        if (Path(budget['external_root']).resolve() != EXTERNAL
                or Path(budget['preparation_root']).resolve() != EXTERNAL / 'preparation'
                or Path(budget['formal_root']).resolve() != EXTERNAL / 'formal'
                or Path(budget['ledger_root']).resolve() != EXTERNAL / 'raster_budget'
                or (budget['preparation_cap'], budget['formal_cap'], budget['total_cap'], budget['per_slot_cap']) != (12, 36, 48, 6)):
            raise ValueError('persistent_task_raster_budget')
        sources[str(path)] = sha(path)
        manifests[candidate] = path
    shared_dependency()
    selected = arm or plan.get('comparison_arm') or 'A'
    if selected not in manifests:
        raise ValueError('registered_comparison_arm')
    return prompt.read_bytes(), manifests[selected], sources


def source_file_list(plan):
    frozen = PREVIOUS / 'FROZEN.json'
    if sha(frozen) != PREVIOUS_FREEZE_SHA256:
        raise ValueError('accepted_previous_freeze_changed')
    sources = dict(read(frozen)['files_sha256'])
    sources[str(frozen)] = PREVIOUS_FREEZE_SHA256
    sources.update(input_checks(plan)[2])
    paths = list(HERE.glob('*.py')) + list((HERE / 'inputs').glob('*'))
    paths += list((HERE / 'admin').glob('*.py'))
    paths += [HERE / name for name in ('ADMINISTRATOR_PLAN.md', 'PLAN.md', 'PLAN.json', 'BASELINE.json',
        'SCORING_PLAN.md', 'RUNTIME_INTERFACE_CHECK.json', 'admin/TRUTH.json',
        'admin/SCORING_CONTRACT.json', 'admin/NORMALIZATION_SCHEMA.json')]
    for path in paths:
        if path.is_file():
            sources[str(path.resolve())] = sha(path)
    for arm in ('A', 'B'):
        binding = read(plan['products'][arm]['path'])
        if len(binding['source_manifest']) != 141:
            raise ValueError('fixed_141_product_manifest:' + arm)
        install = Path(binding['install_root']).resolve()
        for row in binding['source_manifest']:
            source = (install / row['path']).resolve()
            if not source.is_relative_to(install):
                raise ValueError('product_source_path')
            sources[str(source)] = row['sha256']
            if arm == 'B':
                sources[str((ROOT / row['path']).resolve())] = row['sha256']
        for source in install.glob('*.dist-info/*'):
            if source.is_file():
                sources[str(source)] = sha(source)
    for path, expected in sources.items():
        if sha(path) != expected:
            raise ValueError('execution_source_changed:' + path)
    return sources


def verify_frozen(sources):
    path = HERE / 'FROZEN.json'
    frozen = read(path)
    if any(frozen['files_sha256'].get(p) != h for p, h in sources.items()):
        raise ValueError('required_source_missing_from_current_freeze')
    for source, expected in frozen['files_sha256'].items():
        if sha(source) != expected:
            raise ValueError('current_frozen_source_changed:' + source)
    return frozen


def connect_slot(plan, slot, group):
    arm = slot[0]
    if (slot, group) not in SEQUENCE or group != 'P':
        raise ValueError('registered_product_slot')
    selected_plan = dict(plan, comparison_arm=arm)
    selected_plan['inputs'] = dict(plan['inputs'], input_manifest=plan['inputs']['manifests'][arm])
    old = previous.old_launcher()
    driver = old.connect(selected_plan, 'formal')
    accepted_route = driver.run_route
    accepted_launch = accepted_route.__globals__['launch']

    def python_command(entry, arguments):
        if Path(entry).resolve() != HERE / 'actor.py':
            raise ValueError('registered_actor_alias')
        command = accepted_launch.python_command(previous.OLD / 'actor.py', arguments)
        config_path = Path(arguments[arguments.index('--config') + 1])
        config = read(config_path)
        if (config['group'] != 'P' or config['phase'] != 'formal'
                or config['phase_render_cap'] != 36 or config['whole_render_cap'] != 44
                or Path(config['output']).resolve() != EXTERNAL / 'formal' / slot / 'o'
                or Path(config['input_manifest']).resolve() != Path(plan['inputs']['manifests'][arm]).resolve()):
            raise ValueError('actual_arm_command_before_adjustment')
        config.update(whole_render_cap=48, comparison_arm=arm,
            expected_product_source_sha256=read(plan['products'][arm]['path'])['source_sha256'])
        config['runtime_binding']['shared_dependency'] = shared_dependency()
        save(config_path, config)
        command[5:7] = [str(HERE / 'bootstrap.py'), str(HERE / 'bridge.py')]
        return command

    launch = types.SimpleNamespace(BASE=accepted_launch.BASE, BASE_SHA256=accepted_launch.BASE_SHA256,
        stop_process=accepted_launch.stop_process, python_command=python_command)
    selected = old.clone(accepted_route, {'HERE': HERE,
        'input_checks': lambda value: input_checks(value, arm), 'launch': launch})

    def invoke(selected_slot, selected_group, unused_plan, runtime):
        if selected_slot != slot or selected_group != 'P':
            raise ValueError('comparison_dispatch_slot_binding')
        row = selected(slot, 'P', selected_plan, runtime)
        row['comparison_arm'] = arm
        row['comparison_product_source_sha256'] = read(plan['products'][arm]['path'])['source_sha256']
        return row

    checks = dict(route_code_reused=selected.__code__ is accepted_route.__code__,
        route_consumer_reused=selected.__globals__['consumer'] is driver.consumer,
        original_launch_unchanged=accepted_route.__globals__['launch'] is accepted_launch,
        common_internal_role_P=True)
    def proof():
        if (not all(checks.values()) or selected.__globals__['launch'] is not launch
                or driver.run_route is not accepted_route):
            raise ValueError('accepted_route_reference_chain_changed')
        return dict(schema='source-face-binding-entry-proof-v1', slot=slot, group='P',
            comparison_arm=arm, checks=checks, accepted_connect_time_snapshot=driver.pointers,
            current_route_source=accepted_route.__code__.co_filename,
            current_route_source_sha256=sha(accepted_route.__code__.co_filename),
            source_guard_binding=plan['products'][arm], comparison_dispatch='Only product binding/input manifest varies by arm; actual tool role P is shared.')
    # Expose the actual command constructor for offline preparation checks.
    invoke.command_factory = python_command
    return invoke, proof


def require_qualification(plan):
    path = Path(plan['inputs']['qualification']).resolve()
    value = read(path)
    if (value.get('passed') is not True or value.get('status') != 'qualified'
            or value.get('source_freeze_sha256') != sha(HERE / 'FROZEN.json')):
        raise ValueError('final_candidate_qualification_required')
    spec = value['qualification_run']
    run_path = Path(spec['path']).resolve()
    if not run_path.is_relative_to(EXTERNAL / 'preparation') or sha(run_path) != spec['sha256']:
        raise ValueError('actual_qualification_run_binding')
    run = read(run_path)
    if (not run['transport_passed'] or run['actual_model_calls'] != 0
            or run['actual_product_calls'] != 2 or run['source_freeze_sha256'] != sha(HERE / 'FROZEN.json')
            or [r['comparison_arm'] for r in run['records']] != ['A', 'B']):
        raise ValueError('final_source_actual_paired_qualification')
    intents = [read(p) for p in sorted((EXTERNAL / 'raster_budget').glob('attempt_*/INTENT.json'))]
    if (len(intents) > 12 or any(r['phase'] != 'preparation' for r in intents)
            or [r['global_attempt'] for r in intents] != list(range(1, len(intents)+1))):
        raise ValueError('cumulative_qualification_budget')
    return dict(path=str(path), sha256=sha(path), qualification_run=spec,
                cumulative_qualified_phase_rasters=len(intents))


def check_slot_facts(slot, group, runtime):
    started = time.perf_counter_ns()
    owner = runtime / slot / 'o'
    spec = importlib.util.spec_from_file_location('_m1_saved_fact_check', HERE / 'saved_evidence.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    errors, blockers, summary = [], [], None
    try:
        value = module.evaluate_owner(owner, read(HERE / 'admin/TRUTH.json'))
        summary = module.summary(value)
        if value['product_errors']:
            blockers.append(dict(reason='current_product_facts_wrong', product_errors=value['product_errors']))
    except BaseException as error:
        errors.append(error_record(error, 'saved_fact_check'))
        reason = 'current_product_facts_wrong' if isinstance(error, module.ProductFactError) else 'saved_owner_source_proof_failed'
        blockers.append(dict(reason=reason, errors=errors))
    path = runtime / 'slot_records' / slot / 'FACT_CHECK.json'
    closed = time.perf_counter_ns()
    save(path, dict(schema='source-face-binding-between-slot-fact-check-v1', slot=slot, group='P',
        comparison_arm=slot[0], passed=not blockers, evidence_summary=summary, errors=errors,
        stop_reasons=blockers, actual_model_product_raster_calls=0, started_ns=started,
        before_publication_ns=closed, elapsed_ns=closed-started,
        scope='Offline administrator facts after the unchanged complete slot clock, inside batch coordination.'), exclusive=True)
    return dict(path=str(path), sha256=sha(path), passed=not blockers, elapsed_ns=closed-started), blockers


def run_formal(plan, preparation_git):
    started = time.perf_counter_ns()
    runtime = EXTERNAL / 'formal'
    runtime.mkdir(parents=True, exist_ok=False)
    records, terminal, publication_errors = [], [], []
    stopped = None
    context = dict(preparation_git=preparation_git, freeze_sha256=sha(HERE / 'FROZEN.json'))
    try:
        sources = source_file_list(plan)
        verify_frozen(sources)
        if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != preparation_git:
            raise ValueError('fixed_preparation_commit_required')
        if plan.get('model_consumer_enabled') is not True:
            raise ValueError('formal_provider_flag_required')
        context['qualification'] = require_qualification(plan)
        save(HERE / 'FORMAL_STARTED.json', dict(started_ns=time.perf_counter_ns(), **context,
            sequence=plan['sequence'], maximum_provider_sessions=6, outer_retries=0), exclusive=True)
        for slot, group in SEQUENCE:
            if stopped:
                records.append(dict(slot=slot, group=group, comparison_arm=slot[0], execution_state='not_run',
                    route_invoked=False, stop_reasons=stopped))
                continue
            row = run_slot(plan, slot, group, runtime)
            row['comparison_arm'] = slot[0]
            row['batch_stop_reasons'] = ACCEPTED_ROUTED.batch_blockers(row)
            records.append(row)
            if row['execution_state'] == 'completed':
                fact_check, blockers = check_slot_facts(slot, group, runtime)
                row['between_slot_fact_check'] = fact_check
                row['batch_stop_reasons'].extend(blockers)
            if row['batch_stop_reasons']:
                stopped = row['batch_stop_reasons']
    except BaseException as error:
        terminal.append(error_record(error, 'batch_checks_or_execution'))
        stopped = [dict(reason='batch_entry_or_execution_failed', errors=terminal)]
    finally:
        for slot, group in SEQUENCE[len(records):]:
            records.append(dict(slot=slot, group=group, comparison_arm=slot[0], execution_state='not_run',
                route_invoked=False, stop_reasons=stopped or terminal))
        result = ACCEPTED_ROUTED.aggregate(records, started)
        result.update(schema='source-face-binding-six-route-v1', comparison_sequence=plan['sequence'],
            internal_execution_group='P', terminal_errors=terminal, stop_remaining_reasons=stopped,
            maximum_qualification_and_formal_raster_attempts=48)
        ledger = [read(p) for p in sorted((EXTERNAL / 'raster_budget').glob('attempt_*/INTENT.json'))]
        result['preparation_raster_attempts'] = sum(r['phase'] == 'preparation' for r in ledger)
        launch = dict(schema='source-face-binding-launch-v1', **context,
            actual_routes=result['actual_routes'], actual_CLI_processes=result['actual_CLI_processes'],
            execution_states={r['slot']:r['execution_state'] for r in records},
            comparison_arms={s:s[0] for s,_ in SEQUENCE}, internal_execution_group='P',
            terminal_errors=terminal, stop_remaining_reasons=stopped, outer_retries=0)
        for name, value in [('RUN_RESULT.json', result), ('LAUNCH_RESULT.json', launch)]:
            try:
                save(runtime / name, value, exclusive=True)
            except BaseException as error:
                publication_errors.append(error_record(error, 'publish_' + name))
        closed = time.perf_counter_ns()
        save(runtime / 'BATCH_TIMING.json', dict(started_ns=started, aggregate_results_closed_ns=closed,
            elapsed_ns=closed-started, terminal_errors=terminal, publication_errors=publication_errors,
            scope='Whole formal call through checks, serial common run_slot calls, offline fact checks and aggregate publication. Slot/route/consumer clocks are nested.'), exclusive=True)
    result['launcher_publication_errors'] = publication_errors
    return result


run_slot = ACCEPTED_OLD.clone(ACCEPTED_ROUTED.run_slot, dict(HERE=HERE,
    source_file_list=source_file_list, verify_frozen=verify_frozen, connect_slot=connect_slot))
if run_slot.__code__ is not ACCEPTED_ROUTED.run_slot.__code__:
    raise ValueError('accepted_common_slot_clock_code')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-models', action='store_true', required=True)
    parser.add_argument('--preparation-git', required=True)
    args = parser.parse_args()
    result = run_formal(read(HERE / 'PLAN.json'), args.preparation_git)
    print(json.dumps({k:result[k] for k in ('schema', 'actual_routes', 'actual_CLI_processes', 'terminal_errors', 'stop_remaining_reasons')}))
    return 0 if all(r['execution_state']=='completed' for r in result['records']) and not result['terminal_errors'] and not result['stop_remaining_reasons'] and not result['launcher_publication_errors'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
