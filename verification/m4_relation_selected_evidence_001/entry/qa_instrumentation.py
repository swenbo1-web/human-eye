"""Owned Blender QA counters and one fixed initial rigid mapping."""

import sys
import time
from pathlib import Path


def host_work():
    hosts = {}
    for module in list(sys.modules.values()):
        namespace = getattr(module, '__dict__', {})
        host = namespace.get('_mcp_resident_host')
        if host is not None:
            identity = id(host)
            if identity not in hosts:
                state = getattr(host, '_residency', None)
                generation = None if state is None else {
                    'instance_id': state.instance_id, 'epoch': state.epoch, 'revision': state.revision}
                hosts[identity] = {'module_aliases': [], 'work': host.residency_work(),
                                   'generation': generation}
            hosts[identity]['module_aliases'].append(namespace.get('__name__'))
    hosts = list(hosts.values())
    totals = {}
    for row in hosts:
        for key, value in row['work'].items():
            if type(value) is int:
                totals[key] = totals.get(key, 0) + value
    return {'hosts': hosts, 'totals': totals}


def before_rpc():
    began = time.perf_counter_ns()
    state = {'before': host_work(), 'python_calls': {}, 'C_calls': {}, 'C_returns': {},
             'C_exceptions': {}, 'old_profile': sys.getprofile()}
    names = {'capture_scene', 'capture_task_scene', '_capture', '_resident_capture'}

    def profile(frame, event, arg):
        if event == 'call' and frame.f_code.co_name in names:
            if Path(frame.f_code.co_filename).name == 'blender_host.py':
                key = frame.f_code.co_name
                state['python_calls'][key] = state['python_calls'].get(key, 0) + 1
        elif event in ('c_call', 'c_return', 'c_exception'):
            name = getattr(arg, '__name__', None)
            if name in ('to_mesh', 'calc_loop_triangles'):
                table = state[{'c_call': 'C_calls', 'c_return': 'C_returns',
                               'c_exception': 'C_exceptions'}[event]]
                table[name] = table.get(name, 0) + 1

    state['before_probe_elapsed_ns'] = time.perf_counter_ns() - began
    state['profile_started_ns'] = time.perf_counter_ns()
    sys.setprofile(profile)
    return state


def after_rpc(state, namespace):
    sys.setprofile(state.pop('old_profile'))
    profile_ended = time.perf_counter_ns()
    began = time.perf_counter_ns()
    after = host_work()
    keys = set(state['before']['totals']) | set(after['totals'])
    state['after'] = after
    state['native_supplement_work'] = namespace.pop('_qa_native_supplement_work', None)
    state['host_residency_delta'] = {
        key: after['totals'].get(key, 0) - state['before']['totals'].get(key, 0)
        for key in sorted(keys)}
    state['after_probe_elapsed_ns'] = time.perf_counter_ns() - began
    state['profile_scope_ns'] = profile_ended - state.pop('profile_started_ns')
    state['scope'] = ('worker execution including QA profile callbacks; host world_transforms '
                      'counts resident pose preparation, with normalized MeshEntity construction '
                      'reported separately by existing product telemetry')
    return state


def initial_rigid(bpy, workspace, save):
    from mathutils import Matrix

    matrix = Matrix(((0., -1., 0., .125), (1., 0., 0., -.25),
                     (0., 0., 1., .5), (0., 0., 0., 1.)))
    original = [(obj, obj.matrix_world.copy()) for obj in bpy.context.scene.objects]
    before = {obj.name: [list(row) for row in pose] for obj, pose in original}
    for obj, pose in original:
        obj.matrix_world = matrix @ pose
    bpy.context.view_layer.update()
    after = {obj.name: [list(row) for row in obj.matrix_world] for obj, _ in original}
    save(workspace / 'QA_INITIAL_RIGID.json', {
        'matrix_left_multiply': [list(row) for row in matrix], 'before': before, 'after': after,
        'coordinate_readback_tolerance_m': 1e-6,
        'scope': 'owned in-memory startup mapping before the accepted initial fingerprint'})
