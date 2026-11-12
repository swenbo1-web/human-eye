"""Independent saved-evidence cost audit. No product or author analyzers imported."""
from pathlib import Path
import hashlib, json, statistics, subprocess

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE = ROOT/'verification/m4_surface_scan_001'
OUT = Path(__file__).parent
COMMIT = '726e88efba548e85eba1eb148b91486470c5d2c1'
SOURCES, CHECKS = {}, []
TREE = {}
for row in subprocess.check_output(['git','ls-tree','-rz',COMMIT],cwd=ROOT).split(b'\0'):
    if row:
        meta,name=row.split(b'\t',1);TREE[name.decode()]=meta.split()[2].decode()

def read(p):
    p=Path(p);p=p if p.is_absolute() else BASE/p
    raw=p.read_bytes();name=p.relative_to(ROOT).as_posix()
    blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    assert TREE.get(name)==blob,(name,'not original Git bytes')
    SOURCES[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'git_blob':blob}
    return raw

def j(p):return json.loads(read(p))
def jl(p):return [json.loads(x) for x in read(p).splitlines() if x.strip()]
def check(name,value,detail=None):
    CHECKS.append({'name':name,'passed':bool(value),'detail':detail})
    assert value,(name,detail)

cells=[];sequences=[];deps=[]
for n in range(1,6):
    p=BASE/f'engineering/run_01/sequence_{n:02}'
    audits=jl(p/'audit.jsonl');events=jl(p/'native/WORKER_EVENTS.jsonl')
    result=j(p/'RESULTS.json');session=j(p/'native/SESSION.json')
    close=j(p/'product/CLOSE.json');worker_close=j(p/'native/WORKER_CLOSED.json')
    check(f'{n}:planned_states',[x['state'] for x in result['business']]==['cold','repeat','edit'])
    check(f'{n}:errors_and_closure',not result['errors'] and result['automatic_retries']==0
          and close['confirmed'] and close['exit_code']==0 and close['process_reaped']
          and result['runtime_exit']['confirmed'] and result['runtime_exit']['exit_code']==0
          and result['native_close']['process_reaped'] and result['native_close']['exit_code']==0
          and not worker_close['poisoned'])
    check(f'{n}:whole_sequence',result['session_wall_ns']==result['ended_ns']-result['started_ns'])
    wire=j(p/'native/WIRE/INDEX.json')
    check(f'{n}:all_host_calls',len(wire)==len(events)==result['all_host_RPC_including_QA_and_close']==7)
    for row in wire:
        q=p/f"native/WIRE/{row['sequence']:03}"
        tx=read(q/'REQUEST.bin');rx=read(q/'RESPONSE.bin')
        check(f'{n}:host_wire_{row["sequence"]}',len(tx)==row['request_bytes'] and len(rx)==row['response_attempted_bytes']
              and len(tx)+len(rx)==row['request_response_attempted_bytes'] and row['response_sendall_completed'])
    delta_by_state={};row_by_state={}
    for state,prodseq in [('cold',5),('repeat',6),('edit',7)]:
        label=f'{n}:{state}'
        receipt=j(p/f'{state}_RESPONSE_RECEIPT.json');request=j(p/f'{state}_REQUEST.json')
        rawreceipt=j(p/f'product/{prodseq:03}/RECEIPT.json')
        tx=read(p/f'product/{prodseq:03}/TX.bin');rx=read(p/f'product/{prodseq:03}/RX.bin')
        response=json.loads(rx);body=json.loads(response['result']['content'][0]['text'])
        check(label+':raw_request_response',json.loads(tx)==request==receipt['request'] and response==receipt['response']
              and body==receipt['body'] and not receipt['errors'] and not response['result'].get('isError'))
        check(label+':time',receipt['ended_ns']-receipt['started_ns']==receipt['complete_client_request_ns']
              and rawreceipt==receipt['stdio'] and rawreceipt['elapsed_ns']<=receipt['complete_client_request_ns'])
        check(label+':stdio_bytes',len(tx)==rawreceipt['sent_bytes']==rawreceipt['attempted_send_bytes']
              and len(rx)==rawreceipt['received_bytes'] and rawreceipt['send_confirmed'] and rawreceipt['error'] is None)
        records=[x for x in audits if x.get('trace_id')==body['trace_id']]
        obs=[x for x in records if x.get('event')=='observe'];tr=[x['trace'] for x in records if x.get('event')=='request_trace']
        check(label+':one_observe_trace',len(obs)==len(tr)==1)
        work=obs[0]['task_work'];trace=tr[0]
        check(label+':trace_delivery',trace['outcome']=='complete' and trace['annotations']['delivery']=='stdio_write_completed'
              and trace['annotations']['mcp_request_id']==state and trace['annotations']['mcp_native_image_block_count']==0)
        spans=trace['spans'];spanmap={x['name']:x['duration_ns'] for x in spans}
        check(label+':outer_spans',all(k in spanmap for k in ['mcp.wire_encode','mcp.stdio_write','host.capture','observation.surface_scan'])
              and all(s['start_offset_ns']+s['duration_ns']<=trace['duration_ns'] for s in spans))
        ev=[x for x in events if receipt['started_ns']<=x['started_ns']<=receipt['ended_ns']]
        check(label+':single_host_execution',len(ev)==1 and ev[0]['status']=='completed' and ev[0]['script_error'] is None
              and ev[0]['changed_or_new_PNG_files']==[] and ev[0]['render_events_before']==ev[0]['render_events_after']==0)
        hostseq=ev[0]['sequence'];rawhost=j(p/f'native/WIRE/{hostseq:03}/RESPONSE.bin')
        stdout=read(p/f'native/call_{hostseq}/stdout.txt').decode()
        check(label+':host_stdout',rawhost['status']=='success' and rawhost['result']['executed'] is True
              and rawhost['result']['result'].replace('\r\n','\n')==stdout.replace('\r\n','\n'))
        delta=json.loads(stdout.split('HUMAN_EYE_BLENDER_MCP:',1)[1])['result'];scan=delta['capture'];delta_by_state[state]=delta
        check(label+':captured_work',scan['work']==work['acquisition_work'])
        rd=scan['work']['residency_delta'];m2=ev[0]['m2_work'];after=m2['after'][0];before=m2['before']
        bwork=before[0]['work'] if before else {}
        check(label+':raw_counters',all(after['work'][k]-bwork.get(k,0)==v for k,v in rd.items()))
        expected_kernel=0 if state=='repeat' else (112 if state=='cold' else 114)
        check(label+':kernel',work['kernel_calls']==expected_kernel
              and sum(x['surface_pair_count'] for x in work.get('pairs',{}).values())==expected_kernel
              and work['normalizations']==(0 if state=='repeat' else 1))
        check(label+':resources',len(delta['resources'])==(24 if state=='cold' else 0)
              and m2['new_resource_arrays']['vertices']==(530 if state=='cold' else 0)
              and rd['resource_vertices_read']==(530 if state=='cold' else 0)
              and rd['resource_faces_read']==(978 if state=='cold' else 0)
              and rd['world_vertices_transformed']=={'cold':530,'repeat':0,'edit':8}[state])
        mapping={m['object_id']:m['name'] for m in scan['capture']['meshes']}
        pairs={tuple(mapping[i] for i in json.loads(key)):w for key,w in work.get('pairs',{}).items()}
        unrelated=[pair for pair,w in pairs.items() if 'Obj_008' not in pair and w['surface_pair_count']==1]
        total_work={k:sum(x['surface_work'].get(k,0) for x in work.get('pairs',{}).values()) for k in
                    ['work_units','tree_builds','tree_build_units','narrow_phase_pairs','validated_faces','referenced_vertices']}
        unrelated_work={k:sum(pairs[pair]['surface_work'].get(k,0) for pair in unrelated) for k in total_work}
        if state=='edit':check(label+':104_unrelated',len(unrelated)==104)
        for stage in ['memory_before','memory_after']:
            for mem in receipt[stage]:
                check(label+':'+stage+':'+str(mem['pid']),mem['source']=='GetProcessMemoryInfo' and mem['peak_scope']=='process_lifetime_peak'
                      and mem['peak_working_set_bytes']>=mem['working_set_bytes'])
        wrow=next(x for x in wire if x['sequence']==hostseq)
        cell={'sequence':n,'state':state,'client_ns':receipt['complete_client_request_ns'],'trace_ns':trace['duration_ns'],
              'stdio_ns':rawreceipt['elapsed_ns'],'stdio_tx':len(tx),'stdio_rx':len(rx),'host_wire':wrow,
              'host_elapsed_ns':ev[0]['elapsed_ns'],'spans_ns':spanmap,'kernel_calls':expected_kernel,
              'kernel_work':total_work,'unrelated_computations':len(unrelated),'unrelated_work':unrelated_work,
              'residency_delta':rd,'delta_resources':len(delta['resources']),'normalizations':work['normalizations'],
              'memory_before':receipt['memory_before'],'memory_after':receipt['memory_after'],'trace_peak_rss':trace['peak_rss'],
              'result_cache_hit':work['result_cache_hit']}
        cells.append(cell);row_by_state[state]=cell
    b,e=(delta_by_state[s]['capture']['capture'] for s in ['cold','edit'])
    old={m['name']:m['_scene_resource'] for m in b['meshes']};new={m['name']:m['_scene_resource'] for m in e['meshes']}
    changed=[name for name in old if old[name]!=new[name]]
    check(f'{n}:only_one_pose_changed',changed==['Obj_008'] and all(old[k]['id']==new[k]['id'] and old[k]['revision']==new[k]['revision'] for k in old))
    check(f'{n}:epoch_and_instances_same',b['capture_state']['instance_id']==e['capture_state']['instance_id']
          and b['capture_state']['epoch']==e['capture_state']['epoch'] and e['capture_state']['revision']==b['capture_state']['revision']+1
          and b['host_identity']==e['host_identity'])
    bm={m['object_id']:m['name'] for m in b['meshes']}
    coldpairs={tuple(bm[i] for i in x['object_ids']) for x in delta_by_state['cold']['capture']['pairs'] if x['disposition']=='retained'}
    editpairs={tuple(bm[i] for i in x['object_ids']) for x in delta_by_state['edit']['capture']['pairs'] if x['disposition']=='retained'}
    common_unrelated={x for x in editpairs if 'Obj_008' not in x}
    check(f'{n}:unrelated_were_previously_measured',common_unrelated<=coldpairs and len(common_unrelated)==104)
    deps.append({'sequence':n,'changed_names':changed,'old_state':b['capture_state'],'new_state':e['capture_state'],
                 'cold_retained':len(coldpairs),'edit_retained':len(editpairs),'previously_measured_unrelated':len(common_unrelated),
                 'new_required_pairs_if_all_eligible_hits':len(editpairs-common_unrelated),'changed_reference_before':old['Obj_008'],
                 'changed_reference_after':new['Obj_008']})
    sequences.append({'sequence':n,'session_wall_ns':result['session_wall_ns'],'timing_stages_ns':result['timing_stages_ns'],
                      'native_startup_ns':session['startup_ns'],'request_total_ns':sum(x['client_ns'] for x in row_by_state.values()),
                      'whole_host_wire_bytes':sum(x['request_response_attempted_bytes'] for x in wire),
                      'business_host_wire_bytes':sum(x['host_wire']['request_response_attempted_bytes'] for x in row_by_state.values()),
                      'native_close_ns':result['native_close']['elapsed_ns']})

