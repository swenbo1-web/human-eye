"""Explicit dense-observation capability; legacy/default candidate stays separate."""
import math,time
from verification.nonplanar_patch_candidate import (
    dot,sub,cross,need,unit,axes,check,dot_interval,possible_objects,frame,
)
from verification.nonplanar_local_surface import (
    LocalSurfaceIndex,source_binding,local_hit,canonical_boundary,sample_owner,
)
from verification.nonplanar_triangle_index import IndexBudget,filter_view,AUTO_FACE_THRESHOLD

def object_bounds(objects,right,up,vertex_sink=None):
    if vertex_sink is None:
        # Preserve the pre-index small-scene computation and allocation path.
        bounds={}
        for obj in objects:
            axes_bounds=[]
            for axis in (right,up):
                intervals=[dot_interval(p,axis) for p in obj['world_vertices']]
                axes_bounds.append([min(v[0] for v in intervals),max(v[1] for v in intervals)])
            bounds[obj['object_id']]=axes_bounds
        return bounds
    bounds={}
    for obj in objects:
        axes_bounds=[]
        vertex_intervals=[] if vertex_sink is not None else None
        for axis in (right,up):
            intervals=[dot_interval(p,axis) for p in obj['world_vertices']]
            axes_bounds.append([min(v[0] for v in intervals),max(v[1] for v in intervals)])
            if vertex_intervals is not None:vertex_intervals.append(intervals)
        bounds[obj['object_id']]=axes_bounds
        if vertex_sink is not None:vertex_sink[obj['object_id']]=vertex_intervals
    return bounds

def projected_hit(native,point,right,up,direction,allowed_objects=None,*,with_depth=False,allowed_faces=None):
    """Projected barycentric depths, independent of verifier's 3D lines."""
    hits=[]
    for obj in native['objects']:
        if allowed_objects is not None and obj['object_id'] not in allowed_objects:continue
        triangles=(enumerate(obj['faces']) if allowed_faces is None or obj['object_id'] not in allowed_faces
             else ((index,obj['faces'][index]) for index in allowed_faces[obj['object_id']]))
        for index,face in triangles:
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
    return [(obj,index,z) if with_depth else (obj,index) for z,obj,index in hits if depth-z<=eps]

