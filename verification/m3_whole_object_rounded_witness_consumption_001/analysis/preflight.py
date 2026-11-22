"""Exercise archived wire and direct adoption edge cases without starting a slot."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
X = run_path(str(HERE / 'consumption.py'))
V, R, P, OLD, C, M = (X[key] for key in ('V', 'REFERENCES', 'P', 'OLD', 'C', 'M'))
require, read = X['require'], X['read']
HISTORICAL = Path('D:/he_m3_whole_object_witness_triangle_consumption_001')
EXACT_CASE = Path('D:/he_m3_whole_object_rounded_witness_001/candidate_evidence/cases/tree_n02_n03')


def pin(path):
    return C['file_receipt'](path)


def ref_checks(grade, ref):
    return grade['checks'][f'{ref}_actual_point_pair_and_triangle_membership']['verified']


def sample_trace(*, with_source):
    trace, checks = [], {}
    for i, ref in enumerate(R, start=1):
        metric = {'metres': 1., 'direction': [1., 0., 0.], 'point_a': [0., 0., 0.], 'point_b': [1., 0., 0.],
                  'membership': {'a': [4], 'b': [8]} if with_source else {'a': [], 'b': []}}
        trace.append({'attempt': i, 'tool_wire_text_bytes': 200, 'fact': metric,
                      'requested_pair': {'reference': ref, 'order': ['N02', ref], 'ordinary_whole_entry': True,
                                         'explicit_no_image': True},
                      'classification': 'bound_whole_measurement', 'exact_source_verification': with_source,
                      'current_triangle_source': with_source})
        checks[f'{ref}_distance_and_world_direction'] = {
            'verified': {'metres': 1., 'direction_a_to_b': [1., 0., 0.]}}
        checks[f'{ref}_actual_point_pair_and_triangle_membership'] = {
            'verified': {'point_a': [0., 0., 0.], 'point_b': [1., 0., 0.], 'point_pair_quote': f'{ref} 并举证',
                         'stated_source_triangle_indices': {'a': [4], 'b': [8]},
                         'source_basis_kind': 'exact_bound_points'}}
    return trace, {'all_quality_passed': True, 'checks': checks}


def outcomes():
    binding = V / 'm3_whole_object_witness_triangle_consumption_001/FROZEN.json'
    historical = {}
    for label in ('A1', 'B1'):
        slot = HISTORICAL / 'slots' / label
        ledger = C['summarize'](slot, X['digest'](binding.read_bytes()))
        items = M['event_bindings'](slot)
        costs = OLD['account_active_costs'](ledger)
        require(ledger['cost_evidence_verified'] and ledger['status'] == 'completed'
                and len(items) == costs['business_attempts'] and costs['CLI_input_plus_output_tokens'] is not None
                and all(v is not None for v in items.values()), 'sealed_prior_visible_CLI_or_use_unreconciled')
        historical[label] = {'actual_prior_attempts': len(items), 'closed_original': ledger['result_sha256'],
                             'tokens': costs['CLI_input_plus_output_tokens']}
    capture_file, body_file = EXACT_CASE / 'worker/CAPTURE_01.json', EXACT_CASE / 'cold/PUBLIC.txt'
    capture, body = (read(path) for path in (capture_file, body_file))
    source, rows = X['verify_exact'](capture, body, ['N02', 'N03'])
    require(rows == {'a': [38], 'b': [3]} and source['independent_global_distance']['triangle_pairs'] == 528,
            'sealed_true_BVH_source_not_verified')
    wrong = deepcopy(body)
    wrong['facts']['surface_proximity']['value']['nearest_witness']['exact_source_triangles']['a'][
        'source_triangle_index'] = 37
    try:
        X['verify_exact'](capture, wrong, ['N02', 'N03'])
    except ValueError:
        pass
    else:
        raise ValueError('modified_exact_face_accepted')
    original, grade = sample_trace(with_source=True)
    answer = '；'.join(f'{ref} 并举证' for ref in R)
    verified, alternate = {'verified': [], 'unreviewed': []}, {}
    cases = X['summarize_pairs'](original, grade, answer, verified, candidate=True)
    require(all(row['candidate_first_whole_adopted'] for row in cases.values()), 'exact_source_adoption_not_recognized')
    ref_checks(grade, R[0])['source_basis_kind'] = 'independent_geometry'
    declined = X['summarize_pairs'](original, grade, answer, verified, candidate=True)
    require(declined[R[0]]['first_whole_is_exact_answer_match']
            and not declined[R[0]]['candidate_first_whole_adopted'], 'matching_values_alone_miscounted_as_adoption')
    base, prior_grade = sample_trace(with_source=False)
    later = {'attempt': 3, 'classification': 'standalone_new_source_membership', 'pairs': list(R),
             'result_excerpt': 'current checked faces', 'reason': 'Independent evidence for both sourced pairs.'}
    base_cases = X['summarize_pairs'](base, prior_grade, answer, {'verified': [later], 'unreviewed': []},
                                     candidate=False)
    for label, case in (('A1', base_cases), ('B1', cases)):
        alternate[label] = {'status': 'completed', 'formal_slot_created': True, 'model_consumers_launched': 1,
                            'cost_evidence_verified': True, 'thread_id': f'synthetic-{label}', 'verification_errors': [],
                            'pairs': case, 'quality': {'passed': True, 'score': 6}, 'review': {'unreviewed': []}}
    comparison = X['compare'](alternate)
    require(comparison['paired_provenance_followups_A_minus_B'] == 1
            and comparison['required_distinct_provenance_followup_attempts']['A1'] == [3],
            'single_shared_source_tool_overcounted')
    with TemporaryDirectory() as directory:
        empty = {label: X['summarize'](Path(directory) / label, {'sha256': 'synthetic'}, None, {})
                 for label in X['LABELS']}
        require(X['compare'](empty)['denominator']['unrun'] == 2, 'unrun_model_false_denominator')
    return {'passed': True, 'historical_cli_cost_and_attempts': historical, 'true_BVH_source_triangles': rows,
            'wrong_face_rejected': True, 'synthetic_shared_required_source_saving': 1,
            'quoted_numbers_alone_insufficient_for_adoption': True, 'unrun_slots_retained': 2,
            'source_pins': [pin(path) for path in (
                HERE/'consumption.py', V/'m3_whole_object_witness_triangle_consumption_001/checks/consumption_trace.py',
                V/'m1_source_region_no_image_measurement_consumption_001/checks/consumption_trace.py',
                V/'m1_source_region_no_image_native_transfer_001/checks/consumption_trace.py',
                V/'perf050_readonly_product_pilot_001/consumer/costs.py', X['ENGINE'],
                binding, capture_file, body_file)]}


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, default=HERE / 'CONSUMPTION_PREFLIGHT.json')
    args = cli.parse_args()
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(outcomes(), stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
