"""Pinned read helpers and exact-byte host loading; no Blender is launched."""
from __future__ import annotations

import ast
import base64
import copy
from fractions import Fraction
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from human_eye_plugin.blender_mcp_host import BlenderMCPHost, RPC_PREFIX

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'verification/fixes/20261031_v21_readonly_dependency/design_work'
HOST=ROOT/'human_eye_plugin/blender_host.py'
HELPERS=('episode_gateway.py','forward_deadline.py')


class ReadonlyDependencyLoaderTests(unittest.TestCase):
    def setUp(self):
        WORK.mkdir(parents=True,exist_ok=True)
        self.private=tempfile.TemporaryDirectory(prefix='loader-',dir=WORK)
        self.root=Path(self.private.name).resolve()
        assert self.root.is_relative_to(WORK.resolve())
        self.package=self.root/'human_eye_plugin';self.package.mkdir()
        for name in ('blender_host.py',*HELPERS):
            (self.package/name).write_bytes((HOST.parent/name).read_bytes())
        self.module=self.load_host()
        self.host=self.module.BlenderSceneHost.__new__(self.module.BlenderSceneHost)

    def tearDown(self):
        # Only this freshly allocated, checked private fixture is removed.
        assert self.root.is_relative_to(WORK.resolve())
        self.private.cleanup()

    def load_host(self):
        path=self.package/'blender_host.py'
        module=ModuleType('_readonly_dependency_test_host');module.__file__=str(path)
        exec(compile(path.read_bytes(),str(path),'exec',dont_inherit=True),module.__dict__)
        return module

    def execute_template(self,host=None,command='native_observation_capabilities',params=None,**options):
        from verification.test_blender_native_evidence import fixture
        host=host or BlenderMCPHost(self.root)
        code=host._observation_code(command,params or {},'fixed-nonce')
        output=io.StringIO()
        namespace={'bpy':fixture()[0].bpy}
        with patch('sys.stdout',output),patch.dict('builtins.__dict__',options):
            exec(compile(code,'<fixed-readonly-template>','exec'),namespace)
        raw=output.getvalue()
        self.assertTrue(raw.startswith(RPC_PREFIX));self.assertEqual(raw.count('\n'),1)
        return json.loads(raw[len(RPC_PREFIX):]),namespace

    def poison_pyc(self,path):
        # This is a deliberately valid timestamp/size cache in our new fixture.
        from importlib._bootstrap_external import _code_to_timestamp_pyc
        stat=path.stat();cache=Path(importlib.util.cache_from_source(str(path)))
        cache.parent.mkdir(exist_ok=True)
        code=compile("raise RuntimeError('untrusted cache executed')",str(path),'exec')
        cache.write_bytes(_code_to_timestamp_pyc(code,int(stat.st_mtime),stat.st_size))
        return cache

    def test_literal_pins_match_exact_current_helper_sources(self):
        self.assertEqual(set(self.module._READONLY_DEPENDENCY_SHA256),set(HELPERS))
        for name,digest in self.module._READONLY_DEPENDENCY_SHA256.items():
            self.assertEqual(digest,hashlib.sha256((self.package/name).read_bytes()).hexdigest())

    def test_capability_keeps_exact_v1_fields_and_loads_no_writer_state(self):
        value=self.host.native_observation_capabilities()
        self.assertEqual(set(value),{'schema_version','protocol','process_id','clock',
            'max_duration_ns','host_source_sha256','read_only','execution_authority'})
        self.assertEqual(value['host_source_sha256'],hashlib.sha256(HOST.read_bytes()).hexdigest())
        self.assertTrue(value['read_only']);self.assertFalse(value['execution_authority'])
        self.assertEqual(set(self.host.__dict__),{'_readonly_clock_module_cache'})

    def test_fixed_loader_digest_is_used_instead_of_rehashing_later_host_file(self):
        self.module._READONLY_LOADED_HOST_SHA256='a'*64
        (self.package/'blender_host.py').write_text('new unrelated disk contents',encoding='utf8')
        self.assertEqual(self.host.native_observation_capabilities()['host_source_sha256'],'a'*64)

    def test_each_missing_dependency_refuses_before_any_helper_compilation(self):
        for name in HELPERS:
            with self.subTest(name=name):
                path=self.package/name;raw=path.read_bytes();path.unlink()
                try:
                    with patch.object(self.host,'_readonly_checked_module',side_effect=AssertionError('must not compile')):
                        with self.assertRaisesRegex(self.module.BlenderHostError,'readonly_dependency_'):
                            self.host.native_observation_capabilities()
                finally:path.write_bytes(raw)

    def test_each_mismatched_dependency_refuses_capability_and_render_module(self):
        for name in HELPERS:
            with self.subTest(name=name):
                path=self.package/name;raw=path.read_bytes();path.write_bytes(raw+b'\n# mismatched\n')
                try:
                    for method in (self.host.native_observation_capabilities,self.host._readonly_native_module):
                        with self.assertRaisesRegex(self.module.BlenderHostError,'readonly_dependency_source_mismatch'):
                            method()
                finally:path.write_bytes(raw)

    def test_source_read_is_bounded_before_hash_or_compile(self):
        path=self.package/'episode_gateway.py'
        path.write_bytes(b'x'*(self.module._READONLY_SOURCE_LIMIT+1))
        with self.assertRaisesRegex(self.module.BlenderHostError,'readonly_dependency_source_mismatch'):
            self.host._readonly_native_module()

    def test_sibling_resolving_outside_fixed_root_is_rejected_before_open(self):
        real_resolve=Path.resolve
        def resolve(path,*args,**kwargs):
            return self.root/'outside.py' if path==self.package/'episode_gateway.py' else real_resolve(path,*args,**kwargs)
        with patch.object(Path,'resolve',resolve),patch.object(Path,'open',side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(self.module.BlenderHostError,'readonly_dependency_root_or_file_invalid'):
                self.host._readonly_native_module()

    def test_warm_module_identity_remains_usable_for_existing_fault_injection(self):
        first=self.host._readonly_native_module();first._local_test_marker=object()
        self.assertIs(first,self.host._readonly_native_module())
        self.assertIs(first._local_test_marker,self.host._readonly_native_module()._local_test_marker)

    def test_warm_render_module_cannot_hide_later_dependency_drift(self):
        self.host._readonly_native_module();self.host.native_observation_capabilities()
        for name in HELPERS:
            with self.subTest(name=name):
                path=self.package/name;raw=path.read_bytes();path.write_bytes(raw+b'\n')
                try:
                    with self.assertRaisesRegex(self.module.BlenderHostError,'readonly_dependency_source_mismatch'):
                        self.host._readonly_native_module()
                    with self.assertRaisesRegex(self.module.BlenderHostError,'readonly_dependency_source_mismatch'):
                        self.host.native_observation_capabilities()
                finally:path.write_bytes(raw)

    def test_helper_pycs_are_not_executed_even_if_timestamp_and_size_match(self):
        for name in HELPERS:self.poison_pyc(self.package/name)
        # Establish that the fixture really would trip the previous loader.
        spec=importlib.util.spec_from_file_location('_prove_poison',self.package/'episode_gateway.py')
        with self.assertRaisesRegex(RuntimeError,'untrusted cache executed'):
            spec.loader.exec_module(importlib.util.module_from_spec(spec))
        self.assertEqual(self.host._readonly_native_module().PROTOCOL,'owned-common-native-v1-20261031')
        self.assertEqual(self.host.native_observation_capabilities()['clock']['source'],'windows_systemwide_qpc')

    def test_helper_compile_uses_checked_snapshot_when_disk_changes_after_read(self):
        checked=self.host._readonly_dependency_sources();path,raw=checked['episode_gateway.py']
        path.write_text("raise RuntimeError('changed after verification')",encoding='utf8')
        with patch.object(self.host,'_readonly_dependency_sources',return_value=checked):
            module=self.host._readonly_native_module()
        self.assertEqual(module.PROTOCOL,'owned-common-native-v1-20261031')
        with self.assertRaisesRegex(self.module.BlenderHostError,'readonly_dependency_source_mismatch'):
            self.host._readonly_native_module()

    def test_readonly_host_template_ignores_valid_poisoned_host_pyc(self):
        self.poison_pyc(self.package/'blender_host.py')
        value,namespace=self.execute_template()
        self.assertEqual(value['result']['host_source_sha256'],hashlib.sha256(HOST.read_bytes()).hexdigest())
        self.assertEqual(namespace['_module'].__file__,str(self.package/'blender_host.py'))

    def test_host_compile_uses_same_verified_snapshot_and_reports_actual_digest(self):
        import builtins
        original=builtins.compile;path=self.package/'blender_host.py'
        expected=hashlib.sha256(path.read_bytes()).hexdigest()
        def compile_snapshot(raw,filename,*args,**kwargs):
            code=original(raw,filename,*args,**kwargs)
            if filename==str(path):path.write_text("raise RuntimeError('later host was executed')",encoding='utf8')
            return code
        value,_=self.execute_template(compile=compile_snapshot)
        self.assertEqual(value['result']['host_source_sha256'],expected)
        self.assertNotEqual(hashlib.sha256(path.read_bytes()).hexdigest(),expected)

    def test_readonly_capture_ignores_host_pyc_and_does_not_read_render_helpers(self):
        self.poison_pyc(self.package/'blender_host.py')
        real_open=Path.open
        def open_file(path,*args,**kwargs):
            if path.parent==self.package and path.name in HELPERS:
                raise AssertionError('capture must not read native dependencies')
            return real_open(path,*args,**kwargs)
        for command in ('capture','capture_evidence'):
            with self.subTest(command=command),patch.object(Path,'open',open_file):
                value,_=self.execute_template(command=command)
            self.assertIn('result',value);self.assertNotIn('error',value)

    def test_capture_uses_checked_template_only_inside_readonly_scope(self):
        from verification.test_blender_mcp_host import _reply,_server
        with _server(lambda request:_reply(request),connections=4) as (port,requests):
            host=BlenderMCPHost(self.root,port=port)
            host.capture_scene()
            with host.observation_transaction():
                host.capture_scene();host.capture_evidence()
            host.capture_evidence()
        code=[request[0]['params']['code'] for request in requests]
        self.assertNotIn('compile(',code[0]);self.assertNotIn('compile(',code[3])
        self.assertIn('compile(_source_bytes',code[1]);self.assertIn('compile(_source_bytes',code[2])
        self.assertNotIn('_host._readonly_dependency_sources(',code[1])
        self.assertNotIn('_host._readonly_dependency_sources(',code[2])

    def test_connector_initial_host_read_is_bounded(self):
        (self.package/'blender_host.py').write_bytes(b'x'*(512*1024+1))
        with self.assertRaisesRegex(ValueError,'fixed connector bound'):BlenderMCPHost(self.root)

    def test_connector_snapshot_rejects_changed_host_before_compilation(self):
        connector=BlenderMCPHost(self.root)
        (self.package/'blender_host.py').write_text("raise RuntimeError('changed code ran')",encoding='utf8')
        value,_=self.execute_template(connector)
        self.assertIn('differs from the fixed connector snapshot',value['error']['message'])
        self.assertNotIn('changed code ran',value['error']['message'])
        self.assertFalse(value['error']['mutation_uncertain'])

    def test_only_readonly_template_changes_and_worker_compiles_one_host_snapshot(self):
        baseline=WORK.parent/'before/human_eye_plugin/blender_mcp_host.py'
        def functions(path):
            source=path.read_text(encoding='utf8');tree=ast.parse(source)
            cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='BlenderMCPHost')
            return {n.name:ast.get_source_segment(source,n) for n in cls.body if isinstance(n,ast.FunctionDef)}
        old=functions(baseline);new=functions(ROOT/'human_eye_plugin/blender_mcp_host.py')
        self.assertEqual(old['_code'],new['_code']);self.assertEqual(old['_supervision_code'],new['_supervision_code'])
        source=(ROOT/'human_eye_plugin/blender_worker.py').read_text(encoding='utf8')
        self.assertIn("compile(host_source_bytes,str(source),'exec',dont_inherit=True)",source)
        self.assertIn('module._READONLY_LOADED_HOST_SHA256=hashlib.sha256(host_source_bytes).hexdigest()',source)
        self.assertNotIn('spec.loader.exec_module(module)',source)
        self.assertIn('deadline_module = host._readonly_clock_module()',source)
        self.assertNotIn('deadline_spec.loader.exec_module',source)


if __name__=='__main__':unittest.main()
