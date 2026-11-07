import json, math
for name,d in _objs.items():
 print(json.dumps({'name':name,'vertices':[list(v) for v in d['v']],'triangles':d['t'],'faces':d['f']}))

def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def add(a,b): return tuple(x+y for x,y in zip(a,b))
def mul(a,s): return tuple(x*s for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm(a): return math.sqrt(dot(a,a))
def point_triangle(p,a,b,c):
 ab=sub(b,a); ac=sub(c,a); ap=sub(p,a)
 d1=dot(ab,ap); d2=dot(ac,ap)
 if d1<=0 and d2<=0:return a
 bp=sub(p,b); d3=dot(ab,bp); d4=dot(ac,bp)
 if d3>=0 and d4<=d3:return b
 vc=d1*d4-d3*d2
 if vc<=0 and d1>=0 and d3<=0:return add(a,mul(ab,d1/(d1-d3)))
 cp=sub(p,c); d5=dot(ab,cp); d6=dot(ac,cp)
 if d6>=0 and d5<=d6:return c
 vb=d5*d2-d1*d6
 if vb<=0 and d2>=0 and d6<=0:return add(a,mul(ac,d2/(d2-d6)))
 va=d3*d6-d5*d4
 if va<=0 and d4-d3>=0 and d5-d6>=0:return add(b,mul(sub(c,b),(d4-d3)/((d4-d3)+(d5-d6))))
 den=1/(va+vb+vc)
 return add(a,add(mul(ab,vb*den),mul(ac,vc*den)))
def seg_seg(p1,q1,p2,q2):
 d1=sub(q1,p1); d2=sub(q2,p2); r=sub(p1,p2)
 a=dot(d1,d1); e=dot(d2,d2); f=dot(d2,r)
 clamp=lambda x:max(0.,min(1.,x))
 if a<=1e-30 and e<=1e-30:return p1,p2
 if a<=1e-30:s=0.; t=clamp(f/e)
 else:
  c=dot(d1,r)
  if e<=1e-30:t=0.; s=clamp(-c/a)
  else:
   b=dot(d1,d2); den=a*e-b*b
   s=clamp((b*f-c*e)/den) if den!=0 else 0.
   t=(b*s+f)/e
   if t<0:t=0.; s=clamp(-c/a)
   elif t>1:t=1.; s=clamp((b-c)/a)
 return add(p1,mul(d1,s)),add(p2,mul(d2,t))
def seg_tri(p,q,a,b,c):
 d=sub(q,p); e1=sub(b,a); e2=sub(c,a); h=cross(d,e2); det=dot(e1,h)
 if abs(det)<1e-16:return None
 s=sub(p,a); u=dot(s,h)/det
 if u < -1e-12 or u>1+1e-12:return None
 v=dot(d,cross(s,e1))/det
 if v < -1e-12 or u+v>1+1e-12:return None
 t=dot(e2,cross(s,e1))/det
 if t< -1e-12 or t>1+1e-12:return None
 return add(p,mul(d,t))
D=[]
for d in _objs.values():D.append([[tuple(map(float,d['v'][i])) for i in t] for t in d['t']])
best=None; pair_results=[]
for i,A in enumerate(D[0]):
 for j,B in enumerate(D[1]):
  cand=[]
  for k in range(3):
   p=A[k]; q=point_triangle(p,*B); cand.append((norm(sub(q,p)),p,q,'A_vertex_B_face',k))
   q=B[k]; p=point_triangle(q,*A); cand.append((norm(sub(q,p)),p,q,'B_vertex_A_face',k))
   hit=seg_tri(A[k],A[(k+1)%3],*B)
   if hit is not None:cand.append((0.,hit,hit,'A_edge_B_face',k))
   hit=seg_tri(B[k],B[(k+1)%3],*A)
   if hit is not None:cand.append((0.,hit,hit,'B_edge_A_face',k))
   for l in range(3):
    p,q=seg_seg(A[k],A[(k+1)%3],B[l],B[(l+1)%3]); cand.append((norm(sub(q,p)),p,q,'edge_edge',(k,l)))
  m=min(cand,key=lambda x:x[0]); pair_results.append({'triangles':[i,j],'minimum':m})
  if best is None or m[0]<best[0]:best=m+(i,j)
print(json.dumps({'pair_results':pair_results,'minimum':best,'direction':mul(sub(best[2],best[1]),1/best[0]) if best[0]>0 else None}))
