"""Finite XY boundary observation producer, loaded from pinned bytes in Blender.

Only geometry and actual display state drive this candidate. No fixture/oracle,
action episode or model inference is imported. Sampling is an opportunity test,
not a certificate of damage, complete visibility or semantic image usefulness.
"""
from __future__ import annotations
import base64
import hashlib
import json
import math
import time

PROTOCOL = 'readonly-planar-patch-v1'
LIMITS = dict(vertices=4096, triangles=2048, objects=64, members=64,
              ray_triangle_tests=8192, images=2, png_bytes=16*1024*1024)


def require(condition, reason):
    if not condition:raise ValueError('patch_'+reason)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
                                    ensure_ascii=False,allow_nan=False).encode('utf8')).hexdigest()


def checkpoint(deadline):
    require(type(deadline) is int and time.perf_counter_ns()<deadline,'deadline_expired')


def display_profile(host, renderer=None):
    """Read every mesh/layer, including hidden ones; never silently omit one."""
    scene=host.scene;layer=host.view_layer;shade=scene.display.shading
    renderer=renderer or host._readonly_native_module()
    objects=host._objects(host._depsgraph())
    require(1<=len(objects)<=LIMITS['objects'],'object_budget')
    require(sum(len(o.data.vertices) for o in objects)<=LIMITS['vertices'],'vertex_budget')
    require(sum(len(o.data.polygons) for o in objects)<=LIMITS['triangles'],'polygon_budget')
    require(sum(max(0,len(p.vertices)-2) for o in objects for p in o.data.polygons)
            <=LIMITS['triangles'],'triangle_budget')
    rows=[]
    for obj in objects:
        row=dict(object_id=host.object_id(obj),object_uid=int(obj.session_uid),mesh_uid=int(obj.data.session_uid),
            hide_render=bool(obj.hide_render),hide_viewport=bool(obj.hide_viewport),
            hidden=bool(obj.hide_get(view_layer=layer)),visible=bool(obj.visible_get(view_layer=layer)),
            show_in_front=bool(obj.show_in_front),display_type=obj.display_type,alpha=float(obj.color[3]))
        rows.append(row)
    layers=[];pending=[layer.layer_collection]
    while pending:
        lc=pending.pop();require(len(layers)<256,'layer_budget')
        layers.append(dict(uid=int(lc.collection.session_uid),exclude=bool(lc.exclude),
            hide_viewport=bool(lc.hide_viewport),collection_hide_render=bool(lc.collection.hide_render),
            collection_hide_viewport=bool(lc.collection.hide_viewport),holdout=bool(lc.holdout),
            indirect_only=bool(lc.indirect_only)))
        require(len(pending)+len(lc.children)+len(layers)<=256,'layer_budget')
        pending.extend(lc.children)
    sequence=scene.sequence_editor
    strips=getattr(sequence,'strips',getattr(sequence,'sequences_all',None)) if sequence is not None else []
    require(strips is not None,'sequence_inventory_unavailable')
    profile=dict(schema='patch-display-v1',objects=sorted(rows,key=lambda x:x['object_id']),
        layers=layers,view_layer=layer.name,show_xray=bool(shade.show_xray),
        show_xray_wireframe=bool(shade.show_xray_wireframe),show_backface_culling=bool(shade.show_backface_culling),
        compositor=(getattr(scene,'compositing_node_group',None) is not None or getattr(scene,'node_tree',None) is not None),
        sequencer=bool(len(strips)),render_compositing=bool(scene.render.use_compositing),
        render_sequencer=bool(scene.render.use_sequencer),
        view_layer_use=bool(layer.use),render_engine='BLENDER_WORKBENCH',color_policy='opaque_OBJECT',
        display_scalars=renderer._scalar_state(scene.display,()),shading_scalars=renderer._scalar_state(shade,()))
    validate_profile(profile,{r['object_id'] for r in rows})
    return profile


