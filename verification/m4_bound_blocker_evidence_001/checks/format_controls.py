"""Verify source-bound blocker formatting without starting Blender or a model."""

import argparse
from contextlib import ExitStack
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
PRIOR = V / 'm4_dense_region_brief_001'
REPLAY = PRIOR / 'checks/offline_controls.py'
BASELINE = PRIOR / 'install/PRODUCT_RUN_BINDING.json'
TRUTH = V / 'm4_dense_panel_sweep_001/truth/CURRENT_TRUTH.json'
TRUTH_SHA = 'd4d05b3ffb713331c4348852335b9d17ebfe9690c7013062d39b82bb8087700a'
BASE_SOURCE = '6e8663feb57b630048fe919141cfcabbae4ae2365df1f80da693382c360b65e8'
FORMATTER = 'human_eye_plugin/live_spatial_mcp.py'
MAX_BRIEF_BYTES = 10800
BLOCKED_REASON = 'positive_area_occlusion_all_front_views'
PACKET_KEY = 'blocker_evidence'
COLUMNS = ('region_index', 'view_name', 'blocker_object_index', 'source_triangle_index')
ARCHIVES = (
    ('dense', 'm4_dense_region_brief_001', 'QP',
     'd22eae5a40a75a8b6dda86fca05b16c48c09a4f1a030bbbe6b0cc46715e2b645', 1),
    ('cross21', 'm4_cross_scale_cold_frustum_001', 'B1',
     '7f94dc9f4a1d01d5b8b38064293887504b8025065a3e2e994370aea4a1f1a3b0', 2),
    ('assembly28', 'm4_cross_scale_pixel_evidence_001', 'P1',
     '0802bfd8968a14ceb9cb209b4378d27b3045acc61d9bede297d42dba29c5658e', 2),
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def read(path):
    return json.loads(Path(path).read_bytes())


def decoded(result):
    return json.loads(result['content'][0]['text'])


def replaced_body(result, body):
    return {**result, 'content': [{'type': 'text', 'text': json_text(body)}, *result['content'][1:]]}


def original_cases(replay, pins):
    cases = {}
    with ExitStack() as stack:
        for name, batch, slot, index, calls in ARCHIVES:
            archive = replay['Archive'](pins, stack, batch, slot, index)
            cold = archive.take(1)
            cases[name + '_brief'] = {**cold, 'fixture': name, 'kind': 'brief'}
            cases[name + '_default'] = {**cold, 'fixture': name, 'kind': 'brief', 'detail': None}
            cases[name + '_full'] = {**cold, 'fixture': name, 'kind': 'full', 'detail': 'full'}
            if calls == 2:
                hot = archive.take(2)
                require(not hot['producer']['frames'] and not hot['producer']['constructed_frames'] and
                        hot['work']['global_index_cache_hit'] is True and hot['work']['index_calls'] == 0,
                        'original_same_generation_prediction_is_not_index_hit/' + name)
                require(hot['producer']['binding'] == cold['producer']['binding'],
                        'original_hot_prediction_does_not_share_current_source_binding/' + name)
                cases[name + '_hot_full'] = {**hot, 'fixture': name, 'kind': 'full'}
                cases[name + '_hot_brief'] = {**hot, 'fixture': name, 'kind': 'brief', 'detail': 'brief'}
    cases['dense_region_error'] = {
        'producer': cases['dense_brief']['producer'], 'detail': 'brief', 'is_error': True, 'kind': 'legacy'}
    cases['plain_error'] = {
        'producer': {'status': 'failed', 'error': {'type': 'test'}}, 'detail': 'brief',
        'is_error': True, 'kind': 'legacy'}
    for name, path, checksum in replay['LEGACY_MODES']:
        producer = json.loads(pins.raw(path, checksum))
        for frame in producer['frames']:
            pins.raw(frame['image_path'], frame['image_sha256'])
            pins.raw(frame['arrays_path'], frame['arrays_sha256'])
        for detail in (None, 'brief', 'full'):
            cases[f'{name}_{detail or "default"}'] = {'producer': producer, 'detail': detail, 'kind': 'legacy'}
    return cases


def installed_roots(pins, candidate):
    a = json.loads(pins.raw(BASELINE))
    b = json.loads(pins.raw(candidate))
    require(a['source_sha256'] == BASE_SOURCE and a['source_sha256'] != b['source_sha256'] and
            len(a['source_manifest']) == len(b['source_manifest']) == 143, 'registered_a_b_identity')
    require(Path(a['dependency_root']).resolve() == Path(b['dependency_root']).resolve(),
            'same_isolated_dependencies')
    roots, checksums = [], []
    for item in (a, b):
        root = Path(item['install_root']).resolve()
        row, = [row for row in item['source_manifest'] if row['path'] == FORMATTER]
        pins.raw(root / FORMATTER, row['sha256'])
        roots.append(root)
        checksums.append(row['sha256'])
    require(len(set(roots)) == len(set(checksums)) == 2, 'different_isolated_formatters_required')
    return (a, b), roots, checksums


def apply_geometry(case, fixture):
    """Add only the source-bound exact hits verified by the separate geometry run."""
    result = deepcopy(case['producer'])
    binding = result['binding']
    task = result['facts']['region_task']
    region_indices = {item['roi_id']: i for i, item in enumerate(task['rows'])}
    keys = ('roi_id', 'view_name', 'blocker_object_index', 'source_triangle_index', 'triangle_geometry_id',
            'overlap_area_screen_exact')
    rows = []
    for witness in fixture['rows']:
        region = task['rows'][region_indices[witness['roi_id']]]
        expected_views = region['view_reasons'].get('positive_area_occlusion', [])
        require(region['status'] == 'unknown' and region['reason'] == BLOCKED_REASON and
                region['complete_witness'] is None and witness['view_name'] in expected_views,
                'verified_geometry_does_not_match_original_blocked_classification')
        blocker = binding['objects'][witness['blocker_object_index']]
        raw = {key: witness[key] for key in keys}
        raw.update(blocker_host_id=blocker['host_id'], blocker_instance_id=blocker['instance_id'])
        rows.append(raw)
    rows.sort(key=lambda row: (region_indices[row['roi_id']],
                              task['rows'][region_indices[row['roi_id']]]['view_reasons']
                              ['positive_area_occlusion'].index(row['view_name'])))
    require(bool(rows), 'empty_required_geometry_fixture')
    task[PACKET_KEY] = dict(scope_id='global', binding_sha256=binding['binding_sha256'],
                            source_binding_sha256=binding['source_binding_sha256'],
                            camera_identity=binding['camera_identity'], rows=rows)
    return {**case, 'producer': result}


def make_bad_cases(case, assembly):
    def task(value):
        return value['facts']['region_task']

    def packet(value):
        return task(value)[PACKET_KEY]

    def row(value):
        return packet(value)['rows'][0]

    def use_pixel_shortfall_roi(value):
        target, = [item for item in task(value)['rows'] if item['reason'] == 'pixel_evidence_insufficient']
        row(value)['roi_id'] = target['roi_id']

    def use_own_source_triangle(value):
        candidate = row(value)
        target, = [item for item in task(value)['rows'] if item['roi_id'] == candidate['roi_id']]
        obj = value['binding']['objects'][target['object_index']]
        candidate.update(blocker_object_index=target['object_index'],
                         source_triangle_index=target['source_triangle_indices'][0],
                         blocker_host_id=obj['host_id'], blocker_instance_id=obj['instance_id'])

    def lose_source_support_identity(value):
        index = row(value)['blocker_object_index']
        global_scope, = [item for item in value['scopes'] if item['scope_id'] == 'global']
        for facts in (value['facts'], global_scope['facts']):
            facts['scope']['patch_support']['objects'][index]['instance_id'] = 'stale'

    cases = {}
    for label, base, mutate in (
        ('wrong_public_parent_binding', case, lambda value: packet(value).update(binding_sha256='stale')),
        ('wrong_public_source_binding', case, lambda value: packet(value).update(source_binding_sha256='stale')),
        ('wrong_public_camera_binding', case, lambda value: packet(value).update(camera_identity='stale')),
        ('wrong_scope', case, lambda value: packet(value).update(scope_id='local')),
        ('wrong_blocker_host', case, lambda value: row(value).update(blocker_host_id='stale')),
        ('wrong_blocker_instance', case, lambda value: row(value).update(blocker_instance_id='stale')),
        ('wrong_current_source_support', case, lose_source_support_identity),
        ('out_of_bounds_object', case, lambda value: row(value).update(blocker_object_index=len(value['binding']['objects']))),
        ('out_of_bounds_source_triangle', case, lambda value: row(value).update(source_triangle_index=10**8)),
        ('negative_source_triangle', case, lambda value: row(value).update(source_triangle_index=-1)),
        ('boolean_source_triangle', case, lambda value: row(value).update(source_triangle_index=False)),
        ('wrong_region', case, lambda value: row(value).update(roi_id='unknown')),
        ('non_occluding_direction', case, lambda value: row(value).update(view_name='TOP')),
        ('nonpositive_overlap', case, lambda value: row(value).update(overlap_area_screen_exact='0')),
        ('self_source_triangle', case, use_own_source_triangle),
        ('malformed_triangle_geometry_digest', case, lambda value: row(value).update(triangle_geometry_id='stale')),
        ('duplicate_direction', case, lambda value: packet(value)['rows'].append(deepcopy(row(value)))),
        ('reordered_directions', assembly, lambda value: packet(value)['rows'].reverse()),
        ('pixel_shortfall_cannot_receive_blocker', assembly, use_pixel_shortfall_roi),
    ):
        value = deepcopy(base['producer'])
        mutate(value)
        cases[label] = {'producer': value, 'detail': 'brief'}
    cases['bad_full_binding_rejected'] = {**cases['wrong_public_source_binding'], 'detail': 'full'}
    return cases


def check_brief(old, new, source, replay, case):
    old_body, new_body = map(decoded, (old, new))
    require(PACKET_KEY not in old_body, 'baseline_already_contains_new_blocker_evidence')
    table = new_body.pop(PACKET_KEY)
    require(new_body == old_body and replaced_body(new, new_body) == old,
            'old_public_brief_semantics_or_JSON_order_changed')
    require(set(table) == {'scope_index', 'columns', 'rows', 'meaning'} and
            tuple(table['columns']) == COLUMNS and isinstance(table['meaning'], str) and bool(table['meaning']),
            'blocker_table_shape_or_meaning')
    scopes = new_body['scopes']['rows']
    scope_index = table['scope_index']
    require(type(scope_index) is int and 0 <= scope_index < len(scopes) and
            scopes[scope_index][0] == 'global' and scopes[scope_index][1] == new_body['binding']['camera_identity'] and
            scopes[scope_index][2] == new_body['binding']['binding_sha256'], 'blocker_table_not_bound_to_global_camera')
    task = source['facts']['region_task']
    by_region = {item['roi_id']: i for i, item in enumerate(task['rows'])}
    expected = [[by_region[row['roi_id']], row['view_name'], row['blocker_object_index'], row['source_triangle_index']]
                for row in task[PACKET_KEY]['rows']]
    require(table['rows'] == expected and len(expected) == len({tuple(row[:2]) for row in expected}),
            'wire_new_rows_do_not_resolve_to_same_verified_source_and_direction/' + case)
    restored, images = replay['verify_brief'](replaced_body(new, new_body))
    require(len(restored['region_task']['rows']) == len(task['rows']), 'region_denominator_drift')
    mapped = []
    for region_index, view, blocker_index, triangle in table['rows']:
        region = restored['region_task']['rows'][region_index]
        owner = source['binding']['objects'][blocker_index]
        require(region['reason'] == BLOCKED_REASON and region['complete_witness'] is None and
                view in region['view_reasons']['positive_area_occlusion'] and
                type(triangle) is int and triangle >= 0, 'packed_evidence_not_eligible')
        mapped.append({'region': region['object_name'], 'roi_id': region['roi_id'],
                       'target_face_range': [region['source_triangle_indices'][0], region['source_triangle_indices'][-1]],
                       'view_name': view, 'blocker': owner['object_name'], 'source_triangle_index': triangle})
    require(all(len(row) == len(COLUMNS) for row in table['rows']) and
            'm²' not in table['meaning'] and 'm2' not in table['meaning'],
            'screen_area_or_undisclosed_columns_in_public_blocker_table')
    cli = replay['cli_stages'](new)
    require(cli['passed'] and [stage['header_UTF8_bytes'] for stage in cli['stages']] == [33, 34, 35],
            'all_new_brief_facts_and_original_images_must_survive_fixed_CLI/' + case)
    return {'qualified_region_count': len(task['rows']),
            'witness_count': len(new_body['witnesses']['rows']),
            'original_PNG_sha256': [item['PNG_sha256'] for item, _ in images],
            'blocked_witnesses': mapped, 'fixed_CLI': cli}


def check_full(old, new, source):
    old_body, new_body = map(decoded, (old, new))
    attached = new_body['facts']['region_task'].pop(PACKET_KEY)
    require(attached == source['facts']['region_task'][PACKET_KEY], 'full_did_not_preserve_bound_blocker_producer_facts')
    require(replaced_body(new, new_body) == old and new_body == old_body, 'old_full_fields_or_JSON_order_changed')
    return {'older_wire_exact_except_optional_additive_field': True,
            'optional_producer_rows': len(attached['rows'])}


def exercise(args):
    replay = runpy.run_path(str(REPLAY))
    prior = runpy.run_path(str(replay['PRIOR']))
    pins = prior['Evidence']()
    for path in (Path(__file__), REPLAY, PRIOR / 'checks/brief_schema.py',
                 replay['TYPED_PATH'], replay['POLICY_PATH'], Path(sys.executable)):
        pins.raw(path)
    pins.raw(replay['PRIOR'], replay['PRIOR_SHA'])
    truth = json.loads(pins.raw(TRUTH, TRUTH_SHA))
    policy = runpy.run_path(str(replay['POLICY_PATH']))
    for name, digest in policy['REPLAY_PINS'].items():
        pins.raw(V / 'm1_source_region_facts_first_001/checks' / name, digest)
    bindings, roots, checksums = installed_roots(pins, args.candidate)
    a, b = bindings
    geometry = json.loads(pins.raw(args.geometry))
    require(geometry['passed'] and set(geometry['fixtures']) == {'dense', 'cross21', 'assembly28'},
            'actual_three_fixture_geometry_controls_required')

    before_cases = original_cases(replay, pins)
    fixtures = geometry['fixtures']
    for name, fixture in fixtures.items():
        require(fixture['producer_sha256'] == before_cases[name + '_brief']['producer_sha256'],
                'source_fixture_not_replaying_same_archived_producer/' + name)
    after_cases = {name: apply_geometry(case, fixtures[case['fixture']]) if 'fixture' in case else case
                   for name, case in before_cases.items()}
    before_cases['dense_missing_optional_evidence'] = before_cases['dense_brief']
    after_cases['dense_missing_optional_evidence'] = before_cases['dense_brief']
    bad_cases = make_bad_cases(after_cases['dense_brief'], after_cases['assembly28_brief'])
    after_cases.update(bad_cases)
    before = replay['child_replay'](roots[0], a['dependency_root'], before_cases)
    after = replay['child_replay'](roots[1], a['dependency_root'], after_cases)
    require(before['module_sha256'] == checksums[0] and after['module_sha256'] == checksums[1] and
            before['catalogues'] == after['catalogues'], 'actual_verified_isolated_imports_and_tool_definitions')
    results, controls = {}, {}
    for name, case in before_cases.items():
        raw_a, raw_b = before['results'][name], after['results'][name]
        require('result' in raw_a and 'result' in raw_b,
                f'formatter_rejected_registered_positive/{name}/{raw_b.get("reason", raw_a.get("reason"))}')
        old, new = raw_a['result'], raw_b['result']
        require(old['content'][1:] == new['content'][1:] and old['isError'] == new['isError'],
                'actual_native_blocks_or_error_state_changed/' + name)
        original = case.get('original_result')
        if original:
            require(original['content'][1:] == old['content'][1:],
                    'isolated_replay_has_different_original_archived_image_bytes/' + name)
        if name in ('dense_brief', 'dense_default'):
            # The archived producer is reloaded from sorted JSON. Nested field
            # order differs from the live object, but body bytes and data agree.
            require(original['isError'] == old['isError'] and decoded(original) == decoded(old) and
                    len(original['content'][0]['text'].encode()) == len(old['content'][0]['text'].encode()),
                    'installed_A_does_not_replay_the_archived_v2_mcp_envelope')
        details = {
            'original_wire_sha256': case.get('wire_sha256'),
            'old_text_UTF8_bytes': len(old['content'][0]['text'].encode()),
            'new_text_UTF8_bytes': len(new['content'][0]['text'].encode()),
            'original_image_count': len(old['content']) - 1,
            'baseline_formatter_ms': raw_a['elapsed_ns'] / 1e6,
            'candidate_formatter_ms': raw_b['elapsed_ns'] / 1e6,
        }
        source = after_cases[name]['producer']
        if case['kind'] == 'legacy' or name == 'dense_missing_optional_evidence':
            require(old == new, 'preserved_original_mode_or_old_producer_wire_changed/' + name)
            details['unchanged_wire'] = True
        elif case['kind'] == 'brief':
            details.update(check_brief(old, new, source, replay, name))
        else:
            details.update(check_full(old, new, source))
        if '_hot_' in name:
            details.update(original_global_index_cache_hit=case['work']['global_index_cache_hit'],
                           original_global_index_calls=case['work']['index_calls'],
                           original_actual_raster_attempts=case['work']['raster_attempts'])
            require(details['original_image_count'] == details['original_actual_raster_attempts'] == 0,
                    'unchanged_hot_prediction_must_not_claim_images/' + name)
        results[name] = details
    for name in bad_cases:
        error = after['results'][name]
        require(error.get('error') == 'ValueError' and 'result' not in error and
                'blocker' in error['reason'], f'malformed_optional_facts_were_not_rejected/{name}/{error.get("reason")}')
        controls[name] = error['reason']

    dense = results['dense_brief']
    require(dense['old_text_UTF8_bytes'] == 8242 and dense['new_text_UTF8_bytes'] <= MAX_BRIEF_BYTES and
            dense['original_image_count'] == 2 and dense['qualified_region_count'] == len(truth['eligible']) == 13 and
            dense['witness_count'] == 11, 'dense_plus_blocker_preserves_registered_budget_and_original_denominator')
    dense_sources = {(row['region'], tuple(row['target_face_range']), row['view_name'], row['blocker'],
                      row['source_triangle_index']) for row in dense['blocked_witnesses']}
    require(dense_sources == {('M4_Far_00', (0, 511), 'LEFT', 'M4_Near', 0),
                              ('M4_Far_02', (0, 511), 'LEFT', 'M4_Far_00', 512)},
            'new_dense_brief_failed_independently_named_source_and_target_face_checks')
    require(after['results']['dense_brief']['result'] == after['results']['dense_default']['result'],
            'new_successful_default_and_explicit_brief_differ')
    cross = results['cross21_brief']['blocked_witnesses']
    assembly = results['assembly28_brief']['blocked_witnesses']
    require(len(cross) == len(assembly) == 6 and
            {(row['region'], row['blocker']) for row in cross} == {('M06', 'M03')} and
            {row['region'] for row in assembly} == {'N11'} and
            len({row['blocker'] for row in assembly}) > 1,
            'older_cross_scale_briefs_did_not_keep_expected_blocker_roster')
    return {'schema': 'm4-bound-blocker-format-controls-v1', 'passed': True,
            'actual_Blender_processes': 0, 'actual_models': 0, 'actual_raster_attempts': 0,
            'baseline_source_sha256': a['source_sha256'], 'candidate_source_sha256': b['source_sha256'],
            'candidate_formatter_sha256': checksums[1], 'baseline_formatter_sha256': checksums[0],
            'case_denominator': len(before_cases), 'negative_denominator': len(controls),
            'geometry_receipt_sha256': sha256(args.geometry.read_bytes()).hexdigest(),
            'cases': results, 'negative_controls': controls,
            'source_pins': sorted(pins.pins.values(), key=lambda row: row['path'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, default=NS / 'install/PRODUCT_RUN_BINDING.json')
    parser.add_argument('--geometry', type=Path, default=HERE / 'GEOMETRY_CONTROLS.json')
    parser.add_argument('--output', type=Path, default=HERE / 'FORMAT_CONTROLS.json')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_python_required')
    record = exercise(args)
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(record, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        stream.write('\n')
    dense = record['cases']['dense_brief']
    print('Passed formatter controls:', record['case_denominator'], '+', record['negative_denominator'],
          'old/new dense bytes:', dense['old_text_UTF8_bytes'], dense['new_text_UTF8_bytes'])


if __name__ == '__main__':
    main()
