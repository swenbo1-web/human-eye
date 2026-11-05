"""Minimum Euclidean distance between indexed triangle surfaces in world meters."""

from dataclasses import dataclass
from math import inf

import numpy as np


_NEXT = np.array([1, 2, 0])
_CHILDREN = np.arange(2)
_LEAF_SIZE = 4
_NODE_BATCH = 1024
_PAIR_BATCH = 2048
_BOUND_ROUNDING = 1 + 32 * np.finfo(np.float64).eps


@dataclass(frozen=True, slots=True)
class SurfaceDistance:
    """Distance, input triangle row IDs, and corresponding world-meter points."""

    distance_m: float
    triangle_a: int | None
    triangle_b: int | None
    point_a: tuple[float, float, float] | None
    point_b: tuple[float, float, float] | None


@dataclass(slots=True)
class _Triangles:
    vertices: np.ndarray
    edges: np.ndarray
    directions: np.ndarray
    spans: np.ndarray
    direction_sq: np.ndarray
    normals: np.ndarray
    inward: np.ndarray
    low: np.ndarray
    high: np.ndarray


def _dot(a, b):
    return np.einsum("...i,...i->...", a, b)


def _length(vectors):
    return np.hypot(np.hypot(vectors[..., 0], vectors[..., 1]), vectors[..., 2])


def _divide(numerator, denominator):
    return np.divide(
        numerator, denominator, out=np.zeros_like(numerator), where=denominator != 0
    )


def _prepare_triangles(triangles):
    edges = triangles[:, _NEXT] - triangles
    # Power-of-two scaling preserves direction without squaring world lengths.
    _, exponent = np.frexp(np.max(np.abs(edges), axis=2))
    spans = np.ldexp(np.ones_like(exponent, dtype=np.float64), exponent - 1)
    directions = edges / spans[..., None]
    normals = np.cross(directions[:, 0], -directions[:, 2])
    normals = _divide(normals, _length(normals)[:, None])
    return _Triangles(
        triangles, edges, directions, spans, _dot(directions, directions), normals,
        np.cross(normals[:, None], directions), triangles.min(axis=1), triangles.max(axis=1),
    )


def _lower_distance(low_a, high_a, low_b, high_b):
    gap = np.maximum(np.maximum(low_a - high_b, low_b - high_a), 0)
    return _length(gap)


