"""Actual task templates with finite source generations and no Blender process."""
import builtins
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import py_compile
import tempfile
from types import CodeType, SimpleNamespace
import unittest
from unittest.mock import patch

from human_eye_plugin.blender_mcp_host import BlenderMCPHost, RPC_PREFIX
from human_eye_plugin.blender_process import NATIVE_OBSERVATION_PROTOCOL
from verification.test_selected_task_host import selected_fixture


ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / 'verification/fixes/20261106_perf020_o4/generation'
SLOT = '_human_eye_task_host_code_v1'
ORIGINAL_COMPILE = builtins.compile
ORIGINAL_EXEC = builtins.exec
SOURCE = '''GENERATION = GENERATION_VALUE
class BlenderSceneHost:
    native_observation_protocol = PROTOCOL_VALUE
    def __init__(self, bpy_module, execution_metadata=True, identity_metadata=True):
        self.bpy = bpy_module
        self.scene = bpy_module.context.scene
        self.view_layer = bpy_module.context.view_layer
        bpy_module.created.append(self)
        if getattr(self.scene, 'constructor_error', False):
            raise RuntimeError('fixture constructor failure')
    def capture_task_scene(self, selectors):
        self.bpy.captures.append(self)
        if getattr(self.scene, 'capture_error', False):
            raise RuntimeError('fixture capture failure')
        return {'generation': GENERATION, 'revision': self.scene.name,
                'scene': self.scene.name, 'view_layer': self.view_layer.name,
                'targets': list(self.scene.targets), 'selectors': selectors,
                'host_identity': {'document_epoch': self.scene.epoch},
                'loaded_sha': globals().get('_READONLY_LOADED_HOST_SHA256')}
    def capture_scene(self):
        return {'command': 'capture', 'scene': self.scene.name}
    def capture_evidence(self):
        return {'command': 'capture_evidence', 'capture': self.capture_scene()}
    def native_observation_capabilities(self):
        return {'command': 'native_observation_capabilities', 'scene': self.scene.name}
    def last_readonly_native_audit(self, request_id):
        return {'command': 'last_readonly_native_audit', 'request_id': request_id}
    def observe_readonly_native(self, **params):
        return {'command': 'observe_readonly_native', 'params': params}
'''


def source_bytes(generation):
    return SOURCE.replace('GENERATION_VALUE', repr(generation)).replace(
        'PROTOCOL_VALUE', repr(NATIVE_OBSERVATION_PROTOCOL)).encode('utf8')


class ReadWitness:
    def __init__(self, stream, counts):
        self.stream, self.counts = stream, counts

    def __enter__(self):
        self.stream.__enter__()
        return self

    def __exit__(self, *args):
        return self.stream.__exit__(*args)

    def read(self, *args, **kwargs):
        self.counts['read'] += 1
        return self.stream.read(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.stream, name)


class SourceWork:
    """Count the fixed source operations while calling their actual originals."""
    def __init__(self, path, raw):
        self.path, self.raw = path, raw
        self.counts = dict.fromkeys(('resolve', 'open', 'read', 'hash', 'compile', 'exec'), 0)
        self.compiled = []
        self.executed = []

    def __enter__(self):
        self.stack = ExitStack()
        original_resolve, original_open = Path.resolve, Path.open
        original_hash = hashlib.sha256

        def resolve(path, *args, **kwargs):
            if path == self.path:
                self.counts['resolve'] += 1
            return original_resolve(path, *args, **kwargs)

        def open_file(path, *args, **kwargs):
            if path != self.path:
                return original_open(path, *args, **kwargs)
            self.counts['open'] += 1
            return ReadWitness(original_open(path, *args, **kwargs), self.counts)

        def digest(raw=b'', *args, **kwargs):
            if raw == self.raw:
                self.counts['hash'] += 1
            return original_hash(raw, *args, **kwargs)

        def compile_source(raw, filename, *args, **kwargs):
            if filename == str(self.path):
                self.counts['compile'] += 1
                code = ORIGINAL_COMPILE(raw, filename, *args, **kwargs)
                self.compiled.append(code)
                return code
            return ORIGINAL_COMPILE(raw, filename, *args, **kwargs)

        def execute(code, globals=None, locals=None, **kwargs):
            if isinstance(code, CodeType) and code.co_filename == str(self.path):
                self.counts['exec'] += 1
                self.executed.append(code)
            return ORIGINAL_EXEC(code, globals, locals, **kwargs)

        self.stack.enter_context(patch.object(Path, 'resolve', resolve))
        self.stack.enter_context(patch.object(Path, 'open', open_file))
        self.stack.enter_context(patch.object(hashlib, 'sha256', digest))
        self.stack.enter_context(patch.object(builtins, 'compile', compile_source))
        self.stack.enter_context(patch.object(builtins, 'exec', execute))
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)


