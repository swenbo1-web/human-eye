"""Read fixed Git and saved records only. No product import or live operations."""
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

HERE = Path(__file__).resolve().parent
REPO = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
AREA = REPO / 'verification/m4_cross_scale_discovery_001'
RUNTIME = Path('D:/he_m4_cross_scale_001')
FINAL = '3c26b43d197e6de252f65db69c061733e5a7216e'
PREEXEC = 'a63d2b14617a446d87b91b7c069f9a1b801821fa'
COMMITS = {'R0': '481feb6d414ecb1ed1eb0bb3c9c8d9da8b403d69',
           'R1': 'a707364dfd4882288999c75f91366a9f46770056'}
EXPECTED = {'R0': '9c9ff65a162b1a4e5c0e953c83de5bc87767b2c15fdd5bf72a20949029212dc6',
            'R1': 'a2ca481aedee398c49c566feddaa12b904795f828a6e334f07d78b0d28d2f8bc'}
ORDER = ['qualification_R0','pair1_R0','pair1_R1','pair2_R1',
         'pair2_R0','pair3_R0','pair3_R1','state']
CHECKS = []
READS = {}


def check(label, actual):
    CHECKS.append({'name': label, 'passed': bool(actual)})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    value = {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}
    if str(path) in READS:
        if value != READS[str(path)]:
            raise ValueError('input_changed/' + str(path))
    else:
        READS[str(path)] = value
    return data


def read(path):
    return json.loads(raw(path))


def lines(path):
    return [json.loads(row) for row in raw(path).splitlines() if row.strip()]


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args])


def blobs(specifications):
    specs = list(dict.fromkeys(specifications))
    result = subprocess.run(['git','-C',str(REPO),'cat-file','--batch'],
        input=('\n'.join(specs)+'\n').encode(), stdout=subprocess.PIPE, check=True).stdout
    pos, found = 0, {}
    for spec in specs:
        stop = result.index(b'\n',pos)
        header = result[pos:stop].split()
        if len(header) != 3 or header[1] != b'blob':
            raise ValueError('missing_or_nonblob/' + spec)
        size = int(header[2])
        pos = stop + 1
        found[spec] = result[pos:pos+size]
        pos += size + 1
    check('git/batch_consumed', pos == len(result))
    return found


def check_pin(label, pin):
    data = raw(pin['path'])
    check(label, sha(data) == pin['sha256'] and ('bytes' not in pin or len(data) == pin['bytes']))


def source_payloads(code):
    output = []
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 500:
            try:
                value = zlib.decompress(base64.b64decode(node.value,validate=True))
            except (ValueError,zlib.error):
                continue
            output.append(value)
    return output


