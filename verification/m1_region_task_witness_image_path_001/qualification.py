"""Run and verify the four frozen cold/hot production cases."""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0,str(NS))
from freeze import BASELINE, CANDIDATE, MATRIX, ROOT, digest, historical_readback, read, replay, require, save, verify


checker = run_path(str(NS/'checks/evidence.py'))
check_cli = run_path(str(NS.parent/'m4_dense_region_brief_001/checks/brief_schema.py'))['cli_stages']


def records(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def phases(root,source):
    calls = []
    traces = {}
    for event in records(root/'worker/product_audit.jsonl'):
        if event.get('event')=='request_trace':
            trace = event['trace']
            ident = trace['annotations'].get('mcp_request_id')
            if ident is not None:
                traces[ident] = {span['name']:span['duration_ns'] for span in trace['spans']}
    encoder = [row['image_delivery'] for row in records(root/'worker/product_audit.jsonl')
               if row.get('event')=='active_observation_mcp_content']
    for folder in sorted((root/'wire').glob('rpc_*')):
        request = read(folder/'TX.bin')
        if request.get('method')!='tools/call':
            continue
        result = read(folder/'RX.bin')
        ordinal = len(calls)+1
        receipt = read(folder/'RECEIPT.json')
        body = json.loads(result['result']['content'][0]['text'])
        raw = read(root/'worker'/f'SERVICE_RESULT_{ordinal:02}.json')
        require(request['params']==source['request']['params'] and result['result']['isError'] is False
                and raw['frames']==source['producer']['frames']
                and result['id']==request['id'] and digest(folder/'RX.bin')==receipt['RX_sha256'],
                'actual_same_capture_service_or_wire_changed/' + root.name)
        audit = encoder[ordinal-1]
        require(audit['native_blocks_constructed']==3 and audit['PNG_bytes']==7918
                and len(audit['frames'])==3,'actual_native_render_or_original_png_count_changed')
        calls.append({'request':request,'reply':result,'raw':raw,'body':body,
                      'TX_pin':replay['pin'](folder/'TX.bin'),'RX_pin':replay['pin'](folder/'RX.bin'),
                      'wall_ns':receipt['elapsed_ns'],'stages_ns':traces.get(request['id'],{}),'image_audit':audit})
    require(len(calls)==len(encoder)==2, 'exactly_one_cold_and_one_hot_observation_required')
    close = read(root/'STOCK_CLOSE.json')
    eof = read(root/'worker/EOF.json')
    held = read(root/'HELD_EOF.json')
    cache = records(root/'worker/ACTUAL_CACHE.jsonl')
    require(close['confirmed'] and close['exit_code']==0 and eof['closed'] and eof['input_eof_observed']
            and held['stdout_eof_observed'] and held['pid']==eof['pid']==close['pid']
            and held['exit_code']==0 and held['reader_stopped'] and held['process_handle_closed']
            and eof['compute_substitutions']==1 and eof['captures']==2 and eof['service_calls']==2
            and eof['socket_attempts']==eof['actual_rasters']==eof['actual_models']==eof['blocked_old_writes']==0
            and eof['archived_nonimage_inputs_unchanged'] and len(eof['png_reads'])==6
            and len(cache)==2 and cache[0]['cache_observation_python_id']==cache[1]['cache_observation_python_id']
            and calls[0]['raw']['work']['result_cache_hit'] is False
            and calls[1]['raw']['work']['result_cache_hit'] is True
            and calls[1]['raw']['work']['raster_attempts']==0 and calls[1]['raw']['work']['frame_reuses']==3,
            'real_cold_hot_cache_or_held_stdio_contract_changed/' + root.name)
    require([row['service_call'] for row in eof['png_reads']]==[1,1,1,2,2,2],
            'product_optional_paths_added_or_skipped_PNG_reads/' + root.name)
    return calls,close,eof


def public_body(value):
    body=deepcopy(value)
    body.pop('witness_image_paths',None)
    body.pop('session_id',None)
    body['binding'].pop('runtime_source_sha256',None)
    return body


def qualification():
    token=verify()
    root=ROOT/'qualification'
    root.mkdir(parents=True,exist_ok=False)
    started=[]
    outcomes={}
    try:
        for label,slot,new,isolated in MATRIX:
            binding=CANDIDATE if new else BASELINE
            source=replay['archived'](slot)
            started.append(label)
            case=replay['run_case'](root/label,binding,slot,evidence=isolated)
            calls,close,eof=phases(root/label,source)
            outcomes[label]={'slot':slot,'candidate':new,'raw':calls,'close':close,'eof':eof,'public_readback':case}
        outputs={}
        for slot in ('A1','B1'):
            old,new=(outcomes[slot+'_'+arm] for arm in ('baseline','candidate'))
            source=replay['archived'](slot)
            original_paths,original_readback=historical_readback(slot,source)
            for arm in (old,new):
                case=arm['public_readback']['read_images']
                delivered={ref:(item['local_image_path'],item['image_sha256'],raw['bytes'])
                           for ref,item,raw in zip(case['requested_refs'],case['public_paths'],case['images'],strict=True)}
                require(delivered=={ref:(row['path'],row['sha256'],row['bytes']) for ref,row in original_paths.items()},
                        'actual_public_reader_differed_from_historical_scope_or_path/' + slot)
            paired=[]
            for baseline,candidate in zip(old['raw'],new['raw'],strict=True):
                require(public_body(baseline['body'])==public_body(candidate['body'])
                        and baseline['reply']['result']['content'][1:]==candidate['reply']['result']['content'][1:]
                        and 'witness_image_paths' not in baseline['body'],
                        'candidate_changed_more_than_optional_paths/' + slot)
                native=checker['verify_public_witnesses'](candidate['reply'],candidate['raw'],slot=source['folder'],
                                      authoritative_paths=original_paths,require_paths=True)
                require(native['original_native_PNG_blocks']==3 and len(native['paths'])==2,
                        'two_complete_local_original_paths_required/' + slot)
                cli=check_cli(candidate['reply']['result'])
                size=lambda row:len(row['reply']['result']['content'][0]['text'].encode('utf8'))
                require(size(candidate)<=10800 and cli['passed'],'candidate_needed_facts_or_paths_not_delivered')
                paired.append({'baseline_text_bytes':size(baseline),'candidate_text_bytes':size(candidate),
                               'added_text_bytes':size(candidate)-size(baseline),'native':native,'fixed_CLI':cli,
                               'baseline':{key:baseline[key] for key in ('TX_pin','RX_pin','wall_ns','stages_ns','image_audit')},
                               'candidate':{key:candidate[key] for key in ('TX_pin','RX_pin','wall_ns','stages_ns','image_audit')}})
            require(paired[0]['native']['paths']==paired[1]['native']['paths'],'hot_links_differed_from_cached_cold')
            outputs[slot]={'phases':paired,'baseline_close':old['close'],'candidate_close':new['close'],
                           'historical_public_readback':original_readback,
                           'baseline_public_readback':old['public_readback'],'candidate_public_readback':new['public_readback']}
        save(root/'RESULT.json',{'passed':True,'freeze_sha256':token,'started':started,'completed_cells':4,
            'distinct_original_paths':4,'candidate_native_PNG_reads_per_observation':3,'added_PNG_reads':0,
            'new_rasters':0,'new_models':0,'Blender_starts':0,'slot_results':outputs})
        print('Qualified four preserved cold/hot cases and four original paths',token,flush=True)
    except Exception as error:
        save(root/'FAILURE.json',{'passed':False,'started_cells':started,'freeze_sha256':token,
                                  'type':type(error).__name__,'error':str(error)})
        raise


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    qualification()
