"""Verify the six cold dense observations against sealed product and geometry evidence."""

import argparse
from collections import Counter
import json
from pathlib import Path
import runpy
from statistics import median
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
OLD = V / 'm4_bound_blocker_evidence_001'
OLD_RUN = Path('D:/he_m4_bound_blocker_evidence_001')
RUN = Path('D:/he_m4_global_pixel_bound_short_circuit_001')
OLD_REVIEW = OLD / 'checks/LIVE_REVIEW.json'
OLD_REVIEW_SHA = '32b37b7de3be6eda47a949244266e51a05adc1ac8996416d4fe90301cefb0074'
OLD_INDEX_SHA = 'c4558bea03d6b2dbb01a19057209b8a5efe66f76f5b5c3e519ebc7e6f372fdac'
OLD_ARCHIVE_SHA = '18c91c9903cba5f0c7b40e180e7f6a3b503b221eb80c0512ac1c8c12026423b4'
OLD_BINDING_SHA = '486a4a74d95ac5b7049689be581079ba6c971c9b7854e5af9f753226d903f5e3'
BASE_COMMIT = 'e03ee486dc8f86f6a7d2fb75d012d181edcf8f3c'
BASE_SOURCE = '84bf65eedbc0866375d760025437993b90ec54325af09b4e1f36b74abe233d62'
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
CHANGED = 'human_eye_plugin/active_observation_region_task.py'
TARGET_STAGE = 'pixel_bounds_LEFT'
LEFT_THRESHOLD = 70
MIN_RPC_IMPROVEMENTS = 2
BINDINGS = {'A': OLD / 'install/PRODUCT_RUN_BINDING.json', 'B': NS / 'install/PRODUCT_RUN_BINDING.json'}

blocker = runpy.run_path(str(OLD / 'checks/live_review.py'))
dense = blocker['retained']
original = dense['original']
read, require, verified, write, digest, rows, ms = (original[k] for k in
    ('read', 'require', 'verified', 'write', 'digest', 'rows', 'ms'))
proof = runpy.run_path(str(OLD / 'checks/geometry_controls.py'))


def pin(path):
    target = Path(path).resolve()
    data = target.read_bytes()
    return {'path': str(target), 'bytes': len(data), 'sha256': digest(data)}


def historical_reference():
    past = json.loads(verified(OLD_REVIEW, OLD_REVIEW_SHA, OLD))
    require(past['passed'] is True and past['runtime_source_sha256'] == BASE_SOURCE and
            past['work']['pixel_bound_region_calls'] == 10 and
            past['installed_product']['commit'] == BASE_COMMIT and
            len(past['actual_bound_blocker_evidence']) == 2, 'fixed_dense_blocker_reference_changed')
    index_path = OLD / 'RUNTIME_INDEX.json'
    index = json.loads(verified(index_path, OLD_INDEX_SHA, OLD))
    path = OLD_RUN / 'ORIGINAL_RUNTIME.zip'
    raw_zip = verified(path, OLD_ARCHIVE_SHA, OLD_RUN)
    require(index['archive']['sha256'] == OLD_ARCHIVE_SHA and index['archive']['bytes'] == len(raw_zip)
            and Path(index['archive']['path']).resolve() == path.resolve(), 'sealed_dense_archive_binding_changed')
    members = {row['path']: row for row in index['files']}
    require(len(members) == index['count'] == 93, 'sealed_dense_archive_denominator_changed')
    files = (
        'SLOT_STARTED.json', 'SLOT_RESULT.json', 'SLOT_PUBLICATION.json', 'RUNTIME_CLOSE.json',
        'PUBLIC_REQUESTS.jsonl', 'product_calls/call_001/RESPONSE.json',
    )
    verified_paths = []
    with ZipFile(path) as archive:
        require(set(archive.namelist()) == members.keys(), 'sealed_dense_archive_membership_changed')
        for name in files:
            key = f'slots/QP/{name}'
            ref = members[key]
            target = OLD_RUN / key
            data = verified(target, ref['sha256'], OLD_RUN)
            require(len(data) == ref['bytes'] and data == archive.read(key),
                    'sealed_dense_live_reference_bytes_changed/' + name)
            verified_paths.append(target)
        event, = rows(OLD_RUN / 'slots/QP/PUBLIC_REQUESTS.jsonl')
        receipt = event['producer_archive']
        target = Path(receipt['path']).resolve()
        key = target.relative_to(OLD_RUN.resolve()).as_posix()
        producer = verified(target, receipt['sha256'], OLD_RUN)
        require(members[key]['sha256'] == receipt['sha256'] and producer == archive.read(key),
                'sealed_dense_product_producer_snapshot_changed')
        verified_paths.append(target)
    reply = read(OLD_RUN / 'slots/QP/product_calls/call_001/RESPONSE.json')
    body = json.loads(reply['result']['content'][0]['text'])
    require(digest(reply['result']['content'][0]['text'].encode()) == past['wire']['body_sha256'],
            'sealed_dense_raw_brief_changed')
    return past, body, json.loads(producer), [OLD_REVIEW, index_path, path, *verified_paths]


