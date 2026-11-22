"""Audit sealed source-region cases and score actual replay lines through both CLI limits."""

import argparse
from collections import Counter
from fractions import Fraction as F
from hashlib import sha256
from math import sqrt
import json
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
HOLDOUT = V/'m1_region_task_first_packet_consumption_holdout_recovery_001'
RANK = V/'perf050_source_scope_rank_transfer_recovery_001'
HOLDOUT_RUN = Path('D:/he_m1_region_task_first_packet_consumption_holdout_recovery_001')
RANK_RUN = Path('D:/he_perf050_source_scope_rank_transfer_recovery_001')
DOMAIN = 'zero_based_object_local_current_evaluated_capture_triangle_rows'
SCOPE = 'complete_selected_source_triangle_union_to_reference_triangle_surface'
FACT = 'surface_proximity'
FULL = 'human-eye-source-region-observation-v1'
COMPACT = 'source-region-brief-v2'
BINDING_OVERLAYS = {'runtime_source_sha256','source_status','disk_status','source_check_scope'}
CASES = {'holdout_A1':(HOLDOUT,HOLDOUT_RUN,'A1',2,'Component_417','M4_Far_00',[0,1]),
         'holdout_B1':(HOLDOUT,HOLDOUT_RUN,'B1',2,'Component_417','M4_Far_00',[0,1]),
         'independent_P1':(RANK,RANK_RUN,'P1',1,'Obj_07','Obj_05',[0,1,2,3])}
ARCHIVES = {
    HOLDOUT:'a61668ab58b0bf8160eb15838930137547cdb55f29b52d4186c9cea42f5064e7',
    RANK:'fef71aa0e06b589e386783f800ee67f507cc10b8a78bcd69de29d3b02f93810c',
}
MEMBERSHIP = run_path(str(V/'m5_observe_measure_001/oracle.py'))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(raw):
    return sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path, raw=None):
    raw = path.read_bytes() if raw is None else raw
    return {'path':path.resolve().as_posix(),'bytes':len(raw),'sha256':digest(raw)}


