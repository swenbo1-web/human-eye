"""Private, exact source-geometry oracle for the frozen mixed target task.

The finite-pool conclusions follow from exact planar rays and the frozen
geometry. Current-frame readability is evaluated separately from actual
producer buffers. This module does not run a product or renderer.
"""

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
GEOMETRY_SHA = 'decdcc1532f31ceb5c75203705ba5b533520f7a525fa8c6ea0391ba3a1fa36da'
DIRECTIONS = {'SCENE': (4, -4, 3), 'TOP': (0, 0, 1), 'LEFT': (-1, 0, 1),
              'RIGHT': (1, 0, 1), 'FRONT': (0, -1, 1), 'BACK': (0, 1, 1)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def components(faces):
    incidence = {}
    for index, face in enumerate(faces):
        for first, second in zip(face, face[1:] + face[:1]):
            incidence.setdefault(tuple(sorted((first, second))), []).append(index)
    assert all(len(rows) <= 2 for rows in incidence.values())
    neighbors = [set() for _ in faces]
    for rows in incidence.values():
        for index in rows:
            neighbors[index].update(set(rows) - {index})
    remaining, groups = set(range(len(faces))), []
    while remaining:
        queue, found = [min(remaining)], set()
        while queue:
            index = queue.pop()
            if index not in found:
                found.add(index)
                queue.extend(neighbors[index]-found)
        remaining.difference_update(found)
        groups.append(sorted(found))
    return groups


def derive():
    path = HERE / 'reference/FROZEN_GEOMETRY.json'
    assert sha(path) == GEOMETRY_SHA
    geometry = json.loads(path.read_bytes())
    source = {row['name']: row for row in geometry['objects']}
    target = source[geometry['target_name']]
    points = [tuple(F(value) for value in row) for row in target['world_vertices_m']]
    groups = components(target['triangles'])
    assert groups == [list(range(512)), [512, 513]]
    regions = []
    for indices in groups:
        vertices = {points[vertex] for index in indices for vertex in target['triangles'][index]}
        low = tuple(min(point[k] for point in vertices) for k in range(3))
        high = tuple(max(point[k] for point in vertices) for k in range(3))
        fixed = [axis for axis in range(3) if low[axis] == high[axis]]
        assert len(fixed) == 1
        axis = fixed[0]
        free = [k for k in range(3) if k != axis]
        first_face = target['triangles'][indices[0]]
        a, b, c = (points[vertex] for vertex in first_face)
        n = cross(tuple(y-x for x, y in zip(a, b)), tuple(y-x for x, y in zip(a, c)))
        sign = 1 if n[axis] > 0 else -1
        normal = tuple(sign if k == axis else 0 for k in range(3))
        area = F(0)
        for index in indices:
            a, b, c = (points[vertex] for vertex in target['triangles'][index])
            n = cross(tuple(y-x for x, y in zip(a, b)), tuple(y-x for x, y in zip(a, c)))
            assert n[axis]*sign > 0 and all(n[k] == 0 for k in free)
            area += abs(n[axis])/2
        assert area == (high[free[0]]-low[free[0]])*(high[free[1]]-low[free[1]]) == 1
        center = tuple((low[k]+high[k])/2 for k in range(3))
        if axis == 2:
            assert low[2] == 2 and normal == (0, 0, 1)
            assert all(F(point[2]) <= 1 for name, obj in source.items() if name != geometry['target_name']
                       for point in obj['world_vertices_m'])
            assert all(point[2] <= 1 for point in points[:289])
            assert all(direction[2] > 0 for direction in DIRECTIONS.values())
            statuses = {name: 'complete' for name in DIRECTIONS}
            reason = None
            proof = 'The region lies at z=2. Every fixed eye ray increases z, while all other geometry is at z<=1.'
        else:
            assert axis == 0 and low[0] == 1 and normal == (-1, 0, 0)
            near = [tuple(F(value) for value in point) for point in source['M4_Near']['world_vertices_m']]
            d = near[0][0]
            assert near == [(d, 0, 0), (d, 1, 0), (d, 0, 1)] and 0 < d < 1
            assert d*d/2 == F(73786983304225, 9223372036854775808)
            statuses = {'SCENE': 'back_facing', 'TOP': 'edge_on', 'LEFT': 'positive_area_occlusion',
                        'RIGHT': 'back_facing', 'FRONT': 'edge_on', 'BACK': 'edge_on'}
            reason = 'positive_area_occlusion_all_front_views'
            proof = 'LEFT is the only front direction. The Near triangle casts y>=0,z>=0,y+z<=d with exact positive area d^2/2 onto x=1.'
        corners = []
        for first, second in ((0, 0), (1, 0), (1, 1), (0, 1)):
            corner = list(low)
            corner[free[0]], corner[free[1]] = (high if first else low)[free[0]], (high if second else low)[free[1]]
            corners.append(corner)
        regions.append({'id': 'region_' + str(indices[0]), 'object_name': geometry['target_name'],
                        'source_triangle_indices': indices, 'center_world_m': center,
                        'bounds_world_m': [low, high], 'boundary_vertices_world_m': corners,
                        'unit_normal_world': normal, 'area_m2_exact': str(area),
                        'geometry_complete_in_pool': any(value == 'complete' for value in statuses.values()),
                        'geometric_classifications': statuses, 'unknown_reason_code': reason, 'analytic_proof': proof})
    return {'schema': 'target-task-consumption-private-truth-v1', 'administrator_only': True,
            'geometry_sha256': GEOMETRY_SHA, 'object_name': geometry['target_name'],
            'coordinate_frame': 'world', 'unit': 'm', 'finite_view_pool_only': True,
            'directions': DIRECTIONS, 'regions': regions,
            'pixel_truth': 'Computed only for frames actually constructed in each current slot. No pixel result is supplied for an unconstructed view.',
            'thresholds': {'surface_pixels': 16, 'boundary_pixels': 4, 'RGB_euclidean_distance': 24},
            'oracle_source_sha256': sha(Path(__file__)), 'new_actual_calls': 0}


if __name__ == '__main__':
    path = HERE / 'admin/TRUTH.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(derive(), stream, default=str, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'private_truth_created': True, 'new_actual_calls': 0}))
