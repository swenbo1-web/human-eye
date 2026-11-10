"""Affected existing regressions and full-result old/new arithmetic equivalence."""
from pathlib import Path
import argparse, hashlib, importlib, json, subprocess, sys, time, types, unittest
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from human_eye_plugin import surface_proximity as candidate, surface_geometry as solid
from verification.test_concave_geometry import entity,box

MODULES=['verification.test_surface_proximity_001','verification.test_surface_proximity_pruning_001',
 'verification.test_surface_geometry','verification.test_concave_geometry','verification.test_concave_roundoff',
 'verification.test_surface_scope_regression','verification.test_task_query','verification.test_task_complete_001',
 'verification.exact_rank_001.test_exact_rank','verification.closed_solid_read_001.tests.test_closed_solid']

def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true');args=parser.parse_args()
    oldraw=subprocess.check_output(['git','show','d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d:human_eye_plugin/surface_proximity.py'],cwd=ROOT)
    old=types.ModuleType('scale_opt_original');exec(compile(oldraw,'git-d01-surface_proximity.py','exec'),old.__dict__)
    variant='baseline' if args.baseline else 'candidate'
    if args.baseline:candidate._bounded=types.FunctionType(old._bounded.__code__,candidate.__dict__)
    cases=[]
    for sid,peer in [('G60_D12','peer'),('G508','peer'),('G4092','peer'),('T3','competitor'),('T4','competitor')]:
        raw=json.loads((ROOT/'verification/scale_diag_001/fixtures'/(sid+'.json')).read_bytes())
        objects={o['logical_id']:o for o in raw['objects']}
        meshes=[entity(k,objects[k]['vertices_world'],objects[k]['triangles']) for k in ('target',peer)]
        a=old.measure_surface_proximity(*meshes,lambda stage:None,retain_exact_rank=True)
        b=candidate.measure_surface_proximity(*meshes,lambda stage:None,retain_exact_rank=True)
        assert a==b,('full_result_changed',sid)
        cases.append({'id':sid,'full_result_equal':True,'measurement_valid':a['measurement_valid'],'reason':a.get('reason'),'work_equal':a['work']==b['work']})
    # Exact closed-solid code shares the same arithmetic. Preserve its complete
    # default returned record, not only a relation label.
    closed_cases=[('separated',box(center=(0,0,0),size=(2,2,2),identity='a'),box(center=(2.5,2.5,2.5),size=(1,1,1),identity='b')),
      ('touching',box(center=(0,0,0),size=(2,2,2),identity='a'),box(center=(2,0,0),size=(2,2,2),identity='b')),
      ('overlap',box(center=(0,0,0),size=(2,2,2),identity='a'),box(center=(1,1,1),size=(2,2,2),identity='b')),
      ('containment',box(center=(0,0,0),size=(4,4,4),identity='a'),box(center=(0,0,0),size=(2,2,2),identity='b'))]
    fast=candidate._bounded
    try:
        for name,left,right in closed_cases:
            # Compile original function against live module globals so shared
            # error handling, MAX_BITS and callers are exactly the same.
            legacy=types.FunctionType(old._bounded.__code__,candidate.__dict__)
            candidate._bounded=legacy;a=solid.classify_closed_solids(left,right,lambda stage:None)
            candidate._bounded=fast;b=solid.classify_closed_solids(left,right,lambda stage:None)
            assert a==b,('closed_full_result_changed',name)
            cases.append({'id':'solid_'+name,'full_result_equal':True,'relation':a.get('relation'),'measurement_valid':a.get('measurement_valid'),'reason':a.get('reason')})
    finally:candidate._bounded=fast
    suite=unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    with (HERE/('REGRESSIONS_'+variant.upper()+'.txt')).open('w',encoding='utf8',newline='\n') as stream:
        mark=time.perf_counter_ns();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite);elapsed=time.perf_counter_ns()-mark
    value={'variant':variant,'old_commit':'d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d','old_surface_sha256':sha(oldraw),
      'candidate_surface_sha256':sha((ROOT/'human_eye_plugin/surface_proximity.py').read_bytes()),'modules':MODULES,
      'full_result_differential':cases,'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
      'successful':result.wasSuccessful(),'elapsed_ns':elapsed,'test_only_timing_not_performance_samples':True}
    value['failure_ids']=[test.id() for test,trace in result.failures];value['error_ids']=[test.id() for test,trace in result.errors]
    (HERE/('REGRESSIONS_'+variant.upper()+'.json')).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps(value,indent=2))
    if not result.wasSuccessful():raise SystemExit(1)

if __name__=='__main__':main()
