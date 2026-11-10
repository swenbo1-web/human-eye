def point_tri(point,tri):
 a,b,c=tri; ab=b-a; ac=c-a; normal=np.cross(ab,ac)
 proj=point-normal*(np.dot(point-a,normal)/np.dot(normal,normal))
 v=proj-a; aa=np.dot(ab,ab); bb=np.dot(ab,ac); cc=np.dot(ac,ac); va=np.dot(v,ab); vc=np.dot(v,ac); den=aa*cc-bb*bb
 u=(va*cc-vc*bb)/den; w=(vc*aa-va*bb)/den
 if u>=0 and w>=0 and u+w<=1: return proj
 choices=[]
 for start,end in [(a,b),(b,c),(c,a)]:
  delta=end-start; fraction=np.clip(np.dot(point-start,delta)/np.dot(delta,delta),0,1); near=start+fraction*delta; choices.append(near)
 return min(choices,key=lambda near:np.dot(point-near,point-near))
def edge_pair(a,b,c,d):
 u=b-a; v=d-c; w=a-c; aa=u@u; bb=u@v; cc=v@v; dd=u@w; ee=v@w; den=aa*cc-bb*bb
 opts=[]
 if den>1e-28:
  s=(bb*ee-cc*dd)/den; t=(aa*ee-bb*dd)/den
  if 0<=s<=1 and 0<=t<=1: opts.append((a+s*u,c+t*v))
 for p in [a,b]: opts.append((p,c+np.clip((p-c)@v/cc,0,1)*v))
 for q in [c,d]: opts.append((a+np.clip((q-a)@u/aa,0,1)*u,q))
 return min(opts,key=lambda pq:np.sum((pq[0]-pq[1])**2))
def all_edges(ts): return sorted({tuple(sorted((int(a),int(b)))) for tri in ts for a,b in zip(tri,np.roll(tri,-1))})
def mesh_gap(first,second):
 av,at=first; bv,bt=second; best=(float('inf'),None,None)
 def offer(p,q):
  nonlocal best
  dist=np.sum((p-q)**2)
  if dist<best[0]:best=(dist,p.copy(),q.copy())
 for p in av:
  for tri in bv[bt]:offer(p,point_tri(p,tri))
 for q in bv:
  for tri in av[at]:offer(point_tri(q,tri),q)
 for ai,aj in all_edges(at):
  for bi,bj in all_edges(bt):offer(*edge_pair(av[ai],av[aj],bv[bi],bv[bj]))
 return math.sqrt(best[0]),best[1],best[2]
def winding(point,mesh):
 vs,ts=mesh; t=vs[ts]-point; a,b,c=t[:,0],t[:,1],t[:,2]; la=np.linalg.norm(a,axis=1); lb=np.linalg.norm(b,axis=1); lc=np.linalg.norm(c,axis=1)
 return np.sum(2*np.arctan2(np.einsum('ij,ij->i',a,np.cross(b,c)),la*lb*lc+np.einsum('ij,ij->i',a,b)*lc+np.einsum('ij,ij->i',b,c)*la+np.einsum('ij,ij->i',c,a)*lb))/(4*np.pi)
for name in ['Object_02','Object_04']:
 dist,p,q=mesh_gap(base,geo[name]); print(name,'gap',format(dist,'.12f'),'target closest',p.tolist(),'candidate closest',q.tolist(),'vertex winding',[round(winding(v,base),8) for v in geo[name][0]])
name='Object_03'; center=geo[name][0].mean(0)
print(name,'center',center.tolist(),'target local center',(np.linalg.inv(np.array(objs['Object_01'].matrix_world))@np.r_[center,1]).tolist(),'target winding',winding(center,base),'self winding',winding(center,geo[name]),'vertices target winding',[round(winding(v,base),8) for v in geo[name][0]])
print('center to target surface',min(np.linalg.norm(center-point_tri(center,t)) for t in base[0][base[1]]))
for name in ['Object_02','Object_03','Object_04']:
 av=base[0]; bv=geo[name][0];print(name,'world AABB overlap',bool(np.all(av.max(0)>=bv.min(0)) and np.all(bv.max(0)>=av.min(0))))
