"""Integrity and fallback checks for the source-only fresh NPZ decode removal."""
import copy
import hashlib
import importlib.util
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin.active_observation_images import SceneObservationImages
from human_eye_plugin import source_region

spec = importlib.util.spec_from_file_location('_fresh_payload_helpers', Path(__file__).with_name('test_source_region_core.py'))
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


class FreshPayloadTests(unittest.TestCase):
    def adapter(self, directory, enabled=True):
        prepared = source_region.prepare_region(helpers.no_rectangles(), helpers.query([0], 'A', 'B'))
        cameras = copy.deepcopy(prepared.cameras)
        for pose in cameras['views']:
            pose['size_px'] = [64, 64]
        images = SceneObservationImages(prepared.objects, cameras, directory,
            scene_identity=prepared.binding['geometry_identity'],
            candidate_identity=prepared.binding['camera_identity'],
            _prepared_meshes=prepared.meshes, _reuse_published_payload=enabled, _measure_stages=True)
        with patch('human_eye_plugin.active_observation_images.rasterize_attention', return_value=helpers.buffers(prepared, 64)):
            frame = images.render_view('SCENE')
        return images, frame

    def validate(self, images, frame, *, decodes, reuses, error=None):
        diagnostics = {}
        original_load = np.load
        with patch('human_eye_plugin.active_observation_images.np.load', wraps=original_load) as load:
            if error:
                with self.assertRaisesRegex(ValueError, error):
                    images.validate_frame(frame, _diagnostics=diagnostics)
            else:
                images.validate_frame(frame, _diagnostics=diagnostics)
        self.assertEqual(load.call_count, decodes)
        self.assertEqual(diagnostics, {'frame_array_decodes': decodes, 'fresh_payload_reuses': reuses})

    def test_same_published_frame_and_default_decoder(self):
        with tempfile.TemporaryDirectory() as directory:
            enabled, frame = self.adapter(Path(directory) / 'enabled')
            frame.update(host_binding_sha256='host-binding', source_revision='current', image_ref='source-region-image')
            self.validate(enabled, frame, decodes=0, reuses=1)
            self.assertEqual(frame['temporary_encoded_archive_bytes'], frame['compressed_array_file_bytes'])
            payload = frame['stages']['private_encoded_archive']
            self.assertEqual(payload['retained_encoded_payload_bytes'], 0)
            self.assertLessEqual(payload['closed_ns'], frame['stages']['frame_metadata']['closed_ns'])
            disabled, frame = self.adapter(Path(directory) / 'disabled', enabled=False)
            self.validate(disabled, frame, decodes=1, reuses=0)

    def test_disk_replacement_before_first_hash_is_rejected(self):
        original_read = Path.read_bytes
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as directory:
                replaced = []

                def read(path):
                    if path.suffix == '.npz' and not replaced:
                        with np.load(BytesIO(original_read(path)), allow_pickle=False) as archive:
                            changed = {name: archive[name] for name in archive.files}
                        changed['color'][0, 0, 0] ^= 1
                        np.savez_compressed(path, **changed)
                        replaced.append(str(path))
                    return original_read(path)

                if enabled:
                    with patch.object(Path, 'read_bytes', read), self.assertRaisesRegex(ValueError, 'actual_frame_array_bytes_required'):
                        self.adapter(directory, enabled=True)
                else:
                    with patch.object(Path, 'read_bytes', read):
                        images, frame = self.adapter(directory, enabled=False)
                    self.validate(images, frame, decodes=1, reuses=0, error='frame_array_payload_mismatch')
                self.assertEqual(len(replaced), 1)

    def test_foreign_saved_copied_and_changed_references_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            images, frame = self.adapter(Path(directory) / 'producer')
            foreign, _ = self.adapter(Path(directory) / 'foreign')
            self.validate(foreign, frame, decodes=1, reuses=0)
            self.validate(images, copy.deepcopy(frame), decodes=1, reuses=0)
            self.validate(images, {key: value for key, value in frame.items() if key != 'buffers'}, decodes=1, reuses=0)
            original_identity = frame['frame_identity']
            frame['frame_identity'] = 'changed-frame-reference'
            self.validate(images, frame, decodes=1, reuses=0)
            frame['frame_identity'] = original_identity
            for key in ('arrays_path', 'image_path'):
                original = frame[key]
                changed = Path(directory) / ('copied-' + Path(original).name)
                changed.write_bytes(Path(original).read_bytes())
                frame[key] = str(changed)
                self.validate(images, frame, decodes=1, reuses=0)
                frame[key] = original
            original = frame['arrays']['depth']['sha256']
            frame['arrays']['depth']['sha256'] = '0' * 64
            self.validate(images, frame, decodes=1, reuses=0)
            frame['arrays']['depth']['sha256'] = original
            self.validate(images, frame, decodes=0, reuses=1)

    def test_each_current_buffer_is_rehashed_with_dtype_and_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            images, frame = self.adapter(directory)
            for key, original in list(frame['buffers'].items()):
                with self.subTest(buffer=key):
                    changed = original.copy()
                    changed.flat[0] = 0 if key != 'color' else 255
                    frame['buffers'][key] = changed
                    self.validate(images, frame, decodes=1, reuses=0, error='frame_array_payload_mismatch')
                    frame['buffers'][key] = original
            for changed in (frame['buffers']['depth'].astype(np.float32), frame['buffers']['depth'][:32]):
                original = frame['buffers']['depth']
                frame['buffers']['depth'] = changed
                self.validate(images, frame, decodes=1, reuses=0, error='frame_array_payload_mismatch')
                frame['buffers']['depth'] = original

    def test_mapping_and_owner_metadata_arrays_are_rehashed(self):
        with tempfile.TemporaryDirectory() as directory:
            images, frame = self.adapter(directory)
            for group in ('arrays', 'owner_arrays'):
                for key, original in list(images._patch_mapping[group].items()):
                    if not original.size:
                        continue
                    with self.subTest(group=group, key=key):
                        changed = original.copy()
                        changed.flat[0] = int(changed.flat[0]) + 1 if changed.dtype.kind in 'iu' else 'forged'
                        images._patch_mapping[group][key] = changed
                        self.validate(images, frame, decodes=1, reuses=0,
                                      error='saved_patch_mapping_mismatch|saved_owner_mapping_mismatch')
                        images._patch_mapping[group][key] = original

    def test_disk_bytes_and_coordinated_mutation_use_original_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            images, frame = self.adapter(directory)
            for key, reason in [('arrays_path', 'actual_frame_array_bytes_required'),
                                ('image_path', 'actual_PNG_bytes_required')]:
                path = Path(frame[key])
                original = path.read_bytes()
                path.write_bytes(original + b'changed')
                self.validate(images, frame, decodes=0, reuses=int(key == 'image_path'), error=reason)
                path.write_bytes(original)
            with np.load(frame['arrays_path'], allow_pickle=False) as archive:
                stored = {name: archive[name] for name in archive.files}
            stored['depth'][20, 20] = 2
            np.savez_compressed(frame['arrays_path'], **stored)
            frame['arrays_sha256'] = hashlib.sha256(Path(frame['arrays_path']).read_bytes()).hexdigest()
            self.validate(images, frame, decodes=1, reuses=0, error='frame_array_payload_mismatch')
            frame['buffers']['depth'] = stored['depth']
            frame['arrays']['depth']['sha256'] = hashlib.sha256(stored['depth'].tobytes()).hexdigest()
            # The original saved-frame path accepts this coherent depth-only
            # replacement. It must decode it even when every public hash agrees.
            self.validate(images, frame, decodes=1, reuses=0)
