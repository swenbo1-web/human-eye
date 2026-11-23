"""Serve custody-bound offline acquisition through a real held loopback host."""

import argparse
import ast
from hashlib import sha256
import json
import os
from pathlib import Path
from runpy import run_path
import socket
import sys
from threading import Event, Thread
from time import perf_counter_ns


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent/'m2_source_region_cold_selective_transport_001'
RUN = Path('D:/he_m2_source_region_cold_selective_transport_recovery_001').resolve()
LABELS = {'AA':('assembly','A'),'AB':('assembly','B'),
          'YA':('yanyite','A'),'YB':('yanyite','B')}
CANDIDATE = 'a383f953c28413ccdc010869d9a7b35257416632'
WIRE_METER = HERE.parent/'m4_global_local_qualification_001/harness/reused/wire_meter.py'
CONTROL = run_path(str(PRIOR/'controls.py'))
METER = run_path(str(PRIOR/'meter.py'))
require, pin, stable, save, fixture, check_installed = (
    CONTROL[key] for key in ('require','pin','stable','save','fixture','check_installed'))


def request_object(peer,boundary):
    data = bytearray()
    while True:
        chunk = peer.recv(65536)
        require(chunk,'replay_client_eof_before_complete_request')
        data.extend(chunk)
        require(len(data) <= 2*1024*1024,'replay_request_limit')
        if boundary.feed(chunk):
            return bytes(data)


def fixed_command(request):
    outer = json.loads(request)
    require(type(outer) is dict and set(outer)=={'type','params'} and outer['type']=='execute_code'
            and type(outer['params']) is dict and set(outer['params'])=={'code'}
            and type(outer['params']['code']) is str,'replay_fixed_execute_envelope_required')
    script = outer['params']['code']
    assignments = [line for line in script.splitlines() if line.startswith('_request = _json.loads(')]
    require(len(assignments)==1 and assignments[0].endswith(')'),'replay_command_header_changed')
    assignment = ast.parse(assignments[0]).body[0]
    command = json.loads(ast.literal_eval(assignment.value.args[0]))
    require(type(command) is dict and set(command)=={'command','id','params'}
            and type(command['id']) is str and len(command['id'])==32
            and all(c in '0123456789abcdef' for c in command['id'])
            and type(command['params']) is dict,'replay_fixed_command_shape_changed')
    return script,command


def checked_execution(bench,request,script,command,arm,query):
    """Execute only the exact metered source emitted by the pinned connector."""
    name,params = command['command'],command['params']
    if arm=='A':
        require(name=='capture' and not params,'replay_standard_capture_required')
        bounds = {}
    else:
        fixed = {'target':query['region']['object'],'reference':query['reference'],
                 'world_box_m':query['region']['world_box_m']}
        require(name=='capture_source_region_pair' and set(params)==set(fixed)|{'deadline_ns','max_response_bytes'}
                and all(params[key]==value for key,value in fixed.items())
                and type(params['deadline_ns']) is int and perf_counter_ns()<params['deadline_ns']
                and type(params['max_response_bytes']) is int and params['max_response_bytes']==64*1024*1024,
                'replay_selective_capture_or_arguments_changed')
        bounds = {key:params[key] for key in ('deadline_ns','max_response_bytes')}
    expected = bench.connector._observation_code(name,params,command['id'])
    require(script==expected,'replay_will_only_execute_exact_installed_connector_script')
    if hasattr(bench,'host'):
        # The retained meter removes its temporary instance wrappers when it
        # finishes each RPC. Reinstall only the offline acquisition boundary.
        bench.host._capture = bench.capture
    response = bench.exchange(request,**bounds)
    prefix = 'HUMAN_EYE_BLENDER_MCP:'
    text = response['result']['result']
    require(text.startswith(prefix) and text.endswith('\n'),'replay_fixed_response_missing')
    inner = json.loads(text[len(prefix):])
    require(inner['id']==command['id'] and 'result' in inner and 'error' not in inner,
            'replay_real_host_command_failed/'+str(inner.get('error')))
    bench.connector._resident_ready = True
    if arm=='A':
        bench.connector._scene_decoder.apply(inner['result'])
    return json.dumps(response,allow_nan=False,ensure_ascii=True,separators=(',',':')).encode('utf8')


def serve(bench,arm,sequence,query,peer,wire_meter,terminal,geometry_sha):
    from human_eye_plugin.blender_mcp_host import _JSONObjectBoundary

    peer.settimeout(35.)
    started = perf_counter_ns()
    request = request_object(peer,_JSONObjectBoundary())
    script,command = fixed_command(request)
    before = wire_meter['host_work']()
    reply = checked_execution(bench,request,script,command,arm,query)
    work = wire_meter['finish_rpc'](before,bench.scope)
    require(work['native_work'] and work['native_work']['intervals'],'actual_replay_native_meter_missing')
    stable_source = sha256(stable(bench.source)).hexdigest()==geometry_sha and pin(terminal['path'])==terminal
    require(stable_source,'protected_offline_geometry_or_original_terminal_file_changed')
    peer.sendall(reply)
    peer.shutdown(socket.SHUT_WR)
    require(peer.recv(1)==b'','unexpected_extra_data_before_replay_client_EOF')
    closed = perf_counter_ns()
    event = {'sequence':sequence,'status':'completed','started_ns':started,'closed_ns':closed,
             'elapsed_ns':closed-started,'script_sha256':sha256(script.encode('utf8')).hexdigest(),
             'terminal_geometry_and_file_checks_passed':stable_source,'m2_work':work,
             'offline_fixture':True,'check_scope':'retained_replay_arrays_and_original_terminal_digest',
             'Blender_acquisition_observed':False,'real_client_EOF':True,
             'stdout_bytes':len(bench.scope['_m2_encoded'].encode('utf8')),
             'command':command['command'],'request_id':command['id']}
    work['scope'] = 'replayed frozen evaluated geometry; Blender work was not observed'
    index = {'sequence':sequence,'request_bytes':len(request),'response_attempted_bytes':len(reply),
             'response_sendall_completed':True,'request_response_attempted_bytes':len(request)+len(reply),
             'offline_fixture':True,'client_EOF_observed':True}
    return request,reply,index,event


