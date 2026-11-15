"""Saved-only audit of the two closed, zero-model recovery sessions."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import time
import zlib

HERE=Path(__file__).resolve().parent
RUNTIME=Path('D:/he_m5_harness_recovery_001')
CHECKS=[]
PINS={}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    path=Path(path).resolve()
    raw=path.read_bytes()
    entry=dict(path=str(path),sha256=sha(raw),bytes=len(raw))
    previous=PINS.setdefault(str(path),entry)
    check('input_stable/'+str(path),previous==entry)
    return entry


def read(path):
    pin(path)
    return json.loads(Path(path).read_bytes())


def rows(path):
    pin(path)
    return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()]


def check(name,value):
    CHECKS.append(dict(name=name,passed=bool(value)))


def source(group):
    binding=read(HERE/(group+'_RUN_BINDING.json'))
    manifest=binding['source_manifest']
    for row in manifest:
        check(group+'/installed141/'+row['path'],pin(Path(binding['install_root'])/row['path'])['sha256']==row['sha256'])
    identity={key:binding[key] for key in ('base_version','implementation_revision')}
    identity['files']=manifest
    actual=sha(json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    check(group+'/source_identity',len(manifest)==141 and actual==binding['source_sha256'])
    return binding


def host_wire(folder,binding):
    wire=read(folder/'native/WIRE/INDEX.json')
    manifest={row['path']:row['sha256'] for row in binding['source_manifest']}
    loaded=[]
    for row in wire:
        root=folder/'native/WIRE'/str(row['sequence']).zfill(3)
        tx,rx=root/'REQUEST.bin',root/'RESPONSE.bin'
        request,response=read(tx),read(rx)
        check(folder.name+'/native_original_wire/'+str(row['sequence']),
            tx.stat().st_size==row['request_bytes'] and rx.stat().st_size==row['response_attempted_bytes']
            and row['response_sendall_completed'] is True)
        if request['type']!='execute_code':
            continue
        code=request['params']['code']
        for node in ast.walk(ast.parse(code)):
            if not (isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
                    and node.func.id=='compile' and len(node.args)>=2):
                continue
            expression=node.args[0]
            if not (isinstance(expression,ast.Call) and isinstance(expression.func,ast.Attribute)
                    and expression.func.attr=='decompress'):
                continue
            raw=zlib.decompress(base64.b64decode(ast.literal_eval(expression.args[0].args[0]),validate=True))
            path=Path(ast.literal_eval(node.args[1]))
            relative=path.relative_to(Path(binding['install_root'])).as_posix()
            check(folder.name+'/actual_host_loaded_source/'+relative,sha(raw)==manifest[relative]==pin(path)['sha256'])
            loaded.append(dict(path=relative,sha256=sha(raw),wire_sequence=row['sequence']))
    return dict(wire=wire,actual_loaded_source=loaded)


def session(group):
    folder=(RUNTIME/'sessions'/group).resolve()
    binding=source(group)
    slot=read(folder/'SLOT_RESULT.json')
    publication=read(folder/'SLOT_PUBLICATION.json')
    close=read(folder/'RUNTIME_CLOSE.json')
    runtime=close['runtime']
    clocks=slot['clocks']
    check(group+'/completed_original_status',slot['status']==publication['status']=='completed'
        and slot['errors']==close['errors']==runtime['errors']==[])
    check(group+'/original600_window',clocks['worker_deadline_ns']==clocks['owned_deadline_ns']
        ==clocks['slot_started_ns']+600_000_000_000==runtime['owned_deadline_ns']==runtime['consumer_deadline_ns'])
    check(group+'/complete_clock_and_result_hash',publication['complete_slot_ns']
        ==publication['slot_result_published_ns']-clocks['slot_started_ns']
        and publication['result_sha256']==pin(folder/'SLOT_RESULT.json')['sha256']
        and publication['owned_budget_passed'] is True
        and publication['slot_result_published_ns']<clocks['owned_deadline_ns'])
    check(group+'/no_model_or_paid',slot['model_consumers']==slot['paid_API_calls']==0
        and slot['consumer_path'] is None and slot['consumer_record'] is None
        and not (folder/'CONSUMER_START.json').exists())
    config=read(folder/'PRODUCT_CONFIG.json')
    check(group+'/original30_public_budget',config['request_budget_s']==config['blender']['timeout_s']==30)
    initialized=read(folder/'INITIALIZE.json')['result']['_meta']['human_eye']
    mcp_runtime=read(folder/'mcp_io/RUNTIME.json')
    check(group+'/actual_installed_identity',initialized['source_sha256']==binding['source_sha256']
        ==runtime['product_source_sha256']==mcp_runtime['source_sha256']
        and initialized['source_kind']=='installed_distribution'
        and mcp_runtime['algorithm_monkeypatches']==0)
    cleanup=slot['cleanup']
    actor=read(folder/'ACTOR_CLOSE.json')
    check(group+'/actor_closed',cleanup['actor_exit_code']==0 and cleanup['actor_process_handle_closed'] is True
        and actor['errors']==[] and actor['bridge']['confirmed'] is True and actor['bridge']['errors']==[])
    held={}
    for kind in ('native','mcp'):
        spawn=read(folder/kind/'SPAWN.json')
        proof=read(folder/('ROOT_'+kind.upper()+'_PROOF.json'))
        held[kind]=cleanup[kind]
        check(group+'/actual_held_exit/'+kind,spawn['pid']==proof['runtime_pid']
            and spawn['parent_pid']==slot['owned']['actor_pid'] and proof['confirmed'] is True
            and held[kind]['confirmed'] is True and held[kind]['exited'] is True
            and held[kind]['exit_code']==0 and held[kind]['handle_closed'] is True
            and held[kind]['forced_by_root'] is False)
    stdio=read(folder/'mcp/CLOSE.json')
    check(group+'/MCP_reader_pipes_handle_closed',stdio['confirmed'] is True and stdio['exit_code']==0
        and stdio['reader_stopped'] is True and stdio['process_handle_closed'] is True
        and all(stdio['pipes_closed'].values()) and stdio['errors']==[])
    check(group+'/actor_MCP_retained_exit',close['MCP_retained_exit']['confirmed'] is True
        and close['MCP_retained_exit']['exit_code']==0 and close['MCP_retained_exit']['handle_closed'] is True)
    native=read(folder/'native/WORKER_CLOSED.json')
    native_config=read(folder/'native/CONFIG.json')
    check(group+'/Blender_Popen_reaped_and_restored',close['Blender_close']['exit_code']==0
        and close['Blender_close']['process_reaped'] is True and native['poisoned'] is False
        and native['initial_geometry_fingerprint']==native['final_geometry_fingerprint'])
    check(group+'/asset_and_owned_copy_unsaved',close['Blender_status']['source_file_unchanged'] is True
        and close['Blender_status']['protected_files_unchanged'] is True
        and pin(native_config['asset'])['sha256']==pin(native_config['asset_copy'])['sha256']==native_config['asset_sha256'])
    events=rows(folder/'native/WORKER_EVENTS.jsonl')
    wire=host_wire(folder,binding)
    public=runtime['public_requests']
    journal=rows(folder/'PUBLIC_REQUESTS.jsonl')
    check(group+'/original_public_journal',journal==public and len(public)==5)
    index_path=folder/'product_full/INDEX.jsonl'
    index=rows(index_path)
    final_index=index_path.read_bytes()
    owner=read(folder/'owner/BRIDGE_RESULT.json')['calls']
    metrics=read(folder/'owner/METRICS.json')
    check(group+'/four_outer_five_internal',len(owner)==metrics['tool_attempts']==4
        and [i for row in owner for i in row['internal_public_call_indices']]==[1,2,3,4,5])
    marker_results=[]
    owner_frames=[]
    for position,row in enumerate(owner,1):
        root=folder/'owner'/('tool_'+str(position).zfill(2))
        outer=read(root/'RESPONSE.json')
        read(root/'REQUEST.json')
        read(root/'RECEIPT.json')
        check(group+'/outer_original_success/'+str(position),outer['result']['isError'] is False)
        value=json.loads(next(block['text'] for block in outer['result']['content'] if block['type']=='text'))
        check(group+'/ordinary_Python_no_error/'+str(position),value['error'] is None)
        for line in value['stdout'].splitlines():
            if line.startswith('M5_RECOVERY_PUBLIC:'):
                marker_results.append(json.loads(line[len('M5_RECOVERY_PUBLIC:'):]))
        owner_frames.extend(sha(base64.b64decode(block['data'],validate=True)) for block in outer['result']['content'] if block['type']=='image')
    check(group+'/five_direct_public_snapshots',len(marker_results)==5)
    io=rows(folder/'mcp_io/MCP_IO.jsonl')
    public_records=[]
    previous=b''
    for number,request in enumerate(public,1):
        call=folder/'product_calls'/('call_'+str(number).zfill(3))
        before_path,after_path=call/'ARCHIVE_BEFORE.bin',call/'ARCHIVE_AFTER.bin'
        before,after=before_path.read_bytes(),after_path.read_bytes()
        pin(before_path)
        pin(after_path)
        check(group+'/original_INDEX_snapshot_sha/'+str(number),sha(before)==request['archive_before_sha256']
            and sha(after)==request['archive_after_sha256'])
        check(group+'/original_INDEX_prefix_and_continuity/'+str(number),before==previous
            and after.startswith(before) and final_index.startswith(after))
        previous=after
        old=[json.loads(line) for line in before.splitlines()]
        new=[json.loads(line) for line in after.splitlines()][len(old):]
        expected=None if number==2 else number if number==1 else number-1
        check(group+'/actual_independent_producer_index/'+str(number),request['producer_archive_index']==expected
            and len(new)==(0 if expected is None else 1) and 'post_reply_binding_error' not in request)
        producer=None
        if new:
            producer=new[0]
            path=Path(producer['path']).resolve()
            check(group+'/current_producer_exact_path_hash/'+str(number),producer['index']==expected
                and path==(folder/'product_full'/('call_'+str(expected).zfill(3))/'SERVICE_RESULT.json')
                and pin(path)['sha256']==producer['sha256'] and request['producer_archive']==producer)
            check(group+'/current_producer_actual_window/'+str(number),request['started_ns']
                <=producer['started_ns']<=producer['producer_returned_ns']<=request['closed_ns'])
            read(path.with_name('READ_CONTEXT.json'))
        response=read(request['actual_RX_path'])
        check(group+'/raw_MCP_and_standalone_reply/'+str(number),response==request['response']
            ==read(request['response_path']) and pin(request['actual_RX_path'])['sha256']==request['actual_RX_sha256']
            and pin(request['response_path'])['sha256']==request['response_sha256'])
        check(group+'/raw_original_arguments/'+str(number),read(request['actual_TX_path'])==request['request']
            ==read(request['request_path']) and pin(request['actual_TX_path'])['sha256']==request['actual_TX_sha256'])
        value=json.loads(next(block['text'] for block in response['result']['content'] if block['type']=='text'))
        check(group+'/delivered_JSON_and_original_isError/'+str(number),marker_results[number-1]['public_result']==value
            and marker_results[number-1]['isError']==response['result']['isError']==(number==2))
        if number==4:
            check(group+'/partial_retained',value['status']=='partial')
        receipt=request['receipt']
        server=[row for row in io if row['id']==request['id']]
        check(group+'/original_request_windows/'+str(number),len(server)==1
            and request['complete_client_call_ns']==request['closed_ns']-request['started_ns']
            and request['client_flush_to_received_ns']==receipt['received_complete_ns']-receipt['stdin_flushed_ns'])
        if server:
            check(group+'/public30_bound/'+str(number),server[0]['request_to_reply_ns']<=30_000_000_000)
            check(group+'/all_samples_inside600_slot/'+str(number),all(clocks['slot_started_ns']<=sample
                <=publication['slot_result_published_ns'] for sample in (request['started_ns'],request['closed_ns'],
                receipt['stdin_flushed_ns'],receipt['received_complete_ns'],server[0]['request_received_ns'],server[0]['reply_completed_ns'])))
        public_records.append(dict(id=request['id'],producer_index=expected,MCP_isError=response['result']['isError'],
            public_status=value.get('status'),original_producer=producer,server=server,
            complete_client_call_ns=request['complete_client_call_ns'],client_flush_to_received_ns=request['client_flush_to_received_ns'],
            client_pre_receipt_span_ns=request['client_internal_pre_receipt_ns'],raw_RX_bytes=receipt['RX_bytes'],raw_TX_bytes=receipt['TX_bytes'],
            INDEX_before_bytes=len(before),INDEX_after_bytes=len(after)))
    check(group+'/all_final_producer_entries_accounted',previous==final_index and [row['index'] for row in index]==[1,2,3,4])
    saved=read(folder/'SAVED_EVIDENCE.json')
    image_hashes=set()
    for frame in saved['frames']:
        image_hashes.add(frame['PNG_sha256'])
        check(group+'/current_frame_original_sha/'+frame['ref'],pin(frame['PNG'])['sha256']==frame['PNG_sha256']
            and pin(frame['NPZ'])['sha256']==frame['NPZ_sha256'])
    check(group+'/actual_outer_PNGs_current_source',len(owner_frames)==2 and all(value in image_hashes for value in owner_frames))
    return dict(group=group,status=publication['status'],complete_slot_ns=publication['complete_slot_ns'],
        setup_ns=clocks['owner_ready_ns']-clocks['slot_started_ns'],
        recovery_sequence_ns=clocks['business_closed_ns']-clocks['owner_ready_ns'],
        cleanup_ns=clocks['cleanup_closed_ns']-clocks['cleanup_started_ns'],public_calls=5,outer_tools=4,
        producer_indices=[row['producer_index'] for row in public_records],request_evidence=public_records,
        processes=dict(actor_cleanup=cleanup,MCP_stdio=stdio,Blender_Popen=close['Blender_close'],
            worker_close_generic_event=events[-1]['status'],
            scope='Generic worker close unknown remains separate from explicit close RPC, owned wait/reap and actual retained exits.'),
        source_identity=binding['source_sha256'],actual_host_wire=wire,worker_events=events,
        frames=saved['frames'],actual_outer_image_deliveries=len(owner_frames),wrapper_work=runtime['wrapper_work'])


def ledger():
    root=RUNTIME/'budget'
    limits=read(root/'LIMITS.json')
    check('budget/new_global_limits',limits==dict(Blender_start_attempts=2,all_rasters=12,consumer_tasks=0))
    claims=[read(path) for path in sorted((root/'claims').glob('*.json'))]
    starts=[row for row in claims if row['kind']=='Blender_start']
    rasters=[row for row in claims if row['kind']=='raster_attempt']
    businesses=[row for row in claims if row['kind']=='business_tool']
    consumers=[row for row in claims if row['kind']=='consumer_task']
    actual=upper=pending=0
    records=[]
    for claim in starts+rasters:
        path=root/'settlements'/(claim['token']+'.json')
        settled=read(path) if path.exists() else None
        check('budget/settled/'+claim['token'],settled is not None)
        if settled is None:
            pending+=1
            if claim['kind']=='raster_attempt':
                upper+=claim['reserved_upper_bound']
        else:
            check('budget/claim_sha/'+claim['token'],settled['claim_sha256']
                ==pin(root/'claims'/(claim['token']+'.json'))['sha256'])
            if claim['kind']=='raster_attempt':
                count=settled['actual_attempts']
                actual+=settled['confirmed_attempts_lower_bound'] if count is None else count
                upper+=claim['reserved_upper_bound'] if count is None else count
            else:
                check('budget/actual_owned_started/'+claim['token'],settled['spawn_status']=='spawned' and settled['pid'])
        records.append(dict(claim=claim,settlement=settled))
    render_events=sum(sum(row.get('event')=='active_observation_render_attempt' for row in rows(RUNTIME/'sessions'/group/'product_audit.jsonl')) for group in ('A','B'))
    check('budget/exact_two_owned_no_models',len(starts)==2 and len(consumers)==0 and len(businesses)==8)
    check('budget/actual_attempts_and_bounds',actual==render_events and upper<=12 and pending==0)
    return dict(owned_start_attempts=len(starts),raster_attempts_actual=actual,raster_attempts_upper=upper,
        consumer_admissions=len(consumers),paid_API_calls=0,business_admissions=len(businesses),pending=pending,
        limits=limits,records=records,source_scope='Unit raster admissions count actual construction attempts, including failed work. Unknown outcomes retain upper bounds. Legacy phase labels carry no separate cap.')


def main():
    started=time.perf_counter_ns()
    frozen=read(HERE/'FROZEN.json')
    for row in frozen['files']:
        actual=pin(row['path'])
        check('frozen/'+row['path'],actual['sha256']==row['sha256'] and actual['bytes']==row['bytes'])
    baseline=read(HERE/'BASELINE.json')
    for row in baseline['protected_direct_seals']+[baseline['candidate'],baseline['asset']]:
        actual=pin(row['path'])
        check('protected_direct/'+row['path'],actual['sha256']==row['sha256'] and actual['bytes']==row['bytes'])
    sessions=[session(group) for group in ('A','B')]
    budget=ledger()
    pin(__file__)
    check('all_pinned_inputs_unchanged',all(Path(row['path']).stat().st_size==row['bytes']
        and sha(Path(row['path']).read_bytes())==row['sha256'] for row in PINS.values()))
    passed=all(row['passed'] for row in CHECKS)
    report=dict(schema='m5-harness-recovery-runtime-review-v1',passed_checked_scope=passed,checks=CHECKS,
        failed_checks=[row for row in CHECKS if not row['passed']],input_pins=list(PINS.values()),sessions=sessions,budget=budget,
        actual_owned_sessions=2,model_consumers=0,paid_API_calls=0,failed_or_unrun_sessions=[],
        started_ns=started,closed_ns=time.perf_counter_ns(),
        author_association='Reviewer authored migration/runtime/driver/ledger and original correction candidate. Root alone executed the two real sessions. Independent response/geometry/source acceptance is reviewed separately.',
        new_operations=dict(owned_starts=0,MCP_calls=0,rasters=0,models=0),product_or_model_benefit_claim=False,
        timing_scope='Original600 root start through owned closure and SLOT_RESULT fsync. Publication marker persistence separate. Server/client samples have independent boundaries; post-reply snapshots/binding I/O is included by outer/full clocks.',
        limits_scope='Only current two sessions,68direct frozen input pins, registered direct old references and two normal141 installation checks. Historical9609 member matrix remains referenced.',
        limitations=['Counter metadata and retained arrays do not measure true allocation/copy count or transient memory.',
            'Whole-scene NativeSession guards have source-derived scope, elapsed cost included, actual loop visits unmeasured.',
            'This batch verifies real refusal recovery and the test facility. Original five model-consumer outcomes and9withheld replies remain as originally sealed.'])
    path=HERE/'RUNTIME_REVIEW.json'
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(report,stream,sort_keys=True,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=passed,checks=len(CHECKS),failed=report['failed_checks'],
        owned=budget['owned_start_attempts'],raster_actual=budget['raster_attempts_actual'],
        report_sha256=sha(path.read_bytes()))))


if __name__=='__main__':
    main()
