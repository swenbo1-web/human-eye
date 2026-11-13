"""Independent raw-data cost audit. Never imports author executors or runs trials."""
import ast
import base64
import hashlib
import io
import json
import statistics
import struct
import zipfile
from collections import Counter
from fractions import Fraction
from pathlib import Path

B = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_002')
OUT = Path(__file__).resolve().parent
inputs = {}
checks = []


def raw(p):
    p = Path(p)
    x = p.read_bytes()
    inputs[str(p)] = {'bytes': len(x), 'sha256': hashlib.sha256(x).hexdigest()}
    return x


def read(p):
    return json.loads(raw(p))


def check(label, ok, detail=None):
    checks.append({'check': label, 'passed': bool(ok), 'detail': detail})


def sha(x):
    return hashlib.sha256(x).hexdigest()


def images(content):
    return [x for x in content if x.get('type') == 'image']


def image_info(content):
    rows = []
    for x in images(content):
        z = base64.b64decode(x['data'], validate=True)
        rows.append({'sha256': sha(z), 'bytes': len(z), 'base64': len(x['data']), 'mime': x['mimeType']})
    return rows


def fraction(x):
    return {'numerator': x.numerator, 'denominator': x.denominator, 'value': float(x)}


plan = read(B/'PLAN.json')
batch = read(B/'r/RUN_RESULT.json')
check('fixed_sequence', [r['slot'] for r in batch['records']] == ['N1','P1','P2','N2','N3','P3'])
check('six_actual_routes_CLI', batch['actual_routes'] == batch['actual_CLI_processes'] == 6)
check('six_result_folders', {p.name for p in (B/'r').iterdir() if p.is_dir()} == {'N1','P1','P2','N2','N3','P3'})
slots = []
seen_threads = []
previous_close = None
for row in batch['records']:
    slot = row['slot']; p = B/'r'/slot
    r = read(p/'RESULT.json'); c = read(p/'c/CONSUMER.json')
    t = read(p/'FINAL_TIMING.json'); ct = read(p/'c/FINAL_TIMING.json')
    metrics = read(p/'o/METRICS.json')
    check(slot+'.record_matches_batch', all(row[k] == v for k,v in r.items()))
    check(slot+'.completed', row['execution_state'] == c['status'] == 'completed' and t['accepted_success'] and ct['accepted_success'])
    check(slot+'.original_450_deadline', t['original_deadline_ns'] == r['deadline_ns'] == r['started_ns']+450_000_000_000 == c['deadline_ns'])
    check(slot+'.full_clock', t['elapsed_ns'] == t['result_closed_ns']-t['started_ns'] and t['started_ns']==r['started_ns'] and t['result_closed_ns'] < r['deadline_ns'])
    check(slot+'.nested_consumer_clock', t['started_ns'] <= ct['started_ns'] <= ct['consumer_record_closed_ns'] <= t['result_closed_ns'] and ct['full_turn_wall_ns']==ct['consumer_record_closed_ns']-ct['started_ns'])
    if previous_close is not None:check(slot+'.sequential', r['started_ns'] >= previous_close)
    previous_close=t['result_closed_ns']
    for key in ['consumer_process_cleanup','owner_process_cleanup','runtime_exit']:
        cleanup = r[key]
        check(slot+'.'+key, cleanup['confirmed'] and t['started_ns']<=cleanup['started_ns']<=cleanup['closed_ns']<=t['result_closed_ns'])
    check(slot+'.actual_process_exit_codes', r['consumer_process_cleanup']['exit_code']==r['owner_process_cleanup']['exit_code']==0 and r['runtime_exit']['exit_code']==1)
    check(slot+'.EOF_unknown_not_zero_cost', r['bridge_cleanup']['receipt_status']=='unknown' and r['bridge_cleanup']['missing_exit_count']==1)
    check(slot+'.fresh_and_one_turn', c['expected_thread_id'] is None and c['turn_index']==1 and 'resume' not in c['argv'])
    check(slot+'.original_model_requests', c['model']=='gpt-6.1-sol' and c['requested_effort']=='medium' and 'service_tier="default"' in c['argv'])
    check(slot+'.prompt_unchanged', c['input_sha256']==plan['expected_prompt_sha256'] and c['input_text_bytes']==2375)
    data=raw(p/'c/stdout.raw.bin'); lines=[z for z in data.splitlines(keepends=True) if z.strip()];ev=[json.loads(z) for z in lines]
    eventrows=[json.loads(z) for z in raw(p/'c/events.jsonl').splitlines() if z.strip()]
    check(slot+'.event_count_matches_raw',len(eventrows)==len(ev))
    for line,event,logged in zip(lines,ev,eventrows):
        expected=event
        if event.get('item',{}).get('type')=='reasoning':
            expected={'type':event['type'],'item':{'type':'reasoning','redacted':True},'raw_sha256':sha(line),'raw_bytes':len(line)}
        check(slot+'.events_exact_or_declared_reasoning_redaction',logged['event']==expected)
    check(slot+'.raw_stdout_sha_bytes', sha(data)==c['stdout_raw_sha256'] and len(data)==c['stdout_raw_bytes'])
    threads=[e['thread_id'] for e in ev if e['type']=='thread.started'];seen_threads.extend(threads)
    check(slot+'.one_fresh_thread', len(threads)==1 and threads[0]==c['thread_id']==r['observed_thread_id'])
    complete=[e for e in ev if e['type']=='turn.completed']
    check(slot+'.one_usage_complete',len(complete)==1 and sum(e['type']=='turn.started' for e in ev)==1)
    usage=complete[0]['usage']
    check(slot+'.usage_unmodified', [usage]==c['raw_usage_events']==r['raw_usage_events'] and usage==c['usage'])
    check(slot+'.no_visible_top_errors_retry',not any(e['type'] in ['error','turn.failed'] for e in ev) and not c['provider_retry_observations'] and not c['errors'])
    warnings=[e['item']['message'] for e in ev if e['type']=='item.completed' and e['item']['type']=='error']
    check(slot+'.warnings_retained',len(warnings)==2 and any('fallback metadata' in w for w in warnings))
    check(slot+'.unknown_metrics_retained', c['fees'] is c['provider_requests'] is c['resolved_effort'] is c['image_tokens'] is None)
    tool_rows=[e for e in eventrows if e['event']['type']=='item.completed' and e['event']['item']['type']=='mcp_tool_call']
    check(slot+'.tool_count',len(tool_rows)==r['actual_tool_calls']==metrics['tool_attempts']<=12)
    owner_images=[];cli_images=[];tool_ns=0;tool_intervals=[];tool_text_bytes=0
    for i,event in enumerate(tool_rows,1):
        item=event['event']['item'];tool=p/'o'/('tool_%02d'%i)
        req=read(tool/'REQUEST.json');resp=read(tool/'RESPONSE.json');receipt=read(tool/'RECEIPT.json')
        check(slot+'.tool%d.real_args'%i, req['params']['name']==item['tool'] and req['params']['arguments']==item['arguments'])
        check(slot+'.tool%d.real_result'%i, item['status']=='completed' and item['error'] is None and resp['result']['isError'] is False and item['result']['content']==resp['result']['content'])
        check(slot+'.tool%d.clock'%i,receipt['elapsed_ns']==receipt['closed_ns']-receipt['started_ns'] and c['prompt_submitted_ns']<=receipt['started_ns']<=receipt['closed_ns']<=event['perf_ns']<=c['final_received_ns'])
        check(slot+'.tool%d.duplicate_metric'%i,receipt==metrics['tools'][i-1])
        owner_images+=image_info(resp['result']['content']);cli_images+=image_info(item['result']['content'])
        tool_text_bytes+=sum(len(x['text'].encode()) for x in item['result']['content'] if x['type']=='text')
        tool_ns+=receipt['elapsed_ns'];tool_intervals.append((receipt['started_ns'],receipt['closed_ns']))
    check(slot+'.nonoverlap_tools', all(a[1]<=b[0] for a,b in zip(tool_intervals,tool_intervals[1:])))
    construction=read(p/'o/IMAGE_CONSTRUCTIONS.json');constructed=construction['constructed']
    check(slot+'.no_image_failures',not construction['failed'] and not construction['post_construction_failures'])
    check(slot+'.constructed_image_count',len(constructed)==metrics['constructed_image_blocks']==len(cli_images)==c['public_image_count'])
    check(slot+'.same_owner_CLI_images',owner_images==cli_images)
    for image,cr in zip(cli_images,constructed):
        check(slot+'.constructed_image_exact',image['sha256']==cr['PNG_sha256'] and image['bytes']==cr['PNG_bytes_read'] and image['base64']==cr['base64_chars'] and cr['constructed'] and cr['delivery_ready'])
        check(slot+'.constructed_inside_slot',r['started_ns']<=cr['started_ns']<=cr['constructed_ns']<=cr['closed_ns']<=t['result_closed_ns'])
    check(slot+'.CLI_image_bytes',sum(x['bytes'] for x in cli_images)==c['public_image_bytes']==metrics['constructed_PNG_bytes']==metrics['server_socket_sent_PNG_bytes'])
    check(slot+'.image_base64_bytes',sum(x['base64'] for x in cli_images)==c['base64_bytes']==metrics['constructed_base64_chars']==metrics['server_socket_sent_base64_chars'])
    frame_files=sorted((p/'o/frames').glob('*/FRAME.json'));array_bytes=0;npz_bytes=0;png_bytes=0;raster_ns=0;views=[]
    for framefile in frame_files:
        f=read(framefile);views.append(f['view_name'])
        png=raw(Path(f['PNG']));npz=raw(Path(f['NPZ']))
        check(slot+'.frame_files_'+f['view_name'],len(png)==f['PNG_bytes'] and sha(png)==f['PNG_sha256'] and len(npz)==f['NPZ_bytes'] and sha(npz)==f['NPZ_sha256'])
        nbytes=0
        with zipfile.ZipFile(io.BytesIO(npz)) as z:
            for name,meta in f['arrays'].items():
                payload=z.read(name+'.npy');check(slot+'.npy_magic_'+name,payload[:6]==b'\x93NUMPY')
                hs=2 if payload[6]==1 else 4;hsize=int.from_bytes(payload[8:8+hs],'little');header=ast.literal_eval(payload[8+hs:8+hs+hsize].decode());a=payload[8+hs+hsize:]
                check(slot+'.array_'+name,len(a)==meta['nbytes'] and sha(a)==meta['sha256'] and list(header['shape'])==meta['shape'] and header['descr']==meta['dtype_str'])
                nbytes+=len(a)
        check(slot+'.array_payload_sum',nbytes==f['array_payload_bytes'])
        check(slot+'.raster_clock',r['started_ns']<=f['intent_ns']<=f['render_started_ns']<=f['render_closed_ns']<=f['completed_ns']<=t['result_closed_ns'])
        array_bytes+=nbytes;npz_bytes+=len(npz);png_bytes+=len(png);raster_ns+=f['render_closed_ns']-f['render_started_ns']
    common=metrics['common']
    check(slot+'.rasters_all_completed',len(frame_files)==len(set(views))==r['new_renders']==common['render_attempts']==common['raster_completed']==common['frames_completed']<=6)
    check(slot+'.frame_byte_totals',array_bytes==common['array_payload_bytes'] and png_bytes==common['PNG_bytes'] and npz_bytes==common['NPZ_bytes'])
    transport=read(p/'o/TRANSPORT.json');sent=[]
    tx_total=rx_total=0
    for j,tr in enumerate(transport,1):
        folder=p/'o'/('rpc_%03d'%j);tx=raw(folder/'TCP_TX.bin');rx=raw(folder/'TCP_RX.bin');wrapped=json.loads(rx)
        check(slot+'.tcp_lengths_%d'%j,len(tx)==tr['request_bytes'] and len(rx)==tr['outer_TCP_JSON_bytes'] and tr['send_confirmed'] and tr['send_error'] is None)
        sent+=image_info(wrapped['result'].get('result',{}).get('content',[]))
        tx_total+=len(tx);rx_total+=len(rx)
    check(slot+'.server_sent_images_equal_CLI',sent==cli_images)
    stdio_tx=sum(len(raw(f)) for f in (p/'c/attachments').glob('*/*/TX.bin'))
    stdio_rx=sum(len(raw(f)) for f in (p/'c/attachments').glob('*/*/RX.bin'))
    check(slot+'.stdio_counts',stdio_tx==c['MCP_stdio_TX_bytes'] and stdio_rx==c['MCP_stdio_RX_bytes'])
    check(slot+'.socket_byte_totals',tx_total==metrics['server_socket_request_bytes'] and rx_total==metrics['server_socket_sent_outer_TCP_JSON_bytes'])
    check(slot+'.socket_images_count',len(sent)==metrics['server_socket_sent_image_blocks'])
    # Source reads establish that raw ZIP/input readback occur before RESULT clock;
    # hashes establish these artifacts were the files referred to by the result.
    for receipt,path_key,hash_key,size_key in [(r['originals'],'path','sha256','bytes'),(c['archive'],'archive','archive_sha256','archive_bytes')]:
        archive=raw(Path(receipt[path_key]));check(slot+'.archive_digest',sha(archive)==receipt[hash_key] and len(archive)==receipt[size_key])
    prompt_final=c['final_received_ns']-c['prompt_submitted_ns']
    check(slot+'.phase_sum', r['started_ns']<=c['prompt_submitted_ns']<=c['final_received_ns']<=c['turn_completed_ns']<=c['process_exit_ns']<=t['result_closed_ns'])
    slots.append({'slot':slot,'group':row['group'],'full_ns':t['elapsed_ns'],'usage':usage,'reported_input_plus_output':usage['input_tokens']+usage['output_tokens'],
        'tools':len(tool_rows),'tool_ns':tool_ns,'prompt_to_final_ns':prompt_final,'prompt_to_final_outside_tools_ns':prompt_final-tool_ns,
        'before_prompt_ns':c['prompt_submitted_ns']-r['started_ns'],'after_final_ns':t['result_closed_ns']-c['final_received_ns'],
        'turn_complete_to_process_exit_ns':c['process_exit_ns']-c['turn_completed_ns'],'after_process_exit_ns':t['result_closed_ns']-c['process_exit_ns'],
        'rasters':len(frame_files),'raster_ns':raster_ns,'array_payload_bytes':array_bytes,'PNG_file_bytes':png_bytes,'NPZ_file_bytes':npz_bytes,
        'image_blocks':len(cli_images),'image_PNG_bytes':sum(x['bytes'] for x in cli_images),'image_base64_chars':sum(x['base64'] for x in cli_images),
        'tool_text_bytes':tool_text_bytes,'stdout_bytes':len(data),'stdio_TX_bytes':stdio_tx,'stdio_RX_bytes':stdio_rx,'TCP_TX_bytes':tx_total,'TCP_RX_bytes':rx_total,
        'fresh_thread':threads[0],'usage_semantics':c['usage_semantics']})

