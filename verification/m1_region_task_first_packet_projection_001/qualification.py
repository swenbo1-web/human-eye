"""Run fixed production stdio cells with archived captures only."""

from argparse import ArgumentParser
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
import time
from uuid import UUID

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import launch
from launch import read, require, save

V=HERE.parent
BASE=V/'m4_source_region_blocker_frame_list_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE=HERE/'install/PRODUCT_RUN_BINDING.json'
CHECK=V/'m1_region_task_brief_client_profile_001/evidence_check.py'
EXTRAS=(('small','m4_cross_scale_projected_bounds_001','B1',1),
        ('joint','m5_joint_brief_source_projection_recovery_001','B',1))
PRIMARY=('discover_full','discover_brief','discover_omitted')
CONTROLS=('small_full','small_brief','joint_full','joint_brief','discover_no_image','no_image_brief',
          'source_region_full','source_region_no_image','source_region_unknown','active_other',
          'stale_region','after_stale','bad_png','invalid_detail','invalid_objects','after_invalid')
ERRORS={'stale_region':'source_region_ref_document_epoch_changed',
        'bad_png':'Active observation PNG source binding changed',
        'invalid_detail':'response_detail must be full or brief',
        'invalid_objects':'active_observation region_task requires whole-scene discovery without objects',
        'expired':'live_request_expired'}


def cases(slot,extras):
    items=launch.requests(slot,extras)
    items.update(invalid_detail={**items['discover_full'],'response_detail':'unsupported'},
                 invalid_objects={**items['discover_full'],'query':{**items['discover_full']['query'],
                                  'objects':[{'name':'S021'},{'name':'S055'}]}},
                 after_invalid=items['discover_omitted'],after_stale=items['discover_brief'],expired=items['discover_full'],
                 no_image_brief={**items['discover_no_image'],'response_detail':'brief'})
    items['discover_no_image']={**items['discover_no_image'],'response_detail':'full'}
    for kind in ('small','joint'):
        if kind in items:
            for detail in ('brief','full'):
                items[f'{kind}_{detail}']={**items[kind],'response_detail':detail}
    return items


def rows(path):
    if path.is_file():
        return [json.loads(line) for line in path.read_bytes().splitlines()]
    return []


def run_cell(folder,binding,slot,keys,*,isolated=False,extras=(),expiration=False):
    args=cases(slot,extras)
    begin=time.perf_counter_ns()
    out={}
    with launch.stock(folder,binding,slot,isolated=isolated,extras=extras,
                      request_budget_s=0.000001 if expiration else 30) as process:
        initialized,catalogue=launch.hello(process)
        identity=initialized['result']['_meta']['human_eye']
        require(identity['source_sha256']==read(binding)['source_sha256'] and identity['production_mode'] is True
                and identity['source_file_count']==143,'installed_production_identity_drift')
        for key in keys:
            request=launch.rpc(key,'tools/call',name=launch.TOOL,arguments=args[key])
            response=process.call(request)
            result=response['result']
            record=process.records[-1]
            wire=folder/'wire'/f'rpc_{record["index"]:02}'
            tx,rx=(wire/'TX.bin').read_bytes(),(wire/'RX.bin').read_bytes()
            require(json.loads(tx)==request and json.loads(rx)==response
                    and len(tx)==record['TX_bytes'] and len(rx)==record['RX_bytes']
                    and sha256(rx).hexdigest()==record['RX_sha256'],'exact_stdio_delivery_receipts_changed/'+key)
            text=result['content'][0]
            require(text['type']=='text' and result['isError'] is (key in ERRORS),'unanticipated_public_result/'+key+' '+text['text'][:550])
            body=json.loads(text['text'])
            if key in ERRORS:
                require(len(result['content'])==1 and ERRORS[key] in body['error'],'wrong_error_or_error_image/'+key)
            out[key]={'result':result,'wire_index':record['index'],'TX_bytes':len(tx),'RX_bytes':len(rx),
                      'text_bytes':len(text['text'].encode()),'roundtrip_ns':record['elapsed_ns'],
                      'json_decode_ns':record['consumer_json_decoded_ns']-record['received_complete_ns']}
    worker=folder/'worker'
    eof=read(worker/'EOF.json')
    invocations=rows(worker/'SERVICE_CALLS.jsonl')
    producer=rows(worker/'PRODUCER_CALLS.jsonl')
    require(eof['observe_service_calls']==len(invocations) and eof['observe_dispatches']==len(producer)
            and all('response_detail' not in row['keywords'] for row in invocations),'service_arguments_or_counts_changed')
    service_keys=[key for key in keys if key not in ('invalid_detail','invalid_objects')]
    service_arguments=[]
    if not expiration:
        require(len(invocations)==len(service_keys) and
               len(producer)==len(service_keys)-keys.count('stale_region'),
               'one_service_call_and_original_producer_per_valid_request_required')
        default_session=None
        for row,key in zip(invocations,service_keys,strict=True):
            recorded={name:value for name,value in row.items() if name!='started_ns'}
            session_id=row['session_id']
            if 'session_id' in args[key]:
                require(session_id==args[key]['session_id'],'explicit_session_binding_changed/'+key)
            else:
                require(session_id.startswith('mcp-') and UUID(session_id[4:]).version==4
                        and default_session in (None,session_id),'implicit_session_binding_changed/'+key)
                default_session=session_id
                recorded['session_id']='<generated per process>'
            service_arguments.append(recorded)
    traces={}
    for event in rows(worker/'product_audit.jsonl'):
        if event.get('event')=='request_trace':
            trace=event['trace']
            rpc_id=trace['annotations'].get('mcp_request_id')
            if rpc_id in out:
                require(rpc_id not in traces,'duplicate_same_request_audit')
                traces[rpc_id]={span['name']:span['duration_ns'] for span in trace['spans']}
    audits=iter(eof['encoder_events'])
    for key,entry in out.items():
        entry['stages_ns']=traces.get(key,{})
        if (key not in ERRORS or key=='bad_png') and not expiration:
            entry['encode_audit']=next(audits)['image_delivery']
    require(expiration or next(audits,None) is None,'unexpected_extra_encode_or_projection_pass')
    transcript={'installed_identity':identity,'catalogue':catalogue['result']['tools'],'calls':out,
                'service_arguments':service_arguments,
                'producers':[{k:v for k,v in row.items() if k!='started_ns'} for row in producer],
                'closed':read(folder/'STOCK_CLOSE.json'),'eof':eof,'full_cell_ns':time.perf_counter_ns()-begin}
    save(folder/'CELL.json',transcript)
    return transcript


