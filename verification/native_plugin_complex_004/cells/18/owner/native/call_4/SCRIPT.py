def dot_rows(first, second):
    return np.einsum('ij,ij->i',first,second)

def point_segment(points, starts, ends):
    directions=ends-starts
    lengths=dot_rows(directions,directions)
    parameters=np.divide(dot_rows(points-starts,directions),lengths,out=np.zeros_like(lengths),where=lengths>0)
    return starts+np.clip(parameters,0,1)[:,None]*directions

def projected_face(points, triangles):
    origins=triangles[:,0]; first=triangles[:,1]-origins; second=triangles[:,2]-origins
    normals=np.cross(first,second); norm_squared=dot_rows(normals,normals)
    heights=np.divide(dot_rows(points-origins,normals),norm_squared,out=np.zeros_like(norm_squared),where=norm_squared>0)
    projections=points-heights[:,None]*normals
    relative=projections-origins
    bary_first=np.divide(dot_rows(np.cross(relative,second),normals),norm_squared,out=np.zeros_like(norm_squared),where=norm_squared>0)
    bary_second=np.divide(dot_rows(np.cross(first,relative),normals),norm_squared,out=np.zeros_like(norm_squared),where=norm_squared>0)
    inside=(norm_squared>0)&(bary_first>=-1e-13)&(bary_second>=-1e-13)&(bary_first+bary_second<=1+1e-13)
    return projections,inside

def triangle_surface_distance(target_triangles, other_triangles):
    target_pairs=np.repeat(target_triangles,len(other_triangles),axis=0)
    other_pairs=np.tile(other_triangles,(len(target_triangles),1,1))
    best=[float('inf'),None,None,None]
    def consider(first,second,valid=None,feature=''):
        squared=dot_rows(first-second,first-second)
        if valid is not None: squared=np.where(valid,squared,np.inf)
        index=int(np.argmin(squared))
        if squared[index]<best[0]:
            best[:]=[float(squared[index]),first[index].copy(),second[index].copy(),(index//len(other_triangles),index%len(other_triangles),feature)]
    for vertex_index in range(3):
        points=target_pairs[:,vertex_index]
        projections,inside=projected_face(points,other_pairs)
        consider(points,projections,inside,'target vertex / candidate face')
        points=other_pairs[:,vertex_index]
        projections,inside=projected_face(points,target_pairs)
        consider(projections,points,inside,'target face / candidate vertex')
    for first_index in range(3):
        first_start=target_pairs[:,first_index]; first_end=target_pairs[:,(first_index+1)%3]
        for second_index in range(3):
            second_start=other_pairs[:,second_index]; second_end=other_pairs[:,(second_index+1)%3]
            consider(first_start,point_segment(first_start,second_start,second_end),feature='edge boundary')
            consider(first_end,point_segment(first_end,second_start,second_end),feature='edge boundary')
            consider(point_segment(second_start,first_start,first_end),second_start,feature='edge boundary')
            consider(point_segment(second_end,first_start,first_end),second_end,feature='edge boundary')
            first_direction=first_end-first_start; second_direction=second_end-second_start; offset=first_start-second_start
            first_squared=dot_rows(first_direction,first_direction); second_squared=dot_rows(second_direction,second_direction)
            mutual=dot_rows(first_direction,second_direction); first_offset=dot_rows(first_direction,offset); second_offset=dot_rows(second_direction,offset)
            denominator=dot_rows(np.cross(first_direction,second_direction),np.cross(first_direction,second_direction))
            first_parameter=np.divide(mutual*second_offset-second_squared*first_offset,denominator,out=np.zeros_like(denominator),where=denominator>0)
            second_parameter=np.divide(first_squared*second_offset-mutual*first_offset,denominator,out=np.zeros_like(denominator),where=denominator>0)
            valid=(denominator>0)&(first_parameter>=0)&(first_parameter<=1)&(second_parameter>=0)&(second_parameter<=1)
            consider(first_start+first_parameter[:,None]*first_direction,second_start+second_parameter[:,None]*second_direction,valid,'edge / edge interior')
    for edge_triangles,face_triangles in [(target_pairs,other_pairs),(other_pairs,target_pairs)]:
        normals=np.cross(face_triangles[:,1]-face_triangles[:,0],face_triangles[:,2]-face_triangles[:,0])
        for edge_index in range(3):
            starts=edge_triangles[:,edge_index]; directions=edge_triangles[:,(edge_index+1)%3]-starts
            denominator=dot_rows(directions,normals)
            parameters=np.divide(dot_rows(face_triangles[:,0]-starts,normals),denominator,out=np.zeros_like(denominator),where=denominator!=0)
            points=starts+parameters[:,None]*directions
            _,inside=projected_face(points,face_triangles)
            valid=(denominator!=0)&(parameters>=0)&(parameters<=1)&inside
            consider(points,points,valid,'surface intersection')
    return (float(np.sqrt(best[0])),best[1],best[2],best[3])

results=[]
for name,data in geometry.items():
    if name!='Target':
        distance,point_target,point_other,feature=triangle_surface_distance(geometry['Target'][2],data[2])
        results.append((distance,name,point_target,point_other,feature))
results.sort(key=lambda row:row[0])
print('candidate_count',len(results),'all_triangle_pairs',sum(len(geometry['Target'][2])*len(geometry[row[1]][2]) for row in results))
print('all_surface_distances_m',[(name,float(distance)) for distance,name,*rest in results])
for distance,name,point_target,point_other,feature in results[:2]:
    print('witness',name,'distance_m',format(distance,'.15g'),'target_point',point_target.tolist(),'candidate_point',point_other.tolist(),'triangles_feature',feature)
print('nonfinite',[(name,distance) for distance,name,*rest in results if not np.isfinite(distance)])