# Acquire each evaluated mesh once; keep only private numerical copies.
mesh_cache=[]
for obj in objs:
 evaluated=obj.evaluated_get(depsgraph)
 mesh=evaluated.to_mesh()
 try:
  mesh.calc_loop_triangles()
  local=np.array([tuple(v.co) for v in mesh.vertices],dtype=np.float64).reshape((-1,3))
  matrix=np.array(obj.matrix_world,dtype=np.float64)
  world=local @ matrix[:3,:3].T + matrix[:3,3]
  indices=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=np.int64).reshape((-1,3))
  triangles=world[indices]
  mesh_cache.append({'name':obj.name,'tri':triangles,'lo':triangles.min(axis=1) if len(triangles) else np.empty((0,3)), 'hi':triangles.max(axis=1) if len(triangles) else np.empty((0,3))})
 finally:
  evaluated.to_mesh_clear()
print('cached',len(mesh_cache),'triangles',sum(len(m['tri']) for m in mesh_cache))
def dot(first,second):
 return np.einsum('ij,ij->i',first,second)
def point_segment_sq(point,start,end):
 direction=end-start
 denom=dot(direction,direction)
 fraction=np.divide(dot(point-start,direction),denom,out=np.zeros_like(denom),where=denom>0)
 delta=point-(start+np.clip(fraction,0,1)[:,None]*direction)
 return dot(delta,delta)
def projection_inside(point,triangle):
 edge0=triangle[:,1]-triangle[:,0]
 edge1=triangle[:,2]-triangle[:,0]
 relative=point-triangle[:,0]
 normal=np.cross(edge0,edge1)
 normsq=dot(normal,normal)
 # Oriented edge half-spaces; projection on the plane is implicit.
 side0=dot(np.cross(edge0,relative),normal)
 side1=dot(np.cross(triangle[:,2]-triangle[:,1],point-triangle[:,1]),normal)
 side2=dot(np.cross(triangle[:,0]-triangle[:,2],point-triangle[:,2]),normal)
 inside=(normsq>0)&(side0>=0)&(side1>=0)&(side2>=0)
 return inside,normal,normsq

def point_triangle_sq(point,triangle):
 result=np.minimum.reduce([point_segment_sq(point,triangle[:,edge],triangle[:,(edge+1)%3]) for edge in range(3)])
 inside,normal,normsq=projection_inside(point,triangle)
 signed=dot(point-triangle[:,0],normal)
 plane_sq=np.divide(signed*signed,normsq,out=np.full_like(normsq,np.inf),where=normsq>0)
 return np.where(inside,np.minimum(result,plane_sq),result)

def segment_segment_sq(start0,end0,start1,end1):
 direction0=end0-start0; direction1=end1-start1; relative=start0-start1
 aa=dot(direction0,direction0); bb=dot(direction0,direction1); cc=dot(direction1,direction1)
 dd=dot(direction0,relative); ee=dot(direction1,relative)
 # Cross product avoids cancellation in nearly parallel edge determinants.
 cross=np.cross(direction0,direction1); determinant=dot(cross,cross)
 fraction0=np.divide(bb*ee-cc*dd,determinant,out=np.zeros_like(aa),where=determinant>0)
 fraction1=np.divide(aa*ee-bb*dd,determinant,out=np.zeros_like(aa),where=determinant>0)
 interior=(determinant>0)&(fraction0>=0)&(fraction0<=1)&(fraction1>=0)&(fraction1<=1)
 delta=relative+fraction0[:,None]*direction0-fraction1[:,None]*direction1
 result=np.minimum.reduce([point_segment_sq(start0,start1,end1),point_segment_sq(end0,start1,end1),point_segment_sq(start1,start0,end0),point_segment_sq(end1,start0,end0)])
 return np.where(interior,np.minimum(result,dot(delta,delta)),result)

def segment_hits_triangle(start,end,triangle):
 normal=np.cross(triangle[:,1]-triangle[:,0],triangle[:,2]-triangle[:,0])
 numerator=dot(triangle[:,0]-start,normal)
 denominator=dot(end-start,normal)
 fraction=np.divide(numerator,denominator,out=np.zeros_like(numerator),where=denominator!=0)
 point=start+fraction[:,None]*(end-start)
 inside,_,_=projection_inside(point,triangle)
 return (denominator!=0)&(fraction>=0)&(fraction<=1)&inside

def triangle_pair_sq(first,second):
 result=np.full(len(first),np.inf)
 hits=np.zeros(len(first),dtype=bool)
 for edge in range(3):
  result=np.minimum(result,point_triangle_sq(first[:,edge],second))
  result=np.minimum(result,point_triangle_sq(second[:,edge],first))
  hits|=segment_hits_triangle(first[:,edge],first[:,(edge+1)%3],second)
  hits|=segment_hits_triangle(second[:,edge],second[:,(edge+1)%3],first)
  for other_edge in range(3):
   result=np.minimum(result,segment_segment_sq(first[:,edge],first[:,(edge+1)%3],second[:,other_edge],second[:,(other_edge+1)%3]))
 return np.where(hits,0,result)

scale_mm=scene.unit_settings.scale_length*1000
threshold=2.0/scale_mm
results=[]; stats={'object_pairs':0,'object_box_excluded':0,'triangle_box_excluded_pairs':0,'tested_triangle_pairs':0,'empty_pairs':0}; failures=[]
for first_index,first in enumerate(mesh_cache):
 for second in mesh_cache[first_index+1:]:
  stats['object_pairs']+=1
  if not len(first['tri']) or not len(second['tri']):
   stats['empty_pairs']+=1; continue
  boxgap=np.maximum(np.maximum(first['lo'].min(axis=0)-second['hi'].max(axis=0),second['lo'].min(axis=0)-first['hi'].max(axis=0)),0)
  if np.linalg.norm(boxgap)>threshold+1e-12:
   stats['object_box_excluded']+=1; continue
  gaps=np.maximum(np.maximum(first['lo'][:,None,:]-second['hi'][None,:,:],second['lo'][None,:,:]-first['hi'][:,None,:]),0)
  selection=np.sum(gaps*gaps,axis=2)<=(threshold+1e-12)**2
  indices0,indices1=np.nonzero(selection)
  if not len(indices0):
   stats['triangle_box_excluded_pairs']+=1;continue
  values=triangle_pair_sq(first['tri'][indices0],second['tri'][indices1])
  stats['tested_triangle_pairs']+=len(values)
  if not np.isfinite(values).all(): failures.append((first['name'],second['name']))
  minimum=float(np.sqrt(values.min()))*scale_mm
  if minimum<=2.0+1e-9:
   results.append((first['name'],second['name'],minimum))
print('STATS',stats,'FAILURES',failures)
print('MATCHES',len(results))
for name0,name1,distance in results:
 print(name0,name1,format(distance,'.12f'),'mm')
for item in mesh_cache:
 tri=item['tri']; area_sq=dot(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]))
 print('geometry',item['name'],'triangles',len(tri),'degenerate',int(np.count_nonzero(area_sq==0)),'finite',bool(np.isfinite(tri).all()))