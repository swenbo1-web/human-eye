"""Independent OPT1 cost/median-bound arithmetic from raw saved observations."""
from pathlib import Path
from fractions import Fraction
from statistics import median
import ast
import hashlib
import json
import subprocess

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE=ROOT/'verification/m4_surface_scan_001_opt1'
RUN=BASE/'engineering/run_01'
OUT=Path(__file__).resolve().parent
COMMIT='860b87138d40de9cc08b01c947dd864d58da9295'
ORDERS=['AB','BA','AB','BA','AB']
SOURCES={}; CHECKS=[]

def raw(p):
    p=Path(p); b=p.read_bytes()
    SOURCES[p.relative_to(ROOT).as_posix()]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'blob':hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()}
    return b
def read(p):return json.loads(raw(p))
def events(p):return [json.loads(x) for x in raw(p).splitlines() if x.strip()]
def check(name,value):
    CHECKS.append({'name':name,'passed':bool(value)})
    if not value:raise AssertionError(name)
def dump(name,value):
    def encode(x):
        if isinstance(x,Fraction):return {'numerator':x.numerator,'denominator':x.denominator,'value':float(x)}
        raise TypeError(type(x).__name__)
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=encode)+'\n',encoding='utf8',newline='\n')
def med(values):return median(values)

def main():
    binding=read(RUN/'INPUT_BINDINGS.json')
    check('frozen_AB_order',binding['pair_orders']==ORDERS)
    check('planned_30_rows',len(binding['planned_business_rows'])==30)
    controller=raw(BASE/'engineering/run_pairs.py').decode()
    sequence=raw(BASE/'engineering/sequence.py').decode()
    common=raw(BASE/'engineering/common.py').decode()
    # These are also semantically read in REPORT; AST records the call order.
    for name,source in [('run_pairs.py',controller),('sequence.py',sequence),('common.py',common)]:
        path=BASE/'engineering'/name
        check('harness_bound_'+name,hashlib.sha256(source.encode()).hexdigest()==binding['files'][str(path)])
    ct=ast.parse(controller);sq=ast.parse(sequence);cm=ast.parse(common)
    check('controller_not_async',not any(isinstance(n,(ast.AsyncFunctionDef,ast.AsyncFor,ast.Await)) for n in ast.walk(ct)))
    runfun=next(n for n in sq.body if isinstance(n,ast.FunctionDef) and n.name=='run_sequence')
    check('sequence_returns_after_finally',isinstance(runfun.body[-1],ast.Return) and isinstance(runfun.body[-2],ast.Try))
    final=runfun.body[-2].finalbody
    check('final_statement_synchronous_save',isinstance(final[-1],ast.Expr) and isinstance(final[-1].value,ast.Call) and final[-1].value.func.id=='save')
    savefun=next(n for n in cm.body if isinstance(n,ast.FunctionDef) and n.name=='save')
    check('save_with_block_closes_before_return',len(savefun.body)==1 and isinstance(savefun.body[0],ast.With))
    freeze=read(BASE/'engineering/HARNESS_FREEZE.json')
    for row in freeze['files']:
        check('harness_freeze_'+Path(row['path']).name,hashlib.sha256(raw(row['path'])).hexdigest()==row['sha256'])
    chronological=[];rows=[];seqs={}; mappings=[]
    for i,order in enumerate(ORDERS,1):
        for arm in order:
            p=RUN/f'pair_{i:02}'/arm; result=read(p/'RESULTS.json'); seqs[i,arm]=result
            label=f'{i}{arm}'
            check(label+'_planned_states', [r['state'] for r in result['business']]==['cold','repeat','edit'])
            check(label+'_no_errors',result['errors']==[] and result['automatic_retries']==0 and result['source_files_unchanged'])
            check(label+'_prefix_duration',result['session_wall_ns']==result['ended_ns']-result['started_ns']>0)
            chronological.append((i,arm,result['started_ns'],result['ended_ns']))
            close=read(p/'product/CLOSE.json')
            check(label+'_close',close==result['product_close'] and close['process_reaped'] and close['exit_code']==0 and close['error'] is None)
            check(label+'_runtime_exit',result['runtime_exit']['confirmed'] and result['runtime_exit']['exit_code']==0 and result['runtime_exit']['handle_closed'])
            check(label+'_native_exit',result['native_close']['process_reaped'] and result['native_close']['exit_code']==0 and result['native_close']['error'] is None)
            audit=events(p/'audit.jsonl'); worker=events(p/'native/WORKER_EVENTS.jsonl'); wire=read(p/'native/WIRE/INDEX.json')
            check(label+'_worker_same',worker==result['all_worker_events'])
            check(label+'_7_physical_host',len(wire)==result['all_host_RPC_including_QA_and_close']==7)
            for part in wire:
                wdir=p/'native/WIRE'/f"{part['sequence']:03}"
                tx,rx=raw(wdir/'REQUEST.bin'),raw(wdir/'RESPONSE.bin')
                check(label+f"_wire_{part['sequence']}",len(tx)==part['request_bytes'] and len(rx)==part['response_attempted_bytes'] and part['response_sendall_completed'])
            init_events=[e for e in audit if e.get('event')=='request_trace' and e['trace']['operation'] not in ('mcp.observe',)]
            directory_names={}
            for k,r in enumerate(result['business'],5):
                state=r['state']; key=label+'_'+state
                receipt=read(p/f'{state}_RESPONSE_RECEIPT.json')
                check(key+'_raw_time',receipt['started_ns']==r['started_ns'] and receipt['ended_ns']==r['ended_ns'] and receipt['complete_client_request_ns']==r['ended_ns']-r['started_ns'])
                check(key+'_request_window',result['started_ns']<=r['started_ns']<=r['ended_ns']<=result['ended_ns'])
                check(key+'_no_request_error',not receipt['errors'] and not r['errors'] and r['body']['status']=='complete')
                pdir=p/'product'/f'{k:03}';rpc=read(pdir/'RECEIPT.json');tx,rx=raw(pdir/'TX.bin'),raw(pdir/'RX.bin')
                check(key+'_actual_stdio',json.loads(tx)==r['request'] and json.loads(rx)==r['response'] and rpc==r['stdio'])
                check(key+'_wire_lengths',len(tx)==rpc['sent_bytes']==rpc['attempted_send_bytes'] and len(rx)==rpc['received_bytes'] and rpc['send_confirmed'] and rpc['error'] is None)
                trace_id=r['body']['trace_id']
                ts=[e['trace'] for e in audit if e.get('event')=='request_trace' and e.get('trace_id')==trace_id]
                obs=[e for e in audit if e.get('event')=='observe' and e.get('trace_id')==trace_id]
                check(key+'_raw_audit',len(ts)==len(obs)==1 and ts[0]==r['trace'] and obs[0]['task_work']==r['diagnostics'])
                t=ts[0];check(key+'_delivery_timed',t['duration_ns']==r['full_service_and_delivery_trace_ns'] and t['annotations']['delivery']=='stdio_write_completed' and {'mcp.wire_encode','mcp.stdio_write'} <= {s['name'] for s in t['spans']})
                current=[e for e in worker if isinstance(e.get('started_ns'),int) and r['started_ns']<=e['started_ns']<=r['ended_ns']]
                check(key+'_one_host',len(current)==r['actual_host_RPC']==1 and current==r['work_events'])
                response=read(p/'native/WIRE'/f"{current[0]['sequence']:03}"/'RESPONSE.bin')
                host_result=json.loads(response['result']['result'].split('HUMAN_EYE_BLENDER_MCP:',1)[1])['result']
                capture=host_result['capture']
                directory_names={x['object_id']:x['name'] for x in capture['coverage']}
                check(key+'_host_capture_work',capture['work']==r['diagnostics']['acquisition_work'])
                check(key+'_no_render_error',not current[0]['changed_or_new_PNG_files'] and current[0]['script_error'] is None and current[0]['render_events_before']==current[0]['render_events_after']==0)
                w=r['diagnostics'];expected=112 if state=='cold' else 0 if state=='repeat' else 114 if arm=='A' else 10
                check(key+'_kernel_count',w['kernel_calls']==expected)
                event=current[0]['m2_work'];before={v['module']:v['work'] for v in event['before']};after=event['after'][0]
                # enabled/resident_resources are state gauges, not cumulative work counters.
                actual_delta={name:value-before.get(after['module'],{}).get(name,0) for name,value in after['work'].items() if name not in ('enabled','resident_resources')}
                check(key+'_residency_from_worker',actual_delta==w['acquisition_work']['residency_delta'])
                delta=actual_delta
                check(key+'_geometry_work',delta['resource_vertices_read']==(530 if state=='cold' else 0) and delta['resource_faces_read']==(978 if state=='cold' else 0) and delta['world_vertices_transformed']==(530 if state=='cold' else 8 if state=='edit' else 0))
                if arm=='B':
                    c=w['measurement_cache_after'];b=w['measurement_cache_before']
                    check(key+'_capacity',c['max_bytes']==2097152 and w['measurement_cache_max_measurements']==256 and c['accounted_bytes']<=2097152)
                    check(key+'_entries',c['measurement_entries']==(122 if state=='edit' else 112) and c['accounted_bytes']==(198307 if state=='edit' else 181984))
                    if state=='cold':check(key+'_no_prefill',b['measurement_entries']==b['measurement_computations']==b['accounted_bytes']==0)
                rows.append({'pair':i,'version':arm,'state':state,'client_ns':r['complete_client_request_ns'],'trace_ns':t['duration_ns'],
                    'host_wire_bytes':r['bridge_request_bytes']+r['bridge_response_bytes'],'MCP_wire_bytes':len(tx)+len(rx),
                    'kernel':w['kernel_calls'],'cache_hits':w['cache_hits'],'work':delta,'memory':r['memory_after'],
                    'spans':{s['name']:s['duration_ns'] for s in t['spans']}})
            check(label+'_metadata_zero_host',result['metadata_zero_host_RPC'] and worker[0]['started_ns']<result['business'][0]['started_ns'])
            if arm=='B':
                cold=result['business'][0]['diagnostics']['pairs'];edit=result['business'][2]['diagnostics']['pairs']
                hits=[];miss=[]
                for ids,v in edit.items():
                    if v['surface_pair_cache_hit']:
                        check(label+'_dependency_hit_'+ids,ids in cold and v['surface_dependency_key']==cold[ids]['surface_dependency_key'] and v['surface_pair_count']==0)
                        check(label+'_unrelated_hit_'+ids,all(directory_names[x]!='Obj_008' for x in json.loads(ids)))
                        hits.append(ids)
                    else:
                        check(label+'_dependency_miss_'+ids,v['surface_pair_count']==1 and (ids not in cold or v['surface_dependency_key']!=cold[ids]['surface_dependency_key']))
                        check(label+'_changed_miss_'+ids,any(directory_names[x]=='Obj_008' for x in json.loads(ids)))
                        miss.append(ids)
                check(label+'_104_hit_10_miss',len(hits)==104 and len(miss)==10)
                mappings.append({'pair':i,'hits':hits,'misses':miss})
    for previous,current in zip(chronological,chronological[1:]):
        check('serial_clock_'+str(current[:2]),previous[3]<current[2])
    metrics=[];upper=[]
    for i in range(1,6):
        a,b=seqs[i,'A'],seqs[i,'B'];av=[x['complete_client_request_ns'] for x in a['business']];bv=[x['complete_client_request_ns'] for x in b['business']]
        row={'pair':i,'A_ns':av,'B_ns':bv,'cold_delta_ns':bv[0]-av[0],'repeat_delta_ns':bv[1]-av[1],
             'edit_ratio':Fraction(bv[2],av[2]),'business_sum_ratio':Fraction(sum(bv),sum(av)),
             'lifecycle_prefix_ratio':Fraction(b['session_wall_ns'],a['session_wall_ns'])}
        index=next(j for j,x in enumerate(chronological) if x[:2]==(i,'B'))
        if index+1<len(chronological):
            upper_ns=chronological[index+1][2]-b['started_ns'];ratio=Fraction(upper_ns,a['session_wall_ns'])
            row['full_ratio_upper']=ratio;row['B_full_upper_ns']=upper_ns;row['B_tail_upper_ns']=upper_ns-b['session_wall_ns'];upper.append(ratio)
        else:row['full_ratio_upper']='positive_infinity'
        metrics.append(row)
    full_upper=sorted(upper)[2]
    stats={k:med(x[k] for x in metrics) for k in ['cold_delta_ns','repeat_delta_ns','edit_ratio','business_sum_ratio','lifecycle_prefix_ratio']}
    stats['full_lifecycle_ratio_median_upper_bound']=full_upper
    stats['exact_full_lifecycle_ratio_median']='unmeasured'
    stats['cold_allowance_ns']=max(Fraction(1,20)*med(x['A_ns'][0] for x in metrics),2_000_000)
    stats['repeat_allowance_ns']=max(Fraction(1,20)*med(x['A_ns'][1] for x in metrics),2_000_000)
    gates={'edit':stats['edit_ratio']<=Fraction(7,10),'cold':stats['cold_delta_ns']<=stats['cold_allowance_ns'],
           'repeat':stats['repeat_delta_ns']<=stats['repeat_allowance_ns'],'business_sum':stats['business_sum_ratio']<1,
           'full_lifecycle_conservative':full_upper<=Fraction(105,100)}
    check('five_fixed_engineering_gates',all(gates.values()))
    process=read(BASE/'engineering/process_01/RESULTS.json')
    check('Process_3_states', [r['state'] for r in process['business']]==['cold','repeat','edit'])
    check('Process_closed',not process['errors'] and process['close']['process_reaped'] and process['close']['exit_code']==0 and process['close']['stdout_stopped'] and process['close']['stderr_stopped'])
    process_rows=[]
    for r,expected in zip(process['business'],(112,0,10)):
        check('Process_'+r['state'],not r['errors'] and r['body']['status']=='complete' and r['actual_host_RPC']==1 and r['diagnostics']['kernel_calls']==expected and r['complete_client_request_ns']==r['ended_ns']-r['started_ns'])
        process_rows.append({'state':r['state'],'client_ns':r['complete_client_request_ns'],'kernel':expected})
    stdin=[json.loads(line) for line in raw(BASE/'engineering/process_01/Blender_STDIN_UTF8.bin').splitlines() if line]
    commands=[r['command'] for r in stdin]
    check('Process_commands',commands==['capabilities','qa_snapshot','capture_surface_scan','capture_surface_scan','qa_advance','qa_snapshot','capture_surface_scan','shutdown'])
    preparations={}
    for arm,path in [('A',ROOT/'verification/m4_surface_scan_001/installation/run_01/READY.json'),('B',BASE/'installation/run_01/READY.json')]:
        preparations[arm+'_build_install_ns']=read(path)['elapsed_ns']
    oracle=events(ROOT/'verification/m4_surface_scan_001/qualification/ORACLE_RUNS.jsonl')
    check('oracle_single_saved_run',len(oracle)==1 and oracle[0]['status']=='passed' and oracle[0]['error'] is None)
    preparations['historical_oracle_ns']=oracle[0]['ended_ns']-oracle[0]['started_ns']
    preparations['historical_oracle_reported_elapsed_ns']=oracle[0]['elapsed_ns']
    preparations['historical_oracle_elapsed_field_difference_ns']=oracle[0]['elapsed_ns']-preparations['historical_oracle_ns']
    preparations['stages_by_sequence']={str(i)+arm:d['timing_stages_ns'] for (i,arm),d in seqs.items()}
    for row in binding['files']:
        if '/engineering/' in row.replace('\\','/') and row.endswith('.py'):
            check('frozen_engineering_'+Path(row).name,hashlib.sha256(raw(row)).hexdigest()==binding['files'][row])
    # Git object equality for every used file, including raw wire bytes.
    entries={}
    rawtree=subprocess.check_output(['git','ls-tree','-r','-z',COMMIT,'--','verification/m4_surface_scan_001_opt1','verification/m4_surface_scan_001','verification/m1_task_entry_001_eval','verification/native_plugin_complex_003'],cwd=ROOT)
    for line in rawtree.split(b'\0'):
        if line:
            meta,name=line.split(b'\t',1);entries[name.decode()]=meta.split()[2].decode()
    check('all_sources_match_Git',all(entries.get(p)==v['blob'] for p,v in SOURCES.items()))
    return {'passed':True,'raw_rows':rows,'pairs':metrics,'statistics':stats,'gates':gates,'chronological':chronological,
        'cache_mappings':mappings,'source_count':len(SOURCES),'check_count':len(CHECKS),'new_Blender_consumer_API':0,
        'Process_rows':process_rows,'Process_commands':commands,'preparation':preparations}

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    try:result=main()
    except Exception as exc:
        name='FAILED.json' if not (OUT/'FAILED.json').exists() else 'FAILED_'+str(len(list(OUT.glob('FAILED*.json')))+1)+'.json'
        dump(name,{'error':repr(exc),'checks':CHECKS});raise
    dump('RESULTS.json',result);dump('CHECKS.json',CHECKS);dump('SOURCES.json',SOURCES)
    print(json.dumps({'passed':True,'checks':len(CHECKS),'files':len(SOURCES),'statistics':result['statistics']},default=lambda x:float(x)))
