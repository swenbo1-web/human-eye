"""Replay sealed PNG/NPZ receipts through the installed region task and cache."""

import argparse
import base64
from collections import Counter
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
from zipfile import ZipFile


HISTORICAL = Path('D:/he_m4_cross_scale_brief_entry_001')
HISTORICAL_SHA = '1fa86e8346e08c63fa4f3d98e992d239391da0bc7dcca6ed15b6b5f3ba51635e'
ASSET_SHA = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
DEPENDENCIES = Path('D:/he_anchor_001/venv/Lib/site-packages')


def sha(data):
    return hashlib.sha256(data).hexdigest()


class History:
    def __init__(self):
        self.pins = {}

    def pin(self, path, raw=None):
        path = path.resolve()
        raw = path.read_bytes() if raw is None else raw
        self.pins[path] = {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}
        return raw

    def inputs(self):
        archive_path = HISTORICAL / 'ORIGINAL_RUNTIME.zip'
        assert sha(self.pin(archive_path)) == HISTORICAL_SHA, 'historical run archive changed'
        slot = HISTORICAL / 'slots/P1'
        with ZipFile(archive_path) as archive:
            def checked(path, expected=None):
                path = path.resolve()
                member = path.relative_to(HISTORICAL.resolve()).as_posix()
                saved = self.pin(path)
                assert archive.read(member) == saved, member
                if expected is not None:
                    assert sha(saved) == expected, member
                return saved

            producer = json.loads(checked(slot / 'product_full/call_001/SERVICE_RESULT.json'))
            terminal = json.loads(checked(slot / 'TERMINAL_SOURCE.json'))
            request = json.loads(checked(slot / 'owner/tool_01/PRODUCT_REQUEST.json'))['params']['arguments']
            assert terminal['source']['asset_sha256'] == ASSET_SHA
            assert request['include_image'] is True and request['response_detail'] == 'brief'
            for frame in producer['constructed_frames']:
                checked(Path(frame['image_path']), frame['image_sha256'])
                checked(Path(frame['arrays_path']), frame['arrays_sha256'])
            return producer, terminal, request


def reconstruct_capture(producer, terminal):
    """Rehydrate the public host order with independently saved evaluated arrays."""
    binding = producer['binding']
    native = {row['object_id']: row for row in terminal['objects']}
    assert len(binding['objects']) == len(native) == 21
    meshes = []
    for row in binding['objects']:
        output = native[row['host_id']]
        assert (output['name'], output['instance_id']) == (row['object_name'], row['instance_id'])
        world = output['evaluated']
        meshes.append({'object_id': row['host_id'], 'name': row['object_name'],
                       'vertices': copy.deepcopy(world['vertices_world_m']),
                       'faces': copy.deepcopy(world['triangles'])})
    assert sum(len(mesh['vertices']) for mesh in meshes) == 148
    assert sum(len(mesh['faces']) for mesh in meshes) == 184
    return {'unit': binding['unit'], 'source': binding['source'], 'coordinate_frame': binding['coordinate_frame'],
            'revision': binding['scene_revision'], 'capture_state': binding['capture_state'], 'meshes': meshes,
            'host_identity': {'schema_version': '1.0', 'capture_scope': binding['capture_scope'],
                              'document_epoch': binding['document_epoch'],
                              'object_instances': {row['host_id']: row['instance_id'] for row in binding['objects']}}}


class SavedHost:
    def __init__(self, capture):
        self.capture, self.captures = capture, 0

    def capture_scene(self):
        self.captures += 1
        return copy.deepcopy(self.capture)