check('six_unique_fresh_threads',len(seen_threads)==len(set(seen_threads))==6 and seen_threads==batch['observed_fresh_threads'])
check('fixed_formal_budget',sum(x['rasters'] for x in slots)==24<=plan['formal_render_cap']==36 and sum(x['tools'] for x in slots)==14)
by_slot={x['slot']:x for x in slots}
pairs=[{'pair':n,'N_ns':by_slot['N'+str(n)]['full_ns'],'P_ns':by_slot['P'+str(n)]['full_ns'],
        'P_over_N':fraction(Fraction(by_slot['P'+str(n)]['full_ns'],by_slot['N'+str(n)]['full_ns']))} for n in [1,2,3]]
time_ratio=statistics.median(Fraction(x['P_ns'],x['N_ns']) for x in pairs)
totals={}
for arm in ['N','P']:
    selected=[x for x in slots if x['group']==arm]
    totals[arm]={k:sum(x[k] for x in selected) for k,v in selected[0].items() if type(v) is int}
    totals[arm]['usage']={k:sum(x['usage'][k] for x in selected) for k in selected[0]['usage']}
    totals[arm]['median_full_ns']=statistics.median(x['full_ns'] for x in selected)
usage_ratio=Fraction(totals['P']['reported_input_plus_output'],totals['N']['reported_input_plus_output'])
bt=read(B/'r/BATCH_TIMING.json');lt=read(B/'r/LAUNCH_TIMING.json');lr=read(B/'r/LAUNCH_RESULT.json')
prep=read(B/'admin/PREPARATION_BEGAN.json');formal=read(B/'FORMAL_STARTED.json')
check('batch_clock',bt['elapsed_ns']==bt['RUN_RESULT_closed_ns']-bt['started_ns'] and bt['started_ns']==batch['started_ns'])
check('launcher_clock',lt['elapsed_ns']==lt['LAUNCH_RESULT_closed_ns']-lt['started_ns'] and lt['started_ns']==lr['started_ns'])
check('nested_formal_clocks',lt['started_ns']<=formal['started_ns']<=bt['started_ns']<=batch['records'][0]['started_ns'] and previous_close<=bt['RUN_RESULT_closed_ns']<=lt['LAUNCH_RESULT_closed_ns'])
timing={'six_slot_sum_ns':sum(x['full_ns'] for x in slots),'batch_ns':bt['elapsed_ns'],'batch_unassigned_ns':bt['elapsed_ns']-sum(x['full_ns'] for x in slots),
        'launcher_ns':lt['elapsed_ns'],'launcher_outside_batch_ns':lt['elapsed_ns']-bt['elapsed_ns'],
        'preparation_marker_to_formal_ns':formal['started_ns']-prep['observed_ns'],
        'launcher_prefix_overlaps_preparation_ns':formal['started_ns']-lt['started_ns'],
        'preparation_marker_to_launcher_close_ns':lt['LAUNCH_RESULT_closed_ns']-prep['observed_ns']}
