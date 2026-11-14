"""Bind one complete host capture to the finite active-observation core."""

from __future__ import annotations

import copy
from pathlib import Path
import time

import numpy as np

from .active_observation import fingerprint, geometry, prepare_scene_from_parsed
from .active_observation_images import (
    ActiveObservationImages,
    SURFACE_COLOR_RGB,
    _meshes_from_objects,
)
from .attention_rendering import _attention_camera


CAMERA_ORDER = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')
CAMERA_DIRECTIONS = {
    'SCENE': (4, -4, 3), 'TOP': (0, 0, 1),
    'LEFT': (-1, 0, 1), 'RIGHT': (1, 0, 1),
    'FRONT': (0, -1, 1), 'BACK': (0, 1, 1),
}
IMAGE_SIZE = 512
MARGIN_PER_SIDE = .05


def _camera_policy():
    return {'order': list(CAMERA_ORDER),
            'directions': {name: list(CAMERA_DIRECTIONS[name]) for name in CAMERA_ORDER},
            'size_px': [IMAGE_SIZE, IMAGE_SIZE], 'margin_per_side': MARGIN_PER_SIDE,
            'projection': 'orthographic', 'scope': 'complete_captured_world_geometry'}


def source_binding(capture, cameras=None, *, geometry_identity=None):
    """Bind capture identity and ordered host instances before result reuse.

    Supplying cameras adds the complete generated specification. The source
    digest and fixed camera policy also identify the cold computation when
    the existing read context looks up a previously completed result.
    """
    if (type(capture) is not dict or capture.get('unit') != 'm'
            or capture.get('coordinate_frame') != 'world' or capture.get('source') != 'blender'
            or type(capture.get('revision')) is not str or not capture['revision']
            or type(capture.get('meshes')) is not list or not capture['meshes']):
        raise ValueError('active_observation_complete_world_capture_required')
    identity = capture.get('host_identity')
    if (type(identity) is not dict or identity.get('schema_version') != '1.0'
            or identity.get('capture_scope') != 'complete_scene_meshes'
            or capture.get('capture_scope', 'complete_scene_meshes') != 'complete_scene_meshes'
            or type(identity.get('document_epoch')) is not str
            or len(identity['document_epoch']) != 64
            or any(value not in '0123456789abcdef' for value in identity['document_epoch'])
            or type(identity.get('object_instances')) is not dict):
        raise ValueError('active_observation_complete_host_identity_required')
    instances = identity['object_instances']
    objects = []
    for index, mesh in enumerate(capture['meshes']):
        if (type(mesh) is not dict or type(mesh.get('object_id')) is not str
                or not mesh['object_id'] or type(mesh.get('name')) is not str):
            raise ValueError('active_observation_host_object_identity_required')
        host_id = mesh['object_id']
        instance = instances.get(host_id)
        if type(instance) is not str or not instance:
            raise ValueError('active_observation_host_instance_required')
        objects.append({'object_index': index, 'host_id': host_id,
                        'object_name': mesh['name'], 'instance_id': instance})
    if (len({row['host_id'] for row in objects}) != len(objects)
            or len({row['instance_id'] for row in objects}) != len(objects)
            or set(instances) != {row['host_id'] for row in objects}):
        raise ValueError('active_observation_host_instance_mapping_required')
    state = capture.get('capture_state')
    if state is not None and (
            type(state) is not dict
            or set(state) != {'instance_id', 'epoch', 'revision', 'selection_key'}
            or type(state['instance_id']) is not str or not state['instance_id']
            or any(type(state[key]) is not int or state[key] < 0 for key in ('epoch', 'revision'))
            or type(state['selection_key']) is not str):
        raise ValueError('active_observation_capture_state_required')
    result = {
        'schema': 'active-observation-host-source-v1',
        'scene_revision': capture['revision'],
        'document_epoch': identity['document_epoch'],
        'capture_scope': identity['capture_scope'],
        'unit': capture['unit'], 'coordinate_frame': capture['coordinate_frame'],
        'source': capture['source'], 'capture_state': copy.deepcopy(state),
        'objects': objects, 'camera_policy': _camera_policy(),
    }
    result['source_binding_sha256'] = fingerprint(result)
    if cameras is not None:
        result['camera_specification'] = copy.deepcopy(cameras)
        result['geometry_identity'] = geometry_identity
        result['camera_identity'] = fingerprint([
            {key: pose[key] for key in ('name', 'direction_rational', 'view_matrix', 'projection_matrix', 'size_px')}
            for pose in cameras['views']])
        result['binding_sha256'] = fingerprint(result)
    return result


