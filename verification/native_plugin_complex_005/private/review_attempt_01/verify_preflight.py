"""Verify existing no-model artifacts only; never launch a runtime or Blender."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'native_plugin_complex_003'
PREVIOUS = HERE.parent/'native_plugin_complex_004'
DIAG = HERE.parent/'scale_diag_001'
READ_NAMES = {'human_eye_scene_observe', 'human_eye_connection_status'}
H_UNKNOWN = {'query_exact_pair_budget_exhausted', 'query_geometry_resource_limit',
    'exact_penetration_depth_not_certified', 'query_geometry_or_measurement_unknown'}
H_BLOCKED = {'geometry_resource_limit', 'reference_pair_geometry_unknown', 'reference_pair_measurement_unknown'}


def require(value, message):
    if value is not True:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate_json_key:'+key)
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite_json:'+value)))


def read(path):
    return decode(Path(path).read_bytes())


def wire(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))+'\n').encode('utf8')


def payload(reply):
    require(type(reply) is dict and 'error' not in reply and type(reply.get('result')) is dict, 'invalid_product_JSONRPC')
    blocks = reply['result'].get('content')
    require(isinstance(blocks, list) and len(blocks) == 1 and blocks[0].get('type') == 'text', 'single_text_zero_image_required')
    value = decode(blocks[0]['text'])
    require(type(value) is dict, 'product_metadata_object_required')
    return value


def identity_matches(actual, expected):
    fields = ('schema_version', 'base_version', 'implementation_revision', 'build_id', 'build_id_basis',
        'source_sha256', 'source_kind', 'distribution_version', 'source_hash_exclusions', 'protocol_version', 'mode')
    require(type(actual) is dict and all(actual.get(key) == expected.get(key) for key in fields), 'actual_identity_core_mismatch')
    if 'source_files' in actual:
        require(actual['source_files'] == expected['source_files'], 'full_source_members_differ')
    else:
        require(type(actual.get('source_file_count')) is int and actual['source_file_count'] == len(expected['source_files']), 'compact_source_count_differs')
    pin = actual.get('identity_check', {})
    require(pin.get('compatible') is True and pin.get('pins_requested') is True and pin.get('reasons') == []
        and pin.get('expected', {}).get('source_sha256') == expected['source_sha256'], 'actual_source_pin_not_verified')


def normalized(value, task):
    value = value['initial'] if task == 'assembly' and 'initial' in value else value
    return {'unit_scale_m': value.get('unit_scale_m', 1.), 'objects': [
        {key: obj['triangles'] if key == 'faces' and 'faces' not in obj else obj[key]
         for key in ('name', 'vertices_local', 'matrix_world', 'faces')} for obj in value['objects']]}


def lifecycle_reuse():
    def nodes(path):
        module = ast.parse(path.read_text(encoding='utf8'))
        peer = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == 'Peer')
        owner = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == 'Owner')
        close = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == 'close')
        return [ast.dump(node, include_attributes=False) for node in (peer, close)]
    require(nodes(HERE/'actor.py') == nodes(PREVIOUS/'actor.py'), 'reused_Peer_or_Owner_close_has_changed')
    previous = read(PREVIOUS/'WRAPPER_TESTS.json')
    require(previous['passed'] is True and previous['actor_sha256'] == sha(PREVIOUS/'actor.py')
        and previous['test_sha256'] == sha(PREVIOUS/'test_actor_lifecycle.py'), 'prior_lifecycle_test_binding_changed')
    tests = read(HERE/'ADAPTER_TESTS.json')
    require(tests['passed'] is True and tests['actor_sha256'] == sha(HERE/'actor.py'), 'new_adapter_tests_not_final_actor')
    if 'driver_sha256' in tests:
        require(tests['driver_sha256'] == sha(HERE/'driver.py'), 'adapter_driver_hash_changed')
    return {'Peer_and_Owner_close_AST_equal_to_tested_004': True,
        'reused_004_wrapper_tests_sha256': sha(PREVIOUS/'WRAPPER_TESTS.json'),
        'new_adapter_tests_sha256': sha(HERE/'ADAPTER_TESTS.json'),
        'scope': '004 lifecycle tests reused by exact AST binding; not reported as newly run on actor005'}


def qualify_h(reply, phase, mode):
    """Recognize only original H contracts, never a generic caught exception."""
    data = payload(reply)
    status = data.get('status')
    if status in {'expired', 'busy'}:
        code = 'live_request_'+status
        require(data.get('code') == code and data.get('reason_codes') == [code]
            and type(data.get('budget_stage')) is str and bool(data['budget_stage'])
            and data.get('budget_scope') == 'service_entry_to_precommit_checkpoints_not_hard_realtime', 'H_unbound_budget_exit')
        for key in ('executed', 'verified', 'execution_verified', 'allow_action', 'host_mutation_started',
                'connector_state_write_attempted', 'execution_authority', 'retry_authorized'):
            require(data.get(key) is False, 'H_budget_exit_is_not_nonmutating:'+key)
        require(data.get('execution_status') == 'not_executed', 'H_budget_execution_status')
        return {'classification': 'original_budget_'+status, 'status': status, 'reason_codes': [code],
            'geometry_measured': False, 'requested_unsigned_task_qualified': False}
    require(reply['result'].get('isError') is False, 'H_unqualified_tool_error')
    if status == 'blocked':
        routing = data.get('routing', {})
        reasons = routing.get('reason_codes')
        require(isinstance(reasons, list) and len(reasons) == 1 and reasons[0] in H_BLOCKED, 'H_unrecognized_block_reason')
        context = decode(routing['context_text'])
        require(routing.get('route') == 'blocked' and routing.get('allow_action') is False
            and context.get('human_eye_status') == 'blocked' and context.get('reason') == reasons[0], 'H_inconsistent_blocked_contract')
        require(data.get('query_result') is None and routing.get('engine_invoked') is False
            and routing.get('measurement_valid') is None, 'H_blocked_result_has_unqualified_measurement')
        budget = routing.get('geometry_work_budget', {})
        if reasons == ['geometry_resource_limit']:
            require(budget.get('within_budget') is False and budget.get('policy') == 'purpose_scoped_conservative_geometry_no_decimation', 'H_resource_block_without_budget')
            maps = {'dense_geometry_work_limit': ('largest_dense_elements', 'dense_elements'),
                'sat_projection_work_limit': ('largest_sat_projection_elements', 'sat_projection_elements'),
                'scene_geometry_work_limit': ('scene_work_elements', 'scene_work_elements')}
            codes = budget.get('reason_codes')
            require(isinstance(codes, list) and bool(codes) and set(codes) <= set(maps), 'H_unrecognized_geometry_budget_code')
            require(all(budget['estimates'][maps[code][0]] > budget['limits'][maps[code][1]] for code in codes), 'H_geometry_budget_reason_not_supported_by_estimate')
        elif reasons == ['reference_pair_geometry_unknown']:
            index = routing.get('spatial_index', {})
            require(budget.get('within_budget') is True and index.get('supported') is False
                and bool(set(index.get('reason_codes', [])) & {'focal_solid_support_unknown', 'scene_solid_support_unknown'}), 'H_geometry_block_without_original_support_evidence')
        return {'classification': 'original_geometry_or_resource_block', 'status': status, 'reason_codes': reasons,
            'geometry_work_budget': budget, 'spatial_index': routing.get('spatial_index'),
            'geometry_measured': False, 'requested_unsigned_task_qualified': False}
    require(status in {'overview', 'observed', 'partial'}, 'H_unrecognized_observation_status')
    query = data.get('query_result')
    require(type(query) is dict and query.get('mode') == mode, 'H_query_mode_or_result_missing')
    reasons = query.get('reason_codes')
    require(isinstance(reasons, list) and len(reasons) == len(set(reasons)), 'H_query_reason_shape')
    if phase == 'inventory':
        require(mode == 'overview' and query.get('status') in {'complete', 'unknown'}, 'H_inventory_query_status')
        require((query['status'] == 'complete' and reasons == []) or reasons == ['query_pair_required'], 'H_inventory_unexplained_unknown')
        classification = 'original_overview_inventory'
    elif status == 'overview':
        require(query.get('status') == 'unknown' and reasons == ['query_pair_required'], 'H_unexplained_missing_pair')
        classification = 'original_query_pair_required'
    else:
        require(query.get('status') in {'complete', 'unknown'} and query.get('ranking_metric') == 'nonnegative_exact_surface_clearance_m', 'H_original_ranking_scope_missing')
        if query['status'] == 'unknown':
            require(bool(reasons) and set(reasons) <= H_UNKNOWN and bool(query.get('unresolved_object_ids')), 'H_unexplained_query_unknown')
            classification = 'original_query_unknown'
        else:
            require(reasons == [] and query.get('unresolved_object_ids') == [], 'H_complete_with_unresolved')
            classification = 'original_query_complete'
        if mode == 'top1':
            top = query.get('top1')
            require(type(top) is dict and top.get('status') == query['status'] and top.get('execution_authority') is False, 'H_top1_contract_missing')
            if query['status'] == 'unknown':
                require(top.get('nearest_object_ids') is None and top.get('signed_clearance_m') is None, 'H_unknown_top1_has_answer')
    return {'classification': classification, 'status': status, 'query_status': query['status'], 'reason_codes': reasons,
        'geometry_measured': phase == 'query' and query['status'] == 'complete',
        'requested_unsigned_task_qualified': False,
        'scope': 'original H nonpenetrating-clearance contract; not acceptance of the newer unsigned task contract'}


def verify_peer(owner, version, forwarded, static_tools):
    root = owner/'plugin'
    ledger = read(root/'RPC.json')
    folders = sorted(path for path in root.glob('[0-9]*') if path.is_dir())
    require(len(folders) == len(ledger['requests']) and ledger['poisoned'] is False, 'peer_ledger_count_or_poison')
    sent = received = 0
    requests = []
    for index, (folder, receipt) in enumerate(zip(folders, ledger['requests']), 1):
        require(folder.name == str(index).zfill(3), 'peer_sequence_gap')
        tx = (folder/'TX.bin').read_bytes(); request = decode(tx); requests.append(request)
        require(read(folder/'RECEIPT.json') == receipt and receipt['error'] is None and receipt['send_confirmed'] is True
            and receipt['sent_bytes'] == len(tx) and receipt['attempted_send_bytes'] == len(tx), 'peer_send_receipt_mismatch')
        sent += len(tx)
        if 'id' in request:
            raw = (folder/'RX.bin').read_bytes(); reply = decode(raw); received += len(raw)
            require(reply.get('id') == request['id'] and receipt['received_bytes'] == len(raw), 'peer_reply_id_or_bytes_mismatch')
            if request['method'] == 'initialize':
                require(reply == read(owner/'PLUGIN_INITIALIZE.json'), 'actual_initialize_not_saved_reply')
                identity_matches(reply['result']['_meta']['human_eye'], version['identity'])
            elif request['method'] == 'tools/list':
                require(reply == read(owner/'PLUGIN_TOOLS.json') and reply['result']['tools'] == static_tools, 'actual_complete_catalogue_changed')
            elif request.get('id') == 'private-status':
                require(reply == read(owner/'PLUGIN_STATUS.json') and reply['result'].get('isError') is False, 'private_status_failed')
                identity_matches(payload(reply)['runtime_identity'], version['identity'])
            else:
                require(request['id'] in forwarded and forwarded[request['id']][0] == request
                    and forwarded[request['id']][1]['result'] == reply.get('result'), 'product_forwarding_or_reply_rewritten')
        else:
            require(request['method'] == 'notifications/initialized' and not (folder/'RX.bin').exists()
                and receipt['received_bytes'] == 0, 'notification_reply_unexpected')
    require([req.get('id') for req in requests[:4]] == ['private-init', None, 'private-list', 'private-status'], 'private_peer_handshake_changed')
    require([req['id'] for req in requests[4:]] == list(forwarded), 'forwarded_product_request_count_mismatch')
    require(ledger['tx_bytes'] == sent and ledger['rx_bytes'] == received, 'peer_byte_total_mismatch')
    ended = read(root/'CLOSE.json')
    require(ended['confirmed'] is True and ended['process_reaped'] is True and ended['exit_code'] == 0
        and ended['reader_stopped'] is True and ended['error'] is None, 'product_close_not_attested')
    return {'actual_product_stdio_frames': len(folders), 'actual_product_stdio_TX_bytes': sent,
        'actual_product_stdio_RX_bytes': received, 'actual_complete_catalogue_equal_own_version': True}


def main():
    target = HERE/'PREFLIGHT_REVIEW.json'
    require(not target.exists(), 'preflight_review_output_already_exists')
    pre = read(HERE/'PREFLIGHT.json'); source = read(HERE/'SOURCE_PREFLIGHT.json'); plan = read(HERE/'PLAN.json')
    require(pre['passed'] is True and pre['model_calls'] == 0 and len(pre['cells']) == 6, 'six_no_model_cells_required')
    require(Counter((cell['task'], cell['group']) for cell in pre['cells']) == Counter((task, group) for task in ('assembly', 'discovery') for group in ('N', 'H', 'C')), 'duplicate_or_missing_preflight_slots')
    reuse = lifecycle_reuse(); rows = []; paths = {HERE/'PREFLIGHT.json', HERE/'PLAN.json', HERE/'SOURCE_PREFLIGHT.json', HERE/'ADAPTER_TESTS.json'}
    native = None; physical = 0
    oracle = next(row for row in read(DIAG/'ORACLE.json')['snapshots'] if row['id'] == 'D48')['global_nearest_unsigned']
    for cell in pre['cells']:
        folder = Path(cell['folder']).resolve(); owner = folder/'owner'; group, task = cell['group'], cell['task']
        require(folder.is_relative_to(HERE) and cell['error'] is None and cell['closed'] is True and cell['model_calls'] == 0, 'preflight_cell_unqualified')
        config = read(folder/'ACTOR_CONFIG.json'); public = read(folder/'PUBLIC_TOOLS.json')['result']['tools']
        require(config['group'] == group and config['task'] == task, 'actual_actor_slot_mismatch')
        if native is None:
            native = public[0]
        require(public[0] == native and native['name'] == 'execute_blender_code', 'common_native_schema_changed')
        initial, final = read(owner/'INITIAL.json'), read(owner/'FINAL.json')
        expected = read(plan['tasks'][task]['initial'])
        require(initial == final and normalized(initial, task) == normalized(expected, task), 'initial_final_or_frozen_mesh_mismatch')
        require(sha(config['asset']) == plan['tasks'][task]['asset_sha256'] == config['asset_sha256'], 'source_asset_hash_changed')
        for label, snap in (('INITIAL', initial), ('FINAL', final)):
            receipt = read(owner/(label+'.json.receipt.json')); response = receipt['response']
            require(receipt['source_file_unchanged'] is True and receipt['protected_files_unchanged'] is True
                and response['status'] == 'success' and response['result']['executed'] is True
                and decode(response['result']['result']) == snap, 'actual_snapshot_receipt_not_bound')
        closed = read(owner/'CLOSE.json'); finished = read(folder/'OWNER_FINISH.json'); wc = read(owner/'native/WORKER_CLOSED.json')
        require(closed['confirmed'] is True and closed['geometry_unchanged'] is True and closed['asset_unchanged'] is True
            and closed['errors'] == [] and finished['confirmed'] is True and finished['actor_exit'] == 0
            and finished['close'] == closed, 'owner_close_not_attested')
        nc = closed['native_close']
        require(nc['process_reaped'] is True and nc['exit_code'] == 0 and nc['response']['status'] == 'closed'
            and nc['source_file_unchanged'] is True and nc['protected_files_unchanged'] is True
            and wc == closed['worker_closed'] and wc['poisoned'] is False
            and wc['initial_geometry_fingerprint'] == wc['final_geometry_fingerprint'], 'native_close_or_fingerprint_mismatch')
        events = [decode(line) for line in (owner/'native/WORKER_EVENTS.jsonl').read_bytes().splitlines()]
        require(len(events) <= 128 and [event['sequence'] for event in events] == list(range(1, len(events)+1)), 'worker_event_sequence_or_budget')
        require(all(event.get('terminal_geometry_and_file_checks_passed') is True for event in events[:-1]), 'worker_terminal_checks_missing')
        physical += len(events)
        tools = read(owner/'TOOLS.json'); replies = read(folder/'REPLIES.json'); dirs = sorted(owner.glob('tool_[0-9]*'))
        require(tools['attempts'] == cell['tool_attempts'] == len(tools['tools']) == len(replies) == len(dirs), 'attempt_or_reply_count_mismatch')
        forwarded = {}; requests = []; total_bytes = 0
        for seq, (directory, attempt, reply) in enumerate(zip(dirs, tools['tools'], replies), 1):
            require(directory.name == 'tool_'+str(seq).zfill(2), 'attempt_directory_gap')
            request = read(directory/'REQUEST.json'); requests.append(request)
            response_path = directory/'RESPONSE.json' if (directory/'RESPONSE.json').exists() else directory/'ERROR_RESPONSE.json'
            require(read(response_path) == reply and read(directory/'ATTEMPT.json') == attempt and attempt['attempt'] == seq
                and request['id'] == reply.get('id') and attempt['exception'] is None
                and attempt['response_bytes'] == len(wire(reply)), 'actual_attempt_request_response_mismatch')
            require(attempt['is_error'] == reply['result'].get('isError'), 'attempt_error_flag_mismatch')
            total_bytes += attempt['response_bytes']
            name = request['params']['name']
            if name != 'execute_blender_code':
                require(name in READ_NAMES and request['id'] not in forwarded, 'unexpected_or_duplicate_read_request')
                forwarded[request['id']] = (request, reply)
            else:
                receipt = read(directory/'NATIVE_RECEIPT.json')
                require(payload(reply) == receipt['response'], 'native_result_not_actual_receipt')
        require(total_bytes == tools['wire_tool_bytes'] and total_bytes <= 1048576 and len(dirs) <= 32, 'actual_attempt_bytes_or_count_budget')
        require(requests[0]['params']['arguments']['code'] == "raise ValueError('controlled_no_model_preflight_error')"
            and replies[0]['result']['isError'] is True and payload(replies[0])['error']['type'] == 'ValueError'
            and payload(replies[0])['error']['message'] == 'controlled_no_model_preflight_error'
            and replies[1]['result']['isError'] is False, 'controlled_failure_not_preserved_then_recovered')
        row = {'task': task, 'group': group, 'geometry_unchanged': True, 'frozen_mesh_and_receipts_bound': True,
            'normal_owned_backend_close': True, 'failed_attempt_retained': True, 'tool_attempts': len(dirs),
            'worker_events': len(events), 'model_calls': 0, 'public_stdio_TX_RX_measured': False}
        ident = read(owner/'IDENTITY.json')
        if group == 'N':
            require(public == [native] and config['read_schemas'] == [] and ident['runtime_identity'] is None
                and len(dirs) == 2 and not (owner/'plugin').exists(), 'native_only_scope_changed')
        else:
            version = source['versions'][group]; static = read(HERE/(group+'_schemas.stdout.json'))['tools_list']['result']['tools']
            selected = [tool for tool in static if tool['name'] in READ_NAMES]
            require(config['read_schemas'] == selected and public == [native]+selected, 'version_specific_public_schema_changed')
            require(config['source_sha256'] == version['source_sha256'] and config['entry'] == version['entry']
                and config['install_root'] == version['installed_root'], 'controlled_install_binding_changed')
            identity_matches(ident['runtime_identity'], version['identity'])
            row.update(verify_peer(owner, version, forwarded, static))
            require(requests[2]['params'] == {'name': 'human_eye_connection_status', 'arguments': {}}
                and replies[2]['result']['isError'] is False, 'public_status_not_original_empty_request')
            identity_matches(payload(replies[2])['runtime_identity'], version['identity'])
            probe = read(folder/'PRODUCT_PREFLIGHT.json')
            require(probe == cell['product_probe'] and probe['group'] == group and probe['task'] == task
                and all(stage['parse_error'] is None and stage['decoded_metadata'] == payload(stage['raw_response']) for stage in probe['stages']), 'product_probe_raw_metadata_not_bound')
            require([stage['raw_response'] for stage in probe['stages']] == replies[3:], 'product_probe_stage_count_or_order')
            if group == 'H':
                require(len(probe['stages']) in {1, 2} and probe['stages'][0]['stage'] == 'inventory', 'H_inventory_stage_missing')
                inventory_class = qualify_h(replies[3], 'inventory', 'overview')
                if inventory_class['classification'].startswith('original_budget_'):
                    require(len(probe['stages']) == 1 and probe['contract_exit'] == 'inventory_tool_refusal', 'H_budget_exit_not_retained')
                    row['H_original_capability'] = {'inventory': inventory_class, 'query': None}
                else:
                    inventory = payload(replies[3]); objects = inventory.get('objects')
                    require(isinstance(objects, list) and len(objects) == len(initial['objects']), 'H_inventory_incomplete')
                    names = {obj['name']: obj['object_id'] for obj in objects}
                    require(len(names) == len(objects) and len(set(names.values())) == len(objects)
                        and set(names) == {obj['name'] for obj in initial['objects']}, 'H_inventory_ids_or_names_invalid')
                    require(len(probe['stages']) == 2 and probe['stages'][1]['stage'] == 'query' and probe['contract_exit'] is None, 'H_query_not_attempted_after_valid_inventory')
                    args = requests[-1]['params']['arguments']; mode = 'exact_pairs' if task == 'assembly' else 'top1'
                    require(args['query']['mode'] == mode and args['focal_id'] == names['Object_01' if task == 'assembly' else 'Target']
                        and args['reference_id'] in set(names.values())-{args['focal_id']}, 'H_query_ids_not_actual_inventory')
                    if task == 'assembly':
                        require(args['query']['object_ids'] == [names[name] for name in ('Object_02', 'Object_03', 'Object_04')], 'H_original_exact_pair_targets_changed')
                    row['H_original_capability'] = {'inventory': inventory_class, 'query': qualify_h(replies[-1], 'query', mode)}
            else:
                require(len(probe['stages']) == 1 and probe['stages'][0]['stage'] == 'query' and replies[-1]['result']['isError'] is False, 'C_query_failed')
                data = payload(replies[-1]); require(data['binding']['runtime_source_sha256'] == version['source_sha256'], 'C_return_source_binding_mismatch')
                if task == 'assembly':
                    require(data['status'] == 'observed' and len(data['pairs']) == 3, 'C_assembly_pairs_incomplete')
                    for pair, (relation, distance, error) in zip(data['pairs'], [('separated', .01, 2.0446606626675212e-7), ('penetrating', 0., 0.), ('separated', .04, 3.0142333402758355e-7)]):
                        facts = pair['facts']; require(facts['closed_solid_relation']['value'] == relation
                            and abs(facts['surface_proximity']['value']['distance_m']-distance)+error <= 1e-6, 'C_assembly_geometry_answer_wrong')
                else:
                    require(data['status'] == 'complete' and [obj['name'] for obj in data['nearest_objects']] == ['Peer_000']
                        and data['coverage'] == {'targets_excluding_focal': 47, 'distance_valid': 47, 'strictly_excluded': 0, 'unresolved': 0}
                        and max(abs(data['distance_m']-oracle['distance_lower_m']), abs(data['distance_m']-oracle['distance_upper_m'])) <= 1e-6, 'C_unsigned_global_answer_wrong')
                row['C_geometry_answers_qualified'] = True
        paths.update(path for path in folder.rglob('*') if path.is_file())
        rows.append(row)
    result = {'schema': 'complex005-no-model-preflight-review-v1', 'passed': True,
        'scope': 'direct broker TCP records, actual product stdio and owned lifecycle only; not consumer acceptance',
        'model_calls': 0, 'cells': rows, 'common_native_equal_all_6': True,
        'each_release_public_read_schemas_unchanged': True, 'cross_release_schema_equality_required': False,
        'physical_worker_events': physical, 'lifecycle_reuse': reuse,
        'public_stdio_TX_RX_measured': False, 'actual_public_stdio_scope': 'reserved for formal consumers with unmodified 003 thin client',
        'verified_artifact_hashes': {str(path.resolve()): sha(path) for path in sorted(paths)}}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8', newline='\n')
    print(json.dumps({'passed': True, 'cells': len(rows), 'model_calls': 0, 'artifact_files': len(paths), 'worker_events': physical}))


if __name__ == '__main__':
    main()
