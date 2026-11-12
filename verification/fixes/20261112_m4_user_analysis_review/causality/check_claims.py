"""Small saved-record arithmetic and timing-boundary check; no runtime imports."""
import hashlib
import json
import statistics
import subprocess
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH=ROOT/'verification/m4_selected_geometry_consumption_001'
COST=Path('D:/hefe/verification/fixes/20261112_m4_selected_consumption_review/cost/RESULTS.json')
ATTACHMENT=Path('D:/hefe/.codex-remote-attachments/01a1971f-eef5-7a23-a1b1-2352beb80a77/dc149763-6a45-4552-b346-273e80220a75/1-M4_SELECTED_GEOMETRY_TRIAL_REVIEW_ANALYSIS.md')
COMMIT='de35ceda1f5e3f5af2c9ec02f0e4646808f417c2'
sources={}
def raw(path):
    value=path.read_bytes();sources[str(path)]=hashlib.sha256(value).hexdigest();return value
def read(path):return json.loads(raw(path))
audit=read(COST)
text=raw(ATTACHMENT).decode('utf8')
for path in ('runtime/consumer_transport.py','runtime/driver.py'):
    raw(BATCH/path)
for cell in ('sgc03','sgc07'):
    raw(BATCH/'cells'/cell/'owner/tool_01/REQUEST.json')
result=[]
for row in audit['cells']:
    folder=BATCH/'cells'/row['cell']
    consumer=read(folder/'CONSUMER.json')
    events=[json.loads(line) for line in raw(folder/'events.jsonl').splitlines() if line]
    complete=[e for e in events if e['event']['type']=='turn.completed']
    assert len(complete)==1 and complete[0]['event']['usage']==row['usage']
    starts=[e['perf_ns'] for e in events if e['event']['type']=='item.started' and e['event'].get('item',{}).get('type')=='mcp_tool_call']
    ends=[e['perf_ns'] for e in events if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='mcp_tool_call']
    assert len(starts)==len(ends)==row['tool_attempts']
    final=[e for e in events if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='agent_message' and e['event']['item']['text']==consumer['final']]
    assert len(final)==1 and final[0]['perf_ns']==consumer['final_received_ns']
    detail={'cell':row['cell'],'group':row['group'],'tools':len(starts),'full_cell_ns':row['full_cell_ns'],
        'submit_gap_ns':consumer['prompt_submitted_ns']-consumer['started_ns'],
        'pre_setup_ns':row['pre_consumer_setup_ns'],
        'prompt_to_first_tool_ns':starts[0]-consumer['prompt_submitted_ns'],
        'public_tool_sum_ns':sum(b-a for a,b in zip(starts,ends)),
        'inter_tool_ns':sum(starts[i+1]-ends[i] for i in range(len(starts)-1)),
        'last_tool_to_final_ns':consumer['final_received_ns']-ends[-1],
        'final_to_turn_completed_ns':consumer['turn_completed_ns']-consumer['final_received_ns'],
        'turn_completed_to_observed_process_exit_ns':consumer['process_exit_ns']-consumer['turn_completed_ns'],
        'observed_process_exit_to_cleanup_ns':consumer['cleanup_end_ns']-consumer['process_exit_ns'],
        'final_to_cleanup_ns':consumer['cleanup_end_ns']-consumer['final_received_ns'],
        'post_consumer_close_ns':row['post_consumer_close_ns'],
        'input':row['usage']['input_tokens'],'cached_input':row['usage']['cached_input_tokens'],
        'output':row['usage']['output_tokens'],'reasoning_output':row['usage']['reasoning_output_tokens'],
        'total_tokens':row['input_plus_output_tokens'],
        'uncached_input':row['usage']['input_tokens']-row['usage']['cached_input_tokens']}
    additive=['submit_gap_ns','pre_setup_ns','prompt_to_first_tool_ns','public_tool_sum_ns','inter_tool_ns',
              'last_tool_to_final_ns','final_to_cleanup_ns','post_consumer_close_ns']
    assert sum(detail[k] for k in additive)==detail['full_cell_ns']
    assert sum(detail[k] for k in ('final_to_turn_completed_ns','turn_completed_to_observed_process_exit_ns','observed_process_exit_to_cleanup_ns'))==detail['final_to_cleanup_ns']
    detail['partition_sum_exact']=True
    result.append(detail)
by={r['cell']:r for r in result}
contrasts=[]
for gid in ('sgc07','sgc05'):
    for nid in ('sgc01','sgc08'):
        contrasts.append({'candidate':gid,'reference':nid,'same_tool_count':by[gid]['tools']==by[nid]['tools'],
            'token_difference':by[gid]['total_tokens']-by[nid]['total_tokens'],
            'token_change_percent':100*(by[gid]['total_tokens']/by[nid]['total_tokens']-1)})
groups={}
for group in ('N','P','G'):
    chosen=[r for r in result if r['group']==group]
    groups[group]={k:sum(r[k] for r in chosen) for k in ('input','cached_input','uncached_input','output','total_tokens')}
    groups[group]['last_tool_to_final_median_s']=statistics.median(r['last_tool_to_final_ns'] for r in chosen)/1e9
    groups[group]['prompt_to_final_median_s']=statistics.median(r['prompt_to_first_tool_ns']+r['public_tool_sum_ns']+r['inter_tool_ns']+r['last_tool_to_final_ns'] for r in chosen)/1e9
    groups[group]['full_cell_median_s']=statistics.median(r['full_cell_ns'] for r in chosen)/1e9
git_sources=[Path(p) for p in sources if Path(p).is_relative_to(ROOT)]
proc=subprocess.run(['git','cat-file','--batch'],cwd=ROOT,input=('\n'.join(COMMIT+':'+p.relative_to(ROOT).as_posix() for p in git_sources)+'\n').encode(),capture_output=True,check=True)
pos=0
for path in git_sources:
    end=proc.stdout.index(b'\n',pos);header=proc.stdout[pos:end].split();assert header[1]==b'blob';n=int(header[2]);pos=end+1
    assert hashlib.sha256(proc.stdout[pos:pos+n]).hexdigest()==sources[str(path)],str(path)
    pos+=n+1
output={'attachment_sha256':sources[str(ATTACHMENT)],'fixed_commit':COMMIT,'source_git_blobs':len(git_sources),
    'new_product_Blender_model_calls':0,'cells':result,'groups':groups,'same_tool_count_contrasts':contrasts,
    'uncached_input_change_percent':{ref:100*(groups['G']['uncached_input']/groups[ref]['uncached_input']-1) for ref in ('N','P')},
    'two_call_token_range':[min(r['total_tokens'] for r in result if r['tools']==2),max(r['total_tokens'] for r in result if r['tools']==2)],
    'three_call_token_range':[min(r['total_tokens'] for r in result if r['tools']==3),max(r['total_tokens'] for r in result if r['tools']==3)],
    'causal_identification':'Not available: tool count, response format/content, answer length, cache, request latency and route were not independently randomized.',
    'sources':sources}
(OUT/'RESULTS.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'same_tool_count_contrasts':contrasts,'groups':groups,'late_intervals':[{'cell':r['cell'],**{k:round(r[k]/1e9,6) for k in ('final_to_turn_completed_ns','turn_completed_to_observed_process_exit_ns','observed_process_exit_to_cleanup_ns')}} for r in result]},indent=2))
