"""Bounded dual-owner checks, with independent direct-ID and legacy-ID rasters.

This runner creates small synthetic scenes in its own new output directory.
The nineteen-call registry is fixed before the first real raster. It never
starts a model, Blender, the consumer benchmark or a default MCP server.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import time
import traceback
import unittest
from unittest.mock import patch


CASES = (
    'subdivided_patch', 'multi_object_near_far_unsupported', 'equal_depth_first_winner',
    'clipped_triangle_fan', 'all_background',
)
UNIT_MODULES = (
    'verification.test_active_observation_images',
    'verification.test_active_observation_patch_images',
    'verification.test_active_observation_region_anchors',
    'verification.test_active_observation_host',
    'verification.test_active_observation_brief',
)
BUFFER_NAMES = ('color', 'depth', 'owners', 'triangle_ids', 'patch_owners')
OWNER_KEYS = ('owner_schema', 'owner_mapping_identity', 'triangle_id_scope')
PATCH_KEYS = ('patch_mapping_version', 'patch_mapping_identity', 'patch_roi_ids',
              'face_patch_ids', 'face_patch_offsets')


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def camera_pool():
    return {'views': [{
        'name': 'SCENE', 'direction_rational': [0, 0, 1], 'target_to_eye_unit': [0, 0, 1],
        'view_matrix': [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, -2], [0, 0, 0, 1]],
        'projection_matrix': [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, .2, 0], [0, 0, 0, 1]],
        'size_px': [64, 64],
    }]}


def fixture_scenes():
    vertices = [[x, y, 0] for y in (-1, 0, 1) for x in (-1, 0, 1)]
    triangles = []
    for row in range(2):
        for column in range(2):
            start = row * 3 + column
            triangles.extend([[start, start + 1, start + 4], [start, start + 4, start + 3]])
    near_triangle = [[-.3, -.3, .5], [.4, -.3, .5], [0, .5, .5]]
    tie_triangle = [[-.7, -.6, 0], [.8, -.6, 0], [0, .8, 0]]
    return {
        'subdivided_patch': {'objects': [{'name': 'Eight faces one patch',
            'vertices': vertices, 'triangles': triangles}]},
        'multi_object_near_far_unsupported': {'objects': [
            {'name': 'Back supported panel',
             'vertices': [[-.7, -.7, 0], [.6, -.7, 0], [.6, .7, 0], [-.7, .7, 0]],
             'triangles': [[0, 1, 2], [0, 2, 3]]},
            {'name': 'Near unsupported triangle', 'vertices': near_triangle, 'triangles': [[0, 1, 2]]},
            {'name': 'Far unsupported triangle',
             'vertices': [[.1, -.6, -.5], [.95, -.6, -.5], [.95, .7, -.5]],
             'triangles': [[0, 1, 2]]},
        ]},
        'equal_depth_first_winner': {'objects': [{'name': 'Coincident input faces',
            'vertices': tie_triangle, 'triangles': [[0, 1, 2], [0, 1, 2]]}]},
        'clipped_triangle_fan': {'objects': [{'name': 'Left clipped triangle',
            'vertices': [[-2, -.5, 0], [.8, -.5, 0], [.8, .8, 0]], 'triangles': [[0, 1, 2]]}]},
        'all_background': {'objects': [{'name': 'Outside right clip plane',
            'vertices': [[2, -.5, 0], [3, -.5, 0], [3, .5, 0], [2, .5, 0]],
            'triangles': [[0, 1, 2], [0, 2, 3]]}]},
    }


class Checks:
    def __init__(self, root, output):
        self.root = root
        self.output = output
        self.assertions = 0
        self.raster_receipts = []
        self.case_results = []
        self.real_raster = importlib.import_module('human_eye_plugin.attention_raster').rasterize_attention
        self.images = importlib.import_module('human_eye_plugin.active_observation_images')
        self.active = importlib.import_module('human_eye_plugin.active_observation')
        self.np = importlib.import_module('numpy')
        self.active_case = None

    def require(self, condition, name):
        self.assertions += 1
        if not condition:
            raise AssertionError(name)

    def expect_error(self, operation, reason):
        try:
            operation()
        except ValueError as error:
            self.require(reason in str(error), 'wrong_rejection:' + str(error))
            return str(error)
        raise AssertionError('expected_rejection:' + reason)

    def raster(self, role, *args, **kwargs):
        receipt = {'number': len(self.raster_receipts) + 1, 'case': self.active_case,
                   'role': role, 'started_ns': time.perf_counter_ns(), 'size': args[3]}
        self.raster_receipts.append(receipt)
        if len(self.raster_receipts) > 19:
            raise AssertionError('registered_raster_cap_exceeded')
        try:
            result = self.real_raster(*args, **kwargs)
            receipt.update(status='complete', tuple_length=len(result))
            return result
        except Exception as error:
            receipt.update(status='error', error_type=type(error).__name__, error=str(error))
            raise
        finally:
            receipt['completed_ns'] = time.perf_counter_ns()
            with (self.output / 'RASTER_RECEIPTS.jsonl').open('a', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps(receipt, ensure_ascii=False) + '\n')

    def product_raster(self, *args, **kwargs):
        return self.raster('product', *args, **kwargs)

    def save_frame(self, name, frame):
        record = {key: value for key, value in frame.items() if key != 'buffers'}
        write_json(self.output / 'cases' / (name + '_FRAME.json'), record)

    def same(self, left, right, name):
        self.require(left.dtype == right.dtype and left.shape == right.shape
                     and self.np.array_equal(left, right), name)

    def check_readback(self, images, frame):
        np = self.np
        with np.load(frame['arrays_path'], allow_pickle=False) as stored:
            keys = sorted(stored.files)
            self.require(set(keys) == set(BUFFER_NAMES + PATCH_KEYS + OWNER_KEYS), 'thirteen_real_npz_keys')
            for key in BUFFER_NAMES:
                self.same(stored[key], frame['buffers'][key], 'saved_' + key)
            for key in OWNER_KEYS:
                self.require(stored[key].item() == frame[key], 'saved_owner_metadata_' + key)
            self.require(stored['face_patch_offsets'].tolist() ==
                         [0] + list(np.cumsum([len(mesh.faces) for mesh in images.meshes])), 'source_offsets')
        saved = {key: value for key, value in frame.items() if key != 'buffers'}
        feedback = images.observe_frame(saved, include_buffers=True)
        self.require(set(feedback['buffers']) == set(BUFFER_NAMES), 'actual_replay_preserves_five_buffers')
        for key in BUFFER_NAMES:
            self.same(feedback['buffers'][key], frame['buffers'][key], 'replayed_' + key)
            self.require(not feedback['buffers'][key].flags.writeable, 'readonly_replay_' + key)
        serializable = images.observe_frame(saved)
        json.dumps(serializable)
        self.require('buffers' not in serializable, 'default_feedback_json_contract')
        self.require(serializable['owner_capabilities'] == {'triangle_ids': True, 'patch_owners': True},
                     'real_replay_capabilities')
        return {'NPZ_keys': keys, 'readback_image_ref': feedback['receipt']['image_ref'],
                'owner_capabilities': feedback['owner_capabilities']}

    def check_fixture(self, name, scene):
        np = self.np
        self.active_case = name
        cameras = camera_pool()
        write_json(self.output / 'cases' / (name + '_INPUT.json'), {'scene': scene, 'cameras': cameras})
        session = self.active.prepare_scene(scene, cameras)
        images = self.images.ActiveObservationImages(session, self.output / 'frames' / name)
        start_count = len(self.raster_receipts)
        raster_module = importlib.import_module('human_eye_plugin.attention_raster')
        triangle_calls = []
        real_triangle = raster_module._raster_triangle

        def triangle(*args, **kwargs):
            triangle_calls.append({'shape': list(args[0].shape), 'raw_id': int(args[8])})
            return real_triangle(*args, **kwargs)

        with patch.object(raster_module, '_raster_triangle', side_effect=triangle):
            frame = images.render_view('SCENE')
        for _ in range(3):
            cached = images.render_view('SCENE')
            self.require(cached is frame, 'product_same_view_same_frame')
            for key in BUFFER_NAMES:
                self.require(cached['buffers'][key] is frame['buffers'][key], 'product_same_view_same_array_' + key)
        self.require(len(self.raster_receipts) - start_count == 1, 'one_product_raster_after_three_repeats')
        self.require(len(list((self.output / 'frames' / name).glob('*.png'))) == 1, 'one_PNG_publication')
        self.require(len(list((self.output / 'frames' / name).glob('*.npz'))) == 1, 'one_NPZ_publication')
        self.save_frame(name, frame)
        pose = cameras['views'][0]
        # Independent direct IDs use source face counts and forward offsets.
        # They never use patch owners or the product raw-ID preparation.
        direct_ids, offset = [], 0
        for source in scene['objects']:
            count = len(source['triangles'])
            direct_ids.append(np.arange(offset, offset + count, dtype=np.int32))
            offset += count
        for mesh, source in zip(images.meshes, scene['objects']):
            self.same(mesh.faces, np.asarray(source['triangles'], dtype=np.int32), 'source_face_order_retained')
        raw = self.raster('independent_direct_raw_ID_oracle', images.meshes,
            np.asarray(pose['view_matrix'], dtype=np.float64),
            np.asarray(pose['projection_matrix'], dtype=np.float64), 64,
            return_owner=True, return_patch_owner=True, face_patch_ids=tuple(direct_ids))
        old = self.raster('legacy_patch_ID_oracle', images.meshes,
            np.asarray(pose['view_matrix'], dtype=np.float64),
            np.asarray(pose['projection_matrix'], dtype=np.float64), 64,
            return_owner=True, return_patch_owner=True, face_patch_ids=images._patch_mapping['face_ids'])
        for index, key in enumerate(('color', 'depth', 'owners')):
            self.same(frame['buffers'][key], raw[index], 'direct_raw_oracle_' + key)
            self.same(frame['buffers'][key], old[index], 'old_patch_oracle_' + key)
        self.same(frame['buffers']['triangle_ids'], raw[3], 'direct_raw_winner_exact')
        self.same(frame['buffers']['patch_owners'], old[3], 'old_patch_winner_exact')
        buffers = frame['buffers']
        occupied = buffers['owners'] >= 0
        self.require(np.all(buffers['triangle_ids'][~occupied] == -1), 'raw_background_minus_one')
        self.require(np.all(buffers['patch_owners'][~occupied] == -1), 'patch_background_minus_one')
        if name == 'subdivided_patch':
            self.require(len(session.regions) == 1, 'one_supported_patch')
            self.require(len(np.unique(buffers['triangle_ids'][occupied])) == 8, 'eight_true_raw_winners_one_patch')
            self.require(np.unique(buffers['patch_owners'][occupied]).tolist() == [0], 'same_patch_multiple_raw_ids')
        elif name == 'multi_object_near_far_unsupported':
            self.require(set(np.unique(buffers['owners'][occupied]).tolist()) == {0, 1, 2}, 'all_three_objects_visible')
            self.require(np.all(buffers['patch_owners'][buffers['owners'] == 1] == -1), 'near_unsupported_retains_raw')
            self.require(set(np.unique(buffers['triangle_ids'][buffers['owners'] == 1]).tolist()) == {2}, 'near_raw_global_two')
            self.require(np.all(buffers['depth'][buffers['owners'] == 1] < 2), 'near_occluder_depth')
            self.require(np.all(buffers['depth'][buffers['owners'] == 2] > 2), 'far_occluder_depth')
        elif name == 'equal_depth_first_winner':
            self.require(occupied.any() and set(np.unique(buffers['triangle_ids'][occupied])) == {0}, 'equal_depth_first_face_wins')
            self.require(len(triangle_calls) == 2, 'both_tied_faces_rasterized')
        elif name == 'clipped_triangle_fan':
            self.require(occupied.any() and set(np.unique(buffers['triangle_ids'][occupied])) == {0}, 'clipped_fan_same_source_ID')
            self.require(len(triangle_calls) == 2, 'clipped_quad_two_fan_triangles')
        else:
            self.require(not occupied.any() and np.isposinf(buffers['depth']).all(), 'all_background_depth_owner')
        result = {'case': name, 'status': 'pass', 'actual_rasters': len(self.raster_receipts) - start_count,
                  'source_triangles': offset, 'source_objects': len(images.meshes),
                  'supported_regions': len(session.regions), 'foreground_pixels': int(occupied.sum()),
                  'triangle_fan_calls': triangle_calls, **self.check_readback(images, frame)}
        self.case_results.append(result)
        write_json(self.output / 'cases' / (name + '_RESULT.json'), result)
        return session, images, frame

    def check_legacy_and_rejections(self, session, images, frame):
        np = self.np
        folder = self.output / 'legacy'
        folder.mkdir()
        with np.load(frame['arrays_path'], allow_pickle=False) as saved:
            old = {key: saved[key] for key in saved.files if key not in ('triangle_ids', *OWNER_KEYS)}
        legacy_path = folder / 'patch_only.npz'
        np.savez_compressed(legacy_path, **old)
        legacy = {key: value for key, value in frame.items()
                  if key not in ('buffers', *OWNER_KEYS, 'owner_capabilities', 'frame_identity')}
        legacy.update(arrays_path=str(legacy_path), arrays_sha256=file_sha(legacy_path), image_ref='legacy-patch-ref')
        result = images.observe_frame(legacy, include_buffers=True)
        self.require(result['owner_capabilities']['triangle_ids'] is False, 'legacy_patch_capability_missing')
        self.require('triangle_ids' not in result['buffers'], 'legacy_patch_no_fake_raw')
        self.require(result['receipt']['image_ref'] == 'legacy-patch-ref', 'legacy_ref_stable')
        three_path = folder / 'three_buffers.npz'
        np.savez_compressed(three_path, **{key: old[key] for key in ('color', 'depth', 'owners')})
        three = {key: value for key, value in legacy.items()
                 if key not in ('patch_mapping_version', 'patch_mapping_identity', 'patch_roi_ids')}
        three.update(arrays_path=str(three_path), arrays_sha256=file_sha(three_path), image_ref='legacy-three-ref')
        replay = images.observe_frame(three, include_buffers=True)
        self.require('triangle_ids' not in replay['buffers'], 'legacy_three_no_fake_raw')
        self.require(replay['receipt']['image_ref'] == 'legacy-three-ref', 'legacy_three_ref_stable')
        declared = dict(legacy, owner_schema=self.images.OWNER_SCHEMA,
                        owner_capabilities={'triangle_ids': True, 'patch_owners': True})
        self.expect_error(lambda: images.observe_frame(declared), 'declared_triangle_owner_frame_required')
        malformed = folder / 'missing_raw.npz'
        np.savez_compressed(malformed, **old, **images._patch_mapping['owner_arrays'])
        changed = {key: value for key, value in frame.items() if key != 'buffers'}
        changed.update(arrays_path=str(malformed), arrays_sha256=file_sha(malformed))
        self.expect_error(lambda: images.observe_frame(changed), 'saved_triangle_owner_missing')
        for key, value in (('owner_schema', 'different-owner-schema'), ('owner_mapping_identity', '0' * 64)):
            changed = dict(frame, **{key: value})
            self.expect_error(lambda: images.observe_frame(changed), 'current_owner_mapping_frame_required')
        original_ref = frame['image_ref']
        original_triangles = frame['buffers']['triangle_ids'].copy()
        baseline = fixture_scenes()['subdivided_patch']
        camera = camera_pool()
        changes = []
        scene_changed = copy.deepcopy(baseline)
        for vertex in scene_changed['objects'][0]['vertices']:
            vertex[2] += .125
        changes.append(('scene_generation', scene_changed, camera))
        reordered = copy.deepcopy(baseline)
        reordered['objects'][0]['triangles'].reverse()
        changes.append(('ordered_faces_mapping', reordered, camera))
        for label, key, replacement in (('size', 'size_px', [128, 128]),
                                        ('projection', 'projection_matrix', [[.75, 0, 0, 0], [0, 1, 0, 0], [0, 0, .2, 0], [0, 0, 0, 1]]),
                                        ('camera', 'view_matrix', [[1, 0, 0, .1], [0, 1, 0, 0], [0, 0, 1, -2], [0, 0, 0, 1]])):
            other = copy.deepcopy(camera)
            other['views'][0][key] = replacement
            changes.append((label, baseline, other))
        rejected = {}
        for label, scene, cameras in changes:
            session.rebind(scene, cameras)
            images._synchronize()
            self.require(not images._frames, 'cache_invalidated_' + label)
            rejected[label] = self.expect_error(lambda: images.observe_frame(frame),
                'saved_patch_mapping_mismatch' if label == 'ordered_faces_mapping' else 'current_scene_camera_frame_required')
            session.rebind(baseline, camera)
            images._synchronize()
        self.require(frame['image_ref'] == original_ref, 'old_frame_ref_never_retargeted')
        self.same(frame['buffers']['triangle_ids'], original_triangles, 'old_held_raw_arrays_never_mutated')
        write_json(self.output / 'LEGACY_AND_INVALIDATION.json', {'status': 'pass', 'rejections': rejected,
            'legacy_patch_capabilities': result['owner_capabilities'],
            'legacy_three_capabilities': replay['owner_capabilities'],
            'size_scope': '128px binding invalidation only; focused raster fixtures are all 64px.'})

    def check_object_order_and_bad_winners(self, session, images, frame):
        np = self.np
        foreground = frame['buffers']['owners'] == 0
        location = tuple(np.argwhere(foreground)[0])
        changed = {key: value for key, value in frame.items() if key not in ('arrays_path', 'arrays_sha256')}
        changed['buffers'] = {key: value.copy() for key, value in frame['buffers'].items()}
        changed['buffers']['triangle_ids'][location] = 2
        self.expect_error(lambda: images.observe_frame(changed), 'source_triangle_object_order_mismatch')
        changed['buffers']['triangle_ids'][location] = frame['buffers']['triangle_ids'][location]
        changed['buffers']['patch_owners'][location] = -1
        self.expect_error(lambda: images.observe_frame(changed), 'source_triangle_patch_owner_mismatch')
        scene = fixture_scenes()['multi_object_near_far_unsupported']
        scene['objects'][0], scene['objects'][1] = scene['objects'][1], scene['objects'][0]
        session.rebind(scene, camera_pool())
        images._synchronize()
        self.require(not images._frames, 'object_order_invalidates_cache')
        rejection = self.expect_error(lambda: images.observe_frame(frame), 'current_frame_geometry_camera_binding_required')
        write_json(self.output / 'OBJECT_ORDER_AND_WINNERS.json', {'status': 'pass', 'object_order_rejection': rejection})

    def check_public_tuple_contract(self, images):
        self.active_case = 'public_tuple_contract'
        pose = camera_pool()['views'][0]
        args = (images.meshes, self.np.asarray(pose['view_matrix'], dtype=self.np.float64),
                self.np.asarray(pose['projection_matrix'], dtype=self.np.float64), 64)
        two = self.raster('public_2_tuple', *args)
        three = self.raster('public_3_tuple', *args, return_owner=True)
        self.require(len(two) == 2 and len(three) == 3, 'public_two_three_tuple_lengths')
        self.same(two[0], three[0], 'public_tuple_color')
        self.same(two[1], three[1], 'public_tuple_depth')

    def check_publication_failure(self):
        self.active_case = 'publication_failure_then_recovery'
        session = self.active.prepare_scene(fixture_scenes()['subdivided_patch'], camera_pool())
        images = self.images.ActiveObservationImages(session, self.output / 'frames' / 'publication_failure')
        before = len(self.raster_receipts)
        with patch.object(self.images.np, 'savez_compressed', side_effect=OSError('injected_post_raster_NPZ_failure')):
            try:
                images.render_view('SCENE')
            except OSError as error:
                self.require(str(error) == 'injected_post_raster_NPZ_failure', 'expected_publication_failure')
            else:
                raise AssertionError('expected_publication_failure')
        self.require(len(self.raster_receipts) == before + 1, 'failed_publish_keeps_raster_cost')
        self.require(not images._frames, 'failed_publish_no_half_frame_cache')
        frame = images.render_view('SCENE')
        self.require(len(self.raster_receipts) == before + 2, 'recovery_new_raster_once')
        self.require(Path(frame['image_path']).name.startswith('002-'), 'recovery_has_new_construction_sequence')
        self.require(images.render_view('SCENE') is frame, 'recovered_frame_cached')
        self.save_frame('publication_recovery', frame)
        self.check_readback(images, frame)

    def run_units(self):
        before = len(self.raster_receipts)
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in UNIT_MODULES)
        log = io.StringIO()
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        (self.output / 'UNIT_OUTPUT.txt').write_text(log.getvalue(), encoding='utf-8')
        record = {'modules': list(UNIT_MODULES), 'tests_run': result.testsRun,
                  'failures': [{'test': str(test), 'traceback': detail} for test, detail in result.failures],
                  'errors': [{'test': str(test), 'traceback': detail} for test, detail in result.errors],
                  'skipped': [{'test': str(test), 'reason': reason} for test, reason in result.skipped],
                  'actual_raster_calls': len(self.raster_receipts) - before, 'passed': result.wasSuccessful()}
        write_json(self.output / 'UNIT_RESULT.json', record)
        self.require(record['actual_raster_calls'] == 0, 'mock_unit_modules_do_not_execute_real_raster')
        self.require(result.testsRun == 31, 'frozen_related_unit_denominator')
        self.require(result.wasSuccessful(), 'related_unit_regression')
        return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--product-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, output = args.product_root.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'cases').mkdir()
    sys.path.insert(0, str(root))
    checks = Checks(root, output)
    source_paths = [root / 'human_eye_plugin' / name for name in (
        'active_observation_images.py', 'active_observation_host.py', 'live_spatial_mcp.py', 'attention_raster.py')]
    registry = {'schema': 'view-reuse-focused-v1', 'product_root': str(root),
        'source_pins': [{'path': str(path), 'sha256': file_sha(path)} for path in source_paths],
        'cases': list(CASES), 'per_case_calls': ['product', 'independent_direct_raw_ID_oracle', 'legacy_patch_ID_oracle'],
        'extra_calls': ['public_2_tuple', 'public_3_tuple', 'publication_failure', 'publication_recovery'],
        'actual_raster_cap': 19, 'focused_size_px': [64, 64], 'units': list(UNIT_MODULES),
        'units_expected_tests': 31, 'unit_expected_real_raster': 0, 'models': 0, 'Blender': 0}
    write_json(output / 'CASE_REGISTRY.json', registry)
    result = {'schema': 'view-reuse-product-checks-v1', 'passed': False,
              'product_module': str(Path(checks.images.__file__).resolve()), 'source_pins': registry['source_pins'],
              'started_ns': time.perf_counter_ns(), 'failures': []}
    try:
        with patch.object(checks.images, 'rasterize_attention', side_effect=checks.product_raster):
            cases = {name: checks.check_fixture(name, scene) for name, scene in fixture_scenes().items()}
            checks.check_legacy_and_rejections(*cases['subdivided_patch'])
            checks.check_object_order_and_bad_winners(*cases['multi_object_near_far_unsupported'])
            checks.check_public_tuple_contract(cases['subdivided_patch'][1])
            checks.check_publication_failure()
            result['units'] = checks.run_units()
        checks.require(len(checks.raster_receipts) == 19, 'exact_registered_raster_count')
        result['passed'] = True
    except Exception as error:
        result['failures'].append({'error_type': type(error).__name__, 'error': str(error), 'traceback': traceback.format_exc()})
    result.update(completed_ns=time.perf_counter_ns(), assertions=checks.assertions,
                  focused_cases=checks.case_results, actual_raster_calls=len(checks.raster_receipts),
                  actual_raster_roles={role: sum(row['role'] == role for row in checks.raster_receipts)
                                      for role in sorted(set(row['role'] for row in checks.raster_receipts))},
                  scope='Synthetic 64px ownership and saved replay, legacy compatibility, small-scene source invalidation. '
                        'Consumer reuse, 512px installed integration and paired costs are separate. No model or task-benefit claim.')
    write_json(output / 'RESULT.json', result)
    print(json.dumps({'passed': result['passed'], 'assertions': result['assertions'],
                      'actual_raster_calls': result['actual_raster_calls'], 'result': str(output / 'RESULT.json'),
                      'failures': [item['error'] for item in result['failures']]}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
