"""Current captured triangle selections, full-scene images and M3 distances."""
from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import time

import numpy as np

from .active_observation import (
    Triangle, bounds, bounds_overlap, camera_planes, canonical_triangle, clip_convex,
    dot, fingerprint, geometry, inside_frustum, partition_regions, plane_distances,
    project, screen_basis, signed_area, triangle_shadow, vector,
)
from .active_observation_host import scene_from_capture, source_binding
from .active_observation_images import SceneObservationImages, _meshes_from_objects
from .attention_rendering import _contrasting_boundaries
from .blender_host import _observation_target_cameras
from .scene_cache import _validate_scene
from .surface_proximity import measure_surface_proximity
from .task_query import _surface_proximity_fact


REGION_REF_SCHEMA = 'human-eye-source-region-ref-v1'
SOURCE_INDEX_DOMAIN = 'zero_based_object_local_current_evaluated_capture_triangle_rows'
_MIN_SURFACE_PIXELS = 16
_MIN_BOUNDARY_PIXELS = 4
_MIN_RGB_CONTRAST = 24


def display_state(capture, binding=None):
    """Validate current host visibility without inferring it from hide flags."""
    binding = source_binding(capture) if binding is None else binding
    snapshot = capture.get('display_snapshot')
    reason = None
    actual_sha = None
    rows = {}
    view_layer = snapshot.get('view_layer') if type(snapshot) is dict else None
    if type(snapshot) is not dict:
        reason = 'current_display_snapshot_missing'
    else:
        try:
            unsigned = {key: value for key, value in snapshot.items() if key != 'sha256'}
            actual_sha = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(',', ':'),
                ensure_ascii=False, allow_nan=False).encode('utf8')).hexdigest()
        except (TypeError, ValueError, OverflowError):
            actual_sha = None
        if (snapshot.get('schema') != 'blender-viewport-display-v1'
                or snapshot.get('scope') != 'active_view_layer'
                or actual_sha is None or snapshot.get('sha256') != actual_sha):
            reason = 'current_display_snapshot_invalid'
        elif (type(view_layer) is not dict or type(view_layer.get('name')) is not str
                or type(view_layer.get('instance_id')) is not str or not view_layer['instance_id']):
            reason = 'current_display_view_layer_unknown'
        elif type(snapshot.get('objects')) is not list:
            reason = 'current_display_object_mapping_invalid'
        else:
            source_rows = snapshot['objects']
            if (any(type(row) is not dict or type(row.get('host_id')) is not str for row in source_rows)
                    or len({row['host_id'] for row in source_rows}) != len(source_rows)):
                reason = 'current_display_object_mapping_invalid'
            else:
                rows = {row['host_id']: row for row in source_rows}
                if (set(rows) != {row['host_id'] for row in binding['objects']}
                        or any(rows[row['host_id']].get('instance_id') != row['instance_id']
                               for row in binding['objects'])):
                    reason = 'current_display_object_mapping_invalid'
                elif any(type(row.get('visible_get')) is not bool for row in source_rows):
                    reason = 'current_display_visibility_unknown'
                elif any(row.get(key) is not None and type(row[key]) is not bool
                         for row in source_rows for key in ('hide_get', 'hide_viewport', 'hide_render')):
                    reason = 'current_display_flags_invalid'
                elif snapshot.get('status') != 'captured':
                    reason = 'current_display_visibility_unknown'
    captured = reason is None
    identity = snapshot['sha256'] if captured else fingerprint({
        'schema': 'source-region-unknown-display-v1', 'reason': reason,
        'snapshot_sha256': actual_sha,
        'objects': [(row['host_id'], row['instance_id']) for row in binding['objects']]})
    objects = []
    for row in binding['objects']:
        current = rows.get(row['host_id'], {})
        participates = current['visible_get'] if captured else None
        objects.append({**copy.deepcopy(row), 'participates': participates,
            'reason': ('host_visible_get_true' if participates else 'host_visible_get_false') if captured else reason,
            **{key: current.get(key) if type(current.get(key)) is bool else None
               for key in ('visible_get', 'hide_get', 'hide_viewport', 'hide_render')}})
    result = {'schema': 'human-eye-source-region-display-v1',
        'status': 'captured' if captured else 'unknown', 'identity': identity,
        'scope': 'active_view_layer_effective_viewport',
        'view_layer': ({key: view_layer.get(key) if type(view_layer.get(key)) is str else None
                        for key in ('name', 'instance_id')} if type(view_layer) is dict else None),
        'participation_source': 'blender.visible_get(view_layer=captured_active_view_layer)',
        'hide_flag_scope': {'hide_get': 'captured_view_layer', 'hide_viewport': 'object_viewport',
                            'hide_render': 'object_render'},
        'participation_mask': [row['participates'] for row in objects], 'objects': objects,
        'participating_object_indices': [row['object_index'] for row in objects if row['participates'] is True],
        'excluded_object_indices': [row['object_index'] for row in objects if row['participates'] is False],
        'snapshot_sha256': snapshot['sha256'] if captured else None}
    if reason is not None:
        result['reason'] = reason
        if type(snapshot) is dict:
            result['host_status'] = snapshot.get('status') if type(snapshot.get('status')) is str else None
            result['host_reason'] = snapshot.get('reason') if type(snapshot.get('reason')) is str else None
    return result


