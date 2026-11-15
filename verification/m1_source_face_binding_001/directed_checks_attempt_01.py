"""Directed saved-result and independent-fixture source-face acceptance."""

import argparse
import array
import ast
import base64
import bisect
import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time
import traceback
from typing import Any
import zipfile
import zlib


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD_ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe')
SAVED = {
    'qualification_QP': Path('D:/he_occluded_transfer_001/preparation/QP/o/product_call_01/SERVICE_RESULT.json'),
    'formal_P1': Path('D:/he_occluded_transfer_001/formal/P1/o/product_call_01/SERVICE_RESULT.json'),
}
FUNCTIONS = (
    '_project_active_patch_support', '_valid_region_location_vector',
    '_valid_visible_pixel_location', '_project_active_inspection',
    'project_active_observation_brief', '_active_observation_content', '_tool_result',
)
FIELD = 'source_triangle_index_ranges'
SEMANTICS = 'source_triangle_index_ranges_semantics'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2)
        stream.write('\n')


def functions(path, names):
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in selected} != set(names):
        raise ValueError('source_function_not_found')
    return ast.Module(body=selected, type_ignores=[])


def projection_module(root):
    path = root / 'human_eye_plugin/live_spatial_mcp.py'
    telemetry = []
    namespace = dict(copy=copy, json=json, math=math, Fraction=Fraction, Path=Path,
                     base64=base64, hashlib=hashlib, time=time, struct=struct, zlib=zlib,
                     Any=Any, record_image_artifact=lambda *args, **kwargs: telemetry.append([args, kwargs]))
    png_source = root / 'human_eye_plugin/native_observation.py'
    exec(compile(functions(png_source, ('_require', '_public_native_png')), str(png_source), 'exec'), namespace)
    exec(compile(functions(path, FUNCTIONS), str(path), 'exec'), namespace)
    return namespace, telemetry


def rows(table):
    return [dict(zip(table['columns'], values)) for values in table['rows']]


def expand(ranges):
    result = []
    previous = -2
    for start, stop in ranges:
        if type(start) is not int or type(stop) is not int or start < 0 or stop < start or start <= previous + 1:
            raise ValueError('noncanonical_inclusive_ranges')
        result.extend(range(start, stop + 1))
        previous = stop
    return result


def restore_old_fields(brief, old_schema):
    result = copy.deepcopy(brief)
    result['schema'] = old_schema
    result.pop(SEMANTICS, None)
    table = result.get('regions')
    if table is not None and FIELD in table['columns']:
        position = table['columns'].index(FIELD)
        table['columns'].pop(position)
        for values in table['rows']:
            values.pop(position)
    return result


