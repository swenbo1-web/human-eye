"""Run the installed selective host against sealed native mesh data over loopback."""

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
from runpy import run_path
import socket
import sys
from threading import Event, Thread
from time import perf_counter_ns
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
V = HERE.parent
PRIOR = V/'m2_source_region_cold_selective_transport_001'
RECOVERY = V/'m2_source_region_cold_selective_transport_recovery_001'
RUN = Path('D:/he_m2_source_region_selective_residency_001').resolve()
LABELS = {'AA':('assembly','A'),'AB':('assembly','B'),
          'YA':('yanyite','A'),'YB':('yanyite','B')}
BINDINGS = {'A':PRIOR/'install/PRODUCT_RUN_BINDING.json','B':HERE/'install/PRODUCT_RUN_BINDING.json'}
BASE = 'a383f953c28413ccdc010869d9a7b35257416632'
OLD = run_path(str(RECOVERY/'replay_host.py'))
CONTROL, METER = OLD['CONTROL'], OLD['METER']
WIRE_METER = OLD['WIRE_METER']
request_object, fixed_command, flush = (OLD[key] for key in ('request_object','fixed_command','flush'))
require, pin, stable, save, fixture, check_installed = (
    CONTROL[key] for key in ('require','pin','stable','save','fixture','check_installed'))
PRIVATE = 'capture_source_region_pair'
PACKET = 'human-eye-private-source-region-residency-v1'
LEASE = {'document_epoch','instance_id','epoch','revision','selection_sha256','payload_sha256'}


class RecordedMeshes(CONTROL['Replay']):
    """Replace Blender's input objects and mesh extraction, retaining every cache operation."""

    def __init__(self,root,original):
        super().__init__(root,original)
        source = self.terminal['source']
        self.sources = {row['name']:row for row in self.terminal['objects']}
        extras = {row['name']:row for row in self.source['meshes']}
        self.calls = Counter()
        self.scene.name = source['scene']
        self.scene.session_uid = max(obj.session_uid for obj in self.objects)+1
        for key in ('system','length_unit'):
            setattr(self.scene.unit_settings,key,source['unit_settings'][key])
        self.graph = SimpleNamespace(scene_eval=self.scene,updates=(),object_instances=())
        bpy = self.scope['bpy']
        bpy.app.driver_namespace = {}
        bpy.data = SimpleNamespace(filepath=source['asset_copy'])
        for name in ('undo_post','redo_post','load_post'):
            setattr(bpy.app.handlers,name,[])
        layer = bpy.context.view_layer
        layer.depsgraph = self.graph
        layer.update = lambda: None
        layer.objects = SimpleNamespace(active=next((obj for obj in self.objects
            if extras[obj.name]['is_focal_target']),None))

        for nth,obj in enumerate(self.objects,1):
            row = self.sources[obj.name]
            arrays = row['evaluated']
            verts = tuple(SimpleNamespace(co=tuple(v)) for v in arrays['vertices'])
            faces = tuple(SimpleNamespace(vertices=tuple(v)) for v in arrays['triangles'])
            mesh = SimpleNamespace(vertices=verts,loop_triangles=faces,
                calc_loop_triangles=lambda o=obj:self.tick('triangulate',o))
            obj.data = SimpleNamespace(session_uid=self.scene.session_uid+nth,vertices=verts,polygons=faces)
            obj.color = tuple(channel/255 for channel in extras[obj.name]['color_rgb'])+(1.,)
            obj.to_mesh = lambda m=mesh,o=obj: self.extract(m,o)
            obj.to_mesh_clear = lambda o=obj:self.tick('clear',o)
            evaluated = SimpleNamespace(is_evaluated=True,to_mesh=obj.to_mesh,to_mesh_clear=obj.to_mesh_clear)
            obj.evaluated_get = lambda graph,o=obj,e=evaluated:self.evaluated(graph,o,e)
            obj._fixture_visible = row['visible_get']
            obj._fixture_hidden = row['display']['hide_get']
            obj.hide_viewport = row['display']['hide_viewport']
            obj.hide_render = row['display']['hide_render']
            obj.visible_get = lambda *,view_layer,o=obj:o._fixture_visible
            obj.hide_get = lambda *,view_layer,o=obj:o._fixture_hidden

    def tick(self,kind,obj):
        self.calls[kind,obj.name] += 1

    def extract(self,mesh,obj):
        self.tick('to_mesh',obj)
        return mesh

    def evaluated(self,graph,obj,value):
        require(graph is self.graph,'recorded_mesh_evaluated_on_another_graph')
        value.matrix_world = obj.matrix_world
        return value

    def attach(self,host):
        self.host = host
        require([host.object_id(obj) for obj in self.objects]==
                [row['object_id'] for row in self.terminal['objects']],
                'sealed_object_identifiers_could_not_be_reproduced')
        require(host._residency.enabled and len(host._residency.callbacks)==4
                and not host._residency.resources and not host._residency.captures,
                'native_product_residency_must_start_empty_and_enabled')

    def fingerprint(self):
        rows = [{'name':obj.name,'instance_id':obj.session_uid,'matrix_world':obj.matrix_world,
                 'vertices':[v.co for v in obj.data.vertices],'faces':[v.vertices for v in obj.data.polygons],
                 'display':[obj._fixture_visible,obj._fixture_hidden,obj.hide_viewport,obj.hide_render]}
                for obj in self.objects]
        return sha256(stable({'objects':rows,'frame':self.scene.frame_current,
            'subframe':self.scene.frame_subframe,'scale':self.scene.unit_settings.scale_length})).hexdigest()


