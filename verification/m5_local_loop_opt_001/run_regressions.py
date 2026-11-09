"""Affected runtime/owned-bridge regressions for this one follow-up change."""
import hashlib
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
    from human_eye_plugin.runtime_identity import runtime_identity
    label=sys.argv[1]
    if (OUT/(label+'.json')).exists():raise ValueError('Use a new attempt label')
    identity=runtime_identity()
    (OUT/(label+'_identity.json')).write_text(json.dumps(identity,indent=2)+'\n',encoding='utf8')
    (OUT/(label+'_source.patch')).write_bytes(subprocess.check_output(['git','diff','40eb3a0','--','human_eye_plugin']))
    modules=['verification.'+name for name in (
        'test_host_runtime','test_blender_process','test_blender_process_residency',
        'test_runtime_forward_deadline','test_clearance_segment_service',
        'test_scheduler_exception_receipt')]+[
        'verification.m5_local_loop_001.test_local_loop_reuse']
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in modules)
    stream=io.StringIO();started=time.perf_counter_ns()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (OUT/(label+'.log')).write_text(stream.getvalue(),encoding='utf8')
    unchanged=all(hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()==row['sha256']
        for row in identity['source_files'])
    summary=dict(passed=result.wasSuccessful() and unchanged,tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        duration_ms=(time.perf_counter_ns()-started)/1e6,source_sha256=identity['source_sha256'],
        source_unchanged=unchanged,modules=modules,
        failed_methods=[str(test) for test,_ in result.failures+result.errors])
    (OUT/(label+'.json')).write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary))
    return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
