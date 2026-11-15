
import json as _raw_json
import hashlib as _raw_hashlib
import os as _raw_os
import uuid as _raw_uuid
_raw_names = _raw_json.loads('["M4_Far_00"]' )
if '_raw_document_instance' not in globals():
    _raw_document_instance = _raw_uuid.uuid4().hex
_raw_dg = bpy.context.evaluated_depsgraph_get()
_raw_scale = float(bpy.context.scene.unit_settings.scale_length)
_raw_objects = []
for _raw_obj in bpy.data.objects:
    if _raw_obj.type != 'MESH' or (_raw_names is not None and _raw_obj.name not in _raw_names):
        continue
    _raw_id = 'blender:' + _raw_hashlib.sha256(_raw_json.dumps(['',_raw_obj.name],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    _raw_eval = _raw_obj.evaluated_get(_raw_dg)
    _raw_mesh = _raw_eval.to_mesh()
    try:
        _raw_mesh.calc_loop_triangles()
        _raw_vertices = [[float(value)*_raw_scale for value in (_raw_eval.matrix_world @ vertex.co)] for vertex in _raw_mesh.vertices]
        _raw_faces = [list(triangle.vertices) for triangle in _raw_mesh.loop_triangles]
        _raw_objects.append({'name':_raw_obj.name,'object_id':_raw_id,'instance_id':str(_raw_obj.session_uid),
            'vertices':_raw_vertices,'triangles':_raw_faces})
    finally:
        _raw_eval.to_mesh_clear()
_raw_packet = {'objects':sorted(_raw_objects,key=lambda row:row['object_id']),
    'source':{'kind':'actual_owned_Blender_evaluated_mesh','instance_id':_raw_document_instance,
        'pid':_raw_os.getpid(),'frame':bpy.context.scene.frame_current,
        'subframe':bpy.context.scene.frame_subframe,'scale_length':_raw_scale}}
print('CURRENT_RAW_SCENE:' + _raw_json.dumps(_raw_packet,separators=(',',':'),allow_nan=False))