def scene_from_capture(capture):
    """Map evaluated world vertices and tessellated faces without recomputing them."""
    return {'objects': [
        {'name': mesh['name'], 'vertices': mesh['vertices'], 'triangles': mesh['faces']}
        for mesh in capture['meshes']
    ]}


def freeze_cameras(meshes):
    """Fit the registered six-view pool to the shared full-scene mesh arrays."""
    vertices = np.concatenate([mesh.vertices for mesh in meshes])
    center = vertices.min(axis=0) * .5 + vertices.max(axis=0) * .5
    poses = []
    for name in CAMERA_ORDER:
        direction = np.asarray(CAMERA_DIRECTIONS[name], dtype=np.float64)
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
        poses.append({
            'name': name, 'projection': 'orthographic', 'size_px': [IMAGE_SIZE, IMAGE_SIZE],
            'direction_rational': list(CAMERA_DIRECTIONS[name]), 'eye': eye.tolist(), 'target': center.tolist(),
            'near': .08, 'far': far, 'span': 2 * half_span,
            'target_to_eye_direction_rational': list(CAMERA_DIRECTIONS[name]), 'target_to_eye_unit': direction.tolist(),
            'eye_to_scene_unit': (-direction).tolist(), 'up_seed': up_seed.tolist(),
            'right_unit': view[0, :3].tolist(), 'up_unit': view[1, :3].tolist(),
            'target_world_m': center.tolist(), 'camera_eye_world_m': eye.tolist(),
            'view_span_m': 2 * half_span, 'half_span_m': half_span, 'near_m': .08, 'far_m': far,
            'view_matrix': view.tolist(), 'projection_matrix': projection.tolist(),
            'm_per_pixel': 2 * half_span / (IMAGE_SIZE - 1),
            'unpadded_projected_bounds_xy_m': [projected.min(axis=0).tolist(), projected.max(axis=0).tolist()],
            'unpadded_symmetric_half_span_m': half_span_unpadded,
            'all_geometry_inside_frustum': bool(inside.all()), 'vertices_checked': len(vertices),
            'min_camera_depth_m': float(depths.min()), 'max_camera_depth_m': float(depths.max()),
            'ndc_bounds': [ndc.min(axis=0).tolist(), ndc.max(axis=0).tolist()],
        })
    return {
        'schema': 'active-coverage-full-scene-cameras-v1', 'directions': list(CAMERA_ORDER),
        'common_center_world_m': center.tolist(), 'views': poses,
        'frustum_boundary': 'Inclusive NDC [-1,1] on all axes; positive camera depth.',
        'basis': 'right=normalize(cross(-target_to_eye,up_seed)); true_up=cross(right,-target_to_eye); view rows right,true_up,target_to_eye.',
        'margin': {'per_side_fraction_of_unpadded_symmetric_span': MARGIN_PER_SIDE,
                   'square_fit': 'max absolute right/up projection about the one common center'},
        'geometry_conversion': 'Source Fraction to nearest binary64 once, retaining full world geometry.',
        'uniform_object_color_rgb': list(SURFACE_COLOR_RGB),
        'raster_depth_ties': 'Strict nearer update; an equal-depth sample retains the earlier supplied surface.',
        'pixel_center_convention': 'NDC maps to (size-1)/2 coordinates; raster samples integer pixel index +0.5.',
        'scope': 'Whole-scene geometric raster cameras; no ROI IDs, visibility matrix or oracle input.',
    }


def _interval(started):
    closed = time.perf_counter_ns()
    return {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}


