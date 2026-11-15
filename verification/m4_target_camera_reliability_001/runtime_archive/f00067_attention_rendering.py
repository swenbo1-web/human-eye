"""Confirm beneficial Q4 attention changes against the actual scene geometry.

Only the local observation image changes. This module cannot move Blender,
choose an execution pair, grant authority, or certify a collision-free path.
"""
from __future__ import annotations

import copy
import json
import time

import numpy as np
from PIL import Image, ImageDraw

from .attention_policy import AttentionPolicy, confirm_attention
from .scene_rendering import (_look_at, _projection, _annotate, stable_object_label,
                              _prepared_caption_inputs, _claim_prepared_attention_inputs,
                              _prepared_attention_inputs_match, _draw_label_layer)
from .attention_raster import rasterize_attention
from .geometry_safety import _point_triangle_min_sq
from .task_labels import task_display_label, validate_task_label_plan


def _orthogonal_caption_contact(contact, meshes, focal_id, reference_id):
    """Validate the current internal strict pair for a display-only caption.

    This never evaluates clearance or selects a camera. It only accepts the
    already-certified positive orthogonal result and matching original-surface
    witnesses; arbitrary display diagnostics cannot activate the path.
    """
    if type(contact) is not dict or contact.get('object_id') != reference_id:
        return None
    method = 'exact_orthogonal_cell_union_sat'
    strict = contact.get('strict_geometry')
    clearance = contact.get('signed_clearance_m')
    if (type(strict) is not dict or contact.get('measurement_method') != method
            or strict.get('measurement_method') != method
            or contact.get('measurement_valid') is not True
            or strict.get('measurement_valid') is not True
            or contact.get('clearance_exact') is not True
            or contact.get('measurement_kind') != 'exact'
            or contact.get('clearance_state') != 'positive_clearance'
            or contact.get('is_penetrating') is not False
            or strict.get('is_penetrating') is not False
            or type(clearance) not in (int, float) or not np.isfinite(clearance)
            or clearance <= 0
            or type(strict.get('signed_clearance_m')) not in (int, float)
            or strict['signed_clearance_m'] != clearance
            or strict.get('evaluator_source') != 'engine_geometry'
            or strict.get('witness_scope') != 'nearest_original_surface_points_not_internal_cell_boundaries'
            or contact.get('witness_source') != 'current_original_full_mesh_surface_features'):
        return None
    by_id = {mesh.object_id: mesh for mesh in meshes}
    if focal_id == reference_id or focal_id not in by_id or reference_id not in by_id:
        return None
    points = []
    for field, identity in (('point_a_world', focal_id), ('point_b_world', reference_id)):
        value, original = contact.get(field), strict.get(field)
        if (not isinstance(value, (list, tuple)) or len(value) != 3
                or any(type(v) not in (int, float) or not np.isfinite(v) for v in value)
                or not isinstance(original, (list, tuple)) or len(original) != 3
                or any(type(v) not in (int, float) or not np.isfinite(v) for v in original)
                or list(value) != list(original)):
            return None
        point = np.asarray(value, dtype=np.float64)
        mesh = by_id[identity]
        if np.any(point < mesh.bbox_min - 1e-9) or np.any(point > mesh.bbox_max + 1e-9):
            return None
        # Rebase before the membership-only check; no new nearest distance is
        # calculated and no internal decomposition face is drawn as a surface.
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            triangles = mesh.vertices[mesh.faces] - point
            surface_sq = _point_triangle_min_sq(np.zeros((1, 3)), triangles)
        if not np.isfinite(surface_sq) or surface_sq > 1e-18:
            return None
        points.append(point)
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        distance = float(np.linalg.norm(points[1] - points[0]))
    if not np.isfinite(distance) or abs(distance - clearance) > 1e-9:
        return None
    return {'signed_clearance_m': clearance,
            'witness_points_world_m': [point.tolist() for point in points],
            'measurement_method': method}


