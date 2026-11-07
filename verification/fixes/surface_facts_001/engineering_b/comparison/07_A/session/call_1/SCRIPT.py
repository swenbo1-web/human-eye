import json
print(json.dumps({obj.name:dict(vertices=[list(v.co) for v in obj.data.vertices],
faces=[list(p.vertices) for p in obj.data.polygons], matrix=[list(r) for r in obj.matrix_world],
modifiers=len(obj.modifiers)) for obj in bpy.data.objects if obj.type=='MESH'}))
