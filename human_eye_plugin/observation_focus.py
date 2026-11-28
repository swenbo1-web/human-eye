"""Observe a current source triangle or task region with at most one corrective view."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import time

import numpy as np

from .active_observation import cross, fingerprint, subtract, vector
from .active_observation_host import CAMERA_DIRECTIONS
from .active_observation_images import _meshes_from_objects
from .attention_raster import _SPARSE_GRID_SIZE, select_sparse_attention_view
from .blender_host import BlenderHostError, _observation_target_cameras
from .query_policy import MAX_SOURCE_REGION_TRIANGLES, validate_source_region_query
from .source_region import (
    SOURCE_INDEX_DOMAIN, _MIN_SURFACE_PIXELS, _capture_region_frame, _generation, _interval, _object_index,
    _region_image_store, _source_ref, _world_box_source_indices, prepare_region,
)
from .task_query import _surface_pair_measurement


# Limit the additive component value in both full and brief MCP responses.
_FOCUS_COMPONENT_VALUE_BYTES_LIMIT = 1024
_FOCUS_COMPONENT_SCOPE = 'one_target_vertex_connected_component_to_reference_whole_object'
_FOCUS_PROBE_FACE_LIMIT = 16_384
_FOCUS_PROBE_VERTEX_LIMIT = 65_536


def _scaled_cross(points):
    # Independent powers of two preserve direction and keep the area tie-break
    # comparable across very small and very large evaluated world coordinates.
    with np.errstate(over='ignore'):
        edges = points[:, 1:] - points[:, :1]
    overflow = ~np.isfinite(edges).all(axis=(1, 2))
    if overflow.any():
        half = points[overflow] * .5
        edges[overflow] = half[:, 1:] - half[:, :1]
    exponents = np.frexp(np.max(np.abs(edges), axis=2))[1]
    edges = np.ldexp(edges, -exponents[:, :, None])
    return np.cross(edges[:, 0], edges[:, 1]), exponents.sum(axis=1) + 2 * overflow


def select_triangle(mesh, focus, check_budget):
    """Rank oriented world faces. Angles only propose a focus; pixels decide success."""
    faces = mesh['faces']
    explicit = isinstance(focus, dict) and 'source_triangle_index' in focus
    start, end = (focus['source_triangle_index'], focus['source_triangle_index'] + 1) if explicit else (0, len(faces))
    if end > len(faces):
        raise ValueError('focus_source_triangle_out_of_range')
    vertices = None if explicit else np.asarray(mesh['vertices'], dtype=np.float64)
    preferred = None
    if isinstance(focus, dict) and 'normal_world' in focus:
        preferred = np.asarray(focus['normal_world'], dtype=np.float64)
        preferred /= np.linalg.norm(preferred)
    registered = np.array(list(CAMERA_DIRECTIONS.values()), dtype=np.float64)
    registered /= np.linalg.norm(registered, axis=1)[:, None]
    best_key, best = None, None
    # Bound temporary buffers and provide a cancellation point even on dense targets.
    for offset in range(start, end, 1024):
        check_budget('focus_select_faces')
        if explicit:
            points = np.array([[mesh['vertices'][v] for v in faces[offset]]], dtype=np.float64)
        else:
            points = vertices[np.asarray(faces[offset:min(offset + 1024, end)], dtype=np.intp)]
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            normals, exponents = _scaled_cross(points)
            scales = np.max(np.abs(normals), axis=1)
            rows = np.flatnonzero(scales > 0)
            if not rows.size:
                continue
            normals = normals[rows] / scales[rows, None]
            lengths = np.linalg.norm(normals, axis=1)
            normals /= lengths[:, None]
            # A new world direction outranks area. Source order breaks exact ties.
            if preferred is not None:
                score = normals @ preferred
                if score.max() <= 0:
                    continue
            else:
                score = -np.max(normals @ registered.T, axis=1)
            tied = np.flatnonzero(score == score.max())
            # Compare double areas without multiplying a large scale by its length.
            areas = exponents[rows[tied]] + np.log2(scales[rows[tied]]) + np.log2(lengths[tied])
            local = int(np.argmax(areas))
            winner = tied[local]
            source_index = offset + int(rows[winner])
            rank = (float(score[winner]), float(areas[local]), -source_index)
            if best_key is None or rank > best_key:
                best_key, best = rank, (source_index, normals[winner].tolist())
    return best


def _unit_exact_normal(direction):
    scale = max(map(abs, direction))
    if not scale:
        return None
    values = np.asarray([float(x / scale) for x in direction], dtype=np.float64)
    return (values / np.linalg.norm(values)).tolist()


def select_task_region(captured, binding, object_index, task_region, check_budget):
    """Select source rows from the exact closed box or a centroid-to-reference-box tie.

    The reference's complete current evaluated mesh supplies a world AABB.
    Its exact squared distance to each target triangle's centroid sets priority;
    equal distances use source order. An explicit task box fixes membership.
    """
    check_budget('before_task_region_selection')
    reference_index = _object_index(binding, task_region['reference'])
    if object_index == reference_index:
        raise ValueError('focus_task_region_distinct_reference_required')
    mesh = captured['meshes'][object_index]
    ref_mesh = captured['meshes'][reference_index]
    ref_xyz = np.asarray(ref_mesh['vertices'], dtype=np.float64)
    lo, hi = vector(ref_xyz.min(axis=0).tolist()), vector(ref_xyz.max(axis=0).tolist())
    box = task_region.get('world_box_m')
    candidates = range(len(mesh['faces']))
    if box is not None:
        points = np.asarray(mesh['vertices'], dtype=np.float64)
        faces = np.asarray(mesh['faces'], dtype=np.intp)
        candidates = _world_box_source_indices(points, faces, box).tolist()
        if len(candidates) > MAX_SOURCE_REGION_TRIANGLES:
            raise ValueError('focus_task_region_triangle_limit')
    check_budget('after_task_region_candidates')

    minimum = primary = direction = None
    nearest = []
    nearest_count = 0
    for ordinal, index in enumerate(candidates):
        if ordinal % 64 == 0:
            check_budget('focus_task_region_reference_ranking')
        a, b, c = (vector(mesh['vertices'][i]) for i in mesh['faces'][index])
        face_normal = cross(subtract(b, a), subtract(c, a))
        scale = max(map(abs, face_normal))
        if not scale:
            continue
        centroid = ((x + y + z) / 3 for x, y, z in zip(a, b, c))
        distance = sum(max(l - x, x - h, 0) ** 2 for x, l, h in zip(centroid, lo, hi))
        if minimum is None or distance < minimum:
            minimum = distance
            primary = index
            direction = face_normal
            nearest = []
            nearest_count = 0
        if box is None and distance == minimum:
            nearest_count += 1
            if nearest_count <= MAX_SOURCE_REGION_TRIANGLES:
                nearest.append(index)
    if nearest_count > MAX_SOURCE_REGION_TRIANGLES:
        raise ValueError('focus_task_region_triangle_limit')
    check_budget('after_task_region_selection')

    normal = None if direction is None else _unit_exact_normal(direction)
    group = nearest if box is None else candidates
    return {
        'source_triangle_indices': group, 'primary_source_triangle_index': primary,
        'front_normal_world': normal, 'reference': binding['objects'][reference_index],
        'selection_policy': {
            'group': 'minimum_centroid_distance_to_reference_world_aabb' if box is None
                     else 'all_three_vertices_in_world_closed_box',
            'primary': 'minimum_centroid_distance_to_reference_world_aabb_then_source_order',
            'reference_effect': 'group_and_primary' if box is None else 'primary_only',
        },
        'empty_reason': ('no_source_triangles_in_task_world_box' if box is not None and not group
                         else 'no_matching_nondegenerate_source_triangle'),
    }


def _vertex_connected_triangle_rows(faces, seed, check_budget):
    """Walk source vertex indices, with no edge-sharing or coordinate welding requirement."""
    incident = {}
    for index, face in enumerate(faces):
        if index % 128 == 0:
            check_budget('focus_component_adjacency')
        for vertex in face:
            incident.setdefault(vertex, []).append(index)

    visited, pending = {seed}, [seed]
    scanned = 0
    while pending:
        if scanned % 128 == 0:
            check_budget('focus_component_walk')
        row = pending.pop()
        scanned += 1
        for vertex in faces[row]:
            # All source faces incident to this vertex are now reachable.
            for other in incident.pop(vertex, ()):
                if other not in visited:
                    visited.add(other)
                    pending.append(other)
    return sorted(visited)


def _focus_component_value_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8'))


def _nearest_surface_component(captured, binding, object_index, reference, ordered_sha, primary, distance,
                               work, stages, check_budget):
    started = time.perf_counter_ns()
    check_budget('before_focus_component')
    faces = captured['meshes'][object_index]['faces']
    if len(faces) > MAX_SOURCE_REGION_TRIANGLES:
        reason = 'focus_component_triangle_limit'
    else:
        rows = _vertex_connected_triangle_rows(faces, primary, check_budget)
        work.update(focus_component_face_scans=len(faces), focus_component_rows=len(rows))
        component_reference = _source_ref(captured, binding, object_index, rows, ordered_sha)
        # The component contains a witness for the whole target's minimum.
        # Restricting to it keeps that distance with no additional solve.
        component = {'status': 'measured', 'scope': _FOCUS_COMPONENT_SCOPE,
                     'region_ref': component_reference, 'distance_m': distance}
        if _focus_component_value_bytes(component) > _FOCUS_COMPONENT_VALUE_BYTES_LIMIT:
            reason = 'focus_component_text_budget'
        else:
            # An observation may be valid even if its identifiers cannot be used
            # by source_region. Publish only a ref the existing query admits.
            try:
                validate_source_region_query({
                    'mode': 'source_region', 'region_ref': component_reference,
                    'reference': {'id': reference['host_id']}, 'requested_facts': ['surface_proximity'],
                })
            except ValueError:
                reason = 'focus_component_reference_unavailable'
            else:
                reason = None
    if reason is not None:
        component = {'status': 'unknown', 'scope': _FOCUS_COMPONENT_SCOPE, 'reason': reason}
    check_budget('after_focus_component')
    work['focus_component_value_bytes'] = _focus_component_value_bytes(component)
    stages['focus_component_preparation'] = _interval(started)
    return component


def _select_nearest_surface(captured, binding, object_index, task_region, ordered_sha,
                            cache, work, stages, check_budget):
    reference_index = _object_index(binding, task_region['reference'])
    if object_index == reference_index:
        raise ValueError('focus_task_region_distinct_reference_required')
    objects = [binding['objects'][i] for i in (object_index, reference_index)]
    rows = [captured['meshes'][i] for i in (object_index, reference_index)]
    task = {
        'source_triangle_indices': [], 'primary_source_triangle_index': None,
        'front_normal_world': None, 'reference': objects[1],
        'selection_policy': {
            'group': 'one_nearest_surface_witness_target_triangle',
            'primary': 'exact_surface_proximity_winning_triangle',
            'reference_effect': 'group_and_primary',
        },
    }

    def unknown(reason):
        task.update(empty_reason=reason, nearest_surface={'status': 'unknown', 'reason': reason})
        return task

    if binding['capture_state'] is None:
        return unknown('capture_generation_unavailable')
    check_budget('before_nearest_surface_focus_meshes')
    started = time.perf_counter_ns()
    left, right = _meshes_from_objects(
        (mesh['vertices'], mesh['faces'], (obj['host_id'], obj['instance_id']), obj['object_name'])
        for obj, mesh in zip(objects, rows, strict=True))
    stages['nearest_surface_mesh_preparation'] = _interval(started)

    check_budget('before_nearest_surface_focus_measurement')
    started = time.perf_counter_ns()
    diagnostics = {}
    measured = _surface_pair_measurement(
        left, right, cache, check_budget, source=captured['source'], diagnostics=diagnostics,
        witness_capture={
            'document_epoch': binding['document_epoch'], 'capture_state': binding['capture_state'],
            'ordered_geometry_sha256': ordered_sha,
        })
    stages['nearest_surface_measurement'] = _interval(started)
    work.update(surface_pair_count=diagnostics['surface_pair_count'],
                surface_pair_cache_hit=diagnostics['surface_pair_cache_hit'])
    check_budget('after_nearest_surface_focus_measurement')

    distance = measured['distance_m']
    if (measured['measurement_valid'] is not True or type(distance) not in (float, int)
            or not math.isfinite(distance) or distance < 0):
        return unknown(measured.get('reason') or 'nearest_surface_measurement_unavailable')
    exact = measured.get('exact_witness_triangles')
    if exact is None:
        indices = measured.get('witness_triangle_indices')
        points = [measured['point_a_world'], measured['point_b_world']]
        encoding = 'binary64_world_m'
    else:
        indices, points = exact['indices'], exact['points_m']
        encoding = 'rational_world_m'
    if (measured['witness_status'] != 'measured' or not isinstance(indices, (list, tuple))
            or len(indices) != 2 or any(type(i) is not int or not 0 <= i < len(mesh['faces'])
                                        for i, mesh in zip(indices, rows, strict=True))
            or not isinstance(points, (list, tuple)) or len(points) != 2
            or any(not isinstance(point, (list, tuple)) or len(point) != 3 for point in points)):
        return unknown(measured.get('witness_reason') or 'nearest_surface_witness_source_unavailable')

    primary = indices[0]
    a, b, c = (vector(rows[0]['vertices'][vertex]) for vertex in rows[0]['faces'][primary])
    normal = _unit_exact_normal(cross(subtract(b, a), subtract(c, a)))
    if normal is None:
        return unknown('nearest_surface_target_triangle_degenerate')
    witness = {
        'scope': 'one_current_triangle_per_endpoint_non_exhaustive', 'index_domain': SOURCE_INDEX_DOMAIN,
        'ordered_geometry_sha256': ordered_sha, 'point_encoding': encoding,
    }
    for label, obj, index, point in zip(('a', 'b'), objects, indices, points, strict=True):
        witness[label] = {'host_id': obj['host_id'], 'instance_id': obj['instance_id'],
                          'source_triangle_index': index, 'point_m': point}
    component = _nearest_surface_component(captured, binding, object_index, objects[1], ordered_sha,
                                           primary, distance, work, stages, check_budget)
    task.update(source_triangle_indices=[primary], primary_source_triangle_index=primary,
                front_normal_world=normal, nearest_surface={
                    'status': 'measured', 'distance_m': distance, 'method': measured['method'], 'witness': witness,
                    'component': component,
                })
    return task


def _focus_side_directions(normal, scene_eye):
    # Place eight candidates at a fixed 45-degree tilt around the surface
    # normal. The least-aligned world axis gives a stable, nonsingular basis.
    normal = np.asarray(normal)
    axis = np.eye(3)[np.argmin(np.abs(normal))]
    tangent = axis - normal * np.dot(normal, axis)
    tangent /= np.linalg.norm(tangent)
    bitangent = np.cross(normal, tangent)
    diagonal = math.sqrt(.5)
    headings = ((1, 0), (diagonal, diagonal), (0, 1), (-diagonal, diagonal),
                (-1, 0), (-diagonal, -diagonal), (0, -1), (diagonal, -diagonal))
    directions = []
    for i, (x, y) in enumerate(headings):
        direction = normal + x * tangent + y * bitangent
        if np.linalg.norm(direction / np.linalg.norm(direction) - scene_eye) > 1e-12:
            directions.append((f'SIDE_{i}', direction.tolist()))
    return directions


def _focus_second_view(prepared, normal, display, work, stages, check_budget):
    started = time.perf_counter_ns()
    check_budget('focus_before_side_probe')
    scene = prepared.cameras['views'][0]
    baseline = prepared.cameras['views'][-1]
    retry_normal = baseline['name'] == 'FOCUS'
    mask = tuple(display['participation_mask'])
    face_count = sum(len(mesh.faces) for mesh, visible in zip(prepared.meshes, mask, strict=True) if visible)
    vertex_count = sum(len(mesh.vertices) for mesh in prepared.meshes)
    poses = [dict(baseline, name='NORMAL')]
    votes = {}
    chosen = 'NORMAL'
    alternative = None
    if face_count > _FOCUS_PROBE_FACE_LIMIT or vertex_count > _FOCUS_PROBE_VERTEX_LIMIT:
        reason = 'probe_geometry_limit'
    else:
        directions = _focus_side_directions(normal, scene['target_to_eye_unit'])
        bounds = [[mesh.vertices.min(axis=0).tolist(), mesh.vertices.max(axis=0).tolist()]
                  for mesh in prepared.meshes]
        try:
            sides = _observation_target_cameras(prepared.region_mesh.vertices.tolist(), bounds,
                                                directions=directions)
        except BlenderHostError:
            reason = 'probe_camera_unavailable'
        else:
            poses.extend(sides['views'])
            _, votes = select_sparse_attention_view(prepared.meshes, poses, object_mask=mask,
                object_index=prepared.object_index, source_triangle_indices=prepared.source_triangle_indices,
                check_budget=check_budget)
            if 'NORMAL' in votes:
                chosen = max(votes, key=votes.get)
            if chosen != 'NORMAL':
                alternative = next(pose for pose in poses if pose['name'] == chosen)
                reason = 'side_probe_ahead'
            else:
                reason = 'normal_kept' if 'NORMAL' in votes else 'normal_probe_unavailable'
    check_budget('focus_after_side_probe')
    work.update(focus_view_probe_views=len(votes), focus_view_probe_samples=len(votes) * _SPARSE_GRID_SIZE ** 2)
    stages['focus_view_direction_selection'] = {
        **_interval(started), 'votes': votes, 'grid_size': _SPARSE_GRID_SIZE,
        'directions_world': {pose['name']: pose['target_to_eye_unit'] for pose in poses},
        'chosen_candidate': chosen, 'reason': reason, 'normal_already_sampled': not retry_normal,
        'displayed_face_count': face_count, 'all_vertex_count': vertex_count,
        'vote_semantics': 'predicted_target_owned_sample_centres',
    }
    return alternative, retry_normal


@dataclass
class FocusState:
    source_ref: dict | None
    directions: list
    centroid: list | None = None
    normal: list | None = None
    attempted: dict = field(default_factory=dict)
    verified: list = field(default_factory=list)
    best_frame: dict | None = None
    best_sample: dict | None = None
    task_region: dict | None = None
    attempted_primary: dict = field(default_factory=dict)

    @property
    def pixels(self):
        return self.best_sample['selected_surface_pixels'] if self.best_sample else 0


def observe_focus(captured, selector, focus, directory, context, binding, display, ordered_sha,
                  validation_stage, *, include_image, construction_callback, check_budget):
    index = _object_index(binding, selector)
    work = dict(raster_attempts=0, raster_completed=0, PNG_bytes=0, NPZ_bytes=0, array_payload_bytes=0,
                local_verified_images=0, temporary_encoded_archive_bytes=0)
    stages = {}
    task_region = focus.get('task_region') if isinstance(focus, dict) else None
    nearest = task_region is not None and task_region.get('relation') == 'nearest_surface'
    if nearest:
        work.update(surface_pair_count=0, surface_pair_cache_hit=False,
                    focus_component_face_scans=0, focus_component_rows=0, focus_component_value_bytes=0,
                    focus_view_probe_views=0, focus_view_probe_samples=0)

    def select():
        started = time.perf_counter_ns()
        mesh = captured['meshes'][index]
        task = None
        if task_region is not None:
            if nearest:
                task = _select_nearest_surface(captured, binding, index, task_region, ordered_sha,
                                               context.scene_cache, work, stages, check_budget)
            else:
                task = select_task_region(captured, binding, index, task_region, check_budget)
            source_index = task['primary_source_triangle_index']
            normal = task['front_normal_world']
            selected = task['source_triangle_indices']
        else:
            winner = select_triangle(mesh, focus, check_budget)
            source_index, normal = winner if winner is not None else (None, None)
            selected = [source_index]
        stages['focus_selection'] = _interval(started)
        if source_index is None:
            return FocusState(None, [], task_region=task)
        reference = _source_ref(captured, binding, index, selected, ordered_sha)
        scene = CAMERA_DIRECTIONS['SCENE']
        directions = [('SCENE', scene)]
        if np.linalg.norm(normal - np.asarray(scene) / np.linalg.norm(scene)) > 1e-12:
            directions.append(('FOCUS', normal))
        corners = [vector(mesh['vertices'][v]) for v in mesh['faces'][source_index]]
        centroid = [float(sum(axis) / 3) for axis in zip(*corners)]
        return FocusState(reference, directions, centroid, normal, task_region=task)

    state, selection_hit = context.prepared('focus_state', select)
    task = state.task_region
    work['focus_selections'] = int(not selection_hit)
    reason = 'image_not_requested'
    if state.source_ref is None:
        reason = ('no_matching_nondegenerate_source_triangle' if task is None else task['empty_reason'])
    elif display['status'] != 'captured':
        reason = display['reason']
    elif not display['participation_mask'][index]:
        reason = 'selected_object_not_displayed'
    elif include_image and binding['capture_state'] is None:
        reason = 'capture_generation_unavailable'
    elif include_image:
        directions = state.directions
        # If SCENE already points along the normal, allow a side as the only
        # useful second frame. An interrupted SCENE supplies no probe trigger.
        if nearest and len(directions) == 1 and ('SCENE' not in state.attempted
                or type(state.attempted['SCENE']) is int):
            directions = [*directions, ('FOCUS', state.normal)]
        if len(state.attempted) < len(directions) and state.pixels < _MIN_SURFACE_PIXELS:
            prepared = prepare_region(captured, {'region_ref': state.source_ref}, check_budget,
                _binding=binding, _validated_region_ref=True, _scene_validation_stage=validation_stage,
                _camera_directions=state.directions)
            prepared.images = _region_image_store(prepared, directory, display)

        def charge(name):
            construction_callback(name)
            # An interrupted construction spends its view. A never-started one is still available.
            state.attempted[name] = None
            if task is not None:
                state.attempted_primary[name] = None

        pixel_options = {} if task is None else {
            'primary_source_triangle_index': task['primary_source_triangle_index']}
        for name, _ in directions:
            if state.pixels >= _MIN_SURFACE_PIXELS:
                break
            if name in state.attempted:
                continue
            check_budget('focus_before_view')
            frame_source = prepared
            if nearest and name == 'FOCUS' and type(state.attempted.get('SCENE')) is int:
                side, retry_normal = _focus_second_view(prepared, state.normal, display, work, stages, check_budget)
                if side is None and not retry_normal:
                    break
                if side is not None:
                    # The first frame keeps its original camera binding. Bind
                    # the second frame to exactly the camera used for voting.
                    started = time.perf_counter_ns()
                    frame_source = prepare_region(captured, {'region_ref': state.source_ref}, check_budget,
                        _binding=binding, _validated_region_ref=True, _normalized_from=prepared,
                        _scene_validation_stage=validation_stage,
                        _camera_directions=[(name, side['direction_rational'])])
                    if frame_source.cameras['views'] != [dict(side, name=name)]:
                        raise ValueError('focus_second_view_camera_binding_mismatch')
                    frame_source.images = _region_image_store(frame_source, directory, display)
                    stages['focus_second_view_preparation'] = _interval(started)
            frame, sample = _capture_region_frame(frame_source, name, None, display, work, stages,
                                                   charge, check_budget, sampled_pixel=True, **pixel_options)
            pixels = sample['selected_surface_pixels']
            state.attempted[name] = pixels
            if task is not None:
                state.attempted_primary[name] = sample['primary_surface_pixels']
            state.verified.append(frame)
            if state.best_frame is None or pixels > state.pixels:
                state.best_frame = frame
                state.best_sample = {key: sample[key] for key in
                    ('view_name', 'frame_identity', 'image_ref', 'selected_surface_pixels', 'sampled_pixel',
                     'primary_surface_pixels') if key in sample}
                state.best_sample.update(target_world_m=frame['pose']['target_world_m'],
                                         target_to_eye_unit=frame['pose']['target_to_eye_unit'])
        reason = 'sample_target_met' if state.pixels >= _MIN_SURFACE_PIXELS else 'view_budget_exhausted'
    check_budget('focus_before_result')
    frame = state.best_frame if include_image else None
    work['frame_reuses'] = int(frame is not None and not work['raster_attempts'])
    facts = {'selection': focus, 'object': binding['objects'][index], 'region_ref': state.source_ref,
             'source_triangle_centroid_world_m': state.centroid, 'front_normal_world': state.normal,
             'scope': 'one_current_evaluated_source_triangle', 'stop_reason': reason,
             'minimum_sample_pixels': _MIN_SURFACE_PIXELS, 'complete_surface_visibility': 'unknown',
             'views': [{'view_name': name, 'verified_pixels': count} for name, count in state.attempted.items()],
             'sample': state.best_sample if frame is not None else None}
    if task is not None:
        if nearest:
            facts['nearest_surface'] = task['nearest_surface']
        else:
            facts['scope'] = 'multiple_current_evaluated_source_triangles'
        facts.update(primary_source_triangle_index=task['primary_source_triangle_index'],
                     task_source_triangle_indices=task['source_triangle_indices'],
                     reference=task['reference'], selection_policy=task['selection_policy'])
        for view in facts['views']:
            view['primary_verified_pixels'] = state.attempted_primary[view['view_name']]
    response_binding = {key: binding[key] for key in
                        ('document_epoch', 'capture_state', 'source_binding_sha256', 'scene_revision', 'capture_scope')}
    response_binding['display_identity'] = display['identity']
    if frame is not None:
        response_binding.update(camera_identity=frame['candidate_identity'], binding_sha256=frame['host_binding_sha256'])
    return dict(result_kind='active_observation', observation_status='directed_focus',
                status={'sample_target_met': 'complete', 'image_not_requested': 'predicted'}.get(reason, 'unknown'),
                binding=response_binding, facts={'focus': facts}, work=work, stages=stages,
                frames=[frame] if frame is not None else [], constructed_frames=state.verified if include_image else [],
                read_only=True, execution_authority=False)


def _validate_nearest_surface_focus(focus, binding):
    nearest = focus['nearest_surface']
    reference = focus['region_ref']
    primary = focus['primary_source_triangle_index']
    rows = focus['task_source_triangle_indices']
    if nearest['status'] == 'unknown':
        if reference is not None or primary is not None or rows or 'component' in nearest:
            raise ValueError('nearest_surface_focus_source_binding_mismatch')
        return
    witness = nearest['witness']
    if (nearest['status'] != 'measured' or binding['capture_state'] is None or type(primary) is not int
            or reference is None or rows != [primary] or reference['source_triangle_indices'] != rows
            or reference['document_epoch'] != binding['document_epoch']
            or reference['capture_generation'] != _generation(binding)
            or witness['ordered_geometry_sha256'] != reference['ordered_geometry_sha256']
            or witness['a']['source_triangle_index'] != primary
            or any(witness['a'][key] != reference[key] for key in ('host_id', 'instance_id'))
            or any(witness[label][key] != obj[key]
                   for label, obj in zip(('a', 'b'), (focus['object'], focus['reference']), strict=True)
                   for key in ('host_id', 'instance_id'))):
        raise ValueError('nearest_surface_focus_source_binding_mismatch')
    _validate_focus_component(nearest, reference, primary)


def _validate_focus_component(nearest, selected, primary):
    component = nearest['component']
    if component.get('scope') != _FOCUS_COMPONENT_SCOPE:
        raise ValueError('focus_component_scope_mismatch')
    if component.get('status') == 'unknown':
        if set(component) != {'status', 'scope', 'reason'}:
            raise ValueError('focus_component_unknown_evidence_mismatch')
        return

    if set(component) != {'status', 'scope', 'region_ref', 'distance_m'} or component['status'] != 'measured':
        raise ValueError('focus_component_evidence_mismatch')
    reference = component['region_ref']
    rows = reference['source_triangle_indices']
    fields = set(selected) - {'source_triangle_indices', 'region_id'}
    if (component['distance_m'] != nearest['distance_m'] or set(reference) != set(selected)
            or any(reference[key] != selected[key] for key in fields)
            or type(rows) is not list or not 1 <= len(rows) <= MAX_SOURCE_REGION_TRIANGLES
            or any(type(row) is not int or row < 0 for row in rows) or sorted(set(rows)) != rows
            or primary not in rows or _focus_component_value_bytes(component) > _FOCUS_COMPONENT_VALUE_BYTES_LIMIT
            or reference['region_id'] != 'source-region:' + fingerprint({
                key: value for key, value in reference.items() if key != 'region_id'})):
        raise ValueError('focus_component_source_binding_mismatch')


def validate_focus_delivery(result, frames):
    focus, binding = result['facts']['focus'], result['binding']
    if 'nearest_surface' in focus:
        _validate_nearest_surface_focus(focus, binding)
    sample = focus['sample']
    if sample is None and not frames:
        return
    if len(frames) != 1 or not isinstance(sample, dict):
        raise ValueError('focus_frame_binding_mismatch')
    frame = frames[0]
    reference = focus['region_ref']
    if (any(sample[key] != frame[key] for key in ('frame_identity', 'image_ref', 'view_name'))
            or any(sample[key] != frame['pose'][key] for key in ('target_world_m', 'target_to_eye_unit'))
            or frame['image_ref'] != 'source-region-image:' + fingerprint((
                reference['region_id'], frame['frame_identity'], frame['image_sha256']))
            or frame['display_identity'] != binding['display_identity']
            or frame['source_revision'] != binding['scene_revision']
            or frame['candidate_identity'] != binding['camera_identity']
            or frame['host_binding_sha256'] != binding['binding_sha256']):
        raise ValueError('focus_frame_binding_mismatch')
    if 'primary_source_triangle_index' in focus:
        primary = focus['primary_source_triangle_index']
        count = sample['primary_surface_pixels']
        selected_pixels = sample['selected_surface_pixels']
        matching_views = [row for row in focus['views'] if row['view_name'] == sample['view_name']]
        if (type(primary) is not int or primary not in reference['source_triangle_indices']
                or focus['task_source_triangle_indices'] != reference['source_triangle_indices']
                or type(count) is not int or type(selected_pixels) is not int
                or not 0 <= count <= selected_pixels
                or len(matching_views) != 1 or matching_views[0]['verified_pixels'] != selected_pixels
                or matching_views[0]['primary_verified_pixels'] != count):
            raise ValueError('focus_task_region_pixel_binding_mismatch')
    anchor = sample.get('sampled_pixel')
    if sample['selected_surface_pixels']:
        if (not isinstance(anchor, dict) or anchor['source_triangle_index'] not in reference['source_triangle_indices']
                or any(type(anchor[key]) is not int or not 0 <= anchor[key] < 512 for key in ('row', 'column'))):
            raise ValueError('focus_pixel_binding_mismatch')
    elif anchor is not None:
        raise ValueError('focus_pixel_binding_mismatch')
