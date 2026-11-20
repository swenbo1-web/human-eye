"""Score the two rail trials from independently bound source and original tool evidence."""

import argparse
from collections import Counter
from fractions import Fraction
from itertools import accumulate
import json
from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
RUN = Path('D:/he_m4_rail_blocker_consumption_001')
ASSET = Path('D:/he_m4_cross_scale_live_task_001/fixture/main.blend')
ASSET_SHA = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
SOURCE = Path('D:/he_m4_cross_scale_cold_frustum_001/slots/B1/TERMINAL_SOURCE.json')
SOURCE_SHA = '31e69a857baf1f66e33722dec5ef63086565c0fbf3029c39071415782c7a0233'
TRUTH = NS / 'truth/CURRENT_TRUTH.json'
BINDINGS = {arm: V / directory / 'install/PRODUCT_RUN_BINDING.json' for arm, directory in (
    ('A', 'm4_dense_region_brief_001'), ('B', 'm4_bound_blocker_evidence_001'))}
SLOTS = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
REQUEST = {'query': {'mode': 'active_observation', 'region_task': {
    'area_min_m2': 0.25, 'area_max_m2': 0.25, 'normal_z_min': 0}},
    'include_image': True, 'response_detail': 'brief'}

SHARED = V / 'm4_dense_panel_sweep_formal_001/scoring/score.py'
BLOCKER_CHECK = V / 'm4_bound_blocker_evidence_001/checks/live_review.py'
GEOMETRY_CHECK = V / 'm4_bound_blocker_evidence_001/checks/geometry_controls.py'
shared, blocked, geometry = (runpy.run_path(str(path)) for path in (SHARED, BLOCKER_CHECK, GEOMETRY_CHECK))
digest, read, require, verified, write = (shared[key] for key in ('digest', 'read', 'require', 'verified', 'write'))
region_key, region_label = shared['region_key'], shared['region_label']
inspect_frame, product_probe = shared['inspect_frame'], shared['product_probe']


def rail_truth():
    value = read(TRUTH)
    keys = [region_key(row) for row in value['eligible']]
    require(value['passed'] is True and value['asset_sha256'] == ASSET_SHA and value['terminal_sha256'] == SOURCE_SHA and
            value['counts'] == {'objects': 21, 'vertices': 148, 'triangles': 184} and len(set(keys)) == len(keys) == 4 and
            sorted(Counter(name for name, _ in keys).values()) == [2, 2], 'independent_rail_truth_is_incomplete')
    return value


def current_source(slot, result):
    formal = shared['original']['FORMAL']
    started, ready, closed = formal['generic_process'](
        slot, ASSET.resolve(), (slot / 'native/input.blend').resolve(), ASSET_SHA, result['owned_deadline_ns'])
    initial, terminal = result['initial_source'], result['terminal_source']
    first = formal['read_capture'](slot, slot / 'initial_capture/TERMINAL_SOURCE.json', initial, started['pid'], ASSET_SHA)
    last = formal['read_capture'](slot, slot / 'TERMINAL_SOURCE.json', terminal, started['pid'], ASSET_SHA)
    require(started['created_after_ns'] <= first['started_ns'] <= initial['worker']['file_closed_ns'] <=
            result['ready_ns'] <= result['cleanup_started_ns'] <= last['started_ns'] <=
            terminal['worker']['file_closed_ns'] <= closed['closed_ns'] <= result['owned_deadline_ns'],
            'current_source_readbacks_do_not_bracket_request')
    stable = ('source', 'objects', 'source_face_offsets', 'display_object_mask', 'display_scope',
              'display_read', 'layer_collections', 'scene_cameras')
    require(all(first[key] == last[key] for key in stable), 'current_source_or_display_changed')
    saved = json.loads(verified(SOURCE, SOURCE_SHA, SOURCE.parent))
    fixtures = {row['name']: row for row in saved['objects']}
    evaluated = last['objects']
    require(len(evaluated) == len(fixtures) == len({row['name'] for row in evaluated}) == 21 and
            sum(len(row['evaluated']['vertices']) for row in evaluated) == 148 and
            last['source_face_offsets'] == [0, *accumulate(len(row['evaluated']['triangles']) for row in evaluated)] and
            last['source_face_offsets'][-1] == 184 and last['display_object_mask'] == [row['visible_get'] for row in evaluated],
            'current_fixture_roster_or_display_offsets_invalid')
    persistent_source = ('asset_sha256', 'frame', 'subframe', 'scene', 'view_layer', 'unit_settings')
    require(all(last['source'][key] == saved['source'][key] for key in persistent_source), 'current_source_config_changed')
    stable_mesh = ('mesh_name', 'matrix_world', 'native_matrix_world', 'visible_get', 'display',
                   'parent', 'modifiers', 'native', 'evaluated')
    for row in evaluated:
        name = row['name']
        require(all(row[key] == fixtures[name][key] for key in stable_mesh), 'current_fixture_mesh_changed/' + name)
    return last, {'initial_sha256': initial['sha256'], 'terminal_sha256': terminal['sha256'],
                  'fixture_terminal_sha256': SOURCE_SHA, 'unchanged_fingerprint': ready['initial_fingerprint'],
                  'owned_copy_sha256': ASSET_SHA, 'visible_objects': sum(last['display_object_mask'])}


