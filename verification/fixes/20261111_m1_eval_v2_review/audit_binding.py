import ast, copy, hashlib, io, json, subprocess, sys, traceback
from collections import Counter
from pathlib import Path
WT=Path(r'C:\Users\Administrator\.codex\worktrees\m4-single-pass-acquisition\hefe');REL='verification/m1_task_entry_001_eval';R=WT/REL
OUT=Path(r'D:\hefe\verification\fixes\20261111_m1_eval_v2_review')
BASE='82e976cd425fae9703399148a8938bd6099d486f';COMMIT='81dcafec303bb867795f4474f5fe9bca2aa85c8e'
ATTEMPT=OUT/('BINDING_REVIEW_ATTEMPT_%02d.json'%(len(list(OUT.glob('BINDING_REVIEW_ATTEMPT_*.json')))+1))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def exception(t,v,b):
    save(ATTEMPT,{'status':'reviewer_checker_exception','traceback':''.join(traceback.format_exception(t,v,b)),'product_executed':False});sys.__excepthook__(t,v,b)
sys.excepthook=exception
sha=lambda b:hashlib.sha256(b).hexdigest();H=lambda p:sha(Path(p).read_bytes());J=lambda p:json.loads(Path(p).read_bytes());L=lambda p:J(R/p)
G=lambda *a:subprocess.check_output(['git','-C',str(WT),*a])
def git_blobs(commit,paths):
    data=subprocess.run(['git','-C',str(WT),'cat-file','--batch'],input=''.join(commit+':'+p+'\n' for p in paths).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
    stream=io.BytesIO(data);result={}
    for p in paths:
        h=stream.readline().split()
        if len(h)!=3 or h[1]!=b'blob':raise ValueError(p)
        result[p]=stream.read(int(h[2]));assert stream.read(1)==b'\n'
    return result
errors=[];checks=Counter()
def check(ok,name,path=None):
    checks[name]+=1
    if not ok:errors.append({'check':name,'path':str(path) if path else None})
pins={'PLAN.json':'e0653d576e0f64936602e6883fd7a8dffc5a0374c7de4534e9d1284b0eb8fa99','ARTIFACT_INDEX.json':'fd6c9cc5db12810a7aa12e47af3e104fd7073cbdc4d527d48390001310629874','FREEZE.json':'7e5e793a967f89a6c310fb963708294f49093482c463f1c48c3267068abcf639'}
for p,h in pins.items():check(H(R/p)==h,'requested_v2_pin',p)
head=G('rev-parse','HEAD').decode().strip();status=G('status','--porcelain').decode()
check(head==COMMIT and not status,'clean_fixed_HEAD');check(G('rev-parse',COMMIT+'^').decode().strip()==BASE,'parent_82e')
changes=L('finalize_v2/CONTRACT_CHANGES.json');archive=L('finalize_v2/ORIGINAL_ARCHIVE.json');plan=L('PLAN.json');freeze=L('FREEZE.json');tasks=L('TASKS.json');score=L('SCORING_CONTRACT.json');contract=L('EVAL_CONTRACT.json')
archive_rows=archive['files'];old_paths=[r['original_path'] for r in archive_rows];old_blobs=git_blobs(BASE,old_paths);copy_blobs=git_blobs(COMMIT,[r['copy_path'] for r in archive_rows])
check(len(archive_rows)==14 and archive['base_commit']==BASE,'original_14_copy_denominator')
for row in archive_rows:
    raw=(WT/row['copy_path']).read_bytes();check(raw==old_blobs[row['original_path']]==copy_blobs[row['copy_path']] and sha(raw)==row['sha256'] and len(raw)==row['bytes'],'original_copy_exact_Git_blob',row['copy_path'])
old=lambda n:json.loads(old_blobs[REL+'/'+n])
old_plan,old_tasks,old_score,old_contract=old('PLAN.json'),old('TASKS.json'),old('SCORING_CONTRACT.json'),old('EVAL_CONTRACT.json')
old_rules=old_blobs[REL+'/SESSION_RULES.txt'];rules=(R/'SESSION_RULES.txt').read_bytes();precision=changes['public_precision']['text']
check(len(old_rules)==205 and len(rules)==327 and rules==old_rules+precision.encode('utf-8')+b'\n','205_byte_prefix_plus_common_precision_327')
check(H(R/'SESSION_RULES.txt')==changes['public_precision']['new_rules_sha256']==plan['shared_session_rules']['sha256']==contract['shared_session_rules']['sha256']==freeze['public_rules_sha256'] and sha(old_rules)==changes['public_precision']['old_rules_sha256'],'rules_all_contract_hash_binding')
check(score['common_precision_instruction']==precision and plan['shared_session_rules']==contract['shared_session_rules'],'same_disclosed_precision_for_all_arms')
check(score['distance_rule'].startswith(old_score['distance_rule']) and score['text_format'].startswith(old_score['text_format']),'old_numeric_tolerance_and_flexible_text_policy_preserved')

# Bind to the already-certified recorded interval only; do not recompute its mathematics.
roundoff_path=R/'tasks/T1/run_01/WORLD_ROUNDOFF.json';roundoff=J(roundoff_path);intervals={x['name']:x['captured_world_distance_interval_m'] for x in roundoff['separated_distance_intervals_with_binary64_world_roundoff']}
check(set(intervals)=={'Part_26','Part_38'} and H(roundoff_path)==changes['scoring_interval_source']['sha256']==freeze['T1_scoring_source_sha256'],'two_existing_world_roundoff_intervals')
check(roundoff_path.read_bytes()==G('show',BASE+':'+roundoff_path.relative_to(WT).as_posix()),'world_roundoff_evidence_unchanged')
for name,interval in intervals.items():
    rows=[tasks['T1']['facts'][name],plan['tasks']['T1']['facts'][name],score['independent_answers']['T1']['required_pair_facts'][name]]
    for row in rows:
        binding=row['distance_interval_source'];check(row['distance_interval_m']==interval and binding['path']=='tasks/T1/run_01/WORLD_ROUNDOFF.json' and binding['sha256']==H(roundoff_path) and binding['object']==name and binding['field']==changes['scoring_interval_source']['field'],'T1_pair_interval_three_contract_binding',name)
    check(old_tasks['T1']['facts'][name]['distance_interval_m'][0]>=interval[0] and old_tasks['T1']['facts'][name]['distance_interval_m'][1]<=interval[1],'T1_old_interval_contained_in_expanded',name)
nearest=intervals['Part_26'];check(tasks['T1']['distance_interval_m']==plan['tasks']['T1']['distance_interval_m']==score['independent_answers']['T1']['certified_interval_m']==nearest,'T1_nearest_interval_three_contract_binding')
check(tasks['T1']['tolerance_m']==plan['tasks']['T1']['tolerance_m']==score['independent_answers']['T1']['answer_tolerance_m']==old_tasks['T1']['tolerance_m']==1e-6,'unchanged_1e_minus_6_tolerance')

task_normal=copy.deepcopy(tasks)
task_normal['T1']['distance_interval_m']=old_tasks['T1']['distance_interval_m'];task_normal['T1'].pop('distance_interval_source')
for name in intervals:
    task_normal['T1']['facts'][name]['distance_interval_m']=old_tasks['T1']['facts'][name]['distance_interval_m'];task_normal['T1']['facts'][name].pop('distance_interval_source')
check(task_normal==old_tasks,'tasks_only_T1_interval_binding_changed')
score_normal=copy.deepcopy(score)
for k in ['revision','common_precision_instruction']:score_normal.pop(k,None)
for k in ['distance_rule','text_format']:score_normal[k]=old_score[k]
t1=score_normal['independent_answers']['T1'];t1['certified_interval_m']=old_score['independent_answers']['T1']['certified_interval_m'];t1.pop('certified_interval_source')
for name in intervals:t1['required_pair_facts'][name]=old_score['independent_answers']['T1']['required_pair_facts'][name]
score_normal['independent_answers']['T3'].pop('representativeness')
check(score_normal==old_score,'score_other_requirements_thresholds_unchanged')
contract_normal=copy.deepcopy(contract);contract_normal.pop('contract_revision');contract_normal['shared_session_rules']=old_contract['shared_session_rules'];check(contract_normal==old_contract,'eval_contract_only_precision_metadata_changed')

input_rows=[]
for t,task in tasks.items():
    prompt=(R/task['prompt']).read_bytes();combined=rules+b'\n'+prompt;meta=plan['tasks'][t]
    check(sha(combined)==meta['model_input_sha256']==freeze['model_input_sha256'][t] and len(combined)==meta['model_input_bytes'],'three_complete_model_input_hashes',t)
    check(all(meta[k]==v for k,v in task.items()),'plan_tasks_exact_metadata',t)
    for k in ['prompt','asset','snapshot','truth']:check(task[k]==old_tasks[t][k] and task[k+'_sha256']==old_tasks[t][k+'_sha256'],'same_frozen_task_and_asset_metadata',t+'/'+k)
    check(sha(prompt)==task['prompt_sha256'],'same_original_task_prompt_bytes',t)
    input_rows.append({'task':t,'bytes':len(combined),'sha256':sha(combined)})
stable=['sequence','arms','logical_denominator','per_arm','task_count','repetitions_each_task_arm','model','requested_effort','max_session_seconds','total_cell_seconds','tool_attempts','physical_RPC_limit','tool_response_bytes','tool_timeout_s','code_bytes','images','model_retries','S_advancement_gates','first_request_valid_definition','adoption_classes','quality_dimensions','quality_before_cost','sampling','installation_ready','actor_sha256','consumer_transport_sha256','private_anonymous_map_sha256']
for k in stable:check(plan[k]==old_plan[k],'unchanged_schedule_budget_gate_or_native_setting',k)
check(len(plan['sequence'])==27 and Counter((x['task'],x['group'],x['round']) for x in plan['sequence'])==Counter({(t,g,n):1 for t in tasks for g in ['N','C','S'] for n in [1,2,3]}),'same_balanced_27_order')
for p,h in plan['dispatch_input_sha256'].items():check(H(R/p)==h,'current_dispatch_input_hash',p)
# Anonymous mapping is HASH ONLY: never decoded or inspected.
anon_path=R/'private/ANON_MAP.json';anon_digest=H(anon_path)
check(anon_digest==old_plan['private_anonymous_map_sha256']==plan['private_anonymous_map_sha256'],'anonymous_map_hash_only_unchanged')

native_paths=[REL+'/'+p for p in ['actor.py','consumer_transport.py','preflight_client.py','installation/READY.json','catalogues/C/PUBLIC_TOOLS.json','catalogues/S/PUBLIC_TOOLS.json','RUNNER_FINAL_BINDING.json']]
old_native,new_native=git_blobs(BASE,native_paths),git_blobs(COMMIT,native_paths)
for p in native_paths:check(old_native[p]==new_native[p]==(WT/p).read_bytes(),'native_capability_profiles_and_installation_unchanged',p)
source=L('SOURCE_REVIEW.json');manifest=source['files'];source_paths=[x['path'] for x in manifest];old_source,new_source=git_blobs(BASE,source_paths),git_blobs(COMMIT,source_paths)
check(len(source_paths)==len(set(source_paths))==137,'product_137_count')
for row in manifest:
    p=row['path'];check(old_source[p]==new_source[p]==(WT/p).read_bytes() and sha(new_source[p])==row['sha256'],'all_product_sources_unchanged',p)
identity=L('installation/receipt/INSTALLED_IDENTITY_STDOUT.json')['runtime_identity']
canonical=sha(json.dumps({'base_version':identity['base_version'],'implementation_revision':identity['implementation_revision'],'files':manifest},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
check(canonical==freeze['canonical']==plan['candidate_source_sha256']=='0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a','unchanged_product_canonical')

old_ast,new_ast=ast.parse(old_blobs[REL+'/driver.py']),ast.parse((R/'driver.py').read_bytes())
def nodes(tree):return {(n.name if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) else 'top_'+str(i)):ast.dump(n,include_attributes=False) for i,n in enumerate(tree.body)}
a,b=nodes(old_ast),nodes(new_ast);changed_nodes=sorted(k for k in a.keys()|b.keys() if a.get(k)!=b.get(k))
check(changed_nodes==['prepare','run_models'],'driver_only_clock_functions_changed')
clock=L('finalize_v2/clock_check_01/RESULTS.json')
check(clock['passed'] and len(clock['branches'])==2 and all(x['passed'] for x in clock['branches']) and not clock['blocked_attempts'] and clock['driver_sha256']==H(R/'driver.py')==plan['preflight_driver_sha256']==freeze['driver_sha256'] and clock['test_sha256']==H(R/'finalize_v2/test_clock_check.py'),'archived_finite_clock_check_binding')
check(plan['historical_preflight_9_commit']==plan['historical_dispatch_control_5_commit']==BASE and plan['preflight_record_sha256']==old_plan['preflight_record_sha256'] and plan['historical_dispatch_control_record_sha256']==old_plan['dispatch_control_record_sha256'] and plan['historical_dispatch_control_test_sha256']==old_plan['dispatch_control_test_sha256'],'old_preflight_control_not_relabelled_new')
modified=G('diff','--name-only',BASE,COMMIT).decode().splitlines()
allowed_old={REL+'/'+p for p in ['ARTIFACT_INDEX.json','EVAL_CONTRACT.json','FREEZE.json','PLAN.json','REPORT.md','SCORING_CONTRACT.json','SESSION_RULES.txt','SOURCE_REVIEW.json','TASKS.json','driver.py']}
check(all(p in allowed_old or p.startswith(REL+'/finalize_v2/') for p in modified),'no_asset_math_preflight_native_product_changes_in_commit')
check(freeze['plan_sha256']==H(R/'PLAN.json') and freeze['artifact_index_sha256']==H(R/'ARTIFACT_INDEX.json') and freeze['scoring_sha256']==H(R/'SCORING_CONTRACT.json') and freeze['original_archive_sha256']==H(R/'finalize_v2/ORIGINAL_ARCHIVE.json'),'current_freeze_bindings')
current_relevant=[REL+'/'+p for p in pins]+[REL+'/SESSION_RULES.txt',REL+'/SCORING_CONTRACT.json',REL+'/TASKS.json',REL+'/driver.py']
current_blobs=git_blobs(COMMIT,current_relevant)
for p,raw in current_blobs.items():check(raw==(WT/p).read_bytes(),'current_key_contract_Git_blob',p)
go=(R/'GO.json').exists();started=(R/'STARTED.json').exists();check(not go and not started,'real_GO_and_STARTED_absent')
report={'schema_version':1,'status':'passed' if not errors else 'requires_review','recommendation':'No source/contract-binding blocker to root issuing the reviewed V2 GO' if not errors else 'Resolve listed binding findings before GO','commit':COMMIT,'parent':BASE,'worktree_clean':not status,'pins':pins,'three_changes':['Same public precision instruction for all arms, original 205-byte prefix unchanged','Complete cell/batch clock; only prepare/run_models AST changed','T1 two separated and nearest intervals bound to existing WORLD_ROUNDOFF; 1e-6 tolerance unchanged'],'original_Git_copies_verified':14,'public_rules':{'original_bytes':205,'new_bytes':327,'original_prefix_exact':True,'precision_suffix_bytes':len(precision.encode('utf-8'))+1,'all_arms_same_by_task':True},'model_inputs':input_rows,'T1_interval_binding':{'source':'tasks/T1/run_01/WORLD_ROUNDOFF.json','sha256':H(roundoff_path),'pair_intervals':intervals,'nearest_interval':nearest,'answer_tolerance_m':1e-6,'math_rerun':False},'unchanged':{'source_count':137,'canonical':canonical,'sequence':27,'budgets_gates_denominators':True,'native_tool_capability_profiles_and_install':True,'anonymous_map_sha256_only':anon_digest,'anonymous_map_content_read':False},'clock_check':'Archived finite fake-clock result bound to current driver/test; not rerun and not a performance qualification','real_GO_exists':go,'real_STARTED_exists':started,'checks_performed':dict(checks),'errors':errors,'attempt_record':str(ATTEMPT),'not_run':['Full 978-member evidence rehash','Nine preflight services/Blender/model tests','Mathematical/oracle recalculation','New PID scan','Formal consumers or GO issuance'],'product_calls':0,'Blender_calls':0,'model_calls':0,'worktree_writes':0}
save(ATTEMPT,report);save(OUT/'BINDING_REVIEW.json',report)
print(json.dumps({'status':report['status'],'original_copies':14,'rules_bytes':len(rules),'model_inputs':input_rows,'product_sources':137,'driver_changed_functions':changed_nodes,'GO':go,'STARTED':started,'errors':errors,'report':str(OUT/'BINDING_REVIEW.json')},ensure_ascii=False))
