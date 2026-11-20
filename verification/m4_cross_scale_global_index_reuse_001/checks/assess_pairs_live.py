"""Independently reconcile paired three-request sequences with original MCP receipts."""

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from statistics import median
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
PREVIOUS = NS.parent / 'm4_cross_scale_local_first_view_001'
RUN = Path('D:/he_m4_cross_scale_global_index_reuse_001')
BASELINE = PREVIOUS / 'install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS / 'install/PRODUCT_RUN_BINDING.json'
BASELINE_SHA = '58c310d53abbf6ceac9a7c5273fc3119ffbedc1b632b27eb8c49988ca90a7d33'
PHASES = ('cold', 'prediction', 'hot')
CURRENT_BINDING_FIELDS = ('binding_sha256', 'source_binding_sha256', 'runtime_source_sha256',
                          'capture_state', 'document_epoch', 'scene_revision')
INDEX_WORK = {'index_calls', 'partition_calls', 'prepare_calls', 'global_index_cache_hit'}

spec = importlib.util.spec_from_file_location('_retained_local_first_assessor', PREVIOUS / 'checks/assess_pairs.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
from formal import read, require, terminal, verified, write


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(',', ':')).encode()


def audit_prediction(slot, event, meter, audit, request):
    """Bind the text-only wire to the exact archived installed call and producer."""
    ident = event['request']['id']
    receipt = event['receipt']
    require(event['request']['method'] == 'tools/call' and
            event['request']['params'] == {'arguments': request, 'name': prior.PRODUCT} and
            receipt['id'] == meter['response_id'] == ident and receipt['error'] is None,
            'wrong_or_failed_full_prediction_request')
    rpc = slot / 'mcp' / f"rpc_{receipt['index']:02d}"
    original = slot / 'product_calls/call_002'
    tx, rx = (rpc / 'TX.bin').read_bytes(), (rpc / 'RX.bin').read_bytes()
    lf = rx.replace(b'\r\n', b'\n')
    require(prior.digest(tx) == meter['TX_sha256'] and len(tx) == meter['TX_bytes'] == receipt['TX_bytes'] and
            json.loads(tx) == read(original / 'REQUEST.json') == event['request'],
            'full_prediction_request_wire_drift')
    reply = json.loads(rx)
    require(prior.digest(rx) == receipt['RX_sha256'] and len(rx) == receipt['RX_bytes'] and
            prior.digest(lf) == meter['RX_text_UTF8_LF_sha256'] and len(lf) == meter['RX_text_UTF8_LF_bytes'] and
            reply == read(original / 'RESPONSE.json') == event['response'] and reply['id'] == ident and
            reply['result']['isError'] is False, 'full_prediction_response_wire_drift')
    block, = reply['result']['content']
    require(block['type'] == 'text', 'prediction_delivered_non_text_evidence')
    raw_text = block['text'].encode()
    trace, = [row for row in audit if row['event'] == 'request_trace' and
              row['trace']['annotations'].get('mcp_request_id') == ident]
    relevant = [row for row in audit if row.get('request_id') == trace['request_id']]
    formatter, = [row['image_delivery'] for row in relevant if row['event'] == 'active_observation_mcp_content']
    require(formatter['projection_status'] == 'full_requested' and formatter['native_blocks_constructed'] == 0 and
            formatter['public_text_bytes'] == len(raw_text) and formatter['PNG_bytes'] == meter['raster_actual'] == 0 and
            formatter['frames'] == [] and all(row['identity_check']['compatible'] is True for row in relevant) and
            not any(row['event'] == 'active_observation_render_attempt' for row in relevant),
            'full_prediction_generated_or_delivered_observation')
    archive = event['producer_archive']
    require(archive['index'] == 2 and archive['new_observations_for_archive'] == 0,
            'prediction_archive_did_not_retain_same_producer_result')
    raw = verified(archive['path'], archive['sha256'], slot)
    context_path = Path(archive['read_context']).resolve()
    require(context_path.is_relative_to(slot.resolve()), 'prediction_read_context_outside_slot')
    context_raw = context_path.read_bytes()
    public, producer = json.loads(raw_text), json.loads(raw)
    timing = {'server_rpc_ms': prior.milliseconds(meter['request_received_ns'], meter['reply_completed_ns']),
              'client_rpc_ms': prior.milliseconds(receipt['started_ns'], receipt['closed_ns']),
              'caller_window_ms': prior.milliseconds(event['started_ns'], event['closed_ns']),
              'public_formatter_ms': prior.stage_ms(formatter),
              'archive_producer_snapshot_ms': prior.milliseconds(archive['producer_returned_ns'], archive['saved_ns'])}
    wire = {'request_id': ident, 'wire_request_sha256': prior.digest(tx), 'wire_response_sha256': prior.digest(rx),
            'public_body_sha256': prior.digest(raw_text), 'producer_archive_sha256': prior.digest(raw),
            'read_context_sha256': prior.digest(context_raw), 'rpc_bytes': len(rx), 'public_text_bytes': len(raw_text),
            'public_png_bytes': 0, 'producer_archive_bytes': len(raw)}
    return public, producer, timing, wire