def full_or_brief(result):
    """Decode the existing v2 table while keeping the original extension and PNG bytes in evidence."""
    first = shared['audit_source']['facts_from_first'](result['content'])
    if first.get('schema') == shared['schema']['V2'] and 'blocker_evidence' in first:
        legacy = {key: value for key, value in first.items() if key != 'blocker_evidence'}
        result = {**result, 'content': [{'type': 'text', 'text': json.dumps(legacy)}, *result['content'][1:]]}
    return shared['full_or_brief'](result)


def independent_hit(target, direction, name, triangle):
    proof = target['finite_direction_proofs'][direction]
    hits = [row for row in proof['positive_area_occluders']
            if row['object_name'] == name and row['source_triangle_index'] == triangle]
    require(type(triangle) is int and proof['status'] == 'positive_area_occlusion' and len(hits) == 1,
            'blocker_is_not_an_independently_proven_current_source_triangle')
    area = Fraction(hits[0]['projected_target_plane_area_m2_exact'])
    require(area > 0, 'blocker_overlap_is_not_strictly_positive')
    return area


def verify_blockers(body, producer, terminal, truth):
    """Bind each compact blocker to the exact current source and independently replay its overlap."""
    bindings, task = producer['binding'], producer['facts']['region_task']
    internal, public = task['blocker_evidence'], body['blocker_evidence']
    require(set(internal) == {'scope_id', 'binding_sha256', 'source_binding_sha256', 'camera_identity', 'rows'} and
            internal['scope_id'] == 'global' and all(internal[key] == bindings[key]
                for key in ('binding_sha256', 'source_binding_sha256', 'camera_identity')),
            'blocker_producer_not_bound_to_the_current_global_source')
    require(set(public) == {'scope_index', 'columns', 'rows', 'meaning'} and tuple(public['columns']) == blocked['COLUMNS'] and
            public['meaning'] == blocked['MEANING'] and len(public['rows']) == len(internal['rows']),
            'public_blocker_table_disagrees_with_producer')
    indexed = blocked['indexed']
    scope = dict(zip(body['scopes']['columns'], indexed(body['scopes']['rows'], public['scope_index'],
        'invalid_public_blocker_scope'), strict=True))
    require(scope['scope_id'] == 'global' and all(scope[k] == bindings[k] for k in ('camera_identity', 'binding_sha256')),
            'public_blocker_wrong_scope')
    global_scope, = [item['binding'] for item in producer['scopes'] if item['scope_id'] == 'global']
    require(global_scope == bindings, 'producer_global_camera_binding_changed')
    poses = {row['name']: row for row in global_scope['camera_specification']['views']}
    terminal_objects = {item['name']: item for item in terminal['objects']}
    targets = {region_key(row): row for row in truth['eligible']}
    target_columns = body['region_task']['columns']
    seen, records = set(), []
    for compact, actual in zip(public['rows'], internal['rows'], strict=True):
        ri, direction, oi, ti = compact
        source = indexed(task['rows'], ri, 'blocker_target_region_index_invalid')
        public_source = indexed(body['region_task']['rows'], ri, 'blocker_public_region_index_invalid')
        key = region_key(source)
        require(set(actual) == blocked['ORIGINAL_KEYS'] and (ri, direction) not in seen and
                all(type(value) is int for value in (ri, oi, ti)) and
                (actual['roi_id'], actual['view_name'], actual['blocker_object_index'], actual['source_triangle_index']) ==
                (public_source[target_columns.index('roi_id')], direction, oi, ti) and actual['roi_id'] == source['roi_id'] and
                source['status'] == 'unknown' and source['reason'] == blocked['UNKNOWN'] and
                direction in source['view_reasons']['positive_area_occlusion'] and source['complete_witness'] is None,
                'blocker_not_bound_to_the_same_unknown_region_and_view')
        seen.add((ri, direction))
        obj = indexed(bindings['objects'], oi, 'invalid_current_blocker_object')
        public_obj = dict(zip(body['objects']['columns'], indexed(body['objects']['rows'], oi,
            'invalid_public_blocker_object'), strict=True))
        name = obj['object_name']
        current = terminal_objects[name]
        mesh = current['evaluated']
        triangle = indexed(mesh['triangles'], ti, 'blocker_current_source_triangle_out_of_range')
        points = [mesh['vertices_world_m'][idx] for idx in triangle]
        require(obj == public_obj and obj['object_index'] == oi and obj['host_id'] == current['object_id'] == actual['blocker_host_id']
                and obj['instance_id'] == current['instance_id'] == actual['blocker_instance_id'] and current['visible_get']
                and actual['triangle_geometry_id'] == blocked['triangle_key_sha'](points), 'blocker_object_identity_changed')
        target = targets.get(key)
        if target is None:
            continue  # Models may legitimately query task conditions outside this question.
        pose = poses[direction]
        area = independent_hit(target, direction, name, ti)
        geometry_check = shared['original']['prior']['same_geometry']
        geometry_check(source, target, terminal_objects[key[0]], bindings)
        chart, screen = geometry['independent_overlap'](points, geometry['region_corners'](source), pose)
        require(pose['direction_rational'] == truth['directions'][direction] and chart > 0 and screen > 0 and
                chart / 4 == area and type(actual['overlap_area_screen_exact']) is str and
                Fraction(actual['overlap_area_screen_exact']) == screen, 'blocker_exact_replay_or_pose_changed')
        records.append({'region': region_label(key), 'view': direction, 'blocker_object_name': name,
                        'source_triangle_index': ti, 'projected_target_plane_area_m2_exact': str(area),
                        'screen_overlap_exact': str(screen), 'target_roi_id': source['roi_id']})
    return records


