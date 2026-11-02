"""Real subprocess probes of same-byte imports, pyc, lazy loads and workers."""
import hashlib,importlib.util,json,os,py_compile,struct,subprocess,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
from human_eye_plugin import verified_source_loader as v

ROOT=Path(__file__).resolve().parents[1]


def stale_pyc(path,extra="\nraise RuntimeError('UNVERIFIED_PYC_EXECUTED')\n"):
    original=path.read_bytes();stat=path.stat();path.write_bytes(original+extra.encode())
    cache=Path(py_compile.compile(str(path),doraise=True));raw=cache.read_bytes()
    cache.write_bytes(raw[:8]+struct.pack('<II',int(stat.st_mtime)&0xffffffff,len(original))+raw[16:])
    path.write_bytes(original);os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns));return cache


class VerifiedSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.files={'human_eye_plugin/__init__.py':b'',
            'human_eye_plugin/direct.py':b"VALUE='verified source'\n",
            'human_eye_plugin/lazy.py':b"from .direct import VALUE\n",
            'human_eye_plugin/verified_source_loader.py':(ROOT/'human_eye_plugin/verified_source_loader.py').read_bytes(),
            'human_eye_plugin/worker.py':b"import human_eye_plugin.lazy as child\nimport json,sys\nprint(json.dumps(dict(value=child.VALUE,args=sys.argv[sys.argv.index('--')+1:])))\n"}
        for name,blob in self.files.items():p=self.root/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_bytes(blob)
        self.manifest=[dict(path=name,sha256=hashlib.sha256(blob).hexdigest()) for name,blob in sorted(self.files.items())]
    def tearDown(self):self.temp.cleanup()
    def run_child(self,body,*,before='',success=True):
        helper=self.root/'human_eye_plugin/verified_source_loader.py'
        script='\n'.join(['import sys,types,json,hashlib','from pathlib import Path',
            'root=Path('+repr(str(self.root))+')','path=Path('+repr(str(helper))+')',
            "blob=path.read_bytes();helper=types.ModuleType('_checked_helper');helper.__file__=str(path)",
            "sys.modules[helper.__name__]=helper;exec(compile(blob,str(path),'exec'),helper.__dict__)",before,
            'guard=helper.install(root,json.loads('+repr(json.dumps(self.manifest))+'),bootstrap_module=helper)',body])
        result=subprocess.run([sys.executable,'-I','-B','-c',script],capture_output=True,timeout=20)
        if success:self.assertEqual(result.returncode,0,result.stderr.decode('utf8','replace'))
        else:self.assertNotEqual(result.returncode,0,result.stdout.decode('utf8','replace'))
        self.assertNotIn(b'UNVERIFIED_PYC_EXECUTED',result.stderr)
        return result
    def test_cached_package_init_never_executes(self):
        stale_pyc(self.root/'human_eye_plugin/__init__.py')
        result=self.run_child("import human_eye_plugin.direct as m;assert m.VALUE=='verified source';assert guard.verify_loaded()")
    def test_cached_eager_dependency_never_executes(self):
        stale_pyc(self.root/'human_eye_plugin/direct.py')
        self.run_child("import human_eye_plugin.lazy as m;assert m.VALUE=='verified source';assert guard.verify_loaded()")
    def test_cached_late_dependency_never_executes(self):
        stale_pyc(self.root/'human_eye_plugin/lazy.py')
        self.run_child("import human_eye_plugin;import importlib;m=importlib.import_module('human_eye_plugin.lazy');assert m.VALUE=='verified source'")
    def test_loader_own_cached_bytecode_is_not_used(self):
        stale_pyc(self.root/'human_eye_plugin/verified_source_loader.py')
        self.run_child("import human_eye_plugin.verified_source_loader as m;assert m.current_guard(root) is guard;assert guard.verify_loaded()")
    def test_source_change_before_late_import_rejected(self):
        result=self.run_child("(root/'human_eye_plugin/lazy.py').write_text('VALUE=0');import human_eye_plugin.lazy",success=False)
        self.assertIn(b'verified_source_changed:human_eye_plugin/lazy.py',result.stderr)
    def test_unlisted_module_rejected_even_if_file_exists(self):
        (self.root/'human_eye_plugin/unlisted.py').write_text("raise RuntimeError('UNVERIFIED_PYC_EXECUTED')")
        result=self.run_child('import human_eye_plugin.unlisted',success=False)
        self.assertIn(b'verified_source_unlisted_module',result.stderr)
    def test_uncontrolled_preloaded_package_rejected(self):
        result=self.run_child('',before="sys.path.insert(0,str(root));import human_eye_plugin",success=False)
        self.assertIn(b'verified_source_preloaded_module:human_eye_plugin',result.stderr)
    def test_same_root_reinstall_accepts_only_same_generation(self):
        self.run_child('assert helper.install(root,'+repr(self.manifest)+') is guard')
    def test_replacing_loaded_module_rejected(self):
        result=self.run_child("import human_eye_plugin.direct;sys.modules['human_eye_plugin.direct']=types.ModuleType('human_eye_plugin.direct');guard.verify_loaded()",success=False)
        self.assertIn(b'verified_source_preloaded_module',result.stderr)
    def test_worker_entire_chain_ignores_valid_timestamp_pyc(self):
        for name in ('worker.py','lazy.py','direct.py','verified_source_loader.py'):stale_pyc(self.root/'human_eye_plugin'/name)
        expression=v.worker_expression(self.root,self.root/'human_eye_plugin/worker.py',self.manifest)
        result=subprocess.run([sys.executable,'-I','-B','-c',expression,'--','fixed','arguments'],capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr.decode());self.assertEqual(json.loads(result.stdout),dict(value='verified source',args=['fixed','arguments']))
    def test_worker_source_changed_after_parent_snapshot_refused(self):
        expression=v.worker_expression(self.root,self.root/'human_eye_plugin/worker.py',self.manifest)
        (self.root/'human_eye_plugin/worker.py').write_bytes(b"raise RuntimeError('UNVERIFIED_PYC_EXECUTED')")
        result=subprocess.run([sys.executable,'-I','-B','-c',expression],capture_output=True,timeout=20)
        self.assertNotEqual(result.returncode,0);self.assertIn(b'verified_source_changed',result.stderr);self.assertNotIn(b'UNVERIFIED_PYC_EXECUTED',result.stderr)
    def test_worker_loader_changed_after_parent_snapshot_refused(self):
        expression=v.worker_expression(self.root,self.root/'human_eye_plugin/worker.py',self.manifest)
        (self.root/'human_eye_plugin/verified_source_loader.py').write_text("raise RuntimeError('UNVERIFIED_PYC_EXECUTED')")
        result=subprocess.run([sys.executable,'-I','-B','-c',expression],capture_output=True,timeout=20)
        self.assertNotEqual(result.returncode,0);self.assertIn(b'verified_source_worker_loader_pin',result.stderr);self.assertNotIn(b'UNVERIFIED_PYC_EXECUTED',result.stderr)
    def test_namespace_requires_explicit_nonexecuting_witness(self):
        self.run_child("p=types.ModuleType('human_eye_plugin');p.__path__=[str(root/'human_eye_plugin')];guard.allow_namespace(p);sys.modules[p.__name__]=p;import human_eye_plugin.lazy;assert guard.verify_loaded()")
    def test_nonengine_imports_still_use_normal_importers(self):
        self.run_child('import fractions,decimal;assert str(fractions.Fraction(1,3))=="1/3";assert guard.find_spec("numpy") is None')
    def test_alias_exec_compiles_checked_blob(self):
        self.run_child("path=root/'human_eye_plugin/direct.py';m=types.ModuleType('_alias');m.__file__=str(path);sys.modules[m.__name__]=m;helper.exec_verified(m,path);assert m.VALUE=='verified source';assert guard.verify_loaded()")
    def test_alias_cannot_supply_another_payload(self):
        result=self.run_child("path=root/'human_eye_plugin/direct.py';m=types.ModuleType('_alias');m.__file__=str(path);helper.exec_verified(m,path,b'VALUE=1')",success=False)
        self.assertIn(b'verified_source_changed',result.stderr)
    def test_exec_compiles_original_snapshot_after_single_read(self):
        sources=v.capture(self.root,self.manifest);guard=v.SourceGuard(self.root,sources);p=self.root/'human_eye_plugin/direct.py';module=types.ModuleType('_snapshot');module.__file__=str(p)
        original=v._read
        def mutate(path):
            result=original(path);path.write_bytes(b"VALUE='changed'\n");return result
        with mock.patch.object(v,'_read',side_effect=mutate):guard.exec_path(module,p)
        self.assertEqual(module.VALUE,'verified source')
    def test_manifest_traversal_duplicate_and_wrong_digest_rejected(self):
        cases=[[dict(path='../escape.py',sha256='0'*64)],self.manifest+[self.manifest[0]],
            [dict(self.manifest[0],sha256='0'*64)]]
        for manifest in cases:
            with self.subTest(manifest=manifest),self.assertRaises(v.SourceBindingError):v.capture(self.root,manifest)
    def test_missing_worker_or_helper_not_allowed(self):
        for worker,manifest in [(self.root/'not-listed.py',self.manifest),(self.root/'human_eye_plugin/worker.py',[r for r in self.manifest if not r['path'].endswith('verified_source_loader.py')])]:
            with self.subTest(worker=worker),self.assertRaises(v.SourceBindingError):v.worker_expression(self.root,worker,manifest)
    def test_guard_payload_cannot_be_mutated(self):
        guard=v.SourceGuard(self.root,v.capture(self.root,self.manifest))
        with self.assertRaises(TypeError):guard.sources['human_eye_plugin/direct.py']=b'VALUE=0'


if __name__=='__main__':unittest.main()
