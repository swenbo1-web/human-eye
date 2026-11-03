"""Origin-check regression and bounded duplicate-resolve accounting.

Every subprocess installs an externally byte-pinned guard over its own source
copy. These are loader protocol tests, not qualification of a real installed
release. Full identity tests enumerate and read every copied runtime source;
they do not promote an ordinary SDK identity into an execution witness.
"""
import ast,hashlib,json,os,subprocess,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
from human_eye_plugin import verified_source_loader as v

ROOT=Path(__file__).resolve().parents[1]


class GuardHarness(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='he-source-guard-')
        self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name).resolve()
        self.root=self.folder/'engine';self.root.mkdir()
        self.files={'human_eye_plugin/__init__.py':b'',
            'human_eye_plugin/direct.py':b"VALUE='verified source'\n",
            'human_eye_plugin/lazy.py':b"from .direct import VALUE\n",
            'human_eye_plugin/verified_source_loader.py':(ROOT/'human_eye_plugin/verified_source_loader.py').read_bytes()}
        for name,blob in self.files.items():
            p=self.root/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_bytes(blob)
        self.manifest=[dict(path=name,sha256=hashlib.sha256(blob).hexdigest()) for name,blob in sorted(self.files.items())]

    def child(self,body,*,root=None,manifest=None):
        root=self.root if root is None else root;manifest=self.manifest if manifest is None else manifest
        helper=root/'human_eye_plugin/verified_source_loader.py';pin=hashlib.sha256(helper.read_bytes()).hexdigest()
        script='\n'.join(['import sys,types,json,hashlib,os,subprocess','from pathlib import Path',
            'root=Path('+repr(str(root))+')','base=Path('+repr(str(self.folder))+')',
            'path=root/"human_eye_plugin/verified_source_loader.py"','blob=path.read_bytes()',
            'assert hashlib.sha256(blob).hexdigest()=='+repr(pin),
            "helper=types.ModuleType('_checked_helper');helper.__file__=str(path)",
            "sys.modules[helper.__name__]=helper;exec(compile(blob,str(path),'exec',dont_inherit=True),helper.__dict__)",
            'manifest=json.loads('+repr(json.dumps(manifest))+')',
            'guard=helper.install(root,manifest,bootstrap_module=helper)',body])
        result=subprocess.run([sys.executable,'-I','-B','-c',script],capture_output=True,timeout=30)
        if result.returncode==77:
            self.skipTest('Owned temporary symlink/junction creation unavailable: '+result.stdout.decode('utf8','replace')[-300:])
        self.assertEqual(result.returncode,0,result.stderr.decode('utf8','replace'))
        self.assertNotIn(b'UNVERIFIED_PYC_EXECUTED',result.stderr)
        return result


