"""Replay an isolated formatter on fixed producer data and original native images."""

import argparse
import base64
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import runpy
import subprocess
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
sys.path.insert(0, str(HERE))
from brief_schema import (POLICY_PATH, TYPED_PATH, V2, cli_stages, records, require,
                          verify_brief, FRAMES, REGIONS, WITNESSES)


FORMATTER = 'human_eye_plugin/live_spatial_mcp.py'
ORIGIN = V / 'm4_cross_scale_projected_bounds_001/install/PRODUCT_RUN_BINDING.json'
ORIGIN_SHA = 'a43b471280b4b3da1a0e289c688adf45bd3b032d9af454edc140bc140bece13e'
PRIOR = V / 'm4_cross_scale_region_geometry_facts_001/checks/projection_replay.py'
PRIOR_SHA = '10af2c84b49596e7130235310938243cdf0cf1c28288b739ea10005e55e45232'
TRUTH = V / 'm4_dense_panel_sweep_001/truth/CURRENT_TRUTH.json'
TRUTH_SHA = 'd4d05b3ffb713331c4348852335b9d17ebfe9690c7013062d39b82bb8087700a'
QUALIFIED = V / 'm4_dense_panel_sweep_001/checks/QUALIFICATION_QP.json'
QUALIFIED_SHA = 'a5f81128ed502163b141f730a199e7645e34a9e41cd0c65493f1c2b3fe533903'
ARCHIVES = (
    ('dense', 'm4_dense_panel_sweep_001', 'QP',
     '3516e3e6273658fcd2c03f0e2ca1465810a6f940ee6576188d46b1bae7558b90', 1),
    ('cross21', 'm4_cross_scale_cold_frustum_001', 'B1',
     '7f94dc9f4a1d01d5b8b38064293887504b8025065a3e2e994370aea4a1f1a3b0', 2),
    ('assembly28', 'm4_cross_scale_pixel_evidence_001', 'P1',
     '0802bfd8968a14ceb9cb209b4378d27b3045acc61d9bede297d42dba29c5658e', 2),
)
LEGACY_MODES = (
    ('source_region', 'D:/he_m4_live_source_region_task_003/slots/P1/product_full/call_001/SERVICE_RESULT.json',
     '32d1dded3fe137e611087e1e8487b732d3cede1d47a6cbe259a466eb6be5b9c9'),
    ('ordinary_active', 'D:/he_m4_global_local_001/sessions/global/product_full/call_001/SERVICE_RESULT.json',
     '7e1c4331d7582254e985d256595dad0fdef4d98a21974b969f3cff9e97f6a112'),
)
MAX_TEXT_UTF8 = 10_800


def digest(raw):
    return sha256(raw).hexdigest()


