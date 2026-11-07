"""Frozen-source production stdio launcher with transparent QA observations.

Only owned-endpoint socket byte logging and a counting profile hook are added.
The original production launcher, connector methods and socket outputs execute.
"""
import hashlib
import json
from pathlib import Path
import socket
import sys
import time
import traceback
import types
from types import MappingProxyType

plan = json.loads(Path(sys.argv[1]).read_bytes())
out = Path(plan['run_root'])/'stdio'
out.mkdir(exist_ok=False)
root = Path(plan['source_root'])
blobs = MappingProxyType({r['path']:(root/r['path']).read_bytes() for r in plan['product_manifest']})
assert {p:hashlib.sha256(b).hexdigest() for p,b in blobs.items()} == {r['path']:r['sha256'] for r in plan['product_manifest']}
loader_path = root/'human_eye_plugin/verified_source_loader.py'
loader = types.ModuleType('_surface_entry_stdio_loader'); loader.__file__ = str(loader_path)
sys.modules[loader.__name__] = loader
exec(compile(blobs['human_eye_plugin/verified_source_loader.py'], str(loader_path), 'exec', dont_inherit=True), loader.__dict__)
guard = loader.install(root, plan['product_manifest'], sources=blobs, bootstrap_module=loader)
package = types.ModuleType('human_eye_plugin'); package.__path__ = [str(root/'human_eye_plugin')]
guard.allow_namespace(package); sys.modules[package.__name__] = package
from human_eye_plugin import production_server, runtime_identity
assert runtime_identity.runtime_identity()['source_sha256'] == plan['source_sha256']
assert runtime_identity.check_task_source()['compatible'] and guard.verify_loaded()

record = dict(sockets=[], calls=[], profile_overhead_ns=0, started_ns=time.perf_counter_ns(),
    source_sha256=plan['source_sha256'], original_request_unchanged=True, no_packet_file_input=True)
original_socket = socket.socket
class MeterSocket(original_socket):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.qa_row = None; self.qa_folder = None
    def connect_ex(self, address):
        if tuple(address[:2]) == (plan['endpoint']['host'], plan['endpoint']['port']):
            self.qa_folder = out/('socket_'+str(len(record['sockets'])+1)); self.qa_folder.mkdir()
            self.qa_row = dict(address=list(address), send_attempted_bytes=0, send_completed_bytes=0,
                received_bytes=0, started_ns=time.perf_counter_ns())
            record['sockets'].append(self.qa_row)
        return super().connect_ex(address)
    def sendall(self, raw, *args, **kwargs):
        if self.qa_row is not None:
            with (self.qa_folder/'TX.bin').open('ab') as stream: stream.write(raw)
            self.qa_row['send_attempted_bytes'] += len(raw)
        result = super().sendall(raw, *args, **kwargs)
        if self.qa_row is not None: self.qa_row['send_completed_bytes'] += len(raw)
        return result
    def recv(self, *args, **kwargs):
        raw = super().recv(*args, **kwargs)
        if self.qa_row is not None:
            with (self.qa_folder/'RX.bin').open('ab') as stream: stream.write(raw)
            self.qa_row['received_bytes'] += len(raw)
        return raw
    def close(self):
        try: return super().close()
        finally:
            if self.qa_row is not None:
                self.qa_row['ended_ns'] = time.perf_counter_ns()
                (self.qa_folder/'METER.json').write_text(json.dumps(self.qa_row, indent=2)+'\n', encoding='utf8')
socket.socket = MeterSocket

targets = {'_surface_pair_measurement', 'measure_surface_proximity', '_nearest', '_rank_surface_results',
    'surface_nearest_result', 'capture_nearest_candidates', '_surface_nearest', 'surface_nearest'}
active = {}
def profile(frame, event, arg):
    if event not in ('call', 'return'): return
    filename = frame.f_code.co_filename; name = frame.f_code.co_name
    if name not in targets or not filename.startswith(str(root)): return
    started = time.perf_counter_ns()
    try:
        if event == 'call':
            row = dict(name=name, filename=filename, started_ns=started)
            if name == 'surface_nearest_result':
                cache = frame.f_locals.get('cache')
                if cache is not None: row['cache_before'] = cache.stats()
            active[id(frame)] = row; record['calls'].append(row)
        elif event == 'return':
            row = active.pop(id(frame), None)
            if row is not None:
                row['elapsed_ns'] = time.perf_counter_ns()-row['started_ns']
                if name == 'capture_nearest_candidates' and isinstance(arg, dict):
                    row['work'] = arg.get('work'); row['packet_bytes_json'] = len(json.dumps(arg, separators=(',',':'), allow_nan=False).encode())
                    capture = arg.get('capture', {})
                    row['captured_mesh_count'] = len(capture.get('meshes', []))
                    row['captured_vertex_count'] = sum(len(m.get('vertices', [])) for m in capture.get('meshes', []))
                if name == 'surface_nearest_result':
                    cache = frame.f_locals.get('cache')
                    if cache is not None: row['cache_after'] = cache.stats()
                    row['diagnostics'] = frame.f_locals.get('diagnostics')
    finally: record['profile_overhead_ns'] += time.perf_counter_ns()-started
assert sys.getprofile() is None
sys.setprofile(profile)
exit_code = None
try:
    exit_code = production_server.main(['--config', plan['config_path']])
except BaseException as error:
    record['error'] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
    raise
finally:
    sys.setprofile(None); socket.socket = original_socket
    record['ended_ns'] = time.perf_counter_ns(); record['exit_code'] = exit_code
    record['counts'] = {name:sum(row['name']==name for row in record['calls']) for name in sorted(targets)}
    record['counts']['captured_meshes'] = sum(row.get('captured_mesh_count',0) for row in record['calls'])
    record['counts']['captured_vertices'] = sum(row.get('captured_vertex_count',0) for row in record['calls'])
    try:
        owned = {n:m for n,m in sys.modules.items() if guard._owned_name(n)}
        record['execution_witness'] = dict(guard_protocol=guard.protocol, guard_verified=bool(guard.verify_loaded()),
            loaded_engine_module_count=len(owned), every_loaded_module_has_execution_or_namespace_witness=all(
                guard._executed.get(id(m),(None,))[0] is m or guard._namespaces.get(id(m)) is m for m in owned.values()),
            bound_generation=runtime_identity.check_task_source())
    except BaseException as error: record['witness_error'] = dict(type=type(error).__name__, message=str(error))
    (out/'BOOTSTRAP_RESULT.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n', encoding='utf8')
raise SystemExit(exit_code)
