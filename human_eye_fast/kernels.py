"""Vectorized geometry for trusted arrays, with no admission or policy layer.

These kernels compute binary64 geometry. They do not reproduce the legacy
binary32 uncertainty envelope, exact-rational predicates, source verification,
or work/size/deadline limits. The caller supplies valid shapes and indices and
keeps reference topology unchanged. Exact zero-area reference triangles have
undefined deformation (NaN); a collapsed current triangle has zero area ratio.
Near-degenerate finite triangles are evaluated directly rather than rejected.
"""
from dataclasses import dataclass

import numpy as np


def _length(v):
    return np.hypot(np.hypot(v[..., 0], v[..., 1]), v[..., 2])


@dataclass(slots=True)
class Reference:
    triangles: np.ndarray
    inv_length: np.ndarray
    projection_ratio: np.ndarray
    inv_height: np.ndarray


def prepare_reference(vertices, triangles):
    """Cache the inverse reference chart once for all subsequent frames.

    Scaling reference edges before evaluating their chart avoids unnecessary
    square overflow/underflow. No matrix inversion or per-face Python objects
    are involved. The topology array may share storage with the caller.
    """
    vertices = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(triangles, dtype=np.intp)
    points = vertices[triangles]
    e1 = points[:, 1] - points[:, 0]
    e2 = points[:, 2] - points[:, 0]
    scale = np.maximum(np.max(np.abs(e1), axis=1), np.max(np.abs(e2), axis=1))
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        a = e1 / scale[:, None]
        b = e2 / scale[:, None]
        length = _length(a)
        height = _length(np.cross(a, b)) / length
        ratio = np.einsum("ij,ij->i", a, b) / (length * length)
        inv_length = (1.0 / length) / scale
        inv_height = (1.0 / height) / scale
    # Undefined reference area is mathematical output, not a rejection policy.
    undefined = (height == 0) | ~np.isfinite(height)
    inv_length[undefined] = np.nan
    inv_height[undefined] = np.nan
    ratio[undefined] = np.nan
    return Reference(triangles, inv_length, ratio, inv_height)


def deformation_metrics(reference, current_vertices, face_indices=None):
    """Batched surface stretches and area ratios, optionally for dirty faces.

    The 3x2 surface gradient is assembled from the cached inverse chart. Its
    larger singular value uses the closed-form symmetric 2x2 eigenvalue; the
    smaller value is recovered from their product, avoiding subtractive
    cancellation. Gradient scaling prevents squaring physical magnitudes.
    """
    selection = slice(None) if face_indices is None else face_indices
    points = np.asarray(current_vertices, dtype=np.float64)[reference.triangles[selection]]
    e1 = points[:, 1] - points[:, 0]
    e2 = points[:, 2] - points[:, 0]
    with np.errstate(divide="ignore", invalid="ignore", over="ignore", under="ignore"):
        f0 = e1 * reference.inv_length[selection, None]
        f1 = (e2 - e1 * reference.projection_ratio[selection, None]) * reference.inv_height[selection, None]
        scale = np.maximum(np.max(np.abs(f0), axis=1), np.max(np.abs(f1), axis=1))
        a = np.divide(f0, scale[:, None], out=np.zeros_like(f0), where=scale[:, None] != 0)
        b = np.divide(f1, scale[:, None], out=np.zeros_like(f1), where=scale[:, None] != 0)
        c00 = np.einsum("ij,ij->i", a, a)
        c11 = np.einsum("ij,ij->i", b, b)
        c01 = np.einsum("ij,ij->i", a, b)
        largest = np.sqrt(0.5 * (c00 + c11 + np.hypot(c00 - c11, 2 * c01)))
        product = _length(np.cross(a, b))
        smallest = np.divide(product, largest, out=np.zeros_like(product), where=largest != 0)
        high = largest * scale
        low = smallest * scale
        area = high * low
    return {"stretches": np.column_stack((high, low)), "area_ratio": area}


def triangle_box_mask(points, low, high):
    """Closed triangle/box intersection using vectorized separating axes.

    AABB pruning precedes the triangle normal and nine edge/canonical-axis
    tests. Point and segment triangles use the same formulas. Comparisons
    have no epsilon, rational fallback, or conservative unknown outcome;
    floating-point rounding can affect extremely close boundary decisions.
    Temporary storage is linear in the number of surviving triangles.
    """
    points = np.asarray(points, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    high = np.asarray(high, dtype=np.float64)
    mask = np.all(points.max(axis=1) >= low, axis=1) & np.all(points.min(axis=1) <= high, axis=1)
    indices = np.flatnonzero(mask)
    if indices.size == 0:
        return mask
    center = low * 0.5 + high * 0.5
    half = high * 0.5 - low * 0.5
    p = points[indices] - center
    edges = (p[:, 1] - p[:, 0], p[:, 2] - p[:, 1], p[:, 0] - p[:, 2])
    normal = np.cross(edges[0], edges[1])
    distance = np.einsum("ij,ij->i", normal, p[:, 0])
    radius = np.abs(normal) @ half
    overlap = np.abs(distance) <= radius
    for edge in edges:
        for j, k in ((1, 2), (2, 0), (0, 1)):
            projected = p[:, :, j] * edge[:, k, None] - p[:, :, k] * edge[:, j, None]
            radius = half[j] * np.abs(edge[:, k]) + half[k] * np.abs(edge[:, j])
            overlap &= (projected.min(axis=1) <= radius) & (projected.max(axis=1) >= -radius)
    mask[indices] = overlap
    return mask
