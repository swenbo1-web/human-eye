import numpy as np, itertools
mesh_triangles={}
depsgraph=bpy.context.evaluated_depsgraph_get()
for obj in bpy.context.scene.objects:
    if obj.type!='MESH': continue
    evaluated=obj.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    mesh.calc_loop_triangles()
    vertices=np.array([tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices])
    mesh_triangles[obj.name]=vertices[np.array([tuple(triangle.vertices) for triangle in mesh.loop_triangles])]
    evaluated.to_mesh_clear()
def point_triangle_dist(points, triangles):
    edge1=triangles[...,1,:]-triangles[...,0,:]; edge2=triangles[...,2,:]-triangles[...,0,:]
    offset=points-triangles[...,0,:]
    normal=np.cross(edge1,edge2); norm2=np.sum(normal*normal,axis=-1)
    signed=np.sum(offset*normal,axis=-1)
    projected=offset-normal*(signed/np.maximum(norm2,1e-300))[...,None]
    dot11=np.sum(edge1*edge1,axis=-1); dot12=np.sum(edge1*edge2,axis=-1); dot22=np.sum(edge2*edge2,axis=-1)
    dotp1=np.sum(projected*edge1,axis=-1); dotp2=np.sum(projected*edge2,axis=-1)
    denominator=dot11*dot22-dot12*dot12
    coord1=(dot22*dotp1-dot12*dotp2)/np.maximum(denominator,1e-300)
    coord2=(dot11*dotp2-dot12*dotp1)/np.maximum(denominator,1e-300)
    inside=(coord1>=0)&(coord2>=0)&(coord1+coord2<=1)&(norm2>0)
    result=np.where(inside,signed*signed/np.maximum(norm2,1e-300),np.inf)
    for index in range(3):
        start=triangles[...,index,:]; direction=triangles[...,(index+1)%3,:]-start
        parameter=np.clip(np.sum((points-start)*direction,axis=-1)/np.maximum(np.sum(direction*direction,axis=-1),1e-300),0,1)
        delta=points-start-parameter[...,None]*direction
        result=np.minimum(result,np.sum(delta*delta,axis=-1))
    return result
def surface_distance(first,second):
    first=first[:,None,:,:]; second=second[None,:,:,:]
    best=np.inf
    for index in range(3):
        best=min(best,float(np.min(point_triangle_dist(first[...,index,:],second))),float(np.min(point_triangle_dist(second[...,index,:],first))))
    for index in range(3):
        start=first[...,index,:]; direction=first[...,(index+1)%3,:]-start
        edge1=second[...,1,:]-second[...,0,:]; edge2=second[...,2,:]-second[...,0,:]
        cross=np.cross(direction,edge2); determinant=np.sum(edge1*cross,axis=-1)
        inverse=np.divide(1.,determinant,out=np.zeros_like(determinant),where=abs(determinant)>1e-25)
        offset=start-second[...,0,:]; coord1=np.sum(offset*cross,axis=-1)*inverse
        cross2=np.cross(offset,edge1); coord2=np.sum(direction*cross2,axis=-1)*inverse
        parameter=np.sum(edge2*cross2,axis=-1)*inverse
        if np.any((abs(determinant)>1e-25)&(coord1>=0)&(coord2>=0)&(coord1+coord2<=1)&(parameter>=0)&(parameter<=1)): return 0.
        for other in range(3):
            other_start=second[...,other,:]; other_direction=second[...,(other+1)%3,:]-other_start
            offset=start-other_start
            dot11=np.sum(direction*direction,axis=-1); dot12=np.sum(direction*other_direction,axis=-1); dot22=np.sum(other_direction*other_direction,axis=-1)
            dot1=np.sum(direction*offset,axis=-1); dot2=np.sum(other_direction*offset,axis=-1)
            denominator=dot11*dot22-dot12*dot12
            param1=np.divide(dot12*dot2-dot22*dot1,denominator,out=np.zeros_like(denominator),where=abs(denominator)>1e-30)
            param2=(dot12*param1+dot2)/np.maximum(dot22,1e-300)
            valid=(param1>=0)&(param1<=1)&(param2>=0)&(param2<=1)&(abs(denominator)>1e-30)
            delta=offset+param1[...,None]*direction-param2[...,None]*other_direction
            best=min(best,float(np.min(np.where(valid,np.sum(delta*delta,axis=-1),np.inf))))
    return float(np.sqrt(best))
compact_matches=[]
for first_name,second_name in itertools.combinations(sorted(mesh_triangles),2):
    first=mesh_triangles[first_name]; second=mesh_triangles[second_name]
    gap=np.maximum(0,np.maximum(first.min(axis=(0,1))-second.max(axis=(0,1)),second.min(axis=(0,1))-first.max(axis=(0,1))))
    if np.linalg.norm(gap)>0.002: continue
    distance=surface_distance(first,second)
    if distance<=0.002: compact_matches.append((first_name,second_name,distance*1000))
print('count',len(compact_matches))
for first_name,second_name,distance in compact_matches: print(first_name,second_name,format(distance,'.9f'))