def normalize_prediction(public):
    """Remove only validated process-local binding and measured timing/work fields."""
    normalized = deepcopy(public)
    for key in ('session_id', 'stages', 'generation_stages', 'work', 'generation_work'):
        normalized.pop(key)
    for binding in (normalized['binding'], normalized['scopes'][0]['binding']):
        for key in CURRENT_BINDING_FIELDS:
            binding.pop(key)
    for row in normalized['facts']['region_task']['rows']:
        source = row['source']
        for key in ('capture_state', 'document_epoch', 'scene_revision', 'parent_binding_sha256',
                    'parent_source_binding_sha256'):
            source.pop(key)
    return normalized


def assess_prediction(slot, event, meter, audit, request, truth, terminal_source, arm, source_sha):
    public, product, timing, wire = audit_prediction(slot, event, meter, audit, request)
    binding = product['binding']
    require(binding['capture_scope'] == 'complete_scene_meshes' and binding['runtime_source_sha256'] == source_sha and
            product['read_only'] is True and product['execution_authority'] is False and
            product['status'] == 'predicted' and product['observation_status'] == 'prediction_only'
            and product['result_kind'] == 'active_observation', 'prediction_scope_status_or_current_product_drift')
    expected_delivery = {'local_verified_image_count': 0, 'mcp_content_constructed_image_count': 0,
                         'consumer_read_status': 'unconfirmed', 'frame_reuses': 0,
                         'new_raster_attempts': 0, 'selected_image_count': 0}
    expected_public = {k: v for k, v in product.items() if k not in ('steps', 'request_trace')}
    expected_public['binding'] = {k: v for k, v in binding.items() if k != 'camera_specification'}
    expected_public['image_delivery'] = expected_delivery
    require(public == expected_public, 'original_full_public_projection_disagrees_with_producer')
    require(all(product[k] == [] for k in ('frames', 'constructed_frames', 'steps')) and
            not any(product['image_delivery'].values()), 'prediction_contains_actual_frames')
    scope, = product['scopes']
    facts = product['facts']
    require(scope['scope_id'] == 'global' and scope['binding'] == binding and
            scope['facts'] == {k: v for k, v in facts.items() if k != 'region_task'} and
            all(scope[k] == [] for k in ('frame_refs', 'skipped_views', 'steps')) and
            facts['coverage']['state_updates'] == 0 and facts['observations'] == [] and
            facts['coverage']['observed_views'] == facts['coverage']['covered_roi_ids'] == [] and
            facts['inspection']['state'] == 'prediction_only' and
            facts['inspection']['stop_reason'] == 'actual_observation_required',
            'prediction_inherited_actual_observation_state')
    current = {row['name']: row for row in terminal_source['objects']}
    prior.binding_objects(binding, current)
    task = facts['region_task']
    require(task['conditions'] == request['query']['region_task'] and
            task['summary'] == {'constructed_image_count': 0, 'eligible_region_count': 3,
                'external_consumer_verified': False, 'observed_region_count': 0, 'selected_image_count': 0,
                'source_triangle_count': 184, 'supported_region_count': 84, 'supported_triangle_count': 168,
                'unknown_region_count': 3, 'unsupported_triangle_count': 16}
            and len(facts['coverage']['unresolved_roi_ids']) == len(facts['regions']) == 84
            and len(task['rows']) == 3, 'prediction_denominators_changed')
    expected = {row['object_name']: row for row in truth['eligible']}
    require({row['object_name'] for row in task['rows']} == set(expected), 'prediction_region_roster_changed')
    geometry = {}
    for row in task['rows']:
        name = row['object_name']
        ref = expected[name]
        reason = ref['expected_unknown_reason'] if name == 'M06' else 'unobserved_geometric_candidates'
        require(row['status'] == 'unknown' and row['reason'] == reason and row['complete_witness'] is None and
                row['view_reasons'].get('unobserved_geometric_candidate', []) == ref['eligible_complete_views'] and
                set().union(*map(set, row['view_reasons'].values())) == set(truth['directions']),
                'prediction_coverage_reasons_or_witness_changed/' + name)
        geometry[name] = prior.same_geometry(row, ref, current[name], binding)
    work = product['work']
    builds = int(arm == 'A')
    require(work['result_cache_hit'] is False and work['capture_calls'] == work['geometry_parse_calls'] ==
            work['mesh_conversions'] == work['camera_calls'] == 1 and
            work['index_calls'] == work['partition_calls'] == builds and
            (work.get('global_index_cache_hit') is True if arm == 'B' else 'global_index_cache_hit' not in work) and
            all(work[k] == 0 for k in ('raster_attempts', 'raster_completed', 'frame_reuses', 'PNG_bytes', 'NPZ_bytes',
                'array_payload_bytes', 'local_verified_images', 'local_camera_calls')),
            'prediction_did_not_reuse_only_the_registered_preparation')
    require(product['generation_work'] == {k: v for k, v in work.items()
            if k not in ('capture_calls', 'frame_reuses', 'result_cache_hit')} and
            product['generation_stages'] == {k: v for k, v in product['stages'].items()
            if k not in ('host_capture', 'result_lookup', 'service_total')},
            'prediction_exposes_old_generation_work_or_stages')
    stages = {key: prior.stage_ms(value) for key, value in product['stages'].items()}
    require(('index_global' in stages) == ('partition' in stages) == bool(builds) and
            not any(k.startswith(('index_local', 'render_and_publish_', 'feedback_')) for k in stages),
            'prediction_stage_counters_disagree_with_actual_index_work')
    timing.update(service_ms=stages['service_total'], capture_ms=stages['host_capture'],
                  global_index_ms=stages.get('index_global', 0), partition_ms=stages.get('partition', 0),
                  prepare_ms=stages.get('prepare', 0), scoped_stages_ms=stages)
    return {'status': product['status'], 'global_index_builds': builds, 'frame_count': 0,
            'same_generation_index_reuse': not builds, 'work': work, 'timing': timing, 'wire': wire,
            'geometry': geometry, 'normalized_full_sha256': prior.digest(canonical(normalize_prediction(public))),
            'session_id': product['session_id'], 'source_binding': binding['source_binding_sha256'],
            'geometry_identity': binding['geometry_identity'], 'camera_identity': binding['camera_identity'],
            'capture_state': binding['capture_state']}


