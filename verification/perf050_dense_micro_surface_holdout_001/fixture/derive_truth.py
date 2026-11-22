"""Certify the fixed task independently using exact reopened world coordinates."""

from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parents[1] / 'm4_dense_panel_sweep_001/truth/panel_truth.py'
PRIOR_SHA = '2930b3651bede09c47a1e654c03212a45b85780c7cb316da225918d844b26ce6'
MIN_AREA, MAX_AREA = F(7, 2048), F(9, 2048)

helpers = run_path(str(HERE / 'build_asset.py'))
require = helpers['require']
pin = helpers['pin']


def mesh_table(source):
    meshes = {}
    for row in source['objects']:
        require(row['name'] not in meshes and row['native'] == row['evaluated'],
                'native_evaluated_or_object_identity_changed')
        mesh = row['evaluated']
        meshes[row['name']] = (tuple(tuple(map(F, point)) for point in mesh['vertices_world']),
                               tuple(tuple(face) for face in mesh['triangles']))
    require({'objects': len(meshes), 'vertices': sum(len(v) for v, _ in meshes.values()),
             'triangles': sum(len(f) for _, f in meshes.values())} == helpers['COUNTS'],
            'fixture_geometry_counts_changed')
    return meshes


def contains_xy(point, triangle):
    # Signs of exact edge determinants on a nondegenerate horizontal triangle.
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = triangle
    x, y, z = point
    if not az == bz == cz == z:
        return False
    signed_area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    sides = ((bx - ax) * (y - ay) - (by - ay) * (x - ax),
             (cx - bx) * (y - by) - (cy - by) * (x - bx),
             (ax - cx) * (y - cy) - (ay - cy) * (x - cx))
    return signed_area != 0 and all(side * signed_area >= 0 for side in sides)


def measurement(meshes, region):
    reference = 'M4_Far_00'
    distance = F(1, 8)
    corners = [tuple(map(F, point)) for point in region['corners_world_m']]
    selected_min = [min(p[i] for p in corners) for i in range(3)]
    selected_max = [max(p[i] for p in corners) for i in range(3)]
    a = tuple(map(F, region['center_world_m']))
    b = (a[0], a[1], a[2] + distance)
    vertices, faces = meshes[reference]
    bounds, witnesses = [], []
    for index, face in enumerate(faces):
        triangle = tuple(vertices[i] for i in face)
        delta = [max(F(0), selected_min[k] - max(p[k] for p in triangle),
                     min(p[k] for p in triangle) - selected_max[k]) for k in range(3)]
        bounds.append(sum(gap * gap for gap in delta))
        if contains_xy(b, triangle):
            witnesses.append(index)
    require(min(bounds) == distance**2 and witnesses, 'reference_distance_or_attaining_point_changed')
    source_vertices, source_faces = meshes[region['object_name']]
    selected_faces = [i for i in region['source_triangle_indices']
                      if contains_xy(a, tuple(source_vertices[j] for j in source_faces[i]))]
    require(selected_faces, 'selected_attaining_point_outside_faces')
    return {'source_object': region['object_name'], 'reference_object': reference,
            'distance_m': float(distance), 'distance_m_exact': str(distance),
            'world_direction': [0., 0., 1.],
            'nearest_points_world_m': [list(map(float, p)) for p in (a, b)],
            'selected_triangle_indices_containing_witness': selected_faces,
            'reference_triangle_indices_containing_witness': witnesses,
            'reference_triangles_proved_by_exact_componentwise_bbox_lower_bound': len(bounds)}