def binding_key(brief):
    return hashlib.sha256(json.dumps(brief['binding'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def inverse(brief):
    """Consumer example uses only binding, object index and inclusive ranges."""
    bound = binding_key(brief)
    result = {}
    for region in rows(brief['regions']):
        for face in expand(region[FIELD]):
            key = (bound, region['object_index'], face)
            if key in result:
                raise ValueError('duplicate_current_source_owner')
            result[key] = region['roi_id']
    return result


def independent_fixture():
    vertices = [[0,0,0],[1,0,0],[2,0,0],[0,1,0],[1,1,0],[2,1,0],
                [3,0,1],[4,0,1],[4,1,1],[3,1,1],
                [0,3,2],[2,3,2],[2,3.5,2],[.5,3.5,2],[.5,5,2],[0,5,2]]
    faces = [[0,1,4],[10,11,13],[6,7,8],[0,4,3],[11,12,13],
             [10,13,15],[1,2,5],[6,8,9],[13,14,15],[1,5,4]]
    geometry = {'objects': [
        {'name': 'IndependentMultiPatch', 'vertices': vertices, 'triangles': faces},
        {'name': 'IndependentZeroFaceIndex', 'vertices': [[10,0,0],[11,0,0],[11,1,0],[10,1,0]],
         'triangles': [[0,1,2],[0,2,3]]},
        {'name': 'UnsupportedTriangle', 'vertices': [[-5,0,0],[-4,0,0],[-5,1,0]], 'triangles': [[0,1,2]]},
        {'name': 'EmptyRepresentationBoundary', 'vertices': [], 'triangles': []},
    ]}
    objects = [dict(object_index=i, object_name=obj['name'], host_id='independent-host-' + str(i),
                    instance_id='independent-instance-' + str(i)) for i, obj in enumerate(geometry['objects'])]
    assignments = [('subdivided-four', 0, [0,3,6,9]), ('second-same-object', 0, [2,7]), ('zero-face', 1, [0,1])]
    regions = [dict(objects[index], roi_id=identity, status='unknown', reason='finite_camera_pool_uncovered')
               for identity, index, faces in assignments]
    mapping = [dict(roi_id=identity, object_index=index, triangle_indices=faces)
               for identity, index, faces in assignments]
    supported = {0: [0,2,3,6,7,9], 1: [0,1], 2: [], 3: []}
    rejected = {0: [[1,4,5,8]], 1: [], 2: [[0]], 3: []}
    object_support = []
    for i, obj in enumerate(objects):
        unknown = rejected[i]
        object_support.append(dict(obj, source_triangle_count=len(geometry['objects'][i]['triangles']),
            supported_triangle_count=len(supported[i]), supported_triangle_indices=supported[i],
            unsupported_triangle_count=sum(len(part) for part in unknown),
            unsupported_components=[dict(triangle_indices=part, reason='nonrectangular_component', status='unknown') for part in unknown],
            support_status='fully_supported' if supported[i] and not unknown else 'partially_supported' if supported[i] else 'unsupported'))
    patch = dict(schema='active-patch-support-v1', triangle_index_scope='zero_based_object_local_source_triangles',
                 all_triangles_participate_in_occlusion=True, objects=object_support, regions=mapping)
    value = dict(status='unknown', result_kind='active_observation', observation_status='unobserved',
        session_id='independent-source-fixture', read_only=True, execution_authority=False,
        binding=dict(scene_revision='independent-source-v1', document_epoch='independent-document',
            capture_scope='complete_scene_meshes', unit='m', coordinate_frame='world', source='blender',
            capture_state=None, source_binding_sha256='independent-source', geometry_identity='independent-geometry',
            camera_identity='independent-cameras', binding_sha256='independent-binding', runtime_source_sha256='independent-runtime',
            source_status='loaded_generation', disk_status='disk_not_checked', source_check_scope='bound_generation_identity', objects=objects),
        facts=dict(scene_identity='independent-geometry', candidate_identity='independent-cameras', regions=regions,
            observations=[], coverage=dict(covered_roi_ids=[], unresolved_roi_ids=[r['roi_id'] for r in regions],
                candidate_pool_uncovered_roi_ids=[r['roi_id'] for r in regions], scope='independent representation fixture',
                state_updates=0, observed_views=[]),
            scope=dict(capture_object_count=len(objects), supported_roi_object_count=2,
                domain='connected planar rectangles', all_objects_participate_in_occlusion=True,
                objects_without_supported_roi=[dict(obj, status='unknown') for obj in objects[2:]], patch_support=patch),
            image_delivery_scope='local_core_validation'), frames=[],
        image_delivery=dict(local_verified_image_count=0, mcp_content_constructed_image_count=0,
                            consumer_read_status='unconfirmed', frame_reuses=0, new_raster_attempts=0))
    return geometry, value


def reorder_objects(geometry, value):
    result, geo = copy.deepcopy(value), copy.deepcopy(geometry)
    order = [1,0,3,2]
    changes = {old: new for new, old in enumerate(order)}
    geo['objects'] = [geo['objects'][i] for i in order]
    result['binding']['objects'] = [result['binding']['objects'][i] for i in order]
    support = result['facts']['scope']['patch_support']
    support['objects'] = [support['objects'][i] for i in order]
    for collection in (result['binding']['objects'], support['objects'], support['regions'],
                       result['facts']['regions'], result['facts']['scope']['objects_without_supported_roi']):
        for item in collection:
            item['object_index'] = changes[item['object_index']]
    result['binding']['binding_sha256'] += '-objects-reordered'
    return geo, result


def reorder_faces(geometry, value):
    result, geo = copy.deepcopy(value), copy.deepcopy(geometry)
    support = result['facts']['scope']['patch_support']
    for obj_index, obj in enumerate(geo['objects']):
        size = len(obj['triangles'])
        order = [size - 1] + list(range(size - 1)) if size else []
        change = {old: new for new, old in enumerate(order)}
        obj['triangles'] = [obj['triangles'][i] for i in order]
        source = support['objects'][obj_index]
        source['supported_triangle_indices'] = [change[i] for i in source['supported_triangle_indices']]
        for component in source['unsupported_components']:
            component['triangle_indices'] = [change[i] for i in component['triangle_indices']]
        for region in support['regions']:
            if region['object_index'] == obj_index:
                region['triangle_indices'] = [change[i] for i in region['triangle_indices']]
    result['binding']['binding_sha256'] += '-faces-reordered'
    return geo, result


def npy(archive, name):
    raw = archive.read(name + '.npy')
    if raw[:6] != b'\x93NUMPY':
        raise ValueError('actual_npy_magic')
    width = 2 if raw[6] == 1 else 4
    size = int.from_bytes(raw[8:8 + width], 'little')
    header = ast.literal_eval(raw[8 + width:8 + width + size].decode('latin1'))
    if header['fortran_order'] or header['descr'] not in ('<i4', '=i4', '<i8', '=i8'):
        raise ValueError('actual_npy_integer_layout')
    values = array.array('i' if header['descr'].endswith('4') else 'q')
    values.frombytes(raw[8 + width + size:])
    if sys.byteorder != 'little':
        values.byteswap()
    return values


class Checks:
    def __init__(self, output, old, new):
        self.output, self.old, self.new = output, old, new
        self.records = []
        self.assertions = 0
        self.inverse_pixel_counts = []
        self.projection_calls = 0

    def require(self, condition, name):
        self.assertions += 1
        if not condition:
            raise AssertionError(name)

    def project(self, value, role='new'):
        self.projection_calls += 1
        return (self.new if role == 'new' else self.old)['project_active_observation_brief'](value)

    def run(self, name, operation):
        before = self.assertions
        try:
            details = operation()
            self.records.append(dict(name=name, passed=True, assertions=self.assertions-before, details=details))
        except Exception as error:
            self.records.append(dict(name=name, passed=False, assertions=self.assertions-before,
                error=dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())))

    def mapping(self, value):
        original = copy.deepcopy(value)
        baseline, candidate = self.project(value, 'old'), self.project(value)
        self.require(baseline is not None and candidate is not None, 'both_projection_supported')
        self.require(candidate['schema'] == 'active-observation-brief-v5', 'new_capability_schema_v5')
        self.require(candidate[SEMANTICS] == 'zero_based_object_local_inclusive; object_index_in_objects; scoped_to_this_binding', 'precise_semantics')
        self.require(restore_old_fields(candidate, baseline['schema']) == baseline, 'all_old_public_fields_equal')
        source = value['facts']['scope']['patch_support']['regions']
        public = rows(candidate['regions'])
        self.require(len(public) == len(source), 'source_region_denominator')
        for declared, actual in zip(source, public):
            self.require(actual['roi_id'] == declared['roi_id'] and actual['object_index'] == declared['object_index'], 'region_identity')
            self.require(expand(actual[FIELD]) == sorted(declared['triangle_indices']), 'exact_object_local_source_set')
            self.require(actual['triangle_count'] == len(declared['triangle_indices']), 'region_triangle_count')
        lookup = inverse(candidate)
        expected = {(binding_key(candidate), r['object_index'], face): r['roi_id'] for r in source for face in r['triangle_indices']}
        self.require(lookup == expected, 'geometry_free_inverse')
        self.require(value == original, 'projection_input_unchanged')
        return dict(regions=len(public), supported_triangles=len(lookup), old_schema=baseline['schema'],
                    default_added_json_bytes=len(json.dumps(candidate, separators=(',', ':'), ensure_ascii=False).encode())-
                    len(json.dumps(baseline, separators=(',', ':'), ensure_ascii=False).encode()))

    def geometry(self, geometry, value):
        source = value['facts']['scope']['patch_support']
        for region in source['regions']:
            obj = geometry['objects'][region['object_index']]
            points = [[tuple(Fraction(str(x)) for x in obj['vertices'][i]) for i in obj['triangles'][face]]
                      for face in region['triangle_indices']]
            area = sum(abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2 for a,b,c in points)
            vertices = {p for triangle in points for p in triangle}
            minimum = [min(p[k] for p in vertices) for k in range(3)]
            maximum = [max(p[k] for p in vertices) for k in range(3)]
            self.require(minimum[2] == maximum[2], 'independent_rectangle_coplanar')
            self.require(area == (maximum[0]-minimum[0])*(maximum[1]-minimum[1]), 'independent_exact_rectangle_area')
        self.require(len(source['regions'][0]['triangle_indices']) == 4, 'independent_four_triangle_rectangle')
        self.require(len(source['regions']) == 3 and source['regions'][0]['object_index'] == source['regions'][1]['object_index'], 'independent_multiple_regions_one_object')
        return {'source_triangles': sum(len(o['triangles']) for o in geometry['objects']), 'supported_triangles': 8,
                'unsupported_triangles': 5, 'subdivision_triangles': 4}

    def saved_pixels(self, value):
        candidate = self.project(value)
        lookup = inverse(candidate)
        roi_indices = {r['roi_id']: i for i,r in enumerate(rows(candidate['regions']))}
        bound = binding_key(candidate)
        checked = 0
        for frame in value['frames']:
            path = Path(frame['arrays_path'])
            self.require(sha(path) == frame['arrays_sha256'], 'saved_npz_hash')
            with zipfile.ZipFile(path) as archive:
                offsets = npy(archive, 'face_patch_offsets')
                patch_ids = npy(archive, 'face_patch_ids')
                raw = npy(archive, 'triangle_ids')
                owners = npy(archive, 'owners')
                patch_owners = npy(archive, 'patch_owners')
            self.require(len(raw) == len(owners) == len(patch_owners) == 512*512, 'saved_owner_dimensions')
            expected_offsets = [0]
            for obj in value['facts']['scope']['patch_support']['objects']:
                expected_offsets.append(expected_offsets[-1] + obj['source_triangle_count'])
            self.require(list(offsets) == expected_offsets, 'raw_existing_global_offsets')
            self.require(list(frame['patch_roi_ids']) == [r['roi_id'] for r in rows(candidate['regions'])], 'actual_raw_patch_order')
            for global_face, patch in enumerate(patch_ids):
                obj = bisect.bisect_right(offsets, global_face) - 1
                roi = lookup.get((bound, obj, global_face-offsets[obj]))
                self.require((roi_indices[roi] if roi is not None else -1) == patch, 'all_raw_source_face_patch_membership')
            errors = 0
            for global_face, owner, patch in zip(raw, owners, patch_owners):
                if global_face < 0:
                    errors += int(global_face != -1 or owner != -1 or patch != -1)
                    continue
                obj = bisect.bisect_right(offsets, global_face) - 1
                roi = lookup.get((bound, obj, global_face-offsets[obj]))
                errors += int(owner != obj or patch != (roi_indices[roi] if roi is not None else -1))
            self.require(errors == 0, 'all_saved_pixels_geometry_free_inverse')
            checked += len(raw)
        self.inverse_pixel_counts.append(checked)
        return {'actual_saved_frames': len(value['frames']), 'checked_saved_pixel_locations': checked, 'new_rasters': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(HERE)
    output.mkdir(parents=True, exist_ok=False)
    before = {str(p): sha(p) for p in SAVED.values()}
    old, old_telemetry = projection_module(OLD_ROOT)
    new, new_telemetry = projection_module(ROOT)
    checks = Checks(output, old, new)
    saved_values = {name: read(path) for name, path in SAVED.items()}
    fixture_geometry, fixture = independent_fixture()
    fixtures = {'original': (fixture_geometry, fixture), 'object_reorder': reorder_objects(fixture_geometry, fixture),
                'face_reorder': reorder_faces(fixture_geometry, fixture)}
    reordered = copy.deepcopy(fixture)
    reordered['facts']['regions'].reverse()
    reordered['facts']['scope']['patch_support']['regions'].reverse()
    reordered['binding']['binding_sha256'] += '-region-order'
    fixtures['region_order'] = (copy.deepcopy(fixture_geometry), reordered)
    save(output / 'INDEPENDENT_FIXTURES.json', {key: {'source_geometry': geom, 'full_value': value} for key,(geom,value) in fixtures.items()})
    checks.run('D01_independent_fixture_geometry', lambda: checks.geometry(fixture_geometry, fixture))
    for name, value in saved_values.items():
        checks.run('D02_saved_mapping_' + name, lambda value=value: checks.mapping(value))
        checks.run('D03_saved_raw_inverse_' + name, lambda value=value: checks.saved_pixels(value))
    for name, (geom, value) in fixtures.items():
        checks.run('D04_fixture_mapping_' + name, lambda value=value: checks.mapping(value))

    def cross_binding():
        first = inverse(checks.project(fixture))
        second = inverse(checks.project(fixtures['face_reorder'][1]))
        first_binding = next(iter(first))[0]
        second_binding = next(iter(second))[0]
        checks.require(first_binding != second_binding, 'different_binding_identity')
        checks.require(first[(first_binding,0,3)] != second[(second_binding,0,3)], 'same_local_index_different_region')
        checks.require(not set(first).intersection(second), 'binding_scoped_keys_do_not_merge')
        return {'same_local_key': [0,3], 'distinct_bound_face_entries': len(first)+len(second)}
    checks.run('D05_cross_binding_scope', cross_binding)

    def legacy():
        for value in (fixture, saved_values['qualification_QP']):
            value = copy.deepcopy(value)
            value['facts']['scope'].pop('patch_support')
            expected, actual = checks.project(value, 'old'), checks.project(value)
            checks.require(actual == expected and actual is not None, 'legacy_projection_unchanged')
            checks.require(SEMANTICS not in actual and FIELD not in actual['regions']['columns'], 'no_new_capability_without_mapping')
        return {'legacy_versions_checked': ['v1', 'v4']}
    checks.run('D06_legacy_no_mapping', legacy)

    def invalid():
        mutations = []
        def control(name, change):
            value = copy.deepcopy(fixture)
            change(value['facts']['scope']['patch_support'])
            mutations.append((name, value))
        control('missing_region', lambda p: p['regions'].pop())
        control('wrong_roi', lambda p: p['regions'][0].update(roi_id='wrong'))
        control('wrong_object', lambda p: p['regions'][0].update(object_index=1))
        control('boolean_object', lambda p: p['regions'][0].update(object_index=False))
        control('duplicate_face', lambda p: p['regions'][0].update(triangle_indices=[0,0]))
        control('overlap', lambda p: p['regions'][1].update(triangle_indices=[0,2]))
        control('boolean_face', lambda p: p['regions'][0].update(triangle_indices=[False,3,6,9]))
        control('negative_face', lambda p: p['regions'][0].update(triangle_indices=[-1,3,6,9]))
        control('out_of_range', lambda p: p['regions'][0].update(triangle_indices=[0,3,6,100]))
        control('wrong_source_total', lambda p: p['objects'][0].update(source_triangle_count=11))
        control('wrong_supported_partition', lambda p: p['objects'][0]['supported_triangle_indices'].pop())
        control('unsupported_overlap', lambda p: p['objects'][0]['unsupported_components'][0].update(triangle_indices=[0,1,4,5,8]))
        for name, value in mutations:
            checks.require(checks.project(value, 'old') is None and checks.project(value) is None, 'retained_rejection_' + name)
        save(output / 'INVALID_CONTROLS.json', {name: value for name,value in mutations})
        return {'independent_negative_controls': len(mutations), 'all_old_failure_paths_retained': True}
    checks.run('D07_invalid_mapping_existing_failure', invalid)

    def alias_independence():
        value = copy.deepcopy(fixture)
        before_value = copy.deepcopy(value)
        first = checks.project(value)
        position = first['regions']['columns'].index(FIELD)
        first['regions']['rows'][0][position][0][0] = 999
        checks.require(value == before_value, 'public_ranges_do_not_alias_input')
        second = checks.project(value)
        checks.require(expand(second['regions']['rows'][0][position]) == [0,3,6,9], 'later_response_owns_ranges')
        return {'new_observation_calls': 0}
    checks.run('D08_input_and_output_independence', alias_independence)

    def content():
        value = saved_values['qualification_QP']
        original = copy.deepcopy(value)
        calls = []
        for detail in (None, 'full'):
            envelopes = []
            for role, namespace in (('old', old), ('new', new)):
                audit = {}
                envelope = namespace['_tool_result'](value, is_error=False, response_detail=detail, active_delivery_audit=audit)
                envelopes.append(envelope)
                calls.append(dict(role=role, response_detail=detail, audit=audit))
            checks.require(envelopes[0]['content'][1:] == envelopes[1]['content'][1:], 'same_public_image_blocks_' + str(detail))
            checks.require(envelopes[0]['isError'] == envelopes[1]['isError'] is False, 'same_content_success')
            if detail == 'full':
                checks.require(envelopes[0] == envelopes[1], 'full_response_byte_values_unchanged')
            else:
                old_text, new_text = [json.loads(envelope['content'][0]['text']) for envelope in envelopes]
                checks.require(restore_old_fields(new_text, old_text['schema']) == old_text, 'default_nonbinding_fields_unchanged')
        checks.require(value == original, 'content_input_unchanged')
        checks.require(all(call['audit']['native_blocks_constructed'] == len(value['frames']) for call in calls), 'same_image_construction_count')
        save(output / 'ENCODING_AUDITS.json', calls)
        return {'saved_PNG_encoding_calls': len(calls), 'encoded_image_blocks': len(calls)*len(value['frames']),
                'actual_new_rasters': 0, 'historical_raster_metrics_are_not_new_calls': True}
    checks.run('D09_default_full_images_and_cache_work', content)

    def source_scope():
        old_tree = ast.parse((OLD_ROOT/'human_eye_plugin/live_spatial_mcp.py').read_text(encoding='utf-8'))
        new_tree = ast.parse((ROOT/'human_eye_plugin/live_spatial_mcp.py').read_text(encoding='utf-8'))
        before_functions = {node.name: ast.dump(node, include_attributes=False) for node in old_tree.body if isinstance(node, ast.FunctionDef)}
        after_functions = {node.name: ast.dump(node, include_attributes=False) for node in new_tree.body if isinstance(node, ast.FunctionDef)}
        changed = [name for name in sorted(set(before_functions)|set(after_functions)) if before_functions.get(name) != after_functions.get(name)]
        checks.require(changed == ['_project_active_patch_support','project_active_observation_brief'], 'only_two_projection_functions_changed')
        checks.require(before_functions['_active_observation_content'] == after_functions['_active_observation_content'], 'image_encoder_and_cache_accounting_source_unchanged')
        return {'changed_functions': changed, 'new_source_preparation_or_solver_calls': 0}
    checks.run('D10_projection_only_source_change', source_scope)
    after = {str(p): sha(p) for p in SAVED.values()}
    checks.require(before == after, 'saved_service_results_unchanged')
    result = dict(schema='source-face-binding-directed-acceptance-v1', passed=all(r['passed'] for r in checks.records),
        logical_case_count=len(checks.records), passed_cases=sum(r['passed'] for r in checks.records),
        assertion_count=checks.assertions, checks=checks.records,
        source_sha256=dict(old_live_spatial_mcp=sha(OLD_ROOT/'human_eye_plugin/live_spatial_mcp.py'),
                           candidate_live_spatial_mcp=sha(ROOT/'human_eye_plugin/live_spatial_mcp.py'), runner=sha(__file__)),
        saved_service_inputs_sha256=before, saved_inputs_unchanged=before == after,
        source_geometry_fixture='INDEPENDENT_FIXTURES.json', source_projection_calls=checks.projection_calls,
        saved_raw_pixel_locations_checked=sum(checks.inverse_pixel_counts),
        new_observation_calls=0, new_rasters=0, new_geometry_preparation_or_solver_calls=0, model_calls=0,
        loaded_source_scope='AST-extracted original projection/content functions and original PNG validation. Only telemetry sink substituted.',
        telemetry_counts={'old': len(old_telemetry), 'new': len(new_telemetry)},
        reviewer_association='Acceptance author created the independent fixture and source-only runner. Product implementation written by a separate agent.',
        before_publication_ns=time.perf_counter_ns())
    save(output / 'RESULT.json', result)
    print(json.dumps({'passed': result['passed'], 'logical_cases': result['logical_case_count'],
                      'assertions': checks.assertions, 'failed': [r['name'] for r in checks.records if not r['passed']]}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
