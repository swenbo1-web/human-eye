"""QA native oracle and restoration around exactly one product capture."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback
import types
from types import MappingProxyType

OUT = Path(os.environ['VISUAL004_WORKSPACE'])
STATE_OUT = OUT/('state_'+str(STATE)); STATE_OUT.mkdir(exist_ok=False)


def persist(name, value):
    (STATE_OUT/name).write_bytes((json.dumps(value, indent=2, allow_nan=False)+'\n').encode())


def journal(stage, **details):
    with (STATE_OUT/'JOURNAL.jsonl').open('ab') as stream:
        stream.write((json.dumps(dict(stage=stage, at_ns=time.perf_counter_ns(), **details), allow_nan=False)+'\n').encode())
        stream.flush(); os.fsync(stream.fileno())


def error_info(error):
    return dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())


def oracle():
    graph = bpy.context.evaluated_depsgraph_get(); scale = float(bpy.context.scene.unit_settings.scale_length)
    rows = []
    for obj in sorted(bpy.context.scene.objects, key=lambda o:o.name):
        if obj.type != 'MESH': continue
        evaluated = obj.evaluated_get(graph); data = evaluated.data
        coordinates = [[float(v) for v in point.co] for point in data.vertices]
        matrix = [[float(v) for v in row] for row in evaluated.matrix_world]
        world = [[(sum(matrix[r][c]*point[c] for c in range(3))+matrix[r][3])*scale for r in range(3)] for point in coordinates]
        rows.append(dict(name=obj.name, object_id=host.object_id(obj), coordinates_local=coordinates,
            coordinates_world_m=world, polygons=[list(face.vertices) for face in data.polygons],
            loop_vertex_indices=[int(loop.vertex_index) for loop in data.loops], matrix_world=matrix,
            evaluated=bool(evaluated.is_evaluated), bound_box_local=[[float(v) for v in p] for p in evaluated.bound_box]))
    return dict(frame=bpy.context.scene.frame_current, scale_length=scale, rows=rows,
                qa_only_full_native_scan=True, native_vertices_read=sum(len(r['coordinates_local']) for r in rows))


def geometry_only(value):
    return dict(frame=value['frame'], scale=value['scale_length'], rows=[
        {k:r[k] for k in ('name','object_id','coordinates_local','coordinates_world_m','polygons','loop_vertex_indices','matrix_world')}
        for r in value['rows']])


record = dict(state=STATE, mutation=None, capture_called=False, capture=None, primary_error=None,
              restored=False, source_sha256=PLAN['source_sha256'], qa_native_oracle_calls=0)
mesh = None; original_coordinates = original_indices = None
try:
    journal('entered')
    root = Path(PLAN['source_root']); manifest = PLAN['product_manifest']
    blobs = MappingProxyType({r['path']:(root/r['path']).read_bytes() for r in manifest})
    assert {p:hashlib.sha256(b).hexdigest() for p,b in blobs.items()} == {r['path']:r['sha256'] for r in manifest}
    loader_path = root/'human_eye_plugin/verified_source_loader.py'
    guard = next((g for g in sys.meta_path if getattr(g,'protocol',None)=='human-eye-verified-source-v1' and g.root==root), None)
    if guard is None:
        loader = types.ModuleType('_nearest_worker_loader'); loader.__file__ = str(loader_path)
        sys.modules[loader.__name__] = loader
        exec(compile(blobs['human_eye_plugin/verified_source_loader.py'], str(loader_path), 'exec', dont_inherit=True), loader.__dict__)
        guard = loader.install(root, manifest, sources=blobs, bootstrap_module=loader)
    assert dict(guard.sources) == dict(blobs) and guard.verify_loaded()
    host_path = root/'human_eye_plugin/blender_host.py'
    module = types.ModuleType('_nearest_host_'+str(STATE)); module.__file__ = str(host_path)
    sys.modules[module.__name__] = module
    guard.exec_path(module, host_path, expected_blob=blobs['human_eye_plugin/blender_host.py'])
    module._READONLY_LOADED_HOST_SHA256 = PLAN['host_sha256']
    host = module.BlenderSceneHost(bpy_module=bpy, execution_metadata=True, identity_metadata=True)
    record['host_execution'] = dict(source_sha256=PLAN['host_sha256'], bytes=len(blobs['human_eye_plugin/blender_host.py']),
                                  code_filename=module.BlenderSceneHost.capture_nearest_candidates.__code__.co_filename,
                                  guard_verified=guard.verify_loaded())
    assert bpy.app.version_string == '5.2.1 LTS'
    if STATE == 1:
        record['build'] = {n:(getattr(bpy.app,n,None).decode('ascii','replace') if isinstance(getattr(bpy.app,n,None),bytes) else getattr(bpy.app,n,None))
            for n in ('version_string','build_hash','build_branch','build_date','build_time','binary_path')}
    mesh = bpy.data.objects['M4_Far_00'].data
    original_coordinates = [tuple(float(v) for v in vertex.co) for vertex in mesh.vertices]
    original_indices = [int(loop.vertex_index) for loop in mesh.loops]
    expected_far = next(o for o in PLAN['asset_recipe']['objects'] if o['name']=='M4_Far_00')
    assert [list(p) for p in original_coordinates] == expected_far['vertices']
    assert [list(p.vertices) for p in mesh.polygons] == expected_far['faces']
    bpy.context.view_layer.update()
    record['before_mutation'] = oracle(); record['qa_native_oracle_calls'] += 1
    if STATE == 2:
        mesh.vertices[3].co = (.25,.25,.25)
        record['mutation'] = dict(vertex=3, coordinates=list(mesh.vertices[3].co))
    elif STATE == 3:
        for index in (3,4,5): mesh.vertices[index].co.x = 1.
        record['mutation'] = dict(vertices=[3,4,5], coordinates=[list(mesh.vertices[i].co) for i in (3,4,5)])
    elif STATE != 1:
        raise AssertionError('unregistered_state')
    if STATE != 1:
        mesh.update(); bpy.context.view_layer.update()
        record['oracle_before_capture'] = oracle(); record['qa_native_oracle_calls'] += 1
    else:
        record['oracle_before_capture'] = record['before_mutation']
    persist('ORACLE_BEFORE.json', record['oracle_before_capture'])
    journal('before_capture'); record['capture_called'] = True
    try:
        packet = host.capture_nearest_candidates(host.object_id(bpy.data.objects['M4_Focal']), PLAN['deadline_ns'], 8*1024*1024)
        persist('CAPTURE.json', packet)
        record['capture'] = dict(status='returned', capture_scope=packet['capture']['capture_scope'], work=packet['work'])
    except BaseException as error:
        record['capture'] = dict(status='refused', error=error_info(error))
    journal('capture_completed', status=record['capture']['status'])
    record['oracle_after_capture'] = oracle(); record['qa_native_oracle_calls'] += 1
    persist('ORACLE_AFTER.json', record['oracle_after_capture'])
    record['same_native_geometry_before_after_capture'] = geometry_only(record['oracle_before_capture']) == geometry_only(record['oracle_after_capture'])
    record['host_execution']['final_guard_verified'] = guard.verify_loaded()
except BaseException as error:
    record['primary_error'] = error_info(error); journal('script_exception', error=record['primary_error'])
finally:
    try:
        if mesh is not None and original_coordinates is not None:
            for vertex, coordinate in zip(mesh.vertices, original_coordinates): vertex.co = coordinate
            mesh.update(); bpy.context.view_layer.update()
            record['restored'] = ([tuple(float(v) for v in vertex.co) for vertex in mesh.vertices] == original_coordinates
                                  and [int(loop.vertex_index) for loop in mesh.loops] == original_indices)
        journal('restore_completed', restored=record['restored'])
    except BaseException as error:
        record['restore_error'] = error_info(error)
    persist('STATE_RESULT.json', record)
    print('NEAREST_INTEGRATION_STATE:'+json.dumps(record, allow_nan=False, separators=(',',':')))
