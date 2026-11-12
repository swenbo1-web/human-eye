"""Bounded orthographic surface rasterizer for a local attention viewport.

Clip floating-point polygons before converting any coordinate to a pixel
integer. Barycentric coverage avoids division by nearly horizontal scan-line
slopes. All supplied meshes share one depth buffer: no X-ray, focus exemptions,
geometry rescaling, or scene mutations occur here.
"""
from __future__ import annotations

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from .geometry_safety import work_budget_status


MAX_PIXEL_SAMPLES = 8_388_608
_ROWS_PER_CHUNK = 64
_BACKGROUND = (18, 22, 30)


def _clip_polygon(polygon):
    """Sutherland-Hodgman in NDC; component four retains metre camera depth."""
    for axis in range(3):
        for bound, sign in ((-1., 1.), (1., -1.)):
            if len(polygon) == 0:
                return polygon
            output = []
            previous = polygon[-1]
            previous_distance = sign * (previous[axis] - bound)
            for current in polygon:
                current_distance = sign * (current[axis] - bound)
                previous_inside, current_inside = previous_distance >= 0, current_distance >= 0
                if previous_inside != current_inside:
                    fraction = previous_distance / (previous_distance - current_distance)
                    intersection = previous * (1 - fraction) + current * fraction
                    intersection[axis] = bound
                    output.append(intersection)
                if current_inside:
                    output.append(current)
                previous, previous_distance = current, current_distance
            polygon = np.asarray(output, dtype=np.float64)
    return polygon


def _raster_triangle(triangle, rgb, color, depth, sample_count, owners=None, object_index=None):
    size = depth.shape[0]
    xy = np.c_[(triangle[:, 0] + 1) * (size - 1) / 2,
               (1 - triangle[:, 1]) * (size - 1) / 2]
    # Clip already keeps these bounds small; clamp again before integer casts
    # so roundoff at an edge never leaks into an unbounded conversion.
    lower = np.maximum(0., np.minimum(size - 1., np.floor(xy.min(axis=0))))
    upper = np.maximum(0., np.minimum(size - 1., np.ceil(xy.max(axis=0))))
    xmin, ymin = (int(value) for value in lower)
    xmax, ymax = (int(value) for value in upper)
    a, b, c = xy
    area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(area) <= np.finfo(np.float64).eps * size * size * 8:
        return sample_count
    samples = (xmax - xmin + 1) * (ymax - ymin + 1)
    sample_count += samples
    if sample_count > MAX_PIXEL_SAMPLES:
        raise ValueError('Attention raster pixel work budget exceeded')
    # Pixel centres match the retained overview raster convention. Independent
    # chunks cap intermediate coverage/depth arrays at 64 * viewport width.
    x = np.arange(xmin, xmax + 1, dtype=np.float64)[None, :] + .5
    for start in range(ymin, ymax + 1, _ROWS_PER_CHUNK):
        end = min(start + _ROWS_PER_CHUNK, ymax + 1)
        y = np.arange(start, end, dtype=np.float64)[:, None] + .5
        w0 = ((b[0] - x) * (c[1] - y) - (b[1] - y) * (c[0] - x)) / area
        w1 = ((c[0] - x) * (a[1] - y) - (c[1] - y) * (a[0] - x)) / area
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-10) & (w1 >= -1e-10) & (w2 >= -1e-10)
        values = w0 * triangle[0, 3] + w1 * triangle[1, 3] + w2 * triangle[2, 3]
        section = depth[start:end, xmin:xmax + 1]
        nearer = inside & (values > 0) & (values < section)
        section[nearer] = values[nearer]
        color[start:end, xmin:xmax + 1][nearer] = rgb
        if owners is not None:
            owners[start:end, xmin:xmax + 1][nearer] = object_index
    return sample_count


