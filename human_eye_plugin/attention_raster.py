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
_SPARSE_GRID_SIZE = 8
_SPARSE_FACE_BLOCK = 2048
_SPARSE_CLIP_BLOCK = 64


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


def _raster_triangle(triangle, rgb, color, depth, sample_count, owners=None, object_index=None,
                     patch_owners=None, patch_index=None):
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
        if patch_owners is not None:
            patch_owners[start:end, xmin:xmax + 1][nearer] = patch_index
    return sample_count


def _project_attention_mesh(mesh, view, projection):
    camera = mesh.vertices @ view[:3, :3].T + view[:3, 3]
    ndc = camera @ projection[:3, :3].T + projection[:3, 3]
    if not np.isfinite(ndc).all() or not np.isfinite(camera).all():
        raise FloatingPointError('nonfinite_projected_mesh')
    points = np.c_[ndc, -camera[:, 2]]
    codes = np.zeros(len(points), dtype=np.uint8)
    for axis in range(3):
        codes |= (ndc[:, axis] < -1).astype(np.uint8) << (2 * axis)
        codes |= (ndc[:, axis] > 1).astype(np.uint8) << (2 * axis + 1)
    return points, codes


def _sparse_depths(triangles, x, y, size):
    """Evaluate the raster's exact depth expression at the registered centres."""
    ax, bx, cx = ((triangles[:, :, 0] + 1) * (size - 1) / 2).T[:, :, None]
    ay, by, cy = ((1 - triangles[:, :, 1]) * (size - 1) / 2).T[:, :, None]
    area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    valid = np.abs(area) > np.finfo(np.float64).eps * size * size * 8
    denominator = np.where(valid, area, 1.)
    w0 = ((bx - x) * (cy - y) - (by - y) * (cx - x)) / denominator
    w1 = ((cx - x) * (ay - y) - (cy - y) * (ax - x)) / denominator
    w2 = 1 - w0 - w1
    inside = valid & (w0 >= -1e-10) & (w1 >= -1e-10) & (w2 >= -1e-10)
    # The raster also restricts each triangle to a clamped integer pixel box.
    for sample, a, b, c in ((x, ax, bx, cx), (y, ay, by, cy)):
        low = np.clip(np.floor(np.minimum(np.minimum(a, b), c)), 0, size - 1)
        high = np.clip(np.ceil(np.maximum(np.maximum(a, b), c)), 0, size - 1)
        inside &= (sample >= low + .5) & (sample <= high + .5)
    values = (w0 * triangles[:, 0, 3, None] + w1 * triangles[:, 1, 3, None]
              + w2 * triangles[:, 2, 3, None])
    return np.where(inside & (values > 0), values, np.inf)