class SurfaceIndex:
    """Own a BVH over a trusted triangle topology and a snapshot of its surface.

    Vertices are float64 world coordinates in meters. Triangle indices refer to
    rows of the vertex array. Use update() for new vertex positions and construct
    a new index when topology changes. Serialize queries and updates to an index.
    """

    def __init__(self, vertices: np.ndarray, triangles: np.ndarray):
        count = len(triangles)
        self._order = np.arange(count)
        starts = []
        if count:
            points = vertices[triangles]
            centers = points.min(axis=1) * 0.5 + points.max(axis=1) * 0.5
            depth = ((count - 1) // _LEAF_SIZE).bit_length()

            def split(start, stop, remaining):
                if remaining == 0:
                    starts.append(start)
                    return
                rows = self._order[start:stop]
                locations = centers[rows]
                axis = np.argmax(np.ptp(locations, axis=0))
                half = len(rows) // 2
                rows[:] = rows[np.argpartition(locations[:, axis], half)]
                split(start, start + half, remaining - 1)
                split(start + half, stop, remaining - 1)

            split(0, count, depth)

        self._topology = np.asarray(triangles)[self._order]
        self._starts = np.asarray(starts, dtype=np.intp)
        if count:
            stops = np.r_[self._starts[1:], count]
            slots = np.arange(np.max(stops - self._starts))
            # Pad short leaves with their last face. All entries remain valid.
            self._leaves = np.minimum(self._starts[:, None] + slots, stops[:, None] - 1)
        self.update(vertices)

    def update(self, vertices: np.ndarray) -> None:
        """Gather the current surface and refit the original tree from its leaves."""
        packed = _prepare_triangles(vertices[self._topology])
        bounds = []
        if len(self._starts):
            low = np.minimum.reduceat(packed.low, self._starts, axis=0)
            high = np.maximum.reduceat(packed.high, self._starts, axis=0)
            bounds.append((low, high))
            while len(low) > 1:
                low = low.reshape(-1, 2, 3).min(axis=1)
                high = high.reshape(-1, 2, 3).max(axis=1)
                bounds.append((low, high))
        self._packed = packed
        self._bounds = bounds[::-1]


def _piercing_edge(vertices, edges, target, target_ids, offset):
    """Find an edge that crosses the target plane inside a nondegenerate face."""
    normals = target.normals[target_ids]
    heights = _dot(offset[:, :, 0], normals[:, None])
    ends = heights[:, _NEXT]
    rows, edge = np.nonzero(((heights < 0) & (ends > 0)) | ((heights > 0) & (ends < 0)))
    if not len(rows):
        return None
    t = heights[rows, edge] / (heights[rows, edge] - ends[rows, edge])
    start_offset = offset[rows, edge]
    stop_offset = offset[rows, _NEXT[edge]]
    at_crossing = (1 - t[:, None, None]) * start_offset + t[:, None, None] * stop_offset
    inside = np.all(_dot(at_crossing, target.inward[target_ids[rows]]) >= 0, axis=1)
    hits = np.flatnonzero(inside)
    if not len(hits):
        return None
    hit = hits[0]
    row, vertex = rows[hit], edge[hit]
    return row, vertices[row, vertex] + t[hit] * edges[row, vertex]


def _vertex_triangle(vertices, target, target_ids, offset):
    """Best source vertex against the interior, edges or vertices of a face."""
    normals = target.normals[target_ids]
    heights = _dot(offset[:, :, 0], normals[:, None])
    sides = _dot(offset, target.inward[target_ids, None])
    inside = np.all(sides >= 0, axis=2)
    inside &= np.any(normals != 0, axis=1)[:, None]
    face_distance = np.where(inside, np.abs(heights), inf)
    row, vertex = np.unravel_index(np.argmin(face_distance), face_distance.shape)
    best = face_distance[row, vertex]

    # An interior orthogonal projection already minimizes distance for that
    # source vertex. Only outside vertices need the three edge candidates.
    if best > 0:
        outside_row, outside_vertex = np.nonzero(~inside)
        if len(outside_row):
            ids = target_ids[outside_row]
            directions, spans = target.directions[ids], target.spans[ids]
            outside = offset[outside_row, outside_vertex]
            t = _divide(_dot(outside, directions), target.direction_sq[ids])
            np.clip(t, 0, spans, out=t)
            residual = outside - t[..., None] * directions
            residual = np.where((t == spans)[..., None], outside[:, _NEXT], residual)
            edge_distance = _length(residual)
            pair, edge = np.unravel_index(np.argmin(edge_distance), edge_distance.shape)
            if edge_distance[pair, edge] <= best:
                edge_row, edge_vertex = outside_row[pair], outside_vertex[pair]
                point = vertices[edge_row, edge_vertex]
                triangle = target.vertices[ids[pair]]
                parameter = t[pair, edge]
                if parameter == spans[pair, edge]:
                    witness = triangle[_NEXT[edge]]
                else:
                    witness = triangle[edge] + parameter * directions[pair, edge]
                return edge_distance[pair, edge], edge_row, point, witness

    point = vertices[row, vertex]
    triangle = target.vertices[target_ids[row]]
    # Signed side distances multiplied by their edge scales are proportional
    # to the projected point's barycentric weights, in opposite-vertex order.
    weights = sides[row, vertex]
    largest = weights.max()
    if largest > 0:
        face_spans = target.spans[target_ids[row]]
        weights = (weights / largest) * (face_spans / face_spans.max())
        weights /= weights.sum()
        witness = triangle[0] + weights[2] * (triangle[1] - triangle[0])
        witness += weights[0] * (triangle[2] - triangle[0])
    else:
        witness = point - heights[row, vertex] * normals[row]
    return best, row, point, witness


def _edge_edge(a, b, index_a, index_b, offset):
    """Best interior/interior pair. Vertex features cover parallel and end cases."""
    u, v = a.directions[index_a, :, None], b.directions[index_b, None]
    # Remove the common longitudinal component before forming cross products.
    # For almost parallel edges, the unshifted offset can be far larger than
    # their separation, amplifying cancellation in both the height and t.
    axis = np.argmax(np.abs(u), axis=-1, keepdims=True)
    pivot = np.take_along_axis(u, axis, axis=-1)
    v_factor = _divide(np.take_along_axis(v, axis, axis=-1), pivot)
    offset_factor = _divide(np.take_along_axis(offset, axis, axis=-1), pivot)
    shifted_v = v - v_factor * u
    shifted_offset = offset - offset_factor * u
    normal = np.cross(u, shifted_v)
    length = _length(normal)
    normal = _divide(normal, length[..., None])
    t = _divide(_dot(np.cross(shifted_offset, u), normal), length)
    interior_t = (t > 0) & (t < b.spans[index_b, None])
    # Solve the other parameter against the chosen point on B, so the two
    # witnesses share one longitudinal projection even at small angles.
    along_u = offset + np.where(interior_t, t, 0)[..., None] * v
    s = _divide(_dot(along_u, u), a.direction_sq[index_a, :, None])
    interior = interior_t & (s > 0) & (s < a.spans[index_a, :, None])
    distance = np.where(interior, np.abs(_dot(shifted_offset, normal)), inf)
    row, i, j = np.unravel_index(np.argmin(distance), distance.shape)
    best = distance[row, i, j]
    if best == inf:
        return best, row, None, None
    point_a = a.vertices[index_a[row], i] + s[row, i, j] * u[row, i, 0]
    point_b = b.vertices[index_b[row], j] + t[row, i, j] * v[row, 0, j]
    return best, row, point_a, point_b


def _closest_pairs(a, b, index_a, index_b):
    """Return distance in meters, packed face IDs and points for a nonempty batch."""
    vertices_a, vertices_b = a.vertices[index_a], b.vertices[index_b]
    # Pair-local differences avoid forming plane equations in world coordinates.
    offset = vertices_b[:, None] - vertices_a[:, :, None]
    overlap = np.flatnonzero(np.all(
        (a.low[index_a] <= b.high[index_b]) & (b.low[index_b] <= a.high[index_a]), axis=1
    ))
    if len(overlap):
        hit = _piercing_edge(
            vertices_a[overlap], a.edges[index_a[overlap]], b, index_b[overlap], -offset[overlap]
        )
        if hit is None:
            hit = _piercing_edge(
                vertices_b[overlap], b.edges[index_b[overlap]], a, index_a[overlap],
                offset[overlap].swapaxes(1, 2),
            )
        if hit is not None:
            row, point = hit
            row = overlap[row]
            return 0.0, index_a[row], index_b[row], point, point

    best, row, point_a, point_b = _vertex_triangle(vertices_a, b, index_b, -offset)
    if best > 0:
        reverse = _vertex_triangle(vertices_b, a, index_a, offset.swapaxes(1, 2))
        if reverse[0] < best:
            best, row, point_b, point_a = reverse
    if best > 0:
        edge = _edge_edge(a, b, index_a, index_b, offset)
        if edge[0] < best:
            best, row, point_a, point_b = edge
    if best == 0:
        point_b = point_a
    return best, index_a[row], index_b[row], point_a, point_b


def _children(a, b, depth_a, depth_b, ids_a, ids_b):
    if depth_a + 1 < len(a._bounds):
        ids_a = (2 * ids_a[:, None] + _CHILDREN).ravel()
        ids_b = np.repeat(ids_b, 2)
        depth_a += 1
    if depth_b + 1 < len(b._bounds):
        ids_b = (2 * ids_b[:, None] + _CHILDREN).ravel()
        ids_a = np.repeat(ids_a, 2)
        depth_b += 1
    return depth_a, depth_b, ids_a, ids_b


def _node_bounds(a, b, depth_a, depth_b, ids_a, ids_b):
    low_a, high_a = a._bounds[depth_a]
    low_b, high_b = b._bounds[depth_b]
    return _lower_distance(low_a[ids_a], high_a[ids_a], low_b[ids_b], high_b[ids_b])


def _face_pairs(a, b, ids_a, ids_b):
    faces_a, faces_b = a._leaves[ids_a], b._leaves[ids_b]
    return np.repeat(faces_a, faces_b.shape[1], axis=1).ravel(), np.tile(faces_b, (1, faces_a.shape[1])).ravel()


def _projected_bounds(index, axis, origin):
    """Current vertex intervals along a common query axis, refit bottom-up."""
    packed = index._packed
    projection = np.einsum("fvi,i->fv", packed.vertices - origin, axis)
    # Include subtraction as well as dot-product roundoff. At very large
    # world origins the interval becomes looser, never a stronger false bound.
    magnitude = np.maximum(np.abs(packed.low), np.abs(packed.high)).max(axis=0)
    error = 32 * np.finfo(np.float64).eps * np.dot(magnitude + np.abs(origin), np.abs(axis))
    low = np.nextafter(projection.min(axis=1) - error, -np.inf)
    high = np.nextafter(projection.max(axis=1) + error, np.inf)
    faces = low, high
    low = np.minimum.reduceat(low, index._starts)
    high = np.maximum.reduceat(high, index._starts)
    result = [(low, high)]
    while len(low) > 1:
        low = low.reshape(-1, 2).min(axis=1)
        high = high.reshape(-1, 2).max(axis=1)
        result.append((low, high))
    return result[::-1], faces


def _search(a, b):
    root = (0, 0, np.array([0]), np.array([0]))
    leaf_depths = (len(a._bounds) - 1, len(b._bounds) - 1)

    # Keep four cheap node candidates only while seeding a tighter upper bound.
    # The complete traversal below starts again at both roots; this seed does
    # not truncate the global search or exclude unvisited triangle pairs.
    depth_a, depth_b, ids_a, ids_b = root
    while (depth_a, depth_b) != leaf_depths:
        depth_a, depth_b, ids_a, ids_b = _children(a, b, depth_a, depth_b, ids_a, ids_b)
        nearest = np.argsort(_node_bounds(a, b, depth_a, depth_b, ids_a, ids_b))[:4]
        ids_a, ids_b = ids_a[nearest], ids_b[nearest]
    best = _closest_pairs(a._packed, b._packed, *_face_pairs(a, b, ids_a, ids_b))
    if best[0] == 0 or leaf_depths == (0, 0):
        return best

    origin = np.asarray(best[3])
    delta = np.subtract(best[4], origin)
    axis = _divide(delta, np.max(np.abs(delta)))
    axis_length = np.nextafter(_length(axis) * _BOUND_ROUNDING, np.inf)
    projected_a, faces_projection_a = _projected_bounds(a, axis, origin)
    projected_b, faces_projection_b = _projected_bounds(b, axis, origin)

    stack = [root]
    while stack:
        depth_a, depth_b, ids_a, ids_b = stack.pop()
        low_a, high_a = projected_a[depth_a]
        low_b, high_b = projected_b[depth_b]
        gap = np.maximum(np.maximum(low_a[ids_a] - high_b[ids_b],
                                    low_b[ids_b] - high_a[ids_a]), 0)
        projected = np.nextafter(np.nextafter(gap, 0) / axis_length, 0)
        bound = np.maximum(_node_bounds(a, b, depth_a, depth_b, ids_a, ids_b), projected)
        eligible = bound <= best[0] * _BOUND_ROUNDING
        if not np.any(eligible):
            continue
        ids_a, ids_b = ids_a[eligible], ids_b[eligible]
        if (depth_a, depth_b) != leaf_depths:
            da, db, children_a, children_b = _children(a, b, depth_a, depth_b, ids_a, ids_b)
            for start in range(0, len(children_a), _NODE_BATCH):
                stop = start + _NODE_BATCH
                stack.append((da, db, children_a[start:stop], children_b[start:stop]))
            continue

        faces_a, faces_b = _face_pairs(a, b, ids_a, ids_b)
        ta, tb = a._packed, b._packed
        bound = _lower_distance(ta.low[faces_a], ta.high[faces_a], tb.low[faces_b], tb.high[faces_b])
        low_a, high_a = faces_projection_a
        low_b, high_b = faces_projection_b
        gap = np.maximum(np.maximum(low_a[faces_a] - high_b[faces_b],
                                    low_b[faces_b] - high_a[faces_a]), 0)
        bound = np.maximum(bound, np.nextafter(np.nextafter(gap, 0) / axis_length, 0))
        possible = bound <= best[0] * _BOUND_ROUNDING
        faces_a, faces_b = faces_a[possible], faces_b[possible]
        bound = bound[possible]
        if len(bound) <= _PAIR_BATCH or np.min(bound) == np.max(bound):
            for start in range(0, len(faces_a), _PAIR_BATCH):
                stop = start + _PAIR_BATCH
                candidate = _closest_pairs(ta, tb, faces_a[start:stop], faces_b[start:stop])
                if candidate[0] < best[0]:
                    best = candidate
                    if best[0] == 0:
                        return best
            continue
        order = np.argsort(bound)
        faces_a, faces_b, bound = faces_a[order], faces_b[order], bound[order]
        start, count = 0, 32
        while start < len(bound):
            stop = start + count
            keep = bound[start:stop] <= best[0] * _BOUND_ROUNDING
            if not np.any(keep):
                break
            candidate = _closest_pairs(ta, tb, faces_a[start:stop][keep], faces_b[start:stop][keep])
            if candidate[0] < best[0]:
                best = candidate
                if best[0] == 0:
                    return best
            start, count = stop, min(4 * count, _PAIR_BATCH)
    return best


def surface_distance(a: SurfaceIndex, b: SurfaceIndex) -> SurfaceDistance:
    """Return the minimum surface distance and one pair of real witnesses.

    Empty surfaces return infinity and four None fields. Contact/intersection
    has distance zero. A nested surface can have positive separation.
    """
    if not a._bounds or not b._bounds:
        return SurfaceDistance(inf, None, None, None, None)
    distance, i, j, point_a, point_b = _search(a, b)
    return SurfaceDistance(
        float(distance), int(a._order[i]), int(b._order[j]),
        tuple(map(float, point_a)), tuple(map(float, point_b)),
    )
