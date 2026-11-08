"""Finite exact distances between the captured binary64 triangle surfaces.

The small intersection predicates below reuse surface_geometry's formulas with
checked arithmetic. This module has no solid qualification or action callers.
"""
from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction
from functools import cmp_to_key
import math
from numbers import Integral


MAX_FACES = 4096
MAX_TRIANGLE_PAIRS = 16384
MAX_BITS = 4096
_MAX_SCRATCH_BITS = 2 * MAX_BITS + 1
METHOD = 'exact_binary64_triangle_surface_hulls_v3'
_PUBLICATION_TOLERANCE = Fraction.from_float(1e-9)


class _DomainError(ValueError):
    pass


def _bounded(value):
    numerator = value.numerator if isinstance(value, Fraction) else value
    denominator = value.denominator if isinstance(value, Fraction) else 1
    if abs(numerator).bit_length() > MAX_BITS or denominator.bit_length() > MAX_BITS:
        raise _DomainError('surface_exact_bit_budget')
    return value


def _fraction(numerator, denominator=1):
    _bounded(numerator)
    _bounded(denominator)
    return _bounded(Fraction(numerator, denominator))


def _sub(a, b):
    return tuple(_bounded(x - y) for x, y in zip(a, b))


def _add(a, b):
    return tuple(_bounded(x + y) for x, y in zip(a, b))


def _mul(a, scale):
    return tuple(_bounded(x * scale) for x in a)


def _dot(a, b):
    total = 0
    for x, y in zip(a, b):
        total = _bounded(total + _bounded(x * y))
    return total


def _cross(a, b):
    return tuple(_bounded(_bounded(a[i] * b[j]) - _bounded(a[j] * b[i]))
                 for i, j in ((1, 2), (2, 0), (0, 1)))


def _normal(triangle):
    return _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0]))


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


def _intersection(a, b, normal_a, normal_b, budget):
    # Same bidirectional slices and common-line interval as the existing kernel.
    da = [_dot(normal_a, _sub(point, a[0])) for point in b]
    db = [_dot(normal_b, _sub(point, b[0])) for point in a]
    if (all(value > 0 for value in da) or all(value < 0 for value in da)
            or all(value > 0 for value in db) or all(value < 0 for value in db)):
        return []
    axis = _cross(normal_a, normal_b)
    if not any(axis):
        return _clip_coplanar(a, b, normal_a, budget) if all(value == 0 for value in da) else []
    pa, pb = _plane_slice(a, db), _plane_slice(b, da)
    if not pa or not pb:
        return []
    k = max(range(3), key=lambda index: abs(axis[index]))
    pa.sort(key=lambda point: point[k])
    pb.sort(key=lambda point: point[k])
    left = max(pa[0], pb[0], key=lambda point: point[k])
    right = min(pa[-1], pb[-1], key=lambda point: point[k])
    return [] if left[k] > right[k] else list(dict.fromkeys((left, right)))


class _Work:
    def __init__(self, checkpoint, diagnostics):
        self.checkpoint = checkpoint
        self.counts = diagnostics if diagnostics is not None else {}
        self.counts.update(validated_faces=0, referenced_vertices=0, triangle_pairs=0,
                           intersection_tests=0, point_face_tests=0,
                           point_edge_tests=0, edge_edge_tests=0, predicate_steps=0,
                           aabb_bound_tests=0, aabb_pruned_pairs=0)

    def tick(self, kind, amount=1):
        self.checkpoint('surface_proximity_' + kind)
        self.counts[kind] += amount


