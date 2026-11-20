"""Independently review the fixed assembly slots and their original wire and frames."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import runpy
from statistics import median
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
PIXEL = NS.parent / 'm4_cross_scale_pixel_evidence_001'
RUN = Path('D:/he_m4_cross_scale_projected_bounds_001')
ARCHIVED = Path('D:/he_m4_cross_scale_pixel_evidence_001')
OLD_SOURCE = 'b06f5e85a5d7b2519a09df2d7e5aa92ec2c915e860e58979837545c2851ded0a'
OLD_ARCHIVE = '583456c1838a6fd200104fcfaf72dfa279beaf928901a5b42164b99f60415bae'
OLD_TERMINAL = 'a550a7018e07fc8e18204ffe77231b254d93a9558b2114036d2113898120a52b'
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
MIN_REDUCTION = 20
MIN_RPC_IMPROVEMENTS = 2
PHASES = ('cold', 'no_image_full')
SCHEMA = 'm4-cross-scale-projected-bounds-live-review-v1'

PIXEL_HELPER = PIXEL / 'checks/assess_live.py'
PIXEL_HELPER_SHA256 = 'f85522dc0eadf1dfe605c82936e2a38a59974e2f0b253ae1190fc034813698c5'
if sha256(PIXEL_HELPER.read_bytes()).hexdigest() != PIXEL_HELPER_SHA256:
    raise ValueError('archived_pixel_scorer_changed')
pixel = runpy.run_path(str(PIXEL_HELPER))
read, require, verified, digest, rows, ms = (pixel[key] for key in
    ('read', 'require', 'verified', 'digest', 'rows', 'ms'))


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(',', ':')).encode()


def archived_verifier():
    index = read(PIXEL / 'RUNTIME_INDEX.json')
    archive = ARCHIVED / 'ORIGINAL_RUNTIME.zip'
    require(Path(index['archive']['path']).resolve() == archive.resolve() and
            len(verified(archive, OLD_ARCHIVE, ARCHIVED)) == index['archive']['bytes'] and
            index['archive']['sha256'] == OLD_ARCHIVE, 'archived_pixel_archive_not_bound')
    pins = {row['path']: row for row in index['files']}
    require(len(pins) == index['count'] == 106, 'archived_pixel_pins_changed_or_duplicate')

    def verify_path(path):
        key = path.resolve().relative_to(ARCHIVED.resolve()).as_posix()
        pin = pins[key]
        data = verified(path, pin['sha256'], ARCHIVED)
        require(len(data) == pin['bytes'], 'archived_pixel_byte_count_changed/' + key)
        return data

    return verify_path


def retained_index(cold, full):
    contexts = [cold['context'], full['context']]
    snapshots = [ctx[side]['region_task_global_indexes'] for ctx in contexts for side in ('before', 'after')]
    require(snapshots[0] == [] and all(type(group) is list and len(group) == 1 for group in snapshots[1:]),
            'cold_global_index_was_not_the_only_cached_resource')
    indexes = [group[0] for group in snapshots[1:]]
    index = indexes[0]
    binding = full['producer']['binding']
    require(all(row == index for row in indexes[1:]) and type(index['python_id']) is int and index['python_id'] > 0 and
            index['type'].rsplit('.', 1)[-1] == 'CoverageIndex' and
            (index['regions'], index['views'], index['partition_rows']) == (188, 6, 28) and
            index['scene_identity'] == binding['geometry_identity'] and
            index['camera_identity'] == binding['camera_identity'] and
            index['selection_repr'] == contexts[1]['after']['active_selection_repr'] and
            contexts[0]['after']['generation_repr'] == contexts[1]['before']['generation_repr'] ==
            contexts[1]['after']['generation_repr'],
            'retained_global_index_wrong_current_generation_or_scope')
    return {key: index[key] for key in ('regions', 'views', 'partition_rows', 'type', 'scene_identity',
                                        'camera_identity')}


def verify_ledger(result, label):
    ledger = result['budget']
    entry = ledger['slots'][label]
    claims = [row for row in ledger['records'] if row['claim']['label'] == label]
    counts = Counter(x['claim']['kind'] for x in claims)
    expected = {'Blender_start': 1, 'business_tool': 2, 'raster_attempt': 3}
    require(counts == expected and entry['business_admissions'] == 2 and
            entry['raster_upper'] == entry['raster_actual'] == 3 and
            sum(row['settlement']['actual_attempts'] for row in claims
                if row['claim']['kind'] == 'raster_attempt') == 3,
            'actual_slot_denominator_exceeded_or_not_proved')
    return {'Blender_start_attempts': counts['Blender_start'], 'business_admissions': counts['business_tool'],
            'raster_actual': entry['raster_actual'], 'model_consumers': 0}


def original_denominator(runtime, labels):
    """Count admitted attempts even when a slot produced no usable result."""
    budget = runtime / 'budget'
    paths = sorted((budget / 'claims').glob('*.json'))
    settlements = {path.stem: path for path in (budget / 'settlements').glob('*.json')}
    permitted = {'Blender_start': 1, 'business_tool': 2, 'raster_attempt': 3}
    require(set(settlements).issubset(path.stem for path in paths), 'budget_settlement_without_original_claim')
    by_slot = {label: Counter() for label in ORDER}
    for path in paths:
        claim = read(path)
        label, kind = claim['label'], claim['kind']
        require(label in by_slot and kind in permitted and claim['phase'] == 'formal' and
                claim['token'] == path.stem and claim['reserved_upper_bound'] == 1, 'unexpected_live_claim')
        count = by_slot[label]
        count[kind] += 1
        require(count[kind] <= permitted[kind], 'registered_slot_attempt_budget_exceeded')
        if kind == 'raster_attempt':
            settled = read(settlements[path.stem]) if path.stem in settlements else {}
            actual = settled.get('actual_attempts')
            known = settled.get('confirmed_attempts_lower_bound', 0)
            require((not settled or (settled['token'] == path.stem and
                    settled['claim_sha256'] == digest(path.read_bytes()))) and
                    (actual is None or type(actual) is int and actual in (0, 1)) and
                    type(known) is int and known in (0, 1) and
                    (actual is None or known <= actual), 'invalid_original_raster_settlement')
            count['raster_actual_or_lower_bound'] += known if actual is None else actual
            count['raster_upper_bound'] += 1 if actual is None else actual
            count['pending_or_unconfirmed_rasters'] += actual is None
    return {label: dict(by_slot[label]) for label in labels}


def phase_summary(observation, cold, local_scope):
    timing = observation['timing']
    stages = timing['producer_stages_ms']
    if cold:
        require(0 < stages['index_global'] <= stages['service_total'] and
                0 < stages[f'index_{local_scope}'] <= stages['service_total'],
                'missing_or_unordered_cold_index_clocks')
    timing['producer_stages_ms'] = {key.replace(local_scope, 'local_scope'): value
                                    for key, value in stages.items()}
    work = observation['producer']['work']
    frustum_keys = ('frustum_certified_views', 'frustum_fallback_views', 'frustum_shadow_bypassed',
                    'frustum_shadow_legacy', 'frustum_proof_ns')
    frustum = {key: work[key] for key in frustum_keys}
    require(all(type(v) is int and v >= 0 for v in frustum.values()) and
            ((cold and frustum['frustum_certified_views'] == 6 and frustum['frustum_fallback_views'] == 0 and
              frustum['frustum_shadow_bypassed'] > 0 and frustum['frustum_shadow_legacy'] == 0 and
              0 < frustum['frustum_proof_ns'] / 1e6 <= stages['index_global']) or
             (not cold and set(frustum.values()) == {0})), 'certified_view_or_prediction_path_drift')
    normalized = canonical(pixel['normalized_public'](observation, cold))
    return {'timing': timing, 'wire': observation['wire'], 'work': work,
            'exact_shadow_branches': frustum['frustum_shadow_bypassed'] + frustum['frustum_shadow_legacy'],
            'normalized_public_sha256': digest(normalized), 'normalized_public_bytes': len(normalized)}


def inspect_slot(slot, requests, truth, binding_path, freeze_sha, historical=None):
    label = slot.name
    if historical:
        for name in ('SLOT_STARTED.json', 'SLOT_RESULT.json', 'SLOT_PUBLICATION.json', 'MCP_IDENTITY.json',
                     'RUNTIME_READY.json', 'RUNTIME_CLOSE.json', 'TERMINAL_SOURCE.json',
                     'initial_capture/TERMINAL_SOURCE.json', 'native/input.blend',
                     'PUBLIC_REQUESTS.jsonl', 'mcp_io/MCP_IO.jsonl', 'product_audit.jsonl'):
            historical(slot / name)
    installed = read(binding_path)
    source_sha = installed['source_sha256']
    result_path, publication_path = slot / 'SLOT_RESULT.json', slot / 'SLOT_PUBLICATION.json'
    result, publication, started = read(result_path), read(publication_path), read(slot / 'SLOT_STARTED.json')
    require(all(record['label'] == label for record in (result, publication, started)) and
            result['status'] == publication['status'] == 'completed' and not result['errors'] and
            publication['owned_budget_passed'] is True and publication['result_sha256'] ==
            digest(result_path.read_bytes()), 'original_slot_result_or_publication_mismatch')
    arm = 'A' if historical else label[0]
    require((historical or result['arm'] == started['arm'] == arm) and
            result['phase'] == started['phase'] == 'formal' and result['group'] == started['group'] == 'P' and
            result['freeze_sha256'] == started['freeze_sha256'] == freeze_sha and
            result['model_consumers'] == result['paid_API_calls'] == 0 and not (slot / 'consumer').exists() and
            result['task_deadline_ns'] - result['started_ns'] == 450_000_000_000 and
            result['owned_deadline_ns'] - result['started_ns'] == 600_000_000_000,
            'wrong_slot_arm_model_or_absolute_deadline')
    identity, ready = read(slot / 'MCP_IDENTITY.json'), read(slot / 'RUNTIME_READY.json')
    require(result['product_binding_sha256'] == digest(binding_path.read_bytes()) and
            identity['source_sha256'] == ready['product_source_sha256'] == result['product_source_sha256'] ==
            source_sha and identity['source_kind'] == 'installed_distribution' and
            identity['source_file_count'] == len(installed['source_manifest']) == 143 and
            result['asset_sha256'] == ready['asset_copy_sha256'] == truth['asset_sha256'] and
            digest((slot / 'native/input.blend').read_bytes()) == truth['asset_sha256'],
            'actual_running_isolated_install_or_asset_copy_changed')
    history = pixel['score']
    terminal, native = history['bound_terminal'](slot, result, truth['asset_sha256'])
    require(result['independent_before_after']['passed'] is True and
            native['sha256'] == result['independent_before_after']['terminal_sha256'] and
            (not historical or native['sha256'] == OLD_TERMINAL), 'native_before_after_or_archived_terminal_changed')
    runtime_close = read(slot / 'RUNTIME_CLOSE.json')
    exited = runtime_close['public_MCP_exit']
    require(not runtime_close['errors'] and exited['confirmed'] and exited['exited'] and
            exited['handle_closed'] and exited['exit_code'] == 0 and
            publication['started_ns'] == result['started_ns'], 'owned_mcp_process_or_publication_not_closed')

    events = rows(slot / 'PUBLIC_REQUESTS.jsonl')
    meters = [row for row in rows(slot / 'mcp_io/MCP_IO.jsonl') if row['method'] == 'tools/call']
    require(len(events) == len(meters) == 2 and [event['index'] for event in events] == [1, 2] and
            len({row['id'] for row in meters}) == 2, 'expected_exactly_two_original_unique_calls')
    started_at, published_at = result['started_ns'], publication['published_ns']
    clock = [started_at, result['ready_ns'], *(ts for event in events for ts in
            (event['started_ns'], event['closed_ns'])),
            min(result['task_deadline_ns'], result['cleanup_started_ns']), published_at, result['owned_deadline_ns']]
    require(clock == sorted(clock), 'original_slot_or_request_clock_elapsed_outside_owned_window')
    audit = rows(slot / 'product_audit.jsonl')
    cold, full = [pixel['audit_wire'](slot, event, meter, audit, request, detail, historical)
                  for event, meter, request, detail in zip(events, meters, requests, ('brief', 'full'), strict=True)]
    proved = pixel['assess_cold'](slot, cold, terminal, installed, truth, True, historical)
    pixel['assess_prediction'](full, cold, terminal, installed, truth)
    require(all(call['producer']['binding']['runtime_source_sha256'] == source_sha for call in (cold, full)) and
            cold['wire']['body_bytes'] == 10570 and (not historical or full['wire']['body_bytes'] == 393750),
            'public_brief_or_archived_full_size_or_source_drift')
    local_scope = proved['pixel_shortfall']['scope_id']
    cold_summary, full_summary = [phase_summary(call, is_cold, local_scope)
                                  for call, is_cold in ((cold, True), (full, False))]
    frames = proved['frames']
    selected_wire = [digest(data) for _, data in cold['images']]
    return {'label': label, 'arm': arm, 'status': 'completed', 'passed': True, 'native': native,
            'source_sha256': source_sha, 'product_distribution_version': identity['distribution_version'],
            'slot_result_sha256': digest(result_path.read_bytes()),
            'publication_sha256': digest(publication_path.read_bytes()),
            'native_PID': ready['native_pid'], 'product_PID': ready['product_PID'],
            'owned_window_ns': [started_at, published_at],
            'owned_window_ms': ms(started_at, published_at),
            'startup_to_ready_ms': ms(started_at, result['ready_ns']),
            'request_sequence_ms': ms(events[0]['started_ns'], events[-1]['closed_ns']),
            'request_sequence_rpc_sum_ms': sum(call['timing']['server_rpc_ms'] for call in (cold, full)),
            'final_request_to_publication_ms': ms(events[-1]['closed_ns'], published_at),
            'published_PNG_sha256': selected_wire, 'frames': frames, 'pixel_shortfall': proved['pixel_shortfall'],
            'CLI_reconstruction': proved['CLI_reconstruction'], 'retained_global_index': retained_index(cold, full),
            'budget': verify_ledger(result, label), 'cold': cold_summary, 'no_image_full': full_summary}


def compare_quality(first, second):
    fields = ('view', 'object_name', 'image_sha256', 'NPZ_sha256', 'png_bytes', 'npz_bytes',
              'declared_array_payload_bytes', 'independent_pixels')
    require(first['published_PNG_sha256'] == second['published_PNG_sha256'] and
            len(first['frames']) == len(second['frames']) == 3 and
            all(all(a[key] == b[key] for key in fields) for a, b in
                zip(first['frames'], second['frames'], strict=True)) and
            {k: v for k, v in first['pixel_shortfall'].items() if k != 'scope_id'} ==
            {k: v for k, v in second['pixel_shortfall'].items() if k != 'scope_id'} and
            first['retained_global_index'] == second['retained_global_index'],
            'paired_or_archived_PNG_NPZ_evidence_or_visible_current_geometry_changed')
    for phase in PHASES:
        a, b = first[phase], second[phase]
        require(a['normalized_public_sha256'] == b['normalized_public_sha256'] and
                {k: v for k, v in a['work'].items() if k != 'frustum_proof_ns'} ==
                {k: v for k, v in b['work'].items() if k != 'frustum_proof_ns'},
                'paired_or_archived_public_semantics_and_scene_work_changed/' + phase)


def compare_pair(a, b):
    require(a['passed'] and b['passed'], 'one_or_both_attempted_slots_failed_quality')
    compare_quality(a, b)
    values = [s['cold']['timing']['producer_stages_ms']['index_global'] for s in (a, b)]
    rpc = [s['cold']['timing']['server_rpc_ms'] for s in (a, b)]
    timing_keys = ('owned_window_ms', 'startup_to_ready_ms', 'request_sequence_ms', 'request_sequence_rpc_sum_ms',
                   'final_request_to_publication_ms')
    return {'A': a['label'], 'B': b['label'], 'passed': True, 'cold_index_A_B_ms': values,
            'cold_index_reduction_percent': 100 * (values[0] - values[1]) / values[0],
            'cold_RPC_A_B_ms': rpc, 'cold_RPC_delta_ms': rpc[1] - rpc[0], 'cold_RPC_improved': rpc[1] < rpc[0],
            'wall_candidate_minus_baseline_ms': {key: b[key] - a[key] for key in timing_keys},
            'wire_bytes_candidate_minus_baseline': {phase: {
                key: b[phase]['wire'][key] - a[phase]['wire'][key] for key in
                ('body_bytes', 'PNG_bytes', 'rpc_bytes', 'producer_archive_bytes')} for phase in PHASES}}


def load_pins():
    requests = tuple(read(NS / 'inputs' / name) for name in ('REQUEST.json', 'PREDICTION.json'))
    require(all(pixel['exact_request'](req, include, detail) for req, include, detail in
                zip(requests, (True, False), ('brief', 'full'), strict=True)), 'fixed_request_forms_changed')
    truth_sha = pixel['TRUTH_SHA']
    truth = json.loads(verified(pixel['TRUTH'], truth_sha, pixel['ASSEMBLY']))
    old_binding = PIXEL / 'install/PRODUCT_RUN_BINDING.json'
    old = read(old_binding)
    require(old['source_sha256'] == OLD_SOURCE, 'archived_pixel_install_not_the_current_A_reference')
    sys.path.insert(0, old['dependency_root'])
    historical = inspect_slot(ARCHIVED / 'slots/P1', requests, truth, old_binding,
                              digest((PIXEL / 'FROZEN.json').read_bytes()), archived_verifier())
    return requests, truth, historical


def review(runtime, bindings, labels, pair_numbers):
    requests, truth, archive = load_pins()
    freeze_sha = digest((NS / 'FROZEN.json').read_bytes())
    installed = {arm: read(path) for arm, path in bindings.items()}
    require(installed['A']['source_sha256'] == OLD_SOURCE != installed['B']['source_sha256'] and
            installed['A']['dependency_root'] == installed['B']['dependency_root'],
            'fixed_A_or_differing_B_isolated_install_missing')
    slots = {}
    for label in labels:
        path = runtime / 'slots' / label
        try:
            slot = inspect_slot(path, requests, truth, bindings[label[0]], freeze_sha)
            compare_quality(archive, slot)
            slots[label] = slot
        except Exception as error:
            result_path = path / 'SLOT_RESULT.json'
            # Keep a genuine failed runner outcome separate from a failed quality assessment.
            runtime_status = 'missing'
            if result_path.exists():
                try:
                    runtime_status = read(result_path)['status']
                except (UnicodeError, ValueError, KeyError):
                    runtime_status = 'unreadable'
            slots[label] = {'label': label, 'status': 'failed' if path.exists() else 'unrun', 'passed': False,
                            'original_runtime_status': runtime_status,
                            'slot_result_sha256': digest(result_path.read_bytes()) if result_path.exists() else None,
                            'error_type': type(error).__name__, 'error': str(error)}
    pairs = []
    for i in pair_numbers:
        a, b = f'A{i}', f'B{i}'
        try:
            pairs.append(compare_pair(slots[a], slots[b]))
        except Exception as error:
            pairs.append({'A': a, 'B': b, 'passed': False, 'error_type': type(error).__name__, 'error': str(error)})
    complete = [row for row in slots.values() if row['passed']]
    nonoverlap = all(a['owned_window_ns'][1] <= b['owned_window_ns'][0]
                     for a, b in zip(complete, complete[1:]))
    quality = nonoverlap and len(complete) == len(labels) and all(p['passed'] for p in pairs)
    successful_pairs = [p for p in pairs if p['passed']]
    reduction = median(p['cold_index_reduction_percent'] for p in successful_pairs) if successful_pairs else None
    rpc_delta = median(p['cold_RPC_delta_ms'] for p in successful_pairs) if successful_pairs else None
    rpc_improved = sum(p['cold_RPC_improved'] for p in successful_pairs)
    final = labels == ORDER
    performance = (quality and reduction >= MIN_REDUCTION and rpc_delta < 0 and
                   rpc_improved >= MIN_RPC_IMPROVEMENTS) if final else None
    slot_root = runtime / 'slots'
    extras = sorted(path.name for path in slot_root.iterdir() if path.name not in ORDER) if slot_root.is_dir() else []
    require(not extras, 'unregistered_slot_entries/' + ','.join(extras))
    denominator = original_denominator(runtime, labels)
    ready_counts = {'Blender_start': 1, 'business_tool': 2, 'raster_attempt': 3,
                    'raster_actual_or_lower_bound': 3, 'raster_upper_bound': 3,
                    'pending_or_unconfirmed_rasters': 0}
    require(all(denominator[row['label']] == ready_counts for row in complete),
            'published_slot_and_original_attempt_ledger_disagree')
    return {'schema': SCHEMA, 'passed': quality and (not final or performance is True),
            'quality_passed': quality, 'performance_passed': performance,
            'freeze_sha256': freeze_sha, 'registered_order': list(ORDER), 'reviewed_slot_order': list(labels),
            'verified_nonoverlap_in_frozen_order': nonoverlap, 'passed_slot_count': len(complete),
            'attempted_owned_slots': sum((runtime / 'slots' / label).exists() for label in labels),
            'known_verified_budget': dict(sum((Counter(s['budget']) for s in complete), Counter())),
            'original_admissions_even_when_slot_failed': denominator,
            'fixed_asset_sha256': truth['asset_sha256'], 'historical_archive_sha256': OLD_ARCHIVE,
            'fixed_baseline_source_sha256': OLD_SOURCE,
            'candidate_source_sha256': installed['B']['source_sha256'],
            'median_cold_index_reduction_percent': reduction, 'cold_index_threshold_percent': MIN_REDUCTION,
            'median_cold_RPC_delta_ms': rpc_delta, 'cold_RPC_improved_pairs': rpc_improved,
            'cold_RPC_improved_pairs_required': MIN_RPC_IMPROVEMENTS, 'slots': list(slots.values()), 'pairs': pairs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--baseline', type=Path, default=PIXEL / 'install/PRODUCT_RUN_BINDING.json')
    parser.add_argument('--candidate', type=Path, default=NS / 'install/PRODUCT_RUN_BINDING.json')
    parser.add_argument('--output', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--slot', choices=ORDER)
    mode.add_argument('--pair', type=int, choices=(1, 2, 3))
    mode.add_argument('--archived-replay', action='store_true')
    args = parser.parse_args()
    labels, pairs = ORDER, (1, 2, 3)
    if args.slot:
        labels, pairs = (args.slot,), ()
    elif args.pair:
        pairs = (args.pair,)
        labels = ORDER[(args.pair - 1) * 2:args.pair * 2]
    try:
        if args.archived_replay:
            _, _, archived = load_pins()
            result = {'schema': SCHEMA, 'passed': True, 'archived_only': True, 'slot': archived}
        else:
            result = review(args.runtime, {'A': args.baseline, 'B': args.candidate}, labels, pairs)
    except Exception as error:
        result = {'schema': SCHEMA, 'passed': False, 'error_type': type(error).__name__, 'error': str(error)}
    if args.pair:
        receipt = dict(result)
        receipt['slot_result_sha256'] = {row['label']: row['slot_result_sha256'] for row in result.get('slots', [])}
        put(args.runtime / 'preflight/pair_checks' / f'AFTER_PAIR_{args.pair:02d}.json', receipt)
    if args.output:
        put(args.output, result)
    elif not (args.slot or args.pair or args.archived_replay):
        put(HERE / 'LIVE_REVIEW.json', result)
    print(json.dumps({key: result[key] for key in ('passed', 'quality_passed', 'performance_passed',
          'median_cold_index_reduction_percent', 'median_cold_RPC_delta_ms', 'error_type', 'error') if key in result} |
          {'failed_slots': [slot for slot in result.get('slots', []) if not slot['passed']],
           'failed_pairs': [pair for pair in result.get('pairs', []) if not pair['passed']]}, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
