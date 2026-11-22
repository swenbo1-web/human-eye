"""Read the real Codex CLI's local MCP catalogue without creating a model turn."""

from hashlib import sha256
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
from threading import Event, Thread
import time


NS = Path(__file__).resolve().parent
SERVER = 'region_task_profile_probe'
VERSION = '0.152.1'
RELEASE = VERSION + '-x86_64-pc-windows-msvc'
ORIGINAL_RECEIPT = NS.parent / 'perf050_dense_micro_surface_holdout_recovery_001/consumer/PREFLIGHT.json'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha256(path.read_bytes()).hexdigest()}


def write(path, data):
    path.write_bytes((json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode())


def cli_binary():
    path = (Path(os.environ['USERPROFILE']) / '.codex/packages/standalone/releases' / RELEASE / 'bin/codex.exe').resolve(strict=True)
    previous, = [row for row in read(ORIGINAL_RECEIPT)['source_pins'] if Path(row['path']) == path]
    current = pin(path)
    require(all(previous[field] == current[field] for field in ('bytes', 'sha256')), 'actual_formal_CLI_binary_changed')
    return path, current


def owned_thin_lifetime(audit, observed, stop):
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = None
    try:
        while not stop.is_set():
            marker = next(audit.glob('bridge_*/STARTED.json'), None)
            if marker is None:
                stop.wait(0.001)
                continue
            launch = read(marker)
            handle = api.OpenProcess(0x100000 | 0x1000, False, launch['pid'])
            require(bool(handle), 'actual_CLI_MCP_live_owned_handle_unavailable')
            length = wintypes.DWORD(32768)
            path = ctypes.create_unicode_buffer(length.value)
            require(api.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length))
                    and Path(path.value).resolve() == Path(sys.executable).resolve(), 'actual_CLI_MCP_child_executable_changed')
            observed.update(pid=launch['pid'], started_receipt=pin(marker), acquired_ns=time.perf_counter_ns(),
                            executable=path.value, owned_process_handle_acquired=True)
            stop.wait(40)
            status = api.WaitForSingleObject(handle, 5000)
            code = wintypes.DWORD()
            require(status == 0 and api.GetExitCodeProcess(handle, ctypes.byref(code)), 'actual_CLI_MCP_owned_child_did_not_exit')
            observed.update(confirmed=True, exit_code=code.value, wait_status=status)
            return
    except (OSError, ValueError, KeyError) as error:
        observed['error'] = str(error)
    finally:
        if handle:
            observed['handle_closed'] = bool(api.CloseHandle(handle))


def closed_bridge(audit, expected_tools, lifetime):
    folder, = audit.glob('bridge_*')
    exit_file = folder / 'EXIT.json'
    closure = read(exit_file) if exit_file.is_file() else None
    require(lifetime.get('confirmed') is True and lifetime.get('handle_closed') is True,
            'actual_CLI_MCP_owned_child_exit_unconfirmed/' + str(lifetime.get('error')))
    methods, rows, rx_sizes, tx_sizes = [], [], [], []
    for directory in sorted(item for item in folder.iterdir() if item.is_dir()):
        tx_path, rx_path = directory / 'TX.bin', directory / 'RX.bin'
        request, receipt = read(tx_path), read(directory / 'RECEIPT.json')
        methods.append(request['method'])
        tx = pin(tx_path)
        tx_sizes.append(tx['bytes'])
        require(receipt['request_bytes'] == tx['bytes'] and receipt['method'] == request['method']
                and receipt['attempt'] is None, 'actual_CLI_MCP_transaction_not_registry_only')
        row = {'method':request['method'], 'TX':tx, 'receipt':pin(directory / 'RECEIPT.json')}
        if rx_path.is_file():
            reply = read(rx_path)
            row['RX'] = rx = pin(rx_path)
            rx_sizes.append(rx['bytes'])
            require(receipt['response_bytes'] == rx['bytes'] and receipt['origin'] == 'owner'
                    and receipt['owner_TCP_attempted'] is True and receipt['flush_completed_ns']
                    and reply['id'] == request['id'], 'actual_CLI_MCP_owner_reply_identity_changed')
            if request['method'] == 'tools/list':
                require(reply['result']['tools'] == expected_tools, 'app_server_did_not_read_the_exact_owner_catalogue')
        rows.append(row)
    require(methods == ['initialize', 'notifications/initialized', 'tools/list']
            and len(rx_sizes) == 2, 'actual_CLI_registry_wire_incomplete')
    if closure is not None:
        require(closure['normal_exit'] is True and closure['attempts'] == 0 and closure['requests'] == len(methods)
                and closure['complete_tx_bytes'] == sum(tx_sizes) and closure['complete_rx_bytes'] == sum(rx_sizes),
                'actual_CLI_registry_bridge_recorded_incomplete_EOF')
    return {'wire':rows, 'observed_owned_process_exit':lifetime, 'EOF_receipt_present':closure is not None,
            'closure':closure, 'closure_receipt':pin(exit_file) if closure is not None else None}


