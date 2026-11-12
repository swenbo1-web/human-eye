"""Independent offline branch probes; exact frozen source, fake APIs and clocks."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import threading
from types import SimpleNamespace as NS

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT = Path(__file__).resolve().parent
COMMIT = 'c6355a01a4c6ee204a0d676cd9309f02428fe3ba'
sources = []
results = []

def read(name):
    p = ROOT / 'human_eye_plugin' / name
    b = p.read_bytes()
    assert b == subprocess.check_output(['git', 'show', COMMIT + ':human_eye_plugin/' + name], cwd=ROOT)
    sources.append({'path': str(p), 'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)})
    return b

host_blob = read('blender_host.py')
host_ns = {'__name__': 'independent_frozen_host', '__file__': str(OUT / 'frozen_host.py')}
exec(compile(host_blob, str(OUT / 'frozen_host.py'), 'exec'), host_ns)
Host = host_ns['BlenderSceneHost']
guards = dict(parent=None, children=[], constraints=[], modifiers=[], animation=None,
              data_animation=None, rigid_body=None, rigid_body_constraint=None, shape_keys=None,
              linked=False, edit_mode=False)
owner = NS(object_id=lambda obj: obj.name, _guard_description=lambda obj: guards)
matrix = [[float(i == j) for j in range(4)] for i in range(4)]
corners = [(x, y, z) for x in (0., 1.) for y in (0., 1.) for z in (0., 1.)]
data = NS(vertices=[NS(co=p) for p in ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.))],
          polygons=[NS(loop_start=0, loop_total=3)], loops=[NS(vertex_index=i) for i in range(3)], library=None)

class Object:
    def __init__(self, mode, evaluated=False):
        self.mode = mode
        self.name = 'hidden_static'
        self.data = data
        self.matrix_world = matrix
        self.hide_viewport = True
        self.is_evaluated = evaluated
    @property
    def bound_box(self):
        if self.mode == 'bbox_runtime_error':
            raise RuntimeError('injected_bbox_failure')
        return corners
    def evaluated_get(self, graph):
        if self.mode == 'eval_runtime_error':
            raise RuntimeError('injected_evaluation_failure')
        if self.mode == 'eval_reference_error':
            raise ReferenceError('injected_reference_failure')
        return self

for case, evaluated in [('normal_hidden', False), ('bbox_runtime_error', False),
                         ('bbox_runtime_error', True), ('eval_runtime_error', False),
                         ('eval_reference_error', False)]:
    row = {'case': case, 'evaluated': evaluated}
    try:
        answer = Host._acquisition_directory_source(owner, Object(case, evaluated), None, 1., allow_hidden=True)
        row.update(returned=True, source_mode=answer[-1], bounds_unknown=answer[-2] is None)
    except Exception as e:
        row.update(returned=False, error=type(e).__name__, message=str(e))
    results.append(row)
assert results[0]['source_mode'] == 'static_original_hidden'
assert results[1]['error'] == 'RuntimeError'
assert results[2]['returned'] and results[2]['bounds_unknown']
assert results[3]['error'] == 'RuntimeError'
assert results[4]['error'] == 'ReferenceError'

def extracted_class(blob, original_class, methods, namespace):
    tree = ast.parse(blob)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == original_class)
    nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    assert len(nodes) == len(methods)
    # Keep complete method bodies; dependencies are deterministic API doubles.
    new_cls = ast.ClassDef(name='ProbeClass', bases=[], keywords=[], body=nodes, decorator_list=[])
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), new_cls], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<unchanged-frozen-methods>', 'exec'), namespace)
    return namespace['ProbeClass']

class Clock:
    def __init__(self): self.ns = 0
    def perf_counter_ns(self): return self.ns
    def monotonic(self): return self.ns / 1e9

mcp_blob = read('blender_mcp_host.py')
clock = Clock()
class StopProbe(Exception): pass
mcp_globals = dict(time=clock, math=__import__('math'), _MAX_RESPONSE_BYTES=64*1024*1024,
                   _ReadonlyPreconnectUnavailable=RuntimeError)
MCP = extracted_class(mcp_blob, 'BlenderMCPHost', {'capture_surface_scan', '_exchange'}, mcp_globals)
obj = MCP()
obj.timeout_s = 30.
obj._observation_depth = 1
observed = {}
def connect(deadline):
    observed['transport_deadline_s'] = deadline
    raise StopProbe()
def request(command, params):
    observed['forwarded_parent_deadline_ns'] = params['deadline_ns']
    return obj._exchange(b'not-sent')
obj._connect, obj._request = connect, request
try:
    obj.capture_surface_scan(.002, 100_000_000, 100000)
except StopProbe:
    pass
assert observed == {'forwarded_parent_deadline_ns': 100_000_000, 'transport_deadline_s': 30.}
results.append({'case': 'MCP_fake_clock_short_parent', **observed, 'real_network_calls': 0})
def late_request(command, params):
    clock.ns = 500_000_000
    return {}
clock.ns = 0
obj._request = late_request
try:
    obj.capture_surface_scan(.002, 100_000_000, 100000)
    raise AssertionError('late success accepted')
except ValueError as error:
    assert str(error) == 'acquisition_deadline_exceeded'
    results.append({'case': 'MCP_late_success_rejected', 'error': str(error), 'simulated_elapsed_s': .5})

process_blob = read('blender_process.py')
clock = Clock()
process_globals = dict(time=clock, threading=threading, json=json, queue=queue, math=__import__('math'),
    _MAX_LINE_CHARS=64*1024*1024, _MAX_CAPTURE_REQUEST_CHARS=65536, _MAX_REQUEST_CHARS=4096,
    SCENE_DELTA_PROTOCOL='human-eye-scene-delta-v1', HostTransportError=RuntimeError, HostRemoteError=RuntimeError)
Process = extracted_class(process_blob, 'BlenderProcessHost', {'capture_surface_scan', '_capture_request', '_request'}, process_globals)
obj = Process()
obj.timeout = 30.
obj._lock = threading.RLock()
obj._sequence, obj._poisoned, obj._capabilities = 0, False, {}
obj._ensure_live = lambda: None
log = []
class Input:
    def write(self, payload):
        log.append({'op': 'write', 'at_s': clock.monotonic()})
        clock.ns += 250_000_000
    def flush(self):
        log.append({'op': 'flush', 'at_s': clock.monotonic()})
        clock.ns += 250_000_000
class Replies:
    def get(self, timeout):
        log.append({'op': 'queue_wait', 'at_s': clock.monotonic(), 'timeout_s': timeout})
        clock.ns += int(timeout * 1e9)
        return 'response', {'id': 1, 'result': {}}
obj._process, obj._responses = NS(stdin=Input()), Replies()
try:
    obj.capture_surface_scan(.002, 100_000_000, 100000)
    raise AssertionError('late success accepted')
except ValueError as error:
    assert str(error) == 'acquisition_deadline_exceeded'
assert log[-1] == {'op': 'queue_wait', 'at_s': .5, 'timeout_s': .1}
assert clock.ns == 600_000_000
results.append({'case': 'Process_fake_write_consumes_original_deadline', 'parent_deadline_s': .1,
                'operations': log, 'simulated_elapsed_s': clock.monotonic(),
                'late_success_rejected': True, 'real_processes': 0})

payload = dict(scope='Independent conditional pure-Python probes; not Blender or socket failure injection',
               candidate=COMMIT, checks=8, passed=True, results=results, sources=sources)
(OUT/'PROBES.json').write_text(json.dumps(payload, indent=2)+'\n', encoding='utf8', newline='\n')
print(json.dumps({'passed': True, 'cases':len(results), 'output':str(OUT/'PROBES.json')}))
