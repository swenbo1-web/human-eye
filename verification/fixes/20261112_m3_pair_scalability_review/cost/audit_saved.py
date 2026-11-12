"""Independent data-only M3 audit; no author verifier, solver, model or Blender invocation."""
from pathlib import Path
import ast,base64,hashlib,json,re,statistics,subprocess,zlib

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT=Path(__file__).resolve().parent
COMMIT='743a484f16f1dadff8dedcf1abad8d0a14398d17'
PRODUCT='3beb3f809674658b086e50af194adaa16e226111'
SOURCE='0770602e875c819dd424639fd7c750aaad4bca3bbe506aaf747ba337e5991139'
P='verification/m3_pair_scalability_001/'
R=P+'entry/run_01/'
checks=[]; provenance=[]
def need(ok,what):
    checks.append({'check':what,'passed':bool(ok)})
    if not ok:raise AssertionError(what)
def sha(x):return hashlib.sha256(x).hexdigest()
def git(*args,data=None):return subprocess.run(['git','-C',str(ROOT),*args],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
extra=['human_eye_plugin/surface_proximity.py','human_eye_plugin/surface_geometry.py','human_eye_plugin/task_query.py',
       'verification/m2_tight_directory_001/measurement/owned_native.py','verification/m1_task_entry_001_eval/preflight_client.py']
paths=git('ls-tree','-r','--name-only',COMMIT,'--',P).decode().splitlines()+extra
stream=git('cat-file','--batch',data=''.join(COMMIT+':'+p+'\n' for p in paths).encode())
fixed={};at=0
for p in paths:
    end=stream.index(b'\n',at);head=stream[at:end].decode().split();need(len(head)==3 and head[1]=='blob','Git blob '+p)
    size=int(head[2]);body=stream[end+1:end+1+size];at=end+size+2
    need(body==(ROOT/p).read_bytes(),'fixed Git equals checkout '+p);fixed[p]=body
    provenance.append({'path':p,'git_blob':head[0],'bytes':size,'sha256':sha(body)})
need(at==len(stream),'Git stream fully consumed')
def raw(p):return fixed[p]
def j(p):return json.loads(raw(p))
def lines(p):return [json.loads(x) for x in raw(p).splitlines() if x]
def stats(values):return {'n':len(values),'values':values,'median':statistics.median(values),'min':min(values),'max':max(values)}

complete=j(P+'COMPLETE.json');index=j(P+'INDEX.json')
need(complete['product_commit']==PRODUCT and complete['source_sha256']==SOURCE and complete['acceptance_status']=='failed_partial_capability','fixed candidate and failed admission')
need(sha(raw(P+'INDEX.json'))==complete['index_sha256'] and sha(raw(P+'REPORT.md'))==complete['report_sha256'],'completion hashes')
need(len(index['files'])==complete['indexed_files']==913,'913 indexed files')
for row in index['files']:
    indexed_path=row['path'] if row['path'].startswith('verification/') else P+row['path']
    need(len(raw(indexed_path))==row['bytes'] and sha(raw(indexed_path))==row['sha256'],'index '+row['path'])

frozen=j(P+'testing/FROZEN.json'); paired=j(P+'testing/paired_01/RESULTS.json');samples=paired['samples']
paired_binding=j(P+'testing/paired_01/INPUT_BINDINGS.json')
need(paired_binding['candidate_source_sha256']==SOURCE and len(paired_binding['manifests']['candidate'])==137,'kernel fixed candidate manifest and source identity')
cases=['Peer_000','Competing_001','Near_003','cube12/control']
order=[(case,rep['iteration'],role) for case in cases for rep in frozen['timing']['fixed_order'] for role in rep['order']]
need([(s['case'],s['iteration'],s['role']) for s in samples]==order and len(samples)==40,'all forty samples fixed alternating order')
need(paired['source_files_unchanged'] and paired['retries']==0 and paired['actual_samples']==paired['planned_samples']==40,'forty samples no retries source unchanged')
sample_paths=[p for p in paths if p.startswith(P+'testing/paired_01/') and re.search(r'_[1-5]_(reference|candidate)\.json$',p)]
need(len(sample_paths)==40,'forty individual raw sample files')
for s in samples:
    key=s['case'].replace('/','_')+'_'+str(s['iteration'])+'_'+s['role']
    need(j(P+'testing/paired_01/'+key+'.json')==s,'individual raw sample '+key)
    need(s['exception'] is None and s['complete_ns']<30_000_000_000,'no exception or deadline '+key)
    need(s['closed_ns']+s['surface_ns']<=s['complete_ns'],'nested phases '+key)
    need(s['surface']['measurement_valid'] and s['independent_verification']['surface_passed'],'surface measured plus stored certificate '+key)
    need(s['surface_work']['intersection_tests']==s['actual_function_entries']['surface'].get('surface_proximity._intersection',0),'actual expensive surface entries '+key)
    need(s['closed_work']['pair_tests']==s['actual_function_entries']['closed'].get('surface_proximity._intersection',0),'actual complete closed entries '+key)
    expected=s['role']=='reference' or s['case']=='cube12/control'
    need(s['complete_facts']==expected and s['closed']['measurement_valid']==expected,'complete fact state '+key)
    if not expected:
        need(s['closed']['reason']=='closed_solid_work_budget' and s['closed_work']['work_units']==262144
             and s['closed_work']['cross_pair_tests']==s['closed_work']['ray_tests']==0,'closed truncated self budget '+key)
    need('prepare_ns' not in s,'no standalone preparation timer '+key)
kernel=[]
for case in cases:
    arm={}
    for role in ('reference','candidate'):
        rows=[s for s in samples if (s['case'],s['role'])==(case,role)]
        arm[role]={'complete_ms':stats([s['complete_ns']/1e6 for s in rows]),'closed_ms':stats([s['closed_ns']/1e6 for s in rows]),
                   'surface_ms':stats([s['surface_ns']/1e6 for s in rows]),'complete_facts':sum(s['complete_facts'] for s in rows),
                   'surface_facts':sum(s['surface']['measurement_valid'] for s in rows),
                   'expensive_distance_leaves':[s['actual_function_entries']['surface'].get('surface_proximity._intersection',0) for s in rows],
                   'closed_work_first':rows[0]['closed_work'],'surface_work_first':rows[0]['surface_work'],
                   'callback_invocations_first':sum(rows[0]['checkpoint_counts'].values()),
                   'phase_residual_ms':[(s['complete_ns']-s['closed_ns']-s['surface_ns'])/1e6 for s in rows]}
    a,b=arm['reference'],arm['candidate']
    item={'case':case,'arms':arm,'same_complete_facts':a['complete_facts']==b['complete_facts']==5,
          'distance_leaf_change_percent':100*(b['expensive_distance_leaves'][0]/a['expensive_distance_leaves'][0]-1),
          'surface_phase_median_change_percent':100*(b['surface_ms']['median']/a['surface_ms']['median']-1)}
    if case=='Peer_000':need(a['expensive_distance_leaves']==[18791]*5 and b['expensive_distance_leaves']==[7324]*5 and max(b['expensive_distance_leaves'])<=9395,'Peer frozen expensive leaf gate')
    if case=='Competing_001':need(a['expensive_distance_leaves']==[1048]*5 and b['expensive_distance_leaves']==[1324]*5,'Competing regression kept')
    if case=='cube12/control':
        item['median_delta_ms']=b['complete_ms']['median']-a['complete_ms']['median']
        item['allowed_delta_ms']=max(1,a['complete_ms']['median']*.05)
        need(item['median_delta_ms']<=item['allowed_delta_ms'],'simple control finite timing gate')
    kernel.append(item)

# Reconstruct test method denominators from execution logs rather than SUMMARY.
reg=[]
for directory,count in [('final_regressions_01',128),('final_related_01',85)]:
    v=j(P+'testing/'+directory+'/RESULTS.json');text=raw(P+'testing/'+directory+'/TESTS.txt').decode()
    need(v['methods']==len(v['executed'])==count and len(set(v['executed']))==count,'actual executed test methods '+directory)
    need(v['passed'] and not v['failures'] and not v['errors'] and not v['skipped'] and not v['runner_exception'],'regression pass '+directory)
    need(v['source_sha256']==SOURCE and v['guard_verified'] and v['sources_unchanged'] and v['tests_unchanged'],'regression source '+directory)
    need(re.search(r'Ran '+str(count)+r' tests?',text) is not None,'unittest text denominator '+directory)
    reg.append({'run':directory,'methods':count,'files':len(v['test_files']),'source_sha256':v['source_sha256']})
mech=j(P+'testing/final_mechanisms_01/RESULTS.json');node=j(P+'testing/final_node_02/RESULTS.json')
norm=lambda x:x.split('.',1)[1].split(' (',1)[0]
original_methods={norm(x) for x in mech['executed']};original_bad={norm(x['test']) for x in mech['failures']+mech['errors']}
node_methods={norm(x) for x in node['executed']}
need(mech['methods']==len(original_methods)==15 and len(mech['failures'])==4 and len(original_bad)==2,'initial final mechanism fifteen methods four failure entries two methods')
need(node['methods']==len(node_methods)==3 and node['passed'] and not node['failures'] and not node['errors'] and node_methods<=original_methods,'same-scope three node method replay')
need(mech['source_sha256']==node['source_sha256']==SOURCE,'mechanism same product source')
remaining=original_bad-node_methods
need(len(remaining)==1 and any('test_g508_' in x for x in remaining),'effective fourteen of fifteen latest methods')
history=[]
for p in paths:
    if re.match(re.escape(P)+r'testing/[^/]+/RESULTS\.json$',p):
        v=j(p)
        if 'methods' in v:
            history.append({'run':p.split('/')[-2],'methods':v['methods'],'passed':v['passed'],'failure_entries':len(v['failures']),
                            'error_entries':len(v['errors']),'skips':len(v['skipped']),'runner_exception':v['runner_exception'],
                            'source_sha256':v['source_sha256']})

# Fresh ordinary MCP: parse actual raw TX/RX, exact public statuses, metadata and QA accounting.
result=j(R+'RESULTS.json');wire=j(R+'native/WIRE/INDEX.json');events=lines(R+'native/WORKER_EVENTS.jsonl');rpc=j(R+'product/RPC.json')
need(len(wire)==len(events)==5 and len(rpc['requests'])==7,'five host RPC seven stdio requests')
business=result['business'];need([b['request']['id'] for b in business]==['directory','assembly_task','control_task'],'three ordinary business calls fixed sequence')
host=[];windows=[('QA',result['QA_snapshot'])]+[(b['request']['id'],b) for b in business]
for i,meter in enumerate(wire,1):
    prefix=R+f'native/WIRE/{i:03d}/';tx=raw(prefix+'REQUEST.bin');rx=raw(prefix+'RESPONSE.bin');req=json.loads(tx);res=json.loads(rx);event=events[i-1]
    need(meter['request_bytes']==len(tx) and meter['response_attempted_bytes']==len(rx) and meter['response_sendall_completed'],'host raw bytes receipt '+str(i))
    owners=[name for name,w in windows if w['started_ns']<=event['started_ns']<=w['ended_ns']]
    need(len(owners)==(0 if i==5 else 1),'host owner '+str(i))
    if i<5:need(res['status']=='success' and event['status']=='completed' and event['script_error'] is None,'actual host execute success '+str(i))
    caps=[]
    for n in ast.walk(ast.parse(req.get('params',{}).get('code',''))):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='b64decode' and n.args and isinstance(n.args[0],ast.Constant) and isinstance(n.args[0].value,str):
            s=n.args[0].value;caps.append({'literal_bytes':len(s.encode()),'decoded_bytes':len(zlib.decompress(base64.b64decode(s)))})
    delta={}
    for side,sign in [('after',1),('before',-1)]:
        for module in event['m2_work'][side]:
            for k,v in module['work'].items():
                if type(v) is int:delta[k]=delta.get(k,0)+sign*v
    host.append({'sequence':i,'owner':owners[0] if owners else 'close','tx':len(tx),'rx':len(rx),
                 'source_capsules':caps,'worker_elapsed_ms':event['elapsed_ns']/1e6,'work':event['m2_work'],'product_counter_delta':delta})
stdio=[];bodies={}
for i,receipt in enumerate(rpc['requests'],1):
    prefix=R+f'product/{i:03d}/';tx=raw(prefix+'TX.bin');rx=raw(prefix+'RX.bin') if prefix+'RX.bin' in fixed else b'';req=json.loads(tx);res=json.loads(rx) if rx else None
    need(receipt==j(prefix+'RECEIPT.json') and receipt['sent_bytes']==len(tx) and receipt['received_bytes']==len(rx) and receipt['send_confirmed'] and receipt['error'] is None,'stdio actual receipt '+str(i))
    if res:need(res['id']==req['id'] and 'error' not in res,'stdio identity '+str(i))
    if i>=5:
        b=business[i-5];label=req['id']
        need(req==b['request']==j(R+label+'_REQUEST.json') and res==b['response']==j(R+label+'_RESULT.json')['response'],'business exact request response '+label)
        need(b['classification']=='tool_response' and not res['result']['isError'],'business no transport error '+label)
        bodies[label]=json.loads(res['result']['content'][0]['text']);need(bodies[label]==b['body'],'public exact body '+label)
        need(b['tool_ns']==b['ended_ns']-b['started_ns'],'business timing '+label)
    stdio.append({'sequence':i,'id':req.get('id'),'method':req['method'],'tx':len(tx),'rx':len(rx),'elapsed_ms':receipt['elapsed_ns']/1e6})
need(sum(x['tx'] for x in stdio)==rpc['tx_bytes'] and sum(x['rx'] for x in stdio)==rpc['rx_bytes'],'stdio raw totals')
initialized=j(R+'product/001/RX.bin')
need(initialized==j(R+'INITIALIZE.json') and initialized['result']['_meta']['human_eye']['source_sha256']==SOURCE,'actual initialization fixed runtime identity')
need(all(b['binding']['runtime_source_sha256']==SOURCE for b in bodies.values()),'all public facts bound candidate runtime source')
need(sum(bool(x['rx']) for x in stdio)==6 and len(stdio[:4])==4 and max(r['started_ns']+r['elapsed_ns'] for r in rpc['requests'][:4])<events[0]['started_ns'],'metadata four/three no host events')
need(bodies['directory']['status']=='complete' and len(bodies['directory']['objects'])==14,'directory 14 complete')
assembly=bodies['assembly_task'];control=bodies['control_task'];need(len(assembly['pairs'])==3 and assembly['status']=='partial','three actual partial pairs')
for pair in assembly['pairs']:
    f=pair['facts'];need(f['surface_proximity']['status']=='measured' and f['closed_solid_relation']['status']=='unknown'
      and f['closed_solid_relation']['reason']=='closed_solid_work_budget' and pair['separation_gap']['status']=='unknown','actual distance measured closed unknown '+str(pair['candidate_index']))
need(not assembly['summary']['nearest_separated_complete'] and assembly['summary']['nearest_separated_ids'] is None,'actual full nearest unknown')
need(control['status']=='observed' and control['summary']['nearest_separated_complete'] and control['summary']['distance_m']==1.0,'actual control complete')
qa=j(R+'QA_SNAPSHOT_RECEIPT.json');snapshot=j(R+'ACTUAL_SNAPSHOT.json')
need(qa['response']==j(R+'native/WIRE/001/RESPONSE.bin') and json.loads(qa['response']['result']['result'])==snapshot,'actual QA raw equality')
need(sha(raw(R+'ACTUAL_SNAPSHOT.json'))=='29dfdccd839170b70ec03339925323d433b5e4221d1caac6649b2060fefa453c','same frozen evaluated snapshot')
need(result['errors']==[] and result['harness_execution_complete'] and result['business_passed'] is None,'harness completion does not imply business pass')
proof=j(R+'PRODUCT_RUNTIME_PROOF.json');pc=j(R+'product/CLOSE.json');nc=result['native_close'];rxexit=result['product_runtime_exit']
need(proof==result['product_runtime_proof'] and proof['confirmed'] and proof['runtime_pid']!=proof['launcher_pid'] and proof['parent_chain'][0]['parent_pid']==proof['launcher_pid'],'actual runtime ownership distinct from launcher')
need(pc==result['product_close'] and pc['exit_code']==0 and pc['process_reaped'] and pc['reader_stopped'],'launcher exit0')
need(rxexit['confirmed'] and rxexit['exited'] and rxexit['exit_code']==0 and rxexit['handle_closed'],'real runtime exit0 retained handle')
need(nc['response']==j(R+'native/WIRE/005/RESPONSE.bin') and nc['response']['status']=='closed' and nc['exit_code']==0 and nc['process_reaped'] and nc['error'] is None,'real Blender close raw and owned reap')
need(result['closed']==j(R+'native/WORKER_CLOSED.json') and not result['closed']['poisoned'] and result['closed']['initial_geometry_fingerprint']==result['closed']['final_geometry_fingerprint'],'Blender unchanged fingerprint')
need(j(P+'entry/FORMAL_PROCESS.json')['exit_code']==0 and j(P+'entry/FORMAL_STARTED.json')['started_ns']==result['started_ns'],'formal process and marker')
need({p.split('/')[3] for p in paths if p.startswith(P+'entry/run_') and len(p.split('/'))>4}=={'run_01'},'one actual MCP sequence no replay directory')
need(result['ended_ns']-result['started_ns']==result['session_wall_ns'],'session anchor exact')
timing={'business_ms':{b['request']['id']:b['tool_ns']/1e6 for b in business},'business_sum_ms':sum(b['tool_ns'] for b in business)/1e6,
        'session_ms':result['session_wall_ns']/1e6,'formal_process_ms':j(P+'entry/FORMAL_PROCESS.json')['elapsed_ms'],
        'stages_ms':{k:v/1e6 for k,v in result['timing_stages_ns'].items()},
        'unassigned_session_residual_ms':(result['session_wall_ns']-sum(result['timing_stages_ns'].values())-sum(b['tool_ns'] for b in business))/1e6,
        'QA_row_ms':(result['QA_snapshot']['ended_ns']-result['QA_snapshot']['started_ns'])/1e6,'QA_inner_receipt_ms':qa['elapsed_ns']/1e6}

output={'fixed_commit':COMMIT,'product_commit':PRODUCT,'source_sha256':SOURCE,'source_files':len(provenance),'check_count':len(checks),'passed':True,
 'kernel_samples':40,'kernel':kernel,'regressions':reg,'mechanisms':{'first_run_methods':15,'first_run_failed_methods':sorted(original_bad),'first_run_failure_entries':4,
 'node_replay_methods':3,'latest_method_passes':14,'latest_method_total':15,'remaining_failed_methods':sorted(remaining),'remaining_failure_entries':3},
 'test_history':history,'host':host,'stdio':stdio,'host_totals':{'RPC':5,'TX':sum(h['tx'] for h in host),'RX':sum(h['rx'] for h in host)},
 'stdio_totals':{'TX_messages':7,'RX_messages':6,'TX':sum(h['tx'] for h in stdio),'RX':sum(h['rx'] for h in stdio)},'MCP_timing':timing,
 'actual_assembly_summary':assembly['summary'],'lifecycle':{'proof':proof,'runtime_exit':rxexit,'Blender':nc},
 'findings':[{'level':'scope_correction','issue':'REPORT says separate preparation timing; no prepare_ns exists; preparation is inside closed_ns.'},
 {'level':'interpretation','issue':'G508 candidate missing all closed facts. Shorter complete_ns is not same-fact acceleration.'},
 {'level':'interpretation','issue':'Counters differ by kind, batch amount, budget failure boundary and old/new instrumentation; callbacks or work units are not universal CPU operations.'}],
 'execution':{'product_calls':0,'Blender_starts':0,'models':0,'author_verifier_calls':0,'product_imports':0},
 'AL':{'own_context_handle':'963c85c7011a4c0382217460eac60535','context_bound':True,'assignment_current':False,'parent_read_only':True,'parent_task':'6631abd2-5541-4773-9042-a8b61b507223','parent_task_not_modified':True}}
for filename,value in [('RESULTS.json',output),('CHECKS.json',checks),('SOURCES.json',provenance)]:
    (OUT/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'passed':True,'checks':len(checks),'sources':len(provenance),'kernel':[{'case':x['case'],'reference_ms':x['arms']['reference']['complete_ms']['median'],
 'candidate_ms':x['arms']['candidate']['complete_ms']['median'],'reference_surface_ms':x['arms']['reference']['surface_ms']['median'],'candidate_surface_ms':x['arms']['candidate']['surface_ms']['median'],
 'leaf_delta_pct':x['distance_leaf_change_percent'],'same_complete_facts':x['same_complete_facts']} for x in kernel],
 'host':output['host_totals'],'stdio':output['stdio_totals'],'MCP_timing':timing},ensure_ascii=False,indent=2))
