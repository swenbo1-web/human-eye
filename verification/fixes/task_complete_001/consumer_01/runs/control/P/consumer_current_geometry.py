import bpy, json, hashlib
result = []
depsgraph = bpy.context.evaluated_depsgraph_get()
for name in ('Object_01', 'Object_02'):
    obj = bpy.data.objects[name]
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        vertices = [tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices]
        polygons = [tuple(polygon.vertices) for polygon in mesh.polygons]
        geometry = {'vertices': vertices, 'polygons': polygons}
        digest = hashlib.sha256(json.dumps(geometry, separators=(',', ':')).encode()).hexdigest()
        row = {'name': name, 'vertices_count': len(vertices), 'polygons_count': len(polygons), 'world_geometry_sha256': digest, 'aabb': [[min(v[i] for v in vertices) for i in range(3)], [max(v[i] for v in vertices) for i in range(3)]]}
        if len(vertices) <= 64:
            row['world_vertices'] = vertices
        if len(polygons) <= 32:
            row['polygons'] = polygons
        result.append(row)
    finally:
        evaluated.to_mesh_clear()
print(json.dumps({'current_evaluated_geometry': result}))
