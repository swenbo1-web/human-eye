"""Consume a private visual-region capture without a complete-scene identity."""

from pathlib import Path
import time

import numpy as np

from .active_observation import fingerprint, geometry
from .active_observation_host import scene_from_capture
from .active_observation_images import _meshes_from_objects
from .blender_host import _digest, _observation_target_cameras
from .query_policy import MAX_SOURCE_REGION_TRIANGLES, _source_region_world_box
from .scene_cache import _validate_scene
from .source_region import (
    PreparedSourceRegion, _interval, _object_index, _region_arrays,
    _selective_digest, _selective_number, _selective_string, display_state,
    measure_region, observe_region,
)


CAPTURE_SCOPE = 'source_region_visual_meshes'
TRIANGLE_ID_SCOPE = 'zero-based-retained-source-triangles-in-private-visual-mesh-order'
_CAPTURE_FIELDS = {
    'schema', 'source', 'unit', 'coordinate_frame', 'capture_scope', 'revision',
    'document_epoch', 'capture_state', 'source_frame', 'directory', 'display_snapshot',
    'retained_ordinals', 'meshes', 'source_triangle_indices', 'camera_plan', 'query',
    'host_source_sha256', 'execution_authority', 'work', 'sha256',
}
_DIRECTORY_FIELDS = {
    'object_id', 'name', 'instance_id', 'ordinal', 'world_bounds_m', 'bounds_world_m',
    'vertex_count', 'triangle_count', 'triangle_offset', 'matrix_world',
}


def _require(condition, reason):
    if not condition:
        raise ValueError('source_region_visual_' + reason)


def _numeric_rows(rows, row_count, width):
    return (type(rows) is list and len(rows) == row_count
            and all(type(row) is list and len(row) == width
                    and all(_selective_number(value) for value in row) for row in rows))


def _bounds_valid(tight, outward):
    return (_numeric_rows(tight, 2, 3) and _numeric_rows(outward, 2, 3)
            and all(outer_low <= low <= high <= outer_high
                    for low, high, outer_low, outer_high in zip(*tight, *outward)))


def _validate_source(capture, query, host_sha, check_budget):
    check_budget('source_region_visual_validate_source')
    _require(type(capture) is dict and set(capture) == _CAPTURE_FIELDS
             and capture['schema'] == 'human-eye-source-region-visual-capture-v1'
             and capture['capture_scope'] == CAPTURE_SCOPE and capture['source'] == 'blender'
             and capture['unit'] == 'm' and capture['coordinate_frame'] == 'world'
             and capture['execution_authority'] is False and capture['capture_state'] is None
             and type(capture['work']) is dict and _selective_digest(capture['document_epoch'])
             and _selective_digest(host_sha) and host_sha == capture['host_source_sha256'],
             'capture_schema_or_installed_host_mismatch')
    scope_payload = {key: value for key, value in capture.items() if key not in ('work', 'sha256', 'revision')}
    _require(capture['revision'] == 'source-region-visual:' + _digest([scope_payload]), 'source_revision_mismatch')
    # The list wrapper keeps display metadata inside the host digest.
    unsigned = {key: value for key, value in capture.items() if key != 'sha256'}
    _require(_selective_digest(capture['sha256']) and _digest([unsigned]) == capture['sha256'],
             'capture_digest_mismatch')
    _require(type(query) is dict and set(query) == {'target', 'reference', 'world_box_m'}
             and _digest(query) == _digest(capture['query']), 'capture_query_mismatch')
    box = _source_region_world_box(query['world_box_m'])
    frame = capture['source_frame']
    _require(type(frame) is dict and set(frame) == {
                'frame', 'subframe', 'scale_length', 'view_layer', 'unit_settings'}
             and type(frame['frame']) is int and _selective_number(frame['subframe'])
             and _selective_number(frame['scale_length']) and frame['scale_length'] > 0
             and _selective_string(frame['view_layer']) and type(frame['unit_settings']) is dict
             and set(frame['unit_settings']) == {'system', 'length_unit'}
             and all(type(value) is str for value in frame['unit_settings'].values()),
             'current_source_frame_required')
    return box


