"""Exact claim grading primitives, independent of the routed producer schema."""

from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path


def vector(value):
    if type(value) is not list or len(value) != 3 or any(type(item) is bool for item in value):
        raise ValueError('three_coordinate_vector_required')
    return tuple(F(item) for item in value)


def unit_normal(actual, expected):
    actual = vector(actual)
    expected = vector(expected)
    floats = tuple(float(item) for item in actual)
    length = math.hypot(*floats)
    if not math.isfinite(length) or abs(length-1) > 2e-14:
        return False
    return all(abs(float(a)-float(b)) <= 2e-14 for a, b in zip(actual, expected))


def triangle_set(identity):
    alternatives = []
    if 'source_triangle_indices' in identity:
        values = identity['source_triangle_indices']
        if type(values) is not list or any(type(value) is not int or value < 0 for value in values):
            raise ValueError('source_triangle_index_type')
        if len(values) != len(set(values)):
            raise ValueError('duplicate_source_triangle_indices')
        alternatives.append(set(values))
    if 'source_triangle_index_ranges' in identity:
        intervals = identity['source_triangle_index_ranges']
        if type(intervals) is not list:
            raise ValueError('source_triangle_ranges_type')
        values = []
        for interval in intervals:
            if (type(interval) is not list or len(interval) != 2
                    or any(type(value) is not int for value in interval)
                    or not 0 <= interval[0] <= interval[1] < 1_000_000):
                raise ValueError('source_triangle_range_bounds')
            values.extend(range(interval[0], interval[1]+1))
        if len(values) != len(set(values)):
            raise ValueError('overlapping_source_triangle_ranges')
        alternatives.append(set(values))
    if alternatives and any(value != alternatives[0] for value in alternatives[1:]):
        raise ValueError('conflicting_source_triangle_aliases')
    return alternatives[0] if alternatives else None


def extent(actual, expected):
    asserted = []
    if 'bounds_world_m' in actual:
        bounds = actual['bounds_world_m']
        asserted.append(type(bounds) is list and len(bounds) == 2
                        and list(map(vector, bounds)) == list(map(vector, expected['bounds_world_m'])))
    if 'boundary_vertices_world_m' in actual:
        corners = actual['boundary_vertices_world_m']
        asserted.append(type(corners) is list and len(corners) == len(expected['boundary_vertices_world_m'])
                        and len(set(map(vector, corners))) == len(corners)
                        and set(map(vector, corners)) == set(map(vector, expected['boundary_vertices_world_m'])))
    return bool(asserted) and all(asserted)


def identify(region, truth, aliases):
    identity = region.get('identity')
    if type(identity) is not dict:
        return None
    if 'object_name' in identity and identity['object_name'] != truth['object_name']:
        return None
    matches = []
    faces = triangle_set(identity)
    if faces is not None:
        found = [target['id'] for target in truth['regions'] if faces == set(target['source_triangle_indices'])]
        matches.append(found[0] if len(found) == 1 else None)
    if 'roi_id' in identity:
        matches.append(aliases.get(identity['roi_id']))
    if not matches or 'unique_geometry_description' in identity:
        found = [target['id'] for target in truth['regions']
                 if vector(region.get('center_world_m', [])) == vector(target['center_world_m'])
                 and extent(region, target) and unit_normal(region.get('unit_normal_world', []), target['unit_normal_world'])]
        matches.append(found[0] if len(found) == 1 else None)
    return matches[0] if matches and None not in matches and len(set(matches)) == 1 else None


def witness_valid(witness, identity, evidence):
    if type(witness) is not dict:
        return False
    frame = evidence['by_ref'].get(witness.get('frame_ref'))
    if frame is None or frame['view_name'] != witness.get('view_name') or not frame['current_source_verified']:
        return False
    row = frame['regions'].get(identity)
    return bool(row and row['geometry_complete'] and row['front_facing'] and row['readable']
                and type(witness.get('surface_pixels')) is int
                and type(witness.get('boundary_pixels')) is int
                and witness['surface_pixels'] == row['surface_pixels']
                and witness['boundary_pixels'] == row['boundary_pixels'])


