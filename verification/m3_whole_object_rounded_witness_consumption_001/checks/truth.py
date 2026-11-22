"""Independent rational edge projections and whole-surface lower bounds."""

from fractions import Fraction as F
from functools import lru_cache
from hashlib import sha256
import json
from math import isfinite, sqrt
from pathlib import Path
from runpy import run_path

NS = Path(__file__).resolve().parents[1]
V = NS.parent
G = run_path(str(V / 'm3_whole_object_rounded_witness_001/checks/geometry.py'))
OLD = run_path(str(V / 'm3_whole_object_witness_triangle_consumption_001/checks/truth.py'))
require, read, pin, objects, source_faces, member = (OLD[k] for k in
    ('require', 'read', 'pin', 'objects', 'source_faces', 'member'))
dot, sub, at = (G[k] for k in ('dot', 'sub', 'at'))
SLOT = Path('D:/he_m4_cross_scale_assembly_transfer_001/slots/P1')
ASSET = SLOT / 'native/input.blend'
TERMINAL = SLOT / 'TERMINAL_SOURCE.json'
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
TERMINAL_SHA = 'd0d2294f5e5fe006d2f3f23deaf34290dba696b39424585b7cd5e4494d8ffa90'
SOURCE = {'ASSET': ASSET, 'ASSET_SHA': ASSET_SHA, 'PRIOR_TERMINAL': TERMINAL,
          'PRIOR_TERMINAL_SHA': TERMINAL_SHA, 'PRIOR_RUN': SLOT}
DOMAIN = 'zero_based_object_local_current_evaluated_capture_triangle_rows'
TARGET = 'N02'
REFERENCES = ('N04', 'N05')
THRESHOLD = F(1, 5)
REPORT_METRES = F(1, 20000)
REPORT_DIRECTION = 5e-5
ROWS = {'N04': (21, 24), 'N05': (22, 5)}


def vector(point):
    require(type(point) in (list, tuple) and len(point) == 3
            and all(type(v) in (int, float, str) and (type(v) is not float or isfinite(v)) for v in point),
            'three_finite_world_coordinates_required')
    return tuple(F(v) for v in point)


@lru_cache(maxsize=1)
def archive():
    pin(TERMINAL, TERMINAL_SHA)
    return read(TERMINAL)


def verify_source(source, first=None):
    baseline = archive()
    metadata = ('asset_sha256', 'scene', 'view_layer', 'frame', 'subframe',
                'scale_length', 'unit_settings', 'source_index_domain')
    snapshot = ('source', 'objects', 'source_face_offsets', 'display_object_mask',
                'display_scope', 'display_read', 'layer_collections', 'scene_cameras')
    require(first is None or all(first[key] == source[key] for key in snapshot),
            'actual_before_and_after_scene_or_display_changed')
    require(all(source['source'][key] == baseline['source'][key] for key in metadata)
            and source['source']['source_index_domain'] == DOMAIN,
            'frozen_world_frame_or_asset_binding_changed')
    rows, expected = objects(source), objects(baseline)
    require(len(rows) == len(source['objects']) == len(expected) == 28
            and rows.keys() == expected.keys()
            and len({row['object_id'] for row in rows.values()}) == 28
            and len({row['instance_id'] for row in rows.values()}) == 28,
            'frozen_world_roster_not_unique_or_changed')
    mesh_fields = ('native', 'evaluated', 'matrix_world', 'native_matrix_world', 'mesh_name', 'parent',
                   'modifiers', 'visible_get', 'display')
    for name, row in rows.items():
        require(all(row[key] == expected[name][key] for key in mesh_fields),
                'native_or_evaluated_world_arrays_or_display_changed/' + name)
    offsets = [0]
    for row in source['objects']:
        offsets.append(offsets[-1] + len(row['evaluated']['triangles']))
    counts = {'objects': len(rows),
              'vertices': sum(len(row['evaluated']['vertices_world_m']) for row in rows.values()),
              'triangles': offsets[-1]}
    require(counts == {'objects': 28, 'vertices': 416, 'triangles': 744}
            and offsets == source['source_face_offsets']
            and source['display_object_mask'] == [row['visible_get'] for row in source['objects']],
            'frozen_mesh_totals_source_rows_or_display_mask_changed')
    geometry = {name: row['evaluated'] for name, row in rows.items()}
    return {'counts': counts, 'asset_sha256': source['source']['asset_sha256'],
            'same_saved_frame': True, 'before_after_checked': first is not None,
            'ordered_geometry_sha256': sha256(G['canonical'](geometry).encode()).hexdigest()}


def surface_pair(source, reference):
    require(reference in REFERENCES, 'unregistered_reference_whole_object')
    return [source_faces(source, name)[:2] for name in (TARGET, reference)]


