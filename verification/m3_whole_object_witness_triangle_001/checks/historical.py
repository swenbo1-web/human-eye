"""Bind the three original whole-pair tools to their owned capture and source corroboration."""

from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
PRIOR = V/'m1_source_region_no_image_native_transfer_001'
RUNTIME = Path('D:/he_m1_source_region_no_image_native_transfer_001')
ARCHIVE_SHA = '18f4ad4640cdbff60cef0e20eabfc7e42313ec87ab87395ff729690e8990e78e'
FREEZE_SHA = 'ea8470e5be77195c07927425d2ebd3769eb4df6d57743dc27c6b44c0957a30b9'
BINDING = V/'m1_source_region_no_image_measurement_packet_001/install/PRODUCT_RUN_BINDING.json'
E = run_path(str(PRIOR/'checks/evidence.py'))
T = E['T']
require,read,pin = (T[k] for k in ('require','read','pin'))
LABELS = ('P1','P2','P3')
KNOWN = {
    'P1': {'a':[4,7],'b':[0,1,4,5,10]},
    'P2': {'a':[0,1,6,8,9],'b':[0,1,4,5,10]},
    'P3': {'a':[6,11],'b':[0]},
}


def digest(raw):
    return sha256(raw).hexdigest()


def slot_capture(slot, binding, product, take):
    oracle = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    closure = run_path(str(V/'perf050_dense_micro_surface_holdout_recovery_001/qualification/verify.py'))
    native = closure['closed_wire'](slot)
    captures,rows = oracle['decode_captures'](slot,binding,oracle['Audit']())
    commands = [item for item in rows if item['command']['command'] in ('capture','capture_scene','capture_task')]
    require(len(captures)==len(commands),'native_capture_or_its_owned_call_order_mismatched')
    matches = []
    receipt = product['receipt']
    for item,capture in zip(commands,captures,strict=True):
        seq = item['wire_sequence']
        event = native[seq]['worker_event']
        if receipt['started_ns']<=event['started_ns'] and event['started_ns']+event['elapsed_ns']<=receipt['received_complete_ns']:
            matches.append((seq,capture))
    require(len(matches)==1,'measurement_has_no_unique_current_native_capture')
    seq,capture = matches[0]
    for name in ('REQUEST.bin','RESPONSE.bin'):
        take(slot/'native/WIRE'/f'{seq:03d}'/name)
    require(capture['revision']==product['producer']['binding']['scene_revision'],
            'exact_owned_capture_revision_does_not_match_public_binding')
    return seq,capture


def product_call(slot, owner_ordinal, product_ordinal, trace, visible, take):
    owner = slot/'owner'/f'tool_{owner_ordinal:02d}'
    product = slot/'product_calls'/f'call_{product_ordinal:03d}'
    producer_path = slot/'product_full'/product.name/'SERVICE_RESULT.json'
    outer_request,outer_reply = (json.loads(take(owner/file)) for file in ('REQUEST.json','RESPONSE.json'))
    req,reply,receipt = (json.loads(take(product/file)) for file in ('REQUEST.json','RESPONSE.json','RECEIPT.json'))
    native = slot/'mcp'/f"rpc_{receipt['index']:02d}"
    tx,rx = (take(native/name) for name in ('TX.bin','RX.bin'))
    source_raw = take(producer_path)
    event, = [row for row in trace if row.get('producer_archive') is not None
              and Path(row['producer_archive']['path'])==producer_path]
    require(json.loads(tx)==req==event['request'] and json.loads(rx)==reply==event['response']
            and receipt==event['receipt'] and req['id']==reply['id']
            and receipt['RX_sha256']==digest(rx) and receipt['RX_bytes']==len(rx) and receipt['TX_bytes']==len(tx)
            and event['producer_archive']['sha256']==digest(source_raw)
            and outer_reply['result']==reply['result'] and outer_request['params']['arguments']==req['params']['arguments']
            and outer_request['params']['name']==req['params']['name']=='human_eye_scene_observe'
            and json.loads(take(owner/'PRODUCT_RESPONSE.json'))==reply
            and json.loads(take(owner/'PRODUCT_REQUEST.json'))==req,
            'original_product_mcp_owner_or_host_producer_wire_changed')
    result,text,body = E['public'](reply)
    consumer, = [item for item in visible if item.get('arguments')==req['params']['arguments']]
    require(consumer['result']['content']==result['content'],
            'actual_CLI_tool_delivery_differs_from_wire')
    producer = json.loads(source_raw)
    require(body.get('binding',{}).get('binding_sha256') in
            (None,producer['binding'].get('binding_sha256')),'original_display_binding_detached')
    return {'request':req,'reply':reply,'body':body,'text':text,'producer':producer,
            'wire_before_decode':{'request_sha256':digest(tx),'response_sha256':digest(rx)},
            'receipt':receipt,'actual_consumer_item':consumer['id']}


