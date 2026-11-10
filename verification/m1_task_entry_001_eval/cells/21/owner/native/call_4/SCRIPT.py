def projected_vertex_faces(vertices, triangles):
    base=triangles[:,0]; side1=triangles[:,1]-base; side2=triangles[:,2]-base
    normal=np.cross(side1,side2); norm2=np.einsum('ij,ij->i',normal,normal)
    delta=vertices[:,None,:]-base[None,:,:]
    signed=np.einsum('vti,ti->vt',delta,normal)
    projected=vertices[:,None,:]-np.divide(signed,norm2[None,:],out=np.zeros_like(signed),where=norm2[None,:]>0)[:,:,None]*normal[None,:,:]
    rel=projected-base[None,:,:]
    aa=np.einsum('ij,ij->i',side1,side1); ab=np.einsum('ij,ij->i',side1,side2); bb=np.einsum('ij,ij->i',side2,side2)
    ra=np.einsum('vti,ti->vt',rel,side1); rb=np.einsum('vti,ti->vt',rel,side2)
    det=aa*bb-ab*ab
    u=np.divide(bb*ra-ab*rb,det[None,:],out=np.zeros_like(ra),where=det[None,:]>0)
    v=np.divide(aa*rb-ab*ra,det[None,:],out=np.zeros_like(rb),where=det[None,:]>0)
    valid=(norm2[None,:]>0)&(u>=0)&(v>=0)&(u+v<=1)
    dist2=np.where(valid,np.sum((vertices[:,None,:]-projected)**2,axis=2),np.inf)
    index=np.unravel_index(np.argmin(dist2),dist2.shape)
    return float(dist2[index]),vertices[index[0]].copy(),projected[index].copy(),('vertex-face',int(index[0]),int(index[1]))
def vertex_edges(vertices, edges):
    direction=edges[:,1]-edges[:,0]; denom=np.sum(direction*direction,axis=1)
    rel=vertices[:,None,:]-edges[None,:,0,:]
    t=np.clip(np.divide(np.einsum('vei,ei->ve',rel,direction),denom[None,:],out=np.zeros(rel.shape[:2]),where=denom[None,:]>0),0,1)
    q=edges[None,:,0,:]+t[:,:,None]*direction[None,:,:]
    d2=np.sum((vertices[:,None,:]-q)**2,axis=2)
    idx=np.unravel_index(np.argmin(d2),d2.shape)
    return float(d2[idx]),vertices[idx[0]].copy(),q[idx].copy(),('vertex-edge',int(idx[0]),int(idx[1]))
def interior_edges(edges_a,edges_b):
    first=edges_a[:,1]-edges_a[:,0]; second=edges_b[:,1]-edges_b[:,0]
    delta=edges_a[:,None,0,:]-edges_b[None,:,0,:]
    aa=np.sum(first*first,axis=1)[:,None]; bb=first@second.T; cc=np.sum(second*second,axis=1)[None,:]
    dd=np.einsum('abi,ai->ab',delta,first); ee=np.einsum('abi,bi->ab',delta,second)
    determinant=aa*cc-bb*bb
    s=np.divide(bb*ee-cc*dd,determinant,out=np.zeros_like(dd),where=determinant>0)
    t=np.divide(aa*ee-bb*dd,determinant,out=np.zeros_like(dd),where=determinant>0)
    valid=(determinant>0)&(s>=0)&(s<=1)&(t>=0)&(t<=1)
    p=edges_a[:,None,0,:]+s[:,:,None]*first[:,None,:]
    q=edges_b[None,:,0,:]+t[:,:,None]*second[None,:,:]
    dist2=np.where(valid,np.sum((p-q)**2,axis=2),np.inf)
    idx=np.unravel_index(np.argmin(dist2),dist2.shape)
    return float(dist2[idx]),p[idx].copy(),q[idx].copy(),('edge-edge',int(idx[0]),int(idx[1]),float(s[idx]),float(t[idx]))
def unique_edges(faces):
    return np.unique(np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
_target_vertices,_target_faces=_geo['Mesh_DDBB95']
_target_triangles=_target_vertices[_target_faces]
_target_edgeids=unique_edges(_target_faces)
_target_edges=_target_vertices[_target_edgeids]
_results={}
for name,(vertices,faces) in _geo.items():
    if name=='Mesh_DDBB95': continue
    triangles=vertices[faces]; edgeids=unique_edges(faces); edges=vertices[edgeids]
    candidates=[projected_vertex_faces(_target_vertices,triangles),vertex_edges(_target_vertices,edges),interior_edges(_target_edges,edges)]
    for fn,args in [(projected_vertex_faces,(vertices,_target_triangles)),(vertex_edges,(vertices,_target_edges))]:
        distance2,point_other,point_target,feature=fn(*args)
        candidates.append((distance2,point_target,point_other,('reversed',feature)))
    best=min(candidates,key=lambda item:item[0]); _results[name]=best
    print(name,'distance_mm',format(math.sqrt(best[0])*1000,'.12f'),'target_point_m',best[1].tolist(),'other_point_m',best[2].tolist(),'feature',best[3], 'unique_edges',len(edgeids))
print('bbox_z_separation_mm',min(v[:,2].min() for name,(v,f) in _geo.items() if name!='Mesh_DDBB95')*1000-_target_vertices[:,2].max()*1000)
