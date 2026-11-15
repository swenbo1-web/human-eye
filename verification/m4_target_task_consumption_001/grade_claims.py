"""Exact claim grading primitives, independent of the routed producer schema."""

from fractions import Fraction as F
import math


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


def grade_answer(answer, normalized, truth, evidence):
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
