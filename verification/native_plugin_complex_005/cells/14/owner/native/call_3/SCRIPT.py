cache={}
for o in bpy.context.scene.objects:
 o.data.calc_loop_triangles()
 local=np.array([v.co[:] for v in o.data.vertices],dtype=float)
 mat=np.array(o.matrix_world,dtype=float)
 world=local@mat[:3,:3].T+mat[:3,3]
 tris=np.array([t.vertices[:] for t in o.data.loop_triangles],dtype=int)
 cache[o.name]={'local':local,'world':world,'tris':tris,'matrix':mat}
 print(o.name,'local vertices',local.tolist(),'triangles',tris.tolist())
 print('world AABB',world.min(axis=0).tolist(),world.max(axis=0).tolist())
 print('volume signed',sum(np.dot(world[t[0]],np.cross(world[t[1]],world[t[2]]))/6 for t in tris))