def fingerprint(value):
    return digest(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8'))


def public(reply):
    result = reply['result'] if 'result' in reply else reply
    require(result['isError'] is False and len(result['content'])==1
            and result['content'][0]['type']=='text','no_image_measurement_requires_exactly_one_success_text_block')
    text = result['content'][0]['text']
    return result,text,json.loads(text)


def fixture(case):
    namespace,root,label,call,target,reference,indices = CASES[case]
    slot = root/'slots'/label
    want = {'include_image':False,'query':{'mode':'source_region',
             'region':{'object':{'name':target},'source_triangle_indices':indices},
             'reference':{'name':reference},'requested_facts':[FACT]},'response_detail':'full'}
    dense = namespace==HOLDOUT
    index_path = namespace/('RAW_INDEX.json' if dense else 'RUNTIME_INDEX.json')
    index = read(index_path)
    archive = namespace/index['archive']['name'] if dense else Path(index['archive']['path'])
    archive_pin = pin(archive)
    require((archive_pin['bytes'],archive_pin['sha256'])==(index['archive']['bytes'],index['archive']['sha256'])
            and archive_pin['sha256']==ARCHIVES[namespace],'sealed_historical_archive_changed')
    records = index['members'] if dense else {row['path']:row for row in index['files']}
    pins = {}
    with ZipFile(archive) as sealed:
        def take(path):
            relative = path.relative_to(root).as_posix()
            member = 'runtime/'+relative if dense else relative
            raw = path.read_bytes()
            original = records[member]
            checked = pin(path,raw)
            require(raw==sealed.read(member)
                    and (checked['sha256'],checked['bytes'])==(original['sha256'],original['bytes']),
                    'sealed_member_changed/'+member)
            pins[relative] = checked
            return raw

        public_rows = [json.loads(line) for line in take(slot/'PUBLIC_REQUESTS.jsonl').splitlines() if line]

        def verified_call(ordinal,options):
            owner = slot/'owner'/f'tool_{ordinal:02d}'
            producer_path = slot/'product_full'/f'call_{ordinal:03d}'/'SERVICE_RESULT.json'
            produced_bytes = take(producer_path)
            operation, = [row for row in public_rows if row.get('producer_archive') is not None
                          and Path(row['producer_archive']['path'])==producer_path]
            raw = operation['receipt']
            wire = slot/'mcp'/f"rpc_{raw['index']:02d}"
            tx,rx = (take(wire/f'{key}.bin') for key in ('TX','RX'))
            req,reply = (json.loads(value) for value in (tx,rx))
            require(req==operation['request'] and reply==operation['response'] and req['id']==reply['id']
                    and req['params']['name']=='human_eye_scene_observe'
                    and req['params']['arguments']==options and raw['RX_sha256']==digest(rx)
                    and raw['TX_bytes']==len(tx) and raw['RX_bytes']==len(rx)
                    and operation['producer_archive']['sha256']==digest(produced_bytes)
                    and json.loads(take(owner/'REQUEST.json'))['params']['arguments']==options
                    and json.loads(take(owner/'RESPONSE.json'))['result']==reply['result']
                    and json.loads(take(owner/'PRODUCT_RESPONSE.json'))==reply,
                    'historical_public_request_reply_or_producer_not_same_actual_call')
            take(producer_path.with_name('READ_CONTEXT.json'))
            return reply,json.loads(produced_bytes)

        full,producer = verified_call(call,want)
        compact = None
        if dense:
            compact,warm = verified_call(call+1,{**want,'response_detail':'brief'})
            require(all(warm[key]==producer[key] for key in ('facts','region_ref','task_result','source_mapping','binding'))
                    and warm['work']['prepare_cache_hit'] is True
                    and warm['work']['task_query']['result_cache_hit'] is True,'original_brief_not_same_measurement_or_capture')
        else:
            img,readback = verified_call(call+1,{**want,'include_image':True,'response_detail':'brief'})
            require(readback['frames'] and img['result']['content'][1]['type']=='image'
                    and all(readback[key]==producer[key] for key in ('region_ref','task_result','source_mapping')),
                    'rank_original_same_selection_image_or_source_mapping_differs')
        first,last = (json.loads(take(slot/path)) for path in
                      ('initial_capture/TERMINAL_SOURCE.json','TERMINAL_SOURCE.json'))
        closure_raw = take(slot/'SLOT_RESULT.json')
        closure,publication = json.loads(closure_raw),json.loads(take(slot/'SLOT_PUBLICATION.json'))
        require(closure['status']==publication['status']=='completed'
                and publication['result_sha256']==digest(closure_raw)
                and closure['closure_verification']['passed'] and closure['independent_before_after']['passed']
                and all(first[key]==last[key] for key in ('source','objects','source_face_offsets',
                    'display_object_mask','display_scope','layer_collections','scene_cameras'))
                and digest(take(slot/'native/input.blend'))==last['source']['asset_sha256']==closure['asset_sha256'],
                'historical_current_native_evaluated_arrays_or_read_only_close_changed')
        answer = take(slot/'consumer/PUBLIC_FINAL.txt').decode('utf8')
        events = [json.loads(line) for line in take(slot/'consumer/stdout.raw.bin').splitlines() if line]
        items = [event['item'] for event in events if event.get('type')=='item.completed']
        answers = [item['text'] for item in items if item['type']=='agent_message']
        consumed = [item for item in items if item['type']=='mcp_tool_call'
                    and item.get('arguments')==want]
        require(answers and answers[-1]==answer and len(consumed)==1
                and consumed[0]['result']['content']==full['result']['content'],
                'sealed_full_or_final_answer_did_not_reach_cli_original')
        expected_values = ('0.25','(1.5, 0.5, 1.75)','(1.5, 0.5, 2.0)') if dense else (
            '7.318640584152224','(4.75, 4, 1)','(12, 4, 0)')
        require(all(text in answer for text in (target,reference,*expected_values)),
                'historical_used_measurement_omitted_from_final_answer')
    _,body_text,body = public(full)
    if dense:
        require(len(body_text.encode())==48037 and len(public(compact)[1].encode())==9686,
                'historical_full_or_warm_compact_size_changed')
    else:
        require(len(body_text.encode())==39717,'rank_historical_full_size_changed')
    require({k:v for k,v in body.items() if k!='image_delivery'}==
            {k:v for k,v in producer.items() if k!='image_delivery'},'historical_full_not_same_producer')
    return {'case':case,'target':target,'reference':reference,'indices':indices,'source':last,
            'full':full,'compact':compact,'request_arguments':want,'producer':producer,'historical_body_bytes':len(body_text.encode()),
            'originals':{'archive':archive_pin,'index':pin(index_path),'members':pins}}


def geometry(record, producer):
    original = record['producer']
    stable = ('binding','region_ref','source_mapping','status','observation_status','task_result','facts','frames')
    for key in stable:
        left,right = producer[key],original[key]
        if key in ('task_result','binding'):
            # Runtime source attestation can refer to the replay installation; the scene binding cannot change.
            left,right = ({field:value for field,value in item.items() if field not in BINDING_OVERLAYS}
                          if key=='binding' else {**item,'binding':{field:value for field,value in item['binding'].items()
                                               if field not in BINDING_OVERLAYS}} for item in (left,right))
        require(left==right,'actual_replay_producer_not_the_frozen_current_geometry/'+key)
    binding = producer['binding']
    source = record['source']
    target,reference,selected = (record[key] for key in ('target','reference','indices'))
    src = {row['name']:row for row in source['objects']}
    meshes = {name:row['evaluated'] for name,row in src.items()}
    named = {row['object_name']:row for row in binding['objects']}
    require(source['source']['scale_length']==1 and source['source']['unit_settings']['system']=='METRIC'
            and source['source']['source_index_domain']==DOMAIN
            and binding['source']=='blender' and binding['unit']=='m' and binding['coordinate_frame']=='world'
            and binding['capture_scope']=='complete_scene_meshes' and len(src)==len(source['objects'])
            and len(named)==len(binding['objects'])==len(src) and named.keys()==src.keys()
            and all(named[name]['object_index']==index and named[name]['host_id']==src[name]['object_id']
                    and named[name]['instance_id']==src[name]['instance_id']
                    for index,name in enumerate(named)), 'current_capture_source_units_roster_or_instances_changed')
    ordered = [{'host_id':named[name]['host_id'],'instance_id':named[name]['instance_id'],
                'vertices':meshes[name]['vertices_world_m'],'faces':meshes[name]['triangles']} for name in named]
    ordered_sha = fingerprint(ordered)
    generation = {k:binding['capture_state'][k] for k in ('instance_id','epoch','revision')}
    ref = {'schema':'human-eye-source-region-ref-v1','document_epoch':binding['document_epoch'],
           'host_id':named[target]['host_id'],'instance_id':named[target]['instance_id'],
           'ordered_geometry_sha256':ordered_sha,'capture_generation':generation,'source_triangle_indices':selected}
    ref['region_id'] = 'source-region:'+fingerprint(ref)
    require(ref==producer['region_ref']==producer['task_result']['region_ref']
            and ordered_sha==binding['ordered_geometry_sha256'],
            'current_region_reference_does_not_bind_ordered_source')
    expected_reference = {'name':reference,'object_id':named[reference]['host_id'],
                          'instance_id':named[reference]['instance_id'],'object_index':named[reference]['object_index']}
    prod_task = producer['task_result']
    require(prod_task['reference']==expected_reference and prod_task['measurement_scope']==SCOPE
            and prod_task['status']=='complete' and prod_task['binding']==binding,
            'producer_scope_not_selected_union_to_current_entire_reference')
    mesh_a,mesh_b = meshes[target],meshes[reference]
    source_faces = [mesh_a['triangles'][idx] for idx in selected]
    point_indices = sorted({j for face in source_faces for j in face})
    pos = {j:i for i,j in enumerate(point_indices)}
    region_mapping = {'index_domain':DOMAIN,'submesh_to_source_triangle_indices':selected,
                      'submesh_to_source_vertex_indices':point_indices,'triangles_source_vertices':source_faces,
                      'triangles_submesh_vertices':[[pos[j] for j in face] for face in source_faces]}
    selected_world = [mesh_a['vertices_world_m'][j] for j in point_indices]
    region = {'object_name':target,'host_id':ref['host_id'],'instance_id':ref['instance_id'],'index_domain':DOMAIN,
             'source_triangle_indices':selected,'source_vertex_indices':point_indices,
             'triangles_source_vertices':source_faces,'vertices_world_m':selected_world,
             'bbox_min_world_m':[min(axis) for axis in zip(*selected_world)],
             'bbox_max_world_m':[max(axis) for axis in zip(*selected_world)]}
    require(producer['source_mapping']==prod_task['source_mapping']['region']==region_mapping
            and producer['facts']['region']==region,'original_topology_or_selected_source_face_mapping_disagrees')
    proof = proximity(prod_task,mesh_a,mesh_b,selected,reference)
    return {'producer':producer,'expected_reference':expected_reference,'region_ref':ref,'binding':binding,
            'region_mapping':region_mapping,'region':region,'measurement':proof,
            'reference_source_triangle_count':len(mesh_b['triangles'])}


def proximity(task,mesh_a,mesh_b,selected,reference):
    vector,point_distance = (MEMBERSHIP[k] for k in ('vector','triangle_distance_squared'))
    av,bv = ([vector(row) for row in mesh['vertices_world_m']] for mesh in (mesh_a,mesh_b))
    af,bf = (mesh['triangles'] for mesh in (mesh_a,mesh_b))
    part = [av[j] for idx in selected for j in af[idx]]
    if reference=='M4_Far_00':
        min_z,max_z = min(p[2] for p in part),max(p[2] for p in part)
        z_ranges = [(min(bv[j][2] for j in face),max(bv[j][2] for j in face)) for face in bf]
        require(all(hi<=1 or lo==hi==2 for lo,hi in z_ranges) and any(lo==2 for lo,hi in z_ranges)
                and 1<min_z<=max_z<2,'whole_dense_reference_vertical_separation_not_proven')
        lower_squared = min(min_z-1,2-max_z)**2
        expected_pair = ([1.5,.5,1.75],[1.5,.5,2.])
        mechanism = 'All reference triangles are at z=2 or entirely at z<=1. The selected z interval bounds both families.'
        expected_lower = F(1,16)
    else:
        horizontal = max(abs(p[k]) for p in part for k in (0,1))
        min_z = min(p[2] for p in part)
        require(all(p[2]==0 for p in bv) and horizontal<12 and min_z>0 and all(
            any(all(sign*bv[j][axis]>=12 for j in face) for axis in (0,1) for sign in (-1,1)) for face in bf),
            'whole_ring_triangle_separation_halfspace_not_proven')
        lower_squared = (12-horizontal)**2+min_z**2
        expected_pair = ([4.75,4.,1.],[12.,4.,0.])
        mechanism = 'Every reference triangle is at z=0 and entirely beyond one signed x/y=12 plane. The selected maximum absolute x/y and minimum z give the bound.'
        expected_lower = F(857,16)
    require(set(task['facts'])=={FACT},'requires_single_surface_proximity_fact')
    fact = task['facts'][FACT]
    require(fact['status']==fact['direction_status']==fact['witness_status']=='measured'
            and fact['semantics']=='current_evaluated_triangle_surfaces_world_metres',
            'distance_direction_or_witness_is_not_measured')
    value = fact['value']
    witness = value['nearest_witness']
    a,b = vector(witness['a']),vector(witness['b'])
    delta = [y-x for x,y in zip(a,b,strict=True)]
    dist = sqrt(lower_squared)
    require(lower_squared==expected_lower==sum(v*v for v in delta)
            and (witness['a'],witness['b'])==expected_pair
            and abs(value['distance_m']-dist)<1e-13
            and all(abs(received-float(d)/dist)<1e-13 for received,d in zip(witness['direction_a_to_b'],delta,strict=True)),
            'actual_current_pair_does_not_attain_independent_distance_or_world_direction')
    memberships = {}
    topology = []
    sides = (('a',a,av,af,selected),('b',b,bv,bf,range(len(bf))))
    for side,point,vertices,faces,domain in sides:
        members = [idx for idx in domain if point_distance(point,tuple(vertices[j] for j in faces[idx]))==0]
        corners = sorted({j for idx in members for j in faces[idx] if vertices[j]==point})
        expected = {'status':'measured','exact_membership':True,'index_domain':DOMAIN,
                    'source_triangle_indices':members,'source_vertex_indices':corners}
        require(members and task['source_mapping']['nearest_witness'][side]==expected,
                'nearest_point_not_on_proven_source_triangles_and_vertices/'+side)
        memberships[side] = expected
        incidence = Counter(tuple(sorted((p,q))) for i in domain for p,q in zip(faces[i],faces[i][1:]+faces[i][:1]))
        topology.append({'boundary_edge_count':sum(n==1 for n in incidence.values()),
                         'nonmanifold_edge_count':sum(n>2 for n in incidence.values())})
    require(value['topology']==topology,'published_surface_edge_topology_disagrees_with_ordered_source')
    return {'distance_squared_m2':str(lower_squared),'distance_m':dist,'nearest_witness':witness,
            'reference_entire_mesh_triangles':len(bf),'source_membership':memberships,
            'surface_topology':topology,'independent_lower_bound':mechanism}


def verify_packet(packet, proof, mode):
    original = proof['producer']
    task = packet['task_result']
    require(packet['read_only'] is True and packet['execution_authority'] is False
            and packet['result_kind']=='source_region' and packet['status']=='complete'
            and packet['observation_status']=='image_not_requested' and task['status']=='complete'
            and task['measurement_scope']==SCOPE and packet['region_ref']==proof['region_ref']
            and task['reference']==proof['expected_reference'] and task['facts']==original['task_result']['facts']
            and task['source_mapping']['nearest_witness']==proof['measurement']['source_membership'],
            'actual_public_distance_scope_regions_source_points_or_status_changed')
    delivery = packet['image_delivery']
    require(all(delivery[key]==0 for key in ('mcp_content_constructed_image_count','local_verified_image_count','new_raster_attempts')),
            'actual_no_image_public_delivery_image_or_raster_counter_changed')
    if mode=='compact':
        region = dict(proof['region'])
        for field,count in (('source_triangle_indices','source_triangle_count'),('source_vertex_indices','source_vertex_count')):
            region[count] = len(region.pop(field))
        del region['triangles_source_vertices'],region['vertices_world_m']
        require(packet['schema']==COMPACT and packet['images']==[] and packet.get('frames',[])==[]
                and packet['region']==region and {'unit':task['unit'],'coordinate_frame':task['coordinate_frame']}
                =={'unit':'m','coordinate_frame':'world'} and all(packet['binding'][key]==proof['binding'][key]
                    for key in ('source_binding_sha256','binding_sha256')),
                'compact_lost_current_frame_world_units_source_or_region_binding')
    else:
        require(packet['schema']==FULL and packet['frames']==packet.get('constructed_frames',[])==[]
                and packet['binding']==task['binding']==proof['binding']
                and packet['source_mapping']==task['source_mapping']['region']==proof['region_mapping']
                and task['region_ref']==proof['region_ref'] and packet['facts']['region']==proof['region'],
                'standard_full_original_topology_or_complete_source_mapping_changed')


def fixed_cli(result, text, proof, mode):
    policy = run_path(str(V/'m4_cross_scale_live_qualification_001/checks/delivery.py'))['budget_helpers']
    helpers,limits = policy()
    require((limits['MCP_bytes'],limits['history_approximate_tokens'])==(12000,3000),'fixed_CLI_limits_changed')
    sys.path.insert(0,str(V/'m5_global_observe_measure_qualification_001/checks'))
    omitted_paths = run_path(str(V/'m5_global_observe_measure_qualification_001/checks/live_wire.py'))['omitted_paths']
    stages = []
    for wall,head in zip(('0.0000','10.0000','100.0000'),(33,34,35),strict=True):
        raw = helpers['model_items'](result,wall)
        first = helpers['truncate_items'](raw,limits['MCP_bytes'])
        last = helpers['truncate_items'](first,limits['history_approximate_tokens'],token_mode=True)
        require(len(raw[0]['text'].encode())==head,'fixed_CLI_header_bytes_changed')
        for name,current in (('MCP',first),('history',last)):
            require(len(current)==2 and all(item['type']=='input_text' for item in current),
                    'fixed_CLI_no_image_block_count_changed')
            kept = current[1]['text']
            exact = text==kept and raw==current
            lost = [] if exact else ['/'+'/'.join(map(str,path)) for path in omitted_paths(text,kept)]
            critical = [path for path in lost if path.startswith(('/region_ref','/task_result/measurement_scope',
                         '/task_result/reference','/task_result/facts/surface_proximity','/task_result/source_mapping/nearest_witness'))]
            if mode=='compact':
                require(exact and not critical,'compact_lost_required_source_or_measurement/'+name+str(head))
                verify_packet(json.loads(kept),proof,mode)
            stages.append({'header_bytes':head,'phase':name,'body_utf8_bytes':len(kept.encode()),
                           'original_body_exact':exact,'lost_critical_field_count':len(critical),
                           'lost_critical_fields':critical,'body_sha256':digest(kept.encode())})
    return {'mode':'descriptive_original_full_control' if mode=='full' else 'exact_compact_acceptance',
            'limits':limits,'stages':stages,'exact_stages':sum(row['original_body_exact'] for row in stages),
            'all_necessary_fields_retained':all(row['original_body_exact'] and row['lost_critical_field_count']==0
                                                for row in stages)}


def score(case,reply,*,mode,producer=None,request=None):
    record = fixture(case)
    proof = geometry(record,record['producer'] if producer is None else producer)
    selection = None
    if request is not None:
        require(request['id']==reply['id'] and request['method']=='tools/call'
                and request['params']['name']=='human_eye_scene_observe',
                'actual_request_not_the_received_measurement_reply')
        args = request['params']['arguments']
        expected,actual = (dict(value['query']) for value in (record['request_arguments'],args))
        if 'region_ref' in actual:
            require(actual.pop('region_ref')==proof['region_ref'] and 'region' not in actual,
                    'actual_request_region_ref_not_same_current_selection')
            expected.pop('region')
            selection = 'same_capture_region_ref'
        else:
            selection = 'explicit_source_faces'
        require(actual==expected and 'include_image' in args and args['include_image'] is False
                and args.get('response_detail') in (None,'brief','full'),
                'actual_request_intent_or_no_image_scope_changed')
    result,text,packet = public(reply)
    size = len(text.encode())
    require(mode!='compact' or size<=10800,'actual_compact_body_exceeds_10800_bytes')
    verify_packet(packet,proof,mode)
    return {'case':case,'passed':True,'mode':mode,'actual_body_utf8_bytes':size,
            'actual_body_sha256':digest(text.encode()),'original_historical_full_utf8_bytes':record['historical_body_bytes'],
            'target':record['target'],'reference':record['reference'],'selected_faces':record['indices'],'request_selection':selection,
            'reference_source_triangles':proof['reference_source_triangle_count'],
            'ordered_current_region_reference':proof['region_ref'],'measurement_scope':SCOPE,'unit':'m','coordinate_frame':'world',
            'independent_geometry':proof['measurement'],'source_topology':proof['region_mapping'],
            'fixed_CLI':fixed_cli(result,text,proof,mode),'sealed_originals':record['originals']}


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--case',choices=tuple(CASES),required=True)
    cli.add_argument('--response',type=Path)
    cli.add_argument('--producer',type=Path)
    cli.add_argument('--request',type=Path)
    cli.add_argument('--mode',choices=('full','compact'),required=True)
    cli.add_argument('--output',type=Path)
    args = cli.parse_args()
    response = read(args.response) if args.response else fixture(args.case)[args.mode]
    require(response is not None,'no_original_compact_for_same_independent_request_supply_actual_replay_response')
    report = score(args.case,response,mode=args.mode,producer=read(args.producer) if args.producer else None,
                   request=read(args.request) if args.request else None)
    if args.response:
        report['actual_replay_response'] = pin(args.response)
    if args.producer:
        report['actual_replay_producer'] = pin(args.producer)
    if args.request:
        report['actual_replay_request'] = pin(args.request)
    payload = json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf8',newline='\n') as stream:
            stream.write(payload)
    else:
        print(payload,end='')
