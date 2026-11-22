"""Independently solve the fixed task with exact geometry and reopened source order."""

from fractions import Fraction as F
import json
from math import isqrt
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
BUILDER = run_path(str(HERE / 'build_asset.py'))
ORACLE = HERE.parents[1] / 'm4_dense_panel_sweep_001/truth/panel_truth.py'
ORACLE_SHA = '2930b3651bede09c47a1e654c03212a45b85780c7cb316da225918d844b26ce6'
MIN_AREA, MAX_AREA, MIN_NZ = F(19, 4096), F(21, 4096), F(3, 4)
TARGET = {
    'Component_417': (F(5, 1024), (3, 0, 4), (F(49, 32), F(17, 32), F(221, 128))),
    'Component_736': (F(325, 65536), (-5, 0, 12), (F(963, 128), F(1049, 512), F(773, 512))),
    'Component_582': (F(5, 1024), (0, 0, 1), (F(305, 32), F(85, 128), F(5, 4))),
}
PANEL, ROOF, REFERENCE = 'Component_294', 'Component_865', 'M4_Far_00'
require, pin = BUILDER['require'], BUILDER['pin']


def as_meshes(source):
    meshes = {}
    for row in source['objects']:
        require(row['name'] not in meshes and row['native'] == row['evaluated'],
                'nonunique_object_or_evaluated_mesh_mismatch')
        mesh = row['evaluated']
        meshes[row['name']] = (tuple(tuple(map(F, point)) for point in mesh['vertices_world']),
                               tuple(tuple(face) for face in mesh['triangles']))
    require({'objects': len(meshes), 'vertices': sum(len(p) for p, _ in meshes.values()),
             'triangles': sum(len(f) for _, f in meshes.values())} == BUILDER['COUNTS'], 'fixture_counts_changed')
    return meshes


def triangulated(meshes, name, index):
    points, faces = meshes[name]
    return tuple(points[i] for i in faces[index])


def contains(point, triangle, oracle):
    sub, cross, dot = (oracle[name] for name in ('sub', 'cross', 'dot'))
    a, b, c = triangle
    normal = cross(sub(b, a), sub(c, a))
    return any(normal) and dot(normal, sub(point, a)) == 0 and all(
        dot(normal, cross(sub(y, x), sub(point, x))) >= 0 for x, y in oracle['pairs'](triangle))


def distance_certificate(meshes, region, oracle):
    distance = F(1, 4)
    corners = [tuple(map(F, point)) for point in region['corners_world_m']]
    selected_min, selected_max = [tuple(fn(axis) for axis in zip(*corners, strict=True)) for fn in (min, max)]
    a, b = (F(3, 2), F(1, 2), F(7, 4)), (F(3, 2), F(1, 2), F(2))
    require(oracle['sub'](b, a) == (0, 0, distance), 'planned_direction_or_distance_changed')
    bounds, meets = [], []
    for index, face in enumerate(meshes[REFERENCE][1]):
        triangle = triangulated(meshes, REFERENCE, index)
        gaps = [max(F(0), lo - max(axis), min(axis) - hi)
                for lo, hi, axis in zip(selected_min, selected_max, zip(*triangle, strict=True), strict=True)]
        bounds.append(sum(gap**2 for gap in gaps))
        if contains(b, triangle, oracle):
            meets.append(index)
    name = region['object_name']
    source_meets = [i for i in region['source_triangle_indices']
                    if contains(a, triangulated(meshes, name, i), oracle)]
    require(source_meets and meets and min(bounds) == distance**2,
            'registered_witness_does_not_attain_proven_lower_bound')
    return {
        'source_object': name, 'reference_object': REFERENCE,
        'distance_m': float(distance), 'distance_m_exact': str(distance),
        'minimum_squared_bound_m2_exact': str(min(bounds)), 'world_direction': [0, 0, 1],
        'nearest_points_world_m': [list(map(float, a)), list(map(float, b))],
        'nearest_points_world_m_exact': [list(map(str, a)), list(map(str, b))],
        'selected_triangle_indices_containing_witness': source_meets,
        'reference_triangle_indices_containing_witness': meets,
        'reference_triangles_proved_by_exact_componentwise_bbox_lower_bound': len(bounds),
    }


