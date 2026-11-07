"""QA-only normal RNA mutations, full native oracle, and one product capture."""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback
import types

OUT = Path(os.environ['VISUAL004_WORKSPACE'])
STATE_OUT = OUT / ('state_' + str(STATE))
STATE_OUT.mkdir(exist_ok=False)


def safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {'nonfinite': 'nan' if math.isnan(value) else '+inf' if value > 0 else '-inf'}
    if isinstance(value, dict):
        return {str(key): safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(item) for item in value]
    if isinstance(value, bytes):
        return value.decode('ascii', 'replace')
    return value


def persist(name, value):
    blob = (json.dumps(safe(value), indent=2, allow_nan=False) + '\n').encode()
    (STATE_OUT / name).write_bytes(blob)


def journal(stage, **details):
    with (STATE_OUT / 'JOURNAL.jsonl').open('ab') as stream:
        stream.write((json.dumps(safe(dict(stage=stage, at_ns=time.perf_counter_ns(), **details)), allow_nan=False) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())


def error_info(error):
    return {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}


def oracle():
    graph = bpy.context.evaluated_depsgraph_get()
    scale = float(bpy.context.scene.unit_settings.scale_length)
    rows = []
    for obj in sorted(bpy.context.scene.objects, key=lambda item: item.name):
        if obj.type != 'MESH':
            continue
        evaluated = obj.evaluated_get(graph)
        data = evaluated.data
        coords = [[float(value) for value in vertex.co] for vertex in data.vertices]
        polygons = [list(face.vertices) for face in data.polygons]
        loops = [int(loop.vertex_index) for loop in data.loops]
        matrix = [[float(value) for value in row] for row in evaluated.matrix_world]
        world = [[(sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3]) * scale for r in range(3)] for point in coords]
        invalid = [{'face': fi, 'corner': ci, 'index': index} for fi, face in enumerate(polygons)
                   for ci, index in enumerate(face) if not 0 <= index < len(coords)]
        referenced = sorted({index for face in polygons for index in face if 0 <= index < len(coords)})
        nonfinite = [index for index in referenced if any(not math.isfinite(v) for v in coords[index])]
        finite_world = all(math.isfinite(v) for point in world for v in point)
        fresh = [[min(point[k] for point in world) for k in range(3)],
                 [max(point[k] for point in world) for k in range(3)]] if finite_world else None
        bbox = [[float(value) for value in corner] for corner in evaluated.bound_box]
        local_finite = all(math.isfinite(v) for point in coords for v in point)
        enclosed = (all(min(c[k] for c in bbox) <= point[k] <= max(c[k] for c in bbox) for point in coords for k in range(3))
                    if local_finite and all(math.isfinite(v) for corner in bbox for v in corner) else None)
        rows.append(dict(name=obj.name, object_id=host.object_id(obj), evaluated=bool(evaluated.is_evaluated),
                         evaluated_object_pointer=evaluated.as_pointer(), evaluated_data_pointer=data.as_pointer(),
                         vertex_count=len(coords), polygon_count=len(polygons), loop_count=len(loops),
                         coordinates_local=coords, coordinates_world_m=world, polygons=polygons, loop_vertex_indices=loops,
                         matrix_world=matrix, bound_box_local=bbox, fresh_world_minmax=fresh,
                         all_local_vertices_finite=local_finite, referenced_nonfinite_indices=nonfinite,
                         invalid_face_indices=invalid, all_vertices_enclosed_by_api_box=enclosed))
    return dict(graph_pointer=graph.as_pointer(), frame=bpy.context.scene.frame_current, scale_length=scale,
                rows=rows, qa_only_full_native_scan=True)


record = dict(state=STATE, mutation=None, capture_called=False, capture=None, primary_error=None,
              restored=False, source_sha256=PLAN['source_sha256'])
