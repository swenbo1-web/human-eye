"""OPT frozen CPU regression, with explicit state adapters and model counts."""
import hashlib
import importlib
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
names=['human_eye_plugin/'+name for name in ('arm_twist_source.py','blender_host.py','goal_execution.py',
    'goal_scheduler.py','blender_process.py','blender_worker.py','arm_twist_expert.py','arm_twist_weights.py',
    'arm_twist_correction.py','rig_pose.py')]
names+=['verification/arm_correction_execution_opt_001/'+name for name in
    ('test_host.py','test_goal.py','test_source.py','verify.py','native_controller.py','native_initializer.py')]
names+=['verification/arm_correction_execution_001/'+name for name in
    ('test_host.py','test_goal.py','test_transport.py','test_read_compat.py')]
names+=['verification/m6_arm_source_001/test_arm_source.py','verification/test_blender_process.py']
before={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
modules=[importlib.import_module(name) for name in (
    'verification.arm_correction_execution_opt_001.test_host',
    'verification.arm_correction_execution_opt_001.test_goal',
    'verification.arm_correction_execution_opt_001.test_source',
    'verification.arm_correction_execution_001.test_transport',
    'verification.arm_correction_execution_001.test_read_compat',
    'verification.test_blender_process')]
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module) for module in modules)
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
after={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
record={'passed':result.wasSuccessful() and before==after,'tests':result.testsRun,
    'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),
    'before_sha256':before,'after_sha256':after,'sources_unchanged':before==after,
    'scope':'CPU_RNA_doubles_real_locked_state_and_real_Python_worker_loop_not_Blender',
    'blender_runs':0,'paid_model_calls':0,'geometry_model_calls':0,
    'diagnostic_prediction_calls':modules[2].MODEL.calls,
    'diagnostic_events':modules[2].EVENTS,
    'state_probe_counts':modules[1].COUNTS,'host_details':modules[0].DETAILS}
(out/'TESTS.log').write_text(stream.getvalue(),encoding='utf8',newline='\n')
(out/'RESULT.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
print(json.dumps({key:record[key] for key in ('passed','tests','failures','errors','skips',
    'sources_unchanged','diagnostic_prediction_calls')}))
sys.exit(0 if record['passed'] else 1)
