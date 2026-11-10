confirm_cache()
def winding(point,triangles):
 relative=triangles-point
 first=relative[:,0];second=relative[:,1];third=relative[:,2]
 norms=np.linalg.norm(relative,axis=2)
 numerator=np.einsum('ij,ij->i',first,np.cross(second,third))
 denominator=norms[:,0]*norms[:,1]*norms[:,2]+np.einsum('ij,ij->i',first,second)*norms[:,2]+np.einsum('ij,ij->i',second,third)*norms[:,0]+np.einsum('ij,ij->i',third,first)*norms[:,1]
 return np.sum(2*np.arctan2(numerator,denominator))/(4*np.pi)
center=cache['Object_03']['v'].mean(axis=0)
print('Object_03 interior witness world',center.tolist(),'target-frame',(base_inv[:3,:3]@center).tolist())
for name in ['Object_01','Object_03']:
 depth=min(point_triangle(center,triangle)[0] for triangle in cache[name]['triangles'])**.5
 print('witness',name,'winding',winding(center,cache[name]['triangles']),'boundary distance',depth)
for name in ['Object_02','Object_03','Object_04']:
 center_candidate=cache[name]['v'].mean(axis=0)
 print(name,'center target winding',winding(center_candidate,cache['Object_01']['triangles']),'world AABB overlap lengths',(np.minimum(cache['Object_01']['v'].max(axis=0),cache[name]['v'].max(axis=0))-np.maximum(cache['Object_01']['v'].min(axis=0),cache[name]['v'].min(axis=0))).tolist())
print('all cached geometry and transforms reconfirmed current')