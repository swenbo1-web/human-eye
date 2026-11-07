
import json
rows = {}
for obj in sorted(bpy.data.objects, key=lambda value: value.name):
    if obj.type == 'MESH':
        rows[obj.name] = dict(vertices=[list(obj.matrix_world @ vertex.co) for vertex in obj.data.vertices],
                              faces=[list(face.vertices) for face in obj.data.polygons],
                              matrix=[list(row) for row in obj.matrix_world])
print(json.dumps(rows))