def visibility_contract(meshes, by_name, oracle):
    p, q, r = by_name['Component_417'], by_name['Component_736'], by_name['Component_582']
    require(p['eligible_complete_views'] == [] and q['eligible_complete_views'] == ['LEFT']
            and r['eligible_complete_views'] == list(oracle['DIRECTIONS']), 'frozen_visibility_pattern_changed')
    for view, proof in p['finite_direction_proofs'].items():
        expected = {REFERENCE, PANEL} if view == 'RIGHT' else {REFERENCE}
        require({hit['object_name'] for hit in proof['positive_area_occluders']} == expected,
                'covered_region_blocker_source_changed/' + view)
    for view, proof in q['finite_direction_proofs'].items():
        expected = set() if view == 'LEFT' else {ROOF}
        require({hit['object_name'] for hit in proof['positive_area_occluders']} == expected,
                'switch_view_region_blocker_source_changed/' + view)

    right = p['finite_direction_proofs']['RIGHT']
    blockers = {obj: [hit['source_triangle_index'] for hit in right['positive_area_occluders']
                     if hit['object_name'] == obj] for obj in (PANEL, REFERENCE)}
    require(all(all(point[2] == 2 for point in triangulated(meshes, REFERENCE, index))
                for index in blockers[REFERENCE]), 'right_old_roof_plane_changed')
    plate_points, _ = meshes[PANEL]
    x_plane = plate_points[0][0]
    expected_plate = {(F(7, 4), y, z) for y in (F(3, 8), F(3, 4)) for z in (F(3, 2), F(17, 8))}
    require(set(plate_points) == expected_plate, 'right_plate_rectangle_changed')
    dx, dy, dz = right['direction']
    ray_points, roof_gaps = [], []
    for x, y, z in (tuple(map(F, point)) for point in p['corners_world_m']):
        plate_step, roof_step = (x_plane - x) / dx, (2 - z) / dz
        hit = (x_plane, y + dy * plate_step, z + dz * plate_step)
        require(0 < plate_step <= roof_step and F(3, 8) < hit[1] < F(3, 4)
                and F(3, 2) < hit[2] < F(17, 8), 'right_plate_does_not_precede_roof')
        ray_points.append(list(map(str, hit)))
        roof_gaps.append(roof_step - plate_step)
    require(min(roof_gaps) == 0 and max(roof_gaps) > 0, 'right_plate_not_strictly_first_on_interior')
    return {
        'selection': p['object_name'], 'view': 'RIGHT', 'direction': right['direction'],
        'first_blocker_over_interior': PANEL, 'also_positive_area': REFERENCE,
        'source_triangles': blockers, 'plate_hits_world_m_exact': ray_points,
        'roof_minus_plate_ray_parameter_exact': list(map(str, roof_gaps)),
    }


