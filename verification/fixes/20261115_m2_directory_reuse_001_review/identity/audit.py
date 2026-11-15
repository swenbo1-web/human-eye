"""Independent offline identity audit. Never imports or executes project code."""
import hashlib, json, pathlib, subprocess

R = pathlib.Path('C:/Users/Administrator/.codex/worktrees/m2-dir-001/hefe')
N = R / 'verification/m2_directory_resource_reuse_001'
O = pathlib.Path('D:/hefe/verification/fixes/20261115_m2_directory_reuse_001_review/identity')
BASE = '8f2a739e789b777358d84a168154bc7c50b929e5'
HEAD = 'fde0e9ab21fb6eaee1750befd64ad1bebdde2961'
checks = []; files = {}
def data(path):
    p = pathlib.Path(path).resolve()
    if p not in files: files[p] = p.read_bytes()
    return files[p]
def sha(path): return hashlib.sha256(data(path)).hexdigest()
def read(path): return json.loads(data(path))
def check(group, label, value): checks.append({'group':group,'label':label,'passed':bool(value)})
def git(*args): return subprocess.check_output(['git',*args], cwd=R)

check('git','HEAD',git('rev-parse','HEAD').decode().strip()==HEAD)
check('git','clean',git('status','--porcelain')==b'')
check('git','branch',git('branch','--show-current').decode().strip()=='codex/m2-directory-resource-reuse-001')
manifest=read(N/'CONTENT_MANIFEST.json')
names={v['path'] for v in manifest['files']}|{(N/'CONTENT_MANIFEST.json').relative_to(R).as_posix()}
changes=git('diff','--name-status','-z',BASE,HEAD).decode().split('\0')
changes=[v for v in changes if v]
check('git','27 namespace-only additions',len(changes)==54 and changes[::2]==['A']*27 and set(changes[1::2])==names and all(n.startswith('verification/m2_directory_resource_reuse_001/') for n in names))
check('manifest','26 content entries and sum',len(manifest['files'])==manifest['file_count']==26 and sum(v['bytes'] for v in manifest['files'])==manifest['bytes'])
for row in manifest['files']:
    check('manifest',row['path'],sha(R/row['path'])==row['sha256'] and len(data(R/row['path']))==row['bytes'])
tree={}
for row in git('ls-tree','-r','-z',HEAD).split(b'\0'):
    if row:
        info,name=row.split(b'\t',1);tree[name.decode()]=info.split()[2].decode()
for name in names:
    value=data(R/name)
    check('git_blob',name,hashlib.sha1(b'blob '+str(len(value)).encode()+b'\0'+value).hexdigest()==tree[name])
audit=read(N/'FINAL_AUDIT.json')
for name,digest in audit['artifacts_sha256'].items():check('final_artifact',name,sha(N/name)==digest)
base=read(N/'BASELINE.json')
for name,digest in base['protected_old_pins'].items():check('protected_old_pin',name,sha(name)==digest)

binding=read(R/'verification/m1_source_face_binding_001/build/RUN_BINDING.json')
check('source','exact141/install',len(binding['source_manifest'])==141 and pathlib.Path(binding['install_root'])==pathlib.Path('D:/he_source_face_001/product'))
for row in binding['source_manifest']:
    name=row['path'];value=git('show',BASE+':'+name)
    check('source',name,hashlib.sha256(value).hexdigest()==row['sha256']==sha(R/name)==sha(pathlib.Path(binding['install_root'])/name))
identity={key:binding[key] for key in ['base_version','implementation_revision']};identity['files']=binding['source_manifest']
check('source','aggregate',hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==binding['source_sha256']==audit['product_source_aggregate']=='3748d88b618db7de1347d632f2a68f3ed82a2ebb8a6321586fe756be07ea8148')

source=read(N/'SOURCE_ELIGIBILITY_REVIEW.json')
for row in source['evidence_pins']+source['source_inventory']:
    p=pathlib.Path(row['path']);p=p if p.is_absolute() else R/p
    check('targeted_evidence_pin',row['path'],sha(p)==row['sha256'])
plan=data(N/'ADMINISTRATOR_PLAN.md').decode()
check('plan','fixed plan/explicit exit',sha(N/'ADMINISTRATOR_PLAN.md')==base['administrator_plan_sha256']=='19c991d42ac17d0b8e38cfe7286c2c4c28fc4dd554c2e25c29fd52cc41d2cf21' and '交付not_actionable并结束本批' in plan)

def packets(obj):
    if isinstance(obj,dict):
        if obj.get('schema')=='human-eye-directory-v1':yield obj
        else:
            for v in obj.values():yield from packets(v)
    elif isinstance(obj,list):
        for v in obj:yield from packets(v)
    elif isinstance(obj,str):
        try: decoded=json.loads(obj)
        except (ValueError,TypeError):return
        if not isinstance(decoded,str):yield from packets(decoded)
