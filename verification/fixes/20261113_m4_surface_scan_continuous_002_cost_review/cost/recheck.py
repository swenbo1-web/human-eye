"""Independent integer timing/terminal-usage arithmetic from sealed originals."""
import hashlib
import json
from pathlib import Path
from fractions import Fraction
from statistics import median
import subprocess
import zipfile

TREE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=TREE/'verification/m4_surface_scan_continuous_consumption_002'
COST=TREE/'verification/m4_surface_scan_continuous_consumption_002_cost'
QA=Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_002_quality_review')
OUT=Path(__file__).resolve().parent
ORDER=('N1','C1','C2','N2','N3','C3')
TURNS=('BASE','REPEAT','EDIT')
FIELDS=('input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens')
CHECKS=[];INPUTS={}

def sha(raw):return hashlib.sha256(raw).hexdigest()
def check(name,passed,detail=None):CHECKS.append({'name':name,'passed':bool(passed),'detail':detail})
def data(path):
 raw=Path(path).read_bytes();INPUTS[str(path)]={'sha256':sha(raw),'bytes':len(raw)};return raw
def read(path):return json.loads(data(path))
def union(intervals):
 merged=[]
 for a,b in sorted(intervals):
  assert type(a)is int and type(b)is int and a<=b
  if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
  else:merged.append([a,b])
 return sum(b-a for a,b in merged),merged
def ratio(a,b):
 f=Fraction(a,b);return {'numerator':f.numerator,'denominator':f.denominator,'value':float(f)}
def sum_usage(rows):
 r={k:sum(x[k] for x in rows) for k in FIELDS}
 r['input_plus_output']=r['input_tokens']+r['output_tokens']
 r['uncached_input']=r['input_tokens']-r['cached_input_tokens']
 r['uncached_input_plus_output_diagnostic']=r['uncached_input']+r['output_tokens']
 return r

head=subprocess.check_output(['git','-C',str(TREE),'rev-parse','HEAD'],text=True).strip()
check('fixed_cost_delivery',head=='21f08a9826adf5ef44a305e3d6d1898f0dac5e80')
sealraw=data(QA/'QUALITY_SEAL.json');seal=json.loads(sealraw)
check('quality_seal_SHA',sha(sealraw)=='ccea554353a6f0607263124d2170ef3b2094a07e222c86276f522184b7f5316c')
check('sealed_quality_18',seal['quality']['primary_complete_correct']==18 and seal['quality']['current_state_basis_sufficient']==18 and seal['execution']['completed_turns']==18 and seal['execution']['completed_episodes']==6)
scope=read(QA/'usage_scope/RESULTS.json')
check('sealed_scope_SHA',INPUTS[str(QA/'usage_scope/RESULTS.json')]['sha256']==seal['independent_evidence_sha256']['usage_scope/RESULTS.json'])
check('scope_already_confirmed',scope['passed'] and scope['scope_conclusion']=='per_turn_CLI_invocation_observed')
author_t=read(COST/'timing/TIMING.json');author_u=read(COST/'usage/USAGE.json');author_ledger=read(COST/'LEDGER.json')
source_list=read(COST/'INPUTS.json')['files']
author_sources={str(Path(x['path']).resolve()):x['sha256'] for x in source_list}
mapping=read(B/'private/ANON_MAP.json')['rows']
plan=read(B/'PLAN.json')
check('fixed_order',tuple(x['cell'] for x in plan['sequence'])==ORDER)
check('source_delivery',seal['delivery_commit']==author_t['source_delivery_commit']==author_u['source_delivery_commit']=='a798caf982e2d7eefe0bf52b739b9bef88526be4')

