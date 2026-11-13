"""Run the actual FIX2 coordinator against a small, phase-gated reference fixture.

No process, Blender instance or provider is started. Historical geometry and WIRE
are referenced by hash and read in place, while coordinator writes stay in memory.
"""

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import time
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
OLD = ROOT / 'verification/m4_surface_scan_compact_facts_001/engineering/run_01'
FIX1 = ROOT / 'verification/m4_surface_scan_continuity_001_fix1'
PYTHON = 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe'
INPUTS = {}
CASES = []
OUTPUT = None


def raw_input(path):
    data = path.read_bytes()
    INPUTS[path.relative_to(ROOT).as_posix()] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data


def read_input(path):
    return json.loads(raw_input(path))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def projection(value):
    return {'unit_scale_m': value['unit_scale_m'], 'objects': [
        {key: copy.deepcopy(row[key]) for key in ('name', 'vertices_local', 'faces', 'matrix_world')}
        for row in value['objects']]}


class ReferenceEpisode:
    def __init__(self, output, mode):
        self.runner = load('_fix2_stage_runner_' + mode, BATCH / 'engineering/run_candidate.py')
        self.qualification = load('_fix2_stage_qualification_' + mode, FIX1 / 'qualification/verify_continuity.py')
        old_driver = load('_fix2_stage_driver_' + mode, ROOT / 'verification/m4_surface_scan_compact_consumption_001/runtime/driver.py')
        self.driver = types.SimpleNamespace(snapshot_binding=old_driver.snapshot_binding, finish=self.finish)
        fixture = read_input(OLD / 'RESULTS.json')
        selected = ('base_default', 'base_brief', 'edit_default')
        self.fixtures = [copy.deepcopy(next(row for row in fixture['business'] if row['state'] == label)) for label in selected]
        self.initial = projection(read_input(OLD / 'base_ACTUAL_SNAPSHOT.json'))
        self.edited = projection(read_input(OLD / 'edit_ACTUAL_SNAPSHOT.json'))
        self.ready = read_input(FIX1 / 'inputs/C_READY.json')
        self.base_schemas = read_input(FIX1 / 'inputs/C_PUBLIC_TOOLS.json')
        self.output = output
        self.folder = output / 'episodes/C'
        self.native = self.folder / 'owner/native'
        self.mode = mode
        self.memory = {}
        self.events = []
        self.finish_calls = 0
        self.edit_calls = 0
        self.finished = False
        self.process = None
        self.active = None
        self.completed = []
        self.calls = 0
        self.now = self.fixtures[0]['started_ns'] - 100_000_000
        self.start = None
        self.episode = None
        self.deadline = None
        self.windows = []
        self.wire_reads = []
        self.saved_read_bytes = Path.read_bytes
        self.saved_open = Path.open
        self.saved_exists = Path.exists
        self.saved_is_file = Path.is_file

    def clock(self):
        self.now += 1
        return self.now

    def save(self, path, value):
        if self.mode == 'publication_failure' and Path(path).name == 'TIMING_PUBLICATION.json':
            self.events.append('publication_failure')
            raise OSError('injected_timing_receipt_publication_failure')
        self.memory[Path(path)] = copy.deepcopy(value)

    def read(self, path):
        path = Path(path)
        if path in self.memory:
            return copy.deepcopy(self.memory[path])
        if path == self.output / 'inputs/C_READY.json':
            return copy.deepcopy(self.ready)
        if path == self.output / 'inputs/C_PUBLIC_TOOLS.json':
            return copy.deepcopy(self.base_schemas)
        return json.loads(self.read_bytes(path))

    def translate(self, path):
        path = Path(path)
        if path == self.folder / 'owner/audit.jsonl':
            return OLD / 'audit.jsonl'
        if path == self.native / 'WORKER_EVENTS.jsonl':
            return OLD / 'native/WORKER_EVENTS.jsonl'
        try:
            relative = path.relative_to(self.native / 'WIRE')
        except ValueError:
            return path
        self.wire_reads.append({'path': relative.as_posix(), 'after_finish': self.finished})
        if not self.finished or self.mode == 'missing_wire':
            raise FileNotFoundError(2, 'phase fixture WIRE is unavailable', str(path))
        return OLD / 'native/WIRE' / relative

    def read_bytes(self, path):
        path = Path(path)
        if path in self.memory:
            return (json.dumps(self.memory[path], ensure_ascii=False, allow_nan=False) + '\n').encode('utf8')
        mapped = self.translate(path)
        data = self.saved_read_bytes(mapped)
        if mapped.is_relative_to(ROOT) and not mapped.is_relative_to(self.output):
            INPUTS[mapped.relative_to(ROOT).as_posix()] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        return data

    def open(self, path, mode='r', *args, **kwargs):
        path = Path(path)
        if path in self.memory and 'r' in mode:
            raw = self.read_bytes(path)
            return io.BytesIO(raw) if 'b' in mode else io.StringIO(raw.decode('utf8'))
        return self.saved_open(self.translate(path), mode, *args, **kwargs)

    def exists(self, path):
        path = Path(path)
        if path in self.memory:
            return True
        try:
            mapped = self.translate(path)
        except FileNotFoundError:
            return False
        return self.saved_exists(mapped)

    def is_file(self, path):
        path = Path(path)
        if path in self.memory:
            return True
        try:
            mapped = self.translate(path)
        except FileNotFoundError:
            return False
        return self.saved_is_file(mapped)

    def popen(self, command, **kwargs):
        config = self.memory[self.folder / 'ACTOR_CONFIG.json']
        self.episode = config['episode_id']
        self.deadline = config['worker_deadline_ns']
        self.start = self.deadline - 590 * 10**9
        self.memory[self.folder / 'ENDPOINT.json'] = {'host': '127.0.0.1', 'port': 1234, 'actor_pid': 101,
                                                     'chain_deadline_ns': self.deadline}
        self.memory[self.folder / 'owner/INITIAL.json'] = copy.deepcopy(self.initial)
        self.process = types.SimpleNamespace(pid=101, returncode=None, stdin=io.BytesIO())
        self.process.poll = lambda: self.process.returncode
        return self.process

    def status(self):
        return {'episode_id': self.episode, 'owner_pid': 101, 'native_pid': 102,
                'native_host': '127.0.0.1', 'native_port': 103, 'native_workspace': str(self.native),
                'product_launcher_pid': 104, 'product_runtime_proof': {'confirmed': True, 'runtime_pid': 105},
                'session_id': self.episode, 'worker_deadline_ns': self.deadline,
                'active_turn': copy.deepcopy(self.active), 'completed_turns': copy.deepcopy(self.completed),
                'business_attempts': self.calls, 'edit_verified': self.edit_calls == 1,
                'edit_attempted': self.edit_calls == 1, 'owner_close_called': self.finished}

    def attach(self, endpoint, kind, message):
        operation = message['method'].removeprefix('continuity/')
        params = message['params']
        if operation == 'begin_turn':
            index = len(self.completed)
            self.now = self.fixtures[index]['started_ns'] - 100
            self.active = {'turn_id': params['turn_id'], 'started_ns': self.now,
                           'deadline_ns': params['deadline_ns'], 'first_business_attempt': self.calls + 1}
            self.events.append('begin_' + params['turn_id'])
        elif operation == 'end_turn':
            current = {**self.active, 'last_business_attempt': self.calls, 'business_attempts': 1}
            self.completed.append(current)
            self.active = None
            self.events.append('end_' + params['turn_id'])
        elif operation == 'qa_advance':
            assert len(self.completed) == 2 and self.active is None and self.edit_calls == 0
            self.edit_calls += 1
            self.events.append('registered_EDIT')
            self.memory[self.folder / 'owner/EDIT.json'] = copy.deepcopy(self.edited)
            return {'jsonrpc': '2.0', 'id': message['id'], 'result': {
                'snapshot': copy.deepcopy(self.edited), 'advance': {'synthetic_reference_fixture': True}, 'status': self.status()}}
        elif operation != 'status':
            raise AssertionError('unexpected_control_' + operation)
        return {'jsonrpc': '2.0', 'id': message['id'], 'result': self.status()}

    def thin_turn(self, **kwargs):
        index = self.calls
        fixture = self.fixtures[index]
        original_start = self.now
        self.calls += 1
        request = kwargs['requests'][-1]
        answer = copy.deepcopy(fixture['response'])
        answer['id'] = request['id']
        self.events.append('collect_' + self.active['turn_id'])
        self.now = fixture['ended_ns']
        if self.mode == 'event_overrun' and index == 1:
            event = fixture['work_events'][0]
            self.now = event['started_ns'] + event['elapsed_ns'] - 10
        self.windows.append((original_start, self.now + 1))
        return {'confirmed': True, 'responses': [answer], 'exit_code': 0, 'pid': 201 + index,
                'bridge_cleanup': {'confirmed': True}, 'started_ns': fixture['started_ns'], 'ended_ns': self.now,
                'wall_ns': fixture['ended_ns'] - fixture['started_ns'], 'error': None}

    def finish(self, folder, process):
        self.finish_calls += 1
        self.finished = True
        self.events.append('finish')
        process.returncode = 0
        if self.mode == 'deadline_after_finish':
            self.now = self.deadline + 1
        return {'confirmed': self.mode != 'finish_failure', 'exit_code': 0,
                'scope': 'synthetic lifecycle fixture, no backend process exists'}

    def verify_c_turn(self, result, audit, host, source, turn, request, *, capture):
        assert self.finished
        self.events.append('verify_' + turn)
        if self.mode == 'post_qualification_failure' and turn == 'REPEAT':
            raise AssertionError('injected_post_qualification_failure')
        expected = self.edited if turn == 'EDIT' else self.initial
        assert source == expected
        return self.qualification.verify_c_turn(result, audit, host, source, turn, request, capture=capture)

    def verify_sequence(self, rows):
        assert self.finished and self.calls == 3
        self.events.append('verify_sequence')
        if self.mode == 'sequence_failure':
            raise AssertionError('injected_sequence_failure')
        return self.qualification.verify_c_sequence(rows)

    def run(self):
        proxy = types.SimpleNamespace(read_capture=self.qualification.read_capture,
                                      verify_c_turn=self.verify_c_turn, verify_c_sequence=self.verify_sequence)
        with patch.object(self.runner, 'BATCH', self.output), \
                patch.object(self.runner, 'save', self.save), patch.object(self.runner, 'read', self.read), \
                patch.object(self.runner.subprocess, 'Popen', self.popen), \
                patch.object(self.runner.time, 'perf_counter_ns', self.clock), \
                patch.object(Path, 'read_bytes', lambda path: self.read_bytes(path)), \
                patch.object(Path, 'open', lambda path, *args, **kwargs: self.open(path, *args, **kwargs)), \
                patch.object(Path, 'exists', lambda path: self.exists(path)), \
                patch.object(Path, 'is_file', lambda path: self.is_file(path)):
            timing = self.runner.run_episode('C', {'scene_sha256': '7f6452d1d706a9f2db31126eb3aa7d08622e37a28abb9610992006bad5f5ad66'},
                types.SimpleNamespace(thin_turn=self.thin_turn), types.SimpleNamespace(attach=self.attach), proxy, self.driver)
        result = self.memory[self.folder / 'RESULTS.json']
        summary = {'mode': self.mode, 'synthetic': True, 'new_Blender_provider_API_calls': 0,
                   'events': self.events, 'finish_calls': self.finish_calls, 'edit_calls': self.edit_calls,
                   'business_windows': [{'turn': row['turn'], 'started_ns': row['started_ns'], 'ended_ns': row.get('ended_ns'),
                                         'execution_state': row.get('execution_state'), 'qualification_state': row.get('qualification_state'),
                                         'qualification_started_ns': row.get('qualification_started_ns'),
                                         'qualification_ended_ns': row.get('qualification_ended_ns')}
                                        for row in result['business']],
                   'execution_counts': result['execution_counts'], 'qualification_counts': result['qualification_counts'],
                   'sequence_qualification_state': result['sequence_qualification_state'],
                   'timing': timing, 'wire_reads': self.wire_reads,
                   'result_errors': result['errors'], 'raw_matrices_copied_to_disk': False}
        CASES.append(summary)
        return timing, result


