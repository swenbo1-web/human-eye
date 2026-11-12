import numpy as np, itertools
mesh_triangles = {}
depsgraph = bpy.context.evaluated_depsgraph_get()
for obj in bpy.context.scene.objects:
    if obj.type != 'MESH':
        continue
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    mesh.calc_loop_triangles()
    vertices = np.array([tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices], dtype=float)
    mesh_triangles[obj.name] = vertices[np.array([tuple(triangle.vertices) for triangle in mesh.loop_triangles])]
    evaluated.to_mesh_clear()
def dot_vectors(first, second):
    return np.sum(first * second, axis=-1)
def point_segment_squared(points, starts, ends):
    directions = ends-starts
    denominator = dot_vectors(directions,directions)
    fractions = np.divide(dot_vectors(points-starts,directions),denominator,out=np.zeros(np.broadcast_shapes(points.shape[:-1],starts.shape[:-1])),where=denominator>0)
    residual = points-starts-np.clip(fractions,0,1)[...,None]*directions
    return dot_vectors(residual,residual)
def plane_coordinates(points, triangles):
    origin = triangles[...,0,:]
    edge_first = triangles[...,1,:]-origin
    edge_second = triangles[...,2,:]-origin
    normal = np.cross(edge_first,edge_second)
    normal_squared = dot_vectors(normal,normal)
    offset = points-origin
    height = dot_vectors(offset,normal)
    denominator = dot_vectors(edge_first,edge_first)*dot_vectors(edge_second,edge_second)-dot_vectors(edge_first,edge_second)**2
    coord_first = np.divide(dot_vectors(offset,edge_first)*dot_vectors(edge_second,edge_second)-dot_vectors(offset,edge_second)*dot_vectors(edge_first,edge_second),denominator,out=np.zeros_like(height),where=denominator!=0)
    coord_second = np.divide(dot_vectors(offset,edge_second)*dot_vectors(edge_first,edge_first)-dot_vectors(offset,edge_first)*dot_vectors(edge_first,edge_second),denominator,out=np.zeros_like(height),where=denominator!=0)
    inside = (denominator!=0)&(coord_first>=0)&(coord_second>=0)&(coord_first+coord_second<=1)
    squared = np.divide(height**2,normal_squared,out=np.full_like(height,np.inf),where=normal_squared>0)
    return inside,squared,height

def triangle_distance(first,second):
    first = first[:,None,:,:]
    second = second[None,:,:,:]
    best = float('inf')
    for source,target in [(first,second),(second,first)]:
        for vertex_index in range(3):
            points=source[...,vertex_index,:]
            inside,squared,height = plane_coordinates(points,target)
            best=min(best,float(np.min(np.where(inside,squared,np.inf))))
        for edge_index in range(3):
            starts=source[...,edge_index,:]
            ends=source[...,(edge_index+1)%3,:]
            inside_start,squared_start,height_start=plane_coordinates(starts,target)
            inside_end,squared_end,height_end=plane_coordinates(ends,target)
            divisor=height_start-height_end
            fraction=np.divide(height_start,divisor,out=np.full_like(height_start,-1),where=divisor!=0)
            intersections=starts+fraction[...,None]*(ends-starts)
            inside_cross,_,_=plane_coordinates(intersections,target)
            if np.any((fraction>=0)&(fraction<=1)&inside_cross):
                return 0.0
    for first_index in range(3):
        first_start=first[...,first_index,:]
        first_end=first[...,(first_index+1)%3,:]
        for second_index in range(3):
            second_start=second[...,second_index,:]
            second_end=second[...,(second_index+1)%3,:]
            for points,starts,ends in [(first_start,second_start,second_end),(first_end,second_start,second_end),(second_start,first_start,first_end),(second_end,first_start,first_end)]:
                best=min(best,float(np.min(point_segment_squared(points,starts,ends))))
            first_direction=first_end-first_start
            second_direction=second_end-second_start
            offset=first_start-second_start
            first_squared=dot_vectors(first_direction,first_direction)
            second_squared=dot_vectors(second_direction,second_direction)
            mixed=dot_vectors(first_direction,second_direction)
            first_offset=dot_vectors(first_direction,offset)
            second_offset=dot_vectors(second_direction,offset)
            divisor=first_squared*second_squared-mixed*mixed
            first_fraction=np.divide(mixed*second_offset-second_squared*first_offset,divisor,out=np.full_like(divisor,-1),where=divisor>0)
            second_fraction=np.divide(first_squared*second_offset-mixed*first_offset,divisor,out=np.full_like(divisor,-1),where=divisor>0)
            valid=(first_fraction>=0)&(first_fraction<=1)&(second_fraction>=0)&(second_fraction<=1)
            residual=offset+first_fraction[...,None]*first_direction-second_fraction[...,None]*second_direction
            best=min(best,float(np.min(np.where(valid,dot_vectors(residual,residual),np.inf))))
    return float(np.sqrt(best))
computed_matches=[]
for first_name,second_name in itertools.combinations(sorted(mesh_triangles),2):
    first=mesh_triangles[first_name]
    second=mesh_triangles[second_name]
    gap=np.maximum(0,np.maximum(first.min(axis=(0,1))-second.max(axis=(0,1)),second.min(axis=(0,1))-first.max(axis=(0,1))))
    if np.linalg.norm(gap)>0.002:
        continue
    distance=triangle_distance(first,second)
    if distance<=0.002:
        computed_matches.append((first_name,second_name,distance*1000))
print('MATCH_COUNT',len(computed_matches))
for first_name,second_name,distance in computed_matches:
    print(first_name,second_name,format(distance,'.9f'))