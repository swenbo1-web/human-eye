"""Finite, no-network qualification of local transverse evidence preservation.

Each invocation copies exactly 137 sources and uses the product's original
verified loader. Baseline bytes come from Git 107641ec, not an edited old runner.
This is guarded source qualification, not an installed/default runtime test.
"""
from __future__ import annotations

import argparse
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
import tarfile
import tempfile
import traceback
import types
from types import MappingProxyType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = '107641ec19919d56aa843c1949261590fc338148'
BASE_SHA = '7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'
ALLOWED_EDITS = {'human_eye_plugin/task_query.py',
                 'human_eye_plugin/surface_geometry.py',
                 'human_eye_plugin/live_spatial_mcp.py'}
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def git_bytes(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=30, shell=False).stdout


def canonical(blobs):
    tree = ast.parse(blobs['human_eye_plugin/runtime_identity.py'])
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION')}
    manifest = [dict(path=path, sha256=sha(raw)) for path, raw in sorted(blobs.items())]
    digest = sha(json.dumps(dict(base_version=constants['BASE_VERSION'],
        implementation_revision=constants['IMPLEMENTATION_REVISION'], files=manifest),
        sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    return digest, manifest


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True,
                               allow_nan=False)+'\n', encoding='utf8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--role', required=True, choices=('baseline', 'candidate'))
    parser.add_argument('--expected-source-sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    dest = HERE / args.output
    if dest.parent.resolve() != HERE.resolve():
        raise ValueError('output must be a new direct child')
    dest.mkdir(exist_ok=False)
    temp = dest/'tmp'
    temp.mkdir()
    engine = dest/'engine'
    tempfile.tempdir = str(temp)
    os.environ.update(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp))
    sys.dont_write_bytecode = True
    started = datetime.now(timezone.utc).isoformat()

    identity_ast = ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes())
    root_modules = next(ast.literal_eval(node.value) for node in identity_ast.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == '_ROOT_MODULES')
    names = set(root_modules) | {path.relative_to(ROOT).as_posix()
        for package in ('human_eye_plugin', 'human_eye_module1_operators')
        for path in (ROOT/package).glob('*.py')}
    assert len(names) == 137
    raw = git_bytes('archive', '--format=tar', BASE, '--', *sorted(names))
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        baseline = {member.name: archive.extractfile(member).read()
            for member in archive.getmembers() if member.isfile()}
    assert set(baseline) == names
    assert canonical(baseline)[0] == BASE_SHA
    checkout = {name: (ROOT/name).read_bytes() for name in sorted(names)}
    changed = [name for name in sorted(names) if checkout[name] != baseline[name]]
    assert set(changed) <= ALLOWED_EDITS, changed
    blobs = baseline if args.role == 'baseline' else checkout
    digest, manifest = canonical(blobs)
    assert digest == args.expected_source_sha256, (digest, args.expected_source_sha256)
    for relative, data in blobs.items():
        path = engine/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    # Existing finite evidence is read-only; verify it remains byte-identical.
    sealed = {}
    for relative in ('verification/native_plugin_complex_005/C_schemas.stdout.json',
                     'verification/spatial_task_entry_001/dedicated_schema.json'):
        sealed[relative] = (ROOT/relative).read_bytes()
    for batch, cell in (('native_plugin_complex_004', '04'),
                        ('native_plugin_complex_005', '03'),
                        ('native_plugin_complex_005', '11'),
                        ('native_plugin_complex_005', '18')):
        for pattern in ('tool_*/ATTEMPT.json', 'tool_*/REQUEST.json'):
            for path in (ROOT/'verification'/batch/'cells'/cell/'owner').glob(pattern):
                sealed[path.relative_to(ROOT).as_posix()] = path.read_bytes()

    loader = 'human_eye_plugin/verified_source_loader.py'
    helper = types.ModuleType('_human_eye_verified_source_bootstrap')
    helper.__file__ = str(engine/loader)
    sys.modules[helper.__name__] = helper
    exec(compile(blobs[loader], str(engine/loader), 'exec', dont_inherit=True), helper.__dict__)
    guard = helper.install(engine.resolve(), manifest,
        sources=MappingProxyType(blobs), bootstrap_module=helper)
    package = types.ModuleType('human_eye_plugin')
    package.__path__ = [str(engine/'human_eye_plugin')]
    guard.allow_namespace(package)
    sys.modules[package.__name__] = package
    sys.path.insert(0, str(ROOT))
    from human_eye_plugin import runtime_identity, blender_host
    assert runtime_identity.runtime_identity()['source_sha256'] == digest
    blender_host._READONLY_LOADED_HOST_SHA256 = sha(blobs['human_eye_plugin/blender_host.py'])
    blender_host._FIRST_FACE_FIXED_GIT = True

    operations = []
    def forbidden(*args, **kwargs):
        operations.append('external process/network/signal')
        raise AssertionError(operations[-1])

    outputs = {}
    loaded_tests = {}
    stdout, stderr, log = io.StringIO(), io.StringIO(), io.StringIO()
    result, error = None, None
    try:
        with ExitStack() as guards, redirect_stdout(stdout), redirect_stderr(stderr):
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
            suite = unittest.TestSuite()
            selected = [
                ('verification/closed_solid_read_001/tests/test_closed_solid.py', 'ClosedSolidMathTests'),
                ('verification/closed_solid_read_001/tests/test_closed_solid.py', 'ClosedSolidTaskTests'),
                ('verification/m1_task_entry_001/tests/test_task_entry.py', 'CompactTaskEntryTests'),
                ('verification/m4_local_relation_evidence_001/tests/test_local_relation_evidence.py', 'LocalRelationEvidenceTests'),
            ]
            modules = []
            for index, (relative, classname) in enumerate(selected):
                raw_test = (ROOT/relative).read_bytes()
                name = '_local_relation_test_'+str(index)
                module = types.ModuleType(name)
                module.__file__ = str(ROOT/relative)
                module.__package__ = ''
                module.PRODUCT_ROLE = args.role
                module.RUNTIME_SOURCE_SHA256 = digest
                sys.modules[name] = module
                filename = 'verified-test:'+sha(raw_test)+':'+relative
                exec(compile(raw_test, filename, 'exec', dont_inherit=True), module.__dict__)
                suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(getattr(module, classname)))
                loaded_tests[relative] = dict(sha256=sha(raw_test), co_filename=filename)
                modules.append((relative+':'+classname, module))
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
            outputs = {relative: getattr(module, 'EVIDENCE', {}) for relative, module in modules}
    except BaseException:
        error = traceback.format_exc()

    for name, content in (('STDOUT.txt', stdout.getvalue()), ('STDERR.txt', stderr.getvalue()),
                          ('TESTS.txt', log.getvalue())):
        (dest/name).write_text(content, encoding='utf8')
    if error:
        (dest/'RUNNER_EXCEPTION.txt').write_text(error, encoding='utf8')
    loaded_check = guard.verify_loaded()
    checkout_unchanged = all((ROOT/path).read_bytes() == raw for path, raw in checkout.items())
    sealed_unchanged = all((ROOT/path).read_bytes() == raw for path, raw in sealed.items())
    tests_unchanged = all(sha((ROOT/path).read_bytes()) == row['sha256'] for path, row in loaded_tests.items())
    witnesses = {name: guard._executed[id(module)][1] for name, module in list(sys.modules.items())
        if guard._owned_name(name) and id(module) in guard._executed}
    fixture_hashes = {}
    for name, module in list(sys.modules.items()):
        path = getattr(module, '__file__', None)
        if name.startswith('verification.') and path and Path(path).is_file():
            relative = Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
            fixture_hashes[relative] = sha(Path(path).read_bytes())
    summary = dict(role=args.role, started_utc=started,
        ended_utc=datetime.now(timezone.utc).isoformat(),
        tests=0 if result is None else result.testsRun,
        failures=[] if result is None else [dict(test=t.id(), traceback=e) for t, e in result.failures],
        errors=[] if result is None else [dict(test=t.id(), traceback=e) for t, e in result.errors],
        skipped=[] if result is None else [(t.id(), why) for t, why in result.skipped],
        successful=bool(result and result.wasSuccessful() and not error and not operations
            and loaded_check and checkout_unchanged and sealed_unchanged and tests_unchanged),
        runner_exception=error, external_operation_attempts=operations,
        runtime_source_sha256=digest, source_count=len(blobs),
        model_consumers=0, Blender_sessions=0, network_sessions=0)
    save(dest/'RESULTS.json', summary)
    save(dest/'EVIDENCE.json', outputs)
    save(dest/'EXECUTION_IDENTITY.json', dict(role=args.role, baseline_commit=BASE,
        baseline_source_sha256=BASE_SHA, runtime_source_sha256=digest, manifest=manifest,
        candidate_changed_paths=changed, source_count=len(blobs),
        guard_verify_loaded=loaded_check, loaded_product_witnesses=witnesses,
        checkout_files_unchanged=checkout_unchanged, loaded_tests=loaded_tests,
        loaded_tests_unchanged=tests_unchanged, fixture_sha256=fixture_hashes,
        original_read_evidence_sha256={name:sha(raw) for name, raw in sealed.items()},
        original_read_evidence_unchanged=sealed_unchanged,
        runner_sha256=sha(Path(__file__).read_bytes()),
        source_kind=runtime_identity.runtime_identity()['source_kind'],
        deliberately_not_selected=[],
        scope='guarded physical source snapshot; fake RNA + actual kernels; not installed or Blender qualification'))
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if summary['successful'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
