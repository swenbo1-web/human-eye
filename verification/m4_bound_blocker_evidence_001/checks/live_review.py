"""Audit the sole live blocker qualification using current source and raw wire."""

import argparse
from fractions import Fraction
import json
from pathlib import Path
import runpy
import time


HERE = Path(__file__).resolve().parent
NS = HERE.parent
BASE = NS.parent / 'm4_dense_region_brief_001'
RUN = Path('D:/he_m4_bound_blocker_evidence_001')
BASE_REVIEW_SHA = 'dfb3caf6a4709c667bb13b7f592cfcda81b482b2708d87185f26bfcffe72824a'
BASE_COMMIT = '278fd3003758299379f6d87b7e9174c577f5bb88'
BASE_SOURCE = '6e8663feb57b630048fe919141cfcabbae4ae2365df1f80da693382c360b65e8'
BINDING = NS / 'install/PRODUCT_RUN_BINDING.json'
CHANGED = ['human_eye_plugin/active_observation.py', 'human_eye_plugin/active_observation_region_task.py',
           'human_eye_plugin/live_spatial_mcp.py']
COLUMNS = ('region_index', 'view_name', 'blocker_object_index', 'source_triangle_index')
MEANING = ('One current object-local evaluated triangle with positive-area occlusion per listed view. '
           'Nearest depth, other blockers, and total occlusion are unspecified.')
ORIGINAL_KEYS = {'roi_id', 'view_name', 'blocker_object_index', 'source_triangle_index',
                 'blocker_host_id', 'blocker_instance_id', 'triangle_geometry_id', 'overlap_area_screen_exact'}
UNKNOWN = 'positive_area_occlusion_all_front_views'
EXPECTED = {'M4_Far_00': ('M4_Near', 0, Fraction(73786983304225, 9223372036854775808)),
            'M4_Far_02': ('M4_Far_00', 512, Fraction(1, 2))}


retained = runpy.run_path(str(BASE / 'checks/live_review.py'))
read, require, verified, write, digest, ms = (retained[name] for name in
                                               ('read', 'require', 'verified', 'write', 'digest', 'ms'))
original_qualify = retained['qualify']
original_inspect = retained['inspect_product']


def installed_binding(slot, frozen, result):
    base_binding_path = BASE / 'install/PRODUCT_RUN_BINDING.json'
    baseline, candidate = read(base_binding_path), read(BINDING)
    commit, source = candidate['preparation_git'], candidate['source_sha256']
    require(baseline['preparation_git'] == BASE_COMMIT and baseline['source_sha256'] == BASE_SOURCE
            and candidate['historical_preparation_git'] == BASE_COMMIT
            and candidate['historical_source_sha256'] == BASE_SOURCE
            and candidate['changed_product_sources'] == CHANGED
            and frozen['product'] == {'commit': commit, 'source_sha256': source}
            and result['product_source_sha256'] == source
            and result['product_binding_sha256'] == digest(BINDING.read_bytes()) and source != BASE_SOURCE,
            'frozen_product_and_slot_candidate_do_not_agree')
    before, after = ({row['path']: row['sha256'] for row in item['source_manifest']}
                     for item in (baseline, candidate))
    require(len(after) == len(candidate['source_manifest']) == len(before) == len(baseline['source_manifest']) == 143
            and before.keys() == after.keys() and sorted(name for name in before if before[name] != after[name]) == CHANGED,
            'candidate_installed_source_delta_changed')
    install = Path(candidate['install_root'])
    for name, checksum in after.items():
        verified(install / name, checksum, install)
    require(digest(Path(candidate['wheel_path']).read_bytes()) == candidate['wheel_sha256'],
            'registered_candidate_wheel_changed')
    identity, ready = (read(slot / name) for name in ('MCP_IDENTITY.json', 'RUNTIME_READY.json'))
    identity_keys = ('distribution_version', 'source_sha256', 'build_id', 'base_version',
                     'implementation_revision', 'protocol_version')
    require(identity['source_kind'] == 'installed_distribution' and identity['source_file_count'] == 143
            and identity['identity_check']['compatible'] is True and all(identity[k] == candidate[k] for k in identity_keys)
            and ready['product_source_sha256'] == source
            and read(slot / 'INSTALLED_TOOLS.json') == read(base_binding_path.with_name('TOOLS_SCHEMA.json')),
            'actual_candidate_process_or_fixed_tool_schema_changed')
    return candidate


