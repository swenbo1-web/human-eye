def closest_on_triangle(point, tri):
    aa, bb, cc=tri
    ab=bb-aa; ac=cc-aa; ap=point-aa
    d1=np.dot(ab,ap); d2=np.dot(ac,ap)
    if d1<=0 and d2<=0: return aa
    bp=point-bb; d3=np.dot(ab,bp); d4=np.dot(ac,bp)
    if d3>=0 and d4<=d3: return bb
    vc=d1*d4-d3*d2
    if vc<=0 and d1>=0 and d3<=0: return aa+(d1/(d1-d3))*ab
    cp=point-cc; d5=np.dot(ab,cp); d6=np.dot(ac,cp)
    if d6>=0 and d5<=d6: return cc
    vb=d5*d2-d1*d6
    if vb<=0 and d2>=0 and d6<=0: return aa+(d2/(d2-d6))*ac
    va=d3*d6-d5*d4
    if va<=0 and d4-d3>=0 and d5-d6>=0: return bb+((d4-d3)/((d4-d3)+(d5-d6)))*(cc-bb)
    denominator=1/(va+vb+vc)
    return aa+ab*(vb*denominator)+ac*(vc*denominator)
def closest_segments(p1,q1,p2,q2):
    first=q1-p1; second=q2-p2; offset=p1-p2
    aa=np.dot(first,first); ee=np.dot(second,second); ff=np.dot(second,offset)
    if aa==0 and ee==0: return p1,p2
    if aa==0: ss=0.; tt=np.clip(ff/ee,0,1)
    else:
        cc=np.dot(first,offset)
        if ee==0: tt=0.; ss=np.clip(-cc/aa,0,1)
        else:
            bb=np.dot(first,second); denominator=aa*ee-bb*bb
            ss=np.clip((bb*ff-cc*ee)/denominator,0,1) if denominator>0 else 0.
            tt=(bb*ss+ff)/ee
            if tt<0: tt=0.; ss=np.clip(-cc/aa,0,1)
            elif tt>1: tt=1.; ss=np.clip((bb-cc)/aa,0,1)
    return p1+ss*first,p2+tt*second
def segment_triangle_hit(start,end,tri):
    edge1=tri[1]-tri[0]; edge2=tri[2]-tri[0]; direction=end-start
    h=np.cross(direction,edge2); det=np.dot(edge1,h)
    if det==0: return None
    inv=1/det; rel=start-tri[0]; uu=np.dot(rel,h)*inv
    if uu<0 or uu>1: return None
    cross=np.cross(rel,edge1); vv=np.dot(direction,cross)*inv
    if vv<0 or uu+vv>1: return None
    tt=np.dot(edge2,cross)*inv
    if 0<=tt<=1: return start+tt*direction
    return None
edges=[(0,1),(1,2),(2,0)]
def triangle_distance(first,second):
    best=(float('inf'),None,None)
    for start,end in edges:
        hit=segment_triangle_hit(first[start],first[end],second)
        if hit is not None: return (0.,hit,hit)
        hit=segment_triangle_hit(second[start],second[end],first)
        if hit is not None: return (0.,hit,hit)
    for point in first:
        other=closest_on_triangle(point,second); delta=point-other; dist=np.dot(delta,delta)
        if dist<best[0]: best=(dist,point,other)
    for point in second:
        other=closest_on_triangle(point,first); delta=point-other; dist=np.dot(delta,delta)
        if dist<best[0]: best=(dist,other,point)
    for aa,bb in edges:
        for cc,dd in edges:
            point,other=closest_segments(first[aa],first[bb],second[cc],second[dd]); delta=point-other; dist=np.dot(delta,delta)
            if dist<best[0]: best=(dist,point,other)
    return best
started=time.time()
target=geo['Mesh_D17AB2']['tri']
results={}
for name,data in geo.items():
    if name=='Mesh_D17AB2': continue
    best=(float('inf'),None,None,None,None)
    tested=0
    for first_index,first in enumerate(target):
        for second_index,second in enumerate(data['tri']):
            separation=np.maximum(np.maximum(first.min(axis=0)-second.max(axis=0),second.min(axis=0)-first.max(axis=0)),0)
            if np.dot(separation,separation)>best[0]: continue
            candidate=triangle_distance(first,second); tested+=1
            if candidate[0]<best[0]: best=(*candidate,first_index,second_index)
    results[name]=best
    print(name,'mm',math.sqrt(best[0])*1000,'points_world',best[1].tolist(),best[2].tolist(),'triangles',best[3:],'tested',tested)
print('seconds',time.time()-started)
