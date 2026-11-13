"""Local-process regression tests for the real per-turn event/cleanup loop."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import zipfile


spec = importlib.util.spec_from_file_location('_fix1_test_consumer', Path(__file__).with_name('consumer_transport.py'))
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
THREAD = '4ec74e40-c9cc-4297-a1c6-787cf04a7be6'
FAKE = '''import json, pathlib, sys, time
args=sys.argv[1:]
prompt=sys.stdin.buffer.read().decode('utf8')
thread='4ec74e40-c9cc-4297-a1c6-787cf04a7be6'
def event(value):
    print(json.dumps(value),flush=True)
if prompt=='malformed':
    print('retained non-JSON stdout',flush=True)
    sys.exit(0)
event({'type':'thread.started','thread_id':thread})
if prompt=='sleep':
    time.sleep(2)
if prompt=='error':
    event({'type':'error','message':'synthetic reconnect failure'})
pathlib.Path('persistent_marker.txt').write_text(thread)
text='synthetic '+prompt
pathlib.Path(args[args.index('-o')+1]).write_text(text,encoding='utf8')
event({'type':'item.completed','item':{'id':'final','type':'agent_message','text':text}})
event({'type':'turn.completed','usage':{'input_tokens':5,'cached_input_tokens':2,'output_tokens':3,'extra_provider_field':17}})
'''


class ConsumerLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.fake = self.folder / 'fake_cli.py'
        self.fake.write_text(FAKE, encoding='utf8')
        self.endpoint = self.folder / 'ENDPOINT.json'
        self.episode_deadline = time.perf_counter_ns() + 30 * 10**9
        self.endpoint.write_text(json.dumps({'chain_deadline_ns': self.episode_deadline}))
        self.cell = {'group': 'N', 'endpoint': str(self.endpoint), 'audit_dir': str(self.folder / 'owner')}
        self.plan = {'image_count': 0, 'new_images': 0, 'inputs': {}, 'model_consumer_enabled': False}
        self.local = {'command': [sys.executable, '-I', '-B', '-X', 'utf8', str(self.fake)],
                      'script_sha256': hashlib.sha256(self.fake.read_bytes()).hexdigest()}

    def tearDown(self):
        self.temp.cleanup()

    def run_turn(self, index=1, prompt=b'normal', deadline=None):
        return transport.consume_turn(episode_id='local-test', turn_index=index,
            folder=self.folder / ('turn_' + str(index)), work=self.folder / 'shared',
            cell=self.cell, install={'python': sys.executable}, plan=self.plan, prompt=prompt,
            episode_deadline_ns=self.episode_deadline,
            turn_deadline_ns=deadline or self.episode_deadline,
            expected_thread_id=None if index == 1 else THREAD, local_cli=self.local)

    def test_actual_loop_persist_resume_and_raw_usage(self):
        first = self.run_turn()
        second = self.run_turn(2, b'repeat')
        self.assertTrue(first['valid_completion'])
        self.assertTrue(second['valid_completion'])
        self.assertNotIn('--ephemeral', first['frozen_cli_argv'])
        self.assertIn('resume', second['frozen_cli_argv'])
        self.assertEqual(second['frozen_cli_argv'][-2], THREAD)
        self.assertEqual(first['shared_work'], second['shared_work'])
        self.assertEqual(first['endpoint'], second['endpoint'])
        self.assertEqual(first['deadline_ns'], second['deadline_ns'])
        self.assertEqual(second['raw_usage_events'][0]['extra_provider_field'], 17)
        self.assertIsNone(second['usage_aggregation'])
        self.assertEqual((self.folder / 'shared/persistent_marker.txt').read_text(), THREAD)
        self.assertEqual(second['execution_kind'], 'synthetic_local_process')
        self.assertTrue(second['process_reaped'])
        self.assertTrue(second['readers_stopped'])
        with zipfile.ZipFile(second['archive']['archive']) as bundle:
            self.assertEqual(bundle.read('PUBLIC_FINAL.txt'), b'synthetic repeat')
            self.assertIn('events.jsonl', bundle.namelist())
            self.assertIn('BUSINESS_SOURCE_BINDING.json', bundle.namelist())
        self.assertTrue(second['final_timing']['accepted_success'])

    def test_error_with_final_remains_failed(self):
        value = self.run_turn(prompt=b'error')
        self.assertFalse(value['valid_completion'])
        self.assertTrue(value['summary']['final_present'])
        self.assertEqual(value['summary']['execution_state'], 'failed')
        self.assertEqual(value['raw_usage_events'][0]['input_tokens'], 5)
        self.assertTrue(Path(value['archive']['archive']).exists())

    def test_malformed_stdout_is_retained_and_closed(self):
        value = self.run_turn(prompt=b'malformed')
        self.assertFalse(value['valid_completion'])
        self.assertTrue(value['process_reaped'])
        self.assertEqual((self.folder / 'turn_1/stdout_unparsed.bin').read_bytes(), b'retained non-JSON stdout' + os.linesep.encode())
        self.assertTrue(value['readers_stopped'])

    def test_deadline_includes_cleanup(self):
        deadline = time.perf_counter_ns() + 200_000_000
        value = self.run_turn(prompt=b'sleep', deadline=deadline)
        self.assertFalse(value['valid_completion'])
        self.assertEqual(value['deadline_ns'], deadline)
        self.assertFalse(value['final_timing']['accepted_success'])
        self.assertTrue(value['process_reaped'])

    def test_reader_start_failure_reaps_process(self):
        class BadReader(threading.Thread):
            def start(self):
                if getattr(self._target, '__name__', None) == 'reader':
                    raise RuntimeError('synthetic reader startup failure')
                return super().start()
        with mock.patch.object(transport.threading, 'Thread', BadReader):
            value = self.run_turn()
        self.assertFalse(value['valid_completion'])
        self.assertTrue(value['process_reaped'])
        self.assertTrue(value['readers_stopped'])

    def test_late_consumer_publication_is_failed_on_disk(self):
        original_save = transport.save
        delayed = False
        def slow_save(path, value):
            nonlocal delayed
            if Path(path).name == 'CONSUMER.json' and not delayed:
                delayed = True
                time.sleep(.6)
            return original_save(path, value)
        with mock.patch.object(transport, 'save', slow_save):
            value = self.run_turn(deadline=time.perf_counter_ns() + 500_000_000)
        self.assertFalse(value['valid_completion'])
        self.assertFalse(value['final_timing']['accepted_success'])
        self.assertFalse(json.loads((self.folder / 'turn_1/CONSUMER.json').read_bytes())['valid_completion'])

    def test_provider_disabled_before_launch(self):
        with self.assertRaisesRegex(ValueError, 'model_consumer_disabled'):
            transport.consume_turn(episode_id='local-test', turn_index=1,
                folder=self.folder / 'denied', work=self.folder / 'work', cell=self.cell,
                install={'python': sys.executable}, plan=self.plan, prompt=b'normal',
                episode_deadline_ns=self.episode_deadline, turn_deadline_ns=self.episode_deadline)
        self.assertFalse((self.folder / 'denied').exists())

    def test_invalid_deadlines_never_launch(self):
        with self.assertRaisesRegex(ValueError, 'original_absolute'):
            self.run_turn(deadline=self.episode_deadline + 1)

    def test_owner_archive_mismatch_is_retained(self):
        owner = self.folder / 'owner'
        original = owner / 'tool_01'
        original.mkdir(parents=True)
        (owner / 'TOOLS.json').write_text(json.dumps({'tools': [{'attempt': 1}]}))
        (original / 'REQUEST.json').write_text(json.dumps({'params': {'name': 'execute_blender_code', 'arguments': {'code': 'print(1)'}}}))
        (original / 'RESPONSE.json').write_text(json.dumps({'result': {'content': []}}))
        out = self.folder / 'archive_input'
        out.mkdir()
        result = transport.archive_turn(out, self.cell, 1, [])
        self.assertTrue(result['business_binding_errors'])
        self.assertEqual(result['owner_attempts'], [1])
        with zipfile.ZipFile(result['archive']) as bundle:
            self.assertIn('owner_turn/tool_01/REQUEST.json', bundle.namelist())


if __name__ == '__main__':
    unittest.main()
