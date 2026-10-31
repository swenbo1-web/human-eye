"""Independent native box-fixture scorer. Python standard library only.

Input is private native truth, never a plugin measurement or success status.
The scorer does not import the engine, bpy, a model client, or network code.
Every real setter (including rollback) needs a full before/after snapshot.
"""
from collections import Counter
from fractions import Fraction
from itertools import combinations, product
import math


FOCAL = 'BluePart'
REFERENCE = 'GreyBase'
GAP_TOL_M = 1e-5
XY_TOL_M = 1e-6
SUPPORT_MARGIN_M = 1e-6
SEPARATION_M = 1e-6
WRITE_CAP_M = .001
WRITE_COUNT_CAP = 8
PATH_CAP_M = .008
_GEOMETRY_KEYS = ('local_vertices', 'faces', 'color')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _finite_tree(value):
    if type(value) in (int, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite_tree(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite_tree(v) for v in value)
    return True


def _vector(value, size):
    return isinstance(value, (list, tuple)) and len(value) == size and all(map(_number, value))


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _unit(a):
    length = math.hypot(*a)
    if not math.isfinite(length) or length == 0:
        raise ValueError('zero or nonfinite vector length')
    return [v / length for v in a]


def _exact_projection(axis, vertex):
    return sum((Fraction(float(x)) * Fraction(float(y)) for x, y in zip(axis, vertex)), Fraction())


def _matrix_axes(obj):
    return [_unit([obj['matrix'][r][c] for r in range(3)]) for c in range(3)]


def _topology(obj):
    """Check the full face/edge mesh before accepting a closed box domain."""
    vertices, faces = obj['local_vertices'], obj['faces']
    errors = []
    undirected = Counter()
    directed = Counter()
    face_sets = set()
    used = set()
    for face in faces:
        key = tuple(sorted(face))
        if key in face_sets:
            errors.append('duplicate_face')
        face_sets.add(key)
        if len(set(face)) != len(face):
            errors.append('repeated_face_vertex')
        used.update(face)
        for a, b in zip(face, face[1:] + face[:1]):
            undirected[tuple(sorted((a, b)))] += 1
            directed[(a, b)] += 1
        # A convex, nondegenerate planar polygon: no zero turns or bow ties.
        points = [vertices[i] for i in face]
        turns = [_cross(_sub(points[(i+1) % len(points)], points[i]),
                        _sub(points[(i+2) % len(points)], points[(i+1) % len(points)]))
                 for i in range(len(points))]
        longest = max(turns, key=lambda v: math.hypot(*v))
        norm = math.hypot(*longest)
        if not math.isfinite(norm) or norm == 0:
            errors.append('degenerate_face')
            continue
        normal = [v/norm for v in longest]
        span = max(math.dist(p, points[0]) for p in points)
        if any(_dot(t, normal) <= 0 for t in turns):
            errors.append('nonconvex_or_degenerate_face')
        if any(abs(_dot(_sub(p, points[0]), normal)) > max(1e-12, span*1e-10) for p in points):
            errors.append('nonplanar_face')
    closed = bool(faces) and all(count == 2 for count in undirected.values())
    oriented = closed and all(directed[(a, b)] == directed[(b, a)] == 1 for a, b in undirected)
    if not closed:
        errors.append('boundary_or_nonmanifold_edges')
    if not oriented:
        errors.append('inconsistent_edge_orientation')
    if used != set(range(len(vertices))):
        errors.append('unused_vertices')
    return {'closed_two_incident_faces_per_edge': closed,
            'consistent_opposite_edge_orientation': oriented,
            'vertex_count': len(vertices), 'face_count': len(faces),
            'edge_count': len(undirected), 'errors': sorted(set(errors))}


def _box_domain(obj):
    topology = _topology(obj)
    errors = list(topology['errors'])
    vertices, faces, matrix = obj['local_vertices'], obj['faces'], obj['matrix']
    bounds = [[min(v[k] for v in vertices), max(v[k] for v in vertices)] for k in range(3)]
    corners = set(product(*bounds))
    if len(vertices) != 8 or len(corners) != 8 or set(map(tuple, vertices)) != corners:
        errors.append('not_eight_distinct_axis_aligned_local_box_corners')
    columns = [[matrix[r][c] for r in range(3)] for c in range(3)]
    lengths = [math.hypot(*c) for c in columns]
    if any(not math.isfinite(v) or v <= 0 for v in lengths):
        errors.append('singular_box_matrix')
        axes = None
    else:
        axes = [[v/lengths[i] for v in columns[i]] for i in range(3)]
        if any(abs(_dot(a, b)) > 2e-6 for a, b in combinations(axes, 2)):
            errors.append('sheared_box_matrix')
    if len(corners) == 8 and len(vertices) == 8 and set(map(tuple, vertices)) == corners:
        side_area = Counter()
        side_vertices = {}
        for face in faces:
            sides = [(k, end) for k in range(3) for end in (0, 1)
                     if all(vertices[i][k] == bounds[k][end] for i in face)]
            if len(sides) != 1:
                errors.append('face_is_not_on_one_box_side')
                continue
            side = sides[0]
            u, v = [k for k in range(3) if k != side[0]]
            polygon = [vertices[i] for i in face]
            area = abs(sum(a[u]*b[v]-b[u]*a[v] for a, b in zip(polygon, polygon[1:]+polygon[:1]))) / 2
            side_area[side] += area
            side_vertices.setdefault(side, set()).update(face)
        for k in range(3):
            u, v = [j for j in range(3) if j != k]
            expected = (bounds[u][1]-bounds[u][0])*(bounds[v][1]-bounds[v][0])
            for end in (0, 1):
                side = (k, end)
                if (len(side_vertices.get(side, ())) != 4 or
                        not math.isclose(side_area[side], expected, rel_tol=1e-10, abs_tol=1e-16)):
                    errors.append('box_side_not_completely_tiled_once')
    return {'supported': not errors, 'errors': sorted(set(errors)), 'topology': topology,
            'bounds_local': bounds, 'axes_world': axes, 'axis_lengths': lengths}


def _inspect(native):
    errors = []
    boxes = {}
    if not isinstance(native, dict) or not isinstance(native.get('objects'), dict):
        return {'raw_valid': False, 'supported': False, 'errors': ['missing_native_objects'], 'objects': {}}
    if not _vector(native.get('normal'), 3) or not math.isfinite(math.hypot(*native.get('normal', []))) or math.hypot(*native.get('normal', [])) == 0:
        errors.append('missing_or_invalid_private_normal')
    objects = native['objects']
    if FOCAL not in objects or REFERENCE not in objects:
        errors.append('missing_focal_or_reference')
    for name, obj in objects.items():
        obj_errors = []
        if not isinstance(name, str) or not isinstance(obj, dict) or not _finite_tree(obj):
            errors.append('invalid_or_nonfinite_object:' + str(name))
            continue
        matrix = obj.get('matrix')
        if not isinstance(matrix, (list, tuple)) or len(matrix) != 4 or not all(_vector(row, 4) for row in matrix):
            obj_errors.append('invalid_matrix')
        elif list(matrix[3]) != [0, 0, 0, 1]:
            obj_errors.append('non_affine_matrix')
        for key in ('local_vertices', 'world_vertices'):
            value = obj.get(key)
            if not isinstance(value, (list, tuple)) or not value or not all(_vector(v, 3) for v in value):
                obj_errors.append('invalid_' + key)
        if ('invalid_local_vertices' not in obj_errors and 'invalid_world_vertices' not in obj_errors
                and len(obj['local_vertices']) != len(obj['world_vertices'])):
            obj_errors.append('local_world_vertex_count_mismatch')
        faces = obj.get('faces')
        count = len(obj.get('local_vertices', ()))
        if (not isinstance(faces, (list, tuple)) or not faces or
                any(not isinstance(f, (list, tuple)) or len(f) < 3 or
                    any(type(i) is not int or i < 0 or i >= count for i in f) for f in faces)):
            obj_errors.append('invalid_faces')
        if not _vector(obj.get('color'), 4):
            obj_errors.append('invalid_color')
        if not obj_errors:
            # Blender stores native coordinates in binary32; allow its final
            # matrix-vector rounding, without altering exact pose invariants.
            for local, world in zip(obj['local_vertices'], obj['world_vertices']):
                predicted = [_dot(matrix[k][:3], local)+matrix[k][3] for k in range(3)]
                if any(not math.isfinite(p) or abs(p-w) > 4e-7*max(1, abs(p), abs(w)) for p, w in zip(predicted, world)):
                    obj_errors.append('world_vertices_inconsistent_with_native_matrix')
                    break
        if obj_errors:
            errors.extend(str(name)+':'+error for error in obj_errors)
        else:
            boxes[name] = _box_domain(obj)
    raw_valid = not errors
    supported = raw_valid and all(box['supported'] for box in boxes.values())
    alignment = {}
    if supported:
        normal = _unit(native['normal'])
        for name in (FOCAL, REFERENCE):
            dots = [abs(_dot(normal, axis)) for axis in boxes[name]['axes_world']]
            axis = max(range(3), key=lambda k: dots[k])
            alignment[name] = axis
            # Sine angle, rather than 1-cos(angle), catches nonparallel faces.
            if math.hypot(*_cross(normal, boxes[name]['axes_world'][axis])) > 2e-6:
                supported = False
                errors.append(name+':normal_not_parallel_to_box_face')
    return {'raw_valid': raw_valid, 'supported': supported, 'errors': errors,
            'objects': boxes, 'normal_face_axes': alignment}


def independent_gap(native):
    """Signed parallel-plane gap using only raw world vertices/private normal."""
    normal = native['normal']
    focal = [_exact_projection(normal, v) for v in native['objects'][FOCAL]['world_vertices']]
    reference = [_exact_projection(normal, v) for v in native['objects'][REFERENCE]['world_vertices']]
    return float(min(focal)-max(reference)) / math.hypot(*normal)


def independent_footprint(native, inspection=None):
    inspection = inspection or _inspect(native)
    if not inspection['supported']:
        return {'passed': False, 'reason': 'unsupported_native_domain'}
    reference = native['objects'][REFERENCE]
    box = inspection['objects'][REFERENCE]
    normal_axis = inspection['normal_face_axes'][REFERENCE]
    tangent_axes = [k for k in range(3) if k != normal_axis]
    local_center = [sum(ends)/2 for ends in box['bounds_local']]
    center = [_dot(reference['matrix'][r][:3], local_center)+reference['matrix'][r][3] for r in range(3)]
    rows = []
    for axis_index in tangent_axes:
        axis = box['axes_world'][axis_index]
        half = ((box['bounds_local'][axis_index][1]-box['bounds_local'][axis_index][0]) * box['axis_lengths'][axis_index]/2)
        projections = [_dot(_sub(v, center), axis) for v in native['objects'][FOCAL]['world_vertices']]
        remaining = half-max(map(abs, projections))
        rows.append({'axis_world': axis, 'support_half_extent_m': half,
                     'minimum_inside_margin_m': remaining,
                     'passed': math.isfinite(remaining) and remaining > SUPPORT_MARGIN_M})
    return {'passed': all(row['passed'] for row in rows), 'support_center_world': center,
            'required_strict_inside_margin_m': SUPPORT_MARGIN_M, 'tangent_intervals': rows}


def independent_all_pairs_sat(native, inspection=None):
    """15 OBB candidate axes, with exact rational interval certificates.

    Any strict projection separation is a valid certificate. Touch, overlap,
    missing geometry and a gap <= 1um cannot certify separation and fail.
    """
    inspection = inspection or _inspect(native)
    if not inspection['supported']:
        return {'passed': False, 'reason': 'unsupported_native_domain', 'pairs': [], 'pair_count': 0}
    objects = native['objects']
    rows = []
    for left, right in combinations(sorted(objects), 2):
        aa, bb = _matrix_axes(objects[left]), _matrix_axes(objects[right])
        candidates = aa+bb+[_cross(a, b) for a in aa for b in bb]
        certificate = None
        tested = 0
        for axis in candidates:
            length = math.hypot(*axis)
            if length <= 1e-12 or not math.isfinite(length):
                continue
            tested += 1
            ap = [_exact_projection(axis, v) for v in objects[left]['world_vertices']]
            bp = [_exact_projection(axis, v) for v in objects[right]['world_vertices']]
            gap = max(min(bp)-max(ap), min(ap)-max(bp))
            threshold = Fraction(SEPARATION_M)*Fraction(math.nextafter(length, math.inf))
            if gap > threshold:
                certificate = {'axis_world': [v/length for v in axis],
                               'strict_interval_gap_m': float(gap)/length}
                break
        rows.append({'objects': [left, right], 'strictly_separated': certificate is not None,
                     'candidate_axis_count': 15, 'tested_axis_count': tested,
                     'separating_axis_certificate': certificate})
    return {'passed': all(row['strictly_separated'] for row in rows), 'pair_count': len(rows),
            'strict_gap_threshold_m': SEPARATION_M, 'pairs': rows}


def _invariants(initial, native, inspection=None):
    inspection = inspection or _inspect(native)
    old, objects = initial.get('objects', {}), native.get('objects', {})
    focal, before = objects.get(FOCAL, {}), old.get(FOCAL, {})
    has_matrix = 'matrix' in focal and 'matrix' in before and inspection['raw_valid']
    checks = {
        'native_raw_finite_and_valid': inspection['raw_valid'],
        'private_normal_exactly_unchanged': initial.get('normal') == native.get('normal'),
        'closed_box_parallel_support_domain': inspection['supported'],
        'object_name_set_exactly_unchanged': set(objects) == set(old),
        'other_objects_exactly_unchanged': all(objects.get(name) == obj for name, obj in old.items() if name != FOCAL),
        'local_focal_geometry_exactly_unchanged': all(key in focal and focal[key] == before.get(key) for key in _GEOMETRY_KEYS),
        'focal_13_nontranslation_matrix_values_exactly_unchanged': bool(has_matrix) and all(
            focal['matrix'][r][c] == before['matrix'][r][c] for r in range(4) for c in range(4) if c != 3 or r == 3),
        'focal_xy_each_within_1um': bool(has_matrix) and all(
            abs(focal['matrix'][k][3]-before['matrix'][k][3]) <= XY_TOL_M for k in (0, 1)),
        'no_user_file_loaded_or_saved': not native.get('loaded_file') and not native.get('user_file_loaded_or_saved', False),
    }
    footprint = independent_footprint(native, inspection)
    sat = independent_all_pairs_sat(native, inspection)
    checks['focal_footprint_strictly_inside_actual_support'] = footprint['passed']
    checks['all_object_pairs_strictly_separated'] = sat['passed']
    return {'passed': all(checks.values()), 'checks': checks, 'footprint': footprint, 'all_pairs_sat': sat}


def _meter(initial, final, supplied):
    """Account for actual setter paths, not apply requests/truth queries."""
    errors = []
    snapshots = supplied
    writes = final.get('writes')
    if not snapshots and isinstance(writes, list):
        snapshots = writes
    if not isinstance(snapshots, (list, tuple)):
        snapshots = []
        errors.append('write_snapshots_not_a_sequence')
    initial_count = initial.get('counts', {}).get('host_write_events', 0)
    final_count = final.get('counts', {}).get('host_write_events')
    if initial_count != 0 or initial.get('native_cumulative_translation_m', 0) != 0:
        errors.append('initial_native_meter_not_fresh_zero')
    count_known = type(initial_count) is int and initial_count >= 0 and type(final_count) is int and final_count >= initial_count
    if count_known:
        count = final_count-initial_count
    elif isinstance(writes, list):
        count = len(writes)
        count_known = True
    else:
        count = None
        errors.append('unknown_actual_setter_count')
    if count_known and count != len(snapshots):
        errors.append('actual_setter_count_does_not_match_full_snapshots')
    if isinstance(writes, list) and count_known and len(writes) != count:
        errors.append('writes_list_does_not_match_actual_setter_count')
    paths, endpoints = [], []
    previous = initial
    path = 0.0
    for index, event in enumerate(snapshots):
        if not isinstance(event, dict) or not isinstance(event.get('before'), dict) or not isinstance(event.get('after'), dict):
            errors.append('missing_full_before_after_snapshot:' + str(index))
            continue
        before, after = event['before'], event['after']
        bi, ai = _inspect(before), _inspect(after)
        chain = before.get('objects') == previous.get('objects') and before.get('normal') == previous.get('normal')
        if not chain:
            errors.append('discontinuous_write_snapshot_chain:' + str(index))
        if not bi['raw_valid'] or not ai['raw_valid']:
            errors.append('invalid_raw_write_snapshot:' + str(index))
            previous = after
            continue
        delta = [after['objects'][FOCAL]['matrix'][k][3]-before['objects'][FOCAL]['matrix'][k][3] for k in range(3)]
        norm = math.hypot(*delta)
        path += norm
        paths.append({'index': index, 'delta_world_m': delta, 'actual_translation_m': norm,
                      'per_setter_cap_passed': math.isfinite(norm) and norm <= WRITE_CAP_M})
        if not paths[-1]['per_setter_cap_passed']:
            errors.append('actual_setter_over_1mm:' + str(index))
        endpoint = _invariants(initial, after, ai)
        endpoint['index'] = index
        endpoints.append(endpoint)
        if not endpoint['passed']:
            errors.append('unsafe_or_changed_write_endpoint:' + str(index))
        previous = after
    if previous.get('objects') != final.get('objects') or previous.get('normal') != final.get('normal'):
        errors.append('final_native_state_not_last_setter_endpoint')
    reported = final.get('native_cumulative_translation_m')
    baseline = initial.get('native_cumulative_translation_m', 0.0)
    path_known = _number(reported) and _number(baseline) and reported >= baseline
    if path_known:
        reported_path = reported-baseline
        if not math.isclose(reported_path, path, rel_tol=1e-12, abs_tol=1e-12):
            errors.append('native_cumulative_path_does_not_match_actual_snapshots')
    elif isinstance(writes, list):
        reported_path = path
        path_known = all(isinstance(event, dict) and isinstance(event.get('before'), dict) and isinstance(event.get('after'), dict) for event in writes)
        if not path_known:
            errors.append('unknown_actual_translation_path')
    else:
        reported_path = None
        errors.append('unknown_actual_translation_path')
    if count_known and count > WRITE_COUNT_CAP:
        errors.append('actual_setter_count_over_8')
    if not math.isfinite(path) or path > PATH_CAP_M or (path_known and reported_path > PATH_CAP_M):
        errors.append('actual_translation_path_over_8mm')
    checks = {'actual_setter_count_known': count_known, 'actual_translation_path_known': path_known,
              'complete_per_setter_path_and_endpoints': not errors,
              'at_most_8_actual_setters': count_known and count <= WRITE_COUNT_CAP,
              'each_actual_setter_at_most_1mm': len(paths) == len(snapshots) and all(p['per_setter_cap_passed'] for p in paths),
              'actual_translation_path_at_most_8mm': path_known and math.isfinite(path) and path <= PATH_CAP_M and reported_path <= PATH_CAP_M}
    return {'passed': all(checks.values()), 'checks': checks, 'errors': errors,
            'actual_write_count': count, 'actual_cumulative_translation_m': path,
            'native_reported_cumulative_translation_m': reported_path,
            'setter_paths': paths, 'write_endpoints': endpoints}


def _score(initial, final, *, kind='goal', target_m=.001, reported_gap_m=None,
           declared_status=None, write_snapshots=()):
    """Return a JSON-safe contract verdict independent of engine/model claims.

    ``passed`` is success for the selected task contract. ``goal_succeeded``
    means geometric target achievement only, hence is always false for correct
    unsupported refusals and read-only measurements. Final-answer claims are
    recorded separately in ``model_report``; they cannot create geometry success.
    """
    if kind not in ('goal', 'readonly', 'unsupported'):
        raise ValueError('kind must be goal, readonly, or unsupported')
    if not _number(target_m) or target_m <= 0:
        raise ValueError('target_m must be a finite positive number')
    ii, fi = _inspect(initial), _inspect(final)
    result = {'schema_version': 1, 'oracle': 'independent_stdlib_native_box_topology_15_axis_sat',
              'kind': kind, 'passed': False, 'checks': {}, 'goal_succeeded': False,
              'domain': {'supported': ii['supported'] and fi['supported'],
                         'initial': ii, 'final': fi},
              'target_m': target_m, 'gap_tolerance_m': GAP_TOL_M,
              'gap_m': None, 'scope': 'native endpoint geometry and actual setter budget; no swept-path or model-benefit claim'}
    if not isinstance(initial, dict) or not isinstance(final, dict):
        result['checks'] = {'native_raw_finite_and_valid': False}
        result['model_report'] = {'declared_status': str(declared_status) if declared_status is not None else None,
                                  'reported_gap_accurate': False, 'claim_used_for_geometry': False}
        return result
    meter = _meter(initial, final, write_snapshots)
    result['write_meter'] = meter
    raw_valid = ii['raw_valid'] and fi['raw_valid']
    normal_unchanged = initial.get('normal') == final.get('normal')
    unchanged = initial.get('objects') == final.get('objects') and normal_unchanged
    zero_write = meter['passed'] and meter['actual_write_count'] == 0 and meter['actual_cumulative_translation_m'] == 0
    gap = independent_gap(final) if fi['supported'] else None
    result['gap_m'] = gap
    report_accurate = gap is not None and _number(reported_gap_m) and abs(reported_gap_m-gap) <= GAP_TOL_M
    normalized = declared_status.lower().strip() if isinstance(declared_status, str) else None
    refusal = normalized in ('unsupported', 'refused', 'refusal', 'domain_unsupported', 'out_of_domain', 'error_unsupported')
    result['model_report'] = {'declared_status': declared_status if isinstance(declared_status, (str, type(None))) else str(declared_status),
                              'reported_gap_m': reported_gap_m if _number(reported_gap_m) else None,
                              'reported_gap_accurate': bool(report_accurate),
                              'unsupported_refusal_declared': refusal,
                              'claim_used_for_geometry': False}
    if kind == 'goal':
        endpoint = _invariants(initial, final, fi)
        result['endpoint'] = endpoint
        result['checks'] = dict(endpoint['checks'], initial_native_domain_supported=ii['supported'],
                                private_normal_exactly_unchanged=normal_unchanged,
                                clearance_within_10um=gap is not None and abs(gap-target_m) <= GAP_TOL_M,
                                all_actual_setter_paths_and_endpoints_passed=meter['passed'])
        result['goal_succeeded'] = all(result['checks'].values())
    elif kind == 'readonly':
        endpoint = _invariants(initial, final, fi)
        result['endpoint'] = endpoint
        result['checks'] = {'initial_and_final_native_domain_supported': ii['supported'] and fi['supported'],
                            'entire_native_scene_exactly_unchanged': unchanged,
                            'zero_actual_writes': zero_write,
                            'reported_native_gap_within_10um': bool(report_accurate),
                            'native_endpoint_safe': endpoint['passed']}
    else:
        result['checks'] = {'initial_and_final_raw_native_valid': raw_valid,
                            'initial_domain_independently_unsupported': not ii['supported'],
                            'entire_native_scene_exactly_unchanged': unchanged,
                            'zero_actual_writes': zero_write,
                            'correct_unsupported_refusal': refusal,
                            'no_user_file_loaded_or_saved': not final.get('loaded_file') and not final.get('user_file_loaded_or_saved', False)}
    result['passed'] = all(result['checks'].values())
    return result


def score(initial, final, *, kind='goal', target_m=.001, reported_gap_m=None,
          declared_status=None, write_snapshots=()):
    """Score private native truth; malformed/unknown input fails closed."""
    if kind not in ('goal', 'readonly', 'unsupported'):
        raise ValueError('kind must be goal, readonly, or unsupported')
    if not _number(target_m) or target_m <= 0:
        raise ValueError('target_m must be a finite positive number')
    try:
        return _score(initial, final, kind=kind, target_m=target_m,
                      reported_gap_m=reported_gap_m, declared_status=declared_status,
                      write_snapshots=write_snapshots)
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, OverflowError, ZeroDivisionError) as error:
        return {'schema_version': 1, 'oracle': 'independent_stdlib_native_box_topology_15_axis_sat',
                'kind': kind, 'passed': False, 'goal_succeeded': False,
                'checks': {'complete_valid_native_evidence': False},
                'domain': {'supported': False, 'error': type(error).__name__+': '+str(error)},
                'model_report': {'claim_used_for_geometry': False}}
