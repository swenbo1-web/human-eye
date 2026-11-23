"""Serve two custody-bound Yanyite host reads over owned loopback."""

import argparse
import json
import os
from pathlib import Path
from runpy import run_path
import socket
import sys
from threading import Event, Thread
from time import perf_counter_ns


HERE = Path(__file__).resolve().parent
V = HERE.parent
RUN = Path('D:/he_m1_m2_source_region_scoped_measurement_consumption_001').resolve()
PROOF = V/'m1_m2_source_region_scoped_measurement_001'
PRIOR_PATH = V/'m2_source_region_selective_residency_001/replay_host.py'
PRIOR = run_path(str(PRIOR_PATH))
AUDIT = PRIOR['CONTROL']
read = AUDIT['read']
require, pin, save = (PRIOR[key] for key in ('require','pin','save'))
BINDING = PROOF/'install/PRODUCT_RUN_BINDING.json'
TRUTH = RUN/'preflight/TRUTH.json'
PRODUCT = 'ba79e2f1ca79f4651a3acaef90988fef9a1a9fc6'
TERMINAL = 'dd47f22335c8f0fcd3e6e0aa764d5d174be89b49d9e488867813135bb64fd3e6'
ASSET = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
BOXES = (
    {'min':[-.030,-.055,.810],'max':[.030,.055,.855]},
    {'min':[-.050,.035,.530],'max':[.050,.140,.594]},
)
TARGET = '0135bbc4-c6c7-4003-a402-6f2e0283497d'
REFERENCE = 'Cube'


def execute(bench, request, script, command, arm, query):
    if arm == 'B':
        return PRIOR['checked_execution'](bench, request, script, command, 'B', query)
    name, params, identity = command['command'], command['params'], command['id']
    require(name == 'capture' and not params, 'replay_only_allows_the_registered_complete_capture')
    require(script == bench.connector._observation_code(name,params,identity),
            'replay_request_not_exact_installed_connector_script')
    response = bench.exchange(request)
    prefix = 'HUMAN_EYE_BLENDER_MCP:'
    text = response['result']['result']
    require(text.startswith(prefix) and text.endswith('\n'),'replay_response_missing_fixed_envelope')
    decoded = json.loads(text[len(prefix):])
    require(decoded['id'] == identity and 'result' in decoded and 'error' not in decoded,
            'replay_real_capture_failed/'+str(decoded.get('error')))
    bench.connector._scene_decoder.apply(decoded['result'])
    bench.connector._resident_ready = True
    return json.dumps(response,allow_nan=False,ensure_ascii=True,separators=(',',':')).encode('utf8')