def grade_observation_answer(answer, normalized, truth, evidence):
    checks = []

    def check(name, passed):
        checks.append({'check': name, 'passed': bool(passed)})

    check('object_name', answer.get('object_name') == truth['object_name'])
    check('world_metres', answer.get('coordinate_frame') == 'world' and answer.get('unit') == 'm')
    check('finite_view_pool_only', answer.get('finite_view_pool_only') is True)
    regions = answer.get('regions', [])
    check('regions_array', type(regions) is list)
    regions = regions if type(regions) is list else []
    identities = [identify(region, truth, evidence['aliases']) for region in regions]
    expected_ids = {region['id'] for region in truth['regions']}
    check('entire_region_bijection', len(identities) == len(expected_ids)
          and len(set(identities)) == len(identities) and set(identities) == expected_ids)
    for region, identity in zip(regions, identities):
        if identity is None:
            continue
        target = next(row for row in truth['regions'] if row['id'] == identity)
        check(identity + '.center', vector(region.get('center_world_m', [])) == vector(target['center_world_m']))
        check(identity + '.entire_extent', extent(region, target))
        check(identity + '.oriented_unit_normal', unit_normal(region.get('unit_normal_world', []), target['unit_normal_world']))
        check(identity + '.pool_geometry', region.get('geometry_complete_in_pool') is target['geometry_complete_in_pool'])
        check(identity + '.current_source_reference', bool(region.get('source_references'))
              and all(type(ref) is str and ref and ref in evidence['current_source_references']
                      for ref in region.get('source_references', [])))
        if target['geometry_complete_in_pool']:
            check(identity + '.actual_complete_readable', region.get('complete_readable') is True
                  and witness_valid(region.get('complete_witness'), identity, evidence))
            check(identity + '.no_unknown_reason', region.get('unknown_reason') is None)
        else:
            check(identity + '.honest_unknown', region.get('complete_readable') is False
                  and region.get('complete_witness') is None)
            reason = normalized.get('region_reason_codes', {}).get(identity)
            check(identity + '.specific_unknown_reason', bool(region.get('unknown_reason'))
                  and reason == target['unknown_reason_code'])
    check('entire_final_semantically_reviewed', normalized.get('semantic_review', {}).get('entire_final_reviewed') is True
          and normalized.get('semantic_review', {}).get('all_claims_entailed') is True)
    check('all_extra_assertions_correct', normalized.get('extra_assertion_errors') == [])
    check('no_unretracted_contradictions', normalized.get('contradictions') == [])
    check('limitations_explicit', type(answer.get('limitations')) is list)
    return {'passed': all(row['passed'] for row in checks), 'checks': checks,
            'errors': [row['check'] for row in checks if not row['passed']], 'identified_regions': identities}


def numeric_helpers():
    path = Path(__file__).resolve().parent.with_name('m5_observe_measure_001') / 'oracle.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != '0133b8e69b34e9347cb48cf9220f9a880065f6dc95517e300295afd2c96a9acb':
        raise ValueError('accepted_independent_surface_membership_oracle_changed')
    spec = importlib.util.spec_from_file_location('_m5_consumer_membership', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ordered_geometry_hash(mesh):
    value = {'vertices': mesh['vertices'], 'faces': mesh['faces']}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                                     allow_nan=False).encode('utf-8')).hexdigest()


