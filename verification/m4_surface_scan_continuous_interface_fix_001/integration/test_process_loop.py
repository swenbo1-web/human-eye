"""Targeted zero-provider replays through the real local process/reader loop."""

import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import time
import unittest
from unittest import mock
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIX1 = ROOT / 'verification/m4_surface_scan_continuity_001_fix1'
ERROR_SOURCE = ROOT / 'verification/m4_surface_scan_consumption_001/cells/P1/owner/tool_03/RESPONSE.json'
ERROR_SHA = 'ed7236af2a3ef5080b2de78eb30a746f0d8652efc2fd8c339c4a6a08bfe13ef1'
SOURCE_PATHS = [HERE / 'fake_cli.py', HERE / 'same_representation_cli.py', Path(__file__),
                HERE.parent / 'runtime/consumer_transport.py', HERE.parent / 'runtime/episode.py',
                HERE.parent / 'compatibility.py', FIX1 / 'consumer/fake_cli.py', FIX1 / 'consumer/fake_owner.py',
                FIX1 / 'consumer/test_episode_e2e.py', FIX1 / 'runtime/consumer_transport.py',
                FIX1 / 'consumer/episode.py', ERROR_SOURCE]
SOURCE_BEFORE = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in SOURCE_PATHS}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


episode = load('_interface_integration_episode', HERE.parent / 'runtime/episode.py')
reused = load('_interface_existing_loop_assertions', FIX1 / 'consumer/test_episode_e2e.py')


def extended(path):
    """Keep all test artifacts in this batch, including deep Windows archives."""
    if os.name != 'nt' or str(path).startswith('\\\\?\\'):
        return path
    return Path('\\\\?\\' + str(path.resolve()))


def archive_run(output):
    """Seal a closed attempt beside its retained raw directory."""
    output = extended(output)
    archive = output.parent / (output.name + '.zip')
    sources = episode.transport.packer.capture_cell(output, archive)
    manifest = {'raw_directory': str(output), 'archive': str(archive),
                'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                'members': {name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                            for name, raw in sources.items()},
                'scope': 'Complete closed local-process replay originals; raw directory retained'}
    reused.owner_module.FakeOwner.save(output.parent / (output.name + '_MANIFEST.json'), manifest)
    (output.parent / (output.name + '_RESULT.json')).write_bytes((output / 'RESULT.json').read_bytes())
    return manifest


class RecordedErrorOwner(reused.owner_module.FakeOwner):
    """Replay a recorded error result on the second local fixture request."""

    def handle(self, message):
        response = super().handle(message)
        if message['method'] == 'tools/call' and self.calls == 2:
            raw = ERROR_SOURCE.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == ERROR_SHA
            result = copy.deepcopy(json.loads(raw)['result'])
            assert result['isError'] is True
            response = {**response, 'result': result}
            folder = self.folder / 'tool_02'
            self.save(folder / 'RESPONSE.json', response)
            self.save(folder / 'ATTEMPT.json', {'attempt': 2, 'is_error': True, 'exception': None})
            self.save(folder / 'RECORDED_ERROR_SOURCE.json', {'source': str(ERROR_SOURCE),
                      'sha256': ERROR_SHA, 'result_replayed_exactly': True,
                      'scope': 'Recorded result in a synthetic request/response envelope'})
        return response


