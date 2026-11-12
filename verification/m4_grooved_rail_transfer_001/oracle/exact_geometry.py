"""Independent standard-library rational geometry, without product imports."""

from collections import Counter, defaultdict
from decimal import Decimal, localcontext
from fractions import Fraction as F
from itertools import combinations
import math


EDGES = ((0, 1), (1, 2), (2, 0))


def dot(a, b):
    return sum((x * y for x, y in zip(a, b, strict=True)), F(0))


def add(a, b):
    return tuple(x + y for x, y in zip(a, b, strict=True))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b, strict=True))


def scale(a, t):
    return tuple(x * t for x in a)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def squared(a, b):
    delta = sub(a, b)
    return dot(delta, delta)


def blend(points, bary):
    return tuple(sum((weight * point[j] for weight, point in zip(bary, points, strict=True)), F(0))
                 for j in range(3))


def barycentric(point, tri):
    a, b, c = tri
    u, v, w = sub(b, a), sub(c, a), sub(point, a)
    uu, uv, vv = dot(u, u), dot(u, v), dot(v, v)
    den = uu * vv - uv * uv
    if not den:
        raise ValueError("degenerate_triangle")
    s = (dot(w, u) * vv - dot(w, v) * uv) / den
    t = (dot(w, v) * uu - dot(w, u) * uv) / den
    return (1 - s - t, s, t)


def bary_vertex(index):
    return tuple(F(i == index) for i in range(3))


def bary_edge(edge, t):
    result = [F(0), F(0), F(0)]
    result[edge[0]], result[edge[1]] = 1 - t, t
    return tuple(result)


def segment_triangle(p, q, tri):
    """Return all endpoints of the intersection, including coplanar overlap."""
    normal = cross(sub(tri[1], tri[0]), sub(tri[2], tri[0]))
    hp, hq = dot(normal, sub(p, tri[0])), dot(normal, sub(q, tri[0]))
    if hp == 0 and hq == 0:
        # Barycentric coordinates are affine along a coplanar segment.
        # Clip [0,1] against the three nonnegative barycentric halfspaces.
        bp, bq = barycentric(p, tri), barycentric(q, tri)
        lo, hi = F(0), F(1)
        for left, right in zip(bp, bq, strict=True):
            slope = right - left
            if slope == 0:
                if left < 0:
                    return []
            elif slope > 0:
                lo = max(lo, -left / slope)
            else:
                hi = min(hi, -left / slope)
        if lo > hi:
            return []
        return sorted({add(p, scale(sub(q, p), t)) for t in (lo, hi)})
    if hp == hq or hp * hq > 0:
        return []
    t = hp / (hp - hq)
    if not 0 <= t <= 1:
        return []
    point = add(p, scale(sub(q, p), t))
    return [point] if min(barycentric(point, tri)) >= 0 else []


def triangle_intersection(left, right):
    points = set()
    for i, j in EDGES:
        points.update(segment_triangle(left[i], left[j], right))
        points.update(segment_triangle(right[i], right[j], left))
    return sorted(points)


def on_segment(point, p, q):
    delta, offset = sub(q, p), sub(point, p)
    return cross(delta, offset) == (0, 0, 0) and 0 <= dot(offset, delta) <= dot(delta, delta)