def _checkpoint(stage):
    pass


def _interval(started):
    closed = time.perf_counter_ns()
    return {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}


def _ordered_geometry(capture, binding):
    return fingerprint([
        {'host_id': row['host_id'], 'instance_id': row['instance_id'],
         'vertices': mesh['vertices'], 'faces': mesh['faces']}
        for row, mesh in zip(binding['objects'], capture['meshes'])])


def ordered_geometry_identity(capture, binding):
    """Hash complete ordered source arrays once per fresh service capture."""
    return _ordered_geometry(capture, binding)


def _generation(binding):
    state = binding['capture_state']
    return None if state is None else {key: state[key] for key in ('instance_id', 'epoch', 'revision')}


def _source_ref(capture, binding, object_index, faces, ordered_sha):
    row = binding['objects'][object_index]
    value = {'schema': REGION_REF_SCHEMA, 'document_epoch': binding['document_epoch'],
             'host_id': row['host_id'], 'instance_id': row['instance_id'],
             'capture_generation': _generation(binding),
             'ordered_geometry_sha256': ordered_sha, 'source_triangle_indices': list(faces)}
    return {**value, 'region_id': 'source-region:' + fingerprint(value)}


def _indices(values, face_count):
    if (type(values) is not list or not values
            or any(type(index) is not int or not 0 <= index < face_count for index in values)
            or len(set(values)) != len(values)):
        raise ValueError('source_region_unique_current_triangle_indices_required')
    return tuple(sorted(values))


def _object_index(binding, selector):
    if (type(selector) is not dict or len(selector) != 1
            or not set(selector) <= {'id', 'name'}
            or any(type(value) is not str or not value for value in selector.values())):
        raise ValueError('source_region_explicit_object_selector_required')
    key = 'host_id' if 'id' in selector else 'object_name'
    value = next(iter(selector.values()))
    matches = [index for index, row in enumerate(binding['objects']) if row[key] == value]
    if len(matches) != 1:
        raise ValueError('object_not_found' if not matches else 'object_name_ambiguous')
    return matches[0]


