"""Independent saved-record cost audit. No product imports or executions."""
import ast, base64, hashlib, io, json, math, re, struct, zipfile
from pathlib import Path

R=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=R/'verification/m4_consumable_observation_001'
F=Path('D:/he_consume_001/formal'); S=F/'P1'; O=Path(__file__).parent
inputs={}; checks=[]
def raw(p):
    p=Path(p); b=p.read_bytes(); inputs[str(p)]=hashlib.sha256(b).hexdigest(); return b
def js(p): return json.loads(raw(p))
def ck(name,ok): checks.append({'name':name,'passed':bool(ok)})
def sec(ns): return ns/1e9
def interval(x,start,end,stored):
    v=x[end]-x[start]; ck(stored+'_identity',v==x[stored]); return v

parent=js(H/'FORMAL_PROCESS.json'); launch=js(F/'LAUNCH_TIMING.json')
lr=js(F/'LAUNCH_RESULT.json'); route=js(S/'FINAL_TIMING.json'); consumer=js(S/'c/FINAL_TIMING.json')
rr=js(S/'RESULT.json'); cr=js(S/'c/CONSUMER.json'); obs=js(S/'o/OBSERVATIONS.json')
cost=js(H/'COST.json'); qi=js(H/'QUALITY_SEAL.json')
times={'parent':interval(parent,'started_ns','closed_ns','elapsed_ns'),
       'launch':interval(launch,'started_ns','launch_results_closed_ns','elapsed_ns'),
       'route':interval(route,'started_ns','result_closed_ns','elapsed_ns'),
       'consumer':interval(consumer,'started_ns','consumer_record_closed_ns','full_turn_wall_ns')}
for name,n in times.items():ck('cost_clock:'+name,cost['time']['saved_nested_intervals'][name]['elapsed_ns']==n)
ck('nested_starts',parent['started_ns']<=launch['started_ns']<=route['started_ns']<=consumer['started_ns'])
ck('nested_ends',consumer['consumer_record_closed_ns']<=route['result_closed_ns']<=launch['launch_results_closed_ns']<=parent['closed_ns'])
ck('deadline_450s',route['original_deadline_ns']-route['started_ns']==450_000_000_000)
ck('deadline_not_extended',rr['deadline_ns']==consumer['original_turn_deadline_ns']==cr['deadline_ns']==route['original_deadline_ns'])
ck('route_within_deadline',route['result_closed_ns']<route['original_deadline_ns'])
wrapper=launch['route_closed_ns']-launch['route_started_ns']
ck('wrapper_exact',wrapper==launch['route_elapsed_ns'] and wrapper-times['route']==643800)
raw_events=[]
for line in raw(S/'c/stdout.raw.bin').splitlines():
    if line.strip():raw_events.append(json.loads(line))
usage=[x['usage'] for x in raw_events if x.get('type')=='turn.completed' and 'usage'in x]
ck('one_usage_event',len(usage)==1)
ck('usage_matches_summary',usage[0]==cr['usage']==cost['usage']['reported'])
u=usage[0]
ck('usage_exact',u==dict(input_tokens=144766,cached_input_tokens=118528,cache_write_input_tokens=0,output_tokens=2616,reasoning_output_tokens=213))
ck('usage_subsets',0<=u['cached_input_tokens']<=u['input_tokens'] and 0<=u['reasoning_output_tokens']<=u['output_tokens'])
tools=[x['item'] for x in raw_events if x.get('type')=='item.completed' and x.get('item',{}).get('type')=='mcp_tool_call']
ck('seven_cli_tools',len(tools)==7)
records=[]; cli_images=[]; text_bytes=0
for i in range(1,8):
    folder=S/f'o/tool_{i:02d}'
    req=js(folder/'REQUEST.json'); res=js(folder/'RESPONSE.json'); rec=js(folder/'RECEIPT.json')
    name=req['params']['name']; ns=rec['closed_ns']-rec['started_ns']
    ck('tool_clock:'+str(i),ns==rec['elapsed_ns'])
    ck('tool_name:'+str(i),name==rec['name']==tools[i-1]['tool'])
    ck('tool_content:'+str(i),tools[i-1]['result']['content']==res['result']['content'])
    records.append({'tool':i,'name':name,'elapsed_ns':ns,'started_ns':rec['started_ns'],'closed_ns':rec['closed_ns'],'is_error':rec['is_error']})
    for block in tools[i-1]['result']['content']:
        if block['type']=='image':
            b=base64.b64decode(block['data'],validate=True)
            cli_images.append({'tool':i,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'base64_chars':len(block['data'])})
        elif block['type']=='text':text_bytes+=len(block['text'].encode('utf-8'))