def audit_slot(slot, seal, packet, truth, installed, arm):
    audit = shared['audit_slot']
    globals_ = audit.__globals__
    prior_decoder = globals_['full_or_brief']
    globals_['full_or_brief'] = full_or_brief
    try:
        frames, ledger = audit(slot, seal, packet, truth, installed, evidence_root=NS)
    finally:
        globals_['full_or_brief'] = prior_decoder
    for attempt in ledger['attempts']:
        attempt['validated_blockers'] = []
        if (attempt.get('requested_detail') != 'brief' or not attempt.get('fixed_CLI_whole_content') or
                attempt.get('evidence_error') or not attempt.get('product') or not attempt['regions']):
            continue
        try:
            wire = json.loads(verified(attempt['RX']['path'], attempt['RX']['sha256'], slot))
            body = json.loads(wire['result']['content'][0]['text'])
            if 'blocker_evidence' not in body:
                continue
            require(arm == 'B', 'baseline_public_brief_unexpectedly_contains_candidate_blocker_evidence')
            archive = attempt['product']['producer_delivery']['path']
            producer = json.loads(verified(archive['path'], archive['sha256'], slot))
            attempt['validated_blockers'] = verify_blockers(body, producer, packet, truth)
        except (KeyError, OSError, TypeError, ValueError, ZeroDivisionError) as error:
            attempt['blocker_evidence_error'] = {'type': type(error).__name__, 'reason': str(error)}
    return frames, ledger


