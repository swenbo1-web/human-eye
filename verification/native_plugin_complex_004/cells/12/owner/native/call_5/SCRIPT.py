def world_data(name):
 ob=bpy.data.objects[name]
 local,_,tri=meshes[name]
 matrix=np.array(ob.matrix_world,dtype=float)
 return local@matrix[:3,:3].T+matrix[:3,3],tri

def point_faces(points,vertices,triangles):
 best=(float('inf'),None,None)
 for triangle in vertices[triangles]:
  base,second,third=triangle
  first_edge=second-base; second_edge=third-base
  normal=np.cross(first_edge,second_edge); normal2=normal@normal
  heights=(points-base)@normal/normal2
  projected=points-heights[:,None]*normal
  rel=projected-base
  aa=first_edge@first_edge; ab=first_edge@second_edge; bb=second_edge@second_edge
  ra=rel@first_edge; rb=rel@second_edge
  bary_second=(bb*ra-ab*rb)/(aa*bb-ab*ab)
  bary_third=(aa*rb-ab*ra)/(aa*bb-ab*ab)
  valid=(bary_second>=-1e-12)&(bary_third>=-1e-12)&(bary_second+bary_third<=1+1e-12)
  distances=np.sum((points-projected)**2,axis=1); distances[~valid]=np.inf
  index=np.argmin(distances)
  if distances[index]<best[0]: best=(distances[index],points[index],projected[index])
  for start,end in [(base,second),(second,third),(third,base)]:
   direction=end-start
   params=np.clip((points-start)@direction/(direction@direction),0,1)
   foot=start+params[:,None]*direction
   distances=np.sum((points-foot)**2,axis=1); index=np.argmin(distances)
   if distances[index]<best[0]: best=(distances[index],points[index],foot[index])
 return best

def surface_distance(name_a,name_b):
 vertices_a,tri_a=world_data(name_a); vertices_b,tri_b=world_data(name_b)
 result_a=point_faces(vertices_a,vertices_b,tri_b)
 result_b=point_faces(vertices_b,vertices_a,tri_a)
 best=min([result_a,(result_b[0],result_b[2],result_b[1])],key=lambda item:item[0])
 def edge_indices(tri):
  return np.unique(np.sort(np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1),axis=0)
 edges_a=vertices_a[edge_indices(tri_a)]; edges_b=vertices_b[edge_indices(tri_b)]
 starts_a=edges_a[:,0,None,:]; starts_b=edges_b[None,:,0,:]
 directions_a=(edges_a[:,1]-edges_a[:,0])[:,None,:]
 directions_b=(edges_b[:,1]-edges_b[:,0])[None,:,:]
 offsets=starts_a-starts_b
 aa=np.sum(directions_a*directions_a,axis=2); bb=np.sum(directions_b*directions_b,axis=2)
 ab=np.sum(directions_a*directions_b,axis=2); ao=np.sum(directions_a*offsets,axis=2); bo=np.sum(directions_b*offsets,axis=2)
 denominator=aa*bb-ab*ab
 valid=denominator>1e-25
 safe=np.where(valid,denominator,1)
 param_a=(ab*bo-bb*ao)/safe; param_b=(aa*bo-ab*ao)/safe
 valid &= (param_a>=0)&(param_a<=1)&(param_b>=0)&(param_b<=1)
 points_a=starts_a+param_a[:,:,None]*directions_a; points_b=starts_b+param_b[:,:,None]*directions_b
 distances=np.sum((points_a-points_b)**2,axis=2); distances[~valid]=np.inf
 index=np.unravel_index(np.argmin(distances),distances.shape)
 if distances[index]<best[0]: best=(distances[index],points_a[index],points_b[index])
 return math.sqrt(best[0]),best[1],best[2]
for name in ['Object_02','Object_04']:
 distance,point_target,point_candidate=surface_distance('Object_01',name)
 print(name,'global surface distance',format(distance,'.12f'),'target world',point_target.tolist(),'candidate world',point_candidate.tolist())
 print('witness target frame', (target_inverse[:3,:3]@point_target).tolist(), (target_inverse[:3,:3]@point_candidate).tolist())
# Strict shared interior witness for Object_03, using its geometric center.
center=np.array(bpy.data.objects['Object_03'].matrix_world,dtype=float)[:3,3]
center_local=target_inverse[:3,:3]@center
print('03 center world',center.tolist(),'target local',center_local.tolist())
inner=meshes['Object_01'][0][12:24,:2]; outer=meshes['Object_01'][0][:12,:2]
def polygon_halfspace_distances(polygon,point):
 sides=np.roll(polygon,-1,axis=0)-polygon
 inward=np.column_stack([-sides[:,1],sides[:,0]])
 inward/=np.linalg.norm(inward,axis=1)[:,None]
 return np.sum(inward*(point-polygon),axis=1)
print('03 center outer halfspace inward distances',polygon_halfspace_distances(outer,center_local[:2]).tolist())
print('03 center inner halfspace inward distances',polygon_halfspace_distances(inner,center_local[:2]).tolist())
print('03 center distances to thickness faces',0.10000000149011612-abs(center_local[2]))
print('AABB relation:')
for name in names[1:]:
 va,_=world_data('Object_01'); vb,_=world_data(name)
 print(name,'target AABB contains candidate AABB',bool(np.all(vb.min(axis=0)>=va.min(axis=0)) and np.all(vb.max(axis=0)<=va.max(axis=0))))