class StageIntegrationTests(unittest.TestCase):
    def run_case(self, mode):
        output = OUTPUT / mode
        episode = ReferenceEpisode(output, mode)
        timing, result = episode.run()
        self.assertEqual(episode.finish_calls, 1)
        self.assertEqual(episode.calls, 3)
        self.assertEqual(episode.edit_calls, 1)
        self.assertEqual(result['execution_counts'], {'planned': 3, 'attempted': 3, 'successful_returns': 3, 'succeeded': 3, 'failed': 0, 'not_run': 0})
        self.assertTrue(all(row['execution_state'] == 'succeeded' for row in result['business']))
        for index, row in enumerate(result['business']):
            self.assertEqual((row['started_ns'], row['ended_ns']), episode.windows[index])
        self.assertEqual([event for event in episode.events if event.startswith('collect_')], ['collect_BASE', 'collect_REPEAT', 'collect_EDIT'])
        self.assertTrue(all(read['after_finish'] for read in episode.wire_reads))
        return episode, timing, result

    def test_collect_then_finish_then_actual_facts_and_sequence(self):
        episode, timing, result = self.run_case('normal')
        self.assertTrue(timing['accepted_success'])
        self.assertEqual(result['qualification_counts'], {'planned': 3, 'passed': 3, 'failed': 0, 'unverified': 0})
        self.assertLess(episode.events.index('collect_EDIT'), episode.events.index('finish'))
        self.assertLess(episode.events.index('finish'), episode.events.index('verify_BASE'))
        self.assertEqual(episode.events[-1], 'verify_sequence')
        self.assertEqual(result['sequence_verification']['matches'], [71, 71, 72])
        self.assertEqual(result['sequence_verification']['new_kernel_calls'], [112, 0, 10])

    def test_finish_failure_leaves_all_qualifications_unverified(self):
        episode, timing, result = self.run_case('finish_failure')
        self.assertFalse(timing['accepted_success'])
        self.assertEqual(result['qualification_counts']['passed'], 0)
        self.assertEqual(result['qualification_counts']['unverified'], 3)
        self.assertEqual(episode.wire_reads, [])

    def test_missing_wire_never_counts_unverified_as_passed(self):
        _, timing, result = self.run_case('missing_wire')
        self.assertFalse(timing['accepted_success'])
        self.assertEqual(result['qualification_counts']['passed'], 0)
        self.assertTrue(result['qualification_counts']['failed'] + result['qualification_counts']['unverified'] == 3)

    def test_post_qualification_error_preserves_execution_and_original_windows(self):
        _, timing, result = self.run_case('post_qualification_failure')
        self.assertFalse(timing['accepted_success'])
        repeated = result['business'][1]
        self.assertEqual(repeated['qualification_state'], 'failed')
        self.assertTrue(repeated['qualification_errors'])
        self.assertEqual(repeated['execution_state'], 'succeeded')
        self.assertLess(repeated['ended_ns'], repeated['qualification_started_ns'])

    def test_host_event_must_finish_inside_original_business_window(self):
        _, timing, result = self.run_case('event_overrun')
        self.assertFalse(timing['accepted_success'])
        self.assertEqual(result['business'][1]['qualification_state'], 'failed')
        self.assertTrue(result['business'][1]['qualification_errors'])

    def test_expired_absolute_deadline_cannot_pass_after_finish(self):
        _, timing, result = self.run_case('deadline_after_finish')
        self.assertFalse(timing['accepted_success'])
        self.assertFalse(timing['within_590s'])
        self.assertEqual(result['qualification_counts']['passed'], 0)

    def test_sequence_failure_is_failed_after_three_row_qualifications(self):
        _, timing, result = self.run_case('sequence_failure')
        self.assertFalse(timing['accepted_success'])
        self.assertEqual(result['qualification_counts'], {'planned': 3, 'passed': 3, 'failed': 0, 'unverified': 0})
        self.assertEqual(result['sequence_qualification_state'], 'failed')
        self.assertTrue(result['qualification_errors'])

    def test_publication_error_rewrites_final_verdict_without_losing_counts(self):
        episode, timing, result = self.run_case('publication_failure')
        self.assertFalse(timing['accepted_success'])
        self.assertEqual(result['qualification_counts']['passed'], 3)
        final = episode.memory[episode.folder / 'FINAL_TIMING.json']
        self.assertFalse(final['accepted_success'])
        error = episode.memory[episode.folder / 'PUBLICATION_ERROR.json']
        self.assertEqual(error['execution_counts'], result['execution_counts'])
        self.assertEqual(error['qualification_counts'], result['qualification_counts'])