def main():
    manifest = read(AREA/'CONTENT_MANIFEST.json')
    archive = read(AREA/'RUNTIME_ARCHIVE.json')
    baseline = read(AREA/'BASELINE.json')
    decision = read(AREA/'DECISION.json')
    relative_root = AREA.relative_to(REPO).as_posix()
    paths = {relative_root+'/'+row['relative'] for row in manifest['files']}
    paths.add(relative_root+'/CONTENT_MANIFEST.json')
    changed = set(git('diff','--name-only',baseline['baseline_git'],FINAL).decode().splitlines())
    check('git/namespace_manifest_closure', paths == changed and len(paths) == 1360)
    specifications = [FINAL+':'+p for p in sorted(paths)]
    bindings = {v:read(AREA/(v+'_RUN_BINDING.json')) for v in COMMITS}
    freezes = {v:read(AREA/('SOURCE_FREEZE_'+v+'.json')) for v in COMMITS}
    for version,binding in bindings.items():
        specifications += [COMMITS[version]+':'+row['path'] for row in binding['source_manifest']]
        for pin in freezes[version]['harness_pins']+freezes[version]['oracle_pins']+[freezes[version]['task']]:
            specifications.append(PREEXEC+':'+Path(pin['path']).relative_to(REPO).as_posix())
    fixed = blobs(specifications)
    for row in manifest['files']:
        data = raw(AREA/row['relative'])
        check('git/member/'+row['relative'], len(data)==row['bytes'] and sha(data)==row['sha256']
              and data==fixed[FINAL+':'+relative_root+'/'+row['relative']])
    check('git/manifest_blob', raw(AREA/'CONTENT_MANIFEST.json') == fixed[FINAL+':'+relative_root+'/CONTENT_MANIFEST.json'])
    check('runtime/archive_declared',archive['file_count']==1206 and archive['bytes']==30304010 and archive['byte_exact'] is True)
    runtime_files = {p.relative_to(RUNTIME).as_posix() for p in RUNTIME.rglob('*') if p.is_file()}
    check('runtime/archive_enumeration', runtime_files == {row['relative'] for row in archive['files']})
    size=0
    for row in archive['files']:
        original,copy=raw(RUNTIME/row['relative']),raw(AREA/row['copy'])
        size += len(original)
        check('runtime/copy/'+row['relative'],original==copy and len(original)==row['bytes'] and sha(original)==row['sha256'])
    check('runtime/bytes',size==30304010)
    for index,pin in enumerate(baseline['old_direct_seals']):
        check_pin('history/direct_seal/'+str(index),pin)
    for index,row in enumerate(baseline['references']):
        check_pin('reference/copy/'+str(index),row['copy'])
        check_pin('reference/original/'+str(index),row['original'])
        check('reference/equal/'+str(index),row['copy']['sha256']==row['original']['sha256'])
    check_pin('asset/original',baseline['qualification_asset'])
    check_pin('asset/geometry',baseline['qualification_geometry'])
    for version,binding in bindings.items():
        identity={k:binding[k] for k in ('base_version','implementation_revision')}
        aggregate=sha(json.dumps(dict(identity,files=binding['source_manifest']),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
        check(version+'/142_source_aggregate',len(binding['source_manifest'])==142 and aggregate==EXPECTED[version]==binding['source_sha256'])
        freeze=freezes[version]
        check(version+'/freeze_sources',freeze['runtime_manifest']==binding['source_manifest'] and freeze['preparation_git']==COMMITS[version])
        for pin in freeze['harness_pins']+freeze['oracle_pins']+[freeze['task'],freeze['asset'],freeze['oracle']]:
            check_pin(version+'/freeze_pin/'+pin['path'],pin)
            p=Path(pin['path'])
            if p.is_relative_to(REPO):
                check(version+'/preexecution/'+p.name,sha(fixed[PREEXEC+':'+p.relative_to(REPO).as_posix()])==pin['sha256'])
        build=read(AREA/('build_'+version)/'BUILD_INSTALL.json')
        wheel=raw(build['wheel'])
        check(version+'/wheel_SHA',sha(wheel)==binding['wheel_sha256']==build['wheel_sha256'] and build['pip_exit']==0)
        with zipfile.ZipFile(io.BytesIO(wheel)) as zf:
            record=next(n for n in zf.namelist() if n.endswith('.dist-info/RECORD'))
            for name,digest,length in csv.reader(io.StringIO(zf.read(record).decode())):
                if name==record:
                    continue
                data=zf.read(name)
                check(version+'/wheel_RECORD/'+name,len(data)==int(length) and digest=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode())
            for row in binding['source_manifest']:
                data=raw(Path(binding['install_root'])/row['path'])
                check(version+'/source/'+row['path'],data==zf.read(row['path'])==fixed[COMMITS[version]+':'+row['path']] and sha(data)==row['sha256'])
    all_frames=set();counts={'owned':0,'public':0,'constructed':0,'native_blocks':0,'model':0,'paid':0}
    sessions=[];wire_payload_count=0
    for label in ORDER:
        folder=RUNTIME/'sessions'/label
        slot=read(folder/'SLOT_RESULT.json');publication=read(folder/'SLOT_PUBLICATION.json')
        start=read(folder/'RUNTIME_START.json');close=read(folder/'RUNTIME_CLOSE.json')
        version=slot['version'];binding=bindings[version]
        check(label+'/completed',slot['status']=='completed' and not slot['errors'] and publication['status']=='completed' and not close['errors'])
        check(label+'/publication',publication['result_sha256']==sha(raw(folder/'SLOT_RESULT.json')) and publication['complete_slot_ns']==publication['slot_result_published_ns']-publication['slot_started_ns'])
        began=slot['clocks']['slot_started_ns'];deadline=began+600_000_000_000
        check(label+'/absolute600',deadline==slot['clocks']['owned_deadline_ns']==start['owned_deadline_ns']==close['runtime']['owned_deadline_ns'] and publication['slot_result_published_ns']<=deadline)
        check(label+'/original_asset',close['Blender_status']['source_file_unchanged'] is True and close['Blender_status']['protected_files_unchanged'] is True)
        closed=close['Blender_status']['closed']
        check(label+'/geometry_restored',closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint'] and not closed['poisoned'])
        for kind in ('native','MCP'):
            receipt=read(folder/('native/SPAWN.json' if kind=='native' else 'mcp/SPAWN.json'))
            proof=read(folder/('NATIVE_RUNTIME_PROOF.json' if kind=='native' else 'MCP_RUNTIME_PROOF.json'))
            check(label+'/'+kind+'/proof',proof['confirmed'] and proof['before_stdin'] and proof['runtime_pid']==receipt['pid'] and proof['status']=='confirmed')
            check(label+'/'+kind+'/deadline',receipt['original_deadline_ns']==deadline)
        bc=close['Blender_close'];mc=close['MCP_stdio_close']
        check(label+'/Blender_wait_reap',bc['exit_code']==0 and bc['process_reaped'] is True and bc['error'] is None and bc['original_deadline_ns']==deadline)
        check(label+'/MCP_wait_pipes',mc['exit_code']==0 and mc['confirmed'] and mc['reader_stopped'] and all(mc['pipes_closed'].values()) and mc['process_handle_closed'] and not mc['forced_kill'])
        for obj in (slot['cleanup']['native_retained_exit'],close['MCP_retained_exit']):
            check(label+'/held_exit/'+obj['method'],obj['confirmed'] and obj['exit_code']==0 and obj['handle_closed'] and obj['exited'])
        cfg=read(folder/'native/CONFIG.json')
        check(label+'/asset_copy',sha(raw(cfg['asset_copy']))==cfg['asset_sha256']==baseline['qualification_asset']['sha256'])
        init=read(folder/'INITIALIZE.json')['result']['_meta']['human_eye']
        check(label+'/initialize',init['source_sha256']==binding['source_sha256'] and init['distribution_version']==binding['distribution_version'])
        runtime=read(folder/'mcp_io/RUNTIME.json')
        check(label+'/loaded_generation',runtime['source_sha256']==binding['source_sha256'] and runtime['algorithm_monkeypatches']==0 and runtime['entry_sha256']==sha(raw(runtime['entry'])))
        payloads=[]
        for req in sorted((folder/'native/WIRE').glob('*/REQUEST.bin')):
            obj=read(req)
            if obj.get('type')!='execute_code':continue
            code=obj['params']['code']
            payloads += source_payloads(code)
            seq=int(req.parent.name)
            event=next(e for e in lines(folder/'native/WORKER_EVENTS.jsonl') if e['sequence']==seq)
            check(label+'/actual_code_hash/'+str(seq),event['script_sha256']==sha(code.encode()) and not event['script_error'])
        manifest_sources={row['path']:row['sha256'] for row in binding['source_manifest']}
        decoded={sha(b):b for b in payloads}
        for p in ('human_eye_plugin/blender_host.py','human_eye_plugin/scene_residency.py'):
            check(label+'/actual_embedded/'+p,manifest_sources[p] in decoded and decoded[manifest_sources[p]]==raw(Path(binding['install_root'])/p))
            wire_payload_count+=1
        calls=lines(folder/'PUBLIC_REQUESTS.jsonl');entries=lines(folder/'product_full/INDEX.jsonl')
        check(label+'/request_count',len(calls)==len(entries)==len(slot['requests'])==(7 if label=='state' else 1))
        check(label+'/one_same_source',slot['model_consumers']==slot['paid_API_calls']==0)
        counts['owned']+=1;counts['public']+=len(calls)
        rows=[]
        for call,entry in zip(calls,entries,strict=True):
            n=call['internal_public_call_index'];prefix=label+'/'+str(n)
            check(prefix+'/same_producer_sequence',n==entry['index']==call['producer_archive_index'] and entry==call['producer_archive'])
            check(prefix+'/nested_clocks',began<=call['started_ns']<=entry['started_ns']<=entry['producer_returned_ns']<=call['closed_ns']<=deadline)
            check(prefix+'/original30',0<=call['closed_ns']-call['started_ns']<30_000_000_000 and call['complete_client_call_ns']==call['closed_ns']-call['started_ns'])
            for k in ('request','response','actual_TX','actual_RX'):
                check(prefix+'/raw/'+k,sha(raw(call[k+'_path']))==call[k+'_sha256'])
            tx=json.loads(raw(call['actual_TX_path']));rx=json.loads(raw(call['actual_RX_path']))
            check(prefix+'/wire_public_exact',tx==call['request'] and rx==call['response'])
            original=read(entry['path']);response=read(call['response_path'])
            check(prefix+'/producer_sha',sha(raw(entry['path']))==entry['sha256'] and response==rx)
            images=[b for b in rx['result']['content'] if b['type']=='image']
            check(prefix+'/native_count',len(images)==len(original['frames']))
            for block,frame in zip(images,original['frames'],strict=True):
                check(prefix+'/native_image/'+frame['frame_identity'],sha(base64.b64decode(block['data'],validate=True))==frame['image_sha256'])
            frames=original.get('constructed_frames',original['frames'])
            for frame in frames:
                for k in ('image','arrays'):
                    check(prefix+'/frame_'+k+'/'+frame['frame_identity'],sha(raw(frame[k+'_path']))==frame[k+'_sha256'])
                all_frames.add(frame['image_path'])
            row={'request':n,'service_ms':(entry['producer_returned_ns']-entry['started_ns'])/1e6,
                'product_service_stage_ms':original['stages']['service_total']['elapsed_ns']/1e6,
                'client_ms':call['complete_client_call_ns']/1e6,'constructed_attempts':original['work']['raster_attempts'],
                'selected_blocks':len(images),'generation_frames':len(frames),'cache_hit':original['work']['result_cache_hit'],
                'PNG_generation_bytes':sum(f['PNG_bytes'] for f in frames),
                'NPZ_generation_bytes':sum(f['compressed_array_file_bytes'] for f in frames)}
            counts['native_blocks']+=len(images);counts['constructed']+=row['constructed_attempts'];rows.append(row)
        audit=lines(folder/'product_audit.jsonl')
        check(label+'/actual_producer_rasters',len([e for e in audit if e.get('event')=='active_observation_render_attempt'])==sum(r['constructed_attempts'] for r in rows))
        sessions.append({'label':label,'version':version,'started_ns':began,'closed_ns':publication['slot_result_published_ns'],
                         'complete_owned_ms':publication['complete_slot_ns']/1e6,'requests':rows})
    check('all/owned_public_constructed_native',counts=={'owned':8,'public':14,'constructed':58,'native_blocks':44,'model':0,'paid':0})
    check('all/unique_constructed_frames',len(all_frames)==58)
    check('all/serial_sessions',all(a['closed_ns']<b['started_ns'] for a,b in zip(sessions,sessions[1:])))
    claim_counts={'Blender_start':0,'raster_attempt':0};settled_raster=0
    for path in sorted((RUNTIME/'budget/claims').glob('*.json')):
        claim=read(path);settle=read(RUNTIME/'budget/settlements'/path.name)
        check('budget/claim_identity/'+path.stem,settle['claim_sha256']==sha(raw(path)) and claim['token']==settle['token']==path.stem)
        claim_counts[claim['kind']]+=1
        if claim['kind']=='Blender_start':
            check('budget/start/'+path.stem,settle['spawn_status']=='spawned' and settle['pid']>0)
        else:
            evidence=settle['evidence'];data=raw(evidence['audit_path'])
            part=data[evidence['tail_start_bytes']:evidence['tail_start_bytes']+evidence['tail_bytes']]
            check('budget/nonrefundable_raster/'+path.stem,settle['actual_attempts']==1 and settle['released_proven_unconstructed_reservation']==0 and sha(part)==evidence['tail_sha256'])
            check('budget/producer_event/'+path.stem,json.loads(part)['event']=='active_observation_render_attempt')
            settled_raster+=settle['actual_attempts']
    check('budget/final',claim_counts=={'Blender_start':8,'raster_attempt':58} and settled_raster==58<=64)
    hotspot=read(AREA/'FIRST_VERSION_HOTSPOT.json');first=read(hotspot['original_service_result'])
    global_stages=first['stages']
    render=sum(value['elapsed_ns'] for name,value in global_stages.items() if name.startswith('render_and_publish_global_'))
    feedback=sum(value['elapsed_ns'] for name,value in global_stages.items() if name.startswith('feedback_global_'))
    check('hotspot/original_window',sha(raw(hotspot['original_service_result']))==hotspot['original_sha256'] and render==hotspot['global_render_publish_ns'] and feedback==hotspot['global_feedback_ns'])
    check('freeze/chronology',freezes['R0']['frozen_ns']<sessions[0]['started_ns']<sessions[0]['closed_ns']<freezes['R1']['frozen_ns']<sessions[1]['started_ns'])
    hotspot_path=relative_root+'/FIRST_VERSION_HOTSPOT.json'
    frozen_hotspot=git('show',COMMITS['R1']+':'+hotspot_path)
    check('hotspot/committed_before_optimized_build',frozen_hotspot==raw(AREA/'FIRST_VERSION_HOTSPOT.json'))
    lookup={s['label']:s for s in sessions};pairs=[]
    for number in range(1,4):
        a,b=lookup['pair'+str(number)+'_R0'],lookup['pair'+str(number)+'_R1']
        ac,bc=a['requests'][0],b['requests'][0]
        row={'pair':number,'R0_service_ms':ac['service_ms'],'R1_service_ms':bc['service_ms'],
             'R0_client_ms':ac['client_ms'],'R1_client_ms':bc['client_ms'],
             'R0_owned_ms':a['complete_owned_ms'],'R1_owned_ms':b['complete_owned_ms'],
             'service_reduction':1-bc['service_ms']/ac['service_ms']}
        pairs.append(row)
        check('pair/'+str(number)+'/same_output_sizes',ac['selected_blocks']==bc['selected_blocks']==3 and ac['constructed_attempts']==8 and bc['constructed_attempts']==3)
    service_gain=statistics.median(p['service_reduction'] for p in pairs)
    a_med=statistics.median(p['R0_owned_ms'] for p in pairs);b_med=statistics.median(p['R1_owned_ms'] for p in pairs)
    owned_gain=1-b_med/a_med
    check('performance/recomputed',service_gain==decision['service_paired_median_reduction'] and owned_gain==decision['owned_median_reduction'])
    check('performance/pregistered_gate',service_gain>=.2 and sum(p['R1_owned_ms']<p['R0_owned_ms'] for p in pairs)>=2 and b_med<a_med)
    old_failures=raw(AREA/'transport_tests/R0_LEGACY_RAW_CHECKS.stdout.txt').decode()
    baseline_failures=raw(AREA/'transport_tests/BASELINE_LEGACY_CHECKS.stdout.txt').decode()
    failure_names=lambda text:[s for s in text.splitlines() if s.startswith('FAIL:')]
    check('historical/failure_names',len(failure_names(old_failures))==len(failure_names(baseline_failures))==7 and failure_names(old_failures)==failure_names(baseline_failures))
    check('historical/installed_baseline_traceback','D:\\he_m5_observe_measure_001\\B\\product' in baseline_failures or 'D:/he_m5_observe_measure_001/B/product' in baseline_failures)
    cleanup=read(AREA/'CACHE_CLEANUP.json')
    cache=Path(cleanup['path']).resolve()
    check('cleanup/narrow_generated_cache',cache.is_relative_to(AREA/'harness/reused/__pycache__') and cache.name=='wire_meter.cpython-313.pyc' and not cache.exists() and cleanup['actual_operations_added']==0)
    check('cleanup/pinned_source_present',sha(raw(AREA/'harness/reused/wire_meter.py'))==next(p['sha256'] for p in freezes['R1']['harness_pins'] if p['path'].endswith('wire_meter.py')))
    return dict(status='passed_checked_scope' if all(c['passed'] for c in CHECKS) else 'failed',checks=len(CHECKS),
        failed_checks=[c for c in CHECKS if not c['passed']],checked_author=FINAL,preexecution=PREEXEC,
        manifest_paths=len(paths),runtime_files=len(archive['files']),runtime_bytes=size,actual_host_source_payloads_checked=wire_payload_count,
        budgets=counts,unique_frames=len(all_frames),sessions=sessions,pairs=pairs,
        service_median_paired_reduction=service_gain,owned_median_R0_ms=a_med,owned_median_R1_ms=b_med,owned_median_reduction=owned_gain,
        global_hotspot_render_publish_ns=render,global_hotspot_feedback_ns=feedback,
        task_registration_to_decision_seconds=(decision['closed_ns']-baseline['started_ns'])/1e9,
        limits=['Quality/source-owner correctness is covered by the other independent reviewers.',
                'Model benefit, task-wide root/delegated model usage, provider cash cost, active-only wall time and system load are unmeasured.',
                'Deleted generated cache bytes are unavailable now; pre-deletion SHA/size are receipt-only evidence.',
                'Baseline source_pins describe workspace files, while baseline execution is established separately by imported stack paths and matching failures.'],
        new_live_Blender=0,new_MCP=0,new_raster=0,new_model=0,new_paid_API=0,
        input_pins=list(READS.values()))


if __name__=='__main__':
    HERE.mkdir(parents=True,exist_ok=True)
    try:
        result=main()
    except Exception:
        (HERE/'ERROR.txt').write_text(traceback.format_exc(),encoding='utf8')
        raise
    (HERE/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('sessions','input_pins','pairs','limits')},ensure_ascii=False))
    sys.exit(0 if result['status']=='passed_checked_scope' else 1)
