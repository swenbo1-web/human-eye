"""One gain-confirmed local surface panel for explicit missing identities.

This display-only helper keeps the original four views, pair roles, geometry
and action evidence intact. It never searches multiple cameras or hides an
occluder. A failed optional candidate returns the exact original objects.
"""
from __future__ import annotations

import copy
import math
from time import perf_counter as _monotonic_counter

import numpy as np
from PIL import Image, ImageDraw

from .attention_rendering import _visible_witness
from .scene_rendering import (_SceneRasterizer, _camera, _render_inputs, _render_view,
                              _display_snapshot_signature)
from .task_labels import task_display_label, validate_task_label_plan


MAX_LOCAL_COST_MS = 10.0
MAX_LOCAL_VIEW_SIZE = 128
MAX_FRAME_TARGETS = 3
MAX_GROUP_EXTENT_RATIO = 16.0
MIN_READABLE_PIXELS = 16
MIN_BOUNDARY_PIXELS = 4
MIN_RGB_CONTRAST = 24.0
_RECOVERABLE = frozenset({
    'no_surface_anchor_outside_navigation_overlay',
    'no_label_space_outside_navigation_overlay',
    'insufficient_surface_pixels', 'no_nonoverlapping_local_box',
})


def local_view_clock():
    """Independent monotonic seconds clock, not an interruptible deadline."""
    return _monotonic_counter()


def _projected_window(meshes, source, size):
    points = np.concatenate([m.vertices for m in meshes], axis=0)
    view = np.asarray(source['view_matrix'], dtype=np.float64)
    projection = np.asarray(source['projection_matrix'], dtype=np.float64)
    if view.shape != (4, 4) or projection.shape != (4, 4):
        return None
    clip = (projection @ view @ np.c_[points, np.ones(len(points))].T).T
    if not np.isfinite(clip).all() or not np.all(clip[:, 3] > 0):
        return None
    ndc = clip[:, :2] / clip[:, 3:]
    if not np.isfinite(ndc).all():
        return None
    pixels = np.c_[(ndc[:, 0] + 1) * (size - 1) / 2,
                   (1 - ndc[:, 1]) * (size - 1) / 2]
    lower, upper = pixels.min(axis=0), pixels.max(axis=0)
    center = pixels.mean(axis=0)
    if np.any(center < 0) or np.any(center > size - 1):
        return None
    area = float(np.prod(np.maximum(0., upper - lower)))
    window = [max(0, int(math.floor(lower[0]))), max(0, int(math.floor(lower[1]))),
              min(size, int(math.ceil(upper[0])) + 1), min(size, int(math.ceil(upper[1])) + 1)]
    return window, area


def _raw_count(view, identity):
    value = view.get('object_visible_pixels', {}).get(identity, 0)
    return value if type(value) is int and value >= 0 else 0


def _front_surface_centroid(mesh, view):
    triangles = np.asarray(mesh.vertices)[np.asarray(mesh.faces)]
    if not len(triangles):
        return None
    direction = np.asarray(view, dtype=float)[2, :3]
    edges = triangles[:, 1:] - triangles[:, :1]
    normals = np.cross(edges[:, 0], edges[:, 1])
    scale = np.linalg.norm(edges[:, 0], axis=1) * np.linalg.norm(edges[:, 1], axis=1)
    usable = np.abs(normals @ direction) > np.maximum(scale * 1e-12, 1e-30)
    if not usable.any():
        return None
    centroids = triangles[usable].mean(axis=1)
    if not np.isfinite(centroids).all():
        return None
    return centroids[int(np.argmax(centroids @ direction))]


def _glyph_survives(picture, row, expected_alias, final_pixels=None):
    box = row.get('label_box_px')
    if (type(box) is not list or len(box) != 4 or any(type(v) is not int for v in box)
            or row.get('display_label') != expected_alias):
        return False
    left, top, right, bottom = box
    if not (0 <= left < right < picture.width and 0 <= top < bottom < picture.height):
        return False
    width, height = right - left + 1, bottom - top + 1
    expected = Image.new('RGB', (width, height), (18, 22, 30))
    draw = ImageDraw.Draw(expected)
    draw.rectangle((0, 0, width - 1, height - 1), fill=(18, 22, 30), outline=(150, 145, 110))
    glyph = draw.textbbox((3, 0), expected_alias)
    if not (0 <= glyph[0] < glyph[2] <= width and 0 <= glyph[1] < glyph[3] <= height):
        return False
    draw.text((3, 0), expected_alias, fill=(255, 245, 180))
    alpha = Image.new('L', (width, height))
    ImageDraw.Draw(alpha).text((3, 0), expected_alias, fill=255)
    mask = np.asarray(alpha) > 0
    pixels = np.asarray(picture) if final_pixels is None else final_pixels
    actual = pixels[top:bottom + 1, left:right + 1]
    return bool(mask.any() and np.array_equal(actual[mask], np.asarray(expected)[mask]))


