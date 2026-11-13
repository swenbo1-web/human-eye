"""Resolve the original offline audit's explicit format assumptions; retain originals."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_image_consumption_001')
initial=json.loads((HERE/'RESULTS.json').read_bytes())
def doc(p):return json.loads(Path(p).read_bytes())
def compact(v):return json.dumps(v,ensure_ascii=False,separators=(',',':')).encode('utf8')
corrections=[]
inputs={}
for name in ('actor.py','driver.py','fake_cli.py','consumer.py'):
    b=(BASE/name).read_bytes();inputs[name]=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
for failed in initial['failed']:
    name=failed['name']; phase,arm,kind=name.split('/',2)
    folder=(BASE/'r')if phase=='real'else(BASE/'local/a01')
    d=folder/arm;reason=None;passed=False;detail={}
    if kind=='raw_result_equals_batch':
        route=doc(d/'RESULT.json');batch=next(r for r in doc(folder/'RUN_RESULT.json')['records']if r['group']==arm)
        extra=set(batch)-set(route)
        passed=extra=={'execution_state','final_timing'} and all(batch[k]==v for k,v in route.items()) and batch['final_timing']==doc(d/'FINAL_TIMING.json') and batch['execution_state']=='completed'
        reason='driver appends final_timing and execution_state only after writing each route RESULT; shared fields are exact.'
        detail={'extra_fields':sorted(extra)}
    elif kind=='single_turn' and phase=='local':
        events=[r['event']for r in map(json.loads,(d/'c/events.jsonl').read_bytes().splitlines())]
        started=sum(e['type']=='turn.started'for e in events);completed=sum(e['type']=='turn.completed'for e in events)
        passed=started==0 and completed==1 and 'turn.started'not in(BASE/'fake_cli.py').read_text('utf8')
        reason='Synthetic fixture emits thread.started and turn.completed, not a genuine model turn.started. Real user-turn counts remain separate.'
        detail={'synthetic_turn_started':started,'synthetic_turn_completed':completed}
    elif kind.endswith('_bytes') and kind.startswith('tool'):
        number=int(kind.split('_')[0][4:]);tool=d/'o'/f'tool_{number:02d}'
        response=doc(tool/'RESPONSE.json');receipt=doc(tool/'RECEIPT.json')
        wire=[p.read_bytes()for p in(d/'c/attachments').glob('**/RX.bin')if doc(p).get('id')==response['id']]
        passed=len(wire)==1 and wire[0]==compact(response)+b'\n' and receipt['response_bytes']==len(wire[0])
        reason='MCP line byte counters include their terminating LF; original audit used JSON payload alone.'
        detail={'actual_wire_bytes':len(wire[0]),'counter':receipt['response_bytes']}
    elif kind.endswith('_MCP_bytes') and kind.startswith('rpc'):
        number=int(kind.split('_')[0][3:]);body=doc(d/'o'/f'rpc_{number:03d}'/'TCP_RX.bin')['result']
        row=next(r for r in doc(d/'o/TRANSPORT.json')if r['sequence']==number)
        wire=[p.read_bytes()for p in(d/'c/attachments').glob('**/RX.bin')if doc(p).get('id')==body['id']]
        passed=len(wire)==1 and wire[0]==compact(body)+b'\n' and row['MCP_JSON_bytes']==len(wire[0])
        reason='The inner MCP response is newline-delimited; TCP wrapper and standalone image-block JSON are different scopes.'
        detail={'actual_wire_bytes':len(wire[0]),'counter':row['MCP_JSON_bytes']}
    elif kind.endswith('_raw_len_matches_canonical_event') and phase=='local':
        number=int(kind.split('_')[0][4:]);events=[r['event']for r in map(json.loads,(d/'c/events.jsonl').read_bytes().splitlines())]
        tools=[e for e in events if e['type']=='item.completed'and e.get('item',{}).get('type')=='mcp_tool_call'];event=tools[number-1]
        rows=[r for r in doc(d/'c/CONSUMER.json')['image_deliveries']if r['tool_item_id']==event['item']['id']]
        actual=len(json.dumps(event,ensure_ascii=False).encode('utf8'))+1
        passed=bool(rows)and all(r['CLI_completed_event_JSON_line_bytes']==actual for r in rows)
        reason='fake_cli uses default spaced json.dumps, while the actual CLI emits compact JSON; no performance population is changed.'
        detail={'default_json_plus_LF':actual,'counter':rows[0]['CLI_completed_event_JSON_line_bytes']}
    corrections.append(dict(original_check=name,passed=passed,reason=reason,detail=detail))
assert len(corrections)==33
out=dict(scope='Format-only corrective audit of all33 retained original expectation failures; no experiment execution or author mutation.',
    corrections=corrections,passed=sum(r['passed']for r in corrections),failed=[r for r in corrections if not r['passed']],source_inputs=inputs)
final=dict(author_commit=initial['author_commit'],verdict='pass'if not out['failed']else'fail',
    original_valid_checks=initial['passed'],original_invalid_expectations=len(initial['failed']),corrected_checks=out['passed'],
    unresolved_cost_discrepancies=out['failed'],real_totals=initial['real_totals'],preparation=initial['preparation'],
    total_constructed=initial['total_constructed'],total_server_sent=initial['total_server_sent'],
    routes=initial['routes'],unmeasured=initial['unmeasured'],notes=[
      'Original RESULTS and CHECKS retain all failures; clarification changes only incorrect audit expectations.',
      'Route source_tool_response_bytes in original RESULTS excludes LF; actual MCP tool-response byte sums below are authoritative.',
      'Stored timestamp-wrapped events.jsonl byte length is separate from measured CLI raw-line len counters; canonical JSON checks corroborate counters but raw stdout is not fully retained.',
      'N and P are one-shot transport qualifications with differing tool granularity, not a controlled performance comparison.'])
for phase,folder in [('real',BASE/'r'),('local',BASE/'local/a01')]:
    for arm in ('N','P'):
        final['routes'][phase+'/'+arm]['actual_tool_MCP_line_bytes']=sum(doc(p)['response_bytes']for p in(folder/arm/'o').glob('tool_*/RECEIPT.json'))
for name,value in [('SCHEMA_CLARIFICATION.json',out),('FINAL_RESULTS.json',final)]:
    with(HERE/name).open('x',encoding='utf8',newline='\n')as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps(dict(verdict=final['verdict'],corrected=out['passed'],failed=out['failed'],real_totals=final['real_totals']),ensure_ascii=False))
