"""Five ordinary installed observations on one owned qualified scene copy.

The controller reuses the accepted OPT1 lifecycle, wire meter and exact oracle.
Import and --prepare perform no Blender or product startup.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
import json
import math
from pathlib import Path
import struct
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
PREVIOUS = ROOT / 'verification/m4_surface_scan_001_opt1/engineering'
sys.path.insert(0, str(PREVIOUS))
from common import QUAL, WORKER, bind_snapshot, body, events, load_module, qualification_binding, save, sha
from sequence import ACTOR, RUNTIME, enrich, memory, snapshot
from verify_state import object_ids, verify


SLOTS = (
    ('base_default', 'BASE', None, 71, 112),
    ('base_brief', 'BASE', 'brief', 71, 0),
    ('base_full', 'BASE', 'full', 71, 0),
    ('edit_default', 'EDIT', None, 72, 10),
    ('edit_full', 'EDIT', 'full', 72, 0),
)


def bits(value):
    return struct.pack('>d', value)


def check_deadline(deadline_ns, stage):
    if time.perf_counter_ns() >= deadline_ns:
        raise TimeoutError('original_590s_deadline_' + stage)


def request(label, detail):
    arguments = {'session_id': 'm4-surface-scan-compact-engineering', 'include_image': False,
                 'query': {'mode': 'surface_scan', 'threshold_m': .002}}
    if detail is not None:
        arguments['response_detail'] = detail
    return {'jsonrpc': '2.0', 'id': label, 'method': 'tools/call',
            'params': {'name': 'human_eye_scene_observe', 'arguments': arguments}}


def recover(result):
    if 'display_encoding' not in result:
        return result['matches']
    assert result['display_encoding'] == 'surface-scan-task-table-v1'
    assert result['object_table_scope'] == 'matched_endpoints_only'
    columns = ['object_a', 'object_b', 'object_a_ref', 'object_b_ref', 'distance_m', 'distance_mm']
    assert result['match_columns'] == columns
    objects = result['objects']
    assert len({row['id'] for row in objects}) == len(objects)
    common = result.get('match_metadata', {})
    exceptions = {row['match_index']: row['metadata'] for row in result.get('match_exceptions', [])}
    assert len(exceptions) == len(result.get('match_exceptions', []))
    assert all(type(index) is int and 0 <= index < len(result['matches']) for index in exceptions)
    restored = []
    used = set()
    for index, row in enumerate(result['matches']):
        assert len(row) == len(columns)
        name_a, name_b, ref_a, ref_b, distance, mm = row
        assert type(ref_a) is int and type(ref_b) is int
        assert 0 <= ref_a < len(objects) and 0 <= ref_b < len(objects)
        assert objects[ref_a]['name'] == name_a and objects[ref_b]['name'] == name_b
        assert type(distance) is float and math.isfinite(distance)
        assert type(mm) in (int, float) and bits(float(mm)) == bits(distance * 1000.)
        used.update((ref_a, ref_b))
        restored.append({**common, **exceptions.get(index, {}),
                         'objects': [objects[ref_a], objects[ref_b]], 'distance_m': distance})
    assert used == set(range(len(objects)))
    return restored


def verify_facts(result, work, truth, source, source_sha, compact):
    """Independently check all pairs and exact frozen threshold membership."""
    expected = {tuple(sorted((row['object_a'], row['object_b']))): row for row in truth['pairs']}
    ids = object_ids(source)
    assert len(expected) == 276 and len(ids) == 24
    assert result['result_kind'] == 'surface_scan' and result['status'] == 'complete'
    assert result['scope'] == 'all_scene_mesh_triangle_surfaces'
    assert result['threshold_m'] == .002 and result['unit'] == 'm'
    assert result['coordinate_frame'] == 'world' and result['execution_authority'] is False
    assert result['binding']['runtime_source_sha256'] == source_sha
    assert result['scope_issues'] == result['unsupported_objects'] == result['unresolved'] == []
    assert result['delivery']['complete'] is True
    assert result['delivery']['scope'] == 'reducer_result_before_service_binding_and_trace'
    assert ('display_encoding' in result) is compact
    dispositions = work['dispositions']
    assert len(dispositions) == 276
    counts = Counter()
    measured = {}
    seen = set()
    for disposition in dispositions:
        pair = tuple(sorted(ids[oid] for oid in disposition['object_ids']))
        assert pair not in seen and pair in expected
        seen.add(pair)
        state = disposition['status']
        assert state in ('bound_excluded', 'measured_match', 'measured_nonmatch')
        counts[state] += 1
        assert (state == 'measured_match') == expected[pair]['matches_threshold']
        exact = expected[pair]['exact_squared_distance_m2']
        squared = Fraction(int(exact['numerator']), int(exact['denominator']))
        if state == 'bound_excluded':
            lower = disposition['lower_bound_m']
            assert lower > .002 and Fraction(lower) ** 2 <= squared
        else:
            actual = disposition['distance_m']
            assert abs(actual - math.sqrt(float(squared))) <= 1e-10
            measured[pair] = actual
    actual = recover(result)
    public = set()
    for row in actual:
        pair = tuple(sorted(obj['name'] for obj in row['objects']))
        assert pair not in public and expected[pair]['matches_threshold']
        public.add(pair)
        for obj in row['objects']:
            assert ids[obj['id']] == obj['name']
        assert bits(row['distance_m']) == bits(measured[pair])
    assert public == {pair for pair, row in expected.items() if row['matches_threshold']}
    assert result['delivery']['matches_total'] == result['delivery']['delivered_matches'] == len(public)
    coverage = result['coverage']
    assert coverage['objects'] == 24 and coverage['total_pairs'] == 276
    assert coverage['catalog_scope_confirmed'] is True
    for state in ('bound_excluded', 'measured_match', 'measured_nonmatch', 'unknown', 'deferred'):
        assert coverage[state] == counts[state]
    report = {'passed': True, 'all_pair_partitions_verified': len(seen), 'matches': len(public),
              'raw_distance_bits_equal_private_dispositions': True, 'FP': 0, 'FN': 0,
              'duplicate_pairs': 0, 'full_witnesses_checked': 0,
              'oracle': 'frozen independent exact binary64 triangle-surface truth'}
    if not compact:
        report['detailed_verification'] = verify(result, work, truth, source, source_sha)
        report['full_witnesses_checked'] = 2 * len(public)
    return report


def business(peer, slot, output, audit_path, source, source_sha, native_pid, runtime_pid, deadline_ns):
    label, state, detail, expected_matches, expected_kernels = slot
    req = request(label, detail)
    row = {'state': label, 'truth_state': state, 'response_detail': detail,
           'expected_matches': expected_matches, 'expected_new_kernel_calls': expected_kernels,
           'request': req, 'started_ns': time.perf_counter_ns(), 'errors': []}
    save(output / (label + '_REQUEST.json'), req)
    try:
        check_deadline(deadline_ns, 'before_business_' + label)
        row['memory_before'] = [memory(native_pid), memory(runtime_pid)]
        row['started_ns'] = time.perf_counter_ns()
        remaining_s = (deadline_ns - row['started_ns']) / 1e9
        row['response'] = peer.call(req, timeout_s=min(35., remaining_s))
        row['ended_ns'] = time.perf_counter_ns()
        row['stdio'] = dict(peer.records[-1])
        row['body'] = body(row['response'])
        text = row['response']['result']['content'][0]['text']
        row['business_text_utf8_bytes'] = len(text.encode('utf8'))
        row['byte_budget_scope'] = 'entire actual MCP text content including objects, fields and binding'
        row['memory_after'] = [memory(native_pid), memory(runtime_pid)]
        check_deadline(deadline_ns, 'before_business_QA_' + label)
        trace_id = row['body']['trace_id']
        observed = [event for event in events(audit_path)
                    if event.get('event') == 'observe' and event.get('trace_id') == trace_id]
        assert len(observed) == 1
        work = observed[0]['task_work']
        truth = json.loads((QUAL / (state + '_TRUTH.json')).read_bytes())
        compact = detail != 'full'
        row['verification'] = verify_facts(row['body'], work, truth, source, source_sha, compact)
        assert row['verification']['matches'] == expected_matches
        assert work['kernel_calls'] == expected_kernels
        if compact:
            assert row['business_text_utf8_bytes'] <= 10 * 1024
        check_deadline(deadline_ns, 'after_business_verification_' + label)
    except BaseException as error:
        row.setdefault('ended_ns', time.perf_counter_ns())
        row['errors'].append({'type': type(error).__name__, 'message': str(error),
                              'traceback': traceback.format_exc()})
    row['complete_client_request_ns'] = row['ended_ns'] - row['started_ns']
    row['quality_check_end_ns'] = time.perf_counter_ns()
    save(output / (label + '_RESPONSE_RECEIPT.json'), row)
    return row


def compare_state(rows):
    detailed = next(row['body'] for row in rows if row['response_detail'] == 'full')
    for row in rows:
        value = row['body']
        assert value['binding'] == detailed['binding']
        for key, target in detailed.items():
            if key not in ('matches', 'trace_id'):
                assert value[key] == target, (row['state'], key)
        actual = recover(value)
        assert len(actual) == len(detailed['matches'])
        for restored, full in zip(actual, detailed['matches']):
            assert restored['objects'] == full['objects']
            assert bits(restored['distance_m']) == bits(full['distance_m'])
            for key, target in full.items():
                if key not in ('objects', 'distance_m', 'point_a_world', 'point_b_world'):
                    assert restored[key] == target, (row['state'], key)
            assert set(restored) == set(full) - {'point_a_world', 'point_b_world'} or row['response_detail'] == 'full'
    return {'passed': True, 'same_state_binding_equal': True,
            'match_order_id_name_raw_bits_equal': True,
            'all_original_top_level_fields_except_trace_equal': True,
            'trace_comparison': 'request-local trace identities may differ'}


def run_candidate(output, ready, binding):
    started = time.perf_counter_ns()
    deadline = started + 590 * 10**9
    result = {'started_ns': started, 'deadline_ns': deadline, 'business': [], 'errors': [],
              'planned_business_rows': len(SLOTS), 'automatic_retries': 0,
              'timing_stages_ns': {}, 'host_path': 'BlenderMCPHost', 'registered_pose_applied': False}
    native = peer = None
    runtime_handle = None
    runtime = load_module('_compact_runtime_proof', RUNTIME)
    helper = load_module('_compact_metered_native', PREVIOUS / 'pose_native_metered.py')
    actor = load_module('_compact_stdio_peer', ACTOR)
    try:
        assert all(sha(path) == value for path, value in binding['files'].items())
        mark = time.perf_counter_ns()
        native = helper.NativeSession.start(blender='D:/Tools/blender5.2/blender.exe',
            asset=QUAL / 'assembly.blend', workspace=output / 'native', deadline_ns=deadline,
            condition='P', max_calls=128, expected_asset_sha256=binding['qualification']['asset_sha256'],
            qa_pose_patch=WORKER / 'POSE_PATCH.json')
        result['timing_stages_ns']['owned_Blender_start'] = time.perf_counter_ns() - mark
        config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': ready['install_root'], 'state_file': str(output / 'state.json'),
                  'audit_file': str(output / 'audit.jsonl'), 'request_budget_s': 30.,
                  'expected_identity': {'source_sha256': ready['source_sha256']},
                  'blender': {'host': native.host, 'port': native.port, 'timeout_s': 30.}}
        save(output / 'config.json', config)
        mark = time.perf_counter_ns()
        peer = actor.Peer(dict(ready, group='C', product_config=output / 'config.json'), output / 'product')
        initialized = peer.call({'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'surface-scan-compact-engineering', 'version': '001'}}})
        save(output / 'INITIALIZE.json', initialized)
        identity = initialized['result']['_meta']['human_eye']
        assert identity['source_sha256'] == ready['source_sha256']
        assert identity['source_kind'] == 'installed_distribution'
        peer.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        save(output / 'TOOLS.json', peer.call({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'}))
        assert peer.call({'jsonrpc': '2.0', 'id': 'ping', 'method': 'ping'})['result'] == {}
        assert events(native.workspace / 'WORKER_EVENTS.jsonl') == []
        result['metadata_zero_host_RPC'] = True
        result['timing_stages_ns']['product_start_and_metadata'] = time.perf_counter_ns() - mark
        pids = {row['pid'] for row in events(output / 'audit.jsonl') if row.get('event') == 'request_trace'}
        assert len(pids) == 1
        runtime_pid = pids.pop()
        proof, runtime_handle = runtime._windows_runtime_proof(peer.process, runtime_pid, deadline)
        proof['scope'] = 'after metadata and before QA snapshots or business geometry'
        save(output / 'RUNTIME_PROOF.json', proof)
        assert proof['confirmed']
        mark = time.perf_counter_ns()
        check_deadline(deadline, 'before_base_QA_snapshot')
        base = snapshot(native, 'base', output)
        check_deadline(deadline, 'after_base_QA_snapshot')
        result['timing_stages_ns']['base_QA_snapshot'] = time.perf_counter_ns() - mark
        edited = None
        for index, slot in enumerate(SLOTS):
            if index == 3:
                mark = time.perf_counter_ns()
                check_deadline(deadline, 'before_registered_pose_QA')
                save(output / 'POSE_ADVANCE.json', native.qa_advance(timeout_s=30))
                result['registered_pose_applied'] = True
                result['timing_stages_ns']['registered_pose_edit'] = time.perf_counter_ns() - mark
                mark = time.perf_counter_ns()
                check_deadline(deadline, 'before_edit_QA_snapshot')
                edited = snapshot(native, 'edit', output)
                check_deadline(deadline, 'after_edit_QA_snapshot')
                result['timing_stages_ns']['edit_QA_snapshot'] = time.perf_counter_ns() - mark
            source = edited if slot[1] == 'EDIT' else base
            check_deadline(deadline, 'before_business_dispatch_' + slot[0])
            row = business(peer, slot, output, output / 'audit.jsonl', source,
                           ready['source_sha256'], native.ready['pid'], runtime_pid, deadline)
            result['business'].append(row)
            if row['errors']:
                raise RuntimeError('business_failed_no_replacement_' + slot[0])
        result['same_state_comparisons'] = [compare_state(result['business'][:3]),
                                            compare_state(result['business'][3:])]
        assert result['business'][0]['body']['binding'] != result['business'][3]['body']['binding']
        result['pose_binding_changed'] = True
    except BaseException as error:
        result['errors'].append({'stage': 'candidate', 'type': type(error).__name__,
                                 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        if peer is not None:
            try:
                result['product_close'] = peer.close()
            except BaseException as error:
                result['errors'].append({'stage': 'product_close', 'error': repr(error)})
            try:
                result['runtime_exit'] = runtime._runtime_exit(runtime_handle)
                assert result['runtime_exit']['confirmed'] and result['runtime_exit']['exit_code'] == 0
            except BaseException as error:
                result['errors'].append({'stage': 'runtime_exit', 'error': repr(error)})
        if native is not None:
            try:
                result['native_close'] = native.close()
                result['worker_closed'] = native.status()['closed']
                assert result['native_close']['process_reaped'] and result['native_close']['exit_code'] == 0
                assert result['native_close']['error'] is None
                closed = result['worker_closed']
                assert not closed['poisoned']
                assert closed['qa_patch_applied'] == result['registered_pose_applied']
                assert closed['final_geometry_fingerprint'] == closed['accepted_geometry_fingerprint']
                wire = json.loads((native.workspace / 'WIRE/INDEX.json').read_bytes())
                audit = events(output / 'audit.jsonl')
                for row in result['business']:
                    try:
                        enrich(row, native, audit, wire)
                        assert row['actual_host_RPC'] == 1
                        row['display_encode_spans_ns'] = [span['duration_ns'] for span in row['trace']['spans']
                                                          if span['name'] == 'mcp.content_encode']
                        assert len(row['display_encode_spans_ns']) == 1
                        row['compact_projection_spans_ns'] = [span['duration_ns'] for span in row['trace']['spans']
                                                              if span['name'] == 'mcp.surface_scan_compact_projection']
                        assert len(row['compact_projection_spans_ns']) == int(row['response_detail'] != 'full')
                        row['display_timing_scope'] = 'actual pure compact projection span nested in inclusive MCP content-encoding span'
                    except BaseException as error:
                        row['errors'].append({'stage': 'terminal_evidence', 'type': type(error).__name__,
                                              'message': str(error), 'traceback': traceback.format_exc()})
                business_sequences = {part['sequence'] for row in result['business'] for part in row.get('wire', [])}
                result['all_host_RPC_including_QA_and_close'] = len(wire)
                result['outside_business_RPC'] = [part for part in wire if part['sequence'] not in business_sequences]
                result['outside_business_scope'] = 'QA initial and edited snapshots, registered pose advance, backend close'
                result['all_worker_events'] = events(native.workspace / 'WORKER_EVENTS.jsonl')
            except BaseException as error:
                result['errors'].append({'stage': 'native_close_and_evidence', 'error': repr(error),
                                         'traceback': traceback.format_exc()})
        try:
            result['source_files_unchanged'] = all(sha(path) == value for path, value in binding['files'].items())
        except BaseException as error:
            result['source_files_unchanged'] = False
            result['errors'].append({'stage': 'source_files_check', 'error': repr(error)})
        result['execution_counts'] = {
            'attempted': len(result['business']),
            'completed': sum(not row['errors'] for row in result['business']),
            'failed': sum(bool(row['errors']) for row in result['business']),
            'not_attempted': len(SLOTS) - len(result['business']),
        }
        try:
            check_deadline(deadline, 'before_final_verdict')
        except TimeoutError as error:
            result['errors'].append({'stage': 'final_verdict', 'type': type(error).__name__,
                                     'message': str(error)})
        result['passed'] = (not result['errors'] and result['source_files_unchanged']
                            and len(result['business']) == len(SLOTS)
                            and all(not row['errors'] and row.get('verification', {}).get('passed')
                                    for row in result['business']))
        result['business_and_owned_cleanup_end_ns'] = time.perf_counter_ns()
        result['prefix_wall_ns'] = result['business_and_owned_cleanup_end_ns'] - started
        result['passed_scope'] = 'candidate checks before RESULTS write; FINAL_TIMING.accepted_success is the authoritative complete-close verdict'
        save(output / 'RESULTS.json', result)
        receipts_closed = time.perf_counter_ns()
        complete_close_within_deadline = receipts_closed < deadline
        full = {'started_ns': started, 'business_receipts_closed_ns': receipts_closed,
                'full_session_wall_ns': receipts_closed - started,
                'original_deadline_ns': deadline,
                'complete_business_write_close_within_original_deadline': complete_close_within_deadline,
                'accepted_success': result['passed'] and complete_close_within_deadline,
                'scope': 'before owned startup through five requests, QA verification, owned cleanup and RESULTS file write/close',
                'durability': 'existing buffered RESULTS write and close; fsync unmeasured'}
        publication_start = time.perf_counter_ns()
        save(output / 'FINAL_TIMING.json', full)
        publication_closed = time.perf_counter_ns()
        save(output / 'TIMING_PUBLICATION.json', {'started_ns': publication_start,
            'closed_ns': publication_closed, 'publication_ns': publication_closed - publication_start,
            'scope': 'FINAL_TIMING write/close; this publication receipt itself excluded'})
        result['passed'] = full['accepted_success']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ready', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(HERE)
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'PLANNED_ROWS.json', [{'slot': index, 'label': slot[0], 'state': slot[1],
         'response_detail': slot[2], 'expected_matches': slot[3], 'expected_new_kernels': slot[4],
         'status': 'not_attempted'} for index, slot in enumerate(SLOTS, 1)])
    try:
        qualification, promised = qualification_binding()
        ready = json.loads(args.ready.read_bytes())
        assert ready['commit'] == args.commit and ready['source_sha256'] == args.source_sha256
        fixed = json.loads(Path(ready['fixed_inputs']).read_bytes())
        paths = [Path(__file__), args.ready, ACTOR, RUNTIME, QUAL / 'export_snapshot.py',
                 ROOT / 'verification/native_plugin_complex_003/actor.py',
                 ROOT / 'verification/native_plugin_complex_003/reused/accepted_native.py',
                 ROOT / 'verification/m4_grooved_rail_transfer_001/oracle/exact_geometry.py',
                 *[PREVIOUS / name for name in ('common.py', 'sequence.py', 'verify_state.py',
                                              'pose_native_metered.py', 'wire_meter.py')]]
        files = {str(path.resolve()): sha(path) for path in paths}
        files.update(promised)
        for row in fixed['manifest']:
            path = Path(ready['install_root']) / row['path']
            assert sha(path) == row['sha256']
            files[str(path)] = row['sha256']
        binding = {'schema': 'surface-scan-compact-engineering-inputs-v1', 'ready': ready,
                   'qualification': qualification, 'files': files, 'planned_business_rows': len(SLOTS),
                   'cold_scope': 'fresh owned runtime and empty measurement cache; QA source snapshot precedes scan',
                   'request_budget_s': 30, 'client_timeout_s': 35, 'new_model_consumers': 0,
                   'automatic_retries': 0, 'shared_GUI_calls': 0,
                   'learning_context': {'context_bound': False, 'host_epoch': 5, 'rebind_required': True},
                   'prepared_utc': datetime.now(timezone.utc).isoformat()}
        save(output / 'INPUT_BINDINGS.json', binding)
    except BaseException as error:
        failure = {'stage': 'offline_preparation', 'type': type(error).__name__,
                   'message': str(error), 'traceback': traceback.format_exc(),
                   'new_Blender_product_model_API_starts': 0}
        save(output / 'PREPARATION_FAILURE.json', failure)
        save(output / 'PREPARATION_RESULT.json', {'passed': False,
             'execution_counts': {'attempted': 0, 'completed': 0, 'failed': 0, 'not_attempted': len(SLOTS)},
             'planned_rows_retained': True, 'failure': failure, 'output_not_reusable': True})
        print(json.dumps({'passed': False, 'preparation_failed': True, 'planned_rows': len(SLOTS),
                          'not_attempted': len(SLOTS), 'output': str(output)}, ensure_ascii=False))
        return 1
    if not args.run:
        print(json.dumps({'prepared_only': True, 'planned_business_rows': 5, 'live_calls': 0}))
        return 0
    result = run_candidate(output, ready, binding)
    print(json.dumps({'passed': result['passed'], 'counts': result['execution_counts'],
                      'errors': result['errors'], 'output': str(output)}, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
