"""Offline outer wiring checks. No CLI, owner, Blender or provider is launched."""

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('continuous_driver_under_test', HERE / 'driver.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def consumer(thread='thread-1', expected=None, valid=True):
    return {'thread_id': thread, 'expected_thread_id': expected, 'valid_completion': valid,
            'status': 'completed' if valid else 'failed', 'errors': [], 'summary': {'errors': []},
            'process_reaped': True, 'readers_stopped': True, 'safe_to_continue': True,
            'raw_usage_events': [{'input_tokens': 7, 'output_tokens': 2}]}


class ProjectionTests(unittest.TestCase):
    def test_fixed_plan_and_zero_provider_preflight(self):
        plan = driver.read(driver.BATCH / 'PLAN.json')
        with patch.object(driver.subprocess, 'Popen', side_effect=AssertionError('offline_only')):
            self.assertEqual(driver.contract(plan)['planned_turns'], 18)
            for key, value in (('episode_tool_attempts', 33), ('image_count', 1)):
                changed = copy.deepcopy(plan)
                changed[key] = value
                with self.assertRaises(AssertionError):
                    driver.contract(changed)
            changed = copy.deepcopy(plan)
            changed['sequence'][0], changed['sequence'][1] = changed['sequence'][1], changed['sequence'][0]
            with self.assertRaises(AssertionError):
                driver.contract(changed)

    def test_attempted_without_consumer_is_failed(self):
        rows = driver.execution_rows({'turns': [{'turn_label': 'BASE', 'folder': 'attempt'}]})
        self.assertEqual([row['execution_state'] for row in rows], ['failed', 'not_run', 'not_run'])
        self.assertEqual(driver.counts(rows), {'planned': 3, 'completed': 0, 'failed': 1, 'not_run': 2})
        self.assertEqual(driver.stop_reasons({'coordinator': {'turns': [{'turn_label': 'BASE'}]}})[0]['reason'],
                         'attempted_consumer_lifecycle_unconfirmed')

    def test_real_thread_and_observed_session_fields_remain_separate(self):
        turns = []
        for index, label in enumerate(driver.TURNS):
            turns.append({'turn_label': label, 'consumer': consumer(expected=None if index == 0 else 'thread-1'),
                          'status_after': {'observed_product_session_ids': ['actual-model-arg']}})
        result = driver.continuity({'turns': turns})
        self.assertTrue(result['three_turn_thread_continuity'])
        self.assertEqual(result['configured_session_id'], 'current-scene')
        self.assertEqual(result['observed_product_session_ids'], ['actual-model-arg'])
        turns[2]['consumer']['thread_id'] = 'replacement'
        self.assertFalse(driver.continuity({'turns': turns})['three_turn_thread_continuity'])

    def test_stop_only_actual_unavailable_or_unknown(self):
        failed = consumer(valid=False)
        failed['errors'] = [{'message': 'missing_usage'}]
        failed['provider_retry_observations'] = [{'text': 'HTTP 503 reconnecting'}]
        row = {'owner_started': True, 'owner_finish': {'confirmed': True},
               'coordinator': {'turns': [{'turn_label': 'BASE', 'consumer': failed}]}}
        self.assertEqual(driver.stop_reasons(row), [])
        failed['errors'] = [{'message': 'HTTP status 503 service unavailable'}]
        self.assertEqual(driver.stop_reasons(row)[0]['reason'], 'provider_unavailable')
        failed['errors'] = [{'error': {'code': 429}}]
        self.assertEqual(driver.stop_reasons(row)[0]['reason'], 'provider_unavailable')
        failed.update(turn_completed_ns=1, final_received_ns=2, exit_code=0)
        self.assertEqual(driver.stop_reasons(row), [])
        failed['mutation_unknown'] = True
        self.assertEqual(driver.stop_reasons(row)[0]['reason'], 'consumer_action_state_unknown')
        failed['mutation_unknown'] = False
        failed['bridge_cleanup'] = {'confirmed': False}
        self.assertEqual(driver.stop_reasons(row)[0]['reason'], 'consumer_cleanup_unconfirmed')
        failed['bridge_cleanup'] = {'confirmed': None}
        self.assertEqual(driver.stop_reasons(row), [])
        row['owner_finish']['confirmed'] = False
        self.assertEqual(driver.stop_reasons(row)[0]['reason'], 'owned_close_unconfirmed')

    def test_short_runtime_deepest_known_paths(self):
        root = driver.ROOT / '.m4cc1' / 'C3'
        names = ('c/turns/REPEAT/attachments/' + 'bridge_' + 'f' * 32 + '/004/RX.bin',
                 'c/turns/REPEAT/owner_turn/stdioslice/003/RX.bin',
                 'owner/native/WIRE/128/RESPONSE.bin')
        self.assertTrue(all(len(str(root / name)) < 260 for name in names))

    def test_exception_recovery_uses_actual_turn_prefix(self):
        with tempfile.TemporaryDirectory(prefix='m4cc1-recovery-offline-') as temporary:
            runtime = Path(temporary)
            base = runtime / 'c/turns/BASE'
            base.mkdir(parents=True)
            (runtime / 'c/turns/REPEAT').mkdir()
            driver.save(base / 'CONSUMER.json', consumer())
            recovered = driver.recorded_coordinator(runtime)
            self.assertEqual([row['turn_index'] for row in recovered['turns']], [1, 2])
            self.assertEqual([row['execution_state'] for row in driver.execution_rows(recovered)],
                             ['completed', 'failed', 'not_run'])


class OuterLifecycleTests(unittest.TestCase):
    def run_fake(self, *, coordinator_error=False, startup_error=False):
        with tempfile.TemporaryDirectory(prefix='m4cc1-offline-') as temporary:
            base = Path(temporary)
            batch, runtime_root = base / 'batch', base / 'r'
            (batch / 'inputs').mkdir(parents=True)
            (batch / 'inputs/base').write_bytes(b'base')
            (batch / 'inputs/recheck').write_bytes(b'recheck')
            plan = {'runtime_root': str(runtime_root), 'inputs': {'prompt_base': 'inputs/base',
                    'prompt_recheck': 'inputs/recheck'}, 'installation_ready': {'dependency_python': 'offline-python'}}
            slot = {'cell': 'N1', 'episode': 'N1', 'group': 'N', 'pair': 1,
                    'round': 1, 'anonymous_episode_id': 'anonymous', 'anonymous_turn_ids': ['a', 'b', 'c']}
            events = []
            clock = [10**9]
            real_save = driver.save

            def now():
                clock[0] += 1000
                return clock[0]

            def saving(path, value):
                real_save(path, value)
                events.append(('writeclose', Path(path).name, now()))

            def prepare(slot, plan, runtime, started, deadline):
                events.append(('prepare', started, now()))
                self.assertLess(started, clock[0])
                self.assertEqual(deadline, started + driver.EPISODE_NS)
                return {'group': 'N'}, ['offline-owner'], deadline, {'source': 'bound'}

            def popen(*arguments, **keywords):
                events.append(('Popen', now()))
                return SimpleNamespace(pid=17)

            def ready(*arguments):
                if startup_error:
                    raise ValueError('synthetic_start_failure')

            def finish(runtime, process):
                events.append(('finish', now()))
                receipt = {'confirmed': True, 'close': {}}
                saving(runtime / 'OWNER_FINISH.json', receipt)
                return receipt

            def postclose(row, runtime, plan, guard, deadline, old, post):
                events.append(('postclose', now()))
                row['postclose_verification'] = {'passed': True}
                saving(runtime / 'POST_READBACK.json', {'synthetic': True})

            pack = driver.load('offline_original_packer', driver.ROOT /
                               'verification/m4_surface_scan_compact_consumption_001/runtime/pack_quality.py')
            capture = pack.capture_cell

            def archive(folder, destination):
                result = capture(folder, destination)
                events.append(('archive_closed', now()))
                return result

            def coordinate(**arguments):
                output = arguments['output']
                self.assertFalse(output.exists())
                self.assertEqual(arguments['work'], runtime_root / 'N1/w')
                self.assertEqual(arguments['turn_budget_ns'], driver.TURN_NS)
                self.assertIsNone(arguments['local_cli'])
                self.assertEqual(arguments['prompts'], [b'base', b'recheck', b'recheck'])
                output.mkdir()
                arguments['work'].mkdir()
                if coordinator_error:
                    raise ValueError('synthetic_coordinator_failure')
                turns = []
                for index, label in enumerate(driver.TURNS):
                    record = consumer(expected=None if index == 0 else 'thread-1')
                    folder = output / 'turns' / label
                    folder.mkdir(parents=True)
                    saving(folder / 'CONSUMER.json', record)
                    turns.append({'turn_label': label, 'folder': str(folder), 'consumer': record})
                arguments['finish']()
                arguments['finish']()  # Repeated callback cannot signal or finish the actor again.
                return {'turns': turns, 'qualified_execution': True}

            modules = {'_continuous_original_driver': SimpleNamespace(finish=finish),
                       '_continuous_fixed_coordinator': SimpleNamespace(run_episode=coordinate,
                           pack=SimpleNamespace(capture_cell=archive)),
                       '_continuous_fixed_attach': SimpleNamespace(),
                       '_continuous_terminal_readback': SimpleNamespace()}
            with patch.object(driver, 'BATCH', batch), patch.object(driver, 'load', side_effect=lambda name, path: modules[name]), \
                    patch.object(driver, 'prepare_config', side_effect=prepare), \
                    patch.object(driver, 'wait_ready', side_effect=ready), \
                    patch.object(driver, 'postclose', side_effect=postclose), \
                    patch.object(driver, 'save', side_effect=saving), \
                    patch.object(driver.subprocess, 'Popen', side_effect=popen), \
                    patch.object(driver.time, 'perf_counter_ns', side_effect=now):
                row = driver.run_one(slot, plan)
            self.assertEqual(row['owner_finish_calls'], 1)
            self.assertEqual(sum(event[0] == 'finish' for event in events), 1)
            self.assertEqual(sum(event[0] == 'Popen' for event in events), 1)
            self.assertTrue((runtime_root / 'N1').is_dir())
            with zipfile.ZipFile(row['runtime_archive']) as archive_file:
                self.assertIn('OWNER_FINISH.json', archive_file.namelist())
                self.assertIn('POST_READBACK.json', archive_file.namelist())
            manifest = json.loads((batch / 'episodes/N1/RUNTIME_MANIFEST.json').read_bytes())
            self.assertIn('OWNER_FINISH.json', manifest['members'])
            end = row['timing']['business_receipts_closed_ns']
            archive_closed = next(event[1] for event in events if event[0] == 'archive_closed')
            result_closed = next(event[2] for event in events if event[:2] == ('writeclose', 'OUTER_RESULT.json'))
            self.assertGreater(end, result_closed)
            self.assertGreater(result_closed, archive_closed)
            return row

    def test_full_outer_scope_single_finish_and_no_usage_sum(self):
        row = self.run_fake()
        self.assertTrue(row['outer_valid_completion'])
        self.assertEqual(row['execution_counts']['completed'], 3)
        self.assertIsNone(row['usage_aggregation'])
        self.assertEqual(row['coordinator']['turns'][2]['consumer']['raw_usage_events'],
                         [{'input_tokens': 7, 'output_tokens': 2}])

    def test_coordinator_throw_still_finishes_and_archives(self):
        row = self.run_fake(coordinator_error=True)
        self.assertFalse(row['outer_valid_completion'])
        self.assertEqual(row['execution_counts']['not_run'], 3)
        self.assertEqual(row['stop_reasons'], [])

    def test_startup_throw_still_finishes_and_archives(self):
        row = self.run_fake(startup_error=True)
        self.assertFalse(row['outer_valid_completion'])
        self.assertEqual(row['stop_reasons'], [])


class BatchBoundaryTests(unittest.TestCase):
    def run_batch_fixture(self, failing_index=None, stopping_index=None):
        plan = driver.read(driver.BATCH / 'PLAN.json')
        seen = []

        def run_one(slot, plan):
            index = len(seen)
            seen.append(slot['cell'])
            if index == stopping_index:
                raise RuntimeError('synthetic_unhandled_boundary')
            failed = index == failing_index
            rows = [{'turn_label': label, 'consumer': consumer(thread=slot['cell'],
                    expected=None if turn == 0 else slot['cell'], valid=not failed)}
                    for turn, label in enumerate(driver.TURNS)]
            coordinator = {'turns': rows}
            return {**slot, 'coordinator': coordinator, 'continuity': driver.continuity(coordinator),
                    'execution_counts': driver.counts(driver.execution_rows(coordinator)), 'stop_reasons': []}

        with tempfile.TemporaryDirectory(prefix='m4cc1-batch-offline-') as temporary:
            batch = Path(temporary)
            plan['runtime_root'] = str(batch / 'runtime')
            with patch.object(driver, 'BATCH', batch), patch.object(driver, 'contract', return_value={}), \
                    patch.object(driver, 'run_one', side_effect=run_one):
                result = driver.run_batch(plan)
        return seen, result

    def test_isolated_execution_failure_continues_fixed_six(self):
        seen, result = self.run_batch_fixture(failing_index=1)
        self.assertEqual(tuple(seen), driver.CELLS)
        self.assertEqual(result['execution_counts'], {'planned': 18, 'completed': 15, 'failed': 3, 'not_run': 0})
        self.assertEqual(result['stop_reasons'], [])

    def test_unhandled_boundary_retains_all_eighteen_slots(self):
        seen, result = self.run_batch_fixture(stopping_index=2)
        self.assertEqual(tuple(seen), driver.CELLS[:3])
        self.assertEqual(len(result['records']), 3)
        self.assertEqual([row['cell'] for row in result['not_run_episodes']], list(driver.CELLS[3:]))
        self.assertEqual(result['execution_counts'], {'planned': 18, 'completed': 6, 'failed': 0, 'not_run': 12})
        self.assertFalse(result['records'][2]['outer_valid_completion'])


if __name__ == '__main__':
    unittest.main()
