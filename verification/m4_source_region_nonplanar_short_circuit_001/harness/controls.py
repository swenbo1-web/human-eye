"""Qualify the expected stale-reference error on existing and fresh held wires."""

import argparse
import json
from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import replay
from inputs import BASE, RUN, digest, pin, read, require, sealed_inputs, verify_geometry, write


def verify_expected_error(reply):
    result = reply['result']
    text, = result['content']
    body = json.loads(text['text'])
    require(text['type']=='text' and result['isError'] is True and body['status']=='error'
            and body['error']=='source_region_ref_capture_generation_changed'
            and body['execution_status']=='not_executed' and body['executed'] is False
            and body['connector_state_write_attempted'] is False and body['host_mutation_started'] is False,
            'stale_response_not_its_own_read_only_reference_error')
    return {'passed':True,'expected_mcp_error':body['error'],'require_all_fields':False,
            'original_text_bytes':len(text['text'].encode()),'stages':[]}


def adapt(path):
    namespace = run_path(path)
    if Path(path).resolve()==replay.CLI_PATH.resolve():
        succeeded = namespace['fixed_cli']

        def fixed(reply,*,require_all):
            if not require_all and reply['result']['isError'] is True:
                return verify_expected_error(reply)
            return succeeded(reply,require_all=require_all)

        namespace['fixed_cli'] = fixed
    return namespace


def review_preflight(root):
    """Score the already closed controls slot without reissuing a request."""
    fixed = sealed_inputs('main')
    requests,deltas = replay.replay_plan(fixed,True)
    worker = read(root/'REPLAY_CLOSE.json')
    held = read(root/'mcp/HELD_CLOSE.json')
    require(worker['old_sources_unchanged'] and worker['actual_Blender_starts']==worker['actual_models']==0
            and held['confirmed'] and held['process_handle_closed'] and held['production_eof_and_exit_verified']
            and held['exit_code']==0,'original_baseline_control_did_not_close')
    require(all(pin(row['path'])['sha256']==row['sha256'] for row in (held['worker_eof'],held['worker_exit'])),
            'original_preflight_control_close_pin_changed')
    bound_wire = replay.retained()['bound_wire']
    checks,pins = [],[]
    audit = root/'mcp_io/MCP_IO.jsonl'
    worker_wire = [row for line in audit.read_bytes().splitlines()
                   if (row:=json.loads(line))['method']=='tools/call']
    fixed_cli = adapt(str(replay.CLI_PATH))['fixed_cli']
    for n,(request,delta,call,w) in enumerate(zip(requests,deltas,worker['calls'],worker_wire,strict=True),1):
        here = root/'mcp'/f'rpc_{n+3:02d}'
        receipt = bound_wire(root,request,read(here/'RECEIPT.json'),w)
        response = read(here/'RX.bin')
        for name in ('TX.bin','RX.bin','RECEIPT.json'):
            pins.append(pin(here/name))
        require(receipt['id']==response['id']==request['id'] and w['raster_actual']==0
                and call['resource_count']==len(delta['resources']),'original_control_wire_identity_changed')
        source = root/f'CAPTURE_{n:02d}.json'
        captured = read(source)
        verify_geometry(captured,fixed['terminal'])
        require(captured['capture_state']==call['capture_state']==delta['capture']['capture_state']
                and captured['display_snapshot']==delta['capture']['display_snapshot'],
                'original_control_capture_generation_changed')
        pins.append(pin(source))
        proof = fixed_cli(response,require_all=n!=2)
        path = root/'product_full'/f'call_{n:03d}'/'SERVICE_RESULT.json'
        if n==2:
            require(not path.exists(),'stale_preflight_produced_a_service_result')
            details = {'is_error':True,'work':{},'stages':{}}
        else:
            prod = read(path)
            require(not prod['frames'] and prod['work']['raster_attempts']==0
                    and not prod['work']['task_query']['result_cache_hit']
                    and prod['observation_status']=='image_not_requested','preflight_control_noimage_recovery_failed')
            pins.append(pin(path))
            details = {'is_error':False,'work':prod['work'],'stages':prod['stages']}
        checks.append({'index':n,'wire':receipt,'CLI':proof,'PNG_bytes':0,'raster_attempts':0,**details})
    original_start = read(root/'mcp/START.json')
    binding = read(BASE)
    pins.extend(pin(path) for path in (audit,root/'REPLAY_CLOSE.json',root/'mcp/HELD_CLOSE.json',
                                       root/'mcp/START.json',Path(__file__)))
    report = {'passed':True,'arm':root.name,'fixture':'main','preflight':True,'controls':True,
              'derived_offline_review':True,'original_control_formatter_error':
              'actual_public_result_is_not_successful from the success-only fixed CLI checker',
              'verified_production_reruns':0,'actual_Blender_starts':0,'actual_models':0,
              'product':{key:binding[key] for key in ('preparation_git','source_sha256','wheel_sha256')},
              'source_dimensions':fixed['source_dimensions'],'held_close':pin(root/'mcp/HELD_CLOSE.json'),
              'closure':held,'source_pins':pins+fixed['source_pins']+[pin(path) for path in replay.source_paths()],
              'requests':checks,'historical_frames':[],'construct_frames':[],
              'resource_count':[call['resource_count'] for call in worker['calls']],
              'whole_window_ns':held['closed_ns']-original_start['started_ns'],
              'worker_window_ns':worker['worker_window_ns'],'memory':worker['memory']}
    write(root/'SUMMARY.json',report)
    print('Verified existing baseline control raw lines and closure without reissuing requests')


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output',type=Path)
    mode.add_argument('--review-preflight',action='store_true')
    cli.add_argument('--binding',type=Path)
    cfg = cli.parse_args()
    if cfg.review_preflight:
        require(cfg.binding is None,'review_preflight_uses_frozen_baseline')
        review_preflight((RUN/'preflight/controls').resolve(strict=True))
    else:
        require(cfg.binding is not None,'registered_binding_required')
        replay.run.__globals__['run_path'] = adapt
        replay.run(cfg.output.resolve(),cfg.binding.resolve(strict=True),'main',True,False)