def evidence():
    truth = rail_truth()
    freeze_path = NS / 'FROZEN.json'
    freeze = digest(freeze_path.read_bytes())
    pins = {Path(row['path']).resolve(): row['sha256'] for row in read(freeze_path)['direct_inputs']}
    inputs = (HERE / 'score.py', HERE / 'RUBRIC.md', TRUTH, ASSET, SOURCE, *BINDINGS.values())
    for path in inputs:
        require(pins.get(path.resolve()) == digest(path.read_bytes()), 'unfrozen_formal_scoring_input/' + path.name)
    qualification_path = NS / 'QUALIFICATION.json'
    qualification = read(qualification_path)
    qualified = qualification['passed'] is True
    require(qualification['freeze_sha256'] == freeze and
            [row['label'] for row in qualification['slots']] == ['QA', 'QB'] and
            qualified == all(row.get('passed') is True for row in qualification['slots']), 'rail_qualification_contract_changed')
    gate = digest(qualification_path.read_bytes())
    seals = read(NS / 'ANSWERS_SEALED.json')['answers']
    require(tuple(row['slot'] for row in seals) == SLOTS, 'sealed_formal_denominator_changed')
    records = []
    for seal in seals:
        label = seal['slot']
        arm = label[0]
        slot = RUN / 'slots' / label
        record = {'slot': label, 'arm': arm, 'status': seal['status'], 'answer_sha256': seal['sha256']}
        records.append(record)
        if seal['status'] == 'unrun':
            require(not slot.exists() and seal['path'] is None, 'unrun_slot_has_actual_original/' + label)
            continue
        require(qualified, 'formal_slot_has_run_despite_qualification_gate')
        try:
            outcome_path = slot / 'SLOT_RESULT.json'
            outcome, publication = (read(path) for path in (outcome_path, slot / 'SLOT_PUBLICATION.json'))
            binding_path = BINDINGS[arm]
            installed = read(binding_path)
            require(outcome['label'] == publication['label'] == label and
                    publication['result_sha256'] == seal['slot_result_sha256'] == digest(outcome_path.read_bytes()) and
                    publication['published_ns'] == seal['published_ns'] and publication['status'] == seal['status'] and
                    outcome['freeze_sha256'] == freeze and outcome['qualification_sha256'] == gate and
                    outcome['asset_sha256'] == truth['asset_sha256'] and outcome['arm'] == arm and
                    outcome['product_git'] == installed['preparation_git'] and
                    outcome['product_source_sha256'] == installed['source_sha256'] and
                    outcome['product_binding_sha256'] == pins[binding_path.resolve()] and
                    (outcome['group'], outcome['phase']) == ('P', 'formal') and outcome['paid_API_calls'] == 0,
                    'sealed_answer_is_not_current_two_arm_slot_publication')
            if installed['dependency_root'] not in sys.path:
                sys.path.insert(0, installed['dependency_root'])
            packet, read_only = current_source(slot, outcome)
            record['current_read_only'] = read_only
            record['frames'], record['tools'] = audit_slot(slot, seal, packet, truth, installed, arm)
            attempts = [row['attempt'] for row in record['tools']['attempts']]
            require(attempts == list(range(1, len(attempts) + 1)), 'formal_attempt_sequence_has_gaps')
            record['first_actual_tool_is_frozen_brief'] = bool(attempts) and (
                record['tools']['attempts'][0].get('product') or {}).get('arguments') == REQUEST
        except (KeyError, OSError, TypeError, ValueError, ZeroDivisionError) as error:
            record['evidence_error'] = {'type': type(error).__name__, 'reason': str(error)}
    return {'schema': 'm4-rail-blocker-formal-evidence-v1', 'freeze_sha256': freeze,
            'qualification_sha256': gate, 'qualification_passed': qualified,
            'answers_sealed_sha256': digest((NS / 'ANSWERS_SEALED.json').read_bytes()),
            'independent_truth_sha256': pins[TRUTH.resolve()], 'formal_denominator': len(SLOTS), 'slots': records}