def _directory_binding(capture, check_budget):
    directory, retained, meshes = (capture[key] for key in ('directory', 'retained_ordinals', 'meshes'))
    _require(type(directory) is list and 1 <= len(directory) <= 256
             and type(retained) is list and bool(retained)
             and all(type(ordinal) is int and 0 <= ordinal < len(directory) for ordinal in retained)
             and sorted(set(retained)) == retained
             and type(meshes) is list and len(meshes) == len(retained), 'retained_order_required')
    total_vertices, total_triangles = 0, 0
    objects = []
    for ordinal, row in enumerate(directory):
        check_budget('source_region_visual_directory')
        _require(type(row) is dict and set(row) == _DIRECTORY_FIELDS
                 and type(row['ordinal']) is int and row['ordinal'] == ordinal
                 and _selective_string(row['object_id']) and _selective_string(row['instance_id'])
                 and type(row['name']) is str and type(row['vertex_count']) is int
                 and type(row['triangle_count']) is int and type(row['triangle_offset']) is int
                 and row['vertex_count'] >= 3 and row['triangle_count'] > 0
                 and row['triangle_offset'] == total_triangles
                 and _bounds_valid(row['world_bounds_m'], row['bounds_world_m'])
                 and _numeric_rows(row['matrix_world'], 4, 4)
                 and row['matrix_world'][3] == [0., 0., 0., 1.], 'original_directory_row_invalid')
        total_vertices += row['vertex_count']
        total_triangles += row['triangle_count']
        _require(total_vertices <= 500_000 and total_triangles <= 1_000_000, 'whole_scene_geometry_limit')
        objects.append({'object_index': ordinal, 'original_object_ordinal': ordinal,
                        'original_triangle_offset': row['triangle_offset'], 'triangle_count': row['triangle_count'],
                        'host_id': row['object_id'], 'instance_id': row['instance_id'], 'object_name': row['name']})
    _require(all(len({row[key] for row in objects}) == len(objects) for key in ('host_id', 'instance_id')),
             'original_object_identity_required')
    _validate_scene(capture)
    for ordinal, mesh in zip(retained, meshes, strict=True):
        row = directory[ordinal]
        check_budget('source_region_visual_retained_mesh')
        _require(mesh['object_id'] == row['object_id'] and mesh.get('name') == row['name']
                 and len(mesh['vertices']) == row['vertex_count']
                 and len(mesh['faces']) == row['triangle_count'], 'retained_source_mesh_mismatch')
        vertices = np.asarray(mesh['vertices'], dtype=np.float64)
        # Legacy scene normalization canonicalizes signed zero through Fraction.
        actual = np.stack((vertices.min(axis=0), vertices.max(axis=0)))
        expected = np.asarray(row['world_bounds_m'], dtype=np.float64)
        _require(np.array_equal(actual.view(np.uint64), expected.view(np.uint64)), 'retained_tight_bounds_mismatch')
    return directory, retained, objects


def _private_display(capture, original_objects, retained, scope_id):
    current = display_state(capture, {'objects': original_objects})
    frame = capture['source_frame']
    _require(current['status'] == 'captured' and current['view_layer']['instance_id'] == frame['view_layer'],
             'current_display_binding_required')
    objects = [{**current['objects'][ordinal], 'object_index': local}
               for local, ordinal in enumerate(retained)]
    mask = [row['participates'] for row in objects]
    return {**current, 'schema': 'human-eye-source-region-visual-display-v1',
            'scope': 'active_view_layer_retained_visual_source', 'scope_id': scope_id,
            'identity': fingerprint((scope_id, current['identity'])),
            'objects': objects, 'participation_mask': mask,
            'participating_object_indices': [index for index, item in enumerate(mask) if item],
            'excluded_object_indices': [index for index, item in enumerate(mask) if not item]}


