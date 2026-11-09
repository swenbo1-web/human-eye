"""Preserve affected entry/bridge/MCP regressions, not the historical matrices."""
import hashlib,io,json,subprocess,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))

def main():
    label=sys.argv[1]
    if (OUT/(label+'.json')).exists():raise ValueError('Preserve attempts with a new label')
    from human_eye_plugin.runtime_identity import runtime_identity
    identity=runtime_identity()
    (OUT/(label+'_identity.json')).write_text(json.dumps(identity,indent=2)+'\n',encoding='utf8')
    (OUT/(label+'_test_source.py.txt')).write_bytes((OUT/'test_entry.py').read_bytes())
    (OUT/(label+'_product.patch')).write_bytes(subprocess.check_output(['git','diff','539c277','--','human_eye_plugin','examples/blender_worker.py']))
    modules=['verification.'+name for name in ('test_blender_host_contracts','test_blender_process',
        'test_blender_worker_protocol','test_blender_mcp_host','test_readonly_dependency_loader',
        'test_live_service','test_live_spatial_mcp','test_owned_task_mcp')]+[
        'verification.arch_expert_entry_001.test_entry',
        'verification.arch_read_context_opt_001.test_selection_reuse',
        'verification.m5_local_loop_001.test_local_loop_reuse']
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in modules)
    stream=io.StringIO();started=time.perf_counter_ns()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (OUT/(label+'.log')).write_text(stream.getvalue(),encoding='utf8')
    unchanged=all(hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['sha256'] for r in identity['source_files'])
    value=dict(passed=result.wasSuccessful() and unchanged,tests=result.testsRun,failures=len(result.failures),
        errors=len(result.errors),skipped=len(result.skipped),duration_ms=(time.perf_counter_ns()-started)/1e6,
        source_sha256=identity['source_sha256'],source_members=len(identity['source_files']),source_unchanged=unchanged,
        modules=modules,failed_methods=[str(t) for t,_ in result.failures+result.errors])
    (OUT/(label+'.json')).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8');print(json.dumps(value))
    return 0 if value['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
