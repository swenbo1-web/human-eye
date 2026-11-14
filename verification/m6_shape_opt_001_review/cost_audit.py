"""Reconcile saved online worker measurements and their full-source arrays."""
import json
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
NEW=HERE/'snapshot'
OLD=HERE.parent/'m6_shape_train_001_review/snapshot'
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
def read(p):return json.loads(p.read_bytes())
def path(root,p):return root/Path(p).relative_to(AUTHOR)
r=read(NEW/'verification/m6_shape_opt_001/ONLINE_RESULTS.json')
old=read(OLD/'verification/m6_shape_train_001/ONLINE_RESULTS.json')
baseline={w['sample']:w['worker']['rounds'][0]['artifact']['path'] for w in old['workers'] if w['method']=='mls'}
workers={};calls=0
for item in r['workers']:
    w=read(path(NEW,item['private_worker_report']))
    projected={k:w[k] for k in item['worker'] if k!='rounds'}
    projected['rounds']=[]
    for raw in w['rounds']:
        compact={k:v for k,v in raw.items() if k!='MLS_diagnostics'}
        if 'MLS_diagnostics' in raw:compact['MLS_counts']=raw['MLS_diagnostics']['counts']
        projected['rounds'].append(compact)
    assert projected==item['worker']
    assert set(w)-set(item['worker'])=={'task','cold_definition','warm_definition','includes_coupling'}
    assert w['includes_coupling'] is False
    assert len(w['rounds'])==4 and w['status']=='complete'
    workers[item['sample'],item['method']]=w
    expected=np.load(path(OLD,baseline[item['sample']]),allow_pickle=False)
    for call in w['rounds']:
        actual=np.load(path(NEW,call['artifact']['path']),allow_pickle=False)
        assert actual.shape==(172974,3) and actual.dtype==np.float64
        assert np.array_equal(actual.view(np.uint64),expected.view(np.uint64))
        assert call['input_alignment']['all_whitelist_values_exact']
        stages=sum(v['wall_s'] for v in call['timings'].values())
        assert stages<=call['full_call']['wall_s']+1e-9
        calls+=1
paired=[]
for recorded in r['paired_differences']:
    s=recorded['sample'];m=workers[s,'model'];b=workers[s,'mls']
    cold=m['cold_start_to_first_complete']['wall_s']-b['cold_start_to_first_complete']['wall_s']
    warm=[m['rounds'][i]['full_call']['wall_s']-b['rounds'][i]['full_call']['wall_s'] for i in [1,2,3]]
    assert cold==recorded['cold_model_minus_MLS_wall_s'] and warm==recorded['warm_model_minus_MLS_wall_s']
    paired.append({'sample':s,'cold_s':cold,'warm_s':warm})
cost=read(NEW/'verification/m6_shape_opt_001/COSTS.json')
out={'author_commit':'36694d0e3730a60b0611376b017f978f809a79c0','raw_worker_measurement_fields_matched':len(workers),
     'full_source_saved_arrays_checked':calls,'array_vertices':172974,'full_arrays_bitwise_equal_same_input_frozen_MLS_noop':True,
     'paired':paired,'measurement_scope':'existing worker entry-to-first-complete cold and repeated complete readback warm; no new benchmark, excludes coupling and complete host/model interaction',
     'author_recorded_unmeasured':cost['unmeasured'],'quality_failure_blocks_benefit_claim':True}
(HERE/'COST_AUDIT.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'raw_workers':len(workers),'full_arrays':calls,'paired':paired}))
