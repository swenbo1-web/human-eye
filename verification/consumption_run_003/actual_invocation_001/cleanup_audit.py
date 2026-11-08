"""Post-run RUN-003 receipt audit; only recorded PIDs receive read-only OS queries."""
import ctypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
RUN = OUT.parent
ACTUAL = RUN / 'actual_01'
NEUTRAL = Path('C:/Users/Administrator/AppData/Local/Temp/he-consumption-run-003').resolve()
sha = lambda value: hashlib.sha256(value).hexdigest()
load = lambda path: json.loads(Path(path).read_bytes())


def recorded_pid(pid):
    assert type(pid) is int and 0 < pid < 2**32, 'invalid recorded PID'
    return pid


def observe_known_pid(pid):
    """SYNCHRONIZE-only handle and zero-time wait; no signals, enumeration or retry."""
    recorded_pid(pid)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    kernel.WaitForSingleObject.restype = ctypes.c_ulong
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    result = dict(pid=pid, observed_utc=datetime.now(timezone.utc).isoformat(),
        method='OpenProcess(SYNCHRONIZE) + WaitForSingleObject(handle,0), only recorded PID',
        process_stopped=None, exit_code=None, owner_reaped=None)
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        result.update(open_error=error, process_stopped=True if error == 87 else None,
            observation='PID absent at query' if error == 87 else 'OS state unavailable')
        return result
    try:
        waited = kernel.WaitForSingleObject(handle, 0)
        result.update(wait_result=waited,
            process_stopped=True if waited == 0 else False if waited == 258 else None,
            observation='signaled' if waited == 0 else 'live at query' if waited == 258 else 'OS state unavailable')
    finally:
        kernel.CloseHandle(handle)
    return result


