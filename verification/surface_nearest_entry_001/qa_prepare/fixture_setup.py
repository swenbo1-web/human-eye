"""Private QA fixture hook; run once before one original production capture.

STATE and PLAN are prefixed by the frozen controller. No product method changes.
"""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

assert STATE in (1, 2, 3)
assert sys.getprofile() is None, 'existing_profile_not_replaced'
assert globals().get('_surface_entry_fixture') is None, 'previous_fixture_not_disarmed'
_qa_mesh = bpy.data.objects['M4_Far_00'].data
_qa_original = [tuple(float(v) for v in point.co) for point in _qa_mesh.vertices]
_qa_expected = next(o for o in PLAN['asset_recipe']['objects'] if o['name'] == 'M4_Far_00')
assert [list(p) for p in _qa_original] == _qa_expected['vertices']
assert [list(p.vertices) for p in _qa_mesh.polygons] == _qa_expected['faces']
_qa_host_path = str(Path(PLAN['source_root'])/'human_eye_plugin/blender_host.py')
assert hashlib.sha256(Path(_qa_host_path).read_bytes()).hexdigest() == PLAN['host_sha256']
_qa_folder = Path(PLAN['native_workspace'])/('fixture_'+str(STATE))
_qa_folder.mkdir(exist_ok=False)
_surface_entry_fixture = dict(state=STATE, calls=0, returns=0, restored=False,
    target_file=_qa_host_path, target_name='capture_nearest_candidates',
    profile_overhead_ns=0, qa_oracle_scans=0, qa_vertices_read=0, events=[])

def _qa_snapshot():
    # QA truth only. These evaluated coordinates are never sent to the service.
    graph = bpy.context.evaluated_depsgraph_get()
    rows = []
    scale = float(bpy.context.scene.unit_settings.scale_length)
    for obj in sorted(bpy.context.scene.objects, key=lambda o:o.name):
        if obj.type != 'MESH': continue
        evaluated = obj.evaluated_get(graph)
        rows.append(dict(name=obj.name, vertices_local=[list(v.co) for v in evaluated.data.vertices],
            matrix_world=[list(r) for r in evaluated.matrix_world],
            vertices_world_m=[list((evaluated.matrix_world @ v.co)*scale) for v in evaluated.data.vertices],
            faces=[list(p.vertices) for p in evaluated.data.polygons]))
    _surface_entry_fixture['qa_oracle_scans'] += 1
    _surface_entry_fixture['qa_vertices_read'] += sum(len(r['vertices_local']) for r in rows)
    return rows

def _qa_restore_geometry():
    for point, coordinate in zip(_qa_mesh.vertices, _qa_original): point.co = coordinate
    _qa_mesh.update(); bpy.context.view_layer.update()
    _surface_entry_fixture['restored'] = [tuple(float(v) for v in p.co) for p in _qa_mesh.vertices] == _qa_original
    if not _surface_entry_fixture['restored']: raise AssertionError('private_fixture_restore_failed')

def _qa_persist():
    (_qa_folder/'FIXTURE.json').write_bytes((json.dumps(_surface_entry_fixture, indent=2, allow_nan=False)+'\n').encode())

def _qa_profile(frame, event, arg):
    if event not in ('call', 'return'): return
    if frame.f_code.co_name != 'capture_nearest_candidates' or frame.f_code.co_filename != _qa_host_path: return
    started = time.perf_counter_ns()
    try:
        if event == 'call':
            assert _surface_entry_fixture['calls'] == 0, 'one_shot_capture_only'
            assert frame.f_globals.get('_READONLY_LOADED_HOST_SHA256') == PLAN['host_sha256'], 'original_connector_loaded_host_required'
            _surface_entry_fixture['calls'] += 1
            _surface_entry_fixture['before'] = _qa_snapshot()
            if STATE == 2: _qa_mesh.vertices[3].co = (.25, .25, .25)
            elif STATE == 3:
                for index in (3, 4, 5): _qa_mesh.vertices[index].co.x = 1.
            _qa_mesh.update(); bpy.context.view_layer.update()
            _surface_entry_fixture['during'] = _qa_snapshot()
            _surface_entry_fixture['events'].append(dict(event=event, at_ns=started,
                filename=frame.f_code.co_filename, source_sha256=PLAN['host_sha256']))
        elif event == 'return':
            # CPython emits return(arg=None) when an exception unwinds a frame.
            _surface_entry_fixture['returns'] += 1
            _surface_entry_fixture['events'].append(dict(event=event, at_ns=started,
                returned_packet=isinstance(arg, dict), filename=frame.f_code.co_filename))
            _qa_restore_geometry()
            _surface_entry_fixture['after'] = _qa_snapshot()
            sys.setprofile(None)
    except BaseException as error:
        _surface_entry_fixture['hook_error'] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
        try: _qa_restore_geometry()
        finally: sys.setprofile(None)
        raise
    finally:
        _surface_entry_fixture['profile_overhead_ns'] += time.perf_counter_ns()-started
        _qa_persist()

_surface_entry_fixture['setup_complete'] = True
_qa_persist()
sys.setprofile(_qa_profile)
print('SURFACE_ENTRY_SETUP:'+json.dumps(dict(state=STATE, armed=True, original_geometry_unchanged=True), separators=(',',':')))
