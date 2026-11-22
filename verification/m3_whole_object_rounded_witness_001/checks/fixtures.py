"""Sealed geometry/capture sources for the rounded-witness checks."""

from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
EXTERNAL = Path('D:/he_m3_whole_object_rounded_witness_001')
INPUTS = {
    'linear':{
        'directory':'m4_cross_scale_live_task_formal_001','slot':'P1',
        'runtime':'he_m4_cross_scale_live_task_formal_001','raw_index':'RUNTIME_INDEX.json',
        'archive_sha256':'38be66d67b301524de5594acab12158342da7c31e2aa75629109e2fe4ff8a89d',
        'terminal_sha256':'aae8ad86e3c79032346853360d212c4614c71d20cc50b7b1375786860166e927',
        'binding':'m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'},
    'tree':{
        'directory':'m4_cross_scale_assembly_transfer_001','slot':'P1',
        'runtime':'he_m4_cross_scale_assembly_transfer_001','raw_index':'RUNTIME_INDEX.json',
        'archive_sha256':'bf7be101396593b151411e567b05af32e0e0754ac18dc733a6a10191fcae3627',
        'terminal_sha256':'d0d2294f5e5fe006d2f3f23deaf34290dba696b39424585b7cd5e4494d8ffa90',
        'binding':'m4_cross_scale_cold_frustum_001/install/PRODUCT_RUN_BINDING.json'},
    'success':{
        'directory':'m3_whole_object_witness_triangle_consumption_001','slot':'B1',
        'runtime':'he_m3_whole_object_witness_triangle_consumption_001','raw_index':'RAW_INDEX.json',
        'archive_sha256':'ecf08050ef4cc8c8fcd13cc6ec6ea8715ea77c5a4ba74476a7f279ac51e1dbb0',
        'binding':'m3_whole_object_witness_triangle_001/install/PRODUCT_RUN_BINDING.json'},
}
CASES = {
    'linear_m01_m03': ('linear',('M01','M03')),
    'linear_m03_m01': ('linear',('M03','M01')),
    'linear_m16_m20': ('linear',('M16','M20')),
    'linear_m20_m16': ('linear',('M20','M16')),
    'tree_n02_n03': ('tree',('N02','N03')),
    'success_m16_m19': ('success',('M16','M19')),
    'success_m16_m14': ('success',('M16','M14')),
}