class Archive:
    def __init__(self, pins, stack, batch, slot, index_sha):
        self.pins = pins
        self.root = Path('D:/he_' + batch).resolve()
        self.slot = self.root / 'slots' / slot
        sealed = json.loads(pins.raw(V / batch / 'RUNTIME_INDEX.json', index_sha))
        original_zip = self.root / 'ORIGINAL_RUNTIME.zip'
        require(len(pins.raw(original_zip, sealed['archive']['sha256'])) == sealed['archive']['bytes'],
                'unchanged_runtime_zip_size')
        self.zip = stack.enter_context(ZipFile(original_zip))
        self.index = {row['path']: row for row in sealed['files']}
        names = self.zip.namelist()
        require(len(names) == len(self.index) == sealed['count'] and set(names) == self.index.keys(),
                'unchanged_runtime_archive_manifest')
        self.events = [json.loads(line) for line in self.raw(self.slot / 'PUBLIC_REQUESTS.jsonl').splitlines()]

    def raw(self, path):
        path = Path(path).resolve()
        relative = path.relative_to(self.root).as_posix()
        member = self.index[relative]
        raw = self.pins.raw(path, member['sha256'])
        require(len(raw) == member['bytes'] and raw == self.zip.read(relative),
                'runtime_archive_member_bytes_changed/' + relative)
        return raw

    def read(self, path):
        return json.loads(self.raw(path))

    def take(self, ordinal):
        event = self.events[ordinal - 1]
        receipt = event['receipt']
        rpc = self.slot / 'mcp' / f"rpc_{receipt['index']:02d}"
        request, reply = [self.read(rpc / (name + '.bin')) for name in ('TX', 'RX')]
        require(event['index'] == ordinal and request == event['request'] and request['id'] == reply['id'] and
                request['params']['name'] == 'human_eye_scene_observe' and reply == event['response'] and
                receipt == self.read(rpc / 'RECEIPT.json') and reply['result']['isError'] is False,
                'original_public_stdio_binds_same_product_request')
        raw_reply = self.raw(rpc / 'RX.bin')
        archive = event['producer_archive']
        raw = self.raw(archive['path'])
        require(digest(raw) == archive['sha256'] and archive['new_observations_for_archive'] == 0,
                'archive_source_from_original_production_once')
        source = json.loads(raw)
        self.raw(archive['read_context'])
        self.raw(self.slot / 'TERMINAL_SOURCE.json')
        for frame in source['constructed_frames']:
            image = self.raw(frame['image_path'])
            arrays = self.raw(frame['arrays_path'])
            require(digest(image) == frame['image_sha256'] and digest(arrays) == frame['arrays_sha256']
                    and len(image) == frame['PNG_bytes'], 'original_frame_pair_digest_changed')
        for frame, block in zip(source['frames'], reply['result']['content'][1:], strict=True):
            require(block == {'type': 'image', 'mimeType': 'image/png',
                              'data': base64.b64encode(self.raw(frame['image_path'])).decode('ascii')},
                    'original_product_PNG_not_from_actual_selected_frame')
        return {
            'producer': source, 'detail': request['params']['arguments']['response_detail'],
            'original_result': reply['result'], 'wire_sha256': digest(raw_reply),
            'producer_sha256': digest(raw), 'work': source['work'],
            'original_bytes': len(raw_reply), 'arguments': request['params']['arguments'],
        }


def child_replay(install, dependency, test_cases):
    worker = """
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
install, dependency = map(Path, sys.argv[1:])
sys.path[:0] = [str(install), str(dependency)]
from human_eye_plugin import live_spatial_mcp as mcp
module = Path(mcp.__file__).resolve()
if module != install / 'human_eye_plugin/live_spatial_mcp.py':
    raise ValueError('formatter_import_wrong_build')
results = {}
for name, case in json.load(sys.stdin).items():
    value = case['producer']
    untouched = json.dumps(value, ensure_ascii=True, allow_nan=False)
    audit = {}
    try:
        start = time.perf_counter_ns()
        reply = mcp._tool_result(value, is_error=case.get('is_error', False),
              response_detail=case['detail'], active_delivery_audit=audit)
    except (ValueError, KeyError, TypeError, IndexError, StopIteration) as error:
        results[name] = {'error': type(error).__name__, 'reason': str(error), 'audit': audit}
    else:
        results[name] = {'result': reply, 'audit': audit, 'elapsed_ns': time.perf_counter_ns()-start}
    if untouched != json.dumps(value, ensure_ascii=True, allow_nan=False):
        raise ValueError('formatter_mutated_archived_input/' + name)
print(json.dumps({'results': results, 'module_sha256': sha256(module.read_bytes()).hexdigest(),
      'catalogues': [mcp.LIVE_MCP_TOOLS_SCHEMA, mcp.SPATIAL_TASK_TOOLS_SCHEMA]}, ensure_ascii=True, allow_nan=False))
"""
    fields = {'producer', 'detail', 'is_error'}
    case_input = {name: {key: value for key, value in case.items() if key in fields}
                  for name, case in test_cases.items()}
    ran = subprocess.run([sys.executable, '-I', '-B', '-c', worker, str(install), str(dependency)],
                         input=json.dumps(case_input, ensure_ascii=True, allow_nan=False).encode('utf8'),
                         check=True, capture_output=True, timeout=90)
    return json.loads(ran.stdout)


def variant(case, *, detail=None, is_error=False):
    return {'producer': case['producer'], 'detail': detail, 'is_error': is_error}


def source_regions(value):
    return value['facts']['region_task']['rows']


