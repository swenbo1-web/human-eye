"""RUN006 terminal receipt audit; recorded-PID read-only OS queries only.

No process enumeration, signal, product/helper import, consumer or physical RPC.
Missing optional graceful receipts stay missing; failures/not_run stay in denominator.
"""
import ctypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
RUN = OUT.parent
ACTUAL = RUN / 'actual_01'
NEUTRAL = Path('C:/Users/Administrator/AppData/Local/Temp/he-consumption-run-006').resolve()
SOURCE_AUDIT_SHA = '71ccf6f64424f5f4d04f7dcda691346880416d02941736016f9d537eae87d61d'
sha = lambda data: hashlib.sha256(data).hexdigest()
load = lambda path: json.loads(Path(path).read_bytes())
mapping = lambda value: value if type(value) is dict else {}


def observe_known_pid(pid):
    """SYNCHRONIZE-only handle + zero-time wait; no enumeration or signals."""
    assert type(pid) is int and 0 < pid < 2**32
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    kernel.WaitForSingleObject.restype = ctypes.c_ulong
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    row = dict(pid=pid, observed_utc=datetime.now(timezone.utc).isoformat(),
        method='OpenProcess(SYNCHRONIZE) + WaitForSingleObject(handle,0), recorded PID only',
        process_stopped=None, exit_code=None, owner_reaped=None)
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        row.update(open_error=error, process_stopped=True if error == 87 else None,
            observation='PID absent at query' if error == 87 else 'OS state unavailable')
        return row
    try:
        waited = kernel.WaitForSingleObject(handle, 0)
        row.update(wait_result=waited,
            process_stopped=True if waited == 0 else False if waited == 258 else None,
            observation='signaled' if waited == 0 else 'live at query' if waited == 258 else 'OS state unavailable')
    finally:
        kernel.CloseHandle(handle)
    return row