def replay_task(producer, capture, arguments, folder, *, baseline):
    from human_eye_plugin.active_observation_images import ActiveObservationImages
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer

    host = SavedHost(capture)
    config = folder / 'live.json'
    config.write_text(json.dumps({'schema_version': '1.0', 'enabled': True,
                                  'project_root': str(folder), 'state_file': 'state.json',
                                  'audit_file': 'audit.jsonl'}), encoding='utf8')
    service = LiveSpatialService(config, host=host)
    server = LiveSpatialMCPServer(service)
    originals = {(frame['candidate_identity'], frame['view_name']): frame
                 for frame in producer['constructed_frames']}
    attempts, product_results = [], []
    original_observe = service.observe

    def replay(images, name):
        key = (images.session.candidate_identity, name)
        assert key in originals, f'unexpected saved scope and view request: {key}'
        frame = originals[key]
        assert frame['scene_identity'] == images.session.scene_identity
        attempts.append((frame['scope_id'], name))
        return copy.deepcopy(frame)

    def observe(*args, **kwargs):
        value = original_observe(*args, **kwargs)
        product_results.append(copy.deepcopy(value))
        return value

    def invoke(index, args):
        response = server.handle_jsonrpc_message({
            'jsonrpc': '2.0', 'id': index, 'method': 'tools/call',
            'params': {'name': 'human_eye_scene_observe',
                       'arguments': {**args, 'session_id': 'current-replay'}}})
        result = response['result']
        assert result['isError'] is False, result
        assert result['content'][0]['type'] == 'text'
        return (json.loads(result['content'][0]['text']),
                [sha(base64.b64decode(block['data'], validate=True)) for block in result['content'][1:]])

    with (patch.object(ActiveObservationImages, 'render_view', replay),
          patch.object(service, 'observe', side_effect=observe),
          patch('human_eye_plugin.active_observation_images.rasterize_attention',
                side_effect=AssertionError('offline replay must not execute a real raster'))):
        cold, png = invoke(1, arguments)
        after_cold = len(attempts)
        hot, hot_png = invoke(2, arguments)
        text, text_png = invoke(3, {**arguments, 'include_image': False})
    cold_value, hot_value, text_value = product_results
    assert cold['binding']['source_binding_sha256'] == producer['binding']['source_binding_sha256']
    assert cold['binding']['geometry_identity'] == producer['binding']['geometry_identity']
    expected = [(row['scope_id'], row['view_name']) for row in producer['constructed_frames']]
    if not baseline:
        expected = [row for row in expected if row != (expected[-1][0], 'SCENE')]
    assert attempts == expected and len(attempts) == after_cold
    assert (cold_value['work']['raster_attempts'], cold_value['work']['raster_completed']) == (after_cold, after_cold)
    assert cold_value['work']['result_cache_hit'] is False
    assert hot_value['work']['result_cache_hit'] is True and hot_value['work']['frame_reuses'] == 3
    assert hot_value['work']['raster_attempts'] == hot_value['work']['index_calls'] == 0
    assert hot_value['generation_work']['raster_attempts'] == after_cold
    assert cold['region_task'] == hot['region_task'] and cold['images'] == hot['images']
    assert png == hot_png == [frame['image_sha256'] for frame in producer['frames']]
    assert not text_png and not text['images']['rows'] and not text_value['constructed_frames']
    assert text_value['work']['raster_attempts'] == 0 and not text_value['work']['result_cache_hit']
    assert text['observation_status'] == 'prediction_only' and host.captures == 3
    rows = {row['object_name']: row for row in cold['region_task']['rows']}
    assert rows['M06']['status'] == 'unknown' and rows['M06']['reason'] == 'positive_area_occlusion_all_front_views'
    originals_by_ref = {frame['image_ref']: frame for frame in cold_value['frames']}
    for name, view, pixels, boundary in (('M02', 'SCENE', 50557, 926), ('M09', 'LEFT', 146797, 1530)):
        row = rows[name]
        witness = row['complete_witness']
        frame = originals_by_ref[witness['image_ref']]
        assert row['source_triangle_indices'] == [0, 1] and witness['view_name'] == view
        assert row['status'] == 'covered' and frame['frame_identity'] == witness['frame_identity']
        assert png[witness['native_content_block_index'] - 1] == frame['image_sha256']
        verified = next(item for item in cold['witness_pixels']['rows'] if item[2] == row['roi_id'])
        assert verified[3:5] == [pixels, boundary]
    return {'cold_saved_frames_replayed': after_cold, 'receipt_order': attempts,
            'cold_png_sha256': png, 'same_session_cache_hit': True, 'warm_saved_frames_replayed': 0,
            'no_image_saved_frames_replayed': 0, 'mock_host_captures': host.captures,
            'witnesses': {name: row['complete_witness'] for name, row in rows.items()},
            'm06_reason': rows['M06']['reason']}


