"""Finite source-bound reference-deviation views; independent of boundary tags.

Standalone Blender producer. Numeric deviations are supplied by a trusted
reference binding; images show current geometry and finite witness opportunity.
They do not prove damage intent or complete visibility of the region.
"""
import base64,hashlib,json,math,time

PROTOCOL='readonly-reference-feature-v1'
LIMITS=dict(vertices=4096,triangles=1024,objects=64,members=64,witnesses=3,candidates=2,
    ray_triangle_tests=16384,images=2,png_bytes=16*1024*1024)


def require(value,reason):
    if not value:raise ValueError('reference_view_'+reason)


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
def sub(a,b):return [x-y for x,y in zip(a,b)]
def dot(a,b):return math.fsum(x*y for x,y in zip(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def unit(v):
    length=math.hypot(*v);require(math.isfinite(length) and length>0,'degenerate_basis');return [x/length for x in v]
def check(deadline):require(type(deadline) is int and time.perf_counter_ns()<deadline,'deadline')


def geometry(packet,patch,native):
    require(type(patch) is dict and set(patch)=={'schema','object_id','object_instance','document_epoch','raw_sha256',
        'reference_raw_sha256','reference_ref','threshold_m','tessellation_sha256','members','witnesses','reference_normal'},'patch_fields')
    source=packet['source'];require(patch['schema']=='reference-feature-patch-v1'
        and all(patch[k]==source[k] for k in ('object_id','object_instance','document_epoch','raw_sha256')),'source_binding')
    require(patch['tessellation_sha256']==digest(dict(triangles=packet['triangles'],polygon_indices=packet['triangle_polygons'])),'tessellation_binding')
    members=patch['members'];raw=packet['raw'];nv=len(raw['vertices'])
    require(type(members) is list and 1<=len(members)<=64 and members==sorted(set(members))
        and all(type(i) is int and 0<=i<nv for i in members),'complete_members')
    objects=native['objects'];require(1<=len(objects)<=64 and sum(len(o['world_vertices']) for o in objects)<=4096
        and sum(len(o['faces']) for o in objects)<=1024,'complete_native_geometry_budget')
    target=next((o for o in objects if o['object_id']==source['object_id']),None);require(target is not None,'native_target')
    scale=raw['unit_scale'];matrix=raw['matrix_world'];metres=[row[:] for row in matrix]
    for i in range(3):metres[i][3]*=scale
    world=[[(sum(matrix[k][j]*p[j] for j in range(3))+matrix[k][3])*scale for k in range(3)] for p in raw['vertices']]
    require(target['local_vertices']==[[x*scale for x in p] for p in raw['vertices']]
        and target['matrix']==metres and target['world_vertices']==world and target['faces']==packet['triangles'],'raw_native_correspondence')
    selected=set(members);incident=[i for i,t in enumerate(packet['triangles']) if selected.intersection(t)]
    require(bool(incident),'region_context')
    witnesses=patch['witnesses'];require(type(witnesses) is list and 2<=len(witnesses)<=3,'witness_count')
    samples=[];seen=set()
    for w in witnesses:
        require(type(w) is dict and set(w)=={'triangle','reference_offset_m'} and type(w['triangle']) is int
            and w['triangle'] in incident and w['triangle'] not in seen,'witness_source')
        seen.add(w['triangle']);delta=w['reference_offset_m']
        require(type(delta) is list and len(delta)==3 and all(type(x) in (int,float) and math.isfinite(x) for x in delta)
            and math.hypot(*delta)>=patch['threshold_m'],'meaningful_witness')
        face=packet['triangles'][w['triangle']]
        samples.append(dict(triangle=w['triangle'],point=[math.fsum(world[i][k] for i in face)/3 for k in range(3)],delta=delta))
    points=[world[i] for i in members]+[sample['point'] for sample in samples]
    return points,samples


def frames(native,points,normal,scale):
    normal=unit(normal);axis=min(range(3),key=lambda k:abs(normal[k]));seed=[float(k==axis) for k in range(3)]
    tangent=unit(cross(seed,normal));all_points=[p for o in native['objects'] for p in o['world_vertices']]
    center=[min(p[k] for p in points)/2+max(p[k] for p in points)/2 for k in range(3)]
    global_center=[min(p[k] for p in all_points)/2+max(p[k] for p in all_points)/2 for k in range(3)]
    output=[]
    for sign in (1,-1):
        eye=unit([.5*normal[k]+sign*math.sqrt(.75)*tangent[k] for k in range(3)])
        right=unit([-eye[1],eye[0],0.]) if math.hypot(eye[0],eye[1])>0 else [-1.,0.,0.]
        up=unit(cross(eye,right))
        # World-AABB center need not be the projected midpoint. Enclose every
        # member/witness around the actual selected center, including skew ROI.
        span=3.2*max(abs(dot(sub(p,center),a)) for p in points for a in (right,up))
        overview=2.5*max(abs(dot(sub(p,global_center),a)) for p in all_points for a in (right,up))
        require(math.isfinite(span) and math.isfinite(overview) and span>0 and overview>0,'frame_span')
        def make(c,s):
            depths=[dot(sub(p,c),eye) for p in all_points];margin=max(s,max(depths)-min(depths))*.125;distance=max(depths)+margin
            return dict(center_bu=[x/scale for x in c],direction=eye,right=right,up=up,
                camera_location_bu=[(c[k]+eye[k]*distance)/scale for k in range(3)],ortho_scale_bu=s/scale,
                clip_start_bu=margin*.25/scale,clip_end_bu=(distance-min(depths)+margin)/scale)
        output.append(dict(ordinal=len(output),overview=make(global_center,overview),detail=make(center,span),
            span_m=span,overview_span_m=overview,right=right,up=up,eye=eye,
            camera_basis_supported=math.hypot(eye[0],eye[1])>=math.sin(math.radians(5))))
    return output


def visible_projected(native,sample,candidate,deadline):
    point=sample['point'];right,up,eye=(candidate[k] for k in ('right','up','eye'));hits=[];ambiguous=False
    eps=max(candidate['span_m']*1e-9,128*max(math.ulp(float(x)) for x in point))
    require(eps<candidate['span_m']/3072,'visibility_precision')
    for obj in native['objects']:
        for index,face in enumerate(obj['faces']):
            check(deadline);p=[[dot(sub(obj['world_vertices'][v],point),a) for a in (right,up,eye)] for v in face]
            require(len(p)==3,'native_triangles')
            if any(min(v[k] for v in p)>0 or max(v[k] for v in p)<0 for k in (0,1)):continue
            a,b,c=p;ab=sub(b,a);ac=sub(c,a);den=ab[0]*ac[1]-ab[1]*ac[0]
            if den==0:ambiguous=True;continue
            if abs(den)<=1e-12*max(abs(ab[0]*ac[1]),abs(ab[1]*ac[0])):ambiguous=True;continue
            v=(-a[0]*ac[1]+a[1]*ac[0])/den;w=(-ab[0]*a[1]+ab[1]*a[0])/den;u=1-v-w
            if min(u,v,w)<-1e-12:continue
            hits.append((math.fsum((u*a[2],v*b[2],w*c[2])),obj['object_id'],index))
    if ambiguous or not hits:return False
    depth=max(h[0] for h in hits);nearest={(name,index) for d,name,index in hits if abs(d-depth)<=eps}
    return abs(depth)<=eps and nearest=={(sample['object_id'],sample['triangle'])}


def plan(packet,patch,native,deadline,*,visibility=visible_projected):
    check(deadline);points,samples=geometry(packet,patch,native);candidates=frames(native,points,patch['reference_normal'],packet['raw']['unit_scale'])
    triangles=sum(len(o['faces']) for o in native['objects']);reserved=(2*len(candidates)+1)*len(samples)*triangles
    require(reserved<=LIMITS['ray_triangle_tests'],'combined_ray_budget');rows=[]
    for candidate in candidates:
        signals=[];visible=[]
        if not candidate['camera_basis_supported']:
            rows.append(dict(ordinal=candidate['ordinal'],signals=[],visible=[],qualified_visible=0,
                detail_span_m=candidate['span_m'],overview_span_m=candidate['overview_span_m'],
                reason='native_track_camera_within_five_degrees_of_pole'))
            continue
        for sample in samples:
            sample=dict(sample,object_id=patch['object_id'])
            displacement=math.hypot(dot(sample['delta'],candidate['right']),dot(sample['delta'],candidate['up']))
            detail_px=displacement*384/candidate['span_m'];overview_px=displacement*384/candidate['overview_span_m']
            center=[x*packet['raw']['unit_scale'] for x in candidate['detail']['center_bu']]
            inside=all(abs(dot(sub(sample['point'],center),a))<=candidate['span_m']*(.5-1/384) for a in (candidate['right'],candidate['up']))
            qualified=inside and detail_px>=2 and candidate['overview_span_m']/candidate['span_m']>=2 and overview_px<2
            seen=visibility(native,sample,candidate,deadline)
            signals.append(dict(triangle=sample['triangle'],detail_displacement_px=detail_px,overview_displacement_px=overview_px,qualified=qualified))
            visible.append(bool(seen and qualified))
        rows.append(dict(ordinal=candidate['ordinal'],signals=signals,visible=visible,qualified_visible=sum(visible),
            detail_span_m=candidate['span_m'],overview_span_m=candidate['overview_span_m']))
    eligible=[r for r in rows if r['qualified_visible']>=2]
    best=max(eligible,key=lambda r:(r['qualified_visible'],min(s['detail_displacement_px'] for s,v in zip(r['signals'],r['visible']) if v),-r['ordinal'])) if eligible else None
    supported=sum(c['camera_basis_supported'] for c in candidates)
    return dict(schema='reference-feature-view-plan-v1',candidates=rows,selected_ordinal=best['ordinal'] if best else None,
        reason='visible_projected_reference_change_gain' if best else 'no_verified_task_feature_gain',search_complete=True,
        source_member_count=len(patch['members']),witness_count=len(samples),producer_triangle_tests=supported*len(samples)*triangles,
        consumer_planned_triangle_tests=supported*len(samples)*triangles,consumer_actual_triangle_tests=len(samples)*triangles if best else 0,
        maximum_combined_triangle_tests=LIMITS['ray_triangle_tests'],reserved_combined_triangle_tests=reserved,
        interpretation='finite_displaced_surface_witnesses_not_complete_visibility_or_damage',execution_authority=False),candidates,samples


def observe(host,object_id,patch,request_id,deadline_ns):
    host._readonly_request_id(request_id);check(deadline_ns);require(deadline_ns<=time.perf_counter_ns()+30_000_000_000,'original_deadline')
    require(type(patch) is dict and len(json.dumps(patch,allow_nan=False).encode())<=3000,'input_budget')
    renderer=host._readonly_native_module();store=host._readonly_observation_store(create=True);now=time.perf_counter_ns()
    require(not store['quarantined'] and store['active_request_id'] is None,'read_channel_unavailable')
    store['seen']={k:v for k,v in store['seen'].items() if v>now};require(request_id not in store['seen'] and len(store['seen'])<128,'request_reused')
    store['seen'][request_id]=deadline_ns;store['active_request_id']=request_id;store['sequence']+=1
    audits=[];evidence=profile=None
    try:
        profile=host._patch_focus_module().display_profile(host,renderer)
        packet=host.capture_surface_source(request_id,object_id,deadline_ns);evidence=host.capture_readonly_evidence()
        planned,candidates,_=plan(packet,patch,evidence['native_scene'],deadline_ns);frames_out=[];total_bytes=0
        if planned['selected_ordinal'] is not None:
            selected=candidates[planned['selected_ordinal']]
            for kind in ('overview','detail'):
                check(deadline_ns);require(host._patch_focus_module().display_profile(host,renderer)==profile,'display_changed')
                frame_audits=[];proof=[]
                try:picture=host._readonly_render_view(renderer,store,'SCENE',frame=selected[kind],
                    coverage='all_native_vertices' if kind=='overview' else 'intentional_local_window',expected_evidence=evidence,audit_sink=frame_audits,frustum_sink=proof)
                finally:audits.extend(frame_audits)
                require(len(frame_audits)==len(proof)==1,'render_proof')
                data=base64.b64decode(picture['image_base64'],validate=True);total_bytes+=len(data);require(total_bytes<=LIMITS['png_bytes'],'png_budget')
                frames_out.append(dict(kind=kind,picture=picture,png_sha256=hashlib.sha256(data).hexdigest(),frustum=proof[0],audit=frame_audits[0],
                    frame=renderer._public_view_frame(selected[kind],packet['raw']['unit_scale'],'all_native_vertices' if kind=='overview' else 'intentional_local_window')))
        after=host.capture_surface_source(request_id,object_id,deadline_ns)
        require(after['source']['raw_sha256']==packet['source']['raw_sha256'] and host.capture_readonly_evidence()==evidence
            and host._patch_focus_module().display_profile(host,renderer)==profile,'source_or_display_changed')
        check(deadline_ns)
        return dict(protocol=PROTOCOL,request_id=request_id,object_id=object_id,patch=patch,packet=packet,evidence=evidence,display=profile,
            plan=planned,frames=frames_out,deadline_ns=deadline_ns,finished_ns=time.perf_counter_ns(),restored=True,read_only=True,execution_authority=False)
    except BaseException:
        if audits:
            try:restored=all(a['restored'] for a in audits) and host.capture_readonly_evidence()==evidence and host._patch_focus_module().display_profile(host,renderer)==profile
            except BaseException:restored=False
            if not restored:store['quarantined']=True;store['quarantine_reason']='reference_view_restoration_unconfirmed'
        raise
    finally:store['active_request_id']=None
