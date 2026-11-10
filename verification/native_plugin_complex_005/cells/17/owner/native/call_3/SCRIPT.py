import hashlib
started=time.perf_counter()
deps=bpy.context.evaluated_depsgraph_get()
def read_geometry(obj):
    ev=obj.evaluated_get(deps)
    mesh=ev.to_mesh()
    try:
        mesh.calc_loop_triangles()
        local=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64).reshape(-1,3)
        matrix=np.array(ev.matrix_world,dtype=np.float64)
        vertices=local@matrix[:3,:3].T+matrix[:3,3]
        faces=np.array([tri.vertices[:] for tri in mesh.loop_triangles],dtype=np.int64).reshape(-1,3)
        edges=np.unique(np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
        return vertices,faces,edges
    finally: ev.to_mesh_clear()
geometry={o.name:read_geometry(o) for o in meshes}
print('evaluated_geometry',[(name,len(v),len(f),len(e)) for name,(v,f,e) in geometry.items()])
def point_segment_pairs(points, starts, ends):
    direction=ends-starts
    denominator=np.einsum('ij,ij->i',direction,direction)
    numerator=np.einsum('ijk,jk->ij',points[:,None,:]-starts[None,:,:],direction)
    ratio=np.divide(numerator,denominator[None,:],out=np.zeros_like(numerator),where=denominator[None,:]>0)
    ratio=np.clip(ratio,0,1)
    closest=starts[None,:,:]+ratio[:,:,None]*direction[None,:,:]
    squared=np.sum((points[:,None,:]-closest)**2,axis=2)
    index=np.unravel_index(np.argmin(squared),squared.shape)
    return float(squared[index]),points[index[0]].copy(),closest[index].copy()
def point_face_pairs(points, triangles):
    starts=triangles[:,0]; axis1=triangles[:,1]-starts; axis2=triangles[:,2]-starts
    normals=np.cross(axis1,axis2); normal2=np.sum(normals**2,axis=1)
    offset=points[:,None,:]-starts[None,:,:]
    signed=np.einsum('ijk,jk->ij',offset,normals)
    heights=np.divide(signed,normal2[None,:],out=np.zeros_like(signed),where=normal2[None,:]>0)
    proj=points[:,None,:]-heights[:,:,None]*normals[None,:,:]
    relative=proj-starts[None,:,:]
    cross1=np.cross(relative,axis2[None,:,:]); cross2=np.cross(axis1[None,:,:],relative)
    bary1=np.divide(np.einsum('ijk,jk->ij',cross1,normals),normal2[None,:],out=np.full_like(signed,np.nan),where=normal2[None,:]>0)
    bary2=np.divide(np.einsum('ijk,jk->ij',cross2,normals),normal2[None,:],out=np.full_like(signed,np.nan),where=normal2[None,:]>0)
    inside=(bary1>=0)&(bary2>=0)&(bary1+bary2<=1)&(normal2[None,:]>0)
    squared=np.where(inside,np.sum((points[:,None,:]-proj)**2,axis=2),np.inf)
    index=np.unravel_index(np.argmin(squared),squared.shape)
    best=(float(squared[index]),points[index[0]].copy(),proj[index].copy())
    for edge_index in range(3):
        candidate=point_segment_pairs(points,triangles[:,edge_index],triangles[:,(edge_index+1)%3])
        if candidate[0]<best[0]: best=candidate
    return best
def segment_pairs(first,second):
    start1=first[:,0]; start2=second[:,0]
    direction1=first[:,1]-start1; direction2=second[:,1]-start2
    delta=start1[:,None,:]-start2[None,:,:]
    aa=np.sum(direction1**2,axis=1)[:,None]; cc=np.sum(direction2**2,axis=1)[None,:]
    bb=direction1@direction2.T
    dd=np.einsum('ijk,ik->ij',delta,direction1); ee=np.einsum('ijk,jk->ij',delta,direction2)
    determinant=aa*cc-bb*bb
    valid=determinant>1e-28*aa*cc
    param1=np.divide(bb*ee-cc*dd,determinant,out=np.full_like(bb,np.nan),where=valid)
    param2=np.divide(aa*ee-bb*dd,determinant,out=np.full_like(bb,np.nan),where=valid)
    inside=valid&(param1>=0)&(param1<=1)&(param2>=0)&(param2<=1)
    closest1=start1[:,None,:]+param1[:,:,None]*direction1[:,None,:]
    closest2=start2[None,:,:]+param2[:,:,None]*direction2[None,:,:]
    squared=np.where(inside,np.sum((closest1-closest2)**2,axis=2),np.inf)
    index=np.unravel_index(np.argmin(squared),squared.shape)
    best=(float(squared[index]),closest1[index].copy(),closest2[index].copy())
    for endpoint in range(2):
        candidate=point_segment_pairs(first[:,endpoint],second[:,0],second[:,1])
        if candidate[0]<best[0]: best=candidate
        candidate=point_segment_pairs(second[:,endpoint],first[:,0],first[:,1])
        if candidate[0]<best[0]: best=(candidate[0],candidate[2],candidate[1])
    return best
def crossing(segments,triangles):
    starts=segments[:,0]; directions=segments[:,1]-starts
    base=triangles[:,0]; axis1=triangles[:,1]-base; axis2=triangles[:,2]-base
    normals=np.cross(axis1,axis2); normal2=np.sum(normals**2,axis=1)
    den=directions@normals.T
    numerator=np.einsum('ijk,jk->ij',base[None,:,:]-starts[:,None,:],normals)
    parameter=np.divide(numerator,den,out=np.full_like(den,np.nan),where=den!=0)
    hits=starts[:,None,:]+parameter[:,:,None]*directions[:,None,:]
    relative=hits-base[None,:,:]
    bary1=np.divide(np.einsum('ijk,jk->ij',np.cross(relative,axis2[None,:,:]),normals),normal2[None,:],out=np.full_like(den,np.nan),where=normal2[None,:]>0)
    bary2=np.divide(np.einsum('ijk,jk->ij',np.cross(axis1[None,:,:],relative),normals),normal2[None,:],out=np.full_like(den,np.nan),where=normal2[None,:]>0)
    mask=(parameter>=0)&(parameter<=1)&(bary1>=0)&(bary2>=0)&(bary1+bary2<=1)
    indices=np.argwhere(mask)
    if len(indices):
        index=tuple(indices[0]); return (0.0,hits[index].copy(),hits[index].copy())
    return None
target_vertices,target_faces,target_edges=geometry['Target']
target_triangles=target_vertices[target_faces]; target_segments=target_vertices[target_edges]
results=[]
for name,(vertices,faces,edges) in geometry.items():
    if name=='Target': continue
    triangles=vertices[faces]; segments=vertices[edges]
    candidates=[point_face_pairs(target_vertices,triangles)]
    reverse=point_face_pairs(vertices,target_triangles)
    candidates.append((reverse[0],reverse[2],reverse[1]))
    candidates.append(segment_pairs(target_segments,segments))
    for cross in (crossing(target_segments,triangles),crossing(segments,target_triangles)):
        if cross is not None: candidates.append(cross)
    best=min(candidates,key=lambda entry:entry[0])
    results.append((float(np.sqrt(best[0])),name,best[1],best[2]))
results.sort(key=lambda entry:entry[0])
print('ALL_DISTANCES_M')
for distance,name,point1,point2 in results: print(name,format(distance,'.12f'))
print('WINNER_POINTS',results[0][1],results[0][2].tolist(),results[0][3].tolist())
print('processed',len(results),'finite',all(np.isfinite(row[0]) for row in results),'elapsed_s',time.perf_counter()-started)
print('target_bounds',target_vertices.min(axis=0).tolist(),target_vertices.max(axis=0).tolist())