def _patch_scope_facts(session, binding):
    """Bind the exact partition to complete host objects and source-face counts."""
    partitions = session.index.patch_scope
    if len(partitions) != len(session.objects) or len(binding['objects']) != len(session.objects):
        raise ValueError('active_observation_patch_partition_object_mismatch')
    region_faces = [set() for _ in session.objects]
    region_mapping = []
    for region in session.regions:
        indices = set(region.triangle_indices)
        owned = region_faces[region.object_index]
        if len(indices) != len(region.triangle_indices) or owned & indices:
            raise ValueError('active_observation_patch_triangle_overlap')
        owned.update(indices)
        region_mapping.append({'roi_id': region.roi_id, 'object_index': region.object_index,
                               'triangle_indices': list(region.triangle_indices)})
    support = []
    for index, partition in enumerate(partitions):
        source_count = len(session.objects[index][1])
        supported = set(partition['supported_triangle_indices'])
        rejected = set()
        for component in partition['unsupported_components']:
            indices = set(component['triangle_indices'])
            if (not indices or len(indices) != len(component['triangle_indices'])
                    or rejected & indices or not component['reason']):
                raise ValueError('active_observation_patch_component_mismatch')
            rejected.update(indices)
        if (partition['object_index'] != index or partition['source_triangle_count'] != source_count
                or len(supported) != len(partition['supported_triangle_indices'])
                or supported != region_faces[index]
                or partition['supported_triangle_count'] != len(supported)
                or partition['unsupported_triangle_count'] != len(rejected)
                or supported & rejected or supported | rejected != set(range(source_count))):
            raise ValueError('active_observation_patch_partition_triangle_mismatch')
        status = ('unsupported' if not supported else
                  'partially_supported' if rejected else 'fully_supported')
        row = dict(binding['objects'][index], **copy.deepcopy(partition), support_status=status)
        row['unsupported_components'] = [dict(copy.deepcopy(component), status='unknown')
                                         for component in partition['unsupported_components']]
        support.append(row)
    supported_objects = {region.object_index for region in session.regions}
    return {
        'capture_object_count': len(session.objects),
        'supported_roi_object_count': len(supported_objects),
        'objects_without_supported_roi': [dict(row, status='unknown') for row in binding['objects']
                                          if row['object_index'] not in supported_objects],
        'domain': 'maximal edge-connected exact planar rectangular patches',
        'all_objects_participate_in_occlusion': True,
        'patch_support': {
            'schema': 'active-patch-support-v1',
            'triangle_index_scope': 'zero-based source triangles within each object',
            'all_triangles_participate_in_occlusion': True,
            'objects': support,
            'regions': region_mapping,
        },
    }


def _location_conventions(cameras):
    sizes = [pose['size_px'] for pose in cameras['views']]
    if not sizes or any(size != sizes[0] for size in sizes):
        raise ValueError('active_region_shared_image_size_required')
    return {
        'coordinate_frame': 'world', 'unit': 'm',
        'corner_order': ['center-u-v', 'center+u-v', 'center+u+v', 'center-u+v'],
        'front_direction_normalization': 'maximum absolute component is 1',
        'pixel_origin': 'top-left', 'pixel_index_base': 0, 'pixel_axis_order': ['x', 'y'],
        'image_size_px': list(sizes[0]),
        'visible_pixel_bounds': 'inclusive bounds of actual ROI-owned pixels',
        'visible_pixel_anchor': 'ROI-owned pixel nearest bounds center; row-major ties',
    }


