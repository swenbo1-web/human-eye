"""Small synthetic validation/partition/projection checks with no observation calls."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from human_eye_plugin import active_observation as core
from human_eye_plugin import active_observation_host as bridge
from human_eye_plugin.active_observation_images import _meshes_from_objects, _patch_mapping
from human_eye_plugin.live_spatial_mcp import project_active_observation_brief, _validate_arguments, _tool_result
from human_eye_plugin.query_policy import validate_query


CHECKS = []


def check(name, condition):
    CHECKS.append({'name': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)


def rejects(name, operation, reason):
    try:
        operation()
    except ValueError as error:
        check(name, str(error) == reason)
    else:
        check(name, False)


def directory_digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode('utf8')).hexdigest()


def fixture():
    meshes = [
        {'object_id': 'host-blocker', 'name': '非矩形遮挡物',
         'vertices': [[-1, -1, 1], [1, -1, 1], [0, 1, 1]], 'faces': [[0, 1, 2]]},
        {'object_id': 'host-target', 'name': 'Target',
         'vertices': [[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]],
         'faces': [[0, 1, 2], [0, 2, 3]]},
        {'object_id': 'host-back', 'name': 'Back panel',
         'vertices': [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1]],
         'faces': [[0, 1, 2], [0, 2, 3]]},
    ]
    identity = {'schema_version': '1.0', 'document_epoch': 'a' * 64,
                'capture_scope': 'complete_scene_meshes',
                'object_instances': {row['object_id']: str(index + 101) for index, row in enumerate(meshes)}}
    capture = {'unit': 'm', 'coordinate_frame': 'world', 'source': 'blender',
               'revision': 'synthetic-source:1', 'capture_scope': 'target_observation_meshes',
               'host_identity': dict(identity, capture_scope='target_observation_meshes'),
               'capture_state': {'instance_id': 'synthetic-host', 'epoch': 1, 'revision': 1,
                                 'selection_key': 'synthetic-target'}, 'meshes': meshes}
    objects, triangles, geometry_identity = core.geometry(bridge.scene_from_capture(capture))
    cameras = bridge.freeze_cameras(_meshes_from_objects(objects))
    cameras['schema'] = 'active-coverage-target-cameras-v1'
    rows = [{'object_id': row['object_id'], 'name': row['name'],
             'instance_id': identity['object_instances'][row['object_id']]} for row in meshes]
    capture['observation_target'] = {
        'schema': 'active-observation-target-v1', 'selector': {'name': 'Target'},
        'target_object_id': 'host-target', 'target_instance_id': '102', 'target_object_index': 1,
        'camera_plan': cameras, 'scene_directory': rows, 'full_scene_identity': identity,
        'retained_object_ids': [row['object_id'] for row in meshes], 'excluded_object_ids': [],
        'directory_sha256': directory_digest(rows),
        'source_frame': {'frame': 1, 'subframe': 0.0, 'scale_length': 1.0},
        'work': {'strategy': 'synthetic_unit_full_capture', 'counters': {}, 'stages': {}},
    }
    return capture, objects, triangles, geometry_identity, cameras


def pure_result(capture, objects, triangles, identity, cameras, *, targeted):
    options = {'target_object_index': 1} if targeted else {}
    session = core.prepare_scene_from_parsed(objects, triangles, identity, cameras, **options)
    binding = bridge.source_binding(capture, cameras, geometry_identity=identity)
    facts = session.short_facts()
    for region in facts['regions']:
        host = binding['objects'][region['object_index']]
        region.update(host_id=host['host_id'], instance_id=host['instance_id'])
    facts['scope'] = bridge._patch_scope_facts(session, binding)
    facts['location_conventions'] = bridge._location_conventions(cameras)
    binding.pop('camera_specification')
    binding.update(runtime_source_sha256='b' * 64, source_status='loaded_generation',
                   disk_status='disk_not_checked', source_check_scope='bound_generation_identity')
    value = {'status': 'predicted', 'result_kind': 'active_observation',
             'observation_status': 'prediction_only', 'session_id': 'synthetic-session',
             'binding': binding, 'facts': facts, 'frames': [],
             'image_delivery': {'local_verified_image_count': 0, 'mcp_content_constructed_image_count': 0,
                                'consumer_read_status': 'unconfirmed', 'frame_reuses': 0,
                                'new_raster_attempts': 0},
             'read_only': True, 'execution_authority': False}
    if targeted:
        value['target_view_classifications'] = copy.deepcopy(session.index.classifications)
    return session, value


def main():
    started = time.perf_counter_ns()
    files = [ROOT / 'human_eye_plugin' / name for name in (
        'active_observation.py', 'active_observation_host.py', 'live_service.py', 'live_spatial_mcp.py')]
    sources = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    failure = None
    try:
        capture, objects, triangles, identity, cameras = fixture()
        session, value = pure_result(capture, objects, triangles, identity, cameras, targeted=True)
        check('one_target_region_only', len(session.regions) == 1 and session.regions[0].object_index == 1)
        check('all_five_triangles_remain_occluders', len(session.triangles) == 5)
        check('nonrectangular_non_target_is_occluder_only',
              session.index.patch_scope[0]['coverage_role'] == 'occluder_only'
              and session.index.patch_scope[0]['unsupported_triangle_count'] == 0)
        check('rectangular_non_target_is_occluder_only',
              session.index.patch_scope[2]['coverage_role'] == 'occluder_only')
        check('occluders_are_not_unknown_targets', value['facts']['scope']['objects_without_supported_roi'] == [])
        mapping = _patch_mapping(objects, session.regions)
        check('non_target_face_patch_ids_are_minus_one',
              mapping['face_ids'][0].tolist() == [-1] and mapping['face_ids'][2].tolist() == [-1, -1])
        check('target_source_faces_bound_directly', mapping['face_ids'][1].tolist() == [0, 0])
        brief = project_active_observation_brief(value)
        check('target_default_projection_is_brief_v5', brief is not None and brief['schema'] == 'active-observation-brief-v5')
        columns = brief['regions']['columns']
        check('M1_target_source_range_is_inclusive_object_local',
              brief['regions']['rows'][0][columns.index('source_triangle_index_ranges')] == [[0, 1]])
        check('prediction_does_not_report_actual_witness',
              brief['status'] == 'predicted' and not brief['inspection']['counts']['covered']
              and brief['regions']['rows'][0][columns.index('complete_witness_pixel_index')] is None)
        check('brief_omits_full_directory_and_disposition',
              'scene_directory' not in brief['binding']['observation_target']
              and 'full_scene_identity' not in brief['binding']['observation_target']
              and 'retained_object_ids' not in brief['binding']['observation_target'])
        full_projection = _tool_result(value, is_error=False, response_detail='full')
        check('full_delivery_retains_same_six_view_classifications',
              json.loads(full_projection['content'][0]['text'])['target_view_classifications']
              == value['target_view_classifications'] and len(value['target_view_classifications']) == 6)
        check('brief_omits_diagnostic_classifications', 'target_view_classifications' not in brief)
        check('source_binding_ignores_accounting_work',
              bridge.source_binding(capture) == bridge.source_binding(dict(capture, observation_target=dict(
                  capture['observation_target'], work={'strategy': 'different', 'counters': {'reads': 999}}))))
        bad = copy.deepcopy(capture)
        bad['observation_target']['scene_directory'][0]['name'] = 'changed'
        rejects('directory_hash_tamper_rejected', lambda: bridge.source_binding(bad),
                'active_observation_target_directory_digest_mismatch')
        bad = copy.deepcopy(capture)
        bad['observation_target']['target_instance_id'] = 'wrong'
        rejects('target_instance_mismatch_rejected', lambda: bridge.source_binding(bad),
                'active_observation_target_instance_mismatch')
        bad = copy.deepcopy(capture)
        bad['observation_target']['retained_object_ids'].reverse()
        rejects('retained_capture_order_mismatch_rejected', lambda: bridge.source_binding(bad),
                'active_observation_target_scene_identity_mismatch')
        bad = copy.deepcopy(capture)
        bad.pop('observation_target')
        rejects('partial_scope_cannot_pose_as_complete', lambda: bridge.source_binding(bad),
                'active_observation_complete_host_identity_required')
        bad = copy.deepcopy(value)
        bad['facts']['scope']['patch_support']['objects'][0]['support_status'] = 'unsupported'
        check('occluder_unknown_denominator_tamper_rejected', project_active_observation_brief(bad) is None)
        for selector in ({'name': 'Target'}, {'id': 'host-target'}):
            query = {'mode': 'active_observation', 'objects': [selector]}
            check('query_single_selector_' + next(iter(selector)), validate_query(query) == query)
            _validate_arguments('human_eye_scene_observe', {'session_id': 'unit', 'query': query, 'include_image': False})
        for selectors in ([], [{'name': 'Target'}, {'name': 'Back panel'}]):
            try:
                validate_query({'mode': 'active_observation', 'objects': selectors})
            except ValueError:
                check('bad_selector_count_' + str(len(selectors)), True)
            else:
                check('bad_selector_count_' + str(len(selectors)), False)
        full = copy.deepcopy(capture)
        full.pop('observation_target')
        full.pop('capture_scope')
        full['host_identity']['capture_scope'] = 'complete_scene_meshes'
        full_session, full_value = pure_result(full, objects, triangles, identity, cameras, targeted=False)
        check('legacy_full_scene_partitions_all_rectangles', len(full_session.regions) == 2)
        check('legacy_full_support_schema_preserved',
              full_value['facts']['scope']['patch_support']['schema'] == 'active-patch-support-v1')
        check('legacy_full_brief_v5_preserved',
              project_active_observation_brief(full_value)['schema'] == 'active-observation-brief-v5')
        invalid_target = copy.deepcopy(capture)
        invalid_target['meshes'][1]['faces'] = [[0, 1, 2]]
        bad_objects, bad_triangles, bad_identity = core.geometry(bridge.scene_from_capture(invalid_target))
        unknown_session, unknown = pure_result(invalid_target, bad_objects, bad_triangles, bad_identity,
                                               cameras, targeted=True)
        unknown_brief = project_active_observation_brief(unknown)
        check('unsupported_target_is_unknown_and_non_targets_stay_occluders',
              not unknown_session.regions and unknown_brief is not None
              and len(unknown['facts']['scope']['objects_without_supported_roi']) == 1
              and unknown['facts']['scope']['objects_without_supported_roi'][0]['object_index'] == 1)
        check('synthetic_TOP_prediction_uses_all_occluders',
              session.index.classifications['TOP'][session.regions[0].roi_id]['status'] == 'positive_area_occlusion')
        check('source_files_unchanged_during_pure_checks',
              sources == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files})
    except Exception as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
    result = {'schema': 'm4-target-product-A-pure-checks-v1', 'synthetic_unit_scope': True,
              'camera_fixture_scope': 'full fit synthetic fixture renamed for metadata validation, not target-camera quality proof',
              'source_files': sources, 'checks': CHECKS, 'passed': failure is None,
              'failure': failure, 'started_ns': started, 'closed_ns': time.perf_counter_ns(),
              'new_Blender_processes': 0, 'new_rasters': 0, 'new_observation_calls': 0,
              'new_model_calls': 0, 'actual_host_qualification': False}
    output = Path(__file__).with_name(sys.argv[1] if len(sys.argv) > 1 else 'PRODUCT_A_PURE_CHECKS.json')
    with output.open('x', encoding='utf8', newline='\n') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(CHECKS), 'failure': failure,
                      'output': str(output)}, ensure_ascii=False))
    if failure is not None:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
