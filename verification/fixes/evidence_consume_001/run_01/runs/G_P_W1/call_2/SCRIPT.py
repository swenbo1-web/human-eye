import bpy, json
out=[]
dg=bpy.context.evaluated_depsgraph_get()
for name in ['Object_01','Object_02']:
    obj=bpy.data.objects.get(name)
    e=obj.evaluated_get(dg)
    m=e.to_mesh()
    try:
        out.append({'name':name,'type':obj.type,'vertices_world':[list(e.matrix_world @ v.co) for v in m.vertices],'faces':[list(p.vertices) for p in m.polygons],'modifiers':[{'type':x.type,'show_viewport':x.show_viewport} for x in obj.modifiers]})
    finally:
        e.to_mesh_clear()
print(json.dumps(out,ensure_ascii=False))
