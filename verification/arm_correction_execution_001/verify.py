"""Final same-source CPU regression; no Blender or paid model calls."""
import hashlib
import io
import json
from pathlib import Path
import sys
import types
import unittest

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
sys.path[:0]=[str(ROOT),str(HERE)]
package=types.ModuleType('human_eye_plugin');package.__path__=[str(ROOT/'human_eye_plugin')]
sys.modules['human_eye_plugin']=package
names=['human_eye_plugin/'+name for name in ('goal_execution.py','goal_scheduler.py','blender_host.py',
    'blender_process.py','blender_worker.py','arm_twist_source.py','arm_twist_correction.py',
    'arm_twist_expert.py','arm_twist_weights.py')]
names+=['verification/arm_correction_execution_001/'+name for name in
        ('test_host.py','test_goal.py','test_transport.py','test_read_compat.py','verify.py')]
names+=['verification/test_blender_process.py']
before={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
suite=unittest.TestSuite()
for name in ('test_host','test_goal','test_transport','test_read_compat'):
    suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
suite.addTests(unittest.defaultTestLoader.loadTestsFromName('verification.test_blender_process'))
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
after={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
out=Path(sys.argv[1]).resolve()
if out.exists():raise ValueError('new_output_directory_required')
out.mkdir(parents=True)
record={'passed':result.wasSuccessful() and before==after,'tests':result.testsRun,
    'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),
    'before_sha256':before,'after_sha256':after,'sources_unchanged':before==after,
    'scope':'CPU_RNA_doubles_state_replay_and_real_worker_loop_Python_children_not_Blender',
    'blender_runs':0,'paid_model_calls':0}
(out/'TESTS.log').write_text(stream.getvalue(),encoding='utf8',newline='\n')
(out/'RESULT.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({key:record[key] for key in ('passed','tests','failures','errors','skips','sources_unchanged')}))
sys.exit(0 if record['passed'] else 1)