def validate_profile(profile, ids):
    require(type(profile) is dict and set(profile)=={'schema','objects','layers','view_layer','show_xray',
        'show_xray_wireframe','show_backface_culling','compositor','sequencer','view_layer_use',
        'render_engine','color_policy','render_compositing','render_sequencer','display_scalars','shading_scalars'},'display_fields')
    for key in ('display_scalars','shading_scalars'):
        require(type(profile[key]) is dict and 1<=len(profile[key])<=256
            and len(json.dumps(profile[key],allow_nan=False))<=65536,'display_scalar_budget')
    require(profile['schema']=='patch-display-v1' and profile['render_engine']=='BLENDER_WORKBENCH'
        and profile['color_policy']=='opaque_OBJECT' and type(profile['view_layer']) is str
        and profile['view_layer_use'] is True and all(type(profile[k]) is bool for k in
            ('render_compositing','render_sequencer')),'display_policy')
    require(all(profile[k] is False for k in ('show_xray','show_xray_wireframe','show_backface_culling',
                                            'compositor','sequencer')),'unsupported_display')
    rows=profile['objects'];require(type(rows) is list and 1<=len(rows)<=64,'display_object_budget')
    found=[]
    for row in rows:
        require(type(row) is dict and set(row)=={'object_id','object_uid','mesh_uid','hide_render','hide_viewport',
            'hidden','visible','show_in_front','display_type','alpha'},'display_object_fields')
        require(type(row['object_id']) is str and all(type(row[k]) is int and row[k]>0 for k in
            ('object_uid','mesh_uid')) and type(row['alpha']) in (float,int) and row['alpha']==1
            and row['display_type'] in ('SOLID','TEXTURED') and row['visible'] is True
            and all(row[k] is False for k in ('hide_render','hide_viewport','hidden','show_in_front')),
            'unsupported_object_display')
        found.append(row['object_id'])
    require(len(set(found))==len(found) and set(found)==ids,'display_geometry_coverage')
    require(type(profile['layers']) is list and 1<=len(profile['layers'])<=256,'display_layers')
    for row in profile['layers']:
        require(type(row) is dict and set(row)=={'uid','exclude','hide_viewport','collection_hide_render',
            'collection_hide_viewport','holdout','indirect_only'} and type(row['uid']) is int and row['uid']>0
            and all(v is False for k,v in row.items() if k!='uid'),'unsupported_layer_display')


def geometry(prepared, patch, native):
    """Complete fresh patch is checked by the raw predicate before this call."""
    raw=prepared['raw'];source=prepared['source'];objects=native['objects']
    require(1<=len(objects)<=64 and sum(len(o['world_vertices']) for o in objects)<=4096
            and sum(len(o['faces']) for o in objects)<=2048,'native_budget')
    require(patch['category']=='boundary_edges' and patch['element_kind']=='edge'
            and 3<=len(patch['source_indices'])<=64 and patch['position']['status']=='known','boundary_patch_required')
    target=next((o for o in objects if o['object_id']==source['object_id']),None)
    require(target is not None,'target_missing')
    scale=raw['unit_scale'];matrix=raw['matrix_world'];world=[]
    for p in raw['vertices']:
        world.append([(sum(matrix[k][j]*p[j] for j in range(3))+matrix[k][3])*scale for k in range(3)])
    require(world==target['world_vertices'],'raw_native_world_disagrees')
    edges=[raw['edges'][i] for i in patch['source_indices']];degree={}
    for a,b in edges:degree[a]=degree.get(a,0)+1;degree[b]=degree.get(b,0)+1
    require(all(x==2 for x in degree.values()),'simple_closed_boundary_required')
    points=[world[i] for i in sorted(degree)]
    low=[min(p[k] for p in points) for k in range(3)];high=[max(p[k] for p in points) for k in range(3)]
    widths=[high[k]-low[k] for k in (0,1)];span=1.6*max(widths)
    require(all(math.isfinite(x) and x>0 for x in widths) and math.isfinite(span),'boundary_projection_degenerate')
    center=[low[k]/2+high[k]/2 for k in range(3)]
    tolerance=max(span*1e-10,64*max(math.ulp(float(p[k])) for p in world for k in range(3)))
    require(tolerance<span*1e-5 and all(abs(p[2]-center[2])<=tolerance for p in world),'planar_XY_target_required')
    def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    for i,(a,b) in enumerate(edges):
        for c,d in edges[i+1:]:
            if {a,b}&{c,d}:continue
            p,q,r,s=[world[j] for j in (a,b,c,d)]
            if any(max(p[k],q[k])<min(r[k],s[k])-tolerance or max(r[k],s[k])<min(p[k],q[k])-tolerance for k in (0,1)):continue
            eps=tolerance*span
            o=[orient(p,q,r),orient(p,q,s),orient(r,s,p),orient(r,s,q)]
            require(not (min(o[:2])<=eps and max(o[:2])>=-eps and min(o[2:])<=eps and max(o[2:])>=-eps),
                    'crossing_or_ambiguous_boundary')
    return world,edges,center,widths,span,tolerance