def score_outcome(outcome, target, reference, frames, answer):
    shared['quoted'](answer, outcome['quote'])
    if outcome['kind'] == 'witness':
        shared['quoted'](answer, outcome['ref'])
        delivered = shared['measured_outcome'](target, reference, outcome, frames)
        return {'witness_deliveries': delivered}
    require(outcome['kind'] == 'geometric_occlusion', 'original_answer_has_no_supported_image_or_blocker')
    require(not outcome.get('claims_all_pixels_hidden'), 'claim_exceeds_positive_area_occlusion_evidence')
    shared['measured_outcome'](target, reference, outcome, frames)
    direction = outcome['direction']
    name, triangle = outcome['blocker_object_name'], outcome['source_triangle_index']
    shared['quoted'](answer, name)
    area = independent_hit(target, direction, name, triangle)
    return {'blocker': {'region': reference, 'view': direction, 'blocker_object_name': name,
                        'source_triangle_index': triangle, 'projected_target_plane_area_m2_exact': str(area)}}


def grade_slot(record, claim, answer, truth, sizes):
    quote = shared['quoted']
    require(claim['answer_sha256'] == record['answer_sha256'] == digest(answer.encode()),
            'manual_transcription_not_bound_to_original_reply')
    targets = {region_key(row): row for row in truth['eligible']}
    attempts = record.get('tools', {}).get('attempts', [])
    routes = [row for attempt in attempts if attempt.get('fixed_CLI_whole_content') and
              not attempt.get('evidence_error') for row in attempt['regions']]
    first = attempts[0] if attempts and record.get('first_actual_tool_is_frozen_brief') else {}
    first_blockers = first.get('validated_blockers', [])
    first_adopted = set()
    rows, seen = [], Counter()
    for row in claim['rows']:
        checked = {'object_name': row['object_name'], 'geometry_passed': False, 'evidence_passed': False}
        rows.append(checked)
        try:
            quote(answer, row['quote'])
            key = shared['parse_source'](row, routes, sizes)
            reference = region_label(key)
            checked['region'] = reference
            seen[key] += 1
            target = targets[key]
            for field in ('center_world_m', 'unit_normal'):
                require(all(shared['close_number'](a, b) for a, b in zip(row[field], target[field], strict=True)),
                        field + '_outside_fixed_tolerance')
            checked['geometry_passed'] = True
            outcome = score_outcome(row['outcome'], target, reference, record.get('frames', {}), answer)
            checked.update(outcome, evidence_passed=True)
            blocker = outcome.get('blocker')
            if blocker:
                deliveries = [attempt['attempt'] for attempt in attempts if any(
                    all(row[key] == value for key, value in blocker.items()) for row in attempt['validated_blockers'])]
                checked['matching_candidate_delivery_attempts'] = deliveries
                if any(all(row[key] == value for key, value in blocker.items()) for row in first_blockers):
                    first_adopted.add(reference)
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
            checked['issue'] = str(error)
    pairs = []
    expected_pairs = {row['object_name'] for row in truth['pairs']}
    for pair in claim['pairs']:
        quote(answer, pair['quote'])
        quote(pair['quote'], pair['object_name'])
        pairs.append(pair['object_name'])
    pair_quality = len(pairs) == len(expected_pairs) and set(pairs) == expected_pairs
    contradictions = claim['extra_assertions']
    for issue in contradictions:
        quote(answer, issue['quote'])
        require(type(issue['issue']) is str and issue['issue'], 'unsupported_assertion_requires_assessment')
    geometry_passed = set(seen) == targets.keys() and all(value == 1 for value in seen.values())
    complete = (record['status'] == 'completed' and bool(record.get('current_read_only')) and
                not record.get('evidence_error') and geometry_passed and pair_quality and not contradictions and
                all(row['geometry_passed'] and row['evidence_passed'] and 'issue' not in row for row in rows))
    needed_blockers = {region_label(key) for key, row in targets.items() if not row['eligible_complete_views']}
    return {'slot': record['slot'], 'arm': record['arm'], 'status': record['status'], 'answer_sha256': record['answer_sha256'],
            'passed_quality': bool(complete), 'pair_quality': pair_quality, 'pairs': pairs,
            'first_actual_tool_is_frozen_brief': bool(first),
            'first_brief_region_fact_count': len(first.get('regions', [])),
            'first_brief_witness_regions_used': sorted(row['region'] for row in rows if any(
                hit['attempt'] == first.get('attempt') and hit['origin'] == 'product'
                for hit in row.get('witness_deliveries', []))),
            'blocker_facts_adopted': first_adopted == needed_blockers,
            'first_candidate_blocker_regions_used': sorted(first_adopted),
            'missing_regions': sorted(region_label(key) for key in targets.keys() - seen.keys()),
            'duplicates': sorted(region_label(key) for key, count in seen.items() if count > 1),
            'contradictions': contradictions, 'rows': rows}


