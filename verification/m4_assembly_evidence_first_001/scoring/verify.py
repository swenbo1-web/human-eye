"""Check actual public replay output using fixed geometry and independent arithmetic."""

import argparse
from collections import Counter
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import importlib.util
from itertools import product
import json
import math
from pathlib import Path


BASE = Path(__file__).resolve().parents[2]
SOURCE = BASE / 'm4_observation_baseline_001'
OLD_CASE = BASE / 'closed_solid_read_001' / 'inputs'
WORLD = SOURCE / 'scoring/source/qual001/admin/world_geometry.json'
SNAPSHOT = SOURCE / 'preflight/SOURCE_SNAPSHOT.json'
TRUTH = BASE / 'm4_local_relation_consumption_001/scoring/TRUTH.json'
ASSET = BASE / 'm4_local_relation_consumption_001/input/scene.blend'
ORACLE = SOURCE / 'scoring/source/qual001/oracle/certify.py'
PINS = {
    WORLD: 'daa66107b5b6787dd0083ba5794cb9507218ab8717ee57eb593b749616fd65ab',
    SNAPSHOT: 'ba46e235d6493c193bec7d79b741f2781badda7921aea2537491b609ec6eea4d',
    TRUTH: '2bb917d6d96bfec4b8dffbdbc437f70185f532877e9bcb45855ea2d988e6a1b2',
    ASSET: '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85',
    ORACLE: 'e808997f9aa2fac4338bf340af627abef5e7649bc20473bddad2faaef6d370c7',
    OLD_CASE / 'scene.blend': 'a1a593fc1591365bbbff0c62c535af90ab8b1cdd2dc5ce560d3922252c4e1fcb',
    OLD_CASE / 'TRUTH.json': 'd01b0006ef1d4416c8b40663e8aabb7ba64730c7c833b516c3ee1631651a38ff',
    OLD_CASE / 'author_mesh_snapshots.json': '5a089d22faad7c90b9a28c6ea408ea8b73e8b939e47a3cb66a193ba85f23fc14',
}
PUBLICATION_M = F(1e-9)
CHECKS = ('nonparallel_planes', 'positive_intersection_segment',
          'midpoint_strictly_inside_both_triangles')
VARIANTS = ('A', 'first', 'optimized')
DETAILS = ('brief', 'default', 'full')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def scale(factor, values):
    return tuple(factor * value for value in values)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    x, y, z = a
    u, v, w = b
    return y * w - z * v, z * u - x * w, x * v - y * u


def point(values):
    require(isinstance(values, (list, tuple)) and len(values) == 3
            and all(type(value) in (int, float) and math.isfinite(value) for value in values),
            'nonfinite_or_malformed_world_point')
    return tuple(F(value) for value in values)


def distance_squared(a, b):
    diff = sub(a, b)
    return dot(diff, diff)


def segment_distance_squared(p, a, b):
    edge = sub(b, a)
    t = max(F(0), min(F(1), dot(sub(p, a), edge) / dot(edge, edge)))
    return distance_squared(p, add(a, scale(t, edge)))


def barycentric(p, tri):
    a, b, c = tri
    ab, ac, ap = sub(b, a), sub(c, a), sub(p, a)
    bb, bc, cc = dot(ab, ab), dot(ab, ac), dot(ac, ac)
    bp, cp = dot(ab, ap), dot(ac, ap)
    determinant = bb * cc - bc * bc
    require(determinant > 0, 'degenerate_triangle')
    v = (cc * bp - bc * cp) / determinant
    w = (bb * cp - bc * bp) / determinant
    return (1 - v - w, v, w)


def triangle_distance_squared(p, tri):
    weights = barycentric(p, tri)
    if min(weights) >= 0:
        projection = tuple(dot(weights, values) for values in zip(*tri))
        return distance_squared(p, projection)
    return min(segment_distance_squared(p, start, end)
               for start, end in zip(tri, tri[1:] + tri[:1]))


def mesh_surface_error(p, mesh):
    vertices = [point(v) for v in mesh['vertices']]
    return min(triangle_distance_squared(p, tuple(vertices[i] for i in face))
               for face in mesh['faces'])


def cut_with_plane(tri, origin, normal):
    signed = [dot(sub(p, origin), normal) for p in tri]
    require(min(signed) < 0 < max(signed), 'triangle_lacks_two_sided_cut')
    hits = {p for p, distance in zip(tri, signed) if not distance}
    for i, j in ((0, 1), (1, 2), (2, 0)):
        if signed[i] * signed[j] < 0:
            fraction = signed[i] / (signed[i] - signed[j])
            hits.add(add(tri[i], scale(fraction, sub(tri[j], tri[i]))))
    require(len(hits) == 2, 'triangle_plane_cut_is_not_segment')
    return hits