def grade_measurement(answer, normalized, truth, evidence):
    checks, numeric = [], {}

    def check(name, passed):
        checks.append({'check': name, 'passed': bool(passed)})

    def references(value):
        return (type(value) is list and bool(value) and all(type(ref) is str and ref
                and ref in evidence['current_source_references'] for ref in value))

    value = answer.get('measurement')
    check('measurement.present', type(value) is dict)
    if type(value) is not dict:
        return {'passed': False, 'checks': checks, 'errors': [row['check'] for row in checks if not row['passed']], 'numeric_residuals': numeric}
    expected_names = truth['measurement']['objects_in_pair_order']
    check('measurement.ordered_whole_object_names', [value.get('object_a_name'), value.get('object_b_name')] == expected_names)
    check('measurement.whole_objects_scope', value.get('measurement_scope') == 'whole_objects')
    check('measurement.measured_status', value.get('status') == 'measured')
    check('measurement.current_source_reference', references(value.get('source_references')))
    check('measurement.no_unknown_reason', value.get('unknown_reason') is None)
    expected_distance = F(truth['measurement']['distance_exact_m'])
    tolerance = F.from_float(1e-9)
    distance = value.get('distance_m')
    valid_scalar = type(distance) in (int, float) and math.isfinite(distance)
    check('measurement.finite_nonnegative_distance', valid_scalar and distance >= 0)
    if valid_scalar:
        residual = F(distance)-expected_distance
        numeric.update(distance_error_exact_m=str(residual), distance_error_m=float(residual),
                       expected_distance_exact_m=str(expected_distance), consumer_tolerance_exact_m=str(tolerance))
        check('measurement.independent_distance_publication_tolerance', abs(residual) <= tolerance)
    else:
        check('measurement.independent_distance_publication_tolerance', False)
    current = evidence['whole_object_sources']
    source_rows = value.get('object_source_bindings', [])
    check('measurement.object_source_bindings_bijection', type(source_rows) is list and len(source_rows) == len(expected_names)
          and {row.get('object_name') for row in source_rows if type(row) is dict} == set(expected_names))
    if type(source_rows) is list:
        for row in source_rows:
            name = row.get('object_name') if type(row) is dict else None
            if name not in current:
                check('measurement.unknown_object_source', False)
                continue
            actual = current[name]
            prefix = 'measurement.source.' + name
            check(prefix + '.current_reference', references(row.get('source_references')))
            if 'object_id' in row:
                check(prefix + '.real_object_id', row['object_id'] == actual['object_id'])
            if 'instance_id' in row:
                check(prefix + '.current_instance', row['instance_id'] == actual['instance_id'])
            if 'source_triangle_count' in row:
                check(prefix + '.whole_face_count', type(row['source_triangle_count']) is int and row['source_triangle_count'] == len(actual['faces']))
            asserted_faces = triangle_set(row)
            if asserted_faces is not None:
                check(prefix + '.whole_original_source_faces', asserted_faces == set(range(len(actual['faces']))))
            if 'ordered_geometry_sha256' in row:
                check(prefix + '.ordered_current_geometry_hash', row['ordered_geometry_sha256'] == ordered_geometry_hash(actual))
    witness = value.get('nearest_witness')
    check('measurement.nearest_witness_present', type(witness) is dict)
    if type(witness) is dict:
        helper = numeric_helpers()
        a, b = vector(witness.get('a')), vector(witness.get('b'))
        target, reference = [current[name] for name in expected_names]
        member_a = helper.membership(witness['a'], target['vertices'], target['faces'])
        member_b = helper.membership(witness['b'], reference['vertices'], reference['faces'])
        check('measurement.nearest_a_on_current_whole_target', bool(member_a['within_publication_tolerance_source_triangle_indices']))
        check('measurement.nearest_b_on_current_whole_reference', bool(member_b['within_publication_tolerance_source_triangle_indices']))
        delta = tuple(y-x for x, y in zip(a, b))
        expected_delta = (-expected_distance, F(0), F(0))
        residual = tuple(actual-exact for actual, exact in zip(delta, expected_delta))
        squared = sum(item*item for item in residual)
        check('measurement.nearest_relative_displacement', squared <= tolerance*tolerance)
        check('measurement.oriented_unit_A_to_B_direction', unit_normal(witness.get('direction_a_to_b'), [-1, 0, 0]))
        numeric.update(a_source_membership=member_a, b_source_membership=member_b,
                       displacement_component_errors_exact_m=[str(item) for item in residual],
                       squared_displacement_error_exact_m2=str(squared), particular_equal_distance_pair_required=False)
    relation = answer.get('observation_measurement_correspondence')
    check('correspondence.present', type(relation) is dict)
    if type(relation) is dict:
        check('correspondence.observation_target', relation.get('observation_object_name') == truth['object_name'])
        check('correspondence.whole_measurement_objects', relation.get('measurement_object_names') == expected_names)
        check('correspondence.actual_same_current_source', relation.get('same_current_source') is True
              and evidence['observation_measurement_current_source_consistent'] is True)
        check('correspondence.explanation_present', type(relation.get('explanation')) is str and bool(relation['explanation']))
        check('correspondence.current_references', references(relation.get('source_references')))
        for key, refs in (('parent_binding_sha256', evidence['observation_binding_sha256s']),
                          ('parent_source_binding_sha256', evidence['observation_source_binding_sha256s'])):
            if key in relation:
                check('correspondence.' + key, relation[key] in refs)
    return {'passed': all(row['passed'] for row in checks), 'checks': checks,
            'errors': [row['check'] for row in checks if not row['passed']], 'numeric_residuals': numeric}


def grade_answer(answer, normalized, truth, evidence):
    observation = grade_observation_answer(answer, normalized, truth, evidence)
    measurement = grade_measurement(answer, normalized, truth, evidence)
    return {'passed': observation['passed'] and measurement['passed'],
            'checks': observation['checks'] + measurement['checks'],
            'errors': observation['errors'] + measurement['errors'],
            'identified_regions': observation['identified_regions'], 'measurement': measurement}
