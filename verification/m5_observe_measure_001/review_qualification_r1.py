"""Saved-only A/B quality equivalence after independent slot validation."""

import argparse
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def checker():
    spec = importlib.util.spec_from_file_location('_m5_quality_r2', HERE / 'quality_saved_r2.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observation_comparison(slot, audit, module):
    quality, q, metrics, oracle, _ = module.dependencies()
    result = module.read(slot / 'RESULT.json')
    build = module.read(result['binding_path'])
    manifest = module.asset_manifest(oracle)
    captures, materials, _, host_sha = module.decode_original_wire(slot, build, manifest)
    producer = next(row['producer'] for row in result['requests']
                    if row['request']['params']['arguments']['query']['mode'] == 'active_observation')
    full = module.read(producer['path'])
    capture = next(row['capture'] for row in captures
                   if row['capture'].get('capture_scope') == 'target_observation_meshes'
                   and q.reconstruct_target_binding(row['capture'])['binding_sha256'] == full['binding']['binding_sha256'])
    binding = q.reconstruct_target_binding(capture)
    proof = {'expected_source_sha256': audit['source_sha256'], 'expected_host_source_sha256': host_sha,
             'actual_runtime_identity': module.read(slot / 'INITIALIZE.json')['result']['_meta']['human_eye'],
             'actual_loaded_host_sha256': host_sha, 'material_pins': materials}
    mapping = q.validate_object_mapping(capture, binding, manifest, proof)
    return {'facts': metrics.canonical_facts(full['facts'], mapping, full['frames']),
            'classifications': full['target_view_classifications'],
            'cameras': binding['camera_specification'],
            'view_sequence': [row['view_name'] for row in full['frames']],
            'normalized_current_asset_objects': [row['asset_key'] for row in mapping['objects']]}


def compare(a_slot, b_slot, b_binding):
    module = checker()
    a_slot, b_slot = Path(a_slot), Path(b_slot)
    a, a_arrays = module.audit_slot(a_slot, 'A')
    b, b_arrays = module.audit_slot(b_slot, 'B')
    spec = importlib.util.spec_from_file_location('_m5_compare_witness_residuals', HERE / 'witness_residuals.py')
    residuals = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(residuals)
    witness_reviews = {}
    for arm, slot in (('A', a_slot), ('B', b_slot)):
        requests = module.read(slot / 'RESULT.json')['requests']
        public = module.read(requests[-1]['public_path'])
        task = public if arm == 'A' else public['task_result']
        witness_reviews[arm] = residuals.validate(task['facts']['surface_proximity'])
    module.require(a['source_sha256'] == module.read(HERE / 'A_RUN_BINDING.json')['source_sha256'], 'external_frozen_A_identity')
    expected_b = module.read(b_binding)
    module.require(b['source_sha256'] == expected_b['source_sha256'], 'external_frozen_B_identity')
    a_value = observation_comparison(a_slot, a, module)
    b_value = observation_comparison(b_slot, b, module)
    equal = {key: a_value[key] == b_value[key] for key in a_value}
    module.require(all(equal.values()), 'A_B_entire_observation_facts_classifications_cameras')
    module.require(len(a_arrays) == len(b_arrays), 'A_B_actual_frame_count')
    _, q, _, _, _ = module.dependencies()
    buffer_reviews = []
    import numpy as np
    for left, right in zip(a_arrays, b_arrays):
        review = q.compare_normalized_buffers(left, right)
        review['patch_owners_equal'] = bool(np.array_equal(left['patch_owners'], right['patch_owners']))
        module.require(review['equal'] and review['patch_owners_equal'], 'A_B_actual_all_saved_buffer_equality')
        buffer_reviews.append(review)
    module.require(a['task']['numeric']['distance_m'] == b['task']['numeric']['distance_m'], 'A_B_legal_surface_distance')
    return {'schema': 'm5-A-B-qualified-equivalence-v1', 'passed_checked_scope': True,
            'A': a, 'B': b, 'observation_equivalence': equal, 'actual_buffers': buffer_reviews,
            'numeric_equivalence': {'same_distance': True, 'both_current_witnesses_independently_legal': True,
                                    'particular_equal_distance_witness_required': False},
            'nearest_displacement_publication_reviews': witness_reviews,
            'nearest_displacement_checker_sha256': module.sha(HERE / 'witness_residuals.py'),
            'frozen_A_binding': {'path': str(HERE / 'A_RUN_BINDING.json'), 'sha256': module.sha(HERE / 'A_RUN_BINDING.json')},
            'frozen_B_binding': {'path': str(b_binding), 'sha256': module.sha(b_binding)},
            'source_checker_path': str(HERE / 'source_contract_r2.py'), 'source_checker_sha256': module.sha(HERE / 'source_contract_r2.py'),
            'quality_checker_path': str(HERE / 'quality_saved_r2.py'), 'quality_checker_sha256': module.sha(HERE / 'quality_saved_r2.py'),
            'comparison_checker_sha256': module.sha(Path(__file__)), 'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--A', required=True, type=Path)
    parser.add_argument('--B', required=True, type=Path)
    parser.add_argument('--B-binding', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    review = compare(args.A, args.B, args.B_binding)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(review, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': review['passed_checked_scope'], 'output_sha256': checker().sha(args.output)}))
