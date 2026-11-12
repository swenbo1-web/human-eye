"""Strict independent production consumer for the new finite boundary channel.

No producer geometry/planner imports. XY transport and default behavior stay separate.
"""
import base64,copy,hashlib,json,math,struct,time
from . import mesh_structure as m,native_observation as n,patch_focus as f
from .nonplanar_replay import decision,require

PROTOCOL='readonly-nonplanar-boundary-v1'
MODES=('nonplanar_boundary_v1','nonplanar_dense_v1')


def validate_capabilities(caps):
    from .blender_host import _NONPLANAR_FOCUS_SHA256
    require(type(caps) is dict and set(caps)=={'protocol','helper_sha256','native','read_only','execution_authority','modes'}
        and caps['protocol']==PROTOCOL and caps['helper_sha256']==_NONPLANAR_FOCUS_SHA256
        and caps['modes']==list(MODES) and caps['read_only'] is True and caps['execution_authority'] is False,'capability_mismatch')
    n.validate_native_capabilities(caps['native'])
    return caps


def bounded_wire(value):
    pending=[(value,0)];seen=0
    while pending:
        item,depth=pending.pop();seen+=1
        require(seen<=300000 and depth<=32,'wire_complexity')
        if type(item) is dict:
            require(len(item)<=128 and all(type(k) is str and len(k)<=256 for k in item),'wire_fields')
            pending.extend((v,depth+1) for v in item.values())
        elif type(item) is list:
            require(len(item)<=16384,'wire_list_budget');pending.extend((v,depth+1) for v in item)
        elif type(item) is str:require(len(item)<=12*1024*1024,'wire_string_budget')
        elif type(item) in (int,float):require(math.isfinite(item) and (type(item) is float or item.bit_length()<=128),'wire_number')
        else:require(item is None or type(item) is bool,'wire_scalar')
    require(len(json.dumps(value,allow_nan=False,separators=(',',':')).encode('utf8'))<=36*1024*1024,'wire_total_bytes')
    require(len(json.dumps(value.get('plan'),allow_nan=False,separators=(',',':')).encode('utf8'))<=2*1024*1024,'plan_bytes')


def source_geometry(prepared,patch,native):
    require(patch['category']=='boundary_edges' and patch['element_kind']=='edge'
        and patch['position']['status']=='known' and 3<=len(patch['source_indices'])<=64,'boundary_patch_required')
    raw=prepared['raw'];target=next(o for o in native['objects'] if o['object_id']==prepared['source']['object_id'])
    local_metres=[[x*raw['unit_scale'] for x in point] for point in raw['vertices']]
    require(local_metres==target['local_vertices'] and raw['polygons']==target['faces']
        and all(len(face)==3 for face in raw['polygons']),'raw_native_triangle_correspondence')
    matrix=raw['matrix_world'];world=[]
    matrix_metres=[row[:] for row in matrix]
    for k in range(3):matrix_metres[k][3]*=raw['unit_scale']
    require(matrix_metres==target['matrix'],'raw_native_matrix_correspondence')
    for p in raw['vertices']:
        world.append([(sum(matrix[k][j]*p[j] for j in range(3))+matrix[k][3])*raw['unit_scale'] for k in range(3)])
    require(world==target['world_vertices'],'raw_native_world_correspondence')
    return [raw['edges'][index] for index in patch['source_indices']]


def public_frame(frame,coverage):
    return dict(center_world_m=frame['center_bu'],right_world=frame['right'],up_world=frame['up'],
        eye_direction_world=frame['direction'],span_m=frame['ortho_scale_bu'],
        screen_coverage=coverage,depth_coverage='all_native_vertices')


def validate_result(value, *, object_id, patch, request_id, deadline_ns, capabilities, mode):
    validate_capabilities(capabilities); bounded_wire(value);f.checkpoint(deadline_ns);need=f.require
    fields={'mode','protocol','request_id','object_id','patch','raw','identity','evidence','display','source_binding',
        'plan','frames','started_ns','planning_finished_ns','finished_ns','deadline_ns','restored','read_only','execution_authority'}
    need(type(value) is dict and set(value)==fields and value['protocol']==PROTOCOL and value['mode']==mode
        and value['request_id']==request_id and value['object_id']==object_id
        and f.digest(value['patch'])==f.digest(patch) and value['restored'] is True
        and value['read_only'] is True and value['execution_authority'] is False,'response_binding')
    need(all(type(value[k]) is int for k in ('started_ns','planning_finished_ns','finished_ns','deadline_ns'))
        and value['deadline_ns']==deadline_ns and 0<value['started_ns']<=value['planning_finished_ns']
        <=value['finished_ns']<=time.perf_counter_ns() and value['finished_ns']<deadline_ns<=value['started_ns']+30_000_000_000,'response_deadline')
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
    edges=source_geometry(prepared,patch,native)
    replay_work,overview,detail=decision(value['plan'],native,object_id,edges,mode,deadline_ns)
    views={'overview':public_frame(overview,'all_native_vertices'), 'detail':None if detail is None else public_frame(detail,'intentional_local_window')}
    kinds=['overview','detail'] if (detail is not None) else ['overview'];frames=value['frames']
    need(type(frames) is list and len(frames)==len(kinds),'frame_count')
    images=[];sequence=0;total=0
    for row,kind in zip(frames,kinds):
        f.checkpoint(deadline_ns)
        need(type(row) is dict and set(row)=={'kind','picture','png_sha256','frustum','audit','elapsed_ns'}
            and row['kind']==kind and type(row['elapsed_ns']) is int and row['elapsed_ns']>=0,'frame_record')
        n._validated_render_audit(row['audit'],'SCENE',[o['name'] for o in native['objects']],sequence,minimum_objects=1)
        sequence=row['audit']['sequence']
        n._validate_multiscale_frustum(row['frustum'],views[kind],native,'SCENE',kind)
        picture=row['picture']
        need(type(picture) is dict and set(picture)=={'mime_type','image_base64','width','height','view','source'}
            and picture['mime_type']=='image/png' and picture['view']=='SCENE' and picture['width']==picture['height']==384
            and picture['source']=='blender_workbench_native_render' and type(picture['image_base64']) is str
            and len(picture['image_base64'])<=12*1024*1024,'image_fields')
        raw=base64.b64decode(picture['image_base64'],validate=True);total+=len(raw)
        need(total<=16*1024*1024 and len(raw)>=24 and struct.unpack('>II',raw[16:24])==(384,384)
            and hashlib.sha256(raw).hexdigest()==row['png_sha256'],'image_hash_or_budget')
        clean=n._public_native_png(raw)
        images.append(dict(type='image',mimeType='image/png',data=base64.b64encode(clean).decode('ascii')))
    need(sum(row['elapsed_ns'] for row in frames)<=value['finished_ns']-value['planning_finished_ns'],
        'render_elapsed_time_disagrees')
    f.checkpoint(deadline_ns)
    chosen=value['plan']['selected']
    return dict(status='observed',protocol=PROTOCOL,mode=mode,images=images,
        reason='visible_boundary_gain' if chosen else 'no_useful_local_view',detail_included=chosen is not None,
        projection=copy.deepcopy((chosen or value['plan']['candidates'][0])['projection']),
        visible_edge_pairs=0 if chosen is None else chosen['visible_count'],
        tested_edge_pairs=0 if chosen is None else len(chosen['samples']),combined_triangle_tests=replay_work,
        source_binding=value['source_binding'],execution_authority=False,executed=False,allow_action=False,
        scope='finite_nonplanar_boundary_opportunity_not_damage_or_semantic_understanding')
