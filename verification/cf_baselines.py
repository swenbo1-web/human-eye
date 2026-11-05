"""Frozen CF preflight observables and baselines; no host or fixture metadata."""

from dataclasses import dataclass
from math import sqrt

import numpy as np


CANONICAL_STEPS = (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7, 8)
FIXED_ORDER = tuple(range(len(CANONICAL_STEPS)))
VIEW_COLUMNS = ("log2_gap_over_scale", "section", "front", "rear", "plane")
ACTION_COLUMNS = (
    "gap", "local_delta", "shape_key", "shape_control", "shape_delta",
    "witness_mean_shift_normal", "witness_mean_shift_longitudinal",
    "witness_mean_shift_side", "moving_normal_span", "moving_longitudinal_span",
    "moving_side_span", "reference_normal_span", "reference_longitudinal_span",
    "reference_side_span", "sketch_before_error", "sketch_delta",
    "sketch_fixed_bin_delta", "sketch_valid_fraction", "sketch_second_slack",
    "sketch_has_alternative", "normal_shift_min", "normal_shift_max", "normal_shift_std",
)
_SKETCH_BINS = 8
_EDGE_NEXT = np.array([1, 2, 0])
_PCA_TIE = 16 * np.finfo(np.float64).eps


def _interval_distance(low, high, half_width=0.0):
    return np.maximum(np.maximum(low - half_width, -half_width - high), 0.0)


def view_features(point_a_m, point_b_m, directions, occluders, *, section):
    """One row per shared VG direction. Occluders supply only current indexed geometry."""
    a = np.asarray(point_a_m, dtype=np.float64)
    b = np.asarray(point_b_m, dtype=np.float64)
    directions = np.asarray(directions, dtype=np.float64)
    gap = np.linalg.norm(b - a)
    axis = (b - a) / gap
    result = np.zeros((len(FIXED_ORDER), len(VIEW_COLUMNS)), dtype=np.float64)
    result[:, 1] = section
    triangles = [vertices[indices] for vertices, indices in occluders if len(indices)]
    if not triangles:
        return result

    triangles = np.concatenate(triangles) - (a + b) / 2
    scale = max(gap, np.linalg.norm(np.ptp(triangles.reshape(-1, 3), axis=0)))
    result[:, 0] = np.log2(gap / scale)
    step = gap / 16
    bandwidth = max(2 * step, 0.02 * scale)
    axial = triangles @ axis
    lateral = triangles @ np.cross(directions, axis).T
    depth = triangles @ directions.T
    axial_distance = _interval_distance(axial.min(axis=1), axial.max(axis=1), step)
    lateral_distance = _interval_distance(lateral.min(axis=1), lateral.max(axis=1), step)
    depth_low, depth_high = depth.min(axis=1), depth.max(axis=1)
    depth_span = depth_high - depth_low
    projected_area = np.abs(np.cross(triangles[:, 1] - triangles[:, 0],
                                    triangles[:, 2] - triangles[:, 0]) @ directions.T) / 2
    radius_squared = np.square(triangles.mean(axis=1)).sum(axis=1)
    weight = projected_area / (scale**2 + radius_squared[:, None])
    weight /= 1 + np.square(axial_distance[:, None] / bandwidth)
    weight /= 1 + np.square(lateral_distance / bandwidth)
    front = np.where(depth_low > 0, 1.0, np.where(depth_low < 0, 0.0, 0.5))
    np.divide(np.maximum(depth_high, 0.0) - np.maximum(depth_low, 0.0), depth_span,
              out=front, where=depth_span > 0)
    plane_distance = _interval_distance(depth_low, depth_high)
    result[:, 2] = (weight * front).sum(axis=0)
    result[:, 3] = (weight * (1 - front)).sum(axis=0)
    result[:, 4] = (weight / (1 + np.square(plane_distance / bandwidth))).sum(axis=0)
    return result


def train_scale(bank_keys):
    """Population standard deviation fitted on train keys only."""
    std = np.std(bank_keys, axis=0)
    return np.where(std > 0, std, 1.0)


def feedback_order(feedback):
    """Each canonical row stores safe pixel/native success, then native ray count."""
    success, rays = np.asarray(feedback, dtype=np.float64).T
    return tuple(map(int, np.lexsort((FIXED_ORDER, rays, -success))))


def nearest_view_order(features, bank_keys, bank_feedback, scale):
    """Exact 1-NN over train keys ordered by insertion; first equal-distance row wins."""
    if len(bank_keys) == 0:
        return FIXED_ORDER
    distances = np.square((bank_keys - features) / scale).reshape(len(bank_keys), -1).sum(axis=1)
    return feedback_order(bank_feedback[np.argmin(distances)])


