"""Check the owned startup or READY closure using the available original receipts."""


def ready_closure(closure, group, native_proof, *, require_mcp=True):
    native = closure.get('Blender_close') or {}
    status = closure.get('Blender_status') or {}
    ready, closed, config = (status.get(k) or {} for k in ('ready', 'closed', 'config'))
    ack = native.get('response') or {}
    retained = closure.get('Blender_exit') or {}
    proof = native_proof or {}
    pid = ready.get('pid')
    deadline = ready.get('deadline_ns')
    fingerprint = ready.get('initial_fingerprint')
    if (closure.get('errors') or type(pid) is not int or type(deadline) is not int or not fingerprint
            or proof.get('confirmed') is not True or proof.get('runtime_pid') != pid
            or config.get('pid') != pid or config.get('deadline_ns') != deadline
            or config.get('helper_sha256') != ready.get('helper_sha256')
            or config.get('qa_vertex_patch') is not None or closed.get('qa_patch_applied', False) is not False
            or ack.get('status') != 'closed' or ack.get('pid') != pid or ack.get('deadline_ns') != deadline
            or native.get('pid') != pid or native.get('original_deadline_ns') != deadline or native.get('error') is not None
            or native.get('exit_code') != 0 or native.get('process_reaped') is not True
            or closed.get('pid') != pid or closed.get('original_deadline_ns') != deadline
            or closed.get('poisoned') is not False or not (
                fingerprint == closed.get('initial_geometry_fingerprint') == closed.get('final_geometry_fingerprint'))
            or any(item.get(key) is not True for item in (native, status)
                   for key in ('source_file_unchanged', 'protected_files_unchanged'))
            or any(retained.get(key) is not True for key in ('confirmed', 'exited', 'handle_closed'))
            or retained.get('exit_code') != 0):
        raise ValueError('generic_owned_ready_closure_or_original_asset_identity_failed')
    if group == 'P' and require_mcp:
        mcp = closure.get('public_MCP_close') or {}
        mcp_exit = closure.get('public_MCP_exit') or {}
        if (mcp.get('confirmed') is not True or mcp.get('exit_code') != 0
                or any(mcp_exit.get(key) is not True for key in ('confirmed', 'exited', 'handle_closed'))
                or mcp_exit.get('exit_code') != 0):
            raise ValueError('installed_public_MCP_close_failed')
    return {'status': 'ready_closed', 'passed': True, 'pid': pid, 'deadline_ns': deadline,
            'initial_final_fingerprint': fingerprint, 'mcp_closure_required': group == 'P' and require_mcp}


def startup_closure(*, spawn, failure, launch_cleanup, settlement, asset_matches, copy_matches,
                    ready=None, startup_entered=True):
    observed = launch_cleanup or {}
    record = {'status': 'startup_cleanup_unknown', 'passed': None, 'spawn': spawn, 'failure': failure,
              'launch_cleanup': launch_cleanup, 'settlement': settlement, 'ready_seen': bool(ready),
              'asset_matches': asset_matches, 'copy_matches': copy_matches}
    if (asset_matches is False or copy_matches is False or (failure or {}).get('cleanup_errors')
            or observed.get('process_reaped') is False):
        record.update(status='startup_cleanup_failed', passed=False)
        return record
    if not startup_entered and not spawn and asset_matches is True:
        record.update(status='startup_failed_clean', passed=True, basis='not_entered_no_owned_process')
        return record
    if not failure or failure.get('cleanup_errors') != [] or asset_matches is not True:
        return record
    if spawn:
        pid = spawn.get('pid')
        accounted = (type(pid) is int and pid > 0 and settlement and settlement.get('pid') == pid
                     and settlement.get('spawn_status') == 'spawned' and settlement.get('outcome') == 'failed')
        if accounted and copy_matches is True:
            if observed.get('pid') == pid and observed.get('process_reaped') is True:
                record.update(status='startup_failed_clean', passed=True, basis='launcher_Popen_reaped')
            elif launch_cleanup is None:
                record.update(status='startup_failed_clean', passed=True, basis='archived_launcher_cleanup_receipt')
    elif observed.get('no_process_created') is True and settlement and (
            settlement.get('pid') is None and settlement.get('spawn_status') == 'not_spawned'
            and settlement.get('outcome') == 'failed'):
        record.update(status='startup_failed_clean', passed=True, basis='launcher_recorded_no_process_created')
    return record
