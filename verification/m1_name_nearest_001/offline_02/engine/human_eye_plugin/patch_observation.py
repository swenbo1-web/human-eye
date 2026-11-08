"""Private patch consumer and service integration; no public MCP/Hook route.

Admission shares the raw structural predicate. Visibility is replayed with an
independent 3D line/triangle algorithm; it never calls the producer's planner.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import math
import struct
import time
import uuid
from . import mesh_structure as m, native_observation as n, patch_focus as f


def validate_capabilities(caps):
    from .blender_host import _PATCH_FOCUS_SHA256
    f.require(type(caps) is dict and set(caps)=={'protocol','helper_sha256','native','read_only','execution_authority'}
        and caps['protocol']==f.PROTOCOL and caps['helper_sha256']==_PATCH_FOCUS_SHA256
        and caps['read_only'] is True and caps['execution_authority'] is False,'capability_mismatch')
    n.validate_native_capabilities(caps['native'])
    return caps


def validate_plan(plan, prepared, patch, native, deadline):
    need=f.require
    need(type(plan) is dict and set(plan)=={'schema','view','reason','detail_included','candidate_count','overview',
        'detail','projection','visibility','execution_authority'} and plan['schema']=='planar-patch-plan-v1'
        and plan['view']=='XY' and type(plan['candidate_count']) is int and plan['candidate_count']==1
        and type(plan['detail_included']) is bool and plan['execution_authority'] is False,'plan_fields')
    world,edges,center,widths,span,_=f.geometry(prepared,patch,native)
    points=[p for obj in native['objects'] for p in obj['world_vertices']]
    overview_center=[min(p[k] for p in points)/2+max(p[k] for p in points)/2 for k in range(3)]
    overview_span=2*1.25*max(abs(p[k]-overview_center[k]) for p in points for k in (0,1))
    width=min(widths);projection=dict(boundary_min_extent_m=width,overview_px=width*384/overview_span,
        detail_px=width*384/span,detail_span_m=span,not_aperture_measurement=True)
    need(type(plan['projection']) is dict and f.digest(plan['projection'])==f.digest(projection),'projection_disagrees')
    def check_frame(frame, center, span, coverage):
        expected=dict(center_world_m=center,right_world=[-1.,0.,0.],up_world=[0.,-1.,0.],
            eye_direction_world=[0.,0.,1.],span_m=span,screen_coverage=coverage,depth_coverage='all_native_vertices')
        need(type(frame) is dict and set(frame)==set(expected),'frame_fields')
        for key,value in expected.items():
            if type(value) is list:need(n._vector(frame[key],3) and all(n._near(x,y) for x,y in zip(frame[key],value)),'frame_geometry')
            elif type(value) is float:need(n._near(frame[key],value),'frame_span')
            else:need(frame[key]==value,'frame_coverage')
    check_frame(plan['overview'],overview_center,overview_span,'all_native_vertices')
    visibility=plan['visibility']
    need(type(visibility) is dict and set(visibility)=={'method','samples','visible','producer_triangle_tests',
        'consumer_reserved_triangle_tests','total_limit','scope'} and visibility['method']=='paired_boundary_offsets_XY'
        and visibility['scope']=='finite_geometric_opportunity_not_complete_visibility'
        and type(visibility['total_limit']) is int and visibility['total_limit']==8192,'visibility_fields')
    pairs=[];reason='overview_projection_no_detail_gain';visible=[];work=0
    if projection['overview_px']<16:
        reason='insufficient_projection_gain'
        if projection['detail_px']>=16 and overview_span/span>=2:
            # Reconstruct sample coordinates, without using producer samples().
            for ia,ib in edges:
                a,b=world[ia],world[ib];length=math.hypot(b[0]-a[0],b[1]-a[1]);offset=span/128
                need(length>2*offset,'consumer_short_edge')
                perpendicular=[(a[1]-b[1])/length,(b[0]-a[0])/length,0.]
                for numerator in (1,2,3):
                    q=[math.fsum((a[k]*(4-numerator)/4,b[k]*numerator/4)) for k in range(3)]
                    pairs.append([[q[k]+sign*offset*perpendicular[k] for k in range(3)] for sign in (-1,1)])
            triangles=sum(len(o['faces']) for o in native['objects']);work=len(pairs)*2*triangles
            need(work*2<=8192,'consumer_combined_ray_budget')
            for pair in pairs:
                f.checkpoint(deadline);kinds=[]
                for point in pair:
                    depth,ids,eps=n._dense_focus_ray_readback(native,point,[-1.,0.,0.],[0.,-1.,0.],[0.,0.,1.])
                    kinds.append('open' if depth is None or depth<-eps else
                        'surface' if abs(depth)<=eps and ids=={prepared['source']['object_id']} else 'blocked')
                visible.append(kinds.count('surface')==1 and kinds.count('open')==1)
            reason='visible_boundary_gain' if sum(visible)>=max(8,math.ceil(len(visible)*2/3)) else 'boundary_not_visible_enough'
    need(type(visibility['samples']) is list and len(visibility['samples'])==len(pairs),'sample_count')
    for actual,pair in zip(visibility['samples'],pairs):
        need(type(actual) is list and len(actual)==2 and all(n._vector(p,3) for p in actual),'sample_fields')
        need(all(n._near(x,y) or abs(x-y)<=span*1e-14 for a,b in zip(actual,pair) for x,y in zip(a,b)),'sample_coordinates')
    need(type(visibility['visible']) is list and all(type(v) is bool for v in visibility['visible'])
        and visibility['visible']==visible,'visibility_replay_disagrees')
    need(all(type(visibility[k]) is int and visibility[k]==work for k in
        ('producer_triangle_tests','consumer_reserved_triangle_tests')),'work_accounting_disagrees')
    included=reason=='visible_boundary_gain'
    need(plan['reason']==reason and plan['detail_included'] is included,'gain_decision_disagrees')
    if included:check_frame(plan['detail'],center,span,'intentional_local_window')
    else:need(plan['detail'] is None,'unexpected_detail')
    f.checkpoint(deadline)
    return work


def validate_result(value, *, object_id, patch, request_id, deadline_ns, capabilities):
    validate_capabilities(capabilities);f.checkpoint(deadline_ns);need=f.require
    fields={'protocol','request_id','object_id','patch','raw','identity','evidence','display','source_binding',
        'plan','frames','started_ns','planning_finished_ns','finished_ns','deadline_ns','restored','read_only','execution_authority'}
    need(type(value) is dict and set(value)==fields and value['protocol']==f.PROTOCOL
        and value['request_id']==request_id and value['object_id']==object_id
        and f.digest(value['patch'])==f.digest(patch) and value['restored'] is True
        and value['read_only'] is True and value['execution_authority'] is False,'response_binding')
    need(all(type(value[k]) is int for k in ('started_ns','planning_finished_ns','finished_ns','deadline_ns'))
        and value['deadline_ns']==deadline_ns and 0<value['started_ns']<=value['planning_finished_ns']
        <=value['finished_ns']<deadline_ns<=value['started_ns']+30_000_000_000,'response_deadline')
    budget=m.WorkBudget(deadline_ns=deadline_ns)
    prepared=m.prepare_raw(value['raw'],value['identity'],budget=budget)
    report=m.analyze_prepared(prepared,task_id=request_id,categories=['boundary_edges'],budget=budget)
    need(prepared['source']['object_id']==object_id and f.digest(patch) in {f.digest(p) for p in report['patches']},
         'consumer_patch_source_binding')
    evidence=value['evidence']
    # Enforce the new channel's small geometry domain before the legacy common
    # validator copies arrays or hashes a native packet with larger limits.
    need(type(evidence) is dict and type(evidence.get('native_scene')) is dict,'evidence_fields')
    objects=evidence['native_scene'].get('objects')
    need(type(objects) is list and 1<=len(objects)<=64,'consumer_object_budget')
    vertices=triangles=0
    for obj in objects:
        need(type(obj) is dict and set(obj)==set(n._OBJECT_KEYS)
            and type(obj['world_vertices']) is list and type(obj['local_vertices']) is list
            and len(obj['world_vertices'])==len(obj['local_vertices'])
            and type(obj['faces']) is list,'consumer_geometry_fields')
        vertices+=len(obj['world_vertices']);triangles+=len(obj['faces'])
        need(vertices<=4096 and triangles<=2048,'consumer_geometry_budget')
        need(all(type(face) is list and len(face)==3 for face in obj['faces']),'consumer_triangles_required')
    native=n._readonly_evidence(evidence,evidence['capture'],minimum_objects=1)
    f.validate_profile(value['display'],{o['object_id'] for o in native['objects']})
    host_identity=evidence['capture'].get('host_identity')
    need(type(host_identity) is dict and host_identity.get('schema_version')=='1.0'
        and host_identity.get('capture_scope')=='complete_scene_meshes'
        and host_identity.get('document_epoch')==prepared['source']['document_epoch']
        and type(host_identity.get('object_instances')) is dict
        and host_identity['object_instances']=={r['object_id']:str(r['object_uid']) for r in value['display']['objects']},
        'display_incarnation_binding')
    target_display=next(r for r in value['display']['objects'] if r['object_id']==object_id)
    need(prepared['source']['object_instance']==str(target_display['object_uid'])+':'+str(target_display['mesh_uid']),
        'raw_render_incarnation_binding')
    need(value['source_binding']==f.digest(dict(raw_sha256=prepared['source']['raw_sha256'],
        native=evidence['native_scene'],capture=evidence['capture'],display=value['display'])),'complete_source_binding')
    replay_work=validate_plan(value['plan'],prepared,patch,native,deadline_ns)
    kinds=['overview','detail'] if value['plan']['detail_included'] else ['overview'];frames=value['frames']
    need(type(frames) is list and len(frames)==len(kinds),'frame_count')
    images=[];sequence=0;total=0
    for row,kind in zip(frames,kinds):
        f.checkpoint(deadline_ns)
        need(type(row) is dict and set(row)=={'kind','picture','png_sha256','frustum','audit','elapsed_ns'}
            and row['kind']==kind and type(row['elapsed_ns']) is int and row['elapsed_ns']>=0,'frame_record')
        n._validated_render_audit(row['audit'],'XY',[o['name'] for o in native['objects']],sequence,minimum_objects=1)
        sequence=row['audit']['sequence']
        n._validate_multiscale_frustum(row['frustum'],value['plan'][kind],native,'XY',kind)
        picture=row['picture']
        need(type(picture) is dict and set(picture)=={'mime_type','image_base64','width','height','view','source'}
            and picture['mime_type']=='image/png' and picture['view']=='XY' and picture['width']==picture['height']==384
            and picture['source']=='blender_workbench_native_render' and type(picture['image_base64']) is str
            and len(picture['image_base64'])<=12*1024*1024,'image_fields')
        raw=base64.b64decode(picture['image_base64'],validate=True);total+=len(raw)
        need(total<=16*1024*1024 and len(raw)>=24 and struct.unpack('>II',raw[16:24])==(384,384)
            and hashlib.sha256(raw).hexdigest()==row['png_sha256'],'image_hash_or_budget')
        clean=n._public_native_png(raw)
        images.append(dict(type='image',mimeType='image/png',data=base64.b64encode(clean).decode('ascii')))
    f.checkpoint(deadline_ns)
    return dict(status='observed',protocol=f.PROTOCOL,images=images,reason=value['plan']['reason'],
        detail_included=value['plan']['detail_included'],projection=copy.deepcopy(value['plan']['projection']),
        visible_edge_pairs=sum(value['plan']['visibility']['visible']),
        tested_edge_pairs=len(value['plan']['visibility']['visible']),combined_triangle_tests=replay_work*2,
        source_binding=value['source_binding'],execution_authority=False,executed=False,allow_action=False,
        scope='finite_planar_boundary_opportunity_not_damage_or_semantic_understanding')


def observe(service, session_id, object_id, patch):
    m._require(m._identifier(session_id) and m._identifier(object_id),'patch_request_identity')
    if not service.config.get('enabled',True):return {'status':'disabled','execution_authority':False}
    rejected=service._identity_rejection()
    if rejected is not None:return rejected
    with service._locked() as (state,runtime),service._observation_scope():
        if state.get('inflight') or runtime.status['quarantined']:
            return dict(status='host_quarantined',execution_authority=False)
        host=service.host
        if not all(callable(getattr(host,k,None)) for k in ('patch_observation_capabilities','observe_patch')):
            return dict(status='unsupported',reason='patch_typed_host_unavailable',execution_authority=False)
        service._check_request_budget('before_patch_capabilities')
        caps=validate_capabilities(host.patch_observation_capabilities())
        service._check_request_budget('after_patch_capabilities')
        remaining=service._remaining_request_budget();duration=30. if remaining is None else min(30.,remaining)
        deadline=time.perf_counter_ns()+int(duration*1e9);request=uuid.uuid4().hex
        result=host.observe_patch(request,object_id,copy.deepcopy(patch),deadline)
        service._check_request_budget('after_patch_observation')
        return validate_result(result,object_id=object_id,patch=patch,request_id=request,
                               deadline_ns=deadline,capabilities=caps)
