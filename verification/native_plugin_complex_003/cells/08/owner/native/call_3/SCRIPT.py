dg=bpy.context.evaluated_depsgraph_get()
geo={}
for name,obj in objs.items():
 eo=obj.evaluated_get(dg); me=eo.to_mesh(); me.calc_loop_triangles()
 vs=np.array([tuple(v.co) for v in me.vertices],dtype=float); mat=np.array(obj.matrix_world,dtype=float)
 world=vs@mat[:3,:3].T+mat[:3,3]
 ts=np.array([tuple(t.vertices) for t in me.loop_triangles],dtype=int)
 geo[name]=(world,ts)
 print(name,'local vertices',vs.tolist() if name=='Object_01' else [vs.min(0).tolist(),vs.max(0).tolist()])
 edges={}
 for tri in ts:
  for a,b in zip(tri,np.roll(tri,-1)):
   key=tuple(sorted((int(a),int(b)))); edges[key]=edges.get(key,0)+1
 print('edge incidences',set(edges.values()),'signed volume',np.einsum('ij,ij->i',world[ts[:,0]],np.cross(world[ts[:,1]],world[ts[:,2]])).sum()/6)
 eo.to_mesh_clear()
base=geo['Object_01']; bvh=BVHTree.FromPolygons([Vector(v) for v in base[0]],base[1].tolist(),all_triangles=True,epsilon=0.0)
for name in list(objs)[1:]:
 vs,ts=geo[name]; cb=BVHTree.FromPolygons([Vector(v) for v in vs],ts.tolist(),all_triangles=True,epsilon=0.0)
 print(name,'overlap pairs',bvh.overlap(cb))