@lru_cache(maxsize=None)
def historical(label):
    require(label in LABELS,'registered_sealed_original_P_slot_required')
    _,config = T['scenario'](label)
    target,reference = (config[key] for key in ('target','reference'))
    installed = read(BINDING)
    slot = RUNTIME/'slots'/label
    index_file = PRIOR/'RAW_INDEX.json'
    index = read(index_file)
    frozen = pin(PRIOR/'FROZEN.json',FREEZE_SHA)
    archive = PRIOR/index['archive']['name']
    zip_pin = pin(archive,ARCHIVE_SHA)
    require(index['freeze_sha256']==frozen['sha256'] and zip_pin['sha256']==index['archive']['sha256']
            and zip_pin['bytes']==index['archive']['bytes'],'historical_archive_and_freeze_identity_changed')
    pins = {}
    with ZipFile(archive) as z:
        def take(path):
            member = 'runtime/'+path.relative_to(RUNTIME).as_posix()
            raw = path.read_bytes()
            local = pin(path)
            proof = index['members'][member]
            require(raw==z.read(member) and (local['sha256'],local['bytes'])==(proof['sha256'],proof['bytes']),
                    'actual_original_does_not_equal_sealed_member/'+member)
            pins[member] = local
            return raw

        raw,publication = (json.loads(take(slot/file)) for file in ('SLOT_RESULT.json','SLOT_PUBLICATION.json'))
        require(raw['status']==publication['status']==('failed' if label=='P2' else 'completed')
                and publication['result_sha256']==pins['runtime/slots/'+label+'/SLOT_RESULT.json']['sha256']
                and raw['closure_verification']['passed'] and raw['independent_before_after']['passed'],
                'original_slot_failure_disposition_or_owned_read_only_close_changed')
        first,last = (json.loads(take(slot/file)) for file in
                      ('initial_capture/TERMINAL_SOURCE.json','TERMINAL_SOURCE.json'))
        source_proof = T['verify_source'](last,first)
        require(digest(take(slot/'native/input.blend'))==T['ASSET_SHA']==raw['asset_sha256'],
                'sealed_owned_source_asset_changed')
        trace = [json.loads(line) for line in take(slot/'PUBLIC_REQUESTS.jsonl').splitlines() if line]
        stdout = [json.loads(line) for line in take(slot/'consumer/stdout.raw.bin').splitlines() if line]
        visible = [item['item'] for item in stdout if item.get('type')=='item.completed'
                   and item.get('item',{}).get('type')=='mcp_tool_call' and not item['item'].get('error')]
        whole = product_call(slot,2,2,trace,visible,take)
        region = product_call(slot,4,3,trace,visible,take)
        pair = [{'name':name} for name in (target,reference)]
        mesh_a = T['objects'](last)[target]['evaluated']
        entire_faces = list(range(len(mesh_a['triangles'])))
        require(whole['request']['params']['arguments']=={'query':{'mode':'task','objects':pair,
                    'requested_facts':['surface_proximity']},'include_image':False,'response_detail':'full'}
                and region['request']['params']['arguments']=={'query':{'mode':'source_region',
                    'region':{'object':pair[0],'source_triangle_indices':entire_faces},
                    'reference':pair[1],'requested_facts':['surface_proximity']},'include_image':False},
                'archived_request_is_not_its_registered_two_whole_surface_scopes')
        whole_seq,capture = slot_capture(slot,installed,whole,take)
        other_seq,full_capture = slot_capture(slot,installed,region,take)
    names = [target,reference]
    body = whole['body']
    original_full_proof = E['whole_proof'](label,whole['reply'],whole['producer'],last,installed,capture=capture)
    state = capture['capture_state']
    require(capture['host_identity']['document_epoch']==full_capture['host_identity']['document_epoch']
            and all(state[field]==full_capture['capture_state'][field] for field in ('instance_id','epoch','revision')),
            'whole_and_full_selection_measurements_not_same_owned_generation')
    E['prove_capture'](full_capture,last,T['objects'](last),revision=region['producer']['binding']['scene_revision'],
                      scope='complete_scene_meshes',generation=full_capture['capture_state'],
                      epoch=full_capture['host_identity']['document_epoch'])
    task = region['body']['task_result']
    membership = task['source_mapping']['nearest_witness']
    require(region['body']['observation_status']=='image_not_requested' and region['body']['images']==[]
            and region['body']['region_ref']['source_triangle_indices']==entire_faces
            and region['body']['region']['object_name']==target and task['reference']['name']==reference
            and region['producer']['facts']['region']['source_triangle_indices']==entire_faces
            and task['facts']==body['facts']==region['producer']['task_result']['facts']
            and task['unit']==body['unit']=='m' and task['coordinate_frame']==body['coordinate_frame']=='world',
            'full_selection_corroboration_has_a_different_point_pair_world_scope_or_fact')
    independent = E['fact_proof'](label,last,'whole',task['facts']['surface_proximity'],membership)
    proven = {side:value['exact_source_triangle_indices'] for side,value in independent['source_memberships'].items()}
    require(proven==KNOWN[label],'independent_current_source_triangle_memberships_changed')
    return {'label':label,'names':names,'historical_status':raw['status'],
            'request':whole['request'],'reply':whole['reply'],'text':whole['text'],'producer':whole['producer'],
            'source':last,'capture':capture,'membership':proven,'existing_proof':original_full_proof,
            'selected_corroboration':{'wire':region['wire_before_decode'],'current_region_ref':region['body']['region_ref'],
                                     'actual_consumer_item':region['actual_consumer_item'],'source_proof':independent},
            'whole_wire':whole['wire_before_decode'],'whole_consumer_item':whole['actual_consumer_item'],
            'whole_native_capture_wire':whole_seq,'corroboration_native_capture_wire':other_seq,
            'source_proof':source_proof,'source_pins':{'archive':zip_pin,'index':pin(index_file),
                                                      'frozen':frozen,'members':pins}}


def source_report(label):
    retained = historical(label)
    skip = {'source','capture','request','reply','producer','text'}
    return {key:value for key,value in retained.items() if key not in skip}


if __name__=='__main__':
    print(json.dumps({'passed':True,'sealed_labels':{label:source_report(label) for label in LABELS}},
                     ensure_ascii=False,allow_nan=False,indent=2))
