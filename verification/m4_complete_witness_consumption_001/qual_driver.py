"""One real TCP actor qualification with zero model consumers."""

import argparse
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import time

_launcher_spec = importlib.util.spec_from_file_location(
    '_complete_witness_launcher', Path(__file__).resolve().with_name('launcher.py'))
launcher = importlib.util.module_from_spec(_launcher_spec)
_launcher_spec.loader.exec_module(launcher)


HERE = Path(__file__).resolve().parent
EXTERNAL = launcher.EXTERNAL
MAX_FRAME = 24 * 1024 * 1024


def cleanup_function():
    source = launcher.OLD_ROOT / 'verification/m4_active_coverage_003/launch.py'
    spec = importlib.util.spec_from_file_location('_complete_witness_accepted_cleanup', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.stop_process


def rpc(endpoint, message, output, deadline_ns):
    number = message['id']
    folder = output / ('request_' + str(number).zfill(2))
    folder.mkdir()
    request = dict(request_id=number, operation='attached_mcp', args=dict(kind='native', message=message))
    data = (json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')
    (folder / 'TCP_TX.bin').write_bytes(data)
    started = time.perf_counter_ns()
    received = bytearray()
    with socket.create_connection((endpoint['host'], endpoint['port']), timeout=max(.01, (deadline_ns-time.perf_counter_ns())/1e9)) as connection:
        connection.sendall(data)
        connection.shutdown(socket.SHUT_WR)
        while True:
            remaining = (deadline_ns-time.perf_counter_ns())/1e9
            if remaining <= 0:
                raise TimeoutError('original_qualification_deadline')
            connection.settimeout(min(30, remaining))
            block = connection.recv(65536)
            if not block:
                break
            received.extend(block)
            if len(received) > MAX_FRAME:
                raise ValueError('qualification_RPC_frame_limit')
    (folder / 'TCP_RX.bin').write_bytes(received)
    reply = json.loads(received)
    closed = time.perf_counter_ns()
    launcher.save(folder / 'RECEIPT.json', dict(started_ns=started, closed_ns=closed,
        elapsed_ns=closed-started, TCP_TX_bytes=len(data), TCP_RX_bytes=len(received),
        request_sha256=launcher.sha(folder/'TCP_TX.bin'), reply_sha256=launcher.sha(folder/'TCP_RX.bin')),
        exclusive=True)
    if reply.get('request_id') != number or reply.get('ok') is not True:
        raise ValueError('qualification_actor_RPC_failed')
    return reply['result']


def run(plan):
    started = time.perf_counter_ns()
    deadline_ns = started + 450_000_000_000
    output = EXTERNAL / 'preparation/Q1'
    output.mkdir(parents=True, exist_ok=False)
    process = None
    cleanup = None
    close = None
    endpoint = None
    sources = None
    response = None
    owner_metrics = None
    observations = None
    process_cleanup = None
    errors = []
    command = None
    try:
        sources = launcher.source_file_list(plan)
        launcher.verify_frozen(sources)
        ledger = EXTERNAL / 'raster_budget'
        if ledger.exists() and any(ledger.iterdir()):
            raise ValueError('fresh_global_qualification_ledger_required')
        launcher.save(HERE/'QUALIFICATION_STARTED.json', dict(started_ns=started,
            source_freeze_sha256=launcher.sha(HERE/'FROZEN.json'), maximum_product_calls=1,
            maximum_model_consumers=0, maximum_rasters=6, outer_retries=0), exclusive=True)
        runtime = launcher.runtime_bindings()
        manifest = launcher.read(plan['inputs']['input_manifest'])
        config = dict(group='P', output=str(output/'o'), endpoint=str(output/'ENDPOINT.json'),
            worker_deadline_ns=deadline_ns, input_manifest=plan['inputs']['input_manifest'],
            max_tool_calls=12, max_render_attempts=6, phase='preparation',
            budget_root=manifest['budget_contract']['ledger_root'], whole_render_cap=12, phase_render_cap=6,
            runtime_binding=dict(binding=manifest['product_binding'], verified_bootstrap=runtime['verified_bootstrap']))
        config_path = output/'ACTOR_CONFIG.json'
        launcher.save(config_path, config, exclusive=True)
        command = [runtime['base_python']['path'], '-I', '-B', '-X', 'utf8', str(HERE/'bootstrap.py'),
                   str(HERE/'bridge.py'), '--config', str(config_path)]
        cleanup = cleanup_function()
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
                requests = [dict(jsonrpc='2.0', id=1, method='initialize', params=dict(protocolVersion='2025-03-26')),
                            dict(jsonrpc='2.0', id=2, method='tools/list', params={}),
                            dict(jsonrpc='2.0', id=3, method='tools/call',
                                 params=dict(name='active_observation', arguments=dict(include_images=True)))]
                for message in requests:
                    response = rpc(endpoint, message, output, deadline_ns)
                    launcher.save(output/('MCP_RESPONSE_' + str(message['id']).zfill(2) + '.json'), response, exclusive=True)
                if response.get('result', {}).get('isError') is not False:
                    raise ValueError('qualification_active_tool_error')
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
        close = launcher.read(output/'o/CLOSE.json')
        owner_metrics = launcher.read(output/'o/METRICS.json')
        observations = launcher.read(output/'o/OBSERVATIONS.json')
        if (process_cleanup['confirmed'] is not True or process_cleanup['exit_code'] != 0
                or close['confirmed'] is not True or owner_metrics['tool_attempts'] != 1
                or owner_metrics['common']['product_observation_calls'] != 1
                or not 1 <= owner_metrics['common']['render_attempts'] <= 6):
            raise ValueError('qualification_counts_and_actual_cleanup')
    except BaseException as error:
        errors.append(launcher.error_record(error, 'qualification_driver'))
    finally:
        for name in ('CLOSE.json', 'METRICS.json', 'OBSERVATIONS.json'):
            path = output/'o'/name
            if not path.exists():
                continue
            try:
                value = launcher.read(path)
                if name == 'CLOSE.json':
                    close = value
                elif name == 'METRICS.json':
                    owner_metrics = value
                else:
                    observations = value
            except BaseException as error:
                errors.append(launcher.error_record(error, 'read_actual_' + name))
        try:
            if sources is not None:
                launcher.verify_frozen(sources)
                if launcher.source_file_list(plan) != sources:
                    raise ValueError('source_changed_during_qualification')
        except BaseException as error:
            errors.append(launcher.error_record(error, 'qualification_source_readback'))
        closed = time.perf_counter_ns()
        if closed >= deadline_ns:
            errors.append(launcher.error_record(
                TimeoutError('qualification_original_deadline_through_cleanup'), 'qualification_deadline'))
        counts = None if owner_metrics is None else owner_metrics['common']
        result = dict(schema='complete-witness-public-qualification-run-v1',
            passed=not errors and close is not None and close['confirmed'] is True,
            transport_passed=not errors and close is not None and close['confirmed'] is True,
            semantic_status='unscored_offline_verifier_required', errors=errors,
            source_freeze_sha256=launcher.sha(HERE/'FROZEN.json') if (HERE/'FROZEN.json').exists() else None,
            prompt_sha256=plan['expected_prompt_sha256'],
            source_inputs_sha256=sources, actual_model_calls=0,
            actual_product_calls=None if counts is None else counts['product_observation_calls'],
            actual_rasters=None if counts is None else counts['render_attempts'],
            actual_business_tools=None if owner_metrics is None else owner_metrics['tool_attempts'],
            actual_MCP_requests=len(list(output.glob('request_*'))),
            successful_MCP_responses=len(list(output.glob('MCP_RESPONSE_*.json'))),
            actor_pid=None if process is None else process.pid, command=command, endpoint=endpoint,
            actual_owner_pid=None if process is None else process.pid,
            process_cleanup=process_cleanup, owner_close=close,
            cleanup=dict(process=process_cleanup, owner=close),
            owner_output=str(output/'o'), service_result_path=str(output/'o/product_call_01/SERVICE_RESULT.json'),
            active_tool_response_path=str(output/'o/tool_01/RESPONSE.json'),
            public_MCP_response_path=str(output/'MCP_RESPONSE_03.json'),
            observations_path=str(output/'o/OBSERVATIONS.json'),
            observation_source_inputs=None if observations is None else observations['source_inputs'],
            frames=None if observations is None else observations['frames'],
            source_session_cache_scope='One fresh qualification process/output. Nothing is preloaded into the formal actor.',
            outer_retries=0, original_deadline_ns=deadline_ns,
            started_ns=started, closed_ns=closed, elapsed_ns=closed-started)
        launcher.save(output/'QUALIFICATION_RUN.json', result, exclusive=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualify', action='store_true', required=True)
    args = parser.parse_args()
    result = run(launcher.read(HERE/'PLAN.json'))
    print(json.dumps(dict(transport_passed=result['transport_passed'], actual_rasters=result['actual_rasters'],
                         result_path=str(EXTERNAL/'preparation/Q1/QUALIFICATION_RUN.json'))))
    return 0 if result['transport_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
