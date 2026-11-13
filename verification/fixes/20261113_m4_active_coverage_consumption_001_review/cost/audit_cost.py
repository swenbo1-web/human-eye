"""Independent existing-record arithmetic audit; no author modules imported."""
import base64
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import zipfile
import numpy as np

BASE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_001')
OUT=Path(__file__).resolve().parent
CHECKS=[]; INPUTS={}; ROWS={}
def raw(p):
    p=Path(p);b=p.read_bytes();INPUTS[str(p)]=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest());return b
def doc(p):return json.loads(raw(p))
def enc(x):return json.dumps(x,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8')
def ck(name,ok,detail=None):CHECKS.append(dict(name=name,passed=bool(ok),detail=detail))
def eq(name,a,b):ck(name,a==b,dict(actual=a,expected=b) if a!=b else None)
def interval(name,d,start,end,total='elapsed_ns'):
    eq(name,d[end]-d[start],d[total]);ck(name+'/nonnegative',d[end]>=d[start])
def image_metrics(content):
    result=dict(image_blocks=0,PNG_bytes=0,base64_chars=0,image_block_JSON_bytes=0,text_UTF8_bytes=0)
    for b in content:
        if b['type']=='image':
            png=base64.b64decode(b['data'],validate=True)
            ck('image_png_signature',png.startswith(b'\x89PNG\r\n\x1a\n') and b['mimeType']=='image/png')
            result['image_blocks']+=1;result['PNG_bytes']+=len(png);result['base64_chars']+=len(b['data'])
            result['image_block_JSON_bytes']+=len(enc(b))
        elif b['type']=='text':result['text_UTF8_bytes']+=len(b['text'].encode('utf8'))
    return result

plan=doc(BASE/'PLAN.json');batch=doc(BASE/'r/RUN_RESULT.json');bt=doc(BASE/'r/BATCH_TIMING.json')
order=[r['slot'] for r in plan['sequence']]
eq('fixed_sequence',order,['N1','P1','P2','N2','N3','P3'])
eq('actual_records', [r['slot'] for r in batch['records']],order)
eq('six_actual',batch['actual_routes'],6)
interval('batch_window',bt,'started_ns','RUN_RESULT_closed_ns')
for slot in order:
    folder=BASE/'r'/slot;o=folder/'o';c=folder/'c'
    route=doc(folder/'RESULT.json');timing=doc(folder/'FINAL_TIMING.json');consumer=doc(c/'CONSUMER.json')
    tools=doc(o/'TOOLS.json');metrics=doc(o/'METRICS.json');obs=doc(o/'OBSERVATIONS.json');construct=doc(o/'IMAGE_CONSTRUCTIONS.json')
    transport=doc(o/'TRANSPORT.json');close=doc(o/'CLOSE.json');endpoint=doc(folder/'ENDPOINT.json')
    prefix=slot+'/'
    interval(prefix+'full_interval',timing,'started_ns','result_closed_ns')
    eq(prefix+'same_start',route['started_ns'],timing['started_ns'])
    eq(prefix+'deadline_450s',timing['original_deadline_ns']-timing['started_ns'],450_000_000_000)
    for d,k in [(route,'deadline_ns'),(consumer,'deadline_ns'),(consumer,'episode_deadline_ns'),(obs,'deadline_ns'),(endpoint,'chain_deadline_ns')]:
        eq(prefix+'original_deadline:'+k,d[k],timing['original_deadline_ns'])
    ck(prefix+'full_inside_deadline',timing['result_closed_ns']<timing['original_deadline_ns'])
    for k in ('consumer_process_cleanup','owner_process_cleanup'):
        x=route[k];ck(prefix+k, x['confirmed'] and x['reaped'] and x['process_handle_closed'])
        ck(prefix+k+'/inside_window',timing['started_ns']<=x['started_ns']<=x['closed_ns']<=timing['result_closed_ns'])
        interval(prefix+k+'/interval',x,'started_ns','closed_ns')
    binding=doc(c/'RUNTIME_BINDING.json');runtime=route['runtime_exit']
    ck(prefix+'runtime_bound',binding['confirmed'] and binding['after_stdio_STARTED'] and binding['runtime_pid']==binding['stdio_STARTED']['pid'])
    ck(prefix+'runtime_image',binding['actual_executable_sha256']==binding['expected_executable_sha256'])
    ck(prefix+'runtime_exit',runtime['confirmed'] and runtime['exited'] and runtime['handle_closed'])
    ck(prefix+'runtime_window',timing['started_ns']<binding['stdio_STARTED']['started_ns']<=binding['observed_ns']<=binding['actual_image_checked_ns']<runtime['started_ns']<=runtime['closed_ns']<timing['result_closed_ns'])
    interval(prefix+'runtime_exit_interval',runtime,'started_ns','closed_ns')
    ck(prefix+'EOF_unknown_preserved',route['bridge_cleanup']['confirmed'] is None)
    ck(prefix+'owner_closed',close['confirmed'] and close['server_thread_stopped'] and close['ended_ns']<=timing['result_closed_ns'])
    rawstdout=raw(c/'stdout.raw.bin'); rawlines=rawstdout.splitlines(keepends=True)
    rawrows=[json.loads(l) for l in rawlines if l.strip()]
    wrapped=[json.loads(l) for l in raw(c/'events.jsonl').splitlines() if l.strip()]
    eq(prefix+'stdout_byte_count',len(rawstdout),consumer['stdout_raw_bytes'])
    eq(prefix+'stdout_sha',hashlib.sha256(rawstdout).hexdigest(),consumer['stdout_raw_sha256'])
    usage=[e['usage'] for e in rawrows if e.get('type')=='turn.completed']
    eq(prefix+'usage_raw',usage,consumer['raw_usage_events']);eq(prefix+'usage_outer',usage,route['raw_usage_events'])
    eq(prefix+'single_completed',len(usage),1)
    eq(prefix+'fresh_start',sum(e.get('type')=='thread.started' for e in rawrows),1)
    eq(prefix+'one_user_turn',sum(e.get('type')=='turn.started' for e in rawrows),1)
    tid=next(e['thread_id'] for e in rawrows if e.get('type')=='thread.started')
    eq(prefix+'thread_binding',tid,route['observed_thread_id'])
    completed=[(e,l) for e,l in zip(rawrows,rawlines) if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
    eq(prefix+'tool_count',len(completed),len(tools['tools']));eq(prefix+'tool_count_metrics',len(completed),metrics['tool_attempts'])
    eq(prefix+'tool_count_outer',len(completed),route['actual_tool_calls']);ck(prefix+'tool_budget',len(completed)<=12)
    images=dict(image_blocks=0,PNG_bytes=0,base64_chars=0,image_block_JSON_bytes=0,text_UTF8_bytes=0)
    image_event_bytes=0
    for i,((event,line),tool) in enumerate(zip(completed,tools['tools']),1):
        response=doc(o/('tool_'+str(i).zfill(2))/'RESPONSE.json')
        request=doc(o/('tool_'+str(i).zfill(2))/'REQUEST.json')
        item=event['item'];content=item['result']['content']
        eq(prefix+f'tool{i}_content',content,response['result']['content'])
        eq(prefix+f'tool{i}_name',item['tool'],request['params']['name'])
        eq(prefix+f'tool{i}_arguments',item['arguments'],request['params']['arguments'])
        im=image_metrics(content)
        for k,v in im.items():images[k]+=v
        if im['image_blocks']:image_event_bytes+=len(line)
        interval(prefix+f'tool{i}_interval',tool,'started_ns','closed_ns')
        ck(prefix+f'tool{i}_window',consumer['prompt_submitted_ns']<=tool['started_ns']<=tool['closed_ns']<=consumer['final_received_ns'])
        eq(prefix+f'tool{i}_response_bytes',len(enc(response)),tool['response_bytes'])
    eq(prefix+'CLI_images',images['image_blocks'],consumer['public_image_count'])
    eq(prefix+'CLI_png_bytes',images['PNG_bytes'],consumer['public_image_bytes'])
    unique_event_sizes={x['tool_item_id']:x['CLI_completed_event_JSON_line_bytes'] for x in consumer['image_deliveries']}
    eq(prefix+'unique_image_event_bytes',image_event_bytes,sum(unique_event_sizes.values()))
    eq(prefix+'constructed_blocks',len(construct['constructed']),metrics['constructed_image_blocks'])
    for label,field in [('PNG','PNG_bytes_read'),('base64','base64_chars'),('JSON','image_block_JSON_bytes')]:
        key={'PNG':'constructed_PNG_bytes','base64':'constructed_base64_chars','JSON':'constructed_image_block_JSON_bytes'}[label]
        eq(prefix+'constructed_'+label,sum(x[field] for x in construct['constructed']),metrics[key])
    for i,receipt in enumerate(construct['constructed']):
        ck(prefix+f'construction{i}_monotonic',receipt['constructed'])
        for name,st in receipt['stages'].items():interval(prefix+f'construction{i}_{name}',st,'started_ns','closed_ns')
    wire={name:sum(len(raw(p)) for p in c.glob('attachments/**/'+name+'.bin')) for name in ('TX','RX')}
    for direction in wire:eq(prefix+'stdio_'+direction,wire[direction],consumer['MCP_stdio_'+direction+'_bytes'])
    tcp={direction:sum(len(raw(p)) for p in o.glob('rpc_*/TCP_'+direction+'.bin')) for direction in ('TX','RX')}
    eq(prefix+'TCP_request_bytes',tcp['TX'],sum(t['request_bytes'] for t in transport))
    eq(prefix+'TCP_response_bytes',tcp['RX'],sum(t['outer_TCP_JSON_bytes'] for t in transport))
    eq(prefix+'stdio_response_bytes',wire['RX'],sum(t['MCP_JSON_bytes'] for t in transport))
    eq(prefix+'sent_image_blocks',sum(t['content_metrics']['image_blocks'] for t in transport if t['send_confirmed']),metrics['server_socket_sent_image_blocks'])
    eq(prefix+'sent_PNG_bytes',sum(t['content_metrics']['PNG_bytes'] for t in transport if t['send_confirmed']),metrics['server_socket_sent_PNG_bytes'])
    png_bytes=npz_bytes=array_bytes=0
    for frame in obs['frames']:
        stem=prefix+frame['view_name']
        png=raw(frame['PNG']);npz=raw(frame['NPZ'])
        eq(stem+'/PNG_bytes',len(png),frame['PNG_bytes']);eq(stem+'/PNG_sha',hashlib.sha256(png).hexdigest(),frame['PNG_sha256'])
        eq(stem+'/NPZ_bytes',len(npz),frame['NPZ_bytes']);eq(stem+'/NPZ_sha',hashlib.sha256(npz).hexdigest(),frame['NPZ_sha256'])
        with np.load(frame['NPZ'],allow_pickle=False) as arrays:
            payload=0
            for name,record in frame['arrays'].items():
                arr=arrays[name];payload+=arr.nbytes
                eq(stem+'/'+name+'_nbytes',arr.nbytes,record['nbytes'])
                eq(stem+'/'+name+'_hash',hashlib.sha256(arr.tobytes()).hexdigest(),record['sha256'])
        eq(stem+'/array_payload',payload,frame['array_payload_bytes'])
        ck(stem+'/render_inside_window',timing['started_ns']<=frame['intent_ns']<=frame['render_started_ns']<=frame['render_closed_ns']<=frame['completed_ns']<=timing['result_closed_ns'])
        png_bytes+=len(png);npz_bytes+=len(npz);array_bytes+=payload
    eq(prefix+'render_count',len(obs['render_attempts']),metrics['new_renders'])
    eq(prefix+'raster_count_frames',len(obs['render_attempts']),len(obs['frames']))
    ck(prefix+'render_budget',len(obs['render_attempts'])<=6)
    eq(prefix+'unique_views',len({f['view_name'] for f in obs['frames']}),len(obs['frames']))
    for field,value in [('PNG_bytes',png_bytes),('NPZ_bytes',npz_bytes),('array_payload_bytes',array_bytes)]:eq(prefix+field,metrics['common'][field],value)
    stage_totals={}
    for st in obs['stages']:
        interval(prefix+'stage:'+st['name'],st,'started_ns','closed_ns')
        ck(prefix+'stage_inside:'+st['name'],timing['started_ns']<=st['started_ns']<=st['closed_ns']<=timing['result_closed_ns'])
        stage_totals[st['name']]=stage_totals.get(st['name'],0)+st['elapsed_ns']
    tools_ns=sum(t['closed_ns']-t['started_ns'] for t in tools['tools'])
    prompt_ns=consumer['final_received_ns']-consumer['prompt_submitted_ns']
    final_times=[e['perf_ns'] for e in wrapped if e.get('event',{}).get('type')=='item.completed' and e['event'].get('item',{}).get('type')=='agent_message']
    eq(prefix+'final_received_bound',consumer['final_received_ns'],final_times[-1])
    top_errors=[e.get('message','') for e in rawrows if e.get('type')=='error']
    # No hidden reasoning text is copied to this audit artifact.
    reconnect=sum('Reconnecting' in str(e) for e in rawrows if e.get('type')=='error' or e.get('item',{}).get('type')=='error')
    ROWS[slot]=dict(group=slot[0],thread_id=tid,outer_valid=route['outer_valid_completion'],accepted_success=timing['accepted_success'],
        full_ns=timing['elapsed_ns'],start_ns=timing['started_ns'],end_ns=timing['result_closed_ns'],prompt_to_final_ns=prompt_ns,
        tools_ns=tools_ns,outside_tools_ns=prompt_ns-tools_ns,tools=len(completed),renders=len(obs['render_attempts']),
        images=images,constructed_blocks=metrics['constructed_image_blocks'],server_sent_blocks=metrics['server_socket_sent_image_blocks'],
        generated_PNG_bytes=png_bytes,NPZ_bytes=npz_bytes,array_payload_bytes=array_bytes,
        tool_response_bytes=sum(t['response_bytes'] for t in tools['tools']),stdio=wire,TCP=tcp,raw_stdout_bytes=len(rawstdout),
        unique_image_event_bytes=image_event_bytes,usage=usage[0],top_level_errors=top_errors,reconnect_events=reconnect,
        thin_exit_code=runtime['exit_code'],thin_EOF=route['bridge_cleanup']['confirmed'],stage_totals_ns=stage_totals,
        provider_internal_requests=None,fees=None,usage_semantics=consumer['usage_semantics'])

eq('six_distinct_threads',len({r['thread_id'] for r in ROWS.values()}),6)
eq('strict_pass_slots',[s for s in order if ROWS[s]['outer_valid']],['P1','P2','N2','P3'])
eq('six_slot_total_ns',sum(r['full_ns'] for r in ROWS.values()),398795123100)
eq('batch_total_ns',bt['elapsed_ns'],398802718900)
ck('no_overlapping_slots',all(ROWS[a]['end_ns']<=ROWS[b]['start_ns'] for a,b in zip(order,order[1:])))
eq('formal_renders',sum(r['renders'] for r in ROWS.values()),24)
eq('formal_tools',sum(r['tools'] for r in ROWS.values()),15)
eq('formal_constructed',sum(r['constructed_blocks'] for r in ROWS.values()),6)
eq('formal_received_blocks',sum(r['images']['image_blocks'] for r in ROWS.values()),6)
eq('formal_received_PNG',sum(r['images']['PNG_bytes'] for r in ROWS.values()),20850)
eq('formal_received_base64',sum(r['images']['base64_chars'] for r in ROWS.values()),27804)
prep=doc(BASE/'PREPARATION.json');ledger=doc(BASE/'local_ledger/a01/RESULTS.json')
prep_constructed=0;prep_renders=0;prep_sent=0
for phase in ('local/render_N','local/render_P','local_ledger/a01/normal','local_ledger/a01/post_encode_deadline','local_ledger/a01/post_construct_serialization','local_ledger/a01/post_construct_send'):
    # Ledger cases have direct actor files; render smoke files live below o/.
    folder=BASE/phase
    if (folder/'o/METRICS.json').exists():folder=folder/'o'
    metrics=doc(folder/'METRICS.json');con=doc(folder/'IMAGE_CONSTRUCTIONS.json')
    eq(phase+'/actual_constructed',len(con['constructed']),metrics['constructed_image_blocks'])
    prep_constructed+=len(con['constructed']);prep_renders+=metrics['new_renders'];prep_sent+=metrics['server_socket_sent_image_blocks']
eq('preparation_constructed',prep_constructed,prep['actual_constructed_image_blocks'])
eq('preparation_renders',prep_renders,prep['actual_new_rasters'])
eq('preparation_sent',prep_sent,0)
ck('all_render_cap',prep_renders+sum(r['renders'] for r in ROWS.values())<=42)
began=doc(BASE/'admin/PREPARATION_BEGAN.json')['observed_perf_counter_ns']
formal=doc(BASE/'FORMAL_STARTED.json')['started_ns']
prep_checkpoint=prep['prepared_ns']-began
prep_to_formal=formal-began
groups={}
for arm in ('N','P'):
    selected=[v for v in ROWS.values() if v['group']==arm]
    groups[arm]=dict(full_ns=sum(v['full_ns'] for v in selected),tools=sum(v['tools'] for v in selected),renders=sum(v['renders'] for v in selected),
        usage_field_sums={key:sum(v['usage'].get(key,0) for v in selected) for key in selected[0]['usage']},
        recorded_input_plus_output=sum(v['usage']['input_tokens']+v['usage']['output_tokens'] for v in selected))
ratio=Fraction(ROWS['P2']['full_ns'],ROWS['N2']['full_ns'])
decision=dict(scope='Existing recorded costs only. No author validator/runtime imported; no new CLI, model, renderer or Blender execution.',
    author_commit='52d9a838fd52074f3df157aba97e29a5c0cde924',checks=len(CHECKS),passed=sum(c['passed'] for c in CHECKS),failed=[c for c in CHECKS if not c['passed']],
    routes=ROWS,groups=groups,formal_status=dict(completed=4,failed=2,not_run=0),formal_3pair_benefit_qualified=False,
    complete_single_pair=dict(pair=2,P_over_N_exact=[ratio.numerator,ratio.denominator],P_over_N=float(ratio),scope='One qualified pair descriptive ratio only; no general or3pair claim'),
    preparation=dict(new_rasters=prep_renders,constructed_blocks=prep_constructed,server_sent=prep_sent,marker_to_checkpoint_ns=prep_checkpoint,marker_to_formal_ns=prep_to_formal),
    recorded_batch_ns=bt['elapsed_ns'],slot_sum_ns=sum(r['full_ns'] for r in ROWS.values()),
    raw_total_usage_scope='CLI reported final fields; N3 interrupted-stream earlier usage coverage and provider internal requests remain unknown.',
    unmeasured=['cash fees','image tokens','provider internal requests','resolved model/effort','N3 pre-reconnect usage coverage','controller initial bootstrap and initial freeze checks','work before preparation marker','peak RSS/heap'],
    new_model_render_Blender_provider_runs=0)
OUT.mkdir(parents=True,exist_ok=True)
for name,value in [('INPUTS.json',INPUTS),('CHECKS.json',CHECKS),('RESULTS.json',decision)]:
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:decision[k] for k in ('checks','passed','failed','groups','complete_single_pair','preparation','recorded_batch_ns')},ensure_ascii=False))
