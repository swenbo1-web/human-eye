def point_face(points, triangles):
 origin=triangles[:,0]; edge_u=triangles[:,1]-origin; edge_v=triangles[:,2]-origin
 normal=np.cross(edge_u,edge_v); norm2=np.einsum('ij,ij->i',normal,normal)
 delta=points[:,None,:]-origin[None,:,:]
 signed=np.einsum('ijk,jk->ij',delta,normal)/norm2
 projected=points[:,None,:]-signed[:,:,None]*normal[None,:,:]
 rel=projected-origin[None,:,:]
 uu=np.einsum('ij,ij->i',edge_u,edge_u); uv=np.einsum('ij,ij->i',edge_u,edge_v); vv=np.einsum('ij,ij->i',edge_v,edge_v)
 ru=np.einsum('ijk,jk->ij',rel,edge_u); rv=np.einsum('ijk,jk->ij',rel,edge_v)
 determinant=uu*vv-uv*uv
 bary_u=(ru*vv-rv*uv)/determinant; bary_v=(rv*uu-ru*uv)/determinant
 inside=(bary_u>=0)&(bary_v>=0)&(bary_u+bary_v<=1)
 distances=np.where(inside,signed*signed*norm2,np.inf)
 row,col=np.unravel_index(np.argmin(distances),distances.shape)
 return float(distances[row,col]),points[row],projected[row,col],(int(row),int(col))
def edges_of(triangles):
 return triangles[:,[0,1,2],:].reshape(-1,3),triangles[:,[1,2,0],:].reshape(-1,3)
def point_edge(points,starts,ends):
 direction=ends-starts
 delta=points[:,None,:]-starts[None,:,:]
 parameters=np.clip(np.einsum('ijk,jk->ij',delta,direction)/np.einsum('ij,ij->i',direction,direction),0,1)
 closest=starts[None,:,:]+parameters[:,:,None]*direction[None,:,:]
 sq=np.sum((points[:,None,:]-closest)**2,axis=2)
 row,col=np.unravel_index(np.argmin(sq),sq.shape)
 return float(sq[row,col]),points[row],closest[row,col],(int(row),int(col))
def edge_edge(starts_a,ends_a,starts_b,ends_b):
 direction_a=ends_a-starts_a;direction_b=ends_b-starts_b
 delta=starts_a[:,None,:]-starts_b[None,:,:]
 aa=np.sum(direction_a*direction_a,axis=1)[:,None];bb=np.sum(direction_b*direction_b,axis=1)[None,:]
 ab=direction_a@direction_b.T
 ad=np.einsum('ijk,ik->ij',delta,direction_a);bd=np.einsum('ijk,jk->ij',delta,direction_b)
 determinant=aa*bb-ab*ab
 valid=determinant>1e-28
 safe=np.where(valid,determinant,1)
 param_a=(ab*bd-bb*ad)/safe;param_b=(aa*bd-ab*ad)/safe
 valid &= (param_a>=0)&(param_a<=1)&(param_b>=0)&(param_b<=1)
 closest_a=starts_a[:,None,:]+param_a[:,:,None]*direction_a[:,None,:]
 closest_b=starts_b[None,:,:]+param_b[:,:,None]*direction_b[None,:,:]
 sq=np.where(valid,np.sum((closest_a-closest_b)**2,axis=2),np.inf)
 row,col=np.unravel_index(np.argmin(sq),sq.shape)
 return float(sq[row,col]),closest_a[row,col],closest_b[row,col],(int(row),int(col))
def crossings(starts,ends,triangles):
 origin=triangles[:,0];edge_u=triangles[:,1]-origin;edge_v=triangles[:,2]-origin
 direction=ends-starts
 cross=np.cross(direction[:,None,:],edge_v[None,:,:]);det=np.einsum('ijk,jk->ij',cross,edge_u)
 valid=np.abs(det)>1e-24;safe=np.where(valid,det,1)
 delta=starts[:,None,:]-origin[None,:,:]
 bary_u=np.sum(delta*cross,axis=2)/safe
 cross2=np.cross(delta,edge_u[None,:,:])
 bary_v=np.einsum('ijk,ik->ij',cross2,direction)/safe
 parameter=np.einsum('ijk,jk->ij',cross2,edge_v)/safe
 valid &= (bary_u>=0)&(bary_v>=0)&(bary_u+bary_v<=1)&(parameter>=0)&(parameter<=1)
 if np.any(valid):
  row,col=np.argwhere(valid)[0];point=starts[row]+parameter[row,col]*direction[row]
  return 0.,point,point,(int(row),int(col))
 return None

def surface_distance(geom_a,geom_b):
 triangles_a=geom_a['t'];triangles_b=geom_b['t']
 starts_a,ends_a=edges_of(triangles_a);starts_b,ends_b=edges_of(triangles_b)
 candidates=[]
 for label,entry in [('Aedge_Bface',crossings(starts_a,ends_a,triangles_b)),('Bedge_Aface',crossings(starts_b,ends_b,triangles_a))]:
  if entry is not None:return (*entry,label)
 for label,entry,reverse in [('Avertex_Bface',point_face(geom_a['v'],triangles_b),False),('Bvertex_Aface',point_face(geom_b['v'],triangles_a),True),('Avertex_Bedge',point_edge(geom_a['v'],starts_b,ends_b),False),('Bvertex_Aedge',point_edge(geom_b['v'],starts_a,ends_a),True),('Aedge_Bedge',edge_edge(starts_a,ends_a,starts_b,ends_b),False)]:
  sq,first,second,indices=entry
  if reverse:first,second=second,first
  candidates.append((sq,first,second,indices,label))
 return min(candidates,key=lambda entry:entry[0])
started=time.time();results={}
for name,geom in geometry.items():
 if name!='Target':results[name]=surface_distance(target,geom)
print('elapsed',time.time()-started)
for name,result in sorted(results.items(),key=lambda item:item[1][0]):
 print(name,format(math.sqrt(result[0]),'.12f'),result[4],result[3])
