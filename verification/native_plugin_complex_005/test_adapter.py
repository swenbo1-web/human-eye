"""Small, pure fake checks for the 005 public read-tool adapter.

Only the actual Owner.handle is exercised. Owner/Peer constructors, product
imports, network, Blender and consumers are never used. Temporary fake logs
are removed; the exclusive ADAPTER_TESTS.json keeps the actual test result.
"""
import copy
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
EXPECTED_ACTOR = '42086c72a30500e86298f1e61802daf19979e58dcdbb4a1fdf482a4a70f48eda'
EXPECTED_NATIVE = '77d56a2b28839af4fa24054456f29003d48bc7a1f14dfce49be5823234e6eb14'
READ_NAMES = {'human_eye_scene_observe', 'human_eye_connection_status'}
actor = None
GUARD_ATTEMPTS = []


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def forbidden(*args, **kwargs):
    GUARD_ATTEMPTS.append('process_network_or_constructor')
    raise AssertionError('Pure adapter checks must not construct a real backend')


class PeerFake:
    def __init__(self):
        self.requests = []
        self.reply = None

    def call(self, request, *, timeout_s):
        self.requests.append((request, timeout_s))
        self.reply = {'jsonrpc': '2.0', 'id': request['id'], 'result': {
            'content': [{'type': 'text', 'text': '{"status":"partial","distance_m":0.003,"unknown":["x"]}\n'}],
            'isError': False, '_meta': {'fixture': 'unchanged'}}}
        return self.reply


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='complex005-adapter-fake-')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.index = 0

    def owner(self, *, group='H'):
        self.index += 1
        value = actor.Owner.__new__(actor.Owner)
        value.out = self.folder / str(self.index)
        value.out.mkdir()
        value.calls, value.bytes, value.logs = 0, 0, []
        value.started = time.perf_counter_ns()
        value.peer = None if group == 'N' else PeerFake()
        value.native = types.SimpleNamespace(run=forbidden)
        return value

    @staticmethod
    def request(name, arguments):
        return {'jsonrpc': '2.0', 'id': 'fake-request', 'method': 'tools/call',
                'params': {'name': name, 'arguments': arguments, '_meta': {'fixture': 7}}}

    def ledger(self, owner, request, response, *, failure=None):
        folder = owner.out / ('tool_' + str(owner.calls).zfill(2))
        self.assertEqual(json.loads((folder / 'REQUEST.json').read_bytes()), request)
        row = json.loads((folder / 'ATTEMPT.json').read_bytes())
        document = json.loads((owner.out / 'TOOLS.json').read_bytes())
        self.assertEqual(document['attempts'], owner.calls)
        self.assertEqual(document['tools'], owner.logs)
        self.assertEqual(document['wire_tool_bytes'], len(actor.encoded(response)))
        self.assertEqual(row['response_bytes'], len(actor.encoded(response)))
        self.assertIs(type(row['started_ns']), int)
        self.assertGreaterEqual(row['elapsed_ns'], 0)
        self.assertEqual(row['is_error'], failure is not None)
        if failure is None:
            self.assertIsNone(row['exception'])
            self.assertEqual(json.loads((folder / 'RESPONSE.json').read_bytes()), response)
        else:
            self.assertEqual(row['exception']['message'], failure)
            self.assertTrue(response['result']['isError'])
            self.assertEqual(json.loads((folder / 'ERROR_RESPONSE.json').read_bytes()), response)

    def forwarded(self, request):
        owner = self.owner()
        before = copy.deepcopy(request)
        response = owner.handle(request)
        self.assertEqual(request, before)
        self.assertIs(owner.peer.requests[0][0], request)
        self.assertEqual(len(owner.peer.requests), 1)
        self.assertGreater(owner.peer.requests[0][1], 0)
        self.assertLessEqual(owner.peer.requests[0][1], 30)
        self.assertEqual(response, owner.peer.reply)
        self.ledger(owner, request, response)

    def test_status_needs_no_image_flag_and_forwards_original_request_and_response(self):
        self.forwarded(self.request('human_eye_connection_status', {}))

    def test_scene_explicit_false_forwards_original_request_and_response(self):
        self.forwarded(self.request('human_eye_scene_observe', {
            'include_image': False, 'query': {'mode': 'overview'}, 'response_detail': 'full'}))

    def test_scene_true_or_missing_rejected_without_peer_and_charged(self):
        for arguments in ({'include_image': True}, {}):
            with self.subTest(arguments=arguments):
                owner = self.owner()
                request = self.request('human_eye_scene_observe', arguments)
                response = owner.handle(request)
                self.assertEqual(owner.calls, 1)
                self.assertEqual(owner.peer.requests, [])
                self.ledger(owner, request, response,
                    failure='zero_image_budget_requires_explicit_include_image_false')

    def test_unpublished_write_tools_rejected_without_peer_and_charged(self):
        for name in ('human_eye_transform', 'human_eye_clearance_segment'):
            with self.subTest(name=name):
                owner = self.owner()
                request = self.request(name, {'execute': True})
                response = owner.handle(request)
                self.assertEqual(owner.calls, 1)
                self.assertEqual(owner.peer.requests, [])
                self.ledger(owner, request, response, failure='tool_not_available')

    def test_native_group_does_not_gain_status(self):
        owner = self.owner(group='N')
        request = self.request('human_eye_connection_status', {})
        response = owner.handle(request)
        self.ledger(owner, request, response, failure='tool_not_available')

    def test_status_does_not_bypass_shared_attempt_budget(self):
        owner = self.owner()
        owner.calls = 32
        request = self.request('human_eye_connection_status', {})
        response = owner.handle(request)
        self.assertEqual(owner.calls, 33)
        self.assertEqual(owner.peer.requests, [])
        self.ledger(owner, request, response, failure='common_tool_attempt_budget_32')

    def test_common_native_and_each_release_original_read_schemas(self):
        self.assertEqual(digest(canonical(actor.base.NATIVE)), EXPECTED_NATIVE)
        source = json.loads((HERE / 'SOURCE_PREFLIGHT.json').read_bytes())
        modes = {}
        for group, expected_count in (('H', 4), ('C', 5)):
            catalogue = json.loads((HERE / (group + '_TOOLS_CATALOGUE.json')).read_bytes())
            probe = json.loads((HERE / (group + '_schemas.stdout.json')).read_bytes())
            tools = catalogue['tools_list']['result']['tools']
            self.assertEqual(tools, probe['tools_list']['result']['tools'])
            self.assertEqual(len(tools), expected_count)
            self.assertTrue(catalogue['original_definitions_unchanged'])
            self.assertEqual(catalogue['source_sha256'], source['versions'][group]['source_sha256'])
            reads = [tool for tool in tools if tool['name'] in READ_NAMES]
            self.assertEqual([tool['name'] for tool in reads], source['versions'][group]['proposed_public_tools'])
            owner = self.owner(group=group)
            owner.tools = [copy.deepcopy(actor.base.NATIVE)] + copy.deepcopy(reads)
            listed = owner.handle({'jsonrpc': '2.0', 'id': 'catalogue', 'method': 'tools/list'})
            self.assertEqual(listed['result']['tools'], [actor.base.NATIVE] + reads)
            self.assertEqual(owner.calls, 0)
            observe = next(tool for tool in reads if tool['name'] == 'human_eye_scene_observe')
            modes[group] = observe['inputSchema']['properties']['query']['properties']['mode']['enum']
        self.assertNotIn('task', modes['H'])
        self.assertNotIn('surface_nearest', modes['H'])
        self.assertIn('task', modes['C'])
        self.assertIn('surface_nearest', modes['C'])


