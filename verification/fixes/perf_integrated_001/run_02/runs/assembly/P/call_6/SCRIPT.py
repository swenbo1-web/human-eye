import bpy,json,math
from mathutils import Vector
from mathutils.geometry import closest_point_on_tri
DG=bpy.context.evaluated_depsgraph_get()
meshes={}
for name in ['Object_01','Object_02','Object_03','Object_04']:
 o=bpy.data.objects[name]; ev=o.evaluated_get(DG); me=ev.to_mesh(); me.calc_loop_triangles()
 vs=[o.matrix_world@v.co for v in me.vertices]; ts=[tuple(t.vertices) for t in me.loop_triangles]
 es=set(tuple(sorted((t[i],t[(i+1)%3]))) for t in ts for i in range(3))
 meshes[name]=(vs,ts,list(es))
def point_tri(p,a,b,c):
 q=closest_point_on_tri(p,a,b,c)
 return (p-q).length, p.copy(),q

def seg_seg(p1,q1,p2,q2):
 d1=q1-p1; d2=q2-p2; r=p1-p2
 a=d1.dot(d1);e=d2.dot(d2);f=d2.dot(r);b=d1.dot(d2);c=d1.dot(r)
 den=a*e-b*b
 s=max(0.,min(1.,(b*f-c*e)/den)) if abs(den)>1e-24 else 0.
 t=(b*s+f)/e
 if t<0: t=0.;s=max(0.,min(1.,-c/a))
 elif t>1: t=1.;s=max(0.,min(1.,(b-c)/a))
 x=p1+s*d1;y=p2+t*d2
 return (x-y).length,x,y

def winding(p,vs,ts):
 total=0.
 for ia,ib,ic in ts:
  a=vs[ia]-p;b=vs[ib]-p;c=vs[ic]-p
  la=a.length;lb=b.length;lc=c.length
  total+=2*math.atan2(a.dot(b.cross(c)),la*lb*lc+a.dot(b)*lc+b.dot(c)*la+c.dot(a)*lb)
 return total/(4*math.pi)

def segment_tri(p,q,a,b,c):
 d=q-p;e1=b-a;e2=c-a;h=d.cross(e2);det=e1.dot(h)
 if abs(det)<1e-14:return None
 s=p-a;u=s.dot(h)/det
 if u<-1e-7 or u>1+1e-7:return None
 qv=s.cross(e1);v=d.dot(qv)/det;t=e2.dot(qv)/det
 if v<-1e-7 or u+v>1+1e-7 or t<-1e-7 or t>1+1e-7:return None
 return [t,u,v,list(p+t*d)]
va,ta,ea=meshes['Object_01'];out=[]
for name in ['Object_02','Object_03','Object_04']:
 vb,tb,eb=meshes[name];best=(float('inf'),None,None,'')
 for p in va:
  for i,j,k in tb:
   d,x,y=point_tri(p,vb[i],vb[j],vb[k])
   if d<best[0]:best=(d,x,y,'target vertex to candidate triangle')
 for p in vb:
  for i,j,k in ta:
   d,y,x=point_tri(p,va[i],va[j],va[k])
   if d<best[0]:best=(d,x,y,'candidate vertex to target triangle')
 for i,j in ea:
  for k,l in eb:
   d,x,y=seg_seg(va[i],va[j],vb[k],vb[l])
   if d<best[0]:best=(d,x,y,'edge to edge')
 hits=[]
 for i,j in eb:
  for a,b,c in ta:
   h=segment_tri(vb[i],vb[j],va[a],va[b],va[c])
   if h:hits.append(h)
 for i,j in ea:
  for a,b,c in tb:
   h=segment_tri(va[i],va[j],vb[a],vb[b],vb[c])
   if h:hits.append(h)
 center=sum(vb,Vector())/len(vb)
 local=bpy.data.objects['Object_01'].matrix_world.inverted()
 out.append({'name':name,'surface_distance':0. if hits else best[0],'nearest_feature':best[3],'witness_target':list(best[1]),'witness_candidate':list(best[2]),'winding_at_candidate_vertices':[winding(p,va,ta) for p in vb],'winding_at_candidate_center':winding(center,va,ta),'intersection_count':len(hits),'intersection_examples':hits[:2],'target_local_bounds_of_candidate':[[min((local@p)[i] for p in vb),max((local@p)[i] for p in vb)] for i in range(3)]})
o=bpy.data.objects['Object_01']
print(json.dumps({'pairs':out,'target_local_vertices':[list(v.co) for v in o.data.vertices],'target_rotation_matrix':[list(r) for r in o.matrix_world.to_3x3()]}))
