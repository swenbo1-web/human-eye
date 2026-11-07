import bpy,json,collections
G=[]
for name in ['Object_01','Object_02']:
 o=bpy.data.objects[name];e=o.evaluated_get(bpy.context.evaluated_depsgraph_get());m=e.to_mesh();m.calc_loop_triangles()
 V=[tuple(float(x) for x in (e.matrix_world@v.co)) for v in m.vertices];T=[tuple(t.vertices) for t in m.loop_triangles]
 uses=collections.defaultdict(list)
 for pi,p in enumerate(m.polygons):
  ids=list(p.vertices)
  for a,b in zip(ids,ids[1:]+ids[:1]):uses[tuple(sorted((a,b)))].append((pi,a,b))
 out={'name':name,'V':V,'T':T,'polygons':[list(p.vertices) for p in m.polygons], 'edge_face_use':[(list(k),v) for k,v in uses.items()]}
 G.append({'V':V,'T':T})
 print(json.dumps(out))
 e.to_mesh_clear()