def utf8_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8'))


def indexed(values, index, reason):
    require(type(index) is int and 0 <= index < len(values), reason)
    return values[index]


def triangle_key_sha(points):
    exact = tuple(tuple(Fraction(coord) for coord in point) for point in points)
    canonical = min(exact[i:] + exact[:i] for i in range(3))
    return digest(json.dumps(canonical, default=str, sort_keys=True, separators=(',', ':')).encode('utf-8'))


def verify_blockers(body, producer, terminal, truth, proof):
    binding, task = producer['binding'], producer['facts']['region_task']
    internal = task['blocker_evidence']
    require(set(internal) == {'scope_id', 'binding_sha256', 'source_binding_sha256', 'camera_identity', 'rows'}
            and internal['scope_id'] == 'global'
            and all(internal[key] == binding[key] for key in
                    ('binding_sha256', 'source_binding_sha256', 'camera_identity')),
            'internal_blocker_evidence_not_bound_to_current_global_source')
    public = body['blocker_evidence']
    require(set(public) == {'scope_index', 'columns', 'rows', 'meaning'}
            and tuple(public['columns']) == COLUMNS and public['meaning'] == MEANING,
            'public_blocker_evidence_table_changed')
    scope_columns = body['scopes']['columns']
    scope_row = indexed(body['scopes']['rows'], public['scope_index'], 'blocker_scope_index_invalid')
    scope = dict(zip(scope_columns, scope_row, strict=True))
    require(scope['scope_id'] == 'global' and all(scope[key] == binding[key]
            for key in ('binding_sha256', 'camera_identity')), 'public_blocker_evidence_wrong_current_scope')
    global_scope, = [item for item in producer['scopes'] if item['scope_id'] == 'global']
    cameras = global_scope['binding']['camera_specification']
    poses = {pose['name']: pose for pose in cameras['views']}
    terminal_objects = {item['name']: item for item in terminal['objects']}
    ref_rows = {retained['region_key'](row): row for row in truth['eligible']}
    roi_column = body['region_task']['columns'].index('roi_id')
    v2_region_indices = {row[roi_column]: index
                         for index, row in enumerate(body['region_task']['rows'])}
    original_rows = task['rows']
    targets = [(index, row) for index, row in enumerate(original_rows)
               if row['status'] == 'unknown' and row['reason'] == UNKNOWN]
    require(len(targets) == len(internal['rows']) == len(public['rows']) == len(EXPECTED) == 2
            and {row['object_name'] for _, row in targets} == EXPECTED.keys(),
            'exactly_two_dense_geometric_blocker_certificates_required')
    records = []
    for (region_index, target), actual, compact in zip(targets, internal['rows'], public['rows'], strict=True):
        view = 'LEFT'
        name = target['object_name']
        expected_name, expected_source_index, expected_area = EXPECTED[name]
        require(set(actual) == ORIGINAL_KEYS and actual['roi_id'] == target['roi_id']
                and v2_region_indices[target['roi_id']] == region_index
                and target['source_triangle_indices'] == list(range(512))
                and actual['view_name'] == view and target['view_reasons']['positive_area_occlusion'] == [view]
                and target['complete_witness'] is None,
                'blocker_must_be_tied_to_the_unknown_current_region_and_positive_area_view')
        blocker_index, face_index = actual['blocker_object_index'], actual['source_triangle_index']
        require(compact == [region_index, view, blocker_index, face_index]
                and all(type(compact[i]) is int for i in (0, 2, 3)),
                'public_blocker_row_disagrees_with_current_producer')
        obj = indexed(binding['objects'], blocker_index, 'blocker_object_index_invalid')
        public_obj = dict(zip(body['objects']['columns'], indexed(body['objects']['rows'], blocker_index,
            'public_blocker_object_index_invalid'), strict=True))
        source = terminal_objects[expected_name]
        require(obj == public_obj and obj['object_index'] == blocker_index and obj['object_name'] == expected_name
                and obj['host_id'] == source['object_id'] == actual['blocker_host_id']
                and obj['instance_id'] == source['instance_id'] == actual['blocker_instance_id'],
                'blocker_object_source_not_current')
        mesh = source['evaluated']
        triangle = indexed(mesh['triangles'], face_index, 'source_triangle_index_out_of_range')
        require(face_index == expected_source_index, 'exact_current_source_triangle_not_the_original_first_blocker')
        points = [mesh['vertices_world_m'][point_index] for point_index in triangle]
        trace = ref_rows[retained['region_key'](target)]['finite_direction_proofs'][view]
        expected_hit, = [row for row in trace['positive_area_occluders']
                         if row['object_name'] == expected_name and row['source_triangle_index'] == face_index]
        pose = poses[view]
        chart_area, screen_area = proof['independent_overlap'](points, proof['region_corners'](target), pose)
        require(trace['status'] == 'positive_area_occlusion' and pose['direction_rational'] == trace['direction']
                and chart_area == expected_area == Fraction(expected_hit['projected_area_m2_per_basis'])
                and chart_area > 0 and screen_area > 0
                and type(actual['overlap_area_screen_exact']) is str
                and Fraction(actual['overlap_area_screen_exact']) == screen_area
                and actual['triangle_geometry_id'] == triangle_key_sha(points),
                'blocker_failed_exact_current_source_geometry_or_area_replay')
        records.append({'region_index': region_index, 'target_object_name': name, 'target_roi_id': target['roi_id'],
                        'view_name': view, 'blocker_object_index': blocker_index,
                        'blocker_object_name': expected_name, 'source_triangle_index': face_index,
                        'projected_target_plane_area_m2_exact': str(chart_area),
                        'screen_overlap_exact': str(screen_area), 'actual_geometry_certificate_matches': True})
    return records


