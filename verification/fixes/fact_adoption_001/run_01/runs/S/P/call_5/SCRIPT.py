import bpy, json
out={}
deps=bpy.context.evaluated_depsgraph_get()
for name in ['Object_01','Object_02']:
 o=bpy.data.objects[name]; e=o.evaluated_get(deps); m=e.to_mesh(); vs=[list(e.matrix_world @ v.co) for v in m.vertices]
 out[name]={'type':o.type,'vertex_count':len(vs),'polygon_count':len(m.polygons),'modifiers':[x.type for x in o.modifiers],'world_vertices':vs if len(vs)<=40 else None,'polygons':[list(p.vertices) for p in m.polygons] if len(m.polygons)<=40 else None}
 e.to_mesh_clear()
print(json.dumps(out))
