"""Hold one fixed-generation product session, including deadline and closure."""

import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
NS=HERE.parent
RUNTIME=Path('D:/he_m4_m5_source_region_001')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,ensure_ascii=False,allow_nan=False,indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def request(runtime,arguments,label,folder,deadline,expected_error=False):
    began=time.perf_counter_ns()
    request_deadline=min(deadline,began+30_000_000_000)
    runtime.client.deadline=request_deadline
    try:
        response=runtime.public_request(arguments)
    finally:
        runtime.client.deadline=deadline
    returned=time.perf_counter_ns()
    record=dict(label=label,arguments=arguments,started_ns=began,returned_ns=returned,deadline_ns=request_deadline,
                public_index=runtime._product_calls,isError=response.get('result',{}).get('isError'))
    call=folder/'product_calls'/('call_'+str(runtime._product_calls).zfill(3))
    images=[]
    delivery=call/'delivered'
    delivery.mkdir()
    for block in response.get('result',{}).get('content',[]):
        if block.get('type')=='image':
            raw=base64.b64decode(block['data'],validate=True)
            path=delivery/('image_'+str(len(images)+1).zfill(2)+'.png')
            path.write_bytes(raw)
            images.append(dict(path=str(path),sha256=sha(path),bytes=len(raw)))
    record['images']=images
    save(call/'DELIVERY.json',record)
    if returned>=request_deadline:
        raise TimeoutError('original_30_second_public_deadline')
    is_error = 'error' in response or response.get('result',{}).get('isError') is True
    if is_error != expected_error:
        raise RuntimeError('unexpected_public_error_or_success_preserved')
    record['expected_error'] = expected_error
    record['public_result'] = None if is_error else json.loads(next(block['text'] for block in response['result']['content'] if block['type']=='text'))
    return record


