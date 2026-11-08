"""Execute frozen candidate/test bytes only, with complete raw logs. No backend."""
from datetime import datetime,timezone
import contextlib
import hashlib
import importlib.abc
import io
import json
from pathlib import Path
import sys
import traceback
import types
import unittest
import zipfile

HERE=Path(__file__).resolve().parent;OUT=HERE/sys.argv[1];OUT.mkdir(exist_ok=False)
sha=lambda b:hashlib.sha256(b).hexdigest()
names=['bridge.py','runner.py','he_bootstrap.py','tests_bridge.py','tests_runner.py','tests_images.py','tests_fix_runner.py']
blobs={name:(HERE/name).read_bytes() for name in names};records=[];outcomes={};witness=[]
started=datetime.now(timezone.utc).isoformat()
class NoProduct(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.startswith(('human_eye_plugin','human_eye_module1_operators')):
            raise AssertionError('product import forbidden in tester checks:'+fullname)
guard=NoProduct();sys.meta_path.insert(0,guard)
sys.path.insert(0,str(HERE))
def audit(event,args):
    if event=='compile' and len(args)>1 and str(args[1]).startswith(str(HERE)):
        raw=args[0].encode('utf8') if isinstance(args[0],str) else args[0]
        if isinstance(raw,bytes):witness.append(dict(filename=str(args[1]),sha256=sha(raw)))
sys.addaudithook(audit)
def module(name,filename):
    value=types.ModuleType(name);value.__file__=str(HERE/filename);sys.modules[name]=value
    exec(compile(blobs[filename],str(HERE/filename),'exec',dont_inherit=True),value.__dict__)
    records.append(dict(module=name,path=filename,sha256=sha(blobs[filename]),execution='compile exact frozen snapshot bytes'))
    return value
try:
    with (OUT/'STDOUT.raw.txt').open('w',encoding='utf8') as stdout,(OUT/'STDERR.raw.txt').open('w',encoding='utf8') as stderr, \
            contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
        module('bridge','bridge.py');module('runner','runner.py')
        groups={'LEGACY19':['tests_bridge.py','tests_runner.py'],'DIRECTED':['tests_images.py','tests_fix_runner.py']}
        for label,files in groups.items():
            suite=unittest.TestSuite()
            for path in files:suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module('checks_'+Path(path).stem,path)))
            with (OUT/(label+'.raw.txt')).open('w',encoding='utf8') as raw:
                result=unittest.TextTestRunner(stream=raw,verbosity=2).run(suite)
            outcomes[label]=dict(methods=result.testsRun,failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped),passed=result.wasSuccessful())
except BaseException:
    (OUT/'EXCEPTION.raw.txt').write_text(traceback.format_exc(),encoding='utf8')
    raise
finally:
    sys.meta_path.remove(guard)
    unchanged=all((HERE/name).read_bytes()==raw for name,raw in blobs.items())
    result=dict(started_utc=started,ended_utc=datetime.now(timezone.utc).isoformat(),groups=outcomes,
        methods=sum(r['methods'] for r in outcomes.values()),passed=bool(outcomes) and all(r['passed'] for r in outcomes.values()) and unchanged,
        candidate_unchanged=unchanged,executed_modules=records,compile_witnesses=witness,
        sources=[dict(path=n,sha256=sha(b),bytes=len(b)) for n,b in blobs.items()],
        product_imports=0,actual_consumers=0,actual_Blender=0,actual_MCP_services=0,actual_RPC=0,model_API_calls=0,
        scope='stdlib mocks/controlled functions only; old19once plus directed; no replay of historical76')
    (OUT/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    with zipfile.ZipFile(OUT/'EXECUTED_BYTES.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,raw in blobs.items():archive.writestr(name,raw)
        archive.writestr('run_checks.py',Path(__file__).read_bytes())
    print(json.dumps({k:result[k] for k in ('methods','passed','groups','candidate_unchanged')}))
raise SystemExit(0 if result['passed'] else 1)
