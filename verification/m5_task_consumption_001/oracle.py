"""Private independent answers, reusing accepted source-only geometry proofs."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
OBSERVATION = HERE.with_name('m4_target_task_consumption_001')
ENGINEERING = HERE.with_name('m5_observe_measure_001')
PINS = {
    OBSERVATION / 'oracle.py': '84bf920b5180b1fbc970340ea580b47e7496a480bbdeb486690df272bb9e1420',
    OBSERVATION / 'admin/TRUTH.json': 'a9260bab619f7333cb88bf0ba2ea4e919a021b751913e88536c4c9f25e6efcc1',
    ENGINEERING / 'oracle.py': '0133b8e69b34e9347cb48cf9220f9a880065f6dc95517e300295afd2c96a9acb',
    ENGINEERING / 'scoring/TRUTH.json': '6f16978ec15bd127bb645be0a44526e5e6987ba94fc94062a43b5ace43fe6714'
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def derive():
    for path, digest in PINS.items():
        if sha(path) != digest:
            raise ValueError('accepted_independent_geometry_proof_changed')
    observation = load(OBSERVATION / 'oracle.py', '_m5_consume_planar_oracle').derive()
    original = json.loads((OBSERVATION / 'admin/TRUTH.json').read_bytes())
    if json.loads(json.dumps(observation, default=str)) != original:
        raise ValueError('independent_observation_replay_changed')
    measurement = load(ENGINEERING / 'oracle.py', '_m5_consume_surface_oracle').main_answer()
    actual_objects = load(ENGINEERING / 'oracle.py', '_m5_consume_whole_sources').frozen_objects()
    result = copy.deepcopy(original)
    result.update(schema='m5-task-consumption-private-truth-v1', administrator_only=True,
                  observation_reference_schema=original['schema'], measurement=measurement)
    result['whole_measurement_objects'] = [
        {'object_name': name, 'reference_object_id': actual_objects[name]['reference_object_id'],
         'vertices_world_m': actual_objects[name]['world_vertices_m'],
         'source_triangles': actual_objects[name]['triangles'],
         'source_triangle_count': len(actual_objects[name]['triangles']),
         'source_triangle_index_ranges': [[0, len(actual_objects[name]['triangles'])-1]]}
        for name in measurement['objects_in_pair_order']]
    result['consumer_numeric_contract'] = {
        'domain': 'This fixed current source input only.',
        'producer_scalar': 'Exactly correctly rounded binary64, independently validated from frozen source.',
        'consumer_distance_absolute_tolerance_m': '1e-9',
        'consumer_point_membership_tolerance_m': '1e-9',
        'consumer_relative_displacement_tolerance_m': '1e-9',
        'consumer_direction_component_and_unit_length_tolerance': '2e-14',
        'particular_equal_distance_point_pair_required': False,
        'decimal_presentation_residuals_reported': True}
    result['independent_reference_pins'] = [{'path': str(path), 'sha256': digest} for path, digest in PINS.items()]
    result['current_oracle_sha256'] = sha(Path(__file__))
    result.update(new_actual_calls=0, new_models=0, new_rasters=0)
    return result


if __name__ == '__main__':
    result = derive()
    path = HERE / 'admin/TRUTH.json'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, default=str, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'private_truth_ready': True, 'sha256': sha(path), 'new_actual_calls': 0}))
