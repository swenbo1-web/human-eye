"""Independent stdlib-only identity and cost review; never imports product or scorer."""
import ast
import base64
import collections
import hashlib
import json
import subprocess
from pathlib import Path

REPO=Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe')
PREFIX='verification/m4_complete_witness_consumption_001/'
BASE=REPO/PREFIX
RUNTIME=Path('D:/he_complete_witness_001')
INSTALL=Path('D:/he_view_reuse_001/product')
OUT=Path(__file__).resolve().parent
FINAL='8baad59ac6da01f14e1eb87c3e1f4f0687eb2b7d'
START='a9dd9490d1817630e090975362591ce232d881ae'
PRODUCT='d12c7ab248452ff253452007d0635f2d662f0191'
inputs={}; groups=collections.defaultdict(lambda: {'checks':0,'passed':0,'failed':0}); failures=[]

def digest(raw):return hashlib.sha256(raw).hexdigest()
def read(path):
    path=Path(path);data=path.read_bytes()
    inputs[str(path)]={'path':str(path),'bytes':len(data),'sha256':digest(data)}
    return data
def sha(path):
    path=Path(path); h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    value=h.hexdigest();inputs[str(path)]={'path':str(path),'bytes':path.stat().st_size,'sha256':value}
    return value
def load(path):return json.loads(read(path).decode('utf-8-sig'))
def check(group,name,value):
    groups[group]['checks']+=1;groups[group]['passed' if value else 'failed']+=1
    if not value:failures.append({'group':group,'name':name})
def git(*args):return subprocess.check_output(['git','-C',str(REPO),*args])

manifest=load(BASE/'CONTENT_MANIFEST.json'); frozen=load(BASE/'FROZEN.json')
seal=load(BASE/'admin/QUALITY_SEAL.json'); archive=load(BASE/'RUNTIME_ARCHIVE.json'); baseline=load(BASE/'BASELINE.json')
check('git','head',git('rev-parse','HEAD').decode().strip()==FINAL)
check('git','clean',not git('status','--porcelain'))
changed=git('diff','--name-only',START,FINAL).decode().splitlines()
expected={x['path'] for x in manifest['files']}|{PREFIX+'CONTENT_MANIFEST.json'}
check('git','exact_change_paths',set(changed)==expected and len(changed)==202 and all(x.startswith(PREFIX) for x in changed))
for commit in (START,'4de44716cdee6f8c7669c3c59f866206df3a1f41','64d79a64b3eb13b4ff42e78de1e955f6a19ee88c'):
    check('git','ancestor:'+commit,subprocess.run(['git','-C',str(REPO),'merge-base','--is-ancestor',commit,FINAL],capture_output=True).returncode==0)
for relative in changed:
    raw=read(REPO/relative)
    check('git_blob',relative,git('show',FINAL+':'+relative)==raw)
for row in manifest['files']:
    raw=read(REPO/row['path'])
    check('manifest',row['path'],len(raw)==row['bytes'] and digest(raw)==row['sha256'])
check('manifest','count',len(manifest['files'])==manifest['file_count']==201)
for name, rows in [('frozen',frozen['files_sha256']),('quality_seal',seal['files_sha256'])]:
    for path,value in rows.items():check(name,path,sha(path)==value)
check('frozen','count',len(frozen['files_sha256'])==2216)
check('quality_seal','count',len(seal['files_sha256'])==191)
for row in archive['files']:
    original=read(row['original_path']);copy=read(BASE/row['archive_path'])
    check('archive',row['relative_path'],original==copy and len(original)==row['bytes'] and digest(original)==row['sha256'])
check('archive','count_bytes',len(archive['files'])==136 and sum(x['bytes'] for x in archive['files'])==1572334)
check('archive','runtime_file_set', {str(p.relative_to(RUNTIME)).replace('\\','/') for p in RUNTIME.rglob('*') if p.is_file()}=={x['relative_path'].replace('\\','/') for x in archive['files']})

source_manifest=[]
for row in baseline['source_manifest']:
    source=read(REPO/row['path']); installed=read(INSTALL/row['path'])
    check('product_source',row['path'],source==installed==git('show',PRODUCT+':'+row['path']) and digest(source)==row['sha256'])
    source_manifest.append({'path':row['path'],'sha256':digest(source)})
tree=ast.parse(read(INSTALL/'human_eye_plugin/runtime_identity.py').decode('utf-8'))
constants={}
for node in tree.body:
    if isinstance(node,ast.Assign):
        for target in node.targets:
            if isinstance(target,ast.Name) and target.id in ('BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES'):
                constants[target.id]=ast.literal_eval(node.value)
enumerated=set(constants['_ROOT_MODULES'])
for pkg in ('human_eye_plugin','human_eye_module1_operators'):
    enumerated.update(pkg+'/'+p.name for p in (INSTALL/pkg).glob('*.py'))