def observe_capture(capture, output_directory, construction_callback=None,
                    check_budget=None, include_image=True):
    """Compute serializable facts and current-host-bound local image references.

    The caller supplies one complete capture and retains this result in its
    existing read context. A callback receives the view name immediately
    before each new raster attempt. Image construction and external receipt
    accounting remain separate from local image validation.
    """
    if type(include_image) is not bool:
        raise ValueError('active_observation_include_image_boolean_required')
    stages, frames, steps = {}, [], []
    work = {'mapping_calls': 0, 'geometry_parse_calls': 0, 'mesh_conversions': 0, 'patch_mapping_calls': 0,
            'camera_calls': 0, 'prepare_calls': 0, 'raster_attempts': 0,
            'raster_completed': 0, 'local_verified_images': 0,
            'PNG_bytes': 0, 'NPZ_bytes': 0, 'array_payload_bytes': 0}
    started = time.perf_counter_ns()
    binding = source_binding(capture)
    stages['source_binding'] = _interval(started)
    try:
        if check_budget is not None:
            check_budget('active_observation_before_prepare')
        started = time.perf_counter_ns()
        work['mapping_calls'] += 1
        scene = scene_from_capture(capture)
        stages['capture_mapping'] = _interval(started)
        started = time.perf_counter_ns()
        work['geometry_parse_calls'] += 1
        objects, triangles, scene_identity = geometry(scene)
        stages['geometry'] = _interval(started)
        started = time.perf_counter_ns()
        work['mesh_conversions'] += 1
        meshes = _meshes_from_objects(objects)
        stages['mesh_arrays'] = _interval(started)
        work.update(capture_object_count=len(objects),
                    captured_vertex_count=sum(len(item[0]) for item in objects),
                    captured_triangle_count=len(triangles),
                    geometry_array_payload_bytes=sum(
                        mesh.vertices.nbytes + mesh.faces.nbytes + mesh.edges.nbytes for mesh in meshes))
        started = time.perf_counter_ns()
        work['camera_calls'] += 1
        cameras = freeze_cameras(meshes)
        stages['cameras'] = _interval(started)
        started = time.perf_counter_ns()
        work['prepare_calls'] += 1
        session = prepare_scene_from_parsed(objects, triangles, scene_identity, cameras, diagnostics=True)
        stages['prepare'] = _interval(started)
        stages['partition'] = copy.deepcopy(session.diagnostics['stages']['discovery'])
        stages['index'] = copy.deepcopy(session.diagnostics['stages']['coverage'])
        if 'world_descriptions' in session.diagnostics['stages']:
            stages['world_descriptions'] = copy.deepcopy(session.diagnostics['stages']['world_descriptions'])
        binding = source_binding(capture, session.cameras, geometry_identity=session.scene_identity)
        if binding['camera_identity'] != session.candidate_identity:
            raise ValueError('active_observation_camera_binding_mismatch')
        output = Path(output_directory).resolve() / binding['binding_sha256']
        images = None
        if include_image and session.regions:
            started = time.perf_counter_ns()
            work['patch_mapping_calls'] += 1
            try:
                images = ActiveObservationImages(
                    session, output, _prepared_meshes=(objects, meshes), _measure_stages=True,
                )
            finally:
                stages['patch_mapping_setup'] = _interval(started)
        while images is not None:
            started = time.perf_counter_ns()
            name = session.next_view()
            stages['select_view_' + str(len(frames) + 1)] = _interval(started)
            if name is None:
                break
            if any(frame['view_name'] == name for frame in frames):
                raise ValueError('active_observation_repeated_view_selection')
            if check_budget is not None:
                check_budget('active_observation_before_raster')
            if construction_callback is not None:
                construction_callback(name)
            work['raster_attempts'] += 1
            started = time.perf_counter_ns()
            frame = images.render_view(name)
            work['raster_completed'] += 1
            work['PNG_bytes'] += frame['PNG_bytes']
            work['NPZ_bytes'] += frame['compressed_array_file_bytes']
            work['array_payload_bytes'] += frame['array_payload_bytes']
            frame['host_binding_sha256'] = binding['binding_sha256']
            frame['source_revision'] = binding['scene_revision']
            frame['image_ref'] = 'active-host-image:' + fingerprint(
                (binding['binding_sha256'], name, frame['image_sha256'], frame['patch_mapping_identity']))
            stages['render_and_publish_' + name] = _interval(started)
            started = time.perf_counter_ns()
            feedback = images.observe_frame(frame)
            stages['feedback_' + name] = _interval(started)
            work['local_verified_images'] += 1
            serialized = {key: value for key, value in frame.items() if key != 'buffers'}
            serialized['feedback_stages'] = feedback['stages']
            frames.append(serialized)
            steps.append({'view_name': name, 'update': feedback['update'], 'summary': feedback['summary']})
        if check_budget is not None:
            check_budget('active_observation_before_result')
        started = time.perf_counter_ns()
        facts = session.short_facts()
        for region in facts['regions']:
            host = binding['objects'][region['object_index']]
            region.update(host_id=host['host_id'], instance_id=host['instance_id'])
        for observation in facts['observations']:
            for row in observation['pixel_rows']:
                host = binding['objects'][row['object_index']]
                row.update(host_id=host['host_id'], object_name=host['object_name'])
        facts['scope'] = _patch_scope_facts(session, binding)
        if session.cameras['views']:
            facts['location_conventions'] = _location_conventions(session.cameras)
        stages['scope_and_facts'] = _interval(started)
        observation_status = ('no_supported_regions' if not session.regions
                              else 'locally_observed' if include_image else 'prediction_only')
        return {
            'status': 'unknown' if not session.regions else 'complete' if include_image else 'predicted',
            'result_kind': 'active_observation', 'observation_status': observation_status,
            'binding': binding, 'facts': facts, 'frames': frames, 'steps': steps,
            'work': work, 'stages': stages, 'read_only': True, 'execution_authority': False,
            'image_delivery': {'local_verified': len(frames), 'mcp_content_constructed': 0,
                               'external_consumer_verified': False},
        }
    except Exception as error:
        error.active_observation_work = copy.deepcopy(work)
        error.active_observation_byte_scope = 'completed frame metadata lower bound on failure'
        error.active_observation_stages = copy.deepcopy(stages)
        raise


__all__ = ['source_binding', 'scene_from_capture', 'freeze_cameras', 'observe_capture']
