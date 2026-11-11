"""Saved-data correctness checks, with no timing or geometry solver calls.

The root executes this verifier once. Expected values come from raw source
files, exact signed-coordinate identities and explicit field selections.
"""
import argparse
import copy
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
BASE_SHA = '9248662417e6729351981fe2fdefb21f1939aca49ace435940aa5f33698a5235'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encoded = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True,
                                  separators=(',', ':'), allow_nan=False).encode('utf8')
checks = []


def check(condition, label):
    checks.append({'check': label, 'passed': bool(condition)})


def same(a, b):
    return encoded(a) == encoded(b)


def read(path):
    return json.loads(path.read_bytes())


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def verify_saved_base(bundle, manifest):
    for key, item in manifest['base'].items():
        raw = (BATCH/item['path']).read_bytes()
        check(sha(raw) == item['sha256'] and len(raw) == item['bytes'], 'base.manifest_pin.'+key)
    binding = read(BATCH/manifest['base']['source_binding']['path'])
    check(manifest['base']['bundle']['sha256'] == BASE_SHA == binding['bundle_sha256'], 'base.bundle_pin')
    for relative, digest in binding['source_paths_sha256'].items():
        check(sha((ROOT/relative).read_bytes()) == digest, 'base.original_pin.'+relative)
    initial_path = next(ROOT/path for path in binding['source_paths_sha256'] if path.endswith('/INITIAL.json'))
    response_path = next(ROOT/path for path in binding['source_paths_sha256'] if path.endswith('/tool_02/RESPONSE.json'))
    frame_path = next(ROOT/path for path in binding['source_paths_sha256'] if path.endswith('/native/call_3/stdout.txt'))
    initial = read(initial_path)
    expected_objects = []
    for index, item in enumerate(initial['objects']):
        matrix = item['matrix_world']
        world = [[(sum(matrix[axis][k]*point[k] for k in range(3))+matrix[axis][3])
                  * initial['unit_scale_m'] for axis in range(3)] for point in item['vertices_local']]
        expected_objects.append({'object_id': 'snapshot:'+str(index), 'name': item['name'],
                                 'vertices_world': world, 'faces': item['faces'], 'face_kind': 'source_polygons'})
    body = json.loads(read(response_path)['result']['content'][0]['text'])
    frame = frame_path.read_text(encoding='utf8')
    marker = 'HUMAN_EYE_BLENDER_MCP:'
    check(frame.startswith(marker), 'base.exact_recorded_capture_frame_marker')
    packet = json.loads(frame[len(marker):])['result']
    check(packet['capture']['revision'] == body['context']['scene_revision'], 'base.actual_relation_capture_revision')
    check(same(packet['capture']['capture_state'], binding['actual_capture_state']), 'base.actual_capture_state')
    check(same(binding['actual_relation_context'], body['context']), 'base.original_context_retained')
    by_name = {item['name']: item for item in expected_objects}
    initial_by_name = {item['name']: item for item in initial['objects']}
    resources = {item['id']: item for item in packet['resources']}
    binding_by_name = {item['name']: item for item in binding['selected_geometry_binding']}
    check(len(packet['capture']['meshes']) == len(binding_by_name) == 4, 'base.four_actual_selected_meshes')
    for mesh in packet['capture']['meshes']:
        name, reference = mesh['name'], mesh['_scene_resource']
        resource = resources[reference['id']]
        original, selected = initial_by_name[name], binding_by_name[name]
        check(same(resource['vertices_local'], original['vertices_local']), 'base.actual_local_vertices.'+name)
        check(same(reference['matrix'], original['matrix_world'])
              and reference['scale'] == initial['unit_scale_m'], 'base.actual_pose_unit.'+name)
        check(mesh['object_id'] == selected['host_object_id']
              and by_name[name]['object_id'] == selected['offline_object_id'], 'base.actual_host_offline_ID_binding.'+name)
        check(same(resource['faces'], selected['captured_triangle_indices'])
              and all(len(face) == 3 for face in resource['faces']), 'base.actual_triangle_ordinal_binding.'+name)
        by_name[name]['faces'] = resource['faces']
        by_name[name]['face_kind'] = 'captured_triangles'
    check(same(bundle['objects'], expected_objects), 'base.saved_world_and_actual_capture_triangles_with_explicit_polygon_remainder')
    expected_relations = []
    for row in body['candidates']:
        facts = {field: {**body['measurement_contracts'].get(field, {}), **row[field]}
                 for field in ('closed_solid_relation', 'surface_proximity', 'separation_gap')}
        expected_relations.append({'target_id': by_name[body['target']['name']]['object_id'],
                                   'candidate_id': by_name[row['name']]['object_id'], 'facts': facts})
    check(same(bundle['relations'], expected_relations), 'base.original_three_facts_only_metadata_merged')
    for row in body['candidates']:
        evidence = row['closed_solid_relation'].get('local_evidence')
        if evidence is None:
            continue
        for side, name in enumerate((body['target']['name'], row['name'])):
            mesh = by_name[name]
            indices = mesh['faces'][evidence['triangle_indices'][side]]
            triangle = [mesh['vertices_world'][index] for index in indices]
            check(same(triangle, evidence['triangle_vertices_world_m'][side]), 'base.local_evidence_actual_triangle_source.'+name)
    check(bundle['unit'] == 'm' and bundle['coordinate_frame'] == 'world', 'base.world_metres')