def triangle_distance(left, right, intersections):
    """Exhaust face projections, point-edge/endpoints and edge interiors."""
    candidates = []
    counts = Counter()

    def offer(kind, pa, pb, ba, bb, parameters=None):
        counts[kind] += 1
        assert sum(ba) == sum(bb) == 1 and min(ba) >= 0 and min(bb) >= 0
        assert blend(left, ba) == pa and blend(right, bb) == pb
        candidates.append({
            "kind": kind, "squared_distance_m2": squared(pa, pb),
            "point_target": pa, "point_candidate": pb,
            "barycentric_target": ba, "barycentric_candidate": bb,
            "parameters": parameters,
        })

    for point in intersections:
        offer("intersection", point, point, barycentric(point, left), barycentric(point, right))
    for i, pa in enumerate(left):
        for j, pb in enumerate(right):
            offer("vertex_vertex", pa, pb, bary_vertex(i), bary_vertex(j))
    for i in range(3):
        pa, pb = left[i], right[i]
        bb = barycentric(pa, right)
        counts["vertex_face_projection_tests"] += 1
        if min(bb) >= 0:
            offer("target_vertex_candidate_face", pa, blend(right, bb), bary_vertex(i), bb)
        ba = barycentric(pb, left)
        counts["vertex_face_projection_tests"] += 1
        if min(ba) >= 0:
            offer("candidate_vertex_target_face", blend(left, ba), pb, ba, bary_vertex(i))
        for edge in EDGES:
            delta = sub(right[edge[1]], right[edge[0]])
            t = max(F(0), min(F(1), dot(sub(pa, right[edge[0]]), delta) / dot(delta, delta)))
            bb = bary_edge(edge, t)
            offer("target_vertex_candidate_edge", pa, blend(right, bb), bary_vertex(i), bb,
                  {"candidate_edge_local_indices": edge, "candidate_parameter": t})
            delta = sub(left[edge[1]], left[edge[0]])
            s = max(F(0), min(F(1), dot(sub(pb, left[edge[0]]), delta) / dot(delta, delta)))
            ba = bary_edge(edge, s)
            offer("candidate_vertex_target_edge", blend(left, ba), pb, ba, bary_vertex(i),
                  {"target_edge_local_indices": edge, "target_parameter": s})
    for ea in EDGES:
        for eb in EDGES:
            counts["edge_edge_stationary_tests"] += 1
            u, v = sub(left[ea[1]], left[ea[0]]), sub(right[eb[1]], right[eb[0]])
            r = sub(left[ea[0]], right[eb[0]])
            a, b, c, d, e = dot(u, u), dot(u, v), dot(v, v), dot(u, r), dot(v, r)
            den = a * c - b * b
            if den == 0:
                counts["parallel_edge_pairs"] += 1
                continue
            s, t = (b * e - c * d) / den, (a * e - b * d) / den
            if 0 < s < 1 and 0 < t < 1:
                ba, bb = bary_edge(ea, s), bary_edge(eb, t)
                offer("nonparallel_edge_interiors", blend(left, ba), blend(right, bb), ba, bb,
                      {"target_edge_local_indices": ea, "candidate_edge_local_indices": eb,
                       "target_parameter": s, "candidate_parameter": t, "gram_determinant": den})
    best = min(c["squared_distance_m2"] for c in candidates)
    return {"squared_distance_m2": best,
            "minimum_candidates": [c for c in candidates if c["squared_distance_m2"] == best],
            "candidate_counts": dict(counts), "total_feasible_candidates": len(candidates)}


