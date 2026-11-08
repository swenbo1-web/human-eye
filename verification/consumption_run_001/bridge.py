"""Finite stdio MCP adapters: native Python forwarding and transparent HE relay.

Experiment helper only. No object inventory, solver, geometry, or answer is here.
"""
from contextlib import contextmanager
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
import uuid

MAX_LINE = 24 * 1024 * 1024
MAX_CODE = 256 * 1024


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8') + b'\n'


def decode(raw):
    def invalid(value): raise ValueError('nonfinite_json')
    return json.loads(raw, parse_constant=invalid)


class BudgetError(ValueError):
    pass


class Budget:
    """One local locked ledger shared by both MCP bridges and the controller."""
    def __init__(self, cell):
        self.cell = cell
        self.path = Path(cell['ledger_path'])

    @staticmethod
    def create(cell):
        path = Path(cell['ledger_path']); path.parent.mkdir(parents=True, exist_ok=True)
        value = dict(actions=0, physical_rpc=0, public_text_bytes=0, generated_image_blocks=0, halted=False,
            reason=None, inflight_rpc=[], events=[], deadline_perf_ns=cell['deadline_perf_ns'])
        with path.open('xb') as stream: stream.write(encoded(value))

    @contextmanager
    def locked(self):
        import msvcrt
        lock = self.path.with_suffix(self.path.suffix + '.lock')
        with lock.open('a+b') as stream:
            stream.seek(0, 2)
            if stream.tell() == 0: stream.write(b'0'); stream.flush()
            stop = min(self.cell['deadline_perf_ns'], time.perf_counter_ns() + 2_000_000_000)
            while True:
                try:
                    stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1); break
                except OSError:
                    if time.perf_counter_ns() >= stop: raise BudgetError('ledger_lock_deadline')
                    time.sleep(.005)
            try:
                value = decode(self.path.read_bytes())
                assert value['deadline_perf_ns'] == self.cell['deadline_perf_ns'], 'changed_deadline'
                try: yield value
                finally:
                    temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex)
                    with temporary.open('xb') as target:
                        target.write(encoded(value)); target.flush(); os.fsync(target.fileno())
                    os.replace(temporary, self.path)
            finally:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

    def remaining(self):
        remaining = (self.cell['deadline_perf_ns'] - time.perf_counter_ns()) / 1e9
        if remaining <= 0: raise BudgetError('answer_deadline')
        return remaining

    @staticmethod
    def _ready(state):
        if state['halted']: raise BudgetError('halted:' + str(state['reason']))

    def reserve(self, field, maximum, label):
        self.remaining()
        with self.locked() as state:
            self._ready(state)
            if state[field] >= maximum:
                state.update(halted=True, reason=field + '_limit')
                raise BudgetError(field + '_limit')
            state[field] += 1
            token = uuid.uuid4().hex
            state['events'].append(dict(kind=field, label=label, token=token, at_ns=time.perf_counter_ns()))
            if field == 'physical_rpc': state['inflight_rpc'].append(token)
            return token

    def reserve_action(self, label):
        self.remaining()
        with self.locked() as state:
            self._ready(state)
            state['actions'] += 1
            token = uuid.uuid4().hex
            state['events'].append(dict(kind='actions', label=label, token=token, at_ns=time.perf_counter_ns(),
                above_observation_threshold=state['actions'] > self.cell.get('action_observation_threshold',8)))
            return token

    def reserve_rpc(self, label='HE_owned_socket'):
        return self.reserve('physical_rpc', self.cell.get('max_native_rpc', 128), label)

    def complete_rpc(self, token, *, unknown=False):
        with self.locked() as state:
            if token not in state['inflight_rpc']: raise BudgetError('unknown_rpc_token')
            state['inflight_rpc'].remove(token)
            state['events'].append(dict(kind='rpc_outcome', token=token, unknown=unknown, at_ns=time.perf_counter_ns()))
            if unknown: state.update(halted=True, reason='physical_execution_outcome_unknown_no_replay')

    def charge_public(self, count, label):
        assert type(count) is int and count >= 0
        self.remaining()
        with self.locked() as state:
            self._ready(state)
            if state['public_text_bytes'] + count > self.cell.get('max_public_text_bytes', 1024 * 1024):
                state.update(halted=True, reason='public_text_limit')
                state['events'].append(dict(kind='undelivered_public_text', bytes=count, label=label))
                raise BudgetError('public_text_limit')
            state['public_text_bytes'] += count
            state['events'].append(dict(kind='public_text', bytes=count, label=label, at_ns=time.perf_counter_ns()))

    def halt(self, reason):
        with self.locked() as state:
            state.update(halted=True, reason=reason)

    poison = halt
    charge_text = charge_public

    def image_output(self, count, label):
        self.remaining()
        with self.locked() as state:
            self._ready(state)
            state['generated_image_blocks'] += count
            state['events'].append(dict(kind='generated_images', count=count, label=label, at_ns=time.perf_counter_ns()))
            if state['generated_image_blocks'] > self.cell.get('max_constructed_images', 1):
                state.update(halted=True, reason='image_output_limit')
                raise BudgetError('image_output_limit')


