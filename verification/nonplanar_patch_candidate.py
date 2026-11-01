"""Verification-only bounded 3D boundary view candidate. No runtime authority."""
import math,time


def dot(a,b):return math.fsum(x*y for x,y in zip(a,b))
def sub(a,b):return [x-y for x,y in zip(a,b)]
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def need(test,reason):
    if not test:raise ValueError('nonplanar_'+reason)
def unit(v):
    length=math.hypot(*v);need(math.isfinite(length) and length>1e-15,'degenerate_direction')
    return [x/length for x in v]
def axes(direction):
    d=unit(direction);r=[-d[1],d[0],0.] if math.hypot(d[0],d[1])>1e-10 else [-1.,0.,0.]
    r=unit(r);return r,cross(d,r),d
def check(deadline):need(time.perf_counter_ns()<deadline,'deadline')


def projected_hit(native,point,right,up,direction):
    """Projected barycentric depths, independent of verifier's 3D lines."""
    hits=[]
    for obj in native['objects']:
        for index,face in enumerate(obj['faces']):
            a,b,c=[sub(obj['world_vertices'][i],point) for i in face]
            p,q,s=[[dot(v,axis) for axis in (right,up,direction)] for v in (a,b,c)]
            if not (min(p[0],q[0],s[0])<=0<=max(p[0],q[0],s[0])
                and min(p[1],q[1],s[1])<=0<=max(p[1],q[1],s[1])):continue
            x,y=q[0]-p[0],q[1]-p[1];u,v=s[0]-p[0],s[1]-p[1];den=x*v-y*u
            need(abs(den)>1e-12*max(math.hypot(x,y)*math.hypot(u,v),1e-300),'edge_on_ray_uncertain')
            b0=(-p[0]*v+p[1]*u)/den;b1=(-x*p[1]+y*p[0])/den
            if min(b0,b1,1-b0-b1)<-1e-12:continue
            depth=math.fsum((p[2]*(1-b0-b1),q[2]*b0,s[2]*b1))
            need(math.isfinite(depth),'nonfinite_depth');hits.append((depth,obj['object_id'],index))
    if not hits:return []
    depth=max(h[0] for h in hits);eps=1e-9*max(1.,abs(depth))
    return [(obj,index) for z,obj,index in hits if depth-z<=eps]


def frame(native,center,right,up,direction,span):
    points=[p for o in native['objects'] for p in o['world_vertices']]
    depths=[dot(sub(p,center),direction) for p in points]
    margin=max(span,max(depths)-min(depths))*.125;distance=max(depths)+margin
    return dict(center_bu=center,direction=direction,right=right,up=up,
        camera_location_bu=[center[k]+direction[k]*distance for k in range(3)],
        ortho_scale_bu=span,clip_start_bu=margin*.25,clip_end_bu=distance-min(depths)+margin)