def require(ok,reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path':path.as_posix(),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def digest(value):
    return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def source_family(label):
    if label in INPUTS:
        return label
    return CASES[label][0]


@lru_cache(maxsize=None)
def store(family):
    entry = INPUTS[family]
    space = V/entry['directory']
    runtime = Path('D:/')/entry['runtime']
    slot = runtime/'slots'/entry['slot']
    index_path = space/entry['raw_index']
    index = read(index_path)
    portable = entry['raw_index']=='RAW_INDEX.json'
    archive = space/index['archive']['name'] if portable else Path(index['archive']['path'])
    original = pin(archive)
    require(original['sha256']==index['archive']['sha256']==entry['archive_sha256']
            and original['bytes']==index['archive']['bytes'],'retained_archive_sha_mismatch/'+family)
    records = index['members'] if portable else {row['path']:row for row in index['files']}
    return {'slot':slot,'runtime':runtime,'archive':archive,'index_path':index_path,'records':records,
            'prefix':'runtime/' if portable else '', 'binding_path':V/entry['binding'],
            'original':original,'terminal_sha256':entry.get('terminal_sha256')}


def checked(family,paths):
    origin = store(family)
    records = origin['records']
    receipts = {}
    originals = {}
    with ZipFile(origin['archive']) as archive:
        for path in paths:
            named = origin['prefix']+path.relative_to(origin['runtime']).as_posix()
            raw = path.read_bytes()
            observed = pin(path)
            record = records[named]
            require(raw==archive.read(named) and observed['sha256']==record['sha256']
                    and observed['bytes']==record['bytes'],'retained_exact_artifact_changed/'+named)
            originals[path] = raw
            receipts[named] = observed
    return originals,receipts


@lru_cache(maxsize=None)
def source_material(family):
    origin = store(family)
    slot = origin['slot']
    audit_module = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    captures,commands = audit_module['decode_captures'](slot,read(origin['binding_path']),audit_module['Audit']())
    selected = [row for row in commands if row['command']['command'] in ('capture','capture_scene','capture_task')]
    require(len(selected)==len(captures) and captures,'actual_closed_native_capture_roster_detached/'+family)
    wires = slot/'native/WIRE'
    raw_pins = [path for folder in sorted(wires.glob('[0-9]*')) for path in
                (folder/'REQUEST.bin',folder/'RESPONSE.bin')]
    status = slot/'SLOT_RESULT.json'
    publication = slot/'SLOT_PUBLICATION.json'
    previous,last = (slot/path for path in ('initial_capture/TERMINAL_SOURCE.json','TERMINAL_SOURCE.json'))
    saved,receipts = checked(family,[status,publication,previous,last,slot/'native/input.blend',*raw_pins])
    initial,terminal = (json.loads(saved[path]) for path in (previous,last))
    prove,pub = (json.loads(saved[path]) for path in (status,publication))
    require(prove['closure_verification']['passed'] and prove['status']==pub['status']=='completed'
            and pub['result_sha256']==pin(status)['sha256']
            and (origin['terminal_sha256'] is None or pin(last)['sha256']==origin['terminal_sha256'])
            and all(initial[field]==terminal[field] for field in ('source','objects','source_face_offsets',
                'display_object_mask','display_scope','layer_collections','scene_cameras')),
            'same_closed_asset_before_after_source_not_proven/'+family)
    require(sha256(saved[slot/'native/input.blend']).hexdigest()==terminal['source']['asset_sha256']==prove['asset_sha256'],
            'archived_native_blend_hash_and_current_source_changed/'+family)
    objects = {obj['name']:obj for obj in terminal['objects']}
    normalized = []
    for command,capture in zip(selected,captures,strict=True):
        for mesh in capture['meshes']:
            source = objects[mesh['name']]
            stored = source['evaluated']
            require(mesh['object_id']==source['object_id']
                    and capture['host_identity']['object_instances'][mesh['object_id']]==source['instance_id']
                    and mesh['vertices']==stored['vertices_world_m'] and mesh['faces']==stored['triangles'],
                    'closed_current_capture_does_not_match_independent_ordered_arrays/'+mesh['name'])
        normalized.append((command,capture))
    return {'source':terminal,'captures':normalized,
            'source_pins':{'archive':origin['original'],'index':pin(origin['index_path']),
                           'installed_host_binding':pin(origin['binding_path']),'members':receipts}}


def terminal(label):
    return source_material(source_family(label))['source']


def full_capture(label):
    for _,capture in source_material(source_family(label))['captures']:
        if capture['host_identity']['capture_scope']=='complete_scene_meshes':
            return deepcopy(capture)
    raise ValueError('registered_case_has_only_original_selected_capture')


def build_selected_capture(complete_capture, ordered_names):
    origin = complete_capture['host_identity']
    require(origin['capture_scope']=='complete_scene_meshes' and len(ordered_names)==len(set(ordered_names))==2
            and complete_capture['unit']=='m' and complete_capture['coordinate_frame']=='world',
            'exact_complete_capture_and_two_distinct_ordered_names_required')
    meshes = {row['name']:row for row in complete_capture['meshes']}
    require(len(meshes)==len(complete_capture['meshes']) and set(ordered_names)<=meshes.keys(),
            'archived_source_unique_roster_not_current')
    rows = sorted((deepcopy(meshes[name]) for name in ordered_names),key=lambda row:row['object_id'])
    for i,row in enumerate(rows,1):
        row['mark_label'] = f'#B{i:04d}'
    ids = {row['object_id'] for row in rows}
    selectors = [{'name':name} for name in ordered_names]
    identity = {**deepcopy(origin),'capture_scope':'selected_objects',
                'object_instances':{key:value for key,value in origin['object_instances'].items() if key in ids}}
    require(identity['object_instances'].keys()==ids,'each_derived_selected_source_requires_actual_current_instance')
    result = {'unit':'m','coordinate_frame':'world','source':complete_capture['source'],'meshes':rows,
              'capture_scope':'selected_objects','host_identity':identity,
              'task_selection':{'selectors':selectors,'bindings':[{'object_id':meshes[name]['object_id'],'name':name}
                                for name in ordered_names],'pair_reason':None,'candidate_count':len(meshes)}}
    result['revision'] = 'blender:'+digest({'scene':result,'scale_length':1.0})
    if complete_capture.get('display_snapshot') is not None:
        sidecar = deepcopy(complete_capture['display_snapshot'])
        sidecar.pop('sha256')
        sidecar['objects'] = [row for row in sidecar['objects'] if row['host_id'] in ids]
        sidecar['sha256'] = digest(sidecar)
        result['display_snapshot'] = sidecar
    result['capture_state'] = {**deepcopy(complete_capture['capture_state']),'selection_key':digest(['task',selectors])}
    return result


@lru_cache(maxsize=None)
def fixture(label):
    family,names = CASES[label]
    material = source_material(family)
    result = {'label':label,'family':family,'names':names,'source':material['source'],
              'source_pins':deepcopy(material['source_pins']),'historical_reply':None}
    query = {'mode':'task','objects':[{'name':name} for name in names],'requested_facts':['surface_proximity']}
    if family != 'success':
        result.update(capture=build_selected_capture(full_capture(label),names),
                      request={'jsonrpc':'2.0','id':label,'method':'tools/call','params':{'name':'human_eye_scene_observe',
                                'arguments':{'include_image':False,'query':query,'response_detail':'full'}}},
                      origin='derived_selected_scope_from_actual_sealed_full_capture')
        return result
    wanted = {'selectors':query['objects']}
    item,capture = next((command,capture) for command,capture in material['captures']
                        if command['command']['command']=='capture_task' and command['command']['params']==wanted)
    origin = store(family)
    slot = origin['slot']
    ordinal = item['wire_sequence']-1
    call = slot/'product_calls'/f'call_{ordinal:03d}'
    owner = slot/'owner'/f'tool_{ordinal:02d}'
    files = [call/f for f in ('REQUEST.json','RESPONSE.json','RECEIPT.json')]
    _,_,receipt = (read(file) for file in files)
    rpc = slot/'mcp'/f"rpc_{receipt['index']:02d}"
    raw,pins = checked(family,[*files,owner/'REQUEST.json',owner/'RESPONSE.json',rpc/'TX.bin',rpc/'RX.bin'])
    request,reply = (json.loads(raw[file]) for file in files[:2])
    owner_request = json.loads(raw[owner/'REQUEST.json'])
    require(reply['result']==json.loads(raw[owner/'RESPONSE.json'])['result']
            and request['params']=={key:value for key,value in owner_request['params'].items() if key!='_meta'}
            and json.loads(raw[rpc/'TX.bin'])==request and json.loads(raw[rpc/'RX.bin'])==reply
            and json.loads(reply['result']['content'][0]['text'])['binding']['scene_revision']==capture['revision']
            and request['params']['arguments']=={'query':query,'include_image':False,'response_detail':'full'},
            'actual_previously_successful_original_request_or_witness_reply_changed')
    result['source_pins']['members'].update(pins)
    result.update(capture=deepcopy(capture),request=request,historical_reply=reply,
                  origin='actual_previously_successful_bound_capture_and_original_tool_args')
    return result