def validate_region_ref(capture, region_ref, check_budget=_checkpoint, *, _binding=None,
                        _ordered_geometry_sha256=None):
    """Validate a self-contained reference against the complete fresh capture."""
    check_budget('source_region_validate_reference')
    keys = {'schema', 'region_id', 'document_epoch', 'host_id', 'instance_id',
            'capture_generation', 'ordered_geometry_sha256', 'source_triangle_indices'}
    if type(region_ref) is not dict or set(region_ref) != keys or region_ref.get('schema') != REGION_REF_SCHEMA:
        raise ValueError('source_region_ref_schema_invalid')
    unsigned = {key: value for key, value in region_ref.items() if key != 'region_id'}
    if region_ref['region_id'] != 'source-region:' + fingerprint(unsigned):
        raise ValueError('source_region_ref_identity_mismatch')
    binding = source_binding(capture) if _binding is None else _binding
    if region_ref['document_epoch'] != binding['document_epoch']:
        raise ValueError('source_region_ref_document_epoch_changed')
    matches = [index for index, row in enumerate(binding['objects']) if row['host_id'] == region_ref['host_id']]
    if not matches:
        raise ValueError('source_region_ref_object_missing')
    object_index = matches[0]
    if binding['objects'][object_index]['instance_id'] != region_ref['instance_id']:
        raise ValueError('source_region_ref_object_instance_changed')
    if region_ref['capture_generation'] != _generation(binding):
        raise ValueError('source_region_ref_capture_generation_changed')
    ordered_sha = (_ordered_geometry(capture, binding) if _ordered_geometry_sha256 is None
                   else _ordered_geometry_sha256)
    if region_ref['ordered_geometry_sha256'] != ordered_sha:
        raise ValueError('source_region_ref_ordered_geometry_changed')
    faces = _indices(region_ref['source_triangle_indices'], len(capture['meshes'][object_index]['faces']))
    if list(faces) != region_ref['source_triangle_indices']:
        raise ValueError('source_region_ref_canonical_triangle_order_required')
    check_budget('source_region_reference_validated')
    return ordered_sha


@dataclass
class PreparedSourceRegion:
    binding: dict
    region_ref: dict
    objects: tuple
    meshes: tuple
    object_index: int
    source_triangle_indices: tuple
    source_vertex_indices: tuple
    region_mesh: object
    region_facts: dict
    source_mapping: dict
    cameras: dict
    preparation_stages: dict
    images: object = None
    observation: dict | None = None


