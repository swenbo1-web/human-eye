"""Administrator-only rational box-shadow oracle, independent of candidate code.

This reads the frozen whole-scene geometry and derives inspection rectangles.
It does not import the draft generator or any candidate/product predicate.
Projected boxes are represented by supporting halfplanes. Their intersection
vertices with a target rectangle are obtained from boundary-line pairs.
"""

from fractions import Fraction as F
from functools import cmp_to_key
from itertools import combinations, product
import hashlib
import json
from math import gcd, lcm
from pathlib import Path


HERE = Path(__file__).resolve().parent
DRAFT = Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_002_cost_review/active_scan_design')
NAMES = ('SCENE_GEOMETRY_RATIONAL.json', 'TASK_SPEC.json', 'visibility_oracle.py', 'ORACLE.json', 'REVIEW.md')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2,
                      default=fraction_json) + '\n'


def fraction_json(value):
    if isinstance(value, F):
        return str(value)
    raise TypeError(type(value).__name__)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def rectangle(vertices, triangles):
    if len(vertices) != 4 or len(set(vertices)) != 4 or len(triangles) != 2:
        return None
    if any(len(set(triangle)) != 3 or any(type(index) is not int or index not in range(4) for index in triangle)
           for triangle in triangles):
        return None
    normals = [cross(sub(vertices[b], vertices[a]), sub(vertices[c], vertices[a])) for a, b, c in triangles]
    if not all(any(normal) for normal in normals) or any(cross(normals[0], normals[1])) or dot(*normals) <= 0:
        return None
    if any(dot(normals[0], sub(vertex, vertices[0])) for vertex in vertices):
        return None
    directed = [(triangle[index], triangle[(index + 1) % 3]) for triangle in triangles for index in range(3)]
    boundary = [(a, b) for a, b in directed if (b, a) not in directed]
    if len(boundary) != 4 or len({a for a, _ in boundary}) != 4 or len({b for _, b in boundary}) != 4:
        return None
    successors = dict(boundary)
    start = min(range(4), key=lambda index: vertices[index])
    cycle = [start]
    for _ in range(3):
        cycle.append(successors[cycle[-1]])
    if len(set(cycle)) != 4 or successors[cycle[-1]] != start:
        return None
    corners = [vertices[index] for index in cycle]
    edges = [sub(corners[(index + 1) % 4], corners[index]) for index in range(4)]
    if any(not any(edge) for edge in edges) or any(dot(edges[index], edges[(index + 1) % 4]) for index in range(4)):
        return None
    if edges[0] != tuple(-value for value in edges[2]) or edges[1] != tuple(-value for value in edges[3]):
        return None
    assert dot(cross(edges[0], edges[1]), normals[0]) > 0
    return {'corners': corners, 'front': normals[0]}


def box_from_mesh(vertices, triangles):
    assert len(vertices) == len(set(vertices)) == 8 and len(triangles) == 12, 'bounded_oracle_requires_closed_axis_boxes'
    bounds = tuple((min(vertex[axis] for vertex in vertices), max(vertex[axis] for vertex in vertices)) for axis in range(3))
    assert all(low < high for low, high in bounds)
    assert set(vertices) == set(product(*bounds)), 'axis_box_corner_set'
    faces = {}
    center = tuple((low + high) / 2 for low, high in bounds)
    for triangle in triangles:
        points = [vertices[index] for index in triangle]
        sides = [(axis, side) for axis in range(3) for side in (0, 1)
                 if all(point[axis] == bounds[axis][side] for point in points)]
        assert len(sides) == 1, 'box_boundary_triangle'
        faces.setdefault(sides[0], []).append(triangle)
        normal = cross(sub(points[1], points[0]), sub(points[2], points[0]))
        assert dot(normal, sub(points[0], center)) > 0, 'outward_box_winding'
    assert len(faces) == 6
    for triangles_on_face in faces.values():
        assert len(triangles_on_face) == 2
        indexes = sorted(set(index for triangle in triangles_on_face for index in triangle))
        remap = {old: new for new, old in enumerate(indexes)}
        assert rectangle([vertices[index] for index in indexes],
                         [tuple(remap[index] for index in triangle) for triangle in triangles_on_face]) is not None
    return bounds


