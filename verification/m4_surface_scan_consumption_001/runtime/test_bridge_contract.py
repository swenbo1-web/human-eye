"""Offline bridge checks with synthetic owners, processes and retained handles."""

import ast
from contextlib import ExitStack, contextmanager
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import time
import tomllib
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / 'bridge_checks_01'
SOURCE = 'c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943'
EVIDENCE = {'real_process_launches': 0, 'Blender_sessions': 0, 'model_consumers': 0, 'checks': []}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


actor = load('_grooved_rail_bridge_actor', HERE / 'actor.py')
transport = load('_grooved_rail_bridge_transport', HERE / 'consumer_transport.py')
old_actor = ROOT / 'verification/m4_grooved_rail_consumption_001/runtime/actor.py'
old_transport = old_actor.with_name('consumer_transport.py')
tool_path = HERE.parent/'schemas/P_PUBLIC_TOOLS.json'
TOOLS = json.loads(tool_path.read_bytes())
OBSERVE = next(tool for tool in TOOLS if tool['name'] == 'human_eye_scene_observe')
EVIDENCE['tool_declaration_source'] = {'path': str(tool_path), 'sha256': hashlib.sha256(tool_path.read_bytes()).hexdigest()}


def node(path, name):
    return next(item for item in ast.parse(path.read_bytes()).body
                if isinstance(item, (ast.FunctionDef, ast.ClassDef)) and item.name == name)


@contextmanager
def synthetic_owner(group, *, runtime_confirmed=True, runtime_exit_error=False):
    folder = OUT / 'tmp' / ('owner_' + str(len(EVIDENCE['checks'])).zfill(3))
    folder.mkdir(parents=True, exist_ok=False)
    asset = folder / 'synthetic.blend'
    asset.write_bytes(b'synthetic data, never opened by Blender')
    records = []
    actual_tools = copy.deepcopy(TOOLS)
    selected = next(tool for tool in actual_tools if tool['name'] == 'human_eye_scene_observe')
    selected['x-synthetic-preserved'] = {'nested': [None, False, {'unknown': 'retained'}]}
    payload = {'content': [{'type': 'text', 'text': '{"schema_version":"task-query-set-v2","unknown":{"value":null}}'}],
               'isError': False, '_meta': {'opaque': [1, 2, {'keep': True}]}}

    class Native:
        def __init__(self):
            self.workspace = folder / 'owner/native'
            self.workspace.mkdir(parents=True)
            (self.workspace / 'WORKER_EVENTS.jsonl').write_bytes(b'')
            self.host = '127.0.0.1'
            self.port = 1

        def run(self, code, *, timeout_s):
            records.append(('native', timeout_s, len(code.encode('utf8'))))
            return {'response': {'status': 'success', 'result': {'result': '{"unit_scale_m":1.0,"objects":[]}'}}}

        def close(self):
            records.append(('native_close',))
            return {'process_reaped': True, 'exit_code': 0}

        def status(self):
            return {'closed': {'status': 'closed'}}

    class Loader:
        def create_module(self, spec):
            return None

        def exec_module(self, module):
            def start(**kwargs):
                records.append(('native_start', kwargs['max_calls'], kwargs['deadline_ns']))
                return Native()
            module.NativeSession = types.SimpleNamespace(start=start)

    class Peer:
        def __init__(self, config, out):
            self.out = out
            out.mkdir()
            self.process = types.SimpleNamespace(pid=900001)
            self.close_record = None

        def call(self, request, timeout_s=30):
            records.append(('peer', request['method']))
            audit = self.out.parent / 'audit.jsonl'
            with audit.open('ab') as stream:
                stream.write(b'{"event":"request_trace","pid":900002}\n')
            method = request['method']
            if method == 'initialize':
                return {'result': {'_meta': {'human_eye': {'source_sha256': SOURCE, 'source_kind': 'installed_distribution'}}}}
            if method == 'notifications/initialized':
                return None
            if method == 'tools/list':
                return {'result': {'tools': copy.deepcopy(actual_tools)}}
            if method == 'ping':
                return {'result': {}}
            if method == 'tools/call':
                return {'jsonrpc': '2.0', 'id': request['id'], 'result': copy.deepcopy(payload)}
            raise AssertionError(method)

        def close(self):
            records.append(('peer_close',))
            self.close_record = {'confirmed': True, 'process_reaped': True, 'exit_code': 0}
            return self.close_record

    handle = object()

    def runtime_proof(process, pid, deadline):
        records.append(('runtime_proof', process.pid, pid, deadline))
        return {'confirmed': runtime_confirmed}, handle if runtime_confirmed else None

    def runtime_exit(actual):
        records.append(('runtime_exit', actual is handle))
        if runtime_exit_error:
            raise RuntimeError('synthetic runtime exit error')
        return {'confirmed': actual is handle, 'exited': actual is handle, 'exit_code': 0 if actual is handle else None,
                'handle_closed': actual is handle}

    config = {'group': group, 'output': str(folder / 'owner'), 'worker_deadline_ns': time.perf_counter_ns() + 570_000_000_000,
              'blender': 'synthetic-never-launched', 'asset': str(asset), 'asset_sha256': hashlib.sha256(asset.read_bytes()).hexdigest(),
              'install_root': 'synthetic-install', 'entry': 'synthetic-entry', 'dependency_python': 'synthetic-python',
              'source_sha256': SOURCE, 'read_schemas': [copy.deepcopy(selected)] if group == 'P' else []}
    instance = actor.Owner.__new__(actor.Owner)
    with ExitStack() as stack:
        stack.enter_context(patch.object(actor.importlib.util, 'spec_from_file_location',
            side_effect=lambda name, path: importlib.util.spec_from_loader(name, Loader())))
        stack.enter_context(patch.object(actor, 'Peer', Peer))
        stack.enter_context(patch.object(actor.runtime, '_windows_runtime_proof', side_effect=runtime_proof))
        stack.enter_context(patch.object(actor.runtime, '_runtime_exit', side_effect=runtime_exit))
        yield instance, config, payload, selected, records
    EVIDENCE['checks'].append({'group': group, 'records': records})