def prepare_region(capture, query, check_budget=_checkpoint, *, _binding=None,
                   _validated_region_ref=False, _ordered_geometry_sha256=None):
    """Prepare a complete capture once, retaining a compact selected submesh."""
    started = time.perf_counter_ns()
    check_budget('source_region_prepare_source')
    binding = source_binding(capture) if _binding is None else _binding
    if binding['capture_scope'] != 'complete_scene_meshes':
        raise ValueError('source_region_complete_scene_required')
    if 'region_ref' in query:
        ordered_sha = (query['region_ref']['ordered_geometry_sha256'] if _validated_region_ref
                       else validate_region_ref(capture, query['region_ref'], check_budget, _binding=binding,
                                                _ordered_geometry_sha256=_ordered_geometry_sha256))
        object_index = _object_index(binding, {'id': query['region_ref']['host_id']})
        faces = tuple(query['region_ref']['source_triangle_indices'])
    else:
        ordered_sha = (_ordered_geometry(capture, binding) if _ordered_geometry_sha256 is None
                       else _ordered_geometry_sha256)
        region = query['region']
        object_index = _object_index(binding, region['object'])
        faces = _indices(region['source_triangle_indices'], len(capture['meshes'][object_index]['faces']))
    region_ref = _source_ref(capture, binding, object_index, faces, ordered_sha)
    source_stage = _interval(started)
    started = time.perf_counter_ns()
    _validate_scene(capture)
    parsed, _, scene_identity = geometry(scene_from_capture(capture))
    # Host instances disambiguate geometrically identical scene objects.
    objects = tuple((item[0], item[1], (item[2], row['host_id'], row['instance_id']), item[3])
                    for item, row in zip(parsed, binding['objects']))
    meshes = _meshes_from_objects(objects)
    normalization_stage = _interval(started)
    started = time.perf_counter_ns()
    mesh = meshes[object_index]
    source_faces = mesh.faces[list(faces)]
    vertex_indices = tuple(int(index) for index in np.unique(source_faces))
    reverse_vertices = np.full(len(mesh.vertices), -1, dtype=np.int32)
    reverse_vertices[list(vertex_indices)] = np.arange(len(vertex_indices), dtype=np.int32)
    compact_faces = reverse_vertices[source_faces]
    compact_vertices = mesh.vertices[list(vertex_indices)]
    selected_object = (tuple(map(tuple, compact_vertices)), tuple(map(tuple, compact_faces)),
                       region_ref['region_id'], mesh.name)
    region_mesh = _meshes_from_objects((selected_object,))[0]
    mapping = {'index_domain': SOURCE_INDEX_DOMAIN,
               'submesh_to_source_triangle_indices': list(faces),
               'submesh_to_source_vertex_indices': list(vertex_indices),
               'triangles_source_vertices': source_faces.tolist(),
               'triangles_submesh_vertices': compact_faces.tolist()}
    region_facts = {'host_id': region_ref['host_id'], 'instance_id': region_ref['instance_id'],
                    'object_name': mesh.name, 'index_domain': SOURCE_INDEX_DOMAIN,
                    'source_triangle_indices': list(faces), 'source_vertex_indices': list(vertex_indices),
                    'triangles_source_vertices': source_faces.tolist(),
                    'vertices_world_m': compact_vertices.tolist(),
                    'bbox_min_world_m': compact_vertices.min(axis=0).tolist(),
                    'bbox_max_world_m': compact_vertices.max(axis=0).tolist()}
    mapping_stage = _interval(started)
    started = time.perf_counter_ns()
    world_bounds = [[item.vertices.min(axis=0).tolist(), item.vertices.max(axis=0).tolist()]
                    for item in meshes]
    cameras = _observation_target_cameras(compact_vertices.tolist(), world_bounds)
    cameras.update(schema='active-coverage-source-region-cameras-v1',
                   scope='source_region_fitted_XY_whole_scene_conservative_depth')
    cameras['margin']['square_fit'] = 'selected source triangle world vertices about one common center'
    binding = copy.deepcopy(binding)
    current_display = display_state(capture, binding)
    binding.update(display_identity=current_display['identity'], image_scope=current_display)
    binding['camera_policy'].update(scope='region_fitted_viewport_full_scene_depth',
                                    region_id=region_ref['region_id'],
                                    display_scope=current_display['scope'])
    binding.pop('source_binding_sha256')
    binding['source_binding_sha256'] = fingerprint(binding)
    binding.update(ordered_geometry_sha256=ordered_sha, geometry_identity=scene_identity,
                   camera_specification=cameras, camera_identity=fingerprint(cameras))
    binding['binding_sha256'] = fingerprint(binding)
    camera_stage = _interval(started)
    check_budget('source_region_prepared')
    return PreparedSourceRegion(binding, region_ref, objects, meshes, object_index, faces,
        vertex_indices, region_mesh, region_facts, mapping, cameras,
        {'source_validation': source_stage, 'geometry_normalization': normalization_stage,
         'region_array_preparation': mapping_stage, 'camera_preparation': camera_stage})


def _selected_rectangle(prepared):
    """Require exactly one supported maximal directed rectangle in the source object."""
    try:
        regions, _ = partition_regions(prepared.objects, target_object_index=prepared.object_index)
    except ValueError as error:
        if str(error) != 'coincident_independent_region_identity':
            raise
        return None
    return next((region for region in regions
                 if region.triangle_indices == prepared.source_triangle_indices), None)


def _displayed_front_triangles(prepared, region, check_budget):
    """Retain only displayed, unselected triangles that can block the region plane."""
    selected = set(region.triangle_indices)
    plane = (*region.normal, -dot(region.normal, region.vertices[0]))
    mask = prepared.binding['image_scope']['participation_mask']
    triangles = []
    for object_index, (vertices, faces, _, _) in enumerate(prepared.objects):
        if not mask[object_index]:
            continue
        for triangle_index, row in enumerate(faces):
            check_budget('source_region_occluder_preparation')
            if object_index == region.object_index and triangle_index in selected:
                continue
            points = tuple(vertices[index] for index in row)
            distances = plane_distances(points, plane)
            maximum = max(distances)
            equal_depth = maximum == 0 and min(distances) == 0
            if maximum > 0 or equal_depth:
                triangle = Triangle(object_index, triangle_index, points, canonical_triangle(points))
                triangles.append((triangle, equal_depth))
    return triangles