def rasterize_attention(meshes, view, projection, size, *, return_owner=False):
    """Return RGB uint8 color and float64 positive camera depth in metres.

    Only finite rigid-view/orthographic matrices are accepted. Geometry outside
    any of the six clip planes is excluded. Both triangle orientations are
    rendered, letting ordinary depth occlusion handle closed and open meshes.
    Resource overflow fails explicitly; partial images are never returned.
    """
    if type(return_owner) is not bool:
        raise ValueError('return_owner must be boolean')
    if type(size) is not int or not 64 <= size <= 512:
        raise ValueError('Attention raster size must be an integer in 64..512')
    if not isinstance(meshes, (list, tuple)) or not 1 <= len(meshes) <= 256:
        raise ValueError('Attention raster requires 1..256 meshes')
    if any(not isinstance(mesh, MeshEntity3D) for mesh in meshes):
        raise TypeError('Attention raster requires MeshEntity3D instances')
    view, projection = np.asarray(view, dtype=np.float64), np.asarray(projection, dtype=np.float64)
    if (view.shape != (4, 4) or projection.shape != (4, 4)
            or not np.isfinite(view).all() or not np.isfinite(projection).all()
            or not np.allclose(view[3], [0, 0, 0, 1], rtol=0, atol=1e-12)
            or not np.allclose(projection[3], [0, 0, 0, 1], rtol=0, atol=1e-12)
            or not np.allclose(view[:3, :3] @ view[:3, :3].T, np.eye(3), rtol=0, atol=1e-8)
            or not np.isclose(np.linalg.det(view[:3, :3]), 1, rtol=0, atol=1e-8)):
        raise ValueError('Attention raster requires finite rigid-view and orthographic matrices')
    if not work_budget_status(meshes, purpose='render')['within_budget']:
        raise ValueError('Attention raster geometry work budget exceeded')
    color = np.empty((size, size, 3), dtype=np.uint8)
    color[:] = _BACKGROUND
    depth = np.full((size, size), np.inf, dtype=np.float64)
    owners = np.full((size, size), -1, dtype=np.int32) if return_owner else None
    sample_count = 0
    light = np.array([.4, -.5, 1.])
    light /= np.linalg.norm(light)
    try:
        with np.errstate(over='raise', divide='raise', invalid='raise'):
            for object_index, mesh in enumerate(meshes):
                camera = mesh.vertices @ view[:3, :3].T + view[:3, 3]
                ndc = camera @ projection[:3, :3].T + projection[:3, 3]
                if not np.isfinite(ndc).all() or not np.isfinite(camera).all():
                    raise ValueError('Attention raster geometry exceeds numeric range')
                points = np.c_[ndc, -camera[:, 2]]
                # Classify the same six strict clip-plane inequalities once
                # per vertex instead of issuing several NumPy reductions per
                # face. An AND of the three outcodes rejects exactly a face
                # whose vertices all lie outside one common plane; an OR
                # selects exactly those remaining faces needing polygon clip.
                # Equality stays inside. Face order and all floating-point
                # clipping/shading/depth arithmetic below remain unchanged.
                codes = np.zeros(len(points), dtype=np.uint8)
                for axis in range(3):
                    codes |= (ndc[:, axis] < -1).astype(np.uint8) << (2 * axis)
                    codes |= (ndc[:, axis] > 1).astype(np.uint8) << (2 * axis + 1)
                face_codes = codes[mesh.faces]
                outside = face_codes[:, 0] & face_codes[:, 1] & face_codes[:, 2]
                needs_clip = face_codes[:, 0] | face_codes[:, 1] | face_codes[:, 2]
                for face_index, face in enumerate(mesh.faces):
                    if outside[face_index]:
                        continue
                    triangle = points[face]
                    polygon = _clip_polygon(triangle) if needs_clip[face_index] else triangle
                    if len(polygon) < 3:
                        continue
                    world = mesh.vertices[face]
                    first, second = world[1] - world[0], world[2] - world[0]
                    # Normalise edges before cross product to avoid overflow
                    # and preserve shading when world geometry is very large.
                    scale = max(float(np.max(np.abs(first))), float(np.max(np.abs(second))))
                    normal = np.cross(first / scale, second / scale) if scale else np.zeros(3)
                    length = float(np.linalg.norm(normal))
                    shade = .45 + .55 * abs(float(normal @ light) / length) if length else .45
                    rgb = np.clip(np.asarray(mesh.color_rgb, dtype=np.float64) * shade, 0, 255).astype(np.uint8)
                    for index in range(1, len(polygon) - 1):
                        sample_count = _raster_triangle(polygon[[0, index, index + 1]], rgb, color, depth, sample_count,
                                                        owners, object_index)
    except FloatingPointError as exc:
        raise ValueError('Attention raster geometry exceeds numeric range') from exc
    return (color, depth, owners) if return_owner else (color, depth)


__all__ = ['rasterize_attention']