def _prepare(capture, query, host_sha, check_budget):
    from .blender_host import _source_region_visual_outside_xy_viewports

    started = time.perf_counter_ns()
    box = _validate_source(capture, query, host_sha, check_budget)
    directory, retained, original = _directory_binding(capture, check_budget)
    target, reference = (_object_index({'objects': original}, query[key]) for key in ('target', 'reference'))
    _require(target != reference and target in retained and reference in retained,
             'target_and_reference_original_sources_required')
    object_index = retained.index(target)
    validation = _interval(started)

    started = time.perf_counter_ns()
    target_mesh = capture['meshes'][object_index]
    vertices = np.asarray(target_mesh['vertices'], dtype=np.float64)
    faces = np.asarray(target_mesh['faces'], dtype=np.int64)
    in_box = np.all((vertices >= box['min']) & (vertices <= box['max']), axis=1)
    selected = np.flatnonzero(in_box[faces].all(axis=1)).tolist()
    _require(0 < len(selected) <= MAX_SOURCE_REGION_TRIANGLES
             and type(capture['source_triangle_indices']) is list
             and all(type(value) is int for value in capture['source_triangle_indices'])
             and selected == capture['source_triangle_indices'], 'current_closed_box_source_selection_mismatch')
    selection = _interval(started)

    started = time.perf_counter_ns()
    parsed, _, _ = geometry(scene_from_capture(capture), include_triangles=False)
    objects = tuple((obj[0], obj[1], (obj[2], original[ordinal]['host_id'], original[ordinal]['instance_id']), obj[3])
                    for obj, ordinal in zip(parsed, retained, strict=True))
    meshes = _meshes_from_objects(objects)
    normalization = _interval(started)

    started = time.perf_counter_ns()
    scope = 'source-region-visual-scope:' + capture['revision'].split(':', 1)[1]
    identity_ref = {
        'schema': 'human-eye-source-region-visual-selection-v1', 'scope_id': scope,
        'document_epoch': capture['document_epoch'], 'source_revision': capture['revision'],
        'world_box_m': box, 'host_id': original[target]['host_id'],
        'instance_id': original[target]['instance_id'], 'original_object_ordinal': target,
        'source_triangle_indices': selected,
    }
    identity_ref['selection_id'] = 'source-region-visual-selection:' + fingerprint(identity_ref)
    region_mesh, source_vertices, mapping, facts = _region_arrays(
        meshes[object_index], tuple(selected), identity_ref['selection_id'],
        original[target]['host_id'], original[target]['instance_id'])
    array_preparation = _interval(started)

    started = time.perf_counter_ns()
    cameras = _observation_target_cameras(
        region_mesh.vertices.tolist(), [row['world_bounds_m'] for row in directory])
    cameras.update(schema='active-coverage-source-region-cameras-v1',
                   scope='source_region_fitted_XY_whole_scene_conservative_depth')
    cameras['margin']['square_fit'] = 'selected source triangle world vertices about one common center'
    _require(_digest(cameras) == _digest(capture['camera_plan']), 'camera_plan_mismatch')
    for ordinal, row in enumerate(directory):
        check_budget('source_region_visual_viewport_scope')
        if ordinal not in retained:
            excluded, _ = _source_region_visual_outside_xy_viewports(row['bounds_world_m'], cameras)
            _require(excluded, 'unproved_viewport_exclusion')
    image_scope = _private_display(capture, original, retained, scope)
    retained_objects = [{**original[ordinal], 'object_index': index} for index, ordinal in enumerate(retained)]
    binding = {
        'schema': 'human-eye-source-region-visual-binding-v1', 'scope_id': scope,
        'capture_scope': CAPTURE_SCOPE, 'capture_sha256': capture['sha256'],
        'host_source_sha256': host_sha, 'document_epoch': capture['document_epoch'],
        'capture_state': None, 'scene_revision': capture['revision'], 'source_frame': capture['source_frame'],
        'unit': 'm', 'coordinate_frame': 'world', 'objects': retained_objects,
        'directory': directory, 'retained_ordinals': retained,
        'triangle_id_scope': TRIANGLE_ID_SCOPE,
        'camera_specification': cameras, 'camera_identity': fingerprint(cameras),
        'geometry_identity': fingerprint((scope, capture['revision'])),
        'display_identity': image_scope['identity'], 'image_scope': image_scope,
    }
    binding['source_binding_sha256'] = fingerprint(binding)
    binding['binding_sha256'] = fingerprint(binding)
    camera = _interval(started)
    check_budget('source_region_visual_prepared')
    return PreparedSourceRegion(binding, identity_ref, objects, meshes, object_index, tuple(selected),
        source_vertices, region_mesh, facts, mapping, cameras,
        {'source_validation': validation, 'world_box_selection': selection, 'geometry_normalization': normalization,
         'region_array_preparation': array_preparation, 'camera_and_scope_validation': camera}, scoped_visual=True)


def observe_scoped_visual_region(capture, query, directory, *, host_sha, check_budget, construction_callback=None):
    """Return an independent visual observation and exact closed-box measurement."""
    prepared = _prepare(capture, query, host_sha, check_budget)
    work = {}
    measurement = measure_region(prepared, query['reference'], None, check_budget, work)
    check_budget('source_region_visual_before_raster')
    # A repeated scope is still a separate request and artifact publication.
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    from tempfile import mkdtemp

    frame_directory = Path(mkdtemp(prefix='scope-', dir=directory))
    value = observe_region(prepared, frame_directory, include_image=True,
                           construction_callback=construction_callback, check_budget=check_budget)
    for frames in (value['frames'], value.get('constructed_frames', ())):
        for frame in frames:
            frame['scope_id'] = prepared.binding['scope_id']
    value['task_result'] = measurement
    value['host_work'] = capture['work']
    value['stages'].update(prepared.preparation_stages, **work['stages'])
    check_budget('source_region_visual_before_publish')
    return value
