"""Explicit analytical mesh sections beside, never instead of, natural views.

All supplied objects participate in triangle/plane intersections. This diagnostic
does not certify natural visibility, occupied volume, a free path, or an action.
Its section lines are computed before labels or the supplied measured dimension.
"""
from __future__ import annotations

import copy
import hashlib
import math

import numpy as np
from PIL import Image, ImageDraw

from human_eye_module1_operators import MeshEntity3D
from .geometry_safety import work_budget_status


MAX_SECTION_TRIANGLES = 65_536
MAX_SECTION_SEGMENTS = 32_768


def _point(value):
    point = np.asarray(value, dtype=np.float64)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError('Section requires finite world-metre points')
    return point


def _clip_segment(first, second, half_width, half_height):
    """Clip in metre coordinates before conversion to bounded pixel integers."""
    delta = second - first
    begin, end = 0., 1.
    for axis, half in ((0, half_width), (1, half_height)):
        if delta[axis] == 0:
            if abs(first[axis]) > half:
                return None
            continue
        low, high = sorted(((-half - first[axis]) / delta[axis],
                            (half - first[axis]) / delta[axis]))
        begin, end = max(begin, low), min(end, high)
        if begin > end:
            return None
    return first + begin * delta, first + end * delta


def _intersections(mesh, origin, normal, horizontal, vertical, tolerance):
    local = np.asarray(mesh.vertices, dtype=np.float64) - origin
    distances = local @ normal
    points = np.c_[local @ horizontal, local @ vertical]
    segments, coplanar, tangent, degenerate = [], 0, 0, 0
    for face in mesh.faces:
        world = local[face]
        # A zero-area triangle has no reliable surface intersection.
        edges = world[1:] - world[0]
        scale = max(float(np.max(np.abs(edges))), tolerance)
        if np.linalg.norm(np.cross(edges[0] / scale, edges[1] / scale)) <= 64 * np.finfo(float).eps:
            degenerate += 1
            continue
        signed, xy = distances[face], points[face]
        on = np.abs(signed) <= tolerance
        if on.all():
            coplanar += 1
            segments.extend((xy[i].copy(), xy[(i + 1) % 3].copy()) for i in range(3))
        elif signed.min() <= tolerance and signed.max() >= -tolerance:
            hits = [xy[i].copy() for i in range(3) if on[i]]
            for i in range(3):
                j = (i + 1) % 3
                if not on[i] and not on[j] and (signed[i] < 0) != (signed[j] < 0):
                    fraction = signed[i] / (signed[i] - signed[j])
                    hits.append(xy[i] + fraction * (xy[j] - xy[i]))
            unique = []
            for point in hits:
                if not any(np.linalg.norm(point - other) <= tolerance for other in unique):
                    unique.append(point)
            if len(unique) == 2:
                segments.append((unique[0], unique[1]))
            elif unique:
                tangent += 1
        if len(segments) > MAX_SECTION_SEGMENTS:
            raise ValueError('Section segment work budget exceeded')
    return segments, dict(coplanar_triangle_count=coplanar,
                         tangent_triangle_count=tangent, degenerate_triangle_count=degenerate)


