def edge_face_crossings(source,destination):
    edges=edge_candidates(source)
    edge_directions=edges[:,1]-edges[:,0]
    first=destination[:,1]-destination[:,0]
    second=destination[:,2]-destination[:,0]
    normals=np.cross(first,second)
    denominators=edge_directions@normals.T
    offsets=destination[None,:,0,:]-edges[:,None,0,:]
    numerators=np.einsum('efi,fi->ef',offsets,normals)
    parameter=np.divide(numerators,denominators,out=np.full_like(numerators,np.inf),where=abs(denominators)>1e-20)
    possible=np.argwhere((parameter>=0)&(parameter<=1))
    count=0
    for edge_index,face_index in possible:
        point=edges[edge_index,0]+parameter[edge_index,face_index]*edge_directions[edge_index]
        relative=point-destination[face_index,0]
        axis1=first[face_index]; axis2=second[face_index]
        dot00=axis1@axis1; dot01=axis1@axis2; dot11=axis2@axis2
        denom=dot00*dot11-dot01*dot01
        bary1=(dot11*(relative@axis1)-dot01*(relative@axis2))/denom
        bary2=(dot00*(relative@axis2)-dot01*(relative@axis1))/denom
        if bary1>=-1e-12 and bary2>=-1e-12 and bary1+bary2<=1+1e-12:
            count+=1
    return count
for name,tris in triangles.items():
    areas=np.linalg.norm(np.cross(tris[:,1]-tris[:,0],tris[:,2]-tris[:,0]),axis=1)
    print(name,'min_double_area_m2',float(areas.min()),'bounds_m',tris.reshape(-1,3).min(axis=0).tolist(),tris.reshape(-1,3).max(axis=0).tolist())
    if name!='Mesh_DDBB95':
        print('edge_face_intersections',edge_face_crossings(triangles['Mesh_DDBB95'],tris)+edge_face_crossings(tris,triangles['Mesh_DDBB95']))
print('scene_geometry_float64_coordinate_max_m',max(float(np.max(np.abs(tris))) for tris in triangles.values()))