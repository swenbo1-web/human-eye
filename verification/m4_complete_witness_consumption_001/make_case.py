"""Generate the single fixed integer-world case without importing the product.

Camera arithmetic reproduces the frozen full-scene fitting specification.
This file does not discover regions, classify visibility or render pixels.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
ORDER = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')
DIRECTIONS = {'SCENE': (4, -4, 3), 'TOP': (0, 0, 1),
              'LEFT': (-1, 0, 1), 'RIGHT': (1, 0, 1),
              'FRONT': (0, -1, 1), 'BACK': (0, 1, 1)}
SIZE = 512
MARGIN = .05


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def publish(path, value):
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    with path.open('xb') as stream:
        stream.write(raw)
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def fixed_scene():
    return {'objects': [
        {'name': 'Panel_A', 'vertices': [[-2, -2, 0], [2, -2, 0], [2, 2, 0], [-2, 2, 0]],
         'triangles': [[0, 1, 2], [0, 2, 3]]},
        {'name': 'Panel_B', 'vertices': [[3, -5, 3], [5, -5, 3], [5, -3, 3], [3, -3, 3]],
         'triangles': [[0, 1, 2], [0, 2, 3]]},
    ]}


def cameras_from_scene(scene):
    arrays = [np.asarray(row['vertices'], dtype=np.float64) for row in scene['objects']]
    vertices = np.concatenate(arrays)
    center = vertices.min(axis=0) * .5 + vertices.max(axis=0) * .5
    poses = []
    for name in ORDER:
        direction = np.asarray(DIRECTIONS[name], dtype=np.float64)
        direction /= np.linalg.norm(direction)
        up_seed = np.array([0., 1., 0.]) if abs(direction[2]) > .999999 else np.array([0., 0., 1.])
        right = np.cross(-direction, up_seed)
        right /= np.linalg.norm(right)
        up = np.cross(right, -direction)
        projected = (vertices - center) @ np.stack((right, up)).T
        half_unpadded = float(np.abs(projected).max())
        half_span = half_unpadded * (1 + 2 * MARGIN)
        span = 2 * half_span

        front = max(float(((values - center) @ direction).max()) for values in arrays)
        distance = max(.1, front + .1, span)
        eye = center + direction * distance
        forward = center - eye
        forward /= float(np.linalg.norm(forward))
        camera_right = np.cross(forward, up_seed)
        camera_right /= np.linalg.norm(camera_right)
        camera_up = np.cross(camera_right, forward)
        view = np.eye(4)
        view[:3, :3] = np.array([camera_right, camera_up, -forward])
        view[:3, 3] = -view[:3, :3] @ eye
        far = max(.081, max(float((-values @ view[2, :3] - view[2, 3]).max())
                             for values in arrays) + max(span, .01))
        projection = np.zeros((4, 4))
        projection[0, 0] = projection[1, 1] = 1 / half_span
        projection[2, 2] = -2 / (far - .08)
        projection[2, 3] = -(far + .08) / (far - .08)
        projection[3, 3] = 1
        camera = vertices @ view[:3, :3].T + view[:3, 3]
        ndc = camera @ projection[:3, :3].T + projection[:3, 3]
        depths = -camera[:, 2]
        inside = np.all((ndc >= -1) & (ndc <= 1), axis=1)
        assert bool(inside.all()) and bool((depths > 0).all()), 'full_scene_frustum'
        poses.append({
            'name': name, 'projection': 'orthographic', 'size_px': [SIZE, SIZE],
            'direction_rational': list(DIRECTIONS[name]), 'eye': eye.tolist(), 'target': center.tolist(),
            'near': .08, 'far': far, 'span': span,
            'target_to_eye_direction_rational': list(DIRECTIONS[name]), 'target_to_eye_unit': direction.tolist(),
            'eye_to_scene_unit': (-direction).tolist(), 'up_seed': up_seed.tolist(),
            'right_unit': view[0, :3].tolist(), 'up_unit': view[1, :3].tolist(),
            'target_world_m': center.tolist(), 'camera_eye_world_m': eye.tolist(),
            'view_span_m': span, 'half_span_m': half_span, 'near_m': .08, 'far_m': far,
            'view_matrix': view.tolist(), 'projection_matrix': projection.tolist(),
            'm_per_pixel': span / (SIZE - 1),
            'unpadded_projected_bounds_xy_m': [projected.min(axis=0).tolist(), projected.max(axis=0).tolist()],
            'unpadded_symmetric_half_span_m': half_unpadded,
            'all_geometry_inside_frustum': bool(inside.all()), 'vertices_checked': len(vertices),
            'min_camera_depth_m': float(depths.min()), 'max_camera_depth_m': float(depths.max()),
            'ndc_bounds': [ndc.min(axis=0).tolist(), ndc.max(axis=0).tolist()],
        })
    return {
        'schema': 'active-coverage-full-scene-cameras-v1', 'directions': list(ORDER),
        'common_center_world_m': center.tolist(), 'views': poses,
        'frustum_boundary': 'Inclusive NDC [-1,1] on all axes; positive camera depth.',
        'basis': 'right=normalize(cross(-target_to_eye,up_seed)); true_up=cross(right,-target_to_eye); view rows right,true_up,target_to_eye.',
        'margin': {'per_side_fraction_of_unpadded_symmetric_span': MARGIN,
                   'square_fit': 'max absolute right/up projection about the one common center'},
        'geometry_conversion': 'Source Fraction to nearest binary64 once, retaining full world geometry.',
        'uniform_object_color_rgb': [180, 190, 205],
        'raster_depth_ties': 'Strict nearer update; an equal-depth sample retains the earlier supplied surface.',
        'pixel_center_convention': 'NDC maps to (size-1)/2 coordinates; raster samples integer pixel index +0.5.',
        'scope': 'Whole-scene geometric raster cameras; no ROI IDs, visibility matrix or oracle input.',
    }


def synthetic_capture(scene):
    scene_digest = digest(scene)
    meshes, instances = [], {}
    for index, row in enumerate(scene['objects']):
        object_id = 'blender:' + digest(['complete-witness-consumption-001', row['name']])
        instances[object_id] = 'synthetic-instance-' + str(index + 1)
        edges = sorted({tuple(sorted((face[index], face[(index + 1) % 3])))
                        for face in row['triangles'] for index in range(3)})
        meshes.append({
            'object_id': object_id, 'name': row['name'], 'mark_label': '#B' + str(index + 1).zfill(4),
            'vertices': row['vertices'], 'faces': row['triangles'], 'edges': [list(edge) for edge in edges],
            'color_rgb': [180, 190, 205], 'local_axes': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
            'axes_source': 'host', 'axes_confidence': 'explicit',
            'axes_reason': 'synthetic_world_axes', 'is_focal_target': False,
            'pivot_world': np.asarray(row['vertices'], dtype=np.float64).mean(axis=0).tolist(),
        })
    return {
        'source': 'blender', 'unit': 'm', 'coordinate_frame': 'world',
        'revision': 'synthetic-capture-replay:' + scene_digest,
        'capture_state': {'instance_id': digest(['synthetic-capture', scene_digest]),
                          'epoch': 1, 'revision': 1, 'selection_key': digest([])},
        'host_identity': {'schema_version': '1.0', 'capture_scope': 'complete_scene_meshes',
                          'document_epoch': digest(['synthetic-document', scene_digest]),
                          'object_instances': instances},
        'host_execution': {'schema_version': '1.0', 'operation': 'rigid_transform',
                           'scope': 'independent_static_rigid_meshes', 'supported': True, 'reasons': []},
        'replay_provenance': {'schema': 'synthetic-complete-world-capture-v1',
                              'origin': 'deterministic_integer_world_mesh_fixture',
                              'actual_Blender_calls': 0,
                              'source_field_scope': 'Existing host schema compatibility for a synthetic replay.'},
        'meshes': meshes,
    }


def main():
    output = HERE / 'inputs'
    output.mkdir(parents=True, exist_ok=True)
    scene = fixed_scene()
    cameras = cameras_from_scene(scene)
    capture = synthetic_capture(scene)
    assert [{'name': row['name'], 'vertices': row['vertices'], 'triangles': row['faces']}
            for row in capture['meshes']] == scene['objects']
    for pose in cameras['views']:
        assert pose['size_px'] == [512, 512] and pose['all_geometry_inside_frustum']
    files = [publish(output / 'SCENE_GEOMETRY_RATIONAL.json', scene),
             publish(output / 'CAMERAS.json', cameras),
             publish(output / 'CAPTURE_REPLAY.json', capture)]
    registration = {'schema': 'complete-witness-case-inputs-v1', 'single_case': True,
        'generator_path': str(Path(__file__).resolve()), 'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'python_executable': sys.executable, 'numpy_version': np.__version__,
        'objects': len(scene['objects']), 'vertices': sum(len(row['vertices']) for row in scene['objects']),
        'source_triangles': sum(len(row['triangles']) for row in scene['objects']),
        'view_names': list(ORDER), 'size_px': [SIZE, SIZE], 'files': files,
        'geometry_numeric_encoding': 'All source positions are exact JSON integers in world metres.',
        'capture_provenance': 'Synthetic capture replay. No live or background Blender process was used.',
        'actual_product_calls': 0, 'actual_raster_calls': 0, 'actual_model_calls': 0, 'actual_Blender_calls': 0}
    publish(output / 'CASE_INPUT_REGISTRATION.json', registration)
    print(json.dumps({'input_files': files, 'objects': 2, 'source_triangles': 4, 'cameras': 6,
                      'actual_product_calls': 0, 'actual_raster_calls': 0, 'actual_model_calls': 0}))


if __name__ == '__main__':
    main()
