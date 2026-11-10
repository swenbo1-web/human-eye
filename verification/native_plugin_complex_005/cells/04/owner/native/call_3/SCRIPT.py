def capture_geometry():
    depsgraph=bpy.context.evaluated_depsgraph_get()
    result={}
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH': continue
        evaluated=obj.evaluated_get(depsgraph)
        mesh=evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            local=np.array([tuple(vertex.co) for vertex in mesh.vertices],dtype=np.float64)
            matrix=np.array(evaluated.matrix_world,dtype=np.float64)
            vertices=local@matrix[:3,:3].T+matrix[:3,3]
            triangles=np.array([tuple(triangle.vertices) for triangle in mesh.loop_triangles],dtype=np.int64)
            edges=np.unique(np.sort(np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]]),axis=1),axis=0)
            result[obj.name]=(vertices,triangles,edges)
        finally: evaluated.to_mesh_clear()
    return result
geometry=capture_geometry()
def point_triangles(points, triangles):
    origin=triangles[:,0]; first=triangles[:,1]-origin; second=triangles[:,2]-origin
    normal=np.cross(first,second); norm2=np.sum(normal*normal,axis=-1)
    offset=points[:,None,:]-origin[None,:,:]
    height=np.einsum('ptk,tk->pt',offset,normal)/np.where(norm2>0,norm2,1)[None,:]
    projected=points[:,None,:]-height[:,:,None]*normal[None,:,:]
    relative=projected-origin[None,:,:]
    aa=np.sum(first*first,axis=-1); ab=np.sum(first*second,axis=-1); bb=np.sum(second*second,axis=-1)
    ar=np.einsum('ptk,tk->pt',relative,first); br=np.einsum('ptk,tk->pt',relative,second)
    denom=aa*bb-ab*ab; safe=np.where(denom!=0,denom,1)
    bary_first=(bb*ar-ab*br)/safe; bary_second=(aa*br-ab*ar)/safe
    valid=(bary_first>=0)&(bary_second>=0)&(bary_first+bary_second<=1)&(norm2[None,:]>0)
    distances=np.where(valid,np.sum((points[:,None,:]-projected)**2,axis=-1),np.inf)
    for edge_index in range(3):
        edge_origin=triangles[:,edge_index]; edge_vector=triangles[:,(edge_index+1)%3]-edge_origin
        length2=np.sum(edge_vector*edge_vector,axis=-1)
        param=np.clip(np.einsum('ptk,tk->pt',points[:,None,:]-edge_origin,edge_vector)/np.where(length2>0,length2,1),0,1)
        closest=edge_origin[None,:,:]+param[:,:,None]*edge_vector[None,:,:]
        edge_distance=np.sum((points[:,None,:]-closest)**2,axis=-1)
        better=edge_distance<distances
        distances=np.where(better,edge_distance,distances)
        projected=np.where(better[:,:,None],closest,projected)
    index=np.unravel_index(np.argmin(distances),distances.shape)
    return float(distances[index]),points[index[0]].copy(),projected[index].copy(),index

def edge_edge_interior(first_edges,second_edges):
    origin_first=first_edges[:,0]; vector_first=first_edges[:,1]-origin_first
    origin_second=second_edges[:,0]; vector_second=second_edges[:,1]-origin_second
    offset=origin_first[:,None,:]-origin_second[None,:,:]
    aa=np.sum(vector_first*vector_first,axis=-1)[:,None]
    bb=vector_first@vector_second.T
    cc=np.sum(vector_second*vector_second,axis=-1)[None,:]
    dd=np.einsum('ijk,ik->ij',offset,vector_first)
    ee=np.einsum('ijk,jk->ij',offset,vector_second)
    determinant=aa*cc-bb*bb
    safe=np.where(determinant>0,determinant,1)
    param_first=(bb*ee-cc*dd)/safe
    param_second=(aa*ee-bb*dd)/safe
    valid=(determinant>0)&(param_first>=0)&(param_first<=1)&(param_second>=0)&(param_second<=1)
    closest_first=origin_first[:,None,:]+param_first[:,:,None]*vector_first[:,None,:]
    closest_second=origin_second[None,:,:]+param_second[:,:,None]*vector_second[None,:,:]
    distances=np.where(valid,np.sum((closest_first-closest_second)**2,axis=-1),np.inf)
    index=np.unravel_index(np.argmin(distances),distances.shape)
    return float(distances[index]),closest_first[index].copy(),closest_second[index].copy(),index

def crossing(edges,triangles):
    origins=triangles[:,0]; first=triangles[:,1]-origins; second=triangles[:,2]-origins
    normals=np.cross(first,second)
    directions=edges[:,1]-edges[:,0]
    denominator=directions@normals.T
    numerator=np.einsum('ijk,jk->ij',origins[None,:,:]-edges[:,0,None,:],normals)
    param=numerator/np.where(denominator!=0,denominator,1)
    intersection=edges[:,0,None,:]+param[:,:,None]*directions[:,None,:]
    relative=intersection-origins[None,:,:]
    aa=np.sum(first*first,axis=-1); ab=np.sum(first*second,axis=-1); bb=np.sum(second*second,axis=-1)
    ar=np.einsum('ijk,jk->ij',relative,first); br=np.einsum('ijk,jk->ij',relative,second)
    determinant=aa*bb-ab*ab; safe=np.where(determinant!=0,determinant,1)
    bary_first=(bb*ar-ab*br)/safe; bary_second=(aa*br-ab*ar)/safe
    valid=(denominator!=0)&(determinant[None,:]>0)&(param>=0)&(param<=1)&(bary_first>=0)&(bary_second>=0)&(bary_first+bary_second<=1)
    hits=np.argwhere(valid)
    if len(hits):
        index=tuple(hits[0]); point=intersection[index].copy()
        return (0.,point,point,index)
    return None

target_vertices,target_indices,target_edge_indices=geometry['Target']
target_triangles=target_vertices[target_indices]; target_edges=target_vertices[target_edge_indices]
results=[]
for name,(vertices,indices,edge_indices) in geometry.items():
    if name=='Target': continue
    triangles=vertices[indices]; edges=vertices[edge_indices]
    choices=[('target_vertex_to_face',point_triangles(target_vertices,triangles)),('candidate_vertex_to_face',point_triangles(vertices,target_triangles)),('edge_to_edge',edge_edge_interior(target_edges,edges))]
    for label,hit in [('target_edge_crossing',crossing(target_edges,triangles)),('candidate_edge_crossing',crossing(edges,target_triangles))]:
        if hit is not None: choices.append((label,hit))
    feature,record=min(choices,key=lambda entry:entry[1][0])
    results.append((float(np.sqrt(record[0])),name,feature,record))
results.sort(key=lambda entry:entry[0])
print('evaluated_meshes',len(geometry),'candidate_count',len(results))
print('target_vertices_triangles_edges',len(target_vertices),len(target_indices),len(target_edge_indices))
print('distance_results_m',[(name,format(distance,'.12f'),feature) for distance,name,feature,record in results])
print('closest_details',[(name,feature,record[1].tolist(),record[2].tolist(),record[3]) for distance,name,feature,record in results[:3]])
print('elapsed_seconds',time.time()-start_time)