"""Independent byte, failure and journal checks for bounded state buffering.

The expected byte contract is the previous compact Unicode atomic writer.
Tests use temporary files and read-only/mutable host doubles, never Blender.
"""
from __future__ import annotations

import copy
import errno
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin import agent_hooks
from human_eye_plugin import live_service
from human_eye_plugin.live_service import LiveSpatialService, RequestBudgetError
from verification.test_live_service import SelfLockingHost
from verification.test_request_wait_budget import Clock


def expected_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


class FileProxy:
    def __init__(self, handle, events, fail_write=False):
        self.handle, self.events, self.fail_write = handle, events, fail_write

    def __enter__(self):
        self.handle.__enter__()
        return self

    def __exit__(self, *args):
        return self.handle.__exit__(*args)

    def write(self, value):
        self.events.append(('write', len(value)))
        if self.fail_write:
            raise OSError(errno.EIO, 'simulated write failure')
        return self.handle.write(value)

    def flush(self):
        self.events.append(('flush', None))
        return self.handle.flush()

    def fileno(self):
        return self.handle.fileno()


class AtomicWriterBufferedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder/'state.json'

    def assert_no_temp(self):
        self.assertEqual(list(self.folder.glob('state.json.*.tmp')), [])

    def test_stream_and_buffered_bytes_match_previous_unicode_contract(self):
        cases = [
            {}, {'empty': [], 'value': None, 'false': False, 'zero': 0, 'negative_zero': -0.0},
            {'name': '蓝色零件👁', 'line': 'a\nb\r\t"\\', 'special': '\u2028\u2029'},
            {'finite': [1e308, -1e308, 1e-308, 1.2345678901234567], 'integer': 10**100},
            {1: 'integer key', None: 'null key', 2.5: 'float key'},
            {'items': [{'id': i, '中文': '纹理', 'points': [[i, i+.25, 0]]} for i in range(1000)]},
        ]
        for index, value in enumerate(cases):
            original = copy.deepcopy(value)
            outputs = []
            for buffered in (False, True):
                with self.subTest(case=index, buffered=buffered):
                    agent_hooks._atomic_write(self.path, value, _buffered=buffered)
                    outputs.append(self.path.read_bytes())
                    self.assertEqual(outputs[-1], expected_bytes(value))
                    self.assertEqual(value, original)
                    self.assert_no_temp()
            self.assertEqual(outputs[0], outputs[1])

    def test_default_hook_writer_keeps_streaming_path(self):
        original_dump = json.dump
        with patch('human_eye_plugin.agent_hooks.json.dump', wraps=original_dump) as streamed:
            with patch('human_eye_plugin.agent_hooks.json.dumps', side_effect=AssertionError('default must stream')):
                agent_hooks._atomic_write(self.path, {'_buffered': True, 'name': '默认'})
        self.assertEqual(streamed.call_count, 1)
        self.assertEqual(json.loads(self.path.read_bytes()), {'_buffered': True, 'name': '默认'})

    def test_buffered_path_uses_dumps_and_single_write(self):
        original_fdopen = agent_hooks.os.fdopen
        original_dumps = json.dumps
        events = []
        def fdopen(*args, **kwargs):
            return FileProxy(original_fdopen(*args, **kwargs), events)
        value = {'nested': list(range(100)), 'name': '眼睛👁'}
        with patch('human_eye_plugin.agent_hooks.os.fdopen', side_effect=fdopen):
            with patch('human_eye_plugin.agent_hooks.json.dumps', wraps=original_dumps) as encoded:
                with patch('human_eye_plugin.agent_hooks.json.dump', side_effect=AssertionError('buffer must not stream')):
                    agent_hooks._atomic_write(self.path, value, _buffered=True)
        self.assertEqual(encoded.call_count, 1)
        self.assertEqual([event for event in events if event[0]=='write'], [('write', len(expected_bytes(value).decode('utf-8')))])
        self.assertEqual(self.path.read_bytes(), expected_bytes(value))

    def test_both_modes_keep_write_flush_fsync_replace_order(self):
        original_fdopen = agent_hooks.os.fdopen
        original_fsync = agent_hooks.os.fsync
        original_replace = agent_hooks.os.replace
        for buffered in (False, True):
            events = []
            def fdopen(*args, **kwargs):
                return FileProxy(original_fdopen(*args, **kwargs), events)
            def fsync(fd):
                events.append(('fsync', None))
                return original_fsync(fd)
            def replace(*args):
                events.append(('replace', None))
                return original_replace(*args)
            with self.subTest(buffered=buffered), patch('human_eye_plugin.agent_hooks.os.fdopen', side_effect=fdopen):
                with patch('human_eye_plugin.agent_hooks.os.fsync', side_effect=fsync):
                    with patch('human_eye_plugin.agent_hooks.os.replace', side_effect=replace):
                        agent_hooks._atomic_write(self.path, {'list': list(range(30))}, _buffered=buffered)
            self.assertEqual([event[0] for event in events][-3:], ['flush', 'fsync', 'replace'])
            self.assertTrue(all(event[0]=='write' for event in events[:-3]))
            self.assert_no_temp()

    def test_nonfinite_values_never_replace_existing_destination(self):
        for buffered in (False, True):
            for value in (float('nan'), float('inf'), -float('inf')):
                with self.subTest(buffered=buffered, value=str(value)):
                    self.path.write_bytes(b'prior-state')
                    with self.assertRaises(ValueError):
                        agent_hooks._atomic_write(self.path, {'nested': [1, {'value': value}]}, _buffered=buffered)
                    self.assertEqual(self.path.read_bytes(), b'prior-state')
                    self.assert_no_temp()

    def test_cycle_and_unsupported_values_preserve_destination(self):
        cycle = {}; cycle['self'] = cycle
        for buffered in (False, True):
            for value, error in ((cycle, ValueError), ({'set': {1, 2}}, TypeError), ({'surrogate': '\ud800'}, UnicodeEncodeError)):
                with self.subTest(buffered=buffered, error=error.__name__):
                    self.path.write_bytes(b'prior-state')
                    with self.assertRaises(error):
                        agent_hooks._atomic_write(self.path, value, _buffered=buffered)
                    self.assertEqual(self.path.read_bytes(), b'prior-state')
                    self.assert_no_temp()

    def test_encode_failure_on_absent_destination_leaves_no_state(self):
        for buffered in (False, True):
            with self.subTest(buffered=buffered), self.assertRaises(TypeError):
                agent_hooks._atomic_write(self.path, {'bad': object()}, _buffered=buffered)
            self.assertFalse(self.path.exists())
            self.assert_no_temp()

    def test_write_failure_preserves_existing_destination_and_cleans_temp(self):
        original_fdopen = agent_hooks.os.fdopen
        for buffered in (False, True):
            self.path.write_bytes(b'prior-state')
            def fdopen(*args, **kwargs):
                return FileProxy(original_fdopen(*args, **kwargs), [], fail_write=True)
            with self.subTest(buffered=buffered), patch('human_eye_plugin.agent_hooks.os.fdopen', side_effect=fdopen):
                with self.assertRaises(OSError):
                    agent_hooks._atomic_write(self.path, {'valid': list(range(10))}, _buffered=buffered)
            self.assertEqual(self.path.read_bytes(), b'prior-state')
            self.assert_no_temp()

    def test_fsync_failure_does_not_replace_and_cleans_temp(self):
        for buffered in (False, True):
            self.path.write_bytes(b'prior-state')
            with self.subTest(buffered=buffered), patch('human_eye_plugin.agent_hooks.os.fsync', side_effect=OSError(errno.EIO, 'fsync failure')):
                with patch('human_eye_plugin.agent_hooks.os.replace') as replaced:
                    with self.assertRaises(OSError):
                        agent_hooks._atomic_write(self.path, {'value': '新'}, _buffered=buffered)
            replaced.assert_not_called()
            self.assertEqual(self.path.read_bytes(), b'prior-state')
            self.assert_no_temp()

    def test_replace_failure_keeps_destination_and_cleans_temp(self):
        for buffered in (False, True):
            self.path.write_bytes(b'prior-state')
            with self.subTest(buffered=buffered), patch('human_eye_plugin.agent_hooks.os.replace', side_effect=OSError(errno.EACCES, 'replace refused')):
                with self.assertRaises(OSError):
                    agent_hooks._atomic_write(self.path, {'valid': True}, _buffered=buffered)
            self.assertEqual(self.path.read_bytes(), b'prior-state')
            self.assert_no_temp()

    def test_new_parent_directory_and_unicode_path_are_supported(self):
        target = self.folder/'未创建'/'新状态.json'
        agent_hooks._atomic_write(target, {'名称': '部件👁'}, _buffered=True)
        self.assertEqual(target.read_bytes(), expected_bytes({'名称': '部件👁'}))
        self.assertEqual(list(target.parent.glob('*.tmp')), [])

    def test_buffered_mode_is_keyword_only(self):
        with self.assertRaises(TypeError):
            agent_hooks._atomic_write(self.path, {}, True)
        self.assertFalse(self.path.exists())


class StateServiceBufferedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.state = self.folder/'state.json'
        self.config = self.folder/'live.json'
        self.config.write_text(json.dumps({
            'schema_version': '1.0', 'project_root': str(Path(agent_hooks.__file__).resolve().parents[1]),
            'state_file': str(self.state), 'audit_file': str(self.folder/'events.jsonl'),
            'quad_size': 64, 'max_sessions': 4, 'request_budget_s': 1., 'enabled': True,
        }), encoding='utf-8')
        self.host = SelfLockingHost()
        self.service = LiveSpatialService(self.config, host=self.host)
        self.action = {'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .05]}

    def observe(self):
        return self.service.observe('s', focal_id='part', reference_id='base', include_image=False)

    def save_fixture(self, payload):
        exported = {'schema_version': '1.0', 'blob': payload}
        runtime = SimpleNamespace(router=SimpleNamespace(scene_cache=object()),
            export_state=lambda: copy.deepcopy(exported))
        value = {'schema_version': '1.0', 'config_fingerprint': self.service.config_fingerprint,
                 'runtime': None, 'inflight': None}
        expected = copy.deepcopy(value); expected['runtime'] = copy.deepcopy(exported)
        original = live_service._atomic_write
        with patch('human_eye_plugin.live_service._atomic_write', wraps=original) as writer:
            self.service._save(value, runtime)
        self.assertEqual(writer.call_count, 1)
        self.assertEqual(self.state.read_bytes(), expected_bytes(expected))
        self.assertEqual(value, expected)
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(self.host.captures, 0)
        return expected, writer.call_args.kwargs

    def test_small_real_service_state_opts_in_without_changing_bytes(self):
        original = live_service._atomic_write
        with patch('human_eye_plugin.live_service._atomic_write', wraps=original) as writer:
            result = self.observe()
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(writer.call_count, 1)
        self.assertIs(writer.call_args.kwargs['_buffered'], True)
        loaded = json.loads(self.state.read_bytes())
        self.assertEqual(self.state.read_bytes(), expected_bytes(loaded))
        self.assertIsNone(loaded['inflight'])
        self.assertEqual(self.host.calls, 0)

    def test_512kib_ascii_size_boundary_is_inclusive_and_plus_one_streams(self):
        empty = {'schema_version': '1.0', 'config_fingerprint': self.service.config_fingerprint,
                 'runtime': {'schema_version': '1.0', 'blob': ''}, 'inflight': None}
        overhead = len(json.dumps(empty, ensure_ascii=True, allow_nan=False))
        for offset, expected_mode in ((-1, True), (0, True), (1, False)):
            with self.subTest(offset=offset):
                value, kwargs = self.save_fixture('x'*(512*1024-overhead+offset))
                self.assertEqual(len(json.dumps(value, ensure_ascii=True, allow_nan=False)), 512*1024+offset)
                self.assertIs(kwargs['_buffered'], expected_mode)

    def test_large_unicode_uses_ascii_size_gate_even_when_utf8_is_smaller(self):
        value, kwargs = self.save_fixture('👁'*50000)
        self.assertGreater(len(json.dumps(value, ensure_ascii=True, allow_nan=False)), 512*1024)
        self.assertLess(len(expected_bytes(value)), 512*1024)
        self.assertIs(kwargs['_buffered'], False)

    def test_large_ascii_with_one_astral_character_keeps_streaming(self):
        value, kwargs = self.save_fixture('x'*(600*1024)+'👁')
        self.assertGreater(len(json.dumps(value, ensure_ascii=True, allow_nan=False)), 512*1024)
        self.assertIs(kwargs['_buffered'], False)

    def test_original_32mib_limit_refuses_before_atomic_writer(self):
        self.state.write_bytes(b'prior-state')
        runtime = SimpleNamespace(router=SimpleNamespace(scene_cache=object()),
            export_state=lambda: {'schema_version': '1.0', 'blob': 'x'*(32*1024*1024)})
        with patch('human_eye_plugin.live_service._atomic_write') as writer:
            with self.assertRaisesRegex(ValueError, '32 MiB'):
                self.service._save({'inflight': None}, runtime)
        writer.assert_not_called()
        self.assertEqual(self.state.read_bytes(), b'prior-state')
        self.assertEqual(self.host.calls, 0)

    def test_initial_journal_fault_seam_prevents_mutation(self):
        with patch('human_eye_plugin.live_service._atomic_write', side_effect=OSError(errno.EIO, 'journal fault')) as writer:
            with self.assertRaises(OSError):
                self.service.transform('s', self.action)
        self.assertEqual(writer.call_count, 1)
        self.assertIs(writer.call_args.kwargs['_buffered'], True)
        self.assertEqual(self.host.calls, 0)
        self.assertFalse(self.state.exists())

    def test_final_journal_fault_keeps_durable_inflight_and_blocks_new_instance(self):
        original = live_service._atomic_write
        writes = []
        def fail_final(path, data, **kwargs):
            writes.append(copy.deepcopy(data))
            if len(writes)==2:
                raise OSError(errno.EIO, 'final commit fault')
            return original(path, data, **kwargs)
        with patch('human_eye_plugin.live_service._atomic_write', side_effect=fail_final):
            with self.assertRaises(OSError):
                self.service.transform('s', self.action)
        self.assertEqual(self.host.calls, 1)
        self.assertIsNotNone(json.loads(self.state.read_bytes())['inflight'])
        other = LiveSpatialService(self.config, host=self.host)
        self.assertEqual(other.transform('other', self.action)['status'], 'host_quarantined')
        self.assertEqual(self.host.calls, 1)

    def test_encoding_budget_overrun_still_stops_before_writer_or_mutation(self):
        clock = Clock(); original = json.dumps
        def slow_encode(value, *args, **kwargs):
            encoded = original(value, *args, **kwargs)
            if isinstance(value, dict) and value.get('inflight') is not None and 'config_fingerprint' in value:
                clock.expire()
            return encoded
        with patch('human_eye_plugin.live_service.time', clock):
            with patch('human_eye_plugin.live_service.json.dumps', side_effect=slow_encode):
                with patch('human_eye_plugin.live_service._atomic_write') as writer:
                    with self.assertRaises(RequestBudgetError) as caught:
                        self.service.transform('s', self.action)
        self.assertEqual(caught.exception.to_error_fields()['budget_stage'], 'before_atomic_state_write')
        writer.assert_not_called()
        self.assertEqual(self.host.calls, 0)
        self.assertFalse(self.state.exists())


if __name__=='__main__':
    unittest.main()
