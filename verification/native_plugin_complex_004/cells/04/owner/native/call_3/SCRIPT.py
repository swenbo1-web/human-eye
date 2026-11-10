import hashlib
start_time=time.perf_counter()
depsgraph=bpy.context.evaluated_depsgraph_get()
geometry={}
for obj in meshes:
    evaluated=obj.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    mesh.calc_loop_triangles()
    local=np.array([vertex.co[:] for vertex in mesh.vertices],dtype=np.float64)
    matrix=np.array(evaluated.matrix_world,dtype=np.float64)
    world=local @ matrix[:3,:3].T + matrix[:3,3]
    indices=np.array([tri.vertices[:] for tri in mesh.loop_triangles],dtype=np.int64).reshape((-1,3))
    edge_indices=np.unique(np.sort(np.concatenate([indices[:,[0,1]],indices[:,[1,2]],indices[:,[2,0]]]),axis=1),axis=0)
    geometry[obj.name]={'vertices':world,'triangles':world[indices],'edges':world[edge_indices]}
    evaluated.to_mesh_clear()

def vertex_triangle_min(vertices,triangles):
    points=vertices[:,None,:]
    base=triangles[None,:,0,:]
    side1=triangles[None,:,1,:]-base
    side2=triangles[None,:,2,:]-base
    normal=np.cross(side1,side2)
    normal2=np.sum(normal*normal,axis=-1)
    height=np.sum((points-base)*normal,axis=-1)/np.where(normal2>0,normal2,1)
    projection=points-height[...,None]*normal
    relative=projection-base
    dot11=np.sum(side1*side1,axis=-1); dot12=np.sum(side1*side2,axis=-1); dot22=np.sum(side2*side2,axis=-1)
    dotp1=np.sum(relative*side1,axis=-1); dotp2=np.sum(relative*side2,axis=-1)
    denominator=dot11*dot22-dot12*dot12
    bary1=(dot22*dotp1-dot12*dotp2)/np.where(denominator!=0,denominator,1)
    bary2=(dot11*dotp2-dot12*dotp1)/np.where(denominator!=0,denominator,1)
    valid=(bary1>=0)&(bary2>=0)&(bary1+bary2<=1)&(normal2>0)
    distances=np.where(valid,np.sum((points-projection)**2,axis=-1),np.inf)
    closest=projection.copy()
    for corner in range(3):
        edge_start=triangles[None,:,corner,:]
        edge_delta=triangles[None,:,(corner+1)%3,:]-edge_start
        edge_length2=np.sum(edge_delta*edge_delta,axis=-1)
        fraction=np.clip(np.sum((points-edge_start)*edge_delta,axis=-1)/np.where(edge_length2>0,edge_length2,1),0,1)
        edge_point=edge_start+fraction[...,None]*edge_delta
        squared=np.sum((points-edge_point)**2,axis=-1)
        replace=squared<distances
        closest=np.where(replace[...,None],edge_point,closest)
        distances=np.minimum(distances,squared)
    index=np.unravel_index(np.argmin(distances),distances.shape)
    return float(distances[index]), vertices[index[0]].copy(),closest[index].copy()

def edge_edge_min(edges1,edges2):
    base1=edges1[:,None,0,:]; base2=edges2[None,:,0,:]
    delta1=edges1[:,None,1,:]-base1; delta2=edges2[None,:,1,:]-base2
    offset=base1-base2
    aa=np.sum(delta1*delta1,axis=-1); bb=np.sum(delta1*delta2,axis=-1); cc=np.sum(delta2*delta2,axis=-1)
    dd=np.sum(delta1*offset,axis=-1); ee=np.sum(delta2*offset,axis=-1)
    denominator=aa*cc-bb*bb
    param1=(bb*ee-cc*dd)/np.where(denominator!=0,denominator,1)
    param2=(aa*ee-bb*dd)/np.where(denominator!=0,denominator,1)
    valid=(denominator>1e-28)&(param1>=0)&(param1<=1)&(param2>=0)&(param2<=1)
    point1=base1+param1[...,None]*delta1; point2=base2+param2[...,None]*delta2
    squared=np.where(valid,np.sum((point1-point2)**2,axis=-1),np.inf)
    index=np.unravel_index(np.argmin(squared),squared.shape)
    return float(squared[index]),point1[index].copy(),point2[index].copy()

def edge_face_intersection(edges,triangles):
    origin=edges[:,None,0,:]; direction=edges[:,None,1,:]-origin
    base=triangles[None,:,0,:]; side1=triangles[None,:,1,:]-base; side2=triangles[None,:,2,:]-base
    cross=np.cross(direction,side2); determinant=np.sum(side1*cross,axis=-1)
    inverse=1/np.where(determinant!=0,determinant,1)
    offset=origin-base
    bary1=np.sum(offset*cross,axis=-1)*inverse
    second_cross=np.cross(offset,side1)
    bary2=np.sum(direction*second_cross,axis=-1)*inverse
    param=np.sum(side2*second_cross,axis=-1)*inverse
    valid=(np.abs(determinant)>1e-25)&(bary1>=0)&(bary2>=0)&(bary1+bary2<=1)&(param>=0)&(param<=1)
    if np.any(valid):
        index=tuple(np.argwhere(valid)[0])
        return (origin+param[...,None]*direction)[index].copy()
    return None

target=geometry['Target']
results=[]
for name,candidate in geometry.items():
    if name=='Target': continue
    hit=edge_face_intersection(target['edges'],candidate['triangles'])
    if hit is None: hit=edge_face_intersection(candidate['edges'],target['triangles'])
    if hit is not None:
        best=(0.0,hit,hit)
    else:
        forward=vertex_triangle_min(target['vertices'],candidate['triangles'])
        reverse=vertex_triangle_min(candidate['vertices'],target['triangles'])
        reverse=(reverse[0],reverse[2],reverse[1])
        edges_result=edge_edge_min(target['edges'],candidate['edges'])
        best=min([forward,reverse,edges_result],key=lambda item:item[0])
    results.append({'name':name,'distance':math.sqrt(best[0]),'target_witness':best[1].tolist(),'candidate_witness':best[2].tolist()})
results.sort(key=lambda item:item['distance'])
print('geometry_count',len(geometry),'candidate_count',len(results),'elapsed',time.perf_counter()-start_time)
print('evaluated_mesh_sizes',[(name,len(data['triangles']),len(data['edges'])) for name,data in geometry.items()][:3])
print('ranked_distances',[(row['name'],round(row['distance'],12)) for row in results])
print('nearest_witness',results[0])
print('nonfinite', [row['name'] for row in results if not math.isfinite(row['distance'])])
