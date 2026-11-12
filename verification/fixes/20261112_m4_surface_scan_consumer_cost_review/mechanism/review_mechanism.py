from pathlib import Path
from fractions import Fraction as F
import ast,copy,hashlib,json,re,subprocess

R=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B=R/'verification/m4_surface_scan_consumption_001'
OUT=Path(__file__).resolve().parent
SOURCES={}; CHECKS=[]
def read(p):
 d=p.read_bytes();SOURCES[p.relative_to(R).as_posix()]={'bytes':len(d),'sha256':hashlib.sha256(d).hexdigest()};return d
def obj(p):return json.loads(read(p))
def ck(name,passed):
 CHECKS.append({'name':name,'passed':bool(passed)})
 if not passed:
  (OUT/'FAILED.json').write_text(json.dumps(CHECKS,indent=2),encoding='utf8');raise AssertionError(name)
def encode(x):return json.dumps(x,ensure_ascii=False,allow_nan=False,separators=(',',':'))
truth=obj(B/'runtime/handoff_01/public/scoring/TRUTH.json')
truth2={(p['object_a'],p['object_b']):F(int(p['exact_squared_distance_m2']['numerator']),int(p['exact_squared_distance_m2']['denominator'])) for p in truth['pairs'] if p['matches_threshold']}

def numeric_rows(text):
 rows=[]
 for line in text.splitlines():
  m=re.match(r'^(Obj_\d{3})\s+(Obj_\d{3})\s+([+\-\deE.]+)(?:\s|$)',line)
  if m:rows.append((tuple(sorted(m.group(1,2))),F(m.group(3))))
 return rows
def exact_ok(rows):
 if len(rows)!=71 or set(p for p,d in rows)!=set(truth2):return False
 eps=F('0.000500001')
 return all((max(F(0),d-eps)/1000)**2<=truth2[p]<=((d+eps)/1000)**2 for p,d in rows)

def project(value):
 # One offline readable-table candidate, not a product or new API.
 result={k:copy.deepcopy(v) for k,v in value.items() if k!='matches'}
 ids={};objects=[];rows=[]
 for match in value['matches']:
  refs=[]
  for o in match['objects']:
   if o['id'] not in ids:
    ids[o['id']]=len(objects);objects.append(copy.deepcopy(o))
   else:assert objects[ids[o['id']]]==o
   refs.append(ids[o['id']])
  d=match['distance_m']
  rows.append([match['objects'][0]['name'],match['objects'][1]['name'],*refs,d,d*1000.0])
 result['display_encoding']='surface-scan-task-table-v1-probe'
 result['objects']=objects
 result['object_reference']='zero_based_index_in_objects; scoped_to_this_result_binding'
 result['match_columns']=['object_a','object_b','object_a_ref','object_b_ref','distance_m','distance_mm']
 result['matches']=rows
 result['distance_mm_semantics']='derived_display_only; threshold_membership_uses_original_distance_m'
 result['detail']='response_detail=full requests a new current observation with witnesses; compare binding before combining'
 return result

