"""Independent fresh-payload tamper controls using synthetic raster buffers."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), 'D:/he_anchor_001/venv/Lib/site-packages']
import numpy as np
from PIL import Image
from human_eye_plugin import active_observation_images as images
from human_eye_plugin import source_region as core


def pin(path):
    return dict(path=str(path.resolve()), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    path = ROOT / 'verification/m4_m5_source_region_001/core_tests/test_source_region_core.py'
    spec = importlib.util.spec_from_file_location('_independent_payload_review_fixture', path)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    cases = []
    counts = dict(production_attention_raster_calls=0, mocked_raster_calls=0, PIL_new_calls=0,
                  PIL_save_calls=0, np_load_calls=0)
    def profile(frame, event, argument):
        if event != 'call':
            return
        filename, name = frame.f_code.co_filename.replace('\\', '/'), frame.f_code.co_name
        if filename.endswith('/attention_raster.py') and name == 'rasterize_attention':
            counts['production_attention_raster_calls'] += 1
        if filename.endswith('/PIL/Image.py') and name == 'save':
            counts['PIL_save_calls'] += 1
        if filename.endswith('/PIL/Image.py') and name == 'new':
            counts['PIL_new_calls'] += 1
    original_load = np.load
    def check(name, adapter, frame, *, accepted, decodes=None):
        error = None
        with patch.object(images.np, 'load', wraps=original_load) as loaded:
            try:
                adapter.validate_frame(frame)
                actual = True
            except (ValueError, KeyError) as exc:
                actual = False
                error = str(exc)
        counts['np_load_calls'] += loaded.call_count
        row = dict(case=name, accepted=actual, np_load_calls=loaded.call_count, error=error,
                   passed=actual == accepted and (decodes is None or loaded.call_count == decodes))
        cases.append(row)
        assert row['passed'], row
    sys.setprofile(profile)
    try:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            prepared = core.prepare_region(fixture.captured(), fixture.query())
            def build(name, reuse):
                adapter = images.SceneObservationImages(prepared.objects, prepared.cameras, directory / name,
                    scene_identity=prepared.binding['geometry_identity'], candidate_identity=prepared.binding['camera_identity'],
                    _prepared_meshes=prepared.meshes, _reuse_published_payload=reuse)
                counts['mocked_raster_calls'] += 1
                with patch.object(images, 'rasterize_attention', return_value=fixture.buffers(prepared, 512)):
                    frame = adapter.render_view('SCENE')
                return adapter, frame
            adapter, frame = build('fresh', True)
            check('same_producer_fresh', adapter, frame, accepted=True, decodes=0)
            check('same_producer_repeat_validation', adapter, frame, accepted=True, decodes=0)
            check('foreign_shallow_dict', adapter, dict(frame), accepted=True, decodes=1)
            check('foreign_deepcopy', adapter, copy.deepcopy(frame), accepted=True, decodes=1)
            check('saved_frame_without_buffers', adapter, {key: value for key, value in frame.items() if key != 'buffers'},
                  accepted=True, decodes=1)
            old, old_frame = build('old_default', False)
            check('default_path_retains_decode', old, old_frame, accepted=True, decodes=1)
            metadata = frame['arrays']['depth']
            old_bytes = metadata['nbytes']
            metadata['nbytes'] += 8
            check('frame_array_metadata_changed_fallback', adapter, frame, accepted=True, decodes=1)
            metadata['nbytes'] = old_bytes
            for key in ('color', 'depth', 'owners', 'triangle_ids', 'patch_owners'):
                values = frame['buffers'][key]
                position = (0, 0, 0) if key == 'color' else (0, 0)
                previous = values[position].copy()
                values.setflags(write=True)
                values[position] = 1 if key in ('color', 'depth') else 0
                values.setflags(write=False)
                check('mutated_buffer_' + key, adapter, frame, accepted=False)
                values.setflags(write=True)
                values[position] = previous
                values.setflags(write=False)
            for key in ('face_patch_ids', 'face_patch_offsets'):
                values = adapter._patch_mapping['arrays'][key]
                previous = values[0].copy()
                values.setflags(write=True)
                values[0] = int(values[0]) + 1
                values.setflags(write=False)
                check('mutated_mapping_' + key, adapter, frame, accepted=False)
                values.setflags(write=True)
                values[0] = previous
                values.setflags(write=False)
            values = adapter._patch_mapping['owner_arrays']['owner_schema']
            previous = values.copy()
            values.setflags(write=True)
            values[...] = 'foreign'
            values.setflags(write=False)
            check('mutated_owner_metadata_array', adapter, frame, accepted=False)
            values.setflags(write=True)
            values[...] = previous
            values.setflags(write=False)
            for key in ('owner_mapping_identity', 'mesh_order_identity', 'candidate_identity'):
                previous = frame[key]
                frame[key] = 'foreign'
                check('mutated_frame_' + key, adapter, frame, accepted=False)
                frame[key] = previous
            for kind, path_key in (('NPZ', 'arrays_path'), ('PNG', 'image_path')):
                saved = Path(frame[path_key]).read_bytes()
                Path(frame[path_key]).write_bytes(saved + b'x')
                check('mutated_persisted_' + kind, adapter, frame, accepted=False)
                Path(frame[path_key]).write_bytes(saved)
            archive = Path(frame['arrays_path'])
            original_archive, original_hash = archive.read_bytes(), frame['arrays_sha256']
            archive.write_bytes(original_archive + b'x')
            frame['arrays_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
            check('rewritten_valid_NPZ_with_updated_caller_hash_falls_back', adapter, frame, accepted=True, decodes=1)
            archive.write_bytes(original_archive)
            frame['arrays_sha256'] = original_hash
            check('restored_same_frame_remains_current', adapter, frame, accepted=True, decodes=0)
            legacy_path = ROOT / 'verification/test_active_observation_images.py'
            legacy_spec = importlib.util.spec_from_file_location('_independent_payload_review_legacy', legacy_path)
            legacy = importlib.util.module_from_spec(legacy_spec)
            legacy_spec.loader.exec_module(legacy)
            session = legacy.prepare_scene(legacy.subdivided_scene(), legacy.camera_pool())
            active = images.ActiveObservationImages(session, directory / 'legacy_active')
            legacy_buffers = legacy.synthetic_buffers()
            counts['mocked_raster_calls'] += 1
            with patch.object(images, 'rasterize_attention', return_value=tuple(legacy_buffers[key]
                    for key in ('color', 'depth', 'owners'))):
                active_frame = active.render_next()
            with patch.object(images.np, 'load', wraps=original_load) as loaded:
                observed = active.observe_frame(active_frame)
            counts['np_load_calls'] += loaded.call_count
            cases.append(dict(case='legacy_Active_observe_frame_entry_retains_decode',
                passed=loaded.call_count == 1 and observed['pixel_rows'][0]['readable'], np_load_calls=loaded.call_count))
            assert cases[-1]['passed'], cases[-1]
            counts['mocked_raster_calls'] += 1
            with patch.object(images, 'rasterize_attention', return_value=fixture.buffers(prepared, 512)):
                actual = core.observe_region(prepared, directory / 'source_entry', include_image=True)
            cases.append(dict(case='source_region_entry_after_delivery_annotations_reuses_fresh_arrays',
                passed=actual['work']['frame_array_decodes'] == 0 and actual['work']['fresh_payload_reuses'] == 1,
                work=actual['work']))
            assert cases[-1]['passed'], cases[-1]
            warm = core.observe_region(prepared, directory / 'unused', include_image=True)
            cases.append(dict(case='source_region_warm_observation_keeps_current_frame',
                passed=warm['work']['frame_reuses'] == 1 and warm['work']['raster_attempts'] == 0
                    and warm['frames'] == actual['frames'], work=warm['work']))
            assert cases[-1]['passed'], cases[-1]
    finally:
        sys.setprofile(None)
    result = dict(schema='source-region-independent-source-review-v1', passed=all(row['passed'] for row in cases),
        cases=cases, counts=counts, actual_Blender_processes=0, actual_live_requests=0, paid_model_calls=0,
        source_pins=[pin(Path(module.__file__)) for module in (images, core)],
        fixture_pin=pin(path), checker_pin=pin(Path(__file__)))
    target = Path(__file__).parent / 'SOURCE_REVIEW.json'
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf8')
    print(json.dumps(dict(passed=result['passed'], cases=len(cases), counts=counts)))


if __name__ == '__main__':
    main()
