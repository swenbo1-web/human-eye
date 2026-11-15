"""Offline independent identity, clock, source-wire and budget audit."""
import ast
import base64
import hashlib
import io
import json
import statistics
import subprocess
import zipfile
import zlib
from fractions import Fraction as F
from pathlib import Path

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-camera-001/hefe')
NS=ROOT/'verification/m4_target_camera_reliability_001'
OUT=Path(__file__).parent
FINAL='4f8c41f89c9b40b3f310cf3f8e8b711bf09864a6'
PRODUCT='691f7b78ed89ccf30df47847fc1e99ad51a1dc64'
BASE='03eb4e2971891dfe0160972cbcf974e3dcf1a21c'
RUNTIME=Path('D:/he_m4_camera_001')
checks=[]; pins={}
def sha(b): return hashlib.sha256(b).hexdigest()
def read(p):
    p=Path(p); b=p.read_bytes(); pins[str(p)]={'bytes':len(b),'sha256':sha(b)}; return b
def js(p): return json.loads(read(p))
def ck(name,condition):
    checks.append({'name':name,'passed':bool(condition)})
    assert condition,name
def git(*args): return subprocess.check_output(['git','-C',str(ROOT),*args])
def blobs(expressions):
    data=git('cat-file','--batch') if not expressions else subprocess.check_output(
        ['git','-C',str(ROOT),'cat-file','--batch'],input=('\n'.join(expressions)+'\n').encode())
    stream=io.BytesIO(data); values={}
    for expression in expressions:
        header=stream.readline().split(); assert header[1]==b'blob',expression
        value=stream.read(int(header[2])); assert stream.read(1)==b'\n';values[expression]=value
    assert not stream.read();return values

manifest=js(NS/'CONTENT_MANIFEST.json'); freeze=js(NS/'SOURCE_FREEZE.json'); binding=js(NS/'build/RUN_BINDING.json')
archive=js(NS/'RUNTIME_ARCHIVE.json'); baseline=js(NS/'BASELINE.json')
ck('final_git',git('rev-parse','HEAD').decode().strip()==FINAL)
ck('author_clean',not git('status','--porcelain=v1').strip())
diff=set(git('diff','--name-only',BASE,FINAL).decode().splitlines())
listed={r['path'] for r in manifest['files']}
manifest_rel='verification/m4_target_camera_reliability_001/CONTENT_MANIFEST.json'
ck('769_exact_paths',len(diff)==769 and diff==listed|{manifest_rel} and len(listed)==768)
src=freeze['runtime_manifest'];ck('141_sources',len(src)==141 and src==binding['source_manifest'])
exprs=[FINAL+':'+p for p in sorted(diff|{r['path'] for r in src})]
exprs += [PRODUCT+':'+r['path'] for r in src]
exprs += [BASE+':'+r['path'] for r in src]
gb=blobs(exprs)
for row in manifest['files']:
    b=read(ROOT/row['path']);ck('manifest/'+row['path'],len(b)==row['bytes'] and sha(b)==row['sha256'] and gb[FINAL+':'+row['path']]==b)
ck('manifest_self_git',gb[FINAL+':'+manifest_rel]==read(NS/'CONTENT_MANIFEST.json'))
ck('manifest_total_bytes',sum(r['bytes'] for r in manifest['files'])==manifest['bytes'])
wheel=next((NS/'build').glob('*.whl')); wb=read(wheel);ck('wheel_sha',sha(wb)==binding['wheel_sha256'])
z=zipfile.ZipFile(io.BytesIO(wb)); install=Path(binding['install_root']); old_install=Path(baseline['old_install'])
for row in src:
    p=row['path'];values=[gb[FINAL+':'+p],gb[PRODUCT+':'+p],read(ROOT/p),read(install/p),z.read(p)]
    ck('source_five_way/'+p,len({sha(b) for b in values})==1 and sha(values[0])==row['sha256'])
    ck('old_source/'+p,gb[BASE+':'+p]==read(old_install/p))
