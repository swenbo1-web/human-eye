"""Independent scope/rank oracle and normalized final-answer geometry scoring."""

import argparse
from fractions import Fraction as F
from hashlib import sha256
from math import sqrt
import json
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parents[1]
FIXTURE = Path('D:/he_m4_m5_source_region_001/fixture')
GEOMETRY = VERIFICATION / 'm4_m5_source_region_001/fixture/GEOMETRY.json'
MEMBERSHIP = VERIFICATION / 'm5_observe_measure_001/oracle.py'
ASSET_SHA = 'b9cf3671bc8cd5b88ed23118f229a6e753eda40802d35a3ad297961e0a9edcf9'
READBACK_SHA = '70baebb4994c57a13c145a79627abb0671aafb161f4837e793ac869e6fd9c62c'
GEOMETRY_SHA = 'fa28a684929ef42225a98e0c18b1495bb47b972e3c435b4d5e388f1456e615a1'
MEMBERSHIP_SHA = '0133b8e69b34e9347cb48cf9220f9a880065f6dc95517e300295afd2c96a9acb'
COUNTS = {'objects': 11, 'vertices': 64, 'triangles': 62}
TARGET = 'Obj_07'
SELECTED = (0, 1, 2, 3)
SCOPES = ('selected', 'whole')
REFERENCES = ('Obj_05', 'Obj_08')
REPORT_TOLERANCE_M = F('0.00005')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pin(path, expected=None):
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest()
    require(expected is None or digest == expected, 'fixed_input_digest_changed/' + str(path))
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest}


def vector(values):
    require(isinstance(values, (tuple, list)) and len(values) == 3, 'requires_three_world_coordinates')
    require(all(type(item) in (str, int, float, F) for item in values), 'invalid_world_coordinate')
    return tuple(F(item) for item in values)


def mesh(vertices, faces):
    points = tuple(vector(row) for row in vertices)
    require(all(len(row) == 3 and all(type(i) is int and 0 <= i < len(points) for i in row)
                for row in faces), 'invalid_ordered_source_triangle_rows')
    return points, tuple(tuple(row) for row in faces)


def ordered_meshes(rows, get_mesh):
    result = {row['name']: get_mesh(row) for row in rows}
    require(len(rows) == len(result), 'duplicate_mesh_object_name')
    return result