def exact_crossing(triangles):
    """Independently clip the two exact binary64 triangles on their common line."""
    ta, tb = [tuple(point(p) for p in tri) for tri in triangles]
    na, nb = [cross(sub(b, a), sub(c, a)) for a, b, c in (ta, tb)]
    direction = cross(na, nb)
    require(any(direction), 'parallel_planes')
    axis = max(range(3), key=lambda i: abs(direction[i]))
    a_start, a_end = sorted(cut_with_plane(ta, tb[0], nb), key=lambda v: v[axis])
    b_start, b_end = sorted(cut_with_plane(tb, ta[0], na), key=lambda v: v[axis])
    start = max((a_start, b_start), key=lambda v: v[axis])
    end = min((a_end, b_end), key=lambda v: v[axis])
    require(start[axis] < end[axis], 'no_positive_shared_line_segment')
    mid = scale(F(1, 2), add(start, end))
    weights = [barycentric(mid, tri) for tri in (ta, tb)]
    require(all(min(row) > 0 for row in weights), 'midpoint_not_strictly_inside_both_triangles')
    require(dot(sub(mid, ta[0]), na) == dot(sub(mid, tb[0]), nb) == 0, 'midpoint_off_planes')
    return mid, {
        'intersection_length_m': math.sqrt(float(distance_squared(start, end))),
        'midpoint_world_m': [float(v) for v in mid],
        'barycentric_each_triangle': [[float(value) for value in row] for row in weights],
        'plane_sine': math.sqrt(float(dot(direction, direction) / (dot(na, na) * dot(nb, nb)))),
    }


def face_set(faces):
    return Counter(min(tuple(face[i:] + face[:i]) for i in range(3)) for face in faces)


def world_from_snapshot(vertices, matrix, unit):
    return [tuple((dot(tuple(F(v) for v in row[:3]), point(vertex)) + F(row[3])) * F(unit)
                  for row in matrix[:3]) for vertex in vertices]


def fixed_inputs():
    for path, expected in PINS.items():
        require(digest(path.read_bytes()) == expected, f'frozen_input_changed/{path.name}')
    oracle_spec = importlib.util.spec_from_file_location('frozen_independent_oracle', ORACLE)
    oracle = importlib.util.module_from_spec(oracle_spec)
    oracle_spec.loader.exec_module(oracle)
    names = ('N16', 'N13', 'N08', 'N28')
    export, snapshot, truth = read(WORLD), read(SNAPSHOT), read(TRUTH)
    require(len(export['objects']) == len(snapshot['objects']) == 28
            and snapshot['unit_scale_m'] == 1
            and export['source_sha256'] == truth['source_scene_sha256'] == PINS[ASSET]
            and truth['source_world_geometry_sha256'] == PINS[WORLD]
            and truth['target_id'] == names[0], 'second_frozen_asset_source_binding')
    by_name = {row['name']: row for row in snapshot['objects']}
    sources = {row['name']: row for row in export['objects']}
    require(len(by_name) == len(sources) == 28 and by_name.keys() == sources.keys(),
            'second_frozen_object_coverage')
    for name in names:
        native, world = by_name[name], sources[name]
        require(native['vertices_local'] == world['local_vertices']
                and native['matrix_world'] == world['matrix_world']
                and native['faces'] == world['polygons']
                and world['triangles'] == world['faces']
                and all(any(set(tri) <= set(poly) for poly in native['faces']) for tri in world['faces'])
                and [tuple(map(float, p)) for p in world_from_snapshot(
                    native['vertices_local'], native['matrix_world'], 1)]
                == [tuple(p) for p in world['world_vertices']], 'second_frozen_geometry_mismatch/' + name)
    exact_meshes = {name: oracle.object_mesh(sources[name]) for name in names}
    for mesh in exact_meshes.values():
        oracle.manifold(mesh)
    ring = oracle.certify_ring(exact_meshes[names[0]])
    outcomes = {}
    for published in truth['relations']:
        name = published['neighbor_id']
        replay = oracle.relation(ring, oracle.certify_convex_extrusion(exact_meshes[name]))
        sq = replay['minimum_distance_squared_m2']
        volume = replay['intersection_volume_m3']
        require(sq == published['minimum_distance_squared_m2']
                and volume == published['intersection_volume_m3']
                and replay['classification'] == published['classification'], 'independent_reference_mismatch/' + name)
        distance_squared_m = F(int(sq['numerator']), int(sq['denominator']))
        distance = math.sqrt(float(distance_squared_m))
        zero_tolerance = 'penetrating' if F(volume['numerator']) > 0 else 'separated' if distance_squared_m > 0 else 'touching'
        outcomes[name] = {'relation': zero_tolerance, 'minimum_gap_m': distance,
                          'interval_m': [distance, distance], 'historical_business_classification': replay['classification']}
    require(set(outcomes) == set(names[1:]) and outcomes['N08']['relation'] == 'separated'
            and 0 < outcomes['N08']['minimum_gap_m'] < truth['contact_tolerance_m'], 'second_positive_near_gap')
    old_names = ('Object_01', 'Object_02', 'Object_03', 'Object_04')
    old_snapshot = read(OLD_CASE / 'author_mesh_snapshots.json')['initial']
    old_truth = read(OLD_CASE / 'TRUTH.json')
    require(old_truth['input_snapshot_sha256'] == PINS[OLD_CASE / 'author_mesh_snapshots.json']
            and old_snapshot['unit_scale_m'] == 1, 'assembly001_frozen_source_binding')
    old_outcomes = {name: {'relation': row['relation'], 'interval_m': row.get('distance_interval_m')}
                    for name, row in old_truth['states']['initial']['probes'].items()}
    return {
        'second_assembly': {'names': names, 'meshes': sources, 'outcomes': outcomes, 'nearest': 'N08',
                            'certification': 'exact frozen prism/ray oracle replay with zero geometric tolerance'},
        'assembly001': {'names': old_names, 'outcomes': old_outcomes,
                        'meshes': {m['name']: m for m in old_snapshot['objects']}, 'nearest': 'Object_02',
                        'certification': 'independent frozen closed-shell interval certificates from live assembly 001'},
    }