def synthetic_cases(cases):
    dense = cases['dense_brief']
    value = deepcopy(dense['producer'])
    task = value['facts']['region_task']
    row = next(item for item in task['rows'] if item['reason'] == 'positive_area_occlusion_all_front_views')
    globals_ = [value['facts']['scope'], next(scope for scope in value['scopes']
                                             if scope['scope_id'] == 'global')['facts']['scope']]
    ids = [0, 2, 3, 511]
    row['source_triangle_indices'] = row['source']['source_triangle_indices'] = ids
    for scope in globals_:
        source, = [r for r in scope['patch_support']['regions'] if r['roi_id'] == row['roi_id']]
        source['triangle_indices'] = ids
    cases['sparse_triangles'] = {'producer': value, 'detail': 'brief', 'compact': True}

    value = deepcopy(dense['producer'])
    retired = value['frames'].pop(1)
    value['facts']['region_task']['summary']['selected_image_count'] = 1
    for row in source_regions(value):
        witness = row['complete_witness']
        if witness is not None and witness['frame_identity'] == retired['frame_identity']:
            witness['selected_for_delivery'] = False
    cases['unselected_complete_witness'] = {'producer': value, 'detail': 'brief', 'compact': True}
    value = deepcopy(dense['producer'])
    value['frames'].reverse()
    cases['selected_reordered_vs_constructed'] = {'producer': value, 'detail': 'brief', 'compact': True}

    value = deepcopy(cases['assembly28_brief']['producer'])
    value['frames'].append(next(frame for frame in value['constructed_frames']
                                if frame['scope_id'] != 'global' and frame['view_name'] == 'TOP'))
    value['facts']['region_task']['summary']['selected_image_count'] = 2
    cases['selected_pixel_shortfall'] = {'producer': value, 'detail': 'brief', 'compact': True}

    value = deepcopy(dense['producer'])
    binding = value['binding']
    value['task_result'] = {'status': 'complete', 'facts': {'geometry_test_control': [1, 17]},
                            'binding': {'observation_source': {
                                'measurement_scope': 'whole_objects', 'parent_binding_sha256': binding['binding_sha256'],
                                'parent_source_binding_sha256': binding['source_binding_sha256'],
                                'parent_capture_scope': binding['capture_scope']}}}
    cases['combined_task_result'] = {'producer': value, 'detail': 'brief', 'compact': True}

    for name, mutate in (
        ('wrong_frame_source_revision', lambda value: value['constructed_frames'][-1].update(source_revision='stale')),
        ('wrong_region_source_binding', lambda value: source_regions(value)[0]['source'].update(
            parent_source_binding_sha256='stale')),
        ('wrong_witness_scope', lambda value: source_regions(value)[-1]['complete_witness'].update(scope_id='stale')),
        ('wrong_witness_pixel_row', lambda value: source_regions(value)[-1]['complete_witness'].update(pixel_row_index=10**6)),
        ('duplicate_frame_identity', lambda value: value['constructed_frames'][-1].update(
            frame_identity=value['constructed_frames'][0]['frame_identity'])),
    ):
        value = deepcopy(dense['producer'])
        mutate(value)
        cases[name] = {'producer': value, 'detail': 'brief', 'negative': True}
    value = deepcopy(cases['combined_task_result']['producer'])
    value['task_result']['binding']['observation_source']['parent_binding_sha256'] = 'stale'
    cases['wrong_combined_task_source'] = {'producer': value, 'detail': 'brief', 'negative': True}
    cases['wrong_witness_pixel_row_full'] = dict(cases['wrong_witness_pixel_row'], detail='full')


