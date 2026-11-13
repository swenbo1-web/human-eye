"""Independent offline cost accounting. No author modules or experiment execution."""
import base64
import hashlib
import json
from pathlib import Path

BASE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_image_consumption_001')
OUT=Path(__file__).resolve().parent
CHECKS=[]
INPUTS={}

def raw(p):
    p=Path(p); b=p.read_bytes()
    INPUTS[str(p)]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    return b
def doc(p): return json.loads(raw(p))
def packed(v): return json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
def check(label,ok,detail=None): CHECKS.append({'name':label,'passed':bool(ok),'detail':detail})
def eq(label,a,b): check(label,a==b, None if a==b else {'actual':a,'expected':b})
def content_cost(content):
    result=dict(image_blocks=0,PNG_bytes=0,base64_chars=0,image_block_JSON_bytes=0,text_UTF8_bytes=0,PNG_sha256=[])
    for item in content:
        if item['type']=='image':
            data=base64.b64decode(item['data'],validate=True)
            result['image_blocks']+=1; result['PNG_bytes']+=len(data);result['base64_chars']+=len(item['data'])
            result['image_block_JSON_bytes']+=len(packed(item));result['PNG_sha256'].append(hashlib.sha256(data).hexdigest())
        elif item['type']=='text':result['text_UTF8_bytes']+=len(item['text'].encode('utf8'))
    return result
def added(rows,keys):return {k:sum(row[k] for row in rows) for k in keys}

source={ref:raw(BASE/'inputs'/(ref+'.png'))for ref in ('view-a','view-b')}
digests=[hashlib.sha256(source[ref]).hexdigest()for ref in source]
plan=doc(BASE/'PLAN.json')
eq('registered_order',plan['sequence'],['N','P'])
eq('registered_deadline',plan['route_deadline_seconds'],450)
routes={}