def canonical_line(a, b, c):
    denominator = lcm(a.denominator, b.denominator, c.denominator)
    integers = [int(value * denominator) for value in (a, b, c)]
    divisor = gcd(gcd(abs(integers[0]), abs(integers[1])), abs(integers[2]))
    return tuple(value // divisor for value in integers)


def projected_box_constraints(bounds, direction, plane_z):
    dx, dy, dz = direction
    assert dz > 0 and bounds[2][0] > plane_z, 'box_must_be_strictly_front_of_horizontal_ROI'
    points = set((x - (z - plane_z) * dx / dz, y - (z - plane_z) * dy / dz) for x, y, z in product(*bounds))
    planes = set()
    for first, second in combinations(points, 2):
        a, b = second[1] - first[1], first[0] - second[0]
        c = a * first[0] + b * first[1]
        values = [a * point[0] + b * point[1] - c for point in points]
        if all(value <= 0 for value in values):
            planes.add(canonical_line(a, b, c))
        elif all(value >= 0 for value in values):
            planes.add(canonical_line(-a, -b, -c))
    assert len(planes) >= 3
    return [tuple(map(F, plane)) for plane in planes]


def intersection_area(rect, box, direction, plane_z):
    constraints = projected_box_constraints(box, direction, plane_z)
    constraints += [(F(1), F(0), rect[0][1]), (F(-1), F(0), -rect[0][0]),
                    (F(0), F(1), rect[1][1]), (F(0), F(-1), -rect[1][0])]
    vertices = set()
    for (a, b, c), (u, v, w) in combinations(constraints, 2):
        determinant = a * v - u * b
        if determinant == 0:
            continue
        point = ((c * v - w * b) / determinant, (a * w - u * c) / determinant)
        if all(x * point[0] + y * point[1] <= bound for x, y, bound in constraints):
            vertices.add(point)
    if len(vertices) < 3:
        return F(0)
    center = tuple(sum(point[axis] for point in vertices) / len(vertices) for axis in (0, 1))

    def ordering(first, second):
        ax, ay = sub(first, center)
        bx, by = sub(second, center)
        first_half = ay < 0 or (ay == 0 and ax < 0)
        second_half = by < 0 or (by == 0 and bx < 0)
        if first_half != second_half:
            return 1 if first_half else -1
        determinant = ax * by - ay * bx
        if determinant:
            return -1 if determinant > 0 else 1
        return (ax * ax + ay * ay > bx * bx + by * by) - (ax * ax + ay * ay < bx * bx + by * by)

    boundary = sorted(vertices, key=cmp_to_key(ordering))
    return abs(sum(first[0] * second[1] - first[1] * second[0]
                   for first, second in zip(boundary, boundary[1:] + boundary[:1]))) / 2


def main():
    originals = HERE / 'original'
    originals.mkdir(exist_ok=True)
    inputs = {}
    for name in NAMES:
        source, destination = DRAFT / name, originals / name
        inputs[str(source.resolve())] = sha(source)
        if destination.exists():
            assert destination.read_bytes() == source.read_bytes(), 'original_copy_changed'
        else:
            destination.write_bytes(source.read_bytes())
    scene = json.loads((originals / 'SCENE_GEOMETRY_RATIONAL.json').read_bytes())
    task = json.loads((originals / 'TASK_SPEC.json').read_bytes())
    draft = json.loads((originals / 'ORACLE.json').read_bytes())
    directions = {name: tuple(map(F, direction)) for name, direction in task['directions'].items()}
    assert tuple(directions) == ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')
    targets, boxes = [], []
    for mesh in scene['objects']:
        vertices = [tuple(map(F, vertex)) for vertex in mesh['vertices']]
        triangles = mesh['triangles']
        panel = rectangle(vertices, triangles)
        if panel is None:
            boxes.append({'object_id': mesh['name'], 'bounds': box_from_mesh(vertices, triangles)})
            continue
        assert len({vertex[2] for vertex in vertices}) == 1, 'bounded_oracle_uses_horizontal_ROIs'
        bounds = tuple((min(vertex[axis] for vertex in vertices), max(vertex[axis] for vertex in vertices)) for axis in (0, 1))
        plane_z = vertices[0][2]
        assert set(vertices) == {(x, y, plane_z) for x, y in product(*bounds)}
        targets.append({'object_id': mesh['name'], 'rect_xy': bounds, 'plane_z': plane_z,
                        'front_normal_from_winding': panel['front']})
    assert len({mesh['name'] for mesh in scene['objects']}) == len(scene['objects'])
    for first, second in combinations(targets, 2):
        overlap = max(F(0), min(first['rect_xy'][0][1], second['rect_xy'][0][1]) - max(first['rect_xy'][0][0], second['rect_xy'][0][0]))
        overlap *= max(F(0), min(first['rect_xy'][1][1], second['rect_xy'][1][1]) - max(first['rect_xy'][1][0], second['rect_xy'][1][0]))
        assert first['plane_z'] == second['plane_z'] and overlap == 0, 'coplanar_ROIs_are_disjoint'
    visibility, matrix = {}, []
    for view, direction in directions.items():
        visibility[view] = []
        for target in targets:
            front = dot(target['front_normal_from_winding'], direction) > 0
            blockers = []
            if front:
                for box in boxes:
                    overlap = intersection_area(target['rect_xy'], box['bounds'], direction, target['plane_z'])
                    if overlap > 0:
                        blockers.append({'occluder': box['object_id'], 'overlap_area_m2': str(overlap)})
            full = front and not blockers
            if full:
                visibility[view].append(target['object_id'])
            matrix.append({'direction': view, 'target': target['object_id'], 'front_facing': front,
                           'full_interior_visible': full, 'positive_area_blockers': blockers})
    coverable = set().union(*(set(values) for values in visibility.values()))
    minimum_subsets = []
    for size in range(len(directions) + 1):
        minimum_subsets = [list(views) for views in combinations(directions, size)
                           if set().union(*(set(visibility[name]) for name in views)) == coverable]
        if minimum_subsets:
            break
    expected_rows = {(row['direction'], row['target']): row for row in draft['proofs']}
    mismatches = []
    for row in matrix:
        expected = expected_rows[(row['direction'], row['target'])]
        actual_areas = {item['occluder']: F(item['overlap_area_m2']) for item in row['positive_area_blockers']}
        expected_areas = {item['occluder']: F(item['overlap_area_m2']) for item in expected['positive_area_blockers']}
        if row['full_interior_visible'] != expected['full_interior_visible'] or actual_areas != expected_areas:
            mismatches.append({'actual': row, 'draft': expected})
    checks = {
        'objects': len(scene['objects']) == draft['objects'] == 28,
        'triangles': sum(len(mesh['triangles']) for mesh in scene['objects']) == draft['triangles'] == 276,
        'independent_discovery': {row['object_id'] for row in targets} == set(draft['discovered_targets']),
        '36_matrix_rows': len(matrix) == len(expected_rows) == 36,
        'all_visibility_and_exact_blocker_areas_match': not mismatches,
        'five_coverable_one_finite_pool_uncovered': len(coverable) == 5 and len(targets) - len(coverable) == 1,
        'minimum_subsets_match': minimum_subsets == draft['optimal_direction_subsets'],
        'minimum_count_match': len(minimum_subsets[0]) == draft['minimum_direction_count_for_coverable'],
    }
    control_rect = ((F(-1), F(1)), (F(-1), F(1)))
    control_box = ((F(9, 10), F(11, 10)), (F(9, 10), F(11, 10)), (F(1), F(11, 10)))
    tangent_box = ((F(1), F(2)), (F(0), F(1, 2)), (F(1), F(11, 10)))
    control_area = intersection_area(control_rect, control_box, (F(0), F(0), F(1)), F(0))
    tangent_area = intersection_area(control_rect, tangent_box, (F(0), F(0), F(1)), F(0))
    center_ray_inside_box = all(low <= 0 <= high for low, high in control_box[:2])
    checks['center_clear_corner_occluded_control'] = not center_ray_inside_box and control_area == F(1, 100)
    checks['boundary_only_touch_has_zero_area'] = tangent_area == 0
    quantization_mismatches = []
    for row in matrix:
        target = next(item for item in targets if item['object_id'] == row['target'])
        quantized_rect = tuple(tuple(F.from_float(float(value)) for value in pair) for pair in target['rect_xy'])
        quantized_z = F.from_float(float(target['plane_z']))
        quantized_blocked = any(intersection_area(quantized_rect,
            tuple(tuple(F.from_float(float(value)) for value in pair) for pair in box['bounds']),
            directions[row['direction']], quantized_z) > 0 for box in boxes)
        quantized_full = row['front_facing'] and not quantized_blocked
        if quantized_full != row['full_interior_visible']:
            quantization_mismatches.append({'direction': row['direction'], 'target': row['target'],
                                           'rational': row['full_interior_visible'], 'binary64_rationalized': quantized_full})
    checks['binary64_geometry_quantization_preserves_36_visibility_results'] = not quantization_mismatches
    answer = {'administrator_only': True, 'schema': 'independent-rational-halfplane-oracle-v1',
              'targets': targets, 'opaque_boxes': boxes, 'matrix': matrix, 'visibility_by_direction': visibility,
              'coverable_targets': sorted(coverable), 'uncovered_in_finite_pool': sorted({row['object_id'] for row in targets} - coverable),
              'minimum_direction_subsets': minimum_subsets, 'minimum_direction_count': len(minimum_subsets[0]),
              'checks': checks, 'mismatches': mismatches, 'inputs_sha256': inputs,
              'binary64_quantization_mismatches': quantization_mismatches,
              'algorithm': 'Exact projected-box supporting halfplanes, pairwise boundary intersections, rational polygon area. No candidate/draft predicate imports.',
              'scope': 'Fixed horizontal rectangles and validated closed axis boxes. Other target surfaces are coplanar and disjoint. Camera frustum/pixel checks are separate.',
              'controls': {'corner_positive_area': str(control_area), 'boundary_touch_area': str(tangent_area)},
              'new_model_Blender_product_API_runs': 0, 'source_sha256': sha(Path(__file__))}
    (HERE / 'ADMIN_ORACLE.json').write_text(encode(answer), encoding='utf8', newline='\n')
    public = {'passed': all(checks.values()), 'matrix_rows_checked': len(matrix),
              'independently_discovered_count': len(targets), 'coverable_count': len(coverable),
              'finite_pool_uncovered_count': len(targets) - len(coverable), 'draft_mismatches': len(mismatches),
              'binary64_quantization_mismatch_count': len(quantization_mismatches),
              'controls_passed': checks['center_clear_corner_occluded_control'] and checks['boundary_only_touch_has_zero_area'],
              'private_oracle_sha256': sha(HERE / 'ADMIN_ORACLE.json'),
              'source_sha256': sha(Path(__file__)), 'new_model_Blender_product_API_runs': 0,
              'privacy': 'Summary omits target IDs, visibility matrix and best subset. Administrator answer files must not enter the candidate runner.'}
    (HERE / 'PUBLIC_SUMMARY.json').write_text(encode(public), encoding='utf8', newline='\n')
    print(encode(public), end='')


if __name__ == '__main__':
    main()