def view(body):
    if body['schema_version'] == 'task-query-set-v1':
        context = body['binding']
        operands = context['objects']
        rows = body['pairs']
        ids = body['summary']['nearest_separated_ids']
        handling = (body['summary']['nearest_separated_complete'], ids,
                    body['summary']['distance_m'], body['summary']['penetrating_ids'])
        unit, coordinates = body['unit'], body['coordinate_frame']
    else:
        require(body['schema_version'] == 'spatial-relations-v1', 'unexpected_public_result_schema')
        context = body['context']
        operands = [body['target'], *body['candidates']]
        rows = []
        contracts = body['measurement_contracts']
        for row in body['candidates']:
            facts = {name: {**contracts.get(name, {}), **row[name]}
                     for name in ('closed_solid_relation', 'surface_proximity', 'separation_gap')}
            separation = facts.pop('separation_gap')
            rows.append({'candidate_index': row['candidate_index'], 'object_id': row.get('object_id'),
                         'facts': facts, 'separation_gap': separation})
        nearest, penetrating = body['sets']['nearest_separated'], body['sets']['penetrating']

        def ids_for(indices):
            return None if indices is None else [body['candidates'][i]['object_id'] for i in indices]

        handling = (nearest['complete'], ids_for(nearest['candidate_indices']), nearest['distance_m'],
                    ids_for(penetrating['candidate_indices']))
        unit, coordinates = context['unit'], context['coordinate_frame']
    require(body['result_kind'] == 'task_query' and unit == 'm' and coordinates == 'world'
            and body['execution_authority'] is False, 'unexpected_public_result_domain')
    return context, operands, rows, handling


