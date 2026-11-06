import json
from collections import Counter
old_rows = globals().get('rows', None)
current_rows=[]
dg=bpy.context.evaluated_depsgraph_get()
for name in ['Object_01','Object_02']:
    obj=bpy.data.objects[name]
    ev=obj.evaluated_get(dg)
    mesh=ev.to_mesh()
    mesh.calc_loop_triangles()
    verts=[tuple(ev.matrix_world @ v.co) for v in mesh.vertices]
    edges=Counter(tuple(sorted((p.vertices[i],p.vertices[(i+1)%len(p.vertices)]))) for p in mesh.polygons for i in range(len(p.vertices)))
    current_rows.append({'name':name,'type':obj.type,'vertices':verts if len(verts)<=100 else None,'triangles':[list(t.vertices) for t in mesh.loop_triangles] if len(mesh.loop_triangles)<=200 else None,'vertex_count':len(verts),'triangle_count':len(mesh.loop_triangles),'edge_face_counts':dict(Counter(edges.values())),'matrix_world':[list(r) for r in ev.matrix_world]})
    ev.to_mesh_clear()
print(json.dumps({'prior_native_cache_available':old_rows is not None,'current_equals_prior':current_rows==old_rows if old_rows is not None else None,'current':current_rows}))
rows=current_rows
