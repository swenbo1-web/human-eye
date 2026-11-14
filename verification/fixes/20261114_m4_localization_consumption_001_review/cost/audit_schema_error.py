"""Independent saved-only accounting. No author/product/CLI/raster execution."""
from pathlib import Path
from fractions import Fraction
from collections import Counter
import ast,base64,hashlib,io,json,math,struct,zipfile

R=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=R/'verification/m4_region_localization_consumption_001'; O=Path(__file__).parent
inputs={}; checks=[]
def raw(p):
    p=Path(p); b=p.read_bytes(); inputs[str(p)]=hashlib.sha256(b).hexdigest(); return b
def js(p):return json.loads(raw(p))
def ck(n,v):checks.append({'name':n,'passed':bool(v)})
archive=js(H/'EXTERNAL_ARCHIVE.json'); idx={row['original_relative_path']:R/row['archive_path'] for row in archive['files']}
original={row['original_path']:R/row['archive_path'] for row in archive['files']}
def saved(n):return js(idx[n])
def absraw(p):return raw(original[p])
cost=js(H/'COST_REPORT.json'); author={x['slot']:x for x in cost['slots']}
frozen=js(H/'FROZEN.json'); seal=js(H/'QUALITY_SEAL.json')
ck('seal_binding',hashlib.sha256(raw(H/'QUALITY_SEAL.json')).hexdigest()==cost['quality_seal_sha256'])
ck('seal_completed6',seal['denominator']==seal['quality_complete']==6 and seal['cost_analysis_unlocked_after_this_seal'])
ck('score_source_pin',hashlib.sha256(raw(H/'admin/score_quality.py')).hexdigest()==seal['frozen_scoring_source_sha256']==frozen['files_sha256'][str(H/'admin/score_quality.py')])
for row in seal['inputs']:ck('quality_pin:'+row['path'],hashlib.sha256(raw(H/row['path'])).hexdigest()==row['sha256'])
order=['N1','P1','P2','N2','N3','P3']; slots=[]; tids=[]; pids=[]; pngbytes=npzbytes=arraybytes=0
for slot in order:
    stem='formal/'+slot; res=saved(stem+'/RESULT.json'); ft=saved(stem+'/FINAL_TIMING.json')
    c=saved(stem+'/c/CONSUMER.json'); ct=saved(stem+'/c/FINAL_TIMING.json')
    met=saved(stem+'/o/METRICS.json'); obs=saved(stem+'/o/OBSERVATIONS.json')
    tools=saved(stem+'/o/TOOLS.json')['tools']; construct=saved(stem+'/o/IMAGE_CONSTRUCTIONS.json')
    rt=res['runtime_exit']; tids.append(c['thread_id']); pids += [res['owner_pid'],res['consumer_pid'],res['runtime_binding']['runtime_pid']]
    ck(slot+':outer_clock',ft['result_closed_ns']-ft['started_ns']==ft['elapsed_ns'])
    ck(slot+':consumer_clock',ct['consumer_record_closed_ns']-ct['started_ns']==ct['full_turn_wall_ns'])
    ck(slot+':450s',ft['original_deadline_ns']-ft['started_ns']==450_000_000_000 and ft['result_closed_ns']<ft['original_deadline_ns'])
    ck(slot+':nested',ft['started_ns']<=ct['started_ns']<=c['prompt_submitted_ns']<=c['final_received_ns']<=c['turn_completed_ns']<=c['process_exit_ns']<=ct['consumer_record_closed_ns']<=ft['result_closed_ns'])
    ck(slot+':completed',ft['accepted_success'] and res['outer_valid_completion'] and not res['errors'] and not res['stop_remaining_reasons'])
    for role in ['consumer_process_cleanup','owner_process_cleanup']:
        q=res[role];ck(slot+':'+role,q['exit_code']==0 and q['reaped'] and q['process_handle_closed'] and not q['kill_requested'] and all(q['pipes_closed'].values()) and q['closed_ns']<=ft['result_closed_ns'])
    ck(slot+':thin_held_exit1',rt['confirmed'] and rt['exited'] and rt['exit_code']==1 and rt['handle_closed'] and rt['closed_ns']<=ft['result_closed_ns'])
    ck(slot+':runtime_binding',res['runtime_binding']['confirmed'] and res['runtime_binding']['after_stdio_STARTED'])
    stdout=raw(idx[stem+'/c/stdout.raw.bin']); events=[json.loads(line) for line in stdout.splitlines() if line]
    usages=[e['usage'] for e in events if e.get('type')=='turn.completed']
    ck(slot+':usage_once',len(usages)==1 and usages==c['raw_usage_events']==res['raw_usage_events'])
    u=usages[0];ck(slot+':usage_subsets',u['cached_input_tokens']<=u['input_tokens'] and u['reasoning_output_tokens']<=u['output_tokens'])
    item=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
    ck(slot+':tool_counts',len(item)==len(tools)==met['tool_attempts']==res['actual_tool_calls']<=12)
    ck(slot+':tool_order',[i['tool'] for i in item]==[t['name'] for t in tools])
    ck(slot+':no_active',all(t['name']!='active_observation' for t in tools) and not obs['active'] and not obs['replays'] and met['common']['product_observation_calls']==0)
    images=[]
    for i in item:
        for block in (i.get('result') or {}).get('content',[]):
            if block.get('type')=='image':
                b=base64.b64decode(block['data'],validate=True)
                ck(slot+':image512',b[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',b[16:24])==(512,512))
                images.append({'bytes':len(b),'base64':len(block['data']),'sha256':hashlib.sha256(b).hexdigest()})
    ck(slot+':image_construct_delivery',len(images)==len(construct['constructed'])==c['public_image_count']==met['server_socket_sent_image_blocks'] and not construct['failed'] and not construct['post_construction_failures'])
    ck(slot+':image_order',[i['sha256'] for i in images]==[x['PNG_sha256'] for x in construct['constructed']]==[x['PNG_sha256'] for x in c['image_deliveries']])
    for i,receipt in zip(images,construct['constructed']):ck(slot+':image_receipt',i['bytes']==receipt['PNG_bytes_read'] and i['base64']==receipt['base64_chars'] and receipt['constructed'] and receipt['constructed_ns']<=receipt['closed_ns'])
    ck(slot+':raster_six',len(obs['frames'])==len(obs['render_attempts'])==met['new_renders']==6)
    raster_ns=frame_ns=0; frame_png=frame_npz=frame_arrays=0
    for fr in obs['frames']:
        p=absraw(fr['PNG']); z=absraw(fr['NPZ']); frame_png+=len(p);frame_npz+=len(z)
        ck(slot+':frame_file_sha:'+fr['view_name'],len(p)==fr['PNG_bytes'] and len(z)==fr['NPZ_bytes'] and hashlib.sha256(p).hexdigest()==fr['PNG_sha256'] and hashlib.sha256(z).hexdigest()==fr['NPZ_sha256'])
        with zipfile.ZipFile(io.BytesIO(z)) as archive_zip:
            ck(slot+':four_arrays',set(archive_zip.namelist())=={n+'.npy' for n in ['color','depth','owners','triangle_ids']})
            for name in ['color','depth','owners','triangle_ids']:
                b=archive_zip.read(name+'.npy');ck(slot+':NPY_magic',b[:6]==b'\x93NUMPY')
                width=2 if b[6]==1 else 4; hlen=int.from_bytes(b[8:8+width],'little'); h=ast.literal_eval(b[8+width:8+width+hlen].decode().strip());payload=b[8+width+hlen:]
                nbytes=math.prod(h['shape'])*int(h['descr'][2:]);meta=fr['arrays'][name]
                ck(slot+':array:'+fr['view_name']+':'+name,len(payload)==nbytes==meta['nbytes'] and list(h['shape'])==meta['shape'] and hashlib.sha256(payload).hexdigest()==meta['sha256'])
                frame_arrays+=nbytes
        ck(slot+':frame_clock',fr['started_ns']<=fr['render_started_ns']<=fr['render_closed_ns']<=fr['completed_ns'])
        raster_ns+=fr['render_closed_ns']-fr['render_started_ns'];frame_ns+=fr['completed_ns']-fr['started_ns']
    pngbytes+=frame_png; npzbytes+=frame_npz; arraybytes+=frame_arrays
    ck(slot+':array_totals',frame_arrays==met['common']['array_payload_bytes'] and frame_png==met['common']['PNG_bytes'] and frame_npz==met['common']['NPZ_bytes'])
    txnames=[p for p in idx if p.startswith(stem+'/c/attachments/') and p.endswith('/TX.bin')];rxnames=[p for p in idx if p.startswith(stem+'/c/attachments/') and p.endswith('/RX.bin')]
    tx=sum(len(raw(idx[p])) for p in txnames);rx=sum(len(raw(idx[p])) for p in rxnames)
    textbytes=wire_images=0
    for p in rxnames:
        response=json.loads(raw(idx[p]));content=response.get('result',{}).get('content',[])
        for b in content:
            if b['type']=='text':textbytes+=len(b['text'].encode())
            if b['type']=='image':wire_images+=1
    ck(slot+':wire_counts',tx==c['MCP_stdio_TX_bytes'] and rx==c['MCP_stdio_RX_bytes']==met['server_socket_sent_MCP_JSON_bytes'] and wire_images==len(images) and textbytes==met['server_socket_sent_text_UTF8_bytes'])
    for t in tools:ck(slot+':tool_elapsed',t['closed_ns']-t['started_ns']==t['elapsed_ns'])
    service=sum(t['closed_ns']-t['started_ns'] for t in tools)
    row={'slot':slot,'elapsed_ns':ft['elapsed_ns'],'started_ns':ft['started_ns'],'closed_ns':ft['result_closed_ns'],'usage':u,'input_plus_output':u['input_tokens']+u['output_tokens'],'tool_calls':len(tools),'business_errors':sum(t['is_error'] for t in tools),'raster_calls':len(obs['frames']),'CLI_images':len(images),'CLI_PNG_bytes':sum(i['bytes'] for i in images),'base64_chars':sum(i['base64'] for i in images),'stdio_TX':tx,'stdio_RX':rx,'text_UTF8_bytes':textbytes,'stdout_bytes':len(stdout),'raster_ns':raster_ns,'frames_ns':frame_ns,'tools_ns':service,'generated_PNG':frame_png,'generated_NPZ':frame_npz,'array_payload':frame_arrays}
    ac=author[slot]
    ck(slot+':author_time_usage',row['elapsed_ns']==ac['timing']['full_outer']['elapsed_ns'] and row['input_plus_output']==ac['reported_input_plus_output'])
    ck(slot+':author_frames',raster_ns==ac['frame_raster_sum_ns'] and frame_ns==ac['frame_total_sum_ns'])
    slots.append(row)
ck('six_distinct_contexts',len(set(tids))==6)
ck('18_distinct_process_ids',len(set(pids))==18)
ck('fixed_order',order==frozen['formal_sequence'] and all(slots[i]['closed_ns']<=slots[i+1]['started_ns'] for i in range(5)))
intents=[saved(p) for p in idx if p.startswith('raster_budget/') and p.endswith('/INTENT.json')]
ck('40_durable_attempts',len(intents)==40 and sorted(x['global_attempt'] for x in intents)==list(range(1,41)))
ck('phase_rasters',Counter(x['phase'] for x in intents)=={'preparation':4,'formal':36})
ck('native_formal',all(x['origin']=='native' for x in intents if x['phase']=='formal'))
prep=js(H/'PREPARATION.json');pn=js(H/'preparation/N1_PROCESS.json');pp=js(H/'preparation/P1_PROCESS.json');pq=js(H/'PREPARATION_QUALIFICATION.json')
ck('prep_clock',pq['before_publication_ns']-pn['started_ns']==prep['recorded_validation_window']['elapsed_ns']==152008315100)
ck('prep_2fake',pn['new_model_sessions']==pp['new_model_sessions']==0 and pn['exit_code']==pp['exit_code']==0 and prep['total_preparation_rasters']==4)
ck('prep_limits',prep['preparation_cap']==8 and len(intents)<=44)
parent=js(H/'FORMAL_PROCESS.json'); batch=saved('formal/BATCH_TIMING.json'); launch=saved('formal/LAUNCH_TIMING.json')
ck('parent_clock',parent['closed_ns']-parent['started_ns']==parent['elapsed_ns']==1028889168100 and parent['exit_code']==0 and parent['formal_attempt']==1)
ck('parent_includes_all',parent['started_ns']<=launch['started_ns']<=batch['started_ns']<=slots[0]['started_ns'] and slots[-1]['closed_ns']<=batch['RUN_RESULT_closed_ns']<=launch['launch_result_closed_ns']<=parent['closed_ns'])
ck('freeze_before_formal',frozen['frozen_before_publication_ns']<parent['started_ns'])
ck('quality_after_six',seal['sealed_ns']>parent['closed_ns'])
groups={g:{'elapsed_ns':sum(x['elapsed_ns'] for x in slots if x['slot'][0]==g),'input_plus_output':sum(x['input_plus_output'] for x in slots if x['slot'][0]==g)} for g in ['N','P']}
pairs=[]
for i in range(1,4):
    n=next(x for x in slots if x['slot']=='N'+str(i));p=next(x for x in slots if x['slot']=='P'+str(i))
    pairs.append({'pair':i,'time_ratio':str(Fraction(p['elapsed_ns'],n['elapsed_ns'])),'usage_ratio':str(Fraction(p['input_plus_output'],n['input_plus_output']))})
median=sorted(Fraction(x['time_ratio']) for x in pairs)[1]; usage=Fraction(groups['P']['input_plus_output'],groups['N']['input_plus_output'])
totals={'elapsed_ns':sum(x['elapsed_ns'] for x in slots),'parent_elapsed_ns':parent['elapsed_ns'],'generated_PNG_bytes':pngbytes,'generated_NPZ_bytes':npzbytes,'array_payload_bytes':arraybytes,'tools':sum(x['tool_calls'] for x in slots),'business_errors':sum(x['business_errors'] for x in slots),'CLI_images':sum(x['CLI_images'] for x in slots),'CLI_PNG_bytes':sum(x['CLI_PNG_bytes'] for x in slots),'base64_chars':sum(x['base64_chars'] for x in slots),'stdio_TX_bytes':sum(x['stdio_TX'] for x in slots),'stdio_RX_bytes':sum(x['stdio_RX'] for x in slots),'sent_text_UTF8_bytes':sum(x['text_UTF8_bytes'] for x in slots),'stdout_bytes':sum(x['stdout_bytes'] for x in slots),'tools_ns':sum(x['tools_ns'] for x in slots),'raster_ns':sum(x['raster_ns'] for x in slots),'frames_ns':sum(x['frames_ns'] for x in slots)}
expected={'elapsed_ns':1026309909400,'generated_PNG_bytes':92760,'generated_NPZ_bytes':1093008,'array_payload_bytes':179306496,'tools':50,'business_errors':2,'CLI_images':18,'CLI_PNG_bytes':50756,'base64_chars':67680,'stdio_TX_bytes':115969,'stdio_RX_bytes':582569,'sent_text_UTF8_bytes':428639,'stdout_bytes':754382,'tools_ns':16733239400,'raster_ns':7435517900,'frames_ns':8835310200}
for k,v in expected.items():ck('total:'+k,totals[k]==v)
for row in archive['files']:
    p=R/row['archive_path']
    if str(p) in inputs:ck('archive_pin:'+row['original_relative_path'],inputs[str(p)]==row['sha256'])
stable=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==s for p,s in inputs.items());ck('input_hashes_stable',stable)
result={'passed':all(x['passed'] for x in checks),'checks':len(checks),'failures':[x for x in checks if not x['passed']],'slots':slots,'groups':groups,'pairs':pairs,'time_ratio_median_fraction':str(median),'time_ratio_median':float(median),'usage_total_ratio_fraction':str(usage),'usage_total_ratio':float(usage),'totals':totals,'inputs':inputs,'check_details':checks,'new_product_model_Blender_raster_benchmark_calls':0,'scope':'Saved-only accounting; cohort differences are not product algorithm benefits because all six used native computation and P active adoption is 0/3.','preparation_read_error':'One exploratory schema printer assumed TRANSPORT was dict; actual list corrected before this audit; no source modifications or product calls.'}
(O/'RESULTS.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ['slots','inputs','check_details']},indent=2))