def coordinate_paths(facts):
    paths = []
    if 'local_evidence' in facts['closed_solid_relation']:
        local = ('closed_solid_relation', 'local_evidence')
        paths.append((*local, 'point_world_m'))
        for triangle in range(2):
            for vertex in range(3):
                paths.append((*local, 'triangle_vertices_world_m', triangle, vertex))
    surface = facts['surface_proximity'].get('value')
    if surface is not None and 'nearest_witness' in surface:
        paths.extend(('surface_proximity', 'value', 'nearest_witness', key)
                     for key in ('a', 'b', 'direction_a_to_b'))
    return paths


def parent_at(value, path):
    for key in path[:-1]:
        value = value[key]
    return value, path[-1]


def verify_variants(base, manifest):
    base_folder = (BATCH/manifest['base']['bundle']['path']).parent
    fixtures = [('original', base, base_folder)]
    spec = read(HERE/'SPEC.json')
    check(manifest['SPEC_sha256'] == sha((HERE/'SPEC.json').read_bytes()), 'variants.frozen_spec_pin')
    check(manifest['generator_sha256'] == sha((HERE/'prepare_validation.py').read_bytes()), 'variants.generator_pin')
    check(len(manifest['variants']) == 3, 'variants.fixed_three')
    for record in manifest['variants']:
        for item in record['files']:
            raw = (BATCH/item['path']).read_bytes()
            check(sha(raw) == item['sha256'] and len(raw) == item['bytes'], 'variants.file_pin.'+item['path'])
        bundle_file = next(item for item in record['files'] if Path(item['path']).name == 'BUNDLE.json')
        folder = (BATCH/bundle_file['path']).parent
        bundle, derivation = read(folder/'BUNDLE.json'), read(folder/'DERIVATION.json')
        check(bundle['source']['base_bundle_sha256'] == BASE_SHA
              and same(bundle['source']['original_source'], base['source'])
              and bundle['source']['kind'] == 'offline_derived_fixture', record['name']+'.derived_source')
        before = {item['object_id']: item for item in base['objects']}
        after = {item['object_id']: item for item in bundle['objects']}
        check(len(after) == len(bundle['objects']), record['name']+'.unique_object_IDs')
        if record['name'] == 'renamed_ids_reordered':
            seed = spec['seed']
            rank = sorted(before, key=lambda key: sha((seed+'|id|'+key).encode('utf8')))
            identifiers = {old: 'offline-r-'+str(i+1).zfill(4) for i, old in enumerate(rank)}
            check(identifiers == derivation['identifier_map'], 'rename.independent_seed_ID_map')
            order = sorted(before, key=lambda key: sha((seed+'|order|'+key).encode('utf8')))
            check([item['object_id'] for item in bundle['objects']] == [identifiers[key] for key in order], 'rename.independent_storage_order')
            for key, old in before.items():
                expected = copy.deepcopy(old)
                expected['object_id'] = identifiers[key]
                expected['name'] = 'asset_'+sha((seed+'|name|'+key).encode('utf8'))[:12]
                check(same(after[identifiers[key]], expected), 'rename.geometry_name_ID.'+key)
            expected = copy.deepcopy(base['relations'])
            for row in expected:
                row['target_id'], row['candidate_id'] = identifiers[row['target_id']], identifiers[row['candidate_id']]
            check(same(bundle['relations'], expected), 'rename.only_pair_identifiers_changed')
        elif record['name'] == 'proper_rotation_z90':
            check(len(bundle['objects']) == len(base['objects'])
                  and len(bundle['relations']) == len(base['relations']), 'rotation.object_relation_counts')
            for key, old in before.items():
                check(same({field: value for field, value in after[key].items() if field != 'vertices_world'},
                           {field: value for field, value in old.items() if field != 'vertices_world'}), 'rotation.every_noncoordinate_object_field.'+key)
                check(len(after[key]['vertices_world']) == len(old['vertices_world']), 'rotation.vertex_count.'+key)
                for point, rotated in zip(old['vertices_world'], after[key]['vertices_world']):
                    a, b = [Q.from_float(x) for x in point], [Q.from_float(x) for x in rotated]
                    check(b == [-a[1], a[0], a[2]], 'rotation.exact_coordinate.'+key)
            for index, (old, new) in enumerate(zip(base['relations'], bundle['relations'])):
                restored = copy.deepcopy(new['facts'])
                for path in coordinate_paths(old['facts']):
                    original_parent, field = parent_at(old['facts'], path)
                    changed_parent, _ = parent_at(restored, path)
                    point, rotated = original_parent[field], changed_parent[field]
                    check(rotated is None if point is None else
                          [Q.from_float(float(x)) for x in rotated] ==
                          [-Q.from_float(float(point[1])), Q.from_float(float(point[0])), Q.from_float(float(point[2]))],
                          'rotation.explicit_fact_coordinate.'+str(index)+str(path))
                    changed_parent[field] = copy.deepcopy(point)
                check(same(restored, old['facts']), 'rotation.every_remaining_fact_unchanged.'+str(index))
                check((new['target_id'], new['candidate_id']) == (old['target_id'], old['candidate_id']), 'rotation.pair_order.'+str(index))
        else:
            check(len(after) == len(before)+1 and all(same(after[key], item) for key, item in before.items()), 'distractor.all_original_objects_retained')
            copied = before[base['relations'][0]['target_id']]
            added = after['offline-distractor-v1']
            check(same(added['faces'], copied['faces']) and added['face_kind'] == copied['face_kind'], 'distractor.same_polygon_shape')
            check(len(added['vertices_world']) == len(copied['vertices_world']), 'distractor.vertex_count')
            for source, changed in zip(copied['vertices_world'], added['vertices_world']):
                check([Q.from_float(x) for x in changed] ==
                      [Q.from_float(source[0])+2, Q.from_float(source[1]), Q.from_float(source[2])], 'distractor.exact_translation')
            check(same(bundle['relations'], base['relations']), 'distractor.no_new_relation_claims')
        identifiers = derivation['identifier_map'] if record['name'] == 'renamed_ids_reordered' else {key: key for key in before}
        for filename in ('REQUEST_PRIMARY.json', 'REQUEST_OPTIONAL_UNION.json'):
            expected_request = copy.deepcopy(read(base_folder/filename))
            expected_request['source'] = copy.deepcopy(bundle['source'])
            for row in expected_request['objects']:
                row['object_id'] = identifiers[row['object_id']]
            for row in expected_request['relation_pairs']:
                row['target_id'], row['candidate_id'] = identifiers[row['target_id']], identifiers[row['candidate_id']]
            check(same(read(folder/filename), expected_request), record['name']+'.request_selection_mapping.'+filename)
        fixtures.append((record['name'], bundle, folder))
    return fixtures


