"""Read-only complete geometry export, executed by the existing private QA worker."""

import bpy
import json
import os


objects = []
for obj in sorted(bpy.context.scene.objects, key=lambda value: value.name):
    assert obj.type == 'MESH'
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.data
    local = [[float(value) for value in vertex.co] for vertex in mesh.vertices]
    matrix = [[float(value) for value in row] for row in obj.matrix_world]
    world = [[((matrix[row][0] * vertex[0] + matrix[row][1] * vertex[1])
               + matrix[row][2] * vertex[2]) + matrix[row][3] for row in range(3)]
             for vertex in local]
    triangles = [list(polygon.vertices) for polygon in mesh.polygons]
    assert all(len(face) == 3 for face in triangles)
    edge_uses = {}
    for face_index, face in enumerate(triangles):
        for left, right in zip(face, face[1:] + face[:1]):
            edge_uses.setdefault(tuple(sorted((left, right))), []).append([face_index, left, right])
    objects.append({
        'name': obj.name, 'type': obj.type, 'mesh_name': mesh.name,
        'vertices_local': local, 'vertices_world': world, 'matrix_world': matrix,
        'evaluated_bound_box_local': [list(point) for point in evaluated.bound_box],
        'matrix_local': [list(row) for row in obj.matrix_local],
        'matrix_basis': [list(row) for row in obj.matrix_basis],
        'location': list(obj.location), 'rotation_mode': obj.rotation_mode,
        'rotation_quaternion': list(obj.rotation_quaternion), 'scale': list(obj.scale),
        'triangles': triangles, 'faces': triangles,
        'polygons': [{'index': p.index, 'vertices': list(p.vertices), 'loop_start': p.loop_start,
                      'loop_total': p.loop_total, 'material_index': p.material_index,
                      'use_smooth': p.use_smooth, 'normal_local': list(p.normal),
                      'area_local_mm2': float(p.area)} for p in mesh.polygons],
        'edges': [{'index': edge.index, 'vertices': list(edge.vertices)} for edge in mesh.edges],
        'topology': {'vertex_count': len(local), 'polygon_count': len(triangles),
                     'triangle_count': len(triangles), 'edge_count': len(mesh.edges),
                     'edge_incidence': [{'vertices': list(edge), 'uses': uses}
                                        for edge, uses in sorted(edge_uses.items())],
                     'boundary_edge_count': sum(len(uses) == 1 for uses in edge_uses.values()),
                     'nonmanifold_edge_count': sum(len(uses) != 2 for uses in edge_uses.values())},
        'parent': None if obj.parent is None else obj.parent.name,
        'modifiers': [{'name': m.name, 'type': m.type} for m in obj.modifiers],
        'constraints': [{'name': c.name, 'type': c.type} for c in obj.constraints],
        'animation_present': obj.animation_data is not None or mesh.animation_data is not None,
        'shape_keys_present': mesh.shape_keys is not None,
        'object_custom_properties': list(obj.keys()), 'mesh_custom_properties': list(mesh.keys()),
        'material_names': [m.name for m in mesh.materials],
        'mesh_attributes': [{'name': a.name, 'data_type': a.data_type, 'domain': a.domain} for a in mesh.attributes],
        'hidden_render': obj.hide_render, 'hidden_viewport': obj.hide_viewport,
    })
snapshot = {
    'schema': 'm4-surface-scan-actual-snapshot-v1', 'pid': os.getpid(),
    'blend_filepath': bpy.data.filepath, 'blender_version': bpy.app.version_string,
    'unit': 'm', 'coordinate_frame': 'world', 'local_coordinate_unit': 'm',
    'scale_length': float(bpy.context.scene.unit_settings.scale_length),
    'unit_scale_m': float(bpy.context.scene.unit_settings.scale_length),
    'unit_system': bpy.context.scene.unit_settings.system,
    'unit_length': bpy.context.scene.unit_settings.length_unit,
    'frame_current': bpy.context.scene.frame_current,
    'scene_custom_properties': list(bpy.context.scene.keys()),
    'world_vertex_evaluation': 'Python binary64 (((m0*x + m1*y) + m2*z) + translation) using exported actual matrix and local coordinates',
    'objects': objects,
    'counts': {'objects': len(objects), 'vertices': sum(len(o['vertices_local']) for o in objects),
               'triangles': sum(len(o['triangles']) for o in objects)},
}
print(json.dumps(snapshot, ensure_ascii=True, sort_keys=True, allow_nan=False, separators=(',', ':')))
