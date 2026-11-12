"""Exactly five ordinary installed MCP sequences, each cold/repeat/pose-edit."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, QUAL, ROOT, WORKER, bind_snapshot, body, events, load_module, request, save, sha
from verify_state import verify


ACTOR = ROOT / 'verification/m1_task_entry_001_eval/actor.py'
RUNTIME = ROOT / 'verification/m1_task_entry_001_eval/preflight_client.py'


def memory(pid):
    """A process-lifetime peak, explicitly separate from a request-local peak."""
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x410, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        value = Counters()
        value.cb = ctypes.sizeof(value)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(value), value.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {'pid': pid, 'observed_ns': time.perf_counter_ns(),
                'working_set_bytes': value.WorkingSetSize,
                'peak_working_set_bytes': value.PeakWorkingSetSize,
                'peak_scope': 'process_lifetime_peak', 'source': 'GetProcessMemoryInfo'}
    finally:
        kernel.CloseHandle(handle)


def snapshot(native, state, output):
    receipt = native.run((QUAL / 'export_snapshot.py').read_text(encoding='utf8'), timeout_s=30)
    save(output / (state + '_SNAPSHOT_RECEIPT.json'), receipt)
    assert receipt['response']['status'] == 'success', receipt
    actual = json.loads(receipt['response']['result']['result'])
    reference = json.loads((QUAL / (state.upper() + '_SNAPSHOT.json')).read_bytes())
    save(output / (state + '_ACTUAL_SNAPSHOT.json'), actual)
    save(output / (state + '_SOURCE_BINDING.json'), bind_snapshot(actual, reference))
    return actual


def business(peer, state, output, native_pid, runtime_pid):
    req = request(state)
    row = {'state': state, 'request': req, 'started_ns': time.perf_counter_ns(), 'errors': []}
    save(output / (state + '_REQUEST.json'), req)
    try:
        row['memory_before'] = [memory(native_pid), memory(runtime_pid)]
        row['started_ns'] = time.perf_counter_ns()
        row['response'] = peer.call(req, timeout_s=35)
        row['ended_ns'] = time.perf_counter_ns()
        row['stdio'] = dict(peer.records[-1])
        row['body'] = body(row['response'])
        row['memory_after'] = [memory(native_pid), memory(runtime_pid)]
    except BaseException as error:
        row['ended_ns'] = time.perf_counter_ns()
        row['errors'].append({'type': type(error).__name__, 'message': str(error),
                              'traceback': traceback.format_exc()})
    row['complete_client_request_ns'] = row['ended_ns'] - row['started_ns']
    save(output / (state + '_RESPONSE_RECEIPT.json'), row)
    return row


def enrich(row, native, audit, wire):
    observed = [event for event in events(native.workspace / 'WORKER_EVENTS.jsonl')
                if type(event.get('started_ns')) is int
                and row['started_ns'] <= event['started_ns'] <= row['ended_ns']]
    row['work_events'] = observed
    row['actual_host_RPC'] = len(observed)
    sequences = {event['sequence'] for event in observed}
    row['wire'] = [part for part in wire if part['sequence'] in sequences]
    row['bridge_request_bytes'] = sum(part['request_bytes'] for part in row['wire'])
    row['bridge_response_bytes'] = sum(part['response_attempted_bytes'] for part in row['wire'])
    trace_id = row.get('body', {}).get('trace_id')
    row['audit'] = [event for event in audit if trace_id is not None and event.get('trace_id') == trace_id]
    observations = [event for event in row['audit'] if event.get('event') == 'observe']
    traces = [event['trace'] for event in row['audit'] if event.get('event') == 'request_trace']
    assert len(observations) == len(traces) == 1, 'trace or private work evidence missing'
    row['diagnostics'] = observations[0]['task_work']
    row['trace'] = traces[0]
    row['full_service_and_delivery_trace_ns'] = traces[0]['duration_ns']
    row['span_timings_ns'] = [{'name': span['name'], 'duration_ns': span['duration_ns'],
                              'start_offset_ns': span['start_offset_ns']}
                             for span in traces[0]['spans']]
    row['process_peak_rss'] = traces[0]['peak_rss']
    assert all(event.get('changed_or_new_PNG_files', []) == [] for event in observed)
    assert traces[0]['annotations']['mcp_native_image_block_count'] == 0


def check_business(row, audit_path, source, source_sha):
    """Stop this candidate before another request if a complete result is wrong."""
    started = time.perf_counter_ns()
    assert not row['errors'], row['errors']
    trace_id = row['body']['trace_id']
    observations = [event for event in events(audit_path)
        if event.get('event') == 'observe' and event.get('trace_id') == trace_id]
    assert len(observations) == 1
    truth_state = 'EDIT' if row['state'] == 'edit' else 'BASE'
    truth = json.loads((QUAL/(truth_state+'_TRUTH.json')).read_bytes())
    row['verification'] = verify(row['body'], observations[0]['task_work'], truth, source, source_sha)
    row['quality_check_ns'] = time.perf_counter_ns()-started


def run_sequence(index, output, ready, binding):
    output.mkdir(exist_ok=False)
    started = time.perf_counter_ns()
    deadline = started + 590 * 10**9
    result = {'sequence': index, 'started_ns': started, 'host_path': 'BlenderMCPHost',
              'business': [], 'errors': [], 'timing_stages_ns': {}, 'automatic_retries': 0}
    native = peer = None
    runtime_handle = None
    runtime = load_module('_scan_runtime_proof', RUNTIME)
    helper = load_module('_scan_metered_native', HERE / 'pose_native_metered.py')
    actor = load_module('_scan_stdio_peer', ACTOR)
    try:
        assert all(sha(path) == expected for path, expected in binding['files'].items())
        mark = time.perf_counter_ns()
        native = helper.NativeSession.start(blender='D:/Tools/blender5.2/blender.exe',
            asset=QUAL / 'assembly.blend', workspace=output / 'native',
            deadline_ns=deadline, condition='P', max_calls=128,
            expected_asset_sha256=binding['qualification']['asset_sha256'],
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
            'clientInfo': {'name': 'surface-scan-engineering', 'version': '001'}}})
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
        runtime_pids = {row['pid'] for row in events(output / 'audit.jsonl')
                        if row.get('event') == 'request_trace'}
        assert len(runtime_pids) == 1
        runtime_pid = runtime_pids.pop()
        proof, runtime_handle = runtime._windows_runtime_proof(peer.process, runtime_pid, deadline)
        proof['before_stdin'] = False
        proof['scope'] = 'after metadata with zero host RPC; before geometry requests'
        save(output / 'RUNTIME_PROOF.json', proof)
        assert proof['confirmed']
        mark = time.perf_counter_ns()
        base = snapshot(native, 'base', output)
        result['timing_stages_ns']['base_QA_source_binding'] = time.perf_counter_ns() - mark
        result['business'].append(business(peer, 'cold', output, native.ready['pid'], runtime_pid))
        check_business(result['business'][-1], output/'audit.jsonl', base, ready['source_sha256'])
        result['business'].append(business(peer, 'repeat', output, native.ready['pid'], runtime_pid))
        check_business(result['business'][-1], output/'audit.jsonl', base, ready['source_sha256'])
        mark = time.perf_counter_ns()
        save(output / 'POSE_ADVANCE.json', native.qa_advance(timeout_s=30))
        result['timing_stages_ns']['registered_pose_edit'] = time.perf_counter_ns() - mark
        mark = time.perf_counter_ns()
        edited = snapshot(native, 'edit', output)
        result['timing_stages_ns']['edit_QA_source_binding'] = time.perf_counter_ns() - mark
        result['business'].append(business(peer, 'edit', output, native.ready['pid'], runtime_pid))
        check_business(result['business'][-1], output/'audit.jsonl', edited, ready['source_sha256'])
    except BaseException as error:
        result['errors'].append({'stage': 'sequence', 'type': type(error).__name__,
            'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        if peer is not None:
            try:
                result['product_close'] = peer.close()
            except BaseException as error:
                result['errors'].append({'stage': 'product_close', 'error': repr(error)})
            try:
                result['runtime_exit'] = runtime._runtime_exit(runtime_handle)
                if not (result['runtime_exit']['confirmed'] and result['runtime_exit']['exit_code'] == 0):
                    result['errors'].append({'stage': 'runtime_exit', 'error': result['runtime_exit']})
            except BaseException as error:
                result['errors'].append({'stage': 'runtime_exit', 'error': repr(error)})
        if native is not None:
            try:
                result['native_close'] = native.close()
                result['worker_closed'] = native.status()['closed']
                assert result['native_close']['process_reaped'] and result['native_close']['exit_code'] == 0
                assert result['native_close']['error'] is None
                closed = result['worker_closed']
                assert not closed['poisoned'] and closed['qa_patch_applied']
                assert closed['final_geometry_fingerprint'] == closed['accepted_geometry_fingerprint']
                wire = json.loads((native.workspace / 'WIRE/INDEX.json').read_bytes())
                audit = events(output / 'audit.jsonl')
                for row in result['business']:
                    try:
                        enrich(row, native, audit, wire)
                        assert row.get('verification', {}).get('passed')
                    except BaseException as error:
                        row['errors'].append({'stage': 'independent_verification',
                            'type': type(error).__name__, 'message': str(error),
                            'traceback': traceback.format_exc()})
                result['all_host_RPC_including_QA_and_close'] = len(wire)
                result['all_worker_events'] = events(native.workspace / 'WORKER_EVENTS.jsonl')
            except BaseException as error:
                result['errors'].append({'stage': 'native_close_and_evidence',
                    'error': repr(error), 'traceback': traceback.format_exc()})
        try:
            result['source_files_unchanged'] = all(sha(path) == expected for path, expected in binding['files'].items())
        except BaseException as error:
            result['source_files_unchanged'] = False
            result['errors'].append({'stage': 'source_files_check', 'error': repr(error)})
        result['ended_ns'] = time.perf_counter_ns()
        result['session_wall_ns'] = result['ended_ns'] - started
        result['passed'] = (not result['errors'] and len(result['business']) == 3
            and result['source_files_unchanged'] and all(not row['errors']
            and row.get('verification', {}).get('passed') for row in result['business']))
        save(output / 'RESULTS.json', result)
    return result