def expected_directory(bundle):
    objects, gaps = [], []
    for item in bundle['objects']:
        row = {'object_id': item['object_id'], 'name': item['name']}
        points = item.get('vertices_world')
        if points:
            row['aabb'] = {'min': [min(point[k] for point in points) for k in range(3)],
                           'max': [max(point[k] for point in points) for k in range(3)]}
        else:
            row['aabb'] = None
            gaps.append({'object_id': item['object_id'], 'reason': 'world_geometry_not_available'})
        objects.append(row)
    return {'status': 'partial' if gaps else 'observed', 'source': copy.deepcopy(bundle['source']),
            'unit': bundle['unit'], 'coordinate_frame': bundle['coordinate_frame'], 'objects': objects, 'gaps': gaps}


def expected_selection(bundle, request):
    result = {'status': 'observed', 'source': copy.deepcopy(bundle['source']), 'unit': bundle['unit'],
              'coordinate_frame': bundle['coordinate_frame'], 'objects': [], 'relations': [], 'gaps': []}
    if request['source'] != bundle['source']:
        result.update(status='unknown', gaps=[{'reason': 'source_mismatch'}])
        return result
    for selection in request.get('objects', []):
        matches = [item for item in bundle['objects'] if item['object_id'] == selection['object_id']]
        if not matches:
            result['gaps'].append({'object_id': selection['object_id'], 'reason': 'object_not_in_capture'})
            continue
        item = matches[0]
        row = {'object_id': item['object_id'], 'name': item['name']}
        for field in selection['fields']:
            if field in ('vertices_world', 'faces') and field in item:
                row[field] = copy.deepcopy(item[field])
                if field == 'faces': row['face_kind'] = item['face_kind']
            else:
                result['gaps'].append({'object_id': item['object_id'], 'field': field, 'reason': 'object_field_not_available'})
        result['objects'].append(row)
    for selection in request.get('relation_pairs', []):
        target, candidate = selection['target_id'], selection['candidate_id']
        matches = [item for item in bundle['relations'] if (item['target_id'], item['candidate_id']) == (target, candidate)]
        if not matches:
            result['gaps'].append({'target_id': target, 'candidate_id': candidate, 'reason': 'ordered_relation_not_in_capture'})
            continue
        row = {'target_id': target, 'candidate_id': candidate, 'facts': {}}
        for field in selection['fields']:
            if field in matches[0]['facts']: row['facts'][field] = copy.deepcopy(matches[0]['facts'][field])
            else: result['gaps'].append({'target_id': target, 'candidate_id': candidate, 'field': field, 'reason': 'relation_field_not_available'})
        result['relations'].append(row)
    if result['gaps']: result['status'] = 'partial'
    return result


