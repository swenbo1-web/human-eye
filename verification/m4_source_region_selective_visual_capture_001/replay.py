"""Run the installed host protocol on archived RNA over real loopback TCP."""
from argparse import ArgumentParser
import ast
from contextlib import redirect_stdout
from hashlib import sha256
import importlib.util
from io import StringIO
import json
import os
from pathlib import Path
import socket
import sys
from time import perf_counter_ns
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from cold_native import retained
ROOT = Path('D:/he_m4_source_region_selective_visual_capture_001').resolve()
PRIOR = Path('D:/he_m4_source_region_live_bounds_qualification_001/REQUESTS.json')
PRIOR_SHA = 'bfc52c993fc8ee5919f7bb312619d3f548a756abe894c3aef2a2ab69f1986c7f'
COLOR_SHA = '3bf6269051a0d76689383725512f143fa232402bfa9cadfa56c972cf1d34d110'
SOURCE_SNAPSHOT = HERE.parent/'m4_source_region_live_bounds_qualification_001/replay_rna.py'
RPC_PREFIX = 'HUMAN_EYE_BLENDER_MCP:'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def raw(path):
    return Path(path).read_bytes()


def pin(path):
    return sha256(raw(path)).hexdigest()


def signed(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def frozen_inputs(args):
    require(pin(PRIOR)==PRIOR_SHA,'replay_qualification_requests_changed')
    case = json.loads(raw(PRIOR))['cases']['RAIL']
    require(args.terminal==Path(case['terminal']['path']).resolve()
            and pin(args.terminal)==case['terminal']['sha256'],
            'replay_wrong_actual_terminal')
    require(pin(args.asset)==case['asset']['sha256']==args.asset_sha256,
            'replay_wrong_rail_asset')
    source = json.loads(raw(args.terminal))
    require(source['source']['asset_sha256']==args.asset_sha256,'replay_terminal_asset_mismatch')
    wire_path = Path(case['asset']['path']).parent/'WIRE/002/RESPONSE.bin'
    require(pin(wire_path)==COLOR_SHA,'replay_actual_color_packet_changed')
    wire = json.loads(raw(wire_path))['result']['result']
    original = next(json.loads(line[len(RPC_PREFIX):]) for line in wire.splitlines()
                    if line.startswith(RPC_PREFIX))['result']
    mesh_by_id = {row['object_id']: row for row in original['capture']['meshes']}
    require(len(mesh_by_id)==len(source['objects']) and
            set(mesh_by_id)=={row['object_id'] for row in source['objects']},
            'replay_actual_color_domain')
    requests = {}
    for old in case['closed_cases']:
        query = old['query']
        requests[old['label']] = {'target':query['region']['object'], 'reference':query['reference'],
                                  'world_box_m':query['region']['world_box_m']}
    require(set(requests)=={'M21','M19'},'replay_request_domain')
    return source, mesh_by_id, [requests[label] for label in ('M21','M19')]


def replay_bpy(source, mesh_by_id):
    bpy = load_module('_m4_visual_archive_rna',SOURCE_SNAPSHOT).archive_as_bpy(source)
    graph = bpy.context.view_layer.depsgraph
    source_by_name = {row['name']: row for row in source['objects']}
    active = None
    for obj in bpy.context.scene.objects:
        mesh = mesh_by_id[source_by_name[obj.name]['object_id']]
        obj.color = [value/255 for value in mesh['color_rgb']]+[1.]
        if mesh['is_focal_target']:
            require(active is None,'replay_active_target_ambiguous')
            active = obj
        evaluated = obj.evaluated_get(graph)
        evaluated_calls = {'to_mesh':0,'triangulations':0,'to_mesh_clear':0}

        def count(action, func, counters=evaluated_calls):
            def recorded():
                counters[action] += 1
                return func()
            return recorded

        evaluated.to_mesh = count('to_mesh', evaluated.to_mesh)
        evaluated.to_mesh_clear = count('to_mesh_clear', evaluated.to_mesh_clear)
        evaluated.data.calc_loop_triangles = count('triangulations', evaluated.data.calc_loop_triangles)
        obj.replay_evaluated_calls = evaluated_calls
    bpy.context.view_layer.objects = SimpleNamespace(active=active)
    return bpy


def verify_fixture(bpy, source):
    current = bpy.context.scene.objects
    require([obj.name for obj in current]==[row['name'] for row in source['objects']],
            'replay_object_order_changed')
    graph = bpy.context.view_layer.depsgraph
    for obj, row in zip(current,source['objects'],strict=True):
        evaluated = obj.evaluated_get(graph)
        require(signed(evaluated.matrix_world)==signed(row['matrix_world'])
                and signed(obj.matrix_world)==signed(row['native_matrix_world'])
                and obj.visible_get(view_layer=bpy.context.view_layer)==row['visible_get'],
                'replay_pose_or_visibility_changed')
        for data, actual in ((obj.data,row['native']),(evaluated.data,row['evaluated'])):
            require(signed([v.co for v in data.vertices])==signed(actual['vertices'])
                    and [list(face.vertices) for face in data.loop_triangles]==actual['triangles']
                    and [list(face.vertices) for face in data.polygons]==[
                        face['vertices'] if type(face) is dict else face for face in actual['polygons']],
                    'replay_array_changed')


def installed_connector(path, label):
    binding = json.loads(raw(path))
    root = Path(binding['install_root']).resolve(strict=True)
    hashes = {item['path']:item['sha256'] for item in binding['source_manifest']}
    for name in ('blender_mcp_host.py','blender_host.py','scene_residency.py','rig_pose.py',
                 'arm_twist_weights.py','arm_twist_expert.py','arm_twist_source.py'):
        relative='human_eye_plugin/'+name
        require(pin(root/relative)==hashes[relative],'replay_loaded_source_identity/'+name)
    expected = {'A': Path('D:/he_m1_m2_source_region_scoped_measurement_001/candidate_install/product').resolve(),
                'B': ROOT/'candidate_install/product'}
    require(root==expected[label],'replay_wrong_installation')
    sys.path[:0] = [str(root),str(Path(binding['dependency_root']).resolve(strict=True))]
    from human_eye_plugin import blender_mcp_host
    require(Path(blender_mcp_host.__file__).resolve()==root/'human_eye_plugin/blender_mcp_host.py',
            'replay_connector_wrong_loader')
    return blender_mcp_host.BlenderMCPHost(root)


def exact_script(request, connector, expected, deadline):
    require(set(request)=={'type','params'} and request['type']=='execute_code'
            and type(request['params']) is dict and set(request['params'])=={'code'}
            and type(request['params']['code']) is str,
            'replay_fixed_execute_request')
    code = request['params']['code']
    assignments = [statement.value for statement in ast.parse(code).body if isinstance(statement,ast.Assign)
                   and len(statement.targets)==1 and isinstance(statement.targets[0],ast.Name)
                   and statement.targets[0].id=='_request']
    require(len(assignments)==1,'replay_generated_assignment')
    assignment = assignments[0]
    require(isinstance(assignment,ast.Call) and len(assignment.args)==1 and not assignment.keywords
            and ast.unparse(assignment.func)=='_json.loads','replay_generated_literal')
    envelope = json.loads(ast.literal_eval(assignment.args[0]))
    require(set(envelope)=={'id','command','params'}
            and type(envelope['id']) is str and len(envelope['id'])==32
            and all(c in '0123456789abcdef' for c in envelope['id'])
            and type(envelope['params']) is dict,'replay_inner_envelope')
    command, params = envelope['command'], envelope['params']
    if expected is None:
        require(command=='capture' and not params,'replay_standard_complete_capture_required')
    else:
        require(command=='capture_source_region_visual'
                and set(params)=={'query','deadline_ns','max_response_bytes'}
                and signed(params['query'])==signed(expected)
                and type(params['deadline_ns']) is int and perf_counter_ns()<params['deadline_ns']<=deadline
                and type(params['max_response_bytes']) is int and 1<=params['max_response_bytes']<=64*1024*1024,
                'replay_private_closed_box_request_mismatch')
    require(code==connector._observation_code(command,params,envelope['id']),
            'replay_host_dispatch_not_byte_exact')
    return code, envelope


def run(args):
    require(args.workspace.is_relative_to(ROOT) and args.workspace.name=='native'
            and 'slots' not in args.workspace.relative_to(ROOT).parts[:1]
            and type(args.deadline_ns) is int and perf_counter_ns()<args.deadline_ns,
            'replay_namespace_or_deadline')
    args.workspace.mkdir(parents=True,exist_ok=True)
    source, mesh_by_id, queries = frozen_inputs(args)
    asset_copy = args.workspace/'input.blend'
    if not asset_copy.exists():
        with asset_copy.open('xb') as copy:
            copy.write(raw(args.asset))
    require(pin(asset_copy)==args.asset_sha256,'replay_working_asset_binding')
    bpy = replay_bpy(source, mesh_by_id)
    connector = installed_connector(args.binding,args.label)
    meter = load_module('_m4_visual_replay_wire',HERE.parent/'m4_global_local_qualification_001/harness/reused/wire_meter.py')
    namespace={'__name__':'__m4_selective_visual_replay__','bpy':bpy}
    deadline=args.deadline_ns
    args_trace = {'boundary':'sealed current topology plus original TCP scene-delta metadata, synthesized Blender RNA',
                  'terminal_sha256':pin(args.terminal),'asset_sha256':args.asset_sha256,
                  'prior_color_packet_sha256':COLOR_SHA,'binding_sha256':pin(args.binding),
                  'actual_blender_starts':0,'geometry_array_reads_in_guards':0,
                  'evaluated_depsgraph_or_to_mesh_in_guards':0,'pid':os.getpid()}
    retained['save'](args.workspace/'COLD_POLICY.json',args_trace)
    initial=pin(args.terminal)
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as server:
        server.bind(('127.0.0.1',0))
        server.listen(2)
        retained['publish_ready'](args.workspace/'READY.json',
            dict(host='127.0.0.1',port=server.getsockname()[1],pid=os.getpid(),deadline_ns=deadline,
                 initial_fingerprint=initial,helper_sha256=pin(__file__)),deadline_ns=deadline)
        for sequence in (1,2,3):
            retained['check'](deadline)
            server.settimeout(max(.001,(deadline-perf_counter_ns())/1e9))
            connection,_=server.accept()
            with meter.WireSocket(connection,sequence) as wire:
                request=retained['_read_request'](wire,deadline)
                if sequence==3:
                    require(request=={'type':'close'},'replay_exact_close_required')
                    verify_fixture(bpy,source)
                    require(pin(asset_copy)==args.asset_sha256,'replay_closed_working_asset_changed')
                    wire.sendall(retained['encoded']({'status':'closed','pid':os.getpid(),'deadline_ns':deadline}))
                    break
                expected=queries[sequence-1] if args.label=='B' else None
                code,envelope=exact_script(request,connector,expected,deadline)
                start=perf_counter_ns()
                before=meter.host_work()
                called_before={obj.name:dict(obj.replay_evaluated_calls) for obj in bpy.context.scene.objects}
                output=StringIO()
                call=args.workspace/('call_'+str(sequence))
                call.mkdir()
                (call/'SCRIPT.py').write_bytes(code.encode('utf8'))
                with redirect_stdout(output):
                    exec(compile(code,str(call/'SCRIPT.py'),'exec'),namespace)
                out=output.getvalue()
                (call/'stdout.txt').write_bytes(out.encode('utf8'))
                rows=[json.loads(line[len(RPC_PREFIX):]) for line in out.splitlines() if line.startswith(RPC_PREFIX)]
                require(len(rows)==1 and rows[0].get('id')==envelope['id'] and
                        rows[0].get('protocol_version')=='1.0','replay_installed_envelope_missing')
                if 'result' in rows[0]:
                    connector._resident_ready=True
                    if args.label=='A':
                        connector._scene_decoder.apply(rows[0]['result'])
                intact=pin(args.terminal)==initial and pin(args.asset)==pin(asset_copy)==args.asset_sha256
                retained['check'](deadline)
                require(intact,'replay_source_asset_or_archive_changed')
                delta={obj.name:{key:value-called_before[obj.name][key]
                                 for key,value in obj.replay_evaluated_calls.items()}
                       for obj in bpy.context.scene.objects
                       if obj.replay_evaluated_calls!=called_before[obj.name]}
                retained['append'](args.workspace/'WORKER_EVENTS.jsonl',dict(
                    sequence=sequence,started_ns=start,status='completed',render_events_before=0,render_events_after=0,
                    script_sha256=sha256(code.encode('utf8')).hexdigest(),stdout_bytes=len(out.encode('utf8')),
                    stderr_bytes=0,script_error=None,changed_or_new_PNG_files=[],
                    terminal_geometry_and_file_checks_passed=intact,elapsed_ns=perf_counter_ns()-start,
                    m2_work=meter.finish_rpc(before,namespace),replay_actual_mesh_calls=delta))
                wire.sendall(retained['encoded']({'status':'success','result':{'executed':True,'result':out}}))
    meter.flush(args.workspace)
    retained['save'](args.workspace/'WORKER_CLOSED.json',dict(pid=os.getpid(),closed_ns=perf_counter_ns(),poisoned=False,
        initial_geometry_fingerprint=initial,final_geometry_fingerprint=pin(args.terminal),
        original_deadline_ns=deadline,offline_fixture=True))


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    for name in ('terminal','workspace','asset','binding'):
        parser.add_argument('--'+name,required=True,type=lambda text:Path(text).resolve())
    parser.add_argument('--asset-sha256',required=True)
    parser.add_argument('--deadline-ns',required=True,type=int)
    parser.add_argument('--label',required=True,choices=('A','B'))
    run(parser.parse_args())