def _annotate_orthogonal_target_measurement(canvas, metadata, meshes, *,
                                           focal_id, reference_id, contact,
                                           prepared_render=None):
    """Caption a held default Q4 without asserting camera or visible-gap gain.

    Accepted attention already has its own measurement overlay. A hold never
    becomes a camera shift merely to display this annotation. Q1-Q3 and the
    rendered Q4 camera and geometry are retained, and no state is committed.
    Small or occupied views retain their original pixels. The layout must be
    proved by the current opaque render's depth and drawn-annotation evidence;
    ordinary metadata or a copied/mutated image cannot supply that proof.
    """
    if (type(metadata) is not dict or metadata.get('measurement_overlay') is not False
            or type(metadata.get('attention')) is not dict
            or metadata['attention'].get('decision') != 'hold'
            or type(metadata.get('raster_schedule')) is not dict
            or metadata['raster_schedule'].get('canvas_complete') is not True
            or metadata['raster_schedule'].get('final_q4') != 'target'):
        return canvas, metadata
    size = metadata.get('quad_size')
    views = metadata.get('views')
    if (type(size) is not int or not 256 <= size <= 512
            or canvas.mode != 'RGB' or canvas.size != (size * 2, size * 2)
            or type(views) is not list or len(views) != 4
            or type(views[3]) is not dict or views[3].get('name') != 'Q4 TARGET'
            or views[3].get('target_object_ids') != [focal_id, reference_id]
            or views[3].get('render_status') == 'deferred'):
        return canvas, metadata
    inputs = _prepared_caption_inputs(canvas, metadata, meshes, prepared_render)
    if inputs is None:
        return canvas, metadata
    region, render_meshes = inputs
    try:
        measured = _orthogonal_caption_contact(contact, render_meshes, focal_id, reference_id)
    except (KeyError, TypeError, ValueError, IndexError, OverflowError, FloatingPointError):
        measured = None
    if measured is None:
        return canvas, metadata
    millimetres = measured['signed_clearance_m'] * 1000
    if not np.isfinite(millimetres):
        return canvas, metadata
    lines = [f'MEASURED {millimetres:.6g} mm', 'Auxiliary measurement, not a visible gap']
    left, top, right, bottom = region
    visual = copy.deepcopy(metadata)
    output = canvas.copy()
    picture = output.crop((size, size, size * 2, size * 2))
    draw = ImageDraw.Draw(picture)
    origins = [(left + 2, top + 2 + index * 12) for index in range(len(lines))]
    for line, origin in zip(lines, origins):
        bounds = draw.textbbox(origin, line)
        if bounds[0] < left or bounds[1] < top or bounds[2] > right or bounds[3] > bottom:
            return canvas, metadata
    draw.rectangle((left, top, right - 1, bottom - 1), fill=(18, 22, 30))
    for index, line in enumerate(lines):
        draw.text(origins[index], line, fill=(255, 223, 110))
    output.paste(picture, (size, size))
    visual['views'][3]['measurement_overlay'] = {
        'scope': 'strict_numeric_annotation_only_no_camera_change_or_visible_gap_evidence',
        **measured,
        'source': 'current_original_full_mesh_surface_features',
        'object_markers': [{'marker': marker, 'object_id': identity,
                            'stable_label': stable_object_label(identity)}
                           for marker, identity in zip(('A', 'B'), (focal_id, reference_id))],
        'caption_lines': lines, 'caption_box_px': list(region),
        'caption_layout_source': 'current_depth_and_drawn_annotations_empty_interior_band',
        'camera_changed': False, 'dimension_line_drawn': False,
        'visible_gap_certified': False, 'execution_authority': False,
        'independent_ground_truth': False, 'units': 'm'}
    visual['measurement_overlay'] = True
    return output, visual


def _attention_camera(meshes, plan):
    target = np.asarray(plan['target_world_m'], dtype=float)
    direction = np.asarray(plan['direction'], dtype=float)
    up = np.asarray(plan['up'], dtype=float)
    span = float(plan['view_span_m'])
    # Put the eye in front of ALL supplied geometry, not inside an occluder.
    front = max(float(((m.vertices - target) @ direction).max()) for m in meshes)
    distance = max(.1, front + .1, span)
    eye = target + direction * distance
    view = _look_at(eye, target, up)
    far = max(.081, max(float((-m.vertices @ view[2, :3] - view[2, 3]).max())
                       for m in meshes) + max(span, .01))
    projection = _projection('orthographic', span / 2, .08, far)
    return view, projection, eye, far


_WITNESS_GEOMETRY_MAX_BYTES = 8 * 1024 * 1024


