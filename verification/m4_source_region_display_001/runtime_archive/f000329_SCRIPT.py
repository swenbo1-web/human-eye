OUTPUT_PATH='D:\\he_m4_source_region_display_001\\sessions\\state\\SOURCE_target_restored.json'
STATE='target_restored'
OWNED_ROOT='D:\\he_m4_source_region_display_001\\sessions\\state'
"""Executed inside the existing owned Blender, with OUTPUT_PATH and STATE set."""

import hashlib as export_hashlib
import json as export_json
import os as export_os
from pathlib import Path as ExportPath
import time as export_time

export_started = export_time.perf_counter_ns()
export_view_layer = bpy.context.view_layer


def export_layer_collection(layer):
    return {
        'name': layer.name, 'collection_name': layer.collection.name,
        'exclude': layer.exclude, 'hide_viewport': layer.hide_viewport,
        'holdout': layer.holdout, 'indirect_only': layer.indirect_only,
        'children': [export_layer_collection(child) for child in layer.children],
    }


export_display_started = export_time.perf_counter_ns()
export_display_objects = {}
for export_obj in sorted(bpy.data.objects, key=lambda obj: obj.name):
    export_host_id = 'blender:' + export_hashlib.sha256(export_json.dumps(
        ['', export_obj.name], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    export_display_objects[export_obj.name] = {
        'name': export_obj.name, 'type': export_obj.type, 'host_id': export_host_id,
        'instance_id': str(export_obj.session_uid),
        'hide_get': export_obj.hide_get(view_layer=export_view_layer),
        'visible_get': export_obj.visible_get(view_layer=export_view_layer),
        'hide_render': export_obj.hide_render, 'hide_viewport': export_obj.hide_viewport,
        'hide_select': export_obj.hide_select, 'display_type': export_obj.display_type,
        'show_in_front': export_obj.show_in_front,
        'show_instancer_for_viewport': export_obj.show_instancer_for_viewport,
        'show_instancer_for_render': export_obj.show_instancer_for_render,
        'collections': sorted(collection.name for collection in export_obj.users_collection),
    }
export_display = {
    'source': 'current_owned_Blender_Object.visible_get(view_layer=current)',
    'scope': 'active_view_layer_effective_viewport',
    'view_layer': {'name': export_view_layer.name, 'scene_name': bpy.context.scene.name,
                   'instance_id': 'rna:' + str(int(export_view_layer.as_pointer()))},
    'viewport': None,
    'layer_collections': export_layer_collection(export_view_layer.layer_collection),
    'collections': [
        {'name': collection.name, 'hide_viewport': collection.hide_viewport,
         'hide_render': collection.hide_render, 'hide_select': collection.hide_select}
        for collection in sorted(bpy.data.collections, key=lambda item: item.name)],
    'objects': list(export_display_objects.values()),
}
export_display_digest = export_hashlib.sha256(export_json.dumps(
    export_display, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
export_display_complete = export_time.perf_counter_ns()
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
    export_inventory.append(export_display_objects[export_obj.name])
    if export_obj.type != 'MESH':
        continue
    export_item = {
        'name': export_obj.name, 'host_id': export_display_objects[export_obj.name]['host_id'],
        'instance_id': str(export_obj.session_uid),
        'instance_id_kind': 'Blender_session_uid', 'mesh_name': export_obj.data.name,
        'matrix_world': [list(row) for row in export_obj.matrix_world],
        'parent': None if export_obj.parent is None else export_obj.parent.name,
        'display': export_display_objects[export_obj.name],
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
    'display_snapshot': export_display, 'display_snapshot_sha256': export_display_digest,
    'display_read_started_ns': export_display_started, 'display_read_complete_ns': export_display_complete,
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