def original_images(slot, call):
    packet = read(slot / 'product_calls' / f'call_{call:03d}' / 'RESPONSE.json')
    return [block['data'] for block in packet['result']['content'][1:]]


def read_contexts(slot, events, observations):
    contexts = []
    for event, observation in zip(events, observations, strict=True):
        path = Path(event['producer_archive']['read_context']).resolve()
        context = json.loads(verified(path, observation['wire']['read_context_sha256'], slot))
        cpu = context['after']['producer_window_cpu_ns']
        require(type(cpu) is int and cpu >= 0, 'missing_actual_installed_producer_cpu_time')
        observation['timing']['producer_cpu_ms'] = cpu / 1e6
        contexts.append(context)
    return contexts


def index_resource(contexts, arm, prediction):
    snapshots = [context[side]['region_task_global_indexes'] for context in contexts for side in ('before', 'after')]
    require(all(type(items) is list for items in snapshots), 'missing_live_index_resource_receipt')
    if arm == 'A':
        require(snapshots == [[] for _ in snapshots], 'baseline_unregistered_retained_index_resource')
        return {'count': 0}
    require(snapshots[0] == [] and all(len(items) == 1 for items in snapshots[1:]),
            'candidate_does_not_keep_exactly_one_same_selection_index')
    states = [items[0] for items in snapshots[1:]]
    registered = states[0]
    require(all('python_graph' not in state for state in states[:-1]) and
            all({k: v for k, v in state.items() if k != 'python_graph'} == registered for state in states) and
            type(registered['python_id']) is int and registered['python_id'] > 0 and
            registered['scene_identity'] == prediction['geometry_identity'] and
            registered['camera_identity'] == prediction['camera_identity'] and
            registered['type'].rsplit('.', 1)[-1] == 'CoverageIndex' and
            (registered['regions'], registered['views'], registered['partition_rows']) == (84, 6, 21) and
            registered['selection_repr'] == contexts[1]['after']['active_selection_repr'],
            'live_global_index_identity_or_selection_drift')
    sample = states[-1]['python_graph']
    measure = {k: sample[k] for k in ('bytes', 'objects', 'wall_ns', 'cpu_ns')}
    require(set(sample) == set(measure) | {'scope'} and type(sample['scope']) is str and
            all(type(value) is int and value >= 0 for value in measure.values()) and
            measure['objects'] > 0 and measure['bytes'] > 0 and measure['wall_ns'] > 0,
            'actual_retained_index_size_missing_or_malformed')
    return {'count': 1, 'identity': registered, 'python_graph': measure,
            'scope': sample['scope']}