def registered_feature_points(surfaces, reference):
    tri_a, tri_b = (G['selected'](mesh, idx)
                    for mesh, idx in zip(surfaces, ROWS[reference], strict=True))
    # N04 has a vertical supporting edge. Minimize in XY, then match the A point's elevation.
    if reference == 'N04':
        a0, a1, b0 = tri_a[0], tri_a[2], tri_b[1]
        require(tri_b[1][:2] == tri_b[2][:2] and tri_b[1][2] != tri_b[2][2],
                'frozen_N04_vertical_feature_changed')
        direction = sub(a1, a0)
        t = dot(sub(b0, a0)[:2], direction[:2]) / dot(direction[:2], direction[:2])
        a = at(a0, direction, t)
        b = (*b0[:2], a[2])
    else:
        a0, a1, b = tri_a[1], tri_a[2], tri_b[1]
        direction = sub(a1, a0)
        t = dot(sub(b, a0), direction) / dot(direction, direction)
        a = at(a0, direction, t)
    require(0 < t < 1 and G['exactly_on'](a, tri_a) and G['exactly_on'](b, tri_b),
            'frozen_nearest_features_do_not_attain_both_surfaces/' + reference)
    return a, b


@lru_cache(maxsize=12)
def establish_surfaces(surfaces, reference):
    a,b = registered_feature_points(surfaces, reference)
    proof = G['prove_global'](surfaces, a, b)
    require(proof['pairs_proven_by_support'] == proof['triangle_pairs'] == 1936
            and proof['true_vertex_support_gap'] == proof['exact_distance_squared_m2'],
            'independent_rational_support_plane_not_a_global_minimum/' + reference)
    length = proof['distance_m']
    points = {side: list(map(str, point)) for side, point in (('a', a), ('b', b))}
    memberships = {side: member(point, (*mesh, tuple(range(len(mesh[1])))))
                   for side, point, mesh in zip(('a', 'b'), (a, b), surfaces, strict=True)}
    return {'ordered_objects': [TARGET, reference], 'scope': 'whole_objects', 'threshold_m': float(THRESHOLD),
            'distance_squared_m2': proof['exact_distance_squared_m2'], 'distance_m': length,
            'direction_a_to_b': [float(v) / length for v in sub(b, a)],
            'meets_threshold': F(proof['exact_distance_squared_m2']) >= THRESHOLD ** 2,
            'attaining_point_pair': {**points, 'memberships': memberships},
            'registered_source_triangle_indices': list(ROWS[reference]),
            'support_proof': {**proof, 'normal_B_minus_A': list(map(str, sub(b, a)))}}


def establish(source, reference):
    return establish_surfaces(tuple(surface_pair(source, reference)), reference)


def measured(source, reference, item, *, exact=False):
    expected = establish(source, reference)
    a, b = vector(item['a']), vector(item['b'])
    d = sub(b, a)
    length_sq = dot(d, d)
    length = sqrt(length_sq)
    length_tol = 1e-12 if exact else float(REPORT_METRES)
    direction_tol = 1e-12 if exact else REPORT_DIRECTION
    memberships = {side: member(point, source_faces(source, name), F(0) if exact else REPORT_METRES)
                   for side, point, name in (('a', a, TARGET), ('b', b, reference))}
    faces = item.get('source_triangle_indices', {})
    stated = all(type(faces.get(side)) is list and faces[side]
                 and all(type(n) is int for n in faces[side]) and len(set(faces[side])) == len(faces[side])
                 and set(faces[side]) <= set(row['source_triangle_indices_within_tolerance'])
                 for side, row in memberships.items())
    expected_direction = expected['direction_a_to_b']
    return {'distance_correct': abs(float(F(item['distance_m'])) - expected['distance_m']) <= length_tol,
            'direction_correct': all(abs(float(v) - w) <= direction_tol
                                     for v, w in zip(vector(item['direction_a_to_b']), expected_direction, strict=True)),
            'actual_attaining_pair': length > 0 and abs(length - expected['distance_m']) <= 2 * length_tol
                and all(abs(float(v) / length - w) <= 4 * direction_tol
                        for v, w in zip(d, expected_direction, strict=True))
                and (not exact or length_sq == F(expected['distance_squared_m2']))
                and all(m['source_triangle_indices_within_tolerance'] for m in memberships.values()),
            'claimed_source_triangle_indices_are_current': stated, 'memberships': memberships,
            'pair_distance_m': length, 'expected': expected}


def frozen_truth():
    source = archive()
    original = pin(ASSET, ASSET_SHA)
    require(original['bytes'] == 106640, 'frozen_blend_length_changed')
    proofs = {ref: establish(source, ref) for ref in REFERENCES}
    require(not proofs['N04']['meets_threshold'] and proofs['N05']['meets_threshold']
            and proofs['N04']['distance_m'] < proofs['N05']['distance_m'], 'threshold_or_closest_pair_changed')
    return {'schema': 'm3-rounded-whole-object-consumption-independent-v1',
            'assets': {'blend': original, 'current_sealed_source': pin(TERMINAL, TERMINAL_SHA)},
            'source': verify_source(source), 'order': list(REFERENCES), 'threshold_m': float(THRESHOLD),
            'closer_reference': 'N04', 'facts': proofs,
            'human_report_tolerances': {'metres': str(REPORT_METRES), 'direction_component': REPORT_DIRECTION},
            'actual_new_Blender': 0, 'actual_new_models': 0}


if __name__ == '__main__':
    print(json.dumps(frozen_truth(), ensure_ascii=False, allow_nan=False, indent=2))
