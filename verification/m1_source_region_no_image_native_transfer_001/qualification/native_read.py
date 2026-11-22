# This diagnostic executes only in the owned, read-only Blender process.
import json
import bpy

names = ('M12', 'M17', 'M19', 'M15', 'M08', 'M02')
depsgraph = bpy.context.evaluated_depsgraph_get()
scale = bpy.context.scene.unit_settings.scale_length
meshes = {}
for name in names:
    obj = bpy.context.scene.objects[name].evaluated_get(depsgraph)
    mesh = obj.to_mesh()
    try:
        mesh.calc_loop_triangles()
        meshes[name] = {
            'vertices': [[float(c) * scale for c in obj.matrix_world @ vertex.co] for vertex in mesh.vertices],
            'faces': [list(triangle.vertices) for triangle in mesh.loop_triangles],
        }
    finally:
        obj.to_mesh_clear()
print(json.dumps({'meshes': meshes, 'frame': bpy.context.scene.frame_current, 'scale_length': scale}))
