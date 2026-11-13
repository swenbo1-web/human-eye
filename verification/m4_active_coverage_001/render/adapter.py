"""Fixed-product orthographic geometry raster adapter for active coverage."""

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = HERE.parents[2]
INSTALL = ROOT / '.human-eye/releases/9.7.2+m4.surface.scan.compact.r1/site-packages'
BUILD = ROOT / 'verification/m4_surface_scan_compact_facts_001/installation/run_01/FIXED_BUILD_INPUTS.json'
PRODUCT_SHA = '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6'
ORDER = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')
SIZE = 512
MARGIN_PER_SIDE = .05
COLOR = (180, 190, 205)
sys.path.insert(0, str(INSTALL))

import numpy as np
import PIL
from PIL import Image
from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.attention_rendering import _attention_camera, _readability_evidence
from human_eye_plugin.attention_raster import rasterize_attention


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf8')


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encoded(value))


def load_meshes(scene):
    meshes = []
    for index, obj in enumerate(scene['objects']):
        vertices = np.asarray([[float(Fraction(value)) for value in point] for point in obj['vertices']], dtype=np.float64)
        faces = np.asarray(obj['triangles'], dtype=np.int32)
        identity = 'geometry:' + digest(encoded({'vertices': obj['vertices'], 'triangles': obj['triangles']}))
        mesh = MeshEntity3D(object_id=identity, mark_label='geometry_' + str(index), name=obj['name'],
            vertices=vertices, faces=faces, edges=np.empty((0, 2), dtype=np.int32), color_rgb=COLOR,
            local_axes=np.eye(3, dtype=np.float64), axes_source='declared_adapter_frame',
            axes_confidence='explicit', axes_reason='world_coordinates_no_transform')
        for value in (mesh.vertices, mesh.faces, mesh.edges):
            value.setflags(write=False)
        meshes.append(mesh)
    if len({mesh.object_id for mesh in meshes}) != len(meshes):
        raise ValueError('geometry_identity_collision_requires_explicit_instance_identity')
    return meshes


def dependency_binding():
    raw = BUILD.read_bytes()
    fixed = json.loads(raw)
    if fixed['source_count'] != 138 or fixed['source_sha256'] != PRODUCT_SHA:
        raise ValueError('fixed_product_identity')
    files = {}
    expected = {row['path']: row['sha256'] for row in fixed['manifest']}
    for relative, wanted in expected.items():
        path = INSTALL / relative
        actual = digest(path.read_bytes())
        if actual != wanted:
            raise ValueError('fixed_install_source_changed:' + relative)
        files[str(path.resolve())] = actual
    loaded = {}
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        if name.startswith('human_eye_plugin') or name.startswith('human_eye_module1_operators') or name == 'human_eye_foveated_renderer':
            path = Path(filename).resolve()
            relative = (name.replace('.', '/') + '/__init__.py' if path.name == '__init__.py'
                        else name.replace('.', '/') + '.py')
            actual = digest(path.read_bytes())
            if expected.get(relative) != actual:
                raise ValueError('loaded_product_module_bytes_changed:' + name)
            loaded[name] = {'path': str(path), 'sha256': actual}
    return {'fixed_commit': fixed['commit'], 'source_count': len(expected), 'source_sha256': PRODUCT_SHA,
        'fixed_build_inputs_sha256': digest(raw), 'installed_sources_sha256': files, 'loaded_product_modules': loaded,
        'numpy_version': np.__version__, 'Pillow_version': PIL.__version__,
        'adapter_sha256': digest(Path(__file__).read_bytes()),
        'native_image_channel': 'Fixed geometry raster RGB, common depth and owner; no material/texture channel.'}


