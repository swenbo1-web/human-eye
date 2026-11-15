"""Check the final candidate's actual public shape and narrow alias reuse."""

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SLOT = Path('D:/he_m5_observe_measure_001/qualification/B_qual')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    full_path = SLOT / 'producer/call_001/SERVICE_RESULT.json'
    public_path = SLOT / 'business/main/PUBLIC_01.json'
    full, public = [json.loads(path.read_bytes()) for path in (full_path, public_path)]
    actual = full['task_result']
    expected_keys = {'binding', 'coordinate_frame', 'execution_authority', 'facts', 'pair_order',
                     'result_kind', 'schema_version', 'status', 'unit'}
    assert type(actual) is dict and set(actual) == expected_keys
    assert public['task_result'] == actual and type(public['task_result']) is dict
    work = full['work']['task_query']
    assert work['geometry_alias_parse_calls'] == 0 and work['geometry_alias_reuses'] == 2
    assert work['ordered_geometry_hash_calls'] == 2 and work['normalization_calls'] == 1
    assert work['surface_pair_count'] == 1 and work['supplemental_capture_calls'] == 0
    assert work['additional_raster_attempts'] == 0
    return {'schema': 'm5-final-narrow-reuse-contract-review-v1', 'passed_checked_scope': True,
            'actual_task_result_keys': sorted(actual), 'actual_public_task_result_shape': 'task-query-v3 object',
            'private_observation_cache_tuple_in_public_or_raw_task_result': False,
            'same_actual_public_and_raw_task_result': True,
            'actual_alias_parse_calls': work['geometry_alias_parse_calls'],
            'actual_alias_reuses': work['geometry_alias_reuses'],
            'actual_ordered_geometry_hash_calls': work['ordered_geometry_hash_calls'],
            'actual_normalization_calls': work['normalization_calls'],
            'actual_surface_solver_calls': work['surface_pair_count'],
            'actual_additional_detailed_captures': work['supplemental_capture_calls'],
            'actual_additional_raster_attempts': work['additional_raster_attempts'],
            'input_pins': [{'path': str(path), 'sha256': sha(path)} for path in (full_path, public_path)],
            'checker_sha256': sha(Path(__file__)), 'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0}


if __name__ == '__main__':
    result = run()
    path = HERE / 'B_FINAL_OPTIMIZATION_REVIEW.json'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'output_sha256': sha(path)}))
