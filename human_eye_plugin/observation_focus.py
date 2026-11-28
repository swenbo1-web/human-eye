"""Select one current source triangle and spend at most one corrective view on it."""
from __future__ import annotations

from dataclasses import dataclass, field
import time

import numpy as np

from .active_observation import fingerprint, vector
from .active_observation_host import CAMERA_DIRECTIONS
from .source_region import (
    _MIN_SURFACE_PIXELS, _capture_region_frame, _interval, _object_index,
    _region_image_store, _source_ref, prepare_region,
)


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

    @property
    def pixels(self):
        return self.best_sample['selected_surface_pixels'] if self.best_sample else 0


def observe_focus(captured, selector, focus, directory, context, binding, display, ordered_sha,
                  validation_stage, *, include_image, construction_callback, check_budget):
    index = _object_index(binding, selector)
    work = dict(raster_attempts=0, raster_completed=0, PNG_bytes=0, NPZ_bytes=0, array_payload_bytes=0,
                local_verified_images=0, temporary_encoded_archive_bytes=0)
    stages = {}

    def select():
        started = time.perf_counter_ns()
        mesh = captured['meshes'][index]
        winner = select_triangle(mesh, focus, check_budget)
        stages['focus_selection'] = _interval(started)
        if winner is None:
            return FocusState(None, [])
        source_index, normal = winner
        reference = _source_ref(captured, binding, index, [source_index], ordered_sha)
        scene = CAMERA_DIRECTIONS['SCENE']
        directions = [('SCENE', scene)]
        if np.linalg.norm(normal - np.asarray(scene) / np.linalg.norm(scene)) > 1e-12:
            directions.append(('FOCUS', normal))
        corners = [vector(mesh['vertices'][v]) for v in mesh['faces'][source_index]]
        centroid = [float(sum(axis) / 3) for axis in zip(*corners)]
        return FocusState(reference, directions, centroid, normal)

    state, selection_hit = context.prepared('focus_state', select)
    work['focus_selections'] = int(not selection_hit)
    reason = 'image_not_requested'
    if state.source_ref is None:
        reason = 'no_matching_nondegenerate_source_triangle'
    elif display['status'] != 'captured':
        reason = display['reason']
    elif not display['participation_mask'][index]:
        reason = 'selected_object_not_displayed'
    elif include_image and binding['capture_state'] is None:
        reason = 'capture_generation_unavailable'
    elif include_image:
        if len(state.attempted) < len(state.directions) and state.pixels < _MIN_SURFACE_PIXELS:
            prepared = prepare_region(captured, {'region_ref': state.source_ref}, check_budget,
                _binding=binding, _validated_region_ref=True, _scene_validation_stage=validation_stage,
                _camera_directions=state.directions)
            prepared.images = _region_image_store(prepared, directory, display)

        def charge(name):
            construction_callback(name)
            # An interrupted construction spends its view. A never-started one is still available.
            state.attempted[name] = None

        for name, _ in state.directions:
            if state.pixels >= _MIN_SURFACE_PIXELS:
                break
            if name in state.attempted:
                continue
            check_budget('focus_before_view')
            frame, sample = _capture_region_frame(prepared, name, None, display, work, stages,
                                                   charge, check_budget, sampled_pixel=True)
            pixels = sample['selected_surface_pixels']
            state.attempted[name] = pixels
            state.verified.append(frame)
            if state.best_frame is None or pixels > state.pixels:
                state.best_frame = frame
                state.best_sample = {key: sample[key] for key in
                    ('view_name', 'frame_identity', 'image_ref', 'selected_surface_pixels', 'sampled_pixel')
                    if key in sample}
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


def validate_focus_delivery(result, frames):
    focus, binding = result['facts']['focus'], result['binding']
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
    anchor = sample.get('sampled_pixel')
    if sample['selected_surface_pixels']:
        if (not isinstance(anchor, dict) or anchor['source_triangle_index'] not in reference['source_triangle_indices']
                or any(type(anchor[key]) is not int or not 0 <= anchor[key] < 512 for key in ('row', 'column'))):
            raise ValueError('focus_pixel_binding_mismatch')
    elif anchor is not None:
        raise ValueError('focus_pixel_binding_mismatch')