class GuardOriginSemanticsTests(GuardHarness):
    def test_owned_legal_and_repeated_checks(self):
        self.child("import human_eye_plugin.direct as m;assert m.VALUE=='verified source';assert guard.verify_loaded();assert guard.verify_loaded()")

    def test_owned_replacement_is_rejected_by_exact_reason(self):
        self.child("""
import human_eye_plugin.direct
sys.modules['human_eye_plugin.direct']=types.ModuleType('human_eye_plugin.direct')
try:guard.verify_loaded()
except helper.SourceBindingError as exc:assert str(exc)=='verified_source_preloaded_module:human_eye_plugin.direct'
else:raise AssertionError('replacement was accepted')
""")

    def test_owned_path_change_is_rechecked(self):
        self.child("""
import human_eye_plugin.direct as m
assert guard.verify_loaded()
m.__file__=str(base/'elsewhere.py')
try:guard.verify_loaded()
except helper.SourceBindingError as exc:assert str(exc)=='verified_source_preloaded_module:human_eye_plugin.direct'
else:raise AssertionError('origin drift was accepted')
""")

    def test_owned_equivalent_relative_origin_keeps_original_semantics(self):
        self.child("""
import human_eye_plugin.direct as m
os.chdir(root);m.__file__='human_eye_plugin/direct.py'
assert guard.verify_loaded()
m.__file__='../elsewhere.py'
try:guard.verify_loaded()
except helper.SourceBindingError as exc:assert str(exc)=='verified_source_preloaded_module:human_eye_plugin.direct'
else:raise AssertionError('relative origin drift was accepted')
""")

    def test_alias_same_bytes_is_valid_and_origin_change_is_rechecked(self):
        self.child("""
p=root/'human_eye_plugin/direct.py';m=types.ModuleType('_verified_alias');m.__file__=str(p)
sys.modules[m.__name__]=m;helper.exec_verified(m,p)
assert m.VALUE=='verified source' and guard.verify_loaded()
m.__file__=str(root/'human_eye_plugin/lazy.py')
try:guard.verify_loaded()
except helper.SourceBindingError as exc:assert str(exc)=='verified_source_preloaded_module:_verified_alias'
else:raise AssertionError('alias origin drift was accepted')
""")

    def test_alias_without_execution_witness_is_rejected(self):
        self.child("""
m=types.ModuleType('_unverified_alias');m.__file__=str(root/'human_eye_plugin/direct.py');sys.modules[m.__name__]=m
try:guard.verify_loaded()
except helper.SourceBindingError as exc:assert str(exc)=='verified_source_preloaded_module:_unverified_alias'
else:raise AssertionError('unwitnessed alias was accepted')
""")

    def test_namespace_normal_path_and_malformed_file_follow_original_branch(self):
        self.child("""
p=types.ModuleType('human_eye_plugin');p.__path__=[str(root/'human_eye_plugin')]
guard.allow_namespace(p);sys.modules[p.__name__]=p;assert guard.verify_loaded()
p.__file__=[]
try:guard.verify_loaded()
except TypeError:pass
else:raise AssertionError('namespace malformed file field bypassed path validation')
""")

    def test_external_symlink_or_junction_target_is_not_cached_between_checks(self):
        result=self.child("""
link=base/'outside_link';external=base/'external';external.mkdir();(external/'direct.py').write_text('# external source\\n')
def create(target):
    try:
        os.symlink(str(target),str(link),target_is_directory=True);return 'symlink'
    except OSError as exc:
        if os.name!='nt':print(str(exc));raise SystemExit(77)
        run=subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(link),str(target)],capture_output=True)
        if run.returncode:print(run.stderr.decode('utf8','replace'));raise SystemExit(77)
        return 'junction'
def remove():
    if link.is_symlink():link.unlink()
    else:os.rmdir(link)
method=create(external)
try:
    m=types.ModuleType('_external_redirect');m.__file__=str(link/'direct.py');sys.modules[m.__name__]=m
    assert guard.verify_loaded()
    remove();method2=create(root/'human_eye_plugin')
    try:guard.verify_loaded()
    except helper.SourceBindingError as exc:assert str(exc)=='verified_source_preloaded_module:_external_redirect'
    else:raise AssertionError('external path redirected inside engine was accepted')
    print(json.dumps(dict(first=method,second=method2,redirect_rejected=True)))
finally:
    if os.path.lexists(link):remove()
""")
        proof=json.loads(result.stdout);self.assertTrue(proof['redirect_rejected'])
        self.assertIn(proof['first'],('symlink','junction'));self.assertIn(proof['second'],('symlink','junction'))