def geometry_digest(meshes):
    rows = [[name, [[str(coord) for coord in point] for point in vertices], faces]
            for name, (vertices, faces) in sorted(meshes.items())]
    return sha256(json.dumps(rows, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def frozen_meshes():
    source_pins = {
        'asset': pin(FIXTURE / 'main.blend', ASSET_SHA),
        'readback_after_reload': pin(FIXTURE / 'READBACK_AFTER_RELOAD.json', READBACK_SHA),
        'authored_world_geometry': pin(GEOMETRY, GEOMETRY_SHA),
        'independent_point_triangle_distance': pin(MEMBERSHIP, MEMBERSHIP_SHA),
        'oracle': pin(Path(__file__).resolve()),
    }
    readback = json.loads((FIXTURE / 'READBACK_AFTER_RELOAD.json').read_bytes())
    authored = json.loads(GEOMETRY.read_bytes())
    require(readback['frame'] == authored['frame'] == 1 and readback['subframe'] == authored['subframe'] == 0
            and readback['scale_length'] == authored['scale_length'] == 1
            and readback['unit_system'] == 'METRIC' and authored['unit'] == 'metre',
            'fixed_saved_frame_or_units_changed')
    frozen = ordered_meshes(readback['objects'], lambda row: mesh(
        row['evaluated']['vertices_world'], row['evaluated']['triangles']))
    exact = ordered_meshes(authored['objects'], lambda row: mesh(row['vertices_world_m'], row['triangles']))
    counts = {'objects': len(exact), 'vertices': sum(len(vertices) for vertices, _ in exact.values()),
              'triangles': sum(len(faces) for _, faces in exact.values())}
    require(frozen == exact and counts == authored['counts'] == COUNTS
            and set(readback['object_names']) == set(frozen),
            'fixed_authored_and_reopened_ordered_geometry_differ')
    return frozen, source_pins


def verifies_geometry(packet, expected):
    """Verify an actual full-scene TERMINAL_SOURCE.json from the current slot."""
    source = packet['source']
    require(source['asset_sha256'] == ASSET_SHA and source['frame'] == 1 and source['subframe'] == 0
            and source['scale_length'] == 1 and source['unit_settings']['system'] == 'METRIC'
            and source['unit_settings']['scale_length'] == 1, 'current_asset_frame_or_units_changed')
    rows = packet['objects']
    require(packet['display_object_mask'] == [True] * COUNTS['objects'] and len(rows) == COUNTS['objects']
            and all(row['visible_get'] is True for row in rows), 'current_display_is_not_complete')
    actual = ordered_meshes(rows, lambda row: mesh(
        row['evaluated']['vertices_world_m'], row['evaluated']['triangles']))
    require(actual == expected, 'current_ordered_evaluated_geometry_changed')
    ids = {row['object_id']: row['instance_id'] for row in rows}
    require(len(ids) == len(actual) and all(ids.values()), 'ambiguous_current_source_identity')
    return {'passed': True, 'asset_sha256': source['asset_sha256'], 'counts': COUNTS,
            'ordered_world_geometry_sha256': geometry_digest(actual), 'object_ids_and_instances': ids}


def verifies_capture(capture, slot):
    """Compare a decoded product capture against the same slot's full scene.

    The caller must bind the decoded capture to the particular tool response.
    A requested-object subset can prove its own source rows, not scene coverage.
    """
    identity = capture['host_identity']
    actual = {row['name']: row for row in slot['objects']}
    captured = capture['meshes']
    names = [row['name'] for row in captured]
    require(names and len(names) == len(set(names)) and set(names) <= actual.keys(),
            'invalid_current_captured_object_roster')
    if identity['capture_scope'] == 'complete_scene_meshes':
        require(set(names) == actual.keys(), 'complete_scene_capture_missing_objects')
    for row in captured:
        terminal = actual[row['name']]
        evaluated = terminal['evaluated']
        require(row['object_id'] == terminal['object_id']
                and identity['object_instances'][row['object_id']] == terminal['instance_id']
                and mesh(row['vertices'], row['faces']) == mesh(evaluated['vertices_world_m'], evaluated['triangles']),
                'captured_instance_or_ordered_source_rows_changed/' + row['name'])
    return {'passed': True, 'capture_scope': identity['capture_scope'], 'objects': names}


def squared_length(a, b):
    return sum((end - start)**2 for start, end in zip(a, b, strict=True))


def nearby_faces(point, source, indices, tolerance, distance):
    vertices, faces = source
    distances = [(i, distance(point, tuple(vertices[j] for j in faces[i]))) for i in indices]
    return {'within_tolerance': [i for i, value in distances if value <= tolerance*tolerance],
            'exact': [i for i, value in distances if value == 0],
            'minimum_squared_m2': str(min(value for _, value in distances))}


def scoped_ids(meshes, scope):
    return SELECTED if scope == 'selected' else tuple(range(len(meshes[TARGET][1])))


def analytical_truth(meshes, source_pins, point):
    target_vertices, target_faces = meshes[TARGET]
    ring_vertices, ring_faces = meshes['Obj_05']
    reference_vertices, _ = meshes['Obj_08']
    require(all(p[2] == 0 for p in ring_vertices), 'ring_left_Z_zero_plane')
    ring_halfplanes = []
    for index, row in enumerate(ring_faces):
        candidates = [(axis, sign) for axis in (0, 1) for sign in (-1, 1)
                      if all(sign * ring_vertices[j][axis] >= 12 for j in row)]
        require(candidates, 'ring_triangle_enters_inner_square/' + str(index))
        ring_halfplanes.append({'source_triangle': index, 'axis': candidates[0][0], 'sign': candidates[0][1]})
    normal = point['cross']
    diff = point['subtract']
    normals = [normal(diff(target_vertices[row[1]], target_vertices[row[0]]),
                      diff(target_vertices[row[2]], target_vertices[row[0]]))
               for row in (target_faces[i] for i in SELECTED)]
    require(any(any(normal(normals[0], candidate)) for candidate in normals[1:]),
            'selected_faces_are_coplanar')
    all_y_maximum = max(p[1] for p in reference_vertices)
    require(all_y_maximum == -3, 'Obj_08_expected_Y_limit_changed')

    measurements = []
    ranking = {}
    for scope in SCOPES:
        ids = scoped_ids(meshes, scope)
        vertices = [target_vertices[j] for i in ids for j in target_faces[i]]
        xy_abs_max = max(abs(p[k]) for p in vertices for k in (0, 1))
        min_z = min(p[2] for p in vertices)
        min_y = min(p[1] for p in vertices)
        require((xy_abs_max, min_z, min_y) == ((F('4.75'), F(1), F(4)) if scope == 'selected'
                                            else (F(6), F(1, 32), F(4))),
                'surface_extrema_changed/' + scope)
        bounds = {'Obj_05': (F(12) - xy_abs_max)**2 + min_z**2, 'Obj_08': (min_y - all_y_maximum)**2}
        witnesses = {'Obj_05': ([xy_abs_max, F(4), min_z], [F(12), F(4), F(0)]),
                     'Obj_08': ([F(4), F(4), F(1)], [F(4), F(-3), F(1)])}
        ranking[scope] = min(bounds, key=bounds.get)
        for reference in REFERENCES:
            a, b = witnesses[reference]
            ref_ids = range(len(meshes[reference][1]))
            exact_a = nearby_faces(a, meshes[TARGET], ids, F(0), point['triangle_distance_squared'])
            exact_b = nearby_faces(b, meshes[reference], ref_ids, F(0), point['triangle_distance_squared'])
            squared = bounds[reference]
            require(exact_a['exact'] and exact_b['exact'] and squared_length(a, b) == squared,
                    'analytical_lower_bound_not_attained/' + scope + '/' + reference)
            measurements.append({
                'scope': scope, 'reference': reference, 'source_triangles_a': list(ids),
                'source_triangles_b': list(ref_ids), 'distance_squared_m2': str(squared), 'distance_m': sqrt(squared),
                'witness_a': [str(value) for value in a], 'witness_b': [str(value) for value in b],
                'witness_a_exact_source_triangle_ids': exact_a['exact'], 'witness_b_exact_source_triangle_ids': exact_b['exact'],
                'target_max_abs_XY': str(xy_abs_max), 'target_min_Z': str(min_z), 'target_min_Y': str(min_y),
            })
    require(ranking == {'selected': 'Obj_08', 'whole': 'Obj_05'}, 'expected_scope_ranking_reversal_changed')
    return {'schema': 'perf050-source-scope-rank-independent-v1', 'source_pins': source_pins,
            'main_asset_sha256': ASSET_SHA, 'unit': 'm', 'coordinate_frame': 'world', 'frame': 1, 'subframe': 0,
            'counts': COUNTS, 'ordered_world_geometry_sha256': geometry_digest(meshes), 'focus_object': TARGET,
            'selected_source_triangle_ids': list(SELECTED), 'selected_plane_normals_exact': [list(map(str, n)) for n in normals],
            'ring_per_triangle_separating_halfplanes': ring_halfplanes,
            'lower_bound_proof': {
                'Obj_05': 'Each reference triangle lies at z=0 and on one signed side of x or y at 12 m. The target maximum absolute x/y and its minimum z bound squared lateral plus vertical separation. Both terms are attained by a pair on the respective source surfaces.',
                'Obj_08': 'Every reference point has y<=-3 and both target scopes have y>=4. Aligned x and z coordinates attain the 7 m separation on the respective source surfaces.',
            },
            'measurements': measurements, 'ranking': ranking, 'ranking_reverses': True,
            'reported_distance_and_point_surface_tolerance_m': str(REPORT_TOLERANCE_M),
            'actual_new_Blender': 0, 'actual_new_rasters': 0, 'actual_new_models': 0}


def check_measurement(row, expected, meshes, point):
    scope, reference = expected['scope'], expected['reference']
    if row is None:
        return {'scope': scope, 'reference': reference, 'passed': False, 'reason': 'missing_answer_for_this_scope_and_reference'}
    try:
        declared = F(row['distance_m'])
        require(type(row['distance_m']) is not bool and declared >= 0, 'invalid_distance')
        a, b = (vector(row[key]) for key in ('witness_a', 'witness_b'))
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return {'scope': scope, 'reference': reference, 'passed': False, 'reason': 'invalid_or_missing_distance_and_world_point_pair'}
    length_squared = squared_length(a, b)
    true_squared = F(expected['distance_squared_m2'])
    tolerance = REPORT_TOLERANCE_M
    published_distance_ok = max(F(0), declared - tolerance)**2 <= true_squared <= (declared + tolerance)**2
    pair_distance = sqrt(length_squared)
    pair_length_ok = abs(pair_distance - expected['distance_m']) <= float(tolerance)
    source_a = nearby_faces(a, meshes[TARGET], expected['source_triangles_a'], tolerance, point['triangle_distance_squared'])
    source_b = nearby_faces(b, meshes[reference], expected['source_triangles_b'], tolerance, point['triangle_distance_squared'])
    both_members = bool(source_a['within_tolerance'] and source_b['within_tolerance'])
    return {'scope': scope, 'reference': reference, 'passed': published_distance_ok and pair_length_ok and both_members,
            'reported_distance_matches_lower_bound': published_distance_ok,
            'point_pair_attains_lower_bound': pair_length_ok and both_members, 'point_pair_distance_m': pair_distance,
            'witness_a_membership': source_a, 'witness_b_membership': source_b}


def score_geometry(answers, truth, meshes, point):
    """Score a reviewer transcription of the original reply, in metres."""
    rows = answers.get('measurements', [])
    keys = [(row.get('scope'), row.get('reference')) for row in rows]
    expected_keys = {(scope, reference) for scope in SCOPES for reference in REFERENCES}
    require(set(keys) <= expected_keys and len(keys) == len(set(keys)), 'extra_or_duplicate_scope_reference_rows')
    by_key = dict(zip(keys, rows, strict=True))
    results = [check_measurement(by_key.get((row['scope'], row['reference'])), row, meshes, point)
               for row in truth['measurements']]
    ranks = {scope: (answers.get('ranking') or {}).get(scope) == truth['ranking'][scope] for scope in SCOPES}
    registered = answers.get('focus_object') == TARGET and answers.get('selected_source_triangle_ids') == list(SELECTED)
    return {'passed': registered and all(row['passed'] for row in results) and all(ranks.values()),
            'focus_and_selection_as_answered': registered,
            'pairs': results, 'pair_passed': sum(row['passed'] for row in results), 'pair_total': len(results),
            'rankings': ranks, 'ranking_passed': sum(ranks.values()), 'ranking_total': len(ranks)}


def read(path):
    return json.loads(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', type=Path)
    parser.add_argument('--answers', type=Path)
    parser.add_argument('--initial', type=Path)
    parser.add_argument('--terminal', type=Path)
    parser.add_argument('--asset-copy', type=Path)
    args = parser.parse_args()
    meshes, source_pins = frozen_meshes()
    point = run_path(str(MEMBERSHIP))
    truth = analytical_truth(meshes, source_pins, point)
    if args.freeze:
        args.freeze.write_bytes((json.dumps(truth, indent=2, ensure_ascii=False) + '\n').encode())
    if not args.answers:
        print(json.dumps(truth if not args.freeze else {'passed': True, 'truth': pin(args.freeze)}, indent=2))
        return
    require(args.initial and args.terminal and args.asset_copy, 'scoring_requires_current_slot_initial_terminal_and_asset_copy')
    initial, terminal = (read(path) for path in (args.initial, args.terminal))
    proof = [verifies_geometry(packet, meshes) for packet in (initial, terminal)]
    require(all(Path(packet['source']['asset_copy']).resolve() == args.asset_copy.resolve()
                for packet in (initial, terminal)) and initial['source']['pid'] == terminal['source']['pid']
            and proof[0]['object_ids_and_instances'] == proof[1]['object_ids_and_instances'],
            'capture_copy_process_or_instance_binding_changed')
    score = score_geometry(read(args.answers), truth, meshes, point)
    score['slot_sources'] = {'initial': pin(args.initial), 'terminal': pin(args.terminal),
                             'asset_copy': pin(args.asset_copy, ASSET_SHA), 'geometry_proofs': proof}
    print(json.dumps(score, indent=2))


if __name__ == '__main__':
    main()
