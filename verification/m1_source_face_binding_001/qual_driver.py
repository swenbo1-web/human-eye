"""One retained TCP owner per product arm, with cumulative qualification charging."""

import argparse
import importlib.util
from pathlib import Path
import json
import subprocess
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_m1_qualification_launcher', HERE / 'launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
rpc_spec = importlib.util.spec_from_file_location('_m1_retained_qualification_rpc',
    launcher.LEGACY_ROOT / 'verification/m4_complete_witness_consumption_001/qual_driver.py')
retained = importlib.util.module_from_spec(rpc_spec)
rpc_spec.loader.exec_module(retained)
rpc = retained.rpc
EXTERNAL = launcher.EXTERNAL


def run_owner(plan, arm, attempt_root):
    started = time.perf_counter_ns()
    deadline_ns = started + 450_000_000_000
    output = attempt_root / ('Q' + arm)
    output.mkdir(parents=True, exist_ok=False)
    process = None
    process_cleanup = None
    close = metrics = observations = endpoint = command = None
    errors = []
    runtime = launcher.runtime_bindings()
    manifest_path = Path(plan['inputs']['manifests'][arm])
    manifest = launcher.read(manifest_path)
    binding = launcher.read(manifest['product_binding']['path'])
    config = dict(group='P', comparison_arm=arm, expected_product_source_sha256=binding['source_sha256'],
        output=str(output / 'o'), endpoint=str(output / 'ENDPOINT.json'),
        worker_deadline_ns=deadline_ns, input_manifest=str(manifest_path), max_tool_calls=12,
        max_render_attempts=6, phase='preparation', budget_root=manifest['budget_contract']['ledger_root'],
        whole_render_cap=48, phase_render_cap=12,
        runtime_binding=dict(binding=manifest['product_binding'], verified_bootstrap=runtime['verified_bootstrap'],
            shared_dependency=launcher.shared_dependency()))
    config_path = output / 'ACTOR_CONFIG.json'
    launcher.save(config_path, config, exclusive=True)
    command = [runtime['base_python']['path'], '-I', '-B', '-X', 'utf8', str(HERE / 'bootstrap.py'),
        str(HERE / 'bridge.py'), '--config', str(config_path)]
    cleanup = retained.cleanup_function()
    try:
        with (output / 'ACTOR_STDOUT.bin').open('wb') as stdout, (output / 'ACTOR_STDERR.bin').open('wb') as stderr:
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                    cwd=output, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                while time.perf_counter_ns() < deadline_ns:
                    path = output / 'ENDPOINT.json'
                    if path.exists():
                        endpoint = launcher.read(path)
                        if endpoint['actor_pid'] != process.pid:
                            raise ValueError('actual_qualification_actor_PID')
                        break
                    if process.poll() is not None:
                        raise RuntimeError('qualification_actor_exit_before_endpoint')
                    time.sleep(.05)
                if endpoint is None:
                    raise TimeoutError('qualification_endpoint_deadline')
                requests = [
                    dict(jsonrpc='2.0', id=1, method='initialize', params=dict(protocolVersion='2025-03-26')),
                    dict(jsonrpc='2.0', id=2, method='tools/list', params={}),
                    dict(jsonrpc='2.0', id=3, method='tools/call',
                        params=dict(name='active_observation', arguments=dict(include_images=True))),
                    dict(jsonrpc='2.0', id=4, method='tools/call', params=dict(name='execute_python', arguments=dict(code=
                        "print(render_views([next(n for n in ['SCENE','TOP','LEFT','RIGHT','FRONT','BACK'] if n in buffers)],include_images=True,fresh=False))")))
                ]
                for message in requests:
                    response = rpc(endpoint, message, output, deadline_ns)
                    launcher.save(output / ('MCP_RESPONSE_' + str(message['id']).zfill(2) + '.json'), response, exclusive=True)
                    if message['method'] == 'tools/call' and response.get('result', {}).get('isError') is not False:
                        raise ValueError('qualification_business_tool_error_' + str(message['id']))
                    if message['id'] == 3:
                        before = launcher.read(output / 'o/OBSERVATIONS.json')
                        launcher.save(output / 'METRICS_BEFORE_REPEAT.json', dict(common=before['metrics'],
                            source='Closed tool3 OBSERVATIONS before repeat request4.'), exclusive=True)
            finally:
                if process is not None:
                    try:
                        if process.poll() is None:
                            process.stdin.write(b'\n')
                            process.stdin.flush()
                            process.wait(timeout=max(.01, min(10, (deadline_ns-time.perf_counter_ns())/1e9)))
                    except BaseException as error:
                        errors.append(launcher.error_record(error, 'qualification_actor_EOF'))
                    process_cleanup = cleanup(process, timeout=5)
    except BaseException as error:
        errors.append(launcher.error_record(error, 'qualification_owner'))
    finally:
        for filename in ('CLOSE.json', 'METRICS.json', 'OBSERVATIONS.json'):
            path = output / 'o' / filename
            if not path.exists():
                continue
            try:
                value = launcher.read(path)
                if filename == 'CLOSE.json':
                    close = value
                elif filename == 'METRICS.json':
                    metrics = value
                else:
                    observations = value
            except BaseException as error:
                errors.append(launcher.error_record(error, 'read_actual_' + filename))
        counts = None if metrics is None else metrics['common']
        try:
            if (process_cleanup is None or process_cleanup['confirmed'] is not True
                    or process_cleanup['exit_code'] != 0 or close is None or close['confirmed'] is not True
                    or metrics['tool_attempts'] != 2):
                raise ValueError('qualification_actual_process_and_two_tools')
            if counts['product_observation_calls'] != 1 or not 1 <= counts['render_attempts'] <= 6:
                raise ValueError('qualification_owner_raster_and_product_counts')
            before = launcher.read(output / 'METRICS_BEFORE_REPEAT.json')['common']
            if counts['render_attempts'] != before['render_attempts']:
                raise ValueError('qualification_repeat_cache_hit_required')
        except BaseException as error:
            errors.append(launcher.error_record(error, 'qualification_owner_counts'))
        closed = time.perf_counter_ns()
        if closed >= deadline_ns:
            errors.append(launcher.error_record(TimeoutError('qualification_original_deadline'), 'qualification_deadline'))
        result = dict(schema='source-face-binding-owner-qualification-v1', group='P', comparison_arm=arm,
            transport_passed=not errors, errors=errors, actual_model_calls=0,
            actual_product_calls=None if counts is None else counts['product_observation_calls'],
            actual_rasters=None if counts is None else counts['render_attempts'],
            actual_business_tools=None if metrics is None else metrics['tool_attempts'],
            actual_MCP_requests=len(list(output.glob('request_*'))),
            successful_MCP_responses=len(list(output.glob('MCP_RESPONSE_*.json'))),
            actor_pid=None if process is None else process.pid, command=command, endpoint=endpoint,
            process_cleanup=process_cleanup, owner_close=close, owner_output=str(output / 'o'),
            input_manifest=dict(path=str(manifest_path), sha256=launcher.sha(manifest_path)),
            product_source_sha256=binding['source_sha256'],
            frames=None if observations is None else observations['frames'],
            source_inputs=None if observations is None else observations['source_inputs'],
            original_deadline_ns=deadline_ns, started_ns=started, closed_ns=closed,
            elapsed_ns=closed-started, outer_retries=0)
        launcher.save(output / 'QUALIFICATION_RUN.json', result, exclusive=True)
    return result