def capture_binding(raw, normalized, body, case):
    context, operands, rows, _ = view(body)
    names = case['names']
    selection = raw['task_selection']
    expected = selection['bindings']
    require(selection['selectors'] == [{'name': name} for name in names]
            and [o['name'] for o in expected] == list(names)
            and [{'object_id': row['object_id'], 'name': row['name']} for row in operands] == expected
            and [(row['candidate_index'], row['object_id']) for row in rows]
            == [(index, row['object_id']) for index, row in enumerate(expected[1:])], 'operands_out_of_order')
    require(context['scene_revision'] == raw['revision']
            and context['source'] == raw['source']
            and context['capture_scope'] == raw['capture_scope'] == 'selected_objects'
            and context['currentness'] == 'capture_snapshot'
            and context['scene_fingerprint'] == digest(canonical(normalized)), 'stale_or_foreign_capture_context')
    identity = raw['host_identity']
    public_identity = context['host_identity']
    instances = public_identity.get('object_instances', {}) | {
        row['object_id']: row['instance_id'] for row in operands if 'instance_id' in row}
    require(public_identity['document_epoch'] == identity['document_epoch']
            and instances == identity['object_instances']
            and len(instances) == len(names) and len(set(instances.values())) == len(names),
            'stale_or_foreign_object_instances')
    require(all(normalized[key] == raw[key] for key in (
        'revision', 'unit', 'coordinate_frame', 'source', 'capture_scope', 'task_selection', 'host_identity')),
        'normalized_capture_source_differs')
    meshes = {mesh['object_id']: mesh for mesh in raw['meshes']}
    require(len(meshes) == len(raw['meshes']) == len(normalized['meshes']) == len(names)
            and set(meshes) == set(instances), 'wrong_capture_mesh_coverage')
    for ordered_raw, canonical_mesh in zip(raw['meshes'], normalized['meshes']):
        require(all(ordered_raw[key] == canonical_mesh[key] for key in ('object_id', 'name', 'vertices', 'faces')),
                'normalized_capture_mesh_differs')
    error = F(0)
    for row in expected:
        mesh = meshes[row['object_id']]
        ref = case['meshes'][row['name']]
        require(mesh['name'] == ref['name'] and len(mesh['vertices']) == len(ref['world_vertices'])
                and face_set(mesh['faces']) == face_set(ref['faces']), 'capture_faces_or_object_differs/' + row['name'])
        error = max(error, *(distance_squared(point(a), point(b))
                             for a, b in zip(mesh['vertices'], ref['world_vertices'])))
        require(error <= F(2.9103830456733704e-11) ** 2, 'capture_world_coordinates_differ/' + row['name'])
    return meshes, {'scene_fingerprint': context['scene_fingerprint'], 'revision': context['scene_revision'],
                    'objects': instances, 'max_reference_world_error_m': math.sqrt(float(error))}


def crossing_fact(evidence, meshes):
    indices = evidence['triangle_indices']
    require(evidence['type'] == 'transverse_triangle_crossing' and len(indices) == len(meshes) == 2
            and all(type(i) is int and 0 <= i < len(row['faces']) for i, row in zip(indices, meshes)),
            'invalid_support_triangle_capture_rows')
    face_rows = [mesh['faces'][i] for mesh, i in zip(meshes, indices)]
    triangles = [[mesh['vertices'][j] for j in face] for mesh, face in zip(meshes, face_rows)]
    require(evidence['triangle_vertices_world_m'] == triangles, 'support_points_do_not_match_capture')
    exact, geometry = exact_crossing(triangles)
    published = evidence['point_world_m']
    require(evidence['publication_tolerance_m'] == float(PUBLICATION_M), 'unexpected_publication_tolerance')
    if evidence['point_status'] == 'approximate':
        require(distance_squared(point(published), exact) <= PUBLICATION_M ** 2, 'published_crossing_point_exceeds_bound')
        geometry['publication_error_m'] = math.sqrt(float(distance_squared(point(published), exact)))
    else:
        require(evidence['point_status'] == 'unknown' and published is None
                and evidence.get('point_reason') in ('world_point_publication_limit', 'world_point_precision_exceeded'),
                'unknown_localization_claims_usable_point')
        geometry['publication_unknown'] = evidence['point_reason']
    return {'triangle_indices': indices, 'triangle_vertex_indices': face_rows, **geometry}


def check_extensions(body, meshes, crossings, expected):
    extension = body.get('capture_evidence')
    require((extension is not None) == expected, 'unexpected_capture_evidence_presence')
    if not expected:
        return None
    require(extension['schema_version'] == 'task-closed-crossing-review-v1'
            and extension['source_scope'] == 'same_normalized_capture_as_binding'
            and extension['index_scope'] == 'zero_based_capture_rows'
            and extension['source_limit'] == 'native_polygon_ids_and_independent_source_not_supplied',
            'unexpected_evidence_schema_or_source_scope')
    expected_counts = {oid: {'vertices': len(mesh['vertices']), 'triangles': len(mesh['faces'])}
                       for oid, mesh in meshes.items()}
    require(extension['object_counts'] == expected_counts, 'evidence_mesh_counts_differ')
    observed = extension['crossings']
    require(len(observed) == len(crossings) and len({item['candidate_index'] for item in observed}) == len(observed),
            'wrong_review_crossing_coverage')
    for item in observed:
        index = item['candidate_index']
        require(type(index) is int and index in crossings and item['status'] == 'verified',
                'review_crossing_bound_to_wrong_candidate')
        require(item['triangle_vertex_indices'] == crossings[index]['triangle_vertex_indices'],
                'review_vertex_rows_differ_from_capture')
        require(item['exact_checks'] == list(CHECKS), 'wrong_exact_certificate_checks')
    return {'object_counts': expected_counts, 'reviewed_candidate_indices': [row['candidate_index'] for row in observed]}


