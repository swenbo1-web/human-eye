def row_dot(first,second):
    return np.einsum('...i,...i->...',first,second)

def point_segment_squared(points,start,end):
    direction=end-start
    denom=row_dot(direction,direction)
    fraction=np.divide(row_dot(points-start,direction),denom,out=np.zeros_like(denom),where=denom>0)
    nearest=start+np.clip(fraction,0,1)[...,None]*direction
    return row_dot(points-nearest,points-nearest)

def point_triangle_squared(points,triangles):
    start,second,third=triangles[:,0],triangles[:,1],triangles[:,2]
    normal=np.cross(second-start,third-start)
    norm_squared=row_dot(normal,normal)
    signed=row_dot(points-start,normal)
    projection=points-np.divide(signed,norm_squared,out=np.zeros_like(signed),where=norm_squared>0)[:,None]*normal
    inside=np.ones(len(points),dtype=bool)
    for edge in range(3):
        edge_start=triangles[:,edge]; edge_end=triangles[:,(edge+1)%3]
        inside &= row_dot(np.cross(edge_end-edge_start,projection-edge_start),normal)>=0
    distances=np.minimum.reduce([point_segment_squared(points,triangles[:,edge],triangles[:,(edge+1)%3]) for edge in range(3)])
    plane_distance=np.divide(signed*signed,norm_squared,out=np.full_like(signed,np.inf),where=norm_squared>0)
    return np.where(inside & (norm_squared>0),np.minimum(distances,plane_distance),distances)

def segment_segment_squared(start_a,end_a,start_b,end_b):
    direction_a=end_a-start_a; direction_b=end_b-start_b; offset=start_a-start_b
    length_a=row_dot(direction_a,direction_a); length_b=row_dot(direction_b,direction_b)
    mixed=row_dot(direction_a,direction_b); offset_a=row_dot(direction_a,offset); offset_b=row_dot(direction_b,offset)
    determinant=row_dot(np.cross(direction_a,direction_b),np.cross(direction_a,direction_b))
    parameter_a=np.divide(mixed*offset_b-length_b*offset_a,determinant,out=np.zeros_like(determinant),where=determinant>0)
    parameter_b=np.divide(length_a*offset_b-mixed*offset_a,determinant,out=np.zeros_like(determinant),where=determinant>0)
    interior=(determinant>0)&(parameter_a>=0)&(parameter_a<=1)&(parameter_b>=0)&(parameter_b<=1)
    residual=offset+parameter_a[:,None]*direction_a-parameter_b[:,None]*direction_b
    return np.minimum(np.minimum.reduce([point_segment_squared(start_a,start_b,end_b),point_segment_squared(end_a,start_b,end_b),point_segment_squared(start_b,start_a,end_a),point_segment_squared(end_b,start_a,end_a)]),np.where(interior,row_dot(residual,residual),np.inf))

def segment_triangle_intersects(start,end,triangles):
    normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    signed_start=row_dot(start-triangles[:,0],normal)
    denominator=row_dot(end-start,normal)
    parameter=np.divide(-signed_start,denominator,out=np.full_like(denominator,np.inf),where=denominator!=0)
    valid=(denominator!=0)&(parameter>=0)&(parameter<=1)
    point=start+np.where(valid,parameter,0)[:,None]*(end-start)
    for edge in range(3):
        valid &= row_dot(np.cross(triangles[:,(edge+1)%3]-triangles[:,edge],point-triangles[:,edge]),normal)>=0
    return valid

def triangles_squared(first,second):
    distances=np.full(len(first),np.inf)
    intersection=np.zeros(len(first),dtype=bool)
    for edge in range(3):
        distances=np.minimum(distances,point_triangle_squared(first[:,edge],second))
        distances=np.minimum(distances,point_triangle_squared(second[:,edge],first))
        intersection |= segment_triangle_intersects(first[:,edge],first[:,(edge+1)%3],second)
        intersection |= segment_triangle_intersects(second[:,edge],second[:,(edge+1)%3],first)
        for other_edge in range(3):
            distances=np.minimum(distances,segment_segment_squared(first[:,edge],first[:,(edge+1)%3],second[:,other_edge],second[:,(other_edge+1)%3]))
    return np.where(intersection,0,distances)

unit_mm=scene.unit_settings.scale_length*1000
threshold=2/unit_mm
scan_results=[]; excluded_objects=0; candidate_pairs=0; tested_triangles=0
for first_index,first in enumerate(scan_meshes):
    for second in scan_meshes[first_index+1:]:
        if not len(first['tri']) or not len(second['tri']): continue
        gap=np.maximum(0,np.maximum(first['lo'].min(axis=0)-second['hi'].max(axis=0),second['lo'].min(axis=0)-first['hi'].max(axis=0)))
        if np.dot(gap,gap)>(threshold+1e-12)**2:
            excluded_objects+=1; continue
        candidate_pairs+=1
        gaps=np.maximum(0,np.maximum(first['lo'][:,None,:]-second['hi'][None,:,:],second['lo'][None,:,:]-first['hi'][:,None,:]))
        first_tri,second_tri=np.nonzero(row_dot(gaps,gaps)<=(threshold+1e-12)**2)
        tested_triangles+=len(first_tri)
        if not len(first_tri): continue
        squared=triangles_squared(first['tri'][first_tri],second['tri'][second_tri])
        best=float(np.sqrt(squared.min()))
        if best<=threshold+1e-12:
            scan_results.append((first['name'],second['name'],best*unit_mm))
print('pairs_total',len(scan_meshes)*(len(scan_meshes)-1)//2,'aabb_excluded',excluded_objects,'candidate_object_pairs',candidate_pairs,'tested_triangle_pairs',tested_triangles)
print('degenerate_triangles',[(item['name'],int(np.count_nonzero(np.linalg.norm(np.cross(item['tri'][:,1]-item['tri'][:,0],item['tri'][:,2]-item['tri'][:,0]),axis=1)==0))) for item in scan_meshes if np.any(np.linalg.norm(np.cross(item['tri'][:,1]-item['tri'][:,0],item['tri'][:,2]-item['tri'][:,0]),axis=1)==0)])
print('qualifying',len(scan_results))
for result in scan_results: print('%s %s %.12f mm'%result)
