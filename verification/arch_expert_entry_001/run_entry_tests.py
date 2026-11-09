"""Preserve one explicit CPU entry-test attempt and its executing source."""
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
    label=sys.argv[1]
    if (OUT/(label+'.json')).exists():raise ValueError('Use a new label; preserve the existing attempt')
    from human_eye_plugin.runtime_identity import runtime_identity
    identity=runtime_identity()
    (OUT/(label+'_identity.json')).write_text(json.dumps(identity,indent=2)+'\n',encoding='utf8')
    (OUT/(label+'_test_source.py.txt')).write_bytes((OUT/'test_entry.py').read_bytes())
    (OUT/(label+'_product.patch')).write_bytes(subprocess.check_output(['git','diff','539c277','--','human_eye_plugin','examples/blender_worker.py']))
    suite=unittest.defaultTestLoader.loadTestsFromName('verification.arch_expert_entry_001.test_entry')
    stream=io.StringIO();started=time.perf_counter_ns()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (OUT/(label+'.log')).write_text(stream.getvalue(),encoding='utf8')
    unchanged=all(hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()==row['sha256']
        for row in identity['source_files'])
    record=dict(passed=result.wasSuccessful() and unchanged,tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        duration_ms=(time.perf_counter_ns()-started)/1e6,source_sha256=identity['source_sha256'],
        source_members=len(identity['source_files']),source_unchanged=unchanged,
        failed_methods=[str(case) for case,_ in result.failures+result.errors])
    (OUT/(label+'.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
    print(json.dumps(record))
    return 0 if record['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