def freeze_cameras(scene, directions):
    if set(directions) != set(ORDER):
        raise ValueError('six_registered_direction_order')
    meshes = load_meshes(scene)
    vertices = np.concatenate([mesh.vertices for mesh in meshes])
    center = vertices.min(axis=0) * .5 + vertices.max(axis=0) * .5
    poses = []
    for name in ORDER:
        direction = np.asarray(directions[name], dtype=np.float64)
        direction /= np.linalg.norm(direction)
        up_seed = np.array([0., 1., 0.]) if abs(direction[2]) > .999999 else np.array([0., 0., 1.])
        right = np.cross(-direction, up_seed)
        right /= np.linalg.norm(right)
        up = np.cross(right, -direction)
        projected = (vertices - center) @ np.stack((right, up)).T
        half_span_unpadded = float(np.abs(projected).max())
        half_span = half_span_unpadded * (1 + 2 * MARGIN_PER_SIDE)
        plan = {'target_world_m': center.tolist(), 'direction': direction.tolist(), 'up': up_seed.tolist(),
                'view_span_m': 2 * half_span}
        view, projection, eye, far = _attention_camera(meshes, plan)
        camera = vertices @ view[:3, :3].T + view[:3, 3]
        ndc = camera @ projection[:3, :3].T + projection[:3, 3]
        depths = -camera[:, 2]
        inside = np.all((ndc >= -1) & (ndc <= 1), axis=1)
        if not inside.all() or not (depths > 0).all():
            raise ValueError('complete_scene_frustum_failed:' + name)
        poses.append({'name': name, 'projection': 'orthographic', 'size_px': [SIZE, SIZE],
            'direction_rational': directions[name], 'eye': eye.tolist(), 'target': center.tolist(),
            'near': .08, 'far': far, 'span': 2 * half_span,
            'target_to_eye_direction_rational': directions[name], 'target_to_eye_unit': direction.tolist(),
            'eye_to_scene_unit': (-direction).tolist(), 'up_seed': up_seed.tolist(),
            'right_unit': view[0, :3].tolist(), 'up_unit': view[1, :3].tolist(),
            'target_world_m': center.tolist(), 'camera_eye_world_m': eye.tolist(),
            'view_span_m': 2 * half_span, 'half_span_m': half_span, 'near_m': .08, 'far_m': far,
            'view_matrix': view.tolist(), 'projection_matrix': projection.tolist(),
            'm_per_pixel': 2 * half_span / (SIZE - 1),
            'unpadded_projected_bounds_xy_m': [projected.min(axis=0).tolist(), projected.max(axis=0).tolist()],
            'unpadded_symmetric_half_span_m': half_span_unpadded,
            'all_geometry_inside_frustum': bool(inside.all()), 'vertices_checked': len(vertices),
            'min_camera_depth_m': float(depths.min()), 'max_camera_depth_m': float(depths.max()),
            'ndc_bounds': [ndc.min(axis=0).tolist(), ndc.max(axis=0).tolist()]})
    return {'schema': 'active-coverage-full-scene-cameras-v1', 'directions': list(ORDER),
        'common_center_world_m': center.tolist(), 'views': poses,
        'frustum_boundary': 'Inclusive NDC [-1,1] on all axes; positive camera depth.',
        'basis': 'right=normalize(cross(-target_to_eye,up_seed)); true_up=cross(right,-target_to_eye); view rows right,true_up,target_to_eye.',
        'margin': {'per_side_fraction_of_unpadded_symmetric_span': MARGIN_PER_SIDE,
                   'square_fit': 'max absolute right/up projection about the one common center'},
        'geometry_conversion': 'Source Fraction to nearest binary64 once, retaining full world geometry.',
        'scene_input_sha256': digest(encoded(scene)), 'uniform_object_color_rgb': list(COLOR),
        'raster_depth_ties': 'Strict nearer update; an equal-depth sample retains the earlier supplied surface.',
        'pixel_center_convention': 'NDC maps to (size-1)/2 coordinates; raster samples integer pixel index +0.5.',
        'scope': 'Whole-scene geometric raster cameras; no ROI IDs, visibility matrix or oracle input.'}


def render_one(meshes, pose):
    color, depth, owners = rasterize_attention(meshes, np.asarray(pose['view_matrix']),
        np.asarray(pose['projection_matrix']), SIZE, return_owner=True)
    return {'color': color, 'depth': depth, 'owners': owners}


def readability_for_rois(meshes, pose, buffers, rois):
    view = np.asarray(pose['view_matrix'])
    projection = np.asarray(pose['projection_matrix'])
    direction = np.asarray(pose['target_to_eye_unit'])
    results = []
    for roi in rois:
        index = roi['object_index'] if isinstance(roi, dict) else roi.object_index
        identity = roi['roi_id'] if isinstance(roi, dict) else roi.roi_id
        if type(index) is not int or not 0 <= index < len(meshes):
            raise ValueError('discovered_roi_object_index')
        mesh = meshes[index]
        if len(mesh.vertices) != 4 or len(mesh.faces) != 2:
            raise ValueError('readability_requires_discovered_whole_quad_object')
        face = mesh.vertices[mesh.faces[0]]
        normal = np.cross(face[1] - face[0], face[2] - face[0])
        front = bool(normal @ direction > 0)
        camera = mesh.vertices[:2] @ view[:3, :3].T + view[:3, 3]
        ndc = camera @ projection[:3, :3].T + projection[:3, 3]
        pixels = (ndc[:, :2] + 1) * (SIZE - 1) / 2
        evidence = _readability_evidence(buffers['color'], buffers['owners'], meshes, (mesh.object_id,), pixels)
        results.append({'roi_id': identity, 'object_index': index, 'view': pose['name'],
            'front_facing': front, 'visible_surface_pixels': evidence['visible_surface_pixels'][0],
            'contrasting_boundary_pixels': evidence['contrasting_boundary_pixels'][0],
            'minimum_surface_pixels': 16, 'minimum_boundary_pixels': 4, 'minimum_rgb_boundary_contrast': 24,
            'readable': front and evidence['passed'], 'annotations_count_as_evidence': False,
            'scope': 'Whole discovered quad object, actual common-depth owner pixels and contrasting boundaries.',
            'model_texture_recognition_proven': False})
    return results