def run(label,version):
    started=time.perf_counter_ns()
    deadline=started+600_000_000_000
    folder=RUNTIME/'sessions'/label
    folder.mkdir(parents=True,exist_ok=False)
    result=dict(schema='m4-cross-scale-slot-v1',label=label,version=version,status='running',errors=[],requests=[],
        clocks=dict(slot_started_ns=started,owned_deadline_ns=deadline),model_consumers=0,paid_API_calls=0,cleanup={},
        run_binding_path=str(NS/(version+'_RUN_BINDING.json')))
    runtime=None
    native_handle=None
    proof=load('_cross_proof',HERE/'reused/process_proof.py')
    moved=restored=False
    try:
        frozen=read(NS/('SOURCE_FREEZE_'+version+'.json'))
        binding=read(NS/(version+'_RUN_BINDING.json'))
        for row in frozen['harness_pins']+[frozen['task'],frozen['oracle'],frozen['asset']]:
            if sha(row['path'])!=row['sha256']:
                raise ValueError('frozen_direct_input_changed/'+row['path'])
        for row in frozen['runtime_manifest']:
            if sha(Path(binding['install_root'])/row['path'])!=row['sha256']:
                raise ValueError('frozen_install_changed')
        for dependency in (binding['dependency_root'],read(NS/'SHARED_DEPENDENCY.json')['dependency_root']):
            sys.path.insert(0,dependency)
        controller=load('_cross_owned',HERE/'owned_runtime.py')
        runtime=controller.RootRuntime.start(folder,'qualification',label,version,deadline_ns=deadline)
        identity,native_handle=proof._windows_runtime_proof(runtime.native.process,runtime.native.config['pid'],deadline)
        save(folder/'NATIVE_RUNTIME_PROOF.json',identity)
        if identity.get('confirmed') is not True:
            raise RuntimeError('native_identity_unconfirmed')
        result['clocks']['ready_ns']=time.perf_counter_ns()
        sequence=read(NS/'REQUESTS.json')
        labels=sequence['state_order'] if label=='state' else sequence['main_order']
        initial_ref = None
        for stage in labels:
            if stage=='moved_old':
                save(folder/'MOVE_RECEIPT.json',runtime.native.m5_matrix_step('qa_m5_matrix_move'))
                moved=True
            if stage=='restored_old':
                save(folder/'RESTORE_RECEIPT.json',runtime.native.m5_matrix_step('qa_m5_matrix_restore'))
                restored=True
            arguments = copy.deepcopy(sequence['requests'][stage])
            if stage in sequence['use_initial_public_region_ref']:
                if initial_ref is None:
                    raise ValueError('original_public_region_ref_unavailable')
                del arguments['query']['region']
                arguments['query']['region_ref'] = copy.deepcopy(initial_ref)
            completed = request(runtime,arguments,stage,folder,deadline,stage in sequence['expected_error_stages'])
            result['requests'].append(completed)
            if stage == 'initial':
                initial_ref = copy.deepcopy(completed['public_result']['region_ref'])
        result['status']='completed'
    except BaseException as error:
        result['status']='failed'
        result['errors'].append(dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc()))
    finally:
        if runtime is not None:
            if moved and not restored and not (runtime.native.workspace/'POISONED.json').exists():
                try:
                    save(folder/'CLEANUP_RESTORE_RECEIPT.json',runtime.native.m5_matrix_step('qa_m5_matrix_restore'))
                    restored=True
                except BaseException as error:
                    result['errors'].append(dict(phase='fixture_restore',type=type(error).__name__,message=str(error)))
            try:
                close=runtime.close()
                result['cleanup']['runtime_close']=close
                if close.get('errors') or close['runtime']['errors']:
                    raise RuntimeError('runtime_close_failed')
                status=close['Blender_status']
                state=status['closed']
                if (close['Blender_close']['exit_code']!=0 or state['poisoned']
                        or state['initial_geometry_fingerprint']!=state['final_geometry_fingerprint']
                        or status['source_file_unchanged'] is not True or status['protected_files_unchanged'] is not True
                        or close['MCP_stdio_close']['confirmed'] is not True or close['MCP_retained_exit']['exit_code']!=0):
                    raise RuntimeError('source_or_process_closure_unconfirmed')
            except BaseException as error:
                result['errors'].append(dict(phase='close',type=type(error).__name__,message=str(error)))
            try:
                result['cleanup']['native_retained_exit']=proof._runtime_exit(native_handle)
                native_handle=None
                runtime.native.process._handle.Close()
                result['cleanup']['native_Popen_handle_closed']=bool(runtime.native.process._handle.closed)
                if result['cleanup']['native_retained_exit'].get('exit_code')!=0:
                    raise RuntimeError('native_exit_unconfirmed')
            except BaseException as error:
                result['errors'].append(dict(phase='native_exit',type=type(error).__name__,message=str(error)))
        if native_handle is not None:
            result['cleanup']['late_native_exit']=proof._runtime_exit(native_handle)
        result['fixture_control']=dict(moved=moved,restored=restored,source_file_saved=False)
        if result['errors'] or time.perf_counter_ns()>=deadline:
            result['status']='failed'
        result['clocks']['cleanup_closed_ns']=time.perf_counter_ns()
        save(folder/'SLOT_RESULT.json',result)
        ended=time.perf_counter_ns()
        save(folder/'SLOT_PUBLICATION.json',dict(label=label,version=version,status=result['status'],
            slot_started_ns=started,slot_result_published_ns=ended,complete_slot_ns=ended-started,
            result_sha256=sha(folder/'SLOT_RESULT.json'),owned_budget_passed=ended<deadline))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',required=True)
    parser.add_argument('--version',choices=('R0','R1'),required=True)
    args=parser.parse_args()
    result=run(args.label,args.version)
    print(json.dumps(dict(label=args.label,status=result['status'],errors=result['errors'])))
    if result['status']!='completed':
        raise SystemExit(1)
