"""002-only outer and scheduler checks with external startup/RPC substitutes."""

import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('outer002', HERE / 'driver.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
ORIGINAL_BATCH = driver.BATCH


def extended(path):
    if os.name != 'nt' or str(path).startswith('\\\\?\\'):
        return path
    return Path('\\\\?\\' + str(path.resolve()))


class StartupSubstitute:
    """Replace Popen and socket RPC, retaining actual loops and post-close reads."""

    def __init__(self):
        self.config = None
        self.active = None
        self.completed = []
        self.edited = False
        self.finish_signals = 0
        self.actor = None
        self.cli_count = 0

    def popen(self, command, **options):
        if '--config' in command:
            self.config = driver.read(command[command.index('--config') + 1])
            owner = Path(self.config['output'])
            owner.mkdir()
            driver.save(owner / 'INITIAL.json', driver.read(driver.QUAL / 'BASE_SNAPSHOT.json'))
            driver.save(Path(self.config['endpoint']), {'chain_deadline_ns': self.config['worker_deadline_ns'],
                        'host': '127.0.0.1', 'port': 1})
            actor = SimpleNamespace(pid=17000, returncode=None)

            def write(raw):
                assert raw == b'finish\n'
                self.finish_signals += 1
                snapshot = driver.QUAL / ('EDIT_SNAPSHOT.json' if self.edited else 'BASE_SNAPSHOT.json')
                driver.save(owner / 'FINAL.json', driver.read(snapshot))
                close = {'confirmed': True, 'errors': [], 'asset_unchanged': True,
                         'accepted_worker_geometry_matches': True, 'expected_terminal_geometry_matches': True,
                         'zero_new_images_budget_met': True, 'registered_pose_applied': self.edited}
                driver.save(owner / 'CLOSE.json', close)
                wire = owner / 'native/WIRE'
                (wire / '001').mkdir(parents=True)
                request, response = b'{"type":"close"}', b'{"status":"closed"}'
                (wire / '001/REQUEST.bin').write_bytes(request)
                (wire / '001/RESPONSE.bin').write_bytes(response)
                driver.save(wire / 'INDEX.json', [{'sequence': 1, 'response_sendall_completed': True,
                    'request_bytes': len(request), 'response_attempted_bytes': len(response),
                    'request_response_attempted_bytes': len(request) + len(response)}])
                actor.returncode = 0

            actor.stdin = SimpleNamespace(write=write, close=lambda: None)
            actor.poll = lambda: actor.returncode
            actor.wait = lambda timeout: actor.returncode
            self.actor = actor
            return actor
        assert command[0] == driver.read(driver.CLI_INTERFACE)['executable'], 'unexpected_external_launch'
        self.cli_count += 1
        final = Path(command[command.index('-o') + 1])
        text = 'SYNTHETIC 002 startup-substitute final'
        final.write_text(text, encoding='utf8')
        events = [{'type': 'thread.started', 'thread_id': '75e546be-1fb7-4e10-87e5-38ef4cd611c6'},
                  {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': text}},
                  {'type': 'turn.completed', 'usage': {'input_tokens': 0, 'output_tokens': 0}}]
        process = SimpleNamespace(pid=17000 + self.cli_count, returncode=0, stdin=io.BytesIO(),
                                  stdout=io.BytesIO(b''.join((json.dumps(row) + '\n').encode() for row in events)),
                                  stderr=io.BytesIO())
        process.poll = lambda: 0
        process.wait = lambda timeout: 0
        return process

    def status(self):
        return {'episode_id': self.config['episode_id'], 'owner_pid': 17000, 'native_pid': 17001,
                'native_host': '127.0.0.1', 'native_port': 1, 'native_workspace': self.config['output'],
                'product_launcher_pid': None, 'product_runtime_proof': None, 'session_id': 'current-scene',
                'worker_deadline_ns': self.config['worker_deadline_ns'], 'business_attempts': 0,
                'active_turn': self.active, 'completed_turns': self.completed}

    def attach(self, endpoint, kind, request):
        operation = request['method'].removeprefix('continuity/')
        arguments = request['params']
        if operation == 'begin_turn':
            self.active = arguments['turn_id']
        elif operation == 'end_turn':
            self.completed.append(self.active)
            self.active = None
        elif operation == 'qa_advance':
            assert self.completed == ['BASE', 'REPEAT'] and not self.edited
            self.edited = True
            owner = Path(self.config['output'])
            driver.save(owner / 'PRE_EDIT.json', driver.read(driver.QUAL / 'BASE_SNAPSHOT.json'))
            driver.save(owner / 'EDIT.json', driver.read(driver.QUAL / 'EDIT_SNAPSHOT.json'))
        return {'jsonrpc': '2.0', 'id': request['id'], 'result': self.status()}


class WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = HERE / 'offline'
        parent.mkdir(exist_ok=True)
        numbers = [int(path.name[1:]) for path in parent.glob('a*') if path.is_dir() and path.name[1:].isdigit()]
        cls.output = extended(parent / ('a' + str(max(numbers, default=0) + 1).zfill(2)))
        cls.output.mkdir()
        cls.records = []

    def plan(self):
        root = self.output / self._testMethodName[-12:]
        batch = root / 'm4_surface_scan_continuous_consumption_002'
        (batch / 'inputs').mkdir(parents=True)
        plan = driver.read(ORIGINAL_BATCH / 'PLAN.json')
        plan['runtime_root'] = str(root / '.m4cc2')
        for name in ('C_READY.json', 'C_PUBLIC_TOOLS.json', 'PROMPT_T1.txt', 'PROMPT_T2_T3.txt'):
            (batch / 'inputs' / name).write_bytes((ORIGINAL_BATCH / 'inputs' / name).read_bytes())
        driver.save(batch / 'PLAN.json', plan)
        return root, batch, plan

    def test_actual_wrapper_full_outer(self):
        root, batch, plan = self.plan()
        startup = StartupSubstitute()
        original_load = driver.load
        loaded = []

        def loading(name, path):
            module = original_load(name, path)
            if path == driver.ATTACH:
                module.attach = startup.attach
            if path == driver.COORDINATOR:
                loaded.append(module)
            return module

        with patch.object(driver, 'ROOT', root), patch.object(driver, 'BATCH', batch), \
                patch.object(driver, 'load', side_effect=loading), \
                patch.object(driver.subprocess, 'Popen', side_effect=startup.popen):
            row = driver.run_one(plan['sequence'][0], plan)
        self.assertEqual(len(loaded), 1)
        self.assertFalse(hasattr(loaded[0], 'pack'))
        self.assertEqual(startup.finish_signals, 1)
        self.assertEqual(startup.cli_count, 3)
        self.assertTrue(row['postclose_verification']['passed'], row['errors'])
        self.assertTrue(row['terminal_wire_verification']['passed'])
        self.assertTrue(row['outer_valid_completion'], row['errors'])
        self.assertEqual(row['execution_counts'], {'planned': 3, 'completed': 3, 'failed': 0, 'not_run': 0})
        manifest = driver.read(Path(row['runtime_manifest']))
        with zipfile.ZipFile(row['runtime_archive']) as archive:
            self.assertEqual(set(archive.namelist()), set(manifest['members']))
            for name, expected in manifest['members'].items():
                raw = archive.read(name)
                self.assertEqual(len(raw), expected['bytes'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected['sha256'])
            self.assertIn('owner/CLOSE.json', archive.namelist())
            self.assertIn('SOURCE_GUARD_AFTER.json', archive.namelist())
            self.assertIn('c/EPISODE_RESULT.json', archive.namelist())
        self.assertTrue((Path(row['folder']) / 'OUTER_RESULT.json').is_file())
        self.assertTrue((Path(row['folder']) / 'FINAL_TIMING.json').is_file())
        self.records.append({'case': self._testMethodName, 'finish_signals': startup.finish_signals,
                             'substituted_CLI_starts': startup.cli_count, 'archive_members': len(manifest['members']),
                             'outer_valid_completion': row['outer_valid_completion']})

    def fault_row(self, slot, plan, tool_error):
        runtime = Path(plan['runtime_root']) / slot['cell']
        owner = runtime / 'owner/tool_01'
        folder = runtime / 'c/turns/BASE'
        copied = folder / 'owner_turn/tool_01'
        owner.mkdir(parents=True)
        copied.mkdir(parents=True)
        response = {'jsonrpc': '2.0', 'id': 1, 'result': {'content': [{'type': 'text', 'text': 'fixture'}], 'isError': tool_error}}
        request = {'params': {'name': 'execute_blender_code', 'arguments': {'code': 'fixture'}}}
        item = {'type': 'mcp_tool_call', 'tool': 'execute_blender_code', 'arguments': request['params']['arguments'],
                'status': 'failed' if tool_error else 'completed', 'error': None,
                'result': {'content': [{'type': 'text', 'text': 'fixture' if tool_error else 'tampered'}], 'structured_content': None}}
        driver.save(owner / 'RESPONSE.json', response)
        driver.save(owner / 'REQUEST.json', request)
        (copied / 'RESPONSE.json').write_bytes((owner / 'RESPONSE.json').read_bytes())
        driver.save(folder / 'BUSINESS_SOURCE_BINDING.json', {'recorded_owner_attempts': [1]})
        (folder / 'events.jsonl').write_text(json.dumps({'event': {'type': 'item.completed', 'item': item}}) + '\n', encoding='utf8')
        record = {'valid_completion': False, 'status': 'failed', 'thread_id': slot['anonymous_episode_id'],
                  'expected_thread_id': None, 'process_reaped': True, 'readers_stopped': True,
                  'safe_to_continue': True, 'mutation_unknown': False, 'bridge_protocol_errors': [],
                  'unexpected_tool_deviations': [], 'errors': [{'stage': 'business_original_binding',
                      'errors': [{'attempt': 1, 'reason': 'CLI_result_differs_from_owner'}]}]}
        coordinator = {'turns': [{'turn_index': 1, 'turn_label': 'BASE', 'folder': str(folder), 'consumer': record}]}
        row = {**slot, 'runtime_folder': str(runtime), 'owner_output': str(runtime / 'owner'),
               'coordinator': coordinator, 'owner_started': True, 'owner_finish': {'confirmed': True},
               'owner_finish_calls': 1, 'errors': []}
        row['shared_binding_check'] = driver.shared_binding_check(row)
        row['stop_reasons'] = driver.stop_reasons(row)
        row['execution_counts'] = driver.counts(driver.execution_rows(coordinator))
        row['continuity'] = driver.continuity(coordinator)
        return row

    def scheduler(self, tool_error):
        root, batch, plan = self.plan()
        entered = []

        def run_one(slot, plan):
            entered.append(slot['cell'])
            row = self.fault_row(slot, plan, tool_error)
            self.assertEqual(row['owner_finish_calls'], 1)
            return row

        with patch.object(driver, 'ROOT', root), patch.object(driver, 'BATCH', batch), \
                patch.object(driver, 'run_one', side_effect=run_one):
            result = driver.run_batch(plan)
        self.records.append({'case': self._testMethodName, 'entered': entered,
                             'execution_counts': result['execution_counts'],
                             'stop_reasons': [entry['reason'] for entry in result['stop_reasons']]})
        return entered, result

    def test_shared_fault_stops_fixed_remainder(self):
        entered, result = self.scheduler(False)
        self.assertEqual(entered, ['N1'])
        self.assertEqual(result['stop_reasons'][0]['reason'], 'shared_success_binding_fault')
        self.assertEqual([row['cell'] for row in result['not_run_episodes']], list(driver.CELLS[1:]))
        self.assertEqual(result['execution_counts'], {'planned': 18, 'completed': 0, 'failed': 1, 'not_run': 17})

    def test_tool_error_keeps_original_policy(self):
        entered, result = self.scheduler(True)
        self.assertEqual(tuple(entered), driver.CELLS)
        self.assertEqual(result['stop_reasons'], [])
        self.assertEqual(result['execution_counts'], {'planned': 18, 'completed': 0, 'failed': 6, 'not_run': 12})


if __name__ == '__main__':
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(WiringTests))
    text = stream.getvalue()
    print(text, end='')
    (WiringTests.output / 'TESTS.txt').write_text(text, encoding='utf8', newline='\n')
    driver.save(WiringTests.output / 'RESULT.json', {'tests': result.testsRun, 'failures': len(result.failures),
                'errors': len(result.errors), 'passed': result.wasSuccessful(), 'records': WiringTests.records,
                'new_model_Blender_product_provider_calls': 0,
                'scope': 'Actual wrapper, consumer/coordinator, finish/postclose/packer/publication; Popen and owner RPC substituted. Scheduler cases substitute run_one.'})
    raise SystemExit(0 if result.wasSuccessful() else 1)