def prepare(scene_path, spec_path, cameras_path):
    started = time.perf_counter_ns()
    scene_path, spec_path = Path(scene_path), Path(spec_path)
    scene, specification = read(scene_path), read(spec_path)
    dependencies = dependency_binding()
    cameras = freeze_cameras(scene, specification['directions'])
    cameras['source_geometry_file_sha256'] = digest(scene_path.read_bytes())
    cameras['source_task_spec_file_sha256'] = digest(spec_path.read_bytes())
    save(cameras_path, cameras)
    meshes = load_meshes(scene)
    save(HERE / 'DEPENDENCIES.json', dependencies)
    save(HERE / 'BINARY64_GEOMETRY.json', {'source_sha256': digest(scene_path.read_bytes()), 'objects': [
        {'object_index': index, 'object_id': mesh.object_id, 'name': mesh.name,
         'vertices_binary64_hex': [[float(value).hex() for value in point] for point in mesh.vertices],
         'triangles': mesh.faces.tolist(), 'color_rgb': list(mesh.color_rgb)} for index, mesh in enumerate(meshes)]})
    receipts = []
    for pose in cameras['views']:
        before = time.perf_counter_ns()
        buffers = render_one(meshes, pose)
        raster_closed = time.perf_counter_ns()
        png, arrays = HERE / (pose['name'] + '.png'), HERE / (pose['name'] + '.npz')
        with png.open('xb') as stream:
            Image.fromarray(buffers['color'], mode='RGB').save(stream, format='PNG')
        with arrays.open('xb') as stream:
            np.savez_compressed(stream, **buffers)
        positive = np.isfinite(buffers['depth']) & (buffers['depth'] > 0)
        receipt = {'view': pose['name'], 'all_object_count': len(meshes),
            'triangle_count': sum(len(mesh.faces) for mesh in meshes),
            'raster_calls': 1, 'raster_elapsed_ns': raster_closed - before,
            'render_and_publish_elapsed_ns': time.perf_counter_ns() - before,
            'PNG': png.name, 'PNG_sha256': digest(png.read_bytes()), 'PNG_bytes': png.stat().st_size,
            'owner_depth_RGB_arrays': arrays.name, 'arrays_sha256': digest(arrays.read_bytes()),
            'compressed_array_file_bytes': arrays.stat().st_size,
            'array_payload_bytes': sum(value.nbytes for value in buffers.values()),
            'foreground_pixels': int(positive.sum()), 'background_owner': -1, 'background_depth': 'positive infinity',
            'all_objects_participate_in_same_depth': True, 'annotations': False,
            'pose': pose, 'owner_index_to_object': [{'object_index': index, 'object_id': mesh.object_id,
                                                   'name': mesh.name} for index, mesh in enumerate(meshes)]}
        save(HERE / (pose['name'] + '.json'), receipt)
        receipts.append(receipt)
    result = {'schema': 'active-coverage-six-view-raster-v1', 'render_calls': len(receipts),
        'size_px': [SIZE, SIZE], 'views': receipts,
        'total_elapsed_ns': time.perf_counter_ns() - started,
        'PNG_output_bytes': sum(row['PNG_bytes'] for row in receipts),
        'compressed_array_output_bytes': sum(row['compressed_array_file_bytes'] for row in receipts),
        'array_payload_bytes': sum(row['array_payload_bytes'] for row in receipts),
        'array_payload_scope': 'RGB uint8, camera-depth float64 and owner int32 arrays; not process RSS.',
        'Blender_runs': 0, 'model_calls': 0, 'API_calls': 0,
        'scope': 'Six actual full-scene geometry rasters. Continuous ROI visibility and delivered coverage are separate.'}
    save(HERE / 'RASTER_RESULTS.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', type=Path, required=True)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--cameras', type=Path, default=BATCH / 'inputs/CAMERAS.json')
    args = parser.parse_args()
    result = prepare(args.scene, args.spec, args.cameras)
    print(json.dumps({'render_calls': result['render_calls'], 'PNG_output_bytes': result['PNG_output_bytes'],
                      'compressed_array_output_bytes': result['compressed_array_output_bytes'],
                      'Blender_runs': 0, 'model_calls': 0, 'API_calls': 0}))
