"""Check cost aggregation and frozen evidence after independent reads."""
import json
from pathlib import Path
import time
import hashlib

HERE=Path(__file__).resolve().parent
B=HERE/'snapshot/verification/m6_shape_observe_001'
read=lambda p:json.loads(Path(p).read_bytes())
start,cpu=time.perf_counter(),time.process_time()
c=read(B/'COSTS.json');rows=[]
for phase,value in c['phases'].items():
    w=value['worker_tree'];controller=value['controller']
    assert w['returncode']==0 and controller['returncode']==0
    assert abs(sum(p['cpu_s'] for p in w['process_tree'])-w['tree_cpu_s'])<1e-9
    assert controller['wall_s_including_worker_before_write']>=w['full_process_wall_s']
    rows.append({'phase':phase,'wall_s':controller['wall_s_including_worker_before_write'],
                 'worker_tree_CPU_s':w['tree_cpu_s'],'controller_CPU_s':controller['process_lifetime_before_final_write']['cpu_s']})
for key,field in [('sequential_controller_main_wall_sum_s','wall_s'),('phase_worker_tree_CPU_sum_s','worker_tree_CPU_s'),('phase_outer_controller_lifetime_CPU_before_final_write_sum_s','controller_CPU_s')]:
    assert abs(sum(r[field] for r in rows)-c[key])<1e-9,key
snap=read(HERE/'SNAPSHOT.json')
for row in snap['snapshot_files']:
    p=HERE/'snapshot'/row['relative'];b=p.read_bytes()
    assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'],row['relative']
out={'status':'passed','phases':rows,'totals':{k:c[k] for k in c if k.endswith('_sum_s')},
     'missing_costs_retained':c['missing'],'author_delivery_assertion_failure':read(B/'DELIVERY_AUDIT_LOG.json'),
     'frozen_snapshot_files_unchanged':len(snap['snapshot_files']),
     'measurement':'Recorded author process costs verified arithmetically; not an independent rerun of wall-time benchmark',
     'wall_s_before_final_write':time.perf_counter()-start,'CPU_s_before_final_write':time.process_time()-cpu}
(HERE/'COST_AUDIT.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps(out,indent=2))