def stable_body(body):
    """Compare task facts; source and session identifiers are checked inside each slot."""
    require(len(body['binding']) > 0, 'no_current_brief_binding')
    stable = {key: value for key, value in body.items()
              if key not in ('binding', 'session_id', 'scopes', 'frames', 'objects')}
    dynamic = {
        'binding': {'scene_revision', 'document_epoch', 'capture_state', 'source_binding_sha256', 'geometry_identity',
                    'camera_identity', 'binding_sha256', 'runtime_source_sha256'},
        'scopes': {'camera_identity', 'binding_sha256'},
        'frames': {'frame_identity', 'image_ref'},
        'objects': {'host_id', 'instance_id'},
    }
    for name, removed in dynamic.items():
        table = body[name]
        columns = table.get('columns')
        if columns is None:
            stable[name] = {key: value for key, value in table.items() if key not in removed}
            continue
        kept = [i for i, key in enumerate(columns) if key not in removed]
        stable[name] = {'columns': [columns[i] for i in kept], 'rows': [
            [row[i] for i in kept] for row in table['rows']]}
    return stable


def installations():
    baseline = json.loads(verified(BINDINGS['A'], OLD_BINDING_SHA, OLD))
    candidate = read(BINDINGS['B'])
    require(baseline['preparation_git'] == BASE_COMMIT and baseline['source_sha256'] == BASE_SOURCE and
            candidate['historical_preparation_git'] == BASE_COMMIT and
            candidate['historical_source_sha256'] == BASE_SOURCE and candidate['changed_product_sources'] == [CHANGED] and
            candidate['preparation_git'] != BASE_COMMIT and candidate['source_sha256'] != BASE_SOURCE and
            candidate['dependency_root'] == baseline['dependency_root'],
            'fixed_baseline_or_direct_candidate_isolated_install_changed')
    base_files, new_files = ({row['path']: row['sha256'] for row in v['source_manifest']}
                             for v in (baseline, candidate))
    require(len(base_files) == len(new_files) == 143 and
            len(baseline['source_manifest']) == len(candidate['source_manifest']) == 143 and
            new_files.keys() == base_files.keys() and
            {path for path in base_files if base_files[path] != new_files[path]} == {CHANGED},
            'candidate_source_difference_not_one_registered_file')
    catalog = read(BINDINGS['A'].with_name('TOOLS_SCHEMA.json'))
    require(len(catalog) == 5 and catalog == read(BINDINGS['B'].with_name('TOOLS_SCHEMA.json')),
            'candidate_catalog_changes_the_five_registered_tools')
    return {'A': baseline, 'B': candidate}, catalog


def verify_install(installed):
    install = Path(installed['install_root'])
    for entry in installed['source_manifest']:
        verified(install / entry['path'], entry['sha256'], install)
    wheel = Path(installed['wheel_path'])
    verified(wheel, installed['wheel_sha256'], wheel.parent)


def inspect_current_install(slot, result, installed, binding_path, catalog):
    identity = read(slot / 'MCP_IDENTITY.json')
    ready = read(slot / 'RUNTIME_READY.json')
    fields = ('distribution_version', 'source_sha256', 'build_id', 'base_version',
              'implementation_revision', 'protocol_version')
    require(result['product_source_sha256'] == installed['source_sha256'] == ready['product_source_sha256'] and
            result['product_binding_sha256'] == digest(binding_path.read_bytes()) and
            identity['source_kind'] == 'installed_distribution' and identity['source_file_count'] == 143 and
            identity['identity_check']['compatible'] is True and all(identity[k] == installed[k] for k in fields) and
            read(slot / 'INSTALLED_TOOLS.json') == catalog,
            'completed_slot_actual_installed_runtime_or_catalog_mismatch')
    return {'commit': installed['preparation_git'], 'source_sha256': installed['source_sha256'],
            'wheel_sha256': installed['wheel_sha256'], 'runtime_sources_verified': 143}