def _classify_view(region, triangles, pose, check_budget):
    """Use the exact M4 screen/frustum/strict-nearer tests for this one selection."""
    direction = vector(pose['direction_rational'])
    facing = dot(region.normal, direction)
    if facing <= 0:
        return {'status': 'back_facing' if facing < 0 else 'edge_on'}
    planes = camera_planes(pose)
    if not inside_frustum(region.vertices, planes):
        return {'status': 'outside_frustum'}
    basis = screen_basis(direction)
    polygon = project(region.vertices, basis)
    if signed_area(polygon) < 0:
        polygon = tuple(reversed(polygon))
    region_bounds = bounds(polygon)
    tied = None
    for triangle, equal_depth in triangles:
        check_budget('source_region_view_occlusion')
        screen = project(triangle.vertices, basis)
        if not bounds_overlap(region_bounds, bounds(screen)):
            continue
        # Equal-depth overlap lies on the in-frustum region plane. A real
        # raster winner at the tie does not prove that the patch owns it.
        shadow = screen if equal_depth else triangle_shadow(triangle, region, basis, planes, screen)
        if len(shadow) < 3 or not signed_area(shadow):
            continue
        overlap = clip_convex(shadow, polygon)
        if not overlap:
            continue
        area = abs(signed_area(overlap))
        if not area:
            continue
        source = {'object_index': triangle.object_index,
                  'source_triangle_index': triangle.triangle_index,
                  'overlap_area_screen_exact': str(area)}
        if not equal_depth:
            return {'status': 'positive_area_occlusion', 'first_blocker': source}
        if tied is None:
            tied = source
    if tied is not None:
        return {'status': 'equal_depth_ownership_unknown', 'first_tie': tied}
    return {'status': 'complete'}


def _capture_region_frame(prepared, view, geometry_status, image_scope, work, stages,
                          construction_callback, check_budget):
    check_budget('source_region_before_frame')
    started = time.perf_counter_ns()
    if construction_callback is not None:
        construction_callback(view)
    work['raster_attempts'] += 1
    frame = prepared.images.render_view(view)
    work['raster_completed'] += 1
    frame['host_binding_sha256'] = prepared.binding['binding_sha256']
    frame['source_revision'] = prepared.binding['scene_revision']
    frame['image_ref'] = 'source-region-image:' + fingerprint((
        prepared.region_ref['region_id'], frame['frame_identity'], frame['image_sha256']))
    stages['render_and_publish_' + view] = _interval(started)
    check_budget('source_region_after_frame')

    started = time.perf_counter_ns()
    buffers = prepared.images.validate_frame(frame, _diagnostics=work)
    if 'triangle_ids' not in buffers:
        raise ValueError('source_region_actual_triangle_owner_required')
    offset = int(prepared.images._patch_mapping['arrays']['face_patch_offsets'][prepared.object_index])
    selected = np.asarray(prepared.source_triangle_indices, dtype=np.int32) + offset
    mask = np.isin(buffers['triangle_ids'], selected)
    visible = sorted(int(index) - offset for index in np.unique(buffers['triangle_ids'][mask]))
    y, x = np.nonzero(mask)
    samples = len(x)
    visibility = {'status': 'observed_samples', 'view_name': view,
        'visible_source_triangle_indices': visible,
        'unseen_source_triangle_indices': sorted(set(prepared.source_triangle_indices) - set(visible)),
        'selected_surface_pixels': samples,
        'visible_pixel_bounds': [int(x.min()), int(y.min()), int(x.max()), int(y.max())] if samples else None,
        'complete_witness': None, 'visibility_scope': 'actual_frame_source_triangle_samples',
        'unknown': ['complete_surface_visibility'], 'image_ref': frame['image_ref'],
        'frame_identity': frame['frame_identity'], 'image_scope': copy.deepcopy(image_scope),
        'selected_source_triangle_count': len(prepared.source_triangle_indices),
        'selected_object_participates': image_scope['participation_mask'][prepared.object_index]}
    if not samples:
        visibility.update(status='unknown', reason=(
            'selected_region_not_displayed' if not visibility['selected_object_participates']
            else 'selected_region_displayed_without_pixels'))
    if geometry_status is not None:
        visibility['geometry_status'] = geometry_status
    if geometry_status == 'complete':
        # Disjoint selected-region ownership treats neighboring triangles on
        # the same object as outside the selected region, using the original RGB.
        contrast = int(np.count_nonzero(mask & _contrasting_boundaries(buffers['color'], mask)))
        visibility['contrasting_boundary_pixels'] = contrast
        if samples >= _MIN_SURFACE_PIXELS and contrast >= _MIN_BOUNDARY_PIXELS:
            visibility['unknown'] = []
            visibility['complete_witness'] = {
                'view_name': view, 'image_ref': frame['image_ref'], 'frame_identity': frame['frame_identity'],
                'geometry_status': geometry_status, 'selected_surface_pixels': samples,
                'contrasting_boundary_pixels': contrast, 'minimum_surface_pixels': _MIN_SURFACE_PIXELS,
                'minimum_boundary_pixels': _MIN_BOUNDARY_PIXELS,
                'minimum_rgb_boundary_contrast': _MIN_RGB_CONTRAST,
            }
        elif samples:
            visibility['reason'] = 'selected_region_boundary_or_surface_pixels_insufficient'
    stages['frame_validation_and_selected_pixels_' + view] = _interval(started)
    for destination, key in (('PNG_bytes', 'PNG_bytes'), ('NPZ_bytes', 'compressed_array_file_bytes'),
                             ('array_payload_bytes', 'array_payload_bytes')):
        work[destination] += frame[key]
    work['local_verified_images'] += 1
    work['temporary_encoded_archive_bytes'] += frame.get('temporary_encoded_archive_bytes', 0)
    return {key: value for key, value in frame.items() if key != 'buffers'}, visibility