proc=j('engineering/process_01/RESULTS.json');pdata=read('engineering/process_01/Blender_STDIN_UTF8.bin')
pout=read('engineering/process_01/Blender_STDOUT_UTF8.bin');paudit=jl('engineering/process_01/audit.jsonl')
commands=[json.loads(line) for line in pdata.splitlines() if line.strip()]
check('process:commands',[r['command'] for r in commands]==['capabilities','capture_surface_scan','shutdown'])
check('process:closure',not proc['errors'] and proc['close']['process_reaped'] and proc['close']['exit_code']==0)
ptrace=[e['trace'] for e in paudit if e['event']=='request_trace' and e['trace'].get('operation')=='mcp.observe']
check('process:single_trace',len(ptrace)==1)
installation=j('installation/run_01/READY.json')
prep=[]
for name in ['04_BUILD','05_INSTALL']:
    record=j(f'installation/run_01/{name}.PROCESS.json');prep.append({'name':name,'record':record})
oracle=jl('qualification/ORACLE_RUNS.jsonl')
for name in ['human_eye_plugin/read_context.py','human_eye_plugin/scene_cache.py','human_eye_plugin/scene_residency.py',
             'human_eye_plugin/surface_scan.py','human_eye_plugin/task_query.py','human_eye_plugin/live_service.py','human_eye_plugin/blender_host.py',
             'human_eye_plugin/surface_proximity.py','human_eye_plugin/surface_geometry.py',
             'human_eye_plugin/blender_mcp_host.py','human_eye_plugin/blender_process.py',
             'verification/m4_surface_scan_001/engineering/run_main.py','verification/m4_surface_scan_001/engineering/wire_meter.py',
             'verification/m4_surface_scan_001/engineering/run_process.py','verification/m1_task_entry_001_eval/actor.py']:
    read(ROOT/name)