class InterfaceLoop(unittest.TestCase):
    verify_success = reused.EpisodeEndToEnd.verify_success
    verify_failed_second = reused.EpisodeEndToEnd.verify_failed_second

    @classmethod
    def setUpClass(cls):
        parent = HERE / 'offline'
        parent.mkdir(exist_ok=True)
        existing = [int(path.name[1:]) for path in parent.glob('a*')
                    if path.is_dir() and path.name[1:].isdigit()]
        index = max(existing, default=0) + 1
        cls.run_directory = parent / ('a' + str(index).zfill(2))
        cls.run_directory.mkdir(exist_ok=False)
        with zipfile.ZipFile(extended(cls.run_directory / 'SOURCES.zip'), 'x', compression=zipfile.ZIP_DEFLATED) as sources:
            for path in SOURCE_PATHS:
                raw = path.read_bytes()
                assert hashlib.sha256(raw).hexdigest() == SOURCE_BEFORE[str(path)], 'source_changed_before_replay'
                sources.writestr(path.relative_to(ROOT).as_posix(), raw)
        ready = json.loads((ROOT / 'verification/m4_surface_scan_continuity_001/inputs/C_READY.json').read_bytes())
        cls.python = ready['dependency_python']
        cls.prompt = (ROOT / 'verification/m4_surface_scan_continuity_001/inputs/PROMPT_T1.txt').read_bytes()
        recheck = '请重新检查当前场景。'.encode('utf8') + cls.prompt
        cls.prompts = [cls.prompt, recheck, recheck]
        cls.records = []

    def setUp(self):
        self.owner = None

    def tearDown(self):
        if self.owner is not None and self.owner.finish_calls == 0:
            self.owner.finish()

    def exercise(self, group='N', scenario='normal', turn_budget_ns=5 * 10**9,
                 provider_fixture=True):
        assert provider_fixture, 'this_replay_has_no_provider_path'
        case_name = hashlib.sha256(self._testMethodName.encode('utf8')).hexdigest()[:6]
        ordinary_folder = self.run_directory / case_name
        folder = extended(ordinary_folder)
        folder.mkdir()
        reused.owner_module.FakeOwner.save(folder / 'CASE.json', {'test': self._testMethodName,
                                            'synthetic': True, 'scenario': scenario})
        deadline = time.perf_counter_ns() + 25 * 10**9
        episode_id = 'synthetic-interface-' + case_name
        owner_type = reused.owner_module.FakeOwner if scenario == 'normal' else RecordedErrorOwner
        self.owner = owner_type(folder / 'owner', episode_id, group, deadline, scenario)
        fake = HERE / ('same_representation_cli.py' if scenario == 'same_representation_error' else 'fake_cli.py')
        local_cli = {'command': [self.python, '-I', '-B', '-X', 'utf8', str(fake)],
                     'script_sha256': hashlib.sha256(fake.read_bytes()).hexdigest()}
        compare = episode.transport.compatibility.successful_result_matches
        with mock.patch.object(episode.transport.compatibility, 'successful_result_matches', wraps=compare) as observed:
            result = episode.run_episode(episode_id=episode_id, output=folder / 'episode',
                work=ordinary_folder / 'work',
                cell={'group': 'N' if group == 'N' else 'P', 'endpoint': str(self.owner.endpoint),
                      'audit_dir': str(self.owner.folder)}, install={'python': self.python},
                plan={'image_count': 0, 'new_images': 0, 'inputs': {}, 'model_consumer_enabled': False},
                prompts=self.prompts, episode_deadline_ns=deadline, turn_budget_ns=turn_budget_ns,
                control=self.owner.control, finish=self.owner.finish,
                anonymous_episode_id='anonymous-synthetic-interface', local_cli=local_cli)
            comparison_calls = observed.call_count
        self.assertEqual(self.owner.finish_calls, 1)
        self.assertTrue(result['owner_finish']['confirmed'])
        self.assertIsNone(result['usage_aggregation'])
        self.assertTrue(all(event['finish_calls'] == 0 for event in self.owner.events))
        self.assertIs(episode.transport.consume_turn.__globals__['archive_turn'], episode.transport.archive_turn)
        self.assertIs(episode.run_episode.__globals__['transport'], episode.transport)
        for row in result['turns']:
            record = row['consumer']
            self.assertEqual(record['execution_kind'], 'synthetic_local_process')
            self.assertTrue(record['process_reaped'] and record['readers_stopped'])
            self.assertTrue(record['bridge_cleanup']['confirmed'])
            self.assertTrue(record['safe_to_continue'])
            self.assertFalse(record['mutation_unknown'])
            self.assertIsNone(record['summary']['usage_aggregation'])
        self.records.append({'case': self._testMethodName, 'scenario': scenario, 'folder': str(folder),
                             'counts': result['counts'], 'qualified_execution': result['qualified_execution'],
                             'comparison_calls': comparison_calls, 'finish_calls': self.owner.finish_calls,
                             'registered_edits': self.owner.edits, 'new_provider_model_Blender_product_calls': 0,
                             'scope': 'Local CLI/stdio processes and socket fixture; no actual model resume'})
        self.comparison_calls = comparison_calls
        return folder, result

    def assert_recorded_success_shapes(self, folder, result):
        self.assertEqual(self.comparison_calls, 3)
        for row in result['turns']:
            number = row['turn_index']
            response = json.loads((folder / 'owner' / ('tool_' + str(number).zfill(2)) / 'RESPONSE.json').read_bytes())
            item = row['consumer']['tool_calls'][0]['item']
            self.assertIs(response['result']['isError'], False)
            self.assertEqual(set(item['result']), {'content', 'structured_content'})
            self.assertIsNone(item['result']['structured_content'])
            self.assertEqual(item['status'], 'completed')
            self.assertIsNone(item['error'])
            self.assertEqual(response['result']['content'], item['result']['content'])
            self.assertNotEqual(episode.transport.packer.encoded(response['result']),
                                episode.transport.packer.encoded(item['result']))
            self.assertEqual(row['consumer']['archive']['business_binding_errors'], [])

    def test_native_recorded_shape_three_turns(self):
        self.verify_success('N')
        # verify_success executes the existing process/readers/archive assertions.
        record = self.records[-1]
        result = json.loads((Path(record['folder']) / 'episode/EPISODE_RESULT.json').read_bytes())
        self.assert_recorded_success_shapes(Path(record['folder']), result)

    def test_compact_recorded_shape_three_turns(self):
        self.verify_success('C')
        record = self.records[-1]
        result = json.loads((Path(record['folder']) / 'episode/EPISODE_RESULT.json').read_bytes())
        self.assert_recorded_success_shapes(Path(record['folder']), result)

    def test_recorded_cross_representation_error_keeps_failure(self):
        folder, result, second = self.verify_failed_second('recorded_error')
        self.assertEqual(self.comparison_calls, 2)
        response = json.loads((folder / 'owner/tool_02/RESPONSE.json').read_bytes())
        original = json.loads(ERROR_SOURCE.read_bytes())
        self.assertEqual(response['result'], original['result'])
        item = second['tool_calls'][0]['item']
        self.assertEqual(item['status'], 'failed')
        self.assertIsNone(item['error'])
        self.assertEqual(response['result']['content'], item['result']['content'])
        self.assertFalse(episode.transport.compatibility.successful_result_matches(response, item))
        self.assertTrue(second['summary']['final_present'])
        self.assertTrue(any(error.get('stage') == 'business_original_binding' for error in second['errors']))
        self.assertEqual(second['archive']['business_binding_errors'],
                         [{'attempt': 2, 'reason': 'CLI_result_differs_from_owner'}])
        self.assertFalse(result['qualified_execution'])

    def test_identical_error_binding_keeps_original_policy(self):
        folder, result = self.exercise(scenario='same_representation_error')
        self.assertEqual(self.comparison_calls, 2)
        self.assertTrue(result['qualified_execution'], result['errors'])
        self.assertEqual(result['counts'], {'completed': 3, 'failed': 0, 'not_run': 0})
        second = result['turns'][1]['consumer']
        response = json.loads((folder / 'owner/tool_02/RESPONSE.json').read_bytes())
        item = second['tool_calls'][0]['item']
        self.assertIs(response['result']['isError'], True)
        self.assertEqual(item['status'], 'failed')
        self.assertIsNone(item['error'])
        self.assertEqual(response['result'], item['result'])
        self.assertFalse(episode.transport.compatibility.successful_result_matches(response, item))
        self.assertEqual(second['archive']['business_binding_errors'], [])
        self.assertEqual(len(result['turns']), 3)


if __name__ == '__main__':
    started = time.perf_counter_ns()
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(InterfaceLoop))
    text = stream.getvalue()
    print(text, end='')
    output = extended(InterfaceLoop.run_directory)
    (output / 'TESTS.txt').write_text(text, encoding='utf8', newline='\n')
    source_after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in SOURCE_PATHS}
    report = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'passed': result.wasSuccessful() and SOURCE_BEFORE == source_after,
              'wall_ns': time.perf_counter_ns() - started,
              'new_provider_model_Blender_product_calls': 0, 'cases': InterfaceLoop.records,
              'source_sha256_before': SOURCE_BEFORE, 'source_sha256_after': source_after,
              'sources_unchanged_during_replay': SOURCE_BEFORE == source_after,
              'scope': 'Targeted local-process interface replay. Original formal states unchanged; actual model resume unmeasured.'}
    reused.owner_module.FakeOwner.save(output / 'RESULT.json', report)
    archive_run(output)
    raise SystemExit(0 if report['passed'] else 1)
