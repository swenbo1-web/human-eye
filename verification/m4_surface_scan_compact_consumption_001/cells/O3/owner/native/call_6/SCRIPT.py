def reverse_intersects(first,second):
    first=first[:,None,:,:]; second=second[None,:,:,:]
    for index in range(3):
        start=first[...,index,:]; direction=first[...,(index+1)%3,:]-start
        edge1=second[...,1,:]-second[...,0,:]; edge2=second[...,2,:]-second[...,0,:]
        cross=np.cross(direction,edge2); determinant=np.sum(edge1*cross,axis=-1)
        inverse=np.divide(1.,determinant,out=np.zeros_like(determinant),where=abs(determinant)>1e-25)
        offset=start-second[...,0,:]; coord1=np.sum(offset*cross,axis=-1)*inverse
        cross2=np.cross(offset,edge1); coord2=np.sum(direction*cross2,axis=-1)*inverse
        parameter=np.sum(edge2*cross2,axis=-1)*inverse
        if np.any((abs(determinant)>1e-25)&(coord1>=0)&(coord2>=0)&(coord1+coord2<=1)&(parameter>=0)&(parameter<=1)): return True
    return False
compact_matches=[]
for first_name,second_name in itertools.combinations(sorted(mesh_triangles),2):
    first=mesh_triangles[first_name]; second=mesh_triangles[second_name]
    gap=np.maximum(0,np.maximum(first.min(axis=(0,1))-second.max(axis=(0,1)),second.min(axis=(0,1))-first.max(axis=(0,1))))
    if np.linalg.norm(gap)>0.002: continue
    distance=0. if reverse_intersects(second,first) else surface_distance(first,second)
    if distance<=0.002: compact_matches.append((first_name,second_name,distance*1000))
print('count',len(compact_matches))
for first_name,second_name,distance in compact_matches: print(first_name,second_name,format(distance,'.9f'))