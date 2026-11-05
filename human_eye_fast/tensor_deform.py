"""Per-face temporal deformation summaries for trusted, fixed-topology frames."""

import numpy as np

from .kernels import _length, deformation_metrics, prepare_reference


def _face_geometry(vertices, triangles):
    points = np.asarray(vertices, dtype=np.float64)[triangles]
    origin = points[:, 0]
    first = points[:, 1] - origin
    second = points[:, 2] - origin
    centers = origin + (first / 3.0 + second / 3.0)

    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        normals = np.cross(first, second)
        lengths = _length(normals)
        # Rescale the edges where a raw cross can lose range or precision.
        small_or_nonfinite = (lengths < np.finfo(np.float64).tiny**0.5) | ~np.isfinite(lengths)
        if small_or_nonfinite.any():
            a = first[small_or_nonfinite]
            b = second[small_or_nonfinite]
            scale = np.maximum(np.abs(a).max(axis=1), np.abs(b).max(axis=1))
            exponent = np.frexp(scale)[1][:, None]
            scaled = np.cross(np.ldexp(a, -exponent), np.ldexp(b, -exponent))
            normals[small_or_nonfinite] = scaled
            lengths[small_or_nonfinite] = _length(scaled)
    collapsed = lengths == 0.0
    lengths[collapsed] = np.nan
    return centers, normals / lengths[:, None], collapsed


def _top_faces(score, top_k):
    if top_k <= 0:
        return np.empty(0, dtype=np.intp)
    ids = np.flatnonzero(~np.isnan(score))
    if ids.size > top_k:
        scores = score[ids]
        cutoff = np.partition(scores, ids.size - top_k)[ids.size - top_k]
        higher = ids[scores > cutoff]
        tied = ids[scores == cutoff][:top_k - higher.size]
        ids = np.concatenate((higher, tied))
    return ids[np.lexsort((ids, -score[ids]))]


def compute_cross_frame_deformation_tensor(v_frames, tris, *, reference_vertices=None, top_k=12):
    """Reduce a sequence of (V, 3) vertex arrays over fixed (F, 3) topology.

    The default reference is frame zero. An explicit reference only sets the
    comparison geometry. Each face keeps the maximum larger stretch, minimum
    smaller stretch, maximum absolute area-ratio change from one, maximum
    oriented world-normal angle in degrees and maximum centroid displacement
    in input distance units. Empty sequences have NaN summaries.

    Degenerate references have undefined stretches, area strain, normal angle
    and score. Their centroid displacement is still reported. Collapsed
    current faces contribute zero area ratio and have undefined normals. The
    angle reduction skips undefined samples and returns NaN when none exist.

    Score combines the largest stretch deviation from one, twice the area
    strain, three times the angle as a fraction of 180 degrees (zero when
    undefined), and displacement divided by the reference bounding-box
    diagonal. Witnesses are original triangle row indices ordered by
    descending score, then ascending row index. NaN scores are excluded.
    """
    triangles = np.asarray(tris, dtype=np.intp)
    high = np.full(len(triangles), np.nan)
    low = np.full_like(high, np.nan)
    area = np.full_like(high, np.nan)
    angle = np.full_like(high, np.nan)
    displacement = np.full_like(high, np.nan)
    score = np.full_like(high, np.nan)

    if len(v_frames) and len(triangles):
        old = np.asarray(v_frames[0] if reference_vertices is None else reference_vertices, dtype=np.float64)
        reference = prepare_reference(old, triangles)
        reference_centers, reference_normals, _ = _face_geometry(old, triangles)
        invalid_reference = np.isnan(reference.inv_length) | np.isnan(reference_normals[:, 0])
        reference_normals[invalid_reference] = np.nan
        reference_scale = _length(old.max(axis=0) - old.min(axis=0))

        for frame in v_frames:
            vertices = np.asarray(frame, dtype=np.float64)
            metrics = deformation_metrics(reference, vertices)
            centers, normals, collapsed = _face_geometry(vertices, triangles)
            # Measure collapse in world geometry before reference-chart roundoff.
            metrics["stretches"][collapsed, 1] = 0.0
            metrics["area_ratio"][collapsed] = 0.0
            np.fmax(high, metrics["stretches"][:, 0], out=high)
            np.fmin(low, metrics["stretches"][:, 1], out=low)
            np.fmax(area, np.abs(metrics["area_ratio"] - 1.0), out=area)

            sine = _length(np.cross(reference_normals, normals))
            cosine = np.einsum("ij,ij->i", reference_normals, normals)
            np.fmax(angle, np.arctan2(sine, cosine), out=angle)
            np.fmax(displacement, _length(centers - reference_centers), out=displacement)

        np.degrees(angle, out=angle)
        high[invalid_reference] = low[invalid_reference] = area[invalid_reference] = np.nan
        if reference_scale > 0.0:
            score = (np.maximum(np.abs(high - 1.0), np.abs(low - 1.0))
                     + 2.0 * area + 3.0 * (np.fmax(angle, 0.0) / 180.0)
                     + displacement / reference_scale)

    return {
        "max_principal_stretch": high,
        "min_principal_stretch": low,
        "max_area_strain": area,
        "max_normal_angle_deg": angle,
        "max_centroid_displacement": displacement,
        "score": score,
        "witness_triangle_ids": _top_faces(score, top_k),
    }