def checked_execution(bench,request,script,command,arm,query):
    """Re-emit the fixed installed script before executing any request contents."""
    name,params = command['command'],command['params']
    fixed = {'target':query['region']['object'],'reference':query['reference'],
             'world_box_m':query['region']['world_box_m']}
    base_fields = set(fixed)|{'deadline_ns','max_response_bytes'}
    require(name==PRIVATE and (set(params)==base_fields or arm=='B' and set(params)==base_fields|{'known'})
            and all(params[key]==value for key,value in fixed.items())
            and type(params['deadline_ns']) is int and perf_counter_ns()<params['deadline_ns']
            and type(params['max_response_bytes']) is int and params['max_response_bytes']==64*1024*1024,
            'replay_host_request_or_scope_changed')
    offered = params.get('known')
    if offered is not None:
        require(type(offered) is dict and set(offered)==LEASE,'candidate_known_lease_fields_changed')
    require(script==bench.connector._observation_code(name,params,command['id']),
            'replay_will_only_execute_exact_installed_connector_script')
    response = bench.exchange(request,deadline_ns=params['deadline_ns'],
                              max_response_bytes=params['max_response_bytes'])
    prefix = 'HUMAN_EYE_BLENDER_MCP:'
    text = response['result']['result']
    require(text.startswith(prefix) and text.endswith('\n'),'replay_fixed_response_missing')
    inner = json.loads(text[len(prefix):])
    require(inner['id']==command['id'] and 'result' in inner and 'error' not in inner,
            'replay_real_host_command_failed/'+str(inner.get('error')))
    bench.connector._resident_ready = True
    packet = inner['result']
    if arm=='B':
        require(packet['schema']==PACKET,'resident_controller_did_not_receive_current_reply_protocol')
        if packet['capture'] is None:
            require(offered is not None and offered==packet['lease'],'resident_ack_without_current_matching_offer')
    return json.dumps(response,allow_nan=False,ensure_ascii=True,separators=(',',':')).encode('utf8')


