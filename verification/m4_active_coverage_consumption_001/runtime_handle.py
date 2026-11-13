"""Read-only ownership and terminal observation of one existing thin runtime."""

import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'verification/m1_task_entry_001_eval/preflight_client.py'
spec = importlib.util.spec_from_file_location('_coverage_readonly_preflight', SOURCE)
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)


def bind_runtime(process, started, expected_executable, expected_sha256, deadline_ns):
    """Bind once after STARTED, retaining the proven process object handle."""
    proof, handle = previous._windows_runtime_proof(process, started.get('pid'), deadline_ns)
    proof.pop('before_stdin', None)
    proof.update(after_stdio_STARTED=True, stdio_STARTED=started,
                 expected_executable=str(Path(expected_executable).resolve()),
                 expected_executable_sha256=expected_sha256)
    if handle is None:
        return proof, None
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    try:
        if time.perf_counter_ns() >= deadline_ns:
            raise TimeoutError('original_route_deadline_during_runtime_binding')
        buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        actual = Path(buffer.value).resolve()
        actual_sha256 = hashlib.sha256(actual.read_bytes()).hexdigest()
        proof.update(actual_executable=str(actual), actual_executable_sha256=actual_sha256,
                     actual_image_checked_ns=time.perf_counter_ns())
        if actual != Path(expected_executable).resolve() or actual_sha256 != expected_sha256:
            raise ValueError('actual_thin_base_image_binding')
        if proof['actual_image_checked_ns'] >= deadline_ns:
            raise TimeoutError('original_route_deadline_after_runtime_image_check')
        return proof, handle
    except BaseException as error:
        proof.update(confirmed=False, status='unknown', error={'type': type(error).__name__, 'message': str(error)})
        proof['failed_binding_handle_closed'] = bool(kernel.CloseHandle(handle))
        return proof, None


def wait_exit(handle, deadline_ns):
    """Wait within the original route deadline, then close the retained handle."""
    began = time.perf_counter_ns()
    row = {'confirmed': False, 'exited': None, 'exit_code': None, 'handle_closed': None,
           'started_ns': began, 'original_deadline_ns': deadline_ns,
           'method': 'retained read-only Windows process handle', 'error': None}
    if handle is None:
        row.update(reason='runtime_handle_unavailable', closed_ns=time.perf_counter_ns())
        return row
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    try:
        # Floor the remaining budget so the wait never introduces a new window.
        milliseconds = max(0, min(0xFFFFFFFE, (deadline_ns - time.perf_counter_ns()) // 1_000_000))
        state = kernel.WaitForSingleObject(handle, milliseconds)
        if state == 0:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise ctypes.WinError(ctypes.get_last_error())
            row.update(exited=True, exit_code=int(code.value))
        elif state == 258:
            row.update(exited=False, reason='runtime_not_observed_exited_within_original_deadline')
        else:
            raise ctypes.WinError(ctypes.get_last_error())
    except BaseException as error:
        row['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        row['handle_closed'] = bool(kernel.CloseHandle(handle))
        row['closed_ns'] = time.perf_counter_ns()
        row['elapsed_ns'] = row['closed_ns'] - began
        row['confirmed'] = bool(row['exited'] is True and row['handle_closed'] is True
                                and row['error'] is None and row['closed_ns'] < deadline_ns)
    return row
