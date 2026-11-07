import bpy,json
from mathutils import Vector
out={}
dg=bpy.context.evaluated_depsgraph_get()
for name in ['Object_01','Object_02']:
 o=bpy.data.objects.get(name)
 if o is None:
  out[name]={'missing':True};continue
 eo=o.evaluated_get(dg);m=eo.to_mesh();m.calc_loop_triangles()
 vv=[eo.matrix_world@v.co for v in m.vertices]
 out[name]={'type':o.type,'vertices':len(m.vertices),'polygons':len(m.polygons),'triangles':len(m.loop_triangles),'matrix':list(map(list,eo.matrix_world)),'bounds':[[min(v[k] for v in vv),max(v[k] for v in vv)] for k in range(3)],'modifiers':[(mod.name,mod.type,mod.show_viewport) for mod in o.modifiers]}
 if len(vv)<100:out[name]['verts']=[list(v) for v in vv];out[name]['tris']=[list(t.vertices) for t in m.loop_triangles]
 eo.to_mesh_clear()
print(json.dumps(out))
