"""Preflight fresh consumer launch, original transport, and missing reply handling offline."""

from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from socketserver import BaseRequestHandler, TCPServer
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time
from unittest.mock import patch
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import costs
import driver


PREVIOUS = driver.NS.parent / 'perf050_dense_micro_surface_holdout_001'
DUAL = driver.NS.parent / 'perf050_dual_region_occlusion_transfer_001'
DUAL_RUN = Path('D:/he_perf050_dual_region_occlusion_transfer_001')
DUAL_COMMIT = 'ac593f97'
FORMAL_ORDER = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')


def require(test, message):
    if not test:
        raise ValueError(message)


def load_helpers(path):
    paths = sys.path[:]
    try:
        return run_path(str(path))
    finally:
        sys.path[:] = paths


def archived_wires(slot, pin):
    root, = (slot / 'consumer/attachments').glob('bridge_*')
    consumer = slot / 'consumer/CONSUMER.json'
    pin(consumer)
    recorded = costs.read(consumer)
    require(recorded['process_reaped'] is True and recorded['readers_stopped'] is True
            and recorded['runtime_exit']['confirmed'] is True and recorded['runtime_exit']['handle_closed'] is True,
            'original_CLI_process_did_not_close/' + slot.name)
    rows = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        receipt = costs.read(directory / 'RECEIPT.json')
        tx, rx = directory / 'TX.bin', directory / 'RX.bin'
        pin(directory / 'RECEIPT.json')
        pin(tx)
        request = tx.read_bytes()
        response = b''
        if rx.is_file():
            pin(rx)
            response = rx.read_bytes()
            require(receipt['origin'] == 'owner' and receipt['owner_TCP_attempted'] and receipt['flush_completed_ns']
                    and len(response) == receipt['response_bytes'], 'original_owner_response_boundary/' + directory.name)
        else:
            require(receipt['method'] == 'notifications/initialized' and receipt['origin'] is None,
                    'unexpected_missing_original_outer_reply/' + directory.name)
        require(len(request) == receipt['request_bytes'], 'original_request_size_mismatch/' + directory.name)
        rows.append((request, response, receipt))
    attempts = [row['attempt'] for _, _, row in rows if row['attempt'] is not None]
    require(attempts == list(range(1, len(attempts)+1))
            and len(attempts) == recorded['tool_accounting']['completed_business_calls'],
            'original_authentic_attempt_denominator_mismatch/' + slot.name)
    return rows


