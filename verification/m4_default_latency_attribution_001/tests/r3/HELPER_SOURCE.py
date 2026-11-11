"""Fixed per-RPC QA profile switch with observed restoration evidence."""

from contextlib import contextmanager
from pathlib import Path
import sys
import time


class QAProfileStateError(RuntimeError):
    pass


def host_work():
    hosts = {}
    for module in list(sys.modules.values()):
        namespace = getattr(module, '__dict__', {})
        host = namespace.get('_mcp_resident_host')
        if host is not None:
            identity = id(host)
            if identity not in hosts:
                state = getattr(host, '_residency', None)
                generation = None if state is None else {
                    'instance_id': state.instance_id, 'epoch': state.epoch, 'revision': state.revision}
                hosts[identity] = {'module_aliases': [], 'work': host.residency_work(),
                                   'generation': generation}
            hosts[identity]['module_aliases'].append(namespace.get('__name__'))
    hosts = list(hosts.values())
    totals = {}
    for row in hosts:
        for key, value in row['work'].items():
            if type(value) is int:
                totals[key] = totals.get(key, 0) + value
    return {'hosts': hosts, 'totals': totals}


def issue(state, stage, error):
    state['errors'].append({'stage': stage, 'type': type(error).__name__, 'message': str(error)})


def before_rpc(state):
    began = time.perf_counter_ns()
    old = sys.getprofile()
    state['_old_profile'] = old
    state['profile_initial_present'] = old is not None
    names = {'capture_scene', 'capture_task_scene', '_capture', '_resident_capture'}

    def profile(frame, event, arg):
        try:
            if event == 'call' and frame.f_code.co_name in names:
                if Path(frame.f_code.co_filename).name == 'blender_host.py':
                    key = frame.f_code.co_name
                    state['python_calls'][key] = state['python_calls'].get(key, 0) + 1
            elif event in ('c_call', 'c_return', 'c_exception'):
                name = getattr(arg, '__name__', None)
                if name in ('to_mesh', 'calc_loop_triangles'):
                    table = state[{'c_call': 'C_calls', 'c_return': 'C_returns',
                                   'c_exception': 'C_exceptions'}[event]]
                    table[name] = table.get(name, 0) + 1
        except BaseException as exc:
            issue(state, 'callback', exc)
            raise

    state['_callback'] = profile
    state['before'] = host_work()
    if old is not None:
        issue(state, 'initial_profile', QAProfileStateError('initial_profile_not_none'))
    elif type(state['profile_enabled']) is not bool:
        issue(state, 'schedule', QAProfileStateError('worker_sequence_outside_frozen_schedule'))
    elif state['profile_enabled']:
        state['profile_install_attempted'] = True
        sys.setprofile(profile)
        state['profile_installed'] = True
        state['profile_actual_enabled'] = sys.getprofile() is profile
        if not state['profile_actual_enabled']:
            issue(state, 'installation', QAProfileStateError('callback_not_installed'))
    state['before_probe_elapsed_ns'] = time.perf_counter_ns() - began


def after_rpc(state, namespace):
    began = time.perf_counter_ns()
    old_known = '_old_profile' in state
    old = state.pop('_old_profile', None)
    callback = state.pop('_callback', None)
    try:
        current = sys.getprofile()
        state['profile_before_restore_present'] = current is not None
        if old_known and old is None and state['profile_enabled'] is True:
            if callback is not None and current is callback:
                state['profile_restore_attempted'] = True
                try:
                    sys.setprofile(old)
                    state['profile_restore_succeeded'] = True
                except BaseException as exc:
                    issue(state, 'restoration', exc)
            elif state['profile_install_attempted']:
                issue(state, 'restoration', QAProfileStateError(
                    'callback_disappeared' if current is None else 'foreign_callback_replaced_qa'))
        elif old_known and current is not old:
            issue(state, 'restoration', QAProfileStateError('profile_changed_during_OFF_or_blocked_call'))
        state['profile_after_restore_present'] = sys.getprofile() is not None
        state['profile_restored_to_initial'] = old_known and sys.getprofile() is old
        if not state['profile_restored_to_initial']:
            issue(state, 'restoration', QAProfileStateError('initial_profile_not_restored'))
    except BaseException as exc:
        issue(state, 'restore_observation', exc)
    state['profile_scope_ns'] = time.perf_counter_ns() - state.pop('_scope_started_ns')
    try:
        state['after'] = host_work()
        if state['before'] is not None:
            keys = set(state['before']['totals']) | set(state['after']['totals'])
            state['host_residency_delta'] = {
                key: state['after']['totals'].get(key, 0) - state['before']['totals'].get(key, 0)
                for key in sorted(keys)}
    except BaseException as exc:
        issue(state, 'after_sampling', exc)
    state['after_probe_elapsed_ns'] = time.perf_counter_ns() - began
    return state


@contextmanager
def rpc_scope(sequence, profile_enabled, namespace, event, previous_profile_enabled=None):
    state = {'worker_sequence': sequence, 'profile_enabled': profile_enabled,
             'previous_profile_enabled': previous_profile_enabled,
             'before': None, 'after': None, 'host_residency_delta': None,
             'python_calls': {} if profile_enabled is True else None,
             'C_calls': {} if profile_enabled is True else None,
             'C_returns': {} if profile_enabled is True else None,
             'C_exceptions': {} if profile_enabled is True else None,
             'callback_counts_status': 'collected' if profile_enabled is True else 'not_collected',
             'profile_initial_present': None, 'profile_install_attempted': False,
             'profile_installed': False, 'profile_actual_enabled': False,
             'profile_restore_attempted': False, 'profile_restore_succeeded': False,
             'profile_restored_to_initial': None, 'errors': [],
             '_scope_started_ns': time.perf_counter_ns(),
             'scope': 'original QA sampling, fingerprint/file checks and execution; profile scope is inclusive'}
    event['qa_work'] = state
    entered = False
    try:
        before_rpc(state)
        if state['errors']:
            raise QAProfileStateError('QA_profile_boundary_failed')
        entered = True
        yield state
    except BaseException as exc:
        if not entered and not state['errors']:
            issue(state, 'before_sampling_or_installation', exc)
        else:
            state['operation_exception'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        try:
            after_rpc(state, namespace)
        except BaseException as exc:
            issue(state, 'after_boundary', exc)
            state.pop('_old_profile', None)
            state.pop('_callback', None)
            state.pop('_scope_started_ns', None)
        if state['errors']:
            raise QAProfileStateError('QA_profile_boundary_failed: ' + repr(state['errors']))