def main():
    global actor
    output = HERE / 'ADAPTER_TESTS.json'
    if output.exists():
        raise FileExistsError('Adapter check result is exclusive; do not overwrite')
    actor_path = HERE / 'actor.py'
    raw = actor_path.read_bytes()
    if digest(raw) != EXPECTED_ACTOR:
        raise RuntimeError('Actor changed before the frozen fake checks')
    text = io.StringIO()
    with patch.object(subprocess, 'Popen', side_effect=forbidden), \
            patch.object(socket, 'socket', side_effect=forbidden), \
            patch.object(socket, 'create_connection', side_effect=forbidden):
        actor = types.ModuleType('complex005_adapter_fake_actor')
        actor.__file__ = str(actor_path)
        exec(compile(raw, str(actor_path), 'exec'), actor.__dict__)
        with patch.object(actor.Owner, '__init__', side_effect=forbidden), \
                patch.object(actor.Peer, '__init__', side_effect=forbidden):
            result = unittest.TextTestRunner(stream=text, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(AdapterTests))
    unchanged = actor_path.read_bytes() == raw
    product_imports = sorted(name for name in sys.modules if name == 'human_eye_plugin' or name.startswith('human_eye_plugin.'))
    inputs = [HERE / 'SOURCE_PREFLIGHT.json'] + [HERE / (g + suffix)
        for g in ('H', 'C') for suffix in ('_TOOLS_CATALOGUE.json', '_schemas.stdout.json')]
    value = {'schema': 'complex005-public-adapter-pure-fakes-v1', 'tests_run': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
        'passed': result.wasSuccessful() and unchanged and not GUARD_ATTEMPTS and not product_imports,
        'actor_sha256': digest(raw), 'actor_source_unchanged': unchanged,
        'test_sha256': digest(Path(__file__).read_bytes()),
        'input_files_sha256': {str(p): digest(p.read_bytes()) for p in inputs},
        'common_native_canonical_sha256': digest(canonical(actor.base.NATIVE)),
        'failure_ids': [test.id() for test, _ in result.failures],
        'error_ids': [test.id() for test, _ in result.errors], 'log': text.getvalue(),
        'guard_attempts': GUARD_ATTEMPTS, 'product_modules_imported': product_imports,
        'Blender_runs': 0, 'serve_processes': 0, 'consumer_runs': 0,
        'performance_samples': 0, 'scope': 'Actual Owner.handle against temporary fakes; constructors forbidden; original schemas read as JSON only.'}
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(value, ensure_ascii=False))
    return 0 if value['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