class _WitnessGeometry:
    """Lazy triangle data belonging to one claimed attention observation.

    The limit covers retained NumPy storage, not process RSS or temporary ray
    arrays. A mesh that does not fit still uses the original full-geometry
    calculation. These objects never enter a result, cache or persistent state.
    """
    __slots__ = ('__meshes', '__data', '__retained_bytes')

    def __init__(self, meshes):
        meshes = tuple(meshes)
        if any(not isinstance(mesh.vertices, np.ndarray)
               or not isinstance(mesh.faces, np.ndarray)
               or mesh.vertices.flags.writeable or mesh.faces.flags.writeable
               for mesh in meshes):
            raise ValueError('Witness geometry requires operation-owned read-only meshes')
        object.__setattr__(self, '_WitnessGeometry__meshes', meshes)
        object.__setattr__(self, '_WitnessGeometry__data', [None] * len(meshes))
        object.__setattr__(self, '_WitnessGeometry__retained_bytes', 0)

    @property
    def meshes(self):
        return self.__meshes

    @property
    def retained_bytes(self):
        return self.__retained_bytes

    def __setattr__(self, name, value):
        raise AttributeError('Witness geometry belongs to one observation')

    def __reduce_ex__(self, protocol):
        raise TypeError('Witness geometry cannot be copied or persisted')

    def for_mesh(self, index):
        data = self.__data[index]
        if data is False:
            return None
        if data is not None:
            return data
        mesh = self.__meshes[index]
        # An a view retains the 3x3 triangle storage, in addition to two 3-vector
        # edges and one scale value: 16 float64 values per triangle. Reject the
        # allocation before preparing it when it would exceed the local limit.
        required = len(mesh.faces) * 16 * np.dtype(np.float64).itemsize
        if (mesh.vertices.dtype != np.dtype(np.float64)
                or required > _WITNESS_GEOMETRY_MAX_BYTES - self.__retained_bytes):
            self.__data[index] = False
            return None
        tri = mesh.vertices[mesh.faces]
        a, e1, e2 = tri[:, 0], tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
        scale = np.linalg.norm(e1, axis=1) * np.linalg.norm(e2, axis=1)
        retained = tri.nbytes + e1.nbytes + e2.nbytes + scale.nbytes
        if retained != required:
            # Defensive compatibility fallback; never approximate or silently
            # retain storage outside the declaration above.
            self.__data[index] = False
            return None
        for value in (tri, a, e1, e2, scale):
            value.setflags(write=False)
        data = (a, e1, e2, scale)
        self.__data[index] = data
        object.__setattr__(self, '_WitnessGeometry__retained_bytes',
                           self.__retained_bytes + retained)
        return data


def _visible_witness(point, meshes, view, span):
    """Orthographic ray/triangle occlusion at the exact known surface point.

    Visibility is local to two witnesses, not an object-wide visibility claim.
    Coplanar grazing rays are rejected rather than calling them unobstructed.
    """
    p = np.asarray(point, dtype=float)
    eye_direction = view[2, :3]
    tolerance = max(1e-9, span * 1e-7)
    # Cast towards the eye from just in front of the witness. A positive hit
    # is an intervening surface, including self-occlusion by the target mesh.
    origin = p + eye_direction * tolerance
    has_surface = False
    prepared = meshes if type(meshes) is _WitnessGeometry else None
    for index, mesh in enumerate(prepared.meshes if prepared is not None else meshes):
        data = prepared.for_mesh(index) if prepared is not None else None
        if data is None:
            tri = mesh.vertices[mesh.faces]
            a, e1, e2 = tri[:, 0], tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
        else:
            a, e1, e2, scale = data
        cross = np.cross(np.broadcast_to(eye_direction, e2.shape), e2)
        det = np.einsum('ij,ij->i', e1, cross)
        if data is None:
            scale = np.linalg.norm(e1, axis=1) * np.linalg.norm(e2, axis=1)
        usable = np.abs(det) > np.maximum(scale * 1e-12, 1e-30)
        if not usable.any():
            continue
        a, e1, e2, cross, det = a[usable], e1[usable], e2[usable], cross[usable], det[usable]
        offset = origin - a
        u = np.einsum('ij,ij->i', offset, cross) / det
        q = np.cross(offset, e1)
        v = (q @ eye_direction) / det
        distance = np.einsum('ij,ij->i', e2, q) / det
        inside = (u >= -1e-8) & (v >= -1e-8) & (u + v <= 1 + 1e-8)
        if np.any(inside & (distance > tolerance)):
            return False
        if np.any(inside & (np.abs(distance) <= tolerance * 4)):
            has_surface = True
    return bool(has_surface)