def generic_cases(base, request, renamed):
    rows = []
    stale = copy.deepcopy(request); stale['source'] = {'kind': 'synthetic_stale_source'}
    rows.append(('source_mismatch', base, stale))
    missing = copy.deepcopy(request); missing['objects'].append({'object_id': 'unknown-object', 'fields': ['faces']})
    rows.append(('unknown_object', base, missing))
    field = copy.deepcopy(request); field['objects'][0]['fields'].append('unavailable_generic_field')
    rows.append(('unknown_object_field', base, field))
    reverse = copy.deepcopy(request); pair = reverse['relation_pairs'][0]; pair['target_id'], pair['candidate_id'] = pair['candidate_id'], pair['target_id']
    rows.append(('reverse_ordered_pair', base, reverse))
    fact = copy.deepcopy(request); fact['relation_pairs'][0]['fields'].append('unavailable_generic_fact')
    rows.append(('unknown_relation_field', base, fact))
    unknown = copy.deepcopy(base); unknown['relations'][0]['facts']['closed_solid_relation'] = {'status': 'unknown', 'value': None, 'reason': 'synthetic_recorded_unknown'}
    rows.append(('unknown_fact_retained', unknown, request))
    alias_request = {'source': renamed['source'], 'objects': [{'object_id': renamed['objects'][0]['name'], 'fields': ['faces']}], 'relation_pairs': []}
    rows.append(('name_is_not_object_ID', renamed, alias_request))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prototype', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('preserve_previous_validation')
    manifest = read(HERE/'MANIFEST.json')
    base = read(BATCH/manifest['base']['bundle']['path'])
    verify_saved_base(base, manifest)
    fixtures = verify_variants(base, manifest)
    external = []
    def forbidden(*args, **kwargs):
        external.append('process_or_socket')
        raise AssertionError('offline saved-data validation forbids external operations')
    with patch.object(subprocess, 'Popen', side_effect=forbidden), patch.object(socket, 'socket', side_effect=forbidden):
        candidate = module(args.prototype.resolve(), 'batch_candidate')
        native = module(HERE/'native_projection.py', 'batch_native')
        for name, bundle, folder in fixtures:
            before = encoded(bundle)
            for lane, implementation in (('prototype', candidate), ('native', native)):
                check(same(implementation.directory(bundle), expected_directory(bundle)), name+'.'+lane+'.directory_exact_source_fields')
                for filename in ('REQUEST_PRIMARY.json', 'REQUEST_OPTIONAL_UNION.json'):
                    request = read(folder/filename)
                    selected = implementation.selected_observation(bundle, request)
                    check(same(selected, expected_selection(bundle, request)), name+'.'+lane+'.'+filename+'.selected_exact_fields')
                    if selected['objects'] and 'vertices_world' in selected['objects'][0]:
                        selected['objects'][0]['vertices_world'][0][0] = 123456.0
                        check(same(implementation.selected_observation(bundle, request), expected_selection(bundle, request)), name+'.'+lane+'.detached_output')
            check(encoded(bundle) == before, name+'.retained_input_unchanged')
        renamed = fixtures[1][1]
        primary_request = read(BATCH/manifest['base']['request']['path'])
        for name, bundle, request in generic_cases(base, primary_request, renamed):
            for lane, implementation in (('prototype', candidate), ('native', native)):
                check(same(implementation.selected_observation(bundle, request), expected_selection(bundle, request)), 'generic.'+name+'.'+lane)
        missing = copy.deepcopy(base); missing['objects'][0].pop('vertices_world')
        for lane, implementation in (('prototype', candidate), ('native', native)):
            check(same(implementation.directory(missing), expected_directory(missing)), 'generic.missing_world_directory.'+lane)
        distractor = fixtures[-1][1]
        request = {'source': distractor['source'], 'objects': [{'object_id': 'offline-distractor-v1', 'fields': ['vertices_world', 'faces']}],
                   'relation_pairs': [{'target_id': distractor['relations'][0]['target_id'], 'candidate_id': 'offline-distractor-v1', 'fields': ['closed_solid_relation']}]}
        for lane, implementation in (('prototype', candidate), ('native', native)):
            check(same(implementation.selected_observation(distractor, request), expected_selection(distractor, request)), 'generic.distractor_has_no_invented_relation.'+lane)
    check(not external, 'external_operation_attempts_zero')
    check(not any(name.startswith('human_eye_plugin') or name.startswith('human_eye_module1_operators') for name in sys.modules), 'product_modules_not_imported')
    result = {'cycle_id': 'M4-BATCH-OBSERVATION-COVERAGE-001', 'passed': all(row['passed'] for row in checks),
              'check_count': len(checks), 'checks': checks, 'prototype_sha256': sha(args.prototype.read_bytes()),
              'native_sha256': sha((HERE/'native_projection.py').read_bytes()), 'verifier_sha256': sha(Path(__file__).read_bytes()),
              'manifest_sha256': sha((HERE/'MANIFEST.json').read_bytes()), 'fixture_count': len(fixtures),
              'offline_modules_imported': [str(args.prototype.resolve()), str(HERE/'native_projection.py')],
              'product_imports': 0, 'production_geometry_solves': 0, 'external_attempts': external,
              'performance_measurements': 0, 'model_consumers': 0, 'Blender_sessions': 0,
              'integration_gap': manifest['integration_scope']}
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'failures': sum(not row['passed'] for row in checks), 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
