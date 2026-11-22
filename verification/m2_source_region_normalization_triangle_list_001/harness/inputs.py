"""Bind the fixed source-region and default observation inputs to retained wires."""

import ast
import json
from pathlib import Path
import re
from runpy import run_path
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
RETAINED = V/'m4_source_region_nonplanar_short_circuit_001'
PRIOR_INPUTS = RETAINED/'harness/inputs.py'
GLOBAL_INPUTS = V/'m4_region_task_global_first_frame_001/harness/inputs.py'
old = run_path(str(PRIOR_INPUTS))
BASE = RETAINED/'install/PRODUCT_RUN_BINDING.json'
BASE_GIT = 'cca20c17401e75f564a9e881da977e5448bc3f94'
RUN = Path('D:/he_m2_source_region_normalization_triangle_list_001')
OLD_ROOT = Path('D:/he_m4_source_region_nonplanar_short_circuit_001')
OLD_GIT = 'a640d12814a5d0432f7b80ad690f2f1cc994a59a'
GLOBAL = V/'m4_region_task_global_first_frame_001'
GLOBAL_ROOT = Path('D:/he_m4_region_task_global_first_frame_001')
GLOBAL_GIT = '42ebf86d034fff9cc4bc788f815bd701b8e26eae'
TARGET = V/'perf050_target_observation_first_image_p2'
TARGET_ROOT = Path('D:/he_perf050_target_observation_first_image_p2')
TARGET_GIT = 'c41b106771b5e994d1555d87f21fca7507d494a8'
FIXTURES = (*old['FIXTURES'],'dual','defaults')
read, write, pin, digest, require, committed, verify_geometry = (
    old[name] for name in ('read','write','pin','digest','require','committed','verify_geometry')
)
CATALOGUE, PRIOR, SEAL = (old[name] for name in ('CATALOGUE','PRIOR','SEAL'))


def archived(root, path, index, bundle, prefix, pins):
    real = path.resolve(strict=True)
    key = prefix+real.relative_to(root.resolve()).as_posix()
    raw = real.read_bytes()
    checksum = digest(raw)
    require(index[key]==checksum and bundle.read(key)==raw,'fixed_archive_member_mismatch/'+key)
    pins.append({'path':str(real),**checksum})
    return raw


def indexed_archive(path, expected, pins):
    item = pin(path)
    require({k:item[k] for k in ('bytes','sha256')}=={k:expected[k] for k in ('bytes','sha256')},
            'fixed_archive_digest_mismatch/'+str(path))
    pins.append(item)
    return ZipFile(path)


def original_product_calls(slot, calls, member):
    tx,rx,full = [],[],[]
    for i in calls:
        folder = slot/'product_calls'/f'call_{i:03d}'
        tx.append(json.loads(member(folder/'REQUEST.json')))
        rx.append(json.loads(member(folder/'RESPONSE.json')))
        full.append(json.loads(member(slot/'product_full'/f'call_{i:03d}/SERVICE_RESULT.json')))
    return tx,rx,full


def prior_main(fixture):
    result_path = RETAINED/'RESULT.json'
    require(result_path.read_bytes()==committed(result_path,OLD_GIT),'recorded_main_baseline_continuity_changed')
    result = read(result_path)
    index_path = OLD_ROOT/'sealed/RAW_INDEX.json'
    index = read(index_path)
    archive = OLD_ROOT/'sealed/ORIGINAL_RUNTIME.zip'
    pins = [pin(result_path),pin(index_path)]
    proof = result['raw_evidence_local']
    require(index['archive']==proof['archive'] and index['member_count']==proof['member_count'],
            'direct_baseline_closed_archive_not_bound_to_Git_result')
    with indexed_archive(archive,index['archive'],pins) as bundle:
        member = lambda path:archived(OLD_ROOT,path,index['members'],bundle,'runtime/',pins)
        arm = OLD_ROOT/'arms/P1'
        summary = json.loads(member(arm/'SUMMARY.json'))
        closed = json.loads(member(arm/'REPLAY_CLOSE.json'))
        producer = json.loads(member(arm/'product_full/call_001/SERVICE_RESULT.json'))
        require(summary['passed'] is True and summary['product']['preparation_git']==BASE_GIT
                and closed['old_sources_unchanged'] is True and summary['closure']['confirmed'] is True
                and summary['closure']['exit_code']==0 and len(closed['calls'])==3,
                'previous_candidate_P1_originals_not_independently_closed')
        for n,original in enumerate((fixture['calls'][0],None,fixture['calls'][1]),1):
            folder = arm/'mcp'/f'rpc_{n+3:02d}'
            request = json.loads(member(folder/'TX.bin'))
            member(folder/'RX.bin')
            capture = json.loads(member(arm/f'CAPTURE_{n:02d}.json'))
            verify_geometry(capture,fixture['terminal'])
            delta = fixture['deltas'][int(n!=1)]
            require(capture['capture_state']==closed['calls'][n-1]['capture_state']==delta['capture']['capture_state']
                    and capture['display_snapshot']==delta['capture']['display_snapshot'],
                    'previous_candidate_capture_versus_fixed_native_wire_changed')
            if original is not None:
                require(request==original,'previous_candidate_real_query_changed')
        for f,frame in zip(summary['construct_frames'],fixture['frames'],strict=True):
            require(all(digest(member(Path(f[k]['path'])))==frame[k] for k in ('png','arrays'))
                    and f['view_name']==frame['view_name'],'previous_candidate_image_or_arrays_changed')
        require(producer['region_ref']==fixture['producer']['region_ref']
                and producer['task_result']['facts']==fixture['producer']['task_result']['facts'],
                'previous_candidate_public_region_or_measurement_changed')
    return {**fixture,'source_pins':fixture['source_pins']+pins}


