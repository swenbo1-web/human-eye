"""Relevant frozen-model regressions; no training or performance loops."""
import hashlib
import io
import json
from pathlib import Path
import sys
import types
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'verification/m6_arm_expert_001'),str(Path(__file__).parent)]
package=types.ModuleType('human_eye_plugin');package.__path__=[str(ROOT/'human_eye_plugin')]
sys.modules['human_eye_plugin']=package
files=[ROOT/'human_eye_plugin/arm_twist_expert.py',ROOT/'human_eye_plugin/arm_twist_weights.py',
       ROOT/'verification/m6_arm_expert_001/run_01/dataset.json.gz']
before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
suite=unittest.defaultTestLoader.discover(str(ROOT/'verification/m6_arm_expert_001'),pattern='*test*.py')
suite.addTests(unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_*.py'))
log=io.StringIO();result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
from human_eye_plugin.runtime_identity import runtime_identity
identity=runtime_identity()
record={'passed':result.wasSuccessful() and before==after,'tests':result.testsRun,
    'failures':len(result.failures),'errors':len(result.errors),'sources_and_data_unchanged':before==after,
    'source_sha256':identity['source_sha256'],'source_count':len(identity['source_files']),
    'input_sha256':after,'training_calls':0,'blender_calls':0,'external_api_calls':0}
output=Path(sys.argv[1]).resolve();output.mkdir(parents=True,exist_ok=True)
(output/'unit.log').write_text(log.getvalue(),encoding='utf8',newline='\n')
(output/'result.json').write_text(json.dumps(record,indent=2),encoding='utf8',newline='\n')
print(json.dumps(record))
sys.exit(0 if record['passed'] else 1)