for phase,folder,kind in [('local',BASE/'local/a01','synthetic_local_process'),('real',BASE/'r','provider')]:
    run=doc(folder/'RUN_RESULT.json')
    eq(phase+'/two_route_records',len(run['records']),2)
    for arm in ('N','P'):
        d=folder/arm;tag=phase+'/'+arm
        result=doc(d/'RESULT.json'); timing=doc(d/'FINAL_TIMING.json'); consumer=doc(d/'c/CONSUMER.json')
        ctime=doc(d/'c/FINAL_TIMING.json'); metrics=doc(d/'o/METRICS.json'); constructions=doc(d/'o/IMAGE_CONSTRUCTIONS.json')
        transports=doc(d/'o/TRANSPORT.json'); ownerclose=doc(d/'o/CLOSE.json')
        eq(tag+'/execution_kind',result['execution_kind'],kind)
        eq(tag+'/raw_result_equals_batch',result,next(r for r in run['records']if r['group']==arm))
        eq(tag+'/full_time',timing['elapsed_ns'],timing['result_closed_ns']-timing['started_ns'])
        eq(tag+'/original_deadline',timing['original_deadline_ns']-timing['started_ns'],450_000_000_000)
        eq(tag+'/same_start',timing['started_ns'],result['started_ns'])
        eq(tag+'/same_deadline',consumer['deadline_ns'],timing['original_deadline_ns'])
        eq(tag+'/same_episode_deadline',consumer['episode_deadline_ns'],timing['original_deadline_ns'])
        eq(tag+'/consumer_wall',ctime['full_turn_wall_ns'],ctime['consumer_record_closed_ns']-ctime['started_ns'])
        check(tag+'/full_order',timing['started_ns']<=ctime['started_ns']<=consumer['popen_ns']<=consumer['prompt_submitted_ns']<=consumer['final_received_ns']<=consumer['turn_completed_ns']<=consumer['process_exit_ns']<=ctime['consumer_record_closed_ns']<=timing['result_closed_ns']<timing['original_deadline_ns'])
        eq(tag+'/prompt_to_final',consumer['prompt_to_final_ns'],consumer['final_received_ns']-consumer['prompt_submitted_ns'])
        eq(tag+'/one_fresh_user_turn',consumer['turn_index'],1)
        eq(tag+'/no_expected_resume',consumer['expected_thread_id'],None)
        eq(tag+'/no_resume_argv','resume' in consumer['argv'],False)
        eq(tag+'/initial_images_zero',consumer['initial_image']['count'],0)
        for field in ('new_renders','Blender_processes','paid_API_calls'):eq(tag+'/'+field,result[field],0)
        eq(tag+'/source_construct_count',len(constructions['constructed']),2)
        eq(tag+'/failed_constructions',constructions['failed'],[])
        stage_sums={k:0 for k in ('read','validate_decode','encode')}
        for i,c in enumerate(constructions['constructed']):
            eq(tag+f'/construction{i}_bytes',c['PNG_bytes_read'],len(source[c['ref']]))
            eq(tag+f'/construction{i}_sha',c['PNG_sha256'],hashlib.sha256(source[c['ref']]).hexdigest())
            eq(tag+f'/construction{i}_b64',c['base64_chars'],len(base64.b64encode(source[c['ref']])))
            eq(tag+f'/construction{i}_time',c['elapsed_ns'],c['closed_ns']-c['started_ns'])
            check(tag+f'/construction{i}_inside_route',timing['started_ns']<=c['started_ns']<=c['closed_ns']<=timing['result_closed_ns'])
            for stage,s in c['stages'].items():
                eq(tag+f'/construction{i}_{stage}_time',s['elapsed_ns'],s['closed_ns']-s['started_ns'])
                check(tag+f'/construction{i}_{stage}_inside',c['started_ns']<=s['started_ns']<=s['closed_ns']<=c['closed_ns'])
                stage_sums[stage]+=s['elapsed_ns']
        events=[];event_disk_bytes=0
        for line in raw(d/'c/events.jsonl').splitlines(keepends=True):
            record=json.loads(line);events.append(record)
            check(tag+'/event_inside_full_window',timing['started_ns']<=record['perf_ns']<=timing['result_closed_ns'])
            if record['event'].get('item',{}).get('type')=='mcp_tool_call' and record['event']['type']=='item.completed':event_disk_bytes+=len(line)
        tool_events=[r for r in events if r['event']['type']=='item.completed'and r['event'].get('item',{}).get('type')=='mcp_tool_call']
        userturns=[r for r in events if r['event']['type']=='turn.started']
        completed=[r for r in events if r['event']['type']=='turn.completed']
        threads=[r['event']['thread_id']for r in events if r['event']['type']=='thread.started']
        warnings=[r['event']['item']['message']for r in events if r['event'].get('item',{}).get('type')=='error']
        eq(tag+'/single_turn',len(userturns),1);eq(tag+'/one_completed',len(completed),1)
        eq(tag+'/one_thread',threads,[consumer['thread_id']])
        eq(tag+'/usage_raw',completed[0]['event']['usage'],consumer['usage'])
        eq(tag+'/usage_not_aggregated',consumer['usage_aggregation'],None)
        eq(tag+'/usage_rows',consumer['raw_usage_events'],[completed[0]['event']['usage']])
        eq(tag+'/tool_events',len(tool_events),result['actual_tool_calls'])
        eq(tag+'/tool_metadata',len(tool_events),metrics['tool_attempts'])
        check(tag+'/max_four_tools',len(tool_events)<=4)
        all_content=[];tool_response_bytes=0;unique_event_bytes=0
        for index,event in enumerate(tool_events,1):
            item=event['event']['item'];tool=d/'o'/f'tool_{index:02d}'
            receipt=doc(tool/'RECEIPT.json');response=doc(tool/'RESPONSE.json');request=doc(tool/'REQUEST.json')
            eq(tag+f'/tool{index}_elapsed',receipt['elapsed_ns'],receipt['closed_ns']-receipt['started_ns'])
            eq(tag+f'/tool{index}_bytes',receipt['response_bytes'],len(packed(response)))
            content=item['result']['content']; all_content.extend(content)
            eq(tag+f'/tool{index}_content_cost',content_cost(content),receipt['content_metrics'])
            eq(tag+f'/tool{index}_source_content',content,response['result']['content'])
            eq(tag+f'/tool{index}_name',item['tool'],receipt['name'])
            if phase=='real': check(tag+f'/tool{index}_no_pixel_compute',item['tool']!='execute_python')
            tool_response_bytes+=len(packed(response))
            image_rows=[r for r in consumer['image_deliveries']if r['tool_item_id']==item['id']]
            if any(block['type']=='image' for block in content):
                eq(tag+f'/tool{index}_unique_byte_counter',len({r['CLI_completed_event_JSON_line_bytes']for r in image_rows}),1)
                measured=image_rows[0]['CLI_completed_event_JSON_line_bytes']
                eq(tag+f'/tool{index}_raw_len_matches_canonical_event',measured,len(packed(event['event']))+1)
                unique_event_bytes+=measured
            else: eq(tag+f'/tool{index}_nonimage_rows',image_rows,[])
        public=content_cost(all_content)
        eq(tag+'/image_count',public['image_blocks'],consumer['public_image_count'])
        eq(tag+'/image_bytes',public['PNG_bytes'],consumer['public_image_bytes'])
        eq(tag+'/correct_order_payloads',public['PNG_sha256'],digests)
        eq(tag+'/two_images',public['image_blocks'],2)
        eq(tag+'/no_construct_refund',metrics['constructed_image_blocks'],len(constructions['constructed']))
        for key in ('image_blocks','PNG_bytes','base64_chars','image_block_JSON_bytes','text_UTF8_bytes'):
            eq(tag+'/socket_'+key,metrics['server_socket_sent_'+key],public[key])
        for key in ('PNG_bytes','base64_chars','image_block_JSON_bytes'):
            eq(tag+'/constructed_'+key,metrics['constructed_'+key],public[key])
        wires={name:sum(len(raw(p))for p in (d/'c/attachments').glob('**/'+name+'.bin'))for name in ('TX','RX')}
        eq(tag+'/stdio_TX',wires['TX'],consumer['MCP_stdio_TX_bytes'])
        eq(tag+'/stdio_RX',wires['RX'],consumer['MCP_stdio_RX_bytes'])
        eq(tag+'/server_MCP_to_stdio_RX',wires['RX'],metrics['server_socket_sent_MCP_JSON_bytes'])
        tcp_tx=tcp_rx=0
        for row in transports:
            rpc=d/'o'/f"rpc_{row['sequence']:03d}"
            tx=raw(rpc/'TCP_TX.bin');rx=raw(rpc/'TCP_RX.bin')
            tcp_tx+=len(tx);tcp_rx+=len(rx)
            body=json.loads(rx)['result']
            eq(tag+f"/rpc{row['sequence']}_tx_bytes",len(tx),row['request_bytes'])
            eq(tag+f"/rpc{row['sequence']}_rx_bytes",len(rx),row['outer_TCP_JSON_bytes'])
            eq(tag+f"/rpc{row['sequence']}_MCP_bytes",len(packed(body)),row['MCP_JSON_bytes'])
            eq(tag+f"/rpc{row['sequence']}_content_cost",content_cost(body.get('result',{}).get('content',[])),row['content_metrics'])
            check(tag+f"/rpc{row['sequence']}_clock",timing['started_ns']<=row['started_ns']<=row['closed_ns']<=timing['result_closed_ns'])
        eq(tag+'/TCP_TX',tcp_tx,metrics['server_socket_request_bytes'])
        eq(tag+'/TCP_RX',tcp_rx,metrics['server_socket_sent_outer_TCP_JSON_bytes'])
        eq(tag+'/owner_closed_metrics',ownerclose['metrics'],metrics)
        if phase=='real':
            eq(tag+'/two_warnings',len(warnings),2)
            check(tag+'/metadata_warning_retained',any('fallback metadata'in w for w in warnings))
            eq(tag+'/thin_exit_unknown',result['bridge_cleanup']['confirmed'],None)
            for field in ('provider_requests','fees','image_tokens','resolved_effort'):eq(tag+'/unknown_'+field,consumer[field],None)
        routes[tag]=dict(arm=arm,phase=phase,execution_kind=kind,thread_id=consumer['thread_id'],user_turns=len(userturns),tools=len(tool_events),
            image=public,constructed=len(constructions['constructed']),server_sent=metrics['server_socket_sent_image_blocks'],
            full_elapsed_ns=timing['elapsed_ns'],full_start_ns=timing['started_ns'],full_end_ns=timing['result_closed_ns'],
            consumer_full_ns=ctime['full_turn_wall_ns'],prompt_to_final_ns=consumer['final_received_ns']-consumer['prompt_submitted_ns'],
            read_validate_encode_ns=stage_sums,stdio_TX=wires['TX'],stdio_RX=wires['RX'],TCP_TX=tcp_tx,TCP_RX=tcp_rx,
            unique_image_CLI_event_bytes=unique_event_bytes,stored_wrapped_event_line_bytes=event_disk_bytes,
            source_tool_response_bytes=tool_response_bytes,usage=completed[0]['event']['usage'],warnings=warnings)