def transport_replay(folder, rows, python, *, omit_attempt=None):
    folder.mkdir()
    reached = 0
    failures = []
    forwarded = [(json.loads(tx), json.loads(rx), row['attempt']) for tx, rx, row in rows if rx]

    class ArchivedReply(BaseRequestHandler):
        def handle(self):
            nonlocal reached
            try:
                self.request.settimeout(5)
                with self.request.makefile('rb') as stream:
                    request = json.loads(stream.readline(4 * 1024 * 1024))
                expected_tx, saved_rx, attempt = forwarded[reached]
                require(request['operation'] == 'attached_mcp' and request['args'] == {
                    'kind': 'native', 'message': expected_tx, 'attempt': attempt}, 'new_outer_did_not_forward_original_envelope')
                reached += 1
                if omit_attempt is not None and attempt == omit_attempt:
                    return
                reply = {'request_id': request['request_id'], 'ok': True, 'result': saved_rx}
                self.request.sendall(json.dumps(reply, separators=(',', ':'), allow_nan=False).encode('utf8'))
            except (OSError, ValueError, IndexError, KeyError) as error:
                failures.append(str(error))

    endpoint = folder / 'ENDPOINT.json'
    with TCPServer(('127.0.0.1', 0), ArchivedReply) as server:
        host, port = server.server_address
        endpoint.write_text(json.dumps({'host':host, 'port':port, 'chain_deadline_ns':time.perf_counter_ns()+35_000_000_000}), encoding='utf8')
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval':0.01})
        thread.start()
        try:
            child = subprocess.run([python,'-IB','-X','utf8',str(driver.THIN),'--endpoint',str(endpoint),
                                    '--audit',str(folder/'attachments')], input=b''.join(tx for tx, _, _ in rows),
                                   capture_output=True, timeout=30)
        finally:
            server.shutdown()
            thread.join(5)
    require(not thread.is_alive() and reached == len(forwarded) and not failures,
            'archive_only_loopback_transcript_failed/' + str(failures))
    require(child.returncode == 0 and not child.stderr, 'new_outer_stdio_failed_or_did_not_close')
    bridge, = (folder / 'attachments').glob('bridge_*')
    closing = costs.read(bridge / 'EXIT.json')
    require(closing['normal_exit'] is True and closing['requests'] == len(rows)
            and closing['attempts'] == sum(row['attempt'] is not None for _, _, row in rows)
            and closing['complete_tx_bytes'] == sum(len(tx) for tx, _, _ in rows)
            and closing['complete_rx_bytes'] == len(child.stdout) and closing['ended_ns'] > closing['started_ns'],
            'new_outer_eof_counters_or_lifetime_changed')
    image_count = 0
    omitted = 0
    files_to_stdout = []
    for tx, rx, original in rows:
        wire = bridge / f'{original["sequence"]:03d}'
        receipt = costs.read(wire / 'RECEIPT.json')
        require((wire / 'TX.bin').read_bytes() == tx and all(receipt[key] == original[key] for key in ('attempt','method','RPC_id')),
                'new_outer_request_changed')
        current_path = wire / 'RX.bin'
        if not rx:
            require(not current_path.exists(), 'notification_generated_a_new_reply')
            continue
        current = current_path.read_bytes()
        files_to_stdout.append(current)
        if omit_attempt is not None and original['attempt'] == omit_attempt:
            result = json.loads(current)
            require(receipt['origin'] == 'transport_failure' and receipt['owner_TCP_attempted']
                    and result['id'] == original['RPC_id'] and result['result']['isError'] is True,
                    'missing_owner_business_reply_must_be_a_bound_rejection')
            omitted += 1
        else:
            require(current == rx and receipt['origin'] == 'owner' and receipt['flush_completed_ns'],
                    'new_outer_original_response_bytes_or_provenance_changed')
            image_count += sum(b.get('type') == 'image' for b in json.loads(current).get('result',{}).get('content',[]))
    require(child.stdout == b''.join(files_to_stdout) and omitted == int(omit_attempt is not None),
            'new_outer_exact_stdout_or_control_denominator_changed')
    require(image_count > 0, 'actual_original_image_blocks_missing')
    return {'outer_stdio': str(driver.THIN), 'requests': len(rows), 'business_calls': closing['attempts'],
            'source_owner_replies': len(forwarded), 'original_images_preserved':image_count,
            'ordered_raw_stdout': {'bytes':len(child.stdout),'sha256':sha256(child.stdout).hexdigest()},
            'closed': True, 'matched_after_missing_business_attempt': omit_attempt is not None, 'omitted_attempt':omit_attempt}


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'registered_isolated_interpreter_required')
    original = load_helpers(PREVIOUS / 'consumer/preflight.py')
    with patch.object(driver, 'DENSE', driver.NS.parent/'m4_dense_panel_sweep_formal_001', create=True):
        retained = load_helpers(driver.PILOT / 'consumer/preflight.py')
    turn, proof, metadata = driver.consumer_adapter()
    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve(strict=True)
        if path not in pins:
            pins[path] = costs.file_receipt(path)
        row = pins[path]
        require((digest is None or row['sha256'] == digest) and (size is None or row['bytes'] == size),
                'original_consumer_input_identity_changed/' + str(path))
        return row

    for path in (Path(__file__), PREVIOUS/'consumer/preflight.py', driver.PILOT/'consumer/preflight.py',
                 driver.THIN, driver.NS/'harness/bridge.py'):
        pin(path)
    registered_prompt = pin(driver.PROMPT, driver.PROMPT_SHA, 1032)
    pin(PREVIOUS/'inputs/PROMPT.txt', registered_prompt['sha256'], registered_prompt['bytes'])
    for row in proof['execution_sources']:
        pin(row['path'], row['sha256'], row['bytes'])
    pin(proof['Python_path'], proof['Python_sha256'])
    pin(proof['CLI_path'], proof['CLI_sha256'])
    version = subprocess.check_output([proof['CLI_path'],'--version'],timeout=15).decode().strip()
    login = subprocess.run([proof['CLI_path'],'login','status'],capture_output=True,timeout=15,check=True)
    login_text = (login.stdout + login.stderr).decode('utf8').strip()
    require((version, login_text) == ('codex-cli 0.152.1', 'Logged in using ChatGPT'), 'registered_existing_CLI_login_changed')
    require(turn.__globals__['safe_environment']({'OPENAI_API_KEY':'stub','GOOGLE_API_KEY':'stub','AN_ACCESS_TOKEN':'stub',
            'CODEX_THREAD_ID':'stub','Keep':'sentinel'}) == {'Keep':'sentinel'}, 'shadow_API_or_history_inherited')

    index = DUAL/'RUNTIME_INDEX.json'
    pin(index)
    expected_index = subprocess.check_output(['git','-C',str(driver.NS.parent.parent),'show',
                  f'{DUAL_COMMIT}:{index.relative_to(driver.NS.parent.parent).as_posix()}'])
    require(expected_index == index.read_bytes(), 'reference_archive_index_is_not_from_actual_formal_commit')
    archived = costs.read(index)
    archive = pin(archived['archive']['path'], archived['archive']['sha256'], archived['archive']['bytes'])
    members = {row['path']:row for row in archived['files']}
    prior_roots = original['HISTORY']
    real = {}
    transport = {}
    with TemporaryDirectory(prefix='he_dense_micro_consumer_') as workdir:
        root = Path(workdir).resolve()
        require(tuple(driver.LABELS) == FORMAL_ORDER, 'frozen_six_formal_dispatch_order_changed')
        actual = {label:original['local_exit'](label,root/label,turn,proof,metadata,retained['normalize'],pin)
                  for label in FORMAL_ORDER}
        for label in ('N1','P1'):
            old_slot = DUAL_RUN/'slots'/label
            local = root/f'old_{label}'
            local.mkdir()
            real[label] = retained['replay_archive'](old_slot,local,turn,pin)
            rows = archived_wires(old_slot,pin)
            transport[label] = transport_replay(root/f'outer_{label}',rows,proof['Python_path'])
            if label == 'P1':
                transport['P1_missing_then_success'] = transport_replay(root/'outer_P1_missing',rows,proof['Python_path'],omit_attempt=1)
        with ZipFile(archive['path']) as original_zip:
            for path, row in pins.items():
                if path.is_relative_to(DUAL_RUN) and path != Path(archive['path']):
                    key = path.relative_to(DUAL_RUN).as_posix()
                    require(all(row[field] == members[key][field] for field in ('sha256','bytes'))
                            and sha256(original_zip.read(key)).hexdigest() == row['sha256'], 'genuine_formal_original_changed/' + key)
        for original_run, previous_code, _ in prior_roots:
            old_index = previous_code.parent/'RUNTIME_INDEX.json'
            pin(old_index)
            indexed = costs.read(old_index)
            old_archive = indexed['archive']
            old_path = Path(pin(old_archive['path'], old_archive['sha256'], old_archive['bytes'])['path'])
            with ZipFile(old_path) as saved:
                for path, row in pins.items():
                    if path.is_relative_to(original_run) and path != old_path:
                        key = path.relative_to(original_run).as_posix()
                        require(sha256(saved.read(key)).hexdigest() == row['sha256'], 'actual_CLI_argv_receipt_changed/' + key)
    require(all(row['stdin_sha256'] == registered_prompt['sha256'] and row['stdin_bytes'] == registered_prompt['bytes']
                for row in actual.values()) and set(proof['actual_tools_by_group']['P'])-set(proof['actual_tools_by_group']['N'])
                == {'human_eye_scene_observe'}, 'shared_prompt_or_common_tools_changed')
    output = HERE/'PREFLIGHT.json'
    with output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump({'passed':True,'provider_model_launches':0,'Blender_launches':0,'CLI':version,'login_status':login_text,
                   'exact_common_prompt':registered_prompt,'fixed_requested_model':proof['model'],
                   'fixed_reasoning_effort':proof['reasoning_effort'],'fixed_service_tier':proof['service_tier'],
                   'formal_order':list(actual),'fresh_local_early_exit_tests':actual,'tool_names':proof['actual_tools_by_group'],
                   'original_CLI_cost_and_result_replays':real,'current_outer_stdio_original_wire_replays':transport,
                   'original_transport_scope':'Archived replies over loopback. Original CLI process close uses retained handle; the new stdio replay also records EXIT.json.',
                   'source_pins':list(pins.values())},stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')
    print('Recovery consumer preflight passed',costs.digest(output),len(pins),flush=True)


if __name__ == '__main__':
    main()
