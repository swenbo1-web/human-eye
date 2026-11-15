"""Freeze private answers and quality algorithms before any model consumer."""

import hashlib
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    paths = ['inputs/COMMON_TASK.txt', 'inputs/ANSWER_SCHEMA.json', 'admin/TRUTH.json',
             'oracle.py', 'grade_claims.py', 'pixel_oracle.py', 'SCORING_PLAN.md',
             'A_RUN_BINDING.json', 'B_RUN_BINDING.json', 'PREP_PLAN.json']
    truth = json.loads((HERE / 'admin/TRUTH.json').read_bytes())
    for row in truth['independent_reference_pins']:
        if sha(row['path']) != row['sha256']:
            raise ValueError('independent_reference_changed_before_freeze')
    for path in ('inputs/COMMON_TASK.txt', 'inputs/ANSWER_SCHEMA.json'):
        if not (HERE / path).is_file():
            raise ValueError('common_public_input_missing')
    contract = {
        'schema': 'm5-task-consumption-scoring-contract-v1', 'administrator_only': True,
        'frozen_before_formal_models': True, 'formal_models_at_freeze': 0, 'frozen_ns': time.perf_counter_ns(),
        'formal_slots': ['A1', 'B1', 'B2', 'A2', 'A3', 'B3'], 'quality_denominator': 6,
        'failed_and_not_run_kept': True, 'source_quoted_normalization_review_before_content_grade': True,
        'whole_final_and_unretracted_extras_scored': True,
        'source_only_normalization': True, 'missing_values_may_be_filled_from_truth': False,
        'equivalent_explicit_notes_reason_allowed_when_unknown_reason_null': True,
        'normalization_schema': 'm5-task-consumption-normalized-v1',
        'semantic_review_schema': 'm5-task-consumption-semantic-review-v1',
        'run_schema': 'target-task-consumption-run-v1', 'slot_schema': 'target-task-consumption-slot-v1',
        'products': {'A': '776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be',
                     'B': '7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a'},
        'thresholds': {'surface_pixels': 16, 'boundary_pixels': 4, 'RGB_euclidean_distance': 24,
                       'region_finite_rational_geometry': 'exact', 'unit_normal_error': 2e-14,
                       'consumer_distance_absolute_error_m': 1e-9, 'consumer_source_membership_error_m': 1e-9,
                       'consumer_relative_displacement_error_m': 1e-9, 'consumer_direction_and_unit_error': 2e-14},
        'numeric_domain': 'Only the fixed current frozen input. Producer retains independently checked exact binary64 result; consumer decimal residuals are reported.',
        'legal_nonunique_nearest_points_allowed': True,
        'A_observation_measurement_association': 'Own actually public objects and source references, with independent current capture equality. B parentbinding fields are optional in the common answer.',
        'B_parent_binding': 'Additional actual product interface check. Never imposed mechanically on A.',
        'B_adoption': {
            'observation': 'Actual current joint public observation fact, source-quoted delivered tool/code dataflow and final task use.',
            'measurement': 'Actual same joint call public measurement fact, source-quoted delivered tool/code dataflow and final task use.',
            'same_joint_call_required': True, 'whole_objects_scope_required': True,
            'calls_or_field_presence_sufficient': False, 'background_full_is_consumption': False,
            'adoption_observed_separately_from_quality': True},
        'A_batch_adoption': 'One actual outer tool includes ordinary observation and ordinary task public calls. Actual calls and final use are recorded separately.',
        'source_reference_policy': {'explicit_unique_current_tool_or_API_reference_allowed': True,
                                    'canonical_current_tool_form': 'current-tool:<actual outer attempt>:<actual tool name>',
                                    'exact_final_excerpt_actual_request_response_current_source_required': True,
                                    'empty_references_filled': False, 'ambiguous_or_cross_slot_accepted': False,
                                    'private_undelivered_hash_required': False},
        'work_classification': 'Every actual outer tool, public call, error and recovery retained. Additional information, recomputation, geometry reverse lookup, pixel recomputation and repeat images require source/code provenance. Necessity stays unknown without specific proof.',
        'geometry_or_pixel_recomputation_forbidden': False,
        'positive_signal': {'A_quality': 3, 'B_quality': 3, 'B_joint_fact_adoption': 3,
                            'same_source_comparable_usage': True, 'median_complete_time_B_over_A_max': .9,
                            'minimum_B_faster_pairs': 2, 'B_raw_input_plus_output_total_not_increased': True},
        'quality_before_cost': True, 'cost_analysis_performed': False,
        'remaining_preformal_preparation': 'Saved-format adapter, quotation/scorer interfaces and source-only normalization implementation may be completed before consumers. Expected answers, algorithms and thresholds above are fixed. Any saved-format correction retains initial source and reason.',
        'files_sha256': {str(HERE / path): sha(HERE / path) for path in paths},
        'new_model_calls': 0, 'new_product_observations': 0, 'new_rasters': 0}
    path = HERE / 'admin/SCORING_CONTRACT.json'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(contract, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'quality_contract_ready': True, 'sha256': sha(path), 'new_models': 0}))


if __name__ == '__main__':
    main()
