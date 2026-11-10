target=cache['Object_01']; inv=np.linalg.inv(target['matrix'])
for n,d in cache.items():
 current=objs[n]
 assert np.array_equal(np.array(current.matrix_world,dtype=float),d['matrix']) and np.array_equal(np.array([tuple(v.co) for v in current.data.vertices]),d['local'])
 if n!='Object_01':
  rel=d['v']@inv[:3,:3].T+inv[:3,3]
  print(n,'in target frame',rel.tolist(),'range',rel.min(axis=0).tolist(),rel.max(axis=0).tolist(),'center',rel.mean(axis=0).tolist())
from collections import Counter
for n,d in cache.items():
 counts=Counter(tuple(sorted((int(a),int(b)))) for t in d['t'] for a,b in zip(t,np.roll(t,-1)))
 print(n,'edge multiplicities',dict(Counter(counts.values())))

def segclose(a,b,c,d):
 u=b-a; v=d-c; w=a-c
 aa=u@u; bb=u@v; cc=v@v; dd=u@w; ee=v@w
 den=aa*cc-bb*bb
 choices=[]
 if den>1e-24:
  s=(bb*ee-cc*dd)/den; t=(aa*ee-bb*dd)/den
  if 0<=s<=1 and 0<=t<=1: choices.append((a+s*u,c+t*v))
 for p in (a,b): choices.append((p,c+np.clip((p-c)@v/cc,0,1)*v))
 for p in (c,d): choices.append((a+np.clip((p-a)@u/aa,0,1)*u,p))
 return min(choices,key=lambda pair:np.sum((pair[0]-pair[1])**2))
def pointtri(p,t):
 a,b,c=t; u=b-a; v=c-a; normal=np.cross(u,v); normal/=np.linalg.norm(normal)
 q=p-((p-a)@normal)*normal
 uu=u@u; uv=u@v; vv=v@v; qu=(q-a)@u; qv=(q-a)@v
 den=uu*vv-uv*uv; s=(vv*qu-uv*qv)/den; r=(uu*qv-uv*qu)/den
 if s>=-1e-14 and r>=-1e-14 and s+r<=1+1e-14: return q
 choices=[]
 for x,y in ((a,b),(b,c),(c,a)):
  edge=y-x; choices.append(x+np.clip((p-x)@edge/(edge@edge),0,1)*edge)
 return min(choices,key=lambda q:np.sum((p-q)**2))
for n in ['Object_02','Object_04']:
 best=(float('inf'),None)
 for ti,ids in enumerate(target['t']):
  ta=target['v'][ids]
  for tj,jds in enumerate(cache[n]['t']):
   tb=cache[n]['v'][jds]
   pairs=[(p,pointtri(p,tb)) for p in ta]+[(pointtri(p,ta),p) for p in tb]
   pairs += [segclose(ta[i],ta[(i+1)%3],tb[j],tb[(j+1)%3]) for i in range(3) for j in range(3)]
   for p,q in pairs:
    ds=float((p-q)@(p-q))
    if ds<best[0]: best=(ds,(ti,tj,p.tolist(),q.tolist()))
 print('minimum_surface_distance',n,math.sqrt(best[0]),'triangles_and_world_witness',best[1])