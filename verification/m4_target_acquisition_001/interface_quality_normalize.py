"""Synthetic source/schema counterexamples for the offline quality adapter.

The fixtures exercise validation only.  They are not captures, images,
installed-runtime proof, task quality samples, or qualification evidence.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent


def load_adapter():
    path = HERE / 'quality_normalize.py'
    spec = importlib.util.spec_from_file_location('_target_quality_interface_adapter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(module, *, subset, generation):
    target = {'asset_key': 'fixture/target', 'source_order': 1, 'object_id': 'blender:b',
              'object_name': 'Target', 'vertices_world': [[-1., -1., 0.], [1., -1., 0.], [1., 1., 0.], [-1., 1., 0.]],
              'triangles': [[0, 1, 2], [0, 2, 3]]}
    other = {'asset_key': 'fixture/occluder', 'source_order': 0, 'object_id': 'blender:a',
             'object_name': 'Occluder', 'vertices_world': [[100., 100., 1.], [101., 100., 1.], [100., 101., 1.]],
             'triangles': [[0, 1, 2]]}
    assets = {'asset_sha256': 'c' * 64, 'target_asset_key': target['asset_key'],
              'source_frame': {'frame': 1, 'subframe': 0., 'scale_length': 1.}, 'objects': [other, target]}
    included = [target] if subset else [other, target]
    instances = {row['object_id']: generation + ':' + row['object_name'] for row in assets['objects']}
    full = {'schema_version': '1.0', 'document_epoch': hashlib.sha256(generation.encode()).hexdigest(),
            'capture_scope': 'complete_scene_meshes', 'object_instances': instances}
    identity = dict(full, capture_scope='target_observation_meshes',
                    object_instances={row['object_id']: instances[row['object_id']] for row in included})
    eye = [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., -10.], [0., 0., 0., 1.]]
    projection = [[.5, 0., 0., 0.], [0., .5, 0., 0.], [0., 0., -.01, 0.], [0., 0., 0., 1.]]
    cameras = {'schema': 'active-coverage-target-cameras-v1', 'views': [
        {'name': name, 'view_matrix': eye, 'projection_matrix': projection,
         'size_px': [512, 512], 'direction_rational': list(direction)}
        for name, direction in zip(module.VIEW_ORDER, module.DIRECTIONS)]}
    directory = [{'object_id': row['object_id'], 'name': row['object_name'],
                  'instance_id': instances[row['object_id']]} for row in assets['objects']]
    directory_sha = hashlib.sha256(json.dumps(directory, sort_keys=True, separators=(',', ':'),
                                              ensure_ascii=False).encode()).hexdigest()
    capture = {'unit': 'm', 'coordinate_frame': 'world', 'source': 'blender',
               'revision': 'synthetic:' + generation, 'capture_scope': 'target_observation_meshes',
               'host_identity': identity,
               'capture_state': {'instance_id': generation, 'epoch': 1, 'revision': 1, 'selection_key': 'd' * 64},
               'meshes': [{'object_id': row['object_id'], 'name': row['object_name'],
                           'vertices': row['vertices_world'], 'faces': row['triangles']} for row in included]}
    target_index = len(included) - 1
    capture['observation_target'] = {
        'schema': 'active-observation-target-v1', 'selector': {'name': 'Target'},
        'target_object_id': target['object_id'], 'target_instance_id': instances[target['object_id']],
        'target_object_index': target_index, 'camera_plan': cameras, 'scene_directory': directory,
        'full_scene_identity': full, 'retained_object_ids': [row['object_id'] for row in included],
        'excluded_object_ids': [row['object_id'] for row in assets['objects'] if row not in included],
        'directory_sha256': directory_sha, 'source_frame': assets['source_frame'], 'work': {}}
    binding = module.reconstruct_target_binding(capture)
    proof = {'expected_source_sha256': 'a' * 64, 'expected_host_source_sha256': 'b' * 64,
             'actual_runtime_identity': {'source_kind': 'installed_distribution', 'source_sha256': 'a' * 64},
             'actual_loaded_host_sha256': 'b' * 64,
             'material_pins': [{'path': str(Path(__file__).resolve()),
                                'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}]}
    mapping = module.validate_object_mapping(capture, binding, assets, proof)
    compact = {key: copy.deepcopy(value) for key, value in binding.items()
               if key not in ('schema', 'objects', 'camera_policy', 'camera_specification')}
    compact['capture_state'].pop('selection_key')
    compact_target = {key: compact['observation_target'][key] for key in (
        'schema', 'selector', 'target_object_id', 'target_instance_id', 'target_object_index',
        'camera_plan_sha256', 'directory_sha256', 'source_frame')}
    compact_target['full_scene_identity_sha256'] = module.fingerprint(full)
    compact['observation_target'] = compact_target
    compact.update(runtime_source_sha256='a' * 64, source_status='loaded_generation',
                   disk_status='disk_not_checked', source_check_scope='bound_generation_identity')
    region = {'roi_id': 'synthetic_roi', 'object_index': target_index,
              'status': 'unknown', 'reason': 'pending_observation', 'triangle_count': 2,
              'source_triangle_index_ranges': [[0, 1]], 'center_world_m': [0, 0, 0],
              'half_edge_u_world_m': [1, 0, 0], 'half_edge_v_world_m': [0, 1, 0],
              'front_direction_world': [0, 0, 1], 'complete_witness_pixel_index': None,
              'unobserved_reason': 'unobserved_geometric_candidates', 'unobserved_view_group_indices': []}
    public = {'schema': 'active-observation-brief-v5', 'index_base': 0,
              'status': 'predicted', 'result_kind': 'active_observation', 'observation_status': 'prediction_only',
              'session_id': generation, 'read_only': True, 'execution_authority': False, 'binding': compact,
              'objects': {'columns': ['object_index', 'host_id', 'instance_id', 'object_name'],
                          'rows': [[row[key] for key in ('object_index', 'host_id', 'instance_id', 'object_name')]
                                   for row in binding['objects']]},
              'regions': {'columns': list(region), 'rows': [list(region.values())]},
              'coverage': {'scope': 'target', 'state_updates': 0, 'unresolved_region_indices': [0]},
              'source_triangle_index_ranges_semantics': 'zero_based_object_local_inclusive; object_index_in_objects; scoped_to_this_binding',
              'scope': {'capture_object_count': len(included), 'supported_roi_object_count': 1,
                        'domain': 'maximal edge-connected exact planar rectangular patches',
                        'all_objects_participate_in_occlusion': True,
                        'observation_scope': {'kind': 'target', 'target_object_index': target_index,
                                              'target_object_count': 1, 'occluder_only_object_count': len(included)-1,
                                              'full_scene_object_count': 2, 'excluded_object_count': int(subset)},
                        'patch_support': {'schema': 'active-patch-support-v2',
                                          'triangle_index_scope': 'zero-based source triangles within each object',
                                          'all_triangles_participate_in_occlusion': True,
                                          'object_support': {'columns': ['object_index', 'source_triangle_count',
                                                                         'supported_triangle_count', 'unsupported_triangle_count', 'support_status'],
                                                             'rows': [[index, len(row['triangles']), 2 if index == target_index else 0,
                                                                       0, 'fully_supported' if index == target_index else 'occluder_only']
                                                                      for index, row in enumerate(included)]}}}}
    classifications = {name: {'synthetic_roi': {'status': 'complete', 'complete': True, 'first_blocker': None}}
                       for name in module.VIEW_ORDER}
    return capture, binding, assets, proof, mapping, public, classifications


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    module = load_adapter()
    a = fixture(module, subset=False, generation='synthetic-A')
    b = fixture(module, subset=True, generation='synthetic-B')
    records = []

    def check(name, call, rejects=False):
        try:
            call()
        except ValueError as error:
            records.append({'case': name, 'passed': rejects, 'rejection': str(error)})
        except Exception as error:
            records.append({'case': name, 'passed': False, 'unexpected_error': type(error).__name__ + ' ' + str(error)})
        else:
            records.append({'case': name, 'passed': not rejects})

    def source_subset_and_fresh_instances():
        left = module.normalize_public_target(a[5], a[0], a[1], a[4], a[6], [])
        right = module.normalize_public_target(b[5], b[0], b[1], b[4], b[6], [])
        assert left['comparison'] == right['comparison']
        assert left['comparison']['regions'][0]['status'] == 'unknown'
        assert left['scope_audit']['capture_object_count'] == 2
        assert right['scope_audit']['capture_object_count'] == 1

    check('fresh_instances_and_subset_owner_order_normalize_after_local_validation', source_subset_and_fresh_instances)
    wrong_source = copy.deepcopy(a[3])
    wrong_source['expected_source_sha256'] = 'f' * 64
    check('wrong_arm_source_rejected', lambda: module.validate_object_mapping(a[0], a[1], a[2], wrong_source), True)
    wrong_instance = copy.deepcopy(a[1])
    wrong_instance['objects'][0]['instance_id'] = 'stale-instance'
    check('stale_current_instance_rejected', lambda: module.validate_object_mapping(a[0], wrong_instance, a[2], a[3]), True)
    reversed_faces = copy.deepcopy(a[0])
    reversed_faces['meshes'][1]['faces'].reverse()
    check('changed_local_face_order_rejected', lambda: module.validate_object_mapping(reversed_faces, a[1], a[2], a[3]), True)
    check('missing_actual_classifications_rejected',
          lambda: module.normalize_public_target(a[5], a[0], a[1], a[4], None, []), True)
    bad_front = copy.deepcopy(a[5])
    bad_front['regions']['rows'][0][bad_front['regions']['columns'].index('front_direction_world')] = [0, 0, 6.5]
    check('center_copied_as_front_vector_rejected',
          lambda: module.normalize_public_target(bad_front, a[0], a[1], a[4], a[6], []), True)
    missing_face = copy.deepcopy(a[5])
    missing_face['regions']['rows'][0][missing_face['regions']['columns'].index('source_triangle_index_ranges')] = [[0, 0]]
    check('missing_declared_source_face_rejected',
          lambda: module.normalize_public_target(missing_face, a[0], a[1], a[4], a[6], []), True)
    check('table_extra_tail_rejected', lambda: module.table({'columns': ['a'], 'rows': [[1, 2]]}), True)
    check('adjacent_noncanonical_ranges_rejected', lambda: module.source_face_indices([[0, 0], [1, 1]], 2), True)
    result = {'schema': 'm4-target-quality-normalization-synthetic-interface-v1',
              'scope': 'Hand-authored schema-validation fixtures only. No actual source, camera, capture, pixel or task-quality qualification.',
              'records': records, 'passed': all(row['passed'] for row in records),
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'adapter_sha256': hashlib.sha256((HERE / 'quality_normalize.py').read_bytes()).hexdigest(),
              'product_imports': 0, 'Blender_starts': 0, 'raster_calls': 0, 'model_calls': 0}
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'cases': len(records), 'failures': [row for row in records if not row['passed']]}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
