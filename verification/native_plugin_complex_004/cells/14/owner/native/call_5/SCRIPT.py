# Closed-mesh solid-angle test distinguishes the hole from target material.
def winding(point,mesh):
 offsets=mesh['v'][mesh['f']]-point
 lengths=np.linalg.norm(offsets,axis=2)
 numerator=np.einsum('ij,ij->i',offsets[:,0],np.cross(offsets[:,1],offsets[:,2]))
 denominator=lengths.prod(axis=1)+np.einsum('ij,ij->i',offsets[:,0],offsets[:,1])*lengths[:,2]+np.einsum('ij,ij->i',offsets[:,1],offsets[:,2])*lengths[:,0]+np.einsum('ij,ij->i',offsets[:,2],offsets[:,0])*lengths[:,1]
 return float(np.sum(2*np.arctan2(numerator,denominator))/(4*np.pi))
for name in ['Object_02','Object_03','Object_04']:
 obj=objs[name]
 assert np.array_equal(np.array(obj.matrix_world),geo[name]['matrix']) and np.array_equal(np.array([v.co[:] for v in obj.data.vertices]),geo[name]['local'])
 center=geo[name]['v'].mean(axis=0)
 print(name,'center world',center.tolist(),'center target-local',geo[name]['target_local'].mean(axis=0).tolist(),'winding center',winding(center,geo['Object_01']),'vertex windings',[round(winding(point,geo['Object_01']),9) for point in geo[name]['v']])
 print('AABB overlap lengths',(np.minimum(geo['Object_01']['v'].max(axis=0),geo[name]['v'].max(axis=0))-np.maximum(geo['Object_01']['v'].min(axis=0),geo[name]['v'].min(axis=0))).tolist())
print('target center winding',winding(geo['Object_01']['v'].mean(axis=0),geo['Object_01']))
