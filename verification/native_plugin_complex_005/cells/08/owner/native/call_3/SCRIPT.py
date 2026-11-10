depsgraph=bpy.context.evaluated_depsgraph_get()
geometry={}
for obj in meshes:
    ev=obj.evaluated_get(depsgraph); mesh=ev.to_mesh(); mesh.calc_loop_triangles()
    local=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)
    matrix=np.array(ev.matrix_world,dtype=np.float64)
    vertices=local@matrix[:3,:3].T+matrix[:3,3]
    triangles=np.array([t.vertices[:] for t in mesh.loop_triangles],dtype=np.int64)
    edges=np.unique(np.sort(np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]]),axis=1),axis=0)
    geometry[obj.name]=(vertices,triangles,edges)
    ev.to_mesh_clear()
print('evaluated',len(geometry),'triangle_counts',sorted(set(len(g[1]) for g in geometry.values())))
print('Target bounds',geometry['Target'][0].min(axis=0).tolist(),geometry['Target'][0].max(axis=0).tolist())
def point_face(vertices, other):
    points,triangles,edges=other
    tri=points[triangles]; base=tri[:,0]; u=tri[:,1]-base; v=tri[:,2]-base
    normal=np.cross(u,v); norm2=np.einsum('ij,ij->i',normal,normal)
    offset=vertices[:,None,:]-base[None,:,:]
    height=np.einsum('ijk,jk->ij',offset,normal)/np.where(norm2>0,norm2,1)[None,:]
    projected=vertices[:,None,:]-height[:,:,None]*normal[None,:,:]
    rel=projected-base[None,:,:]
    uu=np.einsum('ij,ij->i',u,u); uv=np.einsum('ij,ij->i',u,v); vv=np.einsum('ij,ij->i',v,v)
    ru=np.einsum('ijk,jk->ij',rel,u); rv=np.einsum('ijk,jk->ij',rel,v)
    den=uu*vv-uv*uv; safe=np.where(den>0,den,1)
    alpha=(vv*ru-uv*rv)/safe; beta=(uu*rv-uv*ru)/safe
    valid=(alpha>=0)&(beta>=0)&(alpha+beta<=1)&(den[None,:]>0)
    dist2=height*height*norm2[None,:]; dist2=np.where(valid,dist2,np.inf)
    idx=np.unravel_index(np.argmin(dist2),dist2.shape)
    return float(dist2[idx]),vertices[idx[0]],projected[idx]
def edge_face_hit(first,second):
    verts,tris,edges=first; verts2,tris2,edges2=second
    origin=verts[edges[:,0]]; direction=verts[edges[:,1]]-origin
    tri=verts2[tris2]; edge1=tri[:,1]-tri[:,0]; edge2=tri[:,2]-tri[:,0]
    cross=np.cross(direction[:,None,:],edge2[None,:,:]); det=np.einsum('jk,ijk->ij',edge1,cross)
    safe=np.where(det!=0,det,1); relative=origin[:,None,:]-tri[None,:,0,:]
    alpha=np.einsum('ijk,ijk->ij',relative,cross)/safe
    q=np.cross(relative,edge1[None,:,:]); beta=np.einsum('ik,ijk->ij',direction,q)/safe
    param=np.einsum('jk,ijk->ij',edge2,q)/safe
    hit=(det!=0)&(alpha>=0)&(beta>=0)&(alpha+beta<=1)&(param>=0)&(param<=1)
    indices=np.argwhere(hit)
    if len(indices):
        edge_idx,tri_idx=indices[0]; return origin[edge_idx]+param[edge_idx,tri_idx]*direction[edge_idx]
    return None
def edge_edge(first,second):
    verts,tris,edges=first; verts2,tris2,edges2=second
    p=verts[edges[:,0]][:,None,:]; u=(verts[edges[:,1]]-verts[edges[:,0]])[:,None,:]
    q=verts2[edges2[:,0]][None,:,:]; v=(verts2[edges2[:,1]]-verts2[edges2[:,0]])[None,:,:]
    w=p-q; aa=np.sum(u*u,axis=2); bb=np.sum(u*v,axis=2); cc=np.sum(v*v,axis=2); dd=np.sum(u*w,axis=2); ee=np.sum(v*w,axis=2)
    determinant=aa*cc-bb*bb
    ss=(bb*ee-cc*dd)/np.where(determinant>0,determinant,1)
    tt=(aa*ee-bb*dd)/np.where(determinant>0,determinant,1)
    candidates=[(ss,tt,(determinant>0)&(ss>=0)&(ss<=1)&(tt>=0)&(tt<=1)),(np.zeros_like(bb),np.clip(ee/cc,0,1),True),(np.ones_like(bb),np.clip((ee+bb)/cc,0,1),True),(np.clip(-dd/aa,0,1),np.zeros_like(bb),True),(np.clip((bb-dd)/aa,0,1),np.ones_like(bb),True)]
    best=(float('inf'),None,None)
    for s,t,valid in candidates:
        pp=p+s[:,:,None]*u; qq=q+t[:,:,None]*v
        distances=np.where(valid,np.sum((pp-qq)**2,axis=2),np.inf)
        idx=np.unravel_index(np.argmin(distances),distances.shape)
        if distances[idx]<best[0]: best=(float(distances[idx]),pp[idx],qq[idx])
    return best
def surface_distance(first,second):
    hit=edge_face_hit(first,second)
    if hit is None: hit=edge_face_hit(second,first)
    if hit is not None: return (0.,hit,hit,'intersection')
    a=point_face(first[0],second); b=point_face(second[0],first); c=edge_edge(first,second)
    options=[(*a,'Target vertex / candidate face'),(b[0],b[2],b[1],'Target face / candidate vertex'),(*c,'edge / edge')]
    return min(options,key=lambda item:item[0])
results=[]
calculation_start=time.time()
for name,geom in geometry.items():
    if name=='Target': continue
    res=surface_distance(geometry['Target'],geom)
    results.append((name,math.sqrt(res[0]),res[1].tolist(),res[2].tolist(),res[3]))
results.sort(key=lambda item:item[1])
print('elapsed_seconds',time.time()-calculation_start)
for result in results: print(result)