def verify_close(slot, started, result, published, freeze, label):
    require(all(x['label'] == x['slot'] == label for x in (started, result, published)) and
            started['freeze_sha256'] == result['freeze_sha256'] == freeze and
            published['result_sha256'] == digest((slot / 'SLOT_RESULT.json').read_bytes()) and
            started['asset_sha256'] == result['asset_sha256'] == original['ASSET_SHA'] and
            all(x['model_consumers'] == x['paid_API_calls'] == 0 and x['actual_model_admitted'] is False
                for x in (started, result)), 'actual_slot_result_publication_or_asset_not_bound')
    require(published['status'] == result['status'] == 'completed' and not result['errors'] and
            published['owned_budget_passed'] is True and
            result['closure_verification']['passed'] is True and
            result['closure_verification']['status'] == 'ready_closed' and
            result['closure_verification']['mcp_closure_required'] is True and
            result['independent_before_after']['passed'] is True and
            result['independent_before_after']['same_owned_scene'] is True,
            'owned_slot_did_not_complete_cleanly')
    closed = read(slot / 'RUNTIME_CLOSE.json')
    require(not closed['errors'] and all(exit_['exit_code'] == 0 and
            all(exit_[k] is True for k in ('confirmed', 'exited', 'handle_closed')) for exit_ in
            (closed['public_MCP_exit'], closed['Blender_exit'])),
            'actual_mcp_or_blender_exit_not_confirmed')
    require(ms(started['started_ns'], published['published_ns']) * 1e6 <=
            result['owned_deadline_ns'] - started['started_ns'] and started['started_ns'] == result['started_ns'] ==
            published['started_ns'] and published['complete_slot_ns'] == published['published_ns'] - started['started_ns'],
            'owned_window_clock_changed')
    call, = result['business_calls']
    require(call['kind'] == 'cold' and call['status'] == 'completed' and
            started['started_ns'] <= result['ready_ns'] <= call['started_ns'] <= call['closed_ns']
            <= result['task_deadline_ns'], 'one_completed_cold_call_required')
    return call


def verified_budget(runtime, label, result):
    entry = result['budget']['slots'][label]
    claims = [row for row in result['budget']['records'] if row['claim']['label'] == label]
    require(Counter(row['claim']['kind'] for row in claims) ==
            {'Blender_start': 1, 'business_tool': 1, 'raster_attempt': 2} and
            entry['business_admissions'] == 1 and entry['raster_upper'] == entry['raster_actual'] == 2,
            'exactly_one_cold_admission_and_two_rasters_required')
    budget = runtime / 'budget'
    for row in claims:
        claim, settlement = row['claim'], row['settlement']
        path = budget / 'claims' / (claim['token'] + '.json')
        require(read(path) == claim, 'original_ledger_claim_and_result_differ')
        if claim['kind'] == 'business_tool':
            continue
        settled = read(budget / 'settlements' / path.name)
        require(settled == settlement and settled['claim_sha256'] == digest(path.read_bytes()),
                'original_ledger_settlement_and_result_differ')
        if claim['kind'] == 'raster_attempt':
            require(settled['actual_attempts'] == settled['confirmed_attempts_lower_bound'] == 1,
                    'independent_ledger_did_not_admit_one_actual_frame')


