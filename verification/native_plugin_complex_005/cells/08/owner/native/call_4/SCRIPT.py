first=geometry['Target']; second=geometry['Near_017']
vertices,triangles,edges=first; vertices2,triangles2,edges2=second
origin=vertices[edges[:,0]]; direction=vertices[edges[:,1]]-origin
tri=vertices2[triangles2]; edge1=tri[:,1]-tri[:,0]; edge2=tri[:,2]-tri[:,0]
cross=np.cross(direction[:,None,:],edge2[None,:,:]); det=np.einsum('jk,ijk->ij',edge1,cross)
safe=np.where(det!=0,det,1); relative=origin[:,None,:]-tri[None,:,0,:]
alpha=np.einsum('ijk,ijk->ij',relative,cross)/safe
q=np.cross(relative,edge1[None,:,:]); beta=np.einsum('ik,ijk->ij',direction,q)/safe
param=np.einsum('jk,ijk->ij',edge2,q)/safe
hit=(det!=0)&(alpha>=0)&(beta>=0)&(alpha+beta<=1)&(param>=0)&(param<=1)
indices=np.argwhere(hit)
print('edge_face_hit_count',len(indices))
for edge_idx,tri_idx in indices[:3]:
    point_a=origin[edge_idx]+param[edge_idx,tri_idx]*direction[edge_idx]
    point_b=tri[tri_idx,0]+alpha[edge_idx,tri_idx]*edge1[tri_idx]+beta[edge_idx,tri_idx]*edge2[tri_idx]
    print('Target edge vertices',edges[edge_idx].tolist(),'Near_017 triangle vertices',triangles2[tri_idx].tolist(),'edge parameter',float(param[edge_idx,tri_idx]),'triangle barycentric',[float(1-alpha[edge_idx,tri_idx]-beta[edge_idx,tri_idx]),float(alpha[edge_idx,tri_idx]),float(beta[edge_idx,tri_idx])],'witness',point_a.tolist(),'residual_m',float(np.linalg.norm(point_a-point_b)))
print('coverage',len(results),'of',len(meshes)-1,'finite',all(math.isfinite(row[1]) for row in results))
print('scene meshes unchanged',set(geometry)=={o.name for o in bpy.context.scene.objects if o.type=='MESH'})