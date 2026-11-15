import hashlib,json,subprocess,time
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];SNAP=HERE/'snapshot'
REL='verification/m6_perception_001';P=SNAP/REL
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
COMMIT='38fa3e2d01300498aabd43a051876a6f779dab68'
PLAN='cf9ad6c5ac2c64915fb883dfac41d91272d9ce3f'
CAL='6fa798646795d17081c1cf2cc7ce66f34dd7e53d'
n=0
def sha(b):return hashlib.sha256(b).hexdigest()
def load(name):return json.loads((P/name).read_bytes())
def git(*args):return subprocess.check_output(['git',*args],cwd=AUTHOR)
def check(v,why):
 global n
 n+=1
 assert v,why
def local(path):return SNAP/Path(path).relative_to(AUTHOR)

def main():
 start=time.perf_counter();cpu=time.process_time()
 for a,b in [('7ae143a6b062ac3c9fedcbf50939b79082884963',PLAN),(PLAN,CAL),(CAL,COMMIT)]:
  check(subprocess.run(['git','merge-base','--is-ancestor',a,b],cwd=AUTHOR).returncode==0,'ancestry')
 for row in load('PLAN_FREEZE.json')['files']:
  b=git('show',PLAN+':'+REL+'/'+row['path'])
  check(b==(P/row['path']).read_bytes() and sha(b)==row['sha256'],'plan fixed '+row['path'])
 for name in ['CALIBRATION.json','CALIBRATION_FREEZE.json','TRAIN_LOG.json','MODEL_IDENTITY.json','NORMALIZATION.json']:
  check(git('show',CAL+':'+REL+'/'+name)==(P/name).read_bytes(),'freeze public '+name)
 frozen=load('CALIBRATION_FREEZE.json')['files']
 for row in frozen:
  b=local(row['path']).read_bytes()
  check(len(b)==row['bytes'] and sha(b)==row['sha256'],'freeze member')
 tree=git('ls-tree','-r','--name-only',CAL,'--',REL).decode().splitlines()
 check(REL+'/EVALUATION.json' not in tree,'no validation evaluation at calibration commit')
 prior=json.loads((ROOT/'verification/m6_shape_pretrain_001_review/SNAPSHOT.json').read_bytes())
 prior_by_hash={(r['sha256'],r['bytes']) for r in prior['records']}
 snapshot=json.loads((HERE/'SNAPSHOT.json').read_bytes())
 unmatched=[r for r in snapshot['reused_inputs'] if r['matched_prior'] is None]
 check(len(unmatched)==37,'only 37 prior hash-only sampling records')
 for row in unmatched:
  check('/private/predictions/pointfilter/' in row['relative'] and row['relative'].endswith('/sampling_1.npz'),'previous sampling record')
  check((row['sha256'],row['bytes']) in prior_by_hash,'prior root hash binding')
 for row in load('SOURCE_INDEX.json')['files']:
  b=local(row['path']).read_bytes();check(sha(b)==row['sha256'],'official source bytes')
  if 'git_blob' in row:
   check(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==row['git_blob'],'official source blob')
 archives=list((P/'private/recovery').glob('*.py'))
 for f in sorted(P.glob('*.json')):
  j=json.loads(f.read_bytes());hashes=j.get('source_sha256')
  if isinstance(hashes,str):hashes={'verify.py':hashes}
  if isinstance(hashes,dict):
   for name,digest in hashes.items():
    check(any(x.is_file() and sha(x.read_bytes())==digest for x in [P/name,*archives]),'executed source '+f.name+'/'+name)
 costs=load('COSTS.json');phases=costs['phases']
 for name,row in phases.items():
  check(load('private/processes/'+name+'.controller.json')==row['controller'],'raw controller '+name)
  check(load('private/processes/'+name+'.json')==row['worker_tree'],'raw worker '+name)
  check(row['controller']['returncode']==0 and row['worker_tree']['returncode']==0,'phase success '+name)
  worker=Path(row['worker_tree']['command'][-1]).name;digest=row['controller']['worker_source_sha256']
  check(any(x.is_file() and sha(x.read_bytes())==digest for x in [P/worker,*archives]),'phase source '+name)
 check(abs(sum(r['controller']['main_wall_s_including_worker_before_write'] for r in phases.values())-costs['sequential_controller_wall_sum_s'])<1e-9,'phase wall sum')
 check(sum(r['worker_tree']['tree_cpu_s'] for r in phases.values())==costs['worker_tree_CPU_sum_s'],'phase worker CPU')
 check(sum(r['controller']['process_lifetime_before_final_write']['cpu_s'] for r in phases.values())==costs['controller_lifetime_CPU_sum_s'],'phase controller CPU')
 check(max(r['worker_tree']['tree_sampled_peak_working_set_bytes'] for r in phases.values())==costs['maximum_sampled_tree_RSS_bytes'],'phase RSS')
 old=load('private/recovery/regions_initial_reports/REGION_REFERENCES.json');new=load('REGION_REFERENCES.json')
 check(set(old['regions'])==set(new['regions']),'presentation references unchanged')
 for ref,r in new['regions'].items():check(r==old['regions'][ref],'reference record unchanged')
 features=load('FEATURES.json');timings=features['timings'];ft=phases['features']['controller']['main_wall_s_including_worker_before_write']
 out={'status':'passed','assertions':n,'calibration_freeze_records':len(frozen),'prior_physical_snapshot_matches':snapshot['prior_independent_matches'],
      'prior_hash_record_matches':len(unmatched),'prior_total_bound':snapshot['prior_independent_matches']+len(unmatched),
      'reference_records_unchanged_by_presentation_refinement':len(new['regions']),'raw_phase_count':len(phases),
      'author_phase_wall_sum_s':costs['sequential_controller_wall_sum_s'],'author_worker_CPU_s':costs['worker_tree_CPU_sum_s'],
      'author_controller_CPU_s':costs['controller_lifetime_CPU_sum_s'],'author_peak_RSS_bytes':costs['maximum_sampled_tree_RSS_bytes'],
      'feature_phase_wall_s':ft,'encoder_forward_wall_s':timings['encoder_forward']['wall_s'],
      'encoder_forward_fraction_of_feature_phase':timings['encoder_forward']['wall_s']/ft,
      'feature_cache_and_sampling_write_wall_s':timings['feature_and_sampling_cache_save_hash']['wall_s'],
      'wall_s':time.perf_counter()-start,'CPU_s':time.process_time()-cpu,
      'limits':['Commit ancestry and frozen byte identities support ordering, not external process attestation.',
                'The 37 old sampling caches were previously independently hash-bound, not physically copied into that prior review.',
                'Costs are author raw phase accounting reconstructed here; not an independent production latency or LLM comparison.',
                'Three fixed text reports were read; all references independently reconstructed in METRICS_REGIONS_RESULTS, not desktop plugin integration.']}
 (HERE/'EVIDENCE_RESULTS.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
 print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