def inspect(slot, reply, event, meter, installed, terminal, truth, _, outcome):
    baseline = json.loads(verified(BASE / 'checks/LIVE_REVIEW.json', BASE_REVIEW_SHA, BASE))
    require(baseline['passed'] is True and baseline['runtime_source_sha256'] == BASE_SOURCE
            and baseline['installed_product']['commit'] == BASE_COMMIT and baseline['wire']['body_UTF8_bytes'] == 8242,
            'retained_compact_qualification_baseline_changed')
    outcome['baseline_compact_qualification_sha256'] = BASE_REVIEW_SHA
    original_inspect(slot, reply, event, meter, installed, terminal, truth, baseline, outcome)
    body = json.loads(reply['result']['content'][0]['text'])
    archive = event['producer_archive']
    producer = json.loads(verified(archive['path'], archive['sha256'], slot))
    proof = runpy.run_path(str(HERE / 'geometry_controls.py'))
    records = verify_blockers(body, producer, terminal, truth, proof)
    compact = dict(body)
    compact.pop('blocker_evidence')
    compact_bytes = utf8_bytes(compact)
    outcome['actual_bound_blocker_evidence'] = records
    outcome['blocker_delivery_bytes'] = {
        'reference_compact_body_UTF8_bytes': baseline['wire']['body_UTF8_bytes'],
        'current_body_without_optional_blocker_table_UTF8_bytes': compact_bytes,
        'added_body_UTF8_bytes': outcome['wire']['body_UTF8_bytes'] - compact_bytes,
        'current_producer_blocker_packet_UTF8_bytes': utf8_bytes(producer['facts']['region_task']['blocker_evidence']),
    }
    outcome['baseline_compact_timing'] = baseline['timing']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--freeze', type=Path, default=NS / 'FROZEN.json')
    parser.add_argument('--output', type=Path, default=HERE / 'LIVE_REVIEW.json')
    args = parser.parse_args()
    original_qualify.__globals__.update(NS=NS, installed_binding=installed_binding, inspect_product=inspect)
    started = time.perf_counter_ns()
    outcome = {'schema': 'm4-bound-blocker-evidence-QP-live-review-v1', 'label': 'QP', 'issues': [],
               'cli_path': args.runtime / 'preflight/product_cli'}
    try:
        original_qualify(args.runtime, args.freeze, outcome)
    except Exception as error:
        outcome['issues'].append('product_or_qualification_semantic_evidence_failed')
        outcome['error'] = {'type': type(error).__name__, 'message': str(error)}
    outcome['cli_path'] = str(outcome['cli_path'])
    outcome['passed'] = not outcome['issues']
    outcome['reason'] = 'qualified' if outcome['passed'] else outcome['issues'][0]
    outcome['assessment_ms'] = ms(started, time.perf_counter_ns())
    write(args.output, outcome)
    print(json.dumps({key: outcome.get(key) for key in ('passed', 'reason', 'error', 'wire', 'denominator',
           'actual_bound_blocker_evidence', 'blocker_delivery_bytes')}, ensure_ascii=False))
    return 0 if outcome['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
