"""Assess discovered ROIs from the six stored full-scene depth/owner images."""

import argparse
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = load('_active_readability_adapter', HERE / 'adapter.py')


def assess():
    started = time.perf_counter_ns()
    coverage = load('_active_discovery_for_readability', BATCH / 'coverage.py')
    scene_path = BATCH / 'inputs/SCENE_GEOMETRY_RATIONAL.json'
    camera_path = BATCH / 'inputs/CAMERAS.json'
    scene, cameras = adapter.read(scene_path), adapter.read(camera_path)
    regions = coverage.discover_regions(scene)
    meshes = adapter.load_meshes(scene)
    scene_identity = coverage.geometry(scene)[2]
    candidate_identity = coverage.fingerprint([{key: pose[key] for key in (
        'name', 'direction_rational', 'view_matrix', 'projection_matrix', 'size_px')} for pose in cameras['views']])
    rows, frames = [], []
    product_rendering = sys.modules['human_eye_plugin.attention_rendering']
    product_raster = sys.modules['human_eye_plugin.attention_raster']
    def forbidden_raster(*args, **kwargs):
        raise AssertionError('readability_must_reuse_actual_stored_full_scene_buffers')
    with patch.object(adapter, 'rasterize_attention', forbidden_raster), \
            patch.object(product_rendering, 'rasterize_attention', forbidden_raster), \
            patch.object(product_raster, 'rasterize_attention', forbidden_raster):
        for pose in cameras['views']:
            before = time.perf_counter_ns()
            metadata = adapter.read(HERE / (pose['name'] + '.json'))
            arrays_path, png_path = HERE / metadata['owner_depth_RGB_arrays'], HERE / metadata['PNG']
            if adapter.digest(arrays_path.read_bytes()) != metadata['arrays_sha256']:
                raise ValueError('stored_buffer_binding_changed')
            if adapter.digest(png_path.read_bytes()) != metadata['PNG_sha256']:
                raise ValueError('stored_image_binding_changed')
            with adapter.np.load(arrays_path, allow_pickle=False) as arrays:
                buffers = {key: arrays[key] for key in ('color', 'depth', 'owners')}
                pixels = adapter.readability_for_rois(meshes, pose, buffers, regions)
            rows.extend(pixels)
            frames.append({'view_name': pose['name'], 'image_path': str(png_path.resolve()),
                'image_sha256': metadata['PNG_sha256'], 'array_sha256': metadata['arrays_sha256'],
                'readable_roi_ids': [row['roi_id'] for row in pixels if row['readable']],
                'elapsed_ns': time.perf_counter_ns() - before, 'raster_calls': 0})
    source_path = Path(inspect.getsourcefile(adapter._readability_evidence))
    return {'schema': 'active-coverage-discovered-ROI-readability-v1',
        'scene_identity': scene_identity, 'candidate_identity': candidate_identity,
        'source_scene_sha256': adapter.digest(scene_path.read_bytes()),
        'source_cameras_sha256': adapter.digest(camera_path.read_bytes()),
        'discovery_source_sha256': adapter.digest((BATCH / 'coverage.py').read_bytes()),
        'pixel_evidence_product_source': str(source_path),
        'pixel_evidence_product_source_sha256': adapter.digest(source_path.read_bytes()),
        'discovered_roi_count': len(regions), 'view_count': len(frames), 'pixel_rows': rows, 'frames': frames,
        'discovered_regions': [{'roi_id': region.roi_id, 'object_index': region.object_index,
                                'display_name': region.object_name} for region in regions],
        'full_scene_raster_calls': 0, 'solo_target_footprint_raster_calls': 0,
        'actual_raster_functions_guarded_against_calls': True,
        'elapsed_ns': time.perf_counter_ns() - started,
        'continuous_geometry_complete': 'computed independently by coverage index; receipt readable IDs can include partial surfaces',
        'model_Blender_API_calls': 0,
        'scope': 'Existing whole-scene PNG and common depth/owner buffers, dynamically discovered regions, fixed 16/4/24RGB thresholds.'}


def receipt_for_view(index, view_name, assessment=None):
    assessment = adapter.read(HERE / 'READABILITY.json') if assessment is None else assessment
    if (index.scene_identity != assessment['scene_identity']
            or index.candidate_identity != assessment['candidate_identity']):
        raise ValueError('stored_image_scene_or_camera_identity_changed')
    if adapter.digest((BATCH / 'inputs/CAMERAS.json').read_bytes()) != assessment['source_cameras_sha256']:
        raise ValueError('frozen_camera_bytes_changed')
    frames = {row['view_name']: row for row in assessment['frames']}
    frame = frames[view_name]
    image_path = Path(frame['image_path'])
    image_sha = adapter.digest(image_path.read_bytes())
    if image_sha != frame['image_sha256']:
        raise ValueError('actual_delivered_image_bytes_changed')
    if not set(frame['readable_roi_ids']).issubset(index.region_ids):
        raise ValueError('image_pixel_region_binding_changed')
    return {'view_name': view_name, 'scene_identity': index.scene_identity,
        'candidate_identity': index.candidate_identity, 'actual_image_delivered': True,
        'image_path': str(image_path), 'image_sha256': image_sha,
        'pixel_evidence_scope': 'actual_common_depth_owner',
        'readable_roi_ids': list(frame['readable_roi_ids'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=HERE / 'READABILITY.json')
    args = parser.parse_args()
    result = assess()
    adapter.save(args.output, result)
    print(json.dumps({'discovered_roi_count': result['discovered_roi_count'], 'pixel_rows': len(result['pixel_rows']),
        'readable_by_view': {row['view_name']: len(row['readable_roi_ids']) for row in result['frames']},
        'new_raster_calls': 0, 'solo_footprint_raster_calls': 0}))