allrows=[]
for cell in ['N1','P1','P2','N2','N3','P3']:
 folder=B/'cells'/cell
 consumer=obj(folder/'CONSUMER.json')
 events=[json.loads(line) for line in read(folder/'events.jsonl').decode('utf8').splitlines()]
 started={e['event']['item']['id']:e['perf_ns'] for e in events if e['event']['type']=='item.started' and e['event'].get('item',{}).get('type')=='mcp_tool_call'}
 completed=[e for e in events if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='mcp_tool_call']
 ck(cell+'_attempt_count',len(completed)==len(list((folder/'owner').glob('tool_*'))))
 ck(cell+'_no_explicit_truncation_configuration',not any('tool_output_limit' in s or 'truncat' in s for s in consumer['argv']))
 ck(cell+'_provider_requests_unrecorded',consumer['provider_requests'] is None)
 # Read actual thin frames, indexed by content (not by assumed RPC IDs).
 thin={}
 for p in (folder/'attachments').rglob('RX.bin'):
  x=obj(p)
  if isinstance(x.get('result'),dict) and 'content' in x['result']:
   thin.setdefault(encode(x['result']['content']),[]).append(p.relative_to(R).as_posix())
 product={}
 for p in (folder/'owner/plugin').rglob('RX.bin'):
  x=obj(p)
  if isinstance(x.get('result'),dict) and 'content' in x['result']:
   product.setdefault(encode(x['result']['content']),[]).append(p.relative_to(R).as_posix())
 attempts=[];first=None;first_scan=None
 for n,event in enumerate(completed,1):
  item=event['event']['item'];req=obj(folder/'owner'/f'tool_{n:02d}'/'REQUEST.json');resp=obj(folder/'owner'/f'tool_{n:02d}'/'RESPONSE.json')
  ck(f'{cell}_{n}_request',req['params']['arguments']==item['arguments'] and req['params']['name']==item['tool'])
  content=resp['result']['content'];ck(f'{cell}_{n}_owner_cli_equal',content==item['result']['content'])
  ck(f'{cell}_{n}_thin_cli_equal',encode(content) in thin)
  text=''.join(p['text'] for p in content if p.get('type')=='text')
  payload=json.loads(text)
  scan=payload.get('result_kind')=='surface_scan'
  sufficient=False;probe=None
  if scan:
   ck(f'{cell}_{n}_product_cli_equal',encode(content) in product)
   ck(f'{cell}_{n}_scan_bytes',len(text.encode())==34754)
   matches=payload['matches'];ck(f'{cell}_{n}_71',len(matches)==71)
   rownums=[(tuple(sorted(o['name'] for o in m['objects'])),F(m['distance_m'])*1000) for m in matches]
   sufficient=exact_ok(rownums)
   ck(f'{cell}_{n}_scan_complete',sufficient and payload['coverage']['total_pairs']==276 and payload['coverage']['unknown']==0 and payload['delivery']['complete'])
   if first_scan is None:first_scan=payload
   else:
    ck(f'{cell}_{n}_explicit_brief',item['arguments']['response_detail']=='brief')
    ck(f'{cell}_{n}_same_except_trace', {k:v for k,v in payload.items() if k!='trace_id'}=={k:v for k,v in first_scan.items() if k!='trace_id'})
   projected=project(payload);encoded=encode(projected)
   for i,m in enumerate(matches):
    row=projected['matches'][i]
    ck(f'{cell}_{n}_projection_{i}',[projected['objects'][row[2]],projected['objects'][row[3]]]==m['objects'] and row[:2]==[o['name'] for o in m['objects']] and row[4]==m['distance_m'] and row[5]==m['distance_m']*1000)
   ck(f'{cell}_{n}_all_top_level_fields',{k:v for k,v in projected.items() if k in payload and k!='matches'}=={k:v for k,v in payload.items() if k!='matches'})
   probe={'bytes':len(encoded.encode()),'full_bytes':len(text.encode()),'object_refs':len(projected['objects']),'rows':len(projected['matches']),'saving_fraction':1-len(encoded.encode())/len(text.encode())}
   if cell=='P1' and n==1:(OUT/'CANDIDATE_LAYOUT_PROBE.json').write_text(encoded+'\n',encoding='utf8')
  else:
   stdout=payload.get('result',{}).get('result','') if isinstance(payload.get('result'),dict) else ''
   sufficient=exact_ok(numeric_rows(stdout))
  if sufficient and first is None:first=n
  attempts.append({'order':n,'tool':item['tool'],'arguments':item['arguments'] if item['tool']!='execute_blender_code' else {'code_sha256':hashlib.sha256(item['arguments']['code'].encode()).hexdigest()},'status':item['status'],'started_ns':started[item['id']],'completed_ns':event['perf_ns'],'tool_ns':event['perf_ns']-started[item['id']],'complete_numeric_rows_at_cli':sufficient,'text_bytes':len(text.encode()),'probe':probe})
 ck(cell+'_first_complete',first is not None)
 start=consumer['prompt_submitted_ns'];split=attempts[first-1]['completed_ns'];end=consumer['final_received_ns']
 later=sum(a['tool_ns'] for a in attempts[first:])
 messages=[e['event']['item']['text'] for e in events if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='agent_message']
 allrows.append({'cell':cell,'first_complete_attempt':first,'prompt_to_first_ns':split-start,'first_to_final_ns':end-split,'later_tool_ns':later,'non_tool_tail_ns':end-split-later,'truncation_self_reports':[m for m in messages if '截断' in m or 'truncat' in m.lower()],'attempts':attempts,'model_rendered_input':'unmeasured'})

source=read(R/'human_eye_plugin/live_spatial_mcp.py').decode('utf-8-sig')
tree=ast.parse(source);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_tool_result')
early=next(n for n in fn.body if isinstance(n,ast.If) and 'surface_scan' in ast.unparse(n.test))
brief=next(n for n in fn.body if isinstance(n,ast.If) and "response_detail == 'brief'" in ast.unparse(n.test))
ck('early_return_precedes_brief',early.lineno<brief.lineno and any(isinstance(n,ast.Return) for n in ast.walk(early)))
result={'independent_checks':len(CHECKS),'cells':allrows,'early_return_line':early.lineno,'brief_line':brief.lineno,'new_Blender_model_API_runs':0,'single_layout_probe_only':True,'not_claimed':['provider truncation proved','model saw every character','token/time/cost savings from bytes','historical detail retrieval'],'config_truncation':'No explicit truncation setting in actual six argv; internal CLI/provider defaults unobserved'}
for name,x in [('RESULTS.json',result),('CHECKS.json',CHECKS),('SOURCES.json',SOURCES)]:
 (OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'checks':len(CHECKS),'times':[ {k:v for k,v in c.items() if k not in ['attempts','truncation_self_reports']} for c in allrows],'probe':[a['probe'] for c in allrows for a in c['attempts'] if a['probe']][:1]},ensure_ascii=False))