ck('actual_tool_sequence',[x['name'] for x in records]==['active_observation','execute_python','execute_python','render_views','execute_python','execute_python','execute_python'])
ck('one_recovered_error',[x['tool'] for x in records if x['is_error']]==[5])
ck('duplicate_render_arguments',js(S/'o/tool_04/REQUEST.json')['params']['arguments']=={'names':['SCENE'],'include_images':True})
ck('tool_service_sum',sum(x['elapsed_ns'] for x in records)==4_709_071_000==cost['time']['owner_tool_service_sum_ns'])
public=js(S/'o/tool_01/RESPONSE.json')['result']['content'][0]['text']
ck('public_v4_bytes',len(public.encode('utf-8'))==44873)
old=js(Path('D:/he_explicit_001/formal/P1/o/tool_01/RESPONSE.json'))['result']['content'][0]['text']
ck('old_same_scene_actual_v3_bytes',len(old.encode('utf-8'))==42049)
oldj=json.loads(old); pubj=json.loads(public)
ck('same_geometry_camera',oldj['binding']['geometry_identity']==pubj['binding']['geometry_identity'] and oldj['binding']['camera_identity']==pubj['binding']['camera_identity'])
ck('four_cli_images',len(cli_images)==4 and sum(x['bytes'] for x in cli_images)==13109 and sum(x['base64_chars'] for x in cli_images)==17480)
ck('image_costs',sum(x['bytes'] for x in cli_images)==cost['bytes']['CLI_PNG']==cr['public_image_bytes'])
frames=obs['frames']; attempts=obs['render_attempts']; intents=[]; frame_summaries=[]
for p in sorted(Path('D:/he_consume_001/raster_budget').glob('attempt_*/INTENT.json')):intents.append(js(p))
ck('four_raster_intents',len(frames)==len(attempts)==len(intents)==4)
ck('raster_origins',[(x['origin'],x['view_name']) for x in attempts]==[('product','SCENE'),('product','BACK'),('product','LEFT'),('native','SCENE')])
ck('intent_ordinals',[x['global_attempt'] for x in intents]==[1,2,3,4])
ck('actual_no_prep_or_capture',all(x['phase']=='formal' for x in intents) and obs['metrics']['actual_Blender_capture_calls']==0 and len(obs['replays'])==1)
payload=0
for frame in frames:
    png=raw(frame['PNG']); npz=raw(frame['NPZ'])
    ck('PNG:'+str(frame['attempt_id']),len(png)==frame['PNG_bytes'] and hashlib.sha256(png).hexdigest()==frame['PNG_sha256'])
    ck('NPZ:'+str(frame['attempt_id']),len(npz)==frame['NPZ_bytes'] and hashlib.sha256(npz).hexdigest()==frame['NPZ_sha256'])
    arrays={}
    with zipfile.ZipFile(io.BytesIO(npz)) as z:
        for member in z.namelist():
            a=z.read(member); assert a[:6]==b'\x93NUMPY'; version=tuple(a[6:8]); width=2 if version==(1,0) else 4
            h=struct.unpack('<H' if width==2 else '<I',a[8:8+width])[0]
            meta=ast.literal_eval(a[8+width:8+width+h].decode('latin1')); data=a[8+width+h:]
            dtype=meta['descr']; n=int(re.search(r'(\d+)$',dtype).group(1)); n*=4 if 'U' in dtype else 1
            ck('array_shape:'+str(frame['attempt_id'])+member,len(data)==math.prod(meta['shape'])*n)
            key=member[:-4]; arrays[key]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            ck('array_digest:'+str(frame['attempt_id'])+key,arrays[key]['sha256']==frame['arrays'][key]['sha256'] and len(data)==frame['arrays'][key]['nbytes'])
    ck('frame_payload:'+str(frame['attempt_id']),sum(v['bytes'] for v in arrays.values())==frame['array_payload_bytes'])
    payload+=sum(v['bytes'] for v in arrays.values())
    frame_summaries.append({'origin':frame['origin'],'view':frame['view_name'],'PNG_bytes':len(png),'NPZ_bytes':len(npz),'arrays':arrays,'raster_ns':frame['render_closed_ns']-frame['render_started_ns']})