def main():
    global OUTPUT
    parent = HERE / 'offline'
    parent.mkdir(exist_ok=True)
    OUTPUT = parent / ('attempt_' + str(len(list(parent.glob('attempt_*'))) + 1).zfill(2))
    OUTPUT.mkdir()
    stream = io.StringIO()
    began = time.perf_counter_ns()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(StageIntegrationTests)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    ended = time.perf_counter_ns()
    for path in (Path(__file__).resolve(), BATCH / 'engineering/run_candidate.py', FIX1 / 'qualification/verify_continuity.py'):
        raw_input(path)
    for name, record in INPUTS.items():
        data = (ROOT / name).read_bytes()
        assert len(data) == record['bytes'] and hashlib.sha256(data).hexdigest() == record['sha256'], name
    summary = {'schema': 'fix2_actual_runner_phase_integration_v1', 'test_methods': result.testsRun,
               'passed': result.wasSuccessful(), 'failures': len(result.failures), 'errors': len(result.errors),
               'wall_ns': ended - began, 'new_Blender_provider_API_calls': 0,
               'scope': 'Actual new run_episode; synthetic Popen/admin/thin and phase-gated fixed historical evidence; no large fixture copies',
               'fixture_note': 'BASE/EDIT ordinary default originals; REPEAT historical brief result with synthetic default request and unchanged raw evidence',
               'cases': CASES, 'inputs': [{'path': key, **value} for key, value in sorted(INPUTS.items())]}
    (OUTPUT / 'RESULT.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    (OUTPUT / 'unittest.txt').write_text(stream.getvalue(), encoding='utf8', newline='\n')
    print(json.dumps({key: summary[key] for key in ('test_methods', 'passed', 'failures', 'errors', 'new_Blender_provider_API_calls')}, ensure_ascii=False))
    if not result.wasSuccessful():
        print(stream.getvalue())
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