@dataclass(frozen=True, slots=True)
class FiniteAction:
    """The known command and current control, before execution of a relative linear action."""

    kind: str
    control_before: float | tuple[float, float, float]
    target: float | tuple[float, float, float]
    basis_world_m: np.ndarray | None

    @classmethod
    def shape_key(cls, q, target, basis_world_m):
        return cls("set_shape_key", float(q), float(target), np.asarray(basis_world_m, dtype=np.float64))

    @classmethod
    def translation(cls, delta_world_m, control_before_m):
        return cls("translate", tuple(control_before_m), tuple(delta_world_m), None)

    def displacement(self, indices):
        if self.kind == "set_shape_key":
            return (self.target - self.control_before) * self.basis_world_m[indices]
        return np.broadcast_to(self.target, (*indices.shape, 3))


def _point_segment_sq(points, start, end):
    segment = end - start
    relative = points - start
    denominator = np.square(segment).sum(axis=-1)
    numerator = (relative * segment).sum(axis=-1)
    fraction = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0)
    return np.square(relative - np.clip(fraction, 0, 1)[..., None] * segment).sum(axis=-1)


def _inside(points, triangle, normal):
    sides = np.cross(triangle[_EDGE_NEXT] - triangle, points[:, None] - triangle)
    return (sides @ normal >= 0).all(axis=1)


def _vertex_to_face_sq(points, triangle, normal):
    boundary = _point_segment_sq(points[:, None], triangle, triangle[_EDGE_NEXT]).min(axis=1)
    normal_squared = normal @ normal
    if normal_squared == 0:
        return boundary.min()
    # Orientation tests are unchanged by projecting the point onto the face plane.
    plane = np.square((points - triangle[0]) @ normal) / normal_squared
    return np.minimum(boundary, np.where(_inside(points, triangle, normal), plane, np.inf)).min()


def _pierces_face(points, triangle, normal):
    signed = (points - triangle[0]) @ normal
    other = signed[_EDGE_NEXT]
    opposite_sides = ((signed >= 0) & (other <= 0)) | ((signed <= 0) & (other >= 0))
    crossing = opposite_sides & (signed != other)
    start, end = points[crossing], points[_EDGE_NEXT[crossing]]
    fraction = signed[crossing] / (signed[crossing] - other[crossing])
    return _inside(start + fraction[:, None] * (end - start), triangle, normal).any()


def _edge_interiors_sq(a, b):
    u = (a[_EDGE_NEXT] - a)[:, None]
    v = (b[_EDGE_NEXT] - b)[None, :]
    w = b[None, :] - a[:, None]
    normal = np.cross(u, v)
    denominator = np.square(normal).sum(axis=-1)
    s = (np.cross(w, v) * normal).sum(axis=-1)
    t = (np.cross(w, u) * normal).sum(axis=-1)
    valid = (denominator > 0) & (s >= 0) & (s <= denominator) & (t >= 0) & (t <= denominator)
    # At the two interior closest points, only the line separation normal remains.
    numerator = np.square((w * normal).sum(axis=-1))
    return np.divide(numerator, denominator, out=np.full_like(numerator, np.inf), where=valid).min()


def triangle_pair_distance(a, b):
    """Independent single-pair narrow phase, including crossing and degenerate triangles."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64) - a[0]
    a = a - a[0]
    scale = max(np.abs(a).max(), np.abs(b).max())
    if scale == 0:
        return 0.0
    a, b = a / scale, b / scale
    normal_a = np.cross(a[1] - a[0], a[2] - a[0])
    normal_b = np.cross(b[1] - b[0], b[2] - b[0])
    if _pierces_face(a, b, normal_b) or _pierces_face(b, a, normal_a):
        return 0.0
    distance_sq = min(_vertex_to_face_sq(a, b, normal_b), _vertex_to_face_sq(b, a, normal_a),
                      _edge_interiors_sq(a, b))
    return scale * sqrt(distance_sq)


def _witness_pair(moving, reference, witness, action):
    moving_vertices, moving_faces = moving
    reference_vertices, reference_faces = reference
    moving_face = moving_faces[witness.triangle_a]
    shift = action.displacement(moving_face)
    distance_after = triangle_pair_distance(moving_vertices[moving_face] + shift,
                                            reference_vertices[reference_faces[witness.triangle_b]])
    return distance_after - witness.distance_m, shift


def geometry_delta(moving, reference, witness, action):
    """Exact known finite action on today's two witness faces, with no global requery."""
    return _witness_pair(moving, reference, witness, action)[0]


def _indexed(mesh):
    vertices, triangles = mesh
    indices = np.unique(triangles)
    return vertices[indices], indices


def _chart_normal(witness, moving, reference):
    axis = np.asarray(witness.point_b) - witness.point_a
    length = np.linalg.norm(axis)
    if length > 0:
        return axis / length
    axis = reference.mean(axis=0) - moving.mean(axis=0)
    length = np.linalg.norm(axis)
    return axis / length if length > 0 else np.array([0.0, 0.0, 1.0])