def flush(slot,records):
    native = slot/'native'
    wire = native/'WIRE'
    wire.mkdir(parents=True,exist_ok=False)
    pins = []
    for request,reply,index,_ in records:
        folder = wire/f"{index['sequence']:03d}"
        folder.mkdir()
        for name,data in (('REQUEST.bin',request),('RESPONSE.bin',reply)):
            path = folder/name
            with path.open('xb') as out:
                out.write(data)
            pins.append(pin(path))
    save(wire/'INDEX.json',[record[2] for record in records])
    events = native/'WORKER_EVENTS.jsonl'
    with events.open('x',encoding='utf8',newline='\n') as out:
        for record in records:
            out.write(json.dumps(record[3],allow_nan=False,ensure_ascii=False,sort_keys=True)+'\n')
    return [*pins,pin(wire/'INDEX.json'),pin(events)]


def run(label,slot):
    asset,arm = LABELS[label]
    root = slot.parents[1]
    require(slot.parent.name=='slots' and slot.name==label and root.is_relative_to(RUN/'preflight')
            and root.is_dir() and not slot.exists(),'registered_recovery_replay_slot_required')
    binding_path = CONTROL['BASE'] if arm=='A' else PRIOR/'install/PRODUCT_RUN_BINDING.json'
    selected,product,product_pins = check_installed(binding_path)
    baseline,baseline_root,base_pins = check_installed(CONTROL['BASE'])
    require(baseline['preparation_git']==CONTROL['BASE_GIT']
            and selected['preparation_git']==(CONTROL['BASE_GIT'] if arm=='A' else CANDIDATE),
            'retained_product_identity_required')
    original = fixture(asset,baseline_root)
    _,_,_,queries,_,fixture_pins = original
    terminal, = (row for row in fixture_pins if Path(row['path']).name=='TERMINAL_SOURCE.json'
                 and Path(row['path']).parent.name=='P1')
    ready = root/'REPLAY_READY.json'
    complete = root/'REPLAY_CLOSE.json'
    sys.path[:0] = [str(product),selected['dependency_root']]
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost

    wire_meter = run_path(str(WIRE_METER))
    bench = CONTROL['Replay'](product,original)
    geometry_sha = sha256(stable(bench.source)).hexdigest()
    old_code = BlenderMCPHost._resident_code
    BlenderMCPHost._resident_code = lambda host,*args: METER['resident_code'](old_code,host,*args)
    details = {'offline_fixture':True,'phase':'custody_bound_actual_tcp_acquisition_replay',
               'pid':os.getpid(),'label':label,'asset':asset,'arm':arm,
               'product_git':selected['preparation_git'],'product_source_sha256':selected['source_sha256'],
               'actual_Blender':0,'actual_models':0,'actual_rasters':0,'terminal_source':terminal,
               'fixture_world_sha256':geometry_sha}
    received_close = Event()
    eof = []

    def watch_controller():
        eof.append(os.read(sys.stdin.fileno(),1)==b'')
        received_close.set()

    intake = Thread(target=watch_controller,daemon=True)
    records,error = [],None
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1',0))
            listener.listen(1)
            listener.settimeout(.2)
            host,port = listener.getsockname()
            pins = {row['path']:row for row in (*base_pins,*product_pins,*fixture_pins,pin(__file__),
                    pin(PRIOR/'controls.py'),pin(PRIOR/'meter.py'),pin(WIRE_METER))}
            save(ready,{**details,'host':host,'port':port,'started_ns':perf_counter_ns(),
                        'sources':list(pins.values())})
            intake.start()
            expected = (queries[0],queries[0],queries[1])
            deadline = perf_counter_ns()+150_000_000_000
            while not received_close.is_set():
                require(perf_counter_ns()<deadline,'held_replay_controller_eof_timeout')
                try:
                    peer,address = listener.accept()
                except TimeoutError:
                    continue
                with peer:
                    require(address[0]=='127.0.0.1' and len(records)<len(expected),
                            'unregistered_replay_TCP_request')
                    records.append(serve(bench,arm,len(records)+1,expected[len(records)],peer,
                                         wire_meter,terminal,geometry_sha))
        intake.join(timeout=1.)
        require(eof==[True] and not intake.is_alive() and len(records)==len(expected),
                'actual_replay_controller_close_or_transport_count_mismatch')
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as exc:
        error = {'type':type(exc).__name__,'message':str(exc)}
    finally:
        BlenderMCPHost._resident_code = old_code
        bench.close()
        publication = flush(slot,records) if slot.exists() else []
        save(complete,{**details,'passed':error is None,'closed_ns':perf_counter_ns(),
             'connections_completed':len(records),'actual_stdin_EOF':eof==[True],
             'listener_closed':True,'error':error,'ready':pin(ready) if ready.exists() else None,
             'wire_pins':publication})
    return int(error is not None)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'isolated_held_replay_runtime_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',choices=tuple(LABELS),required=True)
    parser.add_argument('--slot-dir',type=Path,required=True)
    options = parser.parse_args()
    raise SystemExit(run(options.label,options.slot_dir.resolve()))