def probe(root, endpoint, arm, expected_tools):
    """Register the exact tools from one live local Owner via the experiment thin stdio."""
    require(arm in ('QA', 'QB'), 'unknown_CLI_profile_arm')
    root = Path(root).resolve() / 'actual_cli_registry'
    root.mkdir(parents=True, exist_ok=False)
    state = root / 'cli_state'
    state.mkdir()
    audit = root / 'mcp_audit'
    thin = NS / 'consumer/thin_stdio.py'
    endpoint = Path(endpoint).resolve(strict=True)
    cli, binary = cli_binary()
    blocked = ('TOKEN', 'SECRET', 'KEY', 'PROXY', 'CODEX_', 'OPENAI', 'CHATGPT', 'OPENROUTER',
               'ANTHROPIC', 'AZURE', 'GOOGLE', 'MCP_', 'RUST_LOG')
    environment = {key: value for key, value in os.environ.items() if not any(marker in key.upper() for marker in blocked)}
    # Select an empty, per-process state root without touching any desktop or shell configuration.
    environment['CODEX_HOME'] = str(state)
    version = subprocess.check_output([str(cli), '--version'], env=environment, cwd=root, timeout=10).decode().strip()
    require(version == 'codex-cli ' + VERSION, 'actual_CLI_version_changed')
    command = [str(cli), 'app-server', '--listen', 'stdio://', '-c', 'analytics.enabled=false',
               '-c', 'model_provider="local_offline_registry"', '-c', 'model_providers.local_offline_registry.name="Isolated registry probe"',
               '-c', 'model_providers.local_offline_registry.base_url="http://127.0.0.1:1/v1"',
               '-c', f'mcp_servers.{SERVER}.command=' + json.dumps(sys.executable),
               '-c', f'mcp_servers.{SERVER}.args=' + json.dumps(['-IB', '-X', 'utf8', str(thin), '--endpoint', str(endpoint), '--audit', str(audit)])]
    requests = (
        {'jsonrpc':'2.0', 'id':0, 'method':'initialize', 'params':{'clientInfo':{
            'name':'he_local_registry_probe', 'title':'Local tool registry probe', 'version':'1.0.0'}}},
        {'jsonrpc':'2.0', 'method':'initialized'},
        {'jsonrpc':'2.0', 'id':1, 'method':'mcpServerStatus/list', 'params':{'detail':'toolsAndAuthOnly'}},
    )
    channel = Queue()
    notifications = []
    clocks = {}
    started = time.perf_counter_ns()
    process = subprocess.Popen(command, cwd=root, env=environment, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def stdout_reader():
        for line in process.stdout:
            channel.put(line)
        channel.put(None)

    stderr = bytearray()
    stdout_thread = Thread(target=stdout_reader, daemon=True)
    stderr_thread = Thread(target=lambda:stderr.extend(process.stderr.read()), daemon=True)
    thin_observation, stop = {}, Event()
    thin_thread = Thread(target=owned_thin_lifetime, args=(audit, thin_observation, stop), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    thin_thread.start()
    responses = {}
    killed = False
    try:
        for sequence, request in enumerate(requests,1):
            wire = root / f'{sequence:03d}'
            wire.mkdir()
            payload = (json.dumps(request, separators=(',', ':')) + '\n').encode()
            (wire/'TX.bin').write_bytes(payload)
            sent = time.perf_counter_ns()
            process.stdin.write(payload)
            process.stdin.flush()
            if 'id' not in request:
                continue
            deadline = time.monotonic() + 30
            while True:
                line = channel.get(timeout=max(0.01, deadline - time.monotonic()))
                require(line is not None, 'actual_CLI_closed_before_registry_reply')
                reply = json.loads(line)
                if 'id' not in reply:
                    # Preserve the notification disposition without publishing device identifiers.
                    notifications.append(reply['method'])
                    require(time.monotonic() < deadline, 'actual_CLI_registry_reply_timeout')
                    continue
                (wire/'RX.bin').write_bytes(line)
                require(reply['id'] == request['id'] and 'result' in reply, 'actual_CLI_registry_RPC_error_or_wrong_id')
                responses[request['method']] = reply['result']
                clocks[request['method']] = {'elapsed_ns':time.perf_counter_ns()-sent, 'tx_bytes':len(payload), 'rx_bytes':len(line)}
                break
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            killed = True
            process.kill()
            process.wait(timeout=5)
        stdout_thread.join(5)
        stderr_thread.join(5)
        stop.set()
        thin_thread.join(6)
        (root/'STDERR.bin').write_bytes(stderr)
        write(root/'PROCESS_CLOSE.json', {'exit_code':process.returncode,'killed_after_timeout':killed,
             'readers_joined':not stdout_thread.is_alive() and not stderr_thread.is_alive(),
             'thin_watcher_joined':not thin_thread.is_alive(),'observed_thin_process':thin_observation,
             'elapsed_ns':time.perf_counter_ns()-started})
    require(process.returncode == 0 and not killed and not stdout_thread.is_alive() and not stderr_thread.is_alive(),
            'actual_CLI_registry_process_close_unconfirmed')
    initialized = responses['initialize']
    require(Path(initialized['codexHome']).resolve(strict=True) == state
            and '/' + VERSION + ' ' in initialized['userAgent'], 'actual_CLI_wrong_state_root_or_binary_version')
    listing = responses['mcpServerStatus/list']
    row, = listing['data']
    indexed = {item['name']:item for item in expected_tools}
    require(row['name'] == SERVER and listing['nextCursor'] is None and row['tools'] == indexed,
            'nested_condition_or_other_tool_definition_changed_in_actual_CLI_registry')
    bridge = closed_bridge(audit, expected_tools, thin_observation)
    proof = {'passed':True,'arm':arm,'CLI':version,'binary':binary,'probe_source':pin(Path(__file__).resolve()),
             'scope':'actual local Codex app-server MCP registry only; no provider prompt or request was issued',
             'provider_model_launches':0,'threads_started':0,'business_calls':0,'tool_count':len(indexed),
             'exact_all_tool_definitions':True,'mcp_tools_list':bridge,'app_server_RPC':clocks,
             'app_server_notification_methods':notifications,'closed_process':pin(root/'PROCESS_CLOSE.json'),
             'registry_response':pin(root/'003/RX.bin')}
    write(root/'CLI_PROOF.json', proof)
    return proof
