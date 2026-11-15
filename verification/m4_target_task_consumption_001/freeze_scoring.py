"""Freeze the private grading contract before the unique six-model run."""

import hashlib
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    paths = [HERE / name for name in (
        'inputs/COMMON_TASK.txt', 'inputs/ANSWER_SCHEMA.json', 'SCORING_PLAN.md',
        'admin/NORMALIZATION_SCHEMA.json', 'admin/TRUTH.json', 'admin/QUALIFICATION.json',
        'oracle.py', 'grade_claims.py', 'pixel_oracle.py', 'quoted_sources.py', 'score_saved.py',
        'saved_evidence.py', 'qualify_saved.py', 'freeze_scoring.py',
        'launcher.py', 'bridge.py', 'native_tools.py', 'owned_runtime.py', 'mcp_entry.py',
        'native_consumer_audit.py', 'budget.py', 'bootstrap.py', 'run_slot.py',
        'PRODUCT_RUN_BINDING.json', 'SHARED_DEPENDENCY.json', 'fixtures/DEVICE_CAMERAS.json',
        'reference/FROZEN_GEOMETRY.json', 'reference/M4_TARGET_TASK_CONSUMPTION_001_PLAN.md')]
    paths += [HERE / name for name in (
        'admin/INTERFACE_CLAIMS.json', 'admin/INTERFACE_PIXELS_01.json',
        'admin/INTERFACE_ADOPTION_R2.json', 'admin/INTERFACE_REFERENCES.json', 'admin/INTERFACE_TERMINAL_R1.json')]
    qualification = json.loads((HERE / 'admin/QUALIFICATION.json').read_bytes())
    assert qualification['passed_checked_scope'] is True and qualification['qualification'] == 'PASS'
    assert qualification['saved_adapter_sha256'] == sha(HERE / 'saved_evidence.py')
    for name, field, source in (
            ('INTERFACE_CLAIMS.json', 'checker_sha256', 'grade_claims.py'),
            ('INTERFACE_PIXELS_01.json', 'pixel_oracle_sha256', 'pixel_oracle.py'),
            ('INTERFACE_ADOPTION_R2.json', 'source_sha256', 'quoted_sources.py'),
            ('INTERFACE_REFERENCES.json', 'source_sha256', 'quoted_sources.py'),
            ('INTERFACE_TERMINAL_R1.json', 'scorer_sha256', 'score_saved.py')):
        report = json.loads((HERE / 'admin' / name).read_bytes())
        assert report['passed_checked_scope'] is True and report[field] == sha(HERE / source)
    pins = {str(path.resolve()): sha(path) for path in paths}
    contract = {'schema': 'target-task-consumption-scoring-contract-v1', 'administrator_only': True,
        'frozen_before_formal_models': True, 'frozen_ns': time.perf_counter_ns(),
        'formal_slots': ['N1', 'P1', 'P2', 'N2', 'N3', 'P3'], 'quality_denominator': 6,
        'run_schema': 'target-task-consumption-run-v1', 'slot_schema': 'target-task-consumption-slot-v1',
        'normalization_schema': 'target-task-consumption-normalized-v1',
        'semantic_review_schema': 'target-task-consumption-semantic-review-v1',
        'source_reference_policy': {
            'canonical_current_ref': True, 'explicit_unique_current_tool_reference_allowed': True,
            'normalization_requires_exact_final_excerpt_actual_request_response_and_current_source': True,
            'private_undelivered_hash_required': False, 'empty_reference_fields_may_be_filled': False,
            'cross_slot_or_ambiguous_reference_accepted': False,
            'current_tool_canonical_form': 'current-tool:<actual attempt>:<actual tool name>',
            'public_ROI_frame_binding_reference_mapped_under_current_source': True},
        'actual_adoption': 'Task fact in actual delivered product response, actual final use, and explicit current public source chain, independently reviewed. Calls and field presence alone are insufficient.',
        'adoption_observed_independently_of_task_quality': True,
        'background_full_used_as_model_consumption': False,
        'whole_final_and_unretracted_extras_scored': True,
        'thresholds': {'surface_pixels': 16, 'boundary_pixels': 4, 'RGB_euclidean_distance': 24},
        'geometry_measurement': 'Exact finite rational source sets, centers and extents. Oriented unit normals allow 2e-14 double-normalization error.',
        'finite_pool_reason_codes': ['positive_area_occlusion_all_front_views', 'no_front_facing_candidate',
                                     'no_complete_geometric_candidate', 'pixel_evidence_insufficient', 'pending_evidence'],
        'unconstructed_view_pixels': 'not_run', 'source_quoted_normalization_review_before_content_grade': True,
        'quality_before_cost': True, 'direct_only_is_diagnostic': True,
        'native_supplement_necessity_without_specific_proof': 'unknown',
        'positive_signal': {'N_quality': 3, 'P_quality': 3, 'P_adoption': 3,
                            'median_complete_time_P_over_N_max': 0.90, 'minimum_P_faster_pairs': 2,
                            'P_total_raw_input_plus_output_not_increased': True, 'same_source_usage_required': True},
        'files_sha256': pins, 'new_model_calls': 0, 'new_rasters': 0, 'new_product_observations': 0}
    path = HERE / 'admin/SCORING_CONTRACT.json'
    save(path, contract)
    freeze = {'schema': 'target-task-consumption-private-scoring-freeze-v1',
              'contract': {'path': str(path), 'sha256': sha(path)}, 'files_sha256': pins,
              'scope': 'Private grading preparation only. Public task/schema and runtime sources are pinned. No task consumer launched.',
              'models_launched_by_freeze': 0, 'product_or_raster_calls': 0}
    save(HERE / 'admin/PRIVATE_SOURCE_FREEZE.json', freeze)
    print(json.dumps({'scoring_freeze_ready': True, 'pinned_files': len(pins), 'contract_sha256': sha(path),
                      'private_source_freeze_sha256': sha(HERE / 'admin/PRIVATE_SOURCE_FREEZE.json')}))


if __name__ == '__main__':
    main()
