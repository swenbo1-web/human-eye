"""Independent saved-file source, accounting and lifecycle checks."""
from pathlib import Path
import ast
import base64
import csv
import hashlib
import io
import json
import statistics
import subprocess
import sys
import traceback
import zipfile
import zlib

HERE=Path(__file__).resolve().parent
REPO=Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
AREA=REPO/'verification/m4_m5_source_region_001'
RUNTIME=Path('D:/he_m4_m5_source_region_001')
FINAL='de884a2a44557fb3d01407c5e7c2883cc4aa749c'
SOURCE_GIT={'R0':'7f71b352b949ce8c6a9982cddb9cb46366eac427',
    'R0F':'f14f155386d0f163aba445c3de92292553631cab',
    'R1':'2292c3d79e9996fb29b0c3351102998923113d56'}
FREEZE_GIT={'R0':'e31f07b5aea2c08f36db3b2f0bdd69ea82f4c697',
    'R0F':'350ef758ace96d7ba92c62561e8b24a48f68be44',
    'R1':'f6487657fe5e716886e1f36d176c4a1df431bcff'}
EXPECTED={'R0':'cc628abc7137b13792f1079c1aff5a6d3dcfa5fe5efbeafdd55d26ee4527d49b',
    'R0F':'e394544f70b94b3f94165985e8215d70db2ae8963b0e7546a167831c65c3376a',
    'R1':'8d8d3d60e99b5e039e6711c168f95d648124e96eea03b0a061b2796c5a690600'}
ORDER=['qualification_R0','pair1_R0','pair1_R1','pair2_R1','pair2_R0','pair3_R0','pair3_R1','state']
CHECKS=[]
PINS={}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(name,value):
    CHECKS.append(dict(name=name,passed=bool(value)))


def raw(path):
    path=Path(path).resolve()
    data=path.read_bytes()
    pin=dict(path=str(path),bytes=len(data),sha256=sha(data))
    if str(path) in PINS and PINS[str(path)]!=pin:
        raise ValueError('changed_input/'+str(path))
    PINS[str(path)]=pin
    return data


def read(path):
    return json.loads(raw(path))


def lines(path):
    return [json.loads(line) for line in raw(path).splitlines() if line.strip()]


def git(*args):
    return subprocess.check_output(['git','-C',str(REPO),*args])


def blob_batch(specs):
    specs=list(dict.fromkeys(specs))
    out=subprocess.run(['git','-C',str(REPO),'cat-file','--batch'],
        input=('\n'.join(specs)+'\n').encode(),stdout=subprocess.PIPE,check=True).stdout
    found={};pos=0
    for spec in specs:
        end=out.index(b'\n',pos)
        header=out[pos:end].split()
        if len(header)!=3 or header[1]!=b'blob':raise ValueError('nonblob/'+spec)
        size=int(header[2]);pos=end+1
        found[spec]=out[pos:pos+size];pos+=size+1
    check('git/batch_complete',pos==len(out))
    return found


def pin_matches(pin,data):
    return sha(data)==pin['sha256'] and ('bytes' not in pin or len(data)==pin['bytes'])


def source_payloads(code):
    result={}
    for node in ast.walk(ast.parse(code)):
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and len(node.value)>500:
            try:data=zlib.decompress(base64.b64decode(node.value,validate=True))
            except (ValueError,zlib.error):continue
            result[sha(data)]=data
    return result