check('product_source','enumeration',len(source_manifest)==141 and enumerated=={x['path'] for x in source_manifest})
source_digest=digest(json.dumps({'base_version':constants['BASE_VERSION'],'implementation_revision':constants['IMPLEMENTATION_REVISION'],'files':sorted(source_manifest,key=lambda x:x['path'])},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
check('product_source','digest',source_digest=='d8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02')

quality=load(BASE/'admin/QUALITY.json')
check('scorer_failure','original_hash',sha(BASE/'admin/QUALITY.json')=='272f925f1f46b4140b7483fbeceb1ff0a2b58285d3b5c9cab6c417cbb6cb3a87')
check('scorer_failure','original_false_null',quality['final_quality_passed'] is False and quality['direct_product_adoption'] is None and quality['denominator']==1)
check('scorer_failure','preserved_error','execution_state' in str(quality['errors']))
run=load(RUNTIME/'formal/RUN_RESULT.json'); route=run['records'][0]
check('lifecycle','one_route',len(run['records'])==run['actual_routes']==run['actual_CLI_processes']==1 and run['outer_retries']==0)
check('scorer_failure','actual_field_location',run['execution_state']=='completed' and 'execution_state' not in route)
check('lifecycle','terminal',run['launcher_succeeded'] and not run['terminal_errors'] and route['outer_valid_completion'] and route['consumer_valid_completion'] and route['turn_terminal_event_seen'])
check('lifecycle','no_slot_timing','slot_timing' not in route and not list(RUNTIME.glob('**/SLOT_TIMING.json')))
launch=load(RUNTIME/'formal/LAUNCH_TIMING.json');timing=load(RUNTIME/'formal/P1/FINAL_TIMING.json');q=load(RUNTIME/'preparation/Q1/QUALIFICATION_RUN.json')
check('timing','route_subtraction',timing['elapsed_ns']==timing['result_closed_ns']-timing['started_ns']==62845182500)
check('timing','launch_subtraction',launch['elapsed_ns']==launch['launch_results_closed_ns']-launch['started_ns']==64549834500)
check('timing','nested_route_wrapper',launch['route_elapsed_ns']==launch['route_closed_ns']-launch['route_started_ns'] and launch['started_ns']<=launch['route_started_ns']<=timing['started_ns']<timing['result_closed_ns']<=launch['route_closed_ns']<=launch['launch_results_closed_ns'])
check('timing','original_450s_deadline',timing['original_deadline_ns']-timing['started_ns']==450*10**9 and route['deadline_ns']==timing['original_deadline_ns'])
check('timing','qualification_subtraction',q['elapsed_ns']==q['closed_ns']-q['started_ns']==2723434900)
check('lifecycle','qualification_once_zero_model',q['actual_model_calls']==0 and q['actual_product_calls']==1 and q['actual_business_tools']==1 and q['outer_retries']==0 and q['passed'] and not q['errors'])
consumer=load(RUNTIME/'formal/P1/c/CONSUMER.json')
check('lifecycle','different_pids',len({q['actor_pid'],route['owner_pid'],route['consumer_pid'],route['runtime_binding']['runtime_pid']})==4)
for label,row in [('qualification',q['process_cleanup']),('actor',route['owner_process_cleanup']),('CLI',route['consumer_process_cleanup'])]:
    check('lifecycle',label+'_closed',row['confirmed'] is True and row['exit_code']==0 and row['process_handle_closed'] and row['reaped'] and not row['kill_requested'] and not row['errors'])
check('lifecycle','held_thin_exit',route['runtime_binding']['confirmed'] is True and route['runtime_exit']['confirmed'] is True and route['runtime_exit']['exited'] is True and route['runtime_exit']['handle_closed'] is True and route['runtime_exit']['exit_code']==1)
check('lifecycle','thin_missing_receipt_preserved',route['bridge_cleanup']['missing_exit_count']==1 and route['bridge_cleanup']['receipt_status']=='unknown')

raw_lines=read(RUNTIME/'formal/P1/c/stdout.raw.bin').splitlines()
raw_events=[json.loads(line) for line in raw_lines if line.strip()]
event_rows=[json.loads(line) for line in read(RUNTIME/'formal/P1/c/events.jsonl').splitlines() if line.strip()]
check('consumer','event_count',len(raw_events)==len(event_rows))
for index,(line,raw,row) in enumerate(zip(raw_lines,raw_events,event_rows)):
    public=row['event']; redacted=raw.get('item',{}).get('type')=='reasoning'
    ok=(public.get('raw_sha256')==digest(line) and public.get('raw_bytes')==len(line) and public.get('item',{}).get('redacted') is True) if redacted else public==raw
    check('consumer','raw_event:'+str(index),ok)
usages=[x['usage'] for x in raw_events if x.get('type')=='turn.completed']
check('consumer','one_usage',len(usages)==1)
usage=usages[0]
check('consumer','raw_usage',usage==consumer['usage'] and usage['input_tokens']==42627 and usage['output_tokens']==1331 and usage['cached_input_tokens']==28160 and usage['reasoning_output_tokens']==20)
tools=[x['item'] for x in raw_events if x.get('type')=='item.completed' and x.get('item',{}).get('type')=='mcp_tool_call']
check('consumer','three_tools',[x['tool'] for x in tools]==['active_observation','execute_python','execute_python'])
images=[];text_bytes=0
for tool in tools:
    for item in tool['result']['content']:
        if item['type']=='image':images.append(base64.b64decode(item['data'],validate=True))
        elif item['type']=='text':text_bytes+=len(item['text'].encode('utf-8'))
check('consumer','actual_images',len(images)==2 and sum(map(len,images))==5127)
metrics=load(RUNTIME/'formal/P1/o/METRICS.json')
check('consumer','metrics_images',metrics['server_socket_sent_image_blocks']==2 and metrics['server_socket_sent_PNG_bytes']==5127)
check('consumer','text_bytes',metrics['server_socket_sent_text_UTF8_bytes']==text_bytes)
receipts=[];wire_bytes=0
for folder in sorted((RUNTIME/'formal/P1/o').glob('tool_*')):
    rec=load(folder/'RECEIPT.json');receipts.append(rec)
    response=load(folder/'RESPONSE.json')
    check('consumer',folder.name+'_completed',not rec['is_error'] and rec['response_serialization_error'] is None and rec['elapsed_ns']==rec['closed_ns']-rec['started_ns'])
    wire_files=list(folder.glob('*'))
transport=load(RUNTIME/'formal/P1/o/TRANSPORT.json') if (RUNTIME/'formal/P1/o/TRANSPORT.json').exists() else None
observations=load(RUNTIME/'formal/P1/o/OBSERVATIONS.json')
check('cache','TOP_hit_only',len(observations['cache_requests'])==1 and observations['cache_requests'][0]['names']==['TOP'] and observations['cache_requests'][0]['new_raster_attempts']==0 and observations['cache_requests'][0]['frames'][0]['cached'] is True)
intents=[load(p) for p in sorted((RUNTIME/'raster_budget').glob('*/INTENT.json'))]
counts=collections.Counter(x['phase'] for x in intents)
check('raster','four_intents',len(intents)==4 and counts=={'preparation':2,'formal':2})
check('raster','global_sequence',[x['global_attempt'] for x in intents]==[1,2,3,4])
check('raster','product_origin',all(x['origin']=='product' for x in intents))
check('raster','two_each_observations',metrics['common']['render_attempts']==2 and q['actual_rasters']==2 and route['new_renders']==2)
check('ordering','quality_before_cost_no_rewrite',seal['cost_analysis_performed_before_seal'] is False and seal['automatic_formal_quality_passed'] is False and seal['automatic_direct_product_adoption'] is None)

summary={'new_product_model_Blender_raster_calls':0,'fixed_commit':FINAL,'changed_paths':len(changed),'frozen_paths':len(frozen['files_sha256']),'quality_seal_files':len(seal['files_sha256']),'archive_files':len(archive['files']),'archive_bytes':sum(x['bytes'] for x in archive['files']),'product_sources':len(source_manifest),'product_source_digest':source_digest,'qualification_seconds':q['elapsed_ns']/1e9,'formal_route_seconds':timing['elapsed_ns']/1e9,'formal_launch_seconds':launch['elapsed_ns']/1e9,'wrapper_route_call_seconds':launch['route_elapsed_ns']/1e9,'slot_timing':None,'usage':usage,'raw_input_plus_output':usage['input_tokens']+usage['output_tokens'],'business_tools':len(tools),'actual_images':len(images),'PNG_bytes':sum(map(len,images)),'text_UTF8_bytes':text_bytes,'actual_rasters':dict(counts),'TOP_repeat_new_rasters':0,'formal_tool_handler_seconds':sum(x['elapsed_ns'] for x in receipts)/1e9,'cash_image_tokens_provider_requests':'unmeasured','official_automated_quality':'failed_before_content_checks','manual_quality':'separate_semantics_reviewer_scope','PID':{'Q_actor':q['actor_pid'],'F_actor':route['owner_pid'],'CLI':route['consumer_pid'],'thin':route['runtime_binding']['runtime_pid']}}
result={'method':'Independent stdlib/hash/git/raw CLI and receipt review; no product/scorer/launcher imports','summary':summary,'groups':dict(groups),'checks':sum(x['checks'] for x in groups.values()),'failures':failures,'all_passed':not failures}
(OUT/'INPUTS.json').write_text(json.dumps(list(inputs.values()),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'checks':result['checks'],'failed':len(failures),'summary':summary},ensure_ascii=False))
if failures:print(json.dumps(failures,ensure_ascii=False));raise SystemExit(1)