def run(plan, attempt):
    if len(attempt) != 3 or attempt[0] != 'Q' or not attempt[1:].isdigit() or int(attempt[1:]) < 1:
        raise ValueError('explicit_qualification_attempt_Qnn_required')
    preparation = EXTERNAL / 'preparation'
    preparation.mkdir(parents=True, exist_ok=True)
    output = preparation / attempt
    if output.exists():
        raise FileExistsError('qualification_attempt_cannot_be_repeated')
    prior_runs = []
    for prior in sorted(preparation.glob('Q[0-9][0-9]')):
        path = prior / 'QUALIFICATION_RUN.json'
        if not path.exists():
            raise ValueError('prior_qualification_execution_state_unknown')
        result = launcher.read(path)
        for owner in (prior / 'QA', prior / 'QB'):
            if owner.exists() and not (owner / 'QUALIFICATION_RUN.json').is_file():
                raise ValueError('prior_qualification_owner_execution_state_unknown')
        for record in result['records']:
            if record['actor_pid'] is not None and (record.get('process_cleanup') or {}).get('confirmed') is not True:
                raise ValueError('prior_qualification_process_state_unknown')
        prior_runs.append(dict(path=str(path), sha256=launcher.sha(path)))
    if int(attempt[1:]) != len(prior_runs) + 1:
        raise ValueError('qualification_attempt_sequence')
    output.mkdir(exist_ok=False)
    started = time.perf_counter_ns()
    records, errors = [], []
    sources = None
    try:
        sources = launcher.source_file_list(plan)
        launcher.verify_frozen(sources)
        intents = [launcher.read(p) for p in sorted((EXTERNAL / 'raster_budget').glob('attempt_*/INTENT.json'))]
        if (len(intents) >= 12 or any(r['phase'] != 'preparation' for r in intents)
                or [r['global_attempt'] for r in intents] != list(range(1, len(intents)+1))):
            raise ValueError('persistent_qualification_budget_exhausted_or_unknown')
        launcher.save(output / 'STARTED.json', dict(started_ns=started,
            source_freeze_sha256=launcher.sha(HERE / 'FROZEN.json'), prior_runs=prior_runs,
            cumulative_qualification_rasters_before=len(intents), max_cumulative_qualification_rasters=12,
            maximum_model_consumers=0, order=['A','B'], outer_retries=0), exclusive=True)
        for arm in ('A', 'B'):
            record = run_owner(plan, arm, output)
            records.append(record)
            if not record['transport_passed']:
                break
        if len(records) != 2 or any(not r['transport_passed'] for r in records):
            raise ValueError('both_qualification_arms_required')
    except BaseException as error:
        errors.append(launcher.error_record(error, 'qualification_pair'))
    finally:
        try:
            if sources is not None:
                launcher.verify_frozen(sources)
                if sources != launcher.source_file_list(plan):
                    raise ValueError('source_changed_during_qualification')
        except BaseException as error:
            errors.append(launcher.error_record(error, 'qualification_source_readback'))
        intents = [launcher.read(p) for p in sorted((EXTERNAL / 'raster_budget').glob('attempt_*/INTENT.json'))]
        known = all(type(r['actual_rasters']) is int for r in records)
        closed = time.perf_counter_ns()
        value = dict(schema='source-face-binding-paired-qualification-run-v1', attempt=attempt,
            transport_passed=not errors and len(records)==2, semantic_status='unscored_saved_verification_required',
            records=records, errors=errors, prior_attempts=prior_runs, planned_owners=2, actual_owners=len(records),
            unrun_arms=[a for a in ('A','B') if a not in {r['comparison_arm'] for r in records}],
            actual_model_calls=0, actual_product_calls=sum(r['actual_product_calls'] or 0 for r in records),
            actual_rasters=sum(r['actual_rasters'] for r in records) if known else None,
            cumulative_preparation_rasters=len(intents), maximum_qualification_rasters=12,
            maximum_batch_rasters=48, source_freeze_sha256=launcher.sha(HERE / 'FROZEN.json'),
            source_inputs_sha256=sources, outer_retries=0, started_ns=started,
            closed_ns=closed, elapsed_ns=closed-started,
            scope='Two fresh isolated product owners. All attempts share one persistent12 qualification ledger and task48 budget.')
        launcher.save(output / 'QUALIFICATION_RUN.json', value, exclusive=True)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualify', action='store_true', required=True)
    parser.add_argument('--attempt', required=True)
    args = parser.parse_args()
    result = run(launcher.read(HERE / 'PLAN.json'), args.attempt)
    print(json.dumps({k:result[k] for k in ('transport_passed','actual_owners','actual_rasters','cumulative_preparation_rasters')}))
    return 0 if result['transport_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
