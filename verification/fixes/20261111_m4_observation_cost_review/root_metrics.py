from pathlib import Path
import hashlib,json,statistics

B=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_observation_baseline_001')
OUT=Path('D:/hefe/verification/fixes/20261111_m4_observation_cost_review')
S=Path('D:/hefe/verification/fixes/20261111_m4_observation_quality_review/QUALITY_SEAL.json')
assert hashlib.sha256(S.read_bytes()).hexdigest()=='16032384e9f0914ba3e377a1fad1ecd05bcdc9c92ffce6e9a8dc5087eeb8c2c1'
run=json.loads((B/'RUN_RESULT.json').read_bytes());rows=[]
for r in run['records']:
 c=r['consumer'];close=r['finish']['close'];u=c['usage'];tools=close['tools']
 assert c['valid_completion'] and c['exit_code']==0 and not r['errors'] and r['finish']['confirmed']
 assert c==json.loads((B/'cells'/r['cell']/'CONSUMER.json').read_bytes())
 rows.append({'cell':r['cell'],'round':r['round'],'group':r['group'],
  'full_s':r['full_cell_wall_ns']/1e9,'consumer_s':c['wall_ns']/1e9,
  'pre_consumer_s':c['pre_consumer_setup_ns']/1e9,
  'post_consumer_s':(r['full_cell_wall_ns']-c['wall_ns']-c['pre_consumer_setup_ns'])/1e9,
  'prompt_to_final_s':c['prompt_to_final_ns']/1e9,
  'tools':len(tools),'tool_work_s':sum(t['elapsed_ns'] for t in tools)/1e9,
  'response_bytes':sum(t['response_bytes'] for t in tools),
  'input_tokens':u['input_tokens'],'cached_input_tokens':u['cached_input_tokens'],
  'uncached_input_tokens':u['input_tokens']-u['cached_input_tokens'],
  'output_tokens':u['output_tokens'],'reasoning_output_tokens':u['reasoning_output_tokens'],
  'provider_requests':c['provider_requests'],'fees':c['fees'],
  'tool_names':[t['name'] for t in tools]})
summary={}
for arm in ['N','P']:
 rr=[r for r in rows if r['group']==arm];assert len(rr)==3
 summary[arm]={'count':3,'complete_correct':3,
  'sum_s':sum(r['full_s'] for r in rr),'median_s':statistics.median(r['full_s'] for r in rr),
  'range_s':[min(r['full_s'] for r in rr),max(r['full_s'] for r in rr)],
  'consumer_median_s':statistics.median(r['consumer_s'] for r in rr),
  **{k:sum(r[k] for r in rr) for k in ['tools','response_bytes','tool_work_s','input_tokens','cached_input_tokens','uncached_input_tokens','output_tokens','reasoning_output_tokens']}}
pairs=[]
for i in range(1,4):
 rr={r['group']:r for r in rows if r['round']==i};pairs.append({'round':i,'P_minus_N_s':rr['P']['full_s']-rr['N']['full_s'],'P_vs_N_percent':100*(rr['P']['full_s']/rr['N']['full_s']-1)})
result={'review_scope':'Root recomputation from original RUN_RESULT and CONSUMER after quality seal; no model/product execution',
 'quality_seal_sha256':hashlib.sha256(S.read_bytes()).hexdigest(),
 'run_result_sha256':hashlib.sha256((B/'RUN_RESULT.json').read_bytes()).hexdigest(),
 'rows':rows,'summary':summary,'pairs':pairs,
 'P_median_percent_change':100*(summary['P']['median_s']/summary['N']['median_s']-1),
 'P_sum_percent_change':100*(summary['P']['sum_s']/summary['N']['sum_s']-1),
 'batch_wall_s':run['batch_wall_ns']/1e9,'cell_wall_sum_s':sum(r['full_s'] for r in rows),
 'prespecified_median_efficiency_passed':summary['P']['median_s']<summary['N']['median_s'],
 'quality_passed':True,'caveats':['One scene, three repeats per group.','Input includes cached subset; reasoning is subset of output.','All cells and setup/cleanup retained.','No fee estimates or claimed project ROI.']}
(OUT/'ROOT_METRICS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