def choose(native,object_id,edges,deadline,*,max_tests=8192,max_locality_work=32768,locality_policy='strict_coplanar',
        acceleration='auto',index_limits=None):
    check(deadline);objects=native['objects']
    need(1<=len(objects)<=64 and sum(len(o['world_vertices']) for o in objects)<=4096
        and sum(len(o['faces']) for o in objects)<=2048,'geometry_budget')
    need(type(max_tests) is int and 0<=max_tests<=8192,'test_budget')
    need(len({o['object_id'] for o in objects})==len(objects),'unique_native_objects')
    binding=source_binding(native,object_id,edges)
    target=next(o for o in objects if o['object_id']==object_id);vertices=target['world_vertices']
    local_index=LocalSurfaceIndex(target,deadline,max_locality_work,locality_policy)
    need(3<=len(edges)<=64 and len({tuple(sorted(e)) for e in edges})==len(edges),'boundary_budget')
    degree={};adjacent={};normals=[]
    for a,b in edges:
        need(a!=b and 0<=a<len(vertices) and 0<=b<len(vertices),'edge_indices')
        degree[a]=degree.get(a,0)+1;degree[b]=degree.get(b,0)+1
        faces=[entry[0] for entry in local_index.links.get(tuple(sorted((a,b))),[])]
        need(len(faces)==1,'single_native_adjacent_triangle_required');adjacent[tuple((a,b))]=faces[0]
        p,q,r=[vertices[j] for j in target['faces'][faces[0]]]
        face_normal=unit(cross(sub(q,p),sub(r,p)));edge_length=math.hypot(*sub(vertices[a],vertices[b]))
        normals.append([edge_length*x for x in face_normal])
    need(all(v==2 for v in degree.values()),'closed_component_required')
    reached={edges[0][0]}
    for _ in edges:
        for a,b in edges:
            if a in reached or b in reached:reached.update((a,b))
    need(reached==set(degree),'single_component_required')
    normal=[math.fsum(n[k] for n in normals) for k in range(3)]
    need(math.hypot(*normal)>.1*sum(math.hypot(*n) for n in normals),'normal_cancellation_requires_charts')
    n=unit(normal);directions=[]
    for d in (n,[-x for x in n],[0.,0.,1.],[0.,1.,0.]):
        if not any(dot(d,old)>1-1e-10 for old in directions):directions.append(d)
    points=[vertices[i] for i in sorted(degree)];all_points=[p for o in objects for p in o['world_vertices']]
    need(all(type(x) in (int,float) and math.isfinite(x) for p in all_points for x in p),'finite_geometry')
    features=canonical_boundary(local_index,edges)
    center=[min(p[k] for p in points)/2+max(p[k] for p in points)/2 for k in range(3)]
    all_center=[min(p[k] for p in all_points)/2+max(p[k] for p in all_points)/2 for k in range(3)]
    counts={o['object_id']:len(o['faces']) for o in objects}
    need(acceleration in ('auto','off','force'),'acceleration_mode')
    threshold=1 if acceleration=='force' else AUTO_FACE_THRESHOLD
    indexed=acceleration!='off' and any(count>=threshold for count in counts.values())
    index_budget=IndexBudget(deadline,**(index_limits or {})) if indexed else None
    combined=box_work=projection_work=0;rows=[];search_complete=True
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
            samples=[],visible_count=0,reason='no_projection_gain',tests_reserved=0,local_surfaces=[])
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
        row['reason']='boundary_not_visible_enough';staged=[]
        for feature in features:
            a,b=feature['edge']
            dx,dy=sub(projected[b],projected[a]);length=math.hypot(dx,dy)
            if length<=6*span/384:row['reason']='edge_subpixel';break
            offset=[span/128*(-dy*right[k]+dx*up[k])/length for k in range(3)]
            for t in (.25,.5,.75):
                check(deadline);mid=[vertices[a][k]*(1-t)+vertices[b][k]*t for k in range(3)]
                pair=[[mid[k]+sign*offset[k] for k in range(3)] for sign in (-1,1)]
                staged.append(dict(edge=[a,b],source_edge=sample_owner(local_index,feature,t),pair=pair))
        if len(staged)!=len(features)*3:continue
        # Reserve both ends' broad-phase work before constructing intervals.
        boxes=len(staged)*2*len(objects)*2;projections=(len(all_points)+len(staged)*2)*2*2
        if box_work+boxes+(index_budget.node_tests_reserved if indexed else 0)>32768 or projection_work+projections>65536:
            row['reason']='broad_phase_budget_exhausted';search_complete=False;break
        box_work+=boxes;projection_work+=projections
        vertex_intervals={} if indexed else None
        bounds=object_bounds(objects,right,up,vertex_intervals)
        for sample in staged:
            sample['possible_objects']=[possible_objects(bounds,p,right,up) for p in sample['pair']]
        view_index=None
        if indexed:
            index_budget.box_limit=32768-box_work
            view_index=filter_view(native,staged,vertex_intervals,right,up,binding,counts,index_budget,dot_interval,threshold)
            if view_index is not None:
                row['acceleration']=view_index
                if not view_index['complete']:
                    row['reason']=view_index['reason'];search_complete=False;break
        if view_index is None:
            required=2*sum(counts[name] for s in staged for ids in s['possible_objects'] for name in ids)
        else:
            required=2*sum(len(view_index['queries'][s['index_queries'][side]]['filters'][name])
                if name in view_index['queries'][s['index_queries'][side]]['filters'] else counts[name]
                for s in staged for side,ids in enumerate(s['possible_objects']) for name in ids)
        if combined+required>max_tests:
            row['reason']='combined_budget_exhausted';search_complete=False;break
        combined+=required;row['tests_reserved']=required
        row['local_surfaces']=[local_index.proof(edge,4*span/128) for edge in edges]
        # The full ray reservation also bounds every possible front-hit
        # membership/distance check at producer and independent verifier.
        local_index.reserve(required)
        local_by_edge={tuple(sorted(proof['edge'])):proof for proof in row['local_surfaces']}
        for sample in staged:
            check(deadline);a,b=sample['edge'];pair=sample['pair']
            if view_index is None:
                hits=[projected_hit(native,p,right,up,d,ids,with_depth=True) for p,ids in zip(pair,sample['possible_objects'])]
            else:
                hits=[projected_hit(native,p,right,up,d,ids,with_depth=True,
                    allowed_faces=view_index['queries'][sample['index_queries'][side]]['filters'])
                    for side,(p,ids) in enumerate(zip(pair,sample['possible_objects']))]
            proof=local_by_edge[tuple(sorted(sample['source_edge']))]
            kinds=['open' if not h else 'local_surface' if local_hit(local_index,proof,p,d,h,object_id)
                else 'blocked' for p,h in zip(pair,hits)]
            visible=sorted(kinds)==['local_surface','open']
            row['samples'].append(dict(**sample,visible=visible))
            row['visible_count']+=visible
        if len(row['samples'])==len(features)*3 and row['visible_count']>=max(8,math.ceil(len(row['samples'])*2/3)):
            row['reason']='visible_boundary_gain'
    valid=[r for r in rows if r['reason']=='visible_boundary_gain']
    best=max(valid,key=lambda r:(r['visible_count'],r['projection']['detail_px']),default=None)
    if best:
        best['overview_frame']=frame(native,all_center,best['right'],best['up'],best['direction'],best['overview_span'])
        best['detail_frame']=frame(native,center,best['right'],best['up'],best['direction'],best['span'])
    result=dict(schema='verification-nonplanar-boundary-candidate-v3',selected=best,candidates=rows,
        native_binding_sha256=binding,binding_scope='native_verification_snapshot_only_not_raw_epoch_protocol',
        sampling_features=features,sampling_policy='three_per_exact_collinear_coplanar_feature',
        locality_work_reserved=local_index.work,max_locality_work=max_locality_work,
        locality_policy=locality_policy,
        search_complete=search_complete,combined_triangle_tests_reserved=combined,max_triangle_tests=max_tests,
        combined_box_tests_reserved=box_work+(index_budget.node_tests_reserved if indexed else 0),combined_projection_ops_reserved=projection_work,
        maximum_candidates=4,maximum_images=2,execution_authority=False)
    if indexed and index_budget.reservations:
        result.update(acceleration_mode=acceleration,index_build_reservations=index_budget.reservations,
            index_build_units_reserved=index_budget.build_reserved,index_node_slots_reserved=index_budget.nodes_reserved,
            index_node_tests_reserved=index_budget.node_tests_reserved,index_packet_bytes=index_budget.packet_bytes)
    return result
