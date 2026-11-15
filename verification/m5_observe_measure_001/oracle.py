"""Independent rational geometry answers and published-witness membership.

Only frozen source geometry is read. No product distance kernel, live host,
renderer, model, installation or source editing is performed.
"""

from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
GEOMETRY = HERE.with_name('m4_target_acquisition_002') / 'reference/FROZEN_GEOMETRY.json'
GEOMETRY_SHA = 'decdcc1532f31ceb5c75203705ba5b533520f7a525fa8c6ea0391ba3a1fa36da'
PUBLICATION_TOLERANCE_M = F.from_float(1e-9)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def vector(value):
    if type(value) not in (list, tuple) or len(value) != 3 or any(type(item) is bool for item in value):
        raise ValueError('finite_three_coordinate_point_required')
    return tuple(F(item) for item in value)


def subtract(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def segment_distance_squared(point, a, b):
    edge = subtract(b, a)
    length_squared = dot(edge, edge)
    if length_squared == 0:
        delta = subtract(point, a)
        return dot(delta, delta)
    t = max(F(0), min(F(1), dot(subtract(point, a), edge)/length_squared))
    nearest = tuple(a[k]+t*edge[k] for k in range(3))
    delta = subtract(point, nearest)
    return dot(delta, delta)


def triangle_distance_squared(point, triangle):
    """Exact point/triangle distance by plane projection and edge segments."""
    a, b, c = triangle
    normal = cross(subtract(b, a), subtract(c, a))
    norm_squared = dot(normal, normal)
    if norm_squared:
        signed = dot(subtract(point, a), normal)
        projected = tuple(point[k]-normal[k]*signed/norm_squared for k in range(3))
        sides = [dot(cross(subtract(end, start), subtract(projected, start)), normal)
                 for start, end in ((a, b), (b, c), (c, a))]
        if all(value >= 0 for value in sides):
            return signed*signed/norm_squared
    return min(segment_distance_squared(point, start, end) for start, end in ((a, b), (b, c), (c, a)))


def membership(point, vertices, faces):
    point = vector(point)
    vertices = [vector(value) for value in vertices]
    distances = [triangle_distance_squared(point, tuple(vertices[index] for index in face)) for face in faces]
    tolerance_squared = PUBLICATION_TOLERANCE_M*PUBLICATION_TOLERANCE_M
    return {'exact_source_triangle_indices': [index for index, value in enumerate(distances) if value == 0],
            'within_publication_tolerance_source_triangle_indices': [index for index, value in enumerate(distances) if value <= tolerance_squared],
            'minimum_squared_distance_to_source': str(min(distances)),
            'publication_tolerance_m': str(PUBLICATION_TOLERANCE_M)}


def frozen_objects():
    if sha(GEOMETRY) != GEOMETRY_SHA:
        raise ValueError('frozen_main_geometry_changed')
    return {row['name']: row for row in json.loads(GEOMETRY.read_bytes())['objects']}


def main_answer():
    objects = frozen_objects()
    target, reference = objects['M4_Far_00'], objects['M4_Near']
    a = F(reference['world_vertices_m'][0][0])
    assert 0 < a < 1
    assert all(F(point[0]) == a for point in reference['world_vertices_m'])
    assert all(F(point[0]) >= 1 for point in target['world_vertices_m'])
    distance = 1-a
    lower_bounds = []
    for index, face in enumerate(target['triangles']):
        points = [vector(target['world_vertices_m'][vertex]) for vertex in face]
        minimum_x = min(point[0] for point in points)
        lower_bound_squared = (minimum_x-a)**2
        if min(point[2] for point in points) == 2:
            assert max(F(point[2]) for point in reference['world_vertices_m']) == 1
            lower_bound_squared += 1
        assert lower_bound_squared >= distance*distance
        lower_bounds.append({'target_source_triangle_index': index,
                             'against_reference_source_triangle_indices': list(range(len(reference['triangles']))),
                             'independent_lower_bound_squared_m2': str(lower_bound_squared)})
    point_a, point_b = [1, 0, 0], [float(a), 0, 0]
    assert membership(point_a, target['world_vertices_m'], target['triangles'])['exact_source_triangle_indices']
    assert membership(point_b, reference['world_vertices_m'], reference['triangles'])['exact_source_triangle_indices']
    assert dot(subtract(vector(point_b), vector(point_a)), subtract(vector(point_b), vector(point_a))) == distance*distance
    return {'schema': 'm5-independent-main-surface-proximity-v1',
            'objects_in_pair_order': ['M4_Far_00', 'M4_Near'],
            'object_ids_in_pair_order': [target['reference_object_id'], reference['reference_object_id']],
            'coordinate_frame': 'world', 'unit': 'm', 'surface_only': True,
            'reference_plane_x_exact': str(a), 'distance_exact_m': str(distance),
            'distance_binary64_m': float(distance), 'distance_binary64_exact': str(F(float(distance))),
            'direction_a_to_b': [-1, 0, 0], 'one_legal_witness': {'a': point_a, 'b': point_b},
            'witness_nonuniqueness': 'Any shared YZ point in the Near triangle and vertical target region yields a legal nearest pair.',
            'global_lower_bound_proof': 'Every target point has x>=1 and every reference point has x=a. Thus every source-face pair distance is at least 1-a. The displayed pair attains this bound.',
            'target_source_triangle_count': len(target['triangles']), 'reference_source_triangle_count': len(reference['triangles']),
            'all_source_face_lower_bounds': lower_bounds,
            'horizontal_source_faces_strictly_farther': [row['target_source_triangle_index'] for row in lower_bounds
                if F(row['independent_lower_bound_squared_m2']) > distance*distance],
            'geometry_path': str(GEOMETRY), 'geometry_sha256': GEOMETRY_SHA,
            'publication_tolerance_m': str(PUBLICATION_TOLERANCE_M),
            'distance_comparison': 'Exact binary64 value equal to the correctly rounded rational distance.',
            'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0}


def validate_main_fact(fact, target, reference):
    truth = main_answer()
    if fact.get('status') != 'measured' or type(fact.get('value')) is not dict:
        raise ValueError('main_surface_proximity_not_measured')
    value = fact['value']
    distance = value.get('distance_m')
    if type(distance) not in (int, float) or not math.isfinite(distance) or float(distance) != truth['distance_binary64_m']:
        raise ValueError('main_independent_surface_distance')
    witness = value.get('nearest_witness')
    if type(witness) is not dict:
        raise ValueError('nested_value_nearest_witness_required')
    point_a, point_b = vector(witness['a']), vector(witness['b'])
    left = membership(witness['a'], target['vertices'], target['faces'])
    right = membership(witness['b'], reference['vertices'], reference['faces'])
    if not left['within_publication_tolerance_source_triangle_indices'] or not right['within_publication_tolerance_source_triangle_indices']:
        raise ValueError('published_witness_outside_current_source_surfaces')
    exact_distance = F(truth['distance_exact_m'])
    delta = subtract(point_b, point_a)
    squared_length = dot(delta, delta)
    if not (exact_distance-PUBLICATION_TOLERANCE_M)**2 <= squared_length <= (exact_distance+PUBLICATION_TOLERANCE_M)**2:
        raise ValueError('published_witness_length_not_nearest')
    if vector(witness.get('direction_a_to_b')) != (-1, 0, 0):
        raise ValueError('A_to_B_direction_not_negative_X')
    if fact.get('witness_status') != 'measured' or fact.get('direction_status') != 'measured':
        raise ValueError('witness_or_direction_status')
    return {'passed_checked_scope': True, 'distance_m': distance,
            'exact_distance_residual': str(F(distance)-exact_distance),
            'squared_published_witness_length': str(squared_length),
            'witness_a_source_membership': left, 'witness_b_source_membership': right,
            'same_particular_witness_required': False}


def folded_fixture():
    vertices = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
    faces = [[0, 1, 2], [0, 3, 1]]
    reference = [[-1, 0, 0], [-1, 1, 0], [-1, 0, 1]]
    normals = [cross(subtract(vector(vertices[face[1]]), vector(vertices[face[0]])),
                     subtract(vector(vertices[face[2]]), vector(vertices[face[0]]))) for face in faces]
    assert cross(normals[0], normals[1]) != (0, 0, 0)
    witnesses = [{'a': [0, .5, 0], 'b': [-1, .5, 0], 'target_source_triangle': 0},
                 {'a': [0, 0, .5], 'b': [-1, 0, .5], 'target_source_triangle': 1}]
    for witness in witnesses:
        assert witness['target_source_triangle'] in membership(witness['a'], vertices, faces)['exact_source_triangle_indices']
        assert membership(witness['b'], reference, [[0, 1, 2]])['exact_source_triangle_indices'] == [0]
    return {'schema': 'm5-independent-folded-source-fixture-v1', 'scope': 'pure offline geometry and source-mapping control',
            'target': {'name': 'FoldTarget', 'object_id': 'fixture:fold-target', 'instance_id': 'fold-instance-1',
                       'vertices': vertices, 'faces': faces, 'source_triangle_indices': [0, 1]},
            'reference': {'name': 'FoldReference', 'object_id': 'fixture:fold-reference', 'instance_id': 'reference-instance-1',
                          'vertices': reference, 'faces': [[0, 1, 2]], 'source_triangle_indices': [0]},
            'target_normals_exact': normals, 'distance_exact_m': '1', 'direction_a_to_b': [-1, 0, 0],
            'legal_witnesses_on_different_target_facets': witnesses,
            'proof': 'All target x>=0 and reference x=-1. Each displayed source-facet witness attains distance 1.',
            'changed_coordinate_same_distance': {'vertex_index': 3, 'new_value': [0, 0, 2]},
            'face_order_change_same_union': [[0, 3, 1], [0, 1, 2]],
            'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0}


if __name__ == '__main__':
    directory = HERE / 'scoring'
    directory.mkdir(exist_ok=True)
    for name, value in (('TRUTH.json', main_answer()), ('FOLDED_TRUTH.json', folded_fixture())):
        value['oracle_source_sha256'] = sha(Path(__file__))
        with (directory / name).open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, default=str, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n')
    print(json.dumps({'independent_main_and_folded_truth_ready': True, 'new_actual_calls': 0}))
