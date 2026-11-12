"""Independent saved-data cost audit. Does not import product/author analyzers."""
import hashlib
import json
import math
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE = ROOT/'verification/m2_tight_directory_001'
RUN = BASE/'measurement/run_01'
OUT = Path(__file__).resolve().parent
COMMIT = 'c0134088796d47a982edfc838aa6704c8e052d57'
READS = {}
CHECKS = []

def raw(p):
    p=Path(p); data=p.read_bytes(); READS[str(p)]=hashlib.sha256(data).hexdigest(); return data
def read(p): return json.loads(raw(p))
def rows(p): return [json.loads(line) for line in raw(p).splitlines() if line]
def ck(condition, name):
    CHECKS.append({'name':name,'passed':bool(condition)})
    if not condition: raise AssertionError(name)
def sha(data): return hashlib.sha256(data).hexdigest()
def stats(values):
    return {'n':len(values),'raw':values,'median':statistics.median(values),
            'p95_nearest_rank':sorted(values)[math.ceil(len(values)*.95)-1]}
def wirebody(response):
    text=response['result']['result']
    prefix='HUMAN_EYE_BLENDER_MCP:'
    return json.loads(text[len(prefix):])['result'] if text.startswith(prefix) else json.loads(text)

binding=read(RUN/'INPUT_BINDINGS.json')
matrix=read(RUN/'RESULTS.json')
freeze=read(BASE/'measurement/BASELINE_FROZEN.json')
author=read(RUN/'SUMMARY.json')
assets={a['name']:a for a in binding['assets']}
lanes=('old','new','native')
orders=(lanes,('native','old','new'),('new','native','old'))
expected=[]
for asset in ('simple_boxes','peripheral','rotated_asymmetric'):
    for rep,order in enumerate(orders,1):
        expected += [f'dir_{asset}_{rep}_{lane}' for lane in order]
for asset,order in zip(assets,orders): expected += [f'two_{asset}_{lane}' for lane in order]
ck([c['case_id'] for c in binding['schedule']]==expected,'frozen_27_plus_9_balanced_order')
ck([c['case']['case_id'] for c in matrix['cases']]==expected,'executed_order_matches_frozen_order')
ck(matrix['performance_retries']==0 and matrix['all_planned_dispatched'],'one_matrix_no_recorded_retries')
ck(matrix['ended_ns']-matrix['started_ns']==matrix['wall_ns'],'matrix_wall_subtraction')
for name,digest in binding['source_files'].items(): ck(sha(raw(name))==digest,'frozen_source:'+name)
for name,digest in freeze['files'].items(): ck(sha(raw(BASE/'measurement'/name))==digest,'preimplementation_frozen:'+name)
for asset in assets.values(): ck(sha(raw(asset['asset']))==asset['asset_sha256'],'asset:'+asset['name'])

groups=defaultdict(lambda:defaultdict(list))
lifetimes=defaultdict(lambda:defaultdict(list))
session_outputs=[]
two=[]
business=0
all_rpc=0
runtime_count=0
last_end=matrix['started_ns']
native_tail=[]
peer_tail=[]

