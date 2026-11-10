cache={}
for name in ['Object_01','Object_02','Object_03','Object_04']:
 obj=bpy.data.objects[name]; mesh=obj.data
 verts=np.array([list(v.co) for v in mesh.vertices],dtype=float)
 faces=[tuple(p.vertices) for p in mesh.polygons]
 mat=np.array(obj.matrix_world,dtype=float); world=verts@mat[:3,:3].T+mat[:3,3]
 cache[name]={'v':world,'local':verts,'faces':faces,'mat':mat,'signature':(verts.copy(),faces,mat.copy())}
 print(name,'local vertices',verts.tolist(),'faces',faces if name=='Object_01' else '', 'world AABB',world.min(axis=0).tolist(),world.max(axis=0).tolist())
