import math
for name in geometry:
    evaluated=bpy.data.objects[name].evaluated_get(depsgraph)
    mesh=evaluated.to_mesh(); mesh.calc_loop_triangles()
    local=np.array([tuple(vertex.co) for vertex in mesh.vertices],dtype=np.float64)
    matrix=np.array(evaluated.matrix_world,dtype=np.float64)
    vertices=local @ matrix[:3,:3].T+matrix[:3,3]
    triangles=np.array([tuple(triangle.vertices) for triangle in mesh.loop_triangles],dtype=np.int64)
    geometry[name]=(vertices,triangles)
    evaluated.to_mesh_clear()

def point_segment(point, start, end):
    direction=end-start
    denominator=np.dot(direction,direction)
    factor=np.clip(np.dot(point-start,direction)/denominator,0.,1.) if denominator else 0.
    return start+factor*direction

def point_triangle(point,triangle):
    start,second,third=triangle
    first_edge=second-start; second_edge=third-start
    normal=np.cross(first_edge,second_edge)
    normal_squared=np.dot(normal,normal)
    candidates=[point_segment(point,triangle[index],triangle[(index+1)%3]) for index in range(3)]
    if normal_squared>1e-30:
        projected=point-normal*(np.dot(point-start,normal)/normal_squared)
        relative=projected-start
        gram=np.array([[np.dot(first_edge,first_edge),np.dot(first_edge,second_edge)],[np.dot(first_edge,second_edge),np.dot(second_edge,second_edge)]])
        bary=np.linalg.solve(gram,np.array([np.dot(relative,first_edge),np.dot(relative,second_edge)]))
        if bary[0]>=-1e-13 and bary[1]>=-1e-13 and bary.sum()<=1+1e-13:
            candidates.append(projected)
    return min(candidates,key=lambda candidate:np.dot(point-candidate,point-candidate))

def segment_segment(start_a,end_a,start_b,end_b):
    direction_a=end_a-start_a; direction_b=end_b-start_b; relative=start_a-start_b
    aa=np.dot(direction_a,direction_a); bb=np.dot(direction_a,direction_b); cc=np.dot(direction_b,direction_b)
    dd=np.dot(direction_a,relative); ee=np.dot(direction_b,relative)
    candidates=[(start_a,point_segment(start_a,start_b,end_b)),(end_a,point_segment(end_a,start_b,end_b)),(point_segment(start_b,start_a,end_a),start_b),(point_segment(end_b,start_a,end_a),end_b)]
    denominator=aa*cc-bb*bb
    if denominator>1e-28:
        factor_a=(bb*ee-cc*dd)/denominator
        factor_b=(aa*ee-bb*dd)/denominator
        if 0<=factor_a<=1 and 0<=factor_b<=1:
            candidates.append((start_a+factor_a*direction_a,start_b+factor_b*direction_b))
    return min(candidates,key=lambda pair:np.sum((pair[0]-pair[1])**2))

def segment_triangle(start,end,triangle):
    edge_a=triangle[1]-triangle[0]; edge_b=triangle[2]-triangle[0]; direction=end-start
    crossed=np.cross(direction,edge_b); determinant=np.dot(edge_a,crossed)
    if abs(determinant)<1e-22:return None
    relative=start-triangle[0]; factor_u=np.dot(relative,crossed)/determinant
    crossed2=np.cross(relative,edge_a); factor_v=np.dot(direction,crossed2)/determinant
    factor_t=np.dot(edge_b,crossed2)/determinant
    if -1e-12<=factor_u and -1e-12<=factor_v and factor_u+factor_v<=1+1e-12 and -1e-12<=factor_t<=1+1e-12:
        return start+factor_t*direction
    return None

def winding(point,vertices,triangles):
    vectors=vertices[triangles]-point
    norms=np.linalg.norm(vectors,axis=2)
    numerator=np.einsum('ij,ij->i',vectors[:,0],np.cross(vectors[:,1],vectors[:,2]))
    denominator=norms.prod(axis=1)+np.einsum('ij,ij->i',vectors[:,0],vectors[:,1])*norms[:,2]+np.einsum('ij,ij->i',vectors[:,1],vectors[:,2])*norms[:,0]+np.einsum('ij,ij->i',vectors[:,2],vectors[:,0])*norms[:,1]
    return np.sum(2*np.arctan2(numerator,denominator))/(4*np.pi)

results={}
vertices_a,indices_a=geometry['Target']
for name in ('Part_A','Part_B','Part_C'):
    vertices_b,indices_b=geometry[name]
    best=(float('inf'),None,None,None)
    crossings=[]
    for index_a,tri_a in enumerate(vertices_a[indices_a]):
        for index_b,tri_b in enumerate(vertices_b[indices_b]):
            candidates=[]
            for point in tri_a:candidates.append((point,point_triangle(point,tri_b)))
            for point in tri_b:candidates.append((point_triangle(point,tri_a),point))
            for edge_a in range(3):
                hit=segment_triangle(tri_a[edge_a],tri_a[(edge_a+1)%3],tri_b)
                if hit is not None: crossings.append(hit); candidates.append((hit,hit))
                hit=segment_triangle(tri_b[edge_a],tri_b[(edge_a+1)%3],tri_a)
                if hit is not None: crossings.append(hit); candidates.append((hit,hit))
                for edge_b in range(3):
                    candidates.append(segment_segment(tri_a[edge_a],tri_a[(edge_a+1)%3],tri_b[edge_b],tri_b[(edge_b+1)%3]))
            for point_a,point_b in candidates:
                distance=np.linalg.norm(point_a-point_b)
                if distance<best[0]:best=(distance,point_a.copy(),point_b.copy(),(index_a,index_b))
    results[name]=best
    print(name,'distance_m',format(best[0],'.15f'),'distance_mm',format(best[0]*1000,'.12f'),'Target_point',best[1].tolist(),'Part_point',best[2].tolist(),'triangles',best[3],'crossings',len(crossings))
    print('part_vertices_winding_in_target',[round(winding(point,vertices_a,indices_a),9) for point in vertices_b])
    print('target_vertices_winding_in_part',[round(winding(point,vertices_b,indices_b),9) for point in vertices_a])
for name,(vertices,triangles) in geometry.items():
    counts={}
    for triangle in triangles:
        for index in range(3):
            edge=tuple(sorted((int(triangle[index]),int(triangle[(index+1)%3])))); counts[edge]=counts.get(edge,0)+1
    print(name,'edge_face_counts',sorted(set(counts.values())))