def result(cell,key):
    return cell['calls'][key]['result']


def payload(cell,key):
    return json.loads(result(cell,key)['content'][0]['text'])


def without_trace_ids(reply):
    changed=deepcopy(reply)
    block=changed['content'][0]
    body=json.loads(block['text'])
    if isinstance(body.get('request_trace'),dict):
        for name in ('request_id','trace_id'):
            body['request_trace'].pop(name,None)
        block['text']=json.dumps(body,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    return changed


def definitions(standard,isolated):
    sealed=read(BASE.with_name('TOOLS_SCHEMA.json'))
    require(standard==sealed and len(standard)==len(isolated),'standard_catalogue_or_tool_count_changed')
    existing,profile=deepcopy(standard),deepcopy(isolated)
    match,=[tool for tool in profile if tool['name']==launch.TOOL]
    baseline,=[tool for tool in existing if tool['name']==launch.TOOL]
    description=match['description']
    require(description.startswith(baseline['description']) and 'omitted, brief, or full' in description
            and 'standard endpoint' in description,'isolated_directory_does_not_disclose_projection_contract')
    match['description']=baseline['description']
    require(profile==existing,'isolated_directory_changes_more_than_observe_description')
    return len(description.encode())-len(baseline['description'].encode())


def preflight(root):
    root.mkdir(parents=True,exist_ok=False)
    keys=(*PRIMARY,'bad_png','invalid_detail','after_invalid')
    a=run_cell(root/'standard',CANDIDATE,'P3',keys)
    b=run_cell(root/'isolated',CANDIDATE,'P3',keys,isolated=True)
    check=run_path(str(CHECK))
    archive=check['archived_cases']()['P3']
    require(result(a,'discover_full')==archive['full'] and result(a,'discover_brief')==result(b,'discover_full')
            ==result(b,'discover_brief')==result(b,'discover_omitted') and
            a['service_arguments']==b['service_arguments'] and a['producers']==b['producers'],
            'actual_installed_production_preflight_did_not_project_once')
    definitions(a['catalogue'],b['catalogue'])
    require(all(result(a,key)==result(b,key) for key in ('bad_png','invalid_detail','after_invalid')),
            'preflight_encoding_error_or_recovery_changed')
    save(root/'PREFLIGHT.json',{'passed':True,'scope':'candidate stock main, exact request forwarding and held exit',
                               'installed_production_cells':2,'model_starts':0,'new_rasters':0,'Blender_starts':0})


def qualification(root):
    from freeze import check_prior_public_readback, verify
    token=verify()
    root.mkdir(parents=True,exist_ok=False)
    modes=(('base',BASE,False),('standard',CANDIDATE,False),('isolated',CANDIDATE,True))
    cells={}
    for slot in ('P2','P3'):
        keys=PRIMARY if slot=='P2' else PRIMARY+CONTROLS
        extras=EXTRAS if slot=='P3' else ()
        cells[slot]={name:run_cell(root/(slot+'_'+name),binding,slot,keys,isolated=isolated,extras=extras)
                     for name,binding,isolated in modes}
    expiry={name:run_cell(root/('expired_'+name),binding,'P3',('expired',),isolated=isolated,expiration=True)
            for name,binding,isolated in modes}
    check=run_path(str(CHECK))
    gold={}
    delta=None
    for slot,arms in cells.items():
        base,standard,isolated=(arms[name] for name in ('base','standard','isolated'))
        require(base['catalogue']==standard['catalogue'],'candidate_default_actual_catalogue_changed')
        delta=definitions(standard['catalogue'],isolated['catalogue'])
        require(base['service_arguments']==standard['service_arguments']==isolated['service_arguments']
                and base['producers']==standard['producers']==isolated['producers'],'fixture_dispatch_or_service_arguments_changed')
        all_keys=base['calls']
        for key in all_keys:
            a,b,c=(without_trace_ids(result(cell,key)) for cell in (base,standard,isolated))
            if key in ('discover_full','small_full','joint_full','discover_no_image'):
                other={'discover_full':'discover_brief','small_full':'small_brief','joint_full':'joint_brief',
                       'discover_no_image':'no_image_brief'}[key]
                require(c==without_trace_ids(result(standard,other)),'isolated_projection_not_equivalent_to_standard_brief/'+slot+'/'+key)
            else:
                require(b==c,'unrelated_product_path_changed/'+slot+'/'+key)
            require(a==b,'standard_product_path_changed/'+slot+'/'+key)
        wire_index=base['calls']['discover_full']['wire_index']
        baseline_wire=root/(slot+'_base')/'wire'/f'rpc_{wire_index:02}'/'RX.bin'
        standard_wire=root/(slot+'_standard')/'wire'/f'rpc_{wire_index:02}'/'RX.bin'
        require(baseline_wire.read_bytes()==standard_wire.read_bytes(),'standard_primary_wire_bytes_changed/'+slot)
        require(result(isolated,'discover_brief')==result(isolated,'discover_omitted')==result(isolated,'discover_full'),
                'omission_or_explicit_brief_differed/'+slot)
        if slot=='P3':
            require(payload(isolated,'joint_full')['task_result']==payload(standard,'joint_brief')['task_result'] and
                    payload(isolated,'discover_no_image')['observation_status']=='prediction_only' and
                    len(result(isolated,'discover_no_image')['content'])==1 and
                    payload(isolated,'source_region_unknown')['status']=='partial',
                    'joint_measurement_no_image_or_unknown_scope_changed')
        gold[slot]={'discover_full':result(standard,'discover_full'),
                    **{key:result(isolated,key) for key in ('discover_brief','discover_omitted')}}
    comparison=check['check_products'](gold)
    for name,cell in expiry.items():
        require(payload(cell,'expired')['code']=='live_request_expired','expired_request_lost_typed_behavior/'+name)
    image_results={}
    for slot,arms in cells.items():
        response={'result':result(arms['isolated'],'discover_full')}
        dependencies=read(CANDIDATE)['dependency_root']
        if dependencies not in sys.path:
            sys.path.insert(0,dependencies)
        opened=launch.transport().inspect_images(response,root/(slot+'_decoded_originals'))
        refs=launch.fixtures(slot)['discovery']['producer']['frames']
        require(opened['PNG_bytes']==8671 and len(opened['images'])==len(refs)==3 and
                all(Path(img['path']).read_bytes()==Path(frame['image_path']).read_bytes() and
                    frame['image_sha256']==img['PNG_sha256'] for img,frame in zip(opened['images'],refs,strict=True)),
                'actual_public_native_blocks_no_longer_read_back/'+slot)
        image_results[slot]={'original_bytes':opened['PNG_bytes'],'images':opened['images'],'readback_ns':opened['elapsed_ns']}
    prior_readback=check_prior_public_readback(result(cells['P3']['isolated'],'discover_full'))
    proof={'passed':True,'freeze_sha256':token,'registered_cells':9,'closed_cells':9,
           'directory_description_delta_bytes':delta,'same_service_arguments_and_producers':True,
           'comparison':comparison,'verified_public_image_readback':image_results,
           'historical_public_readback_binding_P3':prior_readback,
           'model_starts':0,'Blender_starts':0,'new_rasters':0,
           'scope':'local production main, saved producer substitution only'}
    save(root/'RESULT.json',proof)
    print('Actual production stdio qualification passed',token,flush=True)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_interpreter_required')
    cli=ArgumentParser(description=__doc__)
    cli.add_argument('stage',choices=('preflight','qualification'))
    stage=cli.parse_args().stage
    output=launch.EXTERNAL/('production_preflight' if stage=='preflight' else 'qualification')
    try:
        globals()[stage](output)
    except Exception as error:
        if output.is_dir() and not (output/'FAILURE.json').exists():
            save(output/'FAILURE.json',{'passed':False,'stage':stage,'type':type(error).__name__,'error':str(error)})
        raise