def _sparse_attention_owner_count(meshes, pose, object_mask, selected_object, selected, check_budget):
    view = np.asarray(pose['view_matrix'], dtype=np.float64)
    projection = np.asarray(pose['projection_matrix'], dtype=np.float64)
    size = pose['size_px'][0]
    pixels = (2 * np.arange(_SPARSE_GRID_SIZE) + 1) * size // (2 * _SPARSE_GRID_SIZE)
    x, y = (coordinate.ravel() for coordinate in np.meshgrid(pixels + .5, pixels + .5))
    nearest = np.full(x.size, np.inf)
    selected_winner = np.zeros(x.size, dtype=np.bool_)
    locations = np.arange(x.size)
    for object_index, mesh in enumerate(meshes):
        if not object_mask[object_index]:
            continue
        check_budget('source_region_sparse_view_projection')
        points, outcodes = _project_attention_mesh(mesh, view, projection)
        # Clipping can only shrink the projected box. A one-pixel margin keeps
        # the broad phase conservative near floating-point clip boundaries.
        bounded = np.clip(points[:, :2], -1., 1.)
        screen = np.c_[(bounded[:, 0] + 1) * (size - 1) / 2,
                       (1 - bounded[:, 1]) * (size - 1) / 2]
        for start in range(0, len(mesh.faces), _SPARSE_FACE_BLOCK):
            check_budget('source_region_sparse_view_faces')
            faces = mesh.faces[start:start + _SPARSE_FACE_BLOCK]
            a, b, c = faces.T
            eligible = (outcodes[a] & outcodes[b] & outcodes[c]) == 0
            pa, pb, pc = screen[a], screen[b], screen[c]
            lo = np.floor(np.minimum(np.minimum(pa, pb), pc)) - 1
            hi = np.ceil(np.maximum(np.maximum(pa, pb), pc)) + 1
            eligible &= (np.searchsorted(pixels, lo, side='left') <
                         np.searchsorted(pixels, hi, side='right')).all(axis=1)
            rows = np.flatnonzero(eligible)
            if not rows.size:
                continue
            clipped = (outcodes[a[rows]] | outcodes[b[rows]] | outcodes[c[rows]]) != 0
            ordinary = rows[~clipped]
            block_depth = np.full(x.size, np.inf)
            block_face = np.full(x.size, len(faces), dtype=np.intp)
            if ordinary.size:
                depths = _sparse_depths(points[faces[ordinary]], x, y, size)
                winner = depths.argmin(axis=0)
                block_depth = depths[winner, locations]
                block_face = ordinary[winner]
            clipped_rows = rows[clipped]
            for clip_start in range(0, len(clipped_rows), _SPARSE_CLIP_BLOCK):
                check_budget('source_region_sparse_view_clipping')
                pieces, sources = [], []
                for row in clipped_rows[clip_start:clip_start + _SPARSE_CLIP_BLOCK]:
                    polygon = _clip_polygon(points[faces[row]])
                    if len(polygon) >= 3:
                        fan = np.arange(1, len(polygon) - 1)
                        pieces.append(polygon[np.column_stack((np.zeros_like(fan), fan, fan + 1))])
                        sources.extend([row] * len(fan))
                if not pieces:
                    continue
                depths = _sparse_depths(np.concatenate(pieces), x, y, size)
                winner = depths.argmin(axis=0)
                values = depths[winner, locations]
                winning_face = np.asarray(sources)[winner]
                # Merge the clipped fans by source order on a tie. This is
                # equivalent to the ordered raster's strict nearest update.
                nearer = (values < block_depth) | ((values == block_depth) & (winning_face < block_face))
                block_depth[nearer] = values[nearer]
                block_face[nearer] = winning_face[nearer]
            nearer = block_depth < nearest
            nearest[nearer] = block_depth[nearer]
            selected_winner[nearer] = (selected[start + block_face[nearer]]
                                       if object_index == selected_object else False)
    return int(np.count_nonzero(selected_winner))


def select_sparse_attention_view(meshes, poses, *, object_mask, object_index, source_triangle_indices, check_budget):
    """Choose one registered view using sparse predictions, not image evidence."""
    if not work_budget_status(meshes, purpose='render')['within_budget']:
        # Let the original raster own admission and report its normal failure.
        return 'SCENE', {}
    selected = np.zeros(len(meshes[object_index].faces), dtype=np.bool_)
    selected[list(source_triangle_indices)] = True
    votes = {}
    with np.errstate(over='raise', divide='raise', invalid='raise'):
        for pose in poses:
            check_budget('source_region_before_sparse_view')
            name = pose['name']
            try:
                votes[name] = _sparse_attention_owner_count(meshes, pose, object_mask, object_index, selected, check_budget)
            except FloatingPointError:
                # Preserve the raster's normal failure path for the original
                # default view. Other trials contribute no predictive evidence.
                if name == 'SCENE':
                    return name, votes
                continue
            if name == 'SCENE' and votes[name]:
                return name, votes
    chosen = max(votes, key=votes.get) if any(votes.values()) else 'SCENE'
    return chosen, votes


