"""Bounded six-file original regression against one physical guarded source."""

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
TEST_FILES = ('test_surface_proximity_001.py','test_surface_proximity_pruning_001.py',
    'test_surface_geometry.py','test_original_triangle_witness.py','test_task_query.py','test_selected_task_query.py')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-root',required=True,type=Path)
    parser.add_argument('--expected-source-sha256',required=True)
    parser.add_argument('--role',required=True,choices=('baseline','candidate'))
    parser.add_argument('--output',required=True)
    parser.add_argument('--migrations',action='store_true')
    args = parser.parse_args()
    output = HERE/args.output
    assert output.resolve().parent == HERE.resolve()
    output.mkdir(exist_ok=False)
    engine = args.engine_root.resolve()
    tree = ast.parse((engine/'human_eye_plugin/runtime_identity.py').read_bytes())
    constants = {node.targets[0].id:ast.literal_eval(node.value) for node in tree.body if
        isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and
        node.targets[0].id in ('_ROOT_MODULES','BASE_VERSION','IMPLEMENTATION_REVISION')}
    names = set(constants['_ROOT_MODULES']) | {p.relative_to(engine).as_posix() for package in
        ('human_eye_plugin','human_eye_module1_operators') for p in (engine/package).glob('*.py')}
    blobs = {name:(engine/name).read_bytes() for name in sorted(names)}
    manifest = [{'path':name,'sha256':sha(raw)} for name,raw in blobs.items()]
    canonical = sha(json.dumps({'base_version':constants['BASE_VERSION'],
        'implementation_revision':constants['IMPLEMENTATION_REVISION'],'files':manifest},
        sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    assert len(blobs)==137 and canonical==args.expected_source_sha256
    helper = types.ModuleType('_human_eye_verified_source_bootstrap')
    helper.__file__ = str(engine/'human_eye_plugin/verified_source_loader.py')
    sys.modules[helper.__name__] = helper
    exec(compile(blobs['human_eye_plugin/verified_source_loader.py'],helper.__file__,'exec',dont_inherit=True),helper.__dict__)
    guard = helper.install(engine,manifest,sources=MappingProxyType(blobs),bootstrap_module=helper)
    package = types.ModuleType('human_eye_plugin')
    package.__path__ = [str(engine/'human_eye_plugin')]
    guard.allow_namespace(package)
    sys.modules[package.__name__] = package
    sys.path.insert(0,str(ROOT))
    sys.dont_write_bytecode = True
    temporary = output/'tmp'
    temporary.mkdir()
    tempfile.tempdir = str(temporary.resolve())
    os.environ.update(TEMP=str(temporary.resolve()),TMP=str(temporary.resolve()),TMPDIR=str(temporary.resolve()))
    attempts, local_connections, source_tests, executed = [], [], {}, []

    def forbidden(*unused,**kwargs):
        attempts.append('external process/socket/signal')
        raise AssertionError(attempts[-1])

    original_socket = socket.socket

    class LoopbackSocket(original_socket):
        def bind(self,address):
            if address[0] not in ('127.0.0.1','::1','localhost'):
                return forbidden()
            local_connections.append({'operation':'bind','address':address})
            return super().bind(address)

        def connect(self,address):
            if address[0] not in ('127.0.0.1','::1','localhost'):
                return forbidden()
            local_connections.append({'operation':'connect','address':address})
            return super().connect(address)

        def connect_ex(self,address):
            if address[0] not in ('127.0.0.1','::1','localhost'):
                return forbidden()
            local_connections.append({'operation':'connect_ex','address':address})
            return super().connect_ex(address)

    class RecordedResult(unittest.TextTestResult):
        def startTest(self,test):
            executed.append(test.id())
            super().startTest(test)

    stdout,stderr,log = io.StringIO(),io.StringIO(),io.StringIO()
    result,error,identity = None,None,None
    try:
        with ExitStack() as stack,redirect_stdout(stdout),redirect_stderr(stderr):
            for name in ('Popen','run','call','check_call','check_output'):
                stack.enter_context(patch.object(subprocess,name,side_effect=forbidden))
            stack.enter_context(patch.object(socket,'socket',LoopbackSocket))
            for name in ('system','kill'):
                stack.enter_context(patch.object(os,name,side_effect=forbidden))
            from human_eye_plugin.runtime_identity import runtime_identity
            identity = runtime_identity()
            assert identity['source_sha256']==canonical
            suite = unittest.TestSuite()
            for index,name in enumerate(TEST_FILES):
                path = HERE/'baseline/tests'/name
                if args.migrations and (HERE/'migrations'/name).exists():
                    path = HERE/'migrations'/name
                if args.migrations and args.role=='candidate' and (HERE/'candidate_migrations'/name).exists():
                    path = HERE/'candidate_migrations'/name
                raw = path.read_bytes()
                source_tests[str(path.relative_to(ROOT))] = sha(raw)
                # The original test filename anchors its existing fixture paths.
                module = types.ModuleType('_m3_original_regression_'+str(index))
                module.__file__ = str(ROOT/'verification'/name)
                module.RUNTIME_SOURCE_SHA256 = canonical
                sys.modules[module.__name__] = module
                exec(compile(raw,module.__file__,'exec',dont_inherit=True),module.__dict__)
                if name == 'test_selected_task_query.py':
                    # This legacy transport fixture embeds host source bytes.
                    # Keep that source root on this same physical generation.
                    module.ROOT = engine
                suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
            result = unittest.TextTestRunner(stream=log,verbosity=2,resultclass=RecordedResult).run(suite)
    except BaseException:
        error = traceback.format_exc()
    for name,value in (('STDOUT.txt',stdout.getvalue()),('STDERR.txt',stderr.getvalue()),('TESTS.txt',log.getvalue())):
        (output/name).write_text(value,encoding='utf8',newline='\n')
    loaded = guard.verify_loaded()
    unchanged = all((engine/name).read_bytes()==raw for name,raw in blobs.items())
    tests_unchanged = all(sha((ROOT/path).read_bytes())==expected for path,expected in source_tests.items())
    summary = {'passed':bool(result and result.wasSuccessful() and not error and not attempts and loaded and unchanged),
        'role':args.role,'migrated_tests':args.migrations,'source_sha256':canonical,'source_count':len(blobs),'source_kind':None if identity is None else identity['source_kind'],
        'test_files':source_tests,'methods':0 if result is None else result.testsRun,'executed':executed,
        'failures':[] if result is None else [{'test':t.id(),'traceback':tb} for t,tb in result.failures],
        'errors':[] if result is None else [{'test':t.id(),'traceback':tb} for t,tb in result.errors],
        'skipped':[] if result is None else [{'test':t.id(),'reason':reason} for t,reason in result.skipped],
        'runner_exception':error,'guard_verified':loaded,'sources_unchanged':unchanged,'external_attempts':attempts,
        'existing_fixture_loopback_operations':local_connections,
        'tests_unchanged':tests_unchanged,
        'Blender_sessions':0,'model_consumers':0,'performance_samples':0}
    save(output/'RESULTS.json',summary)
    save(output/'SOURCE.json',{'manifest':manifest,'identity':identity,'runner_sha256':sha(Path(__file__).read_bytes())})
    print(json.dumps({'passed':summary['passed'],'methods':summary['methods'],
        'failures':len(summary['failures']),'errors':len(summary['errors']),'skips':len(summary['skipped'])}))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
