"""Independent stdlib-only recount. Does not load product code or start actors."""
import ast
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zipfile

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=ROOT/'verification/m4_active_observation_host_bridge_001'
OUT=Path(__file__).resolve().parent
checks=[];inputs={}
def raw(p):
    p=Path(p);b=p.read_bytes();inputs[str(p)]=hashlib.sha256(b).hexdigest();return b
def sha(p):return hashlib.sha256(raw(p)).hexdigest()
def js(p):return json.loads(raw(p))
def ck(k,c,detail=None):checks.append({'check':k,'passed':bool(c),'detail':detail})
def eq(k,a,b):ck(k,a==b,None if a==b else {'actual':a,'expected':b})
archive=js(H/'EXTERNAL_ARCHIVE.json')
mapping={r['original_relative_path']:ROOT/r['archive_path'] for r in archive['files']}
by_original={str(Path(r['original_path'])):ROOT/r['archive_path'] for r in archive['files']}
def ar(rel):return js(mapping[rel])
def lines(rel):return [json.loads(x) for x in raw(mapping[rel]).splitlines()]
def original(p):return by_original[str(Path(p))]
eq('archive_count',len(mapping),199)
eq('archive_bytes',sum(r['bytes'] for r in archive['files']),4206086)
for r in archive['files']:
    eq('archive_sha:'+r['original_relative_path'],sha(ROOT/r['archive_path']),r['sha256'])
    eq('original_bytes:'+r['original_relative_path'],raw(ROOT/r['archive_path']),raw(r['original_path']))

