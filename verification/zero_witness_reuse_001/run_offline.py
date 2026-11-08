"""Freeze and execute exact product/test bytes through the original loader."""
import ast
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import traceback
import time
from types import MappingProxyType
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DEST = OUT / sys.argv[1]
DEST.mkdir(exist_ok=False)
ENGINE = DEST / 'engine'
TEMP = DEST / 'tmp'
TEMP.mkdir()
tempfile.tempdir = str(TEMP)
os.environ.update(TMP=str(TEMP), TEMP=str(TEMP), TMPDIR=str(TEMP))
sys.dont_write_bytecode = True
records, test_blobs, outcomes = [], {}, {}
started = datetime.now(timezone.utc).isoformat()
started_ns = time.perf_counter_ns()
sha = lambda b: hashlib.sha256(b).hexdigest()


def save(name, value):
    (DEST/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf8')


tree = ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes())
constants = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
    if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
    and n.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES')}
names = set(constants['_ROOT_MODULES']) | {p.relative_to(ROOT).as_posix()
    for package in ('human_eye_plugin', 'human_eye_module1_operators') for p in (ROOT/package).glob('*.py')}
blobs = {p: (ROOT/p).read_bytes() for p in sorted(names)}
assert len(blobs) == 131
manifest = [dict(path=p, sha256=sha(b)) for p,b in blobs.items()]
digest = sha(json.dumps(dict(base_version=constants['BASE_VERSION'],
    implementation_revision=constants['IMPLEMENTATION_REVISION'], files=manifest),
    sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
for p,b in blobs.items():
    path = ENGINE/p
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b)
loader_path = ENGINE/'human_eye_plugin/verified_source_loader.py'
helper = types.ModuleType('_human_eye_verified_source_bootstrap')
helper.__file__ = str(loader_path)
sys.modules[helper.__name__] = helper
exec(compile(blobs['human_eye_plugin/verified_source_loader.py'], str(loader_path), 'exec', dont_inherit=True), helper.__dict__)
guard = helper.install(ENGINE.resolve(), manifest, sources=MappingProxyType(blobs), bootstrap_module=helper)
package = types.ModuleType('human_eye_plugin')
package.__path__ = [str(ENGINE/'human_eye_plugin')]
guard.allow_namespace(package)
sys.modules[package.__name__] = package
sys.path.insert(0, str(ROOT))
from human_eye_plugin import runtime_identity, blender_host
assert runtime_identity.runtime_identity()['source_sha256'] == digest
blender_host._READONLY_LOADED_HOST_SHA256 = sha(blobs['human_eye_plugin/blender_host.py'])
blender_host._FIRST_FACE_FIXED_GIT = True


def execute_test(name, path):
    raw = (ROOT/path).read_bytes()
    test_blobs[path] = raw
    module = types.ModuleType(name)
    module.__file__ = str(ROOT/path)
    module.__package__ = name.rpartition('.')[0]
    sys.modules[name] = module
    filename = 'verified-test:' + sha(raw) + ':' + path
    exec(compile(raw, filename, 'exec', dont_inherit=True), module.__dict__)
    records.append(dict(module=name, path=path, bytes=len(raw), sha256=sha(raw), co_filename=filename))
    return module


def run_group(label, modules, *, omit=(), only=()):
    stream = io.StringIO()
    suite = unittest.TestSuite()
    def add(test):
        if isinstance(test, unittest.TestSuite):
            for child in test: add(child)
        elif test.id().rsplit('.',1)[-1] not in omit and (not only or test.id().rsplit('.',1)[-1] in only):
            suite.addTest(test)
    for module in modules:
        add(unittest.defaultTestLoader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (DEST/(label+'.txt')).write_text(stream.getvalue(), encoding='utf8')
    outcomes[label] = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        skipped=len(result.skipped), successful=result.wasSuccessful(), omitted_methods=list(omit), selected_methods=list(only))


import subprocess, socket
from unittest.mock import patch
from contextlib import ExitStack
forbidden_calls = []
def forbidden(*args, **kwargs):
    forbidden_calls.append('offline process/network/signal')
    raise AssertionError(forbidden_calls[-1])
guards = ExitStack()
for name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
    guards.enter_context(patch.object(subprocess, name, side_effect=forbidden))
for name in ('kill', 'system'):
    guards.enter_context(patch.object(os, name, side_effect=forbidden))
guards.enter_context(patch.object(socket, 'socket', side_effect=forbidden))
guards.enter_context(patch.object(socket, 'create_connection', side_effect=forbidden))
try:
    import verification.test_blender_host_contracts as fixtures
    fixtures._module = blender_host
    fixtures.BlenderSceneHost = blender_host.BlenderSceneHost
    fixtures.BlenderHostError = blender_host.BlenderHostError
    prior = execute_test('verification.closed_solid_read_001.tests.test_closed_solid', 'verification/closed_solid_read_001/tests/test_closed_solid.py')
    directed = execute_test('_zero_witness_directed', 'verification/zero_witness_reuse_001/tests/test_zero_witness.py')
    run_group('ZERO_WITNESS_DIRECTED', [directed])
    if hasattr(directed, 'EVIDENCE'): save('DIRECTED_EVIDENCE.json', directed.EVIDENCE)
    assert guard.verify_loaded()
finally:
    if sys.exc_info()[1] is not None:
        (DEST/'RUNNER_EXCEPTION.txt').write_text(traceback.format_exc(), encoding='utf8')
    guards.close()
    checked = guard.verify_loaded()
    witnessed = {name: guard._executed[id(module)][1] for name,module in list(sys.modules.items())
        if guard._owned_name(name) and id(module) in guard._executed}
    save('EXECUTION_IDENTITY.json', dict(runtime_source_sha256=digest, source_count=131,
        manifest=manifest, loader_sha256=sha(blobs['human_eye_plugin/verified_source_loader.py']),
        guard_verify_loaded=checked, loaded_product_witnesses=witnessed, executed_tests=records,
        product_execution='original verified_source_loader from frozen exact bytes',
        test_execution='compile exact read bytes with SHA in co_filename; loadTestsFromModule',
        dependency_scope='stdlib/third party/test dependencies outside product guard',
        fixture_scope='actual fake-bpy capture; no synthesized final nearest result',
        omitted_scope='external CLI help subprocess would not share this exact-byte loader'))
    result = dict(started_utc=started, ended_utc=datetime.now(timezone.utc).isoformat(), elapsed_ns=time.perf_counter_ns()-started_ns, groups=outcomes,
        tests_run=sum(r['tests'] for r in outcomes.values()), passed=bool(outcomes) and all(r['successful'] for r in outcomes.values()) and not forbidden_calls, forbidden_attempts=forbidden_calls,
        runtime_source_sha256=digest, source_count=131, Blender_sessions=0, real_RPC=0)
    save('RESULTS.json', result)
    with zipfile.ZipFile(DEST/'EXECUTED_BYTES.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for p,b in blobs.items(): archive.writestr('product/'+p,b)
        for p,b in test_blobs.items(): archive.writestr('tests/'+p,b)
        archive.writestr('runner/run_offline.py', Path(__file__).read_bytes())
    print(json.dumps(result))
raise SystemExit(0 if result['passed'] else 1)
