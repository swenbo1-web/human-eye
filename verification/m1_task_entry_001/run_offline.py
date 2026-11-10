"""Run only the M1 compact-entry tests through the existing verified loader.

This is an offline test runner, not a server or a replacement product loader.
It does not execute historical runners or write their evidence directories.
"""
import ast
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import traceback
import types
from types import MappingProxyType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEST = HERE / (sys.argv[1] if len(sys.argv) == 2 else 'offline_01')
if DEST.parent.resolve() != HERE.resolve():
    raise ValueError('output must be an immediate new child of this evidence directory')
DEST.mkdir(exist_ok=False)
TEMP = DEST/'tmp'
TEMP.mkdir()
ENGINE = DEST/'engine'
tempfile.tempdir = str(TEMP)
os.environ.update(TMP=str(TEMP), TEMP=str(TEMP), TMPDIR=str(TEMP))
sys.dont_write_bytecode = True
started = datetime.now(timezone.utc).isoformat()
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def save(name, data):
    (DEST/name).write_text(json.dumps(data, indent=2, ensure_ascii=True)+'\n', encoding='utf8')


tree = ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes())
constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    and node.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES')}
names = set(constants['_ROOT_MODULES']) | {path.relative_to(ROOT).as_posix()
    for package in ('human_eye_plugin', 'human_eye_module1_operators')
    for path in (ROOT/package).glob('*.py')}
blobs = {path: (ROOT/path).read_bytes() for path in sorted(names)}
manifest = [dict(path=path, sha256=sha(raw)) for path, raw in blobs.items()]
digest = sha(json.dumps(dict(base_version=constants['BASE_VERSION'],
    implementation_revision=constants['IMPLEMENTATION_REVISION'], files=manifest),
    sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
expected_edits = {
    'human_eye_plugin/live_spatial_mcp.py': '3748b57d63f8a1ebe901b3e2cb555b658ad7673ad7318431155af6a29d9e73d9',
    'human_eye_plugin/production_server.py': '57afb43c9d081da23807fa79ecb32e89b79dd619270d9bebe03facfc8e2fc609',
}
for name, expected in expected_edits.items():
    assert sha(blobs[name]) == expected, ('candidate source changed', name)
for relative, raw in blobs.items():
    path = ENGINE/relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)

# Seal only the original evidence that this suite actually consumes. None of
# these files are rewritten, repaired or used as newly generated output.
sealed = {}
for relative in ('verification/native_plugin_complex_005/C_schemas.stdout.json',
                 'verification/spatial_task_entry_001/dedicated_schema.json'):
    sealed[relative] = (ROOT/relative).read_bytes()
for batch, cell in (('native_plugin_complex_004', '04'),
                    ('native_plugin_complex_005', '03'),
                    ('native_plugin_complex_005', '11'),
                    ('native_plugin_complex_005', '18')):
    owner = ROOT/'verification'/batch/'cells'/cell/'owner'
    for pattern in ('tool_*/ATTEMPT.json', 'tool_*/REQUEST.json'):
        for path in owner.glob(pattern):
            sealed[path.relative_to(ROOT).as_posix()] = path.read_bytes()

loader_path = ENGINE/'human_eye_plugin/verified_source_loader.py'
helper = types.ModuleType('_human_eye_verified_source_bootstrap')
helper.__file__ = str(loader_path)
sys.modules[helper.__name__] = helper
exec(compile(blobs['human_eye_plugin/verified_source_loader.py'], str(loader_path), 'exec',
             dont_inherit=True), helper.__dict__)
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

forbidden_calls = []


def forbidden(*args, **kwargs):
    forbidden_calls.append('external process/network/signal')
    raise AssertionError(forbidden_calls[-1])


test_path = 'verification/m1_task_entry_001/tests/test_task_entry.py'
test_bytes = (ROOT/test_path).read_bytes()
runner_bytes = Path(__file__).read_bytes()
module = types.ModuleType('_m1_compact_task_entry_current')
module.__file__ = str(ROOT/test_path)
module.__package__ = ''
sys.modules[module.__name__] = module
test_filename = 'verified-test:'+sha(test_bytes)+':'+test_path
out = io.StringIO()
err = io.StringIO()
test_log = io.StringIO()
result = None
failure = None
try:
    with ExitStack() as guards, redirect_stdout(out), redirect_stderr(err):
        for name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
            guards.enter_context(patch.object(subprocess, name, side_effect=forbidden))
        for name in ('kill', 'system'):
            guards.enter_context(patch.object(os, name, side_effect=forbidden))
        guards.enter_context(patch.object(socket, 'socket', side_effect=forbidden))
        guards.enter_context(patch.object(socket, 'create_connection', side_effect=forbidden))
        import verification.test_blender_host_contracts as fixtures
        fixtures._module = blender_host
        fixtures.BlenderSceneHost = blender_host.BlenderSceneHost
        fixtures.BlenderHostError = blender_host.BlenderHostError
        exec(compile(test_bytes, test_filename, 'exec', dont_inherit=True), module.__dict__)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.CompactTaskEntryTests)
        result = unittest.TextTestRunner(stream=test_log, verbosity=2).run(suite)
