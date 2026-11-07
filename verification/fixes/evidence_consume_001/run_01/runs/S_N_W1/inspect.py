import bpy, json, importlib.util
from collections import Counter
out=[]
for name in ['Object_01','Object_02']:
 o=bpy.data.objects.get(name)
 if o is None:
  out.append({'name':name,'missing':True}); continue
 dg=bpy.context.evaluated_depsgraph_get(); eo=o.evaluated_get(dg); m=eo.to_mesh(); m.calc_loop_triangles()
 c=Counter()
 for p in m.polygons:
  for e in p.edge_keys: c[tuple(sorted(e))]+=1
 out.append({'name':name,'type':o.type,'verts':len(m.vertices),'edges':len(m.edges),'polys':len(m.polygons),'tris':len(m.loop_triangles),'edge_face_hist':dict(Counter(c.get(tuple(sorted(e.vertices)),0) for e in m.edges)),'matrix': [list(r) for r in eo.matrix_world],'bounds':[list(eo.matrix_world @ v.co) for v in m.vertices[:3]]})
 eo.to_mesh_clear()
print(json.dumps({'objects':out,'scipy':bool(importlib.util.find_spec('scipy')),'numpy':bool(importlib.util.find_spec('numpy'))}))