def measured(fact, value):
    return fact.get('status') == 'measured' and fact.get('value') == value


def check_score(body, raw, normalized, case, with_extension):
    meshes, provenance = capture_binding(raw, normalized, body, case)
    _, operands, rows, summary = view(body)
    require(body['status'] == 'observed' and body['coverage'] == {
        'requested_candidates': 3, 'resolved_candidates': 3, 'classified_candidates': 3, 'unresolved_candidates': 0},
        'wrong_positive_fixture_coverage')
    target = meshes[operands[0]['object_id']]
    assertions, values, crossings = {'S1': True}, {}, {}
    for row in rows:
        candidate = meshes[row['object_id']]
        name = candidate['name']
        truth = case['outcomes'][name]
        closed, surface = [row['facts'][key] for key in ('closed_solid_relation', 'surface_proximity')]
        assertions['R/' + name] = measured(closed, truth['relation']) and closed['relation_tolerance_m'] == 0
        item = values[name] = {'claimed_relation': closed['value'], 'reference_relation': truth['relation']}
        if truth['relation'] == 'penetrating':
            require(row['separation_gap']['status'] == 'not_applicable' and row['separation_gap']['value'] is None,
                    'penetration_reported_as_separation_distance')
            require(closed['certificate'] == 'transverse_boundary_interiors', 'missing_exact_transverse_certificate')
            result = crossing_fact(closed['local_evidence'], (target, candidate))
            item['crossing'] = crossings[row['candidate_index']] = result
            assertions['P/' + name] = 'publication_error_m' in result
        if truth['relation'] != 'separated':
            continue
        interval = truth['interval_m']
        gap = row['separation_gap']['value']
        recorded_surface = surface['value']['distance_m']
        assertions['G/' + name] = (type(gap) in (int, float) and math.isfinite(gap) and gap > 0
                                    and measured(row['separation_gap'], recorded_surface)
                                    and interval[0] - 1e-9 <= gap <= interval[1] + 1e-9)
        a, b = [point(surface['value']['nearest_witness'][side]) for side in ('a', 'b')]
        errors = [mesh_surface_error(a, target), mesh_surface_error(b, candidate)]
        actual = math.sqrt(float(distance_squared(a, b)))
        assertions['W/' + name] = (surface['status'] == surface['witness_status'] == 'measured'
            and max(errors) <= PUBLICATION_M ** 2 and interval[0] - 1e-9 <= actual <= interval[1] + 1e-9)
        item.update(gap_m=gap, independent_gap_interval_m=interval, endpoint_distance_m=actual,
                    endpoint_surface_errors_m=[math.sqrt(float(v)) for v in errors])
    complete, nearest, distance, penetrating = summary
    nearest_name = case['nearest']
    by_name = {row['name']: row['object_id'] for row in operands}
    nearest_interval = case['outcomes'][nearest_name]['interval_m']
    expected_penetrating = [by_name[name] for name in case['names'][1:]
                            if case['outcomes'][name]['relation'] == 'penetrating']
    assertions['N1'] = (complete is True and nearest == [by_name[nearest_name]] and penetrating == expected_penetrating
                        and nearest_interval[0] - 1e-9 <= distance <= nearest_interval[1] + 1e-9
                        and all(other['interval_m'][0] > nearest_interval[1]
                                for name, other in case['outcomes'].items()
                                if name != nearest_name and other['relation'] == 'separated'))
    require(len(assertions) == 10 and all(assertions.values()),
            'failed_obligations/' + ','.join(key for key, passed in assertions.items() if not passed))
    extension = check_extensions(body, meshes, crossings, with_extension)
    return {'passed': sum(assertions.values()), 'denominator': len(assertions), 'checks': assertions,
            'facts': values, 'capture': provenance, 'extra_review_evidence': extension}


def checked_rejection(call, expected):
    try:
        call()
    except ValueError as failure:
        require(str(failure) == expected, f'unexpected_rejection/{expected}/{failure}')
        return {'expected': expected, 'actual': str(failure), 'passed': True}
    raise ValueError('missing_rejection/' + expected)


