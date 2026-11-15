"""Supplement sealed quality with frozen-schema and exact extra-claim records."""

from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
ORDER = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')
RUNTIME = Path('D:/he_m4_target_consume_001/formal')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def schema_errors(value, schema, root, path='$'):
    """Implement every assertion keyword used by this frozen public schema."""
    if '$ref' in schema:
        target = root
        for part in schema['$ref'].removeprefix('#/').split('/'):
            target = target[part]
        return schema_errors(value, target, root, path)
    errors = []
    types = {'object': lambda v: type(v) is dict, 'array': lambda v: type(v) is list,
             'string': lambda v: type(v) is str, 'integer': lambda v: type(v) is int,
             'number': lambda v: type(v) in (int, float) and math.isfinite(v),
             'boolean': lambda v: type(v) is bool, 'null': lambda v: v is None}
    if 'type' in schema:
        permitted = schema['type'] if type(schema['type']) is list else [schema['type']]
        if not any(types[kind](value) for kind in permitted):
            return [path + '.type']
    if 'const' in schema and (value != schema['const'] or type(value) is not type(schema['const'])):
        errors.append(path + '.const')
    if 'minimum' in schema and type(value) in (int, float) and value < schema['minimum']:
        errors.append(path + '.minimum')
    if type(value) is dict:
        errors.extend(path + '.required.' + key for key in schema.get('required', []) if key not in value)
        for key, subschema in schema.get('properties', {}).items():
            if key in value:
                errors.extend(schema_errors(value[key], subschema, root, path + '.' + key))
    if type(value) is list:
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', math.inf):
            errors.append(path + '.item_count')
        if 'items' in schema:
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, schema['items'], root, path + '[' + str(index) + ']'))
    for name in ('oneOf', 'anyOf'):
        if name in schema:
            matches = sum(not schema_errors(value, branch, root, path) for branch in schema[name])
            if matches != 1 if name == 'oneOf' else matches == 0:
                errors.append(path + '.' + name)
    return errors


def source_id(region):
    return 'region_' + str(min(low for low, high in region['identity']['source_triangle_index_ranges']))


def projected_bounds(points, pose):
    output = []
    for point in points:
        vector = tuple(F(value) for value in point) + (F(1),)
        view = tuple(sum(F(row[k])*vector[k] for k in range(4)) for row in pose['view_matrix'])
        projected = tuple(sum(F(row[k])*view[k] for k in range(4)) for row in pose['projection_matrix'])
        assert projected[3] != 0
        output.append(tuple(projected[k]/projected[3] for k in range(3)))
    bounds = [[min(point[k] for point in output) for k in range(3)],
              [max(point[k] for point in output) for k in range(3)]]
    return {'inside': all(-1 <= value <= 1 for row in bounds for value in row),
            'exact_ndc_bounds': [[str(value) for value in row] for row in bounds]}