def main():
    manifest=read(AREA/'CONTENT_MANIFEST.json');archive=read(AREA/'RUNTIME_ARCHIVE.json')
    baseline=read(AREA/'BASELINE.json');decision=read(AREA/'DECISION.json')
    namespace=AREA.relative_to(REPO).as_posix()
    member_paths={namespace+'/'+r['relative'] for r in manifest['files']}|{namespace+'/CONTENT_MANIFEST.json'}
    changed=set(git('diff','--name-only',baseline['baseline_git'],FINAL).decode().splitlines())
    check('git/1550_namespace',len(member_paths)==1550 and member_paths=={p for p in changed if p.startswith(namespace+'/')})
    expected_product={str(Path('human_eye_plugin')/name).replace('\\','/') for name in
        ('active_observation_images.py','live_service.py','live_spatial_mcp.py','query_policy.py','read_context.py','source_region.py','surface_proximity.py')}
    check('git/seven_product_changes',changed-member_paths==expected_product)
    bindings={v:read(AREA/(v+'_RUN_BINDING.json')) for v in SOURCE_GIT}
    freezes={v:read(AREA/('SOURCE_FREEZE_'+v+'.json')) for v in SOURCE_GIT}
    specs=[FINAL+':'+p for p in sorted(member_paths)]
    for tag,binding in bindings.items():
        specs += [SOURCE_GIT[tag]+':'+r['path'] for r in binding['source_manifest']]
        for p in freezes[tag]['harness_pins']+freezes[tag]['oracle_pins']+[freezes[tag]['task'],freezes[tag]['oracle']]:
            specs.append(FREEZE_GIT[tag]+':'+Path(p['path']).relative_to(REPO).as_posix())
    cleanup_records=[read(AREA/'TEST_CACHE_CLEANUP.json'),read(AREA/'FINAL_CACHE_CLEANUP.json')]
    for record in cleanup_records:
        for p in record['files']:
            commit=p.get('prior_git',record.get('prior_tracked_generation_git'))
            rel=p.get('prior_git_path',Path(p['path']).relative_to(REPO).as_posix())
            specs.append(commit+':'+rel)
    fixed=blob_batch(specs)
    for row in manifest['files']:
        data=raw(AREA/row['relative'])
        check('git/member/'+row['relative'],pin_matches(row,data) and data==fixed[FINAL+':'+namespace+'/'+row['relative']])
    check('git/manifest_self',raw(AREA/'CONTENT_MANIFEST.json')==fixed[FINAL+':'+namespace+'/CONTENT_MANIFEST.json'])
    check('runtime/declared_counts',archive['file_count']==1375 and archive['bytes']==29929015)
    original_paths={p.relative_to(RUNTIME).as_posix() for p in RUNTIME.rglob('*') if p.is_file()}
    check('runtime/zero_exclusion_set',original_paths=={p['relative'] for p in archive['files']})
    total=0
    for row in archive['files']:
        original=raw(RUNTIME/row['relative']);copy=raw(AREA/row['copy'])
        check('runtime/copy/'+row['relative'],original==copy and pin_matches(row,original))
        total+=len(original)
    check('runtime/byte_total',total==29929015)
    for pin in baseline['old_direct_seals']+[baseline['accepted_install']]:
        check('history/direct/'+pin['path'],pin_matches(pin,raw(pin['path'])))
    for ref in baseline['references']:
        check('reference/'+ref['copy']['path'],pin_matches(ref['copy'],raw(ref['copy']['path'])) and
              pin_matches(ref['original'],raw(ref['original']['path'])) and ref['copy']['sha256']==ref['original']['sha256'])
    stage_changes=[]
    for tag,binding in bindings.items():
        freeze=freezes[tag]
        digest=sha(json.dumps({k:binding[k] for k in ('base_version','implementation_revision')}|
            {'files':binding['source_manifest']},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
        check(tag+'/143_aggregate',len(binding['source_manifest'])==143 and digest==EXPECTED[tag]==binding['source_sha256'])
        check(tag+'/frozen_product',binding['source_manifest']==freeze['runtime_manifest'] and binding['preparation_git']==freeze['preparation_git']==SOURCE_GIT[tag])
        for p in freeze['harness_pins']+freeze['oracle_pins']+[freeze['task'],freeze['oracle']]:
            rel=Path(p['path']).relative_to(REPO).as_posix()
            check(tag+'/frozen_pin/'+rel,pin_matches(p,fixed[FREEZE_GIT[tag]+':'+rel]))
            if not pin_matches(p,raw(p['path'])):
                stage_changes.append(dict(version=tag,path=p['path'],frozen_sha256=p['sha256'],current_sha256=sha(raw(p['path']))))
        check(tag+'/asset_pin',pin_matches(freeze['asset'],raw(freeze['asset']['path'])))
        build=read(AREA/('build_'+tag)/'BUILD_INSTALL.json')
        wheel=raw(build['wheel'])
        check(tag+'/wheel',sha(wheel)==binding['wheel_sha256']==build['wheel_sha256'] and build['pip_exit']==0)
        with zipfile.ZipFile(io.BytesIO(wheel)) as zf:
            record=next(p for p in zf.namelist() if p.endswith('.dist-info/RECORD'))
            for p,digest,length in csv.reader(io.StringIO(zf.read(record).decode())):
                if p==record:continue
                data=zf.read(p)
                check(tag+'/wheel_RECORD/'+p,len(data)==int(length) and digest=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode())
            for row in binding['source_manifest']:
                data=raw(Path(binding['install_root'])/row['path'])
                check(tag+'/runtime/'+row['path'],sha(data)==row['sha256'] and data==zf.read(row['path'])==fixed[SOURCE_GIT[tag]+':'+row['path']])
    prep=read(RUNTIME/'fixture_preparation/RESULT.json')
    check('preparation/one_closed_process',prep['Blender_process_attempts']==1 and prep['status']=='completed' and prep['exit_code']==0 and prep['process_reaped'] and prep['Popen_handle_closed'] and prep['stdout_closed'] and prep['stderr_closed'] and not prep['errors'])
    check('preparation/held_exit',prep['retained_exit']['confirmed'] and prep['retained_exit']['exit_code']==0 and prep['retained_exit']['handle_closed'])
    counts=dict(owned=0,public_requests=0,stale_errors=0,constructed_frames=0,native_blocks=0,model=0,paid=0)
    sessions=[];unique_frames=set();actual_source_count=0
    for label in ORDER:
        folder=RUNTIME/'sessions'/label
        slot=read(folder/'SLOT_RESULT.json');pub=read(folder/'SLOT_PUBLICATION.json');start=read(folder/'RUNTIME_START.json');close=read(folder/'RUNTIME_CLOSE.json')
        tag=slot['version'];binding=bindings[tag]
        check(label+'/completed',slot['status']==pub['status']=='completed' and not slot['errors'] and not close['errors'])
        began=slot['clocks']['slot_started_ns'];deadline=began+600_000_000_000
        check(label+'/original600',slot['clocks']['owned_deadline_ns']==start['owned_deadline_ns']==close['runtime']['owned_deadline_ns']==deadline and pub['slot_result_published_ns']<deadline)
        check(label+'/published_original',pub['result_sha256']==sha(raw(folder/'SLOT_RESULT.json')) and pub['complete_slot_ns']==pub['slot_result_published_ns']-began)
        status=close['Blender_status'];closed=status['closed'];cfg=status['config']
        check(label+'/intact',status['source_file_unchanged'] is True and status['protected_files_unchanged'] is True and closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint'] and not closed['poisoned'])
        check(label+'/asset_copy',sha(raw(cfg['asset_copy']))==cfg['asset_sha256']==prep['asset_sha256'])
        bc=close['Blender_close'];mc=close['MCP_stdio_close']
        check(label+'/native_reap',bc['exit_code']==0 and bc['process_reaped'] and bc['original_deadline_ns']==deadline and slot['cleanup']['native_Popen_handle_closed'])
        check(label+'/mcp_closed',mc['confirmed'] and mc['exit_code']==0 and mc['reader_stopped'] and all(mc['pipes_closed'].values()) and mc['process_handle_closed'] and not mc['forced_kill'])
        for p in (slot['cleanup']['native_retained_exit'],close['MCP_retained_exit']):
            check(label+'/held_exit/'+p['method'],p['confirmed'] and p['exit_code']==0 and p['handle_closed'] and p['exited'])
        for name,directory in (('NATIVE','native'),('MCP','mcp')):
            spawn=read(folder/directory/'SPAWN.json');proof=read(folder/(name+'_RUNTIME_PROOF.json'))
            check(label+'/'+name+'/identity',proof['confirmed'] and proof['before_stdin'] and proof['runtime_pid']==spawn['pid'] and spawn['original_deadline_ns']==deadline)
        init=read(folder/'INITIALIZE.json')['result']['_meta']['human_eye'];rt=read(folder/'mcp_io/RUNTIME.json')
        check(label+'/installed_generation',init['source_sha256']==rt['source_sha256']==binding['source_sha256'] and init['distribution_version']==binding['distribution_version'] and rt['algorithm_monkeypatches']==0)
        check(label+'/entry_bytes',sha(raw(rt['entry']))==rt['entry_sha256'])
        decoded={}
        for request in sorted((folder/'native/WIRE').glob('*/REQUEST.bin')):
            message=read(request)
            if message.get('type')!='execute_code':continue
            code=message['params']['code'];sequence=int(request.parent.name)
            events=lines(folder/'native/WORKER_EVENTS.jsonl')
            event=next(e for e in events if e['sequence']==sequence)
            check(label+'/worker_script/'+str(sequence),sha(code.encode())==event['script_sha256'] and not event['script_error'])
            decoded.update(source_payloads(code))
        for name in ('blender_host.py','scene_residency.py'):
            path='human_eye_plugin/'+name;pin=next(p for p in binding['source_manifest'] if p['path']==path)
            check(label+'/actual_host/'+name,pin['sha256'] in decoded and decoded[pin['sha256']]==raw(Path(binding['install_root'])/path))
            actual_source_count+=1
        calls=lines(folder/'PUBLIC_REQUESTS.jsonl');entries=lines(folder/'product_full/INDEX.jsonl')
        check(label+'/request_count',len(calls)==len(slot['requests'])==(11 if label=='state' else 2))
        check(label+'/success_archive_count',len(entries)==len(calls)-(2 if label=='state' else 0))
        check(label+'/no_model_paid',slot['model_consumers']==slot['paid_API_calls']==0)
        rows=[];indices=[];counts['owned']+=1;counts['public_requests']+=len(calls)
        for call,expect in zip(calls,slot['requests'],strict=True):
            n=call['internal_public_call_index'];prefix=label+'/'+str(n)
            for k in ('request','response','actual_TX','actual_RX'):
                check(prefix+'/raw_'+k,sha(raw(call[k+'_path']))==call[k+'_sha256'])
            tx=json.loads(raw(call['actual_TX_path']));rx=json.loads(raw(call['actual_RX_path']))
            check(prefix+'/wire_same',tx==call['request'] and rx==call['response']==read(call['response_path']))
            check(prefix+'/original30',0<=call['closed_ns']-call['started_ns']<30_000_000_000 and began<=call['started_ns']<call['closed_ns']<=deadline)
            error='error' in rx or rx.get('result',{}).get('isError') is True
            check(prefix+'/expected_outcome',error==expect['expected_error'])
            blocks=rx.get('result',{}).get('content',[]);images=[b for b in blocks if b['type']=='image']
            if error:
                fact=json.loads(next(b['text'] for b in blocks if b['type']=='text'))
                check(prefix+'/stale_specific',fact['error']=='source_region_ref_capture_generation_changed' and fact['automatic_retry'] is False and not images and call['producer_archive_index'] is None)
                counts['stale_errors']+=1
                rows.append(dict(index=n,label=expect['label'],error=True,service_ms=None,client_ms=(call['closed_ns']-call['started_ns'])/1e6,constructed=0,native=0))
                continue
            entry=call['producer_archive'];indices.append(entry['index'])
            original=read(entry['path'])
            check(prefix+'/producer_current',entry['index']==call['producer_archive_index'] and entry in entries and sha(raw(entry['path']))==entry['sha256'])
            check(prefix+'/nested_clocks',call['started_ns']<=entry['started_ns']<=entry['producer_returned_ns']<=call['closed_ns'])
            frames=original.get('frames',[]);work=original.get('work',{});public=json.loads(next(b['text'] for b in blocks if b['type']=='text'))
            check(prefix+'/native_frames',len(images)==len(frames))
            if original['result_kind']=='task_query':
                check(prefix+'/legacy_whole_object',tx['params']['arguments']['query']['mode']=='task' and tx['params']['arguments']['include_image'] is False and not frames)
            else:
                check(prefix+'/read_only',public['read_only'] is True and public['execution_authority'] is False and original['read_only'] is True and original['execution_authority'] is False)
            for image,frame in zip(images,frames,strict=True):
                check(prefix+'/nativePNG/'+frame['frame_identity'],sha(base64.b64decode(image['data'],validate=True))==frame['image_sha256'])
                check(prefix+'/PNG/'+frame['frame_identity'],sha(raw(frame['image_path']))==frame['image_sha256'])
                check(prefix+'/NPZ/'+frame['frame_identity'],sha(raw(frame['arrays_path']))==frame['arrays_sha256'])
                unique_frames.add(frame['image_path'])
            count=work.get('raster_attempts',0)
            counts['constructed_frames']+=count;counts['native_blocks']+=len(images)
            rows.append(dict(index=n,label=expect['label'],error=False,
                service_ms=(entry['producer_returned_ns']-entry['started_ns'])/1e6,
                product_service_stage_ms=original.get('stages',{}).get('service_total',{}).get('elapsed_ns',0)/1e6,
                client_ms=(call['closed_ns']-call['started_ns'])/1e6,constructed=count,native=len(images),
                work=work))
        check(label+'/ordered_success_indices',indices==[r['index'] for r in entries] and indices==sorted(set(indices)))
        events=lines(folder/'product_audit.jsonl')
        attempts=[e for e in events if e.get('event') in ('active_observation_render_attempt','source_region_render_attempt')]
        check(label+'/raster_audit',len(attempts)==sum(r['constructed'] for r in rows))
        sessions.append(dict(label=label,version=tag,started_ns=began,closed_ns=pub['slot_result_published_ns'],
            owned_ms=pub['complete_slot_ns']/1e6,requests=rows,
            business_service_ms=sum(r['service_ms'] or 0 for r in rows),business_client_ms=sum(r['client_ms'] for r in rows)))
    check('all/accounted',counts==dict(owned=8,public_requests=25,stale_errors=2,constructed_frames=17,native_blocks=26,model=0,paid=0))
    check('all/unique_frames',len(unique_frames)==17)
    check('all/serial',all(a['closed_ns']<b['started_ns'] for a,b in zip(sessions,sessions[1:])))
    claim_counts={'Blender_start':0,'raster_attempt':0}
    for path in sorted((RUNTIME/'budget/claims').glob('*.json')):
        claim=read(path);done=read(RUNTIME/'budget/settlements'/path.name)
        check('claim/'+path.stem,sha(raw(path))==done['claim_sha256'] and claim['token']==done['token']==path.stem)
        claim_counts[claim['kind']]+=1
        if claim['kind']=='Blender_start':
            check('spawn/'+path.stem,done['spawn_status']=='spawned' and done['pid']>0)
        else:
            e=done['evidence'];audit=raw(e['audit_path']);part=audit[e['tail_start_bytes']:e['tail_start_bytes']+e['tail_bytes']]
            check('raster/'+path.stem,done['actual_attempts']==1 and done['released_proven_unconstructed_reservation']==0 and sha(part)==e['tail_sha256'] and json.loads(part)['event'] in ('active_observation_render_attempt','source_region_render_attempt'))
    check('budget/settled',claim_counts=={'Blender_start':8,'raster_attempt':17})
    hotspot=read(AREA/'FIRST_CORRECTED_HOTSPOT.json')
    check('chronology/R0_R0F_R1',freezes['R0']['frozen_ns']<sessions[0]['started_ns']<sessions[0]['closed_ns']<freezes['R0F']['frozen_ns']<sessions[1]['started_ns']<sessions[1]['closed_ns']<freezes['R1']['frozen_ns']<sessions[2]['started_ns'])
    check('hotspot/committed_before_R1',git('show',SOURCE_GIT['R1']+':'+namespace+'/FIRST_CORRECTED_HOTSPOT.json')==raw(AREA/'FIRST_CORRECTED_HOTSPOT.json'))
    for pin in hotspot['originals']+[hotspot['quality']]:check('hotspot/pin/'+pin['path'],pin_matches(pin,raw(pin['path'])))
    corrected=read(hotspot['originals'][0]['path']);second=read(hotspot['originals'][1]['path'])
    check('hotspot/corrected_baseline',corrected['stages']['frame_validation_and_selected_pixels']['elapsed_ns']==hotspot['first_validation_ns']==10708600 and hotspot['selected_pixels']==26212 and second['work']['prepare_cache_hit'] and second['work']['frame_reuses']==1)
    look={s['label']:s for s in sessions};pairs=[]
    for number in (1,2,3):
        a,b=look['pair'+str(number)+'_R0'],look['pair'+str(number)+'_R1']
        check('pair/'+str(number)+'/matching_quality_generations',a['version']=='R0F' and b['version']=='R1' and len(a['requests'])==len(b['requests'])==2)
        pairs.append(dict(pair=number,initial_service_ms=a['business_service_ms'],candidate_service_ms=b['business_service_ms'],
            initial_client_ms=a['business_client_ms'],candidate_client_ms=b['business_client_ms'],
            initial_owned_ms=a['owned_ms'],candidate_owned_ms=b['owned_ms'],
            owned_change_ms=b['owned_ms']-a['owned_ms'],service_reduction=1-b['business_service_ms']/a['business_service_ms']))
    gain=statistics.median(p['service_reduction'] for p in pairs)
    owned_gain=1-statistics.median(p['candidate_owned_ms'] for p in pairs)/statistics.median(p['initial_owned_ms'] for p in pairs)
    check('cost/original_arithmetic',abs(gain-decision['median_two_request_service_reduction'])<1e-14 and abs(owned_gain-decision['median_owned_reduction'])<1e-14)
    check('cost/pregistered_timing_gate',sum(p['candidate_service_ms']<p['initial_service_ms'] for p in pairs)>=2 and gain>0)
    check('cost/second_owned_slower_preserved',pairs[1]['owned_change_ms']>0 and abs(pairs[1]['owned_change_ms']-5.0478)<1e-9)
    bytecode=[]
    for record in cleanup_records:
        for p in record['files']:
            path=Path(p['path']).resolve();commit=p.get('prior_git',record.get('prior_tracked_generation_git'))
            rel=p.get('prior_git_path',path.relative_to(REPO).as_posix());data=fixed[commit+':'+rel]
            check('cache_cleanup/'+rel,path.is_relative_to(AREA) and path.parent.name=='__pycache__' and not path.exists() and pin_matches(p,data))
            bytecode.append(dict(path=str(path),prior_git=commit,bytes=len(data),sha256=sha(data)))
    return dict(status='passed_checked_scope' if all(c['passed'] for c in CHECKS) else 'failed',checks=len(CHECKS),failed_checks=[c for c in CHECKS if not c['passed']],
        author_commit=FINAL,git_namespace_paths=len(member_paths),runtime_files=len(archive['files']),runtime_bytes=total,
        source_generations=EXPECTED,actual_host_payloads_checked=actual_source_count,historical_pin_changes=stage_changes,
        preparation_ms=prep['complete_ns']/1e6,budgets=counts,total_Blender_processes=counts['owned']+1,
        sessions=sessions,pairs=pairs,service_paired_median_reduction=gain,owned_median_reduction=owned_gain,
        generated_bytecode_verified_from_prior_Git=bytecode,new_live_Blender=0,new_MCP=0,new_raster=0,new_model=0,new_paid=0,input_pins=list(PINS.values()))


if __name__=='__main__':
    HERE.mkdir(parents=True,exist_ok=True)
    try:result=main()
    except Exception:
        (HERE/'ERROR.txt').write_text(traceback.format_exc(),encoding='utf8')
        raise
    (HERE/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('sessions','pairs','input_pins','generated_bytecode_verified_from_prior_Git','historical_pin_changes','source_generations')},ensure_ascii=False))
    sys.exit(0 if result['status']=='passed_checked_scope' else 1)