outer=[];all_rpc=[];active=[];frames={};direct=[];captures=[];indexes=[];held=[]
wire=Counter();stage_totals=Counter();construct_totals=Counter();feedback_totals=Counter();work=Counter()
expected_times=[1186250100,36448600,1189757500,1039994900,20019900]
for i in (1,2):
    run=f'acceptance_0{i}';prefix='run/'+run
    parent=js(H/'runs'/f'ACCEPTANCE_0{i}_PROCESS.json');result=ar(prefix+'/RESULTS.json')
    close=parent.get('closed_after_process_exit_ns',parent.get('closed_ns'))
    eq(run+':outer_clock',parent['elapsed_ns'],close-parent['started_ns'])
    eq(run+':outer_exit',parent['exit_code'],1 if i==1 else 0)
    eq(run+':success_state',result['passed'],i==2)
    ck(run+':nested_controller',parent['started_ns']<=result['started_ns']<=result['closed_before_publication_ns']<=close)
    eq(run+':no_models',result['new_model_calls'],0);eq(run+':no_pairs',result['new_paired_benchmarks'],0)
    eq(run+':cleanup_errors',result['cleanup_errors'],[])
    outer.append({'run':run,'start':parent['started_ns'],'end':close,'elapsed_ns':parent['elapsed_ns'],'exit_code':parent['exit_code']})
    if i==1:
        eq('first_failure_type',result['error']['type'],'FileExistsError')
        ck('first_failure_progress_path','PROGRESS.json' in result['error']['message'])
        eq('first_successful_responses_preserved',[r['case'] for r in result['requests']],['ordinary','same_source_repeat'])
    qa=ar(prefix+'/QA_LAUNCH.json');qs=ar(prefix+'/qa/CLOSE.json');ss=ar(prefix+'/stdio/START.json');sf=ar(prefix+'/server/FINISH.json');sstart=ar(prefix+'/server/START.json');sc=ar(prefix+'/stdio/CLOSE.json')
    for tag,c,pid in [('QA',result['QA_cleanup'],qa['pid']),('stdio',sc,ss['pid'])]:
        ck(run+':'+tag+'_held_cleanup',c['confirmed'] and c['exit_code']==0 and not c['forced_kill'] and c['pid']==pid)
        ck(run+':'+tag+'_held_handle_closed',c.get('held_handle_closed',c.get('process_handle_closed')))
        ck(run+':'+tag+'_cleanup_nested',result['started_ns']<=c['started_ns']<=c['closed_ns']<=result['closed_before_publication_ns'])
        held.append({'run':run,'actor':tag,**c})
    eq(run+':stdio_cleanup_same',sc,result['stdio_cleanup'])
    ck(run+':all_pipes_closed',all(sc['pipes_closed'].values()) and sc['reader_stopped'])
    eq(run+':server_pid_stable',sf['pid'],sstart['pid']);ck(run+':server_pid_differs_launcher',sf['pid']!=ss['pid'])
    ck(run+':server_finish_before_held_reaped',sf['closed_ns']<=sc['closed_ns'])
    ck(run+':server_clean_finish',sf['failure'] is None and sf['source_check_error'] is None)
    ck(run+':qa_close_requested',qs['close_requested'] and not qs['poisoned'] and qs['file_saves']==0 and qs['Blender_render_calls']==0)
    cap=lines(prefix+'/server/CAPTURES.jsonl');idx=lines(prefix+'/server/INDEXES.jsonl')
    eq(run+':capture_count',len(cap),sf['capture_calls']);eq(run+':prepare_count',len(idx),sf['prepare_calls'])
    for name, rows in [('capture',cap),('index',idx)]:
        for n,row in enumerate(rows):
            eq(run+':'+name+str(n)+':clock',row['elapsed_ns'],row['closed_ns']-row['started_ns'])
            eq(run+':'+name+str(n)+':stored_hash',sha(original(row['path'])),row['sha256'])
            eq(run+':'+name+str(n)+':bytes',len(raw(original(row['path']))),row['bytes'])
            ck(run+':'+name+str(n)+':inside_server',sstart['started_ns']<=row['started_ns']<=row['closed_ns']<=sf['closed_ns'])
            if name=='capture':
                eq(run+':capture'+str(n)+':subtimes',row['elapsed_ns'],row['host_call_elapsed_ns']+row['evidence_serialization_write_elapsed_ns'])
                eq(run+':capture'+str(n)+':no_extra',row['additional_host_capture_calls'],0)
            else:
                eq(run+':index'+str(n)+':subtimes',row['elapsed_ns'],row['original_call_elapsed_ns']+row['evidence_projection_write_elapsed_ns'])
                eq(run+':index'+str(n)+':no_extra',row['extra_prepare_calls'],0)
    captures.extend(cap);indexes.extend(idx)
    rpc_dirs=sorted({rel.rsplit('/',1)[0] for rel in mapping if rel.startswith(prefix+'/stdio/rpc_')})
    rxall=[]
    for d in rpc_dirs:
        tx=raw(mapping[d+'/TX.bin']);rx=raw(mapping[d+'/RX.bin']);receipt=ar(d+'/RECEIPT.json');request=json.loads(tx);response=json.loads(rx)
        eq(d+':TX_bytes',len(tx),receipt['TX_bytes']);eq(d+':RX_bytes',len(rx),receipt['RX_bytes']);eq(d+':RX_hash',hashlib.sha256(rx).hexdigest(),receipt['RX_sha256'])
        eq(d+':RX_structured',response,ar(d+'/RESPONSE.json'));eq(d+':clock',receipt['elapsed_ns'],receipt['closed_ns']-receipt['started_ns'])
        eq(d+':id',request['id'],response['id']);eq(d+':method',request['method'],receipt['method'])
        ck(d+':ordered_times',receipt['started_ns']<=receipt['stdin_flushed_ns']<=receipt['received_complete_ns']<=receipt['consumer_json_decoded_ns']<=receipt['closed_ns'])
        ck(d+':no_transport_error',receipt['error'] is None)
        rxall.append(rx);wire['TX_bytes']+=len(tx);wire['RX_bytes']+=len(rx)
        tool=request.get('params',{}).get('name');args=request.get('params',{}).get('arguments',{})
        all_rpc.append({'run':run,'id':request['id'],'method':request['method'],'tool':tool,'isError':response.get('result',{}).get('isError'), 'error':response.get('error')})
        if tool=='human_eye_scene_observe' and args.get('query',{}).get('mode')=='active_observation' and not response.get('result',{}).get('isError') and 'result' in response:
            result_row=next(r for r in result['requests'] if r['case']==request['id']);readback=ar(prefix+'/consumer_'+request['id']+'/READBACK.json')
            payload=readback['text'];content=response['result']['content'];texts=[b['text'] for b in content if b['type']=='text'];imgs=[b for b in content if b['type']=='image']
            eq(d+':readback_text',json.loads(texts[0]),payload);eq(d+':readback_clock',readback['elapsed_ns'],readback['closed_ns']-readback['started_ns'])
            eq(d+':complete_request_time',result_row['elapsed_to_consumer_images_ns'],readback['closed_ns']-result_row['started_ns'])
            eq(d+':work',payload['work'],result_row['work']);eq(d+':image_count',len(imgs),readback['image_blocks_read'])
            eq(d+':model_calls',readback['model_calls'],0);eq(d+':model_consumption',readback['model_image_consumption'],'not_tested')
            wire['active_text_UTF8_bytes']+=sum(len(t.encode()) for t in texts)
            wire['image_blocks']+=len(imgs)
            for image,reported in zip(imgs,readback['images']):
                png=base64.b64decode(image['data'],validate=True)
                eq(d+':delivered_png_'+str(reported['index']),png,raw(original(reported['path'])))
                eq(d+':delivered_png_hash_'+str(reported['index']),hashlib.sha256(png).hexdigest(),reported['PNG_sha256'])
                wire['delivered_PNG_bytes']+=len(png);wire['base64_characters']+=len(image['data'])
            rx_text=rx.decode('utf8');decoder=json.JSONDecoder();image_slices=[]
            for start,ch in enumerate(rx_text):
                if ch!='{':continue
                try:value,end=decoder.raw_decode(rx_text,start)
                except json.JSONDecodeError:continue
                if isinstance(value,dict) and value.get('type')=='image':
                    image_slices.append((value,len(rx_text[start:end].encode('utf8'))))
            eq(d+':actual_wire_image_objects',[v for v,n in image_slices],imgs)
            wire['image_JSON_bytes']+=sum(n for v,n in image_slices)
            for k,v in payload['work'].items():
                if type(v) is int:work[k]+=v
            for k,v in payload['stages'].items():
                eq(d+':stage_clock:'+k,v['elapsed_ns'],v['closed_ns']-v['started_ns']);stage_totals[k]+=v['elapsed_ns']
            if request['id']=='same_source_repeat':
                eq('hot_capture_once',payload['work']['capture_calls'],1)
                for k in ['prepare_calls','geometry_parse_calls','raster_attempts','raster_completed','mapping_calls','mesh_conversions','camera_calls']:
                    eq('hot_zero:'+k,payload['work'][k],0)
            for frame in payload['frames']:
                key=frame['image_path']
                if key in frames:
                    eq('reused_frame_record:'+key,frames[key],frame)
                else:frames[key]=frame
            active.append({'run':run,'case':request['id'],'elapsed_ns':result_row['elapsed_to_consumer_images_ns'],'work':payload['work'],'stages':payload['stages'],'image_blocks':len(imgs),'readback_ns':readback['elapsed_ns']})
    eq(run+':stdout_all_RX',raw(mapping[prefix+'/stdio/stdout.raw.bin']),b''.join(rxall))
    for rel in mapping:
        if rel.startswith(prefix+'/DIRECT_'):
            v=ar(rel);eq(rel+':clock',v['elapsed_ns'],v['closed_ns']-v['started_ns']);eq(rel+':no_render',v['new_rasters'],0)
            eq(rel+':one_parse',v['extra_QA_geometry_parses'],1);eq(rel+':one_index',v['extra_QA_indexes'],1);direct.append(v)

