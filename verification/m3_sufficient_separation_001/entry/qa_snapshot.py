"""One read-only actual evaluated snapshot, executed only in the owned worker."""
import hashlib
import json
import sys

_qa_scene = bpy.context.scene
_qa_graph = bpy.context.evaluated_depsgraph_get()
_qa_scale = float(_qa_scene.unit_settings.scale_length)
_qa_rows = []
_qa_work = {'to_mesh': 0, 'triangulations': 0, 'world_transforms': 0,
            'vertices_read': 0, 'triangle_rows_read': 0}
for _qa_obj in sorted((item for item in _qa_scene.objects if item.type=='MESH'),key=lambda item:item.name):
    _qa_evaluated = _qa_obj.evaluated_get(_qa_graph)
    if not _qa_evaluated.is_evaluated:
        raise ValueError('qualification_snapshot_evaluation_unavailable')
    _qa_temporary = None
    try:
        _qa_temporary = _qa_evaluated.to_mesh()
        _qa_work['to_mesh'] += 1
        if _qa_temporary is None:
            raise ValueError('qualification_snapshot_mesh_unavailable')
        _qa_temporary.calc_loop_triangles()
        _qa_work['triangulations'] += 1
        _qa_local = [[float(vertex.co[axis]) for axis in range(3)] for vertex in _qa_temporary.vertices]
        _qa_matrix = [[float(value) for value in row] for row in _qa_evaluated.matrix_world]
        _qa_world = [[(sum(_qa_matrix[axis][column]*point[column] for column in range(3))
                      +_qa_matrix[axis][3])*_qa_scale for axis in range(3)] for point in _qa_local]
        _qa_triangles = [[int(index) for index in face.vertices] for face in _qa_temporary.loop_triangles]
        _qa_library = str(getattr(getattr(_qa_obj,'library',None),'filepath',''))
        _qa_id_raw = json.dumps([_qa_library,str(_qa_obj.name_full)],sort_keys=True,
                               separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
        _qa_rows.append({'logical_id':_qa_obj.get('scale_logical_id'),'name':_qa_obj.name,
            'name_full':_qa_obj.name_full,'library_path':_qa_library,
            'object_id':'blender:'+hashlib.sha256(_qa_id_raw).hexdigest(),
            'vertices_local':_qa_local,'vertices_world':_qa_world,'matrix_world':_qa_matrix,
            'triangles':_qa_triangles,'source_polygon_count':len(_qa_temporary.polygons)})
        _qa_work['world_transforms'] += 1
        _qa_work['vertices_read'] += len(_qa_local)
        _qa_work['triangle_rows_read'] += len(_qa_triangles)
    finally:
        if _qa_temporary is not None:
            _qa_evaluated.to_mesh_clear()
_m2_native_last_work = _qa_work
print(json.dumps({'schema':'spatial-task-qualification-actual-evaluated-v1','unit':'m',
    'coordinate_frame':'world','frame':int(_qa_scene.frame_current),
    'subframe':float(_qa_scene.frame_subframe),'scale_length':_qa_scale,
    'Blender':bpy.app.version_string,'Python':sys.version,'objects':_qa_rows},
    ensure_ascii=False,separators=(',',':'),allow_nan=False))
