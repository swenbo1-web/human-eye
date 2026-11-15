"""Direct read-context and serialization checks. No observation method is called."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
fixture_spec = importlib.util.spec_from_file_location('target_public_pure_fixture', HERE / 'target_public_pure_checks.py')
fixture = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(fixture)

from human_eye_plugin.active_observation_host import source_binding
from human_eye_plugin.blender_host import BlenderHostError
from human_eye_plugin.live_spatial_mcp import _tool_result
from human_eye_plugin.read_context import ReadContext, query_key


CHECKS = []


def check(name, condition):
    CHECKS.append({'name': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)


def main():
    paths = [ROOT / 'human_eye_plugin' / name for name in (
        'blender_host.py', 'blender_mcp_host.py', 'query_policy.py', 'active_observation.py',
        'active_observation_host.py', 'live_service.py', 'live_spatial_mcp.py', 'read_context.py')]
    sources = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    failure = None
    try:
        capture, objects, triangles, identity, cameras = fixture.fixture()
        _, predicted = fixture.pure_result(capture, objects, triangles, identity, cameras, targeted=True)
        binding = source_binding(capture)
        context = ReadContext()
        context.activate(capture, 'active_observation', binding)
        false_key = query_key({'mode': 'active_observation', 'include_image': False,
                               'objects': [{'name': 'Target'}]})
        calls = []

        def compute():
            calls.append('pure_prediction')
            return copy.deepcopy(predicted)

        first, hit = context.result(false_key, compute)
        check('cold_target_prediction_is_computed_once', not hit and len(calls) == 1)
        cached, hit = context.result(false_key, compute)
        check('same_target_source_and_query_reuse_prediction', hit and cached == first and len(calls) == 1)
        cached['frames'].append('caller_modified')
        restored, hit = context.result(false_key, compute)
        check('cached_result_detaches_caller_mutation', hit and restored['frames'] == [] and len(calls) == 1)
        true_key = query_key({'mode': 'active_observation', 'include_image': True,
                              'objects': [{'name': 'Target'}]})
        alternate, hit = context.result(true_key, lambda: {'status': 'unknown', 'pure_marker': 'image_query'})
        check('image_query_does_not_reuse_prediction_key', not hit and alternate['pure_marker'] == 'image_query')
        full = copy.deepcopy(capture)
        del full['observation_target']
        del full['capture_scope']
        full['host_identity']['capture_scope'] = 'complete_scene_meshes'
        context.activate(full, 'active_observation', source_binding(full))
        _, hit = context.result(false_key, compute)
        check('full_scope_cannot_reuse_target_result_even_with_same_capture_token', not hit and len(calls) == 2)
        context.activate(capture, 'active_observation', binding)
        _, hit = context.result(false_key, compute)
        check('returning_to_unchanged_target_can_reuse_its_own_prediction', hit and len(calls) == 2)

        renamed_selector = copy.deepcopy(capture)
        renamed_selector['observation_target']['selector'] = {'id': capture['observation_target']['target_object_id']}
        context.activate(renamed_selector, 'active_observation', source_binding(renamed_selector))
        _, hit = context.result(false_key, compute)
        check('explicit_target_selector_binding_is_isolated', not hit and len(calls) == 3)

        replacement = copy.deepcopy(capture)
        target = replacement['observation_target']
        target['target_instance_id'] = 'replacement-102'
        target_id = target['target_object_id']
        replacement['host_identity']['object_instances'][target_id] = target['target_instance_id']
        target['full_scene_identity']['object_instances'][target_id] = target['target_instance_id']
        next(row for row in target['scene_directory'] if row['object_id'] == target_id)['instance_id'] = target['target_instance_id']
        target['directory_sha256'] = fixture.directory_digest(target['scene_directory'])
        context.activate(replacement, 'active_observation', source_binding(replacement))
        _, hit = context.result(false_key, compute)
        check('same_name_replacement_invalidates_by_actual_instance_binding', not hit and len(calls) == 4)

        changed_camera = copy.deepcopy(capture)
        changed_camera['observation_target']['camera_plan']['views'][0]['projection_matrix'][0][0] *= 1.00001
        context.activate(changed_camera, 'active_observation', source_binding(changed_camera))
        _, hit = context.result(false_key, compute)
        check('camera_plan_change_invalidates_prediction_binding', not hit and len(calls) == 5)

        changed_geometry = copy.deepcopy(capture)
        changed_geometry['meshes'][1]['vertices'][0][1] -= 0.125
        changed_geometry['revision'] = 'synthetic-source:2'
        changed_geometry['capture_state']['revision'] = 2
        context.activate(changed_geometry, 'active_observation', source_binding(changed_geometry))
        _, hit = context.result(false_key, compute)
        check('geometry_generation_change_invalidates_cached_prediction', not hit and len(calls) == 6)

        exception_key = query_key({'pure_case': 'camera_refusal'})

        def refused():
            raise BlenderHostError('active_observation_target_camera_numeric_insufficient')

        try:
            context.result(exception_key, refused)
        except BlenderHostError:
            check('numeric_refusal_propagates_without_cached_success', exception_key not in context._results)
        else:
            check('numeric_refusal_propagates_without_cached_success', False)
        recovered, hit = context.result(exception_key, lambda: {'pure_recovery': True})
        check('definite_refusal_does_not_poison_later_pure_result', not hit and recovered == {'pure_recovery': True})

        delivered = _tool_result(predicted, is_error=False)
        public = json.loads(delivered['content'][0]['text'])
        check('prediction_delivery_is_one_text_block_with_zero_native_images',
              len(delivered['content']) == 1 and delivered['content'][0]['type'] == 'text'
              and public['image_delivery']['local_verified_image_count'] == 0
              and public['image_delivery']['mcp_content_constructed_image_count'] == 0)
        region_columns = public['regions']['columns']
        check('prediction_keeps_null_witness_and_zero_covered', public['status'] == 'predicted'
              and public['inspection']['counts']['covered'] == 0
              and all(row[region_columns.index('complete_witness_pixel_index')] is None for row in public['regions']['rows']))
        check('prediction_delivery_has_no_image_table_or_observed_views',
              'images' not in public and not public['coverage'].get('observed_views'))
        check('candidate_sources_unchanged_during_checks',
              sources == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})
    except Exception as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
    result = {'schema': 'm4-target-camera-cache-source-prediction-pure-v1',
              'passed': failure is None, 'checks': CHECKS, 'failure': failure,
              'candidate_source_pins': sources,
              'fixture_path': str(HERE / 'target_public_pure_checks.py'),
              'fixture_sha256': hashlib.sha256((HERE / 'target_public_pure_checks.py').read_bytes()).hexdigest(),
              'scope': 'synthetic cache/source/serialization regressions, not camera scenes or actual host operations',
              'new_product_observations': 0, 'new_Blender_starts': 0, 'new_rasters': 0, 'new_model_calls': 0}
    output = HERE / 'B_INSTALLED_CACHE_SOURCE_PREDICTION.json'
    with output.open('x', encoding='utf8', newline='\n') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(CHECKS), 'failure': failure,
                      'output': str(output)}))
    if failure is not None:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
