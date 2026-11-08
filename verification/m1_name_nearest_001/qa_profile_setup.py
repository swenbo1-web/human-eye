"""Draft read-only QA counting hook; prefix QA_PLAN, run only by the owner.

This file is not executed during QA preparation. It does not alter geometry,
product functions, request parameters or returned packets. It self-disarms after
the fixed number of original nearest host calls, including controlled refusal.
"""
import hashlib
import json
from pathlib import Path
import sys
import time

assert sys.getprofile() is None, 'do_not_replace_an_existing_profile'
assert globals().get('_m1_name_nearest_qa') is None, 'single_setup_only'
_m1_host_path = str(Path(QA_PLAN['host_source_path']))
_m1_host_sha = QA_PLAN['host_source_sha256']
_m1_profile_path = Path(QA_PLAN['profile_output_path'])
assert hashlib.sha256(Path(_m1_host_path).read_bytes()).hexdigest() == _m1_host_sha
assert QA_PLAN['expected_nearest_calls'] == 4
_m1_name_nearest_qa = dict(host_source_path=_m1_host_path, host_source_sha256=_m1_host_sha,
    expected_nearest_calls=4, calls=[], active=None, profile_overhead_ns=0,
    all_host_counts={name:0 for name in ('capture_nearest_candidates', '_objects', '_capture', 'capture_task_scene', 'capture_scene')},
    standalone_host_calls=[], disarmed=False, scope='QA hook counts only; no extra geometry capture')


def _m1_qa_save():
    _m1_profile_path.write_text(json.dumps(_m1_name_nearest_qa, indent=2, allow_nan=False)+'\n', encoding='utf8')


def _m1_qa_profile(frame, event, arg):
    if event not in ('call', 'return') or frame.f_code.co_filename != _m1_host_path:
        return
    name = frame.f_code.co_name
    if name not in ('capture_nearest_candidates', '_objects', '_capture', 'capture_task_scene', 'capture_scene'):
        return
    entered = time.perf_counter_ns()
    state = _m1_name_nearest_qa
    try:
        if event == 'call':
            state['all_host_counts'][name] += 1
            if name != 'capture_nearest_candidates' and state['active'] is None:
                state['standalone_host_calls'].append(dict(name=name, at_ns=entered))
        if name == 'capture_nearest_candidates' and event == 'call':
            assert state['active'] is None, 'no_nested_nearest_capture'
            assert len(state['calls']) < state['expected_nearest_calls'], 'fixed_qa_call_count'
            assert frame.f_globals.get('_READONLY_LOADED_HOST_SHA256') == _m1_host_sha
            selector = frame.f_locals.get('selector')
            row = dict(ordinal=len(state['calls'])+1, started_ns=entered,
                selector_fields=sorted(selector) if type(selector) is dict else None,
                focal_id_supplied=frame.f_locals.get('focal_id') is not None,
                counts={'_objects':0, '_capture':0, 'capture_task_scene':0, 'capture_scene':0},
                object_enumeration_callsites=[], returned_packet=False)
            state['calls'].append(row)
            state['active'] = row
        elif state['active'] is not None and event == 'call':
            row = state['active']
            row['counts'][name] += 1
            if name == '_objects':
                row['object_enumeration_callsites'].append(dict(
                    caller=frame.f_back.f_code.co_name, caller_lineno=frame.f_back.f_lineno))
        elif name == 'capture_nearest_candidates' and event == 'return':
            row = state['active']
            assert row is not None
            row.update(ended_ns=entered, returned_packet=type(arg) is dict)
            if type(arg) is dict:
                row['work'] = arg.get('work')
                row['same_main_thread_read'] = arg.get('binding',{}).get('same_main_thread_read')
            row['elapsed_ns'] = entered-row['started_ns']
            state['active'] = None
            if len(state['calls']) == state['expected_nearest_calls']:
                sys.setprofile(None)
                state['disarmed'] = True
            _m1_qa_save()
    except BaseException as error:
        sys.setprofile(None)
        state['disarmed'] = True
        state['hook_error'] = dict(type=type(error).__name__, message=str(error))
        _m1_qa_save()
        raise
    finally:
        state['profile_overhead_ns'] += time.perf_counter_ns()-entered
        if state['disarmed']:
            _m1_qa_save()


_m1_qa_save()
sys.setprofile(_m1_qa_profile)
print('M1_NAME_NEAREST_QA_SETUP:'+json.dumps(dict(armed=True, expected_nearest_calls=4), separators=(',',':')))
