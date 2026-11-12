def point_segment(point,start,end):
 direction=end-start
 param=np.clip(np.dot(point-start,direction)/np.dot(direction,direction),0.,1.)
 return start+param*direction

def point_triangle(point,triangle):
 start,second,third=triangle
 first_edge=second-start;second_edge=third-start
 normal=np.cross(first_edge,second_edge)
 projected=point-normal*(np.dot(point-start,normal)/np.dot(normal,normal))
 bary=np.linalg.solve(np.array([[np.dot(first_edge,first_edge),np.dot(first_edge,second_edge)],[np.dot(first_edge,second_edge),np.dot(second_edge,second_edge)]]),np.array([np.dot(projected-start,first_edge),np.dot(projected-start,second_edge)]))
 if min(bary)>=-1e-14 and sum(bary)<=1.+1e-14:return projected
 candidates=[point_segment(point,triangle[index],triangle[(index+1)%3]) for index in range(3)]
 return min(candidates,key=lambda candidate:np.dot(candidate-point,candidate-point))

def segment_segment(first_start,first_end,second_start,second_end):
 first_dir=first_end-first_start;second_dir=second_end-second_start;offset=first_start-second_start
 candidates=[(first_start,point_segment(first_start,second_start,second_end)),(first_end,point_segment(first_end,second_start,second_end)),(point_segment(second_start,first_start,first_end),second_start),(point_segment(second_end,first_start,first_end),second_end)]
 system=np.array([[np.dot(first_dir,first_dir),-np.dot(first_dir,second_dir)],[-np.dot(first_dir,second_dir),np.dot(second_dir,second_dir)]])
 if abs(np.linalg.det(system))>1e-28:
  params=np.linalg.solve(system,np.array([-np.dot(first_dir,offset),np.dot(second_dir,offset)]))
  if np.all(params>=0) and np.all(params<=1):candidates.append((first_start+params[0]*first_dir,second_start+params[1]*second_dir))
 return min(candidates,key=lambda pair:np.dot(pair[0]-pair[1],pair[0]-pair[1]))

def segment_triangle(start,end,triangle):
 first_edge=triangle[1]-triangle[0];second_edge=triangle[2]-triangle[0]
 system=np.column_stack((end-start,-first_edge,-second_edge))
 if abs(np.linalg.det(system))<1e-22:return None
 params=np.linalg.solve(system,triangle[0]-start)
 if 0<=params[0]<=1 and params[1]>=0 and params[2]>=0 and params[1]+params[2]<=1:return start+params[0]*(end-start)
 return None

def winding(point,vertices,triangles):
 total=0.
 for triangle in vertices[triangles]:
  offsets=triangle-point;lengths=np.linalg.norm(offsets,axis=1)
  numerator=np.dot(offsets[0],np.cross(offsets[1],offsets[2]))
  denominator=np.prod(lengths)+np.dot(offsets[0],offsets[1])*lengths[2]+np.dot(offsets[1],offsets[2])*lengths[0]+np.dot(offsets[2],offsets[0])*lengths[1]
  total+=2*np.arctan2(numerator,denominator)
 return total/(4*np.pi)

results={}
for name in ['Part_A','Part_B','Part_C']:
 target_verts,target_tris=geom['Target'];part_verts,part_tris=geom[name]
 candidates=[];intersections=[]
 for target_index,target_tri in enumerate(target_verts[target_tris]):
  for part_index,part_tri in enumerate(part_verts[part_tris]):
   for vertex in target_tri:candidates.append((vertex,point_triangle(vertex,part_tri),'target vertex / part face',target_index,part_index))
   for vertex in part_tri:candidates.append((point_triangle(vertex,target_tri),vertex,'target face / part vertex',target_index,part_index))
   for edge_index in range(3):
    hit=segment_triangle(target_tri[edge_index],target_tri[(edge_index+1)%3],part_tri)
    if hit is not None:intersections.append(hit)
    hit=segment_triangle(part_tri[edge_index],part_tri[(edge_index+1)%3],target_tri)
    if hit is not None:intersections.append(hit)
    for other_edge in range(3):
     point_target,point_part=segment_segment(target_tri[edge_index],target_tri[(edge_index+1)%3],part_tri[other_edge],part_tri[(other_edge+1)%3])
     candidates.append((point_target,point_part,'edge / edge',target_index,part_index))
 best=min(candidates,key=lambda item:np.linalg.norm(item[0]-item[1]))
 distance=np.linalg.norm(best[0]-best[1])
 results[name]=(distance,best)
 print(name,'distance_m',format(distance,'.15f'),'distance_mm',format(distance*1000,'.12f'),'target_point', [format(value,'.12f') for value in best[0]],'part_point',[format(value,'.12f') for value in best[1]],'feature',best[2:],'intersections',len(intersections))
 print('part vertex windings in target',[round(winding(vertex,target_verts,target_tris),9) for vertex in part_verts])
 print('target vertex windings in part',[round(winding(vertex,part_verts,part_tris),9) for vertex in target_verts])