def assess_slot(slot, label, requests, truth, installed, freeze_sha):
    path = slot / 'SLOT_RESULT.json'
    outcome_raw = path.read_bytes()
    outcome = json.loads(outcome_raw)
    started = read(slot / 'SLOT_STARTED.json')
    pub_path = slot / 'SLOT_PUBLICATION.json'
    publication = read(pub_path)
    arm = label[0]
    require(outcome['status'] == publication['status'] == 'completed' and not outcome['errors'] and
            publication['owned_budget_passed'] is True and publication['result_sha256'] == prior.digest(outcome_raw)
            and all(row['label'] == label for row in (outcome, started, publication)) and
            all(row['freeze_sha256'] == freeze_sha for row in (outcome, started)),
            'original_owned_slot_admission_or_publication_mismatch')
    require(outcome['arm'] == started['arm'] == arm and outcome['model_consumers'] == outcome['paid_API_calls'] == 0 and
            not (slot / 'consumer').exists() and outcome['asset_sha256'] == truth['asset_sha256'] and
            outcome['task_deadline_ns'] - outcome['started_ns'] == 450_000_000_000 and
            outcome['owned_deadline_ns'] - outcome['started_ns'] == 600_000_000_000,
            'wrong_arm_model_asset_or_owned_deadlines')
    asset = Path(truth['asset_path'])
    source_sha = installed[arm]['source_sha256']
    identity = read(slot / 'MCP_IDENTITY.json')
    ready = read(slot / 'RUNTIME_READY.json')
    require(ready['product_source_sha256'] == identity['source_sha256'] == outcome['product_source_sha256'] ==
            source_sha and identity['source_kind'] == 'installed_distribution' and
            identity['source_file_count'] == 143 and len(installed[arm]['source_manifest']) == 143 and
            asset.read_bytes() == (slot / 'native/input.blend').read_bytes(), 'wrong_actual_install_or_asset_copy')
    closure = read(slot / 'RUNTIME_CLOSE.json')
    exit_receipt = closure['public_MCP_exit']
    require(not closure['errors'] and exit_receipt['confirmed'] and exit_receipt['exited'] and
            exit_receipt['handle_closed'] and exit_receipt['exit_code'] == 0, 'installed_mcp_did_not_close_cleanly')
    terminal_source, native = terminal(slot, outcome, truth['asset_sha256'])

    events = prior.rows(slot / 'PUBLIC_REQUESTS.jsonl')
    calls = [r for r in prior.rows(slot / 'mcp_io/MCP_IO.jsonl') if r['method'] == 'tools/call']
    require(len(events) == len(calls) == 3 and [row['index'] for row in events] == [1, 2, 3]
            and [r['request']['id'] for r in events] == [r['id'] for r in calls]
            and len({r['id'] for r in calls}) == 3, 'exact_three_registered_original_requests_required')
    clock = [outcome['ready_ns'], *(mark for row in events for mark in (row['started_ns'], row['closed_ns'])),
             min(outcome['task_deadline_ns'], outcome['cleanup_started_ns']),
             publication['published_ns'], outcome['owned_deadline_ns']]
    require(clock == sorted(clock), 'owned_process_or_request_window_not_closed')
    audit = prior.rows(slot / 'product_audit.jsonl')
    cold = prior.assess_call(slot, events[0], calls[0], audit, requests[0], truth, terminal_source,
                             source_sha, 'B', hot=False)
    prediction = assess_prediction(slot, events[1], calls[1], audit, requests[1], truth, terminal_source, arm, source_sha)
    hot = prior.assess_call(slot, events[2], calls[2], audit, requests[0], truth, terminal_source,
                            source_sha, 'B', hot=True)
    require(all(cold[key] == prediction[key] == hot[key] for key in ('session_id', 'capture_state', 'source_binding'))
            and all(cold[key] == hot[key] for key in ('geometry', 'selected_frame_ids', 'selected', 'frames')) and
            original_images(slot, 1) == original_images(slot, 3),
            'same_generation_or_hot_selected_originals_drifted')
    for row, expected_builds in ((cold, 1), (hot, 0)):
        stages = row['timing']['scoped_stages_ms']
        require(('index_global' in stages) == bool(expected_builds) and
                row['work']['partition_calls'] == expected_builds and not row['work'].get('global_index_cache_hit'),
                'cold_or_hot_index_evidence_disagreement')
        row['global_index_builds'] = expected_builds
    contexts = read_contexts(slot, events, (cold, prediction, hot))
    retained_index = index_resource(contexts, arm, prediction)
    budget = outcome['budget']
    entry = budget['slots'][label]
    claims = [x['claim']['kind'] for x in budget['records'] if x['claim']['label'] == label]
    require(entry['business_admissions'] == claims.count('business_tool') == 3 and
            entry['raster_actual'] == entry['raster_upper'] == cold['new_constructed'] == 3 and
            claims.count('Blender_start') == 1 and claims.count('consumer_task') == 0,
            'retained_attempt_budget_differs_from_verified_observations')
    owned_ms = prior.milliseconds(outcome['started_ns'], publication['published_ns'])
    phases = {'cold': cold, 'prediction': prediction, 'hot': hot}
    return {'label': label, 'arm': arm, 'status': 'completed', 'passed': True, 'source_sha256': source_sha,
            'product_distribution_version': identity['distribution_version'], 'native_PID': ready['native_pid'],
            'product_PID': ready['product_PID'], 'slot_result_sha256': prior.digest(outcome_raw),
            'publication_sha256': prior.digest(pub_path.read_bytes()), 'native': native, 'business_attempts': 3,
            'raster_attempts': entry['raster_actual'], 'owned_window_ms': owned_ms,
            'owned_awake_window': [outcome['started_ns'], publication['published_ns']],
            'startup_to_ready_ms': prior.milliseconds(outcome['started_ns'], outcome['ready_ns']),
            'finished_last_request_to_publication_ms':
                prior.milliseconds(events[2]['closed_ns'], publication['published_ns']),
            'sequence_window_ms': prior.milliseconds(events[0]['started_ns'], events[2]['closed_ns']),
            'sequence_rpc_sum_ms': sum(row['timing']['server_rpc_ms'] for row in phases.values()),
            'retained_global_index': retained_index,
            'sequence_global_index_builds': sum(row['global_index_builds'] for row in phases.values()), **phases}


