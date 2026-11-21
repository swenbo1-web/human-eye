"""Recompute visibility and whole-surface separation from the frozen Blender source."""

from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import runpy


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parents[1]
OLDER = VERIFICATION / 'm4_cross_scale_live_task_001' / 'fixture'
ASSET = Path('D:/he_m4_cross_scale_live_task_001/fixture/main.blend')
TERMINAL = Path('D:/he_m4_cross_scale_live_task_formal_001/slots/P1/TERMINAL_SOURCE.json')
ASSET_SHA = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
TERMINAL_SHA = 'aae8ad86e3c79032346853360d212c4614c71d20cc50b7b1375786860166e927'
DISTANCE = F(15, 64)
PAIR = ((F(-2), F(3, 64), F(65, 64)), (F(-2), F(3, 64), F(5, 4)))


def checked(condition, reason):
    if not condition:
        raise ValueError(reason)


def pin(path):
    body = path.read_bytes()
    return {'path': path.as_posix(), 'bytes': len(body), 'sha256': sha256(body).hexdigest()}


def read(path):
    return json.loads(path.read_bytes())


def write(path, body):
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                    encoding='utf8', newline='\n')


def coordinates(objects):
    return [
        {'name': row['name'], 'vertices': [tuple(map(F, point)) for point in row['evaluated']['vertices_world_m']],
         'triangles': row['evaluated']['triangles']}
        for row in objects
    ]


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b, strict=True))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def barycentric(point, triangle):
    origin, second, third = triangle
    u, v, w = sub(second, origin), sub(third, origin), sub(point, origin)
    uu, uv, vv = dot(u, u), dot(u, v), dot(v, v)
    determinant = uu * vv - uv * uv
    if determinant <= 0:
        return None
    wu, wv = dot(w, u), dot(w, v)
    b, c = (vv * wu - uv * wv) / determinant, (uu * wv - uv * wu) / determinant
    if b < 0 or c < 0 or b + c > 1 or w != tuple(x * b + y * c for x, y in zip(u, v, strict=True)):
        return None
    return [1 - b - c, b, c]


def triangle_points(mesh, row):
    return [mesh['vertices'][i] for i in mesh['triangles'][row]]


def membership(mesh, point):
    return [{'source_triangle_index': i, 'barycentric': weights}
            for i in range(len(mesh['triangles']))
            if (weights := barycentric(point, triangle_points(mesh, i))) is not None]


def whole_distance(first, second):
    x_max = max(point[0] for point in first['vertices'])
    z_max = max(point[2] for point in first['vertices'])
    lower_bounds = []
    for i in range(len(second['triangles'])):
        points = triangle_points(second, i)
        bounds = {'x': min(point[0] for point in points) - x_max,
                  'z': min(point[2] for point in points) - z_max}
        axis = max(bounds, key=bounds.get)
        lower_bounds.append({'M03_source_triangle_index': i, 'axis': '+' + axis.upper(),
                             'axis_lower_bound_m': bounds[axis]})
    lower = min(row['axis_lower_bound_m'] for row in lower_bounds)
    point_a, point_b = PAIR
    members = membership(first, point_a), membership(second, point_b)
    checked(lower == DISTANCE and all(members) and sub(point_b, point_a) == (0, 0, lower),
            'whole_surface_lower_bound_or_attaining_pair_changed')
    return {'objects_in_order': [first['name'], second['name']],
            'mode': 'whole_objects', 'source_triangles_by_object': [list(range(len(row['triangles'])))
                                                                   for row in (first, second)],
            'separation_certificate': lower_bounds, 'distance_m': lower,
            'direction_a_to_b_world': [0, 0, 1], 'distance_mm': lower * 1000,
            'attaining_pair_world_m': PAIR, 'attaining_pair_membership': members,
            'point_pair_may_be_non_unique': True, 'requires_closed_volume': False}


def compute():
    asset, terminal = pin(ASSET), pin(TERMINAL)
    checked(asset['sha256'] == ASSET_SHA and terminal['sha256'] == TERMINAL_SHA, 'frozen_source_changed')
    raw = read(TERMINAL)
    checked((raw['source']['asset_sha256'], raw['source']['frame'], raw['source']['subframe'],
             raw['source']['scale_length']) == (ASSET_SHA, 1, 0, 1), 'terminal_asset_frame_units_changed')
    checked(all(raw['display_object_mask']), 'fixture_visibility_changed')
    old = runpy.run_path(str(OLDER / 'oracle.py'))
    topology, geometry = old['helpers']()
    terminal_meshes = coordinates(raw['objects'])
    reloaded = old['validate_current'](old['read'](OLDER / 'GEOMETRY.json'),
                                      old['read'](ASSET.parent / 'ASSET_BINDING.json'))
    for record in reloaded:
        record['vertices'] = list(map(tuple, record['vertices']))
    ordered_meshes = sorted(terminal_meshes, key=lambda row: row['name'])
    checked(ordered_meshes == reloaded, 'terminal_mesh_rows_differ_from_asset_reload')
    _, chosen = old['determine'](ordered_meshes, topology, geometry)
    region = next(row for row in chosen if row['object_name'] == 'M09')
    checked(region['eligible_complete_views'] == ['LEFT', 'BACK'], 'fixture_complete_views_changed')
    for label, proof in region['finite_direction_proofs'].items():
        if label not in region['eligible_complete_views']:
            checked({row['object_name'] for row in proof['positive_area_occluders']} == {'M03'},
                    'registered_blocker_changed/' + label)
    by_name = {row['name']: row for row in terminal_meshes}
    checked(region['source_triangle_indices'] == list(range(len(by_name['M09']['triangles']))),
            'function_region_differs_from_M09_whole_surface')
    measured = whole_distance(by_name['M09'], by_name['M03'])
    sources = [asset, terminal, pin(OLDER / 'oracle.py'), pin(OLDER / 'GEOMETRY.json'),
               pin(ASSET.parent / 'ASSET_BINDING.json'), pin(Path(__file__)),
               *(pin(VERIFICATION / name) for name in old['SOURCES'])]
    return topology['rational_json']({
        'schema': 'perf050-readonly-product-transfer-truth-v1', 'passed': True, 'source_pins': sources,
        'asset_origin': 'synthetic Blender assembly fixture', 'counts': old['COUNTS'],
        'region': region, 'minimum_pixels': {'surface': 16, 'contrasting_boundary': 4, 'rgb_distance': 24},
        'measurement': measured, 'function_region_is_whole_M09': True,
        'product_imported': False, 'blender_launches': 0, 'model_launches': 0,
    })


if __name__ == '__main__':
    truth = compute()
    write(HERE / 'TRUTH.json', truth)
    print(json.dumps({'passed': truth['passed'], 'views': truth['region']['eligible_complete_views'],
                      'whole_distance_m': truth['measurement']['distance_m']}))
