"""Validation-only observers around real production stdio and default owned host.

No dispatch, capture, normalization, solver, decoder, source guard or worker is
reimplemented. Counter/profile/file/socket observers add unquantified overhead.
"""
import argparse
from collections import Counter
import json
import io
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from human_eye_plugin import live_spatial_mcp as mcp
from human_eye_plugin.blender_mcp_host import BlenderMCPHost
from human_eye_plugin.runtime_identity import runtime_identity

COUNTS = Counter()
TIMES = Counter()
ACTIVE = {}
TOKENS = []
NAMES = {'_validated_scene', 'from_dict', 'task_result', 'surface_nearest_result',
         'classify_closed_solids', 'measure_surface_proximity', 'measure_pair_geometry',
         '_rank_surface_results', '_locked', '_save', '_runtime', '_read_object', '_atomic_write',
         '_capture_request', 'capture_task_scene', 'capture_nearest_candidates', 'apply'}

def profile(frame, event, arg):
    name = frame.f_code.co_name
    if name not in NAMES: return
    filename = frame.f_code.co_filename.replace('\\', '/')
    if '/human_eye_' not in filename: return
    key = filename.rsplit('/', 1)[-1] + ':' + name
    if event == 'call':
        COUNTS[key] += 1
        ACTIVE[id(frame)] = time.perf_counter_ns()
    elif event == 'return':
        start = ACTIVE.pop(id(frame), None)
        if start is not None: TIMES[key] += time.perf_counter_ns() - start
        if name in ('_capture_request', 'capture_task_scene', 'capture_nearest_candidates') and isinstance(arg, dict):
            packet = arg.get('capture', arg)
            if 'capture_state' in packet: TOKENS.append({'function': name, 'capture_state': packet['capture_state']})

class Wire:
    def __init__(self, folder):
        self.folder = folder
        self.lock = threading.Lock()
        self.counts = Counter()
    def record(self, name, data):
        if isinstance(data, str): data = data.encode('utf8')
        with self.lock:
            with (self.folder / name).open('ab') as stream: stream.write(data)
            self.counts[name] += len(data)

class SocketObserver:
    def __init__(self, sock, wire): self.sock, self.wire = sock, wire
    def sendall(self, data, *a, **kw):
        result = self.sock.sendall(data, *a, **kw)
        self.wire.record('mcp_tx.bin', data)
        return result
    def recv(self, *a, **kw):
        data = self.sock.recv(*a, **kw)
        self.wire.record('mcp_rx.bin', data)
        return data
    def __getattr__(self, name): return getattr(self.sock, name)
    def __enter__(self): return self
    def __exit__(self, *a): self.sock.close()

class BinaryTee(io.BufferedIOBase):
    """Observe bytes below UTF8 decoding and universal newline conversion."""
    def __init__(self, stream, wire, name):
        super().__init__()
        self.stream, self.wire, self.name = stream, wire, name
    def readable(self): return self.stream.readable()
    def writable(self): return self.stream.writable()
    def seekable(self): return False
    def fileno(self): return self.stream.fileno()
    def read(self, size=-1):
        data = self.stream.read(size)
        self.wire.record(self.name, data)
        return data
    def read1(self, size=-1):
        data = self.stream.read1(size)
        self.wire.record(self.name, data)
        return data
    def readinto(self, buffer):
        count = self.stream.readinto(buffer)
        if count: self.wire.record(self.name, bytes(memoryview(buffer)[:count]))
        return count
    def write(self, data):
        count = self.stream.write(data)
        if count: self.wire.record(self.name, bytes(memoryview(data)[:count]))
        return count
    def flush(self):
        if not self.stream.closed: return self.stream.flush()
    def close(self):
        if not self.closed:
            super().close()
            self.stream.close()

def observe_text(stream, wire, name):
    encoding, errors = stream.encoding, stream.errors
    line_buffering, write_through = stream.line_buffering, stream.write_through
    raw = stream.detach()
    return io.TextIOWrapper(BinaryTee(raw, wire, name), encoding=encoding, errors=errors,
                            newline=None, line_buffering=line_buffering, write_through=write_through)