def root_interval(value, digits=70):
    """Construct Decimal endpoints and certify both squares as Fractions."""
    if value < 0:
        raise ValueError("negative_squared_distance")
    unit = 10 ** digits
    lo_int = math.isqrt(value.numerator * unit * unit // value.denominator)
    lo, hi = F(lo_int, unit), F(lo_int + 1, unit)
    if lo * lo == value:
        hi = lo
    with localcontext() as context:
        context.prec = digits + 40
        lo_decimal = Decimal(lo.numerator) / Decimal(lo.denominator)
        hi_decimal = Decimal(hi.numerator) / Decimal(hi.denominator)
        assert F(lo_decimal) == lo and F(hi_decimal) == hi
        assert F(lo_decimal) ** 2 <= value <= F(hi_decimal) ** 2
        return {
            "lower_decimal_m": format(lo_decimal, "f"),
            "upper_decimal_m": format(hi_decimal, "f"),
            "lower_exact_m": lo, "upper_exact_m": hi,
            "decimal_endpoints_reparsed_as_fraction_and_squared": True,
            "display_mm": format((lo_decimal + hi_decimal) * 500, ".15f"),
        }


def audit_body(name, vertices, faces):
    edge_uses = defaultdict(list)
    degenerates = []
    for index, face in enumerate(faces):
        tri = [vertices[v] for v in face]
        normal = cross(sub(tri[1], tri[0]), sub(tri[2], tri[0]))
        if dot(normal, normal) == 0:
            degenerates.append(index)
        for i, j in EDGES:
            edge_uses[tuple(sorted((face[i], face[j])))].append((index, face[i], face[j]))
    bad_edges = [{"edge": edge, "uses": uses} for edge, uses in sorted(edge_uses.items())
                 if len(uses) != 2 or uses[0][1:] != tuple(reversed(uses[1][1:]))]
    adjacency = defaultdict(set)
    for uses in edge_uses.values():
        for x, y in combinations(uses, 2):
            adjacency[x[0]].add(y[0])
            adjacency[y[0]].add(x[0])
    reached, frontier = set(), [0]
    while frontier:
        face = frontier.pop()
        if face not in reached:
            reached.add(face)
            frontier.extend(adjacency[face] - reached)
    self_pairs, invalid_contacts = [], []
    if not degenerates:
        for i, j in combinations(range(len(faces)), 2):
            left, right = [vertices[k] for k in faces[i]], [vertices[k] for k in faces[j]]
            contact = triangle_intersection(left, right)
            shared = sorted(set(faces[i]) & set(faces[j]))
            if len(shared) == 1:
                legal = all(p == vertices[shared[0]] for p in contact)
            elif len(shared) == 2:
                legal = all(on_segment(p, vertices[shared[0]], vertices[shared[1]]) for p in contact)
            else:
                legal = not contact
            entry = {"triangle_ids": [i, j], "shared_vertex_ids": shared,
                     "intersection_endpoints": contact, "legal_contact": legal}
            self_pairs.append(entry)
            if not legal:
                invalid_contacts.append(entry)
    volume = sum((dot(vertices[a], cross(vertices[b], vertices[c])) for a, b, c in faces), F(0)) / 6
    complete_vertices = set(range(len(vertices))) == {v for face in faces for v in face}
    passed = (not degenerates and not bad_edges and len(reached) == len(faces)
              and not invalid_contacts and complete_vertices and volume > 0)
    return {
        "name": name, "passed": passed, "vertices": len(vertices), "triangles": len(faces),
        "edges": len(edge_uses), "euler_characteristic": len(vertices) - len(edge_uses) + len(faces),
        "all_vertices_referenced": complete_vertices, "connected_faces": len(reached),
        "degenerate_triangle_ids": degenerates, "bad_oriented_edge_incidence": bad_edges,
        "signed_volume_m3": volume, "self_triangle_pairs_checked": len(self_pairs),
        "self_pair_certificates": self_pairs, "illegal_self_intersections": invalid_contacts,
    }


def point_in_solid(point, vertices, faces):
    triangles = [[vertices[v] for v in face] for face in faces]
    for index, tri in enumerate(triangles):
        n = cross(sub(tri[1], tri[0]), sub(tri[2], tri[0]))
        if dot(n, sub(point, tri[0])) == 0 and min(barycentric(point, tri)) >= 0:
            return {"status": "boundary", "triangle_id": index}
    rejected = []
    for k in range(1, 257):
        direction = (F(1), F(k), F(k * k + k + 1))
        hits, degenerate = [], None
        for index, tri in enumerate(triangles):
            n = cross(sub(tri[1], tri[0]), sub(tri[2], tri[0]))
            den, num = dot(n, direction), dot(n, sub(tri[0], point))
            if den == 0:
                if num == 0:
                    degenerate = {"triangle_id": index, "reason": "coplanar_ray"}
                    break
                continue
            t = num / den
            if t <= 0:
                continue
            intersection = add(point, scale(direction, t))
            bary = barycentric(intersection, tri)
            if min(bary) < 0:
                continue
            if min(bary) == 0:
                degenerate = {"triangle_id": index, "reason": "edge_or_vertex_ray", "t": t}
                break
            hits.append({"triangle_id": index, "parameter": t, "barycentric": bary, "point": intersection})
        if degenerate is not None:
            rejected.append({"direction": direction, "cause": degenerate})
            continue
        if len({h["parameter"] for h in hits}) != len(hits):
            raise ValueError("duplicate_strict_ray_hits")
        return {
            "status": "inside" if len(hits) % 2 else "outside", "direction": direction,
            "hits": sorted(hits, key=lambda h: h["parameter"]), "intersection_count": len(hits),
            "rejected_directions": rejected,
        }
    raise ValueError("rational_ray_direction_exhausted")


def hull_planes(vertices):
    planes = {}
    for ids in combinations(range(len(vertices)), 3):
        a, b, c = [vertices[i] for i in ids]
        normal = cross(sub(b, a), sub(c, a))
        if normal == (0, 0, 0):
            continue
        values = [dot(normal, sub(v, a)) for v in vertices]
        if (max(values) > 0 and min(values) < 0) or min(values) == max(values) == 0:
            continue
        if min(values) >= 0:
            normal = scale(normal, -1)
        coefficients = normal + (-dot(normal, a),)
        denominator = math.lcm(*(q.denominator for q in coefficients))
        integer = [int(q * denominator) for q in coefficients]
        divisor = math.gcd(*integer)
        key = tuple(q // divisor for q in integer)
        entry = planes.setdefault(key, {
            "outward_plane_integer": key, "supporting_triplets": [],
            "coplanar_vertex_ids": [i for i, v in enumerate(vertices) if dot(key[:3], v) + key[3] == 0],
        })
        entry["supporting_triplets"].append(ids)
    if len(planes) < 4:
        raise ValueError("hull_not_three_dimensional")
    return list(planes.values())


def polygon_membership(point, polygon):
    hits = 0
    for a, b in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        area = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
        if (area == 0 and min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
                and min(a[1], b[1]) <= point[1] <= max(a[1], b[1])):
            return "boundary"
        if (a[1] > point[1]) != (b[1] > point[1]):
            x = a[0] + (point[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            hits += x > point[0]
    return "inside" if hits % 2 else "outside"
