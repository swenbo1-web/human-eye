"""Independent saved-only audit of two real zero-model recovery sessions."""

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import traceback


HERE = Path(__file__).resolve().parent
PRIOR = HERE.with_name('m5_task_consumption_001')
REFERENCE_PINS = {
    'saved_evidence_R1.py': '58b012ae540f45906d666b4cea2e9a13e56589e36eb9581b96976db79339c060',
    'product_evidence_saved_R1.py': 'e33a906551ecec1b7b9dca580c8d16b0a15f9e3d860f838e601d30a16935e43a',
    'pixel_oracle.py': '76134a3cf3698d56beb53a15b84b0cfe8ba015ebf2f9cfdc777e9c91d19fee04',
    'admin/TRUTH.json': '50588329cb0829df5cd66aa11d7016e6db779b5760788158c34197235760e558'
}
INPUTS = {}


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def read(path):
    return json.loads(raw(path))


def sha(path):
    return hashlib.sha256(raw(path)).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def load(path, name):
    raw(path)
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def original_public(response):
    text = [block['text'] for block in response['result']['content'] if block.get('type') == 'text']
    require(len(text) == 1, 'one_original_MCP_public_JSON_required')
    return json.loads(text[0])


def source_quality(folder, expectations):
    for name, digest in REFERENCE_PINS.items():
        require(sha(PRIOR/name) == digest, 'accepted_independent_source_or_pixel_helper_changed')
    saved = load(PRIOR/'saved_evidence_R1.py', '_recovery_current_source_pixels')
    truth = read(PRIOR/'admin/TRUTH.json')
    evidence = saved.evaluate_slot(folder, truth)
    require(evidence['observation_measurement_current_source_consistent'], 'one_current_source_required')
    require(len(evidence['summary']['product_reviews']) == 2, 'two_current_observation_producers_required')
    for row in evidence['summary']['product_reviews']:
        counts = row['counts']
        require(all(counts[key] == value for key, value in expectations['sequence'][0]['inspection'].items()),
                'registered_observation_quality')
    return evidence


def closure(folder, group, expected):
    result = read(folder/'SLOT_RESULT.json')
    publication = read(folder/'SLOT_PUBLICATION.json')
    require(result['schema'] == 'm5-harness-recovery-slot-v1'
            and publication['schema'] == 'm5-harness-recovery-publication-v1'
            and result['group'] == group and result['status'] == publication['status'] == 'completed'
            and result['errors'] == [], 'closed_session_status')
    require(result.get('consumer_record') is None and result.get('consumer_envelope_path') is None,
            'zero_model_consumers_required')
    require(result['model_consumers'] == result['paid_API_calls'] == 0, 'zero_models_and_paid_API_calls')
    require(result['source']['product_source141_sha256'] == expected['products'][group], 'external_frozen_product_identity')
    require(result['source']['asset_sha256'] == expected['asset_sha256'], 'external_fixed_asset')
    start = result['clocks']['slot_started_ns']
    deadline = result['clocks']['owned_deadline_ns']
    require(deadline == start+600_000_000_000 and result['clocks']['worker_deadline_ns'] == deadline
            and publication['slot_started_ns'] == start
            and start <= publication['slot_result_published_ns'] < deadline
            and publication['result_sha256'] == sha(folder/'SLOT_RESULT.json'), 'original_owned_deadline_and_publication')
    cleanup = result['cleanup']
    require(cleanup['actor_exit_code'] == 0 and cleanup['actor_process_handle_closed'], 'actor_process_closed')
    for name in ('native', 'mcp'):
        item = cleanup[name]
        require(item['confirmed'] is True and item['exit_code'] == 0 and item['handle_closed'] is True
                and item.get('forced_by_root') is False, 'held_process_not_closed_'+name)
    actor = cleanup['actor_close']
    require(actor['errors'] == [] and actor['bridge']['confirmed'] is True and actor['bridge']['errors'] == [], 'owner_closed_without_errors')
    runtime = actor['runtime']
    require(runtime['errors'] == [] and runtime['runtime']['errors'] == [], 'runtime_closed_without_errors')
    native = runtime['Blender_status']
    require(native['source_file_unchanged'] is True and native['protected_files_unchanged'] is True,
            'original_source_files_unchanged')
    require(native['closed']['initial_geometry_fingerprint'] == native['closed']['final_geometry_fingerprint']
            and native['closed'].get('poisoned') is False, 'original_scene_unchanged')
    require(runtime['Blender_close']['process_reaped'] is True and runtime['Blender_close']['exit_code'] == 0,
            'owned_Blender_reaped')
    require(runtime['MCP_stdio_close']['confirmed'] is True and runtime['MCP_stdio_close']['exit_code'] == 0
            and runtime['MCP_retained_exit']['confirmed'] is True and runtime['MCP_retained_exit']['exit_code'] == 0,
            'original_product_stdio_closed')
    budget = runtime['runtime']['budget']
    counts = budget['counts']
    require(budget['limits'] == {'Blender_start_attempts': 2, 'all_rasters': 12, 'consumer_tasks': 0}
            and counts['Blender_start_attempts'] <= 2 and counts['Blender_spawned_unknown'] == 0
            and counts['pending_raster_reservations'] == 0 and counts['all_raster_upper'] <= 12
            and counts['consumer_admissions'] == 0, 'original_zero_model_budget_settled')
    return result, runtime


