import hashlib,json,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;SNAP=HERE/'snapshot';P=SNAP/'verification/m6_shape_ring_001'
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
REL='verification/m6_shape_ring_001';COMMIT='7ae143a6b062ac3c9fedcbf50939b79082884963'
n=0
def sha(data):return hashlib.sha256(data).hexdigest()
def load(name):return json.loads((P/name).read_bytes())
def check(value,reason):
 global n
 n+=1
 assert value,reason
def git(*args):return subprocess.check_output(['git',*args],cwd=AUTHOR)
def main():
 start=time.perf_counter();cpu=time.process_time()
 plan='1e9926a126a7d83725a69905a72136f7229376bf';cal='ae5f5381905d3158791780f7e6549918f8867ab9'
 for first,second in [(plan,cal),(cal,COMMIT)]:check(subprocess.run(['git','merge-base','--is-ancestor',first,second],cwd=AUTHOR).returncode==0,'ancestry')
 for r in load('PLAN_FREEZE.json')['files']:
  raw=git('show',plan+':'+REL+'/'+r['path']);check(raw==(P/r['path']).read_bytes() and sha(raw)==r['sha256'],'PLAN fixed '+r['path'])
 for name in ('CALIBRATION.json','CALIBRATION_FREEZE.json'):
  check(git('show',cal+':'+REL+'/'+name)==(P/name).read_bytes(),'calibration Git '+name)
 frozen=load('CALIBRATION_FREEZE.json')['files']
 for r in frozen:
  path=SNAP/Path(r['path']).relative_to(AUTHOR);check(sha(path.read_bytes())==r['sha256'],'calibration freeze member')
 check(not any(x.endswith('/EVALUATION.json') for x in git('ls-tree','-r','--name-only',cal,'--',REL).decode().splitlines()),'no evaluation summary at calibration commit')
 for report in ('RESIDUALS.json','CALIBRATION.json','EVALUATION.json','SYNTHETIC_QA.json'):
  for name,digest in load(report)['source_sha256'].items():
   actual=sha((P/name).read_bytes())
   if actual!=digest:
    archives=[x for x in (P/'private/recovery').glob('*.py') if sha(x.read_bytes())==digest]
    check(bool(archives),'executed source archive '+report+name)
   else:check(True,'source identity')
 costs=load('COSTS.json');phases=costs['phases']
 for label,row in phases.items():
  check(load('private/processes/'+label+'.controller.json')==row['controller'],'raw controller '+label)
  check(load('private/processes/'+label+'.json')==row['worker_tree'],'raw process '+label)
  path=Path(row['worker_tree']['command'][-1]);name=path.name;digest=row['controller']['worker_source_sha256']
  found=[x for x in [P/name,*list((P/'private/recovery').glob('*.py'))] if x.is_file() and sha(x.read_bytes())==digest]
  check(bool(found),'worker executed source '+label)
 check(abs(sum(r['controller']['main_wall_s_including_worker_before_write'] for r in phases.values())-costs['sequential_controller_wall_sum_s'])<1e-9,'wall sum')
 check(sum(r['worker_tree']['tree_cpu_s'] for r in phases.values())==costs['worker_tree_CPU_sum_s'],'worker CPU')
 check(sum(r['controller']['process_lifetime_before_final_write']['cpu_s'] for r in phases.values())==costs['controller_lifetime_CPU_sum_s'],'controller CPU')
 check(max(r['worker_tree']['tree_sampled_peak_working_set_bytes'] for r in phases.values())==costs['maximum_sampled_tree_RSS_bytes'],'peak')
 fit=load('RESIDUALS.json')['timings'];calt=load('CALIBRATION.json')['timings'];evt=load('EVALUATION.json')['timings']
 configs=('solid_point','ring_point','solid_cluster','ring_cluster')
 specific={prefix+cfg for cfg in configs for prefix in ('score_','case_evaluation_','group_ranking_','group_operations_')}
 shared_eval={k:v for k,v in evt.items() if k not in specific}
 shared_cal={k:v for k,v in calt.items() if k not in {b+s for b in ('solid','ring') for s in ('_normal_point_scores','_normal_components_and_scores')}}
 for cfg in configs:
  branch,kind=cfg.split('_');saved=costs['four_configuration_costs'][cfg]
  stages={k:evt[k] for k in specific if k.endswith('_'+cfg)}
  stages[branch+'_normal_point_scores']=calt[branch+'_normal_point_scores']
  if kind=='cluster':
   stages[branch+'_normal_components_and_scores']=calt[branch+'_normal_components_and_scores'];stages['score_'+branch+'_point']=evt['score_'+branch+'_point']
  check(stages==saved['marginal_stages'],'marginal stage members '+cfg)
  for metric,field in [('wall_s','main_wall_s_including_worker_before_write'),('CPU_s',None)]:
   total=sum(v[metric] for k,v in fit.items() if k not in ('solid_robust_quadratic_fit','ring_robust_quadratic_fit'))+fit[branch+'_robust_quadratic_fit'][metric]
   total+=sum(v[metric] for v in shared_eval.values())+sum(v[metric] for v in shared_cal.values())+sum(v[metric] for v in stages.values())
   for name,timed in [('fit',fit),('calibrate',calt),('evaluate',evt)]:
    outer=phases[name]['controller'][field] if field else phases[name]['worker_tree']['tree_cpu_s']
    total+=max(0,outer-sum(v[metric] for v in timed.values()))
   total+=sum(r['controller'][field] if field else r['worker_tree']['tree_cpu_s'] for name,r in phases.items() if name not in ('fit','calibrate','evaluate'))
   check(abs(total-saved['complete_measured_component_composition'][metric])<1e-9,'component composition '+cfg+metric)
 ev=load('EVALUATION.json');rows=ev['cases'];w=load('WITNESSES.json')['cases']
 devnorm=[r for r in rows if r['normal_control'] and r['purpose']=='development_train_pool']
 pick=max(devnorm,key=lambda r:(max([x['score_T'] for x in r['configurations']['ring_cluster']['components'] if x['retained_at_least5']] or [0]),r['id']))
 check(w[0]['id']==pick['id'],'normal maxT witness')
 for i,position in [(1,'center'),(2,'offcenter')]:
  eligible=[r for r in rows if r['purpose']=='validation' and not r['normal_control'] and r['position_group']==position]
  pick=max(eligible,key=lambda r:r['depth']['ring']['support_RMSE_over_ell'])
  check(w[i]['id']==pick['id'],'depth witness '+position)
 out={'status':'passed','assertions':n,'calibration_frozen_members':len(frozen),'sequential_phase_count':len(phases),
      'witness_refinement':'primary ring / RMSE-over-ell not separately preregistered; author disclosed, interpretive only',
      'author_wall_sum_s':costs['sequential_controller_wall_sum_s'],'author_worker_CPU_s':costs['worker_tree_CPU_sum_s'],
      'author_controller_CPU_s':costs['controller_lifetime_CPU_sum_s'],'root_wall_s':time.perf_counter()-start,'root_CPU_s':time.process_time()-cpu,
      'limits':['Git ancestry and fixed hashes support ordering; not an external execution attestation','Component costs not independently run standalone latency','No full environment re-audit; prior dependency binding retained']}
 (HERE/'EVIDENCE_RESULTS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
