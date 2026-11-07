import bpy, json, numpy as np
from collections import Counter

def closest_pt_tri(p, a,b,c):
    ab=b-a; ac=c-a; ap=p-a
    d1=np.dot(ab,ap); d2=np.dot(ac,ap)
    if d1<=0 and d2<=0:return a
    bp=p-b; d3=np.dot(ab,bp); d4=np.dot(ac,bp)
    if d3>=0 and d4<=d3:return b
    vc=d1*d4-d3*d2
    if vc<=0 and d1>=0 and d3<=0:
        v=d1/(d1-d3); return a+v*ab
    cp=p-c; d5=np.dot(ab,cp); d6=np.dot(ac,cp)
    if d6>=0 and d5<=d6:return c
    vb=d5*d2-d1*d6
    if vb<=0 and d2>=0 and d6<=0:
        w=d2/(d2-d6); return a+w*ac
    va=d3*d6-d5*d4
    if va<=0 and d4-d3>=0 and d5-d6>=0:
        w=(d4-d3)/((d4-d3)+(d5-d6)); return b+w*(c-b)
    den=1/(va+vb+vc);return a+ab*(vb*den)+ac*(vc*den)

def closest_segments(p1,q1,p2,q2):
    d1=q1-p1; d2=q2-p2; r=p1-p2
    a=np.dot(d1,d1); e=np.dot(d2,d2); f=np.dot(d2,r)
    if a<=1e-30 and e<=1e-30:return p1,p2
    if a<=1e-30:s=0.;t=np.clip(f/e,0,1)
    else:
        c=np.dot(d1,r)
        if e<=1e-30:t=0.;s=np.clip(-c/a,0,1)
        else:
            b=np.dot(d1,d2); den=a*e-b*b
            s=np.clip((b*f-c*e)/den,0,1) if den>1e-30 else 0.
            t=(b*s+f)/e
            if t<0:t=0.;s=np.clip(-c/a,0,1)
            elif t>1:t=1.;s=np.clip((b-c)/a,0,1)
    return p1+d1*s,p2+d2*t

def seg_hit(p,q,a,b,c):
    d=q-p; e1=b-a; e2=c-a; h=np.cross(d,e2); det=np.dot(e1,h)
    if abs(det)<1e-14:return None
    inv=1/det; s=p-a; u=np.dot(s,h)*inv
    if u < -1e-12 or u>1+1e-12:return None
    qq=np.cross(s,e1); v=np.dot(d,qq)*inv
    if v < -1e-12 or u+v>1+1e-12:return None
    t=np.dot(e2,qq)*inv
    if t < -1e-12 or t>1+1e-12:return None
    return p+t*d

dg=bpy.context.evaluated_depsgraph_get(); geoms=[]; diagnostic=[]
for name in ['Object_01','Object_02']:
    eo=bpy.data.objects[name].evaluated_get(dg); m=eo.to_mesh(); m.calc_loop_triangles()
    vv=np.array([tuple(eo.matrix_world @ v.co) for v in m.vertices],dtype=np.float64)
    tt=np.array([tuple(t.vertices) for t in m.loop_triangles],dtype=int)
    inc=Counter()
    for p in m.polygons:
        for e in p.edge_keys:inc[tuple(sorted(e))]+=1
    ec=[inc.get(tuple(sorted(e.vertices)),0) for e in m.edges]
    diagnostic.append({'name':name,'world_vertices':vv.tolist(),'triangle_indices':tt.tolist(),'boundary_edges':sum(n==1 for n in ec),'non_manifold_edges_including_boundary':sum(n!=2 for n in ec),'more_than_2_faces':sum(n>2 for n in ec),'wire_edges':sum(n==0 for n in ec),'triangle_areas':[float(np.linalg.norm(np.cross(vv[t[1]]-vv[t[0]],vv[t[2]]-vv[t[0]]))/2) for t in tt]})
    geoms.append((vv,tt)); eo.to_mesh_clear()
best=(float('inf'),None,None,None); ties=[]; checked=0
for i,ia in enumerate(geoms[0][1]):
    aa=geoms[0][0][ia]
    for j,ib in enumerate(geoms[1][1]):
        bb=geoms[1][0][ib]; checked+=1
        pairs=[]
        for k in range(3):
            p=seg_hit(aa[k],aa[(k+1)%3],*bb)
            if p is not None:pairs.append((p,p,'edgeA-faceB'))
            p=seg_hit(bb[k],bb[(k+1)%3],*aa)
            if p is not None:pairs.append((p,p,'faceA-edgeB'))
        for p in aa:pairs.append((p,closest_pt_tri(p,*bb),'vertexA-faceB'))
        for p in bb:pairs.append((closest_pt_tri(p,*aa),p,'faceA-vertexB'))
        for k in range(3):
            for l in range(3):
                p,q=closest_segments(aa[k],aa[(k+1)%3],bb[l],bb[(l+1)%3]);pairs.append((p,q,'edge-edge'))
        for p,q,kind in pairs:
            ds=float(np.dot(q-p,q-p))
            if ds<best[0]:best=(ds,p,q,(i,j,kind))
        ds,p,q,kind=min((float(np.dot(q-p,q-p)),p,q,kind) for p,q,kind in pairs) if False else (None,None,None,None)
print(json.dumps({'geometry':diagnostic,'pairs_checked':checked,'distance':float(np.sqrt(best[0])),'distance_squared':best[0],'closest_point_Object_01':best[1].tolist(),'closest_point_Object_02':best[2].tolist(),'direction_Object_01_to_Object_02':((best[2]-best[1])/np.sqrt(best[0])).tolist() if best[0]>0 else None,'closest_triangles_and_kind':best[3]}))