eq('RPC_count',len(all_rpc),12);eq('tool_call_count',sum(r['method']=='tools/call' for r in all_rpc),7)
eq('only_expected_tool_error',[r['id'] for r in all_rpc if r['isError']],['bad_active_query'])
eq('bad_then_ping_then_old_read',[r['id'] for r in all_rpc[-3:]],['bad_active_query','ping_after_bad_request','old_readonly_regression'])
ck('ping_and_old_read_succeed',all(r['error'] is None and not r['isError'] for r in all_rpc[-2:]))
eq('active_success_count',len(active),5);eq('active_times',[r['elapsed_ns'] for r in active],expected_times)
eq('capture_count',len(captures),5);eq('prepare_count',len(indexes),4);eq('DIRECT_count',len(direct),4)
eq('DIRECT_elapsed',sum(r['elapsed_ns'] for r in direct),1457536800)
for k,want in [('capture_calls',5),('prepare_calls',4),('geometry_parse_calls',4),('raster_attempts',6),('raster_completed',6),('local_verified_images',6),('frame_reuses',2)]:eq('work_total:'+k,work[k],want)
eq('distinct_constructed_frames',len(frames),6)
intents=lines('run/render_budget/INTENTS.jsonl');eq('intent_count',len(intents),6);eq('intent_numbers',[v['attempt'] for v in intents],list(range(1,7)))
ordered_frames=sorted(frames.values(),key=lambda f:f['stages']['actual_raster']['started_ns'])
png_bytes=npz_bytes=array_bytes=0
for intent,frame in zip(intents,ordered_frames):
    eq('durable_intent:'+str(intent['attempt']),intent,ar('run/render_budget/attempt_'+str(intent['attempt']).zfill(2)+'/INTENT.json'))
    eq('intent_view:'+str(intent['attempt']),intent['fields']['view_name'],frame['view_name'])
    ck('intent_before_raster:'+str(intent['attempt']),intent['monotonic_ns']<frame['stages']['actual_raster']['started_ns'])
    for name,v in frame['stages'].items():eq('frame_clock:'+frame['image_ref']+name,v['elapsed_ns'],v['closed_ns']-v['started_ns']);construct_totals[name]+=v['elapsed_ns']
    for name,v in frame['feedback_stages'].items():eq('feedback_clock:'+frame['image_ref']+name,v['elapsed_ns'],v['closed_ns']-v['started_ns']);feedback_totals[name]+=v['elapsed_ns']
    png=raw(original(frame['image_path']));npz=original(frame['arrays_path']);png_bytes+=len(png);npz_bytes+=len(raw(npz))
    eq('PNG_size:'+frame['image_ref'],len(png),frame['PNG_bytes']);eq('NPZ_size:'+frame['image_ref'],npz.stat().st_size,frame['compressed_array_file_bytes'])
    payload=0
    with zipfile.ZipFile(npz) as z:
        for name in z.namelist():
            buf=z.read(name);major=buf[6];sizefmt='<H' if major==1 else '<I';hlen=struct.unpack_from(sizefmt,buf,8)[0];offset=10 if major==1 else 12
            header=ast.literal_eval(buf[offset:offset+hlen].decode('latin1').strip());n=1
            for dimension in header['shape']:n*=dimension
            itemsize=int(header['descr'][2:]);n*=itemsize;eq('NPY_payload:'+frame['image_ref']+name,len(buf)-offset-hlen,n);payload+=n
    eq('array_payload:'+frame['image_ref'],payload,frame['array_payload_bytes']);array_bytes+=payload