def dual_inputs():
    item = old['FIXTURES']['main']
    root = Path('D:/he_m4_yanyite_dual_curved_region_native_001')
    index,archive,prefix,members,expected,pins = old['truth_index']('main',item,root)
    pins.append(pin(index))
    slot = root/'slots/P1'
    with indexed_archive(archive,expected,pins) as bundle:
        member = lambda path:archived(root,path,members,bundle,prefix,pins)
        original = json.loads(member(slot/'SLOT_RESULT.json'))
        pub = json.loads(member(slot/'SLOT_PUBLICATION.json'))
        require(original['closure_verification']['passed'] and original['independent_before_after']['passed']
                and pub['result_sha256']==digest((slot/'SLOT_RESULT.json').read_bytes())['sha256'],
                'actual_formal_failed_model_slot_not_source_and_process_closed')
        terminal = json.loads(member(slot/'TERMINAL_SOURCE.json'))
        pairs = [old['native_capture'](slot,key,count,member) for key,count in (('003',2),('004',0))]
        deltas,transport = list(zip(*pairs,strict=True))
        calls,responses,producers = original_product_calls(slot,(1,2),member)
        for i,(req,delta,full,count) in enumerate(zip(calls,deltas,producers,(311,331),strict=True)):
            args = req['params']['arguments']
            query = args['query']
            require(req['params']['name']=='human_eye_scene_observe'
                    and args['include_image'] is False and query['mode']=='source_region'
                    and query['reference']=={'name':'Cube'} and len(query['region']['source_triangle_indices'])==count
                    and query['region']['source_triangle_indices']==full['region_ref']['source_triangle_indices']
                    and full.get('frames')==[] and full['binding']['capture_state']==delta['capture']['capture_state']
                    and full['task_result']['facts']['surface_proximity']['status']=='measured',
                    'original_two_noimage_requests_not_bound_to_current_same_generation/'+str(i))
        require(deltas[0]['capture']==deltas[1]['capture']
                and deltas[0]['live_resources']==deltas[1]['live_resources'],'dual_generation_changed')
    return {'name':'dual','source_dimensions':item['sizes'],'original_slot':str(slot),'terminal':terminal,
            'producer':producers[0],'producers':producers,'frames':[],'deltas':deltas,'transport':transport,
            'calls':calls,'responses':responses,'source_pins':pins}