def samples(world, edges, span):
    output=[];offset=3*span/384
    for a,b in edges:
        p,q=world[a],world[b];dx=q[0]-p[0];dy=q[1]-p[1];length=math.hypot(dx,dy)
        require(length>offset*2,'boundary_edge_subpixel_or_degenerate')
        normal=[-dy/length,dx/length,0.]
        for fraction in (.25,.5,.75):
            center=[math.fsum((p[k]*(1-fraction),q[k]*fraction)) for k in range(3)]
            output.append([[center[k]+sign*offset*normal[k] for k in range(3)] for sign in (-1,1)])
    return output


def nearest_xy(native, point, deadline):
    """Producer uses projected barycentric depth, not the consumer's 3D ray."""
    hits=[];work=0
    for obj in native['objects']:
        for face in obj['faces']:
            work+=1
            if work%64==0:checkpoint(deadline)
            a,b,c=[obj['world_vertices'][i] for i in face]
            if any(point[k]<min(a[k],b[k],c[k]) or point[k]>max(a[k],b[k],c[k]) for k in (0,1)):continue
            ux=b[0]-a[0];uy=b[1]-a[1];vx=c[0]-a[0];vy=c[1]-a[1]
            den=ux*vy-uy*vx
            require(abs(den)>1e-12*max(math.hypot(ux,uy)*math.hypot(vx,vy),1e-300),'ray_projection_uncertain')
            x=point[0]-a[0];y=point[1]-a[1];u=(x*vy-y*vx)/den;v=(ux*y-uy*x)/den
            if min(u,v,1-u-v)<-1e-12:continue
            z=math.fsum((a[2]*(1-u-v),b[2]*u,c[2]*v))-point[2]
            require(math.isfinite(z),'ray_nonfinite');hits.append((z,obj['object_id']))
    tolerance=1e-9*max([1.]+[abs(z) for z,_ in hits]);nearest=max((z for z,_ in hits),default=None)
    ids={identity for z,identity in hits if nearest-z<=tolerance}
    return (nearest,ids,tolerance),work


def pair_visible(hits, object_id):
    kinds=[]
    for nearest,ids,tolerance in hits:
        kinds.append('open' if nearest is None or nearest<-tolerance else
                     'surface' if abs(nearest)<=tolerance and ids=={object_id} else 'blocked')
    return sorted(kinds)==['open','surface']


def plan(prepared, patch, native, renderer, deadline):
    checkpoint(deadline)
    world,edges,center,widths,span,tolerance=geometry(prepared,patch,native)
    scale=prepared['raw']['unit_scale'];overview=renderer._native_view_frame(native,'XY',scale)
    overview_span=overview['ortho_scale_bu']*scale;min_width=min(widths)
    reason='overview_projection_no_detail_gain';visible=[];work=0;sample_pairs=[]
    if min_width*384/overview_span<16:
        reason='insufficient_projection_gain'
        if min_width*384/span>=16 and overview_span/span>=2:
            sample_pairs=samples(world,edges,span)
            count=sum(len(o['faces']) for o in native['objects'])
            require(len(sample_pairs)*2*count*2<=8192,'combined_ray_budget_exhausted')
            for pair in sample_pairs:
                hits=[]
                for point in pair:
                    hit,n=nearest_xy(native,point,deadline);hits.append(hit);work+=n
                visible.append(pair_visible(hits,prepared['source']['object_id']))
            reason='visible_boundary_gain' if sum(visible)>=max(8,math.ceil(len(visible)*2/3)) else 'boundary_not_visible_enough'
    detail=None
    if reason=='visible_boundary_gain':
        depths=[(p[2]-center[2])/scale for o in native['objects'] for p in o['world_vertices']]
        margin=max(span/scale,max(depths)-min(depths))*.125;distance=max(depths)+margin
        detail={**overview,'center_bu':[v/scale for v in center],
            'camera_location_bu':[center[0]/scale,center[1]/scale,center[2]/scale+distance],
            'ortho_scale_bu':span/scale,'clip_start_bu':margin*.25,'clip_end_bu':distance-min(depths)+margin}
    checkpoint(deadline)
    result=dict(schema='planar-patch-plan-v1',view='XY',reason=reason,detail_included=detail is not None,
        candidate_count=1,overview=renderer._public_view_frame(overview,scale,'all_native_vertices'),
        detail=None if detail is None else renderer._public_view_frame(detail,scale,'intentional_local_window'),
        projection=dict(boundary_min_extent_m=min_width,overview_px=min_width*384/overview_span,
            detail_px=min_width*384/span,detail_span_m=span,not_aperture_measurement=True),
        visibility=dict(method='paired_boundary_offsets_XY',samples=sample_pairs,visible=visible,
            producer_triangle_tests=work,consumer_reserved_triangle_tests=work,total_limit=8192,
            scope='finite_geometric_opportunity_not_complete_visibility'),execution_authority=False)
    return result,overview,detail