def dense_reference(candidate, checked, truth):
    def indexed(rows):
        return {(item['object_name'], tuple(item['source_triangle_indices'])): item for item in rows}

    public = indexed(candidate['region_task']['rows'])
    reference = indexed(truth['eligible'])
    require(len(public) == len(reference) == 13 and public.keys() == reference.keys(),
            'dense_v2_independent_source_region_roster')
    measured = Counter()
    for key, expected in reference.items():
        actual = public[key]
        name, indices = key
        tag = f'{name}[{indices[0]}–{indices[-1]}]'
        original = checked['original_regions'][tag]
        require(actual['center_world_m'] == expected['center_world_m'] and
                (indices == tuple(range(512)) or indices == (512, 513)) and
                actual['source']['ordered_geometry_sha256'] and actual['view_reasons'] == original['view_reasons'],
                'dense_v2_independent_world_geometry_or_extent/' + tag)
        witness = actual['complete_witness']
        if witness:
            require(witness == original['complete_witness'] and witness['view_name'] in expected['eligible_complete_views'],
                    'dense_v2_original_verified_witness/' + tag)
            measured[witness['view_name']] += 1
        else:
            require(not expected['eligible_complete_views'] and actual['reason'] == 'positive_area_occlusion_all_front_views',
                    'dense_v2_independent_occlusion_reason/' + tag)
            measured['independent_geometric_unknowns'] += 1
    require(measured == {'SCENE': 1, 'LEFT': 10, 'independent_geometric_unknowns': 2},
            'dense_v2_required_evidence_coverage')
    return dict(measured)


def verify_frames_and_controls(name, packet, source, restored):
    frames = records(packet['frames'], FRAMES)
    actual = source['constructed_frames']
    require(len(frames) == len(actual), 'v2_missing_actual_frames/' + name)
    selected = {frame['frame_identity']: i for i, frame in enumerate(source['frames'], start=1)}
    for got, wanted in zip(frames, actual, strict=True):
        scope_index = got['scope_index']
        scopes = packet['scopes']['rows']
        require(scopes[scope_index][0] == wanted['scope_id'] and
                all(got[field] == wanted[field] for field in ('view_name', 'frame_identity', 'image_ref', 'image_sha256'))
                and got['native_content_block_index'] == selected.get(wanted['frame_identity']),
                'v2_frame_must_bind_accurate_original_scope_and_content_block/' + name)
    if name in ('cross21_brief', 'assembly28_brief'):
        repeated = next(view for view, count in Counter(f['view_name'] for f in frames).items() if count > 1)
        pair = [frame for frame in frames if frame['view_name'] == repeated]
        require(len({f['scope_index'] for f in pair}) == len({f['frame_identity'] for f in pair}) == len(pair),
                'v2_repeated_view_must_keep_distinct_scope_and_frame')
    if name == 'sparse_triangles':
        require(any(row['source_triangle_index_ranges'] == [[0, 0], [2, 3], [511, 511]]
                    for row in records(packet['region_task'], REGIONS)), 'v2_sparse_single_zero_inclusive_runs')
    if name == 'unselected_complete_witness':
        rows = [r['complete_witness'] for r in restored['region_task']['rows'] if r['complete_witness']]
        require(sum(row['native_content_block_index'] is None and row['selected_for_delivery'] is False for row in rows)
                == 10, 'v2_verified_unselected_witness_never_claims_delivery')
    if name in ('assembly28_brief', 'selected_pixel_shortfall'):
        probe, = [row['pixel_shortfall'] for row in restored['region_task']['rows'] if 'pixel_shortfall' in row]
        delivered = name == 'selected_pixel_shortfall'
        require(probe['view_name'] == 'TOP' and probe['scope_id'].startswith('local_') and
                probe['visible_surface_pixels'] == 8835 and probe['contrasting_boundary_pixels'] == 0 and
                probe['image_delivered'] is delivered and
                probe['native_content_block_index'] == (2 if delivered else None),
                'v2_pixel_shortfall_binding_or_actual_delivery_changed')
    if name == 'combined_task_result':
        require(restored['task_result'] == source['task_result'], 'v2_combined_task_result_passthrough')


