"""Adaptive four-view scene pictures, with unchanged world-space metre geometry.

Only the legacy surface depth rasterizer is reused. Its fixed cameras, contact
annotations, suggested corrections, X-ray mode and shared frame pools are not
used. Pictures are observations of supplied mesh geometry, not visibility or
clearance certificates.
"""
from __future__ import annotations

import math
import hashlib
import copy
import json
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw

from human_eye_module1_operators import MeshEntity3D, QuadCognitiveCanvasCompositor
from .geometry_safety import work_budget_status
from .task_labels import validate_task_label_plan, task_display_label


MAX_MESH_SCAN_ROWS = 262_144
MAX_SCENE_SCAN_ROWS = 1_048_576
MAX_SURFACE_LABELS = 8
MIN_SURFACE_LABEL_PIXELS = 8
MAX_OMITTED_LABEL_DIAGNOSTICS = 16
CONTEXT_LABEL_FRACTION_TARGET = .05
CONTEXT_LABEL_RISK_TRIGGER = CONTEXT_LABEL_FRACTION_TARGET
CONTEXT_LABEL_MIN_WEIGHTED_GAIN = 16.
CONTEXT_LABEL_PROFILE = 'adaptive_context_benefit_v1'
CONTACT_LABEL_PROFILE = 'local_contact_compat_v1'


class _SceneRasterizer(QuadCognitiveCanvasCompositor):
    """Use the existing depth kernel without constructing its shared PBO pools."""

    def __init__(self, quad_size):
        self.quad_size = quad_size
        self._px_centers = np.arange(quad_size, dtype=np.float64) + .5
        # The kernel expands these per-instance buffers only when necessary.
        for name in ('_f64_buf1', '_f64_buf2', '_f64_buf3'):
            setattr(self, name, np.empty(0, dtype=np.float64))
        for name in ('_i32_buf1', '_i32_buf2', '_i32_buf3', '_i32_buf4'):
            setattr(self, name, np.empty(0, dtype=np.int32))


def _bounds(meshes):
    lower = np.min([m.bbox_min for m in meshes], axis=0)
    upper = np.max([m.bbox_max for m in meshes], axis=0)
    span = upper - lower
    center = lower + span / 2
    radius = max(float(np.linalg.norm(span / 2)), 1e-8)
    if not np.isfinite(np.r_[lower, upper, center, radius]).all():
        raise ValueError('Scene extent exceeds the rendering numeric range')
    return lower, upper, center, radius


def _look_at(eye, target, up):
    # Build exact matrices here: legacy projection caches round near/far/FOV to
    # six decimals, which merges distinct very small-scale camera settings.
    forward = target - eye
    length = float(np.linalg.norm(forward))
    if not np.isfinite(length) or length == 0:
        raise ValueError('Scene coordinates cannot represent the fitted camera')
    forward /= length
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    true_up = np.cross(right, forward)
    view = np.eye(4)
    view[:3, :3] = np.array([right, true_up, -forward])
    view[:3, 3] = -view[:3, :3] @ eye
    return view


def _projection(kind, half_span, near, far, fov=None):
    projection = np.zeros((4, 4))
    if kind == 'orthographic':
        projection[0, 0] = projection[1, 1] = 1 / half_span
        projection[2, 2] = -2 / (far - near)
        projection[2, 3] = -(far + near) / (far - near)
        projection[3, 3] = 1
    else:
        factor = 1 / math.tan(fov / 2)
        projection[0, 0] = projection[1, 1] = factor
        projection[2, 2] = -(far + near) / (far - near)
        projection[2, 3] = -2 * far * near / (far - near)
        projection[3, 2] = -1
    return projection


def _camera(name, meshes, target_meshes, size, kind, direction, axes=None):
    lower, upper, center, radius = _bounds(target_meshes)
    direction = np.asarray(direction, dtype=np.float64)
    direction /= np.linalg.norm(direction)
    # The retained kernel clips at 0.08 m. Move back and narrow FOV for small
    # scenes instead of scaling vertices or pretending render units are metres.
    distance = max(radius / math.sin(math.radians(22.5)) * 1.25, .1 + radius * 2)
    # Framing a local pair must not put the camera inside a foreground object.
    front = max(float(((m.vertices - center) @ direction).max()) for m in meshes)
    distance = max(distance, front + .1)
    eye = center + direction * distance
    up = np.array([0., 1., 0.]) if axes == 'XY' else np.array([0., 0., 1.])
    view = _look_at(eye, center, up)
    scene_depth = max(float((m.vertices @ -view[2, :3] - view[2, 3]).max()) for m in meshes)
    near, far = .08, max(.081, scene_depth + max(radius, 1e-4))
    half_span = max(float((upper - lower)[list(axes_indices(axes))].max()) * .65,
                    radius * 1e-5, 1e-8) if kind == 'orthographic' else None
    fov = (2 * math.asin(min(.95, radius / distance)) * 1.25
           if kind == 'perspective' else None)
    projection = _projection(kind, half_span, near, far, fov)
    metadata = {'name': name, 'projection': kind, 'target_world_m': center.tolist(),
                'camera_eye_world_m': eye.tolist(), 'near_m': near, 'far_m': far,
                'view_matrix': view.tolist(), 'projection_matrix': projection.tolist(),
                'target_object_ids': [m.object_id for m in target_meshes],
                'visibility_certified': False, 'depth_clipping': 'near_0.08m_all_geometry_inside_far'}
    if kind == 'orthographic':
        metadata.update(world_axes=axes, view_span_m=2 * half_span,
                        m_per_pixel=2 * half_span / (size - 1))
    else:
        metadata.update(fov_y_deg=math.degrees(fov), target_plane_distance_m=distance,
                        target_plane_m_per_pixel=2 * distance * math.tan(fov / 2) / (size - 1))
    return view, projection, metadata


def axes_indices(axes):
    return (0, 1) if axes == 'XY' else (0, 2)


def stable_object_label(object_id):
    """A display identifier independent of scene enumeration or host labels."""
    return 'O' + hashlib.sha256(object_id.encode('utf-8')).hexdigest()[:8].upper()


