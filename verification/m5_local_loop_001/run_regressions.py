"""Run the M5 affected checks and preserve each attempt on its source bytes."""
import argparse
import hashlib
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',required=True)
    args=parser.parse_args()
    from human_eye_plugin.runtime_identity import runtime_identity
    identity=runtime_identity()
    target=OUT/(args.label+'.json')
    if target.exists():raise ValueError('Preserve the existing attempt; use a new label')
    (OUT/(args.label+'_identity.json')).write_text(json.dumps(identity,indent=2)+'\n',encoding='utf8')
    (OUT/(args.label+'_source.patch')).write_bytes(subprocess.check_output(['git','diff','52cf080','--','human_eye_plugin']))
    names=['test_host_runtime','test_auto_router','test_task_verification','test_goal_segment',
        'test_clearance_segment_service','test_goal_supervision_service','test_runtime_forward_deadline',
        'test_scheduler_exception_receipt','test_scheduler_native_review','test_scheduler_rollback_reserve',
        'test_owned_clearance_task','test_support_plane_discovery','test_support_plane_segment']
    modules=['verification.'+name for name in names]+[
        'verification.m5_local_loop_001.test_local_loop_reuse',
        'verification.arch_read_context_opt_001.test_selection_reuse',
        'verification.arch_integration_001.test_service_pipeline']
    pipeline=importlib.import_module(modules[-1])
    # This earlier suite saves wire records; never overwrite accepted evidence.
    pipeline.OUT=OUT/(args.label+'_read_pipeline')
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in modules)
    stream=io.StringIO();started=time.perf_counter_ns()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (OUT/(args.label+'.log')).write_text(stream.getvalue(),encoding='utf8')
    unchanged=all(hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()==row['sha256']
        for row in identity['source_files'])
    summary=dict(passed=result.wasSuccessful() and unchanged,tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        duration_ms=(time.perf_counter_ns()-started)/1e6,source_unchanged=unchanged,
        source_sha256=identity['source_sha256'],modules=modules,
        failed_methods=[str(test) for test,_ in result.failures+result.errors])
    target.write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary))
    return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
