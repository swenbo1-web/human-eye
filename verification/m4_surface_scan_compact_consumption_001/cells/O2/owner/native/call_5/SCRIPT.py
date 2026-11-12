import numpy as np
import itertools
mesh_triangles = {}
depsgraph = bpy.context.evaluated_depsgraph_get()
for obj in bpy.context.scene.objects:
    if obj.type != 'MESH':
        continue
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    mesh.calc_loop_triangles()
    coordinates = np.array([tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices])
    mesh_triangles[obj.name] = coordinates[np.array([tuple(triangle.vertices) for triangle in mesh.loop_triangles])]
    evaluated.to_mesh_clear()
def dot_vectors(first, second):
    return np.sum(first * second, axis=-1)
def point_triangle_sq(points, triangles):
    origin = triangles[...,0,:]
    edge_first = triangles[...,1,:]-origin
    edge_second = triangles[...,2,:]-origin
    normal = np.cross(edge_first, edge_second)
    normal_sq = dot_vectors(normal,normal)
    signed = dot_vectors(points-origin, normal)
    projected = points - (signed/np.maximum(normal_sq,1e-300))[...,None]*normal
    relative = projected-origin
    scalar_first = dot_vectors(edge_first,edge_first)
    scalar_cross = dot_vectors(edge_first,edge_second)
    scalar_second = dot_vectors(edge_second,edge_second)
    denominator = scalar_first*scalar_second-scalar_cross**2
    bary_first = (scalar_second*dot_vectors(relative,edge_first)-scalar_cross*dot_vectors(relative,edge_second))/np.maximum(denominator,1e-300)
    bary_second = (scalar_first*dot_vectors(relative,edge_second)-scalar_cross*dot_vectors(relative,edge_first))/np.maximum(denominator,1e-300)
    inside = (bary_first>=0)&(bary_second>=0)&(bary_first+bary_second<=1)&(normal_sq>0)
    distance = np.where(inside,signed**2/np.maximum(normal_sq,1e-300),np.inf)
    for index in range(3):
        start = triangles[...,index,:]
        edge = triangles[...,(index+1)%3,:]-start
        parameter = np.clip(dot_vectors(points-start,edge)/np.maximum(dot_vectors(edge,edge),1e-300),0,1)
        difference = points-start-parameter[...,None]*edge
        distance = np.minimum(distance,dot_vectors(difference,difference))
    return distance
def segment_triangle_hit(start, end, triangles):
    edge_first = triangles[...,1,:]-triangles[...,0,:]
    edge_second = triangles[...,2,:]-triangles[...,0,:]
    direction = end-start
    cross_direction = np.cross(direction,edge_second)
    determinant = dot_vectors(edge_first,cross_direction)
    valid = np.abs(determinant)>1e-25
    reciprocal = np.where(valid,1/np.where(valid,determinant,1),0)
    displacement = start-triangles[...,0,:]
    bary_first = dot_vectors(displacement,cross_direction)*reciprocal
    cross_displacement = np.cross(displacement,edge_first)
    bary_second = dot_vectors(direction,cross_displacement)*reciprocal
    parameter = dot_vectors(edge_second,cross_displacement)*reciprocal
    return valid&(bary_first>=0)&(bary_second>=0)&(bary_first+bary_second<=1)&(parameter>=0)&(parameter<=1)
def triangle_distance(first, second):
    first = first[:,None,:,:]
    second = second[None,:,:,:]
    minimum = np.full(np.broadcast_shapes(first.shape[:2],second.shape[:2]),np.inf)
    for index in range(3):
        minimum = np.minimum(minimum,point_triangle_sq(first[...,index,:],second))
        minimum = np.minimum(minimum,point_triangle_sq(second[...,index,:],first))
        if np.any(segment_triangle_hit(first[...,index,:],first[...,(index+1)%3,:],second)) or np.any(segment_triangle_hit(second[...,index,:],second[...,(index+1)%3,:],first)):
            return 0.0
        for other_index in range(3):
            start_first = first[...,index,:]
            start_second = second[...,other_index,:]
            edge_first = first[...,(index+1)%3,:]-start_first
            edge_second = second[...,(other_index+1)%3,:]-start_second
            relative = start_first-start_second
            first_sq = dot_vectors(edge_first,edge_first)
            second_sq = dot_vectors(edge_second,edge_second)
            cross_scalar = dot_vectors(edge_first,edge_second)
            first_relative = dot_vectors(edge_first,relative)
            second_relative = dot_vectors(edge_second,relative)
            denominator = first_sq*second_sq-cross_scalar**2
            valid = denominator>1e-30
            parameter_first = (cross_scalar*second_relative-second_sq*first_relative)/np.where(valid,denominator,1)
            parameter_second = (first_sq*second_relative-cross_scalar*first_relative)/np.where(valid,denominator,1)
            interior = valid&(parameter_first>=0)&(parameter_first<=1)&(parameter_second>=0)&(parameter_second<=1)
            difference = relative+parameter_first[...,None]*edge_first-parameter_second[...,None]*edge_second
            minimum = np.minimum(minimum,np.where(interior,dot_vectors(difference,difference),np.inf))
    return float(np.sqrt(np.min(minimum)))
compact_matches = []
for first_name, second_name in itertools.combinations(sorted(mesh_triangles),2):
    first = mesh_triangles[first_name]
    second = mesh_triangles[second_name]
    gaps = np.maximum(np.maximum(first.min(axis=(0,1))-second.max(axis=(0,1)),second.min(axis=(0,1))-first.max(axis=(0,1))),0)
    if np.linalg.norm(gaps)>0.002:
        continue
    distance = triangle_distance(first,second)
    if distance<=0.002:
        compact_matches.append((first_name,second_name,distance*1000))
print('match_count',len(compact_matches))
for first_name,second_name,distance_mm in compact_matches:
    print(first_name,second_name,format(distance_mm,'.9f'))