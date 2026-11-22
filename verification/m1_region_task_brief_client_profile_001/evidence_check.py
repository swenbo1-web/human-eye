"""Check historical wire bindings and the isolated profile's discovery outputs."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
ROOT = V.parent
HISTORICAL = V / 'perf050_dense_micro_surface_holdout_recovery_001'
ORIGINAL = Path('D:/he_perf050_dense_micro_surface_holdout_recovery_001')
INSTALL = V / 'm4_source_region_blocker_frame_list_001/install'
HISTORY_COMMIT = 'f56108e537a0664c07a0e9cb2f88186f30ec604c'
ARCHIVE_SHA = 'd260b4854c38cc3e3e23808027442be34903bf88f0f2a4679033254793159c93'
FULL_BYTES = {'P2': 335181, 'P3': 335179}
BRIEF_BYTES = 7521
TOOL = 'human_eye_scene_observe'
REGION = {'area_min_m2': .00341796875, 'area_max_m2': .00439453125, 'normal_z_min': 1}
RULE = {'if': {'required': ['query'], 'properties': {'query': {'type': 'object',
         'required': ['mode', 'region_task'], 'properties': {'mode': {'const': 'active_observation'}}}}},
        'then': {'properties': {'response_detail': {'const': 'brief'}}}}


def require(check, reason):
    if not check:
        raise ValueError(reason)


def pin(value):
    return {'bytes': len(value), 'sha256': sha256(value).hexdigest()}


def json_read(path):
    return json.loads(path.read_bytes())


def unwrap(value):
    if 'result' in value:
        return value['result']
    return value


def schema_applies(value, schema):
    """Evaluate the three keywords used by this single appended rule."""
    if 'const' in schema:
        return type(value) is type(schema['const']) and value == schema['const']
    if schema.get('type') == 'object' and type(value) is not dict:
        return False
    if type(value) is dict:
        return set(schema.get('required', [])) <= value.keys() and all(
            key not in value or schema_applies(value[key], sub_schema)
            for key, sub_schema in schema.get('properties', {}).items())
    return True


def check_catalogue(catalogue_a, catalogue_b):
    """Compare actual declared lists, and test scope, full, brief and absence."""
    require([tool['name'] for tool in catalogue_a] == [tool['name'] for tool in catalogue_b]
            and len({tool['name'] for tool in catalogue_a}) == len(catalogue_a), 'tool_roster_changed')
    expected = json_read(INSTALL / 'PRODUCT_SCHEMA.json')
    a, = [tool for tool in catalogue_a if tool['name'] == TOOL]
    require(a == expected, 'A_tool_does_not_match_installed_shape')
    amended = deepcopy(catalogue_a)
    observe, = [tool for tool in amended if tool['name'] == TOOL]
    observe['inputSchema']['allOf'].append(RULE)
    require(amended == catalogue_b, 'B_has_a_delta_beyond_the_one_local_conditional_rule')
    b, = [tool for tool in catalogue_b if tool['name'] == TOOL]
    rule = b['inputSchema']['allOf'][-1]
    active = {'mode': 'active_observation', 'region_task': REGION}
    plain = {'mode': 'active_observation'}
    source_region = {'mode': 'source_region', 'region': {'object': {'name': 'S034'},
                     'source_triangle_indices': [0,1]}, 'reference': {'name': 'M4_Far_00'},
                     'requested_facts': ['surface_proximity']}
    matrix = [
        ('active_omitted', {'query': active}, True, True),
        ('active_brief', {'query': active, 'response_detail': 'brief'}, True, True),
        ('active_full', {'query': active, 'response_detail': 'full'}, True, False),
        ('active_full_no_image', {'query': active, 'include_image': False, 'response_detail': 'full'}, True, False),
        ('active_full_with_task_query', {'query': {**active, 'task_query': {'objects': [{'name':'S034'},
             {'name':'M4_Far_00'}], 'requested_facts':['surface_proximity']}}, 'response_detail': 'full'}, True, False),
        ('active_plain_full', {'query': plain, 'response_detail': 'full'}, False, True),
        ('active_target_full', {'query': {**plain, 'objects': [{'name': 'M4_Far_00'}]},
             'response_detail': 'full'}, False, True),
        ('source_region_full', {'query': source_region, 'include_image': False, 'response_detail': 'full'}, False, True),
        ('scan_full', {'query': {'mode': 'surface_scan', 'threshold_m': .04}, 'response_detail': 'full'}, False, True),
        ('directory_full', {'query': {'mode': 'directory'}, 'include_image': False, 'response_detail': 'full'}, False, True),
        ('legacy_full_without_query', {'response_detail': 'full'}, False, True),
        ('mode_missing', {'query': {'region_task': REGION}, 'response_detail': 'full'}, False, True),
        ('region_task_null', {'query': {**active, 'region_task': None}, 'response_detail': 'full'}, True, False),
        ('response_detail_null', {'query': active, 'response_detail': None}, True, False),
        ('query_array', {'query': [active], 'response_detail': 'full'}, False, True),
    ]
    cases = []
    for label, args, is_region_task, passes_trial_clause in matrix:
        applies = schema_applies(args, rule['if'])
        passes = not applies or schema_applies(args, rule['then'])
        require((applies, passes) == (is_region_task, passes_trial_clause), 'conditional_truth_table/' + label)
        cases.append({'case':label, 'applies':applies, 'new_clause_allows':passes})
    return {'passed':True, 'one_appended_observe_clause': True, 'tool_names':[item['name'] for item in catalogue_a],
            'matrix_scope':'new clause only; baseline validity/dispatch enforced separately', 'clause_cases':cases}


def archived_cases():
    """Bind original bytes at the archived MCP and Owner boundaries to actual producers."""
    index = HISTORICAL / 'RAW_INDEX.json'
    index_bytes = index.read_bytes()
    original_index = subprocess.check_output(['git','-C',str(ROOT),'show',
        f'{HISTORY_COMMIT}:{index.relative_to(ROOT).as_posix()}'])
    require(index_bytes == original_index, 'archive_index_drift')
    manifest = json.loads(index_bytes)
    archive = HISTORICAL / manifest['archive']['name']
    require(pin(archive.read_bytes()) == {'bytes':manifest['archive']['bytes'], 'sha256':ARCHIVE_SHA}
            and manifest['archive']['sha256'] == ARCHIVE_SHA, 'archive_bytes_changed')
    cases = {}
    with ZipFile(archive) as bundle:
        require(len(bundle.namelist()) == manifest['member_count']==2013, 'archive_roster_changed')
        for slot, expected in FULL_BYTES.items():
            prefix = f'runtime/slots/{slot}/'
            used = {}

            def source(relative):
                name = prefix + relative
                raw = bundle.read(name)
                require(pin(raw) == manifest['members'][name], 'archive_member_changed/' + name)
                path = ORIGINAL / name.removeprefix('runtime/')
                require(path.read_bytes() == raw, 'live_archive_file_differed/' + relative)
                used[name] = pin(raw)
                return raw

            owner = json.loads(source('owner/tool_01/REQUEST.json'))
            request = json.loads(source('product_calls/call_001/REQUEST.json'))
            receipt = json.loads(source('product_calls/call_001/RECEIPT.json'))
            rpc_prefix = f'mcp/rpc_{receipt["index"]:02d}/'
            tx, rx = (source(rpc_prefix + link) for link in ('TX.bin', 'RX.bin'))
            require(json.loads(tx) == request and len(tx) == receipt['TX_bytes']
                    and pin(rx) == {'bytes':receipt['RX_bytes'], 'sha256':receipt['RX_sha256']},
                    'historical_mcp_rpc_binding_changed/' + slot)
            owner_packet = json.loads(source('owner/tool_01/RESPONSE.json'))
            full = unwrap(json.loads(rx))
            require(full == unwrap(owner_packet) == unwrap(json.loads(source('product_calls/call_001/RESPONSE.json'))),
                    'historical_outer_inner_full_changed/' + slot)
            require(owner['params']['name'] == request['params']['name'] == TOOL
                    and owner['params']['arguments'] == request['params']['arguments'] == {
                    'include_image':True, 'query':{'mode':'active_observation','region_task':REGION},
                    'response_detail':'full'}, 'historical_query_changed/' + slot)
            body = full['content'][0]['text'].encode()
            require(len(body) == expected, 'historical_full_bytes_changed/' + slot)
            producer_name = 'product_full/call_001/SERVICE_RESULT.json'
            producer_bytes = source(producer_name)
            archive_after, = [json.loads(line) for line in source('product_calls/call_001/ARCHIVE_AFTER.bin').splitlines()]
            require(archive_after['sha256'] == pin(producer_bytes)['sha256'], 'historical_producer_wire_pin_changed/' + slot)
            producer = json.loads(producer_bytes)
            require(producer['binding']['runtime_source_sha256'] == '65bd1ec8009f8024e85ef1cd30c1229957cceb1c1766c8e5b62f2ef2489ce48c'
                    and producer['binding']['capture_scope'] == 'complete_scene_meshes'
                    and producer['frames'] == producer['constructed_frames'] and len(producer['frames']) == 3,
                    'historical_producer_contract_changed/' + slot)
            for frame, block in zip(producer['frames'], full['content'][1:], strict=True):
                archive_relative = Path(frame['image_path']).relative_to(ORIGINAL/'slots'/slot).as_posix()
                data = source(archive_relative)
                require(block['type'] == 'image' and block['mimeType'] == 'image/png'
                        and base64.b64decode(block['data'], validate=True) == data
                        and pin(data)['sha256'] == frame['image_sha256'] and len(data) == frame['PNG_bytes'],
                        'historical_original_png_mismatch/' + slot)
            cases[slot] = {'arguments':request['params']['arguments'],'producer':producer,'full':full,
                           'provenance':{'archive':str(archive.resolve()),'archive_sha256':ARCHIVE_SHA,
                                         'git_commit':HISTORY_COMMIT,'original_members':used}}
    return cases


def verify_brief(result, original):
    full, producer = original['full'], original['producer']
    require(result['isError'] is False and result['content'][0]['type'] == 'text'
            and result['content'][1:] == full['content'][1:], 'brief_native_PNG_sequence_changed')
    raw = result['content'][0]['text'].encode()
    packet = json.loads(raw)
    require(len(raw) == BRIEF_BYTES, 'known_region_task_brief_bytes_changed')
    brief = run_path(str(V/'m4_dense_region_brief_001/checks/brief_schema.py'))
    decoded = brief['decode_body'](packet, len(result['content']))
    task = producer['facts']['region_task']
    source_rows = task['rows']
    rows = decoded['region_task']['rows']
    require(len(rows) == 3 and {row['object_name'] for row in rows} == {'S021','S034','S055'}
            and task['conditions'] == decoded['region_task']['conditions'] == REGION
            and task['summary'] == decoded['region_task']['summary'], 'brief_region_task_changed')
    objects = brief['records'](decoded['objects'], brief['OBJECTS'])
    published_binding = {key:value for key,value in producer['binding'].items()
                         if key not in {'objects','camera_specification','schema','camera_policy'}}
    require(objects == producer['binding']['objects'] and packet['binding'] == published_binding
            and packet['read_only'] is True and packet['execution_authority'] is False, 'brief_global_source_changed')
    scopes = {scope['scope_id']:scope for scope in producer['scopes']}
    table = brief['records'](packet['frames'], brief['FRAMES'])
    scope_rows = brief['records'](decoded['scopes'], brief['SCOPES'])
    observed = {}
    for frame, row in zip(producer['frames'], table, strict=True):
        scope = scope_rows[row['scope_index']]
        source = scopes[scope['scope_id']]['binding']
        block_index = row['native_content_block_index']
        require(scope['scope_id'] == frame['scope_id'] and scope['binding_sha256'] == source['binding_sha256']
                == frame['host_binding_sha256'] and scope['camera_identity'] == source['camera_identity']
                and all(row[key] == frame[key] for key in ('view_name','frame_identity','image_ref','image_sha256'))
                and block_index is not None, 'brief_scope_or_frame_identity_changed')
        original_png = base64.b64decode(result['content'][block_index]['data'],validate=True)
        require(pin(original_png)['sha256'] == frame['image_sha256'], 'brief_png_attached_to_wrong_scope')
        observed[row['frame_identity']] = {'scope_id':scope['scope_id'],'view':row['view_name'], **pin(original_png)}
    scene = [row for row in observed.values() if row['view'] == 'SCENE']
    require(len(scene) == 2 and len({row['scope_id'] for row in scene}) == 2
            and len({row['sha256'] for row in scene}) == 2, 'global_and_local_SCENE_not_distinct')
    pixel_rows = brief['records'](decoded['witness_pixels'], brief['WITNESSES_V1'])
    for old, new in zip(source_rows, rows, strict=True):
        require(all(old[key] == new[key] for key in old.keys() - {'complete_witness'}),
                'brief_current_region_facts_changed/' + old['object_name'])
        witness = new['complete_witness']
        if witness is None:
            require(old['complete_witness'] is None and old['object_name'] == 'S034' and
                   old['reason'] == 'positive_area_occlusion_all_front_views', 'brief_unknown_reason_changed')
            continue
        require({key:value for key,value in witness.items() if key != 'native_content_block_index'}
                == old['complete_witness'], 'brief_complete_witness_changed/' + old['object_name'])
        w, = [row for row in pixel_rows if row['roi_id'] == old['roi_id']]
        current, = [obs for obs in scopes[w['scope_id']]['facts']['observations']
                    if obs['frame_identity'] == w['frame_identity']]
        upstream = current['pixel_rows'][witness['pixel_row_index']]
        require(all(w[key] == upstream[key] for key in (*brief['PIXELS'],*brief['LOCATIONS'])),
                'brief_current_pixel_witness_changed/' + old['object_name'])
    blocker = packet['blocker_evidence']
    blocker_rows = brief['records'](blocker,('region_index','view_name','blocker_object_index','source_triangle_index'))
    require(scope_rows[blocker['scope_index']]['scope_id']=='global' and len(blocker_rows)==6,
            'brief_blocker_scope_or_count_changed')
    for item, source in zip(blocker_rows, task['blocker_evidence']['rows'], strict=True):
        region, obj = rows[item['region_index']], objects[item['blocker_object_index']]
        require(region['object_name'] == 'S034' and region['roi_id'] == source['roi_id']
                and obj['object_name'] == 'M4_Far_00'
                and obj['host_id'] == source['blocker_host_id'] and obj['instance_id'] == source['blocker_instance_id']
                and item['view_name'] == source['view_name'] and item['source_triangle_index'] == source['source_triangle_index'],
                'brief_original_named_blocker_changed')
    unknown = next(row['reason'] for row in rows if row['object_name']=='S034')
    return {'brief':pin(raw),'frames':observed,'complete_witnesses':2,'unknown':unknown,
            'named_blockers':blocker_rows,'CLI':brief['cli_stages'](result)}


def check_brief_negative_controls(result, original):
    """Keep text length constant while corrupting one semantic binding at a time."""
    controls = (
        ('swapped_scope', lambda val:val['frames']['rows'][1].__setitem__(0,0),
         'v2_frame_scope_view_identity'),
        ('swapped_PNG_block_mapping', lambda val:(val['frames']['rows'][0].__setitem__(5,2),
                                                 val['frames']['rows'][1].__setitem__(5,1)),
         'brief_png_attached_to_wrong_scope'),
        ('same_view_frame_identity_alias', lambda val:val['frames']['rows'][1].__setitem__(2,val['frames']['rows'][0][2]),
         'v2_frame_scope_count_or_selected_coverage'),
        ('changed_source_binding', lambda val:val['binding'].__setitem__('document_epoch',
                                                     '0'*len(val['binding']['document_epoch'])),
         'brief_global_source_changed'),
        ('changed_named_blocker', lambda val:val['blocker_evidence']['rows'][2].__setitem__(3,512),
         'brief_original_named_blocker_changed'),
        ('changed_unknown_reason', lambda val:val['region_task']['rows'][2].__setitem__(
                                                     -2,'positive_area_occlusion_all_front_viewS'),
         'brief_current_region_facts_changed/S034'),
    )
    proof = {}
    for label, alter, expected in controls:
        changed = deepcopy(result)
        block = changed['content'][0]
        packet = json.loads(block['text'])
        alter(packet)
        updated = json.dumps(packet, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        require(len(updated.encode()) == len(block['text'].encode()) and updated != block['text'],
                'control_must_change_one_fact_at_same_text_length/' + label)
        block['text'] = updated
        try:
            verify_brief(changed, original)
        except ValueError as error:
            require(str(error) == expected, 'control_rejected_at_unexpected_check/' + label)
            proof[label] = {'correctly_refused':True,'reason':expected,'body_bytes':len(updated.encode())}
        else:
            raise ValueError('scope_or_source_corruption_accepted/' + label)
    return proof


def check_products(actual, cases=None, *, exact_full=True):
    """Check installed stdio results keyed by historical slot and replay case."""
    cases = archived_cases() if cases is None else cases
    proof = {}
    for slot, original in cases.items():
        incoming = actual[slot]
        full, brief, omitted = (unwrap(incoming['discover_'+form]) for form in ('full','brief','omitted'))
        expected = original['full']
        require(full['isError'] is False and full['content'][1:] == expected['content'][1:]
                and json.loads(full['content'][0]['text']) == json.loads(expected['content'][0]['text']),
                'stock_full_result_differed/' + slot)
        if exact_full:
            require(full==expected, 'stock_full_original_wire_content_not_byte_identical/' + slot)
        require(brief==omitted, 'installed_brief_and_absent_response_detail_differ/' + slot)
        proof[slot] = {'full':pin(full['content'][0]['text'].encode()),'full_content_exact':full==expected,
                       'explicit_and_omitted_brief_equal':True,'provenance':original['provenance'],
                       'retained_evidence':verify_brief(brief,original)}
        if slot == 'P2':
            proof[slot]['same_size_corruption_controls'] = check_brief_negative_controls(brief, original)
    return proof


def golden_reference():
    from contextlib import contextmanager

    @contextmanager
    def installed_path(binding):
        original = sys.path[:]
        sys.path[:0] = [binding['install_root'],binding['dependency_root']]
        try:
            yield
        finally:
            sys.path[:] = original

    binding = json_read(INSTALL/'PRODUCT_RUN_BINDING.json')
    cases = archived_cases()
    actual, costs = {}, {}
    with installed_path(binding):
        from human_eye_plugin.live_spatial_mcp import _tool_result
        material = Path(sys.modules[_tool_result.__module__].__file__)
        expected_source = next(row['sha256'] for row in binding['source_manifest']
                               if row['path']=='human_eye_plugin/live_spatial_mcp.py')
        require(material.is_relative_to(binding['install_root']) and pin(material.read_bytes())['sha256']==expected_source,
                'reference_not_using_the_pinned_installed_serializer')
        for slot, data in cases.items():
            actual[slot], costs[slot] = {}, {}
            for form, detail in (('full','full'),('brief','brief'),('omitted',None)):
                mark = time.perf_counter_ns()
                audit = {}
                result = _tool_result(data['producer'],is_error=False,response_detail=detail,active_delivery_audit=audit)
                costs[slot][form] = {'wall_ns':time.perf_counter_ns()-mark,**{key:audit[key] for key in
                    ('elapsed_ns','public_text_bytes','PNG_bytes','base64_chars')}}
                actual[slot]['discover_'+form] = result
    return {'passed':True,'scope':'installed serializer on sealed historical producers, separate from new stdio qualification',
            'actual_Blender_starts':0,'actual_models':0,'actual_rasters':0,
            'serializer':{'path':str(material),**pin(material.read_bytes())},'checker':pin(Path(__file__).read_bytes()),
            'results':check_products(actual,cases,exact_full=False),'serializer_costs':costs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--golden',action='store_true')
    parser.add_argument('--catalogue-a',type=Path)
    parser.add_argument('--catalogue-b',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    output = {}
    if args.golden:
        output['golden_reference'] = golden_reference()
    if args.catalogue_a and args.catalogue_b:
        def list_from(path):
            return unwrap(json_read(path))['tools']
        output['catalogue'] = check_catalogue(list_from(args.catalogue_a),list_from(args.catalogue_b))
    require(output, 'golden_or_both_actual_catalogues_required')
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(output,stream,ensure_ascii=False,allow_nan=False,indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