mesh = None
original_coords = original_indices = None
try:
    journal('entered')
    root = Path(PLAN['root'])
    loader_path = root / 'human_eye_plugin/verified_source_loader.py'
    loader_blob = loader_path.read_bytes()
    expected = next(row['sha256'] for row in PLAN['product_manifest'] if row['path'] == 'human_eye_plugin/verified_source_loader.py')
    assert hashlib.sha256(loader_blob).hexdigest() == expected
    guard = next((finder for finder in sys.meta_path if getattr(finder, 'protocol', None) == 'human-eye-verified-source-v1' and finder.root == root), None)
    if guard is None:
        loader = types.ModuleType('_bound_qa_loader')
        loader.__file__ = str(loader_path)
        sys.modules[loader.__name__] = loader
        exec(compile(loader_blob, str(loader_path), 'exec', dont_inherit=True), loader.__dict__)
        guard = loader.install(root, PLAN['product_manifest'], bootstrap_module=loader)
    guard.verify_loaded()
    host_path = root / 'human_eye_plugin/blender_host.py'
    host_blob = host_path.read_bytes()
    assert hashlib.sha256(host_blob).hexdigest() == PLAN['host_sha256']
    module = types.ModuleType('_bound_qa_host_' + str(STATE))
    module.__file__ = str(host_path)
    sys.modules[module.__name__] = module
    guard.exec_path(module, host_path, expected_blob=host_blob)
    module._READONLY_LOADED_HOST_SHA256 = PLAN['host_sha256']
    host = module.BlenderSceneHost(bpy_module=bpy, execution_metadata=True, identity_metadata=True)
    record['source_bytes_compiled'] = {'host_sha256': hashlib.sha256(host_blob).hexdigest(), 'host_bytes': len(host_blob),
                                       'guard_verified': guard.verify_loaded()}
    assert bpy.app.version_string == '5.2.1 LTS'
    if STATE == 1:
        record['build'] = {name: safe(getattr(bpy.app, name, None)) for name in
                           ('version', 'version_string', 'build_hash', 'build_branch', 'build_date', 'build_time',
                            'build_type', 'build_commit_date', 'build_commit_time', 'binary_path')}
    obj = bpy.data.objects['M4_Far_00']
    mesh = obj.data
    assert len(mesh.vertices) == 6 and len(mesh.polygons) == 2 and len(mesh.loops) == 6
    assert list(mesh.polygons[0].vertices) == [0, 1, 2] and list(mesh.polygons[1].vertices) == [3, 4, 5]
    original_coords = [tuple(float(x) for x in vertex.co) for vertex in mesh.vertices]
    original_indices = [int(loop.vertex_index) for loop in mesh.loops]
    bpy.context.view_layer.update()
    record['before_mutation'] = oracle()
    rejected = False
    if STATE != 1:
        journal('before_setter')
        try:
            if STATE == 2:
                mesh.vertices[3].co = (0.25, 0.25, 0.25)
                value = tuple(mesh.vertices[3].co)
            elif STATE == 3:
                mesh.vertices[3].co.x = float('nan')
                value = tuple(mesh.vertices[3].co)
            elif STATE in (4, 5):
                mesh.loops[3].vertex_index = len(mesh.vertices) + 7
                value = int(mesh.loops[3].vertex_index)
            else:
                raise AssertionError('unregistered_state')
            record['mutation'] = dict(setter_returned=True, immediate_readback=safe(value))
            journal('setter_returned', mutation=record['mutation'])
            mesh.update()
            bpy.context.view_layer.update()
            journal('canonical_update_returned')
        except Exception as error:
            rejected = True
            record['mutation'] = dict(setter_or_update_rejected=True, error=error_info(error))
            journal('mutation_rejected', mutation=record['mutation'])
    if not rejected:
        record['oracle_before_capture'] = oracle()
        persist('ORACLE_BEFORE.json', record['oracle_before_capture'])
        journal('before_capture')
        record['capture_called'] = True
        try:
            record['capture_focal_name'] = 'M4_Far_00' if STATE == 5 else 'M4_Focal'
            packet = host.capture_nearest_candidates(host.object_id(bpy.data.objects[record['capture_focal_name']]),
                                                      PLAN['deadline_ns'], 8 * 1024 * 1024)
            persist('CAPTURE.json', packet)
            record['capture'] = dict(status='returned', packet=packet)
        except Exception as error:
            record['capture'] = dict(status='refused', error=error_info(error))
        journal('capture_completed', status=record['capture']['status'])
        record['oracle_after_capture'] = oracle()
        persist('ORACLE_AFTER.json', record['oracle_after_capture'])
        record['same_native_state_before_after_capture'] = safe(record['oracle_before_capture']) == safe(record['oracle_after_capture'])
    else:
        record['capture'] = dict(status='not_run_api_rejected')
except BaseException as error:
    record['primary_error'] = error_info(error)
    journal('script_exception', error=record['primary_error'])
finally:
    try:
        if mesh is not None and original_coords is not None and original_indices is not None:
            for loop, index in zip(mesh.loops, original_indices):
                loop.vertex_index = index
            for vertex, coord in zip(mesh.vertices, original_coords):
                vertex.co = coord
            mesh.update()
            bpy.context.view_layer.update()
            record['restored'] = ([tuple(float(x) for x in v.co) for v in mesh.vertices] == original_coords
                                  and [int(loop.vertex_index) for loop in mesh.loops] == original_indices)
        journal('restore_completed', restored=record['restored'])
    except BaseException as error:
        record['restore_error'] = error_info(error)
    persist('STATE_RESULT.json', record)
    print('BOUND_SOURCE_FIX_RESULT:' + json.dumps(safe(record), allow_nan=False, separators=(',', ':')))