episodes={};turns=[];phase_totals={'N':{},'C':{}}
for cell in ORDER:
 p=B/'episodes'/cell
 ft=read(p/'FINAL_TIMING.json');outer=read(p/'OUTER_RESULT.json');publication=read(p/'TIMING_PUBLICATION.json')
 check(cell+':outer_delta',ft['business_receipts_closed_ns']-ft['started_ns']==ft['full_episode_wall_ns'])
 check(cell+':outer_original_deadline',ft['episode_deadline_ns']-ft['started_ns']==590*10**9 and ft['business_receipts_closed_ns']<ft['episode_deadline_ns'])
 check(cell+':outer_valid',ft['outer_valid_completion'] and ft['within_590s'])
 check(cell+':outer_start_binding',outer['started_ns']==ft['started_ns'])
 zpath=p/'ORIGINALS.zip';data(zpath)
 with zipfile.ZipFile(zpath) as z:
  def zr(member):
   raw=z.read(member);key=str(zpath)+'!'+member;INPUTS[key]={'sha256':sha(raw),'bytes':len(raw)}
   runtime=str((TREE/'.m4cc2'/cell/member).resolve())
   if runtime in author_sources:check(cell+':member_author_source:'+member,author_sources[runtime]==sha(raw))
   return json.loads(raw)
  def ze(member):
   raw=z.read(member);INPUTS[str(zpath)+'!'+member]={'sha256':sha(raw),'bytes':len(raw)}
   runtime=str((TREE/'.m4cc2'/cell/member).resolve())
   check(cell+':events_author_source:'+member,runtime in author_sources and author_sources[runtime]==sha(raw))
   return [json.loads(line) for line in raw.splitlines()]
  coordinator=zr('c/FINAL_TIMING.json');cr=zr('c/EPISODE_RESULT.json');tools=zr('owner/TOOLS.json')['tools']
  check(cell+':coordinator_delta',coordinator['business_receipts_closed_ns']-coordinator['started_ns']==coordinator['full_episode_wall_ns'])
  check(cell+':coordinator_nested',ft['started_ns']<=coordinator['started_ns']<=coordinator['business_receipts_closed_ns']<=ft['business_receipts_closed_ns'])
  ct=[];assigned=[]
  for index,label in enumerate(TURNS,1):
   folder='c/turns/'+label+'/'
   tf=zr(folder+'FINAL_TIMING.json');c=zr(folder+'CONSUMER.json');events=ze(folder+'events.jsonl')
   name=cell+'/'+label
   check(name+':turn_delta',tf['consumer_record_closed_ns']-tf['started_ns']==tf['full_turn_wall_ns'])
   check(name+':turn_bound',ft['started_ns']<=tf['started_ns']<=tf['consumer_record_closed_ns']<=ft['business_receipts_closed_ns'])
   check(name+':turn_start_consumer',tf['started_ns']==c['started_ns'])
   check(name+':valid',tf['accepted_success'] and c['valid_completion'])
   terminal=[r['event']['usage'] for r in events if r['event'].get('type')=='turn.completed']
   check(name+':one_terminal',len(terminal)==1)
   u=terminal[0]
   check(name+':terminal_unique_record',u==c['usage'] and c['raw_usage_events']==[u] and c['usage_rows']==[u])
   check(name+':usage_fields',set(u)==set(FIELDS) and all(type(v)is int and v>=0 for v in u.values()))
   check(name+':cached_subset',u['cached_input_tokens']<=u['input_tokens'])
   check(name+':reasoning_subset',u['reasoning_output_tokens']<=u['output_tokens'])
   points=[tf['started_ns'],c['popen_ns'],c['prompt_submitted_ns'],c['final_received_ns'],c['turn_completed_ns'],c['process_exit_ns'],c['cleanup_end_ns'],tf['consumer_record_closed_ns']]
   phase_names=('input_checks_to_launch','launch_to_prompt_submitted','prompt_to_final_received','final_to_turn_completed','turn_completed_to_process_wait_return','process_wait_return_to_cleanup_and_raw_archive_end','cleanup_end_to_consumer_record_close')
   check(name+':monotone_integer_phases',all(type(v)is int for v in points) and points==sorted(points))
   phases={k:points[i+1]-points[i] for i,k in enumerate(phase_names)}
   check(name+':phase_partition',sum(phases.values())==tf['full_turn_wall_ns'])
   attempts=c['archive']['owner_attempts'];assigned.extend(attempts)
   selected=[row for row in tools if row['attempt'] in attempts]
   check(name+':attempt_mapping',len(selected)==len(attempts)==len(set(attempts)))
   intervals=[(r['started_ns'],r['started_ns']+r['elapsed_ns']) for r in selected]
   check(name+':owner_tools_prompt_final',all(c['prompt_submitted_ns']<=a<=b<=c['final_received_ns'] for a,b in intervals))
   tool_union,merged=union(intervals);raw_sum=sum(b-a for a,b in intervals)
   unresolved=c['final_received_ns']-c['prompt_submitted_ns']-tool_union
   check(name+':non_tool_partition',unresolved>=0 and unresolved+tool_union==phases['prompt_to_final_received'])
   ce=[r for r in events if r['event'].get('type')=='item.completed' and r['event'].get('item',{}).get('type')=='mcp_tool_call']
   cs=[r for r in events if r['event'].get('type')=='item.started' and r['event'].get('item',{}).get('type')=='mcp_tool_call']
   check(name+':CLI_attempt_count',len(ce)==len(selected))
   check(name+':CLI_all_completed',all(r['event']['item']['status']=='completed' and r['event']['item'].get('error') is None for r in ce))
   row={'cell':cell,'turn':label,'turn_index':index,'group':cell[0],'start_ns':tf['started_ns'],'close_ns':tf['consumer_record_closed_ns'],
        'full_ns':tf['full_turn_wall_ns'],'phases_ns':phases,'usage':sum_usage([u]),'owner_tool_attempts':len(attempts),
        'owner_tool_union_ns':tool_union,'owner_tool_raw_sum_ns':raw_sum,'owner_tool_overlap_ns':raw_sum-tool_union,
        'model_service_transport_unresolved_ns':unresolved,'CLI_last_tool_to_final_ns':c['final_received_ns']-max(r['perf_ns'] for r in ce),
        'first_sufficient_facts_ns':None,'owner_tool_intervals':intervals}
   claimed=next(r for r in author_t['turns'] if r['cell']==cell and r['turn_label']==label)
   check(name+':author_full',claimed['full_turn_wall_ns']==row['full_ns'])
   check(name+':author_phases',{p['name']:p['duration_ns'] for p in claimed['phases']}==phases)
   check(name+':author_tool_union',claimed['owner_tool_union_ns']==tool_union and claimed['owner_tool_raw_sum_ns']==raw_sum and claimed['owner_tool_overlap_ns']==raw_sum-tool_union)
   check(name+':author_unresolved',claimed['prompt_to_final_partition']['model_service_transport_unresolved_ns']==unresolved)
   check(name+':author_last_tool_marker',claimed['last_cli_tool_event_to_final_ns']==row['CLI_last_tool_to_final_ns'])
   check(name+':sufficiency_unknown_preserved',claimed['first_sufficient_facts_ns'] is None and claimed['first_sufficient_facts_to_final_ns'] is None)
   uc=next(r for r in author_u['rows'] if r['cell']==cell and r['turn']==label)
   check(name+':author_usage',uc['raw_usage']==u and uc['input_plus_output_tokens']==row['usage']['input_plus_output'])
   for k,v in phases.items():phase_totals[cell[0]][k]=phase_totals[cell[0]].get(k,0)+v
   for k,v in [('owner_tool_union_ns_nested_in_prompt_final',tool_union),('model_service_transport_unresolved_ns_nested_in_prompt_final',unresolved)]:phase_totals[cell[0]][k]=phase_totals[cell[0]].get(k,0)+v
   ct.append(row);turns.append(row)
  check(cell+':all_attempts_assigned_once',sorted(assigned)==sorted(r['attempt'] for r in tools) and len(assigned)==len(set(assigned)))
  boundaries=[ft['started_ns']]+[v for row in ct for v in (row['start_ns'],row['close_ns'])]+[ft['business_receipts_closed_ns']]
  partitions=[boundaries[i+1]-boundaries[i] for i in range(len(boundaries)-1)]
  check(cell+':full_partition',min(partitions)>=0 and sum(partitions)==ft['full_episode_wall_ns'])
  segments={'FULL':ft['full_episode_wall_ns'],'BASE':ct[0]['full_ns'],'REPEAT':ct[1]['full_ns'],'EDIT':ct[2]['full_ns'],'REPEAT_EDIT':ct[1]['full_ns']+ct[2]['full_ns']}
  admins=[zr(n) for n in z.namelist() if re_admin(n)] if False else [zr(n) for n in z.namelist() if n.startswith('ADMIN_') and n.endswith('.json') and '/' not in n]
  admin_union,_=union([(r['started_ns'],r['ended_ns']) for r in admins])
  edits=[r for r in admins if r['request']['method']=='continuity/qa_advance']
  check(cell+':one_edit_nested_between_turns',len(edits)==1 and ct[1]['close_ns']<=edits[0]['started_ns']<=edits[0]['ended_ns']<=ct[2]['start_ns'])
  ec=next(r for r in author_t['episodes'] if r['cell']==cell)
  check(cell+':author_segments',ec['segments_ns']==segments)
  check(cell+':author_partition',[r['duration_ns'] for r in ec['partition']]==partitions)
  check(cell+':author_admin_union',ec['administrative_union_ns']==admin_union)
  check(cell+':author_nested_coordinator',ec['coordinator_wall_ns_nested']==coordinator['full_episode_wall_ns'])
  epusage={'FULL':sum_usage([r['usage'] for r in ct]),'BASE':ct[0]['usage'],'REPEAT_EDIT':sum_usage([r['usage'] for r in ct[1:]])}
  episodes[cell]={'group':cell[0],'pair':int(cell[1]),'start_ns':ft['started_ns'],'close_ns':ft['business_receipts_closed_ns'],'segments_ns':segments,'usage':epusage,
                   'outside_consumer_turns_ns':sum(partitions[i] for i in (0,2,4,6)),'publication_ns':publication['closed_ns']-publication['started_ns'],
                   'publication_end_ns':publication['closed_ns'],'admin_union_ns':admin_union}
  check(cell+':publication_outside_full',publication['started_ns']>=ft['business_receipts_closed_ns'])

