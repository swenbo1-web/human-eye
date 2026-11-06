import bpy, json, hashlib
bpy.context.view_layer.update()
dg=bpy.context.evaluated_depsgraph_get(); dg.update()
ans=[]
for name in ['Object_01','Object_02','Object_03','Object_04']:
 ob=bpy.data.objects[name]; ev=ob.evaluated_get(dg); m=ev.to_mesh(); m.calc_loop_triangles()
 data={'vertices':[list(v.co) for v in m.vertices],'triangles':[list(t.vertices) for t in m.loop_triangles],'matrix':[list(r) for r in ev.matrix_world]}
 ans.append({'name':name,'datablock':ob.data.name,'raw_vertices':len(ob.data.vertices),'evaluated_vertices':len(m.vertices),'evaluated_triangles':len(m.loop_triangles),'modifiers':[(x.type,x.show_viewport) for x in ob.modifiers],'matrix':data['matrix'],'local_extrema':[[min(v.co[i] for v in m.vertices),max(v.co[i] for v in m.vertices)]for i in range(3)],'geometry_sha256':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(),'local_vertices':data['vertices'] if name=='Object_01' else None})
 ev.to_mesh_clear()
print(json.dumps(ans))