for item in binding['schedule']:
    cid=item['case_id']; folder=RUN/cid; data=read(folder/'RESULTS.json')
    lane,asset=item['lane'],item['asset']; is_two=item['two_step']
    ck(not data['errors'] and data['passed'],cid+':no_error')
    ck(data['asset']==asset and data['lane']==lane and data['two_step']==is_two,cid+':case_identity')
    ck(data['started_ns']>=last_end and data['ended_ns']<=matrix['ended_ns'],cid+':sequential_window')
    last_end=data['ended_ns']
    ck(data['session_wall_ns']==data['ended_ns']-data['started_ns'],cid+':session_subtraction')
    ck(len(data['rows'])==(2 if is_two else 11),cid+':request_denominator')
    config=read(folder/'native/CONFIG.json')
    ck(config['asset_sha256']==assets[asset]['asset_sha256'],cid+':actual_asset_binding')
    events=rows(folder/'native/WORKER_EVENTS.jsonl')
    wires=read(folder/'native/WIRE/INDEX.json')
    ck(events==data['worker_events'] and wires==data['wire'],cid+':raw_event_binding')
    all_rpc+=len(wires)
    by_sequence={r['sequence']:r for r in wires}
    rawwires={}
    for sequence,meter in by_sequence.items():
        wirefolder=folder/'native/WIRE'/f'{sequence:03d}'
        tx,rx=raw(wirefolder/'REQUEST.bin'),raw(wirefolder/'RESPONSE.bin')
        ck(len(tx)==meter['request_bytes'] and len(rx)==meter['response_attempted_bytes'] and
           len(tx)+len(rx)==meter['request_response_attempted_bytes'] and meter['response_sendall_completed'],cid+f':wire_{sequence}')
        rawwires[sequence]=(json.loads(tx),json.loads(rx),len(tx),len(rx))
    has_product=lane!='native' or is_two
    if has_product:
        runtime_count+=1
        init=read(folder/'ACTUAL_INITIALIZE.json')['result']['_meta']['human_eye']
        ck(init['source_sha256']==binding['new' if lane=='new' else 'old']['source_sha256'],cid+':loaded_source')
        ck(data['product_runtime_exit']['confirmed'] and data['product_runtime_exit']['exit_code']==0,cid+':runtime_exit')
        receipts={}
        for path in sorted((folder/'product').glob('*/RECEIPT.json')):
            r=read(path); req=read(path.parent/'TX.bin')
            if req.get('method')=='tools/call': receipts[req['id']]=(r,req,read(path.parent/'RX.bin'))
    record_rows=[]
    for i,row in enumerate(data['rows']):
        selected=is_two and i==1
        phase='selected' if selected else 'cold' if i==0 else 'warm'
        ck(row['index']==i and row['phase']==phase,cid+f':phase_{i}')
        ck(row['tool_ns']==row['ended_ns']-row['started_ns'],cid+f':tool_time_{i}')
        ck(data['started_ns']<=row['started_ns']<row['ended_ns']<=data['ended_ns'],cid+f':nested_time_{i}')
        matched=[e for e in events if isinstance(e.get('started_ns'),int) and row['started_ns']<=e['started_ns']<=row['ended_ns']]
        ck(len(matched)==1 and row['host_RPC']==1 and matched==row['work_events'],cid+f':actual_rpc_{i}')
        ev=matched[0]; seq=ev['sequence']; req,resp,tx,rx=rawwires[seq]
        ck(ev['status']=='completed' and not ev.get('script_error') and ev['terminal_geometry_and_file_checks_passed'],cid+f':host_success_{i}')
        ck(sha(req['params']['code'].encode())==ev['script_sha256'],cid+f':script_binding_{i}')
        ck(row['wire']==[by_sequence[seq]],cid+f':wire_selection_{i}')
        ck(ev['started_ns']+ev['elapsed_ns']<=row['ended_ns'],cid+f':host_within_call_{i}')
        if row['request_kind']=='original_native_execute_code':
            ck(lane=='native' and not selected,cid+f':native_scope_{i}')
            ck(row['response']['response']==resp,cid+f':native_actual_reply_{i}')
            ck(raw(folder/f'REQUEST_{i}.py').decode()==req['params']['code'],cid+f':native_actual_code_{i}')
            text=resp['result']['result']; public=json.loads(text)
            visible=len(text.encode())
            native_tail.append({'case':cid,'phase':phase,'call_minus_exchange_elapsed_ns':row['tool_ns']-row['response']['elapsed_ns']})
        else:
            receipt,actual_req,actual_resp=receipts[f'read_{i}']
            ck(actual_req==row['request'] and actual_resp==row['response'],cid+f':mcp_actual_io_{i}')
            ck(receipt==row['stdio'] and receipt['started_ns']>=row['started_ns'] and
               receipt['started_ns']+receipt['elapsed_ns']<=row['ended_ns'],cid+f':mcp_receipt_time_{i}')
            mode='task' if selected else 'overview' if lane=='old' else 'directory'
            args=actual_req['params']['arguments']
            ck(args['query']['mode']==mode and args['include_image'] is False,cid+f':actual_mode_{i}')
            if selected: ck(args['query']==freeze['selected_query'],cid+':frozen_second_query')
            ck(not actual_resp['result']['isError'],cid+f':mcp_success_{i}')
            texts=[b['text'] for b in actual_resp['result']['content']]
            public=json.loads(texts[0]); visible=sum(len(t.encode()) for t in texts)
            peer_tail.append({'case':cid,'phase':phase,'outer_minus_receipt_ns':row['tool_ns']-receipt['elapsed_ns']})
        ck(public==row['body'] and visible==row['visible_text_UTF8_bytes'],cid+f':public_body_{i}')
        if not selected:
            facts=json.loads(public['routing']['context_text'])['objects'] if lane=='old' else public['objects']
            # Old public objects and detailed context carry the same range facts.
            truth={o['name']:o for o in assets[asset]['oracle']}
            ck(len(facts)==len(truth) and {o['name'] for o in facts}==set(truth),cid+f':coverage_{i}')
            for o in facts:
                ck(o['bbox_min']==truth[o['name']]['bbox_min'] and o['bbox_max']==truth[o['name']]['bbox_max'],cid+f':bounds_{i}:'+o['name'])
                center=o.get('center',[(a+b)/2 for a,b in zip(o['bbox_min'],o['bbox_max'])])
                ck(center==truth[o['name']]['center'],cid+f':center_{i}:'+o['name'])
        work=ev['m2_work']
        if lane=='new' and not selected:
            ck(work['new_resource_arrays']=={'edges':0,'faces':0,'vertices':0},cid+f':new_no_mesh_arrays_{i}')
            before=sum(x['work'].get('triangulations',0) for x in work['before'])
            after=sum(x['work'].get('triangulations',0) for x in work['after'])
            ck(after-before==0,cid+f':new_no_triangulation_{i}')
        business+=1
        metrics={'tool_ns':row['ended_ns']-row['started_ns'],'bridge_request_bytes':tx,'bridge_response_bytes':rx,
                 'bridge_sum_bytes':tx+rx,'visible_text_UTF8_bytes':visible,'host_RPC':1,'host_elapsed_ns':ev['elapsed_ns']}
        record_rows.append(dict(index=i,phase=phase,**metrics,work=work))
        if not is_two:
            for key,value in metrics.items(): groups[(asset,lane,phase)][key].append(value)
    continuous=data['rows'][-1]['ended_ns']-data['rows'][0]['started_ns']
    ck(continuous==data['continuous_request_window_ns'],cid+':continuous_subtraction')
    ck(data['native_close']['process_reaped'] and data['native_close']['exit_code']==0 and
       data['closed']['initial_geometry_fingerprint']==data['closed']['final_geometry_fingerprint'],cid+':native_close_and_state')
    stage=data['timing_stages_ns']; setup=stage['setup_before_first_request']; close=stage['close_and_meter_publish']
    result={'case_id':cid,'asset':asset,'lane':lane,'two_step':is_two,'rows':record_rows,
            'session_ns':data['session_wall_ns'],'setup_ns':setup,'close_ns':close,
            'continuous_ns':continuous,'tool_sum_ns':sum(r['tool_ns'] for r in record_rows),
            'session_other_ns':data['session_wall_ns']-setup-continuous-close}
    session_outputs.append(result)
    if is_two: two.append(result)
    else:
        for name,value in [('setup_ns',setup),('close_ns',close),('session_ns',data['session_wall_ns'])]: lifetimes[(asset,lane)][name].append(value)