def _observe_displayed_region(prepared, directory, image_scope, work, stages,
                               construction_callback, check_budget):
    check_budget('source_region_before_frame')
    mask = tuple(image_scope['participation_mask'])
    prepared.images = SceneObservationImages(prepared.objects, prepared.cameras, directory,
        scene_identity=prepared.binding['geometry_identity'],
        candidate_identity=prepared.binding['camera_identity'],
        display_identity=prepared.binding['display_identity'],
        object_mask=mask, image_scope=image_scope,
        _prepared_meshes=prepared.meshes, _measure_stages=True, _reuse_published_payload=True)
    started = time.perf_counter_ns()
    region = _selected_rectangle(prepared) if mask[prepared.object_index] else None
    stages['source_region_rectangle_selection'] = _interval(started)
    if region is None:
        frame, visibility = _capture_region_frame(prepared, 'SCENE', None, image_scope, work, stages,
                                                   construction_callback, check_budget)
        stages['frame_validation_and_selected_pixels'] = stages.pop('frame_validation_and_selected_pixels_SCENE')
        return frame, visibility, [], []

    started = time.perf_counter_ns()
    triangles = _displayed_front_triangles(prepared, region, check_budget)
    stages['source_region_occluder_preparation'] = _interval(started)
    attempts, constructed = [], []
    chosen = None
    for pose in prepared.cameras['views']:
        check_budget('source_region_before_view_selection')
        view = pose['name']
        started = time.perf_counter_ns()
        classification = _classify_view(region, triangles, pose, check_budget)
        stages['source_region_view_selection_' + view] = _interval(started)
        geometry_status = classification['status']
        row = {'view_name': view, **classification, 'constructed': False}
        attempts.append(row)
        if geometry_status != 'complete':
            continue
        frame, visibility = _capture_region_frame(prepared, view, geometry_status, image_scope, work, stages,
                                                  construction_callback, check_budget)
        constructed.append(frame)
        row.update(constructed=True, frame_identity=frame['frame_identity'],
                   selected_surface_pixels=visibility['selected_surface_pixels'],
                   contrasting_boundary_pixels=visibility['contrasting_boundary_pixels'])
        if visibility['complete_witness'] is not None:
            return frame, visibility, attempts, constructed
        if chosen is None or visibility['selected_surface_pixels'] > chosen[1]['selected_surface_pixels']:
            chosen = frame, visibility
    if chosen is not None:
        return chosen[0], chosen[1], attempts, constructed
    # Retain the legacy sample only when no registered view can establish
    # complete geometry. It remains a real charged frame, never a witness.
    scene = next(row for row in attempts if row['view_name'] == 'SCENE')
    frame, visibility = _capture_region_frame(prepared, 'SCENE', scene['status'], image_scope, work, stages,
                                              construction_callback, check_budget)
    scene.update(constructed=True, sample_only=True, frame_identity=frame['frame_identity'],
                 selected_surface_pixels=visibility['selected_surface_pixels'])
    return frame, visibility, attempts, [frame]


