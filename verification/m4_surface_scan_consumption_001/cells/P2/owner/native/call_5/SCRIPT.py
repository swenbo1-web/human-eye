import numpy as np
import itertools
mesh_triangles={}
depsgraph=bpy.context.evaluated_depsgraph_get()
for obj in bpy.context.scene.objects:
    if obj.type!='MESH': continue
    evaluated=obj.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    mesh.calc_loop_triangles()
    vertices=np.array([tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices],dtype=float)
    mesh_triangles[obj.name]=vertices[np.array([tuple(triangle.vertices) for triangle in mesh.loop_triangles])]
    evaluated.to_mesh_clear()
def point_triangle_min(points, triangles):
    offsets=points[:,None,:]-triangles[None,:,0,:]
    edge_first=triangles[:,1]-triangles[:,0]
    edge_second=triangles[:,2]-triangles[:,0]
    normals=np.cross(edge_first,edge_second)
    norm_squared=np.sum(normals*normals,axis=-1)
    signed=np.einsum('ptj,tj->pt',offsets,normals)
    projected=offsets-signed[:,:,None]*normals[None,:,:]/norm_squared[None,:,None]
    first_squared=np.sum(edge_first*edge_first,axis=-1)
    second_squared=np.sum(edge_second*edge_second,axis=-1)
    mixed=np.sum(edge_first*edge_second,axis=-1)
    projected_first=np.einsum('ptj,tj->pt',projected,edge_first)
    projected_second=np.einsum('ptj,tj->pt',projected,edge_second)
    determinant=first_squared*second_squared-mixed*mixed
    bary_first=(second_squared*projected_first-mixed*projected_second)/determinant
    bary_second=(first_squared*projected_second-mixed*projected_first)/determinant
    inside=(bary_first>=0)&(bary_second>=0)&(bary_first+bary_second<=1)
    return np.min(np.where(inside,signed*signed/norm_squared,np.inf))
def edges_for(triangles):
    return triangles[:,[0,1,2]].reshape(-1,3),triangles[:,[1,2,0]].reshape(-1,3)
def segment_triangle_hit(starts,ends,triangles):
    directions=ends-starts
    first=triangles[:,1]-triangles[:,0]
    second=triangles[:,2]-triangles[:,0]
    cross=np.cross(directions[:,None,:],second[None,:,:])
    determinant=np.einsum('tj,stj->st',first,cross)
    valid=np.abs(determinant)>1e-25
    inverse=np.divide(1.,determinant,out=np.zeros_like(determinant),where=valid)
    offset=starts[:,None,:]-triangles[None,:,0,:]
    bary_first=np.sum(offset*cross,axis=-1)*inverse
    cross_second=np.cross(offset,first[None,:,:])
    bary_second=np.einsum('sj,stj->st',directions,cross_second)*inverse
    fraction=np.einsum('tj,stj->st',second,cross_second)*inverse
    return np.any(valid&(bary_first>=0)&(bary_second>=0)&(bary_first+bary_second<=1)&(fraction>=0)&(fraction<=1))
def segment_min(starts_a,ends_a,starts_b,ends_b):
    direction_a=(ends_a-starts_a)[:,None,:]
    direction_b=(ends_b-starts_b)[None,:,:]
    offset=starts_a[:,None,:]-starts_b[None,:,:]
    length_a=np.sum(direction_a*direction_a,axis=-1)
    length_b=np.sum(direction_b*direction_b,axis=-1)
    mixed=np.sum(direction_a*direction_b,axis=-1)
    offset_a=np.sum(direction_a*offset,axis=-1)
    offset_b=np.sum(direction_b*offset,axis=-1)
    determinant=length_a*length_b-mixed*mixed
    parameter_a=np.divide(mixed*offset_b-length_b*offset_a,determinant,out=np.zeros_like(determinant),where=determinant>1e-30)
    parameter_b=np.divide(length_a*offset_b-mixed*offset_a,determinant,out=np.zeros_like(determinant),where=determinant>1e-30)
    inside=(determinant>1e-30)&(parameter_a>=0)&(parameter_a<=1)&(parameter_b>=0)&(parameter_b<=1)
    interior=np.sum((offset+parameter_a[:,:,None]*direction_a-parameter_b[:,:,None]*direction_b)**2,axis=-1)
    minimum=np.min(np.where(inside,interior,np.inf))
    for parameter_a in (0.,1.):
        parameter_b=np.clip((offset_b+parameter_a*mixed)/length_b,0,1)
        minimum=min(minimum,np.min(np.sum((offset+parameter_a*direction_a-parameter_b[:,:,None]*direction_b)**2,axis=-1)))
    for parameter_b in (0.,1.):
        parameter_a=np.clip((parameter_b*mixed-offset_a)/length_a,0,1)
        minimum=min(minimum,np.min(np.sum((offset+parameter_a[:,:,None]*direction_a-parameter_b*direction_b)**2,axis=-1)))
    return minimum
surface_matches=[]
for name_a,name_b in itertools.combinations(sorted(mesh_triangles),2):
    triangles_a=mesh_triangles[name_a]; triangles_b=mesh_triangles[name_b]
    gap=np.maximum(np.maximum(triangles_a.min(axis=(0,1))-triangles_b.max(axis=(0,1)),triangles_b.min(axis=(0,1))-triangles_a.max(axis=(0,1))),0)
    if np.linalg.norm(gap)>0.002: continue
    starts_a,ends_a=edges_for(triangles_a); starts_b,ends_b=edges_for(triangles_b)
    if segment_triangle_hit(starts_a,ends_a,triangles_b) or segment_triangle_hit(starts_b,ends_b,triangles_a): distance=0.
    else: distance=float(np.sqrt(min(point_triangle_min(triangles_a.reshape(-1,3),triangles_b),point_triangle_min(triangles_b.reshape(-1,3),triangles_a),segment_min(starts_a,ends_a,starts_b,ends_b))))
    if distance<=0.002: surface_matches.append((name_a,name_b,distance*1000))
print('Matches:',len(surface_matches))
for name_a,name_b,distance_mm in surface_matches: print(name_a,name_b,format(distance_mm,'.9f'))