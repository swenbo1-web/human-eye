import json
_qa_native_supplement_work = dict(to_mesh=0, triangulations=0, world_preparations=0, vertices_mapped=0)
_qa_rows = []
_qa_oracle = []
_qa_graph = bpy.context.evaluated_depsgraph_get()
_qa_scale = float(bpy.context.scene.unit_settings.scale_length)
for _qa_name, _qa_id in [('N16', 'blender:d3f91492188a2ad6163705c33f9c11727e3afee34d473b79735b520165f7bbc5'), ('N28', 'blender:776df02dac3d7ed20707eba5167bd572599bf6276df63d28c016f6f96072bf44')]:
    _qa_object = bpy.data.objects[_qa_name]
    _qa_eval = _qa_object.evaluated_get(_qa_graph)
    _qa_mesh = _qa_eval.to_mesh()
    _qa_native_supplement_work['to_mesh'] += 1
    try:
        _qa_mesh.calc_loop_triangles()
        _qa_native_supplement_work['triangulations'] += 1
        _qa_local = [[float(x) for x in v.co] for v in _qa_mesh.vertices]
        _qa_matrix = [[float(x) for x in row] for row in _qa_eval.matrix_world]
        _qa_world = [[(sum(_qa_matrix[r][c] * p[c] for c in range(3)) + _qa_matrix[r][3]) * _qa_scale
                      for r in range(3)] for p in _qa_local]
        _qa_native_supplement_work['world_preparations'] += 1
        _qa_native_supplement_work['vertices_mapped'] += len(_qa_world)
        _qa_triangles = [[int(x) for x in tri.vertices] for tri in _qa_mesh.loop_triangles]
        _qa_rows.append(dict(object_id=_qa_id, name=_qa_name, vertices_world=_qa_world, triangles=_qa_triangles))
        if False:
            _qa_oracle.append(dict(name=_qa_name, vertices_local=_qa_local, matrix_world=_qa_matrix,
                                   unit_scale_m=_qa_scale, triangles=_qa_triangles,
                                   instance_id=str(getattr(_qa_object, 'session_uid', _qa_object.as_pointer())),
                                   data_users=[o.name for o in bpy.data.objects if o.type == 'MESH' and o.data is _qa_object.data]))
    finally:
        _qa_eval.to_mesh_clear()
if False:
    _qa_native_supplement_work['independent_host_oracle'] = _qa_oracle
print(json.dumps(dict(objects=_qa_rows, contract=dict(
    vertices_world='current_evaluated_vertices_world_metres_in_captured_order',
    triangles='zero_based_triplets_index_vertices_world_in_captured_order')), separators=(',', ':'), allow_nan=False))