def verify_case(name, case, before, after):
    if case.get('negative'):
        if name == 'wrong_witness_pixel_row':
            require(before.get('error') == 'IndexError' and after.get('error') == 'ValueError' and
                    after['reason'] == 'active_region_task_witness_pixel_row_index',
                    'v2_out_of_range_witness_not_controlled')
            return {'outcome': 'rejected', 'legacy_exception': before['error'], 'reason': after['reason']}
        require(before.get('error') is not None and before['error'] == after.get('error') and
                before['reason'] == after['reason'], 'v2_inherited_bad_binding_rejection_changed/' + name)
        return {'outcome': 'rejected', 'reason': after['reason']}
    require('result' in before and 'result' in after, 'v2_unexpected_formatter_failure/' + name
            + '/' + str(after.get('reason') or before.get('reason')))
    old_result, new_result = before['result'], after['result']
    old_text, new_text = [result['content'][0]['text'] for result in (old_result, new_result)]
    old_body, new_body = json.loads(old_text), json.loads(new_text)
    if 'original_result' in case:
        live = case['original_result']
        require(live['isError'] == old_result['isError'] and live['content'][1:] == old_result['content'][1:] and
                json.loads(live['content'][0]['text']) == old_body and
                len(live['content'][0]['text'].encode()) == len(old_text.encode()),
                'retained_old_product_replay_differs_from_original_RPC/' + name)
    require(new_result['content'][1:] == old_result['content'][1:] and
            old_result['isError'] == new_result['isError'], 'v2_changed_native_content_or_result_success/' + name)
    summary = {'outcome': 'passed', 'old_text_UTF8_bytes': len(old_text.encode()),
               'new_text_UTF8_bytes': len(new_text.encode()), 'native_images': len(new_result['content']) - 1,
               'archive_producer_sha256': case.get('producer_sha256'), 'archive_wire_sha256': case.get('wire_sha256'),
               'formatter_only_baseline_ms': before['elapsed_ns'] / 1e6, 'formatter_only_candidate_ms': after['elapsed_ns'] / 1e6}
    if not case.get('compact'):
        require(old_result == new_result, 'v2_out_of_scope_wire_changed/' + name)
        summary['out_of_scope_wire_exact'] = True
        return summary, None
    require(new_body['schema'] == V2 and after['audit']['projection_status'] == 'brief',
            'v2_expected_compact_successful_brief/' + name)
    restored, images = verify_brief(new_result, old_body)
    verify_frames_and_controls(name, new_body, case['producer'], restored)
    summary.update(decoded_exact_v1=True, observed_regions=len(records(new_body['witnesses'], WITNESSES)),
                   decoded_regions=len(restored['region_task']['rows']),
                   original_PNG_sha256=[item['PNG_sha256'] for item, _ in images])
    if name in ('dense_brief', 'cross21_brief', 'assembly28_brief'):
        summary['fixed_CLI'] = cli_stages(new_result)
    return summary, restored


def encoded_negative_controls(result, baseline):
    base = json.loads(result['content'][0]['text'])
    controls = {}
    for name, change in (
        ('wrong_witness_frame_table_index', lambda v: v['witnesses']['rows'][0].__setitem__(1, 1-v['witnesses']['rows'][0][1])),
        ('invalid_frame_scope_index', lambda v: v['frames']['rows'][1].__setitem__(0, len(v['scopes']['rows']))),
        ('duplicate_frame_native_block', lambda v: v['frames']['rows'][1].__setitem__(-1, 1)),
        ('noncanonical_adjacent_triangle_ranges',
         lambda v: v['region_task']['rows'][0].__setitem__(6, [[0, 0], [1, 511]])),
        ('source_triangle_added_outside_domain',
         lambda v: v['region_task']['rows'][0].__setitem__(6, [[0, 6148]])),
    ):
        tampered = deepcopy(base)
        change(tampered)
        try:
            verify_brief({**result, 'content': [{'type': 'text', 'text': json.dumps(tampered)}, *result['content'][1:]]},
                         baseline)
        except ValueError as error:
            controls[name] = str(error)
        else:
            raise ValueError('independent_v2_decoder_accepted_bad_reference/' + name)
    return controls


