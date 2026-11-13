"""Independent raw-event mechanism review. No product/checker execution."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,re,subprocess

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE=ROOT/'verification/m4_surface_scan_compact_consumption_001'
OUT=Path(__file__).resolve().parent
HASHES={};CHECKS=[]
NUM=r'[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?'
EPS=F('0.000500001')

def read(p):
 d=p.read_bytes();HASHES[str(p)]={'bytes':len(d),'sha256':hashlib.sha256(d).hexdigest()};return d
def obj(p):return json.loads(read(p))
def check(name,ok):
 CHECKS.append({'name':name,'passed':bool(ok)})
 if not ok:raise AssertionError(name)
def enc(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def nested(v):
 yield v
 if isinstance(v,dict):
  for x in v.values():yield from nested(x)
 elif isinstance(v,list):
  for x in v:yield from nested(x)
 elif isinstance(v,str) and v.lstrip().startswith(('{','[')):
  try:y=json.loads(v)
  except ValueError:return
  yield from nested(y)
def extract(result):
 scans=[];stdout=[]
 for node in nested(result):
  if isinstance(node,dict):
   if node.get('result_kind')=='surface_scan':scans.append(node)
   if node.get('executed') is True and isinstance(node.get('result'),str):stdout.append(node['result'])
 return scans,stdout
def scanrows(scan):
 if scan.get('display_encoding'):
  rows=[dict(zip(scan['match_columns'],r)) for r in scan['matches']]
  return [(tuple(sorted([r['object_a'],r['object_b']])),F(r['distance_m'])*1000) for r in rows]
 return [(tuple(sorted([r['objects'][0]['name'],r['objects'][1]['name']])),F(r['distance_m'])*1000) for r in scan['matches']]
def stdoutrows(s):
 return [(tuple(sorted([a,b])),F(d)) for a,b,d in re.findall(r'^(Obj_\d{3})\s+(Obj_\d{3})\s+('+NUM+r')(?:\s|$)',s,re.M)]
def valid(rows,truth):
 chosen=[(p,d) for p,d in rows if d<=2]
 return (len(chosen)==len(set(p for p,d in chosen))==71 and set(p for p,d in chosen)==set(truth)
  and all((max(F(0),d-EPS)/1000)**2<=truth[p]<=((d+EPS)/1000)**2 for p,d in chosen))
def union_duration(intervals):
 end=total=0
 for a,b in sorted(intervals):
  total+=max(0,b-max(a,end));end=max(end,b)
 return total

def main():
 head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD']).decode().strip()
 check('fixed_delivery',head=='e089a7ba42c276b6f537b62c1a0a4f037fdaec6d')
 truthdoc=obj(BASE/'quality/public/scoring/TRUTH.json')
 truth={tuple(sorted([p['object_a'],p['object_b']])):F(int(p['exact_squared_distance_m2']['numerator']),int(p['exact_squared_distance_m2']['denominator'])) for p in truthdoc['pairs'] if p['matches_threshold']}
 rows=[];raw={}
 for cell in ('N1','O1','C1','O2','C2','N2','C3','N3','O3'):
  folder=BASE/'cells'/cell
  consumer=obj(folder/'CONSUMER.json');events=[json.loads(x) for x in read(folder/'events.jsonl').decode('utf8').splitlines()]
  final=read(folder/'PUBLIC_FINAL.txt').decode('utf8')
  starts={e['event']['item']['id']:e['perf_ns'] for e in events if e['event']['type']=='item.started' and e['event'].get('item',{}).get('type')=='mcp_tool_call'}
  done=[e for e in events if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='mcp_tool_call']
  finals=[e for e in events if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='agent_message' and e['event']['item'].get('text')==final]
  check(cell+'.final_bound',len(finals)==1 and finals[0]['perf_ns']==consumer['final_received_ns'])
  final_ns=finals[0]['perf_ns'];tools=[];first=None;raw[cell]=[]
  for number,event in enumerate(done,1):
   item=event['event']['item'];toolpath=folder/'owner'/f'tool_{number:02d}'
   request=obj(toolpath/'REQUEST.json');response=obj(toolpath/'RESPONSE.json')
   check(cell+f'.tool{number}.arguments',request['params']['arguments']==item['arguments'])
   check(cell+f'.tool{number}.content',enc(response['result']['content'])==enc(item['result']['content']))
   scans,stdout=extract(item['result']);allrows=[]
   for scan in scans:allrows.extend(scanrows(scan))
   for s in stdout:allrows.extend(stdoutrows(s))
   complete=valid(allrows,truth)
   if complete and first is None:first=(number,event['perf_ns'])
   textbytes=sum(len(c.get('text','').encode('utf8')) for c in item['result']['content'])
   args=item['arguments'];code=args.get('code')
   raw[cell].append({'scans':scans,'stdout':stdout,'code':code,'rows':allrows})
   tools.append({'number':number,'tool':item['tool'],'response_detail':args.get('response_detail','omitted'),
                 'start_ns':starts[item['id']],'complete_ns':event['perf_ns'],
                 'interval_s':(event['perf_ns']-starts[item['id']])/1e9,
                 'text_bytes':textbytes,'full_task_pairs_correct':complete,
                 'is_error':response['result'].get('isError'),
                 'code_sha256':hashlib.sha256(code.encode('utf8')).hexdigest() if code else None})
  check(cell+'.first_sufficient_found',first is not None)
  post=union_duration([(max(first[1],t['start_ns']),min(final_ns,t['complete_ns'])) for t in tools if t['complete_ns']>first[1] and t['start_ns']<final_ns])
  span=final_ns-first[1]
  comments=[e['event']['item']['text'] for e in events if e['event']['type']=='item.completed' and e['event'].get('item',{}).get('type')=='agent_message' and e['event']['item'].get('text')!=final]
  rows.append({'cell':cell,'execution_status':consumer['status'],'valid_completion':consumer['valid_completion'],
               'first_sufficient_tool':first[0],'first_sufficient_cli_ns':first[1],'final_cli_ns':final_ns,
               'prompt_to_first_sufficient_s':(first[1]-consumer['prompt_submitted_ns'])/1e9,
               'first_sufficient_to_final_s':span/1e9,'post_sufficient_tool_s':post/1e9,
               'post_sufficient_non_tool_s':(span-post)/1e9,'tools':tools,'earlier_public_messages':comments,
               'provider_requests_observed':consumer['provider_requests'] is not None,
               'explicit_output_limit_or_truncation_argv':any('tool_output_limit' in a or 'truncat' in a for a in consumer['argv'])})
  if cell.startswith('C'):
   check(cell+'.single_explicit_brief',len(tools)==1 and tools[0]['response_detail']=='brief' and tools[0]['text_bytes']==7911)
   check(cell+'.no_native',all(t['tool']!='execute_blender_code' for t in tools))
  if cell.startswith('O'):
   firstscan,secondscan=raw[cell][0]['scans'][0],raw[cell][1]['scans'][0]
   check(cell+'.old_full_and_brief_34754',tools[0]['text_bytes']==tools[1]['text_bytes']==34754)
   check(cell+'.same_except_trace',enc({k:v for k,v in firstscan.items() if k!='trace_id'})==enc({k:v for k,v in secondscan.items() if k!='trace_id'}))
   check(cell+'.two_receipts_then_native',tools[1]['response_detail']=='brief' and all(t['tool']=='execute_blender_code' for t in tools[2:]))
   for i in range(2,len(raw[cell])):
    code=raw[cell][i]['code']
    (OUT/f'{cell}_tool{i+1:02d}_CODE.txt').write_text(code,encoding='utf8')
  for i,entry in enumerate(raw[cell]):
   if entry['code'] and cell.startswith('N'):
    (OUT/f'{cell}_tool{i+1:02d}_CODE.txt').write_text(entry['code'],encoding='utf8')
 check('tool_denominator_27',sum(len(r['tools']) for r in rows)==27)
 error=raw['O3'][3]['rows'];fixed=raw['O3'][4]['rows'];reference=dict(scanrows(raw['O3'][0]['scans'][0]))
 missing=sorted(set(truth)-set(p for p,d in error if d<=2))
 wrong=[{'pair':p,'intermediate_mm':float(d),'scan_mm':float(reference[p])} for p,d in error if p in reference and abs(d-reference[p])>EPS]
 check('O3_missing_pair',missing==[('Obj_010','Obj_022')])
 check('O3_wrong_two',len(wrong)==2)
 check('O3_correction_full',valid(fixed,truth))
 correction={'missing':missing,'wrong':wrong,
             'max_corrected_vs_scan_mm':float(max(abs(d-reference[p]) for p,d in fixed)),
             'error_to_corrected_receipt_s':(rows[-1]['tools'][4]['complete_ns']-rows[-1]['tools'][3]['complete_ns'])/1e9,
             'correction_tool_s':rows[-1]['tools'][4]['interval_s']}
 # Hash the exact current runtime files reviewed for the architectural proposal.
 for name in ('surface_scan.py','scene_residency.py','read_context.py','scene_cache.py','live_service.py','blender_host.py','blender_mcp_host.py','blender_process.py','live_spatial_mcp.py','task_query.py'):
  read(ROOT/'human_eye_plugin'/name)
 read(Path('D:/hefe/docs/GLOBAL_SCAN_CAPABILITY_AND_OPTIMIZATION_REVIEW_20261112.md'))
 read(Path(__file__))
 result={'fixed_delivery':head,'rows':rows,'O3_correction':correction,
         'limits':['CLI receipt does not prove provider-rendered input','Non-tool interval is not pure reasoning',
                   'Schema and representation changed together','No new model or product execution']}
 for name,value in [('RESULTS.json',result),('CHECKS.json',CHECKS),('INPUT_SHA256.json',HASHES)]:
  (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'checks':len(CHECKS),'passed':sum(c['passed'] for c in CHECKS),
  'rows':[{k:v for k,v in r.items() if k not in ('tools','earlier_public_messages')} for r in rows],
  'O3_correction':correction},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
