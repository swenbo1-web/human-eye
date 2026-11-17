"""Independent fixed-Git, raw-byte, lifecycle and cost qualification audit."""
from pathlib import Path
import ast
import base64
import csv
import hashlib
import io
import json
import subprocess
import sys
import traceback
import zipfile
import zlib

HERE=Path(__file__).resolve().parent
REPO=Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
AREA=REPO/'verification/m4_source_region_display_001'
RUNTIME=Path('D:/he_m4_source_region_display_001')
FINAL='aa45f033ce662b7453dda77084b36da34640f558'
PRODUCT='29f35a771c1d137455602adf28418f45e2788e6a'
SOURCE='af7c2cf6715e11f237e878fd6f66047d632b48e528f6b5abe28f6da66b5e232c'
CHECKS=[]
PINS={}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(path):
    path=Path(path).resolve();data=path.read_bytes()
    pin=dict(path=str(path),bytes=len(data),sha256=sha(data))
    if str(path) in PINS and PINS[str(path)]!=pin:raise ValueError('input_changed/'+str(path))
    PINS[str(path)]=pin
    return data


def read(path):
    return json.loads(raw(path))


def lines(path):
    return [json.loads(line) for line in raw(path).splitlines() if line.strip()]


def check(name,value):
    CHECKS.append(dict(name=name,passed=bool(value)))


def git(*args):
    return subprocess.check_output(['git','-C',str(REPO),*args])


def blobs(specs):
    specs=list(dict.fromkeys(specs))
    stream=subprocess.run(['git','-C',str(REPO),'cat-file','--batch'],input=('\n'.join(specs)+'\n').encode(),stdout=subprocess.PIPE,check=True).stdout
    pos=0;out={}
    for spec in specs:
        end=stream.index(b'\n',pos);header=stream[pos:end].split()
        if len(header)!=3 or header[1]!=b'blob':raise ValueError('missing_blob/'+spec)
        size=int(header[2]);pos=end+1;out[spec]=stream[pos:pos+size];pos+=size+1
    check('git/complete_batch',pos==len(stream))
    return out


def pin_matches(pin,data):
    return sha(data)==pin['sha256'] and ('bytes' not in pin or len(data)==pin['bytes'])


def embedded_sources(code):
    result={}
    for node in ast.walk(ast.parse(code)):
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and len(node.value)>500:
            try:data=zlib.decompress(base64.b64decode(node.value,validate=True))
            except (ValueError,zlib.error):continue
            result[sha(data)]=data
    return result


def bounded_string(node,names):
    if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
    if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):return bounded_string(node.left,names)+bounded_string(node.right,names)
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='repr' and len(node.args)==1 and isinstance(node.args[0],ast.Name):return repr(names[node.args[0].id])
    raise ValueError('counter_code_expression_outside_fixed_string')


