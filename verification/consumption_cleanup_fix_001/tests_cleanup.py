"""Six bounded offline mock groups; this file never launches a real backend.

Fixtures are fixed synthetic JSON bytes in temporary directories under HERE.
Only the parent's controlled driver executes these tests. Subprocess, network,
signals and real Windows process inspection are blocked in every test method.
"""
from contextlib import ExitStack
import ctypes
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import runner


NATIVE_PID = 11001
HE_PID = 22002
CHILD_PID = 33003
LEDGER = 'synthetic://fixed-slot-01/BUDGET.json'
PAIRS = [('T01', 'N'), ('T01', 'P'), ('T02', 'P'), ('T02', 'N'),
         ('T03', 'N'), ('T03', 'P'), ('T04', 'P'), ('T04', 'N')]


def fixed_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode('utf8')


def write_json(path, value):
    path.write_bytes(fixed_bytes(value))


def row_for(result, kind):
    return next(row for row in result['evidence'] if row['kind'] == kind)


class CleanupReceiptChecks(unittest.TestCase):
    def setUp(self):
        self.guards = ExitStack()
        self.addCleanup(self.guards.close)
        self.forbidden_calls = []

        def forbidden(*args, **kwargs):
            self.forbidden_calls.append((args, kwargs))
            raise AssertionError('offline fixture attempted a real process/network operation')

        for name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
            self.guards.enter_context(patch.object(runner.subprocess, name, side_effect=forbidden))
        self.guards.enter_context(patch.object(os, 'kill', side_effect=forbidden))
        self.guards.enter_context(patch.object(os, 'system', side_effect=forbidden))
        self.guards.enter_context(patch.object(socket, 'socket', side_effect=forbidden))
        self.guards.enter_context(patch.object(socket, 'create_connection', side_effect=forbidden))
        self.guards.enter_context(patch.object(ctypes, 'WinDLL', side_effect=forbidden, create=True))
        self.addCleanup(lambda: self.assertEqual(self.forbidden_calls, []))

    def fixture(self, root, arm='N', child=True):
        cell = dict(arm=arm, audit_root=str(root), ledger_path=LEDGER)
        for kind, pid in ([('native', NATIVE_PID), ('he', HE_PID)] if arm == 'P'
                          else [('native', NATIVE_PID)]):
            folder = root / ('bridge_' + kind)
            folder.mkdir()
            write_json(folder / 'STARTED.json', dict(kind=kind, pid=pid,
                       ledger_path=LEDGER, started_ns=100))
        if arm == 'P' and child:
            write_json(root / 'bridge_he/HE_CHILD_STARTED.json',
                       dict(pid=CHILD_PID, started_ns=101))
        return cell

    def bridge_exit(self, kind='native', **updates):
        value = dict(kind=kind, pid=NATIVE_PID if kind == 'native' else HE_PID,
                     ledger_path=LEDGER, normal_exit=True, ended_ns=200)
        if kind == 'he':
            value.update(he_child_pid=CHILD_PID, he_child_reaped=True)
        value.update(updates)
        return value

    def test_01_native_stopped_without_exit_preserves_os_evidence(self):
        with tempfile.TemporaryDirectory(dir=HERE, prefix='mock-native-no-exit-') as name:
            root = Path(name)
            cell = self.fixture(root)
            start_bytes = (root / 'bridge_native/STARTED.json').read_bytes()
            with patch.object(runner, 'process_exited', return_value=True) as query:
                result = runner.registered_tree_cleanup(cell)
            query.assert_called_once_with(NATIVE_PID)
            self.assertTrue(result['confirmed'])
            row = row_for(result, 'native')
            self.assertTrue(row['confirmed'])
            self.assertIs(row['process_stopped'], True)
            self.assertEqual(row['started'], json.loads(start_bytes))
            self.assertIsNone(row['graceful_exit_receipt'])
            self.assertIsNone(row.get('exit_code'))
            self.assertEqual((root / 'bridge_native/STARTED.json').read_bytes(), start_bytes)
            self.assertFalse((root / 'bridge_native/EXIT.json').exists())

    def test_02_native_exit_control_and_conflicting_receipts(self):
        variants = [
            ('matching', self.bridge_exit(normal_exit=False, exit_code=17), True),
            ('pid_conflict', self.bridge_exit(pid=CHILD_PID), False),
            ('ledger_conflict', self.bridge_exit(ledger_path='synthetic://different-slot'), False),
            ('kind_conflict', dict(self.bridge_exit(), kind='he'), False),
            ('null_receipt', b'null\n', False),
            ('malformed', b'{fixed-invalid-json\n', False),
        ]
        for label, receipt, expected in variants:
            with self.subTest(fixture=label), tempfile.TemporaryDirectory(
                    dir=HERE, prefix='mock-native-exit-') as name:
                root = Path(name)
                cell = self.fixture(root)
                path = root / 'bridge_native/EXIT.json'
                path.write_bytes(receipt if isinstance(receipt, bytes) else fixed_bytes(receipt))
                before = path.read_bytes()
                with patch.object(runner, 'process_exited', return_value=True):
                    result = runner.registered_tree_cleanup(cell)
                self.assertIs(result['confirmed'], expected)
                row = row_for(result, 'native')
                self.assertIs(row['process_stopped'], True)
                if label == 'matching':
                    self.assertEqual(row['graceful_exit_receipt'], receipt)
                    self.assertEqual(row['graceful_exit_receipt']['exit_code'], 17)
                    self.assertFalse(row['graceful_exit_receipt']['normal_exit'])
                self.assertEqual(path.read_bytes(), before)

    def test_03_native_live_unknown_denied_or_unbound_cannot_confirm(self):
        variants = [
            ('live', False, None), ('unknown', None, None),
            ('access_denied', PermissionError('fixed offline denial'), None),
            ('missing_started', True, 'missing'),
            ('ledger_mismatch', True, dict(ledger_path='synthetic://wrong-slot')),
            ('kind_mismatch', True, dict(kind='he')),
            ('boolean_pid', True, dict(pid=True)),
            ('zero_pid', True, dict(pid=0)),
            ('negative_pid', True, dict(pid=-1)),
            ('string_pid', True, dict(pid='11001')),
            ('beyond_DWORD_pid', True, dict(pid=2**32)),
        ]
        for label, os_result, mutation in variants:
            with self.subTest(fixture=label), tempfile.TemporaryDirectory(
                    dir=HERE, prefix='mock-native-unknown-') as name:
                root = Path(name)
                cell = self.fixture(root)
                start_path = root / 'bridge_native/STARTED.json'
                if mutation == 'missing':
                    start_path.unlink()
                elif isinstance(mutation, dict):
                    start = json.loads(start_path.read_bytes())
                    start.update(mutation)
                    write_json(start_path, start)
                kwargs = ({'side_effect': os_result} if isinstance(os_result, BaseException)
                          else {'return_value': os_result})
                with patch.object(runner, 'process_exited', **kwargs) as query:
                    result = runner.registered_tree_cleanup(cell)
                self.assertFalse(result['confirmed'])
                self.assertFalse(row_for(result, 'native')['confirmed'])
                if mutation is not None:
                    query.assert_not_called()
                else:
                    query.assert_called_once_with(NATIVE_PID)
                    observed = row_for(result, 'native')['process_stopped']
                    self.assertIs(observed, None if isinstance(os_result, BaseException) else os_result)

        # Invalid identities must not reach even the blocked Windows API hook.
        for invalid_pid in (None, True, False, 0, -1, '11001', 1.5, 2**32):
            with self.subTest(invalid_pid=invalid_pid):
                self.assertIsNone(runner.process_exited(invalid_pid))

        # The real helper runs only against this in-memory Windows API facade.
        for label, handle, error, wait_result, expected in [
            ('denied', None, 5, 0, None),
            ('invalid_pid', None, 87, 0, True),
            ('wait_timeout', 123, 0, 258, False),
            ('wait_failed', 123, 0, 0xFFFFFFFF, None),
            ('signaled', 123, 0, 0, True),
        ]:
            with self.subTest(mock_os=label):
                kernel = types.SimpleNamespace(OpenProcess=Mock(return_value=handle),
                    WaitForSingleObject=Mock(return_value=wait_result), CloseHandle=Mock())
                with patch.object(ctypes, 'WinDLL', return_value=kernel, create=True), \
                        patch.object(ctypes, 'get_last_error', return_value=error, create=True):
                    self.assertIs(runner.process_exited(NATIVE_PID), expected)
                if handle:
                    kernel.WaitForSingleObject.assert_called_once_with(handle, 1000)
                    kernel.CloseHandle.assert_called_once_with(handle)
                else:
                    kernel.WaitForSingleObject.assert_not_called()
                    kernel.CloseHandle.assert_not_called()

    def test_04_he_bridge_stopped_does_not_hide_live_unknown_or_unidentified_child(self):
        variants = [('live_child', False, True), ('unknown_child', None, True),
                    ('unidentified_child', None, False)]
        for label, child_stopped, child_present in variants:
            with self.subTest(fixture=label), tempfile.TemporaryDirectory(
                    dir=HERE, prefix='mock-he-unsafe-') as name:
                root = Path(name)
                cell = self.fixture(root, arm='P', child=child_present)
                query_results = {NATIVE_PID: True, HE_PID: True, CHILD_PID: child_stopped}
                with patch.object(runner, 'process_exited', side_effect=query_results.__getitem__) as query:
                    result = runner.registered_tree_cleanup(cell)
                self.assertFalse(result['confirmed'])
                self.assertTrue(row_for(result, 'native')['confirmed'])
                he = row_for(result, 'he')
                self.assertIs(he['process_stopped'], True)
                self.assertFalse(he['confirmed'])
                if child_present:
                    self.assertIs(he['he_child']['process_stopped'], child_stopped)
                    self.assertIn(((CHILD_PID,), {}), [(call.args, call.kwargs) for call in query.call_args_list])
                else:
                    self.assertNotIn(CHILD_PID, [call.args[0] for call in query.call_args_list])

    def test_05_he_known_child_stopped_without_receipts_and_identity_conflicts(self):
        variants = [('no_receipts', None, None, True),
                    ('valid_child_receipt', None, dict(pid=CHILD_PID, reaped=True, exit_code=23, errors=[]), True),
                    ('bridge_child_pid_conflict', self.bridge_exit('he', he_child_pid=NATIVE_PID), None, False),
                    ('child_receipt_pid_conflict', None, dict(pid=NATIVE_PID, reaped=True, exit_code=0), False),
                    ('bridge_child_bool_pid', self.bridge_exit('he', he_child_pid=True), None, False),
                    ('bridge_child_float_pid', self.bridge_exit('he', he_child_pid=1.0), None, False),
                    ('child_is_bridge', None, None, False)]
        for label, bridge_receipt, child_receipt, expected in variants:
            with self.subTest(fixture=label), tempfile.TemporaryDirectory(
                    dir=HERE, prefix='mock-he-stopped-') as name:
                root = Path(name)
                cell = self.fixture(root, arm='P')
                folder = root / 'bridge_he'
                if label == 'child_is_bridge':
                    write_json(folder / 'HE_CHILD_STARTED.json', dict(pid=HE_PID, started_ns=101))
                elif label in ('bridge_child_bool_pid', 'bridge_child_float_pid'):
                    # Equality with integer 1 must not bypass PID type validation.
                    write_json(folder / 'HE_CHILD_STARTED.json', dict(pid=1, started_ns=101))
                if bridge_receipt is not None:
                    write_json(folder / 'EXIT.json', bridge_receipt)
                if child_receipt is not None:
                    write_json(folder / 'HE_CHILD_EXIT.json', child_receipt)
                before = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
                with patch.object(runner, 'process_exited', return_value=True):
                    result = runner.registered_tree_cleanup(cell)
                self.assertIs(result['confirmed'], expected)
                he = row_for(result, 'he')
                self.assertIs(he['process_stopped'], True)
                if expected:
                    child = he['he_child']
                    self.assertIs(child['process_stopped'], True)
                    self.assertEqual(child['graceful_exit_receipt'], child_receipt)
                    self.assertIsNone(he['graceful_exit_receipt'])
                    if child_receipt is None:
                        self.assertIsNone(child.get('exit_code'))
                        self.assertFalse((folder / 'HE_CHILD_EXIT.json').exists())
                    else:
                        self.assertEqual(child['graceful_exit_receipt']['exit_code'], 23)
                self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}, before)

    def test_06_unknown_cleanup_still_blocks_later_slots_without_resetting_contract(self):
        with tempfile.TemporaryDirectory(dir=HERE, prefix='mock-slot-stop-') as name:
            root = Path(name)
            audit = root / 'registered'
            audit.mkdir()
            cell = self.fixture(audit)
            budget_path = root / 'BUDGET.json'
            original_deadline = 190_000_000_000
            budget = dict(deadline_perf_ns=original_deadline, actions=0, physical_rpc=0,
                          public_text_bytes=911, halted=False, inflight_rpc=[])
            write_json(budget_path, budget)
            budget_before = budget_path.read_bytes()
            limits = dict(answer_seconds=180, chain_seconds=600, cleanup_reserve_seconds=60,
                model_answers=8, native_sessions=8, action_observation_threshold=8,
                public_text_bytes_per_answer=1048576, execute_rpc_per_answer=128,
                close_rpc_per_answer=1, total_physical_rpc=1032, output_tokens_hard_limit=None)
            plan = dict(cells=[dict(ordinal=i, task_id=task, arm=arm)
                              for i, (task, arm) in enumerate(PAIRS, 1)],
                        limits=limits, neutral_run_root='synthetic://never-created-native-root')
            plan_before = fixed_bytes(plan)
            output = root / 'output'
            original_window_deadline = 3_610_000_000_000
            cleanups = []

            def first_cell(actual_plan, entry, task, native, folder, *, window_deadline_ns):
                self.assertIs(actual_plan, plan)
                self.assertEqual(window_deadline_ns, original_window_deadline)
                saved = json.loads((output / 'RESULTS.json').read_bytes())
                self.assertEqual(len(saved['cells']), 8)
                self.assertEqual([r['denominator'] for r in saved['cells']], [1] * 8)
                cleanup = runner.registered_tree_cleanup(cell)
                cleanups.append(cleanup)
                return dict(status='error', reason='synthetic unknown process stop',
                            dispatch_ns=10_000_000_000, safe_to_continue=cleanup['confirmed'])

            material = dict(tasks=[dict(task_id=task) for task in ('T01', 'T02', 'T03', 'T04')])
            with patch.object(runner, 'process_exited', return_value=None), \
                    patch.object(runner.time, 'perf_counter_ns', return_value=10_000_000_000), \
                    patch.object(runner, 'run_cell', side_effect=first_cell) as dispatch:
                result = runner.execute_slots(plan, {}, material, types.SimpleNamespace(), output,
                                              window_deadline_ns=original_window_deadline)
            self.assertEqual(dispatch.call_count, 1)
            self.assertEqual(len(cleanups), 1)
            self.assertFalse(cleanups[0]['confirmed'])
            rows = result['cells']
            self.assertEqual(len(rows), 8)
            self.assertEqual([(r['task_id'], r['arm']) for r in rows], PAIRS)
            self.assertEqual([r['denominator'] for r in rows], [1] * 8)
            self.assertEqual(rows[0]['status'], 'error')
            for row in rows[1:]:
                self.assertEqual(row['status'], 'not_run')
                self.assertEqual(row['reason'], 'previous_slot_cleanup_not_confirmed_no_further_start')
                self.assertIsNone(row['dispatch_ns'])
            self.assertEqual(fixed_bytes(plan), plan_before)
            self.assertEqual(budget_path.read_bytes(), budget_before)
            self.assertEqual(json.loads(budget_before)['deadline_perf_ns'], original_deadline)


if __name__ == '__main__':
    unittest.main(verbosity=2)
