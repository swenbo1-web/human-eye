"""Read-only replay and independent fact/counter reconciliation of FIX2 C.

Reuses the fixed qualification oracle, without executing Blender, a product
process or a model. Only derived files beside this script are written.
"""

from collections import Counter
import contextlib
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BATCH = HERE.parents[1]
ROOT = BATCH.parents[1]
CELL = BATCH / 'episodes/C'
FIX1 = ROOT / 'verification/m4_surface_scan_continuity_001_fix1'
INPUTS = {}
CHECKS = []


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def raw(path):
    path = Path(path)
    data = path.read_bytes()
    INPUTS[path.relative_to(ROOT).as_posix()] = {'bytes': len(data), 'sha256': digest(data)}
    return data


def read(path):
    return json.loads(raw(path))


def check(condition, label):
    CHECKS.append(label)
    if not condition:
        raise AssertionError(label)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')


def bits(value):
    return struct.pack('>d', value)


def load(name, path):
    raw(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def prefix_only(native, sequence):
    """Reject any future WIRE payload read during the actual fixed reader call."""
    original_read, original_open = Path.read_bytes, Path.open
    denied = []
    wire = native / 'WIRE'

    def allowed(path):
        try:
            relative = path.relative_to(wire)
        except ValueError:
            return
        if len(relative.parts) > 1 and relative.parts[0].isdigit() and int(relative.parts[0]) > sequence:
            denied.append(str(path))
            raise AssertionError('future_wire_payload_' + str(path))

    def observe(path):
        allowed(path)
        data = original_read(path)
        if path.is_relative_to(ROOT):
            INPUTS[path.relative_to(ROOT).as_posix()] = {'bytes': len(data), 'sha256': digest(data)}
        return data

    def open_checked(path, *args, **kwargs):
        allowed(path)
        return original_open(path, *args, **kwargs)

    with patch.object(Path, 'read_bytes', observe), patch.object(Path, 'open', open_checked):
        yield denied


def table(body, label):
    check(body['display_encoding'] == 'surface-scan-task-table-v1', label + ' compact_schema')
    check(body['match_columns'] == ['object_a', 'object_b', 'object_a_ref', 'object_b_ref', 'distance_m', 'distance_mm'], label + ' columns')
    check(body['object_table_scope'] == 'matched_endpoints_only', label + ' endpoint_scope')
    result = {}
    for row in body['matches']:
        check(len(row) == 6, label + ' six_columns')
        first, second, ref_a, ref_b, distance, mm = row
        check(type(ref_a) is int and type(ref_b) is int, label + ' integer_refs')
        check(body['objects'][ref_a]['name'] == first and body['objects'][ref_b]['name'] == second, label + ' ref_names')
        check(type(distance) is float and math.isfinite(distance), label + ' finite_raw_m')
        check(type(mm) in (float, int) and bits(float(mm)) == bits(distance * 1000.), label + ' exact_derived_mm')
        pair = tuple(sorted((first, second)))
        check(pair not in result and distance <= .002, label + ' unique_threshold_member')
        result[pair] = distance
    return result


def pair_rows(first, second):
    return [{'pair': list(pair), 'before_mm': first.get(pair) * 1000. if pair in first else None,
             'after_mm': second.get(pair) * 1000. if pair in second else None}
            for pair in sorted(set(first) | set(second))
            if pair not in first or pair not in second or bits(first[pair]) != bits(second[pair])]


def main():
    prep = read(BATCH / 'PREPARATION.json')
    reservation = read(BATCH / 'ENGINEERING_STARTED.json')
    check(reservation['preparation_commit'] == '1511af696b564a0b261b70d5f0562325daa1f2a7', 'fixed_preparation')
    qualification_path = FIX1 / 'qualification/verify_continuity.py'
    check(digest(raw(qualification_path)) == prep['external_sha256'][str(qualification_path)], 'fixed_qualification_source')
    qualification = load('_fix2_postrun_facts_qualification', qualification_path)
    result = read(CELL / 'RESULTS.json')
    initial = read(CELL / 'owner/INITIAL.json')
    edited = read(CELL / 'owner/EDIT.json')
    check(canonical(edited) == canonical(result['registered_pose']['snapshot']), 'registered_EDIT_readback_exact')
    check(initial['unit_scale_m'] == edited['unit_scale_m'] == 1., 'fixed_units')
    check(len(initial['objects']) == len(edited['objects']) == 24, 'complete_source_object_counts')
    changed_matrices = []
    for before, after in zip(initial['objects'], edited['objects']):
        check(before['name'] == after['name'], 'same_source_object')
        check(canonical(before['vertices_local']) == canonical(after['vertices_local']), 'local_vertices_unchanged_' + before['name'])
        check(canonical(before['faces']) == canonical(after['faces']), 'topology_unchanged_' + before['name'])
        if canonical(before['matrix_world']) != canonical(after['matrix_world']):
            changed_matrices.append(before['name'])
    check(changed_matrices == ['Obj_008'], 'only_registered_object_matrix_changed')
    audit = [json.loads(line) for line in raw(CELL / 'owner/audit.jsonl').splitlines()]
    events = [json.loads(line) for line in raw(CELL / 'owner/native/WORKER_EVENTS.jsonl').splitlines()]
    check([row['turn'] for row in result['business']] == ['BASE', 'REPEAT', 'EDIT'], 'three_actual_turns')
    sources = {'BASE': initial, 'EDIT': edited}
    reports, rows, maps, dispositions = [], [], [], []
    for index, row in enumerate(result['business'], 1):
        turn = row['turn']
        check(row['state'] == ('EDIT' if turn == 'EDIT' else 'BASE'), turn + ' source_state')
        check(row['execution_state'] == 'succeeded' and row['qualification_state'] == 'passed', turn + ' execution_and_qualification')
        check(not row['errors'] and not row['qualification_errors'], turn + ' no_errors')
        turn_file = read(CELL / ('TURN_' + turn + '.json'))
        check(turn_file['started_ns'] == row['started_ns'] and turn_file['ended_ns'] == row['ended_ns'], turn + ' original_window_bound')
        response = read(CELL / ('owner/tool_%02d/RESPONSE.json' % index))
        request = read(CELL / ('owner/tool_%02d/REQUEST.json' % index))
        check(canonical(request) == canonical(row['request']) and canonical(response) == canonical(row['response']), turn + ' owner_originals')
        body = json.loads(response['result']['content'][0]['text'])
        check(canonical(body) == canonical(row['body']), turn + ' raw_response_body')
        window = [event for event in events if type(event.get('started_ns')) is int
                  and row['started_ns'] <= event['started_ns'] <= row['ended_ns']]
        check(len(window) == 1, turn + ' single_capture_window')
        host = window[0]
        check(type(host['elapsed_ns']) is int and host['elapsed_ns'] > 0 and host['started_ns'] + host['elapsed_ns'] <= row['ended_ns'], turn + ' complete_host_window')
        check(row['qualification_started_ns'] > result['cleanup']['close']['ended_ns'], turn + ' qualified_after_finish')
        check(row['qualification_started_ns'] > row['ended_ns'], turn + ' separate_qualification_window')
        with prefix_only(CELL / 'owner/native', host['sequence']) as denied:
            captured = qualification.read_capture(CELL / 'owner/native', host)
            verified = qualification.verify_c_turn(body, audit, window, sources[row['state']], turn, request, capture=captured)
        check(denied == [], turn + ' no_future_payload_read')
        check(canonical(verified) == canonical(row['verification']), turn + ' stored_qualification_exact_replay')
        check(verified['source_report']['rich_source_metadata_verified'] is False, turn + ' missing_rich_unverified')
        check(all(part['sequence'] <= host['sequence'] for part in captured['wire_sources']), turn + ' capture_prefix')
        check(all(part['sequence'] <= host['sequence'] for part in captured['resource_origins']), turn + ' resource_prefix')
        reports.append(verified)
        matched = table(body, turn)
        maps.append(matched)
        observations = [part for part in audit if part.get('event') == 'observe' and part.get('trace_id') == body['trace_id']]
        traces = [part['trace'] for part in audit if part.get('event') == 'request_trace' and part.get('trace_id') == body['trace_id']]
        check(len(observations) == len(traces) == 1, turn + ' unique_private_trace')
        work = observations[0]['task_work']
        names = {part['object_id']: part['name'] for part in captured['delta']['capture']['coverage']}
        partition = {tuple(sorted(names[oid] for oid in part['object_ids'])): part for part in work['dispositions']}
        check(len(partition) == 276, turn + ' all_pair_dispositions')
        dispositions.append(partition)
        rows.append({'turn': turn, 'raw_body_sha256': digest(response['result']['content'][0]['text'].encode('utf8')),
                     'model_facing_tool_text_bytes': len(response['result']['content'][0]['text'].encode('utf8')),
                     'business_started_ns': row['started_ns'], 'business_ended_ns': row['ended_ns'],
                     'host_sequence': host['sequence'], 'host_started_ns': host['started_ns'], 'host_elapsed_ns': host['elapsed_ns'],
                     'qualification_started_ns': row['qualification_started_ns'], 'qualification_ended_ns': row['qualification_ended_ns'],
                     'source_schema': verified['source_report']['schema'], 'rich_source_metadata_verified': False,
                     'source_geometry_sha256': verified['source_report']['observed_geometry_sha256'],
                     'binding': body['binding'], 'matched_endpoint_objects': len(body['objects']),
                     'matches': len(matched), 'coverage': body['coverage'], 'FP': verified['facts']['FP'], 'FN': verified['facts']['FN'],
                     'kernel_calls': work['kernel_calls'], 'pair_calls': work['pair_calls'], 'pair_cache_hits': work['cache_hits'],
                     'result_cache_hit': work['result_cache_hit'], 'measurement_cache_before': work['measurement_cache_before'],
                     'measurement_cache_after': work['measurement_cache_after'], 'acquisition_work': work['acquisition_work'],
                     'capture_resources_sent': len(captured['delta']['resources']),
                     'resolved_resources': verified['capture_report']['resolved_resource_count'],
                     'wire_capture_sequences': [part['sequence'] for part in captured['wire_sources']],
                     'resource_origin_sequences': sorted({part['sequence'] for part in captured['resource_origins']}),
                     'status_counts': dict(Counter(part['status'] for part in partition.values())),
                     'trace_spans': traces[0]['spans'], 'thin_wall_ns': row['thin']['wall_ns']})
    sequence = qualification.verify_c_sequence(reports)
    check(canonical(sequence) == canonical(result['sequence_verification']), 'sequence_replay_exact')
    check(pair_rows(maps[0], maps[1]) == [], 'REPEAT_all_matching_raw_distances_equal')
    changed = pair_rows(maps[0], maps[2])
    added = [item for item in changed if item['before_mm'] is None]
    removed = [item for item in changed if item['after_mm'] is None]
    check([item['pair'] for item in added] == [['Obj_002', 'Obj_008']] and not removed, 'actual_match_membership_change')
    transitions = [{'pair': list(pair), 'before_status': dispositions[0][pair]['status'], 'after_status': dispositions[2][pair]['status'],
                    'before_distance_m': dispositions[0][pair].get('distance_m'), 'after_distance_m': dispositions[2][pair].get('distance_m')}
                   for pair in sorted(dispositions[0]) if dispositions[0][pair]['status'] != dispositions[2][pair]['status']]
    for pair in dispositions[0]:
        if 'Obj_008' not in pair:
            check(canonical(dispositions[0][pair]) == canonical(dispositions[2][pair]), 'unchanged_other_object_pair_' + '-'.join(pair))
    check([row['kernel_calls'] for row in rows] == [112, 0, 10], 'actual_kernel_sequence')
    check([row['capture_resources_sent'] for row in rows] == [24, 0, 0], 'actual_resource_delivery_sequence')
    raw(Path(__file__).resolve())
    for path, record in INPUTS.items():
        data = (ROOT / path).read_bytes()
        check(len(data) == record['bytes'] and digest(data) == record['sha256'], 'input_stable_' + path)
    output = {'schema': 'fix2_actual_three_turn_facts_audit_v1', 'status': 'pass_as_actual_facts_replay',
              'preparation_commit': reservation['preparation_commit'], 'checks': len(CHECKS), 'check_labels': CHECKS,
              'rows': rows, 'sequence': sequence, 'changed_matrix_objects': changed_matrices,
              'matching_pair_changes': changed, 'added_matching_pairs': added, 'removed_matching_pairs': removed,
              'disposition_status_changes': transitions, 'source_scope': 'Recorded complete geometry projection and fixed host guard; absent rich source fields remain unrecorded.',
              'EDIT_binding_fields_changed': [key for key in rows[0]['binding'] if rows[0]['binding'][key] != rows[2]['binding'][key]],
              'verification_scope': 'Replays the fixed independent exact-truth qualification; no new geometric solver or experiment.',
              'new_Blender_model_provider_API_calls': 0,
              'cost_scope': 'Engineering counters and nested trace spans only. No model memory, AI task benefit or cash cost is measured.',
              'inputs': [{'path': path, **record} for path, record in sorted(INPUTS.items())]}
    (HERE / 'RESULTS.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'status': output['status'], 'checks': len(CHECKS), 'input_files': len(INPUTS),
                      'matches': [row['matches'] for row in rows], 'kernels': [row['kernel_calls'] for row in rows],
                      'added': added, 'removed': removed, 'new_live': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