check('phase_totals_crosscheck',phase_totals==author_t['consumer_phase_totals_ns'])
comparisons={}
for segment in ('FULL','BASE','REPEAT','EDIT','REPEAT_EDIT'):
 ratios=[Fraction(episodes['C'+str(i)]['segments_ns'][segment],episodes['N'+str(i)]['segments_ns'][segment]) for i in (1,2,3)]
 mid=median(ratios);ns={g:sum(e['segments_ns'][segment] for e in episodes.values() if e['group']==g) for g in ('N','C')}
 claimed=author_t['aggregates'][segment]
 check(segment+':author_exact_median',Fraction(claimed['median_pair_C_over_N']['numerator'],claimed['median_pair_C_over_N']['denominator'])==mid)
 check(segment+':author_group_times',claimed['N_total_ns']==ns['N'] and claimed['C_total_ns']==ns['C'])
 comparisons[segment]={'pairs':[{'pair':i,'N_ns':episodes['N'+str(i)]['segments_ns'][segment],'C_ns':episodes['C'+str(i)]['segments_ns'][segment],'ratio':ratio(episodes['C'+str(i)]['segments_ns'][segment],episodes['N'+str(i)]['segments_ns'][segment])}for i in (1,2,3)],
                       'median_pair_C_over_N':ratio(mid.numerator,mid.denominator),'group_ns':ns,'ratio_of_group_times':ratio(ns['C'],ns['N'])}
 if segment in ('FULL','BASE','REPEAT_EDIT'):
  groupu={g:sum_usage([e['usage'][segment] for e in episodes.values() if e['group']==g]) for g in ('N','C')}
  comparisons[segment]['group_usage']=groupu
  comparisons[segment]['token_total_C_over_N']=ratio(groupu['C']['input_plus_output'],groupu['N']['input_plus_output'])
  comparisons[segment]['uncached_input_plus_output_C_over_N_diagnostic']=ratio(groupu['C']['uncached_input_plus_output_diagnostic'],groupu['N']['uncached_input_plus_output_diagnostic'])
  cu=author_u['segment_summaries'][segment]
  check(segment+':author_group_usage',cu['N_total_input_plus_output']==groupu['N']['input_plus_output'] and cu['C_total_input_plus_output']==groupu['C']['input_plus_output'])