for name,want in [('actual_raster',1204286600),('PNG_NPZ_publication',144677600),('frame_metadata',53616900)]:eq('construction_total:'+name,construct_totals[name],want)
for name,want in [('load_validate',34132300),('readability',30388400),('state_commit',2085600)]:eq('feedback_total:'+name,feedback_totals[name],want)
eq('new_PNG_bytes',png_bytes,20850);eq('new_NPZ_bytes',npz_bytes,144115);eq('array_payload_bytes',array_bytes,23592960)
for k,w in [('image_blocks',8),('active_text_UTF8_bytes',101824),('delivered_PNG_bytes',27800),('base64_characters',37072),('image_JSON_bytes',37504)]:eq('wire:'+k,wire[k],w)
eq('outer_total_ns',sum(r['elapsed_ns'] for r in outer),11340831700)
order=js(H/'WORK_ORDER.json');eq('original_expected_rasters',order['expected_new_rasters'],4);eq('hard_cap',order['global_new_raster_hard_cap'],8)
eq('preparation_span',outer[-1]['end']-order['marked_preparation_started_ns'],3207090301900)
eq('two_batch_span',outer[-1]['end']-outer[0]['start'],485518981600)
repair=js(H/'preparation/PROGRESS_PUBLICATION_REPAIR.json');eq('recovery_total_expected',repair['revised_total_expected_rasters'],6);ck('repair_before_recovery',repair['root_marked_ns']<outer[1]['start'])
unit=js(H/'runs/UNIT_RESULT.json');eq('unit_count',unit['run'],36);eq('unit_wall_ns',unit['closed_before_publication_ns']-unit['started_ns'],1673879900)
env=js(H/'preparation/ENVIRONMENT.json');eq('environment_wall_ns',env['closed_before_publication_ns']-env['started_ns'],7788996600)
build=js(H/'build/BUILD_INSTALL.json')
eq('build_install_wall_ns',build['closed_before_publication_ns']-build['started_ns'],2928106100)
eq('wheel_wall_ns',build['wheel_closed_ns']-build['wheel_started_ns'],394328400)
eq('pip_wall_ns',build['install_closed_ns']-build['install_started_ns'],1597428900)
ck('build_nested_windows',build['started_ns']<=build['wheel_started_ns']<=build['wheel_closed_ns']<=build['install_started_ns']<=build['install_closed_ns']<=build['closed_before_publication_ns'])
cleanup=js(H/'review/FINAL_AUDIT_HELPER_CLEANUP.json')
eq('late_cleanup_sha',sha(H/'review/FINAL_AUDIT_HELPER_CLEANUP.json'),'5fa493a5d749b3f4800d1b2e0a763ca407d9dbcc4f44fa353712fcc38a1c6212')
ck('audit_helper_empty_known_failure',cleanup['helper']['code_submitted'] is False and cleanup['helper']['reaped_original_session_exit_code']==1 and cleanup['helper']['pid']==19992)
ck('helper_identity_specific_cleanup','__AUDIT_END__' in cleanup['helper']['CommandLine'] and 'exact ExecutablePath' in cleanup['helper']['cleanup_action'])
eq('helper_duration_unknown',cleanup['helper']['absolute_start_duration_CPU_RSS'],'unknown')
eq('late_audit_preserved',sha(H/'review/FINAL_COST_AUDIT.json'),cleanup['cost_audit_preserved_sha256'])
changed=subprocess.check_output(['git','-C',str(ROOT),'diff','--name-only','944f590b8376739881e672d11ba4cc638e023c56','32a1c6eb47cfa84133d92199387339d407a33cb5'],text=True).splitlines()
eq('late_commit_only_cleanup_and_manifest',sorted(changed),sorted(['verification/m4_active_observation_host_bridge_001/CONTENT_MANIFEST.json','verification/m4_active_observation_host_bridge_001/review/FINAL_AUDIT_HELPER_CLEANUP.json']))
code=raw(H/'stdio_entry.py').decode();ck('intent_reservation_fixed_8_and_no_delete','range(1, 9)' in code and 'unlink' not in code)
controller=raw(H/'run_acceptance.py').decode();recovery=raw(H/'run_acceptance_r2.py').decode();ck('first_progress_exclusive_failure_explained',"open('xb')" in controller and "save(output / 'PROGRESS.json', result)" in controller)
ck('recovery_unique_progress',"'PROGRESS_' + case + '.json'" in recovery)
cold=sum(r['elapsed_ns'] for r in active if r['image_blocks'] and not r['work']['result_cache_hit'])
result={'schema':'root-host-bridge-cost-lifecycle-v1','commit':'32a1c6eb47cfa84133d92199387339d407a33cb5','passed':all(c['passed'] for c in checks),'check_count':len(checks),'failures':[c for c in checks if not c['passed']], 'checks':checks,'active_requests':active,'rpc':all_rpc,'outer':outer,'held':held,'work_totals':dict(work),'wire_totals':dict(wire),'construction_stage_totals_ns':dict(construct_totals),'feedback_stage_totals_ns':dict(feedback_totals),'cold_complete_total_ns':cold,'readability_fraction_of_cold_complete':feedback_totals['readability']/cold,'capture_bytes':sum(r['bytes'] for r in captures),'direct_elapsed_ns':sum(r['elapsed_ns'] for r in direct),'limits':['Single chain observations, no repeated statistical benefit estimate','Held receipts refer to launcher and QA; server has FINISH/EOF evidence, no independent held server handle','Late audit helper19992 was force-cleaned after identity recheck, code never submitted, absolute duration unknown','Model tokens/fees/consumption and RSS unmeasured'], 'next_priority':'Capability: multi-patch discovery and same-object occlusion before per-ROI pixel micro-optimization. Readability is less than1% of measured three cold image requests.', 'new_product_model_Blender_raster_benchmark_calls':0,'inputs_sha256':inputs}
result['next_priority']='Pixel readability is less than1% of three measured cold image requests, so optimizing it first has little end-to-end upside. Concrete delivery defects, if separately established, should be fixed before capability expansion; this cost audit does not assess that defect.'
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'passed':result['passed'],'checks':len(checks),'failures':result['failures'],'readability_fraction_of_cold_complete':result['readability_fraction_of_cold_complete']},ensure_ascii=False))