def main():
    output = OUT / 'CLEANUP_AUDIT.json'
    assert not output.exists(), 'do not replace post-run evidence'
    source_path = OUT / 'SOURCE_AUDIT.json'
    assert sha(source_path.read_bytes()) == SOURCE_AUDIT_SHA
    source = load(source_path)
    assert source['passed'] is True
    plan = load(RUN / 'PLAN.json')
    raw_result = (ACTUAL / 'RESULTS.json').read_bytes()
    result = json.loads(raw_result)
    outer = load(OUT / 'RESULT.json')
    assert outer['process_reaped'] is True, 'outer owner must finish before post-run audit'
    assert len(result['cells']) == 8
    assert all(slot['status'] not in ('planned', 'running') for slot in result['cells'])
    evidence_files = []
    consistency = []
    records = []

    def retain(path):
        path = Path(path)
        row = dict(path=str(path), exists=path.is_file(), bytes=None, sha256=None)
        if row['exists']:
            data = path.read_bytes()
            row.update(bytes=len(data), sha256=sha(data))
        evidence_files.append(row)
        return row

    def optional(path):
        row = retain(path)
        return load(path) if row['exists'] else None

    def check(name, passed, slot=None):
        consistency.append(dict(slot=slot, check=name, passed=bool(passed)))

    def pid_record(pid, kind, number=None, receipt=None):
        if pid is None:
            return
        check('recorded_' + kind + '_PID_valid', type(pid) is int and 0 < pid < 2**32, number)
        if type(pid) is int and 0 < pid < 2**32:
            records.append(dict(slot=number, kind=kind, pid=pid, receipt_path=receipt))

    def neutral_path(value, name, number):
        if value is None:
            return None
        path = Path(value).resolve()
        inside = path.is_relative_to(NEUTRAL)
        check(name + '_inside_RUN006_neutral_root', inside, number)
        return path if inside else None

    retain(ACTUAL / 'RESULTS.json')
    retain(OUT / 'RESULT.json')
    retain(source_path)
    outer_started = optional(OUT / 'STARTED.json')
    outer_owned = optional(OUT / 'OWNED_PROCESS.json')
    aggregate_started = optional(ACTUAL / 'STARTED.json')
    pid_record(outer.get('pid'), 'outer_Popen_owner', receipt=str(OUT / 'RESULT.json'))
    if outer_owned is not None:
        check('outer_owned_PID_matches_terminal_owner', outer_owned.get('pid') == outer.get('pid'))
    controller_self_pid = mapping(aggregate_started).get('controller_pid', result.get('controller_pid'))
    if controller_self_pid is not None and controller_self_pid != outer.get('pid'):
        pid_record(controller_self_pid, 'controller_self_recorded_no_direct_owner_wait', receipt=str(ACTUAL / 'STARTED.json'))
    controller_pid_scope = dict(outer_Popen_pid=outer.get('pid'), actual_controller_self_pid=controller_self_pid,
        self_pid_exposure='recorded self PID only' if controller_self_pid is not None else 'unexposed by frozen aggregate/STARTED schema',
        owner_wait_scope='outer Popen handle only; no assumption that wrapper PID equals controller self PID')
    slots = []
    for slot in result['cells']:
        number = slot['ordinal']
        folder = ACTUAL / str(number).zfill(2)
        cell = optional(folder / 'CELL.json')
        per_cell = optional(folder / 'RESULT.json')
        consumer_file = optional(folder / 'CONSUMER.json')
        retain(folder / 'BUDGET.json')
        consumer = slot.get('consumer') or {}
        session = slot.get('native_session') or {}
        close = slot.get('close') or {}
        closed = slot.get('closed_worker') or {}
        if per_cell is not None:
            check('per_cell_RESULT_matches_aggregate_fields',
                all(slot.get(key) == value for key, value in per_cell.items()), number)
        if consumer_file is not None:
            check('CONSUMER_matches_aggregate', consumer_file == consumer, number)
        elif consumer:
            check('CONSUMER_receipt_present_for_recorded_consumer', False, number)
        pid_record(consumer.get('consumer_pid'), 'consumer', number, str(folder / 'CONSUMER.json'))
        if cell is not None:
            check('CELL_product_manifest_and_source_SHA_match_fixed_PLAN',
                cell.get('product_manifest') == plan['product_manifest']
                and cell.get('source_sha256') == plan['source_sha256'], number)
        native = None
        if session:
            pid_record(session.get('pid'), 'Blender', number, str(folder / 'RESULT.json'))
            workspace = neutral_path(session.get('workspace'), 'native_workspace', number)
            ready = optional(workspace / 'READY.json') if workspace else None
            session_file = optional(workspace / 'SESSION.json') if workspace else None
            closed_file = optional(workspace / 'WORKER_CLOSED.json') if workspace else None
            if workspace:
                retain(workspace / 'CONFIG.json')
            ready = ready or {}
            worker_events_path = workspace / 'WORKER_EVENTS.jsonl' if workspace else None
            worker_events = []
            if worker_events_path is not None:
                event_file = retain(worker_events_path)
                if event_file['exists']:
                    for line in worker_events_path.read_bytes().splitlines():
                        event = json.loads(line)
                        worker_events.append({key:event[key] for key in ('event','sequence','status','started_ns',
                            'elapsed_ns','script_sha256','stdout_bytes','stderr_bytes',
                            'render_events_before','render_events_after','terminal_geometry_and_file_checks_passed') if key in event})
            check('SESSION_matches_aggregate', session_file == session, number)
            check('WORKER_CLOSED_matches_aggregate', closed_file == closed, number)
            copies = []
            for field in ('asset', 'asset_copy'):
                path = neutral_path(session.get(field), field, number)
                row = retain(path) if path else dict(path=session.get(field), exists=False, bytes=None, sha256=None)
                copies.append(dict(kind=field, **row,
                    matches_original_asset=row['sha256'] is not None and row['sha256'] == session.get('asset_sha256')))
            deadline = session.get('deadline_ns')
            fingerprint = closed.get('initial_geometry_fingerprint')
            native = dict(pid=session.get('pid'), close_receipt=close,
                owner_exit_code=close.get('exit_code'), owner_reaped=close.get('process_reaped'),
                source_file_unchanged=close.get('source_file_unchanged'),
                protected_files_unchanged=close.get('protected_files_unchanged'),
                worker_closed=closed, worker_event_metadata=worker_events,
                original_deadline_matches=deadline is not None and deadline == ready.get('deadline_ns')
                    == close.get('original_deadline_ns') == mapping(close.get('response')).get('deadline_ns')
                    == closed.get('original_deadline_ns'),
                initial_final_fingerprint_same=fingerprint is not None and fingerprint == closed.get('final_geometry_fingerprint'),
                ready_helper_matches=ready.get('helper_sha256') is not None and ready.get('helper_sha256')
                    == session.get('helper_sha256') == source['helper_check']['sha256'],
                all_recorded_native_pids_match=session.get('pid') is not None and session.get('pid') == ready.get('pid')
                    == close.get('pid') == mapping(close.get('response')).get('pid') == closed.get('pid'),
                asset_copies=copies)
        else:
            # Preserve a known start-failure receipt without treating an unstarted slot as a successful close.
            failure = slot.get('native_start_failure')
            if isinstance(failure, dict):
                pid_record(failure.get('pid'), 'native_start_failure', number, str(folder / 'RESULT.json'))
        tree = consumer.get('registered_tree_cleanup') or {}
        bridge_rows = []
        for kind in (('native', 'he') if slot['arm'] == 'P' else ('native',)):
            bridge = folder / ('bridge_' + kind)
            started = optional(bridge / 'STARTED.json')
            exit_receipt = optional(bridge / 'EXIT.json')
            frozen = next((entry for entry in tree.get('evidence', []) if entry.get('kind') == kind), None)
            frozen = frozen or {}
            row = dict(kind=kind, pid=None if started is None else started.get('pid'), started=started,
                frozen_process_stopped=frozen.get('process_stopped'), frozen_confirmed=frozen.get('confirmed'),
                frozen_graceful_exit_receipt=frozen.get('graceful_exit_receipt'),
                current_graceful_exit_receipt=exit_receipt,
                current_EXIT_file_present=exit_receipt is not None,
                owner_exit_code=None, owner_reap_evidence=None)
            if started is not None:
                pid_record(started.get('pid'), 'bridge_' + kind, number, str(bridge / 'STARTED.json'))
                check(kind + '_STARTED_matches_frozen', started == frozen.get('started'), number)
                check(kind + '_STARTED_ledger_and_kind_match_current_CELL', cell is not None
                    and started.get('ledger_path') == cell.get('ledger_path') and started.get('kind') == kind, number)
            if kind == 'he':
                child = optional(bridge / 'HE_CHILD_STARTED.json')
                child_exit = optional(bridge / 'HE_CHILD_EXIT.json')
                frozen_child = frozen.get('he_child') or {}
                row['HE_child'] = dict(pid=None if child is None else child.get('pid'), started=child,
                    bound_by='HE_CHILD_STARTED inside current-slot ledger-bound bridge_he directory',
                    frozen_process_stopped=frozen_child.get('process_stopped'),
                    frozen_graceful_exit_receipt=frozen_child.get('graceful_exit_receipt'),
                    current_graceful_exit_receipt=child_exit, current_EXIT_file_present=child_exit is not None,
                    owner_exit_code=None if child_exit is None else child_exit.get('exit_code'),
                    owner_reap_evidence=None if child_exit is None else child_exit.get('reaped'))
                if child is not None:
                    pid_record(child.get('pid'), 'HE_child', number, str(bridge / 'HE_CHILD_STARTED.json'))
                    check('HE_child_STARTED_matches_frozen', child == frozen_child.get('started'), number)
                    check('HE_child_separate_from_bridge', started is not None and child.get('pid') != started.get('pid'), number)
            bridge_rows.append(row)
        actual_sources = None
        he_launcher_exit = None
        if slot['arm'] == 'P' and cell is not None:
            source_root = neutral_path(cell.get('source_root'), 'product_source_root', number)
            if source_root and source_root.is_dir():
                source_checks = []
                for item in plan['product_manifest']:
                    path = source_root / item['path']
                    row = retain(path)
                    source_checks.append(dict(path=item['path'], exists=row['exists'], sha256=row['sha256'],
                        expected_sha256=item['sha256'], matches=row['sha256'] == item['sha256']))
                actual_sources = dict(count=len(source_checks), all_match=len(source_checks) == 131
                    and all(row['matches'] for row in source_checks), source_checks=source_checks)
                check('isolated_P_product_sources_match_fixed_131', actual_sources['all_match'], number)
            he_exit = optional(folder / 'he_socket/EXIT.json')
            if he_exit is not None:
                he_launcher_exit = {key: he_exit.get(key) for key in
                    ('exit_code', 'started_ns', 'ended_ns', 'source_sha256', 'guard_verified', 'loaded_generation', 'instrumentation')}
        slots.append(dict(ordinal=number, task_id=slot['task_id'], arm=slot['arm'],
            original_status=slot['status'], original_safe_to_continue=slot.get('safe_to_continue'),
            original_cleanup_verified=slot.get('cleanup_verified'), CELL_file_present=cell is not None,
            per_cell_RESULT_present=per_cell is not None, consumer_receipt_present=consumer_file is not None,
            consumer=dict(pid=consumer.get('consumer_pid'), owner_exit_code=consumer.get('exit_code'),
                owner_reaped=consumer.get('process_reaped'), frozen_tree_reaped=consumer.get('tree_reaped'),
                frozen_registered_tree_cleanup=tree), native=native, native_start_failure=slot.get('native_start_failure'),
            bridges=bridge_rows, isolated_P_sources=actual_sources, HE_launcher_optional_exit=he_launcher_exit))
    # A final-state check of these known inputs is separate from rerunning the 131-source matrix.
    postrun_protected_originals = []
    for original in source['original_asset_hashes']:
        row = retain(original['source_path'])
        postrun_protected_originals.append(dict(kind='original_asset', **row,
            expected_sha256=original['expected_sha256'], matches=row['sha256'] == original['expected_sha256']))
    helper = RUN.parents[1] / 'verification/consumption_run_001/materials' / source['helper_check']['path']
    row = retain(helper)
    postrun_protected_originals.append(dict(kind='original_neutral_helper', **row,
        expected_sha256=source['helper_check']['sha256'], matches=row['sha256'] == source['helper_check']['sha256']))
    observed = {pid: observe_known_pid(pid) for pid in sorted({row['pid'] for row in records})}
    for row in records:
        row['postrun_OS_observation'] = observed[row['pid']]
    all_bridges = [row for slot in slots for row in slot['bridges'] if row['started'] is not None]
    all_children = [row['HE_child'] for row in all_bridges if row.get('HE_child', {}).get('started') is not None]
    natives = [slot['native'] for slot in slots if slot['native'] is not None]
    consumers = [slot['consumer'] for slot in slots if slot['consumer']['pid'] is not None]
    unchanged = all(Path(row['path']).is_file() == row['exists']
        and (not row['exists'] or sha(Path(row['path']).read_bytes()) == row['sha256']) for row in evidence_files)
    assert raw_result == (ACTUAL / 'RESULTS.json').read_bytes() and unchanged
    summary = dict(slots=len(slots), frozen_completed=sum(slot['original_status'] == 'completed' for slot in slots),
        frozen_error=sum(slot['original_status'] == 'error' for slot in slots),
        frozen_not_run=sum(slot['original_status'] == 'not_run' for slot in slots),
        frozen_safe_to_continue=sum(slot['original_safe_to_continue'] is True for slot in slots),
        consumer_owners_recorded=len(consumers), consumer_owner_reaped_exit0=sum(row['owner_reaped'] is True and row['owner_exit_code'] == 0 for row in consumers),
        native_owners_recorded=len(natives), native_owner_reaped_exit0=sum(row['owner_reaped'] is True and row['owner_exit_code'] == 0 for row in natives),
        native_closed_clean_fingerprint_deadline_assets=sum(mapping(row['close_receipt'].get('response')).get('status') == 'closed'
            and row['close_receipt'].get('error') is None and row['worker_closed'].get('poisoned') is False
            and row['source_file_unchanged'] is True and row['protected_files_unchanged'] is True
            and row['initial_final_fingerprint_same'] and row['original_deadline_matches']
            and row['ready_helper_matches'] and row['all_recorded_native_pids_match']
            and all(copy['matches_original_asset'] for copy in row['asset_copies']) for row in natives),
        native_worker_events_status_unknown=sum(event.get('status') == 'unknown' for row in natives for event in row.get('worker_event_metadata', [])),
        bridges=len(all_bridges), bridge_frozen_OS_stopped=sum(row['frozen_process_stopped'] is True for row in all_bridges),
        bridge_graceful_EXIT_present=sum(row['current_EXIT_file_present'] for row in all_bridges),
        HE_children=len(all_children), HE_child_frozen_OS_stopped=sum(row['frozen_process_stopped'] is True for row in all_children),
        HE_child_graceful_EXIT_present=sum(row['current_EXIT_file_present'] for row in all_children),
        isolated_P_source_sets_checked=sum(slot['isolated_P_sources'] is not None for slot in slots),
        isolated_P_source_sets_match=sum(slot['isolated_P_sources'] is not None and slot['isolated_P_sources']['all_match'] for slot in slots),
        recorded_PID_roles=len(records), distinct_recorded_PIDs=len(observed),
        postrun_OS_stopped=sum(row['process_stopped'] is True for row in observed.values()),
        postrun_OS_live=sum(row['process_stopped'] is False for row in observed.values()),
        postrun_OS_unknown=sum(row['process_stopped'] is None for row in observed.values()),
        consistency_checks=len(consistency), consistency_failures=sum(row['passed'] is False for row in consistency),
        postrun_original_asset_helper_files_checked=len(postrun_protected_originals),
        postrun_original_asset_helper_files_match=sum(row['matches'] for row in postrun_protected_originals),
        frozen_originals_unchanged_during_audit=unchanged)
    audit = dict(cycle_id='CONSUMPTION-RUN-006', audited_utc=datetime.now(timezone.utc).isoformat(),
        scope='terminal receipts/registered PID observations/known isolated native asset and P source copies; no answer/truth interpretation',
        summary=summary, outer_controller={key: outer.get(key) for key in ('pid', 'exit_code', 'process_reaped', 'started_utc', 'ended_utc', 'wall_ns')},
        controller_pid_scope=controller_pid_scope,
        source_audit_reference=dict(path=str(source_path), sha256=SOURCE_AUDIT_SHA, passed=source['passed'],
            product_source_count=source['product_source_count'], product_canonical_sha256=source['product_canonical_sha256'], source_matrix_rerun=False),
        slots=slots, known_owned_PID_records=records, evidence_files=evidence_files, consistency_checks=consistency,
        postrun_protected_originals=postrun_protected_originals,
        limitations=['Actual controller self PID is not inferred from an outer Popen PID; missing self identity stays unexposed.',
            'Stopped PID observations do not supply absent graceful EXIT receipts, exit codes or owner wait/reap.',
            'Later observations do not rewrite frozen controller fields, failures, not_run or prior-run evidence.',
            'Registered PID checks cannot exclude PID reuse or prove arbitrary descendant/whole-host cleanup.',
            'Missing HE launcher EXIT means its final guard witness is unexposed; source-copy byte checks do not manufacture it.'],
        actual_Codex_CLI=0, actual_consumers=0, actual_MCP_services=0, actual_Blender=0, actual_RPC=0,
        actual_target_process_signals=0, product_or_helper_imports=0, quality_scoring_performed=False)
    output.write_text(json.dumps(audit, indent=2) + '\n', encoding='utf8', newline='\n')
    lines = ['# RUN006 cleanup audit', '',
        f"Frozen denominator: {summary['slots']} slots; completed {summary['frozen_completed']}, error {summary['frozen_error']}, not_run {summary['frozen_not_run']}. Safe-to-continue true: {summary['frozen_safe_to_continue']}. No original field was rewritten.", '',
        f"Outer Popen owner PID {outer['pid']}: exit {outer.get('exit_code')}, owner reaped {outer.get('process_reaped')}. Recorded CLI owners: {summary['consumer_owners_recorded']}, with exit0/reap receipts {summary['consumer_owner_reaped_exit0']}. Recorded Native owners: {summary['native_owners_recorded']}, exit0/reap {summary['native_owner_reaped_exit0']}; clean native close/fingerprint/deadline/helper/assets {summary['native_closed_clean_fingerprint_deadline_assets']}.", '',
        f"Controller actual self PID is {controller_self_pid}; exposure: {controller_pid_scope['self_pid_exposure']}. The owner wait receipt applies to the outer Popen handle. No wrapper/self equality or unrecorded self-PID wait is inferred.", '',
        f"Worker event metadata retains {summary['native_worker_events_status_unknown']} status=unknown events unchanged; separate closed responses/owner receipts do not turn those events into success.", '',
        f"Registered bridges: {summary['bridges']}, frozen OS-stopped {summary['bridge_frozen_OS_stopped']}, graceful EXIT files {summary['bridge_graceful_EXIT_present']}. Registered HE children: {summary['HE_children']}, frozen OS-stopped {summary['HE_child_frozen_OS_stopped']}, graceful HE_CHILD_EXIT files {summary['HE_child_graceful_EXIT_present']}. Missing graceful receipts remain missing. Their absent owner reap/exit codes remain unknown.", '',
        f"Separate read-only post-run queries of {summary['distinct_recorded_PIDs']} recorded PIDs observed stopped {summary['postrun_OS_stopped']}, live {summary['postrun_OS_live']}, unknown {summary['postrun_OS_unknown']}. Only SYNCHRONIZE handles and zero-time waits were used. No process was signaled or enumerated.", '',
        f"Isolated P source sets checked: {summary['isolated_P_source_sets_checked']}; all 131 frozen source bytes matched in {summary['isolated_P_source_sets_match']} sets. Receipt consistency failures: {summary['consistency_failures']} of {summary['consistency_checks']}. The earlier source/package matrix was referenced without rerun. Final-state original-asset/helper checks matched {summary['postrun_original_asset_helper_files_match']}/{summary['postrun_original_asset_helper_files_checked']} known files.", '',
        'OS observations cannot exclude PID reuse, prove whole-host/unknown-descendant cleanup, or replace missing final HE guard receipts. No actual consumer, product/helper import, test, Blender, RPC, signal, backend request or quality scoring was added.', '',
        '| Slot | Arm | Status | CLI PID | Native PID | Native bridge | HE bridge | HE child |',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for slot in slots:
        nb = next((row for row in slot['bridges'] if row['kind'] == 'native'), {})
        he = next((row for row in slot['bridges'] if row['kind'] == 'he'), {})
        lines.append(f"| {slot['ordinal']} | {slot['arm']} | {slot['original_status']} | {slot['consumer'].get('pid')} | {(slot['native'] or {}).get('pid')} | {nb.get('pid')} | {he.get('pid')} | {he.get('HE_child', {}).get('pid')} |")
    (OUT / 'CLEANUP_AUDIT.md').write_text('\n'.join(lines) + '\n', encoding='utf8', newline='\n')
    print(json.dumps(dict(summary=summary, json_sha256=sha(output.read_bytes()), md_sha256=sha((OUT / 'CLEANUP_AUDIT.md').read_bytes()))))


if __name__ == '__main__':
    main()