computed=sha(json.dumps({'base_version':binding['base_version'],'implementation_revision':binding['implementation_revision'],'files':src},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
ck('source_aggregate',computed==binding['source_sha256']=='9f2c5ca150f968841b64f4d4eda89313069453853c877ba21b6a262999e29a61')
expected_src={r['path'] for r in src}
for root in (ROOT,install):
    actual={p.relative_to(root).as_posix() for package in ('human_eye_plugin','human_eye_module1_operators') for p in (root/package).glob('*.py')}
    actual|={r for r in expected_src if '/' not in r}
    ck('source_enumeration/'+str(root),actual==expected_src)
ck('runtime_archive_count',len(archive['files'])==681 and sum(r['bytes'] for r in archive['files'])==14961221)
for row in archive['files']:
    a=read(NS/row['archive_path']);b=read(row['original_path'])
    ck('archive/'+row['relative_path'],a==b and len(a)==row['bytes'] and sha(a)==row['sha256'])
for group in ('protected_old_pins','original_reference_pins'):
    for p,h in baseline[group].items():ck(group+'/'+p,sha(read(p))==h)

inputs=js(NS/'INPUTS.json'); input_freeze=js(NS/'INPUT_FREEZE.json'); micro=js(NS/'MICRO_CAMERA_01.json')
ck('micro_inputs',sha(read(NS/'INPUTS.json'))==micro['input_sha256']==input_freeze['inputs_sha256'])
ck('micro_source',micro['source_sha256']=={'old':sha(gb[BASE+':human_eye_plugin/blender_host.py']),'new':sha(gb[PRODUCT+':human_eye_plugin/blender_host.py'])})
ck('micro_benchmark',sha(read(NS/'micro_camera.py'))==micro['benchmark_sha256'])
plan=inputs['microbenchmark'];micro_results=[]
expected_order=[(case['id'],pair,arm) for case in inputs['micro_cases'] for pair,order in enumerate(plan['pair_orders'],1) for arm in order]
ck('micro_order',[(r['case'],r['pair'],r['arm']) for r in micro['records']]==expected_order)
ck('micro_timed_count',sum(len(r['calls']) for r in micro['records'])==14336==micro['timed_calls']==input_freeze['micro_timed_calls'])
ck('micro_warmups',len(micro['warmups'])==4 and sum(w['calls'] for w in micro['warmups'])==64==micro['warmup_calls'])
for case in inputs['micro_cases']:
    records=[r for r in micro['records'] if r['case']==case['id']]; ratios=[];blockmeans={'old':[],'new':[]}; allcalls={'old':[],'new':[]}
    for r in records:
        ck('micro_block/'+case['id']+'/'+str(r['pair'])+'/'+r['arm'],len(r['calls'])==plan['calls_per_block']==512 and all(r['block_started_ns']<=a<=b<=r['block_closed_ns'] for a,b in r['calls']) and all(r['calls'][i][1]<=r['calls'][i+1][0] for i in range(511)))
        blockmeans[r['arm']].append(F(r['block_closed_ns']-r['block_started_ns'],512))
        allcalls[r['arm']]+=[b-a for a,b in r['calls']]
    for pair in range(1,8):
        rr={r['arm']:r for r in records if r['pair']==pair}
        ratios.append(F(rr['new']['block_closed_ns']-rr['new']['block_started_ns'],rr['old']['block_closed_ns']-rr['old']['block_started_ns']))
    claimed=next(r for r in micro['summaries'] if r['case']==case['id'])
    ck('micro_ratios/'+case['id'],[float(v) for v in ratios]==claimed['paired_block_ratios_new_over_old'] and float(statistics.median(ratios))==claimed['median_paired_ratio'])
    micro_results.append({'case':case['id'],'old_block_average_median_ns':statistics.median(blockmeans['old']),'new_block_average_median_ns':statistics.median(blockmeans['new']),'old_individual_call_median_ns':statistics.median(allcalls['old']),'new_individual_call_median_ns':statistics.median(allcalls['new']),'median_paired_ratio':statistics.median(ratios),'all_ratios':ratios})

schedule=js(NS/'harness/CONTROL_SCHEDULE.json'); rows=[]; all_render_events=0
expected_rasters={'OLD_extreme':1,'NEW_extreme':0,'OLD_origin':2,'NEW_origin':2,'OLD_peripheral':1,'NEW_peripheral':1}
for case in schedule['inputs']:
    label=case['variant']+'_'+case['asset'];root=RUNTIME/'controls'/label;result=js(root/'RESULT.json')
    srcsha=binding['source_sha256'] if case['variant']=='NEW' else baseline['old_source141_sha256']
    bpath=Path(result['binding_file']);raw_binding=read(bpath);bb=json.loads(raw_binding)
    rt=js(root/'io_audit/RUNTIME.json');proof=js(root/'RUNTIME_PROOF.json');sc=js(root/'stdio/CLOSE.json')
    ck(label+'/binding',sha(raw_binding)==result['binding_sha256']==rt['binding_sha256'] and bb['source_sha256']==srcsha==rt['source_sha256']==result['source_sha256'])
    ck(label+'/entry_bytes',sha(read(rt['entry']))==rt['entry_sha256'])
    ck(label+'/runtime_handle',proof['confirmed'] and proof['runtime_pid']==rt['pid'] and result['MCP_runtime_exit']['confirmed'] and result['MCP_runtime_exit']['exit_code']==0 and result['MCP_runtime_exit']['handle_closed'])
    ck(label+'/stdio_closed',sc==result['stdio_close'] and sc['exit_code']==0 and sc['confirmed'] and sc['process_handle_closed'] and sc['reader_stopped'] and all(sc['pipes_closed'].values()) and not sc['forced_kill'])
    native=result['native_final'];closed=js(root/'native/WORKER_CLOSED.json');session=js(root/'native/SESSION.json');ready=js(root/'native/READY.json')
    deadline=result['original_lifecycle_deadline_ns']; nc=result['native_close']
    ck(label+'/deadline',deadline==result['started_ns']+600_000_000_000 and deadline==closed['original_deadline_ns']==session['deadline_ns']==ready['deadline_ns']==nc['original_deadline_ns'] and result['blender_timeout_s']==result['public_request_budget_s']==30)
    ck(label+'/owned_exit',nc['exit_code']==0 and nc['process_reaped'] and nc['pid']==closed['pid']==session['pid']==ready['pid'] and not closed['poisoned'])
    ck(label+'/terminal_assets',closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint']==ready['initial_fingerprint'] and native['source_file_unchanged'] and native['protected_files_unchanged'] and sha(read(result['asset']['asset']))==result['asset']['asset_sha256'])
    ck(label+'/session_clocks',result['session_closed_ns']-result['started_ns']==result['complete_session_ns'] and result['postrun_closed_ns']-result['session_closed_ns']==result['postrun_validation_ns'])
    ios=[json.loads(line) for line in read(root/'io_audit/MCP_IO.jsonl').splitlines() if line]
    ck(label+'/io_copy',ios==result['io_audit'])
    receipts={js(p)['id']:js(p) for p in sorted((root/'stdio').glob('rpc_*/RECEIPT.json'))}
    for i in ios:
        rec=receipts[i['id']];folder=root/'stdio'/('rpc_%02d'%rec['index']);rx=read(folder/'RX.bin');tx=read(folder/'TX.bin')
        ck(label+'/wire/'+i['id'],len(rx)==rec['RX_bytes'] and sha(rx)==rec['RX_sha256'] and len(tx)==i['TX_bytes'] and sha(tx)==i['TX_sha256'] and sha(rx.replace(b'\r\n',b'\n'))==i['RX_text_UTF8_LF_sha256'] and len(rx.replace(b'\r\n',b'\n'))==i['RX_text_UTF8_LF_bytes'])
        ck(label+'/io_clock/'+i['id'],i['reply_completed_ns']-i['request_received_ns']==i['request_to_reply_ns'])
    requests=result['requests'];ck(label+'/requests',[r['id'] for r in requests]==[r['id'] for r in schedule['requests_per_slot']] and len(requests)==4)
    for r in requests:ck(label+'/outer_clock/'+r['id'],r['client_call_completed_ns']-r['client_call_started_ns']==r['client_outer_including_recording_ns'])
    ck(label+'/post_error_health',all(r.get('ping_success') for r in requests if r['result_kind']=='ping') and not requests[2]['is_error'])
    main=next(i for i in ios if i['id']=='target_observation');rec=receipts['target_observation']
    audit=[json.loads(line) for line in read(root/'audit.jsonl').splitlines() if line]
    attempts=[r for r in audit if r.get('event')=='active_observation_render_attempt']
    ck(label+'/raster_count',len(attempts)==expected_rasters[label]==main['raster_actual'])
    all_render_events+=len(attempts)
    if label=='NEW_extreme':ck('numeric_zero_construction',main['numeric_pre_render_proven'] and rt['numeric_pre_render_source_proof']['only_in_host_camera_function'] and requests[0]['is_error'] and requests[0]['image_blocks']==0)
    # Actual Python payload contains compressed source compile operands. Decode only; do not execute.
    wire=js(root/'native/WIRE/001/REQUEST.bin');code=wire['params']['code'];tree=ast.parse(code);embedded=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='compile' and len(node.args)>=2:
            n=node.args[0]
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='decompress':
                value=n.args[0].args[0].value;raw=zlib.decompress(base64.b64decode(value));path=node.args[1].value
                ck(label+'/embedded/'+path,raw==read(path));embedded.append({'path':path,'sha256':sha(raw)})
    ck(label+'/actual_host_source',any(e['path'].endswith('blender_host.py') and e['sha256']==sha(gb[(PRODUCT if case['variant']=='NEW' else BASE)+':human_eye_plugin/blender_host.py']) for e in embedded))
    index=js(root/'native/WIRE/INDEX.json');ck(label+'/host_index',index==result['host_wire_index'])
    for event in index:
        folder=root/'native/WIRE'/('%03d'%event['sequence']);tx=read(folder/'REQUEST.bin');rx=read(folder/'RESPONSE.bin')
        ck(label+'/host_bytes/'+str(event['sequence']),len(tx)==event['request_bytes'] and len(rx)==event['response_attempted_bytes'] and event['response_sendall_completed'])
    rows.append({'slot':label,'server_request_received_to_reply_completed_ns':main['request_to_reply_ns'],'client_stdin_flush_to_received_complete_ns':rec['received_complete_ns']-rec['stdin_flushed_ns'],'client_call_start_to_received_complete_ns':rec['received_complete_ns']-rec['started_ns'],'client_call_recording_complete_ns':rec['elapsed_ns'],'client_outer_including_recording_ns':requests[0]['client_outer_including_recording_ns'],'full_session_ns':result['complete_session_ns'],'postrun_validation_ns':result['postrun_validation_ns'],'rasters':len(attempts),'main_raw_rx_bytes':rec['RX_bytes'],'embedded_sources':embedded,'main_host_work':result['worker_events'][0].get('m2_work')})

claims=[js(p) for p in (RUNTIME/'budget/claims').glob('*.json')]; settlements={p.stem:js(p) for p in (RUNTIME/'budget/settlements').glob('*.json')}
ck('13_claims_no_pending',len(claims)==13 and {r['token'] for r in claims}==set(settlements))
starts=[r for r in claims if r['kind']=='Blender_start'];rasters=[r for r in claims if r['kind']=='raster_request']
ck('7_actual_starts',len(starts)==7 and all(settlements[c['token']]['pid'] and settlements[c['token']]['spawn_status']=='spawned' for c in starts))
for c in claims:ck('claim_settlement/'+c['token'],settlements[c['token']]['claim_sha256']==sha(read(RUNTIME/'budget/claims'/(c['token']+'.json'))))
ck('7_constructed_29_unconstructed',len(rasters)==6 and sum(c['reserved_upper_bound'] for c in rasters)==36 and sum(settlements[c['token']]['actual_attempts'] for c in rasters)==all_render_events==7 and sum(settlements[c['token']]['released_proven_unconstructed_reservation'] for c in rasters)==29)
prep=js(RUNTIME/'assets_01/PREPARATION.json');ck('builder',prep['closed_ns']-prep['started_ns']==prep['elapsed_ns'] and prep['exit_code']==0 and prep['passed'])
first=js(NS/'INSTALLED_PURE.json');fixed=js(NS/'INSTALLED_PURE_R1.json')
ck('installed_failure_retained',not first['passed_checked_scope'] and fixed['passed_checked_scope'])
failure=js(NS/'ACTUAL_REVIEW_ATTEMPT_01.json');ck('checker_failure_retained',bool(failure))
result={'passed':all(c['passed'] for c in checks),'checks':checks,'check_count':len(checks),'pins':pins,'micro':micro_results,'actual_cost':rows,'counts':{'starts':7,'rasters':7,'timed_helper_calls':14336,'warmup_calls':64,'archived_files':681,'archived_bytes':14961221},'builder_elapsed_ns':prep['elapsed_ns'],'scope':'offline source/bytes/clocks/budget; no new product/Blender/raster/model calls','notes':['Report RTT label denotes server MCP_IO interval, not complete caller RTT; raw caller boundaries separately recorded.','No new end-to-end performance conclusion: one sample each, extreme work differs.','Old A01 runtime unknown and cache deletion rejection remain historical; no cleanup attempted.','Full historical protected manifests hashed, not all inner members rechecked.','Blender held Popen wait/reap exit0 verified; separate Win32 handle closure not recorded.']}
(OUT/'RESULT.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf8')
print(json.dumps({'passed':result['passed'],'check_count':len(checks),'pin_count':len(pins),'micro':micro_results,'actual_cost':rows},default=str))
