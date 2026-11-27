"""Read-only canonical full-scene mesh export through the ordinary add-on queue."""
import json
import os
import threading

import bpy
import numpy as np


def mesh_record(mesh, matrix, scale):
    vertices = np.empty(3*len(mesh.vertices), dtype=np.float32)
    mesh.vertices.foreach_get("co", vertices)
    vertices = vertices.reshape((-1, 3)).astype(np.float64)
    matrix = np.asarray(matrix, dtype=np.float64)
    world = (((vertices[:, 0, None]*matrix[None, :3, 0] + vertices[:, 1, None]*matrix[None, :3, 1])
              + vertices[:, 2, None]*matrix[None, :3, 2]) + matrix[None, :3, 3])*scale
    mesh.calc_loop_triangles()
    triangles = np.empty(3*len(mesh.loop_triangles), dtype=np.int32)
    mesh.loop_triangles.foreach_get("vertices", triangles)
    polygons = np.empty(len(mesh.loop_triangles), dtype=np.int32)
    mesh.loop_triangles.foreach_get("polygon_index", polygons)
    return dict(vertices_local=vertices.tolist(), vertices_world_m=world.tolist(),
                triangles=triangles.reshape((-1, 3)).tolist(), triangle_polygons=polygons.tolist(),
                source_triangle_rows=list(range(len(mesh.loop_triangles))),
                native_polygon_vertices=[list(p.vertices) for p in mesh.polygons])


def capture():
    scene = bpy.context.scene
    graph = bpy.context.evaluated_depsgraph_get()
    scale = scene.unit_settings.scale_length
    objects = []
    for obj in sorted(scene.objects, key=lambda value:value.name):
        evaluated = obj.evaluated_get(graph)
        row = dict(name=obj.name, type=obj.type, instance_id=str(obj.session_uid),
                   matrix_world=[list(r) for r in evaluated.matrix_world],
                   visible=obj.visible_get(view_layer=bpy.context.view_layer), hide_render=obj.hide_render,
                   parent=obj.parent.name if obj.parent else None,
                   modifier_types=[m.type for m in obj.modifiers])
        if obj.type == "MESH":
            row["native"] = mesh_record(obj.data, obj.matrix_world, scale)
            mesh = evaluated.to_mesh()
            try:
                row["evaluated"] = mesh_record(mesh, evaluated.matrix_world, scale)
            finally:
                evaluated.to_mesh_clear()
        objects.append(row)
    return dict(schema="m6-044-ordinary-native-capture-v1", source=dict(
        asset=bpy.data.filepath, frame=scene.frame_current, subframe=scene.frame_subframe,
        scale_length=scale, pid=os.getpid(), background=bpy.app.background,
        main_thread=threading.current_thread() is threading.main_thread(), blender_version=list(bpy.app.version)),
        objects=objects)


print("M6_044_CAPTURE:" + json.dumps(capture(), sort_keys=True, allow_nan=False))