class GuardFullRuntimeFreshnessTests(GuardHarness):
    def full_copy(self):
        root=self.folder/'full_engine';root.mkdir()
        tree=ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes())
        roots=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_ROOT_MODULES' for t in n.targets)))
        names=set(roots)
        for package in ('human_eye_plugin','human_eye_module1_operators'):
            names.update(package+'/'+p.name for p in (ROOT/package).glob('*.py'))
        manifest=[]
        for name in sorted(names):
            blob=(ROOT/name).read_bytes();p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(blob)
            manifest.append(dict(path=name,sha256=hashlib.sha256(blob).hexdigest()))
        (root/'pyproject.toml').write_text('# QA source copy; guard is independently installed\n')
        return root,manifest

    def runtime_child(self,body):
        root,manifest=self.full_copy()
        prefix="""
p=types.ModuleType('human_eye_plugin');p.__path__=[str(root/'human_eye_plugin')]
guard.allow_namespace(p);sys.modules[p.__name__]=p
from human_eye_plugin import runtime_identity as identity
assert helper.current_guard(root) is guard and guard.verify_loaded()
assert identity.check_source_drift()['compatible']
"""
        return self.child(prefix+body,root=root,manifest=manifest)

    def test_every_runtime_source_read_on_every_complete_check(self):
        self.runtime_child("""
from unittest import mock
original=Path.read_bytes;reads=[];expected={row['path'] for row in manifest}
def reading(path):
    if path.is_relative_to(root) and path.relative_to(root).as_posix() in expected:reads.append(path.relative_to(root).as_posix())
    return original(path)
with mock.patch.object(Path,'read_bytes',reading):
    for _ in range(2):
        reads.clear();result=identity.check_source_drift()
        assert result['compatible'] and result['check_complete'] and result['status']=='unchanged'
        assert set(reads)==expected and len(reads)==len(expected),(len(reads),len(expected))
""")

    def test_same_size_same_mtime_rewrite_is_detected_and_not_refreshed(self):
        self.runtime_child("""
path=root/'human_eye_plugin/task_intent.py';old=path.read_bytes();stat=path.stat()
changed=bytes([old[0]^1])+old[1:];path.write_bytes(changed);os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
assert path.stat().st_size==stat.st_size and path.stat().st_mtime_ns==stat.st_mtime_ns
for _ in range(2):
    result=identity.check_source_drift()
    assert result['compatible'] is False and result['status']=='changed' and result['check_complete'] is True
    assert result['reasons']==['runtime_source_changed_restart_required'] and result['changed_files']==['human_eye_plugin/task_intent.py']
path.write_bytes(old);os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns));assert identity.check_source_drift()['compatible']
""")

    def test_addition_and_removal_are_fresh_and_have_exact_reasons(self):
        self.runtime_child("""
new=root/'human_eye_plugin/guard_extra_source.py';new.write_text('# added\\n')
result=identity.check_source_drift()
assert result['compatible'] is False and result['reasons']==['runtime_source_changed_restart_required']
assert result['added_files']==['human_eye_plugin/guard_extra_source.py'] and result['removed_files']==[]
new.unlink();assert identity.check_source_drift()['compatible']
old=root/'human_eye_plugin/task_intent.py';old.unlink();result=identity.check_source_drift()
assert result['compatible'] is False and result['check_complete'] is True and result['reasons']==['runtime_source_changed_restart_required']
assert result['removed_files']==['human_eye_plugin/task_intent.py']
""")

    def test_full_source_read_failure_is_unavailable_then_recovers_without_cache(self):
        self.runtime_child("""
from unittest import mock
original=Path.read_bytes;target=root/'human_eye_plugin/task_intent.py';failures=[]
def reading(path):
    if path==target:failures.append(str(path));raise PermissionError('QA source inaccessible')
    return original(path)
with mock.patch.object(Path,'read_bytes',reading):
    result=identity.check_source_drift()
assert failures==[str(target)] and result['compatible'] is False and result['check_complete'] is False
assert result['status']=='unavailable' and result['reasons']==['runtime_source_check_failed'] and result['error'].startswith('PermissionError:')
assert identity.check_source_drift()['compatible']
""")


class GuardResolveAccountingTests(GuardHarness):
    def test_owned_classification_removed_final_origins_and_aliases_still_fresh(self):
        guard=v.SourceGuard(self.root,v.capture(self.root,self.manifest));path=self.root/'human_eye_plugin/direct.py'
        modules={}
        # A synthetic 62-module executed set mirrors the measured owned count.
        # Each witness below comes from actual compilation of pinned tiny bytes;
        # it is not a JSON flag or an admission claim for a production release.
        for i in range(62):
            name='human_eye_plugin.loaded_%02d'%i;module=types.ModuleType(name);module.__file__=str(path)
            guard.exec_path(module,path);modules[name]=module
        alias=types.ModuleType('_verified_alias');alias.__file__=str(path);guard.exec_path(alias,path);modules[alias.__name__]=alias
        external=types.ModuleType('_outside');external.__file__=str(self.folder/'outside.py');modules[external.__name__]=external
        namespace=types.ModuleType('human_eye_plugin');namespace.__path__=[str(self.root/'human_eye_plugin')]
        guard.allow_namespace(namespace);modules[namespace.__name__]=namespace
        original=Path.resolve;calls=[]
        def resolving(p,*args,**kwargs):calls.append(str(p));return original(p,*args,**kwargs)
        with mock.patch.object(v,'sys',types.SimpleNamespace(modules=modules)),mock.patch.object(Path,'resolve',resolving):
            for _ in range(2):
                calls.clear();self.assertTrue(guard.verify_loaded())
                # 62 final owned origins + 2 original alias checks + 1 external
                # classification; namespace has no __file__. Repeat must read
                # every origin again, with no success cached between calls.
                self.assertEqual(calls,[str(path)]*64+[external.__file__])


if __name__=='__main__':unittest.main()
