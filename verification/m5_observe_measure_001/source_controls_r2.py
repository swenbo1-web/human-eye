"""Saved-only independent source contract and folded-witness counterexamples."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


source = module('_m5_source_contract_r2', 'source_contract_r2.py')
oracle = module('_m5_oracle', 'oracle.py')


def fixture(supplement=False):
    folded = oracle.folded_fixture()
    meshes = [copy.deepcopy(folded[key]) for key in ('target', 'reference')]
    instances = {mesh['object_id']: mesh['instance_id'] for mesh in meshes}
    capture = {'capture_scope': 'target_observation_meshes',
               'capture_state': {'instance_id': 'fixture-host-1', 'epoch': 1, 'revision': 7, 'selection_key': 'parent-query'},
               'host_identity': {'document_epoch': 'fixture-document-1', 'object_instances': instances},
               'observation_target': {'full_scene_identity': {'document_epoch': 'fixture-document-1', 'object_instances': copy.deepcopy(instances)}},
               'meshes': meshes[:1] if supplement else meshes}
    binding = {'binding_sha256': 'parent-binding', 'source_binding_sha256': 'parent-source',
               'document_epoch': 'fixture-document-1'}
    task = [{'object_id': mesh['object_id'], 'instance_id': mesh['instance_id']} for mesh in meshes]
    rows = []
    for index, mesh in enumerate(meshes):
        observed = not supplement or index == 0
        rows.append({'object_id': mesh['object_id'], 'instance_id': mesh['instance_id'],
                     'observation_object_index': index if observed else None,
                     'geometry_id': source.geometry_alias(mesh) if observed else None,
                     'source_triangle_count': len(mesh['faces']),
                     'source_triangle_index_ranges': [[0, len(mesh['faces'])-1]],
                     'ordered_geometry_sha256': source.ordered_geometry_sha256(mesh)})
    public = {'schema': 'active-observation-task-source-v1', 'measurement_scope': 'whole_objects',
              'capture_scope': 'observation_task_objects', 'parent_binding_sha256': 'parent-binding',
              'parent_source_binding_sha256': 'parent-source', 'parent_capture_scope': capture['capture_scope'],
              'capture_state': {**capture['capture_state'], 'selection_key': 'derived-query'}, 'objects': rows}
    added = []
    if supplement:
        added = [{'capture_scope': 'task_meshes', 'capture_state': copy.deepcopy(capture['capture_state']),
                  'host_identity': copy.deepcopy(capture['host_identity']), 'meshes': [meshes[1]]}]
    return [public, binding, capture, task, added]


def run():
    rows = []

    def check(name, operation, expected=None):
        try:
            result = operation()
            actual = None
        except ValueError as error:
            actual = str(error)
            result = None
        passed = actual == expected
        rows.append({'case': name, 'passed': passed, 'expected_reason': expected,
                     'actual_reason': actual, 'result': result})
        if not passed:
            raise ValueError(name + ': ' + str(actual))

    def source_case(name, mutate=None, expected=None, supplement=False):
        value = fixture(supplement)
        if mutate:
            mutate(value)
        check(name, lambda: source.validate_source(*value), expected)

    source_case('complete_folded_whole_objects_and_distinct_selection_key')
    source_case('missing_only_same_generation_current_source', supplement=True)
    source_case('old_generation_revision_rejected', lambda x: x[0]['capture_state'].update(revision=6), 'derived_parent_generation_mismatch')
    source_case('old_generation_epoch_rejected', lambda x: x[0]['capture_state'].update(epoch=0), 'derived_parent_generation_mismatch')
    source_case('different_host_instance_rejected', lambda x: x[0]['capture_state'].update(instance_id='other-host'), 'derived_parent_generation_mismatch')
    source_case('parent_document_mismatch', lambda x: x[1].update(document_epoch='other-document'), 'parent_document_epoch_mismatch')
    source_case('old_parent_hash_rejected', lambda x: x[0].update(parent_binding_sha256='old-parent'), 'parent_source_binding_mismatch')
    source_case('same_name_replacement_instance_rejected', lambda x: x[2]['host_identity']['object_instances'].update({'fixture:fold-target': 'replacement'}), 'source_parent_full_object_instance_mismatch')
    source_case('supplement_parent_full_instance_changed', lambda x: x[2]['observation_target']['full_scene_identity']['object_instances'].update({'fixture:fold-reference': 'other-instance'}), 'source_parent_full_object_instance_mismatch', True)
    source_case('parent_full_document_changed', lambda x: x[2]['observation_target']['full_scene_identity'].update(document_epoch='other-document'), 'parent_full_document_epoch_mismatch')
    source_case('wrong_public_geometry_alias', lambda x: x[0]['objects'][0].update(geometry_id='geometry:incorrect'), 'observed_geometry_alias_mismatch')
    source_case('incomplete_folded_source_face_set', lambda x: x[0]['objects'][0].update(source_triangle_index_ranges=[[0, 0]]), 'whole_object_source_faces_incomplete')
    source_case('overlapping_folded_source_face_set', lambda x: x[0]['objects'][0].update(source_triangle_index_ranges=[[0, 1], [1, 1]]), 'source_face_ranges_overlap')
    source_case('source_face_count_mismatch', lambda x: x[0]['objects'][0].update(source_triangle_count=1), 'whole_object_source_faces_incomplete')
    source_case('wrong_observation_index', lambda x: x[0]['objects'][0].update(observation_object_index=1), 'observation_object_index_mismatch')
    source_case('supplement_must_not_claim_image_index', lambda x: x[0]['objects'][1].update(observation_object_index=1), 'observation_object_index_mismatch', True)
    source_case('supplement_must_not_claim_image_geometry', lambda x: x[0]['objects'][1].update(geometry_id='geometry:incorrect'), 'supplement_falsely_claims_observed_geometry', True)
    source_case('supplement_revision_change_rejected', lambda x: x[4][0]['capture_state'].update(revision=8), 'supplemental_generation_mismatch', True)
    source_case('supplement_document_change_rejected', lambda x: x[4][0]['host_identity'].update(document_epoch='other-document'), 'supplemental_document_epoch_mismatch', True)
    source_case('supplement_no_duplicate_parent_read', lambda x: x[4][0]['meshes'].append(copy.deepcopy(x[2]['meshes'][0])), 'supplement_contains_existing_object', True)

    def reorder_faces(value):
        mesh = value[2]['meshes'][0]
        old_alias = source.geometry_alias(mesh)
        mesh['faces'].reverse()
        assert source.geometry_alias(mesh) == old_alias
    source_case('same_union_face_reorder_invalidates_ordered_source', reorder_faces, 'ordered_current_source_geometry_mismatch')

    def change_coordinate(value):
        mesh = value[2]['meshes'][0]
        mesh['vertices'][3] = [0, 0, 2]
        value[0]['objects'][0]['geometry_id'] = source.geometry_alias(mesh)
    source_case('same_distance_new_coordinate_invalidates_old_source', change_coordinate, 'ordered_current_source_geometry_mismatch')
    source_case('duplicate_parent_id_rejected', lambda x: x[2]['meshes'].append(copy.deepcopy(x[2]['meshes'][0])), 'parent_object_ids_duplicate')
    source_case('source_mapping_serialized_in_scene_order', lambda x: x[0]['objects'].reverse())
    source_case('duplicate_task_binding_rejected', lambda x: x[3].__setitem__(1, copy.deepcopy(x[3][0])), 'derived_task_object_bijection_or_duplicates')
    source_case('duplicate_source_mapping_rejected', lambda x: x[0]['objects'].append(copy.deepcopy(x[0]['objects'][0])), 'derived_task_object_bijection_or_duplicates')

    folded = oracle.folded_fixture()
    for index, witness in enumerate(folded['legal_witnesses_on_different_target_facets']):
        def folded_witness(witness=witness):
            left = oracle.membership(witness['a'], folded['target']['vertices'], folded['target']['faces'])
            right = oracle.membership(witness['b'], folded['reference']['vertices'], folded['reference']['faces'])
            delta = oracle.subtract(oracle.vector(witness['b']), oracle.vector(witness['a']))
            assert witness['target_source_triangle'] in left['exact_source_triangle_indices']
            assert right['exact_source_triangle_indices'] == [0]
            assert oracle.dot(delta, delta) == 1
            return {'target_source_membership': left, 'reference_source_membership': right,
                    'exact_squared_witness_length': '1', 'distance_and_direction_unchanged': True}
        check('independent_folded_witness_' + str(index), folded_witness)
    check('coplanar_point_outside_triangular_surface', lambda: {
        'outside_confirmed': not oracle.membership([0, 2, 2], folded['target']['vertices'], folded['target']['faces'])['within_publication_tolerance_source_triangle_indices']})
    assert rows[-1]['result']['outside_confirmed']
    objects = oracle.frozen_objects()
    target = {'vertices': objects['M4_Far_00']['world_vertices_m'], 'faces': objects['M4_Far_00']['triangles']}
    reference = {'vertices': objects['M4_Near']['world_vertices_m'], 'faces': objects['M4_Near']['triangles']}
    distance = oracle.main_answer()['distance_binary64_m']
    a = objects['M4_Near']['world_vertices_m'][0][0]
    for index, yz in enumerate(((0, 0), (.25, .25))):
        fact = {'status': 'measured', 'witness_status': 'measured', 'direction_status': 'measured',
                'value': {'distance_m': distance, 'nearest_witness': {
                    'a': [1, *yz], 'b': [a, *yz], 'direction_a_to_b': [-1, 0, 0]}}}
        check('main_nonunique_legal_pair_' + str(index), lambda fact=fact: oracle.validate_main_fact(fact, target, reference))
    return {'schema': 'm5-independent-source-controls-v1', 'passed_checked_scope': all(row['passed'] for row in rows),
            'case_count': len(rows), 'cases': rows, 'scope': 'Pure offline independent checker and geometry controls, without live product pipeline execution.',
            'input_pins': {filename: hashlib.sha256((HERE / filename).read_bytes()).hexdigest()
                           for filename in ('oracle.py', 'source_contract_r2.py', 'source_controls_r2.py', 'PLAN.json', 'REQUESTS.json', 'STATE_REQUESTS.json')},
            'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0}


if __name__ == '__main__':
    report = run()
    with (HERE / 'scoring/SOURCE_CONTROLS_R2.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, default=str, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': report['passed_checked_scope'], 'case_count': report['case_count']}))