aggregate={state:{field:statistics.median(x[field] for x in cells if x['state']==state) for field in ['client_ns','trace_ns','stdio_ns','host_elapsed_ns']}
           for state in ['cold','repeat','edit']}
for state in aggregate:
    aggregate[state]['span_medians_ns']={k:statistics.median(x['spans_ns'].get(k,0) for x in cells if x['state']==state)
                                        for k in sorted({k for x in cells for k in x['spans_ns']})}
output={'commit':COMMIT,'review_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'samples':{'scenarios':1,'states':2,'independent_process_sequences':5,'requests':15,'process_directed':1},
        'new_Blender_model_API_runs':0,'checks':CHECKS,'cells':cells,'sequences':sequences,'aggregate':aggregate,'dependency_changes':deps,
        'process':{'timing':proc['timing_stages_ns'],'trace_duration_ns':ptrace[0]['duration_ns'],'stdin_bytes':len(pdata),
                   'stdout_bytes':len(pout),'total_recorded_window_ns':proc['ended_ns']-proc['started_ns']},
        'preparation':{'installation_ready_elapsed_ns':installation['elapsed_ns'],'steps':prep,'oracle_runs':oracle}}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
(OUT/'SOURCES.json').write_text(json.dumps(SOURCES,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'sources':len(SOURCES),'assertions':len(CHECKS),'aggregate':aggregate,'dependency_changes':deps[0]},ensure_ascii=False))
