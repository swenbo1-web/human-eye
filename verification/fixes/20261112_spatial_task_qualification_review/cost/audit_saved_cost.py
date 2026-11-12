"""Independent frozen-data audit; never imports authors' scripts or runs product/Blender."""
from pathlib import Path
import ast
import base64
import hashlib
import json
import subprocess
import zlib

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT = Path(__file__).resolve().parent
COMMIT = '93121974595badc90944d5353d23ae7897feda54'
P = 'verification/spatial_task_qualification_001/'
R = P + 'entry/run_01/'
EXTRA = [
 'verification/m2_tight_directory_001/measurement/owned_native.py',
 'verification/m2_tight_directory_001/measurement/wire_meter.py',
 'verification/m1_task_entry_001_eval/actor.py',
 'verification/m1_task_entry_001_eval/preflight_client.py',
 'verification/native_plugin_complex_003/actor.py',
]
checks = []
sources = []
def check(condition, name):
    checks.append({'check': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def cmd(*args, data=None):
    return subprocess.run(['git', '-C', str(ROOT), *args], input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True).stdout

# Read the chosen immutable Git objects, then compare every used checkout byte to them.
paths = cmd('ls-tree', '-r', '--name-only', COMMIT, '--', P).decode().splitlines() + EXTRA
batch = cmd('cat-file', '--batch', data=''.join(COMMIT+':'+p+'\n' for p in paths).encode())
fixed = {}
at = 0
for path in paths:
    end = batch.index(b'\n', at)
    header = batch[at:end].decode().split()
    check(len(header) == 3 and header[1] == 'blob', 'Git blob '+path)
    size = int(header[2]); raw = batch[end+1:end+1+size]; at = end+2+size
    check(raw == (ROOT/path).read_bytes(), 'checkout equals fixed Git '+path)
    fixed[path] = raw
    sources.append({'path':path,'git_blob':header[0],'bytes':size,'sha256':sha(raw)})
check(at == len(batch), 'all Git batch bytes consumed')
def raw(path): return fixed[path]
def load(path): return json.loads(raw(path))
def lines(path): return [json.loads(line) for line in raw(path).splitlines() if line]
def compact(value): return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()

index = load(P+'INDEX.json'); complete = load(P+'COMPLETE.json')
check(len(index['files']) == index['file_count'] == complete['indexed_files'] == 123, '123 indexed evidence files')
for item in index['files']:
    check(len(raw(item['path'])) == item['bytes'] and sha(raw(item['path'])) == item['sha256'], 'index hash '+item['path'])
check(sha(raw(P+'INDEX.json')) == complete['INDEX_sha256'], 'COMPLETE index digest')
result = load(R+'RESULTS.json')
check(sha(raw(R+'RESULTS.json')) == complete['formal_result_sha256'], 'COMPLETE formal result digest')
check(sha(raw(P+'REPORT.md')) == complete['report_sha256'], 'COMPLETE report digest')
check(sha(raw(P+'oracle/formal_replay_01/ORACLE.json')) == complete['formal_oracle_sha256'], 'COMPLETE oracle digest')

events = lines(R+'native/WORKER_EVENTS.jsonl')
wire_index = load(R+'native/WIRE/INDEX.json')
check(len(events) == len(wire_index) == 5, '5 actual host RPC records')
check([e['sequence'] for e in events] == list(range(1,6)), 'worker event sequence 1..5')
business = result['business']; rules = load(P+'entry/QUERY_RULES.json')
check([b['request']['id'] for b in business] == rules['sequence'] == ['directory','assembly_task','control_task'], 'exact three business sequence')
windows = [('QA_snapshot',result['QA_snapshot'])] + [(b['request']['id'],b) for b in business]
host = []
for n, item in enumerate(wire_index,1):
    prefix = R+f'native/WIRE/{n:03d}/'
    tx = raw(prefix+'REQUEST.bin'); rx = raw(prefix+'RESPONSE.bin')
    req = json.loads(tx); res = json.loads(rx); event = events[n-1]
    check(item['sequence'] == n and item['request_bytes'] == len(tx)
          and item['response_attempted_bytes'] == len(rx)
          and item['request_response_attempted_bytes'] == len(tx)+len(rx)
          and item['response_sendall_completed'] is True, f'host raw bytes / send receipt {n}')
    owners = [name for name,w in windows if w['started_ns'] <= event['started_ns'] <= w['ended_ns']]
    check(len(owners) == (0 if n == 5 else 1), f'host window attribution {n}')
    check(req['type'] == ('close' if n == 5 else 'execute_code'), f'host type {n}')
    code = req.get('params',{}).get('code','')
    capsules = []
    for node in ast.walk(ast.parse(code)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'b64decode' and node.args
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value,str)):
            text = node.args[0].value
            decoded = zlib.decompress(base64.b64decode(text))
            capsules.append({'literal_UTF8_bytes':len(text.encode()),'decoded_source_bytes':len(decoded),'decoded_source_sha256':sha(decoded)})
    if n < 5:
        check(code == raw(R+f'native/call_{n}/SCRIPT.py').decode('utf8').replace('\r\n','\n'), f'host script identical after Windows archive newline normalization {n}')
        check(sha(code.encode()) == event['script_sha256'], f'host script hash {n}')
        check(event['status'] == 'completed' and event['script_error'] is None
              and event['terminal_geometry_and_file_checks_passed'] is True, f'worker execution {n}')
        check(res['status'] == 'success' and res['result']['executed'] is True, f'host response success {n}')
        check(res['result']['result'] == raw(R+f'native/call_{n}/stdout.txt').decode().replace('\r\n','\n'),f'host response bound stdout after Windows archive newline normalization {n}')
    host.append({'sequence':n,'owner':owners[0] if owners else 'close','request_type':req['type'],
                 'tx_bytes':len(tx),'rx_bytes':len(rx),'worker_elapsed_ms':event['elapsed_ns']/1e6,
                 'source_capsules':capsules,'work':event['m2_work']})
check([h['owner'] for h in host] == ['QA_snapshot','directory','assembly_task','control_task','close'], 'host attribution exact sequence')
check(len(host[1]['source_capsules']) > 0 and all(not h['source_capsules'] for h in (host[0],host[2],host[3],host[4])), 'source establishment only first directory')
host_total = {'requests':len(host),'tx_bytes':sum(h['tx_bytes'] for h in host),'rx_bytes':sum(h['rx_bytes'] for h in host)}
host_total['total_bytes'] = host_total['tx_bytes']+host_total['rx_bytes']
check(host_total == {'requests':5,'tx_bytes':94844,'rx_bytes':208362,'total_bytes':303206}, 'independent host totals')
qa = load(R+'QA_SNAPSHOT_RECEIPT.json')
check(qa['response'] == json.loads(raw(R+'native/WIRE/001/RESPONSE.bin')), 'QA receipt matches raw response')
snapshot = load(R+'ACTUAL_SNAPSHOT.json')
check(snapshot == json.loads(qa['response']['result']['result']), 'actual snapshot matches raw body')
check(len(snapshot['objects']) == 14 and sum(len(o['vertices_world']) for o in snapshot['objects']) == 848
      and sum(len(o['triangles']) for o in snapshot['objects']) == 1640, 'actual denominator 14/848/1640')

rpc = load(R+'product/RPC.json'); stdio = []; bodies = {}
check(len(rpc['requests']) == 7, 'seven actual stdio messages')
for n,receipt in enumerate(rpc['requests'],1):
    prefix=R+f'product/{n:03d}/'; tx=raw(prefix+'TX.bin')
    rx=raw(prefix+'RX.bin') if prefix+'RX.bin' in fixed else b''
    req=json.loads(tx); res=json.loads(rx) if rx else None
    check(receipt == load(prefix+'RECEIPT.json'),f'stdio record exact receipt {n}')
    check(receipt['sent_bytes'] == receipt['attempted_send_bytes'] == len(tx)
          and receipt['received_bytes'] == len(rx)
          and receipt['send_confirmed'] is True and receipt['error'] is None,f'stdio raw bytes confirmed {n}')
    check(receipt['method'] == req['method'] and receipt['request_id'] == req.get('id'),f'stdio ID/method {n}')
    if n == 2:
        check(res is None and req['method']=='notifications/initialized', 'notification is not reply')
    else:
        check(res['id']==req['id'] and 'error' not in res, f'stdio reply identity {n}')
    if n >= 5:
        b=business[n-5]; label=req['id']
        check(req == b['request'] == load(R+label+'_REQUEST.json') and res == b['response'],f'public saved raw equivalence {label}')
        check(load(R+label+'_RESULT.json')['response'] == res, f'public original row reply {label}')
        check(b['classification']=='tool_response' and res['result']['isError'] is False,f'public no transport or RPC error {label}')
        content=res['result']['content']; check(all(c['type']=='text' for c in content),'text-only '+label)
        body=json.loads(content[0]['text']); bodies[label]=body
        check(body==b['body'], 'raw public body '+label)
        visible=sum(len(c['text'].encode()) for c in content)
        check(visible==b['visible_text_UTF8_bytes'], 'visible UTF8 '+label)
        check(b['tool_ns']==b['ended_ns']-b['started_ns'], 'business elapsed '+label)
        check(b['started_ns'] <= receipt['started_ns'] <= receipt['started_ns']+receipt['elapsed_ns'] <= b['ended_ns'], 'nested stdio timing '+label)
        h=host[n-4]
        check(b['host_RPC']==1 and b['bridge_request_bytes']==h['tx_bytes'] and b['bridge_response_bytes']==h['rx_bytes'], 'business raw host totals '+label)
        check(req['params']['arguments']['include_image'] is False and req['params']['name']==rules['tool'], 'fixed tool and no images '+label)
    else: visible=None
    stdio.append({'sequence':n,'method':req['method'],'id':req.get('id'),'tx_bytes':len(tx),'rx_bytes':len(rx),'elapsed_ms':receipt['elapsed_ns']/1e6,'visible_text_bytes':visible})
check(sum(s['tx_bytes'] for s in stdio)==rpc['tx_bytes']==1647 and sum(s['rx_bytes'] for s in stdio)==rpc['rx_bytes']==42288,'stdio totals independently recomputed')
metadata=rpc['requests'][:4]
check(max(m['started_ns']+m['elapsed_ns'] for m in metadata)<events[0]['started_ns'], 'metadata precedes all host events')
check(len([s for s in stdio[:4] if s['rx_bytes']]) == 3,'metadata 4 messages 3 responses')
directory=bodies['directory']; assembly=bodies['assembly_task']; control=bodies['control_task']
check(directory['status']=='complete' and len(directory['objects'])==14,'directory complete 14')
names={o['name']:o['object_id'] for o in directory['objects']}
check(names==load(R+'DIRECTORY_NAME_ID_BINDING.json') and len(names)==14, 'directory names unique and bound')
for label,rule in [('assembly_task',rules['assembly']),('control_task',rules['control'])]:
    expected={'mode':'task','target':{'id':names[rule['target']]},'candidates':[{'id':names[n]} for n in rule['candidates']], 'requested_facts':rules['requested_facts']}
    row=next(b for b in business if b['request']['id']==label)
    check(row['request']['params']['arguments']['query']==expected,'fixed selectors/facts '+label)
    check(all(v['status']=='measured' for v in bodies[label]['facts']['aabb']),'aabb measurable '+label)
check(assembly['status']=='partial' and len(assembly['pairs'])==3,'assembly three pairs partial')
for p in assembly['pairs']:
    for fact,reason in [('surface_proximity','surface_geometry_work_limit'),('closed_solid_relation','closed_solid_geometry_work_limit')]:
        check(p['facts'][fact]['status']=='unknown' and p['facts'][fact]['value'] is None and p['facts'][fact]['reason']==reason, f'unknown preserved {p["candidate_index"]}/{fact}')
check(assembly['summary']['nearest_separated_complete'] is False and assembly['summary']['nearest_separated_ids'] is None
      and len(assembly['summary']['unresolved_relations'])==3 and assembly['summary']['unresolved_distances']=={}, 'whole unknown summary preserved')
check(control['status']=='observed' and len(control['pairs'])==1, 'one completed control')
facts=control['pairs'][0]['facts']
check(facts['closed_solid_relation']['status']=='measured' and facts['closed_solid_relation']['value']=='separated'
      and facts['surface_proximity']['status']=='measured' and facts['surface_proximity']['value']['distance_m']==1.0, 'control measured distance and relation')
witness=facts['surface_proximity']['value']['nearest_witness']
check(len(compact(witness))==76,'control witness compact value 76 bytes')
objects={o['name']:o for o in snapshot['objects']}
check(witness['a'] in objects['Control_A']['vertices_world'] and witness['b'] in objects['Control_B']['vertices_world'], 'public control witnesses are actual vertices')
check(sum((a-b)**2 for a,b in zip(witness['a'],witness['b']))==1.0,'public control witness squared distance 1')
audit=lines(R+'audit.jsonl')
task_work={}
for label in ('assembly_task','control_task'):
    records=[a for a in audit if a['event']=='observe' and a['trace_id']==bodies[label]['trace_id']]
    check(len(records)==1, 'one raw observe work record '+label)
    task_work[label]=records[0]['task_work']
check(task_work['assembly_task']['surface_pair_count']==task_work['assembly_task']['closed_solid_pair_count']==3,
      'assembly wrapper entries counted, not solved pairs')
for p in task_work['assembly_task']['pairs']:
    check(all(v==0 for v in p['surface_work'].values()), 'emitted surface counters zero '+str(p['candidate_index']))
    check(p['closed_solid_work']['work_units']==1 and all(v==0 for k,v in p['closed_solid_work'].items() if k!='work_units'),
          'emitted closed counters admission only '+str(p['candidate_index']))
for h in host:
    delta={}
    for side,sign in [('after',1),('before',-1)]:
        for module in h['work'][side]:
            for key,value in module['work'].items():
                if type(value) is int: delta[key]=delta.get(key,0)+sign*value
    h['product_counter_delta']=delta
check(host[1]['product_counter_delta']['to_mesh']==14 and host[1]['product_counter_delta']['directory_vertices']==848
      and host[1]['product_counter_delta']['triangulations']==0, 'directory actual counter deltas')
check(host[2]['product_counter_delta']['to_mesh']==host[2]['product_counter_delta']['triangulations']==4
      and host[3]['product_counter_delta']['to_mesh']==host[3]['product_counter_delta']['triangulations']==2, 'selected geometry actual deltas 4 and 2')
check(host[0]['work']['native_work']['to_mesh']==host[0]['work']['native_work']['triangulations']==14,'additional QA evaluated snapshot work')

# Exact entry timing anchors: outer stage assignment occurs 3600ns after QA row's ended_ns.
qa_outer=result['QA_snapshot']['ended_ns']-result['QA_snapshot']['started_ns']
stages=result['timing_stages_ns']
check(qa_outer==54925700 and stages['QA_evaluated_snapshot']==54929300, 'two QA anchors reproduced')
check(result['session_wall_ns']==result['ended_ns']-result['started_ns']==2992042600,'full owned session exact')
business_sum=sum(b['ended_ns']-b['started_ns'] for b in business)
covered=sum(stages.values())+business_sum
timing={'business_rows_ms':{b['request']['id']:(b['ended_ns']-b['started_ns'])/1e6 for b in business},
 'business_sum_ms':business_sum/1e6,'QA_row_outer_ms':qa_outer/1e6,'QA_stage_ms':stages['QA_evaluated_snapshot']/1e6,
 'QA_stage_minus_row_ns':stages['QA_evaluated_snapshot']-qa_outer,'QA_inner_receipt_ms':qa['elapsed_ns']/1e6,
 'stage_ms':{k:v/1e6 for k,v in stages.items()},'full_owned_session_ms':result['session_wall_ns']/1e6,
 'nonoverlapping_stage_plus_business_ms':covered/1e6,'unassigned_residual_within_session_ms':(result['session_wall_ns']-covered)/1e6,
 'no_double_sum':'stdio and worker durations nest in business; QA row nests stage; all stage/business windows nest session'}
check(covered<=result['session_wall_ns'],'phase windows leave nonnegative residual')
formal=load(P+'entry/FORMAL_PROCESS.json'); build=load(P+'assets/build_01/RESULTS.json'); oracle=load(P+'oracle/formal_replay_01/RESULTS.json')
timing['formal_launcher_process_ms']=formal['elapsed_ms']; timing['asset_build_process_ms']=(build['ended_ns']-build['started_ns'])/1e6
timing['formal_oracle_saved_only_ms']=(oracle['ended_ns']-oracle['started_ns'])/1e6
check(formal['exit_code']==0 and build['exit_code']==0 and build['reaped'] is True and build['forced'] is False,'formal runner and separate asset build lifecycle')
check(oracle['elapsed_ns']==oracle['ended_ns']-oracle['started_ns'] and oracle['error'] is None and oracle['product_calls']==oracle['model_consumers']==0,'separate offline oracle replay cost')

proof=load(R+'PRODUCT_RUNTIME_PROOF.json'); pclose=load(R+'product/CLOSE.json'); start=load(R+'product/START.json')
exit_record=result['product_runtime_exit']; nsession=load(R+'native/SESSION.json'); nclosed=load(R+'native/WORKER_CLOSED.json')
check(proof==result['product_runtime_proof'] and proof['confirmed'] and proof['launcher_pid']==start['launcher_pid']==pclose['launcher_pid'],'actual runtime ownership proof bound launcher')
check(proof['runtime_pid']!=proof['launcher_pid'] and proof['parent_chain'][0]['pid']==proof['runtime_pid'] and proof['parent_chain'][0]['parent_pid']==proof['launcher_pid'],'actual child runtime distinct from launcher')
check(pclose==result['product_close'] and pclose['exit_code']==0 and pclose['process_reaped'] and pclose['reader_stopped'] and pclose['error'] is None,'product launcher reaped exit0')
check(exit_record==complete['product_runtime_exit'] and exit_record['confirmed'] and exit_record['exited'] and exit_record['exit_code']==0 and exit_record['handle_closed'],'retained actual runtime handle exit0 and closed')
close_reply=load(R+'native/WIRE/005/RESPONSE.bin')
check(close_reply==result['native_close']['response'] and close_reply['status']=='closed' and close_reply['pid']==nsession['pid']==nclosed['pid'],'native close raw receipt binds actual PID')
check(result['native_close']['exit_code']==0 and result['native_close']['process_reaped'] and result['native_close']['error'] is None,'native owned Popen reaped exit0')
check(nclosed==result['closed'] and nclosed['poisoned'] is False and nclosed['initial_geometry_fingerprint']==nclosed['final_geometry_fingerprint'],'native unchanged final fingerprint')
check(result['errors']==[] and result['harness_execution_complete'] is True and result['business_passed'] is None,'harness complete distinct from business pass')
check(complete['formal_sequences']==1 and complete['formal_replays']==0,'one sequence no replay receipt')
check(sorted({p.split('/')[3] for p in paths if p.startswith(P+'entry/run_') and len(p.split('/'))>4})==['run_01'],'only one saved actual run directory')
marker=load(P+'entry/FORMAL_STARTED.json'); check(marker['started_ns']==result['started_ns'],'single reserved marker matches actual run')
check('three_rows_missing_last_response' in raw(P+'entry/PREPARATION.json').decode()
      and 'handle_closed' in raw(P+'entry/history/prepared_02_03.diff').decode()
      and 'transport_or_harness_exception' in raw(P+'entry/history/prepared_02_03.diff').decode(),'preformal defects and changes preserved')
check(all(not e.get('changed_or_new_PNG_files') and e.get('render_events_after',0)==e.get('render_events_before',0)==0 for e in events),'no recorded render/image changes')

payload={'fixed_commit':COMMIT,'source_files_compared':len(sources),'check_count':len(checks),'passed':True,
 'denominators':{'formal_sequences':1,'formal_product_replays':0,'stdio_TX_messages':7,'stdio_RX_messages':6,'metadata_TX':4,'metadata_RX':3,
 'metadata_host_RPC':0,'QA_host_RPC':1,'business_host_RPC':3,'close_host_RPC':1,'directory_objects':14,'assembly_tasks':1,'assembly_pairs':3,
 'assembly_complete_pairs':0,'assembly_unknown_pairs':3,'control_tasks':1,'control_pairs':1,'control_complete_pairs':1,'assembly_clearance_requirements_unknown':3,'three_candidate_nearest_unknown':1},
 'host':host,'host_totals':host_total,'stdio':stdio,'stdio_totals':{'tx_bytes':1647,'rx_bytes':42288,'total_bytes':43935},'timing':timing,
 'assembly_summary':assembly['summary'],'control_witness':witness,'raw_observe_task_work':task_work,
 'lifecycle':{'product_launcher':pclose,'actual_runtime_proof':proof,'actual_runtime_exit':exit_record,'Blender_close':result['native_close'],'Blender_closed_state':nclosed,
 'close_worker_event_status':events[-1]['status'],'close_status_interpretation':'worker close branch leaves generic event status unknown; raw close says closed and launcher Popen exit0 is confirmed'},
 'failure_history':complete['failure_history'],
 'execution':{'saved_data_analysis_only':True,'author_verifier_invocations':0,'product_or_solver_imports':0,'Blender_starts':0,'model_calls':0},
 'limits':['One qualification sequence, no native-vs-plugin or stable performance claim.',
 'Geometry oracle mathematical verification is outside this cost review; public denominator and preserved unknown/control status checked here.',
 'No timings isolate QA full raw mesh fingerprint scans or source bootstrap from their enclosing request.',
 'Model tokens/fees/quality and complete engineering coordination cost remain unmeasured.']}
for name,value in [('RESULTS.json',payload),('CHECKS.json',checks),('SOURCES.json',sources)]:
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'passed':True,'checks':len(checks),'sources':len(sources),'host_totals':host_total,'timing':timing},ensure_ascii=False,indent=2))