def _readable_focus(picture, raw, view, meshes, requested, plan):
    color, depth, owners = raw
    size = picture.width
    if (color.shape != (size, size, 3) or depth.shape != (size, size)
            or owners.shape != (size, size) or color.dtype != np.uint8
            or not np.issubdtype(owners.dtype, np.integer)
            or int(owners.min()) < -1 or int(owners.max()) >= len(meshes)
            or np.any((owners >= 0) & ~np.isfinite(depth))):
        raise ValueError('Local raster evidence shape differs from the delivered view')
    # Header, scale band and frame pixels cannot substantiate delivered
    # surfaces. Keep their unannotated colours out of the readability count.
    safe = np.zeros(owners.shape, dtype=bool)
    safe[17:size - 15, 1:size - 1] = True
    boundary = np.zeros(owners.shape, dtype=bool)
    for axis in (0, 1):
        first = (slice(None, -1), slice(None)) if axis == 0 else (slice(None), slice(None, -1))
        second = (slice(1, None), slice(None)) if axis == 0 else (slice(None), slice(1, None))
        difference = color[first].astype(np.int16) - color[second].astype(np.int16)
        squared_contrast = np.einsum('ijk,ijk->ij', difference, difference, dtype=np.int32)
        changed = ((owners[first] != owners[second]) & (squared_contrast >= MIN_RGB_CONTRAST ** 2)
                   & safe[first] & safe[second])
        boundary[first] |= changed
        boundary[second] |= changed
    by_id = {mesh.object_id: index for index, mesh in enumerate(meshes)}
    visible_counts = np.bincount(owners[safe & (owners >= 0)], minlength=len(meshes))
    edge_counts = np.bincount(owners[boundary & (owners >= 0)], minlength=len(meshes))
    final_pixels = np.asarray(picture)
    rows = {row['object_id']: row for row in view.get('projected_labels', [])}
    evidence, readable = [], []
    for identity in sorted(requested):
        index = by_id[identity]
        count = int(visible_counts[index])
        edges = int(edge_counts[index])
        row = rows.get(identity)
        anchor_valid = False
        glyph_valid = False
        if row is not None:
            anchor = row.get('projected_center_px')
            if (type(anchor) is list and len(anchor) == 2
                    and all(type(value) is int for value in anchor)):
                x, y = anchor
                anchor_valid = bool(1 <= x < size - 1 and 17 <= y < size - 15
                                    and int(owners[y, x]) == index and np.isfinite(depth[y, x]))
            glyph_valid = _glyph_survives(picture, row, task_display_label(identity, plan), final_pixels)
        passed = bool(count >= MIN_READABLE_PIXELS and edges >= MIN_BOUNDARY_PIXELS
                      and anchor_valid and glyph_valid)
        if passed:
            readable.append(identity)
        evidence.append({'object_id': identity, 'visible_surface_pixels': count,
            'contrasting_boundary_pixels': edges, 'anchor_exact_owner': anchor_valid,
            'complete_final_glyph': glyph_valid, 'passed': passed})
    return readable, evidence