def _contrasting_boundaries(color, owners):
    """Mark both pixels of a winning-owner boundary with RGB distance >=24."""
    boundary = np.zeros(owners.shape, dtype=bool)
    for axis in (0, 1):
        first = (slice(None, -1), slice(None)) if axis == 0 else (slice(None), slice(None, -1))
        second = (slice(1, None), slice(None)) if axis == 0 else (slice(None), slice(1, None))
        if color.dtype == np.uint8:
            # A boundary requires different depth winners. Only those pairs
            # need RGB work; uniform surface interiors contribute nothing.
            changed = owners[first] != owners[second]
            count = int(np.count_nonzero(changed))
            # Bound sparse advanced-index/gather work to 1/8 of the pairs.
            # Beyond this fixed density, sequential per-channel integer
            # accumulation avoids two large coordinate arrays and RGB gathers.
            if count * 8 > changed.size:
                squared = np.zeros(changed.shape, dtype=np.int32)
                for channel in range(color.shape[2]):
                    difference = np.subtract(color[first][..., channel],
                        color[second][..., channel], dtype=np.int32)
                    np.square(difference, out=difference)
                    squared += difference
                changed &= squared >= 24 * 24
                boundary[first] |= changed
                boundary[second] |= changed
            elif count:
                rows, columns = np.nonzero(changed)
                difference = (color[first][rows, columns].astype(np.int32)
                              - color[second][rows, columns].astype(np.int32))
                # uint8 RGB gives an exact integer sum <= 3 * 255**2.
                # Compare squared distances without full-frame float arrays
                # or square roots, retaining the inclusive 24 RGB threshold.
                contrasting = np.einsum('ij,ij->i', difference, difference) >= 24 * 24
                rows, columns = rows[contrasting], columns[contrasting]
                boundary[first][rows, columns] = True
                boundary[second][rows, columns] = True
        else:
            # Preserve the helper's previous numeric behavior for callers
            # with fractional or wider colors; never truncate to uint8/int.
            contrast = np.linalg.norm(color[first].astype(float) - color[second].astype(float), axis=2)
            changed = (owners[first] != owners[second]) & (contrast >= 24.)
            boundary[first] |= changed
            boundary[second] |= changed
    return boundary


def _readability_evidence(color, owners, meshes, target_ids, pixels):
    """Use real unannotated winning surfaces, never labels, as evidence."""
    by_id = {mesh.object_id: index for index, mesh in enumerate(meshes)}
    boundary = _contrasting_boundaries(color, owners)
    counts = [int(np.count_nonzero(owners == by_id[identity])) for identity in target_ids]
    edges = [int(np.count_nonzero(boundary & (owners == by_id[identity]))) for identity in target_ids]
    fraction = np.linspace(.1, .9, 17)
    samples = pixels[0] + fraction[:, None] * (pixels[1] - pixels[0])
    xy = np.rint(samples).astype(int)
    xy[:, 0] = np.clip(xy[:, 0], 0, owners.shape[1] - 1)
    xy[:, 1] = np.clip(owners.shape[0] - 1 - xy[:, 1], 0, owners.shape[0] - 1)
    background = int(np.count_nonzero(owners[xy[:, 1], xy[:, 0]] < 0))
    return {'passed': min(counts) >= 16 and min(edges) >= 4,
        'target_object_ids': list(target_ids), 'visible_surface_pixels': counts,
        'contrasting_boundary_pixels': edges, 'minimum_surface_pixels': 16,
        'minimum_boundary_pixels': 4, 'minimum_rgb_boundary_contrast': 24.,
        'measurement_stage': 'before_any_annotations_full_scene_depth_winners',
        'scope': 'two_object_surface_localization_and_contrasting_boundaries_not_gap_visibility',
        'gap_background_samples': background, 'gap_segment_samples': len(fraction),
        'visible_gap_certified': False, 'annotations_count_as_evidence': False,
        'model_quality_gain_proven': False}


