"""Independent offline cost/lifecycle audit; imports no Human Eye product."""
from pathlib import Path
import base64
import collections
import hashlib
import json
import time

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
D = ROOT / 'verification/m4_active_observation_brief_delivery_001'
OUT = Path(__file__).parent / 'cost_audit.json'
started = time.perf_counter_ns()
checks = []
evidence = {}

def check(label, condition, actual=None):
    checks.append({'label': label, 'passed': bool(condition), 'actual': actual})

def read(path):
    p = Path(path)
    raw = p.read_bytes()
    evidence[str(p)] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return raw

def js(path):
    return json.loads(read(path))

manifest = js(D/'EXTERNAL_ARCHIVE.json')
mapping = {row['original_relative_path']: row for row in manifest['files']}

def ext(relative):
    row = mapping[relative]
    path = ROOT / row['archive_path']
    raw = read(path)
    check('archive_bytes:'+relative, len(raw) == row['bytes'])
    check('archive_sha:'+relative, hashlib.sha256(raw).hexdigest() == row['sha256'])
    return raw

def xjs(relative):
    return json.loads(ext(relative))

def rows(relative):
    return [json.loads(row) for row in ext(relative).splitlines()]

prefix = 'run/replay_01/'
result = xjs(prefix+'RESULTS.json')
summary = js(D/'RESULT_SUMMARY.json')
receipts = []
txs, rxs = [], []
response_by_id = {}
request_by_id = {}
raw_by_id = {}

def raw_json_value(raw, path):
    """Locate the exact original JSON substring, retaining its wire whitespace."""
    text=raw.decode('utf8')
    decoder=json.JSONDecoder()
    def space(i):
        while i<len(text) and text[i].isspace():
            i+=1
        return i
    def locate(i, parts):
        i=space(i)
        if not parts:
            _,end=decoder.raw_decode(text,i)
            return text[i:end].encode('utf8')
        key=parts[0]
        if text[i]=='{':
            i=space(i+1)
            while text[i]!='}':
                name,j=decoder.raw_decode(text,i)
                j=space(j)
                assert text[j]==':'
                j=space(j+1)
                if name==key:
                    return locate(j,parts[1:])
                _,i=decoder.raw_decode(text,j)
                i=space(i)
                if text[i]==',':
                    i=space(i+1)
        elif text[i]=='[':
            i=space(i+1)
            index=0
            while text[i]!=']':
                if index==key:
                    return locate(i,parts[1:])
                _,i=decoder.raw_decode(text,i)
                i=space(i)
                if text[i]==',':
                    i=space(i+1)
                index+=1
        raise KeyError(path)
    return locate(0,path)
for i in range(1,18):
    folder = prefix+'stdio/rpc_'+str(i).zfill(2)+'/'
    tx, rx = ext(folder+'TX.bin'), ext(folder+'RX.bin')
    txs.append(tx)
    rxs.append(rx)
    request, response = json.loads(tx), json.loads(rx)
    receipt = xjs(folder+'RECEIPT.json')
    receipts.append(receipt)
    rid = request['id']
    request_by_id[rid] = request
    response_by_id[rid] = response
    raw_by_id[rid] = rx
    check('rpc_identity:'+str(i), rid == response['id'] == receipt['id'])
    check('rpc_rawsizes:'+str(i), len(tx)==receipt['TX_bytes'] and len(rx)==receipt['RX_bytes'])
    check('rpc_hash:'+str(i), hashlib.sha256(rx).hexdigest()==receipt['RX_sha256'])
    check('rpc_time:'+str(i), receipt['elapsed_ns']==receipt['closed_ns']-receipt['started_ns'])
    check('rpc_time_order:'+str(i), receipt['started_ns']<=receipt['stdin_flushed_ns']<=receipt['received_complete_ns']<=receipt['consumer_json_decoded_ns']<=receipt['closed_ns'])
    check('rpc_no_error:'+str(i), receipt['error'] is None)