def view_controls(producer, capture, folder):
    from human_eye_plugin.active_observation import (
        ActiveObservationSession, CoverageState, build_index_from_parsed, geometry,
        prepare_scene_from_parsed,
    )
    from human_eye_plugin.active_observation_host import scene_from_capture
    from human_eye_plugin.active_observation_images import ActiveObservationImages
    from human_eye_plugin.active_observation_region_task import _local_first_view, _task_next_view
    import numpy as np

    objects, triangles, identity = geometry(scene_from_capture(capture))
    task = {row['object_name']: row for row in producer['facts']['region_task']['rows']}
    scopes = {row['binding'].get('region_source', {}).get('host_id'): row for row in producer['scopes']}
    globals_ = producer['binding']['camera_specification']
    global_session = prepare_scene_from_parsed(objects, triangles, identity, globals_)
    assert global_session.next_view() == 'SCENE'
    assert _task_next_view(global_session, {task['M09']['roi_id']}) == 'SCENE'

    def new_local(name, first='SCENE'):
        row = task[name]
        scope = scopes[row['host_id']]['binding']
        camera = scope['camera_specification']
        region = next(item for item in global_session.regions if item.roi_id == row['roi_id'])
        index = build_index_from_parsed(objects, triangles, identity, (region,), camera)
        assert index.candidate_identity == scope['camera_identity']
        return ActiveObservationSession(objects, triangles, camera, index, CoverageState(index, first_view=first))

    local = new_local('M09', first='LEFT')
    index, roi = local.index, local.regions[0].roi_id
    relevant = {roi}
    assert index.classifications['SCENE'][roi]['status'] == 'positive_area_occlusion'
    assert [view for view in index.view_order if index.view_masks[view]] == ['LEFT', 'BACK']
    assert _local_first_view(index, roi) == _task_next_view(local, relevant) == 'LEFT'
    assert _task_next_view(local, set()) is None
    assert _local_first_view(replace(index, view_masks=dict(reversed(tuple(index.view_masks.items())))), roi) == 'LEFT'
    healthier = new_local('M02').index
    assert _local_first_view(healthier, task['M02']['roi_id']) == 'SCENE'
    for reason in ('back_facing', 'edge_on', 'outside_frustum'):
        classifications = copy.deepcopy(index.classifications)
        classifications['SCENE'][roi]['status'] = reason
        assert _local_first_view(replace(index, classifications=classifications), roi) == 'SCENE'
    fully_blocked = replace(index, view_masks={name: 0 for name in index.view_order},
                            classifications={name: index.classifications['SCENE'] for name in index.view_order})
    assert _local_first_view(fully_blocked, roi) == 'SCENE'

    frames = {frame['view_name']: frame for frame in producer['constructed_frames']
              if frame['candidate_identity'] == index.candidate_identity}
    assert set(frames) == {'LEFT', 'SCENE'}
    images = ActiveObservationImages(local, folder / 'archived-frame-readback')

    def rejects(call, reason, state=local.state):
        before = copy.deepcopy((state.summary(), state.observed_views))
        try:
            call()
        except ValueError as error:
            assert str(error) == reason, (str(error), reason)
        else:
            raise AssertionError('rejected control contributed coverage: ' + reason)
        assert (state.summary(), state.observed_views) == before

    default = new_local('M09')
    default_images = ActiveObservationImages(default, folder / 'default-first-guard')
    rejects(lambda: default_images.observe_frame(frames['LEFT']), 'common_SCENE_observation_required',
            default.state)
    default_feedback = default_images.observe_frame(frames['SCENE'])
    assert default_feedback['update']['new_roi_ids'] == [] and default.state.updates == 1

    rejects(lambda: images.observe_frame(frames['SCENE']), 'planned_first_observation_required')
    rejects(lambda: images.observe_frame({**frames['LEFT'], 'candidate_identity': 'expired-camera'}),
            'current_scene_camera_frame_required')
    rejects(lambda: images.observe_frame({**frames['LEFT'], 'scene_identity': 'expired-scene'}),
            'current_scene_camera_frame_required')
    invalid_arrays = folder / 'bad.npz'
    invalid_arrays.write_bytes(Path(frames['LEFT']['arrays_path']).read_bytes() + b'corrupt')
    rejects(lambda: images.observe_frame({**frames['LEFT'], 'arrays_path': str(invalid_arrays)}),
            'actual_frame_array_bytes_required')
    invalid_png = folder / 'bad.png'
    invalid_png.write_bytes(b'invalid PNG')
    rejects(lambda: images.observe_frame({**frames['LEFT'], 'image_path': str(invalid_png)}), 'actual_PNG_bytes_required')
    rejects(lambda: images.observe_frame({**frames['LEFT'], 'image_path': frames['SCENE']['image_path'],
                                          'image_sha256': frames['SCENE']['image_sha256']}),
            'PNG_RGB_frame_array_binding_required')
    qualified = images.observe_frame(frames['LEFT'])
    qualified_receipt = qualified['receipt']
    pixel = qualified['pixel_rows'][0]
    assert (pixel['visible_surface_pixels'], pixel['contrasting_boundary_pixels']) == (146797, 1530)
    assert pixel['readable'] and qualified['update']['new_roi_ids'] == [roi]
    assert images.observe_frame(frames['LEFT'])['update']['reused'] is True and local.state.updates == 1
    assert _task_next_view(local, relevant) is None
    assert local.state.rebind(replace(index, candidate_identity='expired-camera'))
    assert local.state.first_view == 'SCENE' and local.state.updates == 0
    rejects(lambda: local.state.observe(qualified_receipt), 'actual_bound_image_receipt_required')
    rejects(lambda: local.state.observe({**qualified_receipt, 'candidate_identity': 'expired-camera'}),
            'current_patch_mapping_receipt_required')

    fallback = new_local('M09', first='LEFT')
    synthetic_images = ActiveObservationImages(fallback, folder / 'synthetic-pixel-controls')

    def buffers(width, size=512):
        owner_index = fallback.regions[0].object_index
        triangle_index = sum(len(row[1]) for row in objects[:owner_index]) + fallback.regions[0].triangle_indices[0]
        active = np.zeros((size, size), dtype=np.bool_)
        active[100:100 + width, 100:100 + width] = True
        color = np.full((size, size, 3), 30, dtype=np.uint8)
        color[active] = (180, 190, 205)
        depth = np.where(active, 1., np.inf)
        owners = np.where(active, owner_index, -1).astype(np.int32)
        source = np.where(active, triangle_index, -1).astype(np.int32)
        return color, depth, owners, source

    assert _task_next_view(fallback, relevant) == 'LEFT'
    with patch('human_eye_plugin.active_observation_images.rasterize_attention',
               side_effect=[buffers(3), buffers(8)]) as raster:
        insufficient = synthetic_images.observe_frame(synthetic_images.render_view('LEFT'))
        assert insufficient['pixel_rows'][0]['visible_surface_pixels'] == 9
        assert insufficient['pixel_rows'][0]['readable'] is False and insufficient['update']['new_roi_ids'] == []
        assert _task_next_view(fallback, relevant) == 'BACK'
        sufficient = synthetic_images.observe_frame(synthetic_images.render_view('BACK'))
        assert sufficient['pixel_rows'][0]['visible_surface_pixels'] == 64
        assert sufficient['update']['new_roi_ids'] == [roi] and _task_next_view(fallback, relevant) is None
        assert raster.call_count == 2
    return {'ordered_complete_alternatives': ['LEFT', 'BACK'], 'ordinary_and_global_first': 'SCENE',
            'healthy_first': 'SCENE', 'non_occlusion_and_no_alternative_first': 'SCENE',
            'negative_controls': ['ordinary_unexpected_first', 'unexpected_first', 'stale_camera', 'stale_scene', 'corrupt_NPZ',
                                  'corrupt_PNG', 'other_original_PNG', 'rebound_stale_receipt', 'old_mapping'],
            'archived_left_actual_surface_and_boundary': [146797, 1530],
            'synthetic_pixel_fallback': {'LEFT_surface': 9, 'BACK_surface': 64,
                                         'mock_low_level_raster_calls': 2}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    assert sys.flags.isolated and sys.dont_write_bytecode, 'use the pinned interpreter with -I -B'
    started = time.perf_counter_ns()
    root = args.product_root.resolve()
    sys.path[:0] = [str(root), str(DEPENDENCIES)]
    import human_eye_plugin.active_observation as planner
    import human_eye_plugin.active_observation_region_task as region
    history = History()
    history.pin(Path(__file__))
    for module in (planner, region):
        path = Path(module.__file__).resolve()
        assert path.parent == root / 'human_eye_plugin'
        history.pin(path)
    for filename in ('active_observation_host.py', 'active_observation_images.py', 'live_spatial_mcp.py',
                     'live_service.py', 'read_context.py'):
        history.pin(root / 'human_eye_plugin' / filename)
    producer, terminal, request = history.inputs()
    capture = reconstruct_capture(producer, terminal)
    with tempfile.TemporaryDirectory(prefix='local-view-receipts-') as directory:
        folder = Path(directory)
        replay = replay_task(producer, capture, request, folder, baseline=args.baseline)
        controls = None if args.baseline else view_controls(producer, capture, folder)
    receipt = {'schema': 'm4-cross-scale-local-first-view-offline-controls-v1', 'passed': True,
               'baseline': args.baseline, 'actual_new_rasters': 0, 'models': 0, 'owned_Blender': 0,
               'product_root': str(root), 'raw_png_receipt_replay': replay,
               'local_state_controls': controls, 'elapsed_ns': time.perf_counter_ns() - started,
               'source_pins': list(history.pins.values())}
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(receipt, stream, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print('Offline controls passed', args.output, replay['cold_saved_frames_replayed'])


if __name__ == '__main__':
    main()
