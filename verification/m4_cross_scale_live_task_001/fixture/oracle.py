"""Freeze exact rectangle and finite-direction visibility truth from fixture arrays."""

import argparse
from fractions import Fraction as F
import hashlib
import json
from math import sqrt
from pathlib import Path
import runpy


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parents[1]
OUTPUT = Path('D:/he_m4_cross_scale_live_task_001/fixture')
SOURCES = {
    'm4_global_local_qualification_001/oracle/static_oracle.py':
        '019242f0d881dff998daca74ec5303bda86b202233e207da966b9773673d87f2',
    'm4_cross_scale_discovery_001/oracle/geometry_witness.py':
        '29138a145c6a04bccce7ae950f43e3546efc2d71a533b73105bb4a05277558a0',
}
ELIGIBLE = ('M02', 'M06', 'M09')
OPEN = {'M02': ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK'), 'M06': (), 'M09': ('LEFT', 'BACK')}
COUNTS = {'objects': 21, 'vertices': 148, 'triangles': 184}


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        stream.write('\n')


def helpers():
    sources = []
    for name, expected in SOURCES.items():
        path = VERIFICATION / name
        if sha(path) != expected:
            raise ValueError('prior_independent_source_changed/' + name)
        sources.append(runpy.run_path(str(path)))
    return sources


def occluders(objects, region, direction, geometry):
    """Return every positive-depth triangle with positive projected overlap."""
    point_sub, dot, clip, area2 = (geometry[name] for name in ('sub', 'dot', 'clip', 'area2'))
    target = next(row for row in objects if row['name'] == region['object_name'])
    corners = [target['vertices'][i] for i in region['boundary_loops'][0]]
    origin, u, v = corners[0], point_sub(corners[1], corners[0]), point_sub(corners[-1], corners[0])
    uu, vv = dot(u, u), dot(v, v)
    normal = region['plane_normal_integer']
    facing = dot(normal, direction)
    if facing <= 0:
        raise ValueError('registered_direction_not_in_front/' + region['object_name'])

    def distance(point):
        return dot(normal, point_sub(point, origin)) / facing

    result = []
    for row in objects:
        for i, triangle in enumerate(row['triangles']):
            if row is target and i in region['source_triangle_indices']:
                continue
            points = [row['vertices'][j] for j in triangle]
            depths = [distance(point) for point in points]
            if max(depths) <= 0:
                continue
            front = clip(points, depths)
            projected = []
            for point in front:
                offset = distance(point)
                in_plane = tuple(x - offset * d for x, d in zip(point, direction, strict=True))
                relative = point_sub(in_plane, origin)
                projected.append((dot(relative, u) / uu, dot(relative, v) / vv))
            for axis, bound, sign in ((0, 0, 1), (0, 1, -1), (1, 0, 1), (1, 1, -1)):
                projected = clip(projected, [sign * (q[axis] - bound) for q in projected])
            overlap = area2(projected) / 2
            if overlap:
                result.append({'object_name': row['name'], 'source_triangle_index': i,
                               'rectangle_overlap_fraction': str(overlap),
                               'clipped_normalized_polygon': [[str(value) for value in q] for q in projected]})
    return result


def validate_current(recipe, binding):
    if (binding['counts'] != COUNTS or binding['preparation_processes'] != 1 or binding['raster_attempts'] != 0
            or sha(Path(binding['asset_path'])) != binding['asset_sha256']
            or sha(HERE / 'GEOMETRY.json') != binding['geometry']['sha256']):
        raise ValueError('asset_binding_or_original_changed')
    before, after = (Path(binding[key]['path']) for key in ('readback_before_save', 'readback_after_reload'))
    if sha(before) != binding['readback_before_save']['sha256'] or sha(after) != binding['readback_after_reload']['sha256']:
        raise ValueError('asset_readback_identity_changed')
    if before.read_bytes() != after.read_bytes():
        raise ValueError('saved_evaluated_source_changed_after_reload')
    data = read(after)
    if data['scale_length'] != 1 or data['frame'] != 1 or data['subframe'] != 0:
        raise ValueError('readback_scene_generation_changed')
    meshes = []
    for source, built in zip(recipe['objects'], data['objects'], strict=True):
        if (built['name'] != source['name'] or built['matrix_world'] != source['matrix_world']
                or built['evaluated_matrix_world'] != source['matrix_world']
                or built['native'] != built['evaluated'] or not built['visibility']['viewport']):
            raise ValueError('readback_source_binding_changed/' + source['name'])
        verts = [[F.from_float(x) if type(x) is float else F(x) for x in p]
                 for p in built['evaluated']['vertices_world']]
        tris = built['evaluated']['triangles']
        if (verts != [list(map(F, p)) for p in source['vertices_world_m']] or tris != source['triangles']):
            raise ValueError('current_ordered_mesh_differs_from_geometry/' + source['name'])
        meshes.append(dict(name=built['name'], vertices=verts, triangles=tris))
    return meshes


def determine(objects, topology, geometry):
    all_components = [row for mesh in objects
                      for row in topology['component_analysis'](mesh['name'], mesh['vertices'], mesh['triangles'])]
    chosen = [row for row in all_components if row['eligible']]
    if tuple(row['object_name'] for row in chosen) != ELIGIBLE:
        raise ValueError('independent_eligible_set_differs_from_fixed_plan')
    for row in chosen:
        name = row['object_name']
        if row['source_triangle_indices'] != [0, 1]:
            raise ValueError('eligible_triangle_rows_changed/' + name)
        scans = {}
        for label, direction in topology['VIEWS'].items():
            hits = occluders(objects, row, direction, geometry)
            if not hits:
                geometry['prove'](objects, row, direction)
            scans[label] = {'direction': direction, 'tested_other_triangles': COUNTS['triangles'] - 2,
                            'whole_region_clear': not hits, 'positive_area_occluders': hits}
        if tuple(label for label, proof in scans.items() if proof['whole_region_clear']) != OPEN[name]:
            raise ValueError('visibility_truth_differs_from_registered_layout/' + name)
        norm = sqrt(sum(x * x for x in row['plane_normal_integer']))
        row.update(area_m2=sqrt(float(row['area_squared_m4'])),
                   unit_normal=[x / norm for x in row['plane_normal_integer']],
                   finite_direction_proofs=scans,
                   eligible_complete_views=list(OPEN[name]),
                   visibility='certified_clear_direction_available' if OPEN[name] else 'unknown',
                   expected_unknown_reason=None if OPEN[name] else 'positive_area_occlusion_all_front_views')
    return all_components, chosen


def main(current):
    topo, geom = helpers()
    recipe = read(HERE / 'GEOMETRY.json')
    binding = read(OUTPUT / 'ASSET_BINDING.json') if current else None
    objects = (validate_current(recipe, binding) if current else
               [{'name': row['name'], 'vertices': [list(map(F, p)) for p in row['vertices_world_m']],
                 'triangles': row['triangles']} for row in recipe['objects']])
    all_rows, chosen = determine(objects, topo, geom)
    exact = topo['rational_json']
    summary = {'passed': True, 'counts': COUNTS, 'component_count': len(all_rows),
               'rectangles': sum(row['rectangle_supported'] for row in all_rows), 'eligible': exact(chosen),
               'directions': topo['VIEWS'], 'product_imported': False, 'raster_executed': False,
               'geometry_sha256': sha(HERE / 'GEOMETRY.json'), 'role_map_sha256': sha(HERE / 'ROLE_MAP.json'),
               'oracle_source_pins': {str(VERIFICATION / name): pin for name, pin in SOURCES.items()},
               'current_blender_evaluated_readback': current}
    if current:
        draft = read(HERE / 'STATIC_TRUTH.json')
        if draft['eligible'] != summary['eligible']:
            raise ValueError('Blender_current_truth_differs_from_prescribed_geometry')
        summary.update(asset_path=binding['asset_path'], asset_sha256=binding['asset_sha256'],
                       readback_sha256=binding['readback_after_reload']['sha256'],
                       prebuild_truth_sha256=sha(HERE / 'STATIC_TRUTH.json'))
    write(HERE / ('CURRENT_TRUTH.json' if current else 'STATIC_TRUTH.json'), summary)
    print(json.dumps({'passed': True, 'current': current, 'counts': COUNTS,
                     'complete_view_sets': {row['object_name']: row['eligible_complete_views'] for row in chosen}}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current', action='store_true')
    main(parser.parse_args().current)
