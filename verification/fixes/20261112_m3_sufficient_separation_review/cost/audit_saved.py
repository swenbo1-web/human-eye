"""Independent immutable-data cost/status audit. Never runs project code or host tools."""
from pathlib import Path
from fractions import Fraction as F
import ast,hashlib,json,math,re,statistics,subprocess

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT=Path(__file__).resolve().parent
COMMIT='189ecdb84185d96c3ed0d75ca268bc16d6d4999b'
PRODUCT='e836e03f4b3821f869c72ac3e50df5204f28b50f'
SOURCE='2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390'
P='verification/m3_sufficient_separation_001/'
R=P+'entry/run_01/'
QUAL='verification/spatial_task_qualification_001/'
checks=[];sources=[]
def need(value,label):
    checks.append({'check':label,'passed':bool(value)})
    if not value:raise AssertionError(label)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def git(*args,data=None):return subprocess.run(['git','-C',str(ROOT),*args],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
extra=[QUAL+'entry/run_01/ACTUAL_SNAPSHOT.json',QUAL+'oracle/formal_replay_01/ORACLE.json',
 'verification/m3_pair_scalability_001/testing/run_paired_kernel.py',
 'verification/m2_tight_directory_001/measurement/owned_native.py',
 'verification/m1_task_entry_001_eval/preflight_client.py']
paths=git('ls-tree','-r','--name-only',COMMIT,'--',P).decode().splitlines()+extra
stream=git('cat-file','--batch',data=''.join(COMMIT+':'+p+'\n' for p in paths).encode());at=0;fixed={}
for path in paths:
    end=stream.index(b'\n',at);head=stream[at:end].decode().split();need(len(head)==3 and head[1]=='blob','Git blob '+path)
    size=int(head[2]);value=stream[end+1:end+1+size];at=end+size+2
    need(value==(ROOT/path).read_bytes(),'Git same bytes '+path);fixed[path]=value
    sources.append({'path':path,'git_blob':head[0],'bytes':size,'sha256':sha(value)})
need(at==len(stream),'Git stream consumed')
def raw(p):return fixed[p]
def j(p):return json.loads(raw(p))
def lines(p):return [json.loads(x) for x in raw(p).splitlines() if x]
def stats(x):return {'n':len(x),'values':x,'median':statistics.median(x),'min':min(x),'max':max(x)}

complete=j(P+'COMPLETE.json');index=j(P+'INDEX.json')
need(complete['product_commit']==PRODUCT and complete['source_sha256']==SOURCE,'product identity')
need(sha(raw(P+'INDEX.json'))==complete['index_sha256'] and sha(raw(P+'REPORT.md'))==complete['report_sha256'],'complete checksums')
need(len(index['files'])==complete['indexed_files']==623,'623 indexed files')
for item in index['files']:
    path=item['path'] if item['path'].startswith('verification/') else P+item['path']
    need(len(raw(path))==item['bytes'] and sha(raw(path))==item['sha256'],'index '+path)

frozen=j(P+'testing/FROZEN.json');design=j(P+'testing/DESIGNED_CASES.json');sequence=j(P+'testing/TIMING_SEQUENCE.json')['calls']
need(sha(raw(P+'testing/DESIGNED_CASES.json'))==frozen['designed_cases_sha256'] and sha(raw(P+'testing/TIMING_SEQUENCE.json'))==frozen['sequence_sha256'],'frozen design and sequence')
snap=j(QUAL+'entry/run_01/ACTUAL_SNAPSHOT.json');objects={o['name']:o for o in snap['objects']}
oracle=j(QUAL+'oracle/formal_replay_01/ORACLE.json')
truth={ 'G508/'+p['candidate_name']:('separated',[p['distance_lower_m'],p['distance_upper_m']]) for p in oracle['pairs']}
cases={'G508/'+name:(objects['Target'],objects[name]) for name in design['g508']['candidates']}
cases['simple_control']=(design['simple_control']['left'],design['simple_control']['right']);truth['simple_control']=('separated',[1.,1.])
for name in ('fallback_intersecting_bars','fallback_full_containment'):
    pair=next(p for p in design['analytic_pairs'] if p['id']==name)
    cases[name]=(pair['left'],pair['right']);truth[name]=(pair['independent_truth']['relation'],[pair['independent_truth']['distance_m']]*2)

def exact_rank(surface):
    a,b,e=surface['_exact_distance_sq'];return F(a,b)*(F(2)**e)

def check_support(bundle,diagnostics,left,right,label):
    proof=bundle['spatial']['support_evidence'];direction=proof['primitive_direction']
    a,b=bundle['surface']['point_a_world'],bundle['surface']['point_b_world']
    differences=[F(y)-F(x) for x,y in zip(a,b)];scale=math.lcm(*(x.denominator for x in differences))
    ints=[int(x*scale) for x in differences];g=math.gcd(*ints)
    need(g>0 and [x//g for x in ints]==direction,'exact sole public direction '+label)
    origin=[F(*x) for x in proof['origin']];factor=proof['factor'];supports=[];refs=[]
    for obj in (left,right):
        ids=sorted({v for face in obj['triangles'] for v in face});refs.append(ids)
        values={}
        for idx in ids:
            p=[(F(v)-o)*factor for v,o in zip(obj['vertices_world'][idx],origin)]
            need(all(v.denominator==1 for v in p),'exact source integer frame '+label+'/'+str(len(supports))+'/'+str(idx))
            values[idx]=sum(d*v for d,v in zip(direction,p))
        supports.append(values)
    need(proof['referenced_counts']==[len(x) for x in refs],'all referenced source counts '+label)
    need(max(supports[0].values())==proof['left_max'] and min(supports[1].values())==proof['right_min'] and proof['right_min']>proof['left_max'],'strict full reference support '+label)
    need(supports[0][proof['left_vertex_index']]==proof['left_max'] and supports[1][proof['right_vertex_index']]==proof['right_min'],'support witnesses source indices '+label)
    work=diagnostics['support_work'];n=sum(len(x) for x in refs)
    need(work['support_source_vertices']==work['support_vertex_dots']==n and work['support_direction_components']==3 and work['work_units_after']-work['work_units_before']==2*n+3,'exact support cost 2V+3 '+label)

sixty=j(P+'testing/sixty_01/RESULTS.json');rows=sixty['samples'];binding=j(P+'testing/sixty_01/INPUT_BINDINGS.json')
need(len(rows)==len(sequence)==sixty['actual_calls']==sixty['fixed_calls']==60 and sixty['retries']==0,'exact 60 timed calls no retry')
need(binding['candidate_commit']==sixty['candidate_commit']==PRODUCT and binding['candidate_source_sha256']==SOURCE,'timed source identity')
need(binding['additional_spies'] is False and binding['per_checkpoint_dictionary'] is False,'declared unprofiled timing')
need(sixty['source_files_unchanged'] and sixty['preparation_files_unchanged'],'same source and preparation')
marker=j(P+'testing/TIMING_STARTED.json');need(marker['input_bindings_sha256']==sha(raw(P+'testing/sixty_01/INPUT_BINDINGS.json')) and marker['calls']==60,'one timing reservation')
# Static primary-runner audit: wrappers defined in a reused loader are not invoked.
tree=ast.parse(raw(P+'testing/run_sixty.py'));callnames=[]
for node in ast.walk(tree):
    if isinstance(node,ast.Call):callnames.append(node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else '')
need(not set(callnames)&{'work_spy','setprofile','patch','counted'},'no QA spy invoked by primary runner')
checkpoint=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='checkpoint')
need(not any(isinstance(n,(ast.Assign,ast.AugAssign)) for n in ast.walk(checkpoint)),'primary deadline callback has no counting dictionary')
timed=[];ranks={}
for slot,row in zip(sequence,rows):
    need(all(row[k]==v for k,v in slot.items()),'frozen sequence slot '+str(slot['sequence']))
    stem=f"{slot['sequence']:02d}_{slot['arm']}";label=slot['case']+'/'+stem
    need(j(P+'testing/sixty_01/'+stem+'.json')==row,'individual sample raw '+label)
    payload=raw(P+'testing/sixty_01/'+stem+'.PAYLOAD.bin');decoded=json.loads(payload)
    need(len(payload)==row['payload_UTF8_bytes'] and sha(payload)==row['payload_sha256'],'actual payload bytes/hash '+label)
    need(decoded['result']==row['result'] and decoded['diagnostics']==row['diagnostics'],'actual complete payload semantics '+label)
    need(decoded['requested_facts']==(['closed_solid_relation','surface_proximity'] if slot['arm']=='reference' else ['spatial_relation','surface_proximity']),'explicit different fact contract '+label)
    need(row['original_deadline_ns']-row['started_ns']==30_000_000_000 and row['ended_ns']<row['original_deadline_ns'] and row['error'] is None and row['within_original_30s'],'original deadline through encoding '+label)
    need(row['complete_business_ns']==row['ended_ns']-row['started_ns'] and set(row['timing_stages_ns'])=={'input_preparation_ns','query_preparation_ns','solving_ns','serialization_ns'},'explicit complete timing anchors '+label)
    need(row['timing_residual_ns']==row['complete_business_ns']-sum(row['timing_stages_ns'].values()) and row['timing_residual_ns']>=0,'nonoverlap timing stages '+label)
    result=row['result'];relation=result['closed'] if slot['arm']=='reference' else result['spatial'];surface=result['surface'];expected,interval=truth[slot['case']]
    need(relation['measurement_valid'] and relation['relation']==expected and surface['measurement_valid'] and surface['witness_status']=='measured','both business facts valid '+label)
    need(interval[0]-1e-6<=surface['distance_m']<=interval[1]+1e-6,'distance independent interval '+label)
    need(abs(sum((a-b)**2 for a,b in zip(surface['point_a_world'],surface['point_b_world']))-surface['distance_m']**2)<=max(1e-18,2e-9*max(1,surface['distance_m'])),'public witness distance consistency '+label)
    ranks[(slot['arm'],slot['iteration'],slot['case'])]=exact_rank(surface)
    if slot['arm']=='candidate':
        need(result['measurement_valid'] and not result['budget_stopped'],'candidate whole pair valid '+label)
        if expected=='separated':
            need(result['closed'] is None and row['diagnostics']['closed_solid_pair_count']==0 and relation['certificate']=='strict_all_referenced_vertex_support','sufficient certificate no closed work '+label)
            check_support(result,row['diagnostics'],*cases[slot['case']],label)
        else:need(result['closed']['measurement_valid'] and row['diagnostics']['closed_solid_pair_count']==1,'one valid fallback '+label)
    timed.append({'sequence':slot['sequence'],'case':slot['case'],'arm':slot['arm'],'iteration':slot['iteration'],'total_ms':row['complete_business_ns']/1e6,'payload_bytes':len(payload),'stage_ms':{k:v/1e6 for k,v in row['timing_stages_ns'].items()},'residual_ms':row['timing_residual_ns']/1e6})
for arm in ('reference','candidate'):
    for iteration in range(1,6):
        keys=[ranks[(arm,iteration,'G508/'+name)] for name in design['g508']['candidates']]
        need(keys[0]<keys[1]<keys[2] and [x>=F(1,250)**2 for x in keys]==[False,True,True],'exact rank/4mm '+arm+str(iteration))
summaries=[]
for case in cases:
    arms={arm:{'total_ms':stats([r['total_ms'] for r in timed if (r['case'],r['arm'])==(case,arm)]),
      'payload_bytes':stats([r['payload_bytes'] for r in timed if (r['case'],r['arm'])==(case,arm)]),
      'stages_ms':{key:stats([r['stage_ms'][key] for r in timed if (r['case'],r['arm'])==(case,arm)]) for key in rows[0]['timing_stages_ns']}} for arm in ('reference','candidate')}
    need(all(a['total_ms']['n']==5 for a in arms.values()),'five repetitions each arm '+case)
    ref=arms['reference']['total_ms']['median'];cand=arms['candidate']['total_ms']['median']
    gate=0 if case.startswith('G508/') else max(1,ref*.05) if case=='simple_control' else max(2,ref*.1)
    need(cand-ref<=gate,'frozen individual cost gate '+case)
    summaries.append({'case':case,'arms':arms,'candidate_delta_ms':cand-ref,'allowed_delta_ms':gate,'passed':True})
refsum=sum(s['arms']['reference']['total_ms']['median'] for s in summaries if s['case'].startswith('G508/'))
candsum=sum(s['arms']['candidate']['total_ms']['median'] for s in summaries if s['case'].startswith('G508/'))
need(candsum<=refsum*.8,'G508 aggregate >=20 percent reduction')
need(sixty['batch_wall_ns']==sixty['batch_ended_ns']-sixty['batch_started_ns'],'batch elapsed exact')
need(len(sixty['evidence_publication'])==60,'all evidence publication records')

work=j(P+'testing/initial_work_01/RESULTS.json')
need(work['actual_calls']==work['fixed_expected_calls']==len(work['cases'])==6 and work['performance_samples']==0 and work['retries']==0 and work['source_sha256']==SOURCE,'six separate candidate-only work observations')
for n,row in enumerate(work['cases']):
    name=row['case'];calls=row['actual_function_calls'];d=row['diagnostics']
    need(j(P+'testing/initial_work_01/'+name+'.json')==row and row['error'] is None,'individual non-timing observation '+name)
    need(all(calls['surface_proximity.'+k]==1 for k in ('measure_surface_proximity','_admit','_integer_frame','_referenced_support_evidence','_public_support_direction')),'single pass observed '+name)
    if n<4:
        need(all(calls['surface_geometry.'+k]==0 for k in ('classify_closed_solids','_closed_validate_embedded','_closed_candidate_trees','_closed_cone_metadata')),'actual closed spies zero '+name)
        need(d['support_work']['work_units_after']-d['support_work']['work_units_before']==[1027,579,579,35][n],'support incremental count '+name)
    else:need(calls['surface_geometry.classify_closed_solids']==1 and d['closed_solid_work']['prepared_pair_reused'],'one fallback prepared reuse '+name)

reg=[]
for folder,count in [('initial_regressions_01',213),('initial_directed_01',8),('initial_wiring_01',9)]:
    v=j(P+'testing/'+folder+'/RESULTS.json')
    need(v['methods']==len(v['executed'])==len(set(v['executed']))==count and v['passed'] and not v['failures'] and not v['errors'] and not v['skipped'] and v['runner_exception'] is None,'actual test methods pass '+folder)
    need(v['source_sha256']==SOURCE and v['guard_verified'] and v['sources_unchanged'] and v['tests_unchanged'],'test same candidate source '+folder)
    need(re.search(r'Ran '+str(count)+r' tests?',raw(P+'testing/'+folder+'/TESTS.txt').decode()) is not None,'raw unittest count '+folder)
    reg.append({'run':folder,'methods':count,'test_files':v['test_files']})

result=j(R+'RESULTS.json');rules=j(P+'entry/QUERY_RULES.json');events=lines(R+'native/WORKER_EVENTS.jsonl');wire=j(R+'native/WIRE/INDEX.json');rpc=j(R+'product/RPC.json')
need([b['request']['id'] for b in result['business']]==rules['sequence']==['directory','spatial_assembly_task','legacy_assembly_task','spatial_control_task'],'new before old exact four business order')
need(len(wire)==len(events)==6 and len(rpc['requests'])==8,'actual six host RPC eight stdio messages')
host=[];windows=[('QA',result['QA_snapshot'])]+[(b['request']['id'],b) for b in result['business']]
for n,meter in enumerate(wire,1):
    prefix=R+f'native/WIRE/{n:03d}/';tx=raw(prefix+'REQUEST.bin');rx=raw(prefix+'RESPONSE.bin');response=json.loads(rx);e=events[n-1]
    need(meter['request_bytes']==len(tx) and meter['response_attempted_bytes']==len(rx) and meter['response_sendall_completed'],'host raw receipt '+str(n))
    owners=[name for name,w in windows if w['started_ns']<=e['started_ns']<=w['ended_ns']];need(len(owners)==(0 if n==6 else 1),'host owner '+str(n))
    if n<6:need(response['status']=='success' and e['status']=='completed' and e['script_error'] is None,'actual host success '+str(n))
    host.append({'sequence':n,'owner':owners[0] if owners else 'close','TX':len(tx),'RX':len(rx),'work':e['m2_work'],'worker_ms':e['elapsed_ns']/1e6})
stdio=[];bodies={}
for n,receipt in enumerate(rpc['requests'],1):
    prefix=R+f'product/{n:03d}/';tx=raw(prefix+'TX.bin');rx=raw(prefix+'RX.bin') if prefix+'RX.bin' in fixed else b'';req=json.loads(tx);res=json.loads(rx) if rx else None
    need(receipt==j(prefix+'RECEIPT.json') and receipt['sent_bytes']==len(tx) and receipt['received_bytes']==len(rx) and receipt['error'] is None and receipt['send_confirmed'],'actual stdio '+str(n))
    if res:need(res['id']==req['id'] and 'error' not in res,'stdio reply '+str(n))
    if n>=5:
        b=result['business'][n-5];label=req['id']
        need(req==b['request']==j(R+label+'_REQUEST.json') and res==b['response']==j(R+label+'_RESULT.json')['response'],'business raw equivalence '+label)
        need(b['classification']=='tool_response' and not res['result']['isError'],'business real reply '+label)
        bodies[label]=json.loads(res['result']['content'][0]['text']);need(bodies[label]==b['body'],'public body '+label)
        need(bodies[label]['binding']['runtime_source_sha256']==SOURCE,'public source '+label)
    stdio.append({'sequence':n,'id':req.get('id'),'method':req['method'],'TX':len(tx),'RX':len(rx)})
need(sum(x['TX'] for x in stdio)==rpc['tx_bytes'] and sum(x['RX'] for x in stdio)==rpc['rx_bytes'] and sum(bool(x['RX']) for x in stdio)==7,'stdio totals eight/ seven')
need(max(r['started_ns']+r['elapsed_ns'] for r in rpc['requests'][:4])<events[0]['started_ns'],'metadata zero host RPC')
need(j(R+'product/001/RX.bin')['result']['_meta']['human_eye']['source_sha256']==SOURCE,'real runtime initialize identity')
new=bodies['spatial_assembly_task'];old=bodies['legacy_assembly_task'];ctrl=bodies['spatial_control_task']
need(new['schema_version']=='task-query-set-v2' and new['status']=='observed' and new['summary']['nearest_separated_complete'],'new task complete')
need(old['schema_version']=='task-query-set-v1' and old['status']=='partial' and not old['summary']['nearest_separated_complete'],'old v1 still incomplete')
for pair in old['pairs']:need(pair['facts']['closed_solid_relation']['status']=='unknown' and pair['facts']['closed_solid_relation']['reason']=='closed_solid_work_budget' and pair['separation_gap']['status']=='unknown','old unknown '+str(pair['candidate_index']))
for pair in new['pairs']:need(pair['facts']['spatial_relation']['status']==pair['facts']['surface_proximity']['status']=='measured' and pair['separation_gap']['status']=='measured','new facts '+str(pair['candidate_index']))
names={v['name']:v['object_id'] for v in bodies['directory']['objects']}
need(new['summary']['nearest_separated_ids']==[names['Peer_000']] and ctrl['summary']['distance_m']==1 and ctrl['summary']['nearest_separated_complete'],'actual nearest and control')
audit=lines(R+'audit.jsonl');taskwork={}
for label in ('spatial_assembly_task','legacy_assembly_task','spatial_control_task'):
    match=[a for a in audit if a['event']=='observe' and a['trace_id']==bodies[label]['trace_id']];need(len(match)==1,'unique raw audit '+label)
    taskwork[label]=match[0]['task_work'];need(not taskwork[label]['pair_cache_hit'] and not taskwork[label]['result_cache_hit'],'cold task memo '+label)
for pair in taskwork['spatial_assembly_task']['pairs']:
    need(pair['spatial_pair_count']==pair['surface_pair_count']==1 and pair['closed_solid_pair_count']==0 and not pair['spatial_pair_cache_hit'] and not pair['surface_pair_cache_hit'],'actual cold new pair '+str(pair['candidate_index']))
    n=pair['support_work']['support_source_vertices'];need(n==[512,288,288][pair['candidate_index']] and pair['support_work']['work_units_after']-pair['support_work']['work_units_before']==2*n+3,'actual support work '+str(pair['candidate_index']))
for pair in taskwork['legacy_assembly_task']['pairs']:need(pair['closed_solid_pair_count']==1 and not pair['closed_solid_pair_cache_hit'] and not pair['surface_pair_cache_hit'],'legacy not changed to spatial memo '+str(pair['candidate_index']))
need(raw(R+'ACTUAL_SNAPSHOT.json')==raw(QUAL+'entry/run_01/ACTUAL_SNAPSHOT.json'),'actual same evaluated snapshot bytes')
need(result['errors']==[] and result['harness_execution_complete'] and result['business_passed'] is None,'harness separate from business verification')
proof=j(R+'PRODUCT_RUNTIME_PROOF.json');pc=j(R+'product/CLOSE.json');nc=result['native_close'];exit=result['product_runtime_exit']
need(proof['confirmed'] and proof['runtime_pid']!=proof['launcher_pid'] and proof['parent_chain'][0]['parent_pid']==proof['launcher_pid'],'actual runtime provenance')
need(pc==result['product_close'] and pc['process_reaped'] and pc['exit_code']==0 and pc['reader_stopped'],'launcher clean exit')
need(exit['confirmed'] and exit['exited'] and exit['exit_code']==0 and exit['handle_closed'],'actual runtime retained handle exit0')
need(nc['response']==j(R+'native/WIRE/006/RESPONSE.bin') and nc['response']['status']=='closed' and nc['exit_code']==0 and nc['process_reaped'] and nc['error'] is None,'Blender actual close reap')
need(result['closed']==j(R+'native/WORKER_CLOSED.json') and not result['closed']['poisoned'] and result['closed']['initial_geometry_fingerprint']==result['closed']['final_geometry_fingerprint'],'Blender geometry unchanged')
need(j(P+'entry/FORMAL_PROCESS.json')['exit_code']==0 and j(P+'entry/FORMAL_STARTED.json')['started_ns']==result['started_ns'],'formal execution marker and exit')
need({p.split('/')[3] for p in paths if p.startswith(P+'entry/run_') and len(p.split('/'))>4}=={'run_01'},'one formal entry no replay')
need(result['session_wall_ns']==result['ended_ns']-result['started_ns'],'owned session anchor')
entry_timing={'business_ms':{b['request']['id']:b['tool_ns']/1e6 for b in result['business']},'business_sum_ms':sum(b['tool_ns'] for b in result['business'])/1e6,
 'owned_session_ms':result['session_wall_ns']/1e6,'outer_process_ms':j(P+'entry/FORMAL_PROCESS.json')['elapsed_ns']/1e6,
 'stages_ms':{k:v/1e6 for k,v in result['timing_stages_ns'].items()},'unassigned_residual_ms':(result['session_wall_ns']-sum(result['timing_stages_ns'].values())-sum(b['tool_ns'] for b in result['business']))/1e6}
batch={'wall_ms':sixty['batch_wall_ns']/1e6,'loading_ms':{k:v/1e6 for k,v in sixty['loading_windows_ns'].items()},
 'all_sixty_calls_ms':sum(r['complete_business_ns'] for r in rows)/1e6,'sample_publication_ms':sum(p['elapsed_ns'] for p in sixty['evidence_publication'])/1e6}
delivery=[]
decoder=json.JSONDecoder()
for b in result['business']:
    text=b['response']['result']['content'][0]['text'];parts=[]
    for match in re.finditer(r'"support_evidence"\s*:',text):
        start=match.end()
        while text[start].isspace():start+=1
        value,end=decoder.raw_decode(text,start)
        parts.append({'value_UTF8_bytes':len(text[start:end].encode()),'member_UTF8_bytes':len(text[match.start():end].encode()),'referenced_counts':value['referenced_counts']})
    total=sum(len(v.get('text','').encode()) for v in b['response']['result']['content'])
    need(total==b['visible_text_UTF8_bytes'],'visible text raw measure '+b['request']['id'])
    value_bytes=sum(v['value_UTF8_bytes'] for v in parts);member_bytes=sum(v['member_UTF8_bytes'] for v in parts)
    delivery.append({'id':b['request']['id'],'visible_text_UTF8_bytes':total,'support_evidence_values':parts,
                     'support_value_bytes':value_bytes,'support_member_bytes':member_bytes,
                     'support_value_percent':100*value_bytes/total,'support_member_percent':100*member_bytes/total})
output={'fixed_commit':COMMIT,'product_commit':PRODUCT,'source_sha256':SOURCE,'passed':True,'check_count':len(checks),'fixed_files':len(sources),
 'sixty_samples':timed,'six_case_summaries':summaries,'g508_gate':{'reference_sum_ms':refsum,'candidate_sum_ms':candsum,'reduction_percent':100*(1-candsum/refsum),'passed':True},
 'batch_windows':batch,'work_observations':work,'regressions':reg,'regression_method_total':sum(x['methods'] for x in reg),
 'entry_host':host,'entry_stdio':stdio,'entry_totals':{'host_RPC':6,'host_TX':sum(h['TX'] for h in host),'host_RX':sum(h['RX'] for h in host),'stdio_messages':8,'stdio_replies':7,'stdio_TX':rpc['tx_bytes'],'stdio_RX':rpc['rx_bytes']},
 'entry_timing':entry_timing,'model_visible_delivery':delivery,'actual_task_work':taskwork,'lifecycle':{'proof':proof,'runtime_exit':exit,'Blender_close':nc},
 'scope':'Support direction and extrema independently rederived from frozen vertices. Full triangle witness membership and algorithm proofs reviewed separately by root. No product execution.',
 'AL':{'own_handle':'963c85c7011a4c0382217460eac60535','context_bound':True,'assignment_current':False,'parent_read_only':True,'parent_task':'eeb87f09-6ee2-46f5-8c34-751086cd597b'},
 'execution':{'product_calls':0,'Blender':0,'model_calls':0,'author_verifier':0,'new_performance_runs':0}}
for filename,value in [('RESULTS.json',output),('CHECKS.json',checks),('SOURCES.json',sources)]:
    (OUT/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'passed':True,'checks':len(checks),'files':len(sources),'gate':output['g508_gate'],'medians':[{'case':s['case'],'reference_ms':s['arms']['reference']['total_ms']['median'],'candidate_ms':s['arms']['candidate']['total_ms']['median']} for s in summaries],
 'batch':batch,'entry':output['entry_totals'],'entry_timing':entry_timing,'delivery':delivery},ensure_ascii=False,indent=2))