def evaluate(source):
    pin(PRIOR, PRIOR_SHA)
    oracle = run_path(str(PRIOR))
    meshes = mesh_table(source)
    rectangles, eligible = {}, []
    part_count = rectangle_count = 0
    for name, mesh in meshes.items():
        components, normals = oracle['partition'](mesh)
        part_count += len(components)
        rectangles[name] = []
        for (normal, offset), faces in components:
            area_vector = tuple(sum(normals[i][axis] for i in faces) for axis in range(3))
            perimeter = oracle['boundary_rectangle'](*mesh, faces, area_vector)
            if perimeter is None:
                continue
            rectangle_count += 1
            corners, corner_indices = perimeter
            squared = oracle['dot'](area_vector, area_vector) / 4
            rectangles[name].append((normal, offset, corners, faces, squared))
            if normal != (0, 0, 1) or not MIN_AREA**2 <= squared <= MAX_AREA**2:
                continue
            center = tuple((a + c) / 2 for a, c in zip(corners[0], corners[2], strict=True))
            proofs = {}
            for view, direction in oracle['DIRECTIONS'].items():
                proof = oracle['visibility'](meshes, name, faces, corners, normal, direction)
                proof['tested_other_triangles'] = helpers['COUNTS']['triangles'] - len(faces)
                proofs[view] = proof
            eligible.append({'object_name': name, 'source_triangle_id_ranges': oracle['source_ranges'](faces),
                'source_triangle_indices': faces, 'center_world_m': oracle['numeric_vector'](center),
                'corners_world_m': list(map(oracle['numeric_vector'], corners)),
                'vertex_indices': corner_indices, 'plane_normal_integer': normal, 'unit_normal': [0, 0, 1],
                'area_m2': float(area_vector[2] / 2), 'area_m2_exact': str(area_vector[2] / 2),
                'finite_direction_proofs': proofs,
                'eligible_complete_views': [view for view, proof in proofs.items() if proof['whole_region_clear']]})
    by_name = {region['object_name']: region for region in eligible}
    require(len(eligible) == len(by_name) == 3 and set(by_name) == {'S021', 'S034', 'S055'},
            'whole_scene_exact_candidate_set_changed')
    require(all(row['source_triangle_indices'] == [0, 1] and row['area_m2_exact'] == '1/256'
                for row in eligible), 'eligible_source_or_area_changed')
    for name, area, normal in (('S012', F(13, 4096), (0, 0, 1)), ('S067', F(19, 4096), (0, 0, 1)),
                               ('S041', F(1, 256), (0, 0, -1)), ('S019', F(25, 256), (0, 0, 1))):
        (n, _, _, indices, squared), = rectangles[name]
        require(n == normal and indices == [0, 1] and squared == area**2, 'ineligible_control_changed/' + name)
    clear = {name: row['eligible_complete_views'] for name, row in by_name.items()}
    require('TOP' in clear['S021'] and not clear['S034'] and 'LEFT' in clear['S055']
            and 'SCENE' not in clear['S055'] and 'TOP' not in clear['S055'], 'expected_view_transfer_changed')

    # Check entire lifted rectangles lie strictly inside the known blockers.
    coverage = []
    for selected, blocker, views in (('S034', 'M4_Far_00', oracle['DIRECTIONS']),
                                      ('S055', 'S019', ('SCENE', 'TOP'))):
        covers = [corners for n, plane, corners, _, _ in rectangles[blocker] if n == (0, 0, 1) and plane == 2]
        (cover,) = covers
        lo, hi = [fn(p[0] for p in cover) for fn in (min, max)], [fn(p[1] for p in cover) for fn in (min, max)]
        corners = [tuple(map(F, p)) for p in by_name[selected]['corners_world_m']]
        for view in views:
            direction = oracle['DIRECTIONS'][view]
            lifted = []
            for x, y, z in corners:
                step = (F(2) - z) / direction[2]
                u, v = x + step * direction[0], y + step * direction[1]
                require(lo[0] < u < lo[1] and hi[0] < v < hi[1], 'registered_blocker_does_not_cover_full_region')
                lifted.append([str(u), str(v)])
            hits = by_name[selected]['finite_direction_proofs'][view]['positive_area_occluders']
            source_indices = [hit['source_triangle_index'] for hit in hits if hit['object_name'] == blocker]
            require(source_indices, 'registered_blocker_lacks_exact_positive_area_intersection')
            coverage.append({'selected': selected, 'blocker': blocker, 'view': view,
                             'lifted_target_corners_xy_exact': lifted, 'blocker_source_triangles': source_indices})
    first = min(eligible, key=lambda row: row['center_world_m'][0])
    require(first['object_name'] == 'S034', 'measurement_selection_changed')
    return {'counts': helpers['COUNTS'], 'directions': oracle['DIRECTIONS'],
            'conditions': {'area_min_m2': str(MIN_AREA), 'area_max_m2': str(MAX_AREA),
                           'unit_normal_world': [0, 0, 1]},
            'maximal_plane_component_count': part_count, 'rectangular_component_count': rectangle_count,
            'eligible': eligible, 'blocker_cover_proofs': coverage, 'measurement': measurement(meshes, first),
            'readability': 'Geometric certificates alone do not determine pixel usability.'}


def preview():
    old = helpers['GEOMETRY']
    pin(old, helpers['GEOMETRY_SHA'])
    original = json.loads(old.read_bytes())['objects']
    def row(name, vertices, faces):
        mesh = {'vertices_world': vertices, 'triangles': faces}
        return {'name': name, 'native': mesh, 'evaluated': mesh}
    rows = [row(obj['name'], obj['vertices_world'], obj['source_triangles']) for obj in original]
    rows.extend(row(obj['name'], obj['vertices_world_m'], obj['triangles']) for obj in helpers['additions']())
    print(json.dumps({'offline_preparation_only': True, **evaluate({'objects': rows})},
                     separators=(',', ':'), allow_nan=False))


def main():
    if sys.argv[1:] == ['--preview']:
        preview()
        return
    require(not sys.argv[1:], 'unsupported_fixture_truth_arguments')
    output = helpers['OUTPUT']
    receipt_path = output / 'ASSET_BINDING.json'
    receipt = json.loads(receipt_path.read_bytes())
    reopened = output / 'REOPENED_SOURCE.json'
    asset = output / 'main.blend'
    require(pin(reopened) == receipt['reopened_source'] and pin(asset) == receipt['asset'],
            'fixed_asset_or_reopen_digest_changed')
    result = {'schema': 'perf050-dense-micro-current-reopened-truth-v1',
              'asset': pin(asset), 'reopened_source': pin(reopened), 'binding': pin(receipt_path),
              'independent_rectangle_and_visibility_oracle': pin(PRIOR, PRIOR_SHA),
              **evaluate(json.loads(reopened.read_bytes()))}
    with (HERE / 'TRUTH.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    (HERE / 'ASSET_BINDING.json').write_bytes(receipt_path.read_bytes())
    print(json.dumps({'counts': result['counts'], 'fixture_sha256': result['asset']['sha256'],
                      'truth_sha256': pin(HERE / 'TRUTH.json')['sha256']}))


if __name__ == '__main__':
    main()