def grade(evidence_record, claims):
    require(evidence_record == evidence(), 'formal_evidence_does_not_match_originals')
    truth = rail_truth()
    source = json.loads(verified(SOURCE, SOURCE_SHA, SOURCE.parent))
    sizes = {row['name']: len(row['evaluated']['triangles']) for row in source['objects']}
    seals = {row['slot']: row for row in read(NS / 'ANSWERS_SEALED.json')['answers']}
    expected = {label for label, seal in seals.items() if seal['path'] is not None}
    require(claims.keys() == expected, 'manual_claims_must_cover_the_actual_original_answers')
    outputs = []
    for record in evidence_record['slots']:
        label = record['slot']
        if label not in expected:
            outputs.append({'slot': label, 'arm': record['arm'], 'status': record['status'], 'passed_quality': False,
                            'blocker_facts_adopted': False, 'reason': 'no_sealed_answer', 'rows': []})
            continue
        seal = seals[label]
        answer = verified(seal['path'], seal['sha256'], NS).decode()
        outputs.append(grade_slot(record, claims[label], answer, truth, sizes))
    return {'schema': 'm4-rail-blocker-formal-quality-v1', 'formal_denominator': len(SLOTS),
            'answers_sealed_sha256': evidence_record['answers_sealed_sha256'],
            'evidence_sha256': digest((HERE / 'FORMAL_EVIDENCE.json').read_bytes()),
            'independent_truth_sha256': evidence_record['independent_truth_sha256'], 'slots': outputs,
            'complete_counts': {arm: sum(row['passed_quality'] for row in outputs if row['arm'] == arm) for arm in ('A', 'B')},
            'blocker_adoption_count': sum(row['blocker_facts_adopted'] for row in outputs if row['arm'] == 'B')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('evidence', 'grade'))
    parser.add_argument('--claims', type=Path)
    args = parser.parse_args()
    if args.action == 'evidence':
        write(HERE / 'FORMAL_EVIDENCE.json', evidence())
    else:
        require(args.claims is not None, 'sealed_manual_claim_transcriptions_required')
        write(HERE / 'QUALITY.json', grade(read(HERE / 'FORMAL_EVIDENCE.json'), read(args.claims)))
