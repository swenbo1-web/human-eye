"""Recompute saved actual QA facts only, with stdlib. No product execution."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];RUN=HERE/'actual_run_01'

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rows(path):return [json.loads(row) for row in Path(path).read_text(encoding='utf8').splitlines() if row]
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

d=read(RUN/'RESULTS.json');assert d['passed'] and len(d['records'])==19
before=read(RUN/'identity_before.json');after=read(RUN/'identity_after.json');assert before==after
assert before['source_sha256']==d['source_sha256'] and len(before['source_files'])==136
for item in before['source_files']:
    assert sha(ROOT/item['path'])==item['sha256']
    raw=subprocess.check_output(['git','show',d['product_commit']+':'+item['path']],cwd=ROOT)
    assert hashlib.sha256(raw).hexdigest()==item['sha256']
old=read(RUN/'old_identity_before.json');assert old==read(RUN/'old_identity_after.json')
assert old['source_sha256']==d['old_source_sha256'] and len(old['source_files'])==136
for item in old['source_files']:assert sha(RUN/'runtime_old'/item['path'])==item['sha256']
for name in ('qa_fixture.py','qa_observer.py','qa_stdio.py','qa_run.py'):
    assert (HERE/name).read_bytes()==(RUN/(name+'.txt')).read_bytes()
    tree=ast.parse((HERE/name).read_text(encoding='utf8'))
    assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                   and node.func.attr=='setprofile' for node in ast.walk(tree))

costs=[];calls=Counter();work=Counter();maximum=0.;region_count=0
by_mode={};control_costs=[]
for mode in ('old_owned','new_owned','new_shared'):
    folder=RUN/mode;tx=(folder/'stdio_tx.bin').read_bytes().splitlines(keepends=True)
    rx=(folder/'stdio_rx.bin').read_bytes().splitlines(keepends=True)
    assert len(tx)==len(rx)
    requests={};responses={}
    for left,right in zip(tx,rx):
        a,b=json.loads(left),json.loads(right);assert a['id']==b['id']
        requests[a['id']]=(a,left);responses[a['id']]=(b,right)
        if a['method']=='qa/control':
            event=next(x for x in rows(folder/'metrics.jsonl') if x.get('event')=='control' and x['id']==a['id'])
            control_costs.append(dict(mode=mode,request_id=a['id'],operation=a['params']['op'],
                stdio_tx_bytes=len(left),stdio_rx_bytes=len(right),control_capabilities_ms=event['duration_ms']))
    mode_rows=[r for r in d['records'] if r['mode']==mode]
    assert len(mode_rows)=={'old_owned':4,'new_owned':12,'new_shared':3}[mode]
    for r in mode_rows:
        request,left=requests[r['request_id']];response,right=responses[r['request_id']]
        assert request['params']['arguments']==r['arguments'] and response['result']['isError'] is False
        assert json.loads(response['result']['content'][0]['text'])==r['result']
        assert len(left)==r['stdio_tx_bytes'] and len(right)==r['stdio_rx_bytes']
        assert r['client_profile_none'] and r['metric']['profile_none'] and r['blender_event']['profile_none']
        assert r['ledger_before_sha256']==r['ledger_after_sha256']
        e=r['blender_event'];calls.update(e['calls']);work.update(e['work_delta'])
        oracle=read(r['oracle_file']);expected=oracle['report'];actual=r['result']
        for key in ('schema','status','assessment','model_id','scope','reason'):assert actual.get(key)==expected.get(key)
        assert len(actual['regions'])==len(expected['regions'])
        for a,b in zip(actual['regions'],expected['regions']):
            assert a['section_index']==b['section_index'] and a['vertex_ids']==b['vertex_ids'] and a['flagged']==b['flagged']
            error=abs(a['predicted_severity']-b['predicted_severity']);assert error==0.;maximum=max(maximum,error);region_count+=1
        if 'max_severity' in expected:assert actual['max_severity']==expected['max_severity']
        selection=r['arguments']['selection'];normalized=dict(selection)
        normalized['vertex_indices']=selection.get('vertex_indices',sorted({i for section in selection['sections'] for i in section}))
        encoded=json.dumps(normalized,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
        assert actual['source']['selection_key']==hashlib.sha256(encoded).hexdigest()
        assert actual['source']['selected_vertices']==len(normalized['vertex_indices'])
        assert len(oracle['packet']['vertex_ids'])==len(normalized['vertex_indices'])
        assert e['calls']['capture_entries']==e['calls']['predict_entries']==e['work_delta']['captures']==1
        if 'repeat' in r['label']:
            assert e['bound_same'] and e['prepared_before']==e['prepared_after']
            assert e['work_delta'].get('static_reads',0)==e['work_delta'].get('preparations',0)==0
        expected_copies=1 if mode=='old_owned' and r['label'] in ('first','static','load') else 0
        assert e['calls'].get('static_patch_copies',0)==expected_copies
        costs.append(dict(mode=mode,label=r['label'],status=actual['status'],selected_vertices=actual['source']['selected_vertices'],
            section_count=len(actual['regions']),product_method_ms=e['product_method_ms'],full_tool_rtt_ms=r['full_tool_rtt_ms'],
            stdio_tx_bytes=r['stdio_tx_bytes'],stdio_rx_bytes=r['stdio_rx_bytes'],host_transport_bytes=r['metric']['transport_bytes'],
            calls=e['calls'],work_delta=e['work_delta'],selection_key=actual['source']['selection_key'],
            profile_none=True,oracle_max_abs_error=r['oracle_max_abs_error']))
    exits=[x for x in rows(folder/'metrics.jsonl') if x['event']=='exit'];assert len(exits)==1 and exits[0]['profile_none']
    assert read(folder/'exit.json')['returncode']==0
    wire=exits[0]['transport_bytes']
    for name,count in wire.items():assert (folder/name).stat().st_size==count
    by_mode[mode]=dict(tool_calls=len(mode_rows),stdio_messages=len(tx),
        whole_stdio_tx_bytes=sum(map(len,tx)),whole_stdio_rx_bytes=sum(map(len,rx)),whole_host_bytes=wire,
        tool_stdio_tx_bytes=sum(r['stdio_tx_bytes'] for r in mode_rows),tool_stdio_rx_bytes=sum(r['stdio_rx_bytes'] for r in mode_rows),
        tool_host_bytes=dict(sum((Counter(r['metric']['transport_bytes']) for r in mode_rows),Counter())))
for r in rows(RUN/'new_shared_setup/controls.jsonl'):
    a,b=json.loads(bytes.fromhex(r['tx_hex'])),json.loads(bytes.fromhex(r['rx_hex']))
    assert a['params']['op']=='inspect' and 'control' in b
    control_costs.append(dict(mode='new_shared',operation='inspect',socket_tx_bytes=len(bytes.fromhex(r['tx_hex'])),
        socket_rx_bytes=len(bytes.fromhex(r['rx_hex'])),control_ms=r['duration_ms']))

lookup={(r['mode'],r['label']):r for r in d['records']};pairs=[]
def body(r):return {k:v for k,v in r['result'].items() if k not in ('source','request_trace')}
for label in ('first','repeat','static','load'):
    a,b=lookup['old_owned',label],lookup['new_owned',label]
    assert body(a)==body(b)
    assert read(a['oracle_file'])['packet']==read(b['oracle_file'])['packet']
    assert a['blender_event']['work_delta']==b['blender_event']['work_delta']
    pairs.append(dict(label=label,old_product_ms=a['blender_event']['product_method_ms'],new_product_ms=b['blender_event']['product_method_ms'],
        product_delta_ms=b['blender_event']['product_method_ms']-a['blender_event']['product_method_ms'],
        old_full_tool_rtt_ms=a['full_tool_rtt_ms'],new_full_tool_rtt_ms=b['full_tool_rtt_ms'],
        rtt_delta_ms=b['full_tool_rtt_ms']-a['full_tool_rtt_ms'],reports_equal_excluding_source_trace=True,native_packets_exact=True,
        source_work_equal=True,old_static_copies=a['blender_event']['calls'].get('static_patch_copies',0),
        new_static_copies=b['blender_event']['calls'].get('static_patch_copies',0)))
for mode in ('new_owned','new_shared'):
    a,b,c=(lookup[mode,label]['result']['source'] for label in ('explicit_first','implicit_first','explicit_return'))
    assert [a['selected_vertices'],b['selected_vertices'],c['selected_vertices']]==[1602,1536,1602]
    assert a['selection_key']!=b['selection_key'] and a['selection_key']==c['selection_key']
unknown=lookup['new_owned','unknown']['result'];recovered=lookup['new_owned','recovered']['result']
assert unknown['status']=='unknown' and unknown['reason']=='bone_twist_branch_unknown'
assert unknown['regions']==[] and 'max_severity' not in unknown and recovered['status']=='estimated'
assert recovered['source']['epoch']>unknown['source']['epoch']
assert sum(r['result']['status']=='estimated' for r in d['records'])==18 and region_count==441
assert calls==Counter(capture_entries=19,static_read_entries=14,prepare_entries=14,static_patch_copies=3,predict_entries=19)
assert sum(x['operation']=='inspect' for x in control_costs)==19
for mode in by_mode:
    assert sha(RUN/(mode+'_setup')/'fixture.blend')==d['fixture_sha256']
    assert (RUN/(mode+'_setup')/'actions.json').read_bytes()==b'opaque ledger unchanged in expert opt QA\n'
cleanup=read(HERE/'PROCESS_CLEANUP.json');assert not cleanup['known_pid_processes_observed'] and not cleanup['active_scoped_processes']
cleanup.update(exit_records=d['processes'],stdio_client_pids_recorded=False,
    interpretation='All three known Blender PIDs absent; no task Blender/python commandline remains. Stdio clients exited0 but their numeric PIDs were not separately recorded; no new fixture creator was launched.')
save(HERE/'PROCESS_CLEANUP.json',cleanup)
summary=dict(passed=True,offline_only=True,product_commit=d['product_commit'],source_sha256=d['source_sha256'],source_members=136,
    old_commit=d['old_commit'],old_source_sha256=d['old_source_sha256'],source_unchanged=True,actual_attempts=1,tool_calls=19,
    estimated=18,unknown=1,unexpected_errors=0,estimated_region_comparisons=region_count,direct_max_abs_error=maximum,
    native_oracle_invocations=19,source_calls=dict(calls),source_work=dict(work),pairs=pairs,costs=costs,modes=by_mode,
    qa_controls=control_costs,qa_control_count=len(control_costs),post_response_oracle_controls=19,
    fixture_sha256=d['fixture_sha256'],processes=d['processes'],cleanup=cleanup,runner_sequence_ms=d['runner_sequence_ms'],
    model_api_calls=0,user_assets=0,
    limitations=['One fixed-order old/new sample per stage; no statistical speed guarantee; repeat was slightly slower.',
        'No profiler on client or Blender; lightweight wrappers and transport recording overhead remain in timings.',
        'Oracle/native extraction and large artifact writes occur in separate controls after tools/call response.',
        '19 predict entries include one unknown early result with no MLP score; 18 estimated reports score441 sections.',
        'Unknown recovery uses file load and prepares again; it does not prove reuse across that recovery.',
        'Same-model native oracle checks integration/source consistency, not prediction accuracy.',
        'Accepted whole-mesh BMesh/LBS/model/M5 algorithms were not changed or rebenchmarked.',
        'Stdio client numeric PIDs were not recorded; their exit0 and absence of scoped commandlines are recorded.'])
save(HERE/'ACTUAL_COSTS.json',summary)
lines=['# Expert entry optimization actual QA','',
    f"Fixed product `{d['product_commit']}`; 136-source SHA256 `{d['source_sha256']}`. Old comparison is exported from `{d['old_commit']}` with source SHA256 `{d['old_source_sha256']}`. Both136 source sets match before/after; new current disk also matches fixed Git bytes. The old runtime export contains only136 runtime files and pyproject marker, not another worktree or historical evidence matrix.",'',
    'A single actual_run_01 completed all19 tools on the first attempt: old_owned4, new_owned12, new_shared3. All were normal successful tools (isError=false):18 estimated reports and one real unknown. Independent native RNA packets evaluated by the same frozen model match441 estimated region scores/flags/IDs exactly, maximum severity difference0. Unknown reports bone_twist_branch_unknown, empty regions and no invented score; a subsequent load and normal estimated read recover. Recovery increments epoch and prepares again. This is a same-model source/integration oracle, not independent model accuracy evidence.','',
    'The existing generated fixture is reused unchanged:24,804 vertices/9,866 triangles, original patch1,602 sparse high-ID vertices/3,200 triangles. Owned and shared selections each transition explicit1,602 → default union1,536 → explicit1,602; normalized selection keys change and return exactly. Owned explicit/default warm repeats keep bound/prepared and perform no static read or preparation. All known fixture copies and opaque ledger bytes remain unchanged.','',
    'Across19 successful captures there are14 static reads/preparations and19 predict_prepared entries; the unknown early report does not score the MLP. Old first/static/load each export one unused static_patch copy, repeat exports none. All15 new tools export zero static_patch copies. In the four matched old/new stages, source work and direct native packets are exact, and reports excluding source/trace metadata are exact. Public capture isolation is separately checked by the parent CPU group.','',
    'No sys.setprofile calls exist in the four executing harnesses; client, stdio server and Blender assert getprofile() is None. Lightweight verification wrappers count capture/static/prepare/predict and static-patch deepcopy by schema, excluding notice copies. Host timing encloses only the original host method. Full tool RTT spans stdin write to complete stdout response; transport recording and light wrappers remain included. All19 native oracle extractions, model calls and large event/packet writes run in a separate inspect control after that response. Thus oracle costs are outside both reported time windows.','',
    '| Stage | Old method ms | New method ms | Delta ms | Old tool RTT ms | New tool RTT ms | Delta ms | Old/new copies |',
    '|---|---:|---:|---:|---:|---:|---:|---:|']
for p in pairs:lines.append(f"| {p['label']} | {p['old_product_ms']:.4f} | {p['new_product_ms']:.4f} | {p['product_delta_ms']:+.4f} | {p['old_full_tool_rtt_ms']:.4f} | {p['new_full_tool_rtt_ms']:.4f} | {p['rtt_delta_ms']:+.4f} | {p['old_static_copies']}/{p['new_static_copies']} |")
lines+=['','These are individual fixed-order observations, not sample means or a statistical speed guarantee. Repeat is slightly slower in the new run; it already made no static copy. First includes cold dependency loading. Differences cannot be assigned entirely to deepcopy, and the old profiled82–87ms residual is not used as a saving estimate. Removing three observed unused exports, while preserving results and source work, is the direct adoption evidence. No fastest-sample retries were made.','',
    '| Mode | Call | Status | Selected | Method ms | Full RTT ms | Stdio TX/RX B | Host TX/RX B |',
    '|---|---|---|---:|---:|---:|---:|---:|']
for c in costs:
    wire=c['host_transport_bytes'];tx=sum(v for k,v in wire.items() if '_tx.' in k);rx=sum(v for k,v in wire.items() if '_rx.' in k)
    lines.append(f"| {c['mode']} | {c['label']} | {c['status']} | {c['selected_vertices']} | {c['product_method_ms']:.4f} | {c['full_tool_rtt_ms']:.4f} | {c['stdio_tx_bytes']}/{c['stdio_rx_bytes']} | {tx}/{rx} |")
lines+=['',f"ACTUAL_COSTS.json retains all19 individual costs, source work, raw byte totals and all{len(control_costs)} separate controls. Nineteen controls are post-response oracle inspections; the other six perform static/load/unknown fixture changes. Initialization/tools-list and controls remain outside the19-tool denominator. Entire runner sequence is{d['runner_sequence_ms']:.4f}ms, including136-source export/Git reads, subprocess startup, controls and oracle; this is not a pure task runtime.",'',
    '| Mode | Whole stdio messages | Whole stdio TX/RX B | Tool stdio TX/RX B | Whole host wire B |',
    '|---|---:|---:|---:|---|']
for mode,m in by_mode.items():lines.append(f"| {mode} | {m['stdio_messages']} | {m['whole_stdio_tx_bytes']}/{m['whole_stdio_rx_bytes']} | {m['tool_stdio_tx_bytes']}/{m['tool_stdio_rx_bytes']} | {json.dumps(m['whole_host_bytes'])} |")
lines+=['','The3 known Blender PIDs29420/6496/28636 are absent in the final read-only query; no task Blender/python commandline remains. Owned old/new and shared stdio clients exit0. Shared fixture is controlled terminate then wait with return1. Stdio client numeric PIDs were not separately recorded; exit0 records and the scoped process query are retained. No fixture creator was launched because the prior generated fixture was reused.','',
    'This group does not repeat the old25-tool or165-test matrices, task/nearest or M5. Existing unaffected results are referenced by the parent. Whole-mesh BMesh cost and numerical/model algorithms remain unchanged; no end-to-end native performance target is inferred. Original actual_run_01 raw files, four executing harness snapshots,19 full native packets/reports, identities and generated copies are retained. Offline report generation imports no product and starts no Blender.','']
(HERE/'ACTUAL_QA_REPORT.md').write_text('\n'.join(lines),encoding='utf8')
print(json.dumps(dict(passed=True,tool_calls=19,estimated=18,unknown=1,regions=region_count,source_calls=dict(calls),controls=len(control_costs))))
