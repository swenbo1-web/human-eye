target_matrix=np.array(bpy.data.objects['Object_01'].matrix_world,dtype=float)
inv_target=np.linalg.inv(target_matrix)
for name in names[1:]:
 world,tris=meshdata[name]; target_local=world@inv_target[:3,:3].T+inv_target[:3,3]
 print(name,'in target frame',target_local.tolist(),'center',target_local.mean(axis=0).tolist())

def point_segment(point,start,end):
 direction=end-start; param=np.clip(np.dot(point-start,direction)/np.dot(direction,direction),0.,1.)
 return start+param*direction

def point_triangle(point,triangle):
 start,second,third=triangle; edge1=second-start; edge2=third-start
 normal=np.cross(edge1,edge2); projected=point-normal*np.dot(point-start,normal)/np.dot(normal,normal)
 gram=np.array([[edge1@edge1,edge1@edge2],[edge1@edge2,edge2@edge2]])
 weights=np.linalg.solve(gram,np.array([(projected-start)@edge1,(projected-start)@edge2]))
 if weights.min()>=-1e-13 and weights.sum()<=1+1e-13: return projected
 choices=[point_segment(point,triangle[index],triangle[(index+1)%3]) for index in range(3)]
 return min(choices,key=lambda candidate: np.dot(point-candidate,point-candidate))

def segment_segment(start1,end1,start2,end2):
 direction1=end1-start1; direction2=end2-start2; offset=start1-start2
 aa=direction1@direction1; bb=direction1@direction2; cc=direction2@direction2; dd=direction1@offset; ee=direction2@offset
 candidates=[]
 for point in [start1,end1]: candidates.append((point,point_segment(point,start2,end2)))
 for point in [start2,end2]: candidates.append((point_segment(point,start1,end1),point))
 denom=aa*cc-bb*bb
 if denom>1e-25:
  first=(bb*ee-cc*dd)/denom; second=(aa*ee-bb*dd)/denom
  if 0<=first<=1 and 0<=second<=1: candidates.append((start1+first*direction1,start2+second*direction2))
 return min(candidates,key=lambda pair: np.sum((pair[0]-pair[1])**2))

for name in ['Object_02','Object_04']:
 verts1,tris1=meshdata['Object_01']; verts2,tris2=meshdata[name]; best=(float('inf'),None)
 for index1,indices1 in enumerate(tris1):
  triangle1=verts1[indices1]
  for index2,indices2 in enumerate(tris2):
   triangle2=verts2[indices2]; pairs=[]
   for point in triangle1: pairs.append((point,point_triangle(point,triangle2)))
   for point in triangle2: pairs.append((point_triangle(point,triangle1),point))
   for edge1 in range(3):
    for edge2 in range(3): pairs.append(segment_segment(triangle1[edge1],triangle1[(edge1+1)%3],triangle2[edge2],triangle2[(edge2+1)%3]))
   for pair in pairs:
    distance=np.linalg.norm(pair[0]-pair[1])
    if distance<best[0]: best=(distance,(index1,index2,pair[0].tolist(),pair[1].tolist()))
 print('GLOBAL SURFACE DISTANCE',name,best)
