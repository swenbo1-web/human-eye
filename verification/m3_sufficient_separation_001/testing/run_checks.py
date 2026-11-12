"""Guarded directed or existing regression checks, never a performance run."""

import argparse
import ast
from contextlib import ExitStack,redirect_stderr,redirect_stdout
from fractions import Fraction
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
REGRESSIONS = ('test_surface_proximity_001.py','test_surface_proximity_pruning_001.py',
    'test_surface_geometry.py','test_original_triangle_witness.py','test_task_query.py','test_selected_task_query.py',
    'test_scene_cache.py','test_mesh_mutation_cache.py','test_surface_scope_regression.py',
    'test_task_contract_001.py','test_task_complete_001.py')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded_exact(value):
    if isinstance(value,Fraction):
        return {'type':'Fraction','numerator':value.numerator,'denominator':value.denominator}
    raise TypeError('Unsupported evidence value: '+type(value).__name__)


def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False,default=encoded_exact)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product-root',required=True,type=Path)
    parser.add_argument('--source-sha256',required=True)
    parser.add_argument('--suite',required=True,choices=('regressions','directed','wiring'))
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    output = HERE/args.output
    assert output.resolve().parent==HERE.resolve()
    output.mkdir(exist_ok=False)
    frozen = json.loads((HERE/'FROZEN.json').read_bytes())
    assert sha((HERE/'DESIGNED_CASES.json').read_bytes())==frozen['designed_cases_sha256']
    assert sha((HERE/'TIMING_SEQUENCE.json').read_bytes())==frozen['sequence_sha256']
    engine = args.product_root.resolve()
    tree = ast.parse((engine/'human_eye_plugin/runtime_identity.py').read_bytes())
    constants = {node.targets[0].id:ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
        and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('_ROOT_MODULES','BASE_VERSION','IMPLEMENTATION_REVISION')}
    names = set(constants['_ROOT_MODULES']) | {path.relative_to(engine).as_posix() for package in
        ('human_eye_plugin','human_eye_module1_operators') for path in (engine/package).glob('*.py')}
    blobs = {name:(engine/name).read_bytes() for name in sorted(names)}
    manifest = [{'path':name,'sha256':sha(raw)} for name,raw in blobs.items()]
    digest = sha(json.dumps({'base_version':constants['BASE_VERSION'],'implementation_revision':constants['IMPLEMENTATION_REVISION'],
        'files':manifest},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    assert len(manifest)==137 and digest==args.source_sha256
    bootstrap = types.ModuleType('_human_eye_verified_source_bootstrap')
    bootstrap.__file__ = str(engine/'human_eye_plugin/verified_source_loader.py')
    sys.modules[bootstrap.__name__] = bootstrap
    exec(compile(blobs['human_eye_plugin/verified_source_loader.py'],bootstrap.__file__,'exec',dont_inherit=True),bootstrap.__dict__)
    guard = bootstrap.install(engine,manifest,sources=MappingProxyType(blobs),bootstrap_module=bootstrap)
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
    external,local,test_pins,executed,evidence = [],[],{},[],{}

    def forbidden(*unused,**kwargs):
        external.append('external process/socket/signal')
        raise AssertionError(external[-1])

    original_socket = socket.socket
    class LoopbackSocket(original_socket):
        def bind(self,address):
            if address[0] not in ('127.0.0.1','::1','localhost'):
                return forbidden()
            local.append({'op':'bind','address':address})
            return super().bind(address)

        def connect(self,address):
            if address[0] not in ('127.0.0.1','::1','localhost'):
                return forbidden()
            local.append({'op':'connect','address':address})
            return super().connect(address)

    class RecordedResult(unittest.TextTestResult):
        def startTest(self,test):
            executed.append(test.id())
            super().startTest(test)

    result,error,identity = None,None,None
    stdout,stderr,log = io.StringIO(),io.StringIO(),io.StringIO()
    try:
        with ExitStack() as stack,redirect_stdout(stdout),redirect_stderr(stderr):
            for name in ('Popen','run','call','check_call','check_output'):
                stack.enter_context(patch.object(subprocess,name,side_effect=forbidden))
            stack.enter_context(patch.object(socket,'socket',LoopbackSocket))
            for name in ('system','kill'):
                stack.enter_context(patch.object(os,name,side_effect=forbidden))
            from human_eye_plugin.runtime_identity import runtime_identity
            identity = runtime_identity()
            assert identity['source_sha256']==digest
            if args.suite=='regressions':
                paths = [ROOT/'verification'/name for name in REGRESSIONS]
            elif args.suite=='wiring':
                paths = [HERE.parent/'wiring/test_spatial_wiring.py']
            else:
                paths = [HERE/'test_sufficient_separation.py']
            suite = unittest.TestSuite()
            for index,path in enumerate(paths):
                raw = path.read_bytes()
                test_pins[str(path)] = sha(raw)
                module = types.ModuleType('_sufficient_qa_'+str(index))
                module.__file__ = str(path)
                module.RUNTIME_SOURCE_SHA256 = digest
                sys.modules[module.__name__] = module
                exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
                if path.name=='test_selected_task_query.py':
                    module.ROOT = engine
                if hasattr(module,'EVIDENCE'):
                    evidence[path.name] = module.EVIDENCE
                suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
            result = unittest.TextTestRunner(stream=log,verbosity=2,resultclass=RecordedResult).run(suite)
    except BaseException:
        error = traceback.format_exc()
    for name,value in (('STDOUT.txt',stdout.getvalue()),('STDERR.txt',stderr.getvalue()),('TESTS.txt',log.getvalue())):
        (output/name).write_text(value,encoding='utf8',newline='\n')
    verified = guard.verify_loaded()
    unchanged = all((engine/name).read_bytes()==raw for name,raw in blobs.items())
    tests_unchanged = all(sha(Path(path).read_bytes())==digest for path,digest in test_pins.items())
    summary = {'passed':bool(result and result.wasSuccessful() and not error and not external and verified and unchanged and tests_unchanged),
        'suite':args.suite,'source_sha256':digest,'source_count':137,'source_kind':None if identity is None else identity['source_kind'],
        'methods':0 if result is None else result.testsRun,'executed':executed,'test_files':test_pins,
        'failures':[] if result is None else [{'test':t.id(),'traceback':tb} for t,tb in result.failures],
        'errors':[] if result is None else [{'test':t.id(),'traceback':tb} for t,tb in result.errors],
        'skipped':[] if result is None else [{'test':t.id(),'reason':reason} for t,reason in result.skipped],
        'runner_exception':error,'guard_verified':verified,'sources_unchanged':unchanged,'tests_unchanged':tests_unchanged,
        'external_attempts':external,'existing_fixture_loopback_operations':local,
        'Blender_sessions':0,'real_product_processes':0,'model_consumers':0,'performance_samples':0}
    save(output/'RESULTS.json',summary)
    save(output/'SOURCE.json',{'manifest':manifest,'identity':identity,'runner_sha256':sha(Path(__file__).read_bytes())})
    save(output/'EVIDENCE.json',evidence)
    print(json.dumps({'passed':summary['passed'],'methods':summary['methods'],
        'failures':len(summary['failures']),'errors':len(summary['errors'])}))
    return 0 if summary['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
