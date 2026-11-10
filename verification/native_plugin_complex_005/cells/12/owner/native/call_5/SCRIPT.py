# Validate cached geometry against the current scene before further use.
print('cache_current',all(np.array_equal(np.array(obs[name].matrix_world,dtype=float),geo[name][3]) and np.array_equal(np.array([v.co[:] for v in obs[name].data.vertices],dtype=float),geo[name][2]) for name in geo))
def winding_number(point, vertices, triangles):
 offsets=vertices[triangles]-point
 lengths=np.linalg.norm(offsets,axis=2)
 numerator=np.einsum('ij,ij->i',offsets[:,0],np.cross(offsets[:,1],offsets[:,2]))
 denominator=lengths.prod(axis=1)+np.einsum('ij,ij->i',offsets[:,0],offsets[:,1])*lengths[:,2]+np.einsum('ij,ij->i',offsets[:,1],offsets[:,2])*lengths[:,0]+np.einsum('ij,ij->i',offsets[:,2],offsets[:,0])*lengths[:,1]
 return np.sum(2*np.arctan2(numerator,denominator))/(4*np.pi)
world03,tris03,_,_=geo['Object_03']
witness=world03.mean(axis=0)
print('interior witness world',witness.tolist(),'target local',(inv_target[:3,:3]@witness+inv_target[:3,3]).tolist(),'winding target',winding_number(witness,target_world,target_tris),'winding candidate',winding_number(witness,world03,tris03))
print('witness distances to target and Object_03 surface',math.sqrt(point_triangle_batch(witness[None,:],target_world[target_tris])[0]),math.sqrt(point_triangle_batch(witness[None,:],world03[tris03])[0]))
# Moller-Trumbore proper edge/triangle intersections (excluding endpoints).
edges=world03[unique_edges(tris03)]; starts=edges[:,None,0]; directions=edges[:,None,1]-starts
triangles=target_world[target_tris];origin=triangles[None,:,0];edge1=triangles[None,:,1]-origin;edge2=triangles[None,:,2]-origin
cross=np.cross(directions,edge2);det=np.sum(edge1*cross,axis=-1);nonparallel=np.abs(det)>1e-14
inverse=np.divide(1.,det,out=np.zeros_like(det),where=nonparallel);relative=starts-origin
bary1=np.sum(relative*cross,-1)*inverse;cross2=np.cross(relative,edge1);bary2=np.sum(directions*cross2,-1)*inverse;parameter=np.sum(edge2*cross2,-1)*inverse
hits=nonparallel&(bary1>=-1e-10)&(bary2>=-1e-10)&(bary1+bary2<=1+1e-10)&(parameter>1e-8)&(parameter<1-1e-8)
hit_indices=np.argwhere(hits)
print('proper edge triangle intersections',len(hit_indices))
for edge_index,triangle_index in hit_indices[:3]:
 point=starts[edge_index,0]+parameter[edge_index,triangle_index]*directions[edge_index,0]
 print('intersection world',point.tolist(),'target local',(inv_target[:3,:3]@point+inv_target[:3,3]).tolist())
