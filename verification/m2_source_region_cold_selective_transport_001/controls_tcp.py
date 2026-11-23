"""Replay three sealed sources through the installed connector over actual TCP."""

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import sys
from time import perf_counter_ns


sys.path.insert(0, str(Path(__file__).resolve().parent))
from controls import (BASE, BASE_GIT, FIXTURES, RUN, Replay, build_service, check_installed,
                      fixture, normalize_result, pin, prove_transmitted, require, save)


def serve_one(listener, bench, folder):
    """Receive original client bytes and send the resident host's full envelope."""
    from human_eye_plugin.blender_mcp_host import _JSONObjectBoundary

    with listener.accept()[0] as peer:
        peer.settimeout(35.)
        request = bytearray()
        state = _JSONObjectBoundary()
        while True:
            data = peer.recv(65536)
            require(data,'peer_closed_during_fixed_request')
            request.extend(data)
            require(len(request)<=2*1024*1024,'fixture_fixed_request_exceeded_bound')
            if state.feed(data):
                break
        code = json.loads(request)['params']['code']
        node = ast.parse(code).body[1]
        require(isinstance(node,ast.Assign) and node.targets[0].id=='_request','same_fixed_dispatch_required')
        command = json.loads(ast.literal_eval(node.value.args[0]))
        params = command['params']
        bounds = {key:params[key] for key in ('deadline_ns','max_response_bytes') if key in params}
        reply = bench.exchange(bytes(request),**bounds)
        response = json.dumps(reply,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()
        # Deliberately cross a JSON token boundary on each receive path.
        peer.sendall(response[:19])
        peer.sendall(response[19:])
    folder.mkdir(parents=True,exist_ok=False)
    for path,data in ((folder/'REQUEST.bin',request),(folder/'RESPONSE.bin',response)):
        with path.open('xb') as output:
            output.write(data)
    return {'command':command['command'],'TX':pin(folder/'REQUEST.bin'),'RX':pin(folder/'RESPONSE.bin'),
            'max_response_bytes':params.get('max_response_bytes')}


def run(candidate, output):
    binding,root,pins = check_installed(candidate)
    baseline,old_root,old_pins = check_installed(BASE)
    require(baseline['preparation_git']==BASE_GIT,'unchanged_baseline_install_required')
    pins.extend(old_pins)
    pins.extend((pin(__file__),pin(Path(__file__).with_name('controls.py'))))
    sys.path[:0] = [str(root),binding['dependency_root']]
    from human_eye_plugin.blender_process import HostTransportError

    cases = {}
    for name in FIXTURES:
        original = fixture(name,old_root)
        _,full,terminal,queries,truths,source_pins = original
        pins.extend(source_pins)
        query,truth = queries[0],truths[0]
        bench = Replay(root,original)
        path = output.parent/(output.stem+'_wire')/name
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
                listener.bind(('127.0.0.1',0))
                listener.listen(2)
                listener.settimeout(35.)
                bench.connector.host,bench.connector.port = listener.getsockname()
                del bench.connector._exchange
                service = build_service(root,bench,path/'service')

                def consume():
                    private = service._measure_selective_source_region('loopback',query,include_image=False)
                    public = service.observe('loopback',query=query,include_image=False)
                    require(normalize_result(private)==normalize_result(public),'exact_facts_or_source_witness_changed')
                    if name=='rail':
                        try:
                            bench.connector.capture_source_region_pair(query['region']['object'],query['reference'],
                                query['region']['world_box_m'],perf_counter_ns()+5_000_000_000,1)
                        except HostTransportError as exc:
                            require('response exceeds the size limit' in str(exc),'wrong_TCP_limit_failure/'+str(exc))
                            return private,public,str(exc)
                        raise ValueError('actual_receive_budget_was_not_enforced')
                    return private,public,None

                with ThreadPoolExecutor(max_workers=1) as client:
                    pending = client.submit(consume)
                    paths = [serve_one(listener,bench,path/f'{i:03d}') for i in range(1,4 if name=='rail' else 3)]
                    private,public,rejected = pending.result(timeout=40)
                prove_transmitted(bench.wire[0]['response'],terminal,full,query,truth)
                require([item['command'] for item in paths[:2]]==['capture_source_region_pair','capture']
                        and public['binding']['capture_scope']=='complete_scene_meshes'
                        and private['work']['raster_attempts']==0 and not private['frames'] and not public['frames'],
                        'actual_loopback_did_not_use_the_distinct_expected_scopes')
                require(paths[0]['RX']['bytes']<paths[1]['RX']['bytes'],
                        'private_host_return_did_not_reduce_fixture_loopback_wire')
                for item in paths:
                    pins.extend((item['TX'],item['RX']))
                cases[name] = {'wires':paths,'private_work':private['work']['host_capture'],
                               'exact_facts_and_source_map_equal':True,'receiver_budget_error':rejected}
        finally:
            bench.close()
    save(output,{'passed':True,'phase':'installed_actual_loopback_offline_Blender_acquisition_replayed',
        'product_git':binding['preparation_git'],'cases':cases,
        'source_pins':list({row['path']:row for row in pins}.values()),
        'actual_Blender':0,'actual_models':0,'actual_rasters':0})


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode and
            args.output.resolve().is_relative_to(RUN/'preflight'),'private_isolated_controls_output_required')
    run(args.candidate,args.output.resolve())
