"""Persist the combined fake-RNA source checks; never launch Blender."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
package=types.ModuleType('human_eye_plugin');package.__path__=[str(ROOT/'human_eye_plugin')]
sys.modules['human_eye_plugin']=package
files=[ROOT/'human_eye_plugin'/name for name in ('arm_twist_source.py','arm_twist_expert.py','arm_twist_weights.py')]
files.append(ROOT/'verification/m6_arm_expert_001/run_01/dataset.json.gz')
before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
spec=importlib.util.spec_from_file_location('arm_source_work_acceptance',Path(__file__).with_name('verify.py'))
acceptance=importlib.util.module_from_spec(spec);sys.modules[spec.name]=acceptance;spec.loader.exec_module(acceptance)
suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_arm_source.py')
suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(acceptance.SourceAcceptance))
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
from human_eye_plugin.runtime_identity import runtime_identity
identity=runtime_identity()
record={'passed':result.wasSuccessful() and before==after,'tests':result.testsRun,'failures':len(result.failures),
    'errors':len(result.errors),'sources_and_data_unchanged':before==after,'input_sha256':after,
    'source_sha256':identity['source_sha256'],'source_count':len(identity['source_files']),
    'observations':acceptance.OBSERVATIONS,'scope':'fake_RNA_indexed_collections_not_real_Blender',
    'default_bmesh_executed':False,'blender_calls':0,'training_calls':0,'external_model_api_calls':0}
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
(out/'unit.log').write_text(stream.getvalue(),encoding='utf8',newline='\n')
(out/'result.json').write_text(json.dumps(record,indent=2,allow_nan=False),encoding='utf8',newline='\n')
print(json.dumps({k:v for k,v in record.items() if k!='observations'}))
sys.exit(0 if record['passed'] else 1)
