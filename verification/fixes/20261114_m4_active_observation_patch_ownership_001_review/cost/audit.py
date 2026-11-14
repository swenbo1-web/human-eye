"""Independent original-record cost audit. No product or author oracle import."""
from pathlib import Path
from io import BytesIO
import base64, hashlib, json, statistics, time, zipfile
import numpy as np

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H=ROOT/'verification/m4_active_observation_patch_ownership_001'
OUT=Path(__file__).resolve().parent
started=time.perf_counter_ns(); checks=[]; evidence={}
def raw(p):
    p=Path(p); b=p.read_bytes(); evidence[str(p)]=hashlib.sha256(b).hexdigest(); return b
def js(p): return json.loads(raw(p))
def ck(name,ok,detail=None): checks.append({'name':name,'passed':bool(ok),'detail':detail})
archive=js(H/'EXTERNAL_ARCHIVE.json')
byrel={r['original_relative_path']:ROOT/r['archive_path'] for r in archive['files']}
byabsolute={str(Path(r['original_path'])):ROOT/r['archive_path'] for r in archive['files']}
def arc(rel): return byrel[rel]
def arj(rel): return js(arc(rel))
def lines(rel): return [json.loads(line) for line in raw(arc(rel)).splitlines() if line]
for row in archive['files']:
    b=raw(ROOT/row['archive_path']); ck('archive:'+row['original_relative_path'],len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'])
ck('archive_denominator',len(archive['files'])==169 and sum(r['bytes'] for r in archive['files'])==archive['bytes']==7233396)
summary=js(H/'RESULT_SUMMARY.json');run=arj('run/acceptance_01/RESULTS.json')
captures=lines('run/acceptance_01/server/CAPTURES.jsonl')
indexes=lines('run/acceptance_01/server/INDEXES.jsonl')
results=lines('run/acceptance_01/server/RESULTS.jsonl')
intents=lines('run/render_budget/INTENTS.jsonl')
ck('actual_stage_denominators',(len(captures),len(indexes),len(results),len(intents))==(5,2,5,6))
for category,rows,clock,end in [('capture',captures,'host_call_elapsed_ns','host_returned_ns'),('index',indexes,'original_call_elapsed_ns','original_returned_ns'),('result',results,'original_call_elapsed_ns','original_returned_ns')]:
    for r in rows:
        b=raw(byabsolute[str(Path(r['path']))]);ck(category+':raw:'+str(r['index']),len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'])
        ck(category+':clock:'+str(r['index']),r['closed_ns']-r['started_ns']==r['elapsed_ns'] and r[end]-r['started_ns']==r[clock] and r['started_ns']<=r[end]<=r['closed_ns'])
        extra='evidence_projection_write_elapsed_ns' if category=='index' else 'evidence_serialization_write_elapsed_ns'
        ck(category+':sidecar:'+str(r['index']),r['closed_ns']-r[end]==r[extra])
slotrows=[r for r in archive['files'] if r['original_relative_path'].startswith('run/render_budget/attempt_')]
ck('six_durable_slots',len(slotrows)==6 and [r['attempt'] for r in intents]==list(range(1,7)))
for r in intents:
    v=arj('run/render_budget/attempt_'+str(r['attempt']).zfill(2)+'/INTENT.json')
    ck('intent_same:'+str(r['attempt']),v==r and r['event']=='active_observation_render_attempt' and r['pid']==26720)

rxs=[]; tx_bytes=rx_bytes=txt_bytes=png_bytes=base64chars=image_json_bytes=text_json_bytes=0
request_metrics=[];raw_results=[];decoder=json.JSONDecoder()
def block_spans(data):
    text=data.decode('utf8'); at=text.index('"content"'); pos=text.index('[',at)+1; spans=[]
    while text[pos].isspace(): pos+=1
    while text[pos]!=']':
        obj,end=decoder.raw_decode(text,pos); spans.append((obj,len(text[pos:end].encode('utf8'))));pos=end
        while text[pos].isspace():pos+=1
        if text[pos]==',':
            pos+=1
            while text[pos].isspace():pos+=1
    return spans
for i in range(1,8):
    prefix='run/acceptance_01/stdio/rpc_'+str(i).zfill(2)+'/'
    tx,rx=raw(arc(prefix+'TX.bin')),raw(arc(prefix+'RX.bin'));txv,rv=json.loads(tx),json.loads(rx);receipt=arj(prefix+'RECEIPT.json')
    tx_bytes+=len(tx);rx_bytes+=len(rx);rxs.append(rx)
    ck('rpc:'+str(i),txv['id']==rv['id']==receipt['id'] and rv==arj(prefix+'RESPONSE.json') and receipt['error'] is None)
    ck('rpc_receipt_bytes:'+str(i),len(tx)==receipt['TX_bytes'] and len(rx)==receipt['RX_bytes'] and hashlib.sha256(rx).hexdigest()==receipt['RX_sha256'])
    ck('rpc_receipt_clock:'+str(i),receipt['closed_ns']-receipt['started_ns']==receipt['elapsed_ns'] and receipt['started_ns']<=receipt['stdin_flushed_ns']<=receipt['received_complete_ns']<=receipt['consumer_json_decoded_ns']<=receipt['closed_ns'])
    if i<3:
        ck('protocol_method:'+str(i),txv['method']==['initialize','tools/list'][i-1]);continue
    n=i-3;case=summary['cases'][n]['case']; req=run['requests'][n]
    text=rv['result']['content'][0]['text'];public=json.loads(text);readback=arj('run/acceptance_01/consumer_'+case+'/READBACK.json')
    service=arj('run/acceptance_01/server/RESULT_'+str(n+1).zfill(2)+'.json');raw_results.append(service)
    ck('tool_call:'+case,txv['method']=='tools/call' and txv['id']==case and rv['result']['isError'] is False)
    ck('actual_text:'+case,readback['text']==public and len(text.encode('utf8'))==summary['cases'][n]['text_UTF8_bytes']==req['delivery']['text_UTF8_bytes'])
    txt_bytes+=len(text.encode('utf8'))
    content=rv['result']['content']; imgs=content[1:];ck('images_per_request:'+case,len(imgs)==3==readback['image_blocks_read'])
    for image,frame in zip(imgs,service['frames']):
        img=base64.b64decode(image['data'],validate=True); png_bytes+=len(img);base64chars+=len(image['data'])
        ck('native_image:'+case+':'+frame['view_name'],image['type']=='image' and image['mimeType']=='image/png' and len(img)==frame['PNG_bytes'] and hashlib.sha256(img).hexdigest()==frame['image_sha256'] and img==raw(byabsolute[str(Path(frame['image_path']))]))
    for block,count in block_spans(rx):
        if block['type']=='image':image_json_bytes+=count
        else:text_json_bytes+=count
    elapsed=readback['closed_ns']-req['started_ns']
    ck('consumer_clock:'+case,elapsed==req['elapsed_to_consumer_ns']==summary['cases'][n]['request_to_consumer_ns'] and receipt['closed_ns']<=readback['started_ns']<=readback['closed_ns'])
    ck('consumer_no_model:'+case,readback['model_calls']==0 and readback['model_image_consumption']=='not_tested')
    ck('work_same:'+case,service['work']==req['work']==summary['cases'][n]['work'])
    ck('fresh_capture:'+case,service['work']['capture_calls']==1 and len(results[n]['capture_associations'])==1 and results[n]['capture_associations'][0]['index']==n+1)
    if case.endswith('cold'):
        ck('cold_work:'+case,all(service['work'][k]==1 for k in ('geometry_parse_calls','prepare_calls','patch_mapping_calls','mapping_calls','camera_calls','mesh_conversions')) and service['work']['raster_attempts']==service['work']['raster_completed']==3)
    else:
        ck('hot_work:'+case,all(service['work'][k]==0 for k in ('geometry_parse_calls','prepare_calls','patch_mapping_calls','mapping_calls','camera_calls','mesh_conversions','raster_attempts','raster_completed','NPZ_bytes','PNG_bytes','array_payload_bytes')) and service['work']['frame_reuses']==3)
    for stage,row in service['stages'].items():
        ck('stage_clock:'+case+':'+stage,row['elapsed_ns']==row['closed_ns']-row['started_ns'] and row['started_ns']<=row['closed_ns'])
    request_metrics.append({'case':case,'consumer_ns':elapsed,'service_ns':service['stages']['service_total']['elapsed_ns'],'public_text_bytes':len(text.encode('utf8')),'RX_bytes':len(rx),'index_ns':service['stages'].get('index',{}).get('elapsed_ns'),'work':service['work']})
ck('wire_totals',(tx_bytes,rx_bytes,txt_bytes,png_bytes,base64chars)==(1328,485084,369723,44095,58800))
ck('stdout_is_seven_RX',b''.join(rxs)==raw(arc('run/acceptance_01/stdio/stdout.raw.bin')))
ck('stderr_empty',raw(arc('run/acceptance_01/stdio/stderr.raw.bin'))==b'')
ck('unique_business_frames',sum(r['work']['raster_attempts'] for r in raw_results)==6 and sum(r['work']['prepare_calls'] for r in raw_results)==2)

arrays=[];new_png=new_npz=array_payload=patch_bytes=mapping_bytes=0
for n in (0,2):
    service=raw_results[n];reprname='split' if n==0 else 'joined'
    for frame in service['frames']:
        png=raw(byabsolute[str(Path(frame['image_path']))]);npz=raw(byabsolute[str(Path(frame['arrays_path']))])
        new_png+=len(png);new_npz+=len(npz)
        ck('frame_files:'+reprname+':'+frame['view_name'],len(png)==frame['PNG_bytes'] and len(npz)==frame['compressed_array_file_bytes'] and hashlib.sha256(npz).hexdigest()==frame['arrays_sha256'])
        size=patch=meta=0
        with np.load(BytesIO(npz),allow_pickle=False) as z:
            ck('nine_NPY:'+reprname+':'+frame['view_name'],len(z.files)==9)
            for key in z.files:
                a=z[key];observed={'dtype':str(a.dtype),'shape':list(a.shape),'nbytes':a.nbytes,'sha256':hashlib.sha256(a.tobytes(order='C')).hexdigest()}
                ck('NPY_metadata:'+reprname+':'+frame['view_name']+':'+key,observed==frame['arrays'][key])
                size+=a.nbytes
                if key=='patch_owners':patch=a.nbytes
                elif key not in ('color','depth','owners'):meta+=a.nbytes
        ck('frame_array_payload:'+reprname+':'+frame['view_name'],size==frame['array_payload_bytes'] and patch==frame['patch_owner_array_bytes']==1048576 and meta==frame['patch_mapping_array_bytes'])
        array_payload+=size;patch_bytes+=patch;mapping_bytes+=meta
        arrays.append(dict(representation=reprname,view=frame['view_name'],payload_bytes=size,patch_bytes=patch,mapping_bytes=meta))
        for group in ('stages','feedback_stages'):
            for key,r in frame[group].items():ck('frame_clock:'+reprname+':'+frame['view_name']+':'+key,r['elapsed_ns']==r['closed_ns']-r['started_ns'])
        matching=[r for r in intents if r['fields']['view_name']==frame['view_name'] and r['monotonic_ns']<frame['stages']['actual_raster']['started_ns']]
        ck('intent_before_raster:'+reprname+':'+frame['view_name'],bool(matching))
ck('new_frame_totals',(new_png,new_npz,array_payload,patch_bytes,mapping_bytes)==(17638,187544,30060048,6291456,175632))

bench=arj('run/benchmark_01.json');calls=bench['calls'];pairs=bench['pairs'];fixed=js(H/'EXECUTION_PLAN.json')['benchmark']
ck('fixed_five_pairs',len(calls)==10 and len(pairs)==5 and bench['pair_order']==fixed['order'] and bench['warmup_calls']==0)
ck('benchmark_zero_new_business',bench['new_raster_calls']==bench['new_geometry_discovery_calls']==bench['new_model_calls']==0)
for c in calls:ck('benchmark_clock:'+str(c['pair'])+':'+c['variant'],c['closed_ns']-c['started_ns']==c['elapsed_ns'])
for i,pair in enumerate(pairs,1):
    pc=[r for r in calls if r['pair']==i]
    ck('pair_order:'+str(i),[r['variant'] for r in pc]==fixed['order'][i-1] and pair['counts_equal'] is True)
    ck('pair_times:'+str(i),all(pair[r['variant']+'_ns']==r['elapsed_ns'] for r in pc))
    ck('comparison_clock:'+str(i),pair['comparison_elapsed_ns']==pair['comparison_closed_ns']-pair['comparison_started_ns'] and max(r['closed_ns'] for r in pc)<=pair['comparison_started_ns'])
stats={}
for arm in ('reference','optimized'):
    ns=[r['elapsed_ns'] for r in calls if r['variant']==arm]
    stats[arm]={'raw_ns':ns,'median_ns':statistics.median(ns),'sum_ns':sum(ns),'max_ns':max(ns)}
    ck('benchmark_summary:'+arm,ns==bench['summary'][arm]['raw_ns'] and statistics.median(ns)==bench['summary'][arm]['median_ns'] and sum(ns)==bench['summary'][arm]['sum_ns'] and max(ns)==bench['summary'][arm]['maximum_ns'])
ratio=stats['optimized']['median_ns']/stats['reference']['median_ns']
ck('median_reduction',ratio==bench['ratio_of_medians'] and (1-ratio)*100==summary['kernel_comparison']['median_reduction_percent'])
ck('ratio_definition',statistics.median(p['optimized_ns']/p['reference_ns'] for p in pairs)==bench['pair_ratio_median'] and stats['optimized']['sum_ns']/stats['reference']['sum_ns']==bench['ratio_of_sums'])
# Recompute once from the already saved first frame, outside any product/benchmark.
with np.load(BytesIO(raw(byabsolute[str(Path(bench['arrays_path']))])),allow_pickle=False) as z:
    color=z['color'].astype(np.int32); owners=z['patch_owners']; boundary=np.zeros(owners.shape,dtype=bool)
    for axis in (0,1):
        a=(slice(None,-1),slice(None)) if axis==0 else (slice(None),slice(None,-1))
        b=(slice(1,None),slice(None)) if axis==0 else (slice(None),slice(1,None))
        delta=color[a]-color[b];edge=(owners[a]!=owners[b]) & ((delta*delta).sum(axis=2)>=576)
        boundary[a]|=edge;boundary[b]|=edge
    independent={'visible_surface_pixels':[int(np.count_nonzero(owners==i)) for i in range(138)],'contrasting_boundary_pixels':[int(np.count_nonzero((owners==i)&boundary)) for i in range(138)]}
for p in pairs:ck('stored_pair_counts_independently_recomputed:'+str(p['pair']),p['output_counts']==independent)

windows={}
for tag,rel in [('integration','runs/ACCEPTANCE_01_PROCESS.json'),('benchmark','runs/BENCHMARK_01_PROCESS.json')]:
    v=js(H/rel);elapsed=v['closed_after_process_exit_ns']-v['started_ns'];windows[tag]=elapsed
    ck(tag+'_outer_clock',elapsed==v['elapsed_ns'] and v['exit_code']==0)
windows['integration_internal']=run['closed_before_publication_ns']-run['started_ns']
ck('whole_integration_nested',js(H/'runs/ACCEPTANCE_01_PROCESS.json')['started_ns']<=run['started_ns']<run['closed_before_publication_ns']<=js(H/'runs/ACCEPTANCE_01_PROCESS.json')['closed_after_process_exit_ns'])
for name,rel in [('environment','preparation/ENVIRONMENT.json'),('build_R1','build/BUILD_INSTALL.json'),('build_R2','build_r2/BUILD_INSTALL.json'),('units_R1','units_01/UNIT_RESULT.json'),('units_R3','units_03/UNIT_RESULT.json')]:
    v=js(H/rel);windows[name]=v['closed_before_publication_ns']-v['started_ns'];ck(name+'_clock_nonnegative',windows[name]>=0)
u1,u3=js(H/'units_01/UNIT_RESULT.json'),js(H/'units_03/UNIT_RESULT.json');u2=js(H/'preparation/UNIT_GUARD_STARTUP_REPAIR.json')
ck('R1_failure_retained',u1['run']==65 and not u1['passed'] and len(u1['errors'])==len(u1['failures'])==1)
ck('R2_startup_retained',u2['error_type']=='unittest.mock.InvalidSpecError' and u2['original_tool_receipt']['exit_code']==1 and u2['original_tool_receipt']['UNIT_RESULT_created'] is False and not (H/'units_02/UNIT_RESULT.json').exists())
ck('R3_pass_retained',u3['run']==65 and u3['passed'] and not u3['errors'] and not u3['failures'])
for label,u in [('R1',u1),('R3',u3)]:
    ck(label+'_units_no_raster',u['real_rasters']==u['Blender_processes']==0 and not u['forbidden_calls'])
    ck(label+'_help_child_exit',len(u['Python_test_children'])==1 and u['Python_test_children'][0]['exit_code']==0 and u['Python_test_children'][0]['command'][-1]=='--help')

finish=arj('run/acceptance_01/server/FINISH.json');server_start=arj('run/acceptance_01/server/START.json');close=arj('run/acceptance_01/stdio/CLOSE.json');stdio_start=arj('run/acceptance_01/stdio/START.json');qa=run['QA_cleanup'];qa_launch=arj('run/acceptance_01/QA_LAUNCH.json');qa_ready=arj('run/acceptance_01/qa/READY.json')
ck('server_terminal',finish['pid']==server_start['pid']==26720 and finish['failure'] is None and finish['source_check_error'] is None and finish['capture_calls']==5 and finish['prepare_calls']==2 and finish['observe_calls']==5 and finish['raster_intents']==6)
ck('launcher_cleanup',close==run['stdio_cleanup'] and close['pid']==2376 and close['exit_code']==0 and not close['forced_kill'] and close['confirmed'] and close['reader_stopped'] and close['process_handle_closed'] and all(close['pipes_closed'].values()) and not close['errors'])
ck('QA_cleanup',qa['pid']==16604 and qa['exit_code']==0 and not qa['forced_kill'] and qa['held_handle_closed'] and qa['confirmed'])
ck('no_cleanup_errors',not run['cleanup_errors'])
ck('server_ends_before_launcher',finish['closed_ns']<=close['closed_ns'] and finish['pid']!=close['pid'])
ck('deadline_not_extended',run['original_deadline_ns']-run['started_ns']==600_000_000_000 and run['closed_before_publication_ns']<run['original_deadline_ns'])

out={'schema':'root-patch-ownership-cost-review-v1','passed':all(c['passed'] for c in checks),'check_count':len(checks),'failures':[c for c in checks if not c['passed']],
 'bytes':dict(TX=tx_bytes,RX=rx_bytes,public_text=txt_bytes,delivered_PNG=png_bytes,base64_characters=base64chars,native_image_JSON=image_json_bytes,text_block_JSON=text_json_bytes,new_PNG=new_png,new_NPZ=new_npz,arrays=array_payload,patch_owner=patch_bytes,mapping=mapping_bytes),
 'requests':request_metrics,'benchmark':dict(stats=stats,ratio_of_medians=ratio,reduction_percent=(1-ratio)*100,pair_ratio_median=bench['pair_ratio_median']),
 'arrays':arrays,'windows_ns':windows,'lifecycle':dict(QA=qa,launcher=close,server=finish),
 'denominators':dict(protocol_requests=7,tool_requests=5,fresh_capture=5,prepare=2,new_rasters=6,native_blocks=15,NPY_arrays=54,pairs=5,kernel_calls_each=5,unit_methods_executed=130,unit_startup_failures=1,independent_world_geometry=1),
 'limits':['Local five-pair kernel only; no complete task or model gain measured.','Published array bytes and per-frame repeated mapping are not RSS.','Benchmark optimized per-pair arrays are not separately logged; equality is evidenced by checked original code/assertions and receipts. Stored reference counts independently recomputed once.','No model/API/RSS/new independent asset measurement.','Failed test and startup records retained; Bad Request itself is host conversation evidence, not inferred from unit files.'],
 'new_product_model_Blender_raster_benchmark_calls':0,'checks':checks,'evidence':evidence,'own_audit_elapsed_ns':time.perf_counter_ns()-started}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({k:v for k,v in out.items() if k in ('passed','check_count','failures','bytes','windows_ns','benchmark')},ensure_ascii=False))
