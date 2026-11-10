# Check cached geometry against the current scene before using it.
for name, data in cache.items():
 obj=bpy.data.objects[name]
 assert np.array_equal(np.array(obj.matrix_world,dtype=float), data['mat'])
 assert np.array_equal(np.array([v.co[:] for v in obj.data.vertices],dtype=float),data['local'])
 assert not obj.modifiers
print('cache matches current meshes and transforms')
def edges_of(data):
 return np.unique(np.sort(np.concatenate([data['t'][:,[0,1]],data['t'][:,[1,2]],data['t'][:,[2,0]]]),axis=1),axis=0)
def point_faces(points, verts, triangles):
 tri=verts[triangles]; origin=tri[:,0]; u=tri[:,1]-origin; v=tri[:,2]-origin
 normal=np.cross(u,v); norm2=np.sum(normal*normal,axis=1)
 delta=points[:,None,:]-origin[None,:,:]
 signed=np.einsum('ijk,jk->ij',delta,normal)/norm2
 projected=points[:,None,:]-signed[:,:,None]*normal[None,:,:]
 w=projected-origin[None,:,:]
 uu=np.sum(u*u,axis=1); uv=np.sum(u*v,axis=1); vv=np.sum(v*v,axis=1)
 wu=np.einsum('ijk,jk->ij',w,u); wv=np.einsum('ijk,jk->ij',w,v)
 denominator=uu*vv-uv*uv
 alpha=(wu*vv-wv*uv)/denominator; beta=(wv*uu-wu*uv)/denominator
 dist2=signed*signed*norm2
 dist2[(alpha < -1e-12)|(beta < -1e-12)|(alpha+beta > 1+1e-12)]=np.inf
 index=np.unravel_index(np.argmin(dist2),dist2.shape)
 return float(dist2[index]),points[index[0]],projected[index]
def edge_distance(data_a,data_b):
 edges_a=edges_of(data_a); edges_b=edges_of(data_b)
 p=data_a['v'][edges_a[:,0]][:,None,:]; q=data_b['v'][edges_b[:,0]][None,:,:]
 u=(data_a['v'][edges_a[:,1]]-data_a['v'][edges_a[:,0]])[:,None,:]
 v=(data_b['v'][edges_b[:,1]]-data_b['v'][edges_b[:,0]])[None,:,:]
 w=p-q
 aa=np.sum(u*u,axis=2); bb=np.sum(u*v,axis=2); cc=np.sum(v*v,axis=2); dd=np.sum(u*w,axis=2); ee=np.sum(v*w,axis=2)
 denom=aa*cc-bb*bb
 safe=np.where(denom>1e-25,denom,1)
 ss=(bb*ee-cc*dd)/safe; tt=(aa*ee-bb*dd)/safe
 valid=(denom>1e-25)&(ss>=0)&(ss<=1)&(tt>=0)&(tt<=1)
 candidates=[(ss,tt,valid),(np.zeros_like(dd),np.clip(ee/cc,0,1),True),(np.ones_like(dd),np.clip((ee+bb)/cc,0,1),True),(np.clip(-dd/aa,0,1),np.zeros_like(dd),True),(np.clip((bb-dd)/aa,0,1),np.ones_like(dd),True)]
 best=(np.inf,None,None)
 for s,t,mask in candidates:
  pa=p+s[:,:,None]*u; pb=q+t[:,:,None]*v
  distances=np.where(mask,np.sum((pa-pb)**2,axis=2),np.inf)
  idx=np.unravel_index(np.argmin(distances),distances.shape)
  if distances[idx]<best[0]: best=(float(distances[idx]),pa[idx],pb[idx])
 return best
target=cache['Object_01']; inverse=np.linalg.inv(target['mat'])
for name in names[1:]:
 data=cache[name]
 relative=(data['v']-target['mat'][:3,3])@inverse[:3,:3].T
 print(name,'target-frame bounds',relative.min(axis=0).tolist(),relative.max(axis=0).tolist(),'center',relative.mean(axis=0).tolist())
 if name!='Object_03':
  pf=point_faces(target['v'],data['v'],data['t']); fp=point_faces(data['v'],target['v'],target['t']); fp=(fp[0],fp[2],fp[1])
  best=min([pf,fp,edge_distance(target,data)], key=lambda result:result[0])
  print('exhaustive vertex-face + edge-edge minimum',math.sqrt(best[0]),'world witnesses',best[1].tolist(),best[2].tolist(),'target-frame witnesses',(inverse[:3,:3]@best[1]).tolist(),(inverse[:3,:3]@best[2]).tolist())
 print('AABB overlap extents',(np.minimum(target['v'].max(axis=0),data['v'].max(axis=0))-np.maximum(target['v'].min(axis=0),data['v'].min(axis=0))).tolist())
for name in names:
 data=cache[name]; tri=data['v'][data['t']]
 all_edges=np.sort(np.concatenate([data['t'][:,[0,1]],data['t'][:,[1,2]],data['t'][:,[2,0]]]),axis=1)
 _,counts=np.unique(all_edges,axis=0,return_counts=True)
 print(name,'closed edges count2',bool(np.all(counts==2)),'signed volume',float(np.sum(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])))/6))
