"""Verify actual private wires and identical captured geometry in both arms."""

from hashlib import sha256
import json
import math
from pathlib import Path
from runpy import run_path


HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parent/'m2_source_region_cold_selective_transport_recovery_001'
OLD=run_path(str(PREVIOUS/'verify.py'))
HOST=run_path(str(HERE/'host.py'))
COMMON=run_path(str(HERE/'common.py'))
RUN,REPLAY,LABELS,ASSETS,BINDINGS,PRIVATE_TOOL=(
    HOST[key] for key in ('RUN','REPLAY','LABELS','ASSETS','BINDINGS','PRIVATE_TOOL'))
require,pin,read,lines,indexed,normalize_result=(
    OLD[key] for key in ('require','pin','read','lines','indexed','normalize_result'))
order,arguments,query_from_record=(COMMON[key] for key in ('order','arguments','query_from_record'))
closed_source,wire_records=(OLD[key] for key in ('closed_source','wire_records'))
for original in (closed_source,wire_records,OLD['new_decoder']):
    original.__globals__.update(HERE=HERE,RUN=RUN,REPLAY=REPLAY,LABELS=LABELS,ASSETS=ASSETS,BINDINGS=BINDINGS)

RESIDENT='human-eye-private-source-region-residency-v1'
SOURCE='human-eye-selective-source-region-capture-v1'
SCOPE='selected_source_region_and_reference'
COMMAND='capture_source_region_pair'
OLD_RUN=Path('D:/he_m2_source_region_cold_selective_transport_recovery_001')
BASELINE=OLD['CONTROL']
_KNOWN_FIELDS={'document_epoch','instance_id','epoch','revision','selection_sha256','payload_sha256'}