def _task_marker_label(draw, marker, identity, endpoint, size, occupied):
    """Place one whole witness glyph inside the remaining contact view.

    Fixed candidates and at most two markers bound the work. Moving text does
    not move a witness or dimension line; an unplaceable glyph is explicit.
    """
    bottom = size - (47 if size >= 256 else 55 if size >= 128 else 16)
    region = (2, 19, size - 2, bottom)
    glyph = draw.textbbox((0, 0), marker, stroke_width=1)
    width, height = glyph[2] - glyph[0], glyph[3] - glyph[1]
    receipt = {'marker': marker, 'object_id': identity, 'status': 'omitted_no_label_space',
               'text_box_px': None, 'text_position_px': None,
               'text_box_convention': 'right_bottom_exclusive'}
    if width > region[2] - region[0] or height > region[3] - region[1]:
        return receipt
    ex, ey = (float(value) for value in endpoint)
    preferred = [(ex + 5 + glyph[0], ey - 7 + glyph[1]),
                 (ex - width - 5, ey - height / 2),
                 (ex - width / 2, ey - height - 5), (ex - width / 2, ey + 5)]
    preferred.extend([(region[0], region[1]), (region[2] - width, region[1]),
                      (region[0], region[3] - height), (region[2] - width, region[3] - height)])
    candidates = []
    for x, y in preferred:
        left = max(region[0], min(int(round(x)), region[2] - width))
        top = max(region[1], min(int(round(y)), region[3] - height))
        box = (left, top, left + width, top + height)
        if any(box[0] < old[2] + 2 and box[2] > old[0] - 2
               and box[1] < old[3] + 2 and box[3] > old[1] - 2 for old in occupied):
            continue
        distance = abs((box[0] + box[2]) / 2 - ex) + abs((box[1] + box[3]) / 2 - ey)
        candidates.append((distance, box))
    if not candidates:
        return receipt
    box = min(candidates, key=lambda row: (row[0], row[1]))[1]
    position = (box[0] - glyph[0], box[1] - glyph[1])
    draw.text(position, marker, fill=(255, 245, 170), stroke_width=1, stroke_fill=(12, 16, 24))
    occupied.append(box)
    receipt.update(status='drawn', text_box_px=list(box), text_position_px=list(position))
    return receipt


def _contact_overlay(picture, plan, proposal, pixels, view_metadata, *, label_plan=None):
    draw, size = ImageDraw.Draw(picture), picture.width
    screen = np.c_[pixels[:, 0], size - 1 - pixels[:, 1]]
    direction = screen[1] - screen[0]
    length = float(np.linalg.norm(direction))
    perpendicular = np.array([-direction[1], direction[0]]) / max(length, 1e-12)
    dimension = screen + perpendicular * 22
    markers = ([task_display_label(identity, label_plan) for identity in plan['target_object_ids']]
               if label_plan is not None else ['A', 'B'])
    for label, point, endpoint in zip(markers, screen, dimension):
        x, y = (float(value) for value in point)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), outline=(255, 245, 170), width=1)
        draw.line([tuple(point), tuple(endpoint)], fill=(255, 223, 110), width=1)
        if label_plan is None:
            draw.text((float(endpoint[0] + 5), float(endpoint[1] - 7)), label, fill=(255, 245, 170),
                      stroke_width=1, stroke_fill=(12, 16, 24))
    draw.line([tuple(point) for point in dimension], fill=(255, 223, 110), width=2)
    if length > 1e-12:
        along = direction / length
        for endpoint, sign in ((dimension[0], 1), (dimension[1], -1)):
            tip = endpoint + along * sign * min(3., length / 3)
            draw.line([tuple(tip + perpendicular * 2), tuple(endpoint), tuple(tip - perpendicular * 2)],
                      fill=(255, 223, 110), width=1)
    marker_labels = []
    if label_plan is not None:
        # Surface labels are painted once, after dimension lines, so neither
        # those lines nor later witness labels can cross their text.
        rows = view_metadata.get('projected_labels', [])
        _draw_label_layer(draw, rows)
        occupied = [(r['label_box_px'][0], r['label_box_px'][1],
                     r['label_box_px'][2] + 1, r['label_box_px'][3] + 1) for r in rows]
        for marker, identity, endpoint in zip(markers, plan['target_object_ids'], dimension):
            marker_labels.append(_task_marker_label(draw, marker, identity, endpoint, size, occupied))
    if size >= 128:
        band_height = 47 if size >= 256 else 55
        draw.rectangle((0, size - band_height, size - 1, size - 16), fill=(18, 22, 30))
        label_a, label_b = [stable_object_label(identity) for identity in plan['target_object_ids']]
        if size >= 256:
            pair_text = (f'{markers[0]} / {markers[1]}: surfaces' if label_plan is not None
                         else f'A {label_a} / B {label_b}')
            draw.text((4, size - 46), pair_text, fill=(235, 242, 255))
            text = f"MEASURED {proposal['strict_clearance_m'] * 1000:.6g} mm; aux, not visible gap"
            draw.text((4, size - 32), text, fill=(255, 223, 110))
        else:
            draw.text((4, size - 54), f'{markers[0]} / {markers[1]}: surfaces', fill=(235, 242, 255))
            draw.text((4, size - 41), f"Measured {proposal['strict_clearance_m'] * 1000:.4g} mm", fill=(255, 223, 110))
            draw.text((4, size - 28), 'Aux; gap unproven', fill=(255, 223, 110))
    view_metadata['measurement_overlay'] = {
        'scope': 'numeric_witness_dimension_annotation_not_visible_gap_evidence',
        'signed_clearance_m': proposal['strict_clearance_m'],
        'object_markers': [{'marker': marker, 'object_id': identity, 'stable_label': stable_object_label(identity)}
                           for marker, identity in zip(markers, plan['target_object_ids'])],
        'witness_screen_px': screen.tolist(), 'dimension_line_px': dimension.tolist(),
        'visible_gap_certified': False, 'units': 'm', 'source': 'existing_unrounded_contact_measurement'}
    if label_plan is not None:
        view_metadata['measurement_overlay']['marker_labels'] = marker_labels


