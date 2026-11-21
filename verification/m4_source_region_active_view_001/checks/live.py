"""Score the two actual isolated source-region slots against sealed independent evidence."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import (ASSET, BASE, CANDIDATE, CAPTURE, HERE, NS, POSITIVE, RUN, TOP, canonical, digest,
                      frame_metrics, parse_public, pin, read, replay_cli, require, save, verify_capture)


def lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()] if path.is_file() else []


def interval(start, end):
    require(type(start) is int and type(end) is int and start <= end, 'unordered_original_event_clocks')
    return round((end - start) / 1e6, 6)


def stages(value):
    out = {}
    for name, stage in value.items():
        if type(stage) is not dict:
            continue
        if 'elapsed_ns' in stage:
            require(stage['closed_ns'] - stage['started_ns'] == stage['elapsed_ns'], 'stage_clock_mismatch/' + name)
            out[name] = interval(stage['started_ns'], stage['closed_ns'])
        else:
            out[name] = stages(stage)
    return out


def decode_display_scope(body):
    scope = deepcopy(body['image_scope'])
    if body['schema'] == 'source-region-brief-v3':
        directory = scope['objects']
        columns, rows = directory['columns'], directory['rows']
        require(len(columns) == len(set(columns)) and all(len(row) == len(columns) for row in rows),
                'compact_display_directory_not_lossless')
        scope['objects'] = [dict(zip(columns, row, strict=True)) for row in rows]
    else:
        require(body['schema'] == 'source-region-brief-v2' and type(scope['objects']) is list,
                'original_source_region_display_table_schema_changed')
    return scope


def actual_wire(slot, event, meter, expected):
    ident, receipt = event['id'], event['receipt']
    ordinal = event['index']
    call = slot / 'product_calls' / f'call_{ordinal:03d}'
    raw = slot / 'mcp' / f"rpc_{receipt['index']:02d}"
    request = {'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
               'params': {'name': 'human_eye_scene_observe', 'arguments': expected}}
    tx, rx = [(raw / name).read_bytes() for name in ('TX.bin', 'RX.bin')]
    received = json.loads(rx)
    clean = rx.replace(b'\r\n', b'\n')
    require(ident == meter['id'] == meter['response_id'] == receipt['id'] and
            json.loads(tx) == request == event['request'] == read(call / 'REQUEST.json') and
            received == event['response'] == read(call / 'RESPONSE.json') and
            received['result']['isError'] is False and receipt == read(raw / 'RECEIPT.json') and
            receipt['error'] is None and
            len(tx) == meter['TX_bytes'] == receipt['TX_bytes'] and digest(tx) == meter['TX_sha256'] and
            len(rx) == receipt['RX_bytes'] and digest(rx) == receipt['RX_sha256'] and
            len(clean) == meter['RX_text_UTF8_LF_bytes'] and digest(clean) == meter['RX_text_UTF8_LF_sha256'],
            'actual_public_server_and_client_trace_mismatch')
    row = event['producer_archive']
    producer = Path(row['path']).resolve()
    parent = (slot / f"product_full/call_{row['index']:03d}").resolve()
    context = Path(row['read_context']).resolve()
    require(row['index'] == ordinal and row['new_observations_for_archive'] == 0 and
            producer == parent / 'SERVICE_RESULT.json' and context == parent / 'READ_CONTEXT.json' and
            digest(producer.read_bytes()) == row['sha256'],
            'producer_archive_not_bound_to_same_public_operation')
    before, after = [(call / name).read_bytes() for name in ('ARCHIVE_BEFORE.bin', 'ARCHIVE_AFTER.bin')]
    require(after.startswith(before) and len(after.splitlines()) == len(before.splitlines()) + 1 and
            json.loads(after.splitlines()[-1]) == row and
            event['started_ns'] <= meter['request_received_ns'] <= row['producer_returned_ns'] <=
            meter['reply_completed_ns'] <= event['closed_ns'], 'producer_not_synchronous_to_original_wire')
    return (received['result'], read(producer), read(context),
            {'TX': pin(raw / 'TX.bin'), 'RX': pin(raw / 'RX.bin'), 'producer': pin(producer),
             'server_rpc_ms': interval(meter['request_received_ns'], meter['reply_completed_ns']),
             'client_rpc_ms': interval(receipt['started_ns'], receipt['closed_ns']),
             'original_meter_raster_attempts': meter['raster_actual']})


def actual_outer(slot, turn, side, expected, inner, image):
    path = slot / 'batch' / f'rpc_{turn + 2:02d}'
    original = read(path / 'RECEIPT.json')
    tx, rx = [(path / name).read_bytes() for name in ('TCP_TX.bin', 'TCP_RX.bin')]
    request = {'jsonrpc': '2.0', 'id': 'source-region-' + side, 'method': 'tools/call',
               'params': {'name': 'human_eye_scene_observe', 'arguments': expected}}
    wrapper = {'operation': 'attached_mcp', 'request_id': request['id'],
               'args': {'kind': 'native', 'message': request}}
    received = json.loads(rx)
    parsed = received['result']
    require(json.loads(tx) == wrapper and received['ok'] is True and received['request_id'] == request['id']
            and parsed == original['response'] and parsed['id'] == request['id']
            and parsed['result'] == inner and len(tx) == original['TX_bytes'] and len(rx) == original['RX_bytes']
            and digest(tx) == original['TX_sha256'] and digest(rx) == original['RX_sha256'] and
            image == (path / 'image_1.png').read_bytes(), 'outer_relay_did_not_deliver_exact_public_PNG_or_text')
    return {name: original[name] for name in ('started_ns', 'closed_ns', 'TX_bytes', 'RX_bytes', 'TX_sha256',
                                                'RX_sha256', 'client_socket_ns')}


def verify_geometry_binding(producer, capture, installed):
    binding = producer['binding']
    snapshot = capture['display_snapshot']
    flags = {row['host_id']: row for row in snapshot['objects']}
    display = binding['image_scope']
    objects = binding['objects']
    require(binding['runtime_source_sha256'] == installed['source_sha256'] and
            binding['document_epoch'] == capture['host_identity']['document_epoch'] and
            binding['capture_state'] == capture['capture_state'] and
            binding['scene_revision'] == capture['revision'] and
            binding['source'] == 'blender' and binding['unit'] == 'm' and binding['coordinate_frame'] == 'world',
            'source_not_bound_to_same_installed_current_capture')
    require(display['status'] == 'captured' and display['identity'] == binding['display_identity'] ==
            snapshot['sha256'] == digest(canonical({key: val for key, val in snapshot.items() if key != 'sha256'}))
            and display['participation_mask'] == [True] * 28 and
            all(row['object_index'] == index and row['host_id'] == mesh['object_id'] and
                row['object_name'] == mesh['name'] and row['instance_id'] ==
                capture['host_identity']['object_instances'][mesh['object_id']] == flags[mesh['object_id']]['instance_id']
                and flags[mesh['object_id']]['visible_get'] for index, (row, mesh) in
                enumerate(zip(objects, capture['meshes'], strict=True))), 'source_display_identity_or_order_mismatch')
    ordered = [{'host_id': row['host_id'], 'instance_id': row['instance_id'],
                'vertices': mesh['vertices'], 'faces': mesh['faces']}
               for row, mesh in zip(objects, capture['meshes'], strict=True)]
    require(binding['ordered_geometry_sha256'] == digest(canonical(ordered)) and
            binding['camera_identity'] == digest(canonical(binding['camera_specification'])),
            'source_geometry_or_bound_camera_identity_changed')
    ref = producer['region_ref']
    unsigned = {key: value for key, value in ref.items() if key != 'region_id'}
    require(ref['region_id'] == 'source-region:' + digest(canonical(unsigned)) and
            ref['ordered_geometry_sha256'] == binding['ordered_geometry_sha256'] and
            ref['capture_generation'] == {key: capture['capture_state'][key] for key in ('instance_id', 'epoch', 'revision')} and
            ref['source_triangle_indices'] == [20, 21], 'selected_source_reference_generation_changed')
    source = producer['facts']['region']
    index = next(idx for idx, value in enumerate(objects) if value['host_id'] == ref['host_id'])
    mesh = capture['meshes'][index]
    require(mesh['name'] == source['object_name'] == 'N15' and
            [mesh['faces'][idx] for idx in ref['source_triangle_indices']] == source['triangles_source_vertices'] and
            [mesh['vertices'][idx] for idx in source['source_vertex_indices']] == source['vertices_world_m'] and
            source['host_id'] == ref['host_id'] and source['instance_id'] == ref['instance_id'],
            'selected_source_mapping_not_current')


def timing(state, publication, slots):
    start, task, owned = (state[key] for key in ('started_ns', 'task_deadline_ns', 'owned_deadline_ns'))
    published = publication['published_ns']
    require(start + 450_000_000_000 == task and start + 600_000_000_000 == owned and
            all(state['ready_ns'] <= row['outer']['started_ns'] <= row['outer']['closed_ns'] < task for row in slots) and
            start <= state['ready_ns'] <= state['cleanup_started_ns'] <= state['closed_ns'] <= published < owned,
            'absolute_task_or_owned_deadline_changed')
    return {'passed': True, 'owned_window_ms': interval(start, published),
            'admission_ms': state.get('admission_verification_ns', 0) / 1e6,
            'startup_to_ready_ms': interval(start, state['ready_ns']),
            'cleanup_to_publish_ms': interval(state['cleanup_started_ns'], published),
            'absolute_task_ns': task, 'absolute_ownership_ns': owned}


def score_one(label, slot, state, published, frozen, offline, installed):
    requests = lines(slot / 'PUBLIC_REQUESTS.jsonl')
    meters = [row for row in lines(slot / 'mcp_io/MCP_IO.jsonl') if row.get('method') == 'tools/call']
    expected = offline['real_original_request']
    close = state.get('closure_verification', {})
    source = state.get('independent_before_after', {})
    require(published['status'] == state['status'] == 'completed' and state['errors'] == [] and
            published['owned_budget_passed'] is True and close['passed'] is True and
            close['status'] == 'ready_closed' and source['passed'] is True and source['same_owned_scene'] is True and
            state['outer_owner_close']['confirmed'] and state['model_consumers'] == state['paid_API_calls'] == 0 and
            len(requests) == len(meters) == 2 and digest((slot / 'native/input.blend').read_bytes()) == ASSET,
            'actual_slot_progress_or_independent_close_failed')
    counts = state['budget']['slots'][label]
    expected_rasters = 1 if label == 'A' else 2
    require(counts['business_admissions'] == 2 and counts['raster_actual'] == expected_rasters and
            state['budget']['counts']['pending_raster_reservations'] == 0,
            'actual_slot_raster_denominator_was_not_confirmed')
    outer = read(slot / 'batch/QUALIFICATION_BATCH.json')
    require(outer['outer_business_count'] == outer['inner_public_count'] == 2
            and outer['public_request_same_session'] is True and outer['hot_binding_equals_cold'] is True
            and [entry['actual_new_raster_attempts'] for entry in outer['calls']] == [expected_rasters, 0],
            'outer_batch_admission_did_not_count_new_frames')
    dep = installed['dependency_root']
    if dep not in sys.path:
        sys.path.insert(0, dep)
    check = run_path(str(CAPTURE))
    captures, commands = check['decode_captures'](slot, installed, check['Audit']())
    initial = read(slot / 'initial_capture/TERMINAL_SOURCE.json')
    terminal = read(slot / 'TERMINAL_SOURCE.json')
    require(initial['objects'] == terminal['objects'] and
            initial['display_object_mask'] == terminal['display_object_mask'] == [True] * 28,
            'independent_display_or_geometry_changed')
    traces = {trace['annotations'].get('mcp_request_id'): trace for event in lines(slot / 'product_audit.jsonl')
              if event.get('event') == 'request_trace' for trace in [event['trace']]}
    proof = []
    cold = None
    ref_frames = offline['same_installed_renderer_replayed']['independent_frames']
    all_captures = [row for row in commands if row['command']['command'] == 'capture']
    require(1 <= len(all_captures) <= 2 and len(commands) == len(all_captures),
            'extra_live_host_geometry_request_detected')
    for turn, (request, meter) in enumerate(zip(requests, meters, strict=True), 1):
        body, prod, context, wire = actual_wire(slot, request, meter, expected)
        side = 'cold' if turn == 1 else 'hot'
        capture = check['current_capture'](captures, prod['binding'], check['Audit']())
        verify_capture(capture, terminal)
        verify_geometry_binding(prod, capture, installed)
        require(prod['read_only'] is True and prod['execution_authority'] is False and len(prod['frames']) == 1,
                'source_region_result_must_deliver_one_read_only_frame')
        final = frame_metrics(prod['frames'][0], prod, slot=slot)
        metadata, png = parse_public(body, final)
        require(decode_display_scope(metadata) == prod['binding']['image_scope'] and
                metadata['region_ref'] == prod['region_ref'] and
                metadata['task_result']['facts'] == prod['task_result']['facts'] and
                metadata['task_result']['facts']['surface_proximity'] == offline['measurement_fact'] and
                metadata['task_result']['measurement_scope'] == offline['measurement_scope'] and
                metadata['task_result']['source_mapping']['nearest_witness'] ==
                prod['task_result']['source_mapping']['nearest_witness'],
                'public_compact_display_scope_or_proven_measurement_changed')
        cli = replay_cli(body)
        original = actual_outer(slot, turn, side, expected, body, png)
        require(original['started_ns'] <= request['started_ns'] <= request['closed_ns'] <= original['closed_ns'],
                'public_wire_not_inside_actual_outer_call')
        work = prod['work']
        expected_new = expected_rasters if turn == 1 else 0
        require(wire['original_meter_raster_attempts'] == work['raster_attempts'] ==
                work['raster_completed'] == expected_new and work['capture_calls'] <= 1 and
                work['frame_reuses'] == int(turn == 2), 'new_work_accounting_inconsistent')
        visibility = metadata['visibility']
        selected_view = 'SCENE' if label == 'A' else 'RIGHT'
        want = (0, 0) if label == 'A' else POSITIVE
        require(final['view_name'] == selected_view and (final['surface'], final['contrast']) == want and
                final['array_sha256'] == ref_frames[selected_view]['array_sha256'] and
                final['PNG_sha256'] == ref_frames[selected_view]['PNG_sha256'] and
                cli['required_payload_and_PNG_preserved'], 'actual_chosen_original_frame_or_CLI_payload_changed')
        witness = visibility['complete_witness']
        diagnostics = []
        if label == 'A':
            require(witness is None and metadata['observation_status'] == 'evidence_insufficient' and
                    visibility['reason'] == 'selected_region_displayed_without_pixels',
                    'baseline_observation_no_longer_matches_true_failing_SCENE')
        else:
            require(metadata['schema'] == 'source-region-brief-v3' and cli['passed'] and final['corners_inside_clip']
                    and offline['independent_exact_visibility']['RIGHT']['clear'] and
                    all(witness[key] == final[key] for key in ('view_name', 'image_ref', 'frame_identity'))
                    and [witness[k] for k in ('selected_surface_pixels', 'contrasting_boundary_pixels',
                                            'minimum_surface_pixels', 'minimum_boundary_pixels',
                                            'minimum_rgb_boundary_contrast')] == [*POSITIVE, 16, 4, 24]
                    and final['visible_source_ids'] == [20, 21], 'candidate_actual_positive_witness_not_certified')
            built = [frame_metrics(frame, prod, slot=slot) for frame in prod['constructed_frames']]
            require([row['view_name'] for row in built] == ['TOP', 'RIGHT'] and
                    (built[0]['surface'], built[0]['contrast']) == TOP and
                    built[0]['array_sha256'] == ref_frames['TOP']['array_sha256'] and built[1] == final,
                    'all_actual_considered_frame_evidence_did_not_match_TOP_RIGHT_contract')
            diagnostics = [{k: v for k, v in val.items() if k != 'pose'} for val in built]
        if cold is None:
            cold = metadata, final
        else:
            require(metadata['session_id'] == cold[0]['session_id'] and metadata['region_ref'] == cold[0]['region_ref']
                    and visibility == cold[0]['visibility'] and final == cold[1] and work['prepare_cache_hit'] is True,
                    'hot_same_capture_not_same_generation_or_same_original_PNG')
        proof.append({'side': side, 'outer': original, 'public_wire': wire, 'fixed_CLI': cli,
                      'selected_original_frame': {k: v for k, v in final.items() if k != 'pose'},
                      'complete_witness': witness, 'constructed_original_frames': diagnostics,
                      'reason': visibility.get('reason'), 'work': work, 'producer_stages_ms': stages(prod['stages']),
                      'selected_frame_stages_ms': stages(prod['frames'][0].get('stages', {})),
                      'public_trace_stages_ms': {row['name']: row['duration_ns'] / 1e6 for row in
                           traces.get(request['id'], {}).get('spans', [])}, 'read_context': context})
    return {'label': label, 'status': 'completed', 'passed': True, 'actual_geometry_captures': len(all_captures),
            'observed_requests': proof, 'confirmed_close': close, 'source_readback': source,
            'timing': timing(state, published, proof), 'slot_counts': counts}


def review(run, freeze):
    frozen_digest = digest(freeze.read_bytes())
    frozen = read(freeze)
    offline = read(HERE / 'OFFLINE.json')
    rows = []
    denominators = {'registered_owned': 2, 'observed_owned': 0, 'product_calls': 0, 'outer_calls': 0,
                    'raster_attempts': 0, 'models': 0, 'paid_API_calls': 0,
                    'completed': 0, 'failed': 0, 'unrun': 0, 'qualified': 0}
    for label, binding_path in (('A', BASE), ('B', CANDIDATE)):
        slot = run / 'slots' / label
        result = slot / 'SLOT_RESULT.json'
        publication = slot / 'SLOT_PUBLICATION.json'
        arm = {'label': label, 'status': 'unconfirmed' if slot.is_dir() else 'unrun', 'passed': False}
        state = read(result) if result.is_file() else {}
        denominators['observed_owned'] += int(slot.is_dir())
        denominators['product_calls'] += len(lines(slot / 'PUBLIC_REQUESTS.jsonl'))
        denominators['outer_calls'] += sum((slot / f'batch/rpc_{i:02d}/RECEIPT.json').is_file() for i in (3, 4))
        denominators['models'] += state.get('model_consumers', 0)
        denominators['paid_API_calls'] += state.get('paid_API_calls', 0)
        denominators['raster_attempts'] += (state.get('budget') or {}).get('slots', {}).get(label, {}).get('raster_actual', 0)
        if publication.is_file():
            pub = read(publication)
            arm.update(status=pub['status'], runtime_errors=state.get('errors', []),
                       result_sha256=pub['result_sha256'], closure=state.get('closure_verification'))
            try:
                installed = read(binding_path)
                stamp = frozen['products'][label]
                require(state['label'] == pub['label'] == label and state['freeze_sha256'] == frozen_digest and
                        pub['result_sha256'] == digest(result.read_bytes()) and
                        state['product_binding_sha256'] == digest(binding_path.read_bytes()) and
                        stamp == {key: installed['preparation_git' if key == 'commit' else key]
                                  for key in ('commit', 'source_sha256', 'wheel_sha256')},
                        'slot_publication_not_bound_to_current_frozen_product')
                if pub['status'] == 'completed':
                    arm.update(score_one(label, slot, state, pub, frozen, offline, installed))
            except Exception as exc:
                arm.update(review_error=str(exc), review_error_class=type(exc).__name__)
        rows.append(arm)
        if arm['status'] in ('completed', 'failed', 'unrun'):
            denominators[arm['status']] += 1
        denominators['qualified'] += int(arm['passed'])
    return {'schema': 'm4-source-region-active-view-live-review-v1', 'freeze_sha256': frozen_digest,
            'passed': (denominators['qualified'] == 2 and denominators['product_calls'] ==
                       denominators['outer_calls'] == 4 and denominators['raster_attempts'] == 3 and
                       denominators['models'] == denominators['paid_API_calls'] == 0),
            'denominators': denominators, 'slots': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--freeze', type=Path, default=NS / 'FROZEN.json')
    parser.add_argument('--output', type=Path, default=HERE / 'LIVE_REVIEW.json')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_isolated_interpreter_required')
    data = review(args.runtime, args.freeze)
    print('Live source-region proof', save(args.output, data), 'passed', data['passed'])
    if not data['passed']:
        for row in data['slots']:
            print(row['label'], row['status'], row.get('review_error'), row.get('runtime_errors'))
    return 0 if data['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
