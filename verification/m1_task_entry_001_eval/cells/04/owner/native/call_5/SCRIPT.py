def surface_distance(first, second):
    first_vertices,first_indices=first
    second_vertices,second_indices=second
    first_triangles=first_vertices[first_indices]
    second_triangles=second_vertices[second_indices]
    best=[float('inf'),None,None,None]
    def submit(distances, points_a, points_b, kind, reverse=False):
        flat_index=int(np.argmin(distances))
        distance=float(distances.flat[flat_index])
        if distance < best[0]:
            index=np.unravel_index(flat_index,distances.shape)
            point_a=np.broadcast_to(points_a,distances.shape+(3,))[index].copy()
            point_b=np.broadcast_to(points_b,distances.shape+(3,))[index].copy()
            best[:]=[distance,point_b if reverse else point_a,point_a if reverse else point_b,kind]
    def point_face(points,triangles,reverse):
        origin=triangles[:,0]
        edge_u=triangles[:,1]-origin
        edge_v=triangles[:,2]-origin
        normals=np.cross(edge_u,edge_v)
        norm_squared=np.einsum('ij,ij->i',normals,normals)
        relative=points[:,None,:]-origin[None,:,:]
        signed=np.einsum('pfi,fi->pf',relative,normals)/norm_squared[None,:]
        projected=points[:,None,:]-signed[:,:,None]*normals[None,:,:]
        offset=projected-origin[None,:,:]
        uu=np.einsum('ij,ij->i',edge_u,edge_u)
        uv=np.einsum('ij,ij->i',edge_u,edge_v)
        vv=np.einsum('ij,ij->i',edge_v,edge_v)
        pu=np.einsum('pfi,fi->pf',offset,edge_u)
        pv=np.einsum('pfi,fi->pf',offset,edge_v)
        denominator=uu*vv-uv*uv
        bary_u=(vv*pu-uv*pv)/denominator
        bary_v=(uu*pv-uv*pu)/denominator
        inside=(bary_u>=-1e-13)&(bary_v>=-1e-13)&(bary_u+bary_v<=1+1e-13)
        distance_squared=np.sum((points[:,None,:]-projected)**2,axis=2)
        submit(np.where(inside,distance_squared,np.inf),points[:,None,:],projected,'vertex-face',reverse)
    point_face(first_vertices,second_triangles,False)
    point_face(second_vertices,first_triangles,True)
    def edges(triangles):
        return triangles.reshape(-1,3),triangles[:,[1,2,0],:].reshape(-1,3)
    start_a,end_a=edges(first_triangles)
    start_b,end_b=edges(second_triangles)
    vector_a=end_a-start_a
    vector_b=end_b-start_b
    def points_segments(points,starts,vectors,reverse):
        relative=points[:,None,:]-starts[None,:,:]
        parameters=np.clip(np.einsum('psi,si->ps',relative,vectors)/np.einsum('si,si->s',vectors,vectors),0,1)
        projections=starts[None,:,:]+parameters[:,:,None]*vectors[None,:,:]
        submit(np.sum((points[:,None,:]-projections)**2,axis=2),points[:,None,:],projections,'vertex-edge',reverse)
    points_segments(first_vertices,start_b,vector_b,False)
    points_segments(second_vertices,start_a,vector_a,True)
    relative=start_a[:,None,:]-start_b[None,:,:]
    aa=np.einsum('ij,ij->i',vector_a,vector_a)[:,None]
    bb=np.einsum('ij,kj->ik',vector_a,vector_b)
    cc=np.einsum('ij,ij->i',vector_b,vector_b)[None,:]
    dd=np.einsum('abi,ai->ab',relative,vector_a)
    ee=np.einsum('abi,bi->ab',relative,vector_b)
    determinant=aa*cc-bb*bb
    safe=np.where(determinant>1e-28,determinant,1.0)
    parameter_a=(bb*ee-cc*dd)/safe
    parameter_b=(aa*ee-bb*dd)/safe
    eligible=(determinant>1e-28)&(parameter_a>=0)&(parameter_a<=1)&(parameter_b>=0)&(parameter_b<=1)
    points_a=start_a[:,None,:]+parameter_a[:,:,None]*vector_a[:,None,:]
    points_b=start_b[None,:,:]+parameter_b[:,:,None]*vector_b[None,:,:]
    submit(np.where(eligible,np.sum((points_a-points_b)**2,axis=2),np.inf),points_a,points_b,'edge-edge')
    def intersections(starts,vectors,triangles,reverse):
        edge_u=triangles[:,1]-triangles[:,0]
        edge_v=triangles[:,2]-triangles[:,0]
        cross=np.cross(vectors[:,None,:],edge_v[None,:,:])
        det=np.einsum('fi,sfi->sf',edge_u,cross)
        safe_det=np.where(np.abs(det)>1e-20,det,1.0)
        relative=starts[:,None,:]-triangles[None,:,0,:]
        bary_u=np.einsum('sfi,sfi->sf',relative,cross)/safe_det
        cross_second=np.cross(relative,edge_u[None,:,:])
        bary_v=np.einsum('si,sfi->sf',vectors,cross_second)/safe_det
        parameter=np.einsum('fi,sfi->sf',edge_v,cross_second)/safe_det
        hits=(np.abs(det)>1e-20)&(bary_u>=0)&(bary_v>=0)&(bary_u+bary_v<=1)&(parameter>=0)&(parameter<=1)
        if hits.any():
            points=starts[:,None,:]+parameter[:,:,None]*vectors[:,None,:]
            submit(np.where(hits,0.0,np.inf),points,points,'surface-intersection',reverse)
    intersections(start_a,vector_a,second_triangles,False)
    intersections(start_b,vector_b,first_triangles,True)
    return [math.sqrt(best[0]),best[1].tolist(),best[2].tolist(),best[3]]
results={}
for name,data in geometry.items():
    if name!='Mesh_D17AB2':
        results[name]=surface_distance(geometry['Mesh_D17AB2'],data)
for name,result in sorted(results.items(),key=lambda item:item[1][0]):
    print(name,'distance_mm',format(result[0]*1000,'.12f'),'target_witness_m',result[1],'other_witness_m',result[2],'feature',result[3])
print('tested_all_other_meshes',len(results),'target_triangles',len(geometry['Mesh_D17AB2'][1]))