def compare_pair(run, baseline, candidate):
    a, b = baseline['label'], candidate['label']
    slot_a, slot_b = run / 'slots' / a, run / 'slots' / b
    for i, phase in ((1, 'cold'), (3, 'hot')):
        first, second = baseline[phase], candidate[phase]
        keys = ('view', 'object_name', 'image_sha256', 'png_bytes', 'camera_sha256', 'independent_pixels')
        require(first['geometry'] == second['geometry'] and
                original_images(slot_a, i) == original_images(slot_b, i) and
                all(all(x[k] == y[k] for k in keys) for x, y in zip(first['selected'], second['selected'], strict=True)),
                'paired_current_geometry_or_decoded_original_images_changed/' + phase)
    first, second = baseline['prediction'], candidate['prediction']
    require(first['geometry'] == second['geometry'] and
            first['normalized_full_sha256'] == second['normalized_full_sha256'] and
            {k: v for k, v in first['work'].items() if k not in INDEX_WORK} ==
            {k: v for k, v in second['work'].items() if k not in INDEX_WORK},
            'normalized_full_prediction_or_unchanged_work_disagrees')
    builds = [baseline['sequence_global_index_builds'], candidate['sequence_global_index_builds']]
    require(builds == [2, 1], 'paired_global_index_reuse_not_demonstrated')
    changes = {}
    byte_changes = {}
    for phase in PHASES:
        first, second = baseline[phase], candidate[phase]
        changes[phase] = {k: second['timing'][k] - v for k, v in first['timing'].items() if k.endswith('_ms') and k != 'scoped_stages_ms'}
        byte_changes[phase] = {k: second['wire'][k] - first['wire'][k] for k in
                               ('rpc_bytes', 'public_text_bytes', 'public_png_bytes', 'producer_archive_bytes')}
    return {'A': a, 'B': b, 'passed': True, 'sequence_global_index_builds_A_B': builds,
            'prediction_normalized_full_sha256': baseline['prediction']['normalized_full_sha256'],
            'selected_PNG_hashes': baseline['cold']['wire']['public_png_hashes'],
            'sequence_window_A_B_ms': [baseline['sequence_window_ms'], candidate['sequence_window_ms']],
            'owned_window_A_B_ms': [baseline['owned_window_ms'], candidate['owned_window_ms']],
            'timing_candidate_minus_baseline_ms': changes, 'byte_candidate_minus_baseline': byte_changes,
            **{f'{key}_candidate_minus_baseline_ms': candidate[f'{key}_ms'] - baseline[f'{key}_ms']
               for key in ('sequence_window', 'sequence_rpc_sum', 'owned_window')}}