def public_text_bytes(response):
    """MCP-side exposure: full returned catalogue plus literal text blocks.

    Host filtering/schema reserialization is a distinct, possibly unexposed cost.
    Count the full returned catalogue conservatively before any host filtering.
    """
    result = response.get('result', {})
    total = len(encoded(result['tools'])) - 1 if 'tools' in result else 0
    total += sum(len(block.get('text', '').encode('utf8')) for block in result.get('content', [])
        if block.get('type') == 'text')
    if 'error' in response: total += len(encoded(response['error'])) - 1
    return total


NATIVE_TOOL = dict(name='execute_blender_code', description=(
    'Execute Python in the private Blender session with bpy, Python/math, scripts, aggregation and per-answer cached variables; return the original execution response. '
    'The neutral host requires original scene geometry at the end of each call. Optional deliver_paths relays requested PNGs from the private workspace as images.'),
    inputSchema=dict(type='object', properties=dict(code=dict(type='string'),
        deliver_paths=dict(type='array', items=dict(type='string'), maxItems=1)), required=['code'], additionalProperties=False))


def register_images(cell, budget, blocks, origin):
    """Reuse the original neutral ImageLedger for common PNG delivery credit."""
    if not blocks: return
    folder = Path(cell['audit_root'])/'image_attempts'; folder.mkdir(parents=True, exist_ok=True)
    target = folder/(uuid.uuid4().hex+'.json')
    record = dict(origin=origin, generated_blocks=len(blocks), started_ns=time.perf_counter_ns(),
        encoded_data_bytes=sum(len(block.get('data','').encode('utf8')) for block in blocks), rows=[], reservation=None)
    try:
        budget.image_output(len(blocks), origin)
        source = Path(cell['native_helper']); raw = source.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == cell['native_helper_sha256'], 'native_helper_changed'
        spec = importlib.util.spec_from_file_location('_consumption_neutral_images', source)
        module = importlib.util.module_from_spec(spec)
        exec(compile(raw, str(source), 'exec', dont_inherit=True), module.__dict__)
        limits = cell.get('image_limits', dict(max_images=1,max_single_pixels=768**2,max_total_pixels=768**2))
        ledger = module.ImageLedger(Path(cell['native_workspace']).resolve(), limits=limits)
        for block in blocks:
            if block.get('mimeType') != 'image/png': raise ValueError('common_image_route_requires_PNG')
            payload = base64.b64decode(block['data'], validate=True)
            row = ledger.register_external_image(payload, label=origin, origin=origin)
            record['rows'].append(row)
            maximum = cell.get('max_image_dimension', 768)
            if row['width'] > maximum or row['height'] > maximum: raise ValueError('common_image_dimension_limit')
        record['reservation'] = ledger.reserve_delivery([row['image_id'] for row in record['rows']])
    except Exception as error:
        record['error'] = dict(type=type(error).__name__,message=str(error))
        budget.halt('image_generation_or_delivery_budget_failure_no_refund')
        raise
    finally:
        record['elapsed_ns'] = time.perf_counter_ns()-record['started_ns']
        target.write_bytes(encoded(record))