except BaseException:
    failure = traceback.format_exc()
finally:
    (DEST/'STDOUT.txt').write_text(out.getvalue(), encoding='utf8')
    (DEST/'STDERR.txt').write_text(err.getvalue(), encoding='utf8')
    (DEST/'TESTS.txt').write_text(test_log.getvalue(), encoding='utf8')
    if failure:
        (DEST/'RUNNER_EXCEPTION.txt').write_text(failure, encoding='utf8')
    check = guard.verify_loaded()
    product_unchanged = all((ROOT/path).read_bytes() == raw for path, raw in blobs.items())
    historical_unchanged = all((ROOT/path).read_bytes() == raw for path, raw in sealed.items())
    test_unchanged = (ROOT/test_path).read_bytes() == test_bytes
    witnesses = {name: guard._executed[id(loaded)][1] for name, loaded in list(sys.modules.items())
        if guard._owned_name(name) and id(loaded) in guard._executed}
    fixture_hashes = {}
    for name, loaded in list(sys.modules.items()):
        path = getattr(loaded, '__file__', None)
        if name.startswith('verification.') and path and Path(path).is_file():
            relative = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
            fixture_hashes[relative] = sha(Path(path).read_bytes())
    save('EXECUTION_IDENTITY.json', dict(runtime_source_sha256=digest,
        source_count=len(blobs), manifest=manifest,
        expected_edited_files=expected_edits, guard_verify_loaded=check,
        loaded_product_witnesses=witnesses, product_files_unchanged=product_unchanged,
        test=dict(path=test_path, sha256=sha(test_bytes), co_filename=test_filename,
                  bytes=len(test_bytes), unchanged=test_unchanged),
        runner_sha256=sha(runner_bytes), fixture_sha256=fixture_hashes,
        sealed_original_files_sha256={path: sha(raw) for path, raw in sealed.items()},
        sealed_original_files_unchanged=historical_unchanged,
        product_execution='current exact bytes through original verified_source_loader',
        fixture_scope='actual guarded fake-RNA capture + existing packet fixtures; real summarizer/kernel',
        external_dependencies='existing Python/stdlib/third-party/test modules outside product guard'))
    summary = dict(started_utc=started, ended_utc=datetime.now(timezone.utc).isoformat(),
        tests=0 if result is None else result.testsRun,
        failures=[] if result is None else [dict(test=test.id(), traceback=detail)
            for test, detail in result.failures],
        errors=[] if result is None else [dict(test=test.id(), traceback=detail)
            for test, detail in result.errors],
        skipped=[] if result is None else [(test.id(), reason) for test, reason in result.skipped],
        successful=(result is not None and result.wasSuccessful() and failure is None
            and not forbidden_calls and check and product_unchanged and historical_unchanged and test_unchanged),
        runner_exception=failure, external_operation_attempts=forbidden_calls,
        runtime_source_sha256=digest, source_count=len(blobs),
        Blender_sessions=0, models=0, network_or_service_sessions=0)
    save('RESULTS.json', summary)
    save('KERNEL_EVIDENCE.json', getattr(module, 'EVIDENCE', {}))
    print(json.dumps({key: value for key, value in summary.items() if key not in ('failures', 'errors')}, ensure_ascii=True))
    print('failures='+str(len(summary['failures']))+' errors='+str(len(summary['errors'])))
raise SystemExit(0 if summary['successful'] else 1)
