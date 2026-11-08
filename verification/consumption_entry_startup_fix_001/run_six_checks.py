"""Frozen candidate bytes, exactly six mocks; no CLI/consumer/backend runs."""
import contextlib
from datetime import datetime,timezone
import hashlib
import importlib.abc
import json
from pathlib import Path
import sys
import types
import unittest
import zipfile

HERE=Path(__file__).resolve().parent;OUT=HERE/'check_01';OUT.mkdir(exist_ok=False)
sha=lambda b:hashlib.sha256(b).hexdigest()
blobs={n:(HERE/n).read_bytes() for n in ('runner.py','bridge.py','tests_startup.py')}
class NoProduct(importlib.abc.MetaPathFinder):
    def find_spec(self,name,path=None,target=None):
        if name.startswith(('human_eye_plugin','human_eye_module1_operators')):raise AssertionError('product import forbidden')
guard=NoProduct();sys.meta_path.insert(0,guard);sys.path.insert(0,str(HERE))
records=[]
def load(name,path):
    m=types.ModuleType(name);m.__file__=str(HERE/path);sys.modules[name]=m
    exec(compile(blobs[path],str(HERE/path),'exec',dont_inherit=True),m.__dict__)
    records.append(dict(module=name,path=path,sha256=sha(blobs[path]),execution='compile exact frozen read bytes'))
    return m
started=datetime.now(timezone.utc).isoformat()
with (OUT/'STDOUT.raw.txt').open('w',encoding='utf8') as stdout,(OUT/'STDERR.raw.txt').open('w',encoding='utf8') as stderr, \
        contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
    load('bridge','bridge.py');load('runner','runner.py');tests=load('startup_frozen_checks','tests_startup.py')
    suite=unittest.defaultTestLoader.loadTestsFromModule(tests)
    assert suite.countTestCases()==6
    with (OUT/'TESTS.raw.txt').open('w',encoding='utf8') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
unchanged=all((HERE/n).read_bytes()==b for n,b in blobs.items())
record=dict(started_utc=started,ended_utc=datetime.now(timezone.utc).isoformat(),methods=result.testsRun,
    failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped),passed=result.wasSuccessful() and unchanged,
    candidate_unchanged=unchanged,executed=records,actual_CLI_parses_in_this_process=0,
    consumers=0,Blender=0,MCP_services=0,real_RPC=0,model_API=0,product_imports=0,
    scope='stdlib in-memory streams/Popen mocks; old32 and oldconsumerbatch not rerun')
(OUT/'RESULTS.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
with zipfile.ZipFile(OUT/'EXECUTED_BYTES.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
    for n,b in blobs.items():archive.writestr(n,b)
    archive.writestr('run_six_checks.py',Path(__file__).read_bytes())
sys.meta_path.remove(guard)
print(json.dumps(dict(methods=result.testsRun,passed=record['passed'],failures=record['failures'],errors=record['errors'])))
raise SystemExit(0 if record['passed'] else 1)
