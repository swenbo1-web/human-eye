"""Bind the historical no-image full and brief wires to their archived CLI events."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZipFile


V = Path(__file__).resolve().parents[2]
RUNS = {
    'P1_full': ('he_perf050_source_scope_rank_transfer_recovery_001', 'P1', 1,
                'item_3', 39717, 11, 'fef71aa0e06b589e386783f800ee67f507cc10b8a78bcd69de29d3b02f93810c'),
    'N15_P2_brief': ('he_perf050_source_region_active_view_p2', 'P2', 5,
                     'item_7', 12032, 28, 'befd9d28399e6a2a06b89626d221684433050fda01422d1552a7b05eafde4aa5'),
}
DISTANCE = ('task_result', 'facts', 'surface_proximity', 'value', 'distance_m')
POINTS = ('task_result', 'facts', 'surface_proximity', 'value', 'nearest_witness')
POINT_FACES = ('task_result', 'source_mapping', 'nearest_witness')
N15_DISPLAY_LOSS = {('image_scope', 'objects', 11, field)
                    for field in ('object_name', 'instance_id', 'participates')}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return sha256(raw).hexdigest()


def proof(raw):
    return {'bytes': len(raw), 'sha256': digest(raw)}


def decoded(raw):
    return json.loads(raw)


def duplicates(text, data):
    require(data['binding'] == data['task_result']['binding'], 'full_binding_not_equal')
    require(data['region_ref'] == data['task_result']['region_ref'], 'full_region_ref_not_equal')
    raw = text.encode()
    values = {}
    for name, byte_count in (('binding', 16230), ('region_ref', None)):
        encoded = json.dumps(data[name], ensure_ascii=False, separators=(',', ':')).encode()
        marker = ('"' + name + '":').encode()
        needle = marker + encoded
        first = raw.find(needle)
        second = raw.find(needle, first + len(needle))
        require(first >= 0 and second > first and raw.count(needle) == 2, 'raw_duplicate_field_span/' + name)
        require(byte_count is None or len(encoded) == byte_count, 'raw_duplicate_value_byte_count/' + name)
        values[name] = {**proof(encoded), 'raw_occurrences': 2, 'total_value_bytes': 2 * len(encoded),
                        'value_spans_zero_based_half_open': [[start + len(marker), start + len(needle)]
                                                            for start in (first, second)]}
    return values


def archive_result(name, definition, output):
    run, slot_label, attempt, item_id, text_bytes, object_count, archive_sha = definition
    root = Path('D:/') / run
    slot_rel = f'slots/{slot_label}'
    slot = root / slot_rel
    archive_path = root / 'ORIGINAL_RUNTIME.zip'
    archive_pin = proof(archive_path.read_bytes())
    require(archive_pin['sha256'] == archive_sha, 'historical_archive_changed/' + name)
    call = f'product_calls/call_{attempt:03d}'
    tcp = f'mcp/rpc_{attempt + 3:02d}'
    owner = f'owner/tool_{attempt:02d}'
    outer_seq = f'{attempt + 3:03d}'
    attachment, = (slot / 'consumer/attachments').glob(f'bridge_*/{outer_seq}/TX.bin')
    outer = attachment.parent.relative_to(slot).as_posix()
    public_requests_path = 'PUBLIC_REQUESTS.jsonl'
    request_log = (slot / public_requests_path).read_bytes()
    log_entry, = (item for item in map(decoded, request_log.splitlines()) if item['id'] == f'observe-{attempt}')
    producer_pin = log_entry['producer_archive']
    require(producer_pin['new_observations_for_archive'] == 0, 'unexpected_additional_historical_observation')
    wanted = {
        'product_request.json': f'{call}/REQUEST.json', 'product_response.json': f'{call}/RESPONSE.json',
        'public_requests.jsonl': public_requests_path,
        'producer.json': Path(producer_pin['path']).relative_to(slot).as_posix(),
        'read_context.json': Path(producer_pin['read_context']).relative_to(slot).as_posix(),
        'inner_tx.bin': f'{tcp}/TX.bin', 'inner_rx.bin': f'{tcp}/RX.bin',
        'inner_receipt.json': f'{tcp}/RECEIPT.json', 'owner_request.json': f'{owner}/REQUEST.json',
        'owner_response.json': f'{owner}/RESPONSE.json', 'owner_receipt.json': f'{owner}/RECEIPT.json',
        'outer_tx.bin': f'{outer}/TX.bin', 'outer_rx.bin': f'{outer}/RX.bin',
        'outer_receipt.json': f'{outer}/RECEIPT.json',
        'business_source_binding.json': 'consumer/BUSINESS_SOURCE_BINDING.json',
        'slot_result.json': 'SLOT_RESULT.json',
    }
    with ZipFile(archive_path) as bundle:
        sealed = {filename: bundle.read(f'{slot_rel}/{original}') for filename, original in wanted.items()}
        whole_stdout = bundle.read(f'{slot_rel}/consumer/stdout.raw.bin')
    require(all(raw == (slot / wanted[filename]).read_bytes() for filename, raw in sealed.items())
            and whole_stdout == (slot / 'consumer/stdout.raw.bin').read_bytes(), 'historical_raw_file_differs/' + name)

    q = decoded(sealed['inner_tx.bin'])
    reply = decoded(sealed['inner_rx.bin'])
    result = reply['result']
    outer_q = decoded(sealed['outer_tx.bin'])
    outer_response = decoded(sealed['outer_rx.bin'])
    inner_pin = decoded(sealed['inner_receipt.json'])
    outer_pin = decoded(sealed['outer_receipt.json'])
    owner_pin = decoded(sealed['owner_receipt.json'])
    args = q['params']['arguments']
    require(q == decoded(sealed['product_request.json']) and reply == decoded(sealed['product_response.json'])
            and q == log_entry['request'] and reply == log_entry['response']
            and digest(sealed['producer.json']) == producer_pin['sha256']
            and inner_pin['id'] == q['id'] == reply['id']
            and inner_pin['RX_sha256'] == digest(sealed['inner_rx.bin']), 'historical_inner_mcp_binding/' + name)
    require(outer_q == decoded(sealed['owner_request.json']) and outer_response == decoded(sealed['owner_response.json'])
            and outer_q['id'] == outer_response['id'] == owner_pin['RPC_id'] == outer_pin['RPC_id']
            and args == outer_q['params']['arguments'] and outer_response['result'] == result,
            'historical_outer_mcp_binding/' + name)

    completed = []
    for raw in whole_stdout.splitlines(keepends=True):
        event = decoded(raw)
        item = event.get('item', {})
        if event.get('type') == 'item.completed' and item.get('id') == item_id:
            completed.append((item, raw))
    (item, cli_line), = completed
    require(item['tool'] == q['params']['name'] == 'human_eye_scene_observe'
            and item['status'] == 'completed' and item['arguments'] == args
            and item['result']['content'] == result['content'], 'historical_cli_original_binding/' + name)
    business = decoded(sealed['business_source_binding.json'])
    recorded, = (record for record in business['result_contracts'] if record['attempt'] == attempt)
    require(recorded['matched'] and recorded['reason'] == 'content_and_envelope_match'
            and recorded['caller_identity']['CLI_event_item_id'] == item_id
            and recorded['TX_sha256'] == digest(sealed['outer_tx.bin'])
            and recorded['RX_sha256'] == digest(sealed['outer_rx.bin'])
            and recorded['CLI_text_UTF8_bytes'] == text_bytes and recorded['CLI_images'] == 0,
            'historical_actual_business_source_binding/' + name)

    (content,) = result['content']
    require(not result['isError'] and content['type'] == 'text', 'historical_no_image_success/' + name)
    require(args['include_image'] is False and args['query']['mode'] == 'source_region'
            and args['response_detail'] == ('full' if name == 'P1_full' else 'brief'), 'wrong_fixed_request/' + name)
    text = content['text']
    public = decoded(text)
    producer = decoded(sealed['producer.json'])
    status = {key: public[key] for key in ('schema', 'status', 'observation_status', 'read_only')}
    require(len(text.encode()) == text_bytes and status['status'] == 'complete'
            and status['observation_status'] == 'image_not_requested' and status['read_only'] is True
            and producer['frames'] == [] and public['region_ref'] == producer['region_ref']
            and len(producer['binding']['image_scope']['objects']) == object_count, 'original_source_contract/' + name)
    measurement = public['task_result']
    fact = measurement['facts']['surface_proximity']
    point_faces = measurement['source_mapping']['nearest_witness']
    visibility = public['facts']['visibility'] if name == 'P1_full' else public['visibility']
    require(measurement['status'] == 'complete' and fact['status'] == 'measured'
            and fact == producer['task_result']['facts']['surface_proximity']
            and point_faces == producer['task_result']['source_mapping']['nearest_witness']
            and visibility['status'] == 'unknown' and visibility['reason'] == 'image_not_requested',
            'historical_measurement_or_visibility_contract/' + name)
    if name == 'P1_full':
        require(public['binding'] == producer['binding'] and public['task_result'] == producer['task_result'],
                'historical_full_producer_fields_changed')
    else:
        require(args['query']['region'] == {'object': {'name': 'N15'}, 'source_triangle_indices': [20, 21]}
                and args['query']['reference'] == {'name': 'N23'} and public['schema'] == 'source-region-brief-v2',
                'historical_N15_identity_changed')

    result_pin = decoded(sealed['slot_result.json'])
    output.mkdir(parents=True, exist_ok=False)
    for filename, raw in sealed.items():
        (output / filename).write_bytes(raw)
    (output / 'cli_completed_original_event.jsonl').write_bytes(cli_line)
    (output / 'body_original.json').write_bytes(text.encode())
    details = {'archive': {'path': str(archive_path), **archive_pin}, 'attempt': attempt, 'slot': slot_label,
               'arguments': args, 'body': proof(text.encode()), 'source_objects': object_count,
               'result_status': status, 'visibility': visibility, 'measurement_status': measurement['status'],
               'measured_distance_m': fact['value']['distance_m'], 'point_pair': fact['value']['nearest_witness'],
               'nearest_witness_source': point_faces, 'region_ref': public['region_ref'],
               'actual_opening_text_and_CLI_match': True, 'actual_CLI_item_id': item_id,
               'actual_CLI_event_line': proof(cli_line), 'actual_CLI_stdout_input': proof(whole_stdout),
               'actual_CLI_images': 0, 'actual_slot_status': result_pin['status'],
               'actual_producer_source_sha256': result_pin['product_source_sha256'],
               'actual_outer_stdio_wall_ms': (outer_pin['flush_completed_ns'] - outer_pin['received_ns']) / 1e6,
               'actual_inner_mcp_RTT_ms': inner_pin['elapsed_ns'] / 1e6,
               'archived_inputs': {filename: {'archive_member': f'{slot_rel}/{wanted[filename]}', **proof(raw)}
                                   for filename, raw in sealed.items()}}
    if name == 'P1_full':
        details['raw_duplicate_object_bytes'] = duplicates(text, public)
    return result, details


def budget_replay(result, name, output, helpers, policy, omitted):
    original = result['content'][0]['text']
    rows = []
    for seconds, head_bytes in zip(('0.0000', '10.0000', '100.0000'), (33, 34, 35), strict=True):
        rows_in = helpers['model_items'](result, seconds)
        require(len(rows_in[0]['text'].encode()) == head_bytes, 'offline_budget_header_changed')
        mcp = helpers['truncate_items'](rows_in, policy['MCP_bytes'])
        history = helpers['truncate_items'](mcp, policy['history_approximate_tokens'], token_mode=True)
        for stage, items in (('MCP', mcp), ('history', history)):
            texts = [row['text'] for row in items if row['type'] == 'input_text']
            kept = texts[1]
            lost = omitted(original, kept)
            lost_distance = DISTANCE in lost
            lost_point = [list(path) for path in lost if path[:len(POINTS)] == POINTS]
            lost_point_faces = [list(path) for path in lost if path[:len(POINT_FACES)] == POINT_FACES]
            lost_region_ref = [list(path) for path in lost if path[0] == 'region_ref']
            if name == 'P1_full':
                require(len(lost) == 1340 and lost_distance and len(lost_point) == 9 and lost_region_ref,
                        'P1_full_historical_middle_cut_changed')
            else:
                require(set(lost) == N15_DISPLAY_LOSS and not (lost_distance or lost_point or lost_point_faces or lost_region_ref),
                        'N15_historical_budget_edge_changed')
            output_name = f'{head_bytes}_{stage}_body.txt'
            (output / output_name).write_bytes(kept.encode())
            rows.append({'stage': stage, 'tool_header_bytes': head_bytes, 'retained_body_file': output_name,
                         'retained': proof(kept.encode()), 'omitted_JSON_leaves': len(lost),
                         'display_row_omitted_leaves': [list(path) for path in lost if path in N15_DISPLAY_LOSS],
                         'distance_omitted': lost_distance,
                         'point_pair_omitted_leaves': lost_point, 'point_source_omitted_leaves': lost_point_faces,
                         'root_region_ref_omitted_leaves': lost_region_ref})
    return rows


def main(output):
    budget = V / 'm4_cross_scale_live_qualification_001/checks/delivery.py'
    loss = V / 'm5_global_observe_measure_qualification_001/checks/live_wire.py'
    helpers, policy = run_path(str(budget))['budget_helpers']()
    sys.path.insert(0, str(loss.parent))
    omitted = run_path(str(loss))['omitted_paths']
    require((policy['MCP_bytes'], policy['history_approximate_tokens']) == (12000, 3000), 'budget_policy_changed')
    results = {}
    output.mkdir(parents=True, exist_ok=False)
    for name, definition in RUNS.items():
        raw, details = archive_result(name, definition, output / name)
        details['fixed_budget_offline_replays'] = budget_replay(raw, name, output / name, helpers, policy, omitted)
        results[name] = details
    files = {path.relative_to(output).as_posix(): proof(path.read_bytes())
             for path in sorted(output.rglob('*')) if path.is_file()}
    report = {'passed': True, 'scope': 'historical wire audit and offline policy only; no product, provider or Blender launches',
              'runtime_cases': len(results), 'policy_stages': sum(len(r['fixed_budget_offline_replays']) for r in results.values()),
              'retained_policy_files': {str(path): proof(path.read_bytes()) for path in (budget, loss)},
              'cases': results, 'sealed_output_files': files}
    with (output / 'HISTORY_BOUNDARY.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': True, 'runtime_cases': len(results), 'policy_cases': report['policy_stages'],
                      'receipt': str(output / 'HISTORY_BOUNDARY.json'), **proof((output / 'HISTORY_BOUNDARY.json').read_bytes())}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output.resolve())