def main():
    manifest=read(AREA/'CONTENT_MANIFEST.json');archive=read(AREA/'RUNTIME_ARCHIVE.json')
    baseline=read(AREA/'BASELINE.json');binding=read(AREA/'R0_RUN_BINDING.json');freeze=read(AREA/'SOURCE_FREEZE.json')
    ns=AREA.relative_to(REPO).as_posix()
    paths={ns+'/'+r['path'] for r in manifest['files']}|{ns+'/CONTENT_MANIFEST.json'}
    changed=set(git('diff','--name-only',baseline['baseline_git'],FINAL).decode().splitlines())
    product_paths={'human_eye_plugin/'+p for p in ('active_observation_images.py','attention_raster.py','blender_host.py','live_service.py','live_spatial_mcp.py','source_region.py')}
    check('git/namespace_569',len(paths)==569 and paths=={p for p in changed if p.startswith(ns+'/')})
    check('git/separate_six_product_and_host_test',changed-paths==product_paths|{'verification/test_source_region_display_host.py'})
    specs=[FINAL+':'+p for p in sorted(changed)]+[PRODUCT+':'+p['path'] for p in binding['source_manifest']]
    worker_paths=('human_eye_plugin/blender_worker.py','examples/blender_worker.py')
    specs += [baseline['baseline_git']+':'+p for p in worker_paths]
    fixed=blobs(specs)
    for row in manifest['files']:
        data=raw(AREA/row['path']);check('git/member/'+row['path'],pin_matches(row,data) and data==fixed[FINAL+':'+ns+'/'+row['path']])
    check('git/manifest_self',raw(AREA/'CONTENT_MANIFEST.json')==fixed[FINAL+':'+ns+'/CONTENT_MANIFEST.json'])
    for p in changed-paths:check('git/other/'+p,raw(REPO/p)==fixed[FINAL+':'+p])
    current_files={p.relative_to(RUNTIME).as_posix() for p in RUNTIME.rglob('*') if p.is_file()}
    check('runtime/complete_original_set',len(current_files)==501 and current_files=={p['relative'] for p in archive['files']} and archive['runtime_exclusions']==[])
    total=0
    for row in archive['files']:
        data=raw(RUNTIME/row['relative']);copy=raw(AREA/row['copy']);total+=len(data)
        check('runtime/copy/'+row['relative'],data==copy and pin_matches(row,data))
    check('runtime/bytes',total==archive['bytes']==217130593)
    check('source/frozen_manifest',freeze['runtime_manifest']==binding['source_manifest'] and freeze['product_git']==binding['preparation_git']==PRODUCT and freeze['source_sha256']==SOURCE)
    aggregate=sha(json.dumps({k:binding[k] for k in ('base_version','implementation_revision')}|{'files':binding['source_manifest']},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    check('source/143aggregate',len(binding['source_manifest'])==143 and aggregate==binding['source_sha256']==SOURCE)
    wheel_paths=list((AREA/'build_R0').glob('*.whl'));check('source/one_wheel',len(wheel_paths)==1)
    wheel=raw(wheel_paths[0]);check('source/wheel_sha',sha(wheel)==binding['wheel_sha256'])
    with zipfile.ZipFile(io.BytesIO(wheel)) as zf:
        record=next(p for p in zf.namelist() if p.endswith('.dist-info/RECORD'))
        for name,digest,length in csv.reader(io.StringIO(zf.read(record).decode())):
            if name==record:continue
            data=zf.read(name);check('source/RECORD/'+name,len(data)==int(length) and digest=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode())
        for row in binding['source_manifest']:
            data=raw(Path(binding['install_root'])/row['path'])
            check('source/Git_wheel_install/'+row['path'],sha(data)==row['sha256'] and data==zf.read(row['path'])==fixed[PRODUCT+':'+row['path']])
    for pin in freeze['direct_inputs']+baseline['direct_pins']:check('pin/'+pin['path'],pin_matches(pin,raw(pin['path'])))
    check('source/asset_unchanged',sha(raw(baseline['asset']['path']))==baseline['asset']['sha256']=='614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d')
    export_body=raw(AREA/'harness/export_source.py').decode('utf8')
    runner=ast.parse(raw(AREA/'harness/run_slot.py'))
    counter_function=next(node for node in runner.body if isinstance(node,ast.FunctionDef) and node.name=='host_residency_work')
    counter_expression=next(node.value for node in counter_function.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='code' for t in node.targets))
    install_root=Path(binding['install_root']).resolve()
    counter_code=bounded_string(counter_expression,dict(slot='_human_eye_mcp_resident_'+sha(str(install_root).encode())[:20],expected_host_sha=next(p['sha256'] for p in binding['source_manifest'] if p['path']=='human_eye_plugin/blender_host.py')))
    totals=dict(owned=0,public=0,constructed=0,native_blocks=0,exports=0,fixture_visibility=0,product_setters=0,model=0,paid=0)
    sessions=[];frames_unique=set();host_payloads=0;actual_capture_commands=0;unknown_closes=[];counter_records=[]
    for label in ('main','state'):
        folder=RUNTIME/'sessions'/label
        slot=read(folder/'SLOT_RESULT.json');pub=read(folder/'SLOT_PUBLICATION.json');start=read(folder/'RUNTIME_START.json');close=read(folder/'RUNTIME_CLOSE.json')
        began=slot['clocks']['slot_started_ns'];deadline=began+600_000_000_000
        check(label+'/completion',slot['status']==pub['status']=='completed' and not slot['errors'] and not close['errors'])
        check(label+'/original600',freeze['frozen_ns']<began and deadline==slot['clocks']['owned_deadline_ns']==start['owned_deadline_ns']==close['runtime']['owned_deadline_ns'] and pub['slot_result_published_ns']<=deadline)
        check(label+'/publication',sha(raw(folder/'SLOT_RESULT.json'))==pub['result_sha256'] and pub['complete_slot_ns']==pub['slot_result_published_ns']-began)
        fixture=slot['fixture_control'];totals['owned']+=1;totals['fixture_visibility']+=fixture['fixture_hide_set_setters']
        check(label+'/fixture_boundaries',fixture['restored'] and fixture['source_file_saved'] is False and fixture['product_setters']==0 and fixture['fixture_hide_set_setters']==fixture['fixture_operation_attempts']==fixture['fixture_hide_set_setters_confirmed_lower_bound']==fixture['fixture_hide_set_setters_upper_bound']==(0 if label=='main' else 4))
        check(label+'/no_consumers_or_paid',slot['model_consumers']==slot['paid_API_calls']==0)
        status=close['Blender_status'];closed=status['closed'];bc=close['Blender_close'];mc=close['MCP_stdio_close'];cfg=status['config']
        check(label+'/original_files_and_geometry',status['source_file_unchanged'] is True and status['protected_files_unchanged'] is True and closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint'] and not closed['poisoned'])
        check(label+'/asset_copy',sha(raw(cfg['asset_copy']))==baseline['asset']['sha256'])
        check(label+'/native_reap_close',bc['response']['status']=='closed' and bc['exit_code']==0 and bc['process_reaped'] and bc['original_deadline_ns']==deadline and slot['cleanup']['native_Popen_handle_closed'])
        check(label+'/MCP_reader_pipes',mc['confirmed'] and mc['exit_code']==0 and mc['reader_stopped'] and all(mc['pipes_closed'].values()) and mc['process_handle_closed'] and not mc['forced_kill'])
        for name,r in (('native',slot['cleanup']['native_retained_exit']),('MCP',close['MCP_retained_exit'])):check(label+'/'+name+'/held_exit',r['confirmed'] and r['exited'] and r['exit_code']==0 and r['handle_closed'])
        for name,d in (('NATIVE','native'),('MCP','mcp')):
            proof=read(folder/(name+'_RUNTIME_PROOF.json'));spawn=read(folder/d/'SPAWN.json')
            check(label+'/'+name+'/PID_deadline',proof['confirmed'] and proof['before_stdin'] and proof['runtime_pid']==spawn['pid'] and spawn['original_deadline_ns']==deadline)
        init=read(folder/'INITIALIZE.json')['result']['_meta']['human_eye'];rt=read(folder/'mcp_io/RUNTIME.json')
        check(label+'/actual_generation',init['source_sha256']==rt['source_sha256']==SOURCE and init['distribution_version']==binding['distribution_version'] and rt['algorithm_monkeypatches']==0 and rt['entry_sha256']==sha(raw(rt['entry'])))
        calls=lines(folder/'PUBLIC_REQUESTS.jsonl');index=lines(folder/'product_full/INDEX.jsonl');events=lines(folder/'native/WORKER_EVENTS.jsonl')
        check(label+'/request_count',len(calls)==len(slot['requests'])==len(index)==(2 if label=='main' else 6))
        codes={};decoded={};commands=[]
        for p in sorted((folder/'native/WIRE').glob('*/REQUEST.bin')):
            request=read(p);sequence=int(p.parent.name);commands.append(request['type'])
            if request['type']=='close':
                response=read(p.with_name('RESPONSE.bin'));event=next(e for e in events if e['sequence']==sequence)
                unknown_closes.append(dict(label=label,sequence=sequence,status=event['status'],wire_response=response))
                check(label+'/worker_unknown_and_closed_response',event['status']=='unknown' and response['status']=='closed' and response['pid']==cfg['pid'] and response['deadline_ns']==deadline)
            if request['type']!='execute_code':continue
            code=request['params']['code'];codes[sha(code.encode())]=code;decoded.update(embedded_sources(code));event=next(e for e in events if e['sequence']==sequence)
            check(label+'/actual_code/'+str(sequence),event['script_sha256']==sha(code.encode()) and not event.get('script_error'))
            if not code.endswith(export_body) and code!=counter_code:
                values=[json.loads(n.value.args[0].value) for n in ast.walk(ast.parse(code)) if isinstance(n,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id=='_request' for t in n.targets) and isinstance(n.value,ast.Call) and n.value.args and isinstance(n.value.args[0],ast.Constant)]
                check(label+'/read_only_capture_command/'+str(sequence),len(values)==1 and values[0]['command']=='capture');actual_capture_commands+=1
        expected_commands=[] if label=='main' else ['qa_display_cube_visible','qa_display_cube_restored','qa_display_target_hidden','qa_display_target_restored']
        check(label+'/four_display_fixtures',[c for c in commands if c.startswith('qa_')]==expected_commands)
        for name in ('blender_host.py','scene_residency.py'):
            path='human_eye_plugin/'+name;pin=next(p for p in binding['source_manifest'] if p['path']==path)
            check(label+'/embedded_current/'+name,pin['sha256'] in decoded and decoded[pin['sha256']]==raw(install_root/path));host_payloads+=1
        native_calls=lines(folder/'NATIVE_CALLS.jsonl')
        check(label+'/fresh_export_and_counter_call_count',len(native_calls)==len(slot['source_exports'])+1==(2 if label=='main' else 6))
        for stage,native in zip(slot['source_exports'],native_calls[:-1],strict=True):
            receipt=read(folder/('SOURCE_'+stage+'_RECEIPT.json'));answer=read(receipt['oracle_path']);source=folder/('SOURCE_'+stage+'.json')
            code='OUTPUT_PATH='+repr(str(source))+'\nSTATE='+repr(stage)+'\nOWNED_ROOT='+repr(str(folder))+'\n'+export_body
            check(label+'/fixed_export_code/'+stage,native['code_sha256']==sha(code.encode()) and codes.get(native['code_sha256'])==code and native['trusted_fixture_operation'] is True)
            check(label+'/export_oracle_hash/'+stage,pin_matches(receipt['receipt'],raw(source)) and sha(raw(receipt['oracle_path']))==receipt['oracle_sha256'] and answer['status']=='passed' and receipt['receipt']['process_id']==cfg['pid'])
            request=next(r for r in slot['requests'] if r['label']==stage)
            check(label+'/oracle_before_request/'+stage,receipt['started_ns']<=native['started_ns']<native['closed_ns']<=receipt['finished_ns']<request['started_ns']);totals['exports']+=1
        counter=read(folder/'HOST_RESIDENCY_WORK.json');native=native_calls[-1]
        check(label+'/counter_fixed_code',codes.get(native['code_sha256'])==counter_code and native['code_sha256']==sha(counter_code.encode()))
        check(label+'/counter_original_window',counter==slot['host_residency_work'] and counter['native_call_index']==native['index'] and counter['started_ns']<=native['started_ns']<native['closed_ns']<=counter['returned_ns']<=pub['slot_result_published_ns'])
        value=counter['value'];stats=value['counters']
        check(label+'/counter_source_and_PID',value['process_id']==cfg['pid'] and Path(value['module_file']).resolve()==install_root/'human_eye_plugin/blender_host.py' and value['loaded_host_source_sha256']==sha(raw(value['module_file'])))
        check(label+'/display_counts',stats['display_snapshots']==len(calls) and stats['display_objects']==2*len(calls) and stats['display_read_ns']>0 and counter['new_capture_calls']==counter['new_processes']==counter['new_rasters']==0)
        counter_records.append(dict(label=label,total_RPC_ms=(counter['returned_ns']-counter['started_ns'])/1e6,native_RPC_ms=(native['closed_ns']-native['started_ns'])/1e6,display_snapshots=stats['display_snapshots'],display_object_rows=stats['display_objects'],cumulative_display_read_ns=stats['display_read_ns'],counter_read_ns=value['read_complete_ns']-value['read_started_ns']))
        request_rows=[]
        for call,delivery,entry in zip(calls,slot['requests'],index,strict=True):
            n=call['internal_public_call_index'];prefix=label+'/'+str(n);totals['public']+=1
            for k in ('request','response','actual_TX','actual_RX'):check(prefix+'/original_'+k,sha(raw(call[k+'_path']))==call[k+'_sha256'])
            tx=json.loads(raw(call['actual_TX_path']));rx=json.loads(raw(call['actual_RX_path']))
            check(prefix+'/raw_delivery_object',tx==call['request'] and rx==call['response']==read(call['response_path']) and read(folder/'product_calls'/('call_'+str(n).zfill(3))/'DELIVERY.json')==delivery)
            check(prefix+'/original30',delivery['deadline_ns']==min(deadline,delivery['started_ns']+30_000_000_000) and delivery['started_ns']<=call['started_ns']<call['closed_ns']<=delivery['returned_ns']<delivery['deadline_ns'])
            check(prefix+'/same_successful_producer',rx['result']['isError'] is False and entry==call['producer_archive'] and n==entry['index']==call['producer_archive_index'] and call['started_ns']<=entry['started_ns']<=entry['producer_returned_ns']<=call['closed_ns'])
            original=read(entry['path']);check(prefix+'/producer_hash',sha(raw(entry['path']))==entry['sha256'])
            blocks=rx['result']['content'];images=[b for b in blocks if b['type']=='image'];public=json.loads(next(b['text'] for b in blocks if b['type']=='text'))
            check(prefix+'/same_public_JSON',public==delivery['public_result'] and public['read_only'] is True and public['execution_authority'] is False)
            check(prefix+'/one_native_frame',len(images)==len(original['frames'])==len(delivery['images'])==1)
            for block,frame,image in zip(images,original['frames'],delivery['images'],strict=True):
                data=base64.b64decode(block['data'],validate=True)
                check(prefix+'/nativePNG',sha(data)==frame['image_sha256']==image['sha256'] and data==raw(frame['image_path'])==raw(image['path']))
                check(prefix+'/NPZ',sha(raw(frame['arrays_path']))==frame['arrays_sha256']);frames_unique.add(frame['image_path'])
            work=original['work'];count=work['raster_attempts'];totals['constructed']+=count;totals['native_blocks']+=len(images)
            request_rows.append(dict(public_index=n,stage=delivery['label'],complete_request_ms=(delivery['returned_ns']-delivery['started_ns'])/1e6,client_ms=(call['closed_ns']-call['started_ns'])/1e6,service_ms=(entry['producer_returned_ns']-entry['started_ns'])/1e6,constructed=count,native_blocks=len(images),status=public['status'],observation_status=public['observation_status'],selected_surface_pixels=original['facts']['visibility']['selected_surface_pixels'],work=work))
        attempts=[e for e in lines(folder/'product_audit.jsonl') if e.get('event')=='source_region_render_attempt']
        check(label+'/actual_raster_audit',len(attempts)==sum(r['constructed'] for r in request_rows))
        sessions.append(dict(label=label,started_ns=began,closed_ns=pub['slot_result_published_ns'],complete_owned_ms=pub['complete_slot_ns']/1e6,requests=request_rows))
    check('total/counts',totals==dict(owned=2,public=8,constructed=6,native_blocks=8,exports=6,fixture_visibility=4,product_setters=0,model=0,paid=0))
    check('total/unique_frames_and_serial',len(frames_unique)==6 and sessions[0]['closed_ns']<sessions[1]['started_ns'])
    claims={'Blender_start':0,'raster_attempt':0}
    for p in sorted((RUNTIME/'budget/claims').glob('*.json')):
        claim=read(p);done=read(RUNTIME/'budget/settlements'/p.name);claims[claim['kind']]+=1
        check('budget/claim/'+p.stem,done['claim_sha256']==sha(raw(p)) and done['token']==claim['token']==p.stem)
        if claim['kind']=='Blender_start':check('budget/spawn/'+p.stem,done['spawn_status']=='spawned' and done['pid']>0)
        else:
            e=done['evidence'];data=raw(e['audit_path']);part=data[e['tail_start_bytes']:e['tail_start_bytes']+e['tail_bytes']]
            check('budget/nonrefunded_raster/'+p.stem,done['actual_attempts']==1 and done['released_proven_unconstructed_reservation']==0 and sha(part)==e['tail_sha256'] and json.loads(part)['event']=='source_region_render_attempt')
    check('budget/settled_counts',claims=={'Blender_start':2,'raster_attempt':6})
    regressions=[]
    for tag in ('source','installed'):
        report=read(AREA/'tests'/('REGRESSIONS_'+tag+'.json'));log=raw(AREA/'tests'/('REGRESSIONS_'+tag+'.log'))
        check('regression/'+tag,report['status']=='passed' and report['tests']==240 and not report['failures'] and not report['errors'] and not report['skipped'] and report['owned_Blender']==report['outer_real_raster_guard_calls']==report['model_consumers']==0 and sha(log)==report['log_sha256'])
        expected=install_root/'human_eye_plugin/source_region.py' if tag=='installed' else REPO/'human_eye_plugin/source_region.py'
        check('regression/'+tag+'/source_import',Path(report['source_import']).resolve()==expected.resolve())
        regressions.append(dict(tag=tag,tests=report['tests'],elapsed_ms=report['elapsed_ns']/1e6,synthetic_encoding=report['synthetic_encoding']))
    worker=read(AREA/'tests/WORKER_BASELINE_OBSERVATION.json');worker_log=raw(AREA/'tests/WORKER_BASELINE_OBSERVATION.log').decode()
    check('worker/historical_failure_scope',worker['tests']==9 and len(worker['failures'])==1 and not worker['errors'] and 'canonical_worker_is_standalone_and_example_copy_matches' in worker['failures'][0]['test'] and 'FAILED (failures=1)' in worker_log)
    worker_data=[]
    for p in worker_paths:
        data=raw(REPO/p);check('worker/unchanged/'+p,data==fixed[baseline['baseline_git']+':'+p]);worker_data.append(data)
    check('worker/existing_example_discrepancy',worker_data[0]!=worker_data[1])
    cleanup=read(AREA/'CACHE_CLEANUP.json')
    for row in cleanup['deleted']:
        path=Path(row['path']).resolve();check('cleanup/narrow_generated',path.is_relative_to(AREA/'tests/__pycache__') and not path.exists() and sha(raw(row['authored_source']))==row['source_sha256'])
    check('cleanup/runtime_preserved',cleanup['runtime_files_deleted']==0)
    return dict(status='passed_checked_scope' if all(c['passed'] for c in CHECKS) else 'failed',checks=len(CHECKS),failed_checks=[c for c in CHECKS if not c['passed']],author=FINAL,
        namespace_Git_paths=len(paths),total_Git_changed_paths=len(changed),runtime_files=len(archive['files']),runtime_bytes=total,source_files=len(binding['source_manifest']),source_sha256=SOURCE,actual_host_payloads_checked=host_payloads,actual_product_capture_commands=actual_capture_commands,
        counts=totals,sessions=sessions,counter_records=counter_records,regressions=regressions,worker_unknown_close_events=unknown_closes,
        new_live_Blender=0,new_MCP=0,new_raster=0,new_image_encoding=0,new_model=0,new_paid=0,input_pins=list(PINS.values()))


if __name__=='__main__':
    HERE.mkdir(parents=True,exist_ok=True)
    try:result=main()
    except Exception:
        (HERE/'ERROR.txt').write_text(traceback.format_exc(),encoding='utf8');raise
    (HERE/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('sessions','input_pins','worker_unknown_close_events','regressions')},ensure_ascii=False))
    sys.exit(0 if result['status']=='passed_checked_scope' else 1)