def audit_session(folder, group, expected):
    folder = Path(folder).resolve()
    result, closed = closure(folder, group, expected)
    evidence = source_quality(folder, expected)
    rows = [json.loads(line) for line in raw(folder/'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
    tools = read(folder/'owner/TOOLS.json')['tools']
    registered = read(HERE/'harness/REQUESTS.json')['groups'][group]
    require(len(rows) == 5 and len(tools) == 4 and [row['attempt'] for row in tools] == [1,2,3,4], 'fixed_five_API_four_outer_sequence')
    require([row['producer_archive_index'] for row in rows] == expected['expected_service_archive_indices'], 'independent_service_archive_sequence')
    archive = load(HERE/'archive_oracle.py', '_recovery_independent_archive_transition')
    public, markers, archive_reviews, outer_reviews = [], [], [], []
    previous_after = b''
    for row, specification in zip(rows, expected['sequence']):
        index = specification['public_call_index']
        require(row['internal_public_call_index'] == index, 'original_public_sequence')
        request, response = read(row['request_path']), read(row['response_path'])
        require(request == row['request'] and response == row['response'], 'original_API_snapshot')
        for name, hash_key in (('request_path','request_sha256'),('response_path','response_sha256'),
                               ('actual_TX_path','actual_TX_sha256'),('actual_RX_path','actual_RX_sha256')):
            path = Path(row[name]).resolve()
            require(path.is_relative_to(folder) and sha(path) == row[hash_key], 'current_API_path_and_bytes')
        require(read(row['actual_TX_path']) == request and read(row['actual_RX_path']) == response, 'actual_original_MCP_TX_RX')
        args = request['params']['arguments']
        query = specification.get('query', specification.get(group+'_query'))
        require(args['query'] == query and args['include_image'] is specification['include_image'], 'registered_query_arguments')
        require('response_detail' not in args, 'registered_default_public_detail')
        flag = response['result']['isError']
        require(type(flag) is bool and flag is expected['expected_original_MCP_isError'][index-1], 'original_MCP_error_flag')
        require(row.get('post_reply_binding_error') is None, 'no_post_reply_bridge_binding_error')
        before_path, after_path = Path(row['request_path']).parent/'ARCHIVE_BEFORE.bin', Path(row['request_path']).parent/'ARCHIVE_AFTER.bin'
        before, after = raw(before_path), raw(after_path)
        require(before == previous_after, 'consecutive_archive_snapshots_original_chain')
        require(hashlib.sha256(before).hexdigest() == row['archive_before_sha256']
                and hashlib.sha256(after).hexdigest() == row['archive_after_sha256'], 'archive_snapshot_SHA')
        review = archive.transition(before, after, row['started_ns'], row['closed_ns'], flag, folder/'product_full')
        require(review['service_archive_index'] == expected['expected_service_archive_indices'][index-1], 'actual_delta_matches_registered_service_sequence')
        if review['service_archive_index'] is not None:
            raw(review['archive_payload_path'])
        require(0 <= row['closed_ns']-row['started_ns'] <= 30_000_000_000, 'original_product_request_budget')
        previous_after = after
        value = original_public(response)
        public.append(value)
        archive_reviews.append({'public_call_index': index, 'step': specification['step'], 'original_isError': flag, **review})
    require(raw(folder/'product_full/INDEX.jsonl') == previous_after, 'terminal_archive_exact_last_snapshot')
    for tool in tools:
        n = tool['attempt']
        require(read(folder/'owner'/f'tool_{n:02}'/'REQUEST.json') == registered[n-1], 'frozen_original_outer_request')
        response = read(folder/'owner'/f'tool_{n:02}'/'RESPONSE.json')
        require(response['result']['isError'] is False, 'outer_Python_execution_must_deliver_results')
        texts = [block['text'] for block in response['result']['content'] if block.get('type') == 'text']
        require(len(texts) == 1, 'one_outer_Python_text')
        payload = json.loads(texts[0])
        require(type(payload.get('stdout')) is str and not payload.get('error'), 'ordinary_Python_stdout_without_exception')
        found = [json.loads(line[len(expected['public_delivery']['marker']):]) for line in payload['stdout'].splitlines()
                 if line.startswith(expected['public_delivery']['marker'])]
        expected_indices = [row['public_call_index'] for row in expected['sequence'] if row['outer_attempt'] == n]
        require(tool['internal_public_call_indices'] == expected_indices and len(found) == len(expected_indices), 'outer_to_inner_real_call_mapping')
        require(len(tool['product_requests']) == len(expected_indices), 'ordinary_wrapper_original_call_markers')
        for marker, index, wrapper in zip(found, expected_indices, tool['product_requests']):
            spec = expected['sequence'][index-1]
            require(set(marker) == set(expected['public_delivery']['record_fields']) and marker['step'] == spec['step'], 'original_result_container_schema')
            require(canonical(marker['public_result']) == canonical(public[index-1]), 'outer_Python_must_get_original_public_JSON')
            require(type(marker['isError']) is bool and marker['isError'] is rows[index-1]['response']['result']['isError']
                    and wrapper['is_error'] is marker['isError'], 'original_error_flag_preserved_in_wrapper_and_stdout')
            markers.append({'step': marker['step'], 'isError': marker['isError'], 'public_JSON_sha256': hashlib.sha256(canonical(marker['public_result']).encode()).hexdigest(),
                            'outer_attempt': n, 'public_call_index': index})
        images = [block for block in response['result']['content'] if block.get('type') == 'image']
        outer_reviews.append({'attempt': n, 'markers': len(found), 'actual_image_sha256s': [hashlib.sha256(base64.b64decode(block['data'], validate=True)).hexdigest() for block in images]})
    require([row['step'] for row in markers] == [row['step'] for row in expected['sequence']], 'five_original_public_results_delivered_in_order')
    invalid = public[1]
    reject = expected['sequence'][1]
    require(invalid['status'] == reject['public_status'] and invalid['error'] == reject['expected_error']
            and invalid['executed'] is False and invalid['execution_status'] == 'not_executed', 'rejection_must_be_expected_frontend_reason')
    for index in (2,3):
        value, spec = public[index], expected['sequence'][index]
        require(value['schema_version'] == spec['public_schema_version'] and value['status'] == spec['public_status'], 'delivered_success_and_partial_status')
        require(value['facts']['surface_proximity']['status'] == 'measured', 'partial_keeps_valid_surface_fact')
    require(public[3]['facts']['closed_solid_relation']['status'] == 'unknown', 'partial_unknown_preserved')
    for index in (0,4):
        require(public[index]['schema'] == 'active-observation-brief-v5', 'actual_default_brief_delivery')
        require(all(public[index]['inspection']['counts'][key] == value for key,value in expected['sequence'][0]['inspection'].items()), 'current_observation_quality')
    if group == 'B':
        require(type(public[4].get('task_result')) is dict and public[4]['task_result']['status'] == 'observed', 'actual_joint_measurement_delivery')
    require(outer_reviews[0]['actual_image_sha256s'] and outer_reviews[-1]['actual_image_sha256s'], 'initial_and_final_actual_PNG_delivery')
    final_refs = []
    for public_index, outer_index in ((0,0),(4,3)):
        images = public[public_index]['images']
        require(len(set(images['columns'])) == len(images['columns'])
                and all(len(row) == len(images['columns']) for row in images['rows']), 'public_image_table_shape')
        image_rows = [dict(zip(images['columns'], row)) for row in images['rows']]
        require([row['image_sha256'] for row in image_rows] == outer_reviews[outer_index]['actual_image_sha256s'],
                'actual_outer_PNGs_match_this_public_reply')
        require(all(row['image_ref'] in evidence['by_ref'] and evidence['by_ref'][row['image_ref']]['current_source_verified']
                    for row in image_rows), 'actual_reply_frame_refs_registered_and_current')
        if public_index == 4:
            final_refs = [row['image_ref'] for row in image_rows]
    final_frames = evidence['summary']['frames']
    require(bool(final_frames), 'current_frame_registration_required')
    last_entry = archive.records(previous_after)[-1]
    last_full = read(last_entry['path'])
    cache = {key: last_full.get('work', {}).get(key) for key in ('result_cache_hit', 'frame_reuses', 'raster_attempts', 'raster_completed')}
    for path in sorted(folder.rglob('*')):
        if path.is_file():
            raw(path)
    return {'group': group, 'passed_checked_scope': True, 'outer_public_results': markers,
            'archive_association': archive_reviews, 'outer_deliveries': outer_reviews,
            'surface_success_delivered_after_rejection': True, 'partial_and_unknown_delivered_after_rejection': True,
            'actual_product_replies_prove_MCP_availability': [3,4,5], 'owner_ping_is_not_substitute': True,
            'source_frame_and_numeric_review': evidence['summary'],
            'final_frame_registration': final_refs, 'final_cache_metadata_as_observed': cache,
            'actual_current_source_generation': evidence['summary']['public_API']['one_current_generation'],
            'actual_product_source_sha256': closed['runtime']['product_source_sha256'],
            'settled_budget': closed['runtime']['budget'],
            'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0}


def qualify(runtime_root):
    expected = read(HERE/'EXPECTATIONS.json')
    require(sha(HERE/'harness/REQUESTS.json') == 'abdef182c015d8b72c99b5e0c013dbe0480176ea28471a775d42530ff698a3d0',
            'frozen_recovery_requests_changed')
    records = []
    for group in ('A','B'):
        folder = Path(runtime_root)/'sessions'/group
        try:
            records.append(audit_session(folder, group, expected))
        except Exception as error:
            records.append({'group': group, 'passed_checked_scope': False, 'error_type': type(error).__name__,
                            'error': str(error), 'traceback': traceback.format_exc()})
    return {'schema': 'm5-harness-recovery-independent-qualification-v1',
            'passed_checked_scope': all(row['passed_checked_scope'] for row in records), 'denominator': 2, 'records': records,
            'expectations_sha256': sha(HERE/'EXPECTATIONS.json'), 'checker_sha256': sha(Path(__file__)),
            'inputs_sha256': dict(sorted(INPUTS.items())), 'accepted_reference_helpers': REFERENCE_PINS,
            'private_full_used_as_outer_delivery': False, 'performance_ranking_performed': False,
            'product_benefit_test': False, 'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, default=Path('D:/he_m5_harness_recovery_001'))
    parser.add_argument('--output', type=Path, default=HERE/'QUALIFICATION.json')
    args = parser.parse_args()
    report = qualify(args.runtime_root)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': report['passed_checked_scope'], 'records': 2,
                      'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest()}))
