def unique_edges(triangles):
 return np.unique(np.sort(np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]]),axis=1),axis=0)
def vertex_face(points,vertices,triangles):
 face=vertices[triangles]; origin=face[:,0]; first=face[:,1]-origin; second=face[:,2]-origin
 normals=np.cross(first,second); norm2=np.sum(normals*normals,axis=1)
 offset=points[:,None,:]-origin[None,:,:]
 heights=np.einsum('ijk,jk->ij',offset,normals)/norm2
 projected=points[:,None,:]-heights[:,:,None]*normals
 rel=projected-origin
 aa=np.sum(first*first,axis=1); ab=np.sum(first*second,axis=1); bb=np.sum(second*second,axis=1)
 ra=np.einsum('ijk,jk->ij',rel,first); rb=np.einsum('ijk,jk->ij',rel,second)
 denom=aa*bb-ab*ab
 coord1=(bb*ra-ab*rb)/denom; coord2=(aa*rb-ab*ra)/denom
 valid=(coord1>=-1e-12)&(coord2>=-1e-12)&(coord1+coord2<=1+1e-12)
 dist2=np.where(valid,heights*heights*norm2,np.inf)
 index=np.unravel_index(np.argmin(dist2),dist2.shape)
 return float(dist2[index]),points[index[0]].copy(),projected[index].copy()
def edge_edge(vertices_a,edges_a,vertices_b,edges_b):
 start_a=vertices_a[edges_a[:,0]][:,None,:]; direction_a=(vertices_a[edges_a[:,1]]-vertices_a[edges_a[:,0]])[:,None,:]
 start_b=vertices_b[edges_b[:,0]][None,:,:]; direction_b=(vertices_b[edges_b[:,1]]-vertices_b[edges_b[:,0]])[None,:,:]
 offset=start_a-start_b
 aa=np.sum(direction_a*direction_a,axis=2); bb=np.sum(direction_a*direction_b,axis=2); cc=np.sum(direction_b*direction_b,axis=2)
 dd=np.sum(direction_a*offset,axis=2); ee=np.sum(direction_b*offset,axis=2); denom=aa*cc-bb*bb
 parameter_a=np.divide(bb*ee-cc*dd,denom,out=np.zeros_like(denom),where=denom>1e-25)
 parameter_a=np.clip(parameter_a,0,1); parameter_b=(bb*parameter_a+ee)/cc
 parameter_a=np.where(parameter_b<0,np.clip(-dd/aa,0,1),parameter_a)
 parameter_a=np.where(parameter_b>1,np.clip((bb-dd)/aa,0,1),parameter_a)
 parameter_b=np.clip(parameter_b,0,1)
 point_a=start_a+parameter_a[:,:,None]*direction_a; point_b=start_b+parameter_b[:,:,None]*direction_b
 dist2=np.sum((point_a-point_b)**2,axis=2); index=np.unravel_index(np.argmin(dist2),dist2.shape)
 return float(dist2[index]),point_a[index].copy(),point_b[index].copy()
def crossing(vertices_a,edges_a,vertices_b,triangles_b):
 start=vertices_a[edges_a[:,0]][:,None,:]; direction=(vertices_a[edges_a[:,1]]-vertices_a[edges_a[:,0]])[:,None,:]
 face=vertices_b[triangles_b]; first=face[:,1]-face[:,0]; second=face[:,2]-face[:,0]
 h=np.cross(direction,second[None,:,:]); det=np.einsum('jk,ijk->ij',first,h)
 inv=np.divide(1.0,det,out=np.zeros_like(det),where=np.abs(det)>1e-18)
 offset=start-face[None,:,0,:]; coord1=np.sum(offset*h,axis=2)*inv
 q=np.cross(offset,first[None,:,:]); coord2=np.sum(direction*q,axis=2)*inv; parameter=np.einsum('jk,ijk->ij',second,q)*inv
 valid=(np.abs(det)>1e-18)&(coord1>=0)&(coord2>=0)&(coord1+coord2<=1)&(parameter>=0)&(parameter<=1)
 return int(np.count_nonzero(valid))
results={}
vertices_a,triangles_a=geo['Target']; edges_a=unique_edges(triangles_a)
for name in names[1:]:
 vertices_b,triangles_b=geo[name]; edges_b=unique_edges(triangles_b)
 forward=vertex_face(vertices_a,vertices_b,triangles_b)
 reverse=vertex_face(vertices_b,vertices_a,triangles_a); reverse=(reverse[0],reverse[2],reverse[1])
 best=min([forward,reverse,edge_edge(vertices_a,edges_a,vertices_b,edges_b)],key=lambda value:value[0])
 intersects=crossing(vertices_a,edges_a,vertices_b,triangles_b)+crossing(vertices_b,edges_b,vertices_a,triangles_a)
 results[name]=best
 print(name,'distance_mm',format(np.sqrt(best[0])*1000,'.12f'),'Target_world_m', ['%.12f'%value for value in best[1]],'other_world_m',['%.12f'%value for value in best[2]],'edge_face_crossings',intersects)