def geometry_controls():
    xy = [(0, 0, 0), (6, 0, 0), (0, 6, 0)]
    cross_x = [(2, -1, -1), (2, 4, -1), (2, 1, 1)]
    _, witness = exact_crossing([xy, cross_x])
    tangent_b = [(2, 4, -1), (2, 6, -1), (2, 4, 1)]
    boundary_b = [(2, 0, 0), (4, 0, 0), (2, 2, 1)]
    return {'exact_transverse': {'passed': True, **witness},
            'coplanar': checked_rejection(lambda: exact_crossing([xy, xy]), 'parallel_planes'),
            'point_tangent': checked_rejection(lambda: exact_crossing([xy, tangent_b]),
                                               'no_positive_shared_line_segment'),
            'edge_contact': checked_rejection(lambda: exact_crossing([xy, boundary_b]),
                                               'triangle_lacks_two_sided_cut')}


def tamper_controls(body, capture, normalized, case):
    context, operands, rows, _ = view(body)
    by_id = {mesh['object_id']: mesh for mesh in capture['meshes']}
    row = next(row for row in rows if row['facts']['closed_solid_relation']['value'] == 'penetrating')
    evidence = row['facts']['closed_solid_relation']['local_evidence']
    pair = (by_id[operands[0]['object_id']], by_id[row['object_id']])
    changed_revision = deepcopy(capture)
    changed_revision['revision'] += '-other-capture'
    changed_normalized = deepcopy(normalized)
    changed_normalized['meshes'][0]['vertices'][0][0] += 0.001
    changed_instances = deepcopy(capture)
    instances = changed_instances['host_identity']['object_instances']
    ids = list(instances)
    instances[ids[0]], instances[ids[1]] = instances[ids[1]], instances[ids[0]]
    wrong_point = deepcopy(evidence)
    wrong_point['point_world_m'][0] += 0.001
    wrong_triangle = deepcopy(evidence)
    wrong_triangle['triangle_indices'][0] = len(pair[0]['faces'])
    wrong_review = deepcopy(body)
    item = wrong_review['capture_evidence']['crossings'][0]
    item['triangle_vertex_indices'][0].reverse()
    crossings = {row['candidate_index']: crossing_fact(evidence, pair)}
    corrupt_capture = deepcopy(capture)
    corrupt_capture['meshes'][0]['vertices'][0][0] += 0.001
    precision = deepcopy(evidence)
    precision.update(point_world_m=None, point_status='unknown', point_reason='world_point_precision_exceeded')
    precision_result = crossing_fact(precision, pair)
    require(precision_result['publication_unknown'] == 'world_point_precision_exceeded', 'unknown_precision_not_preserved')
    precision_wrong = deepcopy(precision)
    precision_wrong['point_world_m'] = evidence['point_world_m']
    controls = {
        'old_revision': (lambda: capture_binding(changed_revision, normalized, body, case),
                         'stale_or_foreign_capture_context'),
        'old_fingerprint': (lambda: capture_binding(capture, changed_normalized, body, case),
                            'stale_or_foreign_capture_context'),
        'wrong_instance': (lambda: capture_binding(changed_instances, normalized, body, case),
                           'stale_or_foreign_object_instances'),
        'wrong_current_mesh': (lambda: capture_binding(corrupt_capture, normalized, body, case),
                               'normalized_capture_mesh_differs'),
        'wrong_triangle_domain': (lambda: crossing_fact(wrong_triangle, pair), 'invalid_support_triangle_capture_rows'),
        'wrong_review_vertex_order': (lambda: check_extensions(wrong_review, by_id, crossings, True),
                                      'review_vertex_rows_differ_from_capture'),
        'overstated_point_precision': (lambda: crossing_fact(wrong_point, pair), 'published_crossing_point_exceeds_bound'),
        'unknown_precision_with_coordinates': (lambda: crossing_fact(precision_wrong, pair),
                                               'unknown_localization_claims_usable_point'),
    }
    return {**{key: checked_rejection(*call) for key, call in controls.items()},
            'unknown_precision_preserved': {'passed': True, 'exact_certificate_review_remains_possible': True,
                                            'publishable_position_claim': False}}


def without_identity_noise(body):
    result = deepcopy(body)
    for key in ('trace_id', 'capture_evidence'):
        result.pop(key, None)
    result.get('binding', result.get('context', {})).pop('runtime_source_sha256', None)
    return result


