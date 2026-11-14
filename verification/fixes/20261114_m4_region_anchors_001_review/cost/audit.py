"""Independent saved-record audit. No product imports or new measurements."""
from pathlib import Path
import base64
import hashlib
import json
import statistics
import math
from fractions import Fraction
from io import BytesIO
import numpy as np

REPO = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BASE = REPO / 'verification/m4_active_observation_region_anchors_001'
OUT = Path(__file__).resolve().parent
inputs = {}
checks = []
def read(path):
    path = Path(path)
    data = path.read_bytes()
    inputs[str(path)] = {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    return data
def js(path):
    return json.loads(read(path))
def check(name, cond, details=None):
    checks.append({'name':name,'passed':bool(cond),**({'details':details} if details is not None else {})})
def eq(name, got, want):
    check(name, got == want, None if got == want else {'actual':got,'expected':want})
def clock(name, row):
    eq(name, row['closed_ns']-row['started_ns'],row['elapsed_ns'])
def nested_clock(name, child, parent):
    clock(name,child)
    check(name+'_nested',parent['started_ns'] <= child['started_ns'] <= child['closed_ns'] <= parent['closed_ns'])

archive=js(BASE/'EXTERNAL_ARCHIVE.json')
mapping={r['original_relative_path']:r for r in archive['files']}
def ar_bytes(rel):
    rec=mapping[rel]
    data=read(REPO/rec['archive_path'])
    eq('archive_input_hash:'+rel,hashlib.sha256(data).hexdigest(),rec['sha256'])
    eq('archive_input_size:'+rel,len(data),rec['bytes'])
    return data
def ar(rel): return json.loads(ar_bytes(rel))
def lines(rel): return [json.loads(x) for x in ar_bytes(rel).splitlines() if x]

frozen=js(BASE/'FROZEN.json')
units=js(BASE/'units_01/UNIT_RESULT.json')
unit_log=read(BASE/'units_01/UNIT_TESTS.txt').decode()
processes={n:js(BASE/(n+'_PROCESS.json')) for n in ['UNIT','ACTUAL','BENCHMARK']}
for name,p in processes.items():
    clock(name+'_process',p)
    eq(name+'_exit',p['exit_code'],0)
    check(name+'_after_freeze',p['started_ns']>frozen['closed_before_publication_ns'])
eq('freeze_execution_count',frozen['candidate_functions_tests_rasters_model_calls_before_freeze'],0)
eq('freeze_pairs',frozen['benchmark_pair_count'],5)
eq('freeze_warmups',frozen['benchmark_warmups'],0)
eq('freeze_raster_cap',frozen['new_raster_hard_cap'],4)
eq('freeze_text_gate',frozen['text_gate_bytes'],48162)
eq('unit_methods',units['run'],86)
eq('unit_selected_unique',len(set(units['selected_method_ids'])),86)
new=[x for x in units['selected_method_ids'] if x.split('.')[1] in ('test_active_observation_region_world','test_active_observation_region_anchors','test_active_observation_region_delivery')]
eq('unit_new_methods',len(new),22)
eq('unit_old_methods',len(units['selected_method_ids'])-len(new),64)
eq('unit_log_success_lines',sum(x.rstrip().endswith(' ... ok') for x in unit_log.splitlines()),86)
for k in ['errors','failures','forbidden_calls']: eq('units_'+k,units[k],[])
for k in ['real_rasters','Blender_processes']: eq('units_'+k,units[k],0)
eq('unit_help_children',len(units['Python_test_children']),1)
eq('unit_help_exit',units['Python_test_children'][0]['exit_code'],0)

prefix='run/acceptance_01/'
actual=ar(prefix+'RESULTS.json')
finish=ar(prefix+'server/FINISH.json')
captures=lines(prefix+'server/CAPTURES.jsonl')
indexes=lines(prefix+'server/INDEXES.jsonl')
observes=lines(prefix+'server/RESULTS.jsonl')
intents=lines('run/render_budget/INTENTS.jsonl')
eq('actual_request_count',len(actual['requests']),3)
eq('actual_cases',[x['case'] for x in actual['requests']],['joined_cold','joined_hot','cached_full'])
eq('captures_actual',len(captures),3)
eq('prepare_actual',len(indexes),1)
eq('observe_actual',len(observes),3)
eq('intents_actual',len(intents),3)
eq('intent_views',[x['fields']['view_name'] for x in intents],['SCENE','BACK','LEFT'])
eq('intent_numbers',[x['attempt'] for x in intents],[1,2,3])
for key,want in [('capture_calls',3),('prepare_calls',1),('observe_calls',3),('raster_intents',3),('new_model_calls',0)]:eq('finish_'+key,finish[key],want)
for key in ['failure','source_check_error']: eq('finish_'+key,finish[key],None)
eq('finish_record',actual['server_finish'],finish)
eq('budget_prior',actual['prior_charged_raster_attempts'],0)
eq('budget_new',actual['new_raster_attempts'],3)
eq('budget_total',actual['global_charged_raster_attempts'],3)
eq('budget_cap',actual['global_raster_hard_cap'],4)
eq('intent_directory_count',len(actual['charged_attempt_directories']),3)
for idx,row in enumerate(intents,1):eq('intent_individual:'+str(idx),ar('run/render_budget/attempt_%02d/INTENT.json'%idx),row)

tx_total=rx_total=image_total=png_consumed=text_total=0
request_metrics=[]
raw_results=[]
for i in range(1,6):
    stem=prefix+'stdio/rpc_%02d/'%i
    txb,rxb=ar_bytes(stem+'TX.bin'),ar_bytes(stem+'RX.bin')
    tx,rx=json.loads(txb),json.loads(rxb)
    receipt=ar(stem+'RECEIPT.json')
    eq('rpc_saved_response:%d'%i,ar(stem+'RESPONSE.json'),rx)
    eq('rpc_matching_id:%d'%i,tx['id'],rx['id'])
    eq('rpc_bytes_tx:%d'%i,len(txb),receipt['TX_bytes'])
    eq('rpc_bytes_rx:%d'%i,len(rxb),receipt['RX_bytes'])
    eq('rpc_rx_hash:%d'%i,hashlib.sha256(rxb).hexdigest(),receipt['RX_sha256'])
    clock('rpc_elapsed:%d'%i,receipt)
    eq('rpc_error:%d'%i,receipt['error'],None)
    tx_total+=len(txb); rx_total+=len(rxb)
    eq('rpc_method:%d'%i,tx['method'],['initialize','tools/list','tools/call','tools/call','tools/call'][i-1])
    if i < 3: continue
    req=actual['requests'][i-3]
    result=ar(prefix+'server/RESULT_%02d.json'%(i-2));raw_results.append(result)
    consumer=ar(prefix+'consumer_'+req['case']+'/READBACK.json')
    content=rx['result']['content']
    texts=[v['text'] for v in content if v['type']=='text']; images=[v for v in content if v['type']=='image']
    eq('one_text:'+req['case'],len(texts),1);eq('three_images:'+req['case'],len(images),3)
    eq('consumer_text:'+req['case'],json.loads(texts[0]),consumer['text'])
    text_bytes=len(texts[0].encode('utf8'));text_total+=text_bytes
    eq('text_size:'+req['case'],text_bytes,[42045,42045,315585][i-3])
    if i < 5:check('brief_gate:'+req['case'],text_bytes<=frozen['text_gate_bytes'])
    eq('request_elapsed:'+req['case'],consumer['closed_ns']-req['started_ns'],req['elapsed_to_consumer_ns'])
    clock('consumer_elapsed:'+req['case'],consumer)
    eq('consumer_model_calls:'+req['case'],consumer['model_calls'],0)
    decoded=[base64.b64decode(img['data'],validate=True) for img in images]
    image_total+=len(images);png_consumed+=sum(map(len,decoded))
    eq('consumer_png_bytes:'+req['case'],sum(map(len,decoded)),consumer['PNG_bytes'])
    for j,data in enumerate(decoded,1):eq('consumer_saved_image:'+req['case']+str(j),data,ar_bytes(prefix+'consumer_'+req['case']+'/image_%02d.png'%j))
    work=result['work'];eq('work_receipt:'+req['case'],work,req['work'])
    eq('capture_once:'+req['case'],work['capture_calls'],1)
    eq('raster_count:'+req['case'],work['raster_attempts'],3 if i==3 else 0)
    eq('raster_completed:'+req['case'],work['raster_completed'],3 if i==3 else 0)
    if i>3:
        for k in ['geometry_parse_calls','prepare_calls','mapping_calls','patch_mapping_calls','mesh_conversions','PNG_bytes','NPZ_bytes','array_payload_bytes']:eq('hot_no_'+k+':'+req['case'],work[k],0)
        eq('frame_reuses:'+req['case'],work['frame_reuses'],3)
        eq('reused_generation_stages:'+req['case'],result['generation_stages'],raw_results[0]['generation_stages'])
    request_metrics.append({'case':req['case'],'text_bytes':text_bytes,'elapsed_to_consumer_ns':req['elapsed_to_consumer_ns'],'rpc_elapsed_ns':receipt['elapsed_ns'],'consumer_decode_ns':consumer['elapsed_ns']})
eq('rpc_total_tx',tx_total,904);eq('rpc_total_rx',rx_total,491182)
eq('native_blocks',image_total,9);eq('consumed_png_bytes',png_consumed,26457)
for row in captures:
    clock('capture_clock:'+str(row['index']),row)
    eq('capture_once_extra:'+str(row['index']),row['additional_host_capture_calls'],0)
for row in indexes:
    clock('prepare_clock',row);eq('prepare_extra',row['extra_prepare_calls'],0)
for row in observes:
    clock('observe_clock:'+str(row['index']),row);eq('observe_extra:'+str(row['index']),row['extra_observe_calls'],0)
    eq('observe_one_capture:'+str(row['index']),len(row['capture_associations']),1)

cold=raw_results[0];stages=cold['stages']
for name,row in stages.items():clock('cold_stage:'+name,row)
nested_clock('world_in_prepare',stages['world_descriptions'],stages['prepare'])
nested_clock('index_in_prepare',stages['index'],stages['prepare'])
loc_time=readability_time=png_bytes=npz_bytes=payload=temporary=0;temp_max=0
for frame in cold['frames']:
    view=frame['view_name'];fs=frame['feedback_stages']
    for name,row in fs.items():clock(view+':'+name,row)
    nested_clock(view+'_location_in_readability',fs['pixel_localization'],fs['readability'])
    loc_time+=fs['pixel_localization']['elapsed_ns'];readability_time+=fs['readability']['elapsed_ns']
    t=fs['pixel_localization']['named_temporary_array_bytes'];temporary+=t;temp_max=max(temp_max,t)
    eq(view+'_new_cached_arrays',fs['pixel_localization']['new_cached_array_bytes'],0)
    rel=lambda p:str(p).replace('\\','/').split('/run/',1)[1]
    png=ar_bytes('run/'+rel(frame['image_path']));npz=ar_bytes('run/'+rel(frame['arrays_path']))
    png_bytes+=len(png);npz_bytes+=len(npz)
    with np.load(BytesIO(npz),allow_pickle=False) as data:
        nbytes=sum(data[key].nbytes for key in data.files);payload+=nbytes
        eq(view+'_array_payload',nbytes,frame['array_payload_bytes'])
        for key in data.files:eq(view+'_array_bytes:'+key,data[key].nbytes,frame['arrays'][key]['nbytes'])
    eq(view+'_png_size',len(png),frame['PNG_bytes']);eq(view+'_npz_size',len(npz),frame['compressed_array_file_bytes'])
eq('world_ns',stages['world_descriptions']['elapsed_ns'],2412500)
eq('index_ns',stages['index']['elapsed_ns'],3277635200)
eq('pixel_loc_ns',loc_time,1783700);eq('readability_ns',readability_time,6571900)
eq('generated_png_bytes',png_bytes,8819);eq('generated_npz_bytes',npz_bytes,93904);eq('generated_array_payload',payload,15029688)
eq('temp_array_sum',temporary,2614707);eq('temp_array_max',temp_max,1312284)

cleanup=ar(prefix+'stdio/CLOSE.json');qaclose=ar(prefix+'qa/CLOSE.json');initial=ar(prefix+'qa/INITIAL.json')
eq('stdio_cleanup_receipt',cleanup,actual['stdio_cleanup']);clock('stdio_cleanup_clock',cleanup)
eq('launcher_pid',cleanup['pid'],26484);eq('server_pid',finish['pid'],22452)
for k,v in [('confirmed',True),('exit_code',0),('forced_kill',False),('reader_stopped',True),('process_handle_closed',True),('errors',[])]:eq('stdio_cleanup_'+k,cleanup[k],v)
eq('pipes_closed',cleanup['pipes_closed'],{'stderr':True,'stdin':True,'stdout':True})
for k,v in [('confirmed',True),('exit_code',0),('forced_kill',False),('held_handle_closed',True),('pid',5028)]:eq('QA_cleanup_'+k,actual['QA_cleanup'][k],v)
eq('qa_final_no_saves',qaclose['file_saves'],0);eq('qa_final_no_render',qaclose['Blender_render_calls'],0)
eq('qa_initial_final_snapshot',qaclose['final_snapshot'],initial)
eq('qa_failure',qaclose['failure'],None);eq('cleanup_errors',actual['cleanup_errors'],[])
check('finish_before_launcher_close',finish['closed_ns']<=cleanup['closed_ns'])
check('all_cleanup_before_result_publish',max(cleanup['closed_ns'],actual['QA_cleanup']['closed_ns'])<=actual['closed_before_publication_ns'])
check('result_before_outer_end',actual['closed_before_publication_ns']<processes['ACTUAL']['closed_ns'])

bench=js(BASE/'BENCHMARK.json')
eq('bench_ncalls',len(bench['calls']),10);eq('bench_npairs',len(bench['pairs']),5)
eq('bench_warmups',bench['warmup_calls'],0)
for k in ['new_raster_calls','new_model_calls','new_geometry_discovery_calls']:eq('bench_'+k,bench[k],0)
expected_order=[['reference','optimized'],['optimized','reference'],['reference','optimized'],['optimized','reference'],['reference','optimized']]
eq('bench_fixed_order',bench['pair_order'],expected_order)
for i,pair in enumerate(bench['pairs'],1):
    calls=[c for c in bench['calls'] if c['pair']==i]
    eq('pair_order:'+str(i),[c['variant'] for c in calls],expected_order[i-1])
    eq('pair_counts_equal:'+str(i),pair['counts_equal'],True);eq('pair_locations_equal:'+str(i),pair['locations_equal'],True)
    clock('pair_comparison:'+str(i),{'started_ns':pair['comparison_started_ns'],'closed_ns':pair['comparison_closed_ns'],'elapsed_ns':pair['comparison_elapsed_ns']})
    for c in calls:
        clock('bench_call:'+str(i)+c['variant'],c)
        eq('bench_pair_time:'+str(i)+c['variant'],pair[c['variant']+'_ns'],c['elapsed_ns'])
        check('bench_call_before_comparison:'+str(i)+c['variant'],c['closed_ns']<=pair['comparison_started_ns'])
    eq('pair_output_counts_stable:'+str(i),pair['output_counts'],bench['pairs'][0]['output_counts'])
    eq('pair_output_locations_stable:'+str(i),pair['output_locations'],bench['pairs'][0]['output_locations'])
    for data in [*pair['output_counts'].values(),*pair['output_locations'].values()]:eq('pair_output_length:'+str(i),len(data),138)
raw={v:[c['elapsed_ns'] for c in bench['calls'] if c['variant']==v] for v in ['reference','optimized']}
for v,vals in raw.items():
    eq('bench_arm_count:'+v,len(vals),5)
    eq('bench_summary:'+v,bench['summary'][v],{'calls':5,'sum_ns':sum(vals),'median_ns':statistics.median(vals),'minimum_ns':min(vals),'maximum_ns':max(vals),'raw_ns':vals})
ratio=Fraction(statistics.median(raw['optimized']),statistics.median(raw['reference']))
eq('bench_median_ratio',float(ratio),bench['ratio_of_medians'])
eq('bench_sum_ratio',sum(raw['optimized'])/sum(raw['reference']),bench['ratio_of_sums'])
check('bench_times_in_outer',processes['BENCHMARK']['started_ns']<bench['calls'][0]['started_ns']<bench['calls'][-1]['closed_ns']<processes['BENCHMARK']['closed_ns'])
eq('actual_full_outer_ns',processes['ACTUAL']['elapsed_ns'],7707836700)

audit_corrections=js(BASE/'review/SOURCE_AUDIT_R1.json')
eq('historical_source_audit_preserved_failure',audit_corrections['passed'],False)
quality=js(BASE/'review/QUALITY.json')
check('quality_history_retained',bool(quality.get('attempt_history')))
result={'passed':all(c['passed'] for c in checks),'checks':len(checks),'failed':[c for c in checks if not c['passed']],
 'metrics':{'requests':request_metrics,'stdio_TX_bytes':tx_total,'stdio_RX_bytes':rx_total,'native_images':image_total,'PNG_consumed_bytes':png_consumed,'raster_attempts':len(intents),'world_descriptions_ns':stages['world_descriptions']['elapsed_ns'],'pixel_locations_ns':loc_time,'index_ns':stages['index']['elapsed_ns'],'readability_ns':readability_time,'named_localization_temporary_bytes_sum':temporary,'named_localization_temporary_bytes_max':temp_max,'benchmark_raw_ns':raw,'benchmark_median_ratio_exact':str(ratio),'benchmark_median_improvement_percent':float((1-ratio)*100),'benchmark_setup_ns':bench['timing']['setup_ns'],'benchmark_outer_ns':processes['BENCHMARK']['elapsed_ns'],'acceptance_outer_ns':processes['ACTUAL']['elapsed_ns']},
 'limits':['No product, author audit/scorer, unit tests, raster, Blender, model or benchmark executed in this review.','Benchmark equality relies on frozen run-time full comparison and saved booleans; separate candidate per-call outputs were not saved.','Array byte counts are payloads, not heap or RSS; no incremental Python heap/process memory attributed to localization.','Server PID has FINISH/EOF; independently held process handle belongs to launcher, not server.','Overall model task time, answer quality, model token/fee benefit unmeasured.'],
 'check_details':checks,'inputs':inputs}
for path,rec in list(inputs.items()):
    data=Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest()!=rec['sha256']:raise RuntimeError('input changed:'+path)
result['input_hashes_stable']=True
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:result[k] for k in ['passed','checks','failed','metrics']},ensure_ascii=False))