def measure(slot, installed, result, published, started, outcome, reference, truth, bound_count):
    old, old_body, old_producer, _ = reference
    terminal, outcome['current_source'] = original['current_source'](slot, result)
    reply, event, meter, outcome['wire'], outcome['timing'] = original['audit_wire'](slot, started, result, published)
    outcome['timing']['admission_verification_ms'] = result['admission_verification_ns'] / 1e6
    body = json.loads(reply['result']['content'][0]['text'])
    archive = event['producer_archive']
    producer = json.loads(verified(archive['path'], archive['sha256'], slot))
    require(stable_body(body) == stable_body(old_body), 'normalized_current_brief_differs_from_original')
    require(all(frame['pose'] == historic['pose'] for frame, historic in
                zip(producer['constructed_frames'], old_producer['constructed_frames'], strict=True)) and
            len(producer['scopes']) == 1 and producer['scopes'][0]['scope_id'] == 'global' and
            producer['scopes'][0]['skipped_views'] == old_producer['scopes'][0]['skipped_views'] == [],
            'original_dense_camera_pose_scope_or_view_decision_changed')
    outcome.update(normalized_original_brief_sha256=digest(json.dumps(
        stable_body(body), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()))
    # The sole expected difference in the retained scene work account is the number of actual bound calls.
    expected_work = {**old['work'], 'pixel_bound_region_calls': bound_count}
    baseline = {**old, 'work': expected_work}
    blocker['original_inspect'](slot, reply, event, meter, installed, terminal, truth, baseline, outcome)
    measured = blocker['verify_blockers'](body, producer, terminal, truth, proof)
    require(measured == old['actual_bound_blocker_evidence'], 'exact_bound_blocker_output_changed')
    outcome['actual_bound_blocker_evidence'] = measured
    observation, = [row for row in rows(slot / 'product_audit.jsonl') if row['event'] == 'observe']
    require(observation['task_work'] == producer['work'] and
            producer['generation_work']['pixel_bound_region_calls'] == producer['work']['pixel_bound_region_calls'] ==
            bound_count, 'actual_bound_call_count_differs_across_producer_and_audit')
    stage, = [key for key in producer['stages'] if key.startswith('pixel_bounds_')]
    value = producer['stages'][stage]
    start, end = value['started_ns'], value['closed_ns']
    require(stage == TARGET_STAGE and value['elapsed_ns'] == end - start > 0 and
            meter['request_received_ns'] <= start <= end <= meter['reply_completed_ns'] and
            outcome['timing']['producer_stages_ms'][TARGET_STAGE] == ms(start, end)
            <= outcome['timing']['request_server_RPC_ms'], 'actual_left_bound_stage_not_bound_to_cold_server_RPC')
    require(outcome['CLI']['passed'] and outcome['body_cap_passed'] and not outcome['issues'],
            'fixed_CLI_text_or_original_png_delivery_changed')
    outcome.update(pixel_bound_region_calls=bound_count, left_bound_ns=[start, end],
                   cold_rpc_ns=[meter['request_received_ns'], meter['reply_completed_ns']],
                   owned_window_ns=[started['started_ns'], published['published_ns']])
    return producer, event


def check_call_trace(slot, producer, event, outcome):
    archive = event['producer_archive']
    path = Path(archive['read_context']).resolve()
    require(path == (slot / 'product_full/call_001/READ_CONTEXT.json').resolve(),
            'bound_probe_is_not_the_original_observation_context')
    context = read(path)
    before, after = (context[key]['pixel_bound_probe'] for key in ('before', 'after'))
    installed = read(BINDINGS[outcome['arm']])
    source = Path(installed['install_root']) / CHANGED
    expected_source = {'path': str(source.resolve()),
                       'sha256': next(row['sha256'] for row in installed['source_manifest'] if row['path'] == CHANGED)}
    count = outcome['pixel_bound_region_calls']
    scope, = producer['scopes']
    full = [{'view_name': 'LEFT', 'roi_id': row['roi_id']}
            for row in scope['facts']['region_evidence']
            if (row['complete_witness'] or {}).get('view_name') == 'LEFT']
    require(before == {'source': expected_source, 'total': 0, 'calls': []} and
            after == {'source': expected_source, 'total': count, 'calls': full[:count]} and
            len(full) == 10 and len({row['roi_id'] for row in full}) == 10,
            'source_bound_probe_call_count_or_fixed_roi_order_changed')
    warm_index, = context['after']['region_task_global_indexes']
    require(context['before']['region_task_global_indexes'] == [] and
            warm_index['scene_identity'] == producer['binding']['geometry_identity'] and
            warm_index['camera_identity'] == producer['binding']['camera_identity'],
            'cold_observation_did_not_form_the_current_global_index_once')
    outcome.update(pixel_bound_probe=after, cold_index=warm_index,
                   read_context_sha256=digest(path.read_bytes()))


def compare_pair(a, b):
    require(a['passed'] is True and b['passed'] is True, 'one_or_both_slots_not_quality_verified')
    require(a['normalized_original_brief_sha256'] == b['normalized_original_brief_sha256'] and
            [a['pixel_bound_region_calls'], b['pixel_bound_region_calls']] == [10, 1],
            'paired_same_quality_or_actual_call_count_failed')
    checks = (
        ('LEFT_pixel_bounds_ms', 'producer_stages_ms', TARGET_STAGE),
        ('cold_server_RPC_ms', 'request_server_RPC_ms'),
        ('cold_client_RPC_ms', 'request_client_RPC_ms'),
        ('startup_to_ready_ms', 'startup_to_ready_ms'),
        ('owned_window_ms', 'owned_window_ms'),
        ('capture_ms', 'producer_stages_ms', 'host_capture'),
        ('index_ms', 'producer_stages_ms', 'index_global'),
        ('SCENE_render_publish_ms', 'producer_stages_ms', 'render_and_publish_global_SCENE'),
        ('LEFT_render_publish_ms', 'producer_stages_ms', 'render_and_publish_global_LEFT'),
    )
    def timing(slot, path):
        value = slot['timing']
        for key in path:
            value = value[key]
        return value
    clocks = {name: [timing(slot, path) for slot in (a, b)] for name, *path in checks}
    x, y = clocks['LEFT_pixel_bounds_ms']
    cold_a, cold_b = clocks['cold_server_RPC_ms']
    return {'A': a['label'], 'B': b['label'], 'passed': True, 'pixel_bound_region_calls_A_B': [10, 1],
            'timing_A_B_ms': clocks, 'LEFT_pixel_bound_reduction_percent': 100 * (x - y) / x,
            'cold_RPC_delta_ms': cold_b - cold_a, 'cold_RPC_improved': cold_b < cold_a}


def raw_denominator(runtime):
    root = runtime / 'budget'
    by_slot = {label: Counter() for label in ORDER}
    claims = {p.stem: p for p in (root / 'claims').glob('*.json')}
    settled = {p.stem: p for p in (root / 'settlements').glob('*.json')}
    caps = {'Blender_start': 1, 'business_tool': 1, 'raster_attempt': 2}
    require(set(settled) <= claims.keys(), 'settlement_without_a_registered_admission')
    for token, path in claims.items():
        claim = read(path)
        label, kind = claim['label'], claim['kind']
        require(label in by_slot and kind in caps and claim['token'] == token and
                claim['phase'] == 'formal' and claim['reserved_upper_bound'] == 1, 'unregistered_actual_claim')
        counts = by_slot[label]
        counts[kind] += 1
        require(counts[kind] <= caps[kind], 'actual_claims_exceed_registered_slot_cap')
        if token in settled:
            record = read(settled[token])
            require(record['claim_sha256'] == digest(path.read_bytes()) and record['token'] == token,
                    'mismatched_actual_budget_settlement')
        else:
            record = {}
        if kind == 'raster_attempt':
            known, measured = record.get('confirmed_attempts_lower_bound', 0), record.get('actual_attempts')
            require(type(known) is int and known in (0, 1) and
                    (measured is None or type(measured) is int and measured in (0, 1) and measured >= known),
                    'unknown_or_mismatched_raster_settlement')
            counts['actual_rasters_or_lower_bound'] += known if measured is None else measured
            counts['potential_upper_rasters'] += 1 if measured is None else measured
            counts['pending_rasters'] += int(measured is None)
    return {label: dict(values) for label, values in by_slot.items()}


def truth():
    return json.loads(verified(dense['TRUTH'], dense['TRUTH_SHA'], dense['PRIOR_NS']))


def review_slot(runtime, label, freeze, installed, catalog, reference, archive_truth):
    slot = runtime / 'slots' / label
    result_path = slot / 'SLOT_RESULT.json'
    publication_path = slot / 'SLOT_PUBLICATION.json'
    outcome = {'label': label, 'arm': label[0], 'passed': False, 'issues': [],
               'status': 'failed' if slot.exists() else 'unrun',
               'cli_path': runtime / 'preflight/CLI_REPLAY' / label}
    try:
        if not slot.exists():
            return outcome
        if result_path.is_file():
            result = read(result_path)
            outcome.update(slot_result_sha256=digest(result_path.read_bytes()),
                           original_runtime_status=result['status'], original_slot_errors=result['errors'])
        else:
            raise ValueError('slot_started_without_a_closed_result')
        published = read(publication_path)
        started = read(slot / 'SLOT_STARTED.json')
        outcome.update(publication_sha256=digest(publication_path.read_bytes()),
                       original_publication_status=published['status'])
        require(all(x['phase'] == 'formal' and x['group'] == 'P' and x['arm'] == label[0]
                    for x in (started, result)), 'mismatched_executed_actual_arm')
        verify_close(slot, started, result, published, freeze, label)
        verified_budget(runtime, label, result)
        outcome['installed_product'] = inspect_current_install(slot, result, installed, BINDINGS[label[0]], catalog)
        producer, event = measure(slot, installed, result, published, started, outcome, reference, archive_truth,
                                  10 if label[0] == 'A' else 1)
        check_call_trace(slot, producer, event, outcome)
        outcome.update(status='completed', passed=True)
    except Exception as error:
        outcome['issues'].append({'type': type(error).__name__, 'message': str(error)})
    finally:
        outcome['cli_path'] = str(outcome['cli_path'])
    return outcome


def review(runtime, freeze_path):
    freeze = digest(freeze_path.read_bytes())
    frozen = read(freeze_path)
    installed, catalog = installations()
    require(frozen['slots'] == list(ORDER) and frozen['asset_sha256'] == original['ASSET_SHA'],
            'frozen_actual_six_slots_or_dense_asset_changed')
    for arm, data in installed.items():
        verify_install(data)
        require(all(frozen['products'][arm][key] == data[field] for key, field in
                    (('commit', 'preparation_git'), ('source_sha256', 'source_sha256'))),
                'installed_product_differs_from_frozen_arm/' + arm)
    sys.path.insert(0, installed['A']['dependency_root'])
    source = truth()
    reference = historical_reference()
    slot_root = runtime / 'slots'
    attempted = {path.name for path in slot_root.iterdir()} if slot_root.is_dir() else set()
    require(attempted == set(ORDER[:len(attempted)]), 'non_prefix_or_unknown_original_slot')
    denominator = raw_denominator(runtime)
    expected = {'Blender_start': 1, 'business_tool': 1, 'raster_attempt': 2,
                'actual_rasters_or_lower_bound': 2, 'potential_upper_rasters': 2, 'pending_rasters': 0}
    slots = {label: review_slot(runtime, label, freeze, installed[label[0]], catalog, reference, source) for label in ORDER}
    pairs = []
    for i in (1, 2, 3):
        a, b = f'A{i}', f'B{i}'
        try:
            pairs.append(compare_pair(slots[a], slots[b]))
        except (KeyError, TypeError, ValueError) as error:
            pairs.append({'A': a, 'B': b, 'passed': False, 'reason': str(error)})
    complete = [row for row in slots.values() if row['passed']]
    require(all(denominator[row['label']] == expected for row in complete), 'finished_slot_original_ledger_mismatch')
    nonoverlap = all(a['owned_window_ns'][1] <= b['owned_window_ns'][0] for a, b in zip(complete, complete[1:]))
    quality = len(complete) == len(ORDER) and nonoverlap and all(pair['passed'] for pair in pairs)
    good = [pair for pair in pairs if pair['passed']]
    reduction = median(row['LEFT_pixel_bound_reduction_percent'] for row in good) if good else None
    rpc_delta = median(row['cold_RPC_delta_ms'] for row in good) if good else None
    rpc_wins = sum(row['cold_RPC_improved'] for row in good)
    median_window_delta = median(t[1] - t[0] for t in (
        row['timing_A_B_ms']['owned_window_ms'] for row in good)) if good else None
    left_gate = len(good) == 3 and reduction >= LEFT_THRESHOLD
    rpc_gate = len(good) == 3 and rpc_wins >= MIN_RPC_IMPROVEMENTS and rpc_delta < 0
    return {'schema': 'm4-global-pixel-bound-short-circuit-live-review-v1', 'passed': quality and left_gate and rpc_gate,
            'quality_passed': quality, 'performance_passed': left_gate and rpc_gate,
            'left_stage_gate_passed': left_gate, 'cold_rpc_gate_passed': rpc_gate, 'verified_nonoverlap': nonoverlap,
            'freeze_sha256': freeze, 'registered_order': list(ORDER), 'passed_slot_count': len(complete),
            'attempted_owned_slots': len(attempted), 'nonpassing_slot_count': len(attempted) - len(complete),
            'unrun_slot_count': len(ORDER) - len(attempted),
            'original_admissions_even_when_slot_failed': denominator,
            'fixed_asset_sha256': source['asset_sha256'], 'historical_archive_sha256': OLD_ARCHIVE_SHA,
            'fixed_baseline_source_sha256': BASE_SOURCE, 'candidate_source_sha256': installed['B']['source_sha256'],
            'median_LEFT_pixel_bound_reduction_percent': reduction, 'left_stage_threshold_percent': LEFT_THRESHOLD,
            'median_cold_RPC_delta_ms': rpc_delta, 'cold_RPC_improved_pairs': rpc_wins,
            'cold_RPC_improved_pairs_required': MIN_RPC_IMPROVEMENTS,
            'median_owned_window_delta_ms': median_window_delta, 'model_consumers': 0,
            'slots': list(slots.values()), 'pairs': pairs}


def preflight():
    slot = OLD_RUN / 'slots/QP'
    original_result = read(slot / 'SLOT_RESULT.json')
    reference = historical_reference()
    installed = json.loads(verified(BINDINGS['A'], OLD_BINDING_SHA, OLD))
    verify_install(installed)
    sys.path.insert(0, installed['dependency_root'])
    frozen = OLD / 'FROZEN.json'
    published, started = (read(slot / name) for name in ('SLOT_PUBLICATION.json', 'SLOT_STARTED.json'))
    verify_close(slot, started, original_result, published, digest(frozen.read_bytes()), 'QP')
    verified_budget(OLD_RUN, 'QP', original_result)
    inspect_current_install(slot, original_result, installed, BINDINGS['A'], read(BINDINGS['A'].with_name('TOOLS_SCHEMA.json')))
    before = {'issues': [], 'cli_path': HERE / 'historical_CLI_REPLAY'}
    measure(slot, installed, original_result, published, started, before, reference, truth(), 10)
    # Bind every original input and the exact helper versions. No output touches the old runtime.
    paths = [
        *reference[3], BINDINGS['A'], BINDINGS['A'].with_name('TOOLS_SCHEMA.json'), frozen, dense['TRUTH'],
        Path(__file__), OLD / 'checks/live_review.py', OLD / 'checks/geometry_controls.py',
        V / 'm4_dense_region_brief_001/checks/live_review.py', V / 'm4_dense_region_brief_001/checks/brief_schema.py',
        V / 'm4_dense_panel_sweep_001/checks/qualify_product.py',
        V / 'm4_cross_scale_live_task_formal_001/scoring/formal.py',
        V / 'm4_cross_scale_local_first_view_001/checks/assess_pairs.py',
        V / 'm4_cross_scale_pixel_evidence_001/checks/assess_live.py',
    ]
    return {'passed': True, 'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_raster_attempts': 0,
            'original_archive_sha256': OLD_ARCHIVE_SHA,
            'verified_raw_regions': len(before['original_regions']),
            'verified_bound_blockers': len(before['actual_bound_blocker_evidence']),
            'original_frames': before['frames'], 'old_cold_pixel_bound_count': before['pixel_bound_region_calls'],
            'fixed_CLI': before['CLI'], 'source_pins': sorted((pin(p) for p in paths), key=lambda x: x['path'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--freeze', type=Path, default=NS / 'FROZEN.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    result = preflight() if args.preflight else review(args.runtime, args.freeze)
    output = args.output or HERE / ('LIVE_PREFLIGHT.json' if args.preflight else 'LIVE_REVIEW.json')
    write(output, result)
    fields = ('passed', 'quality_passed', 'performance_passed', 'passed_slot_count',
              'median_LEFT_pixel_bound_reduction_percent', 'median_cold_RPC_delta_ms', 'cold_RPC_improved_pairs')
    print(json.dumps({k: result[k] for k in fields if k in result}, ensure_ascii=False), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