def directory(path):
    found={json.dumps(v,sort_keys=True):v for v in packets(read(path))}
    if len(found)!=1:raise ValueError('Expected one directory packet: '+str(path))
    return next(iter(found.values()))

old=R/'verification/m2_tight_directory_001/correctness'
for case in ['entry_01','entry_02']:
    cold=directory(old/case/'directory_cold.RESPONSE.json')
    after=directory(old/case/'directory_after_full.RESPONSE.json')
    check('raw_cache_control',case,cold['cache_hit'] is False and after['cache_hit'] is True and cold['capture_state']==after['capture_state'])
typed=old/'typed_01'
check('raw_cache_control','typed byte equality',data(typed/'directory_after_selected.json')==data(typed/'directory_hot.json') and read(typed/'directory_after_selected.json')['cache_hit'] is True)

bridge=R/'verification/m4_active_observation_host_bridge_001';actual=bridge/'external_archive/run/acceptance_02'
request=read(actual/'stdio/rpc_08/TX.bin');protocol=read(bridge/'HARNESS_PROTOCOL.json')
packet=directory(actual/'stdio/rpc_08/RX.bin');capture=read(actual/'server/CAPTURE_03.json')
check('raw_technical','request was frozen compatibility control',request['id']=='old_readonly_regression' and request['params']['arguments']['query']=={'mode':'directory'} and protocol['fixed_requests'][-1]['id']==request['id'])
check('raw_technical','real directory miss',packet['cache_hit'] is False and packet['result_kind']=='scene_directory')
check('raw_technical','same generation',all(packet['capture_state'][k]==capture['capture_state'][k] for k in ['instance_id','epoch','revision']))
check('raw_technical','same object incarnation',packet['binding']['host_identity']['object_instances']==capture['host_identity']['object_instances'])
check('raw_technical','historical host source=current',packet['binding']['host_source_sha256']==sha(R/'human_eye_plugin/blender_host.py'))
runner=data(bridge/'run_acceptance_r2.py').decode().splitlines()
runner_lines=[{'line':i+1,'text':line} for i,line in enumerate(runner) if 218<=i<=228]

m2=read(N/'M2_TRACE_REVIEW.json');den=m2['denominators'];m4=read(N/'M4_TRACE_REVIEW.json');decision=read(N/'DECISION.json')
check('recorded_denominator','42/368/139/98/41',len(m2['cases'])==den['actual_host_task_sessions']==42 and den['read_business_records']==368 and den['product_directory_records']==139 and den['product_directory_cache']=={'hit':98,'miss':41})
check('recorded_denominator','three existing-hit cases',len(m2['candidates'])==3 and all(v['record']['packet']['cache_hit'] is True for v in m2['candidates']))
check('recorded_denominator','one technical, zero qualified',m4['technical_reuse_opportunity_count']==decision['historical_real_host_technical_examples']==1 and m2['natural_task_hit_count']==m4['qualified_natural_task_hits']==decision['qualified_natural_task_hits']==0)
check('recorded_denominator','unknown retained',decision['complete_performance_benefit'] is None and decision['coordinator_reviewer_model_tokens_and_cash'] is None)
check('zero_product','no product candidate or test runtime',decision['product_modified'] is False and decision['candidate_count']==0 and decision['formal_comparison']['actual_slots']==0 and not pathlib.Path('D:/he_directory_reuse_001').exists())
check('AL','author pending not registered',base['AL']['task_registration']=='pending_current_chat_host_binding' and base['AL']['task_write_calls']==0 and read(N/'AL_COMPLETION_CONTEXT.json')['actual_response']['context_bound'] is False)
groups={}
for row in checks:groups[row['group']]=groups.get(row['group'],0)+1
result={'passed':all(v['passed'] for v in checks),'checks':len(checks),'groups':groups,'failures':[v for v in checks if not v['passed']], 'unique_read_files':len(files),'baseline':BASE,'head':HEAD,'selected_runner_lines':runner_lines,'new_product_model_Blender_raster_calls':0,'limitations':['Did not rerun the authors 4702-file M2, 1622-file M4, 2221-file context or prior M1 archive matrices. All 12 major old pins plus 27 source/evidence pins were checked; three raw cache cases and one raw technical case inspected.','Recorded session/task inventory totals checked for internal agreement only, not independently re-enumerated as raw host events.','Zero calls are independently true of this reviewer. Author no-call statements cannot prove an absence of unrecorded external execution; namespace-only Git changes, unchanged 141-source install and no candidate runtime independently checked.','Own AL handle resolves to stale prior-task assignment(current=false); parent task is current but not a substitute for child registration.']}
O.mkdir(parents=True,exist_ok=True)
with (O/'RESULT.json').open('x',encoding='utf8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({k:result[k] for k in ['passed','checks','groups','failures','unique_read_files']},ensure_ascii=False))