class Native:
    def __init__(self, cell, budget, audit):
        self.cell, self.budget, self.audit = cell, budget, audit

    def images(self, names):
        if not names: return []
        workspace = Path(self.cell['native_workspace']).resolve()
        blocks = []
        for name in names:
            target = Path(name); target = (target if target.is_absolute() else workspace / target).resolve()
            if not target.is_relative_to(workspace): raise ValueError('image_outside_private_workspace')
            blocks.append(dict(type='image', mimeType='image/png', data=base64.b64encode(target.read_bytes()).decode('ascii')))
        register_images(self.cell, self.budget, blocks, 'native_consumer_requested_PNG')
        # Reserve before publication; no claim that the model received images.
        return blocks

    def execute(self, code):
        endpoint = self.cell['endpoint']
        raw = encoded(dict(type='execute_code', params=dict(code=code)))
        token = self.budget.reserve_rpc('native_execute_code'); start = time.perf_counter_ns()
        folder = self.audit / ('native_' + token); folder.mkdir()
        (folder / 'TX.bin').write_bytes(raw)
        received = bytearray(); known = False
        try:
            with socket.create_connection((endpoint['host'], endpoint['port']), timeout=self.budget.remaining()) as connection:
                connection.settimeout(self.budget.remaining()); connection.sendall(raw); connection.shutdown(socket.SHUT_WR)
                while True:
                    connection.settimeout(self.budget.remaining()); block = connection.recv(65536)
                    if not block: break
                    received.extend(block)
                    if len(received) > 20 * 1024 * 1024: raise ValueError('native_response_wire_limit')
            value = decode(received)
            if type(value) is not dict or value.get('status') not in ('success', 'error'): raise ValueError('native_response_envelope')
            known = True
            if value.get('poisoned'): self.budget.halt('native_host_poisoned')
            return value
        finally:
            (folder / 'RX.bin').write_bytes(received)
            (folder / 'METER.json').write_bytes(encoded(dict(tx_attempted_bytes=len(raw), rx_bytes=len(received),
                started_ns=start, elapsed_ns=time.perf_counter_ns()-start, outcome_known=known)))
            self.budget.complete_rpc(token, unknown=not known)

    def handle(self, request):
        method, request_id = request.get('method'), request.get('id')
        if 'id' not in request: return None
        if method == 'initialize':
            version = request.get('params', {}).get('protocolVersion', '2024-11-05')
            result = dict(protocolVersion=version, capabilities=dict(tools=dict(listChanged=False)),
                serverInfo=dict(name='consumption-neutral-native', version='1'))
        elif method == 'ping': result = {}
        elif method == 'tools/list': result = dict(tools=[NATIVE_TOOL])
        elif method == 'tools/call':
            params = request.get('params', {}); args = params.get('arguments', {})
            if params.get('name') != NATIVE_TOOL['name'] or type(args) is not dict or set(args)-{'code','deliver_paths'}:
                raise ValueError('native_tool_arguments')
            code, paths = args.get('code'), args.get('deliver_paths', [])
            if type(code) is not str or len(code.encode('utf8')) > MAX_CODE: raise ValueError('native_code_bytes')
            if type(paths) is not list or len(paths)>1 or any(type(p) is not str for p in paths): raise ValueError('native_deliver_paths')
            value = self.execute(code)
            result = dict(content=[dict(type='text', text=encoded(value).decode('utf8').rstrip('\n'))] + self.images(paths),
                isError=value['status'] != 'success')
        else: return dict(jsonrpc='2.0', id=request_id, error=dict(code=-32601, message='Method not found'))
        return dict(jsonrpc='2.0', id=request_id, result=result)