def _display_snapshot_signature(meshes):
    """Bind an optional extra view to the exact supplied display snapshot.

    This is an internal consistency hash, not host freshness or permission.
    Hash array bytes directly instead of duplicating geometry as JSON.
    """
    digest = hashlib.sha256()
    for mesh in meshes:
        header = [mesh.object_id, mesh.mark_label, mesh.name, list(mesh.color_rgb),
                  bool(mesh.is_focal_target), mesh.axes_source, mesh.axes_confidence, mesh.axes_reason]
        encoded = json.dumps(header, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('utf-8')
        digest.update(len(encoded).to_bytes(8, 'big'));digest.update(encoded)
        for name in ('vertices', 'faces', 'edges', 'pivot_world', 'local_axes'):
            value = getattr(mesh, name)
            if value is None:
                digest.update((name + ':none').encode('ascii'));continue
            array = np.ascontiguousarray(value)
            descriptor = json.dumps([name, array.dtype.str, list(array.shape)], separators=(',', ':')).encode('ascii')
            digest.update(len(descriptor).to_bytes(8, 'big'));digest.update(descriptor)
            if array.nbytes:
                digest.update(memoryview(array).cast('B'))
    return 'sha256:' + digest.hexdigest()


def _raster_with_owners(rasterizer, meshes, view, projection, size):
    color = np.empty((size, size, 3), dtype=np.uint8)
    color[:] = (18, 22, 30)
    depth = np.full((size, size), np.inf)
    owners = np.full((size, size), -1, dtype=np.int32)
    for index, mesh in enumerate(meshes):
        # Track changes only in a conservative projected vertex rectangle.
        # The actual renderer still receives every mesh, including occluders.
        clip = (projection @ view @ np.c_[mesh.vertices, np.ones(len(mesh.vertices))].T).T
        window = (slice(0, size), slice(0, size))
        if np.isfinite(clip).all() and np.all(clip[:, 3] > 0):
            with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
                ndc = clip[:, :2] / clip[:, 3:]
                pixels = np.c_[(ndc[:, 0] + 1) * (size - 1) / 2,
                               (1 - ndc[:, 1]) * (size - 1) / 2]
            if np.isfinite(pixels).all():
                lower = np.clip(np.floor(pixels.min(axis=0)) - 2, 0, size).astype(int)
                upper = np.clip(np.ceil(pixels.max(axis=0)) + 3, 0, size).astype(int)
                window = (slice(lower[1], upper[1]), slice(lower[0], upper[0]))
        previous_depth = depth[window].copy()
        rasterizer._rasterize_meshes_zbuffer(color, depth, [mesh], view, projection,
            is_foveal_micro_view=False, foveal_xray_focus_world=None)
        owners[window][depth[window] < previous_depth] = index
    return color, depth, owners


def _label_leader_endpoint(anchor, box):
    """Join a label at its nearest edge instead of crossing to its left side."""
    x = max(box[0], min(anchor[0], box[2]))
    y = max(box[1], min(anchor[1], box[3]))
    if box[0] < anchor[0] < box[2] and box[1] < anchor[1] < box[3]:
        edges = [(anchor[0], box[1]), (anchor[0], box[3]),
                 (box[0], anchor[1]), (box[2], anchor[1])]
        return min(edges, key=lambda point: abs(point[0] - anchor[0]) + abs(point[1] - anchor[1]))
    return x, y


def _label_box_cost(foreground, box):
    """Pillow rectangles include their right and bottom boundary pixels."""
    x0, y0, x1, y1 = box
    return float(np.sum(foreground[y0:y1 + 1, x0:x1 + 1], dtype=np.float64))


def _label_penalty_map(owners, counts, size):
    # Owner -1 maps to the zero entry. One indexed image pass replaces one
    # full-image comparison/write for every object, with the same weights.
    lookup = np.zeros(len(counts) + 1, dtype=np.float32)
    lookup[1:] = np.minimum(16., np.maximum(1., size * size / (4 * np.maximum(counts, 1))))
    return lookup[owners + 1]


def _label_coverage_stats(foreground, owners, protected_indices, anchor, box, *,
                          covered=None, commit=False, endpoint=None):
    """Count one inclusive box/leader union using only its local image windows.

    The per-owner counts exclude pixels covered by earlier labels. Weighted
    foreground cost covers the whole current annotation, without counting its
    line/box intersection twice. Axis-aligned leaders need no drawing mask.
    """
    weighted = _label_box_cost(foreground, box)
    increments = [0] * len(protected_indices)

    def window(ys, xs, mask=None, *, add_weight=True):
        nonlocal weighted
        if add_weight:
            values = foreground[ys, xs]
            weighted += float(np.sum(values if mask is None else values[mask], dtype=np.float64))
        if owners is not None and protected_indices:
            fresh = mask
            if covered is not None:
                fresh = ~covered[ys, xs] if mask is None else mask & ~covered[ys, xs]
            local_owners = owners[ys, xs]
            selected = local_owners if fresh is None else local_owners[fresh]
            # One local histogram also bounds the public no-pair case where
            # the legacy priority list can contain all scene objects.
            histogram = np.bincount(selected[selected >= 0], minlength=max(protected_indices) + 1)
            for ordinal, index in enumerate(protected_indices):
                increments[ordinal] += int(histogram[index])
        if commit and covered is not None:
            if mask is None:
                covered[ys, xs] = True
            else:
                covered[ys, xs][mask] = True

    x0, y0, x1, y1 = box
    window(slice(y0, y1 + 1), slice(x0, x1 + 1), add_weight=False)
    ax, ay = anchor
    ex, ey = _label_leader_endpoint(anchor, box) if endpoint is None else endpoint
    if ay == ey:
        left, right = min(ax, ex), max(ax, ex)
        if y0 <= ay <= y1:
            for start, stop in ((left, min(right, x0 - 1)), (max(left, x1 + 1), right)):
                if start <= stop:
                    window(slice(ay, ay + 1), slice(start, stop + 1))
        else:
            window(slice(ay, ay + 1), slice(left, right + 1))
    elif ax == ex:
        top, bottom = min(ay, ey), max(ay, ey)
        if x0 <= ax <= x1:
            for start, stop in ((top, min(bottom, y0 - 1)), (max(top, y1 + 1), bottom)):
                if start <= stop:
                    window(slice(start, stop + 1), slice(ax, ax + 1))
        else:
            window(slice(top, bottom + 1), slice(ax, ax + 1))
    else:
        left, top = min(ax, ex), min(ay, ey)
        width, height = abs(ex - ax) + 1, abs(ey - ay) + 1
        line = Image.new('1', (width, height))
        ImageDraw.Draw(line).line((ax - left, ay - top, ex - left, ey - top), fill=1, width=1)
        mask = np.asarray(line, dtype=bool).copy()
        overlap = (max(0, x0 - left), max(0, y0 - top),
                   min(width, x1 - left + 1), min(height, y1 - top + 1))
        if overlap[0] < overlap[2] and overlap[1] < overlap[3]:
            mask[overlap[1]:overlap[3], overlap[0]:overlap[2]] = False
        window(slice(top, top + height), slice(left, left + width), mask)
    return weighted, increments


def _contact_label_box(draw, text, anchor, size, occupied, foreground):
    """Preserve the validated e09 local layout, including its cost semantics."""
    width = int(draw.textbbox((0, 0), text)[2]) + 6
    height = 14
    candidates = []
    offsets = [(8, -20), (8, 8), (-width - 8, -20), (-width - 8, 8),
               (8, -40), (-width - 8, 28), (18, 28), (-width - 18, -40)]
    for dx, dy in offsets:
        x = max(2, min(int(anchor[0] + dx), size - width - 2))
        y = max(19, min(int(anchor[1] + dy), size - height - 19))
        box = (x, y, x + width, y + height)
        if any(box[0] < old[2] + 2 and box[2] > old[0] - 2
               and box[1] < old[3] + 2 and box[3] > old[1] - 2 for old in occupied):
            continue
        # Compatibility deliberately keeps e09's float32 reduction and its
        # exclusive right/bottom cost slice, distinct from actual context cost.
        overlap = float(np.sum(foreground[y:y + height, x:x + width]))
        candidates.append((overlap, abs(x - anchor[0]) + abs(y - anchor[1]), box))
    return min(candidates, key=lambda item: item[:2])[2] if candidates else None


def _label_avoids_caption(anchor, box, region):
    """Protect a proven empty caption band with the actual inclusive drawing."""
    left, top, right, bottom = region
    if box[0] < right and box[2] >= left and box[1] < bottom and box[3] >= top:
        return False
    if left <= anchor[0] < right and top <= anchor[1] < bottom:
        return False
    endpoint = _label_leader_endpoint(anchor, box)
    # Ordinary owner anchors and reserved boxes are both above the band.
    if max(anchor[1], endpoint[1]) < top:
        return True
    if (max(anchor[0], endpoint[0]) < left or min(anchor[0], endpoint[0]) >= right
            or min(anchor[1], endpoint[1]) >= bottom):
        return True
    # Only a border-anchor exception needs a small band-local line mask.
    protected = Image.new('1', (right - left, bottom - top))
    ImageDraw.Draw(protected).line((anchor[0] - left, anchor[1] - top,
        endpoint[0] - left, endpoint[1] - top), fill=1, width=1)
    return protected.getbbox() is None


def _label_box(draw, text, anchor, size, occupied, foreground, *, surface_bounds=None,
               owners=None, protected_owner_indices=(), protected_visible_counts=(),
               covered=None, covered_counts=(), profile=CONTEXT_LABEL_PROFILE,
               caption_reserved_region=None):
    if profile == CONTACT_LABEL_PROFILE:
        return _contact_label_box(draw, text, anchor, size, occupied, foreground)
    width = int(draw.textbbox((0, 0), text)[2]) + 6
    height = 14
    max_y = size - height - 19
    if caption_reserved_region is not None:
        # Rectangle bottoms are inclusive; leave two clear pixel rows before
        # the original empty band's top, preserving its exact later proof.
        max_y = min(max_y, caption_reserved_region[1] - height - 3)
    candidates = []
    previous_counts = covered_counts if len(covered_counts) else (0,) * len(protected_owner_indices)
    offsets = [(8, -20), (8, 8), (-width - 8, -20), (-width - 8, 8),
               (8, -40), (-width - 8, 28), (18, 28), (-width - 18, -40)]
    positions = [(anchor[0] + dx, anchor[1] + dy) for dx, dy in offsets]
    if surface_bounds is not None:
        left, top, right, bottom = surface_bounds
        # Only four additional positions, outside this object's actual winning
        # pixels. Full-scene foreground costs still protect other objects.
        positions.extend([(anchor[0] - width // 2, top - height - 3),
                          (anchor[0] - width // 2, bottom + 3),
                          (left - width - 3, anchor[1] - height // 2),
                          (right + 3, anchor[1] - height // 2)])
    seen = set()
    for px, py in positions:
        x = max(2, min(int(px), size - width - 2))
        y = max(19, min(int(py), max_y))
        box = (x, y, x + width, y + height)
        if box in seen:
            continue
        seen.add(box)
        if any(box[0] < old[2] + 2 and box[2] > old[0] - 2
               and box[1] < old[3] + 2 and box[3] > old[1] - 2 for old in occupied):
            continue
        if caption_reserved_region is not None and not _label_avoids_caption(anchor, box, caption_reserved_region):
            continue
        weighted, increments = _label_coverage_stats(foreground, owners, protected_owner_indices,
            anchor, box, covered=covered)
        fractions = [(previous + added) / count for previous, added, count in
                     zip(previous_counts, increments, protected_visible_counts)]
        # A presentation target, not a visibility or completeness certificate.
        # Inside the target, avoid extra foreground coverage for tiny changes
        # in ratios; beyond it still choose the least excess without dropping a label.
        excess = max(0., max(fractions, default=0.) - CONTEXT_LABEL_FRACTION_TARGET)
        endpoint = _label_leader_endpoint(anchor, box)
        distance = abs(endpoint[0] - anchor[0]) + abs(endpoint[1] - anchor[1])
        candidates.append((excess, weighted, sum(fractions), distance, box))
    return min(candidates, key=lambda item: item[:4])[4] if candidates else None


def _adaptive_context_label(draw, text, anchor, size, occupied, foreground,
                            owners, counts, protected_indices, surface_pixels, *,
                            caption_reserved_region=None):
    """Keep exact legacy output unless a measured risky label has proven benefit."""
    old_box = _label_box(draw, text, anchor, size, occupied, foreground, profile=CONTACT_LABEL_PROFILE)
    if old_box is None:
        return None, None, False, False
    old_endpoint = old_box[0], old_box[1] + 7
    fallback = old_box, old_endpoint, False, False
    if not protected_indices:
        return fallback
    area = (old_box[2] - old_box[0] + 1) * (old_box[3] - old_box[1] + 1)
    line_bound = max(abs(anchor[0] - old_endpoint[0]), abs(anchor[1] - old_endpoint[1])) + 1
    minimum_visible = min(int(counts[index]) for index in protected_indices)
    if area + line_bound <= CONTEXT_LABEL_RISK_TRIGGER * minimum_visible:
        return fallback
    # A single local histogram returns every owner count. Its sum is the
    # actual foreground footprint; the protected subset needs no second scan.
    all_indices = tuple(range(len(counts)))
    old_weighted, old_owners = _label_coverage_stats(foreground, owners, all_indices,
        anchor, old_box, endpoint=old_endpoint)
    if not any(old_owners[index] / int(counts[index]) > CONTEXT_LABEL_RISK_TRIGGER
               for index in protected_indices):
        return fallback
    if old_weighted - float(foreground[anchor[1], anchor[0]]) < CONTEXT_LABEL_MIN_WEIGHTED_GAIN:
        return fallback
    xs, ys = surface_pixels
    bounds = int(xs.min()), int(ys[0]), int(xs.max()), int(ys[-1])
    new_box = _label_box(draw, text, anchor, size, occupied, foreground,
        surface_bounds=bounds, owners=owners, protected_owner_indices=protected_indices,
        protected_visible_counts=tuple(int(counts[index]) for index in protected_indices),
        profile=CONTEXT_LABEL_PROFILE, caption_reserved_region=caption_reserved_region)
    if new_box is None:
        return old_box, old_endpoint, True, False
    new_endpoint = _label_leader_endpoint(anchor, new_box)
    new_weighted, new_owners = _label_coverage_stats(foreground, owners, all_indices,
        anchor, new_box, endpoint=new_endpoint)
    if (all(new_owners[index] <= old_owners[index] for index in protected_indices)
            and sum(new_owners) <= sum(old_owners)
            and old_weighted - new_weighted >= CONTEXT_LABEL_MIN_WEIGHTED_GAIN):
        return new_box, new_endpoint, True, True
    return old_box, old_endpoint, True, False


def _draw_label_layer(draw, rows):
    for row in rows:
        box = row['label_box_px']
        draw.rectangle(box, fill=(18, 22, 30), outline=(150, 145, 110))
        draw.text((box[0] + 3, box[1]), row.get('display_label', row['stable_label']), fill=(255, 245, 180))


def _annotate(image, meshes, view, projection, metadata, owners, *, caption_reserved_region=None,
              label_plan=None, defer_label_layer=False, navigation_reserved_region=None,
              frame_safe_labels=False):
    """Label only actual winning depth pixels; labels remain annotations."""
    size = image.width
    draw = ImageDraw.Draw(image)
    contact_view = metadata['name'] == 'Q4 CONTACT'
    contact_compat = contact_view and label_plan is None
    profile = CONTACT_LABEL_PROFILE if contact_compat else CONTEXT_LABEL_PROFILE
    metadata['label_layout_profile'] = profile
    if label_plan is not None:
        metadata['label_layout_profile'] = 'task_focus_compact_v1'
    anchors, occupied, omitted = [], [], []
    omitted_count, omitted_reason_counts = 0, {}
    optimizer_attempts, optimizer_applied = 0, 0
    visual_focus = set(label_plan['visual_focus_object_ids']) if label_plan is not None else set()
    # Requested core identities need the same delivery receipts as related
    # ones, but do not opt the existing pair into a different layout.
    focus_layout = bool(visual_focus - set(label_plan['core_object_ids'])) if label_plan is not None else False
    visual_omissions = {}
    focus_endpoint_adjustments = 0
    reserved_region = navigation_reserved_region
    reserved_kind = 'navigation_overlay'
    if reserved_region is None and frame_safe_labels:
        reserved_region = (0, size - 15, size, size)
        reserved_kind = 'frame_overlay'

    def record_omission(identity, reason):
        nonlocal omitted_count
        omitted_count += 1
        omitted_reason_counts[reason] = omitted_reason_counts.get(reason, 0) + 1
        if identity in visual_focus:
            # At most six entries, independent of the general diagnostic cap.
            visual_omissions[identity] = reason
        if len(omitted) < MAX_OMITTED_LABEL_DIAGNOSTICS:
            omitted.append({'object_id': identity, 'reason': reason})

    foreground = owners >= 0
    counts = np.bincount(owners[foreground], minlength=len(meshes))
    # Protect small visible objects more than large background surfaces when
    # no completely empty label location exists; keep leaders local.
    # Build the weight image only when a usable label reaches layout. Fully
    # occluded/request-excluded surfaces still need their omission receipts,
    # but never consume this full-image array.
    label_penalty = None
    # Camera targets define framing, which may include the whole scene. Label
    # priority instead follows the caller's pair. CONTACT supplies its own
    # actual attention pair through target_object_ids when no override exists.
    priority_ids = list(metadata.get('label_priority_object_ids', metadata['target_object_ids']))
    active_ids = None
    if label_plan is not None:
        # The task pair keeps A/B everywhere. A contact close-up can focus a
        # different pair; it gets those objects' existing aliases, never a new B.
        priority_ids = (list(metadata['target_object_ids']) if contact_view else
                        label_plan['core_object_ids'] + label_plan['related_object_ids'])
        active_ids = set(priority_ids)
    priority_rank = {identity: rank for rank, identity in enumerate(priority_ids)}
    protected_ids = set(metadata.get('label_protected_object_ids', priority_ids)) if not contact_compat else set()
    if label_plan is not None:
        protected_ids = set(metadata['target_object_ids'] if contact_view else label_plan['core_object_ids'])
    owner_indices = {mesh.object_id: index for index, mesh in enumerate(meshes)}
    protected_indices = tuple(owner_indices[identity] for identity in sorted(protected_ids)
                              if identity in owner_indices and counts[owner_indices[identity]] > 0)
    ranked = sorted(range(len(meshes)), key=lambda index:
                    (priority_rank.get(meshes[index].object_id, len(priority_ids)),
                     -counts[index], meshes[index].object_id))
    metadata['object_visible_pixels'] = {mesh.object_id: int(counts[index]) for index, mesh in enumerate(meshes)}
    for index in ranked:
        mesh = meshes[index]
        reason = ('not_surface_visible' if counts[index] == 0 else
                  'insufficient_surface_pixels' if counts[index] < MIN_SURFACE_LABEL_PIXELS else
                  'view_too_small' if size < 96 else
                  'outside_task_label_focus' if active_ids is not None and mesh.object_id not in active_ids else
                  'label_budget_exhausted' if len(anchors) >= MAX_SURFACE_LABELS else None)
        if reason is not None:
            record_omission(mesh.object_id, reason)
            continue
        ys, xs = np.nonzero(owners == index)
        if label_plan is not None and contact_view and caption_reserved_region is not None:
            # The later measurement band covers these pixels. Choose an
            # anchor that will remain in the surface view, never inside it.
            usable = (ys >= 19) & (ys < caption_reserved_region[1])
            xs, ys = xs[usable], ys[usable]
            if len(xs) < MIN_SURFACE_LABEL_PIXELS:
                record_omission(mesh.object_id, 'no_surface_anchor_outside_caption')
                continue
        center = np.array([np.mean(xs), np.mean(ys)])
        nearest = int(np.argmin((xs - center[0]) ** 2 + (ys - center[1]) ** 2))
        anchor = [int(xs[nearest]), int(ys[nearest])]
        if reserved_region is not None and not (17 <= anchor[1] < reserved_region[1]):
            # Navigation text is opaque presentation, not empty geometry.
            # Choose a current depth winner outside its band, never retain a
            # pixel that the delivered map necessarily paints over.
            # Title ends at inclusive row 16; label boxes still keep their
            # existing row-19 margin, but a genuine surface anchor at row 17
            # is safe and must not be discarded just for that text margin.
            usable = (ys >= 17) & (ys < reserved_region[1])
            xs, ys = xs[usable], ys[usable]
            if len(xs) < MIN_SURFACE_LABEL_PIXELS:
                record_omission(mesh.object_id, 'no_surface_anchor_outside_' + reserved_kind)
                continue
            center = np.array([np.mean(xs), np.mean(ys)])
            nearest = int(np.argmin((xs - center[0]) ** 2 + (ys - center[1]) ** 2))
            anchor = [int(xs[nearest]), int(ys[nearest])]
        label = (task_display_label(mesh.object_id, label_plan) if label_plan is not None
                 else stable_object_label(mesh.object_id))
        if label_penalty is None:
            # The checks above establish size >= 96 and sufficient surface
            # pixels. All layouts in this view share the identical weight map.
            label_penalty = _label_penalty_map(owners, counts, size)
        if contact_compat:
            box = _label_box(draw, label, anchor, size, occupied, label_penalty, profile=CONTACT_LABEL_PROFILE)
            endpoint = (box[0], box[1] + 7) if box is not None else None
            applied = False
        elif label_plan is not None and contact_view and caption_reserved_region is not None:
            box = _label_box(draw, label, anchor, size, occupied, label_penalty,
                surface_bounds=(int(xs.min()), int(ys[0]), int(xs.max()), int(ys[-1])),
                owners=owners, protected_owner_indices=protected_indices,
                protected_visible_counts=tuple(int(counts[i]) for i in protected_indices),
                caption_reserved_region=caption_reserved_region)
            endpoint = _label_leader_endpoint(anchor, box) if box is not None else None
            applied = box is not None
            optimizer_attempts += 1
            optimizer_applied += int(applied)
        else:
            box, endpoint, attempted, applied = _adaptive_context_label(draw, label, anchor,
                size, occupied, label_penalty, owners, counts, protected_indices, (xs, ys),
                caption_reserved_region=(reserved_region if reserved_region is not None
                                         else caption_reserved_region))
            optimizer_attempts += int(attempted)
            optimizer_applied += int(applied)
        if box is None:
            record_omission(mesh.object_id, 'no_nonoverlapping_local_box')
            continue
        if reserved_region is not None and not _label_avoids_caption(anchor, box, reserved_region):
            # Compatibility's initial local box can ignore a reserved band.
            # Relocate only that conflicting result; if no legal local box
            # exists, its delivery receipt must explicitly remain undrawn.
            box = _label_box(draw, label, anchor, size, occupied, label_penalty,
                surface_bounds=(int(xs.min()), int(ys[0]), int(xs.max()), int(ys[-1])),
                owners=owners, protected_owner_indices=protected_indices,
                protected_visible_counts=tuple(int(counts[i]) for i in protected_indices),
                caption_reserved_region=reserved_region)
            optimizer_attempts += 1
            if box is None:
                record_omission(mesh.object_id, 'no_label_space_outside_' + reserved_kind)
                continue
            endpoint = _label_leader_endpoint(anchor, box)
            optimizer_applied += 1
            applied = True
        if focus_layout and not contact_view:
            # A short alias can change the old left-corner leader's slope.
            # Use its nearest edge only after exact current-owner coverage
            # proves no per-core or total-foreground increase.
            local_endpoint = _label_leader_endpoint(anchor, box)
            if local_endpoint != endpoint:
                all_indices = tuple(range(len(meshes)))
                old_cost, old_counts = _label_coverage_stats(label_penalty, owners, all_indices,
                    anchor, box, endpoint=endpoint)
                new_cost, new_counts = _label_coverage_stats(label_penalty, owners, all_indices,
                    anchor, box, endpoint=local_endpoint)
                if (new_cost <= old_cost and sum(new_counts) <= sum(old_counts)
                        and all(new_counts[i] <= old_counts[i] for i in protected_indices)):
                    endpoint = local_endpoint
                    focus_endpoint_adjustments += 1
        occupied.append(box)
        draw.line((anchor[0], anchor[1], endpoint[0], endpoint[1]), fill=(245, 218, 135), width=1)
        if contact_compat:
            draw.rectangle(box, fill=(18, 22, 30), outline=(150, 145, 110))
            draw.text((box[0] + 3, box[1]), label, fill=(255, 245, 180))
        row = {'object_id': mesh.object_id, 'mark_label': mesh.mark_label,
                        'stable_label': stable_object_label(mesh.object_id) if label_plan is not None else label,
                        'projected_center_px': anchor,
                        'label_box_px': list(box), 'surface_visible_pixels': int(counts[index]),
                        'anchor_source': 'current_full_scene_depth_winner'}
        if label_plan is not None:
            row['display_label'] = label
        if applied or (focus_layout and not contact_view):
            row['leader_endpoint_px'] = list(endpoint)
        anchors.append(row)
    if not contact_compat and not defer_label_layer:
        # Placement depends on depth owners and occupied boxes, not these
        # pixels. Put the bounded label layer above every context leader so a
        # later object's line cannot overwrite an earlier object's identifier.
        # Boxes, anchors and the inclusive annotation footprint stay unchanged.
        _draw_label_layer(draw, anchors)
    draw.rectangle((0, 0, size - 1, 16), fill=(28, 34, 46))
    draw.text((3, 1), metadata['name'], fill=(235, 242, 255))
    # The bar is a constant scale only for the orthographic views.
    if metadata['projection'] == 'orthographic':
        bar_px = max(8, size // 4)
        length_m = bar_px * metadata['m_per_pixel']
        draw.rectangle((0, size - 15, size - 1, size - 1), fill=(18, 22, 30))
        draw.line((4, size - 4, 4 + bar_px, size - 4), fill=(225, 230, 240), width=2)
        draw.text((4, size - 15), f'{length_m:.3g} m', fill=(235, 242, 255))
        metadata['scale_bar'] = {'pixels': bar_px, 'length_m': length_m}
    metadata['projected_labels'] = anchors
    metadata['label_priority_object_ids'] = priority_ids
    metadata['label_layout'] = {
        'policy': 'explicit_priority_then_visible_surface_pixels_then_object_id',
        'max_labels': MAX_SURFACE_LABELS,
        'minimum_surface_pixels': MIN_SURFACE_LABEL_PIXELS,
        'eligible_object_count': int(np.count_nonzero(counts >= MIN_SURFACE_LABEL_PIXELS)),
        'displayed_label_count': len(anchors),
        'optimizer_attempts': optimizer_attempts, 'optimizer_applied': optimizer_applied,
        'omitted_object_count': omitted_count,
        'omitted_reason_counts': omitted_reason_counts,
        'omitted_objects': omitted,
        'omitted_objects_truncated': omitted_count - len(omitted),
        'scope': 'annotation_layout_only_not_visibility_or_execution_authority'}
    metadata['label_policy'] = 'stable_object_id_digest_visible_surface_anchors_nonoverlapping_boxes'
    if label_plan is not None:
        metadata['label_policy'] = 'task_core_and_related_visible_surfaces_with_observation_wide_aliases'
        metadata['label_layout'].update(max_labels=len(priority_ids),
            policy='task_pair_or_contact_pair_then_related_stable_identity',
            task_focus_object_ids=list(priority_ids))
        if visual_focus:
            drawn = {row['object_id'] for row in anchors}
            metadata['label_layout']['visual_focus_endpoint_adjustments'] = focus_endpoint_adjustments
            metadata['label_layout']['visual_focus_coverage'] = {
                'drawn_object_ids': sorted(visual_focus & drawn),
                'undrawn_objects': [{'object_id': identity, 'reason': visual_omissions[identity]}
                                    for identity in sorted(visual_focus - drawn)],
                'scope': 'current_sampled_surface_labels_not_whole_object_visibility'}
    if navigation_reserved_region is not None:
        metadata['label_layout']['navigation_reserved_region_px'] = list(navigation_reserved_region)
    elif frame_safe_labels:
        metadata['label_layout']['frame_reserved_region_px'] = list(reserved_region)
    metadata['label_visibility_scope'] = 'sampled_surface_pixels_only_not_whole_object_visibility'
    metadata['labels_certify_visibility'] = False
    draw.rectangle((0, 0, size - 1, size - 1), outline=(70, 82, 105))


def _task_label_coverage_summary(metadata):
    """Compact display-selection evidence; never claim complete scene risks.

    CONTACT can show a pair outside the natural-view selection. Report plan
    selection counts separately from actual requested-label delivery so its
    extra object cannot be mistaken for a missing or certified risk.
    """
    plan = metadata.get('task_labels')
    if plan is None:
        return None
    selected = plan['related_object_ids']
    known_penetrations = plan['candidate_reason_counts'].get('known_penetration', 0)
    selected_penetrations = sum(reason == 'known_penetration' for reason in plan['related_reasons'].values())
    visual_focus = set(plan['visual_focus_object_ids'])
    base_drawn = {row['object_id'] for view in metadata['views']
                  for row in view.get('projected_labels', ())}
    local_readable = set()
    for view in metadata.get('supplemental_views', ()):
        # Supplementary labels count only after the local-view readability
        # gate, not merely because an annotation was attempted or painted.
        actual = {row['object_id'] for row in view.get('projected_labels', ())}
        local_readable.update(set(view.get('readable_focus_object_ids', ())) & actual & visual_focus)
    drawn = base_drawn | local_readable
    missing = sorted(visual_focus - drawn)
    unselected = plan['related_candidate_count'] - len(selected)
    summary = {
        'scope': 'display_of_existing_task_evidence_not_complete_scene_risk_scan',
        'execution_authority': False,
        'selection_mode': 'explicit_visual_focus' if visual_focus else 'pair_context',
        'related_candidate_count': plan['related_candidate_count'],
        'selected_related_count': len(selected),
        'unselected_related_count': unselected,
        'known_penetration_candidate_count': known_penetrations,
        'unselected_known_penetration_count': known_penetrations - selected_penetrations,
        'visual_focus_count': len(visual_focus),
        'visual_focus_drawn_count': len(visual_focus & drawn),
        'visual_focus_not_drawn_ids': missing,
        'per_view_focus_evidence': 'canvas.views[].label_layout.visual_focus_coverage',
        'supplement_query_field': 'query.label_object_ids',
        'supplement_max_object_ids': 6,
    }
    if metadata.get('supplemental_views'):
        summary.update(natural_visual_focus_drawn_count=len(visual_focus & base_drawn),
            natural_visual_focus_not_drawn_ids=sorted(visual_focus - base_drawn),
            new_local_readable_object_ids=sorted(local_readable - base_drawn),
            supplemental_focus_evidence='canvas.supplemental_views[].readable_focus_object_ids')
    refilled = {row['object_id'] for view in metadata['views']
                for row in view.get('projected_labels', ())
                if row.get('display_source') == 'visible_candidate_refill'}
    if refilled:
        summary.update(refilled_related_object_ids=sorted(refilled),
            drawn_originally_selected_related_count=len(set(selected) & base_drawn),
            actual_default_related_drawn_count=len((set(selected) & base_drawn) | refilled),
            original_priority_selection_preserved=True,
            refill_scope='empty_global_default_slots_existing_CONTACT_exception_separate',
            refill_evidence='label_refill')
    return summary


def _navigation(image, meshes, focus, view, projection, metadata):
    """Coordinate map glyphs are explicitly separate from surface evidence."""
    draw, size = ImageDraw.Draw(image), image.width
    positions = []
    for mesh in meshes:
        clip = projection @ view @ np.r_[mesh.aabb_center, 1.]
        ndc = clip[:3] / clip[3]
        if not np.isfinite(ndc).all() or np.any(np.abs(ndc[:2]) > 1):
            continue
        x, y = (int(round((ndc[0] + 1) * (size - 1) / 2)),
                int(round((1 - ndc[1]) * (size - 1) / 2)))
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), outline=(170, 180, 192))
        positions.append({'object_id': mesh.object_id, 'position_px': [x, y]})
    bounds = np.array([_bounds(focus)[0], _bounds(focus)[1]])
    corners = np.array([[x, y, bounds[0, 2], 1.] for x in bounds[:, 0] for y in bounds[:, 1]])
    clip = (projection @ view @ corners.T).T
    xy = clip[:, :2] / clip[:, 3:]
    pixels = np.c_[(xy[:, 0] + 1) * (size - 1) / 2, (1 - xy[:, 1]) * (size - 1) / 2]
    center = pixels.mean(axis=0)
    half = np.maximum((pixels.max(axis=0) - pixels.min(axis=0)) / 2, 4.)
    box = [int(center[0] - half[0]), int(center[1] - half[1]),
           int(center[0] + half[0]), int(center[1] + half[1])]
    draw.rectangle(box, outline=(255, 207, 88), width=2)
    if size >= 128:
        draw.rectangle((0, size - 43, size - 1, size - 16), fill=(18, 22, 30))
        first = 'MAP: positions, not visible surfaces' if size >= 256 else 'MAP: positions only'
        second = 'Gold box: workspace (minimum marker)' if size >= 256 else 'See work views'
        draw.text((4, size - 43), first, fill=(215, 222, 235))
        draw.text((4, size - 30), second, fill=(255, 207, 88))
    metadata.update(navigation={'scope': 'object_positions_not_visible_surfaces',
        'position_count': len(positions), 'positions': positions, 'workspace_marker_px': box,
        'workspace_marker_minimum_size_px': 8, 'workspace_marker_is_exact_extent': False},
        surface_readability='insufficient_at_global_scale_use_workspace_views')


def _render_inputs(meshes, quad_size):
    if type(quad_size) is not int or not 64 <= quad_size <= 512:
        raise ValueError('quad_size must be an integer in 64..512')
    if not isinstance(meshes, (list, tuple)) or not 1 <= len(meshes) <= 256:
        raise ValueError('Rendering requires 1..256 meshes')
    if any(not isinstance(mesh, MeshEntity3D) for mesh in meshes):
        raise TypeError('Rendering requires MeshEntity3D instances')
    budget = work_budget_status(meshes, purpose='render')
    scan_rows = [len(mesh.faces) * quad_size for mesh in meshes]
    if (not budget['within_budget'] or max(scan_rows) > MAX_MESH_SCAN_ROWS
            or sum(scan_rows) > MAX_SCENE_SCAN_ROWS):
        raise ValueError('Rendering resource budget exceeded; geometry must not be silently simplified')
    # Fresh meshes own projection/shading caches; callers retain original data.
    render_meshes = [MeshEntity3D.from_dict(mesh.to_dict()) for mesh in meshes]
    by_id = {m.object_id: m for m in render_meshes}
    if len(by_id) != len(render_meshes):
        raise ValueError('Rendering requires unique object IDs')
    return render_meshes, by_id, budget, scan_rows


def _empty_caption_region(depth, owners, metadata, size):
    """Return a conservative interior band using this view's existing raster.

    Surface ownership, rather than RGB, protects geometry even if its colour
    matches the background. Annotation boxes and leaders are protected as
    drawn, including their background-coloured pixels. No second raster is
    needed, and an occupied band simply has no caption layout.
    """
    if (not 256 <= size <= 512 or metadata.get('name') != 'Q4 TARGET'
            or metadata.get('projection') != 'perspective'):
        return None
    left, top, right, bottom = 1, size - 29, size - 1, size - 1
    window = (slice(top, bottom), slice(left, right))
    if np.any(np.isfinite(depth[window])) or np.any(owners[window] >= 0):
        return None
    labels = metadata.get('projected_labels', ())
    if not labels:
        return left, top, right, bottom
    protected = Image.new('1', (right - left, bottom - top))
    draw = ImageDraw.Draw(protected)
    for label in labels:
        x0, y0, x1, y1 = label['label_box_px']
        anchor = label['projected_center_px']
        endpoint = label.get('leader_endpoint_px', (x0, y0 + 7))
        draw.rectangle((x0 - left, y0 - top, x1 - left, y1 - top), fill=1)
        draw.line((anchor[0] - left, anchor[1] - top,
                   endpoint[0] - left, endpoint[1] - top), fill=1, width=1)
    if protected.getbbox() is not None:
        return None
    # The top title and all four border lines are outside this interior band.
    return left, top, right, bottom


def _render_view(rasterizer, meshes, view, projection, metadata, navigation_focus=None, scope=None,
                 caption_region_out=None, label_plan=None, raw_evidence_out=None,
                 frame_safe_labels=False, raw_observer=None):
    """Render one view with the full supplied occlusion geometry."""
    size = rasterizer.quad_size
    color, depth, owners = _raster_with_owners(rasterizer, meshes, view, projection, size)
    if raw_evidence_out is not None:
        # Only the optional local candidate requests this operation-local
        # evidence. Own immutable copies keep annotation pixels out of its
        # visibility/readability test; ordinary views take no copy.
        raw = tuple(array.copy() for array in (color, depth, owners))
        for array in raw:
            array.setflags(write=False)
        raw_evidence_out.append(raw)
    foreground = np.isfinite(depth)
    metadata['geometry_depth_pixels'] = int(np.count_nonzero(foreground))
    metadata['geometry_depth_fraction'] = float(np.mean(foreground))
    metadata['depth_range_m'] = ([float(depth[foreground].min()), float(depth[foreground].max())]
                                if foreground.any() else None)
    metadata.update(scope or {})
    picture = Image.fromarray(color, mode='RGB')
    # Reserve only a band proved empty by this same current raster. This is
    # layout input, never a JSON authorization or a replacement for the final
    # depth-and-drawn-annotation caption check below.
    caption_region = _empty_caption_region(depth, owners,
        {'name': metadata['name'], 'projection': metadata['projection']}, size)
    navigation_region = None
    if navigation_focus is not None:
        # Map markers and workspace outlines are background to identifiers.
        # Keep their opaque explanation band reserved, then draw label glyphs
        # last so metadata describes text actually delivered in the PNG.
        _navigation(picture, meshes, navigation_focus, view, projection, metadata)
        navigation_region = ((0, size - 43, size, size - 15) if size >= 128 else
                             (0, size - 15, size, size))
    _annotate(picture, meshes, view, projection, metadata, owners,
              caption_reserved_region=caption_region, label_plan=label_plan,
              navigation_reserved_region=navigation_region, frame_safe_labels=frame_safe_labels)
    metadata['geometry_depth_statistics_stage'] = 'before_annotations'
    metadata['geometry_pixels_unchanged_by_annotations'] = int(np.count_nonzero(
        foreground & np.all(np.asarray(picture) == color, axis=2)))
    if caption_region_out is not None:
        caption_region_out.append(_empty_caption_region(depth, owners, metadata, size))
    if raw_observer is not None:
        # Optional internal display recovery borrows this operation's fresh
        # preannotation arrays. No raw evidence is put in JSON or state.
        raw_observer(picture, metadata, meshes, color, depth, owners)
    return picture


def _render_scene_canvas_impl(meshes, quad_size, *, focal_id=None, reference_id=None,
                              defer_q4=False, prepared_fingerprint=None, label_plan=None,
                              raw_observer=None):
    """Return (PIL RGB image, JSON-compatible visual evidence metadata).

    Compact scenes retain three overview views. Dispersed scenes use a global
    navigation map and two work-area views. Q4 fits the requested pair, one
    focal mesh, or the scene when no target is known. All scene meshes
    participate in depth rasterization, including possible occluders. No
    collision probe is run, and no VLM token estimate or complete-visibility
    promise is generated.

    The internal ``defer_q4`` opt-in leaves Q4 unrendered, with its fitted
    camera retained for a possible attention replacement. Such a canvas must
    receive confirmed CONTACT pixels or pass through ``finalize_scene_q4``
    before delivery. The public default returns the same complete four views.
    """
    if type(defer_q4) is not bool:
        raise ValueError('defer_q4 must be a boolean')
    render_meshes, by_id, budget, scan_rows = _render_inputs(meshes, quad_size)
    for identity in (focal_id, reference_id):
        if identity is not None and identity not in by_id:
            raise ValueError('Unknown rendering target object')
    if focal_id is not None and focal_id == reference_id:
        raise ValueError('Focal and reference must differ')
    if label_plan is not None:
        label_plan = validate_task_label_plan(label_plan, render_meshes,
            focal_id=focal_id, reference_id=reference_id)
        if prepared_fingerprint is not None and label_plan['scene_fingerprint'] != prepared_fingerprint:
            raise ValueError('Task labels belong to a different current snapshot')
    lower, upper, _, _ = _bounds(render_meshes)
    focus = ([by_id[focal_id]] + ([by_id[reference_id]] if reference_id else [])
             if focal_id else render_meshes)
    scene_radius, focus_radius = _bounds(render_meshes)[3], _bounds(focus)[3]
    layered = bool(focal_id and scene_radius > focus_radius * 4)
    plans = [('Q1 XY TOP', 'orthographic', [0, 0, 1], 'XY', render_meshes),
             ('Q2 XZ FRONT', 'orthographic', [0, -1, 0], 'XZ', render_meshes),
             ('Q3 SCENE', 'perspective', [2.4, -3.2, 2.4], None, render_meshes),
             ('Q4 TARGET', 'perspective', [2.4, -3.2, 2.4], None, focus)]
    if layered:
        plans[:3] = [('Q1 NAV XY', 'orthographic', [0, 0, 1], 'XY', render_meshes),
                     ('Q2 WORK XY', 'orthographic', [0, 0, 1], 'XY', focus),
                     ('Q3 WORK XZ', 'orthographic', [0, -1, 0], 'XZ', focus)]
    rasterizer = _SceneRasterizer(quad_size)
    canvas = Image.new('RGB', (quad_size * 2, quad_size * 2))
    views = []
    for index, (name, kind, direction, axes, targets) in enumerate(plans):
        view, projection, metadata = _camera(name, render_meshes, targets, quad_size, kind, direction, axes)
        metadata['label_priority_object_ids'] = [identity for identity in (focal_id, reference_id)
                                                  if identity is not None]
        scope = dict(view_scope=('coordinate_navigation' if layered and index == 0 else
            'target_workspace' if layered and index in (1, 2) else
            'target_pair' if index == 3 and focal_id else 'whole_scene'),
            occlusion_object_ids=[mesh.object_id for mesh in render_meshes],
            all_supplied_geometry_participates_in_depth=True)
        if defer_q4 and index == 3:
            metadata.update(scope)
            metadata['render_status'] = 'deferred'
        else:
            observer_args = ({'raw_observer': lambda *parts, i=index: raw_observer(i, *parts)}
                             if raw_observer is not None and index < 3 else {})
            picture = _render_view(rasterizer, render_meshes, view, projection, metadata,
                                   focus if layered and index == 0 else None, scope, label_plan=label_plan,
                                   **observer_args)
            canvas.paste(picture, ((index % 2) * quad_size, (index // 2) * quad_size))
        views.append(metadata)
    metadata = {'renderer': 'adaptive_world_metre_surface_raster_v1', 'unit': 'm',
                'coordinate_frame': 'world', 'geometry_scaled': False,
                'scene_bbox_min_m': lower.tolist(), 'scene_bbox_max_m': upper.tolist(),
                'quad_size': quad_size, 'canvas_size': [quad_size * 2, quad_size * 2],
                'scope': 'known_mesh_geometry_four_views', 'visibility_certified': False,
                'depth_mode': 'surface_z_buffer_no_xray',
                'view_layout_version': 'layered-four-view-v2-20261023',
                'view_layout': 'navigation_workspace_target' if layered else 'scene_overview_target',
                'stable_label_source': 'sha256_full_object_id_prefix_8',
                'object_labels': [{'object_id': mesh.object_id, 'stable_label': stable_object_label(mesh.object_id),
                                   'host_mark_label': mesh.mark_label} for mesh in render_meshes],
                'focus_scope': 'target_pair_focus' if focal_id and reference_id else
                               'single_target_focus' if focal_id else 'whole_scene_focus',
                'measurement_overlay': False, 'action_prescription_overlay': False, 'views': views}
    metadata['work_budget'] = budget
    if label_plan is not None:
        metadata['task_labels'] = label_plan
        if label_plan['visual_focus_object_ids']:
            metadata['display_snapshot_signature'] = _display_snapshot_signature(render_meshes)
        for row in metadata['object_labels']:
            row['display_label'] = task_display_label(row['object_id'], label_plan)
    metadata['raster_scan_row_upper_bound'] = {'per_mesh_max': max(scan_rows), 'scene_total': sum(scan_rows),
                                             'per_mesh_limit': MAX_MESH_SCAN_ROWS,
                                             'scene_limit': MAX_SCENE_SCAN_ROWS}
    if defer_q4:
        metadata['raster_schedule'] = {'default_q4': 'deferred', 'final_q4': 'pending',
                                       'canvas_complete': False}
    if prepared_fingerprint is not None:
        prepared = _PreparedSceneRender(_PREPARED_RENDER_KEY, render_meshes, canvas,
                                        metadata, prepared_fingerprint)
        return canvas, metadata, prepared
    return canvas, metadata


def render_scene_canvas(meshes: Sequence[MeshEntity3D], quad_size: int = 128, *,
                        focal_id: str | None = None, reference_id: str | None = None,
                        defer_q4: bool = False, label_plan=None):
    """Return the compatible complete canvas, or explicitly defer Q4.

    All supplied geometry still participates in depth. Callers opting into
    ``defer_q4`` must apply confirmed CONTACT or finalize before delivery.
    """
    return _render_scene_canvas_impl(meshes, quad_size, focal_id=focal_id,
                                    reference_id=reference_id, defer_q4=defer_q4, label_plan=label_plan)


_PREPARED_RENDER_KEY = object()


def _render_metadata_binding(metadata):
    if type(metadata) is not dict:
        raise ValueError('Prepared render metadata must be an ordinary dictionary')
    # Optional attention diagnostics are added by an independent candidate
    # renderer, including on hold. Every supplied camera/geometry claim and
    # the incomplete schedule itself must otherwise remain exactly bound.
    return {key: value for key, value in metadata.items() if key != 'attention'}


class _PreparedSceneRender:
    """Operation-local render inputs; not a cache or scene authority.

    No object is put in output metadata or persistent state. The fingerprint
    is supplied only by the internal caller's current full-scene validation,
    never treated as proof supplied by an external connector. Mesh copies
    belong to this operation, and ordinary Pillow mutations detach the
    read-only original image core, invalidating its cheap identity binding.
    """
    __slots__ = ('__meshes', '__canvas', '__core', '__size', '__metadata',
                 '__fingerprint', '__consumed', '__caption_region', '__attention_claimed')

    def __init__(self, key, meshes, canvas, metadata, fingerprint):
        if key is not _PREPARED_RENDER_KEY:
            raise TypeError('Prepared render inputs are created only by rendering')
        for mesh in meshes:
            for name in ('vertices', 'faces', 'edges', 'pivot_world', 'local_axes', 'bbox_min', 'bbox_max', 'color_rgb'):
                value = getattr(mesh, name, None)
                if isinstance(value, np.ndarray):
                    value.setflags(write=False)
        canvas.readonly = 1
        for name, value in (
            ('__meshes', tuple(meshes)), ('__canvas', canvas), ('__core', canvas.im),
            ('__size', metadata['quad_size']),
            ('__metadata', copy.deepcopy(_render_metadata_binding(metadata))),
            ('__fingerprint', fingerprint), ('__consumed', False), ('__caption_region', None),
            ('__attention_claimed', False),
        ):
            object.__setattr__(self, '_PreparedSceneRender' + name, value)

    def __setattr__(self, name, value):
        raise AttributeError('Prepared render inputs cannot be reassigned')

    def __copy__(self):
        raise TypeError('Prepared render inputs cannot be copied or persisted')

    def __deepcopy__(self, memo):
        raise TypeError('Prepared render inputs cannot be copied or persisted')

    def __reduce_ex__(self, protocol):
        raise TypeError('Prepared render inputs cannot be copied or persisted')

    def _attention_matches(self, canvas, metadata, meshes, fingerprint):
        """Check current pending inputs without treating a fingerprint as proof."""
        if (self.__consumed or type(fingerprint) is not str
                or fingerprint != self.__fingerprint
                or canvas is not self.__canvas or canvas.im is not self.__core
                or not canvas.readonly or canvas.mode != 'RGB'
                or canvas.size != (self.__size * 2, self.__size * 2)
                or not isinstance(meshes, (list, tuple)) or len(meshes) != len(self.__meshes)):
            return False
        try:
            if _render_metadata_binding(metadata) != self.__metadata:
                return False
            # Preserve enumeration as well as all inputs used by the camera,
            # rays, raster, policy and labels. Copies here are the already
            # operation-owned render snapshot, not a new geometry cache.
            arrays = ('vertices', 'faces', 'edges', 'pivot_world', 'local_axes')
            scalars = ('object_id', 'mark_label', 'name', 'color_rgb', 'is_focal_target',
                       'axes_source', 'axes_confidence', 'axes_reason')
            for supplied, owned in zip(meshes, self.__meshes):
                if not isinstance(supplied, MeshEntity3D):
                    return False
                if any(getattr(supplied, name) != getattr(owned, name) for name in scalars):
                    return False
                for name in arrays:
                    a, b = getattr(supplied, name), getattr(owned, name)
                    if a is None or b is None:
                        if a is not b:
                            return False
                    elif not np.array_equal(a, b):
                        return False
            return True
        except (AttributeError, TypeError, ValueError):
            return False

    def _claim_attention(self, canvas, metadata, meshes, fingerprint):
        if self.__attention_claimed or not self._attention_matches(canvas, metadata, meshes, fingerprint):
            return None
        # One proposal operation may use this snapshot. A hold leaves default
        # Q4 completion available, but it cannot obtain another precheck memo.
        object.__setattr__(self, '_PreparedSceneRender__attention_claimed', True)
        return self.__meshes

    def _finish(self, canvas, metadata, fingerprint):
        if type(fingerprint) is not str or fingerprint != self.__fingerprint:
            raise ValueError('Prepared render belongs to a different current snapshot')
        if self.__consumed:
            raise ValueError('Prepared render has already completed its operation')
        binding = _render_metadata_binding(metadata)
        if (canvas is not self.__canvas or canvas.im is not self.__core
                or not canvas.readonly or canvas.mode != 'RGB'
                or canvas.size != (self.__size * 2, self.__size * 2)):
            raise ValueError('Prepared render belongs to a different or modified canvas')
        try:
            metadata_matches = binding == self.__metadata
        except (TypeError, ValueError):
            metadata_matches = False
        if not metadata_matches:
            raise ValueError('Prepared render camera or metadata was modified')
        visual = copy.deepcopy(metadata)
        target = visual['views'][3]
        target.pop('render_status')
        scope = {key: target.pop(key) for key in ('view_scope', 'occlusion_object_ids',
                                                'all_supplied_geometry_participates_in_depth')}
        caption_region = []
        picture = _render_view(_SceneRasterizer(self.__size), self.__meshes,
                               np.asarray(target['view_matrix'], dtype=float),
                               np.asarray(target['projection_matrix'], dtype=float),
                               target, scope=scope, caption_region_out=caption_region,
                               label_plan=visual.get('task_labels'))
        output = canvas.copy()
        output.paste(picture, (self.__size, self.__size))
        visual['raster_schedule'].update(default_q4='rendered_on_fallback', final_q4='target', canvas_complete=True)
        # Completion consumes the render operation. Bind its optional layout
        # proof to the finished image/core and metadata, replacing the pending
        # binding rather than retaining two canvases or exposing a JSON claim.
        output.readonly = 1
        for name, value in (('__canvas', output), ('__core', output.im),
                            ('__metadata', copy.deepcopy(visual)),
                            ('__caption_region', caption_region[0])):
            object.__setattr__(self, '_PreparedSceneRender' + name, value)
        object.__setattr__(self, '_PreparedSceneRender__consumed', True)
        return output, visual

    def _caption_inputs(self, canvas, metadata, meshes):
        if (not self.__consumed or self.__caption_region is None
                or canvas is not self.__canvas or canvas.im is not self.__core
                or not canvas.readonly or canvas.mode != 'RGB'
                or canvas.size != (self.__size * 2, self.__size * 2)
                or type(metadata) is not dict):
            return None
        try:
            matches = metadata == self.__metadata
        except (TypeError, ValueError):
            matches = False
        if not matches or not isinstance(meshes, (list, tuple)) or len(meshes) != len(self.__meshes):
            return None
        # A stale witness can remain on a different surface of a moved solid.
        # Bind the complete supplied world-metre geometry to the actual render
        # before reusing any of its strict-pair display facts. This is bounded
        # equality, not a second distance evaluation or rasterization.
        try:
            if any(not isinstance(mesh, MeshEntity3D) for mesh in meshes):
                return None
            by_id = {mesh.object_id: mesh for mesh in meshes}
            if len(by_id) != len(self.__meshes):
                return None
            for owned in self.__meshes:
                supplied = by_id.get(owned.object_id)
                if (supplied is None or not np.array_equal(supplied.vertices, owned.vertices)
                        or not np.array_equal(supplied.faces, owned.faces)):
                    return None
        except (AttributeError, TypeError, ValueError):
            return None
        return self.__caption_region, self.__meshes


def _render_scene_canvas_prepared(meshes, quad_size=128, *, focal_id=None,
                                  reference_id=None, scene_fingerprint, label_plan=None,
                                  raw_observer=None):
    """Internal deferred canvas plus opaque inputs for this observation only."""
    if type(scene_fingerprint) is not str or not scene_fingerprint or len(scene_fingerprint) > 256:
        raise ValueError('Prepared render requires the current validated scene fingerprint')
    return _render_scene_canvas_impl(meshes, quad_size, focal_id=focal_id,
                                    reference_id=reference_id, defer_q4=True,
                                    prepared_fingerprint=scene_fingerprint, label_plan=label_plan,
                                    raw_observer=raw_observer)


def _finalize_prepared_scene_q4(canvas, metadata, prepared, *, scene_fingerprint):
    """Finish a bound pending Q4 without normalizing or cloning meshes again.

    The internal caller must supply its currently validated snapshot hash.
    Reusing a token with a new canvas, camera or snapshot is rejected. An
    adopted CONTACT does not need this function; use it only for fallback.
    Successful completion consumes the token; only the public legacy finalizer
    provides idempotent no-op completion of arbitrary finished canvases.
    """
    if type(prepared) is not _PreparedSceneRender:
        raise TypeError('Prepared render inputs must be the operation-local opaque object')
    return prepared._finish(canvas, metadata, scene_fingerprint)


def _prepared_caption_inputs(canvas, metadata, meshes, prepared):
    """Read the current opaque layout and owned geometry, never a JSON claim."""
    if type(prepared) is not _PreparedSceneRender:
        return None
    return prepared._caption_inputs(canvas, metadata, meshes)


def _claim_prepared_attention_inputs(canvas, metadata, meshes, prepared, *, scene_fingerprint):
    """Internal operation-local read-only geometry; never a JSON certificate."""
    if type(prepared) is not _PreparedSceneRender:
        return None
    return prepared._claim_attention(canvas, metadata, meshes, scene_fingerprint)


def _prepared_attention_inputs_match(canvas, metadata, meshes, prepared, *, scene_fingerprint):
    if type(prepared) is not _PreparedSceneRender:
        return False
    return prepared._attention_matches(canvas, metadata, meshes, scene_fingerprint)


def finalize_scene_q4(canvas, metadata, meshes):
    """Complete an internal deferred Q4, or leave a finished canvas intact.

    The fallback uses every scene mesh and the original fitted camera. Inputs
    are not modified, and repeated calls on the returned canvas are no-ops.
    The caller must keep the same scene snapshot between prepare and finish.
    """
    schedule = metadata.get('raster_schedule')
    if schedule is None or schedule.get('canvas_complete') is True:
        return canvas, metadata
    if schedule.get('default_q4') != 'deferred' or schedule.get('final_q4') != 'pending':
        raise ValueError('Unrecognized incomplete scene canvas')
    size = metadata['quad_size']
    if canvas.mode != 'RGB' or canvas.size != (size * 2, size * 2) or len(metadata['views']) != 4:
        raise ValueError('Invalid deferred scene canvas')
    render_meshes, _, _, _ = _render_inputs(meshes, size)
    visual = copy.deepcopy(metadata)
    target = visual['views'][3]
    if (target.get('render_status') != 'deferred'
            or target.get('occlusion_object_ids') != [mesh.object_id for mesh in render_meshes]):
        raise ValueError('Deferred scene canvas occlusion geometry differs')
    target.pop('render_status')
    view = np.asarray(target['view_matrix'], dtype=float)
    projection = np.asarray(target['projection_matrix'], dtype=float)
    if view.shape != (4, 4) or projection.shape != (4, 4) or not np.isfinite(np.r_[view.ravel(), projection.ravel()]).all():
        raise ValueError('Invalid deferred Q4 camera')
    scope = {key: target.pop(key) for key in ('view_scope', 'occlusion_object_ids',
                                            'all_supplied_geometry_participates_in_depth')}
    label_plan = visual.get('task_labels')
    if label_plan is not None:
        if type(label_plan) is not dict:
            raise ValueError('Invalid task label plan')
        label_plan = validate_task_label_plan(label_plan, render_meshes,
            focal_id=label_plan.get('focal_id'), reference_id=label_plan.get('reference_id'))
    picture = _render_view(_SceneRasterizer(size), render_meshes, view, projection, target,
                           scope=scope, label_plan=label_plan)
    output = canvas.copy()
    output.paste(picture, (size, size))
    visual['raster_schedule'].update(default_q4='rendered_on_fallback', final_q4='target', canvas_complete=True)
    return output, visual


__all__ = ['render_scene_canvas', 'finalize_scene_q4']