check('preparation_no_double_count',timing['preparation_marker_to_formal_ns']+timing['launcher_ns']-timing['launcher_prefix_overlaps_preparation_ns']==timing['preparation_marker_to_launcher_close_ns'])
local_cost=[]
for group in ['N','P']:
    local=B/'local'/(group+'1');local_record=read(local/'LOCAL_RESULT.json')
    # Local results reference their completed real capture, with no Pro or raster cost.
    check('local_'+group+'_single_attempt',len(list((B/'local').glob(group+'*')))==1)
    check('local_'+group+'_recorded',local_record['group']==group)
    lrte=read(local/('LOCAL_'+group+'1')/'RESULT.json')
    lm=read(local/('LOCAL_'+group+'1')/'o/METRICS.json')
    lcon=read(local/('LOCAL_'+group+'1')/'c/CONSUMER.json')
    lraw=[json.loads(z) for z in raw(local/('LOCAL_'+group+'1')/'c/stdout.raw.bin').splitlines() if z.strip()]
    ltools=[e['item']for e in lraw if e['type']=='item.completed' and e['item']['type']=='mcp_tool_call']
    check('local_'+group+'_cost_zero_raster_image_Pro',lrte['execution_kind']=='synthetic_local_process' and lm['common']['render_attempts']==lm['constructed_image_blocks']==lcon['public_image_count']==0 and len(ltools)==2)
    check('local_'+group+'_actual_error_then_success',[x['status'] for x in ltools]==['failed','completed'])
    local_cost.append({'group':group,'tools':len(ltools),'rasters':lm['common']['render_attempts'],'images':lm['constructed_image_blocks'],'Pro_calls':0})