class BridgeContractTests(unittest.TestCase):
    def setUp(self):
        self.no_process = patch.object(subprocess, 'Popen', side_effect=AssertionError('real process forbidden in offline checks'))
        self.no_process.start()
        self.addCleanup(self.no_process.stop)

    def test_tool_allowlists_and_common_native_are_exact(self):
        self.assertEqual(actor.TOOLS_BY_GROUP['P'], {'human_eye_scene_observe'})
        self.assertEqual(transport.TOOLS_BY_GROUP['N'], {'execute_blender_code'})
        self.assertEqual(transport.TOOLS_BY_GROUP['P'], {'execute_blender_code', 'human_eye_scene_observe'})
        native = load('_spatial_common_native_schema', ROOT / 'verification/native_plugin_complex_003/actor.py').NATIVE
        self.assertEqual(actor.encoded(actor.base.NATIVE), actor.encoded(native))

    def test_new_common_prompt_asset_and_frozen_schema_bindings(self):
        batch = HERE.parent
        prompt = (batch / 'input/PROMPT.txt').read_bytes()
        planned = next(line[2:] for line in (batch / 'ROOT_PLAN.md').read_text(encoding='utf8').splitlines()
                       if line.startswith('> 检查'))
        self.assertEqual(prompt.rstrip(b'\n'), planned.encode('utf8'))
        self.assertEqual(hashlib.sha256((batch / 'input/scene.blend').read_bytes()).hexdigest(),
                         '7f6452d1d706a9f2db31126eb3aa7d08622e37a28abb9610992006bad5f5ad66')
        self.assertEqual(json.loads((batch / 'schemas/COMMON_NATIVE.json').read_bytes()), actor.base.NATIVE)
        self.assertEqual(json.loads((batch / 'schemas/P_PUBLIC_TOOLS.json').read_bytes()), [OBSERVE])

    def test_argv_is_text_only_and_matches_exact_preapproval(self):
        folder = OUT / 'tmp/argv'
        folder.mkdir(parents=True)
        for group in ('N', 'P'):
            path = folder / (group + '.json')
            path.write_text(json.dumps({'group': group, 'endpoint': 'synthetic-endpoint'}), encoding='utf8')
            argv = transport.argv_for('synthetic-python', path, folder, folder / 'final.txt', group)
            self.assertNotIn('--image', argv)
            for flag in ('--ignore-user-config', '--ignore-rules', '--ephemeral', '--strict-config', '--json'):
                self.assertIn(flag, argv)
            configs = [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == '-c']
            setting = next(value for value in configs if value.startswith('mcp_servers.arm_engine='))
            table = tomllib.loads(setting)['mcp_servers']['arm_engine']
            self.assertEqual(set(table['tools']), transport.TOOLS_BY_GROUP[group])
            self.assertTrue(all(value == {'approval_mode': 'approve'} for value in table['tools'].values()))
            self.assertEqual(argv[argv.index('-m') + 1], 'gpt-6.1-sol')
            with self.assertRaisesRegex(ValueError, 'zero_initial_image'):
                transport.argv_for('synthetic-python', path, folder, folder / 'final.txt', group, initial_image='image.png')

    def test_zero_image_metadata_and_unchanged_isolation_settings(self):
        value = transport.initial_image_metadata({'image_count': 0, 'new_images': 0, 'inputs': {}})
        self.assertEqual((value['count'], value['bytes'], value['path']), (0, 0, None))
        for plan in ({'image_count': 1, 'new_images': 0, 'inputs': {}},
                     {'image_count': 0, 'new_images': 1, 'inputs': {}},
                     {'image_count': 0, 'new_images': 0, 'inputs': {'image': 'old.png'}}):
            with self.assertRaises(ValueError):
                transport.initial_image_metadata(plan)
        for name in ('settings', 'safe_environment', 'kill_owned_tree', 'wait_bridge_closed'):
            self.assertEqual(ast.dump(node(old_transport, name)), ast.dump(node(HERE / 'consumer_transport.py', name)))
        settings = transport.settings()
        self.assertEqual(settings['model_reasoning_effort'], 'medium')
        self.assertFalse(settings['features.hooks'])
        self.assertFalse(settings['features.memories'])
        self.assertEqual(settings['forced_login_method'], 'chatgpt')

    def test_real_peer_constructor_uses_ordinary_serve_with_fake_process(self):
        captured = []

        class Process:
            pid = 900003

            def __init__(self, command, **kwargs):
                captured.append(command)
                self.stdin, self.stdout = io.BytesIO(), io.BytesIO()
                self.returncode = None

            def poll(self):
                return self.returncode

            def wait(self, timeout):
                self.returncode = 0
                return 0

            def kill(self):
                self.returncode = 1

        with patch.object(actor.subprocess, 'Popen', Process):
            peer = actor.Peer({'dependency_python': 'synthetic-python', 'entry': 'synthetic-entry',
                               'product_config': 'synthetic-config', 'group': 'P'}, OUT / 'tmp/peer')
            self.assertTrue(peer.close()['confirmed'])
        self.assertIn('serve', captured[0])
        self.assertNotIn('--spatial-task-only', captured[0])

    def test_owner_exposes_full_selected_schema_and_forwards_complete_result(self):
        for group in ('N', 'P'):
            with synthetic_owner(group) as (owner, config, payload, selected, records):
                owner.__init__(config)
                self.assertEqual(owner.tools[0], actor.base.NATIVE)
                if group == 'P':
                    self.assertEqual(owner.tools[1], selected)
                    response = owner.handle({'jsonrpc': '2.0', 'id': 'full', 'method': 'tools/call', 'params': {
                        'name': 'human_eye_scene_observe', 'arguments': {'session_id': 'synthetic', 'include_image': False,
                        'query': {'mode': 'directory'}}}})
                    self.assertEqual(response['result'], payload)
                    self.assertEqual(owner.bytes, len(actor.encoded(response)))
                    self.assertTrue(any(row[0] == 'runtime_proof' and row[3] == config['worker_deadline_ns'] for row in records))
                else:
                    self.assertEqual(len(owner.tools), 1)
                closed = owner.close()
                self.assertTrue(closed['confirmed'])
                self.assertEqual(records[0][1], 128)
                self.assertEqual(records[-1][0], 'native_close')
                if group == 'P':
                    names = [row[0] for row in records]
                    self.assertLess(names.index('peer_close'), names.index('runtime_exit'))
                    self.assertLess(names.index('runtime_exit'), names.index('native_close'))

    def test_surface_scan_implicit_false_is_forwarded_unchanged(self):
        with synthetic_owner('P') as (owner, config, payload, selected, records):
            owner.__init__(config)
            seen = []
            original = owner.peer.call
            def capture(request, timeout_s=30):
                seen.append(copy.deepcopy(request))
                return original(request, timeout_s=timeout_s)
            owner.peer.call = capture
            request = {'jsonrpc':'2.0','id':'implicit','method':'tools/call','params':{
                'name':'human_eye_scene_observe','arguments':{'query':{'mode':'surface_scan','threshold_m':.002}}}}
            response = owner.handle(request)
            self.assertEqual(response['result'], payload)
            self.assertEqual(seen, [request])
            self.assertNotIn('include_image', request['params']['arguments'])
            self.assertTrue(owner.close()['confirmed'])

    def test_budget_is_cumulative_and_bounded_error_counts(self):
        with synthetic_owner('P') as (owner, config, payload, selected, records):
            owner.__init__(config)
            request = {'jsonrpc': '2.0', 'id': 'budget', 'method': 'tools/call', 'params': {
                'name': 'human_eye_scene_observe', 'arguments': {'include_image': False}}}
            expected = {'jsonrpc': '2.0', 'id': request['id'], 'result': payload}
            owner.bytes = 1048576 - len(actor.encoded(expected))
            owner.handle(request)
            self.assertEqual(owner.bytes, 1048576)
            with self.assertRaisesRegex(ValueError, 'common_tool_response_byte_budget_1MiB'):
                owner.handle(request)
            self.assertEqual(owner.bytes, 1048576)
            self.assertEqual(owner.calls, 2)
            self.assertIsNotNone(owner.logs[-1]['exception'])
            self.assertTrue(owner.close()['confirmed'])

    def test_zero_image_request_is_rejected_before_product_and_uses_attempt(self):
        with synthetic_owner('P') as (owner, config, payload, selected, records):
            owner.__init__(config)
            before = len([row for row in records if row[:2] == ('peer', 'tools/call')])
            response = owner.handle({'jsonrpc': '2.0', 'id': 'image', 'method': 'tools/call', 'params': {
                'name': 'human_eye_scene_observe', 'arguments': {'include_image': True}}})
            self.assertTrue(response['result']['isError'])
            self.assertIn('effective_include_image_false', response['result']['content'][0]['text'])
            self.assertEqual(before, len([row for row in records if row[:2] == ('peer', 'tools/call')]))
            self.assertEqual(owner.calls, 1)
            self.assertGreater(owner.bytes, 0)
            self.assertTrue(owner.close()['confirmed'])

    def test_unconfirmed_runtime_prevents_ready_and_cleanup_reaps_native(self):
        with synthetic_owner('P', runtime_confirmed=False) as (owner, config, payload, selected, records):
            with self.assertRaisesRegex(AssertionError, 'runtime_ownership_unconfirmed'):
                owner.__init__(config)
            self.assertFalse(owner.close()['confirmed'])
            self.assertEqual(records[-1][0], 'native_close')

    def test_runtime_exit_failure_never_skips_native_cleanup(self):
        with synthetic_owner('P', runtime_exit_error=True) as (owner, config, payload, selected, records):
            owner.__init__(config)
            closed = owner.close()
            self.assertFalse(closed['confirmed'])
            self.assertEqual(closed['errors'][0]['stage'], 'product_runtime_exit')
            self.assertEqual(records[-1][0], 'native_close')


if __name__ == '__main__':
    OUT.mkdir(exist_ok=False)
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BridgeContractTests))
    (OUT / 'TESTS.txt').write_text(log.getvalue(), encoding='utf8', newline='\n')
    record = {'passed': result.wasSuccessful(), 'methods': result.testsRun,
              'failures': [{'test': str(test), 'traceback': text} for test, text in result.failures],
              'errors': [{'test': str(test), 'traceback': text} for test, text in result.errors],
              'evidence': EVIDENCE, 'source_sha256': {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
              for name in ('actor.py', 'consumer_transport.py', 'test_bridge_contract.py')}}
    (OUT / 'RESULTS.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'passed': record['passed'], 'methods': record['methods'], 'failures': len(result.failures), 'errors': len(result.errors),
                      'real_process_launches': 0, 'Blender_sessions': 0, 'model_consumers': 0}))
    raise SystemExit(0 if record['passed'] else 1)