class ResidentTaskHostTests(unittest.TestCase):
    def setUp(self):
        RECORDS.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='source-unit-', dir=RECORDS)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.scene = SimpleNamespace(name='scene-1', targets=['target-1'], epoch='a' * 64)
        self.bpy = SimpleNamespace(app=SimpleNamespace(driver_namespace={}),
            context=SimpleNamespace(scene=self.scene, view_layer=SimpleNamespace(name='layer-1')),
            created=[], captures=[])
        self.remote, self.raw = self.connector('generation_a.py', source_bytes('A'))
        self.serial = 0

    def connector(self, name, raw):
        path = (self.base / name).resolve()
        path.write_bytes(raw)
        remote = BlenderMCPHost(ROOT)
        remote.source = path
        remote._readonly_host_source_sha256 = hashlib.sha256(raw).hexdigest()
        return remote, raw

    def run_template(self, remote=None, raw=None, *, command='capture_task', params=None, bpy=None):
        remote = self.remote if remote is None else remote
        raw = self.raw if raw is None else raw
        params = {'selectors': [{'name': 'target'}]} if params is None else params
        self.serial += 1
        request_id = 'resident-test-' + str(self.serial)
        text = remote._observation_code(command, params, request_id)
        outer_code = ORIGINAL_COMPILE(text, '<resident-template-test>', 'exec')
        output = io.StringIO()
        with SourceWork(remote.source, raw) as work, redirect_stdout(output):
            ORIGINAL_EXEC(outer_code, {'bpy': self.bpy if bpy is None else bpy})
        packet = output.getvalue()
        self.assertTrue(packet.startswith(RPC_PREFIX), packet)
        self.assertEqual(packet.count('\n'), 1)
        response = json.loads(packet[len(RPC_PREFIX):])
        self.assertEqual(response['id'], request_id)
        self.assertEqual(response['protocol_version'], '1.0')
        return response, work

    def resident_class(self):
        slot = self.bpy.app.driver_namespace[SLOT]
        self.assertIs(type(slot), tuple)
        self.assertEqual(len(slot), 3)
        self.assertIsInstance(slot[2], type)
        self.assertEqual(set(self.bpy.app.driver_namespace), {SLOT})
        return slot[2]

    def assert_cold(self, work):
        self.assertEqual(work.counts, dict.fromkeys(work.counts, 1))
        self.assertEqual(len(work.compiled), 1)
        self.assertIs(work.compiled[0], work.executed[0])

    def assert_hot(self, work):
        self.assertEqual(work.counts, dict.fromkeys(work.counts, 0))

    def assert_readonly_error(self, response, kind=None):
        self.assertEqual(set(response), {'protocol_version', 'id', 'error'})
        self.assertFalse(response['error']['mutation_uncertain'])
        if kind is not None:
            self.assertEqual(response['error']['type'], kind)

    def test_cold_positive_work_then_exact_code_reuse_and_fresh_host(self):
        first, cold = self.run_template()
        self.assert_cold(cold)
        cls = self.resident_class()
        method = cls.capture_task_scene.__code__
        second, hot = self.run_template()
        self.assert_hot(hot)
        self.assertIs(self.resident_class(), cls)
        self.assertIs(self.bpy.created[0].__class__.capture_task_scene.__code__, method)
        self.assertIs(self.bpy.created[1].__class__.capture_task_scene.__code__, method)
        self.assertIsNot(self.bpy.created[0], self.bpy.created[1])
        self.assertEqual(len(self.bpy.captures), 2)
        self.assertEqual(first['result'], second['result'])
        self.assertEqual(first['result']['loaded_sha'], self.remote._readonly_host_source_sha256)

    def test_hot_host_binds_current_scene_layer_and_target_values(self):
        self.run_template()
        original_class = self.resident_class()
        current = SimpleNamespace(name='scene-2', targets=['moved', 'new-instance'], epoch='b' * 64)
        self.bpy.context.scene = current
        self.bpy.context.view_layer = SimpleNamespace(name='layer-2')
        response, work = self.run_template()
        self.assert_hot(work)
        self.assertIs(self.resident_class(), original_class)
        self.assertIs(self.bpy.created[-1].scene, current)
        self.assertEqual(response['result']['scene'], 'scene-2')
        self.assertEqual(response['result']['view_layer'], 'layer-2')
        self.assertEqual(response['result']['targets'], ['moved', 'new-instance'])
        current.targets[:] = []
        response, work = self.run_template()
        self.assert_hot(work)
        self.assertEqual(response['result']['targets'], [])

    def test_slot_loss_reloads_once_with_new_executable_class(self):
        self.run_template()
        previous = self.resident_class()
        del self.bpy.app.driver_namespace[SLOT]
        _, work = self.run_template()
        self.assert_cold(work)
        self.assertIsNot(self.resident_class(), previous)
        _, work = self.run_template()
        self.assert_hot(work)

    def test_ordinary_wrong_slot_markers_are_misses(self):
        wrong = [None, {}, [], ('one',), ('path', 'hash', object()),
                 (str(self.remote.source), 'wrong-hash', type),
                 ('wrong-path', self.remote._readonly_host_source_sha256, type),
                 (str(self.remote.source), self.remote._readonly_host_source_sha256, object())]
        for marker in wrong:
            with self.subTest(marker=repr(marker)):
                self.bpy.app.driver_namespace[SLOT] = marker
                reply, work = self.run_template()
                self.assert_cold(work)
                self.assertEqual(reply['result']['generation'], 'A')
                self.resident_class()

    def test_same_generation_disk_edit_uses_resident_then_miss_rejects(self):
        self.run_template()
        previous = self.resident_class()
        self.remote.source.write_bytes(source_bytes('B'))
        response, work = self.run_template()
        self.assert_hot(work)
        self.assertEqual(response['result']['generation'], 'A')
        self.assertIs(self.resident_class(), previous)
        del self.bpy.app.driver_namespace[SLOT]
        response, work = self.run_template()
        self.assert_readonly_error(response, 'ValueError')
        self.assertIn('fixed connector snapshot', response['error']['message'])
        self.assertNotIn(SLOT, self.bpy.app.driver_namespace)
        self.assertEqual(work.counts['compile'], 0)

    def test_removed_source_hot_uses_resident_and_miss_reports_file_error(self):
        self.run_template()
        self.remote.source.unlink()
        response, work = self.run_template()
        self.assert_hot(work)
        self.assertEqual(response['result']['generation'], 'A')
        del self.bpy.app.driver_namespace[SLOT]
        response, _ = self.run_template()
        self.assert_readonly_error(response, 'FileNotFoundError')
        self.assertNotIn(SLOT, self.bpy.app.driver_namespace)

    def test_path_and_digest_generations_replace_one_slot_A_B_A(self):
        second, second_raw = self.connector('generation_b.py', source_bytes('B'))
        classes = []
        for remote, raw, generation in ((self.remote, self.raw, 'A'), (second, second_raw, 'B'),
                                         (self.remote, self.raw, 'A')):
            response, work = self.run_template(remote, raw)
            self.assert_cold(work)
            classes.append(self.resident_class())
            self.assertEqual(response['result']['generation'], generation)
            self.assertEqual(self.bpy.app.driver_namespace[SLOT][:2],
                             (str(remote.source), remote._readonly_host_source_sha256))
            _, work = self.run_template(remote, raw)
            self.assert_hot(work)
        self.assertEqual(len(set(classes)), 3)

    def test_same_path_new_digest_establishes_new_executable_generation(self):
        self.run_template()
        previous = self.resident_class()
        new_raw = source_bytes('B')
        self.remote.source.write_bytes(new_raw)
        self.remote._readonly_host_source_sha256 = hashlib.sha256(new_raw).hexdigest()
        response, work = self.run_template(self.remote, new_raw)
        self.assert_cold(work)
        self.assertEqual(response['result']['generation'], 'B')
        self.assertIsNot(self.resident_class(), previous)
        _, work = self.run_template(self.remote, new_raw)
        self.assert_hot(work)

    def test_failed_new_generation_preserves_successful_old_slot(self):
        self.run_template()
        previous = self.bpy.app.driver_namespace[SLOT]
        bad_cases = [('syntax.py', b'class :\n', 'SyntaxError'),
                     ('raises.py', b'raise RuntimeError("fixture exec failure")\n', 'RuntimeError'),
                     ('nonclass.py', b'BlenderSceneHost = 42\n', None),
                     ('oversize.py', b'#' * (512 * 1024 + 1), 'ValueError')]
        for name, raw, error_kind in bad_cases:
            with self.subTest(name=name):
                remote, _ = self.connector(name, raw)
                response, _ = self.run_template(remote, raw)
                self.assert_readonly_error(response, error_kind)
                self.assertIs(self.bpy.app.driver_namespace[SLOT], previous)
                response, work = self.run_template()
                self.assert_hot(work)
                self.assertEqual(response['result']['generation'], 'A')

    def test_bad_expected_digest_publishes_no_first_slot(self):
        self.remote._readonly_host_source_sha256 = '0' * 64
        response, work = self.run_template()
        self.assert_readonly_error(response, 'ValueError')
        self.assertEqual(work.counts['compile'], 0)
        self.assertEqual(self.bpy.app.driver_namespace, {})

    def test_business_failure_keeps_successfully_loaded_code(self):
        self.scene.capture_error = True
        response, work = self.run_template()
        self.assert_cold(work)
        self.assert_readonly_error(response, 'RuntimeError')
        cls = self.resident_class()
        self.scene.capture_error = False
        self.scene.constructor_error = True
        response, work = self.run_template()
        self.assert_hot(work)
        self.assert_readonly_error(response, 'RuntimeError')
        self.assertIs(self.resident_class(), cls)
        self.scene.constructor_error = False
        response, work = self.run_template()
        self.assert_hot(work)
        self.assertEqual(response['result']['generation'], 'A')

    def test_source_bytes_win_over_same_metadata_stale_pyc(self):
        path = self.remote.source
        path.write_bytes(source_bytes('B'))
        py_compile.compile(str(path), doraise=True)
        metadata = path.stat()
        path.write_bytes(self.raw)
        import os
        os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        self.assertEqual(len(self.raw), len(source_bytes('B')))
        self.assertTrue(list(path.parent.rglob('*.pyc')))
        response, work = self.run_template()
        self.assert_cold(work)
        self.assertEqual(response['result']['generation'], 'A')

    def test_full_and_native_commands_keep_loader_and_leave_task_slot(self):
        self.run_template()
        previous = self.bpy.app.driver_namespace[SLOT]
        cases = [('capture', {}), ('capture_evidence', {}), ('native_observation_capabilities', {}),
                 ('last_readonly_native_audit', {'request_id': 'native-id'}),
                 ('observe_readonly_native', {'request_id': 'native-id', 'focal_id': 'focal',
                    'reference_id': 'reference', 'expected_capture_revision': 'rev',
                    'deadline_ns': 1000, 'view': 'SCENE'})]
        for command, params in cases:
            with self.subTest(command=command):
                response, work = self.run_template(command=command, params=params)
                self.assert_cold(work)
                self.assertEqual(response['result']['command'], command)
                self.assertIs(self.bpy.app.driver_namespace[SLOT], previous)
        self.remote.source.write_bytes(source_bytes('B'))
        response, _ = self.run_template(command='capture', params={})
        self.assert_readonly_error(response, 'ValueError')
        self.assertIs(self.bpy.app.driver_namespace[SLOT], previous)
        response, work = self.run_template()
        self.assert_hot(work)
        self.assertEqual(response['result']['generation'], 'A')

    def test_typed_arguments_and_escaped_selectors_keep_original_boundaries(self):
        for command, params in [('capture_task', {}), ('capture_task', {'selectors': [], 'code': 'raise Exception'}),
                                ('apply', {})]:
            with self.subTest(command=command, params=params), self.assertRaisesRegex(ValueError, 'Invalid fixed'):
                self.remote._observation_code(command, params, 'typed')
        with self.assertRaisesRegex(ValueError, '4096'):
            self.remote._observation_code('last_readonly_native_audit', {'request_id': 'x' * 5000}, 'typed')
        with self.assertRaisesRegex(ValueError, '8192'):
            self.remote._observation_code('capture_task', {'selectors': [{'name': 'x' * 9000}]}, 'typed')
        selectors = [{'name': 'A' + '\x01' * 255} for _ in range(4)]
        response, _ = self.run_template(params={'selectors': selectors})
        self.assertEqual(response['result']['selectors'], selectors)

    def test_public_task_entry_performs_one_rpc_and_keeps_document_record(self):
        requests = []

        def exchange(payload):
            requests.append(payload)
            request = json.loads(payload)
            output = io.StringIO()
            with redirect_stdout(output):
                ORIGINAL_EXEC(request['params']['code'], {'bpy': self.bpy})
            return {'status': 'success', 'result': {'executed': True, 'result': output.getvalue()}}

        with patch.object(self.remote, '_exchange', exchange), self.remote.observation_transaction():
            first = self.remote.capture_task_scene([{'name': 'target'}])
            second = self.remote.capture_task_scene([{'id': 'target-id'}])
        self.assertEqual(len(requests), 2)
        self.assertEqual(first['generation'], second['generation'])
        self.assertEqual(self.remote._observation_document_epoch, 'a' * 64)
        self.assertTrue(self.remote.is_alive)
        self.assertEqual(len(self.bpy.captures), 2)

    def test_actual_host_code_reuses_class_and_reads_current_fake_scene_geometry(self):
        local, focal, reference, _ = selected_fixture()
        remote = BlenderMCPHost(ROOT)
        raw = remote.source.read_bytes()
        selectors = {'selectors': [{'name': 'Focal'}]}
        first, cold = self.run_template(remote, raw, params=selectors, bpy=local.bpy)
        self.assert_cold(cold)
        cached_class = local.bpy.app.driver_namespace[SLOT][2]
        focal.data.vertices[0].co = (0.25, 0, 0)
        second, hot = self.run_template(remote, raw, params=selectors, bpy=local.bpy)
        self.assert_hot(hot)
        self.assertIs(local.bpy.app.driver_namespace[SLOT][2], cached_class)
        self.assertNotEqual(first['result']['meshes'][0]['vertices'], second['result']['meshes'][0]['vertices'])
        self.assertEqual(focal.mesh_reads, 2)
        self.assertEqual(reference.mesh_reads, 0)
        replacement, _, _, _ = selected_fixture()
        replacement.scene.session_uid = 200
        replacement.scene.objects[1]._matrix_world[0][3] = 9.0
        local.bpy.context.scene = replacement.scene
        local.bpy.context.view_layer = replacement.view_layer
        third, hot = self.run_template(remote, raw, params=selectors, bpy=local.bpy)
        self.assert_hot(hot)
        self.assertIs(local.bpy.app.driver_namespace[SLOT][2], cached_class)
        self.assertNotEqual(second['result']['host_identity']['document_epoch'],
                            third['result']['host_identity']['document_epoch'])
        self.assertEqual(third['result']['meshes'][0]['vertices'][0][0], 9.0)


if __name__ == '__main__':
    unittest.main()
