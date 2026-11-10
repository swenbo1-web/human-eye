from mathutils.geometry import closest_point_on_tri
# Fresh evaluated mesh comparison validates the per-call cached geometry.
for name,data in objs.items():
 eo=bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get()); me=eo.to_mesh(); me.calc_loop_triangles()
 current=np.array([tuple(eo.matrix_world @ vertex.co) for vertex in me.vertices]); current_t=np.array([tuple(tri.vertices) for tri in me.loop_triangles]); eo.to_mesh_clear()
 assert np.array_equal(current,data['v']) and np.array_equal(current_t,data['t']),name

def edges_of(data):
 return sorted({tuple(sorted((int(tri[index]),int(tri[(index+1)%3])))) for tri in data['t'] for index in range(3)})
def segment_pair(first,second,third,fourth):
 direction1=second-first; direction2=fourth-third; offset=first-third
 aa=direction1@direction1; bb=direction1@direction2; cc=direction2@direction2; dd=direction1@offset; ee=direction2@offset
 candidates=[]
 denominator=aa*cc-bb*bb
 if denominator>1e-25:
  ss=(bb*ee-cc*dd)/denominator; tt=(aa*ee-bb*dd)/denominator
  if 0<=ss<=1 and 0<=tt<=1: candidates.append((ss,tt))
 candidates.extend([(0,np.clip(ee/cc,0,1)),(1,np.clip((ee+bb)/cc,0,1)),(np.clip(-dd/aa,0,1),0),(np.clip((bb-dd)/aa,0,1),1)])
 pairs=[(first+ss*direction1,third+tt*direction2) for ss,tt in candidates]
 return min(pairs,key=lambda pair:np.sum((pair[0]-pair[1])**2))
def mesh_distance(first,second):
 best=(float('inf'),None,None,None)
 for src,dst,reverse in [(first,second,False),(second,first,True)]:
  for vi,point in enumerate(src['v']):
   for ti,tri in enumerate(dst['t']):
    nearest=np.array(closest_point_on_tri(Vector(point),*(Vector(dst['v'][idx]) for idx in tri)))
    distance=float(np.linalg.norm(point-nearest))
    if distance<best[0]: best=(distance,nearest if reverse else point,point if reverse else nearest,('vertex-face',reverse,vi,ti))
 for edge1 in edges_of(first):
  for edge2 in edges_of(second):
   point1,point2=segment_pair(*first['v'][list(edge1)],*second['v'][list(edge2)])
   distance=float(np.linalg.norm(point1-point2))
   if distance<best[0]: best=(distance,point1,point2,('edge-edge',edge1,edge2))
 return best
base=objs['Object_01']; base_bvh=BVHTree.FromPolygons(base['v'].tolist(),base['t'].tolist(),all_triangles=True,epsilon=0)
inv=np.linalg.inv(np.array(bpy.data.objects['Object_01'].matrix_world,dtype=float))
for name in ['Object_02','Object_03','Object_04']:
 data=objs[name]; tree=BVHTree.FromPolygons(data['v'].tolist(),data['t'].tolist(),all_triangles=True,epsilon=0)
 overlaps=base_bvh.overlap(tree)
 local=(np.column_stack((data['v'],np.ones(len(data['v']))))@inv.T)[:,:3]
 print(name,'surface triangle overlap count',len(overlaps),'candidate vertices in target frame',local.tolist())
 if not overlaps:
  print('minimum distance & world witness target,candidate,feature',mesh_distance(base,data))
