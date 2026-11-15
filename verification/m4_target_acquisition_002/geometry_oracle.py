"""Independent rational analysis of the exact frozen mixed-target geometry."""

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
GEOMETRY_SHA = 'decdcc1532f31ceb5c75203705ba5b533520f7a525fa8c6ea0391ba3a1fa36da'
DIRECTIONS = {'SCENE': (4, -4, 3), 'TOP': (0, 0, 1), 'LEFT': (-1, 0, 1),
              'RIGHT': (1, 0, 1), 'FRONT': (0, -1, 1), 'BACK': (0, 1, 1)}


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def components(faces):
    incidence = {}
    for index, face in enumerate(faces):
        for first, second in zip(face, face[1:] + face[:1]):
            incidence.setdefault(tuple(sorted((first, second))), []).append(index)
    assert all(len(values) <= 2 for values in incidence.values())
    neighbors = [set() for _ in faces]
    for values in incidence.values():
        for index in values:
            neighbors[index].update(set(values) - {index})
    unseen, result = set(range(len(faces))), []
    while unseen:
        pending = [min(unseen)]
        found = set()
        while pending:
            index = pending.pop()
            if index not in found:
                found.add(index)
                pending.extend(neighbors[index] - found)
        unseen.difference_update(found)
        result.append(sorted(found))
    return result


def analyze():
    path = HERE / 'reference/FROZEN_GEOMETRY.json'
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == GEOMETRY_SHA
    frozen = json.loads(raw)
    objects = {row['name']: {'points': [tuple(F(value) for value in point) for point in row['world_vertices_m']],
                              'faces': row['triangles']} for row in frozen['objects']}
    target = objects[frozen['target_name']]
    assert len(objects) == 14 and len(target['points']) == 293 and len(target['faces']) == 514
    groups = components(target['faces'])
    assert groups == [list(range(512)), [512, 513]]
    assert target['points'][289:] == [(F(1), F(0), F(2)), (F(2), F(0), F(2)),
                                     (F(2), F(1), F(2)), (F(1), F(1), F(2))]
    regions = []
    for kind, indices, expected_normal in (
            ('vertical', groups[0], (-1, 0, 0)), ('horizontal', groups[1], (0, 0, 1))):
        area = F(0)
        axis = 0 if kind == 'vertical' else 2
        for index in indices:
            a, b, c = [target['points'][vertex] for vertex in target['faces'][index]]
            normal = cross(tuple(y-x for x, y in zip(a, b)), tuple(y-x for x, y in zip(a, c)))
            assert dot(normal, expected_normal) > 0
            assert all(normal[k] == 0 for k in range(3) if k != axis)
            assert all(point[axis] == (1 if axis == 0 else 2) for point in (a, b, c))
            area += abs(normal[axis]) / 2
        assert area == 1
        regions.append({'kind': kind, 'source_faces': indices, 'source_triangle_count': len(indices),
                        'front_direction': list(expected_normal), 'area_exact': str(area)})
    assert all(point[2] <= 1 for name, source in objects.items() if name != frozen['target_name'] for point in source['points'])
    assert all(point[2] <= 1 for point in target['points'][:289])
    near = objects['M4_Near']
    d = near['points'][0][0]
    assert near['points'] == [(d, 0, 0), (d, 1, 0), (d, 0, 1)] and 0 < d < 1
    area = d*d/2
    assert area == F(73786983304225, 9223372036854775808)
    center = (F(3, 2), F(1, 2), F(1))
    separations = []
    for name, direction in DIRECTIONS.items():
        seed = (0, 1, 0) if name == 'TOP' else (0, 0, 1)
        negative = tuple(-value for value in direction)
        right = cross(negative, seed)
        up = cross(right, negative)
        axes = (right, up)
        maxima = []
        candidates = []
        for axis in axes:
            norm2 = dot(axis, axis)
            projections = [dot(axis, tuple(value-offset for value, offset in zip(point, center))) for point in target['points']]
            maxima.append(max(abs(value) for value in projections)**2/norm2)
            other = [dot(axis, tuple(value-offset for value, offset in zip(point, center))) for point in objects['M4_Far_11']['points']]
            lo, hi = min(other), max(other)
            distance = lo if lo > 0 else -hi if hi < 0 else F(0)
            candidates.append({'axis': list(axis), 'norm_squared': norm2,
                               'raw_range': [str(lo), str(hi)], 'nearest_squared': distance**2/norm2})
        span2 = F(121, 100)*max(maxima)
        witnesses = [row for row in candidates if row['nearest_squared'] > span2]
        assert witnesses
        witness = witnesses[0]
        witness['nearest_squared'] = str(witness['nearest_squared'])
        separations.append({'view': name, 'half_span_squared': str(span2), 'strict_separation': witness})
    return {'schema': 'm4-target-002-independent-geometry-v1', 'geometry_sha256': GEOMETRY_SHA,
            'counts': {'objects': 14, 'vertices': sum(len(row['points']) for row in objects.values()),
                       'triangles': sum(len(row['faces']) for row in objects.values()),
                       'target_vertices': 293, 'target_triangles': 514, 'supported_target_regions': 2},
            'regions': regions, 'horizontal_main_geometric_classifications': {name: 'complete' for name in DIRECTIONS},
            'vertical_main_geometric_classifications': {'SCENE': 'back_facing', 'TOP': 'edge_on',
                'LEFT': 'positive_area_occlusion', 'RIGHT': 'back_facing', 'FRONT': 'edge_on', 'BACK': 'edge_on'},
            'vertical_target_only_geometric_classifications': {'SCENE': 'back_facing', 'TOP': 'edge_on',
                'LEFT': 'complete', 'RIGHT': 'back_facing', 'FRONT': 'edge_on', 'BACK': 'edge_on'},
            'near_shadow': {'plane_x': str(d), 'vertical_target_shadow': 'y>=0, z>=0, y+z<=d', 'area_exact': str(area)},
            'horizontal_visibility': 'z=2 is above all other geometry. Every fixed eye direction has positive z, so no positive ray distance meets the lower geometry.',
            'vertical_self_occlusion': 'LEFT positive rays from x=1 have x<1. The added horizontal rectangle has x>=1.',
            'TOP_geometric_margin_m': '1/20', 'Far11_six_view_separation': separations,
            'main_expected': {'supported': 2, 'complete_readable_witnesses_required': 1, 'unknown': 1},
            'target_only_expected': {'supported': 2, 'complete_readable_witnesses_required': 2, 'unknown': 0},
            'actual_pixel_qualification': 'pending original main requests',
            'oracle_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'new_Blender_starts': 0, 'new_rasters': 0, 'new_product_observations': 0}


if __name__ == '__main__':
    report = analyze()
    with (HERE / 'ANALYTIC_REVIEW.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'regions': 2, 'target_faces': 514,
                      'main_required': '1 complete, 1 unknown', 'target_only_required': '2 complete'}))
