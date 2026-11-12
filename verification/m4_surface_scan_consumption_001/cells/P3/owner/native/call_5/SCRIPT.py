import numpy as np
import itertools
from mathutils import Vector
mesh_surfaces={}
depsgraph=bpy.context.evaluated_depsgraph_get()
for obj in bpy.context.scene.objects:
    if obj.type!='MESH': continue
    evaluated=obj.evaluated_get(depsgraph)
    mesh=evaluated.to_mesh()
    coords=np.array([tuple(evaluated.matrix_world @ vert.co) for vert in mesh.vertices],dtype=float)
    triangles=[]
    for polygon in mesh.polygons:
        vertices=list(polygon.vertices)
        for offset in range(1,len(vertices)-1):
            triangles.append(coords[[vertices[0],vertices[offset],vertices[offset+1]]])
    mesh_surfaces[obj.name]=np.array(triangles)
    evaluated.to_mesh_clear()
def dot_arrays(first,second): return np.sum(first*second,axis=-1)
def point_triangle_distance(points,triangles):
    origin=triangles[...,0,:]; side_one=triangles[...,1,:]-origin; side_two=triangles[...,2,:]-origin
    relative=points-origin
    aa=dot_arrays(side_one,side_one); ab=dot_arrays(side_one,side_two); bb=dot_arrays(side_two,side_two)
    ar=dot_arrays(side_one,relative); br=dot_arrays(side_two,relative)
    denominator=aa*bb-ab*ab
    safe=np.where(denominator!=0,denominator,1)
    first=(bb*ar-ab*br)/safe; second=(aa*br-ab*ar)/safe
    projection=origin+first[...,None]*side_one+second[...,None]*side_two
    distances=np.where((denominator!=0)&(first>=0)&(second>=0)&(first+second<=1),dot_arrays(points-projection,points-projection),np.inf)
    for edge in range(3):
        start=triangles[...,edge,:]; direction=triangles[...,(edge+1)%3,:]-start
        length=dot_arrays(direction,direction)
        parameter=np.clip(dot_arrays(points-start,direction)/np.where(length!=0,length,1),0,1)
        delta=points-start-parameter[...,None]*direction
        distances=np.minimum(distances,dot_arrays(delta,delta))
    return distances

def surface_distance(first,second):
    minimum=np.inf
    for vertex in range(3):
        minimum=min(minimum,float(point_triangle_distance(first[:,None,vertex,:],second[None,:,:,:]).min()),float(point_triangle_distance(second[None,:,vertex,:],first[:,None,:,:]).min()))
    for edge_one in range(3):
        start=first[:,None,edge_one,:]; direction=first[:,None,(edge_one+1)%3,:]-start
        for edge_two in range(3):
            other=second[None,:,edge_two,:]; other_direction=second[None,:,(edge_two+1)%3,:]-other
            relative=start-other
            aa=dot_arrays(direction,direction); bb=dot_arrays(direction,other_direction); cc=dot_arrays(other_direction,other_direction)
            dd=dot_arrays(direction,relative); ee=dot_arrays(other_direction,relative)
            denominator=aa*cc-bb*bb
            first_param=(bb*ee-cc*dd)/np.where(denominator!=0,denominator,1)
            second_param=(aa*ee-bb*dd)/np.where(denominator!=0,denominator,1)
            delta=relative+first_param[...,None]*direction-second_param[...,None]*other_direction
            valid=(denominator!=0)&(first_param>=0)&(first_param<=1)&(second_param>=0)&(second_param<=1)
            minimum=min(minimum,float(np.where(valid,dot_arrays(delta,delta),np.inf).min()))
        triangle_origin=second[None,:,0,:]; side_one=second[None,:,1,:]-triangle_origin; side_two=second[None,:,2,:]-triangle_origin
        normal=np.cross(side_one,side_two)
        divisor=dot_arrays(direction,normal)
        parameter=dot_arrays(triangle_origin-start,normal)/np.where(divisor!=0,divisor,1)
        hit=start+parameter[...,None]*direction
        relative=hit-triangle_origin
        aa=dot_arrays(side_one,side_one); ab=dot_arrays(side_one,side_two); bb=dot_arrays(side_two,side_two)
        ar=dot_arrays(side_one,relative); br=dot_arrays(side_two,relative); determinant=aa*bb-ab*ab
        first_bary=(bb*ar-ab*br)/np.where(determinant!=0,determinant,1)
        second_bary=(aa*br-ab*ar)/np.where(determinant!=0,determinant,1)
        if np.any((divisor!=0)&(determinant!=0)&(parameter>=0)&(parameter<=1)&(first_bary>=0)&(second_bary>=0)&(first_bary+second_bary<=1)): return 0.0
    return minimum**0.5
surface_rows=[]
for first_name,second_name in itertools.combinations(sorted(mesh_surfaces),2):
    first=mesh_surfaces[first_name]; second=mesh_surfaces[second_name]
    separation=np.maximum(0,np.maximum(first.min(axis=(0,1))-second.max(axis=(0,1)),second.min(axis=(0,1))-first.max(axis=(0,1))))
    if np.linalg.norm(separation)>0.002: continue
    distance=min(surface_distance(first,second),surface_distance(second,first))
    if distance<=0.002:
        surface_rows.append((first_name,second_name,distance*1000))
print('count',len(surface_rows))
for first_name,second_name,distance in surface_rows:
    print(first_name,second_name,format(distance,'.6f'))