"""Independent OPT1 evidence check; reuse the root's sealed geometry checker."""
from pathlib import Path
from collections import Counter
import hashlib, importlib.util, json, math, subprocess, time

OUT=Path(__file__).resolve().parent
ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE=ROOT/'verification/m4_surface_scan_001_opt1'
QUAL=ROOT/'verification/m4_surface_scan_001/qualification'
DELIVERY='860b87138d40de9cc08b01c947dd864d58da9295'
OLDROOT=Path('D:/hefe/verification/fixes/20261112_m4_surface_scan_initial_review/quality')
ROOT_COMMIT='dd11f1aa97ad0bf8bb314a86cd91b32ff0123874'
SOURCES={'A':'b3654f6f943c3fb6feff0011397c0a8c20872e41f35973e6baf53e3a5e277314',
 'B':'c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943'}
REUSE={}
for name in ('check_saved.py','ORACLE_RECOMPUTE.json','INPUTS.json','RESULTS.json'):
 p=OLDROOT/name;data=p.read_bytes();rel=p.relative_to(Path('D:/hefe')).as_posix()
 assert data==subprocess.check_output(['git','show',ROOT_COMMIT+':'+rel],cwd='D:/hefe')
 REUSE[name]={'sha256':hashlib.sha256(data).hexdigest(),'root_commit':ROOT_COMMIT}