run=read(B/'RUN_RESULT.json');reservation=read(B/'FORMAL_STARTED.json')
reservation_start=reservation.get('started_ns',reservation.get('reserved_ns'))
if reservation_start is None:reservation_start=author_t['shared_and_historical_costs']['current_batch_recorded_span']['started_ns'];check('reservation_key_missing',False)
fullsum=sum(e['segments_ns']['FULL'] for e in episodes.values())
span=run['ended_ns']-reservation_start
gaps=[episodes[ORDER[0]]['start_ns']-reservation_start]+[episodes[b]['start_ns']-episodes[a]['close_ns'] for a,b in zip(ORDER,ORDER[1:])]+[run['ended_ns']-episodes[ORDER[-1]]['close_ns']]
check('current_span_partition',span==fullsum+sum(gaps) and min(gaps)>=0)
shared=author_t['shared_and_historical_costs']
check('current_shared_span_matches',shared['current_episode_outer_sum_ns']==fullsum and shared['current_outside_episode_recorded_ns']==sum(gaps))
check('outer_publication_nested_in_shared_gaps',sum(e['publication_ns'] for e in episodes.values())==shared['current_outer_FINAL_TIMING_publication_sum_ns_nested_in_gaps'])
historical=0
for cell in ORDER:
 h=read(TREE/'verification/m4_surface_scan_continuous_consumption_001/episodes'/cell/'FINAL_TIMING.json')
 check('historical_failed_outer_delta:'+cell,h['business_receipts_closed_ns']-h['started_ns']==h['full_episode_wall_ns'])
 historical+=h['full_episode_wall_ns']