def reader(stream):
    output = queue.Queue()
    def consume():
        while True:
            raw = stream.readline(MAX_LINE+1); output.put(raw)
            if not raw: break
    threading.Thread(target=consume, daemon=True).start()
    return output


class HE:
    def __init__(self, cell, budget, audit):
        self.budget = budget
        self.stderr = (audit/'HE_STDERR.bin').open('wb')
        self.process = subprocess.Popen(cell['he_argv'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.stderr, cwd=cell.get('he_cwd'), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.incoming = reader(self.process.stdout)

    def handle_raw(self, raw, request):
        self.budget.remaining(); self.process.stdin.write(raw); self.process.stdin.flush()
        if 'id' not in request: return None
        reply = self.incoming.get(timeout=self.budget.remaining())
        if not reply or len(reply)>MAX_LINE: raise ValueError('HE_stdio_EOF_or_frame_limit_no_replay')
        if decode(reply).get('id') != request['id']: raise ValueError('HE_response_identity_no_replay')
        return reply

    def close(self):
        self.process.stdin.close()
        try: self.process.wait(timeout=5)
        except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=5)
        self.stderr.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=('native','he'), required=True)
    parser.add_argument('--cell', type=Path, required=True)
    options = parser.parse_args(argv); cell = decode(options.cell.read_bytes()); budget = Budget(cell)
    audit = Path(cell['audit_root'])/('bridge_'+options.kind); audit.mkdir(parents=True, exist_ok=False)
    backend = Native(cell, budget, audit) if options.kind=='native' else HE(cell, budget, audit)
    incoming = reader(sys.stdin.buffer); sequence = 0
    try:
        while True:
            raw = incoming.get(timeout=budget.remaining())
            if not raw: break
            sequence += 1; folder = audit/str(sequence).zfill(3); folder.mkdir()
            (folder/'TX.bin').write_bytes(raw); started = time.perf_counter_ns()
            request = None; reply = None; published = False
            try:
                if len(raw)>MAX_LINE: raise ValueError('MCP_frame_limit')
                request = decode(raw)
                if type(request) is not dict or request.get('jsonrpc')!='2.0': raise ValueError('invalid_MCP_request')
                if request.get('method')=='tools/call' and 'id' in request:
                    budget.reserve_action(options.kind + ':' + str(request.get('params',{}).get('name')))
                if options.kind=='he': reply = backend.handle_raw(raw, request)
                else:
                    value = backend.handle(request); reply = None if value is None else encoded(value)
                if reply is not None:
                    if options.kind=='he':
                        register_images(cell, budget, [block for block in decode(reply).get('result',{}).get('content',[])
                            if block.get('type')=='image'], 'HE_original_PNG')
                    budget.charge_public(public_text_bytes(decode(reply)), options.kind + ':MCP_response')
                    budget.remaining(); sys.stdout.buffer.write(reply); sys.stdout.buffer.flush(); published = True
            except BudgetError:
                # No over-budget error payload or late result is published.
                budget.halt('budget_exhausted'); raise
            except Exception as error:
                if options.kind=='he': budget.halt('HE_protocol_or_transport_unknown_no_replay'); raise
                value = dict(jsonrpc='2.0',id=request.get('id') if type(request) is dict else None,
                    error=dict(code=-32000,message=str(error),data=dict(automatic_retry=False)))
                reply = encoded(value); budget.charge_public(public_text_bytes(value), 'native:error')
                budget.remaining(); sys.stdout.buffer.write(reply); sys.stdout.buffer.flush(); published = True
            finally:
                if reply is not None: (folder/'GENERATED_RESPONSE.bin').write_bytes(reply)
                if published: (folder/'RX.bin').write_bytes(reply)
                (folder/'METER.json').write_bytes(encoded(dict(tx_bytes=len(raw), generated_rx_bytes=len(reply or b''),
                    published_rx_bytes=len(reply or b'') if published else 0,
                    elapsed_ns=time.perf_counter_ns()-started)))
    finally:
        if options.kind=='he': backend.close()


if __name__ == '__main__': main()