def exercise(args):
    helper = runpy.run_path(str(PRIOR))
    pins = helper['Evidence']()
    for path in (Path(__file__), HERE / 'brief_schema.py', TYPED_PATH, POLICY_PATH, Path(sys.executable)):
        pins.raw(path)
    pins.raw(PRIOR, PRIOR_SHA)
    truth = json.loads(pins.raw(TRUTH, TRUTH_SHA))
    qualification = json.loads(pins.raw(QUALIFIED, QUALIFIED_SHA))
    limits_path = V / 'm1_source_region_facts_first_001/checks'
    for name, pin in runpy.run_path(str(POLICY_PATH))['REPLAY_PINS'].items():
        pins.raw(limits_path / name, pin)
    a = json.loads(pins.raw(ORIGIN, ORIGIN_SHA))
    b = json.loads(pins.raw(args.candidate))
    dependency = Path(a['dependency_root']).resolve()
    require(dependency == Path(b['dependency_root']).resolve(), 'same_dependency_environment_required')
    product_roots, product_digests = [], []
    for binding in (a, b):
        install = Path(binding['install_root']).resolve()
        formatter, = [row for row in binding['source_manifest'] if row['path'] == FORMATTER]
        pins.raw(install / FORMATTER, formatter['sha256'])
        product_roots.append(install)
        product_digests.append(formatter['sha256'])
    require(len(set(product_roots)) == len(set(product_digests)) == 2, 'isolated_product_candidate_required')

    cases = {}
    with ExitStack() as stack:
        for name, batch, label, index_sha, count in ARCHIVES:
            archive = Archive(pins, stack, batch, label, index_sha)
            compact = archive.take(1)
            cases[name + '_brief'] = {**compact, 'compact': True}
            cases[name + '_full'] = variant(compact, detail='full')
            if count == 2:
                prediction = archive.take(2)
                cases[name + '_prediction_full'] = prediction
                cases[name + '_prediction_default'] = {**variant(prediction), 'compact': True}
    cases['dense_default'] = {**variant(cases['dense_brief']), 'compact': True}
    cases['dense_as_error'] = variant(cases['dense_brief'], detail='brief', is_error=True)
    cases['plain_service_error'] = {'producer': {'status': 'failed', 'error': {'type': 'example'}},
                                    'detail': 'brief', 'is_error': True}
    for name, path, pin in LEGACY_MODES:
        value = json.loads(pins.raw(path, pin))
        for frame in value['frames']:
            pins.raw(frame['image_path'], frame['image_sha256'])
            pins.raw(frame['arrays_path'], frame['arrays_sha256'])
        for detail in ('brief', 'full', None):
            cases[f'{name}_{detail or "default"}'] = {'producer': value, 'detail': detail}
    synthetic_cases(cases)
    before, after = [child_replay(install, dependency, cases) for install in product_roots]
    require([before['module_sha256'], after['module_sha256']] == product_digests and
            before['catalogues'] == after['catalogues'], 'same_actual_tools_and_verified_formatter_sources')
    summaries, restored = {}, {}
    for name, case in cases.items():
        old, new = before['results'][name], after['results'][name]
        outcome = verify_case(name, case, old, new)
        if case.get('negative'):
            summaries[name] = outcome
        else:
            summaries[name], restored[name] = outcome
    dense = summaries['dense_brief']
    require(dense['new_text_UTF8_bytes'] <= MAX_TEXT_UTF8 and dense['old_text_UTF8_bytes'] == 72253 and
            dense['native_images'] == 2 and dense['decoded_regions'] == 13 and dense['observed_regions'] == 11 and
            after['results']['dense_brief']['result'] == after['results']['dense_default']['result'],
            'dense_packet_budget_or_same_default_form_gate_failed')
    dense['independent_truth_crosscheck'] = dense_reference(restored['dense_brief'], qualification, truth)
    negative = encoded_negative_controls(after['results']['dense_brief']['result'], restored['dense_brief'])
    return {'schema': 'm4-dense-region-brief-offline-controls-v1', 'passed': True,
            'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_raster_attempts': 0,
            'baseline_source_sha256': a['source_sha256'], 'candidate_source_sha256': b['source_sha256'],
            'baseline_formatter_sha256': product_digests[0], 'candidate_formatter_sha256': product_digests[1],
            'direct_source_and_original_PNG_NPZ_verified': True,
            'case_denominator': len(cases), 'cases': summaries, 'encoded_negative_controls': negative,
            'source_pins': sorted(pins.pins.values(), key=lambda row: row['path'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'OFFLINE_CONTROLS.json')
    parser.add_argument('--candidate', type=Path, default=NS / 'install/PRODUCT_RUN_BINDING.json')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_python_I_B_required')
    result = exercise(args)
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        stream.write('\n')
    dense = result['cases']['dense_brief']
    print('Approved offline', result['case_denominator'], dense['old_text_UTF8_bytes'],
          dense['new_text_UTF8_bytes'], dense['independent_truth_crosscheck'])


if __name__ == '__main__':
    main()
