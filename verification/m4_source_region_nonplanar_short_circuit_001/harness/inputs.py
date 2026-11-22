"""Load only the original scene captures, requests and image arrays of the three fixtures."""

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
REPO = V.parent
RUN = Path('D:/he_m4_source_region_nonplanar_short_circuit_001')
PRIOR = V/'m4_dense_sweep_integrated_native_pilot_001'
SEAL = V/'m5_harness_recovery_001'
CATALOGUE = PRIOR/'inputs/EVIDENCE_TOOLS_SCHEMA.json'
BASE = V/'m4_region_task_global_first_frame_001/install/PRODUCT_RUN_BINDING.json'
BASE_GIT = '7e096daf3bb24596905f76abefa5e07a96a9f5d1'
FIXTURES = {
    'main': {
        'git':'eeae0719aa49896c84d4f48e97f86585159f6a37',
        'namespace':'m4_yanyite_dual_curved_region_native_001','slot':'QP',
        'source_sha':'977078b4ac86cdaf75cfb15151ca5ddf8c197895ce0bb7fa6691547c428e1d6f',
        'producer_sha':'af7f24a52f584f40eb0d7c3ff9acd9c23f19a530e7a5c818f732c848cf097289',
        'sizes':[2,27312,53276],'wire':('003','004'),'calls':(2,1),'producer':2,
        'selection_count':311,'target':'0135bbc4-c6c7-4003-a402-6f2e0283497d','views':['SCENE'],
    },
    'holdout': {
        'git':'721ed392','namespace':'m1_source_region_task_entry_holdout_001','slot':'QA',
        'source_sha':'f2b7ee3225ee783241f4cde0f0169d08e20183fe6b2a43e90083ff6ce823c451',
        'producer_sha':'0c35451055a41e81ec1bf5e88b41ebe28326ec3f1d01d195a71b8f746794d741',
        'sizes':[11,64,62],'wire':('003',),'calls':(2,),'producer':1,
        'selection_count':4,'target':'Obj_08','views':['SCENE'],
    },
    'rectangle': {
        'git':'c18b7bdc','namespace':'m4_source_region_active_view_001','slot':'B',
        'source_sha':'3328091f66ee12728ae55f4ae389cb46a14176980b98fd25c39755f3813e0ddc',
        'producer_sha':'eb19da6a5ed05e9548c047c82cb14613ff4e8530550295cea635fd6e1dc78ab5',
        'sizes':[28,416,744],'wire':('002','003'),'calls':(1,2),'producer':1,
        'selection_count':2,'target':'N15','views':['TOP','RIGHT'],
    },
}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with Path(path).open('xb') as out:
        out.write((json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)+'\n').encode())


def digest(raw):
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def pin(path):
    p = Path(path).resolve(strict=True)
    return {'path':str(p), **digest(p.read_bytes())}


def committed(path, commit):
    return subprocess.check_output(['git','show',commit+':'+path.relative_to(REPO).as_posix()],cwd=REPO)


def truth_index(name, item, original):
    if name=='main':
        registered = V/item['namespace']/'RESULT.json'
        require(registered.read_bytes()==committed(registered,item['git']), 'registered_Yanyite_result_differs_from_git')
        result = read(registered)
        index = original/'sealed/RAW_INDEX.json'
        archive = original/'sealed/ORIGINAL_RUNTIME.zip'
        value = read(index)
        expected = result['original_local_raw_archive']
        require(value['archive']=={k:expected[k] for k in ('bytes','sha256')}
                and value['sealed_unmodified_raw_members']==expected['member_count']
                and value['freeze_sha256']==result['freeze_sha256'],'Yanyite_local_archive_not_bound_to_registered_result')
        return index,archive,'runtime/',value['members'],value['archive'],[pin(registered)]
    index = V/item['namespace']/('RAW_INDEX.json' if name=='holdout' else 'RUNTIME_INDEX.json')
    require(index.read_bytes()==committed(index,item['git']),'committed_archive_index_changed/'+name)
    value = read(index)
    archive = Path(value['archive']['path'])
    if name=='holdout':
        require(archive.read_bytes()==committed(index.parent/'ORIGINAL_RUNTIME.zip',item['git']),
                'holdout_original_archive_git_bytes_changed')
        prefix, members = 'runtime/',value['members']
    else:
        prefix = ''
        members = {row['path']:{k:row[k] for k in ('bytes','sha256')} for row in value['files']}
    return index,archive,prefix,members,{k:value['archive'][k] for k in ('bytes','sha256')},[]