def choose(native,object_id,edges,deadline,*,max_tests=8192):
    check(deadline);objects=native['objects']
    need(1<=len(objects)<=64 and sum(len(o['world_vertices']) for o in objects)<=4096
        and sum(len(o['faces']) for o in objects)<=2048,'geometry_budget')
    need(type(max_tests) is int and 0<=max_tests<=8192,'test_budget')
    target=next(o for o in objects if o['object_id']==object_id);vertices=target['world_vertices']
    need(3<=len(edges)<=64 and len({tuple(sorted(e)) for e in edges})==len(edges),'boundary_budget')
    degree={};adjacent={};normals=[]
    for a,b in edges:
        need(a!=b and 0<=a<len(vertices) and 0<=b<len(vertices),'edge_indices')
        degree[a]=degree.get(a,0)+1;degree[b]=degree.get(b,0)+1
        faces=[i for i,f in enumerate(target['faces']) if a in f and b in f]
        need(len(faces)==1,'single_native_adjacent_triangle_required');adjacent[tuple((a,b))]=faces[0]
        p,q,r=[vertices[j] for j in target['faces'][faces[0]]]
        normals.append(cross(sub(q,p),sub(r,p)))
    need(all(v==2 for v in degree.values()),'closed_component_required')
    reached={edges[0][0]}
    for _ in edges:
        for a,b in edges:
            if a in reached or b in reached:reached.update((a,b))
    need(reached==set(degree),'single_component_required')
    normal=[math.fsum(n[k] for n in normals) for k in range(3)]
    need(math.hypot(*normal)>.1*sum(math.hypot(*n) for n in normals),'normal_cancellation_requires_charts')
    n=unit(normal);directions=[]
    for d in ([0.,0.,1.],n,[-x for x in n],[0.,1.,0.]):
        if not any(dot(d,old)>1-1e-10 for old in directions):directions.append(d)
    points=[vertices[i] for i in sorted(degree)];all_points=[p for o in objects for p in o['world_vertices']]
    need(all(type(x) in (int,float) and math.isfinite(x) for p in all_points for x in p),'finite_geometry')
    center=[min(p[k] for p in points)/2+max(p[k] for p in points)/2 for k in range(3)]
    all_center=[min(p[k] for p in all_points)/2+max(p[k] for p in all_points)/2 for k in range(3)]
    triangle_count=sum(len(o['faces']) for o in objects);combined=0;rows=[];search_complete=True
    for d in directions:
        check(deadline);right,up,d=axes(d)
        projected={i:[dot(sub(vertices[i],center),axis) for axis in (right,up)] for i in degree}
        widths=[max(p[k] for p in projected.values())-min(p[k] for p in projected.values()) for k in (0,1)]
        span=1.6*max(widths);min_width=min(widths)
        overview_span=2.5*max(abs(dot(sub(p,all_center),axis)) for p in all_points for axis in (right,up))
        need(span>0 and overview_span>0 and math.isfinite(span+overview_span),'degenerate_projection')
        need(min_width>64*max(math.ulp(float(x)) for p in points for x in p) or min_width==0,'unrepresentable_feature')
        row=dict(direction=d,right=right,up=up,center=center,span=span,overview_span=overview_span,
            projection=dict(overview_px=384*min_width/overview_span,detail_px=384*min_width/span),
            samples=[],visible_count=0,reason='no_projection_gain',tests_reserved=0)
        rows.append(row)
        if not (row['projection']['overview_px']<16<=row['projection']['detail_px'] and overview_span/span>=2):continue
        # Reject overlapping non-neighbour edges in this projection.
        ambiguous=False
        def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        for i,(a,b) in enumerate(edges):
            for c,e in edges[i+1:]:
                if {a,b}&{c,e}:continue
                p,q,r,s=[projected[j] for j in (a,b,c,e)]
                if any(max(p[k],q[k])<min(r[k],s[k]) or max(r[k],s[k])<min(p[k],q[k]) for k in (0,1)):continue
                eps=span*span*1e-12;o=[orient(p,q,r),orient(p,q,s),orient(r,s,p),orient(r,s,q)]
                if min(o[:2])<=eps and max(o[:2])>=-eps and min(o[2:])<=eps and max(o[2:])>=-eps:ambiguous=True
        if ambiguous:row['reason']='ambiguous_projected_boundary';continue
        required=len(edges)*3*2*triangle_count*2
        if combined+required>max_tests:
            row['reason']='combined_budget_exhausted';search_complete=False;break
        combined+=required;row['tests_reserved']=required;row['reason']='boundary_not_visible_enough'
        for a,b in edges:
            dx,dy=sub(projected[b],projected[a]);length=math.hypot(dx,dy)
            if length<=6*span/384:row['reason']='edge_subpixel';break
            offset=[span/128*(-dy*right[k]+dx*up[k])/length for k in range(3)]
            for t in (.25,.5,.75):
                check(deadline);mid=[vertices[a][k]*(1-t)+vertices[b][k]*t for k in range(3)]
                pair=[[mid[k]+sign*offset[k] for k in range(3)] for sign in (-1,1)]
                hits=[projected_hit(native,p,right,up,d) for p in pair];expected={(object_id,adjacent[(a,b)])}
                kinds=['open' if not h else 'local_surface' if set(h)==expected else 'blocked' for h in hits]
                visible=sorted(kinds)==['local_surface','open']
                row['samples'].append(dict(edge=[a,b],pair=pair,visible=visible))
                row['visible_count']+=visible
        if len(row['samples'])==len(edges)*3 and row['visible_count']>=max(8,math.ceil(len(row['samples'])*2/3)):
            row['reason']='visible_boundary_gain'
    valid=[r for r in rows if r['reason']=='visible_boundary_gain']
    best=max(valid,key=lambda r:(r['visible_count'],r['projection']['detail_px']),default=None)
    if best:
        best['overview_frame']=frame(native,all_center,best['right'],best['up'],best['direction'],best['overview_span'])
        best['detail_frame']=frame(native,center,best['right'],best['up'],best['direction'],best['span'])
    return dict(schema='verification-nonplanar-boundary-candidate-v1',selected=best,candidates=rows,
        search_complete=search_complete,combined_triangle_tests_reserved=combined,max_triangle_tests=max_tests,
        maximum_candidates=4,maximum_images=2,execution_authority=False)