def serve(bench,arm,sequence,query,peer,wire_meter,terminal,geometry_sha):
    from human_eye_plugin.blender_mcp_host import _JSONObjectBoundary

    peer.settimeout(35.)
    started = perf_counter_ns()
    request = request_object(peer,_JSONObjectBoundary())
    script,command = fixed_command(request)
    before = wire_meter['host_work']()
    before_api = bench.calls.copy()
    reply = checked_execution(bench,request,script,command,arm,query)
    work = wire_meter['finish_rpc'](before,bench.scope)
    require(work['native_work'] and work['native_work']['intervals'],'actual_replay_native_meter_missing')
    stable_source = bench.fingerprint()==geometry_sha and pin(terminal['path'])==terminal
    require(stable_source,'protected_offline_geometry_or_original_terminal_file_changed')
    peer.sendall(reply)
    peer.shutdown(socket.SHUT_WR)
    require(peer.recv(1)==b'','unexpected_extra_data_before_replay_client_EOF')
    closed = perf_counter_ns()
    work['scope'] = 'actual installed host work from replayed immutable evaluated Blender arrays'
    work['fixture_mesh_calls'] = [
        {'api':api,'object':obj,'calls':count}
        for (api,obj),count in sorted((bench.calls-before_api).items())
    ]
    event = {'sequence':sequence,'status':'completed','started_ns':started,'closed_ns':closed,
             'elapsed_ns':closed-started,'script_sha256':sha256(script.encode('utf8')).hexdigest(),
             'terminal_geometry_and_file_checks_passed':stable_source,'m2_work':work,
             'offline_fixture':True,'check_scope':'retained_replay_arrays_and_original_terminal_digest',
             'Blender_acquisition_observed':False,'real_client_EOF':True,
             'stdout_bytes':len(bench.scope['_m2_encoded'].encode('utf8')),
             'command':command['command'],'request_id':command['id']}
    index = {'sequence':sequence,'request_bytes':len(request),'response_attempted_bytes':len(reply),
             'response_sendall_completed':True,'request_response_attempted_bytes':len(request)+len(reply),
             'offline_fixture':True,'client_EOF_observed':True}
    return request,reply,index,event


def run(label,slot):
    asset,arm = LABELS[label]
    root = slot.parents[1]
    require(slot.parent.name=='slots' and slot.name==label and root.is_relative_to(RUN/'preflight')
            and root.is_dir() and not slot.exists(),'registered_residency_replay_slot_required')
    selected,product,product_pins = check_installed(BINDINGS[arm])
    baseline,baseline_root,base_pins = check_installed(CONTROL['BASE'])
    require(baseline['preparation_git']==CONTROL['BASE_GIT'] and
            (selected['preparation_git']==BASE if arm=='A' else selected['historical_preparation_git']==BASE),
            'retained_product_identity_required')
    original = fixture(asset,baseline_root)
    _,_,_,queries,_,fixture_pins = original
    terminal, = (row for row in fixture_pins if Path(row['path']).name=='TERMINAL_SOURCE.json'
                 and Path(row['path']).parent.name=='P1')
    ready,complete = root/'REPLAY_READY.json',root/'REPLAY_CLOSE.json'
    sys.path[:0] = [str(product),selected['dependency_root']]
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost

    wire_meter = run_path(str(WIRE_METER))
    bench = RecordedMeshes(product,original)
    geometry_sha = bench.fingerprint()
    old_code = BlenderMCPHost._resident_code
    BlenderMCPHost._resident_code = lambda host,*args: METER['resident_code'](old_code,host,*args)
    details = {'offline_fixture':True,'phase':'custody_bound_actual_tcp_acquisition_replay',
               'pid':os.getpid(),'label':label,'asset':asset,'arm':arm,
               'product_git':selected['preparation_git'],'product_source_sha256':selected['source_sha256'],
               'actual_Blender':0,'actual_models':0,'actual_rasters':0,'terminal_source':terminal,
               'fixture_world_sha256':geometry_sha,
               'fixture_input_scope':'immutable_evaluated_local_arrays_with_original_world_pose'}
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
                    pin(PRIOR/'controls.py'),pin(PRIOR/'meter.py'),pin(RECOVERY/'replay_host.py'),pin(WIRE_METER))}
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
    except (KeyError,OSError,TypeError,ValueError,RuntimeError) as exc:
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
