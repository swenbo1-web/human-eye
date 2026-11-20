"""Check the one owned brief/full sequence against real files and archived evidence."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
ASSEMBLY = V / 'm4_cross_scale_assembly_transfer_001'
ARCHIVED_RUN = Path('D:/he_m4_cross_scale_assembly_transfer_001')
RUN = Path('D:/he_m4_cross_scale_pixel_evidence_001')
TRUTH = ASSEMBLY / 'fixture/CURRENT_TRUTH.json'
TRUTH_SHA = 'da4a27ac2cf278709a3f1a7de691af416fc2c1b21d2846a21a1d38732ddbbd71'
OLD_BINDING = V / 'm4_cross_scale_cold_frustum_001/install/PRODUCT_RUN_BINDING.json'
OLD_SOURCE = 'ea93acca1a4ba0bcd527f9702657e9180bac05e2cb126e10474fb525b7fa1ca7'
OLD_ARCHIVE_SHA = 'bf7be101396593b151411e567b05af32e0e0754ac18dc733a6a10191fcae3627'
PRODUCT = 'human_eye_scene_observe'
ROW_OUTCOMES = {'N10': ('unknown', 'pixel_evidence_insufficient'),
                'N11': ('unknown', 'positive_area_occlusion_all_front_views'),
                'N22': ('covered', 'observed_readable')}

prior = runpy.run_path(str(V / 'm4_cross_scale_local_first_view_001/checks/assess_pairs.py'))
read, require, verified, write, digest, rows, ms, stage_ms = (prior[key] for key in (
    'read', 'require', 'verified', 'write', 'digest', 'rows', 'milliseconds', 'stage_ms'))
score = runpy.run_path(str(ASSEMBLY / 'scoring/score_live.py'))
typed = runpy.run_path(str(V / 'm4_cross_scale_live_task_formal_001/checks/typed_diagnostic.py'))
budget = runpy.run_path(str(V / 'm4_cross_scale_live_task_recovery_001/qualify.py'))
checker = runpy.run_path(str(V / 'm4_cross_scale_discovery_001/oracle/check_saved.py'))


def exact_request(value, include_image, detail):
    return value == {'query': {'mode': 'active_observation', 'region_task': {
        'area_min_m2': .025, 'area_max_m2': .05, 'normal_z_min': .75}},
        'include_image': include_image, 'response_detail': detail}


def audit_wire(slot, event, meter, audit, expected, detail, historical=None):
    """Use the installed original stdio wire, not the summary or a rerender."""
    request, receipt = event['request'], event['receipt']
    ident, ordinal = request['id'], event['index']
    require(request['method'] == 'tools/call' and request['params'] == {
        'arguments': expected, 'name': PRODUCT} and
        ident == receipt['id'] == meter['id'] == meter['response_id'] and receipt['error'] is None,
        'original_request_wrong_or_failed/' + detail)
    wire_dir = slot / 'mcp' / f"rpc_{receipt['index']:02d}"
    record = slot / 'product_calls' / f'call_{ordinal:03d}'
    tx_path, rx_path = wire_dir / 'TX.bin', wire_dir / 'RX.bin'
    tx, rx = tx_path.read_bytes(), rx_path.read_bytes()
    rx_lf = rx.replace(b'\r\n', b'\n')
    reply = json.loads(rx)
    require(digest(tx) == meter['TX_sha256'] and len(tx) == meter['TX_bytes'] == receipt['TX_bytes'] and
            json.loads(tx) == request == read(record / 'REQUEST.json') and
            digest(rx) == receipt['RX_sha256'] and len(rx) == receipt['RX_bytes'] and
            digest(rx_lf) == meter['RX_text_UTF8_LF_sha256'] and len(rx_lf) == meter['RX_text_UTF8_LF_bytes'] and
            read(wire_dir / 'RECEIPT.json') == receipt and
            reply == event['response'] == read(record / 'RESPONSE.json') and reply['id'] == ident and
            reply['result']['isError'] is False, 'mcp_wire_and_preserved_result_differ/' + detail)
    if detail == 'brief':
        public, texts, images = typed['verify_content'](reply, contract='active_region_task')
        require(len(texts) == len(images) == 1, 'expected_one_fact_body_and_one_original_png')
    else:
        block, = reply['result']['content']
        require(block['type'] == 'text', 'full_prediction_returned_non_text')
        public, images = json.loads(block['text']), []
    body = reply['result']['content'][0]['text'].encode()
    trace, = [row for row in audit if row['event'] == 'request_trace' and
              row['trace']['annotations'].get('mcp_request_id') == ident]
    relevant = [row for row in audit if row.get('request_id') == trace['request_id']]
    formatter, = [row['image_delivery'] for row in relevant if row['event'] == 'active_observation_mcp_content']
    attempts = [row for row in relevant if row['event'] == 'active_observation_render_attempt']
    png_bytes = sum(len(raw) for _, raw in images)
    require(formatter['projection_status'] == ('brief' if detail == 'brief' else 'full_requested') and
            formatter['public_text_bytes'] == len(body) and
            formatter['native_blocks_constructed'] == len(images) and formatter['PNG_bytes'] == png_bytes and
            len(attempts) == meter['raster_actual'] == (3 if images else 0) and
            all(row['identity_check']['compatible'] is True for row in relevant),
            'formatter_or_raster_audit_drift/' + detail)
    archive = event['producer_archive']
    require(archive['index'] == ordinal and archive['new_observations_for_archive'] == 0,
            'archive_is_not_the_actual_producer_return')
    producer_path = Path(archive['path'])
    producer_raw = verified(producer_path, archive['sha256'], slot)
    context_path = Path(archive['read_context']).resolve()
    require(context_path.is_relative_to(slot.resolve()), 'read_context_outside_owned_slot')
    context = read(context_path)
    if historical is not None:
        for path in (tx_path, rx_path, producer_path, context_path, record / 'REQUEST.json',
                     record / 'RESPONSE.json'):
            historical(path)
    timing = {'server_rpc_ms': ms(meter['request_received_ns'], meter['reply_completed_ns']),
              'client_rpc_ms': ms(receipt['started_ns'], receipt['closed_ns']),
              'caller_window_ms': ms(event['started_ns'], event['closed_ns']),
              'archive_producer_snapshot_ms': ms(archive['producer_returned_ns'], archive['saved_ns']),
              'public_formatter_ms': stage_ms(formatter),
              'selected_png_read_ms': sum(row['read_ns'] for row in formatter['frames']) / 1e6}
    cpu = context['after'].get('producer_window_cpu_ns')
    if cpu is not None:
        require(type(cpu) is int and cpu >= 0, 'invalid_installed_process_CPU_sample')
        timing['producer_cpu_ms'] = cpu / 1e6
    producer = json.loads(producer_raw)
    timing['producer_stages_ms'] = {k: stage_ms(v) for k, v in producer['stages'].items()}
    return {'public': public, 'images': images, 'producer': producer, 'context': context, 'timing': timing,
            'attempts': attempts, 'result': reply['result'],
            'wire': {'request_sha256': digest(tx), 'response_sha256': digest(rx), 'body_sha256': digest(body),
                     'body_bytes': len(body), 'PNG_bytes': png_bytes, 'rpc_bytes': len(rx),
                     'producer_sha256': digest(producer_raw), 'producer_archive_bytes': len(producer_raw),
                     'read_context_sha256': digest(context_path.read_bytes())}}


def current_geometry(slot, product, terminal, product_binding, truth):
    audit = checker['Audit']()
    captures, _ = checker['decode_captures'](slot, product_binding, audit)
    parent = product['binding']
    current = checker['current_capture'](captures, parent, audit)
    checker['source_binding_checks'](current, parent, product_binding, audit)
    objects = {item['name']: item for item in terminal['objects']}
    require(len(objects) == len(current['meshes']) == 28 and
            {mesh['name'] for mesh in current['meshes']} == objects.keys() and
            all(item['visible_get'] is True for item in objects.values()), 'current_ordered_scene_mismatch')
    for mesh in current['meshes']:
        source = objects[mesh['name']]
        require(mesh['object_id'] == source['object_id'] and
                current['host_identity']['object_instances'][mesh['object_id']] == source['instance_id'] and
                mesh['faces'] == source['evaluated']['triangles'] and
                mesh['vertices'] == source['evaluated']['vertices_world_m'],
                'captured_object_is_not_current/' + mesh['name'])
    expected = {row['object_name']: row for row in truth['eligible']}
    task = {entry['object_name']: entry for entry in product['facts']['region_task']['rows']}
    require(set(task) == set(expected) == set(ROW_OUTCOMES) and len(task) ==
            len(product['facts']['region_task']['rows']), 'current_region_roster_changed')
    for name, row in task.items():
        require(row['source'] == checker['source_row'](expected[name], current, parent),
                'current_region_row_source_mismatch/' + name)
        prior['same_geometry'](row, expected[name], objects[name], parent)
    return task, audit


def assess_cold(slot, observation, terminal, product_binding, truth, candidate, historical=None):
    public, product = observation['public'], observation['producer']
    parent = product['binding']
    require(public['schema'] == 'active-observation-region-task-brief-v1' and
            public['status'] == product['status'] == 'complete' and
            public['observation_status'] == product['observation_status'] == 'region_task_observed' and
            public['read_only'] is product['read_only'] is True and
            public['execution_authority'] is product['execution_authority'] is False and
            public['session_id'] == product['session_id'] and
            public['binding'] == {k: v for k, v in parent.items()
                                  if k not in ('schema', 'objects', 'camera_policy', 'camera_specification')},
            'brief_status_or_current_read_only_binding_changed')
    task, audit = current_geometry(slot, product, terminal, product_binding, truth)
    displayed = {row['object_name']: row for row in public['region_task']['rows']}
    require(len(displayed) == len(public['region_task']['rows']) == 3 and displayed.keys() == task.keys() and
            public['region_task']['summary'] == product['facts']['region_task']['summary'],
            'brief_row_roster_or_summary_drift')
    for name, row in displayed.items():
        original = dict(task[name])
        if original['complete_witness'] is not None:
            original['complete_witness'] = {**original['complete_witness'], 'native_content_block_index': 1}
        require((row['status'], row['reason']) == ROW_OUTCOMES[name] and
                {k: v for k, v in row.items() if k != 'pixel_shortfall'} == original and
                ('pixel_shortfall' in row) == (candidate and name == 'N10'),
                'brief_row_changed_beyond_one_bound_N10_shortfall/' + name)
    require(set(displayed['N11']['view_reasons']['positive_area_occlusion']) == set(truth['directions']) and
            displayed['N10']['complete_witness'] is displayed['N11']['complete_witness'] is None,
            'geometric_occlusion_claimed_as_a_readable_witness')
    scopes = {scope['scope_id']: scope for scope in product['scopes']}
    require(len(scopes) == len(product['scopes']) == 2 and scopes['global']['binding'] == parent,
            'unexpected_constructed_scope_roster')
    local, = [scope for key, scope in scopes.items() if key != 'global']
    checker['local_binding_checks'](local, parent, task['N10']['source'], audit)
    frames = product['constructed_frames']
    chosen, = product['frames']
    image, = observation['images']
    require([(frame['scope_id'], frame['view_name']) for frame in frames] ==
            [('global', 'SCENE'), ('global', 'TOP'), (local['scope_id'], 'TOP')] and chosen == frames[0] and
            [entry['view_name'] for entry in observation['attempts']] == ['SCENE', 'TOP', 'TOP'] and
            image[0]['ref'] == chosen['image_ref'] == displayed['N22']['complete_witness']['image_ref'],
            'constructed_or_delivered_frames_changed')
    checked = []
    for frame in frames:
        if historical is not None:
            historical(Path(frame['image_path']))
            historical(Path(frame['arrays_path']))
        scope = scopes[frame['scope_id']]
        require([item['frame_identity'] for item in scope['steps']] == scope['frame_refs'] ==
                [item['frame_identity'] for item in scope['facts']['observations']] ==
                [item['frame_identity'] for item in frames if item['scope_id'] == frame['scope_id']],
                'frame_or_observation_does_not_belong_to_scope')
        checked.append(prior['frame_payload'](slot, frame, scope, terminal, truth,
                                              image[1] if frame == chosen else None))
    require(checked[0]['independent_pixels']['N22'] == {
        'target_surface_pixels': 1489, 'contrasting_boundary_pixels': 546, 'qualifies': True},
        'original_N22_readable_witness_changed')
    first_probe, selected_probe = [item['independent_pixels']['N10'] for item in checked[1:]]
    require(first_probe == {'target_surface_pixels': 5026, 'contrasting_boundary_pixels': 0, 'qualifies': False} and
            selected_probe == {'target_surface_pixels': 8835, 'contrasting_boundary_pixels': 0, 'qualifies': False},
            'N10_current_RGB_or_source_owner_measurements_changed')
    shortfall = displayed['N10'].get('pixel_shortfall')
    if candidate:
        expected = {'scope_id': local['scope_id'], 'view_name': 'TOP', 'visible_surface_pixels': 8835,
                    'contrasting_boundary_pixels': 0, 'minimum_surface_pixels': 16,
                    'minimum_boundary_pixels': 4, 'minimum_rgb_boundary_contrast': 24,
                    'image_delivered': False, 'native_content_block_index': None}
        require(shortfall == expected and shortfall['image_delivered'] is False and
                shortfall['native_content_block_index'] is None, 'shortfall_not_the_one_actual_unselected_local_TOP')
        frame = frames[-1]
        probe, = local['facts']['observations']
        pixel, = [row for row in probe['pixel_rows'] if row['roi_id'] == task['N10']['roi_id']]
        evidence, = [row for row in local['facts']['region_evidence'] if row['roi_id'] == task['N10']['roi_id']]
        target, = [row for row in truth['eligible'] if row['object_name'] == 'N10']
        mesh, = [row for row in terminal['objects'] if row['name'] == 'N10']
        points = [mesh['evaluated']['vertices_world_m'][i] for i in target['vertex_indices']]
        require(probe['view_name'] == frame['view_name'] == 'TOP' and
                probe['frame_identity'] == frame['frame_identity'] and
                prior['in_frame'](frame['pose'], points, truth['directions']['TOP']) and
                target['eligible_complete_views'] == ['TOP'] and pixel['front_facing'] is True and
                pixel['readable'] is False and evidence['unobserved_reason'] == 'pixel_evidence_insufficient' and
                evidence['view_reasons']['pixel_evidence_insufficient'] == ['TOP'] and
                all(shortfall[k] == pixel[k] for k in expected if k in pixel),
                'shortfall_not_bound_to_a_geometrically_complete_ROI_and_measured_frame')
    work = product['work']
    require(work['raster_attempts'] == work['raster_completed'] == 3 and
            work['capture_calls'] == work['partition_calls'] == 1 and work['index_calls'] == 2 and
            work['global_index_cache_hit'] is work['result_cache_hit'] is False,
            'cold_raster_or_index_behavior_drift')
    required = {k: budget['compact'](public[k]) for k in ('binding', 'region_task', 'images', 'witness_pixels')}
    presentation = budget['consumer_budget'](observation['result'], required)
    require(presentation['passed'] and all(row['text_exact'] for row in presentation['stages']),
            'actual_brief_fact_or_image_lost_in_fixed_CLI_budget')
    return {'pixel_shortfall': shortfall, 'frames': checked, 'CLI_reconstruction': presentation,
            'same_generation_work': work}


def assess_prediction(observation, cold, terminal, binding, truth):
    public, product = observation['public'], observation['producer']
    parent = product['binding']
    expected_public = {k: v for k, v in product.items() if k not in ('steps', 'request_trace')}
    expected_public['binding'] = {k: v for k, v in parent.items() if k != 'camera_specification'}
    expected_public['image_delivery'] = {'local_verified_image_count': 0, 'mcp_content_constructed_image_count': 0,
        'consumer_read_status': 'unconfirmed', 'frame_reuses': 0, 'new_raster_attempts': 0, 'selected_image_count': 0}
    require(public == expected_public and product['status'] == 'predicted' and
            product['observation_status'] == 'prediction_only' and not any(product['image_delivery'].values()) and
            product['read_only'] is True and product['execution_authority'] is False and
            all(product[key] == [] for key in ('frames', 'constructed_frames', 'steps')) and
            product['session_id'] == cold['producer']['session_id'] and parent == cold['producer']['binding'],
            'full_prediction_projection_or_same_generation_drift')
    scope, = product['scopes']
    facts = product['facts']
    task = facts['region_task']
    work = product['work']
    require(scope['scope_id'] == 'global' and scope['binding'] == parent and
            scope['facts'] == {k: v for k, v in facts.items() if k != 'region_task'} and
            all(scope[key] == [] for key in ('frame_refs', 'skipped_views', 'steps')) and
            facts['coverage']['state_updates'] == 0 and
            facts['observations'] == facts['coverage']['observed_views'] == facts['coverage']['covered_roi_ids'] == [] and
            facts['inspection']['state'] == 'prediction_only' and
            task['summary']['observed_region_count'] == task['summary']['selected_image_count'] ==
            task['summary']['constructed_image_count'] == 0 and
            task['summary']['eligible_region_count'] == task['summary']['unknown_region_count'] == 3 and
            work['global_index_cache_hit'] is True and work['result_cache_hit'] is False and
            work['capture_calls'] == work['geometry_parse_calls'] == work['mesh_conversions'] == work['camera_calls'] == 1 and
            all(work[key] == 0 for key in ('raster_attempts', 'raster_completed', 'index_calls', 'partition_calls',
                'prepare_calls', 'frame_reuses', 'local_verified_images', 'local_camera_calls', 'PNG_bytes', 'NPZ_bytes'))
            and 'index_global' not in product['stages'], 'full_prediction_leaked_observations_or_rebuilt_preparation')
    expected = {row['object_name']: row for row in truth['eligible']}
    objects = {row['name']: row for row in terminal['objects']}
    require(len(task['rows']) == 3 and {r['object_name'] for r in task['rows']} == set(expected),
            'full_prediction_region_roster_changed')
    for row in task['rows']:
        name = row['object_name']
        prior['same_geometry'](row, expected[name], objects[name], parent)
        require(row['status'] == 'unknown' and row['complete_witness'] is None and 'pixel_shortfall' not in row and
                row['reason'] == (ROW_OUTCOMES['N11'][1] if name == 'N11' else 'unobserved_geometric_candidates') and
                row['view_reasons'].get('unobserved_geometric_candidate', []) ==
                expected[name]['eligible_complete_views'], 'full_prediction_row_has_actual_evidence/' + name)
    return work


def normalized_public(observation, cold):
    """Replace only verified worker-local identifiers, retaining actual result fields."""
    result = deepcopy(observation['public'])
    producer = observation['producer']
    identifiers = {producer['session_id']: '@session'}
    for count, scope in enumerate(producer['scopes']):
        if scope['scope_id'] != 'global':
            identifiers[scope['scope_id']] = f'@scope{count}'
        for key in ('binding_sha256', 'source_binding_sha256', 'document_epoch', 'scene_revision',
                    'runtime_source_sha256'):
            if key in scope['binding']:
                identifiers.setdefault(scope['binding'][key], f'@scope{count}.{key}')
    for count, frame in enumerate(producer['constructed_frames']):
        identifiers[frame['frame_identity']] = f'@frame{count}'
        identifiers[frame['image_ref']] = f'@image{count}'
    for row in result.get('region_task', {}).get('rows', []):
        row.pop('pixel_shortfall', None)
    if not cold:
        for key in ('stages', 'generation_stages'):
            result.pop(key)

    def normalize(value):
        if isinstance(value, str):
            return identifiers.get(value, value)
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {k: '@validated_capture_state' if k == 'capture_state' else normalize(v)
                    for k, v in value.items()}
        return value

    return normalize(result)


def archived_verifier():
    index_path = ASSEMBLY / 'RUNTIME_INDEX.json'
    index = read(index_path)
    original = Path(index['archive']['path'])
    require(original.resolve() == (ARCHIVED_RUN / 'ORIGINAL_RUNTIME.zip').resolve() and
            digest(original.read_bytes()) == index['archive']['sha256'] == OLD_ARCHIVE_SHA,
            'historical_assembly_runtime_archive_changed')
    pins = {row['path']: row for row in index['files']}
    require(len(pins) == index['count'], 'historical_archive_has_duplicate_paths')

    def verify_path(path):
        key = path.resolve().relative_to(ARCHIVED_RUN.resolve()).as_posix()
        pin = pins[key]
        raw = verified(path, pin['sha256'], ARCHIVED_RUN)
        require(len(raw) == pin['bytes'], 'historical_runtime_byte_count_changed/' + key)
        return raw

    return verify_path


def inspect_slot(slot, requests, truth, installed, historical=None):
    if historical is not None:
        for name in ('SLOT_STARTED.json', 'SLOT_RESULT.json', 'SLOT_PUBLICATION.json', 'MCP_IDENTITY.json',
                     'PUBLIC_REQUESTS.jsonl', 'mcp_io/MCP_IO.jsonl', 'product_audit.jsonl'):
            historical(slot / name)
    source = installed['source_sha256']
    result_path = slot / 'SLOT_RESULT.json'
    result, published, started = [read(slot / name) for name in
                                   ('SLOT_RESULT.json', 'SLOT_PUBLICATION.json', 'SLOT_STARTED.json')]
    require(result['status'] == published['status'] == 'completed' and not result['errors'] and
            published['owned_budget_passed'] is True and published['result_sha256'] == digest(result_path.read_bytes())
            and all(item['label'] == slot.name for item in (result, published, started)),
            'live_or_archived_slot_did_not_complete')
    if historical is None:
        freeze = digest((NS / 'FROZEN.json').read_bytes())
        require(started['freeze_sha256'] == result['freeze_sha256'] == freeze and
                result['model_consumers'] == 0 and not (slot / 'consumer').exists() and
                result['paid_API_calls'] == 0 and
                result['task_deadline_ns'] - result['started_ns'] == 450_000_000_000 and
                result['owned_deadline_ns'] - result['started_ns'] == 600_000_000_000,
                'slot_not_the_frozen_zero_model_owned_run')
    identity = read(slot / 'MCP_IDENTITY.json')
    ready = read(slot / 'RUNTIME_READY.json')
    require(identity['source_sha256'] == ready['product_source_sha256'] == source and
            identity['source_kind'] == 'installed_distribution' and identity['source_file_count'] ==
            len(installed['source_manifest']) == 143 and
            result['asset_sha256'] == truth['asset_sha256'], 'actual_installed_product_or_original_assembly_changed')
    terminal, closure = score['bound_terminal'](slot, result, truth['asset_sha256'])
    runtime_close = read(slot / 'RUNTIME_CLOSE.json')
    exit_receipt = runtime_close['public_MCP_exit']
    require(not runtime_close['errors'] and exit_receipt['exited'] and exit_receipt['confirmed'] and
            exit_receipt['handle_closed'] and exit_receipt['exit_code'] == 0, 'actual_mcp_unclean_close')
    events = rows(slot / 'PUBLIC_REQUESTS.jsonl')
    meters = [row for row in rows(slot / 'mcp_io/MCP_IO.jsonl') if row['method'] == 'tools/call']
    require(len(events) == len(meters) == 2 and [item['index'] for item in events] == [1, 2],
            'not_two_original_installed_requests')
    clock = [result['ready_ns'], *(ts for event in events for ts in (event['started_ns'], event['closed_ns'])),
             min(result['task_deadline_ns'], result['cleanup_started_ns']), published['published_ns'],
             result['owned_deadline_ns']]
    require(clock == sorted(clock), 'owned_request_clocks_outside_frozen_deadlines')
    audit = rows(slot / 'product_audit.jsonl')
    cold, prediction = [audit_wire(slot, event, meter, audit, request, detail, historical) for
                        event, meter, request, detail in zip(events, meters, requests, ('brief', 'full'), strict=True)]
    proved = assess_cold(slot, cold, terminal, installed, truth, historical is None, historical)
    require(all(phase['producer']['binding']['runtime_source_sha256'] == source for phase in (cold, prediction)),
            'product_source_changed_inside_request')
    full_work = assess_prediction(prediction, cold, terminal, installed, truth)
    if historical is None:
        ledger = result['budget']
        counts = ledger['counts']
        claims = [r['claim']['kind'] for r in ledger['records'] if r['claim']['label'] == slot.name]
        require(len(ledger['slots']) == 1 and counts['Blender_start_attempts'] == claims.count('Blender_start') == 1 and
                counts['all_raster_actual'] == counts['all_raster_upper'] == 3 and
                counts['business_admissions'] == claims.count('business_tool') == 2 and
                counts['consumer_admissions'] == claims.count('consumer_task') == 0,
                'live_actual_attempt_denominator_exceeded')
    return cold, prediction, proved, full_work, {
        'owned_window_ms': ms(result['started_ns'], published['published_ns']),
        'ready_ms': ms(result['started_ns'], result['ready_ns']),
        'request_sequence_ms': ms(events[0]['started_ns'], events[-1]['closed_ns']),
        'final_request_to_publish_ms': ms(events[-1]['closed_ns'], published['published_ns']),
        'current_source': closure, 'slot_result_sha256': digest(result_path.read_bytes()),
        'publication_sha256': digest((slot / 'SLOT_PUBLICATION.json').read_bytes()),
        'installed_source_sha256': source, 'model_consumers': result['model_consumers']}


def assess(runtime, request, prediction):
    require(exact_request(request, True, 'brief') and exact_request(prediction, False, 'full'),
            'the_two_requests_are_not_the_frozen_assembly_task')
    installed = read(NS / 'install/PRODUCT_RUN_BINDING.json')
    original = read(OLD_BINDING)
    require(original['source_sha256'] == OLD_SOURCE != installed['source_sha256'] and
            original['dependency_root'] == installed['dependency_root'] and
            installed['historical_source_sha256'] == OLD_SOURCE and
            read(NS / 'install/TOOLS_SCHEMA.json') ==
            read(V / 'm4_cross_scale_cold_frustum_001/install/TOOLS_SCHEMA.json'),
            'baseline_candidate_scope_or_tool_schema_changed')
    sys.path.insert(0, installed['dependency_root'])
    truth = json.loads(verified(TRUTH, TRUTH_SHA, ASSEMBLY))
    requests = (request, prediction)
    old_cold, old_full, old_proof, old_full_work, old_window = inspect_slot(
        ARCHIVED_RUN / 'slots/P1', requests, truth, original, archived_verifier())
    cold, full, proof, full_work, window = inspect_slot(runtime / 'slots/P1', requests, truth, installed)
    for old, new, is_cold in ((old_cold, cold, True), (old_full, full, False)):
        require(normalized_public(old, is_cold) == normalized_public(new, is_cold),
                'public_packet_changed_beyond_shortfall_and_named_worker_local_metadata')
    for old, new in ((old_proof['same_generation_work'], proof['same_generation_work']),
                     (old_full_work, full_work)):
        require({k: v for k, v in old.items() if k != 'frustum_proof_ns'} ==
                {k: v for k, v in new.items() if k != 'frustum_proof_ns'}, 'engine_work_changed')
    keys = ('view', 'object_name', 'image_sha256', 'NPZ_sha256', 'png_bytes', 'npz_bytes', 'independent_pixels')
    require([item[1] for item in cold['images']] == [item[1] for item in old_cold['images']] and
            all(all(left[k] == right[k] for k in keys)
                for left, right in zip(old_proof['frames'], proof['frames'], strict=True)),
            'archived_and_actual_PNG_NPZ_or_pixel_evidence_differ')
    phase = lambda observation: {key: observation[key] for key in ('timing', 'wire')}
    return {'schema': 'm4-cross-scale-pixel-evidence-live-v1', 'passed': True,
            'product_difference': 'N10 one bound pixel_shortfall', 'registered_live_slots': 1,
            'business_requests': 2, 'raster_attempts': 3, 'actual_live_models': 0,
            'fixed_asset_sha256': truth['asset_sha256'], 'independent_truth_sha256': TRUTH_SHA,
            'historical_original_archive_sha256': OLD_ARCHIVE_SHA, 'observed': window,
            'historical_reference_only': old_window, 'cold': phase(cold), 'no_image_full': phase(full),
            'historical_cold': phase(old_cold), 'historical_full': phase(old_full),
            'cold_body_UTF8_bytes_added': cold['wire']['body_bytes'] - old_cold['wire']['body_bytes'],
            'full_body_UTF8_bytes_delta': full['wire']['body_bytes'] - old_full['wire']['body_bytes'],
            'live_full_global_index_reused': full_work['global_index_cache_hit'],
            'original_PNG_and_NPZ_unchanged': True, 'normalized_full_projection_unchanged': True, **proof}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--output', type=Path, default=HERE / 'LIVE_REVIEW.json')
    args = parser.parse_args()
    try:
        outcome = assess(args.runtime, read(NS / 'inputs/REQUEST.json'), read(NS / 'inputs/PREDICTION.json'))
    except Exception as error:
        outcome = {'schema': 'm4-cross-scale-pixel-evidence-live-v1', 'passed': False,
                   'runtime': str(args.runtime), 'error_type': type(error).__name__, 'error': str(error)}
    write(args.output, outcome)
    print(json.dumps({key: outcome[key] for key in ('passed', 'cold_body_UTF8_bytes_added',
        'full_body_UTF8_bytes_delta', 'error_type', 'error') if key in outcome}, ensure_ascii=False))
    return 0 if outcome['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
