"""Narrow offline follow-up: original LF-bound redaction and captured wire totals.

Uses saved R1 hashes, never imports or reruns the product, launcher, or scorer.
"""
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
RUNTIME=Path('D:/he_complete_witness_001')
PRODUCER=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_001/consumer.py')
rows=[];inputs=[]
def read(p):
    data=Path(p).read_bytes()
    inputs.append({'path':str(p),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    return data
def load(p):return json.loads(read(p))
def check(name,value):rows.append({'name':name,'passed':bool(value)})
def encoded(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')+b'\n'

r1=load(OUT/'RESULT_R1.json')
check('R1_only_failed_unterminated_line_assumption',r1['failures']==[{'group':'consumer','name':'raw_event:9'}])
producer=read(PRODUCER).decode('utf-8')
check('declared_line_includes_terminator',"for raw in iter(stream.readline,b''):" in producer and "'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw)" in producer)
rawlines=[line for line in read(RUNTIME/'formal/P1/c/stdout.raw.bin').splitlines(keepends=True) if line.strip()]
events=[json.loads(line)['event'] for line in read(RUNTIME/'formal/P1/c/events.jsonl').splitlines() if line.strip()]
check('raw_line_and_event_count',len(rawlines)==len(events)==14)
redacted_metadata=[]
for i,(line,public) in enumerate(zip(rawlines,events)):
    raw=json.loads(line)
    if raw.get('item',{}).get('type')=='reasoning':
        value=(public.get('raw_sha256')==hashlib.sha256(line).hexdigest() and public.get('raw_bytes')==len(line) and public.get('item',{}).get('redacted') is True)
        redacted_metadata.append({'index':i,'original_line_bytes_with_LF':len(line),'sha256':hashlib.sha256(line).hexdigest(),'line_ending_hex':line[-1:].hex(),'r1_line_bytes_without_LF':len(line.rstrip(b'\n'))})
    else:value=public==raw
    check('exact_original_event:'+str(i),value)

metrics=load(RUNTIME/'formal/P1/o/METRICS.json')
transport=load(RUNTIME/'formal/P1/o/TRANSPORT.json')
toolcalls=[json.loads(line)['item'] for line in rawlines if json.loads(line).get('type')=='item.completed' and json.loads(line).get('item',{}).get('type')=='mcp_tool_call']
wire=[]
for folder,tr in zip(sorted((RUNTIME/'formal/P1/o').glob('rpc_*')),transport):
    # Existing owner RPC_RX stores its emitted reply; RPC_TX stores incoming request.
    replyraw=read(folder/'TCP_RX.bin');request=read(folder/'TCP_TX.bin');reply=json.loads(replyraw)
    mcp=reply['result']
    val={'rpc':folder.name,'request_bytes':len(request),'outer_reply_bytes':len(replyraw),'MCP_JSON_bytes':len(encoded(mcp))}
    wire.append(val)
    check(folder.name+'_wire_lengths',len(request)==tr['request_bytes'] and len(replyraw)==tr['outer_TCP_JSON_bytes'] and len(encoded(mcp))==tr['MCP_JSON_bytes'])
    check(folder.name+'_successful_send',reply['ok'] is True and tr['send_confirmed'] is True and tr['send_error'] is None)
    if tr['sequence']>=3:
        check(folder.name+'_CLI_received_same_tool_result',mcp['result']==toolcalls[tr['sequence']-3]['result'])
totals={k:sum(v[k] for v in wire) for k in ('request_bytes','outer_reply_bytes','MCP_JSON_bytes')}
check('all_five_RPCs',len(wire)==len(transport)==5)
check('request_total',totals['request_bytes']==metrics['server_socket_request_bytes']==5212)
check('reply_total',totals['outer_reply_bytes']==metrics['server_socket_sent_outer_TCP_JSON_bytes']==30828)
check('MCP_total',totals['MCP_JSON_bytes']==metrics['server_socket_sent_MCP_JSON_bytes']==30483)
check('image_base64_cost',sum(len(x['data']) for t in toolcalls for x in t['result']['content'] if x['type']=='image')==6840)

failures=[x for x in rows if not x['passed']]
result={'method':'Narrow offline original-byte check; only correction is preserving original LF for the declared raw-line hash/count. No other normalization. No live calls or repeated identity matrix.',
        'R1_preserved':True,'R1_sha256':hashlib.sha256((OUT/'RESULT_R1.json').read_bytes()).hexdigest(),
        'producer':str(PRODUCER),'producer_definition_lines':[287,340,341],
        'checks':len(rows),'failures':failures,'all_passed':not failures,'new_product_model_Blender_raster_calls':0,
        'redacted_metadata':redacted_metadata,'wire':wire,'wire_totals':totals,'details':rows}
(OUT/'COST_ADDENDUM_INPUTS.json').write_text(json.dumps(inputs,indent=2)+'\n',encoding='utf-8')
(OUT/'COST_ADDENDUM_RESULT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
final={'scope':'Fixed identity/seal/cost review, excluding semantic answer scoring','new_product_model_Blender_raster_calls':0,
       'R1_checks':r1['checks'],'R1_passed':r1['checks']-len(r1['failures']),'R1_failures_preserved':r1['failures'],
       'resolved_review_script_failure':'raw_event:9 excluded LF despite producer hashing the original readline bytes; exact original LF-byte comparison now passes' if not failures else None,
       'narrow_addendum_checks':len(rows),'narrow_addendum_failures':failures,'summary':r1['summary'],
       'wire_totals':totals,'unresolved_findings':[] if not failures else failures,
       'identity_and_cost_passed':not failures}
(OUT/'FINAL_RESULT.json').write_text(json.dumps(final,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'checks':len(rows),'failures':failures,'wire_totals':totals,'redacted_metadata':redacted_metadata}))
raise SystemExit(bool(failures))
