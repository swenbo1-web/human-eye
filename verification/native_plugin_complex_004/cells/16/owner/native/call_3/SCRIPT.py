depsgraph=bpy.context.evaluated_depsgraph_get()
geometry={}
for obj in [o for o in bpy.context.scene.objects if o.type=='MESH']:
 evaluated=obj.evaluated_get(depsgraph)
 mesh=evaluated.data
 matrix=np.array(evaluated.matrix_world,dtype=np.float64)
 local=np.array([tuple(v.co) for v in mesh.vertices],dtype=np.float64)
 vertices=local@matrix[:3,:3].T+matrix[:3,3]
 faces=[tuple(p.vertices) for p in mesh.polygons]
 assert all(len(face)==3 for face in faces),obj.name
 indices=np.array(faces,dtype=int)
 geometry[obj.name]={'v':vertices,'f':indices,'t':vertices[indices]}
print('evaluated meshes',len(geometry),'triangles',sum(len(g['f']) for g in geometry.values()))
print('bounds and AABB lower distance:')
target=geometry['Target']; lower=target['v'].min(0); upper=target['v'].max(0)
for name,g in geometry.items():
 if name=='Target':continue
 gap=np.maximum(np.maximum(g['v'].min(0)-upper,lower-g['v'].max(0)),0)
 print(name, 'lower',format(np.linalg.norm(gap),'.12f'))
print('target bounds',lower,upper)