def observe_region(prepared, directory, *, include_image, construction_callback=None,
                   check_budget=_checkpoint):
    """Observe source samples using the captured view layer's displayed meshes."""
    if type(include_image) is not bool:
        raise ValueError('include_image_must_be_boolean')
    work = {'raster_attempts': 0, 'raster_completed': 0, 'frame_reuses': 0,
            'PNG_bytes': 0, 'NPZ_bytes': 0, 'array_payload_bytes': 0,
            'local_verified_images': 0, 'frame_array_decodes': 0, 'fresh_payload_reuses': 0,
            'temporary_encoded_archive_bytes': 0}
    if include_image and prepared.observation is not None:
        result = copy.deepcopy(prepared.observation)
        work['frame_reuses'] = len(result['frames'])
        result.update(work=work, stages={})
        return result
    frames, stages = [], {}
    visibility = {'status': 'unknown', 'reason': 'image_not_requested',
                  'visible_source_triangle_indices': [],
                  'unseen_source_triangle_indices': list(prepared.source_triangle_indices),
                  'selected_surface_pixels': 0, 'complete_witness': None,
                  'visibility_scope': 'actual_frame_source_triangle_samples'}
    image_scope = prepared.binding['image_scope']
    visibility.update(selected_source_triangle_count=len(prepared.source_triangle_indices),
                      selected_object_participates=image_scope['participation_mask'][prepared.object_index])
    if include_image and image_scope['status'] != 'captured':
        visibility.update(reason=image_scope['reason'], image_scope=copy.deepcopy(image_scope),
                          unknown=['current_viewport_image', 'complete_surface_visibility'])
    attempts, constructed = [], []
    if include_image and image_scope['status'] == 'captured':
        frame, visibility, attempts, constructed = _observe_displayed_region(
            prepared, directory, image_scope, work, stages, construction_callback, check_budget)
        frames.append(frame)
    check_budget('source_region_before_observation_result')
    insufficient = include_image and visibility['status'] == 'unknown'
    result = {'schema': 'human-eye-source-region-observation-v1', 'result_kind': 'source_region',
              'status': 'partial' if insufficient else 'complete',
              'observation_status': ('evidence_insufficient' if insufficient else
                                     'locally_observed' if include_image else 'image_not_requested'),
              'binding': copy.deepcopy(prepared.binding), 'region_ref': copy.deepcopy(prepared.region_ref),
              'facts': {'region': copy.deepcopy(prepared.region_facts), 'visibility': visibility},
              'source_mapping': copy.deepcopy(prepared.source_mapping),
              'frames': frames, 'work': work, 'stages': stages,
              'image_delivery': {'local_verified': len(frames), 'mcp_content_constructed': 0,
                                 'external_consumer_verified': False},
              'read_only': True, 'execution_authority': False}
    if attempts:
        result.update(view_attempts=attempts, constructed_frames=constructed)
    result['generation_work'] = copy.deepcopy(work)
    result['generation_stages'] = copy.deepcopy(stages)
    if include_image:
        prepared.observation = copy.deepcopy(result)
    return result


def _subtract(left, right):
    return tuple(a - b for a, b in zip(left, right))


def _dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def _cross(left, right):
    return (left[1] * right[2] - left[2] * right[1],
            left[2] * right[0] - left[0] * right[2],
            left[0] * right[1] - left[1] * right[0])