def apply_attention_to_canvas(canvas, metadata, meshes, *, focal_id, reference_id,
                              contacts, scene_fingerprint, previous=None, now_s=None,
                              prepared_render=None):
    """Return canvas, metadata and optional confirmed state to persist.

    The default Q4 remains intact if the candidate has no demonstrated gain,
    is occluded, exceeds the explicit cost budget, or fails validation. An
    internally deferred input stays incomplete on hold, so the caller must
    run finalize_scene_q4 before delivery. Only confirmed adoption can mark
    that deferred canvas complete without drawing the default Q4.
    """
    started = time.perf_counter()
    size = metadata['quad_size']
    label_plan = metadata.get('task_labels')
    if label_plan is not None:
        label_plan = validate_task_label_plan(label_plan, meshes,
            focal_id=focal_id, reference_id=reference_id)
        if label_plan['scene_fingerprint'] != scene_fingerprint:
            raise ValueError('Task labels belong to a different current snapshot')
    policy = AttentionPolicy()
    source_meshes = meshes
    owned = None
    if prepared_render is not None:
        owned = _claim_prepared_attention_inputs(canvas, metadata, meshes, prepared_render,
            scene_fingerprint=scene_fingerprint)
        if owned is None:
            visual = copy.deepcopy(metadata)
            visual['attention'] = {'decision': 'hold', 'applied': False,
                'state_to_commit': None, 'reason_codes': ['attention_prepared_inputs_invalid'],
                'visibility_verified': False, 'readability_verified': False,
                'precheck_reused': False, 'execution_authority': False,
                'additional_cost_ms': (time.perf_counter() - started) * 1000}
            return canvas, visual, None
        meshes = owned
    # Only the operation-owned, read-only snapshot may retain direction-free
    # triangle data. Construct even its small bookkeeping only when a real ray
    # is needed; a no-candidate hold must not scan every mesh for this feature.
    # Construction and lazy allocations stay inside the existing timer.
    witness_meshes = None
    def witness_inputs():
        nonlocal witness_meshes
        if witness_meshes is None:
            witness_meshes = _WitnessGeometry(owned) if owned is not None else meshes
        return witness_meshes
    precheck = None
    def plan_key(plan):
        # Keep the complete value, not a hash or rounded geometry surrogate.
        try:
            return json.dumps(plan, sort_keys=True, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError):
            return None
    def candidate_visible(plan):
        nonlocal precheck
        precheck = None
        if (time.perf_counter() - started) * 1000 >= policy.limits.max_additional_cost_ms:
            return False
        camera = _attention_camera(meshes, plan)
        visible = all(_visible_witness(point, witness_inputs(), camera[0], plan['view_span_m'])
                      for point in plan['witness_points_world_m'])
        if visible and owned is not None:
            key = plan_key(plan)
            if key is not None:
                # Only a completely successful two-witness callback is saved,
                # and the memo lives only in this one proposal invocation.
                precheck = (key, camera)
        return visible
    proposal = policy.propose(meshes, focal_id=focal_id, reference_id=reference_id,
        contacts=contacts, quad_size=size, include_image=True,
        scene_fingerprint=scene_fingerprint, previous=previous, now_s=now_s,
        candidate_visible=candidate_visible)
    visual = copy.deepcopy(metadata)
    visual['attention'] = copy.deepcopy(proposal)
    def budget_hold(elapsed_ms, *, actual_gap=None, visible=None, reused=False):
        # This is a cooperative checkpoint, not interruption of an in-flight
        # kernel or a deadline for the caller's necessary default-Q4 fallback.
        visual['attention'] = {'schema_version': '1.0', 'decision': 'hold',
            'applied': False, 'state_to_commit': None,
            'reason_codes': ['attention_budget_exhausted_before_raster'],
            'proposal': proposal, 'additional_cost_ms': elapsed_ms,
            'aborted_before_raster': True, 'raster_performed': False,
            'visibility_verified': False, 'readability_verified': False,
            'witness_visible': visible, 'raster_witness_supported': None,
            'readability': None, 'actual_projected_gap_px': actual_gap,
            'precheck_reused': bool(reused), 'execution_authority': False,
            'model_quality_gain_proven': False,
            'cost_scope': 'proposal_owned_input_validation_and_visibility_before_candidate_raster'}
        return canvas, visual, None
    if proposal['decision'] not in ('propose', 'retain'):
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms >= policy.limits.max_additional_cost_ms:
            return budget_hold(elapsed_ms)
        return canvas, visual, None
    if owned is not None and not _prepared_attention_inputs_match(
            canvas, metadata, source_meshes, prepared_render, scene_fingerprint=scene_fingerprint):
        visual['attention'] = {'decision': 'hold', 'applied': False,
            'state_to_commit': None, 'reason_codes': ['attention_prepared_inputs_changed'],
            'visibility_verified': False, 'readability_verified': False,
            'precheck_reused': False, 'execution_authority': False,
            'additional_cost_ms': (time.perf_counter() - started) * 1000}
        return canvas, visual, None
    plan = proposal['camera_plan']
    reused = precheck is not None and precheck[0] == plan_key(plan)
    view, projection, eye, far = precheck[1] if reused else _attention_camera(meshes, plan)
    points = np.asarray(plan['witness_points_world_m'], dtype=float)
    clip = (projection @ view @ np.c_[points, np.ones(2)].T).T
    ndc = clip[:, :3] / clip[:, 3:]
    pixels = (ndc[:, :2] + 1) * (size - 1) / 2
    actual_gap = float(np.linalg.norm(pixels[0] - pixels[1]))
    visible = [bool(np.all(np.abs(ndc[i]) <= 1) and
                    (reused or _visible_witness(points[i], witness_inputs(), view, plan['view_span_m'])))
               for i in range(2)]
    elapsed_before_raster = (time.perf_counter() - started) * 1000
    if elapsed_before_raster >= policy.limits.max_additional_cost_ms:
        return budget_hold(elapsed_before_raster, actual_gap=actual_gap, visible=visible, reused=reused)
    # Do not pay for a raster when the exact witnesses are already occluded.
    if all(visible):
        raster = rasterize_attention(meshes, view, projection, size, return_owner=True)
        color, depth = raster[:2]
        # The production raster already owns all three buffers. A legacy
        # two-buffer result has no owner evidence and cannot claim readability.
        owners = raster[2] if len(raster) == 3 else np.full((size, size), -1, dtype=np.int32)
    else:
        color = np.empty((size, size, 3), dtype=np.uint8)
        color[:] = (18, 22, 30)
        depth = np.full((size, size), np.inf)
        owners = np.full((size, size), -1, dtype=np.int32)
    raster_visible = []
    for i, point in enumerate(points):
        x = int(round(pixels[i, 0]))
        y = int(round((size - 1) - pixels[i, 1]))
        patch = depth[max(0, y - 2):min(size, y + 3), max(0, x - 2):min(size, x + 3)]
        expected_depth = float(-view[2, :3] @ point - view[2, 3])
        tolerance = max(1e-8, 2 * plan['view_span_m'] / (size - 1))
        raster_visible.append(bool(visible[i] and np.any(np.abs(patch - expected_depth) <= tolerance)))
    foreground = np.isfinite(depth)
    readability = _readability_evidence(color, owners, meshes, plan['target_object_ids'], pixels)
    elapsed_before_annotations = (time.perf_counter() - started) * 1000
    confirmed = confirm_attention(proposal, witness_visible=raster_visible,
        actual_projected_gap_px=actual_gap, additional_cost_ms=elapsed_before_annotations,
        scene_fingerprint=scene_fingerprint, now_s=now_s, readability=readability)
    if confirmed.get('state_to_commit') is None:
        # All geometric/readability inputs are now fixed. Annotation cannot
        # repair them, and nonnegative compute cost only lowers net gain.
        # A hold therefore cannot become success by spending on discarded
        # labels/copies. A provisional success below still needs final measured
        # confirmation after compositing, including this precheck's cost.
        visual['attention'] = {**confirmed, 'proposal': proposal,
            'additional_cost_ms': elapsed_before_annotations, 'witness_visible': visible,
            'precheck_reused': bool(reused), 'aborted_before_raster': False,
            'raster_performed': bool(all(visible)), 'aborted_before_annotations': True,
            'raster_witness_supported': raster_visible, 'actual_projected_gap_px': actual_gap,
            'readability': readability, 'execution_authority': False,
            'visibility_scope': 'two_surface_witnesses_ray_triangle_and_local_depth_patch_no_xray',
            'benefit_scope': 'projected_sampling_and_two_object_localization_not_visible_gap_or_model_gain',
            'cost_scope': 'proposal_visibility_candidate_raster_and_readability_before_annotations'}
        return canvas, visual, None
    picture = Image.fromarray(color)
    annotation_meta = {'name': 'Q4 CONTACT', 'projection': 'orthographic',
                       'view_span_m': plan['view_span_m'], 'm_per_pixel': plan['view_span_m'] / (size - 1),
                       'target_object_ids': plan['target_object_ids']}
    reserved = ((0, size - (47 if size >= 256 else 55 if size >= 128 else 15), size, size)
                if label_plan is not None else None)
    _annotate(picture, meshes, view, projection, annotation_meta, owners, label_plan=label_plan,
              caption_reserved_region=reserved, defer_label_layer=label_plan is not None)
    _contact_overlay(picture, plan, proposal, pixels, annotation_meta, label_plan=label_plan)
    output = canvas.copy()
    output.paste(picture, (size, size))
    elapsed_ms = (time.perf_counter() - started) * 1000
    confirmed = confirm_attention(proposal, witness_visible=raster_visible,
        actual_projected_gap_px=actual_gap, additional_cost_ms=elapsed_ms,
        scene_fingerprint=scene_fingerprint, now_s=now_s, readability=readability)
    visual['attention'] = {**confirmed, 'proposal': proposal,
        'visibility_scope': 'two_surface_witnesses_ray_triangle_and_local_depth_patch_no_xray',
        'additional_cost_ms': elapsed_ms, 'witness_visible': visible,
        'precheck_reused': bool(reused), 'aborted_before_raster': False,
        'raster_witness_supported': raster_visible, 'actual_projected_gap_px': actual_gap,
        'readability': readability,
        'benefit_scope': 'projected_sampling_and_two_object_localization_not_visible_gap_or_model_gain',
        'cost_scope': 'proposal_visibility_candidate_raster_and_image_compositing'}
    committed = confirmed.get('state_to_commit')
    if committed is None:
        return canvas, visual, None
    if not foreground.any():
        visual['attention'].update(decision='hold', state_to_commit=None,
            reason_codes=['candidate_raster_empty'])
        return canvas, visual, None
    view_metadata = {'name': 'Q4 CONTACT', 'projection': 'orthographic',
        'target_world_m': plan['target_world_m'], 'camera_eye_world_m': eye.tolist(),
        'near_m': .08, 'far_m': far, 'view_matrix': view.tolist(),
        'projection_matrix': projection.tolist(), 'target_object_ids': plan['target_object_ids'],
        'visibility_certified': False, 'witness_visibility_confirmed': True,
        'renderer': 'clipped_orthographic_attention_surface_v1',
        'geometry_depth_pixels': int(foreground.sum()),
        'geometry_depth_fraction': float(foreground.mean()),
        'geometry_depth_statistics_stage': 'before_annotations',
        'geometry_pixels_unchanged_by_annotations': int(np.count_nonzero(
            foreground & np.all(np.asarray(picture) == color, axis=2))),
        'view_span_m': plan['view_span_m'], 'm_per_pixel': plan['view_span_m'] / (size - 1),
        'depth_mode': 'surface_z_buffer_no_xray',
        'view_scope': 'measured_contact_localization',
        'all_supplied_geometry_participates_in_depth': True,
        'occlusion_object_ids': [mesh.object_id for mesh in meshes],
        'projected_labels': annotation_meta['projected_labels'],
        'label_layout_profile': annotation_meta['label_layout_profile'],
        'object_visible_pixels': annotation_meta['object_visible_pixels'],
        'scale_bar': annotation_meta['scale_bar'],
        'measurement_overlay': annotation_meta['measurement_overlay'],
        'readability': readability,
        'labels_certify_visibility': False}
    if label_plan is not None:
        for key in ('label_layout', 'label_priority_object_ids', 'label_policy', 'label_visibility_scope'):
            view_metadata[key] = annotation_meta[key]
    visual['views'][3] = view_metadata
    visual['focus_scope'] = 'benefit_confirmed_contact_focus'
    visual['measurement_overlay'] = True
    if 'raster_schedule' in visual:
        visual['raster_schedule'].update(default_q4='skipped_after_confirmed_contact',
            final_q4='contact', canvas_complete=True)
    return output, visual, committed


__all__ = ['apply_attention_to_canvas']
