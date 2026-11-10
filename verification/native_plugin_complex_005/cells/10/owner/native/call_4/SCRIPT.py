def cache_current():
 return all(np.array_equal(np.array(bpy.data.objects[name].matrix_world),data['matrix']) and np.array_equal(np.array([list(v.co) for v in bpy.data.objects[name].data.vertices]),data['local']) and np.array_equal(np.array([list(t.vertices) for t in bpy.data.objects[name].data.loop_triangles]),data['triangles']) for name,data in meshes.items())
print('cached scene unchanged',cache_current())
inverse_target=np.linalg.inv(meshes['Object_01']['matrix'])
for name in names[1:]:
 points=meshes[name]['world']@inverse_target[:3,:3].T+inverse_target[:3,3]
 print(name,'in target local coordinates',points.tolist())

def point_triangle_candidates(points,triangles):
 point=points[:,None,:]; first=triangles[None,:,0,:]; ab=triangles[None,:,1,:]-first; ac=triangles[None,:,2,:]-first
 normal=np.cross(ab,ac); norm2=np.sum(normal*normal,axis=-1)
 projected=point-np.sum((point-first)*normal,axis=-1)[...,None]/norm2[...,None]*normal
 relative=projected-first
 aa=np.sum(ab*ab,axis=-1); bb=np.sum(ab*ac,axis=-1); cc=np.sum(ac*ac,axis=-1)
 dd=np.sum(relative*ab,axis=-1); ee=np.sum(relative*ac,axis=-1); determinant=aa*cc-bb*bb
 coord_b=(cc*dd-bb*ee)/determinant; coord_c=(aa*ee-bb*dd)/determinant
 valid=(coord_b>=-1e-12)&(coord_c>=-1e-12)&(coord_b+coord_c<=1+1e-12)
 squared=np.where(valid,np.sum((point-projected)**2,axis=-1),np.inf)
 idx=np.unravel_index(np.argmin(squared),squared.shape)
 return float(squared[idx]), points[idx[0]],projected[idx],('vertex-face',idx)

def mesh_edges(data):
 indices=np.array(sorted({tuple(sorted((int(tri[j]),int(tri[(j+1)%3])))) for tri in data['triangles'] for j in range(3)}))
 return data['world'][indices]

def edge_edge_candidates(edges_a,edges_b):
 origin_a=edges_a[:,None,0,:]; origin_b=edges_b[None,:,0,:]
 direction_a=edges_a[:,None,1,:]-origin_a; direction_b=edges_b[None,:,1,:]-origin_b; relative=origin_a-origin_b
 aa=np.sum(direction_a**2,axis=-1); bb=np.sum(direction_a*direction_b,axis=-1); cc=np.sum(direction_b**2,axis=-1)
 dd=np.sum(direction_a*relative,axis=-1); ee=np.sum(direction_b*relative,axis=-1); denominator=aa*cc-bb*bb
 safe=np.where(np.abs(denominator)>1e-24,denominator,1)
 param_a=(bb*ee-cc*dd)/safe; param_b=(aa*ee-bb*dd)/safe
 candidates=[(param_a,param_b,(np.abs(denominator)>1e-24)&(param_a>=0)&(param_a<=1)&(param_b>=0)&(param_b<=1)),(np.zeros_like(ee),np.clip(ee/cc,0,1),True),(np.ones_like(ee),np.clip((ee+bb)/cc,0,1),True),(np.clip(-dd/aa,0,1),np.zeros_like(dd),True),(np.clip((bb-dd)/aa,0,1),np.ones_like(dd),True)]
 best=(float('inf'),None,None,None)
 for pa,pb,valid in candidates:
  point_a=origin_a+pa[...,None]*direction_a; point_b=origin_b+pb[...,None]*direction_b
  squared=np.where(valid,np.sum((point_a-point_b)**2,axis=-1),np.inf); index=np.unravel_index(np.argmin(squared),squared.shape)
  if squared[index]<best[0]:best=(float(squared[index]),point_a[index],point_b[index],('edge-edge',index))
 return best

def winding(points,data):
 triangle=data['world'][data['triangles']]
 vectors=triangle[None,:,:,:]-points[:,None,None,:]
 va,vb,vc=vectors[:,:,0],vectors[:,:,1],vectors[:,:,2]
 la=np.linalg.norm(va,axis=-1);lb=np.linalg.norm(vb,axis=-1);lc=np.linalg.norm(vc,axis=-1)
 numerator=np.sum(va*np.cross(vb,vc),axis=-1)
 denominator=la*lb*lc+np.sum(va*vb,axis=-1)*lc+np.sum(vb*vc,axis=-1)*la+np.sum(vc*va,axis=-1)*lb
 return np.sum(2*np.arctan2(numerator,denominator),axis=1)/(4*np.pi)

results={}
target=meshes[names[0]]
for name in names[1:]:
 candidate=meshes[name]
 options=[point_triangle_candidates(target['world'],candidate['world'][candidate['triangles']])]
 reverse=point_triangle_candidates(candidate['world'],target['world'][target['triangles']]);options.append((reverse[0],reverse[2],reverse[1],reverse[3]))
 options.append(edge_edge_candidates(mesh_edges(target),mesh_edges(candidate)))
 best=min(options,key=lambda item:item[0]);results[name]=best
 print(name,'minimum feature distance',math.sqrt(best[0]),'target point',best[1].tolist(),'candidate point',best[2].tolist(),'feature',best[3])
 print('candidate vertex winding inside target',winding(candidate['world'],target).tolist(),'center winding',winding(candidate['world'].mean(axis=0)[None,:],target).tolist())