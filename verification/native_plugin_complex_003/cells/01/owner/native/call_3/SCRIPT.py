o=bpy.data.objects['Object_01']; eo=o.evaluated_get(bpy.context.evaluated_depsgraph_get()); me=eo.to_mesh()
print('target local verts',[(v.index,tuple(v.co)) for v in me.vertices]); print('faces',[tuple(p.vertices) for p in me.polygons]); eo.to_mesh_clear()
for name,data in objs.items():
 edges={}
 for tri in data['t']:
  for a,b in zip(tri,np.roll(tri,-1)):
   key=tuple(sorted((int(a),int(b)))); edges[key]=edges.get(key,0)+1
 print(name,'edge incidences',sorted(set(edges.values())))
