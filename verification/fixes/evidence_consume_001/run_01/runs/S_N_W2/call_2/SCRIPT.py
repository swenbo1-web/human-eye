import math, json
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def mul(a,s):return tuple(x*s for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def clamp(x):return max(0.,min(1.,x))
def segseg(p1,q1,p2,q2):
    d1=sub(q1,p1);d2=sub(q2,p2);r=sub(p1,p2)
    a=dot(d1,d1);e=dot(d2,d2);f=dot(d2,r)
    if a<=1e-30 and e<=1e-30:return p1,p2
    if a<=1e-30:s=0.;t=clamp(f/e)
    else:
        c=dot(d1,r)
        if e<=1e-30:t=0.;s=clamp(-c/a)
        else:
            b=dot(d1,d2);den=a*e-b*b
            s=clamp((b*f-c*e)/den) if den>1e-30 else 0.
            t=(b*s+f)/e
            if t<0.:t=0.;s=clamp(-c/a)
            elif t>1.:t=1.;s=clamp((b-c)/a)
    return add(p1,mul(d1,s)),add(p2,mul(d2,t))
def pointtri(p,a,b,c):
    ab=sub(b,a);ac=sub(c,a);ap=sub(p,a)
    d1=dot(ab,ap);d2=dot(ac,ap)
    if d1<=0 and d2<=0:return a
    bp=sub(p,b);d3=dot(ab,bp);d4=dot(ac,bp)
    if d3>=0 and d4<=d3:return b
    vc=d1*d4-d3*d2
    if vc<=0 and d1>=0 and d3<=0:return add(a,mul(ab,d1/(d1-d3)))
    cp=sub(p,c);d5=dot(ab,cp);d6=dot(ac,cp)
    if d6>=0 and d5<=d6:return c
    vb=d5*d2-d1*d6
    if vb<=0 and d2>=0 and d6<=0:return add(a,mul(ac,d2/(d2-d6)))
    va=d3*d6-d5*d4
    if va<=0 and d4-d3>=0 and d5-d6>=0:return add(b,mul(sub(c,b),(d4-d3)/((d4-d3)+(d5-d6))))
    inv=1./(va+vb+vc)
    return add(a,add(mul(ab,vb*inv),mul(ac,vc*inv)))
def segtri(p,q,a,b,c):
    d=sub(q,p);e1=sub(b,a);e2=sub(c,a);h=cross(d,e2);det=dot(e1,h)
    if abs(det)<1e-25:return None
    inv=1./det;s=sub(p,a);u=dot(s,h)*inv
    if u < -1e-13 or u > 1+1e-13:return None
    z=cross(s,e1);v=dot(d,z)*inv
    if v < -1e-13 or u+v>1+1e-13:return None
    t=dot(e2,z)*inv
    if t < -1e-13 or t > 1+1e-13:return None
    return add(p,mul(d,t))
A=Object_01;B=Object_02
best=(float('inf'),None,None,None)
candidates=[];intersections=[]
def consider(p,q,kind,i,j):
    global best
    ds=dot(sub(q,p),sub(q,p));record=(ds,p,q,(kind,i,j))
    candidates.append(record)
    if ds<best[0]:best=record
for i,ai in enumerate(A['triangles']):
    at=[A['vertices'][v] for v in ai]
    for j,bi in enumerate(B['triangles']):
        bt=[B['vertices'][v] for v in bi]
        for k in range(3):
            consider(at[k],pointtri(at[k],*bt),'A_vertex_to_B_face',i,j)
            consider(pointtri(bt[k],*at),bt[k],'A_face_to_B_vertex',i,j)
            x=segtri(at[k],at[(k+1)%3],*bt)
            if x is not None:intersections.append((i,j,'Aedge_Bface',x));consider(x,x,'intersection',i,j)
            x=segtri(bt[k],bt[(k+1)%3],*at)
            if x is not None:intersections.append((i,j,'Bedge_Aface',x));consider(x,x,'intersection',i,j)
            for l in range(3):
                p,q=segseg(at[k],at[(k+1)%3],bt[l],bt[(l+1)%3])
                consider(p,q,'edge_edge',i,j)
d=math.sqrt(best[0]);p=best[1];q=best[2]
direction=mul(sub(q,p),1/d) if d else None
res={'distance_m':d,'direction_A_to_B':direction,'point_A':p,'point_B':q,'best_kind_triangles':best[3],'triangle_pairs':len(A['triangles'])*len(B['triangles']),'candidate_count':len(candidates),'intersection_count':len(intersections),'closest_candidates':[v for v in sorted(candidates,key=lambda x:x[0])[:12]],'geometry':{'Object_01':A,'Object_02':B}}
print(json.dumps(res))
