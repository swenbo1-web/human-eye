"""Validation observer loaded before the unchanged default owned worker.

Only __init__ is profiled. Then wrappers read actual residency counters and
direct native RNA after capture/apply. Observation adds unquantified overhead
inside the measured worker request; it never changes product source or APIs.
"""
import json
import os
from pathlib import Path
import sys
import time
from collections import Counter
import bpy

DEST = Path(os.environ['ARCH_INTEGRATION_WORKER_OBSERVER'])
C_CALLS = Counter()

def c_profile(frame, event, arg):
    if event == 'c_call' and getattr(arg, '__name__', None) in ('to_mesh', 'calc_loop_triangles', 'to_mesh_clear'):
        C_CALLS[arg.__name__] += 1

def emit(value):
    with DEST.open('a', encoding='utf8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')

def snapshot(host, method, result):
    started = time.perf_counter_ns()
    meshes = []
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH': continue
        if obj.modifiers or obj.constraints or obj.parent:
            raise ValueError('owned oracle requires plain independent fixture meshes')
        meshes.append({'name': obj.name, 'vertices': [list(obj.matrix_world @ v.co) for v in obj.data.vertices],
                       'faces': [list(p.vertices) for p in obj.data.polygons], 'location': list(obj.location)})
    packet = result
    while isinstance(packet, dict) and 'capture_state' not in packet and isinstance(packet.get('capture'), dict):
        packet = packet['capture']
    token = packet.get('capture_state') if isinstance(packet, dict) else None
    value = {'event': 'worker_snapshot', 'method': method, 'work': host.residency_work(),
             'c_call_events': dict(C_CALLS),
             'work_scope': 'work counts resident only; c_call counts require calibration against resident to_mesh; full-capture world maps unknown',
             'capture_state': token,
             'native': {'meshes': meshes, 'scale': bpy.context.scene.unit_settings.scale_length,
                        'scene': bpy.context.scene.name, 'frame': bpy.context.scene.frame_current,
                        'basis': 'independent direct bpy RNA; plain meshes, no host/decoder/solver geometry'}}
    value['observer_ms_before_append'] = (time.perf_counter_ns() - started) / 1e6
    emit(value)

def profile(frame, event, arg):
    if event != 'return' or frame.f_code.co_name != '__init__': return
    host = frame.f_locals.get('self')
    if host is None or type(host).__name__ != 'BlenderSceneHost': return
    sys.setprofile(c_profile)
    for name in ('capture_delta', 'apply_transform'):
        original = getattr(host, name)
        def wrapped(*a, _original=original, _name=name, **kw):
            result = _original(*a, **kw)
            snapshot(host, _name, result)
            return result
        setattr(host, name, wrapped)
    emit({'event': 'observer_attached', 'pid': os.getpid(), 'host_module': type(host).__module__,
          'source': sys.modules[type(host).__module__].__file__,
          'overhead': 'c_call profile + native RNA traversal + counters + JSON append per capture/apply; not subtracted'})

emit({'event': 'observer_armed', 'pid': os.getpid()})
sys.setprofile(profile)
