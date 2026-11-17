"""Exact projected triangle intersection proof for an entire rectangle witness."""

from fractions import Fraction as F


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def clip(polygon, distances):
    output = []
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        da, db = distances[index], distances[(index + 1) % len(polygon)]
        if da >= 0:
            output.append(a)
        if (da < 0 < db) or (db < 0 < da):
            ratio = da / (da - db)
            output.append(tuple(x + ratio * (y - x) for x, y in zip(a, b)))
    return output


def area2(polygon):
    if not polygon:
        return F(0)
    return abs(sum(a[0] * b[1] - a[1] * b[0]
                   for a, b in zip(polygon, polygon[1:] + polygon[:1])))


def prove(objects, region, direction):
    target = next(obj for obj in objects if obj['name'] == region['object_name'])
    indices = region['boundary_loops'][0]
    a, b, _, e = [target['vertices'][index] for index in indices]
    u, v = sub(b, a), sub(e, a)
    normal = tuple(F(value) for value in region['plane_normal_integer'])
    denominator = dot(normal, direction)
    if denominator <= 0:
        raise ValueError('witness_view_not_oriented_front')
    uu, vv = dot(u, u), dot(v, v)
    proofs = []
    for obj in objects:
        for index, face in enumerate(obj['triangles']):
            if obj['name'] == target['name'] and index in region['source_triangle_indices']:
                continue
            points = [obj['vertices'][vertex] for vertex in face]
            times = [dot(normal, sub(point, a)) / denominator for point in points]
            if max(times) <= 0:
                proofs.append(dict(object_name=obj['name'], triangle=index, reason='no_positive_front_depth'))
                continue
            positive = clip(points, times)
            projected = []
            for point in positive:
                time = dot(normal, sub(point, a)) / denominator
                plane_point = tuple(x - time * d for x, d in zip(point, direction))
                relative = sub(plane_point, a)
                projected.append((dot(relative, u) / uu, dot(relative, v) / vv))
            for axis, bound, sign in ((0, F(0), 1), (0, F(1), -1), (1, F(0), 1), (1, F(1), -1)):
                if projected:
                    projected = clip(projected, [sign * (point[axis] - bound) for point in projected])
            overlap = area2(projected)
            if overlap:
                raise ValueError('positive_area_front_occluder/' + obj['name'] + '/' + str(index))
            proofs.append(dict(object_name=obj['name'], triangle=index, reason='zero_area_positive_front_projection'))
    return dict(whole_rectangle_geometrically_complete=True, front_dot_product=str(denominator),
                world_direction=list(direction), occluder_triangles_checked=len(proofs),
                method='Fraction front halfspace clipping, directional projection to target plane, rectangle intersection area',
                proofs=proofs)