ck('all_array_payload',payload==20010424==obs['metrics']['array_payload_bytes']==cost['bytes']['all_saved_NPZ_array_payload'])
ck('duplicate_same_pose',frames[0]['pose']==frames[3]['pose'])
ck('duplicate_same_RGB_PNG',raw(frames[0]['PNG'])==raw(frames[3]['PNG']))
ck('incompatible_owner_semantics','patch_owners'in frames[0]['arrays'] and 'triangle_ids'not in frames[0]['arrays'] and 'triangle_ids'in frames[3]['arrays'])
for key in ('color','depth','owners'):ck('duplicate_common_array:'+key,frame_summaries[0]['arrays'][key]==frame_summaries[3]['arrays'][key])
ck('CLI_all_PNGs',[x['sha256'] for x in cli_images]==[x['PNG_sha256'] for x in frames])
service=js(S/'o/product_call_01/SERVICE_RESULT.json'); call=js(S/'o/product_call_01/CALL.json')
ck('product_fact_projection',service['stages']['scope_and_facts']['elapsed_ns']==2803900)
ck('product_envelope',call['delivery_audit']['closed_ns']-call['delivery_audit']['started_ns']==12991600)
for mode in ('TX','RX'):
    paths=[x for x in cr['MCP_wire_files'] if Path(x['path']).name==mode+'.bin']
    count=0
    for x in paths:
        b=raw(S/'c'/x['path']);ck('wire:'+x['path'],len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256']);count+=len(b)
    ck('wire_sum:'+mode,count==cost['bytes']['stdio_'+mode])
ck('exit_success',parent['exit_code']==cr['exit_code']==rr['owner_process_cleanup']['exit_code']==0 and lr['launcher_succeeded'])
ck('thin_held_exit',cr['runtime_exit']['confirmed'] and cr['runtime_exit']['exited'] and cr['runtime_exit']['exit_code']==1 and cr['runtime_exit']['handle_closed'])
ck('thin_EXIT_unknown',cr['bridge_cleanup']['receipt_status']=='unknown' and cr['bridge_cleanup']['missing_exit_count']==1)
ck('publication_present',not launch['terminal_errors'] and not launch['publication_errors'] and lr['route_execution_state']=='completed')
for name in ('bridge.py','native_tools.py','launcher.py'):raw(H/name)
ck('render_contract_fresh',b'Every requested view constructs a fresh frame' in raw(H/'bridge.py'))
post_product=cr['final_received_ns']-cr['tool_calls'][0]['perf_ns']
extra=sum(x['elapsed_ns'] for x in records[4:])
summary={'times_seconds':{k:sec(v) for k,v in times.items()},'wrapper_seconds':sec(wrapper),'tools':records,'tool_service_seconds':sec(sum(x['elapsed_ns'] for x in records)),
 'prompt_to_product_s':sec(cr['tool_calls'][0]['perf_ns']-cr['prompt_submitted_ns']), 'product_to_final_s':sec(post_product),
 'duplicate_render_service_s':sec(records[3]['elapsed_ns']),'duplicate_raster_only_s':sec(frame_summaries[3]['raster_ns']),
 'mapping_and_verification_service_s':sec(extra),'duplicate_service_fraction_of_parent':records[3]['elapsed_ns']/times['parent'],
 'duplicate_plus_mapping_service_fraction_of_parent':(records[3]['elapsed_ns']+extra)/times['parent'],
 'usage':u,'input_plus_output':u['input_tokens']+u['output_tokens'],'cached_and_reasoning_are_subsets':True,
 'frames':frame_summaries,'CLI_images':cli_images,'public_JSON_bytes':44873,'historical_same_scene_v3_JSON_bytes':42049,'added_public_JSON_bytes':2824,
 'generated_arrays_bytes':payload,'provider_requests':None,'cash':None,'normal_thin_EOF':'unknown','actual_API_selection_or_retry':'unproven',
 'decision':'Preserve efficiency failure; end zero-duplicate micro-optimization and use a bounded preregistered fair full-task comparison. No cached swap of patch_owner for native triangle_ids.'}
result={'passed':all(x['passed'] for x in checks),'checks':len(checks),'failures':[x for x in checks if not x['passed']],
 'summary':summary,'inputs_sha256':inputs,'new_product_model_Blender_raster_benchmark_calls':0,'limitations':['No independent namespace dump/hash','No pure model reasoning or counterfactual saved-turn time','Old v3 bytes independently read from same-scene prior real packet, same-state old projector not executed','Full-source/wheel/quality audits are handled by other root reviewers']}
(O/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(O/'CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('inputs_sha256','summary')},ensure_ascii=False));print(json.dumps({k:v for k,v in summary.items() if k not in ('frames','CLI_images','tools')},ensure_ascii=False))
