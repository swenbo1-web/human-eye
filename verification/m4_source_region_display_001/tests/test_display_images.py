"""Display participation and evidence feedback using synthetic frame buffers.

Every raster entry is mocked. PNG/NPZ encoding and validation are real bounded
64-square work and are separate from the zero real-raster construction count.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin import source_region
from human_eye_plugin.active_observation_images import SceneObservationImages


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf8')).hexdigest()


def snapshot(capture, visible=(False, True, True)):
    value = {'schema': 'blender-viewport-display-v1', 'scope': 'active_view_layer',
        'status': 'captured', 'view_layer': {'name': '当前层', 'instance_id': 'layer:1'},
        'objects': [{'host_id': mesh['object_id'],
            'instance_id': capture['host_identity']['object_instances'][mesh['object_id']],
            'visible_get': shown, 'hide_get': not shown, 'hide_viewport': False,
            'hide_render': index != 0} for index, (mesh, shown) in enumerate(zip(capture['meshes'], visible))]}
    return {**value, 'sha256': digest(value)}


def captured(visible=(False, True, True)):
    meshes = [{'object_id': name, 'name': name,
        'vertices': [[0, 0, height], [1, 0, height], [1, 1, height], [0, 1, height]],
        'faces': [[0, 1, 2], [0, 2, 3]]} for name, height in [('Cube', 2), ('Body', 1), ('Ref', 0)]]
    value = {'unit': 'm', 'coordinate_frame': 'world', 'source': 'blender', 'revision': 'test:1',
        'capture_scope': 'complete_scene_meshes', 'meshes': meshes,
        'host_identity': {'schema_version': '1.0', 'document_epoch': 'a' * 64,
            'capture_scope': 'complete_scene_meshes',
            'object_instances': {mesh['object_id']: 'instance-' + mesh['name'] for mesh in meshes}},
        'capture_state': {'instance_id': 'host:1', 'epoch': 1, 'revision': 1, 'selection_key': 'scene'}}
    value['display_snapshot'] = snapshot(value, visible)
    return value


def resign(capture):
    value = capture['display_snapshot']
    value['sha256'] = digest({key: item for key, item in value.items() if key != 'sha256'})


def prepare(capture=None):
    original = source_region._observation_target_cameras

    def cameras(*args):
        value = original(*args)
        for pose in value['views']:
            pose['size_px'] = [64, 64]
        return value

    with patch.object(source_region, '_observation_target_cameras', side_effect=cameras):
        return source_region.prepare_region(captured() if capture is None else capture,
            {'region': {'object': {'name': 'Body'}, 'source_triangle_indices': [1]}})


def buffers(prepared, object_index=1, face_index=1):
    color = np.zeros((64, 64, 3), dtype=np.uint8)
    depth = np.full((64, 64), np.inf, dtype=np.float64)
    owners = np.full((64, 64), -1, dtype=np.int32)
    triangles = np.full((64, 64), -1, dtype=np.int32)
    if object_index is not None:
        color[12:16, 20:24] = (180, 190, 205)
        depth[12:16, 20:24] = 1
        owners[12:16, 20:24] = object_index
        offset = sum(len(mesh.faces) for mesh in prepared.meshes[:object_index])
        triangles[12:16, 20:24] = offset + face_index
    return color, depth, owners, triangles


def adapter(prepared, directory, *, display=True):
    options = {}
    if display:
        options = {'display_identity': prepared.binding['display_identity'],
            'image_scope': prepared.binding['image_scope'],
            'object_mask': tuple(prepared.binding['image_scope']['participation_mask'])}
    return SceneObservationImages(prepared.objects, prepared.cameras, directory,
        scene_identity=prepared.binding['geometry_identity'],
        candidate_identity=prepared.binding['camera_identity'], _prepared_meshes=prepared.meshes,
        _reuse_published_payload=True, **options)


class DisplayImagesTests(unittest.TestCase):
    def setUp(self):
        self.guard = patch('human_eye_plugin.active_observation_images.rasterize_attention',
            side_effect=AssertionError('real raster is outside these pure controls'))
        self.guard.start()
        self.addCleanup(self.guard.stop)

    def observe(self, prepared, directory, object_index=1, face_index=1):
        with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                   return_value=buffers(prepared, object_index, face_index)) as raster:
            result = source_region.observe_region(prepared, directory, include_image=True)
        return result, raster

    def test_effective_visibility_drives_mask_with_full_source_offsets(self):
        prepared = prepare()
        with tempfile.TemporaryDirectory() as directory:
            result, raster = self.observe(prepared, directory)
            self.assertIs(raster.call_args.args[0], prepared.meshes)
            self.assertEqual(raster.call_args.kwargs['object_mask'], (False, True, True))
            self.assertEqual([values.tolist() for values in raster.call_args.kwargs['face_patch_ids']],
                             [[0, 1], [2, 3], [4, 5]])
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['observation_status'], 'locally_observed')
            visible = result['facts']['visibility']
            self.assertEqual(visible['status'], 'observed_samples')
            self.assertEqual(visible['selected_surface_pixels'], 16)
            self.assertEqual(visible['visible_source_triangle_indices'], [1])
            self.assertIn('complete_surface_visibility', visible['unknown'])
            self.assertIsNone(visible['complete_witness'])
            scope = result['binding']['image_scope']
            self.assertEqual(scope['participating_object_indices'], [1, 2])
            self.assertEqual(scope['excluded_object_indices'], [0])
            self.assertEqual(scope['objects'][0]['reason'], 'host_visible_get_false')
            self.assertTrue(scope['objects'][1]['hide_render'])
            self.assertTrue(scope['objects'][1]['participates'])
            frame = result['frames'][0]
            self.assertEqual(frame['display_identity'], scope['identity'])
            self.assertEqual(frame['image_scope'], scope)
            self.assertEqual(frame['all_object_count'], 3)
            self.assertEqual(frame['all_triangle_count'], 6)
            self.assertEqual(result['work']['fresh_payload_reuses'], 1)
            with np.load(frame['arrays_path'], allow_pickle=False) as arrays:
                self.assertEqual(arrays['face_patch_offsets'].tolist(), [0, 2, 4, 6])
                self.assertEqual(arrays['display_object_mask'].tolist(), [False, True, True])
                self.assertEqual(str(arrays['display_identity']), scope['identity'])
            measured = source_region.measure_region(prepared, {'name': 'Cube'}, None)
            self.assertEqual(measured['facts']['surface_proximity']['value']['distance_m'], 1)
            self.assertEqual(measured['reference']['object_index'], 0)
            self.assertEqual(len(prepared.meshes[0].faces), 2)

    def test_zero_samples_distinguish_hidden_target_and_displayed_without_pixels(self):
        for shown, reason, winner in [
                ((True, True, True), 'selected_region_displayed_without_pixels', 0),
                ((True, False, True), 'selected_region_not_displayed', 0),
                ((False, False, False), 'selected_region_not_displayed', None)]:
            with self.subTest(shown=shown), tempfile.TemporaryDirectory() as directory:
                prepared = prepare(captured(shown))
                result, _ = self.observe(prepared, directory, winner)
                visible = result['facts']['visibility']
                self.assertEqual(result['status'], 'partial')
                self.assertEqual(result['observation_status'], 'evidence_insufficient')
                self.assertEqual(visible['status'], 'unknown')
                self.assertEqual(visible['reason'], reason)
                self.assertEqual(visible['selected_surface_pixels'], 0)
                self.assertEqual(visible['selected_source_triangle_count'], 1)
                self.assertEqual(visible['selected_object_participates'], shown[1])
                self.assertEqual(visible['visible_source_triangle_indices'], [])
                self.assertEqual(visible['unseen_source_triangle_indices'], [1])
                self.assertIsNone(visible['visible_pixel_bounds'])
                measured = source_region.measure_region(prepared, {'name': 'Cube'}, None)
                self.assertEqual(measured['status'], 'complete')
                self.assertEqual(measured['facts']['surface_proximity']['value']['distance_m'], 1)
                again = source_region.observe_region(prepared, directory, include_image=True)
                self.assertEqual(again['status'], 'partial')
                self.assertEqual(again['observation_status'], 'evidence_insufficient')
                self.assertEqual(again['work']['raster_attempts'], 0)
                self.assertEqual(again['work']['frame_reuses'], 1)

    def test_effective_host_result_is_authoritative_over_explanatory_flags(self):
        capture = captured()
        capture['display_snapshot']['objects'][0].update(hide_get=False, hide_viewport=False, hide_render=False)
        capture['display_snapshot']['objects'][1].update(hide_get=True, hide_viewport=True, hide_render=True)
        resign(capture)
        prepared = prepare(capture)
        self.assertEqual(prepared.binding['image_scope']['participation_mask'], [False, True, True])
        with tempfile.TemporaryDirectory() as directory:
            result, raster = self.observe(prepared, directory)
        self.assertEqual(raster.call_args.kwargs['object_mask'], (False, True, True))
        self.assertEqual(result['facts']['visibility']['status'], 'observed_samples')

    def test_unselected_face_pixels_do_not_count_as_region_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            result, _ = self.observe(prepare(), directory, 1, 0)
        self.assertEqual(result['facts']['visibility']['selected_surface_pixels'], 0)
        self.assertEqual(result['observation_status'], 'evidence_insufficient')

    def test_missing_invalid_and_unknown_display_keep_measurements(self):
        changes = [lambda value: value.pop('display_snapshot'),
            lambda value: value['display_snapshot'].update(sha256='0' * 64),
            lambda value: value['display_snapshot']['objects'][1].update(instance_id='foreign'),
            lambda value: value['display_snapshot']['objects'].pop(),
            lambda value: value['display_snapshot']['objects'][1].update(visible_get=None),
            lambda value: value['display_snapshot']['view_layer'].update(instance_id=None),
            lambda value: value['display_snapshot'].update(status='unknown', reason='host_read_failed')]
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                capture = captured()
                change(capture)
                if 'display_snapshot' in capture and index != 1:
                    resign(capture)
                state = source_region.display_state(capture)
                self.assertEqual(state['status'], 'unknown')
                self.assertEqual(state, source_region.display_state(copy.deepcopy(capture)))
                prepared = prepare(capture)
                result = source_region.observe_region(prepared, '.', include_image=True)
                self.assertEqual(result['frames'], [])
                self.assertEqual(result['work']['raster_attempts'], 0)
                self.assertEqual(result['status'], 'partial')
                self.assertEqual(result['observation_status'], 'evidence_insufficient')
                self.assertEqual(result['facts']['visibility']['status'], 'unknown')
                measured = source_region.measure_region(prepared, {'name': 'Cube'}, None)
                self.assertEqual(measured['facts']['surface_proximity']['value']['distance_m'], 1)
        self.assertNotEqual(source_region.display_state(captured())['identity'], state['identity'])

    def test_view_layer_and_visible_get_change_identity_with_same_geometry_generation(self):
        original = captured()
        changed = captured((True, True, True))
        layer = captured()
        layer['display_snapshot']['view_layer'].update(instance_id='layer:2')
        resign(layer)
        prepared = [prepare(value) for value in (original, changed, layer)]
        self.assertEqual(prepared[0].region_ref, prepared[1].region_ref)
        self.assertEqual(source_region.validate_region_ref(changed, prepared[0].region_ref),
                         prepared[0].region_ref['ordered_geometry_sha256'])
        self.assertEqual(len({item.binding['geometry_identity'] for item in prepared}), 1)
        self.assertEqual(len({item.binding['camera_identity'] for item in prepared}), 1)
        self.assertEqual(len({item.binding['display_identity'] for item in prepared}), 3)
        with tempfile.TemporaryDirectory() as directory:
            frames = [self.observe(item, Path(directory) / str(index))[0]['frames'][0]
                      for index, item in enumerate(prepared)]
        self.assertEqual(len({frame['image_sha256'] for frame in frames}), 1)
        self.assertEqual(len({frame['frame_identity'] for frame in frames}), 3)
        self.assertEqual(len({frame['image_ref'] for frame in frames}), 3)

    def test_non_json_snapshot_fields_produce_serializable_unknown_results(self):
        for field, bad in [('view_layer', float('nan')), ('view_layer', object()),
                           ('reason', float('nan')), ('objects', object())]:
            with self.subTest(field=field, bad_type=type(bad).__name__):
                capture = captured()
                capture['display_snapshot'][field] = bad
                state = source_region.display_state(capture)
                self.assertEqual(state['status'], 'unknown')
                json.dumps(state, allow_nan=False)
                prepared = prepare(capture)
                result = source_region.observe_region(prepared, '.', include_image=True)
                self.assertEqual(result['observation_status'], 'evidence_insufficient')
                json.dumps(result, allow_nan=False)
                self.assertEqual(source_region.measure_region(prepared, {'name': 'Cube'}, None)['status'], 'complete')
        for field in ('name', 'instance_id'):
            capture = captured()
            capture['display_snapshot']['view_layer'][field] = float('nan')
            state = source_region.display_state(capture)
            self.assertEqual(state['status'], 'unknown')
            self.assertIsNone(state['view_layer'][field])
            json.dumps(state, allow_nan=False)

    def test_malformed_explanatory_flags_are_unknown(self):
        for field in ('hide_get', 'hide_viewport', 'hide_render'):
            with self.subTest(field=field):
                capture = captured()
                capture['display_snapshot']['objects'][1][field] = 'foo'
                resign(capture)
                state = source_region.display_state(capture)
                self.assertEqual(state['status'], 'unknown')
                self.assertEqual(state['reason'], 'current_display_flags_invalid')
                self.assertIsNone(state['objects'][1][field])
                result = source_region.observe_region(prepare(capture), '.', include_image=True)
                self.assertEqual(result['frames'], [])
                json.dumps(result, allow_nan=False)

    def test_repeated_observation_and_no_image_follow_existing_contract(self):
        prepared = prepare()
        with tempfile.TemporaryDirectory() as directory:
            first, _ = self.observe(prepared, directory)
            first['facts']['visibility']['image_scope']['objects'][0]['reason'] = 'caller-mutated'
            again = source_region.observe_region(prepared, directory, include_image=True)
            self.assertEqual(again['frames'], first['frames'])
            self.assertEqual(again['work']['raster_attempts'], 0)
            self.assertEqual(again['work']['frame_reuses'], 1)
            self.assertEqual(again['facts']['visibility']['image_scope']['objects'][0]['reason'],
                             'host_visible_get_false')
            no_image = source_region.observe_region(prepared, directory, include_image=False)
            self.assertEqual(no_image['status'], 'complete')
            self.assertEqual(no_image['observation_status'], 'image_not_requested')
            self.assertEqual(no_image['facts']['visibility']['reason'], 'image_not_requested')
            self.assertEqual(no_image['frames'], [])
        missing = captured()
        missing.pop('display_snapshot')
        self.assertEqual(source_region.observe_region(prepare(missing), '.', include_image=False)['status'], 'complete')

    def test_hidden_object_owner_is_rejected(self):
        prepared = prepare()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'current_display_object_participation_required'):
                self.observe(prepared, directory, 0)

    def test_saved_foreign_and_producer_frames_bind_display_metadata(self):
        prepared = prepare()
        changed = prepare(captured((True, True, True)))
        with tempfile.TemporaryDirectory() as directory:
            producer = adapter(prepared, Path(directory) / 'producer')
            foreign = adapter(prepared, Path(directory) / 'foreign')
            other_display = adapter(changed, Path(directory) / 'changed')
            default = adapter(prepared, Path(directory) / 'default', display=False)
            with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                       return_value=buffers(prepared)):
                frame = producer.render_view('SCENE')
            work = {}
            producer.validate_frame(frame, _diagnostics=work)
            self.assertEqual(work, {'frame_array_decodes': 0, 'fresh_payload_reuses': 1})
            saved = {key: value for key, value in frame.items() if key != 'buffers'}
            for consumer, supplied in [(producer, saved), (foreign, frame), (producer, copy.deepcopy(frame))]:
                work = {}
                consumer.validate_frame(supplied, _diagnostics=work)
                self.assertEqual(work, {'frame_array_decodes': 1, 'fresh_payload_reuses': 0})
            for consumer in (other_display, default):
                with self.assertRaisesRegex(ValueError, 'current_display_frame_binding_required'):
                    consumer.validate_frame(saved)
            relabelled = copy.deepcopy(saved)
            relabelled.update(display_identity=changed.binding['display_identity'],
                image_scope=changed.binding['image_scope'],
                image_scope_identity=source_region.fingerprint(changed.binding['image_scope']))
            with self.assertRaisesRegex(ValueError, 'saved_display_mapping_mismatch'):
                other_display.validate_frame(relabelled)
            for name, original in list(producer._display_arrays.items()):
                with self.subTest(array=name):
                    changed_array = original.copy()
                    changed_array.flat[0] = not bool(changed_array.flat[0]) if name == 'display_object_mask' else 'forged'
                    producer._display_arrays[name] = changed_array
                    with self.assertRaisesRegex(ValueError, 'saved_display_mapping_mismatch'):
                        producer.validate_frame(frame)
                    producer._display_arrays[name] = original

    def test_default_scene_adapter_uses_all_objects_without_display_metadata(self):
        prepared = prepare()
        with tempfile.TemporaryDirectory() as directory:
            images = adapter(prepared, directory, display=False)
            with patch('human_eye_plugin.active_observation_images.rasterize_attention',
                       return_value=buffers(prepared, 0)) as raster:
                frame = images.render_view('SCENE')
            self.assertNotIn('object_mask', raster.call_args.kwargs)
            self.assertNotIn('display_identity', frame)
            self.assertNotIn('image_scope', frame)
            images.validate_frame(frame)


if __name__ == '__main__':
    unittest.main()
