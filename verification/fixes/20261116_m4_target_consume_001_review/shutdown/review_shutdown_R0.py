"""Audit saved teardown and compare the exact thin adapter under local pipes."""

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time


HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
SOURCE = AUTHOR / 'verification/native_plugin_complex_003/reused/stdio_attach.py'
RUN = Path('D:/he_m4_target_consume_001/formal')
EXPECTED_SHA = '210539d6a728fd63cc8f8b3925bb866e1929dce4a8e5db85a7ceece7c183cb00'
CHECKS = []


def check(value, label):
    CHECKS.append(label)
    if not value:
        raise AssertionError(label)


def load(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def saved_evidence():
    rows = []
    for label in ('N1', 'P1', 'P2', 'N2', 'N3', 'P3'):
        folder = RUN / label
        consumer = load(folder / 'consumer/CONSUMER.json')
        slot = load(folder / 'SLOT_RESULT.json')
        runtime_exit = consumer['runtime_exit']
        cleanup = consumer['process_cleanup']
        binding = consumer['runtime_binding']
        check(binding['confirmed'] and binding['actual_executable_sha256'] ==
              '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869', label + ' thin identity')
        check(runtime_exit['confirmed'] and runtime_exit['exited'] and runtime_exit['handle_closed']
              and runtime_exit['error'] is None and runtime_exit['exit_code'] == 1, label + ' retained thin exit')
        check(cleanup['confirmed'] and cleanup['reaped'] and cleanup['exit_code'] == 0
              and not cleanup['kill_requested'] and not cleanup['errors'], label + ' CLI original handle clean')
        check(consumer['exit_code'] == 0 and consumer['readers_stopped'] and
              not consumer['deadline_timer_fired'] and not consumer['errors'], label + ' reader and deadline state')
        check(consumer['safe_to_continue'] and consumer['valid_completion'] and
              not consumer['mutation_unknown'] and not consumer['bridge_protocol_errors'], label + ' accepted closure state')
        attaches = list((folder / 'consumer/attachments').glob('bridge_*'))
        check(len(attaches) == 1, label + ' exactly one thin runtime')
        attach = attaches[0]
        started = load(attach / 'STARTED.json')
        check(started['pid'] == binding['runtime_pid'], label + ' STARTED matches retained process')
        check(not (attach / 'EXIT.json').exists(), label + ' missing EXIT preserved')
        requests = []
        for call in sorted(path for path in attach.iterdir() if path.is_dir()):
            tx = load(call / 'TX.bin')
            if 'id' in tx:
                check((call / 'RX.bin').exists(), label + '/' + call.name + ' response saved')
                rx = load(call / 'RX.bin')
                check(type(rx['id']) is type(tx['id']) and rx['id'] == tx['id'],
                      label + '/' + call.name + ' complete request-response ID')
                requests.append(tx)
            else:
                check(not (call / 'RX.bin').exists(), label + '/' + call.name + ' notification has no response')
        business = [request for request in requests if request['method'] == 'tools/call']
        check(len(business) == len(consumer['tool_calls']), label + ' every public tool has response')
        check(len(consumer['raw_usage_events']) == 1 and consumer['final'] and
              consumer['cli_output_matches_public_final'], label + ' complete final and usage')
        tool_completed = [row['perf_ns'] for row in consumer['tool_calls']]
        check(max(tool_completed) <= consumer['final_received_ns'] <= consumer['turn_completed_ns']
              <= consumer['process_exit_ns'] <= runtime_exit['started_ns'] <= runtime_exit['closed_ns']
              < slot['clocks']['slot_completed_ns'], label + ' observed close after all completed work')
        actor_close = slot['cleanup']['actor_close']
        check(not actor_close['errors'] and actor_close['bridge']['confirmed'] and
              not actor_close['bridge']['errors'], label + ' actor and listener closed')
        actor_runtime = actor_close['runtime']
        check(actor_runtime['Blender_close']['exit_code'] == 0 and
              actor_runtime['Blender_close']['process_reaped'], label + ' Blender exited and reaped')
        if label.startswith('P'):
            check(actor_runtime['MCP_stdio_close']['confirmed'] and
                  actor_runtime['MCP_stdio_close']['exit_code'] == 0 and
                  actor_runtime['MCP_retained_exit']['confirmed'] and
                  actor_runtime['MCP_retained_exit']['exit_code'] == 0, label + ' product MCP clean')
        rows.append(dict(slot=label, business_calls=len(business), metadata_calls=len(requests)-len(business),
                         adapter_pid=started['pid'], adapter_exit_code=runtime_exit['exit_code'],
                         EXIT_present=False, CLI_exit_code=consumer['exit_code'],
                         turn_completed_ns=consumer['turn_completed_ns'],
                         CLI_process_exit_observed_ns=consumer['process_exit_ns'],
                         held_adapter_exit_observed_ns=runtime_exit['closed_ns'],
                         held_wait_elapsed_ns=runtime_exit['elapsed_ns'],
                         final_complete=True, all_tool_responses_complete=True,
                         adapter_shutdown_cause='not recorded by existing evidence'))
    return rows


def local_adapter_case(mode):
    folder = HERE / ('local_' + mode)
    folder.mkdir(exist_ok=False)
    fake_calls = []
    server_errors = []
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(5)
        endpoint_path = folder / 'ENDPOINT.json'
        save(endpoint_path, dict(host='127.0.0.1', port=listener.getsockname()[1],
                                 chain_deadline_ns=time.perf_counter_ns()+10_000_000_000))

        def serve():
            try:
                connection, _ = listener.accept()
                with connection:
                    data = bytearray()
                    while True:
                        block = connection.recv(65536)
                        if not block:
                            break
                        data.extend(block)
                    request = json.loads(data)
                    fake_calls.append(request)
                    message = request['args']['message']
                    result = dict(jsonrpc='2.0', id=message['id'], result={'ack': 'local fake broker'})
                    response = dict(request_id=request['request_id'], ok=True, result=result)
                    connection.sendall(json.dumps(response).encode('utf8'))
            except BaseException as error:
                server_errors.append(repr(error))

        thread = None
        if mode == 'rpc_then_EOF':
            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
        command = [sys.executable, '-I', '-B', str(SOURCE), '--endpoint', str(endpoint_path),
                   '--kind', 'native', '--audit', str(folder / 'attachments')]
        started_ns = time.perf_counter_ns()
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 5
        while not list((folder / 'attachments').glob('bridge_*/STARTED.json')):
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('local STARTED not observed')
            time.sleep(.005)
        if mode == 'forced_terminate':
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
        elif mode == 'rpc_then_EOF':
            message = dict(jsonrpc='2.0', id='local-ping', method='ping')
            stdout, stderr = process.communicate(json.dumps(message).encode('utf8')+b'\n', timeout=5)
        elif mode == 'malformed_then_EOF':
            stdout, stderr = process.communicate(b'{invalid-json}\n', timeout=5)
        else:
            stdout, stderr = process.communicate(b'', timeout=5)
        ended_ns = time.perf_counter_ns()
        if thread is not None:
            thread.join(timeout=5)
            check(not thread.is_alive() and not server_errors, mode + ' fake broker complete')
        (folder / 'STDOUT.bin').write_bytes(stdout)
        (folder / 'STDERR.bin').write_bytes(stderr)
        receipts = list((folder / 'attachments').glob('bridge_*/EXIT.json'))
        check(len(receipts) <= 1, mode + ' receipt count')
        receipt = load(receipts[0]) if receipts else None
        if mode == 'forced_terminate':
            check(process.returncode == 1 and receipt is None, mode + ' exit1 no finally')
        elif mode == 'malformed_then_EOF':
            check(process.returncode == 1 and receipt and receipt['normal_exit'] is False
                  and b'JSONDecodeError' in stderr, mode + ' exception still produces EXIT')
        else:
            check(process.returncode == 0 and receipt and receipt['normal_exit'] is True
                  and not stderr, mode + ' graceful exit0 receipt')
        if mode == 'rpc_then_EOF':
            check(len(fake_calls) == 1 and json.loads(stdout)['result']['ack'] == 'local fake broker'
                  and receipt['requests'] == 1, mode + ' one execution and delivered reply')
        row = dict(mode=mode, pid=process.pid, command=command, exit_code=process.returncode,
                   EXIT_receipt=receipt, stdout_bytes=len(stdout), stderr_bytes=len(stderr),
                   started_ns=started_ns, ended_ns=ended_ns, fake_broker_calls=len(fake_calls),
                   model_calls=0, Blender_calls=0, raster_calls=0, paid_calls=0)
        save(folder / 'RESULT.json', row)
        return row


def main():
    check(hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED_SHA, 'original thin source SHA')
    saved = saved_evidence()
    local = [local_adapter_case(mode) for mode in ('EOF', 'rpc_then_EOF', 'malformed_then_EOF', 'forced_terminate')]
    result = dict(status='passed', checks=len(CHECKS), source=str(SOURCE), source_sha256=EXPECTED_SHA,
                  saved_slots=saved, local_controls=local,
                  conclusion='Saved task results and actual closure confirmed; abrupt host termination explains signature but initiator not proved.',
                  new_model_calls=0, new_Blender_calls=0, new_raster_calls=0, new_paid_calls=0)
    save(HERE / 'RESULT.json', result)
    print(json.dumps({key: result[key] for key in ('status', 'checks', 'new_model_calls', 'new_Blender_calls')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