def append_gain_local_view(canvas, metadata, meshes, *, scene_fingerprint,
                           remaining_budget_ms, diagnostic_requested=False):
    """Try one local orthographic view, append only measured readable gain.

    The supplied snapshot binding is provenance from the caller's fresh scene,
    not an independent freshness check. This never grants execution authority.
    """
    started = local_view_clock()
    receipt = {'applied': False, 'status': 'skipped', 'reason': 'not_requested',
        'attempted': False, 'candidate_raster_count': 0, 'additional_cost_ms': 0.,
        'budget_ms': 0., 'new_readable_object_ids': [], 'base_drawn_object_ids': [],
        'still_missing_ids': [], 'execution_authority': False,
        'model_quality_gain_proven': False,
        'cost_scope': 'local_selection_owned_inputs_ray_raster_readability_annotations_compositing_excludes_final_png',
        'deadline_scope': 'cooperative_checkpoints_not_interruptible_kernel_deadline'}

    def elapsed():
        return max(0., (local_view_clock() - started) * 1000.)

    def finish(reason, status='skipped'):
        receipt.update(reason=reason, status=status, additional_cost_ms=elapsed())
        return canvas, metadata, receipt

    def over_budget():
        return elapsed() >= receipt['budget_ms']

    try:
        if type(metadata) is not dict:
            return finish('invalid_canvas_metadata', 'unavailable')
        plan = metadata.get('task_labels')
        if type(plan) is not dict or not plan.get('visual_focus_object_ids'):
            return finish('no_explicit_visual_focus')
        requested = set(plan['visual_focus_object_ids'])
        views = metadata.get('views')
        if type(views) is not list or len(views) != 4:
            return finish('complete_four_view_canvas_required', 'unavailable')
        drawn = {row['object_id'] for view in views for row in view.get('projected_labels', ())}
        missing = sorted(requested - drawn)
        receipt.update(base_drawn_object_ids=sorted(requested & drawn), still_missing_ids=missing)
        if not missing:
            return finish('all_requested_identities_already_drawn')
        if diagnostic_requested:
            return finish('existing_visual_diagnostic_requested')
        if (not isinstance(scene_fingerprint, str) or not scene_fingerprint
                or plan.get('scene_fingerprint') != scene_fingerprint):
            return finish('local_scene_binding_mismatch', 'unavailable')
        size = metadata.get('quad_size')
        if type(size) is not int or not 64 <= size <= 512:
            return finish('invalid_local_quad_size', 'unavailable')
        if size < 128:
            return finish('original_view_too_small')
        if (not isinstance(canvas, Image.Image) or canvas.mode != 'RGB'
                or canvas.size != (2 * size, 2 * size)
                or metadata.get('raster_schedule', {}).get('canvas_complete', True) is not True
                or any(view.get('render_status') == 'deferred' for view in views)
                or metadata.get('supplemental_views') or metadata.get('diagnostic_panel')
                or metadata.get('natural_canvas_size')):
            return finish('complete_unextended_canvas_required', 'unavailable')
        if (type(remaining_budget_ms) not in (int, float)
                or not math.isfinite(remaining_budget_ms) or remaining_budget_ms <= 0):
            return finish('shared_local_budget_unavailable')
        receipt['budget_ms'] = min(MAX_LOCAL_COST_MS, float(remaining_budget_ms))
        if over_budget():
            return finish('local_budget_exhausted_before_selection')
        plan = validate_task_label_plan(plan, meshes,
            focal_id=plan['focal_id'], reference_id=plan['reference_id'])
        by_id = {mesh.object_id: mesh for mesh in meshes}
        candidates = []
        for view_index, source in enumerate(views):
            axes = source.get('world_axes')
            if source.get('projection') != 'orthographic' or axes not in ('XY', 'XZ'):
                continue
            coverage = source.get('label_layout', {}).get('visual_focus_coverage', {})
            reasons = {row['object_id']: row['reason'] for row in coverage.get('undrawn_objects', ())}
            eligible, tiny = [], []
            for identity in missing:
                if reasons.get(identity) in _RECOVERABLE and _raw_count(source, identity) > 0:
                    eligible.append(identity)
                elif (reasons.get(identity) == 'not_surface_visible'
                        and all(_raw_count(view, identity) == 0 for view in views)):
                    projected = _projected_window([by_id[identity]], source, size)
                    if projected is not None and projected[1] < 16.:
                        eligible.append(identity)
                        tiny.append(identity)
            if eligible:
                candidates.append((view_index, source, sorted(eligible), set(tiny)))
        if not candidates:
            return finish('no_recoverable_local_source')
        source_index, source, eligible, tiny_ids = min(candidates, key=lambda row: (-len(row[2]), row[0], row[2]))
        frame_ids = eligible[:MAX_FRAME_TARGETS]
        target_meshes = [by_id[identity] for identity in frame_ids]
        lower = np.min([mesh.bbox_min for mesh in target_meshes], axis=0)
        upper = np.max([mesh.bbox_max for mesh in target_meshes], axis=0)
        smallest_member = min(float(np.max(mesh.bbox_max - mesh.bbox_min)) for mesh in target_meshes)
        if smallest_member <= 0 or float(np.max(upper - lower)) / smallest_member > MAX_GROUP_EXTENT_RATIO:
            frame_ids = frame_ids[:1]
        target_meshes = [by_id[identity] for identity in frame_ids]
        projected = _projected_window(target_meshes, source, size)
        if projected is None:
            return finish('local_source_projection_unavailable')
        source_window = projected[0]
        receipt.update(attempted=True, source_view_index=source_index,
            source_window_px=source_window, framing_object_ids=list(frame_ids),
            source_window_convention='left_top_right_bottom_exclusive')
        if over_budget():
            return finish('local_budget_exhausted_before_camera')
        local_size = min(size, MAX_LOCAL_VIEW_SIZE)
        render_meshes, owned_by_id, _, _ = _render_inputs(meshes, local_size)
        if _display_snapshot_signature(render_meshes) != metadata.get('display_snapshot_signature'):
            return finish('current_display_snapshot_changed', 'unavailable')
        owned_targets = [owned_by_id[identity] for identity in frame_ids]
        axes = source['world_axes']
        direction = [0, 0, 1] if axes == 'XY' else [0, -1, 0]
        view, projection, view_metadata = _camera('LOCAL ' + axes, render_meshes, owned_targets,
            local_size, 'orthographic', direction, axes)
        if over_budget():
            return finish('local_budget_exhausted_before_ray')
        witness_receipts = []
        for identity in frame_ids:
            if identity not in tiny_ids:
                continue
            if over_budget():
                return finish('local_budget_exhausted_before_ray')
            witness = _front_surface_centroid(owned_by_id[identity], view)
            visible = bool(witness is not None and _visible_witness(witness, render_meshes, view,
                                                                   view_metadata['view_span_m']))
            witness_receipts.append({'object_id': identity, 'confirmed': visible,
                'point_world_m': witness.tolist() if witness is not None else None,
                'scope': 'current_front_triangle_centroid_ray_precheck_not_whole_object_visibility'})
            receipt['tiny_surface_prechecks'] = witness_receipts
            if not visible:
                return finish('tiny_surface_witness_unconfirmed')
        if over_budget():
            return finish('local_budget_exhausted_before_raster')
        view_metadata['label_priority_object_ids'] = list(plan['core_object_ids'])
        raw = []
        receipt['candidate_raster_count'] = 1
        picture = _render_view(_SceneRasterizer(local_size), render_meshes, view, projection, view_metadata,
            scope={'view_scope': 'requested_identity_local_surface_view',
                   'all_supplied_geometry_participates_in_depth': True,
                   'occlusion_object_ids': [mesh.object_id for mesh in render_meshes]},
            label_plan=plan, raw_evidence_out=raw, frame_safe_labels=True)
        if over_budget():
            return finish('local_budget_exhausted_after_raster')
        if len(raw) != 1:
            raise ValueError('Local view needs one unannotated full-scene raster receipt')
        readable, readability = _readable_focus(picture, raw[0], view_metadata,
                                               render_meshes, requested, plan)
        new_ids = sorted(set(readable) - drawn)
        receipt['readability'] = {'minimum_surface_pixels': MIN_READABLE_PIXELS,
            'minimum_contrasting_boundary_pixels': MIN_BOUNDARY_PIXELS,
            'minimum_rgb_contrast': MIN_RGB_CONTRAST, 'objects': readability,
            'scope': 'unannotated_surface_localization_and_complete_delivered_glyph_not_model_gain'}
        if not new_ids:
            return finish('no_new_readable_identity')
        if over_budget():
            return finish('local_budget_exhausted_before_append')
        output = Image.new('RGB', (canvas.width + local_size, canvas.height), (18, 22, 30))
        output.paste(canvas, (0, 0))
        output.paste(picture, (canvas.width, 0))
        draw = ImageDraw.Draw(output)
        left = canvas.width + 4
        top = local_size + 8
        region = ('lower band' if source_window[1] >= 2 * size / 3 else
                  'upper band' if source_window[3] <= size / 3 else
                  'left band' if source_window[2] <= size / 3 else
                  'right band' if source_window[0] >= 2 * size / 3 else None)
        lines = [f'Source Q{source_index + 1} {axes}']
        if region:
            lines.append(region)
        lines += [f'px ({source_window[0]},{source_window[1]})',
                  f'to ({source_window[2]},{source_window[3]})',
                  f'New labels: {len(new_ids)}', 'Surfaces; no xray']
        for index, line in enumerate(lines):
            draw.text((left, top + index * 14), line, fill=(235, 242, 255))
        if over_budget():
            return finish('local_budget_exhausted_after_compositing')
        visual = copy.deepcopy(metadata)
        view_metadata.update(readable_focus_object_ids=readable,
            panel_offset_px=[canvas.width, 0], panel_size_px=[local_size, canvas.height],
            view_size_px=[local_size, local_size], source_view_index=source_index,
            source_window_px=source_window,
            source_window_convention='left_top_right_bottom_exclusive',
            visibility_certified=False, labels_certify_visibility=False,
            execution_authority=False)
        visual['supplemental_views'] = [view_metadata]
        visual['natural_canvas_size'] = list(canvas.size)
        visual['canvas_size'] = list(output.size)
        visual['view_layout'] = metadata.get('view_layout', 'four_views') + '_with_gain_local_view'
        if over_budget():
            return finish('local_budget_exhausted_before_commit')
        receipt.update(applied=True, status='applied', reason='new_readable_visual_identity',
            new_readable_object_ids=new_ids, still_missing_ids=sorted(requested - drawn - set(readable)),
            additional_cost_ms=elapsed(), panel_offset_px=[canvas.width, 0],
            panel_size_px=[local_size, canvas.height], view_size_px=[local_size, local_size])
        return output, visual, receipt
    except Exception as exc:
        receipt['error_type'] = type(exc).__name__
        return finish('local_view_unavailable', 'unavailable')


__all__ = ['append_gain_local_view', 'local_view_clock']