def delta(now, before):
    return {k: now[k] - before.get(k, 0) for k in now if now[k] != before.get(k, 0)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('shared', 'owned'), required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--blender')
    parser.add_argument('--scene')
    parser.add_argument('--spatial-task-only', action='store_true')
    args = parser.parse_args()
    mcp._configure_utf8_stdio()
    folder = Path(args.directory)
    folder.mkdir(parents=True, exist_ok=True)
    wire = Wire(folder)
    metric = folder / 'metrics.jsonl'
    def emit(value):
        with metric.open('a', encoding='utf8') as stream: stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
    emit({'event': 'startup', 'identity': runtime_identity(mode='live'), 'mode': args.mode,
          'observation_overhead': 'Python call profile, real wire copies/appends, metrics append; unquantified and not subtracted'})
    original_connect = BlenderMCPHost._connect
    BlenderMCPHost._connect = lambda self, deadline: SocketObserver(original_connect(self, deadline), wire)
    original_popen = subprocess.Popen
    def popen(command, *a, **kw):
        # Keep the default worker expression and source guard unchanged. Blender
        # executes one observer file first, before the verified worker expression.
        command = list(command)
        if args.mode == 'owned' and Path(command[0]).resolve() == Path(args.blender).resolve():
            index = command.index('--python-expr')
            command[index:index] = ['--python', str(Path(__file__).with_name('observe_worker.py'))]
            env = dict(os.environ if kw.get('env') is None else kw['env'])
            env['ARCH_INTEGRATION_WORKER_OBSERVER'] = str(folder / 'worker_observer.jsonl')
            kw['env'] = env
            emit({'event': 'default_worker_launch', 'command': command,
                  'worker_path_override': False, 'observer_before_fixed_worker': True})
            process = original_popen(command, *a, **kw)
            process.stdin = observe_text(process.stdin, wire, 'owned_tx.bin')
            process.stdout = observe_text(process.stdout, wire, 'owned_rx.bin')
            return process
        return original_popen(command, *a, **kw)
    subprocess.Popen = popen
    original_call = mcp.LiveSpatialMCPServer._call_tool
    def measured_call(self, name, arguments, **kw):
        before, times, transport, token_index = COUNTS.copy(), TIMES.copy(), wire.counts.copy(), len(TOKENS)
        decoder = getattr(self.service.host, '_scene_decoder', None)
        decoder_before = decoder.work_totals() if decoder else None
        started = time.perf_counter_ns()
        try:
            return original_call(self, name, arguments, **kw)
        finally:
            elapsed = time.perf_counter_ns() - started
            decoder = getattr(self.service.host, '_scene_decoder', None)
            emit({'event': 'tool', 'name': name, 'arguments': arguments,
                  'request_id': kw.get('mcp_request_id'), 'dispatch_content_ms': elapsed / 1e6,
                  'calls': delta(COUNTS, before), 'profile_inclusive_ms': {k: v / 1e6 for k, v in delta(TIMES, times).items()},
                  'transport_bytes': delta(wire.counts, transport), 'capture_states': TOKENS[token_index:],
                  'decoder_before': decoder_before, 'decoder_after': decoder.work_totals() if decoder else None,
                  'scope': 'tool dispatch through MCP content; final stdio encode/write excluded; parent records full RTT'})
    mcp.LiveSpatialMCPServer._call_tool = measured_call
    sys.setprofile(profile)
    try:
        argv = ['--config', args.config] + (['--spatial-task-only'] if args.spatial_task_only else [])
        if args.mode == 'shared':
            from human_eye_plugin.production_server import main as production_main
            return production_main(argv)
        from verification.arch_integration_001.owned_service_stdio import main as owned_main
        return owned_main(argv + ['--blender', args.blender, '--scene', args.scene, '--timeout-s', '20'])
    finally:
        sys.setprofile(None)
        emit({'event': 'exit', 'transport_bytes': dict(wire.counts), 'calls': dict(COUNTS)})

if __name__ == '__main__': raise SystemExit(main())
