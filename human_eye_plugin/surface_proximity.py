"""Finite exact distances between the captured binary64 triangle surfaces.

The small intersection predicates below reuse surface_geometry's formulas with
checked arithmetic. This module has no solid qualification or action callers.
"""
from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction
from functools import cmp_to_key
import heapq
import math
from numbers import Integral

from .telemetry import span


MAX_FACES = 4096
MAX_TRIANGLE_PAIRS = 16384
MAX_NARROW_PHASE_PAIRS = MAX_TRIANGLE_PAIRS
MAX_WORK_UNITS = MAX_FACES * 32 + MAX_TRIANGLE_PAIRS * 64
LINEAR_PAIR_LIMIT = 256
MAX_BITS = 4096
MAX_EXACT_SOURCE_BYTES = 1024
_MAX_SCRATCH_BITS = 2 * MAX_BITS + 1
METHOD = 'exact_binary64_triangle_surface_hulls_v3'
_PUBLICATION_TOLERANCE = Fraction.from_float(1e-9)
SPATIAL_METHOD = 'exact_sufficient_spatial_relation_v1'
SPATIAL_SCOPE = 'referenced_triangle_unions_and_their_vertex_convex_hulls'
_SURFACE_RESOURCE_STOPS = frozenset({'surface_work_budget', 'surface_pair_budget',
                                      'surface_geometry_work_limit'})
_CLOSED_RESOURCE_STOPS = frozenset({'closed_solid_work_budget', 'closed_solid_pair_budget',
    'closed_solid_ray_budget', 'closed_solid_vertex_budget', 'closed_solid_geometry_work_limit'})


class _DomainError(ValueError):
    pass


def _bounded(value):
    if type(value) is int:
        if value.bit_length() > MAX_BITS:
            raise _DomainError('surface_exact_bit_budget')
        return value
    numerator = value.numerator if isinstance(value, Fraction) else value
    denominator = value.denominator if isinstance(value, Fraction) else 1
    if abs(numerator).bit_length() > MAX_BITS or denominator.bit_length() > MAX_BITS:
        raise _DomainError('surface_exact_bit_budget')
    return value


def _fraction(numerator, denominator=1):
    _bounded(numerator)
    _bounded(denominator)
    return _bounded(Fraction(numerator, denominator))


_FAST_COORD_LIMIT = 1 << 500


def _sub(a, b):
    ax, ay, az = a
    bx, by, bz = b
    return (_bounded(ax - bx), _bounded(ay - by), _bounded(az - bz))


def _add(a, b):
    ax, ay, az = a
    bx, by, bz = b
    return (_bounded(ax + bx), _bounded(ay + by), _bounded(az + bz))


def _mul(a, scale):
    ax, ay, az = a
    return (_bounded(ax * scale), _bounded(ay * scale), _bounded(az * scale))


def _dot(a, b):
    ax, ay, az = a
    bx, by, bz = b
    return _bounded(_bounded(_bounded(ax * bx) + _bounded(ay * by)) + _bounded(az * bz))


def _cross(a, b):
    ax, ay, az = a
    bx, by, bz = b
    return (
        _bounded(_bounded(ay * bz) - _bounded(az * by)),
        _bounded(_bounded(az * bx) - _bounded(ax * bz)),
        _bounded(_bounded(ax * by) - _bounded(ay * bx)),
    )


def _normal(triangle):
    return _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0]))


def _fast_cross(a, b):
    ax, ay, az = a
    bx, by, bz = b
    return (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)


def _fast_bary(triangle):
    p0, p1, p2 = triangle[0]
    n = triangle[1]
    p0x, p0y, p0z = p0
    p1x, p1y, p1z = p1
    p2x, p2y, p2z = p2
    nx, ny, nz = n
    d2x, d2y, d2z = p2x - p0x, p2y - p0y, p2z - p0z
    d1x, d1y, d1z = p1x - p0x, p1y - p0y, p1z - p0z
    return (
        (d2y * nz - d2z * ny, d2z * nx - d2x * nz, d2x * ny - d2y * nx),
        (ny * d1z - nz * d1y, nz * d1x - nx * d1z, nx * d1y - ny * d1x),
    )


def _bounds_fit_fast(side):
    limit = _FAST_COORD_LIMIT
    for tri in side:
        for lo, hi in tri[4]:
            if lo <= -limit or hi >= limit:
                return False
    return True


def _orient(a, b, c, axes):
    x, y = axes
    return _bounded(_bounded(_bounded(b[x] - a[x]) * _bounded(c[y] - a[y]))
                    - _bounded(_bounded(b[y] - a[y]) * _bounded(c[x] - a[x])))


def _clip_coplanar(a, b, normal, budget):
    # Same closed convex clipping formula as surface_geometry.clip_coplanar.
    drop = max(range(3), key=lambda k: abs(normal[k]))
    axes = tuple(k for k in range(3) if k != drop)
    sign = 1 if _orient(*b, axes) > 0 else -1
    polygon = list(a)
    for i in range(3):
        budget.tick('predicate_steps', 1 + len(polygon))
        if not polygon:
            break
        c, d = b[i], b[(i + 1) % 3]
        result = []
        for j, point in enumerate(polygon):
            previous = polygon[j - 1]
            current_side = sign * _orient(c, d, point, axes)
            previous_side = sign * _orient(c, d, previous, axes)
            if (current_side >= 0) != (previous_side >= 0):
                parameter = _fraction(previous_side, _bounded(previous_side - current_side))
                result.append(_add(previous, _mul(_sub(point, previous), parameter)))
            if current_side >= 0:
                result.append(point)
        polygon = list(dict.fromkeys(result))
    return polygon


def _plane_slice(triangle, distances):
    # Same edge/plane construction as surface_geometry.plane_slice.
    points = [point for point, distance in zip(triangle, distances) if distance == 0]
    for i in range(3):
        j = (i + 1) % 3
        if distances[i] * distances[j] < 0:
            parameter = _fraction(distances[i], _bounded(distances[i] - distances[j]))
            points.append(_add(triangle[i], _mul(_sub(triangle[j], triangle[i]), parameter)))
    return list(dict.fromkeys(points))


def _plane_distances(points, origin, normal, budget, *, fast_ints=False):
    budget.tick('plane_projection_tests', len(points))
    if fast_ints:
        ox, oy, oz = origin
        nx, ny, nz = normal
        if len(points) == 3:
            p0, p1, p2 = points
            return (
                (p0[0] - ox) * nx + (p0[1] - oy) * ny + (p0[2] - oz) * nz,
                (p1[0] - ox) * nx + (p1[1] - oy) * ny + (p1[2] - oz) * nz,
                (p2[0] - ox) * nx + (p2[1] - oy) * ny + (p2[2] - oz) * nz,
            )
        return tuple((p[0] - ox) * nx + (p[1] - oy) * ny + (p[2] - oz) * nz for p in points)
    return tuple(_dot(normal, _sub(point, origin)) for point in points)


def _intersection_with_planes(a, b, normal_a, normal_b, budget, *, plane_distances=None, fast_ints=False):
    # Same bidirectional slices and common-line interval as the existing kernel.
    da, db = (None, None) if plane_distances is None else plane_distances
    if da is None:
        da = _plane_distances(b, a[0], normal_a, budget, fast_ints=fast_ints)
    if (da[0] > 0 and da[1] > 0 and da[2] > 0) or (da[0] < 0 and da[1] < 0 and da[2] < 0):
        return [], da, db
    if db is None:
        db = _plane_distances(a, b[0], normal_b, budget, fast_ints=fast_ints)
    if (db[0] > 0 and db[1] > 0 and db[2] > 0) or (db[0] < 0 and db[1] < 0 and db[2] < 0):
        return [], da, db
    axis = _fast_cross(normal_a, normal_b) if fast_ints else _cross(normal_a, normal_b)
    if not any(axis):
        return (_clip_coplanar(a, b, normal_a, budget) if not any(da) else []), da, db
    pa, pb = _plane_slice(a, db), _plane_slice(b, da)
    if not pa or not pb:
        return [], da, db
    k = max(range(3), key=lambda index: abs(axis[index]))
    pa.sort(key=lambda point: point[k])
    pb.sort(key=lambda point: point[k])
    left = max(pa[0], pb[0], key=lambda point: point[k])
    right = min(pa[-1], pb[-1], key=lambda point: point[k])
    points = [] if left[k] > right[k] else list(dict.fromkeys((left, right)))
    return points, da, db


def _intersection(a, b, normal_a, normal_b, budget, *, plane_distances=None):
    return _intersection_with_planes(a, b, normal_a, normal_b, budget,
                                     plane_distances=plane_distances)[0]


_WORK_STAGES = {
    name: 'surface_proximity_' + name for name in (
        'validated_faces', 'referenced_vertices', 'triangle_pairs',
        'intersection_tests', 'point_face_tests', 'point_edge_tests',
        'edge_edge_tests', 'predicate_steps', 'aabb_bound_tests',
        'aabb_pruned_pairs', 'work_units', 'prepared_triangles',
        'tree_builds', 'tree_build_units', 'node_pair_visits',
        'leaf_pair_visits', 'queue_pushes', 'queue_bound_tests',
        'narrow_phase_pairs', 'plane_projection_tests', 'plane_bound_tests',
        'plane_pruned_pairs', 'subtree_pruned_pairs', 'surface_bvh_build',
        'pair', 'pair_budget', 'triangle_prepare',
        'witness_projection', 'witness_projection_tests',
        'witness_projection_direction_builds', 'witness_projection_tri_dots',
        'witness_projection_node_visits', 'witness_projection_completed_exact',
        'bvh_compile', 'face_validate', 'mesh_cache_affine_fallback',
    )
}


_WORK_STAGES_GET = _WORK_STAGES.get


class _Work:
    __slots__ = ('checkpoint', 'counts')

    def __init__(self, checkpoint, diagnostics):
        self.checkpoint = checkpoint
        self.counts = diagnostics if diagnostics is not None else {}
        self.counts.clear()
        self.counts.update(validated_faces=0, referenced_vertices=0, triangle_pairs=0,
                           intersection_tests=0, point_face_tests=0,
                           point_edge_tests=0, edge_edge_tests=0, predicate_steps=0,
                           aabb_bound_tests=0, aabb_pruned_pairs=0,
                           work_units=0, prepared_triangles=0, tree_builds=0,
                           tree_build_units=0, node_pair_visits=0, leaf_pair_visits=0,
                           queue_pushes=0, queue_bound_tests=0, narrow_phase_pairs=0,
                           plane_projection_tests=0, plane_bound_tests=0,
                           plane_pruned_pairs=0, subtree_pruned_pairs=0, shared_trees=False,
                           support_direction_components=0, support_source_vertices=0,
                           support_vertex_dots=0)

    def consume(self, amount, stage):
        cp = _WORK_STAGES_GET(stage)
        self.checkpoint(cp if cp is not None else 'surface_proximity_' + stage)
        counts = self.counts
        new_work = counts['work_units'] + amount
        if new_work > MAX_WORK_UNITS:
            raise _DomainError('surface_work_budget')
        counts['work_units'] = new_work
        if stage == 'surface_bvh_build':
            counts['tree_build_units'] += amount

    def tick(self, kind, amount=1):
        cp = _WORK_STAGES_GET(kind)
        self.checkpoint(cp if cp is not None else 'surface_proximity_' + kind)
        counts = self.counts
        new_work = counts['work_units'] + amount
        if new_work > MAX_WORK_UNITS:
            raise _DomainError('surface_work_budget')
        counts['work_units'] = new_work
        try:
            counts[kind] += amount
        except KeyError:
            counts[kind] = amount

    def narrow_pair(self):
        if self.counts['narrow_phase_pairs'] >= MAX_NARROW_PHASE_PAIRS:
            self.checkpoint('surface_proximity_pair_budget')
            raise _DomainError('surface_pair_budget')
        self.tick('narrow_phase_pairs')


_MESH_CACHE_MAX_ENTRIES = 256


def _numpy_2d_list(array, allowed_kinds):
    if type(array).__module__ == 'numpy':
        dtype = getattr(array, 'dtype', None)
        if dtype is not None and dtype.kind in allowed_kinds and getattr(array, 'ndim', 0) == 2 and array.shape[1] == 3:
            return array.tolist()
    return None


def _is_numpy_2d_vertices(array):
    if type(array).__module__ == 'numpy':
        dtype = getattr(array, 'dtype', None)
        if dtype is not None and dtype.kind in ('f', 'i', 'u') and getattr(array, 'ndim', 0) == 2:
            if array.shape[1] != 3:
                raise _DomainError('surface_nonfinite_vertex')
            return True
    return False


def _read_vertex_xyz(verts, index, is_np_2d):
    if is_np_2d:
        item = verts.item
        vx = float(item((index, 0)))
        vy = float(item((index, 1)))
        vz = float(item((index, 2)))
    else:
        values = verts[index]
        if len(values) != 3:
            raise _DomainError('surface_nonfinite_vertex')
        vx, vy, vz = values[0], values[1], values[2]
        if type(vx) is not float:
            vx = float(vx)
        if type(vy) is not float:
            vy = float(vy)
        if type(vz) is not float:
            vz = float(vz)
    if not (math.isfinite(vx) and math.isfinite(vy) and math.isfinite(vz)):
        raise _DomainError('surface_nonfinite_vertex')
    return vx, vy, vz


def _admit_one(mesh, tick, valid_int_types, *, checkpoint=None, verts=None, faces=None):
    verts_src = mesh.vertices if verts is None else verts
    faces_src = mesh.faces if faces is None else faces
    num_verts = len(verts_src)
    out_faces, used, incidence = [], set(), {}
    add_used = used.add
    if checkpoint is not None:
        checkpoint('surface_proximity_validated_faces')
    raw_faces = _numpy_2d_list(faces_src, ('i', 'u'))
    face_iter = raw_faces if raw_faces is not None else faces_src
    for row in face_iter:
        tick('validated_faces')
        if len(row) != 3:
            raise _DomainError('surface_invalid_triangle_indices')
        a, b, c = row[0], row[1], row[2]
        if type(a) is int and type(b) is int and type(c) is int:
            if not (0 <= a < num_verts and 0 <= b < num_verts and 0 <= c < num_verts):
                raise _DomainError('surface_invalid_triangle_indices')
        else:
            for index in (a, b, c):
                t = type(index)
                if t not in valid_int_types:
                    if not isinstance(index, Integral) or isinstance(index, bool):
                        raise _DomainError('surface_invalid_triangle_indices')
                    valid_int_types.add(t)
                if not 0 <= index < num_verts:
                    raise _DomainError('surface_invalid_triangle_indices')
            a, b, c = int(a), int(b), int(c)
        out_faces.append((a, b, c))
        add_used(a)
        add_used(b)
        add_used(c)
        e0 = (a, b) if a <= b else (b, a)
        e1 = (b, c) if b <= c else (c, b)
        e2 = (c, a) if c <= a else (a, c)
        incidence[e0] = incidence.get(e0, 0) + 1
        incidence[e1] = incidence.get(e1, 0) + 1
        incidence[e2] = incidence.get(e2, 0) + 1
    boundary = 0
    nonmanifold = 0
    for count in incidence.values():
        if count == 1:
            boundary += 1
        elif count > 2:
            nonmanifold += 1
    return (mesh, out_faces, sorted(used)), dict(boundary_edge_count=boundary, nonmanifold_edge_count=nonmanifold)


def _admit(meshes, budget):
    sizes = [len(mesh.faces) for mesh in meshes]
    if not all(sizes) or sum(sizes) > MAX_FACES:
        raise _DomainError('surface_geometry_work_limit')
    records, topology = [], []
    tick = budget.tick
    checkpoint = budget.checkpoint
    valid_int_types = {int}
    for mesh in meshes:
        rec, topo = _admit_one(mesh, tick, valid_int_types, checkpoint=checkpoint)
        records.append(rec)
        topology.append(topo)
    return records, topology


def _float_dyadic(value):
    if value == 0.0:
        return 0, 0
    m, e = math.frexp(value)
    mant = int(math.ldexp(m, 53))
    tz = (mant & -mant).bit_length() - 1
    return mant >> tz, e - 53 + tz


def _sub_dyadic(a, b):
    m1, e1 = a
    m0, e0 = b
    if m0 == 0:
        return m1, e1
    if m1 == 0:
        return -m0, e0
    if e1 >= e0:
        diff = (m1 << (e1 - e0)) - m0
        min_e = e0
    else:
        diff = m1 - (m0 << (e0 - e1))
        min_e = e1
    if diff == 0:
        return 0, 0
    tz = (diff & -diff).bit_length() - 1
    return diff >> tz, min_e + tz


def _build_fast_triangles(faces, integers, budget=None):
    triangles = []
    append = triangles.append
    checkpoint = budget.checkpoint if budget is not None else None
    tick = budget.tick if budget is not None else None
    for i0, i1, i2 in faces:
        if checkpoint is not None:
            checkpoint('surface_proximity_triangle_prepare')
            tick('prepared_triangles')
        p0 = integers[i0]
        p1 = integers[i1]
        p2 = integers[i2]
        p0x, p0y, p0z = p0
        p1x, p1y, p1z = p1
        p2x, p2y, p2z = p2
        d1x, d1y, d1z = p1x - p0x, p1y - p0y, p1z - p0z
        d2x, d2y, d2z = p2x - p0x, p2y - p0y, p2z - p0z
        nx = d1y * d2z - d1z * d2y
        ny = d1z * d2x - d1x * d2z
        nz = d1x * d2y - d1y * d2x
        if nx or ny or nz:
            points = (p0, p1, p2)
            normal = (nx, ny, nz)
            squared = nx * nx + ny * ny + nz * nz
            d3x, d3y, d3z = p0x - p2x, p0y - p2y, p0z - p2z
            d23x, d23y, d23z = p2x - p1x, p2y - p1y, p2z - p1z
            edges = [
                (p0, p1, (d1x, d1y, d1z), d1x * d1x + d1y * d1y + d1z * d1z),
                (p1, p2, (d23x, d23y, d23z), d23x * d23x + d23y * d23y + d23z * d23z),
                (p2, p0, (d3x, d3y, d3z), d3x * d3x + d3y * d3y + d3z * d3z),
            ]
            bounds = (
                (min(p0x, p1x, p2x), max(p0x, p1x, p2x)),
                (min(p0y, p1y, p2y), max(p0y, p1y, p2y)),
                (min(p0z, p1z, p2z), max(p0z, p1z, p2z)),
            )
        else:
            normal = (0, 0, 0)
            squared = 0
            start = min(p0, p1, p2)
            end = max(p0, p1, p2)
            if start == end:
                points = (start,)
                edges = []
                sx, sy, sz = start
                bounds = ((sx, sx), (sy, sy), (sz, sz))
            else:
                points = (start, end)
                dx, dy, dz = end[0] - start[0], end[1] - start[1], end[2] - start[2]
                edges = [(start, end, (dx, dy, dz), dx * dx + dy * dy + dz * dz)]
                bounds = (
                    (start[0], end[0]) if start[0] <= end[0] else (end[0], start[0]),
                    (start[1], end[1]) if start[1] <= end[1] else (end[1], start[1]),
                    (start[2], end[2]) if start[2] <= end[2] else (end[2], start[2]),
                )
        append((points, normal, squared, edges, bounds))
    return triangles


