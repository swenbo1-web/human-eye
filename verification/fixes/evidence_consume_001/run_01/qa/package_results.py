"""Offline answer packaging and explicit author scoring; no new consumer work."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text('utf-8-sig'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


bindings = read(ROOT/'dispatch/BINDINGS.json')['bindings']
usage = read(ROOT/'audit/MODEL_USAGE.json')
costs = read(ROOT/'audit/COSTS.json')
by_id = {row['binding']['answer_id']: row for row in usage['consumers']}
assert len(bindings) == len(by_id) == 8 and not usage['issues']
truth = {case: read(ROOT/'author'/case/'TRUTH.json') for case in ('S','G')}
truth_ids = dict(S='T1', G='T2')
public_truths = []
for case in ('S','G'):
    source = truth[case]
    public_truths.append(dict(truth_id=truth_ids[case], coordinate_unit='m', coordinate_frame='world',
        vertices_per_mesh=source['vertices_per_mesh'], triangles_per_mesh=source['triangles_per_mesh'],
        construction=source['construction'], expected=source['expected'], exact_answer=source['exact_answer'],
        proof=source['proof'], source='independent frozen assignment construction, not product outputs',
        original_truth_sha256=sha(ROOT/'author'/case/'TRUTH.json')))
questions = [dict(answer_id=row['answer_id'], question=row['question'], truth_id=truth_ids[row['case']])
             for row in sorted(bindings, key=lambda row: row['answer_id'])]
save(ROOT/'public/QUESTIONS_AND_TRUTH.json', dict(schema='unlabeled-questions-truth-v1', questions=questions,
    truths=public_truths, rubric=dict(distance_tolerance_m=1e-6, direction_component_tolerance=1e-6,
        nonmanifold_edge_definition='triangle edge incidence strictly greater than two; boundary incidence one separately',
        solid='surface intersection alone cannot establish a closed-solid penetration or nonpenetration result',
        evidence='valid current fact references or native proof accepted; independent recomputation not required'),
    masking='No N/P/wording condition labels in package headers. Exact question wording and answer bodies may reveal condition; not fully blind.'))
lines = ['# 公开答案包', '',
    '本包使用预先打乱的中性编号，不附工具条件或措辞标签。原回答的来源说明与链接完整保留，正文可能自行暴露条件，因此不承诺完全盲评。晚答保留原文并作中性期限标记。', '',
    '独立问题、真值与评分定义见 [QUESTIONS_AND_TRUTH.json](QUESTIONS_AND_TRUTH.json)。', '']
for row in questions:
    text = (ROOT/'public/answers'/(row['answer_id']+'.txt')).read_text('utf8')
    lines += ['## '+row['answer_id'], '', '问题：'+row['question'], '', text, '']
(ROOT/'public/ANSWERS.md').write_text('\n'.join(lines), encoding='utf8')

mapping = [dict(answer_id=row['answer_id'], sequence=row['sequence'], chain_id=row['chain_id'],
    case=row['case'], condition=row['condition'], wording=row['wording'],
    agent_path=row['agent_path'], thread_id=by_id[row['answer_id']]['model_usage']['thread_id'],
    prompt_path=row['prompt_path'], prompt_sha256=row['prompt_sha256'],
    private_exact_answer='answers_private/'+row['chain_id']+'.txt') for row in bindings]
save(ROOT/'analysis/CONDITION_MAP.json', dict(mapping=mapping, masking='Open only after independent public-answer grading.'))

grades = []
for row in bindings:
    model = by_id[row['answer_id']]['model_usage']
    assert model['completed_turn_count'] == 1 and model['usage_complete_from_observed_counters']
    common = dict(answer_id=row['answer_id'], chain_id=row['chain_id'],
        exact_public_answer_sha256=by_id[row['answer_id']]['public_final_sha256'],
        within_frozen_dispatch_answer_budget=model['within_answer_budget'],
        dispatch_to_public_final_seconds=model['dispatch_to_public_final_seconds'],
        no_retry_or_replacement=True)
    if row['case'] == 'S':
        criteria = dict(distance_3_over_32_m=1, ordered_direction_n_over_3=1, boundary_edges_10_each=1,
            nonmanifold_over_two_0_each=1, unit_and_order=1, current_evidence_and_source=1)
        common.update(criteria=criteria, content_target_coverage='6/6',
            topology_presentation=('explicit alternative definitions: 10 including boundary, 0 for incidence>2; primary label ambiguous'
                if row['condition']=='N' else 'separate boundary10/nonmanifold0'))
    else:
        criteria = dict(distance_zero_m=1, zero_direction_not_applicable=1, solid_currently_undetermined=1,
            no_false_solid_penetration_or_nonpenetration=1, current_geometric_basis_and_source=1)
        common.update(criteria=criteria, content_target_coverage='5/5',
            topology_presentation='open surface explanation supported; topology counts not mandatory question output')
    common.update(author_content_targets_present=True,
        deadline_completion_credit=bool(model['within_answer_budget']),
        author_note='Author counts explicitly stated incidence>2 value0 as the requested topology answer, while flagging N terminology ambiguity for independent review.'
            if row['case']=='S' and row['condition']=='N' else 'Requested numeric/applicability/unknown distinctions retained.')
    grades.append(common)
save(ROOT/'analysis/AUTHOR_SCORE.json', dict(schema='author-score-separated-v1', answers=grades,
    public_answers=8, deadline_completions=sum(row['deadline_completion_credit'] for row in grades),
    late_answers=sum(not row['deadline_completion_credit'] for row in grades), unrun=0, replacements=0,
    scoring_policy='Content target coverage separate from deadline completion. Native definition-qualified topology explicitly flagged, not silently normalized.',
    independence='Author assessment only; coordinator should grade public package before opening this file.'))

classification = {
 'S_P_W1': [('observe','argument_validation_error_no_worker_geometry'), ('observe','sufficient_current_surface_fact_adopted')],
 'S_P_W2': [('observe','sufficient_current_surface_fact_adopted')],
 'G_P_W2': [('observe','mixed_known_surface_and_unknown_pair_adopted')],
 'G_P_W1': [('observe','mixed_known_surface_and_unknown_pair_adopted'),
             ('native_run','additional_raw_vertices_faces_modifiers_for_plane_intersection_explanation_no_numeric_solver')],
 'S_N_W1': [('native_run','metadata_topology_and_runtime_math_library_availability'),
             ('native_run','original_world_mesh_read_and_144_triangle_pair_point_face_edge_edge_intersection_solver'),
             ('native_run','projection_certificate_from_retained_geometry_no_new_raw_capture')],
 'S_N_W2': [('native_run','current_geometry_topology_capture_retained_in_native_variables'),
             ('native_run','144_triangle_pair_distance_and_intersection_solver_on_retained_geometry'),
             ('native_run','raw_topology_and_projection_certificate_reinspection')],
 'G_N_W2': [('native_run','object_metadata_inventory'), ('native_run','world_vertices_faces_and_edge_incidence_read'),
             ('native_run','analytic_planes_common_vertices_boundary_and_area_checks_from_current_mesh')],
 'G_N_W1': [('native_run','object_metadata_and_world_bounds_inventory'),
             ('native_run','evaluated_world_vertices_faces_triangles_and_modifiers_read'),
             ('native_run','current_plane_common_origin_and_boundary_certificate')],
}
behavior = []
for row in costs['chains']:
    binding, data = row['binding'], row['costs']
    chain_id = binding['chain_id']
    calls = [call for call in data['calls'] if call['consumer_public_call']]
    expected = classification[chain_id]
    assert [call['operation'] for call in calls] == [operation for operation, _ in expected]
    records = []
    for call, (_, kind) in zip(calls, expected):
        records.append(dict(sequence=call['sequence'], operation=call['operation'], classification=kind,
            request=call['source']+'/REQUEST.json', request_sha256=sha(ROOT/call['source']/'REQUEST.json')))
    is_p = binding['condition']=='P'
    behavior.append(dict(answer_id=binding['answer_id'], chain_id=chain_id, calls=records,
        HE_response_adoption_exposed=is_p, HE_current_known_facts_adopted=is_p,
        native_first_or_entirely_native=not is_p,
        additional_raw_capture_after_sufficient_HE=1 if chain_id=='G_P_W1' else (0 if is_p else None),
        after_sufficient_HE_numeric_recomputation=0 if is_p else None,
        missing_item_effective_native_evidence='not_needed_after_HE' if is_p else 'native acquisition and analytic/computational derivation',
        mixed_response_exposed=bool(is_p and binding['case']=='G'),
        mixed_known_quantity_preserved=True if is_p and binding['case']=='G' else None,
        unknown_solid_overreach=False if binding['case']=='G' else None,
        redundancy_judgment=('HE already supplied distance0, common witness, direction not applicable, boundary16 and unsupported-solid scope. Raw read adds plane/mesh narrative, no new minimum required answer fact; counts as supplementary evidence beyond sufficiency, not SAT.'
            if chain_id=='G_P_W1' else 'Native-only calls are itemized by acquisition/solver/certificate; not mislabeled as plugin distrust or SAT reruns.')))
save(ROOT/'analysis/BEHAVIOR.json', dict(answers=behavior,
    interpretation='W1/W2 impose different evidence wording. A single sample per cell cannot establish general preferences or causal product speed. Native proof reinforcement and full numeric solving remain distinct.'))

consumer_tokens = Counter()
for row in usage['consumers']:
    consumer_tokens.update(row['model_usage']['verified_token_deltas'])
protocol_totals = Counter()
for row in costs['chains']:
    protocol_totals.update({key:value for key,value in row['costs']['summary'].items() if type(value) is int})
pair_rows = []
for case in ('S','G'):
    for wording in ('W1','W2'):
        members = [row for row in costs['chains'] if row['binding']['case']==case and row['binding']['wording']==wording]
        values = {}
        for row in members:
            model = by_id[row['binding']['answer_id']]['model_usage']
            values[row['binding']['condition']] = dict(answer_id=row['binding']['answer_id'],
                within_budget=model['within_answer_budget'], tokens=model['verified_token_deltas'],
                dispatch_to_public_final_seconds=model['dispatch_to_public_final_seconds'],
                dispatch_to_task_started_seconds=model['dispatch_to_task_started_seconds'],
                reported_task_duration_ms=model['turns'][0].get('reported_duration_ms'),
                root_collection_delay_seconds=model['root_collection_delay_seconds'],
                chain_wall_seconds=row['costs']['chain_wall_seconds'], protocol=row['costs']['summary'])
        pair_rows.append(dict(case=case, wording=wording, values=values,
            scope='one fixed same-wording N/P pair; late data retained; no population inference'))
save(ROOT/'analysis/SUMMARY.json', dict(generated_utc=datetime.now(timezone.utc).isoformat(),
    denominator=8, public_finals=8, within_dispatch_budget=6, late=2, unrun=0, retries=0,
    consumer_token_totals=dict(consumer_tokens), cached_input_is_subset=True, reasoning_output_is_subset=True,
    consumer_protocol_totals=dict(protocol_totals),
    consumer_chain_wall_seconds_total=sum(row['costs']['chain_wall_seconds'] for row in costs['chains']),
    same_wording_pairs=pair_rows, preparation_and_audit_model_usage=usage['preparation_and_audit_usage'],
    provider_request_count=None, fees=None, exact_backend_verified=False, pro_identity_verified=False,
    scope='All eight attempts, including late answers and failed tool request; auxiliary costs separate; root usage only through audit read.'))
save(ROOT/'audit/CORRECTIONS.json', dict(
    protected_dispatch='An exploratory check initially treated protected ciphertext hash mismatch as plaintext prompt difference. That inference was withdrawn; only ciphertext existence/length/hash retained. No decryption or ciphertext body export.',
    auxiliary_turn_shells='Initial audit included inherited parent turn shells with zero token events in completeness flags. Final script excludes only those zero-usage shells; numeric own-child token totals unchanged. Initial outputs and script snapshot retained.',
    deadlines='Parent polling did not interrupt attempts02/03 at dispatch+150; public finals arrived15.815303/10.042205sec late, with actual host durations145255/138552ms. Both retained and receive no deadline completion credit; no retry/replacement and no other budget adjustment.',
    experiment_compatibility_recoveries=0, additional_model_answers=0, product_changes=0))
print(json.dumps(dict(public_answers=8, within_budget=6, late=2,
    consumer_tokens=consumer_tokens['total_tokens'], public_calls=protocol_totals['public_calls'])))
