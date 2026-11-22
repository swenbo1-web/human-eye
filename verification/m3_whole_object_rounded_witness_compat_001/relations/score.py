"""Qualify fixed real stdio replays against the old legacy publication."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from statistics import median
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import CASES, EXTERNAL, EXPECTED_POINT, LABELS, compact, fixture, pin, read, require, save


MODES = ('standard', 'evidence')
PHASES = ('cold', 'hot')
ROLES = ('A0', 'A1', 'B')
LOCKED_SHA = {'A0': 'd39b0da9913dc31f55944a10b0299c15acc265a2d4d33d77a39e4798c65cb8c7',
              'A1': 'db381ce42b20e864d347c02ec1d41c847b3850d950e03dbbbec56abb9862c7f9'}
SOLVES = ('surface_pair_count', 'closed_solid_pair_count', 'spatial_pair_count')
SPANS = ('host.capture', 'scene.validate', 'observation.task_facts', 'mcp.content_encode',
         'mcp.wire_encode', 'mcp.stdio_write')


def crossing(fact, shadow):
    require(fact['status'] == 'measured' and fact['value'] == 'penetrating'
            and fact['certificate'] == 'transverse_boundary_interiors', 'closed_transverse_relation_changed')
    local = fact['local_evidence']
    require(local['type'] == 'transverse_triangle_crossing' and local['triangle_indices'] == [6, 4]
            and local['point_status'] == 'approximate', 'closed_transverse_certificate_changed')
    point = local['point_world_m']
    scalars = (type(point) is list and len(point) == 3
               and all(type(v) in (int, float) and math.isfinite(v) for v in point))
    if shadow:
        require(not scalars and point == [EXPECTED_POINT, EXPECTED_POINT], 'expected_old_dimension_regression_missing')
        local['point_world_m'] = list(EXPECTED_POINT)
    else:
        require(scalars and point == EXPECTED_POINT, 'finite_legacy_xyz_point_required')
    return point


def checked_body(label, response, source_sha, shadow):
    content = response['result']['content']
    require(response['result']['isError'] is False and len(content) == 1 and content[0]['type'] == 'text',
            'actual_single_text_success_required')
    text = content[0]['text']
    body = json.loads(text)
    normalized = deepcopy(body)
    binding = normalized['binding']
    frozen = fixture(label)['capture']
    require(compact(body).decode('utf8') == text and body['status'] == 'observed'
            and body['result_kind'] == 'task_query' and body['pair_order'] == 'A_to_B'
            and type(body['trace_id']) is str and body['trace_id']
            and body['execution_authority'] is False and body['unit'] == 'm'
            and body['coordinate_frame'] == 'world'
            and binding['runtime_source_sha256'] == source_sha and binding['scene_revision'] == frozen['revision']
            and binding['capture_scope'] == 'selected_objects'
            and [obj['name'] for obj in binding['objects']] == ['A', 'B']
            and set(body['facts']) == set(CASES[label]), 'scope_public_body_or_current_install_binding_changed')
    normalized['trace_id'] = '<trace>'
    binding['runtime_source_sha256'] = '<source>'
    points = {}
    for name in CASES[label]:
        if name == 'surface_proximity':
            continue
        fact = normalized['facts'][name]
        if label == 'separated':
            require(fact['status'] == 'measured' and fact['value'] == 'separated'
                    and 'local_evidence' not in fact, 'separation_no_local_point_required')
        else:
            points[name] = crossing(fact, shadow)
    return {'normalized': compact(normalized), 'point_world_m': points,
            'body_bytes': len(text.encode('utf8'))}


def arm(root, role, mode):
    directory = root / f'{role}_{mode}'
    index_path = directory / 'INDEX.json'
    index = read(index_path)
    binding = read(index['binding']['path'])
    require(pin(index['binding']['path']) == index['binding'], 'run_binding_bytes_changed')
    sha = binding['source_sha256']
    require(role not in LOCKED_SHA or sha == LOCKED_SHA[role], 'baseline_install_changed')
    require(index['planned'] == list(LABELS) and not index['unrun'] and index['passed']
            and index['mode'] == mode and len(index['actual']) == len(LABELS), 'registered_relation_arm_incomplete')
    results = {}
    for label, case in zip(LABELS, index['actual'], strict=True):
        path = directory / 'cases' / label
        require(case['label'] == label and case['passed'] and case['binding'] == index['binding']
                and case['production_evidence_option'] == (mode == 'evidence'), 'actual_case_identity_changed')
        events = [json.loads(line) for line in (path / 'worker/PRODUCT_EVENTS.jsonl').read_bytes().splitlines()]
        work_rows = [row['task_work'] for row in events if row.get('event') == 'observe']
        traces = [row['trace'] for row in events if row.get('event') == 'request_trace'
                  and row['trace']['operation'] == 'mcp.observe']
        require(len(work_rows) == len(traces) == 2, 'two_actual_requests_required')
        records = {}
        for phase, work, trace in zip(PHASES, work_rows, traces, strict=True):
            hold = case['observations'][phase]
            for key in ('TX', 'RX', 'request', 'response', 'public', 'receipt'):
                require(pin(hold[key]['path']) == hold[key], 'raw_artifact_receipt_changed')
            req, reply, receipt = (read(hold[key]['path']) for key in ('TX', 'RX', 'receipt'))
            require(req == fixture(label)['request'] and reply == read(hold['response']['path'])
                    and trace['annotations']['mcp_request_id'] == req['id']
                    and receipt['RX_sha256'] == hold['RX']['sha256']
                    and read(hold['capture_path']) == fixture(label)['capture'], 'request_capture_or_original_wire_changed')
            require(work['result_cache_hit'] is (phase == 'hot')
                    and any(work.get(key, 0) for key in SOLVES) is (phase == 'cold'), 'cold_or_hot_work_changed')
            record = checked_body(label, reply, sha, role == 'A1')
            require(record['body_bytes'] == hold['public_UTF8_bytes']
                    and reply['result']['content'][0]['text'].encode('utf8') == Path(hold['public']['path']).read_bytes(),
                    'public_text_not_original_wire')
            ord_num = '01' if phase == 'cold' else '02'
            service = read(path / f'worker/call_{ord_num}/RECEIPT.json')
            records[phase] = {**record, 'work': work, 'stdio_RTT_ns': receipt['elapsed_ns'],
                'service_elapsed_ns': service['service_elapsed_ns'], 'request_trace_ns': trace['duration_ns'],
                'stage_ns': {row['name']: row['duration_ns'] for row in trace['spans'] if row['name'] in SPANS},
                'wire': {'TX': hold['TX'], 'RX': hold['RX']}}
        require(records['cold']['normalized'] == records['hot']['normalized'], 'same_arm_hot_body_changed')
        results[label] = {'closure': case['held_EOF'], 'phases': records}
    return {'index': pin(index_path), 'source_sha256': sha, 'cases': results}


def score(root, shadow_only):
    roles = ROLES[:2] if shadow_only else ROLES
    arms = {(role, mode): arm(root, role, mode) for role in roles for mode in MODES}
    for mode in MODES:
        legacy = arms['A0', mode]
        for role in roles[1:]:
            for label in LABELS:
                for phase in PHASES:
                    prev = legacy['cases'][label]['phases'][phase]
                    next_ = arms[role, mode]['cases'][label]['phases'][phase]
                    require(next_['normalized'] == prev['normalized']
                            and next_['work'] == prev['work'], 'other_public_bytes_or_work_counters_changed')
    timing = {}
    for (role, mode), measured in arms.items():
        key = f'{role}_{mode}'
        timing[key] = {phase: {name: median(row['phases'][phase][name] for row in measured['cases'].values())
                               for name in ('stdio_RTT_ns', 'service_elapsed_ns', 'request_trace_ns')}
                       for phase in PHASES}
        for row in measured['cases'].values():
            for record in row['phases'].values():
                del record['normalized']
    units = len(MODES) * len(LABELS)
    return {'passed': True, 'candidate_scored': not shadow_only, 'processes_passed': len(roles) * units,
            'observations_passed': len(roles) * units * len(PHASES), 'shadow_malformed_body_count': 16,
            'shadow_malformed_fact_count': 20, 'original_shape_and_full_body_equal': not shadow_only,
            'selected_controls': list(LABELS), 'timings_median_ns': timing,
            'arms': {f'{role}_{mode}': data for (role, mode), data in arms.items()},
            'ignored_public_fields': ['trace_id', 'binding.runtime_source_sha256'],
            'notes': 'A1 shadow must exhibit only the old point nesting; timings include instrumentation and are serial.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shadow-only', action='store_true')
    args = parser.parse_args()
    result = score(EXTERNAL, args.shadow_only)
    save(EXTERNAL / ('SHADOW.json' if args.shadow_only else 'MATRIX.json'), result)
    print(json.dumps({key: val for key, val in result.items() if key != 'arms'}, ensure_ascii=False))