ck(business==315 and all_rpc==351 and runtime_count==27,'observed_denominators')
computed={}
for (asset,lane,phase),values in groups.items():
    computed.setdefault(asset,{}).setdefault(lane,{})[phase]={k:stats(v) for k,v in values.items()}
    for key in ('tool_ns','bridge_request_bytes','bridge_response_bytes','bridge_sum_bytes','visible_text_UTF8_bytes','host_RPC'):
        ck(computed[asset][lane][phase][key]==author['groups'][asset][lane][phase][key],f'author_stat_agreement:{asset}:{lane}:{phase}:{key}')
sessions={}
for (asset,lane),values in lifetimes.items(): sessions.setdefault(asset,{})[lane]={k:stats(v) for k,v in values.items()}
old= computed['peripheral']['old']['cold']; new=computed['peripheral']['new']['cold']
simple=computed['simple_boxes']; old95=simple['old']['warm']['tool_ns']['p95_nearest_rank']; new95=simple['new']['warm']['tool_ns']['p95_nearest_rank']
gates={'peripheral_cold_response_reduction':1-new['bridge_response_bytes']['median']/old['bridge_response_bytes']['median'],
       'peripheral_cold_time_reduction':1-new['tool_ns']['median']/old['tool_ns']['median'],
       'peripheral_cold_tx_rx_reduction':1-new['bridge_sum_bytes']['median']/old['bridge_sum_bytes']['median'],
       'simple_warm_p95_increase_ns':new95-old95,'simple_warm_p95_limit_ns':max(1000000,old95*.05)}