def _chart(normal, moving):
    centered = moving - moving.mean(axis=0)
    perpendicular = centered - (centered @ normal)[:, None] * normal
    values, vectors = np.linalg.eigh(perpendicular.T @ perpendicular)
    if values[-1] - values[-2] <= _PCA_TIE * values[-1]:
        longitudinal = np.eye(3)[np.argmin(np.abs(normal))]
    else:
        longitudinal = vectors[:, -1]
    longitudinal = longitudinal - (longitudinal @ normal) * normal
    longitudinal /= np.linalg.norm(longitudinal)
    longitudinal *= 1 if longitudinal[np.argmax(np.abs(longitudinal))] >= 0 else -1
    return np.stack((normal, longitudinal, np.cross(normal, longitudinal)), axis=1)


def _support_sketch(moving, reference, axial_shift, gap):
    """Approximate projection support changes in common, unchanged current bins."""
    low = max(moving[:, 1].min(), reference[:, 1].min())
    high = min(moving[:, 1].max(), reference[:, 1].max())
    if high <= low:
        return (0.0,) * 6

    def select(points):
        along = points[:, 1]
        mask = (low <= along) & (along <= high)
        bins = ((along[mask] - low) * _SKETCH_BINS / (high - low)).astype(np.intp)
        return mask, np.minimum(bins, _SKETCH_BINS - 1)

    moving_mask, moving_bins = select(moving)
    ref_mask, ref_bins = select(reference)
    current = np.full(_SKETCH_BINS, -np.inf)
    estimate = np.full(_SKETCH_BINS, -np.inf)
    fixed = np.full(_SKETCH_BINS, np.inf)
    np.maximum.at(current, moving_bins, moving[moving_mask, 0])
    np.maximum.at(estimate, moving_bins, moving[moving_mask, 0] + axial_shift[moving_mask])
    np.minimum.at(fixed, ref_bins, reference[ref_mask, 0])
    valid = np.isfinite(current) & np.isfinite(fixed)
    count = np.count_nonzero(valid)
    if count == 0:
        return (0.0,) * 6
    before, changed = fixed[valid] - current[valid], fixed[valid] - estimate[valid]
    best = np.argmin(before)
    slack = np.partition(before, 1)[1] - before[best] if count > 1 else 0.0
    return (before[best] - gap, changed.min() - before[best], changed[best] - before[best],
            count / _SKETCH_BINS, slack, float(count > 1))


def action_features(moving, reference, witness, action):
    """Return 23 legal features plus meter scale; length features are divided by scale."""
    m, ids = _indexed(moving)
    r, _ = _indexed(reference)
    gap = witness.distance_m
    scale = max(gap, np.linalg.norm(np.ptp(m, axis=0)), np.linalg.norm(np.ptp(r, axis=0))) or 1.0
    normal = _chart_normal(witness, m, r)
    chart = _chart(normal, m)
    local_delta, face_shift = _witness_pair(moving, reference, witness, action)
    axial_shift = action.displacement(ids) @ normal
    origin = np.asarray(witness.point_a)
    m, r = (m - origin) @ chart, (r - origin) @ chart
    sketch_error, sketch_delta, fixed_delta, valid_fraction, slack, alternative = _support_sketch(
        m, r, axial_shift, gap)
    shape = action.kind == "set_shape_key"
    q = action.control_before if shape else 0.0
    dq = action.target - q if shape else 0.0
    features = np.asarray((gap / scale, local_delta / scale, float(shape), q, dq,
                           *(face_shift.mean(axis=0) @ chart / scale),
                           *(np.ptp(m, axis=0) / scale), *(np.ptp(r, axis=0) / scale),
                           sketch_error / scale, sketch_delta / scale, fixed_delta / scale,
                           valid_fraction, slack / scale, alternative,
                           axial_shift.min() / scale, axial_shift.max() / scale,
                           axial_shift.std() / scale))
    return features, scale


def command_group(action, *, normal=None, scale=None):
    """Explicit direction and magnitude groups for the conditional meter median."""
    if action.kind == "set_shape_key":
        directed = action.target - action.control_before
        magnitude = abs(directed)
        cutoff = 0.15
    else:
        directed = np.asarray(action.target) @ normal
        magnitude = np.linalg.norm(action.target) / scale
        cutoff = 0.02
    sign = int(np.sign(directed))
    band = 0 if magnitude == 0 else 1 + int(magnitude > cutoff)
    return action.kind, sign, band


class ConditionalConstant:
    """Train-only meter medians. Missing groups use same-kind then all-train medians."""

    def __init__(self, groups, train_labels_m):
        grouped, kinds = {}, {}
        labels = tuple(train_labels_m)
        for group, value in zip(groups, labels, strict=True):
            grouped.setdefault(group, []).append(value)
            kinds.setdefault(group[0], []).append(value)
        self.global_median_m = float(np.median(labels))
        self.by_kind_m = {kind: float(np.median(values)) for kind, values in kinds.items()}
        self.by_group_m = {group: float(np.median(values)) for group, values in grouped.items()}
        self.train_counts = {group: len(values) for group, values in grouped.items()}

    def predict(self, group):
        return self.by_group_m.get(group, self.by_kind_m.get(group[0], self.global_median_m))