def _admit(meshes, budget):
    sizes = [len(mesh.faces) for mesh in meshes]
    if not all(sizes) or sum(sizes) > MAX_FACES or sizes[0] * sizes[1] > MAX_TRIANGLE_PAIRS:
        raise _DomainError('surface_geometry_work_limit')
    records, topology = [], []
    for mesh in meshes:
        faces, used, incidence = [], set(), Counter()
        for row in mesh.faces:
            budget.tick('validated_faces')
            if (len(row) != 3 or any(not isinstance(index, Integral)
                    or isinstance(index, bool) or not 0 <= index < len(mesh.vertices) for index in row)):
                raise _DomainError('surface_invalid_triangle_indices')
            face = tuple(int(index) for index in row)
            faces.append(face)
            used.update(face)
            incidence.update(tuple(sorted((face[i], face[(i + 1) % 3]))) for i in range(3))
        topology.append(dict(boundary_edge_count=sum(count == 1 for count in incidence.values()),
                             nonmanifold_edge_count=sum(count > 2 for count in incidence.values())))
        records.append((mesh, faces, sorted(used)))
    return records, topology


def _integer_frame(records, budget):
    first_mesh, _, first_indices = records[0]
    first = first_mesh.vertices[first_indices[0]]
    if len(first) != 3 or any(not math.isfinite(float(value)) for value in first):
        raise _DomainError('surface_nonfinite_vertex')
    origin = tuple(_bounded(Fraction.from_float(float(value))) for value in first)
    relative, exponent = [], 0
    for mesh, faces, indices in records:
        coordinates = {}
        for index in indices:
            budget.tick('referenced_vertices')
            values = mesh.vertices[index]
            if len(values) != 3 or any(not math.isfinite(float(value)) for value in values):
                raise _DomainError('surface_nonfinite_vertex')
            point = tuple(_bounded(Fraction.from_float(float(value))) for value in values)
            local = _sub(point, origin)
            exponent = max(exponent, *(value.denominator.bit_length() - 1 for value in local))
            coordinates[index] = local
        relative.append((faces, coordinates))
    factor = _bounded(1 << exponent)
    prepared = []
    for faces, coordinates in relative:
        integers = {index: tuple(_bounded(value.numerator <<
                    (exponent - value.denominator.bit_length() + 1)) for value in point)
                    for index, point in coordinates.items()}
        triangles = []
        for face in faces:
            budget.checkpoint('surface_proximity_triangle_prepare')
            points = tuple(integers[index] for index in face)
            normal = _normal(points)
            if not any(normal):
                # A collinear triple's lexicographic extremes are its closed
                # hull endpoints, regardless of vertex order or duplicates.
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
    return origin, factor, prepared