def stable(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def digest(value):
    return sha256(stable(value).encode('utf8')).hexdigest()


def hex_value(value,n):
    return type(value) is str and len(value)==n and all(char in '0123456789abcdef' for char in value)


def check_lease(lease,core):
    require(type(lease) is dict and set(lease)==_KNOWN_FIELDS
            and lease['document_epoch']==core['binding']['document_epoch']
            and lease['payload_sha256']==core['payload_sha256']
            and hex_value(lease['selection_sha256'],64) and hex_value(lease['instance_id'],32)
            and type(lease['epoch']) is int and lease['epoch']>=1
            and type(lease['revision']) is int and lease['revision']>=1,
            'private_actual_confirmation_lease_wrong')


def materialization(wire,preceding,arm):
    body=wire['packet']
    if arm=='A':
        require(body['schema']==SOURCE and 'known' not in wire['params'],'legacy_private_wire_changed')
        return body,body['work'],None
    require(type(body) is dict and set(body)=={'schema','host_source_sha256','lease','capture','work','stages'}
            and body['schema']==RESIDENT,'private_resident_envelope_shape_invalid')
    work,lease=body['work'],body['lease']
    if body['capture'] is None:
        require(preceding is not None and lease==wire['params'].get('known')==preceding[0]
                and work['mode']=='lease_hit','acknowledgement_without_actual_prior_held_package')
        core=preceding[1]
    else:
        core=body['capture']
        require(work==core['work'] and body['stages']==core['stages']
                and work['mode'] in ('resident_capture','uncached_capture'),
                'actual_resident_full_body_work_not_bound')
    if lease is not None:
        check_lease(lease,core)
    else:
        require(work['mode']=='uncached_capture','private_bound_read_missing_lease')
    require(body['host_source_sha256']==core['binding']['host_source_sha256'],'resident_envelope_host_source_changed')
    return core,work,lease


def verify_core(core,work,archive,wire,terminal,query,arm):
    bind=core['binding']
    require(core['schema']==SOURCE and bind['capture_scope']==SCOPE and 'ordered_geometry_sha256' not in bind
            and 'region_ref' not in archive and 'capture_state' not in bind
            and bind=={key:archive['binding'][key] for key in bind}
            and archive['payload_sha256']==core['payload_sha256']==digest(
                {key:core[key] for key in ('schema','binding','region','reference')})
            and archive['schema']=='human-eye-selective-source-region-measurement-v1'
            and archive['status']=='complete' and archive['read_only'] is True
            and archive['execution_authority'] is False and archive['frames']==[],
            'private_current_capture_and_actual_producer_mismatch')
    params=wire['params']
    expected={'target':query['region']['object'],'reference':query['reference'],
              'world_box_m':{key:[float(coordinate) for coordinate in values]
                             for key,values in query['region']['world_box_m'].items()}}
    require(set(params) in ({*expected,'deadline_ns','max_response_bytes'},
                            {*expected,'deadline_ns','max_response_bytes','known'})
            and stable({key:params[key] for key in expected})==stable(expected)
            and stable(bind['world_box_m'])==stable(expected['world_box_m'])
            and type(params['deadline_ns']) is int and type(params['max_response_bytes']) is int
            and 0<wire['rx']['bytes']<=params['max_response_bytes']
            and wire['event']['m2_work']['native_work']['envelope_encoding']['closed_ns']<=params['deadline_ns'],
            'private_wire_box_or_budget_not_actually_requested')
    meshes=indexed(terminal['objects'],'name','terminal_current_objects')
    host_manifest={row['path']:row['sha256'] for row in read(BINDINGS[arm])['source_manifest']}
    require(bind['host_source_sha256']==host_manifest['human_eye_plugin/blender_host.py']
            and bind['source_frame']['frame']==terminal['source']['frame']
            and bind['source_frame']['subframe']==terminal['source']['subframe']
            and bind['source_frame']['view_layer']==terminal['source']['view_layer_id']
            and bind['source_frame']['scale_length']==terminal['source']['scale_length'],
            'private_actual_blender_host_or_frame_mismatch')
    for key in ('target','reference'):
        obj=meshes[expected[key]['name']]
        require(bind[key]=={name:obj[name] for name in ('name','object_id','instance_id')}
                and bind[key+'_selector']==expected[key] and bind['world_matrices'][key]==obj['matrix_world'],
                'private_current_instance_pose_not_actual/'+key)
    sent={key:work['transmitted_'+key] for key in ('objects','vertices','triangles')}
    expected_work=archive['work']['host_capture']
    require(all(type(value) is int and value>=0 for value in sent.values())
            and all(expected_work[key]==value for key,value in work.items()),
            'actual_transport_work_not_bound_to_producer')
    if arm=='A' or work['mode']!='lease_hit':
        require(sent=={'objects':2,'vertices':len(core['region']['vertices'])+len(core['reference']['vertices']),
                         'triangles':len(core['region']['faces'])+len(core['reference']['faces'])},
                'full_private_packet_geometry_count_changed')
    else:
        require(not any(sent.values()) and not any(work[key] for key in (
            'to_mesh','triangulations','world_transforms','world_vertices_transformed','box_vertices_scanned',
            'box_triangles_scanned','expanded_objects','expanded_vertices','expanded_triangles')),
            'private_acknowledgement_repeated_geometry_or_filter')
    return sent


def verify_slot(slot,label,expected_records,*,offline=False):
    slot=Path(slot).resolve(strict=True)
    result=read(slot/'SLOT_RESULT.json')
    closed,terminal,independent,pins=closed_source(slot,label,result,read(slot/'SLOT_PUBLICATION.json'),offline=offline)
    arm=LABELS[label][1]
    binding=read(BINDINGS[arm])
    meter=read(slot/'mcp_io/REAL_HOST_STAGES.json')
    stdio=OLD['STDIO']
    streams=indexed([row for row in lines(slot/'mcp_io/MCP_IO.jsonl') if row['method']=='tools/call'],
                    'id','held_tools')
    native=wire_records(slot,offline=offline)
    require(len(native)==len(meter['requests'])==len(streams)==len(result['observations'])==3
            and meter['source_sha256']==binding['source_sha256'] and meter['gc_before']==meter['gc_after']
            and meter['open_pause'] is None,'actual_transport_three_slot_denominator')
    checked,preceding=[],None
    for index,(wire,client,observation,record) in enumerate(
            zip(native,meter['requests'],result['observations'],order(expected_records),strict=True),1):
        parsed=stdio['_raw_stdio'](slot,streams[observation['response_id']])
        query=query_from_record(record)
        require(parsed['tool']==PRIVATE_TOOL and stable(parsed['arguments'])==stable(arguments(record,arm))
                and parsed['rasters']==0 and parsed['is_error'] is False
                and client['outcome']=='success' and client['command']==wire['command']==COMMAND
                and client['host_request_id']==wire['host_id'] and client['request_bytes']==wire['tx']['bytes']
                and client['response_bytes']==wire['rx']['bytes'] and client['resident_before'] is (index>1)
                and client['resident_after'] is True and (wire['bootstrap_base64_bytes']>0) is (index==1)
                and 'decoder' not in client,'actual_scoped_blender_and_stdio_identity_changed')
        producer=slot/'mcp_io'/f'PRIVATE_RESULT_{index}.json'
        archive=OLD['_published_value'](parsed,producer,'B')
        core,work,lease=materialization(wire,preceding,arm)
        sent=verify_core(core,work,archive,wire,terminal,query,arm)
        span=client['stages']['tcp_exchange_including_outer_json']
        meter_native=wire['event']['m2_work']['native_work']
        require(OLD['_within'](meter_native['envelope_encoding'],span)
                and all(OLD['_within'](item,span) for item in meter_native['intervals']),
                'actual_private_host_spans_not_within_tcp')
        if arm=='B' and work['mode']!='uncached_capture':
            before,after=(meter_native['residency_'+when] for when in ('before','after'))
            require(all(after[name]-before[name]==work[name] for name in (
                'to_mesh','triangulations','world_transforms','world_vertices_transformed')),
                'actual_resident_host_counters_differ_from_packet')
        if arm=='A':
            # The pinned uncached branch contains exactly one to_mesh and
            # one triangulation per expanded object. It has no native
            # residency counter for these two operations.
            work={**work,'mode':'legacy_uncached','to_mesh':work['expanded_objects'],
                'triangulations':work['expanded_objects'],'world_vertices_transformed':work['expanded_vertices'],
                'box_triangles_scanned':core['region']['source_triangle_count'],
                'box_vertices_scanned':core['region']['source_vertex_count']}
        if not offline:
            for key in ('Blender','engine'):
                before,after=(observation['process_'+when][key] for when in ('before','after'))
                require(before['pid']==after['pid'] and before['sampled_ns']<=after['sampled_ns']
                        and all(before[field]<=after[field] for field in ('kernel_cpu_ns','user_cpu_ns')),
                        'invalid_actual_process_resource_window')
        transport={key:value for key,value in wire.items() if key not in ('params','packet','event')}
        checked.append({'index':index,'query':query,'measurement':normalize_result(archive),'producer':pin(producer),
              'stdio':parsed,'host':client,'host_native':meter_native,'transport':transport,
              'expanded':work,'transmitted':sent,'host_wire_total_bytes':wire['tx']['bytes']+wire['rx']['bytes'],
              'local_stages':archive['stages'],'wall_ns':observation['wall_ns'],
              'process_samples':{k:v for k,v in observation.items() if k.startswith('process_')},
              'connector_work':{k:v for k,v in archive['work']['host_capture'].items() if k not in work},
              'lease':lease,'known_lease_sent':wire['params'].get('known'),
              'scoped_packet':core})
        preceding=(lease,core) if lease is not None else None
        pins.extend((wire['tx'],wire['rx'],parsed['tx'],parsed['rx'],pin(producer)))
    return {'label':label,'window_ns':result['window_ns'],'calls':checked,'terminal':terminal,
            'before_after':independent,'close':pin(slot/'HOST_RECEIPT.json'),'budget':closed['budget']['slots'][label],
            'offline_fixture':offline,'source_pins':pins}


def original_full(asset):
    label={'assembly':'AA','yanyite':'YA'}[asset]
    slot=OLD_RUN/'slots'/label
    rows=wire_records(slot)
    require(len(rows)==3 and rows[0]['command']=='capture','prior_actual_complete_scene_missing')
    return OLD['new_decoder']().apply(rows[0]['packet']),rows[0]['rx']


def compare(asset,left,right,truth):
    require(left['offline_fixture'] is right['offline_fixture']
            and LABELS[left['label']]==(asset,'A') and LABELS[right['label']]==(asset,'B')
            and [row['query'] for row in left['calls']]==[row['query'] for row in right['calls']]
                ==[query_from_record(record) for record in order(truth['requests'])],
            'actual_assets_arms_or_queries_changed')
    prior,source=original_full(asset)
    terms=[indexed(row['terminal']['objects'],'name','same_scene_terminal') for row in (left,right)]
    require(terms[0].keys()==terms[1].keys()
            and all(all(obj[key]==terms[1][name][key] for key in ('evaluated','matrix_world','visible_get'))
                    for name,obj in terms[0].items()),'same_scene_end_source_changed')
    for index,(a,b) in enumerate(zip(left['calls'],right['calls'],strict=True)):
        require(a['measurement']==b['measurement'],'exact_distance_points_and_face_membership_changed')
        expected=truth['regions'][int(index==2)]
        for case in (a,b):
            OLD['_prove_geometry'](prior,case['scoped_packet'],case['query'],expected)
        result=a['measurement']
        fact=result['facts']['surface_proximity']
        witness=fact['value']['nearest_witness']
        require(fact['status']=='measured' and math.isclose(fact['value']['distance_m'],expected['distance_m'],
                rel_tol=1e-12,abs_tol=1e-10) and math.dist(witness['direction_a_to_b'],expected['direction'])<=1e-6
                and all(result['nearest'][side]['status']=='measured' and result['nearest'][side]['exact_membership']
                        for side in ('a','b')),'winner_does_not_match_independent_distance_and_source')
    cold,hot,alternate=right['calls']
    require(cold['expanded']['mode']=='resident_capture' and cold['lease'] is not None
            and cold['known_lease_sent'] is None and cold['transmitted']==left['calls'][0]['transmitted']
            and hot['expanded']['mode']=='lease_hit' and hot['lease']==cold['lease']==hot['known_lease_sent']
            and hot['host_wire_total_bytes']<left['calls'][1]['host_wire_total_bytes']
            and alternate['expanded']['mode']=='resident_capture' and alternate['known_lease_sent'] is None
            and alternate['transmitted']==left['calls'][2]['transmitted'],
            'resident_cold_repeat_or_alternate_gate_failed')
    if asset=='yanyite':
        require(not any(alternate['expanded'][k] for k in ('to_mesh','triangulations','world_transforms'))
                and alternate['expanded']['box_triangles_scanned']>0,
                'same_pair_new_box_redid_world_geometry_or_did_not_scan')
    return {'selective_residency_passed':True,'source_and_exact_witness_equal':True,
            'third_query_expanded_objects':alternate['expanded']['expanded_objects'],
            'third_query_box_triangles':alternate['expanded']['box_triangles_scanned'],
            'original_complete_geometry':source,
            'complete_slot_ns':[left['window_ns'],right['window_ns']],'offline_fixture':left['offline_fixture']}