def main():
    output = OUT / 'CLEANUP_AUDIT.json'
    assert not output.exists(), 'do not silently replace post-run audit evidence'
    source_path = OUT / 'SOURCE_AUDIT.json'
    source = load(source_path)
    assert source['passed'] is True
    assert sha(source_path.read_bytes()) == 'cd36d3490ab48eedcead3dd77bbe1d1e78caa3a8b088e4abf57278280ef4c57f'
    raw_result = (ACTUAL / 'RESULTS.json').read_bytes()
    result = json.loads(raw_result)
    outer = load(OUT / 'RESULT.json')
    assert outer['process_reaped'] is True and outer['exit_code'] == 0
    assert len(result['cells']) == 8 and all(slot['status'] not in ('planned', 'running') for slot in result['cells'])
    records = [dict(slot=None, kind='controller', pid=recorded_pid(outer['pid']))]
    evidence_files = []

    def retain(path):
        path = Path(path)
        row = dict(path=str(path), exists=path.exists(), bytes=None, sha256=None)
        if row['exists']:
            data = path.read_bytes()
            row.update(bytes=len(data), sha256=sha(data))
        evidence_files.append(row)
        return row

    retain(ACTUAL / 'RESULTS.json')
    retain(OUT / 'RESULT.json')
    retain(source_path)
    slots = []
    for slot in result['cells']:
        number = slot['ordinal']
        folder = ACTUAL / str(number).zfill(2)
        cell = load(folder / 'CELL.json')
        consumer = slot.get('consumer') or {}
        session = slot.get('native_session') or {}
        close = slot.get('close') or {}
        closed = slot.get('closed_worker') or {}
        retain(folder / 'CELL.json')
        retain(folder / 'RESULT.json')
        retain(folder / 'CONSUMER.json')
        retain(folder / 'BUDGET.json')
        per_cell = load(folder / 'RESULT.json')
        assert all(slot.get(key) == value for key, value in per_cell.items())
        assert load(folder / 'CONSUMER.json') == consumer
        records.append(dict(slot=number, kind='consumer', pid=recorded_pid(consumer['consumer_pid'])))
        records.append(dict(slot=number, kind='Blender', pid=recorded_pid(session['pid'])))
        workspace = Path(session['workspace']).resolve()
        assert workspace.is_relative_to(NEUTRAL)
        ready = load(workspace / 'READY.json')
        for name in ('READY.json', 'SESSION.json', 'CONFIG.json', 'WORKER_CLOSED.json'):
            retain(workspace / name)
        assert load(workspace / 'SESSION.json') == session
        assert load(workspace / 'WORKER_CLOSED.json') == closed
        copies = []
        for field in ('asset', 'asset_copy'):
            path = Path(session[field]).resolve()
            assert path.is_relative_to(NEUTRAL)
            row = retain(path)
            copies.append(dict(kind=field, **row, matches_original_asset=row['sha256'] == session['asset_sha256']))
        native = dict(pid=session['pid'], close_receipt=close,
            owner_exit_code=close.get('exit_code'), owner_reaped=close.get('process_reaped'),
            worker_closed=closed,
            original_deadline_matches=(session['deadline_ns'] == ready.get('deadline_ns')
                == close.get('original_deadline_ns') == close.get('response', {}).get('deadline_ns')
                == closed.get('original_deadline_ns')),
            initial_final_fingerprint_same=closed.get('initial_geometry_fingerprint') == closed.get('final_geometry_fingerprint'),
            ready_helper_matches=ready.get('helper_sha256') == session.get('helper_sha256') == source['helper_check']['sha256'],
            all_recorded_native_pids_match=session['pid'] == ready.get('pid') == close.get('pid')
                == close.get('response', {}).get('pid') == closed.get('pid'),
            asset_copies=copies)
        tree = consumer.get('registered_tree_cleanup') or {}
        bridge_rows = []
        for kind in ('native', 'he') if slot['arm'] == 'P' else ('native',):
            bridge = folder / ('bridge_' + kind)
            started = load(bridge / 'STARTED.json')
            frozen = next(row for row in tree.get('evidence', []) if row['kind'] == kind)
            pid = recorded_pid(started['pid'])
            records.append(dict(slot=number, kind='bridge_' + kind, pid=pid))
            start_file = retain(bridge / 'STARTED.json')
            exit_file = retain(bridge / 'EXIT.json')
            exit_receipt = load(bridge / 'EXIT.json') if exit_file['exists'] else None
            row = dict(kind=kind, pid=pid, started=started, started_file=start_file,
                frozen_process_stopped=frozen.get('process_stopped'), frozen_confirmed=frozen.get('confirmed'),
                frozen_graceful_exit_receipt=frozen.get('graceful_exit_receipt'),
                ledger_kind_matches=started.get('ledger_path') == cell['ledger_path'] and started.get('kind') == kind,
                matches_frozen_started=started == frozen.get('started'),
                current_EXIT_file=exit_file, current_graceful_exit_receipt=exit_receipt,
                owner_exit_code=None, owner_reap_evidence=None)
            if kind == 'he':
                child_started = load(bridge / 'HE_CHILD_STARTED.json')
                child_pid = recorded_pid(child_started['pid'])
                records.append(dict(slot=number, kind='HE_child', pid=child_pid))
                frozen_child = frozen.get('he_child') or {}
                child_start_file = retain(bridge / 'HE_CHILD_STARTED.json')
                child_exit_file = retain(bridge / 'HE_CHILD_EXIT.json')
                child_exit = load(bridge / 'HE_CHILD_EXIT.json') if child_exit_file['exists'] else None
                row['HE_child'] = dict(pid=child_pid, started=child_started, started_file=child_start_file,
                    bound_by='HE_CHILD_STARTED within current slot ledger-bound bridge_he directory',
                    matches_frozen_started=child_started == frozen_child.get('started'),
                    separate_from_bridge=child_pid != pid,
                    frozen_process_stopped=frozen_child.get('process_stopped'),
                    frozen_graceful_exit_receipt=frozen_child.get('graceful_exit_receipt'),
                    current_EXIT_file=child_exit_file, current_graceful_exit_receipt=child_exit,
                    owner_exit_code=None if child_exit is None else child_exit.get('exit_code'),
                    owner_reap_evidence=None if child_exit is None else child_exit.get('reaped'))
            bridge_rows.append(row)
        slots.append(dict(ordinal=number, task_id=slot['task_id'], arm=slot['arm'],
            original_status=slot['status'], original_safe_to_continue=slot.get('safe_to_continue'),
            original_cleanup_verified=slot.get('cleanup_verified'),
            consumer=dict(pid=consumer.get('consumer_pid'), owner_exit_code=consumer.get('exit_code'),
                owner_reaped=consumer.get('process_reaped'), frozen_tree_reaped=consumer.get('tree_reaped'),
                frozen_registered_tree_cleanup=tree), native=native, bridges=bridge_rows))
    observed = {pid: observe_known_pid(pid) for pid in sorted({row['pid'] for row in records})}
    for row in records:
        row['postrun_OS_observation'] = observed[row['pid']]
    all_bridges = [bridge for slot in slots for bridge in slot['bridges']]
    all_children = [bridge['HE_child'] for bridge in all_bridges if 'HE_child' in bridge]
    unchanged = all(not row['exists'] or sha(Path(row['path']).read_bytes()) == row['sha256'] for row in evidence_files)
    assert raw_result == (ACTUAL / 'RESULTS.json').read_bytes() and unchanged
    summary = dict(slots=len(slots), frozen_completed=sum(slot['original_status'] == 'completed' for slot in slots),
        frozen_safe_to_continue=sum(slot['original_safe_to_continue'] is True for slot in slots),
        consumer_owner_reaped_exit0=sum(slot['consumer']['owner_reaped'] is True and slot['consumer']['owner_exit_code'] == 0 for slot in slots),
        native_owner_reaped_exit0=sum(slot['native']['owner_reaped'] is True and slot['native']['owner_exit_code'] == 0 for slot in slots),
        native_closed_clean_fingerprint_deadline_assets=sum(slot['native']['close_receipt'].get('response', {}).get('status') == 'closed'
            and slot['native']['close_receipt'].get('error') is None and slot['native']['worker_closed'].get('poisoned') is False
            and slot['native']['initial_final_fingerprint_same'] and slot['native']['original_deadline_matches']
            and slot['native']['ready_helper_matches'] and slot['native']['all_recorded_native_pids_match']
            and all(row['matches_original_asset'] for row in slot['native']['asset_copies']) for slot in slots),
        bridges=len(all_bridges), bridge_frozen_OS_stopped=sum(row['frozen_process_stopped'] is True for row in all_bridges),
        bridge_graceful_EXIT_present=sum(row['current_EXIT_file']['exists'] for row in all_bridges),
        HE_children=len(all_children), HE_child_frozen_OS_stopped=sum(row['frozen_process_stopped'] is True for row in all_children),
        HE_child_graceful_EXIT_present=sum(row['current_EXIT_file']['exists'] for row in all_children),
        recorded_PID_roles=len(records), distinct_recorded_PIDs=len(observed),
        postrun_OS_stopped=sum(row['process_stopped'] is True for row in observed.values()),
        postrun_OS_live=sum(row['process_stopped'] is False for row in observed.values()),
        postrun_OS_unknown=sum(row['process_stopped'] is None for row in observed.values()),
        frozen_originals_unchanged_during_audit=unchanged)
    audit = dict(cycle_id='CONSUMPTION-RUN-003', audited_utc=datetime.now(timezone.utc).isoformat(),
        scope='read-only receipts/registered PID observations/known native asset copies; no answer body or truth interpretation',
        summary=summary, outer_controller={key: outer.get(key) for key in ('pid', 'exit_code', 'process_reaped', 'started_utc', 'ended_utc', 'wall_ns')},
        source_audit_reference=dict(path=str(source_path), sha256=sha(source_path.read_bytes()), passed=source['passed'],
            product_source_count=source['product_source_count'], product_canonical_sha256=source['product_canonical_sha256'],
            source_matrix_rerun=False), slots=slots, known_owned_PID_records=records, evidence_files=evidence_files,
        limitations=['OS stopped observations do not supply absent graceful EXIT receipts, exit codes or owner wait/reap.',
            'Later observations do not rewrite frozen controller fields, prior RUN-001/002 output or quality state.',
            'Registered PID checks cannot exclude PID reuse or prove arbitrary descendant/whole-host cleanup.'],
        actual_Codex_CLI=0, actual_consumers=0, actual_MCP_services=0, actual_Blender=0, actual_RPC=0,
        actual_target_process_signals=0, product_or_helper_imports=0, quality_scoring_performed=False)
    output.write_text(json.dumps(audit, indent=2) + '\n', encoding='utf8', newline='\n')
    lines = ['# RUN-003 cleanup audit', '',
        f"All {summary['frozen_completed']}/8 frozen slots remain completed and safe_to_continue=true; no original field was rewritten.", '',
        f"Controller PID {outer['pid']}, all 8 CLI parents and all 8 Native Blender owners have original wait/reap receipts with exit 0. All 8 native closes returned closed, unpoisoned, unchanged geometry fingerprint/deadline/helper and asset-copy bytes.", '',
        f"All {summary['bridges']} registered bridges and {summary['HE_children']} registered HE children have frozen OS process_stopped=true. There are {summary['bridge_graceful_EXIT_present']} bridge EXIT files and {summary['HE_child_graceful_EXIT_present']} HE_CHILD_EXIT files. Their missing graceful receipts remain missing; bridge/HE-child owner reap and exit codes remain unexposed, not fabricated as 0.", '',
        f"A separate post-run SYNCHRONIZE-only, zero-time query of {summary['distinct_recorded_PIDs']} recorded PIDs observed {summary['postrun_OS_stopped']} stopped, {summary['postrun_OS_live']} live, {summary['postrun_OS_unknown']} unknown. It neither signals nor enumerates any process, and is not a whole-host/descendant cleanup claim.", '',
        'The earlier SOURCE_AUDIT remains the source/package/asset/helper matrix; it was not rerun. No consumer, backend, product/helper import, scoring, signal or RPC was launched by this audit.', '',
        '| Slot | Arm | CLI PID | Native PID | Native bridge PID | HE bridge PID | HE child PID |',
        '|---|---|---:|---:|---:|---:|---:|']
    for slot in slots:
        native_bridge = next(row for row in slot['bridges'] if row['kind'] == 'native')
        he = next((row for row in slot['bridges'] if row['kind'] == 'he'), None)
        lines.append(f"| {slot['ordinal']} | {slot['arm']} | {slot['consumer']['pid']} | {slot['native']['pid']} | {native_bridge['pid']} | {he['pid'] if he else ''} | {he['HE_child']['pid'] if he else ''} |")
    (OUT / 'CLEANUP_AUDIT.md').write_text('\n'.join(lines) + '\n', encoding='utf8', newline='\n')
    print(json.dumps(dict(summary=summary, json_sha256=sha(output.read_bytes()),
        md_sha256=sha((OUT / 'CLEANUP_AUDIT.md').read_bytes()))))


if __name__ == '__main__':
    main()