def native_capture(slot, key, resources, take):
    folder = slot/'native/WIRE'/key
    tx,rx = (take(folder/name) for name in ('REQUEST.bin','RESPONSE.bin'))
    request,reply = json.loads(tx),json.loads(rx)
    expression = re.search(r'_request = _json.loads\((.+)\)\n',request['params']['code'])
    require(expression is not None,'original_native_transport_request_not_decodable')
    sent = json.loads(ast.literal_eval(expression[1]))
    lines = [line for line in reply['result']['result'].splitlines() if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
    require(reply['status']=='success' and len(lines)==1,'original_native_transport_failed')
    packet = json.loads(lines[0].split(':',1)[1])
    current = packet['result']
    require(packet['id']==sent['id'] and sent['command']=='capture' and not sent['params']
            and current['schema']=='human-eye-scene-delta-v1' and len(current['resources'])==resources,
            'original_full_or_incremental_complete_capture_changed/'+key)
    return current,{'wire':key,'TX':digest(tx),'RX':digest(rx),'resource_count':resources}


def verify_geometry(current, terminal):
    rows = {row['name']:row for row in terminal['objects']}
    require(len(current['meshes'])==len(rows) and {m['name'] for m in current['meshes']}==rows.keys(),
            'replay_capture_current_evaluated_roster_mismatch')
    units = terminal['source']['scale_length']
    for mesh in current['meshes']:
        original = rows[mesh['name']]
        matrix = original['matrix_world']
        # Blender stores world readback in float32. The native transport applies
        # the same saved local vertices and world matrix in binary64.
        world = [[(sum(matrix[i][j]*p[j] for j in range(3))+matrix[i][3])*units for i in range(3)]
                 for p in original['evaluated']['vertices']]
        require(mesh['object_id']==original['object_id']
                and current['host_identity']['object_instances'][mesh['object_id']]==original['instance_id']
                and mesh['vertices']==world and mesh['faces']==original['evaluated']['triangles'],
                'replay_capture_current_ordered_geometry_changed/'+mesh['name'])


def sealed_inputs(name):
    item = FIXTURES[name]
    original = Path('D:/')/('he_'+item['namespace'])
    slot = original/'slots'/item['slot']
    index,archive,prefix,members,expected,pins = truth_index(name,item,original)
    arch = pin(archive)
    require({k:arch[k] for k in expected}==expected,'original_archive_digest_mismatch/'+name)
    pins.extend([pin(index),arch])

    def take(path):
        path = Path(path).resolve(strict=True)
        require(path.is_relative_to(slot.resolve()),'unexpected_source_outside_fixed_original_slot')
        key = prefix+path.relative_to(original.resolve()).as_posix()
        raw = path.read_bytes()
        identity = digest(raw)
        require(members[key]==identity and zipfile.read(key)==raw,'original_file_differs_from_archive/'+key)
        pins.append({'path':str(path),**identity})
        return raw

    with ZipFile(archive) as zipfile:
        terminal_raw = take(slot/'TERMINAL_SOURCE.json')
        terminal = json.loads(terminal_raw)
        rows = terminal['objects']
        sizes = [len(rows),sum(len(row['evaluated']['vertices']) for row in rows),
                 sum(len(row['evaluated']['triangles']) for row in rows)]
        require(sizes==item['sizes'] and digest(terminal_raw)['sha256']==item['source_sha'],
                'original_terminal_hash_or_size_changed/'+name)
        result_raw = take(slot/'SLOT_RESULT.json')
        result = json.loads(result_raw)
        pub = json.loads(take(slot/'SLOT_PUBLICATION.json'))
        require(result['closure_verification']['passed'] and result['independent_before_after']['passed']
                and pub['result_sha256']==digest(result_raw)['sha256'],'original_close_not_independently_verified/'+name)
        deltas,transport = [],[]
        for i,key in enumerate(item['wire']):
            capture, record = native_capture(slot,key,sizes[0] if i==0 else 0,take)
            deltas.append(capture)
            transport.append(record)
        if len(deltas)==1:
            # QA's later actual delta is a selected-object query. For warm
            # transport use the identical complete capture with its already
            # resident resources omitted, not a different selection.
            deltas.append({**deltas[0],'resources':[]})
            transport.append({'wire':None,'derived_same_complete_capture_from':item['wire'][0],'resource_count':0})
        require(deltas[0]['capture']==deltas[1]['capture']
                and deltas[0]['live_resources']==deltas[1]['live_resources'],'warm_capture_changed/'+name)
        captured = deltas[0]['capture']
        calls,responses = [],[]
        for i in item['calls']:
            folder = slot/'product_calls'/f'call_{i:03d}'
            calls.append(json.loads(take(folder/'REQUEST.json')))
            responses.append(json.loads(take(folder/'RESPONSE.json')))
        prod = take(slot/'product_full'/f"call_{item['producer']:03d}"/'SERVICE_RESULT.json')
        producer = json.loads(prod)
        region = calls[0]['params']['arguments']['query']['region']
        require(digest(prod)['sha256']==item['producer_sha']
                and all(c['params']['name']=='human_eye_scene_observe' for c in calls)
                and calls[0]['params']['arguments']['include_image'] is True
                and region['object']['name']==item['target']
                and len(region['source_triangle_indices'])==item['selection_count']
                and producer['region_ref']['source_triangle_indices']==region['source_triangle_indices']
                and producer['binding']['capture_state']==captured['capture_state']
                and producer['binding']['scene_revision']==captured['revision'],'original_req_selection_and_producer_unbound/'+name)
        if name=='main':
            lower = json.loads(take(slot/'product_full/call_001/SERVICE_RESULT.json'))
            require(calls[1]['params']['arguments']['include_image'] is False and len(lower['region_ref']['source_triangle_indices'])==331
                    and lower['binding']['capture_state']==captured['capture_state']
                    and lower['binding']['scene_revision']==captured['revision'],'main_lower_noimage_compatibility_not_same_capture')
        elif name=='rectangle':
            require(calls[1]['params']==calls[0]['params'],'rectangle_warm_request_different_from_original_query')
        frames = []
        for frame in producer.get('constructed_frames',producer['frames']):
            png = digest(take(Path(frame['image_path'])))
            arrays = digest(take(Path(frame['arrays_path'])))
            require(png['sha256']==frame['image_sha256'] and arrays['sha256']==frame['arrays_sha256'],
                    'original_frame_sidecars_hash_changed/'+name)
            frames.append({'view_name':frame['view_name'],'png':png,'arrays':arrays})
        require([row['view_name'] for row in frames]==item['views'],'original_raster_roster_changed/'+name)
    return {'name':name,'source_dimensions':sizes,'original_slot':str(slot),'terminal':terminal,'producer':producer,
            'frames':frames,'deltas':deltas,'transport':transport,'calls':calls,'responses':responses,
            'source_pins':sorted(pins,key=lambda value:value['path'])}