def main():
    schema = read(HERE / 'inputs/ANSWER_SCHEMA.json')
    truth = read(HERE / 'admin/TRUTH.json')
    saved = read(HERE / 'admin/SAVED_REVIEW_01.json')
    device = read(HERE / 'fixtures/DEVICE_CAMERAS.json')
    poses = {row['name']: row for row in device['views']}
    targets = {row['id']: row for row in truth['regions']}
    frozen = read(HERE / 'reference/FROZEN_GEOMETRY.json')
    near = next(row for row in frozen['objects'] if row['name'] == 'M4_Near')
    d = F(near['world_vertices_m'][0][0])
    area = d*d/2
    assert area == F(73786983304225, 9223372036854775808)
    pose = poses['LEFT']
    projection, view = pose['projection_matrix'], pose['view_matrix']
    a = [[sum(F(projection[r][j])*F(view[j][k]) for j in range(4)) for k in range(4)] for r in range(4)]
    jacobian = abs(a[0][1]*a[1][2]-a[0][2]*a[1][1])
    numeric = []
    for slot, claim, reference, context in (
            ('N1', '0.00000800000076', area, 'world area reported approximately'),
            ('N1', '0.000004155632533968272', area*jacobian, 'NDC result from explicitly floating projection/clipping'),
            ('N1', '0.5194540174005858', jacobian, 'unit-square NDC area from explicitly floating projection'),
            ('N2', '0.000008000000759959', area, 'world area reported approximately'),
            ('N2', '0.000004155632533969', area*jacobian, 'NDC area reported approximately')):
        final = (RUNTIME / slot / 'consumer/PUBLIC_FINAL.txt').read_bytes().decode('utf-8')
        assert claim in final
        value = F(claim)
        numeric.append({'slot_id': slot, 'actual_final_numeric_excerpt': claim, 'independent_exact_reference': str(reference),
                        'reference_float': float(reference), 'signed_exact_residual': str(value-reference),
                        'absolute_residual': float(abs(value-reference)), 'relative_residual': float(abs(value-reference)/reference),
                        'interpretation': context, 'positive_area_conclusion_independently_proved': value > 0 and reference > 0,
                        'new_numeric_acceptance_threshold_introduced': False})
    records = []
    for slot in ORDER:
        final_path = RUNTIME / slot / 'consumer/PUBLIC_FINAL.txt'
        answer = read(final_path)
        errors = schema_errors(answer, schema, schema)
        assert not errors, (slot, errors)
        current = next(row for row in saved['records'] if row['slot_id'] == slot)
        frames = {row['ref']: row for row in current['summary']['frames']}
        views = []
        for region in answer['regions']:
            identity = source_id(region)
            target = targets[identity]
            for row in region.get('view_evidence', []):
                frame = frames[row['frame_ref']]
                assert frame['view_name'] == row['view_name']
                pixels = frame['regions'][identity]
                status = target['geometric_classifications'][row['view_name']]
                checks = {}
                for key in ('surface_pixels', 'boundary_pixels'):
                    if key in row:
                        checks[key] = row[key] == pixels[key]
                if 'orientation' in row:
                    expected = 'front_facing' if pixels['front_facing'] else status
                    checks['orientation'] = row['orientation'] == expected
                if 'geometrically_complete' in row:
                    checks['geometry'] = row['geometrically_complete'] is pixels['geometry_complete']
                if 'complete_readable' in row:
                    checks['complete_readable'] = row['complete_readable'] is pixels['complete_readable']
                if 'pixel_thresholds_pass' in row:
                    checks['pixel_thresholds_pass'] = row['pixel_thresholds_pass'] is (pixels['surface_pixels'] >= 16 and pixels['boundary_pixels'] >= 4)
                frustum = projected_bounds(target['boundary_vertices_world_m'], poses[row['view_name']])
                if 'entire_region_inside_frustum' in row:
                    checks['entire_frustum'] = row['entire_region_inside_frustum'] is frustum['inside']
                if 'occluded_boundary_vertices_world_m' in row:
                    expected = {(F(1), F(0), F(0)), (F(1), d, F(0)), (F(1), F(0), d)}
                    checks['occluded_world_boundary'] = {tuple(F(value) for value in point) for point in row['occluded_boundary_vertices_world_m']} == expected
                numeric_claims = []
                for key in ('occluded_fraction', 'occluded_area_world_m2'):
                    if key in row:
                        reference = area if identity == 'region_0' else F(0)
                        actual = F(row[key])
                        numeric_claims.append({'field': key, 'actual': row[key], 'independent_exact_reference': str(reference),
                                               'signed_exact_residual': str(actual-reference), 'absolute_residual': float(abs(actual-reference)),
                                               'context': 'Explicit floating geometry approximation; no new pass threshold added.'})
                dot = None
                if 'normal_dot_direction_to_camera' in row:
                    direction = truth['directions'][row['view_name']]
                    expected = sum(float(n)*axis for n, axis in zip(target['unit_normal_world'], direction))/math.hypot(*direction)
                    dot = {'actual': row['normal_dot_direction_to_camera'], 'independent_unit_direction_dot': expected,
                           'absolute_residual': abs(row['normal_dot_direction_to_camera']-expected)}
                assert all(checks.values()), (slot, identity, row['view_name'], checks)
                views.append({'source_region': identity, 'view': row['view_name'], 'actual_view_evidence': row,
                              'exact_checks': checks, 'frustum': frustum, 'approximate_numeric_claims': numeric_claims, 'unit_direction_dot': dot})
        records.append({'slot_id': slot, 'raw_final_sha256': sha(final_path), 'frozen_public_schema_valid': True,
                        'schema_errors': errors, 'extra_view_evidence_records': views,
                        'raw_null_reason_is_schema_permitted': True,
                        'explicit_notes_reason_handled_by_sealed_independent_semantic_review': True})
    assert sum(len(row['extra_view_evidence_records']) for row in records) == 12
    report = {'schema': 'target-task-consumption-public-schema-extra-claims-v1', 'passed_checked_scope': True,
              'schema_sha256': sha(HERE / 'inputs/ANSWER_SCHEMA.json'),
              'schema_validator_scope': 'All assertion keywords in this fixed schema, with JSON type distinctions and default additional-properties behavior. No package was installed.',
              'records': records, 'N3_extra_view_records_checked': 12,
              'Near_world_area_exact': str(area), 'LEFT_NDC_jacobian_exact': str(jacobian),
              'LEFT_NDC_occlusion_area_exact': str(area*jacobian), 'near_numeric_claim_records': numeric,
              'approximation_scope': 'Area and dot results remain explicitly floating approximations with exact residuals reported. Frozen exact source-set/center/extent and normal rules are unchanged.',
              'semantic_review_sha256': sha(HERE / 'admin/SEMANTIC_REVIEW.json'),
              'saved_source_frame_review_sha256': sha(HERE / 'admin/SAVED_REVIEW_01.json'),
              'source_sha256': sha(Path(__file__)), 'sealed_quality_changed': False,
              'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0}
    with (HERE / 'admin/PUBLIC_SCHEMA_AND_EXTRAS.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed_checked_scope': True, 'schema_valid_finals': 6, 'extra_view_records': 12, 'new_actual_calls': 0}))


if __name__ == '__main__':
    main()