def run(label, root):
    require(root.is_relative_to(RUN/'preflight') and root != RUN/'preflight',
            'only_registered_closed_replay_directory_allowed')
    root.mkdir(parents=True,exist_ok=True)
    ready, complete = root/'REPLAY_READY.json',root/'REPLAY_CLOSE.json'
    slot = root/'slots'/label
    require(not ready.exists() and not complete.exists() and not (slot/'native/WIRE').exists(),
            'replay_receipts_cannot_be_replaced')
    binding, product, product_pins = AUDIT['check_installed'](BINDING)
    require(binding['preparation_git']==PRODUCT,'same_fixed_product_required_in_both_arms')
    baseline, baseline_root, baseline_pins = AUDIT['check_installed'](AUDIT['BASE'])
    require(baseline['preparation_git']==AUDIT['BASE_GIT'],'old_wire_oracle_install_changed')
    original = AUDIT['fixture']('yanyite',baseline_root)
    _,_,terminal,_,_,fixture_pins = original
    terminal_pin, = (item for item in fixture_pins if Path(item['path']).name=='TERMINAL_SOURCE.json'
                     and Path(item['path']).parent.name=='P1')
    truth = read(TRUTH)
    require(terminal_pin['sha256'] == TERMINAL == truth['terminal_sha256']
            and Path(terminal_pin['path']) == Path(truth['terminal_path']).resolve(strict=True)
            and terminal['source']['asset_sha256'] == ASSET == truth['asset_sha256']
            and truth['target'] == TARGET and truth['reference'] == REFERENCE
            and tuple(truth['regions'][key]['box_m'] for key in ('high','low')) == BOXES,
            'retained_Yanyite_replay_not_bound_to_current_frozen_truth')
    queries = [AUDIT['public_query'](TARGET,REFERENCE,(box['min'],box['max'])) for box in BOXES]
    sys.path[:0] = [str(product),binding['dependency_root']]
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost

    wire_meter = run_path(str(PRIOR['WIRE_METER']))
    bench = PRIOR['RecordedMeshes'](product,original)
    geometry_sha = bench.fingerprint()
    original_code = BlenderMCPHost._resident_code
    BlenderMCPHost._resident_code = lambda host,*args: PRIOR['METER']['resident_code'](original_code,host,*args)
    serve = PRIOR['serve']
    serve.__globals__['checked_execution'] = execute
    details = {
        'offline_fixture':True,'phase':'actual_production_TCP_replay',
        'pid':os.getpid(),'label':label,'arm':label[0],'asset':'yanyite',
        'product_git':binding['preparation_git'],'product_source_sha256':binding['source_sha256'],
        'terminal_source':terminal_pin,'fixture_world_sha256':geometry_sha,
        'fixture_input_scope':'immutable_evaluated_local_arrays_with_original_world_pose',
        'actual_Blender':0,'actual_models':0,'actual_rasters':0,
    }
    stop, eof = Event(), []

    def wait_close():
        eof.append(os.read(sys.stdin.fileno(),1)==b'')
        stop.set()

    intake = Thread(target=wait_close,daemon=True)
    records, error = [], None
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1',0))
            listener.listen(1)
            listener.settimeout(.2)
            host, port = listener.getsockname()
            pins = {item['path']:item for item in (*baseline_pins,*product_pins,*fixture_pins,
                    pin(__file__),pin(PRIOR_PATH),pin(PRIOR['PRIOR']/'controls.py'),
                    pin(PRIOR['PRIOR']/'meter.py'),pin(PRIOR['RECOVERY']/'replay_host.py'),
                    pin(PRIOR['WIRE_METER']),pin(TRUTH))}
            save(ready,{**details,'host':host,'port':port,'started_ns':perf_counter_ns(),
                        'requests':queries,'source_pins':list(pins.values())})
            intake.start()
            deadline = perf_counter_ns()+150_000_000_000
            while not stop.is_set():
                require(perf_counter_ns()<deadline,'replay_controller_EOF_timeout')
                try:
                    peer,address = listener.accept()
                except TimeoutError:
                    continue
                with peer:
                    index = len(records)
                    require(address[0]=='127.0.0.1' and index<len(queries),'unregistered_replay_connection')
                    records.append(serve(bench,label[0],index+1,queries[index],peer,
                                         wire_meter,terminal_pin,geometry_sha))
        intake.join(timeout=1.)
        require(eof==[True] and not intake.is_alive() and len(records)==len(queries),
                'replay_actual_peer_eof_or_transport_count_mismatch')
    except (KeyError,OSError,TypeError,ValueError,RuntimeError) as exc:
        error = {'type':type(exc).__name__,'message':str(exc)}
        print(json.dumps(error,ensure_ascii=False),file=sys.stderr,flush=True)
    finally:
        BlenderMCPHost._resident_code = original_code
        bench.close()
        pins = PRIOR['flush'](slot,records) if slot.exists() else []
        save(complete,{**details,'passed':error is None,'closed_ns':perf_counter_ns(),
             'connections_completed':len(records),'actual_stdin_EOF':eof==[True],
             'listener_closed':True,'error':error,'ready':pin(ready) if ready.exists() else None,
             'wire_pins':pins})
    return int(error is not None)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'held_replay_needs_fixed_isolated_interpreter')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label',choices=('A1','B1'))
    parser.add_argument('root',type=Path)
    args=parser.parse_args()
    raise SystemExit(run(args.label,args.root.resolve()))