def append_contact_section(canvas, meshes, measurement, *, focal_id, reference_id, quad_size):
    """Return a new composite plus JSON evidence, or fail without changing input.

    Caller supplies its current validated scene and exact positive pair result.
    A measured dimension is not independent ground truth. Coplanar triangles
    retain their wire edges; contours are not a filled-solid classifier.
    """
    if (type(quad_size) is not int or not 64 <= quad_size <= 512
            or not isinstance(canvas, Image.Image) or canvas.mode != 'RGB'
            or canvas.size != (2 * quad_size, 2 * quad_size)):
        raise ValueError('Section requires a complete RGB four-view canvas')
    if (not isinstance(meshes, (list, tuple)) or not 1 <= len(meshes) <= 256
            or any(not isinstance(mesh, MeshEntity3D) for mesh in meshes)):
        raise ValueError('Section requires validated scene meshes')
    identities = [mesh.object_id for mesh in meshes]
    if (len(set(identities)) != len(meshes) or focal_id not in identities
            or reference_id not in identities or focal_id == reference_id):
        raise ValueError('Section requires distinct current target objects')
    triangles = sum(len(mesh.faces) for mesh in meshes)
    if triangles > MAX_SECTION_TRIANGLES or not work_budget_status(meshes, purpose='render')['within_budget']:
        raise ValueError('Section geometry work budget exceeded')
    if (not isinstance(measurement, dict) or measurement.get('measurement_kind') != 'exact'
            or measurement.get('clearance_exact') is not True or measurement.get('measurement_valid') is not True):
        raise ValueError('Section requires an exact positive pair measurement')
    gap = measurement.get('signed_clearance_m')
    if type(gap) not in (int, float) or not math.isfinite(gap) or gap <= 0:
        raise ValueError('Section requires an exact positive pair measurement')
    first, second = _point(measurement.get('point_a_world')), _point(measurement.get('point_b_world'))
    vector = first - second
    distance = float(np.linalg.norm(vector))
    if not math.isfinite(distance) or abs(distance - gap) > max(1e-9, gap * 1e-5):
        raise ValueError('Section witnesses disagree with measured clearance')
    origin = first / 2 + second / 2
    scale = max(1., float(np.max(np.abs(origin))))
    tolerance = max(1e-12, scale * np.finfo(float).eps * 64)
    if distance <= tolerance * 8:
        raise ValueError('Section clearance below local numeric resolution')
    vertical = vector / distance
    seed = np.eye(3)[int(np.argmin(np.abs(vertical)))]
    horizontal = seed - np.dot(seed, vertical) * vertical
    horizontal /= np.linalg.norm(horizontal)
    normal = np.cross(horizontal, vertical)
    width, height = max(192, quad_size), quad_size * 2
    left, top, right, bottom = 10, 38, width - 11, height - 41
    plot_width, plot_height = right - left, bottom - top
    m_per_pixel = gap / 12.
    half_width, half_height = plot_width * m_per_pixel / 2, plot_height * m_per_pixel / 2
    panel = Image.new('RGB', (width, height), (18, 22, 30))
    draw = ImageDraw.Draw(panel)
    center = np.array([(left + right) / 2, (top + bottom) / 2])

    def pixel(point):
        return (float(center[0] + point[0] / m_per_pixel),
                float(center[1] - point[1] / m_per_pixel))

    objects, segments_total = [], 0
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        for mesh in meshes:
            vertices = np.asarray(mesh.vertices)
            faces = np.asarray(mesh.faces)
            if (vertices.ndim != 2 or vertices.shape[1:] != (3,) or not np.isfinite(vertices).all()
                    or faces.ndim != 2 or faces.shape[1:] != (3,) or faces.dtype.kind not in 'iu'
                    or not len(faces) or np.min(faces) < 0 or np.max(faces) >= len(vertices)):
                raise ValueError('Invalid current section geometry')
            segments, status = _intersections(mesh, origin, normal, horizontal, vertical, tolerance)
            segments_total += len(segments)
            if segments_total > MAX_SECTION_SEGMENTS:
                raise ValueError('Section segment work budget exceeded')
            clipped, visible = [], []
            for a, b in segments:
                result = _clip_segment(a, b, half_width, half_height)
                if result is None:
                    continue
                p, q = result
                if np.linalg.norm(p - q) <= tolerance:
                    continue
                clipped.append([p.tolist(), q.tolist()])
                visible.append((pixel(p), pixel(q)))
            rgb = tuple(int(channel) for channel in mesh.color_rgb)
            for p, q in visible:
                draw.line([p, q], fill=rgb, width=1)
            objects.append(dict(object_id=mesh.object_id, triangle_count=len(faces),
                intersection_segment_count=len(segments), visible_segment_count=len(visible),
                viewport_segments_plane_m=clipped, **status))
    # Preserve an unannotated geometry hash. Neither text nor dimension lines
    # can serve as natural-visibility or free-space evidence.
    raw_hash = hashlib.sha256(panel.tobytes()).hexdigest()
    draw.rectangle((left, top, right, bottom), outline=(80, 90, 105))
    draw.text((5, 4), 'CONTACT SECTION', fill=(235, 242, 255))
    draw.text((5, 18), 'Mesh cut; not a natural view', fill=(255, 223, 110))
    for label, point in (('A', first), ('B', second)):
        local = point - origin
        screen = pixel(np.array([local @ horizontal, local @ vertical]))
        draw.ellipse((screen[0]-2, screen[1]-2, screen[0]+2, screen[1]+2), outline=(255, 223, 110))
        draw.text((screen[0]+5, screen[1]-5), label, fill=(255, 223, 110))
    draw.text((5, height-36), f'Measured {gap*1000:.6g} mm', fill=(255, 223, 110))
    draw.text((5, height-23), f'{m_per_pixel*1000:.4g} mm / px', fill=(220, 228, 235))
    draw.text((5, height-11), 'A focal / B reference', fill=(220, 228, 235))
    output = Image.new('RGB', (canvas.width + width, height), (18, 22, 30))
    output.paste(canvas, (0, 0))
    output.paste(panel, (canvas.width, 0))
    evidence = dict(schema_version='1.0', kind='contact_section', status='available',
        source='current_full_mesh_triangle_plane_intersections',
        scope='local_analytical_wire_section_not_natural_visibility_or_solid_classification',
        natural_visibility_certified=False, free_path_certified=False, execution_authority=False,
        independent_ground_truth=False, geometry_modified=False,
        target_object_ids=[focal_id, reference_id], witness_points_world_m=[first.tolist(), second.tolist()],
        measured_clearance_m=float(gap), plane_origin_world_m=origin.tolist(),
        plane_normal_world=normal.tolist(), horizontal_basis_world=horizontal.tolist(),
        vertical_basis_world=vertical.tolist(), plane_tolerance_m=tolerance,
        m_per_pixel=m_per_pixel, viewport_half_extent_m=[half_width, half_height],
        panel_offset_px=[canvas.width, 0], panel_size_px=[width, height],
        plane_origin_panel_px=center.tolist(), original_natural_views_preserved=True,
        participating_object_ids=identities, objects=objects,
        coplanar_policy='triangle_wire_edges_retained_not_solid_boundary_certificate',
        degenerate_policy='skip_and_report_not_clear',
        unannotated_geometry_rgb_sha256=raw_hash, annotations_count_as_evidence=False,
        work=dict(triangles=triangles, intersection_segments=segments_total,
                  max_triangles=MAX_SECTION_TRIANGLES, max_segments=MAX_SECTION_SEGMENTS))
    return output, copy.deepcopy(evidence)


__all__ = ['append_contact_section']