cases = ('ordinary','same_source_repeat','recovery_rename_baseline','renamed_source','nonplanar_source')
details = ('default','brief','full')
check('protocol_methods', [r['method'] for r in request_by_id.values()] == ['initialize','tools/list']+['tools/call']*15)
check('case_order', list(response_by_id)[2:] == [case+'__'+detail for case in cases for detail in details])
check('controller_records', len(result['records'])==15)
text_totals=collections.Counter()
image_blocks=image_bytes=image_json_bytes=base64_chars=text_block_bytes=0
compact_image_json_bytes=compact_text_block_bytes=0
case_bytes=[]
request_times=[]
for case in cases:
    old = js(D/'inputs'/case/'RX.bin')
    old_text=old['result']['content'][0]['text']
    sizes={'case':case,'historical':len(old_text.encode('utf8'))}
    for detail in details:
        rid=case+'__'+detail
        response=response_by_id[rid]
        request=request_by_id[rid]
        public=response['result']['content']
        check('response_ok:'+rid,response['result']['isError'] is False)
        check('single_text:'+rid,len([b for b in public if b['type']=='text'])==1)
        text=public[0]['text']
        n=len(text.encode('utf8'))
        text_totals[detail]+=n
        sizes[detail]=n
        check('request_detail:'+rid,request['params']['arguments'].get('response_detail','default')==detail)
        images=public[1:]
        check('images_count:'+rid,len(images)==len(old['result']['content'][1:]))
        # Image preservation here supports the cost denominator, not a second pixel semantics test.
        check('image_content_identical:'+rid,images==old['result']['content'][1:])
        image_blocks+=len(images)
        for bi,block in enumerate(images,1):
            image_bytes+=len(base64.b64decode(block['data'],validate=True))
            base64_chars+=len(block['data'])
            compact_image_json_bytes+=len(json.dumps(block,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode('utf8'))
            block_raw=raw_json_value(raw_by_id[rid],['result','content',bi])
            image_json_bytes+=len(block_raw)
            check('wire_image_block_span:'+rid+':'+str(bi),json.loads(block_raw)==block)
        compact_text_block_bytes+=len(json.dumps(public[0],ensure_ascii=True,sort_keys=True,separators=(',',':')).encode('utf8'))
        block_raw=raw_json_value(raw_by_id[rid],['result','content',0])
        text_block_bytes+=len(block_raw)
        check('wire_text_block_span:'+rid,json.loads(block_raw)==public[0])
        row=next(r for r in result['records'] if r['request_id']==rid)
        check('consumer_cost:'+rid,row['elapsed_to_consumer_images_ns']==row['consumer_images_read_ns']-row['started_ns'])
        check('record_time:'+rid,row['elapsed_ns']==row['closed_ns']-row['started_ns'])
        check('record_order:'+rid,row['started_ns']<=row['response_received_ns']<=row['consumer_images_read_ns']<=row['closed_ns'])
        check('record_sizes:'+rid,row['public_text_UTF8_bytes']==n and row['native_image_blocks']==len(images))
        request_times.append({'id':rid,'request_to_consumer_read_ns':row['elapsed_to_consumer_images_ns'],
                              'record_total_ns':row['elapsed_ns']})
    check('default_brief_equal:'+case,response_by_id[case+'__default']['result']==response_by_id[case+'__brief']['result'])
    check('default_case_budget:'+case,sizes['default'] <= (2048 if case=='nonplanar_source' else 8192))
    case_bytes.append(sizes)

old_total=sum(r['historical'] for r in case_bytes)
check('fixed_historical_denominator',old_total==101824)
check('actual_default_total',text_totals['default']==27745)
check('aggregate_byte_budget',text_totals['default']*100<=old_total*35)
check('summary_totals',summary['historical_text_UTF8_bytes']==old_total and summary['five_case_default_UTF8_bytes']==text_totals['default'])
check('summary_saving',summary['reduction_bytes']==old_total-text_totals['default'] and abs(summary['reduction_percent']-(1-text_totals['default']/old_total)*100)<1e-10)
check('raw_stdio_complete',ext(prefix+'stdio/stdout.raw.bin')==b''.join(rxs))
check('stderr_empty',ext(prefix+'stdio/stderr.raw.bin')==b'')
check('raw_protocol_totals',sum(map(len,txs))==3832==result['RPC_TX_bytes'] and sum(map(len,rxs))==311634==result['RPC_RX_bytes'])
check('image_totals',image_blocks==24==result['native_image_blocks'] and image_bytes==83400==result['native_PNG_bytes'] and base64_chars==111216==result['native_base64_characters'])
check('wire_JSON_block_byte_totals',image_json_bytes==112512 and text_block_bytes==168844)

projection=rows(prefix+'server/PROJECTION_PHASES.jsonl')
content=rows(prefix+'server/CONTENT_PHASES.jsonl')
wire=rows(prefix+'server/WIRE_ENCODING_PHASES.jsonl')
service=rows(prefix+'server/SERVICE_CALLS.jsonl')
events=rows(prefix+'server/PRODUCT_EVENTS.jsonl')
check('phase_counts',(len(projection),len(content),len(wire),len(service),len(events))==(10,15,17,15,15))
for category,values in [('projection',projection),('content',content),('wire',wire),('service',service)]:
    for i,row in enumerate(values):
        check(category+':elapsed:'+str(i),row['elapsed_ns']==row['closed_ns']-row['started_ns'] and row['elapsed_ns']>=0)
        if 'error' in row:
            check(category+':noerror:'+str(i),row['error'] is None)
for i,row in enumerate(projection):
    parent=next(c for c in content if c['call']['index']==row['call']['index'])
    check('projection_nested:'+str(i),parent['started_ns']<=row['started_ns']<=row['closed_ns']<=parent['closed_ns'])
    check('projection_actual:'+str(i),row['returned_projection'] and row['call']['response_detail']!='full')
for i,row in enumerate(wire):
    check('wire_CR_extra:'+str(i),len(rxs[i])-row['UTF8_bytes']==1 and rxs[i].endswith(b'\r\n'))
    check('wire_id:'+str(i),row['request_id']==receipts[i]['id'])
for i,row in enumerate(service):
    check('zero_new_scene_work:'+str(i),all(row[k]==0 for k in ['actual_new_capture_calls','actual_new_prepare_calls','actual_new_raster_attempts','actual_new_local_image_constructions']))
    check('fixed_historical_source:'+str(i),row['historical_response_sha256']==hashlib.sha256(read(D/'inputs'/row['case']/'RX.bin')).hexdigest())
delivery=[]
for i,event in enumerate(events):
    d=event['fields']['image_delivery']
    delivery.append(d)
    check('construction_accounted:'+str(i),d['native_blocks_constructed']==len(d['frames']) and d['mcp_content_ready'] and d['status']=='constructed')
    check('consumer_not_faked:'+str(i),d['consumer_read_status']=='unconfirmed')
    check('delivery_timing:'+str(i),d['elapsed_ns']==d['closed_ns']-d['started_ns'])
    for k in ['PNG_bytes','base64_chars']:
        fkey={'PNG_bytes':'PNG_bytes_read','base64_chars':'base64_chars'}[k]
        check('delivery_'+k+':'+str(i),d[k]==sum(f[fkey] for f in d['frames']))

outer=js(D/'runs/REPLAY_01_PROCESS.json')
env=js(D/'preparation/ENVIRONMENT.json')
build=js(D/'build/BUILD_INSTALL.json')
unit=js(D/'units/UNIT_RESULT.json')
start=xjs(prefix+'stdio/START.json')
close=xjs(prefix+'stdio/CLOSE.json')
serverstart=xjs(prefix+'server/START.json')
serverend=xjs(prefix+'server/FINISH.json')
stub=xjs(prefix+'server/STUB_CLOSE.json')
for label,row,endkey,durationkey in [('outer',outer,'closed_after_exit_ns','elapsed_ns'),('controller',result,'closed_before_publication_ns','elapsed_before_publication_ns'),('cleanup',close,'closed_ns','elapsed_ns')]:
    check(label+':duration',row[endkey]-row['started_ns']==row[durationkey])
check('whole_controller_in_outer',outer['started_ns']<=result['started_ns']<=result['closed_before_publication_ns']<=outer['closed_after_exit_ns'])
check('cleanup_before_end',close['closed_ns']<=result['closed_before_publication_ns'])
check('server_finish_before_held_wait',serverstart['pid']==serverend['pid'] and serverend['closed_ns']<=close['closed_ns'])
check('held_pid_matches',start['pid']==close['pid'])
check('held_exit',close['exit_code']==0 and close['confirmed'] and not close['forced_kill'])
check('held_cleanup',close['reader_stopped'] and close['process_handle_closed'] and all(close['pipes_closed'].values()) and not close['errors'])
check('server_success',serverend['failure'] is None and serverend['source_error'] is None and serverend['service_calls']==15)
check('stub_closed',stub['fixed_call_count_completed'] and stub['calls']==15 and stub['actual_new_capture_prepare_raster_calls']==0)
check('outer_exit',outer['exit_code']==0)
check('controller_success',result['passed'] and not result['cleanup_errors'])
check('unit_outcome',unit['run']==33 and unit['passed'] and not unit['errors'] and not unit['failures'] and not unit['forbidden_calls'])
check('unit_child',len(unit['Python_test_children'])==1 and unit['Python_test_children'][0]['exit_code']==0)
check('env_build_success',env['venv_exit_code']==0 and build['pip_exit_code']==0)

phase_sums={name:sum(r['elapsed_ns'] for r in values) for name,values in [('projection',projection),('active_content',content),('wire_encoding',wire),('historical_service',service)]}
phase_sums.update({k:sum(f[k] for d in delivery for f in d['frames']) for k in ['read_ns','validate_ns','base64_ns']})
output={
    'schema':'root-brief-delivery-cost-review-v1',
    'candidate':'cdd2b11693a2586cfea07528c6bca27b93d02499',
    'review_scope':'Independent JSON/byte/timestamp recomputation, no imported product or rerun business calls.',
    'passed':all(c['passed'] for c in checks),'check_count':len(checks),
    'failures':[c for c in checks if not c['passed']],
    'bytes':{'historical_default':old_total,'text_per_detail':dict(text_totals),'case_bytes':case_bytes,
             'reduction':old_total-text_totals['default'],'reduction_fraction':1-text_totals['default']/old_total,
             'all_text':sum(text_totals.values()),'text_block_JSON':text_block_bytes,
             'compact_text_block_JSON_for_comparison_only':compact_text_block_bytes,
             'compact_image_block_JSON_for_comparison_only':compact_image_json_bytes,
             'images':image_blocks,'PNG':image_bytes,'base64':base64_chars,'image_block_JSON':image_json_bytes,
             'TX':sum(map(len,txs)),'RX':sum(map(len,rxs)),
             'wire_serializer_UTF8':sum(r['UTF8_bytes'] for r in wire),'wire_CR_extra':len(wire)},
    'phase_elapsed_sums_ns':phase_sums,
    'requests':request_times,
    'wallclock_windows_ns':{'environment':env['closed_before_publication_ns']-env['started_ns'],
         'build_install':build['closed_before_publication_ns']-build['started_ns'],
         'units':unit['closed_before_publication_ns']-unit['started_ns'],
         'outer_replay':outer['elapsed_ns'],'controller':result['elapsed_before_publication_ns'],
         'server_setup':serverstart['ready_ns']-serverstart['started_ns'],
         'held_cleanup':close['elapsed_ns']},
    'lifecycle':{'held_launcher_pid':start['pid'],'server_executor_pid':serverend['pid'],'unit_help_pid':unit['Python_test_children'][0]['pid'],
                 'held_cleanup':close,'server_finish':serverend,'scope':'Held launcher exit and handle cleanup are explicit; executor has FINISH/source/EOF evidence, not a separately held executor-handle receipt.'},
    'denominators':{'old_responses':5,'old_PNG_files':8,'RPC':17,'tool_requests':15,'projections':10,'content_constructions':15,'image_blocks':24,'units':33,'formal_replay_attempts':1},
    'limits':['72.75% is default text-byte reduction on five historical responses; not token, fee, model quality or full-task speedup.',
      'Projection runs inside content; projection evidence fsync also falls inside content timer. Stage sums are overlapping and instrumented, not a latency A/B.',
      'Initial initialize includes service startup; first consumer image decode includes PIL lazy startup. Sequential timing does not establish per-format performance.',
      'Full has 2160 fewer bytes after registered PNG path relocation; this is kept separate from semantic projection savings.',
      'This audit did not rerun unit or business calls. Passed counts verify author raw logs, not new test execution.',
      'Model token/fee/quality, RSS, unmarked preparation and post-replay audit/Git publication time remain unmeasured.'],
    'own_audit_correction':{'initial_result_retained':'cost_audit_initial_compact_JSON_assumption.json',
        'problem':'Initial independent audit measured JSON child blocks by compact reserialization, omitting wire spaces. Raw values/TX/RX and all historical byte-savings checks were unaffected.',
        'correction':'Now locate exact original RX substrings. Actual image-block JSON 112512B and text-block JSON 168844B match author; compact values retained as a separately named non-wire representation.',
        'new_business_calls':0},
    'checks':checks,'evidence':evidence,
    'own_cost':{'started_ns':started,'closed_before_write_ns':time.perf_counter_ns(),'new_product_Blender_raster_model_calls':0}
}
OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:output[k] for k in ('passed','check_count','failures','bytes','phase_elapsed_sums_ns','wallclock_windows_ns')},ensure_ascii=False))
