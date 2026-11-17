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
AREA=REPO/'verification/m4_real_asset_region_qualification_001'
RUNTIME=Path('D:/he_m4_real_asset_region_001')
FINAL='828d1265a3434fd1b5fb97e4759acaedd9253bc0'
PRODUCT='2292c3d79e9996fb29b0c3351102998923113d56'
SOURCE='8d8d3d60e99b5e039e6711c168f95d648124e96eea03b0a061b2796c5a690600'
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


def main():
    manifest=read(AREA/'CONTENT_MANIFEST.json');archive=read(AREA/'RUNTIME_ARCHIVE.json')
    baseline=read(AREA/'BASELINE.json');binding=read(AREA/'R1_RUN_BINDING.json');freeze=read(AREA/'SOURCE_FREEZE.json')
    ns=AREA.relative_to(REPO).as_posix()
    paths={ns+'/'+r['path'] for r in manifest['files']}|{ns+'/CONTENT_MANIFEST.json'}
    changed=set(git('diff','--name-only',baseline['baseline_git'],FINAL).decode().splitlines())
    check('git/exact_321_namespace_only',len(paths)==321 and paths==changed)
    check('git/no_product_delta',not git('diff',PRODUCT,FINAL,'--','human_eye_plugin'))
    fixed=blobs([FINAL+':'+p for p in sorted(paths)]+[PRODUCT+':'+p['path'] for p in binding['source_manifest']])
    for row in manifest['files']:
        data=raw(AREA/row['path'])
        check('git/member/'+row['path'],pin_matches(row,data) and data==fixed[FINAL+':'+ns+'/'+row['path']])
    check('git/self_manifest',raw(AREA/'CONTENT_MANIFEST.json')==fixed[FINAL+':'+ns+'/CONTENT_MANIFEST.json'])
    actual_files={p.relative_to(RUNTIME).as_posix() for p in RUNTIME.rglob('*') if p.is_file()}
    check('runtime/complete_file_set',len(actual_files)==274 and actual_files=={r['relative'] for r in archive['files']} and archive['runtime_exclusions']==[])
    total=0
    for row in archive['files']:
        data=raw(RUNTIME/row['relative']);copy=raw(AREA/row['copy']);total+=len(data)
        check('runtime/copy/'+row['relative'],data==copy and pin_matches(row,data))
    check('runtime/byte_total',total==archive['bytes']==100678626)
    check('source/frozen_product',freeze['product_changes']==0 and freeze['product_git']==binding['preparation_git']==baseline['product_git']==PRODUCT and freeze['runtime_manifest']==binding['source_manifest'])
    identity={k:binding[k] for k in ('base_version','implementation_revision')}
    aggregate=sha(json.dumps(identity|{'files':binding['source_manifest']},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    check('source/143_aggregate',len(binding['source_manifest'])==143 and aggregate==SOURCE==binding['source_sha256']==freeze['source_sha256'])
    wheel_paths=list((AREA.with_name('m4_m5_source_region_001')/'build_R1').glob('*.whl'))
    check('source/one_wheel',len(wheel_paths)==1)
    wheel=raw(wheel_paths[0]);check('source/wheel_SHA',sha(wheel)==binding['wheel_sha256'])
    with zipfile.ZipFile(io.BytesIO(wheel)) as zf:
        record=next(p for p in zf.namelist() if p.endswith('.dist-info/RECORD'))
        for name,digest,length in csv.reader(io.StringIO(zf.read(record).decode())):
            if name==record:continue
            data=zf.read(name)
            check('source/wheel_RECORD/'+name,len(data)==int(length) and digest=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode())
        for row in binding['source_manifest']:
            data=raw(Path(binding['install_root'])/row['path'])
            check('source/Git_wheel_install/'+row['path'],sha(data)==row['sha256'] and data==zf.read(row['path'])==fixed[PRODUCT+':'+row['path']])
    for pin in freeze['direct_inputs']:
        check('freeze/input/'+pin['path'],pin_matches(pin,raw(pin['path'])))
    for pin in baseline['direct_pins']:
        check('baseline/input/'+pin['path'],pin_matches(pin,raw(pin['path'])))
    asset=Path(baseline['asset']['path'])
    check('asset/original_SHA',sha(raw(asset))==baseline['asset']['sha256']=='614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d')
    export_body=raw(AREA/'harness/export_source.py').decode('utf8')
    totals=dict(owned=0,public=0,success=0,stale=0,constructed=0,native_blocks=0,exports=0,fixture_matrix=0,product_setters=0,model=0,paid=0)
    rows=[];unique_frames=set();unknown_close_events=[];host_payloads=0;capture_commands=0
    for label in ('main','state'):
        folder=RUNTIME/'sessions'/label
        slot=read(folder/'SLOT_RESULT.json');pub=read(folder/'SLOT_PUBLICATION.json');start=read(folder/'RUNTIME_START.json');close=read(folder/'RUNTIME_CLOSE.json')
        began=slot['clocks']['slot_started_ns'];deadline=began+600_000_000_000
        check(label+'/completed',slot['status']==pub['status']=='completed' and not slot['errors'] and not close['errors'])
        check(label+'/original600',freeze['frozen_ns']<began and deadline==slot['clocks']['owned_deadline_ns']==start['owned_deadline_ns']==close['runtime']['owned_deadline_ns'] and pub['slot_result_published_ns']<=deadline)
        check(label+'/publication',sha(raw(folder/'SLOT_RESULT.json'))==pub['result_sha256'] and pub['complete_slot_ns']==pub['slot_result_published_ns']-began)
        check(label+'/nonmutating_public',slot['fixture_control']['source_file_saved'] is False and slot['fixture_control']['product_setters']==0 and slot['model_consumers']==slot['paid_API_calls']==0)
        totals['fixture_matrix']+=slot['fixture_control']['fixture_matrix_setters'];totals['owned']+=1
        status=close['Blender_status'];closed=status['closed'];bc=close['Blender_close'];mc=close['MCP_stdio_close']
        check(label+'/geometry_and_original_file',status['source_file_unchanged'] is True and status['protected_files_unchanged'] is True and closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint'] and not closed['poisoned'])
        check(label+'/input_copy',sha(raw(status['config']['asset_copy']))==baseline['asset']['sha256'])
        check(label+'/native_close_response',bc['response']['status']=='closed' and bc['process_reaped'] and bc['exit_code']==0 and bc['original_deadline_ns']==deadline and slot['cleanup']['native_Popen_handle_closed'])
        check(label+'/MCP_reader_pipe_handle_close',mc['confirmed'] and mc['exit_code']==0 and mc['reader_stopped'] and all(mc['pipes_closed'].values()) and mc['process_handle_closed'] and not mc['forced_kill'])
        for name,receipt in (('native',slot['cleanup']['native_retained_exit']),('MCP',close['MCP_retained_exit'])):
            check(label+'/'+name+'/held_exit',receipt['confirmed'] and receipt['exited'] and receipt['exit_code']==0 and receipt['handle_closed'])
        for name,directory in (('NATIVE','native'),('MCP','mcp')):
            proof=read(folder/(name+'_RUNTIME_PROOF.json'));spawn=read(folder/directory/'SPAWN.json')
            check(label+'/'+name+'/runtime_PID',proof['confirmed'] and proof['runtime_pid']==spawn['pid'] and proof['before_stdin'] and spawn['original_deadline_ns']==deadline)
        init=read(folder/'INITIALIZE.json')['result']['_meta']['human_eye'];rt=read(folder/'mcp_io/RUNTIME.json')
        check(label+'/loaded_generation',init['source_sha256']==rt['source_sha256']==SOURCE and init['distribution_version']==binding['distribution_version'] and rt['algorithm_monkeypatches']==0)
        check(label+'/entry_bytes',rt['entry_sha256']==sha(raw(rt['entry'])))
        calls=lines(folder/'PUBLIC_REQUESTS.jsonl');index=lines(folder/'product_full/INDEX.jsonl');events=lines(folder/'native/WORKER_EVENTS.jsonl')
        check(label+'/public_denominator',len(calls)==len(slot['requests'])==(2 if label=='main' else 5) and len(index)==(2 if label=='main' else 3))
        actual_codes={};decoded={};commands=[]
        for p in sorted((folder/'native/WIRE').glob('*/REQUEST.bin')):
            request=read(p);sequence=int(p.parent.name);commands.append(request['type'])
            if request['type']=='close':
                response=read(p.with_name('RESPONSE.bin'))
                close_event=next(e for e in events if e['sequence']==sequence)
                unknown_close_events.append(dict(label=label,sequence=sequence,event_status=close_event['status'],wire_response=response))
                check(label+'/unknown_worker_close_retained',close_event['status']=='unknown' and response['status']=='closed' and response['pid']==status['config']['pid'] and response['deadline_ns']==deadline)
            if request['type']!='execute_code':continue
            code=request['params']['code'];actual_codes[sha(code.encode())]=code;decoded.update(embedded_sources(code))
            event=next(e for e in events if e['sequence']==sequence)
            check(label+'/executed_code/'+str(sequence),event['script_sha256']==sha(code.encode()) and not event.get('script_error'))
            if not code.endswith(export_body):
                request_values=[json.loads(node.value.args[0].value) for node in ast.walk(ast.parse(code))
                    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_request' for t in node.targets)
                    and isinstance(node.value,ast.Call) and node.value.args and isinstance(node.value.args[0],ast.Constant)]
                check(label+'/product_read_capture/'+str(sequence),len(request_values)==1 and request_values[0]['command']=='capture')
                capture_commands+=1
        for name in ('blender_host.py','scene_residency.py'):
            path='human_eye_plugin/'+name;pin=next(p for p in binding['source_manifest'] if p['path']==path)
            check(label+'/embedded_current/'+name,pin['sha256'] in decoded and decoded[pin['sha256']]==raw(Path(binding['install_root'])/path));host_payloads+=1
        check(label+'/fixture_command_count',commands.count('qa_m5_matrix_move')==commands.count('qa_m5_matrix_restore')==(0 if label=='main' else 1))
        native_calls=lines(folder/'NATIVE_CALLS.jsonl')
        check(label+'/source_export_count',len(native_calls)==len(slot['source_exports'])==(1 if label=='main' else 3))
        for stage,native in zip(slot['source_exports'],native_calls,strict=True):
            receipt=read(folder/('SOURCE_'+stage+'_RECEIPT.json'));answer=read(receipt['oracle_path'])
            source_path=folder/('SOURCE_'+stage+'.json')
            code='OUTPUT_PATH='+repr(str(source_path))+'\nSTATE='+repr(stage)+'\nOWNED_ROOT='+repr(str(folder))+'\n'+export_body
            check(label+'/export_original_code/'+stage,native['code_sha256']==sha(code.encode()) and actual_codes.get(native['code_sha256'])==code and native['trusted_fixture_operation'] is True)
            check(label+'/export_oracle_hash/'+stage,pin_matches(receipt['receipt'],raw(source_path)) and sha(raw(receipt['oracle_path']))==receipt['oracle_sha256'] and answer['status']=='passed' and receipt['receipt']['process_id']==status['config']['pid'])
            check(label+'/export_before_query/'+stage,receipt['fixed_before_subsequent_product_query'] and receipt['started_ns']<=native['started_ns']<native['closed_ns']<=receipt['finished_ns']<next(r['started_ns'] for r in slot['requests'] if r['label']==('initial' if stage=='initial' else stage+'_old')))
            totals['exports']+=1
        request_rows=[];success_indices=[]
        for call,delivered in zip(calls,slot['requests'],strict=True):
            n=call['internal_public_call_index'];prefix=label+'/'+str(n);totals['public']+=1
            for k in ('request','response','actual_TX','actual_RX'):
                check(prefix+'/raw_'+k,sha(raw(call[k+'_path']))==call[k+'_sha256'])
            tx=json.loads(raw(call['actual_TX_path']));rx=json.loads(raw(call['actual_RX_path']))
            check(prefix+'/wire_exact',tx==call['request'] and rx==call['response']==read(call['response_path']))
            check(prefix+'/original30',delivered['deadline_ns']==min(deadline,delivered['started_ns']+30_000_000_000) and delivered['returned_ns']<delivered['deadline_ns'] and delivered['started_ns']<=call['started_ns']<call['closed_ns']<=delivered['returned_ns'])
            error='error' in rx or rx.get('result',{}).get('isError') is True
            check(prefix+'/outcome_matches',error==delivered['is_error'])
            blocks=rx.get('result',{}).get('content',[]);images=[b for b in blocks if b['type']=='image'];public=json.loads(next(b['text'] for b in blocks if b['type']=='text'))
            check(prefix+'/retained_delivery_original',read(folder/'product_calls'/('call_'+str(n).zfill(3))/'DELIVERY.json')==delivered)
            row=dict(public_index=n,stage=delivered['label'],error=error,complete_request_ms=(delivered['returned_ns']-delivered['started_ns'])/1e6,client_ms=(call['closed_ns']-call['started_ns'])/1e6,native_blocks=len(images))
            if error:
                check(prefix+'/specific_stale_no_retry',public['error']=='source_region_ref_capture_generation_changed' and public['automatic_retry'] is False and not images and call['producer_archive_index'] is None)
                row.update(constructed=0,service_ms=None);totals['stale']+=1
            else:
                entry=call['producer_archive'];original=read(entry['path']);success_indices.append(entry['index'])
                check(prefix+'/same_producer',entry in index and entry['index']==call['producer_archive_index'] and sha(raw(entry['path']))==entry['sha256'])
                check(prefix+'/nested_service',call['started_ns']<=entry['started_ns']<=entry['producer_returned_ns']<=call['closed_ns'])
                check(prefix+'/same_public_json',public==delivered['public_result'] and public['read_only'] is True and public['execution_authority'] is False)
                check(prefix+'/one_native_frame',len(images)==len(original['frames'])==len(delivered['images'])==1)
                for image,frame,saved in zip(images,original['frames'],delivered['images'],strict=True):
                    data=base64.b64decode(image['data'],validate=True)
                    check(prefix+'/nativePNG',sha(data)==frame['image_sha256']==saved['sha256'] and data==raw(frame['image_path'])==raw(saved['path']))
                    check(prefix+'/NPZ',sha(raw(frame['arrays_path']))==frame['arrays_sha256']);unique_frames.add(frame['image_path'])
                work=original['work'];count=work['raster_attempts']
                totals['constructed']+=count;totals['native_blocks']+=len(images);totals['success']+=1
                row.update(constructed=count,service_ms=(entry['producer_returned_ns']-entry['started_ns'])/1e6,work=work,
                    selected_surface_pixels=original['facts']['visibility']['selected_surface_pixels'],status=original['status'],observation_status=original['observation_status'])
            request_rows.append(row)
        check(label+'/success_index_order',success_indices==[r['index'] for r in index])
        audits=lines(folder/'product_audit.jsonl');attempts=[r for r in audits if r.get('event')=='source_region_render_attempt']
        check(label+'/producer_constructed_count',len(attempts)==sum(r['constructed'] for r in request_rows))
        rows.append(dict(label=label,started_ns=began,closed_ns=pub['slot_result_published_ns'],complete_owned_ms=pub['complete_slot_ns']/1e6,requests=request_rows))
    check('total/counts',totals==dict(owned=2,public=7,success=5,stale=2,constructed=4,native_blocks=5,exports=4,fixture_matrix=2,product_setters=0,model=0,paid=0))
    check('total/unique_constructed_frames',len(unique_frames)==4)
    check('total/serial',rows[0]['closed_ns']<rows[1]['started_ns'])
    claim_counts={'Blender_start':0,'raster_attempt':0}
    for p in sorted((RUNTIME/'budget/claims').glob('*.json')):
        claim=read(p);done=read(RUNTIME/'budget/settlements'/p.name);claim_counts[claim['kind']]+=1
        check('budget/claim/'+p.stem,done['claim_sha256']==sha(raw(p)) and claim['token']==done['token']==p.stem)
        if claim['kind']=='Blender_start':check('budget/spawn/'+p.stem,done['spawn_status']=='spawned' and done['pid']>0)
        else:
            e=done['evidence'];audit=raw(e['audit_path']);part=audit[e['tail_start_bytes']:e['tail_start_bytes']+e['tail_bytes']]
            check('budget/raster/'+p.stem,done['actual_attempts']==1 and done['released_proven_unconstructed_reservation']==0 and sha(part)==e['tail_sha256'] and json.loads(part)['event']=='source_region_render_attempt')
    check('budget/two_owned_four_rasters',claim_counts=={'Blender_start':2,'raster_attempt':4})
    cleanup=read(AREA/'CACHE_CLEANUP.json')
    for row in cleanup['deleted']:
        path=Path(row['path']).resolve()
        check('cleanup/narrow_generated',path.is_relative_to(AREA/'checks/__pycache__') and not path.exists() and sha(raw(row['authored_source']))==row['source_sha256'])
    check('cleanup/no_runtime_deletion',cleanup['runtime_files_deleted']==0)
    return dict(status='passed_checked_scope' if all(c['passed'] for c in CHECKS) else 'failed',checks=len(CHECKS),failed_checks=[c for c in CHECKS if not c['passed']],
        author=FINAL,git_paths=len(paths),runtime_files=len(archive['files']),runtime_bytes=total,source_files=len(binding['source_manifest']),source_sha256=SOURCE,
        actual_host_payloads_checked=host_payloads,actual_product_capture_commands=capture_commands,counts=totals,sessions=rows,worker_unknown_close_events=unknown_close_events,
        new_live_Blender=0,new_MCP=0,new_raster=0,new_model=0,new_paid=0,input_pins=list(PINS.values()))


if __name__=='__main__':
    HERE.mkdir(parents=True,exist_ok=True)
    try:result=main()
    except Exception:
        (HERE/'ERROR.txt').write_text(traceback.format_exc(),encoding='utf8')
        raise
    (HERE/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('sessions','input_pins','worker_unknown_close_events')},ensure_ascii=False))
    sys.exit(0 if result['status']=='passed_checked_scope' else 1)