def _ratio(numerator, denominator):
    divisor = math.gcd(numerator, denominator)
    return _bounded(numerator // divisor), _bounded(denominator // divisor)


def _closer(numerator, denominator, best):
    if numerator < 0 or denominator <= 0:
        raise ArithmeticError('Invalid exact squared surface distance')
    numerator, denominator = _ratio(numerator, denominator)
    if best is None or numerator * best[1] < best[0] * denominator:
        return numerator, denominator
    return None


def _point_faces(point, triangle, reverse, best, budget):
    points, normal, squared, _, _ = triangle
    budget.tick('point_face_tests')
    q = _sub(point, points[0])
    u = _dot(_cross(_sub(points[2], points[0]), normal), q)
    v = _dot(_cross(normal, _sub(points[1], points[0])), q)
    if u < 0 or v < 0 or u + v > squared:
        return best
    height = _dot(q, normal)
    distance = _closer(height * height, squared, best)
    return (*distance, ('face', point, normal, height, squared, reverse)) if distance else best


def _point_edges(point, edge, reverse, best, budget):
    budget.tick('point_edge_tests')
    start, end, delta, squared = edge
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
    distance = _closer(numerator, denominator, best)
    return (*distance, ('edge', point, start, delta, parameter, squared, reverse)) if distance else best


def _edge_edges(left, right, best, budget):
    budget.tick('edge_edge_tests')
    a, _, u, aa = left
    b, _, v, bb = right
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
    distance = _closer(height * height, determinant, best)
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


def _aabb_exceeds_best(left, right, best):
    # The integer squared lower bound exceeds n/d iff it exceeds floor(n/d).
    # Subtract each squared gap from that floor instead of forming L2*d. A gap
    # difference needs at most 4097 scratch bits; only a gap whose square fits
    # the remaining <=4096-bit integer is ever squared. Equality never prunes.
    remaining = best[0] // best[1]
    for (left_min, left_max), (right_min, right_max) in zip(left, right):
        gap = max(left_min - right_max, right_min - left_max, 0)
        if gap > math.isqrt(remaining):
            return True
        remaining -= gap * gap
    return False


def _nearest(prepared, budget):
    best = None
    for left in prepared[0]:
        for right in prepared[1]:
            budget.checkpoint('surface_proximity_pair')
            budget.counts['triangle_pairs'] += 1
            if best is not None:
                budget.counts['aabb_bound_tests'] += 1
                if _aabb_exceeds_best(left[4], right[4], best):
                    budget.counts['aabb_pruned_pairs'] += 1
                    continue
            budget.tick('intersection_tests')
            if left[2] and right[2]:
                contact = _intersection(left[0], right[0], left[1], right[1], budget)
                if contact:
                    return 0, 1, ('contact', contact[0])
            elif left[2] or right[2]:
                contact = (_segment_face_contact(right, left) if left[2]
                           else _segment_face_contact(left, right))
                if contact:
                    return 0, 1, contact
            elif len(left[0]) == len(right[0]) == 1:
                delta = _sub(right[0][0], left[0][0])
                distance = _closer(_dot(delta, delta), 1, best)
                if distance:
                    best = (*distance, ('points', left[0][0], right[0][0]))
            for point in left[0]:
                if right[2]:
                    best = _point_faces(point, right, False, best, budget)
                for edge in right[3]:
                    best = _point_edges(point, edge, False, best, budget)
            for point in right[0]:
                if left[2]:
                    best = _point_faces(point, left, True, best, budget)
                for edge in left[3]:
                    best = _point_edges(point, edge, True, best, budget)
            for edge_a in left[3]:
                for edge_b in right[3]:
                    best = _edge_edges(edge_a, edge_b, best, budget)
            if best[0] == 0:
                return best
    return best


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


def _publish_points(points, origin, factor, distance):
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
    return [list(point) for point in rounded]


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


def measure_surface_proximity(left, right, checkpoint, *, diagnostics=None, retain_exact_rank=False,
                              _prepared_pair=None):
    """Measure only the requested triangle surfaces, retaining known quantities."""
    checkpoint('surface_proximity_admission')
    budget = _Work(checkpoint, diagnostics)
    result = dict(measurement_valid=False, distance_m=None, point_a_world=None,
        point_b_world=None, direction_a_to_b=None, witness_status='unknown',
        direction_status='unknown', topology=None, method=METHOD,
        work=budget.counts)
    try:
        if _prepared_pair is None:
            records, result['topology'] = _admit((left, right), budget)
            origin, factor, prepared = _integer_frame(records, budget)
        else:
            records, result['topology'], origin, factor, prepared = _prepared_pair
            budget.counts['shared_preparation'] = True
        numerator, denominator, descriptor = _nearest(prepared, budget)
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
            if numerator > 0:
                delta = _sub(points[1], points[0])
                direction = [float(Decimal(value.numerator) / Decimal(value.denominator) / local_distance)
                             if isinstance(value, Fraction) else float(Decimal(value) / local_distance)
                             for value in delta]
                result.update(direction_a_to_b=direction, direction_status='measured')
            world = _publish_points(points, origin, factor, distance)
        except _DomainError:
            result['witness_reason'] = 'surface_witness_bit_budget'
            if result['direction_status'] == 'unknown':
                result['direction_reason'] = 'surface_witness_bit_budget'
            return result
    if world is None:
        result['witness_reason'] = 'original_surface_witness_precision_exceeded'
    else:
        result.update(point_a_world=world[0], point_b_world=world[1], witness_status='measured')
    checkpoint('surface_proximity_complete')
    return result
