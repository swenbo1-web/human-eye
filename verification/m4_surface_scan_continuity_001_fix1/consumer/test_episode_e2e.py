"""Provider-free local-process tests through consume_turn and run_episode."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import unittest
from unittest import mock
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


episode = load('_fix1_episode_e2e', HERE / 'episode.py')
owner_module = load('_fix1_owner_e2e', HERE / 'fake_owner.py')


def allocate_run():
    parent = HERE / 'offline'
    parent.mkdir(exist_ok=True)
    index = len(list(parent.glob('attempt_*'))) + 1
    result = parent / ('attempt_' + str(index).zfill(2))
    result.mkdir(exist_ok=False)
    return result


class EpisodeEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_directory = allocate_run()
        ready = json.loads((ROOT / 'verification/m4_surface_scan_continuity_001/inputs/C_READY.json').read_bytes())
        cls.python = ready['dependency_python']
        cls.prompt = (ROOT / 'verification/m4_surface_scan_continuity_001/inputs/PROMPT_T1.txt').read_bytes()
        cls.prompts = [cls.prompt, '请重新检查当前场景。'.encode('utf8') + cls.prompt,
                       '请重新检查当前场景。'.encode('utf8') + cls.prompt]

    def setUp(self):
        self.owner = None

    def tearDown(self):
        if self.owner is not None and self.owner.finish_calls == 0:
            self.owner.finish()

    def exercise(self, group='N', scenario='normal', turn_budget_ns=5 * 10**9, provider_fixture=True):
        folder = self.run_directory / hashlib.sha256(self._testMethodName.encode('utf8')).hexdigest()[:6]
        folder.mkdir()
        (folder / 'CASE.json').write_text(json.dumps({'test': self._testMethodName}) + '\n', encoding='utf8')
        deadline = time.perf_counter_ns() + 25 * 10**9
        episode_id = 'synthetic-' + self._testMethodName
        self.owner = owner_module.FakeOwner(folder / 'owner', episode_id, group, deadline, scenario)
        fake = HERE / 'fake_cli.py'
        local_cli = {'command': [self.python, '-I', '-B', '-X', 'utf8', str(fake)],
                     'script_sha256': hashlib.sha256(fake.read_bytes()).hexdigest()} if provider_fixture else None
        result = episode.run_episode(episode_id=episode_id, output=folder / 'episode', work=folder / 'work',
            cell={'group': 'N' if group == 'N' else 'P', 'endpoint': str(self.owner.endpoint),
                  'audit_dir': str(self.owner.folder)}, install={'python': self.python},
            plan={'image_count': 0, 'new_images': 0, 'inputs': {}, 'model_consumer_enabled': False},
            prompts=self.prompts, episode_deadline_ns=deadline, turn_budget_ns=turn_budget_ns,
            control=self.owner.control, finish=self.owner.finish,
            anonymous_episode_id='anonymous-synthetic-episode', local_cli=local_cli)
        self.assertEqual(self.owner.finish_calls, 1)
        self.assertTrue(result['owner_finish']['confirmed'])
        self.assertIsNone(result['usage_aggregation'])
        self.assertEqual(result['model_continuity_attestation'], 'pending_actual_consumer')
        self.assertTrue(all(row['finish_calls'] == 0 for row in self.owner.events))
        return folder, result

    def verify_success(self, group):
        folder, result = self.exercise(group)
        self.assertTrue(result['qualified_execution'], result['errors'])
        self.assertEqual(result['counts'], {'completed': 3, 'failed': 0, 'not_run': 0})
        self.assertEqual(self.owner.edits, 1)
        self.assertEqual(self.owner.calls, 3)
        self.assertEqual([row['operation'] for row in self.owner.events].count('qa_advance'), 1)
        records = [row['consumer'] for row in result['turns']]
        self.assertEqual(len({row['thread_id'] for row in records}), 1)
        self.assertEqual(len({row['shared_work'] for row in records}), 1)
        self.assertEqual(len({row['endpoint'] for row in records}), 1)
        self.assertEqual(len({row['consumer_pid'] for row in records}), 3)
        self.assertEqual(len({row['archive']['archive'] for row in records}), 3)
        for index, record in enumerate(records, 1):
            self.assertEqual(record['execution_kind'], 'synthetic_local_process')
            self.assertTrue(record['process_reaped'] and record['readers_stopped'])
            self.assertTrue(record['bridge_cleanup']['confirmed'])
            self.assertFalse(record['process_cleanup']['tree_kill_requested'])
            self.assertEqual(len(record['raw_usage_events']), 1)
            self.assertIsNone(record['summary']['usage_aggregation'])
            self.assertLessEqual(record['deadline_ns'], record['episode_deadline_ns'])
            argv = record['frozen_cli_argv']
            self.assertNotIn('--ephemeral', argv)
            if index == 1:
                self.assertNotIn('resume', argv)
            else:
                self.assertIn('resume', argv)
                self.assertEqual(argv[-2], records[0]['thread_id'])
            fake = json.loads((folder / 'work' / ('FAKE_TURN_' + str(index) + '.json')).read_bytes())
            self.assertEqual(fake['marker'], 'synthetic-retained-workspace')
            self.assertEqual(fake['resumed'], index > 1)
            self.assertEqual(fake['prompt_sha256'], hashlib.sha256(self.prompts[index - 1]).hexdigest())
            self.assertEqual(record['archive']['business_binding_errors'], [])
            with zipfile.ZipFile(record['archive']['archive']) as archive:
                self.assertEqual(set(archive.namelist()), set(record['archive']['source_files_sha256']))
                for name, expected in record['archive']['source_files_sha256'].items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), expected)
        public = folder / 'episode/quality/public'
        manifest = json.loads((public / 'EPISODE.json').read_bytes())
        self.assertEqual(manifest['counts'], result['counts'])
        for index in (1, 2, 3):
            evidence = json.loads((public / ('turn_' + str(index)) / 'tool_evidence.json').read_bytes())
            self.assertEqual(len(evidence['owner_attempts']), 1)
            self.assertEqual(len(evidence['public_tool_events']), 2)
            payload = evidence['owner_attempts'][0]['responses'][0]['value']['result']['content'][0]['text']
            value = json.loads(payload)
            self.assertEqual(value['perf_ns'], 'semantic-data-kept')
            self.assertEqual(value['group'], group)
            self.assertEqual(value['pose'], int(index == 3))
            self.assertEqual((public / ('turn_' + str(index)) / 'answer.txt').read_bytes(),
                             ('SYNTHETIC final for turn ' + str(index)).encode())
        private = json.loads((folder / 'episode/quality/PRIVATE_BINDING.json').read_bytes())
        self.assertTrue(private['synthetic_fixture'])
        self.assertEqual(len(private['turn_bindings']), 3)

    def test_native_three_turn_loop_and_archives(self):
        self.verify_success('N')

    def test_compact_three_turn_loop_and_archives(self):
        self.verify_success('C')

    def verify_failed_second(self, scenario, group='N', turn_budget_ns=5 * 10**9):
        folder, result = self.exercise(group, scenario, turn_budget_ns)
        self.assertFalse(result['qualified_execution'])
        self.assertEqual(result['counts'], {'completed': 1, 'failed': 1, 'not_run': 1})
        self.assertEqual(self.owner.edits, 0)
        self.assertEqual(len(result['turns']), 2)
        self.assertFalse((folder / 'episode/turns/EDIT').exists())
        second = result['turns'][1]['consumer']
        self.assertEqual(second['status'], 'failed')
        self.assertEqual(second['expected_thread_id'], result['turns'][0]['consumer']['thread_id'])
        self.assertIsNone(second['summary']['usage_aggregation'])
        return folder, result, second

    def test_recovered_error_preserves_final_and_failure(self):
        folder, result, second = self.verify_failed_second('recovered_error')
        self.assertTrue(second['summary']['final_present'])
        self.assertTrue(any('SYNTHETIC reconnect' in json.dumps(row) for row in second['errors']))
        manifest = json.loads((folder / 'episode/quality/public/EPISODE.json').read_bytes())
        self.assertEqual(manifest['turns'][1]['execution_state'], 'failed')
        self.assertTrue(manifest['turns'][1]['final_present'])
        self.assertIn('SYNTHETIC reconnect', json.dumps(manifest['turns'][1]['errors']))

    def test_missing_final_keeps_slot_failed(self):
        _, _, second = self.verify_failed_second('missing_final', 'C')
        self.assertFalse(second['summary']['final_present'])

    def test_wrong_thread_never_falls_back_to_fresh_context(self):
        _, _, second = self.verify_failed_second('wrong_thread')
        self.assertTrue(any(row.get('type') == 'resume_thread_mismatch' for row in second['summary']['errors']))

    def test_original_deadline_stops_consumer_and_later_turn(self):
        _, _, second = self.verify_failed_second('timeout', turn_budget_ns=1500 * 10**6)
        self.assertTrue(second['deadline_timer_fired'])
        self.assertTrue(second['process_reaped'] and second['readers_stopped'])

    def test_nonzero_exit_after_final_remains_failed(self):
        _, _, second = self.verify_failed_second('nonzero_exit', 'C')
        self.assertEqual(second['exit_code'], 3)
        self.assertTrue(second['summary']['final_present'])

    def test_malformed_stream_originals_are_retained(self):
        folder, _, second = self.verify_failed_second('malformed')
        raw = folder / 'episode/turns/REPEAT/stdout_unparsed.bin'
        self.assertIn(b'SYNTHETIC non-JSON stdout', raw.read_bytes())
        self.assertEqual(second['status'], 'failed')

    def test_provider_disabled_path_never_launches_consumer(self):
        folder, result = self.exercise(provider_fixture=False)
        self.assertFalse(result['qualified_execution'])
        self.assertTrue(any(row['message'] == 'model_consumer_disabled_in_preparation' for row in result['errors']))
        self.assertEqual(self.owner.calls, 0)
        self.assertFalse((folder / 'work/SYNTHETIC_THREAD.json').exists())

    def test_archive_failure_keeps_completed_turns_and_failed_episode(self):
        with mock.patch.object(episode.pack, 'capture_cell', side_effect=RuntimeError('synthetic archive failure')):
            folder, result = self.exercise()
        self.assertFalse(result['qualified_execution'])
        self.assertEqual(result['counts'], {'completed': 3, 'failed': 0, 'not_run': 0})
        self.assertEqual(result['archive_status'], 'failed')
        self.assertTrue(any(row.get('stage') == 'quality_archive' for row in result['errors']))
        saved = json.loads((folder / 'episode/EPISODE_RESULT.json').read_bytes())
        timing = json.loads((folder / 'episode/FINAL_TIMING.json').read_bytes())
        self.assertFalse(saved['qualified_execution'])
        self.assertFalse(timing['qualified_execution'])
        self.assertEqual(saved['counts'], result['counts'])
        self.assertTrue((folder / 'episode/quality/ARCHIVE_FAILURE.json').exists())

    def test_archive_directory_failure_keeps_terminal_receipts(self):
        original = Path.mkdir
        def reject_quality(path, *args, **kwargs):
            if path.name == 'quality':
                raise OSError('synthetic quality directory failure')
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, 'mkdir', reject_quality):
            folder, result = self.exercise()
        self.assertFalse(result['qualified_execution'])
        self.assertEqual(result['counts'], {'completed': 3, 'failed': 0, 'not_run': 0})
        self.assertEqual(result['archive_status'], 'failed')
        self.assertIn('failure_receipt_error', result['errors'][0])
        self.assertTrue((folder / 'episode/EPISODE_RESULT.json').exists())
        self.assertFalse(json.loads((folder / 'episode/FINAL_TIMING.json').read_bytes())['qualified_execution'])


if __name__ == '__main__':
    began = time.perf_counter_ns()
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(EpisodeEndToEnd)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    text = stream.getvalue()
    print(text, end='')
    out = EpisodeEndToEnd.run_directory
    (out / 'TESTS.txt').write_text(text, encoding='utf8', newline='\n')
    (out / 'RESULT.json').write_text(json.dumps({'tests': result.testsRun, 'failures': len(result.failures),
        'errors': len(result.errors), 'passed': result.wasSuccessful(), 'wall_ns': time.perf_counter_ns() - began,
        'new_provider_model_Blender_calls': 0, 'scope': 'Actual consume loop/coordinator with synthetic CLI and local socket owner only'}, indent=2) + '\n', encoding='utf8', newline='\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
