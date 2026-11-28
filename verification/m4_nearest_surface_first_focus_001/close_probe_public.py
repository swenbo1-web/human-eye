"""Exercise the retained MCP dispatcher through the no-turn Windows app-server."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import queue
import secrets
import socket
import struct
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ['HE_NEAREST_FOCUS_ROOT']).resolve(strict=True)
OLD = ROOT.parent / 'M4-REFERENCE-ONLY-INTENT-HOLDOUT-001'
PROBE = ROOT / 'preflight/close-windows'
PLAN = ROOT / 'preflight/CLOSE_PLAN.json'
RESULT = ROOT / 'preflight/CLOSE_RESULT.json'
KINDS = ('normal', 'missing_last', 'reset')
FRAME = '_local_close_control'
sys.path.insert(0, str(HERE.parent / 'm4_reference_only_intent_holdout_001'))
os.environ.setdefault('HE_INTENT_RUNS', str(ROOT.parent))
import natural_public as natural
from natural_bridge import Bridge, encode, pin, require, write


def read(path):
    return json.loads(Path(path).read_bytes())


def send(socket_, value):
    socket_.sendall(encode(value) + b'\n')


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def line(stream):
    raw = stream.readline(32 * 1024 * 1024 + 1)
    require(not raw or raw.endswith(b'\n') and len(raw) <= 32 * 1024 * 1024, 'complete_bounded_line')
    return raw


def thin(endpoint):
    original = read(endpoint)
    require(original['host'] == '127.0.0.1', 'owned_loopback_only')
    folder = endpoint.parent
    write(folder/'THIN_STARTED.json', {'pid': os.getpid(), 'ppid': os.getppid()})
    evidence = {'pending': None, 'eof': False, 'exit': 1}
    try:
        with socket.create_connection((original['host'], original['port']), timeout=18) as sock:
            sock.sendall(original['token'].encode('ascii') + b'\n')
            with sock.makefile('rb', buffering=0) as incoming:
                while request := line(sys.stdin.buffer):
                    command = json.loads(request)
                    sock.sendall(request)
                    if 'id' not in command:
                        continue
                    evidence['pending'] = command['id']
                    raw = line(incoming)
                    require(raw and json.loads(raw)['id'] == command['id'], 'response_EOF_before_delivery')
                    sys.stdout.buffer.write(raw)
                    sys.stdout.buffer.flush()
                    flushed = {FRAME: 'delivered', 'id': command['id'], 'sha256': digest(raw),
                               'in_flight': 0, 'flushed_ns': time.perf_counter_ns()}
                    send(sock, flushed)
                    evidence.update(pending=None, last_flush=flushed)
                    marker = json.loads(line(incoming))
                    if marker[FRAME] == 'continue':
                        continue
                    require(marker[FRAME] == 'close' and marker['id'] == command['id']
                            and marker['sha256'] == flushed['sha256'] and marker['in_flight'] == 0,
                            'owner_close_not_bound_to_last_delivery')
                    ack = {**marker, FRAME: 'close_ack'}
                    evidence.update(marker=marker, ack=ack)
                    send(sock, ack)
                    sock.shutdown(socket.SHUT_WR)
                    evidence['eof'] = not line(incoming)
                    require(evidence['eof'], 'unexpected_bytes_after_close_ack')
                    evidence['exit'] = 0
                    return 0
        raise ValueError('stdio_EOF_without_paired_close')
    except (ValueError, OSError, KeyError) as exc:
        evidence['error'] = {'type': type(exc).__name__, 'message': str(exc),
                             'winerror': getattr(exc, 'winerror', None)}
        return 1
    finally:
        write(folder/'THIN_EXIT.json', {**evidence, 'closed_ns': time.perf_counter_ns()})


class Owner:
    def __init__(self, bridge, kind, folder):
        self.bridge, self.kind, self.folder = bridge, kind, folder
        self.token = secrets.token_hex(24)
        self.authorize = threading.Event()
        self.evidence = {'pending': None, 'last': None, 'flushed': [], 'eof': False, 'rst': False}
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.listener.settimeout(18)
        self.path = folder/'ENDPOINT.json'
        write(self.path, {'host': '127.0.0.1', 'port': self.listener.getsockname()[1], 'token': self.token})
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        data = self.evidence
        try:
            conn, _ = self.listener.accept()
            with conn:
                conn.settimeout(18)
                with conn.makefile('rb', buffering=0) as incoming:
                    require(line(incoming) == self.token.encode() + b'\n', 'invalid_loopback_token')
                    while raw := line(incoming):
                        request = json.loads(raw)
                        self.bridge.ordinal += 1
                        outgoing = self.bridge.dispatch(raw)
                        if not outgoing:
                            continue
                        wanted = {'id': request['id'], 'sha256': digest(outgoing), 'in_flight': 0}
                        data['pending'] = wanted
                        last = request['method'] == 'tools/call'
                        if last:
                            data['last'] = {**wanted, 'ordinal': self.bridge.ordinal, 'request_sha256': digest(raw)}
                        if last and self.kind == 'missing_last':
                            data['initiator'] = 'owner_dropped_prepared_reply'
                            conn.shutdown(socket.SHUT_WR)
                            data['eof'] = not line(incoming)
                            return
                        conn.sendall(outgoing)
                        flushed = json.loads(line(incoming))
                        wanted_flush = {**wanted, FRAME: 'delivered'}
                        require(all(flushed[key] == val for key, val in wanted_flush.items()), 'wrong_thin_flush_receipt')
                        data['flushed'].append(flushed)
                        data['pending'] = None
                        if not last:
                            send(conn, {FRAME: 'continue'})
                            continue
                        require(self.authorize.wait(12), 'actual_app_consumer_delivery_missing')
                        if self.kind == 'reset':
                            data.update(initiator='owner_abortive_close_after_delivery', rst=True)
                            conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('HH', 1, 0))
                            return
                        marker = {**wanted, FRAME: 'close', 'nonce': secrets.token_hex(20)}
                        data.update(initiator='owner_after_actual_app_delivery', marker=marker)
                        send(conn, marker)
                        ack = json.loads(line(incoming))
                        require(ack == {**marker, FRAME: 'close_ack'}, 'missing_paired_end')
                        data['ack'] = ack
                        data['eof'] = not line(incoming)
                        require(data['eof'], 'thin_EOF_missing')
                        conn.shutdown(socket.SHUT_WR)
                        return
        except (OSError, ValueError, KeyError) as exc:
            data['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        finally:
            self.listener.close()
            write(self.folder/'OWNER_CLOSE.json', {**data, 'closed_ns': time.perf_counter_ns()})


class App:
    def __init__(self, folder, endpoint):
        self.folder, self.work = folder, folder/'workspace'
        self.work.mkdir()
        isolated = folder/'codex-home'
        isolated.mkdir()
        q = lambda value: json.dumps(str(value), ensure_ascii=True)
        args = ','.join(map(q, ('-IB', '-X', 'utf8', Path(__file__).resolve(), 'thin', endpoint)))
        mcp = f'mcp_servers.arm_engine={{command={q(sys.executable)},args=[{args}],cwd={q(self.work)},required=true,startup_timeout_sec=15,tool_timeout_sec=15}}'
        config = [mcp, 'features.apps=false', 'features.hooks=false', 'features.plugins=false',
                  'features.memories=false', 'web_search="disabled"', 'model_provider="close_probe_local"',
                  'model_providers.close_probe_local={name="offline",base_url="http://127.0.0.1:1/v1",'
                  'wire_api="responses",requires_openai_auth=false}']
        argv = [str(natural.CLI), 'app-server', '--stdio', '--strict-config']
        for item in config:
            argv.extend(('-c', item))
        env = dict(os.environ, CODEX_HOME=str(isolated))
        for key in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'AZURE_OPENAI_API_KEY'):
            env.pop(key, None)
        self.stderr = (folder/'APP_STDERR.bin').open('xb')
        self.proc = subprocess.Popen(argv, cwd=self.work, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.stderr, creationflags=subprocess.CREATE_NO_WINDOW)
        write(folder/'APP_STARTED.json', {'pid': self.proc.pid, 'argv': argv, 'started_ns': time.perf_counter_ns()})
        self.queue = queue.Queue()
        self.reader = threading.Thread(target=self.pump, daemon=True)
        self.reader.start()

    def pump(self):
        with (self.folder/'APP_RX.bin').open('xb') as out:
            while raw := line(self.proc.stdout):
                out.write(raw)
                out.flush()
                self.queue.put(raw)
        self.queue.put(None)

    def call(self, method, params, ident=None):
        require(method in {'initialize', 'initialized', 'thread/start', 'mcpServer/tool/call'},
                'only_no_turn_app_server_methods')
        message = {'method': method, 'params': params}
        if ident is not None:
            message['id'] = ident
        raw = encode(message) + b'\n'
        with (self.folder/'APP_TX.bin').open('ab') as out:
            out.write(raw)
        self.proc.stdin.write(raw)
        self.proc.stdin.flush()
        if ident is not None:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                answer = self.queue.get(timeout=max(.001, deadline-time.monotonic()))
                require(answer is not None, 'app_stdout_closed')
                result = json.loads(answer)
                if result.get('id') == ident:
                    return result

    def close(self):
        self.proc.stdin.close()
        forced = False
        try:
            exit_code = self.proc.wait(8)
        except subprocess.TimeoutExpired:
            forced = True
            self.proc.kill()
            exit_code = self.proc.wait(3)
        self.reader.join(2)
        self.proc.stdout.close()
        self.stderr.close()
        return {'exit_code': exit_code, 'pid': self.proc.pid, 'forced': forced, 'stdout_eof': not self.reader.is_alive(),
                'closed_ns': time.perf_counter_ns()}


class ProcessHandle:
    def __init__(self, pid):
        api = self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        api.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        api.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.handle = api.OpenProcess(0x101000, False, pid)
        require(self.handle, 'cannot_retain_thin_process_handle')
        self.pid = pid

    def result(self):
        code = wintypes.DWORD()
        try:
            require(self.api.WaitForSingleObject(self.handle, 8000) == 0
                    and self.api.GetExitCodeProcess(self.handle, ctypes.byref(code)), 'thin_exit_not_confirmed')
            return {'pid': self.pid, 'exit_code': code.value, 'confirmed_ns': time.perf_counter_ns()}
        finally:
            self.api.CloseHandle(self.handle)


def process_ancestry(child, owner_pid):
    """Follow the Windows venv launcher between the Python child and Codex."""
    class Entry(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('uses', wintypes.DWORD), ('pid', wintypes.DWORD),
                    ('heap', ctypes.c_size_t), ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                    ('parent', wintypes.DWORD), ('priority', wintypes.LONG), ('flags', wintypes.DWORD),
                    ('image', wintypes.WCHAR * 260)]

    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    api.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        proc = getattr(api, name)
        proc.argtypes = (wintypes.HANDLE, ctypes.POINTER(Entry))
        proc.restype = wintypes.BOOL
    api.CloseHandle.argtypes = (wintypes.HANDLE,)
    snapshot = api.CreateToolhelp32Snapshot(2, 0)
    require(snapshot != ctypes.c_void_p(-1).value, 'process_snapshot_unavailable')
    observed = {}
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        ok = api.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            observed[entry.pid] = {'pid': entry.pid, 'parent': entry.parent, 'executable_basename': entry.image}
            ok = api.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        api.CloseHandle(snapshot)
    require(observed[child['pid']]['parent'] == child['ppid'], 'thin_process_parent_changed')
    chain = []
    cursor = child['pid']
    while cursor in observed and len(chain) < 8:
        row = observed[cursor]
        chain.append(row)
        if cursor == owner_pid:
            return chain
        cursor = row['parent']
    raise ValueError('thin_is_not_a_descendant_of_Codex')


def wait_file(path):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        try:
            return read(path)
        except (OSError, ValueError):
            time.sleep(.025)
    raise ValueError('thin_process_marker_missing')


def prepare():
    v = subprocess.run([str(natural.CLI), '--version'], capture_output=True, check=True, timeout=10,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    require(pin(natural.CLI)['sha256'] == natural.CLI_SHA and v.stdout.strip() == b'codex-cli 0.152.1', 'cli_changed')
    prior_path = OLD/'preflight/NATURAL_PLAN.json'
    prior = read(prior_path)
    installed = {name: prior[name] for name in ('product', 'site', 'product_source_sha256', 'product_source_files')}
    require(installed['product'] == 'b7fe4bb0dc2ce277ff5dd7a6198365253b716c09', 'product_changed')
    terminal = OLD/'slots/NATURAL_K/post_capture.json'
    old = [OLD/'NATURAL_SCORE_FORMAL.json']
    for key in 'KT':
        slot = OLD/'slots'/f'NATURAL_{key}'
        closed = read(slot/'closed.json')
        require(closed['transport']['error']['type'] == 'ConnectionResetError'
                and '10054' in closed['transport']['error']['message']
                and read(slot/'consumer/RESULT.json')['passed_transport'] is False, 'old_failure_missing')
        old.extend((slot/'closed.json', slot/'consumer/RESULT.json'))
    paths = [Path(__file__), Path(natural.__file__), HERE.parent/'m4_reference_only_intent_holdout_001/natural_bridge.py',
             ROOT/'preflight/ADMIN_PLAN.md', prior_path, terminal, natural.CLI, Path(sys.executable), *old]
    write(PLAN, {'inputs': list(map(pin, paths)), 'old_failures_and_verdict': list(map(pin, old)),
          'terminal': pin(terminal), 'installed': installed, 'cases': list(KINDS),
          'budget': {'app_server_processes': 3, 'business': 3, 'model_turns': 0, 'Blender': 0},
          'method': 'real app-server stdio with ephemeral thread, manual mcpServer/tool/call and no turn',
          'untested': 'codex exec natural consumer shutdown'})


def probe_case(plan, kind):
    folder = PROBE/kind
    folder.mkdir()
    host = natural.ReplayHost(read(plan['terminal']['path']))
    service, server = natural.product(plan['installed'], folder, host)
    bridge = Bridge(folder, host, service, server, time.perf_counter_ns() + 60_000_000_000)
    bridge.install_raster_guard()
    owner = Owner(bridge, kind, folder)
    app = App(folder, owner.path)
    try:
        hello = app.call('initialize', {'clientInfo': {'name': 'close-probe', 'version': '1'}, 'capabilities': None}, 1)
        require(hello and 'result' in hello, 'app_initialize_failed')
        app.call('initialized', {})
        thread = app.call('thread/start', {'cwd': str(app.work), 'ephemeral': True,
                                           'sandbox': 'read-only', 'approvalPolicy': 'never'}, 2)
        require(thread and 'result' in thread, 'ephemeral_no_turn_thread_failed/' + str(thread))
        child = wait_file(folder/'THIN_STARTED.json')
        chain = process_ancestry(child, app.proc.pid)
        handle = ProcessHandle(child['pid'])
        answer = app.call('mcpServer/tool/call', {'threadId': thread['result']['thread']['id'], 'server': 'arm_engine',
            'tool': 'human_eye_scene_observe', 'arguments': {'query': {'mode': 'active_observation',
                'objects': [{'name': 'Part M'}], 'focus': {'task_region': {'reference': {'name': 'Fixture K'}}}},
                'include_image': False}}, 3)
        last = owner.evidence['last']
        require(last is not None, 'actual_cli_last_request_not_dispatched')
        prepared = read(folder/'wire'/f"{last['ordinal']:03d}"/'RX.bin')
        delivered = bool(answer and answer.get('result', {}).get('content') == prepared['result']['content']
                         and prepared['result']['isError'] is False)
        if delivered:
            owner.authorize.set()
        owner.thread.join(8)
        require(not owner.thread.is_alive(), 'owner_thread_not_closed')
        thin_exit = handle.result()
    finally:
        app_exit = app.close()
        bridge.images_module.rasterize_attention = bridge.original_raster
        bridge.service.observe = bridge.original_observe
    o, t = read(folder/'OWNER_CLOSE.json'), read(folder/'THIN_EXIT.json')
    accepted = bool(delivered and o.get('marker') == t.get('marker') and o.get('ack') == t.get('ack')
                    and o['pending'] is None and o['eof'] and t['eof'] and thin_exit['exit_code'] == 0
                    and app_exit['exit_code'] == 0 and app_exit['stdout_eof'] and not app_exit['forced'])
    if kind == 'normal':
        passed = accepted
    elif kind == 'missing_last':
        passed = (not accepted and not delivered and o['pending'] is not None and t['pending'] == last['id']
                  and t['error']['message'] == 'response_EOF_before_delivery' and thin_exit['exit_code'] != 0)
    else:
        passed = (not accepted and delivered and o['rst'] and o['pending'] is None
                  and t['error']['winerror'] == 10054 and thin_exit['exit_code'] != 0)
    results = {'case': kind, 'passed': passed, 'actual_last_delivered': delivered, 'transport_accepted': accepted,
               'thin_process': thin_exit, 'app_process': app_exit, 'ancestry': chain, 'answer': answer, 'last': last,
               'business': bridge.biz, 'rasters': len(bridge.rasters), 'files': list(map(pin, (
                   folder/'THIN_EXIT.json', folder/'OWNER_CLOSE.json', folder/'APP_TX.bin', folder/'APP_RX.bin',
                   folder/'wire/INDEX.jsonl')))}
    write(folder/'RESULT.json', results)
    require(passed and bridge.biz == 1 and not bridge.rasters and app_exit['exit_code'] == 0 and not app_exit['forced'],
            'frozen_close_case_failed/' + kind)
    return results


def run():
    plan = read(PLAN)
    require(all(pin(r['path']) == r for r in plan['inputs']), 'frozen_source_changed')
    PROBE.mkdir()
    cases = [probe_case(plan, kind) for kind in KINDS]
    write(RESULT, {'passed': True, 'plan': pin(PLAN), 'cases': cases, 'Blender': 0, 'model_turns': 0,
                   'untested': plan['untested']})


if __name__ == '__main__':
    require(os.name == 'nt' and sys.flags.isolated and sys.dont_write_bytecode, 'isolated_Windows_required')
    command = sys.argv[1]
    if command == 'thin':
        raise SystemExit(thin(Path(sys.argv[2])))
    {'prepare': prepare, 'run': run}[command]()
