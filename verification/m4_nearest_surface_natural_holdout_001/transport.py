"""Bound Windows MCP delivery per request across the actual Codex Thin process."""
import hashlib
import json
import os
from pathlib import Path
import queue
import secrets
import socket
import struct
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / 'm4_nearest_surface_first_focus_001'),
                 str(HERE.parent / 'm4_reference_only_intent_holdout_001')]
from close_probe import ProcessHandle, process_ancestry
from natural_bridge import append, encode, pin, require, write

FRAME = '_transport_control'
MAX_WIRE = 32 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def line(stream):
    raw = stream.readline(MAX_WIRE + 1)
    require(not raw or len(raw) <= MAX_WIRE and raw.endswith(b'\n'), 'complete_bounded_transport_line')
    return raw


def packet(sock, obj):
    sock.sendall(encode(obj) + b'\n')


def start_transport(folder, bridge, deadline_ns):
    return Owner(Path(folder).resolve(strict=True), bridge, deadline_ns)


class Owner:
    def __init__(self, folder, bridge, deadline_ns):
        self.folder, self.bridge, self.deadline_ns = folder, bridge, deadline_ns
        self.endpoint = folder / 'ENDPOINT.json'
        self.token = secrets.token_hex(24)
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.listener.settimeout(.2)
        write(self.endpoint, {'host': '127.0.0.1', 'port': self.listener.getsockname()[1],
                             'token': self.token, 'deadline_ns': deadline_ns})
        self.parent_known = threading.Event()
        self.stop = threading.Event()
        self.idle = threading.Event()
        self.idle.set()
        self.active = None
        self.cli_pid = self.thin_pid = self.handle = self.ancestry = None
        self.error = None
        self.records = []
        self.fault = None
        bridge.install_raster_guard()
        self.thread = threading.Thread(target=self.serve, name='paired-natural-owner', daemon=True)
        self.thread.start()

    def bind_cli(self, pid):
        require(self.cli_pid is None and type(pid) is int and pid > 0, 'one_owned_Codex_process_required')
        self.cli_pid = pid
        self.parent_known.set()

    def arm_offline_fault(self, kind):
        require(kind in ('missing_last', 'reset') and self.idle.wait(3) and not self.stop.is_set()
                and self.fault is None and self.records, 'invalid_offline_negative_control')
        self.fault = kind

    def establish(self, hello):
        require(hello.get('token') == self.token and hello.get('ordinal') == self.bridge.ordinal + 1,
                'unauthenticated_or_misordered_local_exchange')
        require(self.parent_known.wait(5), 'owned_Codex_missing')
        if self.thin_pid is None:
            self.thin_pid = hello['pid']
            child = read(self.folder / 'THIN_STARTED.json')
            require(child['pid'] == self.thin_pid, 'Thin_process_identity_mismatch')
            self.ancestry = process_ancestry(child, self.cli_pid)
            self.handle = ProcessHandle(self.thin_pid)
        require(hello.get('pid') == self.thin_pid, 'unowned_secondary_Thin')

    def exchange(self, conn):
        with conn.makefile('rb') as src:
            header = json.loads(line(src))
            self.establish(header)
            self.bridge.ordinal += 1
            ordinal = self.bridge.ordinal
            raw = line(src)
            require(bool(raw), 'authenticated_request_missing')
            req = json.loads(raw)
            self.active = {'ordinal': ordinal, 'id': req.get('id'), 'request_sha256': sha(raw)}
            out = self.bridge.dispatch(raw)
            self.active.update(response_sha256=sha(out), response_bytes=len(out))
            fault = self.fault if req['method'] == 'tools/call' else None
            if fault == 'missing_last':
                self.fault = None
                conn.shutdown(socket.SHUT_WR)
                self.active.update(fault=fault, peer_eof=(not line(src)))
                raise ValueError('offline_negative_withheld_prepared_last_reply')
            packet(conn, {FRAME: 'response', **self.active})
            if out:
                conn.sendall(out)
            receipt = json.loads(line(src))
            expected = {FRAME: 'received', **self.active}
            require(receipt == expected, 'Thin_receipt_not_bound_to_raw_result')
            if fault == 'reset':
                self.fault = None
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('HH', 1, 0))
                self.active.update(fault=fault, prepared_reply_read_by_Thin=True)
                raise ValueError('offline_negative_aborted_after_private_receipt_before_public_write')
            offer = {FRAME: 'end', **self.active, 'nonce': secrets.token_hex(16), 'in_flight': 0}
            packet(conn, offer)
            ack = json.loads(line(src))
            require(ack == {**offer, FRAME: 'end_ack'}, 'paired_exchange_ack_mismatch')
            require(not line(src), 'missing_Thin_half_close')
            conn.shutdown(socket.SHUT_WR)
            record = {'request': self.active, 'offer': offer, 'ack': ack,
                      'peer_eof': True, 'owner_eof_sent': True, 'settled_ns': time.perf_counter_ns()}
            append(self.folder / 'TRANSPORT_OWNER.jsonl', record)
            self.records.append(record)
            self.active = None

    def serve(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError as error:
                if not self.stop.is_set():
                    self.error = {'type': type(error).__name__, 'message': str(error)}
                break
            self.idle.clear()
            try:
                with conn:
                    conn.settimeout(10)
                    self.exchange(conn)
            except Exception as error:
                self.error = {'type': type(error).__name__, 'message': str(error),
                              'winerror': getattr(error, 'winerror', None)}
                break
            finally:
                self.idle.set()

    def request_thin_end(self):
        """Only after a caller has witnessed its last reply may it stop an idle Thin."""
        require(self.idle.wait(4) and self.records and self.active is None and self.error is None,
                'cannot_stop_Thin_with_unsettled_requests')
        last = self.records[-1]['request']
        write(self.folder / 'THIN_STOP_REQUEST.json', last)
        return last

    def finish(self):
        self.stop.set()
        self.thread.join(1)
        self.listener.close()
        self.thread.join(11)
        thread_closed = not self.thread.is_alive()
        if thread_closed:
            if hasattr(self.bridge, 'images_module'):
                self.bridge.images_module.rasterize_attention = self.bridge.original_raster
            self.bridge.service.observe = self.bridge.original_observe
        exit_record = None
        if self.handle is not None:
            try:
                exit_record = self.handle.result()
            except ValueError as error:
                self.error = self.error or {'type': type(error).__name__, 'message': str(error)}
        thin_exit_path = self.folder/'THIN_EXIT.json'
        thin_exit = read(thin_exit_path) if thin_exit_path.is_file() else None
        close_owner = thread_closed and self.active is None and self.error is None
        both = close_owner and bool(self.records) and len(self.records) == self.bridge.ordinal
        own_termination = thin_exit is not None and thin_exit.get('exit') == 0
        terminal = (exit_record is not None and not (thin_exit and not own_termination)
                    and exit_record['exit_code'] in ((0,) if own_termination else (0, 1)))
        line_mode = ('observed_own_graceful_termination' if own_termination else
                     'process_exited_without_own_Thin_witness' if exit_record and thin_exit is None else
                     'failed_or_unverified_Thin_termination')
        summary = {'closed': bool(both and terminal), 'transport_eof': bool(both),
                   'business': self.bridge.biz, 'rasters': self.bridge.rasters,
                   'requests': self.bridge.ordinal, 'known_frames': len(self.bridge.frames),
                   'delivered_frames': len(self.bridge.advertised), 'paired_exchanges': len(self.records),
                   'zero_in_flight': self.active is None, 'owner_thread_closed': thread_closed,
                   'error': self.error, 'outstanding': self.active, 'Thin_process': exit_record,
                   'Thin_exit': thin_exit, 'Thin_termination': line_mode, 'ancestry': self.ancestry,
                   'last_paired': self.records[-1] if self.records else None}
        write(self.folder/'TRANSPORT_OWNER.json', summary)
        return summary


def incoming_lines(messages):
    """Use the raw Windows stdin descriptor to leave no buffered-reader lock on exit."""
    fd = sys.stdin.fileno()
    partial = bytearray()
    while chunk := os.read(fd, 65536):
        partial.extend(chunk)
        while (end := partial.find(b'\n')) >= 0:
            data = bytes(partial[:end+1])
            del partial[:end+1]
            messages.put(data)
        if len(partial) > MAX_WIRE:
            messages.put(b'')
            return
    messages.put(bytes(partial) if partial else None)


def thin(endpoint):
    endpoint = Path(endpoint).resolve(strict=True)
    config = read(endpoint)
    folder = endpoint.parent
    pid, last, active = os.getpid(), None, None
    require(config['host'] == '127.0.0.1', 'only_owned_loopback')
    write(folder/'THIN_STARTED.json', {'pid': pid, 'ppid': os.getppid(), 'started_ns': time.perf_counter_ns()})
    evidence = {'exit': 1, 'stdin_eof': False, 'normal_close_request': None}
    messages = queue.Queue()
    threading.Thread(target=incoming_lines, args=(messages,), daemon=True).start()
    try:
        ordinal = 0
        while True:
            try:
                raw = messages.get(timeout=.04)
            except queue.Empty:
                stop = folder/'THIN_STOP_REQUEST.json'
                if not stop.is_file():
                    continue
                target = read(stop)
                require(last is not None and last == target and messages.empty(), 'unpaired_idle_Thin_stop')
                evidence.update(exit=0, normal_close_request=target)
                return 0
            if raw is None:
                evidence.update(exit=0, stdin_eof=True)
                return 0
            require(raw.endswith(b'\n') and len(raw) <= MAX_WIRE, 'incomplete_Thin_stdio_request')
            request = json.loads(raw)
            ordinal += 1
            active = {'ordinal': ordinal, 'id': request.get('id'), 'request_sha256': sha(raw)}
            with socket.create_connection(('127.0.0.1', config['port']), timeout=10) as conn:
                packet(conn, {'token': config['token'], 'pid': pid, 'ordinal': ordinal})
                conn.sendall(raw)
                with conn.makefile('rb') as src:
                    raw_header = line(src)
                    require(bool(raw_header), 'owner_EOF_before_private_response')
                    header = json.loads(raw_header)
                    require(header[FRAME] == 'response' and all(header[k]==v for k,v in active.items()),
                            'wrong_raw_response_header')
                    response = line(src) if header['response_bytes'] else b''
                    require(len(response) == header['response_bytes'] and sha(response) == header['response_sha256']
                            and (not response or json.loads(response)['id'] == request['id']),
                            'unbound_or_missing_raw_response')
                    active.update(response_sha256=sha(response), response_bytes=len(response))
                    packet(conn, {FRAME: 'received', **active})
                    offer = json.loads(line(src))
                    require(offer[FRAME] == 'end' and offer['in_flight'] == 0
                            and all(offer[key] == val for key,val in active.items()), 'bad_exchange_end_offer')
                    ack = {**offer, FRAME: 'end_ack'}
                    packet(conn, ack)
                    conn.shutdown(socket.SHUT_WR)
                    require(not line(src), 'missing_owner_half_close')
            append(folder/'TRANSPORT_THIN.jsonl', {'request': active, 'offer': offer, 'ack': ack,
                   'peer_eof': True, 'thin_eof_sent': True, 'before_public_write': time.perf_counter_ns()})
            last = active
            active = None
            if response:
                sys.stdout.buffer.write(response)
                sys.stdout.buffer.flush()
                append(folder/'TRANSPORT_FLUSH.jsonl', {**last, 'flushed_ns': time.perf_counter_ns()})
    except (OSError, ValueError, KeyError) as error:
        evidence['error'] = {'type': type(error).__name__, 'message': str(error),
                             'winerror': getattr(error, 'winerror', None)}
        return 1
    finally:
        write(folder/'THIN_EXIT.json', {**evidence, 'last_paired': last, 'outstanding': active,
                                      'closed_ns': time.perf_counter_ns()})


def rows(path):
    return [json.loads(raw) for raw in Path(path).read_bytes().splitlines()]


def verify_cli_consumption(folder, event_path):
    """Match actual completed public CLI tool events to all paired original MCP results."""
    folder = Path(folder)
    owner = read(folder/'TRANSPORT_OWNER.json')
    paired_owner, paired_thin = map(rows, (folder/'TRANSPORT_OWNER.jsonl', folder/'TRANSPORT_THIN.jsonl'))
    trace = rows(folder/'wire/INDEX.jsonl')
    start, complete, accepted = {}, {}, []
    for event in rows(event_path):
        item = event.get('item', {})
        if item.get('type') != 'mcp_tool_call':
            continue
        if event['type'] == 'item.started':
            require(item['id'] not in start, 'duplicate_public_tool_start')
            start[item['id']] = item
        elif event['type'] == 'item.completed':
            require(item['id'] in start and item['id'] not in complete, 'unbound_or_duplicate_tool_completion')
            complete[item['id']] = item
    require(owner['closed'] and owner['zero_in_flight'] and len(trace) == len(paired_owner) == len(paired_thin),
            'owner_or_Thin_exchange_not_closed')
    remaining = list(complete.values())
    for wire, left, right in zip(trace,paired_owner,paired_thin,strict=True):
        pair = left['request']
        require(pair == right['request'] and left['ack'] == right['ack'] and left['offer'] == right['offer']
                and left['peer_eof'] and right['peer_eof'] and pin(wire['tx']['path']) == wire['tx']
                and pin(wire['rx']['path']) == wire['rx'] and pair['request_sha256'] == wire['tx']['sha256']
                and pair['response_sha256'] == wire['rx']['sha256'] and pair['ordinal'] == wire['ordinal'],
                'paired_close_does_not_bind_original_wire')
        if wire['method'] != 'tools/call':
            continue
        tx, rx = (read(wire[key]['path']) for key in ('tx','rx'))
        match = next((m for m in remaining if m['tool']==tx['params']['name']
                      and m['server']=='arm_engine' and m['arguments']==tx['params']['arguments']
                      and isinstance(m.get('result'),dict) and m['result'].get('content')==rx['result']['content']), None)
        require(match is not None, 'actual_CLI_completed_result_missing/' + str(wire['ordinal']))
        remaining.remove(match)
        accepted.append({'ordinal':wire['ordinal'], 'mcp_id':tx['id'], 'tool':match['tool'],
                         'cli_item_id':match['id'], 'rx':wire['rx']})
    require(bool(accepted) and set(start)==set(complete) and not remaining,
            'not_all_CLI_tool_attempts_received')
    receipt = {'passed':True, 'paired_public_calls':len(accepted), 'zero_outstanding_cli':True,
               'last_cli_delivery':accepted[-1], 'actual_tools':accepted,
               'public_events':pin(event_path), 'owner_close':pin(folder/'TRANSPORT_OWNER.json')}
    write(folder/'CONSUMER_DELIVERY.json', receipt)
    return receipt


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and len(sys.argv)==3 and sys.argv[1]=='thin',
            'only_owned_isolated_Thin_entry')
    raise SystemExit(thin(sys.argv[2]))
