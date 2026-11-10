dg=bpy.context.evaluated_depsgraph_get()
data={}
for name,obj in objs.items():
 eo=obj.evaluated_get(dg); mesh=eo.to_mesh(); mesh.calc_loop_triangles()
 local=np.array([list(v.co) for v in mesh.vertices],dtype=float); mat=np.array(obj.matrix_world,dtype=float)
 verts=local@mat[:3,:3].T+mat[:3,3]; tris=np.array([list(t.vertices) for t in mesh.loop_triangles],dtype=int)
 data[name]={'v':verts,'t':tris,'local':local,'mat':mat}
 edges={}
 for tri in tris:
  for a,b in zip(tri,np.roll(tri,-1)):
   key=tuple(sorted((int(a),int(b)))); edges[key]=edges.get(key,0)+1
 print(name,'local vertices',local.tolist(),'world AABB',verts.min(0).tolist(),verts.max(0).tolist(),'triangles',len(tris),'edge multiplicity',dict((k,list(edges.values()).count(k)) for k in set(edges.values())))
 if name=='Object_01':print('target triangles',tris.tolist())
 eo.to_mesh_clear()