def _prepare_triangles_from_relative(relative, exponent, budget, *, holder=None):
    factor = _bounded(1 << exponent)
    limit = _FAST_COORD_LIMIT
    prepared = []
    retained = [] if holder is not None else None
    checkpoint = budget.checkpoint
    tick = budget.tick
    for faces, coordinates in relative:
        integers = {}
        fast_side = True
        for index, (dx, dy, dz) in coordinates.items():
            checkpoint('surface_proximity_referenced_vertices')
            ix = dx[0] << (exponent + dx[1]) if dx[0] else 0
            iy = dy[0] << (exponent + dy[1]) if dy[0] else 0
            iz = dz[0] << (exponent + dz[1]) if dz[0] else 0
            if ix <= -limit or ix >= limit or iy <= -limit or iy >= limit or iz <= -limit or iz >= limit:
                fast_side = False
                _bounded(ix)
                _bounded(iy)
                _bounded(iz)
            integers[index] = (ix, iy, iz)
        if fast_side:
            triangles = _build_fast_triangles(faces, integers, budget=budget)
        else:
            triangles = []
            for face in faces:
                checkpoint('surface_proximity_triangle_prepare')
                tick('prepared_triangles')
                points = tuple(integers[index] for index in face)
                normal = _normal(points)
                if not any(normal):
                    start, end = min(points), max(points)
                    points = (start,) if start == end else (start, end)
                squared = _dot(normal, normal)
                edges = []
                for i in range(3 if squared else len(points) - 1):
                    start, end = points[i], points[(i + 1) % len(points)]
                    delta = _sub(end, start)
                    edges.append((start, end, delta, _dot(delta, delta)))
                bounds = tuple((min(point[k] for point in points),
                                max(point[k] for point in points)) for k in range(3))
                triangles.append((points, normal, squared, edges, bounds))
        prepared.append(triangles)
        if retained is not None:
            retained.append(integers)
    if holder is not None:
        holder['coordinates'] = tuple(retained)
    return factor, prepared


def _integer_frame(records, budget, *, holder=None):
    """Exact binary64-to-integer common-exponent frame (fast bounded-spread path + arbitrary-exponent fallback)."""
    verts_info = []
    for mesh, _, _ in records:
        verts = mesh.vertices
        verts_info.append((verts, _is_numpy_2d_vertices(verts)))
    first_verts, first_np = verts_info[0]
    budget.checkpoint('surface_proximity_referenced_vertices')
    fx, fy, fz = _read_vertex_xyz(first_verts, records[0][2][0], first_np)
    origin = (_bounded(Fraction.from_float(fx)),
              _bounded(Fraction.from_float(fy)),
              _bounded(Fraction.from_float(fz)))

    frexp = math.frexp
    ldexp = math.ldexp
    isfinite = math.isfinite
    tick = budget.tick
    checkpoint = budget.checkpoint

    min_e = None
    max_e = None
    if fx != 0.0:
        m, e = frexp(fx); om0 = int(ldexp(m, 53)); oe0 = e - 53
        min_e = max_e = oe0
    else:
        om0 = oe0 = 0
    if fy != 0.0:
        m, e = frexp(fy); om1 = int(ldexp(m, 53)); oe1 = e - 53
        if min_e is None: min_e = max_e = oe1
        else:
            if oe1 < min_e: min_e = oe1
            if oe1 > max_e: max_e = oe1
    else:
        om1 = oe1 = 0
    if fz != 0.0:
        m, e = frexp(fz); om2 = int(ldexp(m, 53)); oe2 = e - 53
        if min_e is None: min_e = max_e = oe2
        else:
            if oe2 < min_e: min_e = oe2
            if oe2 > max_e: max_e = oe2
    else:
        om2 = oe2 = 0

    raw_sides = []
    for (_, faces, indices), (verts, is_np) in zip(records, verts_info):
        raw_coords = []
        app = raw_coords.append
        if is_np:
            item = verts.item
            for index in indices:
                tick('referenced_vertices')
                vx = float(item((index, 0)))
                vy = float(item((index, 1)))
                vz = float(item((index, 2)))
                if not (isfinite(vx) and isfinite(vy) and isfinite(vz)):
                    raise _DomainError('surface_nonfinite_vertex')
                if vx != 0.0:
                    m, e = frexp(vx); mx = int(ldexp(m, 53)); ex = e - 53
                    if min_e is None: min_e = max_e = ex
                    else:
                        if ex < min_e: min_e = ex
                        if ex > max_e: max_e = ex
                else:
                    mx = ex = 0
                if vy != 0.0:
                    m, e = frexp(vy); my = int(ldexp(m, 53)); ey = e - 53
                    if min_e is None: min_e = max_e = ey
                    else:
                        if ey < min_e: min_e = ey
                        if ey > max_e: max_e = ey
                else:
                    my = ey = 0
                if vz != 0.0:
                    m, e = frexp(vz); mz = int(ldexp(m, 53)); ez = e - 53
                    if min_e is None: min_e = max_e = ez
                    else:
                        if ez < min_e: min_e = ez
                        if ez > max_e: max_e = ez
                else:
                    mz = ez = 0
                app((index, mx, ex, my, ey, mz, ez))
        else:
            for index in indices:
                tick('referenced_vertices')
                values = verts[index]
                if len(values) != 3:
                    raise _DomainError('surface_nonfinite_vertex')
                vx, vy, vz = values[0], values[1], values[2]
                if type(vx) is not float: vx = float(vx)
                if type(vy) is not float: vy = float(vy)
                if type(vz) is not float: vz = float(vz)
                if not (isfinite(vx) and isfinite(vy) and isfinite(vz)):
                    raise _DomainError('surface_nonfinite_vertex')
                if vx != 0.0:
                    m, e = frexp(vx); mx = int(ldexp(m, 53)); ex = e - 53
                    if min_e is None: min_e = max_e = ex
                    else:
                        if ex < min_e: min_e = ex
                        if ex > max_e: max_e = ex
                else:
                    mx = ex = 0
                if vy != 0.0:
                    m, e = frexp(vy); my = int(ldexp(m, 53)); ey = e - 53
                    if min_e is None: min_e = max_e = ey
                    else:
                        if ey < min_e: min_e = ey
                        if ey > max_e: max_e = ey
                else:
                    my = ey = 0
                if vz != 0.0:
                    m, e = frexp(vz); mz = int(ldexp(m, 53)); ez = e - 53
                    if min_e is None: min_e = max_e = ez
                    else:
                        if ez < min_e: min_e = ez
                        if ez > max_e: max_e = ez
                else:
                    mz = ez = 0
                app((index, mx, ex, my, ey, mz, ez))
        raw_sides.append((faces, indices, raw_coords))

    if min_e is None:
        min_e = max_e = 0

    if max_e - min_e <= 900 and -min_e <= 900:
        E_upper = 0 if min_e >= 0 else -min_e
        ox_u = om0 << (E_upper + oe0) if om0 else 0
        oy_u = om1 << (E_upper + oe1) if om1 else 0
        oz_u = om2 << (E_upper + oe2) if om2 else 0
        or_all = 0
        shifted_sides = []
        for faces, indices, raw_coords in raw_sides:
            sc = []
            sapp = sc.append
            for index, mx, ex, my, ey, mz, ez in raw_coords:
                dx_u = (mx << (E_upper + ex) if mx else 0) - ox_u
                dy_u = (my << (E_upper + ey) if my else 0) - oy_u
                dz_u = (mz << (E_upper + ez) if mz else 0) - oz_u
                or_all |= dx_u | dy_u | dz_u
                sapp((index, dx_u, dy_u, dz_u))
            shifted_sides.append((faces, indices, sc))

        common_tz = E_upper if or_all == 0 else min(E_upper, (or_all & -or_all).bit_length() - 1)
        exponent = E_upper - common_tz
        factor = _bounded(1 << exponent)
        limit = _FAST_COORD_LIMIT
        prepared = []
        retained = [] if holder is not None else None
        for faces, indices, sc in shifted_sides:
            max_idx = indices[-1] if indices else -1
            use_list = (holder is None and 0 <= max_idx < 65536 and max_idx < 4 * len(indices))
            integers = [None] * (max_idx + 1) if use_list else {}
            fast_side = True
            if common_tz:
                for index, dx_u, dy_u, dz_u in sc:
                    checkpoint('surface_proximity_referenced_vertices')
                    ix = dx_u >> common_tz
                    iy = dy_u >> common_tz
                    iz = dz_u >> common_tz
                    if ix <= -limit or ix >= limit or iy <= -limit or iy >= limit or iz <= -limit or iz >= limit:
                        fast_side = False
                        _bounded(ix); _bounded(iy); _bounded(iz)
                    integers[index] = (ix, iy, iz)
            else:
                for index, ix, iy, iz in sc:
                    checkpoint('surface_proximity_referenced_vertices')
                    if ix <= -limit or ix >= limit or iy <= -limit or iy >= limit or iz <= -limit or iz >= limit:
                        fast_side = False
                        _bounded(ix); _bounded(iy); _bounded(iz)
                    integers[index] = (ix, iy, iz)
            if fast_side:
                triangles = _build_fast_triangles(faces, integers, budget=budget)
            else:
                triangles = []
                for face in faces:
                    checkpoint('surface_proximity_triangle_prepare')
                    tick('prepared_triangles')
                    points = tuple(integers[index] for index in face)
                    normal = _normal(points)
                    if not any(normal):
                        start, end = min(points), max(points)
                        points = (start,) if start == end else (start, end)
                    squared = _dot(normal, normal)
                    edges = []
                    for i in range(3 if squared else len(points) - 1):
                        start, end = points[i], points[(i + 1) % len(points)]
                        delta = _sub(end, start)
                        edges.append((start, end, delta, _dot(delta, delta)))
                    bounds = tuple((min(point[k] for point in points),
                                    max(point[k] for point in points)) for k in range(3))
                    triangles.append((points, normal, squared, edges, bounds))
            prepared.append(triangles)
            if retained is not None:
                retained.append(integers)
        if holder is not None:
            holder['coordinates'] = tuple(retained)
        return origin, factor, prepared

    def _norm_dy(m_raw, e_raw):
        if m_raw == 0:
            return 0, 0
        tz = (m_raw & -m_raw).bit_length() - 1
        return m_raw >> tz, e_raw + tz

    o0 = _norm_dy(om0, oe0)
    o1 = _norm_dy(om1, oe1)
    o2 = _norm_dy(om2, oe2)
    relative, exponent = [], 0
    for faces, _, raw_coords in raw_sides:
        coordinates = {}
        for index, mx, ex, my, ey, mz, ez in raw_coords:
            dx = _sub_dyadic(_norm_dy(mx, ex), o0)
            dy = _sub_dyadic(_norm_dy(my, ey), o1)
            dz = _sub_dyadic(_norm_dy(mz, ez), o2)
            if dx[0] and -dx[1] > exponent: exponent = -dx[1]
            if dy[0] and -dy[1] > exponent: exponent = -dy[1]
            if dz[0] and -dz[1] > exponent: exponent = -dz[1]
            coordinates[index] = (dx, dy, dz)
        relative.append((faces, coordinates))
    factor, prepared = _prepare_triangles_from_relative(relative, exponent, budget, holder=holder)
    return origin, factor, prepared