def observe(host, object_id, patch, request_id, deadline_ns):
    """One synchronous lease; restoration uncertainty quarantines read rendering."""
    host._readonly_request_id(request_id);checkpoint(deadline_ns)
    require(deadline_ns<=time.perf_counter_ns()+30_000_000_000,'original_deadline_required')
    require(type(patch) is dict and len(json.dumps(patch,allow_nan=False))<=16384,'patch_input_budget')
    renderer=host._readonly_native_module();m=host._raw_mesh_module()
    store=host._readonly_observation_store(create=True);now=time.perf_counter_ns()
    require(not store['quarantined'] and store['active_request_id'] is None,'read_channel_unavailable')
    store['seen']={k:v for k,v in store['seen'].items() if v>now}
    require(request_id not in store['seen'] and len(store['seen'])<128,'request_reused_or_capacity')
    store['seen'][request_id]=deadline_ns;store['active_request_id']=request_id
    store['sequence']+=1;audits=[];evidence=None;profile=None;started=now
    try:
        profile=display_profile(host,renderer)
        budget=m.WorkBudget(deadline_ns=deadline_ns)
        prepared=m.capture_raw(host,object_id,budget=budget)
        diagnosis=m.analyze_prepared(prepared,task_id=request_id,categories=['boundary_edges'],budget=budget)
        require(digest(patch) in {digest(p) for p in diagnosis['patches']},'stale_or_incomplete_patch')
        evidence=host.capture_readonly_evidence();checkpoint(deadline_ns)
        planned,overview,detail=plan(prepared,patch,evidence['native_scene'],renderer,deadline_ns)
        planning_finished=time.perf_counter_ns();frames=[];total_bytes=0
        for kind,frame in [('overview',overview)]+([('detail',detail)] if detail else []):
            checkpoint(deadline_ns);require(display_profile(host,renderer)==profile,'display_changed_before_render')
            proof=[];frame_audits=[];t=time.perf_counter_ns()
            try:
                picture=host._readonly_render_view(renderer,store,'XY',frame=frame,
                    coverage='all_native_vertices' if kind=='overview' else 'intentional_local_window',
                    expected_evidence=evidence,audit_sink=frame_audits,frustum_sink=proof)
            finally:audits.extend(frame_audits)
            require(display_profile(host,renderer)==profile,'display_changed_after_render')
            require(len(proof)==1 and len(frame_audits)==1,'render_proof_missing')
            raw=base64.b64decode(picture['image_base64'],validate=True);total_bytes+=len(raw)
            require(total_bytes<=LIMITS['png_bytes'],'png_total_budget')
            frames.append(dict(kind=kind,picture=picture,png_sha256=hashlib.sha256(raw).hexdigest(),
                frustum=proof[0],audit=frame_audits[0],elapsed_ns=time.perf_counter_ns()-t))
        after=host.capture_readonly_evidence();after_profile=display_profile(host,renderer)
        final_raw=m.capture_raw(host,object_id,budget=budget)
        require(after==evidence and after_profile==profile and final_raw['source']['raw_sha256']==prepared['source']['raw_sha256'],
                'source_changed_after_observation')
        checkpoint(deadline_ns)
        identity={k:prepared['source'][k] for k in ('object_id','object_instance','document_epoch','capture_id')}
        return dict(protocol=PROTOCOL,request_id=request_id,object_id=object_id,patch=patch,
            raw=prepared['raw'],identity=identity,evidence=evidence,display=profile,
            source_binding=digest(dict(raw_sha256=prepared['source']['raw_sha256'],
                native=evidence['native_scene'],capture=evidence['capture'],display=profile)),
            plan=planned,frames=frames,started_ns=started,planning_finished_ns=planning_finished,
            finished_ns=time.perf_counter_ns(),deadline_ns=deadline_ns,restored=True,
            read_only=True,execution_authority=False)
    except BaseException:
        if audits:
            try:restored=(all(a['restored'] for a in audits) and host.capture_readonly_evidence()==evidence
                          and display_profile(host,renderer)==profile)
            except BaseException:restored=False
            if not restored:
                store['quarantined']=True;store['quarantine_reason']='patch_restoration_unconfirmed'
        raise
    finally:store['active_request_id']=None