gates['all_cost_gates_pass']=gates['peripheral_cold_response_reduction']>=.5 and gates['peripheral_cold_time_reduction']>=.1 and new95-old95<=max(1000000,old95*.05)
ck(gates['all_cost_gates_pass'],'frozen_numeric_cost_gates')

# Verify every consumed indexed file against both the index and fixed Git bytes.
index={row['path']:row for row in read(BASE/'INDEX.json')['files']}
git_paths=[]
for path,digest in list(READS.items()):
    p=Path(path)
    if not p.is_relative_to(ROOT): continue
    rel=p.relative_to(ROOT).as_posix()
    if rel in index:
        ck(index[rel]['sha256']==digest and index[rel]['bytes']==p.stat().st_size,'index:'+rel)
        git_paths.append((rel,digest))
    elif rel!='verification/m2_tight_directory_001/INDEX.json':
        git_paths.append((rel,digest))
proc=subprocess.run(['git','cat-file','--batch'],cwd=ROOT,input=('\n'.join(COMMIT+':'+p for p,_ in git_paths)+'\n').encode(),capture_output=True,check=True)
data=proc.stdout; pos=0
for path,digest in git_paths:
    end=data.index(b'\n',pos); header=data[pos:end].split(); pos=end+1
    ck(len(header)==3 and header[1]==b'blob','fixed_git_present:'+path)
    size=int(header[2]); content=data[pos:pos+size];pos+=size+1
    ck(sha(content)==digest,'fixed_git_bytes:'+path)
result={'fixed_commit':COMMIT,'counts':{'pure_sessions':27,'two_step_sessions':9,'directory_requests':306,
    'selected_requests':9,'business_rpc':business,'all_rpc_including_close':all_rpc,'actual_product_runtime_exits':runtime_count,
    'independent_checks':len(CHECKS),'source_files_read':len(READS),'fixed_git_files':len(git_paths)},
    'groups':computed,'session_costs':sessions,'two_step':two,'gates':gates,
    'matrix_ns':matrix['wall_ns'],'sum_session_ns':sum(r['session_ns'] for r in session_outputs),
    'matrix_between_sessions_ns':matrix['wall_ns']-sum(r['session_ns'] for r in session_outputs),
    'native_tail':native_tail,'peer_tail':peer_tail,'sessions':session_outputs,'checks':CHECKS}
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'SOURCES.json').write_text(json.dumps(READS,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'counts':result['counts'],'gates':gates,'matrix_ns':result['matrix_ns'],'sum_session_ns':result['sum_session_ns']},indent=2))