def assess(run, request_path, prediction_path, pair_count):
    truth_path = prior.FORMAL / 'fixture/CURRENT_TRUTH.json'
    truth = json.loads(verified(truth_path, prior.TRUTH_SHA256, prior.FORMAL))
    request, prediction = read(request_path), read(prediction_path)
    query = {'mode': 'active_observation', 'region_task': {
        'area_min_m2': 0.0078125, 'area_max_m2': 0.03125, 'normal_z_min': 0.75}}
    require(request == {'include_image': True, 'response_detail': 'brief', 'query': query} and
            prediction == {'include_image': False, 'response_detail': 'full', 'query': query},
            'registered_exact_request_forms_required')
    installed = {'A': read(BASELINE), 'B': read(CANDIDATE)}
    require(installed['A']['source_sha256'] == BASELINE_SHA != installed['B']['source_sha256'],
            'registered_isolated_arm_sources_required')
    sys.path.insert(0, installed['A']['dependency_root'])
    freeze_sha = prior.digest((NS / 'FROZEN.json').read_bytes())
    order = prior.ORDER[:pair_count * 2]
    slots, pairs = {}, []
    for label in order:
        slot = run / 'slots' / label
        try:
            slots[label] = assess_slot(slot, label, (request, prediction), truth, installed, freeze_sha)
        except Exception as error:
            result = slot / 'SLOT_RESULT.json'
            slots[label] = {'label': label, 'arm': label[0], 'status': 'failed' if slot.exists() else 'unrun',
                            'passed': False, 'error_type': type(error).__name__, 'error': str(error),
                            'slot_result_sha256': prior.digest(result.read_bytes()) if result.exists() else None}
    for n in range(1, pair_count + 1):
        a, b = slots[f'A{n}'], slots[f'B{n}']
        try:
            require(a['passed'] and b['passed'], 'incomplete_or_failed_original_pair')
            pairs.append(compare_pair(run, a, b))
        except Exception as error:
            pairs.append({'A': a['label'], 'B': b['label'], 'passed': False, 'error_type': type(error).__name__,
                          'error': str(error)})
    complete = [row for row in slots.values() if row['passed']]
    nonoverlap = all(a['owned_awake_window'][1] <= b['owned_awake_window'][0]
                     for a, b in zip(complete, complete[1:]))
    quality = nonoverlap and all(row['passed'] for row in pairs)
    gains = None
    medians = {}
    if quality:
        for phase in PHASES:
            phases = [row['timing_candidate_minus_baseline_ms'][phase] for row in pairs]
            medians[phase] = {k: median(row[k] for row in phases) for k in phases[0]}
        for key in ('sequence_window', 'sequence_rpc_sum', 'owned_window'):
            medians[key] = median(row[f'{key}_candidate_minus_baseline_ms'] for row in pairs)
        if pair_count == 3:
            gains = medians['prediction']['server_rpc_ms'] < 0 and medians['sequence_window'] < 0
    passed = quality and (pair_count < 3 or gains is True)
    graphs = [row['retained_global_index']['python_graph'] for row in complete if row['arm'] == 'B']
    graph_medians = {key: median(row[key] for row in graphs) for key in graphs[0]} if graphs else None
    return {'schema': 'm4-cross-scale-global-index-reuse-paired-review-v1', 'passed': passed,
            'quality_passed': quality, 'median_prediction_and_sequence_gates_passed': gains,
            'registered_order': list(prior.ORDER), 'reviewed_slot_count': len(order),
            'attempted_slot_order': list(slots), 'closed_qualifying_slot_count': len(complete),
            'pair_denominator': 3, 'reviewed_pair_count': pair_count,
            'reviewed_passing_pairs': sum(row['passed'] for row in pairs), 'order_nonoverlap': nonoverlap,
            'model_consumers': 0, 'completed_verified_raster_attempts': sum(s['raster_attempts'] for s in complete),
            'completed_verified_business_attempts': sum(s['business_attempts'] for s in complete),
            'current_truth_sha256': prior.TRUTH_SHA256, 'freeze_sha256': freeze_sha,
            'request_sha256': prior.digest(request_path.read_bytes()),
            'prediction_request_sha256': prior.digest(prediction_path.read_bytes()),
            'retained_python_graph_medians': graph_medians,
            'median_candidate_minus_baseline_ms': medians, 'slots': list(slots.values()), 'pairs': pairs}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--pairs', type=int, choices=(1, 2, 3), default=3)
    parser.add_argument('--request', type=Path, default=NS / 'inputs/REQUEST.json')
    parser.add_argument('--prediction', type=Path, default=NS / 'inputs/PREDICTION.json')
    parser.add_argument('--output', type=Path, default=HERE / 'PAIR_REVIEW.json')
    options = parser.parse_args()
    result = assess(options.runtime, options.request, options.prediction, options.pairs)
    write(options.output, result)
    print(json.dumps({'passed': result['passed'], 'quality_passed': result['quality_passed'],
                      'median_prediction_and_sequence_gates_passed': result['median_prediction_and_sequence_gates_passed'],
                      'median_candidate_minus_baseline_ms': result['median_candidate_minus_baseline_ms'],
                      'failed_slots': [row for row in result['slots'] if not row['passed']],
                      'failed_pairs': [row for row in result['pairs'] if not row['passed']]}, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
