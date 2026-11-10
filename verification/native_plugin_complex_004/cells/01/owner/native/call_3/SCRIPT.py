names=['Object_01','Object_02','Object_03','Object_04']
cache={}
deps=bpy.context.evaluated_depsgraph_get()
for name in names:
 o=bpy.data.objects[name]; ev=o.evaluated_get(deps); mesh=ev.to_mesh(); mesh.calc_loop_triangles()
 local=np.array([v.co[:] for v in mesh.vertices],dtype=float)
 mat=np.array(o.matrix_world,dtype=float); verts=local@mat[:3,:3].T+mat[:3,3]
 tris=np.array([t.vertices[:] for t in mesh.loop_triangles],dtype=int)
 cache[name]={'v':verts,'t':tris,'local':local,'mat':mat}
 ev.to_mesh_clear()
 print(name,'local vertices',local.tolist(),'world bounds',verts.min(axis=0).tolist(),verts.max(axis=0).tolist())
 if name=='Object_01': print('triangles',tris.tolist())
