"""Directed fake-host acquisition and target-contract checks without Blender."""

import copy
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from verification.test_blender_host_contracts import FakeObject, host_fixture, matrix, _module as host_module
from human_eye_plugin import active_observation as core
from human_eye_plugin import active_observation_host as bridge
from human_eye_plugin.live_spatial_mcp import _tool_result, project_active_observation_brief
from human_eye_plugin.read_context import ReadContext, query_key


CHECKS = []
FAKE_CAPTURES = 0


def check(name, condition):
    CHECKS.append({'name': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)


class CountingMesh:
    def __init__(self, vertices, faces):
        self.vertices = [NS(co=tuple(point)) for point in vertices]
        self.polygons = [NS(vertices=tuple(face)) for face in faces]
        self.loops = [NS(vertex_index=index) for face in faces for index in face]
        self.loop_triangles = [NS(vertices=tuple(face)) for face in faces]
        self.shape_keys = self.animation_data = self.library = None
        self.triangulations = 0

    def calc_loop_triangles(self):
        self.triangulations += 1


class CountingObject(FakeObject):
    def __init__(self, row, uid):
        super().__init__(row['name'])
        points = [[float(Fraction(value)) for value in point] for point in row['world_vertices_m']]
        self.data = CountingMesh(points, row['triangles'])
        low = [min(point[axis] for point in points) for axis in range(3)]
        high = [max(point[axis] for point in points) for axis in range(3)]
        self.bound_box = list(itertools.product(*[(a, b) for a, b in zip(low, high)]))
        self.session_uid, self.is_evaluated = uid, True
        self.mesh_calls = 0

    def to_mesh(self):
        self.mesh_calls += 1
        return super().to_mesh()


class UnknownCount:
    def __len__(self):
        raise AttributeError('synthetic count unavailable')


class LargeUpperCount:
    def __len__(self):
        return 1_001_024


def fixture(geometry, *, target_only=False):
    host, _, _, _ = host_fixture()
    rows = [row for row in geometry['objects'] if not target_only or row['name'] == geometry['target_name']]
    objects = [CountingObject(row, 1000 + index) for index, row in enumerate(rows)]
    host.scene.objects = objects
    host.scene.session_uid = 77
    handlers = NS(depsgraph_update_post=[], undo_post=[], redo_post=[], load_post=[], persistent=lambda function: function)
    host.bpy.app = NS(driver_namespace={}, handlers=handlers)
    host.view_layer.objects.active = next(obj for obj in objects if obj.name == geometry['target_name'])
    host.identity_metadata = True
    return host, {obj.name: obj for obj in objects}


def capture(host, target):
    global FAKE_CAPTURES
    FAKE_CAPTURES += 1
    return host.capture_active_observation({'name': target}, time.perf_counter_ns() + 30_000_000_000, 64 * 1024 * 1024)


def predicted_result(packet):
    objects, triangles, identity = core.geometry(bridge.scene_from_capture(packet))
    cameras = packet['observation_target']['camera_plan']
    target_index = packet['observation_target']['target_object_index']
    session = core.prepare_scene_from_parsed(objects, triangles, identity, cameras, target_object_index=target_index)
    binding = bridge.source_binding(packet, cameras, geometry_identity=identity)
    binding.pop('camera_specification')
    binding.update(runtime_source_sha256='b' * 64, source_status='loaded_generation',
                   disk_status='disk_not_checked', source_check_scope='bound_generation_identity')
    facts = session.short_facts()
    for region in facts['regions']:
        obj = binding['objects'][region['object_index']]
        region.update(host_id=obj['host_id'], instance_id=obj['instance_id'])
    facts['scope'] = bridge._patch_scope_facts(session, binding)
    facts['location_conventions'] = bridge._location_conventions(cameras)
    value = {'status': 'predicted', 'result_kind': 'active_observation', 'observation_status': 'prediction_only',
             'session_id': 'pure', 'binding': binding, 'facts': facts, 'frames': [], 'read_only': True,
             'execution_authority': False, 'image_delivery': {'local_verified_image_count': 0,
                 'mcp_content_constructed_image_count': 0, 'consumer_read_status': 'unconfirmed',
                 'frame_reuses': 0, 'new_raster_attempts': 0}}
    return session, value


def main():
    source = ROOT / 'human_eye_plugin/blender_host.py'
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    host_module._READONLY_LOADED_HOST_SHA256 = source_sha
    geometry_path = HERE / 'reference/FROZEN_GEOMETRY.json'
    geometry = json.loads(geometry_path.read_bytes())
    before_sources = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in (ROOT / 'human_eye_plugin').glob('*.py')}
    failure = None
    main_work = {}
    try:
        host, objects = fixture(geometry)
        packet = capture(host, geometry['target_name'])
        main_work = packet['observation_target']['work']
        kept = packet['observation_target']['retained_object_ids']
        excluded = packet['observation_target']['excluded_object_ids']
        by_id = {host.object_id(obj): obj for obj in objects.values()}
        check('Far11_is_excluded_before_detailed_extraction', host.object_id(objects['M4_Far_11']) in excluded
              and objects['M4_Far_11'].mesh_calls == objects['M4_Far_11'].data.triangulations == 0)
        check('target_is_extracted_once', objects[geometry['target_name']].mesh_calls == 1
              and objects[geometry['target_name']].data.triangulations == 1)
        check('all_excluded_objects_have_zero_mesh_and_triangle_work',
              all(by_id[oid].mesh_calls == by_id[oid].data.triangulations == 0 for oid in excluded))
        check('only_retained_objects_are_expanded_once',
              all(by_id[oid].mesh_calls == by_id[oid].data.triangulations == 1 for oid in kept))
        check('actual_resource_counters_match_retained_reads', main_work['residency_delta']['to_mesh'] == len(kept)
              and main_work['residency_delta']['triangulations'] == len(kept)
              and main_work['residency_delta']['resource_vertices_read'] == main_work['expanded_vertices']
              and main_work['residency_delta']['world_vertices_transformed'] == main_work['expanded_vertices'])
        expected_tests = sum(host_module._observation_outside_xy_viewports(row['bounds_world_m'], packet['observation_target']['camera_plan'])[1]
                             for row in packet['observation_target']['scene_directory']
                             if row['object_id'] != host.object_id(objects[geometry['target_name']]))
        check('bound_tests_are_actual_view_tests', main_work['bound_tests'] == expected_tests and expected_tests > 0)
        source_order = [row['object_id'] for row in packet['observation_target']['scene_directory']]
        check('retained_and_excluded_keep_source_relative_order',
              [oid for oid in source_order if oid in set(kept)] == kept
              and [oid for oid in source_order if oid in set(excluded)] == excluded)
        check('full_directory_and_subset_counts_are_distinct', len(source_order) == 14
              and len(packet['meshes']) == len(kept) < 14 and len(kept) + len(excluded) == 14)
        a_qualification = json.loads((HERE / 'A_QUALIFICATION.json').read_bytes())
        a_slot = Path(a_qualification['records'][0]['slot'])
        a_capture = json.loads((a_slot / 'MAIN_CAPTURE_01.json').read_bytes())
        check('candidate_uses_actual_A_camera_plan_unchanged',
              packet['observation_target']['camera_plan'] == a_capture['observation_target']['camera_plan'])
        a_meshes = {mesh['name']: mesh for mesh in a_capture['meshes']}
        check('retained_vertices_and_source_faces_equal_actual_A', all(
            mesh['vertices'] == a_meshes[mesh['name']]['vertices']
            and mesh['faces'] == a_meshes[mesh['name']]['faces'] for mesh in packet['meshes']))
        session, value = predicted_result(packet)
        brief = project_active_observation_brief(value)
        check('subset_uses_existing_brief_v5', brief is not None and brief['schema'] == 'active-observation-brief-v5')
        columns = brief['regions']['columns']
        ranges = sorted(row[columns.index('source_triangle_index_ranges')] for row in brief['regions']['rows'])
        check('both_target_source_ranges_preserved', ranges == [[[0, 511]], [[512, 513]]])
        check('subset_coverage_still_has_only_two_target_regions', len(session.regions) == 2
              and brief['scope']['observation_scope']['target_object_count'] == 1
              and brief['scope']['observation_scope']['full_scene_object_count'] == 14
              and brief['scope']['observation_scope']['excluded_object_count'] == len(excluded))
        text = _tool_result(value, is_error=False)
        check('prediction_creates_no_images_or_witnesses', len(text['content']) == 1
              and value['facts']['inspection']['counts']['covered'] == 0
              and all(row['complete_witness'] is None for row in value['facts']['region_evidence']))

        context = ReadContext()
        key = query_key({'mode': 'active_observation', 'objects': [{'name': geometry['target_name']}], 'include_image': False})
        context.activate(packet, 'active_observation', bridge.source_binding(packet))
        context.result(key, lambda: {'status': 'predicted', 'generation': 'before_move'})
        objects['M4_Far_11']._matrix_world = matrix((-11., 0., 0.))
        moved = capture(host, geometry['target_name'])
        check('excluded_object_moving_into_view_is_now_captured',
              host.object_id(objects['M4_Far_11']) in moved['observation_target']['retained_object_ids']
              and objects['M4_Far_11'].mesh_calls == 1)
        context.activate(moved, 'active_observation', bridge.source_binding(moved))
        _, hit = context.result(key, lambda: {'status': 'predicted', 'generation': 'after_move'})
        check('moved_excluded_object_invalidates_cached_target_result', not hit)
        repeated = capture(host, geometry['target_name'])
        context.activate(repeated, 'active_observation', bridge.source_binding(repeated))
        _, hit = context.result(key, lambda: {'unexpected': True})
        check('unchanged_source_reuses_its_own_result', hit)
        check('hot_target_does_not_repeat_mesh_extraction', objects[geometry['target_name']].mesh_calls == 1)
        host.close_residency()

        host, objects = fixture(geometry, target_only=True)
        only = capture(host, geometry['target_name'])
        check('target_only_has_no_exclusion_or_bound_tests', len(only['meshes']) == 1
              and only['observation_target']['excluded_object_ids'] == []
              and only['observation_target']['work']['bound_tests'] == 0
              and next(iter(objects.values())).mesh_calls == 1)
        host.close_residency()

        for name, counter in [('unknown_count', UnknownCount()), ('upper_budget', LargeUpperCount())]:
            host, objects = fixture(geometry)
            objects['M4_Far_11'].data.loops = counter
            complete = capture(host, geometry['target_name'])
            check('require_complete_' + name, complete['observation_target']['work']['source_counts_require_complete'] is True
                  and len(complete['meshes']) == 14 and complete['observation_target']['work']['bound_tests'] == 0
                  and all(obj.mesh_calls == 1 for obj in objects.values()))
            host.close_residency()

        host, objects = fixture(geometry)
        objects['M4_Far_11'].bound_box = None
        unknown = capture(host, geometry['target_name'])
        check('initial_unknown_bbox_is_read_and_retained', host.object_id(objects['M4_Far_11'])
              in unknown['observation_target']['retained_object_ids'] and objects['M4_Far_11'].mesh_calls == 1)
        host.close_residency()

        bad_camera = copy.deepcopy(packet['observation_target']['camera_plan'])
        bad_camera['views'][0]['projection_matrix'][0][1] = 0.01
        outside_bounds = next(row['bounds_world_m'] for row in packet['observation_target']['scene_directory']
                              if row['name'] == 'M4_Far_11')
        check('unsupported_projection_structure_is_retained', host_module._observation_outside_xy_viewports(outside_bounds, bad_camera)[0] is False)
        check('unknown_and_nonfinite_bounds_are_retained', host_module._observation_outside_xy_viewports(None, packet['observation_target']['camera_plan'])[0] is False
              and host_module._observation_outside_xy_viewports([[math.inf] * 3, [math.inf] * 3], packet['observation_target']['camera_plan'])[0] is False)
        host, objects = fixture(geometry)
        full = host.capture_scene()
        check('legacy_complete_capture_still_reads_all_objects', len(full['meshes']) == 14
              and all(obj.mesh_calls == 1 for obj in objects.values()) and 'observation_target' not in full)
        host.close_residency()
        check('product_sources_unchanged_during_pure_checks', before_sources == {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT / 'human_eye_plugin').glob('*.py')})
    except Exception as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
    result = {'schema': 'm4-target-acquisition-002-product-pure-v1', 'passed': failure is None,
              'checks': CHECKS, 'failure': failure, 'host_source_sha256': source_sha,
              'frozen_geometry_sha256': hashlib.sha256(geometry_path.read_bytes()).hexdigest(),
              'fake_host_capture_calls': FAKE_CAPTURES, 'main_fake_work': main_work,
              'fake_scope': 'Real host acquisition function with reused existing bpy doubles. Not Blender evaluation or profiling.',
              'oracle_scope': 'Independent numeric/coverage oracle is maintained by quality agent. This file checks acquisition and representation.',
              'new_Blender_starts': 0, 'new_rasters': 0, 'new_product_observations': 0, 'new_model_calls': 0}
    with (HERE / 'PRODUCT_PURE_01.json').open('x', encoding='utf8', newline='\n') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'passed': failure is None, 'checks': len(CHECKS), 'failure': failure,
                      'fake_host_capture_calls': FAKE_CAPTURES}))
    if failure:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
