def point_tri(point, triangle):
    first,second,third=triangle
    edge_ab=second-first; edge_ac=third-first; offset=point-first
    dot_ab=offset@edge_ab; dot_ac=offset@edge_ac
    if dot_ab<=0 and dot_ac<=0: return first
    offset_b=point-second; dot_bab=offset_b@edge_ab; dot_bac=offset_b@edge_ac
    if dot_bab>=0 and dot_bac<=dot_bab: return second
    vc=dot_ab*dot_bac-dot_bab*dot_ac
    if vc<=0 and dot_ab>=0 and dot_bab<=0: return first+dot_ab/(dot_ab-dot_bab)*edge_ab
    offset_c=point-third; dot_cab=offset_c@edge_ab; dot_cac=offset_c@edge_ac
    if dot_cac>=0 and dot_cab<=dot_cac: return third
    vb=dot_cab*dot_ac-dot_ab*dot_cac
    if vb<=0 and dot_ac>=0 and dot_cac<=0: return first+dot_ac/(dot_ac-dot_cac)*edge_ac
    va=dot_bab*dot_cac-dot_cab*dot_bac
    if va<=0 and dot_bac-dot_bab>=0 and dot_cab-dot_cac>=0:
        return second+(dot_bac-dot_bab)/((dot_bac-dot_bab)+(dot_cab-dot_cac))*(third-second)
    return first+(vb*edge_ab+vc*edge_ac)/(va+vb+vc)
def segment_pair(start_a,end_a,start_b,end_b):
    direction_a=end_a-start_a; direction_b=end_b-start_b; offset=start_a-start_b
    aa=direction_a@direction_a; bb=direction_a@direction_b; cc=direction_b@direction_b
    dd=direction_a@offset; ee=direction_b@offset
    denom=aa*cc-bb*bb
    param_a=np.clip((bb*ee-cc*dd)/denom,0,1) if denom>1e-30 else 0.0
    param_b=(bb*param_a+ee)/cc
    if param_b<0: param_b=0.; param_a=np.clip(-dd/aa,0,1)
    elif param_b>1: param_b=1.; param_a=np.clip((bb-dd)/aa,0,1)
    return start_a+param_a*direction_a,start_b+param_b*direction_b

def segment_triangle(start,end,triangle):
    edge_ab=triangle[1]-triangle[0]; edge_ac=triangle[2]-triangle[0]; direction=end-start
    cross=np.cross(direction,edge_ac); determinant=edge_ab@cross
    if abs(determinant)<1e-20: return None
    offset=start-triangle[0]; param_u=(offset@cross)/determinant
    cross2=np.cross(offset,edge_ab); param_v=(direction@cross2)/determinant
    param_t=(edge_ac@cross2)/determinant
    if 0<=param_u<=1 and 0<=param_v and param_u+param_v<=1 and 0<=param_t<=1:
        return start+param_t*direction
    return None

def winding(point,triangles):
    offsets=triangles-point
    lengths=np.linalg.norm(offsets,axis=2)
    numerator=np.einsum('ij,ij->i', offsets[:,0], np.cross(offsets[:,1], offsets[:,2]))
    denominator=lengths.prod(axis=1)+np.einsum('ij,ij->i',offsets[:,0],offsets[:,1])*lengths[:,2]+np.einsum('ij,ij->i',offsets[:,1],offsets[:,2])*lengths[:,0]+np.einsum('ij,ij->i',offsets[:,2],offsets[:,0])*lengths[:,1]
    return np.sum(2*np.arctan2(numerator,denominator))/(4*np.pi)

results={}
target_vertices,target_indices=geo['Target']; target_triangles=target_vertices[target_indices]
for name in ['Part_A','Part_B','Part_C']:
    vertices,indices=geo[name]; triangles=vertices[indices]
    best=(float('inf'),None,None,None); intersections=0
    def consider(point_a,point_b,feature):
        global best
        squared=np.sum((point_a-point_b)**2)
        if squared<best[0]: best=(squared,point_a.copy(),point_b.copy(),feature)
    for ti,triangle_a in enumerate(target_triangles):
        for pi,triangle_b in enumerate(triangles):
            for corner in range(3):
                consider(triangle_a[corner],point_tri(triangle_a[corner],triangle_b),('target_vertex',ti,pi,corner))
                consider(point_tri(triangle_b[corner],triangle_a),triangle_b[corner],('part_vertex',ti,pi,corner))
                hit=segment_triangle(triangle_a[corner],triangle_a[(corner+1)%3],triangle_b)
                if hit is not None: intersections+=1; consider(hit,hit,('intersection',ti,pi))
                hit=segment_triangle(triangle_b[corner],triangle_b[(corner+1)%3],triangle_a)
                if hit is not None: intersections+=1; consider(hit,hit,('intersection',ti,pi))
                for other in range(3):
                    endpoint_a,endpoint_b=segment_pair(triangle_a[corner],triangle_a[(corner+1)%3],triangle_b[other],triangle_b[(other+1)%3])
                    consider(endpoint_a,endpoint_b,('edge_edge',ti,pi,corner,other))
    results[name]=best
    print(name,'distance_mm',format(np.sqrt(best[0])*1000,'.12f'),'target_point', ['%.12f'%value for value in best[1]],'part_point',['%.12f'%value for value in best[2]],'feature',best[3], 'intersections',intersections)
    print('part_vertices_winding_in_target',[round(winding(point,target_triangles),10) for point in vertices])
    print('target_vertices_winding_in_part',[round(winding(point,triangles),10) for point in target_vertices])