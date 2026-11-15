"""One paired zero-model qualification through the actual common TCP tools."""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_transfer_qualification_launcher', HERE / 'launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
old_spec = importlib.util.spec_from_file_location('_transfer_retained_qualification_rpc',
    HERE.with_name('m4_complete_witness_consumption_001') / 'qual_driver.py')
retained = importlib.util.module_from_spec(old_spec)
old_spec.loader.exec_module(retained)
rpc = retained.rpc
EXTERNAL = launcher.EXTERNAL
VIEWS = ['SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK']


def run_owner(plan, group):
    started = time.perf_counter_ns()
    deadline_ns = started + 450_000_000_000
    output = EXTERNAL / 'preparation' / ('QN' if group == 'N' else 'QP')
    output.mkdir(parents=True, exist_ok=False)
    process = None
    process_cleanup = None
    close = metrics = observations = endpoint = command = None
    errors = []
    runtime = launcher.runtime_bindings()
    manifest = launcher.read(plan['inputs']['input_manifest'])
    config = dict(group=group, output=str(output/'o'), endpoint=str(output/'ENDPOINT.json'),
        worker_deadline_ns=deadline_ns, input_manifest=plan['inputs']['input_manifest'],
        max_tool_calls=12, max_render_attempts=6, phase='preparation',
        budget_root=manifest['budget_contract']['ledger_root'], whole_render_cap=48, phase_render_cap=12,
        runtime_binding=dict(binding=manifest['product_binding'], verified_bootstrap=runtime['verified_bootstrap'],
            shared_dependency=launcher.shared_dependency()))
    config_path = output/'ACTOR_CONFIG.json'
    launcher.save(config_path, config, exclusive=True)
    command = [runtime['base_python']['path'], '-I', '-B', '-X', 'utf8', str(HERE/'bootstrap.py'),
               str(HERE/'bridge.py'), '--config', str(config_path)]
    cleanup = retained.cleanup_function()
    try:
        with (output/'ACTOR_STDOUT.bin').open('wb') as stdout, (output/'ACTOR_STDERR.bin').open('wb') as stderr:
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                    cwd=output, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                while time.perf_counter_ns() < deadline_ns:
                    path = output/'ENDPOINT.json'
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
                business = (dict(name='render_views', arguments=dict(names=VIEWS, include_images=True, fresh=False))
                    if group == 'N' else dict(name='active_observation', arguments=dict(include_images=True)))
                repeat = (dict(name='render_views', arguments=dict(names=['SCENE'], include_images=True, fresh=False))
                    if group == 'N' else dict(name='execute_python', arguments=dict(code=
                        "print(render_views([next(n for n in ['SCENE','TOP','LEFT','RIGHT','FRONT','BACK'] if n in buffers)],include_images=True,fresh=False))")))
                requests = [dict(jsonrpc='2.0', id=1, method='initialize', params=dict(protocolVersion='2025-03-26')),
                    dict(jsonrpc='2.0', id=2, method='tools/list', params={}),
                    dict(jsonrpc='2.0', id=3, method='tools/call', params=business),
                    dict(jsonrpc='2.0', id=4, method='tools/call', params=repeat)]
                for message in requests:
                    response = rpc(endpoint, message, output, deadline_ns)
                    launcher.save(output/('MCP_RESPONSE_' + str(message['id']).zfill(2) + '.json'), response, exclusive=True)
                    if message['method'] == 'tools/call' and response.get('result', {}).get('isError') is not False:
                        raise ValueError('qualification_business_tool_error_' + str(message['id']))
                    if message['id'] == 3:
                        # OBSERVATIONS is closed before the tool response and
                        # transport accounting does not rewrite it afterward.
                        before = launcher.read(output/'o/OBSERVATIONS.json')
                        launcher.save(output/'METRICS_BEFORE_REPEAT.json', dict(common=before['metrics'],
                            source='Closed tool3 OBSERVATIONS, before sending repeat request4.'), exclusive=True)
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
            path = output/'o'/filename
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
            if (counts['product_observation_calls'] != int(group == 'P')
                    or not 1 <= counts['render_attempts'] <= 6
                    or (group == 'N' and counts['render_attempts'] != 6)):
                raise ValueError('qualification_owner_raster_and_product_counts')
            before = launcher.read(output/'METRICS_BEFORE_REPEAT.json')['common']
            if counts['render_attempts'] != before['render_attempts']:
                raise ValueError('qualification_repeat_cache_hit_required')
        except BaseException as error:
            errors.append(launcher.error_record(error, 'qualification_owner_counts'))
        closed = time.perf_counter_ns()
        if closed >= deadline_ns:
            errors.append(launcher.error_record(TimeoutError('qualification_original_deadline_through_cleanup'), 'qualification_deadline'))
        result = dict(schema='occluded-transfer-owner-qualification-v1', group=group,
            transport_passed=not errors, errors=errors, actual_model_calls=0,
            actual_product_calls=None if counts is None else counts['product_observation_calls'],
            actual_rasters=None if counts is None else counts['render_attempts'],
            actual_business_tools=None if metrics is None else metrics['tool_attempts'],
            actual_MCP_requests=len(list(output.glob('request_*'))),
            successful_MCP_responses=len(list(output.glob('MCP_RESPONSE_*.json'))),
            actor_pid=None if process is None else process.pid, command=command, endpoint=endpoint,
            process_cleanup=process_cleanup, owner_close=close,
            owner_output=str(output/'o'), frames=None if observations is None else observations['frames'],
            source_inputs=None if observations is None else observations['source_inputs'],
            original_deadline_ns=deadline_ns, started_ns=started, closed_ns=closed, elapsed_ns=closed-started,
            cache_hit_reread='request4 reuses one frame from request3 in the same process', outer_retries=0)
        launcher.save(output/'QUALIFICATION_RUN.json', result, exclusive=True)
    return result