def _ratio(numerator, denominator):
    divisor = math.gcd(numerator, denominator)
    return _bounded(numerator // divisor), _bounded(denominator // divisor)


def _closer(numerator, denominator, best, *, tie_accept=False):
    if numerator < 0 or denominator <= 0:
        raise ArithmeticError('Invalid exact squared surface distance')
    if best is not None and numerator.bit_length() <= MAX_BITS and denominator.bit_length() <= MAX_BITS:
        lhs = numerator * best[1]
        rhs = best[0] * denominator
        if lhs > rhs or (lhs == rhs and not tie_accept):
            return None
    if denominator == 1:
        return _bounded(numerator), 1
    numerator, denominator = _ratio(numerator, denominator)
    if best is None:
        return numerator, denominator
    lhs = numerator * best[1]
    rhs = best[0] * denominator
    if lhs < rhs or (tie_accept and lhs == rhs):
        return numerator, denominator
    return None


def _point_faces(point, triangle, reverse, best, budget, *,
                 tie_accept=False, fast_ints=False, height=None,
                 bary_cache=None, tri_idx=0):
    points, normal, squared, _, _ = triangle
    budget.tick('point_face_tests')
    if fast_ints:
        px, py, pz = point
        p0x, p0y, p0z = points[0]
        qx, qy, qz = px - p0x, py - p0y, pz - p0z
        if height is None:
            nx, ny, nz = normal
            height = qx * nx + qy * ny + qz * nz
        hh = height * height
        if best is not None:
            lhs = hh * best[1]
            rhs = best[0] * squared
            if lhs > rhs or (lhs == rhs and not tie_accept):
                return best
        if bary_cache is not None:
            bary = bary_cache[tri_idx]
            if bary is None:
                bary = bary_cache[tri_idx] = _fast_bary(triangle)
        else:
            bary = _fast_bary(triangle)
        (c1x, c1y, c1z), (c2x, c2y, c2z) = bary
        u = c1x * qx + c1y * qy + c1z * qz
        v = c2x * qx + c2y * qy + c2z * qz
        if u < 0 or v < 0 or u + v > squared:
            return best
        distance = _closer(hh, squared, best, tie_accept=tie_accept)
        return (*distance, ('face', point, normal, height, squared, reverse)) if distance else best
    q = _sub(point, points[0])
    u = _dot(_cross(_sub(points[2], points[0]), normal), q)
    v = _dot(_cross(normal, _sub(points[1], points[0])), q)
    if u < 0 or v < 0 or u + v > squared:
        return best
    if height is None:
        height = _dot(q, normal)
    distance = _closer(height * height, squared, best, tie_accept=tie_accept)
    return (*distance, ('face', point, normal, height, squared, reverse)) if distance else best


def _point_edges(point, edge, reverse, best, budget, *, tie_accept=False, fast_ints=False):
    budget.tick('point_edge_tests')
    start, end, delta, squared = edge
    if fast_ints:
        px, py, pz = point
        sx, sy, sz = start
        ex, ey, ez = end
        if best is not None:
            gx = (sx - px if px < sx else (px - ex if px > ex else 0)) if sx <= ex else (ex - px if px < ex else (px - sx if px > sx else 0))
            gy = (sy - py if py < sy else (py - ey if py > ey else 0)) if sy <= ey else (ey - py if py < ey else (py - sy if py > sy else 0))
            gz = (sz - pz if pz < sz else (pz - ez if pz > ez else 0)) if sz <= ez else (ez - pz if pz < ez else (pz - sz if pz > sz else 0))
            if gx or gy or gz:
                lhs = (gx * gx + gy * gy + gz * gz) * best[1]
                rhs = best[0]
                if lhs > rhs or (lhs == rhs and not tie_accept):
                    return best
        dx, dy, dz = delta
        qx, qy, qz = px - sx, py - sy, pz - sz
        parameter = qx * dx + qy * dy + qz * dz
        if parameter <= 0:
            numerator = qx * qx + qy * qy + qz * qz
            if best is not None:
                lhs = numerator * best[1]
                rhs = best[0]
                if lhs > rhs or (lhs == rhs and not tie_accept):
                    return best
            denominator, parameter = 1, 0
        elif parameter >= squared:
            rx, ry, rz = px - ex, py - ey, pz - ez
            numerator = rx * rx + ry * ry + rz * rz
            if best is not None:
                lhs = numerator * best[1]
                rhs = best[0]
                if lhs > rhs or (lhs == rhs and not tie_accept):
                    return best
            denominator, parameter = 1, squared
        else:
            numerator = (qx * qx + qy * qy + qz * qz) * squared - parameter * parameter
            if best is not None:
                lhs = numerator * best[1]
                rhs = best[0] * squared
                if lhs > rhs or (lhs == rhs and not tie_accept):
                    return best
            denominator = squared
        distance = _closer(numerator, denominator, best, tie_accept=tie_accept)
        return (*distance, ('edge', point, start, delta, parameter, squared, reverse)) if distance else best
    q = _sub(point, start)
    parameter = _dot(q, delta)
    if parameter <= 0:
        numerator, denominator, parameter = _dot(q, q), 1, 0
    elif parameter >= squared:
        residual = _sub(point, end)
        numerator, denominator, parameter = _dot(residual, residual), 1, squared
    else:
        numerator = _dot(q, q) * squared - parameter * parameter
        denominator = squared
    distance = _closer(numerator, denominator, best, tie_accept=tie_accept)
    return (*distance, ('edge', point, start, delta, parameter, squared, reverse)) if distance else best


def _edge_edges(left, right, best, budget, *, tie_accept=False, fast_ints=False):
    budget.tick('edge_edge_tests')
    a, a_end, u, aa = left
    b, b_end, v, bb = right
    if fast_ints:
        ax, ay, az = a
        aex, aey, aez = a_end
        bx, by, bz = b
        bex, bey, bez = b_end
        if best is not None:
            ax0, ax1 = (ax, aex) if ax <= aex else (aex, ax)
            bx0, bx1 = (bx, bex) if bx <= bex else (bex, bx)
            gx = ax0 - bx1 if ax0 > bx1 else (bx0 - ax1 if bx0 > ax1 else 0)
            ay0, ay1 = (ay, aey) if ay <= aey else (aey, ay)
            by0, by1 = (by, bey) if by <= bey else (bey, by)
            gy = ay0 - by1 if ay0 > by1 else (by0 - ay1 if by0 > ay1 else 0)
            az0, az1 = (az, aez) if az <= aez else (aez, az)
            bz0, bz1 = (bz, bez) if bz <= bez else (bez, bz)
            gz = az0 - bz1 if az0 > bz1 else (bz0 - az1 if bz0 > az1 else 0)
            if gx or gy or gz:
                lhs = (gx * gx + gy * gy + gz * gz) * best[1]
                rhs = best[0]
                if lhs > rhs or (lhs == rhs and not tie_accept):
                    return best
        ux, uy, uz = u
        vx, vy, vz = v
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        determinant = nx * nx + ny * ny + nz * nz
        if determinant == 0:
            return best
        wx, wy, wz = ax - bx, ay - by, az - bz
        height = wx * nx + wy * ny + wz * nz
        hh = height * height
        if best is not None:
            lhs = hh * best[1]
            rhs = best[0] * determinant
            if lhs > rhs or (lhs == rhs and not tie_accept):
                return best
        ab = ux * vx + uy * vy + uz * vz
        au = ux * wx + uy * wy + uz * wz
        bv = vx * wx + vy * wy + vz * wz
        s = ab * bv - bb * au
        if not (0 <= s <= determinant):
            return best
        t = aa * bv - ab * au
        if not (0 <= t <= determinant):
            return best
        distance = _closer(hh, determinant, best, tie_accept=tie_accept)
        return (*distance, ('edges', a, b, u, v, s, t, determinant)) if distance else best
    normal = _cross(u, v)
    determinant = _dot(normal, normal)
    if determinant == 0:
        return best
    w = _sub(a, b)
    ab, au, bv = _dot(u, v), _dot(u, w), _dot(v, w)
    s, t = ab * bv - bb * au, aa * bv - ab * au
    if not (0 <= s <= determinant and 0 <= t <= determinant):
        return best
    height = _dot(w, normal)
    distance = _closer(height * height, determinant, best, tie_accept=tie_accept)
    return (*distance, ('edges', a, b, u, v, s, t, determinant)) if distance else best


def _segment_face_contact(segment, triangle):
    """Prove an interior plane crossing before constructing its witness."""
    if len(segment[0]) != 2:
        return None
    start, end = segment[0]
    points, normal, squared, _, _ = triangle
    da = _dot(normal, _sub(start, points[0]))
    db = _dot(normal, _sub(end, points[0]))
    if not (da < 0 < db or db < 0 < da):
        # Endpoint and coplanar contacts use the existing closed features.
        return None
    denominator = _bounded(da - db)
    numerator = da
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    delta = segment[3][0][2]
    scaled = _add(_mul(_sub(start, points[0]), denominator), _mul(delta, numerator))
    u = _dot(_cross(_sub(points[2], points[0]), normal), scaled)
    v = _dot(_cross(normal, _sub(points[1], points[0])), scaled)
    if u < 0 or v < 0 or _bounded(u + v) > _bounded(squared * denominator):
        return None
    return ('segment_face', start, delta, numerator, denominator)


def _aabb_exceeds_best(left, right, best, *, strict=True, remaining=None, fast_ints=False):
    # The integer squared lower bound exceeds n/d iff it exceeds floor(n/d)
    # (or (n-1)//d for >= when tie-breaking disallows equal candidates).
    if remaining is None:
        remaining = (best[0] // best[1]) if strict else ((best[0] - 1) // best[1])
    if remaining < 0:
        return True
    ((lx0, lx1), (ly0, ly1), (lz0, lz1)) = left
    ((rx0, rx1), (ry0, ry1), (rz0, rz1)) = right
    gx = lx0 - rx1
    if rx0 - lx1 > gx:
        gx = rx0 - lx1
    gy = ly0 - ry1
    if ry0 - ly1 > gy:
        gy = ry0 - ly1
    gz = lz0 - rz1
    if rz0 - lz1 > gz:
        gz = rz0 - lz1
    if fast_ints:
        gsq = 0
        if gx > 0:
            gsq += gx * gx
        if gy > 0:
            gsq += gy * gy
        if gz > 0:
            gsq += gz * gz
        return gsq > remaining
    for gap in (gx, gy, gz):
        if gap > 0:
            if gap.bit_length() <= 2048:
                gap_sq = gap * gap
                if gap_sq > remaining:
                    return True
                remaining -= gap_sq
            else:
                if gap > math.isqrt(remaining):
                    return True
                remaining -= gap * gap
    return False


def _plane_exceeds_best(distances, normal_squared, best, *, strict=True, fast_ints=False):
    if not normal_squared or not distances:
        return False
    if len(distances) == 3:
        d0, d1, d2 = distances
        if d0 > 0 and d1 > 0 and d2 > 0:
            gap = d0 if d0 <= d1 else d1
            if d2 < gap:
                gap = d2
        elif d0 < 0 and d1 < 0 and d2 < 0:
            gap = -d0
            if -d1 < gap:
                gap = -d1
            if -d2 < gap:
                gap = -d2
        else:
            return False
    else:
        if not (all(value > 0 for value in distances) or all(value < 0 for value in distances)):
            return False
        gap = min(abs(value) for value in distances)
    if fast_ints:
        lhs = gap * gap * best[1]
        rhs = best[0] * normal_squared
        return lhs > rhs if strict else lhs >= rhs
    # g²*d > n*n² iff integer g² > floor(n*n²/d); >= iff > (n*n² - 1)//d.
    product = _scratch(best[0] * normal_squared)
    if not strict:
        product -= 1
    threshold = product // best[1]
    if threshold < 0:
        return True
    if gap.bit_length() <= 2048:
        return gap * gap > threshold
    return gap > math.isqrt(threshold)


def _triangle_plane_bounds(left, right, best, budget, *, strict=True, fast_ints=False):
    if not left[2] or not right[2]:
        return False, None
    da = _plane_distances(right[0], left[0][0], left[1], budget, fast_ints=fast_ints)
    budget.tick('plane_bound_tests')
    if _plane_exceeds_best(da, left[2], best, strict=strict, fast_ints=fast_ints):
        return True, (da, None)
    db = _plane_distances(left[0], right[0][0], right[1], budget, fast_ints=fast_ints)
    budget.tick('plane_bound_tests')
    return _plane_exceeds_best(db, right[2], best, strict=strict, fast_ints=fast_ints), (da, db)


def _nearest_pair(left, right, best, budget, plane_distances=None,
                  *, tie_accept=False, fast_ints=False,
                  left_bary=None, left_idx=0, right_bary=None, right_idx=0):
    budget.narrow_pair()
    budget.tick('intersection_tests')
    da = db = None
    if left[2] and right[2]:
        contact, da, db = _intersection_with_planes(
            left[0], right[0], left[1], right[1], budget,
            plane_distances=plane_distances, fast_ints=fast_ints)
        if contact:
            return 0, 1, ('contact', contact[0])
    elif left[2] or right[2]:
        contact = (_segment_face_contact(right, left) if left[2]
                   else _segment_face_contact(left, right))
        if contact:
            return 0, 1, contact
    elif len(left[0]) == len(right[0]) == 1:
        delta = _sub(right[0][0], left[0][0])
        distance = _closer(_dot(delta, delta), 1, best, tie_accept=tie_accept)
        if distance:
            return (*distance, ('points', left[0][0], right[0][0]))
        return best
    cur_best = best
    accept_eq = bool(tie_accept and cur_best is not None)
    for idx_a, point in enumerate(left[0]):
        if right[2]:
            h = None if db is None else db[idx_a]
            cand = _point_faces(point, right, False, cur_best, budget,
                                tie_accept=accept_eq, fast_ints=fast_ints, height=h,
                                bary_cache=right_bary, tri_idx=right_idx)
            if cand is not cur_best:
                cur_best = cand
                accept_eq = False
        for edge in right[3]:
            cand = _point_edges(point, edge, False, cur_best, budget,
                                tie_accept=accept_eq, fast_ints=fast_ints)
            if cand is not cur_best:
                cur_best = cand
                accept_eq = False
    for idx_b, point in enumerate(right[0]):
        if left[2]:
            h = None if da is None else da[idx_b]
            cand = _point_faces(point, left, True, cur_best, budget,
                                tie_accept=accept_eq, fast_ints=fast_ints, height=h,
                                bary_cache=left_bary, tri_idx=left_idx)
            if cand is not cur_best:
                cur_best = cand
                accept_eq = False
        for edge in left[3]:
            cand = _point_edges(point, edge, True, cur_best, budget,
                                tie_accept=accept_eq, fast_ints=fast_ints)
            if cand is not cur_best:
                cur_best = cand
                accept_eq = False
    for edge_a in left[3]:
        for edge_b in right[3]:
            cand = _edge_edges(edge_a, edge_b, cur_best, budget,
                               tie_accept=accept_eq, fast_ints=fast_ints)
            if cand is not cur_best:
                cur_best = cand
                accept_eq = False
    return cur_best


def _nearest_linear(prepared, budget, witness_pair=None, *, cutoff=None):
    fast_ints = _bounds_fit_fast(prepared[0]) and _bounds_fit_fast(prepared[1])
    bary_a = [None] * len(prepared[0]) if fast_ints else None
    bary_b = [None] * len(prepared[1]) if fast_ints else None
    best = None
    cut_floor = cutoff[2] if cutoff is not None else None
    cutoff_sentinel = (cutoff[0], cutoff[1], None) if cutoff is not None else None
    for i, left in enumerate(prepared[0]):
        for j, right in enumerate(prepared[1]):
            budget.checkpoint('surface_proximity_pair')
            budget.tick('leaf_pair_visits')
            budget.counts['triangle_pairs'] += 1
            if best is not None:
                budget.tick('aabb_bound_tests')
                if _aabb_exceeds_best(left[4], right[4], best, fast_ints=fast_ints):
                    budget.counts['aabb_pruned_pairs'] += 1
                    continue
            elif cutoff_sentinel is not None:
                budget.tick('aabb_bound_tests')
                if _aabb_exceeds_best(left[4], right[4], cutoff_sentinel, strict=True,
                                      remaining=cut_floor, fast_ints=fast_ints):
                    budget.counts['aabb_pruned_pairs'] += 1
                    continue
            eff_best = best if best is not None else cutoff_sentinel
            candidate = _nearest_pair(left, right, eff_best, budget,
                                      tie_accept=(best is None and cutoff_sentinel is not None),
                                      fast_ints=fast_ints,
                                      left_bary=bary_a, left_idx=i,
                                      right_bary=bary_b, right_idx=j)
            if candidate is not eff_best:
                if witness_pair is not None:
                    witness_pair[:] = (i, j)
                best = candidate
                if best[0] == 0:
                    return best
    return best


def _distance_roots(prepared, budget, holder=None):
    from .surface_geometry import _bvh_from_flat_bounds
    roots = []
    retained_bounds = [] if holder is not None else None
    for triangles in prepared:
        n_tris = len(triangles)
        budget.tick('tree_build_units', n_tris)
        flat_bounds = [None] * n_tris
        if retained_bounds is None:
            for row_idx, triangle in enumerate(triangles):
                b = triangle[4]
                ax, bx = b[0]
                ay, by = b[1]
                az, bz = b[2]
                flat_bounds[row_idx] = (ax, ay, az, bx, by, bz, ax + bx, ay + by, az + bz)
        else:
            bounds = [None] * n_tris
            for row_idx, triangle in enumerate(triangles):
                b = triangle[4]
                ax, bx = b[0]
                ay, by = b[1]
                az, bz = b[2]
                bounds[row_idx] = ((ax, ay, az), (bx, by, bz))
                flat_bounds[row_idx] = (ax, ay, az, bx, by, bz, ax + bx, ay + by, az + bz)
            retained_bounds.append(bounds)
        budget.tick('tree_builds')
        roots.append(_bvh_from_flat_bounds(flat_bounds, budget, leaf_size=2))
    if holder is not None:
        holder['trees'] = dict(pair=holder['pair'], triangles=tuple(prepared),
                               bounds=tuple(retained_bounds), roots=tuple(roots),
                               tree_kind='sah_bvh')
    return tuple(roots)


def _compile_bvh_node(node, center_shift, budget=None):
    if budget is not None:
        budget.checkpoint('surface_proximity_bvh_compile')
    lo, hi, count, ids, left, right = node
    lx, ly, lz = lo
    hx, hy, hz = hi
    cx2, cy2, cz2 = lx + hx, ly + hy, lz + hz
    if center_shift:
        cx2 >>= center_shift
        cy2 >>= center_shift
        cz2 >>= center_shift
    if ids is not None:
        return (lx, ly, lz, hx, hy, hz, count, tuple(ids), None, None, min(ids), cx2, cy2, cz2)
    lw = _compile_bvh_node(left, center_shift, budget=budget)
    rw = _compile_bvh_node(right, center_shift, budget=budget)
    min_id = lw[10] if lw[10] <= rw[10] else rw[10]
    return (lx, ly, lz, hx, hy, hz, count, None, lw, rw, min_id, cx2, cy2, cz2)


def _node_queue_bounds(left, right, shift, budget, *, fast_ints=False):
    budget.tick('queue_bound_tests')
    gx = left[0] - right[3]
    if right[0] - left[3] > gx:
        gx = right[0] - left[3]
    if gx < 0:
        gx = 0
    gy = left[1] - right[4]
    if right[1] - left[4] > gy:
        gy = right[1] - left[4]
    if gy < 0:
        gy = 0
    gz = left[2] - right[5]
    if right[2] - left[5] > gz:
        gz = right[2] - left[5]
    if gz < 0:
        gz = 0
    if shift:
        gx >>= shift
        gy >>= shift
        gz >>= shift
    dx = left[11] - right[11]
    dy = left[12] - right[12]
    dz = left[13] - right[13]
    if fast_ints:
        return gx * gx + gy * gy + gz * gz, dx * dx + dy * dy + dz * dz
    return _scratch(gx * gx + gy * gy + gz * gz), _scratch(dx * dx + dy * dy + dz * dz)


def _fast_descriptor_direction(descriptor):
    kind = descriptor[0]
    if kind == 'points':
        p0, p1 = descriptor[1], descriptor[2]
        return (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    if kind == 'face':
        _, _, normal, height, _, reverse = descriptor
        sign = (1 if reverse else -1) * (1 if height > 0 else -1)
        return (sign * normal[0], sign * normal[1], sign * normal[2])
    if kind == 'edge':
        _, point, start, delta, parameter, squared, reverse = descriptor
        s = -squared if reverse else squared
        t = -parameter if reverse else parameter
        return (
            (start[0] - point[0]) * s + delta[0] * t,
            (start[1] - point[1]) * s + delta[1] * t,
            (start[2] - point[2]) * s + delta[2] * t,
        )
    if kind == 'edges':
        _, a, b, u, v, s, t, denominator = descriptor
        return (
            (b[0] - a[0]) * denominator + v[0] * t - u[0] * s,
            (b[1] - a[1]) * denominator + v[1] * t - u[1] * s,
            (b[2] - a[2]) * denominator + v[2] * t - u[2] * s,
        )
    return None


_FAST_WP_AFTER_COMPLETED = 16
_FAST_WP_NODE_BOX_MIN_CREDIT = 64
_DEFAULT_PROJECTION_MODE = 'settled_credit_031_ref'
_VALID_PROJECTION_MODES = frozenset({'settled_credit_031_ref', 'off', 'off_paid_dequeue_ref'})
_NODE_PRUNE_OBSERVER = None


class _FastWitnessProjection:
    """Fast exact witness-axis projection governed strictly by settled _ProjectionCredit."""
    __slots__ = (
        'axis', 'norm_sq', 'best', 'cutoff_strict', 'cutoff_tie',
        'node_a', 'node_b', 'tri_a', 'tri_b',
        'prep_a', 'prep_b', 'epoch',
    )

    _BUILD_COST = 8

    @classmethod
    def build(cls, best, prep_a, prep_b, epoch, budget, *, credit=None):
        bn, bd, desc = best
        if bn <= 0 or bd <= 0:
            return None
        budget.checkpoint('surface_proximity_witness_projection')
        if credit is not None:
            ok, res = credit.try_run(cls._BUILD_COST, lambda: cls._build_inner(best, prep_a, prep_b, epoch, budget))
            return res if ok else None
        if MAX_WORK_UNITS - budget.counts['work_units'] < cls._BUILD_COST:
            budget.counts['witness_projection_budget_deferrals'] = budget.counts.get('witness_projection_budget_deferrals', 0) + 1
            return None
        return cls._build_inner(best, prep_a, prep_b, epoch, budget)

    @classmethod
    def _build_inner(cls, best, prep_a, prep_b, epoch, budget):
        bn, bd, desc = best
        budget.consume(cls._BUILD_COST - 1, 'witness_projection')
        budget.tick('witness_projection_direction_builds', 1)
        axis = _fast_descriptor_direction(desc)
        if axis is None:
            return None
        ax, ay, az = axis
        g = math.gcd(ax, math.gcd(ay, az))
        if not g:
            return None
        ax //= g
        ay //= g
        az //= g
        if ax.bit_length() > 1024 or ay.bit_length() > 1024 or az.bit_length() > 1024:
            return None
        norm_sq = ax * ax + ay * ay + az * az
        self = cls()
        self.axis = (ax, ay, az)
        self.norm_sq = norm_sq
        self.best = (bn, bd)
        self.cutoff_strict = math.isqrt((norm_sq * bn) // bd)
        self.cutoff_tie = math.isqrt((norm_sq * bn - 1) // bd)
        self.node_a = {}
        self.node_b = {}
        self.tri_a = [None] * len(prep_a)
        self.tri_b = [None] * len(prep_b)
        self.prep_a = prep_a
        self.prep_b = prep_b
        self.epoch = epoch
        budget.counts['witness_projection_directions'] = budget.counts.get('witness_projection_directions', 0) + 1
        return self

    @classmethod
    def build_for_cutoff(cls, cut_n, cut_d, seed_desc, prep_a, prep_b, budget):
        """Build an exact Cauchy-Schwarz separating-axis projector for an external upper bound."""
        if cut_n < 0 or cut_d <= 0:
            return None
        budget.checkpoint('surface_proximity_witness_projection')
        if MAX_WORK_UNITS - budget.counts['work_units'] < cls._BUILD_COST:
            budget.counts['witness_projection_budget_deferrals'] = budget.counts.get('witness_projection_budget_deferrals', 0) + 1
            return None
        axis = _fast_descriptor_direction(seed_desc)
        if axis is None:
            return None
        ax, ay, az = axis
        g = math.gcd(ax, math.gcd(ay, az))
        if not g:
            return None
        ax //= g
        ay //= g
        az //= g
        if ax.bit_length() > 1024 or ay.bit_length() > 1024 or az.bit_length() > 1024:
            return None
        norm_sq = ax * ax + ay * ay + az * az
        if norm_sq.bit_length() + cut_n.bit_length() > _MAX_SCRATCH_BITS:
            return None
        budget.consume(cls._BUILD_COST - 1, 'witness_projection')
        budget.tick('witness_projection_direction_builds', 1)
        self = cls()
        self.axis = (ax, ay, az)
        self.norm_sq = norm_sq
        self.best = (cut_n, cut_d)
        c_strict = math.isqrt((norm_sq * cut_n) // cut_d)
        self.cutoff_strict = c_strict
        self.cutoff_tie = c_strict
        self.node_a = {}
        self.node_b = {}
        self.tri_a = [None] * len(prep_a)
        self.tri_b = [None] * len(prep_b)
        self.prep_a = prep_a
        self.prep_b = prep_b
        self.epoch = 0
        budget.counts['witness_projection_directions'] = budget.counts.get('witness_projection_directions', 0) + 1
        return self

    def _tri_interval(self, idx, tri_cache, prep_side, budget):
        row = tri_cache[idx]
        if row is not None:
            return row
        pts = prep_side[idx][0]
        cost = len(pts)
        if MAX_WORK_UNITS - budget.counts['work_units'] < cost:
            budget.counts['witness_projection_budget_deferrals'] = budget.counts.get('witness_projection_budget_deferrals', 0) + 1
            return None
        budget.tick('witness_projection_tri_dots', cost)
        ax, ay, az = self.axis
        p0 = pts[0]
        d0 = p0[0] * ax + p0[1] * ay + p0[2] * az
        if len(pts) == 3:
            p1, p2 = pts[1], pts[2]
            d1 = p1[0] * ax + p1[1] * ay + p1[2] * az
            d2 = p2[0] * ax + p2[1] * ay + p2[2] * az
            row = (min(d0, d1, d2), max(d0, d1, d2))
        else:
            lo = hi = d0
            for p in pts[1:]:
                d = p[0] * ax + p[1] * ay + p[2] * az
                if d < lo: lo = d
                elif d > hi: hi = d
            row = (lo, hi)
        tri_cache[idx] = row
        return row

    @staticmethod
    def _cold_interval_upper(node, node_cache):
        """O(1) conservative work upper bound with zero descendant traversal."""
        if id(node) in node_cache:
            return 0
        n = node[6]
        if node[7] is not None:
            return 1 + 3 * n
        return 5 * n - 1

    def _node_interval(self, node, node_cache, tri_cache, prep_side, budget):
        hit = node_cache.get(id(node))
        if hit is not None:
            return hit
        stack = [(node, False)]
        while stack:
            cur, ready = stack.pop()
            cid = id(cur)
            if cid in node_cache:
                continue
            ids = cur[7]
            if ids is not None:
                lo = hi = None
                for idx in ids:
                    t = self._tri_interval(idx, tri_cache, prep_side, budget)
                    if t is None:
                        return None
                    tlo, thi = t
                    if lo is None or tlo < lo:
                        lo = tlo
                    if hi is None or thi > hi:
                        hi = thi
                if MAX_WORK_UNITS - budget.counts['work_units'] < 1:
                    budget.counts['witness_projection_budget_deferrals'] = budget.counts.get('witness_projection_budget_deferrals', 0) + 1
                    return None
                budget.tick('witness_projection_node_visits', 1)
                node_cache[cid] = (lo, hi)
            elif not ready:
                lch, rch = cur[8], cur[9]
                lid, rid = id(lch), id(rch)
                if lid in node_cache and rid in node_cache:
                    if MAX_WORK_UNITS - budget.counts['work_units'] < 1:
                        budget.counts['witness_projection_budget_deferrals'] = budget.counts.get('witness_projection_budget_deferrals', 0) + 1
                        return None
                    budget.tick('witness_projection_node_visits', 1)
                    la, rb = node_cache[lid], node_cache[rid]
                    node_cache[cid] = (
                        la[0] if la[0] <= rb[0] else rb[0],
                        la[1] if la[1] >= rb[1] else rb[1],
                    )
                else:
                    stack.append((cur, True))
                    if rid not in node_cache:
                        stack.append((rch, False))
                    if lid not in node_cache:
                        stack.append((lch, False))
            else:
                if MAX_WORK_UNITS - budget.counts['work_units'] < 1:
                    budget.counts['witness_projection_budget_deferrals'] = budget.counts.get('witness_projection_budget_deferrals', 0) + 1
                    return None
                budget.tick('witness_projection_node_visits', 1)
                la = node_cache[id(cur[8])]
                rb = node_cache[id(cur[9])]
                node_cache[cid] = (
                    la[0] if la[0] <= rb[0] else rb[0],
                    la[1] if la[1] >= rb[1] else rb[1],
                )
        return node_cache[id(node)]

    @staticmethod
    def _slab_exceeds_cutoff(gap, cutoff):
        return gap > cutoff

    def _emit_prune(self, left, right, strict, best_pair, source, gap, cutoff):
        obs = _NODE_PRUNE_OBSERVER
        if obs is not None:
            obs({
                'left': left,
                'right': right,
                'strict': strict,
                'axis': self.axis,
                'norm_sq': self.norm_sq,
                'best': self.best,
                'best_pair': best_pair,
                'epoch': self.epoch,
                'source': source,
                'gap': gap,
                'cutoff': cutoff,
            })

    def prunes_nodes(self, left, right, strict, budget, *, use_vertex_slab=True, credit=None, best_pair=None):
        counts = budget.counts
        ax, ay, az = self.axis
        cutoff = self.cutoff_strict if strict else self.cutoff_tie
        node_a = self.node_a
        node_b = self.node_b
        la = rb = None

        if credit is not None:
            cap = credit.balance
            rem_wu = MAX_WORK_UNITS - counts['work_units']
            if rem_wu < cap:
                cap = rem_wu
            can_slab = False
            slab_upper = 0
            if use_vertex_slab:
                la = node_a.get(id(left))
                rb = node_b.get(id(right))
                ul = 0 if la is not None else ((1 + 3 * left[6]) if left[7] is not None else (5 * left[6] - 1))
                ur = 0 if rb is not None else ((1 + 3 * right[6]) if right[7] is not None else (5 * right[6] - 1))
                slab_upper = ul + ur
                counts['witness_projection_upper_calls'] = counts.get('witness_projection_upper_calls', 0) + 1
                if 1 + slab_upper <= cap:
                    can_slab = True
                else:
                    counts['witness_projection_slab_deferred'] = counts.get('witness_projection_slab_deferred', 0) + 1
                    credit.record_deferral(1 + slab_upper)
            if not can_slab and cap < _FAST_WP_NODE_BOX_MIN_CREDIT:
                if not use_vertex_slab:
                    credit.record_deferral(_FAST_WP_NODE_BOX_MIN_CREDIT)
                return False

            if 1 > credit.balance:
                counts['witness_projection_credit_credit_deferrals'] += 1
                return False
            if 1 > MAX_WORK_UNITS - counts['work_units']:
                counts['witness_projection_credit_budget_deferrals'] += 1
                counts['witness_projection_budget_deferrals'] = counts.get('witness_projection_budget_deferrals', 0) + 1
                return False
            credit.attempts += 1
            counts['witness_projection_credit_attempts'] = credit.attempts
            counts['witness_projection_credit_upper_units'] += 1
            counts['witness_projection_credit_last_upper'] = 1
            credit.pending_upper = 1
            credit.pending_work_start = counts['work_units']
            try:
                budget.tick('witness_projection_tests', 1)
                lmin = (ax * left[0] if ax >= 0 else ax * left[3]) + (ay * left[1] if ay >= 0 else ay * left[4]) + (az * left[2] if az >= 0 else az * left[5])
                lmax = (ax * left[3] if ax >= 0 else ax * left[0]) + (ay * left[4] if ay >= 0 else ay * left[1]) + (az * left[5] if az >= 0 else az * left[2])
                rmin = (ax * right[0] if ax >= 0 else ax * right[3]) + (ay * right[1] if ay >= 0 else ay * right[4]) + (az * right[2] if az >= 0 else az * right[5])
                rmax = (ax * right[3] if ax >= 0 else ax * right[0]) + (ay * right[4] if ay >= 0 else ay * right[1]) + (az * right[5] if az >= 0 else az * right[2])
                box_gap = lmin - rmax if lmin > rmax else (rmin - lmax if rmin > lmax else 0)
            finally:
                actual = counts['work_units'] - credit.pending_work_start
                credit.balance -= actual
                credit.spent += actual
                credit.pending_upper = credit.pending_work_start = None
                counts['witness_projection_credit_spent_units'] = credit.spent
                counts['witness_projection_credit_last_actual'] = actual
                counts['witness_projection_credit_balance'] = credit.balance
                if actual < 0 or actual > 1 or credit.balance < 0:
                    raise ArithmeticError('witness_projection_credit_invariant')
            if box_gap > cutoff:
                counts['witness_projection_box_pruned_pairs'] = counts.get('witness_projection_box_pruned_pairs', 0) + 1
                if _NODE_PRUNE_OBSERVER is not None:
                    self._emit_prune(left, right, strict, best_pair, 'box', box_gap, cutoff)
                return True
            if not can_slab:
                return False

            counts['witness_projection_slab_admitted'] = counts.get('witness_projection_slab_admitted', 0) + 1
            counts['witness_projection_slab_reserved_units'] = counts.get('witness_projection_slab_reserved_units', 0) + slab_upper
            w0 = counts['work_units']
            if slab_upper > credit.balance:
                counts['witness_projection_credit_credit_deferrals'] += 1
                counts['witness_projection_slab_actual_units'] = counts.get('witness_projection_slab_actual_units', 0) + (counts['work_units'] - w0)
                return False
            if slab_upper > MAX_WORK_UNITS - w0:
                counts['witness_projection_credit_budget_deferrals'] += 1
                counts['witness_projection_budget_deferrals'] = counts.get('witness_projection_budget_deferrals', 0) + 1
                counts['witness_projection_slab_actual_units'] = counts.get('witness_projection_slab_actual_units', 0) + (counts['work_units'] - w0)
                return False
            credit.attempts += 1
            counts['witness_projection_credit_attempts'] = credit.attempts
            counts['witness_projection_credit_upper_units'] += slab_upper
            counts['witness_projection_credit_last_upper'] = slab_upper
            credit.pending_upper = slab_upper
            credit.pending_work_start = w0
            res = False
            slab_gap = 0
            try:
                counts['witness_projection_vertex_slabs'] = counts.get('witness_projection_vertex_slabs', 0) + 1
                if la is None:
                    la = self._node_interval(left, node_a, self.tri_a, self.prep_a, budget)
                if la is not None:
                    if rb is None:
                        rb = self._node_interval(right, node_b, self.tri_b, self.prep_b, budget)
                    if rb is not None:
                        slab_gap = la[0] - rb[1] if la[0] > rb[1] else (rb[0] - la[1] if rb[0] > la[1] else 0)
                        res = self._slab_exceeds_cutoff(slab_gap, cutoff)
            finally:
                actual = counts['work_units'] - credit.pending_work_start
                credit.balance -= actual
                credit.spent += actual
                credit.pending_upper = credit.pending_work_start = None
                counts['witness_projection_credit_spent_units'] = credit.spent
                counts['witness_projection_credit_last_actual'] = actual
                counts['witness_projection_credit_balance'] = credit.balance
                if actual < 0 or actual > slab_upper or credit.balance < 0:
                    raise ArithmeticError('witness_projection_credit_invariant')
            counts['witness_projection_slab_actual_units'] = counts.get('witness_projection_slab_actual_units', 0) + (counts['work_units'] - w0)
            if res:
                counts['witness_projection_vertex_slab_pruned_pairs'] = counts.get('witness_projection_vertex_slab_pruned_pairs', 0) + 1
                if _NODE_PRUNE_OBSERVER is not None:
                    self._emit_prune(left, right, strict, best_pair, 'vertex_slab', slab_gap, cutoff)
                return True
            return False

        if MAX_WORK_UNITS - counts['work_units'] < 1:
            counts['witness_projection_budget_deferrals'] = counts.get('witness_projection_budget_deferrals', 0) + 1
            return False
        budget.tick('witness_projection_tests', 1)
        lmin = (ax * left[0] if ax >= 0 else ax * left[3]) + (ay * left[1] if ay >= 0 else ay * left[4]) + (az * left[2] if az >= 0 else az * left[5])
        lmax = (ax * left[3] if ax >= 0 else ax * left[0]) + (ay * left[4] if ay >= 0 else ay * left[1]) + (az * left[5] if az >= 0 else az * left[2])
        rmin = (ax * right[0] if ax >= 0 else ax * right[3]) + (ay * right[1] if ay >= 0 else ay * right[4]) + (az * right[2] if az >= 0 else az * right[5])
        rmax = (ax * right[3] if ax >= 0 else ax * right[0]) + (ay * right[4] if ay >= 0 else ay * right[1]) + (az * right[5] if az >= 0 else az * right[2])
        box_gap = lmin - rmax if lmin > rmax else (rmin - lmax if rmin > lmax else 0)
        if box_gap > cutoff:
            counts['witness_projection_box_pruned_pairs'] = counts.get('witness_projection_box_pruned_pairs', 0) + 1
            if _NODE_PRUNE_OBSERVER is not None:
                self._emit_prune(left, right, strict, best_pair, 'box', box_gap, cutoff)
            return True
        if not use_vertex_slab:
            return False
        counts['witness_projection_vertex_slabs'] = counts.get('witness_projection_vertex_slabs', 0) + 1
        la = node_a.get(id(left))
        if la is None:
            la = self._node_interval(left, node_a, self.tri_a, self.prep_a, budget)
            if la is None:
                return False
        rb = node_b.get(id(right))
        if rb is None:
            rb = self._node_interval(right, node_b, self.tri_b, self.prep_b, budget)
            if rb is None:
                return False
        slab_gap = la[0] - rb[1] if la[0] > rb[1] else (rb[0] - la[1] if rb[0] > la[1] else 0)
        if self._slab_exceeds_cutoff(slab_gap, cutoff):
            counts['witness_projection_vertex_slab_pruned_pairs'] = counts.get('witness_projection_vertex_slab_pruned_pairs', 0) + 1
            if _NODE_PRUNE_OBSERVER is not None:
                self._emit_prune(left, right, strict, best_pair, 'vertex_slab', slab_gap, cutoff)
            return True
        return False

    def prunes_triangles(self, i, j, strict, budget, *, credit=None):
        tri_a = self.tri_a
        tri_b = self.tri_b
        cutoff = self.cutoff_strict if strict else self.cutoff_tie
        if credit is not None:
            counts = budget.counts
            ia = tri_a[i]
            jb = tri_b[j]
            ta = 0 if ia is not None else len(self.prep_a[i][0])
            tb = 0 if jb is not None else len(self.prep_b[j][0])
            upper = 1 + ta + tb
            if upper > credit.balance:
                counts['witness_projection_credit_credit_deferrals'] += 1
                return False
            w0 = counts['work_units']
            if upper > MAX_WORK_UNITS - w0:
                counts['witness_projection_credit_budget_deferrals'] += 1
                counts['witness_projection_budget_deferrals'] = counts.get('witness_projection_budget_deferrals', 0) + 1
                return False
            credit.attempts += 1
            counts['witness_projection_credit_attempts'] = credit.attempts
            counts['witness_projection_credit_upper_units'] += upper
            counts['witness_projection_credit_last_upper'] = upper
            credit.pending_upper = upper
            credit.pending_work_start = w0
            res = False
            try:
                budget.tick('witness_projection_tests', 1)
                if ia is None:
                    ia = self._tri_interval(i, tri_a, self.prep_a, budget)
                if ia is not None:
                    if jb is None:
                        jb = self._tri_interval(j, tri_b, self.prep_b, budget)
                    if jb is not None:
                        gap = ia[0] - jb[1] if ia[0] > jb[1] else (jb[0] - ia[1] if jb[0] > ia[1] else 0)
                        res = gap > cutoff
            finally:
                actual = counts['work_units'] - credit.pending_work_start
                credit.balance -= actual
                credit.spent += actual
                credit.pending_upper = credit.pending_work_start = None
                counts['witness_projection_credit_spent_units'] = credit.spent
                counts['witness_projection_credit_last_actual'] = actual
                counts['witness_projection_credit_balance'] = credit.balance
                if actual < 0 or actual > upper or credit.balance < 0:
                    raise ArithmeticError('witness_projection_credit_invariant')
            return res

        if MAX_WORK_UNITS - budget.counts['work_units'] < 1:
            budget.counts['witness_projection_budget_deferrals'] = budget.counts.get('witness_projection_budget_deferrals', 0) + 1
            return False
        budget.tick('witness_projection_tests', 1)
        ia = tri_a[i]
        if ia is None:
            ia = self._tri_interval(i, tri_a, self.prep_a, budget)
            if ia is None:
                return False
        jb = tri_b[j]
        if jb is None:
            jb = self._tri_interval(j, tri_b, self.prep_b, budget)
            if jb is None:
                return False
        gap = ia[0] - jb[1] if ia[0] > jb[1] else (jb[0] - ia[1] if jb[0] > ia[1] else 0)
        return gap > cutoff


WITNESS_PROJECTION_AFTER_COMPLETED = 64
WITNESS_PROJECTION_BUILD_BITS = 256
WITNESS_PROJECTION_AXIS_BITS = 128
WITNESS_PROJECTION_SCRATCH_BITS = 512
WITNESS_PROJECTION_FIRST_ALLOWANCE = 100
WITNESS_PROJECTION_TEST_ALLOWANCE = 50


class _ProjectionUnavailable(Exception):
    """Only this optional local proof is unavailable; use original exact work."""


def _wp_optional_allowance(budget, amount, *, reserve=0):
    if reserve == 0 and MAX_WORK_UNITS - budget.counts['work_units'] >= amount:
        return True
    budget.counts['witness_projection_budget_deferrals'] = budget.counts.get('witness_projection_budget_deferrals', 0) + 1
    return False


def _wp_scalar(value, cap):
    if type(value) is not int or abs(value).bit_length() > min(cap, MAX_BITS):
        raise _ProjectionUnavailable('local_bits')
    return value


def _wp_add(a, b, cap, budget):
    budget.tick('witness_projection_arithmetic')
    cap = min(cap, _MAX_SCRATCH_BITS)
    _wp_scalar(a, cap)
    _wp_scalar(b, cap)
    if a == 0:
        return b
    if b == 0:
        return a
    if max(abs(a).bit_length(), abs(b).bit_length()) + 1 > cap:
        raise _ProjectionUnavailable('local_bits')
    return a + b


def _wp_mul(a, b, cap, budget):
    budget.tick('witness_projection_arithmetic')
    cap = min(cap, _MAX_SCRATCH_BITS)
    _wp_scalar(a, cap)
    _wp_scalar(b, cap)
    if a == 0 or b == 0:
        return 0
    if abs(a).bit_length() + abs(b).bit_length() > cap:
        raise _ProjectionUnavailable('local_bits')
    return a * b


def _wp_vector(value, budget):
    if type(value) not in (tuple, list) or len(value) != 3:
        raise _ProjectionUnavailable('descriptor')
    budget.tick('witness_projection_descriptor_components', 3)
    return tuple(_wp_scalar(x, WITNESS_PROJECTION_BUILD_BITS) for x in value)


def _wp_difference(a, b, budget):
    return tuple(_wp_add(x, -y, WITNESS_PROJECTION_BUILD_BITS, budget) for x, y in zip(a, b))


def _wp_descriptor_direction(descriptor, budget):
    """Positive-denominator symbolic form of point_b minus point_a."""
    if type(descriptor) not in (tuple, list) or not descriptor:
        raise _ProjectionUnavailable('descriptor')
    kind, *values = descriptor
    cap = WITNESS_PROJECTION_BUILD_BITS
    if kind == 'points' and len(values) == 2:
        return _wp_difference(_wp_vector(values[1], budget), _wp_vector(values[0], budget), budget)
    if kind == 'face' and len(values) == 5:
        point, normal, height, squared, reverse = values
        normal = _wp_vector(normal, budget)
        budget.tick('witness_projection_descriptor_components', 2)
        height, squared = _wp_scalar(height, cap), _wp_scalar(squared, cap)
        if squared <= 0 or type(reverse) is not bool:
            raise _ProjectionUnavailable('descriptor')
        sign = (1 if reverse else -1) * ((height > 0) - (height < 0))
        budget.tick('witness_projection_arithmetic', 3)
        return tuple(sign * x for x in normal)
    if kind == 'edge' and len(values) == 6:
        point, start, delta, parameter, squared, reverse = values
        point, start, delta = (_wp_vector(p, budget) for p in (point, start, delta))
        budget.tick('witness_projection_descriptor_components', 2)
        parameter, squared = _wp_scalar(parameter, cap), _wp_scalar(squared, cap)
        if squared <= 0 or type(reverse) is not bool:
            raise _ProjectionUnavailable('descriptor')
        difference = _wp_difference(start, point, budget)
        axis = tuple(_wp_add(_wp_mul(x, squared, cap, budget), _wp_mul(v, parameter, cap, budget), cap, budget)
                     for x, v in zip(difference, delta))
        if reverse:
            budget.tick('witness_projection_arithmetic', 3)
            axis = tuple(-x for x in axis)
        return axis
    if kind == 'edges' and len(values) == 7:
        a, b, u, v, s, t, denominator = values
        a, b, u, v = (_wp_vector(p, budget) for p in (a, b, u, v))
        budget.tick('witness_projection_descriptor_components', 3)
        s, t, denominator = (_wp_scalar(x, cap) for x in (s, t, denominator))
        if denominator <= 0:
            raise _ProjectionUnavailable('descriptor')
        difference = _wp_difference(b, a, budget)
        return tuple(_wp_add(_wp_add(_wp_mul(x, denominator, cap, budget),
                         _wp_mul(y, t, cap, budget), cap, budget),
                         -_wp_mul(z, s, cap, budget), cap, budget)
                     for x, y, z in zip(difference, v, u))
    raise _ProjectionUnavailable('descriptor')


class _WitnessProjection:
    """One actual-best epoch, one primitive axis, two lazy source-row maps."""
    @classmethod
    def from_best(cls, best, budget):
        budget.tick('witness_projection_direction_builds')
        try:
            if (type(best) not in (tuple, list) or len(best) != 3
                    or type(best[0]) is not int or type(best[1]) is not int
                    or best[0] <= 0 or best[1] <= 0):
                raise _ProjectionUnavailable('descriptor')
            axis = _wp_descriptor_direction(best[2], budget)
            budget.tick('witness_projection_arithmetic', 3)
            divisor = math.gcd(*axis)
            if not divisor:
                raise _ProjectionUnavailable('zero_axis')
            budget.tick('witness_projection_arithmetic', 3)
            axis = tuple(x // divisor for x in axis)
            if any(abs(x).bit_length() > WITNESS_PROJECTION_AXIS_BITS for x in axis):
                raise _ProjectionUnavailable('local_bits')
            cap = WITNESS_PROJECTION_SCRATCH_BITS
            squared = 0
            for x in axis:
                squared = _wp_add(squared, _wp_mul(x, x, cap, budget), cap, budget)
            numerator, denominator = (_wp_scalar(x, cap) for x in best[:2])
            product = _wp_mul(squared, numerator, cap, budget)
            budget.tick('witness_projection_arithmetic', 2)
            cutoff = math.isqrt(product // denominator)
        except _ProjectionUnavailable as exc:
            label = {'descriptor': 'descriptor', 'zero_axis': 'zero_axis', 'local_bits': 'local_limit'}[str(exc)]
            name = 'witness_projection_' + label + '_skips'
            budget.counts[name] = budget.counts.get(name, 0) + 1
            return False
        budget.tick('witness_projection_directions')
        # One real cache epoch will be released, either on best replacement or
        # query return. Charge its release now rather than after exact work may
        # have used the final original budget unit. There is no refund/reset.
        budget.tick('witness_projection_epoch_release_units')
        self = cls.__new__(cls)
        self.best = best
        self.axis = axis
        self.norm_squared = squared
        self.cutoff = cutoff
        self.epoch = budget.counts['witness_projection_directions']
        self.intervals = ({}, {})
        return self

    def interval(self, side, row, triangle, budget):
        budget.tick('witness_projection_cache_lookups')
        cache = self.intervals[side]
        if row in cache:
            budget.counts['witness_projection_cache_hits'] = budget.counts.get('witness_projection_cache_hits', 0) + 1
            return cache[row]
        cap = WITNESS_PROJECTION_SCRATCH_BITS
        try:
            values = []
            for point in triangle[0]:
                budget.tick('witness_projection_vertex_dots')
                total = 0
                for x, n in zip(point, self.axis):
                    total = _wp_add(total, _wp_mul(x, n, cap, budget), cap, budget)
                values.append(total)
            interval = min(values), max(values)
        except _ProjectionUnavailable:
            budget.counts['witness_projection_local_limit_skips'] = budget.counts.get('witness_projection_local_limit_skips', 0) + 1
            interval = False
        budget.tick('witness_projection_intervals_built')
        cache[row] = interval
        return interval

    def prunes(self, i, j, a, b, budget):
        budget.tick('witness_projection_tests')
        left = self.interval(0, i, a, budget)
        right = self.interval(1, j, b, budget)
        if left is False or right is False:
            return False
        try:
            gap = max(_wp_add(left[0], -right[1], WITNESS_PROJECTION_SCRATCH_BITS, budget),
                      _wp_add(right[0], -left[1], WITNESS_PROJECTION_SCRATCH_BITS, budget), 0)
        except _ProjectionUnavailable:
            budget.counts['witness_projection_local_limit_skips'] = budget.counts.get('witness_projection_local_limit_skips', 0) + 1
            return False
        if gap > self.cutoff:
            budget.counts['witness_projection_pruned_pairs'] = budget.counts.get('witness_projection_pruned_pairs', 0) + 1
            return True
        return False


def _wp_attempt_work_bound(projection, i, j, a, b):
    """51 axis units; test base5; cold side1+7 per prepared hull point.

    Cached False intervals are still cached: their failed construction has
    already been paid, and a future lookup cannot repeat that construction.
    """
    cost = 51 if projection is None else 0
    cost += 5
    for side, row, triangle in ((0, i, a), (1, j, b)):
        if projection is None or row not in projection.intervals[side]:
            cost += 1 + 7 * len(triangle[0])
    return cost


def _wp_narrow_work_floor(a, b):
    """Strict positive separation excludes contact early returns.

    A completed original narrow call must pay narrow+intersection=2 and every
    native point-face, point-edge and edge-edge feature entry counted here.
    Normal triangles give35. No optional or old plane/AABB work is credited.
    """
    va, vb = len(a[0]), len(b[0])
    ea, eb = len(a[3]), len(b[3])
    return 2 + va * (int(bool(b[2])) + eb) + vb * (int(bool(a[2])) + ea) + ea * eb


class _ProjectionCredit:
    """Query-local, non-borrowing account of already saved original work.

    Start0. A reused unshifted dequeue bound saves1 at the same checkpoint.
    Only a proved strict leaf exclusion earns its original narrow work floor.
    Each attempt must fit both settled credit and original remaining budget;
    finally debit the actual original _Work delta, including every failure.
    There is no refund, replay, increase of a limit or whole-query result cache.
    """
    def __init__(self, budget):
        self.budget = budget
        self.balance = 0
        self.spent = 0
        self.earned_bounds = 0
        self.earned_narrow = 0
        self.earned_node_prune = 0
        self.attempts = 0
        self.pending_upper = None
        self.pending_work_start = None
        for name in ('balance', 'node_units', 'narrow_units', 'node_prune_units', 'spent_units', 'attempts',
                     'credit_deferrals', 'budget_deferrals', 'upper_units', 'last_upper', 'last_actual'):
            budget.counts['witness_projection_credit_' + name] = 0

    @property
    def available_credit(self):
        """True prefix margin also while an admitted attempt is in progress."""
        pending = (0 if self.pending_work_start is None else
                   self.budget.counts['work_units'] - self.pending_work_start)
        return self.balance - pending

    def saved_bound(self):
        self.balance += 1
        self.earned_bounds += 1
        counts = self.budget.counts
        counts['witness_projection_credit_node_units'] = self.earned_bounds
        counts['witness_projection_credit_balance'] = self.balance

    def record_deferral(self, upper):
        counts = self.budget.counts
        if upper > self.balance:
            counts['witness_projection_credit_credit_deferrals'] += 1
        else:
            counts['witness_projection_credit_budget_deferrals'] += 1
            counts['witness_projection_budget_deferrals'] = counts.get('witness_projection_budget_deferrals', 0) + 1

    def earn_narrow(self, saved):
        self.balance += saved
        self.earned_narrow += saved
        counts = self.budget.counts
        counts['witness_projection_credit_narrow_units'] = self.earned_narrow
        counts['witness_projection_credit_balance'] = self.balance

    def earn_node_prune(self, saved):
        self.balance += saved
        self.earned_node_prune += saved
        counts = self.budget.counts
        counts['witness_projection_credit_node_prune_units'] = self.earned_node_prune
        counts['witness_projection_credit_balance'] = self.balance

    def try_run(self, upper, fn):
        budget = self.budget
        counts = budget.counts
        if upper > self.balance:
            counts['witness_projection_credit_credit_deferrals'] += 1
            return False, None
        if upper > MAX_WORK_UNITS - counts['work_units']:
            counts['witness_projection_credit_budget_deferrals'] += 1
            counts['witness_projection_budget_deferrals'] = counts.get('witness_projection_budget_deferrals', 0) + 1
            return False, None
        self.attempts += 1
        counts['witness_projection_credit_attempts'] = self.attempts
        counts['witness_projection_credit_upper_units'] += upper
        counts['witness_projection_credit_last_upper'] = upper
        self.pending_upper = upper
        self.pending_work_start = counts['work_units']
        try:
            out = fn()
        finally:
            actual = counts['work_units'] - self.pending_work_start
            self.balance -= actual
            self.spent += actual
            self.pending_upper = self.pending_work_start = None
            counts['witness_projection_credit_spent_units'] = self.spent
            counts['witness_projection_credit_last_actual'] = actual
            counts['witness_projection_credit_balance'] = self.balance
            if actual < 0 or actual > upper or self.balance < 0:
                raise ArithmeticError('witness_projection_credit_invariant')
        return True, out

    def attempt(self, projection, best, i, j, a, b):
        upper = _wp_attempt_work_bound(projection, i, j, a, b)
        budget = self.budget
        pruned = False
        def _run():
            nonlocal projection, pruned
            if projection is None:
                projection = _WitnessProjection.from_best(best, budget)
            if projection is not False:
                pruned = projection.prunes(i, j, a, b, budget)
        ok, _ = self.try_run(upper, _run)
        if not ok:
            return projection, False
        if pruned:
            self.earn_narrow(_wp_narrow_work_floor(a, b))
        return projection, pruned


def _nearest_tree(prepared, roots, budget, witness_pair=None, *, projection_mode=None, cutoff=None):
    mode = _DEFAULT_PROJECTION_MODE if projection_mode is None else projection_mode
    if mode not in _VALID_PROJECTION_MODES:
        raise ValueError(f'unsupported projection_mode: {mode!r}')
    proj_enabled = (mode == 'settled_credit_031_ref')
    counts = budget.counts
    tick = budget.tick
    checkpoint = budget.checkpoint
    counts['witness_projection_mode'] = mode
    counts['witness_projection_credit_reference'] = (
        'mandatory_031_dequeue_aabb' if proj_enabled
        else ('paid_dequeue_reference' if mode == 'off_paid_dequeue_ref' else 'none')
    )
    limit = _FAST_COORD_LIMIT
    fast_ints = all(-limit < r < limit for s in (0, 1) for b in (roots[s][0], roots[s][1]) for r in b)
    na, nb = len(prepared[0]), len(prepared[1])
    bary_a = [None] * na if fast_ints else None
    bary_b = [None] * nb if fast_ints else None
    largest_span = max(max(a, b) - min(c, d) for a, b, c, d in
                       zip(roots[0][1], roots[1][1], roots[0][0], roots[1][0]))
    # One common priority scale protects extreme inputs. Safe pruning below
    # always uses unshifted bounds, regardless of this queue-only ordering.
    span_bits = largest_span.bit_length()
    shift = max(0, span_bits - (MAX_BITS - 1))
    center_shift = max(0, span_bits - (MAX_BITS - 4))
    left_root = _compile_bvh_node(roots[0], center_shift, budget=budget)
    right_root = _compile_bvh_node(roots[1], center_shift, budget=budget)

    pending = []
    heappush = heapq.heappush
    heappop = heapq.heappop
    serial = 0
    best = best_pair = None
    best_floor = tie_floor = None
    cut_floor = cutoff[2] if cutoff is not None else None
    cutoff_sentinel = (cutoff[0], cutoff[1], None) if cutoff is not None else None
    credit = _ProjectionCredit(budget)
    completed_exact = 0
    projection = None
    fast_proj = None
    fast_proj_tried = False
    fast_proj_epoch = 0
    cutoff_proj = None
    prep_a, prep_b = prepared[0], prepared[1]

    def invalidate_fast_proj():
        nonlocal fast_proj, fast_proj_tried, fast_proj_epoch
        fast_proj = None
        fast_proj_tried = False
        fast_proj_epoch += 1

    def ensure_fast_proj(min_extra=1):
        nonlocal fast_proj, fast_proj_tried
        if fast_proj is not None:
            return fast_proj
        if (not fast_ints or best is None or best[0] <= 0
                or completed_exact < _FAST_WP_AFTER_COMPLETED or fast_proj_tried):
            return None
        need = _FastWitnessProjection._BUILD_COST + min_extra
        rem = MAX_WORK_UNITS - counts['work_units']
        if need > credit.balance or need > rem:
            credit.record_deferral(need)
            return None
        fast_proj_tried = True
        fast_proj = _FastWitnessProjection.build(
            best, prep_a, prep_b, fast_proj_epoch, budget, credit=credit)
        return fast_proj

    def eval_leaf(left, right):
        nonlocal best, best_pair, best_floor, tie_floor, completed_exact, projection
        singleton = shift == 0 and left[6] == 1 and right[6] == 1
        for i in left[7]:
            a = prep_a[i]
            for j in right[7]:
                tick('leaf_pair_visits')
                counts['triangle_pairs'] += 1
                b = prep_b[j]
                planes = None
                if best is not None:
                    bp0, bp1 = best_pair
                    strict = (i < bp0 or (i == bp0 and j < bp1))
                    if not singleton:
                        tick('aabb_bound_tests')
                        if _aabb_exceeds_best(a[4], b[4], best, strict=strict,
                                              remaining=(best_floor if strict else tie_floor),
                                              fast_ints=fast_ints):
                            counts['aabb_pruned_pairs'] += 1
                            continue
                    pruned, planes = _triangle_plane_bounds(
                        a, b, best, budget, strict=strict, fast_ints=fast_ints)
                    if pruned:
                        counts['plane_pruned_pairs'] += 1
                        continue
                    if proj_enabled and fast_ints and best[0] > 0:
                        fp = ensure_fast_proj(1 + len(a[0]) + len(b[0]))
                        if fp is not None and fp.prunes_triangles(i, j, strict, budget, credit=credit):
                            counts['witness_projection_pruned_pairs'] = counts.get('witness_projection_pruned_pairs', 0) + 1
                            counts['witness_projection_tri_pruned_pairs'] = counts.get('witness_projection_tri_pruned_pairs', 0) + 1
                            credit.earn_narrow(_wp_narrow_work_floor(a, b))
                            continue
                    if (proj_enabled and not fast_ints
                            and completed_exact >= WITNESS_PROJECTION_AFTER_COMPLETED
                            and best[0] > 0 and projection is not False):
                        projection, projection_pruned = credit.attempt(projection, best, i, j, a, b)
                        if projection_pruned:
                            continue
                    eff_best = best
                    tie_accept = strict
                elif cutoff_sentinel is not None:
                    tick('aabb_bound_tests')
                    if _aabb_exceeds_best(a[4], b[4], cutoff_sentinel, strict=True,
                                          remaining=cut_floor, fast_ints=fast_ints):
                        counts['aabb_pruned_pairs'] += 1
                        continue
                    pruned, planes = _triangle_plane_bounds(
                        a, b, cutoff_sentinel, budget, strict=True, fast_ints=fast_ints)
                    if pruned:
                        counts['plane_pruned_pairs'] += 1
                        continue
                    if cutoff_proj is not None and cutoff_proj.prunes_triangles(i, j, True, budget):
                        counts['witness_projection_pruned_pairs'] = counts.get('witness_projection_pruned_pairs', 0) + 1
                        counts['witness_projection_tri_pruned_pairs'] = counts.get('witness_projection_tri_pruned_pairs', 0) + 1
                        continue
                    eff_best = cutoff_sentinel
                    tie_accept = True
                else:
                    eff_best = None
                    tie_accept = False
                candidate = _nearest_pair(
                    a, b, eff_best, budget, planes,
                    tie_accept=tie_accept,
                    fast_ints=fast_ints,
                    left_bary=bary_a, left_idx=i,
                    right_bary=bary_b, right_idx=j)
                completed_exact += 1
                counts['witness_projection_completed_exact'] = completed_exact
                if best is None:
                    if candidate is not eff_best:
                        best, best_pair = candidate, (i, j)
                        best_floor = best[0] // best[1]
                        tie_floor = (best[0] - 1) // best[1]
                        projection = None
                        invalidate_fast_proj()
                elif candidate is not best:
                    comparison = candidate[0] * best[1] - best[0] * candidate[1]
                    if comparison < 0 or (comparison == 0 and (i < best_pair[0] or (i == best_pair[0] and j < best_pair[1]))):
                        best, best_pair = candidate, (i, j)
                        best_floor = best[0] // best[1]
                        tie_floor = (best[0] - 1) // best[1]
                        if projection is not None or fast_proj is not None:
                            counts['witness_projection_invalidations'] = counts.get('witness_projection_invalidations', 0) + 1
                        projection = None
                        invalidate_fast_proj()

    def push_pair(key, cdist, sl, sr):
        nonlocal serial
        if best is not None:
            strict = (sl[10] < best_pair[0] or (sl[10] == best_pair[0] and sr[10] < best_pair[1]))
            if shift == 0:
                checkpoint('surface_proximity_aabb_bound_tests')
                limit = best_floor if strict else tie_floor
                if key > limit:
                    counts['subtree_pruned_pairs'] += sl[6] * sr[6]
                    return
            else:
                tick('aabb_bound_tests')
                if _aabb_exceeds_best(
                        ((sl[0], sl[3]), (sl[1], sl[4]), (sl[2], sl[5])),
                        ((sr[0], sr[3]), (sr[1], sr[4]), (sr[2], sr[5])),
                        best, strict=strict):
                    counts['subtree_pruned_pairs'] += sl[6] * sr[6]
                    return
        elif cutoff_sentinel is not None:
            if shift == 0:
                checkpoint('surface_proximity_aabb_bound_tests')
                if key > cut_floor:
                    counts['subtree_pruned_pairs'] += sl[6] * sr[6]
                    return
            else:
                tick('aabb_bound_tests')
                if _aabb_exceeds_best(
                        ((sl[0], sl[3]), (sl[1], sl[4]), (sl[2], sl[5])),
                        ((sr[0], sr[3]), (sr[1], sr[4]), (sr[2], sr[5])),
                        cutoff_sentinel, strict=True, remaining=cut_floor):
                    counts['subtree_pruned_pairs'] += sl[6] * sr[6]
                    return
        tick('queue_pushes')
        heappush(pending, (key, cdist, serial, sl, sr))
        serial += 1

    # Inline 1-path greedy DFS descent to seed best quickly before priority loop.
    siblings = []
    cur_l, cur_r = left_root, right_root
    dfs_aborted = False
    while cur_l[7] is None or cur_r[7] is None:
        tick('node_pair_visits')
        if cur_r[7] is not None or (cur_l[7] is None and cur_l[6] >= cur_r[6]):
            c0, c1 = cur_l[8], cur_l[9]
            k0, cd0 = _node_queue_bounds(c0, cur_r, shift, budget, fast_ints=fast_ints)
            k1, cd1 = _node_queue_bounds(c1, cur_r, shift, budget, fast_ints=fast_ints)
            if (k0, cd0, c0[10]) <= (k1, cd1, c1[10]):
                if shift == 0 and cut_floor is not None and k0 > cut_floor:
                    counts['subtree_pruned_pairs'] += c0[6] * cur_r[6] + c1[6] * cur_r[6]
                    dfs_aborted = True
                    break
                siblings.append((k1, cd1, c1, cur_r))
                cur_l = c0
            else:
                if shift == 0 and cut_floor is not None and k1 > cut_floor:
                    counts['subtree_pruned_pairs'] += c0[6] * cur_r[6] + c1[6] * cur_r[6]
                    dfs_aborted = True
                    break
                siblings.append((k0, cd0, c0, cur_r))
                cur_l = c1
        else:
            c0, c1 = cur_r[8], cur_r[9]
            k0, cd0 = _node_queue_bounds(cur_l, c0, shift, budget, fast_ints=fast_ints)
            k1, cd1 = _node_queue_bounds(cur_l, c1, shift, budget, fast_ints=fast_ints)
            if (k0, cd0, c0[10]) <= (k1, cd1, c1[10]):
                if shift == 0 and cut_floor is not None and k0 > cut_floor:
                    counts['subtree_pruned_pairs'] += cur_l[6] * c0[6] + cur_l[6] * c1[6]
                    dfs_aborted = True
                    break
                siblings.append((k1, cd1, cur_l, c1))
                cur_r = c0
            else:
                if shift == 0 and cut_floor is not None and k1 > cut_floor:
                    counts['subtree_pruned_pairs'] += cur_l[6] * c0[6] + cur_l[6] * c1[6]
                    dfs_aborted = True
                    break
                siblings.append((k0, cd0, cur_l, c0))
                cur_r = c1
    if not dfs_aborted:
        tick('node_pair_visits')
        eval_leaf(cur_l, cur_r)
        if cutoff_sentinel is not None and best is None and fast_ints and proj_enabled:
            i0, j0 = cur_l[7][0], cur_r[7][0]
            seed_cand = _nearest_pair(
                prep_a[i0], prep_b[j0], None, budget, None,
                fast_ints=fast_ints,
                left_bary=bary_a, left_idx=i0,
                right_bary=bary_b, right_idx=j0,
            )
            if seed_cand[0] > 0:
                cutoff_proj = _FastWitnessProjection.build_for_cutoff(
                    cutoff_sentinel[0], cutoff_sentinel[1], seed_cand[2], prep_a, prep_b, budget
                )
                if cutoff_proj is not None and left_root[6] <= 512 and right_root[6] <= 512:
                    if cutoff_proj.prunes_nodes(left_root, right_root, True, budget, use_vertex_slab=True):
                        counts['witness_projection_pruned_pairs'] = counts.get('witness_projection_pruned_pairs', 0) + 1
                        counts['witness_projection_node_pruned_pairs'] = counts.get('witness_projection_node_pruned_pairs', 0) + 1
                        counts['cutoff_pruned_pairs'] = counts.get('cutoff_pruned_pairs', 0) + na * nb
                        return None

    for k, cd, sl, sr in siblings:
        push_pair(k, cd, sl, sr)

    fast_push = (shift == 0 and fast_ints)
    while pending:
        tick('node_pair_visits')
        key, _, _, left, right = heappop(pending)
        if best is not None:
            if shift == 0:
                counts['dequeue_reused_aabb_bounds'] = counts.get('dequeue_reused_aabb_bounds', 0) + 1
                if mode == 'off_paid_dequeue_ref':
                    tick('aabb_bound_tests')
                else:
                    checkpoint('surface_proximity_aabb_bound_tests')
                    counts['aabb_bound_tests'] += 1
                    if proj_enabled:
                        credit.saved_bound()
                # Global break is mathematically valid only when shift == 0 and key is exact unshifted AABB sq dist.
                if key > best_floor:
                    pruned = left[6] * right[6]
                    for item in pending:
                        pruned += item[3][6] * item[4][6]
                    counts['subtree_pruned_pairs'] += pruned
                    break
                bp0, bp1 = best_pair
                strict = (left[10] < bp0 or (left[10] == bp0 and right[10] < bp1))
                if not strict and key > tie_floor:
                    counts['subtree_pruned_pairs'] += left[6] * right[6]
                    continue
            else:
                tick('aabb_bound_tests')
                bp0, bp1 = best_pair
                strict = (left[10] < bp0 or (left[10] == bp0 and right[10] < bp1))
                if _aabb_exceeds_best(
                        ((left[0], left[3]), (left[1], left[4]), (left[2], left[5])),
                        ((right[0], right[3]), (right[1], right[4]), (right[2], right[5])),
                        best, strict=strict):
                    counts['subtree_pruned_pairs'] += left[6] * right[6]
                    continue
            if proj_enabled and fast_ints and best[0] > 0:
                fp = ensure_fast_proj(1)
                if fp is not None:
                    use_vs = left[6] <= 512 and right[6] <= 512
                    if fp.prunes_nodes(
                            left, right, strict, budget,
                            use_vertex_slab=use_vs, credit=credit, best_pair=best_pair):
                        counts['witness_projection_pruned_pairs'] = counts.get('witness_projection_pruned_pairs', 0) + 1
                        counts['witness_projection_node_pruned_pairs'] = counts.get('witness_projection_node_pruned_pairs', 0) + 1
                        counts['subtree_pruned_pairs'] += left[6] * right[6]
                        singleton_leaf = (shift == 0 and left[6] == 1 and right[6] == 1)
                        saved_np = (
                            (left[6] * right[6] * (1 if singleton_leaf else 2))
                            if (left[7] is not None and right[7] is not None) else 2
                        )
                        credit.earn_node_prune(saved_np)
                        continue
        elif cutoff_sentinel is not None:
            if shift == 0:
                counts['dequeue_reused_aabb_bounds'] = counts.get('dequeue_reused_aabb_bounds', 0) + 1
                if mode == 'off_paid_dequeue_ref':
                    tick('aabb_bound_tests')
                else:
                    checkpoint('surface_proximity_aabb_bound_tests')
                    counts['aabb_bound_tests'] += 1
                    if proj_enabled:
                        credit.saved_bound()
                if key > cut_floor:
                    pruned = left[6] * right[6]
                    for item in pending:
                        pruned += item[3][6] * item[4][6]
                    counts['subtree_pruned_pairs'] += pruned
                    break
            else:
                tick('aabb_bound_tests')
                if _aabb_exceeds_best(
                        ((left[0], left[3]), (left[1], left[4]), (left[2], left[5])),
                        ((right[0], right[3]), (right[1], right[4]), (right[2], right[5])),
                        cutoff_sentinel, strict=True, remaining=cut_floor):
                    counts['subtree_pruned_pairs'] += left[6] * right[6]
                    continue
            if cutoff_proj is not None:
                use_vs = left[6] <= 512 and right[6] <= 512
                if cutoff_proj.prunes_nodes(left, right, True, budget, use_vertex_slab=use_vs):
                    counts['witness_projection_pruned_pairs'] = counts.get('witness_projection_pruned_pairs', 0) + 1
                    counts['witness_projection_node_pruned_pairs'] = counts.get('witness_projection_node_pruned_pairs', 0) + 1
                    counts['subtree_pruned_pairs'] += left[6] * right[6]
                    continue

        if left[7] is not None and right[7] is not None:
            eval_leaf(left, right)
        elif right[7] is not None or (left[7] is None and left[6] >= right[6]):
            if fast_push:
                r0, r1, r2, r3, r4, r5 = right[0], right[1], right[2], right[3], right[4], right[5]
                r6, r10, r11, r12, r13 = right[6], right[10], right[11], right[12], right[13]
                for child in (left[8], left[9]):
                    tick('queue_bound_tests')
                    gx = child[0] - r3
                    if r0 - child[3] > gx: gx = r0 - child[3]
                    gy = child[1] - r4
                    if r1 - child[4] > gy: gy = r1 - child[4]
                    gz = child[2] - r5
                    if r2 - child[5] > gz: gz = r2 - child[5]
                    k = (gx * gx if gx > 0 else 0) + (gy * gy if gy > 0 else 0) + (gz * gz if gz > 0 else 0)
                    if best is not None:
                        checkpoint('surface_proximity_aabb_bound_tests')
                        bp0, bp1 = best_pair
                        limit_k = best_floor if (child[10] < bp0 or (child[10] == bp0 and r10 < bp1)) else tie_floor
                        if k > limit_k:
                            counts['subtree_pruned_pairs'] += child[6] * r6
                            continue
                    elif cut_floor is not None:
                        checkpoint('surface_proximity_aabb_bound_tests')
                        if k > cut_floor:
                            counts['subtree_pruned_pairs'] += child[6] * r6
                            continue
                    dx = child[11] - r11
                    dy = child[12] - r12
                    dz = child[13] - r13
                    tick('queue_pushes')
                    heappush(pending, (k, dx * dx + dy * dy + dz * dz, serial, child, right))
                    serial += 1
            else:
                for child in (left[8], left[9]):
                    k, cd = _node_queue_bounds(child, right, shift, budget, fast_ints=fast_ints)
                    push_pair(k, cd, child, right)
        else:
            if fast_push:
                l0, l1, l2, l3, l4, l5 = left[0], left[1], left[2], left[3], left[4], left[5]
                l6, l10, l11, l12, l13 = left[6], left[10], left[11], left[12], left[13]
                for child in (right[8], right[9]):
                    tick('queue_bound_tests')
                    gx = l0 - child[3]
                    if child[0] - l3 > gx: gx = child[0] - l3
                    gy = l1 - child[4]
                    if child[1] - l4 > gy: gy = child[1] - l4
                    gz = l2 - child[5]
                    if child[2] - l5 > gz: gz = child[2] - l5
                    k = (gx * gx if gx > 0 else 0) + (gy * gy if gy > 0 else 0) + (gz * gz if gz > 0 else 0)
                    if best is not None:
                        checkpoint('surface_proximity_aabb_bound_tests')
                        bp0, bp1 = best_pair
                        limit_k = best_floor if (l10 < bp0 or (l10 == bp0 and child[10] < bp1)) else tie_floor
                        if k > limit_k:
                            counts['subtree_pruned_pairs'] += l6 * child[6]
                            continue
                    elif cut_floor is not None:
                        checkpoint('surface_proximity_aabb_bound_tests')
                        if k > cut_floor:
                            counts['subtree_pruned_pairs'] += l6 * child[6]
                            continue
                    dx = l11 - child[11]
                    dy = l12 - child[12]
                    dz = l13 - child[13]
                    tick('queue_pushes')
                    heappush(pending, (k, dx * dx + dy * dy + dz * dz, serial, left, child))
                    serial += 1
            else:
                for child in (right[8], right[9]):
                    k, cd = _node_queue_bounds(left, child, shift, budget, fast_ints=fast_ints)
                    push_pair(k, cd, left, child)
    if witness_pair is not None and best_pair is not None:
        witness_pair[:] = best_pair
    return best


def _local_cutoff_from_exact_key(cutoff_key, factor):
    if (type(cutoff_key) not in (list, tuple) or len(cutoff_key) != 3
            or any(type(v) is not int for v in cutoff_key)
            or cutoff_key[0] < 0 or cutoff_key[1] <= 0
            or cutoff_key[0].bit_length() > MAX_BITS or cutoff_key[1].bit_length() > MAX_BITS):
        raise ValueError('invalid _upper_bound_sq_key')
    cn, cd, ce = cutoff_key
    shift = ce + 2 * (factor.bit_length() - 1)
    if abs(shift) > MAX_BITS:
        return None
    if shift >= 0:
        if cn.bit_length() + shift > MAX_BITS:
            return None
        cut_n, cut_d = cn << shift, cd
    else:
        if cd.bit_length() - shift > MAX_BITS:
            return None
        cut_n, cut_d = cn, cd << (-shift)
    return (cut_n, cut_d, cut_n // cut_d)


def _prepared_root_aabb(triangles):
    b0 = triangles[0][4]
    lx0, lx1 = b0[0]
    ly0, ly1 = b0[1]
    lz0, lz1 = b0[2]
    for tri in triangles[1:]:
        b = tri[4]
        ax0, ax1 = b[0]
        ay0, ay1 = b[1]
        az0, az1 = b[2]
        if ax0 < lx0: lx0 = ax0
        if ax1 > lx1: lx1 = ax1
        if ay0 < ly0: ly0 = ay0
        if ay1 > ly1: ly1 = ay1
        if az0 < lz0: lz0 = az0
        if az1 > lz1: lz1 = az1
    return ((lx0, lx1), (ly0, ly1), (lz0, lz1))


def _nearest(prepared, budget, *, prepared_trees=None, prepared_holder=None, witness_pair=None,
             projection_mode=None, cutoff=None):
    na, nb = len(prepared[0]), len(prepared[1])
    if cutoff is not None:
        if prepared_trees is not None:
            r0, r1 = prepared_trees['roots']
            box_a = ((r0[0][0], r0[1][0]), (r0[0][1], r0[1][1]), (r0[0][2], r0[1][2]))
            box_b = ((r1[0][0], r1[1][0]), (r1[0][1], r1[1][1]), (r1[0][2], r1[1][2]))
        else:
            box_a = _prepared_root_aabb(prepared[0])
            box_b = _prepared_root_aabb(prepared[1])
        if _aabb_exceeds_best(box_a, box_b, cutoff, strict=True, remaining=cutoff[2]):
            budget.counts['cutoff_pruned_pairs'] = budget.counts.get('cutoff_pruned_pairs', 0) + na * nb
            return None
    if na * nb <= LINEAR_PAIR_LIMIT:
        return _nearest_linear(prepared, budget, witness_pair, cutoff=cutoff)
    if prepared_trees is None:
        roots = _distance_roots(prepared, budget, holder=prepared_holder)
    else:
        roots = prepared_trees['roots']
        budget.counts['shared_trees'] = True
        if prepared_holder is not None:
            prepared_holder['trees'] = prepared_trees
    return _nearest_tree(prepared, roots, budget, witness_pair, projection_mode=projection_mode, cutoff=cutoff)


def _witness(descriptor):
    kind, *values = descriptor
    if kind == 'contact':
        return values[0], values[0]
    if kind == 'points':
        return values[0], values[1]
    if kind == 'segment_face':
        start, delta, numerator, denominator = values
        point = _add(start, _mul(delta, _fraction(numerator, denominator)))
        return point, point
    if kind == 'edges':
        a, b, u, v, s, t, denominator = values
        return _add(a, _mul(u, _fraction(s, denominator))), _add(b, _mul(v, _fraction(t, denominator)))
    if kind == 'face':
        point, normal, height, squared, reverse = values
        on_surface = _sub(point, _mul(normal, _fraction(height, squared)))
    else:
        point, start, delta, parameter, squared, reverse = values
        on_surface = _add(start, _mul(delta, _fraction(parameter, squared)))
    return (on_surface, point) if reverse else (point, on_surface)


def _scratch(value):
    if abs(value).bit_length() > _MAX_SCRATCH_BITS:
        raise _DomainError('surface_exact_bit_budget')
    return value


def _rounded_distance(numerator, denominator, factor):
    """Round the exact square root to binary64, including halfway cases."""
    if numerator == 0:
        return 0.0
    exponent = numerator.bit_length() - denominator.bit_length()
    below = (numerator < denominator << exponent if exponent >= 0
             else numerator << -exponent < denominator)
    squared_exponent = exponent - int(below)
    root_exponent = squared_exponent // 2
    frame_exponent = factor.bit_length() - 1
    world_exponent = root_exponent - frame_exponent
    if world_exponent < -1075:
        raise _DomainError('surface_distance_below_float_resolution')
    if world_exponent >= 1024:
        raise _DomainError('surface_distance_outside_float_range')
    unit_exponent = max(world_exponent - 52, -1074)
    shift = -2 * (frame_exponent + unit_exponent)
    if shift >= 0:
        cancel = min(shift, (denominator & -denominator).bit_length() - 1)
        scaled_numerator = _scratch(numerator << (shift - cancel))
        scaled_denominator = denominator >> cancel
    else:
        cancel = min(-shift, (numerator & -numerator).bit_length() - 1)
        scaled_numerator = numerator >> cancel
        scaled_denominator = _scratch(denominator << (-shift - cancel))
    integer = math.isqrt(scaled_numerator // scaled_denominator)
    left = _scratch(4 * scaled_numerator)
    right = _scratch(scaled_denominator * (2 * integer + 1) ** 2)
    if left > right or left == right and integer % 2:
        integer += 1
    if integer == 0:
        raise _DomainError('surface_distance_below_float_resolution')
    try:
        return math.ldexp(float(integer), unit_exponent)
    except OverflowError as exc:
        raise _DomainError('surface_distance_outside_float_range') from exc


def _publish_points(points, origin, factor, distance, *, include_exact=False):
    exact = [_add(origin, tuple(_fraction(value, factor) for value in point)) for point in points]
    rounded = [tuple(float(value) for value in point) for point in exact]
    if any(not math.isfinite(value) for point in rounded for value in point):
        return None
    errors = [_sub(tuple(Fraction.from_float(value) for value in point), source)
              for point, source in zip(rounded, exact)]
    tolerance_squared = _PUBLICATION_TOLERANCE * _PUBLICATION_TOLERANCE
    if any(_dot(error, error) > tolerance_squared for error in errors):
        return None
    displacement_error = _sub(errors[1], errors[0])
    if _dot(displacement_error, displacement_error) > tolerance_squared:
        return None
    if distance > 0 and rounded[0] == rounded[1]:
        return None
    reported = math.dist(*rounded)
    if not math.isfinite(reported) or abs(reported - distance) > 1e-9:
        return None
    displayed = [list(point) for point in rounded]
    return (displayed, exact) if include_exact else displayed


def _exact_distance_key(numerator, denominator, factor):
    """Private world square = odd numerator / odd denominator * 2**exponent."""
    if numerator == 0:
        return [0, 1, 0]
    n_shift = (numerator & -numerator).bit_length() - 1
    d_shift = (denominator & -denominator).bit_length() - 1
    return [numerator >> n_shift, denominator >> d_shift,
            n_shift - d_shift - 2 * (factor.bit_length() - 1)]


def _compare_distance_keys(left, right, checkpoint):
    checkpoint('surface_proximity_rank_compare')
    a, b, ae = left
    c, d, ce = right
    if a == 0 or c == 0:
        return (a > 0) - (c > 0)
    common_n, common_d = math.gcd(a, c), math.gcd(b, d)
    lhs = (a // common_n) * (d // common_d)
    rhs = (c // common_n) * (b // common_d)
    leading = lhs.bit_length() + ae - rhs.bit_length() - ce
    if leading:
        return 1 if leading > 0 else -1
    # Equal leading exponents bound the aligned products by the original
    # <=2*MAX_BITS cross-product width, without expanding either factor².
    shift = ae - ce
    if shift >= 0:
        lhs <<= shift
    else:
        rhs <<= -shift
    return (lhs > rhs) - (lhs < rhs)


def _rank_surface_results(results_by_id, checkpoint):
    """Rank provided kernel results only; no scene coverage or host assertion."""
    known, unresolved = {}, {}
    for identity, result in sorted(results_by_id.items()):
        checkpoint('surface_proximity_rank_candidate')
        if result.get('measurement_valid') is not True:
            unresolved[identity] = result.get('reason') or 'surface_measurement_unavailable'
            continue
        key = result.get('_exact_distance_sq')
        if (type(key) not in (list, tuple) or len(key) != 3
                or any(type(value) is not int for value in key)
                or key[0] < 0 or key[1] <= 0
                or key[0].bit_length() > MAX_BITS or key[1].bit_length() > MAX_BITS):
            unresolved[identity] = 'surface_exact_rank_key_unavailable'
            continue
        known[identity] = key
    identities = sorted(known, key=cmp_to_key(
        lambda a, b: _compare_distance_keys(known[a], known[b], checkpoint)))
    groups = []
    for identity in identities:
        if groups and _compare_distance_keys(known[groups[-1][0]], known[identity], checkpoint) == 0:
            groups[-1].append(identity)
        else:
            groups.append([identity])
    checkpoint('surface_proximity_rank_complete')
    return dict(status='partial' if unresolved and known else 'unknown' if not known else 'ranked',
                ordered_object_id_groups=groups, unresolved=unresolved,
                scope='provided_kernel_results_only')


def _point_on_prepared_triangle(point, triangle):
    points, normal, squared, edges, _ = triangle
    if not squared:
        if not edges:
            return point == points[0]
        start, _, edge, edge_squared = edges[0]
        offset = _sub(point, start)
        return not any(_cross(offset, edge)) and 0 <= _dot(offset, edge) <= edge_squared
    if _dot(normal, _sub(point, points[0])) != 0:
        return False
    drop = max(range(3), key=lambda axis: abs(normal[axis]))
    axes = tuple(axis for axis in range(3) if axis != drop)
    sign = 1 if _orient(*points, axes) > 0 else -1
    return all(sign * _orient(points[i], points[(i + 1) % 3], point, axes) >= 0 for i in range(3))


def _witness_triangle_provenance(world, exact_world, local_points, indices, prepared, origin, factor, budget):
    # Validate the same winning triangles for the two encodings of these points.
    try:
        with span('surface_proximity.rounded_source_membership'):
            for point, side, index in zip(world, prepared, indices):
                budget.tick('witness_triangle_checks')
                local = _mul(_sub(tuple(Fraction.from_float(value) for value in point), origin), factor)
                if not _point_on_prepared_triangle(local, side[index]):
                    break
            else:
                return {'witness_triangle_indices': indices}
        with span('surface_proximity.exact_source_membership'):
            for local, side, index in zip(local_points, prepared, indices):
                budget.tick('exact_witness_triangle_checks')
                if not _point_on_prepared_triangle(local, side[index]):
                    return {}
            points_m = [[str(value) for value in point] for point in exact_world]
            if sum(len(value) for point in points_m for value in point) <= MAX_EXACT_SOURCE_BYTES:
                return {'exact_witness_triangles': {'indices': indices, 'points_m': points_m}}
    except _DomainError:
        pass  # Evidence is optional when the remaining exact-arithmetic budget is insufficient.
    return {}


def _boundary_witness(contact, pair, budget):
    """Check a same-query exact contact against its two original triangles."""
    if type(contact) is not dict or contact.get('pair') is not pair:
        return None
    indices, point = contact.get('triangles'), contact.get('point')
    if (type(indices) is not tuple or len(indices) != 2
            or any(type(index) is not int for index in indices)
            or type(point) is not tuple or len(point) != 3
            or any(type(value) not in (int, Fraction) for value in point)):
        return None
    budget.checkpoint('surface_proximity_boundary_witness')
    try:
        for value in point:
            _bounded(value)
        for side, index in zip(pair[4], indices):
            if not 0 <= index < len(side):
                return None
            triangle = side[index]
            if not triangle[2] or not _point_on_prepared_triangle(point, triangle):
                return None
    except _DomainError:
        return None
    return point


class _CacheBuildBudget:
    """Forward local-cache BVH build costs and checkpoints directly to caller budget."""
    __slots__ = ('budget', 'units')

    def __init__(self, budget):
        self.budget = budget
        self.units = 0

    def consume(self, amount, stage):
        self.units += amount
        self.budget.consume(amount, stage)


def _mesh_cache_is_immutable(verts, faces, budget=None):
    """Fail-closed deep tuple immutability check on captured references; ALL ndarrays fail closed."""
    if type(verts) is not tuple or type(faces) is not tuple:
        return False
    if not faces or len(faces) > MAX_FACES:
        return False
    n_verts = len(verts)
    checked_v = set()
    checkpoint = budget.checkpoint if budget is not None else None
    for row in faces:
        if checkpoint is not None:
            checkpoint('surface_proximity_face_validate')
        if type(row) is not tuple or len(row) != 3:
            return False
        a, b, c = row
        if type(a) is not int or type(b) is not int or type(c) is not int:
            return False
        if not (0 <= a < n_verts and 0 <= b < n_verts and 0 <= c < n_verts):
            return False
        for idx in row:
            if idx not in checked_v:
                v = verts[idx]
                if (type(v) is not tuple or len(v) != 3
                        or type(v[0]) not in (int, float)
                        or type(v[1]) not in (int, float)
                        or type(v[2]) not in (int, float)):
                    return False
                checked_v.add(idx)
    return True


def _ensure_cached_frame(ent, budget):
    frame = ent.get('frame')
    if frame is not None:
        budget.tick('referenced_vertices', len(ent['admission'][0][2]))
        return frame, True
    mesh, _, indices = ent['admission'][0]
    verts = ent.get('verts_ref', mesh.vertices)
    is_np = _is_numpy_2d_vertices(verts)
    budget.checkpoint('surface_proximity_referenced_vertices')
    fx, fy, fz = _read_vertex_xyz(verts, indices[0], is_np)
    origin_frac = (_bounded(Fraction.from_float(fx)),
                   _bounded(Fraction.from_float(fy)),
                   _bounded(Fraction.from_float(fz)))
    o_dy = (_float_dyadic(fx), _float_dyadic(fy), _float_dyadic(fz))
    o0, o1, o2 = o_dy
    rel = {}
    local_exp = 0
    tick = budget.tick
    checkpoint = budget.checkpoint
    for idx in indices:
        tick('referenced_vertices')
        vx, vy, vz = _read_vertex_xyz(verts, idx, is_np)
        dx = _sub_dyadic(_float_dyadic(vx), o0)
        dy = _sub_dyadic(_float_dyadic(vy), o1)
        dz = _sub_dyadic(_float_dyadic(vz), o2)
        if dx[0] and -dx[1] > local_exp: local_exp = -dx[1]
        if dy[0] and -dy[1] > local_exp: local_exp = -dy[1]
        if dz[0] and -dz[1] > local_exp: local_exp = -dz[1]
        rel[idx] = (dx, dy, dz)
    ints = {}
    max_bits = 0
    for idx, (dx, dy, dz) in rel.items():
        checkpoint('surface_proximity_referenced_vertices')
        ix = dx[0] << (local_exp + dx[1]) if dx[0] else 0
        iy = dy[0] << (local_exp + dy[1]) if dy[0] else 0
        iz = dz[0] << (local_exp + dz[1]) if dz[0] else 0
        b = max(abs(ix).bit_length(), abs(iy).bit_length(), abs(iz).bit_length())
        if b > max_bits:
            max_bits = b
        ints[idx] = (ix, iy, iz)
    frame = dict(
        o_dy=o_dy, origin_frac=origin_frac, local_exp=local_exp,
        rel=rel, ints=ints, max_bits=max_bits, fit_fast=max_bits < 480,
    )
    ent['frame'] = frame
    return frame, False


def _translate_bvh(node, shift_e, tx, ty, tz, *, budget=None):
    checkpoint = budget.checkpoint if budget is not None else None
    nodes = 0

    def walk(cur):
        nonlocal nodes
        if checkpoint is not None:
            checkpoint('surface_proximity_surface_bvh_build')
        nodes += 1
        lo, hi, count, ids, left, right = cur
        if shift_e:
            nlo = ((lo[0] << shift_e) + tx, (lo[1] << shift_e) + ty, (lo[2] << shift_e) + tz)
            nhi = ((hi[0] << shift_e) + tx, (hi[1] << shift_e) + ty, (hi[2] << shift_e) + tz)
        else:
            nlo = (lo[0] + tx, lo[1] + ty, lo[2] + tz)
            nhi = (hi[0] + tx, hi[1] + ty, hi[2] + tz)
        if ids is not None:
            return (nlo, nhi, count, ids, None, None)
        return (nlo, nhi, count, None, walk(left), walk(right))

    root = walk(node)
    if budget is not None:
        budget.counts['mesh_cache_translate_units'] = budget.counts.get('mesh_cache_translate_units', 0) + nodes
    return root


def _translate_triangles(local_tris, shift_e, tx, ty, tz, *, budget=None, charge_prepare=False):
    tris = []
    append = tris.append
    checkpoint = budget.checkpoint if budget is not None else None
    tick = budget.tick if budget is not None else None
    if shift_e == 0:
        for pts, normal, squared, edges, bounds in local_tris:
            if checkpoint is not None:
                if charge_prepare:
                    tick('prepared_triangles')
                else:
                    checkpoint('surface_proximity_triangle_prepare')
            npts = tuple((p[0] + tx, p[1] + ty, p[2] + tz) for p in pts)
            nedges = [((s[0] + tx, s[1] + ty, s[2] + tz),
                       (e[0] + tx, e[1] + ty, e[2] + tz), d, dd) for s, e, d, dd in edges]
            (lx0, hx0), (ly0, hy0), (lz0, hz0) = bounds
            nbounds = ((lx0 + tx, hx0 + tx), (ly0 + ty, hy0 + ty), (lz0 + tz, hz0 + tz))
            append((npts, normal, squared, nedges, nbounds))
        if budget is not None:
            budget.counts['mesh_cache_translate_units'] = budget.counts.get('mesh_cache_translate_units', 0) + len(tris)
        return tris
    s2 = shift_e + shift_e
    s4 = s2 + s2
    for pts, normal, squared, edges, bounds in local_tris:
        if checkpoint is not None:
            if charge_prepare:
                tick('prepared_triangles')
            else:
                checkpoint('surface_proximity_triangle_prepare')
        npts = tuple(((p[0] << shift_e) + tx, (p[1] << shift_e) + ty, (p[2] << shift_e) + tz) for p in pts)
        nnormal = (normal[0] << s2, normal[1] << s2, normal[2] << s2) if squared else normal
        nsquared = squared << s4 if squared else 0
        nedges = [(((s[0] << shift_e) + tx, (s[1] << shift_e) + ty, (s[2] << shift_e) + tz),
                   ((e[0] << shift_e) + tx, (e[1] << shift_e) + ty, (e[2] << shift_e) + tz),
                   (d[0] << shift_e, d[1] << shift_e, d[2] << shift_e), dd << s2)
                  for s, e, d, dd in edges]
        (lx0, hx0), (ly0, hy0), (lz0, hz0) = bounds
        nbounds = (((lx0 << shift_e) + tx, (hx0 << shift_e) + tx),
                   ((ly0 << shift_e) + ty, (hy0 << shift_e) + ty),
                   ((lz0 << shift_e) + tz, (hz0 << shift_e) + tz))
        append((npts, nnormal, nsquared, nedges, nbounds))
    if budget is not None:
        budget.counts['mesh_cache_translate_units'] = budget.counts.get('mesh_cache_translate_units', 0) + len(tris)
    return tris


def _pair_from_mesh_cache(left, right, budget, mesh_cache, witness_pair=None, need_trees=True):
    l_verts = getattr(left, 'vertices', None)
    l_faces = getattr(left, 'faces', None)
    r_verts = getattr(right, 'vertices', None)
    r_faces = getattr(right, 'faces', None)
    if l_faces is None or r_faces is None:
        raise _DomainError('surface_geometry_work_limit')
    nl_raw, nr_raw = len(l_faces), len(r_faces)
    if not nl_raw or not nr_raw or nl_raw + nr_raw > MAX_FACES:
        raise _DomainError('surface_geometry_work_limit')
    if type(mesh_cache) is not dict:
        return None

    def cached_valid(mesh, verts, faces):
        mid = id(mesh)
        ent = mesh_cache.get(mid)
        if ent is not None:
            if (ent.get('mesh') is mesh
                    and ent.get('verts_ref') is verts
                    and ent.get('faces_ref') is faces
                    and ent.get('verts_id') == id(verts)
                    and ent.get('faces_id') == id(faces)
                    and ent.get('verts_len') == (len(verts) if type(verts) is tuple else -1)
                    and ent.get('faces_len') == (len(faces) if type(faces) is tuple else -1)
                    and ent.get('verts_kind') == 'tuple'
                    and ent.get('faces_kind') == 'tuple'
                    and type(verts) is tuple
                    and type(faces) is tuple
                    and 'admission' in ent):
                return ent, True
            mesh_cache.pop(mid, None)
        return None, False

    c_l, ok_l = cached_valid(left, l_verts, l_faces)
    c_r, ok_r = cached_valid(right, r_verts, r_faces)
    if (not ok_l and not _mesh_cache_is_immutable(l_verts, l_faces, budget)) or (not ok_r and not _mesh_cache_is_immutable(r_verts, r_faces, budget)):
        return None

    # Stage 1: Lazy on-demand admission using captured immutable refs (never re-reading wrapper attrs).
    valid_int_types = {int}
    entries = []
    for mesh, verts_ref, faces_ref, cached_ent, is_ok in (
        (left, l_verts, l_faces, c_l, ok_l),
        (right, r_verts, r_faces, c_r, ok_r),
    ):
        if is_ok:
            ent = cached_ent
            rec, _ = ent['admission']
            budget.tick('validated_faces', len(rec[1]))
        else:
            rec, topo = _admit_one(
                mesh, budget.tick, valid_int_types, checkpoint=budget.checkpoint,
                verts=verts_ref, faces=faces_ref,
            )
            ent = {
                'mesh': mesh,
                'verts_ref': verts_ref, 'faces_ref': faces_ref,
                'verts_id': id(verts_ref), 'faces_id': id(faces_ref),
                'verts_len': len(verts_ref), 'faces_len': len(faces_ref),
                'verts_kind': 'tuple',
                'faces_kind': 'tuple',
                'face_count': len(rec[1]),
                'ref_vertex_count': len(rec[2]),
                'admission': (rec, topo),
            }
            if getattr(mesh, 'vertices', None) is verts_ref and getattr(mesh, 'faces', None) is faces_ref:
                if len(mesh_cache) >= _MESH_CACHE_MAX_ENTRIES:
                    evict_key = next((k for k in mesh_cache if type(k) is int and k not in (id(left), id(right))), None)
                    if evict_key is not None:
                        mesh_cache.pop(evict_key, None)
                mesh_cache[id(mesh)] = ent
            else:
                mesh_cache.pop(id(mesh), None)
        entries.append(ent)

    el, er = entries
    rec_l, topo_l = el['admission']
    rec_r, topo_r = er['admission']
    nl, nr = len(rec_l[1]), len(rec_r[1])
    if not nl or not nr or nl + nr > MAX_FACES:
        raise _DomainError('surface_geometry_work_limit')

    # Stage 2: Lazy local coordinate frames & bit-domain verification.
    fl, hl = _ensure_cached_frame(el, budget)
    fr, hr = _ensure_cached_frame(er, budget)
    budget.counts['mesh_cache_hits'] = budget.counts.get('mesh_cache_hits', 0) + int(hl) + int(hr)
    budget.counts['mesh_cache_misses'] = budget.counts.get('mesh_cache_misses', 0) + int(not hl) + int(not hr)

    dx_o = _sub_dyadic(fr['o_dy'][0], fl['o_dy'][0])
    dy_o = _sub_dyadic(fr['o_dy'][1], fl['o_dy'][1])
    dz_o = _sub_dyadic(fr['o_dy'][2], fl['o_dy'][2])
    exponent = max(fl['local_exp'], fr['local_exp'],
                   -dx_o[1] if dx_o[0] else 0,
                   -dy_o[1] if dy_o[0] else 0,
                   -dz_o[1] if dz_o[0] else 0)
    dL = exponent - fl['local_exp']
    dR = exponent - fr['local_exp']
    tx = dx_o[0] << (exponent + dx_o[1]) if dx_o[0] else 0
    ty = dy_o[0] << (exponent + dy_o[1]) if dy_o[0] else 0
    tz = dz_o[0] << (exponent + dz_o[1]) if dz_o[0] else 0
    t_bits = max(abs(tx).bit_length(), abs(ty).bit_length(), abs(tz).bit_length())
    records = (rec_l, rec_r)
    topology = [dict(topo_l), dict(topo_r)]

    if not (fl['fit_fast'] and fr['fit_fast']
            and fl['max_bits'] + dL < 490
            and max(t_bits, fr['max_bits'] + dR) + 1 < 490):
        # Fallback cleanly without building local fast triangles or BVHs or re-running _admit.
        budget.counts['mesh_cache_fallbacks'] = budget.counts.get('mesh_cache_fallbacks', 0) + 1
        nx = (-dx_o[0], dx_o[1])
        ny = (-dy_o[0], dy_o[1])
        nz = (-dz_o[0], dz_o[1])
        fb_exp = fl['local_exp']
        rel_r_in_l = {}
        checkpoint = budget.checkpoint
        for idx, (vx, vy, vz) in fr['rel'].items():
            checkpoint('surface_proximity_mesh_cache_affine_fallback')
            rx = _sub_dyadic(vx, nx)
            ry = _sub_dyadic(vy, ny)
            rz = _sub_dyadic(vz, nz)
            if rx[0] and -rx[1] > fb_exp: fb_exp = -rx[1]
            if ry[0] and -ry[1] > fb_exp: fb_exp = -ry[1]
            if rz[0] and -rz[1] > fb_exp: fb_exp = -rz[1]
            rel_r_in_l[idx] = (rx, ry, rz)
        factor, prepared = _prepare_triangles_from_relative(
            ((rec_l[1], fl['rel']), (rec_r[1], rel_r_in_l)), fb_exp, budget)
        for side_m, side_ent in ((left, el), (right, er)):
            if (getattr(side_m, 'vertices', None) is not side_ent['verts_ref']
                    or getattr(side_m, 'faces', None) is not side_ent['faces_ref']):
                mesh_cache.pop(id(side_m), None)
        return records, topology, fl['origin_frac'], factor, prepared, None

    factor = _bounded(1 << exponent)
    # Stage 2b: Lazy local triangle construction & translation.
    prepared = []
    for ent, rec, frame, dS, sx, sy, sz in (
        (el, rec_l, fl, dL, 0, 0, 0),
        (er, rec_r, fr, dR, tx, ty, tz),
    ):
        local_tris = ent.get('local_tris')
        tris_cached = local_tris is not None
        if not tris_cached:
            local_tris = _build_fast_triangles(rec[1], frame['ints'], budget=budget)
            ent['local_tris'] = local_tris
        if dS or sx or sy or sz:
            tris = _translate_triangles(local_tris, dS, sx, sy, sz, budget=budget, charge_prepare=tris_cached)
        else:
            if tris_cached:
                budget.tick('prepared_triangles', len(local_tris))
            tris = local_tris
        prepared.append(tris)

    # Stage 3: Lazy local BVH construction ONLY for non-linear pairs.
    roots = None
    if need_trees and nl * nr > LINEAR_PAIR_LIMIT:
        from .surface_geometry import _bvh_from_flat_bounds
        out_roots = []
        for ent, n_faces, dS, sx, sy, sz in (
            (el, nl, dL, 0, 0, 0),
            (er, nr, dR, tx, ty, tz),
        ):
            budget.tick('tree_build_units', n_faces)
            budget.tick('tree_builds', 1)
            tree_entry = ent.get('tree')
            if tree_entry is None:
                local_tris = ent['local_tris']
                local_flat = [None] * len(local_tris)
                for row_idx, t in enumerate(local_tris):
                    b = t[4]
                    ax, bx = b[0]
                    ay, by = b[1]
                    az, bz = b[2]
                    local_flat[row_idx] = (ax, ay, az, bx, by, bz, ax + bx, ay + by, az + bz)
                b_proxy = _CacheBuildBudget(budget)
                local_root = _bvh_from_flat_bounds(local_flat, b_proxy, leaf_size=2)
                tree_entry = {'local_root': local_root, 'bvh_units': b_proxy.units}
                ent['tree'] = tree_entry
                budget.counts['mesh_cache_tree_builds'] = budget.counts.get('mesh_cache_tree_builds', 0) + 1
                budget.counts['mesh_cache_tree_build_units'] = budget.counts.get('mesh_cache_tree_build_units', 0) + b_proxy.units
            else:
                budget.counts['mesh_cache_tree_reuses'] = budget.counts.get('mesh_cache_tree_reuses', 0) + 1
                budget.consume(tree_entry['bvh_units'], 'surface_bvh_build')
            if dS or sx or sy or sz:
                out_roots.append(_translate_bvh(tree_entry['local_root'], dS, sx, sy, sz, budget=budget))
            else:
                out_roots.append(tree_entry['local_root'])
        roots = tuple(out_roots)
    for side_m, side_ent in ((left, el), (right, er)):
        if (getattr(side_m, 'vertices', None) is not side_ent['verts_ref']
                or getattr(side_m, 'faces', None) is not side_ent['faces_ref']):
            mesh_cache.pop(id(side_m), None)
    return records, topology, fl['origin_frac'], factor, prepared, roots


def measure_surface_proximity(left, right, checkpoint, *, diagnostics=None, retain_exact_rank=False,
                              retain_witness_triangles=False, _prepared_pair=None, _boundary_contact=None,
                              _prepared_trees=None,
                              _prepared_holder=None, _mesh_cache=None, _projection_mode=None,
                              _upper_bound_sq_key=None):
    """Measure only the requested triangle surfaces, retaining known quantities."""
    mode = _DEFAULT_PROJECTION_MODE if _projection_mode is None else _projection_mode
    if mode not in _VALID_PROJECTION_MODES:
        raise ValueError(f'unsupported projection_mode: {mode!r}')
    if _upper_bound_sq_key is not None:
        if (type(_upper_bound_sq_key) not in (list, tuple) or len(_upper_bound_sq_key) != 3
                or any(type(v) is not int for v in _upper_bound_sq_key)
                or _upper_bound_sq_key[0] < 0 or _upper_bound_sq_key[1] <= 0
                or _upper_bound_sq_key[0].bit_length() > MAX_BITS
                or _upper_bound_sq_key[1].bit_length() > MAX_BITS):
            raise ValueError('invalid _upper_bound_sq_key')
    checkpoint('surface_proximity_admission')
    budget = _Work(checkpoint, diagnostics)
    budget.counts['witness_projection_mode'] = mode
    budget.counts['witness_projection_credit_reference'] = (
        'mandatory_031_dequeue_aabb' if mode == 'settled_credit_031_ref'
        else ('paid_dequeue_reference' if mode == 'off_paid_dequeue_ref' else 'none')
    )
    witness_pair = [] if retain_witness_triangles else None
    if witness_pair is not None:
        budget.counts['witness_triangle_checks'] = 0
    if _prepared_holder is not None:
        for key in ('pair', 'work', 'coordinates', 'trees', 'witness_points'):
            _prepared_holder.pop(key, None)
        _prepared_holder['work'] = budget
    result = dict(measurement_valid=False, distance_m=None, point_a_world=None,
        point_b_world=None, direction_a_to_b=None, witness_status='unknown',
        direction_status='unknown', topology=None, method=METHOD,
        work=budget.counts)
    try:
        cached_roots = None
        if (_prepared_pair is None or _prepared_pair[0][0][0] is not left
                or _prepared_pair[0][1][0] is not right):
            fast_cached = (_pair_from_mesh_cache(left, right, budget, _mesh_cache)
                           if _mesh_cache is not None and _prepared_holder is None else None)
            if fast_cached is not None:
                records, result['topology'], origin, factor, prepared, cached_roots = fast_cached
            else:
                records, result['topology'] = _admit((left, right), budget)
                origin, factor, prepared = _integer_frame(records, budget, holder=_prepared_holder)
            pair = (records, result['topology'], origin, factor, prepared)
            contact = None
        else:
            records, result['topology'], origin, factor, prepared = _prepared_pair
            pair = _prepared_pair
            budget.counts['shared_preparation'] = True
            contact = _boundary_witness(_boundary_contact, _prepared_pair, budget)
        if _prepared_holder is not None:
            _prepared_holder['pair'] = pair
        cutoff = (_local_cutoff_from_exact_key(_upper_bound_sq_key, factor)
                  if _upper_bound_sq_key is not None and contact is None else None)
        if contact is None:
            if cached_roots is not None:
                if cutoff is not None:
                    box_a = ((cached_roots[0][0][0], cached_roots[0][1][0]),
                             (cached_roots[0][0][1], cached_roots[0][1][1]),
                             (cached_roots[0][0][2], cached_roots[0][1][2]))
                    box_b = ((cached_roots[1][0][0], cached_roots[1][1][0]),
                             (cached_roots[1][0][1], cached_roots[1][1][1]),
                             (cached_roots[1][0][2], cached_roots[1][1][2]))
                    if _aabb_exceeds_best(box_a, box_b, cutoff, strict=True, remaining=cutoff[2]):
                        budget.counts['cutoff_pruned_pairs'] = (
                            budget.counts.get('cutoff_pruned_pairs', 0)
                            + len(prepared[0]) * len(prepared[1])
                        )
                        nearest = None
                    else:
                        nearest = _nearest_tree(
                            prepared, cached_roots, budget, witness_pair,
                            projection_mode=mode, cutoff=cutoff)
                else:
                    nearest = _nearest_tree(
                        prepared, cached_roots, budget, witness_pair, projection_mode=mode)
            else:
                trees = None
                if (_prepared_pair is not None and type(_prepared_trees) is dict
                        and _prepared_trees.get('pair') is _prepared_pair
                        and len(_prepared_trees.get('triangles', ())) == 2
                        and all(a is b for a,b in zip(_prepared_trees['triangles'],prepared))):
                    trees = _prepared_trees
                nearest = _nearest(prepared, budget, prepared_trees=trees,
                                   prepared_holder=_prepared_holder,
                                   witness_pair=witness_pair,
                                   projection_mode=mode,
                                   cutoff=cutoff)
            if nearest is None:
                checkpoint('surface_proximity_complete')
                return {
                    'measurement_valid': True,
                    'cutoff_pruned': True,
                    'pruned_strictly_above_cutoff': True,
                    'topology': result['topology'],
                    'method': METHOD,
                    'work': dict(budget.counts),
                }
            numerator, denominator, descriptor = nearest
        else:
            budget.counts['zero_witness_reused'] = True
            numerator, denominator, descriptor = 0, 1, ('contact', contact)
            if witness_pair is not None:
                witness_pair[:] = _boundary_contact['triangles']
    except _DomainError as exc:
        result['reason'] = str(exc)
        return result
    checkpoint('surface_proximity_publish')
    try:
        distance = _rounded_distance(numerator, denominator, factor)
    except _DomainError as exc:
        result['reason'] = str(exc)
        return result
    with localcontext() as context:
        context.prec = 80
        local_distance = (Decimal(numerator) / Decimal(denominator)).sqrt()
        result.update(measurement_valid=True, distance_m=distance)
        if retain_exact_rank:
            checkpoint('surface_proximity_exact_rank_key')
            result['_exact_distance_sq'] = _exact_distance_key(numerator, denominator, factor)
        if numerator == 0:
            result.update(direction_status='not_applicable', direction_reason='undefined_zero_distance')
        try:
            points = _witness(descriptor)
            if _prepared_holder is not None:
                _prepared_holder['witness_points'] = points
            if numerator > 0:
                delta = _sub(points[1], points[0])
                direction = [float(Decimal(value.numerator) / Decimal(value.denominator) / local_distance)
                             if isinstance(value, Fraction) else float(Decimal(value) / local_distance)
                             for value in delta]
                result.update(direction_a_to_b=direction, direction_status='measured')
            publication = _publish_points(points, origin, factor, distance, include_exact=True)
        except _DomainError:
            result['witness_reason'] = 'surface_witness_bit_budget'
            if result['direction_status'] == 'unknown':
                result['direction_reason'] = 'surface_witness_bit_budget'
            return result
    if publication is None:
        result['witness_reason'] = 'original_surface_witness_precision_exceeded'
    else:
        world, exact_world = publication
        result.update(point_a_world=world[0], point_b_world=world[1], witness_status='measured')
        if witness_pair:
            result.update(_witness_triangle_provenance(
                world, exact_world, points, witness_pair, prepared, origin, factor, budget))
    checkpoint('surface_proximity_complete')
    return result


def _public_support_direction(surface, budget):
    points = (surface.get('point_a_world'), surface.get('point_b_world'))
    if (surface.get('measurement_valid') is not True or surface.get('witness_status') != 'measured'
            or any(type(point) not in (list, tuple) or len(point) != 3 for point in points)
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for point in points for value in point)):
        return None, 'spatial_support_direction_unavailable'
    direction = []
    for left, right in zip(*points):
        budget.tick('support_direction_components')
        direction.append(_bounded(Fraction.from_float(float(right)) - Fraction.from_float(float(left))))
    exponent = max(value.denominator.bit_length()-1 for value in direction)
    integers = tuple(_bounded(value.numerator << (exponent-value.denominator.bit_length()+1))
                     for value in direction)
    divisor = math.gcd(*integers)
    if not divisor:
        return None, 'spatial_support_direction_zero'
    return tuple(value//divisor for value in integers), None


def _referenced_support_evidence(surface, holder, budget):
    direction, reason = _public_support_direction(surface, budget)
    if direction is None:
        return None, reason
    pair, coordinates = holder.get('pair'), holder.get('coordinates')
    if pair is None or coordinates is None:
        return None, 'spatial_support_preparation_unavailable'
    extrema, indices = [], []
    for side, (record, points) in enumerate(zip(pair[0], coordinates)):
        value = chosen = None
        for index in record[2]:
            budget.tick('support_source_vertices')
            budget.tick('support_vertex_dots')
            projection = _dot(direction, points[index])
            if value is None or (projection > value if side == 0 else projection < value):
                value, chosen = projection, index
        extrema.append(value)
        indices.append(chosen)
    if extrema[1] <= extrema[0]:
        return None, 'spatial_support_not_strictly_separated'
    return dict(proposal='first_public_nearest_points_difference', primitive_direction=list(direction),
        left_max=extrema[0], right_min=extrema[1], left_vertex_index=indices[0], right_vertex_index=indices[1],
        referenced_counts=[len(record[2]) for record in pair[0]],
        origin=[[value.numerator, value.denominator] for value in pair[2]], factor=pair[3]), None


def measure_spatial_relation(left, right, checkpoint, *, diagnostics=None, retain_exact_rank=False,
                             prepared_holder=None):
    """Prove sufficient support separation, or run the original classifier once."""
    metrics = diagnostics if diagnostics is not None else {}
    metrics.update(surface_pair_count=1, closed_solid_pair_count=0,
                   closed_solid_work={}, support_work={})
    surface_work = {}
    metrics['surface_work'] = surface_work
    holder = prepared_holder if prepared_holder is not None else {}
    surface = measure_surface_proximity(left, right, checkpoint, diagnostics=surface_work,
        retain_exact_rank=retain_exact_rank, _prepared_holder=holder)
    budget = holder['work']
    before_support = budget.counts['work_units']
    spatial = dict(measurement_valid=False, relation=None, method=SPATIAL_METHOD,
                   geometry_scope=SPATIAL_SCOPE, relation_tolerance_m=0.0)
    closed = None
    budget_stopped = surface.get('reason') in _SURFACE_RESOURCE_STOPS
    stop_reason = surface.get('reason') if budget_stopped else None
    support_reason = stop_reason
    if not budget_stopped:
        try:
            evidence, support_reason = _referenced_support_evidence(surface, holder, budget)
            if evidence is not None:
                spatial.update(measurement_valid=True, relation='separated',
                    certificate='strict_all_referenced_vertex_support', support_evidence=evidence)
        except _DomainError as exc:
            support_reason = str(exc)
            if support_reason in _SURFACE_RESOURCE_STOPS:
                budget_stopped, stop_reason = True, support_reason
    metrics['support_work'].update({key:budget.counts[key] for key in
        ('support_direction_components', 'support_source_vertices', 'support_vertex_dots')})
    metrics['support_work'].update(work_units_before=before_support,
        work_units_after=budget.counts['work_units'], reason=support_reason)
    if budget_stopped:
        spatial['reason'] = stop_reason
    elif spatial['measurement_valid'] is not True:
        from .surface_geometry import classify_closed_solids
        metrics['closed_solid_pair_count'] = 1
        closed = classify_closed_solids(left, right, checkpoint, diagnostics=metrics['closed_solid_work'],
            prepared_pair=holder.get('pair'), prepared_trees=holder.get('trees'), prepared_holder=holder)
        spatial = {key:closed[key] for key in ('measurement_valid', 'relation', 'method', 'geometry_scope',
            'relation_tolerance_m', 'certificate', 'local_evidence', 'reason') if key in closed}
        if closed.get('reason') in _CLOSED_RESOURCE_STOPS:
            budget_stopped, stop_reason = True, closed['reason']
    checkpoint('spatial_relation_complete')
    return dict(measurement_valid=surface.get('measurement_valid') is True
                    and spatial.get('measurement_valid') is True,
                surface=surface, spatial=spatial, closed=closed,
                budget_stopped=budget_stopped, stop_reason=stop_reason)


def _mesh_world_aabb(mesh):
    verts = getattr(mesh, 'vertices', None)
    if verts is None:
        return None
    try:
        if len(verts) <= 0:
            return None
        if _is_numpy_2d_vertices(verts):
            lo = verts.min(axis=0)
            hi = verts.max(axis=0)
            bx = ((float(lo[0]), float(lo[1]), float(lo[2])),
                  (float(hi[0]), float(hi[1]), float(hi[2])))
        else:
            v0 = verts[0]
            if len(v0) != 3:
                return None
            lx = hx = float(v0[0])
            ly = hy = float(v0[1])
            lz = hz = float(v0[2])
            for p in verts[1:]:
                x, y, z = float(p[0]), float(p[1]), float(p[2])
                if x < lx: lx = x
                elif x > hx: hx = x
                if y < ly: ly = y
                elif y > hy: hy = y
                if z < lz: lz = z
                elif z > hz: hz = z
            bx = ((lx, ly, lz), (hx, hy, hz))
        if all(math.isfinite(c) for side in bx for c in side):
            return bx
    except Exception:
        return None
    return None


def measure_nearest_surface_batch(target, peers, checkpoint, *, use_mesh_cache=True,
                                use_cutoff=True, sort_by_aabb=True,
                                retain_witness_triangles=False):
    """Find all exact nearest peers to target with optional cutoff & AABB ordering."""
    n_peers = len(peers)
    if n_peers == 0:
        return {
            'measurement_valid': False,
            'status': 'unknown',
            'nearest_indices': [],
            'best_exact_distance_sq': None,
            'distance_m': None,
            'results_by_index': [],
            'unresolved_indices': [],
            'cutoff_pruned_count': 0,
            'evaluated_count': 0,
        }
    order = list(range(n_peers))
    if sort_by_aabb and n_peers > 1:
        tbox = _mesh_world_aabb(target)
        if tbox is not None:
            (tx0, ty0, tz0), (tx1, ty1, tz1) = tbox
            scores = []
            for idx in order:
                pbox = _mesh_world_aabb(peers[idx])
                if pbox is None:
                    scores.append((0.0, idx))
                    continue
                (px0, py0, pz0), (px1, py1, pz1) = pbox
                gx = tx0 - px1 if tx0 > px1 else (px0 - tx1 if px0 > tx1 else 0.0)
                gy = ty0 - py1 if ty0 > py1 else (py0 - ty1 if py0 > ty1 else 0.0)
                gz = tz0 - pz1 if tz0 > pz1 else (pz0 - tz1 if pz0 > tz1 else 0.0)
                gap = math.hypot(gx, gy, gz)
                scores.append((gap if math.isfinite(gap) else 0.0, idx))
            scores.sort()
            order = [idx for _, idx in scores]

    cache = {} if use_mesh_cache else None
    results_by_index = [None] * n_peers
    nearest_indices = []
    unresolved_indices = []
    best_key = None
    cutoff_pruned_count = 0
    evaluated_count = 0

    for idx in order:
        res = measure_surface_proximity(
            target, peers[idx], checkpoint,
            retain_exact_rank=True,
            retain_witness_triangles=retain_witness_triangles,
            _mesh_cache=cache,
            _upper_bound_sq_key=(best_key if use_cutoff else None),
        )
        results_by_index[idx] = res
        if res.get('cutoff_pruned'):
            cutoff_pruned_count += 1
        elif res.get('measurement_valid') is True and '_exact_distance_sq' in res:
            evaluated_count += 1
            ek = res['_exact_distance_sq']
            if best_key is None:
                best_key = ek
                nearest_indices = [idx]
            else:
                cmp = _compare_distance_keys(ek, best_key, checkpoint)
                if cmp < 0:
                    best_key = ek
                    nearest_indices = [idx]
                elif cmp == 0:
                    nearest_indices.append(idx)
        else:
            evaluated_count += 1
            unresolved_indices.append(idx)

    nearest_indices.sort()
    unresolved_indices.sort()
    status = ('complete' if (nearest_indices and not unresolved_indices)
              else ('partial' if nearest_indices else 'unknown'))
    best_res = results_by_index[nearest_indices[0]] if nearest_indices else None
    return {
        'measurement_valid': status == 'complete',
        'status': status,
        'nearest_indices': nearest_indices,
        'best_exact_distance_sq': best_key,
        'distance_m': best_res.get('distance_m') if best_res else None,
        'results_by_index': results_by_index,
        'unresolved_indices': unresolved_indices,
        'cutoff_pruned_count': cutoff_pruned_count,
        'evaluated_count': evaluated_count,
    }