def read_public(path, *, error=False):
    public_path = path / 'PUBLIC.json'
    raw = public_path.read_bytes()
    request = read(path / 'REQUEST.json')
    response = read(path / 'RESPONSE.json')
    reply = response['result']
    require(response['id'] == request['id'] and reply['isError'] is error
            and reply['content'] == [{'type': 'text', 'text': raw.decode('utf-8')}],
            'public_exact_rpc_envelope_mismatch')
    return raw, json.loads(raw), request


def source_controls(root, variant):
    def load(label, attempt=None, *, error=False):
        path = root / variant / label / 'brief'
        if attempt:
            path /= attempt
        public, body, _ = read_public(path, error=error)
        capture = read(path / 'CAPTURE.json')
        if not error:
            normalized = read(path / 'NORMALIZED_CAPTURE.json')
            context = view(body)[0]
            require(context['scene_fingerprint'] == digest(canonical(normalized))
                    and context['scene_revision'] == normalized['revision'] == capture['revision']
                    and len(capture['meshes']) == len(normalized['meshes'])
                    and all(all(mesh[key] == mesh_raw[key] for key in ('vertices', 'faces', 'object_id', 'name'))
                            for mesh, mesh_raw in zip(normalized['meshes'], capture['meshes'])),
                    'control_capture_is_not_source_bound/' + label)
        return body, {m['object_id']: m for m in capture['meshes']}, capture, digest(public)

    positive_extension = variant != 'A'
    results = {}
    for label, expected_dim in (('touching', 1), ('coplanar_overlap', 2)):
        body, meshes, _, public_hash = load(label)
        _, operands, rows, _ = view(body)
        boxes = []
        for row in operands[:2]:
            points = {point(p) for p in meshes[row['object_id']]['vertices']}
            axis = [(min(v), max(v)) for v in zip(*points)]
            require(points == set(product(*axis)), 'control_source_not_analytic_box/' + label)
            boxes.append(axis)
        overlap = [min(a[1], b[1]) - max(a[0], b[0]) for a, b in zip(*boxes)]
        first = rows[0]['facts']['closed_solid_relation']
        require(min(overlap) == 0 and sum(v > 0 for v in overlap) == expected_dim
                and measured(first, 'touching') and 'local_evidence' not in first,
                'touching_fixture_or_certificate_mislabeled/' + label)
        check_extensions(body, meshes, {}, positive_extension)
        results[label] = {'passed': True, 'contact_dimension': expected_dim, 'public_sha256': public_hash}

    body, meshes, _, public_hash = load('publication_limit')
    _, operands, rows, _ = view(body)
    first = rows[0]['facts']['closed_solid_relation']
    evidence = first['local_evidence']
    require(measured(first, 'penetrating') and first['certificate'] == 'transverse_boundary_interiors'
            and evidence['point_status'] == 'unknown' and evidence['point_world_m'] is None
            and evidence['point_reason'] == 'world_point_precision_exceeded', 'publication_limit_overclaimed')
    pair = (meshes[operands[0]['object_id']], meshes[rows[0]['object_id']])
    crossing = crossing_fact(evidence, pair)
    exact, _ = exact_crossing(evidence['triangle_vertices_world_m'])
    rounding = distance_squared(exact, point(tuple(map(float, exact))))
    require(rounding > PUBLICATION_M ** 2, 'fixture_midpoint_fits_publication_after_all')
    check_extensions(body, meshes, {0: crossing}, positive_extension)
    results['publication_limit'] = {'passed': True, 'point_status': 'unknown', 'exact_witness_still_replayable': True,
                                    'nearest_binary64_point_error_m': math.sqrt(float(rounding)), 'public_sha256': public_hash}

    initial, old_meshes, _, initial_hash = load('stale_capture')
    current, meshes, _, current_hash = load('stale_capture', 'attempt_002')
    old_context, old_operands, old_rows, _ = view(initial)
    context, operands, rows, _ = view(current)
    old_first = old_rows[0]['facts']['closed_solid_relation']
    first = rows[0]['facts']['closed_solid_relation']
    require(old_context['scene_fingerprint'] != context['scene_fingerprint']
            and old_context['scene_revision'] != context['scene_revision']
            and old_operands == operands
            and measured(old_first, 'penetrating') and measured(first, 'separated') and 'local_evidence' not in first,
            'old_capture_reused_after_generation_change')
    moved = meshes[rows[0]['object_id']]
    target = meshes[operands[0]['object_id']]
    require(min(v[0] for v in moved['vertices']) > max(v[0] for v in target['vertices']), 'moved_mesh_not_axis_separated')
    old_crossing = crossing_fact(old_first['local_evidence'],
                                 (old_meshes[old_operands[0]['object_id']], old_meshes[old_rows[0]['object_id']]))
    check_extensions(initial, old_meshes, {0: old_crossing}, positive_extension)
    check_extensions(current, meshes, {}, positive_extension)
    results['stale_capture'] = {'passed': True, 'old_public_sha256': initial_hash, 'new_public_sha256': current_hash,
                                'proof_preserved_only_in_old_snapshot': True}

    failure, _, capture, public_hash = load('wrong_scope', error=True)
    require(capture['capture_scope'] == 'complete_scene_meshes' and failure['status'] == 'error'
            and failure['error'] == 'Scene capture_scope does not match this observation entry'
            and failure['execution_authority'] is False and 'capture_evidence' not in failure,
            'wrong_domain_failure_changed')
    results['wrong_scope'] = {'passed': True, 'reason': failure['error'], 'public_sha256': public_hash}
    return results