def target_wire(slot,number,command,resource_count,member):
    folder = slot/'native/WIRE'/number
    tx,rx = (member(folder/name) for name in ('REQUEST.bin','RESPONSE.bin'))
    request,reply = json.loads(tx),json.loads(rx)
    encoded = re.search(r'_request = _json.loads\((.+)\)\n',request['params']['code'])
    sent = json.loads(ast.literal_eval(encoded[1]))
    lines = [line for line in reply['result']['result'].splitlines()
             if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
    require(reply['status']=='success' and len(lines)==1,'original_target_capture_failed')
    packet = json.loads(lines[0].split(':',1)[1])
    payload = packet['result']
    require(packet['id']==sent['id'] and sent['command']==command
            and payload['schema']=='human-eye-scene-delta-v1' and len(payload['resources'])==resource_count,
            'original_target_command_or_transport_changed')
    return payload,{'wire':number,'command':command,'params':sent['params'],'TX':digest(tx),'RX':digest(rx),
                    'resource_count':resource_count}


def default_inputs():
    g = run_path(str(GLOBAL_INPUTS))['sealed_inputs']('main')
    pins = list(g['source_pins'])
    index_path = GLOBAL/'RAW_INDEX.json'
    require(index_path.read_bytes()==committed(index_path,GLOBAL_GIT),'global_entry_raw_index_changed')
    index = read(index_path)
    pins.append(pin(index_path))
    frames,calls,history = [],[],[]
    with indexed_archive(GLOBAL/index['archive']['name'],index['archive'],pins) as bundle:
        member = lambda path:archived(GLOBAL_ROOT,path,index['members'],bundle,'runtime/',pins)
        for lane,n,source in (('arms/P1',1,'region_task'),('controls/OP',5,'ordinary')):
            arm = GLOBAL_ROOT/lane
            report = json.loads(member(arm/'SUMMARY.json'))
            closed = json.loads(member(arm/'mcp/HELD_CLOSE.json'))
            require(report['passed'] and closed['confirmed'] and closed['exit_code']==0
                    and closed['production_eof_and_exit_verified'],'old_default_replay_did_not_pass')
            folder = arm/'mcp'/f'rpc_{n+3:02d}'
            request = json.loads(member(folder/'TX.bin'))
            result = json.loads(member(folder/'RX.bin'))
            producer = json.loads(member(arm/'product_full'/f'call_{n:03d}/SERVICE_RESULT.json'))
            decoded = json.loads(member(arm/f'CAPTURE_{n:02d}.json'))
            calls.append(request)
            history.append(result)
            frames.append(frame_hashes(producer,member))
            verify_geometry(decoded,g['terminal'])
            if source=='ordinary':
                ordinary_delta = {**g['deltas'][1],'capture':{
                    **g['deltas'][1]['capture'],
                    'revision':decoded['revision'],'capture_state':decoded['capture_state'],
                }}
            else:
                require(decoded['capture_state']==g['deltas'][0]['capture']['capture_state'],
                        'sealed_region_task_not_bound_to_fixed_native_wire')
    idx = TARGET/'RUNTIME_INDEX.json'
    require(idx.read_bytes()==committed(idx,TARGET_GIT),'target_runtime_index_differs_from_Git')
    ind = read(idx)
    roster = {row['path']:{k:row[k] for k in ('bytes','sha256')} for row in ind['files']}
    pins.append(pin(idx))
    target = TARGET_ROOT/'slots/P2'
    with indexed_archive(Path(ind['archive']['path']),ind['archive'],pins) as bundle:
        member = lambda path:archived(TARGET_ROOT,path,roster,bundle,'',pins)
        target_terminal = json.loads(member(target/'TERMINAL_SOURCE.json'))
        target_calls,target_history,target_producers = original_product_calls(target,(1,),member)
        ta,ar = target_wire(target,'002','capture_active_observation',3,member)
        args = target_calls[0]['params']['arguments']
        require(args['query']['mode']=='active_observation' and args['query']['objects']==[ar['params']['selector']]
                and args['query']['task_query']['objects']==[{'name':'M09'},{'name':'M03'}],
                'recorded_target_selectors_changed')
        frames.append(frame_hashes(target_producers[0],member))
        calls.extend(target_calls)
        history.extend(target_history)
    capture_plan = [
        (g['deltas'][0],{'command':'capture','params':{}},g['terminal']),
        (ordinary_delta,{'command':'capture','params':{}},g['terminal']),
        (ta,ar,subset_terminal(target_terminal,ta)),
    ]
    return {'name':'defaults','source_dimensions':g['source_dimensions'],'terminal':g['terminal'],
            'source_pins':pins,'capture_plan':capture_plan,'frames_by_call':frames,'calls':calls,'responses':history,
            'transport':[*g['transport'],ar]}


def subset_terminal(terminal,delta):
    object_ids = {row['object_id'] for row in delta['capture']['meshes']}
    return {**terminal,'objects':[row for row in terminal['objects'] if row['object_id'] in object_ids]}


def frame_hashes(producer,member):
    return [{'view_name':f['view_name'],'png':digest(member(Path(f['image_path']))),
             'arrays':digest(member(Path(f['arrays_path'])))}
            for f in producer.get('constructed_frames',producer['frames'])]


def sealed_inputs(name):
    if name=='dual':
        return dual_inputs()
    if name=='defaults':
        return default_inputs()
    fixture = old['sealed_inputs'](name)
    return prior_main(fixture) if name=='main' else fixture
