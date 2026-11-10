from collections import Counter
print('cache_current',all(np.array_equal(np.array(bpy.data.objects[name].matrix_world),data['matrix']) and np.array_equal(np.array([v.co[:] for v in bpy.data.objects[name].data.vertices]),data['local']) and np.array_equal(np.array([t.vertices[:] for t in bpy.data.objects[name].data.loop_triangles]),data['tris']) for name,data in cache.items()))
for name,data in cache.items():
 counts=Counter(tuple(sorted((int(tri[edge]),int(tri[(edge+1)%3])))) for tri in data['tris'] for edge in range(3))
 print(name,'edge incidence counts',dict(Counter(counts.values())))
witness=cache['Object_03']['matrix'][:3,3]
print('Object_03 center world',witness.tolist(),'target local',(inv_target[:3,:3]@witness+inv_target[:3,3]).tolist())
for name in ['Object_01','Object_03']:
 data=cache[name]
 distances=[np.linalg.norm(point_triangle(witness,data['world'][indices])-witness) for indices in data['tris']]
 triangles=data['world'][data['tris']]-witness
 first=triangles[:,0]; second=triangles[:,1]; third=triangles[:,2]
 norms=np.linalg.norm(triangles,axis=2)
 numer=np.einsum('ij,ij->i',first,np.cross(second,third))
 denom=norms.prod(axis=1)+np.einsum('ij,ij->i',first,second)*norms[:,2]+np.einsum('ij,ij->i',second,third)*norms[:,0]+np.einsum('ij,ij->i',third,first)*norms[:,1]
 winding=np.sum(2*np.arctan2(numer,denom))/(4*np.pi)
 print(name,'witness boundary distance',min(distances),'winding',winding)