# Only now compare the independently computed totals with the author's ledger.
author=read(B/'admin/COST_AUTHOR.json')
for arm in ['N','P']:
    own=totals[arm];a=author['group_totals_all_three'][arm]
    for ak,ok in [('full_slot_wall_ns','full_ns'),('tools','tools'),('rasters','rasters'),('raw_usage_sums','usage'),('raw_stdout_bytes','stdout_bytes'),('array_payload_bytes','array_payload_bytes'),('stdio_TX_bytes','stdio_TX_bytes'),('stdio_RX_bytes','stdio_RX_bytes'),('TCP_TX_bytes','TCP_TX_bytes'),('TCP_RX_bytes','TCP_RX_bytes')]:
        check('author_'+arm+'_'+ak,a[ak]==own[ok])
check('author_primary_time_ratio',author['paired_median_P_over_N']==float(time_ratio))
check('author_primary_usage_ratio',author['reported_total_usage_P_over_N']==float(usage_ratio))

# Read execution source, not execute it, to establish stage-clock boundaries.
raw(B.parent/'m4_active_coverage_consumption_001/driver.py')
raw(B/'launcher.py')
result={'schema':'root-independent-coverage-consumption-002-cost-v1','candidate_commit':'c556d29156e7d65fc02238dca63321ac062d2c1a',
        'checks':checks,'check_count':len(checks),'passed':sum(x['passed'] for x in checks),'failed':[x for x in checks if not x['passed']],
        'slots':slots,'pairs':pairs,'totals':totals,'paired_time_P_over_N':fraction(time_ratio),'relative_time_reduction':float(1-time_ratio),
        'reported_usage_P_over_N':fraction(usage_ratio),'relative_reported_usage_reduction':float(1-usage_ratio),'timing':timing,'local_cost':local_cost,
        'quality_qualification':'Separate independent review required; this cost audit does not grade answers.',
        'new_model_CLI_actor_raster_Blender_calls':0,
        'limitations':['CLI usage semantics retain unconfirmed_turn_or_session_scope; fresh single-turn calls avoid resume differencing.',
            'Actual provider model/effort, provider internal calls, image-token split and fees remain unmeasured.',
            'Tool-external time includes model/backend/network/client waits, not isolated model inference.',
            'Actor process RSS is unmeasured; ndarray payload is not RSS or model input.',
            'Preparation marker omits earlier editing/review, and review-model usage is not completely counted.',
            'Formal stdio EOF receipts remain unknown, although retained handles confirm actual process exit.']}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'INPUTS.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'checks':len(checks),'passed':result['passed'],'failed':result['failed'],'time_reduction':result['relative_time_reduction'],'usage_reduction':result['relative_reported_usage_reduction'],'timing':timing},ensure_ascii=False))