check('historical_001_sum',historical==shared['historical_001_failed_outer_sum_ns'])
check('historical_partial_sum',sum(r['reported_partial_wall_ns'] for r in shared['historical_interface_local_process_checks'])==shared['historical_interface_reported_partial_check_sum_ns'])
for k in ('project_total_investment_ns','historical_interface_total_ns','current_preparation_offline_freeze_commit_total_ns','quality_package_build_publish_ns','final_RUN_RESULT_write_close_ns'):
 check('shared_unknown:'+k,shared[k] is None)

gate_quality=seal['quality']['primary_complete_correct']==18 and seal['quality']['current_state_basis_sufficient']==18 and seal['execution']['completed_episodes']==6
gate_time=Fraction(**{k:comparisons['FULL']['median_pair_C_over_N'][k] for k in ('numerator','denominator')})<=Fraction(7,10)
gate_token=comparisons['FULL']['group_usage']['C']['input_plus_output']<=comparisons['FULL']['group_usage']['N']['input_plus_output']
check('author_overall_gate',author_ledger['gates']['overall_fixed_task']==(gate_quality and gate_time and gate_token))
check('HEAD_unchanged',subprocess.check_output(['git','-C',str(TREE),'rev-parse','HEAD'],text=True).strip()==head)
result={'fixed_cost_delivery':head,'original_delivery':seal['delivery_commit'],'quality_seal_sha256':sha(sealraw),
        'episodes':episodes,'turns':turns,'comparisons':comparisons,'phase_totals_ns':phase_totals,
        'shared_measured':{'batch_span_ns':span,'episode_outer_sum_ns':fullsum,'outside_episode_ns':sum(gaps),'historical_001_failed_outer_sum_ns':historical,
                           'historical_interface_partial_reported_ns':shared['historical_interface_reported_partial_check_sum_ns'],
                           'scope':'Historical interface partial sum arithmetic only; source process histories reused, not reexecuted.'},
        'gates':{'quality':gate_quality,'time':gate_time,'token':gate_token,'overall':gate_quality and gate_time and gate_token},
        'checks':len(CHECKS),'passed':all(r['passed'] for r in CHECKS),'failed_checks':[r for r in CHECKS if not r['passed']],
        'limits':['Only this fixed task, three paired episodes; no independent retention ablation.',
                  'Non-tool residual combines model/service/transport; first sufficient facts stays unknown.',
                  'Uncached-input-plus-output is diagnostic, not cost or a replacement gate.',
                  'Usage scope and sealed quality reused by hash; no session rollout re-read or quality rescore.',
                  'Actual fees, provider retry coverage, whole project labor/preparation, and thin EXIT remain unknown.']}
for name,value in [('RESULTS.json',result),('CHECKS.json',CHECKS),('INPUT_HASHES.json',INPUTS)]:
 (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'checks':len(CHECKS),'passed':result['passed'],'gates':result['gates'],'FULL':comparisons['FULL'],'REPEAT_EDIT':comparisons['REPEAT_EDIT'],'failed_checks':result['failed_checks']},ensure_ascii=False))
