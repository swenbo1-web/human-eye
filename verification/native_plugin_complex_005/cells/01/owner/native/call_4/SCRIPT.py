def confirm_cache():
 for name, data in cache.items():
  obj=bpy.data.objects[name]
  assert np.array_equal(np.array(obj.matrix_world),data['mat'])
  assert np.array_equal(np.array([list(v.co) for v in obj.data.vertices]),data['local'])
  assert [tuple(p.vertices) for p in obj.data.polygons]==data['faces']
confirm_cache()
base_inv=np.linalg.inv(cache['Object_01']['mat'])
for name,data in cache.items():
 data['target_frame']=data['v']@base_inv[:3,:3].T+base_inv[:3,3]
 data['triangles']=data['v'][np.array(data['faces'])]
 data['bvh']=BVHTree.FromPolygons([Vector(v) for v in data['v']],data['faces'],all_triangles=True,epsilon=0.0)
 if name!='Object_01':
  print(name,'vertices in target local frame',data['target_frame'].tolist(),'BVH triangle overlaps',len(cache['Object_01']['bvh'].overlap(data['bvh'])))
from collections import Counter
for name,data in cache.items():
 counts=Counter(tuple(sorted((face[index],face[(index+1)%3]))) for face in data['faces'] for index in range(3))
 print(name,'edge incidence',dict(Counter(counts.values())))

def point_triangle(point,tri):
 first,second,third=tri
 edge1=second-first;edge2=third-first
 normal=np.cross(edge1,edge2)
 projected=point-normal*np.dot(point-first,normal)/np.dot(normal,normal)
 dot11=np.dot(edge1,edge1);dot12=np.dot(edge1,edge2);dot22=np.dot(edge2,edge2)
 vector=projected-first;dotv1=np.dot(vector,edge1);dotv2=np.dot(vector,edge2)
 denom=dot11*dot22-dot12*dot12
 beta=(dot22*dotv1-dot12*dotv2)/denom;gamma=(dot11*dotv2-dot12*dotv1)/denom
 if beta>=0 and gamma>=0 and beta+gamma<=1:
  return np.dot(point-projected,point-projected),projected
 best=(float('inf'),None)
 for start,end in [(first,second),(second,third),(third,first)]:
  edge=end-start;fraction=np.clip(np.dot(point-start,edge)/np.dot(edge,edge),0,1);closest=start+fraction*edge
  dist=np.dot(point-closest,point-closest)
  if dist<best[0]:best=(dist,closest)
 return best

def segment_segment(start1,end1,start2,end2):
 edge1=end1-start1;edge2=end2-start2;offset=start1-start2
 aa=np.dot(edge1,edge1);bb=np.dot(edge1,edge2);cc=np.dot(edge2,edge2);dd=np.dot(edge1,offset);ee=np.dot(edge2,offset)
 denom=aa*cc-bb*bb
 candidates=[]
 if denom>1e-25:
  param1=(bb*ee-cc*dd)/denom;param2=(aa*ee-bb*dd)/denom
  if 0<=param1<=1 and 0<=param2<=1:candidates.append((param1,param2))
 candidates.extend([(0,np.clip(ee/cc,0,1)),(1,np.clip((ee+bb)/cc,0,1)),(np.clip(-dd/aa,0,1),0),(np.clip((bb-dd)/aa,0,1),1)])
 best=(float('inf'),None,None)
 for param1,param2 in candidates:
  point1=start1+param1*edge1;point2=start2+param2*edge2
  dist=np.dot(point1-point2,point1-point2)
  if dist<best[0]:best=(dist,point1,point2)
 return best

def surfaces_distance(data1,data2):
 best=(float('inf'),None,None,None)
 for index1,tri1 in enumerate(data1['triangles']):
  for index2,tri2 in enumerate(data2['triangles']):
   for point in tri1:
    dist,closest=point_triangle(point,tri2)
    if dist<best[0]:best=(dist,point,closest,(index1,index2,'vertex-face'))
   for point in tri2:
    dist,closest=point_triangle(point,tri1)
    if dist<best[0]:best=(dist,closest,point,(index1,index2,'face-vertex'))
   for edge_index1 in range(3):
    for edge_index2 in range(3):
     dist,point1,point2=segment_segment(tri1[edge_index1],tri1[(edge_index1+1)%3],tri2[edge_index2],tri2[(edge_index2+1)%3])
     if dist<best[0]:best=(dist,point1,point2,(index1,index2,'edge-edge'))
 return best
for name in ['Object_02','Object_04']:
 best=surfaces_distance(cache['Object_01'],cache[name]);cache[name]['closest']=best
 print('MINIMUM',name,math.sqrt(best[0]),'world points',best[1].tolist(),best[2].tolist(),'feature',best[3], 'target-frame points', (base_inv[:3,:3]@best[1]).tolist(),(base_inv[:3,:3]@best[2]).tolist())
