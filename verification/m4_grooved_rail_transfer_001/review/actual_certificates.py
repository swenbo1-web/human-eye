"""Independent actual-coordinate support and oriented-chain certificates."""

from collections import Counter
from fractions import Fraction as F
from itertools import combinations
from math import isqrt
import hashlib
import json
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
CAP = [(0, 1, 3), (1, 2, 3), (0, 3, 4), (0, 4, 6), (4, 5, 6)]


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def mul(a, scale):
    return tuple(value * scale for value in a)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def exact(values):
    return tuple(F(value) for value in values)


def serial(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [serial(item) for item in value]
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    return value


def sqrt_interval(square, places=30):
    scale = 10 ** places
    lower_integer = isqrt(square.numerator * scale * scale // square.denominator)
    lower = F(lower_integer, scale)
    upper = lower if lower * lower == square else F(lower_integer + 1, scale)
    assert lower * lower <= square <= upper * upper
    return {'lower_m': lower, 'upper_m': upper, 'squares_verified': True}


def signed_chain(faces):
    result = Counter()
    for face in faces:
        inversions = sum(face[i] > face[j] for i in range(3) for j in range(i + 1, 3))
        result[tuple(sorted(face))] += -1 if inversions % 2 else 1
    return {key: value for key, value in result.items() if value}


def target_faces():
    faces = list(CAP) + [tuple(value + 7 for value in reversed(face)) for face in CAP]
    for left in range(7):
        right = (left + 1) % 7
        faces += [(left, left + 7, right + 7), (left, right + 7, right)]
    return faces


def prism_chain(cap):
    faces = [cap, tuple(value + 7 for value in reversed(cap))]
    exterior = {frozenset((i, (i + 1) % 7)): (i, (i + 1) % 7) for i in range(7)}
    for left, right in zip(cap, cap[1:] + cap[:1]):
        first, second = exterior.get(frozenset((left, right)), tuple(sorted((left, right))))
        side = [(first, first + 7, second + 7), (first, second + 7, second)]
        faces += side if (left, right) == (first, second) else [tuple(reversed(face)) for face in side]
    return faces


def projection(point, triangle):
    origin, second, third = triangle
    edge1, edge2 = sub(second, origin), sub(third, origin)
    normal = cross(edge1, edge2)
    normal_square = dot(normal, normal)
    assert normal_square > 0
    foot = sub(point, mul(normal, dot(sub(point, origin), normal) / normal_square))
    offset = sub(foot, origin)
    aa, ab, bb = dot(edge1, edge1), dot(edge1, edge2), dot(edge2, edge2)
    denominator = aa * bb - ab * ab
    u = (dot(offset, edge1) * bb - dot(offset, edge2) * ab) / denominator
    v = (dot(offset, edge2) * aa - dot(offset, edge1) * ab) / denominator
    return {'target_point': foot, 'part_point': point, 'barycentric': (1 - u - v, u, v),
            'distance_square_m2': dot(sub(point, foot), sub(point, foot))}


def support_bound(first, second, directions):
    best = None
    for direction in directions:
        square = dot(direction, direction)
        if square == 0:
            continue
        for normal in (direction, mul(direction, -1)):
            gap = min(dot(point, normal) for point in second) - max(dot(point, normal) for point in first)
            if gap > 0:
                bound = gap * gap / square
                if best is None or bound > best['distance_square_lower_bound_m2']:
                    best = {'direction': normal, 'projected_gap': gap,
                            'distance_square_lower_bound_m2': bound}
    assert best is not None
    return best


def normals(points):
    return [cross(sub(b, a), sub(c, a)) for a, b, c in combinations(points, 3)]


def point_inside_hull(point, vertices):
    tested = 0
    for a, b, c in combinations(vertices, 3):
        normal = cross(sub(b, a), sub(c, a))
        if dot(normal, normal) == 0:
            continue
        signs = [dot(sub(vertex, a), normal) for vertex in vertices]
        if all(sign <= 0 for sign in signs):
            tested += 1
            if dot(sub(point, a), normal) >= 0:
                return False, tested
        elif all(sign >= 0 for sign in signs):
            tested += 1
            if dot(sub(point, a), normal) <= 0:
                return False, tested
    return tested > 0, tested


def closest_edges(a, b, c, d):
    first, second, offset = sub(b, a), sub(d, c), sub(a, c)
    aa, ab, bb = dot(first, first), dot(first, second), dot(second, second)
    denominator = aa * bb - ab * ab
    assert denominator > 0
    s = (ab * dot(second, offset) - bb * dot(first, offset)) / denominator
    t = (aa * dot(second, offset) - ab * dot(first, offset)) / denominator
    left, right = add(a, mul(first, s)), add(c, mul(second, t))
    return {'target_point': left, 'part_point': right, 'target_parameter': s, 'part_parameter': t,
            'nonparallel_denominator': denominator, 'distance_square_m2': dot(sub(right, left), sub(right, left))}


def frozen_local():
    contour = [(F(x), F(z)) for x, z in [('0', '0'), ('40', '0'), ('22.4', '13.2'),
        ('14', '2'), ('1.2', '11.6'), ('9.6', '22.8'), ('0', '30')]]
    target = [(x, F(y), z) for y in (-20, 20) for x, z in contour]
    a = [((4 * F(s) + 3 * F(h)) / 5, F(y), (-3 * F(s) + 4 * F(h)) / 5)
         for s, y, h in [('2', '2', '15.25'), ('0', '-2', '20.25'), ('4', '-2', '20.25'), ('2', '8', '20.25')]]
    normal, tangent = exact((F(-3, 5), 0, F(-4, 5))), exact((F(4, 5), 0, F(-3, 5)))
    q = add(exact((0, 5, 0)), mul(normal, F('2.75')))
    b = [add(q, mul(tangent, sign * 6)) for sign in (1, -1)]
    b += [add(add(q, mul(normal, 8)), exact((0, sign * 6, 0))) for sign in (1, -1)]
    c = [exact(point) for point in [(10, F('28.5'), 2), (16, F('36.5'), -2), (4, F('36.5'), -2), (10, F('36.5'), 10)]]
    return {'Target': target, 'Part_A': a, 'Part_B': b, 'Part_C': c}


def main():
    source = BATCH / 'asset/ACTUAL_SNAPSHOT.json'
    snapshot = json.loads(source.read_bytes())
    objects = {row['name']: row for row in snapshot['objects']}
    world = {name: [exact(point) for point in row['vertices_world']] for name, row in objects.items()}
    target = world['Target']
    checks = {'actual_counts': snapshot['counts'] == {'objects': 4, 'vertices': 26, 'triangles': 36},
              'unit_one': snapshot['unit_scale_m'] == snapshot['scale_length'] == 1,
              'fixed_target_face_order': objects['Target']['triangles'] == [list(face) for face in target_faces()]}
    local = frozen_local()
    f32 = lambda value: struct.unpack('f', struct.pack('f', float(value)))[0]
    checks['actual_local_matches_frozen_binary32'] = all(objects[name]['vertices_local']
        == [[f32(value) for value in point] for point in points] for name, points in local.items())
    checks['world_binary64_export_reproduced'] = all(row['vertices_world'] == [
        [((row['matrix_world'][i][0] * point[0] + row['matrix_world'][i][1] * point[1])
          + row['matrix_world'][i][2] * point[2]) + row['matrix_world'][i][3] for i in range(3)]
        for point in row['vertices_local']] for row in objects.values())
    checks['no_extra_transform_dependencies_or_labels'] = all(not row['parent'] and not row['modifiers']
        and not row['constraints'] and not row['animation_present'] and not row['shape_keys_present']
        and not row['object_custom_properties'] and not row['mesh_custom_properties'] and not row['material_names']
        for row in objects.values())
    chains = [prism_chain(cap) for cap in CAP]
    checks['actual_target_equals_five_oriented_chains'] = signed_chain([face for chain in chains for face in chain]) == signed_chain(objects['Target']['triangles'])
    a_candidates = [(index, projection(world['Part_A'][0], [target[i] for i in objects['Target']['triangles'][index]])) for index in (16, 17)]
    a_candidates = [(index, value) for index, value in a_candidates if all(weight > 0 for weight in value['barycentric'])]
    assert a_candidates
    a_index, a = min(a_candidates, key=lambda pair: pair[1]['distance_square_m2'])
    a['target_triangle'] = a_index
    a['part_vertex'] = 0
    direction = sub(a['part_point'], a['target_point'])
    prism_bounds = []
    for cap, chain in zip(CAP, chains):
        vertices = [target[i] for i in (*cap, *(index + 7 for index in cap))]
        bound = support_bound(vertices, world['Part_A'], normals(vertices) + normals(world['Part_A']) + [direction])
        prism_bounds.append({'cap': cap, 'oriented_faces': chain, **bound})
    a['distance_square_lower_bound_m2'] = min(row['distance_square_lower_bound_m2'] for row in prism_bounds)
    checks['A_actual_floor_triangle_interior'] = a_index == 16 and all(weight > 0 for weight in a['barycentric'])
    hull = [target[index] for index in (0, 1, 6, 7, 8, 13)]
    hull_membership = [point_inside_hull(point, hull) for point in world['Part_A']]
    checks['A_strictly_inside_actual_target_convex_hull'] = all(passed for passed, count in hull_membership)
    checks['A_outside_every_prism_hull'] = all(row['projected_gap'] > 0 for row in prism_bounds)
    b = closest_edges(target[0], target[7], world['Part_B'][0], world['Part_B'][1])
    b['target_edge'], b['part_edge'] = (0, 7), (0, 1)
    b_bound = support_bound(target, world['Part_B'], [sub(b['part_point'], b['target_point'])])
    b.update(b_bound)
    checks['B_nonparallel_internal_edges'] = 0 < b['target_parameter'] < 1 and 0 < b['part_parameter'] < 1
    checks['B_exact_global_support_equality'] = b['distance_square_lower_bound_m2'] == b['distance_square_m2']
    c_candidates = [(index, projection(world['Part_C'][0], [target[i] for i in objects['Target']['triangles'][index]])) for index in range(5, 10)]
    c_candidates = [(index, value) for index, value in c_candidates if all(weight > 0 for weight in value['barycentric'])]
    assert c_candidates
    c_index, c = min(c_candidates, key=lambda pair: pair[1]['distance_square_m2'])
    c['target_triangle'], c['part_vertex'] = c_index, 0
    c.update(support_bound(target, world['Part_C'], [sub(c['part_point'], c['target_point'])]))
    checks['C_actual_cap_material_interior'] = all(weight > 0 for weight in c['barycentric'])
    results = {'Part_A': a, 'Part_B': b, 'Part_C': c}
    for name, value in results.items():
        lower, upper = value['distance_square_lower_bound_m2'], value['distance_square_m2']
        nominal = {'Part_A': F('0.00525'), 'Part_B': F('0.00275'), 'Part_C': F('0.0085')}[name]
        checks[name + '_bounds_ordered'] = 0 < lower <= upper
        checks[name + '_nominal_consistent_with_scoring_precision'] = (nominal - F(1, 10**6))**2 <= lower <= upper <= (nominal + F(1, 10**6))**2
        value['distance_lower_interval'] = sqrt_interval(lower)
        value['distance_upper_interval'] = sqrt_interval(upper)
    checks['actual_four_mm_thresholds'] = a['distance_square_lower_bound_m2'] > F('0.004')**2 and b['distance_square_m2'] < F('0.004')**2 and c['distance_square_lower_bound_m2'] > F('0.004')**2
    checks['actual_unique_nearest_B'] = b['distance_square_m2'] < min(a['distance_square_lower_bound_m2'], c['distance_square_lower_bound_m2'])
    result = {'schema': 'grooved-rail-independent-actual-support-certificate-v1', 'passed': all(checks.values()),
        'checks': checks, 'snapshot_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'actual_features': results,
        'A_prism_bounds': prism_bounds, 'A_actual_hull_tests': hull_membership,
        'containment_certificate': 'Target equals the sum of five closed oriented prism chains with exact internal-face cancellation. Every chain is inside its six-vertex convex hull. The entire A tetrahedron is strictly separated from each hull, so winding additivity gives zero Target winding on A. A is strictly inside the actual outer hull. B/C have global material separation supports.',
        'scope': 'Independent support, convex-hull and oriented-chain check of actual geometry. Full triangle intersection, self-intersection and oracle qualification are reviewed separately.',
        'model_Blender_product_runs': 0}
    with (HERE / 'ACTUAL_CERTIFICATES.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(serial(result), stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(checks),
                      'failed': [name for name, passed in checks.items() if not passed]}))


if __name__ == '__main__':
    main()