def _contains_exact(point, triangle):
    points, normal, squared, _, _ = triangle
    delta = _subtract(point, points[0])
    if not squared:
        if len(points) == 1:
            return point == points[0]
        edge = _subtract(points[1], points[0])
        return (not any(_cross(delta, edge)) and 0 <= _dot(delta, edge) <= _dot(edge, edge))
    if _dot(delta, normal):
        return False
    u = _dot(_cross(_subtract(points[2], points[0]), normal), delta)
    v = _dot(_cross(normal, _subtract(points[1], points[0])), delta)
    return u >= 0 and v >= 0 and u + v <= squared


def _witness_sources(holder, side, triangle_indices, vertex_indices, check_budget):
    points = holder.get('witness_points')
    if points is None:
        return {'status': 'unknown', 'reason': 'exact_surface_witness_unavailable'}
    point = points[side]
    triangles = holder['pair'][4][side]
    memberships = []
    for index, triangle in enumerate(triangles):
        check_budget('source_region_witness_source_membership')
        if _contains_exact(point, triangle):
            memberships.append(index)
    coordinates = holder['coordinates'][side]
    vertices = [int(vertex_indices[index]) for index, value in coordinates.items() if value == point]
    return {'status': 'measured', 'exact_membership': True,
            'source_triangle_indices': [int(triangle_indices[index]) for index in memberships],
            'source_vertex_indices': vertices, 'index_domain': SOURCE_INDEX_DOMAIN}


def measure_region(prepared, reference, cache, check_budget=_checkpoint, diagnostics=None):
    """Run the existing triangle-surface solver on the complete selected union."""
    diagnostics = {} if diagnostics is None else diagnostics
    index = _object_index(prepared.binding, reference)
    row = prepared.binding['objects'][index]
    reference_binding = {'object_id': row['host_id'], 'name': row['object_name'],
                         'instance_id': row['instance_id'], 'object_index': index}
    right = prepared.meshes[index]
    diagnostics.update(surface_pair_count=0, surface_pair_cache_hit=False)
    started = time.perf_counter_ns()

    def compute():
        diagnostics['surface_pair_count'] += 1
        holder, surface_work = {}, {}
        measured = measure_surface_proximity(prepared.region_mesh, right, check_budget,
            diagnostics=surface_work, _prepared_holder=holder)
        diagnostics['surface_work'] = surface_work
        witness = {
            'a': _witness_sources(holder, 0, prepared.source_triangle_indices,
                                   prepared.source_vertex_indices, check_budget),
            'b': _witness_sources(holder, 1, range(len(right.faces)), range(len(right.vertices)), check_budget)}
        diagnostics['source_membership_triangle_tests'] = (
            len(prepared.region_mesh.faces) + len(right.faces) if 'witness_points' in holder else 0)
        return {'surface': measured, 'nearest_witness_source': witness}

    parameters = {'region_ref': prepared.region_ref, 'reference': reference_binding,
                  'source_binding_sha256': prepared.binding['source_binding_sha256'],
                  'unit': 'm', 'coordinate_frame': 'world'}
    if cache is None:
        value = compute()
    else:
        value, diagnostics['surface_pair_cache_hit'] = cache.pair_measurement(
            prepared.region_mesh, right, compute, parameters=parameters,
            algorithm_version='source-region-surface-proximity-v1')
    diagnostics['stages'] = {'surface_measurement_and_mapping': _interval(started)}
    return {'schema': 'human-eye-source-region-measurement-v1', 'status': 'complete',
            'region_ref': copy.deepcopy(prepared.region_ref), 'reference': reference_binding,
            'measurement_scope': 'complete_selected_source_triangle_union_to_reference_triangle_surface',
            'facts': {'surface_proximity': _surface_proximity_fact(value['surface'])},
            'source_mapping': {'region': copy.deepcopy(prepared.source_mapping),
                               'nearest_witness': value['nearest_witness_source']},
            'binding': copy.deepcopy(prepared.binding), 'read_only': True, 'execution_authority': False}


__all__ = ['REGION_REF_SCHEMA', 'SOURCE_INDEX_DOMAIN', 'PreparedSourceRegion',
           'display_state', 'ordered_geometry_identity', 'prepare_region', 'validate_region_ref',
           'observe_region', 'measure_region']