def run(plan):
    started = time.perf_counter_ns()
    output = EXTERNAL/'preparation'
    output.mkdir(parents=True, exist_ok=False)
    records, errors = [], []
    sources = None
    try:
        sources = launcher.source_file_list(plan)
        launcher.verify_frozen(sources)
        ledger = EXTERNAL/'raster_budget'
        if ledger.exists() and any(ledger.iterdir()):
            raise ValueError('fresh_paired_qualification_ledger_required')
        launcher.save(HERE/'QUALIFICATION_STARTED.json', dict(started_ns=started,
            source_freeze_sha256=launcher.sha(HERE/'FROZEN.json'), maximum_model_consumers=0,
            maximum_product_calls=1, maximum_rasters=12, order=['N', 'P'], outer_retries=0), exclusive=True)
        for group in ('N', 'P'):
            record = run_owner(plan, group)
            records.append(record)
            if not record['transport_passed']:
                break
        if len(records) != 2 or any(not row['transport_passed'] for row in records):
            raise ValueError('both_qualification_owners_required')
    except BaseException as error:
        errors.append(launcher.error_record(error, 'qualification_pair'))
    finally:
        try:
            if sources is not None:
                launcher.verify_frozen(sources)
                if launcher.source_file_list(plan) != sources:
                    raise ValueError('source_changed_during_qualification')
        except BaseException as error:
            errors.append(launcher.error_record(error, 'qualification_source_readback'))
        closed = time.perf_counter_ns()
        counts_known = all(type(row['actual_rasters']) is int for row in records)
        result = dict(schema='occluded-transfer-paired-qualification-run-v1',
            transport_passed=not errors and len(records) == 2, semantic_status='unscored_offline_verifier_required',
            errors=errors, records=records, planned_owners=2, actual_owners=len(records),
            unrun_groups=[group for group in ('N', 'P') if group not in {row['group'] for row in records}],
            actual_model_calls=0, actual_product_calls=sum(row['actual_product_calls'] or 0 for row in records),
            actual_rasters=sum(row['actual_rasters'] for row in records) if counts_known else None,
            source_freeze_sha256=launcher.sha(HERE/'FROZEN.json'), source_inputs_sha256=sources,
            qualification_cache_scope='Two fresh isolated owner processes. Formal processes receive no qualification frames, caches or answers.',
            maximum_rasters=12, maximum_batch_rasters=48, outer_retries=0,
            started_ns=started, closed_ns=closed, elapsed_ns=closed-started)
        launcher.save(output/'QUALIFICATION_RUN.json', result, exclusive=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualify', action='store_true', required=True)
    parser.parse_args()
    result = run(launcher.read(HERE/'PLAN.json'))
    print(json.dumps({key: result[key] for key in ('transport_passed', 'actual_owners', 'actual_rasters')}))
    return 0 if result['transport_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