helper=doc(BASE/'LOCAL_HELPER_CHECK.json')
eq('helper/two_constructed',len(helper['images']),2)
helper_elapsed=0
for item in helper['images']:
    eq('helper/'+item['ref']+'_bytes',item['PNG_bytes_read'],len(source[item['ref']]))
    eq('helper/'+item['ref']+'_time',item['elapsed_ns'],item['closed_ns']-item['started_ns'])
    check('helper/'+item['ref']+'_constructed',item['constructed'])
    helper_elapsed+=item['elapsed_ns']
real=[routes['real/'+arm]for arm in ('N','P')];local=[routes['local/'+arm]for arm in ('N','P')]
eq('fresh_real_threads',len(set(r['thread_id']for r in real)),2)
eq('real/tools_total',sum(r['tools']for r in real),3)
eq('real/PNG_bytes_total',sum(r['image']['PNG_bytes']for r in real),13398)
eq('real/total_time',sum(r['full_elapsed_ns']for r in real),43872732300)
eq('real/wall_span',real[-1]['full_end_ns']-real[0]['full_start_ns'],43873299400)
eq('all/construct_count',len(helper['images'])+sum(r['constructed']for r in routes.values()),10)
eq('all/server_sent_count',sum(r['server_sent']for r in routes.values()),8)
real_cost=added(real,['tools','constructed','server_sent','full_elapsed_ns','stdio_TX','stdio_RX','TCP_TX','TCP_RX','unique_image_CLI_event_bytes','stored_wrapped_event_line_bytes'])
real_cost['PNG_bytes']=sum(r['image']['PNG_bytes']for r in real)
real_cost['wall_span_ns']=real[-1]['full_end_ns']-real[0]['full_start_ns']
real_cost['between_routes_ns']=real[1]['full_start_ns']-real[0]['full_end_ns']
real_cost['raw_usage_field_sums']={k:sum(r['usage'][k]for r in real)for k in real[0]['usage']}
out=dict(author_commit='a54ad3a9bf738e8f9b5a75c71c29b0a6b105a6ff',scope='Offline source-record arithmetic; no author modules, models, CLI, actor, render, Blender, API, or process experiments.',
    checks=len(CHECKS),passed=sum(r['passed']for r in CHECKS),failed=[r for r in CHECKS if not r['passed']],
    routes=routes,real_totals=real_cost,preparation=dict(helper_constructed=2,helper_measured_construction_sum_ns=helper_elapsed,synthetic_constructed=sum(r['constructed']for r in local),synthetic_server_sent=sum(r['server_sent']for r in local),synthetic_full_route_sum_ns=sum(r['full_elapsed_ns']for r in local)),
    total_constructed=10,total_server_sent=8,new_image_generation=0,unmeasured=['provider internal request count/raw request/resolved model/effort','image tokens and cash charges','preparation coding/review/full setup wall time','normal stdio EOF/exit receipts in actual CLI sessions'],
    interpretation='Two one-shot transport qualifications, not an engine-benefit or matched performance A/B. N and P differ in tool granularity. CLI event byte fields are original runtime len(raw) counters consistent with canonical event re-encoding; stored timestamp-wrapped log bytes are reported separately.')
OUT.mkdir(parents=True,exist_ok=True)
for name,value in [('RESULTS.json',out),('CHECKS.json',CHECKS),('INPUTS.json',INPUTS)]:
    with (OUT/name).open('x',encoding='utf8',newline='\n')as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({k:out[k]for k in ('checks','passed','failed','real_totals','preparation')},ensure_ascii=False))
