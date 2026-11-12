"""One guarded source snapshot and bounded directory/legacy offline checks."""

import argparse
import ast
from contextlib import ExitStack, redirect_stderr, redirect_stdout
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


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--expected-source-sha256', required=True)
    arguments = parser.parse_args()
    destination = HERE / arguments.output
    assert destination.parent.resolve() == HERE.resolve() and destination.name not in ('.', '..')
    destination.mkdir(exist_ok=False)
    tree = ast.parse((ROOT / 'human_eye_plugin/runtime_identity.py').read_bytes())
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in ('_ROOT_MODULES', 'BASE_VERSION', 'IMPLEMENTATION_REVISION')}
    paths = set(constants['_ROOT_MODULES']) | {path.relative_to(ROOT).as_posix()
        for package in ('human_eye_plugin', 'human_eye_module1_operators') for path in (ROOT / package).glob('*.py')}
    blobs = {name: (ROOT / name).read_bytes() for name in sorted(paths)}
    manifest = [{'path': name, 'sha256': sha(raw)} for name, raw in blobs.items()]
    digest = sha(json.dumps({'base_version': constants['BASE_VERSION'],
        'implementation_revision': constants['IMPLEMENTATION_REVISION'], 'files': manifest},
        sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    assert len(blobs) == 137 and digest == arguments.expected_source_sha256
    engine = destination / 'e'
    for name, raw in blobs.items():
        path = engine / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    temporary = destination / 't'
    temporary.mkdir()
    assert temporary.resolve().is_relative_to(destination.resolve())
    tempfile.tempdir = str(temporary)
    os.environ.update(TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    sys.dont_write_bytecode = True
    loader = 'human_eye_plugin/verified_source_loader.py'
    helper = types.ModuleType('_human_eye_verified_source_bootstrap')
    helper.__file__ = str(engine / loader)
    sys.modules[helper.__name__] = helper
    exec(compile(blobs[loader], helper.__file__, 'exec', dont_inherit=True), helper.__dict__)
    guard = helper.install(engine.resolve(), manifest, sources=MappingProxyType(blobs), bootstrap_module=helper)
    package = types.ModuleType('human_eye_plugin')
    package.__path__ = [str(engine / 'human_eye_plugin')]
    guard.allow_namespace(package)
    sys.modules[package.__name__] = package
    sys.path.insert(0, str(ROOT))
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append('external process/socket/signal')
        raise AssertionError(attempts[-1])

    result, error, modules, tested = None, None, [], {}
    stdout, stderr, log = io.StringIO(), io.StringIO(), io.StringIO()
    try:
        with ExitStack() as stack, redirect_stdout(stdout), redirect_stderr(stderr):
            for name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
                stack.enter_context(patch.object(subprocess, name, side_effect=forbidden))
            for name in ('socket', 'create_connection'):
                stack.enter_context(patch.object(socket, name, side_effect=forbidden))
            for name in ('system', 'kill'):
                stack.enter_context(patch.object(os, name, side_effect=forbidden))
            from human_eye_plugin.runtime_identity import runtime_identity
            identity = runtime_identity()
            assert identity['source_sha256'] == digest and identity['source_kind'] == 'unregistered_runtime'
            selected = [
                ('verification/m2_tight_directory_001/correctness/test_directory.py', 'DirectoryTests', None),
                ('verification/test_selected_task_query.py', 'SelectedTaskQueryTests', [
                    'test_service_uses_one_selected_capture_and_original_facts',
                    'test_duplicate_selectors_capture_one_and_preserve_pair_unknown']),
                ('verification/arch_read_context_001/test_resident_task.py', 'ResidentTaskTests', [
                    'test_same_token_same_query_warm_skips_normalize_solver_and_action_io']),
                ('verification/m1_task_entry_001/tests/test_task_entry.py', 'CompactTaskEntryTests', [
                    'test_new_minimum_and_name_id_results_equal_legacy_full_facts']),
            ]
            suite = unittest.TestSuite()
            for index, (relative, classname, methods) in enumerate(selected):
                raw = (ROOT / relative).read_bytes()
                module = types.ModuleType('_directory_unit_' + str(index))
                module.__file__ = str(ROOT / relative)
                module.RUNTIME_SOURCE_SHA256 = digest
                sys.modules[module.__name__] = module
                exec(compile(raw, str(ROOT / relative), 'exec', dont_inherit=True), module.__dict__)
                case = getattr(module, classname)
                suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case) if methods is None else [case(name) for name in methods])
                modules.append(module)
                tested[relative] = sha(raw)
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    except BaseException:
        error = traceback.format_exc()
    for name, value in (('STDOUT.txt', stdout.getvalue()), ('STDERR.txt', stderr.getvalue()), ('TESTS.txt', log.getvalue())):
        (destination / name).write_text(value, encoding='utf8', newline='\n')
    if error:
        (destination / 'RUNNER_EXCEPTION.txt').write_text(error, encoding='utf8', newline='\n')
    loaded = guard.verify_loaded()
    source_unchanged = all((ROOT / name).read_bytes() == raw and (engine / name).read_bytes() == raw for name, raw in blobs.items())
    tests_unchanged = all(sha((ROOT / name).read_bytes()) == value for name, value in tested.items())
    summary = {'passed': bool(result and result.wasSuccessful() and not error and not attempts and loaded and source_unchanged and tests_unchanged),
        'test_methods': 0 if result is None else result.testsRun,
        'failures': [] if result is None else [{'test': test.id(), 'traceback': value} for test, value in result.failures],
        'errors': [] if result is None else [{'test': test.id(), 'traceback': value} for test, value in result.errors],
        'runner_exception': error, 'external_operation_attempts': attempts,
        'runtime_source_sha256': digest, 'source_count': len(blobs), 'guard_verified': loaded,
        'source_kind': 'unregistered_runtime', 'sources_unchanged': source_unchanged, 'tests_unchanged': tests_unchanged,
        'model_consumers': 0, 'Blender_sessions': 0, 'performance_samples': 0}
    save(destination / 'RESULTS.json', summary)
    save(destination / 'EVIDENCE.json', {module.__name__: getattr(module, 'EVIDENCE', {}) for module in modules})
    save(destination / 'EXECUTION_IDENTITY.json', {'manifest': manifest, 'runtime_source_sha256': digest,
        'tests_sha256': tested, 'runner_sha256': sha(Path(__file__).read_bytes()),
        'scope': 'guarded candidate source plus existing RNA fixtures; this is not installed or Blender qualification'})
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