def rasterize_attention(meshes, view, projection, size, *, return_owner=False,
                        return_patch_owner=False, face_patch_ids=None, object_mask=None):
    """Return RGB uint8 color and float64 positive camera depth in metres.

    Only finite rigid-view/orthographic matrices are accepted. Geometry outside
    any of the six clip planes is excluded. Both triangle orientations are
    rendered, letting ordinary depth occlusion handle closed and open meshes.
    Resource overflow fails explicitly; partial images are never returned.
    ``return_patch_owner=True`` adds a fourth int32 buffer, updated by the same
    depth winner. ``face_patch_ids`` supplies one ID per source triangle, with
    -1 marking faces outside the caller's supported patch set.
    """
    if type(return_owner) is not bool:
        raise ValueError('return_owner must be boolean')
    if type(return_patch_owner) is not bool or return_patch_owner and not return_owner:
        raise ValueError('Patch ownership requires return_owner=True')
    if type(size) is not int or not 64 <= size <= 512:
        raise ValueError('Attention raster size must be an integer in 64..512')
    if not isinstance(meshes, (list, tuple)) or not 1 <= len(meshes) <= 256:
        raise ValueError('Attention raster requires 1..256 meshes')
    if any(not isinstance(mesh, MeshEntity3D) for mesh in meshes):
        raise TypeError('Attention raster requires MeshEntity3D instances')
    if object_mask is not None and (
            not isinstance(object_mask, (list, tuple)) or len(object_mask) != len(meshes)
            or any(type(value) is not bool for value in object_mask)):
        raise ValueError('Object participation requires one boolean per source mesh')
    if return_patch_owner:
        if not isinstance(face_patch_ids, (list, tuple)) or len(face_patch_ids) != len(meshes):
            raise ValueError('Patch ownership requires one face mapping per mesh')
        face_patch_ids = tuple(np.asarray(values) for values in face_patch_ids)
        if any(values.dtype != np.int32 or values.shape != (len(mesh.faces),)
               or np.any(values < -1) for mesh, values in zip(meshes, face_patch_ids)):
            raise ValueError('Patch face mappings require int32 IDs or -1 for unsupported faces')
    elif face_patch_ids is not None:
        raise ValueError('Face patch mappings require return_patch_owner=True')
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
    patch_owners = np.full((size, size), -1, dtype=np.int32) if return_patch_owner else None
    sample_count = 0
    light = np.array([.4, -.5, 1.])
    light /= np.linalg.norm(light)
    try:
        with np.errstate(over='raise', divide='raise', invalid='raise'):
            for object_index, mesh in enumerate(meshes):
                if object_mask is not None and not object_mask[object_index]:
                    continue
                # Classify the same six strict clip-plane inequalities once
                # per vertex instead of issuing several NumPy reductions per
                # face. An AND of the three outcodes rejects exactly a face
                # whose vertices all lie outside one common plane; an OR
                # selects exactly those remaining faces needing polygon clip.
                # Equality stays inside. Face order and all floating-point
                # clipping/shading/depth arithmetic below remain unchanged.
                points, codes = _project_attention_mesh(mesh, view, projection)
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
                    if scale:
                        ux, uy, uz = first / scale
                        vx, vy, vz = second / scale
                        # Keep NumPy's three-dimensional cross-product operation order.
                        normal = np.array((uy * vz - uz * vy,
                                           uz * vx - ux * vz,
                                           ux * vy - uy * vx))
                    else:
                        normal = np.zeros(3)
                    length = float(np.linalg.norm(normal))
                    shade = .45 + .55 * abs(float(normal @ light) / length) if length else .45
                    rgb = np.clip(np.asarray(mesh.color_rgb, dtype=np.float64) * shade, 0, 255).astype(np.uint8)
                    patch_index = face_patch_ids[object_index][face_index] if return_patch_owner else None
                    for index in range(1, len(polygon) - 1):
                        sample_count = _raster_triangle(polygon[[0, index, index + 1]], rgb, color, depth, sample_count,
                                                        owners, object_index, patch_owners, patch_index)
    except FloatingPointError as exc:
        raise ValueError('Attention raster geometry exceeds numeric range') from exc
    if return_patch_owner:
        return color, depth, owners, patch_owners
    return (color, depth, owners) if return_owner else (color, depth)


__all__ = ['rasterize_attention', 'select_sparse_attention_view']
