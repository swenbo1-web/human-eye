OUTPUT_PATH='D:\\he_m4_real_asset_region_001\\sessions\\state\\SOURCE_restored.json'
STATE='restored'
OWNED_ROOT='D:\\he_m4_real_asset_region_001\\sessions\\state'
"""Executed inside the existing owned Blender, with OUTPUT_PATH and STATE set."""

import hashlib as export_hashlib
import json as export_json
import os as export_os
from pathlib import Path as ExportPath
import time as export_time

export_started = export_time.perf_counter_ns()
export_dg = bpy.context.evaluated_depsgraph_get()


def export_mesh(mesh, matrix):
    mesh.calc_loop_triangles()
    return {
        'vertices': [list(vertex.co) for vertex in mesh.vertices],
        'vertices_world_m': [[float(value) * bpy.context.scene.unit_settings.scale_length
                              for value in matrix @ vertex.co] for vertex in mesh.vertices],
        'polygons': [list(face.vertices) for face in mesh.polygons],
        'triangles': [list(face.vertices) for face in mesh.loop_triangles],
        'triangle_polygons': [face.polygon_index for face in mesh.loop_triangles],
    }


export_objects = []
export_inventory = []
for export_obj in bpy.data.objects:
    export_inventory.append({'name': export_obj.name, 'type': export_obj.type})
    if export_obj.type != 'MESH':
        continue
    export_item = {
        'name': export_obj.name, 'instance_id': str(export_obj.session_uid),
        'instance_id_kind': 'Blender_session_uid', 'mesh_name': export_obj.data.name,
        'matrix_world': [list(row) for row in export_obj.matrix_world],
        'parent': None if export_obj.parent is None else export_obj.parent.name,
        'display': {'hide_render': export_obj.hide_render, 'hide_viewport': export_obj.hide_viewport,
                    'hide_get': export_obj.hide_get(), 'visible_get': export_obj.visible_get(),
                    'display_type': export_obj.display_type},
        'modifiers': [{'name': modifier.name, 'type': modifier.type} for modifier in export_obj.modifiers],
        'animation': None if export_obj.animation_data is None else {
            'action': None if export_obj.animation_data.action is None else export_obj.animation_data.action.name,
            'nla_tracks': len(export_obj.animation_data.nla_tracks), 'drivers': len(export_obj.animation_data.drivers)},
    }
    export_native_mesh = export_obj.to_mesh()
    try:
        export_item['native'] = export_mesh(export_native_mesh, export_obj.matrix_world)
    finally:
        export_obj.to_mesh_clear()
    export_evaluated = export_obj.evaluated_get(export_dg)
    export_eval_mesh = export_evaluated.to_mesh()
    try:
        export_item['evaluated'] = export_mesh(export_eval_mesh, export_evaluated.matrix_world)
    finally:
        export_evaluated.to_mesh_clear()
    export_objects.append(export_item)

export_scene = bpy.context.scene
export_value = {
    'schema': 'real-asset-source-v1', 'state': STATE,
    'source_sha256': '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d',
    'process_id': export_os.getpid(), 'frame': export_scene.frame_current,
    'subframe': export_scene.frame_subframe, 'unit_scale': export_scene.unit_settings.scale_length,
    'unit_settings': {'system': export_scene.unit_settings.system,
                      'scale_length': export_scene.unit_settings.scale_length,
                      'length_unit': export_scene.unit_settings.length_unit},
    'objects': export_objects, 'objects_inventory': export_inventory,
    'started_ns': export_started, 'read_complete_ns': export_time.perf_counter_ns(),
    'source_writes': 0, 'saved_blend': False,
}
export_path = ExportPath(OUTPUT_PATH)
export_path.resolve().relative_to(ExportPath(OWNED_ROOT).resolve())
export_raw = export_json.dumps(export_value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')
with export_path.open('xb') as export_stream:
    export_stream.write(export_raw)
    export_stream.flush()
    export_os.fsync(export_stream.fileno())
assert export_path.read_bytes() == export_raw
print('REAL_ASSET_EXPORT:' + export_json.dumps({'path': str(export_path), 'bytes': len(export_raw),
      'sha256': export_hashlib.sha256(export_raw).hexdigest(), 'process_id': export_os.getpid(), 'state': STATE}))