spec=importlib.util.spec_from_file_location('_root_sealed_geometry',OLDROOT/'check_saved.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g);g.OUT=OUT
read,raw,check,dump,F=g.read,g.raw,g.check,g.dump,g.F
TH,TOL=g.TH,g.TOL

def normalized(x):return {k:v for k,v in x.items() if k not in ('pid','blend_filepath')}
def lines(path):return [json.loads(s) for s in raw(path).splitlines() if s.strip()]

def main():
 started=time.perf_counter();prepared={s:g.prepare(s) for s in ('base','edit')}
 sealed=json.loads((OLDROOT/'ORACLE_RECOMPUTE.json').read_bytes())
 for state in prepared:
  expected=prepared[state][2];old={tuple(r['pair']):r for r in sealed[state]['pairs']}
  check(state+'.sealed_minima_set',set(expected)==set(old))
  for pair,row in expected.items():check(state+'.sealed_minimum.'+str(pair),g.exact(row['exact_squared_distance_m2'])==g.exact(old[pair]['exact_squared']))
 names=prepared['base'][1]
 ids={'blender:'+hashlib.sha256(json.dumps(['',n],ensure_ascii=False,separators=(',',':')).encode()).hexdigest():n for n in names}
 witness_cache={};observations=[];mappings=[];max_error=0.
 def verify(label,state,body,diag,arm):
  nonlocal max_error
  objects,truth=prepared[state][1:];matches={p for p,r in truth.items() if r['matches_threshold']}
  check(label+'.contract',body['result_kind']=='surface_scan' and body['status']=='complete' and body['threshold_m']==.002 and body['unit']=='m' and body['coordinate_frame']=='world' and body['execution_authority'] is False)
  check(label+'.source_solid',body['binding']['runtime_source_sha256']==SOURCES[arm] and body['measurement_semantics']['solid_relation']=='not_evaluated')
  check(label+'.scope',not body['scope_issues'] and not body['unsupported_objects'] and not body['unresolved'])
  part={};counts=Counter()
  for row in diag['dispositions']:
   pair=tuple(sorted(ids[i] for i in row['object_ids']));check(label+'.unique_partition.'+str(pair),pair not in part and pair in truth)
   part[pair]=row;counts[row['status']]+=1;d=g.exact(truth[pair]['exact_squared_distance_m2'])
   check(label+'.partition_truth.'+str(pair),row['status'] in ('bound_excluded','measured_match','measured_nonmatch') and (row['status']=='measured_match')==(pair in matches))
   if row['status']=='bound_excluded':check(label+'.exclusion.'+str(pair),F(row['lower_bound_m'])>TH and F(row['lower_bound_m'])**2<=d)
   else:
    err=abs(row['distance_m']-math.sqrt(float(d)));max_error=max(max_error,err)
    check(label+'.private_distance.'+str(pair),math.isfinite(row['distance_m']) and err<=float(TOL))
  check(label+'.all_pairs',set(part)==set(truth));seen=set();wc=0
  for row in body['matches']:
   pair=tuple(sorted(o['name'] for o in row['objects']));check(label+'.unique_public.'+str(pair),pair not in seen and pair in matches);seen.add(pair)
   check(label+'.ids.'+str(pair),all(ids[o['id']]==o['name'] for o in row['objects']))
   d=g.exact(truth[pair]['exact_squared_distance_m2']);err=abs(row['distance_m']-math.sqrt(float(d)));max_error=max(max_error,err)
   check(label+'.public_distance.'+str(pair),math.isfinite(row['distance_m']) and row['distance_m']>=0 and err<=float(TOL) and row['witness_status']=='measured')
   check(label+'.witness_separation.'+str(pair),abs(math.dist(row['point_a_world'],row['point_b_world'])-row['distance_m'])<=float(TOL))
   for k,key in enumerate(('point_a_world','point_b_world')):
    n=row['objects'][k]['name'];p=tuple(F(x) for x in row[key]);ck=(state,n,p)
    if ck not in witness_cache:witness_cache[ck]=min(g.point_triangle_sq(p,t) for t in objects[n]['triangles'])
    check(label+'.surface_witness.'+str(pair)+'.'+key,witness_cache[ck]<=TOL*TOL);wc+=1
  check(label+'.public_set',seen==matches)
  c=body['coverage'];check(label+'.coverage',c['objects']==24 and c['total_pairs']==276 and c['catalog_scope_confirmed'] and all(c[k]==counts[k] for k in ['bound_excluded','measured_match','measured_nonmatch','unknown','deferred']))
  check(label+'.delivery',body['delivery']['complete'] and body['delivery']['matches_total']==body['delivery']['delivered_matches']==len(matches))
  observations.append({'label':label,'state':state,'arm':arm,'pairs':len(part),'matches':len(matches),'witnesses':wc,'counts':dict(counts)})
 def reuse(label,rows):
  cold,repeat,edit=(r['diagnostics'] for r in rows)
  check(label+'.cold_empty',cold['measurement_cache_before']['measurement_entries']==cold['measurement_cache_before']['measurement_computations']==0)
  check(label+'.kernel_counts',[x['kernel_calls'] for x in (cold,repeat,edit)]==[112,0,10])
  check(label+'.cache_limits',all(x['measurement_cache_after']['max_bytes']==2097152 and x['measurement_cache_max_measurements']==256 for x in (cold,repeat,edit)))
  old=cold['pairs'];hits=misses=0;details=[]
  for key,value in edit['pairs'].items():
   pair=tuple(ids[i] for i in json.loads(key));unchanged='Obj_008' not in pair
   check(label+'.trusted_used.'+str(pair),value['surface_dependency_used'] is True)
   if unchanged:
    check(label+'.unchanged_hit.'+str(pair),key in old and value['surface_dependency_key']==old[key]['surface_dependency_key'] and value['surface_dependency_objects']==old[key]['surface_dependency_objects'] and value['surface_pair_cache_hit'] is True and value['surface_dependency_cache_hit'] is True and value['surface_pair_count']==0)
    hits+=1
   else:
    check(label+'.changed_miss.'+str(pair),not value['surface_pair_cache_hit'] and not value['surface_dependency_cache_hit'] and value['surface_pair_count']==1 and (key not in old or value['surface_dependency_key']!=old[key]['surface_dependency_key']))
    misses+=1
   details.append({'pair':pair,'unchanged':unchanged,'hit':value['surface_pair_cache_hit'],'key':value['surface_dependency_key']})
  check(label+'.104_10',hits==104 and misses==10)
  mappings.append({'label':label,'unchanged_hits':hits,'changed_misses':misses,'pairs':details})
 asset=hashlib.sha256(raw(QUAL/'assembly.blend')).hexdigest();actual_snapshots=0
 for seq in range(1,6):
  for arm in ('A','B'):
   path=BASE/'engineering/run_01'/f'pair_{seq:02d}'/arm;d=read(path/'RESULTS.json');label=f'{seq}.{arm}'
   check(label+'.planned_rows',[r['state'] for r in d['business']]==['cold','repeat','edit'])
   check(label+'.no_failure',not d['errors'] and d['automatic_retries']==0 and d['metadata_zero_host_RPC'])
   check(label+'.asset',hashlib.sha256(raw(path/'native/input.blend')).hexdigest()==asset)
   audits=lines(path/'audit.jsonl');tx=[read(f) for f in sorted((path/'product').glob('*/TX.bin'))];rx=[read(f) for f in sorted((path/'product').glob('*/RX.bin'))]
   check(label+'.only3scan',sum(r.get('params',{}).get('name')=='human_eye_scene_observe' for r in tx)==3)
   check(label+'.only_allowed_requests',all(r['method'] in ('initialize','notifications/initialized','ping','tools/list') or r.get('params',{}).get('name')=='human_eye_scene_observe' for r in tx))
   for state in ('base','edit'):
    snap=read(path/(state+'_ACTUAL_SNAPSHOT.json'));check(label+'.snapshot.'+state,normalized(snap)==normalized(prepared[state][0]));actual_snapshots+=1
   for row in d['business']:
    lab=label+'.'+row['state'];state='edit' if row['state']=='edit' else 'base'
    request=read(path/(row['state']+'_REQUEST.json'));receipt=read(path/(row['state']+'_RESPONSE_RECEIPT.json'))
    check(lab+'.request',row['request']==request and request['params']['arguments']['query']=={'mode':'surface_scan','threshold_m':.002} and sum(t==request for t in tx)==1)
    check(lab+'.response',receipt['body']==row['body'] and json.loads(row['response']['result']['content'][0]['text'])==row['body'] and sum(r==row['response'] for r in rx)==1)
    obs=[a for a in audits if a.get('event')=='observe' and a.get('trace_id')==row['body']['trace_id']]
    check(lab+'.audit',len(obs)==1 and obs[0]['task_work']==row['diagnostics'])
    check(lab+'.execution',not row['errors'] and row['actual_host_RPC']==1)
    verify(lab,state,row['body'],row['diagnostics'],arm)
   check(label+'.kernels',[r['diagnostics']['kernel_calls'] for r in d['business']]==([112,0,114] if arm=='A' else [112,0,10]))
   if arm=='B':reuse(label,d['business'])
 path=BASE/'engineering/process_01';d=read(path/'RESULTS.json');tx=lines(path/'MCP_TX.bin');rx=lines(path/'MCP_RX.bin');audits=lines(path/'audit.jsonl');cmds=lines(path/'Blender_STDIN_UTF8.bin')
 check('Process.rows',[r['state'] for r in d['business']]==['cold','repeat','edit'] and not d['errors'])
 order=['capabilities','qa_snapshot','capture_surface_scan','capture_surface_scan','qa_advance','qa_snapshot','capture_surface_scan','shutdown']
 check('Process.command_order',[r['command'] for r in cmds]==order)
 closed=read(path/'QA_CLOSED.json');conf=read(path/'qa_worker.json')
 check('Process.wrapper',raw(path/'qa_worker.py')==raw(BASE/'engineering/process_worker.py') and closed['normal_commands']==[x for x in order if not x.startswith('qa_')] and closed['strict_sequence_finished'] and closed['qa_advanced_once'] and closed['error'] is None)
 check('Process.worker_sha',hashlib.sha256(raw(Path(conf['install_root'])/'human_eye_plugin/blender_worker.py')).hexdigest()==conf['worker_sha256']==closed['unmodified_product_worker_sha256'])
 check('Process.asset',hashlib.sha256(raw(path/'input.blend')).hexdigest()==asset)
 for s in ('cold','edit'):check('Process.snapshot.'+s,normalized(read(path/(s+'_ACTUAL_SNAPSHOT.json')))==normalized(prepared['edit' if s=='edit' else 'base'][0]))
 for row in d['business']:
  label='Process.'+row['state'];check(label+'.raw_stdio',sum(t==row['request'] for t in tx)==1 and sum(r==row['response'] for r in rx)==1)
  check(label+'.raw_body_and_query',json.loads(row['response']['result']['content'][0]['text'])==row['body'] and row['request']['params']['arguments']['query']=={'mode':'surface_scan','threshold_m':.002})
  obs=[a for a in audits if a.get('event')=='observe' and a.get('trace_id')==row['body']['trace_id']]
  check(label+'.raw_audit',len(obs)==1 and obs[0]['task_work']==row['diagnostics'] and not row['errors'])
  verify(label,'edit' if row['state']=='edit' else 'base',row['body'],row['diagnostics'],'B')
 reuse('Process',d['business'])
 for name in ('sequence.py','process_worker.py','run_process.py','run_pairs.py','common.py'):raw(BASE/'engineering'/name)
 # Every loaded evidence file must equal its fixed Git blob. Installed worker is checked against its product commit.
 for rel,meta in g.FILES.items():
  if rel.startswith('.human-eye/'):
   suffix=rel.split('/site-packages/',1)[1];commit='c1cb2da32034e056a270384e691a2cde8dddbc0d';name=suffix
  else:commit=DELIVERY;name=rel
  blob=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
  check('git:'+rel,hashlib.sha256(blob).hexdigest()==meta['sha256'])
 check('denominator33',len(observations)==33)
 result={'passed':True,'observations':observations,'total_partitions':sum(r['pairs'] for r in observations),'public_distances':sum(r['matches'] for r in observations),'witness_occurrences':sum(r['witnesses'] for r in observations),'unique_witnesses':len(witness_cache),'max_public_or_private_distance_error_m':max_error,'actual_main_snapshots':actual_snapshots,'process_actual_snapshots':2,'assertions':len(g.CHECKS),'files_read':len(g.FILES),'exact_minima_reused_from_root':552,'new_product_Blender_consumers_API':0,'elapsed_seconds':time.perf_counter()-started}
 dump('RESULTS.json',result);dump('REUSE.json',REUSE);dump('INPUTS.json',g.FILES);dump('CACHE_MAPPING.json',mappings)
 dump('CHECKS.json',{'checks':len(g.CHECKS),'failed':[c for c in g.CHECKS if not c['passed']],'per_observation':dict(Counter(c['name'].split('.')[0] for c in g.CHECKS))})
 print(json.dumps({k:v for k,v in result.items() if k!='observations'}))

if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True)
 try:main()
 except BaseException:
  dump('FAILURE_CHECKS.json',g.CHECKS);dump('FAILURE_INPUTS.json',g.FILES);raise