def evaluate(source):
    oracle_pin = pin(ORACLE, ORACLE_SHA)
    oracle = run_path(str(ORACLE))
    meshes = as_meshes(source)
    conditions = {'area_low_m2_exact': str(MIN_AREA), 'area_high_m2_exact': str(MAX_AREA),
                  'normal_z_min_exact': str(MIN_NZ)}
    components, eligible = [], []
    for name, mesh in meshes.items():
        parts, normals = oracle['partition'](mesh)
        for (normal, offset), indices in parts:
            twice_area = tuple(sum(normals[i][axis] for i in indices) for axis in range(3))
            area_squared = oracle['dot'](twice_area, twice_area) / 4
            norm_squared = oracle['dot'](normal, normal)
            rectangle = oracle['boundary_rectangle'](*mesh, indices, twice_area)
            in_band = MIN_AREA**2 <= area_squared <= MAX_AREA**2
            upward = normal[2] >= 0 and normal[2]**2 >= MIN_NZ**2 * norm_squared
            row = {
                'object_name': name, 'source_triangle_id_ranges': oracle['source_ranges'](indices),
                'plane_normal_integer': list(normal), 'plane_offset_exact': str(offset),
                'area_squared_m4_exact': str(area_squared),
                'rectangle_supported': rectangle is not None, 'eligible': rectangle is not None and in_band and upward,
            }
            components.append(row)
            if not row['eligible']:
                continue
            corners, _ = rectangle
            center = tuple((a + c) / 2 for a, c in zip(corners[0], corners[2], strict=True))
            expected_area, expected_normal, expected_center = TARGET[name]
            require(area_squared == expected_area**2 and normal == expected_normal
                    and center == expected_center and indices == [0, 1], 'registered_region_fact_changed/' + name)
            norm = isqrt(norm_squared)
            require(norm * norm == norm_squared, 'registered_region_normal_lost_exact_denominator/' + name)
            unit = [F(c, norm) for c in normal]
            proofs = {key: oracle['visibility'](meshes, name, indices, corners, normal, d)
                      for key, d in oracle['DIRECTIONS'].items()}
            for proof in proofs.values():
                proof['tested_other_triangles'] = (BUILDER['COUNTS']['triangles'] - len(indices)
                                                   if F(proof['normal_dot_direction']) > 0 else 0)
            views = [key for key, proof in proofs.items() if proof['whole_region_clear']]
            eligible.append({
                **row, 'source_triangle_indices': indices, 'center_world_m': oracle['numeric_vector'](center),
                'center_world_m_exact': list(map(str, center)),
                'corners_world_m': [oracle['numeric_vector'](point) for point in corners],
                'area_m2_exact': str(expected_area), 'area_m2': float(expected_area),
                'unit_normal_world_exact': list(map(str, unit)), 'unit_normal': list(map(float, unit)),
                'finite_direction_proofs': proofs, 'eligible_complete_views': views,
                'expected_unknown_reason': None if views else 'positive_area_occlusion_all_front_views',
            })
    by_name = {row['object_name']: row for row in eligible}
    require(len(eligible) == len(by_name) == len(TARGET) and by_name.keys() == TARGET.keys(),
            'exact_whole_scene_candidate_set_changed')
    first = min(eligible, key=lambda row: F(row['center_world_m_exact'][0]))
    require(first['object_name'] == 'Component_417', 'measurement_target_order_changed')
    return {
        'schema': 'region-task-first-packet-holdout-exact-reopened-truth-v1',
        'counts': BUILDER['COUNTS'], 'conditions': conditions, 'directions': oracle['DIRECTIONS'],
        'independent_geometry_oracle': oracle_pin, 'components': components, 'eligible': eligible,
        'right_blocker_order': visibility_contract(meshes, by_name, oracle),
        'measurement': distance_certificate(meshes, first, oracle),
        'visibility_domain': 'Exact finite orthographic geometry; actual framed pixel evidence is measured in qualification.',
    }


def preview():
    geometry = BUILDER['GEOMETRY']
    pin(geometry, BUILDER['GEOMETRY_SHA'])

    def row(name, vertices, faces):
        mesh = {'vertices_world': vertices, 'triangles': faces}
        return {'name': name, 'native': mesh, 'evaluated': mesh}

    original = [row(obj['name'], obj['vertices_world'], obj['source_triangles'])
                for obj in BUILDER['read'](geometry)['objects']]
    derived = [row(name, vertices, BUILDER['FACES']) for name, vertices in BUILDER['additions']()]
    return evaluate({'objects': original + derived})


if __name__ == '__main__':
    data = preview()
    print(json.dumps({'counts': data['counts'], 'regions': [
        (row['object_name'], row['area_m2_exact'], row['eligible_complete_views']) for row in data['eligible']],
        'measurement': data['measurement']}, allow_nan=False))