def run(root, variants):
    cases = fixed_inputs()
    scored = {}
    expected_contracts = {}
    checked_controls = {}
    installed_controls = {}
    for variant in variants:
        arms = scored[variant] = {}
        for case_name, case in cases.items():
            arms[case_name] = {}
            for detail in DETAILS:
                path = root / variant / case_name / detail
                capture_path = path / 'CAPTURE.json'
                normalized_path, request_path = path / 'NORMALIZED_CAPTURE.json', path / 'REQUEST.json'
                raw_capture = capture_path.read_bytes()
                raw_public, body, request = read_public(path)
                capture, normalized = json.loads(raw_capture), read(normalized_path)
                args = request['params']['arguments']
                query = args['query']
                require(request['method'] == 'tools/call' and request['params']['name'] == 'human_eye_scene_observe'
                        and args['include_image'] is False and args.get('response_detail', 'default') == detail
                        and query['mode'] == 'task' and query['target'] == {'name': case['names'][0]}
                        and query['candidates'] == [{'name': name} for name in case['names'][1:]]
                        and query['requested_facts'] == ['closed_solid_relation', 'surface_proximity'],
                        'unexpected_request_detail_or_operands')
                with_proof = variant != 'A' and detail == 'brief'
                row = check_score(body, capture, normalized, case, with_proof)
                contract_key = (case_name, detail)
                contract = without_identity_noise(body)
                expected = expected_contracts.setdefault(contract_key, contract)
                require(contract == expected, 'public_fact_or_legacy_contract_changed/' + '/'.join(contract_key))
                row.update(public_sha256=digest(raw_public), text_bytes=len(raw_public),
                           capture_sha256=digest(raw_capture), normalized_archive_sha256=digest(normalized_path.read_bytes()),
                           request_sha256=digest(request_path.read_bytes()),
                           historical_geometry_recertification=case['certification'], baseline_contract_preserved=True)
                arms[case_name][detail] = row
                if case_name == 'second_assembly' and with_proof:
                    checked_controls[variant] = tamper_controls(body, capture, normalized, case)
        installed_controls[variant] = source_controls(root, variant)
    return {'schema': 'm4-assembly-evidence-first-independent-verdict-v1',
            'scope': 'Independent offline checker. Replay inputs are saved captures and a simulated host.',
            'input_sha256': {str(path.relative_to(BASE)).replace('\\', '/'): value for path, value in PINS.items()},
            'scored': scored, 'geometry_controls': geometry_controls(), 'rejected_mutations': checked_controls,
            'installed_entry_controls': installed_controls,
            'zero_tolerance_n08': cases['second_assembly']['outcomes']['N08'],
            'separate_independent_readback': 'Fixture provenance was checked offline. A deployed Blender readback was not re-run.',
            'new_model_runs': 0, 'new_blender_runs': 0, 'new_product_solver_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay', type=Path, default=Path('D:/he_m4_assembly_evidence_first_001/replay'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--variants', nargs='+', default=VARIANTS, choices=VARIANTS)
    cli = parser.parse_args()
    result = run(cli.replay, cli.variants)
    cli.output.write_bytes(json.dumps(result, indent=2, allow_nan=False).encode('utf-8') + b'\n')
    print(json.dumps({key: {case: {detail: row['passed'] for detail, row in details.items()}
                           for case, details in cases.items()} for key, cases in result['scored'].items()}))


if __name__ == '__main__':
    main()
