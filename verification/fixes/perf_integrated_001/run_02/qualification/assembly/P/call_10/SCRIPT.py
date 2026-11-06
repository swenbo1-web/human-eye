_qa_case = 'assembly'
_qa_state = 'changed'

import json as _qa_json
import os as _qa_os
_qa_namespace_count = globals().get('_qa_namespace_count', 0) + 1
_qa_rows = []
for _qa_obj in sorted(bpy.data.objects, key=lambda item: item.name):
    if _qa_obj.type != 'MESH':
        raise ValueError('Qualification fixture has a non-mesh object')
    _qa_matrix = [[float(value) for value in row] for row in _qa_obj.matrix_world]
    _qa_points = [[float(value) for value in vertex.co] for vertex in _qa_obj.data.vertices]
    _qa_world = [[sum(_qa_matrix[axis][k] * point[k] for k in range(3))
                  + _qa_matrix[axis][3] for axis in range(3)] for point in _qa_points]
    _qa_rows.append(dict(name=_qa_obj.name, vertices_local=_qa_points,
                        matrix_world=_qa_matrix, world_vertices=_qa_world,
                        faces=[list(face.vertices) for face in _qa_obj.data.polygons]))
print(_qa_json.dumps(dict(snapshot=dict(schema='perf-integrated-001-mesh-readback-v1',
    case=_qa_case, state=_qa_state,
    unit_scale_m=float(bpy.context.scene.unit_settings.scale_length), objects=_qa_rows),
    namespace_count=_qa_namespace_count, worker_pid=_qa_os.getpid()), allow_nan=False))
